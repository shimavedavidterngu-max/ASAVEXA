"""Investments endpoints (records and evidence): holdings, typed purchases, sales approved by a different person, typed price marks and gain or loss arithmetic. Thin: the rules live in asavexa.investments.

Viewing needs audit:read. Adding holdings, recording purchases and prices and proposing sales need investments:prepare. Closing holdings, approving or rejecting sales and setting the policy need investments:approve;
the service refuses the person whose work is being decided. The organisation always comes from the signed-in session. Nothing here reads market data, gives advice or posts to a ledger."""
from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...identity.domain.permissions import AUDIT_READ, INVEST_APPROVE, INVEST_PREPARE
from ...investments.service import InvestmentsService
from ..deps import get_current_actor, get_current_org, get_investments, require_permission

router = APIRouter(prefix="/investments", tags=["Investments"], dependencies=[Depends(require_permission(AUDIT_READ))])
_prepare = Depends(require_permission(INVEST_PREPARE))
_approve = Depends(require_permission(INVEST_APPROVE))


class ReasonBody(BaseModel):
    reason: str = ""


class NoteBody(BaseModel):
    note: Optional[str] = None


class PolicyBody(BaseModel):
    stale_days: Optional[Any] = None


class HoldingBody(BaseModel):
    name: Optional[str] = None
    identifier: Optional[str] = None
    asset_class: Optional[str] = None
    currency: Optional[str] = None
    account: Optional[str] = None


class TradeBody(BaseModel):
    units: Optional[Any] = None
    price: Optional[Any] = None
    fee: Optional[Any] = None
    traded_on: Optional[str] = None
    reference: Optional[str] = None


class MarkBody(BaseModel):
    price: Optional[Any] = None
    as_of: Optional[str] = None
    source: Optional[str] = None


def _d(body) -> dict:
    """Only the fields the caller actually sent."""
    return body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)


@router.get("/options")
def options(org: str = Depends(get_current_org), svc: InvestmentsService = Depends(get_investments)): return svc.im_options(org)


@router.get("/overview")
def overview(org: str = Depends(get_current_org), svc: InvestmentsService = Depends(get_investments)): return svc.im_overview(org)


@router.get("/policy")
def policy(org: str = Depends(get_current_org), svc: InvestmentsService = Depends(get_investments)): return svc.im_get_policy(org)


@router.put("/policy", dependencies=[_approve])
def set_policy(body: PolicyBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: InvestmentsService = Depends(get_investments)):
    return svc.im_set_policy(org, _d(body), actor)


@router.get("/holdings")
def holdings(status: Optional[str] = None, org: str = Depends(get_current_org), svc: InvestmentsService = Depends(get_investments)): return svc.im_list_holdings(org, status)


@router.post("/holdings", status_code=201, dependencies=[_prepare])
def add_holding(body: HoldingBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: InvestmentsService = Depends(get_investments)):
    return svc.im_add_holding(org, _d(body), actor)


@router.get("/holdings/{hid}")
def get_holding(hid: str, org: str = Depends(get_current_org), svc: InvestmentsService = Depends(get_investments)): return svc.im_get_holding(org, hid)


@router.post("/holdings/{hid}/close", dependencies=[_approve])
def close_holding(hid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: InvestmentsService = Depends(get_investments)):
    return svc.im_close_holding(org, hid, body.reason, actor)


@router.post("/holdings/{hid}/buy", dependencies=[_prepare])
def buy(hid: str, body: TradeBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: InvestmentsService = Depends(get_investments)):
    return svc.im_buy(org, hid, _d(body), actor)


@router.post("/holdings/{hid}/sells", dependencies=[_prepare])
def propose_sell(hid: str, body: TradeBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: InvestmentsService = Depends(get_investments)):
    return svc.im_propose_sell(org, hid, _d(body), actor)


@router.post("/holdings/{hid}/sells/{no}/approve", dependencies=[_approve])
def approve_sell(hid: str, no: int, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: InvestmentsService = Depends(get_investments)):
    return svc.im_approve_sell(org, hid, no, _d(body), actor)


@router.post("/holdings/{hid}/sells/{no}/reject", dependencies=[_approve])
def reject_sell(hid: str, no: int, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: InvestmentsService = Depends(get_investments)):
    return svc.im_reject_sell(org, hid, no, body.reason, actor)


@router.post("/holdings/{hid}/marks", dependencies=[_prepare])
def record_mark(hid: str, body: MarkBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: InvestmentsService = Depends(get_investments)):
    return svc.im_record_mark(org, hid, _d(body), actor)
