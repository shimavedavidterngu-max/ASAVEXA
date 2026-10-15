"""Payroll and workforce cost endpoints (records and evidence): payroll runs worked out from typed pay lines and reviewed by a different person. Thin: the rules live in asavexa.payroll.

Viewing needs audit:read. Creating runs, adding and removing pay lines, submitting and withdrawing need payroll:prepare. Approving or returning a submitted run and setting the review limit need payroll:approve;
the service refuses the person who submitted the run. The organisation always comes from the signed-in session. Nothing here calculates tax or any statutory amount or pays anyone."""
from typing import Any, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...identity.domain.permissions import AUDIT_READ, PAY_APPROVE, PAY_PREPARE
from ...payroll.service import PayrollService
from ..deps import get_current_actor, get_current_org, get_payroll, require_permission

router = APIRouter(prefix="/payroll", tags=["Payroll"], dependencies=[Depends(require_permission(AUDIT_READ))])
_prepare = Depends(require_permission(PAY_PREPARE))
_approve = Depends(require_permission(PAY_APPROVE))


class ReasonBody(BaseModel):
    reason: str = ""


class NoteBody(BaseModel):
    note: Optional[str] = None


class SettingBody(BaseModel):
    review_limit: Optional[Any] = None


class RunBody(BaseModel):
    label: Optional[str] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    currency: Optional[str] = None


class LineBody(BaseModel):
    staff_ref: Optional[str] = None
    department: Optional[str] = None
    base_pay: Optional[Any] = None
    allowances: Optional[Any] = None
    deductions: Optional[List[Any]] = None
    employer_contributions: Optional[Any] = None


def _d(body) -> dict:
    """Only the fields the caller actually sent."""
    return body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)


@router.get("/options")
def options(org: str = Depends(get_current_org), svc: PayrollService = Depends(get_payroll)): return svc.pw_options(org)


@router.get("/overview")
def overview(org: str = Depends(get_current_org), svc: PayrollService = Depends(get_payroll)): return svc.pw_overview(org)


@router.get("/setting")
def setting(org: str = Depends(get_current_org), svc: PayrollService = Depends(get_payroll)): return svc.pw_get_setting(org)


@router.put("/setting", dependencies=[_approve])
def set_setting(body: SettingBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PayrollService = Depends(get_payroll)):
    return svc.pw_set_setting(org, _d(body), actor)


@router.get("/runs")
def runs(status: Optional[str] = None, org: str = Depends(get_current_org), svc: PayrollService = Depends(get_payroll)): return svc.pw_list_runs(org, status)


@router.post("/runs", status_code=201, dependencies=[_prepare])
def create_run(body: RunBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PayrollService = Depends(get_payroll)):
    return svc.pw_create_run(org, _d(body), actor)


@router.get("/runs/{rid}")
def get_run(rid: str, org: str = Depends(get_current_org), svc: PayrollService = Depends(get_payroll)): return svc.pw_get_run(org, rid)


@router.post("/runs/{rid}/lines", dependencies=[_prepare])
def add_line(rid: str, body: LineBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PayrollService = Depends(get_payroll)):
    return svc.pw_add_line(org, rid, _d(body), actor)


@router.post("/runs/{rid}/lines/{no}/remove", dependencies=[_prepare])
def remove_line(rid: str, no: int, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PayrollService = Depends(get_payroll)):
    return svc.pw_remove_line(org, rid, no, body.reason, actor)


@router.post("/runs/{rid}/submit", dependencies=[_prepare])
def submit(rid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PayrollService = Depends(get_payroll)):
    return svc.pw_submit(org, rid, _d(body), actor)


@router.post("/runs/{rid}/withdraw", dependencies=[_prepare])
def withdraw(rid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PayrollService = Depends(get_payroll)):
    return svc.pw_withdraw_run(org, rid, body.reason, actor)


@router.post("/runs/{rid}/approve", dependencies=[_approve])
def approve(rid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PayrollService = Depends(get_payroll)):
    return svc.pw_approve_run(org, rid, _d(body), actor)


@router.post("/runs/{rid}/return", dependencies=[_approve])
def return_run(rid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PayrollService = Depends(get_payroll)):
    return svc.pw_return_run(org, rid, body.reason, actor)
