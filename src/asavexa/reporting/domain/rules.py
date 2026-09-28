"""
Pure calculation rules for Financial Reporting. No side effects, no
storage dependency — same discipline as every other module's
domain/rules.py.

These functions interpret the *raw* debit_total/credit_total figures
AccountingEngine.get_trial_balance() already computes. The Accounting
Engine itself imposes no normal-balance sign convention — it only
enforces that debits equal credits per journal. Turning "this account
had $500 more debits than credits" into "this asset increased by $500"
vs. "this revenue account decreased by $500" requires knowing the
account's classification, which is exactly Reporting's job, using the
standard double-entry convention (the one AccountType's five values
exist to support):

    ASSET, EXPENSE      -> normal debit balance   (amount = debit - credit)
    LIABILITY, EQUITY,
    REVENUE             -> normal credit balance  (amount = credit - debit)

This is not a "textbook formula imposed blindly" — it is the only
convention consistent with what AccountType's five values already mean
in accounting/domain/enums.py, so it fully preserves the Accounting
Engine's own account-sign design rather than inventing one.
"""
from __future__ import annotations

from decimal import Decimal

from ...accounting.domain.enums import AccountType
from .errors import UnsupportedAccountClassificationError

_DEBIT_NORMAL = frozenset({AccountType.ASSET, AccountType.EXPENSE})
_CREDIT_NORMAL = frozenset({AccountType.LIABILITY, AccountType.EQUITY, AccountType.REVENUE})


def normal_balance_amount(account_type: AccountType, debit_total: Decimal, credit_total: Decimal) -> Decimal:
    if account_type in _DEBIT_NORMAL:
        return debit_total - credit_total
    if account_type in _CREDIT_NORMAL:
        return credit_total - debit_total
    # Unreachable given AccountType's current five values — see
    # UnsupportedAccountClassificationError's docstring.
    raise UnsupportedAccountClassificationError(
        f"No normal-balance convention defined for account type {account_type!r}."
    )


def is_income_statement_type(account_type: AccountType) -> bool:
    return account_type in (AccountType.REVENUE, AccountType.EXPENSE)


def is_balance_sheet_type(account_type: AccountType) -> bool:
    return account_type in (AccountType.ASSET, AccountType.LIABILITY, AccountType.EQUITY)
