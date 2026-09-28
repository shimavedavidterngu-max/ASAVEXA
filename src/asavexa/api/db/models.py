"""
SQLAlchemy ORM models — the PostgreSQL-backed mirror of
schema.sql and the domain dataclasses in
accounting/domain/models.py.

These are storage models only. They deliberately do not contain any
business rules (balance checks, immutability, period locks) — those
live exactly once, in accounting/domain/rules.py and
accounting/services/engine.py, and must not be duplicated here.

NOTE: `Organisation` and `AuditEventORM` used to live here but have been
promoted to api/db/identity_models.py and api/db/audit_models.py
respectively, alongside the domain-layer promotion of the same classes
(see asavexa/audit/ and asavexa/identity/). All ORM classes share one
`Base` (api/db/base.py), so `Base.metadata.create_all()` still creates
every table regardless of which file defines it.
"""
import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class AccountORM(Base):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("org_id", "code"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("organisations.id"))
    code: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    parent_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("accounts.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class AccountingPeriodORM(Base):
    __tablename__ = "accounting_periods"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("organisations.id"))
    name: Mapped[str] = mapped_column(String, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String, default="OPEN")
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String, nullable=True)


class JournalORM(Base):
    __tablename__ = "journals"
    __table_args__ = (UniqueConstraint("org_id", "journal_number"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("organisations.id"))
    period_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("accounting_periods.id"))
    journal_number: Mapped[str] = mapped_column(String, nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String, default="DRAFT")
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    posted_by: Mapped[str | None] = mapped_column(String, nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reversal_of_journal_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("journals.id"), nullable=True)
    reversed_by_journal_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("journals.id"), nullable=True)
    transaction_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    evidence_ref: Mapped[str | None] = mapped_column(String, nullable=True)

    lines: Mapped[list["JournalLineORM"]] = relationship(
        back_populates="journal", order_by="JournalLineORM.line_no", cascade="all, delete-orphan"
    )


class JournalLineORM(Base):
    __tablename__ = "journal_lines"
    __table_args__ = (
        UniqueConstraint("journal_id", "line_no"),
        CheckConstraint("(debit_amount = 0) OR (credit_amount = 0)", name="one_sided_line"),
        CheckConstraint("(debit_amount > 0) OR (credit_amount > 0)", name="non_zero_line"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    journal_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("journals.id"))
    line_no: Mapped[int] = mapped_column(nullable=False)
    account_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("accounts.id"))
    debit_amount: Mapped[Numeric] = mapped_column(Numeric(18, 2), default=0)
    credit_amount: Mapped[Numeric] = mapped_column(Numeric(18, 2), default=0)
    description: Mapped[str] = mapped_column(Text, default="")

    journal: Mapped["JournalORM"] = relationship(back_populates="lines")
