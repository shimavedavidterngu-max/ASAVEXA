"""Financial-crime casework endpoints (records and evidence): alerts, cases, conflict declarations, timeline, screening records, two-person decisions, loss and recovery.
Thin: the rules live in asavexa.fincrime.

Cases are confidential, so viewing needs fincrime:read (not the everyday reporting:read). Raising alerts, opening and working cases, recording screening results, losses and
recoveries and proposing an outcome need fincrime:prepare. Dismissing an alert, deciding an outcome, resolving a screening match, confirming a recovery, changing the lead,
reopening a case and setting the targets need fincrime:approve; the service refuses the person whose work is being decided. Declaring a conflict of interest needs only
fincrime:read. The organisation always comes from the signed-in session."""
from typing import Any, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...fincrime.service import FincrimeService
from ...identity.domain.permissions import FINCRIME_APPROVE, FINCRIME_PREPARE, FINCRIME_READ
from ..deps import get_current_actor, get_current_org, get_fincrime, require_permission

router = APIRouter(prefix="/fincrime", tags=["Financial-crime casework"], dependencies=[Depends(require_permission(FINCRIME_READ))])
_prepare = Depends(require_permission(FINCRIME_PREPARE))
_approve = Depends(require_permission(FINCRIME_APPROVE))
_read = Depends(require_permission(FINCRIME_READ))


class NoteBody(BaseModel):
    note: str = ""


class ReasonBody(BaseModel):
    reason: str = ""


class PolicyBody(BaseModel):
    alert_sla_days: Optional[int] = None
    case_sla_days: Optional[int] = None


class AlertBody(BaseModel):
    source: Optional[str] = None
    summary: Optional[str] = None
    observed_on: Optional[str] = None
    amount: Optional[Any] = None
    currency: Optional[str] = None
    evidence_ids: List[str] = []


class CaseBody(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    severity: Optional[str] = None
    alert_ids: List[str] = []
    conflict: Optional[str] = None
    conflict_note: Optional[str] = None


class DeclareBody(BaseModel):
    status: Optional[str] = None
    note: Optional[str] = None


class LeadBody(BaseModel):
    lead: Optional[str] = None
    reason: str = ""


class EventBody(BaseModel):
    occurred_on: Optional[str] = None
    kind: Optional[str] = None
    text: Optional[str] = None
    evidence_ids: List[str] = []


class ScreeningBody(BaseModel):
    subject: Optional[str] = None
    subject_kind: Optional[str] = None
    check: Optional[str] = None
    list_name: Optional[str] = None
    screened_on: Optional[str] = None
    result: Optional[str] = None
    note: Optional[str] = None


class ResolveBody(BaseModel):
    outcome: Optional[str] = None
    reason: Optional[str] = None


class LossBody(BaseModel):
    amount: Optional[Any] = None
    currency: Optional[str] = None
    occurred_on: Optional[str] = None
    description: Optional[str] = None
    evidence_ids: List[str] = []


class RecoveryBody(BaseModel):
    amount: Optional[Any] = None
    currency: Optional[str] = None
    received_on: Optional[str] = None
    kind: Optional[str] = None
    note: Optional[str] = None
    evidence_ids: List[str] = []


class DecisionBody(BaseModel):
    outcome: Optional[str] = None
    rationale: Optional[str] = None
    referral_to: Optional[str] = None


def _d(body) -> dict:
    """Only the fields the caller actually sent."""
    return body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)


@router.get("/options")
def options(org: str = Depends(get_current_org), svc: FincrimeService = Depends(get_fincrime)): return svc.fc_options(org)


@router.get("/overview")
def overview(org: str = Depends(get_current_org), svc: FincrimeService = Depends(get_fincrime)): return svc.fc_overview(org)


@router.get("/policy")
def policy(org: str = Depends(get_current_org), svc: FincrimeService = Depends(get_fincrime)): return svc.fc_get_policy(org)


@router.put("/policy", dependencies=[_approve])
def set_policy(body: PolicyBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FincrimeService = Depends(get_fincrime)):
    return svc.fc_set_policy(org, _d(body), actor)


@router.get("/alerts")
def alerts(status: Optional[str] = None, org: str = Depends(get_current_org), svc: FincrimeService = Depends(get_fincrime)): return svc.fc_list_alerts(org, status)


@router.post("/alerts", status_code=201, dependencies=[_prepare])
def raise_alert(body: AlertBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FincrimeService = Depends(get_fincrime)):
    return svc.fc_raise_alert(org, _d(body), actor)


@router.post("/alerts/{aid}/dismiss", dependencies=[_approve])
def dismiss_alert(aid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FincrimeService = Depends(get_fincrime)):
    return svc.fc_dismiss_alert(org, aid, body.reason, actor)


@router.get("/cases")
def cases(status: Optional[str] = None, org: str = Depends(get_current_org), svc: FincrimeService = Depends(get_fincrime)): return svc.fc_list_cases(org, status)


@router.post("/cases", status_code=201, dependencies=[_prepare])
def open_case(body: CaseBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FincrimeService = Depends(get_fincrime)):
    return svc.fc_open_case(org, _d(body), actor)


@router.get("/cases/{cid}")
def get_case(cid: str, org: str = Depends(get_current_org), svc: FincrimeService = Depends(get_fincrime)): return svc.fc_get_case(org, cid)


@router.post("/cases/{cid}/declaration", dependencies=[_read])
def declare_interest(cid: str, body: DeclareBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FincrimeService = Depends(get_fincrime)):
    return svc.fc_declare_interest(org, cid, _d(body), actor)


@router.post("/cases/{cid}/lead", dependencies=[_approve])
def change_lead(cid: str, body: LeadBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FincrimeService = Depends(get_fincrime)):
    return svc.fc_change_lead(org, cid, body.lead, body.reason, actor)


@router.post("/cases/{cid}/events", status_code=201, dependencies=[_prepare])
def add_event(cid: str, body: EventBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FincrimeService = Depends(get_fincrime)):
    return svc.fc_add_event(org, cid, _d(body), actor)


@router.post("/cases/{cid}/screenings", status_code=201, dependencies=[_prepare])
def record_screening(cid: str, body: ScreeningBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FincrimeService = Depends(get_fincrime)):
    return svc.fc_record_screening(org, cid, _d(body), actor)


@router.post("/cases/{cid}/screenings/{sid}/resolve", dependencies=[_approve])
def resolve_screening(cid: str, sid: str, body: ResolveBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FincrimeService = Depends(get_fincrime)):
    return svc.fc_resolve_screening(org, cid, sid, _d(body), actor)


@router.post("/cases/{cid}/losses", status_code=201, dependencies=[_prepare])
def record_loss(cid: str, body: LossBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FincrimeService = Depends(get_fincrime)):
    return svc.fc_record_loss(org, cid, _d(body), actor)


@router.post("/cases/{cid}/recoveries", status_code=201, dependencies=[_prepare])
def record_recovery(cid: str, body: RecoveryBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FincrimeService = Depends(get_fincrime)):
    return svc.fc_record_recovery(org, cid, _d(body), actor)


@router.post("/cases/{cid}/recoveries/{rid}/confirm", dependencies=[_approve])
def confirm_recovery(cid: str, rid: str, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FincrimeService = Depends(get_fincrime)):
    return svc.fc_confirm_recovery(org, cid, rid, actor)


@router.post("/cases/{cid}/recoveries/{rid}/reject", dependencies=[_approve])
def reject_recovery(cid: str, rid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FincrimeService = Depends(get_fincrime)):
    return svc.fc_reject_recovery(org, cid, rid, body.reason, actor)


@router.post("/cases/{cid}/decision", dependencies=[_prepare])
def propose_decision(cid: str, body: DecisionBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FincrimeService = Depends(get_fincrime)):
    return svc.fc_propose_decision(org, cid, _d(body), actor)


@router.post("/cases/{cid}/decision/approve", dependencies=[_approve])
def approve_decision(cid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FincrimeService = Depends(get_fincrime)):
    return svc.fc_approve_decision(org, cid, actor, body.note)


@router.post("/cases/{cid}/decision/reject", dependencies=[_approve])
def reject_decision(cid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FincrimeService = Depends(get_fincrime)):
    return svc.fc_reject_decision(org, cid, body.reason, actor)


@router.post("/cases/{cid}/reopen", dependencies=[_approve])
def reopen_case(cid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: FincrimeService = Depends(get_fincrime)):
    return svc.fc_reopen_case(org, cid, body.reason, actor)
