"""
PeriodCloseService — the public service facade for Period Close &
Financial Controls.

"Don't just close the period. Prove that it was properly closed."

This module coordinates existing controls; it does not replace any of
them:

- Reads the Accounting Engine's periods and journals through its
  existing public interface (`accounting.periods`, `accounting.journals`)
  and calls its existing, UNCHANGED `lock_period()` to perform the one
  real act of enforcement — no new accounting method, no new
  AccountingPeriod field, no direct mutation of period status from
  here. See the module README's "Architecture" section.
- Reads Financial Reporting's `get_trial_balance()` for the balance
  control rather than recomputing debit/credit totals itself.
- Optionally reads Reconciliation's `list_reconciliations()` /
  `list_transactions()` for the reconciliation-exceptions control.
- Optionally reads Evidence Vault's `get_evidence()` for the
  required-evidence control.
- Writes only to the shared `asavexa/audit/` trail.
- Performs no permission checks itself — every method takes a plain
  `actor: str`, exactly like every other module's service layer.
  Maker-checker is enforced at the API boundary via the
  `period_close:request` / `period_close:review` / `period_close:approve`
  permissions, not here.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from ...accounting.domain.enums import JournalStatus
from ...accounting.services.engine import AccountingEngine
from ...audit.models import AuditEvent
from ...audit.repository import AuditRepository
from ...evidence.domain.enums import EvidenceStatus
from ...evidence.domain.errors import EvidenceNotFoundError
from ...evidence.services.vault import EvidenceVault
from ...reconciliation.domain.enums import BankTransactionStatus, ReconciliationStatus
from ...reconciliation.services.service import ReconciliationService
from ...reporting.services.service import ReportingService
from ..domain import rules
from ..domain.enums import AuditAction, ControlName, ControlStatus, PeriodCloseStatus
from ..domain.errors import (
    CloseAlreadyInProgressError,
    CloseNotReadyError,
    NotReviewedError,
    PeriodCloseProcessNotFoundError,
    PeriodNotFoundError,
)
from ..domain.models import CloseReadinessReport, ControlFinding, PeriodCloseProcess
from ..repository.interfaces import PeriodCloseRepository


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PeriodCloseService:
    def __init__(
        self,
        accounting: AccountingEngine,
        reporting: ReportingService,
        close_processes: PeriodCloseRepository,
        audit: AuditRepository,
        reconciliation: Optional[ReconciliationService] = None,
        evidence: Optional[EvidenceVault] = None,
    ):
        self.accounting = accounting
        self.reporting = reporting
        self.close_processes = close_processes
        self.audit = audit
        self.reconciliation = reconciliation
        self.evidence = evidence

    # ------------------------------------------------------------------
    # Close readiness — a pure, repeatable check. Never persisted.
    # ------------------------------------------------------------------
    def check_close_readiness(
        self, org_id: str, period_id: str, actor: str,
        required_evidence_refs: Optional[List[str]] = None,
    ) -> CloseReadinessReport:
        self._log(org_id, AuditAction.CLOSE_CHECK_STARTED, actor, "Period", period_id)

        period = self.accounting.periods.get(org_id, period_id)
        if period is None:
            raise PeriodNotFoundError(f"No accounting period {period_id} found for organisation {org_id}.")

        findings: List[ControlFinding] = [
            ControlFinding(
                control=ControlName.PERIOD_INTEGRITY, status=ControlStatus.PASSED, blocking=True,
                message=f"Period {period.name} exists and belongs to organisation {org_id}.",
            ),
            self._check_trial_balance(org_id, period_id, actor),
            self._check_unposted_journals(org_id, period_id),
            self._check_reconciliation(org_id, period),
            self._check_required_evidence(org_id, required_evidence_refs),
        ]

        blocking_failures = [f.control for f in findings if f.status == ControlStatus.FAILED and f.blocking]
        report = CloseReadinessReport(
            org_id=org_id, period_id=period_id, generated_at=_now(), generated_by=actor,
            findings=findings, is_ready=not blocking_failures, blocking_failures=blocking_failures,
        )
        self._log(
            org_id, AuditAction.CLOSE_CHECK_COMPLETED, actor, "Period", period_id,
            new_value={
                "is_ready": report.is_ready,
                "blocking_failures": [c.value for c in blocking_failures],
                "finding_count": len(findings),
            },
        )
        return report

    def _check_trial_balance(self, org_id: str, period_id: str, actor: str) -> ControlFinding:
        tb = self.reporting.get_trial_balance(org_id, period_id, actor=actor)
        if tb.is_balanced:
            return ControlFinding(
                control=ControlName.TRIAL_BALANCE_BALANCED, status=ControlStatus.PASSED, blocking=True,
                message=f"Trial balance is balanced: total debits {tb.total_debits} = total credits {tb.total_credits}.",
                reference={"total_debits": str(tb.total_debits), "total_credits": str(tb.total_credits)},
            )
        return ControlFinding(
            control=ControlName.TRIAL_BALANCE_BALANCED, status=ControlStatus.FAILED, blocking=True,
            message=(
                f"Trial balance is NOT balanced: total debits {tb.total_debits} != "
                f"total credits {tb.total_credits}. This is exposed exactly as computed — "
                f"never forced to balance."
            ),
            reference={"total_debits": str(tb.total_debits), "total_credits": str(tb.total_credits)},
        )

    def _check_unposted_journals(self, org_id: str, period_id: str) -> ControlFinding:
        drafts = self.accounting.journals.list_for_org(
            org_id, period_id=period_id, status=JournalStatus.DRAFT.value
        )
        if not drafts:
            return ControlFinding(
                control=ControlName.UNPOSTED_JOURNALS, status=ControlStatus.PASSED, blocking=True,
                message="No draft (unposted) journals remain in this period.",
            )
        return ControlFinding(
            control=ControlName.UNPOSTED_JOURNALS, status=ControlStatus.FAILED, blocking=True,
            message=f"{len(drafts)} draft journal(s) in this period must be posted or discarded before closing.",
            reference={"draft_journal_ids": [j.id for j in drafts], "count": len(drafts)},
        )

    def _check_reconciliation(self, org_id: str, period) -> ControlFinding:
        """
        Non-blocking by default (WARNING, not FAILED): the blueprint
        does not mandate 100% reconciliation before close, so this
        control surfaces outstanding items without inventing a hard
        requirement that was never specified. See README "Close
        controls" for the exact reasoning and how to make this
        blocking if a future policy requires it.

        Reconciliation batches have no period_id linking them to an
        AccountingPeriod (see reconciliation/README.md) — relevance is
        determined by date-range overlap between the batch's
        period_start/period_end and this AccountingPeriod's
        start_date/end_date, which is stated here explicitly rather
        than silently assumed.
        """
        if self.reconciliation is None:
            return ControlFinding(
                control=ControlName.RECONCILIATION_EXCEPTIONS, status=ControlStatus.NOT_APPLICABLE,
                blocking=False, message="Reconciliation integration not configured for this close service.",
            )

        relevant = [
            r for r in self.reconciliation.list_reconciliations(org_id)
            if not (r.period_end < period.start_date or r.period_start > period.end_date)
        ]
        outstanding_ids: List[str] = []
        unfinalized_reconciliation_ids: List[str] = []
        for recon in relevant:
            if recon.status != ReconciliationStatus.RECONCILED:
                unfinalized_reconciliation_ids.append(recon.id)
            for txn in self.reconciliation.list_transactions(org_id, recon.id):
                if txn.status not in (BankTransactionStatus.RECONCILED,):
                    outstanding_ids.append(txn.id)

        if not outstanding_ids and not unfinalized_reconciliation_ids:
            return ControlFinding(
                control=ControlName.RECONCILIATION_EXCEPTIONS, status=ControlStatus.PASSED, blocking=False,
                message="All reconciliation activity overlapping this period is fully reconciled.",
                reference={"reconciliations_checked": [r.id for r in relevant]},
            )
        return ControlFinding(
            control=ControlName.RECONCILIATION_EXCEPTIONS, status=ControlStatus.WARNING, blocking=False,
            message=(
                f"{len(outstanding_ids)} outstanding bank transaction(s) and "
                f"{len(unfinalized_reconciliation_ids)} unfinalized reconciliation(s) overlap this "
                f"period. Not blocking by default — see README."
            ),
            reference={
                "outstanding_transaction_ids": outstanding_ids,
                "unfinalized_reconciliation_ids": unfinalized_reconciliation_ids,
            },
        )

    def _check_required_evidence(
        self, org_id: str, required_evidence_refs: Optional[List[str]]
    ) -> ControlFinding:
        """
        Only evaluates evidence the CALLER explicitly designated as
        required for this specific close — this module invents no
        universal "evidence is always required to close" policy, since
        none is defined in the blueprint. A rejected or unverified
        reference fails outright; existence alone is never treated as
        proof (Blueprint Rule 2 / this control's own purpose).
        """
        if not required_evidence_refs:
            return ControlFinding(
                control=ControlName.REQUIRED_EVIDENCE, status=ControlStatus.NOT_APPLICABLE, blocking=False,
                message="No evidence was designated as required for this close.",
            )
        if self.evidence is None:
            return ControlFinding(
                control=ControlName.REQUIRED_EVIDENCE, status=ControlStatus.FAILED, blocking=True,
                message="Evidence was required for this close, but Evidence Vault integration is not configured.",
                reference={"required_evidence_refs": required_evidence_refs},
            )

        problems: dict[str, str] = {}
        for evidence_id in required_evidence_refs:
            try:
                record = self.evidence.get_evidence(org_id, evidence_id)
            except EvidenceNotFoundError:
                problems[evidence_id] = "not found"
                continue
            if record.status == EvidenceStatus.REJECTED:
                problems[evidence_id] = "rejected"
            elif record.status != EvidenceStatus.VERIFIED:
                problems[evidence_id] = f"not verified (status: {record.status.value})"

        if not problems:
            return ControlFinding(
                control=ControlName.REQUIRED_EVIDENCE, status=ControlStatus.PASSED, blocking=True,
                message=f"All {len(required_evidence_refs)} required evidence reference(s) are verified.",
                reference={"required_evidence_refs": required_evidence_refs},
            )
        return ControlFinding(
            control=ControlName.REQUIRED_EVIDENCE, status=ControlStatus.FAILED, blocking=True,
            message=f"{len(problems)} of {len(required_evidence_refs)} required evidence reference(s) failed: {problems}.",
            reference={"problems": problems},
        )

    # ------------------------------------------------------------------
    # Workflow: request -> (recheck) -> review -> approve|reject
    # ------------------------------------------------------------------
    def request_close(
        self, org_id: str, period_id: str, actor: str,
        required_evidence_refs: Optional[List[str]] = None,
    ) -> PeriodCloseProcess:
        existing = self.close_processes.get_active_for_period(org_id, period_id)
        if existing is not None:
            raise CloseAlreadyInProgressError(
                f"Period {period_id} already has an active close process ({existing.id}, "
                f"status {existing.status.value}). Resolve it before requesting another."
            )

        process = PeriodCloseProcess(
            id=_new_id(), org_id=org_id, period_id=period_id, status=PeriodCloseStatus.REQUESTED,
            requested_by=actor, requested_at=_now(),
        )
        self.close_processes.create(process)
        self._log(org_id, AuditAction.CLOSE_REQUESTED, actor, "PeriodCloseProcess", process.id,
                   new_value={"period_id": period_id})

        return self._evaluate_and_transition(process, actor, required_evidence_refs)

    def recheck_controls(
        self, org_id: str, process_id: str, actor: str,
        required_evidence_refs: Optional[List[str]] = None,
    ) -> PeriodCloseProcess:
        process = self._get_process(org_id, process_id)
        if process.status not in (
            PeriodCloseStatus.REQUESTED, PeriodCloseStatus.CONTROLS_FAILED, PeriodCloseStatus.READY_FOR_CLOSE,
        ):
            raise CloseNotReadyError(
                f"Cannot re-run controls on a close process that is {process.status.value}."
            )
        return self._evaluate_and_transition(process, actor, required_evidence_refs)

    def _evaluate_and_transition(
        self, process: PeriodCloseProcess, actor: str, required_evidence_refs: Optional[List[str]],
    ) -> PeriodCloseProcess:
        report = self.check_close_readiness(process.org_id, process.period_id, actor, required_evidence_refs)
        new_status = PeriodCloseStatus.READY_FOR_CLOSE if report.is_ready else PeriodCloseStatus.CONTROLS_FAILED
        rules.assert_transition_allowed(process.status, new_status)

        process.status = new_status
        process.last_findings = [
            {
                "control": f.control.value, "status": f.status.value, "blocking": f.blocking,
                "message": f.message, "reference": f.reference,
            }
            for f in report.findings
        ]
        self.close_processes.update(process)

        if new_status == PeriodCloseStatus.CONTROLS_FAILED:
            self._log(
                process.org_id, AuditAction.CLOSE_CONTROL_FAILED, actor, "PeriodCloseProcess", process.id,
                new_value={"blocking_failures": [c.value for c in report.blocking_failures]},
            )
        return process

    def review_close(self, org_id: str, process_id: str, actor: str) -> PeriodCloseProcess:
        process = self._get_process(org_id, process_id)
        if process.status != PeriodCloseStatus.READY_FOR_CLOSE:
            raise CloseNotReadyError(
                f"Close process {process_id} is {process.status.value}, not READY_FOR_CLOSE — "
                f"nothing to review yet."
            )
        process.reviewed_by = actor
        process.reviewed_at = _now()
        self.close_processes.update(process)
        self._log(org_id, AuditAction.CLOSE_REVIEWED, actor, "PeriodCloseProcess", process.id)
        return process

    def approve_close(self, org_id: str, process_id: str, actor: str, reason: Optional[str] = None) -> PeriodCloseProcess:
        """
        The one method that actually changes the Accounting Engine's
        state — and even here, only by calling its existing,
        unmodified `lock_period()`. Requires the process to have been
        reviewed first; review and approval are separate, both-required
        steps (they may be performed by the same or different actors,
        subject to whatever roles the caller's Identity permissions
        grant — this module does not itself enforce "different person").

        Re-verifies close readiness immediately before locking, rather
        than trusting the READY_FOR_CLOSE status set by an earlier
        request_close/recheck_controls call. Found during the
        cross-module integrity audit: accounting/reconciliation/evidence
        state can change in the window between that earlier check and
        this approval (e.g. a new draft journal appears) — approving
        against a stale snapshot would let a period lock over a control
        that no longer actually passes. If re-verification fails, the
        process moves to CONTROLS_FAILED (never straight to CLOSED, and
        never silently) and this call raises rather than proceeding.
        """
        process = self._get_process(org_id, process_id)
        if process.status != PeriodCloseStatus.READY_FOR_CLOSE:
            raise CloseNotReadyError(
                f"Close process {process_id} is {process.status.value}, not READY_FOR_CLOSE."
            )
        if process.reviewed_by is None:
            raise NotReviewedError(f"Close process {process_id} has not been reviewed yet.")

        report = self.check_close_readiness(org_id, process.period_id, actor)
        if not report.is_ready:
            rules.assert_transition_allowed(process.status, PeriodCloseStatus.CONTROLS_FAILED)
            process.status = PeriodCloseStatus.CONTROLS_FAILED
            process.last_findings = [
                {
                    "control": f.control.value, "status": f.status.value, "blocking": f.blocking,
                    "message": f.message, "reference": f.reference,
                }
                for f in report.findings
            ]
            self.close_processes.update(process)
            self._log(
                org_id, AuditAction.CLOSE_CONTROL_FAILED, actor, "PeriodCloseProcess", process.id,
                new_value={"blocking_failures": [c.value for c in report.blocking_failures]},
                reason="Readiness re-verification at approval time found controls that had since regressed.",
            )
            raise CloseNotReadyError(
                f"Close process {process_id} failed re-verification at approval time — "
                f"controls that previously passed no longer do: "
                f"{[c.value for c in report.blocking_failures]}. The process has been moved to "
                f"CONTROLS_FAILED; re-run recheck_controls after resolving the issue."
            )

        rules.assert_transition_allowed(process.status, PeriodCloseStatus.CLOSED)
        process.status = PeriodCloseStatus.CLOSED
        process.approved_by = actor
        process.approved_at = _now()
        self.close_processes.update(process)

        self._log(org_id, AuditAction.CLOSE_APPROVED, actor, "PeriodCloseProcess", process.id)
        self._log(org_id, AuditAction.PERIOD_CLOSED, actor, "Period", process.period_id,
                   related_record_id=process.id)

        # The one real act of enforcement — reuses the Accounting
        # Engine's own, unmodified lock mechanism. This call logs its
        # own PERIOD_LOCKED audit event under accounting's AuditAction;
        # not duplicated here (see domain/enums.py).
        self.accounting.lock_period(
            org_id, process.period_id, actor=actor,
            reason=reason or f"Period close process {process.id} approved.",
        )
        return process

    def reject_close(self, org_id: str, process_id: str, actor: str, reason: str) -> PeriodCloseProcess:
        process = self._get_process(org_id, process_id)
        rules.assert_transition_allowed(process.status, PeriodCloseStatus.REJECTED)
        process.status = PeriodCloseStatus.REJECTED
        process.rejected_by = actor
        process.rejected_at = _now()
        process.rejection_reason = reason
        self.close_processes.update(process)
        self._log(org_id, AuditAction.CLOSE_REJECTED, actor, "PeriodCloseProcess", process.id, reason=reason)
        return process

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    def _get_process(self, org_id: str, process_id: str) -> PeriodCloseProcess:
        process = self.close_processes.get(org_id, process_id)
        if process is None:
            raise PeriodCloseProcessNotFoundError(f"Period close process {process_id} not found.")
        return process

    def get_process(self, org_id: str, process_id: str) -> PeriodCloseProcess:
        return self._get_process(org_id, process_id)

    def get_active_process(self, org_id: str, period_id: str) -> Optional[PeriodCloseProcess]:
        return self.close_processes.get_active_for_period(org_id, period_id)

    def list_processes(self, org_id: str, period_id: str) -> List[PeriodCloseProcess]:
        return self.close_processes.list_for_period(org_id, period_id)

    # ------------------------------------------------------------------
    def _log(
        self, org_id: str, action: AuditAction, actor: str, entity_type: str, entity_id: str,
        new_value: Optional[dict] = None, reason: Optional[str] = None,
        related_record_id: Optional[str] = None,
    ) -> None:
        self.audit.record(
            AuditEvent(
                id=_new_id(), org_id=org_id, entity_type=entity_type, entity_id=entity_id,
                action=action.value, actor=actor, timestamp=_now(),
                new_value=new_value, reason=reason, related_record_id=related_record_id,
            )
        )
