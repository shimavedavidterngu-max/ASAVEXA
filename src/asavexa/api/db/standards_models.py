"""ORM model for an organisation's saved standards configuration
(jurisdiction, entity type, framework, accounting-policy overrides).
Created at start-up with CREATE TABLE IF NOT EXISTS semantics — see
profile_models.py for why."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, get_engine


class OrganisationStandardsORM(Base):
    __tablename__ = "organisation_standards"

    org_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("organisations.id"), primary_key=True)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_by: Mapped[str] = mapped_column(String, nullable=False)


def ensure_standards_table() -> None:
    OrganisationStandardsORM.__table__.create(bind=get_engine(), checkfirst=True)
