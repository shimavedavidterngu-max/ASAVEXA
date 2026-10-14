"""Quality management endpoints (records and evidence): nonconformances and corrective actions. Thin: the rules live in asavexa.quality.

Viewing needs audit:read. Raising and analysing nonconformances and adding and completing actions need quality:prepare. Checking an action's effectiveness, cancelling an action,
closing or voiding a nonconformance and setting the policy need quality:approve; the service refuses the person whose work is being decided.
The organisation always comes from the signed-in session. Nothing here inspects or measures anything."""
from typing import Any, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...identity.domain.permissions import AUDIT_READ, QUAL_APPROVE, QUAL_PREPARE
from ...quality.service import QualityService
from ..deps import get_current_actor, get_current_org, get_quality, require_permission

router = APIRouter(prefix="/quality", tags=["Quality management"], dependencies=[Depends(require_permission(AUDIT_READ))])
_prepare = Depends(require_permission(QUAL_PREPARE))
_approve = Depends(require_permission(QUAL_APPROVE))


class ReasonBody(BaseModel):
    reason: str = ""


class PolicyBody(BaseModel):
    verify_days: Optional[Any] = None


class NcBody(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    source: Optional[str] = None
    severity: Optional[str] = None
    area: Optional[str] = None
    occurred_on: Optional[str] = None
    discovered_on: Optional[str] = None
    evidence_ids: List[str] = []


class AnalyseBody(BaseModel):
    root_cause: Optional[str] = None
    containment: Optional[str] = None


class CloseBody(BaseModel):
    note: Optional[str] = None
    no_action_reason: Optional[str] = None


class ActionBody(BaseModel):
    nc_id: Optional[str] = None
    kind: Optional[str] = None
    description: Optional[str] = None
    owner_name: Optional[str] = None
    due_on: Optional[str] = None


class CompleteBody(BaseModel):
    completed_on: Optional[str] = None
    note: Optional[str] = None
    evidence_ids: List[str] = []


class VerifyBody(BaseModel):
    result: Optional[str] = None
    note: Optional[str] = None


def _d(body) -> dict:
    """Only the fields the caller actually sent."""
    return body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)


@router.get("/options")
def options(org: str = Depends(get_current_org), svc: QualityService = Depends(get_quality)): return svc.ql_options(org)


@router.get("/overview")
def overview(org: str = Depends(get_current_org), svc: QualityService = Depends(get_quality)): return svc.ql_overview(org)


@router.get("/policy")
def policy(org: str = Depends(get_current_org), svc: QualityService = Depends(get_quality)): return svc.ql_get_policy(org)


@router.put("/policy", dependencies=[_approve])
def set_policy(body: PolicyBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: QualityService = Depends(get_quality)):
    return svc.ql_set_policy(org, _d(body), actor)


@router.get("/ncs")
def ncs(status: Optional[str] = None, severity: Optional[str] = None, org: str = Depends(get_current_org), svc: QualityService = Depends(get_quality)): return svc.ql_list_ncs(org, status, severity)


@router.post("/ncs", status_code=201, dependencies=[_prepare])
def raise_nc(body: NcBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: QualityService = Depends(get_quality)):
    return svc.ql_raise_nc(org, _d(body), actor)


@router.get("/ncs/{nid}")
def get_nc(nid: str, org: str = Depends(get_current_org), svc: QualityService = Depends(get_quality)): return svc.ql_get_nc(org, nid)


@router.post("/ncs/{nid}/analyse", dependencies=[_prepare])
def analyse_nc(nid: str, body: AnalyseBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: QualityService = Depends(get_quality)):
    return svc.ql_analyse_nc(org, nid, _d(body), actor)


@router.post("/ncs/{nid}/close", dependencies=[_approve])
def close_nc(nid: str, body: CloseBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: QualityService = Depends(get_quality)):
    return svc.ql_close_nc(org, nid, _d(body), actor)


@router.post("/ncs/{nid}/void", dependencies=[_approve])
def void_nc(nid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: QualityService = Depends(get_quality)):
    return svc.ql_void_nc(org, nid, body.reason, actor)


@router.get("/actions")
def actions(nc_id: Optional[str] = None, status: Optional[str] = None, org: str = Depends(get_current_org), svc: QualityService = Depends(get_quality)): return svc.ql_list_actions(org, nc_id, status)


@router.post("/actions", status_code=201, dependencies=[_prepare])
def add_action(body: ActionBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: QualityService = Depends(get_quality)):
    return svc.ql_add_action(org, _d(body), actor)


@router.get("/actions/{aid}")
def get_action(aid: str, org: str = Depends(get_current_org), svc: QualityService = Depends(get_quality)): return svc.ql_get_action(org, aid)


@router.post("/actions/{aid}/complete", dependencies=[_prepare])
def complete_action(aid: str, body: CompleteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: QualityService = Depends(get_quality)):
    return svc.ql_complete_action(org, aid, _d(body), actor)


@router.post("/actions/{aid}/verify", dependencies=[_approve])
def verify_action(aid: str, body: VerifyBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: QualityService = Depends(get_quality)):
    return svc.ql_verify_action(org, aid, _d(body), actor)


@router.post("/actions/{aid}/cancel", dependencies=[_approve])
def cancel_action(aid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: QualityService = Depends(get_quality)):
    return svc.ql_cancel_action(org, aid, body.reason, actor)
