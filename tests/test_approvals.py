"""Approval workflows: policies with up to three steps, requests that move through them, different-person rules, no double decisions, isolation, audit and permissions."""
import ast
import os
import unittest
from datetime import date, datetime, timedelta, timezone

from analysis_fixture import ORG, OTHER, World
from asavexa.approvals.errors import ApprovalsError, ApprovalsForbiddenError, ApprovalsNotFoundError, ApprovalsStateError
from asavexa.approvals.service import ApprovalsService
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.permissions import APW_APPROVE, APW_PREPARE, AUDIT_READ, ROLE_PERMISSIONS

U1, U2, U3, U4, U5, U6 = "user-1", "user-2", "user-3", "user-4", "user-5", "user-6"   # U1 and U2 prepare, U3 to U6 approve


class Clock:
    def __init__(self): self.d = date(2026, 3, 31)
    def __call__(self): return datetime(self.d.year, self.d.month, self.d.day, 9, tzinfo=timezone.utc)


class Base(unittest.TestCase):
    def setUp(self):
        self.w = World(); self.clock = Clock(); self.events = []
        self.svc = ApprovalsService(self.w.store, None, log=lambda *a: self.events.append(a), now=self.clock)

    def policy(self, actor=U1, **kw):
        d = dict(name="Payments over limit", request_kind="PAYMENT", steps=[{"label": "Finance review", "required": 1}, {"label": "Director sign-off", "required": 2}], description="Large payments need two stages of review"); d.update(kw)
        return self.svc.apw_add_policy(ORG, d, actor)

    def active(self, actor=U1, approver=U3, **kw):
        p = self.policy(actor, **kw); return self.svc.apw_activate_policy(ORG, p["id"], {}, approver)

    def request(self, p, actor=U1, **kw):
        d = dict(policy_id=p["id"], title="Supplier payment", request_ref="PAY-1", amount="2500000", currency="NGN", description="Quarterly supplier payment run"); d.update(kw)
        return self.svc.apw_submit_request(ORG, d, actor)

    def ok(self, x, actor, note=None):
        return self.svc.apw_decide(ORG, x["id"], True, {"note": note} if note else {}, actor)

    def no(self, x, actor, reason="The invoice does not match the order"):
        return self.svc.apw_decide(ORG, x["id"], False, reason, actor)


class Policies(Base):
    def test_validation(self):
        bad = [dict(name="ab"), dict(request_kind="SPACE"), dict(description="short"), dict(steps=[]), dict(steps="x"), dict(steps=None), dict(steps=[{"label": "A", "required": 1}]),
               dict(steps=[{"label": "Review", "required": 0}]), dict(steps=[{"label": "Review", "required": 6}]), dict(steps=[{"label": "Review", "required": 1.5}]), dict(steps=[{"label": "Review", "required": True}]),
               dict(steps=["Review"]), dict(steps=[{"label": "Review one", "required": 1}] * 2), dict(steps=[{"label": f"Step {i}", "required": 1} for i in range(4)])]
        for kw in bad:
            with self.assertRaises(ApprovalsError, msg=str(kw)): self.policy(**kw)

    def test_proposed_then_decided_by_a_different_person(self):
        p = self.policy(); self.assertEqual((p["status"], p["ref"], p["people_per_request"]), ("PROPOSED", "AP-001", 3))
        with self.assertRaises(ApprovalsForbiddenError): self.svc.apw_activate_policy(ORG, p["id"], {}, U1)
        with self.assertRaises(ApprovalsForbiddenError): self.svc.apw_reject_policy(ORG, p["id"], "Not needed any more", U1)
        a = self.svc.apw_activate_policy(ORG, p["id"], {"note": "Matches our delegation of authority"}, U3); self.assertEqual((a["status"], a["decided_by"]), ("ACTIVE", U3))
        with self.assertRaises(ApprovalsStateError): self.svc.apw_activate_policy(ORG, p["id"], {}, U4)
        q = self.policy(name="Another policy"); r = self.svc.apw_reject_policy(ORG, q["id"], "Duplicate of the payments policy", U3); self.assertEqual(r["status"], "REJECTED")
        with self.assertRaises(ApprovalsError): self.svc.apw_reject_policy(ORG, self.policy(name="Third")["id"], "short", U3)

    def test_duplicate_names_and_retirement(self):
        p = self.active()
        with self.assertRaises(ApprovalsStateError): self.policy(name="payments OVER limit")
        with self.assertRaises(ApprovalsStateError): self.svc.apw_retire_policy(ORG, self.policy(name="Never active")["id"], "Not used by anyone", U3)
        with self.assertRaises(ApprovalsError): self.svc.apw_retire_policy(ORG, p["id"], "short", U3)
        r = self.svc.apw_retire_policy(ORG, p["id"], "Replaced by a new delegation of authority", U3); self.assertEqual(r["status"], "RETIRED")
        self.assertEqual(self.policy()["status"], "PROPOSED")                                              # the name is free again
        with self.assertRaises(ApprovalsStateError): self.request(p)

    def test_list_and_filter(self):
        a = self.active(); self.policy(name="Waiting policy"); ls = self.svc.apw_list_policies(ORG)
        self.assertEqual([x["ref"] for x in ls], ["AP-001", "AP-002"]); self.assertTrue(all(x["history"] == [] for x in ls))
        self.assertEqual([x["ref"] for x in self.svc.apw_list_policies(ORG, "ACTIVE")], ["AP-001"])
        self.assertTrue(self.svc.apw_get_policy(ORG, a["id"])["history"])


class Requests(Base):
    def test_full_path_through_two_steps(self):
        p = self.active(); x = self.request(p)
        self.assertEqual((x["status"], x["ref"], x["current_step"], x["current_label"], x["still_needed"], x["approvals_in_total"]), ("PENDING", "AR-001", 1, "Finance review", 1, 3))
        x = self.ok(x, U3, "Invoice matches the order"); self.assertEqual((x["current_step"], x["current_label"], x["still_needed"], x["status"]), (2, "Director sign-off", 2, "PENDING"))
        x = self.ok(x, U4); self.assertEqual((x["current_step"], x["still_needed"], x["approvals_so_far"]), (2, 1, 2))
        x = self.ok(x, U5); self.assertEqual((x["status"], x["current_step"], x["current_label"], x["decided_by"], x["approvals_so_far"]), ("APPROVED", None, None, U5, 3))
        self.assertEqual([h["event"] for h in x["history"]], ["SUBMITTED", "STEP_1_PASSED", "STEP_2_APPROVAL", "APPROVED"])
        with self.assertRaises(ApprovalsStateError): self.ok(x, U6)

    def test_submitter_can_never_decide_even_with_approve_rights(self):
        p = self.active(); x = self.request(p, U3)
        with self.assertRaises(ApprovalsForbiddenError): self.ok(x, U3)
        with self.assertRaises(ApprovalsForbiddenError): self.no(x, U3)

    def test_one_person_cannot_decide_twice_across_steps(self):
        p = self.active(); x = self.request(p); x = self.ok(x, U3)
        with self.assertRaises(ApprovalsForbiddenError): self.ok(x, U3)
        with self.assertRaises(ApprovalsForbiddenError): self.no(x, U3)
        x = self.ok(x, U4)
        with self.assertRaises(ApprovalsForbiddenError): self.ok(x, U3)
        with self.assertRaises(ApprovalsForbiddenError): self.ok(x, U4)
        self.assertEqual(self.svc.apw_get_request(ORG, x["id"])["still_needed"], 1)

    def test_rejection_ends_it_with_the_reason(self):
        p = self.active(); x = self.request(p); x = self.ok(x, U3); x = self.no(x, U4, "The second quote is missing")
        self.assertEqual((x["status"], x["current_step"], x["decision_note"], x["decided_by"]), ("REJECTED", None, "The second quote is missing", U4))
        with self.assertRaises(ApprovalsStateError): self.ok(x, U5)
        with self.assertRaises(ApprovalsError): self.no(self.request(p, request_ref="PAY-2"), U3, "short")

    def test_single_step_single_approval(self):
        p = self.active(name="Small spend", steps=[{"label": "Manager", "required": 1}]); x = self.ok(self.request(p), U3)
        self.assertEqual(x["status"], "APPROVED")

    def test_three_steps_with_five_approvals_needs_exactly_the_right_number(self):
        p = self.active(name="Big", steps=[{"label": "One", "required": 5}, {"label": "Two", "required": 1}, {"label": "Three", "required": 1}]); x = self.request(p)
        for i in range(5): x = self.ok(x, f"approver-{i}")
        self.assertEqual((x["current_step"], x["status"]), (2, "PENDING")); x = self.ok(x, "approver-9"); x = self.ok(x, "approver-10"); self.assertEqual(x["status"], "APPROVED")

    def test_snapshot_survives_retiring_the_policy(self):
        p = self.active(); x = self.request(p); self.svc.apw_retire_policy(ORG, p["id"], "Replaced by a new delegation", U4)
        x = self.ok(x, U3); self.assertEqual((x["current_step"], x["policy_name"]), (2, "Payments over limit"))
        self.assertEqual(self.svc.apw_get_policy(ORG, p["id"])["requests_under_way"], 1)

    def test_withdraw(self):
        p = self.active(); x = self.request(p)
        with self.assertRaises(ApprovalsForbiddenError): self.svc.apw_withdraw(ORG, x["id"], "I changed my mind about it", U2)
        with self.assertRaises(ApprovalsForbiddenError): self.svc.apw_withdraw(ORG, x["id"], "I changed my mind about it", U3)
        with self.assertRaises(ApprovalsError): self.svc.apw_withdraw(ORG, x["id"], "short", U1)
        w = self.svc.apw_withdraw(ORG, x["id"], "Duplicate of an earlier request", U1); self.assertEqual((w["status"], w["current_step"]), ("WITHDRAWN", None))
        with self.assertRaises(ApprovalsStateError): self.svc.apw_withdraw(ORG, x["id"], "Trying to withdraw twice", U1)
        with self.assertRaises(ApprovalsStateError): self.ok(w, U3)

    def test_validation_and_amounts(self):
        p = self.active()
        for kw in (dict(policy_id=""), dict(policy_id=None), dict(policy_id=5), dict(policy_id="nope"), dict(title="ab"), dict(request_ref="x"), dict(description="short"), dict(amount="12.345"), dict(amount="abc"), dict(amount=12.5), dict(amount="0"),
                   dict(amount="-5"), dict(currency="NAIRA"), dict(currency=None), dict(amount=None)):
            with self.assertRaises(ApprovalsError, msg=str(kw)): self.request(p, **kw)
        n = self.request(p, amount=None, currency=None, request_ref="NOAMT"); self.assertEqual((n["amount"], n["currency"]), (None, None))
        e = self.request(p, amount="", currency="", request_ref="EMPTY"); self.assertIsNone(e["amount"])
        big = self.request(p, amount="1,234,567.89", currency="usd", request_ref="BIG"); self.assertEqual((big["amount"], big["currency"]), ("1234567.89", "USD"))
        with self.assertRaises(ApprovalsNotFoundError): self.svc.apw_submit_request(ORG, dict(policy_id="x" * 40, title="Supplier payment", request_ref="PAY", description="Quarterly supplier payment run"), U1)

    def test_a_proposed_policy_takes_no_requests(self):
        p = self.policy()
        with self.assertRaises(ApprovalsStateError): self.request(p)

    def test_waiting_flags_follow_the_setting(self):
        p = self.active(); x = self.request(p); self.assertEqual((x["waiting_days"], x["stale"]), (0, False))
        self.clock.d += timedelta(days=5); y = self.svc.apw_get_request(ORG, x["id"]); self.assertEqual((y["waiting_days"], y["stale"]), (5, True))
        self.svc.apw_set_setting(ORG, {"stale_days": 10}, U3); self.assertFalse(self.svc.apw_get_request(ORG, x["id"])["stale"])
        self.clock.d += timedelta(days=6); self.assertTrue(self.svc.apw_get_request(ORG, x["id"])["stale"])
        done = self.no(x, U3); self.assertEqual((done["waiting_days"], done["stale"]), (None, False))

    def test_list_is_summary_only_and_filters(self):
        p = self.active(); a = self.request(p); b = self.request(p, request_ref="PAY-2"); self.ok(a, U3)
        ls = self.svc.apw_list_requests(ORG); self.assertEqual([x["ref"] for x in ls], ["AR-001", "AR-002"]); self.assertTrue(all(x["history"] == [] and all(s["decisions"] == [] for s in x["steps"]) for x in ls))
        self.assertEqual(len(self.svc.apw_list_requests(ORG, "PENDING")), 2); self.assertEqual(self.svc.apw_list_requests(ORG, "APPROVED"), [])
        self.assertEqual(len(self.svc.apw_get_request(ORG, a["id"])["steps"][0]["decisions"]), 1); self.assertTrue(b)


class Settings(Base):
    def test_settings(self):
        self.assertEqual(self.svc.apw_get_setting(ORG)["stale_days"], 5)
        self.assertEqual(self.svc.apw_set_setting(ORG, {"stale_days": "12"}, U3)["stale_days"], 12)
        self.assertEqual(self.svc.apw_set_setting(ORG, {}, U3)["stale_days"], 12)
        for bad in (0, 366, "x", 1.5, True, -1):
            with self.assertRaises(ApprovalsError): self.svc.apw_set_setting(ORG, {"stale_days": bad}, U3)


class Overview(Base):
    def test_empty(self):
        o = self.svc.apw_overview(ORG); self.assertEqual([a["kind"] for a in o["attention"]], ["NO_ACTIVE_POLICY"]); self.assertEqual(o["by_currency"], []); self.assertEqual(o["requests"]["pending"], 0)

    def test_counts_attention_and_currencies_never_added(self):
        p = self.active(); self.policy(name="Waiting policy")
        a = self.request(p, amount="100.10", currency="NGN"); self.request(p, amount="200.20", currency="NGN", request_ref="REF-B"); self.request(p, amount="50.05", currency="USD", request_ref="REF-C"); self.request(p, amount=None, currency=None, request_ref="REF-D")
        x = self.request(p, amount="1000", currency="NGN", request_ref="REF-E"); self.no(x, U3); w = self.request(p, request_ref="REF-F", amount="7", currency="GBP"); self.svc.apw_withdraw(ORG, w["id"], "No longer needed at all", U1)
        self.clock.d += timedelta(days=6); o = self.svc.apw_overview(ORG)
        self.assertEqual({a["kind"]: a["count"] for a in o["attention"]}, {"POLICIES_TO_DECIDE": 1, "REQUESTS_WAITING": 4, "REQUESTS_STALE": 4})
        self.assertEqual(o["policies"], {"proposed": 1, "active": 1, "rejected": 0, "retired": 0}); self.assertEqual(o["requests"], {"pending": 4, "approved": 0, "rejected": 1, "withdrawn": 1})
        self.assertEqual(o["pending_by_kind"], {"PAYMENT": 4})
        self.assertEqual({t["currency"]: (t["pending"], t["approved"]) for t in o["by_currency"]}, {"NGN": ("300.30", "0.00"), "USD": ("50.05", "0.00")})
        self.assertTrue(a)

    def test_approved_amounts_move_to_the_approved_column(self):
        p = self.active(steps=[{"label": "Manager", "required": 1}]); x = self.request(p, amount="10.10", currency="NGN"); self.ok(x, U3); self.request(p, amount="5.05", currency="NGN", request_ref="REF-B")
        t = self.svc.apw_overview(ORG)["by_currency"][0]; self.assertEqual((t["pending"], t["approved"]), ("5.05", "10.10"))


class Isolation(Base):
    def test_other_company(self):
        p = self.active(); x = self.request(p); self.assertEqual(self.svc.apw_list_requests(OTHER), []); self.assertEqual(self.svc.apw_list_policies(OTHER), [])
        for f in (lambda: self.svc.apw_get_request(OTHER, x["id"]), lambda: self.svc.apw_decide(OTHER, x["id"], True, {}, U4), lambda: self.svc.apw_withdraw(OTHER, x["id"], "Trying from another company", U1),
                  lambda: self.svc.apw_get_policy(OTHER, p["id"]), lambda: self.svc.apw_activate_policy(OTHER, p["id"], {}, U4), lambda: self.svc.apw_retire_policy(OTHER, p["id"], "Trying from another company", U4),
                  lambda: self.svc.apw_submit_request(OTHER, dict(policy_id=p["id"], title="Supplier payment", request_ref="PAY", description="Quarterly supplier payment run"), U1)):
            with self.assertRaises(ApprovalsNotFoundError): f()
        q = self.svc.apw_add_policy(OTHER, dict(name="Own policy", request_kind="OTHER", steps=[{"label": "Only step", "required": 1}], description="A policy at another company"), U1); self.assertEqual(q["ref"], "AP-001")
        self.assertEqual(self.svc.apw_get_request(ORG, x["id"])["still_needed"], 1)


class Audit(Base):
    def test_every_write_logged_without_content(self):
        p = self.active(name="Secret policy name", description="Secret description of the policy"); x = self.request(p, title="Secret title", request_ref="SECRETREF", amount="9876543.21", description="Secret request description")
        self.ok(x, U3, "Chinedu checked the invoice"); self.ok(x, U4); self.no(x, U5, "Quote was unsigned by the supplier")
        y = self.request(p, request_ref="REF-Y"); self.svc.apw_withdraw(ORG, y["id"], "Supplier cancelled the order", U1)
        q = self.policy(name="Rejected policy"); self.svc.apw_reject_policy(ORG, q["id"], "Duplicate of another policy", U3)
        self.svc.apw_retire_policy(ORG, p["id"], "Replaced by a newer policy", U3); self.svc.apw_set_setting(ORG, {"stale_days": 3}, U3)
        acts = {e[0] for e in self.events}
        for a in ("APPROVALS_POLICY_PROPOSED", "APPROVALS_POLICY_ACTIVATED", "APPROVALS_POLICY_REJECTED", "APPROVALS_POLICY_RETIRED", "APPROVALS_REQUEST_SUBMITTED", "APPROVALS_REQUEST_STEP_APPROVED", "APPROVALS_REQUEST_REJECTED", "APPROVALS_REQUEST_WITHDRAWN", "APPROVALS_SETTING_SET"): self.assertIn(a, acts)
        blob = " ".join(str(e) for e in self.events)
        for secret in ("Secret", "SECRETREF", "9876543", "Chinedu", "unsigned", "Supplier cancelled", "Duplicate of", "Replaced by", "Director sign-off", "Finance review"): self.assertNotIn(secret, blob)

    def test_final_approval_is_logged_as_approved(self):
        p = self.active(steps=[{"label": "Manager", "required": 1}]); self.ok(self.request(p), U3)
        self.assertIn("APPROVALS_REQUEST_APPROVED", {e[0] for e in self.events})

    def test_failed_actions_are_not_logged(self):
        with self.assertRaises(ApprovalsError): self.policy(name="ab")
        p = self.active(); x = self.request(p); n = len(self.events)
        with self.assertRaises(ApprovalsForbiddenError): self.ok(x, U1)
        with self.assertRaises(ApprovalsError): self.no(x, U3, "short")
        with self.assertRaises(ApprovalsStateError): self.request(self.policy(name="Not active"))
        self.assertEqual(len(self.events), n + 1)                                                          # only the policy proposed above


class Permissions(unittest.TestCase):
    def test_roles(self):
        has = lambda r, p: p in ROLE_PERMISSIONS[r]
        for r in (Role.OWNER, Role.ADMINISTRATOR, Role.MANAGER, Role.AUDITOR): self.assertTrue(has(r, APW_PREPARE), r)
        for r in (Role.OWNER, Role.APPROVER, Role.MANAGER): self.assertTrue(has(r, APW_APPROVE), r)
        for r in (Role.ACCOUNTANT, Role.REVIEWER, Role.EXTERNAL_AUDITOR, Role.READ_ONLY, Role.DONOR, Role.REGULATOR, Role.INVESTOR_REVIEWER): self.assertFalse(has(r, APW_PREPARE) or has(r, APW_APPROVE), r)

    def test_anyone_who_can_prepare_or_approve_can_view(self):
        for r, perms in ROLE_PERMISSIONS.items():
            if APW_PREPARE in perms or APW_APPROVE in perms: self.assertIn(AUDIT_READ, perms, r)


class RouterGuards(unittest.TestCase):
    SRC = os.path.join(os.path.dirname(__file__), "..", "src", "asavexa", "api", "routers", "approvals.py")

    def test_every_write_has_the_right_guard(self):
        with open(self.SRC) as fh: src = fh.read()
        tree = ast.parse(src); named = {"_prepare": "APW_PREPARE", "_approve": "APW_APPROVE"}; g = {}
        for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.decorator_list]:
            verbs, guards = set(), set()
            for dec in fn.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute): verbs.add(dec.func.attr)
                for kw in getattr(dec, "keywords", []):
                    if kw.arg == "dependencies": guards |= {named[e.id] for e in kw.value.elts if isinstance(e, ast.Name) and e.id in named}
            g[fn.name] = (verbs, guards)
        approve = {"set_setting", "activate_policy", "reject_policy", "retire_policy", "approve_request", "reject_request"}
        prepare = {"add_policy", "submit_request", "withdraw_request"}
        for n in approve: self.assertEqual(g[n][1], {"APW_APPROVE"}, n)
        for n in prepare: self.assertEqual(g[n][1], {"APW_PREPARE"}, n)
        for n, (verbs, guards) in g.items():
            if verbs == {"get"}: self.assertEqual(guards, set(), n)
            else: self.assertIn(n, approve | prepare, f"{n} writes but has no approvals guard")
        self.assertIn("dependencies=[Depends(require_permission(AUDIT_READ))]", src); self.assertNotIn("org_id", src)


if __name__ == "__main__":
    unittest.main()
