"""
ORM model for the organisation profile (legal name, registration and tax
numbers, address, contacts, base currency, fiscal-year start, reporting
framework).

Created by Alembic revision b7c1d2e3f4a5 (migrations/sql/), not at start-up.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class OrganisationProfileORM(Base):
    __tablename__ = "organisation_profiles"

    org_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("organisations.id"), primary_key=True)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_by: Mapped[str] = mapped_column(String, nullable=False)

