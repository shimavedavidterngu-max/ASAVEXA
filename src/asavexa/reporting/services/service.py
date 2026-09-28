"""
ReportingService — the public service facade for Financial Reporting.

Reads the Accounting Engine through its existing public interface
(`accounting.accounts`, `accounting.periods`, `accounting.get_ledger`,
`accounting.get_trial_balance`) and writes to it NEVER — no method here
creates, updates, or deletes anything in the Accounting Engine. Every
report is computed fresh on every call; nothing is cached or persisted
by this module (see the package README's "Architecture" section for
why there is no reporting/repository/ package at all).

Optionally reads Reconciliation's transaction repository (read-only,
for `get_reconciliation_summary`) and never reads Evidence or Identity
directly — evidence provenance comes for free because
`AccountingEngine.get_ledger()` already includes each line's
`evidence_ref`/`transaction_ref`, and permission checks are the API
layer's job, exactly like every other module's service layer.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from ...accounting.domain.enums import AccountType
from ...accounting.domain.models import Account
from ...accounting.services.engine import AccountingEngine
from ...audit.models import AuditEvent
from ...audit.repository import AuditRepository
from ..domain import rules as reporting_rules
from ..domain.enums import AuditAction, ReportType
from ..domain.errors import (
    ReconciliationNotConfiguredError,
    ReportingAccountNotFoundError,
    ReportingPeriodNotFoundError,
    UnknownReportTypeError,
)
from ..domain.models import (
    BalanceSheetReport,
    GeneralLedgerAccountSection,
    GeneralLedgerReport,
    IncomeStatementReport,
    ReconciliationSummary,
    StatementLine,
    TrialBalanceLine,
    TrialBalanceReport,
)

TWO_PLACES = Decimal("0.01")


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ReportingService:
    def __init__(
        self,
        accounting: AccountingEngine,
        audit: AuditRepository,
        reconciliation: Optional["object"] = None,
    ):
        self.accounting = accounting
        self.audit = audit
        # Typed as a forward-reference-free `object` above to avoid a
        # hard import dependency on the Reconciliation module from this
        # module's constructor signature — the actual type expected is
        # reconciliation.services.service.ReconciliationService, and
        # only its public `.transactions` repository attribute is ever
        # touched (see get_reconciliation_summary).
        self.reconciliation = reconciliation

    # ------------------------------------------------------------------
    def _get_period(self, org_id: str, period_id: str):
        period = self.accounting.periods.get(org_id, period_id)
        if period is None:
            raise ReportingPeriodNotFoundError(
                f"No accounting period {period_id} found for organisation {org_id}."
            )
        return period

    def _account_lookup(self, org_id: str) -> dict[str, Account]:
        return {a.id: a for a in self.accounting.accounts.list_for_org(org_id)}

    def _log(
        self, org_id: str, action: AuditAction, actor: str, report_type: ReportType,
        entity_id: str, new_value: Optional[dict] = None, reason: Optional[str] = None,
    ) -> None:
        self.audit.record(
            AuditEvent(
                id=_new_id(), org_id=org_id, entity_type="Report", entity_id=entity_id,
                action=action.value, actor=actor, timestamp=_now(),
                new_value={"report_type": report_type.value, **(new_value or {})}, reason=reason,
            )
        )

    # ------------------------------------------------------------------
    # Trial Balance
    # ------------------------------------------------------------------
    def get_trial_balance(self, org_id: str, period_id: str, actor: str) -> TrialBalanceReport:
        try:
            self._get_period(org_id, period_id)
            raw = self.accounting.get_trial_balance(org_id, period_id)
            accounts = self._account_lookup(org_id)

            lines = [
                TrialBalanceLine(
                    account_id=account_id,
                    account_code=accounts[account_id].code if account_id in accounts else "?",
                    account_name=accounts[account_id].name if account_id in accounts else "(unknown account)",
                    account_type=accounts[account_id].type if account_id in accounts else AccountType.ASSET,
                    debit_total=totals["debit_total"], credit_total=totals["credit_total"],
                )
                for account_id, totals in raw["accounts"].items()
            ]
            lines.sort(key=lambda l: l.account_code)

            report = TrialBalanceReport(
                org_id=org_id, period_id=period_id, generated_at=_now(), generated_by=actor,
                lines=lines, total_debits=raw["total_debits"], total_credits=raw["total_credits"],
                is_balanced=raw["is_balanced"],
            )
        except Exception as exc:
            self._log(org_id, AuditAction.REPORT_GENERATION_FAILED, actor, ReportType.TRIAL_BALANCE,
                       period_id, reason=str(exc))
            raise
        self._log(
            org_id, AuditAction.REPORT_GENERATED, actor, ReportType.TRIAL_BALANCE, period_id,
            new_value={
                "period_id": period_id, "total_debits": str(report.total_debits),
                "total_credits": str(report.total_credits), "is_balanced": report.is_balanced,
                "line_count": len(report.lines),
            },
        )
        return report

    # ------------------------------------------------------------------
    # Income Statement
    # ------------------------------------------------------------------
    def get_income_statement(self, org_id: str, period_id: str, actor: str) -> IncomeStatementReport:
        try:
            self._get_period(org_id, period_id)
            raw = self.accounting.get_trial_balance(org_id, period_id)
            accounts = self._account_lookup(org_id)

            revenue_lines: List[StatementLine] = []
            expense_lines: List[StatementLine] = []
            for account_id, totals in raw["accounts"].items():
                account = accounts.get(account_id)
                if account is None or not reporting_rules.is_income_statement_type(account.type):
                    continue
                amount = reporting_rules.normal_balance_amount(
                    account.type, totals["debit_total"], totals["credit_total"]
                )
                line = StatementLine(
                    account_id=account_id, account_code=account.code, account_name=account.name,
                    account_type=account.type, amount=amount,
                )
                (revenue_lines if account.type == AccountType.REVENUE else expense_lines).append(line)

            revenue_lines.sort(key=lambda l: l.account_code)
            expense_lines.sort(key=lambda l: l.account_code)
            total_revenue = sum((l.amount for l in revenue_lines), Decimal("0.00"))
            total_expenses = sum((l.amount for l in expense_lines), Decimal("0.00"))

            report = IncomeStatementReport(
                org_id=org_id, period_id=period_id, generated_at=_now(), generated_by=actor,
                revenue_lines=revenue_lines, expense_lines=expense_lines,
                total_revenue=total_revenue, total_expenses=total_expenses,
                net_income=total_revenue - total_expenses,
            )
        except Exception as exc:
            self._log(org_id, AuditAction.REPORT_GENERATION_FAILED, actor, ReportType.INCOME_STATEMENT,
                       period_id, reason=str(exc))
            raise
        self._log(
            org_id, AuditAction.REPORT_GENERATED, actor, ReportType.INCOME_STATEMENT, period_id,
            new_value={
                "period_id": period_id, "total_revenue": str(report.total_revenue),
                "total_expenses": str(report.total_expenses), "net_income": str(report.net_income),
            },
        )
        return report

    # ------------------------------------------------------------------
    # Balance Sheet
    # ------------------------------------------------------------------
    def get_balance_sheet(self, org_id: str, period_id: str, actor: str) -> BalanceSheetReport:
        try:
            self._get_period(org_id, period_id)
            raw = self.accounting.get_trial_balance(org_id, period_id)
            accounts = self._account_lookup(org_id)

            asset_lines: List[StatementLine] = []
            liability_lines: List[StatementLine] = []
            equity_lines: List[StatementLine] = []
            for account_id, totals in raw["accounts"].items():
                account = accounts.get(account_id)
                if account is None or not reporting_rules.is_balance_sheet_type(account.type):
                    continue
                amount = reporting_rules.normal_balance_amount(
                    account.type, totals["debit_total"], totals["credit_total"]
                )
                line = StatementLine(
                    account_id=account_id, account_code=account.code, account_name=account.name,
                    account_type=account.type, amount=amount,
                )
                if account.type == AccountType.ASSET:
                    asset_lines.append(line)
                elif account.type == AccountType.LIABILITY:
                    liability_lines.append(line)
                else:
                    equity_lines.append(line)

            for bucket in (asset_lines, liability_lines, equity_lines):
                bucket.sort(key=lambda l: l.account_code)

            total_assets = sum((l.amount for l in asset_lines), Decimal("0.00"))
            total_liabilities = sum((l.amount for l in liability_lines), Decimal("0.00"))
            total_equity = sum((l.amount for l in equity_lines), Decimal("0.00"))
            imbalance = (total_assets - (total_liabilities + total_equity)).quantize(TWO_PLACES)

            report = BalanceSheetReport(
                org_id=org_id, period_id=period_id, generated_at=_now(), generated_by=actor,
                asset_lines=asset_lines, liability_lines=liability_lines, equity_lines=equity_lines,
                total_assets=total_assets, total_liabilities=total_liabilities, total_equity=total_equity,
                accounting_equation_holds=(imbalance == Decimal("0.00")), imbalance_amount=imbalance,
            )
        except Exception as exc:
            self._log(org_id, AuditAction.REPORT_GENERATION_FAILED, actor, ReportType.BALANCE_SHEET,
                       period_id, reason=str(exc))
            raise
        self._log(
            org_id, AuditAction.REPORT_GENERATED, actor, ReportType.BALANCE_SHEET, period_id,
            new_value={
                "period_id": period_id, "total_assets": str(report.total_assets),
                "total_liabilities": str(report.total_liabilities), "total_equity": str(report.total_equity),
                "accounting_equation_holds": report.accounting_equation_holds,
            },
        )
        return report

    # ------------------------------------------------------------------
    # General Ledger
    # ------------------------------------------------------------------
    def get_general_ledger(
        self, org_id: str, actor: str, period_id: Optional[str] = None,
        account_ids: Optional[List[str]] = None,
    ) -> GeneralLedgerReport:
        entity_id = period_id or "all-periods"
        try:
            if period_id is not None:
                self._get_period(org_id, period_id)
            accounts = self._account_lookup(org_id)
            selected_ids = account_ids if account_ids is not None else list(accounts.keys())

            sections: List[GeneralLedgerAccountSection] = []
            for account_id in selected_ids:
                account = accounts.get(account_id)
                if account is None:
                    raise ReportingAccountNotFoundError(
                        f"Account {account_id} not found for organisation {org_id}."
                    )
                entries = self.accounting.get_ledger(org_id, account_id, period_id=period_id)
                closing = entries[-1]["running_balance"] if entries else Decimal("0.00")
                sections.append(GeneralLedgerAccountSection(
                    account_id=account_id, account_code=account.code, account_name=account.name,
                    account_type=account.type, entries=entries, closing_balance=closing,
                ))
            sections.sort(key=lambda s: s.account_code)

            report = GeneralLedgerReport(
                org_id=org_id, period_id=period_id, generated_at=_now(), generated_by=actor,
                accounts=sections,
            )
        except Exception as exc:
            self._log(org_id, AuditAction.REPORT_GENERATION_FAILED, actor, ReportType.GENERAL_LEDGER,
                       entity_id, reason=str(exc))
            raise
        self._log(
            org_id, AuditAction.REPORT_GENERATED, actor, ReportType.GENERAL_LEDGER, entity_id,
            new_value={"period_id": period_id, "account_count": len(report.accounts)},
        )
        return report

    # ------------------------------------------------------------------
    # Provenance drill-down
    # ------------------------------------------------------------------
    def trace_line(self, org_id: str, account_id: str, period_id: Optional[str] = None) -> List[dict]:
        """
        "Where did this number come from?" — the exact posted ledger
        entries (with each entry's journal_id, journal_number,
        evidence_ref, transaction_ref) behind one account's balance, for
        one period or all time. This is a thin, named wrapper over
        AccountingEngine.get_ledger — Reporting does not compute
        anything different here, it only gives the trace its own
        report-shaped entry point.
        """
        account = self.accounting.accounts.get(org_id, account_id)
        if account is None:
            raise ReportingAccountNotFoundError(f"Account {account_id} not found for organisation {org_id}.")
        if period_id is not None:
            self._get_period(org_id, period_id)
        return self.accounting.get_ledger(org_id, account_id, period_id=period_id)

    # ------------------------------------------------------------------
    # Generic dispatcher
    # ------------------------------------------------------------------
    def generate(self, report_type: ReportType, org_id: str, period_id: str, actor: str):
        if report_type == ReportType.TRIAL_BALANCE:
            return self.get_trial_balance(org_id, period_id, actor)
        if report_type == ReportType.INCOME_STATEMENT:
            return self.get_income_statement(org_id, period_id, actor)
        if report_type == ReportType.BALANCE_SHEET:
            return self.get_balance_sheet(org_id, period_id, actor)
        if report_type == ReportType.GENERAL_LEDGER:
            return self.get_general_ledger(org_id, actor, period_id=period_id)
        raise UnknownReportTypeError(f"Unknown report type: {report_type!r}")

    # ------------------------------------------------------------------
    # Optional, read-only Reconciliation enrichment
    # ------------------------------------------------------------------
    def get_reconciliation_summary(self, org_id: str, bank_account_id: str) -> ReconciliationSummary:
        """
        Purely informational control context — never changes any report
        figure. Requires this ReportingService to have been constructed
        with a ReconciliationService; the integration is optional and
        never assumed.
        """
        if self.reconciliation is None:
            raise ReconciliationNotConfiguredError(
                "This ReportingService was constructed without a ReconciliationService — "
                "reconciliation-status enrichment is unavailable."
            )
        # RECONCILED / APPROVED / MATCHED / REVIEW_REQUIRED / UNMATCHED /
        # REJECTED / IMPORTED are plain strings on the transaction's
        # .status.value — no import of reconciliation's enum module is
        # needed here, keeping this method's dependency surface minimal.
        transactions = self.reconciliation.transactions.list_for_account(org_id, bank_account_id)
        reconciled = sum(1 for t in transactions if t.status.value == "RECONCILED")
        exceptions = sum(1 for t in transactions if t.status.value in ("REVIEW_REQUIRED", "UNMATCHED"))
        outstanding = len(transactions) - reconciled - exceptions
        return ReconciliationSummary(
            bank_account_id=bank_account_id, reconciled_count=reconciled,
            outstanding_count=outstanding, exception_count=exceptions,
        )
