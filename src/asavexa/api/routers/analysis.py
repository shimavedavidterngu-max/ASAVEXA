"""Financial Analysis workspace endpoints. Thin: the rules live in asavexa.analysis.

Viewing needs reporting:read. Preparing (classification, budgets, commentary, scenarios, reports) needs analysis:prepare. Approving needs analysis:approve.
The service itself refuses to let the person who submitted a report approve or reject it, so the rule holds even for a direct API call."""
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from ...analysis.service import AnalysisService
from ...evidence.services.vault import EvidenceVault
from ...identity.domain.permissions import ANALYSIS_APPROVE, ANALYSIS_PREPARE, REPORTING_READ
from ..deps import get_analysis, get_current_actor, get_current_org, get_evidence_vault, require_permission

router = APIRouter(prefix="/analysis", tags=["Financial Analysis"], dependencies=[Depends(require_permission(REPORTING_READ))])
_prepare = Depends(require_permission(ANALYSIS_PREPARE))
_approve = Depends(require_permission(ANALYSIS_APPROVE))


class ConfigBody(BaseModel):
    tags: Optional[Dict[str, Optional[str]]] = None
    thresholds: Optional[Dict[str, str]] = None


class BudgetBody(BaseModel):
    period_id: str
    lines: Dict[str, str]
    note: str = ""


class CommentBody(BaseModel):
    period_id: str
    account_id: str
    text: str


class ScenarioBody(BaseModel):
    name: str
    base_period_id: str
    assumptions: Dict[str, object]


class BreakevenBody(BaseModel):
    fixed_costs: str
    price: str
    variable_cost: str


class ReportBody(BaseModel):
    period_id: str
    title: str
    note: str = ""
    scenario_ids: List[str] = []
    evidence_ids: List[str] = []


class ReportEditBody(BaseModel):
    title: Optional[str] = None
    note: Optional[str] = None
    scenario_ids: Optional[List[str]] = None
    evidence_ids: Optional[List[str]] = None


class NoteBody(BaseModel):
    note: str = ""


def _evidence(vault: EvidenceVault, org: str, ids: Optional[List[str]]):
    """Evidence must already exist in this organisation's vault; only a reference is kept, never a copy."""
    if ids is None:
        return None
    out = []
    for eid in dict.fromkeys(ids):
        e = vault.get_evidence(org, eid)
        out.append({"id": e.id, "filename": e.original_filename, "type": e.type.value, "status": e.status.value, "file_hash": e.file_hash})
    return out


@router.get("/overview")
def overview(period_id: str, org: str = Depends(get_current_org), svc: AnalysisService = Depends(get_analysis)): return svc.overview(org, period_id)


@router.get("/ratios")
def ratios(period_id: str, org: str = Depends(get_current_org), svc: AnalysisService = Depends(get_analysis)): return svc.ratios(org, period_id)


@router.get("/variance")
def variance(period_id: str, org: str = Depends(get_current_org), svc: AnalysisService = Depends(get_analysis)): return svc.variance(org, period_id)


@router.get("/config")
def get_config(org: str = Depends(get_current_org), svc: AnalysisService = Depends(get_analysis)): return svc.get_config(org)


@router.put("/config", dependencies=[_prepare])
def set_config(body: ConfigBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: AnalysisService = Depends(get_analysis)):
    return svc.set_config(org, body.tags, body.thresholds, actor)


@router.get("/budget")
def get_budget(period_id: str, org: str = Depends(get_current_org), svc: AnalysisService = Depends(get_analysis)): return svc.get_budget(org, period_id)


@router.put("/budget", dependencies=[_prepare])
def set_budget(body: BudgetBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: AnalysisService = Depends(get_analysis)):
    return svc.set_budget(org, body.period_id, body.lines, body.note, actor)


@router.get("/budget-variance")
def budget_variance(period_id: str, org: str = Depends(get_current_org), svc: AnalysisService = Depends(get_analysis)): return svc.budget_variance(org, period_id)


@router.post("/commentary", status_code=201, dependencies=[_prepare])
def add_comment(body: CommentBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: AnalysisService = Depends(get_analysis)):
    return svc.add_comment(org, body.period_id, body.account_id, body.text, actor)


@router.get("/suggest")
def suggest(period_id: str, org: str = Depends(get_current_org), svc: AnalysisService = Depends(get_analysis)): return svc.suggest(org, period_id)


@router.get("/scenarios")
def scenarios(period_id: Optional[str] = None, org: str = Depends(get_current_org), svc: AnalysisService = Depends(get_analysis)): return svc.list_scenarios(org, period_id)


@router.post("/scenarios", status_code=201, dependencies=[_prepare])
def save_scenario(body: ScenarioBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: AnalysisService = Depends(get_analysis)):
    return svc.save_scenario(org, body.name, body.base_period_id, body.assumptions, actor)


@router.put("/scenarios/{scenario_id}", dependencies=[_prepare])
def update_scenario(scenario_id: str, body: ScenarioBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: AnalysisService = Depends(get_analysis)):
    return svc.save_scenario(org, body.name, body.base_period_id, body.assumptions, actor, scenario_id=scenario_id)


@router.get("/scenarios/{scenario_id}/run")
def run_scenario(scenario_id: str, org: str = Depends(get_current_org), svc: AnalysisService = Depends(get_analysis)): return svc.run_scenario(org, scenario_id)


@router.post("/breakeven")
def breakeven(body: BreakevenBody, svc: AnalysisService = Depends(get_analysis)): return svc.breakeven(body.fixed_costs, body.price, body.variable_cost)


@router.get("/reports")
def reports(org: str = Depends(get_current_org), svc: AnalysisService = Depends(get_analysis)): return svc.list_reports(org)


@router.post("/reports", status_code=201, dependencies=[_prepare])
def create_report(body: ReportBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: AnalysisService = Depends(get_analysis), vault: EvidenceVault = Depends(get_evidence_vault)):
    return svc.create_report(org, body.period_id, body.title, body.note, body.scenario_ids, _evidence(vault, org, body.evidence_ids), actor)


@router.get("/reports/{report_id}")
def get_report(report_id: str, org: str = Depends(get_current_org), svc: AnalysisService = Depends(get_analysis)): return svc.get_report(org, report_id)


@router.put("/reports/{report_id}", dependencies=[_prepare])
def update_report(report_id: str, body: ReportEditBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: AnalysisService = Depends(get_analysis), vault: EvidenceVault = Depends(get_evidence_vault)):
    return svc.update_report(org, report_id, body.title, body.note, body.scenario_ids, _evidence(vault, org, body.evidence_ids), actor)


@router.post("/reports/{report_id}/submit", dependencies=[_prepare])
def submit_report(report_id: str, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: AnalysisService = Depends(get_analysis)):
    return svc.submit_report(org, report_id, actor)


@router.post("/reports/{report_id}/approve", dependencies=[_approve])
def approve_report(report_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: AnalysisService = Depends(get_analysis)):
    return svc.approve_report(org, report_id, actor, body.note)


@router.post("/reports/{report_id}/reject", dependencies=[_approve])
def reject_report(report_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: AnalysisService = Depends(get_analysis)):
    return svc.reject_report(org, report_id, actor, body.note)


@router.get("/reports/{report_id}/verify")
def verify_report(report_id: str, org: str = Depends(get_current_org), svc: AnalysisService = Depends(get_analysis)): return svc.verify_report(org, report_id)


@router.get("/reports/{report_id}/export")
def export_report(report_id: str, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: AnalysisService = Depends(get_analysis)):
    out = svc.export_csv(org, report_id, actor)
    return Response(content=out["content"], media_type=out["content_type"], headers={"Content-Disposition": f'attachment; filename="{out["filename"]}"', "Cache-Control": "no-store"})
