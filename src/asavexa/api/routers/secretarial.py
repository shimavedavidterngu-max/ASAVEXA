"""Company secretarial endpoints (records and evidence): meetings and minutes, resolutions, and a register of statutory filings. Thin: the rules live in asavexa.secretarial.

Viewing needs audit:read. Scheduling meetings, recording minutes, proposing resolutions, adding filings and recording them as filed need secretarial:prepare. Approving minutes, cancelling meetings,
deciding or withdrawing resolutions, confirming or withdrawing filings and setting the policy need secretarial:approve; the service refuses the person whose work is being decided.
The organisation always comes from the signed-in session. Nothing here checks company law or contacts any registry."""
from typing import Any, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...identity.domain.permissions import AUDIT_READ, SEC_APPROVE, SEC_PREPARE
from ...secretarial.service import SecretarialService
from ..deps import get_current_actor, get_current_org, get_secretarial, require_permission

router = APIRouter(prefix="/secretarial", tags=["Company secretarial"], dependencies=[Depends(require_permission(AUDIT_READ))])
_prepare = Depends(require_permission(SEC_PREPARE))
_approve = Depends(require_permission(SEC_APPROVE))


class ReasonBody(BaseModel):
    reason: str = ""


class NoteBody(BaseModel):
    note: Optional[str] = None


class PolicyBody(BaseModel):
    due_soon_days: Optional[Any] = None


class MeetingBody(BaseModel):
    kind: Optional[str] = None
    title: Optional[str] = None
    held_on: Optional[str] = None
    location: Optional[str] = None
    agenda: Optional[str] = None


class MinutesBody(BaseModel):
    attendees: Optional[str] = None
    minutes: Optional[str] = None
    evidence_ids: List[str] = []


class ResolutionBody(BaseModel):
    kind: Optional[str] = None
    text: Optional[str] = None
    meeting_id: Optional[str] = None


class DecideBody(BaseModel):
    votes_for: Optional[Any] = None
    votes_against: Optional[Any] = None
    abstentions: Optional[Any] = None
    outcome: Optional[str] = None
    note: Optional[str] = None


class FilingBody(BaseModel):
    kind: Optional[str] = None
    title: Optional[str] = None
    authority: Optional[str] = None
    due_on: Optional[str] = None
    owner_name: Optional[str] = None


class FiledBody(BaseModel):
    filed_on: Optional[str] = None
    receipt_ref: Optional[str] = None
    evidence_ids: List[str] = []


def _d(body) -> dict:
    """Only the fields the caller actually sent."""
    return body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)


@router.get("/options")
def options(org: str = Depends(get_current_org), svc: SecretarialService = Depends(get_secretarial)): return svc.cs_options(org)


@router.get("/overview")
def overview(org: str = Depends(get_current_org), svc: SecretarialService = Depends(get_secretarial)): return svc.cs_overview(org)


@router.get("/policy")
def policy(org: str = Depends(get_current_org), svc: SecretarialService = Depends(get_secretarial)): return svc.cs_get_policy(org)


@router.put("/policy", dependencies=[_approve])
def set_policy(body: PolicyBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: SecretarialService = Depends(get_secretarial)):
    return svc.cs_set_policy(org, _d(body), actor)


@router.get("/meetings")
def meetings(status: Optional[str] = None, org: str = Depends(get_current_org), svc: SecretarialService = Depends(get_secretarial)): return svc.cs_list_meetings(org, status)


@router.post("/meetings", status_code=201, dependencies=[_prepare])
def schedule_meeting(body: MeetingBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: SecretarialService = Depends(get_secretarial)):
    return svc.cs_schedule_meeting(org, _d(body), actor)


@router.get("/meetings/{mid}")
def get_meeting(mid: str, org: str = Depends(get_current_org), svc: SecretarialService = Depends(get_secretarial)): return svc.cs_get_meeting(org, mid)


@router.post("/meetings/{mid}/minutes", dependencies=[_prepare])
def record_minutes(mid: str, body: MinutesBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: SecretarialService = Depends(get_secretarial)):
    return svc.cs_record_minutes(org, mid, _d(body), actor)


@router.post("/meetings/{mid}/approve", dependencies=[_approve])
def approve_minutes(mid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: SecretarialService = Depends(get_secretarial)):
    return svc.cs_approve_minutes(org, mid, _d(body), actor)


@router.post("/meetings/{mid}/cancel", dependencies=[_approve])
def cancel_meeting(mid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: SecretarialService = Depends(get_secretarial)):
    return svc.cs_cancel_meeting(org, mid, body.reason, actor)


@router.get("/resolutions")
def resolutions(meeting_id: Optional[str] = None, status: Optional[str] = None, org: str = Depends(get_current_org), svc: SecretarialService = Depends(get_secretarial)): return svc.cs_list_resolutions(org, meeting_id, status)


@router.post("/resolutions", status_code=201, dependencies=[_prepare])
def propose_resolution(body: ResolutionBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: SecretarialService = Depends(get_secretarial)):
    return svc.cs_propose_resolution(org, _d(body), actor)


@router.get("/resolutions/{rid}")
def get_resolution(rid: str, org: str = Depends(get_current_org), svc: SecretarialService = Depends(get_secretarial)): return svc.cs_get_resolution(org, rid)


@router.post("/resolutions/{rid}/decide", dependencies=[_approve])
def decide_resolution(rid: str, body: DecideBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: SecretarialService = Depends(get_secretarial)):
    return svc.cs_decide_resolution(org, rid, _d(body), actor)


@router.post("/resolutions/{rid}/withdraw", dependencies=[_approve])
def withdraw_resolution(rid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: SecretarialService = Depends(get_secretarial)):
    return svc.cs_withdraw_resolution(org, rid, body.reason, actor)


@router.get("/filings")
def filings(status: Optional[str] = None, org: str = Depends(get_current_org), svc: SecretarialService = Depends(get_secretarial)): return svc.cs_list_filings(org, status)


@router.post("/filings", status_code=201, dependencies=[_prepare])
def add_filing(body: FilingBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: SecretarialService = Depends(get_secretarial)):
    return svc.cs_add_filing(org, _d(body), actor)


@router.get("/filings/{fid}")
def get_filing(fid: str, org: str = Depends(get_current_org), svc: SecretarialService = Depends(get_secretarial)): return svc.cs_get_filing(org, fid)


@router.post("/filings/{fid}/file", dependencies=[_prepare])
def file_filing(fid: str, body: FiledBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: SecretarialService = Depends(get_secretarial)):
    return svc.cs_file_filing(org, fid, _d(body), actor)


@router.post("/filings/{fid}/confirm", dependencies=[_approve])
def confirm_filing(fid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: SecretarialService = Depends(get_secretarial)):
    return svc.cs_confirm_filing(org, fid, _d(body), actor)


@router.post("/filings/{fid}/withdraw", dependencies=[_approve])
def withdraw_filing(fid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: SecretarialService = Depends(get_secretarial)):
    return svc.cs_withdraw_filing(org, fid, body.reason, actor)
