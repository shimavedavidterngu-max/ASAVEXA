"""Insolvency: claims, realisations and costs decided by different people, and an exact class-by-class distribution in which every cent is allocated (checked against an independent calculation)."""
import ast
import os
import random
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from fractions import Fraction

from analysis_fixture import ORG, OTHER, World
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.permissions import AUDIT_READ, ISV_APPROVE, ISV_PREPARE, ROLE_PERMISSIONS
from asavexa.insolvency.errors import InsolvencyError, InsolvencyForbiddenError, InsolvencyNotFoundError, InsolvencyStateError
from asavexa.insolvency.service import InsolvencyService, split_cents

U1, U2, U3, U4 = "user-1", "user-2", "user-3", "user-4"   # U1 and U2 prepare, U3 and U4 approve


class Clock:
    def __init__(self): self.d = date(2026, 3, 31)
    def __call__(self): return datetime(self.d.year, self.d.month, self.d.day, 9, tzinfo=timezone.utc)


def indep_shares(total_cents, weights):
    """Largest remainder, written differently from the service: integer maths on remainders."""
    tw = sum(weights)
    if not tw or not total_cents: return [0] * len(weights)
    q = [total_cents * w // tw for w in weights]; rem = [total_cents * w % tw for w in weights]; need = total_cents - sum(q)
    for i in sorted(range(len(weights)), key=lambda i: (-rem[i], i))[:need]: q[i] += 1
    return q


class Base(unittest.TestCase):
    def setUp(self):
        self.w = World(); self.clock = Clock(); self.events = []
        self.svc = InsolvencyService(self.w.store, None, log=lambda *a: self.events.append(a), now=self.clock)

    def case(self, actor=U1, **kw):
        d = dict(title="Acme Textiles liquidation", currency="ngn", description="Estate of a closed textile company"); d.update(kw); return self.svc.isv_add_case(ORG, d, actor)

    def opened(self, actor=U1, approver=U3, **kw):
        c = self.case(actor, **kw); return self.svc.isv_approve_case(ORG, c["id"], {}, approver)

    def claim(self, c, ref="SUP-1", cls="UNSECURED", amt="1000", actor=U1, **kw):
        d = dict(creditor_ref=ref, claim_class=cls, amount=amt, basis="Unpaid invoices for fabric supplied"); d.update(kw); return self.svc.isv_add_claim(ORG, c["id"], d, actor)

    def admit(self, c, no, amt, actor=U3):
        return self.svc.isv_admit_claim(ORG, c["id"], no, {"amount": amt}, actor)

    def entry(self, c, kind="REALISATION", amt="1000", actor=U1, **kw):
        d = dict(entry_type=kind, description="Sale of the machinery", amount=amt, entry_date="2026-03-30"); d.update(kw); return self.svc.isv_add_entry(ORG, c["id"], d, actor)

    def confirm(self, c, no, actor=U3): return self.svc.isv_confirm_entry(ORG, c["id"], no, {}, actor)

    def example(self, **kw):
        c = self.opened(**kw)
        for ref, cls, amt in (("BANK-1", "SECURED", "500000.00"), ("TAX-1", "PREFERENTIAL", "100000.00"), ("SUP-1", "UNSECURED", "300000.00"), ("SUP-2", "UNSECURED", "200000.00"), ("SUP-3", "UNSECURED", "100000.01")): c = self.claim(c, ref, cls, amt)
        for no, adm in ((1, "500000.00"), (2, "80000.00"), (3, "300000.00"), (4, "200000.00"), (5, "100000.01")): c = self.admit(c, no, adm)
        c = self.entry(c, "REALISATION", "1000000.00"); c = self.confirm(c, 1); c = self.entry(c, "COST", "50000.00", description="Administration costs"); return self.confirm(c, 2)


class Split(unittest.TestCase):
    def test_every_cent_is_allocated(self):
        self.assertEqual(split_cents(100, [1, 1, 1]), [34, 33, 33]); self.assertEqual(split_cents(10, [3, 3, 4]), [3, 3, 4]); self.assertEqual(split_cents(1, [5, 5]), [1, 0]); self.assertEqual(split_cents(0, [1, 2]), [0, 0]); self.assertEqual(split_cents(5, [0, 0]), [0, 0])
        rnd = random.Random(7)
        for _ in range(300):
            ws = [rnd.randint(0, 10 ** rnd.randint(1, 9)) for _ in range(rnd.randint(1, 12))]; t = rnd.randint(0, 10 ** rnd.randint(1, 11)); got = split_cents(t, ws)
            self.assertEqual(got, indep_shares(t, ws)); 
            if sum(ws): self.assertEqual(sum(got), t); self.assertTrue(all(abs(g - Fraction(t * w, sum(ws))) < 1 for g, w in zip(got, ws)))

    def test_nobody_gets_more_than_owed_when_paying_less_than_the_total(self):
        rnd = random.Random(11)
        for _ in range(200):
            ws = [rnd.randint(1, 10 ** 6) for _ in range(rnd.randint(1, 8))]; t = rnd.randint(0, sum(ws)); got = split_cents(t, ws)
            self.assertEqual(sum(got), t); self.assertTrue(all(g <= w for g, w in zip(got, ws)), (t, ws, got))


class Waterfall(Base):
    def test_worked_example(self):
        c = self.example(); w = c["waterfall"]
        self.assertEqual((w["realisations"], w["costs"], w["available"], w["total_owed"], w["total_paid"], w["shortfall"], w["left_over"], w["costs_exceed"]), ("1000000.00", "50000.00", "950000.00", "1180000.01", "950000.00", "230000.01", "0.00", False))
        by = {k["claim_class"]: k for k in w["classes"]}
        self.assertEqual((by["SECURED"]["paid"], by["SECURED"]["recovery_pct"], by["PREFERENTIAL"]["paid"], by["PREFERENTIAL"]["owed"]), ("500000.00", "100.00", "80000.00", "80000.00"))
        un = by["UNSECURED"]; self.assertEqual((un["owed"], un["paid"], un["recovery_pct"]), ("600000.01", "370000.00", "61.67"))
        want = indep_shares(37000000, [30000000, 20000000, 10000001]); self.assertEqual([cents(x["dividend"]) for x in un["claims"]], want); self.assertEqual(sum(want), 37000000)
        self.assertEqual(by["SUBORDINATED"]["claims"], []); self.assertEqual(by["SUBORDINATED"]["owed"], "0.00")

    def test_order_follows_the_case(self):
        c = self.example(priority=["unsecured", "SECURED", "PREFERENTIAL", "SUBORDINATED"]); w = c["waterfall"]
        self.assertEqual([k["claim_class"] for k in w["classes"]], ["UNSECURED", "SECURED", "PREFERENTIAL", "SUBORDINATED"]); self.assertEqual([k["paid"] for k in w["classes"]], ["600000.01", "349999.99", "0.00", "0.00"])

    def test_costs_come_first_and_can_exceed(self):
        c = self.opened(); c = self.claim(c); c = self.admit(c, 1, "1000"); c = self.entry(c, amt="100"); c = self.confirm(c, 1); c = self.entry(c, "COST", "250", description="Administration costs"); c = self.confirm(c, 2)
        w = c["waterfall"]; self.assertEqual((w["available"], w["total_paid"], w["costs_exceed"]), ("0.00", "0.00", True)); self.assertIn("COSTS_EXCEED_REALISATIONS", [x["kind"] for x in self.svc.isv_overview(ORG)["attention"]])

    def test_only_confirmed_entries_and_admitted_claims_count(self):
        c = self.opened(); c = self.claim(c); c = self.claim(c, "SUP-2"); c = self.admit(c, 1, "400"); c = self.svc.isv_reject_claim(ORG, c["id"], 2, "No proof of debt was supplied", U3)
        c = self.entry(c, amt="1000"); self.assertEqual(c["waterfall"]["available"], "0.00")                 # proposed
        c = self.confirm(c, 1); c = self.entry(c, amt="5000"); c = self.svc.isv_reject_entry(ORG, c["id"], 2, "Entered against the wrong case", U3)
        w = c["waterfall"]; self.assertEqual((w["available"], w["total_owed"], w["total_paid"], w["left_over"]), ("1000.00", "400.00", "400.00", "600.00"))

    def test_waterfall_is_only_shown_on_open_and_closed_cases(self):
        c = self.case(); self.assertIsNone(c["waterfall"]); c = self.svc.isv_approve_case(ORG, c["id"], {}, U3); self.assertIsNotNone(c["waterfall"])

    def test_shortfall_with_one_cent_amounts(self):
        c = self.opened(); 
        for r in ("A-1", "A-2", "A-3"): c = self.claim(c, r, "UNSECURED", "0.01")
        for n in (1, 2, 3): c = self.admit(c, n, "0.01")
        c = self.entry(c, amt="0.02"); c = self.confirm(c, 1); un = c["waterfall"]["classes"][2]
        self.assertEqual((un["paid"], un["owed"], un["recovery_pct"], sorted(x["dividend"] for x in un["claims"])), ("0.02", "0.03", "66.67", ["0.00", "0.01", "0.01"])); self.assertEqual(sum(1 for x in un["claims"] if x["dividend"] == "0.01"), 2)


def cents(d): return int(Decimal(str(d)).scaleb(2))


class Distribution(Base):
    def test_record_updates_what_is_owed(self):
        c = self.example(); c = self.svc.isv_record_distribution(ORG, c["id"], {"note": "First distribution"}, U3); d = c["distributions"][0]
        self.assertEqual((d["no"], d["total"], d["available"], d["shortfall"], d["by"]), (1, "950000.00", "950000.00", "230000.01", U3)); self.assertEqual(sum(cents(x["amount"]) for x in d["lines"]), 95000000)
        by = {x["no"]: x for x in c["claims"]}; sh = indep_shares(37000000, [30000000, 20000000, 10000001]); self.assertEqual((by[1]["owed"], by[2]["owed"], [cents(by[n]["paid"]) for n in (3, 4, 5)]), ("0.00", "0.00", sh)); self.assertEqual(c["waterfall"]["distributed_to_date"], "950000.00")
        self.assertEqual(sum(cents(x["paid"]) for x in c["claims"]), 95000000); self.assertEqual(c["waterfall"]["available"], "0.00")
        with self.assertRaises(InsolvencyStateError): self.svc.isv_record_distribution(ORG, c["id"], {}, U3)           # nothing left to distribute

    def test_interim_distributions_pay_what_is_still_owed(self):
        c = self.example(); c = self.svc.isv_record_distribution(ORG, c["id"], {}, U3)
        c = self.entry(c, amt="100000.00", description="Sale of the vehicles"); c = self.confirm(c, 3); w = c["waterfall"]
        self.assertEqual((w["available"], w["total_owed"], w["total_paid"]), ("100000.00", "230000.01", "100000.00"))
        un = [k for k in w["classes"] if k["claim_class"] == "UNSECURED"][0]; owed = [cents(x["owed"]) for x in un["claims"]]; self.assertEqual([cents(x["dividend"]) for x in un["claims"]], indep_shares(10000000, owed))
        c = self.svc.isv_record_distribution(ORG, c["id"], {}, U4); self.assertEqual(len(c["distributions"]), 2); self.assertEqual(c["waterfall"]["total_owed"], "130000.01")
        c = self.entry(c, amt="130000.01", description="Recovery of a debt"); c = self.confirm(c, 4); c = self.svc.isv_record_distribution(ORG, c["id"], {}, U3)
        self.assertEqual((c["waterfall"]["total_owed"], c["waterfall"]["left_over"], c["waterfall"]["shortfall"]), ("0.00", "0.00", "0.00")); self.assertTrue(all(x["owed"] == "0.00" for x in c["claims"]))

    def test_surplus_is_shown_not_paid(self):
        c = self.opened(); c = self.claim(c); c = self.admit(c, 1, "400"); c = self.entry(c, amt="1000"); c = self.confirm(c, 1); c = self.svc.isv_record_distribution(ORG, c["id"], {}, U3)
        self.assertEqual((c["distributions"][0]["total"], c["waterfall"]["left_over"], c["waterfall"]["available"]), ("400.00", "600.00", "600.00"))

    def test_who_and_when(self):
        c = self.example()
        with self.assertRaises(InsolvencyForbiddenError): self.svc.isv_record_distribution(ORG, c["id"], {}, U1)                       # the proposer
        with self.assertRaises(InsolvencyError): self.svc.isv_record_distribution(ORG, c["id"], {"note": "short"}, U3)
        c2 = self.claim(c, "LATE-1"); 
        with self.assertRaises(InsolvencyStateError): self.svc.isv_record_distribution(ORG, c["id"], {}, U3)                           # a claim waits
        self.admit(c2, 6, "10"); c3 = self.entry(c2, amt="5", description="Small sale")
        with self.assertRaises(InsolvencyStateError): self.svc.isv_record_distribution(ORG, c["id"], {}, U3)                           # an entry waits
        self.confirm(c3, 3); self.assertEqual(len(self.svc.isv_record_distribution(ORG, c["id"], {}, U4)["distributions"]), 1)
        p = self.case()
        with self.assertRaises(InsolvencyStateError): self.svc.isv_record_distribution(ORG, p["id"], {}, U3)                           # not open


class Cases(Base):
    def test_validation(self):
        for bad in ({"title": "ab"}, {"description": "short"}, {"currency": "NG"}, {"priority": ["SECURED"]}, {"priority": ["SECURED", "SECURED", "UNSECURED", "PREFERENTIAL"]}, {"priority": ["A", "B", "C", "D"]}, {"priority": "SECURED"}, {"claims_deadline": "2026-02-30"}):
            with self.assertRaises(InsolvencyError, msg=bad): self.case(**bad)
        c = self.case(currency=" usd ", claims_deadline="2026-06-30"); self.assertEqual((c["ref"], c["currency"], c["status"], c["priority"], c["claims_deadline"]), ("IC-001", "USD", "PROPOSED", ["SECURED", "PREFERENTIAL", "UNSECURED", "SUBORDINATED"], "2026-06-30")); self.assertEqual(self.case()["ref"], "IC-002")
        self.assertIsNone(self.case(claims_deadline="")["claims_deadline"])

    def test_decisions_by_a_different_person(self):
        c = self.case()
        with self.assertRaises(InsolvencyForbiddenError): self.svc.isv_approve_case(ORG, c["id"], {}, U1)
        with self.assertRaises(InsolvencyForbiddenError): self.svc.isv_reject_case(ORG, c["id"], "Rejecting my own case", U1)
        with self.assertRaises(InsolvencyError): self.svc.isv_reject_case(ORG, c["id"], "short", U3)
        with self.assertRaises(InsolvencyError): self.svc.isv_approve_case(ORG, c["id"], {"note": "short"}, U3)
        for f in (lambda: self.claim(c), lambda: self.entry(c)):
            with self.assertRaises(InsolvencyStateError): f()
        self.assertEqual(self.svc.isv_approve_case(ORG, c["id"], {"note": "Appointment documents seen"}, U3)["status"], "OPEN")
        for f in (lambda: self.svc.isv_approve_case(ORG, c["id"], {}, U4), lambda: self.svc.isv_reject_case(ORG, c["id"], "Rejecting it a bit later", U4)):
            with self.assertRaises(InsolvencyStateError): f()
        r = self.case(); self.assertEqual(self.svc.isv_reject_case(ORG, r["id"], "Duplicate of another case", U3)["status"], "REJECTED")

    def test_close(self):
        c = self.opened(); c = self.claim(c)
        with self.assertRaises(InsolvencyStateError): self.svc.isv_close_case(ORG, c["id"], "The estate is finished", U3)
        c = self.admit(c, 1, "10")
        with self.assertRaises(InsolvencyError): self.svc.isv_close_case(ORG, c["id"], "short", U3)
        c = self.svc.isv_close_case(ORG, c["id"], "The estate is finished", U3); self.assertEqual((c["status"], c["close_note"]), ("CLOSED", "The estate is finished")); self.assertIsNotNone(c["waterfall"])
        for f in (lambda: self.claim(c, "SUP-9"), lambda: self.entry(c), lambda: self.svc.isv_close_case(ORG, c["id"], "Closing it a second time", U3), lambda: self.svc.isv_record_distribution(ORG, c["id"], {}, U3)):
            with self.assertRaises(InsolvencyStateError): f()

    def test_list_summary_only(self):
        c = self.example(); row = self.svc.isv_list_cases(ORG)[0]; self.assertEqual((row["claims"], row["entries"], row["history"], row["waterfall"]), ([], [], [], None)); self.assertEqual(row["admitted_total"], "1180000.01")
        self.assertEqual(len(self.svc.isv_list_cases(ORG, "OPEN")), 1); self.assertEqual(self.svc.isv_list_cases(ORG, "CLOSED"), [])


class Claims(Base):
    def test_validation(self):
        c = self.opened()
        for bad in ({"creditor_ref": "x"}, {"claim_class": "OTHER"}, {"claim_class": None}, {"amt": "0"}, {"amt": "-5"}, {"amt": 5.5}, {"amt": "1.234"}, {"amt": None}, {"amt": True}, {"basis": "short"}):
            kw = dict(bad); amt = kw.pop("amt", "1000")
            if "amt" in bad and "basis" not in bad: pass
            with self.assertRaises(InsolvencyError, msg=bad): self.claim(c, amt=amt, **kw)
        self.assertEqual(self.claim(c, cls="secured", amt="1,000.50")["claims"][0]["amount"], "1000.50")

    def test_admit_and_reject(self):
        c = self.claim(self.opened())
        with self.assertRaises(InsolvencyForbiddenError): self.admit(c, 1, "500", U1)
        with self.assertRaises(InsolvencyForbiddenError): self.svc.isv_reject_claim(ORG, c["id"], 1, "Rejecting my own claim", U1)
        for bad in ("0", "1000.01", "x", None, 5.5, "-1", True):
            with self.assertRaises(InsolvencyError, msg=bad): self.admit(c, 1, bad)
        with self.assertRaises(InsolvencyError): self.svc.isv_admit_claim(ORG, c["id"], 1, {"amount": "500", "note": "short"}, U3)
        for bad in ("x", None, True, 1.5):
            with self.assertRaises(InsolvencyError): self.admit(c, bad, "500")
        with self.assertRaises(InsolvencyNotFoundError): self.admit(c, 9, "500")
        with self.assertRaises(InsolvencyError): self.svc.isv_reject_claim(ORG, c["id"], 1, "short", U3)
        a = self.admit(c, 1, "1000"); self.assertEqual((a["claims"][0]["status"], a["claims"][0]["admitted"], a["claims"][0]["owed"], a["admitted_total"]), ("ADMITTED", "1000.00", "1000.00", "1000.00"))
        for f in (lambda: self.admit(c, 1, "500", U4), lambda: self.svc.isv_reject_claim(ORG, c["id"], 1, "Rejecting it a bit later", U4)):
            with self.assertRaises(InsolvencyStateError): f()

    def test_late_claims_are_flagged_not_refused(self):
        c = self.opened(claims_deadline="2026-03-30"); c = self.claim(c); self.assertTrue(c["claims"][0]["late"]); self.assertEqual(c["late_claims"], 1)
        self.assertIn("LATE_CLAIMS", [x["kind"] for x in self.svc.isv_overview(ORG)["attention"]])
        d = self.opened(claims_deadline="2026-03-31"); d = self.claim(d); self.assertFalse(d["claims"][0]["late"])                      # the deadline day itself is on time
        e = self.opened(); e = self.claim(e); self.assertFalse(e["claims"][0]["late"])

    def test_rejected_claims_leave_the_totals(self):
        c = self.opened(); c = self.claim(c); c = self.claim(c, "SUP-2", amt="500"); c = self.svc.isv_reject_claim(ORG, c["id"], 2, "No proof of debt was supplied", U3); self.assertEqual(c["claimed_total"], "1000.00")


class Entries(Base):
    def test_validation(self):
        c = self.opened()
        for bad in ({"entry_type": "GIFT"}, {"description": "ab"}, {"amount": "0"}, {"amount": 5.5}, {"amount": "-1"}, {"entry_date": "2026-02-30"}, {"entry_date": "2026-04-05"}, {"entry_date": None}):
            with self.assertRaises(InsolvencyError, msg=bad): self.entry(c, **bad)
        self.assertEqual(self.entry(c, entry_date="2026-04-01")["entries"][0]["entry_date"], "2026-04-01")

    def test_decisions(self):
        c = self.entry(self.opened())
        with self.assertRaises(InsolvencyForbiddenError): self.confirm(c, 1, U1)
        with self.assertRaises(InsolvencyForbiddenError): self.svc.isv_reject_entry(ORG, c["id"], 1, "Rejecting my own entry", U1)
        with self.assertRaises(InsolvencyError): self.svc.isv_reject_entry(ORG, c["id"], 1, "short", U3)
        with self.assertRaises(InsolvencyError): self.svc.isv_confirm_entry(ORG, c["id"], 1, {"note": "short"}, U3)
        with self.assertRaises(InsolvencyNotFoundError): self.confirm(c, 9)
        c = self.confirm(c, 1); self.assertEqual(c["entries"][0]["status"], "CONFIRMED")
        with self.assertRaises(InsolvencyStateError): self.confirm(c, 1, U4)


class Overview(Base):
    def test_totals_per_currency_and_attention(self):
        c = self.example(); self.svc.isv_record_distribution(ORG, c["id"], {}, U3)
        self.case(); u = self.opened(currency="USD"); u = self.claim(u, amt="50"); self.admit(u, 1, "50"); self.claim(u, "SUP-2")
        o = self.svc.isv_overview(ORG); self.assertEqual(o["counts"], {"proposed": 1, "open": 2, "rejected": 0, "closed": 0})
        self.assertEqual(o["totals"], [{"currency": "NGN", "cases": 1, "admitted": "1180000.01", "distributed": "950000.00"}, {"currency": "USD", "cases": 1, "admitted": "50.00", "distributed": "0.00"}])
        self.assertEqual({x["kind"]: x["count"] for x in o["attention"]}, {"CASES_TO_APPROVE": 1, "CLAIMS_TO_DECIDE": 1})

    def test_funds_ready(self):
        c = self.example(); self.assertIn("FUNDS_READY", [x["kind"] for x in self.svc.isv_overview(ORG)["attention"]])
        self.svc.isv_record_distribution(ORG, c["id"], {}, U3); self.assertNotIn("FUNDS_READY", [x["kind"] for x in self.svc.isv_overview(ORG)["attention"]])

    def test_empty(self):
        o = self.svc.isv_overview(ORG); self.assertEqual((o["attention"], o["totals"]), ([], []))


class Isolation(Base):
    def test_other_company(self):
        c = self.example(); self.assertEqual(self.svc.isv_list_cases(OTHER), [])
        for f in (lambda: self.svc.isv_get_case(OTHER, c["id"]), lambda: self.svc.isv_record_distribution(OTHER, c["id"], {}, U3), lambda: self.svc.isv_add_claim(OTHER, c["id"], {}, U1), lambda: self.svc.isv_close_case(OTHER, c["id"], "Closing from elsewhere", U3)):
            with self.assertRaises(InsolvencyNotFoundError): f()
        self.assertEqual(self.svc.isv_add_case(OTHER, dict(title="Other case", currency="NGN", description="A case of another company"), U1)["ref"], "IC-001")


class Audit(Base):
    def test_every_write_logged_without_content(self):
        c = self.opened(title="Secret estate name"); c = self.claim(c, "BANK-77", "SECURED", "123456.78", basis="Loan agreement signed by Chinedu"); c = self.admit(c, 1, "100000.00"); c = self.claim(c, "SUP-88"); c = self.svc.isv_reject_claim(ORG, c["id"], 2, "No proof of debt was supplied", U3)
        c = self.entry(c, amt="777777.77", description="Sale of the secret machinery"); c = self.confirm(c, 1); c = self.entry(c, "COST", "5", description="Cost to reject"); c = self.svc.isv_reject_entry(ORG, c["id"], 2, "Entered against the wrong case", U3)
        self.svc.isv_record_distribution(ORG, c["id"], {"note": "First distribution"}, U3); r = self.case(); self.svc.isv_reject_case(ORG, r["id"], "Duplicate of another case", U3); self.svc.isv_close_case(ORG, c["id"], "The estate is finished", U3)
        acts = [e[0] for e in self.events]
        for a in ("INSOLVENCY_CASE_PROPOSED", "INSOLVENCY_CASE_APPROVED", "INSOLVENCY_CASE_REJECTED", "INSOLVENCY_CASE_CLOSED", "INSOLVENCY_CLAIM_LODGED", "INSOLVENCY_CLAIM_ADMITTED", "INSOLVENCY_CLAIM_REJECTED", "INSOLVENCY_ENTRY_RECORDED", "INSOLVENCY_ENTRY_CONFIRMED", "INSOLVENCY_ENTRY_REJECTED", "INSOLVENCY_DISTRIBUTION_RECORDED"): self.assertIn(a, acts)
        blob = " ".join(str(e) for e in self.events)
        for secret in ("Secret estate", "BANK-77", "SUP-88", "123456", "777777", "Chinedu", "secret machinery", "No proof of debt", "wrong case", "First distribution", "Duplicate of", "estate is finished"): self.assertNotIn(secret, blob)

    def test_failed_actions_are_not_logged(self):
        with self.assertRaises(InsolvencyError): self.case(title="ab")
        c = self.opened(); n = len(self.events)
        with self.assertRaises(InsolvencyError): self.claim(c, amt="0")
        with self.assertRaises(InsolvencyForbiddenError): self.svc.isv_approve_case(ORG, self.case()["id"], {}, U1)
        self.assertEqual(len(self.events), n + 1)                                                                   # only the case proposed above


class Permissions(unittest.TestCase):
    def test_roles(self):
        has = lambda r, p: p in ROLE_PERMISSIONS[r]
        for r in (Role.OWNER, Role.ADMINISTRATOR, Role.MANAGER, Role.AUDITOR): self.assertTrue(has(r, ISV_PREPARE), r)
        for r in (Role.OWNER, Role.APPROVER, Role.MANAGER): self.assertTrue(has(r, ISV_APPROVE), r)
        for r in (Role.ACCOUNTANT, Role.REVIEWER, Role.EXTERNAL_AUDITOR, Role.READ_ONLY, Role.DONOR, Role.REGULATOR, Role.INVESTOR_REVIEWER): self.assertFalse(has(r, ISV_PREPARE) or has(r, ISV_APPROVE), r)

    def test_anyone_who_can_prepare_or_approve_can_view(self):
        for r, perms in ROLE_PERMISSIONS.items():
            if ISV_PREPARE in perms or ISV_APPROVE in perms: self.assertIn(AUDIT_READ, perms, r)


class RouterGuards(unittest.TestCase):
    SRC = os.path.join(os.path.dirname(__file__), "..", "src", "asavexa", "api", "routers", "insolvency.py")

    def test_every_write_has_the_right_guard(self):
        tree = ast.parse(open(self.SRC).read()); named = {"_prepare": "ISV_PREPARE", "_approve": "ISV_APPROVE"}; g = {}
        for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.decorator_list]:
            verbs, guards = set(), set()
            for dec in fn.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute): verbs.add(dec.func.attr)
                for kw in getattr(dec, "keywords", []):
                    if kw.arg == "dependencies": guards |= {named[e.id] for e in kw.value.elts if isinstance(e, ast.Name) and e.id in named}
            g[fn.name] = (verbs, guards)
        approve = {"approve_case", "reject_case", "close_case", "admit_claim", "reject_claim", "confirm_entry", "reject_entry", "record_distribution"}; prepare = {"add_case", "add_claim", "add_entry"}
        for n in approve: self.assertEqual(g[n][1], {"ISV_APPROVE"}, n)
        for n in prepare: self.assertEqual(g[n][1], {"ISV_PREPARE"}, n)
        for n, (verbs, guards) in g.items():
            if verbs == {"get"}: self.assertEqual(guards, set(), n)
            else: self.assertIn(n, approve | prepare, f"{n} writes but has no insolvency guard")
        src = open(self.SRC).read(); self.assertIn("dependencies=[Depends(require_permission(AUDIT_READ))]", src); self.assertNotIn("org_id", src)


if __name__ == "__main__":
    unittest.main()
