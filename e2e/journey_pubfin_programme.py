"""Browser journey: Public Finance, grants matched to programme results by reference (Stage 14). Run via e2e/run_all.py.
Indicators come from the real Impact routes (proposed by one person, approved by another, readings confirmed by another)."""
from datetime import datetime, timedelta, timezone
from common import *

M = "Meridian"
TODAY = datetime.now(timezone.utc).date(); D = lambda n: (TODAY + timedelta(days=n)).isoformat()
SHOTS = "/tmp/claude-0/-home-claude/60ab6487-5258-5631-bac9-a1da502d1394/scratchpad/shots/"
def P(m, path, who, body=None): return api(m, "/pubfin" + path, who, M, body)
def I(m, path, who, body=None): return api(m, "/impact" + path, who, M, body)
def ok(r, what):
    if isinstance(r, dict) and "body" in r and r.get("status") in (400, 403, 404, 409, 500): raise SystemExit(f"seed failed at {what}: {r}")
    return r
ind = ok(I("POST", "/indicators", DARA, dict(title="Households with clean water", programme_ref="WASH-01", unit="households", direction="INCREASE", baseline="100", target="1000", baseline_date=D(-100), target_date=D(265))), "indicator")
ok(I("POST", f"/indicators/{ind['id']}/approve", KWAME, {"note": ""}), "approve indicator")
ok(I("POST", f"/indicators/{ind['id']}/readings", DARA, dict(period_end=D(-5), value="460", source_note="Counted from the field register")), "reading")
ok(I("POST", f"/indicators/{ind['id']}/readings/1/confirm", KWAME, {"note": "Checked against the register"}), "confirm")
ok(I("POST", "/indicators", DARA, dict(title="Pending one", programme_ref="WASH-01", unit="percent", direction="INCREASE", baseline="1", target="9", baseline_date=D(-100), target_date=D(265))), "proposed indicator")
g1 = ok(P("POST", "/grants", AISHA, {"title": "Clean water", "donor": "Water Fund", "amount": "50000.00", "currency": "NGN", "start": "2026-01-01", "end": "2026-12-31", "restricted": True, "conditions": "", "programme_ref": "wash-01"}), "grant 1")
g2 = ok(P("POST", "/grants", AISHA, {"title": "School roof", "donor": "Roof Fund", "amount": "9000.00", "currency": "NGN", "start": "2026-01-01", "end": "2026-12-31", "restricted": False, "conditions": ""}), "grant 2")
sv = P("GET", f"/grants/{g1['id']}", KWAME)
check("the server kept the typed reference and a grant without one has none", sv.get("programme_ref") == "wash-01" and P("GET", f"/grants/{g2['id']}", KWAME).get("programme_ref") is None, sv.get("programme_ref"))
check("the server refuses a one-character reference", P("PUT", f"/grants/{g2['id']}/programme", AISHA, {"programme_ref": "x"}).get("status") == 400)
check("an approver without prepare rights cannot set it", P("PUT", f"/grants/{g2['id']}/programme", KWAME, {"programme_ref": "WASH-09"}).get("status") in (401, 403))

start_web()
p, b, pg, errs = session()
sign_in(pg, *DARA, "Meridian"); goto(pg, "/pubfin")
pg.wait_for_selector("#pf-tab-follow", timeout=8000); pg.click("#pf-tab-follow"); pg.wait_for_selector("#pf-follow-programme", timeout=8000)
pg.select_option("#pf-follow-pick", g1["id"]); pg.wait_for_selector("#pf-programme-list", timeout=8000)
li = pg.inner_text("#pf-programme-list")
check("the matched indicator is listed with the server's figures", "Households with clean water" in li and "460.00 households" in li and "%" in li, li)
check("only the approved indicator is listed, not the pending one", "Pending one" not in li)
check("the caveat says it is not proof of cause", "does not show that the grant caused any change" in pg.inner_text("#pf-programme-limit"))
check("no buttons inside the read-only ledger", pg.locator("#pf-follow-ledger button").count() == 0)
pg.select_option("#pf-follow-pick", g2["id"]); pg.wait_for_selector("#pf-programme-noref", timeout=8000)
check("a grant without a reference says no indicators are matched", "No programme reference" in pg.inner_text("#pf-programme-noref"))
pg.fill("#pf-programme-ref", "NOPE-99"); pg.click("#pf-programme-save")
pg.wait_for_selector("#pf-programme-none", timeout=8000)
check("a reference with no approved indicator says so with the code", "NOPE-99" in pg.inner_text("#pf-programme-none"))
pg.fill("#pf-programme-ref", "x"); pg.click("#pf-programme-save"); pg.wait_for_timeout(600)
check("a one-character reference is refused in words", "2 to 40" in pg.inner_text("body") and P("GET", f"/grants/{g2['id']}", DARA)["programme_ref"] == "NOPE-99")
pg.fill("#pf-programme-ref", "WASH-01"); pg.click("#pf-programme-save"); pg.wait_for_selector("#pf-programme-list", timeout=8000)
check("saving the reference matches the indicator", "Households with clean water" in pg.inner_text("#pf-programme-list") and P("GET", f"/grants/{g2['id']}", DARA)["programme_ref"] == "WASH-01")
pg.fill("#pf-programme-ref", ""); pg.click("#pf-programme-save"); pg.wait_for_selector("#pf-programme-noref", timeout=8000)
check("emptying it removes the reference", P("GET", f"/grants/{g2['id']}", DARA)["programme_ref"] is None)
# new-grant form carries the field
pg.click("#pf-tab-grants"); pg.wait_for_selector("#grant-new"); pg.click("#grant-new"); pg.wait_for_selector("#gf-prog")
check("the new-grant form has an optional programme reference", "optional" in pg.inner_text("#grant-form"))
pg.click("#gf-cancel")
# a person who cannot read impact sees 'Not checked', not 'none'
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/pubfin"); pg.wait_for_selector("#pf-tab-follow"); pg.click("#pf-tab-follow"); pg.wait_for_selector("#pf-follow-programme", timeout=8000)
pg.select_option("#pf-follow-pick", g1["id"]); pg.wait_for_timeout(1200)
t = pg.inner_text("#pf-follow-programme")
check("with or without impact access the page is honest (matched, or 'Not checked')", ("Households with clean water" in t) or t.count("Not checked") == 1, t[:200])
ctx = b.new_context(viewport={"width": 390, "height": 1800}); pg2 = ctx.new_page(); pg2.route("https://asavexa.onrender.com/**", handle)
sign_in(pg2, *DARA, "Meridian"); goto(pg2, "/pubfin"); pg2.click("#pf-tab-follow"); pg2.wait_for_selector("#pf-follow-programme"); pg2.select_option("#pf-follow-pick", g1["id"]); pg2.wait_for_selector("#pf-programme-list"); pg2.wait_for_timeout(400)
check("no sideways overflow at 390px", pg2.evaluate("document.documentElement.scrollWidth") <= 390, pg2.evaluate("document.documentElement.scrollWidth"))
pg2.screenshot(path=SHOTS + "programme-390.png"); pg.screenshot(path=SHOTS + "programme-1300.png")
check("no browser errors", not errs, errs[:3])
finish(p, b)
