"""SQLAlchemy implementation of the shared AuditRepository. Shared by
the Accounting Engine, Identity module, and Evidence Vault adapters."""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...audit.models import AuditEvent
from .audit_models import AuditEventORM


def _row_to_domain(row: AuditEventORM) -> AuditEvent:
    return AuditEvent(
        id=row.id, org_id=row.org_id, entity_type=row.entity_type, entity_id=row.entity_id,
        action=row.action, actor=row.actor, timestamp=row.timestamp,
        previous_value=row.previous_value, new_value=row.new_value,
        reason=row.reason, related_record_id=row.related_record_id,
    )


class SqlAlchemyAuditRepository:
    def __init__(self, session: Session):
        self.session = session

    def record(self, event: AuditEvent) -> AuditEvent:
        row = AuditEventORM(
            id=event.id, org_id=event.org_id, entity_type=event.entity_type,
            entity_id=event.entity_id, action=event.action, actor=event.actor,
            timestamp=event.timestamp, previous_value=event.previous_value,
            new_value=event.new_value, reason=event.reason,
            related_record_id=event.related_record_id,
        )
        self.session.add(row)
        return event

    def list_for_entity(
        self, entity_type: str, entity_id: str, org_id: Optional[str] = None
    ) -> List[AuditEvent]:
        query = select(AuditEventORM).where(
            AuditEventORM.entity_type == entity_type, AuditEventORM.entity_id == entity_id
        )
        if org_id is not None:
            query = query.where(AuditEventORM.org_id == org_id)
        rows = self.session.scalars(query.order_by(AuditEventORM.timestamp)).all()
        return [_row_to_domain(r) for r in rows]

    def list_for_org(self, org_id: str) -> List[AuditEvent]:
        rows = self.session.scalars(
            select(AuditEventORM).where(AuditEventORM.org_id == org_id).order_by(AuditEventORM.timestamp)
        ).all()
        return [_row_to_domain(r) for r in rows]

    def list_for_actor(self, actor: str) -> List[AuditEvent]:
        rows = self.session.scalars(
            select(AuditEventORM).where(AuditEventORM.actor == actor).order_by(AuditEventORM.timestamp)
        ).all()
        return [_row_to_domain(r) for r in rows]
