"""Mergers and acquisitions endpoints (records and evidence). Thin: the rules live in asavexa.mergers.

Viewing needs audit:read. Proposing deals and recording checklist items, conditions, adjustments and what was provided or met need mergers:prepare. Deciding them, closing deals and the settings need mergers:approve; the service refuses the person who recorded the item. Nothing here values a business, reads a contract or gives deal, tax or legal advice.
The organisation always comes from the signed-in session."""
from typing import Any, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...identity.domain.permissions import AUDIT_READ, MNA_APPROVE, MNA_PREPARE
from ...mergers.service import MergersService
from ..deps import get_current_actor, get_current_org, get_mergers, require_permission

router = APIRouter(prefix="/mergers", tags=["Mergers and acquisitions"], dependencies=[Depends(require_permission(AUDIT_READ))])
_prepare = Depends(require_permission(MNA_PREPARE))
_approve = Depends(require_permission(MNA_APPROVE))


class AdjustmentBody(BaseModel):
    kind: Optional[str] = None
    amount: Optional[Any] = None
    basis: Optional[str] = None


class ChecklistBody(BaseModel):
    title: Optional[str] = None
    area: Optional[str] = None


class CloseBody(BaseModel):
    outcome: Optional[str] = None
    reason: Optional[str] = None


class ConditionBody(BaseModel):
    title: Optional[str] = None
    due_date: Optional[str] = None


class DealBody(BaseModel):
    name: Optional[str] = None
    deal_ref: Optional[str] = None
    currency: Optional[str] = None
    deal_type: Optional[str] = None
    base_price: Optional[Any] = None
    target_close_date: Optional[str] = None
    description: Optional[str] = None


class DoneBody(BaseModel):
    done_on: Optional[str] = None
    note: Optional[str] = None


class NoteBody(BaseModel):
    note: Optional[str] = None


class ReasonBody(BaseModel):
    reason: str = ""


class SettingBody(BaseModel):
    due_soon_days: Optional[Any] = None


def _d(body) -> dict:
    """Only the fields the caller actually sent."""
    return body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)


@router.get("/options")
def options(org: str = Depends(get_current_org), svc: MergersService = Depends(get_mergers)):
    return svc.ma_options(org)


@router.get("/overview")
def overview(org: str = Depends(get_current_org), svc: MergersService = Depends(get_mergers)):
    return svc.ma_overview(org)


@router.get("/setting")
def setting(org: str = Depends(get_current_org), svc: MergersService = Depends(get_mergers)):
    return svc.ma_get_setting(org)


@router.put("/setting", dependencies=[_approve])
def set_setting(body: SettingBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: MergersService = Depends(get_mergers)):
    return svc.ma_set_setting(org, _d(body), actor)


@router.get("/deals")
def deals(status: Optional[str] = None, org: str = Depends(get_current_org), svc: MergersService = Depends(get_mergers)):
    return svc.ma_list_deals(org, status)


@router.post("/deals", status_code=201, dependencies=[_prepare])
def add_deal(body: DealBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: MergersService = Depends(get_mergers)):
    return svc.ma_add_deal(org, _d(body), actor)


@router.get("/deals/{did}")
def get_deal(did: str, org: str = Depends(get_current_org), svc: MergersService = Depends(get_mergers)):
    return svc.ma_get_deal(org, did)


@router.post("/deals/{did}/approve", dependencies=[_approve])
def approve_deal(did: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: MergersService = Depends(get_mergers)):
    return svc.ma_approve_deal(org, did, _d(body), actor)


@router.post("/deals/{did}/reject", dependencies=[_approve])
def reject_deal(did: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: MergersService = Depends(get_mergers)):
    return svc.ma_reject_deal(org, did, body.reason, actor)


@router.post("/deals/{did}/close", dependencies=[_approve])
def close_deal(did: str, body: CloseBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: MergersService = Depends(get_mergers)):
    return svc.ma_close_deal(org, did, _d(body), actor)


@router.post("/deals/{did}/checklist", dependencies=[_prepare])
def add_checklist(did: str, body: ChecklistBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: MergersService = Depends(get_mergers)):
    return svc.ma_add_checklist(org, did, _d(body), actor)


@router.post("/deals/{did}/checklist/{no}/provide", dependencies=[_prepare])
def provide_checklist(did: str, no: int, body: DoneBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: MergersService = Depends(get_mergers)):
    return svc.ma_provide(org, did, 'checklist', no, _d(body), actor)


@router.post("/deals/{did}/checklist/{no}/confirm", dependencies=[_approve])
def confirm_checklist(did: str, no: int, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: MergersService = Depends(get_mergers)):
    return svc.ma_decide(org, did, 'checklist', no, True, _d(body), actor)


@router.post("/deals/{did}/checklist/{no}/reject", dependencies=[_approve])
def reject_checklist(did: str, no: int, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: MergersService = Depends(get_mergers)):
    return svc.ma_decide(org, did, 'checklist', no, False, body.reason, actor)


@router.post("/deals/{did}/conditions", dependencies=[_prepare])
def add_condition(did: str, body: ConditionBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: MergersService = Depends(get_mergers)):
    return svc.ma_add_condition(org, did, _d(body), actor)


@router.post("/deals/{did}/conditions/{no}/meet", dependencies=[_prepare])
def meet_condition(did: str, no: int, body: DoneBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: MergersService = Depends(get_mergers)):
    return svc.ma_provide(org, did, 'conditions', no, _d(body), actor)


@router.post("/deals/{did}/conditions/{no}/confirm", dependencies=[_approve])
def confirm_condition(did: str, no: int, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: MergersService = Depends(get_mergers)):
    return svc.ma_decide(org, did, 'conditions', no, True, _d(body), actor)


@router.post("/deals/{did}/conditions/{no}/reject", dependencies=[_approve])
def reject_condition(did: str, no: int, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: MergersService = Depends(get_mergers)):
    return svc.ma_decide(org, did, 'conditions', no, False, body.reason, actor)


@router.post("/deals/{did}/adjustments", dependencies=[_prepare])
def add_adjustment(did: str, body: AdjustmentBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: MergersService = Depends(get_mergers)):
    return svc.ma_add_adjustment(org, did, _d(body), actor)


@router.post("/deals/{did}/adjustments/{no}/confirm", dependencies=[_approve])
def confirm_adjustment(did: str, no: int, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: MergersService = Depends(get_mergers)):
    return svc.ma_decide(org, did, 'adjustments', no, True, _d(body), actor)


@router.post("/deals/{did}/adjustments/{no}/reject", dependencies=[_approve])
def reject_adjustment(did: str, no: int, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: MergersService = Depends(get_mergers)):
    return svc.ma_decide(org, did, 'adjustments', no, False, body.reason, actor)

