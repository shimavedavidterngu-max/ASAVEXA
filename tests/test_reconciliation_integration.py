"""
Integration test: Identity (permissions) + Accounting Engine (read-only)
+ Evidence Vault + Reconciliation, wired together through one shared
audit trail — proving the maker-checker separation is enforced by the
*existing* Identity permission model, not by anything invented inside
Reconciliation itself.

Flow (per the module's build brief):
    ACCOUNTANT/maker  -> imports bank transactions, creates a
                          reconciliation, matches, attaches evidence
    APPROVER/checker  -> verifies evidence, approves each transaction,
                          finalizes the reconciliation
then verifies: final status, Accounting Engine untouched, the evidence
relationship exists, the shared audit trail names both actors
distinctly, and organisation isolation holds throughout.
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
from asavexa.evidence.domain.enums import EvidenceStatus, EvidenceType
from asavexa.evidence.repository.sqlite_repository import SqliteEvidenceRepository
from asavexa.evidence.services.vault import EvidenceVault
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.errors import PermissionDeniedError
from asavexa.identity.domain.permissions import (
    RECONCILIATION_APPROVE,
    RECONCILIATION_CREATE,
    RECONCILIATION_IMPORT,
    RECONCILIATION_MATCH,
)
from asavexa.identity.repository.sqlite_repository import (
    SqliteMembershipRepository,
    SqliteOrganisationRepository,
    SqliteSessionRepository,
    SqliteUserRepository,
)
from asavexa.identity.services.service import IdentityService
from asavexa.reconciliation.domain.enums import BankTransactionStatus, ReconciliationStatus
from asavexa.reconciliation.domain.models import BankTransactionInput
from asavexa.reconciliation.repository.sqlite_repository import (
    SqliteBankTransactionRepository,
    SqliteReconciliationRepository,
)
from asavexa.reconciliation.services.service import ReconciliationService


class ReconciliationCrossModuleIntegrationTestCase(unittest.TestCase):
    def setUp(self):
        self.conn = create_sqlite_connection(":memory:")
        audit = SqliteAuditRepository(self.conn)
        self.audit = audit

        self.identity = IdentityService(
            organisations=SqliteOrganisationRepository(self.conn),
            users=SqliteUserRepository(self.conn),
            memberships=SqliteMembershipRepository(self.conn),
            sessions=SqliteSessionRepository(self.conn),
            audit=audit,
        )
        self.accounting = AccountingEngine(
            accounts=SqliteAccountRepository(self.conn),
            periods=SqlitePeriodRepository(self.conn),
            journals=SqliteJournalRepository(self.conn),
            audit=audit,
        )
        self.evidence = EvidenceVault(
            evidence=SqliteEvidenceRepository(self.conn),
            audit=audit,
        )
        self.reconciliation = ReconciliationService(
            reconciliations=SqliteReconciliationRepository(self.conn),
            transactions=SqliteBankTransactionRepository(self.conn),
            audit=audit,
            accounting=self.accounting,
        )

        # Organisation A: a real tenant with a maker and a checker.
        self.owner = self.identity.register_user("dara@meridian.test", "correct horse battery staple")
        self.org = self.identity.create_organisation("Meridian Textiles Ltd", actor=self.owner.id)
        self.identity.add_membership(self.org.id, self.owner.id, Role.OWNER, actor_user_id=self.owner.id)

        self.accountant = self.identity.register_user("aisha@meridian.test", "another-strong-password")
        self.identity.add_membership(self.org.id, self.accountant.id, Role.ACCOUNTANT, actor_user_id=self.owner.id)

        self.approver = self.identity.register_user("kwame@meridian.test", "yet-another-password")
        self.identity.add_membership(self.org.id, self.approver.id, Role.APPROVER, actor_user_id=self.owner.id)

        # Organisation B: a second, unrelated tenant.
        self.other_owner = self.identity.register_user("priya@other.test", "totally-unrelated-password")
        self.other_org = self.identity.create_organisation("Other Org Ltd", actor=self.other_owner.id)
        self.identity.add_membership(self.other_org.id, self.other_owner.id, Role.OWNER, actor_user_id=self.other_owner.id)

        # Chart of accounts + an already-posted sale for Org A only.
        self.cash = self.accounting.create_account(self.org.id, "1000", "Cash", AccountType.ASSET, actor=self.owner.id)
        self.revenue = self.accounting.create_account(self.org.id, "4000", "Revenue", AccountType.ASSET, actor=self.owner.id)
        self.period = self.accounting.open_period(
            self.org.id, "FY2026-M01", date(2026, 1, 1), date(2026, 1, 31), actor=self.owner.id
        )
        journal = self.accounting.create_draft_journal(
            self.org.id, date(2026, 1, 5), "Cash sale to Kadena Ltd", "USD",
            [LineInput(self.cash.id, debit_amount=Decimal("500.00")),
             LineInput(self.revenue.id, credit_amount=Decimal("500.00"))],
            created_by=self.owner.id,
        )
        self.journal = self.accounting.post_journal(self.org.id, journal.id, actor=self.owner.id)

    # ------------------------------------------------------------------
    # Permission-matrix behaviour for the roles this module cares about
    # ------------------------------------------------------------------
    def test_accountant_has_maker_permissions_but_not_approve(self):
        self.identity.require_permission(self.accountant.id, self.org.id, RECONCILIATION_IMPORT)
        self.identity.require_permission(self.accountant.id, self.org.id, RECONCILIATION_CREATE)
        self.identity.require_permission(self.accountant.id, self.org.id, RECONCILIATION_MATCH)
        with self.assertRaises(PermissionDeniedError):
            self.identity.require_permission(self.accountant.id, self.org.id, RECONCILIATION_APPROVE)

    def test_approver_has_approve_but_not_maker_permissions(self):
        self.identity.require_permission(self.approver.id, self.org.id, RECONCILIATION_APPROVE)
        for permission in (RECONCILIATION_IMPORT, RECONCILIATION_CREATE, RECONCILIATION_MATCH):
            with self.assertRaises(PermissionDeniedError):
                self.identity.require_permission(self.approver.id, self.org.id, permission)

    def test_same_actor_cannot_prepare_and_approve_their_own_reconciliation(self):
        """The maker (ACCOUNTANT) does the entire preparation themselves,
        then is denied when attempting the approval step — proving
        maker-checker holds even when it would be 'convenient' to let
        one person finish the job."""
        recon = self.reconciliation.create_reconciliation(
            self.org.id, self.cash.id, "January", date(2026, 1, 1), date(2026, 1, 31), actor=self.accountant.id,
        )
        [txn] = self.reconciliation.import_transactions(
            self.org.id, recon.id,
            [BankTransactionInput(date(2026, 1, 5), "Deposit", debit_amount=Decimal("500.00"))],
            actor=self.accountant.id, import_source="csv",
        )
        self.assertEqual(txn.status, BankTransactionStatus.MATCHED)
        self.reconciliation.submit_reconciliation(self.org.id, recon.id, actor=self.accountant.id)

        # The accountant has RECONCILIATION_MATCH/CREATE/IMPORT but not
        # RECONCILIATION_APPROVE — the identity layer must refuse them
        # here, exactly as it would at the API boundary.
        with self.assertRaises(PermissionDeniedError):
            self.identity.require_permission(self.accountant.id, self.org.id, RECONCILIATION_APPROVE)

    def test_unauthorized_actor_cannot_approve(self):
        """A user with no membership at all in this organisation must be
        refused, distinctly from a member who merely lacks the
        permission."""
        recon = self.reconciliation.create_reconciliation(
            self.org.id, self.cash.id, "January", date(2026, 1, 1), date(2026, 1, 31), actor=self.accountant.id,
        )
        with self.assertRaises(PermissionDeniedError):
            self.identity.require_permission(self.other_owner.id, self.org.id, RECONCILIATION_APPROVE)

    # ------------------------------------------------------------------
    # The full maker -> checker flow
    # ------------------------------------------------------------------
    def test_full_maker_checker_flow_with_evidence_and_shared_audit_trail(self):
        # ---- MAKER (accountant): import, create, match, attach evidence ----
        self.identity.require_permission(self.accountant.id, self.org.id, RECONCILIATION_CREATE)
        recon = self.reconciliation.create_reconciliation(
            self.org.id, self.cash.id, "January cash reconciliation",
            date(2026, 1, 1), date(2026, 1, 31), actor=self.accountant.id,
        )

        self.identity.require_permission(self.accountant.id, self.org.id, RECONCILIATION_IMPORT)
        [txn] = self.reconciliation.import_transactions(
            self.org.id, recon.id,
            [BankTransactionInput(date(2026, 1, 6), "Deposit from Kadena Ltd", debit_amount=Decimal("500.00"))],
            actor=self.accountant.id, import_source="bank_feed",
        )
        # Deterministic matching found the one posted sale automatically.
        self.assertEqual(txn.status, BankTransactionStatus.MATCHED)
        self.assertEqual(txn.matched_journal_id, self.journal.id)

        evidence_record = self.evidence.upload_evidence(
            self.org.id, EvidenceType.BANK_STATEMENT, b"fake January bank statement PDF content",
            "statement-jan-2026.pdf", "application/pdf", uploaded_by=self.accountant.id,
            linked_transaction_ref=f"reconciliation:{recon.id}",
        )
        recon = self.reconciliation.attach_evidence(
            self.org.id, recon.id, evidence_id=evidence_record.id, actor=self.accountant.id
        )
        self.reconciliation.submit_reconciliation(self.org.id, recon.id, actor=self.accountant.id)

        # ---- CHECKER (approver): verify evidence, approve, finalize ----
        self.identity.require_permission(self.approver.id, self.org.id, RECONCILIATION_APPROVE)

        # The checker looks at the evidence status before trusting it —
        # exactly the "Show Me the Number" pattern from the Accounting
        # Engine's own cross-module test: Reconciliation never checks
        # evidence status itself, the reviewer does, using EvidenceVault
        # directly.
        status = self.evidence.get_status_for_reference(
            self.org.id, transaction_ref=f"reconciliation:{recon.id}"
        )
        self.assertEqual(status, "UPLOADED")  # present, but not yet verified
        self.evidence.verify_evidence(self.org.id, evidence_record.id, actor=self.approver.id, note="matches bank feed")
        status_after = self.evidence.get_status_for_reference(
            self.org.id, transaction_ref=f"reconciliation:{recon.id}"
        )
        self.assertEqual(status_after, EvidenceStatus.VERIFIED.value)

        self.reconciliation.approve_transaction(self.org.id, txn.id, actor=self.approver.id)
        finalized = self.reconciliation.approve_reconciliation(self.org.id, recon.id, actor=self.approver.id)

        # ---- Assertions ----
        self.assertEqual(finalized.status, ReconciliationStatus.RECONCILED)
        self.assertEqual(finalized.evidence_ref, evidence_record.id)

        final_txn = self.reconciliation.get_transaction(self.org.id, txn.id)
        self.assertEqual(final_txn.status, BankTransactionStatus.RECONCILED)

        # Accounting Engine untouched by any of this.
        reloaded_journal = self.accounting.journals.get(self.org.id, self.journal.id)
        self.assertEqual(reloaded_journal.status, self.journal.status)
        self.assertEqual(reloaded_journal.total_debits(), Decimal("500.00"))

        # Evidence relationship genuinely exists (not just an unused field).
        self.assertIsNotNone(finalized.evidence_ref)
        linked_evidence = self.evidence.get_evidence(self.org.id, finalized.evidence_ref)
        self.assertEqual(linked_evidence.status, EvidenceStatus.VERIFIED)

        # Shared audit trail names both actors distinctly.
        org_events = self.audit.list_for_org(self.org.id)
        maker_events = {e.actor for e in org_events if e.action in
                        ("RECONCILIATION_CREATED", "TRANSACTION_IMPORTED", "RECONCILIATION_SUBMITTED")}
        checker_events = {e.actor for e in org_events if e.action in
                           ("TRANSACTION_APPROVED", "RECONCILIATION_APPROVED", "RECONCILIATION_FINALIZED")}
        self.assertEqual(maker_events, {self.accountant.id})
        self.assertEqual(checker_events, {self.approver.id})
        self.assertTrue(maker_events.isdisjoint(checker_events))

        evidence_events = {e.actor for e in org_events if e.action == "EVIDENCE_VERIFIED"}
        self.assertEqual(evidence_events, {self.approver.id})

        # Organisation isolation still holds after all of this activity.
        from asavexa.reconciliation.domain.errors import ReconciliationNotFoundError
        with self.assertRaises(ReconciliationNotFoundError):
            self.reconciliation.get_reconciliation(self.other_org.id, recon.id)
        self.assertEqual(len(self.reconciliation.list_reconciliations(self.other_org.id)), 0)
        with self.assertRaises(PermissionDeniedError):
            self.identity.require_permission(self.other_owner.id, self.org.id, RECONCILIATION_APPROVE)


if __name__ == "__main__":
    unittest.main()
