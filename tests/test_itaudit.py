"""IT audit: change records and flags, repeatable samples, change tests, control definitions and tests, two-person approval, policy, isolation, audit, permissions."""
import ast
import os
import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace

from analysis_fixture import ORG, OTHER, World
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.permissions import AUDIT_READ, ITAUDIT_APPROVE, ITAUDIT_PREPARE, ROLE_PERMISSIONS
from asavexa.itaudit.errors import ItAuditError, ItAuditForbiddenError, ItAuditNotFoundError, ItAuditStateError
from asavexa.itaudit.service import ItAuditService, refnum, select_sample

U1, U2, U3 = "user-1", "user-2", "user-3"   # U1 records, U2 tests, U3 approves


class Clock:
    def __init__(self): self.d = date(2026, 2, 15)
    def __call__(self): return datetime(self.d.year, self.d.month, self.d.day, 9, tzinfo=timezone.utc)


class Vault:
    def get_evidence(self, org, i):
        if org == ORG and i in ("ev1", "ev2"): return SimpleNamespace(id=i, original_filename=f"{i}.pdf", file_hash="h" * 64)
        raise LookupError(i)


class Base(unittest.TestCase):
    def setUp(self):
        self.w = World(); self.clock = Clock(); self.events = []
        self.svc = ItAuditService(self.w.store, Vault(), log=lambda *a: self.events.append(a), now=self.clock)

    def change(self, actor=U1, org=ORG, **kw):
        d = dict(system="Payroll", title="Update tax tables", description="Applied the new tax tables to payroll", change_type="NORMAL", risk="LOW", requested_by="Ada",
                 approved_by_name="Ben", approved_on="2026-02-01", ticket_ref=f"CHG-{len(self.events)}-{kw.get('n', '')}", implemented_on="2026-02-03",
                 testing_evidence="Tested in the staging copy with 20 payslips", rollback_plan="Restore the previous table file")
        d.update({k: v for k, v in kw.items() if k != "n"}); return self.svc.ia_record_change(org, d, actor)

    def control(self, actor=U1, **kw):
        d = dict(system="Payroll", name="Duplicate payee check", control_type="INPUT_VALIDATION", description="The system rejects a second payee with the same bank account",
                 expected_result="Duplicate payee is rejected", frequency="CONTINUOUS", tolerable=0); d.update(kw); return self.svc.ia_define_control(ORG, d, actor)

    def ctest(self, c, actor=U2, **kw):
        d = dict(title="Test duplicate payee check", control_id=c["id"]); d.update(kw); return self.svc.ia_plan_control_test(ORG, d, actor)

    def case(self, t, result="PASS", actor=U2, **kw):
        d = dict(description="Entered a payee with an existing bank account", expected="Rejected", actual="Rejected", result=result, performed_on="2026-02-14"); d.update(kw)
        return self.svc.ia_add_case(ORG, t["id"], d, actor)

    def ptest(self, actor=U2, **kw):
        d = dict(title="February change test", period_from="2026-02-01", period_to="2026-02-14", sample_size=3, seed="feb-2026", tolerable=0); d.update(kw)
        return self.svc.ia_plan_change_test(ORG, d, actor)

    def conclude_all(self, t, actor=U2):
        for i in t["items"]: t = self.svc.ia_conclude_item(ORG, t["id"], i["id"], {"result": "NO_EXCEPTION"}, actor)
        return t


class Helpers(unittest.TestCase):
    def test_refnum_sorts_numerically(self):
        self.assertEqual(sorted([{"ref": "CH-010"}, {"ref": "CH-002"}], key=refnum)[0]["ref"], "CH-002"); self.assertEqual(refnum({"ref": "x"}), 0)

    def test_sample_is_repeatable_and_depends_on_seed(self):
        refs = [f"CH-{i:03d}" for i in range(1, 30)]
        a = select_sample(refs, "s1", 5); self.assertEqual(a, select_sample(list(reversed(refs)), "s1", 5)); self.assertEqual(len(set(a)), 5)
        self.assertNotEqual(a, select_sample(refs, "s2", 5)); self.assertEqual(select_sample(refs, "s1", 99), refs)


class Policy(Base):
    def test_defaults_set_and_validation(self):
        self.assertEqual(self.svc.ia_get_policy(ORG)["emergency_ratify_days"], 5)
        self.assertEqual(self.svc.ia_set_policy(ORG, {"emergency_ratify_days": 2, "retest_days": 90}, U2)["retest_days"], 90)
        for bad in ({"emergency_ratify_days": 61}, {"retest_days": 10}, {"emergency_ratify_days": "x"}, {"retest_days": True}):
            with self.assertRaises(ItAuditError): self.svc.ia_set_policy(ORG, bad, U2)

    def test_window_is_fixed_on_the_record_when_recorded(self):
        c = self.change(change_type="EMERGENCY", approved_on="2026-02-06", implemented_on="2026-02-03", n="a")
        self.assertEqual(c["ratify_days"], 5); self.assertEqual(c["flags"], [])
        self.svc.ia_set_policy(ORG, {"emergency_ratify_days": 1}, U2)
        self.assertEqual(self.svc.ia_get_change(ORG, c["id"])["flags"], [])


class Changes(Base):
    def test_clean_change_has_no_flags_and_numbered_ref(self):
        c = self.change(); self.assertEqual(c["ref"], "CH-001"); self.assertEqual(c["flags"], []); self.assertEqual(self.change(n="b")["ref"], "CH-002")

    def test_each_flag(self):
        self.assertEqual(self.change(approved_by_name="", approved_on="", n="1")["flags"], ["NO_APPROVAL"])
        self.assertIn("APPROVED_AFTER_GO_LIVE", self.change(approved_on="2026-02-05", n="2")["flags"])
        self.assertIn("SELF_APPROVED", self.change(approved_by_name="ada", n="3")["flags"])
        self.assertIn("NO_TESTING_EVIDENCE", self.change(testing_evidence="", n="4")["flags"])
        self.assertIn("NO_ROLLBACK_PLAN", self.change(risk="HIGH", rollback_plan="", n="5")["flags"])
        self.assertNotIn("NO_ROLLBACK_PLAN", self.change(risk="LOW", rollback_plan="", n="6")["flags"])
        self.assertEqual(self.change(change_type="STANDARD", testing_evidence="", n="7")["flags"], [])

    def test_emergency_ratification_window(self):
        self.assertEqual(self.change(change_type="EMERGENCY", approved_on="2026-02-08", n="1")["flags"], [])
        self.assertIn("EMERGENCY_RATIFIED_LATE", self.change(change_type="EMERGENCY", approved_on="2026-02-09", n="2")["flags"])
        self.assertEqual(self.change(change_type="EMERGENCY", approved_on="2026-02-03", n="3")["flags"], [])

    def test_validation(self):
        bad = [dict(system=""), dict(change_type="BIG"), dict(risk="x"), dict(title="abc"), dict(description="short"), dict(requested_by=""), dict(ticket_ref=""),
               dict(implemented_on="2026-13-01"), dict(implemented_on="2026-03-01"), dict(approved_on="2026-03-01"), dict(approved_on=""), dict(approved_by_name=""),
               dict(testing_evidence="short"), dict(evidence_ids=["nope"]), dict(asset_id="zzz")]
        for i, b in enumerate(bad):
            with self.assertRaises(ItAuditError, msg=str(b)): self.change(n=f"v{i}", **b)
        self.assertEqual(self.svc.ia_overview(ORG)["counts"]["changes"], 0)

    def test_failed_validation_does_not_burn_a_reference(self):
        with self.assertRaises(ItAuditError): self.change(title="abc")
        self.assertEqual(self.change(n="ok")["ref"], "CH-001")

    def test_duplicate_ticket_for_same_system_refused(self):
        self.change(ticket_ref="CHG-1"); 
        with self.assertRaises(ItAuditStateError): self.change(ticket_ref="chg-1")
        self.assertEqual(self.change(ticket_ref="CHG-1", system="Billing")["system"], "Billing")

    def test_evidence_and_asset_links(self):
        self.assertEqual(self.change(evidence_ids=["ev1", "ev1"], n="e")["evidence"][0]["evidence_id"], "ev1")
        self.w.store.put("cy_asset", f"{ORG}:a1", {"id": "a1", "org": ORG, "ref": "AS-001", "name": "Payroll server", "status": "ACTIVE"}, org_id=ORG)
        self.w.store.put("cy_asset", f"{OTHER}:a2", {"id": "a2", "org": OTHER, "ref": "AS-001", "name": "Other", "status": "ACTIVE"}, org_id=OTHER)
        self.assertEqual(self.change(asset_id="a1", n="a")["asset_name"], "Payroll server")
        with self.assertRaises(ItAuditError): self.change(asset_id="a2", n="b")
        self.assertEqual([a["id"] for a in self.svc.ia_options(ORG)["assets"]], ["a1"])

    def test_list_filters_and_void(self):
        a = self.change(n="a"); b = self.change(approved_by_name="", approved_on="", system="Billing", n="b")
        self.assertEqual([c["ref"] for c in self.svc.ia_list_changes(ORG, flagged=True)], [b["ref"]]); self.assertEqual(len(self.svc.ia_list_changes(ORG, system="payroll")), 1)
        with self.assertRaises(ItAuditForbiddenError): self.svc.ia_void_change(ORG, b["id"], "Entered in error by mistake", U1)
        self.assertEqual(self.svc.ia_void_change(ORG, b["id"], "Entered in error by mistake", U3)["status"], "VOIDED")
        with self.assertRaises(ItAuditStateError): self.svc.ia_void_change(ORG, b["id"], "Entered in error by mistake", U3)
        with self.assertRaises(ItAuditError): self.svc.ia_void_change(ORG, a["id"], "short", U3)
        self.assertEqual(len(self.svc.ia_list_changes(ORG, status="RECORDED")), 1)


class ChangeTests(Base):
    def seed(self, n=5):
        for i in range(n): self.change(n=f"s{i}", implemented_on="2026-02-03")

    def test_population_validation(self):
        with self.assertRaises(ItAuditError): self.ptest()
        self.seed()
        for bad in (dict(period_to="2026-01-01"), dict(period_to="2026-03-30"), dict(sample_size=0), dict(sample_size=101), dict(seed="a"), dict(title="abc"), dict(system="Nothing"), dict(tolerable=21)):
            with self.assertRaises(ItAuditError, msg=str(bad)): self.ptest(**bad)

    def test_sample_is_repeatable_snapshotted_and_capped(self):
        self.seed(); t1 = self.ptest(); t2 = self.ptest()
        self.assertEqual([i["ref"] for i in t1["items"]], [i["ref"] for i in t2["items"]]); self.assertEqual(t1["population_fingerprint"], t2["population_fingerprint"])
        self.assertEqual(len(self.ptest(sample_size=50)["items"]), 5); self.assertEqual(t1["population_count"], 5)
        self.assertEqual(t1["ref"], "TS-001"); self.assertEqual(t1["items"][0]["snapshot"]["recorded_by"], U1)

    def test_voided_and_out_of_period_changes_excluded(self):
        self.seed(3); x = self.change(n="out", implemented_on="2026-01-10", approved_on="2026-01-05"); v = self.change(n="void"); self.svc.ia_void_change(ORG, v["id"], "Entered in error by mistake", U3)
        t = self.ptest(sample_size=10); refs = {i["ref"] for i in t["items"]}
        self.assertEqual(t["population_count"], 4 - 0 - 0 if False else 3 + 0); self.assertNotIn(x["ref"], refs); self.assertNotIn(v["ref"], refs)

    def test_tester_cannot_test_own_record_and_only_planner_works(self):
        self.seed()
        with self.assertRaises(ItAuditForbiddenError): self.ptest(actor=U1)               # the sample would include changes U1 recorded
        self.assertEqual(self.svc.ia_overview(ORG)["counts"]["tests"], 0)                # and no reference was used up
        t = self.ptest(actor=U2); self.assertEqual(t["ref"], "TS-001")
        with self.assertRaises(ItAuditForbiddenError): self.svc.ia_conclude_item(ORG, t["id"], t["items"][0]["id"], {"result": "NO_EXCEPTION"}, U3)
        with self.assertRaises(ItAuditNotFoundError): self.svc.ia_conclude_item(ORG, t["id"], "nope", {"result": "NO_EXCEPTION"}, U2)

    def test_conclusion_rules_for_flagged_and_clean_items(self):
        self.change(approved_by_name="", approved_on="", n="f"); self.change(n="c"); t = self.ptest(sample_size=2); fl = next(i for i in t["items"] if i["flags"]); cl = next(i for i in t["items"] if not i["flags"])
        with self.assertRaises(ItAuditError): self.svc.ia_conclude_item(ORG, t["id"], fl["id"], {"result": "NO_EXCEPTION", "note": "too short"}, U2)
        with self.assertRaises(ItAuditError): self.svc.ia_conclude_item(ORG, t["id"], cl["id"], {"result": "EXCEPTION"}, U2)
        with self.assertRaises(ItAuditError): self.svc.ia_conclude_item(ORG, t["id"], cl["id"], {"result": "MAYBE"}, U2)
        with self.assertRaises(ItAuditError): self.svc.ia_conclude_item(ORG, t["id"], cl["id"], {"result": "NO_EXCEPTION", "note": "tiny"}, U2)
        t = self.svc.ia_conclude_item(ORG, t["id"], fl["id"], {"result": "NO_EXCEPTION", "note": "Approval was given by email, copy filed under ticket"}, U2)
        self.assertEqual(t["overrides"], 1); t = self.svc.ia_conclude_item(ORG, t["id"], cl["id"], {"result": "EXCEPTION", "note": "Testing evidence missing"}, U2)
        self.assertEqual((t["exceptions"], t["concluded"]), (1, 2))

    def test_submit_needs_all_items_and_approval_rules(self):
        self.seed(); t = self.ptest()
        with self.assertRaises(ItAuditStateError): self.svc.ia_submit_test(ORG, t["id"], U2)
        t = self.conclude_all(t)
        with self.assertRaises(ItAuditForbiddenError): self.svc.ia_submit_test(ORG, t["id"], U3)
        self.svc.ia_submit_test(ORG, t["id"], U2)
        with self.assertRaises(ItAuditStateError): self.svc.ia_conclude_item(ORG, t["id"], t["items"][0]["id"], {"result": "NO_EXCEPTION"}, U2)
        with self.assertRaises(ItAuditForbiddenError): self.svc.ia_approve_test(ORG, t["id"], U2)
        with self.assertRaises(ItAuditForbiddenError): self.svc.ia_approve_test(ORG, t["id"], U1)   # recorded the sampled changes
        a = self.svc.ia_approve_test(ORG, t["id"], U3); self.assertEqual((a["status"], a["conclusion"], a["approved_by"]), ("APPROVED", "WITHIN_TOLERANCE", U3))
        with self.assertRaises(ItAuditStateError): self.svc.ia_approve_test(ORG, t["id"], U3)

    def test_exceptions_need_a_note_and_tolerance_is_arithmetic(self):
        self.seed(); t = self.ptest(tolerable=1); ids = [i["id"] for i in t["items"]]
        self.svc.ia_conclude_item(ORG, t["id"], ids[0], {"result": "EXCEPTION", "note": "No evidence of testing found"}, U2)
        for i in ids[1:]: self.svc.ia_conclude_item(ORG, t["id"], i, {"result": "NO_EXCEPTION"}, U2)
        self.svc.ia_submit_test(ORG, t["id"], U2)
        with self.assertRaises(ItAuditError): self.svc.ia_approve_test(ORG, t["id"], U3)
        self.assertEqual(self.svc.ia_approve_test(ORG, t["id"], U3, "Exception reported to the change manager")["conclusion"], "WITHIN_TOLERANCE")
        t = self.ptest(tolerable=0)
        self.svc.ia_conclude_item(ORG, t["id"], t["items"][0]["id"], {"result": "EXCEPTION", "note": "No evidence of testing found"}, U2)
        for i in t["items"][1:]: self.svc.ia_conclude_item(ORG, t["id"], i["id"], {"result": "NO_EXCEPTION"}, U2)
        self.svc.ia_submit_test(ORG, t["id"], U2); self.assertEqual(self.svc.ia_approve_test(ORG, t["id"], U3, "Reported to the change manager")["conclusion"], "ABOVE_TOLERANCE")

    def test_override_needs_approval_note_and_reject_returns_to_draft(self):
        self.change(approved_by_name="", approved_on="", n="f"); t = self.ptest(sample_size=1)
        self.svc.ia_conclude_item(ORG, t["id"], t["items"][0]["id"], {"result": "NO_EXCEPTION", "note": "Approval was given by email, filed under ticket"}, U2); self.svc.ia_submit_test(ORG, t["id"], U2)
        with self.assertRaises(ItAuditError): self.svc.ia_approve_test(ORG, t["id"], U3)
        with self.assertRaises(ItAuditForbiddenError): self.svc.ia_reject_test(ORG, t["id"], "Please attach the email", U2)
        with self.assertRaises(ItAuditError): self.svc.ia_reject_test(ORG, t["id"], "no", U3)
        r = self.svc.ia_reject_test(ORG, t["id"], "Please attach the email", U3); self.assertEqual((r["status"], r["rejected_note"]), ("DRAFT", "Please attach the email"))
        self.svc.ia_submit_test(ORG, t["id"], U2); self.assertEqual(self.svc.ia_approve_test(ORG, t["id"], U3, "Email approval verified against the filed copy")["status"], "APPROVED")

    def test_change_in_open_test_cannot_be_voided(self):
        c = self.change(); t = self.ptest(sample_size=1)
        with self.assertRaises(ItAuditStateError): self.svc.ia_void_change(ORG, c["id"], "Entered in error by mistake", U3)

    def test_kind_mismatch_refused(self):
        self.seed(); t = self.ptest()
        with self.assertRaises(ItAuditStateError): self.case(t)


class Withdraw(Base):
    def test_planner_can_withdraw_a_draft_and_it_releases_changes_and_controls(self):
        c = self.change(); t = self.ptest(sample_size=1)
        with self.assertRaises(ItAuditStateError): self.svc.ia_void_change(ORG, c["id"], "Entered in error by mistake", U3)
        with self.assertRaises(ItAuditForbiddenError): self.svc.ia_withdraw_test(ORG, t["id"], "Planned by mistake today", U3)
        with self.assertRaises(ItAuditError): self.svc.ia_withdraw_test(ORG, t["id"], "short", U2)
        w = self.svc.ia_withdraw_test(ORG, t["id"], "Planned by mistake today", U2); self.assertEqual((w["status"], w["rejected_note"]), ("WITHDRAWN", "Planned by mistake today"))
        self.assertEqual(self.svc.ia_void_change(ORG, c["id"], "Entered in error by mistake", U3)["status"], "VOIDED")
        for f in (lambda: self.svc.ia_withdraw_test(ORG, t["id"], "Planned by mistake today", U2), lambda: self.svc.ia_submit_test(ORG, t["id"], U2), lambda: self.svc.ia_approve_test(ORG, t["id"], U3)):
            with self.assertRaises(ItAuditStateError): f()
        k = self.control(); kt = self.ctest(k); self.svc.ia_withdraw_test(ORG, kt["id"], "Wrong control picked", U2)
        self.assertEqual(self.ctest(k)["status"], "DRAFT")

    def test_submitted_test_cannot_be_withdrawn(self):
        self.change(); t = self.conclude_all(self.ptest(sample_size=1)); self.svc.ia_submit_test(ORG, t["id"], U2)
        with self.assertRaises(ItAuditStateError): self.svc.ia_withdraw_test(ORG, t["id"], "Changed my mind about it", U2)

    def test_withdrawal_is_audited_without_the_reason(self):
        self.change(); t = self.ptest(sample_size=1); self.svc.ia_withdraw_test(ORG, t["id"], "Planned by mistake today", U2)
        self.assertIn("ITAUDIT_TEST_WITHDRAWN", [e[0] for e in self.events]); self.assertNotIn("mistake", " ".join(str(e) for e in self.events))


class Controls(Base):
    def test_define_validate_duplicate_and_ref(self):
        c = self.control(); self.assertEqual((c["ref"], c["retest_due"], c["tests"]), ("AC-001", True, 0))
        with self.assertRaises(ItAuditStateError): self.control(name="duplicate PAYEE check")
        for bad in (dict(name="abc", system="Billing"), dict(control_type="X", name="Another one"), dict(frequency="x", name="Another two"), dict(tolerable=21, name="Another three"), dict(expected_result="", name="Another four"), dict(tolerable="-1", name="Another five")):
            with self.assertRaises(ItAuditError, msg=str(bad)): self.control(**bad)
        self.assertEqual(self.control(name="Another good", tolerable="")["tolerable"], 0)

    def test_test_lifecycle_and_roles(self):
        c = self.control(); t = self.ctest(c)
        with self.assertRaises(ItAuditForbiddenError): self.ctest(c, actor=U1)
        with self.assertRaises(ItAuditStateError): self.ctest(c)
        with self.assertRaises(ItAuditStateError): self.svc.ia_retire_control(ORG, c["id"], "No longer in use anywhere", U3)
        with self.assertRaises(ItAuditStateError): self.svc.ia_submit_test(ORG, t["id"], U2)
        with self.assertRaises(ItAuditError): self.case(t, result="FAIL")
        with self.assertRaises(ItAuditError): self.case(t, performed_on="2026-03-30")
        with self.assertRaises(ItAuditError): self.case(t, evidence_ids=["nope"])
        t = self.case(t, evidence_ids=["ev1"]); self.assertEqual((t["concluded"], t["exceptions"]), (1, 0))
        with self.assertRaises(ItAuditStateError): self.svc.ia_conclude_item(ORG, t["id"], "x", {"result": "NO_EXCEPTION"}, U2)
        self.svc.ia_submit_test(ORG, t["id"], U2)
        with self.assertRaises(ItAuditForbiddenError): self.svc.ia_approve_test(ORG, t["id"], U1)   # defined the control
        a = self.svc.ia_approve_test(ORG, t["id"], U3); self.assertEqual(a["conclusion"], "WITHIN_TOLERANCE")
        v = self.svc.ia_get_control(ORG, c["id"]); self.assertEqual((v["tests"], v["last_conclusion"], v["last_tested_on"], v["retest_due"]), (1, "WITHIN_TOLERANCE", "2026-02-15", False))

    def test_failure_above_tolerance_and_retest_due(self):
        c = self.control(); t = self.ctest(c); self.case(t, result="FAIL", note="Duplicate payee was accepted"); self.svc.ia_submit_test(ORG, t["id"], U2)
        with self.assertRaises(ItAuditError): self.svc.ia_approve_test(ORG, t["id"], U3)
        self.assertEqual(self.svc.ia_approve_test(ORG, t["id"], U3, "Reported to the payroll manager")["conclusion"], "ABOVE_TOLERANCE")
        self.clock.d = date(2027, 3, 1); self.assertTrue(self.svc.ia_get_control(ORG, c["id"])["retest_due"])

    def test_retire_and_retired_cannot_be_tested(self):
        c = self.control()
        with self.assertRaises(ItAuditError): self.svc.ia_retire_control(ORG, c["id"], "short", U3)
        self.assertEqual(self.svc.ia_retire_control(ORG, c["id"], "Replaced by a new system", U3)["status"], "RETIRED")
        with self.assertRaises(ItAuditStateError): self.svc.ia_retire_control(ORG, c["id"], "Replaced by a new system", U3)
        with self.assertRaises(ItAuditStateError): self.ctest(c)
        self.assertEqual(self.control()["ref"], "AC-002")

    def test_unknown_control(self):
        with self.assertRaises(ItAuditNotFoundError): self.svc.ia_plan_control_test(ORG, {"title": "Test of something", "control_id": "nope"}, U2)


class Overview(Base):
    def test_attention_items_and_counts(self):
        self.change(approved_by_name="", approved_on="", n="f"); self.change(change_type="EMERGENCY", approved_on="2026-02-12", n="e"); self.control()
        o = self.svc.ia_overview(ORG); kinds = {a["kind"]: a["count"] for a in o["attention"]}
        self.assertEqual(kinds["CHANGES_FLAGGED_UNTESTED"], 2); self.assertEqual(kinds["EMERGENCY_CHANGES_FLAGGED"], 1); self.assertEqual(kinds["CONTROLS_NEVER_TESTED"], 1)
        self.assertEqual(o["counts"]["changes_by_type"]["EMERGENCY"], 1); self.assertTrue(o["limitations"])
        t = self.ptest(sample_size=2)
        for i in t["items"]: self.svc.ia_conclude_item(ORG, t["id"], i["id"], {"result": "EXCEPTION", "note": "Not acceptable as recorded"}, U2)
        self.svc.ia_submit_test(ORG, t["id"], U2); kinds = {a["kind"] for a in self.svc.ia_overview(ORG)["attention"]}
        self.assertIn("TESTS_TO_APPROVE", kinds); self.assertNotIn("CHANGES_FLAGGED_UNTESTED", kinds)

    def test_empty(self):
        o = self.svc.ia_overview(ORG); self.assertEqual(o["attention"], []); self.assertEqual(o["counts"]["tests"], 0)


class Isolation(Base):
    def test_other_org_sees_nothing_and_cannot_touch(self):
        c = self.change(); k = self.control(); t = self.ctest(k)
        self.assertEqual(self.svc.ia_list_changes(OTHER), []); self.assertEqual(self.svc.ia_list_controls(OTHER), []); self.assertEqual(self.svc.ia_list_tests(OTHER), [])
        for f in (lambda: self.svc.ia_get_change(OTHER, c["id"]), lambda: self.svc.ia_get_control(OTHER, k["id"]), lambda: self.svc.ia_get_test(OTHER, t["id"]),
                  lambda: self.svc.ia_void_change(OTHER, c["id"], "Entered in error by mistake", U3), lambda: self.svc.ia_approve_test(OTHER, t["id"], U3),
                  lambda: self.svc.ia_plan_control_test(OTHER, {"title": "Test of something", "control_id": k["id"]}, U2)):
            with self.assertRaises(ItAuditNotFoundError): f()
        self.assertEqual(self.svc.ia_get_policy(OTHER)["emergency_ratify_days"], 5)

    def test_same_ticket_in_other_org_allowed(self):
        self.change(ticket_ref="CHG-1"); self.assertEqual(self.change(org=OTHER, ticket_ref="CHG-1")["ref"], "CH-001")


class Audit(Base):
    def test_every_write_is_logged_without_content(self):
        c = self.change(); k = self.control(); t = self.ctest(k); self.case(t); self.svc.ia_submit_test(ORG, t["id"], U2); self.svc.ia_approve_test(ORG, t["id"], U3)
        self.svc.ia_set_policy(ORG, {"retest_days": 100}, U3); self.svc.ia_void_change(ORG, c["id"], "Entered in error by mistake", U3)
        acts = [e[0] for e in self.events]
        for a in ("ITAUDIT_CHANGE_RECORDED", "ITAUDIT_CONTROL_DEFINED", "ITAUDIT_TEST_PLANNED", "ITAUDIT_CASE_ADDED", "ITAUDIT_TEST_SUBMITTED", "ITAUDIT_TEST_APPROVED", "ITAUDIT_POLICY_SET", "ITAUDIT_CHANGE_VOIDED"): self.assertIn(a, acts)
        blob = " ".join(str(e) for e in self.events); self.assertNotIn("tax tables", blob); self.assertNotIn("Entered in error", blob); self.assertNotIn("bank account", blob)

    def test_failed_actions_are_not_logged(self):
        with self.assertRaises(ItAuditError): self.change(title="abc")
        self.assertEqual(self.events, [])


class Permissions(unittest.TestCase):
    def test_roles(self):
        has = lambda r, p: p in ROLE_PERMISSIONS[r]
        for r in (Role.OWNER, Role.ADMINISTRATOR, Role.MANAGER, Role.AUDITOR): self.assertTrue(has(r, ITAUDIT_PREPARE), r)
        for r in (Role.OWNER, Role.APPROVER, Role.MANAGER): self.assertTrue(has(r, ITAUDIT_APPROVE), r)
        for r in (Role.ACCOUNTANT, Role.REVIEWER, Role.EXTERNAL_AUDITOR, Role.READ_ONLY, Role.DONOR, Role.REGULATOR, Role.INVESTOR_REVIEWER):
            self.assertFalse(has(r, ITAUDIT_PREPARE) or has(r, ITAUDIT_APPROVE), r)

    def test_anyone_who_can_prepare_or_approve_can_view(self):
        for r, perms in ROLE_PERMISSIONS.items():
            if ITAUDIT_PREPARE in perms or ITAUDIT_APPROVE in perms: self.assertIn(AUDIT_READ, perms, r)


class RouterGuards(unittest.TestCase):
    SRC = os.path.join(os.path.dirname(__file__), "..", "src", "asavexa", "api", "routers", "itaudit.py")

    def test_every_write_has_the_right_guard(self):
        tree = ast.parse(open(self.SRC).read()); named = {"_prepare": "ITAUDIT_PREPARE", "_approve": "ITAUDIT_APPROVE"}; g = {}
        for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.decorator_list]:
            verbs, guards = set(), set()
            for dec in fn.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute): verbs.add(dec.func.attr)
                for kw in getattr(dec, "keywords", []):
                    if kw.arg == "dependencies": guards |= {named[e.id] for e in kw.value.elts if isinstance(e, ast.Name) and e.id in named}
            g[fn.name] = (verbs, guards)
        approve = {"set_policy", "void_change", "retire_control", "approve_test", "reject_test"}
        prepare = {"record_change", "define_control", "plan_change_test", "plan_control_test", "conclude_item", "add_case", "submit_test", "withdraw_test"}
        for n in approve: self.assertEqual(g[n][1], {"ITAUDIT_APPROVE"}, n)
        for n in prepare: self.assertEqual(g[n][1], {"ITAUDIT_PREPARE"}, n)
        for n, (verbs, guards) in g.items():
            if verbs == {"get"}: self.assertEqual(guards, set(), n)
            else: self.assertIn(n, approve | prepare, f"{n} writes but has no itaudit guard")
        src = open(self.SRC).read(); self.assertIn("dependencies=[Depends(require_permission(AUDIT_READ))]", src); self.assertNotIn("org_id", src)


if __name__ == "__main__":
    unittest.main()
