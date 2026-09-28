"""
Integration test: Identity + Accounting Engine + Evidence Vault, wired
together through one shared SQLite connection and one shared audit
trail — proving the cross-module integration this build was actually
for, not just that each module passes its own tests in isolation.
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
from asavexa.evidence.domain.enums import EvidenceType
from asavexa.evidence.repository.sqlite_repository import SqliteEvidenceRepository
from asavexa.evidence.services.vault import MISSING, EvidenceVault
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.errors import PermissionDeniedError
from asavexa.identity.domain.permissions import EVIDENCE_UPLOAD, JOURNAL_CREATE, JOURNAL_POST
from asavexa.identity.repository.sqlite_repository import (
    SqliteMembershipRepository,
    SqliteOrganisationRepository,
    SqliteSessionRepository,
    SqliteUserRepository,
)
from asavexa.identity.services.service import IdentityService


class CrossModuleIntegrationTestCase(unittest.TestCase):
    def setUp(self):
        self.conn = create_sqlite_connection(":memory:")
        audit = SqliteAuditRepository(self.conn)

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
        self.audit = audit

        # Stand up a tenant with two real, differently-permissioned users.
        self.owner = self.identity.register_user("dara@meridian.test", "correct horse battery staple")
        self.org = self.identity.create_organisation("Meridian Textiles Ltd", actor=self.owner.id)
        self.identity.add_membership(self.org.id, self.owner.id, Role.OWNER, actor_user_id=self.owner.id)

        self.accountant = self.identity.register_user("aisha@meridian.test", "another-strong-password")
        self.identity.add_membership(
            self.org.id, self.accountant.id, Role.ACCOUNTANT, actor_user_id=self.owner.id
        )

        self.cash = self.accounting.create_account(self.org.id, "1000", "Cash", AccountType.ASSET, actor=self.owner.id)
        self.revenue = self.accounting.create_account(self.org.id, "4000", "Revenue", AccountType.REVENUE, actor=self.owner.id)
        self.period = self.accounting.open_period(
            self.org.id, "FY2026-M01", date(2026, 1, 1), date(2026, 1, 31), actor=self.owner.id
        )

    def test_accountant_can_prepare_but_not_post_maker_checker(self):
        """RBAC from the Identity module gates access to the Accounting
        Engine at the API boundary — proven here by checking
        require_permission before calling the engine, exactly as the
        (not-yet-written) API routes will."""
        self.identity.require_permission(self.accountant.id, self.org.id, JOURNAL_CREATE)  # allowed
        with self.assertRaises(PermissionDeniedError):
            self.identity.require_permission(self.accountant.id, self.org.id, JOURNAL_POST)  # denied

    def test_full_evidence_backed_transaction_flow(self):
        # 1. Accountant is permitted to create a draft and upload evidence.
        self.identity.require_permission(self.accountant.id, self.org.id, JOURNAL_CREATE)
        self.identity.require_permission(self.accountant.id, self.org.id, EVIDENCE_UPLOAD)

        journal = self.accounting.create_draft_journal(
            self.org.id, date(2026, 1, 5), "Cash sale to Kadena Ltd", "USD",
            [
                LineInput(self.cash.id, debit_amount=Decimal("500.00")),
                LineInput(self.revenue.id, credit_amount=Decimal("500.00")),
            ],
            created_by=self.accountant.id,
        )

        # Before evidence is attached, the "Show Me the Number" chain
        # must clearly say so — never silently pass.
        self.assertEqual(
            self.evidence.get_status_for_reference(self.org.id, journal_id=journal.id), MISSING
        )

        record = self.evidence.upload_evidence(
            self.org.id, EvidenceType.INVOICE, b"fake invoice content for Kadena Ltd",
            "invoice-kadena.pdf", "application/pdf", uploaded_by=self.accountant.id,
            linked_journal_id=journal.id,
        )
        # Link the journal back to the evidence (the two modules connect
        # only through this opaque string reference).
        journal.evidence_ref = record.id
        self.accounting.journals.update(journal)

        self.assertEqual(
            self.evidence.get_status_for_reference(self.org.id, journal_id=journal.id),
            "UPLOADED",
        )

        # 2. Owner (who holds JOURNAL_POST and EVIDENCE_VERIFY) reviews
        # and posts — a different actor from the one who drafted it.
        self.identity.require_permission(self.owner.id, self.org.id, JOURNAL_POST)
        self.evidence.verify_evidence(self.org.id, record.id, actor=self.owner.id, note="matches bank receipt")
        posted = self.accounting.post_journal(self.org.id, journal.id, actor=self.owner.id)

        self.assertEqual(
            self.evidence.get_status_for_reference(self.org.id, journal_id=journal.id),
            "VERIFIED",
        )

        # 3. Trial balance reflects the posted, evidence-backed entry.
        tb = self.accounting.get_trial_balance(self.org.id, self.period.id)
        self.assertTrue(tb["is_balanced"])
        self.assertEqual(tb["total_debits"], Decimal("500.00"))

        # 4. One shared audit trail carries actions from all three
        # modules for this organisation — this is the actual point of
        # the promotion done at the start of this build.
        org_events = self.audit.list_for_org(self.org.id)
        actions = {e.action for e in org_events}
        self.assertIn("ORGANISATION_CREATED", actions)       # Identity
        self.assertIn("MEMBERSHIP_CREATED", actions)          # Identity
        self.assertIn("JOURNAL_DRAFTED", actions)              # Accounting
        self.assertIn("JOURNAL_POSTED", actions)               # Accounting
        self.assertIn("EVIDENCE_UPLOADED", actions)            # Evidence
        self.assertIn("EVIDENCE_VERIFIED", actions)            # Evidence
        # Provenance: the drafter and the poster are recorded as
        # different actors — maker-checker really happened, not just in
        # theory.
        drafted_by = next(e.actor for e in org_events if e.action == "JOURNAL_DRAFTED")
        posted_by = next(e.actor for e in org_events if e.action == "JOURNAL_POSTED")
        self.assertEqual(drafted_by, self.accountant.id)
        self.assertEqual(posted_by, self.owner.id)
        self.assertNotEqual(drafted_by, posted_by)


if __name__ == "__main__":
    unittest.main()
