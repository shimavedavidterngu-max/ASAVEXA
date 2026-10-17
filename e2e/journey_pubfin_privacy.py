"""Browser journey: Public Finance, server-side donor privacy (Stage 12). Run via e2e/run_all.py.
An approver hides who gave; the SERVER then masks the donor everywhere and stores no new names."""
from common import *

M = "Meridian"
def P(m, path, who, body=None): return api(m, "/pubfin" + path, who, M, body)
def ok(r, what):
    if isinstance(r, dict) and "body" in r and r.get("status") in (400, 403, 404, 409, 500): raise SystemExit(f"seed failed at {what}: {r}")
    return r
OLD = "Old Donor Foundation"
gr = ok(P("POST", "/grants", AISHA, {"title": "Clean water", "donor": OLD, "amount": "50000.00", "currency": "NGN", "start": "2026-01-01", "end": "2026-12-31", "restricted": True, "conditions": ""}), "grant")

start_web()
p, b, pg, errs = session()
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/pubfin")
pg.wait_for_selector("#pf-privacy", timeout=8000)
check("default: who gave is shown", pg.inner_text("#pf-privacy-state").startswith("Shown"), pg.inner_text("#pf-privacy-state"))
pg.click("#pf-tab-grants"); pg.wait_for_selector("#pf-grant-table")
check("the donor is listed while shown", OLD in pg.inner_text("#pf-grant-table"))
pg.click("#pf-tab-overview"); pg.wait_for_selector("#pf-privacy-toggle"); pg.click("#pf-privacy-toggle")
pg.wait_for_function("document.querySelector('#pf-privacy-state') && document.querySelector('#pf-privacy-state').innerText.startsWith('Hidden')", timeout=8000)
check("the state now says Hidden, and that old names are hidden not erased", "hidden, not erased" in pg.inner_text("#pf-privacy-state"))
pg.click("#pf-tab-grants"); pg.wait_for_selector("#pf-grant-table")
check("the old donor name is no longer shown in the list", OLD not in pg.inner_text("body") and "Not recorded" in pg.inner_text("#pf-grant-table"), pg.inner_text("#pf-grant-table"))
sv = P("GET", f"/grants/{gr['id']}", KWAME)
check("the SERVER masks the stored donor", sv["donor"] == "Not recorded", sv.get("donor"))
nw = P("POST", "/grants", AISHA, {"title": "School roof", "donor": "Secret Person", "amount": "10000.00", "currency": "NGN", "start": "2026-01-01", "end": "2026-12-31", "restricted": False, "conditions": ""})
check("a new grant does not store or return the name", nw.get("donor") == "Not recorded" and "Secret Person" not in str(P("GET", "/grants", KWAME)), nw)
pg.click("#pf-tab-follow"); pg.wait_for_selector("#pf-follow-ledger")
check("Follow a grant does not say 'by Not recorded'", "Not recorded" not in pg.inner_text("#pf-follow-sentence") and OLD not in pg.inner_text("body"), pg.inner_text("#pf-follow-sentence"))
check("the accountant cannot change it (server refuses)", P("PUT", "/privacy", AISHA, {"hide_donor": False}).get("status") in (401, 403))
pg.click("#pf-tab-overview"); pg.wait_for_selector("#pf-privacy-toggle"); pg.click("#pf-privacy-toggle")
pg.wait_for_function("document.querySelector('#pf-privacy-state').innerText.startsWith('Shown')", timeout=8000)
check("turning it off restores the older name (it was only masked)", P("GET", f"/grants/{gr['id']}", KWAME)["donor"] == OLD)
check("erase is not offered while names are shown", pg.locator("#pf-erase-go").count() == 0)
pg.click("#pf-privacy-toggle"); pg.wait_for_selector("#pf-erase-go")
pg.fill("#pf-erase-word", "erase"); pg.click("#pf-erase-go"); pg.wait_for_selector(".alert-error, .alert-danger, [role=alert]", timeout=8000)
check("lower-case word is refused with a clear message", "capital letters" in pg.inner_text("body") and "permanently erased" not in pg.inner_text("body"))
pg.fill("#pf-erase-word", "ERASE"); pg.click("#pf-erase-go"); pg.wait_for_function("document.body.innerText.includes('permanently erased')", timeout=8000)
check("the notice says how many were erased and that report copies stay hidden", "permanently erased" in pg.inner_text("body"))
pg.click("#pf-privacy-toggle"); pg.wait_for_function("document.querySelector('#pf-privacy-state').innerText.startsWith('Shown')", timeout=8000)
check("after erasing, turning hiding off does NOT bring the name back", P("GET", f"/grants/{gr['id']}", KWAME)["donor"] == "Not recorded")
check("no browser errors", not errs, errs[:3])
finish(p, b)
