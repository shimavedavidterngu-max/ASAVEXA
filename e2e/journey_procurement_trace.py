"""Browser journey: Procurement Trace (Stage 6). Run via e2e/run_all.py.
The chain for one purchase order is built through the real services by different people, then read in the browser.
The browser user and the people making API calls are always different people."""
from datetime import date, timedelta

from common import *

D = lambda n: (date.today() + timedelta(days=n)).isoformat()
DARA_ = ("dara@meridian.test", "correct horse battery staple1")
def A(m, path, who, bodyj=None): return api(m, "/procurement" + path, who, "Meridian", bodyj)
def hrefs(pg): return [a.get_attribute("href") for a in pg.locator(".app-sidebar a").all()]
def steps(pg): return {s.get_attribute("data-stage"): s.inner_text() for s in pg.locator("#pc-trace-rail .pr-step").all()}
def shape(pg, stage): return pg.locator(f"#pc-trace-rail .pr-step[data-stage={stage}] .pr-bead").get_attribute("class")

# ---- seed: supplier (Aisha) approved by Kwame; two orders ----
s = A("POST", "/suppliers", AISHA, {"name": "Trace Supplies", "category": "GOODS", "country": "Nigeria", "related_party": False}); A("POST", f"/suppliers/{s['id']}/approve", KWAME, {"note": ""})
mk = lambda purpose, price: A("POST", "/orders", AISHA, {"supplier_id": s["id"], "currency": "NGN", "expected_date": D(10), "purpose": purpose, "lines": [{"description": "Reams of paper", "qty": "10", "unit_price": price}]})
bare = mk("Order with nothing after it", "50.00"); A("POST", f"/orders/{bare['id']}/approve", KWAME, {"note": ""})
full = mk("Order that goes all the way", "100.00"); A("POST", f"/orders/{full['id']}/approve", KWAME, {"note": ""})
A("POST", f"/orders/{full['id']}/deliveries", DARA_, {"received_date": D(0), "lines": [{"line": 1, "qty": "10"}]})
iv = A("POST", f"/orders/{full['id']}/invoices", AISHA, {"invoice_number": "TRACE-1", "invoice_date": D(0), "due_date": D(30), "lines": [{"line": 1, "qty": "10", "unit_price": "100.00"}]})
A("POST", f"/invoices/{iv['id']}/approve", KWAME, {"note": ""})
A("POST", f"/invoices/{iv['id']}/paid", AISHA, {"paid_date": D(0), "bank_reference": "BANK-77881"})
A("POST", f"/suppliers/{s['id']}/reviews", AISHA, {"period": "2026-Q1", "scores": {"delivery": 4, "quality": 4, "price": 4, "service": 4}, "comment": ""})

start_web()
p, b, pg, errs = session()
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/procurement")
pg.wait_for_selector("#pc-tab-trace", timeout=8000)
check("the workspace has a Trace tab", pg.locator("#pc-tab-trace").count() == 1)
pg.click("#pc-tab-trace"); pg.wait_for_selector("#pc-trace-order", timeout=8000)
check("before choosing an order nothing is claimed", pg.locator("#pc-trace").count() == 0 and "Choose a purchase order" in pg.inner_text("#pc-trace-empty"))

# ---- an order with nothing after it: every later step says so ----
pg.select_option("#pc-trace-order", bare["id"]); pg.wait_for_selector("#pc-trace-rail", timeout=8000)
t = steps(pg)
check("the rail has all seven steps in order", list(t.keys()) == ["supplier", "contract", "order", "delivery", "invoice", "payment", "review"], list(t.keys()))
check("the supplier and order are linked", "Approved" in t["supplier"] and "Trace Supplies" in t["supplier"] and "Approved" in t["order"], t)
check("no contract is said plainly", "No contract" in t["contract"] and "not raised under a contract" in t["contract"], t["contract"])
check("no delivery, invoice or payment is shown as missing, in words", "Nothing received yet" in t["delivery"] and "No invoice yet" in t["invoice"] and "Nothing to pay yet" in t["payment"], t)
check("a missing step is drawn hollow-dashed (shape, not only colour)", "is-missing" in shape(pg, "delivery") and pg.locator("#pc-trace-rail .pr-step[data-stage=delivery] .pr-dash").count() == 1)
check("the rail says how many steps are linked", "of 7 steps linked" in pg.inner_text("#pc-trace-rail .pr-summary"), pg.inner_text("#pc-trace-rail .pr-summary"))
check("the total is shown exactly, with its currency", "NGN" in pg.inner_text("#pc-trace-total") and "500.00" in pg.inner_text("#pc-trace-total"), pg.inner_text("#pc-trace-total"))

# ---- the order that goes all the way ----
pg.select_option("#pc-trace-order", full["id"]); pg.wait_for_timeout(600)
t = steps(pg)
check("delivery is linked and says a person recorded it", "Fully received" in t["delivery"] and "has not confirmed that anything arrived" in t["delivery"], t["delivery"])
check("the invoice step is linked", "Approved" in t["invoice"] and "1 invoice recorded" in t["invoice"], t["invoice"])
check("the payment step names the bank reference and that ASAVEXA did not pay", "BANK-77881" in t["payment"] and "did not make the payment" in t["payment"], t["payment"])
check("the review step shows the latest review", "Reviewed" in t["review"] and "2026-Q1" in t["review"] and "not a rating issued by ASAVEXA" in t["review"], t["review"])
check("the match table shows what the server recorded", "10" in pg.inner_text("#pc-trace-match tr[data-line='1']") and "100.00" in pg.inner_text("#pc-trace-match tr[data-line='1']"), pg.inner_text("#pc-trace-match"))
check("an order with no contract is never called complete: 6 of 7 linked, the contract said missing", "6 of 7 steps linked" in pg.inner_text("#pc-trace-rail .pr-summary") and pg.locator("#pc-trace-rail.is-complete").count() == 0, pg.inner_text("#pc-trace-rail .pr-summary"))

# ---- the same trace is reachable from the order itself ----
pg.click("#pc-tab-orders"); pg.wait_for_timeout(900)
pg.click(f"#pc-po-trace-{full['ref']}"); pg.wait_for_selector("#pc-trace-rail", timeout=8000)
check("Trace this order opens the trace for that order", full["ref"] in pg.inner_text("#pc-trace-title"), pg.inner_text("#pc-trace-title"))

# ---- the trace is a read view: no buttons that change anything ----
check("the trace page offers no approve, reject or pay buttons", pg.locator("#pc-trace button:has-text('Approve'), #pc-trace button:has-text('Reject'), #pc-trace button:has-text('Record as paid')").count() == 0)

# ---- phone width: nothing spills sideways ----
ctx = b.new_context(viewport={"width": 390, "height": 1600}); pg2 = ctx.new_page(); pg2.route("https://asavexa.onrender.com/**", handle)
sign_in(pg2, *AISHA, "Meridian"); goto(pg2, "/procurement"); pg2.click("#pc-tab-trace"); pg2.wait_for_selector("#pc-trace-order"); pg2.select_option("#pc-trace-order", full["id"]); pg2.wait_for_selector("#pc-trace-rail")
check("no sideways overflow at 390px", pg2.evaluate("document.documentElement.scrollWidth") <= 390, pg2.evaluate("document.documentElement.scrollWidth"))
pg2.screenshot(path="/tmp/claude-0/-home-claude/60ab6487-5258-5631-bac9-a1da502d1394/scratchpad/shots/trace-390.png")
pg.screenshot(path="/tmp/claude-0/-home-claude/60ab6487-5258-5631-bac9-a1da502d1394/scratchpad/shots/trace-1300.png")
check("no browser errors", not errs, errs[:3])
finish(p, b)
