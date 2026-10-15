"""Insurance and claims endpoints (records and evidence): policies, claims, settlements decided by a different person, and amounts received. Thin: the rules live in asavexa.insurance.

Viewing needs audit:read. Recording policies and claims, proposing an outcome and recording money received need insurance:prepare. Approving or rejecting an outcome, cancelling a policy and setting the policy need insurance:approve;
the service refuses the person who proposed the outcome. The organisation always comes from the signed-in session. Nothing here contacts an insurer or gives insurance advice."""
from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...identity.domain.permissions import AUDIT_READ, INS_APPROVE, INS_PREPARE
from ...insurance.service import InsuranceService
from ..deps import get_current_actor, get_current_org, get_insurance, require_permission

router = APIRouter(prefix="/insurance", tags=["Insurance"], dependencies=[Depends(require_permission(AUDIT_READ))])
_prepare = Depends(require_permission(INS_PREPARE))
_approve = Depends(require_permission(INS_APPROVE))


class ReasonBody(BaseModel):
    reason: str = ""


class NoteBody(BaseModel):
    note: Optional[str] = None


class SettingBody(BaseModel):
    warning_days: Optional[Any] = None


class PolicyBody(BaseModel):
    insurer: Optional[str] = None
    policy_number: Optional[str] = None
    cover_type: Optional[str] = None
    covers: Optional[str] = None
    currency: Optional[str] = None
    sum_insured: Optional[Any] = None
    premium: Optional[Any] = None
    excess: Optional[Any] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class ClaimBody(BaseModel):
    loss_date: Optional[str] = None
    reported_date: Optional[str] = None
    description: Optional[str] = None
    claimed_amount: Optional[Any] = None
    claim_number: Optional[str] = None


class OutcomeBody(BaseModel):
    outcome: Optional[str] = None
    amount: Optional[Any] = None
    note: Optional[str] = None


class ReceiptBody(BaseModel):
    amount: Optional[Any] = None
    received_on: Optional[str] = None
    reference: Optional[str] = None


def _d(body) -> dict:
    """Only the fields the caller actually sent."""
    return body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)


@router.get("/options")
def options(org: str = Depends(get_current_org), svc: InsuranceService = Depends(get_insurance)): return svc.ic_options(org)


@router.get("/overview")
def overview(org: str = Depends(get_current_org), svc: InsuranceService = Depends(get_insurance)): return svc.ic_overview(org)


@router.get("/setting")
def setting(org: str = Depends(get_current_org), svc: InsuranceService = Depends(get_insurance)): return svc.ic_get_policy(org)


@router.put("/setting", dependencies=[_approve])
def set_setting(body: SettingBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: InsuranceService = Depends(get_insurance)):
    return svc.ic_set_policy(org, _d(body), actor)


@router.get("/policies")
def policies(status: Optional[str] = None, org: str = Depends(get_current_org), svc: InsuranceService = Depends(get_insurance)): return svc.ic_list_policies(org, status)


@router.post("/policies", status_code=201, dependencies=[_prepare])
def add_policy(body: PolicyBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: InsuranceService = Depends(get_insurance)):
    return svc.ic_add_policy(org, _d(body), actor)


@router.get("/policies/{pid}")
def get_policy(pid: str, org: str = Depends(get_current_org), svc: InsuranceService = Depends(get_insurance)): return svc.ic_get_policy_record(org, pid)


@router.post("/policies/{pid}/cancel", dependencies=[_approve])
def cancel_policy(pid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: InsuranceService = Depends(get_insurance)):
    return svc.ic_cancel_policy(org, pid, body.reason, actor)


@router.post("/policies/{pid}/claims", status_code=201, dependencies=[_prepare])
def add_claim(pid: str, body: ClaimBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: InsuranceService = Depends(get_insurance)):
    return svc.ic_add_claim(org, pid, _d(body), actor)


@router.get("/claims")
def claims(status: Optional[str] = None, org: str = Depends(get_current_org), svc: InsuranceService = Depends(get_insurance)): return svc.ic_list_claims(org, status)


@router.get("/claims/{cid}")
def get_claim(cid: str, org: str = Depends(get_current_org), svc: InsuranceService = Depends(get_insurance)): return svc.ic_get_claim(org, cid)


@router.post("/claims/{cid}/proposals", dependencies=[_prepare])
def propose_outcome(cid: str, body: OutcomeBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: InsuranceService = Depends(get_insurance)):
    return svc.ic_propose_outcome(org, cid, _d(body), actor)


@router.post("/claims/{cid}/proposals/{no}/approve", dependencies=[_approve])
def approve_outcome(cid: str, no: int, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: InsuranceService = Depends(get_insurance)):
    return svc.ic_approve_outcome(org, cid, no, _d(body), actor)


@router.post("/claims/{cid}/proposals/{no}/reject", dependencies=[_approve])
def reject_outcome(cid: str, no: int, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: InsuranceService = Depends(get_insurance)):
    return svc.ic_reject_outcome(org, cid, no, body.reason, actor)


@router.post("/claims/{cid}/receipts", dependencies=[_prepare])
def record_receipt(cid: str, body: ReceiptBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: InsuranceService = Depends(get_insurance)):
    return svc.ic_record_receipt(org, cid, _d(body), actor)
