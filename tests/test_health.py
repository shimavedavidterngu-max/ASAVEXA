"""Health Centre Administration: facilities and isolation, budgets, procurement, inventory, claims, revenue, assets, staffing, dashboard, reports."""
import csv
import io
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

from analysis_fixture import ORG, OTHER, World
from asavexa.evidence.domain.enums import EvidenceType
from asavexa.health.errors import HealthError, HealthForbiddenError, HealthNotFoundError, HealthStateError
from asavexa.health.service import HealthService
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.permissions import ROLE_PERMISSIONS

ADM, PRE, FIN, MGR, APR, AUD, OWN = "u-admin", "u-prep", "u-fin", "u-mgr", "u-appr", "u-aud", "u-owner"
ROLES = {ADM: Role.ADMINISTRATOR, PRE: Role.ACCOUNTANT, FIN: Role.FINANCE_OFFICER, MGR: Role.MANAGER, APR: Role.APPROVER, AUD: Role.AUDITOR, OWN: Role.OWNER}


class Clock:
    def __init__(self): self.d = date(2026, 2, 15)
    def __call__(self): return datetime(self.d.year, self.d.month, self.d.day, 9, tzinfo=timezone.utc)


def can(org, actor, perm): return actor in ROLES and perm in ROLE_PERMISSIONS[ROLES[actor]]   # like the real one: a stranger simply cannot


class Base(unittest.TestCase):
    def setUp(self):
        self.w = World(); self.clock = Clock(); self.events = []
        self.svc = HealthService(self.w.store, self.w.vault, None, log=lambda *a: self.events.append(a), now=self.clock, can=can)
        self.f = self.svc.create_facility(ORG, dict(name="Ikoyi Primary Health Centre", type="PRIMARY_HEALTH_CENTRE", ownership="PUBLIC", region="Lagos", currency="NGN"), ADM)
        self.fid = self.f["id"]
        self.opd = self.svc.add_department(ORG, self.fid, dict(code="opd", name="Outpatient"), ADM)
        self.store = self.svc.add_department(ORG, self.fid, dict(code="stores", name="Medical stores"), ADM)
        for u in (PRE, FIN, MGR, APR, AUD): self.svc.set_access(ORG, u, [self.fid], ADM)

    # ---- builders
    def budget(self, approve=True, lines=None, **kw):
        lines = lines if lines is not None else [dict(dept_id=self.opd["id"], category="MEDICAL_SUPPLIES", amount="100000"), dict(dept_id=self.opd["id"], category="STAFFING", amount="500000"),
                          dict(dept_id=self.opd["id"], category="MAINTENANCE", amount="50000"), dict(dept_id=self.store["id"], category="MEDICAL_SUPPLIES", amount="200000")]
        d = dict(name="2026 operating budget", period_start="2026-01-01", period_end="2026-12-31", lines=lines); d.update(kw)
        b = self.svc.create_budget(ORG, self.fid, d, PRE)
        if approve: self.svc.submit_budget(ORG, b["id"], PRE); b = self.svc.approve_budget(ORG, b["id"], MGR)
        return b

    def supplier(self, name="MediSupply Ltd"):
        for x in self.svc.list_suppliers(ORG, self.fid, PRE):
            if x["name"] == name: return x
        return self.svc.create_supplier(ORG, self.fid, dict(name=name), PRE)

    def item(self, sku="GLV-M", expiry=False, **kw):
        d = dict(sku=sku, name="Examination gloves M", category="MEDICAL_SUPPLIES", uom="box", reorder_level="10", tracks_expiry=expiry); d.update(kw)
        return self.svc.create_item(ORG, self.fid, d, PRE)

    def req(self, item=None, qty="100", price="500", dept=None, cat="MEDICAL_SUPPLIES", approve=True):
        line = dict(description="Examination gloves", qty=qty, unit_price=price)
        if item: line["item_id"] = item["id"]
        r = self.svc.create_requisition(ORG, self.fid, dict(dept_id=(dept or self.opd)["id"], category=cat, lines=[line], justification="Monthly restock"), PRE)
        self.svc.submit_requisition(ORG, r["id"], PRE)
        return self.svc.decide_requisition(ORG, r["id"], True, "", MGR) if approve else r

    def po(self, approve=True, **kw):
        sup = self.supplier() if "sup" not in kw else kw.pop("sup")
        r = self.req(**kw); p = self.svc.create_po(ORG, r["id"], sup["id"], PRE)
        return self.svc.approve_po(ORG, p["id"], "", MGR) if approve else p

    def evidence(self):
        return self.w.vault.upload_evidence(ORG, list(EvidenceType)[0], b"delivery note scan" * 3, "dn.pdf", "application/pdf", uploaded_by=PRE)


class TestFacilityAndAccess(Base):
    def test_only_admin_registers_and_duplicates_refused(self):
        with self.assertRaises(HealthForbiddenError): self.svc.create_facility(ORG, dict(name="X Clinic", type="CLINIC", ownership="PRIVATE", region="Abuja", currency="NGN"), PRE)
        with self.assertRaises(HealthError): self.svc.create_facility(ORG, dict(name=" ikoyi primary health centre", type="CLINIC", ownership="PRIVATE", region="Abuja", currency="NGN"), ADM)
        with self.assertRaises(HealthError): self.svc.create_facility(ORG, dict(name="Bad Currency", type="CLINIC", ownership="PRIVATE", region="Abuja", currency="N1"), ADM)
        with self.assertRaises(HealthError): self.svc.add_department(ORG, self.fid, dict(code="OPD", name="Again"), ADM)
        self.assertEqual(self.f["ref"], "F-001")

    def test_facility_boundaries_cannot_be_crossed_by_changing_an_identifier(self):
        f2 = self.svc.create_facility(ORG, dict(name="Second Clinic", type="CLINIC", ownership="PRIVATE", region="Kano", currency="NGN"), ADM)
        dept2 = self.svc.add_department(ORG, f2["id"], dict(code="GEN", name="General"), ADM)
        self.assertEqual([f["ref"] for f in self.svc.list_facilities(ORG, PRE)], ["F-001"])
        self.assertEqual(len(self.svc.list_facilities(ORG, ADM)), 2)
        with self.assertRaises(HealthNotFoundError): self.svc.get_facility(ORG, f2["id"], PRE)
        with self.assertRaises(HealthNotFoundError): self.svc.list_budgets(ORG, f2["id"], PRE)
        with self.assertRaises(HealthNotFoundError): self.svc.create_supplier(ORG, f2["id"], dict(name="Sneaky"), PRE)
        # a record from facility 2 fetched by id from a user who only has facility 1
        self.svc.set_access(ORG, PRE, [f2["id"]], ADM)
        s2 = self.svc.create_supplier(ORG, f2["id"], dict(name="Kano Supplies"), PRE)
        self.svc.set_access(ORG, PRE, [self.fid], ADM)
        with self.assertRaises(HealthNotFoundError): self.svc.set_supplier_status(ORG, s2["id"], False, "no longer used", PRE)
        with self.assertRaises(HealthNotFoundError): self.svc.dashboard(ORG, f2["id"], MGR)
        with self.assertRaises(HealthForbiddenError): self.svc.set_access(ORG, MGR, [self.fid], MGR)

    def test_facility_access_only_for_people_in_the_organisation(self):
        with self.assertRaises(HealthNotFoundError): self.svc.set_access(ORG, "someone-from-another-company", [self.fid], ADM)
        with self.assertRaises(HealthNotFoundError): self.svc.set_access(ORG, "someone-from-another-company", [], ADM)
        self.assertNotIn("someone-from-another-company", self.svc.get_access(ORG, ADM))

    def test_another_organisation_cannot_see_anything(self):
        self.supplier()
        with self.assertRaises(HealthNotFoundError): self.svc.get_facility(OTHER, self.fid, ADM)
        self.assertEqual(self.svc.list_facilities(OTHER, ADM), [])

    def test_inactive_facility_keeps_history_but_takes_no_new_records(self):
        self.budget(); self.supplier()
        self.svc.set_facility_status(ORG, self.fid, False, "Merged into another site", ADM)
        with self.assertRaises(HealthStateError): self.svc.create_supplier(ORG, self.fid, dict(name="New supplier"), PRE)
        with self.assertRaises(HealthStateError): self.svc.create_requisition(ORG, self.fid, dict(dept_id=self.opd["id"], category="OTHER", lines=[dict(description="x item", qty="1", unit_price="1")], justification="not allowed"), PRE)
        self.assertEqual(len(self.svc.list_budgets(ORG, self.fid, PRE)), 1)
        self.assertEqual(len(self.svc.list_suppliers(ORG, self.fid, PRE)), 1)
        self.assertEqual(self.svc.get_facility(ORG, self.fid, PRE)["status"], "INACTIVE")
        self.svc.set_facility_status(ORG, self.fid, True, "Reopened", ADM); self.supplier("Another")


class TestBudgets(Base):
    def test_budget_approval_needs_a_different_person_and_overlaps_are_refused(self):
        b = self.budget(approve=False); self.svc.submit_budget(ORG, b["id"], PRE)
        with self.assertRaises(HealthForbiddenError): self.svc.approve_budget(ORG, b["id"], PRE)
        with self.assertRaises(HealthStateError): self.svc.revise_budget(ORG, b["id"], "Change of plan here", PRE)      # only an approved budget can be revised
        self.svc.approve_budget(ORG, b["id"], MGR)
        b2 = self.svc.create_budget(ORG, self.fid, dict(name="Other plan", period_start="2026-06-01", period_end="2027-05-31", lines=[dict(dept_id=self.opd["id"], category="OTHER", amount="10")]), PRE)
        self.svc.submit_budget(ORG, b2["id"], PRE)
        with self.assertRaises(HealthStateError): self.svc.approve_budget(ORG, b2["id"], MGR)

    def test_budget_validation(self):
        for lines in ([], [dict(dept_id="nope", category="OTHER", amount="1")], [dict(dept_id=self.opd["id"], category="BOGUS", amount="1")], [dict(dept_id=self.opd["id"], category="OTHER", amount="0")],
                      [dict(dept_id=self.opd["id"], category="OTHER", amount="5"), dict(dept_id=self.opd["id"], category="OTHER", amount="6")]):
            with self.assertRaises(HealthError): self.budget(approve=False, lines=lines)
        with self.assertRaises(HealthError): self.budget(approve=False, period_end="2025-12-31")
        with self.assertRaises(HealthError): self.budget(approve=False, period_end="2027-12-31")

    def test_revision_supersedes_and_keeps_history(self):
        b = self.budget(); r = self.svc.revise_budget(ORG, b["id"], "Mid-year increase for supplies", PRE)
        self.assertEqual((r["version"], r["status"], r["supersedes"]), (2, "DRAFT", b["id"]))
        with self.assertRaises(HealthStateError): self.svc.revise_budget(ORG, b["id"], "Second revision at once", PRE)
        r["lines"][0]["amount"] = "150000.00"; self.svc.update_budget(ORG, r["id"], dict(name=r["name"], period_start=r["period_start"], period_end=r["period_end"], lines=r["lines"]), PRE)
        self.svc.submit_budget(ORG, r["id"], PRE); self.svc.approve_budget(ORG, r["id"], MGR)
        self.assertEqual(self.svc.get_budget(ORG, b["id"], PRE)["status"], "SUPERSEDED")
        self.assertEqual(self.svc.get_budget(ORG, r["id"], PRE)["status"], "APPROVED")
        self.assertEqual(sum(1 for x in self.svc.list_budgets(ORG, self.fid, PRE) if x["status"] == "APPROVED"), 1)

    def test_transfers_need_availability_and_a_second_person(self):
        b = self.budget(); lid = b["lines"][0]["line_id"]; to = b["lines"][1]["line_id"]
        with self.assertRaises(HealthError): self.svc.request_transfer(ORG, b["id"], lid, to, "100001", "Move too much money", PRE)
        t = self.svc.request_transfer(ORG, b["id"], lid, to, "30000", "Staffing needs more cover", PRE)
        with self.assertRaises(HealthForbiddenError): self.svc.decide_transfer(ORG, b["id"], t["id"], True, "", PRE)
        with self.assertRaises(HealthError): self.svc.request_transfer(ORG, b["id"], lid, to, "80000", "Pending plus new exceeds", PRE)
        self.svc.decide_transfer(ORG, b["id"], t["id"], True, "", MGR)
        rows = {r["line_id"]: r for r in self.svc.execution(ORG, self.fid, b["id"], PRE)["rows"]}
        self.assertEqual((rows[lid]["budget"], rows[to]["budget"], rows[lid]["approved"]), ("70000.00", "530000.00", "100000.00"))
        with self.assertRaises(HealthStateError): self.svc.decide_transfer(ORG, b["id"], t["id"], True, "", MGR)


class TestProcurement(Base):
    def test_full_flow_commitment_then_spend_without_double_counting(self):
        b = self.budget(); it = self.item(); sup = self.supplier(); lid = b["lines"][0]["line_id"]
        r = self.req(item=it, qty="100", price="500", approve=False)                      # total 50,000
        with self.assertRaises(HealthForbiddenError): self.svc.decide_requisition(ORG, r["id"], True, "", PRE)
        self.svc.decide_requisition(ORG, r["id"], True, "", MGR)
        p = self.svc.create_po(ORG, r["id"], sup["id"], PRE)
        with self.assertRaises(HealthForbiddenError): self.svc.approve_po(ORG, p["id"], "", PRE)
        ex = lambda: {x["line_id"]: x for x in self.svc.execution(ORG, self.fid, b["id"], PRE)["rows"]}[lid]
        self.assertEqual((ex()["committed"], ex()["spent"], ex()["available"]), ("0.00", "0.00", "100000.00"))   # pending approval commits nothing
        self.svc.approve_po(ORG, p["id"], "", MGR)
        self.assertEqual((ex()["committed"], ex()["spent"], ex()["available"]), ("50000.00", "0.00", "50000.00"))
        g = self.svc.receive_goods(ORG, p["id"], dict(lines=[dict(line_no=1, qty="40", location="MAIN")], delivery_note="DN-1"), PRE)
        po = self.svc.list_pos(ORG, self.fid, PRE)[0]; self.assertEqual(po["status"], "PARTIAL")
        inv = self.svc.record_invoice(ORG, p["id"], dict(invoice_no="INV/77", amount="20000", invoice_date="2026-02-14"), PRE)
        self.assertEqual((inv["status"], inv["match"]["received_value"]), ("MATCHED", "20000.00"))
        self.assertEqual((ex()["committed"], ex()["spent"]), ("50000.00", "0.00"))          # recorded but not verified: still a commitment
        self.svc.verify_invoice(ORG, inv["id"], "", MGR)
        self.assertEqual((ex()["committed"], ex()["spent"], ex()["available"]), ("30000.00", "20000.00", "50000.00"))   # 50,000 never counted twice
        self.svc.receive_goods(ORG, p["id"], dict(lines=[dict(line_no=1, qty="60", location="MAIN")], delivery_note="DN-2"), PRE)
        self.assertEqual(self.svc.list_pos(ORG, self.fid, PRE)[0]["status"], "RECEIVED")
        inv2 = self.svc.record_invoice(ORG, p["id"], dict(invoice_no="INV/78", amount="30000", invoice_date="2026-02-15"), PRE); self.svc.verify_invoice(ORG, inv2["id"], "", MGR)
        self.assertEqual((ex()["committed"], ex()["spent"], ex()["available"], ex()["used_pct"]), ("0.00", "50000.00", "50000.00", "50.00"))
        self.assertEqual(self.svc.stock_levels(ORG, self.fid, PRE)["items"][0]["on_hand"], "100.000")

    def test_partial_delivery_is_not_marked_received_and_over_receipt_refused(self):
        self.budget(); it = self.item(); p = self.po(item=it, qty="10", price="100")
        with self.assertRaises(HealthError): self.svc.receive_goods(ORG, p["id"], dict(lines=[dict(line_no=1, qty="11")], delivery_note="DN-A"), PRE)
        with self.assertRaises(HealthError): self.svc.receive_goods(ORG, p["id"], dict(lines=[dict(line_no=2, qty="1")], delivery_note="DN-A"), PRE)
        with self.assertRaises(HealthError): self.svc.receive_goods(ORG, p["id"], dict(lines=[], delivery_note="DN-A"), PRE)
        self.svc.receive_goods(ORG, p["id"], dict(lines=[dict(line_no=1, qty="4")], delivery_note="DN-A"), PRE)
        with self.assertRaises(HealthError): self.svc.receive_goods(ORG, p["id"], dict(lines=[dict(line_no=1, qty="1")], delivery_note="dn a"), PRE)   # same delivery note again
        self.assertEqual(self.svc.list_pos(ORG, self.fid, PRE)[0]["status"], "PARTIAL")
        with self.assertRaises(HealthError): self.svc.receive_goods(ORG, p["id"], dict(lines=[dict(line_no=1, qty="7")], delivery_note="DN-B"), PRE)
        self.svc.receive_goods(ORG, p["id"], dict(lines=[dict(line_no=1, qty="6")], delivery_note="DN-B"), PRE)
        self.assertEqual(self.svc.list_pos(ORG, self.fid, PRE)[0]["status"], "RECEIVED")
        with self.assertRaises(HealthStateError): self.svc.receive_goods(ORG, p["id"], dict(lines=[dict(line_no=1, qty="1")], delivery_note="DN-C"), PRE)

    def test_overspend_is_blocked_unless_an_exception_is_recorded(self):
        self.budget(); sup = self.supplier(); r = self.req(qty="300", price="500")          # 150,000 > 100,000 line
        p = self.svc.create_po(ORG, r["id"], sup["id"], PRE)
        with self.assertRaises(HealthError): self.svc.approve_po(ORG, p["id"], "", MGR)
        with self.assertRaises(HealthError): self.svc.approve_po(ORG, p["id"], "too short", MGR)
        p = self.svc.approve_po(ORG, p["id"], "Emergency restock agreed with the district office", MGR)
        self.assertEqual(p["exception"]["available"], "100000.00"); self.assertEqual(len(self.svc.procurement_exceptions(ORG, self.fid, PRE)["budget_exceptions"]), 1)

    def test_order_with_no_budget_is_blocked_but_allowed_when_facility_does_not_block(self):
        sup = self.supplier(); r = self.req(qty="1", price="10"); p = self.svc.create_po(ORG, r["id"], sup["id"], PRE)
        with self.assertRaises(HealthError): self.svc.approve_po(ORG, p["id"], "", MGR)
        self.svc.update_facility(ORG, self.fid, dict(block_overspend=False), ADM)
        self.assertEqual(self.svc.approve_po(ORG, p["id"], "", MGR)["status"], "OPEN")

    def test_duplicate_invoices_and_three_way_match(self):
        self.budget(); p = self.po(qty="10", price="1000")
        with self.assertRaises(HealthStateError): self.svc.record_invoice(ORG, p["id"], dict(invoice_no="A1", amount="100", invoice_date="2026-02-01"), PRE)   # nothing received yet
        self.svc.receive_goods(ORG, p["id"], dict(lines=[dict(line_no=1, qty="5")], delivery_note="D1"), PRE)
        i = self.svc.record_invoice(ORG, p["id"], dict(invoice_no="Inv-001", amount="5000", invoice_date="2026-02-01"), PRE)
        for dup in ("INV 001", "inv-001", "INV001"):
            with self.assertRaises(HealthError): self.svc.record_invoice(ORG, p["id"], dict(invoice_no=dup, amount="5000", invoice_date="2026-02-02"), PRE)
        over = self.svc.record_invoice(ORG, p["id"], dict(invoice_no="Inv-002", amount="1", invoice_date="2026-02-02"), PRE)       # received value already fully invoiced
        self.assertEqual((over["status"], over["match"]["allowed"]), ("EXCEPTION", "0.00"))
        with self.assertRaises(HealthError): self.svc.verify_invoice(ORG, over["id"], "", MGR)
        self.svc.verify_invoice(ORG, over["id"], "Supplier delivery charge agreed by phone with manager", MGR)
        self.svc.cancel_invoice(ORG, i["id"], "Replaced by corrected invoice", PRE)
        again = self.svc.record_invoice(ORG, p["id"], dict(invoice_no="Inv-001", amount="5000", invoice_date="2026-02-03"), PRE)   # a cancelled number can be re-entered
        self.assertEqual(again["status"], "EXCEPTION")                                                                              # 1 already verified leaves 4,999 allowed
        self.assertEqual(len(self.svc.procurement_exceptions(ORG, self.fid, PRE)["invoice_mismatches"]), 2)

    def test_payment_chain_separation_and_no_duplicate_payment(self):
        self.budget(); p = self.po(qty="10", price="1000"); self.svc.receive_goods(ORG, p["id"], dict(lines=[dict(line_no=1, qty="10")], delivery_note="D1"), PRE)
        i = self.svc.record_invoice(ORG, p["id"], dict(invoice_no="X-1", amount="10000", invoice_date="2026-02-10"), PRE)
        with self.assertRaises(HealthForbiddenError): self.svc.verify_invoice(ORG, i["id"], "", PRE)
        with self.assertRaises(HealthStateError): self.svc.approve_payment(ORG, i["id"], APR)
        self.svc.verify_invoice(ORG, i["id"], "", MGR)
        with self.assertRaises(HealthForbiddenError): self.svc.approve_payment(ORG, i["id"], MGR)          # verifier cannot approve payment
        with self.assertRaises(HealthStateError): self.svc.pay_invoice(ORG, i["id"], "BANK-1", PRE)         # not yet approved
        self.svc.credit_note(ORG, i["id"], "1000", "Damaged boxes returned", MGR)
        with self.assertRaises(HealthError): self.svc.credit_note(ORG, i["id"], "9500", "More than payable", MGR)
        a = self.svc.approve_payment(ORG, i["id"], APR); self.assertEqual(a["status"], "PAYMENT_APPROVED")
        paid = self.svc.pay_invoice(ORG, i["id"], "BANK-1", PRE); self.assertEqual((paid["status"], paid["payment"]["amount"]), ("PAID", "9000.00"))
        with self.assertRaises(HealthStateError): self.svc.pay_invoice(ORG, i["id"], "BANK-1", PRE)         # duplicate payment request
        with self.assertRaises(HealthStateError): self.svc.credit_note(ORG, i["id"], "10", "Too late to credit", MGR)
        # the same payment reference cannot be reused on another invoice
        p2 = self.po(sup=self.svc.list_suppliers(ORG, self.fid, PRE)[0], qty="1", price="100"); self.svc.receive_goods(ORG, p2["id"], dict(lines=[dict(line_no=1, qty="1")], delivery_note="D9"), PRE)
        j = self.svc.record_invoice(ORG, p2["id"], dict(invoice_no="X-2", amount="100", invoice_date="2026-02-10"), PRE); self.svc.verify_invoice(ORG, j["id"], "", MGR); self.svc.approve_payment(ORG, j["id"], APR)
        with self.assertRaises(HealthError): self.svc.pay_invoice(ORG, j["id"], "bank 1", PRE)

    def test_payables_ageing_buckets(self):
        self.budget()
        sup = self.supplier()
        for n, (amt, d) in enumerate([("1000", "2026-02-10"), ("2000", "2026-01-05"), ("4000", "2025-12-01"), ("8000", "2025-09-01")], 1):
            r = self.req(qty="1", price=amt); p = self.svc.create_po(ORG, r["id"], sup["id"], PRE); self.svc.approve_po(ORG, p["id"], "Approved over budget in this test run", MGR)
            self.svc.receive_goods(ORG, p["id"], dict(lines=[dict(line_no=1, qty="1")], delivery_note=f"D{n}"), PRE); self.svc.record_invoice(ORG, p["id"], dict(invoice_no=f"A{n}", amount=amt, invoice_date=d), PRE)
        a = self.svc.payables_ageing(ORG, self.fid, PRE)["totals"]
        self.assertEqual((a["0-30"], a["31-60"], a["61-90"], a["over 90"], a["total"]), ("1000.00", "2000.00", "4000.00", "8000.00", "15000.00"))

    def test_requisition_quotes_and_po_rules(self):
        self.budget(); sup = self.supplier(); sup2 = self.supplier("Other Supplies"); self.svc.update_facility(ORG, self.fid, dict(min_quotes=2), ADM)
        r = self.req()
        with self.assertRaises(HealthError): self.svc.create_po(ORG, r["id"], sup["id"], PRE)
        self.svc.add_quote(ORG, r["id"], dict(supplier_id=sup["id"], amount="52000"), PRE); self.svc.add_quote(ORG, r["id"], dict(supplier_id=sup2["id"], amount="48000", evidence_ids=[self.evidence().id]), PRE)
        with self.assertRaises(HealthError): self.svc.add_quote(ORG, r["id"], dict(supplier_id=sup2["id"], amount="1"), PRE)
        cmp_ = [x for x in self.svc.list_requisitions(ORG, self.fid, PRE) if x["id"] == r["id"]][0]["quote_comparison"]
        self.assertEqual([(q["supplier"], q["lowest"]) for q in cmp_], [("Other Supplies", True), ("MediSupply Ltd", False)])
        self.svc.set_supplier_status(ORG, sup["id"], False, "Failed an inspection", PRE)
        with self.assertRaises(HealthError): self.svc.create_po(ORG, r["id"], sup["id"], PRE)
        p = self.svc.create_po(ORG, r["id"], sup2["id"], PRE)
        with self.assertRaises(HealthStateError): self.svc.create_po(ORG, r["id"], sup2["id"], PRE)       # one order per requisition
        self.assertEqual(self.svc.cancel_po(ORG, p["id"], "Requisition withdrawn", PRE)["status"], "CANCELLED")

    def test_evidence_links_and_cross_org_evidence_refused(self):
        self.budget(); p = self.po(qty="2", price="100"); ev = self.evidence()
        g = self.svc.receive_goods(ORG, p["id"], dict(lines=[dict(line_no=1, qty="2")], delivery_note="D1", evidence_ids=[ev.id]), PRE)
        self.assertEqual(g["evidence"][0]["filename"], "dn.pdf")
        i = self.svc.record_invoice(ORG, p["id"], dict(invoice_no="E1", amount="200", invoice_date="2026-02-10", evidence_ids=[ev.id]), PRE); self.assertEqual(i["evidence"][0]["evidence_id"], ev.id)
        with self.assertRaises(HealthError): self.svc.record_invoice(ORG, p["id"], dict(invoice_no="E2", amount="1", invoice_date="2026-02-10", evidence_ids=["nope"]), PRE)

    def test_failed_receipt_changes_nothing(self):
        self.budget(); it = self.item(expiry=True); p = self.po(item=it, qty="10", price="100")
        before = self.svc.stock_levels(ORG, self.fid, PRE)["total_value"]
        with self.assertRaises(HealthError): self.svc.receive_goods(ORG, p["id"], dict(lines=[dict(line_no=1, qty="5", batch="B1", expiry="2025-01-01")], delivery_note="D1"), PRE)   # already expired
        with self.assertRaises(HealthError): self.svc.receive_goods(ORG, p["id"], dict(lines=[dict(line_no=1, qty="5")], delivery_note="D1"), PRE)                                    # batch missing
        po = self.svc.list_pos(ORG, self.fid, PRE)[0]
        self.assertEqual((po["status"], po["lines"][0]["received_qty"], self.svc.list_receipts(ORG, self.fid, PRE), self.svc.stock_levels(ORG, self.fid, PRE)["total_value"]), ("OPEN", "0.000", [], before))


class TestInventory(Base):
    def receive(self, it, qty, price, batch=None, expiry=None, loc="MAIN", dn=None):
        p = self.po(item=it, qty=qty, price=price)
        self.dn = getattr(self, "dn", 0) + 1
        return self.svc.receive_goods(ORG, p["id"], dict(lines=[dict(line_no=1, qty=qty, batch=batch, expiry=expiry, location=loc)], delivery_note=dn or f"DN{self.dn}"), PRE)

    def setUp(self):
        super().setUp(); self.budget(lines=[dict(dept_id=self.opd["id"], category="MEDICAL_SUPPLIES", amount="9000000")])

    def test_weighted_average_cost_valuation_and_history(self):
        it = self.item("PCM", name="Paracetamol 500mg tablets", reorder_level="0"); self.receive(it, "10", "10"); self.receive(it, "10", "20")
        row = self.svc.stock_levels(ORG, self.fid, PRE)["items"][0]; self.assertEqual((row["on_hand"], row["avg_cost"], row["value"]), ("20.000", "15.0000", "300.00"))
        self.svc.issue_stock(ORG, it["id"], dict(qty="5", purpose="Outpatient ward use"), PRE)
        row = self.svc.stock_levels(ORG, self.fid, PRE)["items"][0]; self.assertEqual((row["on_hand"], row["avg_cost"], row["value"]), ("15.000", "15.0000", "225.00"))
        mv = self.svc.movements(ORG, it["id"], PRE); self.assertEqual([m["type"] for m in mv], ["RECEIPT", "RECEIPT", "ISSUE"])
        self.assertEqual(sum(Decimal(m["qty"]) for m in mv), Decimal(row["on_hand"])); self.assertEqual(sum(Decimal(m["value"]) for m in mv), Decimal("10") * 10 + Decimal("10") * 20 - Decimal("75"))

    def test_fefo_issue_blocks_expired_and_negative_stock(self):
        it = self.item("AMX", expiry=True, reorder_level="0"); self.receive(it, "10", "10", "LATE", "2026-12-31"); self.receive(it, "10", "10", "EARLY", "2026-03-31"); self.receive(it, "5", "10", "OLD", "2026-02-20")
        self.clock.d = date(2026, 2, 25)                                                                                      # OLD lot has now expired
        self.assertEqual([e["batch"] for e in self.svc.stock_levels(ORG, self.fid, PRE)["alerts"]["expired"]], ["OLD"])
        out = self.svc.issue_stock(ORG, it["id"], dict(qty="12", purpose="Pharmacy store to ward"), PRE)
        self.assertEqual([(m["batch"], m["qty"]) for m in out], [("EARLY", "-10.000"), ("LATE", "-2.000")])
        with self.assertRaises(HealthError): self.svc.issue_stock(ORG, it["id"], dict(qty="9", purpose="Too many for the stock"), PRE)   # 8 usable; the expired 5 are not available
        with self.assertRaises(HealthError): self.svc.issue_stock(ORG, it["id"], dict(qty="1", location="OTHERROOM", purpose="Wrong location here"), PRE)
        with self.assertRaises(HealthError): self.svc.issue_stock(ORG, it["id"], dict(qty="0", purpose="Nothing at all"), PRE)

    def test_expiry_and_low_stock_report(self):
        it = self.item("SYR", expiry=True, reorder_level="20"); self.receive(it, "15", "10", "S1", "2026-03-15")                   # 28 days away; window 90
        a = self.svc.stock_levels(ORG, self.fid, PRE)["alerts"]
        self.assertEqual((len(a["low_stock"]), [x["batch"] for x in a["expiring_soon"]], a["expired"]), (1, ["S1"], []))
        self.svc.update_facility(ORG, self.fid, dict(expiry_alert_days=7), ADM)
        self.assertEqual(self.svc.stock_levels(ORG, self.fid, PRE)["alerts"]["expiring_soon"], [])

    def test_transfer_between_locations(self):
        it = self.item("BND"); self.receive(it, "10", "10", loc="STORE")
        self.svc.transfer_stock(ORG, it["id"], dict(qty="4", from_location="STORE", to_location="WARD"), PRE)
        lots = {l["location"]: l["qty"] for l in self.svc.stock_levels(ORG, self.fid, PRE)["items"][0]["lots"]}; self.assertEqual(lots, {"STORE": "6.000", "WARD": "4.000"})
        with self.assertRaises(HealthError): self.svc.transfer_stock(ORG, it["id"], dict(qty="7", from_location="STORE", to_location="WARD"), PRE)
        with self.assertRaises(HealthError): self.svc.transfer_stock(ORG, it["id"], dict(qty="1", from_location="STORE", to_location="STORE"), PRE)

    def test_adjustments_and_write_offs_need_a_second_person_and_never_go_negative(self):
        it = self.item("GZE", expiry=True, reorder_level="0"); self.receive(it, "10", "20", "G1", "2026-03-01")
        with self.assertRaises(HealthError): self.svc.request_adjustment(ORG, it["id"], dict(batch="G1", expiry="2026-03-01", qty_delta="-11", kind="CORRECTION", reason="Counting mistake found"), PRE)
        with self.assertRaises(HealthError): self.svc.request_adjustment(ORG, it["id"], dict(batch="G1", expiry="2026-03-01", qty_delta="3", kind="DAMAGED", reason="Damaged boxes in the store"), PRE)
        with self.assertRaises(HealthError): self.svc.request_adjustment(ORG, it["id"], dict(batch="ZZ", expiry="2026-03-01", qty_delta="-1", kind="DAMAGED", reason="Unknown batch number here"), PRE)
        with self.assertRaises(HealthError): self.svc.request_adjustment(ORG, it["id"], dict(batch="G1", expiry="2026-03-01", qty_delta="-1", kind="DAMAGED", reason="short"), PRE)
        a = self.svc.request_adjustment(ORG, it["id"], dict(batch="G1", expiry="2026-03-01", qty_delta="-4", kind="DAMAGED", reason="Water damage in the store room", evidence_ids=[self.evidence().id]), PRE)
        with self.assertRaises(HealthError): self.svc.request_adjustment(ORG, it["id"], dict(batch="G1", expiry="2026-03-01", qty_delta="-7", kind="CORRECTION", reason="Pending plus this goes below zero"), PRE)
        self.assertEqual(self.svc.stock_levels(ORG, self.fid, PRE)["items"][0]["on_hand"], "10.000")                           # nothing changes until approved
        with self.assertRaises(HealthForbiddenError): self.svc.decide_adjustment(ORG, a["id"], True, "", PRE)
        done = self.svc.decide_adjustment(ORG, a["id"], True, "", MGR)
        self.assertEqual((done["status"], done["value_effect"]), ("APPROVED", "-80.00")); self.assertIn("journal", done["accounting_note"])
        self.assertEqual(self.svc.movements(ORG, it["id"], PRE)[-1]["type"], "WRITE_OFF"); self.assertEqual(self.svc.stock_levels(ORG, self.fid, PRE)["items"][0]["on_hand"], "6.000")
        with self.assertRaises(HealthStateError): self.svc.decide_adjustment(ORG, a["id"], True, "", MGR)
        b = self.svc.request_adjustment(ORG, it["id"], dict(batch="G1", expiry="2026-03-01", qty_delta="-2", kind="CORRECTION", reason="Recount two boxes less"), PRE)
        with self.assertRaises(HealthError): self.svc.decide_adjustment(ORG, b["id"], False, "", MGR)
        self.assertEqual(self.svc.decide_adjustment(ORG, b["id"], False, "Recount it again first", MGR)["status"], "REJECTED")

    def test_physical_count_creates_a_variance_for_approval(self):
        it = self.item("CNT"); self.receive(it, "10", "10")
        same = self.svc.record_count(ORG, it["id"], dict(counted_qty="10"), PRE); self.assertEqual((same["variance"], same["adjustment"]), ("0.000", None))
        v = self.svc.record_count(ORG, it["id"], dict(counted_qty="8"), PRE); self.assertEqual((v["variance"], v["adjustment"]["qty_delta"], v["adjustment"]["kind"]), ("-2.000", "-2.000", "COUNT_VARIANCE"))
        self.svc.decide_adjustment(ORG, v["adjustment"]["id"], True, "", MGR); self.assertEqual(self.svc.stock_levels(ORG, self.fid, PRE)["items"][0]["on_hand"], "8.000")
        with self.assertRaises(HealthError): self.svc.record_count(ORG, it["id"], dict(counted_qty="-1"), PRE)

    def test_sku_unique_and_stock_changes_are_audited(self):
        self.item("DUP")
        with self.assertRaises(HealthError): self.item("dup")
        it = self.item("AUD"); self.receive(it, "3", "10"); self.svc.issue_stock(ORG, it["id"], dict(qty="1", purpose="Ward round supplies"), PRE)
        self.assertTrue({"HC_GOODS_RECEIVED", "HC_PO_APPROVED"} <= {e[0] for e in self.events})


class TestClaimsAndRevenue(Base):
    def payer(self, name="Sunrise Health Insurance"): return self.svc.create_payer(ORG, self.fid, dict(name=name, kind="INSURER"), PRE)

    def claim(self, payer=None, amount="10000", ext="SUN/2026/001", submit=True):
        c = self.svc.create_claim(ORG, self.fid, dict(payer_id=(payer or self.payer())["id"], external_ref=ext, service_category="OUTPATIENT_SERVICES", service_month="2026-01", amount=amount), PRE)
        return self.svc.submit_claim(ORG, c["id"], PRE) if submit else c

    def test_claims_carry_no_patient_information_and_need_the_claims_permission(self):
        c = self.claim(); self.assertRegex(c["ref"], r"^CLM-[0-9A-F]{8}$")
        self.assertTrue({"name", "patient", "dob", "diagnosis", "address", "phone", "national_id"}.isdisjoint(c.keys()))
        self.assertEqual(c["service_month"], "2026-01")
        for who in (ADM, AUD):
            with self.assertRaises(HealthForbiddenError): self.svc.list_claims(ORG, self.fid, who)
        with self.assertRaises(HealthForbiddenError): self.svc.create_claim(ORG, self.fid, dict(payer_id=c["payer_id"], service_category="OUTPATIENT_SERVICES", service_month="2026-01", amount="1"), ADM)
        with self.assertRaises(HealthForbiddenError): self.svc.get_claim(ORG, c["id"], AUD)
        with self.assertRaises(HealthError): self.svc.create_claim(ORG, self.fid, dict(payer_id=c["payer_id"], external_ref="Ada Okafor", service_category="OUTPATIENT_SERVICES", service_month="2026-01", amount="1"), PRE)   # looks like a name
        with self.assertRaises(HealthError): self.svc.create_claim(ORG, self.fid, dict(payer_id=c["payer_id"], service_category="OUTPATIENT_SERVICES", service_month="2026-01-15", amount="1"), PRE)               # full date refused

    def test_duplicate_claim_and_double_submission(self):
        p = self.payer(); c = self.claim(p)
        with self.assertRaises(HealthError): self.svc.create_claim(ORG, self.fid, dict(payer_id=p["id"], external_ref="sun-2026-001", service_category="OUTPATIENT_SERVICES", service_month="2026-01", amount="5"), PRE)
        with self.assertRaises(HealthStateError): self.svc.submit_claim(ORG, c["id"], PRE)
        p2 = self.payer("Other Payer"); self.claim(p2, ext="SUN/2026/001")            # same reference with a different payer is allowed

    def test_rejection_resubmission_partial_payments_and_overpayment(self):
        c = self.claim(amount="10000")
        with self.assertRaises(HealthStateError): self.svc.resubmit_claim(ORG, c["id"], None, "Nothing to correct", PRE)
        self.svc.reject_claim(ORG, c["id"], "INCOMPLETE_DOCUMENTATION", "Referral form missing", PRE)
        with self.assertRaises(HealthStateError): self.svc.pay_claim(ORG, c["id"], dict(amount="1", payment_ref="PAY-0", date="2026-02-01"), PRE)   # a rejected claim takes no payment
        r = self.svc.resubmit_claim(ORG, c["id"], "9500", "Added the referral form", PRE); self.assertEqual((r["status"], r["amount"], r["resubmissions"]), ("SUBMITTED", "9500.00", 1))
        a = self.svc.pay_claim(ORG, c["id"], dict(amount="4000", payment_ref="PAY-1", date="2026-02-10"), PRE); self.assertEqual((a["status"], a["outstanding"]), ("PARTIALLY_PAID", "5500.00"))
        with self.assertRaises(HealthError): self.svc.pay_claim(ORG, c["id"], dict(amount="4000", payment_ref="pay 1", date="2026-02-11"), PRE)       # same payment reference
        with self.assertRaises(HealthError): self.svc.pay_claim(ORG, c["id"], dict(amount="5500.01", payment_ref="PAY-2", date="2026-02-11"), PRE)    # more than outstanding
        with self.assertRaises(HealthError): self.svc.pay_claim(ORG, c["id"], dict(amount="100", payment_ref="PAY-3", date="2026-03-01"), PRE)         # future date
        full = self.svc.pay_claim(ORG, c["id"], dict(amount="5500", payment_ref="PAY-2", date="2026-02-12"), PRE); self.assertEqual((full["status"], full["outstanding"]), ("PAID", "0.00"))
        with self.assertRaises(HealthStateError): self.svc.pay_claim(ORG, c["id"], dict(amount="1", payment_ref="PAY-9", date="2026-02-12"), PRE)
        with self.assertRaises(HealthStateError): self.svc.reject_claim(ORG, c["id"], "NOT_COVERED", "", PRE)

    def test_resubmission_limit_and_writeoff_needs_a_second_person(self):
        c = self.claim(amount="2000")
        for n in range(3):
            self.svc.reject_claim(ORG, c["id"], "TARIFF_DISPUTE", "", PRE); self.svc.resubmit_claim(ORG, c["id"], None, f"Tariff query {n}", PRE)
        self.svc.reject_claim(ORG, c["id"], "TARIFF_DISPUTE", "", PRE)
        with self.assertRaises(HealthStateError): self.svc.resubmit_claim(ORG, c["id"], None, "Fourth try", PRE)
        w = self.svc.request_writeoff(ORG, c["id"], "Payer will not reverse the decision", PRE); self.assertEqual(w["writeoff"]["amount"], "2000.00")
        with self.assertRaises(HealthStateError): self.svc.request_writeoff(ORG, c["id"], "Asking a second time again", PRE)
        with self.assertRaises(HealthForbiddenError): self.svc.decide_writeoff(ORG, c["id"], True, "", PRE)
        done = self.svc.decide_writeoff(ORG, c["id"], True, "", MGR); self.assertEqual((done["status"], done["written_off"], done["outstanding"]), ("WRITTEN_OFF", "2000.00", "0.00"))

    def test_receivables_ageing_and_payer_reconciliation(self):
        p = self.payer(); a = self.claim(p, "1000", "R/1"); self.clock.d = date(2026, 4, 20); b = self.claim(p, "3000", "R/2")
        self.svc.pay_claim(ORG, b["id"], dict(amount="500", payment_ref="RP-1", date="2026-04-20"), PRE)
        ar = self.svc.receivables_ageing(ORG, self.fid, PRE)["totals"]; self.assertEqual((ar["0-30"], ar["61-90"], ar["total"]), ("2500.00", "1000.00", "3500.00"))
        ok = self.svc.payer_reconciliation(ORG, self.fid, p["id"], dict(start="2026-04-01", end="2026-04-30", statement_amount="500"), PRE); self.assertEqual((ok["status"], ok["difference"]), ("RECONCILED", "0.00"))
        bad = self.svc.payer_reconciliation(ORG, self.fid, p["id"], dict(start="2026-04-01", end="2026-04-30", statement_amount="650"), PRE); self.assertEqual((bad["status"], bad["difference"], bad["recorded_amount"]), ("DIFFERENCE", "150.00", "500.00"))
        self.assertEqual(self.svc.dashboard(ORG, self.fid, MGR)["metrics"]["unreconciled"]["value"], 1)
        with self.assertRaises(HealthError): self.svc.resolve_reconciliation(ORG, bad["id"], "short", PRE)
        self.svc.resolve_reconciliation(ORG, bad["id"], "Payer included a payment from the previous month", PRE)
        self.assertEqual(self.svc.dashboard(ORG, self.fid, MGR)["metrics"]["unreconciled"]["value"], 0)
        self.assertEqual(self.svc.claims_summary(ORG, self.fid, PRE)["pending"], 2)

    def test_revenue_receipts_and_refunds(self):
        fee = self.svc.create_fee(ORG, self.fid, dict(name="Consultation fee", service_category="OUTPATIENT_SERVICES", price="2000", effective_from="2026-01-01"), PRE)
        with self.assertRaises(HealthError): self.svc.create_fee(ORG, self.fid, dict(name="consultation fee", service_category="OUTPATIENT_SERVICES", price="2500", effective_from="2026-01-01"), PRE)
        r = self.svc.record_receipt(ORG, self.fid, dict(fee_id=fee["id"], amount="2000", date="2026-02-10", method="CASH"), PRE); self.assertRegex(r["ref"], r"^RCT-[0-9A-F]{8}$")
        self.svc.record_receipt(ORG, self.fid, dict(service_category="PROCEDURES", amount="5000.50", date="2026-02-11", method="CARD"), PRE)
        with self.assertRaises(HealthError): self.svc.record_receipt(ORG, self.fid, dict(service_category="PROCEDURES", amount="1", date="2026-03-11", method="CARD"), PRE)
        with self.assertRaises(HealthError): self.svc.record_receipt(ORG, self.fid, dict(service_category="PROCEDURES", amount="1", date="2026-02-11", method="BARTER"), PRE)
        x = self.svc.request_refund(ORG, r["id"], "500", "Overcharged at the till", PRE)
        with self.assertRaises(HealthError): self.svc.request_refund(ORG, r["id"], "1600", "Pending plus this too much", PRE)
        with self.assertRaises(HealthForbiddenError): self.svc.decide_refund(ORG, r["id"], x["id"], True, "", PRE)
        self.svc.decide_refund(ORG, r["id"], x["id"], True, "", MGR)
        s = self.svc.revenue_summary(ORG, self.fid, PRE); self.assertEqual((s["net_total"], {r["category"]: r["net"] for r in s["rows"]}), ("6500.50", {"OUTPATIENT_SERVICES": "1500.00", "PROCEDURES": "5000.50"}))
        self.svc.retire_fee(ORG, fee["id"], "Prices revised", PRE)


class TestAssetsAndStaffing(Base):
    def asset(self, tag="EQ-XR1", **kw):
        d = dict(tag=tag, name="Ultrasound scanner", category="DIAGNOSTIC_EQUIPMENT", dept_id=self.opd["id"], location="Room 2", acquisition_date="2025-06-01", cost="1500000", warranty_until="2027-06-01", maintenance_interval_days="90"); d.update(kw)
        return self.svc.create_asset(ORG, self.fid, d, PRE)

    def test_register_maintenance_schedule_downtime_and_evidence(self):
        a = self.asset(); ev = self.evidence()
        with self.assertRaises(HealthError): self.asset("eq xr1".replace(" ", "-"))
        with self.assertRaises(HealthError): self.asset("EQ-2", acquisition_date="2027-01-01")
        self.assertEqual([x["next_due"] for x in self.svc.list_assets(ORG, self.fid, PRE)], ["2025-08-30"])
        due = self.svc.maintenance_due(ORG, self.fid, PRE); self.assertEqual((due[0]["kind"], due[0]["overdue"]), ("SCHEDULE", True))
        m = self.svc.request_maintenance(ORG, a["id"], dict(kind="PREVENTIVE", description="Quarterly service", due_date="2026-02-20", evidence_ids=[ev.id]), PRE)
        self.assertEqual([x["kind"] for x in self.svc.maintenance_due(ORG, self.fid, PRE)], ["REQUEST"])
        self.svc.complete_maintenance(ORG, m["id"], dict(completed_date="2026-02-14", cost="25000", downtime_days=2, work_note="Probe replaced and tested"), PRE)
        self.assertEqual(self.svc.list_assets(ORG, self.fid, PRE)[0]["next_due"], "2026-05-15")
        self.assertEqual(self.svc.downtime_summary(ORG, self.fid, PRE), [dict(tag="EQ-XR1", asset="Ultrasound scanner", jobs=1, downtime_days=2, cost="25000.00")])
        self.assertEqual(self.svc.link_asset_evidence(ORG, a["id"], [ev.id], PRE)["evidence"][0]["filename"], "dn.pdf")
        with self.assertRaises(HealthStateError): self.svc.complete_maintenance(ORG, m["id"], dict(completed_date="2026-02-14", work_note="Again"), PRE)

    def test_maintenance_cost_counts_against_the_budget_unless_bought_through_a_po(self):
        b = self.budget(); a = self.asset(); mid = b["lines"][2]["line_id"]
        m = self.svc.request_maintenance(ORG, a["id"], dict(kind="CORRECTIVE", description="Screen fault", due_date="2026-02-16"), PRE); self.svc.complete_maintenance(ORG, m["id"], dict(completed_date="2026-02-15", cost="12000", downtime_days=1, work_note="Screen replaced"), PRE)
        row = {x["line_id"]: x for x in self.svc.execution(ORG, self.fid, b["id"], PRE)["rows"]}[mid]; self.assertEqual((row["spent"], row["available"]), ("12000.00", "38000.00"))
        p = self.po(qty="1", price="5000", cat="MAINTENANCE"); m2 = self.svc.request_maintenance(ORG, a["id"], dict(kind="CORRECTIVE", description="Second fault", due_date="2026-02-16"), PRE)
        self.svc.complete_maintenance(ORG, m2["id"], dict(completed_date="2026-02-15", cost="5000", work_note="Done via PO", po_id=p["id"]), PRE)
        row = {x["line_id"]: x for x in self.svc.execution(ORG, self.fid, b["id"], PRE)["rows"]}[mid]; self.assertEqual(row["spent"], "12000.00")      # not counted twice

    def test_spending_on_a_line_with_no_budget_is_shown_and_counted_in_the_dashboard(self):
        b = self.budget(lines=[dict(dept_id=self.opd["id"], category="MEDICAL_SUPPLIES", amount="100000")]); a = self.asset()
        m = self.svc.request_maintenance(ORG, a["id"], dict(kind="CORRECTIVE", description="Screen fault", due_date="2026-02-16"), PRE)
        self.svc.complete_maintenance(ORG, m["id"], dict(completed_date="2026-02-15", cost="12000", downtime_days=1, work_note="Screen replaced"), PRE)
        x = self.svc.execution(ORG, self.fid, b["id"], PRE)
        self.assertEqual(x["totals"]["spent"], "0.00"); self.assertEqual(x["totals"]["unbudgeted_spent"], "12000.00"); self.assertEqual(x["totals"]["total_spent"], "12000.00")
        self.assertEqual([(u["dept"], u["category"], u["spent"]) for u in x["unbudgeted"]], [("Outpatient", "MAINTENANCE", "12000.00")])
        d = self.svc.dashboard(ORG, self.fid, PRE)["metrics"]
        self.assertEqual(d["spent"]["value"], "12000.00"); self.assertEqual(d["available"]["value"], "88000.00")        # total budget less all spending, including the unbudgeted spend

    def test_retirement_needs_a_second_person_and_keeps_the_record(self):
        a = self.asset()
        with self.assertRaises(HealthError): self.svc.request_retirement(ORG, a["id"], "old", PRE)
        self.svc.request_retirement(ORG, a["id"], "Beyond economic repair after the fault", PRE)
        with self.assertRaises(HealthForbiddenError): self.svc.decide_retirement(ORG, a["id"], True, "", PRE)
        r = self.svc.decide_retirement(ORG, a["id"], True, "", MGR); self.assertEqual(r["status"], "RETIRED"); self.assertIn("ledger", r["accounting_note"])
        self.assertEqual(self.svc.list_assets(ORG, self.fid, PRE)[0]["history"][-1]["event"], "RETIRED")
        with self.assertRaises(HealthStateError): self.svc.request_maintenance(ORG, a["id"], dict(kind="PREVENTIVE", description="Service it", due_date="2026-03-01"), PRE)

    def test_staffing_costs_are_aggregate_restricted_and_approved(self):
        b = self.budget(); sid = b["lines"][1]["line_id"]
        for who in (PRE, ADM, AUD, MGR):
            with self.assertRaises(HealthForbiddenError): self.svc.record_staffing(ORG, self.fid, dict(dept_id=self.opd["id"], month="2026-01", headcount=10, gross_cost="800000", source="Payroll summary Jan"), who)
        s = self.svc.record_staffing(ORG, self.fid, dict(dept_id=self.opd["id"], month="2026-01", headcount=10, gross_cost="800000", allowances="50000", source="Payroll summary Jan"), FIN)
        self.assertTrue({"employee", "name", "salary", "employee_id"}.isdisjoint(s.keys()))
        with self.assertRaises(HealthError): self.svc.record_staffing(ORG, self.fid, dict(dept_id=self.opd["id"], month="2026-01", headcount=11, gross_cost="1", source="Duplicate month"), FIN)
        row = lambda: {x["line_id"]: x for x in self.svc.execution(ORG, self.fid, b["id"], PRE)["rows"]}[sid]
        self.assertEqual(row()["spent"], "0.00")                                                                                 # not counted until approved
        with self.assertRaises(HealthForbiddenError): self.svc.decide_staffing(ORG, s["id"], True, "", FIN)
        with self.assertRaises(HealthForbiddenError): self.svc.decide_staffing(ORG, s["id"], True, "", MGR)                     # manager lacks the staffing permission
        ROLES["u-owner2"] = Role.OWNER; self.svc.decide_staffing(ORG, s["id"], True, "", "u-owner2")
        self.assertEqual((row()["spent"], row()["available"]), ("850000.00", "-350000.00")); self.assertTrue(row()["overspent"])
        with self.assertRaises(HealthForbiddenError): self.svc.list_staffing(ORG, self.fid, AUD)
        self.assertEqual(self.svc.list_staffing(ORG, self.fid, FIN)["by_department"][0]["total"], "850000.00")


class TestDashboardAndReports(Base):
    def scenario(self):
        b = self.budget(); it = self.item(reorder_level="500"); p = self.po(item=it, qty="100", price="500")
        self.svc.receive_goods(ORG, p["id"], dict(lines=[dict(line_no=1, qty="60")], delivery_note="D1"), PRE)
        i = self.svc.record_invoice(ORG, p["id"], dict(invoice_no="V-1", amount="30000", invoice_date="2026-02-10"), PRE); self.svc.verify_invoice(ORG, i["id"], "", MGR)
        self.svc.record_receipt(ORG, self.fid, dict(service_category="OUTPATIENT_SERVICES", amount="7000", date="2026-02-10", method="CASH"), PRE)
        pay = self.svc.create_payer(ORG, self.fid, dict(name="Sunrise Health Insurance", kind="INSURER"), PRE)
        c = self.svc.create_claim(ORG, self.fid, dict(payer_id=pay["id"], external_ref="S/1", service_category="OUTPATIENT_SERVICES", service_month="2026-01", amount="9000"), PRE); self.svc.submit_claim(ORG, c["id"], PRE)
        self.svc.pay_claim(ORG, c["id"], dict(amount="2000", payment_ref="PAY-A1", date="2026-02-12"), PRE); return b

    def test_dashboard_numbers_reconcile_to_underlying_records(self):
        b = self.scenario(); m = self.svc.dashboard(ORG, self.fid, MGR)["metrics"]; ex = self.svc.execution(ORG, self.fid, b["id"], MGR)["totals"]
        self.assertEqual((m["budget_total"]["value"], m["spent"]["value"], m["committed"]["value"], m["available"]["value"], m["utilisation"]["value"]), ("850000.00", "30000.00", "20000.00", "800000.00", "3.53"))
        self.assertEqual((ex["budget"], ex["spent"], ex["committed"], ex["available"]), ("850000.00", "30000.00", "20000.00", "800000.00"))
        self.assertEqual((m["receipts"]["value"], m["payables"]["value"], m["inventory_value"]["value"], m["low_stock"]["value"]), ("7000.00", "30000.00", "30000.00", 1))
        self.assertEqual((m["claims_submitted"]["value"], m["claims_pending"]["value"], m["receivables"]["value"], m["claim_payments"]["value"]), (1, 1, "7000.00", "2000.00"))
        for k in ("spent", "utilisation", "payables"): self.assertTrue(m[k]["formula"] and m[k]["source"] and m[k]["drill"])

    def test_unavailable_restricted_and_zero_are_different(self):
        m = self.svc.dashboard(ORG, self.fid, MGR)["metrics"]
        self.assertEqual((m["budget_total"]["state"], m["budget_total"]["value"]), ("UNAVAILABLE", None)); self.assertEqual((m["receipts"]["state"], m["receipts"]["value"]), ("OK", "0.00"))
        a = self.svc.dashboard(ORG, self.fid, ADM)["metrics"]                                                                    # admin and auditor do not hold the claims permission
        self.assertEqual((a["receivables"]["state"], a["receivables"]["value"], a["claims_pending"]["state"]), ("RESTRICTED", None, "RESTRICTED"))
        self.assertEqual(self.svc.dashboard(ORG, self.fid, AUD)["metrics"]["claims_paid"]["state"], "RESTRICTED"); self.assertEqual(self.svc.dashboard(ORG, self.fid, MGR)["metrics"]["claims_paid"]["state"], "OK")

    def test_report_freeze_approval_export_and_claims_redaction(self):
        self.scenario(); r = self.svc.create_report(ORG, self.fid, dict(title="=Q1 facility performance", period_start="2026-01-01", period_end="2026-03-31"), PRE)
        self.assertIsNone(r["snapshot"]); r = self.svc.submit_report(ORG, r["id"], PRE); self.assertEqual((r["status"], r["version"], len(r["fingerprint"])), ("SUBMITTED", 1, 64))
        with self.assertRaises(HealthStateError): self.svc.export_csv(ORG, r["id"], MGR)
        with self.assertRaises(HealthForbiddenError): self.svc.decide_report(ORG, r["id"], True, "", PRE)
        self.svc.decide_report(ORG, r["id"], True, "", MGR)
        seen = self.svc.get_report(ORG, r["id"], AUD)["snapshot"]; self.assertTrue(seen["claims_restricted"]); self.assertNotIn("claims", seen); self.assertNotIn("claims_pending", seen["dashboard"]["metrics"])
        self.assertIn("claims", self.svc.get_report(ORG, r["id"], MGR)["snapshot"])
        out = self.svc.export_csv(ORG, r["id"], AUD); rows = list(csv.reader(io.StringIO(out["content"])))
        self.assertTrue(rows[0][0].startswith("CONFIDENTIAL")); text = out["content"]; self.assertIn("'=Q1 facility performance", text); self.assertNotIn("Claims pending", text); self.assertNotIn("PAYER RECEIVABLES", text)
        full = self.svc.export_csv(ORG, r["id"], MGR)["content"]; self.assertIn("Claims pending", full); self.assertIn("PAYER RECEIVABLES AGEING", full); self.assertIn("LIMITATIONS", full)
        raw = self.w.store.get("hc_report", f"{ORG}:{r['id']}"); raw["snapshot"]["payables"]["totals"]["total"] = "1.00"; self.svc._put("hc_report", ORG, raw)
        with self.assertRaises(HealthStateError): self.svc.export_csv(ORG, r["id"], MGR)

    def test_state_survives_a_restart_and_a_second_service_instance_sees_it(self):
        b = self.scenario(); fresh = HealthService(self.w.store, self.w.vault, None, log=lambda *a: None, now=self.clock, can=can)
        self.assertEqual(fresh.execution(ORG, self.fid, b["id"], MGR)["totals"], self.svc.execution(ORG, self.fid, b["id"], MGR)["totals"])
        self.assertEqual(fresh.stock_levels(ORG, self.fid, MGR)["total_value"], "30000.00")

    def test_roles_matrix(self):
        P = lambda r: {p for p in ROLE_PERMISSIONS[r] if p.startswith("health:")}
        self.assertEqual(P(Role.ADMINISTRATOR), {"health:read", "health:prepare", "health:admin"})            # platform admin: no claims, no staffing, no approvals
        self.assertEqual(P(Role.AUDITOR), {"health:read"}); self.assertEqual(P(Role.EXTERNAL_AUDITOR), {"health:read"}); self.assertEqual(P(Role.READ_ONLY), {"health:read"})
        self.assertNotIn("health:approve", P(Role.ACCOUNTANT)); self.assertNotIn("health:approve", P(Role.FINANCE_OFFICER)); self.assertEqual(P(Role.INVESTOR_REVIEWER), set())


class TestEveryStateChangeReachesTheAuditTrail(Base):
    """Stage 1 audit-coverage fix: these seven actions used to change data and keep only the record's own history,
    without an entry in the organisation audit trail. Each must now log exactly one event naming the actor."""

    def setUp(self):
        super().setUp(); self.budget(lines=[dict(dept_id=self.opd["id"], category="MEDICAL_SUPPLIES", amount="9000000"), dict(dept_id=self.opd["id"], category="MAINTENANCE", amount="500000")])

    def last(self, action):
        hits = [e for e in self.events if e[0] == action]
        self.assertEqual(len(hits), 1, f"{action}: expected exactly one audit event, got {len(hits)}")
        self.assertEqual(hits[0][1], PRE, "the event must name the person who acted")
        return hits[0]

    def test_requisition_edit_and_quote(self):
        line = dict(description="Examination gloves", qty="10", unit_price="500")
        r = self.svc.create_requisition(ORG, self.fid, dict(dept_id=self.opd["id"], category="MEDICAL_SUPPLIES", lines=[line], justification="Monthly restock"), PRE)
        self.svc.update_requisition(ORG, r["id"], dict(dept_id=self.opd["id"], category="MEDICAL_SUPPLIES", lines=[line], justification="Monthly restock, revised"), PRE)
        self.assertEqual(self.last("HC_REQ_EDITED")[2], r["id"])
        self.svc.add_quote(ORG, r["id"], dict(supplier_id=self.supplier()["id"], amount="4800"), PRE)
        self.assertEqual(self.last("HC_QUOTE_ADDED")[2], r["id"])

    def test_stock_issue_and_transfer(self):
        it = self.item("AUD-1"); p = self.po(item=it, qty="20", price="100")
        self.svc.receive_goods(ORG, p["id"], dict(lines=[dict(line_no=1, qty="20", location="STORE")], delivery_note="DN-A1"), PRE)
        self.svc.issue_stock(ORG, it["id"], dict(qty="2", location="STORE", purpose="Ward round supplies"), PRE)
        self.assertEqual(self.last("HC_STOCK_ISSUED")[2], it["id"])
        self.svc.transfer_stock(ORG, it["id"], dict(qty="3", from_location="STORE", to_location="WARD"), PRE)
        self.assertEqual(self.last("HC_STOCK_TRANSFERRED")[2], it["id"])

    def test_asset_condition_evidence_and_maintenance_cancel(self):
        a = self.svc.create_asset(ORG, self.fid, dict(tag="EQ-A1", name="Scanner", category="DIAGNOSTIC_EQUIPMENT", dept_id=self.opd["id"], location="Room 2",
                                                       acquisition_date="2025-06-01", cost="1500000", warranty_until="2027-06-01", maintenance_interval_days="90"), PRE)
        self.svc.set_condition(ORG, a["id"], "FAIR", "Worn probe", PRE)
        self.assertEqual(self.last("HC_ASSET_CONDITION_SET")[2], a["id"])
        self.svc.link_asset_evidence(ORG, a["id"], [self.evidence().id], PRE)
        self.assertEqual(self.last("HC_ASSET_EVIDENCE_LINKED")[2], a["id"])
        m = self.svc.request_maintenance(ORG, a["id"], dict(kind="CORRECTIVE", description="Screen fault", due_date="2026-02-16"), PRE)
        self.svc.cancel_maintenance(ORG, m["id"], "Raised twice by mistake", PRE)
        self.assertEqual(self.last("HC_MAINT_CANCELLED")[2], m["id"])


if __name__ == "__main__":

    unittest.main()
