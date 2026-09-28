"""
Automated tests for Controls & Compliance / Audit Workspace.

Run with:  PYTHONPATH=src python3 -m unittest discover -s tests -v

Stdlib-only — exercises ComplianceService against real, SQLite-backed
Accounting, Reporting, Reconciliation, and Evidence instances.
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
from asavexa.compliance.domain.enums import (
    ControlDomain,
    ControlResult,
    ControlSeverity,
    FindingStatus,
    RemediationStatus,
)
from asavexa.compliance.domain.errors import (
    DuplicateControlCodeError,
    FindingAlreadyExistsError,
    InactiveControlError,
    InvalidFindingStateError,
    InvalidRemediationStateError,
    RemediationRequiredError,
    UnknownCheckKeyError,
)
from asavexa.compliance.repository.sqlite_repository import (
    SqliteControlDefinitionRepository,
    SqliteControlExecutionRepository,
    SqliteFindingRepository,
    SqliteRemediationRepository,
)
from asavexa.compliance.services.service import (
    CHECK_EVIDENCE_NOT_MISSING_FOR_JOURNAL,
    CHECK_EVIDENCE_REQUIRED_VALID,
    CHECK_NO_UNPOSTED_JOURNALS,
    CHECK_TRIAL_BALANCE_BALANCED,
    ComplianceService,
)
from asavexa.evidence.domain.enums import EvidenceType
from asavexa.evidence.repository.sqlite_repository import SqliteEvidenceRepository
from asavexa.evidence.services.vault import EvidenceVault
from asavexa.reconciliation.domain.models import BankTransactionInput
from asavexa.reconciliation.repository.sqlite_repository import (
    SqliteBankTransactionRepository,
    SqliteReconciliationRepository,
)
from asavexa.reconciliation.services.service import ReconciliationService
from asavexa.reporting.services.service import ReportingService

ORG_A = "org-meridian"
ORG_B = "org-other-tenant"


class ComplianceServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.conn = create_sqlite_connection(":memory:")
        audit = SqliteAuditRepository(self.conn)
        self.audit = audit

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
        self.evidence = EvidenceVault(evidence=SqliteEvidenceRepository(self.conn), audit=audit)
        self.compliance = ComplianceService(
            definitions=SqliteControlDefinitionRepository(self.conn),
            executions=SqliteControlExecutionRepository(self.conn),
            findings=SqliteFindingRepository(self.conn),
            remediations=SqliteRemediationRepository(self.conn),
            audit=audit, accounting=self.accounting, reporting=self.reporting,
            reconciliation=self.reconciliation, evidence=self.evidence,
        )

        self.cash = self.accounting.create_account(ORG_A, "1000", "Cash", AccountType.ASSET, actor="setup")
        self.revenue = self.accounting.create_account(ORG_A, "4000", "Revenue", AccountType.REVENUE, actor="setup")
        self.period = self.accounting.open_period(ORG_A, "FY2026-M01", date(2026, 1, 1), date(2026, 1, 31), actor="setup")

        self.cash_b = self.accounting.create_account(ORG_B, "1000", "Cash", AccountType.ASSET, actor="setup")
        self.period_b = self.accounting.open_period(ORG_B, "FY2026-M01", date(2026, 1, 1), date(2026, 1, 31), actor="setup")

    def _post(self, org_id, lines, txn_date, desc, actor="dara"):
        journal = self.accounting.create_draft_journal(org_id, txn_date, desc, "USD", lines, created_by=actor)
        return self.accounting.post_journal(org_id, journal.id, actor=actor)

    def _tb_control(self, org_id):
        return next(c for c in self.compliance.seed_standard_controls(org_id, actor="setup") if c.code == "ACC-001")

    # ------------------------------------------------------------------
    # Control definitions
    # ------------------------------------------------------------------
    def test_define_control_succeeds(self):
        control = self.compliance.define_control(
            ORG_A, "CUSTOM-001", "Custom check", "desc", "objective",
            ControlSeverity.MEDIUM, ControlDomain.ACCOUNTING, CHECK_TRIAL_BALANCE_BALANCED, actor="dara",
        )
        self.assertTrue(control.is_active)

    def test_duplicate_control_code_rejected(self):
        self.compliance.define_control(
            ORG_A, "DUP-001", "First", "d", "o", ControlSeverity.LOW,
            ControlDomain.ACCOUNTING, CHECK_TRIAL_BALANCE_BALANCED, actor="dara",
        )
        with self.assertRaises(DuplicateControlCodeError):
            self.compliance.define_control(
                ORG_A, "DUP-001", "Second", "d", "o", ControlSeverity.LOW,
                ControlDomain.ACCOUNTING, CHECK_NO_UNPOSTED_JOURNALS, actor="dara",
            )

    def test_unknown_check_key_rejected(self):
        with self.assertRaises(UnknownCheckKeyError):
            self.compliance.define_control(
                ORG_A, "BAD-001", "Bad", "d", "o", ControlSeverity.LOW,
                ControlDomain.ACCOUNTING, "NOT_A_REAL_CHECK", actor="dara",
            )

    def test_seed_standard_controls_is_idempotent(self):
        first = self.compliance.seed_standard_controls(ORG_A, actor="setup")
        second = self.compliance.seed_standard_controls(ORG_A, actor="setup")
        self.assertEqual({c.id for c in first}, {c.id for c in second})

    def test_deactivated_control_cannot_be_executed(self):
        control = self._tb_control(ORG_A)
        self.compliance.deactivate_control(ORG_A, control.id, actor="dara")
        with self.assertRaises(InactiveControlError):
            self.compliance.execute_control(ORG_A, control.id, actor="dara", period_id=self.period.id)

    # ------------------------------------------------------------------
    # Execution & findings — accounting controls
    # ------------------------------------------------------------------
    def test_balanced_trial_balance_passes_with_no_finding(self):
        self._post(ORG_A, [LineInput(self.cash.id, debit_amount=Decimal("100.00")), LineInput(self.revenue.id, credit_amount=Decimal("100.00"))], date(2026, 1, 5), "Sale")
        control = self._tb_control(ORG_A)
        execution = self.compliance.execute_control(ORG_A, control.id, actor="dara", period_id=self.period.id)
        self.assertEqual(execution.result, ControlResult.PASS)
        self.assertIsNone(execution.finding_id)

    def test_unposted_journal_fails_and_creates_finding_automatically(self):
        self.accounting.create_draft_journal(
            ORG_A, date(2026, 1, 5), "Unposted", "USD",
            [LineInput(self.cash.id, debit_amount=Decimal("10.00")), LineInput(self.revenue.id, credit_amount=Decimal("10.00"))],
            created_by="dara",
        )
        control = next(c for c in self.compliance.seed_standard_controls(ORG_A, actor="setup") if c.code == "ACC-002")
        execution = self.compliance.execute_control(ORG_A, control.id, actor="dara", period_id=self.period.id)
        self.assertEqual(execution.result, ControlResult.FAIL)
        self.assertIsNotNone(execution.finding_id)
        finding = self.compliance.get_finding(ORG_A, execution.finding_id)
        self.assertEqual(finding.status, FindingStatus.OPEN)
        self.assertEqual(finding.severity, control.severity)

    def test_control_never_silently_converts_fail_to_pass(self):
        """Re-executing after fixing the issue creates a NEW execution
        with its own PASS result — the original FAILed execution is
        never edited."""
        journal = self.accounting.create_draft_journal(
            ORG_A, date(2026, 1, 5), "Unposted", "USD",
            [LineInput(self.cash.id, debit_amount=Decimal("10.00")), LineInput(self.revenue.id, credit_amount=Decimal("10.00"))],
            created_by="dara",
        )
        control = next(c for c in self.compliance.seed_standard_controls(ORG_A, actor="setup") if c.code == "ACC-002")
        first = self.compliance.execute_control(ORG_A, control.id, actor="dara", period_id=self.period.id)
        self.assertEqual(first.result, ControlResult.FAIL)

        self.accounting.post_journal(ORG_A, journal.id, actor="dara")
        second = self.compliance.execute_control(ORG_A, control.id, actor="dara", period_id=self.period.id)
        self.assertEqual(second.result, ControlResult.PASS)

        # The original execution's own record is untouched.
        reloaded_first = self.compliance.get_execution(ORG_A, first.id)
        self.assertEqual(reloaded_first.result, ControlResult.FAIL)
        self.assertNotEqual(first.id, second.id)

    def test_review_execution_does_not_change_its_result(self):
        control = self._tb_control(ORG_A)
        execution = self.compliance.execute_control(ORG_A, control.id, actor="dara", period_id=self.period.id)
        reviewed = self.compliance.review_execution(ORG_A, execution.id, actor="controller")
        self.assertEqual(reviewed.result, execution.result)
        self.assertEqual(reviewed.reviewed_by, "controller")

    # ------------------------------------------------------------------
    # Evidence controls
    # ------------------------------------------------------------------
    def test_required_evidence_control_passes_when_verified(self):
        record = self.evidence.upload_evidence(ORG_A, EvidenceType.INVOICE, b"content", "i.pdf", "application/pdf", uploaded_by="dara")
        self.evidence.verify_evidence(ORG_A, record.id, actor="controller")
        control = next(c for c in self.compliance.seed_standard_controls(ORG_A, actor="setup") if c.code == "EVI-001")
        execution = self.compliance.execute_control(ORG_A, control.id, actor="dara", params={"evidence_refs": [record.id]})
        self.assertEqual(execution.result, ControlResult.PASS)

    def test_rejected_evidence_fails_required_evidence_control(self):
        record = self.evidence.upload_evidence(ORG_A, EvidenceType.INVOICE, b"content2", "i2.pdf", "application/pdf", uploaded_by="dara")
        self.evidence.reject_evidence(ORG_A, record.id, actor="controller", reason="bad scan")
        control = next(c for c in self.compliance.seed_standard_controls(ORG_A, actor="setup") if c.code == "EVI-001")
        execution = self.compliance.execute_control(ORG_A, control.id, actor="dara", params={"evidence_refs": [record.id]})
        self.assertEqual(execution.result, ControlResult.FAIL)
        self.assertIsNotNone(execution.finding_id)

    def test_evidence_missing_for_journal_fails(self):
        journal = self._post(ORG_A, [LineInput(self.cash.id, debit_amount=Decimal("50.00")), LineInput(self.revenue.id, credit_amount=Decimal("50.00"))], date(2026, 1, 5), "Sale")
        control = next(c for c in self.compliance.seed_standard_controls(ORG_A, actor="setup") if c.code == "EVI-002")
        execution = self.compliance.execute_control(ORG_A, control.id, actor="dara", params={"journal_id": journal.id})
        self.assertEqual(execution.result, ControlResult.FAIL)

    # ------------------------------------------------------------------
    # Reconciliation controls
    # ------------------------------------------------------------------
    def test_reconciliation_outstanding_is_warning_not_failure(self):
        self._post(ORG_A, [LineInput(self.cash.id, debit_amount=Decimal("500.00")), LineInput(self.revenue.id, credit_amount=Decimal("500.00"))], date(2026, 1, 5), "Sale")
        recon = self.reconciliation.create_reconciliation(ORG_A, self.cash.id, "Jan", date(2026, 1, 1), date(2026, 1, 31), actor="dara")
        self.reconciliation.import_transactions(
            ORG_A, recon.id, [BankTransactionInput(date(2026, 1, 5), "Deposit", debit_amount=Decimal("500.00"))],
            actor="dara", import_source="csv",
        )
        control = next(c for c in self.compliance.seed_standard_controls(ORG_A, actor="setup") if c.code == "REC-001")
        execution = self.compliance.execute_control(ORG_A, control.id, actor="dara", period_id=self.period.id)
        self.assertEqual(execution.result, ControlResult.WARNING)
        self.assertIsNone(execution.finding_id)  # WARNING doesn't auto-create a finding

    # ------------------------------------------------------------------
    # Reporting provenance control
    # ------------------------------------------------------------------
    def test_reporting_provenance_passes_when_traceable(self):
        self._post(ORG_A, [LineInput(self.cash.id, debit_amount=Decimal("75.00")), LineInput(self.revenue.id, credit_amount=Decimal("75.00"))], date(2026, 1, 5), "Sale")
        control = next(c for c in self.compliance.seed_standard_controls(ORG_A, actor="setup") if c.code == "REP-001")
        execution = self.compliance.execute_control(ORG_A, control.id, actor="dara", period_id=self.period.id)
        self.assertEqual(execution.result, ControlResult.PASS)

    def test_reporting_provenance_not_applicable_when_no_activity(self):
        control = next(c for c in self.compliance.seed_standard_controls(ORG_A, actor="setup") if c.code == "REP-001")
        execution = self.compliance.execute_control(ORG_A, control.id, actor="dara", period_id=self.period.id)
        self.assertEqual(execution.result, ControlResult.NOT_APPLICABLE)

    # ------------------------------------------------------------------
    # Manual finding creation for non-FAIL results
    # ------------------------------------------------------------------
    def test_manual_finding_creation_for_warning(self):
        self._post(ORG_A, [LineInput(self.cash.id, debit_amount=Decimal("500.00")), LineInput(self.revenue.id, credit_amount=Decimal("500.00"))], date(2026, 1, 5), "Sale")
        recon = self.reconciliation.create_reconciliation(ORG_A, self.cash.id, "Jan", date(2026, 1, 1), date(2026, 1, 31), actor="dara")
        self.reconciliation.import_transactions(
            ORG_A, recon.id, [BankTransactionInput(date(2026, 1, 5), "Deposit", debit_amount=Decimal("500.00"))],
            actor="dara", import_source="csv",
        )
        control = next(c for c in self.compliance.seed_standard_controls(ORG_A, actor="setup") if c.code == "REC-001")
        execution = self.compliance.execute_control(ORG_A, control.id, actor="dara", period_id=self.period.id)
        finding = self.compliance.create_finding_from_execution(ORG_A, execution.id, actor="controller")
        self.assertEqual(finding.status, FindingStatus.OPEN)
        with self.assertRaises(FindingAlreadyExistsError):
            self.compliance.create_finding_from_execution(ORG_A, execution.id, actor="controller")

    def test_cannot_manually_create_finding_from_a_passing_execution(self):
        """A PASS execution describes no problem — manually opening a
        finding against it would be nonsensical and was previously
        unguarded."""
        self._post(ORG_A, [LineInput(self.cash.id, debit_amount=Decimal("100.00")), LineInput(self.revenue.id, credit_amount=Decimal("100.00"))], date(2026, 1, 5), "Sale")
        control = self._tb_control(ORG_A)
        execution = self.compliance.execute_control(ORG_A, control.id, actor="dara", period_id=self.period.id)
        self.assertEqual(execution.result, ControlResult.PASS)
        from asavexa.compliance.domain.errors import CannotCreateFindingForResultError
        with self.assertRaises(CannotCreateFindingForResultError):
            self.compliance.create_finding_from_execution(ORG_A, execution.id, actor="controller")

    def test_cannot_manually_create_finding_from_not_applicable_execution(self):
        control = next(c for c in self.compliance.seed_standard_controls(ORG_A, actor="setup") if c.code == "EVI-001")
        execution = self.compliance.execute_control(ORG_A, control.id, actor="dara")  # no evidence_refs -> NOT_APPLICABLE
        self.assertEqual(execution.result, ControlResult.NOT_APPLICABLE)
        from asavexa.compliance.domain.errors import CannotCreateFindingForResultError
        with self.assertRaises(CannotCreateFindingForResultError):
            self.compliance.create_finding_from_execution(ORG_A, execution.id, actor="controller")

    # ------------------------------------------------------------------
    # Finding lifecycle
    # ------------------------------------------------------------------
    def _create_failing_finding(self):
        self.accounting.create_draft_journal(
            ORG_A, date(2026, 1, 5), "Unposted", "USD",
            [LineInput(self.cash.id, debit_amount=Decimal("10.00")), LineInput(self.revenue.id, credit_amount=Decimal("10.00"))],
            created_by="dara",
        )
        control = next(c for c in self.compliance.seed_standard_controls(ORG_A, actor="setup") if c.code == "ACC-002")
        execution = self.compliance.execute_control(ORG_A, control.id, actor="dara", period_id=self.period.id)
        return self.compliance.get_finding(ORG_A, execution.finding_id)

    def test_invalid_finding_transition_rejected(self):
        finding = self._create_failing_finding()
        with self.assertRaises(InvalidFindingStateError):
            self.compliance.close_finding(ORG_A, finding.id, actor="controller")  # OPEN -> CLOSED is not a direct hop

    def test_mark_remediation_required_cannot_skip_under_review(self):
        """OPEN -> REMEDIATION_REQUIRED directly is not in the transition
        table — start_review (OPEN -> UNDER_REVIEW) must happen first,
        proving the state machine can't be bypassed by calling a later
        named method out of order."""
        finding = self._create_failing_finding()
        with self.assertRaises(InvalidFindingStateError):
            self.compliance.mark_remediation_required(ORG_A, finding.id, actor="controller")

    def test_send_back_to_open_only_valid_from_under_review(self):
        finding = self._create_failing_finding()
        with self.assertRaises(InvalidFindingStateError):
            self.compliance.send_back_to_open(ORG_A, finding.id, actor="controller", reason="premature")

    def test_full_finding_and_remediation_lifecycle(self):
        finding = self._create_failing_finding()
        self.compliance.start_review(ORG_A, finding.id, actor="controller")
        self.compliance.mark_remediation_required(ORG_A, finding.id, actor="controller")

        remediation = self.compliance.create_remediation(
            ORG_A, finding.id, action="Post the missing journal", owner="dara", actor="controller",
        )
        self.assertEqual(remediation.status, RemediationStatus.PLANNED)
        self.compliance.start_remediation(ORG_A, remediation.id, actor="dara")
        self.compliance.complete_remediation(ORG_A, remediation.id, actor="dara")

        finding_after_completion = self.compliance.get_finding(ORG_A, finding.id)
        self.assertEqual(finding_after_completion.status, FindingStatus.RESOLVED)

        self.compliance.verify_remediation(ORG_A, remediation.id, actor="controller", note="confirmed posted")
        finding_after_verification = self.compliance.get_finding(ORG_A, finding.id)
        self.assertEqual(finding_after_verification.status, FindingStatus.VERIFIED)

        closed = self.compliance.close_finding(ORG_A, finding.id, actor="controller")
        self.assertEqual(closed.status, FindingStatus.CLOSED)
        self.assertEqual(closed.closed_by, "controller")

    def test_cannot_verify_remediation_that_is_not_completed(self):
        finding = self._create_failing_finding()
        self.compliance.start_review(ORG_A, finding.id, actor="controller")
        self.compliance.mark_remediation_required(ORG_A, finding.id, actor="controller")
        remediation = self.compliance.create_remediation(ORG_A, finding.id, action="Fix it", owner="dara", actor="controller")
        with self.assertRaises(RemediationRequiredError):
            self.compliance.verify_remediation(ORG_A, remediation.id, actor="controller")

    def test_reject_remediation_sends_finding_back_to_remediation_required(self):
        finding = self._create_failing_finding()
        self.compliance.start_review(ORG_A, finding.id, actor="controller")
        self.compliance.mark_remediation_required(ORG_A, finding.id, actor="controller")
        remediation = self.compliance.create_remediation(ORG_A, finding.id, action="Fix it", owner="dara", actor="controller")
        self.compliance.start_remediation(ORG_A, remediation.id, actor="dara")
        self.compliance.complete_remediation(ORG_A, remediation.id, actor="dara")

        self.compliance.reject_remediation(ORG_A, remediation.id, actor="controller", reason="not actually fixed")
        reloaded_remediation = self.compliance.get_remediation(ORG_A, remediation.id)
        self.assertEqual(reloaded_remediation.status, RemediationStatus.IN_PROGRESS)
        reloaded_finding = self.compliance.get_finding(ORG_A, finding.id)
        self.assertEqual(reloaded_finding.status, FindingStatus.REMEDIATION_REQUIRED)

    def test_closed_finding_is_terminal_until_explicit_reopen(self):
        finding = self._create_failing_finding()
        self.compliance.start_review(ORG_A, finding.id, actor="controller")
        self.compliance.mark_remediation_required(ORG_A, finding.id, actor="controller")
        remediation = self.compliance.create_remediation(ORG_A, finding.id, action="Fix it", owner="dara", actor="controller")
        self.compliance.start_remediation(ORG_A, remediation.id, actor="dara")
        self.compliance.complete_remediation(ORG_A, remediation.id, actor="dara")
        self.compliance.verify_remediation(ORG_A, remediation.id, actor="controller")
        self.compliance.close_finding(ORG_A, finding.id, actor="controller")

        with self.assertRaises(InvalidFindingStateError):
            self.compliance.start_review(ORG_A, finding.id, actor="controller")

        reopened = self.compliance.reopen_finding(ORG_A, finding.id, actor="controller", reason="issue recurred")
        self.assertEqual(reopened.status, FindingStatus.OPEN)
        self.assertIsNone(reopened.closed_by)
        # History preserves both the original close and the reopen — nothing overwritten.
        statuses_in_history = [h["status"] for h in reopened.history]
        self.assertIn("CLOSED", statuses_in_history)
        self.assertIn("OPEN", statuses_in_history)

    def test_mark_resolved_without_remediation_for_false_positive(self):
        finding = self._create_failing_finding()
        self.compliance.start_review(ORG_A, finding.id, actor="controller")
        resolved = self.compliance.mark_resolved_without_remediation(
            ORG_A, finding.id, actor="controller", reason="false positive — journal was posted by another process concurrently",
        )
        self.assertEqual(resolved.status, FindingStatus.RESOLVED)

    # ------------------------------------------------------------------
    # Tenant isolation
    # ------------------------------------------------------------------
    def test_organisation_b_cannot_read_organisation_a_control(self):
        control = self._tb_control(ORG_A)
        from asavexa.compliance.domain.errors import ControlDefinitionNotFoundError
        with self.assertRaises(ControlDefinitionNotFoundError):
            self.compliance.get_control(ORG_B, control.id)

    def test_organisation_b_cannot_execute_organisation_a_control(self):
        control = self._tb_control(ORG_A)
        from asavexa.compliance.domain.errors import ControlDefinitionNotFoundError
        with self.assertRaises(ControlDefinitionNotFoundError):
            self.compliance.execute_control(ORG_B, control.id, actor="intruder", period_id=self.period_b.id)

    def test_organisation_b_cannot_read_organisation_a_finding(self):
        finding = self._create_failing_finding()
        from asavexa.compliance.domain.errors import FindingNotFoundError
        with self.assertRaises(FindingNotFoundError):
            self.compliance.get_finding(ORG_B, finding.id)

    def test_organisation_b_cannot_modify_organisation_a_finding(self):
        finding = self._create_failing_finding()
        from asavexa.compliance.domain.errors import FindingNotFoundError
        with self.assertRaises(FindingNotFoundError):
            self.compliance.start_review(ORG_B, finding.id, actor="intruder")

    def test_organisation_b_controls_are_independent(self):
        self.compliance.seed_standard_controls(ORG_A, actor="setup")
        org_b_controls = self.compliance.list_controls(ORG_B)
        self.assertEqual(org_b_controls, [])

    # ------------------------------------------------------------------
    # Audit trail
    # ------------------------------------------------------------------
    def test_full_lifecycle_is_audit_logged_with_distinguishable_actors(self):
        finding = self._create_failing_finding()
        self.compliance.start_review(ORG_A, finding.id, actor="controller")
        self.compliance.mark_remediation_required(ORG_A, finding.id, actor="controller")
        remediation = self.compliance.create_remediation(ORG_A, finding.id, action="Fix it", owner="dara", actor="controller")
        self.compliance.start_remediation(ORG_A, remediation.id, actor="dara")
        self.compliance.complete_remediation(ORG_A, remediation.id, actor="dara")
        self.compliance.verify_remediation(ORG_A, remediation.id, actor="controller")
        self.compliance.close_finding(ORG_A, finding.id, actor="controller")

        events = self.audit.list_for_org(ORG_A)
        actions = {e.action for e in events}
        for expected in (
            "CONTROL_DEFINED", "CONTROL_EXECUTED", "FINDING_CREATED", "FINDING_STATUS_CHANGED",
            "REMEDIATION_CREATED", "REMEDIATION_COMPLETED", "REMEDIATION_VERIFIED", "FINDING_CLOSED",
        ):
            self.assertIn(expected, actions, f"missing audit action {expected}")

        remediators = {e.actor for e in events if e.action == "REMEDIATION_COMPLETED"}
        verifiers = {e.actor for e in events if e.action == "REMEDIATION_VERIFIED"}
        self.assertEqual(remediators, {"dara"})
        self.assertEqual(verifiers, {"controller"})
        self.assertTrue(remediators.isdisjoint(verifiers))

    def test_start_remediation_is_audit_logged(self):
        """Previously start_remediation (PLANNED -> IN_PROGRESS) logged
        nothing at all — found during the module audit."""
        finding = self._create_failing_finding()
        self.compliance.start_review(ORG_A, finding.id, actor="controller")
        self.compliance.mark_remediation_required(ORG_A, finding.id, actor="controller")
        remediation = self.compliance.create_remediation(ORG_A, finding.id, action="Fix it", owner="dara", actor="controller")
        self.compliance.start_remediation(ORG_A, remediation.id, actor="dara")

        events = self.audit.list_for_entity("Remediation", remediation.id, org_id=ORG_A)
        actions = {e.action for e in events}
        self.assertIn("REMEDIATION_STARTED", actions)
        started_event = next(e for e in events if e.action == "REMEDIATION_STARTED")
        self.assertEqual(started_event.actor, "dara")

    def test_reject_remediation_is_audit_logged_distinctly_from_finding_change(self):
        """Previously the remediation-level rejection had no dedicated
        audit action of its own — only the finding's
        FINDING_STATUS_CHANGED event recorded anything. Found during the
        module audit."""
        finding = self._create_failing_finding()
        self.compliance.start_review(ORG_A, finding.id, actor="controller")
        self.compliance.mark_remediation_required(ORG_A, finding.id, actor="controller")
        remediation = self.compliance.create_remediation(ORG_A, finding.id, action="Fix it", owner="dara", actor="controller")
        self.compliance.start_remediation(ORG_A, remediation.id, actor="dara")
        self.compliance.complete_remediation(ORG_A, remediation.id, actor="dara")
        self.compliance.reject_remediation(ORG_A, remediation.id, actor="controller", reason="not actually fixed")

        remediation_events = self.audit.list_for_entity("Remediation", remediation.id, org_id=ORG_A)
        self.assertTrue(any(e.action == "REMEDIATION_REJECTED" for e in remediation_events))
        rejected_event = next(e for e in remediation_events if e.action == "REMEDIATION_REJECTED")
        self.assertEqual(rejected_event.actor, "controller")
        self.assertEqual(rejected_event.reason, "not actually fixed")

    # ------------------------------------------------------------------
    # Repository-level tenant isolation (not just service-level) — the
    # audit's explicit ask: verify the layer below the service also
    # scopes data, not merely that the service happens to raise.
    # ------------------------------------------------------------------
    def test_repository_get_returns_none_across_tenants_for_every_entity(self):
        control = self._tb_control(ORG_A)
        execution = self.compliance.execute_control(ORG_A, control.id, actor="dara", period_id=self.period.id)
        finding = self._create_failing_finding()
        self.compliance.start_review(ORG_A, finding.id, actor="controller")
        self.compliance.mark_remediation_required(ORG_A, finding.id, actor="controller")
        remediation = self.compliance.create_remediation(ORG_A, finding.id, action="Fix it", owner="dara", actor="controller")

        # Direct repository calls, bypassing the service entirely —
        # proving isolation lives below the service layer too, not only
        # in the *Error raised by ComplianceService's own guard methods.
        self.assertIsNone(self.compliance.definitions.get(ORG_B, control.id))
        self.assertIsNone(self.compliance.executions.get(ORG_B, execution.id))
        self.assertIsNone(self.compliance.findings.get(ORG_B, finding.id))
        self.assertIsNone(self.compliance.remediations.get(ORG_B, remediation.id))

    def test_organisation_b_cannot_remediate_organisation_a_finding(self):
        finding = self._create_failing_finding()
        self.compliance.start_review(ORG_A, finding.id, actor="controller")
        self.compliance.mark_remediation_required(ORG_A, finding.id, actor="controller")
        remediation = self.compliance.create_remediation(ORG_A, finding.id, action="Fix it", owner="dara", actor="controller")

        from asavexa.compliance.domain.errors import RemediationNotFoundError
        with self.assertRaises(RemediationNotFoundError):
            self.compliance.start_remediation(ORG_B, remediation.id, actor="intruder")
        with self.assertRaises(RemediationNotFoundError):
            self.compliance.complete_remediation(ORG_B, remediation.id, actor="intruder")

    def test_organisation_b_cannot_verify_organisation_a_remediation(self):
        finding = self._create_failing_finding()
        self.compliance.start_review(ORG_A, finding.id, actor="controller")
        self.compliance.mark_remediation_required(ORG_A, finding.id, actor="controller")
        remediation = self.compliance.create_remediation(ORG_A, finding.id, action="Fix it", owner="dara", actor="controller")
        self.compliance.start_remediation(ORG_A, remediation.id, actor="dara")
        self.compliance.complete_remediation(ORG_A, remediation.id, actor="dara")

        from asavexa.compliance.domain.errors import RemediationNotFoundError
        with self.assertRaises(RemediationNotFoundError):
            self.compliance.verify_remediation(ORG_B, remediation.id, actor="intruder")
        with self.assertRaises(RemediationNotFoundError):
            self.compliance.reject_remediation(ORG_B, remediation.id, actor="intruder", reason="n/a")

    def test_organisation_b_cannot_create_finding_against_organisation_a_execution(self):
        self._post(ORG_A, [LineInput(self.cash.id, debit_amount=Decimal("500.00")), LineInput(self.revenue.id, credit_amount=Decimal("500.00"))], date(2026, 1, 5), "Sale")
        recon = self.reconciliation.create_reconciliation(ORG_A, self.cash.id, "Jan", date(2026, 1, 1), date(2026, 1, 31), actor="dara")
        self.reconciliation.import_transactions(
            ORG_A, recon.id, [BankTransactionInput(date(2026, 1, 5), "Deposit", debit_amount=Decimal("500.00"))],
            actor="dara", import_source="csv",
        )
        control = next(c for c in self.compliance.seed_standard_controls(ORG_A, actor="setup") if c.code == "REC-001")
        execution = self.compliance.execute_control(ORG_A, control.id, actor="dara", period_id=self.period.id)

        from asavexa.compliance.domain.errors import ControlExecutionNotFoundError
        with self.assertRaises(ControlExecutionNotFoundError):
            self.compliance.create_finding_from_execution(ORG_B, execution.id, actor="intruder")

    def test_organisation_b_cannot_reopen_organisation_a_finding(self):
        finding = self._create_failing_finding()
        self.compliance.start_review(ORG_A, finding.id, actor="controller")
        self.compliance.mark_remediation_required(ORG_A, finding.id, actor="controller")
        remediation = self.compliance.create_remediation(ORG_A, finding.id, action="Fix it", owner="dara", actor="controller")
        self.compliance.start_remediation(ORG_A, remediation.id, actor="dara")
        self.compliance.complete_remediation(ORG_A, remediation.id, actor="dara")
        self.compliance.verify_remediation(ORG_A, remediation.id, actor="controller")
        self.compliance.close_finding(ORG_A, finding.id, actor="controller")

        from asavexa.compliance.domain.errors import FindingNotFoundError
        with self.assertRaises(FindingNotFoundError):
            self.compliance.reopen_finding(ORG_B, finding.id, actor="intruder", reason="trying to tamper")

    def test_audit_trail_is_append_only_by_interface(self):
        """The AuditRepository Protocol offers no update/delete method
        at all — this is a structural property of the shared audit
        module, not something Controls & Compliance adds. Verified here
        by confirming the interface Controls & Compliance depends on."""
        self.assertFalse(hasattr(self.audit, "update"))
        self.assertFalse(hasattr(self.audit, "delete"))


if __name__ == "__main__":
    unittest.main()
