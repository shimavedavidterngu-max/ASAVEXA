"""Mergers and acquisitions: deals, due-diligence checklist, closing conditions, exact price adjustments, different-person decisions, closing rules, isolation, audit and permissions."""
import ast
import os
import unittest
from datetime import date, datetime, timezone
from fractions import Fraction

from analysis_fixture import ORG, OTHER, World
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.permissions import AUDIT_READ, MNA_APPROVE, MNA_PREPARE, ROLE_PERMISSIONS
from asavexa.mergers.errors import MergersError, MergersForbiddenError, MergersNotFoundError, MergersStateError
from asavexa.mergers.service import MergersService

U1, U2, U3, U4 = "user-1", "user-2", "user-3", "user-4"   # U1 and U2 prepare, U3 and U4 approve


class Clock:
    def __init__(self): self.d = date(2026, 3, 31)
    def __call__(self): return datetime(self.d.year, self.d.month, self.d.day, 9, tzinfo=timezone.utc)


class Base(unittest.TestCase):
    def setUp(self):
        self.w = World(); self.clock = Clock(); self.events = []
        self.svc = MergersService(self.w.store, None, log=lambda *a: self.events.append(a), now=self.clock)

    def deal(self, actor=U1, **kw):
        d = dict(name="Project Falcon", deal_ref="FALCON", currency="NGN", deal_type="ACQUISITION", base_price="1000000", target_close_date="2026-09-30", description="Acquisition of a distribution business"); d.update(kw)
        return self.svc.ma_add_deal(ORG, d, actor)

    def open(self, actor=U1, approver=U3, **kw):
        x = self.deal(actor, **kw); return self.svc.ma_approve_deal(ORG, x["id"], {}, approver)

    def chk(self, x, title="Audited accounts reviewed", area="FINANCIAL", actor=U1):
        return self.svc.ma_add_checklist(ORG, x["id"], dict(title=title, area=area), actor)

    def cond(self, x, title="Regulator consent received", due="2026-04-20", actor=U1):
        return self.svc.ma_add_condition(ORG, x["id"], dict(title=title, due_date=due), actor)

    def adj(self, x, kind="DECREASE", amt="50000", basis="Working capital shortfall found", actor=U1):
        return self.svc.ma_add_adjustment(ORG, x["id"], dict(kind=kind, amount=amt, basis=basis), actor)

    def prov(self, x, kind, no, actor=U1, on="2026-03-30", note="Documents received and filed"):
        return self.svc.ma_provide(ORG, x["id"], kind, no, dict(done_on=on, note=note), actor)

    def conf(self, x, kind, no, actor=U3, note=None):
        return self.svc.ma_decide(ORG, x["id"], kind, no, True, {"note": note} if note else {}, actor)

    def full(self, x, kind, no):
        return self.conf(self.prov(x, kind, no), kind, no)


class Price(Base):
    def test_exact_adjusted_price(self):
        x = self.open(); self.assertEqual((x["adjusted_price"], x["price_change"], x["price_change_pct"]), ("1000000.00", "0.00", "0.00"))
        x = self.adj(x, "DECREASE", "50000.50"); self.assertEqual(x["adjusted_price"], "1000000.00")                   # waiting does not count
        x = self.conf(x, "adjustments", 1); self.assertEqual((x["adjusted_price"], x["price_change"], x["price_change_pct"]), ("949999.50", "-50000.50", "-5.00"))
        x = self.conf(self.adj(x, "INCREASE", "12345.67", "Inventory above the agreed level"), "adjustments", 2); self.assertEqual((x["adjusted_price"], x["price_change"], x["price_change_pct"]), ("962345.17", "-37654.83", "-3.77"))

    def test_percentage_matches_independent_arithmetic(self):
        for base, kind, amt in (("333.33", "INCREASE", "1.00"), ("1", "INCREASE", "0.01"), ("99999999.99", "DECREASE", "12345.67"), ("7", "DECREASE", "3"), ("1000", "INCREASE", "1")):
            x = self.open(name=f"D {base} {amt}", base_price=base); x = self.conf(self.adj(x, kind, amt), "adjustments", 1); p = Fraction(amt) / Fraction(base) * 100 * (1 if kind == "INCREASE" else -1)
            n = p.numerator * 200; q = (abs(n) + p.denominator) // (2 * p.denominator); self.assertEqual(x["price_change_pct"], f"{(q if p >= 0 else -q) / 100:.2f}", (base, amt))

    def test_rejected_adjustments_do_not_count_and_price_never_goes_below_zero(self):
        x = self.open(base_price="100"); x = self.adj(x, "DECREASE", "100"); x = self.svc.ma_decide(ORG, x["id"], "adjustments", 1, False, "The figure was a typing slip", U3); self.assertEqual(x["adjusted_price"], "100.00")
        x = self.conf(self.adj(x, "DECREASE", "60"), "adjustments", 2); x = self.adj(x, "DECREASE", "50")
        with self.assertRaises(MergersStateError): self.conf(x, "adjustments", 3)                                         # would take the price to -10
        x = self.conf(self.adj(x, "INCREASE", "20"), "adjustments", 4); x = self.conf(x, "adjustments", 3); self.assertEqual(x["adjusted_price"], "10.00")

    def test_validation(self):
        x = self.open()
        for bad in ({"kind": "UP"}, {"kind": None}, {"amount": "0"}, {"amount": "x"}, {"amount": -1}, {"amount": 5.5}, {"amount": True}, {"amount": None}, {"amount": "1.234"}, {"basis": "short"}):
            d = dict(kind="INCREASE", amount="10", basis="Inventory above the level"); d.update(bad)
            with self.assertRaises(MergersError, msg=bad): self.svc.ma_add_adjustment(ORG, x["id"], d, U1)
        self.assertEqual(self.adj(x, "increase")["adjustments"][0]["kind"], "INCREASE")


class Checklist(Base):
    def test_progress_is_exact(self):
        x = self.open(); self.assertIsNone(x["checklist_pct"])
        x = self.chk(self.chk(self.chk(x), "Contracts reviewed", "LEGAL"), "Tax filings reviewed", "TAX"); self.assertEqual((x["checklist_total"], x["checklist_confirmed"], x["checklist_pct"], x["open_checklist"]), (3, 0, "0.00", 3))
        x = self.full(x, "checklist", 1); self.assertEqual((x["checklist_pct"], x["open_checklist"]), ("33.33", 2)); x = self.full(x, "checklist", 2); self.assertEqual(x["checklist_pct"], "66.67")
        self.assertEqual(x["by_area"], {"FINANCIAL": {"total": 1, "confirmed": 1}, "LEGAL": {"total": 1, "confirmed": 1}, "TAX": {"total": 1, "confirmed": 0}})
        x = self.full(x, "checklist", 3); self.assertEqual(x["checklist_pct"], "100.00")

    def test_provided_waits_and_reject_sends_back(self):
        x = self.prov(self.chk(self.open()), "checklist", 1); self.assertEqual((x["checklist"][0]["status"], x["checklist_confirmed"], x["pending"]), ("DONE", 0, 1))
        with self.assertRaises(MergersForbiddenError): self.conf(x, "checklist", 1, U1)
        with self.assertRaises(MergersForbiddenError): self.svc.ma_decide(ORG, x["id"], "checklist", 1, False, "Rejecting my own record", U1)
        x = self.svc.ma_decide(ORG, x["id"], "checklist", 1, False, "The accounts shown were unsigned", U3); r = x["checklist"][0]
        self.assertEqual((r["status"], r["done_on"], r["done_by"], r["decision_note"]), ("OPEN", None, None, "The accounts shown were unsigned"))
        x = self.prov(x, "checklist", 1, U2); self.assertEqual(x["checklist"][0]["status"], "DONE")
        with self.assertRaises(MergersForbiddenError): self.conf(x, "checklist", 1, U2)

    def test_only_the_person_who_marked_it_is_barred_from_confirming(self):
        x = self.chk(self.open(), actor=U1); x = self.prov(x, "checklist", 1, U2); self.assertEqual(self.conf(x, "checklist", 1, U1)["checklist"][0]["status"], "CONFIRMED")      # adding and confirming are different acts; marking and confirming must differ

    def test_validation(self):
        x = self.open()
        for bad in ({"title": "ab"}, {"title": None}, {"area": "SPACE"}, {"area": None}):
            d = dict(title="Contracts reviewed", area="LEGAL"); d.update(bad)
            with self.assertRaises(MergersError, msg=bad): self.svc.ma_add_checklist(ORG, x["id"], d, U1)
        x = self.chk(x)
        with self.assertRaises(MergersStateError): self.chk(x)
        self.assertEqual(len(self.chk(x, area="LEGAL")["checklist"]), 2)                                                      # the same title in another area is fine
        for bad in ({"done_on": "2026-04-05"}, {"done_on": "x"}, {"done_on": "1999-01-01"}, {"note": "short"}):
            d = dict(done_on="2026-03-30", note="Documents received and filed"); d.update(bad)
            with self.assertRaises(MergersError, msg=bad): self.svc.ma_provide(ORG, x["id"], "checklist", 1, d, U1)
        for bad in ("members", None, ["checklist"], "adjustments"):
            with self.assertRaises(MergersError): self.svc.ma_provide(ORG, x["id"], bad, 1, dict(done_on="2026-03-30", note="Documents received and filed"), U1)
        self.prov(x, "checklist", 1)
        with self.assertRaises(MergersStateError): self.prov(x, "checklist", 1)


class Conditions(Base):
    def test_flags(self):
        x = self.open(); x = self.cond(x, "Regulator consent", "2026-04-10"); x = self.cond(x, "Board approval", "2026-03-30"); x = self.cond(x, "Financing in place", "2026-09-01")
        self.assertEqual([(c["overdue"], c["due_soon"]) for c in x["conditions"]], [(False, True), (True, False), (False, False)]); self.assertEqual((x["overdue_conditions"], x["due_soon_conditions"]), (1, 1))
        x = self.full(x, "conditions", 2); self.assertEqual((x["overdue_conditions"], x["conditions_confirmed"], x["conditions_total"]), (0, 1, 3))
        self.svc.ma_set_setting(ORG, {"due_soon_days": 200}, U3); self.assertEqual(self.svc.ma_get_deal(ORG, x["id"])["due_soon_conditions"], 2)

    def test_validation(self):
        x = self.open()
        for bad in ({"title": "ab"}, {"due_date": "2026-02-30"}, {"due_date": "1999-01-01"}, {"due_date": "2101-01-01"}, {"due_date": None}):
            d = dict(title="Regulator consent", due_date="2026-04-10"); d.update(bad)
            with self.assertRaises(MergersError, msg=bad): self.svc.ma_add_condition(ORG, x["id"], d, U1)
        x = self.cond(x)
        with self.assertRaises(MergersStateError): self.cond(x)

    def test_met_condition_is_confirmed_by_someone_else(self):
        x = self.prov(self.cond(self.open()), "conditions", 1)
        with self.assertRaises(MergersForbiddenError): self.conf(x, "conditions", 1, U1)
        self.assertEqual(self.conf(x, "conditions", 1, U3, "Consent letter checked")["conditions"][0]["decision_note"], "Consent letter checked")
        with self.assertRaises(MergersStateError): self.conf(x, "conditions", 1, U4)


class Deals(Base):
    def test_validation(self):
        for bad in ({"name": "ab"}, {"deal_ref": "x"}, {"currency": "NG"}, {"deal_type": "SWAP"}, {"deal_type": None}, {"base_price": "0"}, {"base_price": "x"}, {"base_price": -1}, {"base_price": 5.5}, {"base_price": True}, {"base_price": None}, {"base_price": "1.234"},
                    {"target_close_date": "2026-02-30"}, {"target_close_date": "1999-01-01"}, {"target_close_date": "2101-01-01"}, {"target_close_date": None}, {"description": "short"}):
            with self.assertRaises(MergersError, msg=bad): self.deal(**bad)
        x = self.deal(currency="ngn", deal_type="merger"); self.assertEqual((x["ref"], x["currency"], x["deal_type"], x["status"], x["base_price"]), ("MD-001", "NGN", "MERGER", "PROPOSED", "1000000.00")); self.assertEqual(self.deal()["ref"], "MD-002")

    def test_decisions(self):
        x = self.deal()
        with self.assertRaises(MergersForbiddenError): self.svc.ma_approve_deal(ORG, x["id"], {}, U1)
        with self.assertRaises(MergersForbiddenError): self.svc.ma_reject_deal(ORG, x["id"], "Rejecting my own deal", U1)
        with self.assertRaises(MergersError): self.svc.ma_reject_deal(ORG, x["id"], "short", U3)
        with self.assertRaises(MergersError): self.svc.ma_approve_deal(ORG, x["id"], {"note": "short"}, U3)
        with self.assertRaises(MergersStateError): self.chk(x)
        self.assertEqual(self.svc.ma_approve_deal(ORG, x["id"], {"note": "Board minute seen"}, U3)["status"], "APPROVED")
        with self.assertRaises(MergersStateError): self.svc.ma_approve_deal(ORG, x["id"], {}, U4)
        y = self.deal(); self.assertEqual(self.svc.ma_reject_deal(ORG, y["id"], "Duplicate of another deal", U3)["status"], "REJECTED")
        with self.assertRaises(MergersStateError): self.adj(y)

    def test_record_decision_errors(self):
        x = self.adj(self.open())
        for bad in ("x", None, True, 1.5):
            with self.assertRaises(MergersError): self.conf(x, "adjustments", bad)
        with self.assertRaises(MergersNotFoundError): self.conf(x, "adjustments", 9)
        for bad in ("members", None, ["checklist"], 5):
            with self.assertRaises(MergersError): self.svc.ma_decide(ORG, x["id"], bad, 1, True, {}, U3)
        with self.assertRaises(MergersForbiddenError): self.conf(x, "adjustments", 1, U1)
        with self.assertRaises(MergersError): self.svc.ma_decide(ORG, x["id"], "adjustments", 1, False, "short", U3)
        with self.assertRaises(MergersError): self.conf(x, "adjustments", 1, U3, "short")
        self.conf(x, "adjustments", 1)
        with self.assertRaises(MergersStateError): self.conf(x, "adjustments", 1, U4)
        y = self.chk(self.open(name="Second"))
        with self.assertRaises(MergersStateError): self.conf(y, "checklist", 1)                                              # nothing has been provided yet

    def test_close_rules(self):
        x = self.chk(self.open()); x = self.cond(x); x = self.prov(x, "checklist", 1)
        with self.assertRaises(MergersStateError): self.svc.ma_close_deal(ORG, x["id"], dict(outcome="ABANDONED", reason="Talks have ended"), U3)         # something waits
        x = self.conf(x, "checklist", 1)
        with self.assertRaises(MergersStateError): self.svc.ma_close_deal(ORG, x["id"], dict(outcome="COMPLETED", reason="The deal has closed"), U3)       # a condition is still open
        for bad in ({"outcome": "DONE"}, {"outcome": None}, {"reason": "short"}):
            with self.assertRaises(MergersError, msg=bad): self.svc.ma_close_deal(ORG, x["id"], {**dict(outcome="ABANDONED", reason="Talks have ended"), **bad}, U3)
        x = self.full(x, "conditions", 1); c = self.svc.ma_close_deal(ORG, x["id"], dict(outcome="COMPLETED", reason="The deal has closed"), U3)
        self.assertEqual((c["status"], c["outcome"], c["close_note"]), ("CLOSED", "COMPLETED", "The deal has closed"))
        for f in (lambda: self.chk(c, "Another", "LEGAL"), lambda: self.adj(c), lambda: self.svc.ma_close_deal(ORG, x["id"], dict(outcome="ABANDONED", reason="Closing it again"), U3)):
            with self.assertRaises(MergersStateError): f()

    def test_abandon_with_open_items(self):
        x = self.cond(self.chk(self.open())); c = self.svc.ma_close_deal(ORG, x["id"], dict(outcome="abandoned", reason="Talks have ended"), U3); self.assertEqual((c["status"], c["outcome"]), ("CLOSED", "ABANDONED"))

    def test_list_is_summary_only(self):
        self.chk(self.open()); row = self.svc.ma_list_deals(ORG)[0]; self.assertEqual((row["checklist"], row["conditions"], row["adjustments"], row["history"], row["open_checklist"]), ([], [], [], [], 1))
        self.assertEqual(len(self.svc.ma_list_deals(ORG, "APPROVED")), 1); self.assertEqual(self.svc.ma_list_deals(ORG, "PROPOSED"), [])


class Settings(Base):
    def test_settings(self):
        self.assertEqual(self.svc.ma_get_setting(ORG)["due_soon_days"], 14)
        for bad in (0, 366, "x", 1.5, True):
            with self.assertRaises(MergersError, msg=bad): self.svc.ma_set_setting(ORG, {"due_soon_days": bad}, U3)
        self.assertEqual(self.svc.ma_set_setting(ORG, {"due_soon_days": "30"}, U3)["due_soon_days"], 30)


class Overview(Base):
    def test_counts_attention_and_rollup(self):
        self.deal(); a = self.open(name="Deal A"); a = self.chk(a); a = self.cond(a, "Consent", "2026-03-30"); a = self.cond(a, "Financing", "2026-04-05")
        b = self.open(name="Deal B", currency="USD", base_price="500.50", target_close_date="2026-03-01"); b = self.conf(self.adj(b, "INCREASE", "10.25", "Inventory above the level"), "adjustments", 1)
        c = self.open(name="Deal C"); self.svc.ma_close_deal(ORG, c["id"], dict(outcome="ABANDONED", reason="Talks have ended"), U3)
        r = self.deal(name="Deal R"); self.svc.ma_reject_deal(ORG, r["id"], "Duplicate of another deal", U3); self.adj(a)
        o = self.svc.ma_overview(ORG); self.assertEqual(o["counts"], {"proposed": 1, "approved": 2, "rejected": 1, "closed": 1}); self.assertEqual(o["outcomes"], {"completed": 0, "abandoned": 1})
        self.assertEqual({x["kind"]: x["count"] for x in o["attention"]}, {"DEALS_TO_APPROVE": 1, "ITEMS_TO_DECIDE": 1, "CHECKLIST_OPEN": 1, "CONDITIONS_OVERDUE": 1, "CONDITIONS_DUE_SOON": 1, "TARGET_DATE_PASSED": 1})
        self.assertEqual([(t["currency"], t["deals"], t["base_price"], t["adjusted_price"]) for t in o["by_currency"]], [("NGN", 1, "1000000.00", "1000000.00"), ("USD", 1, "500.50", "510.75")])      # currencies are never added together

    def test_empty(self):
        o = self.svc.ma_overview(ORG); self.assertEqual((o["attention"], o["by_currency"], o["counts"]["approved"]), ([], [], 0))


class Isolation(Base):
    def test_other_company(self):
        x = self.adj(self.open()); self.assertEqual(self.svc.ma_list_deals(OTHER), [])
        for f in (lambda: self.svc.ma_get_deal(OTHER, x["id"]), lambda: self.svc.ma_decide(OTHER, x["id"], "adjustments", 1, True, {}, U3), lambda: self.svc.ma_add_checklist(OTHER, x["id"], {}, U1), lambda: self.svc.ma_close_deal(OTHER, x["id"], {}, U3), lambda: self.svc.ma_provide(OTHER, x["id"], "checklist", 1, {}, U1)):
            with self.assertRaises(MergersNotFoundError): f()
        self.assertEqual(self.svc.ma_add_deal(OTHER, dict(name="Other deal", deal_ref="OPS-1", currency="NGN", deal_type="OTHER", base_price="10", target_close_date="2026-12-31", description="A deal at another company"), U1)["ref"], "MD-001")


class Audit(Base):
    def test_every_write_logged_without_content(self):
        x = self.open(name="Secret deal name"); x = self.chk(x, "Secret checklist title"); x = self.prov(x, "checklist", 1, note="Chinedu sent the data room link"); self.conf(x, "checklist", 1, U3, "Matches the data room")
        x = self.cond(x, "Secret condition", "2026-04-20"); x = self.prov(x, "conditions", 1); x = self.svc.ma_decide(ORG, x["id"], "conditions", 1, False, "The letter was unsigned", U3); x = self.adj(x, "INCREASE", "77777.77", "Stock above the agreed level")
        self.conf(x, "adjustments", 1); y = self.deal(name="Rejected deal"); self.svc.ma_reject_deal(ORG, y["id"], "Duplicate of another deal", U3); self.svc.ma_set_setting(ORG, {"due_soon_days": 3}, U3)
        z = self.open(name="Deal Z"); self.svc.ma_close_deal(ORG, z["id"], dict(outcome="ABANDONED", reason="Talks have ended"), U3)
        acts = {e[0] for e in self.events}
        for a in ("MERGERS_DEAL_PROPOSED", "MERGERS_DEAL_APPROVED", "MERGERS_DEAL_REJECTED", "MERGERS_DEAL_CLOSED", "MERGERS_CHECKLIST_ADDED", "MERGERS_CHECKLIST_PROVIDED", "MERGERS_CHECKLIST_CONFIRMED", "MERGERS_CONDITION_ADDED", "MERGERS_CONDITION_MET",
                  "MERGERS_CONDITION_REJECTED", "MERGERS_ADJUSTMENT_ADDED", "MERGERS_ADJUSTMENT_CONFIRMED", "MERGERS_SETTING_SET"): self.assertIn(a, acts)
        blob = " ".join(str(e) for e in self.events)
        for secret in ("Secret deal", "FALCON", "Secret checklist", "Secret condition", "77777", "1000000", "Chinedu", "data room", "unsigned", "Stock above", "Duplicate of", "Talks have ended"): self.assertNotIn(secret, blob)

    def test_failed_actions_are_not_logged(self):
        with self.assertRaises(MergersError): self.deal(name="ab")
        x = self.open(); n = len(self.events)
        with self.assertRaises(MergersError): self.chk(x, area="SPACE")
        with self.assertRaises(MergersForbiddenError): self.svc.ma_approve_deal(ORG, self.deal()["id"], {}, U1)
        self.assertEqual(len(self.events), n + 1)                                                          # only the deal proposed above


class Permissions(unittest.TestCase):
    def test_roles(self):
        has = lambda r, p: p in ROLE_PERMISSIONS[r]
        for r in (Role.OWNER, Role.ADMINISTRATOR, Role.MANAGER, Role.AUDITOR): self.assertTrue(has(r, MNA_PREPARE), r)
        for r in (Role.OWNER, Role.APPROVER, Role.MANAGER): self.assertTrue(has(r, MNA_APPROVE), r)
        for r in (Role.ACCOUNTANT, Role.REVIEWER, Role.EXTERNAL_AUDITOR, Role.READ_ONLY, Role.DONOR, Role.REGULATOR, Role.INVESTOR_REVIEWER): self.assertFalse(has(r, MNA_PREPARE) or has(r, MNA_APPROVE), r)

    def test_anyone_who_can_prepare_or_approve_can_view(self):
        for r, perms in ROLE_PERMISSIONS.items():
            if MNA_PREPARE in perms or MNA_APPROVE in perms: self.assertIn(AUDIT_READ, perms, r)


class RouterGuards(unittest.TestCase):
    SRC = os.path.join(os.path.dirname(__file__), "..", "src", "asavexa", "api", "routers", "mergers.py")

    def test_every_write_has_the_right_guard(self):
        with open(self.SRC) as fh: src = fh.read()
        tree = ast.parse(src); named = {"_prepare": "MNA_PREPARE", "_approve": "MNA_APPROVE"}; g = {}
        for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.decorator_list]:
            verbs, guards = set(), set()
            for dec in fn.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute): verbs.add(dec.func.attr)
                for kw in getattr(dec, "keywords", []):
                    if kw.arg == "dependencies": guards |= {named[e.id] for e in kw.value.elts if isinstance(e, ast.Name) and e.id in named}
            g[fn.name] = (verbs, guards)
        approve = {"set_setting", "approve_deal", "reject_deal", "close_deal", "confirm_checklist", "reject_checklist", "confirm_condition", "reject_condition", "confirm_adjustment", "reject_adjustment"}
        prepare = {"add_deal", "add_checklist", "provide_checklist", "add_condition", "meet_condition", "add_adjustment"}
        for n in approve: self.assertEqual(g[n][1], {"MNA_APPROVE"}, n)
        for n in prepare: self.assertEqual(g[n][1], {"MNA_PREPARE"}, n)
        for n, (verbs, guards) in g.items():
            if verbs == {"get"}: self.assertEqual(guards, set(), n)
            else: self.assertIn(n, approve | prepare, f"{n} writes but has no mergers guard")
        self.assertIn("dependencies=[Depends(require_permission(AUDIT_READ))]", src); self.assertNotIn("org_id", src)


if __name__ == "__main__":
    unittest.main()
