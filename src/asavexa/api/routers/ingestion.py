"""External data ingestion API. `preview` writes nothing. `commit` re-reads the same file with the same settings and only
imports it if it still matches what the person previewed (fingerprint), has no errors, and warnings were acknowledged."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile

from ...identity.domain.errors import PermissionDeniedError
from ...identity.domain.permissions import (
    ACCOUNT_MANAGE, EVIDENCE_UPLOAD, JOURNAL_CREATE, LEDGER_READ, RECONCILIATION_IMPORT,
)
from ...ingestion import commit as C
from ...ingestion import model as M
from ...ingestion import service as S
from ...ingestion.errors import IngestionError
from ...ingestion.tabular import MAX_BYTES
from ..db.audit_sqlalchemy_repository import SqlAlchemyAuditRepository
from ..db.base import get_session
from ..deps import (
    get_accounting_engine, get_current_actor, get_current_org, get_evidence_vault, get_identity_service, get_reconciliation_service,
)
from ..schemas.ingestion import parse_options
from fastapi import HTTPException

router = APIRouter(prefix="/ingestion", tags=["External Data Ingestion"])

# What a person must be allowed to do for each purpose. Preview needs the same permission as the import it leads to.
PURPOSE_PERMISSION = {
    "BANK_STATEMENT": RECONCILIATION_IMPORT, "DOCUMENT": EVIDENCE_UPLOAD, "PAYROLL": EVIDENCE_UPLOAD,
    "CHART_OF_ACCOUNTS": ACCOUNT_MANAGE, "JOURNALS": JOURNAL_CREATE,
}


def _need(identity, actor, org_id, purpose):
    perm = PURPOSE_PERMISSION.get(purpose)
    if perm is None:
        raise IngestionError(f"purpose must be one of: {', '.join(PURPOSE_PERMISSION)}.")
    try:
        identity.require_permission(actor, org_id, perm)
    except PermissionDeniedError:
        raise HTTPException(status_code=403, detail=f"You do not have {perm!r} in this organisation.")


async def _read(file: UploadFile) -> bytes:
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise IngestionError(f"The file is larger than {MAX_BYTES // (1024 * 1024)} MB.")
    return data


def _stage(purpose, filename, content, opts, org_id, reconciliation_id, currency, recon_svc, accounting):
    """Builds the staged batch (shared by preview and commit so they can never disagree)."""
    o = opts.model_dump(exclude_none=True)
    kw = {}
    ctx = None
    if purpose == "BANK_STATEMENT":
        if not reconciliation_id:
            raise IngestionError("Choose the reconciliation the statement belongs to.")
        ctx = C.bank_context(recon_svc, org_id, reconciliation_id)
        kw.update(currency=ctx["currency"])
        o["period"] = ctx["period"]
        if o.get("currency") and o["currency"] != ctx["currency"]:
            raise IngestionError(f"The reconciliation is in {ctx['currency']}, not {o['currency']}.")
    else:
        cur = currency or o.get("currency")
        if purpose in ("CHART_OF_ACCOUNTS", "JOURNALS") and not cur:
            raise IngestionError("Choose the currency for the accounts/journals.")
        kw.update(currency=cur)
    if purpose == "JOURNALS":
        kw["accounts"] = [{"id": a.id, "code": a.code, "name": a.name} for a in accounting.accounts.list_for_org(org_id) if a.is_active]
        kw["periods"] = [{"start": p.start_date, "end": p.end_date, "status": p.status.value} for p in accounting.periods.list_for_org(org_id)]
    if purpose == "CHART_OF_ACCOUNTS":
        kw["existing_codes"] = {a.code: a.id for a in accounting.accounts.list_for_org(org_id)}
    batch = S.preview(filename, content, purpose, o, **kw)
    if ctx is not None:
        C.mark_existing(batch, recon_svc, org_id, ctx)
    return batch, ctx


@router.get("/levels")
def levels(org_id: str = Depends(get_current_org)):
    """What can be imported, and how far each level is actually built (nothing here claims a live connection)."""
    return {"levels": S.LEVELS, "purposes": list(PURPOSE_PERMISSION), "max_file_mb": MAX_BYTES // (1024 * 1024)}


@router.post("/preview")
async def preview(
    file: UploadFile = File(...), purpose: str = Form(...), reconciliation_id: Optional[str] = Form(None),
    options: Optional[str] = Form(None), currency: Optional[str] = Form(None),
    org_id: str = Depends(get_current_org), actor: str = Depends(get_current_actor), identity=Depends(get_identity_service),
    recon_svc=Depends(get_reconciliation_service), accounting=Depends(get_accounting_engine),
):
    """Reads the file and shows exactly what would be imported, and every problem. Writes nothing."""
    _need(identity, actor, org_id, purpose)
    content = await _read(file)
    batch, _ = _stage(purpose, file.filename or "unnamed", content, parse_options(options), org_id, reconciliation_id, currency, recon_svc, accounting)
    return M.display_copy(batch)


@router.post("/commit", status_code=201)
async def commit(
    file: UploadFile = File(...), purpose: str = Form(...), fingerprint: str = Form(...), acknowledge: bool = Form(False),
    reconciliation_id: Optional[str] = Form(None), options: Optional[str] = Form(None), currency: Optional[str] = Form(None),
    evidence_type: Optional[str] = Form(None), allow_duplicate: bool = Form(False),
    org_id: str = Depends(get_current_org), actor: str = Depends(get_current_actor), identity=Depends(get_identity_service),
    recon_svc=Depends(get_reconciliation_service), accounting=Depends(get_accounting_engine), vault=Depends(get_evidence_vault),
    session=Depends(get_session),
):
    """Imports a previewed file. Everything goes through the existing services, so their rules and audit entries all apply."""
    _need(identity, actor, org_id, purpose)
    content = await _read(file)
    name = file.filename or "unnamed"
    ctype = file.content_type or "application/octet-stream"
    batch, ctx = _stage(purpose, name, content, parse_options(options), org_id, reconciliation_id, currency, recon_svc, accounting)
    C.guard(batch, fingerprint, acknowledge)
    cur = currency or (parse_options(options).currency)
    if purpose == "BANK_STATEMENT":
        result = C.commit_bank(batch, recon_svc=recon_svc, vault=vault, org_id=org_id, actor=actor, reconciliation_id=reconciliation_id,
                               filename=name, content=content, content_type=ctype)
    elif purpose == "DOCUMENT":
        doc_type = evidence_type or {"INVOICE": "INVOICE", "RECEIPT": "RECEIPT"}.get((batch.get("document") or {}).get("type"), "OTHER")
        result = C.commit_evidence(batch, vault=vault, org_id=org_id, actor=actor, filename=name, content=content, content_type=ctype,
                                   evidence_type=doc_type, allow_duplicate=allow_duplicate)
    elif purpose == "PAYROLL":
        result = C.commit_evidence(batch, vault=vault, org_id=org_id, actor=actor, filename=name, content=content, content_type=ctype,
                                   evidence_type="PAYROLL_EVIDENCE", allow_duplicate=allow_duplicate)
    elif purpose == "CHART_OF_ACCOUNTS":
        result = C.commit_accounts(batch, accounting=accounting, org_id=org_id, actor=actor, currency=cur)
    else:
        result = C.commit_journals(batch, accounting=accounting, org_id=org_id, actor=actor, currency=cur)
    now = datetime.now(timezone.utc)
    SqlAlchemyAuditRepository(session).record(C.audit_event(org_id, actor, purpose, batch, result, now))
    return {"purpose": purpose, "fingerprint": batch["fingerprint"], "result": result}
