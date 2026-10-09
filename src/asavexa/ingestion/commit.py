"""What a person-confirmed batch is allowed to become. The only module here that writes, and only through the
existing services (so every existing rule, audit entry and permission still applies):

  bank statement lines  -> ReconciliationService.import_transactions (a DRAFT reconciliation only)
  documents / registers -> EvidenceVault.upload_evidence   (status UPLOADED = still unverified)
  chart of accounts     -> AccountingEngine.create_account
  journals              -> AccountingEngine.create_draft_journal (DRAFT; never posted)
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Callable, Dict, List, Optional, Tuple

from ..accounting.domain.enums import AccountType
from ..accounting.services.engine import LineInput
from ..audit.models import AuditEvent
from ..evidence.domain.enums import EvidenceType
from ..evidence.domain.errors import DuplicateEvidenceError
from ..reconciliation.domain import matching
from ..reconciliation.domain.enums import ReconciliationStatus
from ..reconciliation.domain.models import BankTransactionInput
from . import model as M
from .errors import BatchNotImportableError, IngestionError

ZERO = Decimal("0.00")


# ----------------------------------------------------------------- guards
def guard(batch: dict, expected_fingerprint: Optional[str], acknowledge: bool) -> None:
    """Refuse to import anything the person did not see: same file + same settings as the preview, no errors, warnings acknowledged."""
    if not expected_fingerprint:
        raise BatchNotImportableError("Preview the file first; the import needs the preview's fingerprint.")
    if batch["fingerprint"] != expected_fingerprint:
        raise BatchNotImportableError("The file or the settings changed since the preview. Preview it again and check the result.")
    st = batch["status"]
    if st["errors"]:
        raise BatchNotImportableError(f"The file still has {st['errors']} error(s). Fix them and preview again; nothing was imported.")
    if not st["importable"]:
        raise BatchNotImportableError("There is nothing in this file that can be imported.")
    if st["needs_acknowledgement"] and not acknowledge:
        raise BatchNotImportableError("The preview has warnings or failed checks. Read them, then confirm that you accept them to import.")


def audit_event(org_id: str, actor: str, purpose: str, batch: dict, result: dict, now: datetime) -> AuditEvent:
    return AuditEvent(id=str(uuid.uuid4()), org_id=org_id, entity_type="IngestionBatch", entity_id=batch["fingerprint"][:36], action=f"INGEST_{purpose}",
                      actor=actor, timestamp=now, reason=f"Imported {batch['source'].get('filename', 'file')}",
                      new_value={"source_sha256": batch["source"].get("sha256"), "format": batch["source"].get("format"), "summary": batch.get("summary"),
                                 "warnings_acknowledged": batch["status"]["needs_acknowledgement"], "result": result})


def _store_source(vault, org_id: str, actor: str, ev_type: EvidenceType, filename: str, content: bytes, content_type: str, batch: dict,
                  allow_duplicate: bool = False) -> Tuple[str, bool]:
    """Keeps the original file in the Evidence Vault (UPLOADED, not verified). Re-uploading the same file reuses the existing record."""
    meta = {"ingestion": {"fingerprint": batch["fingerprint"], "format": batch["source"].get("format"), "machine_read": True,
                          "summary": batch.get("summary"), "document": (batch.get("document") or {}).get("fields") and
                          {k: v["value"] for k, v in batch["document"]["fields"].items()}}}
    try:
        rec = vault.upload_evidence(org_id=org_id, type=ev_type, content=content, original_filename=filename, content_type=content_type,
                                    uploaded_by=actor, metadata=meta, allow_duplicate=allow_duplicate)
        return rec.id, True
    except DuplicateEvidenceError:
        existing = vault.evidence.get_by_hash(org_id, batch["source"]["sha256"])
        if existing is None:
            raise
        return existing.id, False


# ----------------------------------------------------------------- bank statements
def bank_context(recon_svc, org_id: str, reconciliation_id: str) -> dict:
    r = recon_svc.get_reconciliation(org_id, reconciliation_id)
    return {"reconciliation": r, "currency": r.currency, "period": (r.period_start, r.period_end), "bank_account_id": r.bank_account_id}


def mark_existing(batch: dict, recon_svc, org_id: str, ctx: dict) -> dict:
    """Flags lines already in the system, using the SAME duplicate test the import itself uses, so nothing is rejected at import time."""
    r = ctx["reconciliation"]
    if r.status != ReconciliationStatus.DRAFT:
        batch["issues"].append(M.issue(M.ERROR, f"This reconciliation is {r.status.value}; statement lines can only be imported into a DRAFT reconciliation."))
        batch["status"]["errors"] += 1
        batch["status"]["importable"] = False
    already = 0
    for row in batch["rows"]:
        if row["status"] == "ERROR":
            continue
        h = matching.compute_dedup_hash(org_id, ctx["bank_account_id"], row["reference"], date.fromisoformat(row["date"]),
                                        Decimal(row["money_in"]), Decimal(row["money_out"]), row["description"])
        ex = recon_svc.transactions.get_by_dedup_hash(org_id, ctx["bank_account_id"], h)
        row["already_imported"] = ex is not None
        if ex is not None:
            already += 1
    batch["summary"]["already_imported"] = already
    batch["summary"]["to_import"] = sum(1 for r_ in batch["rows"] if r_["status"] != "ERROR" and not r_.get("already_imported"))
    if already:
        batch["issues"].append(M.issue(M.INFO, f"{already} line(s) are already in this bank account's records and will be skipped (overlapping statement)."))
    batch["reconciliation"] = {"id": r.id, "name": r.name, "currency": r.currency, "status": r.status.value,
                               "period_start": r.period_start.isoformat(), "period_end": r.period_end.isoformat()}
    return batch


def commit_bank(batch: dict, *, recon_svc, vault, org_id: str, actor: str, reconciliation_id: str, filename: str, content: bytes,
                content_type: str) -> dict:
    ctx = bank_context(recon_svc, org_id, reconciliation_id)
    if "to_import" not in batch["summary"]:
        mark_existing(batch, recon_svc, org_id, ctx)
    if not batch["status"]["importable"]:
        raise BatchNotImportableError("This reconciliation is not open for imports (it must be DRAFT).")
    rows = [BankTransactionInput(transaction_date=date.fromisoformat(r["date"]), description=r["description"], debit_amount=Decimal(r["money_in"]),
                                 credit_amount=Decimal(r["money_out"]), value_date=date.fromisoformat(r["value_date"]) if r["value_date"] else None,
                                 external_ref=r["reference"], currency=ctx["currency"])
            for r in batch["rows"] if r["status"] != "ERROR" and not r.get("already_imported")]
    created = []
    if rows:
        src = f"file:{batch['source'].get('filename', '')[:80]} sha256:{batch['source']['sha256'][:12]}"
        created = recon_svc.import_transactions(org_id, reconciliation_id, rows, actor=actor, import_source=src)
    ev_id, new_ev = _store_source(vault, org_id, actor, EvidenceType.BANK_STATEMENT, filename, content, content_type, batch)
    linked = False
    cur = recon_svc.get_reconciliation(org_id, reconciliation_id)
    if cur.evidence_ref in (None, ev_id):
        recon_svc.attach_evidence(org_id, reconciliation_id, ev_id, actor)
        linked = True
    matched = sum(1 for t in created if getattr(t.status, "value", str(t.status)) == "MATCHED")
    return {"imported": len(created), "skipped_already_imported": batch["summary"].get("already_imported", 0), "matched_automatically": matched,
            "evidence_id": ev_id, "evidence_is_new": new_ev, "evidence_linked_to_reconciliation": linked}


# ----------------------------------------------------------------- documents and payroll registers
def commit_evidence(batch: dict, *, vault, org_id: str, actor: str, filename: str, content: bytes, content_type: str, evidence_type: str,
                    allow_duplicate: bool = False) -> dict:
    try:
        ev_type = EvidenceType(evidence_type)
    except ValueError:
        raise IngestionError(f"Unknown evidence type {evidence_type!r}.")
    try:
        rec = vault.upload_evidence(org_id=org_id, type=ev_type, content=content, original_filename=filename, content_type=content_type, uploaded_by=actor,
                                    metadata={"ingestion": {"fingerprint": batch["fingerprint"], "machine_read": True, "format": batch["source"].get("format"),
                                                            "fields": {k: v["value"] for k, v in (batch.get("document") or {}).get("fields", {}).items()} or None,
                                                            "summary": batch.get("summary")}},
                                    allow_duplicate=allow_duplicate)
    except DuplicateEvidenceError:
        raise
    return {"evidence_id": rec.id, "status": rec.status.value, "type": ev_type.value,
            "note": "Stored as UNVERIFIED evidence. A different person must verify it."}


# ----------------------------------------------------------------- chart of accounts
def commit_accounts(batch: dict, *, accounting, org_id: str, actor: str, currency: str) -> dict:
    made, skipped = [], 0
    for r in batch["rows"]:
        if r["status"] == "ERROR":
            continue
        if accounting.accounts.get_by_code(org_id, r["code"]) is not None:
            skipped += 1
            continue
        a = accounting.create_account(org_id, r["code"], r["name"], AccountType(r["type"]), actor, currency=currency)
        made.append(a.code)
    return {"created": len(made), "skipped_existing": skipped, "codes": made}


# ----------------------------------------------------------------- journals (drafts only)
def commit_journals(batch: dict, *, accounting, org_id: str, actor: str, currency: str) -> dict:
    out = []
    for j in batch["rows"]:
        if j["status"] == "ERROR":
            continue
        lines = [LineInput(l["account_id"], debit_amount=Decimal(l["debit"]), credit_amount=Decimal(l["credit"]), description=l["description"] or "")
                 for l in j["lines"]]
        jr = accounting.create_draft_journal(org_id, date.fromisoformat(j["date"]), j["description"], currency, lines, created_by=actor)
        out.append({"journal_id": jr.id, "journal_number": jr.journal_number, "source_journal": j["journal"]})
    return {"drafts_created": len(out), "journals": out, "note": "Created as DRAFT. Someone other than the importer must post them."}
