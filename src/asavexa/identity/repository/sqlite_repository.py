"""
SQLite-backed implementation of the Identity repositories. Stdlib only
(sqlite3) — no external dependencies, same discipline as
accounting/repository/sqlite_repository.py.

`ensure_schema(conn)` is idempotent; see asavexa/bootstrap.py for how
this is combined with the other modules' schemas into one connection
for tests and local development.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import List, Optional

from ..domain.enums import MembershipStatus, Role
from ..domain.models import Membership, Organisation, Session, User

SCHEMA = """
CREATE TABLE IF NOT EXISTS organisations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    mfa_enabled INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memberships (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    UNIQUE(org_id, user_id)
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    org_id TEXT,
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT
);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def connect(db_path: str = ":memory:") -> sqlite3.Connection:
    """Convenience for standalone use of just this module (e.g. its own
    test file). Composed apps should use asavexa.bootstrap instead."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    ensure_schema(conn)
    conn.commit()
    return conn


class SqliteOrganisationRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, org: Organisation) -> Organisation:
        self.conn.execute(
            "INSERT INTO organisations (id, name, created_at) VALUES (?,?,?)",
            (org.id, org.name, org.created_at.isoformat()),
        )
        self.conn.commit()
        return org

    def get(self, org_id: str) -> Optional[Organisation]:
        row = self.conn.execute(
            "SELECT * FROM organisations WHERE id=?", (org_id,)
        ).fetchone()
        if row is None:
            return None
        return Organisation(id=row["id"], name=row["name"], created_at=datetime.fromisoformat(row["created_at"]))

    def list_all(self) -> List[Organisation]:
        rows = self.conn.execute("SELECT * FROM organisations ORDER BY name").fetchall()
        return [
            Organisation(id=r["id"], name=r["name"], created_at=datetime.fromisoformat(r["created_at"]))
            for r in rows
        ]


class SqliteUserRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def _row_to_user(self, row) -> User:
        return User(
            id=row["id"], email=row["email"], password_hash=row["password_hash"],
            is_active=bool(row["is_active"]), mfa_enabled=bool(row["mfa_enabled"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def create(self, user: User) -> User:
        self.conn.execute(
            "INSERT INTO users (id, email, password_hash, is_active, mfa_enabled, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (
                user.id, user.email, user.password_hash, int(user.is_active),
                int(user.mfa_enabled), user.created_at.isoformat(),
            ),
        )
        self.conn.commit()
        return user

    def get(self, user_id: str) -> Optional[User]:
        row = self.conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return self._row_to_user(row) if row else None

    def get_by_email(self, email: str) -> Optional[User]:
        row = self.conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        return self._row_to_user(row) if row else None

    def update(self, user: User) -> User:
        self.conn.execute(
            "UPDATE users SET password_hash=?, is_active=?, mfa_enabled=? WHERE id=?",
            (user.password_hash, int(user.is_active), int(user.mfa_enabled), user.id),
        )
        self.conn.commit()
        return user


class SqliteMembershipRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def _row_to_membership(self, row) -> Membership:
        return Membership(
            id=row["id"], org_id=row["org_id"], user_id=row["user_id"],
            role=Role(row["role"]), status=MembershipStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]), created_by=row["created_by"],
        )

    def create(self, membership: Membership) -> Membership:
        self.conn.execute(
            "INSERT INTO memberships (id, org_id, user_id, role, status, created_at, created_by) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                membership.id, membership.org_id, membership.user_id, membership.role.value,
                membership.status.value, membership.created_at.isoformat(), membership.created_by,
            ),
        )
        self.conn.commit()
        return membership

    def get(self, org_id: str, user_id: str) -> Optional[Membership]:
        row = self.conn.execute(
            "SELECT * FROM memberships WHERE org_id=? AND user_id=?", (org_id, user_id)
        ).fetchone()
        return self._row_to_membership(row) if row else None

    def update(self, membership: Membership) -> Membership:
        self.conn.execute(
            "UPDATE memberships SET role=?, status=? WHERE id=?",
            (membership.role.value, membership.status.value, membership.id),
        )
        self.conn.commit()
        return membership

    def list_for_org(self, org_id: str) -> List[Membership]:
        rows = self.conn.execute(
            "SELECT * FROM memberships WHERE org_id=? ORDER BY created_at", (org_id,)
        ).fetchall()
        return [self._row_to_membership(r) for r in rows]

    def list_for_user(self, user_id: str) -> List[Membership]:
        rows = self.conn.execute(
            "SELECT * FROM memberships WHERE user_id=? ORDER BY created_at", (user_id,)
        ).fetchall()
        return [self._row_to_membership(r) for r in rows]


class SqliteSessionRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def _row_to_session(self, row) -> Session:
        return Session(
            id=row["id"], user_id=row["user_id"], org_id=row["org_id"],
            token_hash=row["token_hash"], created_at=datetime.fromisoformat(row["created_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"]),
            revoked_at=datetime.fromisoformat(row["revoked_at"]) if row["revoked_at"] else None,
        )

    def create(self, session: Session) -> Session:
        self.conn.execute(
            "INSERT INTO sessions (id, user_id, org_id, token_hash, created_at, expires_at, revoked_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                session.id, session.user_id, session.org_id, session.token_hash,
                session.created_at.isoformat(), session.expires_at.isoformat(),
                session.revoked_at.isoformat() if session.revoked_at else None,
            ),
        )
        self.conn.commit()
        return session

    def get_by_token_hash(self, token_hash: str) -> Optional[Session]:
        row = self.conn.execute(
            "SELECT * FROM sessions WHERE token_hash=?", (token_hash,)
        ).fetchone()
        return self._row_to_session(row) if row else None

    def update(self, session: Session) -> Session:
        self.conn.execute(
            "UPDATE sessions SET org_id=?, revoked_at=? WHERE id=?",
            (
                session.org_id,
                session.revoked_at.isoformat() if session.revoked_at else None,
                session.id,
            ),
        )
        self.conn.commit()
        return session
