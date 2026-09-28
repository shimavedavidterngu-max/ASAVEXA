"""
Automated tests for the Asavexa Accounting Engine.

Run with:  python3 -m unittest discover -s tests -v
(from the project root, with src/ on PYTHONPATH — see tests/__init__.py
or run via `PYTHONPATH=src python3 -m unittest discover -s tests -v`)

These tests exercise the engine against the stdlib SQLite repository, so
they require no external dependencies and no network access — they are
the "evidence" behind the claim that the core accounting invariants
(balance, immutability, period locks, audit trail, reversal integrity)
actually hold, per the blueprint's Testing Rule: "critical accounting
functions must have automated tests before production release."
"""
import unittest
from datetime import date
from decimal import Decimal

from asavexa.accounting.domain.enums import AccountType, JournalStatus, PeriodStatus
from asavexa.accounting.domain.errors import (
    EmptyJournalError,
    ImmutableJournalError,
    InvalidJournalStateError,
    InvalidLineAmountError,
    PeriodLockedError,
    UnbalancedJournalError,
)
from asavexa.accounting.repository.sqlite_repository import (
    SqliteAccountRepository,
    SqliteJournalRepository,
    SqlitePeriodRepository,
)
from asavexa.accounting.services.engine import AccountingEngine, LineInput
from asavexa.audit.sqlite_repository import SqliteAuditRepository
from asavexa.bootstrap import create_sqlite_connection

ORG = "org-meridian"


class AccountingEngineTestCase(unittest.TestCase):
    def setUp(self):
        self.conn = create_sqlite_connection(":memory:")
        self.engine = AccountingEngine(
            accounts=SqliteAccountRepository(self.conn),
            periods=SqlitePeriodRepository(self.conn),
            journals=SqliteJournalRepository(self.conn),
            audit=SqliteAuditRepository(self.conn),
        )
        self.cash = self.engine.create_account(
            ORG, "1000", "Cash", AccountType.ASSET, actor="setup"
        )
        self.revenue = self.engine.create_account(
            ORG, "4000", "Revenue", AccountType.REVENUE, actor="setup"
        )
        self.period = self.engine.open_period(
            ORG, "FY2026-M01", date(2026, 1, 1), date(2026, 1, 31), actor="setup"
        )

    def tearDown(self):
        self.conn.close()

    # ------------------------------------------------------------------
    def test_balanced_journal_can_be_created_and_posted(self):
        journal = self.engine.create_draft_journal(
            ORG, date(2026, 1, 5), "Cash sale", "USD",
            [
                LineInput(self.cash.id, debit_amount=Decimal("100.00")),
                LineInput(self.revenue.id, credit_amount=Decimal("100.00")),
            ],
            created_by="dara",
        )
        self.assertEqual(journal.status, JournalStatus.DRAFT)
        posted = self.engine.post_journal(ORG, journal.id, actor="dara")
        self.assertEqual(posted.status, JournalStatus.POSTED)
        self.assertEqual(posted.total_debits(), Decimal("100.00"))
        self.assertEqual(posted.total_credits(), Decimal("100.00"))

    def test_unbalanced_journal_is_rejected(self):
        with self.assertRaises(UnbalancedJournalError):
            self.engine.create_draft_journal(
                ORG, date(2026, 1, 5), "Bad entry", "USD",
                [
                    LineInput(self.cash.id, debit_amount=Decimal("100.00")),
                    LineInput(self.revenue.id, credit_amount=Decimal("99.00")),
                ],
                created_by="dara",
            )

    def test_single_line_journal_is_rejected(self):
        with self.assertRaises(EmptyJournalError):
            self.engine.create_draft_journal(
                ORG, date(2026, 1, 5), "Bad entry", "USD",
                [LineInput(self.cash.id, debit_amount=Decimal("100.00"))],
                created_by="dara",
            )

    def test_line_with_both_debit_and_credit_is_rejected(self):
        with self.assertRaises(InvalidLineAmountError):
            self.engine.create_draft_journal(
                ORG, date(2026, 1, 5), "Bad entry", "USD",
                [
                    LineInput(self.cash.id, debit_amount=Decimal("10"), credit_amount=Decimal("10")),
                    LineInput(self.revenue.id, credit_amount=Decimal("0")),
                ],
                created_by="dara",
            )

    def test_negative_amount_is_rejected(self):
        with self.assertRaises(InvalidLineAmountError):
            self.engine.create_draft_journal(
                ORG, date(2026, 1, 5), "Bad entry", "USD",
                [
                    LineInput(self.cash.id, debit_amount=Decimal("-10.00")),
                    LineInput(self.revenue.id, credit_amount=Decimal("10.00")),
                ],
                created_by="dara",
            )

    # ------------------------------------------------------------------
    def test_cannot_post_into_a_locked_period(self):
        journal = self.engine.create_draft_journal(
            ORG, date(2026, 1, 5), "Cash sale", "USD",
            [
                LineInput(self.cash.id, debit_amount=Decimal("50.00")),
                LineInput(self.revenue.id, credit_amount=Decimal("50.00")),
            ],
            created_by="dara",
        )
        self.engine.lock_period(ORG, self.period.id, actor="controller", reason="month-end close")
        with self.assertRaises(PeriodLockedError):
            self.engine.post_journal(ORG, journal.id, actor="dara")

    def test_cannot_create_draft_in_a_period_with_no_configured_period(self):
        from asavexa.accounting.domain.errors import PeriodNotFoundError
        with self.assertRaises(PeriodNotFoundError):
            self.engine.create_draft_journal(
                ORG, date(2030, 1, 1), "No period covers this date", "USD",
                [
                    LineInput(self.cash.id, debit_amount=Decimal("1.00")),
                    LineInput(self.revenue.id, credit_amount=Decimal("1.00")),
                ],
                created_by="dara",
            )

    # ------------------------------------------------------------------
    def test_posted_journal_is_immutable(self):
        journal = self.engine.create_draft_journal(
            ORG, date(2026, 1, 5), "Cash sale", "USD",
            [
                LineInput(self.cash.id, debit_amount=Decimal("100.00")),
                LineInput(self.revenue.id, credit_amount=Decimal("100.00")),
            ],
            created_by="dara",
        )
        self.engine.post_journal(ORG, journal.id, actor="dara")
        with self.assertRaises(ImmutableJournalError):
            self.engine.update_draft_journal_description(ORG, journal.id, "sneaky edit", actor="dara")

    def test_cannot_post_the_same_journal_twice(self):
        journal = self.engine.create_draft_journal(
            ORG, date(2026, 1, 5), "Cash sale", "USD",
            [
                LineInput(self.cash.id, debit_amount=Decimal("100.00")),
                LineInput(self.revenue.id, credit_amount=Decimal("100.00")),
            ],
            created_by="dara",
        )
        self.engine.post_journal(ORG, journal.id, actor="dara")
        with self.assertRaises(InvalidJournalStateError):
            self.engine.post_journal(ORG, journal.id, actor="dara")

    # ------------------------------------------------------------------
    def test_reversal_creates_offsetting_journal_and_preserves_original(self):
        journal = self.engine.create_draft_journal(
            ORG, date(2026, 1, 5), "Cash sale (posted in error)", "USD",
            [
                LineInput(self.cash.id, debit_amount=Decimal("100.00")),
                LineInput(self.revenue.id, credit_amount=Decimal("100.00")),
            ],
            created_by="dara",
        )
        self.engine.post_journal(ORG, journal.id, actor="dara")

        reversal = self.engine.reverse_journal(
            ORG, journal.id, actor="controller", reason="booked to the wrong customer",
            reversal_date=date(2026, 1, 6),
        )

        original = self.engine._get_journal(ORG, journal.id)
        self.assertEqual(original.status, JournalStatus.REVERSED)
        self.assertEqual(original.reversed_by_journal_id, reversal.id)
        self.assertEqual(reversal.reversal_of_journal_id, original.id)
        self.assertEqual(reversal.status, JournalStatus.POSTED)

        # The original entry is NOT deleted or hidden — immutability.
        self.assertEqual(original.total_debits(), Decimal("100.00"))

        # The reversal exactly swaps debit/credit per line.
        reversal_by_account = {l.account_id: l for l in reversal.lines}
        self.assertEqual(reversal_by_account[self.cash.id].credit_amount, Decimal("100.00"))
        self.assertEqual(reversal_by_account[self.cash.id].debit_amount, Decimal("0.00"))
        self.assertEqual(reversal_by_account[self.revenue.id].debit_amount, Decimal("100.00"))

        # Net ledger effect on Cash is zero once both entries are counted.
        ledger = self.engine.get_ledger(ORG, self.cash.id)
        self.assertEqual(len(ledger), 2)
        self.assertEqual(ledger[-1]["running_balance"], Decimal("0.00"))

    def test_cannot_reverse_a_draft_journal(self):
        journal = self.engine.create_draft_journal(
            ORG, date(2026, 1, 5), "Cash sale", "USD",
            [
                LineInput(self.cash.id, debit_amount=Decimal("100.00")),
                LineInput(self.revenue.id, credit_amount=Decimal("100.00")),
            ],
            created_by="dara",
        )
        with self.assertRaises(InvalidJournalStateError):
            self.engine.reverse_journal(ORG, journal.id, actor="controller", reason="n/a")

    # ------------------------------------------------------------------
    def test_trial_balance_matches_ledger_and_is_balanced(self):
        j1 = self.engine.create_draft_journal(
            ORG, date(2026, 1, 5), "Cash sale 1", "USD",
            [
                LineInput(self.cash.id, debit_amount=Decimal("100.00")),
                LineInput(self.revenue.id, credit_amount=Decimal("100.00")),
            ],
            created_by="dara",
        )
        self.engine.post_journal(ORG, j1.id, actor="dara")

        j2 = self.engine.create_draft_journal(
            ORG, date(2026, 1, 10), "Cash sale 2", "USD",
            [
                LineInput(self.cash.id, debit_amount=Decimal("250.50")),
                LineInput(self.revenue.id, credit_amount=Decimal("250.50")),
            ],
            created_by="dara",
        )
        self.engine.post_journal(ORG, j2.id, actor="dara")

        tb = self.engine.get_trial_balance(ORG, self.period.id)
        self.assertTrue(tb["is_balanced"])
        self.assertEqual(tb["total_debits"], Decimal("350.50"))
        self.assertEqual(tb["total_credits"], Decimal("350.50"))
        self.assertEqual(tb["accounts"][self.cash.id]["debit_total"], Decimal("350.50"))
        self.assertEqual(tb["accounts"][self.revenue.id]["credit_total"], Decimal("350.50"))

    def test_draft_journals_do_not_appear_in_ledger_or_trial_balance(self):
        self.engine.create_draft_journal(
            ORG, date(2026, 1, 5), "Never posted", "USD",
            [
                LineInput(self.cash.id, debit_amount=Decimal("999.00")),
                LineInput(self.revenue.id, credit_amount=Decimal("999.00")),
            ],
            created_by="dara",
        )
        ledger = self.engine.get_ledger(ORG, self.cash.id)
        self.assertEqual(ledger, [])
        tb = self.engine.get_trial_balance(ORG, self.period.id)
        self.assertEqual(tb["total_debits"], Decimal("0.00"))

    # ------------------------------------------------------------------
    def test_every_state_change_is_audit_logged(self):
        journal = self.engine.create_draft_journal(
            ORG, date(2026, 1, 5), "Cash sale", "USD",
            [
                LineInput(self.cash.id, debit_amount=Decimal("100.00")),
                LineInput(self.revenue.id, credit_amount=Decimal("100.00")),
            ],
            created_by="dara",
        )
        self.engine.post_journal(ORG, journal.id, actor="dara")
        self.engine.reverse_journal(
            ORG, journal.id, actor="controller", reason="test", reversal_date=date(2026, 1, 6)
        )

        trail = self.engine.get_audit_trail(ORG, "Journal", journal.id)
        actions = [e.action for e in trail]
        self.assertIn("JOURNAL_DRAFTED", actions)
        self.assertIn("JOURNAL_POSTED", actions)
        self.assertIn("JOURNAL_REVERSED", actions)
        # Every audit event names an actor — never anonymous.
        self.assertTrue(all(e.actor for e in trail))

    def test_journals_get_returns_none_for_missing_journal(self):
        """Found during the Phase 2 API-boundary audit: the API router
        for GET /journals/{id} relies on `engine.journals.get(org_id, id)`
        returning None (not raising) for a missing journal, and does its
        own None -> JournalNotFoundError translation — but that
        repository-level contract had no direct test anywhere. This is
        the API boundary contract this router's 404 path actually rests
        on."""
        self.assertIsNone(self.engine.journals.get(ORG, "not-a-real-journal-id"))

    def test_journals_get_returns_none_across_tenants(self):
        """Same contract, checked across a real second organisation —
        the router's 404 path must not distinguish 'wrong org' from
        'does not exist' by returning something different."""
        other_org = "org-other-tenant"
        cash_other = self.engine.create_account(other_org, "1000", "Cash", AccountType.ASSET, actor="setup")
        equity_other = self.engine.create_account(other_org, "3000", "Equity", AccountType.EQUITY, actor="setup")
        self.engine.open_period(other_org, "FY2026-M01", date(2026, 1, 1), date(2026, 1, 31), actor="setup")
        journal = self.engine.create_draft_journal(
            other_org, date(2026, 1, 2), "Other org's journal", "USD",
            [LineInput(cash_other.id, debit_amount=Decimal("10.00")), LineInput(equity_other.id, credit_amount=Decimal("10.00"))],
            created_by="setup",
        )
        self.assertIsNone(self.engine.journals.get(ORG, journal.id))


if __name__ == "__main__":
    unittest.main()
