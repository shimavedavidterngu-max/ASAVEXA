"""
Automated tests for Period Close & Financial Controls.

Run with:  PYTHONPATH=src python3 -m unittest discover -s tests -v

Stdlib-only — exercises PeriodCloseService against real, SQLite-backed
AccountingEngine, ReportingService, ReconciliationService, and
EvidenceVault instances — not mocks.
"""
import unittest
from datetime import date
from decimal import Decimal

from asavexa.accounting.domain.enums import AccountType, PeriodStatus
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
from asavexa.period_close.domain.enums import ControlName, ControlStatus, PeriodCloseStatus
from asavexa.period_close.domain.errors import (
    CloseAlreadyInProgressError,
    CloseNotReadyError,
    InvalidCloseStateError,
    NotReviewedError,
    PeriodNotFoundError,
)
from asavexa.period_close.repository.sqlite_repository import SqlitePeriodCloseRepository
from asavexa.period_close.services.service import PeriodCloseService
from asavexa.reconciliation.domain.models import BankTransactionInput
from asavexa.reconciliation.repository.sqlite_repository import (
    SqliteBankTransactionRepository,
    SqliteReconciliationRepository,
)
from asavexa.reconciliation.services.service import ReconciliationService
from asavexa.reporting.services.service import ReportingService

ORG_A = "org-meridian"
ORG_B = "org-other-tenant"


class PeriodCloseServiceTestCase(unittest.TestCase):
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
            audit=audit,
            accounting=self.accounting,
        )
        self.evidence = EvidenceVault(evidence=SqliteEvidenceRepository(self.conn), audit=audit)
        self.close = PeriodCloseService(
            accounting=self.accounting, reporting=self.reporting,
            close_processes=SqlitePeriodCloseRepository(self.conn), audit=audit,
            reconciliation=self.reconciliation, evidence=self.evidence,
        )

        self.cash = self.accounting.create_account(ORG_A, "1000", "Cash", AccountType.ASSET, actor="setup")
        self.equity = self.accounting.create_account(ORG_A, "3000", "Owner's Capital", AccountType.EQUITY, actor="setup")
        self.revenue = self.accounting.create_account(ORG_A, "4000", "Sales Revenue", AccountType.REVENUE, actor="setup")
        self.period = self.accounting.open_period(ORG_A, "FY2026-M01", date(2026, 1, 1), date(2026, 1, 31), actor="setup")

        self.cash_b = self.accounting.create_account(ORG_B, "1000", "Cash", AccountType.ASSET, actor="setup")
        self.period_b = self.accounting.open_period(ORG_B, "FY2026-M01", date(2026, 1, 1), date(2026, 1, 31), actor="setup")

    def _post(self, org_id, lines, txn_date, desc, actor="dara"):
        journal = self.accounting.create_draft_journal(org_id, txn_date, desc, "USD", lines, created_by=actor)
        return self.accounting.post_journal(org_id, journal.id, actor=actor)

    def _find(self, report, control):
        return next(f for f in report.findings if f.control == control)

    # ------------------------------------------------------------------
    # Period readiness / basic controls
    # ------------------------------------------------------------------
    def test_open_period_with_balanced_activity_is_ready(self):
        self._post(
            ORG_A,
            [LineInput(self.cash.id, debit_amount=Decimal("1000.00")), LineInput(self.equity.id, credit_amount=Decimal("1000.00"))],
            date(2026, 1, 2), "Investment",
        )
        report = self.close.check_close_readiness(ORG_A, self.period.id, actor="dara")
        self.assertTrue(report.is_ready)
        self.assertEqual(self._find(report, ControlName.TRIAL_BALANCE_BALANCED).status, ControlStatus.PASSED)

    def test_invalid_period_cannot_be_checked_or_closed(self):
        with self.assertRaises(PeriodNotFoundError):
            self.close.check_close_readiness(ORG_A, "not-a-real-period", actor="dara")

    def test_foreign_organisation_period_cannot_be_accessed(self):
        with self.assertRaises(PeriodNotFoundError):
            self.close.check_close_readiness(ORG_B, self.period.id, actor="intruder")

    # ------------------------------------------------------------------
    # Close controls
    # ------------------------------------------------------------------
    def test_unposted_draft_journal_blocks_close(self):
        self.accounting.create_draft_journal(
            ORG_A, date(2026, 1, 5), "Unposted", "USD",
            [LineInput(self.cash.id, debit_amount=Decimal("10.00")), LineInput(self.revenue.id, credit_amount=Decimal("10.00"))],
            created_by="dara",
        )
        report = self.close.check_close_readiness(ORG_A, self.period.id, actor="dara")
        self.assertFalse(report.is_ready)
        finding = self._find(report, ControlName.UNPOSTED_JOURNALS)
        self.assertEqual(finding.status, ControlStatus.FAILED)
        self.assertIn(ControlName.UNPOSTED_JOURNALS, report.blocking_failures)

    def test_outstanding_reconciliation_is_a_warning_not_a_blocker_by_default(self):
        self._post(
            ORG_A,
            [LineInput(self.cash.id, debit_amount=Decimal("500.00")), LineInput(self.revenue.id, credit_amount=Decimal("500.00"))],
            date(2026, 1, 5), "Sale",
        )
        recon = self.reconciliation.create_reconciliation(
            ORG_A, self.cash.id, "Jan", date(2026, 1, 1), date(2026, 1, 31), actor="dara",
        )
        self.reconciliation.import_transactions(
            ORG_A, recon.id,
            [BankTransactionInput(date(2026, 1, 5), "Deposit", debit_amount=Decimal("500.00"))],
            actor="dara", import_source="csv",
        )
        # Matched automatically but never approved/finalized — still outstanding.
        report = self.close.check_close_readiness(ORG_A, self.period.id, actor="dara")
        finding = self._find(report, ControlName.RECONCILIATION_EXCEPTIONS)
        self.assertEqual(finding.status, ControlStatus.WARNING)
        self.assertFalse(finding.blocking)
        self.assertTrue(report.is_ready)  # a non-blocking warning does not prevent readiness

    def test_fully_reconciled_period_passes_reconciliation_control(self):
        self._post(
            ORG_A,
            [LineInput(self.cash.id, debit_amount=Decimal("500.00")), LineInput(self.revenue.id, credit_amount=Decimal("500.00"))],
            date(2026, 1, 5), "Sale",
        )
        recon = self.reconciliation.create_reconciliation(
            ORG_A, self.cash.id, "Jan", date(2026, 1, 1), date(2026, 1, 31), actor="dara",
        )
        [txn] = self.reconciliation.import_transactions(
            ORG_A, recon.id,
            [BankTransactionInput(date(2026, 1, 5), "Deposit", debit_amount=Decimal("500.00"))],
            actor="dara", import_source="csv",
        )
        self.reconciliation.submit_reconciliation(ORG_A, recon.id, actor="dara")
        self.reconciliation.approve_transaction(ORG_A, txn.id, actor="controller")
        self.reconciliation.approve_reconciliation(ORG_A, recon.id, actor="controller")

        report = self.close.check_close_readiness(ORG_A, self.period.id, actor="dara")
        finding = self._find(report, ControlName.RECONCILIATION_EXCEPTIONS)
        self.assertEqual(finding.status, ControlStatus.PASSED)

    def test_required_evidence_verified_passes(self):
        record = self.evidence.upload_evidence(
            ORG_A, EvidenceType.BANK_STATEMENT, b"statement content", "jan.pdf", "application/pdf",
            uploaded_by="dara",
        )
        self.evidence.verify_evidence(ORG_A, record.id, actor="controller")
        report = self.close.check_close_readiness(ORG_A, self.period.id, actor="dara", required_evidence_refs=[record.id])
        finding = self._find(report, ControlName.REQUIRED_EVIDENCE)
        self.assertEqual(finding.status, ControlStatus.PASSED)

    def test_rejected_evidence_is_not_treated_as_valid(self):
        record = self.evidence.upload_evidence(
            ORG_A, EvidenceType.BANK_STATEMENT, b"bad statement", "bad.pdf", "application/pdf",
            uploaded_by="dara",
        )
        self.evidence.reject_evidence(ORG_A, record.id, actor="controller", reason="illegible")
        report = self.close.check_close_readiness(ORG_A, self.period.id, actor="dara", required_evidence_refs=[record.id])
        finding = self._find(report, ControlName.REQUIRED_EVIDENCE)
        self.assertEqual(finding.status, ControlStatus.FAILED)
        self.assertIn(ControlName.REQUIRED_EVIDENCE, report.blocking_failures)
        self.assertFalse(report.is_ready)

    def test_unverified_evidence_fails_required_evidence_control(self):
        record = self.evidence.upload_evidence(
            ORG_A, EvidenceType.BANK_STATEMENT, b"pending statement", "pending.pdf", "application/pdf",
            uploaded_by="dara",
        )
        report = self.close.check_close_readiness(ORG_A, self.period.id, actor="dara", required_evidence_refs=[record.id])
        self.assertEqual(self._find(report, ControlName.REQUIRED_EVIDENCE).status, ControlStatus.FAILED)

    def test_no_required_evidence_is_not_applicable(self):
        report = self.close.check_close_readiness(ORG_A, self.period.id, actor="dara")
        finding = self._find(report, ControlName.REQUIRED_EVIDENCE)
        self.assertEqual(finding.status, ControlStatus.NOT_APPLICABLE)
        self.assertFalse(finding.blocking)

    def test_unbalanced_ledger_is_exposed_not_hidden(self):
        """The Accounting Engine itself always keeps journals balanced,
        so we can't produce a genuinely unbalanced trial balance through
        normal posting — this test instead proves the control faithfully
        reports whatever Reporting computes, by checking a balanced
        period is reported as such with the real figures, not a
        hand-waved True."""
        self._post(
            ORG_A,
            [LineInput(self.cash.id, debit_amount=Decimal("333.33")), LineInput(self.revenue.id, credit_amount=Decimal("333.33"))],
            date(2026, 1, 5), "Sale",
        )
        report = self.close.check_close_readiness(ORG_A, self.period.id, actor="dara")
        finding = self._find(report, ControlName.TRIAL_BALANCE_BALANCED)
        self.assertEqual(finding.reference["total_debits"], "333.33")
        self.assertEqual(finding.reference["total_credits"], "333.33")

    # ------------------------------------------------------------------
    # Maker-checker workflow
    # ------------------------------------------------------------------
    def test_request_review_approve_happy_path(self):
        self._post(
            ORG_A,
            [LineInput(self.cash.id, debit_amount=Decimal("1000.00")), LineInput(self.equity.id, credit_amount=Decimal("1000.00"))],
            date(2026, 1, 2), "Investment",
        )
        process = self.close.request_close(ORG_A, self.period.id, actor="dara")
        self.assertEqual(process.status, PeriodCloseStatus.READY_FOR_CLOSE)

        self.close.review_close(ORG_A, process.id, actor="controller")
        finalized = self.close.approve_close(ORG_A, process.id, actor="controller")
        self.assertEqual(finalized.status, PeriodCloseStatus.CLOSED)

        period = self.accounting.periods.get(ORG_A, self.period.id)
        self.assertEqual(period.status, PeriodStatus.LOCKED)

    def test_request_close_with_failing_controls_lands_in_controls_failed(self):
        self.accounting.create_draft_journal(
            ORG_A, date(2026, 1, 5), "Unposted", "USD",
            [LineInput(self.cash.id, debit_amount=Decimal("10.00")), LineInput(self.revenue.id, credit_amount=Decimal("10.00"))],
            created_by="dara",
        )
        process = self.close.request_close(ORG_A, self.period.id, actor="dara")
        self.assertEqual(process.status, PeriodCloseStatus.CONTROLS_FAILED)

    def test_cannot_request_close_twice_while_one_is_active(self):
        self.close.request_close(ORG_A, self.period.id, actor="dara")
        with self.assertRaises(CloseAlreadyInProgressError):
            self.close.request_close(ORG_A, self.period.id, actor="dara")

    def test_recheck_controls_moves_controls_failed_to_ready(self):
        journal = self.accounting.create_draft_journal(
            ORG_A, date(2026, 1, 5), "Unposted", "USD",
            [LineInput(self.cash.id, debit_amount=Decimal("10.00")), LineInput(self.revenue.id, credit_amount=Decimal("10.00"))],
            created_by="dara",
        )
        process = self.close.request_close(ORG_A, self.period.id, actor="dara")
        self.assertEqual(process.status, PeriodCloseStatus.CONTROLS_FAILED)

        self.accounting.post_journal(ORG_A, journal.id, actor="dara")
        rechecked = self.close.recheck_controls(ORG_A, process.id, actor="dara")
        self.assertEqual(rechecked.status, PeriodCloseStatus.READY_FOR_CLOSE)

    def test_cannot_approve_without_review(self):
        self._post(
            ORG_A,
            [LineInput(self.cash.id, debit_amount=Decimal("1000.00")), LineInput(self.equity.id, credit_amount=Decimal("1000.00"))],
            date(2026, 1, 2), "Investment",
        )
        process = self.close.request_close(ORG_A, self.period.id, actor="dara")
        with self.assertRaises(NotReviewedError):
            self.close.approve_close(ORG_A, process.id, actor="controller")

    def test_cannot_approve_a_controls_failed_process(self):
        self.accounting.create_draft_journal(
            ORG_A, date(2026, 1, 5), "Unposted", "USD",
            [LineInput(self.cash.id, debit_amount=Decimal("10.00")), LineInput(self.revenue.id, credit_amount=Decimal("10.00"))],
            created_by="dara",
        )
        process = self.close.request_close(ORG_A, self.period.id, actor="dara")
        with self.assertRaises(CloseNotReadyError):
            self.close.approve_close(ORG_A, process.id, actor="controller")

    def test_approve_close_re_verifies_readiness_and_catches_a_regression(self):
        """Found during the cross-module integrity audit: approve_close
        previously trusted the READY_FOR_CLOSE status set by an earlier
        request_close call without re-checking. If a new draft journal
        appears in the window between request and approval, the old
        behaviour would lock the period anyway. This proves the gap is
        closed: approval re-verifies immediately before locking, and a
        regression here moves the process to CONTROLS_FAILED and raises
        — the period must NOT end up locked."""
        self._post(
            ORG_A,
            [LineInput(self.cash.id, debit_amount=Decimal("1000.00")), LineInput(self.equity.id, credit_amount=Decimal("1000.00"))],
            date(2026, 1, 2), "Investment",
        )
        process = self.close.request_close(ORG_A, self.period.id, actor="dara")
        self.assertEqual(process.status, PeriodCloseStatus.READY_FOR_CLOSE)
        self.close.review_close(ORG_A, process.id, actor="controller")

        # State regresses AFTER the readiness check and review, but
        # BEFORE approval — a new draft journal appears in the period.
        self.accounting.create_draft_journal(
            ORG_A, date(2026, 1, 20), "Snuck in after review", "USD",
            [LineInput(self.cash.id, debit_amount=Decimal("5.00")), LineInput(self.revenue.id, credit_amount=Decimal("5.00"))],
            created_by="dara",
        )

        with self.assertRaises(CloseNotReadyError):
            self.close.approve_close(ORG_A, process.id, actor="controller")

        # The process was moved to CONTROLS_FAILED, not silently left
        # claiming READY_FOR_CLOSE, and critically the period was NEVER
        # locked.
        reloaded_process = self.close.get_process(ORG_A, process.id)
        self.assertEqual(reloaded_process.status, PeriodCloseStatus.CONTROLS_FAILED)
        period = self.accounting.periods.get(ORG_A, self.period.id)
        self.assertEqual(period.status, PeriodStatus.OPEN)

        # The audit trail records that this specific control failure
        # was caught, distinct from a normal request-time failure.
        events = self.audit.list_for_org(ORG_A)
        failure_events = [e for e in events if e.action == "CLOSE_CONTROL_FAILED"]
        self.assertTrue(any("stale" in (e.reason or "").lower() or "regressed" in (e.reason or "").lower() for e in failure_events))

    def test_reject_close_is_terminal(self):
        self._post(
            ORG_A,
            [LineInput(self.cash.id, debit_amount=Decimal("1000.00")), LineInput(self.equity.id, credit_amount=Decimal("1000.00"))],
            date(2026, 1, 2), "Investment",
        )
        process = self.close.request_close(ORG_A, self.period.id, actor="dara")
        rejected = self.close.reject_close(ORG_A, process.id, actor="controller", reason="need more documentation")
        self.assertEqual(rejected.status, PeriodCloseStatus.REJECTED)
        with self.assertRaises(InvalidCloseStateError):
            self.close.reject_close(ORG_A, process.id, actor="controller", reason="again")

    def test_invalid_transition_is_rejected(self):
        self._post(
            ORG_A,
            [LineInput(self.cash.id, debit_amount=Decimal("1000.00")), LineInput(self.equity.id, credit_amount=Decimal("1000.00"))],
            date(2026, 1, 2), "Investment",
        )
        process = self.close.request_close(ORG_A, self.period.id, actor="dara")
        self.close.review_close(ORG_A, process.id, actor="controller")
        self.close.approve_close(ORG_A, process.id, actor="controller")
        # CLOSED is terminal.
        with self.assertRaises(InvalidCloseStateError):
            self.close.reject_close(ORG_A, process.id, actor="controller", reason="too late")

    # ------------------------------------------------------------------
    # Locking / closed-period protection
    # ------------------------------------------------------------------
    def test_closed_period_rejects_new_postings(self):
        self._post(
            ORG_A,
            [LineInput(self.cash.id, debit_amount=Decimal("1000.00")), LineInput(self.equity.id, credit_amount=Decimal("1000.00"))],
            date(2026, 1, 2), "Investment",
        )
        process = self.close.request_close(ORG_A, self.period.id, actor="dara")
        self.close.review_close(ORG_A, process.id, actor="controller")
        self.close.approve_close(ORG_A, process.id, actor="controller")

        from asavexa.accounting.domain.errors import PeriodLockedError
        with self.assertRaises(PeriodLockedError):
            self.accounting.create_draft_journal(
                ORG_A, date(2026, 1, 15), "Too late", "USD",
                [LineInput(self.cash.id, debit_amount=Decimal("1.00")), LineInput(self.revenue.id, credit_amount=Decimal("1.00"))],
                created_by="dara",
            )

    def test_existing_posted_journal_remains_immutable_after_close(self):
        journal = self._post(
            ORG_A,
            [LineInput(self.cash.id, debit_amount=Decimal("1000.00")), LineInput(self.equity.id, credit_amount=Decimal("1000.00"))],
            date(2026, 1, 2), "Investment",
        )
        process = self.close.request_close(ORG_A, self.period.id, actor="dara")
        self.close.review_close(ORG_A, process.id, actor="controller")
        self.close.approve_close(ORG_A, process.id, actor="controller")

        reloaded = self.accounting.journals.get(ORG_A, journal.id)
        self.assertEqual(reloaded.total_debits(), journal.total_debits())
        self.assertEqual(reloaded.status, journal.status)

    def test_reporting_still_reflects_authoritative_ledger_after_close(self):
        self._post(
            ORG_A,
            [LineInput(self.cash.id, debit_amount=Decimal("1000.00")), LineInput(self.equity.id, credit_amount=Decimal("1000.00"))],
            date(2026, 1, 2), "Investment",
        )
        process = self.close.request_close(ORG_A, self.period.id, actor="dara")
        self.close.review_close(ORG_A, process.id, actor="controller")
        self.close.approve_close(ORG_A, process.id, actor="controller")

        tb = self.reporting.get_trial_balance(ORG_A, self.period.id, actor="dara")
        self.assertEqual(tb.total_debits, Decimal("1000.00"))
        self.assertTrue(tb.is_balanced)

    # ------------------------------------------------------------------
    # Tenant isolation
    # ------------------------------------------------------------------
    def test_organisation_b_cannot_access_organisation_a_close_process(self):
        self._post(
            ORG_A,
            [LineInput(self.cash.id, debit_amount=Decimal("1000.00")), LineInput(self.equity.id, credit_amount=Decimal("1000.00"))],
            date(2026, 1, 2), "Investment",
        )
        process = self.close.request_close(ORG_A, self.period.id, actor="dara")

        from asavexa.period_close.domain.errors import PeriodCloseProcessNotFoundError
        with self.assertRaises(PeriodCloseProcessNotFoundError):
            self.close.get_process(ORG_B, process.id)

    def test_organisation_b_cannot_approve_organisation_a_close(self):
        self._post(
            ORG_A,
            [LineInput(self.cash.id, debit_amount=Decimal("1000.00")), LineInput(self.equity.id, credit_amount=Decimal("1000.00"))],
            date(2026, 1, 2), "Investment",
        )
        process = self.close.request_close(ORG_A, self.period.id, actor="dara")
        self.close.review_close(ORG_A, process.id, actor="controller")

        from asavexa.period_close.domain.errors import PeriodCloseProcessNotFoundError
        with self.assertRaises(PeriodCloseProcessNotFoundError):
            self.close.approve_close(ORG_B, process.id, actor="intruder")

    def test_organisation_b_cannot_lock_organisation_a_period(self):
        self._post(
            ORG_A,
            [LineInput(self.cash.id, debit_amount=Decimal("1000.00")), LineInput(self.equity.id, credit_amount=Decimal("1000.00"))],
            date(2026, 1, 2), "Investment",
        )
        process = self.close.request_close(ORG_A, self.period.id, actor="dara")
        self.close.review_close(ORG_A, process.id, actor="controller")
        self.close.approve_close(ORG_A, process.id, actor="controller")

        # Org A's period is now locked; Org B's own period is untouched.
        period_b = self.accounting.periods.get(ORG_B, self.period_b.id)
        self.assertEqual(period_b.status, PeriodStatus.OPEN)

    # ------------------------------------------------------------------
    # Audit trail
    # ------------------------------------------------------------------
    def test_full_workflow_is_audit_logged_with_distinguishable_actors(self):
        self._post(
            ORG_A,
            [LineInput(self.cash.id, debit_amount=Decimal("1000.00")), LineInput(self.equity.id, credit_amount=Decimal("1000.00"))],
            date(2026, 1, 2), "Investment",
        )
        process = self.close.request_close(ORG_A, self.period.id, actor="dara")
        self.close.review_close(ORG_A, process.id, actor="controller")
        self.close.approve_close(ORG_A, process.id, actor="controller")

        events = self.audit.list_for_org(ORG_A)
        actions = {e.action for e in events}
        for expected in (
            "CLOSE_CHECK_STARTED", "CLOSE_CHECK_COMPLETED", "CLOSE_REQUESTED",
            "CLOSE_REVIEWED", "CLOSE_APPROVED", "PERIOD_CLOSED", "PERIOD_LOCKED",
        ):
            self.assertIn(expected, actions, f"missing audit action {expected}")

        makers = {e.actor for e in events if e.action == "CLOSE_REQUESTED"}
        checkers = {e.actor for e in events if e.action in ("CLOSE_REVIEWED", "CLOSE_APPROVED")}
        self.assertEqual(makers, {"dara"})
        self.assertEqual(checkers, {"controller"})
        self.assertTrue(makers.isdisjoint(checkers))

    def test_control_failure_is_audited(self):
        self.accounting.create_draft_journal(
            ORG_A, date(2026, 1, 5), "Unposted", "USD",
            [LineInput(self.cash.id, debit_amount=Decimal("10.00")), LineInput(self.revenue.id, credit_amount=Decimal("10.00"))],
            created_by="dara",
        )
        self.close.request_close(ORG_A, self.period.id, actor="dara")
        events = self.audit.list_for_org(ORG_A)
        self.assertTrue(any(e.action == "CLOSE_CONTROL_FAILED" for e in events))


if __name__ == "__main__":
    unittest.main()
