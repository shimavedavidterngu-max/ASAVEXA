"""Investments: holdings, typed purchases, two-person sales, weighted-average cost, typed prices, gain or loss arithmetic, alerts, policy, isolation, audit, permissions."""
import ast
import os
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

from analysis_fixture import ORG, OTHER, World
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.permissions import AUDIT_READ, INVEST_APPROVE, INVEST_PREPARE, ROLE_PERMISSIONS
from asavexa.investments.errors import InvestmentsError, InvestmentsForbiddenError, InvestmentsNotFoundError, InvestmentsStateError
from asavexa.investments.service import InvestmentsService, refnum

U1, U2, U3, U4 = "user-1", "user-2", "user-3", "user-4"   # U1 and U2 prepare, U3 and U4 approve


class Clock:
    def __init__(self): self.d = date(2026, 3, 10)
    def __call__(self): return datetime(self.d.year, self.d.month, self.d.day, 9, tzinfo=timezone.utc)


class Base(unittest.TestCase):
    def setUp(self):
        self.w = World(); self.clock = Clock(); self.events = []
        self.svc = InvestmentsService(self.w.store, None, log=lambda *a: self.events.append(a), now=self.clock)

    def hold(self, actor=U1, **kw):
        d = dict(name="Dangote Cement shares", identifier="dangcem", asset_class="EQUITY", currency="NGN", account="Broker account 1"); d.update(kw)
        return self.svc.im_add_holding(ORG, d, actor)

    def buy(self, h, units=10, price="100.00", fee="5.00", actor=U1, **kw):
        d = dict(units=units, price=price, fee=fee, traded_on="2026-03-09", reference="CN-001"); d.update(kw)
        return self.svc.im_buy(ORG, h["id"], d, actor)

    def sell(self, h, units=1, price="100.00", fee="0", actor=U1, **kw):
        d = dict(units=units, price=price, fee=fee, traded_on="2026-03-10", reference="CN-900"); d.update(kw)
        return self.svc.im_propose_sell(ORG, h["id"], d, actor)

    def mark(self, h, price="110", as_of="2026-03-09", source="Broker statement", actor=U1):
        return self.svc.im_record_mark(ORG, h["id"], dict(price=price, as_of=as_of, source=source), actor)


class Helpers(unittest.TestCase):
    def test_refnum(self): self.assertEqual((refnum({"ref": "HD-012"}), refnum({})), (12, 0))


class Policy(Base):
    def test_default_set_bounds(self):
        self.assertEqual(self.svc.im_get_policy(ORG)["stale_days"], 30); self.assertEqual(self.svc.im_set_policy(ORG, {"stale_days": "90"}, U3)["stale_days"], 90); self.assertEqual(self.svc.im_get_policy(OTHER)["stale_days"], 30)
        for v in (6, 366, "x", True, -1, 4.5, ""):
            with self.assertRaises(InvestmentsError, msg=str(v)): self.svc.im_set_policy(ORG, {"stale_days": v}, U3)


class Holdings(Base):
    def test_add_and_validation(self):
        h = self.hold(); self.assertEqual((h["ref"], h["identifier"], h["units"], h["cost_basis"], h["status"], h["average_cost"], h["market_value"]), ("HD-001", "DANGCEM", "0", "0.00", "ACTIVE", "0.0000", None)); self.assertEqual(self.hold(identifier="").get("ref"), "HD-002")
        for bad in (dict(name="ab"), dict(asset_class="SHARES"), dict(asset_class=""), dict(currency="NG"), dict(currency="N1A"), dict(account="x"), dict(identifier="x")):
            with self.assertRaises(InvestmentsError, msg=str(bad)): self.hold(**{"identifier": "other-1", **bad})
        self.assertEqual(self.hold(identifier=None)["identifier"], None)

    def test_duplicate_identifier_only_while_active(self):
        h = self.hold()
        with self.assertRaises(InvestmentsStateError): self.hold(identifier="DangCem")
        self.svc.im_close_holding(ORG, h["id"], "Position was never opened here", U3); self.assertEqual(self.hold()["ref"], "HD-002")

    def test_close_rules(self):
        h = self.buy(self.hold())
        with self.assertRaises(InvestmentsStateError): self.svc.im_close_holding(ORG, h["id"], "Closing with units left over", U3)
        self.sell(h, 10); 
        with self.assertRaises(InvestmentsStateError): self.svc.im_close_holding(ORG, h["id"], "Closing with a sale waiting", U3)
        self.svc.im_approve_sell(ORG, h["id"], 2, {}, U3)
        with self.assertRaises(InvestmentsError): self.svc.im_close_holding(ORG, h["id"], "short", U3)
        c = self.svc.im_close_holding(ORG, h["id"], "Position fully sold and settled", U3); self.assertEqual(c["status"], "CLOSED")
        for fn in (lambda: self.buy(h), lambda: self.sell(h), lambda: self.mark(h), lambda: self.svc.im_close_holding(ORG, h["id"], "Closing a second time here", U3)):
            with self.assertRaises(InvestmentsStateError): fn()


class Buys(Base):
    def test_cost_includes_fee_and_average(self):
        h = self.buy(self.hold(), 10, "100.00", "5.00"); self.assertEqual((h["units"], h["cost_basis"], h["average_cost"]), ("10", "1005.00", "100.5000"))
        t = h["trades"][0]; self.assertEqual((t["gross"], t["amount"], t["fee"], t["status"], t["units_after"], t["basis_after"]), ("1000.00", "1005.00", "5.00", "APPLIED", "10", "1005.00"))
        h = self.buy(h, 5, "120.5", "0", reference="CN-002"); self.assertEqual((h["units"], h["cost_basis"], h["average_cost"]), ("15", "1607.50", "107.1667")); self.assertEqual([t["no"] for t in h["trades"]], [1, 2])

    def test_fractional_units_and_rounding(self):
        h = self.buy(self.hold(), "2.5", "10.3333", None); self.assertEqual((h["units"], h["cost_basis"], h["trades"][0]["gross"]), ("2.5", "25.83", "25.83"))
        h = self.buy(h, "0.0001", "99999", "0", reference="CN-3"); self.assertEqual((h["units"], h["cost_basis"]), ("2.5001", "35.83"))

    def test_validation(self):
        h = self.hold()
        base = dict(units=1, price="5", fee="0", traded_on="2026-03-09", reference="CN-9")
        for bad in (dict(units=0), dict(units=-1), dict(units="x"), dict(units=1.5), dict(units=True), dict(units="1.23456"), dict(units=10**10), dict(price="0"), dict(price="-1"), dict(price=1.5), dict(price="1.23456"), dict(price=None),
                    dict(fee="-1"), dict(fee="1.234"), dict(fee="x"), dict(fee=1.5), dict(traded_on="2026-04-30"), dict(traded_on="nope"), dict(reference="x"), dict(units="0.0001", price="0.0001")):
            with self.assertRaises(InvestmentsError, msg=str(bad)): self.svc.im_buy(ORG, h["id"], {**base, **bad}, U1)
        self.assertEqual(self.svc.im_buy(ORG, h["id"], {**base, "fee": None}, U1)["cost_basis"], "5.00")
        self.assertEqual(self.svc.im_buy(ORG, h["id"], {**base, "fee": ""}, U1)["cost_basis"], "10.00")

    def test_lookalike_digits_and_loose_commas_are_refused(self):
        h = self.hold()
        for bad in ("０１", "1,0,0", "٣", "1e3"):
            with self.assertRaises(InvestmentsError, msg=bad): self.buy(h, bad, "5")
            with self.assertRaises(InvestmentsError, msg=bad): self.buy(h, 1, bad)
        with self.assertRaises(InvestmentsError): self.buy(h, 1, "5", fee="1,0,0")
        with self.assertRaises(InvestmentsError): self.buy(h, 1, "5", traded_on="２０２６-03-09")
        self.assertEqual(self.buy(h, 1, "5", fee="1,000.50")["cost_basis"], "1005.50")


class Sells(Base):
    def test_cycle_with_exact_gain(self):
        h = self.buy(self.buy(self.hold(), 10, "100.00", "5.00"), 5, "120.5", "0", reference="CN-2")
        p = self.sell(h, 6, "130", "3"); self.assertEqual((p["pending_sells"], p["units"], p["trades"][-1]["status"], p["trades"][-1]["gross"]), (1, "15", "PENDING", "780.00"))
        with self.assertRaises(InvestmentsForbiddenError): self.svc.im_approve_sell(ORG, h["id"], 3, {}, U1)
        with self.assertRaises(InvestmentsForbiddenError): self.svc.im_reject_sell(ORG, h["id"], 3, "Rejecting my own proposal", U1)
        with self.assertRaises(InvestmentsError): self.svc.im_approve_sell(ORG, h["id"], 3, {"note": "ok"}, U3)
        d = self.svc.im_approve_sell(ORG, h["id"], 3, {}, U3); t = d["trades"][-1]
        self.assertEqual((d["units"], d["cost_basis"], d["realised_total"], d["pending_sells"]), ("9", "964.50", "134.00", 0)); self.assertEqual((t["proceeds"], t["cost_removed"], t["realised"], t["status"], t["units_after"], t["basis_after"]), ("777.00", "643.00", "134.00", "APPLIED", "9", "964.50"))
        with self.assertRaises(InvestmentsStateError): self.svc.im_approve_sell(ORG, h["id"], 3, {}, U4)
        with self.assertRaises(InvestmentsStateError): self.svc.im_reject_sell(ORG, h["id"], 3, "Rejecting an applied sale", U4)

    def test_selling_everything_leaves_no_residue_and_a_loss_is_negative(self):
        h = self.buy(self.hold(), 3, "10.01", "0"); self.sell(h, 3, "5", "0"); d = self.svc.im_approve_sell(ORG, h["id"], 2, {}, U3)
        self.assertEqual((d["units"], d["cost_basis"], d["realised_total"], d["trades"][-1]["cost_removed"], d["trades"][-1]["realised"]), ("0", "0.00", "-15.03", "30.03", "-15.03"))

    def test_partial_sales_never_drift(self):
        h = self.buy(self.hold(), 7, "3.33", "0.01"); total = Decimal("0")
        for k, q in enumerate((2, 3, 2), start=2):
            self.sell(h, q, "4", "0", reference=f"S-{q}{k}"); d = self.svc.im_approve_sell(ORG, h["id"], len(self.svc.im_get_holding(ORG, h["id"])["trades"]), {}, U3); total += Decimal(d["trades"][-1]["cost_removed"])
        self.assertEqual((d["units"], d["cost_basis"]), ("0", "0.00")); self.assertEqual(total, Decimal("23.32"))

    def test_validation_and_limits(self):
        h = self.buy(self.hold(), 5)
        with self.assertRaises(InvestmentsStateError): self.sell(h, 6)
        for bad in (dict(units=0), dict(units="x"), dict(price="0"), dict(traded_on="2026-04-30"), dict(reference=""), dict(fee="-1")):
            with self.assertRaises(InvestmentsError, msg=str(bad)): self.sell(h, **{"units": 1, **bad})
        with self.assertRaises(InvestmentsError): self.sell(h, 1, "10", "11")
        self.assertEqual(self.sell(h, 1, "10", "10")["pending_sells"], 1)

    def test_approval_checks_units_again(self):
        h = self.buy(self.hold(), 5); self.sell(h, 4); self.sell(h, 4, reference="CN-901"); self.svc.im_approve_sell(ORG, h["id"], 2, {}, U3)
        with self.assertRaises(InvestmentsStateError): self.svc.im_approve_sell(ORG, h["id"], 3, {}, U3)
        r = self.svc.im_reject_sell(ORG, h["id"], 3, "Units have moved since this was proposed", U3); self.assertEqual((r["units"], r["trades"][2]["status"]), ("1", "REJECTED"))

    def test_reject_needs_reason_and_missing_numbers(self):
        h = self.buy(self.hold(), 5); self.sell(h)
        with self.assertRaises(InvestmentsError): self.svc.im_reject_sell(ORG, h["id"], 2, "short", U3)
        for no in (1, 9):
            with self.assertRaises((InvestmentsStateError, InvestmentsNotFoundError)): self.svc.im_approve_sell(ORG, h["id"], no, {}, U3)   # a purchase is not a sale
        with self.assertRaises(InvestmentsError): self.svc.im_approve_sell(ORG, h["id"], "x", {}, U3)

    def test_at_most_five_waiting(self):
        h = self.buy(self.hold(), 50)
        for _ in range(5): self.sell(h)
        with self.assertRaises(InvestmentsStateError): self.sell(h)

    def test_applied_on_is_the_approval_day(self):
        h = self.buy(self.hold(), 5); self.sell(h); self.clock.d = date(2026, 3, 20); t = self.svc.im_approve_sell(ORG, h["id"], 2, {}, U3)["trades"][-1]
        self.assertEqual((t["traded_on"], t["applied_on"]), ("2026-03-10", "2026-03-20"))


class Marks(Base):
    def test_market_value_and_unrealised(self):
        h = self.buy(self.buy(self.hold(), 10, "100.00", "5.00"), 5, "120.5", "0", reference="CN-2"); self.assertTrue(h["no_mark"]); self.assertIsNone(h["market_value"])
        h = self.mark(h, "110"); self.assertEqual((h["market_value"], h["unrealised"], h["no_mark"], h["latest_mark"]["source"]), ("1650.00", "42.50", False, "Broker statement"))
        h = self.mark(h, "105.25", as_of="2026-03-01", source="Older statement"); self.assertEqual(h["latest_mark"]["price"], "110.0000")   # the newest date wins, not the last typed
        h = self.mark(h, "99.9999", as_of="2026-03-10", source="Exchange close"); self.assertEqual((h["market_value"], h["unrealised"]), ("1500.00", "-107.50")); self.assertEqual(len(h["marks"]), 3)

    def test_stale_follows_the_setting(self):
        h = self.mark(self.buy(self.hold(), 5)); self.assertFalse(h["mark_stale"]); self.clock.d = date(2026, 4, 15); self.assertTrue(self.svc.im_get_holding(ORG, h["id"])["mark_stale"])
        self.svc.im_set_policy(ORG, {"stale_days": 60}, U3); self.assertFalse(self.svc.im_get_holding(ORG, h["id"])["mark_stale"])
        e = self.hold(identifier="empty-1"); self.assertFalse(self.svc.im_get_holding(ORG, e["id"])["mark_stale"]); self.assertFalse(e["no_mark"])

    def test_validation(self):
        h = self.hold()
        for bad in (dict(price="0"), dict(price="x"), dict(price=1.5), dict(price=None), dict(price="1.23456"), dict(as_of="2026-04-30"), dict(as_of="soon"), dict(source="x"), dict(source="")):
            with self.assertRaises(InvestmentsError, msg=str(bad)): self.svc.im_record_mark(ORG, h["id"], {"price": "5", "as_of": "2026-03-09", "source": "Statement", **bad}, U1)
        self.assertEqual(self.mark(h, 5)["latest_mark"]["price"], "5.0000")


class Overview(Base):
    def test_totals_per_currency_and_attention(self):
        a = self.mark(self.buy(self.hold(), 10, "100.00", "5.00"), "110"); b = self.buy(self.hold(identifier="b-1", name="Treasury bill"), 4, "50", "0")
        c = self.mark(self.buy(self.hold(identifier="c-1", currency="USD", name="Dollar fund", asset_class="FUND"), 2, "10.5", "0"), "11")
        d = self.buy(self.hold(identifier="d-1", name="Sold position"), 1, "10", "0"); self.sell(d, 1, "12", "0"); self.svc.im_approve_sell(ORG, d["id"], 2, {}, U3); self.svc.im_close_holding(ORG, d["id"], "Fully sold and settled", U3)
        self.sell(a, 1, "120", "0")
        o = self.svc.im_overview(ORG); kinds = {x["kind"]: x["count"] for x in o["attention"]}; self.assertEqual(kinds, {"SELLS_TO_APPROVE": 1, "NO_PRICE": 1})
        t = {x["currency"]: x for x in o["totals"]}
        self.assertEqual((t["NGN"]["holdings"], t["NGN"]["cost"], t["NGN"]["valued"], t["NGN"]["unvalued"], t["NGN"]["market_value"], t["NGN"]["unrealised"], t["NGN"]["realised"]), (2, "1205.00", 1, 1, "1100.00", "95.00", "2.00"))
        self.assertEqual((t["USD"]["holdings"], t["USD"]["cost"], t["USD"]["market_value"], t["USD"]["unrealised"], t["USD"]["realised"]), (1, "21.00", "22.00", "1.00", "0.00")); self.assertEqual((o["counts"]["active"], o["counts"]["closed"]), (3, 1))

    def test_stale_attention(self):
        self.mark(self.buy(self.hold(), 5)); self.clock.d = date(2026, 4, 15); self.assertEqual({x["kind"]: x["count"] for x in self.svc.im_overview(ORG)["attention"]}, {"PRICES_STALE": 1})

    def test_empty(self):
        o = self.svc.im_overview(OTHER); self.assertEqual((o["attention"], o["totals"]), ([], [])); self.assertIn("BOND", self.svc.im_options(ORG)["asset_classes"]); self.assertTrue(o["limitations"])


class Isolation(Base):
    def test_other_company_sees_nothing_and_cannot_touch(self):
        h = self.buy(self.hold(), 5); self.sell(h); self.assertEqual(self.svc.im_list_holdings(OTHER), [])
        for fn in (lambda: self.svc.im_get_holding(OTHER, h["id"]), lambda: self.svc.im_buy(OTHER, h["id"], {}, U1), lambda: self.svc.im_propose_sell(OTHER, h["id"], {}, U1), lambda: self.svc.im_record_mark(OTHER, h["id"], {}, U1),
                   lambda: self.svc.im_approve_sell(OTHER, h["id"], 2, {}, U3), lambda: self.svc.im_reject_sell(OTHER, h["id"], 2, "Rejecting from outside", U3), lambda: self.svc.im_close_holding(OTHER, h["id"], "Closing from outside here", U3)):
            with self.assertRaises(InvestmentsNotFoundError): fn()

    def test_same_identifier_allowed_in_each_company(self):
        self.hold(); self.assertEqual(self.svc.im_add_holding(OTHER, dict(name="Dangote Cement shares", identifier="DANGCEM", asset_class="EQUITY", currency="NGN", account="Broker"), U1)["ref"], "HD-001")


class Audit(Base):
    def test_every_write_logged_without_content(self):
        h = self.buy(self.hold(), 10, "100.00", "5.00"); self.mark(h); self.svc.im_set_policy(ORG, {"stale_days": 100}, U3)
        self.sell(h, 1, "123.45"); self.svc.im_approve_sell(ORG, h["id"], 2, {}, U3); self.sell(h, 1, "99.99", reference="CN-777"); self.svc.im_reject_sell(ORG, h["id"], 3, "Price was typed wrongly this time", U3)
        j = self.hold(identifier="old-1"); self.svc.im_close_holding(ORG, j["id"], "Position was never opened here", U3)
        acts = [x[0] for x in self.events]
        for x in ("INVESTMENTS_HOLDING_ADDED", "INVESTMENTS_HOLDING_CLOSED", "INVESTMENTS_BUY_RECORDED", "INVESTMENTS_SELL_PROPOSED", "INVESTMENTS_SELL_APPROVED", "INVESTMENTS_SELL_REJECTED", "INVESTMENTS_MARK_RECORDED", "INVESTMENTS_POLICY_SET"): self.assertIn(x, acts)
        blob = " ".join(str(x) for x in self.events)
        for secret in ("Dangote", "Broker account", "CN-001", "CN-777", "1005", "123.45", "99.99", "Broker statement", "typed wrongly"): self.assertNotIn(secret, blob)

    def test_failed_actions_are_not_logged(self):
        with self.assertRaises(InvestmentsError): self.hold(name="ab")
        self.assertEqual(self.events, [])


class Permissions(unittest.TestCase):
    def test_roles(self):
        has = lambda r, p: p in ROLE_PERMISSIONS[r]
        for r in (Role.OWNER, Role.ADMINISTRATOR, Role.MANAGER, Role.AUDITOR): self.assertTrue(has(r, INVEST_PREPARE), r)
        for r in (Role.OWNER, Role.APPROVER, Role.MANAGER): self.assertTrue(has(r, INVEST_APPROVE), r)
        for r in (Role.ACCOUNTANT, Role.REVIEWER, Role.EXTERNAL_AUDITOR, Role.READ_ONLY, Role.DONOR, Role.REGULATOR, Role.INVESTOR_REVIEWER): self.assertFalse(has(r, INVEST_PREPARE) or has(r, INVEST_APPROVE), r)

    def test_anyone_who_can_prepare_or_approve_can_view(self):
        for r, perms in ROLE_PERMISSIONS.items():
            if INVEST_PREPARE in perms or INVEST_APPROVE in perms: self.assertIn(AUDIT_READ, perms, r)


class RouterGuards(unittest.TestCase):
    SRC = os.path.join(os.path.dirname(__file__), "..", "src", "asavexa", "api", "routers", "investments.py")

    def test_every_write_has_the_right_guard(self):
        tree = ast.parse(open(self.SRC).read()); named = {"_prepare": "INVEST_PREPARE", "_approve": "INVEST_APPROVE"}; g = {}
        for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.decorator_list]:
            verbs, guards = set(), set()
            for dec in fn.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute): verbs.add(dec.func.attr)
                for kw in getattr(dec, "keywords", []):
                    if kw.arg == "dependencies": guards |= {named[e.id] for e in kw.value.elts if isinstance(e, ast.Name) and e.id in named}
            g[fn.name] = (verbs, guards)
        approve = {"set_policy", "close_holding", "approve_sell", "reject_sell"}
        prepare = {"add_holding", "buy", "propose_sell", "record_mark"}
        for n in approve: self.assertEqual(g[n][1], {"INVEST_APPROVE"}, n)
        for n in prepare: self.assertEqual(g[n][1], {"INVEST_PREPARE"}, n)
        for n, (verbs, guards) in g.items():
            if verbs == {"get"}: self.assertEqual(guards, set(), n)
            else: self.assertIn(n, approve | prepare, f"{n} writes but has no investments guard")
        src = open(self.SRC).read(); self.assertIn("dependencies=[Depends(require_permission(AUDIT_READ))]", src); self.assertNotIn("org_id", src)


if __name__ == "__main__":
    unittest.main()
