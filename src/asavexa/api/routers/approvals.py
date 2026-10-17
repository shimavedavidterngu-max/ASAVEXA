"""Approval workflows endpoints (records and evidence). Thin: the rules live in asavexa.approvals.

Viewing needs audit:read. Proposing policies, submitting requests and withdrawing your own need approvals:prepare. Activating or retiring policies, deciding a request step and the settings need approvals:approve; the service refuses the person who submitted the item, and refuses a second decision from the same person on one request. Nothing here connects to a payment, purchasing or other system: an approval is a record, not an instruction to anyone.
The organisation always comes from the signed-in session."""
from typing import Any, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...identity.domain.permissions import AUDIT_READ, APW_APPROVE, APW_PREPARE
from ...approvals.service import ApprovalsService
from ..deps import get_current_actor, get_current_org, get_approvals, require_permission

router = APIRouter(prefix="/approvals", tags=["Approval workflows"], dependencies=[Depends(require_permission(AUDIT_READ))])
_prepare = Depends(require_permission(APW_PREPARE))
_approve = Depends(require_permission(APW_APPROVE))


class NoteBody(BaseModel):
    note: Optional[str] = None


class PolicyBody(BaseModel):
    name: Optional[str] = None
    request_kind: Optional[str] = None
    steps: Optional[Any] = None
    description: Optional[str] = None


class ReasonBody(BaseModel):
    reason: str = ""


class RequestBody(BaseModel):
    policy_id: Optional[str] = None
    title: Optional[str] = None
    request_ref: Optional[str] = None
    amount: Optional[Any] = None
    currency: Optional[str] = None
    description: Optional[str] = None


class SettingBody(BaseModel):
    stale_days: Optional[Any] = None


def _d(body) -> dict:
    """Only the fields the caller actually sent."""
    return body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)


@router.get("/options")
def options(org: str = Depends(get_current_org), svc: ApprovalsService = Depends(get_approvals)):
    return svc.apw_options(org)


@router.get("/overview")
def overview(org: str = Depends(get_current_org), svc: ApprovalsService = Depends(get_approvals)):
    return svc.apw_overview(org)


@router.get("/setting")
def setting(org: str = Depends(get_current_org), svc: ApprovalsService = Depends(get_approvals)):
    return svc.apw_get_setting(org)


@router.put("/setting", dependencies=[_approve])
def set_setting(body: SettingBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ApprovalsService = Depends(get_approvals)):
    return svc.apw_set_setting(org, _d(body), actor)


@router.get("/policies")
def policies(status: Optional[str] = None, org: str = Depends(get_current_org), svc: ApprovalsService = Depends(get_approvals)):
    return svc.apw_list_policies(org, status)


@router.post("/policies", status_code=201, dependencies=[_prepare])
def add_policy(body: PolicyBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ApprovalsService = Depends(get_approvals)):
    return svc.apw_add_policy(org, _d(body), actor)


@router.get("/policies/{pid}")
def get_policy(pid: str, org: str = Depends(get_current_org), svc: ApprovalsService = Depends(get_approvals)):
    return svc.apw_get_policy(org, pid)


@router.post("/policies/{pid}/activate", dependencies=[_approve])
def activate_policy(pid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ApprovalsService = Depends(get_approvals)):
    return svc.apw_activate_policy(org, pid, _d(body), actor)


@router.post("/policies/{pid}/reject", dependencies=[_approve])
def reject_policy(pid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ApprovalsService = Depends(get_approvals)):
    return svc.apw_reject_policy(org, pid, body.reason, actor)


@router.post("/policies/{pid}/retire", dependencies=[_approve])
def retire_policy(pid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ApprovalsService = Depends(get_approvals)):
    return svc.apw_retire_policy(org, pid, body.reason, actor)


@router.get("/requests")
def requests(status: Optional[str] = None, org: str = Depends(get_current_org), svc: ApprovalsService = Depends(get_approvals)):
    return svc.apw_list_requests(org, status)


@router.post("/requests", status_code=201, dependencies=[_prepare])
def submit_request(body: RequestBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ApprovalsService = Depends(get_approvals)):
    return svc.apw_submit_request(org, _d(body), actor)


@router.get("/requests/{rid}")
def get_request(rid: str, org: str = Depends(get_current_org), svc: ApprovalsService = Depends(get_approvals)):
    return svc.apw_get_request(org, rid)


@router.post("/requests/{rid}/approve", dependencies=[_approve])
def approve_request(rid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ApprovalsService = Depends(get_approvals)):
    return svc.apw_decide(org, rid, True, _d(body), actor)


@router.post("/requests/{rid}/reject", dependencies=[_approve])
def reject_request(rid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ApprovalsService = Depends(get_approvals)):
    return svc.apw_decide(org, rid, False, body.reason, actor)


@router.post("/requests/{rid}/withdraw", dependencies=[_prepare])
def withdraw_request(rid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ApprovalsService = Depends(get_approvals)):
    return svc.apw_withdraw(org, rid, body.reason, actor)

