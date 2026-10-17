"""Operations research: exact NPV, payback, benefit-cost and sensitivity (checked against an independent fraction calculation), the different-person workflow, the recorded decision, isolation, audit and permissions."""
import ast
import os
import unittest
from datetime import date, datetime, timezone
from fractions import Fraction

from analysis_fixture import ORG, OTHER, World
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.permissions import AUDIT_READ, OPR_APPROVE, OPR_PREPARE, ROLE_PERMISSIONS
from asavexa.oprs.errors import OprsError, OprsForbiddenError, OprsNotFoundError, OprsStateError
from asavexa.oprs.service import OprsService, round2

U1, U2, U3, U4 = "user-1", "user-2", "user-3", "user-4"   # U1 and U2 prepare, U3 and U4 approve


class Base(unittest.TestCase):
    def setUp(self):
        self.w = World(); self.events = []
        self.svc = OprsService(self.w.store, None, log=lambda *a: self.events.append(a), now=lambda: datetime(2026, 3, 31, 9, tzinfo=timezone.utc))

    def an(self, actor=U1, **kw):
        d = dict(title="Replace the delivery fleet", currency="ngn", discount_rate="10", purpose="Compare buying with leasing vans"); d.update(kw)
        return self.svc.op_create_analysis(ORG, d, actor)

    def opt(self, a, actor=U1, **kw):
        d = dict(name="Buy", upfront_cost="1000", flows=["600", "600"]); d.update(kw)
        return self.svc.op_add_option(ORG, a["id"], d, actor)

    def ready(self, actor=U1):
        a = self.an(actor); self.opt(a, actor); return self.opt(a, actor, name="Lease", upfront_cost="200", flows=["150", "150", "150"])

    def submitted(self, actor=U1):
        a = self.ready(actor); return self.svc.op_submit(ORG, a["id"], {}, actor)

    def approved(self, actor=U1, approver=U3):
        a = self.submitted(actor); return self.svc.op_approve(ORG, a["id"], {}, approver)


def indep_npv(upfront, flows, pct):
    r = Fraction(str(pct)) / 100
    return -Fraction(str(upfront)) + sum(Fraction(str(f)) / (1 + r) ** (i + 1) for i, f in enumerate(flows))


class Arithmetic(Base):
    def test_round_half_away_from_zero(self):
        for f, want in ((Fraction(5, 1000), "0.01"), (Fraction(-5, 1000), "-0.01"), (Fraction(4, 1000), "0.00"), (Fraction(-4, 1000), "0.00"), (Fraction(1, 3), "0.33"), (Fraction(2, 3), "0.67"), (Fraction(-2, 3), "-0.67"), (Fraction(12345, 100), "123.45")):
            self.assertEqual(str(round2(f)), want, f)

    def test_known_example(self):
        a = self.ready(); r = a["results"][0]
        self.assertEqual((r["npv"], r["total_flows"], r["net_value"], r["payback_year"], r["benefit_cost_ratio"], r["years"]), ("41.32", "1200.00", "200.00", 2, "1.20", 2))
        self.assertEqual([(s["rate"], s["npv"]) for s in r["sensitivity"]], [("8.00", str(round2(indep_npv(1000, [600, 600], 8)))), ("10.00", "41.32"), ("12.00", str(round2(indep_npv(1000, [600, 600], 12))))])

    def test_every_figure_matches_an_independent_calculation(self):
        for rate in ("0", "3.5", "7.25", "10", "99.99", "100"):
            a = self.an(discount_rate=rate); data = {"Opt A": (1234.5, [100, -50.25, 900.10, 0, 450]), "Opt B": (80, [10, 10, 10]), "Opt C": (1000000, [250000, 250000, 250000, 250000, 250000, 250000, 250000, 250000, 250000, 250000])}
            for n, (u, f) in data.items(): a = self.opt(a, name=n, upfront_cost=f"{u:.2f}", flows=[f"{x:.2f}" for x in f])
            for r in a["results"]:
                u, f = data[r["name"]]; want = indep_npv(f"{u:.2f}", [f"{x:.2f}" for x in f], rate)
                self.assertEqual(r["npv"], str(round2(want)), (rate, r["name"])); tot = sum(Fraction(f"{x:.2f}") for x in f)
                self.assertEqual(r["net_value"], str(round2(tot - Fraction(f"{u:.2f}")))); self.assertEqual(r["benefit_cost_ratio"], str(round2(tot / Fraction(f"{u:.2f}"))))

    def test_zero_rate_and_payback_boundaries(self):
        a = self.an(discount_rate="0"); a = self.opt(a, name="Exact", upfront_cost="500", flows=["100"] * 5); r = a["results"][0]
        self.assertEqual((r["npv"], r["payback_year"]), ("0.00", 5))                                    # cumulative equals the cost in year five
        a = self.opt(a, name="Never", upfront_cost="1000", flows=["-100", "200"]); self.assertIsNone(a["results"][1]["payback_year"])
        a = self.opt(a, name="Year one", upfront_cost="50", flows=["50"]); self.assertEqual(a["results"][2]["payback_year"], 1)

    def test_ranks_ties_and_highest(self):
        a = self.an(); a = self.opt(a, name="One", upfront_cost="100", flows=["60", "60"]); a = self.opt(a, name="Two", upfront_cost="100", flows=["60", "60"]); a = self.opt(a, name="Three", upfront_cost="100", flows=["10"])
        self.assertEqual([(r["name"], r["rank"], r["highest_npv"]) for r in a["results"]], [("One", 1, True), ("Two", 1, True), ("Three", 3, False)])

    def test_sensitivity_skips_negative_rates(self):
        a = self.an(discount_rate="1"); a = self.opt(a); self.assertEqual([s["rate"] for s in a["results"][0]["sensitivity"]], ["1.00", "3.00"])
        a = self.an(discount_rate="0"); a = self.opt(a); self.assertEqual([s["rate"] for s in a["results"][0]["sensitivity"]], ["0.00", "2.00"])

    def test_removed_options_drop_out(self):
        a = self.ready(); a = self.svc.op_remove_option(ORG, a["id"], 2, "Leasing is not on offer", U1)
        self.assertEqual([r["name"] for r in a["results"]], ["Buy"]); self.assertEqual((a["active_options"], a["options"][1]["status"], a["options"][1]["removed_note"]), (1, "REMOVED", "Leasing is not on offer"))


class Validation(Base):
    def test_analysis(self):
        for bad in ({"title": "ab"}, {"purpose": "short"}, {"currency": "NG"}, {"currency": "N1A"}, {"discount_rate": "100.01"}, {"discount_rate": "-1"}, {"discount_rate": "1e1"}, {"discount_rate": "１０"}, {"discount_rate": 5.5}, {"discount_rate": True}, {"discount_rate": None}, {"discount_rate": "1.234"}, {"discount_rate": "1,5"}):
            with self.assertRaises(OprsError, msg=bad): self.an(**bad)
        a = self.an(currency=" usd ", discount_rate="100"); self.assertEqual((a["ref"], a["currency"], a["discount_rate"], a["status"]), ("OA-001", "USD", "100.00", "DRAFT")); self.assertEqual(self.an()["ref"], "OA-002")

    def test_option(self):
        a = self.an()
        for bad in ({"name": "x"}, {"upfront_cost": "0"}, {"upfront_cost": 5.5}, {"upfront_cost": "-5"}, {"upfront_cost": "1.234"}, {"upfront_cost": None}, {"flows": []}, {"flows": "600"}, {"flows": None}, {"flows": ["1"] * 11}, {"flows": ["abc"]}, {"flows": [5.5]}, {"flows": ["1.234"]}, {"flows": [True]}, {"flows": [None]}, {"flows": ["600", "x"]}):
            with self.assertRaises(OprsError, msg=bad): self.opt(a, **bad)
        r = self.opt(a, flows=["-100.50", "0", "1,000.25", 7]); self.assertEqual(r["options"][0]["flows"], ["-100.50", "0.00", "1000.25", "7.00"])
        with self.assertRaises(OprsStateError): self.opt(a, name=" buy ")                                  # same name

    def test_option_limit_counts_active_options(self):
        a = self.an()
        for i in range(8): a = self.opt(a, name=f"Option {i}")
        with self.assertRaises(OprsStateError): self.opt(a, name="Option 9")
        a = self.svc.op_remove_option(ORG, a["id"], 1, "Dropped from the comparison", U1); self.assertEqual(self.opt(a, name="Option 9")["active_options"], 8)


class Workflow(Base):
    def test_submit_needs_two_options(self):
        a = self.an()
        with self.assertRaises(OprsStateError): self.svc.op_submit(ORG, a["id"], {}, U1)
        a = self.opt(a)
        with self.assertRaises(OprsStateError): self.svc.op_submit(ORG, a["id"], {}, U1)
        a = self.opt(a, name="Lease"); 
        with self.assertRaises(OprsError): self.svc.op_submit(ORG, a["id"], {"note": "short"}, U1)
        self.assertEqual(self.svc.op_submit(ORG, a["id"], {"note": "Ready for your review"}, U1)["status"], "SUBMITTED")

    def test_submitted_is_locked(self):
        a = self.submitted()
        for f in (lambda: self.opt(a, name="Late"), lambda: self.svc.op_remove_option(ORG, a["id"], 1, "Trying to remove it", U1), lambda: self.svc.op_withdraw(ORG, a["id"], "Trying to withdraw it", U1), lambda: self.svc.op_submit(ORG, a["id"], {}, U1)):
            with self.assertRaises(OprsStateError): f()

    def test_different_person_decides(self):
        a = self.submitted()
        with self.assertRaises(OprsForbiddenError): self.svc.op_approve(ORG, a["id"], {}, U1)
        with self.assertRaises(OprsForbiddenError): self.svc.op_return(ORG, a["id"], "Returning my own analysis", U1)
        with self.assertRaises(OprsError): self.svc.op_return(ORG, a["id"], "short", U3)
        with self.assertRaises(OprsError): self.svc.op_approve(ORG, a["id"], {"note": "short"}, U3)
        r = self.svc.op_return(ORG, a["id"], "Please add the lease quotes", U3); self.assertEqual((r["status"], r["decision_note"]), ("RETURNED", "Please add the lease quotes"))
        a = self.opt(r, name="Third", upfront_cost="10", flows=["5", "5", "5"]); self.assertEqual(a["active_options"], 3)       # a returned analysis can be edited again
        self.svc.op_submit(ORG, a["id"], {}, U2); self.assertEqual(self.svc.op_approve(ORG, a["id"], {"note": "Quotes are attached"}, U4)["status"], "APPROVED")
        for f in (lambda: self.svc.op_approve(ORG, a["id"], {}, U3), lambda: self.svc.op_return(ORG, a["id"], "Returning it later on", U3), lambda: self.opt(a, name="After"), lambda: self.svc.op_withdraw(ORG, a["id"], "Withdrawing it later", U1)):
            with self.assertRaises(OprsStateError): f()

    def test_withdraw(self):
        a = self.ready()
        with self.assertRaises(OprsError): self.svc.op_withdraw(ORG, a["id"], "short", U1)
        r = self.svc.op_withdraw(ORG, a["id"], "No longer needed at all", U1); self.assertEqual(r["status"], "WITHDRAWN")
        with self.assertRaises(OprsStateError): self.opt(r, name="After")

    def test_list_summary_only(self):
        self.approved(); row = self.svc.op_list_analyses(ORG)[0]; self.assertEqual((row["options"], row["results"], row["history"]), ([], [], [])); self.assertEqual(row["active_options"], 2)
        self.assertEqual(len(self.svc.op_list_analyses(ORG, "APPROVED")), 1); self.assertEqual(self.svc.op_list_analyses(ORG, "DRAFT"), [])


class Decision(Base):
    def test_rules(self):
        a = self.submitted()
        with self.assertRaises(OprsStateError): self.svc.op_decide(ORG, a["id"], {"option_no": 1, "rationale": "Chosen before approval"}, U3)
        a = self.svc.op_approve(ORG, a["id"], {}, U3)
        with self.assertRaises(OprsForbiddenError): self.svc.op_decide(ORG, a["id"], {"option_no": 1, "rationale": "I submitted this one"}, U1)
        for bad in ({"option_no": "x"}, {"option_no": None}, {"option_no": True}, {"option_no": 1.5}, {"option_no": 0}, {"option_no": 1, "rationale": "short"}):
            with self.assertRaises(OprsError, msg=bad): self.svc.op_decide(ORG, a["id"], {"rationale": "A proper rationale here", **bad}, U4)
        with self.assertRaises(OprsNotFoundError): self.svc.op_decide(ORG, a["id"], {"option_no": 9, "rationale": "A proper rationale here"}, U4)
        r = self.svc.op_decide(ORG, a["id"], {"option_no": 2, "rationale": "Highest value over the period"}, U4); self.assertEqual((r["decision"]["option_name"], r["decision"]["by"], r["decision_flag"]), ("Lease", U4, False))
        with self.assertRaises(OprsStateError): self.svc.op_decide(ORG, a["id"], {"option_no": 1, "rationale": "Changing my mind later"}, U3)

    def test_choosing_a_lower_npv_is_flagged_not_blocked(self):
        a = self.approved(); r = self.svc.op_decide(ORG, a["id"], {"option_no": 1, "rationale": "Cash is short this year"}, U4)
        self.assertTrue(r["decision_flag"]); self.assertIn("DECISION_NOT_HIGHEST_NPV", [x["kind"] for x in self.svc.op_overview(ORG)["attention"]])

    def test_a_removed_option_cannot_be_chosen(self):
        a = self.ready(); a = self.svc.op_remove_option(ORG, a["id"], 2, "Leasing is not on offer", U1); a = self.opt(a, name="Rent", upfront_cost="5", flows=["3", "3"])
        a = self.svc.op_submit(ORG, a["id"], {}, U1); a = self.svc.op_approve(ORG, a["id"], {}, U3)
        with self.assertRaises(OprsNotFoundError): self.svc.op_decide(ORG, a["id"], {"option_no": 2, "rationale": "A proper rationale here"}, U4)


class Overview(Base):
    def test_counts_and_attention(self):
        self.an(); s = self.submitted(); r = self.submitted(); self.svc.op_return(ORG, r["id"], "Please add the lease quotes", U3); ap = self.approved(); self.approved(); self.svc.op_decide(ORG, ap["id"], {"option_no": 2, "rationale": "Highest value over the period"}, U4)
        o = self.svc.op_overview(ORG); self.assertEqual(o["counts"], {"draft": 1, "submitted": 1, "approved": 2, "returned": 1, "withdrawn": 0})
        kinds = {x["kind"]: x["count"] for x in o["attention"]}; self.assertEqual(kinds, {"ANALYSES_TO_REVIEW": 1, "ANALYSES_RETURNED": 1, "DECISIONS_NEEDED": 1}); self.assertEqual((o["decisions_recorded"], o["approved_by_currency"]), (1, [{"currency": "NGN", "analyses": 2}]))

    def test_empty_and_currencies_kept_apart(self):
        o = self.svc.op_overview(ORG); self.assertEqual((o["attention"], o["approved_by_currency"]), ([], []))
        a = self.an(currency="USD"); self.opt(a); a = self.opt(a, name="Two"); self.svc.op_submit(ORG, a["id"], {}, U1); self.svc.op_approve(ORG, a["id"], {}, U3); self.approved()
        self.assertEqual(self.svc.op_overview(ORG)["approved_by_currency"], [{"currency": "NGN", "analyses": 1}, {"currency": "USD", "analyses": 1}])


class Isolation(Base):
    def test_other_company(self):
        a = self.approved(); self.assertEqual(self.svc.op_list_analyses(OTHER), [])
        for f in (lambda: self.svc.op_get_analysis(OTHER, a["id"]), lambda: self.svc.op_decide(OTHER, a["id"], {"option_no": 1, "rationale": "A proper rationale here"}, U4), lambda: self.svc.op_add_option(OTHER, a["id"], {}, U1)):
            with self.assertRaises(OprsNotFoundError): f()
        self.assertEqual(self.svc.op_create_analysis(OTHER, dict(title="Other analysis", currency="NGN", discount_rate="5", purpose="An analysis of another company"), U1)["ref"], "OA-001")


class Audit(Base):
    def test_every_write_logged_without_content(self):
        a = self.ready(); self.svc.op_remove_option(ORG, a["id"], 2, "Leasing is not on offer", U1); self.opt(a, name="Rent kit", upfront_cost="777", flows=["333", "444"]); self.svc.op_submit(ORG, a["id"], {"note": "Please check the figures"}, U1)
        self.svc.op_return(ORG, a["id"], "Please add the lease quotes", U3); self.svc.op_submit(ORG, a["id"], {}, U2); self.svc.op_approve(ORG, a["id"], {"note": "Quotes are attached"}, U3); self.svc.op_decide(ORG, a["id"], {"option_no": 1, "rationale": "Highest value over the period"}, U4)
        w = self.ready(); self.svc.op_withdraw(ORG, w["id"], "No longer needed at all", U1)
        acts = [x[0] for x in self.events]
        for x in ("OPRS_ANALYSIS_CREATED", "OPRS_OPTION_ADDED", "OPRS_OPTION_REMOVED", "OPRS_ANALYSIS_SUBMITTED", "OPRS_ANALYSIS_RETURNED", "OPRS_ANALYSIS_APPROVED", "OPRS_DECISION_RECORDED", "OPRS_ANALYSIS_WITHDRAWN"): self.assertIn(x, acts)
        blob = " ".join(str(x) for x in self.events)
        for secret in ("delivery fleet", "vans", "Rent kit", "777", "333", "Leasing is not", "lease quotes", "Quotes are attached", "Highest value", "check the figures", "No longer needed"): self.assertNotIn(secret, blob)

    def test_failed_actions_are_not_logged(self):
        with self.assertRaises(OprsError): self.an(title="ab")
        a = self.an(); n = len(self.events)
        with self.assertRaises(OprsError): self.opt(a, upfront_cost="0")
        with self.assertRaises(OprsStateError): self.svc.op_submit(ORG, a["id"], {}, U1)
        self.assertEqual(len(self.events), n)


class Permissions(unittest.TestCase):
    def test_roles(self):
        has = lambda r, p: p in ROLE_PERMISSIONS[r]
        for r in (Role.OWNER, Role.ADMINISTRATOR, Role.MANAGER, Role.AUDITOR): self.assertTrue(has(r, OPR_PREPARE), r)
        for r in (Role.OWNER, Role.APPROVER, Role.MANAGER): self.assertTrue(has(r, OPR_APPROVE), r)
        for r in (Role.ACCOUNTANT, Role.REVIEWER, Role.EXTERNAL_AUDITOR, Role.READ_ONLY, Role.DONOR, Role.REGULATOR, Role.INVESTOR_REVIEWER): self.assertFalse(has(r, OPR_PREPARE) or has(r, OPR_APPROVE), r)

    def test_anyone_who_can_prepare_or_approve_can_view(self):
        for r, perms in ROLE_PERMISSIONS.items():
            if OPR_PREPARE in perms or OPR_APPROVE in perms: self.assertIn(AUDIT_READ, perms, r)


class RouterGuards(unittest.TestCase):
    SRC = os.path.join(os.path.dirname(__file__), "..", "src", "asavexa", "api", "routers", "oprs.py")

    def test_every_write_has_the_right_guard(self):
        tree = ast.parse(open(self.SRC).read()); named = {"_prepare": "OPR_PREPARE", "_approve": "OPR_APPROVE"}; g = {}
        for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.decorator_list]:
            verbs, guards = set(), set()
            for dec in fn.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute): verbs.add(dec.func.attr)
                for kw in getattr(dec, "keywords", []):
                    if kw.arg == "dependencies": guards |= {named[e.id] for e in kw.value.elts if isinstance(e, ast.Name) and e.id in named}
            g[fn.name] = (verbs, guards)
        approve = {"approve_analysis", "return_analysis", "record_decision"}; prepare = {"add_analysis", "add_option", "remove_option", "submit_analysis", "withdraw_analysis"}
        for n in approve: self.assertEqual(g[n][1], {"OPR_APPROVE"}, n)
        for n in prepare: self.assertEqual(g[n][1], {"OPR_PREPARE"}, n)
        for n, (verbs, guards) in g.items():
            if verbs == {"get"}: self.assertEqual(guards, set(), n)
            else: self.assertIn(n, approve | prepare, f"{n} writes but has no operations research guard")
        src = open(self.SRC).read(); self.assertIn("dependencies=[Depends(require_permission(AUDIT_READ))]", src); self.assertNotIn("org_id", src)


if __name__ == "__main__":
    unittest.main()
