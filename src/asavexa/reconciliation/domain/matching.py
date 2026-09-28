"""
Deterministic reconciliation matching — explainable rules, not opaque
AI, per this module's build brief: "start with explainable rules...
never silently auto-match ambiguous transactions."

Ledger candidates are plain dicts, exactly the shape
`AccountingEngine.get_ledger()` already returns — this module never
imports Accounting's `Journal` type, only reads that one documented,
read-only interface (see services/service.py).
"""
from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal
from typing import Iterable, List, Set

from .models import BankTransaction, MatchCandidate, MatchDecision
from .enums import MatchOutcome

DEFAULT_DATE_TOLERANCE_DAYS = 3
TWO_PLACES = Decimal("0.01")

# Stable, machine-checkable rule codes — never just a free-text sentence.
# A match must always carry one of these (or None, when no decision was
# reached), so "why was this matched" is a code you can query on, not
# prose you have to parse.
MATCH_RULE_EXACT_AMOUNT_AND_DATE = "EXACT_AMOUNT_AND_DATE_WITHIN_TOLERANCE"
MATCH_RULE_MANUAL_OVERRIDE = "MANUAL_OVERRIDE"


def compute_dedup_hash(
    org_id: str,
    bank_account_id: str,
    external_ref: str | None,
    transaction_date: date,
    debit_amount: Decimal,
    credit_amount: Decimal,
    description: str,
) -> str:
    """
    Stable fingerprint used to prevent accidental duplicate imports.
    Includes `external_ref` when the source provides one (the strongest
    signal) but still produces a stable hash without it, using date +
    amount + description — the same "always compute something concrete,
    never skip the check" discipline as Evidence's file-hash dedup.
    """
    payload = "|".join([
        org_id, bank_account_id, external_ref or "",
        transaction_date.isoformat(),
        str(debit_amount.quantize(TWO_PLACES)), str(credit_amount.quantize(TWO_PLACES)),
        description.strip().lower(),
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def find_candidates(
    transaction: BankTransaction,
    ledger_entries: Iterable[dict],
    exclude_journal_ids: Set[str],
    date_tolerance_days: int = DEFAULT_DATE_TOLERANCE_DAYS,
) -> List[MatchCandidate]:
    """
    A ledger entry is a candidate only if it shows the *exact same*
    debit/credit shape on this account (the bank statement and the
    ledger describing the same real-world movement must agree on
    amount and direction — this is not a "roughly similar" heuristic)
    and falls within `date_tolerance_days` of the statement date, and
    is not already claimed by another transaction's accepted match.
    """
    txn_debit = transaction.debit_amount.quantize(TWO_PLACES)
    txn_credit = transaction.credit_amount.quantize(TWO_PLACES)

    candidates: List[MatchCandidate] = []
    for entry in ledger_entries:
        if entry["journal_id"] in exclude_journal_ids:
            continue
        if entry["debit"].quantize(TWO_PLACES) != txn_debit:
            continue
        if entry["credit"].quantize(TWO_PLACES) != txn_credit:
            continue
        date_diff = abs((entry["date"] - transaction.transaction_date).days)
        if date_diff > date_tolerance_days:
            continue
        candidates.append(MatchCandidate(
            journal_id=entry["journal_id"], journal_number=entry["journal_number"],
            date=entry["date"], description=entry["description"],
            debit_amount=entry["debit"], credit_amount=entry["credit"],
            date_diff_days=date_diff,
        ))

    candidates.sort(key=lambda c: c.date_diff_days)
    return candidates


def decide_match(transaction: BankTransaction, candidates: List[MatchCandidate]) -> MatchDecision:
    """
    The only place a matching decision is made. Every branch produces a
    human-readable `reason` — this is what "prove the match" means at
    the code level, not just a status flip.
    """
    if len(candidates) == 0:
        return MatchDecision(
            outcome=MatchOutcome.NO_CANDIDATE,
            reason=(
                f"No posted ledger entry on this account matches "
                f"debit={transaction.debit_amount} credit={transaction.credit_amount} "
                f"within the configured date tolerance of {transaction.transaction_date}."
            ),
        )
    if len(candidates) == 1:
        c = candidates[0]
        return MatchDecision(
            outcome=MatchOutcome.UNIQUE_CANDIDATE,
            matched_journal_id=c.journal_id,
            match_rule=MATCH_RULE_EXACT_AMOUNT_AND_DATE,
            reason=(
                f"Unique candidate: journal {c.journal_number} dated {c.date} "
                f"(debit={c.debit_amount}, credit={c.credit_amount}), "
                f"{c.date_diff_days} day(s) from the statement date — "
                f"exact amount match, no other candidate in range."
            ),
            candidates=candidates,
        )
    return MatchDecision(
        outcome=MatchOutcome.AMBIGUOUS,
        reason=(
            f"{len(candidates)} posted ledger entries match this amount within "
            f"the date tolerance — cannot auto-select one. Candidates: "
            + ", ".join(f"{c.journal_number} ({c.date})" for c in candidates)
        ),
        candidates=candidates,
    )
