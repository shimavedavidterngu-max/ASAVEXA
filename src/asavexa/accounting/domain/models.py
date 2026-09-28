"""
Domain models for the Asavexa Accounting Engine.

These are plain dataclasses with no dependency on any web framework or ORM.
This is deliberate (Blueprint Rule 19 — "keep concerns separated" / "no
module should unnecessarily control an unrelated domain"): the accounting
rules must be correct and testable on their own, independent of whether
they are eventually served over FastAPI and stored in Postgres or SQLite.

Money is always `decimal.Decimal`, never `float` — floating-point rounding
errors are not acceptable in a ledger.

NOTE: `Organisation` and `AuditEvent` used to live here but have been
promoted to their proper homes (`asavexa.identity.domain.models` and
`asavexa.audit.models` respectively) now that more than one module needs
them. Accounting still refers to organisations only by `org_id: str`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List

from .enums import AccountType, JournalStatus, PeriodStatus


@dataclass
class Account:
    """A single node in the chart of accounts."""
    id: str
    org_id: str
    code: str
    name: str
    type: AccountType
    currency: str = "USD"
    parent_id: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None


@dataclass
class AccountingPeriod:
    """A financial period that can be locked to prevent further posting."""
    id: str
    org_id: str
    name: str
    start_date: date
    end_date: date
    status: PeriodStatus = PeriodStatus.OPEN
    locked_at: Optional[datetime] = None
    locked_by: Optional[str] = None


@dataclass
class JournalLine:
    """
    One line of a journal entry.

    Exactly one of debit_amount / credit_amount must be non-zero. This is
    the standard general-ledger shape (supports journals with more than
    two lines) and still satisfies the blueprint's "debit account, credit
    account, amount" requirement at the journal level.
    """
    id: str
    journal_id: str
    line_no: int
    account_id: str
    debit_amount: Decimal
    credit_amount: Decimal
    description: str = ""


@dataclass
class Journal:
    """
    A journal entry header. Every posted transaction in Asavexa must
    produce exactly one Journal (Blueprint Rule: "every financial
    transaction must produce a traceable accounting record").
    """
    id: str
    org_id: str
    period_id: str
    journal_number: str
    date: date
    description: str
    currency: str
    created_by: str
    created_at: datetime
    lines: List[JournalLine] = field(default_factory=list)
    status: JournalStatus = JournalStatus.DRAFT
    posted_by: Optional[str] = None
    posted_at: Optional[datetime] = None
    reversal_of_journal_id: Optional[str] = None
    reversed_by_journal_id: Optional[str] = None
    # Evidence & source linkage — populated once the Evidence Vault module
    # exists. Kept here now so later modules integrate without a schema
    # migration on this table. See src/asavexa/evidence/README.md.
    transaction_ref: Optional[str] = None
    evidence_ref: Optional[str] = None

    def total_debits(self) -> Decimal:
        return sum((l.debit_amount for l in self.lines), Decimal("0.00"))

    def total_credits(self) -> Decimal:
        return sum((l.credit_amount for l in self.lines), Decimal("0.00"))
