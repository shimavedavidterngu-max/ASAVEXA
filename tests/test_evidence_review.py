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


class OutcomeMeasurementTests(unittest.TestCase):
    """Stage 10: rated residual risk, a reopen rule the system can check, scheduled re-checks and a measurement timeline."""

    def setUp(self):
        from datetime import datetime, timezone
        self.w = World(); self.s = make(self.w); self.o = self.w.org.id
        self.clock = [datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)]
        self.s.now = lambda: self.clock[0]

    def done_case(self):
        w, s, o = self.w, self.s, self.o
        c = s.open_case(o, w.period.id, "income_statement", w.accountant.id)
        s.plan_action(o, c["id"], "fix", w.accountant.id, w.owner.id)
        self.ev = w.vault.upload_evidence(o, EvidenceType.CONTRACT, b"l", "l.pdf", "application/pdf", uploaded_by=w.accountant.id, linked_journal_id=w.rent_journal.id)
        w.vault.verify_evidence(o, self.ev.id, actor=w.approver.id)
        return s.complete_action(o, c["id"], w.accountant.id, "done")

    def test_rating_threshold_and_interval_are_recorded(self):
        c = self.done_case()
        c = self.s.verify_outcome(self.o, c["id"], self.w.approver.id, "Lease may lapse", "A new unsupported journal", "ok",
                                  residual_level="medium", reopen_if_gaps_above=2, recheck_after_days=30)
        out = c["outcome"]
        self.assertEqual((out["residual_level"], out["reopen_if_gaps_above"], out["recheck_after_days"]), ("MEDIUM", 2, 30))
        self.assertEqual(c["recheck_due"], "2026-10-31")

    def test_bad_values_are_refused_and_change_nothing(self):
        c = self.done_case()
        for kw in ({"residual_level": "SEVERE"}, {"reopen_if_gaps_above": -1}, {"reopen_if_gaps_above": "x"}, {"reopen_if_gaps_above": True},
                   {"reopen_if_gaps_above": 1.5}, {"recheck_after_days": 0}, {"recheck_after_days": 400}):
            with self.assertRaises(EvidenceReviewError, msg=str(kw)):
                self.s.verify_outcome(self.o, c["id"], self.w.approver.id, "r", "c", **kw)
        self.assertEqual(self.s.get_case(self.o, c["id"])["status"], "ACTION_DONE")

    def test_defaults_keep_the_old_behaviour(self):
        c = self.done_case()
        c = self.s.verify_outcome(self.o, c["id"], self.w.approver.id, "r", "c")
        self.assertEqual((c["outcome"]["residual_level"], c["outcome"]["reopen_if_gaps_above"], c["recheck_due"]), (None, 0, None))

    def test_gaps_within_tolerance_do_not_reopen(self):
        w, s, o = self.w, self.s, self.o
        c = self.done_case()
        c = s.verify_outcome(o, c["id"], w.approver.id, "r", "c", reopen_if_gaps_above=1)
        w.vault.reject_evidence(o, self.ev.id, actor=w.approver.id, reason="forged")
        c = s.recheck(o, c["id"], w.owner.id)
        self.assertEqual(c["status"], "VERIFIED")
        self.assertEqual((c["rechecks"][-1]["gaps"], c["rechecks"][-1]["tolerance"]), (1, 1))
        self.assertIn("within the agreed tolerance", c["history"][-1]["note"])

    def test_gaps_above_tolerance_reopen_and_clear_the_schedule(self):
        w, s, o = self.w, self.s, self.o
        c = self.done_case()
        c = s.verify_outcome(o, c["id"], w.approver.id, "r", "c", reopen_if_gaps_above=0, recheck_after_days=7)
        w.vault.reject_evidence(o, self.ev.id, actor=w.approver.id, reason="forged")
        c = s.recheck(o, c["id"], w.owner.id)
        self.assertEqual((c["status"], c["recheck_due"]), ("REOPENED", None))
        self.assertIn("above the agreed tolerance", c["history"][-1]["note"])

    def test_due_for_recheck_follows_the_clock(self):
        from datetime import datetime, timezone
        w, s, o = self.w, self.s, self.o
        c = self.done_case()
        s.verify_outcome(o, c["id"], w.approver.id, "r", "c", recheck_after_days=10)
        self.assertEqual(s.list_cases(o, due_for_recheck=True), [])
        self.clock[0] = datetime(2026, 10, 11, 9, 0, tzinfo=timezone.utc)
        self.assertEqual([x["id"] for x in s.list_cases(o, due_for_recheck=True)], [c["id"]])
        s.recheck(o, c["id"], w.owner.id)  # clean: the next re-check is scheduled 10 days on
        self.assertEqual(s.list_cases(o, due_for_recheck=True), [])
        self.assertEqual(s.get_case(o, c["id"])["recheck_due"], "2026-10-21")

    def test_timeline_lists_every_measurement_in_order(self):
        w, s, o = self.w, self.s, self.o
        c = s.open_case(o, w.period.id, "income_statement", w.accountant.id)
        s.plan_action(o, c["id"], "fix", w.accountant.id, w.owner.id)
        s.complete_action(o, c["id"], w.accountant.id, "claimed")           # nothing was actually fixed
        self.clock[0] = self.clock[0].replace(hour=10)
        s.verify_outcome(o, c["id"], w.approver.id, "r", "c")               # rejected
        kinds = [m["kind"] for m in s.get_case(o, c["id"])["measurements"]]
        self.assertEqual(kinds, ["BASELINE", "REJECTED_ATTEMPT"])
        self.assertEqual([m["gaps"] for m in s.get_case(o, c["id"])["measurements"]], [1, 1])

    def test_other_tenant_never_sees_due_cases(self):
        from datetime import datetime, timezone
        c = self.done_case()
        self.s.verify_outcome(self.o, c["id"], self.w.approver.id, "r", "c", recheck_after_days=1)
        self.clock[0] = datetime(2026, 12, 1, tzinfo=timezone.utc)
        self.assertEqual(self.s.list_cases("some-other-org", due_for_recheck=True), [])


def _rules(**over):
    """The default rules, with ER-003 (expenses) changed as asked."""
    from asavexa.evidencereview.rules import DEFAULT_RULES
    out = [dict(r) for r in DEFAULT_RULES]
    for r in out:
        if r["id"] == "ER-003":
            r.update(over)
    return out


class RuleSetTests(unittest.TestCase):
    """Stage 11: an organisation's own expected-record rules, proposed by one person and approved by another."""

    def setUp(self):
        self.w = World(); self.s = make(self.w); self.o = self.w.org.id

    def fix(self):
        w = self.w
        ev = w.vault.upload_evidence(self.o, EvidenceType.CONTRACT, b"lease-r", "lease.pdf", "application/pdf", uploaded_by=w.accountant.id, linked_journal_id=w.rent_journal.id)
        w.vault.verify_evidence(self.o, ev.id, actor=w.approver.id)
        return ev

    def strict(self):
        return _rules(expects_any=["RECEIPT"])

    def activate(self, rules=None, note="ok"):
        d = self.s.propose_rule_set(self.o, rules or self.strict(), self.w.accountant.id, "Expenses need receipts")
        return self.s.approve_rule_set(self.o, d["version"], self.w.approver.id, note)

    def test_starts_on_the_built_in_defaults(self):
        ov = self.s.rule_set_overview(self.o)
        self.assertEqual((ov["active"]["version"], ov["active"]["source"], ov["pending"], ov["history"]), (0, "DEFAULT", None, []))
        self.assertEqual(self.s.review(self.o, self.w.period.id, "income_statement", self.w.owner.id)["rules_version"], 0)

    def test_a_proposal_changes_nothing_until_approved(self):
        self.fix()
        d = self.s.propose_rule_set(self.o, self.strict(), self.w.accountant.id, "Expenses need receipts")
        self.assertEqual((d["version"], d["status"]), (1, "PENDING"))
        self.assertEqual(self.s.active_rule_set(self.o)["version"], 0)
        self.assertEqual(gap_count(self.s.review(self.o, self.w.period.id, "income_statement", self.w.owner.id)), 0)
        self.assertEqual(self.s.rule_set_overview(self.o)["pending"]["version"], 1)

    def test_proposer_cannot_approve_but_someone_else_can(self):
        d = self.s.propose_rule_set(self.o, self.strict(), self.w.accountant.id, "why")
        with self.assertRaises(ReviewForbiddenError):
            self.s.approve_rule_set(self.o, d["version"], self.w.accountant.id)
        a = self.s.approve_rule_set(self.o, d["version"], self.w.approver.id, "agreed")
        self.assertEqual((a["status"], a["decided_by"]), ("ACTIVE", self.w.approver.id))
        self.assertEqual(self.s.active_rule_set(self.o)["version"], 1)

    def test_approved_rules_change_what_counts_as_a_gap(self):
        self.fix()
        before = self.s.review(self.o, self.w.period.id, "income_statement", self.w.owner.id)
        self.activate()
        after = self.s.review(self.o, self.w.period.id, "income_statement", self.w.owner.id)
        self.assertEqual((gap_count(before), gap_count(after), after["rules_version"]), (0, 1, 1))
        self.assertEqual(after["missing"][0]["kind"], "WRONG_TYPE")
        self.assertNotEqual(before["fingerprint"], after["fingerprint"])

    def test_a_new_version_supersedes_the_old_and_history_is_kept(self):
        self.activate()
        self.activate(_rules(expects_any=["INVOICE"]))
        ov = self.s.rule_set_overview(self.o)
        self.assertEqual([(h["version"], h["status"]) for h in ov["history"]], [(2, "ACTIVE"), (1, "SUPERSEDED")])

    def test_the_baseline_rule_cannot_be_removed_or_narrowed(self):
        from asavexa.evidencereview.rules import DEFAULT_RULES
        no_base = [dict(r) for r in DEFAULT_RULES if r["id"] != "ER-001"]
        narrowed = [dict(r) for r in DEFAULT_RULES]; narrowed[0]["account_types"] = ["REVENUE"]
        for bad in (no_base, narrowed):
            with self.assertRaises(EvidenceReviewError) as cm:
                self.s.propose_rule_set(self.o, bad, self.w.accountant.id, "x")
            self.assertIn("ER-001", str(cm.exception))
        # it may be made stricter
        stricter = [dict(r) for r in DEFAULT_RULES]; stricter[0]["expects_any"] = ["INVOICE", "CONTRACT"]
        self.assertEqual(self.s.propose_rule_set(self.o, stricter, self.w.accountant.id, "stricter")["status"], "PENDING")

    def test_bad_rule_sets_are_refused(self):
        from asavexa.evidencereview.rules import DEFAULT_RULES
        many = [dict(r) for r in DEFAULT_RULES] + [{"id": f"X-{i}", "name": "n", "account_types": None, "expects_any": None, "severity": "LOW"} for i in range(30)]
        weird = [dict(r) for r in DEFAULT_RULES] + [{"id": "bad id!", "name": "n"}]
        for bad in ("nope", [], [1], many, weird, _rules(severity="EXTREME"), _rules(expects_any=["LUNCH"])):
            with self.assertRaises(EvidenceReviewError, msg=str(bad)[:40]):
                self.s.propose_rule_set(self.o, bad, self.w.accountant.id, "x")
        with self.assertRaises(EvidenceReviewError):
            self.s.propose_rule_set(self.o, self.strict(), self.w.accountant.id, "  ")
        self.assertEqual(self.s.rule_set_overview(self.o)["history"], [])

    def test_no_change_and_one_proposal_at_a_time(self):
        from asavexa.evidencereview.rules import DEFAULT_RULES
        with self.assertRaises(ReviewStateError):
            self.s.propose_rule_set(self.o, [dict(r) for r in DEFAULT_RULES], self.w.accountant.id, "same")
        self.s.propose_rule_set(self.o, self.strict(), self.w.accountant.id, "first")
        with self.assertRaises(ReviewStateError):
            self.s.propose_rule_set(self.o, _rules(expects_any=["INVOICE"]), self.w.accountant.id, "second")

    def test_reject_needs_a_reason_and_a_rejected_change_cannot_be_approved(self):
        d = self.s.propose_rule_set(self.o, self.strict(), self.w.accountant.id, "why")
        with self.assertRaises(EvidenceReviewError):
            self.s.reject_rule_set(self.o, d["version"], self.w.approver.id, " ")
        self.s.reject_rule_set(self.o, d["version"], self.w.approver.id, "Too strict for us")
        with self.assertRaises(ReviewStateError):
            self.s.approve_rule_set(self.o, d["version"], self.w.approver.id)
        self.assertEqual(self.s.active_rule_set(self.o)["version"], 0)
        # and a new proposal is now allowed, as version 2
        self.assertEqual(self.s.propose_rule_set(self.o, self.strict(), self.w.accountant.id, "again")["version"], 2)

    def test_unknown_versions_are_not_found(self):
        for v in (0, 7, -1, "1"):
            with self.assertRaises(ReviewNotFoundError):
                self.s.approve_rule_set(self.o, v, self.w.approver.id)

    def test_a_case_keeps_the_rules_it_was_measured_with(self):
        w, s, o = self.w, self.s, self.o
        c = s.open_case(o, w.period.id, "income_statement", w.accountant.id)
        self.assertEqual(c["rules_version"], 0)
        s.plan_action(o, c["id"], "attach the lease", w.accountant.id, w.owner.id)
        self.fix()
        s.complete_action(o, c["id"], w.accountant.id, "done")
        self.activate()                              # stricter rules arrive while the case is open
        c = s.verify_outcome(o, c["id"], w.approver.id, "r", "c")
        self.assertEqual((c["status"], c["outcome"]["result"], c["outcome"]["post_gaps"]), ("VERIFIED", "RESOLVED", 0))
        c = s.recheck(o, c["id"], w.owner.id)        # a later re-check uses the rules now in force
        self.assertEqual((c["status"], c["rules_version"], c["baseline"]["gaps"]), ("REOPENED", 1, 1))

    def test_rule_changes_are_audited(self):
        self.activate()
        self.assertEqual([e[0] for e in self.w.events], ["EVIDENCE_RULES_PROPOSED", "EVIDENCE_RULES_APPROVED"])
        d = self.s.propose_rule_set(self.o, _rules(expects_any=["INVOICE"]), self.w.accountant.id, "x")
        self.s.reject_rule_set(self.o, d["version"], self.w.approver.id, "no")
        self.assertEqual(self.w.events[-1][0], "EVIDENCE_RULES_REJECTED")

    def test_other_organisation_never_sees_or_decides_our_rules(self):
        d = self.s.propose_rule_set(self.o, self.strict(), self.w.accountant.id, "why")
        other = "00000000-other-org"
        self.assertEqual(self.s.rule_set_overview(other)["history"], [])
        self.assertEqual(self.s.active_rule_set(other)["version"], 0)
        for fn in (lambda: self.s.approve_rule_set(other, d["version"], "someone"), lambda: self.s.reject_rule_set(other, d["version"], "someone", "x"),
                   lambda: self.s.rule_set_version(other, d["version"])):
            with self.assertRaises(ReviewNotFoundError):
                fn()
        self.assertEqual(self.s.rule_set_overview(self.o)["pending"]["version"], d["version"])


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

    def test_verify_accepts_the_new_fields_through_the_router(self):
        er, w, o, sv = self.er, self.w, self.o, self.s
        c = er.open_case(er.OpenBody(period_id=w.period.id), o, w.accountant.id, sv)
        er.plan(c["id"], er.PlanBody(action="fix", owner=w.accountant.id), o, w.owner.id, sv)
        ev = w.vault.upload_evidence(o, EvidenceType.CONTRACT, b"l", "l.pdf", "application/pdf", uploaded_by=w.accountant.id, linked_journal_id=w.rent_journal.id)
        w.vault.verify_evidence(o, ev.id, actor=w.approver.id)
        er.complete(c["id"], er.DoneBody(note="done"), o, w.accountant.id, sv)
        c = er.verify(c["id"], er.VerifyBody(residual_risk="r", reopen_criteria="c", residual_level="LOW", reopen_if_gaps_above=1, recheck_after_days=14), o, w.approver.id, sv)
        self.assertEqual((c["outcome"]["residual_level"], c["outcome"]["reopen_if_gaps_above"]), ("LOW", 1))
        self.assertEqual(er.list_cases(None, o, sv, True)["cases"], [])
        with self.assertRaises(er.HTTPException) as cm:
            er.verify(c["id"], er.VerifyBody(residual_risk="r", reopen_criteria="c", residual_level="BAD"), o, w.approver.id, sv)
        self.assertEqual(cm.exception.status_code, 409)

    def test_rule_sets_through_the_router(self):
        er, w, o, sv = self.er, self.w, self.o, self.s
        body = er.RulesBody(rules=_rules(expects_any=["RECEIPT"]), reason="Expenses need receipts")
        d = er.propose_rules(body, o, w.accountant.id, sv)
        self.assertEqual(d["status"], "PENDING")
        self.assertEqual(er.rules_overview(o, sv)["pending"]["version"], 1)
        with self.assertRaises(er.HTTPException) as cm:
            er.approve_rules(1, er.DecisionBody(), o, w.accountant.id, sv)
        self.assertEqual(cm.exception.status_code, 403)
        self.assertEqual(er.approve_rules(1, er.DecisionBody(note="ok"), o, w.approver.id, sv)["status"], "ACTIVE")
        with self.assertRaises(er.HTTPException) as cm:
            er.reject_rules(9, er.RejectBody(reason="no"), o, w.approver.id, sv)
        self.assertEqual(cm.exception.status_code, 404)
        with self.assertRaises(er.HTTPException) as cm:
            er.propose_rules(er.RulesBody(rules=[], reason="x"), o, w.accountant.id, sv)
        self.assertEqual(cm.exception.status_code, 400)

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
        for needle in ("FINDING_MANAGE", "FINDING_REMEDIATE", "FINDING_VERIFY", "REPORTING_READ", "GRC_PREPARE", "GRC_APPROVE"):
            self.assertIn(needle, src)
