"""Browser journey: Financial-crime casework (Stage 19). Run via e2e/run_all.py."""
from datetime import date, datetime, timedelta, timezone

from common import *

TODAY = datetime.now(timezone.utc).date()                      # the server works in UTC dates
D = lambda n: (TODAY + timedelta(days=n)).isoformat()
def hrefs(pg): return [a.get_attribute("href") for a in pg.locator(".app-sidebar a").all()]
def tab(pg, name):
    pg.click(f"#fx-tab-{name}"); pg.wait_for_timeout(900)
def body(pg): return pg.inner_text("body")
def err(pg): return txt(pg, ".alert-error")
def A(m, path, who, bodyj=None, org="Meridian"): return api(m, "/fincrime" + path, who, org, bodyj)
def st(r): return r.get("status") if isinstance(r, dict) else None

start_web()
p, b, pg, errs = session()

# ---- an accountant has no business here: no menu entry, no content, the server refuses ----
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/fincrime")
check("the menu does not offer financial-crime casework to an accountant", "#/fincrime" not in hrefs(pg), hrefs(pg))
check("typing the address shows no case content", "Open a case" not in body(pg) and "Raise an alert" not in body(pg), body(pg)[:200])
check("the server refuses an accountant (overview)", st(A("GET", "/overview", AISHA)) == 403)
check("the server refuses an accountant (cases)", st(A("GET", "/cases", AISHA)) == 403)

# ---- Dara (owner) raises alerts ----
sign_in(pg, *DARA, "Meridian"); goto(pg, "/fincrime")
check("the menu offers financial-crime casework", "#/fincrime" in hrefs(pg), hrefs(pg))
check("the banner says nothing is screened or filed", "does not screen anyone" in txt(pg, "#fx-banner") and "conflict of interest" in txt(pg, "#fx-banner"), txt(pg, "#fx-banner"))
check("nothing needs attention yet", "Nothing needs attention" in txt(pg, "#fx-attention"), txt(pg, "#fx-attention"))
tab(pg, "alerts")
pg.click("#fx-al-save"); pg.wait_for_timeout(300)
check("an empty alert is stopped with a plain sentence", "at least 10" in txt(pg, "#alert-problem"), txt(pg, "#alert-problem"))
pg.fill("#fx-al-summary", "A supplier asked for payment into a personal account"); pg.fill("#fx-al-date", D(5)); pg.click("#fx-al-save"); pg.wait_for_timeout(1200)
check("a date in the future is refused by the server", "future" in err(pg).lower(), err(pg) + txt(pg, "#alert-problem"))
pg.fill("#fx-al-date", D(-3)); pg.fill("#fx-al-amount", "2,500.505"); pg.fill("#fx-al-cur", "ngn"); pg.click("#fx-al-save"); pg.wait_for_timeout(300)
check("an amount with too many decimals is stopped", "decimal" in txt(pg, "#alert-problem").lower(), txt(pg, "#alert-problem"))
pg.fill("#fx-al-amount", "2,500.50"); pg.click("#fx-al-save"); pg.wait_for_timeout(1500)
check("alert raised", "Alert raised" in txt(pg, "#fx-notice") and "AL-001" in txt(pg, "#fx-alerts") and "2500.50 NGN" in txt(pg, "#fx-alerts"), txt(pg, "#fx-notice") + err(pg))
pg.fill("#fx-al-summary", "A second report about the same supplier from a colleague"); pg.fill("#fx-al-date", D(-2)); pg.click("#fx-al-save"); pg.wait_for_timeout(1500)
check("a second alert was raised", "AL-002" in txt(pg, "#fx-alerts"), txt(pg, "#fx-alerts"))
AL = {x["ref"]: x["id"] for x in A("GET", "/alerts", DARA)}
check("the person who raised an alert cannot dismiss it (server)", st(A("POST", f"/alerts/{AL['AL-002']}/dismiss", DARA, {"reason": "Nothing in it after checking"})) == 403)
check("the raiser is told a different person must dismiss", "different person must dismiss" in txt(pg, "#fx-alerts"), txt(pg, "#fx-alerts"))

# ---- Kwame (approver) dismisses one alert ----
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/fincrime"); tab(pg, "alerts")
check("a decision-maker sees no raise form", pg.locator("#fx-al-save").count() == 0)
pg.fill(f"#note-al-{AL['AL-002']}", "short"); pg.click("#fx-al-AL-002-dismiss"); pg.wait_for_timeout(400)
check("a short reason is stopped", "at least 10" in err(pg), err(pg))
pg.fill(f"#note-al-{AL['AL-002']}", "Duplicate of the first report, same supplier"); pg.click("#fx-al-AL-002-dismiss"); pg.wait_for_timeout(1500)
check("alert dismissed with the reason kept", "Alert dismissed" in txt(pg, "#fx-notice") and "Duplicate of the first report" in txt(pg, "#fx-alerts"), txt(pg, "#fx-notice") + err(pg))

# ---- Dara opens a case ----
sign_in(pg, *DARA, "Meridian"); goto(pg, "/fincrime"); tab(pg, "cases")
pg.fill("#fx-case-title", "Payments to a personal account"); pg.fill("#fx-case-summary", "A supplier asked for payment into an account in a person's name"); pg.check(f"#fx-case-alert-AL-001")
pg.select_option("#fx-case-conflict", "yes"); pg.fill("#fx-case-conflict-note", "short"); pg.click("#fx-case-save"); pg.wait_for_timeout(300)
check("a conflict must be described", "conflict" in txt(pg, "#casef-problem").lower(), txt(pg, "#casef-problem"))
pg.fill("#fx-case-conflict-note", "The supplier is my brother-in-law"); pg.click("#fx-case-save"); pg.wait_for_timeout(1500)
check("someone with a conflict cannot open or lead the case", "conflict of interest" in err(pg) and "CS-001" not in txt(pg, "#fx-cases"), err(pg) + txt(pg, "#fx-cases"))
pg.select_option("#fx-case-conflict", "no"); pg.click("#fx-case-save"); pg.wait_for_timeout(1500)
check("case opened, with the opener as lead and a declaration on file", "CS-001" in txt(pg, "#fx-notice") and "no conflict" in txt(pg, "#fx-declarations") and "AL-001" in txt(pg, "#fx-cases"), txt(pg, "#fx-notice") + err(pg))
C = A("GET", "/cases", DARA)[0]["id"]
check("the alert moved into the case", A("GET", "/alerts", DARA)[0]["status"] == "IN_CASE")

# timeline
pg.fill("#fx-ev-date", D(5)); pg.fill("#fx-ev-text", "Supplier phoned to chase"); pg.click("#fx-ev-save"); pg.wait_for_timeout(1200)
check("an event in the future is refused", "future" in err(pg).lower(), err(pg))
pg.fill("#fx-ev-date", D(-2)); pg.click("#fx-ev-save"); pg.wait_for_timeout(1500)
check("event added to the timeline", "Supplier phoned to chase" in txt(pg, "#fx-timeline"), txt(pg, "#fx-timeline") + err(pg))
# screening with a possible match
pg.fill("#fx-sc-subject", "Acme Trading Ltd"); pg.fill("#fx-sc-list", "Internal watch list"); pg.fill("#fx-sc-date", D(-1)); pg.select_option("#fx-sc-result", "POSSIBLE_MATCH"); pg.fill("#fx-sc-note", "Similar name, different country"); pg.click("#fx-sc-save"); pg.wait_for_timeout(1500)
check("screening result recorded as waiting for a different person", "Possible match" in txt(pg, "#fx-screenings") and "Waiting for a different person" in txt(pg, "#fx-screenings"), txt(pg, "#fx-screenings") + err(pg))
# loss and recovery
pg.fill("#fx-loss-amount", "1,000.10"); pg.fill("#fx-loss-cur", "ngn"); pg.fill("#fx-loss-date", D(-4)); pg.fill("#fx-loss-desc", "Payment made to the wrong account"); pg.click("#fx-loss-save"); pg.wait_for_timeout(1500)
check("loss recorded and shown exactly", "Lost 1000.10 NGN" in txt(pg, "#fx-position"), txt(pg, "#fx-position") + err(pg))
pg.fill("#fx-rec-amount", "700"); pg.fill("#fx-rec-cur", "NGN"); pg.fill("#fx-rec-date", D(-1)); pg.fill("#fx-rec-note", "First part repaid by the supplier"); pg.click("#fx-rec-save"); pg.wait_for_timeout(1500)
pg.fill("#fx-rec-amount", "400"); pg.fill("#fx-rec-cur", "NGN"); pg.fill("#fx-rec-date", D(-1)); pg.fill("#fx-rec-note", "Second part repaid by the supplier"); pg.click("#fx-rec-save"); pg.wait_for_timeout(1500)
check("a recovery bigger than the loss is refused by the server", "cannot be more than the loss" in err(pg), err(pg) + txt(pg, "#fx-position"))
# outcome blocked while the match is unresolved
pg.fill("#fx-dec-rationale", "The money was recovered and the control was changed so it cannot recur"); pg.click("#fx-dec-save"); pg.wait_for_timeout(1500)
check("an outcome is refused while a possible match is unresolved", "possible screening match" in err(pg), err(pg))
check("the lead cannot resolve their own screening result (server)", st(A("POST", f"/cases/{C}/screenings/{A('GET', '/cases/' + C, DARA)['screenings'][0]['id']}/resolve", DARA, {"outcome": "FALSE_POSITIVE", "reason": "Different country entirely"})) in (403,))

# ---- Kwame declares, then resolves and confirms ----
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/fincrime"); tab(pg, "cases")
pg.click("#fx-case-open-CS-001"); pg.wait_for_timeout(900)
check("a decision-maker who has not declared is asked to", pg.locator("#fx-need-declaration").count() == 1 and pg.locator("#fx-sc-1-false").count() == 0, txt(pg, "#fx-case-detail")[:300])
sid = A("GET", f"/cases/{C}", KWAME)["screenings"][0]["id"]
check("the server refuses a decision before the declaration", st(A("POST", f"/cases/{C}/screenings/{sid}/resolve", KWAME, {"outcome": "FALSE_POSITIVE", "reason": "Different country entirely"})) == 409)
check("a decision-maker cannot work the case (no forms)", pg.locator("#fx-ev-save").count() == 0 and pg.locator("#fx-dec-save").count() == 0)
pg.click("#fx-decl-save"); pg.wait_for_timeout(1500)
check("declaration recorded", "no conflict" in txt(pg, "#fx-declarations") and pg.locator("#fx-need-declaration").count() == 0 and pg.locator("#fx-sc-1-false").count() == 1, txt(pg, "#fx-declarations") + err(pg))
pg.click("#fx-sc-1-false"); pg.wait_for_timeout(500)
check("a resolution needs a written reason", "reason" in err(pg).lower(), err(pg))
pg.fill(f"#note-case-{C}", "Different country and date of birth"); pg.click("#fx-sc-1-false"); pg.wait_for_timeout(1500)
check("possible match resolved as not a match", "Not a match" in txt(pg, "#fx-screenings") and "Different country" in txt(pg, "#fx-screenings"), txt(pg, "#fx-screenings") + err(pg))
pg.click("#fx-rec-1-confirm"); pg.wait_for_timeout(1500)
check("recovery confirmed and the position is exact", "recovered and confirmed 700.00" in txt(pg, "#fx-position") and "still outstanding 300.10" in txt(pg, "#fx-position"), txt(pg, "#fx-position") + err(pg))

# ---- Dara proposes; cannot decide; Kwame sends back, then approves ----
sign_in(pg, *DARA, "Meridian"); goto(pg, "/fincrime"); tab(pg, "cases"); pg.click("#fx-case-open-CS-001"); pg.wait_for_timeout(900)
pg.select_option("#fx-dec-outcome", "NO_CONCERN"); pg.fill("#fx-dec-rationale", "The money was recovered and the control was changed so it cannot recur"); pg.click("#fx-dec-save"); pg.wait_for_timeout(1500)
check("'no concern' is refused when a loss has been recorded", "cannot be proposed" in err(pg), err(pg))
pg.select_option("#fx-dec-outcome", "CONCERN_RESOLVED"); pg.click("#fx-dec-save"); pg.wait_for_timeout(1500)
check("outcome proposed and waiting for a different person", "Outcome proposed" in txt(pg, "#fx-notice") and "different person must decide" in txt(pg, "#fx-waiting"), txt(pg, "#fx-notice") + err(pg))
check("the lead has no approve button", pg.locator("#fx-dec-approve").count() == 0)
check("the lead cannot approve (server)", st(A("POST", f"/cases/{C}/decision/approve", DARA, {})) == 403)

sign_in(pg, *KWAME, "Meridian"); goto(pg, "/fincrime"); tab(pg, "cases"); pg.click("#fx-case-open-CS-001"); pg.wait_for_timeout(900)
check("the decision-maker sees approve and send back", pg.locator("#fx-dec-approve").count() == 1 and pg.locator("#fx-dec-reject").count() == 1)
pg.click("#fx-dec-reject"); pg.wait_for_timeout(500)
check("sending back needs a written reason", "reason" in err(pg).lower(), err(pg))
pg.fill(f"#note-case-{C}", "Please add the date the control was changed"); pg.click("#fx-dec-reject"); pg.wait_for_timeout(1500)
check("outcome sent back, case open again", "sent back" in txt(pg, "#fx-notice").lower() and "Sent back: Please add the date" in txt(pg, "#fx-decision"), txt(pg, "#fx-notice") + err(pg))
sign_in(pg, *DARA, "Meridian"); goto(pg, "/fincrime"); tab(pg, "cases"); pg.click("#fx-case-open-CS-001"); pg.wait_for_timeout(900)
pg.select_option("#fx-dec-outcome", "CONCERN_RESOLVED"); pg.fill("#fx-dec-rationale", "The money was recovered and the control was changed on the 1st; it cannot recur"); pg.click("#fx-dec-save"); pg.wait_for_timeout(1500)
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/fincrime"); tab(pg, "cases"); pg.click("#fx-case-open-CS-001"); pg.wait_for_timeout(900)
pg.click("#fx-dec-approve"); pg.wait_for_timeout(1500)
check("outcome approved and the case closed", "case is closed" in txt(pg, "#fx-notice").lower() and "Closed" in txt(pg, "#fx-cases"), txt(pg, "#fx-notice") + err(pg))
check("a closed case cannot be added to (server)", st(A("POST", f"/cases/{C}/events", DARA, {"occurred_on": D(-1), "kind": "OTHER", "text": "Too late for this"})) == 409)

# ---- reopen ----
goto(pg, "/fincrime"); tab(pg, "cases")
if pg.locator("#fx-case-detail").count() == 0: pg.click("#fx-case-open-CS-001"); pg.wait_for_timeout(900)      # the open case is remembered between visits
pg.click("#fx-case-reopen"); pg.wait_for_timeout(500)
check("reopening needs a written reason", "reason" in err(pg).lower(), err(pg))
pg.fill(f"#note-case-{C}", "New information has come in from the bank"); pg.click("#fx-case-reopen"); pg.wait_for_timeout(1500)
check("case reopened and the history kept", "reopened" in txt(pg, "#fx-notice").lower() and "decision approved" in txt(pg, "#fx-case-detail").lower(), txt(pg, "#fx-notice") + err(pg))

# ---- targets, isolation, audit ----
tab(pg, "overview")
pg.fill("#fx-policy-alert", "99"); pg.click("#fx-policy-save"); pg.wait_for_timeout(400)
check("an out-of-range target is stopped", "0 to 60" in body(pg), body(pg)[:200])
pg.fill("#fx-policy-alert", "3"); pg.click("#fx-policy-save"); pg.wait_for_timeout(1500)
check("targets saved", "Targets saved" in txt(pg, "#fx-notice"), txt(pg, "#fx-notice") + err(pg))
check("the other company sees none of it", A("GET", "/cases", OTHER, org="Other").__class__ is list and A("GET", "/cases", OTHER, org="Other") == [] and st(A("GET", f"/cases/{C}", OTHER, org="Other")) in (403, 404))
check("the other company cannot act on it", st(A("POST", f"/cases/{C}/reopen", OTHER, {"reason": "No right to do this"}, org="Other")) in (403, 404))
acts = api("GET", "/_audit", DARA, "Meridian")["actions"]
need_ = ["FINCRIME_ALERT_RAISED", "FINCRIME_ALERT_DISMISSED", "FINCRIME_CASE_OPENED", "FINCRIME_EVENT_ADDED", "FINCRIME_INTEREST_DECLARED", "FINCRIME_SCREENING_RECORDED", "FINCRIME_SCREENING_RESOLVED", "FINCRIME_LOSS_RECORDED",
         "FINCRIME_RECOVERY_RECORDED", "FINCRIME_RECOVERY_CONFIRMED", "FINCRIME_DECISION_PROPOSED", "FINCRIME_DECISION_REJECTED", "FINCRIME_DECISION_APPROVED", "FINCRIME_CASE_REOPENED", "FINCRIME_POLICY_SET"]
check("every step was written to the audit trail", all(x in acts for x in need_), [x for x in need_ if x not in acts])
check("no page errors in the browser", not errs, errs[:3])
finish(p, b)
