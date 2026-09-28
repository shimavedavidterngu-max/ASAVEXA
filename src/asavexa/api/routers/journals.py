from fastapi import APIRouter, Depends

from ...accounting.domain.errors import JournalNotFoundError
from ...accounting.services.engine import AccountingEngine, LineInput
from ...identity.domain.permissions import AUDIT_READ, JOURNAL_CREATE, JOURNAL_POST, JOURNAL_REVERSE, LEDGER_READ
from ..deps import get_accounting_engine, get_current_actor, get_current_org, require_permission
from ..schemas.journals import JournalCreate, JournalOut, ReverseJournalRequest

router = APIRouter(prefix="/journals", tags=["Journals"])


@router.post(
    "", response_model=JournalOut, status_code=201,
    dependencies=[Depends(require_permission(JOURNAL_CREATE))],
)
def create_draft_journal(
    body: JournalCreate,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    engine: AccountingEngine = Depends(get_accounting_engine),
):
    """Creates a DRAFT journal. Posting is a separate, explicit step —
    see POST /journals/{id}/post — so an approval workflow can sit
    between the two (maker-checker)."""
    lines = [
        LineInput(l.account_id, l.debit_amount, l.credit_amount, l.description)
        for l in body.lines
    ]
    return engine.create_draft_journal(
        org_id=org_id, date_=body.date, description=body.description,
        currency=body.currency, lines=lines, created_by=actor,
        transaction_ref=body.transaction_ref, evidence_ref=body.evidence_ref,
    )


@router.get("/{journal_id}", response_model=JournalOut, dependencies=[Depends(require_permission(LEDGER_READ))])
def get_journal(
    journal_id: str,
    org_id: str = Depends(get_current_org),
    engine: AccountingEngine = Depends(get_accounting_engine),
):
    journal = engine.journals.get(org_id, journal_id)
    if journal is None:
        raise JournalNotFoundError(f"Journal {journal_id} not found.")
    return journal


@router.post(
    "/{journal_id}/post", response_model=JournalOut,
    dependencies=[Depends(require_permission(JOURNAL_POST))],
)
def post_journal(
    journal_id: str,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    engine: AccountingEngine = Depends(get_accounting_engine),
):
    return engine.post_journal(org_id, journal_id, actor)


@router.post(
    "/{journal_id}/reverse", response_model=JournalOut,
    dependencies=[Depends(require_permission(JOURNAL_REVERSE))],
)
def reverse_journal(
    journal_id: str,
    body: ReverseJournalRequest,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    engine: AccountingEngine = Depends(get_accounting_engine),
):
    """Never edits or deletes the original — creates and posts an
    offsetting journal, and marks the original REVERSED. See Blueprint
    Rule 6 (Immutable Financial History)."""
    return engine.reverse_journal(org_id, journal_id, actor, body.reason)


@router.get("/{journal_id}/audit-trail", dependencies=[Depends(require_permission(AUDIT_READ))])
def get_journal_audit_trail(
    journal_id: str,
    org_id: str = Depends(get_current_org),
    engine: AccountingEngine = Depends(get_accounting_engine),
):
    return engine.get_audit_trail(org_id, "Journal", journal_id)
