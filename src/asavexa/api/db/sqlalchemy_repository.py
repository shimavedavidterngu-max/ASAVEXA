"""
PostgreSQL/SQLAlchemy implementation of the accounting repositories.

Implements the exact same Protocols as
accounting/repository/sqlite_repository.py (see
accounting/repository/interfaces.py). AccountingEngine is constructed
identically either way:

    # tests / local dev
    engine = AccountingEngine(SqliteAccountRepository(conn), ...)

    # production
    engine = AccountingEngine(SqlAlchemyAccountRepository(session), ...)

Not executed in the sandbox that produced this starter codebase — see
api/__init__.py for why, and tests/test_accounting_engine.py for the
proof that the underlying engine logic is correct against the SQLite
adapter.

NOTE: the audit repository used to live in this file. It has been
promoted to api/db/audit_sqlalchemy_repository.py (shared by every
module's adapter) alongside the domain-layer promotion in asavexa/audit/.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...accounting.domain.enums import AccountType, JournalStatus, PeriodStatus
from ...accounting.domain.models import (
    Account,
    AccountingPeriod,
    Journal,
    JournalLine,
)
from .models import (
    AccountORM,
    AccountingPeriodORM,
    JournalLineORM,
    JournalORM,
)


def _account_to_domain(row: AccountORM) -> Account:
    return Account(
        id=row.id, org_id=row.org_id, code=row.code, name=row.name,
        type=AccountType(row.type), currency=row.currency,
        parent_id=row.parent_id, is_active=row.is_active, created_at=row.created_at,
    )


def _period_to_domain(row: AccountingPeriodORM) -> AccountingPeriod:
    return AccountingPeriod(
        id=row.id, org_id=row.org_id, name=row.name,
        start_date=row.start_date, end_date=row.end_date,
        status=PeriodStatus(row.status), locked_at=row.locked_at, locked_by=row.locked_by,
    )


def _journal_to_domain(row: JournalORM) -> Journal:
    return Journal(
        id=row.id, org_id=row.org_id, period_id=row.period_id,
        journal_number=row.journal_number, date=row.date,
        description=row.description, currency=row.currency,
        created_by=row.created_by, created_at=row.created_at,
        lines=[
            JournalLine(
                id=l.id, journal_id=l.journal_id, line_no=l.line_no,
                account_id=l.account_id,
                debit_amount=Decimal(l.debit_amount), credit_amount=Decimal(l.credit_amount),
                description=l.description,
            )
            for l in row.lines
        ],
        status=JournalStatus(row.status), posted_by=row.posted_by, posted_at=row.posted_at,
        reversal_of_journal_id=row.reversal_of_journal_id,
        reversed_by_journal_id=row.reversed_by_journal_id,
        transaction_ref=row.transaction_ref, evidence_ref=row.evidence_ref,
    )


class SqlAlchemyAccountRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, account: Account) -> Account:
        row = AccountORM(
            id=account.id, org_id=account.org_id, code=account.code,
            name=account.name, type=account.type.value, currency=account.currency,
            parent_id=account.parent_id, is_active=account.is_active,
            created_at=account.created_at,
        )
        self.session.add(row)
        return account

    def get(self, org_id: str, account_id: str) -> Optional[Account]:
        row = self.session.get(AccountORM, account_id)
        if row is None or row.org_id != org_id:
            return None
        return _account_to_domain(row)

    def get_by_code(self, org_id: str, code: str) -> Optional[Account]:
        row = self.session.scalar(
            select(AccountORM).where(AccountORM.org_id == org_id, AccountORM.code == code)
        )
        return _account_to_domain(row) if row else None

    def list_for_org(self, org_id: str) -> List[Account]:
        rows = self.session.scalars(
            select(AccountORM).where(AccountORM.org_id == org_id).order_by(AccountORM.code)
        ).all()
        return [_account_to_domain(r) for r in rows]


class SqlAlchemyPeriodRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, period: AccountingPeriod) -> AccountingPeriod:
        row = AccountingPeriodORM(
            id=period.id, org_id=period.org_id, name=period.name,
            start_date=period.start_date, end_date=period.end_date,
            status=period.status.value, locked_at=period.locked_at, locked_by=period.locked_by,
        )
        self.session.add(row)
        return period

    def get(self, org_id: str, period_id: str) -> Optional[AccountingPeriod]:
        row = self.session.get(AccountingPeriodORM, period_id)
        if row is None or row.org_id != org_id:
            return None
        return _period_to_domain(row)

    def get_for_date(self, org_id: str, on_date: date) -> Optional[AccountingPeriod]:
        row = self.session.scalar(
            select(AccountingPeriodORM)
            .where(
                AccountingPeriodORM.org_id == org_id,
                AccountingPeriodORM.start_date <= on_date,
                AccountingPeriodORM.end_date >= on_date,
            )
            .order_by(AccountingPeriodORM.start_date.desc())
        )
        return _period_to_domain(row) if row else None

    def update(self, period: AccountingPeriod) -> AccountingPeriod:
        row = self.session.get(AccountingPeriodORM, period.id)
        row.status = period.status.value
        row.locked_at = period.locked_at
        row.locked_by = period.locked_by
        return period

    def list_for_org(self, org_id: str) -> List[AccountingPeriod]:
        rows = self.session.scalars(
            select(AccountingPeriodORM)
            .where(AccountingPeriodORM.org_id == org_id)
            .order_by(AccountingPeriodORM.start_date)
        ).all()
        return [_period_to_domain(r) for r in rows]


class SqlAlchemyJournalRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, journal: Journal) -> Journal:
        row = JournalORM(
            id=journal.id, org_id=journal.org_id, period_id=journal.period_id,
            journal_number=journal.journal_number, date=journal.date,
            description=journal.description, currency=journal.currency,
            status=journal.status.value, created_by=journal.created_by,
            created_at=journal.created_at, posted_by=journal.posted_by,
            posted_at=journal.posted_at,
            reversal_of_journal_id=journal.reversal_of_journal_id,
            reversed_by_journal_id=journal.reversed_by_journal_id,
            transaction_ref=journal.transaction_ref, evidence_ref=journal.evidence_ref,
            lines=[
                JournalLineORM(
                    id=l.id, line_no=l.line_no, account_id=l.account_id,
                    debit_amount=l.debit_amount, credit_amount=l.credit_amount,
                    description=l.description,
                )
                for l in journal.lines
            ],
        )
        self.session.add(row)
        return journal

    def get(self, org_id: str, journal_id: str) -> Optional[Journal]:
        row = self.session.get(JournalORM, journal_id)
        if row is None or row.org_id != org_id:
            return None
        return _journal_to_domain(row)

    def update(self, journal: Journal) -> Journal:
        """Status/metadata transitions only — see the note in the SQLite
        equivalent (evidence_ref/transaction_ref persistence fixed
        alongside it for the same reason). Line immutability is enforced
        in services/engine.py."""
        row = self.session.get(JournalORM, journal.id)
        row.status = journal.status.value
        row.posted_by = journal.posted_by
        row.posted_at = journal.posted_at
        row.reversal_of_journal_id = journal.reversal_of_journal_id
        row.reversed_by_journal_id = journal.reversed_by_journal_id
        row.description = journal.description
        row.evidence_ref = journal.evidence_ref
        row.transaction_ref = journal.transaction_ref
        return journal

    def list_for_org(
        self, org_id, period_id=None, account_id=None, status=None
    ) -> List[Journal]:
        query = select(JournalORM).where(JournalORM.org_id == org_id)
        if period_id:
            query = query.where(JournalORM.period_id == period_id)
        if status:
            query = query.where(JournalORM.status == status)
        if account_id:
            query = query.join(JournalLineORM).where(JournalLineORM.account_id == account_id)
        query = query.order_by(JournalORM.date, JournalORM.journal_number).distinct()
        rows = self.session.scalars(query).unique().all()
        return [_journal_to_domain(r) for r in rows]

    def next_journal_number(self, org_id: str) -> str:
        count = self.session.scalar(
            select(JournalORM).where(JournalORM.org_id == org_id)
        )
        n = len(self.session.scalars(select(JournalORM).where(JournalORM.org_id == org_id)).all())
        return f"JRN-{n + 1:06d}"
