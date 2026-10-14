"""Browser journey: IT audit (Stage 20). Run via e2e/run_all.py."""
from datetime import datetime, timedelta, timezone

from common import *

TODAY = datetime.now(timezone.utc).date()                      # the server works in UTC dates
D = lambda n: (TODAY + timedelta(days=n)).isoformat()
def hrefs(pg): return [a.get_attribute("href") for a in pg.locator(".app-sidebar a").all()]
def tab(pg, name):
    pg.click(f"#ia-tab-{name}"); pg.wait_for_timeout(900)
def body(pg): return pg.inner_text("body")
def err(pg): return txt(pg, ".alert-error")
def A(m, path, who, bodyj=None, org="Meridian"): return api(m, "/itaudit" + path, who, org, bodyj)
def st(r): return r.get("status") if isinstance(r, dict) else None
def fill_change(pg, ticket, title, **kw):
    f = dict(system="Payroll", requested="Ada Obi", approver="", approved="", live=D(-10), testing="Tested on a copy with 20 payslips", rollback="Restore the previous table file", type="NORMAL", risk="LOW",
             desc="Applied the new tax tables to the payroll system"); f.update(kw)
    pg.fill("#ia-ch-system", f["system"]); pg.fill("#ia-ch-ticket", ticket); pg.select_option("#ia-ch-type", f["type"]); pg.select_option("#ia-ch-risk", f["risk"]); pg.fill("#ia-ch-title", title); pg.fill("#ia-ch-desc", f["desc"])
    pg.fill("#ia-ch-requested", f["requested"]); pg.fill("#ia-ch-approver", f["approver"]); pg.fill("#ia-ch-approved", f["approved"]); pg.fill("#ia-ch-live", f["live"])
    pg.fill("#ia-ch-testing", f["testing"]); pg.fill("#ia-ch-rollback", f["rollback"])
def card_text(pg, sel): return txt(pg, sel)
def open_test(pg, ref):
    if pg.locator("#ia-test-detail").count() == 0 or ref not in txt(pg, "#ia-test-detail"):
        if pg.locator("#ia-test-detail").count() and ref not in txt(pg, "#ia-test-detail"):
            pg.click(f"#ia-test-open-{ref}"); pg.wait_for_timeout(900)   # a different test is open: opening this one replaces it
        else:
            pg.click(f"#ia-test-open-{ref}"); pg.wait_for_timeout(900)

start_web()
p, b, pg, errs = session()

# ---- an accountant has no business here ----
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/itaudit")
check("the menu does not offer IT audit to an accountant", "#/itaudit" not in hrefs(pg), hrefs(pg))
check("typing the address shows no IT audit content", "Record a change" not in body(pg) and "Define a control" not in body(pg), body(pg)[:200])
check("the server refuses an accountant (overview)", st(A("GET", "/overview", AISHA)) == 403)
check("the server refuses an accountant (changes)", st(A("GET", "/changes", AISHA)) == 403)

# ---- Dara (owner) records changes and defines a control ----
sign_in(pg, *DARA, "Meridian"); goto(pg, "/itaudit")
check("the menu offers IT audit", "#/itaudit" in hrefs(pg), hrefs(pg))
check("the banner says nothing is connected or tested", "does not connect to any system" in txt(pg, "#ia-banner") and "nobody tests their own records" in txt(pg, "#ia-banner"), txt(pg, "#ia-banner"))
check("nothing needs attention yet", "Nothing needs attention" in txt(pg, "#ia-attention"), txt(pg, "#ia-attention"))
tab(pg, "changes")
pg.click("#ia-ch-save"); pg.wait_for_timeout(300)
check("an empty change is stopped with a plain sentence", "system" in txt(pg, "#change-problem").lower(), txt(pg, "#change-problem"))
fill_change(pg, "CHG-101", "Update the tax tables", approver="Ben Eze", approved=D(-12), live=D(5)); pg.click("#ia-ch-save"); pg.wait_for_timeout(1200)
check("a go-live date in the future is refused by the server", "future" in err(pg).lower(), err(pg) + txt(pg, "#change-problem"))
fill_change(pg, "CHG-101", "Update the tax tables", approver="Ben Eze", approved=""); pg.click("#ia-ch-save"); pg.wait_for_timeout(300)
check("an approver without a date is stopped", "both who approved" in txt(pg, "#change-problem"), txt(pg, "#change-problem"))
fill_change(pg, "CHG-101", "Update the tax tables", approver="Ben Eze", approved=D(-12)); pg.click("#ia-ch-save"); pg.wait_for_timeout(1500)
check("a clean change is recorded with no flags", "CH-001" in txt(pg, "#ia-changes") and "No flags" in card_text(pg, "[data-change='CH-001']"), txt(pg, "#ia-notice") + err(pg))
fill_change(pg, "CHG-102", "Open a new payroll interface", risk="HIGH", rollback="", live=D(-9)); pg.click("#ia-ch-save"); pg.wait_for_timeout(1500)
c2 = card_text(pg, "[data-change='CH-002']")
check("a change with no approval and no rollback plan shows both flags", "No approval recorded" in c2 and "No rollback plan" in c2, c2)
fill_change(pg, "CHG-103", "Emergency fix to the pay run", type="EMERGENCY", approver="Ben Eze", approved=D(-1), live=D(-8)); pg.click("#ia-ch-save"); pg.wait_for_timeout(1500)
check("an emergency approved too long after go-live is flagged", "Emergency approval too late" in card_text(pg, "[data-change='CH-003']"), card_text(pg, "[data-change='CH-003']"))
r4 = A("POST", "/changes", DARA, dict(system="Payroll", title="Change the pension rate", description="Changed the employer pension rate in the payroll system", change_type="NORMAL", risk="LOW", requested_by="Ada Obi",
                                      approved_by_name="ada obi", approved_on=D(-10), ticket_ref="CHG-104", implemented_on=D(-9), testing_evidence="Tested on a copy with 20 payslips", rollback_plan="Restore the previous rate"))
check("a change approved by the person who asked is flagged self-approved", r4.get("flags") == ["SELF_APPROVED"], r4)
pg.click("#ia-ch-save"); pg.wait_for_timeout(300)
check("a duplicate ticket for the same system is refused", st(A("POST", "/changes", DARA, dict(system="payroll", title="Update the tax tables", description="Applied the new tax tables to payroll", change_type="NORMAL", risk="LOW", requested_by="Ada", ticket_ref="chg-101", implemented_on=D(-9)))) == 409)
tab(pg, "changes")
pg.click("#ia-filter-flagged"); pg.wait_for_timeout(400)
check("the flagged filter hides the clean change", pg.locator("[data-change='CH-001']").count() == 0 and pg.locator("[data-change='CH-002']").count() == 1, body(pg)[:200])
pg.click("#ia-filter-flagged"); pg.wait_for_timeout(400)
check("the recorder is told a different person must void the record", "different person must void" in card_text(pg, "[data-change='CH-001']") and pg.locator("#ia-void-CH-001").count() == 0, card_text(pg, "[data-change='CH-001']"))
check("the server refuses the recorder voiding their own record", st(A("POST", f"/changes/{A('GET', '/changes', DARA)[0]['id']}/void", DARA, {"reason": "Entered in error by mistake"})) == 403)
tab(pg, "controls")
pg.fill("#ia-ct-system", "Payroll"); pg.fill("#ia-ct-name", "Duplicate payee check"); pg.fill("#ia-ct-desc", "The payroll system rejects a second payee with the same bank account number"); pg.fill("#ia-ct-expected", "The duplicate payee is rejected")
pg.fill("#ia-ct-tol", "21"); pg.click("#ia-ct-save"); pg.wait_for_timeout(300)
check("a tolerable number over 20 is stopped", "0 to 20" in txt(pg, "#control-problem"), txt(pg, "#control-problem"))
pg.fill("#ia-ct-tol", "1"); pg.click("#ia-ct-save"); pg.wait_for_timeout(1500)
check("control defined and flagged as never tested", "AC-001" in txt(pg, "#ia-controls") and "Never tested" in card_text(pg, "[data-control='AC-001']"), txt(pg, "#ia-notice") + err(pg))
tab(pg, "overview")
check("the overview says the control has never been tested and changes with flags are untested", "never been tested" in txt(pg, "#ia-attention") and "have a flag" in txt(pg, "#ia-attention"), txt(pg, "#ia-attention"))
tab(pg, "tests")
check("the definer of a control is not offered it to test", "cannot test a control you defined" in txt(pg, "#ia-ctest-card"), txt(pg, "#ia-ctest-card"))
pg.fill("#ia-pt-title", "October change test"); pg.fill("#ia-pt-from", D(-30)); pg.fill("#ia-pt-to", D(-1)); pg.fill("#ia-pt-size", "10"); pg.fill("#ia-pt-seed", "october-sample"); pg.click("#ia-pt-save"); pg.wait_for_timeout(1200)
check("a sample that includes your own records cannot be planned", "you recorded" in err(pg) and "TS-001" not in txt(pg, "#ia-tests"), err(pg))

# ---- Tunde (administrator, can prepare) tests the changes and the control ----
sign_in(pg, *TUNDE, "Meridian"); goto(pg, "/itaudit")
check("the menu offers IT audit to an administrator", "#/itaudit" in hrefs(pg), hrefs(pg))
check("an administrator cannot change the settings", pg.locator("#ia-policy-save").count() == 0)
tab(pg, "changes")
check("an administrator can record changes but not void them", pg.locator("#ia-ch-save").count() == 1 and pg.locator("#ia-void-CH-001").count() == 0)
tab(pg, "controls")
check("an administrator can define controls but not retire them", pg.locator("#ia-ct-save").count() == 1 and pg.locator("#ia-retire-AC-001").count() == 0)
tab(pg, "tests")
pg.fill("#ia-pt-title", "Scratch test planned too early"); pg.fill("#ia-pt-from", D(-30)); pg.fill("#ia-pt-to", D(-1)); pg.fill("#ia-pt-size", "1"); pg.fill("#ia-pt-seed", "scratch"); pg.click("#ia-pt-save"); pg.wait_for_timeout(1500)
check("a one-change test is planned", "TS-001" in txt(pg, "#ia-tests") and "1 of 4" in txt(pg, "#ia-sample-info"), txt(pg, "#ia-notice") + err(pg))
pg.fill("#note-wd-" + A("GET", "/tests", TUNDE)[0]["id"], "short"); pg.click("#ia-test-withdraw"); pg.wait_for_timeout(400)
check("a short withdrawal reason is stopped", "at least 10" in err(pg), err(pg))
pg.fill("#note-wd-" + A("GET", "/tests", TUNDE)[0]["id"], "Planned before the other changes were in"); pg.click("#ia-test-withdraw"); pg.wait_for_timeout(1500)
check("the test is withdrawn and says so", "Withdrawn" in txt(pg, "#ia-withdrawn") and pg.locator("#ia-test-withdraw").count() == 0, txt(pg, "#ia-notice") + err(pg))
pg.fill("#ia-pt-title", "October change test"); pg.fill("#ia-pt-from", D(-30)); pg.fill("#ia-pt-to", D(-1)); pg.fill("#ia-pt-size", "10"); pg.fill("#ia-pt-seed", "october-sample"); pg.fill("#ia-pt-tol", "0"); pg.click("#ia-pt-save"); pg.wait_for_timeout(1500)
check("the real test samples all four changes and shows how", "TS-002" in txt(pg, "#ia-tests") and "4 of 4" in txt(pg, "#ia-sample-info") and "october-sample" in txt(pg, "#ia-sample-info"), txt(pg, "#ia-sample-info") + err(pg))
check("the submit button is not offered while changes are unconcluded", pg.locator("#ia-test-submit").count() == 0 and "still need a conclusion" in txt(pg, "#ia-blocked"), txt(pg, "#ia-blocked"))
t2 = [t for t in A("GET", "/tests", TUNDE) if t["ref"] == "TS-002"][0]; items = {i["ref"]: i["id"] for i in A("GET", f"/tests/{t2['id']}", TUNDE)["items"]}
check("the sample is repeatable (the same seed gives the same four)", sorted(items) == ["CH-001", "CH-002", "CH-003", "CH-004"], items)
pg.click("#ia-item-CH-001-ok"); pg.wait_for_timeout(1200)
check("a clean change is concluded with no note", "No exception" in card_text(pg, "[data-item='CH-001']") and "CH-001 concluded" in txt(pg, "#ia-notice"), txt(pg, "#ia-notice") + err(pg))
pg.fill(f"#note-it-{items['CH-002']}", "approved by email"); pg.click("#ia-item-CH-002-ok"); pg.wait_for_timeout(400)
check("a flagged change cannot be called no-exception with a thin note", "20 characters" in err(pg), err(pg))
pg.fill(f"#note-it-{items['CH-002']}", "Approval was given by email; the copy is filed under the ticket"); pg.click("#ia-item-CH-002-ok"); pg.wait_for_timeout(1200)
check("a flagged change is concluded with an explanation and the override is shown", "flags overridden" in card_text(pg, "[data-item='CH-002']"), card_text(pg, "[data-item='CH-002']") + err(pg))
pg.click("#ia-item-CH-003-exc"); pg.wait_for_timeout(400)
check("an exception needs a note", "at least 10" in err(pg), err(pg))
pg.fill(f"#note-it-{items['CH-003']}", "Approved seven days after go-live"); pg.click("#ia-item-CH-003-exc"); pg.wait_for_timeout(1200)
pg.fill(f"#note-it-{items['CH-004']}", "The requester approved their own change"); pg.click("#ia-item-CH-004-exc"); pg.wait_for_timeout(1200)
check("all four changes concluded and the tolerance line counts the exceptions", "2 exception(s) found; 0 tolerable" in txt(pg, "#ia-tolerance"), txt(pg, "#ia-tolerance"))
pg.click("#ia-test-submit"); pg.wait_for_timeout(1500)
check("the test is submitted and can no longer be worked on", "Waiting for approval" in txt(pg, "#ia-test-detail") and pg.locator("#ia-item-CH-001-ok").count() == 0 and pg.locator("#ia-test-withdraw").count() == 0, txt(pg, "#ia-notice") + err(pg))
check("the preparer is told a different person must approve it", "different person must approve" in txt(pg, "#ia-test-detail") or pg.locator("#ia-test-approve").count() == 0, txt(pg, "#ia-test-detail")[:300])
# a control test
pg.fill("#ia-cx-title", "Test the duplicate payee check"); pg.select_option("#ia-cx-control", label=[o for o in pg.locator("#ia-cx-control option").all_text_contents() if "AC-001" in o][0]); pg.click("#ia-cx-save"); pg.wait_for_timeout(1500)
check("a control test is planned by a different person from the definer", "TS-003" in txt(pg, "#ia-tests") and "Duplicate payee check" in txt(pg, "#ia-test-detail"), txt(pg, "#ia-notice") + err(pg))
pg.fill("#ia-cs-desc", "Entered a payee with an existing bank account"); pg.fill("#ia-cs-date", D(-1)); pg.fill("#ia-cs-expected", "Rejected"); pg.fill("#ia-cs-actual", "Accepted"); pg.select_option("#ia-cs-result", "FAIL"); pg.click("#ia-cs-save"); pg.wait_for_timeout(300)
check("a failed case needs a note", "failure" in txt(pg, "#case-problem"), txt(pg, "#case-problem"))
pg.fill("#ia-cs-note", "The duplicate payee was accepted without a warning"); pg.click("#ia-cs-save"); pg.wait_for_timeout(1500)
check("the failed case is recorded and counted", "Failed" in txt(pg, "#ia-cases") and "1 exception(s) found; 1 tolerable" in txt(pg, "#ia-tolerance"), txt(pg, "#ia-notice") + err(pg))
pg.fill("#ia-cs-desc", "Entered a payee with a new bank account"); pg.fill("#ia-cs-date", D(-1)); pg.fill("#ia-cs-expected", "Accepted"); pg.fill("#ia-cs-actual", "Accepted"); pg.select_option("#ia-cs-result", "PASS"); pg.click("#ia-cs-save"); pg.wait_for_timeout(1500)
check("a passing case is recorded", "Passed" in txt(pg, "#ia-cases"), txt(pg, "#ia-notice") + err(pg))
pg.click("#ia-test-submit"); pg.wait_for_timeout(1500)
check("the control test is submitted", "Waiting for approval" in txt(pg, "#ia-test-detail"), txt(pg, "#ia-notice") + err(pg))
tid3 = [t for t in A("GET", "/tests", TUNDE) if t["ref"] == "TS-003"][0]["id"]
check("the server refuses an administrator approving", st(A("POST", f"/tests/{t2['id']}/approve", TUNDE, {"note": "Looks fine to me, approving it"})) == 403)
check("the server refuses a planner withdrawing a submitted test", st(A("POST", f"/tests/{t2['id']}/withdraw", TUNDE, {"reason": "Changed my mind about it"})) == 409)
check("the server refuses concluding an item on a submitted test", st(A("POST", f"/tests/{t2['id']}/items/{items['CH-001']}", TUNDE, {"result": "NO_EXCEPTION"})) == 409)

# ---- Dara cannot approve either test: she recorded the changes and defined the control ----
sign_in(pg, *DARA, "Meridian"); goto(pg, "/itaudit"); tab(pg, "tests")
open_test(pg, "TS-002")
check("the recorder of sampled changes cannot approve their test", pg.locator("#ia-test-approve").count() == 0 and "recorded one of the sampled" in txt(pg, "#ia-waiting"), txt(pg, "#ia-waiting"))
open_test(pg, "TS-003")
check("the definer of a control cannot approve its test", pg.locator("#ia-test-approve").count() == 0 and "defined this control" in txt(pg, "#ia-waiting"), txt(pg, "#ia-waiting"))
check("the server refuses both", st(A("POST", f"/tests/{t2['id']}/approve", DARA, {"note": "Approving my own records"})) == 403 and st(A("POST", f"/tests/{tid3}/approve", DARA, {"note": "Approving my own control"})) == 403)

# ---- Kwame (approver) decides ----
A("POST", "/changes", TUNDE, dict(system="Billing", title="Entered in the wrong system", description="Recorded in error, belongs to another company", change_type="STANDARD", risk="LOW", requested_by="Ada Obi", approved_by_name="Ben Eze", approved_on=D(-6), ticket_ref="CHG-105", implemented_on=D(-5)))
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/itaudit")
check("the overview says two tests are waiting", "2 test(s) are waiting" in txt(pg, "#ia-attention"), txt(pg, "#ia-attention"))
tab(pg, "tests"); open_test(pg, "TS-002")
check("an approver sees approve and send back and a note box", pg.locator("#ia-test-approve").count() == 1 and pg.locator("#ia-test-reject").count() == 1 and pg.locator(f"#note-test-{t2['id']}").count() == 1)
pg.click("#ia-test-approve"); pg.wait_for_timeout(400)
check("a test with exceptions cannot be approved without a note", "at least 10" in err(pg), err(pg))
pg.fill(f"#note-test-{t2['id']}", "short"); pg.click("#ia-test-reject"); pg.wait_for_timeout(400)
check("a short send-back reason is stopped", "at least 10" in err(pg), err(pg))
pg.fill(f"#note-test-{t2['id']}", "Please say who gave the email approval for CH-002"); pg.click("#ia-test-reject"); pg.wait_for_timeout(1500)
check("the test is sent back to be worked on again", "Being worked on" in txt(pg, "#ia-test-detail") and "Sent back" in txt(pg, "#ia-sent-back"), txt(pg, "#ia-notice") + err(pg))
check("the server refuses approving a test that is back in draft", st(A("POST", f"/tests/{t2['id']}/approve", KWAME, {"note": "Approving a draft test"})) == 409)
check("the preparer re-submits (second round)", A("POST", f"/tests/{t2['id']}/submit", TUNDE).get("status") == "SUBMITTED")
goto(pg, "/itaudit"); tab(pg, "tests"); open_test(pg, "TS-002")
pg.fill(f"#note-test-{t2['id']}", "Two exceptions reported to the change manager on the day"); pg.click("#ia-test-approve"); pg.wait_for_timeout(1500)
check("the change test is approved and is above tolerance", "Above tolerance" in txt(pg, "#ia-test-detail") and "approved by You" in txt(pg, "#ia-test-detail"), txt(pg, "#ia-notice") + err(pg))
open_test(pg, "TS-003")
pg.fill(f"#note-test-{tid3}", "One failure, within the number we agreed to tolerate"); pg.click("#ia-test-approve"); pg.wait_for_timeout(1500)
check("the control test is approved and is within tolerance", "Within tolerance" in txt(pg, "#ia-test-detail"), txt(pg, "#ia-notice") + err(pg))
tab(pg, "overview")
check("the overview now shows the test above tolerance and no waiting tests", "approved test(s) found more exceptions" in txt(pg, "#ia-attention") and "waiting for a different person" not in txt(pg, "#ia-attention"), txt(pg, "#ia-attention"))
tab(pg, "controls")
c1 = card_text(pg, "[data-control='AC-001']")
check("the control shows its last approved test and no retest due", "1 test(s)" in c1 and "Within tolerance" in c1 and "Retest due" not in c1, c1)
tab(pg, "changes")
ch_ids = {c["ref"]: c["id"] for c in A("GET", "/changes", DARA)}; ctl_id = A("GET", "/controls", DARA)[0]["id"]
sampled = ch_ids["CH-001"]
check("a change in an approved test sample cannot be voided", st(A("POST", f"/changes/{sampled}/void", KWAME, {"reason": "Entered in error by mistake"})) == 409)
pg.fill("#note-void-" + ch_ids["CH-005"], "short"); pg.click("#ia-void-CH-005"); pg.wait_for_timeout(400)
check("a short void reason is stopped", "at least 10" in err(pg), err(pg))
pg.fill("#note-void-" + ch_ids["CH-005"], "Recorded against the wrong company by mistake"); pg.click("#ia-void-CH-005"); pg.wait_for_timeout(1500)
check("the change is voided and the reason is kept", "Voided" in card_text(pg, "[data-change='CH-005']") and "wrong company" in card_text(pg, "[data-change='CH-005']"), txt(pg, "#ia-notice") + err(pg))
tab(pg, "controls")
pg.fill("#note-retire-" + ctl_id, "short"); pg.click("#ia-retire-AC-001"); pg.wait_for_timeout(400)
check("a short retire reason is stopped", "at least 10" in err(pg), err(pg))
pg.fill("#note-retire-" + ctl_id, "Replaced by a new payroll system"); pg.click("#ia-retire-AC-001"); pg.wait_for_timeout(1500)
check("the control is retired", "Retired" in card_text(pg, "[data-control='AC-001']") and "Replaced by a new payroll system" in card_text(pg, "[data-control='AC-001']"), txt(pg, "#ia-notice") + err(pg))
check("a retired control cannot be tested", st(A("POST", "/tests/control", TUNDE, {"title": "Test of a retired control", "control_id": ctl_id})) == 409)
tab(pg, "overview")
pg.fill("#ia-policy-emerg", "99"); pg.click("#ia-policy-save"); pg.wait_for_timeout(400)
check("an out-of-range window is stopped", "0 to 60" in body(pg), body(pg)[:200])
pg.fill("#ia-policy-emerg", "7"); pg.click("#ia-policy-save"); pg.wait_for_timeout(1500)
check("settings saved and the meaning updates", "Settings saved" in txt(pg, "#ia-notice") and "within 7 days" in txt(pg, "#ia-policy-meaning"), txt(pg, "#ia-notice") + err(pg))
check("an earlier emergency change keeps the window it was recorded under", [c for c in A("GET", "/changes", DARA) if c["ref"] == "CH-003"][0]["ratify_days"] == 5)

# ---- isolation and audit ----
check("the other company sees none of it", A("GET", "/changes", OTHER, org="Other") == [] and A("GET", "/controls", OTHER, org="Other") == [] and A("GET", "/tests", OTHER, org="Other") == [])
check("the other company cannot read or act on a test", st(A("GET", f"/tests/{t2['id']}", OTHER, org="Other")) == 404 and st(A("POST", f"/tests/{t2['id']}/approve", OTHER, {"note": "Approving from outside"}, org="Other")) == 404)
acts = api("GET", "/_audit", DARA, "Meridian")["actions"]
need_ = ["ITAUDIT_CHANGE_RECORDED", "ITAUDIT_CHANGE_VOIDED", "ITAUDIT_CONTROL_DEFINED", "ITAUDIT_CONTROL_RETIRED", "ITAUDIT_TEST_PLANNED", "ITAUDIT_TEST_WITHDRAWN", "ITAUDIT_ITEM_CONCLUDED", "ITAUDIT_CASE_ADDED",
         "ITAUDIT_TEST_SUBMITTED", "ITAUDIT_TEST_REJECTED", "ITAUDIT_TEST_APPROVED", "ITAUDIT_POLICY_SET"]
check("every step was written to the audit trail", all(x in acts for x in need_), [x for x in need_ if x not in acts])
check("no page errors in the browser", not errs, errs[:3])
finish(p, b)
