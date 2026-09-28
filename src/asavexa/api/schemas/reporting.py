from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel

from ...accounting.domain.enums import AccountType


class TrialBalanceLineOut(BaseModel):
    account_id: str
    account_code: str
    account_name: str
    account_type: AccountType
    debit_total: Decimal
    credit_total: Decimal


class TrialBalanceOut(BaseModel):
    org_id: str
    period_id: str
    generated_at: datetime
    generated_by: str
    lines: List[TrialBalanceLineOut]
    total_debits: Decimal
    total_credits: Decimal
    is_balanced: bool


class StatementLineOut(BaseModel):
    account_id: str
    account_code: str
    account_name: str
    account_type: AccountType
    amount: Decimal


class IncomeStatementOut(BaseModel):
    org_id: str
    period_id: str
    generated_at: datetime
    generated_by: str
    revenue_lines: List[StatementLineOut]
    expense_lines: List[StatementLineOut]
    total_revenue: Decimal
    total_expenses: Decimal
    net_income: Decimal


class BalanceSheetOut(BaseModel):
    org_id: str
    period_id: str
    generated_at: datetime
    generated_by: str
    asset_lines: List[StatementLineOut]
    liability_lines: List[StatementLineOut]
    equity_lines: List[StatementLineOut]
    total_assets: Decimal
    total_liabilities: Decimal
    total_equity: Decimal
    accounting_equation_holds: bool
    imbalance_amount: Decimal


class GeneralLedgerAccountSectionOut(BaseModel):
    account_id: str
    account_code: str
    account_name: str
    account_type: AccountType
    entries: List[dict]
    closing_balance: Decimal


class GeneralLedgerOut(BaseModel):
    org_id: str
    period_id: Optional[str]
    generated_at: datetime
    generated_by: str
    accounts: List[GeneralLedgerAccountSectionOut]


class ReconciliationSummaryOut(BaseModel):
    bank_account_id: str
    reconciled_count: int
    outstanding_count: int
    exception_count: int
