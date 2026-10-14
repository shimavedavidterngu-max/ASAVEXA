"""Browser journey: organisation type and workspaces (Stage 15). Run via e2e/run_all.py."""
import json

from common import *

def side(pg): return pg.text_content(".app-sidebar") or ""
def hrefs(pg): return [a.get_attribute("href") for a in pg.locator(".app-sidebar a").all()]
def at(pg, path):
    goto(pg, path); return hrefs(pg)

start_web()
p, b, pg, errs = session()
sign_in(pg, *DARA, "Meridian"); goto(pg, "/entity-config")
check("menu has the page for someone who can change settings", "#/entity-config" in hrefs(pg), hrefs(pg))
check("not set up yet: says every workspace is shown", "every workspace is shown" in txt(pg,"#ec-status"), txt(pg,"#ec-status"))
before = at(pg, "/analysis")
check("before set-up the menu shows the workspaces", "#/tax" in before and "#/analysis" in before and "#/forensic" in before, before)
goto(pg, "/entity-config")
check("sign-up category pre-selected a starting kind", pg.locator("#ec-type").input_value()=="BUSINESS", pg.locator("#ec-type").input_value())
pg.select_option("#ec-type", "HEALTH"); pg.wait_for_timeout(300)
check("subtypes follow the kind", "Hospital" in pg.locator("#ec-subtype").inner_text(), pg.locator("#ec-subtype").inner_text())
pg.select_option("#ec-subtype", "HOSPITAL")
check("suggested workspaces are ticked, others are not", pg.locator("#ec-ws-health").is_checked() and pg.locator("#ec-ws-analysis").is_checked() and not pg.locator("#ec-ws-forensic").is_checked() and not pg.locator("#ec-ws-tax").is_checked())
pg.fill("#ec-custom", "Village clinic network"); pg.fill("#ec-languages", "en, fr"); pg.fill("#ec-timezone", "Africa/Lagos")
pg.click("#ec-save"); pg.wait_for_timeout(1500)
check("saved", "Saved" in txt(pg,"#ec-notice"), txt(pg,"#ec-notice") + txt(pg,"#ec-form-error"))
check("status shows the kind, subtype and own words", "Health and care" in txt(pg,"#ec-current") and "Hospital" in txt(pg,"#ec-current") and "Village clinic network" in txt(pg,"#ec-current"), txt(pg,"#ec-current"))
check("says nobody's access changed", "Nobody's access has changed" in txt(pg,"#ec-hidden"), txt(pg,"#ec-hidden"))
after = at(pg, "/analysis")
check("the menu now hides workspaces that were switched off", "#/tax" not in after and "#/forensic" not in after, after)
check("the menu keeps the chosen workspaces", "#/health" in after and "#/analysis" in after, after)
check("core pages are untouched", "#/accounting" in at(pg, "/accounting"))
pg.screenshot(path="/tmp/ec-saved.png", full_page=True)
# hiding is only a menu change: the page is still reachable by address for someone with permission
goto(pg, "/tax")
check("a hidden workspace is still reachable by address (menu only, not a lock)", "Tax Compliance" in pg.inner_text("main, #app-root") , pg.inner_text("body")[:300])
check("and its breadcrumb is right, not 'Page not found'", "Page not found" not in pg.inner_text("body"), pg.inner_text("body")[:300])
# a fresh sign-in still gets the saved set-up
sign_in(pg, *DARA, "Meridian")
again = at(pg, "/analysis")
check("the saved set-up survives signing in again", "#/tax" not in again and "#/health" in again, again)
goto(pg, "/entity-config")
# changing needs a reason; an unchanged save is refused
pg.select_option("#ec-type", "BUSINESS"); pg.wait_for_timeout(200)
pg.click("#ec-save"); pg.wait_for_timeout(500)
check("changing without a reason is stopped", "why" in txt(pg,"#ec-form-error").lower(), txt(pg,"#ec-form-error"))
pg.select_option("#ec-type", "HEALTH"); pg.wait_for_timeout(200)
pg.select_option("#ec-subtype", "HOSPITAL"); pg.fill("#ec-reason", "again"); pg.click("#ec-save"); pg.wait_for_timeout(1200)
check("saving the same set-up again is refused by the server", "Nothing has changed" in pg.inner_text("body"), pg.inner_text("body")[:300])
pg.select_option("#ec-type", "BUSINESS"); pg.wait_for_timeout(200)
pg.fill("#ec-reason", "We also trade as a business"); pg.click("#ec-save"); pg.wait_for_timeout(1500)
check("change saved with a reason", "Saved" in txt(pg,"#ec-notice"), txt(pg,"#ec-notice") + txt(pg,"#ec-form-error"))
check("history keeps both versions and what changed", pg.locator("#ec-history [data-version]").count()==2 and "HEALTH → BUSINESS" in txt(pg,"#ec-history"), txt(pg,"#ec-history"))
check("the menu follows the new kind", "#/tax" in at(pg, "/analysis"), at(pg, "/analysis"))
goto(pg, "/entity-config")
# a person without the settings permission
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/entity-config")
check("an approver sees it read-only", pg.locator("#ec-readonly").count()==1 and pg.locator("#ec-save").count()==0)
check("the menu entry is not offered to them", "#/entity-config" not in hrefs(pg))
res = api("PUT", "/entity-config", KWAME, "Meridian", {"entity_type": "HEALTH"})
check("the server refuses their change (403)", res.get("status")==403, res)
# another company
sign_in(pg, *OTHER, "Other"); goto(pg, "/entity-config")
check("another company is not set up and sees everything", "every workspace is shown" in txt(pg,"#ec-status"), txt(pg,"#ec-status"))
res = api("GET", "/entity-config", OTHER, "Other")
check("the other company's record is its own", res.get("configured") is False, res)
acts = api("GET","/_audit", DARA, "Meridian")["actions"]
check("audit has ENTITY_CONFIG_SAVED", "ENTITY_CONFIG_SAVED" in acts, acts[:8])
check("no console or page errors", not errs, errs)

finish(p, b)
