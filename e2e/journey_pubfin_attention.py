"""Browser journey: Public Finance, "Needs attention" opens the proof (Stage 15). Run via e2e/run_all.py."""
from common import *

M = "Meridian"
SHOTS = "/tmp/claude-0/-home-claude/60ab6487-5258-5631-bac9-a1da502d1394/scratchpad/shots/"
def P(m, path, who, body=None): return api(m, "/pubfin" + path, who, M, body)
def ok(r, what):
    if isinstance(r, dict) and "body" in r and r.get("status") in (400, 403, 404, 409, 500): raise SystemExit(f"seed failed at {what}: {r}")
    return r
acc = {x["code"]: x["id"] for x in api("GET", "/accounts", DARA, M)}
tight = ok(P("POST", "/budgets", AISHA, {"name": "Tight budget", "start": "2026-01-01", "end": "2026-12-31", "currency": "NGN", "lines": [{"account_id": acc["5000"], "amount": "10000.00"}, {"account_id": acc["4000"], "amount": "50000.00"}]}), "budget")
ok(P("POST", f"/budgets/{tight['id']}/submit", AISHA), "submit"); ok(P("POST", f"/budgets/{tight['id']}/approve", KWAME, {"note": ""}), "approve")
old = ok(P("POST", "/grants", AISHA, {"title": "Old grant", "donor": "Some Donor", "amount": "9000.00", "currency": "NGN", "start": "2025-01-01", "end": "2025-12-31", "restricted": True, "conditions": ""}), "old grant")
late = ok(P("POST", "/grants", AISHA, {"title": "Late cash", "donor": "Cash Donor", "amount": "9000.00", "currency": "NGN", "start": "2026-01-01", "end": "2026-12-31", "restricted": False, "conditions": ""}), "late grant")
sp = ok(P("POST", f"/grants/{late['id']}/spend", AISHA, {"amount": "500.00", "date": "2026-03-01", "description": "Early spend", "reference": "V-1", "evidence_ids": []}), "spend")
ok(P("POST", f"/grants/{late['id']}/spend/{sp['spend'][0]['id']}/approve", KWAME, {"note": ""}), "approve spend")

start_web()
p, b, pg, errs = session()
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/pubfin"); pg.wait_for_selector("#pf-overspent", timeout=8000)
check("the overspent line is listed with its own button", pg.locator("#pf-overspent button").count() >= 1, pg.inner_text("#pf-overspent"))
pg.locator("#pf-overspent button").first.click(); pg.wait_for_selector("#pf-spend-ledger", timeout=8000)
check("it opens Where the money went for that budget", "Tight budget" in pg.inner_text("#pf-spend-title") or "Tight budget" in pg.inner_text("#pf-spend-ledger"), pg.inner_text("#pf-spend-title"))
check("and shows the overspent line with the server's sentence", "more has been spent or promised than was approved" in pg.inner_text("#pf-spend-sentence"), pg.inner_text("#pf-spend-sentence"))
check("the Where the money went tab is the active one", pg.get_attribute("#pf-tab-spend", "aria-selected") == "true")
pg.click("#pf-tab-overview"); pg.wait_for_selector("#pf-overview")
pg.click(f"#pf-expired-{old['ref']}"); pg.wait_for_selector("#pf-follow-ledger", timeout=8000)
check("an expired grant opens Follow a grant for that grant", old["ref"] in pg.inner_text("#pf-follow-title"), pg.inner_text("#pf-follow-title"))
check("Follow a grant is the active tab", pg.get_attribute("#pf-tab-follow", "aria-selected") == "true")
pg.click("#pf-tab-overview"); pg.wait_for_selector("#pf-overview")
pg.click(f"#pf-overrcv-{late['ref']}"); pg.wait_for_selector("#pf-follow-ledger", timeout=8000)
check("a grant with spending beyond cash opens its own page", late["ref"] in pg.inner_text("#pf-follow-title") and "500.00" in pg.inner_text("#pf-follow-sentence"), pg.inner_text("#pf-follow-sentence"))
check("the picker agrees with the grant opened", pg.eval_on_selector("#pf-follow-pick", "e => e.options[e.selectedIndex].text").startswith(late["ref"]))
ctx = b.new_context(viewport={"width": 390, "height": 1600}); pg2 = ctx.new_page(); pg2.route("https://asavexa.onrender.com/**", handle)
sign_in(pg2, *AISHA, "Meridian"); goto(pg2, "/pubfin"); pg2.wait_for_selector("#pf-overspent"); pg2.wait_for_timeout(400)
check("no sideways overflow at 390px", pg2.evaluate("document.documentElement.scrollWidth") <= 390, pg2.evaluate("document.documentElement.scrollWidth"))
pg2.screenshot(path=SHOTS + "attention-390.png")
check("no browser errors", not errs, errs[:3])
finish(p, b)
