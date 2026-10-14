"""AI governance endpoints (records and evidence): inventory of AI systems, model changes, AI incidents. Thin: the rules live in asavexa.aigov.

Viewing needs audit:read. Proposing systems and recording changes and incidents need aigov:prepare. Approving, rejecting, retiring, reviewing, voiding and setting the
policy need aigov:approve; the service refuses the person whose work is being decided. The organisation always comes from the signed-in session.
Nothing here connects to, tests or measures any AI system."""
from typing import Any, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...aigov.service import AigovService
from ...identity.domain.permissions import AIG_APPROVE, AIG_PREPARE, AUDIT_READ
from ..deps import get_aigov, get_current_actor, get_current_org, require_permission

router = APIRouter(prefix="/aigov", tags=["AI governance"], dependencies=[Depends(require_permission(AUDIT_READ))])
_prepare = Depends(require_permission(AIG_PREPARE))
_approve = Depends(require_permission(AIG_APPROVE))


class ReasonBody(BaseModel):
    reason: str = ""


class NoteBody(BaseModel):
    note: str = ""


class PolicyBody(BaseModel):
    review_days: Optional[Any] = None
    incident_review_days: Optional[Any] = None


class SystemBody(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    origin: Optional[str] = None
    vendor_name: Optional[str] = None
    intended_use: Optional[str] = None
    out_of_scope: Optional[str] = None
    risk_tier: Optional[str] = None
    data_categories: Optional[str] = None
    human_oversight: Optional[str] = None
    owner_name: Optional[str] = None


class ChangeBody(BaseModel):
    system_id: Optional[str] = None
    change_kind: Optional[str] = None
    from_version: Optional[str] = None
    to_version: Optional[str] = None
    description: Optional[str] = None
    effective_on: Optional[str] = None
    testing_summary: Optional[str] = None
    evidence_ids: List[str] = []


class IncidentBody(BaseModel):
    system_id: Optional[str] = None
    incident_kind: Optional[str] = None
    severity: Optional[str] = None
    description: Optional[str] = None
    occurred_on: Optional[str] = None
    discovered_on: Optional[str] = None
    harm: Optional[str] = None
    people_affected: Optional[Any] = None
    evidence_ids: List[str] = []


class ReviewBody(BaseModel):
    cause: Optional[str] = None
    corrective_action: Optional[str] = None


def _d(body) -> dict:
    """Only the fields the caller actually sent."""
    return body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)


@router.get("/options")
def options(org: str = Depends(get_current_org), svc: AigovService = Depends(get_aigov)): return svc.aig_options(org)


@router.get("/overview")
def overview(org: str = Depends(get_current_org), svc: AigovService = Depends(get_aigov)): return svc.aig_overview(org)


@router.get("/policy")
def policy(org: str = Depends(get_current_org), svc: AigovService = Depends(get_aigov)): return svc.aig_get_policy(org)


@router.put("/policy", dependencies=[_approve])
def set_policy(body: PolicyBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: AigovService = Depends(get_aigov)):
    return svc.aig_set_policy(org, _d(body), actor)


@router.get("/systems")
def systems(status: Optional[str] = None, tier: Optional[str] = None, org: str = Depends(get_current_org), svc: AigovService = Depends(get_aigov)): return svc.aig_list_systems(org, status, tier)


@router.post("/systems", status_code=201, dependencies=[_prepare])
def propose_system(body: SystemBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: AigovService = Depends(get_aigov)):
    return svc.aig_propose_system(org, _d(body), actor)


@router.get("/systems/{sid}")
def get_system(sid: str, org: str = Depends(get_current_org), svc: AigovService = Depends(get_aigov)): return svc.aig_get_system(org, sid)


@router.post("/systems/{sid}/approve", dependencies=[_approve])
def approve_system(sid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: AigovService = Depends(get_aigov)):
    return svc.aig_approve_system(org, sid, actor, body.note)


@router.post("/systems/{sid}/reject", dependencies=[_approve])
def reject_system(sid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: AigovService = Depends(get_aigov)):
    return svc.aig_reject_system(org, sid, body.reason, actor)


@router.post("/systems/{sid}/retire", dependencies=[_approve])
def retire_system(sid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: AigovService = Depends(get_aigov)):
    return svc.aig_retire_system(org, sid, body.reason, actor)


@router.post("/systems/{sid}/review", dependencies=[_approve])
def review_system(sid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: AigovService = Depends(get_aigov)):
    return svc.aig_review_system(org, sid, body.note, actor)


@router.get("/changes")
def changes(system_id: Optional[str] = None, status: Optional[str] = None, org: str = Depends(get_current_org), svc: AigovService = Depends(get_aigov)): return svc.aig_list_changes(org, system_id, status)


@router.post("/changes", status_code=201, dependencies=[_prepare])
def record_change(body: ChangeBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: AigovService = Depends(get_aigov)):
    return svc.aig_record_change(org, _d(body), actor)


@router.get("/changes/{cid}")
def get_change(cid: str, org: str = Depends(get_current_org), svc: AigovService = Depends(get_aigov)): return svc.aig_get_change(org, cid)


@router.post("/changes/{cid}/approve", dependencies=[_approve])
def approve_change(cid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: AigovService = Depends(get_aigov)):
    return svc.aig_approve_change(org, cid, actor, body.note)


@router.post("/changes/{cid}/reject", dependencies=[_approve])
def reject_change(cid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: AigovService = Depends(get_aigov)):
    return svc.aig_reject_change(org, cid, body.reason, actor)


@router.get("/incidents")
def incidents(system_id: Optional[str] = None, status: Optional[str] = None, org: str = Depends(get_current_org), svc: AigovService = Depends(get_aigov)): return svc.aig_list_incidents(org, system_id, status)


@router.post("/incidents", status_code=201, dependencies=[_prepare])
def record_incident(body: IncidentBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: AigovService = Depends(get_aigov)):
    return svc.aig_record_incident(org, _d(body), actor)


@router.get("/incidents/{iid}")
def get_incident(iid: str, org: str = Depends(get_current_org), svc: AigovService = Depends(get_aigov)): return svc.aig_get_incident(org, iid)


@router.post("/incidents/{iid}/review", dependencies=[_approve])
def review_incident(iid: str, body: ReviewBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: AigovService = Depends(get_aigov)):
    return svc.aig_review_incident(org, iid, _d(body), actor)


@router.post("/incidents/{iid}/void", dependencies=[_approve])
def void_incident(iid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: AigovService = Depends(get_aigov)):
    return svc.aig_void_incident(org, iid, body.reason, actor)
