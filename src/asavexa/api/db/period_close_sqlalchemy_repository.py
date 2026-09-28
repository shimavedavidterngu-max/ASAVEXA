"""
PostgreSQL/SQLAlchemy implementation of the Period Close repository.
Implements the same Protocol as
period_close/repository/sqlite_repository.py. Not executed in the
sandbox that produced this starter codebase.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...period_close.domain.enums import PeriodCloseStatus
from ...period_close.domain.models import PeriodCloseProcess
from .period_close_models import PeriodCloseProcessORM

_ACTIVE_STATUSES = (
    PeriodCloseStatus.REQUESTED.value,
    PeriodCloseStatus.READY_FOR_CLOSE.value,
    PeriodCloseStatus.CONTROLS_FAILED.value,
)


def _row_to_domain(row: PeriodCloseProcessORM) -> PeriodCloseProcess:
    return PeriodCloseProcess(
        id=row.id, org_id=row.org_id, period_id=row.period_id,
        status=PeriodCloseStatus(row.status), requested_by=row.requested_by,
        requested_at=row.requested_at, last_findings=row.last_findings or [],
        reviewed_by=row.reviewed_by, reviewed_at=row.reviewed_at,
        approved_by=row.approved_by, approved_at=row.approved_at,
        rejected_by=row.rejected_by, rejected_at=row.rejected_at,
        rejection_reason=row.rejection_reason,
        supersedes_close_process_id=row.supersedes_close_process_id,
    )


class SqlAlchemyPeriodCloseRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, process: PeriodCloseProcess) -> PeriodCloseProcess:
        p = process
        row = PeriodCloseProcessORM(
            id=p.id, org_id=p.org_id, period_id=p.period_id, status=p.status.value,
            requested_by=p.requested_by, requested_at=p.requested_at, last_findings=p.last_findings,
            reviewed_by=p.reviewed_by, reviewed_at=p.reviewed_at,
            approved_by=p.approved_by, approved_at=p.approved_at,
            rejected_by=p.rejected_by, rejected_at=p.rejected_at,
            rejection_reason=p.rejection_reason,
            supersedes_close_process_id=p.supersedes_close_process_id,
        )
        self.session.add(row)
        return process

    def get(self, org_id: str, process_id: str) -> Optional[PeriodCloseProcess]:
        row = self.session.get(PeriodCloseProcessORM, process_id)
        if row is None or row.org_id != org_id:
            return None
        return _row_to_domain(row)

    def update(self, process: PeriodCloseProcess) -> PeriodCloseProcess:
        p = process
        row = self.session.get(PeriodCloseProcessORM, p.id)
        row.status = p.status.value
        row.last_findings = p.last_findings
        row.reviewed_by = p.reviewed_by
        row.reviewed_at = p.reviewed_at
        row.approved_by = p.approved_by
        row.approved_at = p.approved_at
        row.rejected_by = p.rejected_by
        row.rejected_at = p.rejected_at
        row.rejection_reason = p.rejection_reason
        return process

    def list_for_period(self, org_id: str, period_id: str) -> List[PeriodCloseProcess]:
        rows = self.session.scalars(
            select(PeriodCloseProcessORM)
            .where(PeriodCloseProcessORM.org_id == org_id, PeriodCloseProcessORM.period_id == period_id)
            .order_by(PeriodCloseProcessORM.requested_at)
        ).all()
        return [_row_to_domain(r) for r in rows]

    def get_active_for_period(self, org_id: str, period_id: str) -> Optional[PeriodCloseProcess]:
        row = self.session.scalar(
            select(PeriodCloseProcessORM)
            .where(
                PeriodCloseProcessORM.org_id == org_id,
                PeriodCloseProcessORM.period_id == period_id,
                PeriodCloseProcessORM.status.in_(_ACTIVE_STATUSES),
            )
            .order_by(PeriodCloseProcessORM.requested_at.desc())
        )
        return _row_to_domain(row) if row else None
