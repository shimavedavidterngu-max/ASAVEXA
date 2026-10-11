"""Public Finance: budget approval, execution against the posted ledger, commitments that cannot exceed availability, virements, procurement, grants, reports, isolation."""
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

from analysis_fixture import ORG, OTHER, World
from asavexa.evidence.domain.enums import EvidenceType
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.permissions import PUBFIN_APPROVE, PUBFIN_PREPARE, REPORTING_READ, ROLE_PERMISSIONS
from asavexa.pubfin.errors import PubFinError, PubFinForbiddenError, PubFinNotFoundError, PubFinStateError
from asavexa.pubfin.service import PubFinService

U1, U2, U3 = "user-1", "user-2", "user-3"


class Clock:
    def __init__(self): self.d = date(2026, 2, 15)
    def __call__(self): return datetime(self.d.year, self.d.month, self.d.day, 9, tzinfo=timezone.utc)


class Base(unittest.TestCase):
    def setUp(self):
        self.w = World(); self.clock = Clock(); self.events = []
        self.svc = PubFinService(self.w.store, self.w.acc, self.w.vault, log=lambda *a: self.events.append(a), now=self.clock)
        self.a = self.w.a

    def lines(self, rent="5000", cos="20000", interest="1000", sales="40000"):
        return [{"account_id": self.a["5100"].id, "amount": rent}, {"account_id": self.a["5000"].id, "amount": cos}, {"account_id": self.a["5200"].id, "amount": interest}, {"account_id": self.a["4000"].id, "amount": sales}]

    def draft(self, rent="5000", **kw):
        d = dict(name="Operations 2026 H1", start="2026-01-01", end="2026-02-28", currency="USD", lines=self.lines(rent=rent)); d.update(kw)
        return self.svc.create_budget(ORG, d, U1)

    def approved(self, **kw):
        b = self.draft(**kw); self.svc.submit_budget(ORG, b["id"], U1); return self.svc.approve_budget(ORG, b["id"], U2)

    def row(self, bid, code):
        return next(r for r in self.svc.execution(ORG, bid)["rows"] if r["code"] == code)

    def commit(self, bid, code="5100", amount="100", **kw):
        d = dict(budget_id=bid, account_id=self.a[code].id, vendor="Landlord Ltd", description="Rent", amount=amount, date="2026-02-10"); d.update(kw)
        return self.svc.create_commitment(ORG, d, U1)

    def evidence(self):
        return self.w.vault.upload_evidence(ORG, list(EvidenceType)[0], b"quote body" * 5, "quote.pdf", "application/pdf", uploaded_by=U1)


class Budgets(Base):
    def test_lifecycle_and_two_person_approval(self):
        b = self.draft(); self.assertEqual((b["status"], b["ref"], b["total_expense"], b["total_revenue"]), ("DRAFT", "B-001", "26000.00", "40000.00"))
        s = self.svc.submit_budget(ORG, b["id"], U1); self.assertEqual(s["status"], "SUBMITTED")
        with self.assertRaises(PubFinForbiddenError): self.svc.approve_budget(ORG, b["id"], U1)
        with self.assertRaises(PubFinForbiddenError): self.svc.reject_budget(ORG, b["id"], U1, "no way")
        with self.assertRaises(PubFinError): self.svc.reject_budget(ORG, b["id"], U2, "")
        self.assertEqual(self.svc.reject_budget(ORG, b["id"], U2, "Rent too low")["status"], "REJECTED")
        self.svc.update_budget(ORG, b["id"], {"name": "Operations v2"}, U1)
        self.svc.submit_budget(ORG, b["id"], U3)
        self.assertEqual(self.svc.approve_budget(ORG, b["id"], U2)["status"], "APPROVED")

    def test_approved_budget_is_frozen(self):
        b = self.approved()
        for f in (lambda: self.svc.update_budget(ORG, b["id"], {"name": "Changed"}, U1), lambda: self.svc.submit_budget(ORG, b["id"], U1), lambda: self.svc.discard_budget(ORG, b["id"], U1)):
            with self.assertRaises(PubFinStateError): f()

    def test_tampering_with_stored_lines_blocks_approval(self):
        b = self.draft(); self.svc.submit_budget(ORG, b["id"], U1)
        raw = self.w.store.get("pf_budget", f"{ORG}:{b['id']}"); raw["lines"][0]["amount"] = "999999.00"; self.w.store.put("pf_budget", f"{ORG}:{b['id']}", raw, org_id=ORG)
        with self.assertRaises(PubFinStateError): self.svc.approve_budget(ORG, b["id"], U2)

    def test_validation(self):
        bad = [dict(name="ab"), dict(start="2026-13-01"), dict(end="2025-12-31"), dict(currency="US"), dict(lines=[]), dict(lines=[{"account_id": "nope", "amount": "5"}]),
               dict(lines=[{"account_id": self.a["1000"].id, "amount": "5"}]), dict(lines=[{"account_id": self.a["5100"].id, "amount": "-5"}]), dict(lines=[{"account_id": self.a["5100"].id, "amount": "abc"}]),
               dict(lines=[{"account_id": self.a["5100"].id, "amount": "5"}, {"account_id": self.a["5100"].id, "amount": "6"}])]
        for kw in bad:
            with self.assertRaises((PubFinError, PubFinNotFoundError), msg=str(kw)): self.draft(**kw)

    def test_discard(self):
        b = self.draft(); self.svc.discard_budget(ORG, b["id"], U1); self.assertEqual(self.svc.list_budgets(ORG), [])

    def test_close_blocked_by_open_commitment(self):
        b = self.approved(); c = self.commit(b["id"])
        with self.assertRaises(PubFinStateError): self.svc.close_budget(ORG, b["id"], "Year finished fully", U1)
        self.svc.cancel_commitment(ORG, c["id"], "Not needed any more", U1)
        self.assertEqual(self.svc.close_budget(ORG, b["id"], "Year finished fully", U1)["status"], "CLOSED")
        with self.assertRaises(PubFinStateError): self.commit(b["id"])


class Execution(Base):
    def test_actuals_come_from_posted_journals_in_the_period(self):
        b = self.approved(); ex = self.svc.execution(ORG, b["id"])
        r = {x["code"]: x for x in ex["rows"]}
        self.assertEqual((r["5100"]["actual"], r["5000"]["actual"], r["5200"]["actual"], r["4000"]["actual"]), ("4400.00", "15000.00", "500.00", "35000.00"))
        self.assertEqual((r["5100"]["available"], r["5100"]["used_pct"], r["4000"]["shortfall"]), ("600.00", "88.00", "5000.00"))
        self.assertEqual(ex["expense_totals"], {"budget": "26000.00", "actual": "19900.00", "committed": "0.00", "available": "6100.00"})

    def test_period_dates_limit_actuals(self):
        b = self.approved(end="2026-01-31"); self.assertEqual(self.row(b["id"], "5100")["actual"], "2000.00")

    def test_drafts_never_count(self):
        from asavexa.accounting.services.engine import LineInput
        self.w.acc.create_draft_journal(ORG, date(2026, 2, 20), "Draft rent", "USD", [LineInput(self.a["5100"].id, debit_amount=Decimal("999"), credit_amount=Decimal(0)), LineInput(self.a["1000"].id, debit_amount=Decimal(0), credit_amount=Decimal("999"))], created_by=U1)
        b = self.approved(); self.assertEqual(self.row(b["id"], "5100")["actual"], "4400.00")

    def test_open_commitments_reduce_available_settled_do_not(self):
        b = self.approved(); c = self.commit(b["id"], amount="250.50")
        self.assertEqual((self.row(b["id"], "5100")["committed"], self.row(b["id"], "5100")["available"]), ("250.50", "349.50"))
        self.svc.settle_commitment(ORG, c["id"], "250.50", "Posted as JE-9", U1)
        self.assertEqual((self.row(b["id"], "5100")["committed"], self.row(b["id"], "5100")["available"]), ("0.00", "600.00"))

    def test_overspent_line_flagged(self):
        b = self.approved(rent="4000"); r = self.row(b["id"], "5100"); self.assertEqual((r["available"], r["overspent"]), ("-400.00", True))
        self.assertEqual(self.svc.overview(ORG)["overspent_lines"][0]["code"], "5100")

    def test_money_is_exact(self):
        b = self.approved(rent="0.30"); self.assertEqual(self.row(b["id"], "5100")["budget"], "0.30")
        self.assertEqual(self.row(self.approved(name="Another one", rent="4400.005")["id"], "5100")["budget"], "4400.01")


class Commitments(Base):
    def test_cannot_exceed_available_and_nothing_is_recorded(self):
        b = self.approved()
        with self.assertRaises(PubFinStateError): self.commit(b["id"], amount="600.01")
        self.assertEqual(self.svc.list_commitments(ORG), [])
        self.commit(b["id"], amount="600.00")
        with self.assertRaises(PubFinStateError): self.commit(b["id"], amount="0.01")

    def test_validation(self):
        b = self.approved()
        for kw in (dict(amount="0"), dict(amount="-5"), dict(amount="x"), dict(date="2027-01-01"), dict(date="soon"), dict(vendor=""), dict(code="4000"), dict(code="1000")):
            with self.assertRaises(PubFinError, msg=str(kw)): self.commit(b["id"], **kw)
        d = self.draft(name="Not yet approved")
        with self.assertRaises(PubFinStateError): self.commit(d["id"])

    def test_settle_and_cancel_states(self):
        b = self.approved(); c = self.commit(b["id"])
        with self.assertRaises(PubFinError): self.svc.settle_commitment(ORG, c["id"], "-1", "note ok", U1)
        s = self.svc.settle_commitment(ORG, c["id"], "90", "Posted as JE-9", U1); self.assertEqual((s["status"], s["settled_amount"]), ("SETTLED", "90.00"))
        for f in (lambda: self.svc.settle_commitment(ORG, c["id"], "90", "again here", U1), lambda: self.svc.cancel_commitment(ORG, c["id"], "too late now", U1)):
            with self.assertRaises(PubFinStateError): f()

    def test_evidence_attached_and_unknown_refused(self):
        b = self.approved(); ev = self.evidence()
        self.assertEqual(self.commit(b["id"], evidence_ids=[ev.id])["evidence"][0]["filename"], "quote.pdf")
        with self.assertRaises(PubFinError): self.commit(b["id"], evidence_ids=["nope"])

    def test_references_sequential(self):
        b = self.approved(); self.assertEqual([self.commit(b["id"])["ref"], self.commit(b["id"])["ref"]], ["C-001", "C-002"])


class Virements(Base):
    def test_moves_budget_after_second_person_approves(self):
        b = self.approved(); r, c = self.a["5100"].id, self.a["5000"].id
        v = self.svc.propose_virement(ORG, b["id"], c, r, "500", "Rent rose after renegotiation", U1)["virements"][0]
        self.assertEqual(self.row(b["id"], "5100")["budget"], "5000.00")
        with self.assertRaises(PubFinForbiddenError): self.svc.approve_virement(ORG, b["id"], v["id"], U1)
        self.svc.approve_virement(ORG, b["id"], v["id"], U2, "ok")
        self.assertEqual((self.row(b["id"], "5100")["budget"], self.row(b["id"], "5100")["adjustment"], self.row(b["id"], "5000")["budget"]), ("5500.00", "500.00", "19500.00"))
        with self.assertRaises(PubFinStateError): self.svc.approve_virement(ORG, b["id"], v["id"], U2)

    def test_cannot_take_more_than_available(self):
        b = self.approved(); v = self.svc.propose_virement(ORG, b["id"], self.a["5100"].id, self.a["5000"].id, "601", "Moving too much money", U1)["virements"][0]
        with self.assertRaises(PubFinStateError): self.svc.approve_virement(ORG, b["id"], v["id"], U2)

    def test_commitment_after_virement_uses_new_availability(self):
        b = self.approved(); v = self.svc.propose_virement(ORG, b["id"], self.a["5000"].id, self.a["5100"].id, "400", "Rent rose after renegotiation", U1)["virements"][0]
        self.svc.approve_virement(ORG, b["id"], v["id"], U2); self.commit(b["id"], amount="1000")

    def test_validation_and_reject(self):
        b = self.approved(); r, c = self.a["5100"].id, self.a["5000"].id
        for args in ((r, r, "5", "Same line again here"), (r, self.a["4000"].id, "5", "Revenue line is not allowed"), (r, "nope", "5", "Unknown line given"), (r, c, "0", "Zero amount given here"), (r, c, "5", "short")):
            with self.assertRaises(PubFinError): self.svc.propose_virement(ORG, b["id"], *args, U1)
        v = self.svc.propose_virement(ORG, b["id"], r, c, "5", "A fine long reason", U1)["virements"][0]
        with self.assertRaises(PubFinError): self.svc.reject_virement(ORG, b["id"], v["id"], U2, "")
        self.svc.reject_virement(ORG, b["id"], v["id"], U2, "Not justified")
        self.assertEqual(self.row(b["id"], "5100")["budget"], "5000.00")

    def test_pending_virement_blocks_close_and_draft_budget_refused(self):
        b = self.approved(); self.svc.propose_virement(ORG, b["id"], self.a["5100"].id, self.a["5000"].id, "5", "A fine long reason", U1)
        with self.assertRaises(PubFinStateError): self.svc.close_budget(ORG, b["id"], "Closing the budget", U1)
        with self.assertRaises(PubFinStateError): self.svc.propose_virement(ORG, self.draft(name="Draft one")["id"], self.a["5100"].id, self.a["5000"].id, "5", "A fine long reason", U1)


class Procurement(Base):
    def setUp(self):
        super().setUp(); self.b = self.approved()

    def proc(self, estimate="400"):
        return self.svc.create_procurement(ORG, dict(budget_id=self.b["id"], account_id=self.a["5100"].id, title="Office space", estimate=estimate), U1)

    def quotes(self, p, amounts=("300", "350", "400")):
        for i, a in enumerate(amounts): p = self.svc.add_quote(ORG, p["id"], f"Vendor {i}", a, "", [], U1)
        return p

    def test_award_creates_commitment_after_second_person_approves(self):
        p = self.quotes(self.proc()); lowest = p["quotes"][0]["id"]
        p = self.svc.propose_award(ORG, p["id"], lowest, "", "", U1); self.assertEqual((p["status"], p["award"]["flags"]), ("AWARD_PROPOSED", []))
        with self.assertRaises(PubFinForbiddenError): self.svc.approve_award(ORG, p["id"], U1)
        a = self.svc.approve_award(ORG, p["id"], U2)
        self.assertEqual((a["status"], a["commitment_ref"]), ("AWARDED", "C-001"))
        c = self.svc.list_commitments(ORG)[0]; self.assertEqual((c["amount"], c["vendor"], c["procurement_id"]), ("300.00", "Vendor 0", p["id"]))
        self.assertEqual(self.row(self.b["id"], "5100")["available"], "300.00")

    def test_policy_quote_count_and_exception(self):
        p = self.quotes(self.proc(), ("300", "350")); q = p["quotes"][0]["id"]
        with self.assertRaises(PubFinError): self.svc.propose_award(ORG, p["id"], q, "", "", U1)
        with self.assertRaises(PubFinError): self.svc.propose_award(ORG, p["id"], q, "", "too short", U1)
        a = self.svc.propose_award(ORG, p["id"], q, "", "Only two suppliers exist in this district.", U1); self.assertIn("EXCEPTION: fewer quotes than policy", a["award"]["flags"])

    def test_threshold_below_which_policy_does_not_apply(self):
        self.svc.set_policy(ORG, 3, "1000", U2)
        p = self.quotes(self.proc("400"), ("300",)); self.svc.propose_award(ORG, p["id"], p["quotes"][0]["id"], "", "", U1)

    def test_not_lowest_needs_justification(self):
        p = self.quotes(self.proc()); q = p["quotes"][2]["id"]
        with self.assertRaises(PubFinError): self.svc.propose_award(ORG, p["id"], q, "short", "", U1)
        a = self.svc.propose_award(ORG, p["id"], q, "Higher quote includes delivery and a warranty.", "", U1); self.assertIn("NOT LOWEST QUOTE", a["award"]["flags"])

    def test_award_beyond_available_leaves_it_proposed(self):
        p = self.quotes(self.proc(), ("700", "800", "900")); self.svc.propose_award(ORG, p["id"], p["quotes"][0]["id"], "", "", U1)
        with self.assertRaises(PubFinStateError): self.svc.approve_award(ORG, p["id"], U2)
        self.assertEqual((self.svc.get_procurement(ORG, p["id"])["status"], self.svc.list_commitments(ORG)), ("AWARD_PROPOSED", []))

    def test_reject_returns_to_open_and_duplicate_vendor_refused(self):
        p = self.quotes(self.proc()); self.svc.propose_award(ORG, p["id"], p["quotes"][0]["id"], "", "", U1)
        with self.assertRaises(PubFinError): self.svc.reject_award(ORG, p["id"], U2, "")
        self.assertEqual(self.svc.reject_award(ORG, p["id"], U2, "Check references first")["status"], "OPEN")
        with self.assertRaises(PubFinError): self.svc.add_quote(ORG, p["id"], "vendor 0", "100", "", [], U1)

    def test_validation_and_cancel(self):
        for kw in (dict(estimate="0"), dict(estimate="x"), dict(title="")):
            with self.assertRaises(PubFinError): self.svc.create_procurement(ORG, {**dict(budget_id=self.b["id"], account_id=self.a["5100"].id, title="Thing", estimate="5"), **kw}, U1)
        with self.assertRaises(PubFinError): self.svc.create_procurement(ORG, dict(budget_id=self.b["id"], account_id=self.a["4000"].id, title="Thing", estimate="5"), U1)
        p = self.proc(); self.svc.add_quote(ORG, p["id"], "Vendor A", "5", "", [], U1)
        with self.assertRaises(PubFinError): self.svc.add_quote(ORG, p["id"], "Vendor B", "-5", "", [], U1)
        with self.assertRaises(PubFinNotFoundError): self.svc.propose_award(ORG, p["id"], "nope", "", "", U1)
        with self.assertRaises(PubFinError): self.svc.cancel_procurement(ORG, p["id"], "no", U1)
        self.assertEqual(self.svc.cancel_procurement(ORG, p["id"], "No longer required", U1)["status"], "CANCELLED")
        with self.assertRaises(PubFinStateError): self.svc.add_quote(ORG, p["id"], "Vendor Z", "5", "", [], U1)

    def test_policy_validation(self):
        for mq, th in ((0, "5"), (11, "5"), ("x", "5"), (True, "5"), (3, "-1"), (3, "x")):
            with self.assertRaises(PubFinError): self.svc.set_policy(ORG, mq, th, U2)
        self.assertEqual(self.svc.set_policy(ORG, 2, "1500.5", U2)["quote_threshold"], "1500.50")


class Grants(Base):
    def grant(self, **kw):
        d = dict(title="Water project", donor="Aid Fund", amount="10000", currency="USD", start="2026-01-01", end="2026-12-31", conditions="Report quarterly"); d.update(kw)
        return self.svc.create_grant(ORG, d, U1)

    def test_spend_needs_second_person_and_counts_only_when_approved(self):
        g = self.grant(); g = self.svc.record_receipt(ORG, g["id"], "6000", "2026-01-20", "BANK-77", U1)
        g = self.svc.add_spend(ORG, g["id"], "2500.25", "2026-02-01", "Pump purchase", "JE-5", [], U1); sid = g["spend"][0]["id"]
        self.assertEqual((g["spent"], g["pending"]), ("0.00", "2500.25"))
        with self.assertRaises(PubFinForbiddenError): self.svc.approve_spend(ORG, g["id"], sid, U1)
        g = self.svc.approve_spend(ORG, g["id"], sid, U2)
        self.assertEqual((g["spent"], g["remaining"], g["utilisation_pct"], g["received"], g["cash_on_hand"]), ("2500.25", "7499.75", "25.00", "6000.00", "3499.75"))

    def test_cannot_spend_above_award(self):
        g = self.grant(amount="1000"); g = self.svc.add_spend(ORG, g["id"], "1200", "2026-02-01", "Too much money", "", [], U1)
        with self.assertRaises(PubFinStateError): self.svc.approve_spend(ORG, g["id"], g["spend"][0]["id"], U2)
        g = self.svc.add_spend(ORG, g["id"], "1000", "2026-02-02", "Exactly the award", "", [], U1)
        self.assertEqual(self.svc.approve_spend(ORG, g["id"], g["spend"][1]["id"], U2)["remaining"], "0.00")
        g = self.svc.add_spend(ORG, g["id"], "0.01", "2026-02-03", "One cent more", "", [], U1)
        with self.assertRaises(PubFinStateError): self.svc.approve_spend(ORG, g["id"], g["spend"][2]["id"], U2)

    def test_dates_receipts_and_validation(self):
        g = self.grant()
        with self.assertRaises(PubFinError): self.svc.add_spend(ORG, g["id"], "5", "2025-12-31", "Before the grant", "", [], U1)
        with self.assertRaises(PubFinError): self.svc.add_spend(ORG, g["id"], "5", "2027-01-01", "After the grant", "", [], U1)
        self.svc.record_receipt(ORG, g["id"], "10000", "2026-01-20", "BANK-1", U1)
        with self.assertRaises(PubFinStateError): self.svc.record_receipt(ORG, g["id"], "0.01", "2026-01-21", "BANK-2", U1)
        for kw in (dict(amount="0"), dict(end="2025-01-01"), dict(currency="U"), dict(donor=""), dict(title="")):
            with self.assertRaises(PubFinError): self.grant(**kw)

    def test_reject_close_and_flags(self):
        g = self.grant(end="2026-02-01"); g = self.svc.add_spend(ORG, g["id"], "50", "2026-01-30", "Hand tools", "", [], U1)
        with self.assertRaises(PubFinError): self.svc.reject_spend(ORG, g["id"], g["spend"][0]["id"], U2, "")
        with self.assertRaises(PubFinStateError): self.svc.close_grant(ORG, g["id"], "Grant is finished", U1)
        g = self.svc.approve_spend(ORG, g["id"], g["spend"][0]["id"], U2)
        self.assertTrue(g["expired"]); self.assertTrue(g["overspent_vs_received"])
        self.assertEqual(self.svc.overview(ORG)["grants_overspent_vs_received"][0]["ref"], "G-001")
        self.assertEqual(self.svc.close_grant(ORG, g["id"], "Grant is finished", U1)["status"], "CLOSED")
        with self.assertRaises(PubFinStateError): self.svc.add_spend(ORG, g["id"], "5", "2026-01-30", "After close", "", [], U1)

    def test_spend_evidence(self):
        g = self.grant(); ev = self.evidence()
        self.assertEqual(self.svc.add_spend(ORG, g["id"], "5", "2026-02-01", "Receipt held", "", [ev.id], U1)["spend"][0]["evidence"][0]["file_hash"], ev.file_hash)
        with self.assertRaises(PubFinError): self.svc.add_spend(ORG, g["id"], "5", "2026-02-01", "Receipt held", "", ["nope"], U1)


class Reports(Base):
    def test_report_flow_freezes_figures_and_exports(self):
        b = self.approved(); self.commit(b["id"], amount="100"); g = self.svc.create_grant(ORG, dict(title="=cmd|' /C calc'!A0", donor="Aid", amount="500", currency="USD", start="2026-01-01", end="2026-12-31"), U1)
        r = self.svc.create_report(ORG, b["id"], "H1 accountability", U1)
        with self.assertRaises(PubFinStateError): self.svc.export_csv(ORG, r["id"], U1)
        s = self.svc.submit_report(ORG, r["id"], U1); self.assertEqual((s["status"], s["version"]), ("SUBMITTED", 1))
        with self.assertRaises(PubFinForbiddenError): self.svc.approve_report(ORG, r["id"], U1)
        with self.assertRaises(PubFinError): self.svc.reject_report(ORG, r["id"], U2, "")
        self.svc.reject_report(ORG, r["id"], U2, "Add the grants"); s2 = self.svc.submit_report(ORG, r["id"], U3); self.assertEqual(s2["version"], 2)
        self.svc.approve_report(ORG, r["id"], U2)
        self.commit(b["id"], amount="50")  # after freezing
        out = self.svc.export_csv(ORG, r["id"], U1)
        self.assertIn("CONFIDENTIAL", out["content"].splitlines()[0]); self.assertIn("BUDGET EXECUTION", out["content"]); self.assertIn("'=cmd", out["content"]); self.assertNotIn(",=cmd", out["content"])
        frozen = self.svc.get_report(ORG, r["id"])["snapshot"]["execution"]["expense_totals"]["committed"]; self.assertEqual(frozen, "100.00")
        self.assertEqual(self.svc.execution(ORG, b["id"])["expense_totals"]["committed"], "150.00")

    def test_tamper_blocks_approval_and_export(self):
        b = self.approved(); r = self.svc.create_report(ORG, b["id"], "H1 accountability", U1); self.svc.submit_report(ORG, r["id"], U1)
        raw = self.w.store.get("pf_report", f"{ORG}:{r['id']}"); raw["snapshot"]["execution"]["expense_totals"]["actual"] = "0.00"; self.w.store.put("pf_report", f"{ORG}:{r['id']}", raw, org_id=ORG)
        with self.assertRaises(PubFinStateError): self.svc.approve_report(ORG, r["id"], U2)

    def test_needs_approved_budget(self):
        with self.assertRaises(PubFinStateError): self.svc.create_report(ORG, self.draft()["id"], "Too early report", U1)


class IsolationAndAudit(Base):
    def test_other_org_sees_nothing_and_touches_nothing(self):
        b = self.approved(); c = self.commit(b["id"]); g = self.svc.create_grant(ORG, dict(title="Grant", donor="Donor", amount="500", currency="USD", start="2026-01-01", end="2026-12-31"), U1)
        p = self.svc.create_procurement(ORG, dict(budget_id=b["id"], account_id=self.a["5100"].id, title="Thing", estimate="5"), U1)
        for f in (lambda: self.svc.get_budget(OTHER, b["id"]), lambda: self.svc.execution(OTHER, b["id"]), lambda: self.svc.settle_commitment(OTHER, c["id"], "1", "note ok", U2), lambda: self.svc.get_grant(OTHER, g["id"]),
                  lambda: self.svc.add_quote(OTHER, p["id"], "V", "5", "", [], U2), lambda: self.svc.create_report(OTHER, b["id"], "Sneaky report", U2),
                  lambda: self.svc.propose_virement(OTHER, b["id"], self.a["5100"].id, self.a["5000"].id, "5", "A fine long reason", U2)):
            with self.assertRaises(PubFinNotFoundError): f()
        self.assertEqual((self.svc.list_budgets(OTHER), self.svc.list_commitments(OTHER), self.svc.list_grants(OTHER), self.svc.list_procurements(OTHER)), ([], [], [], []))
        self.assertEqual(self.svc.overview(OTHER)["counts"]["budgets"], 0)

    def test_policy_is_per_org(self):
        self.svc.set_policy(ORG, 5, "100", U2); self.assertEqual(self.svc.get_policy(OTHER)["min_quotes"], 3)

    def test_every_write_is_audited(self):
        b = self.approved(); self.commit(b["id"]); self.svc.set_policy(ORG, 2, "5", U2)
        r = self.svc.create_report(ORG, b["id"], "H1 accountability", U1); self.svc.submit_report(ORG, r["id"], U1); self.svc.approve_report(ORG, r["id"], U2); self.svc.export_csv(ORG, r["id"], U1)
        acts = {e[0] for e in self.events}
        for x in ("PF_BUDGET_CREATED", "PF_BUDGET_SUBMITTED", "PF_BUDGET_APPROVED", "PF_COMMITMENT_CREATED", "PF_POLICY_SET", "PF_REPORT_APPROVED", "PF_REPORT_EXPORTED"): self.assertIn(x, acts)

    def test_role_matrix_and_options(self):
        has = lambda role, p: p in ROLE_PERMISSIONS[role]
        for role in (Role.OWNER, Role.ACCOUNTANT, Role.FINANCE_OFFICER): self.assertTrue(has(role, PUBFIN_PREPARE), role)
        for role in (Role.OWNER, Role.FINANCE_OFFICER, Role.APPROVER, Role.MANAGER): self.assertTrue(has(role, PUBFIN_APPROVE), role)
        for role in (Role.READ_ONLY, Role.AUDITOR, Role.REVIEWER, Role.EXTERNAL_AUDITOR, Role.APPROVER, Role.MANAGER, Role.ADMINISTRATOR): self.assertFalse(has(role, PUBFIN_PREPARE), role)
        for role in (Role.READ_ONLY, Role.AUDITOR, Role.ACCOUNTANT, Role.ADMINISTRATOR): self.assertFalse(has(role, PUBFIN_APPROVE), role)
        o = self.svc.options(ORG); self.assertTrue(all(a["type"] in ("EXPENSE", "REVENUE") for a in o["accounts"])); self.assertTrue(o["limitations"])


if __name__ == "__main__":
    unittest.main()
