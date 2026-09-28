from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

from ...reconciliation.domain.enums import BankTransactionStatus, ReconciliationStatus


class ReconciliationCreate(BaseModel):
    bank_account_id: str
    name: str
    period_start: date
    period_end: date
    currency: str = "USD"


class ReconciliationOut(BaseModel):
    id: str
    org_id: str
    bank_account_id: str
    name: str
    period_start: date
    period_end: date
    currency: str
    status: ReconciliationStatus
    created_by: str
    created_at: datetime
    submitted_by: Optional[str]
    submitted_at: Optional[datetime]
    approved_by: Optional[str]
    approved_at: Optional[datetime]
    rejected_by: Optional[str]
    rejected_at: Optional[datetime]
    rejection_reason: Optional[str]
    supersedes_reconciliation_id: Optional[str]
    evidence_ref: Optional[str]

    model_config = {"from_attributes": True}


class BankTransactionRowIn(BaseModel):
    transaction_date: date
    description: str
    debit_amount: Decimal = Decimal("0.00")
    credit_amount: Decimal = Decimal("0.00")
    value_date: Optional[date] = None
    external_ref: Optional[str] = None
    currency: str = "USD"

    @model_validator(mode="after")
    def one_side_only(self):
        if (self.debit_amount > 0) == (self.credit_amount > 0):
            raise ValueError(
                "exactly one of debit_amount / credit_amount must be greater than zero"
            )
        return self


class ImportTransactionsRequest(BaseModel):
    rows: List[BankTransactionRowIn] = Field(..., min_length=1)
    import_source: str


class BankTransactionOut(BaseModel):
    id: str
    org_id: str
    reconciliation_id: str
    bank_account_id: str
    import_batch_id: str
    transaction_date: date
    value_date: Optional[date]
    description: str
    debit_amount: Decimal
    credit_amount: Decimal
    currency: str
    external_ref: Optional[str]
    status: BankTransactionStatus
    matched_journal_id: Optional[str]
    match_reason: Optional[str]
    match_rule: Optional[str]
    match_history: list
    created_by: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ManualMatchRequest(BaseModel):
    journal_id: str
    note: Optional[str] = None


class RejectMatchRequest(BaseModel):
    reason: str


class RejectReconciliationRequest(BaseModel):
    reason: str


class AttachEvidenceRequest(BaseModel):
    evidence_id: str
