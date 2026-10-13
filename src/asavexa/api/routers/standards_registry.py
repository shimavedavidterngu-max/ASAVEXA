"""Verified Standards Registry endpoints. Thin: the rules live in asavexa.standards.registry.

Viewing needs audit:read. Adding and submitting a source needs grc:prepare. Approving, sending back and withdrawing need grc:approve, and the service
refuses an approver who added or submitted the source."""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...identity.domain.permissions import AUDIT_READ, GRC_APPROVE, GRC_PREPARE
from ...standards.registry import StandardsRegistry
from ..deps import get_current_actor, get_current_org, get_standards_registry, require_permission

router = APIRouter(prefix="/standards-registry", tags=["Verified Standards Registry"], dependencies=[Depends(require_permission(AUDIT_READ))])
_prepare = Depends(require_permission(GRC_PREPARE))
_approve = Depends(require_permission(GRC_APPROVE))


class SourceBody(BaseModel):
    framework: str
    title: str
    url: str
    authority: str
    version: str
    effective_from: str
    review_by: str
    summary: str = ""
    jurisdiction: Optional[str] = None


class NoteBody(BaseModel):
    note: str = ""


class ReasonBody(BaseModel):
    reason: str


@router.get("/coverage")
def coverage(jurisdiction: Optional[str] = None, org: str = Depends(get_current_org), svc: StandardsRegistry = Depends(get_standards_registry)):
    return svc.coverage(org, jurisdiction)


@router.get("/sources")
def list_sources(status: Optional[str] = None, framework: Optional[str] = None, org: str = Depends(get_current_org), svc: StandardsRegistry = Depends(get_standards_registry)):
    return {"sources": svc.list_sources(org, status, framework)}


@router.get("/sources/{source_id}")
def get_source(source_id: str, org: str = Depends(get_current_org), svc: StandardsRegistry = Depends(get_standards_registry)):
    return svc.get_source(org, source_id)


@router.post("/sources", status_code=201, dependencies=[_prepare])
def add_source(body: SourceBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: StandardsRegistry = Depends(get_standards_registry)):
    return svc.add_source(org, actor, body.framework, body.title, body.url, body.authority, body.version, body.effective_from, body.review_by, body.summary, body.jurisdiction)


@router.post("/sources/{source_id}/submit", dependencies=[_prepare])
def submit(source_id: str, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: StandardsRegistry = Depends(get_standards_registry)):
    return svc.submit(org, source_id, actor)


@router.post("/sources/{source_id}/approve", dependencies=[_approve])
def approve(source_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: StandardsRegistry = Depends(get_standards_registry)):
    return svc.approve(org, source_id, actor, body.note)


@router.post("/sources/{source_id}/send-back", dependencies=[_approve])
def send_back(source_id: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: StandardsRegistry = Depends(get_standards_registry)):
    return svc.send_back(org, source_id, actor, body.reason)


@router.post("/sources/{source_id}/withdraw", dependencies=[_approve])
def withdraw(source_id: str, body: ReasonBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: StandardsRegistry = Depends(get_standards_registry)):
    return svc.withdraw(org, source_id, actor, body.reason)
