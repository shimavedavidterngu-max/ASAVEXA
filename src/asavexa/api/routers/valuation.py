"""Valuation endpoints (records and evidence): valuation workpapers whose methods are worked out from typed inputs, weights, a concluded value and a review by a different person. Thin: the rules live in asavexa.valuation.

Viewing needs audit:read. Creating workpapers, adding and removing methods, submitting and withdrawing need valuation:prepare. Approving or returning a submitted workpaper and setting the policy need valuation:approve;
the service refuses the person who submitted it. The organisation always comes from the signed-in session. Nothing here reads market data or gives an opinion of value."""
from typing import Any, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...identity.domain.permissions import AUDIT_READ, VAL_APPROVE, VAL_PREPARE
from ...valuation.service import ValuationService
from ..deps import get_current_actor, get_current_org, get_valuation, require_permission

router = APIRouter(prefix="/valuation", tags=["Valuation"], dependencies=[Depends(require_permission(AUDIT_READ))])
_prepare = Depends(require_permission(VAL_PREPARE))
_approve = Depends(require_permission(VAL_APPROVE))


class ReasonBody(BaseModel):
    reason: str = ""


class NoteBody(BaseModel):
    note: Optional[str] = None


class SubmitBody(BaseModel):
    rationale: Optional[str] = None


class PolicyBody(BaseModel):
    review_days: Optional[Any] = None


class CaseBody(BaseModel):
    subject: Optional[str] = None
    subject_kind: Optional[str] = None
    purpose: Optional[str] = None
    basis: Optional[str] = None
    valuation_date: Optional[str] = None
    currency: Optional[str] = None


class MethodBody(BaseModel):
    kind: Optional[str] = None
    label: Optional[str] = None
    weight: Optional[Any] = None
    metric: Optional[Any] = None
    multiple: Optional[Any] = None
    net_debt: Optional[Any] = None
    cash_flows: Optional[List[Any]] = None
    discount_rate: Optional[Any] = None
    terminal_growth: Optional[Any] = None
    total_assets: Optional[Any] = None
    total_liabilities: Optional[Any] = None


def _d(body) -> dict:
    """Only the fields the caller actually sent."""
    return body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)


@router.get("/options")
def options(org: str = Depends(get_current_org), svc: ValuationService = Depends(get_valuation)): return svc.vl_options(org)


@router.get("/overview")
def overview(org: str = Depends(get_current_org), svc: ValuationService = Depends(get_valuation)): return svc.vl_overview(org)


@router.get("/policy")
def policy(org: str = Depends(get_current_org), svc: ValuationService = Depends(get_valuation)): return svc.vl_get_policy(org)


@router.put("/policy", dependencies=[_approve])
def set_policy(body: PolicyBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ValuationService = Depends(get_valuation)):
    return svc.vl_set_policy(org, _d(body), actor)


@router.get("/cases")
def cases(status: Optional[str] = None, org: str = Depends(get_current_org), svc: ValuationService = Depends(get_valuation)): return svc.vl_list_cases(org, status)


@router.post("/cases", status_code=201, dependencies=[_prepare])
def create_case(body: CaseBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ValuationService = Depends(get_valuation)):
    return svc.vl_create_case(org, _d(body), actor)


@router.get("/cases/{cid}")
def get_case(cid: str, org: str = Depends(get_current_org), svc: ValuationService = Depends(get_valuation)): return svc.vl_get_case(org, cid)


@router.get("/cases/{cid}/methods/{no}/sensitivity")
def sensitivity(cid: str, no: int, org: str = Depends(get_current_org), svc: ValuationService = Depends(get_valuation)): return svc.vl_sensitivity(org, cid, no)


@router.post("/cases/{cid}/methods", dependencies=[_prepare])
def add_method(cid: str, body: MethodBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ValuationService = Depends(get_valuation)):
    return svc.vl_add_method(org, cid, _d(body), actor)


@router.post("/cases/{cid}/methods/{no}/remove", dependencies=[_prepare])
def remove_method(cid: str, no: int, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ValuationService = Depends(get_valuation)):
    return svc.vl_remove_method(org, cid, no, body.reason, actor)


@router.post("/cases/{cid}/submit", dependencies=[_prepare])
def submit(cid: str, body: SubmitBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ValuationService = Depends(get_valuation)):
    return svc.vl_submit(org, cid, _d(body), actor)


@router.post("/cases/{cid}/withdraw", dependencies=[_prepare])
def withdraw(cid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ValuationService = Depends(get_valuation)):
    return svc.vl_withdraw_case(org, cid, body.reason, actor)


@router.post("/cases/{cid}/approve", dependencies=[_approve])
def approve(cid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ValuationService = Depends(get_valuation)):
    return svc.vl_approve_case(org, cid, _d(body), actor)


@router.post("/cases/{cid}/return", dependencies=[_approve])
def return_case(cid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ValuationService = Depends(get_valuation)):
    return svc.vl_return_case(org, cid, body.reason, actor)
