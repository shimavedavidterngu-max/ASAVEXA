"""
PostgreSQL/SQLAlchemy implementation of the Controls & Compliance
repositories. Implements the same Protocols as
compliance/repository/sqlite_repository.py. Not executed in the
sandbox that produced this starter codebase.
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...compliance.domain.enums import ControlDomain, ControlResult, ControlSeverity, FindingStatus, RemediationStatus
from ...compliance.domain.models import ControlDefinition, ControlExecution, Finding, Remediation
from .compliance_models import ControlDefinitionORM, ControlExecutionORM, FindingORM, RemediationORM


def _definition_to_domain(row: ControlDefinitionORM) -> ControlDefinition:
    return ControlDefinition(
        id=row.id, org_id=row.org_id, code=row.code, name=row.name, description=row.description,
        objective=row.objective, severity=ControlSeverity(row.severity), domain=ControlDomain(row.domain),
        check_key=row.check_key, created_by=row.created_by, created_at=row.created_at,
        frequency=row.frequency, is_active=row.is_active,
    )


def _execution_to_domain(row: ControlExecutionORM) -> ControlExecution:
    return ControlExecution(
        id=row.id, org_id=row.org_id, control_id=row.control_id, executed_by=row.executed_by,
        executed_at=row.executed_at, result=ControlResult(row.result), explanation=row.explanation,
        reference=row.reference or {}, period_id=row.period_id,
        reviewed_by=row.reviewed_by, reviewed_at=row.reviewed_at, finding_id=row.finding_id,
    )


def _finding_to_domain(row: FindingORM) -> Finding:
    return Finding(
        id=row.id, org_id=row.org_id, control_id=row.control_id, execution_id=row.execution_id,
        description=row.description, severity=ControlSeverity(row.severity), status=FindingStatus(row.status),
        created_by=row.created_by, created_at=row.created_at, evidence_ref=row.evidence_ref,
        remediation_id=row.remediation_id, closed_by=row.closed_by, closed_at=row.closed_at,
        history=row.history or [],
    )


def _remediation_to_domain(row: RemediationORM) -> Remediation:
    return Remediation(
        id=row.id, org_id=row.org_id, finding_id=row.finding_id, action=row.action, owner=row.owner,
        status=RemediationStatus(row.status), created_by=row.created_by, created_at=row.created_at,
        due_date=row.due_date, completion_evidence_ref=row.completion_evidence_ref,
        completed_by=row.completed_by, completed_at=row.completed_at,
        verified_by=row.verified_by, verified_at=row.verified_at, verification_note=row.verification_note,
    )


class SqlAlchemyControlDefinitionRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, definition: ControlDefinition) -> ControlDefinition:
        d = definition
        row = ControlDefinitionORM(
            id=d.id, org_id=d.org_id, code=d.code, name=d.name, description=d.description,
            objective=d.objective, severity=d.severity.value, domain=d.domain.value,
            check_key=d.check_key, frequency=d.frequency, is_active=d.is_active,
            created_by=d.created_by, created_at=d.created_at,
        )
        self.session.add(row)
        return definition

    def get(self, org_id: str, definition_id: str) -> Optional[ControlDefinition]:
        row = self.session.get(ControlDefinitionORM, definition_id)
        if row is None or row.org_id != org_id:
            return None
        return _definition_to_domain(row)

    def get_by_code(self, org_id: str, code: str) -> Optional[ControlDefinition]:
        row = self.session.scalar(
            select(ControlDefinitionORM).where(ControlDefinitionORM.org_id == org_id, ControlDefinitionORM.code == code)
        )
        return _definition_to_domain(row) if row else None

    def update(self, definition: ControlDefinition) -> ControlDefinition:
        d = definition
        row = self.session.get(ControlDefinitionORM, d.id)
        row.name = d.name
        row.description = d.description
        row.objective = d.objective
        row.severity = d.severity.value
        row.frequency = d.frequency
        row.is_active = d.is_active
        return definition

    def list_for_org(self, org_id: str, active_only: bool = False) -> List[ControlDefinition]:
        query = select(ControlDefinitionORM).where(ControlDefinitionORM.org_id == org_id)
        if active_only:
            query = query.where(ControlDefinitionORM.is_active.is_(True))
        rows = self.session.scalars(query.order_by(ControlDefinitionORM.code)).all()
        return [_definition_to_domain(r) for r in rows]


class SqlAlchemyControlExecutionRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, execution: ControlExecution) -> ControlExecution:
        e = execution
        row = ControlExecutionORM(
            id=e.id, org_id=e.org_id, control_id=e.control_id, period_id=e.period_id,
            executed_by=e.executed_by, executed_at=e.executed_at, result=e.result.value,
            explanation=e.explanation, reference=e.reference, reviewed_by=e.reviewed_by,
            reviewed_at=e.reviewed_at, finding_id=e.finding_id,
        )
        self.session.add(row)
        return execution

    def get(self, org_id: str, execution_id: str) -> Optional[ControlExecution]:
        row = self.session.get(ControlExecutionORM, execution_id)
        if row is None or row.org_id != org_id:
            return None
        return _execution_to_domain(row)

    def update(self, execution: ControlExecution) -> ControlExecution:
        e = execution
        row = self.session.get(ControlExecutionORM, e.id)
        row.reviewed_by = e.reviewed_by
        row.reviewed_at = e.reviewed_at
        row.finding_id = e.finding_id
        return execution

    def list_for_control(self, org_id: str, control_id: str) -> List[ControlExecution]:
        rows = self.session.scalars(
            select(ControlExecutionORM)
            .where(ControlExecutionORM.org_id == org_id, ControlExecutionORM.control_id == control_id)
            .order_by(ControlExecutionORM.executed_at)
        ).all()
        return [_execution_to_domain(r) for r in rows]

    def list_for_org(self, org_id: str, period_id: Optional[str] = None) -> List[ControlExecution]:
        query = select(ControlExecutionORM).where(ControlExecutionORM.org_id == org_id)
        if period_id is not None:
            query = query.where(ControlExecutionORM.period_id == period_id)
        rows = self.session.scalars(query.order_by(ControlExecutionORM.executed_at)).all()
        return [_execution_to_domain(r) for r in rows]


class SqlAlchemyFindingRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, finding: Finding) -> Finding:
        f = finding
        row = FindingORM(
            id=f.id, org_id=f.org_id, control_id=f.control_id, execution_id=f.execution_id,
            description=f.description, severity=f.severity.value, status=f.status.value,
            created_by=f.created_by, created_at=f.created_at, evidence_ref=f.evidence_ref,
            remediation_id=f.remediation_id, closed_by=f.closed_by, closed_at=f.closed_at,
            history=f.history,
        )
        self.session.add(row)
        return finding

    def get(self, org_id: str, finding_id: str) -> Optional[Finding]:
        row = self.session.get(FindingORM, finding_id)
        if row is None or row.org_id != org_id:
            return None
        return _finding_to_domain(row)

    def update(self, finding: Finding) -> Finding:
        f = finding
        row = self.session.get(FindingORM, f.id)
        row.status = f.status.value
        row.evidence_ref = f.evidence_ref
        row.remediation_id = f.remediation_id
        row.closed_by = f.closed_by
        row.closed_at = f.closed_at
        row.history = f.history
        return finding

    def list_for_org(self, org_id: str, status: Optional[str] = None) -> List[Finding]:
        query = select(FindingORM).where(FindingORM.org_id == org_id)
        if status is not None:
            query = query.where(FindingORM.status == status)
        rows = self.session.scalars(query.order_by(FindingORM.created_at)).all()
        return [_finding_to_domain(r) for r in rows]

    def list_for_control(self, org_id: str, control_id: str) -> List[Finding]:
        rows = self.session.scalars(
            select(FindingORM)
            .where(FindingORM.org_id == org_id, FindingORM.control_id == control_id)
            .order_by(FindingORM.created_at)
        ).all()
        return [_finding_to_domain(r) for r in rows]


class SqlAlchemyRemediationRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, remediation: Remediation) -> Remediation:
        r = remediation
        row = RemediationORM(
            id=r.id, org_id=r.org_id, finding_id=r.finding_id, action=r.action, owner=r.owner,
            status=r.status.value, created_by=r.created_by, created_at=r.created_at, due_date=r.due_date,
            completion_evidence_ref=r.completion_evidence_ref, completed_by=r.completed_by,
            completed_at=r.completed_at, verified_by=r.verified_by, verified_at=r.verified_at,
            verification_note=r.verification_note,
        )
        self.session.add(row)
        return remediation

    def get(self, org_id: str, remediation_id: str) -> Optional[Remediation]:
        row = self.session.get(RemediationORM, remediation_id)
        if row is None or row.org_id != org_id:
            return None
        return _remediation_to_domain(row)

    def update(self, remediation: Remediation) -> Remediation:
        r = remediation
        row = self.session.get(RemediationORM, r.id)
        row.status = r.status.value
        row.completion_evidence_ref = r.completion_evidence_ref
        row.completed_by = r.completed_by
        row.completed_at = r.completed_at
        row.verified_by = r.verified_by
        row.verified_at = r.verified_at
        row.verification_note = r.verification_note
        return remediation

    def list_for_finding(self, org_id: str, finding_id: str) -> List[Remediation]:
        rows = self.session.scalars(
            select(RemediationORM)
            .where(RemediationORM.org_id == org_id, RemediationORM.finding_id == finding_id)
            .order_by(RemediationORM.created_at)
        ).all()
        return [_remediation_to_domain(r) for r in rows]
