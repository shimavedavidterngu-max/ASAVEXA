"""ESG and carbon: emission records, verification by a different person, targets, setting, isolation, audit, permissions."""
import ast
import os
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from fractions import Fraction

from analysis_fixture import ORG, OTHER, World
from asavexa.esg.errors import EsgError, EsgForbiddenError, EsgNotFoundError, EsgStateError
from asavexa.esg.service import EsgService, refnum
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.permissions import AUDIT_READ, ESG_APPROVE, ESG_PREPARE, ROLE_PERMISSIONS

U1, U2, U3, U4 = "user-1", "user-2", "user-3", "user-4"   # U1 and U2 prepare, U3 and U4 approve


class Clock:
    def __init__(self): self.d = date(2026, 3, 10)
    def __call__(self): return datetime(self.d.year, self.d.month, self.d.day, 9, tzinfo=timezone.utc)


def half_up(fr, places):
    s = fr * 10 ** places; n = s.numerator * 2 + s.denominator
    return Decimal(n // (2 * s.denominator)) / Decimal(10 ** places)


class Base(unittest.TestCase):
    def setUp(self):
        self.w = World(); self.clock = Clock(); self.events = []
        self.svc = EsgService(self.w.store, None, log=lambda *a: self.events.append(a), now=self.clock)

    def ent(self, actor=U1, **kw):
        d = dict(scope="SCOPE_1", category="FUEL", description="Diesel for the generator", period_start="2025-01-01", period_end="2025-12-31", quantity="1250.5", unit="litres", factor="2.68", factor_source="National factor table 2024", factor_year=2024); d.update(kw)
        return self.svc.es_add_entry(ORG, d, actor)

    def ver(self, e, actor=U3): return self.svc.es_verify_entry(ORG, e["id"], {}, actor)

    def tgt(self, actor=U1, **kw):
        d = dict(label="Cut total emissions", scope="ALL", baseline_year=2024, baseline_tonnes="1250.500", reduction_pct="42.5", target_year=2025); d.update(kw)
        return self.svc.es_add_target(ORG, d, actor)


class Entries(Base):
    def test_arithmetic_is_exact_against_an_oracle(self):
        e = self.ent(); want = half_up(Fraction(Decimal("1250.5")) * Fraction(Decimal("2.68")), 2)
        self.assertEqual((e["ref"], e["kg_co2e"], e["status"], e["year"], e["tonnes"]), ("ER-001", str(want), "PROPOSED", 2025, "3.351")); self.assertEqual(e["kg_co2e"], "3351.34")
        for q, f in (("0.0001", "0.000001"), ("999999999999", "999999.999999"), ("7.1234", "0.375"), ("0.5", "0.01")):
            try: r = self.ent(quantity=q, factor=f)["kg_co2e"]
            except EsgError: continue
            self.assertEqual(Decimal(r), half_up(Fraction(Decimal(q)) * Fraction(Decimal(f)), 2), (q, f))

    def test_validation(self):
        for bad in ({"scope": "SCOPE_4"}, {"category": "AIR"}, {"description": "abc"}, {"period_start": "2025-02-30"}, {"period_end": "2024-12-31"}, {"period_end": "2026-01-02", "period_start": "2025-12-01"}, {"period_end": "2027-01-01", "period_start": "2027-01-01"},
                    {"quantity": "0"}, {"quantity": 5.5}, {"quantity": "1.23456"}, {"quantity": "１２３"}, {"quantity": "1,00"}, {"unit": ""}, {"factor": "0"}, {"factor": 2.68}, {"factor": "1.2345678"}, {"factor_source": "abc"}, {"factor_year": "1980"}, {"factor_year": "2028"}, {"factor_year": "x"},
                    {"quantity": "0.0001", "factor": "0.001"}):
            with self.assertRaises(EsgError, msg=str(bad)): self.ent(**bad)
        self.assertEqual(self.ent(quantity="1,250.5")["quantity"], "1250.5")

    def test_numbering_per_company_and_failed_does_not_use_one(self):
        with self.assertRaises(EsgError): self.ent(quantity="0")
        self.assertEqual(self.ent()["ref"], "ER-001"); self.assertEqual(self.ent()["ref"], "ER-002")
        self.assertEqual(self.svc.es_add_entry(OTHER, dict(scope="SCOPE_2", category="ELECTRICITY", description="Grid power", period_start="2025-01-01", period_end="2025-06-30", quantity="10", unit="kWh", factor="0.4", factor_source="Grid operator 2024", factor_year=2024), U1)["ref"], "ER-001")
        self.assertEqual(refnum({"ref": "ER-010"}), 10)

    def test_verify_and_reject(self):
        e = self.ent(); v = self.svc.es_verify_entry(ORG, e["id"], {"note": "Checked against the invoices"}, U3); self.assertEqual((v["status"], v["decided_by"]), ("VERIFIED", U3))
        with self.assertRaises(EsgStateError): self.svc.es_reject_entry(ORG, e["id"], "Trying to reject it later", U4)
        with self.assertRaises(EsgStateError): self.ver(e, U4)
        r = self.ent(); 
        with self.assertRaises(EsgError): self.svc.es_reject_entry(ORG, r["id"], "short", U3)
        self.assertEqual(self.svc.es_reject_entry(ORG, r["id"], "Quantity does not match invoices", U3)["status"], "REJECTED")
        with self.assertRaises(EsgError): self.svc.es_verify_entry(ORG, self.ent()["id"], {"note": "ok"}, U3)

    def test_two_person_rule_for_every_role(self):
        e = self.ent(actor=U3)
        with self.assertRaises(EsgForbiddenError): self.ver(e, U3)
        with self.assertRaises(EsgForbiddenError): self.svc.es_reject_entry(ORG, e["id"], "Rejecting my own record", U3)
        self.assertEqual(self.ver(e, U4)["status"], "VERIFIED")

    def test_old_factor_flag_and_setting(self):
        e = self.ent(factor_year=2018); self.assertFalse(self.svc.es_get_entry(ORG, e["id"])["old_factor"]); self.ver(e)
        self.assertTrue(self.svc.es_get_entry(ORG, e["id"])["old_factor"])            # 2025 - 2018 = 7 > 5
        self.svc.es_set_setting(ORG, {"factor_max_age_years": 7}, U3); self.assertFalse(self.svc.es_get_entry(ORG, e["id"])["old_factor"])
        for bad in (0, 21, "x", 2.5, True):
            with self.assertRaises(EsgError, msg=str(bad)): self.svc.es_set_setting(ORG, {"factor_max_age_years": bad}, U3)


class Targets(Base):
    def test_target_arithmetic(self):
        t = self.tgt(); want = half_up(Fraction(Decimal("1250.5")) * (100 - Fraction(Decimal("42.5"))) / 100, 3)
        self.assertEqual((t["ref"], t["target_tonnes"], t["status"], t["reduction_pct"], t["baseline_tonnes"]), ("TG-001", str(want), "PROPOSED", "42.5", "1250.5")); self.assertEqual(t["target_tonnes"], "719.038")

    def test_validation(self):
        for bad in ({"label": "ab"}, {"scope": "SCOPE_9"}, {"baseline_year": "1980"}, {"baseline_year": "2099"}, {"target_year": "2024"}, {"target_year": "2101"}, {"baseline_tonnes": "0"}, {"baseline_tonnes": 5.5}, {"baseline_tonnes": "1.2345"},
                    {"reduction_pct": "100.01"}, {"reduction_pct": "0"}, {"reduction_pct": "1.234"}, {"reduction_pct": -5}):
            with self.assertRaises(EsgError, msg=str(bad)): self.tgt(**bad)
        self.assertEqual(self.tgt(reduction_pct="100")["target_tonnes"], "0.000")

    def test_progress_uses_only_verified_entries_of_the_year_and_scope(self):
        e1 = self.ent(); self.ver(e1)                                                    # 3351.34 kg, 2025, scope 1
        e2 = self.ent(scope="SCOPE_2", category="ELECTRICITY", quantity="1000", factor="0.5", factor_year=2024); self.ver(e2)   # 500.00 kg
        self.ent(quantity="9999")                                                        # proposed: not counted
        r = self.ent(); self.svc.es_reject_entry(ORG, r["id"], "Duplicate of ER-001 entered twice", U3)   # rejected: not counted
        self.ver(self.ent(period_start="2024-01-01", period_end="2024-12-31", quantity="100"))           # other year
        t = self.tgt(baseline_tonnes="4.000", reduction_pct="10"); v = self.svc.es_approve_target(ORG, t["id"], {}, U3)
        self.assertEqual((v["status"], v["actual_tonnes"], v["target_tonnes"]), ("APPROVED", "3.851", "3.600")); self.assertFalse(v["within_target"]); self.assertEqual(v["change_vs_baseline_pct"], "-3.73")
        s1 = self.tgt(scope="SCOPE_1", baseline_tonnes="4.000", reduction_pct="10"); self.assertEqual(self.svc.es_list_targets(ORG)[-1]["actual_tonnes"], "3.351"); self.assertTrue(self.svc.es_list_targets(ORG)[-1]["within_target"])
        s2 = self.tgt(scope="SCOPE_2", baseline_tonnes="1.000", reduction_pct="50"); self.assertEqual(self.svc.es_list_targets(ORG)[-1]["actual_tonnes"], "0.500"); self.assertTrue(self.svc.es_list_targets(ORG)[-1]["within_target"])

    def test_two_person_rule(self):
        t = self.tgt(actor=U3)
        with self.assertRaises(EsgForbiddenError): self.svc.es_approve_target(ORG, t["id"], {}, U3)
        with self.assertRaises(EsgForbiddenError): self.svc.es_reject_target(ORG, t["id"], "Rejecting my own target", U3)
        with self.assertRaises(EsgError): self.svc.es_reject_target(ORG, t["id"], "short", U4)
        self.assertEqual(self.svc.es_reject_target(ORG, t["id"], "The baseline is not agreed yet", U4)["status"], "REJECTED")
        with self.assertRaises(EsgStateError): self.svc.es_approve_target(ORG, t["id"], {}, U4)


class Overview(Base):
    def test_totals_by_year_and_scope(self):
        self.ver(self.ent()); self.ver(self.ent(scope="SCOPE_3", category="TRAVEL", quantity="200", unit="km", factor="0.17", factor_year=2023)); self.ver(self.ent(period_start="2024-01-01", period_end="2024-06-30", quantity="10", factor="1"))
        self.ent(); t = self.tgt(); o = self.svc.es_overview(ORG)
        y = o["years"][0]; self.assertEqual((y["year"], y["total_kg"], y["total_tonnes"], y["scopes"]["SCOPE_1"]["kg"], y["scopes"]["SCOPE_3"]["kg"], y["scopes"]["SCOPE_2"]["kg"]), (2025, "3385.34", "3.385", "3351.34", "34.00", "0.00"))
        self.assertEqual((o["years"][1]["year"], o["years"][1]["total_kg"]), (2024, "10.00"))
        self.assertEqual({a["kind"]: a["count"] for a in o["attention"]}, {"ENTRIES_TO_VERIFY": 1, "TARGETS_TO_DECIDE": 1})
        self.assertEqual((o["counts"]["entries_verified"], o["counts"]["entries_proposed"], o["counts"]["targets_proposed"]), (3, 1, 1)); self.assertEqual(o["targets"], [])

    def test_empty(self):
        o = self.svc.es_overview(ORG); self.assertEqual((o["years"], o["attention"], o["targets"]), ([], [], []))

    def test_old_factor_attention(self):
        self.ver(self.ent(factor_year=2015)); self.assertIn("OLD_FACTORS", [a["kind"] for a in self.svc.es_overview(ORG)["attention"]])


class Isolation(Base):
    def test_other_company(self):
        e = self.ent(); t = self.tgt()
        self.assertEqual((self.svc.es_list_entries(OTHER), self.svc.es_list_targets(OTHER)), ([], [])); self.assertEqual(self.svc.es_overview(OTHER)["years"], [])
        for f in (lambda: self.svc.es_get_entry(OTHER, e["id"]), lambda: self.svc.es_verify_entry(OTHER, e["id"], {}, U3), lambda: self.svc.es_reject_entry(OTHER, e["id"], "Rejecting from elsewhere", U3),
                  lambda: self.svc.es_approve_target(OTHER, t["id"], {}, U3), lambda: self.svc.es_reject_target(OTHER, t["id"], "Rejecting from elsewhere", U3)):
            with self.assertRaises(EsgNotFoundError): f()
        self.ver(e); self.assertEqual(self.svc.es_set_setting(OTHER, {"factor_max_age_years": 2}, U3)["factor_max_age_years"], 2); self.assertEqual(self.svc.es_get_setting(ORG)["factor_max_age_years"], 5)

    def test_other_company_entries_do_not_count_in_targets(self):
        self.svc.es_add_entry(OTHER, dict(scope="SCOPE_2", category="ELECTRICITY", description="Grid power", period_start="2025-01-01", period_end="2025-06-30", quantity="1000", unit="kWh", factor="0.4", factor_source="Grid operator 2024", factor_year=2024), U1)
        oe = self.svc.es_list_entries(OTHER)[0]; self.svc.es_verify_entry(OTHER, oe["id"], {}, U3)
        self.assertEqual(self.tgt()["actual_tonnes"], "0.000")


class Audit(Base):
    def test_every_write_logged_without_content(self):
        e = self.ent(); self.ver(e); r = self.ent(); self.svc.es_reject_entry(ORG, r["id"], "Quantity does not match invoices", U3)
        t = self.tgt(); self.svc.es_approve_target(ORG, t["id"], {"note": "Board agreed on this"}, U3); t2 = self.tgt(label="Second target"); self.svc.es_reject_target(ORG, t2["id"], "The baseline is not agreed yet", U3); self.svc.es_set_setting(ORG, {"factor_max_age_years": 3}, U3)
        acts = [x[0] for x in self.events]
        for x in ("ESG_ENTRY_PROPOSED", "ESG_ENTRY_VERIFIED", "ESG_ENTRY_REJECTED", "ESG_TARGET_PROPOSED", "ESG_TARGET_APPROVED", "ESG_TARGET_REJECTED", "ESG_SETTING_SET"): self.assertIn(x, acts)
        blob = " ".join(str(x) for x in self.events)
        for secret in ("Diesel", "generator", "National factor", "3351", "1250", "719", "Quantity does not", "Board agreed", "Cut total", "not agreed"): self.assertNotIn(secret, blob)

    def test_failed_actions_are_not_logged(self):
        with self.assertRaises(EsgError): self.ent(quantity="0")
        e = self.ent(); n = len(self.events)
        with self.assertRaises(EsgForbiddenError): self.ver(e, U1)
        with self.assertRaises(EsgError): self.svc.es_reject_entry(ORG, e["id"], "short", U3)
        with self.assertRaises(EsgError): self.tgt(reduction_pct="0")
        self.assertEqual(len(self.events), n)


class Permissions(unittest.TestCase):
    def test_roles(self):
        has = lambda r, p: p in ROLE_PERMISSIONS[r]
        for r in (Role.OWNER, Role.ADMINISTRATOR, Role.MANAGER, Role.AUDITOR): self.assertTrue(has(r, ESG_PREPARE), r)
        for r in (Role.OWNER, Role.APPROVER, Role.MANAGER): self.assertTrue(has(r, ESG_APPROVE), r)
        for r in (Role.ACCOUNTANT, Role.REVIEWER, Role.EXTERNAL_AUDITOR, Role.READ_ONLY, Role.DONOR, Role.REGULATOR, Role.INVESTOR_REVIEWER): self.assertFalse(has(r, ESG_PREPARE) or has(r, ESG_APPROVE), r)

    def test_anyone_who_can_prepare_or_approve_can_view(self):
        for r, perms in ROLE_PERMISSIONS.items():
            if ESG_PREPARE in perms or ESG_APPROVE in perms: self.assertIn(AUDIT_READ, perms, r)


class RouterGuards(unittest.TestCase):
    SRC = os.path.join(os.path.dirname(__file__), "..", "src", "asavexa", "api", "routers", "esg.py")

    def test_every_write_has_the_right_guard(self):
        tree = ast.parse(open(self.SRC).read()); named = {"_prepare": "ESG_PREPARE", "_approve": "ESG_APPROVE"}; g = {}
        for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.decorator_list]:
            verbs, guards = set(), set()
            for dec in fn.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute): verbs.add(dec.func.attr)
                for kw in getattr(dec, "keywords", []):
                    if kw.arg == "dependencies": guards |= {named[e.id] for e in kw.value.elts if isinstance(e, ast.Name) and e.id in named}
            g[fn.name] = (verbs, guards)
        approve = {"set_setting", "verify_entry", "reject_entry", "approve_target", "reject_target"}
        prepare = {"add_entry", "add_target"}
        for n in approve: self.assertEqual(g[n][1], {"ESG_APPROVE"}, n)
        for n in prepare: self.assertEqual(g[n][1], {"ESG_PREPARE"}, n)
        for n, (verbs, guards) in g.items():
            if verbs == {"get"}: self.assertEqual(guards, set(), n)
            else: self.assertIn(n, approve | prepare, f"{n} writes but has no esg guard")
        src = open(self.SRC).read(); self.assertIn("dependencies=[Depends(require_permission(AUDIT_READ))]", src); self.assertNotIn("org_id", src)


if __name__ == "__main__":
    unittest.main()
