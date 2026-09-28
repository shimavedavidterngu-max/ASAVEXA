"""
Shared SQLite bootstrap for tests and local development.

Combines every module's own schema into one connection so the whole
starter app can run against a single SQLite file (or :memory:) without
each module needing to know about the others' tables. Each module still
owns its own SCHEMA constant and repository implementations — this file
only composes them.

Production does not use this — see api/db/base.py (SQLAlchemy against
PostgreSQL) and schema.sql for the equivalent production composition.
"""
from __future__ import annotations

import sqlite3

from .accounting.repository.sqlite_repository import SCHEMA as _ACCOUNTING_SCHEMA
from .audit.sqlite_repository import SCHEMA as _AUDIT_SCHEMA
from .compliance.repository.sqlite_repository import SCHEMA as _COMPLIANCE_SCHEMA
from .evidence.repository.sqlite_repository import SCHEMA as _EVIDENCE_SCHEMA
from .identity.repository.sqlite_repository import SCHEMA as _IDENTITY_SCHEMA
from .period_close.repository.sqlite_repository import SCHEMA as _PERIOD_CLOSE_SCHEMA
from .reconciliation.repository.sqlite_repository import SCHEMA as _RECONCILIATION_SCHEMA


def create_sqlite_connection(db_path: str = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # Identity first: accounting/evidence records reference org_id, and
    # while the SQLite schemas don't enforce that FK strictly (unlike
    # schema.sql for PostgreSQL), creating the tenant tables first keeps
    # the intent clear.
    conn.executescript(_IDENTITY_SCHEMA)
    conn.executescript(_AUDIT_SCHEMA)
    conn.executescript(_ACCOUNTING_SCHEMA)
    conn.executescript(_EVIDENCE_SCHEMA)
    conn.executescript(_RECONCILIATION_SCHEMA)
    conn.executescript(_PERIOD_CLOSE_SCHEMA)
    conn.executescript(_COMPLIANCE_SCHEMA)
    conn.commit()
    return conn
