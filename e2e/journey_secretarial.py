"""Browser journey: Company secretarial (Stage 24). Run via e2e/run_all.py."""
from datetime import datetime, timedelta, timezone

from common import *

TODAY = datetime.now(timezone.utc).date()
D = lambda n: (TODAY + timedelta(days=n)).isoformat()
def hrefs(pg): return [a.get_attribute("href") for a in pg.locator(".app-sidebar a").all()]
def tab(pg, name):
    pg.click(f"#cs-tab-{name}"); pg.wait_for_timeout(900)
def body(pg): return pg.inner_text("body")
def err(pg): return txt(pg, ".alert-error")
def A(m, path, who, bodyj=None, org="Meridian"): return api(m, "/secretarial" + path, who, org, bodyj)
def st(r): return r.get("status") if isinstance(r, dict) else None
MT = dict(kind="BOARD", title="Quarterly board meeting", held_on=D(-1), location="Head office boardroom", agenda="Accounts, budget and the new bank mandate")
MINUTES = "The board reviewed the accounts and agreed the budget for the year."

start_web()
p, b, pg, errs = session()

# ---- an accountant has no business here ----
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/secretarial")
check("the menu does not offer the workspace to an accountant", "#/secretarial" not in hrefs(pg), hrefs(pg))
check("typing the address shows no content", "Schedule a meeting" not in body(pg), body(pg)[:200])
check("the server refuses an accountant (overview)", st(A("GET", "/overview", AISHA)) == 403)
check("the server refuses an accountant (meetings)", st(A("GET", "/meetings", AISHA)) == 403)

# ---- Dara schedules a meeting ----
sign_in(pg, *DARA, "Meridian"); goto(pg, "/secretarial")
check("the menu offers the workspace", "#/secretarial" in hrefs(pg), hrefs(pg))
check("the banner says it checks no law", "checks no law" in txt(pg, "#cs-banner") and "not a signed statutory record" in txt(pg, "#cs-banner"), txt(pg, "#cs-banner"))
check("nothing needs attention yet", "Nothing needs attention" in txt(pg, "#cs-attention"), txt(pg, "#cs-attention"))
tab(pg, "meetings")
pg.click("#cs-mt-save"); pg.wait_for_timeout(300)
check("an empty form is stopped with a plain sentence", "title" in txt(pg, "#meeting-problem").lower(), txt(pg, "#meeting-problem"))
pg.fill("#cs-mt-title", MT["title"]); pg.fill("#cs-mt-date", "2026-02-30"); pg.fill("#cs-mt-loc", MT["location"]); pg.fill("#cs-mt-agenda", MT["agenda"]); pg.click("#cs-mt-save"); pg.wait_for_timeout(300)
check("an impossible date is stopped", "real date" in txt(pg, "#meeting-problem"), txt(pg, "#meeting-problem"))
pg.fill("#cs-mt-date", MT["held_on"]); pg.click("#cs-mt-save"); pg.wait_for_timeout(1500)
check("the meeting is scheduled and shows no minutes yet", "MT-001" in txt(pg, "#cs-meetings") and "No minutes yet" in txt(pg, "[data-meeting='MT-001']"), txt(pg, "#cs-notice") + err(pg))
mt2 = A("POST", "/meetings", TUNDE, dict(MT, title="Annual general meeting", kind="ANNUAL_GENERAL", held_on=D(30)))
check("a future meeting is scheduled", mt2.get("ref") == "MT-002", mt2)
check("a bad kind is refused", st(A("POST", "/meetings", TUNDE, dict(MT, kind="PARTY"))) == 400)
mid1 = A("GET", "/meetings", TUNDE)[0]["id"]; mid2 = mt2["id"]
check("minutes cannot be recorded before the meeting date", st(A("POST", f"/meetings/{mid2}/minutes", TUNDE, dict(attendees="Ada Obi", minutes=MINUTES))) == 400)

# ---- Tunde proposes resolutions ----
sign_in(pg, *TUNDE, "Meridian"); goto(pg, "/secretarial"); tab(pg, "resolutions")
pg.select_option("#cs-rs-meeting", index=1); pg.fill("#cs-rs-text", "short"); pg.click("#cs-rs-save"); pg.wait_for_timeout(300)
check("a short resolution is stopped", "20 characters" in txt(pg, "#resolution-problem"), txt(pg, "#resolution-problem"))
pg.fill("#cs-rs-text", "That the budget for the year is approved as presented"); pg.click("#cs-rs-save"); pg.wait_for_timeout(1500)
check("the resolution is proposed", "RS-001" in txt(pg, "#cs-resolutions") and "once minutes of the meeting are recorded" in txt(pg, "[data-resolution='RS-001']"), txt(pg, "#cs-notice") + err(pg))
rid1 = A("GET", "/resolutions", TUNDE)[0]["id"]
rw = A("POST", "/resolutions", TUNDE, dict(kind="WRITTEN", text="That the registered address is changed to the new office"))
check("a written resolution needs no meeting", rw.get("ref") == "RS-002" and rw.get("can_decide") is True, rw)
check("a resolution put to a missing meeting is refused", st(A("POST", "/resolutions", TUNDE, dict(kind="ORDINARY", text="That nothing at all is changed this year", meeting_id="nope"))) == 404)
check("it cannot be decided before the minutes exist", st(A("POST", f"/resolutions/{rid1}/decide", KWAME, dict(votes_for=4, votes_against=1, abstentions=0, outcome="PASSED", note="Counted by the chair"))) == 409)

# ---- Tunde records the minutes, Kwame approves ----
goto(pg, "/secretarial"); tab(pg, "meetings")
pg.fill("#cs-mn-MT-001-att", "Ada Obi"); pg.fill("#cs-mn-MT-001-text", "short"); pg.click("#cs-mt-MT-001-minutes"); pg.wait_for_timeout(400)
check("short minutes are stopped", "20 characters" in txt(pg, "#minutes-" + mid1 + "-problem"), txt(pg, "#minutes-" + mid1 + "-problem"))
pg.fill("#cs-mn-MT-001-text", MINUTES); pg.click("#cs-mt-MT-001-minutes"); pg.wait_for_timeout(1500)
check("the minutes are recorded and wait for approval", "Minutes waiting for approval" in txt(pg, "[data-meeting='MT-001']") and MINUTES in txt(pg, "[data-meeting='MT-001']"), txt(pg, "[data-meeting='MT-001']") + err(pg))
check("recording twice is refused", st(A("POST", f"/meetings/{mid1}/minutes", TUNDE, dict(attendees="Ada Obi", minutes=MINUTES))) == 409)
check("an administrator cannot approve minutes", st(A("POST", f"/meetings/{mid1}/approve", TUNDE, {})) == 403)
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/secretarial"); tab(pg, "meetings")
pg.fill("#cs-mt-MT-001-note", "ok"); pg.click("#cs-mt-MT-001-approve"); pg.wait_for_timeout(500)
check("a short approval note is stopped", "10 characters" in err(pg) or "note" in err(pg).lower(), err(pg))
pg.fill("#cs-mt-MT-001-note", ""); pg.click("#cs-mt-MT-001-approve"); pg.wait_for_timeout(1500)
check("a different person approves the minutes", "Minutes approved" in txt(pg, "[data-meeting='MT-001']"), txt(pg, "[data-meeting='MT-001']") + err(pg))
check("no resolution can be added once minutes are approved", st(A("POST", "/resolutions", TUNDE, dict(kind="ORDINARY", text="That something is added too late", meeting_id=mid1))) == 409)

# ---- Kwame decides ----
tab(pg, "resolutions")
pg.fill("#cs-rs-RS-001-for", "2"); pg.fill("#cs-rs-RS-001-against", "2"); pg.fill("#cs-rs-RS-001-note", "Counted by the chair"); pg.click("#cs-rs-RS-001-decide"); pg.wait_for_timeout(400)
check("a tie cannot be recorded as passed", "more votes were for" in txt(pg, "#decide-" + rid1 + "-problem"), txt(pg, "#decide-" + rid1 + "-problem"))
pg.fill("#cs-rs-RS-001-for", "4"); pg.fill("#cs-rs-RS-001-against", "1"); pg.click("#cs-rs-RS-001-decide"); pg.wait_for_timeout(1500)
check("the resolution passes", "Passed" in txt(pg, "[data-resolution='RS-001']") and "4 for, 1 against" in txt(pg, "[data-resolution='RS-001']"), txt(pg, "[data-resolution='RS-001']") + err(pg))
check("a written resolution is decided by a different person", A("POST", f"/resolutions/{rw['id']}/decide", KWAME, dict(votes_for=1, votes_against=3, abstentions=0, outcome="FAILED", note="Counted by the secretary")).get("status") == "FAILED")
check("a decided resolution cannot be decided again", st(A("POST", f"/resolutions/{rid1}/decide", KWAME, dict(votes_for=4, votes_against=1, abstentions=0, outcome="PASSED", note="Counted by the chair"))) == 409)

# ---- the proposer, the recorder and the filer cannot approve their own work ----
rd = A("POST", "/resolutions", DARA, dict(kind="WRITTEN", text="That the auditors are reappointed for the coming year"))
check("the proposer cannot decide their own resolution", st(A("POST", f"/resolutions/{rd['id']}/decide", DARA, dict(votes_for=3, votes_against=0, abstentions=0, outcome="PASSED", note="Counted by me alone"))) == 403)
mt3 = A("POST", "/meetings", DARA, dict(MT, title="Committee meeting", kind="COMMITTEE"))
A("POST", f"/meetings/{mt3['id']}/minutes", DARA, dict(attendees="Ada Obi", minutes=MINUTES))
check("the person who recorded the minutes cannot approve them", st(A("POST", f"/meetings/{mt3['id']}/approve", DARA, {})) == 403)
check("a held meeting cannot be cancelled", st(A("POST", f"/meetings/{mt3['id']}/cancel", KWAME, {"reason": "Changed our minds on this"})) == 409)
check("a scheduled meeting can be cancelled with a reason", A("POST", f"/meetings/{mid2}/cancel", KWAME, {"reason": "Postponed to next quarter"}).get("status") == "CANCELLED")

# ---- filings ----
sign_in(pg, *DARA, "Meridian"); goto(pg, "/secretarial"); tab(pg, "filings")
pg.fill("#cs-fl-title", "Annual return for the year"); pg.fill("#cs-fl-auth", "Companies registry"); pg.fill("#cs-fl-due", D(-2)); pg.fill("#cs-fl-owner", "A"); pg.click("#cs-fl-save"); pg.wait_for_timeout(300)
check("a one-letter owner is stopped", "owner" in txt(pg, "#filing-problem").lower(), txt(pg, "#filing-problem"))
pg.fill("#cs-fl-owner", "Ada Obi"); pg.click("#cs-fl-save"); pg.wait_for_timeout(1500)
check("the filing is added and shown overdue", "FL-001" in txt(pg, "#cs-filings") and "Overdue" in txt(pg, "[data-filing='FL-001']"), txt(pg, "#cs-notice") + err(pg))
fl1 = A("GET", "/filings", TUNDE)[0]["id"]
soon = A("POST", "/filings", DARA, dict(kind="TAX_RETURN", title="Tax return for the year", authority="Revenue service", due_on=D(5), owner_name="Ada Obi"))
check("a filing due soon is flagged", soon.get("due_soon") is True and soon.get("overdue") is False, soon)
check("a due date more than five years away is refused", st(A("POST", "/filings", DARA, dict(kind="OTHER", title="Far away filing", authority="Registry", due_on=D(2200), owner_name="Ada Obi"))) == 400)
sign_in(pg, *TUNDE, "Meridian"); goto(pg, "/secretarial"); tab(pg, "filings")
pg.fill("#cs-fl-FL-001-date", D(5)); pg.fill("#cs-fl-FL-001-ref", "REG-2026-0042"); pg.click("#cs-fl-FL-001-file"); pg.wait_for_timeout(1200)
check("a future filing date is refused", "future" in (err(pg) + txt(pg, "#filed-" + fl1 + "-problem")).lower(), err(pg) + txt(pg, "#filed-" + fl1 + "-problem"))
pg.fill("#cs-fl-FL-001-date", D(-1)); pg.click("#cs-fl-FL-001-file"); pg.wait_for_timeout(1500)
check("the filing is recorded and waits for confirmation", "Filed: waiting for confirmation" in txt(pg, "[data-filing='FL-001']") and "REG-2026-0042" in txt(pg, "[data-filing='FL-001']") and "Overdue" not in txt(pg, "[data-filing='FL-001']"), txt(pg, "[data-filing='FL-001']") + err(pg))
check("the filer is an administrator and cannot confirm", st(A("POST", f"/filings/{fl1}/confirm", TUNDE, {"note": "Checked the receipt"})) == 403)
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/secretarial"); tab(pg, "filings")
pg.fill("#cs-fl-FL-001-note", "ok"); pg.click("#cs-fl-FL-001-confirm"); pg.wait_for_timeout(400)
check("a short confirmation note is stopped", "10 characters" in txt(pg, "#confirm-" + fl1 + "-problem"), txt(pg, "#confirm-" + fl1 + "-problem"))
pg.fill("#cs-fl-FL-001-note", "Checked the receipt against the registry"); pg.click("#cs-fl-FL-001-confirm"); pg.wait_for_timeout(1500)
check("a different person confirms the filing", "Confirmed" in txt(pg, "[data-filing='FL-001']") and "Checked the receipt against the registry" in txt(pg, "[data-filing='FL-001']"), txt(pg, "[data-filing='FL-001']") + err(pg))
A("POST", f"/filings/{soon['id']}/file", DARA, dict(filed_on=D(-1), receipt_ref="REG-2026-0043"))
check("the owner who recorded a filing cannot confirm it", st(A("POST", f"/filings/{soon['id']}/confirm", DARA, {"note": "Checked the receipt myself"})) == 403)
w = A("POST", "/filings", DARA, dict(kind="OTHER", title="Filing no longer needed", authority="Registry", due_on=D(40), owner_name="Ada Obi"))
check("an open filing can be withdrawn with a reason", A("POST", f"/filings/{w['id']}/withdraw", KWAME, {"reason": "No longer required of us"}).get("status") == "WITHDRAWN")
check("a filed one cannot be withdrawn", st(A("POST", f"/filings/{soon['id']}/withdraw", KWAME, {"reason": "No longer required of us"})) == 409)

# ---- overview and settings ----
sign_in(pg, *DARA, "Meridian"); goto(pg, "/secretarial"); tab(pg, "overview")
check("counts show the passed resolution and confirmed filing", "Resolutions passed: 1" in txt(pg, "#cs-counts") and "Filings confirmed: 1" in txt(pg, "#cs-counts"), txt(pg, "#cs-counts"))
check("minutes and filings waiting are listed", "MINUTES TO APPROVE" in txt(pg, "#cs-attention").upper() and "FILINGS TO CONFIRM" in txt(pg, "#cs-attention").upper(), txt(pg, "#cs-attention"))
pg.fill("#cs-policy-days", "0"); pg.click("#cs-policy-save"); pg.wait_for_timeout(400)
check("zero days is stopped", "1 to 90" in txt(pg, "#policy-problem"), txt(pg, "#policy-problem"))
pg.fill("#cs-policy-days", "30"); pg.click("#cs-policy-save"); pg.wait_for_timeout(1500)
check("the setting is saved", "30 days" in txt(pg, "#cs-policy-meaning"), txt(pg, "#cs-policy-meaning"))

# ---- isolation and audit ----
check("the other company sees none of it", A("GET", "/meetings", OTHER, org="Other") == [] and A("GET", "/resolutions", OTHER, org="Other") == [] and A("GET", "/filings", OTHER, org="Other") == [])
check("the other company cannot read or act on a record", st(A("GET", f"/meetings/{mid1}", OTHER, org="Other")) == 404 and st(A("POST", f"/filings/{fl1}/confirm", OTHER, {"note": "Confirming from outside the company"}, org="Other")) == 404)
check("the other company's overview is empty", A("GET", "/overview", OTHER, org="Other")["counts"]["filings_open"] == 0)
acts = api("GET", "/_audit", DARA, "Meridian")["actions"]
for a_ in ("SECRETARIAL_MEETING_SCHEDULED", "SECRETARIAL_MINUTES_RECORDED", "SECRETARIAL_MINUTES_APPROVED", "SECRETARIAL_MEETING_CANCELLED", "SECRETARIAL_RESOLUTION_PROPOSED", "SECRETARIAL_RESOLUTION_DECIDED", "SECRETARIAL_FILING_ADDED", "SECRETARIAL_FILING_FILED", "SECRETARIAL_FILING_CONFIRMED", "SECRETARIAL_FILING_WITHDRAWN", "SECRETARIAL_POLICY_SET"):
    check(f"the audit trail has {a_}", a_ in acts, [x for x in acts if "SECRETARIAL" in x])
check("no typed content is copied into the audit trail", "bank mandate" not in str(api("GET", "/_audit", DARA, "Meridian")) and "REG-2026" not in str(api("GET", "/_audit", DARA, "Meridian")))
check("no page errors in the browser", not errs, errs[:3])
finish(p, b)
