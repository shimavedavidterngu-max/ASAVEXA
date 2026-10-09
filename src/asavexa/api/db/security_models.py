"""One table for every security feature (MFA state, session facts, audit-chain links, blobs' metadata, holds, alerts, vendors ...).
Created at application start-up like the other late tables (see api/main.py), not through schema.sql / Alembic."""
from datetime import datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, get_engine


class SecurityDocORM(Base):
    __tablename__ = "security_docs"

    kind: Mapped[str] = mapped_column(String, primary_key=True)
    key: Mapped[str] = mapped_column(String, primary_key=True)
    org_id: Mapped[str | None] = mapped_column(String, nullable=True)     # an organisation id, or the audit-chain scope 'GLOBAL' (not a foreign key)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (Index("ix_security_docs_kind_org", "kind", "org_id"),)


def ensure_security_tables() -> None:
    SecurityDocORM.__table__.create(bind=get_engine(), checkfirst=True)
