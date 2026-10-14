"""Planning and KPIs endpoints (records and evidence): KPI ownership and traceability, and forecast accuracy.
Thin: the rules live in asavexa.fpa.

Viewing needs reporting:read. Defining KPIs, accepting ownership, recording readings, registering and withdrawing forecasts and recording actuals need fpa:prepare.
Approving a KPI, reviewing or rejecting a reading, changing an owner, retiring a KPI, confirming or rejecting an actual and setting the policy need fpa:approve;
the service refuses the person whose work is being decided. The organisation always comes from the signed-in session."""
from typing import Any, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...fpa.service import FpaService
from ...identity.domain.permissions import FPA_APPROVE, FPA_PREPARE, REPORTING_READ
from ..deps import get_current_actor, get_current_org, get_fpa, require_permission

router = APIRouter(prefix="/fpa", tags=["Planning and KPIs"], dependencies=[Depends(require_permission(REPORTING_READ))])
_prepare = Depends(require_permission(FPA_PREPARE))
_approve = Depends(require_permission(FPA_APPROVE))


class NoteBody(BaseModel):
    note: str = ""


class OwnerBody(BaseModel):
    owner: Optional[str] = None
    reason: str = ""


class PolicyBody(BaseModel):
    watch_pct: Optional[int] = None
    grace_days: Optional[int] = None
    accuracy_pct: Optional[int] = None
    min_items: Optional[int] = None


class KpiBody(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    unit: Optional[str] = None
    currency: Optional[str] = None
    direction: Optional[str] = None
    frequency: Optional[str] = None
    owner: Optional[str] = None
    data_source: Optional[str] = None
    method: Optional[str] = None
    target: Optional[Any] = None
    watch_pct: Optional[Any] = None
    effective_from: Optional[str] = None


class ReadingBody(BaseModel):
    period_end: Optional[str] = None
    value: Optional[Any] = None
    source_note: Optional[str] = None
    evidence_ids: List[str] = []
    correction_note: Optional[str] = None


class ForecastBody(BaseModel):
    metric: Optional[str] = None
    unit: Optional[str] = None
    currency: Optional[str] = None
    period_end: Optional[str] = None
    value: Optional[Any] = None
    basis: Optional[str] = None
    kpi_id: Optional[str] = None


class ActualBody(BaseModel):
    value: Optional[Any] = None
    source_note: Optional[str] = None
    evidence_ids: List[str] = []


def _d(body) -> dict:
    """Only the fields the caller actually sent."""
    return body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)


@router.get("/options")
def options(org: str = Depends(get_current_org), svc: FpaService = Depends(get_fpa)): return svc.fpa_options(org)


@router.get("/overview")
def overview(org: str = Depends(get_current_org), svc: FpaService = Depends(get_fpa)): return svc.fpa_overview(org)


@router.get("/policy")
def policy(org: str = Depends(get_current_org), svc: FpaService = Depends(get_fpa)): return svc.get_fpa_policy(org)


@router.put("/policy", dependencies=[_approve])
def set_policy(body: PolicyBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FpaService = Depends(get_fpa)):
    return svc.set_fpa_policy(org, _d(body), actor)


@router.get("/kpis")
def kpis(status: Optional[str] = None, owner: Optional[str] = None, org: str = Depends(get_current_org), svc: FpaService = Depends(get_fpa)): return svc.list_kpis(org, status, owner)


@router.post("/kpis", status_code=201, dependencies=[_prepare])
def define_kpi(body: KpiBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FpaService = Depends(get_fpa)):
    return svc.define_kpi(org, _d(body), actor)


@router.get("/kpis/{kid}")
def get_kpi(kid: str, org: str = Depends(get_current_org), svc: FpaService = Depends(get_fpa)): return svc.get_kpi(org, kid)


@router.post("/kpis/{kid}/approve", dependencies=[_approve])
def approve_kpi(kid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FpaService = Depends(get_fpa)):
    return svc.approve_kpi(org, kid, actor, body.note)


@router.post("/kpis/{kid}/accept", dependencies=[_prepare])
def accept_ownership(kid: str, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FpaService = Depends(get_fpa)):
    return svc.accept_kpi_ownership(org, kid, actor)


@router.post("/kpis/{kid}/owner", dependencies=[_approve])
def change_owner(kid: str, body: OwnerBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FpaService = Depends(get_fpa)):
    return svc.reassign_kpi_owner(org, kid, body.owner, body.reason, actor)


@router.post("/kpis/{kid}/retire", dependencies=[_approve])
def retire_kpi(kid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FpaService = Depends(get_fpa)):
    return svc.retire_kpi(org, kid, body.note, actor)


@router.post("/kpis/{kid}/readings", status_code=201, dependencies=[_prepare])
def add_reading(kid: str, body: ReadingBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FpaService = Depends(get_fpa)):
    return svc.record_kpi_reading(org, kid, _d(body), actor)


@router.post("/kpis/{kid}/readings/{rid}/review", dependencies=[_approve])
def review_reading(kid: str, rid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FpaService = Depends(get_fpa)):
    return svc.review_kpi_reading(org, kid, rid, actor, body.note)


@router.post("/kpis/{kid}/readings/{rid}/reject", dependencies=[_approve])
def reject_reading(kid: str, rid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FpaService = Depends(get_fpa)):
    return svc.reject_kpi_reading(org, kid, rid, body.note, actor)


@router.get("/forecasts")
def forecasts(status: Optional[str] = None, org: str = Depends(get_current_org), svc: FpaService = Depends(get_fpa)): return svc.list_forecasts(org, status)


@router.post("/forecasts", status_code=201, dependencies=[_prepare])
def register_forecast(body: ForecastBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FpaService = Depends(get_fpa)):
    return svc.register_forecast(org, _d(body), actor)


@router.get("/forecasts/{fid}")
def get_forecast(fid: str, org: str = Depends(get_current_org), svc: FpaService = Depends(get_fpa)): return svc.get_forecast(org, fid)


@router.post("/forecasts/{fid}/withdraw", dependencies=[_prepare])
def withdraw_forecast(fid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FpaService = Depends(get_fpa)):
    return svc.withdraw_forecast(org, fid, body.note, actor)


@router.post("/forecasts/{fid}/actual", dependencies=[_prepare])
def add_actual(fid: str, body: ActualBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FpaService = Depends(get_fpa)):
    return svc.record_forecast_actual(org, fid, _d(body), actor)


@router.post("/forecasts/{fid}/actual/confirm", dependencies=[_approve])
def confirm_actual(fid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FpaService = Depends(get_fpa)):
    return svc.confirm_forecast_actual(org, fid, actor, body.note)


@router.post("/forecasts/{fid}/actual/reject", dependencies=[_approve])
def reject_actual(fid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FpaService = Depends(get_fpa)):
    return svc.reject_forecast_actual(org, fid, body.note, actor)


@router.get("/accuracy")
def accuracy(min_lead_days: int = 0, org: str = Depends(get_current_org), svc: FpaService = Depends(get_fpa)): return svc.forecast_accuracy_report(org, min_lead_days)
