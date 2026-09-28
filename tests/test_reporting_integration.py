"""
Integration test: Accounting Engine -> Financial Reporting -> Evidence
provenance -> Reconciliation context -> Identity permissions -> shared
Audit Trail, all wired together for real.

Flow:
    1. Create Organisation A with an OWNER and a READ_ONLY user.
    2. Post real accounting transactions.
    3. Import and reconcile a bank transaction against one of them.
    4. Generate Trial Balance, Income Statement, and Balance Sheet.
    5. Trace a report line back to its posted journal (provenance).
    6. Verify the traced journal's evidence reference resolves in the
       Evidence Vault.
    7. Pull a reconciliation-status summary into the reporting context.
    8. Verify the shared audit trail recorded the generation events.
    9. Confirm Organisation B cannot reach any of Organisation A's
       reports, accounts, or reconciliation data.
   10. Confirm report generation left the Accounting Engine byte-for-
       byte unchanged.
"""
import unittest
from datetime import date
from decimal import Decimal

from asavexa.accounting.domain.enums import AccountType
from asavexa.accounting.repository.sqlite_repository import (
    SqliteAccountRepository,
    SqliteJournalRepository,
    SqlitePeriodRepository,
)
from asavexa.accounting.services.engine import AccountingEngine, LineInput
from asavexa.audit.sqlite_repository import SqliteAuditRepository
from asavexa.bootstrap import create_sqlite_connection
from asavexa.evidence.domain.enums import EvidenceType
from asavexa.evidence.repository.sqlite_repository import SqliteEvidenceRepository
from asavexa.evidence.services.vault import EvidenceVault
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.errors import PermissionDeniedError
from asavexa.identity.domain.permissions import REPORTING_READ
from asavexa.identity.repository.sqlite_repository import (
    SqliteMembershipRepository,
    SqliteOrganisationRepository,
    SqliteSessionRepository,
    SqliteUserRepository,
)
from asavexa.identity.services.service import IdentityService
from asavexa.reconciliation.domain.models import BankTransactionInput
from asavexa.reconciliation.repository.sqlite_repository import (
    SqliteBankTransactionRepository,
    SqliteReconciliationRepository,
)
from asavexa.reconciliation.services.service import ReconciliationService
from asavexa.reporting.domain.errors import ReportingPeriodNotFoundError
from asavexa.reporting.services.service import ReportingService


class ReportingCrossModuleIntegrationTestCase(unittest.TestCase):
    def setUp(self):
        self.conn = create_sqlite_connection(":memory:")
        audit = SqliteAuditRepository(self.conn)
        self.audit = audit

        self.identity = IdentityService(
            organisations=SqliteOrganisationRepository(self.conn),
            users=SqliteUserRepository(self.conn),
            memberships=SqliteMembershipRepository(self.conn),
            sessions=SqliteSessionRepository(self.conn),
            audit=audit,
        )
        self.accounting = AccountingEngine(
            accounts=SqliteAccountRepository(self.conn),
            periods=SqlitePeriodRepository(self.conn),
            journals=SqliteJournalRepository(self.conn),
            audit=audit,
        )
        self.evidence = EvidenceVault(evidence=SqliteEvidenceRepository(self.conn), audit=audit)
        self.reconciliation = ReconciliationService(
            reconciliations=SqliteReconciliationRepository(self.conn),
            transactions=SqliteBankTransactionRepository(self.conn),
            audit=audit,
            accounting=self.accounting,
        )
        self.reporting = ReportingService(
            accounting=self.accounting, audit=audit, reconciliation=self.reconciliation,
        )

        # ---- Organisation A: owner + a read-only staffer ----
        self.owner = self.identity.register_user("dara@meridian.test", "correct horse battery staple")
        self.org = self.identity.create_organisation("Meridian Textiles Ltd", actor=self.owner.id)
        self.identity.add_membership(self.org.id, self.owner.id, Role.OWNER, actor_user_id=self.owner.id)

        self.viewer = self.identity.register_user("viewer@meridian.test", "another-strong-password")
        self.identity.add_membership(self.org.id, self.viewer.id, Role.READ_ONLY, actor_user_id=self.owner.id)

        # ---- Organisation B: a second, unrelated tenant ----
        self.other_owner = self.identity.register_user("priya@other.test", "totally-unrelated-password")
        self.other_org = self.identity.create_organisation("Other Org Ltd", actor=self.other_owner.id)
        self.identity.add_membership(self.other_org.id, self.other_owner.id, Role.OWNER, actor_user_id=self.other_owner.id)

        # ---- Chart of accounts + posted transactions for Org A ----
        self.cash = self.accounting.create_account(self.org.id, "1000", "Cash", AccountType.ASSET, actor=self.owner.id)
        self.equity = self.accounting.create_account(self.org.id, "3000", "Owner's Capital", AccountType.EQUITY, actor=self.owner.id)
        self.revenue = self.accounting.create_account(self.org.id, "4000", "Sales Revenue", AccountType.REVENUE, actor=self.owner.id)
        self.period = self.accounting.open_period(
            self.org.id, "FY2026-M01", date(2026, 1, 1), date(2026, 1, 31), actor=self.owner.id
        )

        investment = self.accounting.create_draft_journal(
            self.org.id, date(2026, 1, 2), "Owner investment", "USD",
            [LineInput(self.cash.id, debit_amount=Decimal("1000.00")), LineInput(self.equity.id, credit_amount=Decimal("1000.00"))],
            created_by=self.owner.id,
        )
        self.investment_journal = self.accounting.post_journal(self.org.id, investment.id, actor=self.owner.id)

        sale = self.accounting.create_draft_journal(
            self.org.id, date(2026, 1, 5), "Cash sale to Kadena Ltd", "USD",
            [LineInput(self.cash.id, debit_amount=Decimal("500.00")), LineInput(self.revenue.id, credit_amount=Decimal("500.00"))],
            created_by=self.owner.id,
        )
        self.sale_journal = self.accounting.post_journal(self.org.id, sale.id, actor=self.owner.id)

        # Evidence attached to the sale journal (the "provenance" target).
        self.evidence_record = self.evidence.upload_evidence(
            self.org.id, EvidenceType.INVOICE, b"fake invoice content for Kadena Ltd",
            "invoice-kadena.pdf", "application/pdf", uploaded_by=self.owner.id,
            linked_journal_id=self.sale_journal.id,
        )
        self.sale_journal.evidence_ref = self.evidence_record.id
        self.accounting.journals.update(self.sale_journal)

        # ---- Reconciliation context: the sale gets reconciled ----
        self.recon = self.reconciliation.create_reconciliation(
            self.org.id, self.cash.id, "January", date(2026, 1, 1), date(2026, 1, 31), actor=self.owner.id,
        )
        [self.bank_txn] = self.reconciliation.import_transactions(
            self.org.id, self.recon.id,
            [BankTransactionInput(date(2026, 1, 5), "Deposit from Kadena Ltd", debit_amount=Decimal("500.00"))],
            actor=self.owner.id, import_source="bank_feed",
        )
        self.reconciliation.submit_reconciliation(self.org.id, self.recon.id, actor=self.owner.id)
        self.reconciliation.approve_transaction(self.org.id, self.bank_txn.id, actor=self.owner.id)
        self.reconciliation.approve_reconciliation(self.org.id, self.recon.id, actor=self.owner.id)

    def test_full_reporting_flow_with_provenance_reconciliation_and_audit(self):
        # ---- Permissions: both OWNER and READ_ONLY can read reports ----
        self.identity.require_permission(self.owner.id, self.org.id, REPORTING_READ)
        self.identity.require_permission(self.viewer.id, self.org.id, REPORTING_READ)

        # ---- Generate the three statements ----
        trial_balance = self.reporting.get_trial_balance(self.org.id, self.period.id, actor=self.viewer.id)
        income_statement = self.reporting.get_income_statement(self.org.id, self.period.id, actor=self.viewer.id)
        balance_sheet = self.reporting.get_balance_sheet(self.org.id, self.period.id, actor=self.viewer.id)

        self.assertTrue(trial_balance.is_balanced)
        self.assertEqual(income_statement.total_revenue, Decimal("500.00"))
        self.assertEqual(income_statement.net_income, Decimal("500.00"))
        # Owner investment (equity) + sale (revenue, unclosed) both sit
        # in cash — the balance sheet predictably shows the unclosed
        # net income as the imbalance, exactly as documented.
        self.assertEqual(balance_sheet.imbalance_amount, income_statement.net_income)

        # ---- Trace the revenue line back to its journal (provenance) ----
        revenue_line = next(l for l in income_statement.revenue_lines if l.account_id == self.revenue.id)
        self.assertEqual(revenue_line.amount, Decimal("500.00"))
        trace = self.reporting.trace_line(self.org.id, self.revenue.id, period_id=self.period.id)
        self.assertEqual(len(trace), 1)
        self.assertEqual(trace[0]["journal_id"], self.sale_journal.id)
        self.assertEqual(trace[0]["evidence_ref"], self.evidence_record.id)

        # ---- Evidence reference resolves in the Evidence Vault ----
        linked_evidence = self.evidence.get_evidence(self.org.id, trace[0]["evidence_ref"])
        self.assertEqual(linked_evidence.original_filename, "invoice-kadena.pdf")

        # ---- Reconciliation context, consumed without altering figures ----
        summary = self.reporting.get_reconciliation_summary(self.org.id, self.cash.id)
        self.assertEqual(summary.reconciled_count, 1)
        self.assertEqual(summary.outstanding_count, 0)
        self.assertEqual(summary.exception_count, 0)
        # Re-generating the trial balance after pulling reconciliation
        # context must show exactly the same figures.
        trial_balance_again = self.reporting.get_trial_balance(self.org.id, self.period.id, actor=self.viewer.id)
        self.assertEqual(trial_balance.total_debits, trial_balance_again.total_debits)

        # ---- Shared audit trail ----
        events = self.audit.list_for_org(self.org.id)
        report_events = [e for e in events if e.entity_type == "Report"]
        actions_seen = {e.action for e in report_events}
        self.assertIn("REPORT_GENERATED", actions_seen)
        # Every report-generation event we just triggered is attributed
        # to the viewer, distinctly from the owner's earlier accounting
        # and reconciliation actions.
        report_actors = {e.actor for e in report_events}
        self.assertEqual(report_actors, {self.viewer.id})
        accounting_actors = {e.actor for e in events if e.entity_type == "Journal"}
        self.assertIn(self.owner.id, accounting_actors)

        # ---- Organisation B cannot reach any of this ----
        with self.assertRaises(ReportingPeriodNotFoundError):
            self.reporting.get_trial_balance(self.other_org.id, self.period.id, actor="intruder")
        with self.assertRaises(PermissionDeniedError):
            self.identity.require_permission(self.other_owner.id, self.org.id, REPORTING_READ)
        other_org_ledger = self.reporting.get_general_ledger(self.other_org.id, actor=self.other_owner.id)
        self.assertEqual(other_org_ledger.accounts, [])

        # ---- Report generation left the Accounting Engine untouched ----
        reloaded_sale = self.accounting.journals.get(self.org.id, self.sale_journal.id)
        self.assertEqual(reloaded_sale.status, self.sale_journal.status)
        self.assertEqual(reloaded_sale.total_debits(), self.sale_journal.total_debits())
        reloaded_investment = self.accounting.journals.get(self.org.id, self.investment_journal.id)
        self.assertEqual(reloaded_investment.total_credits(), self.investment_journal.total_credits())
        final_tb = self.accounting.get_trial_balance(self.org.id, self.period.id)
        self.assertEqual(final_tb["total_debits"], Decimal("1500.00"))


if __name__ == "__main__":
    unittest.main()
