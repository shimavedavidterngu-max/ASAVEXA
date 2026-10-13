"""Browser journey: journey_evidence_review. Run via e2e/run_all.py, or: PYTHONPATH=src:tests python3 e2e/server.py & then python3 e2e/journey_evidence_review.py"""
import json

from common import *

def open_case(pg):
    if pg.locator("[data-case] [aria-expanded=false]").count(): pg.locator("[data-case] [aria-expanded=false]").first.click(); pg.wait_for_timeout(400)


def cid(pg): return pg.locator("[data-case]").first.get_attribute("data-case")

start_web()
p, b, pg, errs = session()
sign_in(pg, *DARA, "Meridian")
goto(pg, "/evidence-review")
check("menu has Evidence Review","Evidence Review" in pg.text_content(".app-sidebar"))
check("period preselected", pg.locator("#er-period").input_value()!="")
check("no cases yet", pg.locator("#er-no-cases").count()==1)
pg.select_option("#er-period", index=1); pg.wait_for_timeout(300)
pg.click("#er-run"); pg.wait_for_timeout(1500)
check("verdict is Partly supported", "Partly supported" in txt(pg,"#er-verdict"), txt(pg,"#er-verdict"))
check("assertion shown", "income statement" in txt(pg,"#er-assertion"))
check("rent journal listed as missing", "JRN-000002" in txt(pg,"#er-problems") and "No evidence" in txt(pg,"#er-problems"), txt(pg,"#er-problems"))
check("invoice journal supported by a person-made link", "JRN-000001" in txt(pg,"#er-supporting") and "Linked by a person" in txt(pg,"#er-supporting"), txt(pg,"#er-supporting"))
check("uncertainty, action and limits shown", pg.locator("#er-uncertain").count()==1 and pg.locator("#er-actions").count()==1 and pg.locator("#er-limits").count()==1)
pg.screenshot(path="/tmp/er-review.png", full_page=True)
pg.click("#er-open-case"); pg.wait_for_timeout(1500)
check("case raised", "Case raised" in txt(pg,"#er-notice") and pg.locator("[data-case]").count()==1, txt(pg,"#er-notice"))
check("case is open and needs a plan", "Open: action needed" in txt(pg,"[data-case]") and "Plan the action" in txt(pg,"[data-case]"))
open_case(pg); I=cid(pg)
check("baseline gaps shown as 1", "Gapsatthestart1" in txt(pg,"[data-case]").replace(" ",""), txt(pg,"[data-case]")[:300])
# empty plan is refused by the server and shown
pg.click("[data-act=plan]"); pg.wait_for_timeout(1200)
check("planning with nothing filled in is refused", "required" in txt(pg,"#app, body").lower() or pg.locator(".alert-error").count()>0, txt(pg,".alert-error"))
open_case(pg)
pg.fill(f"#er-action-{I}", "Attach the signed lease and have it verified"); pg.select_option(f"#er-owner-{I}", label="You · OWNER")
pg.click("[data-act=plan]"); pg.wait_for_timeout(1500)
check("action planned", "Action planned" in txt(pg,"[data-case]"), txt(pg,"[data-case]")[:200])
pg.fill(f"#er-note-{I}", "Lease uploaded"); pg.click("[data-act=complete]"); pg.wait_for_timeout(1500)
check("done, waiting for independent check", "waiting for independent check" in txt(pg,"[data-case]"), txt(pg,"[data-case]")[:200])
check("the person who did the work is told they cannot verify", pg.locator("[data-sod]").count()==1 and pg.locator("[data-act=verify]").count()==0)
pg.screenshot(path="/tmp/er-sod.png", full_page=True)
# independent verifier, but nothing has actually been fixed yet
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/evidence-review"); open_case(pg)
check("independent verifier sees the verify form", pg.locator("[data-act=verify]").count()==1)
pg.fill(f"#er-residual_risk-{I}", "High: still no lease"); pg.fill(f"#er-reopen_criteria-{I}", "Any journal without evidence")
pg.click("[data-act=verify]"); pg.wait_for_timeout(1800)
check("verification of unfixed work is rejected", "Not verified" in txt(pg,"#er-notice"), txt(pg,"#er-notice"))
open_case(pg)
check("case went back to the owner with the failed attempt recorded", "Action planned" in txt(pg,"[data-case]") and "rejected 1 time" in txt(pg,"[data-case]"), txt(pg,"[data-case]")[:300])
# the work is really done in the Evidence Vault, then re-recorded
api("POST","/_fix", DARA, "Meridian")
sign_in(pg, *DARA, "Meridian"); goto(pg, "/evidence-review"); open_case(pg)
pg.fill(f"#er-note-{I}", "Lease uploaded and verified in the vault"); pg.click("[data-act=complete]"); pg.wait_for_timeout(1500)
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/evidence-review"); open_case(pg)
pg.fill(f"#er-residual_risk-{I}", "Low: lease may expire"); pg.fill(f"#er-reopen_criteria-{I}", "Any journal without evidence")
pg.click("[data-act=verify]"); pg.wait_for_timeout(1800)
check("verified after a real fix", "Verified: the figure was re-measured" in txt(pg,"#er-notice"), txt(pg,"#er-notice"))
open_case(pg)
check("outcome shows measured before and after", "1 gap(s) before, 0 after" in txt(pg,"[data-outcome]"), txt(pg,"[data-case]")[:400])
pg.click("[data-act=recheck]"); pg.wait_for_timeout(1500)
check("re-check keeps it verified", "still fully supported" in txt(pg,"#er-notice"), txt(pg,"#er-notice"))
pg.select_option("#er-period", index=1); pg.wait_for_timeout(300)
pg.click("#er-run"); pg.wait_for_timeout(1500)
check("the review now says fully supported with no case button", "Fully supported" in txt(pg,"#er-verdict") and pg.locator("#er-open-case").count()==0, txt(pg,"#er-verdict"))
pg.screenshot(path="/tmp/er-verified.png", full_page=True)
acts=api("GET","/_audit", DARA, "Meridian")["actions"]
for a in ("EVIDENCE_REVIEW_CASE_OPENED","EVIDENCE_REVIEW_ACTION_PLANNED","EVIDENCE_REVIEW_ACTION_COMPLETED","EVIDENCE_REVIEW_OUTCOME_REJECTED","EVIDENCE_REVIEW_OUTCOME_VERIFIED","EVIDENCE_REVIEW_RECHECKED"):
    check("audit has "+a, a in acts, acts[:6])
# a second company
sign_in(pg, *OTHER, "Other"); goto(pg, "/evidence-review")
check("other tenant sees no cases", pg.locator("[data-case]").count()==0 and pg.locator("#er-no-cases").count()==1)
res=api("GET",f"/evidence-review/cases/{I}", OTHER, "Other")
check("other tenant cannot fetch the case by id (404)", res.get("status")==404, res)
res=api("POST", f"/evidence-review/cases/{I}/verify", OTHER, "Other",{"residual_risk":"x","reopen_criteria":"y"})
check("other tenant cannot verify it (404)", res.get("status")==404, res)
check("no console or page errors", not errs, errs)

finish(p, b)
