"""Franchise and multi-location endpoints (records and evidence). Thin: the rules live in asavexa.franchise.

Viewing needs audit:read. Proposing locations and recording sales reports and payments need franchise:prepare. Deciding them, closing locations and the settings need franchise:approve; the service refuses the person who recorded the item. Nothing here reads a franchise agreement, collects money or applies franchise law.
The organisation always comes from the signed-in session."""
from typing import Any, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...identity.domain.permissions import AUDIT_READ, FCH_APPROVE, FCH_PREPARE
from ...franchise.service import FranchiseService
from ..deps import get_current_actor, get_current_org, get_franchise, require_permission

router = APIRouter(prefix="/franchise", tags=["Franchise and multi-location"], dependencies=[Depends(require_permission(AUDIT_READ))])
_prepare = Depends(require_permission(FCH_PREPARE))
_approve = Depends(require_permission(FCH_APPROVE))


class LocationBody(BaseModel):
    name: Optional[str] = None
    location_ref: Optional[str] = None
    currency: Optional[str] = None
    royalty_rate_pct: Optional[Any] = None
    due_day: Optional[Any] = None
    start_period: Optional[str] = None
    description: Optional[str] = None


class NoteBody(BaseModel):
    note: Optional[str] = None


class PaymentBody(BaseModel):
    amount: Optional[Any] = None
    paid_on: Optional[str] = None
    note: Optional[str] = None


class ReasonBody(BaseModel):
    reason: str = ""


class ReportBody(BaseModel):
    period: Optional[str] = None
    gross_sales: Optional[Any] = None
    submitted_on: Optional[str] = None


class SettingBody(BaseModel):
    grace_days: Optional[Any] = None


def _d(body) -> dict:
    """Only the fields the caller actually sent."""
    return body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)


@router.get("/options")
def options(org: str = Depends(get_current_org), svc: FranchiseService = Depends(get_franchise)):
    return svc.fch_options(org)


@router.get("/overview")
def overview(org: str = Depends(get_current_org), svc: FranchiseService = Depends(get_franchise)):
    return svc.fch_overview(org)


@router.get("/setting")
def setting(org: str = Depends(get_current_org), svc: FranchiseService = Depends(get_franchise)):
    return svc.fch_get_setting(org)


@router.put("/setting", dependencies=[_approve])
def set_setting(body: SettingBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FranchiseService = Depends(get_franchise)):
    return svc.fch_set_setting(org, _d(body), actor)


@router.get("/locations")
def locations(status: Optional[str] = None, org: str = Depends(get_current_org), svc: FranchiseService = Depends(get_franchise)):
    return svc.fch_list_locations(org, status)


@router.post("/locations", status_code=201, dependencies=[_prepare])
def add_location(body: LocationBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FranchiseService = Depends(get_franchise)):
    return svc.fch_add_location(org, _d(body), actor)


@router.get("/locations/{lid}")
def get_location(lid: str, org: str = Depends(get_current_org), svc: FranchiseService = Depends(get_franchise)):
    return svc.fch_get_location(org, lid)


@router.post("/locations/{lid}/approve", dependencies=[_approve])
def approve_location(lid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FranchiseService = Depends(get_franchise)):
    return svc.fch_approve_location(org, lid, _d(body), actor)


@router.post("/locations/{lid}/reject", dependencies=[_approve])
def reject_location(lid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FranchiseService = Depends(get_franchise)):
    return svc.fch_reject_location(org, lid, body.reason, actor)


@router.post("/locations/{lid}/close", dependencies=[_approve])
def close_location(lid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FranchiseService = Depends(get_franchise)):
    return svc.fch_close_location(org, lid, body.reason, actor)


@router.post("/locations/{lid}/reports", dependencies=[_prepare])
def add_report(lid: str, body: ReportBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FranchiseService = Depends(get_franchise)):
    return svc.fch_add_report(org, lid, _d(body), actor)


@router.post("/locations/{lid}/reports/{no}/confirm", dependencies=[_approve])
def confirm_report(lid: str, no: int, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FranchiseService = Depends(get_franchise)):
    return svc.fch_decide(org, lid, 'reports', no, True, _d(body), actor)


@router.post("/locations/{lid}/reports/{no}/reject", dependencies=[_approve])
def reject_report(lid: str, no: int, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FranchiseService = Depends(get_franchise)):
    return svc.fch_decide(org, lid, 'reports', no, False, body.reason, actor)


@router.post("/locations/{lid}/payments", dependencies=[_prepare])
def add_payment(lid: str, body: PaymentBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FranchiseService = Depends(get_franchise)):
    return svc.fch_add_payment(org, lid, _d(body), actor)


@router.post("/locations/{lid}/payments/{no}/confirm", dependencies=[_approve])
def confirm_payment(lid: str, no: int, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FranchiseService = Depends(get_franchise)):
    return svc.fch_decide(org, lid, 'payments', no, True, _d(body), actor)


@router.post("/locations/{lid}/payments/{no}/reject", dependencies=[_approve])
def reject_payment(lid: str, no: int, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FranchiseService = Depends(get_franchise)):
    return svc.fch_decide(org, lid, 'payments', no, False, body.reason, actor)

