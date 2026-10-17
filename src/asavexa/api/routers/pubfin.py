"""Public Finance endpoints. Thin: the rules live in asavexa.pubfin.

Viewing needs reporting:read. Drafting and proposing needs pubfin:prepare. Approving budgets, virements, awards, grant spending and reports, and setting the
procurement policy, need pubfin:approve; the service refuses the person who proposed or submitted the item."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from ...identity.domain.permissions import PUBFIN_APPROVE, PUBFIN_PREPARE, REPORTING_READ
from ...pubfin.service import PubFinService
from ..deps import get_current_actor, get_current_org, get_pubfin, require_permission

router = APIRouter(prefix="/pubfin", tags=["Public Finance"], dependencies=[Depends(require_permission(REPORTING_READ))])
_prepare = Depends(require_permission(PUBFIN_PREPARE))
_approve = Depends(require_permission(PUBFIN_APPROVE))


class BudgetBody(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None
    currency: Optional[str] = None
    lines: Optional[List[Dict[str, Any]]] = None


class NoteBody(BaseModel):
    note: str = ""


class VirementBody(BaseModel):
    from_account: str
    to_account: str
    amount: str
    reason: str


class CommitmentBody(BaseModel):
    budget_id: str
    account_id: str
    vendor: str
    description: str
    amount: str
    date: str
    evidence_ids: List[str] = []


class SettleBody(BaseModel):
    settled_amount: str
    note: str


class ProcurementBody(BaseModel):
    budget_id: str
    account_id: str
    title: str
    description: str = ""
    estimate: str


class QuoteBody(BaseModel):
    vendor: str
    amount: str
    note: str = ""
    evidence_ids: List[str] = []


class AwardBody(BaseModel):
    quote_id: str
    justification: str = ""
    exception_reason: str = ""


class GrantBody(BaseModel):
    title: str
    donor: str
    amount: str
    currency: str
    start: str
    end: str
    restricted: bool = True
    conditions: str = ""


class ReceiptBody(BaseModel):
    amount: str
    date: str
    reference: str


class SpendBody(BaseModel):
    amount: str
    date: str
    description: str
    reference: str = ""
    evidence_ids: List[str] = []


class PrivacyBody(BaseModel):
    hide_donor: bool


class EraseBody(BaseModel):
    confirm: str


class PolicyBody(BaseModel):
    min_quotes: int
    quote_threshold: str


class ReportBody(BaseModel):
    budget_id: str
    title: str


def _d(body) -> dict:
    """Only the fields the caller actually sent."""
    return body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)



@router.get("/options")
def options(org: str = Depends(get_current_org), svc: PubFinService = Depends(get_pubfin)): return svc.options(org)


@router.get("/overview")
def overview(org: str = Depends(get_current_org), svc: PubFinService = Depends(get_pubfin)): return svc.overview(org)


@router.put("/policy", dependencies=[_approve])
def set_policy(body: PolicyBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PubFinService = Depends(get_pubfin)):
    return svc.set_policy(org, body.min_quotes, body.quote_threshold, actor)


@router.get("/budgets")
def budgets(org: str = Depends(get_current_org), svc: PubFinService = Depends(get_pubfin)): return svc.list_budgets(org)


@router.post("/budgets", status_code=201, dependencies=[_prepare])
def create_budget(body: BudgetBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PubFinService = Depends(get_pubfin)):
    return svc.create_budget(org, _d(body), actor)


@router.get("/budgets/{budget_id}")
def get_budget(budget_id: str, org: str = Depends(get_current_org), svc: PubFinService = Depends(get_pubfin)): return svc.get_budget(org, budget_id)


@router.put("/budgets/{budget_id}", dependencies=[_prepare])
def update_budget(budget_id: str, body: BudgetBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PubFinService = Depends(get_pubfin)):
    return svc.update_budget(org, budget_id, _d(body), actor)


@router.delete("/budgets/{budget_id}", dependencies=[_prepare])
def discard_budget(budget_id: str, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PubFinService = Depends(get_pubfin)):
    return svc.discard_budget(org, budget_id, actor)


@router.post("/budgets/{budget_id}/submit", dependencies=[_prepare])
def submit_budget(budget_id: str, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PubFinService = Depends(get_pubfin)):
    return svc.submit_budget(org, budget_id, actor)


@router.post("/budgets/{budget_id}/approve", dependencies=[_approve])
def approve_budget(budget_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PubFinService = Depends(get_pubfin)):
    return svc.approve_budget(org, budget_id, actor, body.note)


@router.post("/budgets/{budget_id}/reject", dependencies=[_approve])
def reject_budget(budget_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PubFinService = Depends(get_pubfin)):
    return svc.reject_budget(org, budget_id, actor, body.note)


@router.post("/budgets/{budget_id}/close", dependencies=[_prepare])
def close_budget(budget_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PubFinService = Depends(get_pubfin)):
    return svc.close_budget(org, budget_id, body.note, actor)


@router.post("/budgets/{budget_id}/virements", status_code=201, dependencies=[_prepare])
def propose_virement(budget_id: str, body: VirementBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PubFinService = Depends(get_pubfin)):
    return svc.propose_virement(org, budget_id, body.from_account, body.to_account, body.amount, body.reason, actor)


@router.post("/budgets/{budget_id}/virements/{virement_id}/approve", dependencies=[_approve])
def approve_virement(budget_id: str, virement_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PubFinService = Depends(get_pubfin)):
    return svc.approve_virement(org, budget_id, virement_id, actor, body.note)


@router.post("/budgets/{budget_id}/virements/{virement_id}/reject", dependencies=[_approve])
def reject_virement(budget_id: str, virement_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PubFinService = Depends(get_pubfin)):
    return svc.reject_virement(org, budget_id, virement_id, actor, body.note)


@router.get("/commitments")
def commitments(budget_id: Optional[str] = None, status: Optional[str] = None, org: str = Depends(get_current_org), svc: PubFinService = Depends(get_pubfin)): return svc.list_commitments(org, budget_id, status)


@router.post("/commitments", status_code=201, dependencies=[_prepare])
def create_commitment(body: CommitmentBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PubFinService = Depends(get_pubfin)):
    return svc.create_commitment(org, _d(body), actor)


@router.post("/commitments/{commitment_id}/settle", dependencies=[_prepare])
def settle_commitment(commitment_id: str, body: SettleBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PubFinService = Depends(get_pubfin)):
    return svc.settle_commitment(org, commitment_id, body.settled_amount, body.note, actor)


@router.post("/commitments/{commitment_id}/cancel", dependencies=[_prepare])
def cancel_commitment(commitment_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PubFinService = Depends(get_pubfin)):
    return svc.cancel_commitment(org, commitment_id, body.note, actor)


@router.get("/procurements")
def procurements(org: str = Depends(get_current_org), svc: PubFinService = Depends(get_pubfin)): return svc.list_procurements(org)


@router.post("/procurements", status_code=201, dependencies=[_prepare])
def create_procurement(body: ProcurementBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PubFinService = Depends(get_pubfin)):
    return svc.create_procurement(org, _d(body), actor)


@router.get("/procurements/{procurement_id}")
def get_procurement(procurement_id: str, org: str = Depends(get_current_org), svc: PubFinService = Depends(get_pubfin)): return svc.get_procurement(org, procurement_id)


@router.post("/procurements/{procurement_id}/quotes", status_code=201, dependencies=[_prepare])
def add_quote(procurement_id: str, body: QuoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PubFinService = Depends(get_pubfin)):
    return svc.add_quote(org, procurement_id, body.vendor, body.amount, body.note, body.evidence_ids, actor)


@router.post("/procurements/{procurement_id}/award", dependencies=[_prepare])
def propose_award(procurement_id: str, body: AwardBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PubFinService = Depends(get_pubfin)):
    return svc.propose_award(org, procurement_id, body.quote_id, body.justification, body.exception_reason, actor)


@router.post("/procurements/{procurement_id}/approve-award", dependencies=[_approve])
def approve_award(procurement_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PubFinService = Depends(get_pubfin)):
    return svc.approve_award(org, procurement_id, actor, body.note)


@router.post("/procurements/{procurement_id}/reject-award", dependencies=[_approve])
def reject_award(procurement_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PubFinService = Depends(get_pubfin)):
    return svc.reject_award(org, procurement_id, actor, body.note)


@router.post("/procurements/{procurement_id}/cancel", dependencies=[_prepare])
def cancel_procurement(procurement_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PubFinService = Depends(get_pubfin)):
    return svc.cancel_procurement(org, procurement_id, body.note, actor)


@router.get("/grants")
def grants(org: str = Depends(get_current_org), svc: PubFinService = Depends(get_pubfin)): return svc.list_grants(org)


@router.post("/grants", status_code=201, dependencies=[_prepare])
def create_grant(body: GrantBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PubFinService = Depends(get_pubfin)):
    return svc.create_grant(org, _d(body), actor)


@router.get("/grants/{grant_id}")
def get_grant(grant_id: str, org: str = Depends(get_current_org), svc: PubFinService = Depends(get_pubfin)): return svc.get_grant(org, grant_id)


@router.post("/grants/{grant_id}/receipts", status_code=201, dependencies=[_prepare])
def record_receipt(grant_id: str, body: ReceiptBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PubFinService = Depends(get_pubfin)):
    return svc.record_receipt(org, grant_id, body.amount, body.date, body.reference, actor)


@router.post("/grants/{grant_id}/spend", status_code=201, dependencies=[_prepare])
def add_spend(grant_id: str, body: SpendBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PubFinService = Depends(get_pubfin)):
    return svc.add_spend(org, grant_id, body.amount, body.date, body.description, body.reference, body.evidence_ids, actor)


@router.post("/grants/{grant_id}/spend/{spend_id}/approve", dependencies=[_approve])
def approve_spend(grant_id: str, spend_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PubFinService = Depends(get_pubfin)):
    return svc.approve_spend(org, grant_id, spend_id, actor, body.note)


@router.post("/grants/{grant_id}/spend/{spend_id}/reject", dependencies=[_approve])
def reject_spend(grant_id: str, spend_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PubFinService = Depends(get_pubfin)):
    return svc.reject_spend(org, grant_id, spend_id, actor, body.note)


@router.post("/grants/{grant_id}/close", dependencies=[_prepare])
def close_grant(grant_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PubFinService = Depends(get_pubfin)):
    return svc.close_grant(org, grant_id, body.note, actor)


@router.get("/reports")
def reports(org: str = Depends(get_current_org), svc: PubFinService = Depends(get_pubfin)): return svc.list_reports(org)


@router.post("/reports", status_code=201, dependencies=[_prepare])
def create_report(body: ReportBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PubFinService = Depends(get_pubfin)):
    return svc.create_report(org, body.budget_id, body.title, actor)


@router.get("/reports/{report_id}")
def get_report(report_id: str, org: str = Depends(get_current_org), svc: PubFinService = Depends(get_pubfin)): return svc.get_report(org, report_id)


@router.post("/reports/{report_id}/submit", dependencies=[_prepare])
def submit_report(report_id: str, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PubFinService = Depends(get_pubfin)):
    return svc.submit_report(org, report_id, actor)


@router.post("/reports/{report_id}/approve", dependencies=[_approve])
def approve_report(report_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PubFinService = Depends(get_pubfin)):
    return svc.approve_report(org, report_id, actor, body.note)


@router.post("/reports/{report_id}/reject", dependencies=[_approve])
def reject_report(report_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PubFinService = Depends(get_pubfin)):
    return svc.reject_report(org, report_id, actor, body.note)


@router.get("/reports/{report_id}/export")
def export_report(report_id: str, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PubFinService = Depends(get_pubfin)):
    out = svc.export_csv(org, report_id, actor)
    return Response(content=out["content"], media_type=out["content_type"], headers={"Content-Disposition": f'attachment; filename="{out["filename"]}"', "Cache-Control": "no-store"})


@router.put("/privacy", dependencies=[_approve])
def set_privacy(body: PrivacyBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PubFinService = Depends(get_pubfin)):
    return svc.set_privacy(org, body.hide_donor, actor)


@router.post("/privacy/erase-donors", dependencies=[_approve])
def erase_donors(body: EraseBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: PubFinService = Depends(get_pubfin)):
    return svc.erase_donors(org, body.confirm, actor)
