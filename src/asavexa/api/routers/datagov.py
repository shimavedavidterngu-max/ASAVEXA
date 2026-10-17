"""Data governance endpoints (records and evidence). Thin: the rules live in asavexa.datagov.

Viewing needs audit:read. Proposing assets, recording reviews and proposing grants need datagov:prepare. Deciding them, revoking grants, retiring assets and the settings need datagov:approve; the service refuses the person who proposed the item. Nothing here holds data, enforces access or applies any law.
The organisation always comes from the signed-in session."""
from typing import Any, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...identity.domain.permissions import AUDIT_READ, DG_APPROVE, DG_PREPARE
from ...datagov.service import DatagovService
from ..deps import get_current_actor, get_current_org, get_datagov, require_permission

router = APIRouter(prefix="/datagov", tags=["Data governance"], dependencies=[Depends(require_permission(AUDIT_READ))])
_prepare = Depends(require_permission(DG_PREPARE))
_approve = Depends(require_permission(DG_APPROVE))


class AssetBody(BaseModel):
    name: Optional[str] = None
    owner_ref: Optional[str] = None
    classification: Optional[str] = None
    personal_data: Optional[str] = None
    retention_months: Optional[Any] = None
    review_every_months: Optional[Any] = None
    description: Optional[str] = None


class GrantBody(BaseModel):
    person_ref: Optional[str] = None
    access_level: Optional[str] = None
    purpose: Optional[str] = None
    starts_on: Optional[str] = None
    expires_on: Optional[str] = None


class NoteBody(BaseModel):
    note: Optional[str] = None


class ReasonBody(BaseModel):
    reason: str = ""


class ReviewBody(BaseModel):
    review_date: Optional[str] = None
    outcome: Optional[str] = None


class SettingBody(BaseModel):
    expiry_warning_days: Optional[Any] = None
    max_restricted_grants: Optional[Any] = None


def _d(body) -> dict:
    """Only the fields the caller actually sent."""
    return body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)


@router.get("/options")
def options(org: str = Depends(get_current_org), svc: DatagovService = Depends(get_datagov)):
    return svc.dg_options(org)


@router.get("/overview")
def overview(org: str = Depends(get_current_org), svc: DatagovService = Depends(get_datagov)):
    return svc.dg_overview(org)


@router.get("/setting")
def setting(org: str = Depends(get_current_org), svc: DatagovService = Depends(get_datagov)):
    return svc.dg_get_setting(org)


@router.put("/setting", dependencies=[_approve])
def set_setting(body: SettingBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: DatagovService = Depends(get_datagov)):
    return svc.dg_set_setting(org, _d(body), actor)


@router.get("/assets")
def assets(status: Optional[str] = None, org: str = Depends(get_current_org), svc: DatagovService = Depends(get_datagov)):
    return svc.dg_list_assets(org, status)


@router.post("/assets", status_code=201, dependencies=[_prepare])
def add_asset(body: AssetBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: DatagovService = Depends(get_datagov)):
    return svc.dg_add_asset(org, _d(body), actor)


@router.get("/assets/{aid}")
def get_asset(aid: str, org: str = Depends(get_current_org), svc: DatagovService = Depends(get_datagov)):
    return svc.dg_get_asset(org, aid)


@router.post("/assets/{aid}/approve", dependencies=[_approve])
def approve_asset(aid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: DatagovService = Depends(get_datagov)):
    return svc.dg_approve_asset(org, aid, _d(body), actor)


@router.post("/assets/{aid}/reject", dependencies=[_approve])
def reject_asset(aid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: DatagovService = Depends(get_datagov)):
    return svc.dg_reject_asset(org, aid, body.reason, actor)


@router.post("/assets/{aid}/retire", dependencies=[_approve])
def retire_asset(aid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: DatagovService = Depends(get_datagov)):
    return svc.dg_retire_asset(org, aid, body.reason, actor)


@router.post("/assets/{aid}/reviews", dependencies=[_prepare])
def add_review(aid: str, body: ReviewBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: DatagovService = Depends(get_datagov)):
    return svc.dg_add_review(org, aid, _d(body), actor)


@router.post("/assets/{aid}/reviews/{no}/confirm", dependencies=[_approve])
def confirm_review(aid: str, no: int, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: DatagovService = Depends(get_datagov)):
    return svc.dg_confirm_review(org, aid, no, _d(body), actor)


@router.post("/assets/{aid}/reviews/{no}/reject", dependencies=[_approve])
def reject_review(aid: str, no: int, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: DatagovService = Depends(get_datagov)):
    return svc.dg_reject_review(org, aid, no, body.reason, actor)


@router.post("/assets/{aid}/grants", dependencies=[_prepare])
def add_grant(aid: str, body: GrantBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: DatagovService = Depends(get_datagov)):
    return svc.dg_add_grant(org, aid, _d(body), actor)


@router.post("/assets/{aid}/grants/{no}/approve", dependencies=[_approve])
def approve_grant(aid: str, no: int, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: DatagovService = Depends(get_datagov)):
    return svc.dg_approve_grant(org, aid, no, _d(body), actor)


@router.post("/assets/{aid}/grants/{no}/reject", dependencies=[_approve])
def reject_grant(aid: str, no: int, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: DatagovService = Depends(get_datagov)):
    return svc.dg_reject_grant(org, aid, no, body.reason, actor)


@router.post("/assets/{aid}/grants/{no}/revoke", dependencies=[_approve])
def revoke_grant(aid: str, no: int, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: DatagovService = Depends(get_datagov)):
    return svc.dg_revoke_grant(org, aid, no, body.reason, actor)

