"""IT audit endpoints (records and evidence): change-management records and tests, application-control definitions and tests, two-person approval.
Thin: the rules live in asavexa.itaudit.

Viewing needs audit:read. Recording changes and controls, planning and concluding tests and submitting them need itaudit:prepare. Approving or sending back a test,
voiding a change, retiring a control and setting the policy need itaudit:approve; the service refuses the person whose work is being decided.
The organisation always comes from the signed-in session. Nothing here connects to or tests any system."""
from typing import Any, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...identity.domain.permissions import AUDIT_READ, ITAUDIT_APPROVE, ITAUDIT_PREPARE
from ...itaudit.service import ItAuditService
from ..deps import get_current_actor, get_current_org, get_itaudit, require_permission

router = APIRouter(prefix="/itaudit", tags=["IT audit"], dependencies=[Depends(require_permission(AUDIT_READ))])
_prepare = Depends(require_permission(ITAUDIT_PREPARE))
_approve = Depends(require_permission(ITAUDIT_APPROVE))


class ReasonBody(BaseModel):
    reason: str = ""


class NoteBody(BaseModel):
    note: str = ""


class PolicyBody(BaseModel):
    emergency_ratify_days: Optional[Any] = None
    retest_days: Optional[Any] = None


class ChangeBody(BaseModel):
    system: Optional[str] = None
    asset_id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    change_type: Optional[str] = None
    risk: Optional[str] = None
    requested_by: Optional[str] = None
    approved_by_name: Optional[str] = None
    approved_on: Optional[str] = None
    ticket_ref: Optional[str] = None
    implemented_on: Optional[str] = None
    testing_evidence: Optional[str] = None
    rollback_plan: Optional[str] = None
    evidence_ids: List[str] = []


class ControlBody(BaseModel):
    system: Optional[str] = None
    asset_id: Optional[str] = None
    name: Optional[str] = None
    control_type: Optional[str] = None
    description: Optional[str] = None
    expected_result: Optional[str] = None
    frequency: Optional[str] = None
    tolerable: Optional[Any] = None


class ChangeTestBody(BaseModel):
    title: Optional[str] = None
    system: Optional[str] = None
    period_from: Optional[str] = None
    period_to: Optional[str] = None
    sample_size: Optional[Any] = None
    seed: Optional[str] = None
    tolerable: Optional[Any] = None


class ControlTestBody(BaseModel):
    title: Optional[str] = None
    control_id: Optional[str] = None


class ItemBody(BaseModel):
    result: Optional[str] = None
    note: Optional[str] = None


class CaseBody(BaseModel):
    description: Optional[str] = None
    expected: Optional[str] = None
    actual: Optional[str] = None
    result: Optional[str] = None
    note: Optional[str] = None
    performed_on: Optional[str] = None
    evidence_ids: List[str] = []


def _d(body) -> dict:
    """Only the fields the caller actually sent."""
    return body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)


@router.get("/options")
def options(org: str = Depends(get_current_org), svc: ItAuditService = Depends(get_itaudit)): return svc.ia_options(org)


@router.get("/overview")
def overview(org: str = Depends(get_current_org), svc: ItAuditService = Depends(get_itaudit)): return svc.ia_overview(org)


@router.get("/policy")
def policy(org: str = Depends(get_current_org), svc: ItAuditService = Depends(get_itaudit)): return svc.ia_get_policy(org)


@router.put("/policy", dependencies=[_approve])
def set_policy(body: PolicyBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ItAuditService = Depends(get_itaudit)):
    return svc.ia_set_policy(org, _d(body), actor)


@router.get("/changes")
def changes(system: Optional[str] = None, flagged: Optional[bool] = None, status: Optional[str] = None, org: str = Depends(get_current_org), svc: ItAuditService = Depends(get_itaudit)):
    return svc.ia_list_changes(org, system, flagged, status)


@router.post("/changes", status_code=201, dependencies=[_prepare])
def record_change(body: ChangeBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ItAuditService = Depends(get_itaudit)):
    return svc.ia_record_change(org, _d(body), actor)


@router.get("/changes/{cid}")
def get_change(cid: str, org: str = Depends(get_current_org), svc: ItAuditService = Depends(get_itaudit)): return svc.ia_get_change(org, cid)


@router.post("/changes/{cid}/void", dependencies=[_approve])
def void_change(cid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ItAuditService = Depends(get_itaudit)):
    return svc.ia_void_change(org, cid, body.reason, actor)


@router.get("/controls")
def controls(system: Optional[str] = None, org: str = Depends(get_current_org), svc: ItAuditService = Depends(get_itaudit)): return svc.ia_list_controls(org, system)


@router.post("/controls", status_code=201, dependencies=[_prepare])
def define_control(body: ControlBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ItAuditService = Depends(get_itaudit)):
    return svc.ia_define_control(org, _d(body), actor)


@router.get("/controls/{cid}")
def get_control(cid: str, org: str = Depends(get_current_org), svc: ItAuditService = Depends(get_itaudit)): return svc.ia_get_control(org, cid)


@router.post("/controls/{cid}/retire", dependencies=[_approve])
def retire_control(cid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ItAuditService = Depends(get_itaudit)):
    return svc.ia_retire_control(org, cid, body.reason, actor)


@router.get("/tests")
def tests(kind: Optional[str] = None, status: Optional[str] = None, org: str = Depends(get_current_org), svc: ItAuditService = Depends(get_itaudit)): return svc.ia_list_tests(org, kind, status)


@router.post("/tests/change", status_code=201, dependencies=[_prepare])
def plan_change_test(body: ChangeTestBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ItAuditService = Depends(get_itaudit)):
    return svc.ia_plan_change_test(org, _d(body), actor)


@router.post("/tests/control", status_code=201, dependencies=[_prepare])
def plan_control_test(body: ControlTestBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ItAuditService = Depends(get_itaudit)):
    return svc.ia_plan_control_test(org, _d(body), actor)


@router.get("/tests/{tid}")
def get_test(tid: str, org: str = Depends(get_current_org), svc: ItAuditService = Depends(get_itaudit)): return svc.ia_get_test(org, tid)


@router.post("/tests/{tid}/items/{iid}", dependencies=[_prepare])
def conclude_item(tid: str, iid: str, body: ItemBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ItAuditService = Depends(get_itaudit)):
    return svc.ia_conclude_item(org, tid, iid, _d(body), actor)


@router.post("/tests/{tid}/cases", status_code=201, dependencies=[_prepare])
def add_case(tid: str, body: CaseBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ItAuditService = Depends(get_itaudit)):
    return svc.ia_add_case(org, tid, _d(body), actor)


@router.post("/tests/{tid}/submit", dependencies=[_prepare])
def submit_test(tid: str, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ItAuditService = Depends(get_itaudit)):
    return svc.ia_submit_test(org, tid, actor)


@router.post("/tests/{tid}/withdraw", dependencies=[_prepare])
def withdraw_test(tid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ItAuditService = Depends(get_itaudit)):
    return svc.ia_withdraw_test(org, tid, body.reason, actor)


@router.post("/tests/{tid}/approve", dependencies=[_approve])
def approve_test(tid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ItAuditService = Depends(get_itaudit)):
    return svc.ia_approve_test(org, tid, actor, body.note)


@router.post("/tests/{tid}/reject", dependencies=[_approve])
def reject_test(tid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ItAuditService = Depends(get_itaudit)):
    return svc.ia_reject_test(org, tid, body.reason, actor)
