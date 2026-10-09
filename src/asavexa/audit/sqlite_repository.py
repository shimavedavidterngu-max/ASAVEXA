"""
SQLite-backed implementation of the shared audit repository. Stdlib only.

`ensure_schema(conn)` is idempotent and safe to call from any module's
own bootstrap — see asavexa/bootstrap.py, which calls it alongside each
module's own schema so a single SQLite connection can serve the whole
starter app in tests and local development.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import List, Optional

from .entity_ids import db_entity_id
from .models import AuditEvent

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_events (
    id TEXT PRIMARY KEY,
    org_id TEXT,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    previous_value TEXT,
    new_value TEXT,
    reason TEXT,
    related_record_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_events(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_org ON audit_events(org_id);
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_events(actor);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


class SqliteAuditRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def record(self, event: AuditEvent) -> AuditEvent:
        self.conn.execute(
            "INSERT INTO audit_events (id, org_id, entity_type, entity_id, "
            "action, actor, timestamp, previous_value, new_value, reason, "
            "related_record_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                event.id, event.org_id, event.entity_type, db_entity_id(event.entity_id),
                event.action, event.actor, event.timestamp.isoformat(),
                json.dumps(event.previous_value) if event.previous_value is not None else None,
                json.dumps(event.new_value) if event.new_value is not None else None,
                event.reason, event.related_record_id,
            ),
        )
        self.conn.commit()
        return event

    def _row_to_event(self, row) -> AuditEvent:
        return AuditEvent(
            id=row["id"], org_id=row["org_id"], entity_type=row["entity_type"],
            entity_id=row["entity_id"], action=row["action"], actor=row["actor"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            previous_value=json.loads(row["previous_value"]) if row["previous_value"] else None,
            new_value=json.loads(row["new_value"]) if row["new_value"] else None,
            reason=row["reason"], related_record_id=row["related_record_id"],
        )

    def list_for_entity(
        self, entity_type: str, entity_id: str, org_id: Optional[str] = None
    ) -> List[AuditEvent]:
        if org_id is not None:
            rows = self.conn.execute(
                "SELECT * FROM audit_events WHERE org_id=? AND entity_type=? "
                "AND entity_id=? ORDER BY timestamp",
                (org_id, entity_type, db_entity_id(entity_id)),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM audit_events WHERE entity_type=? AND entity_id=? "
                "ORDER BY timestamp",
                (entity_type, db_entity_id(entity_id)),
            ).fetchall()
        return [self._row_to_event(r) for r in rows]

    def list_for_org(self, org_id: str) -> List[AuditEvent]:
        rows = self.conn.execute(
            "SELECT * FROM audit_events WHERE org_id=? ORDER BY timestamp",
            (org_id,),
        ).fetchall()
        return [self._row_to_event(r) for r in rows]

    def list_recent_for_org(self, org_id: str, limit: int, exclude_action_prefix: Optional[str] = None):
        """The most recent `limit` events (oldest first) and the matching total."""
        where, params = "org_id=?", [org_id]
        prefixes = [exclude_action_prefix] if isinstance(exclude_action_prefix, str) else list(exclude_action_prefix or [])
        for prefix in prefixes:   # a string, or several prefixes
            where += " AND action NOT LIKE ? ESCAPE '\\'"
            params.append(prefix.replace("_", "\\_").replace("%", "\\%") + "%")
        total = self.conn.execute(f"SELECT COUNT(*) FROM audit_events WHERE {where}", params).fetchone()[0]
        rows = self.conn.execute(
            f"SELECT * FROM audit_events WHERE {where} ORDER BY timestamp DESC LIMIT ?", params + [limit]
        ).fetchall()
        return [self._row_to_event(r) for r in reversed(rows)], total

    def list_for_actor(self, actor: str) -> List[AuditEvent]:
        rows = self.conn.execute(
            "SELECT * FROM audit_events WHERE actor=? ORDER BY timestamp",
            (actor,),
        ).fetchall()
        return [self._row_to_event(r) for r in rows]

    def count_recent_for_actor(self, actor: str, action: str, since: datetime) -> int:
        """How many events of one action this actor has since a moment (used for sign-in lockout)."""
        rows = self.conn.execute("SELECT timestamp FROM audit_events WHERE actor=? AND action=?", (actor, action)).fetchall()
        floor = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
        n = 0
        for r in rows:
            t = datetime.fromisoformat(r[0])
            n += (t if t.tzinfo else t.replace(tzinfo=timezone.utc)) >= floor
        return n
