"""Browser journey: Impact measurement (Stage 35). Run via e2e/run_all.py. The browser user and the user making API calls are always different people."""
from datetime import datetime, timedelta, timezone

from common import *

TODAY = datetime.now(timezone.utc).date()
D = lambda n: (TODAY + timedelta(days=n)).isoformat()
def hrefs(pg): return [a.get_attribute("href") for a in pg.locator(".app-sidebar a").all()]
def tab(pg, name):
    pg.wait_for_selector(f"#imp-tab-{name}"); pg.click(f"#imp-tab-{name}"); pg.wait_for_timeout(1200)
def body(pg): return pg.inner_text("body")
def err(pg): return txt(pg, ".alert-error")
def A(m, path, who, bodyj=None, org="Meridian"): return api(m, "/impact" + path, who, org, bodyj)
def st(r): return r.get("status") if isinstance(r, dict) else None
def iid(ref, who): return next(i["id"] for i in A("GET", "/indicators", who) if i["ref"] == ref)
def fill(pg, **ids):
    for k, v in ids.items(): pg.fill("#" + k.replace("_", "-"), v)
def opn(pg, ref):
    pg.wait_for_selector(f"#imp-in-open-{ref}", timeout=8000)
    if pg.locator("#imp-indicator-detail").count() and ref in txt(pg, "#imp-indicator-detail h3"): return
    pg.click(f"#imp-in-open-{ref}"); pg.wait_for_timeout(900)
def mk(who, **kw):
    d = dict(title="Second indicator", programme_ref="WASH-2", unit="percent", direction="INCREASE", baseline="200", target="1000", baseline_date=D(-100), target_date=D(265)); d.update(kw); return A("POST", "/indicators", who, d)
def rdg(who, i, **kw):
    d = dict(period_end=D(-5), value="250", source_note="Counted from the field register"); d.update(kw); return A("POST", f"/indicators/{i}/readings", who, d)

start_web()
p, b, pg, errs = session()

# ---- an accountant has no business here ----
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/impact")
check("the menu does not offer the workspace to an accountant", "#/impact" not in hrefs(pg), hrefs(pg))
check("typing the address shows no content", "Propose an indicator" not in body(pg), body(pg)[:200])
check("the server refuses an accountant (overview)", st(A("GET", "/overview", AISHA)) == 403)
check("the server refuses an accountant (indicators)", st(A("GET", "/indicators", AISHA)) == 403)

# ---- Tunde proposes an indicator ----
sign_in(pg, *TUNDE, "Meridian"); goto(pg, "/impact")
check("the menu offers the workspace", "#/impact" in hrefs(pg), hrefs(pg))
check("the banner says it collects and verifies no data", "collects no data" in txt(pg, "#imp-banner") and "verifies no result" in txt(pg, "#imp-banner"), txt(pg, "#imp-banner"))
check("nothing needs attention yet", "Nothing needs attention" in txt(pg, "#imp-attention"), txt(pg, "#imp-attention"))
tab(pg, "indicators")
pg.click("#imp-in-save"); pg.wait_for_timeout(300)
check("an empty form is stopped with a plain sentence", "title" in txt(pg, "#indicator-problem").lower(), txt(pg, "#indicator-problem"))
fill(pg, imp_in_title="Households with clean water", imp_in_prog="WASH-1", imp_in_unit="households", imp_in_base="200", imp_in_target="1,000", imp_in_bdate=D(-100), imp_in_tdate=D(-150)); pg.click("#imp-in-save"); pg.wait_for_timeout(300)
check("a target date before the baseline date is stopped", "after the baseline" in txt(pg, "#indicator-problem"), txt(pg, "#indicator-problem"))
fill(pg, imp_in_tdate=D(265)); pg.select_option("#imp-in-dir", "DECREASE"); pg.click("#imp-in-save"); pg.wait_for_timeout(300)
check("a decrease with a higher target is stopped", "lower than the baseline" in txt(pg, "#indicator-problem"), txt(pg, "#indicator-problem"))
pg.select_option("#imp-in-dir", "INCREASE"); pg.click("#imp-in-save"); pg.wait_for_timeout(1500)
check("the indicator is numbered and waits", "IM-001" in txt(pg, "[data-indicator='IM-001']") and "Waiting for a decision" in txt(pg, "[data-indicator='IM-001']") and "from 200.00 to 1000.00" in txt(pg, "[data-indicator='IM-001']"), txt(pg, "#imp-notice") + err(pg))
opn(pg, "IM-001"); i1 = iid("IM-001", DARA)
check("readings are not offered before approval", pg.locator("#imp-rd-save").count() == 0 and st(rdg(DARA, i1)) == 409)
check("the proposer sees no approve button", pg.locator("#imp-in-approve").count() == 0)
check("the proposer cannot approve through the server", st(A("POST", f"/indicators/{i1}/approve", TUNDE, {})) == 403)

# ---- the owner proposes more; the approver decides some (browser user is Tunde) ----
i2 = mk(DARA, title="Children under weight", unit="percent", direction="DECREASE", baseline="40", target="10")["id"]; i3 = mk(DARA, title="Duplicate indicator")["id"]; i4 = mk(DARA, title="Clinic visits", unit="visits")["id"]
check("the owner cannot approve their own indicator", st(A("POST", f"/indicators/{i2}/approve", DARA, {})) == 403 and st(A("POST", f"/indicators/{i2}/reject", DARA, {"reason": "Rejecting my own indicator"})) == 403)
check("a float baseline is refused", st(mk(DARA, baseline=5.5)) == 400)
check("an indicator with the same dates is refused", st(mk(DARA, target_date=D(-100))) == 400)
check("the approver approves two and rejects one", st(A("POST", f"/indicators/{i2}/approve", KWAME, {})) == "APPROVED" and st(A("POST", f"/indicators/{i4}/approve", KWAME, {"note": "Baseline matches the survey"})) == "APPROVED" and st(A("POST", f"/indicators/{i3}/reject", KWAME, {"reason": "Duplicate of another indicator"})) == "REJECTED")
check("a rejected indicator takes no readings", st(rdg(DARA, i3)) == 409)
check("a reading for the future is refused", st(rdg(DARA, i2, period_end=D(30))) == 400)
check("a reading before the baseline date is refused", st(rdg(DARA, i2, period_end=D(-200))) == 400)
check("a negative value is refused", st(rdg(DARA, i2, value="-1")) == 400)
check("a float value is refused", st(rdg(DARA, i2, value=5.5)) == 400)
check("a short source note is refused", st(rdg(DARA, i2, source_note="short")) == 400)
r2 = rdg(DARA, i2, value="25"); check("a reading is numbered and waits", r2["readings"][0]["status"] == "PROPOSED" and r2["pending_readings"] == 1, r2)
check("a second reading for the same period is refused", st(rdg(DARA, i2, value="26")) == 409)
check("the owner cannot confirm their own reading", st(A("POST", f"/indicators/{i2}/readings/1/confirm", DARA, {})) == 403)
check("the approver confirms it", A("POST", f"/indicators/{i2}/readings/1/confirm", KWAME, {})["progress_pct"] == "50.00")
rdg(DARA, i4); A("POST", f"/indicators/{i4}/readings/1/confirm", KWAME, {})

# ---- Kwame approves the first indicator ----
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/impact"); tab(pg, "indicators"); opn(pg, "IM-001")
check("the approver sees the decision buttons but no proposing form", pg.locator("#imp-in-approve").count() == 1 and pg.locator("#imp-in-save").count() == 0)
pg.click("#imp-in-reject"); pg.wait_for_timeout(400)
check("rejecting without a reason is stopped", "10 characters" in err(pg) or "reason" in err(pg).lower(), err(pg))
pg.fill("#imp-in-note", "ok"); pg.click("#imp-in-approve"); pg.wait_for_timeout(400)
check("a short approval note is stopped", "10 characters" in err(pg) or "note" in err(pg).lower(), err(pg))
pg.fill("#imp-in-note", ""); pg.click("#imp-in-approve"); pg.wait_for_timeout(1500)
check("a different person approves it", "Open" in txt(pg, "[data-indicator='IM-001']") and pg.locator("#imp-in-approve").count() == 0, txt(pg, "[data-indicator='IM-001']") + err(pg))
check("with no reading yet, the expected progress is shown", "No confirmed reading yet; expected by today 27.40 percent" in txt(pg, "#imp-progress"), txt(pg, "#imp-progress"))
check("an approved indicator cannot be decided again", st(A("POST", f"/indicators/{i1}/reject", DARA, {"reason": "Trying to reject it later"})) == 409)

# ---- Tunde records a reading ----
sign_in(pg, *TUNDE, "Meridian"); goto(pg, "/impact"); tab(pg, "indicators"); opn(pg, "IM-001")
pg.click("#imp-rd-save"); pg.wait_for_timeout(300)
check("an empty reading is stopped", bool(txt(pg, "#reading-problem")), txt(pg, "#reading-problem"))
fill(pg, imp_rd_date=D(-200), imp_rd_value="380", imp_rd_source="Counted from the field visit register"); pg.click("#imp-rd-save"); pg.wait_for_timeout(300)
check("a period end before the baseline date is stopped", "before the baseline" in txt(pg, "#reading-problem"), txt(pg, "#reading-problem"))
fill(pg, imp_rd_date=D(40)); pg.click("#imp-rd-save"); pg.wait_for_timeout(1200)
check("a future period end is stopped by the server", "future" in err(pg).lower(), err(pg))
fill(pg, imp_rd_date=D(-5), imp_rd_value="abc"); pg.click("#imp-rd-save"); pg.wait_for_timeout(300)
check("a bad value is stopped", "value" in txt(pg, "#reading-problem").lower(), txt(pg, "#reading-problem"))
fill(pg, imp_rd_value="380"); pg.click("#imp-rd-save"); pg.wait_for_timeout(1500)
check("the reading is recorded and waits", "380.00" in txt(pg, "[data-reading='1']") and "Waiting for a decision" in txt(pg, "[data-reading='1']"), txt(pg, "#imp-readings") + err(pg))
fill(pg, imp_rd_value="390"); pg.click("#imp-rd-save"); pg.wait_for_timeout(1200)
check("a second reading for the same period is refused", bool(err(pg)), err(pg))
check("an administrator sees no confirm button and no close button", pg.locator("#imp-rd-1-confirm").count() == 0 and pg.locator("#imp-cl-save").count() == 0)

# ---- Kwame decides ----
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/impact"); tab(pg, "indicators"); opn(pg, "IM-001")
check("closing is not offered while a reading waits", pg.locator("#imp-cl-save").count() == 0 and st(A("POST", f"/indicators/{i1}/close", DARA, {"reason": "Closing while a reading waits"})) == 409)
pg.click("#imp-rd-1-reject"); pg.wait_for_timeout(400)
check("rejecting a reading without a reason is stopped", "10 characters" in err(pg) or "reason" in err(pg).lower(), err(pg))
pg.fill("#imp-rd-1-note", "short"); pg.click("#imp-rd-1-confirm"); pg.wait_for_timeout(400)
check("a short confirmation note is stopped", "10 characters" in err(pg) or "note" in err(pg).lower(), err(pg))
pg.fill("#imp-rd-1-note", ""); pg.click("#imp-rd-1-confirm"); pg.wait_for_timeout(1500)
check("a different person confirms the reading", "Confirmed" in txt(pg, "[data-reading='1']") and pg.locator("#imp-rd-1-confirm").count() == 0, txt(pg, "#imp-readings") + err(pg))
check("progress is worked out exactly", "progress 22.50 percent" in txt(pg, "#imp-progress") and "expected by today 27.40 percent" in txt(pg, "#imp-progress") and "On track" in txt(pg, "#imp-progress"), txt(pg, "#imp-progress"))
check("a decided reading cannot be decided again", st(A("POST", f"/indicators/{i1}/readings/1/reject", DARA, {"reason": "Trying to reject it later"})) == 409)
opn(pg, "IM-002")
check("a decrease indicator is worked out exactly", "progress 50.00 percent" in txt(pg, "#imp-progress"), txt(pg, "#imp-progress"))
pg.fill("#imp-cl-note", "short"); pg.click("#imp-cl-save"); pg.wait_for_timeout(400)
check("closing without a proper reason is stopped", "10 characters" in err(pg) or "reason" in err(pg).lower(), err(pg))
pg.fill("#imp-cl-note", "The programme has finished"); pg.click("#imp-cl-save"); pg.wait_for_timeout(1500)
check("the indicator is closed with its reason", "Closed" in txt(pg, "[data-indicator='IM-002']") and "The programme has finished" in txt(pg, "#imp-closed"), txt(pg, "[data-indicator='IM-002']") + err(pg))
check("a closed indicator takes no more readings", st(rdg(DARA, i2, period_end=D(-6))) == 409)

# ---- overview (browser user is the owner) ----
mk(TUNDE, title="Waiting indicator", unit="visits")
sign_in(pg, *DARA, "Meridian"); goto(pg, "/impact"); tab(pg, "overview")
check("progress groups add up", all(s in txt(pg, "#imp-states") for s in ("On track: 1", "Behind: 1", "Target reached: 0", "No reading yet: 0")), txt(pg, "#imp-states"))
check("the counts add up", all(s in txt(pg, "#imp-counts") for s in ("Waiting for a decision: 1", "Open: 2", "Rejected: 1", "Closed: 1")), txt(pg, "#imp-counts"))
at = txt(pg, "#imp-attention").upper()
check("items to approve and a behind indicator need attention", "INDICATORS TO APPROVE" in at and "BEHIND TARGET" in at, at)
pg.fill("#imp-set-tol", "abc"); pg.click("#imp-set-save"); pg.wait_for_timeout(400)
check("a bad tolerance is stopped", "0 to 100" in txt(pg, "#setting-problem"), txt(pg, "#setting-problem"))
pg.fill("#imp-set-tol", "0"); pg.click("#imp-set-save"); pg.wait_for_timeout(1500)
check("the settings are saved", "0 percentage point" in txt(pg, "#imp-setting-meaning"), txt(pg, "#imp-setting-meaning"))
check("a tolerance of zero makes the first indicator behind too", "Behind: 2" in txt(pg, "#imp-states") and "On track: 0" in txt(pg, "#imp-states"), txt(pg, "#imp-states"))
check("an administrator cannot change the settings", st(A("PUT", "/setting", TUNDE, {"tolerance_points": 3, "stale_days": 30})) == 403)

# ---- isolation and audit ----
check("the other company sees none of it", A("GET", "/indicators", OTHER, org="Other") == [])
check("the other company cannot read or act on an indicator", st(A("GET", f"/indicators/{i1}", OTHER, org="Other")) == 404 and st(A("POST", f"/indicators/{i4}/approve", OTHER, {}, org="Other")) == 404)
check("the other company's overview is empty", A("GET", "/overview", OTHER, org="Other")["counts"]["approved"] == 0)
acts = api("GET", "/_audit", KWAME, "Meridian")["actions"]
for a_ in ("IMPACT_INDICATOR_PROPOSED", "IMPACT_INDICATOR_APPROVED", "IMPACT_INDICATOR_REJECTED", "IMPACT_INDICATOR_CLOSED", "IMPACT_READING_RECORDED", "IMPACT_READING_CONFIRMED", "IMPACT_SETTING_SET"):
    check(f"the audit trail has {a_}", a_ in acts, [x for x in acts if "IMPACT" in x])
aud = str(api("GET", "/_audit", KWAME, "Meridian"))
check("no typed content is copied into the audit trail", all(s not in aud for s in ("Households with clean", "WASH-", "Children under", "Clinic visits", "Counted from", "Duplicate of", "programme has finished", "Baseline matches")))
check("no page errors in the browser", not errs, errs[:3])
finish(p, b)
