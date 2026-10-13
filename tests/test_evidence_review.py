"""Evidence Review engine, compliance check, and the case lifecycle (on the real services over SQLite)."""
import unittest

from test_passport import World
from asavexa.compliance.domain.enums import ControlResult, FindingStatus
from asavexa.evidence.domain.enums import EvidenceType
from asavexa.evidencereview.errors import EvidenceReviewError, ReviewForbiddenError, ReviewNotFoundError, ReviewStateError
from asavexa.evidencereview.review import build_review, gap_count
from asavexa.evidencereview.rules import validate_rules
from asavexa.evidencereview.service import EvidenceReviewService
from asavexa.proofgraph.graph import UnknownReportError
from asavexa.security.store import MemoryDocStore


def svc(w, store=None):
    from asavexa.identity.repository.sqlite_repository import SqliteMembershipRepository
    mem = SqliteMembershipRepository(w.conn)
    return EvidenceReviewService(store or MemoryDocStore(), w.reporting, w.vault, w.compliance,
                                 is_member=lambda org, uid: mem.get(org, uid) is not None, log=lambda *a, **k: w.events.append(a))


def make(w):
    w.events = []
    w.compliance.evidence = w.vault  # as api/deps.py does in production
    return svc(w)


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.w = World()

    def review(self, rt="income_statement", **kw):
        return build_review(self.w.reporting, self.w.org.id, self.w.period.id, rt, self.w.owner.id, vault=self.w.vault, **kw)

    def test_partly_supported(self):
        r = self.review()
        self.assertEqual(r["verdict"], "PARTLY_SUPPORTED")
        self.assertEqual([s["link"]["kind"] for s in r["supporting"]], ["RECORDED"])
        self.assertEqual([m["kind"] for m in r["missing"]], ["MISSING"])
        self.assertEqual(gap_count(r), 1)
        self.assertTrue(r["action_needed"])

    def test_fingerprint_is_reproducible(self):
        self.assertEqual(self.review()["fingerprint"], self.review()["fingerprint"])

    def test_without_vault_nothing_is_claimed_supported(self):
        r = build_review(self.w.reporting, self.w.org.id, self.w.period.id, "income_statement", self.w.owner.id)
        self.assertNotEqual(r["verdict"], "SUPPORTED")
        self.assertTrue(any("not connected" in u for u in r["uncertain"]))

    def test_unknown_report_and_bad_rules(self):
        with self.assertRaises(UnknownReportError):
            self.review("cash_flow")
        with self.assertRaises(EvidenceReviewError):
            self.review(rules=[{"id": "x", "severity": "EXTREME"}])
        with self.assertRaises(ValueError):
            validate_rules("nope")

    def test_unknown_account_scope(self):
        with self.assertRaises(EvidenceReviewError):
            self.review(account_id="no-such-account")

    def test_verifying_the_rent_evidence_supports_everything(self):
        w = self.w
        ev = w.vault.upload_evidence(w.org.id, EvidenceType.CONTRACT, b"lease-1", "lease.pdf", "application/pdf",
                                     uploaded_by=w.accountant.id, linked_journal_id=w.rent_journal.id)
        self.assertEqual(self.review()["metrics"]["unverified"], 1)
        w.vault.verify_evidence(w.org.id, ev.id, actor=w.approver.id)
        r = self.review()
        self.assertEqual(r["verdict"], "SUPPORTED")
        self.assertEqual(gap_count(r), 0)

    def test_self_verified_flagged(self):
        w = self.w
        ev = w.vault.upload_evidence(w.org.id, EvidenceType.CONTRACT, b"lease-2", "lease.pdf", "application/pdf",
                                     uploaded_by=w.approver.id, linked_journal_id=w.rent_journal.id)
        w.vault.verify_evidence(w.org.id, ev.id, actor=w.approver.id)
        self.assertEqual(self.review()["metrics"]["self_verified"], 1)

    def test_other_tenant_cannot_review_our_period(self):
        w = self.w
        with self.assertRaises(Exception) as cm:
            build_review(w.reporting, w.other_org.id, w.period.id, "income_statement", w.other_owner.id, vault=w.vault)
        self.assertNotIn("JRN-", str(cm.exception))


class CheckTests(unittest.TestCase):
    def test_control_fails_then_opens_finding(self):
        w = World(); s = make(w)
        c = s._control(w.org.id, w.owner.id)
        ex = w.compliance.execute_control(w.org.id, c.id, w.owner.id, period_id=w.period.id, params={"report_type": "income_statement"})
        self.assertEqual(ex.result, ControlResult.FAIL)
        self.assertIsNotNone(ex.finding_id)
        self.assertEqual(ex.reference["metrics"]["journals_with_gaps"], 1)

    def test_standard_control_count_unchanged(self):
        w = World()
        self.assertNotIn("ER-REVIEW", [c.code for c in w.compliance.list_controls(w.org.id)])


class CaseLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.w = World(); self.s = make(self.w); self.o = self.w.org.id

    def open(self):
        return self.s.open_case(self.o, self.w.period.id, "income_statement", self.w.accountant.id)

    def fix(self):
        w = self.w
        ev = w.vault.upload_evidence(self.o, EvidenceType.CONTRACT, b"lease-9", "lease.pdf", "application/pdf",
                                     uploaded_by=w.accountant.id, linked_journal_id=w.rent_journal.id)
        w.vault.verify_evidence(self.o, ev.id, actor=w.approver.id)

    def test_full_scenario(self):
        w, s, o = self.w, self.s, self.o
        c = self.open()
        self.assertEqual((c["status"], c["baseline"]["gaps"]), ("OPEN", 1))
        self.assertEqual(w.compliance.get_finding(o, c["finding_id"]).status, FindingStatus.REMEDIATION_REQUIRED)
        c = s.plan_action(o, c["id"], "Attach the lease and have it verified", w.accountant.id, w.owner.id)
        self.assertEqual(c["status"], "ACTION_PLANNED")
        self.fix()
        c = s.complete_action(o, c["id"], w.accountant.id, "Lease uploaded and verified", "EV-1")
        self.assertEqual(w.compliance.get_finding(o, c["finding_id"]).status, FindingStatus.RESOLVED)
        c = s.verify_outcome(o, c["id"], w.approver.id, "Low: lease could expire", "Any new journal without evidence")
        self.assertEqual(c["status"], "VERIFIED")
        self.assertEqual((c["outcome"]["result"], c["outcome"]["baseline_gaps"], c["outcome"]["post_gaps"]), ("RESOLVED", 1, 0))
        self.assertEqual(w.compliance.get_finding(o, c["finding_id"]).status, FindingStatus.CLOSED)
        self.assertEqual(s.get_case(o, c["id"])["finding_status"], "CLOSED")
        actions = [e[0] for e in w.events]
        self.assertEqual(actions, ["EVIDENCE_REVIEW_CASE_OPENED", "EVIDENCE_REVIEW_ACTION_PLANNED", "EVIDENCE_REVIEW_ACTION_COMPLETED", "EVIDENCE_REVIEW_OUTCOME_VERIFIED"])

    def test_verifier_cannot_be_the_doer_or_owner(self):
        w, s, o = self.w, self.s, self.o
        c = self.open()
        s.plan_action(o, c["id"], "fix", w.accountant.id, w.owner.id)
        self.fix()
        s.complete_action(o, c["id"], w.owner.id, "done")
        for who in (w.owner.id, w.accountant.id):
            with self.assertRaises(ReviewForbiddenError):
                s.verify_outcome(o, c["id"], who, "r", "c")
        self.assertEqual(s.get_case(o, c["id"])["status"], "ACTION_DONE")

    def test_not_fixed_is_rejected_not_verified(self):
        w, s, o = self.w, self.s, self.o
        c = self.open()
        s.plan_action(o, c["id"], "fix", w.accountant.id, w.owner.id)
        s.complete_action(o, c["id"], w.accountant.id, "claimed done")
        c = s.verify_outcome(o, c["id"], w.approver.id, "high", "again")
        self.assertEqual(c["status"], "ACTION_PLANNED")
        self.assertEqual(c["attempts"][0]["result"], "NOT_IMPROVED")
        self.assertIsNone(c["outcome"])
        self.assertEqual(w.compliance.get_finding(o, c["finding_id"]).status, FindingStatus.REMEDIATION_REQUIRED)

    def test_required_fields_and_states(self):
        w, s, o = self.w, self.s, self.o
        c = self.open()
        with self.assertRaises(ReviewStateError):
            s.complete_action(o, c["id"], w.owner.id, "x")
        with self.assertRaises(EvidenceReviewError):
            s.plan_action(o, c["id"], "", w.accountant.id, w.owner.id)
        with self.assertRaises(EvidenceReviewError):
            s.plan_action(o, c["id"], "fix", "not-a-member", w.owner.id)
        with self.assertRaises(EvidenceReviewError):
            s.plan_action(o, c["id"], "fix", w.accountant.id, w.owner.id, due_date="soon")
        with self.assertRaises(ReviewStateError):
            self.open()  # duplicate for same figure
        with self.assertRaises(ReviewStateError):
            s.verify_outcome(o, c["id"], w.approver.id, "r", "c")

    def test_nothing_to_raise_when_supported(self):
        self.fix()
        with self.assertRaises(ReviewStateError):
            self.open()

    def test_recheck_reopens_when_gaps_return(self):
        w, s, o = self.w, self.s, self.o
        w = World(); s = make(w); o = w.org.id
        c = s.open_case(o, w.period.id, "income_statement", w.accountant.id)
        s.plan_action(o, c["id"], "fix", w.accountant.id, w.owner.id)
        ev = w.vault.upload_evidence(o, EvidenceType.CONTRACT, b"l", "l.pdf", "application/pdf", uploaded_by=w.accountant.id, linked_journal_id=w.rent_journal.id)
        w.vault.verify_evidence(o, ev.id, actor=w.approver.id)
        s.complete_action(o, c["id"], w.accountant.id, "done")
        c = s.verify_outcome(o, c["id"], w.approver.id, "r", "c")
        self.assertEqual(s.recheck(o, c["id"], w.owner.id)["status"], "VERIFIED")
        w.vault.reject_evidence(o, ev.id, actor=w.approver.id, reason="forged")
        c = s.recheck(o, c["id"], w.owner.id)
        self.assertEqual(c["status"], "REOPENED")
        self.assertEqual(w.compliance.get_finding(o, c["finding_id"]).status, FindingStatus.REMEDIATION_REQUIRED)
        c = s.plan_action(o, c["id"], "re-obtain the lease", w.accountant.id, w.owner.id)
        self.assertEqual(c["status"], "ACTION_PLANNED")

    def test_other_tenant_cannot_see_or_touch_case(self):
        w, s = self.w, self.s
        c = self.open()
        other = w.other_org.id
        self.assertEqual(s.list_cases(other), [])
        for call in (lambda: s.get_case(other, c["id"]), lambda: s.plan_action(other, c["id"], "x", w.other_owner.id, w.other_owner.id),
                     lambda: s.complete_action(other, c["id"], w.other_owner.id, "x"), lambda: s.verify_outcome(other, c["id"], w.other_owner.id, "r", "c"),
                     lambda: s.recheck(other, c["id"], w.other_owner.id)):
            with self.assertRaises(ReviewNotFoundError):
                call()


if __name__ == "__main__":
    unittest.main()


class RouterTests(unittest.TestCase):
    """Calls the REAL router functions (fastapi is stood in for by the harness; everything else is real)."""

    @classmethod
    def setUpClass(cls):
        import harness_security_routers as H
        import importlib
        cls.H = H
        cls.er = importlib.import_module("asavexa.api.routers.evidence_review")

    def setUp(self):
        self.w = World(); self.s = make(self.w); self.o = self.w.org.id
        self.a = self.w.accountant.id

    def test_read_and_scenario_through_the_router(self):
        er, w, s, o = self.er, self.w, self.s, self.o
        r = er.review(w.period.id, "income_statement", None, o, w.owner.id, s)
        self.assertEqual(r["verdict"], "PARTLY_SUPPORTED")
        c = er.open_case(er.OpenBody(period_id=w.period.id), o, self.a, s)
        c = er.plan(c["id"], er.PlanBody(action="Attach the lease", owner=self.a), o, w.owner.id, s)
        ev = w.vault.upload_evidence(o, EvidenceType.CONTRACT, b"rl", "l.pdf", "application/pdf", uploaded_by=self.a, linked_journal_id=w.rent_journal.id)
        w.vault.verify_evidence(o, ev.id, actor=w.approver.id)
        c = er.complete(c["id"], er.DoneBody(note="done"), o, self.a, s)
        c = er.verify(c["id"], er.VerifyBody(residual_risk="low", reopen_criteria="new gap"), o, w.approver.id, s)
        self.assertEqual(c["status"], "VERIFIED")
        self.assertEqual(len(er.list_cases(None, o, s)["cases"]), 1)

    def test_errors_become_http_errors(self):
        er, w, s, o = self.er, self.w, self.s, self.o
        for fn, code in ((lambda: er.get_case("nope", o, s), 404), (lambda: er.review(w.period.id, "cash_flow", None, o, w.owner.id, s), None),
                         (lambda: er.verify("nope", er.VerifyBody(residual_risk="r", reopen_criteria="c"), o, w.approver.id, s), 404)):
            with self.assertRaises(self.H.HTTPException) as cm:
                fn()
            if code:
                self.assertEqual(cm.exception.status_code, code)

    def test_router_uses_the_right_permissions(self):
        import inspect
        src = inspect.getsource(self.er)
        for needle in ("FINDING_MANAGE", "FINDING_REMEDIATE", "FINDING_VERIFY", "REPORTING_READ"):
            self.assertIn(needle, src)
