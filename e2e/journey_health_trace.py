"""Browser journey: Health administration, "Follow the money" (Stage 7). Run via e2e/run_all.py.
A health centre is built through the real health service by different people (see health_seed.py), then read in the browser.
Pharmacy goes all the way, Laboratory has a part delivery and an invoice that does not match, Administration has an order waiting for approval."""
from common import *
import health_seed as S

R = S.seed(); fid = R["fid"]; dept = R["dept"]
SHOTS = "/tmp/claude-0/-home-claude/60ab6487-5258-5631-bac9-a1da502d1394/scratchpad/shots/"
def steps(pg): return {s.get_attribute("data-stage"): s.inner_text() for s in pg.locator("#hc-trace-rail .pr-step").all()}
def shape(pg, stage): return pg.locator(f"#hc-trace-rail .pr-step[data-stage={stage}] .pr-bead").get_attribute("class")

start_web()
p, b, pg, errs = session()
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/health")
pg.wait_for_selector("#hc-tab-trace", timeout=8000)
check("the workspace has a Follow the money tab", pg.locator("#hc-tab-trace").count() == 1)
pg.click("#hc-tab-trace"); pg.wait_for_selector("#hc-trace-ledger", timeout=8000)
check("the ledger carries the health accent", pg.locator("#hc-trace-ledger[data-sector=health]").count() == 1)
check("the approved budget is named, with its currency", "B-001" in pg.inner_text("#hc-trace-budget") and "NGN" in pg.inner_text("#hc-trace-budget"), pg.inner_text("#hc-trace-budget"))

# ---- the overview restates every budget line exactly as the server recorded it ----
ov = pg.inner_text("#hc-trace-overview")
check("overview shows authorised, committed and spent exactly", "10000.00" in ov and "1000.00" in ov and "9000.00" in ov and "5000.00" in ov and "2000.00" in ov, ov)

# ---- Pharmacy (first department by order): goes all the way ----
pg.select_option("#hc-trace-dept", dept["PHARM"]); pg.wait_for_timeout(500)
t = steps(pg)
check("the rail has four steps in order", list(t.keys()) == ["authorised", "purchased", "delivered", "unresolved"], list(t.keys()))
check("pharmacy: authorised from the approved budget", "Approved" in t["authorised"] and "B-001" in t["authorised"] and "10000.00" in t["authorised"], t["authorised"])
check("pharmacy: purchased and fully received, and it says a person recorded it", "Fully received" in t["delivered"] and "has not confirmed that anything arrived" in t["delivered"], t["delivered"])
check("pharmacy: nothing unresolved, in words", "Nothing open" in t["unresolved"], t["unresolved"])
check("a linked step is drawn solid", "is-linked" in shape(pg, "unresolved"), shape(pg, "unresolved"))
check("the order table shows received over ordered", "10/10" in pg.inner_text("#hc-trace-orders") and "PO-001" in pg.inner_text("#hc-trace-orders"), pg.inner_text("#hc-trace-orders"))

# ---- Laboratory: part delivered, invoice does not match ----
pg.select_option("#hc-trace-dept", dept["LAB"]); pg.wait_for_timeout(500)
t = steps(pg)
check("lab: partly received", "Partly received" in t["delivered"], t["delivered"])
check("lab: the unmatched invoice is unresolved, with the server's numbers", "Does not match" in t["unresolved"] and "900.00" in t["unresolved"] and "400.00" in t["unresolved"], t["unresolved"])
check("lab: unresolved is drawn hollow-dashed (shape, not only colour)", "is-missing" in shape(pg, "unresolved") and pg.locator("#hc-trace-rail .pr-step[data-stage=unresolved] .pr-dash").count() == 1)
check("lab: the invoice list says it does not match", "Does not match" in pg.inner_text("#hc-trace-invoices") and "400.00" in pg.inner_text("#hc-trace-invoices"), pg.inner_text("#hc-trace-invoices"))
check("lab: the rail says it is not complete", pg.locator("#hc-trace-rail.is-complete").count() == 0 and "of 4 steps linked" in pg.inner_text("#hc-trace-rail .pr-summary"), pg.inner_text("#hc-trace-rail .pr-summary"))

# ---- Administration: an order waiting for approval ----
pg.select_option("#hc-trace-dept", dept["ADM"]); pg.wait_for_timeout(500)
t = steps(pg)
check("admin: the order is waiting for a different person", "Waiting for approval" in t["purchased"], t["purchased"])
check("admin: nothing is delivered yet", "Nothing to deliver yet" in t["delivered"], t["delivered"])
check("admin: no invoice is said plainly", "No invoice for this department" in pg.inner_text("#hc-trace-no-invoices"))

# ---- a read view; no patient wording ----
check("the trace offers no approve, pay or receive buttons", pg.locator("#hc-trace-ledger button").count() == 0)
check("no patient wording on the trace tab", not any(w in pg.inner_text("#hc-trace").lower() for w in ("diagnos", "prescription", "patient name")))

# ---- the overview Follow button changes the department ----
pg.click(f"#hc-trace-follow-{dept['LAB']}-MEDICAL_SUPPLIES"); pg.wait_for_timeout(500)
check("Follow switches the department", "LAB" in pg.inner_text("#hc-trace-title"), pg.inner_text("#hc-trace-title"))

# ---- someone from another company sees nothing of this facility ----
other = api("GET", f"/health/facilities/{fid}", OTHER, "Other")
check("another company cannot read the facility", isinstance(other, dict) and other.get("status") in (403, 404), other)
# ---- the approver reads the same figures ----
ex = api("GET", f"/health/facilities/{fid}/budgets", KWAME, "Meridian")
check("the server's own budget list matches what the page named", ex and ex[0]["ref"] == "B-001")

# ---- phone width ----
ctx = b.new_context(viewport={"width": 390, "height": 1800}); pg2 = ctx.new_page(); pg2.route("https://asavexa.onrender.com/**", handle)
sign_in(pg2, *AISHA, "Meridian"); goto(pg2, "/health"); pg2.click("#hc-tab-trace"); pg2.wait_for_selector("#hc-trace-rail"); pg2.select_option("#hc-trace-dept", dept["LAB"]); pg2.wait_for_timeout(500)
check("no sideways overflow at 390px", pg2.evaluate("document.documentElement.scrollWidth") <= 390, pg2.evaluate("document.documentElement.scrollWidth"))
pg2.screenshot(path=SHOTS + "health-390.png"); pg.screenshot(path=SHOTS + "health-1300.png")
check("no browser errors", not errs, errs[:3])
finish(p, b)
