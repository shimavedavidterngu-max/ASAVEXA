"""Projects and grants endpoints (records and evidence): projects with a typed award and budget lines, spending and receipts reviewed by a different person. Thin: the rules live in asavexa.projects.

Viewing needs audit:read. Creating projects, budget lines, submitting, withdrawing and proposing entries need projects:prepare. Approving or returning a project, deciding entries, closing a project and the setting need projects:approve;
the service refuses the person who submitted the project or proposed the entry. The organisation always comes from the signed-in session. Nothing here moves money or applies any funder's rules."""
from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...identity.domain.permissions import AUDIT_READ, PROJ_APPROVE, PROJ_PREPARE
from ...projects.service import ProjectsService
from ..deps import get_current_actor, get_current_org, get_projects, require_permission

router = APIRouter(prefix="/projects", tags=["Projects"], dependencies=[Depends(require_permission(AUDIT_READ))])
_prepare = Depends(require_permission(PROJ_PREPARE))
_approve = Depends(require_permission(PROJ_APPROVE))


class ReasonBody(BaseModel):
    reason: str = ""


class NoteBody(BaseModel):
    note: Optional[str] = None


class SettingBody(BaseModel):
    ending_soon_days: Optional[Any] = None


class ProjectBody(BaseModel):
    title: Optional[str] = None
    funder_ref: Optional[str] = None
    currency: Optional[str] = None
    award: Optional[Any] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None


class BudgetBody(BaseModel):
    category: Optional[str] = None
    amount: Optional[Any] = None


class EntryBody(BaseModel):
    entry_type: Optional[str] = None
    budget_no: Optional[Any] = None
    amount: Optional[Any] = None
    entry_date: Optional[str] = None
    description: Optional[str] = None


def _d(body) -> dict:
    """Only the fields the caller actually sent."""
    return body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)


@router.get("/options")
def options(org: str = Depends(get_current_org), svc: ProjectsService = Depends(get_projects)): return svc.pj_options(org)


@router.get("/overview")
def overview(org: str = Depends(get_current_org), svc: ProjectsService = Depends(get_projects)): return svc.pj_overview(org)


@router.get("/setting")
def setting(org: str = Depends(get_current_org), svc: ProjectsService = Depends(get_projects)): return svc.pj_get_setting(org)


@router.put("/setting", dependencies=[_approve])
def set_setting(body: SettingBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ProjectsService = Depends(get_projects)):
    return svc.pj_set_setting(org, _d(body), actor)


@router.get("/projects")
def projects(status: Optional[str] = None, org: str = Depends(get_current_org), svc: ProjectsService = Depends(get_projects)): return svc.pj_list_projects(org, status)


@router.post("/projects", status_code=201, dependencies=[_prepare])
def create_project(body: ProjectBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ProjectsService = Depends(get_projects)):
    return svc.pj_create_project(org, _d(body), actor)


@router.get("/projects/{pid}")
def get_project(pid: str, org: str = Depends(get_current_org), svc: ProjectsService = Depends(get_projects)): return svc.pj_get_project(org, pid)


@router.post("/projects/{pid}/budget", dependencies=[_prepare])
def add_budget(pid: str, body: BudgetBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ProjectsService = Depends(get_projects)):
    return svc.pj_add_budget(org, pid, _d(body), actor)


@router.post("/projects/{pid}/budget/{no}/remove", dependencies=[_prepare])
def remove_budget(pid: str, no: int, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ProjectsService = Depends(get_projects)):
    return svc.pj_remove_budget(org, pid, no, body.reason, actor)


@router.post("/projects/{pid}/submit", dependencies=[_prepare])
def submit(pid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ProjectsService = Depends(get_projects)):
    return svc.pj_submit(org, pid, _d(body), actor)


@router.post("/projects/{pid}/withdraw", dependencies=[_prepare])
def withdraw(pid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ProjectsService = Depends(get_projects)):
    return svc.pj_withdraw_project(org, pid, body.reason, actor)


@router.post("/projects/{pid}/approve", dependencies=[_approve])
def approve(pid: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ProjectsService = Depends(get_projects)):
    return svc.pj_approve_project(org, pid, _d(body), actor)


@router.post("/projects/{pid}/return", dependencies=[_approve])
def return_project(pid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ProjectsService = Depends(get_projects)):
    return svc.pj_return_project(org, pid, body.reason, actor)


@router.post("/projects/{pid}/close", dependencies=[_approve])
def close_project(pid: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ProjectsService = Depends(get_projects)):
    return svc.pj_close_project(org, pid, body.reason, actor)


@router.post("/projects/{pid}/entries", dependencies=[_prepare])
def add_entry(pid: str, body: EntryBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ProjectsService = Depends(get_projects)):
    return svc.pj_add_entry(org, pid, _d(body), actor)


@router.post("/projects/{pid}/entries/{no}/approve", dependencies=[_approve])
def approve_entry(pid: str, no: int, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ProjectsService = Depends(get_projects)):
    return svc.pj_approve_entry(org, pid, no, _d(body), actor)


@router.post("/projects/{pid}/entries/{no}/reject", dependencies=[_approve])
def reject_entry(pid: str, no: int, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ProjectsService = Depends(get_projects)):
    return svc.pj_reject_entry(org, pid, no, body.reason, actor)
