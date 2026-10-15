"""Browser journey: Payroll and workforce cost (Stage 31). Run via e2e/run_all.py. The browser user and the user making API calls are always different people."""
from datetime import datetime, timedelta, timezone

from common import *

TODAY = datetime.now(timezone.utc).date()
D = lambda n: (TODAY + timedelta(days=n)).isoformat()
def hrefs(pg): return [a.get_attribute("href") for a in pg.locator(".app-sidebar a").all()]
def tab(pg, name):
    pg.click(f"#pw-tab-{name}"); pg.wait_for_timeout(900)
def body(pg): return pg.inner_text("body")
def err(pg): return txt(pg, ".alert-error")
def A(m, path, who, bodyj=None, org="Meridian"): return api(m, "/payroll" + path, who, org, bodyj)
def st(r): return r.get("status") if isinstance(r, dict) else None
def rid(ref, who): return next(i["id"] for i in A("GET", "/runs", who) if i["ref"] == ref)
def fill(pg, **ids):
    for k, v in ids.items(): pg.fill("#" + k.replace("_", "-"), v)
def opn(pg, ref):
    pg.click(f"#pw-rn-open-{ref}"); pg.wait_for_timeout(900)
def mkrun(who, **kw):
    d = dict(label="November payroll", period_start=D(-60), period_end=D(-31), currency="NGN"); d.update(kw); return A("POST", "/runs", who, d)
def ln(who, r, **kw):
    d = dict(staff_ref="EMP-100", department="Sales", base_pay="1000.00", deductions=[]); d.update(kw); return A("POST", f"/runs/{r}/lines", who, d)

start_web()
p, b, pg, errs = session()

# ---- an accountant has no business here ----
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/payroll")
check("the menu does not offer the workspace to an accountant", "#/payroll" not in hrefs(pg), hrefs(pg))
check("typing the address shows no content", "Start a payroll run" not in body(pg), body(pg)[:200])
check("the server refuses an accountant (overview)", st(A("GET", "/overview", AISHA)) == 403)
check("the server refuses an accountant (runs)", st(A("GET", "/runs", AISHA)) == 403)

# ---- Tunde prepares a run ----
sign_in(pg, *TUNDE, "Meridian"); goto(pg, "/payroll")
check("the menu offers the workspace", "#/payroll" in hrefs(pg), hrefs(pg))
check("the banner says it calculates no tax and pays nobody", "calculates no tax" in txt(pg, "#pw-banner") and "pays nobody" in txt(pg, "#pw-banner"), txt(pg, "#pw-banner"))
check("nothing needs attention yet", "Nothing needs attention" in txt(pg, "#pw-attention"), txt(pg, "#pw-attention"))
tab(pg, "runs")
pg.click("#pw-rn-save"); pg.wait_for_timeout(300)
check("an empty form is stopped with a plain sentence", "label" in txt(pg, "#run-problem").lower(), txt(pg, "#run-problem"))
fill(pg, pw_rn_label="October payroll", pw_rn_start=D(-31), pw_rn_end=D(-60), pw_rn_cur="ngn"); pg.click("#pw-rn-save"); pg.wait_for_timeout(300)
check("a period that ends before it starts is stopped", "cannot end before" in txt(pg, "#run-problem"), txt(pg, "#run-problem"))
fill(pg, pw_rn_start=D(-60), pw_rn_end=D(-31)); pg.click("#pw-rn-save"); pg.wait_for_timeout(1500)
check("the run is numbered", "PR-001" in txt(pg, "[data-run='PR-001']") and "NGN" in txt(pg, "[data-run='PR-001']"), txt(pg, "#pw-notice") + err(pg))
opn(pg, "PR-001")
check("submitting an empty run is not offered", pg.locator("#pw-sb-save").count() == 0)
r1 = rid("PR-001", DARA)
check("the server refuses to submit an empty run", st(A("POST", f"/runs/{r1}/submit", TUNDE, {"note": ""})) == 409)
fill(pg, pw_ln_ref="EMP-001", pw_ln_dept="Finance", pw_ln_base="0"); pg.click("#pw-ln-save"); pg.wait_for_timeout(300)
check("a zero base pay is stopped", "more than zero" in txt(pg, "#line-problem"), txt(pg, "#line-problem"))
fill(pg, pw_ln_base="250,000.00", pw_ln_allow="30000.50", pw_ln_emp="28000.05", pw_ln_deds="Pension: 22400.04\nTax: 99999999.00"); pg.click("#pw-ln-save"); pg.wait_for_timeout(300)
check("deductions above gross pay are stopped", "more than the gross" in txt(pg, "#line-problem"), txt(pg, "#line-problem"))
fill(pg, pw_ln_deds="Pension: 22400.04\nTax: 41000.10"); pg.click("#pw-ln-save"); pg.wait_for_timeout(1500)
check("the line is worked out exactly", all(s in txt(pg, "[data-line='1']") for s in ("gross 280000.50", "deductions 63400.14", "net 216600.36", "cost to the employer 308000.55")), txt(pg, "#pw-notice") + err(pg) + txt(pg, "#pw-lines"))
fill(pg, pw_ln_ref="emp-001", pw_ln_dept="Finance", pw_ln_base="500"); pg.click("#pw-ln-save"); pg.wait_for_timeout(1200)
check("the same staff reference twice is refused", bool(err(pg)), err(pg) + txt(pg, "#line-problem"))
fill(pg, pw_ln_ref="EMP-002", pw_ln_dept="Sales", pw_ln_base="180000", pw_ln_allow="", pw_ln_emp="", pw_ln_deds=""); pg.click("#pw-ln-save"); pg.wait_for_timeout(1500)
check("the second line is added", "EMP-002" in txt(pg, "[data-line='2']"), txt(pg, "#pw-lines") + err(pg))
check("the run totals are exact", all(s in txt(pg, "#pw-run-totals") for s in ("gross 460000.50", "deductions 63400.14", "net 396600.36", "cost to the employer 488000.55")), txt(pg, "#pw-run-totals"))
check("per-department totals are shown", "Finance: 1 line(s), gross 280000.50" in txt(pg, "[data-dept='Finance']") and "Sales: 1 line(s), gross 180000.00" in txt(pg, "[data-dept='Sales']"), txt(pg, "#pw-departments"))
check("a float amount is refused by the server", st(ln(DARA, r1, staff_ref="EMP-009", base_pay=1000.5)) == 400)
check("a negative amount is refused", st(ln(DARA, r1, staff_ref="EMP-009", base_pay="-5")) == 400)
fill(pg, pw_ln_ref="EMP-003", pw_ln_dept="Sales", pw_ln_base="1000"); pg.click("#pw-ln-save"); pg.wait_for_timeout(1500)
pg.fill("#pw-ln-3-note", "no"); pg.click("#pw-ln-3-remove"); pg.wait_for_timeout(400)
check("removing without a reason is stopped", "5 characters" in err(pg) or "reason" in err(pg).lower(), err(pg))
pg.fill("#pw-ln-3-note", "Added to the wrong run"); pg.click("#pw-ln-3-remove"); pg.wait_for_timeout(1500)
check("a removed line keeps its reason and drops out of the totals", "Removed: Added to the wrong run" in txt(pg, "[data-line='3']") and "gross 460000.50" in txt(pg, "#pw-run-totals"), txt(pg, "[data-line='3']") + txt(pg, "#pw-run-totals"))
pg.fill("#pw-sb-note", "short"); pg.click("#pw-sb-save"); pg.wait_for_timeout(300)
check("a short note is stopped", "10 characters" in txt(pg, "#submit-problem"), txt(pg, "#submit-problem"))
pg.fill("#pw-sb-note", ""); pg.click("#pw-sb-save"); pg.wait_for_timeout(1500)
check("the run is submitted and locked", "Waiting for review" in txt(pg, "[data-run='PR-001']") and pg.locator("#pw-ln-save").count() == 0 and pg.locator("#pw-dec-approve").count() == 0, txt(pg, "[data-run='PR-001']") + err(pg))
check("the submitter cannot approve through the server", st(A("POST", f"/runs/{r1}/approve", TUNDE, {"note": ""})) == 403)
check("adding to a submitted run is refused", st(ln(DARA, r1, staff_ref="EMP-010")) == 409)

# ---- the owner cannot approve a run they submitted ----
r2 = mkrun(DARA, label="Own run")
ln(DARA, r2["id"], staff_ref="OWN-1"); A("POST", f"/runs/{r2['id']}/submit", DARA, {"note": ""})
check("the owner cannot approve their own run", st(A("POST", f"/runs/{r2['id']}/approve", DARA, {"note": ""})) == 403)
check("the owner cannot return their own run", st(A("POST", f"/runs/{r2['id']}/return", DARA, {"reason": "Returning my own run"})) == 403)

# ---- Kwame decides ----
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/payroll"); tab(pg, "runs"); opn(pg, "PR-001")
check("the approver sees no editing", pg.locator("#pw-ln-save").count() == 0 and pg.locator("#pw-sb-save").count() == 0)
pg.click("#pw-dec-return"); pg.wait_for_timeout(400)
check("returning without a reason is stopped", "10 characters" in err(pg) or "reason" in err(pg).lower(), err(pg))
pg.fill("#pw-dec-note", "Please check the Finance pension amount"); pg.click("#pw-dec-return"); pg.wait_for_timeout(1500)
check("a different person returns it with a reason", "Returned" in txt(pg, "[data-run='PR-001']"), txt(pg, "[data-run='PR-001']") + err(pg))
check("the reason is kept", "Please check the Finance pension amount" in txt(pg, "#pw-returned"), txt(pg, "#pw-run-detail")[:300])
sign_in(pg, *TUNDE, "Meridian"); goto(pg, "/payroll"); tab(pg, "runs"); opn(pg, "PR-001")
check("a returned run can be edited again", pg.locator("#pw-ln-save").count() == 1 and pg.locator("#pw-sb-save").count() == 1)
pg.click("#pw-sb-save"); pg.wait_for_timeout(1500)
check("and submitted again", "Waiting for review" in txt(pg, "[data-run='PR-001']"), txt(pg, "[data-run='PR-001']") + err(pg))
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/payroll"); tab(pg, "runs"); opn(pg, "PR-001")
pg.click("#pw-dec-approve"); pg.wait_for_timeout(1500)
check("a different person approves", "Approved" in txt(pg, "[data-run='PR-001']"), txt(pg, "[data-run='PR-001']") + err(pg))
check("an approved run cannot be decided again", st(A("POST", f"/runs/{r1}/return", DARA, {"reason": "Trying to return it later"})) == 409)
check("an approved run cannot be changed", st(ln(DARA, r1, staff_ref="EMP-011")) == 409 and st(A("POST", f"/runs/{r1}/withdraw", TUNDE, {"reason": "Trying to withdraw it later"})) == 409)

# ---- overlap flag and review limit ----
r3 = mkrun(DARA, label="Overlapping run", period_start=D(-45), period_end=D(-20))
ln(DARA, r3["id"], staff_ref="emp-001", department="Finance", base_pay="300000.00")
A("POST", f"/runs/{r3['id']}/submit", DARA, {"note": ""})
check("overlapping pay is flagged, not blocked", A("GET", f"/runs/{r3['id']}", DARA)["lines"][0]["overlap"] is True)
A("PUT", "/setting", KWAME, {"review_limit": "290000.00"})

# ---- overview ----
sign_in(pg, *DARA, "Meridian"); goto(pg, "/payroll"); tab(pg, "overview")
check("approved runs are totalled exactly per currency", all(s in txt(pg, "[data-currency='NGN']") for s in ("1 approved run(s)", "gross 460000.50", "net 396600.36", "cost to the employer 488000.55")), txt(pg, "#pw-totals"))
check("waiting runs are counted", "2 run(s) waiting" in txt(pg, "[data-currency='NGN']"), txt(pg, "#pw-totals"))
at = txt(pg, "#pw-attention").upper()
check("review, overlap and limit items need attention", "RUNS TO REVIEW" in at and "OVERLAPPING PAY" in at and "LINES ABOVE LIMIT" in at, at)
pg.fill("#pw-set-limit", "abc"); pg.click("#pw-set-save"); pg.wait_for_timeout(400)
check("a bad limit is stopped", "amount" in txt(pg, "#setting-problem"), txt(pg, "#setting-problem"))
check("an administrator cannot change the setting", st(A("PUT", "/setting", TUNDE, {"review_limit": "1.00"})) == 403)
check("a read-only view shows the limits", "calculates no tax" in txt(pg, "#pw-limits").lower() or "no tax" in txt(pg, "#pw-limits").lower(), txt(pg, "#pw-limits"))

# ---- isolation and audit ----
check("the other company sees none of it", A("GET", "/runs", OTHER, org="Other") == [])
check("the other company cannot read or act on a run", st(A("GET", f"/runs/{r1}", OTHER, org="Other")) == 404 and st(A("POST", f"/runs/{r1}/approve", OTHER, {}, org="Other")) == 404)
check("the other company's overview is empty", A("GET", "/overview", OTHER, org="Other")["totals"] == [])
acts = api("GET", "/_audit", KWAME, "Meridian")["actions"]
for a_ in ("PAYROLL_RUN_CREATED", "PAYROLL_LINE_ADDED", "PAYROLL_LINE_REMOVED", "PAYROLL_RUN_SUBMITTED", "PAYROLL_RUN_RETURNED", "PAYROLL_RUN_APPROVED", "PAYROLL_SETTING_SET"):
    check(f"the audit trail has {a_}", a_ in acts, [x for x in acts if "PAYROLL" in x])
aud = str(api("GET", "/_audit", KWAME, "Meridian"))
check("no typed content is copied into the audit trail", all(s not in aud for s in ("EMP-001", "Pension", "280000", "216600", "wrong run", "Finance pension", "October payroll")))
check("no page errors in the browser", not errs, errs[:3])
finish(p, b)
