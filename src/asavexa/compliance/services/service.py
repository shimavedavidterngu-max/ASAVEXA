"""
ComplianceService — the public service facade for Controls &
Compliance / Audit Workspace.

"Don't just claim compliance. Prove the control."

This module is an orchestration/assessment layer. It never recomputes
what an authoritative module already knows — every built-in check
calls into Accounting, Reporting, Reconciliation, or Evidence and
interprets their real answer. It makes no regulatory claims (no
"IFRS compliant", no "SOX compliant") — see the module README.

Performs no permission checks itself — every method takes a plain
`actor: str`, exactly like every other module's service layer.
Segregation of duties (a remediation owner cannot verify their own
work) is enforced at the API boundary via disjoint
`finding:remediate` / `finding:verify` permissions, never by comparing
actor strings here — the same architectural choice Reconciliation and
Period Close already made for their own maker-checker splits.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple

from ...accounting.domain.enums import JournalStatus
from ...accounting.services.engine import AccountingEngine
from ...audit.models import AuditEvent
from ...audit.repository import AuditRepository
from ...evidence.domain.enums import EvidenceStatus
from ...evidence.domain.errors import EvidenceNotFoundError
from ...evidence.services.vault import EvidenceVault, MISSING as EVIDENCE_MISSING
from ...reconciliation.domain.enums import BankTransactionStatus, ReconciliationStatus
from ...reconciliation.services.service import ReconciliationService
from ...reporting.services.service import ReportingService
from ...period_close.services.service import PeriodCloseService
from ..domain import rules
from ..domain.enums import (
    AuditAction,
    ControlDomain,
    ControlResult,
    ControlSeverity,
    FindingStatus,
    RemediationStatus,
)
from ..domain.errors import (
    CannotCreateFindingForResultError,
    ControlDefinitionNotFoundError,
    ControlExecutionNotFoundError,
    DuplicateControlCodeError,
    FindingAlreadyExistsError,
    FindingNotFoundError,
    InactiveControlError,
    RemediationNotFoundError,
    RemediationRequiredError,
    UnknownCheckKeyError,
)
from ..domain.models import ControlDefinition, ControlExecution, Finding, Remediation
from ..repository.interfaces import (
    ControlDefinitionRepository,
    ControlExecutionRepository,
    FindingRepository,
    RemediationRepository,
)

# ----------------------------------------------------------------------
# Built-in check keys — a fixed, named set, deliberately NOT a generic
# rule language. Each maps to exactly one private method below.
# ----------------------------------------------------------------------
CHECK_TRIAL_BALANCE_BALANCED = "ACCOUNTING_TRIAL_BALANCE_BALANCED"
CHECK_NO_UNPOSTED_JOURNALS = "ACCOUNTING_NO_UNPOSTED_JOURNALS"
CHECK_PERIOD_LOCK_STATUS = "ACCOUNTING_PERIOD_LOCK_STATUS"
CHECK_RECONCILIATION_NO_OUTSTANDING = "RECONCILIATION_NO_OUTSTANDING_TRANSACTIONS"
CHECK_EVIDENCE_REQUIRED_VALID = "EVIDENCE_REQUIRED_REFERENCES_VALID"
CHECK_EVIDENCE_NOT_MISSING_FOR_JOURNAL = "EVIDENCE_NOT_MISSING_FOR_JOURNAL"
CHECK_REPORTING_PROVENANCE_AVAILABLE = "REPORTING_TRIAL_BALANCE_PROVENANCE_AVAILABLE"
CHECK_PERIOD_CLOSE_READINESS = "PERIOD_CLOSE_READINESS_CHECK"
CHECK_PERIOD_CLOSE_PERIOD_LOCKED = "PERIOD_CLOSE_PERIOD_LOCKED"

# (code, name, description, objective, severity, domain, check_key) —
# the standard library seeded by seed_standard_controls(). An org may
# still define its own beyond these.
_STANDARD_CONTROLS: List[Tuple[str, str, str, str, ControlSeverity, ControlDomain, str]] = [
    ("ACC-001", "Trial balance is balanced",
     "Verifies AccountingEngine.get_trial_balance() reports total debits equal to total credits for the period.",
     "Detect ledger inconsistency before it reaches a financial statement.",
     ControlSeverity.CRITICAL, ControlDomain.ACCOUNTING, CHECK_TRIAL_BALANCE_BALANCED),
    ("ACC-002", "No unposted journals in period",
     "Verifies no DRAFT journals remain in the period.",
     "Ensure every transaction intended for the period is actually part of the authoritative ledger.",
     ControlSeverity.HIGH, ControlDomain.ACCOUNTING, CHECK_NO_UNPOSTED_JOURNALS),
    ("ACC-003", "Period lock status",
     "Reports whether the period is OPEN, LOCKED, or CLOSED.",
     "Informational visibility into period governance state.",
     ControlSeverity.LOW, ControlDomain.ACCOUNTING, CHECK_PERIOD_LOCK_STATUS),
    ("REC-001", "No outstanding reconciliation for period",
     "Verifies every BankTransaction in a Reconciliation overlapping the period is RECONCILED.",
     "Surface unresolved bank-to-ledger discrepancies.",
     ControlSeverity.MEDIUM, ControlDomain.RECONCILIATION, CHECK_RECONCILIATION_NO_OUTSTANDING),
    ("EVI-001", "Required evidence is verified",
     "Verifies every caller-designated evidence reference is VERIFIED in the Evidence Vault, not merely present.",
     "Prevent unverified or rejected evidence from being treated as proof.",
     ControlSeverity.HIGH, ControlDomain.EVIDENCE, CHECK_EVIDENCE_REQUIRED_VALID),
    ("EVI-002", "Evidence not missing for journal",
     "Verifies a named journal has a linked evidence record, using Evidence Vault's own MISSING sentinel.",
     "Catch transactions posted without supporting documentation.",
     ControlSeverity.MEDIUM, ControlDomain.EVIDENCE, CHECK_EVIDENCE_NOT_MISSING_FOR_JOURNAL),
    ("REP-001", "Trial balance provenance available",
     "Verifies every non-zero trial balance line traces back to at least one posted journal via Reporting.trace_line().",
     "Confirm reported figures are never opaque — every number can be traced to source.",
     ControlSeverity.HIGH, ControlDomain.REPORTING, CHECK_REPORTING_PROVENANCE_AVAILABLE),
    ("CLS-001", "Period close readiness",
     "Runs PeriodCloseService.check_close_readiness() and reports whether the period would currently pass.",
     "Preview close-blocking issues before a formal close request.",
     ControlSeverity.MEDIUM, ControlDomain.PERIOD_CLOSE, CHECK_PERIOD_CLOSE_READINESS),
    ("CLS-002", "Period is closed and locked",
     "Verifies the accounting period's status is LOCKED (or CLOSED).",
     "Confirm period-end governance was actually completed, not just requested.",
     ControlSeverity.HIGH, ControlDomain.PERIOD_CLOSE, CHECK_PERIOD_CLOSE_PERIOD_LOCKED),
]

TWO_PLACES_TOLERANCE = "0.01"


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ComplianceService:
    def __init__(
        self,
        definitions: ControlDefinitionRepository,
        executions: ControlExecutionRepository,
        findings: FindingRepository,
        remediations: RemediationRepository,
        audit: AuditRepository,
        accounting: AccountingEngine,
        reporting: ReportingService,
        reconciliation: Optional[ReconciliationService] = None,
        evidence: Optional[EvidenceVault] = None,
        period_close: Optional[PeriodCloseService] = None,
    ):
        self.definitions = definitions
        self.executions = executions
        self.findings = findings
        self.remediations = remediations
        self.audit = audit
        self.accounting = accounting
        self.reporting = reporting
        self.reconciliation = reconciliation
        self.evidence = evidence
        self.period_close = period_close

        self._check_registry: Dict[str, Callable[[str, Optional[str], dict, str], Tuple[ControlResult, str, dict]]] = {
            CHECK_TRIAL_BALANCE_BALANCED: self._check_trial_balance_balanced,
            CHECK_NO_UNPOSTED_JOURNALS: self._check_no_unposted_journals,
            CHECK_PERIOD_LOCK_STATUS: self._check_period_lock_status,
            CHECK_RECONCILIATION_NO_OUTSTANDING: self._check_reconciliation_no_outstanding,
            CHECK_EVIDENCE_REQUIRED_VALID: self._check_evidence_required_valid,
            CHECK_EVIDENCE_NOT_MISSING_FOR_JOURNAL: self._check_evidence_not_missing_for_journal,
            CHECK_REPORTING_PROVENANCE_AVAILABLE: self._check_reporting_provenance_available,
            CHECK_PERIOD_CLOSE_READINESS: self._check_period_close_readiness,
            CHECK_PERIOD_CLOSE_PERIOD_LOCKED: self._check_period_close_period_locked,
        }

    # ------------------------------------------------------------------
    # Control definitions (the library)
    # ------------------------------------------------------------------
    def define_control(
        self, org_id: str, code: str, name: str, description: str, objective: str,
        severity: ControlSeverity, domain: ControlDomain, check_key: str, actor: str,
        frequency: Optional[str] = None,
    ) -> ControlDefinition:
        if check_key not in self._check_registry:
            raise UnknownCheckKeyError(f"No built-in check registered for check_key {check_key!r}.")
        if self.definitions.get_by_code(org_id, code) is not None:
            raise DuplicateControlCodeError(f"A control with code {code!r} already exists for this organisation.")

        definition = ControlDefinition(
            id=_new_id(), org_id=org_id, code=code, name=name, description=description,
            objective=objective, severity=severity, domain=domain, check_key=check_key,
            created_by=actor, created_at=_now(), frequency=frequency,
        )
        self.definitions.create(definition)
        self._log(org_id, AuditAction.CONTROL_DEFINED, actor, "ControlDefinition", definition.id,
                   new_value={"code": code, "name": name, "domain": domain.value})
        return definition

    def deactivate_control(self, org_id: str, control_id: str, actor: str) -> ControlDefinition:
        definition = self._get_definition(org_id, control_id)
        definition.is_active = False
        self.definitions.update(definition)
        self._log(org_id, AuditAction.CONTROL_DEACTIVATED, actor, "ControlDefinition", definition.id)
        return definition

    def seed_standard_controls(self, org_id: str, actor: str) -> List[ControlDefinition]:
        """Idempotent: creates whichever of the standard library entries
        don't already exist for this organisation (matched by code) and
        returns the full standard set as it now stands. Does not
        prevent an organisation from also defining its own controls."""
        result = []
        for code, name, description, objective, severity, domain, check_key in _STANDARD_CONTROLS:
            existing = self.definitions.get_by_code(org_id, code)
            if existing is not None:
                result.append(existing)
                continue
            result.append(self.define_control(
                org_id, code, name, description, objective, severity, domain, check_key, actor,
            ))
        return result

    def _get_definition(self, org_id: str, control_id: str) -> ControlDefinition:
        definition = self.definitions.get(org_id, control_id)
        if definition is None:
            raise ControlDefinitionNotFoundError(f"Control {control_id} not found.")
        return definition

    def get_control(self, org_id: str, control_id: str) -> ControlDefinition:
        return self._get_definition(org_id, control_id)

    def list_controls(self, org_id: str, active_only: bool = False) -> List[ControlDefinition]:
        return self.definitions.list_for_org(org_id, active_only=active_only)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    def execute_control(
        self, org_id: str, control_id: str, actor: str,
        period_id: Optional[str] = None, params: Optional[dict] = None,
    ) -> ControlExecution:
        definition = self._get_definition(org_id, control_id)
        if not definition.is_active:
            raise InactiveControlError(f"Control {definition.code} is deactivated and cannot be executed.")

        check_fn = self._check_registry[definition.check_key]
        result, explanation, reference = check_fn(org_id, period_id, params or {}, actor)

        execution = ControlExecution(
            id=_new_id(), org_id=org_id, control_id=control_id, period_id=period_id,
            executed_by=actor, executed_at=_now(), result=result, explanation=explanation,
            reference=reference,
        )
        self.executions.create(execution)
        self._log(
            org_id, AuditAction.CONTROL_EXECUTED, actor, "ControlExecution", execution.id,
            new_value={"control_code": definition.code, "result": result.value, "period_id": period_id},
        )

        if result == ControlResult.FAIL:
            finding = self._create_finding(execution, definition, actor)
            execution.finding_id = finding.id
            self.executions.update(execution)
        return execution

    def create_finding_from_execution(
        self, org_id: str, execution_id: str, actor: str, description: Optional[str] = None,
    ) -> Finding:
        """For a WARNING or REQUIRES_REVIEW result the caller judges
        worth tracking — FAIL results already get one automatically
        (see execute_control)."""
        execution = self._get_execution(org_id, execution_id)
        if execution.finding_id is not None:
            raise FindingAlreadyExistsError(f"Execution {execution_id} already has finding {execution.finding_id}.")
        if execution.result not in (ControlResult.WARNING, ControlResult.REQUIRES_REVIEW):
            raise CannotCreateFindingForResultError(
                f"Execution {execution_id} has result {execution.result.value} — a finding may only be "
                f"created manually from WARNING or REQUIRES_REVIEW (FAIL already gets one automatically; "
                f"PASS/NOT_APPLICABLE describe no problem to record)."
            )
        definition = self._get_definition(org_id, execution.control_id)
        finding = self._create_finding(execution, definition, actor, description)
        execution.finding_id = finding.id
        self.executions.update(execution)
        return finding

    def _create_finding(
        self, execution: ControlExecution, definition: ControlDefinition, actor: str,
        description: Optional[str] = None,
    ) -> Finding:
        finding = Finding(
            id=_new_id(), org_id=execution.org_id, control_id=execution.control_id,
            execution_id=execution.id, description=description or execution.explanation,
            severity=definition.severity, status=FindingStatus.OPEN, created_by=actor, created_at=_now(),
        )
        finding.history.append({"at": _now().isoformat(), "by": actor, "status": "OPEN", "note": "created"})
        self.findings.create(finding)
        self._log(execution.org_id, AuditAction.FINDING_CREATED, actor, "Finding", finding.id,
                   new_value={"control_code": definition.code, "execution_id": execution.id})
        return finding

    def review_execution(self, org_id: str, execution_id: str, actor: str) -> ControlExecution:
        execution = self._get_execution(org_id, execution_id)
        execution.reviewed_by = actor
        execution.reviewed_at = _now()
        self.executions.update(execution)
        self._log(org_id, AuditAction.CONTROL_REVIEWED, actor, "ControlExecution", execution.id)
        return execution

    def _get_execution(self, org_id: str, execution_id: str) -> ControlExecution:
        execution = self.executions.get(org_id, execution_id)
        if execution is None:
            raise ControlExecutionNotFoundError(f"Control execution {execution_id} not found.")
        return execution

    def get_execution(self, org_id: str, execution_id: str) -> ControlExecution:
        return self._get_execution(org_id, execution_id)

    def list_executions(self, org_id: str, period_id: Optional[str] = None) -> List[ControlExecution]:
        return self.executions.list_for_org(org_id, period_id=period_id)

    # ------------------------------------------------------------------
    # Findings — named transitions only, never a raw "set status" call
    # ------------------------------------------------------------------
    def _get_finding(self, org_id: str, finding_id: str) -> Finding:
        finding = self.findings.get(org_id, finding_id)
        if finding is None:
            raise FindingNotFoundError(f"Finding {finding_id} not found.")
        return finding

    def get_finding(self, org_id: str, finding_id: str) -> Finding:
        return self._get_finding(org_id, finding_id)

    def list_findings(self, org_id: str, status: Optional[FindingStatus] = None) -> List[Finding]:
        return self.findings.list_for_org(org_id, status=status.value if status else None)

    def _transition_finding(self, finding: Finding, new_status: FindingStatus, actor: str, note: Optional[str] = None) -> Finding:
        rules.assert_finding_transition_allowed(finding.status, new_status)
        previous = finding.status.value
        finding.status = new_status
        finding.history.append({
            "at": _now().isoformat(), "by": actor, "status": new_status.value, "note": note,
        })
        self.findings.update(finding)
        self._log(finding.org_id, AuditAction.FINDING_STATUS_CHANGED, actor, "Finding", finding.id,
                   new_value={"from": previous, "to": new_status.value}, reason=note)
        return finding

    def start_review(self, org_id: str, finding_id: str, actor: str) -> Finding:
        return self._transition_finding(self._get_finding(org_id, finding_id), FindingStatus.UNDER_REVIEW, actor)

    def send_back_to_open(self, org_id: str, finding_id: str, actor: str, reason: str) -> Finding:
        return self._transition_finding(self._get_finding(org_id, finding_id), FindingStatus.OPEN, actor, reason)

    def mark_remediation_required(self, org_id: str, finding_id: str, actor: str, note: Optional[str] = None) -> Finding:
        return self._transition_finding(self._get_finding(org_id, finding_id), FindingStatus.REMEDIATION_REQUIRED, actor, note)

    def mark_resolved_without_remediation(self, org_id: str, finding_id: str, actor: str, reason: str) -> Finding:
        """For a finding a reviewer determines needs no fix (e.g. a
        false positive) — `reason` is required precisely because this
        skips the normal remediation path."""
        return self._transition_finding(self._get_finding(org_id, finding_id), FindingStatus.RESOLVED, actor, reason)

    def reopen_finding(self, org_id: str, finding_id: str, actor: str, reason: str) -> Finding:
        """The one transition NOT in domain/rules.py's table by design —
        reopening a CLOSED finding is an explicit, separately-audited
        action, never just another row in the ordinary flow."""
        finding = self._get_finding(org_id, finding_id)
        if finding.status != FindingStatus.CLOSED:
            from ..domain.errors import InvalidFindingStateError
            raise InvalidFindingStateError(f"Only a CLOSED finding can be reopened (this one is {finding.status.value}).")
        finding.status = FindingStatus.OPEN
        finding.closed_by = None
        finding.closed_at = None
        finding.history.append({"at": _now().isoformat(), "by": actor, "status": "OPEN", "note": f"Reopened: {reason}"})
        self.findings.update(finding)
        self._log(org_id, AuditAction.FINDING_REOPENED, actor, "Finding", finding.id, reason=reason)
        return finding

    def close_finding(self, org_id: str, finding_id: str, actor: str) -> Finding:
        finding = self._get_finding(org_id, finding_id)
        rules.assert_finding_transition_allowed(finding.status, FindingStatus.CLOSED)
        finding.status = FindingStatus.CLOSED
        finding.closed_by = actor
        finding.closed_at = _now()
        finding.history.append({"at": _now().isoformat(), "by": actor, "status": "CLOSED", "note": None})
        self.findings.update(finding)
        self._log(org_id, AuditAction.FINDING_CLOSED, actor, "Finding", finding.id)
        return finding

    # ------------------------------------------------------------------
    # Remediation
    # ------------------------------------------------------------------
    def create_remediation(
        self, org_id: str, finding_id: str, action: str, owner: str, actor: str,
        due_date: Optional[date] = None,
    ) -> Remediation:
        finding = self._get_finding(org_id, finding_id)
        if finding.status != FindingStatus.REMEDIATION_REQUIRED:
            from ..domain.errors import InvalidFindingStateError
            raise InvalidFindingStateError(
                f"Finding {finding_id} is {finding.status.value}; a remediation can only be created "
                f"once it is REMEDIATION_REQUIRED."
            )
        remediation = Remediation(
            id=_new_id(), org_id=org_id, finding_id=finding_id, action=action, owner=owner,
            status=RemediationStatus.PLANNED, created_by=actor, created_at=_now(), due_date=due_date,
        )
        self.remediations.create(remediation)
        finding.remediation_id = remediation.id
        self.findings.update(finding)
        self._log(org_id, AuditAction.REMEDIATION_CREATED, actor, "Remediation", remediation.id,
                   new_value={"finding_id": finding_id, "owner": owner})
        return remediation

    def _get_remediation(self, org_id: str, remediation_id: str) -> Remediation:
        remediation = self.remediations.get(org_id, remediation_id)
        if remediation is None:
            raise RemediationNotFoundError(f"Remediation {remediation_id} not found.")
        return remediation

    def get_remediation(self, org_id: str, remediation_id: str) -> Remediation:
        return self._get_remediation(org_id, remediation_id)

    def start_remediation(self, org_id: str, remediation_id: str, actor: str) -> Remediation:
        remediation = self._get_remediation(org_id, remediation_id)
        rules.assert_remediation_transition_allowed(remediation.status, RemediationStatus.IN_PROGRESS)
        remediation.status = RemediationStatus.IN_PROGRESS
        self.remediations.update(remediation)
        self._log(org_id, AuditAction.REMEDIATION_STARTED, actor, "Remediation", remediation.id)
        return remediation

    def complete_remediation(
        self, org_id: str, remediation_id: str, actor: str, completion_evidence_ref: Optional[str] = None,
    ) -> Remediation:
        remediation = self._get_remediation(org_id, remediation_id)
        rules.assert_remediation_transition_allowed(remediation.status, RemediationStatus.COMPLETED)
        remediation.status = RemediationStatus.COMPLETED
        remediation.completed_by = actor
        remediation.completed_at = _now()
        remediation.completion_evidence_ref = completion_evidence_ref
        self.remediations.update(remediation)
        self._log(org_id, AuditAction.REMEDIATION_COMPLETED, actor, "Remediation", remediation.id,
                   new_value={"completion_evidence_ref": completion_evidence_ref})

        finding = self._get_finding(org_id, remediation.finding_id)
        self._transition_finding(finding, FindingStatus.RESOLVED, actor, "Remediation marked complete.")
        return remediation

    def reject_remediation(self, org_id: str, remediation_id: str, actor: str, reason: str) -> Remediation:
        """A verifier disagreeing that the work is actually done — sends
        the remediation back to IN_PROGRESS and the finding back to
        REMEDIATION_REQUIRED, both explicitly, both audited."""
        remediation = self._get_remediation(org_id, remediation_id)
        rules.assert_remediation_transition_allowed(remediation.status, RemediationStatus.IN_PROGRESS)
        remediation.status = RemediationStatus.IN_PROGRESS
        remediation.completed_by = None
        remediation.completed_at = None
        self.remediations.update(remediation)
        self._log(org_id, AuditAction.REMEDIATION_REJECTED, actor, "Remediation", remediation.id, reason=reason)

        finding = self._get_finding(org_id, remediation.finding_id)
        self._transition_finding(finding, FindingStatus.REMEDIATION_REQUIRED, actor, f"Remediation rejected: {reason}")
        return remediation

    def verify_remediation(
        self, org_id: str, remediation_id: str, actor: str, note: Optional[str] = None,
    ) -> Remediation:
        """No same-actor check here — see the module docstring. This
        method trusts that the caller (API layer) already required
        `finding:verify`, a permission disjoint from `finding:remediate`
        in the default role matrix."""
        remediation = self._get_remediation(org_id, remediation_id)
        if remediation.status != RemediationStatus.COMPLETED:
            raise RemediationRequiredError(
                f"Remediation {remediation_id} is {remediation.status.value}, not COMPLETED — "
                f"nothing to verify yet."
            )
        rules.assert_remediation_transition_allowed(remediation.status, RemediationStatus.VERIFIED)
        remediation.status = RemediationStatus.VERIFIED
        remediation.verified_by = actor
        remediation.verified_at = _now()
        remediation.verification_note = note
        self.remediations.update(remediation)
        self._log(org_id, AuditAction.REMEDIATION_VERIFIED, actor, "Remediation", remediation.id, reason=note)

        finding = self._get_finding(org_id, remediation.finding_id)
        self._transition_finding(finding, FindingStatus.VERIFIED, actor, "Remediation independently verified.")
        return remediation

    # ------------------------------------------------------------------
    # Built-in checks — each calls exactly one authoritative module.
    # Signature: (org_id, period_id, params, executed_by) -> (result, explanation, reference)
    # ------------------------------------------------------------------
    def _check_trial_balance_balanced(self, org_id, period_id, params, executed_by):
        if period_id is None:
            return ControlResult.REQUIRES_REVIEW, "No period_id supplied for a period-scoped control.", {}
        tb = self.reporting.get_trial_balance(org_id, period_id, actor=executed_by)
        reference = {"total_debits": str(tb.total_debits), "total_credits": str(tb.total_credits)}
        if tb.is_balanced:
            return ControlResult.PASS, f"Balanced: debits {tb.total_debits} = credits {tb.total_credits}.", reference
        return ControlResult.FAIL, f"NOT balanced: debits {tb.total_debits} != credits {tb.total_credits}.", reference

    def _check_no_unposted_journals(self, org_id, period_id, params, executed_by):
        if period_id is None:
            return ControlResult.REQUIRES_REVIEW, "No period_id supplied for a period-scoped control.", {}
        drafts = self.accounting.journals.list_for_org(org_id, period_id=period_id, status=JournalStatus.DRAFT.value)
        if not drafts:
            return ControlResult.PASS, "No draft (unposted) journals in this period.", {}
        return (
            ControlResult.FAIL,
            f"{len(drafts)} draft journal(s) remain unposted in this period.",
            {"draft_journal_ids": [j.id for j in drafts]},
        )

    def _check_period_lock_status(self, org_id, period_id, params, executed_by):
        if period_id is None:
            return ControlResult.REQUIRES_REVIEW, "No period_id supplied for a period-scoped control.", {}
        period = self.accounting.periods.get(org_id, period_id)
        if period is None:
            return ControlResult.REQUIRES_REVIEW, f"Period {period_id} not found.", {}
        reference = {"period_status": period.status.value}
        if period.status.value in ("LOCKED", "CLOSED"):
            return ControlResult.PASS, f"Period is {period.status.value}.", reference
        return ControlResult.WARNING, f"Period is still {period.status.value} — not yet locked.", reference

    def _check_reconciliation_no_outstanding(self, org_id, period_id, params, executed_by):
        if self.reconciliation is None:
            return ControlResult.NOT_APPLICABLE, "Reconciliation integration not configured for this compliance service.", {}
        if period_id is None:
            return ControlResult.REQUIRES_REVIEW, "No period_id supplied for a period-scoped control.", {}
        period = self.accounting.periods.get(org_id, period_id)
        if period is None:
            return ControlResult.REQUIRES_REVIEW, f"Period {period_id} not found.", {}

        relevant = [
            r for r in self.reconciliation.list_reconciliations(org_id)
            if not (r.period_end < period.start_date or r.period_start > period.end_date)
        ]
        outstanding: List[str] = []
        for recon in relevant:
            for txn in self.reconciliation.list_transactions(org_id, recon.id):
                if txn.status != BankTransactionStatus.RECONCILED:
                    outstanding.append(txn.id)
        if not outstanding:
            return ControlResult.PASS, "All reconciliation activity overlapping this period is reconciled.", {
                "reconciliations_checked": [r.id for r in relevant],
            }
        return (
            ControlResult.WARNING,
            f"{len(outstanding)} bank transaction(s) overlapping this period are not yet RECONCILED.",
            {"outstanding_transaction_ids": outstanding},
        )

    def _check_evidence_required_valid(self, org_id, period_id, params, executed_by):
        evidence_refs = params.get("evidence_refs") or []
        if not evidence_refs:
            return ControlResult.NOT_APPLICABLE, "No evidence references were designated as required for this execution.", {}
        if self.evidence is None:
            return ControlResult.FAIL, "Evidence was required, but Evidence Vault integration is not configured.", {
                "evidence_refs": evidence_refs,
            }
        problems: dict[str, str] = {}
        for evidence_id in evidence_refs:
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
            return ControlResult.PASS, f"All {len(evidence_refs)} required evidence reference(s) are verified.", {
                "evidence_refs": evidence_refs,
            }
        return ControlResult.FAIL, f"{len(problems)} of {len(evidence_refs)} required evidence reference(s) failed: {problems}.", {
            "problems": problems,
        }

    def _check_evidence_not_missing_for_journal(self, org_id, period_id, params, executed_by):
        journal_id = params.get("journal_id")
        if not journal_id:
            return ControlResult.REQUIRES_REVIEW, "No journal_id supplied.", {}
        if self.evidence is None:
            return ControlResult.NOT_APPLICABLE, "Evidence Vault integration not configured.", {}
        status = self.evidence.get_status_for_reference(org_id, journal_id=journal_id)
        reference = {"journal_id": journal_id, "evidence_status": status}
        if status == EVIDENCE_MISSING:
            return ControlResult.FAIL, f"No evidence is linked to journal {journal_id}.", reference
        if status == EvidenceStatus.REJECTED.value:
            return ControlResult.FAIL, f"Evidence linked to journal {journal_id} was REJECTED.", reference
        if status == EvidenceStatus.VERIFIED.value:
            return ControlResult.PASS, f"Verified evidence is linked to journal {journal_id}.", reference
        return ControlResult.WARNING, f"Evidence linked to journal {journal_id} is present but not verified ({status}).", reference

    def _check_reporting_provenance_available(self, org_id, period_id, params, executed_by):
        if period_id is None:
            return ControlResult.REQUIRES_REVIEW, "No period_id supplied for a period-scoped control.", {}
        tb = self.reporting.get_trial_balance(org_id, period_id, actor=executed_by)
        nonzero_lines = [l for l in tb.lines if l.debit_total != 0 or l.credit_total != 0]
        if not nonzero_lines:
            return ControlResult.NOT_APPLICABLE, "No ledger activity in this period to trace.", {}
        untraceable = []
        for line in nonzero_lines:
            entries = self.reporting.trace_line(org_id, line.account_id, period_id=period_id)
            if not entries or not any(e.get("journal_id") for e in entries):
                untraceable.append(line.account_id)
        if not untraceable:
            return ControlResult.PASS, f"All {len(nonzero_lines)} active account(s) trace to at least one posted journal.", {
                "accounts_checked": [l.account_id for l in nonzero_lines],
            }
        return ControlResult.FAIL, f"{len(untraceable)} account(s) with a non-zero balance have no traceable journal entries.", {
            "untraceable_account_ids": untraceable,
        }

    def _check_period_close_readiness(self, org_id, period_id, params, executed_by):
        if self.period_close is None:
            return ControlResult.NOT_APPLICABLE, "Period Close integration not configured for this compliance service.", {}
        if period_id is None:
            return ControlResult.REQUIRES_REVIEW, "No period_id supplied for a period-scoped control.", {}
        readiness = self.period_close.check_close_readiness(org_id, period_id, actor=executed_by)
        reference = {"blocking_failures": [c.value for c in readiness.blocking_failures]}
        if readiness.is_ready:
            return ControlResult.PASS, "Period Close readiness controls all pass.", reference
        return ControlResult.FAIL, f"Period Close readiness controls failed: {reference['blocking_failures']}.", reference

    def _check_period_close_period_locked(self, org_id, period_id, params, executed_by):
        if period_id is None:
            return ControlResult.REQUIRES_REVIEW, "No period_id supplied for a period-scoped control.", {}
        period = self.accounting.periods.get(org_id, period_id)
        if period is None:
            return ControlResult.REQUIRES_REVIEW, f"Period {period_id} not found.", {}
        reference = {"period_status": period.status.value}
        if period.status.value in ("LOCKED", "CLOSED"):
            return ControlResult.PASS, f"Period is {period.status.value} — close was completed.", reference
        return ControlResult.FAIL, f"Period is {period.status.value} — close has not been completed.", reference

    # ------------------------------------------------------------------
    def _log(
        self, org_id: str, action: AuditAction, actor: str, entity_type: str, entity_id: str,
        new_value: Optional[dict] = None, reason: Optional[str] = None,
    ) -> None:
        self.audit.record(
            AuditEvent(
                id=_new_id(), org_id=org_id, entity_type=entity_type, entity_id=entity_id,
                action=action.value, actor=actor, timestamp=_now(),
                new_value=new_value, reason=reason,
            )
        )
