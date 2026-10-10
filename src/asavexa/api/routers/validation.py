"""Professional validation endpoints. Thin: every rule lives in asavexa.validation.service and is tested there.

Reading needs audit:read. Running the panel and engagements needs validation:manage (owners and administrators).
Recording a review or an independence declaration needs audit:read plus the service's own authority rule: a reviewer linked to
a user acts only as that user; an unlinked reviewer can be recorded on their behalf only by a manager, with a reference to the signed document."""
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...identity.domain.errors import PermissionDeniedError
from ...identity.domain.permissions import AUDIT_READ, VALIDATION_MANAGE
from ...identity.services.service import IdentityService
from ...compliance.services.service import ComplianceService
from ...evidence.services.vault import EvidenceVault
from ...accounting.services.engine import AccountingEngine
from ...security.context import SecurityContext
from ...validation.catalog import BODIES, CONCLUSIONS, DISCLAIMER, RESPONSES, SEVERITIES, SPECIALISMS, STAGES
from ...validation.service import ValidationService
from ...validation.snapshot import build_snapshot
from ..deps import (get_accounting_engine, get_compliance_service, get_current_actor, get_current_org, get_evidence_vault, get_identity_service,
                    get_security, get_validation, require_permission)

router = APIRouter(prefix="/validation", tags=["Professional Validation"])
_read = Depends(require_permission(AUDIT_READ))
_manage = Depends(require_permission(VALIDATION_MANAGE))


class CredentialBody(BaseModel):
    body: str
    membership_no: str
    jurisdiction: str = ""
    year_admitted: Optional[int] = None


class ReviewerBody(BaseModel):
    name: str
    email: str
    credentials: List[CredentialBody]
    specialisms: List[str]
    affiliation: str = ""
    user_id: Optional[str] = None


class ReviewerUpdateBody(BaseModel):
    name: Optional[str] = None
    specialisms: Optional[List[str]] = None
    affiliation: Optional[str] = None
    user_id: Optional[str] = None
    add_credential: Optional[CredentialBody] = None


class VerifyBody(BaseModel):
    accepted: bool
    method: str
    note: str = ""


class EngagementBody(BaseModel):
    title: str
    description: str = ""
    as_of: str
    stages: Optional[List[str]] = None
    min_reviewers: Optional[Dict[str, int]] = None


class WithdrawBody(BaseModel):
    reason: str


class AssignBody(BaseModel):
    stage: str
    reviewer_id: str


class DeclarationBody(BaseModel):
    reviewer_id: str
    independent: bool
    details: str = ""
    confirmations: Dict[str, bool]
    source_reference: Optional[str] = None


class ObservationBody(BaseModel):
    id: Optional[str] = None
    severity: str
    text: str
    recommendation: str = ""


class ReviewBody(BaseModel):
    stage: str
    reviewer_id: str
    conclusion: Optional[str] = None
    scope_reviewed: str = ""
    basis: str = ""
    limitations: str = ""
    competence_confirmed: bool = False
    observations: List[ObservationBody] = []
    source_reference: Optional[str] = None


class ResponseBody(BaseModel):
    status: str
    note: str


def _can_manage(identity: IdentityService, actor: str, org_id: str) -> bool:
    try:
        identity.require_permission(actor, org_id, VALIDATION_MANAGE)
        return True
    except PermissionDeniedError:
        return False


def current_snapshot(org_id: str, vault: EvidenceVault, accounting: AccountingEngine, compliance: ComplianceService,
                     identity: IdentityService, security: SecurityContext) -> dict:
    ids = [m.user_id for m in identity.list_members(org_id) if m.status.value == "ACTIVE"]
    return build_snapshot(
        evidence=vault.list_for_org(org_id), journals=accounting.journals.list_for_org(org_id), periods=accounting.periods.list_for_org(org_id),
        controls=compliance.list_controls(org_id), executions=compliance.list_executions(org_id), findings=compliance.list_findings(org_id),
        audit_chain=security.verify_audit(org_id), security=security.overview(org_id, ids))


@router.get("/guide", dependencies=[_read])
def guide():
    return {"stages": STAGES, "specialisms": SPECIALISMS, "bodies": BODIES, "conclusions": CONCLUSIONS, "severities": SEVERITIES, "responses": RESPONSES,
            "disclaimer": DISCLAIMER}


@router.get("/me")
def me(actor: str = Depends(get_current_actor), org_id: str = Depends(get_current_org), identity: IdentityService = Depends(get_identity_service),
       svc: ValidationService = Depends(get_validation)):
    """Who the signed-in person is on the panel (if anyone), and whether they can manage validation."""
    r = svc.reviewer_for_user(org_id, actor)
    return {"can_manage": _can_manage(identity, actor, org_id), "reviewer": svc._reviewer_out(r) if r else None}


# ------------------------------------------------------------------ panel
@router.get("/panel", dependencies=[_read])
def panel(org_id: str = Depends(get_current_org), svc: ValidationService = Depends(get_validation)):
    return svc.panel(org_id)


@router.post("/panel", dependencies=[_manage], status_code=201)
def add_reviewer(body: ReviewerBody, org_id: str = Depends(get_current_org), actor: str = Depends(get_current_actor),
                 identity: IdentityService = Depends(get_identity_service), svc: ValidationService = Depends(get_validation)):
    if body.user_id and not any(m.user_id == body.user_id and m.status.value == "ACTIVE" for m in identity.list_members(org_id)):
        from ...validation.errors import ProfessionalValidationError
        raise ProfessionalValidationError("That user is not an active member of this organisation.")
    return svc.add_reviewer(org_id, actor, body.name, body.email, [c.model_dump() for c in body.credentials], body.specialisms, body.affiliation, body.user_id)


@router.put("/panel/{reviewer_id}", dependencies=[_manage])
def update_reviewer(reviewer_id: str, body: ReviewerUpdateBody, org_id: str = Depends(get_current_org), actor: str = Depends(get_current_actor),
                    svc: ValidationService = Depends(get_validation)):
    f = body.model_dump(exclude_unset=True)
    return svc.update_reviewer(org_id, actor, reviewer_id, **f)


@router.post("/panel/{reviewer_id}/credentials/{index}/verify", dependencies=[_manage])
def verify_credential(reviewer_id: str, index: int, body: VerifyBody, org_id: str = Depends(get_current_org), actor: str = Depends(get_current_actor),
                      svc: ValidationService = Depends(get_validation)):
    return svc.verify_credential(org_id, actor, reviewer_id, index, body.accepted, body.method, body.note)


@router.post("/panel/{reviewer_id}/deactivate", dependencies=[_manage])
def deactivate_reviewer(reviewer_id: str, org_id: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ValidationService = Depends(get_validation)):
    return svc.set_active(org_id, actor, reviewer_id, False)


@router.post("/panel/{reviewer_id}/activate", dependencies=[_manage])
def activate_reviewer(reviewer_id: str, org_id: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ValidationService = Depends(get_validation)):
    return svc.set_active(org_id, actor, reviewer_id, True)


# ------------------------------------------------------------------ engagements
@router.get("/engagements", dependencies=[_read])
def list_engagements(org_id: str = Depends(get_current_org), svc: ValidationService = Depends(get_validation)):
    return svc.list_engagements(org_id)


@router.get("/snapshot/preview", dependencies=[_manage])
def snapshot_preview(org_id: str = Depends(get_current_org), vault: EvidenceVault = Depends(get_evidence_vault), accounting: AccountingEngine = Depends(get_accounting_engine),
                     compliance: ComplianceService = Depends(get_compliance_service), identity: IdentityService = Depends(get_identity_service),
                     security: SecurityContext = Depends(get_security)):
    return current_snapshot(org_id, vault, accounting, compliance, identity, security)


@router.post("/engagements", dependencies=[_manage], status_code=201)
def create_engagement(body: EngagementBody, org_id: str = Depends(get_current_org), actor: str = Depends(get_current_actor),
                      vault: EvidenceVault = Depends(get_evidence_vault), accounting: AccountingEngine = Depends(get_accounting_engine),
                      compliance: ComplianceService = Depends(get_compliance_service), identity: IdentityService = Depends(get_identity_service),
                      security: SecurityContext = Depends(get_security), svc: ValidationService = Depends(get_validation)):
    snap = current_snapshot(org_id, vault, accounting, compliance, identity, security)
    return svc.create_engagement(org_id, actor, body.title, body.description, body.as_of, snap, body.stages, body.min_reviewers)


@router.get("/engagements/{engagement_id}", dependencies=[_read])
def engagement(engagement_id: str, org_id: str = Depends(get_current_org), vault: EvidenceVault = Depends(get_evidence_vault),
               accounting: AccountingEngine = Depends(get_accounting_engine), compliance: ComplianceService = Depends(get_compliance_service),
               identity: IdentityService = Depends(get_identity_service), security: SecurityContext = Depends(get_security),
               svc: ValidationService = Depends(get_validation)):
    from ...validation.service import sha
    snap_hash = sha(current_snapshot(org_id, vault, accounting, compliance, identity, security))
    return svc.detail(org_id, engagement_id, snap_hash)


@router.post("/engagements/{engagement_id}/refresh-snapshot", dependencies=[_manage])
def refresh_snapshot(engagement_id: str, org_id: str = Depends(get_current_org), actor: str = Depends(get_current_actor), vault: EvidenceVault = Depends(get_evidence_vault),
                     accounting: AccountingEngine = Depends(get_accounting_engine), compliance: ComplianceService = Depends(get_compliance_service),
                     identity: IdentityService = Depends(get_identity_service), security: SecurityContext = Depends(get_security),
                     svc: ValidationService = Depends(get_validation)):
    return svc.refresh_snapshot(org_id, actor, engagement_id, current_snapshot(org_id, vault, accounting, compliance, identity, security))


@router.post("/engagements/{engagement_id}/open", dependencies=[_manage])
def open_engagement(engagement_id: str, org_id: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ValidationService = Depends(get_validation)):
    return svc.open(org_id, actor, engagement_id)


@router.post("/engagements/{engagement_id}/withdraw", dependencies=[_manage])
def withdraw(engagement_id: str, body: WithdrawBody, org_id: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ValidationService = Depends(get_validation)):
    return svc.withdraw(org_id, actor, engagement_id, body.reason)


@router.post("/engagements/{engagement_id}/assignments", dependencies=[_manage])
def assign(engagement_id: str, body: AssignBody, org_id: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ValidationService = Depends(get_validation)):
    return svc.assign(org_id, actor, engagement_id, body.stage, body.reviewer_id)


@router.delete("/engagements/{engagement_id}/assignments/{assignment_id}", dependencies=[_manage])
def unassign(engagement_id: str, assignment_id: str, org_id: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ValidationService = Depends(get_validation)):
    return svc.unassign(org_id, actor, engagement_id, assignment_id)


@router.post("/engagements/{engagement_id}/declarations", dependencies=[_read])
def declare(engagement_id: str, body: DeclarationBody, org_id: str = Depends(get_current_org), actor: str = Depends(get_current_actor),
            identity: IdentityService = Depends(get_identity_service), svc: ValidationService = Depends(get_validation)):
    return svc.declare_independence(org_id, actor, engagement_id, body.reviewer_id, body.independent, body.details, body.confirmations,
                                    can_manage=_can_manage(identity, actor, org_id), source_reference=body.source_reference)


@router.post("/engagements/{engagement_id}/reviews", dependencies=[_read])
def save_review(engagement_id: str, body: ReviewBody, org_id: str = Depends(get_current_org), actor: str = Depends(get_current_actor),
                identity: IdentityService = Depends(get_identity_service), svc: ValidationService = Depends(get_validation)):
    content = body.model_dump()
    stage, rid = content.pop("stage"), content.pop("reviewer_id")
    return svc.save_review(org_id, actor, engagement_id, stage, rid, content, can_manage=_can_manage(identity, actor, org_id))


@router.post("/engagements/{engagement_id}/reviews/{review_id}/sign", dependencies=[_read])
def sign_review(engagement_id: str, review_id: str, org_id: str = Depends(get_current_org), actor: str = Depends(get_current_actor),
                identity: IdentityService = Depends(get_identity_service), svc: ValidationService = Depends(get_validation)):
    return svc.sign_review(org_id, actor, engagement_id, review_id, can_manage=_can_manage(identity, actor, org_id))


@router.post("/engagements/{engagement_id}/reviews/{review_id}/observations/{observation_id}/response", dependencies=[_manage])
def respond(engagement_id: str, review_id: str, observation_id: str, body: ResponseBody, org_id: str = Depends(get_current_org), actor: str = Depends(get_current_actor),
            svc: ValidationService = Depends(get_validation)):
    return svc.respond(org_id, actor, engagement_id, review_id, observation_id, body.status, body.note)


@router.post("/engagements/{engagement_id}/complete", dependencies=[_manage])
def complete(engagement_id: str, org_id: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ValidationService = Depends(get_validation)):
    return svc.complete(org_id, actor, engagement_id)


@router.get("/engagements/{engagement_id}/statement", dependencies=[_read])
def statement(engagement_id: str, org_id: str = Depends(get_current_org), vault: EvidenceVault = Depends(get_evidence_vault),
              accounting: AccountingEngine = Depends(get_accounting_engine), compliance: ComplianceService = Depends(get_compliance_service),
              identity: IdentityService = Depends(get_identity_service), security: SecurityContext = Depends(get_security),
              svc: ValidationService = Depends(get_validation)):
    from ...validation.service import sha
    return svc.statement(org_id, engagement_id, sha(current_snapshot(org_id, vault, accounting, compliance, identity, security)))
