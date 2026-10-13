"""Browser journey: journey_standards_registry. Run via e2e/run_all.py, or: PYTHONPATH=src:tests python3 e2e/server.py & then python3 e2e/journey_standards_registry.py"""
import json

from common import *

start_web()
p, b, pg, errs = session()
sign_in(pg, *DARA, "Meridian"); goto(pg, "/standards-registry")
check("menu has Standards Registry","Standards Registry" in pg.text_content(".app-sidebar"))
check("every framework starts unverified", pg.locator("[data-framework]").count()>=5 and "Verified" not in " ".join(pg.locator("[data-framework] .badge").all_text_contents()).replace("Unverified",""))
pg.click("#sr-add-go"); pg.wait_for_timeout(400)
check("empty form is refused before sending", "Choose a framework" in txt(pg,"#sr-form-error"), txt(pg,"#sr-form-error"))
pg.select_option("#sr-framework", value="IFRS"); pg.fill("#sr-title","IFRS Accounting Standards"); pg.fill("#sr-url","http://insecure.example.org"); pg.fill("#sr-authority","IASB"); pg.fill("#sr-version","2026-01"); pg.fill("#sr-effective_from","2026-01-01"); pg.fill("#sr-review_by","2027-01-01")
pg.click("#sr-add-go"); pg.wait_for_timeout(400)
check("insecure link refused", "https" in txt(pg,"#sr-form-error"), txt(pg,"#sr-form-error"))
pg.fill("#sr-url","https://www.ifrs.org/issued-standards/"); pg.click("#sr-add-go"); pg.wait_for_timeout(1500)
check("source added as draft", pg.locator("[data-status=DRAFT]").count()==1 and "Source added" in txt(pg,"#sr-notice"), txt(pg,"#sr-notice"))
pg.click("[data-act=submit]"); pg.wait_for_timeout(1500)
check("submitted for review", pg.locator("[data-status=UNDER_REVIEW]").count()==1)
check("the person who added it cannot approve it", pg.locator("[data-act=approve]").count()==0 and pg.locator("[data-sod]").count()==1)
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/standards-registry")
check("independent reviewer sees Approve", pg.locator("[data-act=approve]").count()==1)
pg.click("[data-act=approve]"); pg.wait_for_timeout(1500)
check("approved", pg.locator("[data-status=APPROVED]").count()==1)
row=pg.locator("[data-framework=IFRS]").first
check("coverage now shows IFRS verified with its official link", "Verified" in (row.text_content() or "") and row.locator("a[href='https://www.ifrs.org/issued-standards/']").count()==1, row.text_content())
check("other frameworks still unverified", pg.locator("[data-framework=US_GAAP]").first.text_content().count("Unverified")==1)
acts=api("GET","/_audit", DARA, "Meridian")
check("audit has added, submitted, approved", all(x in json.dumps(acts) for x in ("STANDARDS_SOURCE_ADDED","STANDARDS_SOURCE_SUBMITTED","STANDARDS_SOURCE_APPROVED")))
sign_in(pg, *OTHER, "Other"); goto(pg, "/standards-registry")
check("other tenant sees none", pg.locator("#sr-none").count()==1 and "Verified" not in " ".join(pg.locator("[data-framework] .badge").all_text_contents()).replace("Unverified",""))
pg.screenshot(path="/tmp/sr.png", full_page=True)
check("no console or page errors", not errs, errs)

finish(p, b)
