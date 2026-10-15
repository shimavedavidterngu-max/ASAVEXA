"""Payroll and workforce cost: runs, pay lines, exact totals, different-person review, setting, overlaps, isolation, audit, permissions."""
import ast
import os
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from fractions import Fraction

from analysis_fixture import ORG, OTHER, World
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.permissions import AUDIT_READ, PAY_APPROVE, PAY_PREPARE, ROLE_PERMISSIONS
from asavexa.payroll.errors import PayrollError, PayrollForbiddenError, PayrollNotFoundError, PayrollStateError
from asavexa.payroll.service import PayrollService, refnum

U1, U2, U3, U4 = "user-1", "user-2", "user-3", "user-4"   # U1 and U2 prepare, U3 and U4 approve


class Clock:
    def __init__(self): self.d = date(2026, 3, 31)
    def __call__(self): return datetime(self.d.year, self.d.month, self.d.day, 9, tzinfo=timezone.utc)


F = lambda s: Fraction(Decimal(s))


class Base(unittest.TestCase):
    def setUp(self):
        self.w = World(); self.clock = Clock(); self.events = []
        self.svc = PayrollService(self.w.store, None, log=lambda *a: self.events.append(a), now=self.clock)

    def run_(self, actor=U1, **kw):
        d = dict(label="March 2026 salaries", period_start="2026-03-01", period_end="2026-03-31", currency="NGN"); d.update(kw)
        return self.svc.pw_create_run(ORG, d, actor)

    def line(self, r, actor=U1, **kw):
        d = dict(staff_ref="S-014", department="Finance", base_pay="250000.00", allowances="30000.50", deductions=[{"label": "Pension", "amount": "22400.04"}, {"label": "Income tax", "amount": "41000.10"}], employer_contributions="28000.05"); d.update(kw)
        return self.svc.pw_add_line(ORG, r["id"], d, actor)

    def ready(self, actor=U1):
        r = self.run_(actor); self.line(r, actor); return self.line(r, actor, staff_ref="S-015", department="Sales", base_pay="180000", allowances="", deductions=[], employer_contributions=""); 

    def submit(self, r, actor=U1, note=""): return self.svc.pw_submit(ORG, r["id"], {"note": note}, actor)


class Lines(Base):
    def test_exact_arithmetic_against_an_oracle(self):
        r = self.line(self.run_()); l = r["lines"][0]
        gross = F("250000.00") + F("30000.50"); ded = F("22400.04") + F("41000.10"); emp = F("28000.05")
        self.assertEqual((l["gross"], l["total_deductions"], l["net"], l["employer_cost"]), ("280000.50", "63400.14", "216600.36", "308000.55"))
        self.assertEqual((Fraction(Decimal(l["gross"])), Fraction(Decimal(l["total_deductions"])), Fraction(Decimal(l["net"])), Fraction(Decimal(l["employer_cost"]))), (gross, ded, gross - ded, gross + emp))

    def test_totals_and_departments(self):
        r = self.ready(); t = r["totals"]
        self.assertEqual((t["gross"], t["deductions"], t["net"], t["employer_contributions"], t["employer_cost"], t["lines"]), ("460000.50", "63400.14", "396600.36", "28000.05", "488000.55", 2))
        self.assertEqual([(d["department"], d["gross"], d["net"]) for d in r["departments"]], [("Finance", "280000.50", "216600.36"), ("Sales", "180000.00", "180000.00")])

    def test_validation(self):
        r = self.run_()
        for bad in ({"staff_ref": "x"}, {"department": "x"}, {"base_pay": "0"}, {"base_pay": 100.5}, {"base_pay": "1.234"}, {"base_pay": "１２３"}, {"base_pay": "1,00"}, {"allowances": "-1"}, {"employer_contributions": "x"},
                    {"deductions": "x"}, {"deductions": [5]}, {"deductions": [{"label": "x", "amount": "5"}]}, {"deductions": [{"label": "Tax", "amount": "0"}]}, {"deductions": [{"label": "Tax", "amount": 5.5}]}, {"deductions": [{"label": "Tax", "amount": "999999"}]},
                    {"deductions": [{"label": f"D{i}", "amount": "1"} for i in range(9)]}):
            with self.assertRaises(PayrollError, msg=str(bad)): self.line(r, **bad)
        self.assertEqual(self.line(r, base_pay="1,500.50", allowances="", deductions=[])["lines"][0]["base_pay"], "1500.50")
        l = self.line(r, staff_ref="S-2", deductions=None)["lines"][1]; self.assertEqual((l["total_deductions"], l["net"]), ("0.00", l["gross"]))

    def test_deductions_may_equal_gross(self):
        r = self.run_(); l = self.line(r, base_pay="100", allowances="", deductions=[{"label": "Loan repayment", "amount": "100"}])["lines"][0]; self.assertEqual(l["net"], "0.00")

    def test_duplicate_staff_in_a_run_refused_but_reusable_after_removal(self):
        r = self.run_(); self.line(r)
        with self.assertRaises(PayrollStateError): self.line(r, staff_ref="s-014")
        self.svc.pw_remove_line(ORG, r["id"], 1, "Entered with the wrong figures", U1); self.assertEqual(self.line(r)["active_lines"], 1)

    def test_remove(self):
        r = self.ready()
        with self.assertRaises(PayrollError): self.svc.pw_remove_line(ORG, r["id"], 1, "no", U1)
        with self.assertRaises(PayrollError): self.svc.pw_remove_line(ORG, r["id"], "x", "Wrong person entered", U1)
        with self.assertRaises(PayrollNotFoundError): self.svc.pw_remove_line(ORG, r["id"], 9, "Wrong person entered", U1)
        v = self.svc.pw_remove_line(ORG, r["id"], 1, "Entered with the wrong figures", U1); self.assertEqual((v["totals"]["gross"], v["active_lines"], v["lines"][0]["status"]), ("180000.00", 1, "REMOVED"))
        with self.assertRaises(PayrollStateError): self.svc.pw_remove_line(ORG, r["id"], 1, "Removing it a second time", U1)

    def test_line_limit(self):
        r = self.run_()
        for i in range(500): self.svc.pw_add_line(ORG, r["id"], dict(staff_ref=f"S-{i:04d}", department="Ops", base_pay="1"), U1)
        with self.assertRaises(PayrollStateError): self.svc.pw_add_line(ORG, r["id"], dict(staff_ref="S-9999", department="Ops", base_pay="1"), U1)


class Runs(Base):
    def test_create_validation_and_numbering(self):
        self.assertEqual(self.run_()["ref"], "PR-001")
        for bad in ({"label": "ab"}, {"period_start": "2026-02-30"}, {"period_end": "2026-02-28"}, {"period_end": "2026-04-05"}, {"period_start": "2024-01-01"}, {"currency": "NG"}, {"currency": "N1A"}):
            with self.assertRaises(PayrollError, msg=str(bad)): self.run_(**bad)
        self.assertEqual(self.run_()["ref"], "PR-002"); self.assertEqual(refnum({"ref": "PR-010"}), 10)

    def test_withdraw(self):
        r = self.run_()
        with self.assertRaises(PayrollError): self.svc.pw_withdraw_run(ORG, r["id"], "short", U1)
        self.assertEqual(self.svc.pw_withdraw_run(ORG, r["id"], "Started for the wrong month", U1)["status"], "WITHDRAWN")
        with self.assertRaises(PayrollStateError): self.line(r)

    def test_list_carries_totals_not_lines(self):
        self.ready(); x = self.svc.pw_list_runs(ORG)[0]; self.assertEqual((x["lines"], x["totals"]["gross"]), ([], "460000.50"))


class Review(Base):
    def test_submit_needs_a_line(self):
        r = self.run_()
        with self.assertRaises(PayrollStateError): self.submit(r)
        r = self.ready()
        with self.assertRaises(PayrollError): self.submit(r, note="short")
        self.assertEqual(self.submit(r, note="")["status"], "SUBMITTED")
        with self.assertRaises(PayrollStateError): self.line(r)
        with self.assertRaises(PayrollStateError): self.svc.pw_withdraw_run(ORG, r["id"], "Withdrawing after submit", U1)

    def test_approve_and_return_by_a_different_person(self):
        r = self.ready(); self.submit(r, note="March payroll for approval")
        with self.assertRaises(PayrollForbiddenError): self.svc.pw_approve_run(ORG, r["id"], {}, U1)
        with self.assertRaises(PayrollForbiddenError): self.svc.pw_return_run(ORG, r["id"], "Returning my own run", U1)
        with self.assertRaises(PayrollError): self.svc.pw_return_run(ORG, r["id"], "short", U3)
        v = self.svc.pw_return_run(ORG, r["id"], "Finance line looks too high", U3); self.assertEqual((v["status"], v["decision_note"]), ("RETURNED", "Finance line looks too high"))
        self.svc.pw_remove_line(ORG, r["id"], 1, "Wrong figures, will re-enter", U2); self.line(r, U2, staff_ref="S-014", base_pay="200000", allowances="", deductions=[], employer_contributions="")
        self.submit(r, U2); v = self.svc.pw_approve_run(ORG, r["id"], {"note": "Checked against the sheet"}, U4)
        self.assertEqual((v["status"], v["decided_by"], v["totals"]["gross"]), ("APPROVED", U4, "380000.00"))
        for f in (lambda: self.svc.pw_approve_run(ORG, r["id"], {}, U3), lambda: self.svc.pw_return_run(ORG, r["id"], "Returning it after approval", U3), lambda: self.line(r), lambda: self.svc.pw_withdraw_run(ORG, r["id"], "Withdrawing after approval", U1)):
            with self.assertRaises(PayrollStateError): f()

    def test_owner_two_person_rule(self):
        r = self.ready(U3); self.submit(r, U3)
        with self.assertRaises(PayrollForbiddenError): self.svc.pw_approve_run(ORG, r["id"], {}, U3)


class Flags(Base):
    def test_review_limit(self):
        r = self.ready(); self.assertEqual(r["above_limit"], 0); self.assertIn("No line is flagged", self.svc.pw_get_setting(ORG)["meaning"])
        self.svc.pw_set_setting(ORG, {"review_limit": "250,000.00"}, U3); v = self.svc.pw_get_run(ORG, r["id"]); self.assertEqual((v["above_limit"], [l["above_limit"] for l in v["lines"]]), (1, [True, False]))
        self.assertIn("more than 250000.00", self.svc.pw_get_setting(ORG)["meaning"])
        for bad in ("-1", "x", 5.5, True, "1.234"):
            with self.assertRaises(PayrollError, msg=str(bad)): self.svc.pw_set_setting(ORG, {"review_limit": bad}, U3)
        self.svc.pw_set_setting(ORG, {"review_limit": "0"}, U3); self.assertEqual(self.svc.pw_get_run(ORG, r["id"])["above_limit"], 0)

    def test_overlapping_pay_is_flagged_not_blocked(self):
        a = self.ready(); self.submit(a)
        b = self.run_(label="Correction run", period_start="2026-03-15", period_end="2026-03-31"); self.line(b, staff_ref="s-014")
        vb = self.svc.pw_get_run(ORG, b["id"]); self.assertEqual((vb["overlaps"], vb["lines"][0]["overlap"]), (1, True)); self.assertEqual(self.svc.pw_get_run(ORG, a["id"])["overlaps"], 0)      # a draft is not compared with
        c = self.run_(label="April run", period_start="2026-04-01", period_end="2026-04-01"); self.clock.d = date(2026, 4, 2); self.line(c, staff_ref="S-014"); self.assertEqual(self.svc.pw_get_run(ORG, c["id"])["overlaps"], 0)
        d = self.run_(label="Dollar run", currency="USD"); self.line(d, staff_ref="S-014"); self.assertEqual(self.svc.pw_get_run(ORG, d["id"])["overlaps"], 0)
        self.submit(b); self.assertEqual(self.svc.pw_get_run(ORG, a["id"])["overlaps"], 1)       # once both are submitted each flags the other
        self.assertEqual(self.svc.pw_get_run(ORG, b["id"])["status"], "SUBMITTED")


class Overview(Base):
    def test_totals_per_currency_and_attention(self):
        a = self.ready(); self.submit(a); self.svc.pw_approve_run(ORG, a["id"], {}, U3)
        b = self.run_(label="Dollar run", currency="USD"); self.line(b, staff_ref="U-1", base_pay="5000.25", allowances="100", deductions=[{"label": "Tax", "amount": "500.10"}], employer_contributions="50"); self.submit(b)
        c = self.run_(label="Draft run", period_start="2026-02-01", period_end="2026-02-28"); self.line(c)
        self.svc.pw_set_setting(ORG, {"review_limit": "1000"}, U3)
        o = self.svc.pw_overview(ORG); n = next(t for t in o["totals"] if t["currency"] == "NGN"); u = next(t for t in o["totals"] if t["currency"] == "USD")
        self.assertEqual((n["approved_runs"], n["gross"], n["deductions"], n["net"], n["employer_contributions"], n["employer_cost"]), (1, "460000.50", "63400.14", "396600.36", "28000.05", "488000.55"))
        self.assertEqual((u["approved_runs"], u["waiting_runs"], u["gross"]), (0, 1, "0.00"))
        kinds = {x["kind"]: x["count"] for x in o["attention"]}; self.assertEqual((kinds["RUNS_TO_REVIEW"], "OVERLAPPING_PAY" in kinds, kinds["LINES_ABOVE_LIMIT"]), (1, False, 2))
        self.assertEqual((o["counts"]["approved"], o["counts"]["submitted"], o["counts"]["draft"]), (1, 1, 1))

    def test_empty(self):
        o = self.svc.pw_overview(ORG); self.assertEqual((o["totals"], o["attention"]), ([], []))


class Isolation(Base):
    def test_other_company(self):
        r = self.ready()
        self.assertEqual(self.svc.pw_list_runs(OTHER), []); self.assertEqual(self.svc.pw_overview(OTHER)["totals"], [])
        for f in (lambda: self.svc.pw_get_run(OTHER, r["id"]), lambda: self.svc.pw_add_line(OTHER, r["id"], {}, U1), lambda: self.svc.pw_remove_line(OTHER, r["id"], 1, "Removing from elsewhere", U1), lambda: self.svc.pw_submit(OTHER, r["id"], {}, U1),
                  lambda: self.svc.pw_approve_run(OTHER, r["id"], {}, U3), lambda: self.svc.pw_return_run(OTHER, r["id"], "Returning from elsewhere", U3), lambda: self.svc.pw_withdraw_run(OTHER, r["id"], "Withdrawing from elsewhere", U1)):
            with self.assertRaises(PayrollNotFoundError): f()

    def test_overlap_check_ignores_other_companies(self):
        a = self.ready(); self.submit(a)
        o = self.svc.pw_create_run(OTHER, dict(label="Other company run", period_start="2026-03-01", period_end="2026-03-31", currency="NGN"), U1); self.svc.pw_add_line(OTHER, o["id"], dict(staff_ref="S-014", department="Ops", base_pay="10"), U1)
        self.assertEqual(self.svc.pw_get_run(OTHER, o["id"])["overlaps"], 0); self.assertEqual(self.svc.pw_get_run(ORG, a["id"])["overlaps"], 0)

    def test_numbering_per_company(self):
        self.run_(); self.assertEqual(self.svc.pw_create_run(OTHER, dict(label="Other company run", period_start="2026-03-01", period_end="2026-03-31", currency="NGN"), U1)["ref"], "PR-001")


class Audit(Base):
    def test_every_write_logged_without_content(self):
        r = self.ready(); self.svc.pw_remove_line(ORG, r["id"], 2, "Entered with the wrong figures", U1); self.submit(r, note="Note about Chinedu"); self.svc.pw_return_run(ORG, r["id"], "Finance line looks too high", U3)
        self.line(r, staff_ref="S-016"); self.submit(r); self.svc.pw_approve_run(ORG, r["id"], {"note": "Checked against sheet"}, U3); w = self.run_(); self.svc.pw_withdraw_run(ORG, w["id"], "Started for the wrong month", U1); self.svc.pw_set_setting(ORG, {"review_limit": "5"}, U3)
        acts = [x[0] for x in self.events]
        for x in ("PAYROLL_RUN_CREATED", "PAYROLL_LINE_ADDED", "PAYROLL_LINE_REMOVED", "PAYROLL_RUN_SUBMITTED", "PAYROLL_RUN_RETURNED", "PAYROLL_RUN_APPROVED", "PAYROLL_RUN_WITHDRAWN", "PAYROLL_SETTING_SET"): self.assertIn(x, acts)
        blob = " ".join(str(x) for x in self.events)
        for secret in ("S-014", "Finance", "250000", "280000", "Pension", "Income tax", "Chinedu", "March 2026", "wrong figures", "looks too high", "Checked against"): self.assertNotIn(secret, blob)

    def test_failed_actions_are_not_logged(self):
        with self.assertRaises(PayrollError): self.run_(label="ab")
        r = self.run_(); n = len(self.events)
        with self.assertRaises(PayrollError): self.line(r, base_pay="0")
        with self.assertRaises(PayrollStateError): self.submit(r)
        self.assertEqual(len(self.events), n)


class Permissions(unittest.TestCase):
    def test_roles(self):
        has = lambda r, p: p in ROLE_PERMISSIONS[r]
        for r in (Role.OWNER, Role.ADMINISTRATOR, Role.MANAGER, Role.AUDITOR): self.assertTrue(has(r, PAY_PREPARE), r)
        for r in (Role.OWNER, Role.APPROVER, Role.MANAGER): self.assertTrue(has(r, PAY_APPROVE), r)
        for r in (Role.ACCOUNTANT, Role.REVIEWER, Role.EXTERNAL_AUDITOR, Role.READ_ONLY, Role.DONOR, Role.REGULATOR, Role.INVESTOR_REVIEWER): self.assertFalse(has(r, PAY_PREPARE) or has(r, PAY_APPROVE), r)

    def test_anyone_who_can_prepare_or_approve_can_view(self):
        for r, perms in ROLE_PERMISSIONS.items():
            if PAY_PREPARE in perms or PAY_APPROVE in perms: self.assertIn(AUDIT_READ, perms, r)


class RouterGuards(unittest.TestCase):
    SRC = os.path.join(os.path.dirname(__file__), "..", "src", "asavexa", "api", "routers", "payroll.py")

    def test_every_write_has_the_right_guard(self):
        tree = ast.parse(open(self.SRC).read()); named = {"_prepare": "PAY_PREPARE", "_approve": "PAY_APPROVE"}; g = {}
        for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.decorator_list]:
            verbs, guards = set(), set()
            for dec in fn.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute): verbs.add(dec.func.attr)
                for kw in getattr(dec, "keywords", []):
                    if kw.arg == "dependencies": guards |= {named[e.id] for e in kw.value.elts if isinstance(e, ast.Name) and e.id in named}
            g[fn.name] = (verbs, guards)
        approve = {"set_setting", "approve", "return_run"}
        prepare = {"create_run", "add_line", "remove_line", "submit", "withdraw"}
        for n in approve: self.assertEqual(g[n][1], {"PAY_APPROVE"}, n)
        for n in prepare: self.assertEqual(g[n][1], {"PAY_PREPARE"}, n)
        for n, (verbs, guards) in g.items():
            if verbs == {"get"}: self.assertEqual(guards, set(), n)
            else: self.assertIn(n, approve | prepare, f"{n} writes but has no payroll guard")
        src = open(self.SRC).read(); self.assertIn("dependencies=[Depends(require_permission(AUDIT_READ))]", src); self.assertNotIn("org_id", src)


if __name__ == "__main__":
    unittest.main()
