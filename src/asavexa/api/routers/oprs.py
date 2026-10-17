"""Operations research endpoints (records and evidence). Thin: the rules live in asavexa.oprs.

Viewing needs audit:read. Starting analyses, adding and removing options, submitting and withdrawing need oprs:prepare. Approving, returning and recording the decision need oprs:approve; the service refuses the person who submitted the analysis. Nothing here recommends a choice or moves money.
The organisation always comes from the signed-in session."""
from typing import Any, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...identity.domain.permissions import AUDIT_READ, OPR_APPROVE, OPR_PREPARE
from ...oprs.service import OprsService
from ..deps import get_current_actor, get_current_org, get_oprs, require_permission

router = APIRouter(prefix="/oprs", tags=["Operations research"], dependencies=[Depends(require_permission(AUDIT_READ))])
_prepare = Depends(require_permission(OPR_PREPARE))
_approve = Depends(require_permission(OPR_APPROVE))


class AnalysisBody(BaseModel):
    title: Optional[str] = None
    currency: Optional[str] = None
    discount_rate: Optional[Any] = None
    purpose: Optional[str] = None


class DecisionBody(BaseModel):
    option_no: Optional[Any] = None
    rationale: Optional[str] = None


class NoteBody(BaseModel):
    note: Optional[str] = None


class OptionBody(BaseModel):
    name: Optional[str] = None
    upfront_cost: Optional[Any] = None
    flows: Optional[Any] = None


class ReasonBody(BaseModel):
    reason: str = ""


def _d(body) -> dict:
    """Only the fields the caller actually sent."""
    return body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)


@router.get("/options")
def options(org: str = Depends(get_current_org), svc: OprsService = Depends(get_oprs)):
    return svc.op_options(org)


@router.get("/overview")
def overview(org: str = Depends(get_current_org), svc: OprsService = Depends(get_oprs)):
    return svc.op_overview(org)


@router.get("/analyses")
def analyses(status: Optional[str] = None, org: str = Depends(get_current_org), svc: OprsService = Depends(get_oprs)):
    return svc.op_list_analyses(org, status)


@router.post("/analyses", status_code=201, dependencies=[_prepare])
def add_analysis(body: AnalysisBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: OprsService = Depends(get_oprs)):
    return svc.op_create_analysis(org, _d(body), actor)


@router.get("/analyses/{aid}")
def get_analysis(aid: str, org: str = Depends(get_current_org), svc: OprsService = Depends(get_oprs)):
    return svc.op_get_analysis(org, aid)


@router.post("/analyses/{aid}/options", dependencies=[_prepare])
def add_option(aid: str, body: OptionBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: OprsService = Depends(get_oprs)):
    return svc.op_add_option(org, aid, _d(body), actor)


@router.post("/analyses/{aid}/options/{no}/remove", dependencies=[_prepare])
def remove_option(aid: str, no: int, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: OprsService = Depends(get_oprs)):
    return svc.op_remove_option(org, aid, no, body.reason, actor)


@router.post("/analyses/{aid}/submit", dependencies=[_prepare])
def submit_analysis(aid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: OprsService = Depends(get_oprs)):
    return svc.op_submit(org, aid, _d(body), actor)


@router.post("/analyses/{aid}/withdraw", dependencies=[_prepare])
def withdraw_analysis(aid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: OprsService = Depends(get_oprs)):
    return svc.op_withdraw(org, aid, body.reason, actor)


@router.post("/analyses/{aid}/approve", dependencies=[_approve])
def approve_analysis(aid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: OprsService = Depends(get_oprs)):
    return svc.op_approve(org, aid, _d(body), actor)


@router.post("/analyses/{aid}/return", dependencies=[_approve])
def return_analysis(aid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: OprsService = Depends(get_oprs)):
    return svc.op_return(org, aid, body.reason, actor)


@router.post("/analyses/{aid}/decision", dependencies=[_approve])
def record_decision(aid: str, body: DecisionBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: OprsService = Depends(get_oprs)):
    return svc.op_decide(org, aid, _d(body), actor)

