"""Fixed assets register: assets, exact straight-line depreciation, disposals, counts, two-person rules, policy, isolation, audit, permissions."""
import ast
import os
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from analysis_fixture import ORG, OTHER, World
from asavexa.fixedassets.errors import FixedAssetError, FixedAssetForbiddenError, FixedAssetNotFoundError, FixedAssetStateError
from asavexa.fixedassets.service import FixedAssetService, accumulated, months_between, refnum
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.permissions import AUDIT_READ, FIX_APPROVE, FIX_PREPARE, ROLE_PERMISSIONS

U1, U2, U3, U4 = "user-1", "user-2", "user-3", "user-4"   # U1 and U2 prepare, U3 and U4 approve


class Clock:
    def __init__(self): self.d = date(2026, 3, 10)
    def __call__(self): return datetime(self.d.year, self.d.month, self.d.day, 9, tzinfo=timezone.utc)


class Vault:
    def get_evidence(self, org, i):
        if org == ORG and i in ("ev1", "ev2"): return SimpleNamespace(id=i, original_filename=f"{i}.pdf", file_hash="h" * 64)
        raise LookupError(i)


class Base(unittest.TestCase):
    def setUp(self):
        self.w = World(); self.clock = Clock(); self.events = []
        self.svc = FixedAssetService(self.w.store, Vault(), log=lambda *a: self.events.append(a), now=self.clock)

    def asset(self, actor=U1, active=False, **kw):
        d = dict(name="Delivery van", category="VEHICLES", location="Main yard", custodian_name="Ben Eze", acquired_on="2026-01-15", currency="NGN", cost="12000.00", residual_value="2000.00", life_months=60)
        d.update(kw); a = self.svc.fa_propose_asset(ORG, d, actor)
        return self.svc.fa_approve_asset(ORG, a["id"], {}, U3) if active else a

    def count(self, a, actor=U2, **kw):
        d = dict(counted_on="2026-03-10", result="FOUND", note="Found in the yard and checked the plate"); d.update(kw)
        return self.svc.fa_record_count(ORG, a["id"], d, actor)

    def disposal(self, a, actor=U1, **kw):
        d = dict(disposed_on="2026-03-10", proceeds="9000.00", reason="Sold to a dealer after the lease ended"); d.update(kw)
        return self.svc.fa_propose_disposal(ORG, a["id"], d, actor)


class Arithmetic(unittest.TestCase):
    def test_months_between(self):
        for a, b, n in [((2026, 1, 15), (2026, 2, 15), 1), ((2026, 1, 15), (2026, 2, 14), 0), ((2026, 1, 31), (2026, 2, 28), 0), ((2026, 1, 31), (2026, 3, 1), 1), ((2026, 1, 1), (2027, 1, 1), 12), ((2026, 5, 1), (2026, 4, 1), 0), ((2026, 1, 1), (2026, 1, 1), 0)]:
            self.assertEqual(months_between(date(*a), date(*b)), n, (a, b))

    def test_accumulated_is_exact_and_capped(self):
        c, r = Decimal("12000.00"), Decimal("2000.00"); acq = date(2026, 1, 15)
        self.assertEqual(accumulated(c, r, 60, acq, date(2026, 3, 15)), Decimal("333.33"))
        self.assertEqual(accumulated(c, r, 60, acq, date(2031, 1, 15)), Decimal("10000.00")); self.assertEqual(accumulated(c, r, 60, acq, date(2040, 1, 1)), Decimal("10000.00"))
        self.assertEqual(accumulated(c, r, 60, acq, date(2026, 1, 1)), Decimal("0.00")); self.assertEqual(accumulated(c, r, 0, acq, date(2030, 1, 1)), Decimal("0.00"))
        self.assertEqual(accumulated(Decimal("100.00"), Decimal("0.00"), 3, acq, date(2026, 2, 15)), Decimal("33.33")); self.assertEqual(accumulated(Decimal("100.00"), Decimal("0.00"), 3, acq, date(2026, 3, 15)), Decimal("66.67"))
        self.assertEqual(accumulated(Decimal("100.00"), Decimal("0.00"), 3, acq, date(2026, 4, 15)), Decimal("100.00"))

    def test_refnum(self): self.assertEqual((refnum({"ref": "FA-012"}), refnum({})), (12, 0))


class Policy(Base):
    def test_default_set_bounds(self):
        self.assertEqual(self.svc.fa_get_policy(ORG)["count_days"], 365); self.assertEqual(self.svc.fa_set_policy(ORG, {"count_days": "90"}, U3)["count_days"], 90); self.assertEqual(self.svc.fa_get_policy(OTHER)["count_days"], 365)
        for v in (29, 731, "x", True, -1, 4.5, ""):
            with self.assertRaises(FixedAssetError, msg=str(v)): self.svc.fa_set_policy(ORG, {"count_days": v}, U3)


class Assets(Base):
    def test_propose_and_view(self):
        a = self.asset(); self.assertEqual((a["ref"], a["status"], a["cost"], a["residual"], a["monthly"]), ("FA-001", "PROPOSED", "12000.00", "2000.00", "166.67"))
        self.assertEqual((a["accumulated"], a["net_book_value"]), ("166.67", "11833.33")); self.assertEqual(self.asset()["ref"], "FA-002")

    def test_validation(self):
        for bad in (dict(name="ab"), dict(category="BOATS"), dict(location="x"), dict(custodian_name=""), dict(acquired_on="2026-02-30"), dict(acquired_on="2026-04-30"), dict(currency="NG"), dict(currency="N1A"), dict(cost="0"), dict(cost="-5"), dict(cost=12.5), dict(cost="1.234"),
                    dict(cost=True), dict(cost=None), dict(residual_value="12000.00"), dict(residual_value="20000"), dict(residual_value=1.5), dict(life_months=0), dict(life_months=601), dict(life_months="x"), dict(life_months=None), dict(evidence_ids=["nope"])):
            with self.assertRaises(FixedAssetError, msg=str(bad)): self.asset(**bad)
        self.assertEqual(self.asset()["ref"], "FA-001")   # failures used no numbers

    def test_amount_formats(self):
        a = self.asset(cost="1,500", residual_value="", life_months="12"); self.assertEqual((a["cost"], a["residual"], a["life_months"]), ("1500.00", "0.00", 12))
        self.assertEqual(self.asset(cost=2500, residual_value=0)["cost"], "2500.00")

    def test_land_is_not_depreciated(self):
        l = self.asset(category="LAND", life_months=None, residual_value="0", acquired_on="2020-01-01", cost="5000000")
        self.assertEqual((l["accumulated"], l["net_book_value"], l["depreciates"], l["fully_depreciated"]), ("0.00", "5000000.00", False, False))
        for bad in (dict(life_months=60), dict(residual_value="100")):
            with self.assertRaises(FixedAssetError): self.asset(category="LAND", **{"life_months": None, "residual_value": "0", **bad})

    def test_duplicate_serial(self):
        self.asset(serial_number="SN-100")
        with self.assertRaises(FixedAssetStateError): self.asset(serial_number="SN-100")
        self.assertEqual(self.asset(serial_number="SN-101")["ref"], "FA-002")

    def test_serial_free_again_after_rejection(self):
        a = self.asset(serial_number="SN-100"); self.svc.fa_reject_asset(ORG, a["id"], "Entered with the wrong details", U3); self.assertEqual(self.asset(serial_number="SN-100")["ref"], "FA-002")

    def test_approval_needs_a_different_person(self):
        a = self.asset()
        with self.assertRaises(FixedAssetForbiddenError): self.svc.fa_approve_asset(ORG, a["id"], {}, U1)
        with self.assertRaises(FixedAssetForbiddenError): self.svc.fa_reject_asset(ORG, a["id"], "Rejecting my own proposal", U1)
        with self.assertRaises(FixedAssetError): self.svc.fa_approve_asset(ORG, a["id"], {"note": "ok"}, U3)
        p = self.svc.fa_approve_asset(ORG, a["id"], {}, U3); self.assertEqual((p["status"], p["decided_by"]), ("ACTIVE", U3))
        with self.assertRaises(FixedAssetStateError): self.svc.fa_approve_asset(ORG, a["id"], {}, U4)
        with self.assertRaises(FixedAssetStateError): self.svc.fa_reject_asset(ORG, a["id"], "Too late to reject it", U4)

    def test_reject_needs_a_reason(self):
        a = self.asset()
        with self.assertRaises(FixedAssetError): self.svc.fa_reject_asset(ORG, a["id"], "short", U3)
        self.assertEqual(self.svc.fa_reject_asset(ORG, a["id"], "Entered with the wrong details", U3)["status"], "REJECTED")

    def test_filters_and_evidence(self):
        a = self.asset(evidence_ids=["ev1", "ev1"]); self.assertEqual([e["evidence_id"] for e in a["evidence"]], ["ev1"]); self.asset(category="IT_EQUIPMENT", name="Server", serial_number="S1")
        self.assertEqual([x["ref"] for x in self.svc.fa_list_assets(ORG, category="IT_EQUIPMENT")], ["FA-002"]); self.assertEqual(len(self.svc.fa_list_assets(ORG, "PROPOSED")), 2)

    def test_fully_depreciated(self):
        a = self.asset(acquired_on="2020-01-15", life_months=24, active=True); self.assertEqual((a["accumulated"], a["net_book_value"], a["fully_depreciated"]), ("10000.00", "2000.00", True))

    def test_schedule(self):
        a = self.asset(acquired_on="2026-01-15", life_months=5, residual_value="2000.00"); s = self.svc.fa_schedule(ORG, a["id"], 12)
        self.assertEqual([(r["month_no"], r["on"], r["accumulated"]) for r in s["rows"]], [(2, "2026-03-15", "4000.00"), (3, "2026-04-15", "6000.00"), (4, "2026-05-15", "8000.00"), (5, "2026-06-15", "10000.00")])
        self.assertEqual(s["rows"][-1]["net_book_value"], "2000.00"); self.assertEqual(len(self.svc.fa_schedule(ORG, a["id"], 1)["rows"]), 1)
        for bad in (0, 121, "x"):
            with self.assertRaises(FixedAssetError): self.svc.fa_schedule(ORG, a["id"], bad)
        l = self.asset(category="LAND", life_months=None, residual_value="0", name="Plot"); self.assertEqual(self.svc.fa_schedule(ORG, l["id"])["rows"], [])

    def test_schedule_month_end_clamps(self):
        self.clock.d = date(2024, 1, 31); a = self.asset(acquired_on="2024-01-31", life_months=60); rows = {r["month_no"]: r["on"] for r in self.svc.fa_schedule(ORG, a["id"], 120)["rows"]}
        self.assertEqual((rows[1], rows[2], rows[13], rows[14], rows[60]), ("2024-02-29", "2024-03-31", "2025-02-28", "2025-03-31", "2029-01-31"))


class Disposals(Base):
    def test_cycle_with_gain_or_loss(self):
        a = self.asset(active=True); d = self.disposal(a); self.assertEqual((d["status"], d["disposal"]["net_book_value"], d["disposal"]["gain_or_loss"]), ("DISPOSAL_PENDING", "11833.33", "-2833.33"))
        with self.assertRaises(FixedAssetForbiddenError): self.svc.fa_approve_disposal(ORG, a["id"], {}, U1)
        self.clock.d = date(2026, 6, 1); x = self.svc.fa_approve_disposal(ORG, a["id"], {}, U3)
        self.assertEqual((x["status"], x["as_of"], x["net_book_value"]), ("DISPOSED", "2026-03-10", "11833.33"))   # frozen at the disposal date
        with self.assertRaises(FixedAssetStateError): self.svc.fa_approve_disposal(ORG, a["id"], {}, U4)

    def test_validation(self):
        a = self.asset(active=True)
        for bad in (dict(disposed_on="2026-01-01"), dict(disposed_on="2026-04-30"), dict(disposed_on="nope"), dict(proceeds="-1"), dict(proceeds=1.5), dict(proceeds="x"), dict(reason="short")):
            with self.assertRaises(FixedAssetError, msg=str(bad)): self.disposal(a, **bad)
        self.assertEqual(self.disposal(a, proceeds="")["disposal"]["proceeds"], "0.00")

    def test_only_active_assets_and_once(self):
        p = self.asset()
        with self.assertRaises(FixedAssetStateError): self.disposal(p)
        a = self.asset(active=True, name="Second van", serial_number="S2"); self.disposal(a)
        with self.assertRaises(FixedAssetStateError): self.disposal(a)
        with self.assertRaises(FixedAssetStateError): self.count(a)

    def test_reject_returns_to_active_and_allows_a_new_one(self):
        a = self.asset(active=True); self.disposal(a)
        with self.assertRaises(FixedAssetForbiddenError): self.svc.fa_reject_disposal(ORG, a["id"], "Rejecting my own disposal", U1)
        with self.assertRaises(FixedAssetError): self.svc.fa_reject_disposal(ORG, a["id"], "short", U3)
        r = self.svc.fa_reject_disposal(ORG, a["id"], "The dealer offer was withdrawn", U3); self.assertEqual((r["status"], r["disposal"]), ("ACTIVE", None))
        self.assertEqual(self.disposal(a, proceeds="1000")["status"], "DISPOSAL_PENDING")

    def test_zero_cost_gain_on_a_fully_depreciated_asset(self):
        a = self.asset(acquired_on="2020-01-15", life_months=24, active=True); d = self.disposal(a, proceeds="3000")
        self.assertEqual((d["disposal"]["net_book_value"], d["disposal"]["gain_or_loss"]), ("2000.00", "1000.00"))


class Counts(Base):
    def test_record_and_review(self):
        a = self.asset(active=True); c = self.count(a); self.assertEqual((c["counts_to_review"], c["last_counted_on"], c["missing"]), (1, "2026-03-10", False))
        with self.assertRaises(FixedAssetForbiddenError): self.svc.fa_review_count(ORG, a["id"], 1, {"note": "Reviewed the photo"}, U2)
        with self.assertRaises(FixedAssetError): self.svc.fa_review_count(ORG, a["id"], 1, {"note": "ok"}, U3)
        r = self.svc.fa_review_count(ORG, a["id"], 1, {"note": "Reviewed the photo and plate"}, U3); self.assertEqual((r["counts_to_review"], r["counts"][0]["status"]), (0, "REVIEWED"))
        with self.assertRaises(FixedAssetStateError): self.svc.fa_review_count(ORG, a["id"], 1, {"note": "Reviewed it again"}, U4)
        with self.assertRaises(FixedAssetNotFoundError): self.svc.fa_review_count(ORG, a["id"], 9, {"note": "Reviewed a missing count"}, U3)
        with self.assertRaises(FixedAssetError): self.svc.fa_review_count(ORG, a["id"], "x", {"note": "Reviewed a bad number"}, U3)

    def test_validation(self):
        a = self.asset(active=True)
        for bad in (dict(counted_on="2026-01-01"), dict(counted_on="2026-04-30"), dict(result="LOST"), dict(note="short"), dict(evidence_ids=["nope"])):
            with self.assertRaises(FixedAssetError, msg=str(bad)): self.count(a, **bad)
        self.assertEqual(self.count(a, evidence_ids=["ev2"])["counts"][0]["evidence"][0]["evidence_id"], "ev2")

    def test_missing_flag_follows_the_latest_count(self):
        a = self.asset(active=True); self.assertTrue(self.count(a, result="MISSING")["missing"]); self.assertFalse(self.count(a, counted_on="2026-03-11", result="FOUND")["missing"])

    def test_count_due(self):
        a = self.asset(active=True, acquired_on="2024-01-15"); self.assertTrue(self.svc.fa_get_asset(ORG, a["id"])["count_due"])
        self.assertFalse(self.count(a)["count_due"]); self.clock.d = date(2027, 3, 11); self.assertTrue(self.svc.fa_get_asset(ORG, a["id"])["count_due"])
        self.svc.fa_set_policy(ORG, {"count_days": 730}, U3); self.assertFalse(self.svc.fa_get_asset(ORG, a["id"])["count_due"])
        self.assertFalse(self.svc.fa_get_asset(ORG, self.asset(name="New desk", serial_number="S9")["id"])["count_due"])   # not active yet


class Overview(Base):
    def test_attention_and_totals_per_currency(self):
        a = self.asset(active=True, acquired_on="2024-01-15"); self.asset(name="Press", serial_number="P1"); b = self.asset(active=True, name="Generator", currency="USD", cost="900.00", residual_value="0", life_months=36, serial_number="G1")
        self.count(b, result="MISSING"); d = self.asset(active=True, name="Laptop", serial_number="L1"); self.disposal(d)
        o = self.svc.fa_overview(ORG); kinds = {x["kind"]: x["count"] for x in o["attention"]}
        self.assertEqual(kinds, {"MISSING_ASSETS": 1, "COUNTS_OVERDUE": 1, "ASSETS_TO_APPROVE": 1, "DISPOSALS_TO_DECIDE": 1, "COUNTS_TO_REVIEW": 1})
        t = {x["currency"]: x for x in o["totals"]}; self.assertEqual(set(t), {"NGN", "USD"}); self.assertEqual((t["USD"]["cost"], t["USD"]["assets"]), ("900.00", 1)); self.assertEqual((t["NGN"]["cost"], t["NGN"]["assets"]), ("24000.00", 2))
        self.assertEqual(Decimal(t["NGN"]["cost"]) - Decimal(t["NGN"]["accumulated"]), Decimal(t["NGN"]["net_book_value"]))

    def test_counts_and_empty(self):
        self.asset(active=True); self.asset(name="Press", serial_number="P1"); c = self.svc.fa_overview(ORG)["counts"]; self.assertEqual((c["active"], c["proposed"], c["disposed"]), (1, 1, 0))
        o = self.svc.fa_overview(OTHER); self.assertEqual((o["attention"], o["totals"]), ([], [])); self.assertIn("LAND", self.svc.fa_options(ORG)["categories"]); self.assertTrue(o["limitations"])


class Isolation(Base):
    def test_other_company_sees_nothing_and_cannot_touch(self):
        a = self.asset(active=True); self.count(a); self.assertEqual(self.svc.fa_list_assets(OTHER), [])
        for fn in (lambda: self.svc.fa_get_asset(OTHER, a["id"]), lambda: self.svc.fa_schedule(OTHER, a["id"]), lambda: self.svc.fa_approve_asset(OTHER, a["id"], {}, U3), lambda: self.svc.fa_record_count(OTHER, a["id"], {}, U2),
                   lambda: self.svc.fa_review_count(OTHER, a["id"], 1, {"note": "Reviewing from outside"}, U3), lambda: self.svc.fa_propose_disposal(OTHER, a["id"], {}, U1), lambda: self.svc.fa_reject_asset(OTHER, a["id"], "Rejecting from outside", U3)):
            with self.assertRaises(FixedAssetNotFoundError): fn()

    def test_same_serial_allowed_in_each_company(self):
        self.asset(serial_number="SN-1"); d = dict(name="Delivery van", category="OTHER", location="Yard", custodian_name="Zed Ola", acquired_on="2026-01-15", currency="NGN", cost="100", life_months=12, serial_number="SN-1")
        self.assertEqual(self.svc.fa_propose_asset(OTHER, d, U1)["ref"], "FA-001")


class Audit(Base):
    def test_every_write_logged_without_content(self):
        a = self.asset(active=True); self.svc.fa_set_policy(ORG, {"count_days": 100}, U3); self.count(a); self.svc.fa_review_count(ORG, a["id"], 1, {"note": "Reviewed the photo and plate"}, U3)
        self.disposal(a); self.svc.fa_reject_disposal(ORG, a["id"], "The dealer offer was withdrawn", U3); self.disposal(a); self.svc.fa_approve_disposal(ORG, a["id"], {}, U3)
        b = self.asset(name="Press", serial_number="P1"); self.svc.fa_reject_asset(ORG, b["id"], "Entered with the wrong details", U3)
        acts = [x[0] for x in self.events]
        for x in ("FIXEDASSETS_ASSET_PROPOSED", "FIXEDASSETS_ASSET_APPROVED", "FIXEDASSETS_ASSET_REJECTED", "FIXEDASSETS_DISPOSAL_PROPOSED", "FIXEDASSETS_DISPOSAL_APPROVED", "FIXEDASSETS_DISPOSAL_REJECTED", "FIXEDASSETS_COUNT_RECORDED", "FIXEDASSETS_COUNT_REVIEWED", "FIXEDASSETS_POLICY_SET"): self.assertIn(x, acts)
        blob = " ".join(str(x) for x in self.events)
        for secret in ("Delivery van", "Main yard", "12000", "9000", "Sold to a dealer", "plate", "Ben Eze"): self.assertNotIn(secret, blob)

    def test_failed_actions_are_not_logged(self):
        with self.assertRaises(FixedAssetError): self.asset(name="ab")
        self.assertEqual(self.events, [])


class Permissions(unittest.TestCase):
    def test_roles(self):
        has = lambda r, p: p in ROLE_PERMISSIONS[r]
        for r in (Role.OWNER, Role.ADMINISTRATOR, Role.MANAGER, Role.AUDITOR): self.assertTrue(has(r, FIX_PREPARE), r)
        for r in (Role.OWNER, Role.APPROVER, Role.MANAGER): self.assertTrue(has(r, FIX_APPROVE), r)
        for r in (Role.ACCOUNTANT, Role.REVIEWER, Role.EXTERNAL_AUDITOR, Role.READ_ONLY, Role.DONOR, Role.REGULATOR, Role.INVESTOR_REVIEWER): self.assertFalse(has(r, FIX_PREPARE) or has(r, FIX_APPROVE), r)

    def test_anyone_who_can_prepare_or_approve_can_view(self):
        for r, perms in ROLE_PERMISSIONS.items():
            if FIX_PREPARE in perms or FIX_APPROVE in perms: self.assertIn(AUDIT_READ, perms, r)


class RouterGuards(unittest.TestCase):
    SRC = os.path.join(os.path.dirname(__file__), "..", "src", "asavexa", "api", "routers", "fixedassets.py")

    def test_every_write_has_the_right_guard(self):
        tree = ast.parse(open(self.SRC).read()); named = {"_prepare": "FIX_PREPARE", "_approve": "FIX_APPROVE"}; g = {}
        for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.decorator_list]:
            verbs, guards = set(), set()
            for dec in fn.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute): verbs.add(dec.func.attr)
                for kw in getattr(dec, "keywords", []):
                    if kw.arg == "dependencies": guards |= {named[e.id] for e in kw.value.elts if isinstance(e, ast.Name) and e.id in named}
            g[fn.name] = (verbs, guards)
        approve = {"set_policy", "approve_asset", "reject_asset", "approve_disposal", "reject_disposal", "review_count"}
        prepare = {"propose_asset", "propose_disposal", "record_count"}
        for n in approve: self.assertEqual(g[n][1], {"FIX_APPROVE"}, n)
        for n in prepare: self.assertEqual(g[n][1], {"FIX_PREPARE"}, n)
        for n, (verbs, guards) in g.items():
            if verbs == {"get"}: self.assertEqual(guards, set(), n)
            else: self.assertIn(n, approve | prepare, f"{n} writes but has no fixed-assets guard")
        src = open(self.SRC).read(); self.assertIn("dependencies=[Depends(require_permission(AUDIT_READ))]", src); self.assertNotIn("org_id", src)


if __name__ == "__main__":
    unittest.main()
