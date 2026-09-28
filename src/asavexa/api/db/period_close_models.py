"""SQLAlchemy ORM model for Period Close's one persisted entity:
PeriodCloseProcess. Mirrors period_close/repository/sqlite_repository.py."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class PeriodCloseProcessORM(Base):
    __tablename__ = "period_close_processes"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("organisations.id"))
    period_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("accounting_periods.id"))
    status: Mapped[str] = mapped_column(String, nullable=False, default="REQUESTED")
    requested_by: Mapped[str] = mapped_column(String, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    last_findings: Mapped[list] = mapped_column(JSONB, default=list)
    reviewed_by: Mapped[str | None] = mapped_column(String, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_by: Mapped[str | None] = mapped_column(String, nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    supersedes_close_process_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
