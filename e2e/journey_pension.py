"""Browser journey: Pension and fiduciary (Stage 37). Run via e2e/run_all.py. The browser user and the user making API calls are always different people."""
from datetime import date, datetime, timedelta, timezone

from common import *

TODAY = datetime.now(timezone.utc).date()
D = lambda n: (TODAY + timedelta(days=n)).isoformat()
def back(n):
    y, m = TODAY.year, TODAY.month - n
    while m < 1: y, m = y - 1, m + 12
    return f"{y:04d}-{m:02d}"
def due(per, dd):
    y, m = int(per[:4]), int(per[5:7]); y, m = (y + 1, 1) if m == 12 else (y, m + 1); return date(y, m, dd)
def hrefs(pg): return [a.get_attribute("href") for a in pg.locator(".app-sidebar a").all()]
def tab(pg, name):
    pg.wait_for_selector(f"#pen-tab-{name}"); pg.click(f"#pen-tab-{name}"); pg.wait_for_timeout(1200)
def body(pg): return pg.inner_text("body")
def err(pg): return txt(pg, ".alert-error")
def A(m, path, who, bodyj=None, org="Meridian"): return api(m, "/pension" + path, who, org, bodyj)
def st(r): return r.get("status") if isinstance(r, dict) else None
def sid(ref, who): return next(i["id"] for i in A("GET", "/schemes", who) if i["ref"] == ref)
def fill(pg, **ids):
    for k, v in ids.items(): pg.fill("#" + k.replace("_", "-"), v)
def opn(pg, ref):
    pg.wait_for_selector(f"#pen-sc-open-{ref}", timeout=8000)
    if pg.locator("#pen-scheme-detail").count() and ref in txt(pg, "#pen-scheme-detail h3"): return
    pg.click(f"#pen-sc-open-{ref}"); pg.wait_for_timeout(900)
def mk(who, **kw):
    d = dict(name="Second scheme", scheme_ref="TRUST-2", currency="USD", scheme_type="DEFINED_BENEFIT", start_period=back(3), due_day=5, description="A second scheme for the journey"); d.update(kw); return A("POST", "/schemes", who, d)
def con(who, s, **kw):
    d = dict(period=back(2), employer_amount="1000.10", employee_amount="0.20", paid_on=D(-20)); d.update(kw); return A("POST", f"/schemes/{s}/contributions", who, d)
def val(who, s, **kw):
    d = dict(as_of=D(-10), assets="900000", liabilities="1000000", source_note="From the actuary report"); d.update(kw); return A("POST", f"/schemes/{s}/valuations", who, d)

start_web()
p, b, pg, errs = session()

# ---- an accountant has no business here ----
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/pension")
check("the menu does not offer the workspace to an accountant", "#/pension" not in hrefs(pg), hrefs(pg))
check("typing the address shows no content", "Propose a scheme" not in body(pg), body(pg)[:200])
check("the server refuses an accountant (overview)", st(A("GET", "/overview", AISHA)) == 403)
check("the server refuses an accountant (schemes)", st(A("GET", "/schemes", AISHA)) == 403)

# ---- Tunde proposes a scheme ----
sign_in(pg, *TUNDE, "Meridian"); goto(pg, "/pension")
check("the menu offers the workspace", "#/pension" in hrefs(pg), hrefs(pg))
check("the banner says it holds no member data and applies no law", "no member data" in txt(pg, "#pen-banner") and "applies no pension or trust law" in txt(pg, "#pen-banner"), txt(pg, "#pen-banner"))
check("nothing needs attention yet", "Nothing needs attention" in txt(pg, "#pen-attention"), txt(pg, "#pen-attention"))
tab(pg, "schemes")
pg.click("#pen-sc-save"); pg.wait_for_timeout(300)
check("an empty form is stopped with a plain sentence", "name" in txt(pg, "#scheme-problem").lower(), txt(pg, "#scheme-problem"))
fill(pg, pen_sc_name="Staff retirement scheme", pen_sc_ref="TRUST-1", pen_sc_cur="ngn", pen_sc_start="2999-01", pen_sc_day="5", pen_sc_desc="The staff scheme run by the trustees"); pg.click("#pen-sc-save"); pg.wait_for_timeout(300)
check("a first month in the future is stopped", "future" in txt(pg, "#scheme-problem") or "real month" in txt(pg, "#scheme-problem"), txt(pg, "#scheme-problem"))
fill(pg, pen_sc_start=back(3), pen_sc_day="29"); pg.click("#pen-sc-save"); pg.wait_for_timeout(300)
check("a due day of 29 is stopped", "due day" in txt(pg, "#scheme-problem").lower(), txt(pg, "#scheme-problem"))
fill(pg, pen_sc_day="5"); pg.click("#pen-sc-save"); pg.wait_for_timeout(1500)
check("the scheme is numbered and waits", "PS-001" in txt(pg, "[data-scheme='PS-001']") and "Waiting for a decision" in txt(pg, "[data-scheme='PS-001']"), txt(pg, "#pen-notice") + err(pg))
opn(pg, "PS-001"); s1 = sid("PS-001", DARA)
check("records are not offered before approval", pg.locator("#pen-co-save").count() == 0 and st(con(DARA, s1)) == 409)
check("the proposer sees no approve button", pg.locator("#pen-sc-approve").count() == 0)
check("the proposer cannot approve through the server", st(A("POST", f"/schemes/{s1}/approve", TUNDE, {})) == 403)

# ---- the owner proposes more; the approver decides some (browser user is Tunde) ----
s2 = mk(DARA)["id"]; s3 = mk(DARA, name="Duplicate scheme", scheme_ref="TRUST-3")["id"]
check("the owner cannot approve or reject their own scheme", st(A("POST", f"/schemes/{s2}/approve", DARA, {})) == 403 and st(A("POST", f"/schemes/{s2}/reject", DARA, {"reason": "Rejecting my own scheme"})) == 403)
check("a bad currency is refused", st(mk(DARA, currency="NG")) == 400)
check("a bad type is refused", st(mk(DARA, scheme_type="OTHERS")) == 400)
check("a due day of zero is refused", st(mk(DARA, due_day=0)) == 400)
check("the approver approves one and rejects one", st(A("POST", f"/schemes/{s2}/approve", KWAME, {"note": "Trust deed checked"})) == "APPROVED" and st(A("POST", f"/schemes/{s3}/reject", KWAME, {"reason": "Duplicate of another scheme"})) == "REJECTED")
check("a rejected scheme takes no records", st(con(DARA, s3)) == 409)
check("a month in the future is refused", st(con(DARA, s2, period=back(-1))) == 400)
check("a month before the scheme started is refused", st(con(DARA, s2, period=back(6))) == 400)
check("two zero amounts are refused", st(con(DARA, s2, employer_amount="0", employee_amount="0")) == 400)
check("a float amount is refused", st(con(DARA, s2, employer_amount=5.5)) == 400)
check("three decimals are refused", st(con(DARA, s2, employee_amount="1.234")) == 400)
check("a date paid in the future is refused", st(con(DARA, s2, paid_on=D(30))) == 400)
c2 = con(DARA, s2); check("a contribution is numbered and waits", c2["contributions"][0]["status"] == "PROPOSED" and c2["total_contributions"] == "0.00", c2)
check("a second contribution for the month is refused", st(con(DARA, s2)) == 409)
check("the owner cannot confirm their own contribution", st(A("POST", f"/schemes/{s2}/contributions/1/confirm", DARA, {})) == 403)
x = A("POST", f"/schemes/{s2}/contributions/1/confirm", KWAME, {})
check("the approver confirms it and the totals are exact", (x["employer_total"], x["employee_total"], x["total_contributions"]) == ("1000.10", "0.20", "1000.30"), x)
check("a liability of zero is refused", st(val(DARA, s2, liabilities="0")) == 400)
check("a valuation in the future is refused", st(val(DARA, s2, as_of=D(30))) == 400)
val(DARA, s2); x = A("POST", f"/schemes/{s2}/valuations/1/confirm", KWAME, {})
check("a confirmed valuation gives an exact ratio and the deficit", (x["funding_ratio_pct"], x["position"], x["position_amount"], x["below_floor"]) == ("90.00", "DEFICIT", "100000.00", False), x)
A("POST", f"/schemes/{s2}/obligations", DARA, {"title": "File the annual return", "due_date": D(10)})
x = A("POST", f"/schemes/{s2}/obligations/1/complete", DARA, {"completed_on": D(-1), "note": "Filed online with receipt"})
check("the person who marked it done cannot confirm it", x["obligations"][0]["status"] == "DONE" and st(A("POST", f"/schemes/{s2}/obligations/1/confirm", DARA, {})) == 403)
check("a different person confirms it", A("POST", f"/schemes/{s2}/obligations/1/confirm", KWAME, {})["obligations"][0]["status"] == "CONFIRMED")

# ---- Kwame approves the first scheme ----
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/pension"); tab(pg, "schemes"); opn(pg, "PS-001")
check("the approver sees the decision buttons but no proposing form", pg.locator("#pen-sc-approve").count() == 1 and pg.locator("#pen-sc-save").count() == 0)
pg.click("#pen-sc-reject"); pg.wait_for_timeout(400)
check("rejecting without a reason is stopped", "10 characters" in err(pg) or "reason" in err(pg).lower(), err(pg))
pg.fill("#pen-sc-note", "ok"); pg.click("#pen-sc-approve"); pg.wait_for_timeout(400)
check("a short approval note is stopped", "10 characters" in err(pg) or "note" in err(pg).lower(), err(pg))
pg.fill("#pen-sc-note", ""); pg.click("#pen-sc-approve"); pg.wait_for_timeout(1500)
check("a different person approves it", "Open" in txt(pg, "[data-scheme='PS-001']") and pg.locator("#pen-sc-approve").count() == 0, txt(pg, "[data-scheme='PS-001']") + err(pg))
exp = [per for per in (back(3), back(2), back(1), back(0)) if due(per, 5) < TODAY]
check("months past due with nothing recorded are listed", all(per in txt(pg, "#pen-missing") for per in exp) and len(exp) >= 2, txt(pg, "#pen-missing"))
check("an approved scheme cannot be decided again", st(A("POST", f"/schemes/{s1}/reject", DARA, {"reason": "Trying to reject it later"})) == 409)

# ---- Tunde records on the first scheme ----
sign_in(pg, *TUNDE, "Meridian"); goto(pg, "/pension"); tab(pg, "schemes"); opn(pg, "PS-001")
pg.click("#pen-co-save"); pg.wait_for_timeout(300)
check("an empty contribution is stopped", bool(txt(pg, "#contribution-problem")), txt(pg, "#contribution-problem"))
fill(pg, pen_co_period=back(3), pen_co_emp="0", pen_co_ee="0", pen_co_paid=D(-20)); pg.click("#pen-co-save"); pg.wait_for_timeout(300)
check("two zero amounts are stopped", "At least one" in txt(pg, "#contribution-problem"), txt(pg, "#contribution-problem"))
fill(pg, pen_co_period="2026-13", pen_co_emp="1,000.10", pen_co_ee="0.20"); pg.click("#pen-co-save"); pg.wait_for_timeout(300)
check("a bad month is stopped", "real month" in txt(pg, "#contribution-problem"), txt(pg, "#contribution-problem"))
fill(pg, pen_co_period=back(3), pen_co_paid=str(due(back(3), 5) + timedelta(days=9))); pg.click("#pen-co-save"); pg.wait_for_timeout(1500)
check("the contribution is recorded and waits", "1000.10" in txt(pg, "[data-row='contributions-1']") and "Waiting for a decision" in txt(pg, "[data-row='contributions-1']") and "(late)" in txt(pg, "[data-row='contributions-1']"), txt(pg, "#pen-contributions") + err(pg))
fill(pg, pen_co_period=back(3), pen_co_emp="5", pen_co_ee="5", pen_co_paid=D(-20)); pg.click("#pen-co-save"); pg.wait_for_timeout(1200)
check("a second contribution for the same month is refused", bool(err(pg)), err(pg))
fill(pg, pen_va_date=D(-10), pen_va_assets="900,000", pen_va_liab="0", pen_va_source="From the actuary report"); pg.click("#pen-va-save"); pg.wait_for_timeout(300)
check("liabilities of zero are stopped", "more than zero" in txt(pg, "#valuation-problem"), txt(pg, "#valuation-problem"))
fill(pg, pen_va_liab="1000000"); pg.click("#pen-va-save"); pg.wait_for_timeout(1500)
check("the valuation is recorded and waits", "900000.00" in txt(pg, "[data-row='valuations-1']") and "Waiting for a decision" in txt(pg, "[data-row='valuations-1']"), txt(pg, "#pen-valuations") + err(pg))
fill(pg, pen_ob_title="File the annual return", pen_ob_due=D(15)); pg.click("#pen-ob-save"); pg.wait_for_timeout(1500)
check("the obligation is on the calendar and due soon", "File the annual return" in txt(pg, "[data-row='obligations-1']") and "Due soon" in txt(pg, "[data-row='obligations-1']"), txt(pg, "#pen-obligations") + err(pg))
pg.click("#pen-ob-1-done"); pg.wait_for_timeout(300)
check("marking done with nothing typed is stopped", bool(txt(pg, "#complete-1-problem")), txt(pg, "#complete-1-problem"))
fill(pg, pen_ob_1_date=D(-1), pen_ob_1_text="Filed online with receipt"); pg.click("#pen-ob-1-done"); pg.wait_for_timeout(1500)
check("the obligation is done and waits for confirmation", "Done, waiting for confirmation" in txt(pg, "[data-row='obligations-1']"), txt(pg, "#pen-obligations") + err(pg))
fill(pg, pen_cf_ref="TR-03", pen_cf_date=D(-3), pen_cf_nature="short"); pg.click("#pen-cf-save"); pg.wait_for_timeout(300)
check("a short nature is stopped", "nature" in txt(pg, "#conflict-problem").lower(), txt(pg, "#conflict-problem"))
fill(pg, pen_cf_nature="Holds shares in a fund manager"); pg.click("#pen-cf-save"); pg.wait_for_timeout(1500)
check("the declaration is recorded and waits", "TR-03" in txt(pg, "[data-row='conflicts-1']") and "Waiting for a decision" in txt(pg, "[data-row='conflicts-1']"), txt(pg, "#pen-conflicts") + err(pg))
check("an administrator sees no confirm button and no close button", pg.locator("#pen-contributions-1-confirm").count() == 0 and pg.locator("#pen-cl-save").count() == 0)

# ---- Kwame decides ----
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/pension"); tab(pg, "schemes"); opn(pg, "PS-001")
check("closing is not offered while items wait", pg.locator("#pen-cl-save").count() == 0 and st(A("POST", f"/schemes/{s1}/close", DARA, {"reason": "Closing while items wait"})) == 409)
pg.click("#pen-contributions-1-reject"); pg.wait_for_timeout(400)
check("rejecting without a reason is stopped", "10 characters" in err(pg) or "reason" in err(pg).lower(), err(pg))
pg.fill("#pen-contributions-1-note", "short"); pg.click("#pen-contributions-1-confirm"); pg.wait_for_timeout(400)
check("a short confirmation note is stopped", "10 characters" in err(pg) or "note" in err(pg).lower(), err(pg))
pg.fill("#pen-contributions-1-note", ""); pg.click("#pen-contributions-1-confirm"); pg.wait_for_timeout(1500)
check("a different person confirms the contribution", "Confirmed" in txt(pg, "[data-row='contributions-1']") and pg.locator("#pen-contributions-1-confirm").count() == 0, txt(pg, "#pen-contributions") + err(pg))
check("the totals are exact and the late payment is counted", "employer 1000.10, employee 0.20, total 1000.30 NGN" in txt(pg, "#pen-totals") and "Paid late: 1" in txt(pg, "#pen-totals"), txt(pg, "#pen-totals"))
pg.click("#pen-valuations-1-confirm"); pg.wait_for_timeout(1500)
check("the funding position is worked out exactly", "90.00 percent" in txt(pg, "#pen-funding") and "Deficit" in txt(pg, "#pen-funding") and "100000.00 NGN" in txt(pg, "#pen-funding"), txt(pg, "#pen-funding"))
pg.fill("#pen-obligations-1-note", "Receipt number checked"); pg.click("#pen-obligations-1-reject"); pg.wait_for_timeout(1500)
check("sending an obligation back opens it again with the reason kept", "Open" in txt(pg, "[data-row='obligations-1']") and "Receipt number checked" in txt(pg, "[data-row='obligations-1']"), txt(pg, "#pen-obligations") + err(pg))
pg.click("#pen-conflicts-1-confirm"); pg.wait_for_timeout(1500)
check("a different person confirms the declaration", "Confirmed" in txt(pg, "[data-row='conflicts-1']"), txt(pg, "#pen-conflicts") + err(pg))
check("a decided record cannot be decided again", st(A("POST", f"/schemes/{s1}/contributions/1/reject", DARA, {"reason": "Trying to reject it later"})) == 409)
x = A("POST", f"/schemes/{s1}/obligations/1/complete", DARA, {"completed_on": D(-1), "note": "Filed online with receipt"}); A("POST", f"/schemes/{s1}/obligations/1/confirm", KWAME, {})
pg.reload(); pg.wait_for_timeout(1500); tab(pg, "schemes"); opn(pg, "PS-001")
pg.fill("#pen-cl-note", "short"); pg.click("#pen-cl-save"); pg.wait_for_timeout(400)
check("closing without a proper reason is stopped", "10 characters" in err(pg) or "reason" in err(pg).lower(), err(pg))
pg.fill("#pen-cl-note", "The scheme has wound up"); pg.click("#pen-cl-save"); pg.wait_for_timeout(1500)
check("the scheme is closed with its reason", "Closed" in txt(pg, "[data-scheme='PS-001']") and "The scheme has wound up" in txt(pg, "#pen-closed"), txt(pg, "[data-scheme='PS-001']") + err(pg))
check("a closed scheme takes no more records", st(con(DARA, s1, period=back(1))) == 409)

# ---- overview (browser user is the owner) ----
mk(TUNDE, name="Waiting scheme", scheme_ref="TRUST-4")
sign_in(pg, *DARA, "Meridian"); goto(pg, "/pension"); tab(pg, "overview")
check("the counts add up", all(s in txt(pg, "#pen-counts") for s in ("Waiting for a decision: 1", "Open: 1", "Rejected: 1", "Closed: 1")), txt(pg, "#pen-counts"))
check("contributions are shown per currency and never added together", "USD: 1000.30" in txt(pg, "#pen-currency") and "NGN" not in txt(pg, "#pen-currency"), txt(pg, "#pen-currency"))
at = txt(pg, "#pen-attention").upper()
check("a scheme to approve and missing months need attention", "SCHEMES TO APPROVE" in at and "MISSING CONTRIBUTIONS" in at, at)
pg.fill("#pen-set-floor", "abc"); pg.click("#pen-set-save"); pg.wait_for_timeout(400)
check("a bad floor is stopped", "1 to 300" in txt(pg, "#setting-problem"), txt(pg, "#setting-problem"))
pg.fill("#pen-set-floor", "95"); pg.click("#pen-set-save"); pg.wait_for_timeout(1500)
check("the settings are saved", "below 95%" in txt(pg, "#pen-setting-meaning"), txt(pg, "#pen-setting-meaning"))
check("a higher floor flags the 90 percent scheme", "BELOW FUNDING FLOOR" in txt(pg, "#pen-attention").upper(), txt(pg, "#pen-attention"))
check("an administrator cannot change the settings", st(A("PUT", "/setting", TUNDE, {"funding_floor_pct": 50})) == 403)

# ---- isolation and audit ----
check("the other company sees none of it", A("GET", "/schemes", OTHER, org="Other") == [])
check("the other company cannot read or act on a scheme", st(A("GET", f"/schemes/{s2}", OTHER, org="Other")) == 404 and st(A("POST", f"/schemes/{s2}/contributions/1/confirm", OTHER, {}, org="Other")) == 404)
check("the other company's overview is empty", A("GET", "/overview", OTHER, org="Other")["counts"]["approved"] == 0)
acts = api("GET", "/_audit", KWAME, "Meridian")["actions"]
for a_ in ("PENSION_SCHEME_PROPOSED", "PENSION_SCHEME_APPROVED", "PENSION_SCHEME_REJECTED", "PENSION_SCHEME_CLOSED", "PENSION_CONTRIBUTION_RECORDED", "PENSION_CONTRIBUTION_CONFIRMED", "PENSION_VALUATION_CONFIRMED", "PENSION_OBLIGATION_DONE", "PENSION_OBLIGATION_REJECTED", "PENSION_CONFLICT_CONFIRMED", "PENSION_SETTING_SET"):
    check(f"the audit trail has {a_}", a_ in acts, [x for x in acts if "PENSION" in x])
aud = str(api("GET", "/_audit", KWAME, "Meridian"))
check("no typed content is copied into the audit trail", all(s not in aud for s in ("Staff retirement", "TRUST-", "Second scheme", "actuary", "annual return", "TR-03", "fund manager", "Duplicate of", "wound up", "Trust deed", "Receipt number", "1000.10")))
check("no page errors in the browser", not errs, errs[:3])
finish(p, b)
