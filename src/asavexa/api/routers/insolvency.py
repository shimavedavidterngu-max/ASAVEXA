"""Insolvency endpoints (records and evidence). Thin: the rules live in asavexa.insolvency.

Viewing needs audit:read. Proposing cases, lodging claims and recording realisations and costs need insolvency:prepare. Deciding them, closing cases and recording a distribution need insolvency:approve; the service refuses the person who proposed the item. Nothing here pays anyone, files anything or applies any insolvency law.
The organisation always comes from the signed-in session."""
from typing import Any, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...identity.domain.permissions import AUDIT_READ, ISV_APPROVE, ISV_PREPARE
from ...insolvency.service import InsolvencyService
from ..deps import get_current_actor, get_current_org, get_insolvency, require_permission

router = APIRouter(prefix="/insolvency", tags=["Insolvency"], dependencies=[Depends(require_permission(AUDIT_READ))])
_prepare = Depends(require_permission(ISV_PREPARE))
_approve = Depends(require_permission(ISV_APPROVE))


class AdmitBody(BaseModel):
    amount: Optional[Any] = None
    note: Optional[str] = None


class CaseBody(BaseModel):
    title: Optional[str] = None
    currency: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[Any] = None
    claims_deadline: Optional[str] = None


class ClaimBody(BaseModel):
    creditor_ref: Optional[str] = None
    claim_class: Optional[str] = None
    amount: Optional[Any] = None
    basis: Optional[str] = None


class EntryBody(BaseModel):
    entry_type: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[Any] = None
    entry_date: Optional[str] = None


class NoteBody(BaseModel):
    note: Optional[str] = None


class ReasonBody(BaseModel):
    reason: str = ""


def _d(body) -> dict:
    """Only the fields the caller actually sent."""
    return body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)


@router.get("/options")
def options(org: str = Depends(get_current_org), svc: InsolvencyService = Depends(get_insolvency)):
    return svc.isv_options(org)


@router.get("/overview")
def overview(org: str = Depends(get_current_org), svc: InsolvencyService = Depends(get_insolvency)):
    return svc.isv_overview(org)


@router.get("/cases")
def cases(status: Optional[str] = None, org: str = Depends(get_current_org), svc: InsolvencyService = Depends(get_insolvency)):
    return svc.isv_list_cases(org, status)


@router.post("/cases", status_code=201, dependencies=[_prepare])
def add_case(body: CaseBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: InsolvencyService = Depends(get_insolvency)):
    return svc.isv_add_case(org, _d(body), actor)


@router.get("/cases/{cid}")
def get_case(cid: str, org: str = Depends(get_current_org), svc: InsolvencyService = Depends(get_insolvency)):
    return svc.isv_get_case(org, cid)


@router.post("/cases/{cid}/approve", dependencies=[_approve])
def approve_case(cid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: InsolvencyService = Depends(get_insolvency)):
    return svc.isv_approve_case(org, cid, _d(body), actor)


@router.post("/cases/{cid}/reject", dependencies=[_approve])
def reject_case(cid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: InsolvencyService = Depends(get_insolvency)):
    return svc.isv_reject_case(org, cid, body.reason, actor)


@router.post("/cases/{cid}/close", dependencies=[_approve])
def close_case(cid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: InsolvencyService = Depends(get_insolvency)):
    return svc.isv_close_case(org, cid, body.reason, actor)


@router.post("/cases/{cid}/claims", dependencies=[_prepare])
def add_claim(cid: str, body: ClaimBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: InsolvencyService = Depends(get_insolvency)):
    return svc.isv_add_claim(org, cid, _d(body), actor)


@router.post("/cases/{cid}/claims/{no}/admit", dependencies=[_approve])
def admit_claim(cid: str, no: int, body: AdmitBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: InsolvencyService = Depends(get_insolvency)):
    return svc.isv_admit_claim(org, cid, no, _d(body), actor)


@router.post("/cases/{cid}/claims/{no}/reject", dependencies=[_approve])
def reject_claim(cid: str, no: int, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: InsolvencyService = Depends(get_insolvency)):
    return svc.isv_reject_claim(org, cid, no, body.reason, actor)


@router.post("/cases/{cid}/entries", dependencies=[_prepare])
def add_entry(cid: str, body: EntryBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: InsolvencyService = Depends(get_insolvency)):
    return svc.isv_add_entry(org, cid, _d(body), actor)


@router.post("/cases/{cid}/entries/{no}/confirm", dependencies=[_approve])
def confirm_entry(cid: str, no: int, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: InsolvencyService = Depends(get_insolvency)):
    return svc.isv_confirm_entry(org, cid, no, _d(body), actor)


@router.post("/cases/{cid}/entries/{no}/reject", dependencies=[_approve])
def reject_entry(cid: str, no: int, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: InsolvencyService = Depends(get_insolvency)):
    return svc.isv_reject_entry(org, cid, no, body.reason, actor)


@router.post("/cases/{cid}/distribution", dependencies=[_approve])
def record_distribution(cid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: InsolvencyService = Depends(get_insolvency)):
    return svc.isv_record_distribution(org, cid, _d(body), actor)

