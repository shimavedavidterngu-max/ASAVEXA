"""
ORM model for the organisation's ownership structure (owners and
subsidiaries), the two Passport identity facts ASAVEXA has no other
source for. Created at application start-up like organisation_profiles
(see api/main.py), not through schema.sql / Alembic.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, get_engine


class OrganisationStructureORM(Base):
    __tablename__ = "organisation_structures"

    org_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("organisations.id"), primary_key=True)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_by: Mapped[str] = mapped_column(String, nullable=False)


def ensure_structure_table() -> None:
    """Idempotent: creates organisation_structures if it does not exist."""
    OrganisationStructureORM.__table__.create(bind=get_engine(), checkfirst=True)
