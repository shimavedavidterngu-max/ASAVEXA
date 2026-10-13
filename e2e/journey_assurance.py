"""Browser journey: the shared status vocabulary (Stage 12). Run via e2e/run_all.py."""
import json

from common import *

start_web()
p, b, pg, errs = session()
sign_in(pg, *DARA, "Meridian"); goto(pg, "/assurance")
check("menu has Assurance", "Assurance" in pg.text_content(".app-sidebar"))
check("the six kinds are explained", pg.locator("[data-facet]").count()==6)
check("the five flags are explained", pg.locator("[data-flag]").count()==5)
check("says these are not a score", "not a score" in txt(pg,"#as-note"), txt(pg,"#as-note"))
rows = pg.locator("#as-summary [data-record]").count()
check("one summary row per record type", rows==5, rows)  # this test server wires five of the six providers deps.py wires
ev = txt(pg,"[data-record=evidence]")
check("evidence row shows counts", "Evidence" in ev and any(ch.isdigit() for ch in ev), ev)
before = pg.locator("[data-record=evidence] td").nth(1).text_content()
# make something happen in the Evidence Vault by the other module's real endpoint, then look again
api("POST","/_fix", DARA, "Meridian")
pg.click("#as-refresh"); pg.wait_for_timeout(1200)
after = pg.locator("[data-record=evidence] td").nth(1).text_content()
check("the count follows the real records", int(after)==int(before)+1, (before, after))
indep = [pg.locator("[data-record=evidence] td").nth(i).text_content() for i in range(2, 8)]
check("independently verified is counted only for the other-person verification", indep[5] != "0", indep)
check("mapping tables list each module's own status words", pg.locator("#as-mapping").count()==1)
pg.click("#as-mapping summary"); pg.wait_for_timeout(300)
check("finding VERIFIED maps to independently verified", "Independently verified" in txt(pg,"[data-map=finding] [data-status=VERIFIED]"), txt(pg,"[data-map=finding] [data-status=VERIFIED]"))
check("a rejected status carries its flag", "Rejected" in txt(pg,"[data-map=evidence] [data-status=REJECTED]"), txt(pg,"[data-map=evidence] [data-status=REJECTED]"))
sign_in(pg, *OTHER, "Other"); goto(pg, "/assurance")
check("another company sees its own counts only", pg.locator("[data-record=evidence] td").nth(1).text_content()=="0", pg.locator("[data-record=evidence] td").nth(1).text_content())
check("no browser errors", not errs, errs[:3])
finish(p, b)
