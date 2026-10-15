"""Insurance and claims: policies, claims, outcomes decided by a different person, receipts, setting, isolation, audit, permissions."""
import ast
import os
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from fractions import Fraction

from analysis_fixture import ORG, OTHER, World
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.permissions import AUDIT_READ, INS_APPROVE, INS_PREPARE, ROLE_PERMISSIONS
from asavexa.insurance.errors import InsuranceError, InsuranceForbiddenError, InsuranceNotFoundError, InsuranceStateError
from asavexa.insurance.service import InsuranceService, refnum

U1, U2, U3, U4 = "user-1", "user-2", "user-3", "user-4"   # U1 and U2 prepare, U3 and U4 approve
NOTE = "Insurer confirmed this by letter"


class Clock:
    def __init__(self): self.d = date(2026, 3, 10)
    def __call__(self): return datetime(self.d.year, self.d.month, self.d.day, 9, tzinfo=timezone.utc)


class Base(unittest.TestCase):
    def setUp(self):
        self.w = World(); self.clock = Clock(); self.events = []
        self.svc = InsuranceService(self.w.store, None, log=lambda *a: self.events.append(a), now=self.clock)

    def pol(self, actor=U1, **kw):
        d = dict(insurer="Leadway Assurance", policy_number="PL-1001", cover_type="PROPERTY", covers="Warehouse and stock", currency="NGN", sum_insured="1000000", premium="25000.50", excess="5000", start_date="2026-01-01", end_date="2026-12-31"); d.update(kw)
        return self.svc.ic_add_policy(ORG, d, actor)

    def claim(self, p, actor=U1, **kw):
        d = dict(loss_date="2026-02-20", reported_date="2026-02-21", description="Water damage to stock in warehouse", claimed_amount="200000.00", claim_number="CN-77"); d.update(kw)
        return self.svc.ic_add_claim(ORG, p["id"], d, actor)

    def settle(self, c, amount="150000.25", proposer=U1, decider=U3):
        c = self.svc.ic_propose_outcome(ORG, c["id"], {"outcome": "SETTLE", "amount": amount, "note": NOTE}, proposer)
        return self.svc.ic_approve_outcome(ORG, c["id"], 1, {}, decider)

    def receipt(self, c, amount, ref="PAY-1", on="2026-03-10", actor=U1): return self.svc.ic_record_receipt(ORG, c["id"], {"amount": amount, "received_on": on, "reference": ref}, actor)


class Policies(Base):
    def test_add_and_list(self):
        p = self.pol()
        self.assertEqual((p["ref"], p["status"], p["sum_insured"], p["premium"], p["excess"]), ("IP-001", "ACTIVE", "1000000.00", "25000.50", "5000.00"))
        self.assertEqual(self.pol(policy_number="PL-1002")["ref"], "IP-002")
        self.assertEqual([x["ref"] for x in self.svc.ic_list_policies(ORG)], ["IP-001", "IP-002"])

    def test_validation(self):
        for bad in ({"insurer": "x"}, {"policy_number": ""}, {"cover_type": "PIRATES"}, {"currency": "NG"}, {"currency": "N1A"}, {"sum_insured": "0"}, {"sum_insured": 1000.5}, {"sum_insured": "1,00"}, {"sum_insured": "１２３"}, {"premium": "-1"}, {"premium": "1.234"},
                    {"excess": "2000000"}, {"start_date": "2026-02-30"}, {"end_date": "2026-01-01"}, {"end_date": "2037-01-02"}, {"covers": "abc"}):
            with self.assertRaises(InsuranceError, msg=str(bad)): self.pol(**bad)
        self.assertEqual(self.pol(premium="0", excess="")["premium"], "0.00")
        self.assertEqual(self.svc.ic_list_policies(ORG)[0]["excess"], "0.00")

    def test_thousands_separator_accepted_only_when_right(self):
        self.assertEqual(self.pol(sum_insured="1,000,000")["sum_insured"], "1000000.00")
        with self.assertRaises(InsuranceError): self.pol(policy_number="PL-2", sum_insured="1,0000")

    def test_duplicate_active_policy_refused_but_cancelled_can_be_reused(self):
        p = self.pol()
        with self.assertRaises(InsuranceStateError): self.pol(insurer="leadway assurance", policy_number="pl-1001")
        self.svc.ic_cancel_policy(ORG, p["id"], "Replaced by a new policy", U3)
        self.assertEqual(self.pol()["ref"], "IP-002")

    def test_cancel(self):
        p = self.pol()
        with self.assertRaises(InsuranceError): self.svc.ic_cancel_policy(ORG, p["id"], "short", U3)
        r = self.svc.ic_cancel_policy(ORG, p["id"], "Replaced by a new policy", U3); self.assertEqual((r["status"], r["cancel_note"]), ("CANCELLED", "Replaced by a new policy"))
        with self.assertRaises(InsuranceStateError): self.svc.ic_cancel_policy(ORG, p["id"], "Cancelling again please", U3)
        with self.assertRaises(InsuranceStateError): self.claim(p)

    def test_cannot_cancel_with_open_claim(self):
        p = self.pol(); c = self.claim(p)
        with self.assertRaises(InsuranceStateError): self.svc.ic_cancel_policy(ORG, p["id"], "Trying to cancel now", U3)
        self.settle(c); self.svc.ic_cancel_policy(ORG, p["id"], "Settled claim does not block it", U3)

    def test_ending_soon_and_expired_flags(self):
        p = self.pol(start_date="2026-01-01", end_date="2026-04-01")      # 22 days from 10 March
        self.assertTrue(self.svc.ic_get_policy_record(ORG, p["id"])["ending_soon"])
        q = self.pol(policy_number="PL-2", start_date="2025-01-01", end_date="2026-03-01")
        v = self.svc.ic_get_policy_record(ORG, q["id"]); self.assertTrue(v["expired"]); self.assertFalse(v["ending_soon"])
        far = self.pol(policy_number="PL-3"); self.assertFalse(self.svc.ic_get_policy_record(ORG, far["id"])["ending_soon"])


class Claims(Base):
    def test_add(self):
        c = self.claim(self.pol())
        self.assertEqual((c["ref"], c["status"], c["currency"], c["claimed_amount"], c["received"], c["outstanding"]), ("CL-001", "OPEN", "NGN", "200000.00", "0.00", None))
        self.assertEqual(self.svc.ic_get_policy_record(ORG, c["policy_id"])["open_claims"], 1)

    def test_validation(self):
        p = self.pol()
        for bad in ({"loss_date": "2025-12-31"}, {"loss_date": "2027-01-01"}, {"loss_date": "2026-03-20", "reported_date": "2026-03-20"}, {"reported_date": "2026-02-19"}, {"reported_date": "2026-04-01"}, {"description": "short"},
                    {"claimed_amount": "0"}, {"claimed_amount": 5.5}, {"claimed_amount": "1000000.01"}, {"claim_number": "x"}):
            with self.assertRaises(InsuranceError, msg=str(bad)): self.claim(p, **bad)
        self.assertEqual(self.claim(p, claimed_amount="1000000")["claimed_amount"], "1000000.00")
        self.assertIsNone(self.claim(p, claim_number="")["claim_number"])

    def test_loss_must_fall_in_policy_period(self):
        p = self.pol(start_date="2026-03-01", end_date="2026-12-31")
        with self.assertRaises(InsuranceError): self.claim(p, loss_date="2026-02-28", reported_date="2026-03-02")
        self.assertTrue(self.claim(p, loss_date="2026-03-01", reported_date="2026-03-02"))

    def test_numbering_and_sorting_numerically(self):
        p = self.pol(); [self.claim(p) for _ in range(3)]
        self.assertEqual([c["ref"] for c in self.svc.ic_list_claims(ORG)], ["CL-001", "CL-002", "CL-003"])
        self.assertEqual(refnum({"ref": "CL-010"}), 10)

    def test_failed_claim_does_not_use_a_number(self):
        p = self.pol()
        with self.assertRaises(InsuranceError): self.claim(p, claimed_amount="0")
        self.assertEqual(self.claim(p)["ref"], "CL-001")


class Outcomes(Base):
    def test_settle_flow(self):
        c = self.claim(self.pol())
        c = self.svc.ic_propose_outcome(ORG, c["id"], {"outcome": "SETTLE", "amount": "150000.25", "note": NOTE}, U1)
        self.assertEqual((c["status"], c["pending"], c["settled_amount"]), ("PROPOSED", 1, None))
        c = self.svc.ic_approve_outcome(ORG, c["id"], 1, {"note": "Matches the letter on file"}, U3)
        self.assertEqual((c["status"], c["outcome"], c["settled_amount"], c["outstanding"], c["decided_by"]), ("SETTLED", "SETTLE", "150000.25", "150000.25", U3))

    def test_decline_flow(self):
        c = self.claim(self.pol()); c = self.svc.ic_propose_outcome(ORG, c["id"], {"outcome": "DECLINE", "note": "Insurer declined: excluded peril"}, U1)
        c = self.svc.ic_approve_outcome(ORG, c["id"], 1, {}, U3); self.assertEqual((c["status"], c["settled_amount"], c["outstanding"]), ("DECLINED", None, None))

    def test_two_person_rule_for_every_role(self):
        c = self.claim(self.pol()); c = self.svc.ic_propose_outcome(ORG, c["id"], {"outcome": "SETTLE", "amount": "100", "note": NOTE}, U3)   # the proposer is an approver-capable person
        with self.assertRaises(InsuranceForbiddenError): self.svc.ic_approve_outcome(ORG, c["id"], 1, {}, U3)
        with self.assertRaises(InsuranceForbiddenError): self.svc.ic_reject_outcome(ORG, c["id"], 1, "Rejecting my own proposal", U3)
        self.assertEqual(self.svc.ic_approve_outcome(ORG, c["id"], 1, {}, U4)["status"], "SETTLED")

    def test_validation(self):
        c = self.claim(self.pol())
        for bad in ({"outcome": "MAYBE", "note": NOTE}, {"outcome": "SETTLE", "note": NOTE}, {"outcome": "SETTLE", "amount": "0", "note": NOTE}, {"outcome": "SETTLE", "amount": "200000.01", "note": NOTE}, {"outcome": "SETTLE", "amount": 5.5, "note": NOTE},
                    {"outcome": "SETTLE", "amount": "5", "note": "short"}, {"outcome": "DECLINE", "amount": "5", "note": NOTE}):
            with self.assertRaises(InsuranceError, msg=str(bad)): self.svc.ic_propose_outcome(ORG, c["id"], bad, U1)
        self.assertEqual(self.svc.ic_get_claim(ORG, c["id"])["status"], "OPEN")

    def test_one_proposal_at_a_time_and_reject_reopens(self):
        c = self.claim(self.pol()); c = self.svc.ic_propose_outcome(ORG, c["id"], {"outcome": "SETTLE", "amount": "100", "note": NOTE}, U1)
        with self.assertRaises(InsuranceStateError): self.svc.ic_propose_outcome(ORG, c["id"], {"outcome": "SETTLE", "amount": "100", "note": NOTE}, U2)
        with self.assertRaises(InsuranceError): self.svc.ic_reject_outcome(ORG, c["id"], 1, "short", U3)
        c = self.svc.ic_reject_outcome(ORG, c["id"], 1, "The figure does not match the letter", U3); self.assertEqual((c["status"], c["pending"]), ("OPEN", 0))
        c = self.svc.ic_propose_outcome(ORG, c["id"], {"outcome": "SETTLE", "amount": "120", "note": NOTE}, U2)
        c = self.svc.ic_approve_outcome(ORG, c["id"], 2, {}, U3); self.assertEqual(c["settled_amount"], "120.00")

    def test_a_decided_proposal_cannot_be_decided_again(self):
        c = self.settle(self.claim(self.pol()))
        with self.assertRaises(InsuranceStateError): self.svc.ic_approve_outcome(ORG, c["id"], 1, {}, U4)
        with self.assertRaises(InsuranceStateError): self.svc.ic_reject_outcome(ORG, c["id"], 1, "Trying to reject it later", U4)
        with self.assertRaises(InsuranceStateError): self.svc.ic_propose_outcome(ORG, c["id"], {"outcome": "SETTLE", "amount": "1", "note": NOTE}, U1)
        with self.assertRaises(InsuranceNotFoundError): self.svc.ic_approve_outcome(ORG, c["id"], 9, {}, U4)

    def test_at_most_five_proposals(self):
        c = self.claim(self.pol())
        for i in range(5):
            self.svc.ic_propose_outcome(ORG, c["id"], {"outcome": "SETTLE", "amount": "10", "note": NOTE}, U1); self.svc.ic_reject_outcome(ORG, c["id"], i + 1, "Not right, please redo it", U3)
        with self.assertRaises(InsuranceStateError): self.svc.ic_propose_outcome(ORG, c["id"], {"outcome": "SETTLE", "amount": "10", "note": NOTE}, U1)


class Receipts(Base):
    def test_exact_arithmetic_against_an_independent_oracle(self):
        c = self.settle(self.claim(self.pol()), "150000.25")
        parts = ["50000.10", "40000.05", "0.10"]
        for i, a in enumerate(parts, 1): c = self.receipt(c, a, ref=f"PAY-{i}")
        want = Fraction(15000025, 100) - sum(Fraction(Decimal(a)) for a in parts)
        self.assertEqual(Fraction(Decimal(c["outstanding"])), want); self.assertEqual(c["received"], "90000.25"); self.assertEqual(c["outstanding"], "60000.00")

    def test_cannot_exceed_settled_and_exact_total_allowed(self):
        c = self.settle(self.claim(self.pol()), "100.00"); c = self.receipt(c, "99.99", ref="A1")
        with self.assertRaises(InsuranceError): self.receipt(c, "0.02", ref="A2")
        c = self.receipt(c, "0.01", ref="A2"); self.assertEqual(c["outstanding"], "0.00")
        with self.assertRaises(InsuranceError): self.receipt(c, "0.01", ref="A3")

    def test_validation(self):
        c = self.settle(self.claim(self.pol()), "100.00")
        for bad in ({"amount": "0"}, {"amount": 5.5}, {"amount": "1.234"}, {"received_on": "2026-04-01"}, {"received_on": "2026-02-01"}, {"received_on": "nope"}, {"reference": "x"}):
            d = dict(amount="10", received_on="2026-03-10", reference="PAY-1"); d.update(bad)
            with self.assertRaises(InsuranceError, msg=str(bad)): self.svc.ic_record_receipt(ORG, c["id"], d, U1)

    def test_duplicate_reference_refused(self):
        c = self.settle(self.claim(self.pol()), "100.00"); c = self.receipt(c, "10", ref="PAY-1")
        with self.assertRaises(InsuranceStateError): self.receipt(c, "10", ref="pay-1")

    def test_only_a_settled_claim_takes_money(self):
        p = self.pol(); c = self.claim(p)
        with self.assertRaises(InsuranceStateError): self.receipt(c, "10")
        d = self.svc.ic_propose_outcome(ORG, self.claim(p)["id"], {"outcome": "DECLINE", "note": NOTE}, U1); d = self.svc.ic_approve_outcome(ORG, d["id"], 1, {}, U3)
        with self.assertRaises(InsuranceStateError): self.receipt(d, "10")


class Setting(Base):
    def test_default_and_set(self):
        self.assertEqual(self.svc.ic_get_policy(ORG)["warning_days"], 60)
        self.assertEqual(self.svc.ic_set_policy(ORG, {"warning_days": 90}, U3)["warning_days"], 90)
        for bad in (6, 366, "x", 3.5, True, "-1"):
            with self.assertRaises(InsuranceError, msg=str(bad)): self.svc.ic_set_policy(ORG, {"warning_days": bad}, U3)
        self.assertEqual(self.svc.ic_get_policy(ORG)["warning_days"], 90)

    def test_window_changes_the_flag(self):
        p = self.pol(end_date="2026-06-30")        # 112 days away
        self.assertFalse(self.svc.ic_get_policy_record(ORG, p["id"])["ending_soon"])
        self.svc.ic_set_policy(ORG, {"warning_days": 120}, U3); self.assertTrue(self.svc.ic_get_policy_record(ORG, p["id"])["ending_soon"])


class Overview(Base):
    def test_totals_per_currency_and_attention(self):
        a = self.pol(); self.pol(policy_number="PL-2", currency="USD", sum_insured="5000", premium="100", excess="")
        self.pol(policy_number="PL-3", start_date="2025-01-01", end_date="2026-03-01"); self.pol(policy_number="PL-4", end_date="2026-04-15")
        c1 = self.settle(self.claim(a), "150000.25"); self.receipt(c1, "50000.10")
        self.claim(a)                                              # open
        c3 = self.claim(a); self.svc.ic_propose_outcome(ORG, c3["id"], {"outcome": "SETTLE", "amount": "1", "note": NOTE}, U1)
        o = self.svc.ic_overview(ORG); n = next(t for t in o["totals"] if t["currency"] == "NGN"); u = next(t for t in o["totals"] if t["currency"] == "USD")
        self.assertEqual((n["active_policies"], n["sum_insured"], n["premium"]), (3, "3000000.00", "75001.50"))
        self.assertEqual((n["open_claims"], n["claimed_open"], n["settled"], n["received"], n["outstanding"]), (2, "400000.00", "150000.25", "50000.10", "100000.15"))
        self.assertEqual((u["active_policies"], u["sum_insured"], u["open_claims"], u["settled"]), (1, "5000.00", 0, "0.00"))
        kinds = {x["kind"]: x["count"] for x in o["attention"]}
        self.assertEqual(kinds, {"OUTCOMES_TO_DECIDE": 1, "SETTLED_UNPAID": 1, "POLICIES_ENDING_SOON": 1, "POLICIES_EXPIRED": 1})
        self.assertEqual((o["counts"]["claims_open"], o["counts"]["claims_proposed"], o["counts"]["claims_settled"], o["counts"]["policies_active"]), (1, 1, 1, 4))

    def test_empty(self):
        o = self.svc.ic_overview(ORG); self.assertEqual((o["totals"], o["attention"]), ([], []))

    def test_cancelled_policy_leaves_the_active_totals_but_keeps_settled_money(self):
        p = self.pol(); c = self.settle(self.claim(p), "100.00"); self.receipt(c, "40.00"); self.svc.ic_cancel_policy(ORG, p["id"], "Replaced by a new policy", U3)
        t = self.svc.ic_overview(ORG)["totals"][0]; self.assertEqual((t["active_policies"], t["sum_insured"], t["settled"], t["received"], t["outstanding"]), (0, "0.00", "100.00", "40.00", "60.00"))


class Isolation(Base):
    def test_other_company(self):
        p = self.pol(); c = self.claim(p)
        self.assertEqual((self.svc.ic_list_policies(OTHER), self.svc.ic_list_claims(OTHER)), ([], []))
        self.assertEqual(self.svc.ic_overview(OTHER)["totals"], [])
        for f in (lambda: self.svc.ic_get_policy_record(OTHER, p["id"]), lambda: self.svc.ic_get_claim(OTHER, c["id"]), lambda: self.svc.ic_cancel_policy(OTHER, p["id"], "Cancelling from elsewhere", U3),
                  lambda: self.svc.ic_add_claim(OTHER, p["id"], {}, U1), lambda: self.svc.ic_propose_outcome(OTHER, c["id"], {}, U1), lambda: self.svc.ic_record_receipt(OTHER, c["id"], {}, U1)):
            with self.assertRaises(InsuranceNotFoundError): f()
        self.assertEqual(self.svc.ic_set_policy(OTHER, {"warning_days": 30}, U3)["warning_days"], 30); self.assertEqual(self.svc.ic_get_policy(ORG)["warning_days"], 60)

    def test_numbering_is_per_company(self):
        self.pol(); q = self.svc.ic_add_policy(OTHER, dict(insurer="Leadway Assurance", policy_number="PL-1001", cover_type="MOTOR", covers="Fleet of vans", currency="NGN", sum_insured="10", premium="1", start_date="2026-01-01", end_date="2026-12-31"), U1)
        self.assertEqual(q["ref"], "IP-001")


class Audit(Base):
    def test_every_write_logged_without_content(self):
        p = self.pol(); c = self.claim(p); self.svc.ic_propose_outcome(ORG, c["id"], {"outcome": "SETTLE", "amount": "12345.67", "note": NOTE}, U1)
        self.svc.ic_reject_outcome(ORG, c["id"], 1, "Figure disagrees with letter", U3); self.settle_second(c)
        self.svc.ic_set_policy(ORG, {"warning_days": 30}, U3); q = self.pol(policy_number="PL-9"); self.svc.ic_cancel_policy(ORG, q["id"], "Cancelled as the cover was replaced", U3)
        acts = [x[0] for x in self.events]
        for x in ("INSURANCE_POLICY_ADDED", "INSURANCE_POLICY_CANCELLED", "INSURANCE_CLAIM_ADDED", "INSURANCE_OUTCOME_PROPOSED", "INSURANCE_OUTCOME_APPROVED", "INSURANCE_OUTCOME_REJECTED", "INSURANCE_RECEIPT_RECORDED", "INSURANCE_SETTING_SET"): self.assertIn(x, acts)
        blob = " ".join(str(x) for x in self.events)
        for secret in ("Leadway", "PL-1001", "Warehouse", "Water damage", "12345", "25000", "200000", "CN-77", "Insurer confirmed", "disagrees", "PAY-77", "cover was replaced"): self.assertNotIn(secret, blob)

    def settle_second(self, c):
        self.svc.ic_propose_outcome(ORG, c["id"], {"outcome": "SETTLE", "amount": "500", "note": NOTE}, U1); self.svc.ic_approve_outcome(ORG, c["id"], 2, {}, U3)
        self.svc.ic_record_receipt(ORG, c["id"], {"amount": "100", "received_on": "2026-03-10", "reference": "PAY-77"}, U1)

    def test_failed_actions_are_not_logged(self):
        with self.assertRaises(InsuranceError): self.pol(insurer="x")
        p = self.pol(); c = self.claim(p); n = len(self.events)
        with self.assertRaises(InsuranceError): self.claim(p, claimed_amount="0")
        with self.assertRaises(InsuranceStateError): self.receipt(c, "10")
        with self.assertRaises(InsuranceError): self.svc.ic_cancel_policy(ORG, p["id"], "short", U3)
        with self.assertRaises(InsuranceStateError): self.svc.ic_cancel_policy(ORG, p["id"], "Cancelling with an open claim", U3)
        self.assertEqual(len(self.events), n)


class Permissions(unittest.TestCase):
    def test_roles(self):
        has = lambda r, p: p in ROLE_PERMISSIONS[r]
        for r in (Role.OWNER, Role.ADMINISTRATOR, Role.MANAGER, Role.AUDITOR): self.assertTrue(has(r, INS_PREPARE), r)
        for r in (Role.OWNER, Role.APPROVER, Role.MANAGER): self.assertTrue(has(r, INS_APPROVE), r)
        for r in (Role.ACCOUNTANT, Role.REVIEWER, Role.EXTERNAL_AUDITOR, Role.READ_ONLY, Role.DONOR, Role.REGULATOR, Role.INVESTOR_REVIEWER): self.assertFalse(has(r, INS_PREPARE) or has(r, INS_APPROVE), r)

    def test_anyone_who_can_prepare_or_approve_can_view(self):
        for r, perms in ROLE_PERMISSIONS.items():
            if INS_PREPARE in perms or INS_APPROVE in perms: self.assertIn(AUDIT_READ, perms, r)


class RouterGuards(unittest.TestCase):
    SRC = os.path.join(os.path.dirname(__file__), "..", "src", "asavexa", "api", "routers", "insurance.py")

    def test_every_write_has_the_right_guard(self):
        tree = ast.parse(open(self.SRC).read()); named = {"_prepare": "INS_PREPARE", "_approve": "INS_APPROVE"}; g = {}
        for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.decorator_list]:
            verbs, guards = set(), set()
            for dec in fn.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute): verbs.add(dec.func.attr)
                for kw in getattr(dec, "keywords", []):
                    if kw.arg == "dependencies": guards |= {named[e.id] for e in kw.value.elts if isinstance(e, ast.Name) and e.id in named}
            g[fn.name] = (verbs, guards)
        approve = {"set_setting", "cancel_policy", "approve_outcome", "reject_outcome"}
        prepare = {"add_policy", "add_claim", "propose_outcome", "record_receipt"}
        for n in approve: self.assertEqual(g[n][1], {"INS_APPROVE"}, n)
        for n in prepare: self.assertEqual(g[n][1], {"INS_PREPARE"}, n)
        for n, (verbs, guards) in g.items():
            if verbs == {"get"}: self.assertEqual(guards, set(), n)
            else: self.assertIn(n, approve | prepare, f"{n} writes but has no insurance guard")
        src = open(self.SRC).read(); self.assertIn("dependencies=[Depends(require_permission(AUDIT_READ))]", src); self.assertNotIn("org_id", src)


if __name__ == "__main__":
    unittest.main()
