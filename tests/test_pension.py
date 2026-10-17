"""Pension and fiduciary: schemes, contributions (exact totals, late and missing months), funding valuations (exact ratio), obligations calendar, conflict register, different-person decisions, isolation, audit and permissions."""
import ast
import os
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from fractions import Fraction

from analysis_fixture import ORG, OTHER, World
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.permissions import AUDIT_READ, PEN_APPROVE, PEN_PREPARE, ROLE_PERMISSIONS
from asavexa.pension.errors import PensionError, PensionForbiddenError, PensionNotFoundError, PensionStateError
from asavexa.pension.service import PensionService

U1, U2, U3, U4 = "user-1", "user-2", "user-3", "user-4"   # U1 and U2 prepare, U3 and U4 approve


class Clock:
    def __init__(self): self.d = date(2026, 3, 31)
    def __call__(self): return datetime(self.d.year, self.d.month, self.d.day, 9, tzinfo=timezone.utc)


class Base(unittest.TestCase):
    def setUp(self):
        self.w = World(); self.clock = Clock(); self.events = []
        self.svc = PensionService(self.w.store, None, log=lambda *a: self.events.append(a), now=self.clock)

    def sch(self, actor=U1, **kw):
        d = dict(name="Staff retirement scheme", scheme_ref="TRUST-1", currency="NGN", scheme_type="DEFINED_CONTRIBUTION", start_period="2026-01", due_day=15, description="The staff scheme run by the trustees"); d.update(kw)
        return self.svc.pen_add_scheme(ORG, d, actor)

    def open(self, actor=U1, approver=U3, **kw):
        x = self.sch(actor, **kw); return self.svc.pen_approve_scheme(ORG, x["id"], {}, approver)

    def con(self, x, period="2026-01", emp="1000.50", ee="500.25", paid="2026-02-10", actor=U1):
        return self.svc.pen_add_contribution(ORG, x["id"], dict(period=period, employer_amount=emp, employee_amount=ee, paid_on=paid), actor)

    def val(self, x, as_of="2026-03-01", assets="900000", liabilities="1000000", actor=U1, **kw):
        d = dict(as_of=as_of, assets=assets, liabilities=liabilities, source_note="From the actuary report of March"); d.update(kw); return self.svc.pen_add_valuation(ORG, x["id"], d, actor)

    def obl(self, x, title="File the annual return", due="2026-04-20", actor=U1):
        return self.svc.pen_add_obligation(ORG, x["id"], dict(title=title, due_date=due), actor)

    def conf(self, x, kind, no, actor=U3, note=None):
        return self.svc.pen_decide(ORG, x["id"], kind, no, True, {"note": note} if note else {}, actor)


class Contributions(Base):
    def test_totals_are_exact_and_only_confirmed_count(self):
        x = self.open(); x = self.con(x, "2026-01", "1000.10", "0.20"); x = self.con(x, "2026-02", "2000.20", "0.30", "2026-03-10")
        self.assertEqual(x["total_contributions"], "0.00"); x = self.conf(x, "contributions", 1); x = self.conf(x, "contributions", 2)
        self.assertEqual((x["employer_total"], x["employee_total"], x["total_contributions"]), ("3000.30", "0.50", "3000.80"))
        self.assertEqual(x["contributions"][0]["total"], "1000.30")

    def test_late_flag_uses_the_following_months_due_day(self):
        x = self.open(); x = self.con(x, "2026-01", paid="2026-02-15"); x = self.con(x, "2026-02", paid="2026-03-16")
        self.assertEqual([r["due_date"] for r in x["contributions"]], ["2026-02-15", "2026-03-15"]); self.assertEqual([r["late"] for r in x["contributions"]], [False, True])
        x = self.conf(x, "contributions", 1); x = self.conf(x, "contributions", 2); self.assertEqual(x["late_contributions"], 1)

    def test_december_rolls_into_january(self):
        self.clock.d = date(2027, 1, 20); x = self.open(start_period="2026-12"); x = self.con(x, "2026-12", paid="2027-01-15"); self.assertEqual(x["contributions"][0]["due_date"], "2027-01-15")

    def test_missing_months(self):
        x = self.open(); self.assertEqual(x["missing_periods"], ["2026-01", "2026-02"])                  # March is not due until 15 April
        x = self.con(x, "2026-01"); self.assertEqual(x["missing_periods"], ["2026-02"])                    # waiting for a decision still counts as recorded
        self.clock.d = date(2026, 4, 16); self.assertEqual(self.svc.pen_get_scheme(ORG, x["id"])["missing_periods"], ["2026-02", "2026-03"])
        x = self.svc.pen_decide(ORG, x["id"], "contributions", 1, False, "The amount was a typing slip", U3); self.assertEqual(x["missing_periods"], ["2026-01", "2026-02", "2026-03"])

    def test_validation(self):
        x = self.open()
        for bad in ({"period": "2026-13"}, {"period": "2025-12"}, {"period": "2026-04"}, {"period": "26-01"}, {"period": None}, {"employer_amount": "x"}, {"employer_amount": 5.5}, {"employer_amount": True}, {"employer_amount": "-1"}, {"employer_amount": "1.234"}, {"employee_amount": None},
                    {"employer_amount": "0", "employee_amount": "0"}, {"paid_on": "2026-02-30"}, {"paid_on": "2026-04-05"}, {"paid_on": "1999-12-31"}):
            d = dict(period="2026-01", employer_amount="10", employee_amount="5", paid_on="2026-02-10"); d.update(bad)
            with self.assertRaises(PensionError, msg=bad): self.svc.pen_add_contribution(ORG, x["id"], d, U1)
        self.assertEqual(self.con(x, "2026-01", "0", "5")["contributions"][0]["employer_amount"], "0.00")      # one side may be zero

    def test_one_live_contribution_per_month(self):
        x = self.con(self.open())
        with self.assertRaises(PensionStateError): self.con(x)
        x = self.svc.pen_decide(ORG, x["id"], "contributions", 1, False, "The amount was a typing slip", U3); x = self.con(x); x = self.conf(x, "contributions", 2)
        with self.assertRaises(PensionStateError): self.con(x)

    def test_decisions(self):
        x = self.con(self.open())
        with self.assertRaises(PensionForbiddenError): self.conf(x, "contributions", 1, U1)
        with self.assertRaises(PensionForbiddenError): self.svc.pen_decide(ORG, x["id"], "contributions", 1, False, "Rejecting my own record", U1)
        with self.assertRaises(PensionError): self.svc.pen_decide(ORG, x["id"], "contributions", 1, False, "short", U3)
        with self.assertRaises(PensionError): self.conf(x, "contributions", 1, U3, "short")
        for bad in ("x", None, True, 1.5):
            with self.assertRaises(PensionError): self.conf(x, "contributions", bad)
        with self.assertRaises(PensionNotFoundError): self.conf(x, "contributions", 9)
        with self.assertRaises(PensionError): self.svc.pen_decide(ORG, x["id"], "members", 1, True, {}, U3)
        self.assertEqual(self.conf(x, "contributions", 1, U3, "Matches the bank statement")["contributions"][0]["decision_note"], "Matches the bank statement")
        with self.assertRaises(PensionStateError): self.conf(x, "contributions", 1, U4)


class Valuations(Base):
    def test_known_ratio_and_position(self):
        x = self.open(); x = self.val(x); self.assertIsNone(x["funding_ratio_pct"]); x = self.conf(x, "valuations", 1)
        self.assertEqual((x["funding_ratio_pct"], x["position"], x["position_amount"], x["below_floor"]), ("90.00", "DEFICIT", "100000.00", False))
        y = self.conf(self.val(self.open(name="Second"), assets="1250000.50", liabilities="1000000"), "valuations", 1); self.assertEqual((y["funding_ratio_pct"], y["position"], y["position_amount"]), ("125.00", "SURPLUS", "250000.50"))
        z = self.conf(self.val(self.open(name="Third"), assets="1000", liabilities="1000"), "valuations", 1); self.assertEqual((z["funding_ratio_pct"], z["position"], z["position_amount"]), ("100.00", "BALANCED", "0.00"))

    def test_ratio_matches_independent_arithmetic(self):
        for a, l in (("1", "3"), ("2", "3"), ("123456.78", "987654.32"), ("0", "50"), ("99999999.99", "0.01")):
            x = self.conf(self.val(self.open(name=f"S {a} {l}"), assets=a, liabilities=l), "valuations", 1); p = Fraction(a) / Fraction(l) * 100
            q = (p.numerator * 200 + p.denominator) // (2 * p.denominator); self.assertEqual(x["funding_ratio_pct"], f"{q / 100:.2f}", (a, l))

    def test_floor_boundary_and_staleness(self):
        x = self.open(); x = self.conf(self.val(x, assets="899999.99"), "valuations", 1); self.assertTrue(x["below_floor"])       # 89.999999 percent
        y = self.conf(self.val(self.open(name="Second"), assets="900000"), "valuations", 1); self.assertFalse(y["below_floor"])
        self.svc.pen_set_setting(ORG, {"funding_floor_pct": 91}, U3); self.assertTrue(self.svc.pen_get_scheme(ORG, y["id"])["below_floor"])
        self.clock.d = date(2027, 3, 1); self.assertFalse(self.svc.pen_get_scheme(ORG, y["id"])["valuation_stale"])           # 365 days
        self.clock.d = date(2027, 3, 2); self.assertTrue(self.svc.pen_get_scheme(ORG, y["id"])["valuation_stale"])

    def test_latest_confirmed_counts(self):
        x = self.open(); x = self.conf(self.val(x, "2026-02-01", "100", "100"), "valuations", 1); x = self.conf(self.val(x, "2026-03-01", "50", "100"), "valuations", 2); self.assertEqual(x["funding_ratio_pct"], "50.00")
        x = self.conf(self.val(x, "2026-01-01", "10", "100"), "valuations", 3); self.assertEqual(x["funding_ratio_pct"], "50.00")        # an earlier date never replaces it
        x = self.val(x, "2026-03-20", "99", "100"); self.assertEqual(x["funding_ratio_pct"], "50.00")                                  # waiting does not count

    def test_validation(self):
        x = self.open()
        for bad in ({"as_of": "2026-02-30"}, {"as_of": "2026-04-05"}, {"as_of": "1999-01-01"}, {"assets": "x"}, {"assets": -1}, {"assets": 5.5}, {"assets": None}, {"liabilities": "0"}, {"liabilities": "x"}, {"liabilities": True}, {"liabilities": None}, {"source_note": "short"}):
            with self.assertRaises(PensionError, msg=bad): self.val(x, **bad)
        self.assertEqual(self.val(x, assets="0")["valuations"][0]["assets"], "0.00")
        with self.assertRaises(PensionStateError): self.val(x, assets="5")


class Obligations(Base):
    def test_flags_and_flow(self):
        x = self.open(); x = self.obl(x, "File the annual return", "2026-04-20"); x = self.obl(x, "Trustee meeting", "2026-03-30"); x = self.obl(x, "Far away", "2026-09-01")
        r = x["obligations"]; self.assertEqual([(o["overdue"], o["due_soon"]) for o in r], [(False, True), (True, False), (False, False)])
        self.assertEqual((x["overdue_obligations"], x["due_soon_obligations"]), (1, 1))
        x = self.svc.pen_complete_obligation(ORG, x["id"], 2, {"completed_on": "2026-03-30", "note": "Meeting held and minuted"}, U1); self.assertEqual(x["obligations"][1]["status"], "DONE"); self.assertEqual(x["overdue_obligations"], 0)
        with self.assertRaises(PensionForbiddenError): self.conf(x, "obligations", 2, U1)
        x = self.conf(x, "obligations", 2); self.assertEqual((x["obligations"][1]["status"], x["obligations"][1]["done_late"]), ("CONFIRMED", False))

    def test_reject_sends_it_back_to_open(self):
        x = self.obl(self.open()); x = self.svc.pen_complete_obligation(ORG, x["id"], 1, {"completed_on": "2026-03-30", "note": "Return was filed online"}, U1)
        x = self.svc.pen_decide(ORG, x["id"], "obligations", 1, False, "No proof of filing was shown", U3); o = x["obligations"][0]
        self.assertEqual((o["status"], o["completed_on"], o["decision_note"]), ("OPEN", None, "No proof of filing was shown"))
        x = self.svc.pen_complete_obligation(ORG, x["id"], 1, {"completed_on": "2026-03-31", "note": "Receipt number now attached"}, U2); self.assertEqual(x["obligations"][0]["status"], "DONE")
        with self.assertRaises(PensionForbiddenError): self.conf(x, "obligations", 1, U2)

    def test_due_soon_setting_and_late_completion(self):
        x = self.obl(self.open(), due="2026-06-01"); self.assertFalse(x["obligations"][0]["due_soon"]); self.svc.pen_set_setting(ORG, {"due_soon_days": 90}, U3)
        self.assertTrue(self.svc.pen_get_scheme(ORG, x["id"])["obligations"][0]["due_soon"])
        y = self.obl(self.open(name="Second"), due="2026-03-01"); y = self.svc.pen_complete_obligation(ORG, y["id"], 1, {"completed_on": "2026-03-05", "note": "Filed a few days late"}, U1); self.assertTrue(y["obligations"][0]["done_late"])

    def test_validation(self):
        x = self.open()
        for bad in ({"title": "ab"}, {"title": None}, {"due_date": "2026-02-30"}, {"due_date": "1999-01-01"}, {"due_date": "2101-01-01"}, {"due_date": None}):
            d = dict(title="File the return", due_date="2026-04-20"); d.update(bad)
            with self.assertRaises(PensionError, msg=bad): self.svc.pen_add_obligation(ORG, x["id"], d, U1)
        x = self.obl(x)
        with self.assertRaises(PensionStateError): self.obl(x)
        for bad in ({"completed_on": "2026-04-05"}, {"completed_on": "x"}, {"note": "short"}):
            d = dict(completed_on="2026-03-30", note="Filed with the regulator"); d.update(bad)
            with self.assertRaises(PensionError, msg=bad): self.svc.pen_complete_obligation(ORG, x["id"], 1, d, U1)
        self.svc.pen_complete_obligation(ORG, x["id"], 1, dict(completed_on="2026-03-30", note="Filed with the regulator"), U1)
        with self.assertRaises(PensionStateError): self.svc.pen_complete_obligation(ORG, x["id"], 1, dict(completed_on="2026-03-30", note="Filed with the regulator"), U1)


class Conflicts(Base):
    def test_flow(self):
        x = self.open(); x = self.svc.pen_add_conflict(ORG, x["id"], dict(person_ref="TR-03", declared_on="2026-03-01", nature="Holds shares in a fund manager"), U1)
        with self.assertRaises(PensionForbiddenError): self.conf(x, "conflicts", 1, U1)
        x = self.conf(x, "conflicts", 1, U3, "Noted and managed at meetings"); self.assertEqual(x["conflicts"][0]["status"], "CONFIRMED")

    def test_validation(self):
        x = self.open()
        for bad in ({"person_ref": "x"}, {"person_ref": None}, {"declared_on": "2026-04-05"}, {"declared_on": "1999-01-01"}, {"declared_on": "x"}, {"nature": "short"}):
            d = dict(person_ref="TR-03", declared_on="2026-03-01", nature="Holds shares in a fund manager"); d.update(bad)
            with self.assertRaises(PensionError, msg=bad): self.svc.pen_add_conflict(ORG, x["id"], d, U1)


class Schemes(Base):
    def test_validation(self):
        for bad in ({"name": "ab"}, {"scheme_ref": "x"}, {"currency": "NG"}, {"currency": "n$n"}, {"scheme_type": "OTHERS"}, {"scheme_type": None}, {"start_period": "2026-04"}, {"start_period": "2006-03"}, {"start_period": "2026-13"}, {"due_day": 0}, {"due_day": 29}, {"due_day": "x"}, {"due_day": True}, {"due_day": 5.5}, {"description": "short"}):
            with self.assertRaises(PensionError, msg=bad): self.sch(**bad)
        x = self.sch(currency="ngn", scheme_type="hybrid"); self.assertEqual((x["ref"], x["currency"], x["scheme_type"], x["status"]), ("PS-001", "NGN", "HYBRID", "PROPOSED")); self.assertEqual(self.sch()["ref"], "PS-002")

    def test_decisions(self):
        x = self.sch()
        with self.assertRaises(PensionForbiddenError): self.svc.pen_approve_scheme(ORG, x["id"], {}, U1)
        with self.assertRaises(PensionForbiddenError): self.svc.pen_reject_scheme(ORG, x["id"], "Rejecting my own scheme", U1)
        with self.assertRaises(PensionError): self.svc.pen_reject_scheme(ORG, x["id"], "short", U3)
        with self.assertRaises(PensionError): self.svc.pen_approve_scheme(ORG, x["id"], {"note": "short"}, U3)
        with self.assertRaises(PensionStateError): self.con(x)
        self.assertEqual(self.svc.pen_approve_scheme(ORG, x["id"], {"note": "Trust deed checked"}, U3)["status"], "APPROVED")
        with self.assertRaises(PensionStateError): self.svc.pen_approve_scheme(ORG, x["id"], {}, U4)
        y = self.sch(); self.assertEqual(self.svc.pen_reject_scheme(ORG, y["id"], "Duplicate of another scheme", U3)["status"], "REJECTED")
        with self.assertRaises(PensionStateError): self.obl(y)

    def test_close(self):
        x = self.con(self.open())
        with self.assertRaises(PensionStateError): self.svc.pen_close_scheme(ORG, x["id"], "The scheme has wound up", U3)
        self.conf(x, "contributions", 1)
        with self.assertRaises(PensionError): self.svc.pen_close_scheme(ORG, x["id"], "short", U3)
        c = self.svc.pen_close_scheme(ORG, x["id"], "The scheme has wound up", U3); self.assertEqual((c["status"], c["close_note"]), ("CLOSED", "The scheme has wound up"))
        for f in (lambda: self.con(c, "2026-02"), lambda: self.svc.pen_close_scheme(ORG, x["id"], "Closing it a second time", U3)):
            with self.assertRaises(PensionStateError): f()

    def test_list_is_summary_only(self):
        x = self.con(self.open()); row = self.svc.pen_list_schemes(ORG)[0]
        self.assertEqual((row["contributions"], row["history"], row["pending"]), ([], [], 1)); self.assertEqual(len(self.svc.pen_list_schemes(ORG, "APPROVED")), 1); self.assertEqual(self.svc.pen_list_schemes(ORG, "PROPOSED"), [])


class Settings(Base):
    def test_settings(self):
        s = self.svc.pen_get_setting(ORG); self.assertEqual((s["funding_floor_pct"], s["valuation_stale_days"], s["due_soon_days"]), (90, 365, 30))
        for f, bad in (("funding_floor_pct", 0), ("funding_floor_pct", 301), ("funding_floor_pct", "x"), ("funding_floor_pct", 1.5), ("funding_floor_pct", True), ("valuation_stale_days", 0), ("valuation_stale_days", 1501), ("due_soon_days", 0), ("due_soon_days", 366)):
            with self.assertRaises(PensionError, msg=(f, bad)): self.svc.pen_set_setting(ORG, {f: bad}, U3)
        s = self.svc.pen_set_setting(ORG, {"due_soon_days": "45"}, U3); self.assertEqual((s["funding_floor_pct"], s["due_soon_days"]), (90, 45))


class Overview(Base):
    def test_counts_attention_and_totals(self):
        self.sch(); a = self.open(name="Scheme A"); self.con(a); self.conf(self.con(self.open(name="Scheme B", currency="USD"), "2026-01", "10", "5"), "contributions", 1)
        self.conf(self.val(a, assets="500", liabilities="1000"), "valuations", 1); self.obl(a, "Overdue thing", "2026-03-01"); self.obl(a, "Soon thing", "2026-04-10")
        r = self.sch(name="Scheme R"); self.svc.pen_reject_scheme(ORG, r["id"], "Duplicate of another scheme", U3)
        o = self.svc.pen_overview(ORG); self.assertEqual(o["counts"], {"proposed": 1, "approved": 2, "rejected": 1, "closed": 0})
        k = {x["kind"]: x["count"] for x in o["attention"]}
        self.assertEqual(k, {"SCHEMES_TO_APPROVE": 1, "ITEMS_TO_DECIDE": 1, "MISSING_CONTRIBUTIONS": 2, "BELOW_FUNDING_FLOOR": 1, "NO_VALUATION": 1, "OBLIGATIONS_OVERDUE": 1, "OBLIGATIONS_DUE_SOON": 1})
        self.assertEqual([(t["currency"], t["schemes"], t["total_contributions"]) for t in o["by_currency"]], [("NGN", 1, "0.00"), ("USD", 1, "15.00")])      # currencies are never added together

    def test_empty(self):
        o = self.svc.pen_overview(ORG); self.assertEqual((o["attention"], o["by_currency"], o["counts"]["approved"]), ([], [], 0))


class Isolation(Base):
    def test_other_company(self):
        x = self.con(self.open()); self.assertEqual(self.svc.pen_list_schemes(OTHER), [])
        for f in (lambda: self.svc.pen_get_scheme(OTHER, x["id"]), lambda: self.svc.pen_decide(OTHER, x["id"], "contributions", 1, True, {}, U3), lambda: self.svc.pen_add_contribution(OTHER, x["id"], {}, U1), lambda: self.svc.pen_close_scheme(OTHER, x["id"], "Closing from elsewhere", U3)):
            with self.assertRaises(PensionNotFoundError): f()
        self.assertEqual(self.svc.pen_add_scheme(OTHER, dict(name="Other scheme", scheme_ref="OPS-1", currency="NGN", scheme_type="OTHER", start_period="2026-01", due_day=1, description="A scheme at another company"), U1)["ref"], "PS-001")


class Audit(Base):
    def test_every_write_logged_without_content(self):
        x = self.open(name="Secret scheme name"); x = self.con(x, "2026-01", "7777.77", "3333.33"); self.conf(x, "contributions", 1, U3, "Matches the bank statement"); x = self.val(x, assets="1234567", liabilities="2345678")
        self.svc.pen_decide(ORG, x["id"], "valuations", 1, False, "The figure was a typing slip", U3); x = self.obl(x, "Secret obligation title"); x = self.svc.pen_complete_obligation(ORG, x["id"], 1, {"completed_on": "2026-03-30", "note": "Chinedu filed it online"}, U1)
        self.conf(x, "obligations", 1); x = self.svc.pen_add_conflict(ORG, x["id"], dict(person_ref="TR-77", declared_on="2026-03-01", nature="Holds shares in a fund manager"), U1); self.conf(x, "conflicts", 1)
        y = self.sch(name="Rejected scheme"); self.svc.pen_reject_scheme(ORG, y["id"], "Duplicate of another scheme", U3); self.svc.pen_set_setting(ORG, {"due_soon_days": 10}, U3)
        self.svc.pen_close_scheme(ORG, x["id"], "The scheme has wound up", U3)
        acts = {e[0] for e in self.events}
        for a in ("PENSION_SCHEME_PROPOSED", "PENSION_SCHEME_APPROVED", "PENSION_SCHEME_REJECTED", "PENSION_SCHEME_CLOSED", "PENSION_CONTRIBUTION_RECORDED", "PENSION_CONTRIBUTION_CONFIRMED", "PENSION_VALUATION_RECORDED", "PENSION_VALUATION_REJECTED",
                  "PENSION_OBLIGATION_RECORDED", "PENSION_OBLIGATION_DONE", "PENSION_OBLIGATION_CONFIRMED", "PENSION_CONFLICT_RECORDED", "PENSION_CONFLICT_CONFIRMED", "PENSION_SETTING_SET"): self.assertIn(a, acts)
        blob = " ".join(str(e) for e in self.events)
        for secret in ("Secret scheme", "TRUST-1", "7777", "3333", "1234567", "Chinedu", "Secret obligation", "TR-77", "fund manager", "Matches the bank", "typing slip", "Duplicate of", "wound up"): self.assertNotIn(secret, blob)

    def test_failed_actions_are_not_logged(self):
        with self.assertRaises(PensionError): self.sch(name="ab")
        x = self.open(); n = len(self.events)
        with self.assertRaises(PensionError): self.con(x, "2026-13")
        with self.assertRaises(PensionForbiddenError): self.svc.pen_approve_scheme(ORG, self.sch()["id"], {}, U1)
        self.assertEqual(len(self.events), n + 1)                                                          # only the scheme proposed above


class Permissions(unittest.TestCase):
    def test_roles(self):
        has = lambda r, p: p in ROLE_PERMISSIONS[r]
        for r in (Role.OWNER, Role.ADMINISTRATOR, Role.MANAGER, Role.AUDITOR): self.assertTrue(has(r, PEN_PREPARE), r)
        for r in (Role.OWNER, Role.APPROVER, Role.MANAGER): self.assertTrue(has(r, PEN_APPROVE), r)
        for r in (Role.ACCOUNTANT, Role.REVIEWER, Role.EXTERNAL_AUDITOR, Role.READ_ONLY, Role.DONOR, Role.REGULATOR, Role.INVESTOR_REVIEWER): self.assertFalse(has(r, PEN_PREPARE) or has(r, PEN_APPROVE), r)

    def test_anyone_who_can_prepare_or_approve_can_view(self):
        for r, perms in ROLE_PERMISSIONS.items():
            if PEN_PREPARE in perms or PEN_APPROVE in perms: self.assertIn(AUDIT_READ, perms, r)


class RouterGuards(unittest.TestCase):
    SRC = os.path.join(os.path.dirname(__file__), "..", "src", "asavexa", "api", "routers", "pension.py")

    def test_every_write_has_the_right_guard(self):
        tree = ast.parse(open(self.SRC).read()); named = {"_prepare": "PEN_PREPARE", "_approve": "PEN_APPROVE"}; g = {}
        for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.decorator_list]:
            verbs, guards = set(), set()
            for dec in fn.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute): verbs.add(dec.func.attr)
                for kw in getattr(dec, "keywords", []):
                    if kw.arg == "dependencies": guards |= {named[e.id] for e in kw.value.elts if isinstance(e, ast.Name) and e.id in named}
            g[fn.name] = (verbs, guards)
        approve = {"set_setting", "approve_scheme", "reject_scheme", "close_scheme", "confirm_contribution", "reject_contribution", "confirm_valuation", "reject_valuation", "confirm_obligation", "reject_obligation", "confirm_conflict", "reject_conflict"}
        prepare = {"add_scheme", "add_contribution", "add_valuation", "add_obligation", "complete_obligation", "add_conflict"}
        for n in approve: self.assertEqual(g[n][1], {"PEN_APPROVE"}, n)
        for n in prepare: self.assertEqual(g[n][1], {"PEN_PREPARE"}, n)
        for n, (verbs, guards) in g.items():
            if verbs == {"get"}: self.assertEqual(guards, set(), n)
            else: self.assertIn(n, approve | prepare, f"{n} writes but has no pension guard")
        src = open(self.SRC).read(); self.assertIn("dependencies=[Depends(require_permission(AUDIT_READ))]", src); self.assertNotIn("org_id", src)


if __name__ == "__main__":
    unittest.main()
