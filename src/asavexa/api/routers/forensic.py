"""Forensic Accounting and Investigation endpoints. Thin: the rules live in asavexa.forensic.

Investigations are confidential, so even viewing needs forensic:read, which ordinary operational roles do not hold. Working a case needs forensic:prepare;
approving findings and reports needs forensic:approve, and the service refuses the person who prepared or submitted the item."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from ...evidence.services.vault import EvidenceVault
from ...forensic.service import ForensicService
from ...identity.domain.permissions import FORENSIC_APPROVE, FORENSIC_PREPARE, FORENSIC_READ
from ..deps import get_current_actor, get_current_org, get_evidence_vault, get_forensic, require_permission

router = APIRouter(prefix="/forensic", tags=["Forensic Accounting"], dependencies=[Depends(require_permission(FORENSIC_READ))])
_prepare = Depends(require_permission(FORENSIC_PREPARE))
_approve = Depends(require_permission(FORENSIC_APPROVE))


class CaseBody(BaseModel):
    title: str
    description: str = ""
    case_type: str = "OTHER"


class NoteBody(BaseModel):
    note: str = ""


class EvidenceBody(BaseModel):
    evidence_id: str
    note: str = ""


class RunBody(BaseModel):
    scope: Dict[str, Any]
    tests: List[str]
    params: Optional[Dict[str, Any]] = None


class FindingBody(BaseModel):
    title: str
    description: str
    severity: str = "MEDIUM"
    journal_ids: List[str] = []
    evidence_ids: List[str] = []
    run_id: Optional[str] = None


class ReportBody(BaseModel):
    title: str


@router.get("/options")
def options(svc: ForensicService = Depends(get_forensic)): return svc.case_options()


@router.get("/cases")
def cases(org: str = Depends(get_current_org), svc: ForensicService = Depends(get_forensic)): return svc.list_cases(org)


@router.post("/cases", status_code=201, dependencies=[_prepare])
def create_case(body: CaseBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ForensicService = Depends(get_forensic)):
    return svc.create_case(org, body.title, body.description, body.case_type, actor)


@router.get("/cases/{case_id}")
def get_case(case_id: str, org: str = Depends(get_current_org), svc: ForensicService = Depends(get_forensic)): return svc.get_case(org, case_id)


@router.put("/cases/{case_id}", dependencies=[_prepare])
def update_case(case_id: str, body: CaseBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ForensicService = Depends(get_forensic)):
    return svc.update_case(org, case_id, body.title, body.description, actor)


@router.post("/cases/{case_id}/close", dependencies=[_approve])
def close_case(case_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ForensicService = Depends(get_forensic)):
    return svc.close_case(org, case_id, actor, body.note)


@router.post("/cases/{case_id}/evidence", status_code=201, dependencies=[_prepare])
def add_evidence(case_id: str, body: EvidenceBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ForensicService = Depends(get_forensic)):
    return svc.add_evidence(org, case_id, body.evidence_id, body.note, actor)


@router.get("/cases/{case_id}/custody")
def verify_custody(case_id: str, org: str = Depends(get_current_org), svc: ForensicService = Depends(get_forensic)): return svc.verify_custody(org, case_id)


@router.post("/cases/{case_id}/analytics", status_code=201, dependencies=[_prepare])
def run_analytics(case_id: str, body: RunBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ForensicService = Depends(get_forensic)):
    return svc.run_analytics(org, case_id, body.scope, body.tests, body.params, actor)


@router.get("/runs/{run_id}")
def get_run(run_id: str, org: str = Depends(get_current_org), svc: ForensicService = Depends(get_forensic)): return svc.get_run(org, run_id)


@router.post("/cases/{case_id}/findings", status_code=201, dependencies=[_prepare])
def create_finding(case_id: str, body: FindingBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ForensicService = Depends(get_forensic)):
    return svc.create_finding(org, case_id, body.title, body.description, body.severity, body.journal_ids, body.evidence_ids, body.run_id, actor)


@router.put("/findings/{finding_id}", dependencies=[_prepare])
def update_finding(finding_id: str, body: FindingBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ForensicService = Depends(get_forensic)):
    return svc.update_finding(org, finding_id, body.title, body.description, body.severity, body.journal_ids, body.evidence_ids, actor)


@router.delete("/findings/{finding_id}", dependencies=[_prepare])
def discard_finding(finding_id: str, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ForensicService = Depends(get_forensic)): return svc.discard_finding(org, finding_id, actor)


@router.post("/findings/{finding_id}/submit", dependencies=[_prepare])
def submit_finding(finding_id: str, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ForensicService = Depends(get_forensic)): return svc.submit_finding(org, finding_id, actor)


@router.post("/findings/{finding_id}/approve", dependencies=[_approve])
def approve_finding(finding_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ForensicService = Depends(get_forensic)):
    return svc.approve_finding(org, finding_id, actor, body.note)


@router.post("/findings/{finding_id}/reject", dependencies=[_approve])
def reject_finding(finding_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ForensicService = Depends(get_forensic)):
    return svc.reject_finding(org, finding_id, actor, body.note)


@router.post("/cases/{case_id}/reports", status_code=201, dependencies=[_prepare])
def create_report(case_id: str, body: ReportBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ForensicService = Depends(get_forensic)):
    return svc.create_report(org, case_id, body.title, actor)


@router.get("/reports/{report_id}")
def get_report(report_id: str, org: str = Depends(get_current_org), svc: ForensicService = Depends(get_forensic)): return svc.get_report(org, report_id)


@router.post("/reports/{report_id}/submit", dependencies=[_prepare])
def submit_report(report_id: str, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ForensicService = Depends(get_forensic)): return svc.submit_report(org, report_id, actor)


@router.post("/reports/{report_id}/approve", dependencies=[_approve])
def approve_report(report_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ForensicService = Depends(get_forensic)):
    return svc.approve_report(org, report_id, actor, body.note)


@router.post("/reports/{report_id}/reject", dependencies=[_approve])
def reject_report(report_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ForensicService = Depends(get_forensic)):
    return svc.reject_report(org, report_id, actor, body.note)


@router.get("/reports/{report_id}/export")
def export_report(report_id: str, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: ForensicService = Depends(get_forensic)):
    out = svc.export_csv(org, report_id, actor)
    return Response(content=out["content"], media_type=out["content_type"], headers={"Content-Disposition": f'attachment; filename="{out["filename"]}"', "Cache-Control": "no-store"})
