"""
SQLite-backed implementation of the Period Close repository. Stdlib
only (sqlite3, json) — same discipline as every other module's SQLite
adapter.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import List, Optional

from ..domain.enums import PeriodCloseStatus
from ..domain.models import PeriodCloseProcess

SCHEMA = """
CREATE TABLE IF NOT EXISTS period_close_processes (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    period_id TEXT NOT NULL,
    status TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    last_findings TEXT NOT NULL DEFAULT '[]',
    reviewed_by TEXT,
    reviewed_at TEXT,
    approved_by TEXT,
    approved_at TEXT,
    rejected_by TEXT,
    rejected_at TEXT,
    rejection_reason TEXT,
    supersedes_close_process_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_close_org_period ON period_close_processes(org_id, period_id);
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


# Statuses that count as "an active, unresolved close workflow already
# exists for this period" — see get_active_for_period.
_ACTIVE_STATUSES = (
    PeriodCloseStatus.REQUESTED.value,
    PeriodCloseStatus.READY_FOR_CLOSE.value,
    PeriodCloseStatus.CONTROLS_FAILED.value,
)


class SqlitePeriodCloseRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def _row_to_domain(self, row) -> PeriodCloseProcess:
        return PeriodCloseProcess(
            id=row["id"], org_id=row["org_id"], period_id=row["period_id"],
            status=PeriodCloseStatus(row["status"]), requested_by=row["requested_by"],
            requested_at=datetime.fromisoformat(row["requested_at"]),
            last_findings=json.loads(row["last_findings"]) if row["last_findings"] else [],
            reviewed_by=row["reviewed_by"],
            reviewed_at=datetime.fromisoformat(row["reviewed_at"]) if row["reviewed_at"] else None,
            approved_by=row["approved_by"],
            approved_at=datetime.fromisoformat(row["approved_at"]) if row["approved_at"] else None,
            rejected_by=row["rejected_by"],
            rejected_at=datetime.fromisoformat(row["rejected_at"]) if row["rejected_at"] else None,
            rejection_reason=row["rejection_reason"],
            supersedes_close_process_id=row["supersedes_close_process_id"],
        )

    def create(self, process: PeriodCloseProcess) -> PeriodCloseProcess:
        p = process
        self.conn.execute(
            "INSERT INTO period_close_processes (id, org_id, period_id, status, requested_by, "
            "requested_at, last_findings, reviewed_by, reviewed_at, approved_by, approved_at, "
            "rejected_by, rejected_at, rejection_reason, supersedes_close_process_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                p.id, p.org_id, p.period_id, p.status.value, p.requested_by,
                p.requested_at.isoformat(), json.dumps(p.last_findings),
                p.reviewed_by, p.reviewed_at.isoformat() if p.reviewed_at else None,
                p.approved_by, p.approved_at.isoformat() if p.approved_at else None,
                p.rejected_by, p.rejected_at.isoformat() if p.rejected_at else None,
                p.rejection_reason, p.supersedes_close_process_id,
            ),
        )
        self.conn.commit()
        return process

    def get(self, org_id: str, process_id: str) -> Optional[PeriodCloseProcess]:
        row = self.conn.execute(
            "SELECT * FROM period_close_processes WHERE org_id=? AND id=?", (org_id, process_id)
        ).fetchone()
        return self._row_to_domain(row) if row else None

    def update(self, process: PeriodCloseProcess) -> PeriodCloseProcess:
        p = process
        self.conn.execute(
            "UPDATE period_close_processes SET status=?, last_findings=?, reviewed_by=?, "
            "reviewed_at=?, approved_by=?, approved_at=?, rejected_by=?, rejected_at=?, "
            "rejection_reason=? WHERE id=?",
            (
                p.status.value, json.dumps(p.last_findings), p.reviewed_by,
                p.reviewed_at.isoformat() if p.reviewed_at else None,
                p.approved_by, p.approved_at.isoformat() if p.approved_at else None,
                p.rejected_by, p.rejected_at.isoformat() if p.rejected_at else None,
                p.rejection_reason, p.id,
            ),
        )
        self.conn.commit()
        return process

    def list_for_period(self, org_id: str, period_id: str) -> List[PeriodCloseProcess]:
        rows = self.conn.execute(
            "SELECT * FROM period_close_processes WHERE org_id=? AND period_id=? "
            "ORDER BY requested_at",
            (org_id, period_id),
        ).fetchall()
        return [self._row_to_domain(r) for r in rows]

    def get_active_for_period(self, org_id: str, period_id: str) -> Optional[PeriodCloseProcess]:
        placeholders = ",".join("?" for _ in _ACTIVE_STATUSES)
        row = self.conn.execute(
            f"SELECT * FROM period_close_processes WHERE org_id=? AND period_id=? "
            f"AND status IN ({placeholders}) ORDER BY requested_at DESC LIMIT 1",
            (org_id, period_id, *_ACTIVE_STATUSES),
        ).fetchone()
        return self._row_to_domain(row) if row else None
