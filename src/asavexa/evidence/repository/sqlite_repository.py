"""
SQLite-backed implementation of the Evidence Vault repository. Stdlib
only (sqlite3, json) — same discipline as the Accounting Engine and
Identity module's SQLite adapters.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import List, Optional

from ..domain.enums import EvidenceStatus, EvidenceType
from ..domain.models import EvidenceRecord

SCHEMA = """
CREATE TABLE IF NOT EXISTS evidence_records (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    type TEXT NOT NULL,
    status TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    uploaded_by TEXT NOT NULL,
    uploaded_at TEXT NOT NULL,
    verified_by TEXT,
    verified_at TEXT,
    verification_note TEXT,
    rejection_reason TEXT,
    linked_journal_id TEXT,
    linked_transaction_ref TEXT,
    metadata TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_evidence_org ON evidence_records(org_id);
CREATE INDEX IF NOT EXISTS idx_evidence_org_hash ON evidence_records(org_id, file_hash);
CREATE INDEX IF NOT EXISTS idx_evidence_journal ON evidence_records(linked_journal_id);
CREATE INDEX IF NOT EXISTS idx_evidence_txn_ref ON evidence_records(linked_transaction_ref);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def connect(db_path: str = ":memory:") -> sqlite3.Connection:
    """Convenience for standalone use of just this module. Composed
    apps should use asavexa.bootstrap instead."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    ensure_schema(conn)
    conn.commit()
    return conn


class SqliteEvidenceRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def _row_to_record(self, row) -> EvidenceRecord:
        return EvidenceRecord(
            id=row["id"], org_id=row["org_id"], type=EvidenceType(row["type"]),
            status=EvidenceStatus(row["status"]), file_hash=row["file_hash"],
            original_filename=row["original_filename"], content_type=row["content_type"],
            size_bytes=row["size_bytes"], uploaded_by=row["uploaded_by"],
            uploaded_at=datetime.fromisoformat(row["uploaded_at"]),
            verified_by=row["verified_by"],
            verified_at=datetime.fromisoformat(row["verified_at"]) if row["verified_at"] else None,
            verification_note=row["verification_note"], rejection_reason=row["rejection_reason"],
            linked_journal_id=row["linked_journal_id"],
            linked_transaction_ref=row["linked_transaction_ref"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    def create(self, record: EvidenceRecord) -> EvidenceRecord:
        self.conn.execute(
            "INSERT INTO evidence_records (id, org_id, type, status, file_hash, "
            "original_filename, content_type, size_bytes, uploaded_by, uploaded_at, "
            "verified_by, verified_at, verification_note, rejection_reason, "
            "linked_journal_id, linked_transaction_ref, metadata) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                record.id, record.org_id, record.type.value, record.status.value,
                record.file_hash, record.original_filename, record.content_type,
                record.size_bytes, record.uploaded_by, record.uploaded_at.isoformat(),
                record.verified_by,
                record.verified_at.isoformat() if record.verified_at else None,
                record.verification_note, record.rejection_reason,
                record.linked_journal_id, record.linked_transaction_ref,
                json.dumps(record.metadata or {}),
            ),
        )
        self.conn.commit()
        return record

    def get(self, org_id: str, evidence_id: str) -> Optional[EvidenceRecord]:
        row = self.conn.execute(
            "SELECT * FROM evidence_records WHERE org_id=? AND id=?", (org_id, evidence_id)
        ).fetchone()
        return self._row_to_record(row) if row else None

    def get_by_hash(self, org_id: str, file_hash: str) -> Optional[EvidenceRecord]:
        row = self.conn.execute(
            "SELECT * FROM evidence_records WHERE org_id=? AND file_hash=?", (org_id, file_hash)
        ).fetchone()
        return self._row_to_record(row) if row else None

    def update(self, record: EvidenceRecord) -> EvidenceRecord:
        self.conn.execute(
            "UPDATE evidence_records SET status=?, verified_by=?, verified_at=?, "
            "verification_note=?, rejection_reason=?, linked_journal_id=?, "
            "linked_transaction_ref=?, metadata=? WHERE id=?",
            (
                record.status.value, record.verified_by,
                record.verified_at.isoformat() if record.verified_at else None,
                record.verification_note, record.rejection_reason,
                record.linked_journal_id, record.linked_transaction_ref,
                json.dumps(record.metadata or {}), record.id,
            ),
        )
        self.conn.commit()
        return record

    def list_for_org(self, org_id: str) -> List[EvidenceRecord]:
        rows = self.conn.execute(
            "SELECT * FROM evidence_records WHERE org_id=? ORDER BY uploaded_at", (org_id,)
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def find_for_journal(self, org_id: str, journal_id: str) -> Optional[EvidenceRecord]:
        row = self.conn.execute(
            "SELECT * FROM evidence_records WHERE org_id=? AND linked_journal_id=? "
            "ORDER BY uploaded_at DESC LIMIT 1",
            (org_id, journal_id),
        ).fetchone()
        return self._row_to_record(row) if row else None

    def find_for_transaction_ref(self, org_id: str, transaction_ref: str) -> Optional[EvidenceRecord]:
        row = self.conn.execute(
            "SELECT * FROM evidence_records WHERE org_id=? AND linked_transaction_ref=? "
            "ORDER BY uploaded_at DESC LIMIT 1",
            (org_id, transaction_ref),
        ).fetchone()
        return self._row_to_record(row) if row else None
