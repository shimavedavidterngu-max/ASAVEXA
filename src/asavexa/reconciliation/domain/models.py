"""
Domain models for Reconciliation.

Plain dataclasses, no framework dependency, same discipline as every
other module. Deliberately holds no reference to Accounting's `Journal`,
Evidence's `EvidenceRecord`, or Identity's `User`/`Role` types — only
opaque string ids (`bank_account_id`, `matched_journal_id`,
`evidence_ref`), exactly like `Journal.evidence_ref` /
`EvidenceRecord.linked_journal_id` connect Accounting and Evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from .enums import BankTransactionStatus, MatchOutcome, ReconciliationStatus


@dataclass
class Reconciliation:
    """
    The review/approval batch — a maker prepares it against one bank
    account for one statement period, a checker approves or rejects it.
    Never edited back to DRAFT once SUBMITTED; rework means creating a
    new Reconciliation (see `supersedes_reconciliation_id`) — the same
    "never silently reopen, always create a new traceable record"
    philosophy the Accounting Engine uses for corrections.
    """
    id: str
    org_id: str
    bank_account_id: str
    name: str
    period_start: date
    period_end: date
    currency: str
    created_by: str
    created_at: datetime
    status: ReconciliationStatus = ReconciliationStatus.DRAFT
    submitted_by: Optional[str] = None
    submitted_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    rejected_by: Optional[str] = None
    rejected_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    supersedes_reconciliation_id: Optional[str] = None
    # Pointer to a bank-statement/support document in the Evidence
    # Vault — an opaque id, exactly like Journal.evidence_ref. This
    # module never inspects evidence content or status itself.
    evidence_ref: Optional[str] = None


@dataclass
class BankTransaction:
    """
    One imported external (bank) transaction. Never a journal entry —
    it only ever *points at* one via `matched_journal_id` once matched.

    Exactly one of debit_amount / credit_amount is non-zero, mirroring
    accounting's JournalLine convention: a bank debit/credit here means
    the bank statement shows this account being debited/credited by
    this amount, which a correct matching ledger line must mirror
    exactly on the same account.
    """
    id: str
    org_id: str
    reconciliation_id: str
    bank_account_id: str
    import_batch_id: str
    dedup_hash: str
    transaction_date: date
    description: str
    debit_amount: Decimal
    credit_amount: Decimal
    currency: str
    created_by: str
    created_at: datetime
    value_date: Optional[date] = None
    external_ref: Optional[str] = None
    status: BankTransactionStatus = BankTransactionStatus.IMPORTED
    matched_journal_id: Optional[str] = None
    match_reason: Optional[str] = None
    # A stable, machine-checkable code for *why* — never just a free-text
    # sentence. See domain/matching.py's MATCH_RULE_* constants. This is
    # what makes a match provable rather than merely labeled "Matched".
    match_rule: Optional[str] = None
    # Every matching decision ever made for this transaction, oldest
    # first — never overwritten, only appended to. Belt-and-suspenders
    # alongside the shared audit trail: this is the fast, in-record
    # trace; audit/ is the cross-entity, queryable one.
    match_history: List[dict] = field(default_factory=list)


@dataclass
class MatchCandidate:
    """A posted ledger line that could explain a bank transaction. Not
    persisted — produced fresh by matching.find_candidates on each run."""
    journal_id: str
    journal_number: str
    date: date
    description: str
    debit_amount: Decimal
    credit_amount: Decimal
    date_diff_days: int


@dataclass
class MatchDecision:
    """The deterministic, explainable output of matching.decide_match —
    never a silent guess. `reason` is always populated and is what gets
    written to BankTransaction.match_reason and the audit trail."""
    outcome: MatchOutcome
    reason: str
    matched_journal_id: Optional[str] = None
    match_rule: Optional[str] = None
    candidates: List[MatchCandidate] = field(default_factory=list)


@dataclass
class BankTransactionInput:
    """Plain input shape for importing one row, mirroring
    accounting.services.engine.LineInput's role for journal lines."""
    transaction_date: date
    description: str
    debit_amount: Decimal = Decimal("0.00")
    credit_amount: Decimal = Decimal("0.00")
    value_date: Optional[date] = None
    external_ref: Optional[str] = None
    currency: str = "USD"
