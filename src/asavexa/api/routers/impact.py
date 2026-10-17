"""Impact measurement endpoints (records and evidence). Thin: the rules live in asavexa.impact.

Viewing needs audit:read. Proposing indicators and recording readings need impact:prepare. Deciding them, closing indicators and the settings need impact:approve; the service refuses the person who proposed the item. Nothing here collects data or checks a result against the real world.
The organisation always comes from the signed-in session."""
from typing import Any, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...identity.domain.permissions import AUDIT_READ, IMP_APPROVE, IMP_PREPARE
from ...impact.service import ImpactService
from ..deps import get_current_actor, get_current_org, get_impact, require_permission

router = APIRouter(prefix="/impact", tags=["Impact measurement"], dependencies=[Depends(require_permission(AUDIT_READ))])
_prepare = Depends(require_permission(IMP_PREPARE))
_approve = Depends(require_permission(IMP_APPROVE))


class IndicatorBody(BaseModel):
    title: Optional[str] = None
    programme_ref: Optional[str] = None
    unit: Optional[str] = None
    direction: Optional[str] = None
    baseline: Optional[Any] = None
    target: Optional[Any] = None
    baseline_date: Optional[str] = None
    target_date: Optional[str] = None


class NoteBody(BaseModel):
    note: Optional[str] = None


class ReadingBody(BaseModel):
    period_end: Optional[str] = None
    value: Optional[Any] = None
    source_note: Optional[str] = None


class ReasonBody(BaseModel):
    reason: str = ""


class SettingBody(BaseModel):
    tolerance_points: Optional[Any] = None
    stale_days: Optional[Any] = None


def _d(body) -> dict:
    """Only the fields the caller actually sent."""
    return body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)


@router.get("/options")
def options(org: str = Depends(get_current_org), svc: ImpactService = Depends(get_impact)):
    return svc.imp_options(org)


@router.get("/overview")
def overview(org: str = Depends(get_current_org), svc: ImpactService = Depends(get_impact)):
    return svc.imp_overview(org)


@router.get("/setting")
def setting(org: str = Depends(get_current_org), svc: ImpactService = Depends(get_impact)):
    return svc.imp_get_setting(org)


@router.put("/setting", dependencies=[_approve])
def set_setting(body: SettingBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ImpactService = Depends(get_impact)):
    return svc.imp_set_setting(org, _d(body), actor)


@router.get("/indicators")
def indicators(status: Optional[str] = None, org: str = Depends(get_current_org), svc: ImpactService = Depends(get_impact)):
    return svc.imp_list_indicators(org, status)


@router.post("/indicators", status_code=201, dependencies=[_prepare])
def add_indicator(body: IndicatorBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ImpactService = Depends(get_impact)):
    return svc.imp_add_indicator(org, _d(body), actor)


@router.get("/indicators/{iid}")
def get_indicator(iid: str, org: str = Depends(get_current_org), svc: ImpactService = Depends(get_impact)):
    return svc.imp_get_indicator(org, iid)


@router.post("/indicators/{iid}/approve", dependencies=[_approve])
def approve_indicator(iid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ImpactService = Depends(get_impact)):
    return svc.imp_approve_indicator(org, iid, _d(body), actor)


@router.post("/indicators/{iid}/reject", dependencies=[_approve])
def reject_indicator(iid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ImpactService = Depends(get_impact)):
    return svc.imp_reject_indicator(org, iid, body.reason, actor)


@router.post("/indicators/{iid}/close", dependencies=[_approve])
def close_indicator(iid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ImpactService = Depends(get_impact)):
    return svc.imp_close_indicator(org, iid, body.reason, actor)


@router.post("/indicators/{iid}/readings", dependencies=[_prepare])
def add_reading(iid: str, body: ReadingBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ImpactService = Depends(get_impact)):
    return svc.imp_add_reading(org, iid, _d(body), actor)


@router.post("/indicators/{iid}/readings/{no}/confirm", dependencies=[_approve])
def confirm_reading(iid: str, no: int, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ImpactService = Depends(get_impact)):
    return svc.imp_confirm_reading(org, iid, no, _d(body), actor)


@router.post("/indicators/{iid}/readings/{no}/reject", dependencies=[_approve])
def reject_reading(iid: str, no: int, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ImpactService = Depends(get_impact)):
    return svc.imp_reject_reading(org, iid, no, body.reason, actor)

