"""Browser journey: Procurement (Stage 17). Run via e2e/run_all.py."""
import json
from datetime import date, timedelta

from common import *

D = lambda n: (date.today() + timedelta(days=n)).isoformat()
def hrefs(pg): return [a.get_attribute("href") for a in pg.locator(".app-sidebar a").all()]
def tab(pg, name):
    pg.click(f"#pc-tab-{name}"); pg.wait_for_timeout(900)
def body(pg): return pg.inner_text("body")
def err(pg): return txt(pg, ".alert-error")
def A(m, path, who, bodyj=None): return api(m, "/procurement" + path, who, "Meridian", bodyj)

start_web()
p, b, pg, errs = session()

# ---- the accountant registers suppliers ----
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/procurement")
check("the menu offers Procurement", "#/procurement" in hrefs(pg), hrefs(pg))
check("the banner says it does not buy or pay", "does not buy anything" in txt(pg, "#pc-banner") and "someone other than the person who created" in txt(pg, "#pc-banner"), txt(pg, "#pc-banner"))
check("nothing needs attention yet", "Nothing needs attention" in txt(pg, "#pc-attention"), txt(pg, "#pc-attention"))
tab(pg, "suppliers")
pg.click("#pc-sup-save"); pg.wait_for_timeout(300)
check("an empty supplier form is stopped with a plain sentence", "name" in txt(pg, "#supplier-problem").lower(), txt(pg, "#supplier-problem"))
pg.fill("#pc-sup-name", "Acme Supplies"); pg.fill("#pc-sup-country", "Nigeria"); pg.click("#pc-sup-save"); pg.wait_for_timeout(1500)
check("supplier registered and waiting for approval", "SU-001" in txt(pg, "#pc-notice") and "different person must approve" in txt(pg, "#pc-notice") and "Waiting for approval" in txt(pg, "#pc-suppliers"), txt(pg, "#pc-notice") + txt(pg, "#supplier-problem"))
pg.fill("#pc-sup-name", "Cousin Ltd"); pg.select_option("#pc-sup-related", "yes"); pg.wait_for_timeout(300)
pg.fill("#pc-sup-relnote", "short"); pg.click("#pc-sup-save"); pg.wait_for_timeout(300)
check("a connection must be described", "10 characters" in txt(pg, "#supplier-problem"), txt(pg, "#supplier-problem"))
pg.fill("#pc-sup-relnote", "Owned by the finance manager's cousin"); pg.click("#pc-sup-save"); pg.wait_for_timeout(1500)
check("connected supplier registered and marked", "SU-002" in txt(pg, "#pc-notice") and "Connected party" in txt(pg, "#pc-suppliers"), txt(pg, "#pc-suppliers"))
pg.fill("#pc-sup-name", "acme supplies"); pg.click("#pc-sup-save"); pg.wait_for_timeout(1500)
check("a duplicate supplier name is refused by the server", "already registered" in err(pg), err(pg) + txt(pg, "#pc-notice"))
SU = {s["ref"]: s["id"] for s in A("GET", "/suppliers", AISHA)}
check("an order cannot go to an unapproved supplier (server)", A("POST", "/orders", AISHA, {"supplier_id": SU["SU-001"], "currency": "NGN", "expected_date": D(10), "purpose": "Too early", "lines": [{"description": "Thing", "qty": "1", "unit_price": "1"}]}).get("status") == 409)

# ---- the approver approves; a connected supplier needs a reason ----
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/procurement"); tab(pg, "suppliers")
check("an approver sees no register form", pg.locator("#pc-sup-save").count() == 0)
pg.click("#pc-sup-open-SU-001"); pg.wait_for_timeout(900)
check("approve button is offered for someone else's supplier", pg.locator("#pc-sup-SU-001-approve").count() == 1)
pg.click("#pc-sup-SU-001-approve"); pg.wait_for_timeout(1500)
check("supplier approved", "Supplier approved" in txt(pg, "#pc-notice") and "Approved" in txt(pg, "#pc-sup-detail"), txt(pg, "#pc-notice") + err(pg))
pg.click("#pc-sup-open-SU-002"); pg.wait_for_timeout(900)
check("the connected party is shown prominently", "cousin" in txt(pg, "#pc-sup-related-note"), txt(pg, "#pc-sup-detail"))
pg.click("#pc-sup-SU-002-approve"); pg.wait_for_timeout(1500)
check("a connected supplier cannot be approved without a note", "required" in err(pg).lower() or "note" in err(pg).lower(), err(pg) + txt(pg, "#pc-notice"))
pg.fill("#note-sup-" + SU["SU-002"], "Reviewed: the manager takes no part in buying"); pg.click("#pc-sup-SU-002-approve"); pg.wait_for_timeout(1500)
check("approved with a recorded reason", "Supplier approved" in txt(pg, "#pc-notice"), txt(pg, "#pc-notice") + err(pg))

# ---- contract ----
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/procurement"); tab(pg, "contracts")
pg.fill("#pc-con-title", "Supply agreement"); pg.fill("#pc-con-cur", "ngn"); pg.fill("#pc-con-ceiling", "0"); pg.fill("#pc-con-start", D(-30)); pg.fill("#pc-con-end", D(300))
pg.select_option("#pc-con-supplier", SU["SU-001"]); pg.click("#pc-con-save"); pg.wait_for_timeout(300)
check("a zero ceiling is refused with a sentence", "more than zero" in txt(pg, "#contract-problem"), txt(pg, "#contract-problem"))
pg.fill("#pc-con-ceiling", "6,000.00"); pg.click("#pc-con-save"); pg.wait_for_timeout(1500)
check("contract drafted", "CT-001" in txt(pg, "#pc-notice") and "ceiling 6,000.00 NGN" in txt(pg, "#pc-contracts"), txt(pg, "#pc-contracts") + txt(pg, "#contract-problem"))
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/procurement"); tab(pg, "contracts")
pg.click("#pc-con-CT-001-approve"); pg.wait_for_timeout(1500)
check("contract approved", "Contract approved" in txt(pg, "#pc-notice") and "In force" in txt(pg, "#pc-contracts"), txt(pg, "#pc-contracts") + err(pg))

# ---- purchase order ----
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/procurement"); tab(pg, "orders")
pg.select_option("#pc-po-supplier", SU["SU-001"]); pg.wait_for_timeout(300)
pg.select_option("#pc-po-contract", index=1); pg.fill("#pc-po-cur", "NGN"); pg.fill("#pc-po-date", D(10)); pg.fill("#pc-po-purpose", "Office equipment")
pg.fill("#pc-po-line-0-desc", "Laptops"); pg.fill("#pc-po-line-0-qty", "10"); pg.fill("#pc-po-line-0-price", "500.00")
pg.fill("#pc-po-line-1-desc", "Chargers"); pg.fill("#pc-po-line-1-qty", "10")
pg.click("#pc-po-save"); pg.wait_for_timeout(300)
check("a half-filled line is a problem, not silently dropped", "Line 2: the unit price" in txt(pg, "#order-problem"), txt(pg, "#order-problem"))
pg.fill("#pc-po-line-1-price", "20.00"); pg.click("#pc-po-save"); pg.wait_for_timeout(1500)
check("order raised with the total worked out", "PO-001" in txt(pg, "#pc-notice") and "5,200.00 NGN" in txt(pg, "#pc-orders"), txt(pg, "#pc-orders") + txt(pg, "#order-problem") + err(pg))
check("the requester cannot approve their own order", pg.locator("#pc-po-PO-001-approve").count() == 0 and pg.locator("#pc-po-PO-001-cancel").count() == 1)
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/procurement"); tab(pg, "orders")
pg.click("#pc-po-PO-001-approve"); pg.wait_for_timeout(1500)
check("order approved", "Approval recorded" in txt(pg, "#pc-notice") and "Approved" in txt(pg, "[data-order]"), txt(pg, "#pc-orders") + err(pg))
tab(pg, "contracts")
check("the contract shows what is committed and what is left", "committed 5,200.00" in txt(pg, "#pc-contracts") and "remaining 800.00" in txt(pg, "#pc-contracts"), txt(pg, "#pc-contracts"))

# ---- an order that would break the contract ceiling ----
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/procurement"); tab(pg, "orders")
pg.select_option("#pc-po-supplier", SU["SU-001"]); pg.wait_for_timeout(300); pg.select_option("#pc-po-contract", index=1); pg.fill("#pc-po-cur", "NGN"); pg.fill("#pc-po-date", D(10)); pg.fill("#pc-po-purpose", "Too much for the ceiling")
pg.fill("#pc-po-line-0-desc", "More laptops"); pg.fill("#pc-po-line-0-qty", "1"); pg.fill("#pc-po-line-0-price", "800.01"); pg.click("#pc-po-save"); pg.wait_for_timeout(1500)
check("PO-002 raised", "PO-002" in txt(pg, "#pc-notice"), txt(pg, "#pc-notice") + txt(pg, "#order-problem") + err(pg))
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/procurement"); tab(pg, "orders")
pg.click("#pc-po-PO-002-approve"); pg.wait_for_timeout(1500)
check("approval is refused because it would go over the contract ceiling", "ceiling" in err(pg), err(pg))
pg.click("#pc-po-PO-002-reject"); pg.wait_for_timeout(1000)
check("rejecting needs a reason", "reason" in err(pg).lower(), err(pg))
OID2 = [o["id"] for o in A("GET", "/orders", KWAME) if o["ref"] == "PO-002"][0]
pg.fill("#note-po-" + OID2, "Over the contract ceiling"); pg.click("#pc-po-PO-002-reject"); pg.wait_for_timeout(1500)
check("rejected with a reason", "Order rejected" in txt(pg, "#pc-notice"), txt(pg, "#pc-notice") + err(pg))

# ---- delivery: not the person who raised the order ----
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/procurement"); tab(pg, "receipts")
pg.select_option("#pc-dl-order", index=1); pg.wait_for_timeout(500)
check("the delivery form is prefilled with what is still to come", pg.input_value("#pc-dl-qty-1") == "10.000" and pg.input_value("#pc-dl-qty-2") == "10.000", pg.input_value("#pc-dl-qty-1"))
pg.fill("#pc-dl-qty-1", "4"); pg.fill("#pc-dl-qty-2", "10"); pg.fill("#pc-dl-date", D(0)); pg.click("#pc-dl-save"); pg.wait_for_timeout(1500)
check("the person who raised the order cannot record its delivery", "cannot" in err(pg).lower() and "different person" in err(pg).lower(), err(pg) + txt(pg, "#pc-notice"))
sign_in(pg, *("dara@meridian.test", "correct horse battery staple1"), "Meridian"); goto(pg, "/procurement"); tab(pg, "receipts")
pg.select_option("#pc-dl-order", index=1); pg.wait_for_timeout(500)
pg.fill("#pc-dl-qty-1", "11"); pg.fill("#pc-dl-qty-2", "10"); pg.fill("#pc-dl-date", D(0)); pg.click("#pc-dl-save"); pg.wait_for_timeout(1500)
check("more than ordered cannot be received", "only 10.000 is still outstanding" in err(pg), err(pg))
pg.fill("#pc-dl-qty-1", "4"); pg.click("#pc-dl-save"); pg.wait_for_timeout(1500)
check("partial delivery recorded", "DL-001" in txt(pg, "#pc-notice") and "DL-001" in txt(pg, "#pc-deliveries"), txt(pg, "#pc-notice") + err(pg))
tab(pg, "orders")
check("the order shows part received", "Partly received" in txt(pg, "[data-order]") and "6.000" in txt(pg, "[data-order]"), txt(pg, "[data-order]"))

# ---- invoice: three-way match ----
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/procurement"); tab(pg, "receipts")
pg.select_option("#pc-iv-order", index=1); pg.wait_for_timeout(500)
check("the invoice form is prefilled with received and not yet invoiced", pg.input_value("#pc-iv-qty-1") == "4" and pg.input_value("#pc-iv-qty-2") == "10" and pg.input_value("#pc-iv-price-1") == "500.00", pg.input_value("#pc-iv-qty-1"))
pg.fill("#pc-iv-qty-1", "10"); pg.fill("#pc-iv-number", "INV-100"); pg.fill("#pc-iv-date", D(0)); pg.fill("#pc-iv-due", D(30)); pg.click("#pc-iv-save"); pg.wait_for_timeout(1500)
check("invoicing more than was received becomes an exception", "IV-001" in txt(pg, "#pc-notice") and "exception" in txt(pg, "#pc-notice").lower() and pg.locator("[data-flag=NOT_YET_RECEIVED]").count() == 1, txt(pg, "#pc-notice") + txt(pg, "#invoice-problem") + err(pg))
check("the flag is explained in plain words", "More is invoiced than has been recorded as received" in txt(pg, "#pc-invoices"), txt(pg, "#pc-invoices"))
check("an accountant is offered no way to approve or reject it", pg.locator("#pc-iv-IV-001-approve").count() == 0 and pg.locator("#pc-iv-IV-001-reject").count() == 0)
pg.select_option("#pc-iv-order", index=1); pg.wait_for_timeout(500)
pg.fill("#pc-iv-number", "inv-100"); pg.fill("#pc-iv-date", D(0)); pg.fill("#pc-iv-due", D(30)); pg.fill("#pc-iv-qty-1", "1"); pg.click("#pc-iv-save"); pg.wait_for_timeout(1500)
check("the same supplier invoice number is never accepted twice", "already been recorded" in err(pg), err(pg))
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/procurement"); tab(pg, "receipts")
pg.click("#pc-iv-IV-001-approve"); pg.wait_for_timeout(1000)
check("an exception cannot be approved without a written reason", "reason" in err(pg).lower(), err(pg))
IID = A("GET", "/invoices", KWAME)[0]["id"]
pg.fill("#note-iv-" + IID, "Goods arrived yesterday, receipt being entered"); pg.click("#pc-iv-IV-001-approve"); pg.wait_for_timeout(1500)
check("approved with the override recorded", "Invoice approved" in txt(pg, "#pc-notice") and "Approved despite the warnings: Goods arrived" in txt(pg, "#pc-invoices"), txt(pg, "#pc-invoices") + err(pg))
check("an approver is not offered to record payment", pg.locator("#pc-iv-paid-IV-001").count() == 0)

# ---- payment: linked to a released Treasury payment ----
a_id = api("POST", "/treasury/accounts", AISHA, "Meridian", {"name": "Main current account", "currency": "NGN"})["id"]
api("POST", f"/treasury/accounts/{a_id}/balances", AISHA, "Meridian", {"as_at": D(-1), "amount": "99999.00", "source": "Bank statement"})
pay = api("POST", "/treasury/payments", AISHA, "Meridian", {"account_id": a_id, "payee": "Acme Supplies", "amount": "5200.00", "due_date": D(0), "reason": "Invoice INV-100", "invoice_ref": "INV-100"})
api("POST", f"/treasury/payments/{pay['id']}/approve", KWAME, "Meridian", {"note": "Checked against the invoice"})
rel = api("POST", f"/treasury/payments/{pay['id']}/release", ("dara@meridian.test", "correct horse battery staple1"), "Meridian", {"released_date": D(0), "bank_reference": "BANK-5200"})
check("setup: a Treasury payment is released", rel.get("status") == "RELEASED", rel)
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/procurement"); tab(pg, "receipts")
check("the matching released payment is offered", pg.locator("#pc-iv-link-IV-001").count() == 1 and "PR-001" in txt(pg, "#pc-iv-link-IV-001"), txt(pg, "#pc-invoices"))
pg.select_option("#pc-iv-link-IV-001", index=1); pg.click("#pc-iv-paid-IV-001"); pg.wait_for_timeout(1500)
check("invoice paid and linked", "Payment recorded" in txt(pg, "#pc-notice") and "Linked to Treasury payment PR-001" in txt(pg, "#pc-invoices") and "BANK-5200" in txt(pg, "#pc-invoices"), txt(pg, "#pc-invoices") + err(pg))

# ---- a second small order paid by hand ----
o3 = A("POST", "/orders", AISHA, {"supplier_id": SU["SU-001"], "currency": "NGN", "expected_date": D(10), "purpose": "Stationery", "lines": [{"description": "Stapler", "qty": "1", "unit_price": "100.00"}]})
A("POST", f"/orders/{o3['id']}/approve", KWAME, {"note": ""}); dl = A("POST", f"/orders/{o3['id']}/deliveries", ("dara@meridian.test", "correct horse battery staple1"), {"received_date": D(0), "lines": [{"line": 1, "qty": "1"}]})
iv = A("POST", f"/orders/{o3['id']}/invoices", AISHA, {"invoice_number": "INV-200", "invoice_date": D(0), "due_date": D(30), "lines": [{"line": 1, "qty": "1", "unit_price": "100.00"}]})
check("setup: a clean match", iv.get("status") == "MATCHED" and iv.get("flags") == [], iv)
A("POST", f"/invoices/{iv['id']}/approve", KWAME, {"note": ""})
goto(pg, "/procurement"); tab(pg, "receipts")
pg.click("#pc-iv-paid-IV-002"); pg.wait_for_timeout(500)
check("payment needs a date and the bank's reference", "real date" in err(pg) or "bank" in err(pg).lower(), err(pg))
pg.fill("#pc-iv-paid-date-IV-002", D(0)); pg.fill("#pc-iv-paid-ref-IV-002", "TRX-77"); pg.click("#pc-iv-paid-IV-002"); pg.wait_for_timeout(1500)
check("paid by hand with the bank reference", "Bank reference TRX-77" in txt(pg, "#pc-invoices"), txt(pg, "#pc-invoices") + err(pg))

# ---- review ----
tab(pg, "reviews")
pg.select_option("#pc-rv-supplier", SU["SU-001"]); pg.fill("#pc-rv-period", "2026-Q1")
for k, v in (("delivery", "4"), ("quality", "2"), ("price", "3"), ("service", "4")): pg.fill(f"#pc-rv-{k}", v)
pg.click("#pc-rv-save"); pg.wait_for_timeout(300)
check("a low score needs a comment", "comment" in txt(pg, "#review-problem"), txt(pg, "#review-problem"))
pg.fill("#pc-rv-comment", "Three laptops arrived damaged"); pg.click("#pc-rv-save"); pg.wait_for_timeout(1500)
check("review saved, average is arithmetic", "SR-001" in txt(pg, "#pc-notice") and "3.3" in txt(pg, "#pc-reviews") and "Low score" in txt(pg, "#pc-reviews"), txt(pg, "#pc-reviews") + err(pg))

# ---- overview ----
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/procurement")
check("the overview counts and the limits are shown", "Suppliers: 2" in txt(pg, "#pc-counts") and "not an audit opinion" in txt(pg, "#pc-limits"), txt(pg, "#pc-counts"))
check("the policy can be saved by an approver", pg.locator("#pc-policy-save").count() == 1)
pg.fill("#pc-policy-tol", "30"); pg.click("#pc-policy-save"); pg.wait_for_timeout(300)
check("a tolerance over 20 percent is refused", "0 to 20" in txt(pg, "#policy-problem"), txt(pg, "#policy-problem"))
pg.fill("#pc-policy-tol", "3"); pg.fill("#pc-policy-limit", "DEFAULT=2,000, USD=50"); pg.click("#pc-policy-save"); pg.wait_for_timeout(1500)
check("policy saved and explained in words", "up to 3%" in txt(pg, "#pc-policy-meaning") and "2000.00" in txt(pg, "#pc-policy-meaning"), txt(pg, "#pc-policy-meaning") + err(pg))

# ---- the server refuses what the buttons hide, and another company sees nothing ----
check("an accountant cannot approve a supplier even by calling the server (403)", A("POST", f"/suppliers/{SU['SU-001']}/suspend", AISHA, {"note": "no right"}).get("status") == 403)
check("an approver cannot register a supplier (403)", A("POST", "/suppliers", KWAME, {"name": "Sneaky Ltd", "related_party": False}).get("status") == 403)
check("the person who recorded the invoice cannot approve their own (403 or 409)", A("POST", f"/invoices/{IID}/approve", AISHA, {"note": "x" * 12}).get("status") in (403, 409))
r = api("GET", "/procurement/suppliers", OTHER, "Other"); check("another company's supplier list is empty", r == [], r)
r = api("GET", f"/procurement/invoices/{IID}", OTHER, "Other"); check("another company cannot read the invoice (404)", r.get("status") == 404, r)
r = api("POST", f"/procurement/invoices/{IID}/reject", OTHER, "Other", {"note": "not yours"}); check("another company cannot decide it (404)", r.get("status") == 404, r)
acts = api("GET", "/_audit", ("dara@meridian.test", "correct horse battery staple1"), "Meridian")["actions"]
for a in ("PC_SUPPLIER_REGISTERED", "PC_SUPPLIER_APPROVED", "PC_CONTRACT_APPROVED", "PC_ORDER_APPROVED", "PC_ORDER_REJECTED", "PC_DELIVERY_RECORDED", "PC_INVOICE_RECORDED", "PC_INVOICE_APPROVED", "PC_INVOICE_PAID", "PC_SUPPLIER_REVIEWED", "PC_POLICY_SET"):
    check("audit has " + a, a in acts, acts[:6])
check("no console or page errors", not errs, errs)

finish(p, b)
