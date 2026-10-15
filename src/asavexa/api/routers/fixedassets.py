"""Fixed assets register endpoints (records and evidence): assets, straight-line depreciation schedule, disposals and physical counts. Thin: the rules live in asavexa.fixedassets.

Viewing needs audit:read. Proposing assets, proposing disposals and recording counts need fixedassets:prepare. Approving or rejecting assets and disposals, reviewing counts and setting the policy need fixedassets:approve;
the service refuses the person whose work is being decided. The organisation always comes from the signed-in session. Nothing here posts to a ledger."""
from typing import Any, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...fixedassets.service import FixedAssetService
from ...identity.domain.permissions import AUDIT_READ, FIX_APPROVE, FIX_PREPARE
from ..deps import get_current_actor, get_current_org, get_fixedassets, require_permission

router = APIRouter(prefix="/fixedassets", tags=["Fixed assets"], dependencies=[Depends(require_permission(AUDIT_READ))])
_prepare = Depends(require_permission(FIX_PREPARE))
_approve = Depends(require_permission(FIX_APPROVE))


class ReasonBody(BaseModel):
    reason: str = ""


class NoteBody(BaseModel):
    note: Optional[str] = None


class PolicyBody(BaseModel):
    count_days: Optional[Any] = None


class AssetBody(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    location: Optional[str] = None
    custodian_name: Optional[str] = None
    acquired_on: Optional[str] = None
    currency: Optional[str] = None
    cost: Optional[Any] = None
    residual_value: Optional[Any] = None
    life_months: Optional[Any] = None
    serial_number: Optional[str] = None
    evidence_ids: List[str] = []


class DisposalBody(BaseModel):
    disposed_on: Optional[str] = None
    proceeds: Optional[Any] = None
    reason: Optional[str] = None


class CountBody(BaseModel):
    counted_on: Optional[str] = None
    result: Optional[str] = None
    note: Optional[str] = None
    evidence_ids: List[str] = []


def _d(body) -> dict:
    """Only the fields the caller actually sent."""
    return body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)


@router.get("/options")
def options(org: str = Depends(get_current_org), svc: FixedAssetService = Depends(get_fixedassets)): return svc.fa_options(org)


@router.get("/overview")
def overview(org: str = Depends(get_current_org), svc: FixedAssetService = Depends(get_fixedassets)): return svc.fa_overview(org)


@router.get("/policy")
def policy(org: str = Depends(get_current_org), svc: FixedAssetService = Depends(get_fixedassets)): return svc.fa_get_policy(org)


@router.put("/policy", dependencies=[_approve])
def set_policy(body: PolicyBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FixedAssetService = Depends(get_fixedassets)):
    return svc.fa_set_policy(org, _d(body), actor)


@router.get("/assets")
def assets(status: Optional[str] = None, category: Optional[str] = None, org: str = Depends(get_current_org), svc: FixedAssetService = Depends(get_fixedassets)): return svc.fa_list_assets(org, status, category)


@router.post("/assets", status_code=201, dependencies=[_prepare])
def propose_asset(body: AssetBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FixedAssetService = Depends(get_fixedassets)):
    return svc.fa_propose_asset(org, _d(body), actor)


@router.get("/assets/{aid}")
def get_asset(aid: str, org: str = Depends(get_current_org), svc: FixedAssetService = Depends(get_fixedassets)): return svc.fa_get_asset(org, aid)


@router.get("/assets/{aid}/schedule")
def schedule(aid: str, months: int = 12, org: str = Depends(get_current_org), svc: FixedAssetService = Depends(get_fixedassets)): return svc.fa_schedule(org, aid, months)


@router.post("/assets/{aid}/approve", dependencies=[_approve])
def approve_asset(aid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FixedAssetService = Depends(get_fixedassets)):
    return svc.fa_approve_asset(org, aid, _d(body), actor)


@router.post("/assets/{aid}/reject", dependencies=[_approve])
def reject_asset(aid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FixedAssetService = Depends(get_fixedassets)):
    return svc.fa_reject_asset(org, aid, body.reason, actor)


@router.post("/assets/{aid}/disposal", dependencies=[_prepare])
def propose_disposal(aid: str, body: DisposalBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FixedAssetService = Depends(get_fixedassets)):
    return svc.fa_propose_disposal(org, aid, _d(body), actor)


@router.post("/assets/{aid}/disposal/approve", dependencies=[_approve])
def approve_disposal(aid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FixedAssetService = Depends(get_fixedassets)):
    return svc.fa_approve_disposal(org, aid, _d(body), actor)


@router.post("/assets/{aid}/disposal/reject", dependencies=[_approve])
def reject_disposal(aid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FixedAssetService = Depends(get_fixedassets)):
    return svc.fa_reject_disposal(org, aid, body.reason, actor)


@router.post("/assets/{aid}/counts", dependencies=[_prepare])
def record_count(aid: str, body: CountBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FixedAssetService = Depends(get_fixedassets)):
    return svc.fa_record_count(org, aid, _d(body), actor)


@router.post("/assets/{aid}/counts/{no}/review", dependencies=[_approve])
def review_count(aid: str, no: int, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FixedAssetService = Depends(get_fixedassets)):
    return svc.fa_review_count(org, aid, no, _d(body), actor)
