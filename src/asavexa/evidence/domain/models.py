"""
Domain model for the Evidence Vault.

Deliberately has no reference to any Accounting Engine type (Journal,
Transaction). Linkage is by opaque string id
(`linked_journal_id`/`linked_transaction_ref`) exactly as
accounting/domain/models.py::Journal.evidence_ref points the other way —
see evidence/README.md for why this one-directional, string-only
linkage is the integration contract, not a foreign key either module
enforces on the other's behalf.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .enums import EvidenceStatus, EvidenceType


@dataclass
class EvidenceRecord:
    id: str
    org_id: str
    type: EvidenceType
    status: EvidenceStatus
    file_hash: str                 # sha256 hex of the uploaded content
    original_filename: str
    content_type: str
    size_bytes: int
    uploaded_by: str
    uploaded_at: datetime
    verified_by: Optional[str] = None
    verified_at: Optional[datetime] = None
    verification_note: Optional[str] = None
    rejection_reason: Optional[str] = None
    linked_journal_id: Optional[str] = None
    linked_transaction_ref: Optional[str] = None
    # Extracted/proposed data (e.g. from OCR) — the blueprint's Document
    # Intelligence Skill: "extracted information must be treated as
    # proposed data until validated". Never trusted as fact by this
    # module or any other.
    metadata: dict = field(default_factory=dict)
