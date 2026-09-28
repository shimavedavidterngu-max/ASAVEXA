"""
SQLAlchemy ORM model for the shared audit trail. Every module's
SQLAlchemy repository writes here through api/db/audit_sqlalchemy_repository.py
— never duplicate this table per module.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class AuditEventORM(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    # Nullable: some actions (login/logout) are not yet scoped to an
    # organisation. Every org-scoped action must still pass a real org_id.
    org_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("organisations.id"), nullable=True
    )
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    actor: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    previous_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_record_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
