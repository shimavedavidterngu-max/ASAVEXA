"""
The Reconciliation module.

Public entry point: `asavexa.reconciliation.services.service.ReconciliationService`.

Signature principle: "Don't just reconcile the number. Prove the match."
Connects: External Transaction -> Matching Decision -> Ledger (read-only)
-> Evidence (opaque reference) -> Review/Approval -> shared Audit Trail.

Reads the Accounting Engine through its existing public interface
(accounts, journals, get_ledger) and never writes to it. Links to the
Evidence Vault only through an opaque id (Reconciliation.evidence_ref),
exactly like Journal.evidence_ref / EvidenceRecord.linked_journal_id
connect Accounting and Evidence — see README.md for the full contract.
"""
from .services.service import ReconciliationService  # noqa: F401
