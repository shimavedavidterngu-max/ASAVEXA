"""
PostgreSQL/SQLAlchemy implementation of the Reconciliation repositories.
Implements the exact same Protocols as
reconciliation/repository/sqlite_repository.py. Not executed in the
sandbox that produced this starter codebase — see api/__init__.py.
"""
from __future__ import annotations

from decimal import Decimal
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...reconciliation.domain.enums import BankTransactionStatus, ReconciliationStatus
from ...reconciliation.domain.models import BankTransaction, Reconciliation
from .reconciliation_models import BankTransactionORM, ReconciliationORM


def _recon_to_domain(row: ReconciliationORM) -> Reconciliation:
    return Reconciliation(
        id=row.id, org_id=row.org_id, bank_account_id=row.bank_account_id, name=row.name,
        period_start=row.period_start, period_end=row.period_end, currency=row.currency,
        created_by=row.created_by, created_at=row.created_at, status=ReconciliationStatus(row.status),
        submitted_by=row.submitted_by, submitted_at=row.submitted_at,
        approved_by=row.approved_by, approved_at=row.approved_at,
        rejected_by=row.rejected_by, rejected_at=row.rejected_at, rejection_reason=row.rejection_reason,
        supersedes_reconciliation_id=row.supersedes_reconciliation_id, evidence_ref=row.evidence_ref,
    )


def _txn_to_domain(row: BankTransactionORM) -> BankTransaction:
    return BankTransaction(
        id=row.id, org_id=row.org_id, reconciliation_id=row.reconciliation_id,
        bank_account_id=row.bank_account_id, import_batch_id=row.import_batch_id,
        dedup_hash=row.dedup_hash, transaction_date=row.transaction_date, value_date=row.value_date,
        description=row.description, debit_amount=Decimal(row.debit_amount),
        credit_amount=Decimal(row.credit_amount), currency=row.currency, external_ref=row.external_ref,
        status=BankTransactionStatus(row.status), matched_journal_id=row.matched_journal_id,
        match_reason=row.match_reason, match_rule=row.match_rule,
        match_history=row.match_history or [], created_by=row.created_by, created_at=row.created_at,
    )


class SqlAlchemyReconciliationRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, reconciliation: Reconciliation) -> Reconciliation:
        r = reconciliation
        row = ReconciliationORM(
            id=r.id, org_id=r.org_id, bank_account_id=r.bank_account_id, name=r.name,
            period_start=r.period_start, period_end=r.period_end, currency=r.currency,
            status=r.status.value, created_by=r.created_by, created_at=r.created_at,
            supersedes_reconciliation_id=r.supersedes_reconciliation_id, evidence_ref=r.evidence_ref,
        )
        self.session.add(row)
        return reconciliation

    def get(self, org_id: str, reconciliation_id: str) -> Optional[Reconciliation]:
        row = self.session.get(ReconciliationORM, reconciliation_id)
        if row is None or row.org_id != org_id:
            return None
        return _recon_to_domain(row)

    def update(self, reconciliation: Reconciliation) -> Reconciliation:
        r = reconciliation
        row = self.session.get(ReconciliationORM, r.id)
        row.status = r.status.value
        row.submitted_by = r.submitted_by
        row.submitted_at = r.submitted_at
        row.approved_by = r.approved_by
        row.approved_at = r.approved_at
        row.rejected_by = r.rejected_by
        row.rejected_at = r.rejected_at
        row.rejection_reason = r.rejection_reason
        row.evidence_ref = r.evidence_ref
        return reconciliation

    def list_for_org(
        self, org_id: str, bank_account_id: Optional[str] = None, status: Optional[str] = None
    ) -> List[Reconciliation]:
        query = select(ReconciliationORM).where(ReconciliationORM.org_id == org_id)
        if bank_account_id:
            query = query.where(ReconciliationORM.bank_account_id == bank_account_id)
        if status:
            query = query.where(ReconciliationORM.status == status)
        rows = self.session.scalars(query.order_by(ReconciliationORM.created_at)).all()
        return [_recon_to_domain(r) for r in rows]


class SqlAlchemyBankTransactionRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, transaction: BankTransaction) -> BankTransaction:
        t = transaction
        row = BankTransactionORM(
            id=t.id, org_id=t.org_id, reconciliation_id=t.reconciliation_id,
            bank_account_id=t.bank_account_id, import_batch_id=t.import_batch_id,
            dedup_hash=t.dedup_hash, transaction_date=t.transaction_date, value_date=t.value_date,
            description=t.description, debit_amount=t.debit_amount, credit_amount=t.credit_amount,
            currency=t.currency, external_ref=t.external_ref, status=t.status.value,
            matched_journal_id=t.matched_journal_id, match_reason=t.match_reason,
            match_rule=t.match_rule, match_history=t.match_history, created_by=t.created_by,
            created_at=t.created_at,
        )
        self.session.add(row)
        return transaction

    def get(self, org_id: str, transaction_id: str) -> Optional[BankTransaction]:
        row = self.session.get(BankTransactionORM, transaction_id)
        if row is None or row.org_id != org_id:
            return None
        return _txn_to_domain(row)

    def update(self, transaction: BankTransaction) -> BankTransaction:
        t = transaction
        row = self.session.get(BankTransactionORM, t.id)
        row.status = t.status.value
        row.matched_journal_id = t.matched_journal_id
        row.match_reason = t.match_reason
        row.match_rule = t.match_rule
        row.match_history = t.match_history
        row.reconciliation_id = t.reconciliation_id
        return transaction

    def list_for_reconciliation(self, org_id: str, reconciliation_id: str) -> List[BankTransaction]:
        rows = self.session.scalars(
            select(BankTransactionORM)
            .where(BankTransactionORM.org_id == org_id, BankTransactionORM.reconciliation_id == reconciliation_id)
            .order_by(BankTransactionORM.transaction_date)
        ).all()
        return [_txn_to_domain(r) for r in rows]

    def list_for_account(self, org_id: str, bank_account_id: str) -> List[BankTransaction]:
        rows = self.session.scalars(
            select(BankTransactionORM)
            .where(BankTransactionORM.org_id == org_id, BankTransactionORM.bank_account_id == bank_account_id)
            .order_by(BankTransactionORM.transaction_date)
        ).all()
        return [_txn_to_domain(r) for r in rows]

    def get_by_dedup_hash(self, org_id: str, bank_account_id: str, dedup_hash: str) -> Optional[BankTransaction]:
        row = self.session.scalar(
            select(BankTransactionORM).where(
                BankTransactionORM.org_id == org_id,
                BankTransactionORM.bank_account_id == bank_account_id,
                BankTransactionORM.dedup_hash == dedup_hash,
            )
        )
        return _txn_to_domain(row) if row else None
