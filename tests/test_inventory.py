"""Inventory: items, receipts, issues, weighted-average valuation, two-person adjustments, alerts, policy, isolation, audit, permissions."""
import ast
import os
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

from analysis_fixture import ORG, OTHER, World
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.permissions import AUDIT_READ, INV_APPROVE, INV_PREPARE, ROLE_PERMISSIONS
from asavexa.inventory.errors import InventoryError, InventoryForbiddenError, InventoryNotFoundError, InventoryStateError
from asavexa.inventory.service import InventoryService, refnum

U1, U2, U3, U4 = "user-1", "user-2", "user-3", "user-4"   # U1 and U2 prepare, U3 and U4 approve


class Clock:
    def __init__(self): self.d = date(2026, 3, 10)
    def __call__(self): return datetime(self.d.year, self.d.month, self.d.day, 9, tzinfo=timezone.utc)


class Base(unittest.TestCase):
    def setUp(self):
        self.w = World(); self.clock = Clock(); self.events = []
        self.svc = InventoryService(self.w.store, None, log=lambda *a: self.events.append(a), now=self.clock)

    def item(self, actor=U1, **kw):
        d = dict(sku="rice-25", name="Rice 25kg bag", unit="bag", currency="NGN", reorder_level=10, location="Main store"); d.update(kw)
        return self.svc.iv_add_item(ORG, d, actor)

    def receive(self, it, qty=10, cost="100.00", actor=U1, **kw):
        d = dict(qty=qty, unit_cost=cost, moved_on="2026-03-09", reference="GRN-001"); d.update(kw)
        return self.svc.iv_receive(ORG, it["id"], d, actor)

    def issue(self, it, qty=1, actor=U2, **kw):
        d = dict(qty=qty, moved_on="2026-03-10", reference="SIV-001"); d.update(kw)
        return self.svc.iv_issue(ORG, it["id"], d, actor)

    def adjust(self, it, direction="DECREASE", qty=1, actor=U1, **kw):
        d = dict(direction=direction, qty=qty, reason_kind="COUNT_DIFFERENCE", reason="The shelf count was one lower than the book"); d.update(kw)
        return self.svc.iv_propose_adjustment(ORG, it["id"], d, actor)


class Helpers(unittest.TestCase):
    def test_refnum(self): self.assertEqual((refnum({"ref": "IT-012"}), refnum({})), (12, 0))


class Policy(Base):
    def test_default_set_bounds(self):
        self.assertEqual(self.svc.iv_get_policy(ORG)["stale_days"], 180); self.assertEqual(self.svc.iv_set_policy(ORG, {"stale_days": "90"}, U3)["stale_days"], 90); self.assertEqual(self.svc.iv_get_policy(OTHER)["stale_days"], 180)
        for v in (29, 731, "x", True, -1, 4.5, ""):
            with self.assertRaises(InventoryError, msg=str(v)): self.svc.iv_set_policy(ORG, {"stale_days": v}, U3)


class Items(Base):
    def test_add_and_validation(self):
        i = self.item(); self.assertEqual((i["ref"], i["sku"], i["on_hand"], i["value"], i["status"], i["average_cost"]), ("IT-001", "RICE-25", 0, "0.00", "ACTIVE", "0.00")); self.assertEqual(self.item(sku="oil-5").get("ref"), "IT-002")
        for bad in (dict(sku="x"), dict(name="ab"), dict(unit=""), dict(currency="NG"), dict(currency="N1A"), dict(reorder_level=-1), dict(reorder_level="x"), dict(reorder_level=1.5), dict(location="x")):
            with self.assertRaises(InventoryError, msg=str(bad)): self.item(**{"sku": "other-1", **bad})
        self.assertEqual(self.item(sku="beans-1")["ref"], "IT-003")

    def test_reorder_defaults_to_zero(self): self.assertEqual(self.item(reorder_level=None)["reorder_level"], 0)

    def test_duplicate_sku_only_while_active(self):
        i = self.item()
        with self.assertRaises(InventoryStateError): self.item(sku="Rice-25")
        self.svc.iv_discontinue_item(ORG, i["id"], "No longer stocked at this site", U3); self.assertEqual(self.item()["ref"], "IT-002")

    def test_discontinue_rules(self):
        i = self.item(); self.receive(i)
        with self.assertRaises(InventoryStateError): self.svc.iv_discontinue_item(ORG, i["id"], "No longer stocked at this site", U3)
        self.issue(i, 10); self.adjust(self.svc.iv_get_item(ORG, i["id"]), "INCREASE", 1, unit_cost="100")
        with self.assertRaises(InventoryStateError): self.svc.iv_discontinue_item(ORG, i["id"], "No longer stocked at this site", U3)
        self.svc.iv_reject_adjustment(ORG, i["id"], 3, "Not needed after all today", U3)
        with self.assertRaises(InventoryError): self.svc.iv_discontinue_item(ORG, i["id"], "short", U3)
        d = self.svc.iv_discontinue_item(ORG, i["id"], "No longer stocked at this site", U3); self.assertEqual(d["status"], "DISCONTINUED")
        for fn in (lambda: self.receive(i), lambda: self.issue(i), lambda: self.adjust(i), lambda: self.svc.iv_discontinue_item(ORG, i["id"], "Discontinuing a second time", U3)):
            with self.assertRaises(InventoryStateError): fn()


class Movements(Base):
    def test_receipt_values(self):
        i = self.receive(self.item(), 10, "100.00"); self.assertEqual((i["on_hand"], i["value"], i["average_cost"]), (10, "1000.00", "100.00"))
        i = self.receive(i, 10, "120.00", reference="GRN-002"); self.assertEqual((i["on_hand"], i["value"], i["average_cost"]), (20, "2200.00", "110.00"))
        self.assertEqual([m["no"] for m in i["moves"]], [1, 2]); self.assertEqual((i["moves"][1]["qty_after"], i["moves"][1]["value_after"]), (20, "2200.00"))

    def test_issue_uses_average_cost(self):
        i = self.receive(self.receive(self.item(), 10, "100.00"), 10, "120.00", reference="GRN-002"); i = self.issue(i, 5)
        self.assertEqual((i["on_hand"], i["value"], i["moves"][-1]["value"], i["moves"][-1]["unit_cost"]), (15, "1650.00", "550.00", "110.00"))

    def test_issuing_everything_leaves_no_residue(self):
        i = self.receive(self.item(), 3, "10.01"); i = self.issue(self.issue(i, 1), 1); self.assertEqual(i["value"], "10.01"); i = self.issue(i, 1)
        self.assertEqual((i["on_hand"], i["value"]), (0, "0.00")); self.assertEqual(sum(Decimal(m["value"]) for m in i["moves"] if m["kind"] == "ISSUE"), Decimal("30.03"))

    def test_value_always_equals_receipts_less_issues(self):
        i = self.item()
        for q, c in [(7, "3.33"), (5, "4.10"), (11, "0.99")]: i = self.receive(i, q, c, reference=f"GRN-{q}")
        for q in (4, 6, 3): i = self.issue(i, q, reference=f"S-{q}")
        rec = sum(Decimal(m["value"]) for m in i["moves"] if m["kind"] == "RECEIPT"); out = sum(Decimal(m["value"]) for m in i["moves"] if m["kind"] == "ISSUE")
        self.assertEqual(Decimal(i["value"]), rec - out); self.assertEqual(i["on_hand"], 10)

    def test_validation(self):
        i = self.item()
        for bad in (dict(qty=0), dict(qty=-1), dict(qty="x"), dict(qty=1.5), dict(qty=True), dict(qty=10**9), dict(cost="0"), dict(cost="-1"), dict(cost=1.5), dict(cost="1.234"), dict(cost=None), dict(moved_on="2026-04-30"), dict(moved_on="nope"), dict(reference="x")):
            kw = {("unit_cost" if k == "cost" else k): v for k, v in bad.items()}; kw = {"qty": 1, "unit_cost": "5", "moved_on": "2026-03-09", "reference": "GRN-9", **kw}
            with self.assertRaises(InventoryError, msg=str(bad)): self.svc.iv_receive(ORG, i["id"], kw, U1)
        self.assertEqual(self.receive(i)["moves"][0]["no"], 1)

    def test_cannot_issue_more_than_on_hand(self):
        i = self.receive(self.item(), 5)
        with self.assertRaises(InventoryStateError): self.issue(i, 6)
        for bad in (dict(qty=0), dict(moved_on="2026-04-30"), dict(reference="")):
            with self.assertRaises(InventoryError): self.issue(i, **{"qty": 1, **bad})
        self.assertEqual(self.issue(i, 5)["on_hand"], 0)
        with self.assertRaises(InventoryStateError): self.issue(i, 1)

    def test_lookalike_digits_and_loose_commas_are_refused(self):
        i = self.item()
        for bad in ("０１", "1,0,0", "1,00", ",100", "100,", "٣"):
            with self.assertRaises(InventoryError, msg=bad): self.receive(i, 1, bad)
            with self.assertRaises(InventoryError, msg=bad): self.receive(i, bad, "5")
        with self.assertRaises(InventoryError): self.receive(i, 1, "5", moved_on="２０２６-03-09")
        with self.assertRaises(InventoryError): self.receive(i, 1, "5", moved_on="20260309")

    def test_amount_formats(self): self.assertEqual(self.receive(self.item(), 2, "1,500")["value"], "3000.00"); self.assertEqual(self.receive(self.item(sku="b-2"), 2, 15)["value"], "30.00")


class Adjustments(Base):
    def test_decrease_cycle(self):
        i = self.receive(self.item(), 10, "100.00"); a = self.adjust(i, "DECREASE", 2); self.assertEqual((a["pending_adjustments"], a["on_hand"], a["moves"][-1]["status"]), (1, 10, "PENDING"))
        with self.assertRaises(InventoryForbiddenError): self.svc.iv_approve_adjustment(ORG, i["id"], 2, {}, U1)
        with self.assertRaises(InventoryForbiddenError): self.svc.iv_reject_adjustment(ORG, i["id"], 2, "Rejecting my own proposal", U1)
        with self.assertRaises(InventoryError): self.svc.iv_approve_adjustment(ORG, i["id"], 2, {"note": "ok"}, U3)
        d = self.svc.iv_approve_adjustment(ORG, i["id"], 2, {}, U3); self.assertEqual((d["on_hand"], d["value"], d["pending_adjustments"], d["moves"][-1]["status"], d["moves"][-1]["value"]), (8, "800.00", 0, "APPLIED", "200.00"))
        with self.assertRaises(InventoryStateError): self.svc.iv_approve_adjustment(ORG, i["id"], 2, {}, U4)
        with self.assertRaises(InventoryStateError): self.svc.iv_reject_adjustment(ORG, i["id"], 2, "Rejecting an applied one", U4)

    def test_increase_at_average_cost(self):
        i = self.receive(self.receive(self.item(), 10, "100.00"), 10, "120.00", reference="GRN-2"); self.adjust(i, "INCREASE", 2, reason_kind="COUNT_DIFFERENCE")
        d = self.svc.iv_approve_adjustment(ORG, i["id"], 3, {}, U3); self.assertEqual((d["on_hand"], d["value"], d["moves"][-1]["unit_cost"]), (22, "2420.00", "110.00"))

    def test_increase_with_explicit_cost_and_when_empty(self):
        i = self.receive(self.item(), 10, "100.00"); self.adjust(i, "INCREASE", 1, unit_cost="150"); self.assertEqual(self.svc.iv_approve_adjustment(ORG, i["id"], 2, {}, U3)["value"], "1150.00")
        e = self.item(sku="empty-1")
        with self.assertRaises(InventoryError): self.adjust(e, "INCREASE", 1)
        self.adjust(e, "INCREASE", 3, unit_cost="2.50"); self.assertEqual(self.svc.iv_approve_adjustment(ORG, e["id"], 1, {}, U3)["value"], "7.50")

    def test_validation(self):
        i = self.receive(self.item(), 5)
        for bad in (dict(direction="SIDEWAYS"), dict(qty=0), dict(qty="x"), dict(reason_kind="BORED"), dict(reason="short"), dict(direction="INCREASE", unit_cost="x"), dict(direction="INCREASE", unit_cost=1.5)):
            with self.assertRaises(InventoryError, msg=str(bad)): self.adjust(i, **bad)
        with self.assertRaises(InventoryStateError): self.adjust(i, "DECREASE", 6)

    def test_decrease_checked_again_at_approval(self):
        i = self.receive(self.item(), 5); self.adjust(i, "DECREASE", 4); self.issue(i, 3)
        with self.assertRaises(InventoryStateError): self.svc.iv_approve_adjustment(ORG, i["id"], 2, {}, U3)
        r = self.svc.iv_reject_adjustment(ORG, i["id"], 2, "Stock has moved since this was proposed", U3); self.assertEqual((r["on_hand"], r["moves"][1]["status"]), (2, "REJECTED"))

    def test_reject_needs_reason_and_missing_numbers(self):
        i = self.receive(self.item(), 5); self.adjust(i)
        with self.assertRaises(InventoryError): self.svc.iv_reject_adjustment(ORG, i["id"], 2, "short", U3)
        for no in (1, 9):
            with self.assertRaises((InventoryStateError, InventoryNotFoundError)): self.svc.iv_approve_adjustment(ORG, i["id"], no, {}, U3)   # a receipt is not an adjustment
        with self.assertRaises(InventoryError): self.svc.iv_approve_adjustment(ORG, i["id"], "x", {}, U3)

    def test_at_most_five_waiting(self):
        i = self.receive(self.item(), 50)
        for _ in range(5): self.adjust(i)
        with self.assertRaises(InventoryStateError): self.adjust(i)

    def test_applied_on_is_the_approval_day(self):
        i = self.receive(self.item(), 5); self.adjust(i); self.clock.d = date(2026, 3, 20); m = self.svc.iv_approve_adjustment(ORG, i["id"], 2, {}, U3)["moves"][-1]
        self.assertEqual((m["moved_on"], m["applied_on"]), ("2026-03-10", "2026-03-20"))


class Alerts(Base):
    def test_low_and_out_of_stock(self):
        i = self.receive(self.item(reorder_level=10), 12); self.assertFalse(i["low_stock"]); i = self.issue(i, 2); self.assertTrue(i["low_stock"]); self.assertFalse(i["out_of_stock"]); i = self.issue(i, 10)
        self.assertTrue(i["out_of_stock"]); self.assertFalse(self.item(sku="none-1", reorder_level=0)["low_stock"])

    def test_not_moving(self):
        i = self.receive(self.item(), 5); self.assertFalse(i["not_moving"]); self.clock.d = date(2026, 9, 10); self.assertTrue(self.svc.iv_get_item(ORG, i["id"])["not_moving"])
        self.svc.iv_set_policy(ORG, {"stale_days": 400}, U3); self.assertFalse(self.svc.iv_get_item(ORG, i["id"])["not_moving"])
        e = self.item(sku="empty-1"); self.assertFalse(self.svc.iv_get_item(ORG, e["id"])["not_moving"])

    def test_overview(self):
        a = self.receive(self.item(reorder_level=10), 5); self.adjust(a); b = self.receive(self.item(sku="oil-5", reorder_level=3), 3, "50"); self.issue(b, 3)
        c = self.receive(self.item(sku="usd-1", currency="USD", reorder_level=0), 4, "2.50"); self.receive(self.item(sku="old-1", reorder_level=0), 1, "7")
        self.clock.d = date(2026, 12, 20); o = self.svc.iv_overview(ORG); kinds = {x["kind"]: x["count"] for x in o["attention"]}
        self.assertEqual(kinds, {"OUT_OF_STOCK": 1, "LOW_STOCK": 1, "ADJUSTMENTS_TO_APPROVE": 1, "ITEMS_NOT_MOVING": 3})
        t = {x["currency"]: x for x in o["totals"]}; self.assertEqual((t["NGN"]["items"], t["NGN"]["units"], t["NGN"]["value"]), (3, 6, "507.00")); self.assertEqual((t["USD"]["units"], t["USD"]["value"]), (4, "10.00"))

    def test_empty(self):
        o = self.svc.iv_overview(OTHER); self.assertEqual((o["attention"], o["totals"]), ([], [])); self.assertIn("DAMAGE", self.svc.iv_options(ORG)["reason_kinds"]); self.assertTrue(o["limitations"])


class Isolation(Base):
    def test_other_company_sees_nothing_and_cannot_touch(self):
        i = self.receive(self.item(), 5); self.adjust(i); self.assertEqual(self.svc.iv_list_items(OTHER), [])
        for fn in (lambda: self.svc.iv_get_item(OTHER, i["id"]), lambda: self.svc.iv_receive(OTHER, i["id"], {}, U1), lambda: self.svc.iv_issue(OTHER, i["id"], {}, U1), lambda: self.svc.iv_propose_adjustment(OTHER, i["id"], {}, U1),
                   lambda: self.svc.iv_approve_adjustment(OTHER, i["id"], 2, {}, U3), lambda: self.svc.iv_reject_adjustment(OTHER, i["id"], 2, "Rejecting from outside", U3), lambda: self.svc.iv_discontinue_item(OTHER, i["id"], "Discontinuing from outside", U3)):
            with self.assertRaises(InventoryNotFoundError): fn()

    def test_same_sku_allowed_in_each_company(self):
        self.item(); self.assertEqual(self.svc.iv_add_item(OTHER, dict(sku="RICE-25", name="Rice 25kg bag", unit="bag", currency="NGN", location="Store"), U1)["ref"], "IT-001")


class Audit(Base):
    def test_every_write_logged_without_content(self):
        i = self.receive(self.item(), 10, "100.00"); self.issue(i, 1); self.svc.iv_set_policy(ORG, {"stale_days": 100}, U3)
        self.adjust(i, qty=1); self.svc.iv_approve_adjustment(ORG, i["id"], 3, {}, U3); self.adjust(i, qty=1); self.svc.iv_reject_adjustment(ORG, i["id"], 4, "Counted again and it was fine", U3)
        j = self.item(sku="old-1"); self.svc.iv_discontinue_item(ORG, j["id"], "No longer stocked at this site", U3)
        acts = [x[0] for x in self.events]
        for x in ("INVENTORY_ITEM_ADDED", "INVENTORY_ITEM_DISCONTINUED", "INVENTORY_RECEIPT_RECORDED", "INVENTORY_ISSUE_RECORDED", "INVENTORY_ADJUSTMENT_PROPOSED", "INVENTORY_ADJUSTMENT_APPROVED", "INVENTORY_ADJUSTMENT_REJECTED", "INVENTORY_POLICY_SET"): self.assertIn(x, acts)
        blob = " ".join(str(x) for x in self.events)
        for secret in ("Rice 25kg", "Main store", "GRN-001", "100.00", "shelf count", "Counted again"): self.assertNotIn(secret, blob)

    def test_failed_actions_are_not_logged(self):
        with self.assertRaises(InventoryError): self.item(name="ab")
        self.assertEqual(self.events, [])


class Permissions(unittest.TestCase):
    def test_roles(self):
        has = lambda r, p: p in ROLE_PERMISSIONS[r]
        for r in (Role.OWNER, Role.ADMINISTRATOR, Role.MANAGER, Role.AUDITOR): self.assertTrue(has(r, INV_PREPARE), r)
        for r in (Role.OWNER, Role.APPROVER, Role.MANAGER): self.assertTrue(has(r, INV_APPROVE), r)
        for r in (Role.ACCOUNTANT, Role.REVIEWER, Role.EXTERNAL_AUDITOR, Role.READ_ONLY, Role.DONOR, Role.REGULATOR, Role.INVESTOR_REVIEWER): self.assertFalse(has(r, INV_PREPARE) or has(r, INV_APPROVE), r)

    def test_anyone_who_can_prepare_or_approve_can_view(self):
        for r, perms in ROLE_PERMISSIONS.items():
            if INV_PREPARE in perms or INV_APPROVE in perms: self.assertIn(AUDIT_READ, perms, r)


class RouterGuards(unittest.TestCase):
    SRC = os.path.join(os.path.dirname(__file__), "..", "src", "asavexa", "api", "routers", "inventory.py")

    def test_every_write_has_the_right_guard(self):
        tree = ast.parse(open(self.SRC).read()); named = {"_prepare": "INV_PREPARE", "_approve": "INV_APPROVE"}; g = {}
        for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.decorator_list]:
            verbs, guards = set(), set()
            for dec in fn.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute): verbs.add(dec.func.attr)
                for kw in getattr(dec, "keywords", []):
                    if kw.arg == "dependencies": guards |= {named[e.id] for e in kw.value.elts if isinstance(e, ast.Name) and e.id in named}
            g[fn.name] = (verbs, guards)
        approve = {"set_policy", "discontinue_item", "approve_adjustment", "reject_adjustment"}
        prepare = {"add_item", "receive", "issue", "propose_adjustment"}
        for n in approve: self.assertEqual(g[n][1], {"INV_APPROVE"}, n)
        for n in prepare: self.assertEqual(g[n][1], {"INV_PREPARE"}, n)
        for n, (verbs, guards) in g.items():
            if verbs == {"get"}: self.assertEqual(guards, set(), n)
            else: self.assertIn(n, approve | prepare, f"{n} writes but has no inventory guard")
        src = open(self.SRC).read(); self.assertIn("dependencies=[Depends(require_permission(AUDIT_READ))]", src); self.assertNotIn("org_id", src)


if __name__ == "__main__":
    unittest.main()
