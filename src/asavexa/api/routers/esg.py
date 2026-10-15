"""ESG and carbon endpoints (records and evidence): emission records, verification by a different person and reduction targets. Thin: the rules live in asavexa.esg.

Viewing needs audit:read. Proposing emission records and targets needs esg:prepare. Verifying or rejecting a record, approving or rejecting a target and setting the factor age limit need esg:approve;
the service refuses the person who proposed the item. The organisation always comes from the signed-in session. Nothing here supplies emission factors or measures anything."""
from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...esg.service import EsgService
from ...identity.domain.permissions import AUDIT_READ, ESG_APPROVE, ESG_PREPARE
from ..deps import get_current_actor, get_current_org, get_esg, require_permission

router = APIRouter(prefix="/esg", tags=["ESG"], dependencies=[Depends(require_permission(AUDIT_READ))])
_prepare = Depends(require_permission(ESG_PREPARE))
_approve = Depends(require_permission(ESG_APPROVE))


class ReasonBody(BaseModel):
    reason: str = ""


class NoteBody(BaseModel):
    note: Optional[str] = None


class SettingBody(BaseModel):
    factor_max_age_years: Optional[Any] = None


class EntryBody(BaseModel):
    scope: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    quantity: Optional[Any] = None
    unit: Optional[str] = None
    factor: Optional[Any] = None
    factor_source: Optional[str] = None
    factor_year: Optional[Any] = None


class TargetBody(BaseModel):
    label: Optional[str] = None
    scope: Optional[str] = None
    baseline_year: Optional[Any] = None
    baseline_tonnes: Optional[Any] = None
    reduction_pct: Optional[Any] = None
    target_year: Optional[Any] = None


def _d(body) -> dict:
    """Only the fields the caller actually sent."""
    return body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)


@router.get("/options")
def options(org: str = Depends(get_current_org), svc: EsgService = Depends(get_esg)): return svc.es_options(org)


@router.get("/overview")
def overview(org: str = Depends(get_current_org), svc: EsgService = Depends(get_esg)): return svc.es_overview(org)


@router.get("/setting")
def setting(org: str = Depends(get_current_org), svc: EsgService = Depends(get_esg)): return svc.es_get_setting(org)


@router.put("/setting", dependencies=[_approve])
def set_setting(body: SettingBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: EsgService = Depends(get_esg)):
    return svc.es_set_setting(org, _d(body), actor)


@router.get("/entries")
def entries(status: Optional[str] = None, org: str = Depends(get_current_org), svc: EsgService = Depends(get_esg)): return svc.es_list_entries(org, status)


@router.post("/entries", status_code=201, dependencies=[_prepare])
def add_entry(body: EntryBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: EsgService = Depends(get_esg)):
    return svc.es_add_entry(org, _d(body), actor)


@router.get("/entries/{eid}")
def get_entry(eid: str, org: str = Depends(get_current_org), svc: EsgService = Depends(get_esg)): return svc.es_get_entry(org, eid)


@router.post("/entries/{eid}/verify", dependencies=[_approve])
def verify_entry(eid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: EsgService = Depends(get_esg)):
    return svc.es_verify_entry(org, eid, _d(body), actor)


@router.post("/entries/{eid}/reject", dependencies=[_approve])
def reject_entry(eid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: EsgService = Depends(get_esg)):
    return svc.es_reject_entry(org, eid, body.reason, actor)


@router.get("/targets")
def targets(status: Optional[str] = None, org: str = Depends(get_current_org), svc: EsgService = Depends(get_esg)): return svc.es_list_targets(org, status)


@router.post("/targets", status_code=201, dependencies=[_prepare])
def add_target(body: TargetBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: EsgService = Depends(get_esg)):
    return svc.es_add_target(org, _d(body), actor)


@router.post("/targets/{tid}/approve", dependencies=[_approve])
def approve_target(tid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: EsgService = Depends(get_esg)):
    return svc.es_approve_target(org, tid, _d(body), actor)


@router.post("/targets/{tid}/reject", dependencies=[_approve])
def reject_target(tid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: EsgService = Depends(get_esg)):
    return svc.es_reject_target(org, tid, body.reason, actor)
