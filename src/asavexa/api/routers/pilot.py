"""Real-world pilot endpoints (an accounting firm and its small-business clients). Thin: the rules live in asavexa.pilot.

Two kinds of caller:
- the FIRM running the pilot (needs pilot:manage to set it up and see results);
- a CLIENT organisation taking part, which sees only its own entries and a redacted view, and can record time, issues, Passport use and one survey.
Adding a client needs pilot:manage in the firm AND org:manage_settings in the client organisation, plus a reference to the client's written consent.
Measured results only ever include client organisations the asking person can read themselves."""
from datetime import datetime, timezone
from typing import Dict, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...identity.domain.errors import PermissionDeniedError
from ...identity.domain.permissions import LEDGER_READ, ORG_MANAGE_SETTINGS, PILOT_MANAGE
from ...identity.services.service import IdentityService
from ...pilot.errors import PilotForbiddenError
from ...pilot.evaluate import DEFAULT_TARGETS, MIN_N, TARGET_LABELS, LIMITS
from ...pilot.report import to_markdown
from ...pilot.results import compute_results
from ...pilot.service import (ISSUE_KINDS, MAX_CLIENTS, MIN_GROUP_FOR_AVERAGE, PASSPORT_OUTCOMES, PASSPORT_PURPOSES, SCORES, SEVERITIES, TIME_KINDS, PilotService)
from ..deps import get_audit_repository, get_current_actor, get_current_org, get_identity_service, get_pilot, get_session, require_permission

router = APIRouter(prefix="/pilot", tags=["Real Pilot"])
_manage = Depends(require_permission(PILOT_MANAGE))
_member = Depends(require_permission(LEDGER_READ))     # anyone who can read the books of the organisation may record what they experienced
EVENT_WINDOW = 20000


class PilotBody(BaseModel):
    name: str
    start_date: str
    end_date: Optional[str] = None
    notes: str = ""
    targets: Optional[Dict[str, float]] = None


class TargetsBody(BaseModel):
    targets: Dict[str, float]


class StatusBody(BaseModel):
    status: str


class ClientBody(BaseModel):
    client_org_id: str
    label: str
    consent_reference: str
    kickoff: Optional[str] = None
    baseline: Optional[Dict[str, Optional[int]]] = None


class ClientUpdateBody(BaseModel):
    label: Optional[str] = None
    kickoff: Optional[str] = None
    baseline: Optional[Dict[str, Optional[int]]] = None


class ReasonBody(BaseModel):
    reason: str


class TimeBody(BaseModel):
    client_org_id: Optional[str] = None
    kind: str
    minutes: int
    performed_on: str
    baseline_minutes: Optional[int] = None
    note: str = ""


class IssueBody(BaseModel):
    client_org_id: Optional[str] = None
    kind: str
    severity: str
    text: str


class ResolveBody(BaseModel):
    resolution: str


class PassportUseBody(BaseModel):
    client_org_id: Optional[str] = None
    purpose: str
    outcome: str
    saved_minutes: Optional[int] = None
    note: str = ""


class SurveyBody(BaseModel):
    round: str = "GENERAL"
    scores: Dict[str, Optional[int]]
    comment: str = ""


def _has(identity: IdentityService, actor: str, org: str, perm: str) -> bool:
    try:
        identity.require_permission(actor, org, perm)
        return True
    except PermissionDeniedError:
        return False


def _firm(svc: PilotService, org: str, pid: str) -> str:
    return svc.firm_for(org, pid)


def _own_client(org: str, firm: str, client_org: Optional[str]) -> str:
    """A client organisation always records about itself; the firm must say which client."""
    if org != firm:
        return org
    if not client_org:
        raise PilotForbiddenError("Say which client organisation this is about.")
    return client_org


def build_results(svc: PilotService, session, identity: IdentityService, actor: str, org: str, pid: str, include_comments: bool = False) -> dict:
    from ...audit.repository import AuditRepository  # noqa: F401  (documented dependency)
    from ..db.audit_sqlalchemy_repository import SqlAlchemyAuditRepository
    from .passport import gather_inputs

    audit = SqlAlchemyAuditRepository(session)
    firm_ids = [m.user_id for m in identity.list_members(org) if m.status.value == "ACTIVE"]
    return compute_results(svc, org, pid, can_read=lambda o: _has(identity, actor, o, LEDGER_READ), fetch_inputs=lambda o: gather_inputs(session, o),
                           fetch_events=lambda o: audit.list_recent_for_org(o, EVENT_WINDOW)[0], firm_user_ids=firm_ids, now=datetime.now(timezone.utc), include_comments=include_comments)


# ------------------------------------------------------------------ orientation
@router.get("/guide", dependencies=[_member])
def guide():
    return {"time_kinds": TIME_KINDS, "issue_kinds": ISSUE_KINDS, "severities": SEVERITIES, "passport_purposes": PASSPORT_PURPOSES, "passport_outcomes": PASSPORT_OUTCOMES,
            "scores": {k: {"min": lo, "max": hi, "required": req} for k, (lo, hi, req) in SCORES.items()}, "default_targets": DEFAULT_TARGETS, "target_labels": TARGET_LABELS,
            "limits": LIMITS, "min_n": MIN_N, "max_clients": MAX_CLIENTS, "min_group_for_average": MIN_GROUP_FOR_AVERAGE,
            "honesty": "A pilot of a few organisations shows whether ASAVEXA is workable for them. It cannot prove it works for everyone. Measures marked Reported are what people said."}


@router.get("/me")
def me(actor: str = Depends(get_current_actor), org: str = Depends(get_current_org), identity: IdentityService = Depends(get_identity_service), svc: PilotService = Depends(get_pilot)):
    return {"can_manage": _has(identity, actor, org, PILOT_MANAGE), "can_record": _has(identity, actor, org, LEDGER_READ), "can_withdraw": _has(identity, actor, org, ORG_MANAGE_SETTINGS), "membership": svc.membership(org)}


@router.get("/eligible", dependencies=[_manage])
def eligible(actor: str = Depends(get_current_actor), org: str = Depends(get_current_org), identity: IdentityService = Depends(get_identity_service), svc: PilotService = Depends(get_pilot)):
    """Organisations the signed-in person administers (so they can give consent) that are not already in a pilot."""
    out = []
    for m in identity.memberships.list_for_user(actor):
        if m.status.value != "ACTIVE" or m.org_id == org or svc.is_active_client(m.org_id) or not _has(identity, actor, m.org_id, ORG_MANAGE_SETTINGS):
            continue
        o = identity.organisations.get(m.org_id)
        out.append({"org_id": m.org_id, "name": o.name if o else m.org_id})
    return sorted(out, key=lambda x: x["name"].lower())


# ------------------------------------------------------------------ the pilot itself (firm)
@router.get("/pilots", dependencies=[_manage])
def list_pilots(org: str = Depends(get_current_org), svc: PilotService = Depends(get_pilot)):
    return svc.list_pilots(org)


@router.post("/pilots", dependencies=[_manage], status_code=201)
def create_pilot(body: PilotBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PilotService = Depends(get_pilot)):
    return svc.create_pilot(org, actor, body.name, body.start_date, body.end_date, body.notes, body.targets)


@router.get("/pilots/{pid}", dependencies=[_manage])
def get_pilot_view(pid: str, org: str = Depends(get_current_org), svc: PilotService = Depends(get_pilot)):
    return svc.view(org, pid)


@router.put("/pilots/{pid}/targets", dependencies=[_manage])
def update_targets(pid: str, body: TargetsBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PilotService = Depends(get_pilot)):
    return svc.update_targets(org, actor, pid, body.targets)


@router.post("/pilots/{pid}/status", dependencies=[_manage])
def set_status(pid: str, body: StatusBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PilotService = Depends(get_pilot)):
    return svc.set_status(org, actor, pid, body.status)


# ------------------------------------------------------------------ clients
@router.post("/pilots/{pid}/clients", dependencies=[_manage], status_code=201)
def add_client(pid: str, body: ClientBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), identity: IdentityService = Depends(get_identity_service),
               svc: PilotService = Depends(get_pilot)):
    if not _has(identity, actor, body.client_org_id, ORG_MANAGE_SETTINGS):
        raise PilotForbiddenError("To add a client you must be an owner or administrator of that organisation yourself. That is how its consent is given.")
    return svc.add_client(org, actor, pid, body.client_org_id, body.label, body.consent_reference, body.kickoff, body.baseline)


@router.put("/pilots/{pid}/clients/{client_org_id}", dependencies=[_manage])
def update_client(pid: str, client_org_id: str, body: ClientUpdateBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PilotService = Depends(get_pilot)):
    return svc.update_client(org, actor, pid, client_org_id, body.label, body.kickoff, body.baseline)


@router.post("/pilots/{pid}/clients/{client_org_id}/remove", dependencies=[_manage])
def remove_client(pid: str, client_org_id: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PilotService = Depends(get_pilot)):
    return svc.remove_client(org, actor, pid, client_org_id, body.reason)


@router.post("/pilots/{pid}/leave")
def leave(pid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), identity: IdentityService = Depends(get_identity_service),
          svc: PilotService = Depends(get_pilot)):
    """A client organisation withdraws. Its owner/administrator can do this at any time, without the firm's agreement."""
    firm = _firm(svc, org, pid)
    if firm == org:
        raise PilotForbiddenError("The firm running a pilot cannot leave it. Complete the pilot instead.")
    if not _has(identity, actor, org, ORG_MANAGE_SETTINGS):
        raise PilotForbiddenError("Only an owner or administrator of your organisation can withdraw it from the pilot.")
    svc.remove_client(firm, actor, pid, org, body.reason)
    return {"left": True}


# ------------------------------------------------------------------ results
@router.get("/pilots/{pid}/results", dependencies=[_manage])
def results(pid: str, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), identity: IdentityService = Depends(get_identity_service),
            svc: PilotService = Depends(get_pilot), session=Depends(get_session)):
    return build_results(svc, session, identity, actor, org, pid, include_comments=True)


@router.get("/pilots/{pid}/report", dependencies=[_manage])
def report(pid: str, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), identity: IdentityService = Depends(get_identity_service),
           svc: PilotService = Depends(get_pilot), session=Depends(get_session)):
    r = build_results(svc, session, identity, actor, org, pid)
    return {"markdown": to_markdown(r, svc.snapshots(org, pid)), "results": r}


@router.post("/pilots/{pid}/snapshots", dependencies=[_manage], status_code=201)
def take_snapshot(pid: str, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), identity: IdentityService = Depends(get_identity_service),
                  svc: PilotService = Depends(get_pilot), session=Depends(get_session)):
    r = build_results(svc, session, identity, actor, org, pid)
    return svc.take_snapshot(org, actor, pid, r["evaluation"], r["clients_included"], r["clients_total"])


@router.get("/pilots/{pid}/snapshots", dependencies=[_manage])
def snapshots(pid: str, org: str = Depends(get_current_org), svc: PilotService = Depends(get_pilot)):
    return svc.snapshots(org, pid)


# ------------------------------------------------------------------ what people record (firm and clients)
@router.get("/pilots/{pid}/logs", dependencies=[_member])
def logs(pid: str, org: str = Depends(get_current_org), svc: PilotService = Depends(get_pilot)):
    return svc.logs(org, _firm(svc, org, pid), pid)


@router.post("/pilots/{pid}/time", dependencies=[_member], status_code=201)
def log_time(pid: str, body: TimeBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PilotService = Depends(get_pilot)):
    firm = _firm(svc, org, pid)
    return svc.log_time(org, actor, firm, pid, _own_client(org, firm, body.client_org_id), body.kind, body.minutes, body.performed_on, body.baseline_minutes, body.note)


@router.post("/pilots/{pid}/issues", dependencies=[_member], status_code=201)
def log_issue(pid: str, body: IssueBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PilotService = Depends(get_pilot)):
    firm = _firm(svc, org, pid)
    return svc.log_issue(org, actor, firm, pid, _own_client(org, firm, body.client_org_id), body.kind, body.severity, body.text)


@router.post("/pilots/{pid}/issues/{issue_id}/resolve", dependencies=[_manage])
def resolve_issue(pid: str, issue_id: str, body: ResolveBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PilotService = Depends(get_pilot)):
    return svc.resolve_issue(org, actor, pid, issue_id, body.resolution)


@router.post("/pilots/{pid}/passport-uses", dependencies=[_member], status_code=201)
def log_passport_use(pid: str, body: PassportUseBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PilotService = Depends(get_pilot)):
    firm = _firm(svc, org, pid)
    return svc.log_passport_use(org, actor, firm, pid, _own_client(org, firm, body.client_org_id), body.purpose, body.outcome, body.saved_minutes, body.note)


@router.get("/pilots/{pid}/survey", dependencies=[_member])
def my_survey(pid: str, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PilotService = Depends(get_pilot)):
    return svc.my_survey(org, actor, _firm(svc, org, pid), pid)


@router.post("/pilots/{pid}/survey", dependencies=[_member], status_code=201)
def submit_survey(pid: str, body: SurveyBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PilotService = Depends(get_pilot)):
    return svc.submit_survey(org, actor, _firm(svc, org, pid), pid, body.round, body.scores, body.comment)
