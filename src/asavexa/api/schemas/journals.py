from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

from ...accounting.domain.enums import JournalStatus


class JournalLineIn(BaseModel):
    account_id: str
    debit_amount: Decimal = Decimal("0.00")
    credit_amount: Decimal = Decimal("0.00")
    description: str = ""

    @model_validator(mode="after")
    def one_side_only(self):
        if (self.debit_amount > 0) == (self.credit_amount > 0):
            raise ValueError(
                "exactly one of debit_amount / credit_amount must be greater than zero"
            )
        return self


class JournalCreate(BaseModel):
    date: date
    description: str
    currency: str = "USD"
    lines: List[JournalLineIn] = Field(..., min_length=2)
    transaction_ref: Optional[str] = None
    evidence_ref: Optional[str] = None


class JournalLineOut(BaseModel):
    id: str
    line_no: int
    account_id: str
    debit_amount: Decimal
    credit_amount: Decimal
    description: str

    model_config = {"from_attributes": True}


class JournalOut(BaseModel):
    id: str
    org_id: str
    period_id: str
    journal_number: str
    date: date
    description: str
    currency: str
    status: JournalStatus
    created_by: str
    created_at: datetime
    posted_by: Optional[str]
    posted_at: Optional[datetime]
    reversal_of_journal_id: Optional[str]
    reversed_by_journal_id: Optional[str]
    transaction_ref: Optional[str]
    evidence_ref: Optional[str]
    lines: List[JournalLineOut]


class ReverseJournalRequest(BaseModel):
    reason: str
