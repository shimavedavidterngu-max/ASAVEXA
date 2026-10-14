"""Risk indicators and resilience endpoints (records and evidence): key risk indicators and readings, loss events, business processes (impact analysis), continuity tests.
Thin: the rules live in asavexa.resilience.

Viewing needs audit:read. Proposing indicators and processes and recording readings, loss events and tests need resilience:prepare. Approving, rejecting, retiring,
confirming, reviewing, voiding and setting the policy need resilience:approve; the service refuses the person whose work is being decided.
The organisation always comes from the signed-in session. Nothing here measures or connects to any system."""
from typing import Any, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...identity.domain.permissions import AUDIT_READ, RESIL_APPROVE, RESIL_PREPARE
from ...resilience.service import ResilienceService
from ..deps import get_current_actor, get_current_org, get_resilience, require_permission

router = APIRouter(prefix="/resilience", tags=["Risk indicators and resilience"], dependencies=[Depends(require_permission(AUDIT_READ))])
_prepare = Depends(require_permission(RESIL_PREPARE))
_approve = Depends(require_permission(RESIL_APPROVE))


class ReasonBody(BaseModel):
    reason: str = ""


class NoteBody(BaseModel):
    note: str = ""


class PolicyBody(BaseModel):
    drill_days: Optional[Any] = None
    loss_review_days: Optional[Any] = None


class KriBody(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    unit: Optional[str] = None
    direction: Optional[str] = None
    amber: Optional[Any] = None
    red: Optional[Any] = None
    owner_name: Optional[str] = None
    review_days: Optional[Any] = None
    risk_id: Optional[str] = None


class ReadingBody(BaseModel):
    value: Optional[Any] = None
    as_of: Optional[str] = None
    note: Optional[str] = None


class LossBody(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    kind: Optional[str] = None
    occurred_on: Optional[str] = None
    discovered_on: Optional[str] = None
    amount: Optional[Any] = None
    currency: Optional[str] = None
    risk_id: Optional[str] = None
    evidence_ids: List[str] = []


class ReviewBody(BaseModel):
    cause: Optional[str] = None
    lesson: Optional[str] = None


class ProcessBody(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    owner_name: Optional[str] = None
    rto_hours: Optional[Any] = None
    rpo_hours: Optional[Any] = None
    impact_financial: Optional[str] = None
    impact_legal: Optional[str] = None
    impact_reputation: Optional[str] = None
    dependencies: Optional[str] = None


class DrillBody(BaseModel):
    process_id: Optional[str] = None
    drill_type: Optional[str] = None
    scenario: Optional[str] = None
    performed_on: Optional[str] = None
    achieved_recovery_hours: Optional[Any] = None
    achieved_data_loss_hours: Optional[Any] = None
    outcome: Optional[str] = None
    follow_up: Optional[str] = None
    evidence_ids: List[str] = []


def _d(body) -> dict:
    """Only the fields the caller actually sent."""
    return body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)


@router.get("/options")
def options(org: str = Depends(get_current_org), svc: ResilienceService = Depends(get_resilience)): return svc.rs_options(org)


@router.get("/overview")
def overview(org: str = Depends(get_current_org), svc: ResilienceService = Depends(get_resilience)): return svc.rs_overview(org)


@router.get("/policy")
def policy(org: str = Depends(get_current_org), svc: ResilienceService = Depends(get_resilience)): return svc.rs_get_policy(org)


@router.put("/policy", dependencies=[_approve])
def set_policy(body: PolicyBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ResilienceService = Depends(get_resilience)):
    return svc.rs_set_policy(org, _d(body), actor)


@router.get("/kris")
def kris(status: Optional[str] = None, org: str = Depends(get_current_org), svc: ResilienceService = Depends(get_resilience)): return svc.rs_list_kris(org, status)


@router.post("/kris", status_code=201, dependencies=[_prepare])
def propose_kri(body: KriBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ResilienceService = Depends(get_resilience)):
    return svc.rs_propose_kri(org, _d(body), actor)


@router.get("/kris/{kid}")
def get_kri(kid: str, org: str = Depends(get_current_org), svc: ResilienceService = Depends(get_resilience)): return svc.rs_get_kri(org, kid)


@router.post("/kris/{kid}/approve", dependencies=[_approve])
def approve_kri(kid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ResilienceService = Depends(get_resilience)):
    return svc.rs_approve_kri(org, kid, actor, body.note)


@router.post("/kris/{kid}/reject", dependencies=[_approve])
def reject_kri(kid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ResilienceService = Depends(get_resilience)):
    return svc.rs_reject_kri(org, kid, body.reason, actor)


@router.post("/kris/{kid}/retire", dependencies=[_approve])
def retire_kri(kid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ResilienceService = Depends(get_resilience)):
    return svc.rs_retire_kri(org, kid, body.reason, actor)


@router.post("/kris/{kid}/readings", status_code=201, dependencies=[_prepare])
def record_reading(kid: str, body: ReadingBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ResilienceService = Depends(get_resilience)):
    return svc.rs_record_reading(org, kid, _d(body), actor)


@router.post("/kris/{kid}/readings/{rid}/confirm", dependencies=[_approve])
def confirm_reading(kid: str, rid: str, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ResilienceService = Depends(get_resilience)):
    return svc.rs_confirm_reading(org, kid, rid, actor)


@router.post("/kris/{kid}/readings/{rid}/reject", dependencies=[_approve])
def reject_reading(kid: str, rid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ResilienceService = Depends(get_resilience)):
    return svc.rs_reject_reading(org, kid, rid, body.reason, actor)


@router.get("/losses")
def losses(status: Optional[str] = None, kind: Optional[str] = None, org: str = Depends(get_current_org), svc: ResilienceService = Depends(get_resilience)): return svc.rs_list_losses(org, status, kind)


@router.post("/losses", status_code=201, dependencies=[_prepare])
def record_loss(body: LossBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ResilienceService = Depends(get_resilience)):
    return svc.rs_record_loss(org, _d(body), actor)


@router.get("/losses/{lid}")
def get_loss(lid: str, org: str = Depends(get_current_org), svc: ResilienceService = Depends(get_resilience)): return svc.rs_get_loss(org, lid)


@router.post("/losses/{lid}/review", dependencies=[_approve])
def review_loss(lid: str, body: ReviewBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ResilienceService = Depends(get_resilience)):
    return svc.rs_review_loss(org, lid, _d(body), actor)


@router.post("/losses/{lid}/void", dependencies=[_approve])
def void_loss(lid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ResilienceService = Depends(get_resilience)):
    return svc.rs_void_loss(org, lid, body.reason, actor)


@router.get("/processes")
def processes(status: Optional[str] = None, org: str = Depends(get_current_org), svc: ResilienceService = Depends(get_resilience)): return svc.rs_list_processes(org, status)


@router.post("/processes", status_code=201, dependencies=[_prepare])
def propose_process(body: ProcessBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ResilienceService = Depends(get_resilience)):
    return svc.rs_propose_process(org, _d(body), actor)


@router.get("/processes/{pid}")
def get_process(pid: str, org: str = Depends(get_current_org), svc: ResilienceService = Depends(get_resilience)): return svc.rs_get_process(org, pid)


@router.post("/processes/{pid}/approve", dependencies=[_approve])
def approve_process(pid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ResilienceService = Depends(get_resilience)):
    return svc.rs_approve_process(org, pid, actor, body.note)


@router.post("/processes/{pid}/reject", dependencies=[_approve])
def reject_process(pid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ResilienceService = Depends(get_resilience)):
    return svc.rs_reject_process(org, pid, body.reason, actor)


@router.post("/processes/{pid}/retire", dependencies=[_approve])
def retire_process(pid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ResilienceService = Depends(get_resilience)):
    return svc.rs_retire_process(org, pid, body.reason, actor)


@router.get("/drills")
def drills(process_id: Optional[str] = None, status: Optional[str] = None, org: str = Depends(get_current_org), svc: ResilienceService = Depends(get_resilience)): return svc.rs_list_drills(org, process_id, status)


@router.post("/drills", status_code=201, dependencies=[_prepare])
def record_drill(body: DrillBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ResilienceService = Depends(get_resilience)):
    return svc.rs_record_drill(org, _d(body), actor)


@router.get("/drills/{did}")
def get_drill(did: str, org: str = Depends(get_current_org), svc: ResilienceService = Depends(get_resilience)): return svc.rs_get_drill(org, did)


@router.post("/drills/{did}/approve", dependencies=[_approve])
def approve_drill(did: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ResilienceService = Depends(get_resilience)):
    return svc.rs_approve_drill(org, did, actor, body.note)


@router.post("/drills/{did}/reject", dependencies=[_approve])
def reject_drill(did: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ResilienceService = Depends(get_resilience)):
    return svc.rs_reject_drill(org, did, body.reason, actor)
