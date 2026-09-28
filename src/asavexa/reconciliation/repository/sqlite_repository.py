"""
SQLite-backed implementation of the Reconciliation repositories. Stdlib
only (sqlite3) — same discipline as every other module's SQLite adapter.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from ..domain.enums import BankTransactionStatus, ReconciliationStatus
from ..domain.models import BankTransaction, Reconciliation

SCHEMA = """
CREATE TABLE IF NOT EXISTS reconciliations (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    bank_account_id TEXT NOT NULL,
    name TEXT NOT NULL,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    currency TEXT NOT NULL,
    status TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    submitted_by TEXT,
    submitted_at TEXT,
    approved_by TEXT,
    approved_at TEXT,
    rejected_by TEXT,
    rejected_at TEXT,
    rejection_reason TEXT,
    supersedes_reconciliation_id TEXT,
    evidence_ref TEXT
);
CREATE INDEX IF NOT EXISTS idx_reconciliations_org ON reconciliations(org_id);
CREATE INDEX IF NOT EXISTS idx_reconciliations_org_account ON reconciliations(org_id, bank_account_id);

CREATE TABLE IF NOT EXISTS bank_transactions (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    reconciliation_id TEXT NOT NULL,
    bank_account_id TEXT NOT NULL,
    import_batch_id TEXT NOT NULL,
    dedup_hash TEXT NOT NULL,
    transaction_date TEXT NOT NULL,
    value_date TEXT,
    description TEXT NOT NULL,
    debit_amount TEXT NOT NULL,
    credit_amount TEXT NOT NULL,
    currency TEXT NOT NULL,
    external_ref TEXT,
    status TEXT NOT NULL,
    matched_journal_id TEXT,
    match_reason TEXT,
    match_rule TEXT,
    match_history TEXT NOT NULL DEFAULT '[]',
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(org_id, bank_account_id, dedup_hash)
);
CREATE INDEX IF NOT EXISTS idx_banktxn_org_recon ON bank_transactions(org_id, reconciliation_id);
CREATE INDEX IF NOT EXISTS idx_banktxn_org_account ON bank_transactions(org_id, bank_account_id);
CREATE INDEX IF NOT EXISTS idx_banktxn_org_account_hash ON bank_transactions(org_id, bank_account_id, dedup_hash);
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


class SqliteReconciliationRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def _row_to_domain(self, row) -> Reconciliation:
        return Reconciliation(
            id=row["id"], org_id=row["org_id"], bank_account_id=row["bank_account_id"],
            name=row["name"], period_start=date.fromisoformat(row["period_start"]),
            period_end=date.fromisoformat(row["period_end"]), currency=row["currency"],
            created_by=row["created_by"], created_at=datetime.fromisoformat(row["created_at"]),
            status=ReconciliationStatus(row["status"]),
            submitted_by=row["submitted_by"],
            submitted_at=datetime.fromisoformat(row["submitted_at"]) if row["submitted_at"] else None,
            approved_by=row["approved_by"],
            approved_at=datetime.fromisoformat(row["approved_at"]) if row["approved_at"] else None,
            rejected_by=row["rejected_by"],
            rejected_at=datetime.fromisoformat(row["rejected_at"]) if row["rejected_at"] else None,
            rejection_reason=row["rejection_reason"],
            supersedes_reconciliation_id=row["supersedes_reconciliation_id"],
            evidence_ref=row["evidence_ref"],
        )

    def create(self, reconciliation: Reconciliation) -> Reconciliation:
        r = reconciliation
        self.conn.execute(
            "INSERT INTO reconciliations (id, org_id, bank_account_id, name, period_start, "
            "period_end, currency, status, created_by, created_at, submitted_by, submitted_at, "
            "approved_by, approved_at, rejected_by, rejected_at, rejection_reason, "
            "supersedes_reconciliation_id, evidence_ref) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                r.id, r.org_id, r.bank_account_id, r.name, r.period_start.isoformat(),
                r.period_end.isoformat(), r.currency, r.status.value, r.created_by,
                r.created_at.isoformat(), r.submitted_by,
                r.submitted_at.isoformat() if r.submitted_at else None,
                r.approved_by, r.approved_at.isoformat() if r.approved_at else None,
                r.rejected_by, r.rejected_at.isoformat() if r.rejected_at else None,
                r.rejection_reason, r.supersedes_reconciliation_id, r.evidence_ref,
            ),
        )
        self.conn.commit()
        return reconciliation

    def get(self, org_id: str, reconciliation_id: str) -> Optional[Reconciliation]:
        row = self.conn.execute(
            "SELECT * FROM reconciliations WHERE org_id=? AND id=?", (org_id, reconciliation_id)
        ).fetchone()
        return self._row_to_domain(row) if row else None

    def update(self, reconciliation: Reconciliation) -> Reconciliation:
        r = reconciliation
        self.conn.execute(
            "UPDATE reconciliations SET status=?, submitted_by=?, submitted_at=?, "
            "approved_by=?, approved_at=?, rejected_by=?, rejected_at=?, rejection_reason=?, "
            "evidence_ref=? WHERE id=?",
            (
                r.status.value, r.submitted_by,
                r.submitted_at.isoformat() if r.submitted_at else None,
                r.approved_by, r.approved_at.isoformat() if r.approved_at else None,
                r.rejected_by, r.rejected_at.isoformat() if r.rejected_at else None,
                r.rejection_reason, r.evidence_ref, r.id,
            ),
        )
        self.conn.commit()
        return reconciliation

    def list_for_org(
        self, org_id: str, bank_account_id: Optional[str] = None, status: Optional[str] = None
    ) -> List[Reconciliation]:
        query = "SELECT * FROM reconciliations WHERE org_id=?"
        params: list = [org_id]
        if bank_account_id:
            query += " AND bank_account_id=?"
            params.append(bank_account_id)
        if status:
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY created_at"
        rows = self.conn.execute(query, params).fetchall()
        return [self._row_to_domain(r) for r in rows]


class SqliteBankTransactionRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def _row_to_domain(self, row) -> BankTransaction:
        return BankTransaction(
            id=row["id"], org_id=row["org_id"], reconciliation_id=row["reconciliation_id"],
            bank_account_id=row["bank_account_id"], import_batch_id=row["import_batch_id"],
            dedup_hash=row["dedup_hash"], transaction_date=date.fromisoformat(row["transaction_date"]),
            value_date=date.fromisoformat(row["value_date"]) if row["value_date"] else None,
            description=row["description"], debit_amount=Decimal(row["debit_amount"]),
            credit_amount=Decimal(row["credit_amount"]), currency=row["currency"],
            external_ref=row["external_ref"], status=BankTransactionStatus(row["status"]),
            matched_journal_id=row["matched_journal_id"], match_reason=row["match_reason"],
            match_rule=row["match_rule"],
            match_history=json.loads(row["match_history"]) if row["match_history"] else [],
            created_by=row["created_by"], created_at=datetime.fromisoformat(row["created_at"]),
        )

    def create(self, transaction: BankTransaction) -> BankTransaction:
        t = transaction
        self.conn.execute(
            "INSERT INTO bank_transactions (id, org_id, reconciliation_id, bank_account_id, "
            "import_batch_id, dedup_hash, transaction_date, value_date, description, "
            "debit_amount, credit_amount, currency, external_ref, status, matched_journal_id, "
            "match_reason, match_rule, match_history, created_by, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                t.id, t.org_id, t.reconciliation_id, t.bank_account_id, t.import_batch_id,
                t.dedup_hash, t.transaction_date.isoformat(),
                t.value_date.isoformat() if t.value_date else None,
                t.description, str(t.debit_amount), str(t.credit_amount), t.currency,
                t.external_ref, t.status.value, t.matched_journal_id, t.match_reason,
                t.match_rule, json.dumps(t.match_history), t.created_by, t.created_at.isoformat(),
            ),
        )
        self.conn.commit()
        return transaction

    def get(self, org_id: str, transaction_id: str) -> Optional[BankTransaction]:
        row = self.conn.execute(
            "SELECT * FROM bank_transactions WHERE org_id=? AND id=?", (org_id, transaction_id)
        ).fetchone()
        return self._row_to_domain(row) if row else None

    def update(self, transaction: BankTransaction) -> BankTransaction:
        t = transaction
        self.conn.execute(
            "UPDATE bank_transactions SET status=?, matched_journal_id=?, match_reason=?, "
            "match_rule=?, match_history=?, reconciliation_id=? WHERE id=?",
            (
                t.status.value, t.matched_journal_id, t.match_reason, t.match_rule,
                json.dumps(t.match_history), t.reconciliation_id, t.id,
            ),
        )
        self.conn.commit()
        return transaction

    def list_for_reconciliation(self, org_id: str, reconciliation_id: str) -> List[BankTransaction]:
        rows = self.conn.execute(
            "SELECT * FROM bank_transactions WHERE org_id=? AND reconciliation_id=? "
            "ORDER BY transaction_date",
            (org_id, reconciliation_id),
        ).fetchall()
        return [self._row_to_domain(r) for r in rows]

    def list_for_account(self, org_id: str, bank_account_id: str) -> List[BankTransaction]:
        rows = self.conn.execute(
            "SELECT * FROM bank_transactions WHERE org_id=? AND bank_account_id=? "
            "ORDER BY transaction_date",
            (org_id, bank_account_id),
        ).fetchall()
        return [self._row_to_domain(r) for r in rows]

    def get_by_dedup_hash(self, org_id: str, bank_account_id: str, dedup_hash: str) -> Optional[BankTransaction]:
        row = self.conn.execute(
            "SELECT * FROM bank_transactions WHERE org_id=? AND bank_account_id=? AND dedup_hash=?",
            (org_id, bank_account_id, dedup_hash),
        ).fetchone()
        return self._row_to_domain(row) if row else None
