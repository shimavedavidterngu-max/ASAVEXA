"""
ORM model for the organisation profile (legal name, registration and tax
numbers, address, contacts, base currency, fiscal-year start, reporting
framework).

This table is created on application start-up (see
`ensure_profile_table()` and its call in api/main.py) with
`CREATE TABLE IF NOT EXISTS` semantics, rather than through schema.sql +
an Alembic revision. It is a purely additive table that nothing else
references, so creating it idempotently is safe on both brand-new and
already-deployed databases, and it leaves the existing single-revision
migration history untouched.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, get_engine


class OrganisationProfileORM(Base):
    __tablename__ = "organisation_profiles"

    org_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("organisations.id"), primary_key=True)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_by: Mapped[str] = mapped_column(String, nullable=False)


def ensure_profile_table() -> None:
    """Idempotent: creates organisation_profiles if it does not exist."""
    OrganisationProfileORM.__table__.create(bind=get_engine(), checkfirst=True)
