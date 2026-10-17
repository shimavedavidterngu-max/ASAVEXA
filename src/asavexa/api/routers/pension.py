"""Pension and fiduciary endpoints (records and evidence). Thin: the rules live in asavexa.pension.

Viewing needs audit:read. Proposing schemes and recording contributions, valuations, obligations and declarations need pension:prepare. Deciding them, closing schemes and the settings need pension:approve; the service refuses the person who recorded the item. Nothing here holds member data, calculates a benefit or applies any pension law.
The organisation always comes from the signed-in session."""
from typing import Any, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...identity.domain.permissions import AUDIT_READ, PEN_APPROVE, PEN_PREPARE
from ...pension.service import PensionService
from ..deps import get_current_actor, get_current_org, get_pension, require_permission

router = APIRouter(prefix="/pension", tags=["Pension and fiduciary"], dependencies=[Depends(require_permission(AUDIT_READ))])
_prepare = Depends(require_permission(PEN_PREPARE))
_approve = Depends(require_permission(PEN_APPROVE))


class CompleteBody(BaseModel):
    completed_on: Optional[str] = None
    note: Optional[str] = None


class ConflictBody(BaseModel):
    person_ref: Optional[str] = None
    declared_on: Optional[str] = None
    nature: Optional[str] = None


class ContributionBody(BaseModel):
    period: Optional[str] = None
    employer_amount: Optional[Any] = None
    employee_amount: Optional[Any] = None
    paid_on: Optional[str] = None


class NoteBody(BaseModel):
    note: Optional[str] = None


class ObligationBody(BaseModel):
    title: Optional[str] = None
    due_date: Optional[str] = None


class ReasonBody(BaseModel):
    reason: str = ""


class SchemeBody(BaseModel):
    name: Optional[str] = None
    scheme_ref: Optional[str] = None
    currency: Optional[str] = None
    scheme_type: Optional[str] = None
    start_period: Optional[str] = None
    due_day: Optional[Any] = None
    description: Optional[str] = None


class SettingBody(BaseModel):
    funding_floor_pct: Optional[Any] = None
    valuation_stale_days: Optional[Any] = None
    due_soon_days: Optional[Any] = None


class ValuationBody(BaseModel):
    as_of: Optional[str] = None
    assets: Optional[Any] = None
    liabilities: Optional[Any] = None
    source_note: Optional[str] = None


def _d(body) -> dict:
    """Only the fields the caller actually sent."""
    return body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)


@router.get("/options")
def options(org: str = Depends(get_current_org), svc: PensionService = Depends(get_pension)):
    return svc.pen_options(org)


@router.get("/overview")
def overview(org: str = Depends(get_current_org), svc: PensionService = Depends(get_pension)):
    return svc.pen_overview(org)


@router.get("/setting")
def setting(org: str = Depends(get_current_org), svc: PensionService = Depends(get_pension)):
    return svc.pen_get_setting(org)


@router.put("/setting", dependencies=[_approve])
def set_setting(body: SettingBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PensionService = Depends(get_pension)):
    return svc.pen_set_setting(org, _d(body), actor)


@router.get("/schemes")
def schemes(status: Optional[str] = None, org: str = Depends(get_current_org), svc: PensionService = Depends(get_pension)):
    return svc.pen_list_schemes(org, status)


@router.post("/schemes", status_code=201, dependencies=[_prepare])
def add_scheme(body: SchemeBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PensionService = Depends(get_pension)):
    return svc.pen_add_scheme(org, _d(body), actor)


@router.get("/schemes/{sid}")
def get_scheme(sid: str, org: str = Depends(get_current_org), svc: PensionService = Depends(get_pension)):
    return svc.pen_get_scheme(org, sid)


@router.post("/schemes/{sid}/approve", dependencies=[_approve])
def approve_scheme(sid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PensionService = Depends(get_pension)):
    return svc.pen_approve_scheme(org, sid, _d(body), actor)


@router.post("/schemes/{sid}/reject", dependencies=[_approve])
def reject_scheme(sid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PensionService = Depends(get_pension)):
    return svc.pen_reject_scheme(org, sid, body.reason, actor)


@router.post("/schemes/{sid}/close", dependencies=[_approve])
def close_scheme(sid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PensionService = Depends(get_pension)):
    return svc.pen_close_scheme(org, sid, body.reason, actor)


@router.post("/schemes/{sid}/contributions", dependencies=[_prepare])
def add_contribution(sid: str, body: ContributionBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PensionService = Depends(get_pension)):
    return svc.pen_add_contribution(org, sid, _d(body), actor)


@router.post("/schemes/{sid}/contributions/{no}/confirm", dependencies=[_approve])
def confirm_contribution(sid: str, no: int, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PensionService = Depends(get_pension)):
    return svc.pen_decide(org, sid, 'contributions', no, True, _d(body), actor)


@router.post("/schemes/{sid}/contributions/{no}/reject", dependencies=[_approve])
def reject_contribution(sid: str, no: int, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PensionService = Depends(get_pension)):
    return svc.pen_decide(org, sid, 'contributions', no, False, body.reason, actor)


@router.post("/schemes/{sid}/valuations", dependencies=[_prepare])
def add_valuation(sid: str, body: ValuationBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PensionService = Depends(get_pension)):
    return svc.pen_add_valuation(org, sid, _d(body), actor)


@router.post("/schemes/{sid}/valuations/{no}/confirm", dependencies=[_approve])
def confirm_valuation(sid: str, no: int, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PensionService = Depends(get_pension)):
    return svc.pen_decide(org, sid, 'valuations', no, True, _d(body), actor)


@router.post("/schemes/{sid}/valuations/{no}/reject", dependencies=[_approve])
def reject_valuation(sid: str, no: int, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PensionService = Depends(get_pension)):
    return svc.pen_decide(org, sid, 'valuations', no, False, body.reason, actor)


@router.post("/schemes/{sid}/obligations", dependencies=[_prepare])
def add_obligation(sid: str, body: ObligationBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PensionService = Depends(get_pension)):
    return svc.pen_add_obligation(org, sid, _d(body), actor)


@router.post("/schemes/{sid}/obligations/{no}/complete", dependencies=[_prepare])
def complete_obligation(sid: str, no: int, body: CompleteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PensionService = Depends(get_pension)):
    return svc.pen_complete_obligation(org, sid, no, _d(body), actor)


@router.post("/schemes/{sid}/obligations/{no}/confirm", dependencies=[_approve])
def confirm_obligation(sid: str, no: int, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PensionService = Depends(get_pension)):
    return svc.pen_decide(org, sid, 'obligations', no, True, _d(body), actor)


@router.post("/schemes/{sid}/obligations/{no}/reject", dependencies=[_approve])
def reject_obligation(sid: str, no: int, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PensionService = Depends(get_pension)):
    return svc.pen_decide(org, sid, 'obligations', no, False, body.reason, actor)


@router.post("/schemes/{sid}/conflicts", dependencies=[_prepare])
def add_conflict(sid: str, body: ConflictBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PensionService = Depends(get_pension)):
    return svc.pen_add_conflict(org, sid, _d(body), actor)


@router.post("/schemes/{sid}/conflicts/{no}/confirm", dependencies=[_approve])
def confirm_conflict(sid: str, no: int, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PensionService = Depends(get_pension)):
    return svc.pen_decide(org, sid, 'conflicts', no, True, _d(body), actor)


@router.post("/schemes/{sid}/conflicts/{no}/reject", dependencies=[_approve])
def reject_conflict(sid: str, no: int, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PensionService = Depends(get_pension)):
    return svc.pen_decide(org, sid, 'conflicts', no, False, body.reason, actor)

