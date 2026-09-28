"""
Automated tests for Financial Reporting.

Run with:  PYTHONPATH=src python3 -m unittest discover -s tests -v

Stdlib-only — exercises ReportingService against a real, SQLite-backed
AccountingEngine (not a mock), reading through its actual public
interface (accounts, periods, get_ledger, get_trial_balance).
"""
import unittest
from datetime import date
from decimal import Decimal

from asavexa.accounting.domain.enums import AccountType
from asavexa.accounting.repository.sqlite_repository import (
    SqliteAccountRepository,
    SqliteJournalRepository,
    SqlitePeriodRepository,
)
from asavexa.accounting.services.engine import AccountingEngine, LineInput
from asavexa.audit.sqlite_repository import SqliteAuditRepository
from asavexa.bootstrap import create_sqlite_connection
from asavexa.reporting.domain.enums import ReportType
from asavexa.reporting.domain.errors import (
    ReportingAccountNotFoundError,
    ReportingPeriodNotFoundError,
    UnknownReportTypeError,
)
from asavexa.reporting.services.service import ReportingService

ORG_A = "org-meridian"
ORG_B = "org-other-tenant"


class ReportingServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.conn = create_sqlite_connection(":memory:")
        audit = SqliteAuditRepository(self.conn)
        self.audit = audit

        self.accounting = AccountingEngine(
            accounts=SqliteAccountRepository(self.conn),
            periods=SqlitePeriodRepository(self.conn),
            journals=SqliteJournalRepository(self.conn),
            audit=audit,
        )
        self.reporting = ReportingService(accounting=self.accounting, audit=audit)

        # A reasonably complete chart of accounts for Org A: one of each type.
        self.cash = self.accounting.create_account(ORG_A, "1000", "Cash", AccountType.ASSET, actor="setup")
        self.loan_payable = self.accounting.create_account(ORG_A, "2000", "Loan Payable", AccountType.LIABILITY, actor="setup")
        self.equity = self.accounting.create_account(ORG_A, "3000", "Owner's Capital", AccountType.EQUITY, actor="setup")
        self.revenue = self.accounting.create_account(ORG_A, "4000", "Sales Revenue", AccountType.REVENUE, actor="setup")
        self.expense = self.accounting.create_account(ORG_A, "5000", "Rent Expense", AccountType.EXPENSE, actor="setup")
        self.period = self.accounting.open_period(ORG_A, "FY2026-M01", date(2026, 1, 1), date(2026, 1, 31), actor="setup")

        # Org B: a completely separate tenant with its own accounts/period.
        self.cash_b = self.accounting.create_account(ORG_B, "1000", "Cash", AccountType.ASSET, actor="setup")
        self.period_b = self.accounting.open_period(ORG_B, "FY2026-M01", date(2026, 1, 1), date(2026, 1, 31), actor="setup")

    def _post(self, org_id, lines, txn_date, desc):
        journal = self.accounting.create_draft_journal(org_id, txn_date, desc, "USD", lines, created_by="dara")
        return self.accounting.post_journal(org_id, journal.id, actor="dara")

    # ------------------------------------------------------------------
    # Trial Balance
    # ------------------------------------------------------------------
    def test_trial_balance_generation_and_debit_credit_equality(self):
        self._post(
            ORG_A,
            [LineInput(self.cash.id, debit_amount=Decimal("1000.00")), LineInput(self.equity.id, credit_amount=Decimal("1000.00"))],
            date(2026, 1, 2), "Owner investment",
        )
        report = self.reporting.get_trial_balance(ORG_A, self.period.id, actor="dara")
        self.assertEqual(report.total_debits, Decimal("1000.00"))
        self.assertEqual(report.total_credits, Decimal("1000.00"))
        self.assertTrue(report.is_balanced)
        codes = {l.account_code for l in report.lines}
        self.assertEqual(codes, {"1000", "3000"})

    def test_trial_balance_lines_carry_account_metadata(self):
        self._post(
            ORG_A,
            [LineInput(self.cash.id, debit_amount=Decimal("500.00")), LineInput(self.revenue.id, credit_amount=Decimal("500.00"))],
            date(2026, 1, 5), "Sale",
        )
        report = self.reporting.get_trial_balance(ORG_A, self.period.id, actor="dara")
        cash_line = next(l for l in report.lines if l.account_id == self.cash.id)
        self.assertEqual(cash_line.account_code, "1000")
        self.assertEqual(cash_line.account_name, "Cash")
        self.assertEqual(cash_line.account_type, AccountType.ASSET)
        self.assertEqual(cash_line.debit_total, Decimal("500.00"))

    def test_trial_balance_unknown_period_raises(self):
        with self.assertRaises(ReportingPeriodNotFoundError):
            self.reporting.get_trial_balance(ORG_A, "not-a-real-period", actor="dara")

    def test_trial_balance_empty_period_returns_zero_report_not_error(self):
        report = self.reporting.get_trial_balance(ORG_A, self.period.id, actor="dara")
        self.assertEqual(report.lines, [])
        self.assertEqual(report.total_debits, Decimal("0.00"))
        self.assertTrue(report.is_balanced)  # 0 == 0 is honestly balanced

    # ------------------------------------------------------------------
    # Income Statement
    # ------------------------------------------------------------------
    def test_income_statement_generation_and_net_income(self):
        self._post(
            ORG_A,
            [LineInput(self.cash.id, debit_amount=Decimal("1000.00")), LineInput(self.revenue.id, credit_amount=Decimal("1000.00"))],
            date(2026, 1, 5), "Sale",
        )
        self._post(
            ORG_A,
            [LineInput(self.expense.id, debit_amount=Decimal("300.00")), LineInput(self.cash.id, credit_amount=Decimal("300.00"))],
            date(2026, 1, 6), "Rent",
        )
        report = self.reporting.get_income_statement(ORG_A, self.period.id, actor="dara")
        self.assertEqual(report.total_revenue, Decimal("1000.00"))
        self.assertEqual(report.total_expenses, Decimal("300.00"))
        self.assertEqual(report.net_income, Decimal("700.00"))
        self.assertEqual(len(report.revenue_lines), 1)
        self.assertEqual(len(report.expense_lines), 1)

    def test_income_statement_excludes_balance_sheet_accounts(self):
        self._post(
            ORG_A,
            [LineInput(self.cash.id, debit_amount=Decimal("1000.00")), LineInput(self.equity.id, credit_amount=Decimal("1000.00"))],
            date(2026, 1, 2), "Investment",
        )
        report = self.reporting.get_income_statement(ORG_A, self.period.id, actor="dara")
        self.assertEqual(report.revenue_lines, [])
        self.assertEqual(report.expense_lines, [])
        self.assertEqual(report.net_income, Decimal("0.00"))

    def test_revenue_classification_uses_credit_normal_balance(self):
        self._post(
            ORG_A,
            [LineInput(self.cash.id, debit_amount=Decimal("250.00")), LineInput(self.revenue.id, credit_amount=Decimal("250.00"))],
            date(2026, 1, 5), "Sale",
        )
        report = self.reporting.get_income_statement(ORG_A, self.period.id, actor="dara")
        self.assertEqual(report.revenue_lines[0].amount, Decimal("250.00"))  # credit - debit = positive

    def test_expense_classification_uses_debit_normal_balance(self):
        self._post(
            ORG_A,
            [LineInput(self.expense.id, debit_amount=Decimal("80.00")), LineInput(self.cash.id, credit_amount=Decimal("80.00"))],
            date(2026, 1, 6), "Supplies",
        )
        report = self.reporting.get_income_statement(ORG_A, self.period.id, actor="dara")
        self.assertEqual(report.expense_lines[0].amount, Decimal("80.00"))  # debit - credit = positive

    # ------------------------------------------------------------------
    # Balance Sheet
    # ------------------------------------------------------------------
    def test_balance_sheet_holds_with_pure_capital_and_loan_activity(self):
        self._post(
            ORG_A,
            [LineInput(self.cash.id, debit_amount=Decimal("1000.00")), LineInput(self.equity.id, credit_amount=Decimal("1000.00"))],
            date(2026, 1, 2), "Owner investment",
        )
        self._post(
            ORG_A,
            [LineInput(self.cash.id, debit_amount=Decimal("500.00")), LineInput(self.loan_payable.id, credit_amount=Decimal("500.00"))],
            date(2026, 1, 3), "Bank loan",
        )
        report = self.reporting.get_balance_sheet(ORG_A, self.period.id, actor="dara")
        self.assertEqual(report.total_assets, Decimal("1500.00"))
        self.assertEqual(report.total_liabilities, Decimal("500.00"))
        self.assertEqual(report.total_equity, Decimal("1000.00"))
        self.assertTrue(report.accounting_equation_holds)
        self.assertEqual(report.imbalance_amount, Decimal("0.00"))

    def test_balance_sheet_imbalance_equals_unclosed_net_income(self):
        """With no period-close/retained-earnings automation in this
        starter engine, unclosed revenue/expense activity shows up
        honestly as an imbalance — and that imbalance exactly equals
        the period's net income, which is mathematically expected, not
        a defect."""
        self._post(
            ORG_A,
            [LineInput(self.cash.id, debit_amount=Decimal("1000.00")), LineInput(self.equity.id, credit_amount=Decimal("1000.00"))],
            date(2026, 1, 2), "Owner investment",
        )
        self._post(
            ORG_A,
            [LineInput(self.cash.id, debit_amount=Decimal("400.00")), LineInput(self.revenue.id, credit_amount=Decimal("400.00"))],
            date(2026, 1, 5), "Sale",
        )
        self._post(
            ORG_A,
            [LineInput(self.expense.id, debit_amount=Decimal("150.00")), LineInput(self.cash.id, credit_amount=Decimal("150.00"))],
            date(2026, 1, 6), "Rent",
        )
        balance_sheet = self.reporting.get_balance_sheet(ORG_A, self.period.id, actor="dara")
        income_statement = self.reporting.get_income_statement(ORG_A, self.period.id, actor="dara")
        self.assertFalse(balance_sheet.accounting_equation_holds)
        self.assertEqual(balance_sheet.imbalance_amount, income_statement.net_income)

    def test_asset_liability_equity_classification_signs(self):
        self._post(
            ORG_A,
            [LineInput(self.cash.id, debit_amount=Decimal("1000.00")), LineInput(self.equity.id, credit_amount=Decimal("1000.00"))],
            date(2026, 1, 2), "Investment",
        )
        report = self.reporting.get_balance_sheet(ORG_A, self.period.id, actor="dara")
        self.assertEqual(report.asset_lines[0].amount, Decimal("1000.00"))
        self.assertEqual(report.equity_lines[0].amount, Decimal("1000.00"))
        self.assertEqual(report.liability_lines, [])

    def test_balance_sheet_unknown_period_raises(self):
        with self.assertRaises(ReportingPeriodNotFoundError):
            self.reporting.get_balance_sheet(ORG_A, "nonexistent", actor="dara")

    # ------------------------------------------------------------------
    # General Ledger / traceability
    # ------------------------------------------------------------------
    def test_general_ledger_generation_multiple_accounts(self):
        self._post(
            ORG_A,
            [LineInput(self.cash.id, debit_amount=Decimal("1000.00")), LineInput(self.equity.id, credit_amount=Decimal("1000.00"))],
            date(2026, 1, 2), "Investment",
        )
        self._post(
            ORG_A,
            [LineInput(self.cash.id, debit_amount=Decimal("500.00")), LineInput(self.revenue.id, credit_amount=Decimal("500.00"))],
            date(2026, 1, 5), "Sale",
        )
        report = self.reporting.get_general_ledger(ORG_A, actor="dara", period_id=self.period.id)
        cash_section = next(s for s in report.accounts if s.account_id == self.cash.id)
        self.assertEqual(len(cash_section.entries), 2)
        self.assertEqual(cash_section.closing_balance, Decimal("1500.00"))

    def test_general_ledger_unknown_account_id_raises(self):
        with self.assertRaises(ReportingAccountNotFoundError):
            self.reporting.get_general_ledger(ORG_A, actor="dara", account_ids=["not-a-real-account"])

    def test_trace_line_returns_exact_ledger_entries_with_journal_reference(self):
        journal = self._post(
            ORG_A,
            [LineInput(self.cash.id, debit_amount=Decimal("500.00")), LineInput(self.revenue.id, credit_amount=Decimal("500.00"))],
            date(2026, 1, 5), "Sale to Kadena Ltd",
        )
        entries = self.reporting.trace_line(ORG_A, self.cash.id, period_id=self.period.id)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["journal_id"], journal.id)
        self.assertEqual(entries[0]["journal_number"], journal.journal_number)

    def test_trace_line_unknown_account_raises(self):
        with self.assertRaises(ReportingAccountNotFoundError):
            self.reporting.trace_line(ORG_A, "not-a-real-account")

    # ------------------------------------------------------------------
    # Deterministic dispatcher
    # ------------------------------------------------------------------
    def test_generate_dispatches_to_the_right_report(self):
        self._post(
            ORG_A,
            [LineInput(self.cash.id, debit_amount=Decimal("100.00")), LineInput(self.revenue.id, credit_amount=Decimal("100.00"))],
            date(2026, 1, 5), "Sale",
        )
        from asavexa.reporting.domain.models import IncomeStatementReport
        report = self.reporting.generate(ReportType.INCOME_STATEMENT, ORG_A, self.period.id, actor="dara")
        self.assertIsInstance(report, IncomeStatementReport)

    def test_generate_unknown_type_raises(self):
        with self.assertRaises(UnknownReportTypeError):
            self.reporting.generate("NOT_A_REAL_TYPE", ORG_A, self.period.id, actor="dara")

    def test_repeated_generation_is_deterministic(self):
        self._post(
            ORG_A,
            [LineInput(self.cash.id, debit_amount=Decimal("321.00")), LineInput(self.revenue.id, credit_amount=Decimal("321.00"))],
            date(2026, 1, 5), "Sale",
        )
        first = self.reporting.get_trial_balance(ORG_A, self.period.id, actor="dara")
        second = self.reporting.get_trial_balance(ORG_A, self.period.id, actor="controller")
        self.assertEqual(first.total_debits, second.total_debits)
        self.assertEqual(first.total_credits, second.total_credits)
        self.assertEqual(
            [(l.account_id, l.debit_total, l.credit_total) for l in first.lines],
            [(l.account_id, l.debit_total, l.credit_total) for l in second.lines],
        )

    # ------------------------------------------------------------------
    # Tenant isolation
    # ------------------------------------------------------------------
    def test_organisation_b_cannot_see_organisation_a_trial_balance(self):
        self._post(
            ORG_A,
            [LineInput(self.cash.id, debit_amount=Decimal("999.00")), LineInput(self.revenue.id, credit_amount=Decimal("999.00"))],
            date(2026, 1, 5), "Sale",
        )
        # Org B's own period id is different — using Org A's period id
        # under Org B must not resolve to Org A's data.
        with self.assertRaises(ReportingPeriodNotFoundError):
            self.reporting.get_trial_balance(ORG_B, self.period.id, actor="intruder")

    def test_organisation_b_general_ledger_does_not_include_organisation_a_accounts(self):
        self._post(
            ORG_A,
            [LineInput(self.cash.id, debit_amount=Decimal("999.00")), LineInput(self.revenue.id, credit_amount=Decimal("999.00"))],
            date(2026, 1, 5), "Sale",
        )
        report = self.reporting.get_general_ledger(ORG_B, actor="intruder", period_id=self.period_b.id)
        account_ids = {s.account_id for s in report.accounts}
        self.assertNotIn(self.cash.id, account_ids)
        self.assertIn(self.cash_b.id, account_ids)

    def test_organisation_b_cannot_trace_organisation_a_account(self):
        with self.assertRaises(ReportingAccountNotFoundError):
            self.reporting.trace_line(ORG_B, self.cash.id)

    # ------------------------------------------------------------------
    # Audit trail
    # ------------------------------------------------------------------
    def test_report_generation_is_audit_logged(self):
        self.reporting.get_trial_balance(ORG_A, self.period.id, actor="dara")
        events = self.audit.list_for_org(ORG_A)
        generated = [e for e in events if e.action == "REPORT_GENERATED"]
        self.assertEqual(len(generated), 1)
        self.assertEqual(generated[0].actor, "dara")
        self.assertEqual(generated[0].new_value["report_type"], "TRIAL_BALANCE")

    def test_failed_generation_is_audit_logged_and_still_raises(self):
        with self.assertRaises(ReportingPeriodNotFoundError):
            self.reporting.get_trial_balance(ORG_A, "bogus-period", actor="dara")
        events = self.audit.list_for_org(ORG_A)
        failed = [e for e in events if e.action == "REPORT_GENERATION_FAILED"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0].actor, "dara")

    # ------------------------------------------------------------------
    # Accounting Engine is untouched
    # ------------------------------------------------------------------
    def test_accounting_engine_state_is_unchanged_by_report_generation(self):
        journal = self._post(
            ORG_A,
            [LineInput(self.cash.id, debit_amount=Decimal("500.00")), LineInput(self.revenue.id, credit_amount=Decimal("500.00"))],
            date(2026, 1, 5), "Sale",
        )
        tb_before = self.accounting.get_trial_balance(ORG_A, self.period.id)

        self.reporting.get_trial_balance(ORG_A, self.period.id, actor="dara")
        self.reporting.get_income_statement(ORG_A, self.period.id, actor="dara")
        self.reporting.get_balance_sheet(ORG_A, self.period.id, actor="dara")
        self.reporting.get_general_ledger(ORG_A, actor="dara", period_id=self.period.id)
        self.reporting.trace_line(ORG_A, self.cash.id, period_id=self.period.id)

        tb_after = self.accounting.get_trial_balance(ORG_A, self.period.id)
        self.assertEqual(tb_before, tb_after)
        reloaded = self.accounting.journals.get(ORG_A, journal.id)
        self.assertEqual(reloaded.status, journal.status)
        self.assertEqual(reloaded.total_debits(), journal.total_debits())


if __name__ == "__main__":
    unittest.main()
