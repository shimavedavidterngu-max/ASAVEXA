"""Browser journey: Public Finance, "Follow a fund" for a faith-based organisation (Stage 10). Run via e2e/run_all.py.
The organisation is configured as a congregation through the real entity-configuration route. The donor is entered on the record and must never appear in this view."""
from common import *

M = "Meridian"
SHOTS = "/tmp/claude-0/-home-claude/60ab6487-5258-5631-bac9-a1da502d1394/scratchpad/shots/"
DONOR = "Mrs Adeyemi"
def P(m, path, who, body=None): return api(m, "/pubfin" + path, who, M, body)
def ok(r, what):
    if isinstance(r, dict) and "body" in r and r.get("status") in (400, 403, 404, 409, 500): raise SystemExit(f"seed failed at {what}: {r}")
    return r
cfg = api("PUT", "/entity-config", DARA, M, {"entity_type": "FAITH", "subtype": "CONGREGATION"}); ok(cfg, "entity config")
fund = ok(P("POST", "/grants", AISHA, {"title": "Building fund", "donor": DONOR, "amount": "400000.00", "currency": "NGN", "start": "2026-01-01", "end": "2026-12-31", "restricted": True, "conditions": "New roof only"}), "fund")
ok(P("POST", f"/grants/{fund['id']}/receipts", AISHA, {"amount": "150000.00", "date": "2026-02-01", "reference": "OFFERING-1"}), "receipt")
g = ok(P("POST", f"/grants/{fund['id']}/spend", AISHA, {"amount": "90000.00", "date": "2026-03-01", "description": "Roofing sheets", "reference": "V-1", "evidence_ids": []}), "spend")
ok(P("POST", f"/grants/{fund['id']}/spend/{g['spend'][0]['id']}/approve", KWAME, {"note": ""}), "approve")

def steps(pg): return {s.get_attribute("data-stage"): s.inner_text() for s in pg.locator("#pf-follow-rail .pr-step").all()}

start_web()
p, b, pg, errs = session()
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/pubfin")
pg.wait_for_selector("#pf-tab-follow", timeout=8000)
check("the shell accent is the faith-based one", pg.evaluate("document.querySelector('.app-shell').getAttribute('data-sector')") == "church", pg.evaluate("document.querySelector('.app-shell').getAttribute('data-sector')"))
check("the tab is called Follow a fund", pg.inner_text("#pf-tab-follow").strip() == "Follow a fund", pg.inner_text("#pf-tab-follow"))
pg.click("#pf-tab-follow"); pg.wait_for_selector("#pf-follow-ledger", timeout=8000)
check("the title is the fund", "Building fund" in pg.inner_text("#pf-follow-title"))
s_ = pg.inner_text("#pf-follow-sentence")
check("the sentence is about the fund, with the server's figures", s_ == "Of the 400,000.00 NGN set aside for this designated fund, 150,000.00 NGN has been received and 90,000.00 NGN of spending is approved. 310,000.00 NGN is still unspent.", s_)
t = steps(pg)
check("the rail uses fund words", "Set up" in t["funding"] and "Designated" in t["funding"] and "New roof only" in t["funding"] and "Gifts" not in t["funding"], t["funding"])
check("received is worded as gifts with the receipt reference", "Partly received" in t["received"] and "OFFERING-1" in t["received"], t["received"])
check("evidence is not linked yet, in words", "Not linked yet" in t["evidence"], t["evidence"])
check("the donor's name appears NOWHERE on the page", DONOR not in pg.inner_text("body") and "Adeyemi" not in pg.content(), "found")
check("the picker lists the fund without the donor", DONOR not in " ".join(pg.locator("#pf-follow-pick option").all_inner_texts()))
check("the page says it never shows who gave", "never shows who gave" in pg.inner_text("#pf-follow-limit"))
check("no buttons in the ledger (read view)", pg.locator("#pf-follow-ledger button").count() == 0)
# ---- the older pages in the same workspace do not show the donor either ----
pg.click("#pf-tab-grants"); pg.wait_for_selector("#pf-grants-private", timeout=8000)
check("Grants list: says who gave is not shown, no Donor column, no donor name", "Donor" not in pg.inner_text("#pf-grant-table") and DONOR not in pg.inner_text("body") and "not shown" in pg.inner_text("#pf-grants-private"), pg.inner_text("#pf-grants"))
pg.click(f"#grant-open-{fund['id']}"); pg.wait_for_selector("#pf-grant", timeout=8000)
check("the fund's own page has no donor name", DONOR not in pg.inner_text("body") and "Adeyemi" not in pg.content(), "found")
pg.click("#grant-back"); pg.wait_for_selector("#pf-grants-private"); pg.click("#grant-new"); pg.wait_for_selector("#grant-form")
check("the new-fund form asks for a general source", "never a person" in pg.inner_text("#grant-form"), pg.inner_text("#grant-form")[:200])
pg.click("#gf-cancel"); pg.click("#pf-tab-follow"); pg.wait_for_selector("#pf-follow-ledger")
sv = P("GET", f"/grants/{fund['id']}", KWAME)
check("the stored record is untouched (the server still has the donor)", sv["donor"] == DONOR and sv["remaining"] == "310000.00", sv.get("donor"))
ctx = b.new_context(viewport={"width": 390, "height": 1800}); pg2 = ctx.new_page(); pg2.route("https://asavexa.onrender.com/**", handle)
sign_in(pg2, *AISHA, "Meridian"); goto(pg2, "/pubfin"); pg2.click("#pf-tab-follow"); pg2.wait_for_selector("#pf-follow-rail"); pg2.wait_for_timeout(400)
check("no sideways overflow at 390px", pg2.evaluate("document.documentElement.scrollWidth") <= 390, pg2.evaluate("document.documentElement.scrollWidth"))
check("no donor at phone width either", "Adeyemi" not in pg2.content())
pg2.screenshot(path=SHOTS + "fund-390.png"); pg.screenshot(path=SHOTS + "fund-1300.png")
check("no browser errors", not errs, errs[:3])
finish(p, b)
