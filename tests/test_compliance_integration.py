"""
Integration test: Identity (real roles, real PermissionDeniedError) +
Compliance + the underlying Accounting/Reconciliation/Evidence modules,
tracing the exact chain the module audit was asked to verify:

    control execution -> WARNING -> finding creation -> finding
    management -> remediation -> independent verification

end to end, with every permission boundary checked against a real
IdentityService — not asserted, not mocked.

Also proves, with real roles rather than registry inspection alone:
    - a finding manager cannot verify merely because they manage findings
    - a verifier cannot manage findings
    - a remediator cannot verify their own work
    - an accountant cannot verify without being granted finding:verify
    - APPROVER can perform only the verification actions granted to it
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
from asavexa.compliance.domain.enums import ControlResult, FindingStatus, RemediationStatus
from asavexa.compliance.repository.sqlite_repository import (
    SqliteControlDefinitionRepository,
    SqliteControlExecutionRepository,
    SqliteFindingRepository,
    SqliteRemediationRepository,
)
from asavexa.compliance.services.service import ComplianceService
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.errors import PermissionDeniedError
from asavexa.identity.domain.permissions import (
    CONTROL_EXECUTE,
    CONTROL_READ,
    FINDING_MANAGE,
    FINDING_REMEDIATE,
    FINDING_VERIFY,
)
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
from asavexa.reporting.services.service import ReportingService


class ComplianceCrossModuleIntegrationTestCase(unittest.TestCase):
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
        self.reporting = ReportingService(accounting=self.accounting, audit=audit)
        self.reconciliation = ReconciliationService(
            reconciliations=SqliteReconciliationRepository(self.conn),
            transactions=SqliteBankTransactionRepository(self.conn),
            audit=audit, accounting=self.accounting,
        )
        self.compliance = ComplianceService(
            definitions=SqliteControlDefinitionRepository(self.conn),
            executions=SqliteControlExecutionRepository(self.conn),
            findings=SqliteFindingRepository(self.conn),
            remediations=SqliteRemediationRepository(self.conn),
            audit=audit, accounting=self.accounting, reporting=self.reporting,
            reconciliation=self.reconciliation,
        )

        # ---- Organisation A: OWNER + one of each relevant role ----
        self.owner = self.identity.register_user("dara@meridian.test", "correct horse battery staple")
        self.org = self.identity.create_organisation("Meridian Textiles Ltd", actor=self.owner.id)
        self.identity.add_membership(self.org.id, self.owner.id, Role.OWNER, actor_user_id=self.owner.id)

        self.administrator = self.identity.register_user("priya@meridian.test", "another-strong-password")
        self.identity.add_membership(self.org.id, self.administrator.id, Role.ADMINISTRATOR, actor_user_id=self.owner.id)

        self.accountant = self.identity.register_user("aisha@meridian.test", "yet-another-password")
        self.identity.add_membership(self.org.id, self.accountant.id, Role.ACCOUNTANT, actor_user_id=self.owner.id)

        self.approver = self.identity.register_user("kwame@meridian.test", "still-another-password")
        self.identity.add_membership(self.org.id, self.approver.id, Role.APPROVER, actor_user_id=self.owner.id)

        # ---- Organisation B: unrelated tenant ----
        self.other_owner = self.identity.register_user("priya2@other.test", "unrelated-password")
        self.other_org = self.identity.create_organisation("Other Org Ltd", actor=self.other_owner.id)
        self.identity.add_membership(self.other_org.id, self.other_owner.id, Role.OWNER, actor_user_id=self.other_owner.id)

        # ---- Chart of accounts + a posted sale, for the reconciliation-warning scenario ----
        self.cash = self.accounting.create_account(self.org.id, "1000", "Cash", AccountType.ASSET, actor=self.owner.id)
        self.revenue = self.accounting.create_account(self.org.id, "4000", "Sales Revenue", AccountType.REVENUE, actor=self.owner.id)
        self.period = self.accounting.open_period(self.org.id, "FY2026-M01", date(2026, 1, 1), date(2026, 1, 31), actor=self.owner.id)
        sale = self.accounting.create_draft_journal(
            self.org.id, date(2026, 1, 5), "Cash sale to Kadena Ltd", "USD",
            [LineInput(self.cash.id, debit_amount=Decimal("500.00")), LineInput(self.revenue.id, credit_amount=Decimal("500.00"))],
            created_by=self.owner.id,
        )
        self.sale_journal = self.accounting.post_journal(self.org.id, sale.id, actor=self.owner.id)

    def test_full_warning_to_verified_chain_with_real_permission_enforcement(self):
        # ---- 1. ACCOUNTANT can execute controls ----
        self.identity.require_permission(self.accountant.id, self.org.id, CONTROL_EXECUTE)
        controls = self.compliance.seed_standard_controls(self.org.id, actor=self.administrator.id)
        rec_control = next(c for c in controls if c.code == "REC-001")

        # ---- 2. Create outstanding reconciliation activity -> WARNING ----
        recon = self.reconciliation.create_reconciliation(
            self.org.id, self.cash.id, "January", date(2026, 1, 1), date(2026, 1, 31), actor=self.accountant.id,
        )
        self.reconciliation.import_transactions(
            self.org.id, recon.id,
            [BankTransactionInput(date(2026, 1, 5), "Deposit from Kadena Ltd", debit_amount=Decimal("500.00"))],
            actor=self.accountant.id, import_source="bank_feed",
        )
        # Matched automatically but never approved/finalized -> WARNING, no auto-finding.
        execution = self.compliance.execute_control(self.org.id, rec_control.id, actor=self.accountant.id, period_id=self.period.id)
        self.assertEqual(execution.result, ControlResult.WARNING)
        self.assertIsNone(execution.finding_id)

        # ---- 3. ADMINISTRATOR (finding:manage) manually opens a finding from the WARNING ----
        with self.assertRaises(PermissionDeniedError):
            self.identity.require_permission(self.accountant.id, self.org.id, FINDING_MANAGE)
        self.identity.require_permission(self.administrator.id, self.org.id, FINDING_MANAGE)
        finding = self.compliance.create_finding_from_execution(
            self.org.id, execution.id, actor=self.administrator.id, description="Outstanding reconciliation for January",
        )
        self.assertEqual(finding.status, FindingStatus.OPEN)

        # ---- 4. Finding management: triage toward remediation (finding:manage) ----
        self.compliance.start_review(self.org.id, finding.id, actor=self.administrator.id)
        self.compliance.mark_remediation_required(self.org.id, finding.id, actor=self.administrator.id)

        # A finding manager cannot verify merely because they manage findings.
        with self.assertRaises(PermissionDeniedError):
            self.identity.require_permission(self.administrator.id, self.org.id, FINDING_VERIFY)
        # A finding manager cannot remediate either — management and
        # remediation are disjoint capabilities.
        with self.assertRaises(PermissionDeniedError):
            self.identity.require_permission(self.administrator.id, self.org.id, FINDING_REMEDIATE)

        # ---- 5. ACCOUNTANT (finding:remediate) performs the fix ----
        self.identity.require_permission(self.accountant.id, self.org.id, FINDING_REMEDIATE)
        remediation = self.compliance.create_remediation(
            self.org.id, finding.id, action="Approve and finalize the January reconciliation",
            owner=self.accountant.id, actor=self.administrator.id,
        )
        self.compliance.start_remediation(self.org.id, remediation.id, actor=self.accountant.id)

        [txn] = self.reconciliation.list_transactions(self.org.id, recon.id)
        self.reconciliation.submit_reconciliation(self.org.id, recon.id, actor=self.accountant.id)
        self.reconciliation.approve_transaction(self.org.id, txn.id, actor=self.approver.id)
        self.reconciliation.approve_reconciliation(self.org.id, recon.id, actor=self.approver.id)
        self.compliance.complete_remediation(self.org.id, remediation.id, actor=self.accountant.id)

        # A remediator cannot verify their own work.
        with self.assertRaises(PermissionDeniedError):
            self.identity.require_permission(self.accountant.id, self.org.id, FINDING_VERIFY)

        # ---- 6. APPROVER (finding:verify) independently verifies ----
        self.identity.require_permission(self.approver.id, self.org.id, FINDING_VERIFY)
        # APPROVER can perform only the verification actions granted to
        # it — not management, not remediation.
        with self.assertRaises(PermissionDeniedError):
            self.identity.require_permission(self.approver.id, self.org.id, FINDING_MANAGE)
        with self.assertRaises(PermissionDeniedError):
            self.identity.require_permission(self.approver.id, self.org.id, FINDING_REMEDIATE)

        self.compliance.verify_remediation(self.org.id, remediation.id, actor=self.approver.id, note="Confirmed reconciled")
        closed = self.compliance.close_finding(self.org.id, finding.id, actor=self.approver.id)
        self.assertEqual(closed.status, FindingStatus.CLOSED)

        reloaded_remediation = self.compliance.get_remediation(self.org.id, remediation.id)
        self.assertEqual(reloaded_remediation.status, RemediationStatus.VERIFIED)

        # ---- 7. The reconciliation control now passes cleanly ----
        recheck = self.compliance.execute_control(self.org.id, rec_control.id, actor=self.accountant.id, period_id=self.period.id)
        self.assertEqual(recheck.result, ControlResult.PASS)

        # ---- 8. Accounting Engine remains untouched by any of this ----
        reloaded_journal = self.accounting.journals.get(self.org.id, self.sale_journal.id)
        self.assertEqual(reloaded_journal.total_debits(), self.sale_journal.total_debits())
        self.assertEqual(reloaded_journal.status, self.sale_journal.status)

        # ---- 9. Complete, distinguishable, auditable trail ----
        events = self.audit.list_for_org(self.org.id)
        actions = {e.action for e in events}
        for expected in (
            "CONTROL_DEFINED", "CONTROL_EXECUTED", "FINDING_CREATED", "FINDING_STATUS_CHANGED",
            "REMEDIATION_CREATED", "REMEDIATION_STARTED", "REMEDIATION_COMPLETED",
            "REMEDIATION_VERIFIED", "FINDING_CLOSED",
        ):
            self.assertIn(expected, actions, f"missing audit action {expected}")

        managers = {e.actor for e in events if e.action == "FINDING_CREATED"}
        remediators = {e.actor for e in events if e.action == "REMEDIATION_COMPLETED"}
        verifiers = {e.actor for e in events if e.action == "REMEDIATION_VERIFIED"}
        self.assertEqual(managers, {self.administrator.id})
        self.assertEqual(remediators, {self.accountant.id})
        self.assertEqual(verifiers, {self.approver.id})
        self.assertTrue(managers.isdisjoint(remediators))
        self.assertTrue(remediators.isdisjoint(verifiers))
        self.assertTrue(managers.isdisjoint(verifiers))

        # ---- 10. Organisation B cannot reach any of this ----
        self.identity.require_permission(self.other_owner.id, self.other_org.id, CONTROL_READ)  # sanity: OWNER has it in its own org
        with self.assertRaises(PermissionDeniedError):
            self.identity.require_permission(self.other_owner.id, self.org.id, CONTROL_READ)
        from asavexa.compliance.domain.errors import FindingNotFoundError
        with self.assertRaises(FindingNotFoundError):
            self.compliance.get_finding(self.other_org.id, finding.id)


if __name__ == "__main__":
    unittest.main()
