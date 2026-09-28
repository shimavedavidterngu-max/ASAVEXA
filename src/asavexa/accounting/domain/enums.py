"""
Enumerations for the Asavexa Accounting Engine.

Reference: ASAVEXA Master Blueprint, Section 7 (Non-Negotiable Development
Rules) and Section 8 (Engineering Skill Set — Accounting Engine).
"""
from enum import Enum


class AccountType(str, Enum):
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    REVENUE = "REVENUE"
    EXPENSE = "EXPENSE"


class JournalStatus(str, Enum):
    DRAFT = "DRAFT"       # editable, not yet part of the ledger
    POSTED = "POSTED"     # immutable, part of the ledger (Rule 6)
    REVERSED = "REVERSED"  # posted, then superseded by a reversal (Rule 6)


class PeriodStatus(str, Enum):
    OPEN = "OPEN"
    LOCKED = "LOCKED"     # no new postings dated within this period (Rule: period lock)
    CLOSED = "CLOSED"     # locked and formally closed out


class AuditAction(str, Enum):
    ACCOUNT_CREATED = "ACCOUNT_CREATED"
    PERIOD_OPENED = "PERIOD_OPENED"
    PERIOD_LOCKED = "PERIOD_LOCKED"
    JOURNAL_DRAFTED = "JOURNAL_DRAFTED"
    JOURNAL_DRAFT_UPDATED = "JOURNAL_DRAFT_UPDATED"
    JOURNAL_DRAFT_DELETED = "JOURNAL_DRAFT_DELETED"
    JOURNAL_POSTED = "JOURNAL_POSTED"
    JOURNAL_REVERSED = "JOURNAL_REVERSED"
