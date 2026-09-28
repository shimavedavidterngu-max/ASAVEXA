"""
Critical end-to-end integration test:

    ACCOUNTING -> RECONCILIATION -> EVIDENCE -> FINANCIAL REPORTING
    -> CLOSE CONTROLS -> MAKER/CHECKER -> PERIOD LOCK -> AUDIT

This is the test that proves Period Close is genuinely integrated with
the whole existing ASAVEXA architecture, not just internally consistent
on its own.
"""
import unittest
from datetime import date
from decimal import Decimal

from asavexa.accounting.domain.enums import AccountType, PeriodStatus
from asavexa.accounting.domain.errors import PeriodLockedError
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
from asavexa.identity.domain.permissions import (
    PERIOD_CLOSE_APPROVE,
    PERIOD_CLOSE_REQUEST,
    PERIOD_CLOSE_REVIEW,
)
from asavexa.identity.repository.sqlite_repository import (
    SqliteMembershipRepository,
    SqliteOrganisationRepository,
    SqliteSessionRepository,
    SqliteUserRepository,
)
from asavexa.identity.services.service import IdentityService
from asavexa.period_close.domain.enums import PeriodCloseStatus
from asavexa.period_close.repository.sqlite_repository import SqlitePeriodCloseRepository
from asavexa.period_close.services.service import PeriodCloseService
from asavexa.reconciliation.domain.models import BankTransactionInput
from asavexa.reconciliation.repository.sqlite_repository import (
    SqliteBankTransactionRepository,
    SqliteReconciliationRepository,
)
from asavexa.reconciliation.services.service import ReconciliationService
from asavexa.reporting.services.service import ReportingService


class PeriodCloseEndToEndIntegrationTestCase(unittest.TestCase):
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
        self.close = PeriodCloseService(
            accounting=self.accounting, reporting=self.reporting,
            close_processes=SqlitePeriodCloseRepository(self.conn), audit=audit,
            reconciliation=self.reconciliation, evidence=self.evidence,
        )

        # ---- 1. Organisation A with a maker (ACCOUNTANT) and checker (APPROVER) ----
        self.owner = self.identity.register_user("dara@meridian.test", "correct horse battery staple")
        self.org = self.identity.create_organisation("Meridian Textiles Ltd", actor=self.owner.id)
        self.identity.add_membership(self.org.id, self.owner.id, Role.OWNER, actor_user_id=self.owner.id)

        self.maker = self.identity.register_user("aisha@meridian.test", "another-strong-password")
        self.identity.add_membership(self.org.id, self.maker.id, Role.ACCOUNTANT, actor_user_id=self.owner.id)

        self.checker = self.identity.register_user("kwame@meridian.test", "yet-another-password")
        self.identity.add_membership(self.org.id, self.checker.id, Role.APPROVER, actor_user_id=self.owner.id)

        # ---- Organisation B: a second, unrelated tenant ----
        self.other_owner = self.identity.register_user("priya@other.test", "totally-unrelated-password")
        self.other_org = self.identity.create_organisation("Other Org Ltd", actor=self.other_owner.id)
        self.identity.add_membership(self.other_org.id, self.other_owner.id, Role.OWNER, actor_user_id=self.other_owner.id)

        # ---- 3. Open an accounting period ----
        self.cash = self.accounting.create_account(self.org.id, "1000", "Cash", AccountType.ASSET, actor=self.owner.id)
        self.equity = self.accounting.create_account(self.org.id, "3000", "Owner's Capital", AccountType.EQUITY, actor=self.owner.id)
        self.revenue = self.accounting.create_account(self.org.id, "4000", "Sales Revenue", AccountType.REVENUE, actor=self.owner.id)
        self.period = self.accounting.open_period(
            self.org.id, "FY2026-M01", date(2026, 1, 1), date(2026, 1, 31), actor=self.owner.id
        )

    def test_full_close_workflow_across_every_module(self):
        # ---- 4/5. Post valid accounting transactions ----
        investment = self.accounting.create_draft_journal(
            self.org.id, date(2026, 1, 2), "Owner investment", "USD",
            [LineInput(self.cash.id, debit_amount=Decimal("1000.00")), LineInput(self.equity.id, credit_amount=Decimal("1000.00"))],
            created_by=self.maker.id,
        )
        investment = self.accounting.post_journal(self.org.id, investment.id, actor=self.maker.id)

        sale = self.accounting.create_draft_journal(
            self.org.id, date(2026, 1, 5), "Cash sale to Kadena Ltd", "USD",
            [LineInput(self.cash.id, debit_amount=Decimal("500.00")), LineInput(self.revenue.id, credit_amount=Decimal("500.00"))],
            created_by=self.maker.id,
        )
        sale = self.accounting.post_journal(self.org.id, sale.id, actor=self.maker.id)

        # ---- 6. Perform required reconciliation ----
        recon = self.reconciliation.create_reconciliation(
            self.org.id, self.cash.id, "January", date(2026, 1, 1), date(2026, 1, 31), actor=self.maker.id,
        )
        [bank_txn] = self.reconciliation.import_transactions(
            self.org.id, recon.id,
            [BankTransactionInput(date(2026, 1, 5), "Deposit from Kadena Ltd", debit_amount=Decimal("500.00"))],
            actor=self.maker.id, import_source="bank_feed",
        )
        self.assertEqual(bank_txn.matched_journal_id, sale.id)  # deterministic auto-match worked
        self.reconciliation.submit_reconciliation(self.org.id, recon.id, actor=self.maker.id)
        self.reconciliation.approve_transaction(self.org.id, bank_txn.id, actor=self.checker.id)
        self.reconciliation.approve_reconciliation(self.org.id, recon.id, actor=self.checker.id)

        # ---- 7. Attach and verify required evidence ----
        evidence_record = self.evidence.upload_evidence(
            self.org.id, EvidenceType.INVOICE, b"fake invoice content for Kadena Ltd",
            "invoice-kadena.pdf", "application/pdf", uploaded_by=self.maker.id,
            linked_journal_id=sale.id,
        )
        sale.evidence_ref = evidence_record.id
        self.accounting.journals.update(sale)
        self.evidence.verify_evidence(self.org.id, evidence_record.id, actor=self.checker.id)

        # ---- 8/9/10. Generate the statements (Reporting, untouched by Close) ----
        trial_balance = self.reporting.get_trial_balance(self.org.id, self.period.id, actor=self.maker.id)
        income_statement = self.reporting.get_income_statement(self.org.id, self.period.id, actor=self.maker.id)
        balance_sheet = self.reporting.get_balance_sheet(self.org.id, self.period.id, actor=self.maker.id)
        self.assertTrue(trial_balance.is_balanced)
        self.assertEqual(income_statement.net_income, Decimal("500.00"))
        self.assertEqual(balance_sheet.imbalance_amount, income_statement.net_income)  # documented, expected

        # ---- 11/12. Run close-readiness checks and confirm controls pass ----
        readiness = self.close.check_close_readiness(
            self.org.id, self.period.id, actor=self.maker.id, required_evidence_refs=[evidence_record.id],
        )
        self.assertTrue(readiness.is_ready)
        self.assertEqual(readiness.blocking_failures, [])

        # ---- Permission check: maker can request, cannot approve ----
        self.identity.require_permission(self.maker.id, self.org.id, PERIOD_CLOSE_REQUEST)
        with self.assertRaises(PermissionDeniedError):
            self.identity.require_permission(self.maker.id, self.org.id, PERIOD_CLOSE_APPROVE)
        with self.assertRaises(PermissionDeniedError):
            self.identity.require_permission(self.maker.id, self.org.id, PERIOD_CLOSE_REVIEW)

        # ---- 13. Maker requests close ----
        process = self.close.request_close(
            self.org.id, self.period.id, actor=self.maker.id, required_evidence_refs=[evidence_record.id],
        )
        self.assertEqual(process.status, PeriodCloseStatus.READY_FOR_CLOSE)

        # ---- Checker permission check, then 14/15. reviews and approves ----
        self.identity.require_permission(self.checker.id, self.org.id, PERIOD_CLOSE_REVIEW)
        self.identity.require_permission(self.checker.id, self.org.id, PERIOD_CLOSE_APPROVE)
        with self.assertRaises(PermissionDeniedError):
            self.identity.require_permission(self.checker.id, self.org.id, PERIOD_CLOSE_REQUEST)

        self.close.review_close(self.org.id, process.id, actor=self.checker.id)
        finalized = self.close.approve_close(self.org.id, process.id, actor=self.checker.id)

        # ---- 16. Period becomes closed/locked ----
        self.assertEqual(finalized.status, PeriodCloseStatus.CLOSED)
        locked_period = self.accounting.periods.get(self.org.id, self.period.id)
        self.assertEqual(locked_period.status, PeriodStatus.LOCKED)

        # ---- 17/18. New posting into the closed period is rejected ----
        with self.assertRaises(PeriodLockedError):
            self.accounting.create_draft_journal(
                self.org.id, date(2026, 1, 20), "Too late", "USD",
                [LineInput(self.cash.id, debit_amount=Decimal("1.00")), LineInput(self.revenue.id, credit_amount=Decimal("1.00"))],
                created_by=self.maker.id,
            )

        # ---- 19. Existing accounting records remain unchanged ----
        reloaded_sale = self.accounting.journals.get(self.org.id, sale.id)
        self.assertEqual(reloaded_sale.total_debits(), sale.total_debits())
        self.assertEqual(reloaded_sale.status, sale.status)
        reloaded_investment = self.accounting.journals.get(self.org.id, investment.id)
        self.assertEqual(reloaded_investment.total_credits(), investment.total_credits())
        final_tb = self.accounting.get_trial_balance(self.org.id, self.period.id)
        self.assertEqual(final_tb["total_debits"], Decimal("1500.00"))

        # ---- 20. Audit trail contains the complete close sequence ----
        events = self.audit.list_for_org(self.org.id)
        actions = {e.action for e in events}
        for expected in (
            "JOURNAL_POSTED", "MATCH_ACCEPTED", "RECONCILIATION_APPROVED",
            "EVIDENCE_VERIFIED", "REPORT_GENERATED",
            "CLOSE_REQUESTED", "CLOSE_REVIEWED", "CLOSE_APPROVED", "PERIOD_CLOSED", "PERIOD_LOCKED",
        ):
            self.assertIn(expected, actions, f"missing audit action {expected}")
        maker_close_events = {e.actor for e in events if e.action == "CLOSE_REQUESTED"}
        checker_close_events = {e.actor for e in events if e.action in ("CLOSE_REVIEWED", "CLOSE_APPROVED")}
        self.assertEqual(maker_close_events, {self.maker.id})
        self.assertEqual(checker_close_events, {self.checker.id})

        # ---- 21/22. Organisation B cannot access any of this ----
        from asavexa.period_close.domain.errors import PeriodCloseProcessNotFoundError, PeriodNotFoundError
        with self.assertRaises(PeriodNotFoundError):
            self.close.check_close_readiness(self.other_org.id, self.period.id, actor=self.other_owner.id)
        with self.assertRaises(PeriodCloseProcessNotFoundError):
            self.close.get_process(self.other_org.id, process.id)
        with self.assertRaises(PermissionDeniedError):
            self.identity.require_permission(self.other_owner.id, self.org.id, PERIOD_CLOSE_APPROVE)
        other_org_period = self.accounting.periods.get(self.other_org.id, self.period.id)
        self.assertIsNone(other_org_period)  # Org A's period simply doesn't exist for Org B


if __name__ == "__main__":
    unittest.main()
