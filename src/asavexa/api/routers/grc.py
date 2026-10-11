"""Governance, Risk and Compliance endpoints. Thin: the rules live in asavexa.grc.

Viewing needs audit:read. Recording risks, actions and obligations needs grc:prepare. Approving a risk acceptance, verifying a completed action and
setting the risk appetite need grc:approve, and the service refuses the person who asked for or did the work."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from ...grc.service import GrcService
from ...identity.domain.permissions import AUDIT_READ, GRC_APPROVE, GRC_PREPARE
from ..deps import get_current_actor, get_current_org, get_grc, require_permission

router = APIRouter(prefix="/grc", tags=["Governance, Risk and Compliance"], dependencies=[Depends(require_permission(AUDIT_READ))])
_prepare = Depends(require_permission(GRC_PREPARE))
_approve = Depends(require_permission(GRC_APPROVE))


class RiskBody(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    owner: Optional[str] = None
    inherent_l: Optional[int] = None
    inherent_i: Optional[int] = None
    residual_l: Optional[int] = None
    residual_i: Optional[int] = None
    residual_justification: Optional[str] = None
    treatment: Optional[str] = None
    next_review: Optional[str] = None
    control_ids: Optional[List[str]] = None


class AcceptBody(BaseModel):
    justification: str
    review_by: str


class NoteBody(BaseModel):
    note: str = ""


class ActionBody(BaseModel):
    risk_id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    owner: Optional[str] = None
    due: Optional[str] = None


class DoneBody(BaseModel):
    note: str
    evidence_ids: List[str] = []


class ObligationBody(BaseModel):
    title: Optional[str] = None
    source_type: Optional[str] = None
    authority: Optional[str] = None
    source_ref: Optional[str] = None
    source_url: Optional[str] = None
    description: Optional[str] = None
    owner: Optional[str] = None
    frequency: Optional[str] = None
    next_due: Optional[str] = None
    control_ids: Optional[List[str]] = None


class MetBody(BaseModel):
    met_on: str
    note: str
    evidence_ids: List[str] = []


class AppetiteBody(BaseModel):
    appetite: int


def _d(body) -> dict:
    """Only the fields the caller actually sent (so an edit changes only what was asked)."""
    return body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)


@router.get("/options")
def options(org: str = Depends(get_current_org), svc: GrcService = Depends(get_grc)): return svc.options(org)


@router.get("/dashboard")
def dashboard(org: str = Depends(get_current_org), svc: GrcService = Depends(get_grc)): return svc.dashboard(org)


@router.put("/appetite", dependencies=[_approve])
def set_appetite(body: AppetiteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: GrcService = Depends(get_grc)):
    return svc.set_appetite(org, body.appetite, actor)


@router.get("/risks")
def risks(status: Optional[str] = None, category: Optional[str] = None, org: str = Depends(get_current_org), svc: GrcService = Depends(get_grc)): return svc.list_risks(org, status, category)


@router.post("/risks", status_code=201, dependencies=[_prepare])
def create_risk(body: RiskBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: GrcService = Depends(get_grc)):
    return svc.create_risk(org, _d(body), actor)


@router.get("/risks/{risk_id}")
def get_risk(risk_id: str, org: str = Depends(get_current_org), svc: GrcService = Depends(get_grc)): return svc.get_risk(org, risk_id)


@router.put("/risks/{risk_id}", dependencies=[_prepare])
def update_risk(risk_id: str, body: RiskBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: GrcService = Depends(get_grc)):
    return svc.update_risk(org, risk_id, _d(body), actor)


@router.post("/risks/{risk_id}/treat", dependencies=[_prepare])
def treat(risk_id: str, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: GrcService = Depends(get_grc)):
    return svc.start_treatment(org, risk_id, actor)


@router.post("/risks/{risk_id}/accept", dependencies=[_prepare])
def accept(risk_id: str, body: AcceptBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: GrcService = Depends(get_grc)):
    return svc.request_acceptance(org, risk_id, body.justification, body.review_by, actor)


@router.post("/risks/{risk_id}/approve-acceptance", dependencies=[_approve])
def approve_acceptance(risk_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: GrcService = Depends(get_grc)):
    return svc.approve_acceptance(org, risk_id, actor, body.note)


@router.post("/risks/{risk_id}/reject-acceptance", dependencies=[_approve])
def reject_acceptance(risk_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: GrcService = Depends(get_grc)):
    return svc.reject_acceptance(org, risk_id, actor, body.note)


@router.post("/risks/{risk_id}/reopen", dependencies=[_prepare])
def reopen(risk_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: GrcService = Depends(get_grc)):
    return svc.reopen_risk(org, risk_id, body.note, actor)


@router.post("/risks/{risk_id}/close", dependencies=[_prepare])
def close(risk_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: GrcService = Depends(get_grc)):
    return svc.close_risk(org, risk_id, body.note, actor)


@router.get("/actions")
def actions(risk_id: Optional[str] = None, status: Optional[str] = None, org: str = Depends(get_current_org), svc: GrcService = Depends(get_grc)): return svc.list_actions(org, risk_id, status)


@router.post("/actions", status_code=201, dependencies=[_prepare])
def create_action(body: ActionBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: GrcService = Depends(get_grc)):
    return svc.create_action(org, _d(body), actor)


@router.put("/actions/{action_id}", dependencies=[_prepare])
def update_action(action_id: str, body: ActionBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: GrcService = Depends(get_grc)):
    return svc.update_action(org, action_id, _d(body), actor)


@router.post("/actions/{action_id}/complete", dependencies=[_prepare])
def complete_action(action_id: str, body: DoneBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: GrcService = Depends(get_grc)):
    return svc.complete_action(org, action_id, body.note, body.evidence_ids, actor)


@router.post("/actions/{action_id}/verify", dependencies=[_approve])
def verify_action(action_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: GrcService = Depends(get_grc)):
    return svc.verify_action(org, action_id, actor, body.note)


@router.post("/actions/{action_id}/send-back", dependencies=[_approve])
def send_back_action(action_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: GrcService = Depends(get_grc)):
    return svc.reject_action(org, action_id, actor, body.note)


@router.post("/actions/{action_id}/cancel", dependencies=[_prepare])
def cancel_action(action_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: GrcService = Depends(get_grc)):
    return svc.cancel_action(org, action_id, body.note, actor)


@router.get("/obligations")
def obligations(state: Optional[str] = None, org: str = Depends(get_current_org), svc: GrcService = Depends(get_grc)): return svc.list_obligations(org, state)


@router.post("/obligations", status_code=201, dependencies=[_prepare])
def create_obligation(body: ObligationBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: GrcService = Depends(get_grc)):
    return svc.create_obligation(org, _d(body), actor)


@router.get("/obligations/{obligation_id}")
def get_obligation(obligation_id: str, org: str = Depends(get_current_org), svc: GrcService = Depends(get_grc)): return svc.get_obligation(org, obligation_id)


@router.put("/obligations/{obligation_id}", dependencies=[_prepare])
def update_obligation(obligation_id: str, body: ObligationBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: GrcService = Depends(get_grc)):
    return svc.update_obligation(org, obligation_id, _d(body), actor)


@router.post("/obligations/{obligation_id}/met", dependencies=[_prepare])
def mark_met(obligation_id: str, body: MetBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: GrcService = Depends(get_grc)):
    return svc.mark_met(org, obligation_id, body.met_on, body.note, body.evidence_ids, actor)


@router.post("/obligations/{obligation_id}/retire", dependencies=[_prepare])
def retire(obligation_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: GrcService = Depends(get_grc)):
    return svc.retire_obligation(org, obligation_id, body.note, actor)


@router.get("/export")
def export(org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: GrcService = Depends(get_grc)):
    out = svc.export_csv(org, actor)
    return Response(content=out["content"], media_type=out["content_type"], headers={"Content-Disposition": f'attachment; filename="{out["filename"]}"', "Cache-Control": "no-store"})
