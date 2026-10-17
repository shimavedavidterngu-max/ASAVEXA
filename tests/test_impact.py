"""Impact measurement: indicators, readings, exact progress and expected progress, flags, different-person decisions, isolation, audit and permissions."""
import ast
import os
import unittest
from datetime import date, datetime, timezone
from fractions import Fraction

from analysis_fixture import ORG, OTHER, World
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.permissions import AUDIT_READ, IMP_APPROVE, IMP_PREPARE, ROLE_PERMISSIONS
from asavexa.impact.errors import ImpactError, ImpactForbiddenError, ImpactNotFoundError, ImpactStateError
from asavexa.impact.service import ImpactService

U1, U2, U3, U4 = "user-1", "user-2", "user-3", "user-4"   # U1 and U2 prepare, U3 and U4 approve


class Clock:
    def __init__(self): self.d = date(2026, 3, 31)
    def __call__(self): return datetime(self.d.year, self.d.month, self.d.day, 9, tzinfo=timezone.utc)


class Base(unittest.TestCase):
    def setUp(self):
        self.w = World(); self.clock = Clock(); self.events = []
        self.svc = ImpactService(self.w.store, None, log=lambda *a: self.events.append(a), now=self.clock)

    def ind(self, actor=U1, **kw):
        d = dict(title="Households with clean water", programme_ref="WASH-1", unit="households", direction="INCREASE", baseline="200", target="1000", baseline_date="2026-01-01", target_date="2026-12-31"); d.update(kw)
        return self.svc.imp_add_indicator(ORG, d, actor)

    def open(self, actor=U1, approver=U3, **kw):
        x = self.ind(actor, **kw); return self.svc.imp_approve_indicator(ORG, x["id"], {}, approver)

    def read(self, x, value="380", period="2026-03-31", actor=U1, **kw):
        d = dict(period_end=period, value=value, source_note="Counted from the field visit register"); d.update(kw); return self.svc.imp_add_reading(ORG, x["id"], d, actor)

    def confirmed(self, x, value="380", period="2026-03-31"):
        x = self.read(x, value, period); return self.svc.imp_confirm_reading(ORG, x["id"], len(x["readings"]), {}, U3)


class Progress(Base):
    def test_known_example(self):
        x = self.open(); self.assertEqual((x["state"], x["expected_pct"], x["progress_pct"]), ("NO_DATA", "24.45", None))      # 89 of 364 days
        x = self.confirmed(x, "380"); self.assertEqual((x["progress_pct"], x["state"], x["latest_value"], x["latest_period_end"]), ("22.50", "ON_TRACK", "380.00", "2026-03-31"))

    def test_states(self):
        for value, pct, state in (("250", "6.25", "BEHIND"), ("284", "10.50", "BEHIND"), ("288", "11.00", "BEHIND"), ("320", "15.00", "ON_TRACK"), ("200", "0.00", "BEHIND"), ("100", "-12.50", "BEHIND"), ("1000", "100.00", "ACHIEVED"), ("1100", "112.50", "ACHIEVED")):
            x = self.confirmed(self.open(), value); self.assertEqual((x["progress_pct"], x["state"]), (pct, state), value)

    def test_tolerance_boundary_uses_exact_fractions(self):
        # expected is 89/364 of 100 = 24.4505...; with a tolerance of 10 the cut-off progress is 14.4505... percent, i.e. a value of 315.604...
        x = self.confirmed(self.open(), "315.60"); self.assertEqual(x["state"], "BEHIND"); x = self.confirmed(self.open(), "315.61"); self.assertEqual(x["state"], "ON_TRACK")
        self.svc.imp_set_setting(ORG, {"tolerance_points": 0}, U3); x = self.confirmed(self.open(), "395"); self.assertEqual(x["state"], "BEHIND")      # 24.375 percent is below 24.4505
        x = self.confirmed(self.open(), "396"); self.assertEqual(x["state"], "ON_TRACK")                                                                # 24.5 percent

    def test_decrease_direction(self):
        x = self.open(direction="DECREASE", baseline="40", target="10", unit="percent", title="Children under weight"); x = self.confirmed(x, "25"); self.assertEqual((x["progress_pct"], x["state"]), ("50.00", "ON_TRACK"))
        x = self.confirmed(self.open(direction="DECREASE", baseline="40", target="10", title="Children under weight 2"), "45"); self.assertEqual(x["progress_pct"], "-16.67")
        x = self.confirmed(self.open(direction="DECREASE", baseline="40", target="10", title="Children under weight 3"), "10"); self.assertEqual((x["progress_pct"], x["state"]), ("100.00", "ACHIEVED"))

    def test_every_figure_matches_an_independent_calculation(self):
        for base, tgt, val in (("0", "100", "37.37"), ("12.5", "99.99", "50.01"), ("1000000", "5000000", "2345678.91"), ("80", "20", "33.33")):
            d = "INCREASE" if Fraction(tgt) > Fraction(base) else "DECREASE"
            x = self.confirmed(self.open(direction=d, baseline=base, target=tgt, title=f"Indicator {base} {tgt}"), val); p = (Fraction(val) - Fraction(base)) / (Fraction(tgt) - Fraction(base)) * 100
            n = p.numerator * 100; q = (abs(n) * 2 + p.denominator) // (2 * p.denominator); self.assertEqual(x["progress_pct"], f"{(q if n >= 0 else -q) / 100:.2f}", (base, tgt, val))

    def test_the_latest_period_counts_and_only_confirmed_readings(self):
        x = self.confirmed(self.open(), "300", "2026-02-28"); x = self.confirmed(x, "380", "2026-03-31"); self.assertEqual(x["latest_value"], "380.00")
        x = self.confirmed(x, "320", "2026-03-15"); self.assertEqual((x["latest_value"], x["latest_period_end"]), ("380.00", "2026-03-31"))      # an earlier period does not replace it
        y = self.read(x, "999", "2026-03-30"); self.assertEqual(y["latest_value"], "380.00")                                                      # proposed does not count
        y = self.svc.imp_reject_reading(ORG, y["id"], 4, "The figure was a typing slip", U3); self.assertEqual(y["latest_value"], "380.00")

    def test_expected_progress_over_time(self):
        x = self.open(); iid = x["id"]
        for d, want in ((date(2026, 1, 1), "0.00"), (date(2026, 7, 2), "50.00"), (date(2026, 12, 31), "100.00"), (date(2027, 6, 1), "100.00")):
            self.clock.d = d; self.assertEqual(self.svc.imp_get_indicator(ORG, iid)["expected_pct"], want, d)

    def test_target_date_passed_and_stale(self):
        x = self.confirmed(self.open(), "380"); iid = x["id"]
        self.clock.d = date(2026, 7, 29); v = self.svc.imp_get_indicator(ORG, iid); self.assertFalse(v["stale"])           # 120 days
        self.clock.d = date(2026, 7, 30); v = self.svc.imp_get_indicator(ORG, iid); self.assertTrue(v["stale"])
        self.clock.d = date(2026, 12, 31); self.assertEqual(self.svc.imp_get_indicator(ORG, iid)["state"], "BEHIND")
        self.clock.d = date(2027, 1, 1); self.assertEqual(self.svc.imp_get_indicator(ORG, iid)["state"], "OVERDUE")
        self.assertEqual(self.svc.imp_get_indicator(ORG, self.confirmed(self.open(title="Never read"), "1000")["id"])["state"], "ACHIEVED")
        n = self.open(title="No readings at all"); self.assertEqual(self.svc.imp_get_indicator(ORG, n["id"])["state"], "OVERDUE")

    def test_progress_exists_only_on_open_indicators(self):
        x = self.ind(); self.assertEqual((x["state"], x["progress_pct"], x["expected_pct"]), (None, None, None))


class Validation(Base):
    def test_indicator(self):
        for bad in ({"title": "ab"}, {"programme_ref": "x"}, {"unit": ""}, {"unit": "u" * 31}, {"direction": "UP"}, {"direction": None}, {"baseline": "abc"}, {"baseline": 5.5}, {"baseline": True}, {"baseline": "-1"}, {"baseline": "1.234"}, {"baseline": "1,5"}, {"target": None},
                    {"target": "200"}, {"target": "100"}, {"direction": "DECREASE"}, {"baseline_date": "2026-02-30"}, {"target_date": "2026-01-01"}, {"target_date": "2025-12-31"}, {"target_date": "2037-01-02"}):
            with self.assertRaises(ImpactError, msg=bad): self.ind(**bad)
        x = self.ind(baseline="0", unit="people"); self.assertEqual((x["ref"], x["baseline"], x["status"], x["direction"]), ("IM-001", "0.00", "PROPOSED", "INCREASE")); self.assertEqual(self.ind()["ref"], "IM-002")

    def test_reading(self):
        x = self.open()
        for bad in ({"period_end": "2026-02-30"}, {"period_end": "2026-04-05"}, {"period_end": "2025-12-31"}, {"period_end": None}, {"value": "x"}, {"value": -1}, {"value": 5.5}, {"value": None}, {"value": True}, {"value": "1.234"}, {"source_note": "short"}):
            with self.assertRaises(ImpactError, msg=bad): self.read(x, **bad)
        self.assertEqual(self.read(x, period="2026-04-01", value="0")["readings"][0]["value"], "0.00")                                         # a day of leeway; zero is a real value

    def test_one_live_reading_per_period(self):
        x = self.open(); x = self.read(x)
        with self.assertRaises(ImpactStateError): self.read(x, value="390")
        x = self.svc.imp_reject_reading(ORG, x["id"], 1, "The figure was a typing slip", U3); x = self.read(x, value="390"); x = self.svc.imp_confirm_reading(ORG, x["id"], 2, {}, U3)
        with self.assertRaises(ImpactStateError): self.read(x, value="400")


class Workflow(Base):
    def test_indicator_decisions(self):
        x = self.ind()
        with self.assertRaises(ImpactForbiddenError): self.svc.imp_approve_indicator(ORG, x["id"], {}, U1)
        with self.assertRaises(ImpactForbiddenError): self.svc.imp_reject_indicator(ORG, x["id"], "Rejecting my own indicator", U1)
        with self.assertRaises(ImpactError): self.svc.imp_reject_indicator(ORG, x["id"], "short", U3)
        with self.assertRaises(ImpactError): self.svc.imp_approve_indicator(ORG, x["id"], {"note": "short"}, U3)
        with self.assertRaises(ImpactStateError): self.read(x)
        self.assertEqual(self.svc.imp_approve_indicator(ORG, x["id"], {"note": "Baseline matches the survey"}, U3)["status"], "APPROVED")
        for f in (lambda: self.svc.imp_approve_indicator(ORG, x["id"], {}, U4), lambda: self.svc.imp_reject_indicator(ORG, x["id"], "Trying to reject it later", U4)):
            with self.assertRaises(ImpactStateError): f()
        y = self.ind(); self.assertEqual(self.svc.imp_reject_indicator(ORG, y["id"], "Duplicate of another indicator", U3)["status"], "REJECTED")
        with self.assertRaises(ImpactStateError): self.read(y)

    def test_reading_decisions(self):
        x = self.read(self.open())
        with self.assertRaises(ImpactForbiddenError): self.svc.imp_confirm_reading(ORG, x["id"], 1, {}, U1)
        with self.assertRaises(ImpactForbiddenError): self.svc.imp_reject_reading(ORG, x["id"], 1, "Rejecting my own reading", U1)
        with self.assertRaises(ImpactError): self.svc.imp_reject_reading(ORG, x["id"], 1, "short", U3)
        for bad in ("x", None, True, 1.5):
            with self.assertRaises(ImpactError): self.svc.imp_confirm_reading(ORG, x["id"], bad, {}, U3)
        with self.assertRaises(ImpactNotFoundError): self.svc.imp_confirm_reading(ORG, x["id"], 9, {}, U3)
        r = self.svc.imp_confirm_reading(ORG, x["id"], 1, {"note": "Matches the register"}, U3)["readings"][0]; self.assertEqual((r["status"], r["decision_note"]), ("CONFIRMED", "Matches the register"))
        with self.assertRaises(ImpactStateError): self.svc.imp_confirm_reading(ORG, x["id"], 1, {}, U4)

    def test_close(self):
        x = self.read(self.open())
        with self.assertRaises(ImpactStateError): self.svc.imp_close_indicator(ORG, x["id"], "Programme has finished", U3)       # a reading waits
        self.svc.imp_confirm_reading(ORG, x["id"], 1, {}, U3)
        with self.assertRaises(ImpactError): self.svc.imp_close_indicator(ORG, x["id"], "short", U3)
        c = self.svc.imp_close_indicator(ORG, x["id"], "Programme has finished", U3); self.assertEqual((c["status"], c["close_note"], c["state"]), ("CLOSED", "Programme has finished", None))
        with self.assertRaises(ImpactStateError): self.read(c, period="2026-03-30")
        with self.assertRaises(ImpactStateError): self.svc.imp_close_indicator(ORG, x["id"], "Closing it a second time", U3)

    def test_list_summary_only(self):
        x = self.read(self.open()); row = self.svc.imp_list_indicators(ORG)[0]; self.assertEqual((row["readings"], row["history"], row["pending_readings"]), ([], [], 1))
        self.assertEqual(len(self.svc.imp_list_indicators(ORG, "APPROVED")), 1); self.assertEqual(self.svc.imp_list_indicators(ORG, "PROPOSED"), [])


class Settings(Base):
    def test_settings(self):
        s = self.svc.imp_get_setting(ORG); self.assertEqual((s["tolerance_points"], s["stale_days"]), (10, 120))
        for f, bad in (("tolerance_points", -1), ("tolerance_points", 101), ("tolerance_points", "x"), ("tolerance_points", 1.5), ("tolerance_points", True), ("stale_days", 0), ("stale_days", 731)):
            with self.assertRaises(ImpactError, msg=(f, bad)): self.svc.imp_set_setting(ORG, {f: bad}, U3)
        s = self.svc.imp_set_setting(ORG, {"stale_days": "30"}, U3); self.assertEqual((s["tolerance_points"], s["stale_days"]), (10, 30))
        s = self.svc.imp_set_setting(ORG, {"tolerance_points": 0}, U3); self.assertEqual(s["tolerance_points"], 0)


class Overview(Base):
    def test_counts_and_attention(self):
        self.ind(); a = self.confirmed(self.open(title="Behind one"), "250"); self.confirmed(self.open(title="On track one"), "380"); self.open(title="No data one"); self.confirmed(self.open(title="Done one"), "1000")
        self.read(self.open(title="Waiting reading")); r = self.ind(title="To reject"); self.svc.imp_reject_indicator(ORG, r["id"], "Duplicate of another one", U3)
        c = self.confirmed(self.open(title="Closed one"), "300"); self.svc.imp_close_indicator(ORG, c["id"], "Programme has finished", U3)
        o = self.svc.imp_overview(ORG); self.assertEqual(o["counts"], {"proposed": 1, "approved": 5, "rejected": 1, "closed": 1}); self.assertEqual(o["states"], {"NO_DATA": 2, "ACHIEVED": 1, "ON_TRACK": 1, "BEHIND": 1, "OVERDUE": 0})
        kinds = {x["kind"]: x["count"] for x in o["attention"]}; self.assertEqual(kinds, {"INDICATORS_TO_APPROVE": 1, "READINGS_TO_CONFIRM": 1, "BEHIND_TARGET": 1, "NO_READINGS": 2})

    def test_stale_and_overdue_flags(self):
        self.confirmed(self.open(), "380"); self.clock.d = date(2026, 8, 1); kinds = [x["kind"] for x in self.svc.imp_overview(ORG)["attention"]]; self.assertIn("READINGS_STALE", kinds)
        self.clock.d = date(2027, 2, 1); kinds = [x["kind"] for x in self.svc.imp_overview(ORG)["attention"]]; self.assertIn("TARGET_PASSED", kinds)

    def test_empty(self):
        o = self.svc.imp_overview(ORG); self.assertEqual((o["attention"], o["counts"]["approved"], sum(o["states"].values())), ([], 0, 0))


class Isolation(Base):
    def test_other_company(self):
        x = self.read(self.open()); self.assertEqual(self.svc.imp_list_indicators(OTHER), [])
        for f in (lambda: self.svc.imp_get_indicator(OTHER, x["id"]), lambda: self.svc.imp_confirm_reading(OTHER, x["id"], 1, {}, U3), lambda: self.svc.imp_add_reading(OTHER, x["id"], {}, U1), lambda: self.svc.imp_close_indicator(OTHER, x["id"], "Closing from elsewhere", U3)):
            with self.assertRaises(ImpactNotFoundError): f()
        self.assertEqual(self.svc.imp_add_indicator(OTHER, dict(title="Other indicator", programme_ref="OPS-1", unit="units", direction="INCREASE", baseline="1", target="2", baseline_date="2026-01-01", target_date="2026-12-31"), U1)["ref"], "IM-001")


class Audit(Base):
    def test_every_write_logged_without_content(self):
        x = self.open(title="Secret indicator title"); x = self.read(x, "380", source_note="Counted by Chinedu at the clinic"); self.svc.imp_confirm_reading(ORG, x["id"], 1, {"note": "Matches the register"}, U3)
        x = self.read(x, "390", "2026-03-30"); self.svc.imp_reject_reading(ORG, x["id"], 2, "The figure was a typing slip", U3)
        y = self.ind(title="Rejected indicator"); self.svc.imp_reject_indicator(ORG, y["id"], "Duplicate of another one", U3); self.svc.imp_set_setting(ORG, {"stale_days": 60}, U3); self.svc.imp_close_indicator(ORG, x["id"], "Programme has finished", U3)
        acts = [e[0] for e in self.events]
        for a in ("IMPACT_INDICATOR_PROPOSED", "IMPACT_INDICATOR_APPROVED", "IMPACT_INDICATOR_REJECTED", "IMPACT_INDICATOR_CLOSED", "IMPACT_READING_RECORDED", "IMPACT_READING_CONFIRMED", "IMPACT_READING_REJECTED", "IMPACT_SETTING_SET"): self.assertIn(a, acts)
        blob = " ".join(str(e) for e in self.events)
        for secret in ("Secret indicator", "WASH-1", "households", "Chinedu", "380", "Matches the register", "typing slip", "Duplicate of", "Programme has finished"): self.assertNotIn(secret, blob)

    def test_failed_actions_are_not_logged(self):
        with self.assertRaises(ImpactError): self.ind(title="ab")
        x = self.open(); n = len(self.events)
        with self.assertRaises(ImpactError): self.read(x, value="x")
        with self.assertRaises(ImpactForbiddenError): self.svc.imp_approve_indicator(ORG, self.ind()["id"], {}, U1)
        self.assertEqual(len(self.events), n + 1)                                                                    # only the indicator proposed above


class Permissions(unittest.TestCase):
    def test_roles(self):
        has = lambda r, p: p in ROLE_PERMISSIONS[r]
        for r in (Role.OWNER, Role.ADMINISTRATOR, Role.MANAGER, Role.AUDITOR): self.assertTrue(has(r, IMP_PREPARE), r)
        for r in (Role.OWNER, Role.APPROVER, Role.MANAGER): self.assertTrue(has(r, IMP_APPROVE), r)
        for r in (Role.ACCOUNTANT, Role.REVIEWER, Role.EXTERNAL_AUDITOR, Role.READ_ONLY, Role.DONOR, Role.REGULATOR, Role.INVESTOR_REVIEWER): self.assertFalse(has(r, IMP_PREPARE) or has(r, IMP_APPROVE), r)

    def test_anyone_who_can_prepare_or_approve_can_view(self):
        for r, perms in ROLE_PERMISSIONS.items():
            if IMP_PREPARE in perms or IMP_APPROVE in perms: self.assertIn(AUDIT_READ, perms, r)


class RouterGuards(unittest.TestCase):
    SRC = os.path.join(os.path.dirname(__file__), "..", "src", "asavexa", "api", "routers", "impact.py")

    def test_every_write_has_the_right_guard(self):
        tree = ast.parse(open(self.SRC).read()); named = {"_prepare": "IMP_PREPARE", "_approve": "IMP_APPROVE"}; g = {}
        for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.decorator_list]:
            verbs, guards = set(), set()
            for dec in fn.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute): verbs.add(dec.func.attr)
                for kw in getattr(dec, "keywords", []):
                    if kw.arg == "dependencies": guards |= {named[e.id] for e in kw.value.elts if isinstance(e, ast.Name) and e.id in named}
            g[fn.name] = (verbs, guards)
        approve = {"set_setting", "approve_indicator", "reject_indicator", "close_indicator", "confirm_reading", "reject_reading"}; prepare = {"add_indicator", "add_reading"}
        for n in approve: self.assertEqual(g[n][1], {"IMP_APPROVE"}, n)
        for n in prepare: self.assertEqual(g[n][1], {"IMP_PREPARE"}, n)
        for n, (verbs, guards) in g.items():
            if verbs == {"get"}: self.assertEqual(guards, set(), n)
            else: self.assertIn(n, approve | prepare, f"{n} writes but has no impact measurement guard")
        src = open(self.SRC).read(); self.assertIn("dependencies=[Depends(require_permission(AUDIT_READ))]", src); self.assertNotIn("org_id", src)


if __name__ == "__main__":
    unittest.main()
