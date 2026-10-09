import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from ...ai.engine import AiEngine
from ...audit.models import AuditEvent
from ...identity.domain.permissions import LEDGER_READ
from ..db.audit_sqlalchemy_repository import SqlAlchemyAuditRepository
from ..db.base import get_session
from ..deps import get_current_actor, get_current_org, require_permission
from ..schemas.ai import AiAskIn, AiDetectIn, AiExplainIn, AiProveIn, AiRecommendIn
from .passport import gather_inputs

router = APIRouter(prefix="/ai", tags=["ASAVEXA AI"], dependencies=[Depends(require_permission(LEDGER_READ))])


def _run(session, org_id: str, actor: str, fn):
    """Builds the engine from the caller's own organisation's records, runs one read-only
    question, and records that the question was asked (AI_*). The AI itself writes nothing else."""
    inp = gather_inputs(session, org_id)
    now = datetime.now(timezone.utc)
    result = fn(AiEngine(inp, now))
    SqlAlchemyAuditRepository(session).record(AuditEvent(
        id=str(uuid.uuid4()), org_id=org_id, entity_type="AiQuery", entity_id=result["response_id"],
        action="AI_" + str((result.get("interpreted_as") or {}).get("mode") or "ASK"), actor=actor, timestamp=now,
        reason=(result.get("question") or "")[:300],
        new_value={"fingerprint": result["fingerprint"], "grounded": result["grounded"],
                   "interpreted_as": result.get("interpreted_as"), "items": len(result.get("items") or [])},
    ))
    return result


@router.post("/explain")
def explain(body: AiExplainIn, org_id: str = Depends(get_current_org), actor: str = Depends(get_current_actor),
            session=Depends(get_session)):
    """AI Explain: why was this transaction classified this way?"""
    return _run(session, org_id, actor, lambda e: e.explain(body.subject_type, body.subject_id))


@router.post("/detect")
def detect(body: AiDetectIn, org_id: str = Depends(get_current_org), actor: str = Depends(get_current_actor),
           session=Depends(get_session)):
    """AI Detect: find unusual transactions."""
    return _run(session, org_id, actor, lambda e: e.detect(body.period_id, body.limit))


@router.post("/recommend")
def recommend(body: AiRecommendIn, org_id: str = Depends(get_current_org), actor: str = Depends(get_current_actor),
              session=Depends(get_session)):
    """AI Recommend: suggest a reconciliation or adjustment. Proposals only; nothing is applied."""
    return _run(session, org_id, actor, lambda e: e.recommend(body.scope, body.period_id, body.limit))


@router.post("/prove")
def prove(body: AiProveIn, org_id: str = Depends(get_current_org), actor: str = Depends(get_current_actor),
          session=Depends(get_session)):
    """AI Prove: show the evidence supporting an answer."""
    return _run(session, org_id, actor, lambda e: e.prove(body.subject_type, body.subject_id, body.metric, body.period_id))


@router.post("/ask")
def ask(body: AiAskIn, org_id: str = Depends(get_current_org), actor: str = Depends(get_current_actor),
        session=Depends(get_session)):
    """Free-text question, routed to one of the four modes by plain keyword rules."""
    return _run(session, org_id, actor, lambda e: e.ask(body.question))
