"""
Pure invariant checks for the Asavexa Accounting Engine.

These functions have no side effects and no dependency on storage. They
exist so the non-negotiable rules from the ASAVEXA Master Blueprint are
enforced in exactly one place, and are trivially unit-testable in
isolation. The service layer (services/engine.py) calls these before
every state change.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from .enums import PeriodStatus, JournalStatus
from .errors import (
    EmptyJournalError,
    UnbalancedJournalError,
    InvalidLineAmountError,
    CurrencyMismatchError,
    PeriodLockedError,
    ImmutableJournalError,
    InvalidJournalStateError,
)

TWO_PLACES = Decimal("0.01")


def assert_valid_line_amounts(lines) -> None:
    """
    Each line must have exactly one of debit/credit non-zero, and neither
    amount may be negative. A "negative debit" or "negative credit" is a
    disguised entry on the other side of the ledger and is rejected —
    require the caller to state which side the amount belongs on.
    """
    for line in lines:
        debit, credit = line.debit_amount, line.credit_amount
        if debit < 0 or credit < 0:
            raise InvalidLineAmountError(
                f"Line {line.line_no}: amounts must not be negative "
                f"(debit={debit}, credit={credit})."
            )
        if (debit > 0) == (credit > 0):
            raise InvalidLineAmountError(
                f"Line {line.line_no}: exactly one of debit_amount / "
                f"credit_amount must be greater than zero "
                f"(debit={debit}, credit={credit})."
            )


def assert_not_empty(lines) -> None:
    """A journal needs at least two lines to be a valid double entry."""
    if len(list(lines)) < 2:
        raise EmptyJournalError("A journal must contain at least two lines.")


def assert_single_currency(lines, journal_currency: str) -> None:
    """
    v1 scope decision: a journal's lines all settle in the journal's
    stated currency. Cross-currency journals need a sourced FX rate,
    which this engine will not fabricate (Blueprint: "never invent ...
    financial figures"). Multi-currency conversion is a documented
    future extension, not a silent assumption.
    """
    for line in lines:
        line_currency = getattr(line, "currency", journal_currency)
        if line_currency != journal_currency:
            raise CurrencyMismatchError(
                f"Line {line.line_no} currency {line_currency!r} does not "
                f"match journal currency {journal_currency!r}."
            )


def assert_balanced(lines) -> None:
    """
    Rule: "Debits must equal credits for every balanced journal."
    Compared to the currency's minor unit (2 decimal places) using
    Decimal, never float.
    """
    total_debits = sum((l.debit_amount for l in lines), Decimal("0.00"))
    total_credits = sum((l.credit_amount for l in lines), Decimal("0.00"))
    if total_debits.quantize(TWO_PLACES) != total_credits.quantize(TWO_PLACES):
        raise UnbalancedJournalError(
            f"Journal is not balanced: total debits={total_debits}, "
            f"total credits={total_credits}."
        )


def assert_period_open_for_posting(period) -> None:
    """
    Rule: "Financial periods can be locked." No journal may be posted or
    reversed with a date inside a period that is LOCKED or CLOSED.
    """
    if period.status != PeriodStatus.OPEN:
        raise PeriodLockedError(
            f"Period {period.name!r} is {period.status.value} — no "
            f"journals may be posted or reversed against it."
        )


def assert_journal_editable(journal) -> None:
    """
    Rule: "Posted journal entries are immutable." Only DRAFT journals may
    be edited or deleted.
    """
    if journal.status != JournalStatus.DRAFT:
        raise ImmutableJournalError(
            f"Journal {journal.journal_number} is {journal.status.value} "
            f"and cannot be edited or deleted. Use a reversal instead."
        )


def assert_journal_postable(journal) -> None:
    if journal.status != JournalStatus.DRAFT:
        raise InvalidJournalStateError(
            f"Journal {journal.journal_number} is {journal.status.value}; "
            f"only a DRAFT journal can be posted."
        )


def assert_journal_reversible(journal) -> None:
    if journal.status != JournalStatus.POSTED:
        raise InvalidJournalStateError(
            f"Journal {journal.journal_number} is {journal.status.value}; "
            f"only a POSTED journal can be reversed."
        )


def validate_new_journal(lines, journal_currency: str) -> None:
    """Convenience wrapper running every structural check for a new
    (not-yet-saved) journal, in a sensible order."""
    assert_not_empty(lines)
    assert_valid_line_amounts(lines)
    assert_single_currency(lines, journal_currency)
    assert_balanced(lines)
