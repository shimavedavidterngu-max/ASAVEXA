"""
SQLite-backed implementation of the Controls & Compliance repositories.
Stdlib only (sqlite3, json) — same discipline as every other module's
SQLite adapter.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from typing import List, Optional

from ..domain.enums import ControlDomain, ControlResult, ControlSeverity, FindingStatus, RemediationStatus
from ..domain.models import ControlDefinition, ControlExecution, Finding, Remediation

SCHEMA = """
CREATE TABLE IF NOT EXISTS control_definitions (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    objective TEXT NOT NULL,
    severity TEXT NOT NULL,
    domain TEXT NOT NULL,
    check_key TEXT NOT NULL,
    frequency TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(org_id, code)
);

CREATE TABLE IF NOT EXISTS control_executions (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    control_id TEXT NOT NULL,
    period_id TEXT,
    executed_by TEXT NOT NULL,
    executed_at TEXT NOT NULL,
    result TEXT NOT NULL,
    explanation TEXT NOT NULL,
    reference TEXT NOT NULL DEFAULT '{}',
    reviewed_by TEXT,
    reviewed_at TEXT,
    finding_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_exec_org_control ON control_executions(org_id, control_id);
CREATE INDEX IF NOT EXISTS idx_exec_org_period ON control_executions(org_id, period_id);

CREATE TABLE IF NOT EXISTS findings (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    control_id TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    description TEXT NOT NULL,
    severity TEXT NOT NULL,
    status TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    evidence_ref TEXT,
    remediation_id TEXT,
    closed_by TEXT,
    closed_at TEXT,
    history TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_finding_org_status ON findings(org_id, status);
CREATE INDEX IF NOT EXISTS idx_finding_org_control ON findings(org_id, control_id);

CREATE TABLE IF NOT EXISTS remediations (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    finding_id TEXT NOT NULL,
    action TEXT NOT NULL,
    owner TEXT NOT NULL,
    status TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    due_date TEXT,
    completion_evidence_ref TEXT,
    completed_by TEXT,
    completed_at TEXT,
    verified_by TEXT,
    verified_at TEXT,
    verification_note TEXT
);
CREATE INDEX IF NOT EXISTS idx_remediation_org_finding ON remediations(org_id, finding_id);
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


class SqliteControlDefinitionRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def _row_to_domain(self, row) -> ControlDefinition:
        return ControlDefinition(
            id=row["id"], org_id=row["org_id"], code=row["code"], name=row["name"],
            description=row["description"], objective=row["objective"],
            severity=ControlSeverity(row["severity"]), domain=ControlDomain(row["domain"]),
            check_key=row["check_key"], frequency=row["frequency"],
            is_active=bool(row["is_active"]), created_by=row["created_by"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def create(self, definition: ControlDefinition) -> ControlDefinition:
        d = definition
        self.conn.execute(
            "INSERT INTO control_definitions (id, org_id, code, name, description, objective, "
            "severity, domain, check_key, frequency, is_active, created_by, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                d.id, d.org_id, d.code, d.name, d.description, d.objective, d.severity.value,
                d.domain.value, d.check_key, d.frequency, int(d.is_active), d.created_by,
                d.created_at.isoformat(),
            ),
        )
        self.conn.commit()
        return definition

    def get(self, org_id: str, definition_id: str) -> Optional[ControlDefinition]:
        row = self.conn.execute(
            "SELECT * FROM control_definitions WHERE org_id=? AND id=?", (org_id, definition_id)
        ).fetchone()
        return self._row_to_domain(row) if row else None

    def get_by_code(self, org_id: str, code: str) -> Optional[ControlDefinition]:
        row = self.conn.execute(
            "SELECT * FROM control_definitions WHERE org_id=? AND code=?", (org_id, code)
        ).fetchone()
        return self._row_to_domain(row) if row else None

    def update(self, definition: ControlDefinition) -> ControlDefinition:
        d = definition
        self.conn.execute(
            "UPDATE control_definitions SET name=?, description=?, objective=?, severity=?, "
            "frequency=?, is_active=? WHERE id=?",
            (d.name, d.description, d.objective, d.severity.value, d.frequency, int(d.is_active), d.id),
        )
        self.conn.commit()
        return definition

    def list_for_org(self, org_id: str, active_only: bool = False) -> List[ControlDefinition]:
        query = "SELECT * FROM control_definitions WHERE org_id=?"
        params: list = [org_id]
        if active_only:
            query += " AND is_active=1"
        query += " ORDER BY code"
        rows = self.conn.execute(query, params).fetchall()
        return [self._row_to_domain(r) for r in rows]


class SqliteControlExecutionRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def _row_to_domain(self, row) -> ControlExecution:
        return ControlExecution(
            id=row["id"], org_id=row["org_id"], control_id=row["control_id"],
            period_id=row["period_id"], executed_by=row["executed_by"],
            executed_at=datetime.fromisoformat(row["executed_at"]),
            result=ControlResult(row["result"]), explanation=row["explanation"],
            reference=json.loads(row["reference"]) if row["reference"] else {},
            reviewed_by=row["reviewed_by"],
            reviewed_at=datetime.fromisoformat(row["reviewed_at"]) if row["reviewed_at"] else None,
            finding_id=row["finding_id"],
        )

    def create(self, execution: ControlExecution) -> ControlExecution:
        e = execution
        self.conn.execute(
            "INSERT INTO control_executions (id, org_id, control_id, period_id, executed_by, "
            "executed_at, result, explanation, reference, reviewed_by, reviewed_at, finding_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                e.id, e.org_id, e.control_id, e.period_id, e.executed_by, e.executed_at.isoformat(),
                e.result.value, e.explanation, json.dumps(e.reference), e.reviewed_by,
                e.reviewed_at.isoformat() if e.reviewed_at else None, e.finding_id,
            ),
        )
        self.conn.commit()
        return execution

    def get(self, org_id: str, execution_id: str) -> Optional[ControlExecution]:
        row = self.conn.execute(
            "SELECT * FROM control_executions WHERE org_id=? AND id=?", (org_id, execution_id)
        ).fetchone()
        return self._row_to_domain(row) if row else None

    def update(self, execution: ControlExecution) -> ControlExecution:
        """Only reviewed_by/reviewed_at/finding_id are ever written here
        — result/explanation/reference are set once at creation and
        never mutated (see the model's own docstring)."""
        e = execution
        self.conn.execute(
            "UPDATE control_executions SET reviewed_by=?, reviewed_at=?, finding_id=? WHERE id=?",
            (
                e.reviewed_by, e.reviewed_at.isoformat() if e.reviewed_at else None,
                e.finding_id, e.id,
            ),
        )
        self.conn.commit()
        return execution

    def list_for_control(self, org_id: str, control_id: str) -> List[ControlExecution]:
        rows = self.conn.execute(
            "SELECT * FROM control_executions WHERE org_id=? AND control_id=? ORDER BY executed_at",
            (org_id, control_id),
        ).fetchall()
        return [self._row_to_domain(r) for r in rows]

    def list_for_org(self, org_id: str, period_id: Optional[str] = None) -> List[ControlExecution]:
        query = "SELECT * FROM control_executions WHERE org_id=?"
        params: list = [org_id]
        if period_id is not None:
            query += " AND period_id=?"
            params.append(period_id)
        query += " ORDER BY executed_at"
        rows = self.conn.execute(query, params).fetchall()
        return [self._row_to_domain(r) for r in rows]


class SqliteFindingRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def _row_to_domain(self, row) -> Finding:
        return Finding(
            id=row["id"], org_id=row["org_id"], control_id=row["control_id"],
            execution_id=row["execution_id"], description=row["description"],
            severity=ControlSeverity(row["severity"]), status=FindingStatus(row["status"]),
            created_by=row["created_by"], created_at=datetime.fromisoformat(row["created_at"]),
            evidence_ref=row["evidence_ref"], remediation_id=row["remediation_id"],
            closed_by=row["closed_by"],
            closed_at=datetime.fromisoformat(row["closed_at"]) if row["closed_at"] else None,
            history=json.loads(row["history"]) if row["history"] else [],
        )

    def create(self, finding: Finding) -> Finding:
        f = finding
        self.conn.execute(
            "INSERT INTO findings (id, org_id, control_id, execution_id, description, severity, "
            "status, created_by, created_at, evidence_ref, remediation_id, closed_by, closed_at, "
            "history) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                f.id, f.org_id, f.control_id, f.execution_id, f.description, f.severity.value,
                f.status.value, f.created_by, f.created_at.isoformat(), f.evidence_ref,
                f.remediation_id, f.closed_by, f.closed_at.isoformat() if f.closed_at else None,
                json.dumps(f.history),
            ),
        )
        self.conn.commit()
        return finding

    def get(self, org_id: str, finding_id: str) -> Optional[Finding]:
        row = self.conn.execute(
            "SELECT * FROM findings WHERE org_id=? AND id=?", (org_id, finding_id)
        ).fetchone()
        return self._row_to_domain(row) if row else None

    def update(self, finding: Finding) -> Finding:
        f = finding
        self.conn.execute(
            "UPDATE findings SET status=?, evidence_ref=?, remediation_id=?, closed_by=?, "
            "closed_at=?, history=? WHERE id=?",
            (
                f.status.value, f.evidence_ref, f.remediation_id, f.closed_by,
                f.closed_at.isoformat() if f.closed_at else None, json.dumps(f.history), f.id,
            ),
        )
        self.conn.commit()
        return finding

    def list_for_org(self, org_id: str, status: Optional[str] = None) -> List[Finding]:
        query = "SELECT * FROM findings WHERE org_id=?"
        params: list = [org_id]
        if status is not None:
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY created_at"
        rows = self.conn.execute(query, params).fetchall()
        return [self._row_to_domain(r) for r in rows]

    def list_for_control(self, org_id: str, control_id: str) -> List[Finding]:
        rows = self.conn.execute(
            "SELECT * FROM findings WHERE org_id=? AND control_id=? ORDER BY created_at",
            (org_id, control_id),
        ).fetchall()
        return [self._row_to_domain(r) for r in rows]


class SqliteRemediationRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def _row_to_domain(self, row) -> Remediation:
        return Remediation(
            id=row["id"], org_id=row["org_id"], finding_id=row["finding_id"], action=row["action"],
            owner=row["owner"], status=RemediationStatus(row["status"]), created_by=row["created_by"],
            created_at=datetime.fromisoformat(row["created_at"]),
            due_date=date.fromisoformat(row["due_date"]) if row["due_date"] else None,
            completion_evidence_ref=row["completion_evidence_ref"],
            completed_by=row["completed_by"],
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            verified_by=row["verified_by"],
            verified_at=datetime.fromisoformat(row["verified_at"]) if row["verified_at"] else None,
            verification_note=row["verification_note"],
        )

    def create(self, remediation: Remediation) -> Remediation:
        r = remediation
        self.conn.execute(
            "INSERT INTO remediations (id, org_id, finding_id, action, owner, status, created_by, "
            "created_at, due_date, completion_evidence_ref, completed_by, completed_at, "
            "verified_by, verified_at, verification_note) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                r.id, r.org_id, r.finding_id, r.action, r.owner, r.status.value, r.created_by,
                r.created_at.isoformat(), r.due_date.isoformat() if r.due_date else None,
                r.completion_evidence_ref, r.completed_by,
                r.completed_at.isoformat() if r.completed_at else None,
                r.verified_by, r.verified_at.isoformat() if r.verified_at else None,
                r.verification_note,
            ),
        )
        self.conn.commit()
        return remediation

    def get(self, org_id: str, remediation_id: str) -> Optional[Remediation]:
        row = self.conn.execute(
            "SELECT * FROM remediations WHERE org_id=? AND id=?", (org_id, remediation_id)
        ).fetchone()
        return self._row_to_domain(row) if row else None

    def update(self, remediation: Remediation) -> Remediation:
        r = remediation
        self.conn.execute(
            "UPDATE remediations SET status=?, completion_evidence_ref=?, completed_by=?, "
            "completed_at=?, verified_by=?, verified_at=?, verification_note=? WHERE id=?",
            (
                r.status.value, r.completion_evidence_ref, r.completed_by,
                r.completed_at.isoformat() if r.completed_at else None,
                r.verified_by, r.verified_at.isoformat() if r.verified_at else None,
                r.verification_note, r.id,
            ),
        )
        self.conn.commit()
        return remediation

    def list_for_finding(self, org_id: str, finding_id: str) -> List[Remediation]:
        rows = self.conn.execute(
            "SELECT * FROM remediations WHERE org_id=? AND finding_id=? ORDER BY created_at",
            (org_id, finding_id),
        ).fetchall()
        return [self._row_to_domain(r) for r in rows]
