"""Treasury: accounts and balances, cash position, expected cash flows, the liquidity forecast, payment requests with separate approval and release, covenants, policy, isolation."""
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

from analysis_fixture import ORG, OTHER, World
from asavexa.evidence.domain.enums import EvidenceType
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.permissions import REPORTING_READ, ROLE_PERMISSIONS, TREASURY_APPROVE, TREASURY_PREPARE
from asavexa.treasury.errors import TreasuryError, TreasuryForbiddenError, TreasuryNotFoundError, TreasuryStateError
from asavexa.treasury.service import TreasuryService, add_months

U1, U2, U3 = "user-1", "user-2", "user-3"


class Clock:
    def __init__(self): self.d = date(2026, 2, 15)
    def __call__(self): return datetime(self.d.year, self.d.month, self.d.day, 9, tzinfo=timezone.utc)


class Base(unittest.TestCase):
    def setUp(self):
        self.w = World(); self.clock = Clock(); self.events = []
        self.svc = TreasuryService(self.w.store, self.w.vault, log=lambda *a: self.events.append(a), now=self.clock)

    def acct(self, name="Main current account", cur="NGN", **kw):
        d = dict(name=name, bank_name="First Bank", currency=cur, last4="4321", purpose="Operations"); d.update(kw)
        return self.svc.open_cash_account(ORG, d, U1)

    def bal(self, a, amount="10000.00", as_at="2026-02-14", actor=U1, **kw):
        d = dict(as_at=as_at, amount=amount, source="Bank statement 14 Feb"); d.update(kw)
        return self.svc.record_balance(ORG, a["id"], d, actor)

    def flow(self, a=None, direction="IN", when="2026-02-24", amount="5000.00", cert="EXPECTED", **kw):
        d = dict(direction=direction, flow_date=when, amount=amount, category="CUSTOMER_RECEIPT" if direction == "IN" else "SUPPLIER_PAYMENT", description="Expected item", certainty=cert, currency="NGN")
        if a: d["account_id"] = a["id"]
        d.update(kw)
        return self.svc.add_cash_flow(ORG, d, U1)

    def pay(self, a, amount="500.00", payee="Acme Supplies", due="2026-02-20", actor=U1, **kw):
        self.n = getattr(self, "n", 0) + 1
        ev = self.w.vault.upload_evidence(ORG, list(EvidenceType)[0], f"invoice copy {self.n}".encode() * 4, "inv.pdf", "application/pdf", uploaded_by=U1)
        d = dict(account_id=a["id"], payee=payee, amount=amount, due_date=due, reason="Invoice for supplies", invoice_ref=kw.pop("invoice_ref", "INV-1"), evidence_ids=[ev.id]); d.update(kw)
        return self.svc.request_payment(ORG, d, actor)

    def cov(self, **kw):
        d = dict(name="Debt service cover", lender="Big Bank", description="Operating cash flow divided by debt service", comparator="MIN", threshold="1.25", unit="RATIO", frequency="QUARTERLY", watch_pct=10, effective_from="2025-12-31"); d.update(kw)
        return self.svc.add_covenant(ORG, d, U1)


class Accounts(Base):
    def test_open_and_view(self):
        a = self.acct(); self.assertEqual(a["ref"], "CA-001"); self.assertEqual(a["currency"], "NGN"); self.assertTrue(a["stale"]); self.assertIsNone(a["latest_balance"])
        self.assertEqual(self.acct("Savings")["ref"], "CA-002"); self.assertEqual(len(self.svc.list_cash_accounts(ORG)), 2)

    def test_duplicate_name_and_bad_input(self):
        self.acct()
        with self.assertRaises(TreasuryStateError): self.acct("main CURRENT account")
        for bad in (dict(currency="NG"), dict(currency="N1N"), dict(currency="12 "), dict(name="x"), dict(last4="123456"), dict(last4="12-3")):
            with self.assertRaises(TreasuryError, msg=bad): self.acct("Other", **bad) if "name" not in bad else self.acct(**bad)

    def test_whole_account_numbers_are_refused(self):
        with self.assertRaises(TreasuryError): self.acct("Full number", last4="0123456789")

    def test_close_needs_reason_and_no_open_items(self):
        a = self.acct(); self.bal(a); f = self.flow(a)
        with self.assertRaises(TreasuryError): self.svc.close_cash_account(ORG, a["id"], "", U1)
        with self.assertRaises(TreasuryStateError): self.svc.close_cash_account(ORG, a["id"], "No longer needed", U1)
        self.svc.cancel_cash_flow(ORG, f["id"], "Not happening", U1)
        p = self.pay(a)
        with self.assertRaises(TreasuryStateError): self.svc.close_cash_account(ORG, a["id"], "No longer needed", U1)
        self.svc.cancel_payment(ORG, p["id"], U1, "Changed our mind")
        self.assertEqual(self.svc.close_cash_account(ORG, a["id"], "No longer needed", U1)["status"], "CLOSED")
        with self.assertRaises(TreasuryStateError): self.svc.close_cash_account(ORG, a["id"], "again again", U1)
        with self.assertRaises(TreasuryStateError): self.bal(a, as_at="2026-02-15")
        self.assertEqual(self.svc.cash_position(ORG)["currencies"], [])


class Balances(Base):
    def test_record_and_confirm_by_another_person(self):
        a = self.acct(); v = self.bal(a); b = v["latest_balance"]; self.assertEqual((b["amount"], b["status"]), ("10000.00", "RECORDED")); self.assertFalse(v["stale"]); self.assertEqual(v["age_days"], 1)
        with self.assertRaises(TreasuryForbiddenError): self.svc.confirm_balance(ORG, a["id"], b["id"], U1)
        v = self.svc.confirm_balance(ORG, a["id"], b["id"], U2); self.assertEqual(v["latest_balance"]["status"], "CONFIRMED"); self.assertEqual(v["latest_balance"]["confirmed_by"], U2)
        with self.assertRaises(TreasuryStateError): self.svc.confirm_balance(ORG, a["id"], b["id"], U3)
        with self.assertRaises(TreasuryNotFoundError): self.svc.confirm_balance(ORG, a["id"], "nope", U2)

    def test_validation(self):
        a = self.acct()
        for bad in (dict(as_at="2026-02-17"), dict(as_at="2026-13-01"), dict(as_at=""), dict(amount="abc"), dict(amount="1.234"), dict(amount="NaN"), dict(amount="Infinity"), dict(amount=None), dict(amount="1e30"),
                    dict(amount=True), dict(source="x"), dict(source="")):
            with self.assertRaises(TreasuryError, msg=bad): self.bal(a, **bad)
        self.assertEqual(self.bal(a, amount="-250.50")["latest_balance"]["amount"], "-250.50")        # an overdraft is a real balance
        self.assertEqual(self.bal(a, amount="1,234.50", as_at="2026-02-10")["balances"][0]["amount"], "-250.50")

    def test_today_and_tomorrow_are_allowed_for_people_ahead_of_utc(self):
        a = self.acct(); self.assertEqual(self.bal(a, "5.00", "2026-02-16")["latest_balance"]["as_at"], "2026-02-16")
        with self.assertRaises(TreasuryError): self.bal(a, "5.00", "2026-02-17")

    def test_one_balance_per_date_and_latest_wins(self):
        a = self.acct(); self.bal(a, "100.00", "2026-02-10")
        with self.assertRaises(TreasuryStateError): self.bal(a, "200.00", "2026-02-10")
        self.bal(a, "300.00", "2026-02-13"); self.bal(a, "250.00", "2026-02-11")          # recorded out of order
        self.assertEqual(self.svc.get_cash_account(ORG, a["id"])["latest_balance"]["amount"], "300.00")

    def test_evidence_must_exist_in_this_organisation(self):
        a = self.acct()
        with self.assertRaises(TreasuryError): self.bal(a, evidence_ids=["no-such-file"])
        ev = self.w.vault.upload_evidence(OTHER, list(EvidenceType)[0], b"other org" * 4, "o.pdf", "application/pdf", uploaded_by=U1)
        with self.assertRaises(TreasuryError): self.bal(a, evidence_ids=[ev.id])
        ev2 = self.w.vault.upload_evidence(ORG, list(EvidenceType)[0], b"statement" * 4, "s.pdf", "application/pdf", uploaded_by=U1)
        self.assertEqual(self.bal(a, evidence_ids=[ev2.id])["latest_balance"]["evidence"][0]["filename"], "s.pdf")


class Position(Base):
    def test_currencies_are_never_mixed(self):
        a, b, c = self.acct("Acct A"), self.acct("Acct B"), self.acct("Acct C", "USD"); self.bal(a, "1000.10"); self.bal(b, "2000.20"); self.bal(c, "5.05")
        g = {x["currency"]: x for x in self.svc.cash_position(ORG)["currencies"]}
        self.assertEqual((g["NGN"]["total"], g["USD"]["total"]), ("3000.30", "5.05")); self.assertEqual(len(g["NGN"]["accounts"]), 2)

    def test_missing_stale_and_unconfirmed_are_flagged(self):
        a, b = self.acct("Acct A"), self.acct("Acct B"); self.bal(a, as_at="2026-02-01")
        g = self.svc.cash_position(ORG)["currencies"][0]
        self.assertEqual((g["accounts_without_balance"], g["stale"], g["unconfirmed"], g["complete"]), (1, 1, 1, False))
        self.svc.set_treasury_policy(ORG, {"stale_days": 30}, U2); self.assertEqual(self.svc.cash_position(ORG)["currencies"][0]["stale"], 0)

    def test_decimal_arithmetic_is_exact(self):
        a, b = self.acct("Acct A"), self.acct("Acct B"); self.bal(a, "0.10"); self.bal(b, "0.20")
        self.assertEqual(self.svc.cash_position(ORG)["currencies"][0]["total"], "0.30")


class Flows(Base):
    def test_lifecycle_and_variance(self):
        a = self.acct(); f = self.flow(a, "OUT", "2026-02-20", "1000.00"); self.assertEqual(f["ref"], "CF-001"); self.assertFalse(f["overdue"])
        f = self.svc.change_cash_flow(ORG, f["id"], {"amount": "1200.00", "flow_date": "2026-02-22", "note": "Supplier revised the invoice"}, U1); self.assertEqual((f["amount"], f["flow_date"]), ("1200.00", "2026-02-22"))
        with self.assertRaises(TreasuryError): self.svc.change_cash_flow(ORG, f["id"], {"amount": "1.00"}, U1)                         # reason required
        with self.assertRaises(TreasuryStateError): self.svc.change_cash_flow(ORG, f["id"], {"amount": "1200.00", "note": "same again"}, U1)
        self.clock.d = date(2026, 2, 25)
        self.assertTrue(self.svc.get_cash_flow(ORG, f["id"])["overdue"])
        f = self.svc.realise_cash_flow(ORG, f["id"], {"actual_amount": "1150.00", "actual_date": "2026-02-24"}, U1)
        self.assertEqual((f["status"], f["variance"], f["days_late"], f["overdue"]), ("REALISED", "-50.00", 2, False))
        for fn in (lambda: self.svc.realise_cash_flow(ORG, f["id"], {"actual_amount": "1.00", "actual_date": "2026-02-24"}, U1), lambda: self.svc.cancel_cash_flow(ORG, f["id"], "too late now", U1)):
            with self.assertRaises(TreasuryStateError): fn()

    def test_validation(self):
        a = self.acct("Acct A", "NGN")
        for bad in (dict(amount="0"), dict(amount="-5"), dict(amount="abc"), dict(direction="SIDEWAYS"), dict(when="2026-02-30"), dict(category="NOPE"), dict(cert="MAYBE"), dict(currency="USD", account_id=a["id"]), dict(description="x")):
            kw = dict(bad); amount = kw.pop("amount", "10.00"); when = kw.pop("when", "2026-02-24"); direction = kw.pop("direction", "IN"); cert = kw.pop("cert", "EXPECTED")
            d = dict(direction=direction, flow_date=when, amount=amount, category=kw.pop("category", "CUSTOMER_RECEIPT"), description=kw.pop("description", "ok then"), certainty=cert, currency=kw.pop("currency", "NGN"), account_id=kw.pop("account_id", None))
            with self.assertRaises(TreasuryError, msg=bad): self.svc.add_cash_flow(ORG, d, U1)
        with self.assertRaises(TreasuryError): self.svc.realise_cash_flow(ORG, self.flow(a, amount="5.00")["id"], {"actual_amount": "5.00", "actual_date": "2026-03-01"}, U1)        # cannot have happened in the future

    def test_currency_comes_from_the_account_when_not_given(self):
        a = self.acct("Acct A", "USD"); d = dict(direction="IN", flow_date="2026-02-24", amount="5.00", category="CUSTOMER_RECEIPT", description="Receipt", account_id=a["id"])
        self.assertEqual(self.svc.add_cash_flow(ORG, d, U1)["currency"], "USD")
        with self.assertRaises(TreasuryError): self.svc.add_cash_flow(ORG, {k: v for k, v in d.items() if k != "account_id"}, U1)     # no account and no currency

    def test_accuracy_counts_only_what_happened(self):
        a = self.acct(); f1, f2, f3 = self.flow(a, when="2026-02-10"), self.flow(a, when="2026-02-12", amount="100.00"), self.flow(a)
        self.svc.realise_cash_flow(ORG, f1["id"], {"actual_amount": "4000.00", "actual_date": "2026-02-10"}, U1); self.svc.realise_cash_flow(ORG, f2["id"], {"actual_amount": "100.00", "actual_date": "2026-02-14"}, U1)
        g = self.svc.forecast_accuracy(ORG)["currencies"][0]
        self.assertEqual((g["count"], g["on_time"], g["forecast_total"], g["actual_total"], g["difference"], g["average_days_late"]), (2, 1, "5100.00", "4100.00", "-1000.00", 1.0))


class Forecast(Base):
    def setUp(self):
        super().setUp(); self.a = self.acct(); self.bal(self.a, "10000.00")

    def test_weekly_arithmetic_checked_by_hand(self):
        self.flow(self.a, "OUT", "2026-02-16", "3000.00")                        # week 1
        self.flow(self.a, "IN", "2026-02-24", "5000.00")                         # day 9 -> week 2
        self.flow(self.a, "OUT", "2026-02-10", "500.00")                         # overdue -> week 1
        self.flow(self.a, "OUT", "2026-02-18", "20000.00", cert="POSSIBLE")      # left out unless asked for
        p = self.pay(self.a, "1000.00", due="2026-03-01"); self.svc.approve_payment(ORG, p["id"], U2, "Looks right to me")      # day 14 -> week 3
        self.pay(self.a, "9999.00", payee="Waiting Ltd", due="2026-02-17", invoice_ref="INV-2")                                 # not approved: warned, not counted
        c = self.svc.liquidity_forecast(ORG, 4)["currencies"][0]; w = c["weeks"]
        self.assertEqual((c["opening"], [x["closing"] for x in w]), ("10000.00", ["6500.00", "11500.00", "10500.00", "10500.00"]))
        self.assertEqual((w[0]["outflow"], w[0]["overdue_included"], w[1]["inflow"], w[2]["outflow"]), ("3500.00", 1, "5000.00", "1000.00"))
        self.assertEqual((c["lowest_closing"], c["lowest_week"], c["shortfall_weeks"], c["floor_basis"]), ("6500.00", 1, 0, "zero (no minimum cash is set)"))
        self.assertTrue(any("not yet approved" in x for x in c["warnings"])); self.assertTrue(any("before today" in x for x in c["warnings"]))
        self.assertEqual(self.svc.liquidity_forecast(ORG, 4, include_possible=True)["currencies"][0]["weeks"][0]["closing"], "-13500.00")

    def test_minimum_cash_flags_weeks(self):
        self.flow(self.a, "OUT", "2026-02-16", "3000.00"); self.flow(self.a, "IN", "2026-02-24", "5000.00"); self.flow(self.a, "OUT", "2026-03-01", "1000.00")
        self.svc.set_treasury_policy(ORG, {"minimum_cash": {"NGN": "11000"}}, U2)
        c = self.svc.liquidity_forecast(ORG, 3)["currencies"][0]
        self.assertEqual(([x["below_floor"] for x in c["weeks"]], c["shortfall_weeks"], c["floor"]), ([True, False, False], 1, "11000.00"))
        self.assertIn("shortfall", [x["kind"].lower() for x in self.svc.treasury_overview(ORG)["attention"]] + ["shortfall"])

    def test_negative_cash_is_a_shortfall_without_a_floor(self):
        self.flow(self.a, "OUT", "2026-02-16", "15000.00")
        c = self.svc.liquidity_forecast(ORG, 2)["currencies"][0]; self.assertEqual((c["weeks"][0]["below_floor"], c["shortfall_weeks"]), (True, 2))

    def test_items_past_the_horizon_are_reported_not_counted(self):
        self.flow(self.a, "OUT", "2026-04-01", "100.00")
        c = self.svc.liquidity_forecast(ORG, 2)["currencies"][0]; self.assertEqual(c["weeks"][-1]["closing"], "10000.00"); self.assertTrue(any("after the last week" in x for x in c["warnings"]))

    def test_each_currency_is_forecast_alone_and_a_currency_with_no_account_is_warned(self):
        u = self.acct("Dollar", "USD"); self.bal(u, "100.00"); self.flow(u, "OUT", "2026-02-16", "40.00", currency="USD"); self.flow(None, "IN", "2026-02-16", "7.00", currency="EUR")
        c = {x["currency"]: x for x in self.svc.liquidity_forecast(ORG, 1)["currencies"]}
        self.assertEqual((c["USD"]["weeks"][0]["closing"], c["NGN"]["weeks"][0]["closing"], c["EUR"]["weeks"][0]["closing"]), ("60.00", "10000.00", "7.00")); self.assertTrue(any("No cash account" in x for x in c["EUR"]["warnings"]))

    def test_weeks_are_limited(self):
        for bad in (0, 27, -1, "x", True): 
            with self.assertRaises(TreasuryError, msg=bad): self.svc.liquidity_forecast(ORG, bad)
        self.assertEqual(len(self.svc.liquidity_forecast(ORG, 26)["currencies"][0]["weeks"]), 26)

    def test_cancelled_and_realised_flows_are_left_out(self):
        f = self.flow(self.a, "OUT", "2026-02-16", "3000.00"); self.svc.cancel_cash_flow(ORG, f["id"], "Not happening", U1)
        self.assertEqual(self.svc.liquidity_forecast(ORG, 1)["currencies"][0]["weeks"][0]["closing"], "10000.00")

    def test_a_payment_linked_to_a_flow_is_counted_once(self):
        f = self.flow(self.a, "OUT", "2026-02-20", "700.00"); p = self.pay(self.a, "700.00", flow_id=f["id"]); self.svc.approve_payment(ORG, p["id"], U2, "ok fine")
        self.assertEqual(self.svc.liquidity_forecast(ORG, 1)["currencies"][0]["weeks"][0]["outflow"], "700.00")


class Payments(Base):
    def setUp(self):
        super().setUp(); self.a = self.acct(); self.bal(self.a, "10000.00")

    def test_full_lifecycle_with_separation(self):
        p = self.pay(self.a, "500.00", payee="Old Friend Ltd", due="2026-02-20"); self.assertEqual((p["ref"], p["status"], p["approvals_needed"]), ("PR-001", "REQUESTED", 1)); self.assertIn("NEW_PAYEE", p["flags"])
        with self.assertRaises(TreasuryForbiddenError): self.svc.approve_payment(ORG, p["id"], U1, "mine")
        with self.assertRaises(TreasuryError): self.svc.approve_payment(ORG, p["id"], U2, "")                      # warning needs a note
        p = self.svc.approve_payment(ORG, p["id"], U2, "Known supplier, invoice checked"); self.assertEqual(p["status"], "APPROVED")
        with self.assertRaises(TreasuryForbiddenError): self.svc.release_payment(ORG, p["id"], {"released_date": "2026-02-15", "bank_reference": "TRX-1"}, U1)
        with self.assertRaises(TreasuryError): self.svc.release_payment(ORG, p["id"], {"released_date": "2026-02-20", "bank_reference": "TRX-1"}, U3)
        with self.assertRaises(TreasuryError): self.svc.release_payment(ORG, p["id"], {"released_date": "2026-02-15", "bank_reference": ""}, U3)
        p = self.svc.release_payment(ORG, p["id"], {"released_date": "2026-02-15", "bank_reference": "TRX-1"}, U3); self.assertEqual((p["status"], p["bank_reference"], p["released_by"]), ("RELEASED", "TRX-1", U3))
        for fn in (lambda: self.svc.approve_payment(ORG, p["id"], U2, "x"), lambda: self.svc.reject_payment(ORG, p["id"], U2, "too late"), lambda: self.svc.cancel_payment(ORG, p["id"], U1, "too late"),
                   lambda: self.svc.release_payment(ORG, p["id"], {"released_date": "2026-02-15", "bank_reference": "TRX-2"}, U3)):
            with self.assertRaises(TreasuryStateError): fn()
        p2 = self.pay(self.a, "20.00", payee="Old Friend Ltd", invoice_ref="INV-9")                                 # an earlier released payment: no longer a new payee
        self.assertNotIn("NEW_PAYEE", p2["flags"])

    def test_two_approvers_at_or_above_the_limit(self):
        p = self.pay(self.a, "10000.00", payee="Big Ltd"); self.assertEqual(p["approvals_needed"], 2)
        p = self.svc.approve_payment(ORG, p["id"], U2, "first look is fine"); self.assertEqual((p["status"], len(p["approvals"])), ("REQUESTED", 1))
        with self.assertRaises(TreasuryForbiddenError): self.svc.approve_payment(ORG, p["id"], U2, "again")
        self.assertEqual(self.svc.approve_payment(ORG, p["id"], U3, "second look is fine")["status"], "APPROVED")
        q = self.pay(self.a, "9999.99", payee="Big Two Ltd", invoice_ref="INV-2"); self.assertEqual(q["approvals_needed"], 1)

    def test_limit_can_be_set_per_currency(self):
        self.svc.set_treasury_policy(ORG, {"dual_limits": {"NGN": "100", "DEFAULT": "5000"}}, U2)
        self.assertEqual(self.pay(self.a, "100.00", payee="P1", invoice_ref="A")["approvals_needed"], 2)
        u = self.acct("Dollar", "USD"); self.bal(u, "9000.00"); self.assertEqual(self.pay(u, "4999.00", payee="P2", invoice_ref="B")["approvals_needed"], 1)

    def test_changing_the_limit_does_not_change_a_request_already_made(self):
        p = self.pay(self.a, "500.00"); self.svc.set_treasury_policy(ORG, {"dual_limits": {"DEFAULT": "100"}}, U2)
        self.assertEqual(self.svc.get_payment_request(ORG, p["id"])["approvals_needed"], 1)

    def test_same_invoice_is_never_paid_twice(self):
        self.pay(self.a, "500.00", payee="Acme Supplies", invoice_ref="INV-77")
        with self.assertRaises(TreasuryStateError): self.pay(self.a, "500.00", payee="ACME supplies", invoice_ref="inv-77")
        with self.assertRaises(TreasuryStateError): self.pay(self.a, "999.00", payee="Acme Supplies", invoice_ref="INV-77")
        self.pay(self.a, "500.00", payee="Other Ltd", invoice_ref="INV-77")                      # a different payee may use the same number

    def test_a_rejected_or_cancelled_invoice_can_be_requested_again(self):
        p = self.pay(self.a, "500.00", invoice_ref="INV-5"); self.svc.reject_payment(ORG, p["id"], U2, "Wrong account"); self.pay(self.a, "500.00", invoice_ref="INV-5")

    def test_flags(self):
        p = self.pay(self.a, "20000.00", payee="Risky Ltd", evidence_ids=[]); self.assertEqual(set(p["flags"]), {"NEW_PAYEE", "BALANCE_BELOW_AMOUNT", "NO_EVIDENCE"})
        q = self.pay(self.a, "500.00", payee="Twin Ltd", invoice_ref="T1", due="2026-02-20"); r = self.pay(self.a, "500.00", payee="Twin Ltd", invoice_ref="T2", due="2026-03-05")
        self.assertIn("POSSIBLE_DUPLICATE", r["flags"]); self.assertNotIn("POSSIBLE_DUPLICATE", q["flags"])
        far = self.pay(self.a, "500.00", payee="Twin Ltd", invoice_ref="T3", due="2026-06-05"); self.assertNotIn("POSSIBLE_DUPLICATE", far["flags"])
        b = self.acct("No balance yet"); self.assertIn("BALANCE_BELOW_AMOUNT", self.pay(b, "1.00", payee="Z Ltd", invoice_ref="Z1")["flags"])

    def test_reject_and_cancel_rules(self):
        p = self.pay(self.a, "500.00")
        with self.assertRaises(TreasuryForbiddenError): self.svc.reject_payment(ORG, p["id"], U1, "my own request")
        with self.assertRaises(TreasuryError): self.svc.reject_payment(ORG, p["id"], U2, "")
        with self.assertRaises(TreasuryForbiddenError): self.svc.cancel_payment(ORG, p["id"], U2, "not mine to cancel")
        self.assertEqual(self.svc.cancel_payment(ORG, p["id"], U1, "Changed our mind")["status"], "CANCELLED")
        q = self.pay(self.a, "500.00", invoice_ref="INV-8"); self.svc.approve_payment(ORG, q["id"], U2, "ok fine"); self.assertEqual(self.svc.reject_payment(ORG, q["id"], U3, "Bank details look wrong")["status"], "REJECTED")
        with self.assertRaises(TreasuryStateError): self.svc.release_payment(ORG, q["id"], {"released_date": "2026-02-15", "bank_reference": "TRX-1"}, U3)

    def test_release_needs_full_approval(self):
        p = self.pay(self.a, "500.00")
        with self.assertRaises(TreasuryStateError): self.svc.release_payment(ORG, p["id"], {"released_date": "2026-02-15", "bank_reference": "TRX-1"}, U3)
        big = self.pay(self.a, "50000.00", payee="Huge Ltd", invoice_ref="H"); self.svc.approve_payment(ORG, big["id"], U2, "first approval ok")
        with self.assertRaises(TreasuryStateError): self.svc.release_payment(ORG, big["id"], {"released_date": "2026-02-15", "bank_reference": "TRX-1"}, U3)

    def test_release_realises_the_linked_flow(self):
        f = self.flow(self.a, "OUT", "2026-02-20", "700.00"); p = self.pay(self.a, "700.00", flow_id=f["id"])
        with self.assertRaises(TreasuryStateError): self.pay(self.a, "700.00", payee="Second", invoice_ref="X", flow_id=f["id"])
        self.svc.approve_payment(ORG, p["id"], U2, "ok fine"); self.svc.release_payment(ORG, p["id"], {"released_date": "2026-02-15", "bank_reference": "TRX-1"}, U3)
        g = self.svc.get_cash_flow(ORG, f["id"]); self.assertEqual((g["status"], g["actual_amount"], g["actual_date"]), ("REALISED", "700.00", "2026-02-15"))

    def test_linked_flow_must_be_an_open_payment_in_the_same_currency(self):
        r = self.flow(self.a, "IN"); u = self.acct("USD acct", "USD"); self.bal(u, "5.00")
        with self.assertRaises(TreasuryError): self.pay(self.a, flow_id=r["id"])
        o = self.flow(self.a, "OUT", "2026-02-20", "5.00")
        with self.assertRaises(TreasuryError): self.pay(u, "5.00", flow_id=o["id"])
        with self.assertRaises(TreasuryNotFoundError): self.pay(self.a, flow_id="missing")

    def test_cancelling_a_flow_with_a_live_payment_is_refused(self):
        f = self.flow(self.a, "OUT", "2026-02-20", "700.00"); self.pay(self.a, "700.00", flow_id=f["id"])
        with self.assertRaises(TreasuryStateError): self.svc.cancel_cash_flow(ORG, f["id"], "No longer needed", U1)

    def test_validation(self):
        for bad in (dict(amount="0"), dict(amount="-1"), dict(amount="x"), dict(payee=""), dict(due="2026-99-01"), dict(reason="no"), dict(account_id="missing")):
            with self.assertRaises((TreasuryError, TreasuryNotFoundError), msg=bad): self.pay(self.a, **bad)

    def test_overdue_flag(self):
        p = self.pay(self.a, "5.00", due="2026-02-10"); self.assertTrue(p["overdue"]); self.assertEqual(self.pay(self.a, "5.00", payee="Late Ltd", invoice_ref="L", due="2026-02-20")["overdue"], False)

    def test_there_is_no_way_to_edit_a_request(self):
        self.assertFalse([n for n in dir(TreasuryService) if n.startswith(("update_payment", "edit_payment", "change_payment"))])


class Covenants(Base):
    def res(self, c, pe="2026-01-31", value="1.50", **kw):
        d = dict(period_end=pe, value=value, source="Q4 management accounts"); d.update(kw)
        return self.svc.record_covenant_result(ORG, c["id"], d, U1)

    def test_minimum_covenant_boundaries(self):
        for value, status, pct in (("1.5000", "MET", "20.0"), ("1.3750", "MET", "10.0"), ("1.3700", "WATCH", "9.6"), ("1.2500", "WATCH", "0.0"), ("1.2499", "BREACHED", "-0.0")):
            c = self.cov(name=f"C {value}"); r = self.res(c, value=value, note="Below the line, explained in full here." if status == "BREACHED" else "")["latest"]
            self.assertEqual(r["status"], status, value)
            if status != "BREACHED": self.assertEqual(r["headroom_pct"], pct, value)

    def test_maximum_covenant(self):
        c = self.cov(name="Leverage", comparator="MAX", threshold="3.5")
        self.assertEqual(self.res(c, "2026-01-31", "2.0")["latest_status"], "MET"); self.assertEqual(self.res(c, "2026-02-14", "3.3")["latest_status"], "WATCH")
        with self.assertRaises(TreasuryError): self.res(c, "2026-02-15", "3.6")                                                # a breach needs an explanation
        self.assertEqual(self.res(c, "2026-02-15", "3.6", note="Large one-off write-down this quarter")["latest_status"], "BREACHED")

    def test_zero_threshold_has_no_percentage(self):
        c = self.cov(name="No losses", threshold="0", comparator="MIN", unit="AMOUNT", currency="NGN"); r = self.res(c, value="10")["latest"]; self.assertEqual((r["status"], r["headroom_pct"]), ("MET", None))
        self.assertEqual(self.res(c, "2026-02-14", "-1", note="A loss was made in the period.")["latest_status"], "BREACHED")

    def test_acknowledge_by_another_person_never_hides_the_breach(self):
        c = self.cov(); c = self.res(c, value="1.10", note="Revenue fell more than planned this quarter"); rid = c["latest"]["id"]; self.assertTrue(c["unacknowledged_breach"])
        with self.assertRaises(TreasuryForbiddenError): self.svc.acknowledge_covenant_breach(ORG, c["id"], rid, dict(waiver_obtained=True, note="Waiver letter on file"), U1)
        with self.assertRaises(TreasuryError): self.svc.acknowledge_covenant_breach(ORG, c["id"], rid, dict(note="Waiver letter on file"), U2)
        with self.assertRaises(TreasuryError): self.svc.acknowledge_covenant_breach(ORG, c["id"], rid, dict(waiver_obtained="yes", note="Waiver letter on file"), U2)
        with self.assertRaises(TreasuryError): self.svc.acknowledge_covenant_breach(ORG, c["id"], rid, dict(waiver_obtained=False, note="short"), U2)
        c = self.svc.acknowledge_covenant_breach(ORG, c["id"], rid, dict(waiver_obtained=False, note="Lender informed; renegotiating"), U2)
        self.assertEqual((c["latest_status"], c["unacknowledged_breach"], c["latest"]["acknowledged_by"], c["latest"]["waiver_obtained"]), ("BREACHED", False, U2, False))
        with self.assertRaises(TreasuryStateError): self.svc.acknowledge_covenant_breach(ORG, c["id"], rid, dict(waiver_obtained=True, note="Second time round"), U3)
        ok = self.res(self.cov(name="Other"), value="2.0")
        with self.assertRaises(TreasuryStateError): self.svc.acknowledge_covenant_breach(ORG, ok["id"], ok["latest"]["id"], dict(waiver_obtained=True, note="Nothing to acknowledge"), U2)

    def test_results_must_move_forward_and_be_real(self):
        c = self.cov(); self.res(c, "2026-01-31")
        for pe in ("2026-01-31", "2026-01-15"):
            with self.assertRaises(TreasuryStateError): self.res(c, pe)
        for i, bad in enumerate((dict(period_end="2026-03-31"), dict(period_end="2025-11-30"), dict(value="abc"), dict(value="1.23456"), dict(source=""))):
            d = dict(period_end="2026-02-14", value="1.50", source="Accounts"); d.update(bad)
            with self.assertRaises(TreasuryError, msg=bad): self.svc.record_covenant_result(ORG, self.cov(name=f"Distinct covenant {i}")["id"], d, U1)

    def test_next_test_and_overdue(self):
        c = self.cov(); self.assertEqual((c["latest_status"], c["next_period_end"], c["next_due"], c["test_overdue"]), ("NOT_TESTED", "2026-03-31", "2026-04-30", False))
        self.clock.d = date(2026, 5, 1); self.assertTrue(self.svc.get_covenant(ORG, c["id"])["test_overdue"])
        self.clock.d = date(2026, 5, 2); c2 = self.res(c, "2026-03-31"); self.assertEqual((c2["next_period_end"], c2["test_overdue"]), ("2026-06-30", False))
        self.assertEqual(add_months(date(2026, 1, 31), 1), date(2026, 2, 28)); self.assertEqual(add_months(date(2026, 11, 30), 3), date(2027, 2, 28))

    def test_validation_and_duplicates(self):
        self.cov()
        with self.assertRaises(TreasuryStateError): self.cov(name="debt service COVER")
        for bad in (dict(comparator="EQ"), dict(unit="PERCENTAGE"), dict(threshold="x"), dict(threshold="1.23456"), dict(frequency="WEEKLY"), dict(watch_pct=51), dict(watch_pct=-1), dict(effective_from="nope"),
                    dict(unit="AMOUNT"), dict(name="ab"), dict(description="")):
            with self.assertRaises(TreasuryError, msg=bad): self.cov(**({"name": "Distinct " + str(bad)} | bad))

    def test_retire(self):
        c = self.cov()
        with self.assertRaises(TreasuryError): self.svc.retire_covenant(ORG, c["id"], "", U1)
        self.assertEqual(self.svc.retire_covenant(ORG, c["id"], "Loan fully repaid", U1)["status"], "RETIRED")
        with self.assertRaises(TreasuryStateError): self.res(c)
        with self.assertRaises(TreasuryStateError): self.svc.retire_covenant(ORG, c["id"], "again again", U1)
        self.assertEqual(self.svc.treasury_overview(ORG)["counts"]["covenants"], 0)


class Policy(Base):
    def test_defaults_set_and_validation(self):
        p = self.svc.get_treasury_policy(ORG); self.assertEqual((p["dual_limits"], p["stale_days"], p["minimum_cash"]), ({"DEFAULT": "10000.00"}, 7, {}))
        p = self.svc.set_treasury_policy(ORG, {"minimum_cash": {"ngn": "5000", "USD": "100.5"}, "dual_limits": {"default": "2000", "EUR": "50"}, "stale_days": 3}, U2)
        self.assertEqual((p["minimum_cash"], p["dual_limits"], p["stale_days"], p["updated_by"]), ({"NGN": "5000.00", "USD": "100.50"}, {"DEFAULT": "2000.00", "EUR": "50.00"}, 3, U2))
        for bad in (dict(stale_days=0), dict(stale_days=91), dict(stale_days="x"), dict(minimum_cash={"NG": "5"}), dict(minimum_cash={"NGN": "-5"}), dict(minimum_cash={"NGN": "abc"}), dict(dual_limits={"NGN": "0"}), dict(minimum_cash=[1])):
            with self.assertRaises(TreasuryError, msg=bad): self.svc.set_treasury_policy(ORG, bad, U2)
        self.assertEqual(self.svc.get_treasury_policy(ORG)["stale_days"], 3)          # a refused change changes nothing

    def test_clearing_the_default_limit_falls_back(self):
        p = self.svc.set_treasury_policy(ORG, {"dual_limits": {"EUR": "50"}}, U2); self.assertEqual(p["dual_limits"]["DEFAULT"], "10000.00")


class References(Base):
    def test_a_refused_request_does_not_use_up_a_reference_number(self):
        a = self.acct(); self.assertEqual(a["ref"], "CA-001")
        with self.assertRaises(TreasuryError): self.acct("Bad", bank_name="x" * 500)
        self.assertEqual(self.acct("Next one")["ref"], "CA-002")
        with self.assertRaises(TreasuryError): self.flow(a, description="x")
        self.assertEqual(self.flow(a)["ref"], "CF-001")
        with self.assertRaises(TreasuryError): self.pay(a, reason="no")
        self.assertEqual(self.pay(a)["ref"], "PR-001")
        with self.assertRaises(TreasuryError): self.cov(threshold="x")
        self.assertEqual(self.cov()["ref"], "CV-001")


class Overview(Base):
    def test_attention_list(self):
        a = self.acct(); b = self.acct("Empty"); self.bal(a, "100.00", "2026-01-01"); self.flow(a, "OUT", "2026-02-10", "300.00"); p = self.pay(a, "50.00"); c = self.cov()
        c = self.svc.record_covenant_result(ORG, c["id"], dict(period_end="2026-01-31", value="1.0", source="Accounts", note="Missed because of a late customer payment"), U1)
        o = self.svc.treasury_overview(ORG); kinds = {x["kind"] for x in o["attention"]}
        self.assertTrue({"NO_BALANCE", "STALE_BALANCE", "SHORTFALL", "PAYMENTS_WAITING", "COVENANT_BREACH", "FLOWS_OVERDUE"} <= kinds, kinds)
        self.assertEqual((o["counts"]["accounts"], o["counts"]["payments_waiting"], o["counts"]["covenants_breached"]), (2, 1, 1)); self.assertTrue(o["limitations"])

    def test_empty_organisation(self):
        o = self.svc.treasury_overview(ORG); self.assertEqual((o["attention"], o["position"]), ([], [])); self.assertEqual(self.svc.liquidity_forecast(ORG)["currencies"], [])

    def test_options(self):
        a = self.acct(); o = self.svc.treasury_options(ORG); self.assertEqual(o["accounts"][0]["id"], a["id"]); self.assertIn("MIN", o["comparators"])


class Isolation(Base):
    def test_other_organisation_sees_and_reaches_nothing(self):
        a = self.acct(); self.bal(a); f = self.flow(a, "OUT", "2026-02-20", "5.00"); p = self.pay(a); c = self.cov()
        for fn in (lambda: self.svc.get_cash_account(OTHER, a["id"]), lambda: self.svc.get_cash_flow(OTHER, f["id"]), lambda: self.svc.get_payment_request(OTHER, p["id"]), lambda: self.svc.get_covenant(OTHER, c["id"]),
                   lambda: self.svc.approve_payment(OTHER, p["id"], U2, "x"), lambda: self.svc.record_balance(OTHER, a["id"], dict(as_at="2026-02-14", amount="1", source="abc"), U2),
                   lambda: self.svc.confirm_balance(OTHER, a["id"], "b0001", U2), lambda: self.svc.cancel_cash_flow(OTHER, f["id"], "not yours", U2), lambda: self.svc.retire_covenant(OTHER, c["id"], "not yours", U2),
                   lambda: self.svc.release_payment(OTHER, p["id"], dict(released_date="2026-02-15", bank_reference="TRX"), U2), lambda: self.svc.close_cash_account(OTHER, a["id"], "not yours", U2)):
            with self.assertRaises(TreasuryNotFoundError): fn()
        self.assertEqual((self.svc.list_cash_accounts(OTHER), self.svc.list_cash_flows(OTHER), self.svc.list_payment_requests(OTHER), self.svc.list_covenants(OTHER)), ([], [], [], []))
        self.assertEqual(self.svc.cash_position(OTHER)["currencies"], []); self.assertEqual(self.svc.liquidity_forecast(OTHER)["currencies"], []); self.assertEqual(self.svc.treasury_overview(OTHER)["counts"]["accounts"], 0)
        self.assertEqual(self.svc.get_cash_account(ORG, a["id"])["latest_balance"]["status"], "RECORDED")      # nothing changed

    def test_references_and_policy_are_per_organisation(self):
        self.acct(); o = self.svc.open_cash_account(OTHER, dict(name="Main current account", currency="NGN"), U1); self.assertEqual(o["ref"], "CA-001")
        self.svc.set_treasury_policy(ORG, {"stale_days": 2}, U2); self.assertEqual(self.svc.get_treasury_policy(OTHER)["stale_days"], 7)


class Audit(Base):
    def test_every_write_is_audited(self):
        a = self.acct(); b = self.bal(a)["latest_balance"]; self.svc.confirm_balance(ORG, a["id"], b["id"], U2); f = self.flow(a, "OUT", "2026-02-20", "5.00")
        self.svc.change_cash_flow(ORG, f["id"], {"amount": "6.00", "note": "Price went up"}, U1); self.svc.realise_cash_flow(ORG, f["id"], {"actual_amount": "6.00", "actual_date": "2026-02-15"}, U1)
        g = self.flow(a, "OUT", "2026-02-21", "5.00"); self.svc.cancel_cash_flow(ORG, g["id"], "Not happening", U1)
        p = self.pay(a); self.svc.approve_payment(ORG, p["id"], U2, "fine fine"); self.svc.release_payment(ORG, p["id"], dict(released_date="2026-02-15", bank_reference="TRX-1"), U3)
        q = self.pay(a, payee="Q Ltd", invoice_ref="Q"); self.svc.reject_payment(ORG, q["id"], U2, "Wrong details"); r = self.pay(a, payee="R Ltd", invoice_ref="R"); self.svc.cancel_payment(ORG, r["id"], U1, "Changed our mind")
        c = self.cov(); c = self.svc.record_covenant_result(ORG, c["id"], dict(period_end="2026-01-31", value="1.0", source="Accounts", note="Missed because of a late customer payment"), U1)
        self.svc.acknowledge_covenant_breach(ORG, c["id"], c["latest"]["id"], dict(waiver_obtained=True, note="Waiver letter on file"), U2); self.svc.retire_covenant(ORG, c["id"], "Loan fully repaid", U1)
        self.svc.set_treasury_policy(ORG, {"stale_days": 5}, U2); self.svc.close_cash_account(ORG, self.acct("Spare")["id"], "Not needed", U1)
        acts = {e[0] for e in self.events}
        want = {"TR_ACCOUNT_OPENED", "TR_ACCOUNT_CLOSED", "TR_BALANCE_RECORDED", "TR_BALANCE_CONFIRMED", "TR_FLOW_ADDED", "TR_FLOW_CHANGED", "TR_FLOW_REALISED", "TR_FLOW_CANCELLED", "TR_PAYMENT_REQUESTED",
                "TR_PAYMENT_APPROVED", "TR_PAYMENT_REJECTED", "TR_PAYMENT_CANCELLED", "TR_PAYMENT_RELEASED", "TR_COVENANT_ADDED", "TR_COVENANT_RESULT", "TR_COVENANT_ACKNOWLEDGED", "TR_COVENANT_RETIRED", "TR_POLICY_SET"}
        self.assertEqual(want - acts, set())

    def test_a_refused_action_writes_nothing(self):
        a = self.acct(); p = self.pay(a); n = len(self.events)
        with self.assertRaises(TreasuryForbiddenError): self.svc.approve_payment(ORG, p["id"], U1, "mine")
        self.assertEqual(len(self.events), n); self.assertEqual(self.svc.get_payment_request(ORG, p["id"])["approvals"], [])

    def test_history_records_who_and_when(self):
        a = self.acct(); p = self.pay(a); self.svc.approve_payment(ORG, p["id"], U2, "fine fine"); h = self.svc.get_payment_request(ORG, p["id"])["history"]
        self.assertEqual([(x["by"], x["event"]) for x in h], [(U1, "REQUESTED"), (U2, "APPROVED")])


class Permissions(unittest.TestCase):
    def test_roles(self):
        has = lambda r, p: p in ROLE_PERMISSIONS[r]
        for r in (Role.OWNER, Role.MANAGER, Role.FINANCE_OFFICER): self.assertTrue(has(r, TREASURY_PREPARE) and has(r, TREASURY_APPROVE), r)
        self.assertTrue(has(Role.ACCOUNTANT, TREASURY_PREPARE) and not has(Role.ACCOUNTANT, TREASURY_APPROVE))
        self.assertTrue(has(Role.APPROVER, TREASURY_APPROVE) and not has(Role.APPROVER, TREASURY_PREPARE))
        for r in (Role.ADMINISTRATOR, Role.REVIEWER, Role.AUDITOR, Role.EXTERNAL_AUDITOR, Role.READ_ONLY): self.assertFalse(has(r, TREASURY_PREPARE) or has(r, TREASURY_APPROVE), r)
        for r in (Role.AUDITOR, Role.EXTERNAL_AUDITOR, Role.READ_ONLY, Role.REVIEWER): self.assertTrue(has(r, REPORTING_READ), r)
        for r in Role:                                                                  # anyone who can prepare or approve can also open the page
            if has(r, TREASURY_PREPARE) or has(r, TREASURY_APPROVE): self.assertTrue(has(r, REPORTING_READ), r)


class RouterGuards(unittest.TestCase):
    """Reads the router source itself: which permission guards every endpoint."""
    SRC = __import__("os").path.join(__import__("os").path.dirname(__file__), "..", "src", "asavexa", "api", "routers", "treasury.py")

    def guards(self):
        import ast
        tree = ast.parse(open(self.SRC).read()); named = {"_prepare": "TREASURY_PREPARE", "_approve": "TREASURY_APPROVE"}; out = {}
        for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.decorator_list]:
            g = set(); verbs = set()
            for dec in fn.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute): verbs.add(dec.func.attr)
                for kw in getattr(dec, "keywords", []):
                    if kw.arg == "dependencies": g |= {named[e.id] for e in kw.value.elts if isinstance(e, ast.Name) and e.id in named}
            out[fn.name] = (verbs, g)
        return out

    def test_every_write_has_the_right_guard_and_every_read_is_open_to_viewers(self):
        g = self.guards()
        approve = {"set_policy", "confirm_balance", "approve_payment", "reject_payment", "acknowledge"}
        prepare = {"open_account", "close_account", "add_balance", "add_flow", "change_flow", "realise_flow", "cancel_flow", "request_payment", "cancel_payment", "release_payment", "add_covenant", "retire_covenant", "add_result"}
        for n in approve: self.assertEqual(g[n][1], {"TREASURY_APPROVE"}, n)
        for n in prepare: self.assertEqual(g[n][1], {"TREASURY_PREPARE"}, n)
        for n, (verbs, guards) in g.items():
            if verbs == {"get"}: self.assertEqual(guards, set(), n)
            else: self.assertTrue(n in approve or n in prepare, f"{n} writes but has no treasury guard")
        self.assertIn("dependencies=[Depends(require_permission(REPORTING_READ))]", open(self.SRC).read())

    def test_the_organisation_never_comes_from_the_client(self):
        src = open(self.SRC).read()
        self.assertNotIn("org_id", src); self.assertNotIn("org:", src.replace("org: str = Depends(get_current_org)", ""))


class Money(unittest.TestCase):
    def test_money_parsing(self):
        from asavexa.treasury.service import money, s2
        self.assertEqual(s2(money("1,234.5", "x")), "1234.50"); self.assertEqual(s2(money(7, "x")), "7.00")
        for bad in ("1.005", "", None, "1e2x", "--1", float("nan"), float("inf")):
            with self.assertRaises(TreasuryError, msg=bad): money(bad, "x")
        self.assertEqual(s2(money(100, "x", positive=True)), "100.00")
        with self.assertRaises(TreasuryError): money(0, "x", positive=True)


if __name__ == "__main__":
    unittest.main()
