"""
Automated tests for the Reconciliation module.

Run with:  PYTHONPATH=src python3 -m unittest discover -s tests -v

Stdlib-only — no external dependencies required. Exercises
ReconciliationService against the SQLite repositories and a *real*
AccountingEngine (also SQLite-backed) — reconciliation reads actual
posted journals through the same public interface the API layer will
use, not a mock.
"""
import unittest
from datetime import date
from decimal import Decimal

from asavexa.accounting.domain.enums import AccountType
from asavexa.accounting.domain.errors import JournalNotFoundError
from asavexa.accounting.repository.sqlite_repository import (
    SqliteAccountRepository,
    SqliteJournalRepository,
    SqlitePeriodRepository,
)
from asavexa.accounting.services.engine import AccountingEngine, LineInput
from asavexa.audit.sqlite_repository import SqliteAuditRepository
from asavexa.bootstrap import create_sqlite_connection
from asavexa.reconciliation.domain.enums import BankTransactionStatus, ReconciliationStatus
from asavexa.reconciliation.domain.errors import (
    BankAccountNotFoundError,
    DuplicateExternalTransactionError,
    EmptyReconciliationError,
    InvalidReconciliationStateError,
    InvalidTransactionStateError,
    JournalAlreadyMatchedError,
    UnresolvedTransactionsError,
)
from asavexa.reconciliation.domain.matching import (
    MATCH_RULE_EXACT_AMOUNT_AND_DATE,
    MATCH_RULE_MANUAL_OVERRIDE,
)
from asavexa.reconciliation.domain.models import BankTransactionInput
from asavexa.reconciliation.repository.sqlite_repository import (
    SqliteBankTransactionRepository,
    SqliteReconciliationRepository,
)
from asavexa.reconciliation.services.service import ReconciliationService

ORG_A = "org-meridian"
ORG_B = "org-other-tenant"


class ReconciliationServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.conn = create_sqlite_connection(":memory:")
        audit = SqliteAuditRepository(self.conn)

        self.accounting = AccountingEngine(
            accounts=SqliteAccountRepository(self.conn),
            periods=SqlitePeriodRepository(self.conn),
            journals=SqliteJournalRepository(self.conn),
            audit=audit,
        )
        self.reconciliation = ReconciliationService(
            reconciliations=SqliteReconciliationRepository(self.conn),
            transactions=SqliteBankTransactionRepository(self.conn),
            audit=audit,
            accounting=self.accounting,
        )
        self.audit = audit

        # A minimal chart of accounts + one open period + org B's own
        # completely separate cash account, for tenant-isolation tests.
        self.cash = self.accounting.create_account(ORG_A, "1000", "Cash", AccountType.ASSET, actor="setup")
        self.revenue = self.accounting.create_account(ORG_A, "4000", "Revenue", AccountType.ASSET, actor="setup")
        self.period = self.accounting.open_period(
            ORG_A, "FY2026-M01", date(2026, 1, 1), date(2026, 1, 31), actor="setup"
        )
        self.cash_b = self.accounting.create_account(ORG_B, "1000", "Cash", AccountType.ASSET, actor="setup")
        self.accounting.open_period(ORG_B, "FY2026-M01", date(2026, 1, 1), date(2026, 1, 31), actor="setup")

    def _post_cash_journal(self, org_id, cash_account, other_account, amount, txn_date, desc, debit_cash=True):
        lines = (
            [LineInput(cash_account, debit_amount=amount), LineInput(other_account, credit_amount=amount)]
            if debit_cash else
            [LineInput(other_account, debit_amount=amount), LineInput(cash_account, credit_amount=amount)]
        )
        journal = self.accounting.create_draft_journal(
            org_id, txn_date, desc, "USD", lines, created_by="dara",
        )
        return self.accounting.post_journal(org_id, journal.id, actor="dara")

    # ------------------------------------------------------------------
    # Reconciliation creation
    # ------------------------------------------------------------------
    def test_create_reconciliation_succeeds_for_real_account(self):
        recon = self.reconciliation.create_reconciliation(
            ORG_A, self.cash.id, "January cash reconciliation",
            date(2026, 1, 1), date(2026, 1, 31), actor="dara",
        )
        self.assertEqual(recon.status, ReconciliationStatus.DRAFT)

    def test_create_reconciliation_rejects_unknown_bank_account(self):
        with self.assertRaises(BankAccountNotFoundError):
            self.reconciliation.create_reconciliation(
                ORG_A, "not-a-real-account", "Bad", date(2026, 1, 1), date(2026, 1, 31), actor="dara",
            )

    # ------------------------------------------------------------------
    # Import & duplicate control
    # ------------------------------------------------------------------
    def test_import_valid_transactions_succeeds(self):
        recon = self.reconciliation.create_reconciliation(
            ORG_A, self.cash.id, "Jan", date(2026, 1, 1), date(2026, 1, 31), actor="dara",
        )
        rows = [
            BankTransactionInput(date(2026, 1, 5), "Deposit from Kadena Ltd", debit_amount=Decimal("500.00")),
            BankTransactionInput(date(2026, 1, 6), "Wire out", credit_amount=Decimal("120.00")),
        ]
        created = self.reconciliation.import_transactions(ORG_A, recon.id, rows, actor="dara", import_source="csv")
        self.assertEqual(len(created), 2)
        self.assertEqual(created[0].status, BankTransactionStatus.UNMATCHED)  # no ledger entry yet

    def test_duplicate_import_is_rejected_and_first_import_untouched(self):
        recon = self.reconciliation.create_reconciliation(
            ORG_A, self.cash.id, "Jan", date(2026, 1, 1), date(2026, 1, 31), actor="dara",
        )
        row = BankTransactionInput(date(2026, 1, 5), "Deposit from Kadena Ltd", debit_amount=Decimal("500.00"))
        self.reconciliation.import_transactions(ORG_A, recon.id, [row], actor="dara", import_source="csv")
        with self.assertRaises(DuplicateExternalTransactionError):
            self.reconciliation.import_transactions(ORG_A, recon.id, [row], actor="dara", import_source="csv")
        # Still exactly one transaction — the duplicate created nothing.
        self.assertEqual(len(self.reconciliation.list_transactions(ORG_A, recon.id)), 1)

    def test_different_legitimate_transactions_remain_importable(self):
        recon = self.reconciliation.create_reconciliation(
            ORG_A, self.cash.id, "Jan", date(2026, 1, 1), date(2026, 1, 31), actor="dara",
        )
        rows = [
            BankTransactionInput(date(2026, 1, 5), "Deposit A", debit_amount=Decimal("500.00")),
            BankTransactionInput(date(2026, 1, 5), "Deposit B", debit_amount=Decimal("500.00")),  # same amount/date, different description
        ]
        created = self.reconciliation.import_transactions(ORG_A, recon.id, rows, actor="dara", import_source="csv")
        self.assertEqual(len(created), 2)

    def test_duplicate_detection_is_tenant_safe(self):
        recon_a = self.reconciliation.create_reconciliation(
            ORG_A, self.cash.id, "Jan", date(2026, 1, 1), date(2026, 1, 31), actor="dara",
        )
        recon_b = self.reconciliation.create_reconciliation(
            ORG_B, self.cash_b.id, "Jan", date(2026, 1, 1), date(2026, 1, 31), actor="amara",
        )
        row = BankTransactionInput(date(2026, 1, 5), "Deposit", debit_amount=Decimal("500.00"))
        self.reconciliation.import_transactions(ORG_A, recon_a.id, [row], actor="dara", import_source="csv")
        # Identical content, different org — must NOT be treated as a duplicate.
        created = self.reconciliation.import_transactions(ORG_B, recon_b.id, [row], actor="amara", import_source="csv")
        self.assertEqual(len(created), 1)

    def test_cannot_import_into_non_draft_reconciliation(self):
        recon = self.reconciliation.create_reconciliation(
            ORG_A, self.cash.id, "Jan", date(2026, 1, 1), date(2026, 1, 31), actor="dara",
        )
        row = BankTransactionInput(date(2026, 1, 5), "Deposit", debit_amount=Decimal("500.00"))
        self.reconciliation.import_transactions(ORG_A, recon.id, [row], actor="dara", import_source="csv")
        self.reconciliation.submit_reconciliation(ORG_A, recon.id, actor="dara")
        with self.assertRaises(InvalidReconciliationStateError):
            self.reconciliation.import_transactions(
                ORG_A, recon.id,
                [BankTransactionInput(date(2026, 1, 6), "Late row", debit_amount=Decimal("1.00"))],
                actor="dara", import_source="csv",
            )

    # ------------------------------------------------------------------
    # Deterministic matching
    # ------------------------------------------------------------------
    def test_unique_candidate_is_matched_automatically_with_explicit_rule(self):
        self._post_cash_journal(ORG_A, self.cash.id, self.revenue.id, Decimal("500.00"), date(2026, 1, 5), "Sale")
        recon = self.reconciliation.create_reconciliation(
            ORG_A, self.cash.id, "Jan", date(2026, 1, 1), date(2026, 1, 31), actor="dara",
        )
        row = BankTransactionInput(date(2026, 1, 6), "Deposit", debit_amount=Decimal("500.00"))  # 1 day off, within tolerance
        [txn] = self.reconciliation.import_transactions(ORG_A, recon.id, [row], actor="dara", import_source="csv")
        self.assertEqual(txn.status, BankTransactionStatus.MATCHED)
        self.assertIsNotNone(txn.matched_journal_id)
        self.assertEqual(txn.match_rule, MATCH_RULE_EXACT_AMOUNT_AND_DATE)
        self.assertIn("Unique candidate", txn.match_reason)

    def test_ambiguous_candidates_require_review_not_arbitrary_choice(self):
        self._post_cash_journal(ORG_A, self.cash.id, self.revenue.id, Decimal("500.00"), date(2026, 1, 5), "Sale 1")
        self._post_cash_journal(ORG_A, self.cash.id, self.revenue.id, Decimal("500.00"), date(2026, 1, 6), "Sale 2")
        recon = self.reconciliation.create_reconciliation(
            ORG_A, self.cash.id, "Jan", date(2026, 1, 1), date(2026, 1, 31), actor="dara",
        )
        row = BankTransactionInput(date(2026, 1, 5), "Deposit", debit_amount=Decimal("500.00"))
        [txn] = self.reconciliation.import_transactions(ORG_A, recon.id, [row], actor="dara", import_source="csv")
        self.assertEqual(txn.status, BankTransactionStatus.REVIEW_REQUIRED)
        self.assertIsNone(txn.matched_journal_id)
        self.assertIn("2 posted ledger entries", txn.match_reason)

    def test_no_candidate_is_unmatched(self):
        recon = self.reconciliation.create_reconciliation(
            ORG_A, self.cash.id, "Jan", date(2026, 1, 1), date(2026, 1, 31), actor="dara",
        )
        row = BankTransactionInput(date(2026, 1, 5), "Mystery deposit", debit_amount=Decimal("999.00"))
        [txn] = self.reconciliation.import_transactions(ORG_A, recon.id, [row], actor="dara", import_source="csv")
        self.assertEqual(txn.status, BankTransactionStatus.UNMATCHED)

    def test_amount_mismatch_prevents_automatic_match(self):
        self._post_cash_journal(ORG_A, self.cash.id, self.revenue.id, Decimal("500.00"), date(2026, 1, 5), "Sale")
        recon = self.reconciliation.create_reconciliation(
            ORG_A, self.cash.id, "Jan", date(2026, 1, 1), date(2026, 1, 31), actor="dara",
        )
        row = BankTransactionInput(date(2026, 1, 5), "Deposit", debit_amount=Decimal("499.00"))
        [txn] = self.reconciliation.import_transactions(ORG_A, recon.id, [row], actor="dara", import_source="csv")
        self.assertEqual(txn.status, BankTransactionStatus.UNMATCHED)

    def test_date_outside_tolerance_prevents_automatic_match(self):
        self._post_cash_journal(ORG_A, self.cash.id, self.revenue.id, Decimal("500.00"), date(2026, 1, 5), "Sale")
        recon = self.reconciliation.create_reconciliation(
            ORG_A, self.cash.id, "Jan", date(2026, 1, 1), date(2026, 1, 31), actor="dara",
        )
        # 10 days away — outside the default 3-day tolerance.
        row = BankTransactionInput(date(2026, 1, 15), "Deposit", debit_amount=Decimal("500.00"))
        [txn] = self.reconciliation.import_transactions(ORG_A, recon.id, [row], actor="dara", import_source="csv")
        self.assertEqual(txn.status, BankTransactionStatus.UNMATCHED)

    def test_two_transactions_cannot_claim_the_same_journal(self):
        self._post_cash_journal(ORG_A, self.cash.id, self.revenue.id, Decimal("500.00"), date(2026, 1, 5), "Sale")
        recon = self.reconciliation.create_reconciliation(
            ORG_A, self.cash.id, "Jan", date(2026, 1, 1), date(2026, 1, 31), actor="dara",
        )
        row = BankTransactionInput(date(2026, 1, 5), "Deposit", debit_amount=Decimal("500.00"))
        [first] = self.reconciliation.import_transactions(ORG_A, recon.id, [row], actor="dara", import_source="csv")
        self.assertEqual(first.status, BankTransactionStatus.MATCHED)
        # A second, textually-different bank row with the exact same
        # amount/date would otherwise also look like a unique candidate
        # — but the journal is already claimed, so it must not match.
        row2 = BankTransactionInput(date(2026, 1, 5), "Deposit (duplicate-looking)", debit_amount=Decimal("500.00"))
        [second] = self.reconciliation.import_transactions(ORG_A, recon.id, [row2], actor="dara", import_source="csv")
        self.assertEqual(second.status, BankTransactionStatus.UNMATCHED)

    # ------------------------------------------------------------------
    # Manual matching & rejection
    # ------------------------------------------------------------------
    def test_manual_match_resolves_an_unmatched_transaction(self):
        journal = self._post_cash_journal(ORG_A, self.cash.id, self.revenue.id, Decimal("480.00"), date(2026, 1, 20), "Late-cleared sale")
        recon = self.reconciliation.create_reconciliation(
            ORG_A, self.cash.id, "Jan", date(2026, 1, 1), date(2026, 1, 31), actor="dara",
        )
        row = BankTransactionInput(date(2026, 1, 5), "Deposit", debit_amount=Decimal("480.00"))
        [txn] = self.reconciliation.import_transactions(ORG_A, recon.id, [row], actor="dara", import_source="csv")
        self.assertEqual(txn.status, BankTransactionStatus.UNMATCHED)  # too far in date

        matched = self.reconciliation.manual_match(ORG_A, txn.id, journal.id, actor="dara", note="confirmed with bank")
        self.assertEqual(matched.status, BankTransactionStatus.MATCHED)
        self.assertEqual(matched.matched_journal_id, journal.id)
        self.assertEqual(matched.match_rule, MATCH_RULE_MANUAL_OVERRIDE)

    def test_manual_match_records_amount_mismatch_rather_than_hiding_it(self):
        journal = self._post_cash_journal(ORG_A, self.cash.id, self.revenue.id, Decimal("480.00"), date(2026, 1, 5), "Sale")
        recon = self.reconciliation.create_reconciliation(
            ORG_A, self.cash.id, "Jan", date(2026, 1, 1), date(2026, 1, 31), actor="dara",
        )
        row = BankTransactionInput(date(2026, 1, 5), "Deposit", debit_amount=Decimal("500.00"))
        [txn] = self.reconciliation.import_transactions(ORG_A, recon.id, [row], actor="dara", import_source="csv")
        matched = self.reconciliation.manual_match(ORG_A, txn.id, journal.id, actor="controller")
        self.assertIn("AMOUNT MISMATCH", matched.match_reason)

    def test_manual_match_rejects_journal_already_claimed(self):
        journal = self._post_cash_journal(ORG_A, self.cash.id, self.revenue.id, Decimal("500.00"), date(2026, 1, 5), "Sale")
        recon = self.reconciliation.create_reconciliation(
            ORG_A, self.cash.id, "Jan", date(2026, 1, 1), date(2026, 1, 31), actor="dara",
        )
        [matched_txn] = self.reconciliation.import_transactions(
            ORG_A, recon.id,
            [BankTransactionInput(date(2026, 1, 5), "Deposit", debit_amount=Decimal("500.00"))],
            actor="dara", import_source="csv",
        )
        self.assertEqual(matched_txn.status, BankTransactionStatus.MATCHED)
        [unrelated_txn] = self.reconciliation.import_transactions(
            ORG_A, recon.id,
            [BankTransactionInput(date(2026, 1, 20), "Unrelated deposit", debit_amount=Decimal("77.00"))],
            actor="dara", import_source="csv",
        )
        with self.assertRaises(JournalAlreadyMatchedError):
            self.reconciliation.manual_match(ORG_A, unrelated_txn.id, journal.id, actor="dara")

    def test_manual_match_unknown_journal_raises_accounting_not_found(self):
        recon = self.reconciliation.create_reconciliation(
            ORG_A, self.cash.id, "Jan", date(2026, 1, 1), date(2026, 1, 31), actor="dara",
        )
        [txn] = self.reconciliation.import_transactions(
            ORG_A, recon.id,
            [BankTransactionInput(date(2026, 1, 5), "Deposit", debit_amount=Decimal("500.00"))],
            actor="dara", import_source="csv",
        )
        with self.assertRaises(JournalNotFoundError):
            self.reconciliation.manual_match(ORG_A, txn.id, "not-a-real-journal", actor="dara")

    def test_reject_match_transitions_to_rejected_not_deleted(self):
        self._post_cash_journal(ORG_A, self.cash.id, self.revenue.id, Decimal("500.00"), date(2026, 1, 5), "Sale")
        recon = self.reconciliation.create_reconciliation(
            ORG_A, self.cash.id, "Jan", date(2026, 1, 1), date(2026, 1, 31), actor="dara",
        )
        [txn] = self.reconciliation.import_transactions(
            ORG_A, recon.id,
            [BankTransactionInput(date(2026, 1, 5), "Deposit", debit_amount=Decimal("500.00"))],
            actor="dara", import_source="csv",
        )
        rejected = self.reconciliation.reject_match(ORG_A, txn.id, actor="controller", reason="wrong customer")
        self.assertEqual(rejected.status, BankTransactionStatus.REJECTED)
        self.assertEqual(len(rejected.match_history), 2)  # original auto-match + rejection, both preserved

    def test_invalid_transition_is_rejected(self):
        recon = self.reconciliation.create_reconciliation(
            ORG_A, self.cash.id, "Jan", date(2026, 1, 1), date(2026, 1, 31), actor="dara",
        )
        [txn] = self.reconciliation.import_transactions(
            ORG_A, recon.id,
            [BankTransactionInput(date(2026, 1, 5), "Deposit", debit_amount=Decimal("999.00"))],
            actor="dara", import_source="csv",
        )
        self.assertEqual(txn.status, BankTransactionStatus.UNMATCHED)
        # Cannot approve a transaction that was never matched.
        with self.assertRaises(InvalidTransactionStateError):
            self.reconciliation.approve_transaction(ORG_A, txn.id, actor="controller")

    # ------------------------------------------------------------------
    # Reconciliation submit / approve / reject + finalization gate
    # ------------------------------------------------------------------
    def test_cannot_submit_empty_reconciliation(self):
        recon = self.reconciliation.create_reconciliation(
            ORG_A, self.cash.id, "Jan", date(2026, 1, 1), date(2026, 1, 31), actor="dara",
        )
        with self.assertRaises(EmptyReconciliationError):
            self.reconciliation.submit_reconciliation(ORG_A, recon.id, actor="dara")

    def test_cannot_approve_with_unresolved_transactions(self):
        self._post_cash_journal(ORG_A, self.cash.id, self.revenue.id, Decimal("500.00"), date(2026, 1, 5), "Sale")
        recon = self.reconciliation.create_reconciliation(
            ORG_A, self.cash.id, "Jan", date(2026, 1, 1), date(2026, 1, 31), actor="dara",
        )
        [txn] = self.reconciliation.import_transactions(
            ORG_A, recon.id,
            [BankTransactionInput(date(2026, 1, 5), "Deposit", debit_amount=Decimal("500.00"))],
            actor="dara", import_source="csv",
        )
        self.reconciliation.submit_reconciliation(ORG_A, recon.id, actor="dara")
        # txn is MATCHED but never individually APPROVED by a checker.
        with self.assertRaises(UnresolvedTransactionsError):
            self.reconciliation.approve_reconciliation(ORG_A, recon.id, actor="controller")

    def test_full_approval_finalizes_reconciliation_and_all_lines(self):
        self._post_cash_journal(ORG_A, self.cash.id, self.revenue.id, Decimal("500.00"), date(2026, 1, 5), "Sale")
        recon = self.reconciliation.create_reconciliation(
            ORG_A, self.cash.id, "Jan", date(2026, 1, 1), date(2026, 1, 31), actor="dara",
        )
        [txn] = self.reconciliation.import_transactions(
            ORG_A, recon.id,
            [BankTransactionInput(date(2026, 1, 5), "Deposit", debit_amount=Decimal("500.00"))],
            actor="dara", import_source="csv",
        )
        self.reconciliation.submit_reconciliation(ORG_A, recon.id, actor="dara")
        self.reconciliation.approve_transaction(ORG_A, txn.id, actor="controller")
        finalized = self.reconciliation.approve_reconciliation(ORG_A, recon.id, actor="controller")
        self.assertEqual(finalized.status, ReconciliationStatus.RECONCILED)
        [line] = self.reconciliation.list_transactions(ORG_A, recon.id)
        self.assertEqual(line.status, BankTransactionStatus.RECONCILED)

    def test_reconciled_reconciliation_cannot_be_resubmitted_or_reapproved(self):
        self._post_cash_journal(ORG_A, self.cash.id, self.revenue.id, Decimal("500.00"), date(2026, 1, 5), "Sale")
        recon = self.reconciliation.create_reconciliation(
            ORG_A, self.cash.id, "Jan", date(2026, 1, 1), date(2026, 1, 31), actor="dara",
        )
        [txn] = self.reconciliation.import_transactions(
            ORG_A, recon.id,
            [BankTransactionInput(date(2026, 1, 5), "Deposit", debit_amount=Decimal("500.00"))],
            actor="dara", import_source="csv",
        )
        self.reconciliation.submit_reconciliation(ORG_A, recon.id, actor="dara")
        self.reconciliation.approve_transaction(ORG_A, txn.id, actor="controller")
        self.reconciliation.approve_reconciliation(ORG_A, recon.id, actor="controller")
        with self.assertRaises(InvalidReconciliationStateError):
            self.reconciliation.submit_reconciliation(ORG_A, recon.id, actor="dara")
        with self.assertRaises(InvalidReconciliationStateError):
            self.reconciliation.approve_reconciliation(ORG_A, recon.id, actor="controller")

    def test_reject_reconciliation_is_terminal_and_leaves_lines_untouched(self):
        recon = self.reconciliation.create_reconciliation(
            ORG_A, self.cash.id, "Jan", date(2026, 1, 1), date(2026, 1, 31), actor="dara",
        )
        [txn] = self.reconciliation.import_transactions(
            ORG_A, recon.id,
            [BankTransactionInput(date(2026, 1, 5), "Deposit", debit_amount=Decimal("999.00"))],
            actor="dara", import_source="csv",
        )
        self.reconciliation.submit_reconciliation(ORG_A, recon.id, actor="dara")
        rejected = self.reconciliation.reject_reconciliation(ORG_A, recon.id, actor="controller", reason="incomplete statement")
        self.assertEqual(rejected.status, ReconciliationStatus.REJECTED)
        still_unmatched = self.reconciliation.get_transaction(ORG_A, txn.id)
        self.assertEqual(still_unmatched.status, BankTransactionStatus.UNMATCHED)
        with self.assertRaises(InvalidReconciliationStateError):
            self.reconciliation.submit_reconciliation(ORG_A, recon.id, actor="dara")

    # ------------------------------------------------------------------
    # Evidence linkage (opaque id only)
    # ------------------------------------------------------------------
    def test_attach_evidence_sets_reference(self):
        recon = self.reconciliation.create_reconciliation(
            ORG_A, self.cash.id, "Jan", date(2026, 1, 1), date(2026, 1, 31), actor="dara",
        )
        updated = self.reconciliation.attach_evidence(ORG_A, recon.id, evidence_id="evidence-123", actor="dara")
        self.assertEqual(updated.evidence_ref, "evidence-123")

    def test_cannot_attach_evidence_to_finalized_reconciliation(self):
        self._post_cash_journal(ORG_A, self.cash.id, self.revenue.id, Decimal("500.00"), date(2026, 1, 5), "Sale")
        recon = self.reconciliation.create_reconciliation(
            ORG_A, self.cash.id, "Jan", date(2026, 1, 1), date(2026, 1, 31), actor="dara",
        )
        [txn] = self.reconciliation.import_transactions(
            ORG_A, recon.id,
            [BankTransactionInput(date(2026, 1, 5), "Deposit", debit_amount=Decimal("500.00"))],
            actor="dara", import_source="csv",
        )
        self.reconciliation.submit_reconciliation(ORG_A, recon.id, actor="dara")
        self.reconciliation.approve_transaction(ORG_A, txn.id, actor="controller")
        self.reconciliation.approve_reconciliation(ORG_A, recon.id, actor="controller")
        with self.assertRaises(InvalidReconciliationStateError):
            self.reconciliation.attach_evidence(ORG_A, recon.id, evidence_id="late-evidence", actor="dara")

    # ------------------------------------------------------------------
    # Tenant isolation
    # ------------------------------------------------------------------
    def test_organisation_b_cannot_read_organisation_a_reconciliation(self):
        recon = self.reconciliation.create_reconciliation(
            ORG_A, self.cash.id, "Jan", date(2026, 1, 1), date(2026, 1, 31), actor="dara",
        )
        from asavexa.reconciliation.domain.errors import ReconciliationNotFoundError
        with self.assertRaises(ReconciliationNotFoundError):
            self.reconciliation.get_reconciliation(ORG_B, recon.id)

    def test_organisation_b_cannot_import_using_organisation_a_reconciliation_id(self):
        recon = self.reconciliation.create_reconciliation(
            ORG_A, self.cash.id, "Jan", date(2026, 1, 1), date(2026, 1, 31), actor="dara",
        )
        from asavexa.reconciliation.domain.errors import ReconciliationNotFoundError
        with self.assertRaises(ReconciliationNotFoundError):
            self.reconciliation.import_transactions(
                ORG_B, recon.id,
                [BankTransactionInput(date(2026, 1, 5), "Deposit", debit_amount=Decimal("1.00"))],
                actor="amara", import_source="csv",
            )

    def test_organisation_b_cannot_match_organisation_a_transaction(self):
        recon = self.reconciliation.create_reconciliation(
            ORG_A, self.cash.id, "Jan", date(2026, 1, 1), date(2026, 1, 31), actor="dara",
        )
        [txn] = self.reconciliation.import_transactions(
            ORG_A, recon.id,
            [BankTransactionInput(date(2026, 1, 5), "Deposit", debit_amount=Decimal("500.00"))],
            actor="dara", import_source="csv",
        )
        journal = self._post_cash_journal(ORG_A, self.cash.id, self.revenue.id, Decimal("500.00"), date(2026, 1, 5), "Sale")
        from asavexa.reconciliation.domain.errors import BankTransactionNotFoundError
        with self.assertRaises(BankTransactionNotFoundError):
            self.reconciliation.manual_match(ORG_B, txn.id, journal.id, actor="amara")

    def test_organisation_b_cannot_approve_organisation_a_reconciliation(self):
        self._post_cash_journal(ORG_A, self.cash.id, self.revenue.id, Decimal("500.00"), date(2026, 1, 5), "Sale")
        recon = self.reconciliation.create_reconciliation(
            ORG_A, self.cash.id, "Jan", date(2026, 1, 1), date(2026, 1, 31), actor="dara",
        )
        [txn] = self.reconciliation.import_transactions(
            ORG_A, recon.id,
            [BankTransactionInput(date(2026, 1, 5), "Deposit", debit_amount=Decimal("500.00"))],
            actor="dara", import_source="csv",
        )
        self.reconciliation.submit_reconciliation(ORG_A, recon.id, actor="dara")
        self.reconciliation.approve_transaction(ORG_A, txn.id, actor="controller")
        from asavexa.reconciliation.domain.errors import ReconciliationNotFoundError
        with self.assertRaises(ReconciliationNotFoundError):
            self.reconciliation.approve_reconciliation(ORG_B, recon.id, actor="intruder")

    def test_organisation_b_cannot_see_organisation_a_exceptions(self):
        self.reconciliation.create_reconciliation(
            ORG_A, self.cash.id, "Jan", date(2026, 1, 1), date(2026, 1, 31), actor="dara",
        )
        recon_a = self.reconciliation.list_reconciliations(ORG_A)
        recon_b = self.reconciliation.list_reconciliations(ORG_B)
        self.assertEqual(len(recon_a), 1)
        self.assertEqual(len(recon_b), 0)

    # ------------------------------------------------------------------
    # Audit trail
    # ------------------------------------------------------------------
    def test_audit_events_are_recorded_with_distinguishable_actors(self):
        self._post_cash_journal(ORG_A, self.cash.id, self.revenue.id, Decimal("500.00"), date(2026, 1, 5), "Sale")
        recon = self.reconciliation.create_reconciliation(
            ORG_A, self.cash.id, "Jan", date(2026, 1, 1), date(2026, 1, 31), actor="dara",
        )
        [txn] = self.reconciliation.import_transactions(
            ORG_A, recon.id,
            [BankTransactionInput(date(2026, 1, 5), "Deposit", debit_amount=Decimal("500.00"))],
            actor="dara", import_source="csv",
        )
        self.reconciliation.submit_reconciliation(ORG_A, recon.id, actor="dara")
        self.reconciliation.approve_transaction(ORG_A, txn.id, actor="controller")
        self.reconciliation.approve_reconciliation(ORG_A, recon.id, actor="controller")

        events = self.audit.list_for_org(ORG_A)
        actions = {e.action for e in events}
        for expected in (
            "RECONCILIATION_CREATED", "TRANSACTION_IMPORTED", "MATCH_ACCEPTED",
            "TRANSACTION_APPROVED", "RECONCILIATION_SUBMITTED",
            "RECONCILIATION_APPROVED", "RECONCILIATION_FINALIZED",
        ):
            self.assertIn(expected, actions, f"missing audit action {expected}")

        makers = {e.actor for e in events if e.action == "RECONCILIATION_SUBMITTED"}
        checkers = {e.actor for e in events if e.action == "RECONCILIATION_APPROVED"}
        self.assertEqual(makers, {"dara"})
        self.assertEqual(checkers, {"controller"})
        self.assertNotEqual(makers, checkers)

    # ------------------------------------------------------------------
    # Accounting Engine is untouched
    # ------------------------------------------------------------------
    def test_accounting_engine_state_is_unchanged_by_reconciliation(self):
        journal = self._post_cash_journal(ORG_A, self.cash.id, self.revenue.id, Decimal("500.00"), date(2026, 1, 5), "Sale")
        tb_before = self.accounting.get_trial_balance(ORG_A, self.period.id)

        recon = self.reconciliation.create_reconciliation(
            ORG_A, self.cash.id, "Jan", date(2026, 1, 1), date(2026, 1, 31), actor="dara",
        )
        [txn] = self.reconciliation.import_transactions(
            ORG_A, recon.id,
            [BankTransactionInput(date(2026, 1, 5), "Deposit", debit_amount=Decimal("500.00"))],
            actor="dara", import_source="csv",
        )
        self.reconciliation.submit_reconciliation(ORG_A, recon.id, actor="dara")
        self.reconciliation.approve_transaction(ORG_A, txn.id, actor="controller")
        self.reconciliation.approve_reconciliation(ORG_A, recon.id, actor="controller")

        tb_after = self.accounting.get_trial_balance(ORG_A, self.period.id)
        self.assertEqual(tb_before, tb_after)
        reloaded_journal = self.accounting.journals.get(ORG_A, journal.id)
        self.assertEqual(reloaded_journal.status, journal.status)
        self.assertEqual(reloaded_journal.total_debits(), journal.total_debits())


if __name__ == "__main__":
    unittest.main()
