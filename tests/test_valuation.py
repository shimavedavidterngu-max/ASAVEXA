"""Valuation: workpapers, methods worked out from typed inputs, weights and concluded value, different-person review, policy, isolation, audit, permissions."""
import ast
import os
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from fractions import Fraction

from analysis_fixture import ORG, OTHER, World
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.permissions import AUDIT_READ, ROLE_PERMISSIONS, VAL_APPROVE, VAL_PREPARE
from asavexa.valuation.errors import ValuationError, ValuationForbiddenError, ValuationNotFoundError, ValuationStateError
from asavexa.valuation.service import ValuationService, dcf_value, refnum

U1, U2, U3, U4 = "user-1", "user-2", "user-3", "user-4"   # U1 and U2 prepare, U3 and U4 approve
RATIONALE = "Weights favour the multiple because the peer set is close"


class Clock:
    def __init__(self): self.d = date(2026, 3, 10)
    def __call__(self): return datetime(self.d.year, self.d.month, self.d.day, 9, tzinfo=timezone.utc)


def oracle(flows, rate_pct, g_pct=None, net_debt=0):
    """An independent check: exact fractions, rounded half up once at the end."""
    r = Fraction(Decimal(str(rate_pct))) / 100; total = sum(Fraction(Decimal(str(cf))) / (1 + r) ** t for t, cf in enumerate(flows, start=1))
    if g_pct is not None:
        g = Fraction(Decimal(str(g_pct))) / 100; total += Fraction(Decimal(str(flows[-1]))) * (1 + g) / (r - g) / (1 + r) ** len(flows)
    total -= Fraction(Decimal(str(net_debt))); cents = total * 100
    n = cents.numerator * 2 + cents.denominator
    return Decimal(n // (2 * cents.denominator)) / 100


class Base(unittest.TestCase):
    def setUp(self):
        self.w = World(); self.clock = Clock(); self.events = []
        self.svc = ValuationService(self.w.store, None, log=lambda *a: self.events.append(a), now=self.clock)

    def case(self, actor=U1, **kw):
        d = dict(subject="Acme Ltd", subject_kind="BUSINESS", purpose="TRANSACTION", basis="MARKET_VALUE", valuation_date="2026-03-09", currency="NGN"); d.update(kw)
        return self.svc.vl_create_case(ORG, d, actor)

    def mult(self, c, weight=60, actor=U1, **kw):
        d = dict(kind="MULTIPLE", label="Peer EV/EBITDA", weight=weight, metric="1000.00", multiple="6.5", net_debt="500"); d.update(kw)
        return self.svc.vl_add_method(ORG, c["id"], d, actor)

    def dcf(self, c, weight=40, actor=U1, **kw):
        d = dict(kind="DCF", label="Five-year forecast", weight=weight, cash_flows=["100", "110", "121"], discount_rate="10"); d.update(kw)
        return self.svc.vl_add_method(ORG, c["id"], d, actor)

    def asset(self, c, weight=100, actor=U1, **kw):
        d = dict(kind="ASSET_BASED", label="Balance sheet", weight=weight, total_assets="5000", total_liabilities="1500"); d.update(kw)
        return self.svc.vl_add_method(ORG, c["id"], d, actor)

    def ready(self, actor=U1):
        c = self.case(actor); self.mult(c, 60, actor); c = self.dcf(c, 40, actor); return c

    def submit(self, c, actor=U1, rationale=RATIONALE): return self.svc.vl_submit(ORG, c["id"], {"rationale": rationale}, actor)


class Arithmetic(unittest.TestCase):
    def test_dcf_matches_an_independent_calculation(self):
        for flows, r, g, nd in [(["100", "100"], "10", None, "0"), (["100"], "10", "2", "0"), (["100", "110", "121"], "10", None, "0"), (["250.50", "0", "310.25", "400"], "12.5", "3.5", "100.10"),
                                (["1"] * 15, "7.25", "2", "0"), (["999999999999.99"], "0.01", None, "0.01"), (["12345.67", "23456.78"], "99.99", "50", "0")]:
            self.assertEqual(dcf_value([Decimal(x) for x in flows], Decimal(r), Decimal(g) if g else None, Decimal(nd)), oracle([Decimal(x) for x in flows], r, g, nd), (flows, r, g, nd))

    def test_known_values(self):
        self.assertEqual(dcf_value([Decimal("100"), Decimal("100")], Decimal("10"), None, Decimal("0")), Decimal("173.55"))
        self.assertEqual(dcf_value([Decimal("100")], Decimal("10"), Decimal("2"), Decimal("0")), Decimal("1250.00"))

    def test_refnum(self): self.assertEqual((refnum({"ref": "VL-012"}), refnum({})), (12, 0))


class Policy(Base):
    def test_default_set_bounds(self):
        self.assertEqual(self.svc.vl_get_policy(ORG)["review_days"], 365); self.assertEqual(self.svc.vl_set_policy(ORG, {"review_days": "90"}, U3)["review_days"], 90); self.assertEqual(self.svc.vl_get_policy(OTHER)["review_days"], 365)
        for v in (29, 1096, "x", True, -1, 4.5, ""):
            with self.assertRaises(ValuationError, msg=str(v)): self.svc.vl_set_policy(ORG, {"review_days": v}, U3)


class Cases(Base):
    def test_create_and_validation(self):
        c = self.case(); self.assertEqual((c["ref"], c["status"], c["currency"], c["active_methods"], c["weight_total"], c["concluded_value"], c["low"]), ("VL-001", "DRAFT", "NGN", 0, 0, None, None)); self.assertEqual(self.case().get("ref"), "VL-002")
        for bad in (dict(subject="ab"), dict(subject_kind="CAR"), dict(purpose="FUN"), dict(basis="GUESS"), dict(valuation_date="2026-02-30"), dict(valuation_date="20260309"), dict(valuation_date="2026-04-30"), dict(currency="NG"), dict(currency="N1A")):
            with self.assertRaises(ValuationError, msg=str(bad)): self.case(**bad)
        self.assertEqual(self.case(valuation_date="2020-01-31")["valuation_date"], "2020-01-31")   # a valuation date in the past is normal

    def test_withdraw(self):
        c = self.mult(self.case())
        with self.assertRaises(ValuationError): self.svc.vl_withdraw_case(ORG, c["id"], "short", U1)
        w = self.svc.vl_withdraw_case(ORG, c["id"], "Opened by mistake for the wrong company", U1); self.assertEqual(w["status"], "WITHDRAWN")
        for fn in (lambda: self.mult(c), lambda: self.submit(c), lambda: self.svc.vl_withdraw_case(ORG, c["id"], "Withdrawing a second time here", U1)):
            with self.assertRaises(ValuationStateError): fn()


class Methods(Base):
    def test_multiple_exact(self):
        c = self.mult(self.case()); m = c["methods"][0]; self.assertEqual((m["result"], m["weight"], m["status"], m["inputs"]), ("6000.00", 60, "ACTIVE", {"metric": "1000.00", "multiple": "6.5", "net_debt": "500.00"}))
        c = self.mult(c, 0, metric="1,234.56", multiple="3.3333", net_debt=""); self.assertEqual(c["methods"][1]["result"], "4115.16"); self.assertEqual(c["methods"][1]["inputs"]["net_debt"], "0.00")   # 1234.56 x 3.3333 = 4115.158848, rounded once

    def test_dcf_exact_and_stored_inputs(self):
        c = self.dcf(self.case()); m = c["methods"][0]; self.assertEqual(m["result"], "272.73"); self.assertEqual((m["inputs"]["cash_flows"], m["inputs"]["discount_rate"], m["inputs"]["terminal_growth"]), (["100.00", "110.00", "121.00"], "10.00", None))
        c = self.dcf(c, 0, cash_flows=["100"], discount_rate="10", terminal_growth="2"); self.assertEqual(c["methods"][1]["result"], "1250.00")
        c = self.dcf(c, 0, cash_flows=["50", "0", "75"], discount_rate="8.25", terminal_growth="1.5", net_debt="10"); self.assertEqual(c["methods"][2]["result"], str(oracle([50, 0, 75], "8.25", "1.5", "10")))


    def test_asset_based_zero_liabilities(self): self.assertEqual(self.asset(self.case(), total_liabilities="0")["methods"][0]["result"], "5000.00")

    def test_validation(self):
        c = self.case()
        bad_multiple = [dict(metric="0"), dict(metric="-1"), dict(metric="x"), dict(metric=1.5), dict(metric=None), dict(metric="1.234"), dict(metric="０１"), dict(metric="1,0,0"), dict(multiple="0"), dict(multiple="1.23456"), dict(multiple=2.5), dict(multiple="1e3"),
                        dict(net_debt="-1"), dict(net_debt="1.234"), dict(net_debt=True), dict(net_debt="9999999"), dict(weight=101), dict(weight=-1), dict(weight="x"), dict(weight=1.5), dict(weight=True), dict(weight=None), dict(label="x"), dict(label=""), dict(kind="MAGIC"), dict(kind=None)]
        for bad in bad_multiple:
            with self.assertRaises(ValuationError, msg=str(bad)): self.mult(c, **bad)
        for bad in (dict(cash_flows=[]), dict(cash_flows="100"), dict(cash_flows=None), dict(cash_flows=["0", "0"]), dict(cash_flows=["x"]), dict(cash_flows=[1.5]), dict(cash_flows=["-5", "100"]), dict(cash_flows=["1"] * 16), dict(cash_flows=[None]),
                    dict(discount_rate="0"), dict(discount_rate="100.01"), dict(discount_rate="x"), dict(discount_rate=10.5), dict(discount_rate=None), dict(discount_rate="1.234"), dict(terminal_growth="10"), dict(terminal_growth="11"), dict(terminal_growth="-1"), dict(terminal_growth="x"),
                    dict(net_debt="1000000")):
            with self.assertRaises(ValuationError, msg=str(bad)): self.dcf(c, **bad)
        for bad in (dict(total_assets="0"), dict(total_assets="x"), dict(total_liabilities="5000"), dict(total_liabilities="6000"), dict(total_liabilities="-1"), dict(total_assets=None)):
            with self.assertRaises(ValuationError, msg=str(bad)): self.asset(c, **bad)
        self.assertEqual(self.svc.vl_get_case(ORG, c["id"])["methods"], [])

    def test_a_zero_or_negative_result_is_refused(self):
        with self.assertRaises(ValuationError): self.mult(self.case(), metric="100", multiple="1", net_debt="100")
        with self.assertRaises(ValuationError): self.mult(self.case(), metric="100", multiple="1", net_debt="500")

    def test_at_most_five_active_and_remove(self):
        c = self.case()
        for _ in range(5): c = self.mult(c, 20)
        with self.assertRaises(ValuationStateError): self.mult(c, 20)
        with self.assertRaises(ValuationError): self.svc.vl_remove_method(ORG, c["id"], 2, "x", U1)
        c = self.svc.vl_remove_method(ORG, c["id"], 2, "Not comparable", U1); self.assertEqual((c["active_methods"], c["weight_total"], c["methods"][1]["status"], c["methods"][1]["removed_note"]), (4, 80, "REMOVED", "Not comparable"))
        with self.assertRaises(ValuationStateError): self.svc.vl_remove_method(ORG, c["id"], 2, "Removing it again", U1)
        with self.assertRaises(ValuationNotFoundError): self.svc.vl_remove_method(ORG, c["id"], 9, "Removing a missing one", U1)
        with self.assertRaises(ValuationError): self.svc.vl_remove_method(ORG, c["id"], "x", "Removing a bad number", U1)
        c = self.mult(c, 20); self.assertEqual((c["active_methods"], len(c["methods"]), c["methods"][-1]["no"]), (5, 6, 6))

    def test_sensitivity(self):
        c = self.dcf(self.case(), cash_flows=["100", "100"], discount_rate="10"); s = self.svc.vl_sensitivity(ORG, c["id"], 1)
        self.assertEqual([(r["discount_rate"], r["result"]) for r in s["rows"]], [("9.00", str(oracle([100, 100], "9"))), ("10.00", "173.55"), ("11.00", str(oracle([100, 100], "11")))])
        g = self.dcf(c, cash_flows=["100"], discount_rate="2.5", terminal_growth="2"); s = self.svc.vl_sensitivity(ORG, g["id"], 2); self.assertEqual([r["result"] is None for r in s["rows"]], [True, False, False])   # 1.5% is below the growth, so it is blank
        with self.assertRaises(ValuationStateError): self.svc.vl_sensitivity(ORG, self.mult(self.case())["id"], 1)
        with self.assertRaises(ValuationNotFoundError): self.svc.vl_sensitivity(ORG, c["id"], 5)
        with self.assertRaises(ValuationNotFoundError): self.svc.vl_sensitivity(OTHER, c["id"], 1)


class Submit(Base):
    def test_concluded_value_and_range(self):
        c = self.submit(self.ready()); self.assertEqual((c["status"], c["concluded_value"], c["low"], c["high"], c["weight_total"], c["submitted_by"], c["rationale"]), ("SUBMITTED", "3709.09", "272.73", "6000.00", 100, U1, RATIONALE))   # 6000.00 x 60% + 272.73 x 40%

    def test_rounding_happens_once(self):
        c = self.case(); c = self.mult(c, 33, metric="100", multiple="3.3333", net_debt="0"); c = self.mult(c, 33, metric="100", multiple="1.1111", net_debt="0"); c = self.mult(c, 34, metric="100", multiple="2.2222", net_debt="0")
        exp = (Decimal("333.33") * 33 + Decimal("111.11") * 33 + Decimal("222.22") * 34) / 100; self.assertEqual(self.submit(c)["concluded_value"], str(exp.quantize(Decimal("0.01"))))

    def test_rules(self):
        c = self.case()
        with self.assertRaises(ValuationStateError): self.submit(c)
        c = self.mult(c, 60)
        with self.assertRaises(ValuationStateError): self.submit(c)
        c = self.dcf(c, 41)
        with self.assertRaises(ValuationStateError): self.submit(c)
        c = self.svc.vl_remove_method(ORG, c["id"], 2, "Wrong weight entered", U1); c = self.dcf(c, 40)
        for bad in ("short", "", None):
            with self.assertRaises(ValuationError): self.submit(c, rationale=bad)
        self.assertEqual(self.submit(c)["status"], "SUBMITTED")
        for fn in (lambda: self.mult(c), lambda: self.submit(c), lambda: self.svc.vl_remove_method(ORG, c["id"], 1, "Removing while submitted", U1), lambda: self.svc.vl_withdraw_case(ORG, c["id"], "Withdrawing while submitted", U1)):
            with self.assertRaises(ValuationStateError): fn()

    def test_removed_methods_do_not_count(self):
        c = self.mult(self.case(), 100); c = self.mult(c, 50); c = self.svc.vl_remove_method(ORG, c["id"], 2, "Not comparable", U1); self.assertEqual(self.submit(c)["concluded_value"], "6000.00")


class Review(Base):
    def test_approve_by_a_different_person(self):
        c = self.submit(self.ready())
        with self.assertRaises(ValuationForbiddenError): self.svc.vl_approve_case(ORG, c["id"], {}, U1)
        with self.assertRaises(ValuationForbiddenError): self.svc.vl_return_case(ORG, c["id"], "Returning my own submission", U1)
        with self.assertRaises(ValuationError): self.svc.vl_approve_case(ORG, c["id"], {"note": "ok"}, U3)
        a = self.svc.vl_approve_case(ORG, c["id"], {}, U3); self.assertEqual((a["status"], a["decided_by"], a["decided_on"], a["concluded_value"]), ("APPROVED", U3, "2026-03-10", "3709.09"))
        for fn in (lambda: self.svc.vl_approve_case(ORG, c["id"], {}, U4), lambda: self.svc.vl_return_case(ORG, c["id"], "Returning an approved one", U4), lambda: self.mult(c), lambda: self.svc.vl_withdraw_case(ORG, c["id"], "Withdrawing an approved one", U1), lambda: self.submit(c)):
            with self.assertRaises(ValuationStateError): fn()

    def test_return_then_edit_and_resubmit(self):
        c = self.submit(self.ready())
        with self.assertRaises(ValuationError): self.svc.vl_return_case(ORG, c["id"], "short", U3)
        r = self.svc.vl_return_case(ORG, c["id"], "The multiple is not comparable", U3); self.assertEqual((r["status"], r["concluded_value"], r["decision_note"]), ("RETURNED", None, "The multiple is not comparable"))
        r = self.svc.vl_remove_method(ORG, c["id"], 1, "Replacing the multiple", U2); r = self.mult(r, 60, actor=U2, multiple="7"); self.assertEqual(r["methods"][-1]["result"], "6500.00")
        s = self.submit(r, actor=U2); self.assertEqual((s["status"], s["submitted_by"], s["concluded_value"], s["decision_note"]), ("SUBMITTED", U2, "4009.09", None))   # 6500 x 60% + 272.73 x 40%
        with self.assertRaises(ValuationForbiddenError): self.svc.vl_approve_case(ORG, c["id"], {}, U2)
        self.assertEqual(self.svc.vl_approve_case(ORG, c["id"], {"note": "Checked against the peer list"}, U1)["status"], "APPROVED")   # the earlier submitter may now approve

    def test_only_submitted_can_be_decided(self):
        c = self.ready()
        for fn in (lambda: self.svc.vl_approve_case(ORG, c["id"], {}, U3), lambda: self.svc.vl_return_case(ORG, c["id"], "Returning a draft one", U3)):
            with self.assertRaises(ValuationStateError): fn()

    def test_due_for_review_follows_the_setting(self):
        c = self.svc.vl_approve_case(ORG, self.submit(self.ready())["id"], {}, U3); self.assertFalse(c["due_for_review"])
        self.clock.d = date(2027, 3, 11); self.assertTrue(self.svc.vl_get_case(ORG, c["id"])["due_for_review"])
        self.svc.vl_set_policy(ORG, {"review_days": 800}, U3); self.assertFalse(self.svc.vl_get_case(ORG, c["id"])["due_for_review"])
        self.assertFalse(self.svc.vl_get_case(ORG, self.case()["id"])["due_for_review"])


class Overview(Base):
    def test_attention_and_totals(self):
        a = self.svc.vl_approve_case(ORG, self.submit(self.ready())["id"], {}, U3); b = self.submit(self.ready()); c = self.submit(self.ready()); self.svc.vl_return_case(ORG, c["id"], "The weights need another look", U3)
        d = self.case(currency="USD"); self.mult(d, 100); e = self.case(); self.svc.vl_withdraw_case(ORG, e["id"], "Opened by mistake today", U1)
        o = self.svc.vl_overview(ORG); self.assertEqual({x["kind"]: x["count"] for x in o["attention"]}, {"CASES_TO_REVIEW": 1, "CASES_RETURNED": 1})
        t = {x["currency"]: x for x in o["totals"]}; self.assertEqual((t["NGN"]["approved"], t["NGN"]["waiting"], t["NGN"]["in_progress"]), (1, 1, 1)); self.assertEqual((t["USD"]["approved"], t["USD"]["in_progress"]), (0, 1))
        self.assertEqual(o["counts"], {"DRAFT": 1, "SUBMITTED": 1, "APPROVED": 1, "RETURNED": 1, "WITHDRAWN": 1})
        self.clock.d = date(2027, 3, 11); self.assertIn("DUE_FOR_REVIEW", {x["kind"] for x in self.svc.vl_overview(ORG)["attention"]})

    def test_empty(self):
        o = self.svc.vl_overview(OTHER); self.assertEqual((o["attention"], o["totals"]), ([], [])); self.assertIn("DCF", self.svc.vl_options(ORG)["method_kinds"]); self.assertTrue(o["limitations"])


class Isolation(Base):
    def test_other_company_sees_nothing_and_cannot_touch(self):
        c = self.submit(self.ready()); self.assertEqual(self.svc.vl_list_cases(OTHER), [])
        for fn in (lambda: self.svc.vl_get_case(OTHER, c["id"]), lambda: self.svc.vl_add_method(OTHER, c["id"], {}, U1), lambda: self.svc.vl_submit(OTHER, c["id"], {}, U1), lambda: self.svc.vl_approve_case(OTHER, c["id"], {}, U3),
                   lambda: self.svc.vl_return_case(OTHER, c["id"], "Returning from outside the company", U3), lambda: self.svc.vl_remove_method(OTHER, c["id"], 1, "Removing from outside", U1), lambda: self.svc.vl_withdraw_case(OTHER, c["id"], "Withdrawing from outside", U1)):
            with self.assertRaises(ValuationNotFoundError): fn()


class Audit(Base):
    def test_every_write_logged_without_content(self):
        c = self.ready(); self.svc.vl_remove_method(ORG, c["id"], 2, "Dropping this forecast for now", U1); self.dcf(c, 40); self.svc.vl_set_policy(ORG, {"review_days": 100}, U3)
        self.submit(c); self.svc.vl_return_case(ORG, c["id"], "Rationale needs more detail here", U3); self.submit(c, U2, "Second rationale with enough detail"); self.svc.vl_approve_case(ORG, c["id"], {"note": "Approved after checking"}, U3)
        w = self.case(); self.svc.vl_withdraw_case(ORG, w["id"], "Opened by mistake today", U1)
        acts = [x[0] for x in self.events]
        for x in ("VALUATION_CASE_CREATED", "VALUATION_METHOD_ADDED", "VALUATION_METHOD_REMOVED", "VALUATION_CASE_SUBMITTED", "VALUATION_CASE_APPROVED", "VALUATION_CASE_RETURNED", "VALUATION_CASE_WITHDRAWN", "VALUATION_POLICY_SET"): self.assertIn(x, acts)
        blob = " ".join(str(x) for x in self.events)
        for secret in ("Acme", "Peer EV", "6000", "3709", "1000.00", "Weights favour", "Dropping this", "Approved after"): self.assertNotIn(secret, blob)

    def test_failed_actions_are_not_logged(self):
        with self.assertRaises(ValuationError): self.case(subject="ab")
        c = self.case(); n = len(self.events)
        with self.assertRaises(ValuationError): self.mult(c, metric="0")
        with self.assertRaises(ValuationStateError): self.submit(c)
        self.assertEqual(len(self.events), n)


class Permissions(unittest.TestCase):
    def test_roles(self):
        has = lambda r, p: p in ROLE_PERMISSIONS[r]
        for r in (Role.OWNER, Role.ADMINISTRATOR, Role.MANAGER, Role.AUDITOR): self.assertTrue(has(r, VAL_PREPARE), r)
        for r in (Role.OWNER, Role.APPROVER, Role.MANAGER): self.assertTrue(has(r, VAL_APPROVE), r)
        for r in (Role.ACCOUNTANT, Role.REVIEWER, Role.EXTERNAL_AUDITOR, Role.READ_ONLY, Role.DONOR, Role.REGULATOR, Role.INVESTOR_REVIEWER): self.assertFalse(has(r, VAL_PREPARE) or has(r, VAL_APPROVE), r)

    def test_anyone_who_can_prepare_or_approve_can_view(self):
        for r, perms in ROLE_PERMISSIONS.items():
            if VAL_PREPARE in perms or VAL_APPROVE in perms: self.assertIn(AUDIT_READ, perms, r)


class RouterGuards(unittest.TestCase):
    SRC = os.path.join(os.path.dirname(__file__), "..", "src", "asavexa", "api", "routers", "valuation.py")

    def test_every_write_has_the_right_guard(self):
        tree = ast.parse(open(self.SRC).read()); named = {"_prepare": "VAL_PREPARE", "_approve": "VAL_APPROVE"}; g = {}
        for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.decorator_list]:
            verbs, guards = set(), set()
            for dec in fn.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute): verbs.add(dec.func.attr)
                for kw in getattr(dec, "keywords", []):
                    if kw.arg == "dependencies": guards |= {named[e.id] for e in kw.value.elts if isinstance(e, ast.Name) and e.id in named}
            g[fn.name] = (verbs, guards)
        approve = {"set_policy", "approve", "return_case"}
        prepare = {"create_case", "add_method", "remove_method", "submit", "withdraw"}
        for n in approve: self.assertEqual(g[n][1], {"VAL_APPROVE"}, n)
        for n in prepare: self.assertEqual(g[n][1], {"VAL_PREPARE"}, n)
        for n, (verbs, guards) in g.items():
            if verbs == {"get"}: self.assertEqual(guards, set(), n)
            else: self.assertIn(n, approve | prepare, f"{n} writes but has no valuation guard")
        src = open(self.SRC).read(); self.assertIn("dependencies=[Depends(require_permission(AUDIT_READ))]", src); self.assertNotIn("org_id", src)


if __name__ == "__main__":
    unittest.main()
