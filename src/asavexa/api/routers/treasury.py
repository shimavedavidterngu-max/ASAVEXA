"""Treasury endpoints (records and evidence; no bank connection, no money moves). Thin: the rules live in asavexa.treasury.

Viewing needs reporting:read (the same as the ledger and the other finance workspaces). Recording accounts, balances, expected cash flows, payment requests, covenants and covenant results, and recording a payment as released,
need treasury:prepare. Approving or rejecting a payment, confirming a balance, acknowledging a covenant breach and setting the policy need treasury:approve; the
service refuses the person who recorded or asked for the thing being decided. The organisation always comes from the signed-in session."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...identity.domain.permissions import REPORTING_READ, TREASURY_APPROVE, TREASURY_PREPARE
from ...treasury.service import TreasuryService
from ..deps import get_current_actor, get_current_org, get_treasury, require_permission

router = APIRouter(prefix="/treasury", tags=["Treasury"], dependencies=[Depends(require_permission(REPORTING_READ))])
_prepare = Depends(require_permission(TREASURY_PREPARE))
_approve = Depends(require_permission(TREASURY_APPROVE))


class AccountBody(BaseModel):
    name: Optional[str] = None
    bank_name: Optional[str] = None
    currency: Optional[str] = None
    last4: Optional[str] = None
    purpose: Optional[str] = None


class NoteBody(BaseModel):
    note: str = ""


class BalanceBody(BaseModel):
    as_at: Optional[str] = None
    amount: Optional[Any] = None
    source: Optional[str] = None
    evidence_ids: List[str] = []


class FlowBody(BaseModel):
    direction: Optional[str] = None
    flow_date: Optional[str] = None
    amount: Optional[Any] = None
    currency: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    certainty: Optional[str] = None
    account_id: Optional[str] = None


class FlowChangeBody(BaseModel):
    flow_date: Optional[str] = None
    amount: Optional[Any] = None
    certainty: Optional[str] = None
    description: Optional[str] = None
    note: str = ""


class RealiseBody(BaseModel):
    actual_amount: Optional[Any] = None
    actual_date: Optional[str] = None


class PaymentBody(BaseModel):
    account_id: Optional[str] = None
    payee: Optional[str] = None
    amount: Optional[Any] = None
    due_date: Optional[str] = None
    reason: Optional[str] = None
    invoice_ref: Optional[str] = None
    flow_id: Optional[str] = None
    evidence_ids: List[str] = []


class ReleaseBody(BaseModel):
    released_date: Optional[str] = None
    bank_reference: Optional[str] = None


class CovenantBody(BaseModel):
    name: Optional[str] = None
    lender: Optional[str] = None
    description: Optional[str] = None
    comparator: Optional[str] = None
    threshold: Optional[Any] = None
    unit: Optional[str] = None
    currency: Optional[str] = None
    frequency: Optional[str] = None
    watch_pct: Optional[Any] = None
    effective_from: Optional[str] = None


class ResultBody(BaseModel):
    period_end: Optional[str] = None
    value: Optional[Any] = None
    source: Optional[str] = None
    note: str = ""


class AckBody(BaseModel):
    waiver_obtained: Optional[bool] = None
    note: str = ""


class PolicyBody(BaseModel):
    minimum_cash: Optional[Dict[str, Any]] = None
    dual_limits: Optional[Dict[str, Any]] = None
    stale_days: Optional[int] = None


def _d(body) -> dict:
    """Only the fields the caller actually sent."""
    return body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)


@router.get("/options")
def options(org: str = Depends(get_current_org), svc: TreasuryService = Depends(get_treasury)): return svc.treasury_options(org)


@router.get("/overview")
def overview(org: str = Depends(get_current_org), svc: TreasuryService = Depends(get_treasury)): return svc.treasury_overview(org)


@router.get("/policy")
def policy(org: str = Depends(get_current_org), svc: TreasuryService = Depends(get_treasury)): return svc.get_treasury_policy(org)


@router.put("/policy", dependencies=[_approve])
def set_policy(body: PolicyBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: TreasuryService = Depends(get_treasury)):
    return svc.set_treasury_policy(org, _d(body), actor)


@router.get("/position")
def position(org: str = Depends(get_current_org), svc: TreasuryService = Depends(get_treasury)): return svc.cash_position(org)


@router.get("/forecast")
def forecast(weeks: int = 13, include_possible: bool = False, org: str = Depends(get_current_org), svc: TreasuryService = Depends(get_treasury)):
    return svc.liquidity_forecast(org, weeks, include_possible)


@router.get("/forecast-accuracy")
def accuracy(org: str = Depends(get_current_org), svc: TreasuryService = Depends(get_treasury)): return svc.forecast_accuracy(org)


@router.get("/accounts")
def accounts(org: str = Depends(get_current_org), svc: TreasuryService = Depends(get_treasury)): return svc.list_cash_accounts(org)


@router.post("/accounts", status_code=201, dependencies=[_prepare])
def open_account(body: AccountBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: TreasuryService = Depends(get_treasury)):
    return svc.open_cash_account(org, _d(body), actor)


@router.get("/accounts/{aid}")
def get_account(aid: str, org: str = Depends(get_current_org), svc: TreasuryService = Depends(get_treasury)): return svc.get_cash_account(org, aid)


@router.post("/accounts/{aid}/close", dependencies=[_prepare])
def close_account(aid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: TreasuryService = Depends(get_treasury)):
    return svc.close_cash_account(org, aid, body.note, actor)


@router.post("/accounts/{aid}/balances", status_code=201, dependencies=[_prepare])
def add_balance(aid: str, body: BalanceBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: TreasuryService = Depends(get_treasury)):
    return svc.record_balance(org, aid, _d(body), actor)


@router.post("/accounts/{aid}/balances/{bid}/confirm", dependencies=[_approve])
def confirm_balance(aid: str, bid: str, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: TreasuryService = Depends(get_treasury)):
    return svc.confirm_balance(org, aid, bid, actor)


@router.get("/flows")
def flows(status: Optional[str] = None, currency: Optional[str] = None, org: str = Depends(get_current_org), svc: TreasuryService = Depends(get_treasury)):
    return svc.list_cash_flows(org, status, currency)


@router.post("/flows", status_code=201, dependencies=[_prepare])
def add_flow(body: FlowBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: TreasuryService = Depends(get_treasury)):
    return svc.add_cash_flow(org, _d(body), actor)


@router.get("/flows/{fid}")
def get_flow(fid: str, org: str = Depends(get_current_org), svc: TreasuryService = Depends(get_treasury)): return svc.get_cash_flow(org, fid)


@router.put("/flows/{fid}", dependencies=[_prepare])
def change_flow(fid: str, body: FlowChangeBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: TreasuryService = Depends(get_treasury)):
    return svc.change_cash_flow(org, fid, _d(body), actor)


@router.post("/flows/{fid}/realise", dependencies=[_prepare])
def realise_flow(fid: str, body: RealiseBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: TreasuryService = Depends(get_treasury)):
    return svc.realise_cash_flow(org, fid, _d(body), actor)


@router.post("/flows/{fid}/cancel", dependencies=[_prepare])
def cancel_flow(fid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: TreasuryService = Depends(get_treasury)):
    return svc.cancel_cash_flow(org, fid, body.note, actor)


@router.get("/payments")
def payments(status: Optional[str] = None, org: str = Depends(get_current_org), svc: TreasuryService = Depends(get_treasury)): return svc.list_payment_requests(org, status)


@router.post("/payments", status_code=201, dependencies=[_prepare])
def request_payment(body: PaymentBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: TreasuryService = Depends(get_treasury)):
    return svc.request_payment(org, _d(body), actor)


@router.get("/payments/{pid}")
def get_payment(pid: str, org: str = Depends(get_current_org), svc: TreasuryService = Depends(get_treasury)): return svc.get_payment_request(org, pid)


@router.post("/payments/{pid}/approve", dependencies=[_approve])
def approve_payment(pid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: TreasuryService = Depends(get_treasury)):
    return svc.approve_payment(org, pid, actor, body.note)


@router.post("/payments/{pid}/reject", dependencies=[_approve])
def reject_payment(pid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: TreasuryService = Depends(get_treasury)):
    return svc.reject_payment(org, pid, actor, body.note)


@router.post("/payments/{pid}/cancel", dependencies=[_prepare])
def cancel_payment(pid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: TreasuryService = Depends(get_treasury)):
    return svc.cancel_payment(org, pid, actor, body.note)


@router.post("/payments/{pid}/release", dependencies=[_prepare])
def release_payment(pid: str, body: ReleaseBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: TreasuryService = Depends(get_treasury)):
    return svc.release_payment(org, pid, _d(body), actor)


@router.get("/covenants")
def covenants(org: str = Depends(get_current_org), svc: TreasuryService = Depends(get_treasury)): return svc.list_covenants(org)


@router.post("/covenants", status_code=201, dependencies=[_prepare])
def add_covenant(body: CovenantBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: TreasuryService = Depends(get_treasury)):
    return svc.add_covenant(org, _d(body), actor)


@router.get("/covenants/{cid}")
def get_covenant(cid: str, org: str = Depends(get_current_org), svc: TreasuryService = Depends(get_treasury)): return svc.get_covenant(org, cid)


@router.post("/covenants/{cid}/retire", dependencies=[_prepare])
def retire_covenant(cid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: TreasuryService = Depends(get_treasury)):
    return svc.retire_covenant(org, cid, body.note, actor)


@router.post("/covenants/{cid}/results", status_code=201, dependencies=[_prepare])
def add_result(cid: str, body: ResultBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: TreasuryService = Depends(get_treasury)):
    return svc.record_covenant_result(org, cid, _d(body), actor)


@router.post("/covenants/{cid}/results/{rid}/acknowledge", dependencies=[_approve])
def acknowledge(cid: str, rid: str, body: AckBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: TreasuryService = Depends(get_treasury)):
    return svc.acknowledge_covenant_breach(org, cid, rid, _d(body), actor)
