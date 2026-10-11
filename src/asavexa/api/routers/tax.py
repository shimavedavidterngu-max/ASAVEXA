"""Tax Compliance endpoints. Thin: the rules live in asavexa.tax.

Viewing needs reporting:read. Preparing (selecting countries, drafting and submitting rules, calculating, recording filings) needs tax:prepare.
Approving or sending back a rule needs tax:approve, and the service refuses the person who prepared or submitted it."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...identity.domain.permissions import REPORTING_READ, TAX_APPROVE, TAX_PREPARE
from ...tax.service import TaxService
from ..deps import get_current_actor, get_current_org, get_tax, require_permission

router = APIRouter(prefix="/tax", tags=["Tax Compliance"], dependencies=[Depends(require_permission(REPORTING_READ))])
_prepare = Depends(require_permission(TAX_PREPARE))
_approve = Depends(require_permission(TAX_APPROVE))


class CountryBody(BaseModel):
    selected: bool = True
    registration: str = ""


class RuleBody(BaseModel):
    country: str
    tax_type: str
    name: str
    method: str
    rate: Optional[str] = None
    brackets: Optional[List[Dict[str, Any]]] = None
    rounding: str = "HALF_UP"
    effective_from: str
    effective_to: Optional[str] = None
    authority: str
    source_title: str
    source_url: str
    notes: str = ""
    filing: Optional[Dict[str, Any]] = None
    replaces: Optional[str] = None


class NoteBody(BaseModel):
    note: str = ""


class CalcBody(BaseModel):
    rule_id: str
    amount: str
    date: str
    inclusive: bool = False
    basis: Optional[Dict[str, Any]] = None


class FiledBody(BaseModel):
    rule_id: str
    period_end: str
    reference: str


def _rule(body: RuleBody) -> dict:
    return body.model_dump() if hasattr(body, "model_dump") else body.dict()


@router.get("/overview")
def overview(org: str = Depends(get_current_org), svc: TaxService = Depends(get_tax)): return svc.overview(org)


@router.get("/countries")
def countries(q: str = "", region: str = "", org: str = Depends(get_current_org), svc: TaxService = Depends(get_tax)): return svc.countries(org, q, region)


@router.put("/countries/{code}", dependencies=[_prepare])
def set_country(code: str, body: CountryBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: TaxService = Depends(get_tax)):
    return svc.set_jurisdiction(org, code, body.selected, body.registration, actor)


@router.get("/options")
def options(svc: TaxService = Depends(get_tax)): return svc.rule_options()


@router.get("/rules")
def rules(country: Optional[str] = None, status: Optional[str] = None, org: str = Depends(get_current_org), svc: TaxService = Depends(get_tax)): return svc.list_rules(org, country, status)


@router.post("/rules", status_code=201, dependencies=[_prepare])
def create_rule(body: RuleBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: TaxService = Depends(get_tax)):
    d = _rule(body); replaces = d.pop("replaces", None)
    return svc.create_rule(org, d, actor, replaces)


@router.get("/rules/{rule_id}")
def get_rule(rule_id: str, org: str = Depends(get_current_org), svc: TaxService = Depends(get_tax)): return svc.get_rule(org, rule_id)


@router.put("/rules/{rule_id}", dependencies=[_prepare])
def update_rule(rule_id: str, body: RuleBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: TaxService = Depends(get_tax)):
    d = _rule(body); d.pop("replaces", None)
    return svc.update_rule(org, rule_id, d, actor)


@router.delete("/rules/{rule_id}", dependencies=[_prepare])
def discard_rule(rule_id: str, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: TaxService = Depends(get_tax)): return svc.delete_draft(org, rule_id, actor)


@router.post("/rules/{rule_id}/submit", dependencies=[_prepare])
def submit_rule(rule_id: str, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: TaxService = Depends(get_tax)): return svc.submit_rule(org, rule_id, actor)


@router.post("/rules/{rule_id}/approve", dependencies=[_approve])
def approve_rule(rule_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: TaxService = Depends(get_tax)):
    return svc.approve_rule(org, rule_id, actor, body.note)


@router.post("/rules/{rule_id}/reject", dependencies=[_approve])
def reject_rule(rule_id: str, body: NoteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: TaxService = Depends(get_tax)):
    return svc.reject_rule(org, rule_id, actor, body.note)


@router.get("/ledger-base")
def ledger_base(period_id: str, kind: str, org: str = Depends(get_current_org), svc: TaxService = Depends(get_tax)): return svc.ledger_base(org, period_id, kind)


@router.post("/calculate", dependencies=[_prepare])
def calculate(body: CalcBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: TaxService = Depends(get_tax)):
    return svc.calculate(org, body.rule_id, body.amount, body.date, body.inclusive, actor, True, body.basis)


@router.get("/calculations")
def calculations(org: str = Depends(get_current_org), svc: TaxService = Depends(get_tax)): return svc.calc_history(org)


@router.get("/calendar")
def calendar(start: str, end: str, org: str = Depends(get_current_org), svc: TaxService = Depends(get_tax)): return svc.calendar(org, start, end)


@router.post("/filed", status_code=201, dependencies=[_prepare])
def mark_filed(body: FiledBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: TaxService = Depends(get_tax)):
    return svc.mark_filed(org, body.rule_id, body.period_end, body.reference, actor)
