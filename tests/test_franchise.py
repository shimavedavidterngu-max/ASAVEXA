"""Franchise and multi-location: locations, sales reports, exact royalty, payments and balance, late and missing months, different-person decisions, isolation, audit and permissions."""
import ast
import os
import unittest
from datetime import date, datetime, timezone
from fractions import Fraction

from analysis_fixture import ORG, OTHER, World
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.permissions import AUDIT_READ, FCH_APPROVE, FCH_PREPARE, ROLE_PERMISSIONS
from asavexa.franchise.errors import FranchiseError, FranchiseForbiddenError, FranchiseNotFoundError, FranchiseStateError
from asavexa.franchise.service import FranchiseService

U1, U2, U3, U4 = "user-1", "user-2", "user-3", "user-4"   # U1 and U2 prepare, U3 and U4 approve


class Clock:
    def __init__(self): self.d = date(2026, 3, 31)
    def __call__(self): return datetime(self.d.year, self.d.month, self.d.day, 9, tzinfo=timezone.utc)


class Base(unittest.TestCase):
    def setUp(self):
        self.w = World(); self.clock = Clock(); self.events = []
        self.svc = FranchiseService(self.w.store, None, log=lambda *a: self.events.append(a), now=self.clock)

    def loc(self, actor=U1, **kw):
        d = dict(name="Lekki outlet", location_ref="OUT-1", currency="NGN", royalty_rate_pct="5", due_day=10, start_period="2026-01", description="The outlet run by the franchisee"); d.update(kw)
        return self.svc.fch_add_location(ORG, d, actor)

    def open(self, actor=U1, approver=U3, **kw):
        x = self.loc(actor, **kw); return self.svc.fch_approve_location(ORG, x["id"], {}, approver)

    def rep(self, x, period="2026-01", sales="1000.50", sub="2026-02-08", actor=U1):
        return self.svc.fch_add_report(ORG, x["id"], dict(period=period, gross_sales=sales, submitted_on=sub), actor)

    def pay(self, x, amt="20.00", on="2026-02-20", note="Bank transfer", actor=U1):
        return self.svc.fch_add_payment(ORG, x["id"], dict(amount=amt, paid_on=on, note=note), actor)

    def conf(self, x, kind, no, actor=U3, note=None):
        return self.svc.fch_decide(ORG, x["id"], kind, no, True, {"note": note} if note else {}, actor)


class Royalty(Base):
    def test_known_rounding(self):
        x = self.open(); x = self.rep(x, "2026-01", "1000.50"); self.assertEqual(x["reports"][0]["royalty"], "50.03")          # 50.025 rounds away from zero
        x = self.conf(x, "reports", 1); self.assertEqual((x["sales_total"], x["royalty_due"], x["paid_total"], x["balance"], x["balance_state"]), ("1000.50", "50.03", "0.00", "50.03", "OWED"))
        y = self.open(name="Second", royalty_rate_pct="7.5"); y = self.conf(self.rep(y, sales="1234.56"), "reports", 1); self.assertEqual(y["royalty_due"], "92.59")

    def test_matches_independent_arithmetic(self):
        for rate, sales in (("5", "0.10"), ("12.34", "99999.99"), ("0.01", "1234567.89"), ("100", "33.33"), ("33.33", "3.00"), ("7.25", "0.00")):
            x = self.conf(self.rep(self.open(name=f"S {rate} {sales}", royalty_rate_pct=rate), sales=sales), "reports", 1); p = Fraction(sales) * Fraction(rate) / 100
            q = (p.numerator * 200 + p.denominator) // (2 * p.denominator); self.assertEqual(x["royalty_due"], f"{q / 100:.2f}", (rate, sales))

    def test_only_confirmed_reports_and_payments_count(self):
        x = self.open(); x = self.rep(x); self.assertEqual(x["royalty_due"], "0.00"); x = self.conf(x, "reports", 1); x = self.pay(x, "20.00"); self.assertEqual(x["paid_total"], "0.00")
        x = self.conf(x, "payments", 1); self.assertEqual((x["paid_total"], x["balance"]), ("20.00", "30.03"))
        x = self.rep(x, "2026-02", "2000", "2026-03-09"); x = self.svc.fch_decide(ORG, x["id"], "reports", 2, False, "The figure was a typing slip", U3); self.assertEqual(x["royalty_due"], "50.03")

    def test_balance_states(self):
        x = self.open(); x = self.conf(self.rep(x, sales="1000"), "reports", 1); self.assertEqual(x["balance"], "50.00")
        x = self.conf(self.pay(x, "50.00"), "payments", 1); self.assertEqual((x["balance"], x["balance_state"]), ("0.00", "SETTLED"))
        x = self.conf(self.pay(x, "0.01"), "payments", 2); self.assertEqual((x["balance"], x["balance_state"]), ("-0.01", "OVERPAID"))

    def test_late_and_missing_months(self):
        x = self.open(); self.assertEqual(x["missing_periods"], ["2026-01", "2026-02"])                          # March is not due until 10 April
        x = self.rep(x, "2026-01", sub="2026-02-10"); self.assertEqual(x["reports"][0]["late"], False); self.assertEqual(x["missing_periods"], ["2026-02"])
        x = self.rep(x, "2026-02", sub="2026-03-11"); self.assertTrue(x["reports"][1]["late"]); self.assertEqual(x["missing_periods"], [])
        x = self.conf(self.conf(x, "reports", 1), "reports", 2); self.assertEqual(x["late_reports"], 1)
        self.clock.d = date(2026, 4, 11); self.assertEqual(self.svc.fch_get_location(ORG, x["id"])["missing_periods"], ["2026-03"])

    def test_grace_days(self):
        x = self.rep(self.open(), "2026-01", sub="2026-02-12"); self.assertTrue(x["reports"][0]["late"]); self.svc.fch_set_setting(ORG, {"grace_days": 2}, U3)
        v = self.svc.fch_get_location(ORG, x["id"]); self.assertFalse(v["reports"][0]["late"]); self.assertEqual(v["missing_periods"], ["2026-02"])
        self.svc.fch_set_setting(ORG, {"grace_days": 21}, U3); self.assertEqual(self.svc.fch_get_location(ORG, x["id"])["missing_periods"], [])             # 10 Mar + 21 days is 31 Mar, which is not before today

    def test_overdue_amount(self):
        x = self.open(); x = self.conf(self.rep(x, "2026-01", "1000"), "reports", 1); self.assertEqual(x["overdue_amount"], "50.00")          # due 10 Feb, grace 0
        x = self.conf(self.pay(x, "20"), "payments", 1); self.assertEqual(x["overdue_amount"], "30.00")
        x = self.conf(self.pay(x, "100"), "payments", 2); self.assertEqual(x["overdue_amount"], "0.00")                                      # never below zero
        y = self.conf(self.rep(self.open(name="Second"), "2026-03", "1000", "2026-03-30"), "reports", 1); self.assertEqual((y["royalty_due"], y["overdue_amount"]), ("50.00", "0.00"))   # not due until 10 April

    def test_december_rolls_into_january(self):
        self.clock.d = date(2027, 1, 20); x = self.rep(self.open(start_period="2026-12"), "2026-12", sub="2027-01-10"); self.assertEqual(x["reports"][0]["due_date"], "2027-01-10")


class Validation(Base):
    def test_location(self):
        for bad in ({"name": "ab"}, {"location_ref": "x"}, {"currency": "NG"}, {"currency": "n$n"}, {"royalty_rate_pct": "0"}, {"royalty_rate_pct": "100.01"}, {"royalty_rate_pct": "5.123"}, {"royalty_rate_pct": "-1"}, {"royalty_rate_pct": 5.5}, {"royalty_rate_pct": True}, {"royalty_rate_pct": None}, {"royalty_rate_pct": "x"},
                    {"due_day": 0}, {"due_day": 29}, {"due_day": "x"}, {"due_day": True}, {"due_day": 5.5}, {"start_period": "2026-04"}, {"start_period": "2006-03"}, {"start_period": "2026-13"}, {"description": "short"}):
            with self.assertRaises(FranchiseError, msg=bad): self.loc(**bad)
        x = self.loc(currency="ngn", royalty_rate_pct="100"); self.assertEqual((x["ref"], x["currency"], x["royalty_rate_pct"], x["status"]), ("FL-001", "NGN", "100.00", "PROPOSED")); self.assertEqual(self.loc()["ref"], "FL-002")

    def test_report(self):
        x = self.open()
        for bad in ({"period": "2026-13"}, {"period": "2025-12"}, {"period": "2026-04"}, {"period": None}, {"gross_sales": "x"}, {"gross_sales": -1}, {"gross_sales": 5.5}, {"gross_sales": True}, {"gross_sales": None}, {"gross_sales": "1.234"}, {"submitted_on": "2026-02-30"}, {"submitted_on": "2026-04-05"}, {"submitted_on": "1999-12-31"}):
            d = dict(period="2026-01", gross_sales="100", submitted_on="2026-02-08"); d.update(bad)
            with self.assertRaises(FranchiseError, msg=bad): self.svc.fch_add_report(ORG, x["id"], d, U1)
        self.assertEqual(self.rep(x, sales="0")["reports"][0]["royalty"], "0.00")                                # zero sales is a real report

    def test_one_live_report_per_month(self):
        x = self.rep(self.open())
        with self.assertRaises(FranchiseStateError): self.rep(x)
        x = self.svc.fch_decide(ORG, x["id"], "reports", 1, False, "The figure was a typing slip", U3); x = self.rep(x); x = self.conf(x, "reports", 2)
        with self.assertRaises(FranchiseStateError): self.rep(x)

    def test_payment(self):
        x = self.open()
        for bad in ({"amount": "0"}, {"amount": "x"}, {"amount": -1}, {"amount": 5.5}, {"amount": True}, {"amount": None}, {"amount": "1.234"}, {"paid_on": "2026-02-30"}, {"paid_on": "2026-04-05"}, {"paid_on": "1999-01-01"}, {"note": "ab"}):
            d = dict(amount="10", paid_on="2026-02-20", note="Bank transfer"); d.update(bad)
            with self.assertRaises(FranchiseError, msg=bad): self.svc.fch_add_payment(ORG, x["id"], d, U1)
        self.assertEqual(len(self.pay(self.pay(x), "20.00")["payments"]), 2)                                      # several payments are fine


class Workflow(Base):
    def test_location_decisions(self):
        x = self.loc()
        with self.assertRaises(FranchiseForbiddenError): self.svc.fch_approve_location(ORG, x["id"], {}, U1)
        with self.assertRaises(FranchiseForbiddenError): self.svc.fch_reject_location(ORG, x["id"], "Rejecting my own location", U1)
        with self.assertRaises(FranchiseError): self.svc.fch_reject_location(ORG, x["id"], "short", U3)
        with self.assertRaises(FranchiseError): self.svc.fch_approve_location(ORG, x["id"], {"note": "short"}, U3)
        with self.assertRaises(FranchiseStateError): self.rep(x)
        self.assertEqual(self.svc.fch_approve_location(ORG, x["id"], {"note": "Agreement checked"}, U3)["status"], "APPROVED")
        with self.assertRaises(FranchiseStateError): self.svc.fch_approve_location(ORG, x["id"], {}, U4)
        y = self.loc(); self.assertEqual(self.svc.fch_reject_location(ORG, y["id"], "Duplicate of another location", U3)["status"], "REJECTED")
        with self.assertRaises(FranchiseStateError): self.pay(y)

    def test_record_decisions(self):
        x = self.rep(self.open())
        with self.assertRaises(FranchiseForbiddenError): self.conf(x, "reports", 1, U1)
        with self.assertRaises(FranchiseForbiddenError): self.svc.fch_decide(ORG, x["id"], "reports", 1, False, "Rejecting my own record", U1)
        with self.assertRaises(FranchiseError): self.svc.fch_decide(ORG, x["id"], "reports", 1, False, "short", U3)
        with self.assertRaises(FranchiseError): self.conf(x, "reports", 1, U3, "short")
        for bad in ("x", None, True, 1.5):
            with self.assertRaises(FranchiseError): self.conf(x, "reports", bad)
        with self.assertRaises(FranchiseNotFoundError): self.conf(x, "reports", 9)
        for bad in ("members", None, ["reports"], 5):
            with self.assertRaises(FranchiseError): self.svc.fch_decide(ORG, x["id"], bad, 1, True, {}, U3)
        self.assertEqual(self.conf(x, "reports", 1, U3, "Matches the till summary")["reports"][0]["decision_note"], "Matches the till summary")
        with self.assertRaises(FranchiseStateError): self.conf(x, "reports", 1, U4)
        p = self.pay(x)
        with self.assertRaises(FranchiseForbiddenError): self.conf(p, "payments", 1, U1)
        self.assertEqual(self.conf(p, "payments", 1)["payments"][0]["status"], "CONFIRMED")

    def test_close(self):
        x = self.rep(self.open())
        with self.assertRaises(FranchiseStateError): self.svc.fch_close_location(ORG, x["id"], "The franchise has ended", U3)
        self.conf(x, "reports", 1)
        with self.assertRaises(FranchiseError): self.svc.fch_close_location(ORG, x["id"], "short", U3)
        c = self.svc.fch_close_location(ORG, x["id"], "The franchise has ended", U3); self.assertEqual((c["status"], c["close_note"], c["royalty_due"]), ("CLOSED", "The franchise has ended", "50.03"))
        for f in (lambda: self.rep(c, "2026-02"), lambda: self.pay(c), lambda: self.svc.fch_close_location(ORG, x["id"], "Closing it a second time", U3)):
            with self.assertRaises(FranchiseStateError): f()

    def test_list_is_summary_only(self):
        self.rep(self.open()); row = self.svc.fch_list_locations(ORG)[0]
        self.assertEqual((row["reports"], row["payments"], row["history"], row["pending"]), ([], [], [], 1)); self.assertEqual(len(self.svc.fch_list_locations(ORG, "APPROVED")), 1); self.assertEqual(self.svc.fch_list_locations(ORG, "PROPOSED"), [])


class Settings(Base):
    def test_settings(self):
        self.assertEqual(self.svc.fch_get_setting(ORG)["grace_days"], 0)
        for bad in (-1, 61, "x", 1.5, True):
            with self.assertRaises(FranchiseError, msg=bad): self.svc.fch_set_setting(ORG, {"grace_days": bad}, U3)
        self.assertEqual(self.svc.fch_set_setting(ORG, {"grace_days": "14"}, U3)["grace_days"], 14); self.assertEqual(self.svc.fch_set_setting(ORG, {"grace_days": 0}, U3)["grace_days"], 0)


class Overview(Base):
    def test_counts_attention_and_rollup(self):
        self.loc(); a = self.open(name="Location A"); a = self.conf(self.rep(a, "2026-01", "1000", "2026-02-12"), "reports", 1); self.rep(a, "2026-02", "500", "2026-03-09")
        b = self.open(name="Location B", currency="USD", royalty_rate_pct="10"); b = self.conf(self.rep(b, "2026-01", "200.50"), "reports", 1); b = self.conf(self.pay(b, "50"), "payments", 1)
        c = self.open(name="Location C", currency="USD", royalty_rate_pct="10"); self.conf(self.rep(c, "2026-01", "100"), "reports", 1)
        r = self.loc(name="Location R"); self.svc.fch_reject_location(ORG, r["id"], "Duplicate of another location", U3)
        o = self.svc.fch_overview(ORG); self.assertEqual(o["counts"], {"proposed": 1, "approved": 3, "rejected": 1, "closed": 0}); k = {x["kind"]: x["count"] for x in o["attention"]}
        self.assertEqual(k, {"LOCATIONS_TO_APPROVE": 1, "ITEMS_TO_DECIDE": 1, "MISSING_REPORTS": 2, "LATE_REPORTS": 1, "ROYALTY_OVERDUE": 2, "OVERPAID": 1})
        self.assertEqual([(t["currency"], t["locations"], t["sales_total"], t["royalty_due"], t["paid_total"], t["balance"]) for t in o["by_currency"]],
                         [("NGN", 1, "1000.00", "50.00", "0.00", "50.00"), ("USD", 2, "300.50", "30.05", "50.00", "-19.95")])             # currencies are never added together

    def test_empty(self):
        o = self.svc.fch_overview(ORG); self.assertEqual((o["attention"], o["by_currency"], o["counts"]["approved"]), ([], [], 0))


class Isolation(Base):
    def test_other_company(self):
        x = self.rep(self.open()); self.assertEqual(self.svc.fch_list_locations(OTHER), [])
        for f in (lambda: self.svc.fch_get_location(OTHER, x["id"]), lambda: self.svc.fch_decide(OTHER, x["id"], "reports", 1, True, {}, U3), lambda: self.svc.fch_add_report(OTHER, x["id"], {}, U1), lambda: self.svc.fch_close_location(OTHER, x["id"], "Closing from elsewhere", U3)):
            with self.assertRaises(FranchiseNotFoundError): f()
        self.assertEqual(self.svc.fch_add_location(OTHER, dict(name="Other outlet", location_ref="OPS-1", currency="NGN", royalty_rate_pct="5", due_day=1, start_period="2026-01", description="An outlet at another company"), U1)["ref"], "FL-001")


class Audit(Base):
    def test_every_write_logged_without_content(self):
        x = self.open(name="Secret outlet name"); x = self.rep(x, "2026-01", "7777.77"); self.conf(x, "reports", 1, U3, "Matches the till summary"); x = self.pay(x, "3333.33", note="Chinedu transfer ref 42")
        self.svc.fch_decide(ORG, x["id"], "payments", 1, False, "The figure was a typing slip", U3)
        y = self.loc(name="Rejected outlet"); self.svc.fch_reject_location(ORG, y["id"], "Duplicate of another location", U3); self.svc.fch_set_setting(ORG, {"grace_days": 3}, U3); self.svc.fch_close_location(ORG, x["id"], "The franchise has ended", U3)
        acts = {e[0] for e in self.events}
        for a in ("FRANCHISE_LOCATION_PROPOSED", "FRANCHISE_LOCATION_APPROVED", "FRANCHISE_LOCATION_REJECTED", "FRANCHISE_LOCATION_CLOSED", "FRANCHISE_REPORT_RECORDED", "FRANCHISE_REPORT_CONFIRMED", "FRANCHISE_PAYMENT_RECORDED", "FRANCHISE_PAYMENT_REJECTED", "FRANCHISE_SETTING_SET"): self.assertIn(a, acts)
        blob = " ".join(str(e) for e in self.events)
        for secret in ("Secret outlet", "OUT-1", "7777", "3333", "Chinedu", "Matches the till", "typing slip", "Duplicate of", "franchise has ended"): self.assertNotIn(secret, blob)

    def test_failed_actions_are_not_logged(self):
        with self.assertRaises(FranchiseError): self.loc(name="ab")
        x = self.open(); n = len(self.events)
        with self.assertRaises(FranchiseError): self.rep(x, "2026-13")
        with self.assertRaises(FranchiseForbiddenError): self.svc.fch_approve_location(ORG, self.loc()["id"], {}, U1)
        self.assertEqual(len(self.events), n + 1)                                                          # only the location proposed above


class Permissions(unittest.TestCase):
    def test_roles(self):
        has = lambda r, p: p in ROLE_PERMISSIONS[r]
        for r in (Role.OWNER, Role.ADMINISTRATOR, Role.MANAGER, Role.AUDITOR): self.assertTrue(has(r, FCH_PREPARE), r)
        for r in (Role.OWNER, Role.APPROVER, Role.MANAGER): self.assertTrue(has(r, FCH_APPROVE), r)
        for r in (Role.ACCOUNTANT, Role.REVIEWER, Role.EXTERNAL_AUDITOR, Role.READ_ONLY, Role.DONOR, Role.REGULATOR, Role.INVESTOR_REVIEWER): self.assertFalse(has(r, FCH_PREPARE) or has(r, FCH_APPROVE), r)

    def test_anyone_who_can_prepare_or_approve_can_view(self):
        for r, perms in ROLE_PERMISSIONS.items():
            if FCH_PREPARE in perms or FCH_APPROVE in perms: self.assertIn(AUDIT_READ, perms, r)


class RouterGuards(unittest.TestCase):
    SRC = os.path.join(os.path.dirname(__file__), "..", "src", "asavexa", "api", "routers", "franchise.py")

    def test_every_write_has_the_right_guard(self):
        with open(self.SRC) as fh: src = fh.read()
        tree = ast.parse(src); named = {"_prepare": "FCH_PREPARE", "_approve": "FCH_APPROVE"}; g = {}
        for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.decorator_list]:
            verbs, guards = set(), set()
            for dec in fn.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute): verbs.add(dec.func.attr)
                for kw in getattr(dec, "keywords", []):
                    if kw.arg == "dependencies": guards |= {named[e.id] for e in kw.value.elts if isinstance(e, ast.Name) and e.id in named}
            g[fn.name] = (verbs, guards)
        approve = {"set_setting", "approve_location", "reject_location", "close_location", "confirm_report", "reject_report", "confirm_payment", "reject_payment"}; prepare = {"add_location", "add_report", "add_payment"}
        for n in approve: self.assertEqual(g[n][1], {"FCH_APPROVE"}, n)
        for n in prepare: self.assertEqual(g[n][1], {"FCH_PREPARE"}, n)
        for n, (verbs, guards) in g.items():
            if verbs == {"get"}: self.assertEqual(guards, set(), n)
            else: self.assertIn(n, approve | prepare, f"{n} writes but has no franchise guard")
        self.assertIn("dependencies=[Depends(require_permission(AUDIT_READ))]", src); self.assertNotIn("org_id", src)


if __name__ == "__main__":
    unittest.main()
