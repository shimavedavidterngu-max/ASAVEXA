"""Stage 1, two-tenant isolation at the service level, on the real services over in-memory SQLite.

Organisation A is fully populated (accounts, periods, journals, evidence, reconciliation, controls, executions, findings).
Organisation B's owner then tries, by A's identifiers, every read and write below. Each attempt must be refused (or return
nothing), and A's data, and A's audit trail, must be byte-for-byte what they were before.
The HTTP version over every route, on real FastAPI + PostgreSQL, is tests/stack/test_two_tenants_http.py (runs in CI)."""
import json
import unittest
from datetime import date

import harness_security_routers as H
from harness_security_routers import auth, HTTPException
from test_passport import World
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.errors import PermissionDeniedError
from asavexa.audit.sqlite_repository import SqliteAuditRepository


def fingerprint(w):
    """Everything of A's we can read, as one string."""
    o = w.org.id
    rows = [w.accounting.accounts.list_for_org(o), w.accounting.periods.list_for_org(o), w.accounting.journals.list_for_org(o), w.vault.list_for_org(o),
            w.recon.list_reconciliations(o), w.compliance.list_controls(o), w.compliance.list_executions(o), w.compliance.list_findings(o),
            w.identity.list_members(o), SqliteAuditRepository(w.conn).list_for_org(o)]
    parts = [sorted(repr(x) for x in group) for group in rows]
    return json.dumps(parts, default=str, sort_keys=True)


class TwoTenants(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.w = World()

    def setUp(self):
        self.A, self.B = self.w.org.id, self.w.other_org.id
        self.b_actor = self.w.other_owner.id
        self.before = fingerprint(self.w)

    def tearDown(self):
        self.assertEqual(fingerprint(self.w), self.before, "organisation A changed because of organisation B's attempts")

    def refused(self, fn):
        """B must get an error, or nothing back. Returning A's data (anything non-empty) is the failure."""
        try:
            out = fn()
        except HTTPException as e:
            self.assertIn(e.status_code, (403, 404))
            return
        except Exception as e:                     # any domain error (not found / permission / validation) is a refusal
            self.assertNotIsInstance(e, (AssertionError, AttributeError, TypeError, NameError), f"test bug, not a refusal: {e!r}")
            return
        self.assertFalse(out, f"B received something for A's identifier: {out!r}")

    # ---- control: the same calls succeed for A, so a refusal above means isolation, not a broken call
    def test_control_a_can_use_its_own_data(self):
        w, A = self.w, self.A
        self.assertEqual(w.vault.get_evidence(A, w.evidence.id).id, w.evidence.id)
        self.assertTrue(w.accounting.get_ledger(A, w.cash.id))
        self.assertTrue(w.accounting.get_trial_balance(A, w.period.id)["accounts"])
        self.assertEqual(w.recon.get_reconciliation(A, w.reconciliation.id).id, w.reconciliation.id)
        self.assertTrue(w.compliance.get_control(A, w.compliance.list_controls(A)[0].id))
        self.assertTrue(auth.list_members(A, w.owner.id, w.identity))

    # ---- accounting
    def test_accounting_by_id(self):
        w, B = self.w, self.B
        self.refused(lambda: w.accounting.post_journal(B, w.invoice.id, actor=self.b_actor))
        self.refused(lambda: w.accounting.reverse_journal(B, w.invoice.id, self.b_actor, "cross-tenant attempt"))
        self.refused(lambda: w.accounting.get_ledger(B, w.cash.id))
        self.refused(lambda: w.accounting.get_trial_balance(B, w.period.id))   # A's period is 'not found' for B, not an empty success
        self.refused(lambda: w.accounting.lock_period(B, w.period.id, self.b_actor, "cross-tenant attempt"))
        self.refused(lambda: w.accounting.get_audit_trail(B, "Journal", w.invoice.id))

    def test_b_lists_are_empty_of_a(self):
        w, B = self.w, self.B
        for rows in (w.accounting.accounts.list_for_org(B), w.accounting.periods.list_for_org(B), w.accounting.journals.list_for_org(B),
                     w.vault.list_for_org(B), w.recon.list_reconciliations(B), w.compliance.list_controls(B),
                     w.compliance.list_executions(B), w.compliance.list_findings(B)):
            self.assertEqual(list(rows), [])

    # ---- evidence
    def test_evidence_by_id(self):
        w, B = self.w, self.B
        self.refused(lambda: w.vault.get_evidence(B, w.evidence.id))
        self.refused(lambda: w.vault.verify_evidence(B, w.evidence.id, self.b_actor, "cross-tenant attempt"))

    # ---- reconciliation
    def test_reconciliation_by_id(self):
        w, B = self.w, self.B
        self.refused(lambda: w.recon.get_reconciliation(B, w.reconciliation.id))
        self.refused(lambda: w.recon.list_transactions(B, w.reconciliation.id))
        txn_id = w.recon.list_transactions(self.A, w.reconciliation.id)[0].id
        self.refused(lambda: w.recon.get_transaction(B, txn_id))
        self.refused(lambda: w.recon.approve_transaction(B, txn_id, self.b_actor))
        self.refused(lambda: w.recon.approve_reconciliation(B, w.reconciliation.id, self.b_actor))

    # ---- compliance
    def test_compliance_by_id(self):
        w, B = self.w, self.B
        control = w.compliance.list_controls(self.A)[0]
        execution = w.compliance.list_executions(self.A)[0]
        self.refused(lambda: w.compliance.get_control(B, control.id))
        self.refused(lambda: w.compliance.get_execution(B, execution.id))
        self.refused(lambda: w.compliance.review_execution(B, execution.id, self.b_actor))
        self.refused(lambda: w.compliance.execute_control(B, control.id, actor=self.b_actor, period_id=w.period.id))
        for f in w.compliance.list_findings(self.A):
            self.refused(lambda: w.compliance.get_finding(B, f.id))
            self.refused(lambda: w.compliance.close_finding(B, f.id, self.b_actor))

    # ---- identity / membership
    def test_a_member_of_b_cannot_manage_a_membership(self):
        w = self.w
        victim = w.accountant.id
        with self.assertRaises(PermissionDeniedError):
            w.identity.add_membership(self.A, w.other_owner.id, Role.OWNER, actor_user_id=self.b_actor)
        with self.assertRaises(PermissionDeniedError):
            w.identity.change_role(self.A, victim, Role.AUDITOR, actor_user_id=self.b_actor)
        with self.assertRaises(PermissionDeniedError):
            w.identity.revoke_membership(self.A, victim, actor_user_id=self.b_actor)
        self.assertIsNone(w.identity.get_role(self.b_actor, self.A))

    def test_the_members_route_refuses_a_non_member(self):
        with self.assertRaises(HTTPException) as ctx:
            auth.list_members(self.A, self.b_actor, self.w.identity)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertTrue(auth.list_members(self.B, self.b_actor, self.w.identity))     # their own list works

    def test_a_low_privilege_member_of_a_cannot_manage_a_either(self):
        w = self.w
        with self.assertRaises(PermissionDeniedError):
            w.identity.add_membership(self.A, w.other_owner.id, Role.ACCOUNTANT, actor_user_id=w.accountant.id)
        with self.assertRaises(PermissionDeniedError):
            w.identity.change_role(self.A, w.approver.id, Role.OWNER, actor_user_id=w.accountant.id)

    def test_one_session_cannot_be_pointed_at_an_organisation_the_person_does_not_belong_to(self):
        w = self.w
        _, token = w.identity.authenticate("other@other.test", "unrelated-password1")
        with self.assertRaises(PermissionDeniedError):
            w.identity.select_organisation(token, self.A)
        self.assertIsNone(w.identity.validate_session(token).org_id, "a refused selection must not change the session")
        self.assertEqual(w.identity.select_organisation(token, self.B).org_id, self.B)


if __name__ == "__main__":
    unittest.main()
