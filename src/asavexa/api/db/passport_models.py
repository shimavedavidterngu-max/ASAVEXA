"""
ORM model for the organisation's ownership structure (owners and
subsidiaries), the two Passport identity facts ASAVEXA has no other
source for. Created at application start-up like organisation_profiles
(see api/main.py), not through schema.sql / Alembic.
"""
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String
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


class PassportShareORM(Base):
    """A permissioned share of the Passport: who, what, when, how, plus the
    frozen snapshot the recipient may see. Secrets are stored only as hashes."""
    __tablename__ = "passport_shares"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    org_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("organisations.id"), index=True)
    recipient_name: Mapped[str] = mapped_column(String, nullable=False)
    recipient_type: Mapped[str] = mapped_column(String, nullable=False)
    recipient_email: Mapped[str | None] = mapped_column(String, nullable=True)
    purpose: Mapped[str | None] = mapped_column(String, nullable=True)
    scopes: Mapped[list] = mapped_column(JSONB, nullable=False)
    include_detail: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allow_download: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    closed_periods_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    date_from: Mapped[date] = mapped_column(Date, nullable=False)
    date_to: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    secret_hash: Mapped[str] = mapped_column(String, nullable=False)
    code_salt: Mapped[str] = mapped_column(String, nullable=False)
    code_hash: Mapped[str] = mapped_column(String, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False)      # copy of snapshot["share"], cheap to list
    fingerprint: Mapped[str] = mapped_column(String, nullable=False)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    access_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by: Mapped[str | None] = mapped_column(String, nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(String, nullable=True)


class PassportShareSessionORM(Base):
    """A recipient who has passed verification. Only the token's hash is stored."""
    __tablename__ = "passport_share_sessions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    share_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("passport_shares.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def ensure_share_tables() -> None:
    """Idempotent: creates the two sharing tables if they do not exist."""
    PassportShareORM.__table__.create(bind=get_engine(), checkfirst=True)
    PassportShareSessionORM.__table__.create(bind=get_engine(), checkfirst=True)
