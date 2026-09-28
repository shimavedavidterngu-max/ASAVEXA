"""
SQLite-backed implementation of the accounting repositories.

This uses only the Python standard library (`sqlite3`, `decimal`) — no
external dependencies — so the Accounting Engine's core logic can be
exercised and unit-tested without installing or running PostgreSQL.

Money is stored as TEXT (the exact Decimal string), never as REAL/float,
to avoid floating-point rounding errors in a ledger. This mirrors the
NUMERIC columns used in schema.sql for the production PostgreSQL schema.

NOTE: audit storage used to live in this file too. It has been promoted
to asavexa.audit.sqlite_repository (shared by every module) — use
`connect()` here for the accounting tables, and
`asavexa.audit.sqlite_repository.ensure_schema(conn)` (or the combined
`asavexa.bootstrap.create_sqlite_connection()`) for a connection that
also has the audit_events table.

For production, use the SQLAlchemy/PostgreSQL adapter under
src/asavexa/api/db/ instead — it implements the same interfaces.
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from ..domain.enums import AccountType, JournalStatus, PeriodStatus
from ..domain.models import (
    Account,
    AccountingPeriod,
    Journal,
    JournalLine,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    currency TEXT NOT NULL,
    parent_id TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    UNIQUE(org_id, code)
);

CREATE TABLE IF NOT EXISTS periods (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    name TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    status TEXT NOT NULL,
    locked_at TEXT,
    locked_by TEXT
);

CREATE TABLE IF NOT EXISTS journals (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    period_id TEXT NOT NULL,
    journal_number TEXT NOT NULL,
    date TEXT NOT NULL,
    description TEXT NOT NULL,
    currency TEXT NOT NULL,
    status TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    posted_by TEXT,
    posted_at TEXT,
    reversal_of_journal_id TEXT,
    reversed_by_journal_id TEXT,
    transaction_ref TEXT,
    evidence_ref TEXT,
    UNIQUE(org_id, journal_number)
);

CREATE TABLE IF NOT EXISTS journal_lines (
    id TEXT PRIMARY KEY,
    journal_id TEXT NOT NULL,
    line_no INTEGER NOT NULL,
    account_id TEXT NOT NULL,
    debit_amount TEXT NOT NULL,
    credit_amount TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT ''
);
"""


def connect(db_path: str = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def new_id() -> str:
    return str(uuid.uuid4())


class SqliteAccountRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, account: Account) -> Account:
        self.conn.execute(
            "INSERT INTO accounts (id, org_id, code, name, type, currency, "
            "parent_id, is_active, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                account.id, account.org_id, account.code, account.name,
                account.type.value, account.currency, account.parent_id,
                int(account.is_active),
                (account.created_at or datetime.utcnow()).isoformat(),
            ),
        )
        self.conn.commit()
        return account

    def _row_to_account(self, row) -> Account:
        return Account(
            id=row["id"], org_id=row["org_id"], code=row["code"],
            name=row["name"], type=AccountType(row["type"]),
            currency=row["currency"], parent_id=row["parent_id"],
            is_active=bool(row["is_active"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def get(self, org_id: str, account_id: str) -> Optional[Account]:
        row = self.conn.execute(
            "SELECT * FROM accounts WHERE org_id=? AND id=?",
            (org_id, account_id),
        ).fetchone()
        return self._row_to_account(row) if row else None

    def get_by_code(self, org_id: str, code: str) -> Optional[Account]:
        row = self.conn.execute(
            "SELECT * FROM accounts WHERE org_id=? AND code=?",
            (org_id, code),
        ).fetchone()
        return self._row_to_account(row) if row else None

    def list_for_org(self, org_id: str) -> List[Account]:
        rows = self.conn.execute(
            "SELECT * FROM accounts WHERE org_id=? ORDER BY code", (org_id,)
        ).fetchall()
        return [self._row_to_account(r) for r in rows]


class SqlitePeriodRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def _row_to_period(self, row) -> AccountingPeriod:
        return AccountingPeriod(
            id=row["id"], org_id=row["org_id"], name=row["name"],
            start_date=date.fromisoformat(row["start_date"]),
            end_date=date.fromisoformat(row["end_date"]),
            status=PeriodStatus(row["status"]),
            locked_at=datetime.fromisoformat(row["locked_at"]) if row["locked_at"] else None,
            locked_by=row["locked_by"],
        )

    def create(self, period: AccountingPeriod) -> AccountingPeriod:
        self.conn.execute(
            "INSERT INTO periods (id, org_id, name, start_date, end_date, "
            "status, locked_at, locked_by) VALUES (?,?,?,?,?,?,?,?)",
            (
                period.id, period.org_id, period.name,
                period.start_date.isoformat(), period.end_date.isoformat(),
                period.status.value,
                period.locked_at.isoformat() if period.locked_at else None,
                period.locked_by,
            ),
        )
        self.conn.commit()
        return period

    def get(self, org_id: str, period_id: str) -> Optional[AccountingPeriod]:
        row = self.conn.execute(
            "SELECT * FROM periods WHERE org_id=? AND id=?",
            (org_id, period_id),
        ).fetchone()
        return self._row_to_period(row) if row else None

    def get_for_date(self, org_id: str, on_date: date) -> Optional[AccountingPeriod]:
        row = self.conn.execute(
            "SELECT * FROM periods WHERE org_id=? AND start_date<=? AND end_date>=?"
            " ORDER BY start_date DESC LIMIT 1",
            (org_id, on_date.isoformat(), on_date.isoformat()),
        ).fetchone()
        return self._row_to_period(row) if row else None

    def update(self, period: AccountingPeriod) -> AccountingPeriod:
        self.conn.execute(
            "UPDATE periods SET status=?, locked_at=?, locked_by=? WHERE id=?",
            (
                period.status.value,
                period.locked_at.isoformat() if period.locked_at else None,
                period.locked_by, period.id,
            ),
        )
        self.conn.commit()
        return period

    def list_for_org(self, org_id: str) -> List[AccountingPeriod]:
        rows = self.conn.execute(
            "SELECT * FROM periods WHERE org_id=? ORDER BY start_date", (org_id,)
        ).fetchall()
        return [self._row_to_period(r) for r in rows]


class SqliteJournalRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def _load_lines(self, journal_id: str) -> List[JournalLine]:
        rows = self.conn.execute(
            "SELECT * FROM journal_lines WHERE journal_id=? ORDER BY line_no",
            (journal_id,),
        ).fetchall()
        return [
            JournalLine(
                id=r["id"], journal_id=r["journal_id"], line_no=r["line_no"],
                account_id=r["account_id"],
                debit_amount=Decimal(r["debit_amount"]),
                credit_amount=Decimal(r["credit_amount"]),
                description=r["description"],
            )
            for r in rows
        ]

    def _row_to_journal(self, row) -> Journal:
        return Journal(
            id=row["id"], org_id=row["org_id"], period_id=row["period_id"],
            journal_number=row["journal_number"],
            date=date.fromisoformat(row["date"]),
            description=row["description"], currency=row["currency"],
            created_by=row["created_by"],
            created_at=datetime.fromisoformat(row["created_at"]),
            lines=self._load_lines(row["id"]),
            status=JournalStatus(row["status"]),
            posted_by=row["posted_by"],
            posted_at=datetime.fromisoformat(row["posted_at"]) if row["posted_at"] else None,
            reversal_of_journal_id=row["reversal_of_journal_id"],
            reversed_by_journal_id=row["reversed_by_journal_id"],
            transaction_ref=row["transaction_ref"],
            evidence_ref=row["evidence_ref"],
        )

    def create(self, journal: Journal) -> Journal:
        self.conn.execute(
            "INSERT INTO journals (id, org_id, period_id, journal_number, "
            "date, description, currency, status, created_by, created_at, "
            "posted_by, posted_at, reversal_of_journal_id, "
            "reversed_by_journal_id, transaction_ref, evidence_ref) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                journal.id, journal.org_id, journal.period_id,
                journal.journal_number, journal.date.isoformat(),
                journal.description, journal.currency, journal.status.value,
                journal.created_by, journal.created_at.isoformat(),
                journal.posted_by,
                journal.posted_at.isoformat() if journal.posted_at else None,
                journal.reversal_of_journal_id,
                journal.reversed_by_journal_id,
                journal.transaction_ref, journal.evidence_ref,
            ),
        )
        for line in journal.lines:
            self.conn.execute(
                "INSERT INTO journal_lines (id, journal_id, line_no, "
                "account_id, debit_amount, credit_amount, description) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    line.id, journal.id, line.line_no, line.account_id,
                    str(line.debit_amount), str(line.credit_amount),
                    line.description,
                ),
            )
        self.conn.commit()
        return journal

    def get(self, org_id: str, journal_id: str) -> Optional[Journal]:
        row = self.conn.execute(
            "SELECT * FROM journals WHERE org_id=? AND id=?",
            (org_id, journal_id),
        ).fetchone()
        return self._row_to_journal(row) if row else None

    def update(self, journal: Journal) -> Journal:
        """Used only for status transitions (post/reverse) and metadata —
        never to mutate a POSTED journal's lines. Line immutability is
        enforced in the service layer (assert_journal_editable), not here;
        this repository is a dumb storage adapter by design.

        Includes evidence_ref/transaction_ref: the Journal model has
        always declared these settable after creation (see its
        docstring — "populated once the Evidence Vault module exists"),
        and callers (the Evidence integration pattern used since that
        module was built) rely on `journal.evidence_ref = x` followed by
        `journals.update(journal)` actually persisting it. It previously
        did not — this was a storage-adapter gap, not a business-rule
        change; fixed when Reporting's provenance tracing exposed it via
        a real re-fetch from the database."""
        self.conn.execute(
            "UPDATE journals SET status=?, posted_by=?, posted_at=?, "
            "reversal_of_journal_id=?, reversed_by_journal_id=?, "
            "description=?, evidence_ref=?, transaction_ref=? WHERE id=?",
            (
                journal.status.value, journal.posted_by,
                journal.posted_at.isoformat() if journal.posted_at else None,
                journal.reversal_of_journal_id,
                journal.reversed_by_journal_id,
                journal.description, journal.evidence_ref, journal.transaction_ref,
                journal.id,
            ),
        )
        self.conn.commit()
        return journal

    def list_for_org(
        self, org_id, period_id=None, account_id=None, status=None
    ) -> List[Journal]:
        query = "SELECT DISTINCT j.* FROM journals j"
        params: list = [org_id]
        joins = ""
        where = ["j.org_id=?"]
        if account_id:
            joins = " JOIN journal_lines jl ON jl.journal_id = j.id"
            where.append("jl.account_id=?")
            params.append(account_id)
        if period_id:
            where.append("j.period_id=?")
            params.append(period_id)
        if status:
            where.append("j.status=?")
            params.append(status)
        query += joins + " WHERE " + " AND ".join(where) + " ORDER BY j.date, j.journal_number"
        rows = self.conn.execute(query, params).fetchall()
        return [self._row_to_journal(r) for r in rows]

    def next_journal_number(self, org_id: str) -> str:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM journals WHERE org_id=?", (org_id,)
        ).fetchone()
        return f"JRN-{row['n'] + 1:06d}"

