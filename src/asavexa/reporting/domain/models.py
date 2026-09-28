"""
Domain models for Financial Reporting.

None of these are ever written to storage — there is no
reporting/repository/ package (see the module README for why). Every
instance here is constructed fresh, on the spot, from data read out of
the Accounting Engine, and handed back to the caller. The "provenance"
this module promises is: which account, which period, when it was
computed, and by whom asked — plus, for any individual number, a named
trace method (`ReportingService.trace_line`) that returns the exact
posted ledger entries behind it, sourced from
`AccountingEngine.get_ledger` — never a stored copy of that data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from ...accounting.domain.enums import AccountType


@dataclass
class TrialBalanceLine:
    account_id: str
    account_code: str
    account_name: str
    account_type: AccountType
    debit_total: Decimal
    credit_total: Decimal


@dataclass
class TrialBalanceReport:
    org_id: str
    period_id: str
    generated_at: datetime
    generated_by: str
    lines: List[TrialBalanceLine]
    total_debits: Decimal
    total_credits: Decimal
    is_balanced: bool


@dataclass
class StatementLine:
    """One account's contribution to an Income Statement or Balance
    Sheet, already converted to its normal-balance sign (see
    domain/rules.py::normal_balance_amount) — a positive `amount` always
    means "more of what this account normally represents", regardless
    of whether that took a debit or a credit total to get there."""
    account_id: str
    account_code: str
    account_name: str
    account_type: AccountType
    amount: Decimal


@dataclass
class IncomeStatementReport:
    org_id: str
    period_id: str
    generated_at: datetime
    generated_by: str
    revenue_lines: List[StatementLine]
    expense_lines: List[StatementLine]
    total_revenue: Decimal
    total_expenses: Decimal
    net_income: Decimal


@dataclass
class BalanceSheetReport:
    org_id: str
    period_id: str
    generated_at: datetime
    generated_by: str
    asset_lines: List[StatementLine]
    liability_lines: List[StatementLine]
    equity_lines: List[StatementLine]
    total_assets: Decimal
    total_liabilities: Decimal
    total_equity: Decimal
    # Never forced to True. When False, `imbalance_amount` is exposed
    # rather than hidden — see README: with no automated period-close,
    # this equals the period's net income until it is closed to equity,
    # which is an expected, honest fact about this starter engine, not
    # a defect in Reporting.
    accounting_equation_holds: bool
    imbalance_amount: Decimal


@dataclass
class GeneralLedgerAccountSection:
    account_id: str
    account_code: str
    account_name: str
    account_type: AccountType
    entries: List[dict]  # exactly AccountingEngine.get_ledger()'s own entry shape
    closing_balance: Decimal


@dataclass
class GeneralLedgerReport:
    org_id: str
    period_id: Optional[str]
    generated_at: datetime
    generated_by: str
    accounts: List[GeneralLedgerAccountSection] = field(default_factory=list)


@dataclass
class ReconciliationSummary:
    """Optional, read-only enrichment — see
    ReportingService.get_reconciliation_summary. Never affects any
    report figure; purely informational control context."""
    bank_account_id: str
    reconciled_count: int
    outstanding_count: int  # imported but not yet RECONCILED
    exception_count: int    # REVIEW_REQUIRED or UNMATCHED
