"""Business Development endpoints. Thin: the rules live in asavexa.bizdev.

Viewing needs reporting:read. Recording accounts, opportunities, activities and proposals needs bd:prepare. Approving a large discount, confirming a win,
setting targets and policy, and approving reports need bd:approve; the service refuses the person who proposed or requested the item."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from ...bizdev.service import BizDevService
from ...identity.domain.permissions import BD_APPROVE, BD_PREPARE, REPORTING_READ
from ..deps import get_bizdev, get_current_actor, get_current_org, require_permission

router = APIRouter(prefix="/bizdev", tags=["Business Development"], dependencies=[Depends(require_permission(REPORTING_READ))])
_prepare = Depends(require_permission(BD_PREPARE))
_approve = Depends(require_permission(BD_APPROVE))


class AccountBody(BaseModel):
    name: Optional[str] = None
    kind: Optional[str] = None
    sector: Optional[str] = None
    country: Optional[str] = None
    notes: Optional[str] = None
    contacts: Optional[List[Dict[str, Any]]] = None


class OpportunityBody(BaseModel):
    account_id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    source: Optional[str] = None
    currency: Optional[str] = None
    value: Optional[str] = None
    expected_close: Optional[str] = None
    stage: Optional[str] = None


class ActivityBody(BaseModel):
    type: Optional[str] = None
    date: Optional[str] = None
    summary: Optional[str] = None


class StageBody(BaseModel):
    stage: str
    note: str = ""


class NoteBody(BaseModel):
    note: str = ""


class ProposalBody(BaseModel):
    items: Optional[List[Dict[str, Any]]] = None
    discount_pct: Optional[str] = None
    valid_until: Optional[str] = None
    terms: Optional[str] = None
    evidence_ids: List[str] = []


class PolicyBody(BaseModel):
    probabilities: Optional[Dict[str, Any]] = None
    discount_limit_pct: Optional[str] = None
    stale_days: Optional[int] = None


class TargetBody(BaseModel):
    name: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None
    currency: Optional[str] = None
    amount: Optional[str] = None


class ReportBody(BaseModel):
    currency: str
    title: str


def _d(body) -> dict:
    """Only the fields the caller actually sent."""
    return body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)


_O = "/opportunities/{oid}"


@router.get("/options")
def options(org: str = Depends(get_current_org), svc: BizDevService = Depends(get_bizdev)): return svc.options(org)


@router.get("/overview")
def overview(org: str = Depends(get_current_org), svc: BizDevService = Depends(get_bizdev)): return svc.overview(org)


@router.put("/policy", dependencies=[_approve])
def set_policy(body: PolicyBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: BizDevService = Depends(get_bizdev)):
    return svc.set_policy(org, _d(body), actor)


@router.get("/accounts")
def accounts(org: str = Depends(get_current_org), svc: BizDevService = Depends(get_bizdev)): return svc.list_accounts(org)


@router.post("/accounts", status_code=201, dependencies=[_prepare])
def create_account(body: AccountBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: BizDevService = Depends(get_bizdev)):
    return svc.create_account(org, _d(body), actor)


@router.get("/accounts/{account_id}")
def get_account(account_id: str, org: str = Depends(get_current_org), svc: BizDevService = Depends(get_bizdev)): return svc.get_account(org, account_id)


@router.put("/accounts/{account_id}", dependencies=[_prepare])
def update_account(account_id: str, body: AccountBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: BizDevService = Depends(get_bizdev)):
    return svc.update_account(org, account_id, _d(body), actor)


@router.post("/accounts/{account_id}/archive", dependencies=[_prepare])
def archive_account(account_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: BizDevService = Depends(get_bizdev)):
    return svc.archive_account(org, account_id, body.note, actor)


@router.get("/opportunities")
def opportunities(stage: Optional[str] = None, account_id: Optional[str] = None, org: str = Depends(get_current_org), svc: BizDevService = Depends(get_bizdev)):
    return svc.list_opportunities(org, stage or None, account_id or None)


@router.post("/opportunities", status_code=201, dependencies=[_prepare])
def create_opportunity(body: OpportunityBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: BizDevService = Depends(get_bizdev)):
    return svc.create_opportunity(org, _d(body), actor)


@router.get(_O)
def get_opportunity(oid: str, org: str = Depends(get_current_org), svc: BizDevService = Depends(get_bizdev)): return svc.get_opportunity(org, oid)


@router.put(_O, dependencies=[_prepare])
def update_opportunity(oid: str, body: OpportunityBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: BizDevService = Depends(get_bizdev)):
    return svc.update_opportunity(org, oid, _d(body), actor)


@router.post(_O + "/activities", status_code=201, dependencies=[_prepare])
def add_activity(oid: str, body: ActivityBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: BizDevService = Depends(get_bizdev)):
    return svc.add_activity(org, oid, _d(body), actor)


@router.post(_O + "/stage", dependencies=[_prepare])
def move_stage(oid: str, body: StageBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: BizDevService = Depends(get_bizdev)):
    return svc.move_stage(org, oid, body.stage, body.note, actor)


@router.post(_O + "/lost", dependencies=[_prepare])
def mark_lost(oid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: BizDevService = Depends(get_bizdev)):
    return svc.mark_lost(org, oid, body.note, actor)


@router.post(_O + "/win/request", dependencies=[_prepare])
def request_win(oid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: BizDevService = Depends(get_bizdev)):
    return svc.request_win(org, oid, body.note, actor)


@router.post(_O + "/win/approve", dependencies=[_approve])
def approve_win(oid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: BizDevService = Depends(get_bizdev)):
    return svc.approve_win(org, oid, actor, body.note)


@router.post(_O + "/win/reject", dependencies=[_approve])
def reject_win(oid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: BizDevService = Depends(get_bizdev)):
    return svc.reject_win(org, oid, actor, body.note)


@router.post(_O + "/proposals", status_code=201, dependencies=[_prepare])
def create_proposal(oid: str, body: ProposalBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: BizDevService = Depends(get_bizdev)):
    return svc.create_proposal(org, oid, _d(body), actor)


@router.put(_O + "/proposals/{pid}", dependencies=[_prepare])
def update_proposal(oid: str, pid: str, body: ProposalBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: BizDevService = Depends(get_bizdev)):
    return svc.update_proposal(org, oid, pid, _d(body), actor)


@router.post(_O + "/proposals/{pid}/submit", dependencies=[_prepare])
def submit_proposal(oid: str, pid: str, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: BizDevService = Depends(get_bizdev)):
    return svc.submit_proposal(org, oid, pid, actor)


@router.post(_O + "/proposals/{pid}/approve", dependencies=[_approve])
def approve_proposal(oid: str, pid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: BizDevService = Depends(get_bizdev)):
    return svc.approve_proposal(org, oid, pid, actor, body.note)


@router.post(_O + "/proposals/{pid}/reject", dependencies=[_approve])
def reject_proposal(oid: str, pid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: BizDevService = Depends(get_bizdev)):
    return svc.reject_proposal(org, oid, pid, actor, body.note)


@router.post(_O + "/proposals/{pid}/send", dependencies=[_prepare])
def send_proposal(oid: str, pid: str, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: BizDevService = Depends(get_bizdev)):
    return svc.send_proposal(org, oid, pid, actor)


@router.post(_O + "/proposals/{pid}/accept", dependencies=[_prepare])
def accept_proposal(oid: str, pid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: BizDevService = Depends(get_bizdev)):
    return svc.accept_proposal(org, oid, pid, body.note, actor)


@router.post(_O + "/proposals/{pid}/decline", dependencies=[_prepare])
def decline_proposal(oid: str, pid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: BizDevService = Depends(get_bizdev)):
    return svc.decline_proposal(org, oid, pid, body.note, actor)


@router.get("/targets")
def targets(org: str = Depends(get_current_org), svc: BizDevService = Depends(get_bizdev)): return svc.list_targets(org)


@router.post("/targets", status_code=201, dependencies=[_approve])
def create_target(body: TargetBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: BizDevService = Depends(get_bizdev)):
    return svc.create_target(org, _d(body), actor)


@router.post("/targets/{target_id}/retire", dependencies=[_approve])
def retire_target(target_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: BizDevService = Depends(get_bizdev)):
    return svc.retire_target(org, target_id, body.note, actor)


@router.get("/reports")
def reports(org: str = Depends(get_current_org), svc: BizDevService = Depends(get_bizdev)): return svc.list_reports(org)


@router.post("/reports", status_code=201, dependencies=[_prepare])
def create_report(body: ReportBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: BizDevService = Depends(get_bizdev)):
    return svc.create_report(org, body.currency, body.title, actor)


@router.get("/reports/{report_id}")
def get_report(report_id: str, org: str = Depends(get_current_org), svc: BizDevService = Depends(get_bizdev)): return svc.get_report(org, report_id)


@router.post("/reports/{report_id}/submit", dependencies=[_prepare])
def submit_report(report_id: str, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: BizDevService = Depends(get_bizdev)):
    return svc.submit_report(org, report_id, actor)


@router.post("/reports/{report_id}/approve", dependencies=[_approve])
def approve_report(report_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: BizDevService = Depends(get_bizdev)):
    return svc.approve_report(org, report_id, actor, body.note)


@router.post("/reports/{report_id}/reject", dependencies=[_approve])
def reject_report(report_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: BizDevService = Depends(get_bizdev)):
    return svc.reject_report(org, report_id, actor, body.note)


@router.get("/reports/{report_id}/export")
def export_report(report_id: str, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: BizDevService = Depends(get_bizdev)):
    out = svc.export_csv(org, report_id, actor)
    return Response(content=out["content"], media_type=out["content_type"], headers={"Content-Disposition": f'attachment; filename="{out["filename"]}"', "Cache-Control": "no-store"})
