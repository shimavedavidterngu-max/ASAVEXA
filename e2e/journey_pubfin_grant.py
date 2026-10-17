"""Browser journey: Public Finance, "Follow a grant" (Stage 9). Run via e2e/run_all.py.
Grants are built through the real Public Finance service by different people, then read in the browser (which only reads)."""
from common import *

M = "Meridian"
SHOTS = "/tmp/claude-0/-home-claude/60ab6487-5258-5631-bac9-a1da502d1394/scratchpad/shots/"
def P(m, path, who, body=None): return api(m, "/pubfin" + path, who, M, body)
def ok(r, what):
    if isinstance(r, dict) and "body" in r and r.get("status") in (400, 403, 404, 409, 500): raise SystemExit(f"seed failed at {what}: {r}")
    return r
water = ok(P("POST", "/grants", AISHA, {"title": "Clean water", "donor": "Water Fund", "amount": "20000.00", "currency": "USD", "start": "2026-01-01", "end": "2026-12-31", "restricted": True, "conditions": "Wells only"}), "grant")
ok(P("POST", f"/grants/{water['id']}/receipts", AISHA, {"amount": "12000.00", "date": "2026-02-01", "reference": "BANK-1"}), "receipt")
g = ok(P("POST", f"/grants/{water['id']}/spend", AISHA, {"amount": "5000.00", "date": "2026-03-01", "description": "Borehole pump", "reference": "V-1", "evidence_ids": []}), "spend 1")
ok(P("POST", f"/grants/{water['id']}/spend", AISHA, {"amount": "1000.00", "date": "2026-03-05", "description": "Pipes", "reference": "V-2", "evidence_ids": []}), "spend 2")
sid = [s for s in g["spend"] if s["reference"] == "V-1"][0]["id"]
ok(P("POST", f"/grants/{water['id']}/spend/{sid}/approve", KWAME, {"note": ""}), "approve spend")
bare = ok(P("POST", "/grants", AISHA, {"title": "Bare grant", "donor": "Anon Trust", "amount": "3000.00", "currency": "USD", "start": "2026-01-01", "end": "2026-12-31", "restricted": False, "conditions": ""}), "grant 2")

def steps(pg): return {s.get_attribute("data-stage"): s.inner_text() for s in pg.locator("#pf-follow-rail .pr-step").all()}
def shape(pg, st): return pg.locator(f"#pf-follow-rail .pr-step[data-stage={st}] .pr-bead").get_attribute("class")

start_web()
p, b, pg, errs = session()
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/pubfin")
pg.wait_for_selector("#pf-tab-follow", timeout=8000)
check("the workspace has a Follow a grant tab, after Grants", pg.locator("#pf-tab-follow").count() == 1 and pg.locator("#pf-tab-grants + #pf-tab-follow").count() == 1)
pg.click("#pf-tab-follow"); pg.wait_for_selector("#pf-follow-ledger", timeout=8000)
check("the newest grant is shown first", "Bare grant" in pg.inner_text("#pf-follow-title"), pg.inner_text("#pf-follow-title"))

# ---- the grant with nothing after the award ----
t = steps(pg)
check("the rail has four steps in order", list(t.keys()) == ["funding", "received", "spent", "evidence"], list(t.keys()))
check("funding: awarded, unrestricted, no conditions said plainly", "Awarded" in t["funding"] and "Not restricted" in t["funding"] and "No conditions were entered" in t["funding"], t["funding"])
check("received: none, in words", "No cash received yet" in t["received"], t["received"])
check("spent: nothing yet, in words", "Nothing spent yet" in t["spent"], t["spent"])
check("a missing step is drawn hollow-dashed (shape, not only colour)", "is-missing" in shape(pg, "received") and pg.locator("#pf-follow-rail .pr-step[data-stage=received] .pr-dash").count() == 1)
check("with no spending, the spending list says so", "No spending has been recorded" in pg.inner_text("#pf-follow-no-spend"))
check("the limit is stated: conditions are not judged, results are not proven", "does not prove the grant produced any programme result" in pg.inner_text("#pf-follow-limit"))

# ---- the restricted grant with receipts and spending ----
pg.select_option("#pf-follow-pick", water["id"]); pg.wait_for_timeout(600)
check("title changes", "Clean water" in pg.inner_text("#pf-follow-title"), pg.inner_text("#pf-follow-title"))
s_ = pg.inner_text("#pf-follow-sentence")
check("the plain sentence uses the server's figures exactly", s_ == "Of the 20,000.00 USD awarded by Water Fund (restricted), 12,000.00 USD has been received and 5,000.00 USD of spending is approved. 1,000.00 USD more is waiting for a second person to approve it. 15,000.00 USD of the award is still unspent.", s_)
f = pg.inner_text("#pf-follow-figures")
check("the figures table restates the server's own numbers", all(x in f for x in ("20,000.00", "12,000.00", "5,000.00", "1,000.00", "15,000.00", "7,000.00")), f)
t = steps(pg)
check("funding: restricted, with the conditions as entered", "Restricted" in t["funding"] and "Wells only" in t["funding"], t["funding"])
check("received: partly, with the bank reference", "Partly received" in t["received"] and "BANK-1" in t["received"], t["received"])
check("spent: waiting is not counted as spent", "Some waiting for approval" in t["spent"] and "5,000.00 USD approved in 1 entry" in t["spent"], t["spent"])
check("evidence: none linked, naming the vouchers", "Not linked yet" in t["evidence"] and "V-1" in t["evidence"] and "V-2" in t["evidence"], t["evidence"])
check("the spending list says approved and waiting in words", "approved." in pg.inner_text("#pf-follow-spend") and "waiting for a different person to approve it" in pg.inner_text("#pf-follow-spend"), pg.inner_text("#pf-follow-spend"))
check("the rail says it is not complete", pg.locator("#pf-follow-rail.is-complete").count() == 0 and "of 4 steps linked" in pg.inner_text("#pf-follow-rail .pr-summary"), pg.inner_text("#pf-follow-rail .pr-summary"))
check("the page offers no approve, receive or spend buttons in the ledger", pg.locator("#pf-follow-ledger button").count() == 0)

# ---- the server says the same, and another company sees nothing ----
sv = P("GET", f"/grants/{water['id']}", KWAME)
check("the server's own figures match the page", (sv["received"], sv["spent"], sv["pending"], sv["remaining"]) == ("12000.00", "5000.00", "1000.00", "15000.00"), sv)
other = api("GET", f"/pubfin/grants/{water['id']}", OTHER, "Other")
check("another company cannot read the grant", isinstance(other, dict) and other.get("status") in (403, 404), other)

# ---- phone width ----
ctx = b.new_context(viewport={"width": 390, "height": 1800}); pg2 = ctx.new_page(); pg2.route("https://asavexa.onrender.com/**", handle)
sign_in(pg2, *AISHA, "Meridian"); goto(pg2, "/pubfin"); pg2.click("#pf-tab-follow"); pg2.wait_for_selector("#pf-follow-rail"); pg2.select_option("#pf-follow-pick", water["id"]); pg2.wait_for_timeout(500)
check("no sideways overflow at 390px", pg2.evaluate("document.documentElement.scrollWidth") <= 390, pg2.evaluate("document.documentElement.scrollWidth"))
pg2.screenshot(path=SHOTS + "grant-390.png"); pg.screenshot(path=SHOTS + "grant-1300.png")
check("no browser errors", not errs, errs[:3])
finish(p, b)
