"""
Router for Controls & Compliance / Audit Workspace.

This is the actual enforcement point for every permission this module
introduced — ComplianceService itself performs no permission checks
(see its own docstring). Five capabilities, five permissions, applied
to disjoint sets of endpoints below:

    control:read       -> every GET
    control:manage      -> define / deactivate / seed the control library
    control:execute     -> run or review a control execution
    finding:manage      -> triage a finding: start review, send back,
                            mark remediation required, resolve without
                            remediation, reopen a closed finding, and
                            manually create a finding from a non-FAIL
                            execution (itself a triage judgement call)
    finding:remediate   -> create/start/complete a Remediation
    finding:verify       -> verify a completed Remediation, reject one,
                            and close a finding (only reachable after
                            independent verification)

finding:manage is never combined with finding:remediate or
finding:verify on any endpoint below — see
identity/domain/permissions.py and tests/test_compliance_permissions.py
for the proof that granting one never implies another.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends

from ...compliance.domain.enums import FindingStatus
from ...compliance.services.service import ComplianceService
from ...identity.domain.permissions import (
    CONTROL_EXECUTE,
    CONTROL_MANAGE,
    CONTROL_READ,
    FINDING_MANAGE,
    FINDING_REMEDIATE,
    FINDING_VERIFY,
)
from ..deps import get_compliance_service, get_current_actor, get_current_org, require_permission
from ..schemas.compliance import (
    CompleteRemediationRequest,
    ControlDefinitionOut,
    ControlExecutionOut,
    CreateFindingRequest,
    CreateRemediationRequest,
    DefineControlRequest,
    ExecuteControlRequest,
    FindingOut,
    FindingTransitionRequest,
    RejectRemediationRequest,
    RemediationOut,
    ReopenFindingRequest,
    RequiredReasonRequest,
    VerifyRemediationRequest,
)

router = APIRouter(prefix="/compliance", tags=["Controls & Compliance"])


# ----------------------------------------------------------------------
# Control library — control:manage to write, control:read to view
# ----------------------------------------------------------------------
@router.post("/controls", response_model=ControlDefinitionOut, status_code=201,
             dependencies=[Depends(require_permission(CONTROL_MANAGE))])
def define_control(
    body: DefineControlRequest,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    service: ComplianceService = Depends(get_compliance_service),
):
    return service.define_control(
        org_id, body.code, body.name, body.description, body.objective, body.severity,
        body.domain, body.check_key, actor=actor, frequency=body.frequency,
    )


@router.post("/controls/seed-standard", response_model=list[ControlDefinitionOut],
             dependencies=[Depends(require_permission(CONTROL_MANAGE))])
def seed_standard_controls(
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    service: ComplianceService = Depends(get_compliance_service),
):
    return service.seed_standard_controls(org_id, actor=actor)


@router.post("/controls/{control_id}/deactivate", response_model=ControlDefinitionOut,
             dependencies=[Depends(require_permission(CONTROL_MANAGE))])
def deactivate_control(
    control_id: str,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    service: ComplianceService = Depends(get_compliance_service),
):
    return service.deactivate_control(org_id, control_id, actor=actor)


@router.get("/controls", response_model=list[ControlDefinitionOut],
            dependencies=[Depends(require_permission(CONTROL_READ))])
def list_controls(
    active_only: bool = False,
    org_id: str = Depends(get_current_org),
    service: ComplianceService = Depends(get_compliance_service),
):
    return service.list_controls(org_id, active_only=active_only)


@router.get("/controls/{control_id}", response_model=ControlDefinitionOut,
            dependencies=[Depends(require_permission(CONTROL_READ))])
def get_control(
    control_id: str,
    org_id: str = Depends(get_current_org),
    service: ComplianceService = Depends(get_compliance_service),
):
    return service.get_control(org_id, control_id)


# ----------------------------------------------------------------------
# Execution — control:execute to run/review, control:read to view
# ----------------------------------------------------------------------
@router.post("/controls/{control_id}/execute", response_model=ControlExecutionOut, status_code=201,
             dependencies=[Depends(require_permission(CONTROL_EXECUTE))])
def execute_control(
    control_id: str,
    body: ExecuteControlRequest,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    service: ComplianceService = Depends(get_compliance_service),
):
    return service.execute_control(org_id, control_id, actor=actor, period_id=body.period_id, params=body.params)


@router.post("/executions/{execution_id}/review", response_model=ControlExecutionOut,
             dependencies=[Depends(require_permission(CONTROL_EXECUTE))])
def review_execution(
    execution_id: str,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    service: ComplianceService = Depends(get_compliance_service),
):
    return service.review_execution(org_id, execution_id, actor=actor)


@router.get("/executions/{execution_id}", response_model=ControlExecutionOut,
            dependencies=[Depends(require_permission(CONTROL_READ))])
def get_execution(
    execution_id: str,
    org_id: str = Depends(get_current_org),
    service: ComplianceService = Depends(get_compliance_service),
):
    return service.get_execution(org_id, execution_id)


@router.get("/executions", response_model=list[ControlExecutionOut],
            dependencies=[Depends(require_permission(CONTROL_READ))])
def list_executions(
    period_id: Optional[str] = None,
    org_id: str = Depends(get_current_org),
    service: ComplianceService = Depends(get_compliance_service),
):
    return service.list_executions(org_id, period_id=period_id)


# ----------------------------------------------------------------------
# Findings — finding:manage for every triage transition; finding:read
# is covered by control:read (findings are read alongside controls,
# not a separate read permission — see permissions.py: there is
# deliberately no sixth "finding:read", control:read already covers
# reading everything this module produces).
# ----------------------------------------------------------------------
@router.post("/executions/{execution_id}/create-finding", response_model=FindingOut, status_code=201,
             dependencies=[Depends(require_permission(FINDING_MANAGE))])
def create_finding_from_execution(
    execution_id: str,
    body: CreateFindingRequest,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    service: ComplianceService = Depends(get_compliance_service),
):
    """For a WARNING/REQUIRES_REVIEW execution the caller judges worth
    tracking — a FAIL already gets one automatically. Gated by
    finding:manage, not control:execute: deciding to open a finding is
    a triage judgement, not re-running the control."""
    return service.create_finding_from_execution(org_id, execution_id, actor=actor, description=body.description)


@router.get("/findings", response_model=list[FindingOut],
            dependencies=[Depends(require_permission(CONTROL_READ))])
def list_findings(
    status: Optional[FindingStatus] = None,
    org_id: str = Depends(get_current_org),
    service: ComplianceService = Depends(get_compliance_service),
):
    return service.list_findings(org_id, status=status)


@router.get("/findings/{finding_id}", response_model=FindingOut,
            dependencies=[Depends(require_permission(CONTROL_READ))])
def get_finding(
    finding_id: str,
    org_id: str = Depends(get_current_org),
    service: ComplianceService = Depends(get_compliance_service),
):
    return service.get_finding(org_id, finding_id)


@router.post("/findings/{finding_id}/start-review", response_model=FindingOut,
             dependencies=[Depends(require_permission(FINDING_MANAGE))])
def start_review(
    finding_id: str,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    service: ComplianceService = Depends(get_compliance_service),
):
    return service.start_review(org_id, finding_id, actor=actor)


@router.post("/findings/{finding_id}/send-back-to-open", response_model=FindingOut,
             dependencies=[Depends(require_permission(FINDING_MANAGE))])
def send_back_to_open(
    finding_id: str,
    body: RequiredReasonRequest,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    service: ComplianceService = Depends(get_compliance_service),
):
    return service.send_back_to_open(org_id, finding_id, actor=actor, reason=body.reason)


@router.post("/findings/{finding_id}/mark-remediation-required", response_model=FindingOut,
             dependencies=[Depends(require_permission(FINDING_MANAGE))])
def mark_remediation_required(
    finding_id: str,
    body: FindingTransitionRequest,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    service: ComplianceService = Depends(get_compliance_service),
):
    return service.mark_remediation_required(org_id, finding_id, actor=actor, note=body.reason)


@router.post("/findings/{finding_id}/mark-resolved-without-remediation", response_model=FindingOut,
             dependencies=[Depends(require_permission(FINDING_MANAGE))])
def mark_resolved_without_remediation(
    finding_id: str,
    body: RequiredReasonRequest,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    service: ComplianceService = Depends(get_compliance_service),
):
    return service.mark_resolved_without_remediation(org_id, finding_id, actor=actor, reason=body.reason)


@router.post("/findings/{finding_id}/reopen", response_model=FindingOut,
             dependencies=[Depends(require_permission(FINDING_MANAGE))])
def reopen_finding(
    finding_id: str,
    body: ReopenFindingRequest,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    service: ComplianceService = Depends(get_compliance_service),
):
    """The one transition outside the ordinary table — reopening a
    CLOSED finding — still gated by finding:manage, still requires an
    explicit reason, still fully audited (FINDING_REOPENED)."""
    return service.reopen_finding(org_id, finding_id, actor=actor, reason=body.reason)


# ----------------------------------------------------------------------
# Remediation — finding:remediate to do the work
# ----------------------------------------------------------------------
@router.post("/findings/{finding_id}/remediations", response_model=RemediationOut, status_code=201,
             dependencies=[Depends(require_permission(FINDING_REMEDIATE))])
def create_remediation(
    finding_id: str,
    body: CreateRemediationRequest,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    service: ComplianceService = Depends(get_compliance_service),
):
    return service.create_remediation(org_id, finding_id, body.action, body.owner, actor=actor, due_date=body.due_date)


@router.get("/remediations/{remediation_id}", response_model=RemediationOut,
            dependencies=[Depends(require_permission(CONTROL_READ))])
def get_remediation(
    remediation_id: str,
    org_id: str = Depends(get_current_org),
    service: ComplianceService = Depends(get_compliance_service),
):
    return service.get_remediation(org_id, remediation_id)


@router.post("/remediations/{remediation_id}/start", response_model=RemediationOut,
             dependencies=[Depends(require_permission(FINDING_REMEDIATE))])
def start_remediation(
    remediation_id: str,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    service: ComplianceService = Depends(get_compliance_service),
):
    return service.start_remediation(org_id, remediation_id, actor=actor)


@router.post("/remediations/{remediation_id}/complete", response_model=RemediationOut,
             dependencies=[Depends(require_permission(FINDING_REMEDIATE))])
def complete_remediation(
    remediation_id: str,
    body: CompleteRemediationRequest,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    service: ComplianceService = Depends(get_compliance_service),
):
    return service.complete_remediation(org_id, remediation_id, actor=actor, completion_evidence_ref=body.completion_evidence_ref)


# ----------------------------------------------------------------------
# Verification — finding:verify, strictly separate from finding:remediate
# ----------------------------------------------------------------------
@router.post("/remediations/{remediation_id}/verify", response_model=RemediationOut,
             dependencies=[Depends(require_permission(FINDING_VERIFY))])
def verify_remediation(
    remediation_id: str,
    body: VerifyRemediationRequest,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    service: ComplianceService = Depends(get_compliance_service),
):
    """No same-actor check here — see ComplianceService.verify_remediation's
    own docstring. Enforcement is exactly this permission being disjoint
    from finding:remediate in the default role matrix (ACCOUNTANT has
    the latter, not the former; APPROVER has the former, not the
    latter)."""
    return service.verify_remediation(org_id, remediation_id, actor=actor, note=body.note)


@router.post("/remediations/{remediation_id}/reject", response_model=RemediationOut,
             dependencies=[Depends(require_permission(FINDING_VERIFY))])
def reject_remediation(
    remediation_id: str,
    body: RejectRemediationRequest,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    service: ComplianceService = Depends(get_compliance_service),
):
    return service.reject_remediation(org_id, remediation_id, actor=actor, reason=body.reason)


@router.post("/findings/{finding_id}/close", response_model=FindingOut,
             dependencies=[Depends(require_permission(FINDING_VERIFY))])
def close_finding(
    finding_id: str,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    service: ComplianceService = Depends(get_compliance_service),
):
    """Only reachable from VERIFIED — gated by finding:verify, not
    finding:manage, since closing is the verifier's final sign-off,
    not a triage action."""
    return service.close_finding(org_id, finding_id, actor=actor)
