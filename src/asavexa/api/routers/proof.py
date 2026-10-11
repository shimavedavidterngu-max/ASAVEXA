"""Proof-to-Report Graph and the live architecture check. Read-only; needs reporting:read."""
from fastapi import APIRouter, Depends, HTTPException, Request

from ...identity.domain.permissions import REPORTING_READ
from ...proofgraph.architecture import check_architecture
from ...proofgraph.graph import REPORT_TYPES, ProofGraphError, build_graph
from ...reporting.services.service import ReportingService
from ..deps import get_current_actor, get_current_org, get_reporting_service, require_permission

router = APIRouter(prefix="/proof", tags=["Proof-to-Report Graph"], dependencies=[Depends(require_permission(REPORTING_READ))])


@router.get("/graph")
def graph(period_id: str, report: str = "balance_sheet", org_id: str = Depends(get_current_org), actor: str = Depends(get_current_actor),
          service: ReportingService = Depends(get_reporting_service)):
    """Every figure in the report linked to its journals and evidence, with tie-out checks. Report: balance_sheet or income_statement."""
    try:
        return build_graph(service, org_id, period_id, report, actor)
    except ProofGraphError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))


@router.get("/reports")
def report_types():
    return {"reports": list(REPORT_TYPES)}


@router.get("/architecture")
def architecture(request: Request):
    """Is every layer of the architecture present and wired? Loads each module and checks each API prefix is mounted."""
    return check_architecture([getattr(r, "path", "") for r in request.app.routes])
