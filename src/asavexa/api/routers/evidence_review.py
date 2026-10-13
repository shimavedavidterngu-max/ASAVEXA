"""Evidence Review endpoints. Thin: the rules live in asavexa.evidencereview.

Reading the review and the cases needs reporting:read. Raising a case and planning its action need finding:manage, doing the work needs
finding:remediate, and verifying the outcome (or re-checking a verified case) needs finding:verify. The service also refuses a verifier
who did the work or owns the action, whatever role they hold."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...compliance.domain.errors import AsavexaComplianceError
from ...evidencereview.errors import EvidenceReviewError
from ...evidencereview.service import EvidenceReviewService
from ...identity.domain.permissions import GRC_APPROVE, GRC_PREPARE, FINDING_MANAGE, FINDING_REMEDIATE, FINDING_VERIFY, REPORTING_READ
from ...proofgraph.graph import ProofGraphError
from ..deps import get_current_actor, get_current_org, get_evidence_review, require_permission

router = APIRouter(prefix="/evidence-review", tags=["Evidence Review"], dependencies=[Depends(require_permission(REPORTING_READ))])
_manage = Depends(require_permission(FINDING_MANAGE))
_remediate = Depends(require_permission(FINDING_REMEDIATE))
_verify = Depends(require_permission(FINDING_VERIFY))


class OpenBody(BaseModel):
    period_id: str
    report: str = "income_statement"
    account_id: Optional[str] = None
    title: Optional[str] = None


class PlanBody(BaseModel):
    action: str
    owner: str
    due_date: Optional[str] = None


class DoneBody(BaseModel):
    note: str
    evidence_ref: Optional[str] = None


class RulesBody(BaseModel):
    rules: List[dict]
    reason: str


class DecisionBody(BaseModel):
    note: str = ""


class RejectBody(BaseModel):
    reason: str


class VerifyBody(BaseModel):
    residual_risk: str
    reopen_criteria: str
    note: str = ""
    residual_level: Optional[str] = None
    reopen_if_gaps_above: int = 0
    recheck_after_days: Optional[int] = None


def _run(fn):
    try:
        return fn()
    except (EvidenceReviewError, ProofGraphError) as exc:
        raise HTTPException(status_code=getattr(exc, "status", 400), detail=str(exc))
    except AsavexaComplianceError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/review")
def review(period_id: str, report: str = "income_statement", account_id: Optional[str] = None, org: str = Depends(get_current_org),
           actor: str = Depends(get_current_actor), svc: EvidenceReviewService = Depends(get_evidence_review)):
    """What the figure asserts, what supports it, what is missing, conflicting or stale, which links are recorded or inferred, and what is uncertain."""
    return _run(lambda: svc.review(org, period_id, report, actor, account_id))


@router.get("/rules")
def rules_overview(org: str = Depends(get_current_org), svc: EvidenceReviewService = Depends(get_evidence_review)):
    """The expected-record rules in use, any change waiting for approval, and the history of changes."""
    return _run(lambda: svc.rule_set_overview(org))


@router.post("/rules", status_code=201, dependencies=[Depends(require_permission(GRC_PREPARE))])
def propose_rules(body: RulesBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: EvidenceReviewService = Depends(get_evidence_review)):
    return _run(lambda: svc.propose_rule_set(org, body.rules, actor, body.reason))


@router.post("/rules/{version}/approve", dependencies=[Depends(require_permission(GRC_APPROVE))])
def approve_rules(version: int, body: DecisionBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: EvidenceReviewService = Depends(get_evidence_review)):
    return _run(lambda: svc.approve_rule_set(org, version, actor, body.note))


@router.post("/rules/{version}/reject", dependencies=[Depends(require_permission(GRC_APPROVE))])
def reject_rules(version: int, body: RejectBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: EvidenceReviewService = Depends(get_evidence_review)):
    return _run(lambda: svc.reject_rule_set(org, version, actor, body.reason))


@router.get("/cases")
def list_cases(status: Optional[str] = None, org: str = Depends(get_current_org), svc: EvidenceReviewService = Depends(get_evidence_review), due_for_recheck: bool = False):
    return {"cases": svc.list_cases(org, status, due_for_recheck)}


@router.get("/cases/{case_id}")
def get_case(case_id: str, org: str = Depends(get_current_org), svc: EvidenceReviewService = Depends(get_evidence_review)):
    return _run(lambda: svc.get_case(org, case_id))


@router.post("/cases", status_code=201, dependencies=[_manage])
def open_case(body: OpenBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: EvidenceReviewService = Depends(get_evidence_review)):
    return _run(lambda: svc.open_case(org, body.period_id, body.report, actor, body.account_id, body.title or ""))


@router.post("/cases/{case_id}/plan", dependencies=[_manage])
def plan(case_id: str, body: PlanBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: EvidenceReviewService = Depends(get_evidence_review)):
    return _run(lambda: svc.plan_action(org, case_id, body.action, body.owner, actor, body.due_date))


@router.post("/cases/{case_id}/complete", dependencies=[_remediate])
def complete(case_id: str, body: DoneBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: EvidenceReviewService = Depends(get_evidence_review)):
    return _run(lambda: svc.complete_action(org, case_id, actor, body.note, body.evidence_ref))


@router.post("/cases/{case_id}/verify", dependencies=[_verify])
def verify(case_id: str, body: VerifyBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: EvidenceReviewService = Depends(get_evidence_review)):
    return _run(lambda: svc.verify_outcome(org, case_id, actor, body.residual_risk, body.reopen_criteria, body.note,
                                                residual_level=body.residual_level, reopen_if_gaps_above=body.reopen_if_gaps_above, recheck_after_days=body.recheck_after_days))


@router.post("/cases/{case_id}/recheck", dependencies=[_verify])
def recheck(case_id: str, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: EvidenceReviewService = Depends(get_evidence_review)):
    return _run(lambda: svc.recheck(org, case_id, actor))
