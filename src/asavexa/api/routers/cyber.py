"""Cybersecurity endpoints (defensive record-keeping). Thin: the rules live in asavexa.cyber.

Viewing needs audit:read. Recording assets, vulnerabilities, incidents and access reviews, and marking a fix done, needs cyber:prepare. Verifying a fix,
accepting a risk, closing an incident, approving an access review or a report, and setting the policy need cyber:approve; the service refuses the person
who did or asked for the work."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from ...cyber.service import CyberService
from ...identity.domain.permissions import AUDIT_READ, CYBER_APPROVE, CYBER_PREPARE
from ..deps import get_current_actor, get_current_org, get_cyber, require_permission

router = APIRouter(prefix="/cyber", tags=["Cybersecurity"], dependencies=[Depends(require_permission(AUDIT_READ))])
_prepare = Depends(require_permission(CYBER_PREPARE))
_approve = Depends(require_permission(CYBER_APPROVE))


class AssetBody(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    owner: Optional[str] = None
    criticality: Optional[str] = None
    data_class: Optional[str] = None
    location: Optional[str] = None
    notes: Optional[str] = None


class VulnBody(BaseModel):
    asset_id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[str] = None
    cve: Optional[str] = None
    source: Optional[str] = None
    found_date: Optional[str] = None


class NoteBody(BaseModel):
    note: str = ""


class FixBody(BaseModel):
    note: str = ""
    evidence_ids: List[str] = []


class AcceptBody(BaseModel):
    reason: str = ""
    until: str = ""


class IncidentBody(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    severity: Optional[str] = None
    detected_date: Optional[str] = None
    asset_ids: List[str] = []
    personal_data_involved: Optional[bool] = None


class TimelineBody(BaseModel):
    note: str = ""
    date: Optional[str] = None


class CloseBody(BaseModel):
    lessons_learned: str = ""
    notification_decision: str = ""


class ReviewBody(BaseModel):
    name: Optional[str] = None
    scope: Optional[str] = None
    due_date: Optional[str] = None


class EntryBody(BaseModel):
    subject: Optional[str] = None
    system: Optional[str] = None
    access: Optional[str] = None


class DecisionBody(BaseModel):
    decision: str
    note: str = ""


class PolicyBody(BaseModel):
    sla_days: Optional[Dict[str, Any]] = None
    acceptance_max_days: Optional[int] = None


class ReportBody(BaseModel):
    title: str


def _d(body) -> dict:
    """Only the fields the caller actually sent."""
    return body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)


_V, _I, _R = "/vulnerabilities/{vid}", "/incidents/{iid}", "/reviews/{rid}"


@router.get("/options")
def options(org: str = Depends(get_current_org), svc: CyberService = Depends(get_cyber)): return svc.options(org)


@router.get("/overview")
def overview(org: str = Depends(get_current_org), svc: CyberService = Depends(get_cyber)): return svc.overview(org)


@router.put("/policy", dependencies=[_approve])
def set_policy(body: PolicyBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: CyberService = Depends(get_cyber)):
    return svc.set_policy(org, _d(body), actor)


@router.get("/assets")
def assets(org: str = Depends(get_current_org), svc: CyberService = Depends(get_cyber)): return svc.list_assets(org)


@router.post("/assets", status_code=201, dependencies=[_prepare])
def create_asset(body: AssetBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: CyberService = Depends(get_cyber)):
    return svc.create_asset(org, _d(body), actor)


@router.get("/assets/{asset_id}")
def get_asset(asset_id: str, org: str = Depends(get_current_org), svc: CyberService = Depends(get_cyber)): return svc.get_asset(org, asset_id)


@router.put("/assets/{asset_id}", dependencies=[_prepare])
def update_asset(asset_id: str, body: AssetBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: CyberService = Depends(get_cyber)):
    return svc.update_asset(org, asset_id, _d(body), actor)


@router.post("/assets/{asset_id}/retire", dependencies=[_prepare])
def retire_asset(asset_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: CyberService = Depends(get_cyber)):
    return svc.retire_asset(org, asset_id, body.note, actor)


@router.get("/vulnerabilities")
def vulnerabilities(status: Optional[str] = None, severity: Optional[str] = None, asset_id: Optional[str] = None, org: str = Depends(get_current_org), svc: CyberService = Depends(get_cyber)):
    return svc.list_vulnerabilities(org, status or None, severity or None, asset_id or None)


@router.post("/vulnerabilities", status_code=201, dependencies=[_prepare])
def create_vulnerability(body: VulnBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: CyberService = Depends(get_cyber)):
    return svc.create_vulnerability(org, _d(body), actor)


@router.get(_V)
def get_vulnerability(vid: str, org: str = Depends(get_current_org), svc: CyberService = Depends(get_cyber)): return svc.get_vulnerability(org, vid)


@router.post(_V + "/start", dependencies=[_prepare])
def start_vulnerability(vid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: CyberService = Depends(get_cyber)):
    return svc.start_vulnerability(org, vid, body.note, actor)


@router.post(_V + "/fixed", dependencies=[_prepare])
def mark_fixed(vid: str, body: FixBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: CyberService = Depends(get_cyber)):
    return svc.mark_fixed(org, vid, body.note, body.evidence_ids, actor)


@router.post(_V + "/verify", dependencies=[_approve])
def verify_fix(vid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: CyberService = Depends(get_cyber)):
    return svc.verify_fix(org, vid, actor, body.note)


@router.post(_V + "/reject-fix", dependencies=[_approve])
def reject_fix(vid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: CyberService = Depends(get_cyber)):
    return svc.reject_fix(org, vid, actor, body.note)


@router.post(_V + "/acceptance", dependencies=[_prepare])
def request_acceptance(vid: str, body: AcceptBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: CyberService = Depends(get_cyber)):
    return svc.request_acceptance(org, vid, body.reason, body.until, actor)


@router.post(_V + "/acceptance/approve", dependencies=[_approve])
def approve_acceptance(vid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: CyberService = Depends(get_cyber)):
    return svc.approve_acceptance(org, vid, actor, body.note)


@router.post(_V + "/acceptance/reject", dependencies=[_approve])
def reject_acceptance(vid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: CyberService = Depends(get_cyber)):
    return svc.reject_acceptance(org, vid, actor, body.note)


@router.post(_V + "/reopen", dependencies=[_prepare])
def reopen_vulnerability(vid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: CyberService = Depends(get_cyber)):
    return svc.reopen_vulnerability(org, vid, body.note, actor)


@router.get("/incidents")
def incidents(status: Optional[str] = None, org: str = Depends(get_current_org), svc: CyberService = Depends(get_cyber)): return svc.list_incidents(org, status or None)


@router.post("/incidents", status_code=201, dependencies=[_prepare])
def create_incident(body: IncidentBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: CyberService = Depends(get_cyber)):
    return svc.create_incident(org, _d(body), actor)


@router.get(_I)
def get_incident(iid: str, org: str = Depends(get_current_org), svc: CyberService = Depends(get_cyber)): return svc.get_incident(org, iid)


@router.post(_I + "/timeline", status_code=201, dependencies=[_prepare])
def add_timeline(iid: str, body: TimelineBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: CyberService = Depends(get_cyber)):
    return svc.add_timeline(org, iid, body.note, body.date, actor)


@router.post(_I + "/investigate", dependencies=[_prepare])
def investigate_incident(iid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: CyberService = Depends(get_cyber)):
    return svc.investigate_incident(org, iid, body.note, actor)


@router.post(_I + "/contain", dependencies=[_prepare])
def contain_incident(iid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: CyberService = Depends(get_cyber)):
    return svc.contain_incident(org, iid, body.note, actor)


@router.post(_I + "/resolve", dependencies=[_prepare])
def resolve_incident(iid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: CyberService = Depends(get_cyber)):
    return svc.resolve_incident(org, iid, body.note, actor)


@router.post(_I + "/close", dependencies=[_approve])
def close_incident(iid: str, body: CloseBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: CyberService = Depends(get_cyber)):
    return svc.close_incident(org, iid, body.lessons_learned, body.notification_decision, actor)


@router.post(_I + "/reopen", dependencies=[_approve])
def reopen_incident(iid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: CyberService = Depends(get_cyber)):
    return svc.reopen_incident(org, iid, actor, body.note)


@router.get("/reviews")
def reviews(org: str = Depends(get_current_org), svc: CyberService = Depends(get_cyber)): return svc.list_reviews(org)


@router.post("/reviews", status_code=201, dependencies=[_prepare])
def create_review(body: ReviewBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: CyberService = Depends(get_cyber)):
    return svc.create_review(org, _d(body), actor)


@router.get(_R)
def get_review(rid: str, org: str = Depends(get_current_org), svc: CyberService = Depends(get_cyber)): return svc.get_review(org, rid)


@router.post(_R + "/entries", status_code=201, dependencies=[_prepare])
def add_entry(rid: str, body: EntryBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: CyberService = Depends(get_cyber)):
    return svc.add_entry(org, rid, _d(body), actor)


@router.post(_R + "/entries/{eid}/decide", dependencies=[_prepare])
def decide_entry(rid: str, eid: str, body: DecisionBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: CyberService = Depends(get_cyber)):
    return svc.decide_entry(org, rid, eid, body.decision, body.note, actor)


@router.post(_R + "/entries/{eid}/removed", dependencies=[_prepare])
def confirm_removed(rid: str, eid: str, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: CyberService = Depends(get_cyber)):
    return svc.confirm_removed(org, rid, eid, actor)


@router.post(_R + "/submit", dependencies=[_prepare])
def submit_review(rid: str, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: CyberService = Depends(get_cyber)):
    return svc.submit_review(org, rid, actor)


@router.post(_R + "/approve", dependencies=[_approve])
def approve_review(rid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: CyberService = Depends(get_cyber)):
    return svc.approve_review(org, rid, actor, body.note)


@router.post(_R + "/reject", dependencies=[_approve])
def reject_review(rid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: CyberService = Depends(get_cyber)):
    return svc.reject_review(org, rid, actor, body.note)


@router.get("/reports")
def reports(org: str = Depends(get_current_org), svc: CyberService = Depends(get_cyber)): return svc.list_reports(org)


@router.post("/reports", status_code=201, dependencies=[_prepare])
def create_report(body: ReportBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: CyberService = Depends(get_cyber)):
    return svc.create_report(org, body.title, actor)


@router.get("/reports/{report_id}")
def get_report(report_id: str, org: str = Depends(get_current_org), svc: CyberService = Depends(get_cyber)): return svc.get_report(org, report_id)


@router.post("/reports/{report_id}/submit", dependencies=[_prepare])
def submit_report(report_id: str, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: CyberService = Depends(get_cyber)):
    return svc.submit_report(org, report_id, actor)


@router.post("/reports/{report_id}/approve", dependencies=[_approve])
def approve_report(report_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: CyberService = Depends(get_cyber)):
    return svc.approve_report(org, report_id, actor, body.note)


@router.post("/reports/{report_id}/reject", dependencies=[_approve])
def reject_report(report_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: CyberService = Depends(get_cyber)):
    return svc.reject_report(org, report_id, actor, body.note)


@router.get("/reports/{report_id}/export")
def export_report(report_id: str, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: CyberService = Depends(get_cyber)):
    out = svc.export_csv(org, report_id, actor)
    return Response(content=out["content"], media_type=out["content_type"], headers={"Content-Disposition": f'attachment; filename="{out["filename"]}"', "Cache-Control": "no-store"})
