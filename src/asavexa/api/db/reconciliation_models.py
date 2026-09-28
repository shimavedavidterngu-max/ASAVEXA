"""SQLAlchemy ORM models for Reconciliation — mirrors schema.sql and
reconciliation/repository/sqlite_repository.py's SCHEMA. No ForeignKey
to journals, for the same decoupling reason as evidence_records."""
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class ReconciliationORM(Base):
    __tablename__ = "reconciliations"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("organisations.id"))
    bank_account_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("accounts.id"))
    name: Mapped[str] = mapped_column(String, nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="DRAFT")
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    submitted_by: Mapped[str | None] = mapped_column(String, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_by: Mapped[str | None] = mapped_column(String, nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    supersedes_reconciliation_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    evidence_ref: Mapped[str | None] = mapped_column(String, nullable=True)


class BankTransactionORM(Base):
    __tablename__ = "bank_transactions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("organisations.id"))
    reconciliation_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("reconciliations.id"))
    bank_account_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("accounts.id"))
    import_batch_id: Mapped[str] = mapped_column(String, nullable=False)
    dedup_hash: Mapped[str] = mapped_column(String, nullable=False)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    value_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    debit_amount: Mapped[Numeric] = mapped_column(Numeric(18, 2), default=0)
    credit_amount: Mapped[Numeric] = mapped_column(Numeric(18, 2), default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    external_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="IMPORTED")
    matched_journal_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    match_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    match_rule: Mapped[str | None] = mapped_column(String, nullable=True)
    match_history: Mapped[list] = mapped_column(JSONB, default=list)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
