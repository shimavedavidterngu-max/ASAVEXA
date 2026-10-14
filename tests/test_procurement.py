"""Procurement chain: suppliers, contracts, purchase orders, deliveries, three-way invoice matching, payment link, supplier reviews, policy, isolation, audit."""
import ast
import os
import unittest
from datetime import date, datetime, timezone

from analysis_fixture import ORG, OTHER, World
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.permissions import PROCURE_APPROVE, PROCURE_PREPARE, REPORTING_READ, ROLE_PERMISSIONS
from asavexa.procurement.errors import ProcurementError, ProcurementForbiddenError, ProcurementNotFoundError, ProcurementStateError
from asavexa.procurement.service import ProcurementService, line_total
from asavexa.treasury.service import TreasuryService
from decimal import Decimal

U1, U2, U3, U4 = "user-1", "user-2", "user-3", "user-4"


class Clock:
    def __init__(self): self.d = date(2026, 2, 15)
    def __call__(self): return datetime(self.d.year, self.d.month, self.d.day, 9, tzinfo=timezone.utc)


LINES = [{"description": "Laptops", "qty": "10", "unit_price": "500.00"}, {"description": "Chargers", "qty": "10", "unit_price": "20.00"}]      # 5,200.00


class Base(unittest.TestCase):
    def setUp(self):
        self.w = World(); self.clock = Clock(); self.events = []
        self.svc = ProcurementService(self.w.store, log=lambda *a: self.events.append(a), now=self.clock)
        self.tre = TreasuryService(self.w.store, self.w.vault, now=self.clock)

    def sup(self, name="Acme Supplies", approve=True, **kw):
        d = dict(name=name, category="GOODS", country="Nigeria", contact="sales@acme.test", related_party=False); d.update(kw)
        s = self.svc.register_supplier(ORG, d, U1)
        return self.svc.approve_supplier(ORG, s["id"], U2) if approve and False else (self.svc.approve_supplier(ORG, s["id"], U2, "ok fine") if approve else s)

    def contract(self, s, ceiling="10000.00", start="2026-01-01", end="2026-12-31", approve=True, cur="NGN", **kw):
        d = dict(supplier_id=s["id"], title="Supply agreement", currency=cur, ceiling=ceiling, start_date=start, end_date=end); d.update(kw)
        c = self.svc.draft_contract(ORG, d, U1)
        return self.svc.approve_contract(ORG, c["id"], U2) if approve else c

    def order(self, s, lines=None, approve=True, actor=U1, cur="NGN", contract=None, **kw):
        d = dict(supplier_id=s["id"], currency=cur, expected_date="2026-02-28", purpose="Office equipment", lines=lines or [dict(l) for l in LINES])
        if contract: d["contract_id"] = contract["id"]
        d.update(kw)
        o = self.svc.raise_purchase_order(ORG, d, actor)
        return self.svc.approve_purchase_order(ORG, o["id"], U2, "ok") if approve else o

    def receive(self, o, lines=None, actor=U3, when="2026-02-15"):
        return self.svc.record_delivery(ORG, o["id"], dict(received_date=when, lines=lines if lines is not None else [{"line": 1, "qty": "10"}, {"line": 2, "qty": "10"}]), actor)

    def invoice(self, o, lines=None, number="INV-100", actor=U1, **kw):
        d = dict(invoice_number=number, invoice_date="2026-02-15", due_date="2026-03-21", lines=lines if lines is not None else [{"line": 1, "qty": "10", "unit_price": "500.00"}, {"line": 2, "qty": "10", "unit_price": "20.00"}]); d.update(kw)
        return self.svc.record_invoice(ORG, o["id"], d, actor)

    def full(self):
        s = self.sup(); o = self.order(s); self.receive(o); return s, o


class Policy(Base):
    def test_defaults_set_and_validation(self):
        p = self.svc.get_procurement_policy(ORG); self.assertEqual((p["tolerance_pct"], p["dual_limits"], p["warning_days"]), ("2", {"DEFAULT": "10000.00"}, 60))
        p = self.svc.set_procurement_policy(ORG, {"tolerance_pct": "5", "dual_limits": {"default": "500", "usd": "50"}, "warning_days": 30}, U2)
        self.assertEqual((p["tolerance_pct"], p["dual_limits"], p["warning_days"], p["updated_by"]), ("5", {"DEFAULT": "500.00", "USD": "50.00"}, 30, U2))
        self.assertEqual(self.svc.set_procurement_policy(ORG, {"tolerance_pct": "0"}, U2)["tolerance_pct"], "0"); self.assertEqual(self.svc.set_procurement_policy(ORG, {"tolerance_pct": "2.5"}, U2)["tolerance_pct"], "2.5")
        for bad in (dict(tolerance_pct="21"), dict(tolerance_pct="x"), dict(tolerance_pct="-1"), dict(tolerance_pct="1.25"), dict(warning_days=0), dict(warning_days=366), dict(dual_limits={"NGN": "0"}), dict(dual_limits={"NG": "5"}), dict(dual_limits=[1])):
            with self.assertRaises(ProcurementError, msg=bad): self.svc.set_procurement_policy(ORG, bad, U2)
        self.assertEqual(self.svc.get_procurement_policy(ORG)["tolerance_pct"], "2.5")


class Suppliers(Base):
    def test_register_and_approve_by_another_person(self):
        s = self.sup(approve=False); self.assertEqual((s["ref"], s["status"]), ("SU-001", "PENDING"))
        with self.assertRaises(ProcurementForbiddenError): self.svc.approve_supplier(ORG, s["id"], U1)
        s = self.svc.approve_supplier(ORG, s["id"], U2); self.assertEqual((s["status"], s["approved_by"]), ("ACTIVE", U2))
        with self.assertRaises(ProcurementStateError): self.svc.approve_supplier(ORG, s["id"], U3)

    def test_validation_and_duplicates(self):
        self.sup()
        with self.assertRaises(ProcurementStateError): self.sup("ACME supplies")
        for bad in (dict(name="x"), dict(category="NOPE"), dict(related_party=None), dict(related_party="no"), dict(related_party=True), dict(contact="x" * 300)):
            with self.assertRaises(ProcurementError, msg=bad): self.sup(**{"name": "Other Ltd", "approve": False, **bad})

    def test_a_connection_must_be_described_and_the_approver_must_say_why_they_accept_it(self):
        s = self.sup("Cousin Ltd", approve=False, related_party=True, related_party_note="Owned by the finance manager's cousin")
        self.assertTrue(s["related_party"])
        with self.assertRaises(ProcurementError): self.svc.approve_supplier(ORG, s["id"], U2, "")
        self.assertEqual(self.svc.approve_supplier(ORG, s["id"], U2, "Reviewed; manager takes no part in buying")["status"], "ACTIVE")

    def test_suspend_and_reinstate_by_a_different_person(self):
        s = self.sup()
        with self.assertRaises(ProcurementError): self.svc.suspend_supplier(ORG, s["id"], "", U2)
        self.assertEqual(self.svc.suspend_supplier(ORG, s["id"], "Failed an inspection", U2)["status"], "SUSPENDED")
        with self.assertRaises(ProcurementStateError): self.svc.suspend_supplier(ORG, s["id"], "again again", U2)
        with self.assertRaises(ProcurementForbiddenError): self.svc.reinstate_supplier(ORG, s["id"], "All fixed now", U2)
        self.assertEqual(self.svc.reinstate_supplier(ORG, s["id"], "All fixed now", U3)["status"], "ACTIVE")
        with self.assertRaises(ProcurementStateError): self.svc.reinstate_supplier(ORG, s["id"], "All fixed now", U3)

    def test_only_an_approved_supplier_can_be_ordered_from_or_contracted(self):
        p = self.sup("Pending Ltd", approve=False)
        with self.assertRaises(ProcurementStateError): self.order(p)
        with self.assertRaises(ProcurementStateError): self.contract(p)
        a = self.sup(); self.svc.suspend_supplier(ORG, a["id"], "Under investigation", U2)
        with self.assertRaises(ProcurementStateError): self.order(a)

    def test_suspending_stops_an_order_waiting_for_approval(self):
        s = self.sup(); o = self.order(s, approve=False); self.svc.suspend_supplier(ORG, s["id"], "Under investigation", U3)
        with self.assertRaises(ProcurementStateError): self.svc.approve_purchase_order(ORG, o["id"], U2, "ok")

    def test_supplier_summary(self):
        s, o = self.full(); self.assertTrue(self.svc.get_supplier(ORG, s["id"])["needs_review"]); i = self.invoice(o); self.svc.approve_invoice(ORG, i["id"], U2)
        v = self.svc.get_supplier(ORG, s["id"]); self.assertEqual((v["orders"], v["deliveries"], v["invoices"], v["approved_spend"]), (1, 1, 1, {"NGN": "5200.00"}))


class Contracts(Base):
    def test_draft_approve_and_view(self):
        s = self.sup(); c = self.contract(s, approve=False); self.assertEqual((c["ref"], c["status"], c["state"], c["remaining"]), ("CT-001", "PENDING", "IN_FORCE", "10000.00"))
        with self.assertRaises(ProcurementForbiddenError): self.svc.approve_contract(ORG, c["id"], U1)
        c = self.svc.approve_contract(ORG, c["id"], U2); self.assertEqual((c["status"], c["days_left"]), ("ACTIVE", 319))

    def test_validation(self):
        s = self.sup()
        for bad in (dict(end="2025-12-31"), dict(end="2026-01-01"), dict(ceiling="0"), dict(ceiling="x"), dict(cur="N"), dict(start="nope"), dict(title="ab")):
            with self.assertRaises(ProcurementError, msg=bad): self.contract(s, approve=False, **({"title": bad["title"]} if "title" in bad else {k: v for k, v in bad.items()}))
        with self.assertRaises(ProcurementNotFoundError): self.svc.draft_contract(ORG, dict(supplier_id="nope", title="Agreement", currency="NGN", ceiling="1", start_date="2026-01-01", end_date="2026-12-31"), U1)

    def test_cannot_approve_an_ended_contract(self):
        c = self.contract(self.sup(), start="2025-01-01", end="2025-12-31", approve=False)
        with self.assertRaises(ProcurementStateError): self.svc.approve_contract(ORG, c["id"], U2)

    def test_orders_must_fit_the_contract(self):
        s = self.sup(); c = self.contract(s, ceiling="6000.00")
        o1 = self.order(s, contract=c); v = self.svc.get_contract(ORG, c["id"]); self.assertEqual((v["committed"], v["remaining"]), ("5200.00", "800.00"))
        o2 = self.order(s, approve=False, contract=c, lines=[{"description": "More", "qty": "1", "unit_price": "800.01"}])
        with self.assertRaises(ProcurementStateError) as e: self.svc.approve_purchase_order(ORG, o2["id"], U2, "ok")
        self.assertIn("ceiling", str(e.exception))
        o3 = self.order(s, contract=c, lines=[{"description": "Exactly the rest", "qty": "1", "unit_price": "800.00"}])
        self.assertEqual(self.svc.get_contract(ORG, c["id"])["remaining"], "0.00"); self.assertEqual(o3["status"], "APPROVED")

    def test_order_against_wrong_contract_is_refused(self):
        s, t = self.sup(), self.sup("Other Ltd"); c = self.contract(s)
        for kw in (dict(contract=c, cur="USD"),):
            with self.assertRaises(ProcurementError): self.order(s, approve=False, **kw)
        with self.assertRaises(ProcurementError): self.order(t, approve=False, contract=c)                          # another supplier's contract
        with self.assertRaises(ProcurementError): self.order(s, approve=False, contract=self.contract(s, approve=False))   # not approved
        old = self.contract(s, start="2025-01-01", end="2026-02-20"); self.clock.d = date(2026, 3, 1)
        with self.assertRaises(ProcurementError): self.order(s, approve=False, contract=old, expected_date="2026-03-10")

    def test_expiring_soon_and_terminate(self):
        c = self.contract(self.sup(), end="2026-04-01"); self.assertTrue(c["expiring_soon"]); self.assertFalse(self.contract(self.sup("Later Ltd"), end="2026-12-01")["expiring_soon"])
        with self.assertRaises(ProcurementError): self.svc.terminate_contract(ORG, c["id"], "", U2)
        self.assertEqual(self.svc.terminate_contract(ORG, c["id"], "Supplier closed down", U2)["status"], "TERMINATED")
        with self.assertRaises(ProcurementStateError): self.svc.terminate_contract(ORG, c["id"], "again again", U2)
        s = self.sup("Third Ltd")
        with self.assertRaises(ProcurementError): self.order(s, approve=False, contract=c)

    def test_a_ceiling_counts_only_approved_or_closed_orders(self):
        s = self.sup(); c = self.contract(s, ceiling="6000.00"); self.order(s, approve=False, contract=c); o = self.order(s, approve=False, contract=c)
        self.assertEqual(self.svc.get_contract(ORG, c["id"])["committed"], "0.00"); self.svc.reject_purchase_order(ORG, o["id"], "Not needed now", U2); self.assertEqual(self.svc.get_contract(ORG, c["id"])["committed"], "0.00")


class Orders(Base):
    def test_totals_are_exact_and_rounded_half_up_per_line(self):
        self.assertEqual(line_total(Decimal("1.5"), Decimal("0.15")), Decimal("0.23")); self.assertEqual(line_total(Decimal("0.333"), Decimal("10.00")), Decimal("3.33"))
        o = self.order(self.sup(), lines=[{"description": "Odd one", "qty": "1.5", "unit_price": "0.15"}, {"description": "Another", "qty": "3", "unit_price": "0.10"}], approve=False)
        self.assertEqual([l["total"] for l in o["lines"]], ["0.23", "0.30"]); self.assertEqual(o["total"], "0.53")

    def test_lifecycle_and_separation(self):
        s = self.sup(); o = self.order(s, approve=False); self.assertEqual((o["ref"], o["status"], o["approvals_needed"], o["total"]), ("PO-001", "REQUESTED", 1, "5200.00"))
        with self.assertRaises(ProcurementForbiddenError): self.svc.approve_purchase_order(ORG, o["id"], U1)
        with self.assertRaises(ProcurementForbiddenError): self.svc.reject_purchase_order(ORG, o["id"], "my own order", U1)
        with self.assertRaises(ProcurementForbiddenError): self.svc.cancel_purchase_order(ORG, o["id"], "not mine", U2)
        o = self.svc.approve_purchase_order(ORG, o["id"], U2); self.assertEqual(o["status"], "APPROVED")
        for fn in (lambda: self.svc.approve_purchase_order(ORG, o["id"], U3), lambda: self.svc.reject_purchase_order(ORG, o["id"], "too late now", U3)):
            with self.assertRaises(ProcurementStateError): fn()

    def test_two_approvers_at_or_above_the_limit(self):
        self.svc.set_procurement_policy(ORG, {"dual_limits": {"DEFAULT": "5200"}}, U2); s = self.sup(); o = self.order(s, approve=False); self.assertEqual(o["approvals_needed"], 2)
        o = self.svc.approve_purchase_order(ORG, o["id"], U2); self.assertEqual((o["status"], len(o["approvals"])), ("REQUESTED", 1))
        with self.assertRaises(ProcurementForbiddenError): self.svc.approve_purchase_order(ORG, o["id"], U2)
        self.assertEqual(self.svc.approve_purchase_order(ORG, o["id"], U3)["status"], "APPROVED")
        self.svc.set_procurement_policy(ORG, {"dual_limits": {"DEFAULT": "5200.01"}}, U2); self.assertEqual(self.order(s, approve=False)["approvals_needed"], 1)

    def test_validation(self):
        s = self.sup(); good = dict(supplier_id=s["id"], currency="NGN", expected_date="2026-02-28", purpose="Office equipment", lines=[dict(LINES[0])])
        bad_lines = [[], None, "x", [{"description": "a", "qty": "1", "unit_price": "1"}], [{"description": "Thing", "qty": "0", "unit_price": "1"}], [{"description": "Thing", "qty": "1.0001", "unit_price": "1"}],
                     [{"description": "Thing", "qty": "1", "unit_price": "1.234"}], [{"description": "Thing", "qty": "1", "unit_price": "-1"}], [{"description": "Thing", "qty": "x", "unit_price": "1"}], ["not a line"],
                     [{"description": "Thing", "qty": "1", "unit_price": "1"}] * 51]
        for bl in bad_lines:
            with self.assertRaises(ProcurementError, msg=str(bl)[:60]): self.svc.raise_purchase_order(ORG, {**good, "lines": bl}, U1)
        for bad in (dict(expected_date="2026-02-10"), dict(expected_date="soon"), dict(currency="N"), dict(purpose="no"), dict(supplier_id="missing")):
            with self.assertRaises((ProcurementError, ProcurementNotFoundError), msg=bad): self.svc.raise_purchase_order(ORG, {**good, **bad}, U1)
        self.assertEqual(self.svc.raise_purchase_order(ORG, {**good, "expected_date": "2026-02-14"}, U1)["status"], "REQUESTED")        # yesterday is tolerated (time zones)

    def test_cancel_close_rules(self):
        s = self.sup(); o = self.order(s)
        with self.assertRaises(ProcurementError): self.svc.cancel_purchase_order(ORG, o["id"], "", U1)
        p = self.order(s); self.assertEqual(self.svc.cancel_purchase_order(ORG, p["id"], "Plans changed", U1)["status"], "CANCELLED")
        self.receive(o)
        with self.assertRaises(ProcurementStateError): self.svc.cancel_purchase_order(ORG, o["id"], "Plans changed", U1)
        i = self.invoice(o)
        with self.assertRaises(ProcurementStateError): self.svc.close_purchase_order(ORG, o["id"], "All done here", U1)           # an invoice still needs a decision
        self.svc.approve_invoice(ORG, i["id"], U2)
        self.assertEqual(self.svc.close_purchase_order(ORG, o["id"], "All done here", U1)["status"], "CLOSED")
        with self.assertRaises(ProcurementStateError): self.svc.close_purchase_order(ORG, o["id"], "All done here", U1)
        with self.assertRaises(ProcurementStateError): self.receive(o)

    def test_chain_view(self):
        s, o = self.full(); self.invoice(o); v = self.svc.get_purchase_order(ORG, o["id"])
        self.assertEqual((len(v["deliveries"]), len(v["invoices"]), v["fulfilment"]), (1, 1, "RECEIVED")); self.assertEqual(v["lines"][0]["invoiced"], "10.000")
        self.assertEqual([x["ref"] for x in self.svc.list_purchase_orders(ORG, supplier_id=s["id"])], ["PO-001"]); self.assertEqual(self.svc.list_purchase_orders(ORG, status="REQUESTED"), [])


class Deliveries(Base):
    def test_partial_then_complete(self):
        s = self.sup(); o = self.order(s); d = self.receive(o, [{"line": 1, "qty": "4"}]); self.assertEqual(d["ref"], "DL-001")
        v = self.svc.get_purchase_order(ORG, o["id"]); self.assertEqual((v["fulfilment"], v["lines"][0]["received"], v["lines"][0]["outstanding"]), ("PARTLY_RECEIVED", "4.000", "6.000"))
        with self.assertRaises(ProcurementError) as e: self.receive(o, [{"line": 1, "qty": "6.001"}])
        self.assertIn("only 6.000 is still outstanding", str(e.exception))
        self.receive(o, [{"line": 1, "qty": "6"}, {"line": 2, "qty": "10"}]); self.assertEqual(self.svc.get_purchase_order(ORG, o["id"])["fulfilment"], "RECEIVED")
        with self.assertRaises(ProcurementError): self.receive(o, [{"line": 1, "qty": "0.001"}])

    def test_who_and_what(self):
        o = self.order(self.sup())
        with self.assertRaises(ProcurementForbiddenError): self.receive(o, actor=U1)
        for bad in ([], [{"line": 9, "qty": "1"}], [{"line": 1, "qty": "1"}, {"line": 1, "qty": "1"}], [{"line": "x", "qty": "1"}], [{"line": 1, "qty": "0"}], [{"line": 1, "qty": "-1"}]):
            with self.assertRaises(ProcurementError, msg=bad): self.receive(o, bad)
        with self.assertRaises(ProcurementError): self.svc.record_delivery(ORG, o["id"], dict(received_date="2026-02-15", lines=None), U3)
        with self.assertRaises(ProcurementError): self.receive(o, when="2026-02-17")
        with self.assertRaises(ProcurementError): self.receive(o, when="bad")
        with self.assertRaises(ProcurementStateError): self.receive(self.order(self.sup("Waiting Ltd"), approve=False))
        self.assertEqual(self.svc.list_deliveries(ORG), []); self.assertEqual(self.receive(o, [{"line": 2, "qty": "1"}], when="2026-02-16")["lines"][0]["qty"], "1.000")

    def test_overdue_flag_until_fully_received(self):
        o = self.order(self.sup()); self.clock.d = date(2026, 3, 5); self.assertTrue(self.svc.get_purchase_order(ORG, o["id"])["overdue"])
        self.receive(o, when="2026-03-04"); self.assertFalse(self.svc.get_purchase_order(ORG, o["id"])["overdue"])


class Invoices(Base):
    def test_clean_match_then_approval_by_another_person(self):
        s, o = self.full(); i = self.invoice(o); self.assertEqual((i["ref"], i["status"], i["flags"], i["total"]), ("IV-001", "MATCHED", [], "5200.00"))
        with self.assertRaises(ProcurementForbiddenError): self.svc.approve_invoice(ORG, i["id"], U1)
        with self.assertRaises(ProcurementForbiddenError): self.svc.reject_invoice(ORG, i["id"], "my own invoice", U1)
        i = self.svc.approve_invoice(ORG, i["id"], U2); self.assertEqual((i["status"], i["decided_by"], i["override_note"]), ("APPROVED", U2, None))
        with self.assertRaises(ProcurementStateError): self.svc.approve_invoice(ORG, i["id"], U3)

    def test_price_tolerance_boundary(self):
        s, o = self.full()
        ok = self.invoice(o, [{"line": 1, "qty": "10", "unit_price": "510.00"}], "A1"); self.assertEqual(ok["flags"], [])                      # exactly 2% above
        self.svc.reject_invoice(ORG, ok["id"], "Testing the boundary", U2)
        high = self.invoice(o, [{"line": 1, "qty": "10", "unit_price": "510.01"}], "A2"); self.assertEqual((high["status"], high["flags"]), ("EXCEPTION", ["PRICE_ABOVE_ORDER"]))
        self.svc.reject_invoice(ORG, high["id"], "Testing the boundary", U2); self.svc.set_procurement_policy(ORG, {"tolerance_pct": "0"}, U2)
        self.assertEqual(self.invoice(o, [{"line": 1, "qty": "10", "unit_price": "500.01"}], "A3")["flags"], ["PRICE_ABOVE_ORDER"])
        self.assertEqual(self.invoice(o, [{"line": 2, "qty": "10", "unit_price": "19.00"}], "A4")["flags"], [])                                    # cheaper is fine

    def test_cannot_be_invoiced_for_more_than_was_received(self):
        s = self.sup(); o = self.order(s); self.receive(o, [{"line": 1, "qty": "6"}])
        a = self.invoice(o, [{"line": 1, "qty": "6", "unit_price": "500.00"}], "B1"); self.assertEqual(a["flags"], [])
        b = self.invoice(o, [{"line": 1, "qty": "1", "unit_price": "500.00"}], "B2"); self.assertEqual(b["flags"], ["NOT_YET_RECEIVED"])        # cumulative, not per invoice
        c = self.invoice(o, [{"line": 2, "qty": "1", "unit_price": "20.00"}], "B3"); self.assertEqual(c["flags"], ["NOT_YET_RECEIVED"])           # nothing received on line 2
        self.svc.reject_invoice(ORG, a["id"], "Replaced by a corrected one", U2); self.assertEqual(self.invoice(o, [{"line": 1, "qty": "5", "unit_price": "500.00"}], "B4")["flags"], [])   # a rejected invoice frees its quantity

    def test_exceptions_need_a_written_override_from_another_person(self):
        s = self.sup(); o = self.order(s); i = self.invoice(o); self.assertEqual(i["status"], "EXCEPTION")
        with self.assertRaises(ProcurementError): self.svc.approve_invoice(ORG, i["id"], U2, "")
        with self.assertRaises(ProcurementError): self.svc.approve_invoice(ORG, i["id"], U2, "short")
        with self.assertRaises(ProcurementForbiddenError): self.svc.approve_invoice(ORG, i["id"], U1, "Goods arrived late but fine")
        i = self.svc.approve_invoice(ORG, i["id"], U2, "Goods arrived yesterday, receipt not yet entered"); self.assertEqual((i["status"], i["flags"], i["override_note"][:5]), ("APPROVED", ["NOT_YET_RECEIVED"], "Goods"))
        self.assertIn("APPROVED_WITH_OVERRIDE", [h["event"] for h in i["history"]])

    def test_duplicate_invoice_numbers(self):
        s, o = self.full(); a = self.invoice(o, number="INV-9")
        with self.assertRaises(ProcurementStateError): self.invoice(o, number="inv-9")
        t = self.sup("Beta Ltd"); o2 = self.order(t); self.receive(o2); self.assertEqual(self.invoice(o2, number="INV-9")["status"], "MATCHED")      # another supplier may use the same number
        self.svc.reject_invoice(ORG, a["id"], "Wrong supplier name", U2); self.assertEqual(self.invoice(o, number="INV-9")["status"], "MATCHED")

    def test_validation(self):
        s, o = self.full()
        for bad in (dict(number=""), dict(invoice_date="2026-02-17"), dict(invoice_date="bad"), dict(due_date="2026-02-01"), dict(currency="N"), dict(lines=[]), dict(lines=[{"line": 5, "qty": "1", "unit_price": "1"}]),
                    dict(lines=[{"line": 1, "qty": "1", "unit_price": "1"}, {"line": 1, "qty": "1", "unit_price": "1"}]), dict(lines=[{"line": 1, "qty": "0", "unit_price": "1"}]), dict(lines=[{"line": 1, "qty": "1", "unit_price": "x"}])):
            kw = dict(bad); num = kw.pop("number", "V-1")
            with self.assertRaises(ProcurementError, msg=bad): self.invoice(o, number=num, **kw)
        self.assertEqual(self.svc.list_invoices(ORG), [])

    def test_a_different_currency_is_flagged_and_cannot_be_approved(self):
        s, o = self.full(); i = self.invoice(o, number="C1", currency="USD"); self.assertEqual(i["flags"], ["CURRENCY_DIFFERS"])
        with self.assertRaises(ProcurementStateError): self.svc.approve_invoice(ORG, i["id"], U2, "I accept this difference")
        self.assertEqual(self.svc.reject_invoice(ORG, i["id"], "Ask for a corrected invoice", U2)["status"], "REJECTED")

    def test_invoice_only_against_an_approved_order(self):
        o = self.order(self.sup(), approve=False)
        with self.assertRaises(ProcurementStateError): self.invoice(o)

    def test_overdue_after_due_date_until_paid(self):
        s, o = self.full(); i = self.svc.approve_invoice(ORG, self.invoice(o)["id"], U2); self.assertFalse(i["overdue"]); self.clock.d = date(2026, 3, 22)
        self.assertTrue(self.svc.get_invoice(ORG, i["id"])["overdue"]); p = self.svc.mark_invoice_paid(ORG, i["id"], dict(paid_date="2026-03-22", bank_reference="TRX-77"), U3); self.assertFalse(p["overdue"])


class Payment(Base):
    def approved(self):
        s, o = self.full(); return s, self.svc.approve_invoice(ORG, self.invoice(o)["id"], U2)

    def released(self, payee="Acme Supplies", amount="5200.00", cur="NGN", release=True, org=ORG):
        a = self.tre.open_cash_account(org, dict(name=f"Main {payee} {amount} {cur}", currency=cur), U1); self.tre.record_balance(org, a["id"], dict(as_at="2026-02-14", amount="99999.00", source="Statement"), U1)
        p = self.tre.request_payment(org, dict(account_id=a["id"], payee=payee, amount=amount, due_date="2026-03-01", reason="Invoice payment", invoice_ref=f"R-{payee}-{amount}"), U1)
        self.tre.approve_payment(org, p["id"], U2, "checked and fine")
        return self.tre.release_payment(org, p["id"], dict(released_date="2026-02-15", bank_reference="BANK-1"), U3) if release else p

    def test_manual_payment_record(self):
        s, i = self.approved()
        with self.assertRaises(ProcurementError): self.svc.mark_invoice_paid(ORG, i["id"], dict(paid_date="2026-02-16", bank_reference=""), U3)
        with self.assertRaises(ProcurementError): self.svc.mark_invoice_paid(ORG, i["id"], dict(paid_date="2026-02-20", bank_reference="TRX-1"), U3)
        p = self.svc.mark_invoice_paid(ORG, i["id"], dict(paid_date="2026-02-15", bank_reference="TRX-1"), U3); self.assertEqual((p["status"], p["payment"]["bank_reference"], p["payment"]["marked_by"]), ("PAID", "TRX-1", U3))
        with self.assertRaises(ProcurementStateError): self.svc.mark_invoice_paid(ORG, i["id"], dict(paid_date="2026-02-15", bank_reference="TRX-2"), U3)

    def test_only_an_approved_invoice_can_be_paid(self):
        s, o = self.full(); i = self.invoice(o)
        with self.assertRaises(ProcurementStateError): self.svc.mark_invoice_paid(ORG, i["id"], dict(paid_date="2026-02-15", bank_reference="TRX-1"), U3)

    def test_linked_to_a_released_treasury_payment(self):
        s, i = self.approved(); t = self.released()
        p = self.svc.mark_invoice_paid(ORG, i["id"], dict(treasury_payment_id=t["id"]), U3)
        self.assertEqual((p["status"], p["payment"]["treasury_payment_id"], p["payment"]["treasury_ref"], p["payment"]["bank_reference"], p["payment"]["paid_date"]), ("PAID", t["id"], t["ref"], "BANK-1", "2026-02-15"))

    def test_a_treasury_payment_must_match(self):
        s, i = self.approved()
        for kw, exc in ((dict(payee="Someone Else"), ProcurementError), (dict(amount="5200.01"), ProcurementError), (dict(release=False), ProcurementStateError)):
            t = self.released(**kw)
            with self.assertRaises(exc, msg=kw): self.svc.mark_invoice_paid(ORG, i["id"], dict(treasury_payment_id=t["id"]), U3)
        with self.assertRaises(ProcurementNotFoundError): self.svc.mark_invoice_paid(ORG, i["id"], dict(treasury_payment_id="missing"), U3)
        other = self.released(org=OTHER)                                                          # another company's payment is not visible
        with self.assertRaises(ProcurementNotFoundError): self.svc.mark_invoice_paid(ORG, i["id"], dict(treasury_payment_id=other["id"]), U3)
        self.assertEqual(self.svc.get_invoice(ORG, i["id"])["status"], "APPROVED")

    def test_a_treasury_payment_cannot_pay_two_invoices(self):
        s, i = self.approved(); o2 = self.order(s, lines=[dict(LINES[0]), dict(LINES[1])]); self.receive(o2); j = self.svc.approve_invoice(ORG, self.invoice(o2, number="INV-200")["id"], U2)
        t = self.released(); self.svc.mark_invoice_paid(ORG, i["id"], dict(treasury_payment_id=t["id"]), U3)
        with self.assertRaises(ProcurementStateError): self.svc.mark_invoice_paid(ORG, j["id"], dict(treasury_payment_id=t["id"]), U3)


class Reviews(Base):
    SC = dict(delivery=4, quality=5, price=3, service=4)

    def test_review_average_and_rules(self):
        s = self.sup(); r = self.svc.review_supplier(ORG, s["id"], dict(period="2026-Q1", scores=self.SC), U1); self.assertEqual((r["ref"], r["average"], r["low"]), ("SR-001", "4.0", False))
        self.assertEqual(self.svc.review_supplier(ORG, s["id"], dict(period="2026-Q2", scores=dict(delivery=5, quality=4, price=4, service=4)), U1)["average"], "4.3")       # 4.25 rounds half up
        with self.assertRaises(ProcurementStateError): self.svc.review_supplier(ORG, s["id"], dict(period="2026-q1", scores=self.SC), U1)
        for bad in (dict(scores=None), dict(scores=dict(delivery=4)), dict(scores={**self.SC, "price": 0}), dict(scores={**self.SC, "price": 6}), dict(scores={**self.SC, "price": "x"}), dict(scores={**self.SC, "price": True}), dict(period="x")):
            with self.assertRaises(ProcurementError, msg=bad): self.svc.review_supplier(ORG, s["id"], {"period": "2026-Q3", "scores": self.SC, **bad}, U1)

    def test_a_low_score_needs_a_comment(self):
        s = self.sup(); low = {**self.SC, "quality": 2}
        with self.assertRaises(ProcurementError): self.svc.review_supplier(ORG, s["id"], dict(period="2026-Q1", scores=low), U1)
        r = self.svc.review_supplier(ORG, s["id"], dict(period="2026-Q1", scores=low, comment="Three of the ten laptops arrived damaged"), U1); self.assertTrue(r["low"])

    def test_review_clears_the_missing_review_flag_and_lists_newest_first(self):
        s, o = self.full(); self.assertTrue(self.svc.get_supplier(ORG, s["id"])["needs_review"])
        self.svc.review_supplier(ORG, s["id"], dict(period="2026-Q1", scores=self.SC), U1); self.clock.d = date(2026, 3, 1); self.svc.review_supplier(ORG, s["id"], dict(period="2026-Q2", scores=self.SC), U1)
        v = self.svc.get_supplier(ORG, s["id"]); self.assertFalse(v["needs_review"]); self.assertEqual(v["latest_review"]["period"], "2026-Q2"); self.assertEqual([r["period"] for r in self.svc.list_supplier_reviews(ORG, s["id"])], ["2026-Q2", "2026-Q1"])


class Overview(Base):
    def test_attention_list(self):
        p = self.sup("Pending Ltd", approve=False); s = self.sup(); self.contract(s, ceiling="5300.00", end="2026-03-15", approve=False)
        c = self.contract(s, ceiling="5300.00", end="2026-03-15"); o = self.order(s, contract=c); self.order(s, approve=False)
        self.clock.d = date(2026, 3, 5); self.receive(o, [{"line": 1, "qty": "1"}], when="2026-03-01"); i = self.invoice(o, [{"line": 1, "qty": "5", "unit_price": "500.00"}], invoice_date="2026-03-01")
        kinds = {x["kind"] for x in self.svc.procurement_overview(ORG)["attention"]}
        want = {"SUPPLIERS_PENDING", "CONTRACTS_PENDING", "CONTRACT_ENDING", "CONTRACT_CEILING", "ORDERS_WAITING", "DELIVERIES_LATE", "INVOICE_EXCEPTIONS", "REVIEWS_MISSING"}
        self.assertEqual(want - kinds, set(), kinds); self.svc.reject_invoice(ORG, i["id"], "Quantity not received", U2)
        j = self.invoice(o, [{"line": 1, "qty": "1", "unit_price": "500.00"}], "OK-1", invoice_date="2026-03-01"); self.assertEqual(j["status"], "MATCHED")
        k = {x["kind"] for x in self.svc.procurement_overview(ORG)["attention"]}; self.assertIn("INVOICES_WAITING", k); self.svc.approve_invoice(ORG, j["id"], U2); self.assertIn("INVOICES_UNPAID", {x["kind"] for x in self.svc.procurement_overview(ORG)["attention"]})
        self.assertTrue(self.svc.procurement_overview(ORG)["limitations"])

    def test_empty_and_options(self):
        o = self.svc.procurement_overview(ORG); self.assertEqual(o["attention"], []); self.assertEqual(o["counts"]["suppliers"], 0)
        s = self.sup(); op = self.svc.procurement_options(ORG); self.assertEqual(op["suppliers"][0]["id"], s["id"]); self.assertIn("GOODS", op["categories"])


class Isolation(Base):
    def test_other_organisation_sees_and_reaches_nothing(self):
        s, o = self.full(); i = self.invoice(o); c = self.contract(s)
        calls = [lambda: self.svc.get_supplier(OTHER, s["id"]), lambda: self.svc.get_contract(OTHER, c["id"]), lambda: self.svc.get_purchase_order(OTHER, o["id"]), lambda: self.svc.get_invoice(OTHER, i["id"]),
                 lambda: self.svc.approve_invoice(OTHER, i["id"], U2, "x"), lambda: self.svc.approve_purchase_order(OTHER, o["id"], U2, "x"), lambda: self.svc.record_delivery(OTHER, o["id"], dict(received_date="2026-02-15", lines=[{"line": 1, "qty": "1"}]), U3),
                 lambda: self.svc.suspend_supplier(OTHER, s["id"], "not yours", U2), lambda: self.svc.terminate_contract(OTHER, c["id"], "not yours", U2),
                 lambda: self.svc.review_supplier(OTHER, s["id"], dict(period="2026-Q1", scores=dict(delivery=4, quality=4, price=4, service=4)), U2),
                 lambda: self.svc.raise_purchase_order(OTHER, dict(supplier_id=s["id"], currency="NGN", expected_date="2026-03-01", purpose="Not allowed", lines=[dict(LINES[0])]), U1)]
        for fn in calls:
            with self.assertRaises(ProcurementNotFoundError): fn()
        self.assertEqual((self.svc.list_suppliers(OTHER), self.svc.list_contracts(OTHER), self.svc.list_purchase_orders(OTHER), self.svc.list_invoices(OTHER), self.svc.list_deliveries(OTHER), self.svc.list_supplier_reviews(OTHER)), ([], [], [], [], [], []))
        self.assertEqual(self.svc.procurement_overview(OTHER)["counts"]["suppliers"], 0)
        self.assertEqual(self.svc.register_supplier(OTHER, dict(name="Acme Supplies", related_party=False), U1)["ref"], "SU-001")      # same name, own numbering
        self.assertEqual(self.svc.get_invoice(ORG, i["id"])["status"], "MATCHED" if not i["flags"] else "EXCEPTION")


class References(Base):
    def test_refused_requests_do_not_use_up_numbers(self):
        with self.assertRaises(ProcurementError): self.sup("Bad one", contact="x" * 300)
        self.assertEqual(self.sup("Good one", approve=False)["ref"], "SU-001"); s = self.sup("Another")
        with self.assertRaises(ProcurementError): self.contract(s, ceiling="x", approve=False)
        self.assertEqual(self.contract(s, approve=False)["ref"], "CT-001")
        with self.assertRaises(ProcurementError): self.order(s, approve=False, purpose="no")
        self.assertEqual(self.order(s, approve=False)["ref"], "PO-001")


class Audit(Base):
    def test_every_write_is_audited(self):
        s = self.sup(); self.svc.suspend_supplier(ORG, s["id"], "Under investigation", U2); self.svc.reinstate_supplier(ORG, s["id"], "Cleared of concerns", U3)
        c = self.contract(s); self.svc.terminate_contract(ORG, c["id"], "Replaced by new agreement", U2); o = self.order(s); self.receive(o); i = self.invoice(o); self.svc.approve_invoice(ORG, i["id"], U2)
        self.svc.mark_invoice_paid(ORG, i["id"], dict(paid_date="2026-02-15", bank_reference="TRX-5"), U3); j = self.invoice(o, number="INV-X", lines=[{"line": 1, "qty": "1", "unit_price": "500.00"}]); self.svc.reject_invoice(ORG, j["id"], "Duplicate billing", U2)
        self.svc.close_purchase_order(ORG, o["id"], "Everything delivered and paid", U1); p = self.order(s, approve=False); self.svc.reject_purchase_order(ORG, p["id"], "Not needed any more", U2); q = self.order(s, approve=False); self.svc.cancel_purchase_order(ORG, q["id"], "Changed plans", U1)
        self.svc.review_supplier(ORG, s["id"], dict(period="2026-Q1", scores=dict(delivery=4, quality=4, price=4, service=4)), U1); self.svc.set_procurement_policy(ORG, {"warning_days": 30}, U2)
        got = {e[0] for e in self.events}
        want = {"PC_SUPPLIER_REGISTERED", "PC_SUPPLIER_APPROVED", "PC_SUPPLIER_SUSPENDED", "PC_SUPPLIER_REINSTATED", "PC_CONTRACT_DRAFTED", "PC_CONTRACT_APPROVED", "PC_CONTRACT_TERMINATED", "PC_ORDER_REQUESTED", "PC_ORDER_APPROVED",
                "PC_ORDER_REJECTED", "PC_ORDER_CANCELLED", "PC_ORDER_CLOSED", "PC_DELIVERY_RECORDED", "PC_INVOICE_RECORDED", "PC_INVOICE_APPROVED", "PC_INVOICE_REJECTED", "PC_INVOICE_PAID", "PC_SUPPLIER_REVIEWED", "PC_POLICY_SET"}
        self.assertEqual(want - got, set())

    def test_a_refused_action_writes_nothing(self):
        s = self.sup(); o = self.order(s, approve=False); n = len(self.events)
        with self.assertRaises(ProcurementForbiddenError): self.svc.approve_purchase_order(ORG, o["id"], U1)
        self.assertEqual(len(self.events), n); self.assertEqual(self.svc.get_purchase_order(ORG, o["id"])["approvals"], [])


class Permissions(unittest.TestCase):
    def test_roles(self):
        has = lambda r, p: p in ROLE_PERMISSIONS[r]
        for r in (Role.OWNER, Role.MANAGER, Role.FINANCE_OFFICER): self.assertTrue(has(r, PROCURE_PREPARE) and has(r, PROCURE_APPROVE), r)
        self.assertTrue(has(Role.ACCOUNTANT, PROCURE_PREPARE) and not has(Role.ACCOUNTANT, PROCURE_APPROVE)); self.assertTrue(has(Role.APPROVER, PROCURE_APPROVE) and not has(Role.APPROVER, PROCURE_PREPARE))
        for r in (Role.ADMINISTRATOR, Role.REVIEWER, Role.AUDITOR, Role.EXTERNAL_AUDITOR, Role.READ_ONLY): self.assertFalse(has(r, PROCURE_PREPARE) or has(r, PROCURE_APPROVE), r)
        for r in Role:
            if has(r, PROCURE_PREPARE) or has(r, PROCURE_APPROVE): self.assertTrue(has(r, REPORTING_READ), r)


class RouterGuards(unittest.TestCase):
    SRC = os.path.join(os.path.dirname(__file__), "..", "src", "asavexa", "api", "routers", "procurement.py")

    def test_every_write_has_the_right_guard(self):
        tree = ast.parse(open(self.SRC).read()); named = {"_prepare": "PROCURE_PREPARE", "_approve": "PROCURE_APPROVE"}; g = {}
        for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.decorator_list]:
            verbs, guards = set(), set()
            for dec in fn.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute): verbs.add(dec.func.attr)
                for kw in getattr(dec, "keywords", []):
                    if kw.arg == "dependencies": guards |= {named[e.id] for e in kw.value.elts if isinstance(e, ast.Name) and e.id in named}
            g[fn.name] = (verbs, guards)
        approve = {"set_policy", "approve_supplier", "suspend_supplier", "reinstate_supplier", "approve_contract", "terminate_contract", "approve_order", "reject_order", "approve_invoice", "reject_invoice"}
        prepare = {"register_supplier", "draft_contract", "raise_order", "cancel_order", "close_order", "add_delivery", "add_invoice", "pay_invoice", "add_review"}
        for n in approve: self.assertEqual(g[n][1], {"PROCURE_APPROVE"}, n)
        for n in prepare: self.assertEqual(g[n][1], {"PROCURE_PREPARE"}, n)
        for n, (verbs, guards) in g.items():
            if verbs == {"get"}: self.assertEqual(guards, set(), n)
            else: self.assertIn(n, approve | prepare, f"{n} writes but has no procurement guard")
        src = open(self.SRC).read(); self.assertIn("dependencies=[Depends(require_permission(REPORTING_READ))]", src); self.assertNotIn("org_id", src)


class Money(unittest.TestCase):
    def test_numbers(self):
        from asavexa.procurement.service import money, qty
        for bad in ("1e30", "abc", "", None, "1.005", "-1", "0", float("nan"), True): 
            with self.assertRaises(ProcurementError, msg=bad): money(bad, "x")
        self.assertEqual(str(money("1,234.50", "x")), "1234.50"); self.assertEqual(str(qty("2.5", "x")), "2.500")
        with self.assertRaises(ProcurementError): qty("1.0005", "x")


if __name__ == "__main__":
    unittest.main()
