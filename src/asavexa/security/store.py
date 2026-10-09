"""A tiny document store used by every security feature, so production needs ONE table (security_docs) and tests need none.

A document is identified by (kind, key); it has an optional org_id for tenant filtering and a JSON-able dict as data."""
from __future__ import annotations

import json
import sqlite3
from typing import Dict, List, Optional, Protocol, Tuple


class DocStore(Protocol):
    def put(self, kind: str, key: str, data: dict, org_id: Optional[str] = None) -> None: ...
    def get(self, kind: str, key: str, for_update: bool = False) -> Optional[dict]: ...
    def delete(self, kind: str, key: str) -> None: ...
    def list(self, kind: str, org_id: Optional[str] = None, prefix: Optional[str] = None) -> List[Tuple[str, dict]]: ...


class MemoryDocStore:
    def __init__(self):
        self._d: Dict[Tuple[str, str], Tuple[Optional[str], str]] = {}

    def put(self, kind, key, data, org_id=None):
        self._d[(kind, key)] = (org_id, json.dumps(data, sort_keys=True, default=str))

    def get(self, kind, key, for_update=False):
        v = self._d.get((kind, key))
        return json.loads(v[1]) if v else None

    def delete(self, kind, key):
        self._d.pop((kind, key), None)

    def list(self, kind, org_id=None, prefix=None):
        out = []
        for (k, key), (o, raw) in sorted(self._d.items()):
            if k != kind or (org_id is not None and o != org_id) or (prefix and not key.startswith(prefix)):
                continue
            out.append((key, json.loads(raw)))
        return out


SCHEMA = """
CREATE TABLE IF NOT EXISTS security_docs (
    kind TEXT NOT NULL, key TEXT NOT NULL, org_id TEXT, data TEXT NOT NULL, updated_at TEXT,
    PRIMARY KEY (kind, key)
);
"""


class SqliteDocStore:
    """Same contract on SQLite (used by tests that also exercise the real services on one connection)."""
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        conn.executescript(SCHEMA)

    def put(self, kind, key, data, org_id=None):
        self.conn.execute("INSERT OR REPLACE INTO security_docs (kind, key, org_id, data, updated_at) VALUES (?,?,?,?,datetime('now'))",
                          (kind, key, org_id, json.dumps(data, sort_keys=True, default=str)))
        self.conn.commit()

    def get(self, kind, key, for_update=False):
        r = self.conn.execute("SELECT data FROM security_docs WHERE kind=? AND key=?", (kind, key)).fetchone()
        return json.loads(r[0]) if r else None

    def delete(self, kind, key):
        self.conn.execute("DELETE FROM security_docs WHERE kind=? AND key=?", (kind, key))
        self.conn.commit()

    def list(self, kind, org_id=None, prefix=None):
        q, p = "SELECT key, data FROM security_docs WHERE kind=?", [kind]
        if org_id is not None:
            q += " AND org_id=?"; p.append(org_id)
        if prefix:
            q += " AND key LIKE ? ESCAPE '\\'"; p.append(prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
        return [(r[0], json.loads(r[1])) for r in self.conn.execute(q + " ORDER BY key", p).fetchall()]
