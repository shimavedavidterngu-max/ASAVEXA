"""Browser journey: Franchise and multi-location (Stage 38). Run via e2e/run_all.py. The browser user and the user making API calls are always different people."""
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
    pg.wait_for_selector(f"#fch-tab-{name}"); pg.click(f"#fch-tab-{name}"); pg.wait_for_timeout(1200)
def body(pg): return pg.inner_text("body")
def err(pg): return txt(pg, ".alert-error")
def A(m, path, who, bodyj=None, org="Meridian"): return api(m, "/franchise" + path, who, org, bodyj)
def st(r): return r.get("status") if isinstance(r, dict) else None
def lid(ref, who): return next(i["id"] for i in A("GET", "/locations", who) if i["ref"] == ref)
def fill(pg, **ids):
    for k, v in ids.items(): pg.fill("#" + k.replace("_", "-"), v)
def opn(pg, ref):
    pg.wait_for_selector(f"#fch-lc-open-{ref}", timeout=8000)
    if pg.locator("#fch-location-detail").count() and ref in txt(pg, "#fch-location-detail h3"): return
    pg.click(f"#fch-lc-open-{ref}"); pg.wait_for_timeout(900)
def mk(who, **kw):
    d = dict(name="Second outlet", location_ref="OUT-2", currency="USD", royalty_rate_pct="10", due_day=5, start_period=back(3), description="A second outlet for the journey"); d.update(kw); return A("POST", "/locations", who, d)
def rep(who, s, **kw):
    d = dict(period=back(3), gross_sales="200.50", submitted_on=str(due(back(3), 5))); d.update(kw); return A("POST", f"/locations/{s}/reports", who, d)
def pay(who, s, **kw):
    d = dict(amount="50", paid_on=D(-2), note="Bank transfer"); d.update(kw); return A("POST", f"/locations/{s}/payments", who, d)

start_web()
p, b, pg, errs = session()

# ---- an accountant has no business here ----
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/franchise")
check("the menu does not offer the workspace to an accountant", "#/franchise" not in hrefs(pg), hrefs(pg))
check("typing the address shows no content", "Propose a location" not in body(pg), body(pg)[:200])
check("the server refuses an accountant (overview)", st(A("GET", "/overview", AISHA)) == 403)
check("the server refuses an accountant (locations)", st(A("GET", "/locations", AISHA)) == 403)

# ---- Tunde proposes a location ----
sign_in(pg, *TUNDE, "Meridian"); goto(pg, "/franchise")
check("the menu offers the workspace", "#/franchise" in hrefs(pg), hrefs(pg))
check("the banner says it collects no money and applies no law", "collects no money" in txt(pg, "#fch-banner") and "applies no franchise law" in txt(pg, "#fch-banner"), txt(pg, "#fch-banner"))
check("nothing needs attention yet", "Nothing needs attention" in txt(pg, "#fch-attention"), txt(pg, "#fch-attention"))
tab(pg, "locations")
pg.click("#fch-lc-save"); pg.wait_for_timeout(300)
check("an empty form is stopped with a plain sentence", "name" in txt(pg, "#location-problem").lower(), txt(pg, "#location-problem"))
fill(pg, fch_lc_name="Lekki outlet", fch_lc_ref="OUT-1", fch_lc_cur="ngn", fch_lc_rate="100.5", fch_lc_start=back(3), fch_lc_day="5", fch_lc_desc="The outlet run by the franchisee"); pg.click("#fch-lc-save"); pg.wait_for_timeout(300)
check("a rate above 100 percent is stopped", "100 percent" in txt(pg, "#location-problem"), txt(pg, "#location-problem"))
fill(pg, fch_lc_rate="5.123"); pg.click("#fch-lc-save"); pg.wait_for_timeout(300)
check("three decimals in the rate are stopped", "rate" in txt(pg, "#location-problem").lower(), txt(pg, "#location-problem"))
fill(pg, fch_lc_rate="5", fch_lc_day="29"); pg.click("#fch-lc-save"); pg.wait_for_timeout(300)
check("a due day of 29 is stopped", "due day" in txt(pg, "#location-problem").lower(), txt(pg, "#location-problem"))
fill(pg, fch_lc_day="5"); pg.click("#fch-lc-save"); pg.wait_for_timeout(1500)
check("the location is numbered and waits", "FL-001" in txt(pg, "[data-location='FL-001']") and "Waiting for a decision" in txt(pg, "[data-location='FL-001']") and "royalty rate 5.00 percent" in txt(pg, "[data-location='FL-001']"), txt(pg, "#fch-notice") + err(pg))
opn(pg, "FL-001"); s1 = lid("FL-001", DARA)
check("records are not offered before approval", pg.locator("#fch-rp-save").count() == 0 and st(rep(DARA, s1)) == 409)
check("the proposer sees no approve button", pg.locator("#fch-lc-approve").count() == 0)
check("the proposer cannot approve through the server", st(A("POST", f"/locations/{s1}/approve", TUNDE, {})) == 403)

# ---- the owner proposes more; the approver decides some (browser user is Tunde) ----
s2 = mk(DARA)["id"]; s3 = mk(DARA, name="Duplicate outlet", location_ref="OUT-3")["id"]
check("the owner cannot approve or reject their own location", st(A("POST", f"/locations/{s2}/approve", DARA, {})) == 403 and st(A("POST", f"/locations/{s2}/reject", DARA, {"reason": "Rejecting my own location"})) == 403)
check("a zero rate is refused", st(mk(DARA, royalty_rate_pct="0")) == 400)
check("a float rate is refused", st(mk(DARA, royalty_rate_pct=5.5)) == 400)
check("a rate above 100 is refused", st(mk(DARA, royalty_rate_pct="100.01")) == 400)
check("a bad currency is refused", st(mk(DARA, currency="NG")) == 400)
check("the approver approves one and rejects one", st(A("POST", f"/locations/{s2}/approve", KWAME, {"note": "Agreement checked"})) == "APPROVED" and st(A("POST", f"/locations/{s3}/reject", KWAME, {"reason": "Duplicate of another location"})) == "REJECTED")
check("a rejected location takes no records", st(rep(DARA, s3)) == 409 and st(pay(DARA, s3)) == 409)
check("a month in the future is refused", st(rep(DARA, s2, period=back(-1))) == 400)
check("a month before the first reporting month is refused", st(rep(DARA, s2, period=back(6))) == 400)
check("a float sales figure is refused", st(rep(DARA, s2, gross_sales=5.5)) == 400)
check("a negative sales figure is refused", st(rep(DARA, s2, gross_sales="-1")) == 400)
check("a report date in the future is refused", st(rep(DARA, s2, submitted_on=D(30))) == 400)
check("a zero payment is refused", st(pay(DARA, s2, amount="0")) == 400)
check("a payment with three decimals is refused", st(pay(DARA, s2, amount="1.234")) == 400)
r2 = rep(DARA, s2); check("a report is numbered and waits with its exact royalty", r2["reports"][0]["status"] == "PROPOSED" and r2["reports"][0]["royalty"] == "20.05" and r2["royalty_due"] == "0.00", r2)
check("a second report for the month is refused", st(rep(DARA, s2)) == 409)
check("the owner cannot confirm their own report", st(A("POST", f"/locations/{s2}/reports/1/confirm", DARA, {})) == 403)
check("the approver confirms it", A("POST", f"/locations/{s2}/reports/1/confirm", KWAME, {})["royalty_due"] == "20.05")
pay(DARA, s2); check("the owner cannot confirm their own payment", st(A("POST", f"/locations/{s2}/payments/1/confirm", DARA, {})) == 403)
x = A("POST", f"/locations/{s2}/payments/1/confirm", KWAME, {})
check("a payment above the royalty shows as overpaid, exactly", (x["balance"], x["balance_state"], x["overdue_amount"]) == ("-29.95", "OVERPAID", "0.00"), x)

# ---- Kwame approves the first location ----
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/franchise"); tab(pg, "locations"); opn(pg, "FL-001")
check("the approver sees the decision buttons but no proposing form", pg.locator("#fch-lc-approve").count() == 1 and pg.locator("#fch-lc-save").count() == 0)
pg.click("#fch-lc-reject"); pg.wait_for_timeout(400)
check("rejecting without a reason is stopped", "10 characters" in err(pg) or "reason" in err(pg).lower(), err(pg))
pg.fill("#fch-lc-note", "ok"); pg.click("#fch-lc-approve"); pg.wait_for_timeout(400)
check("a short approval note is stopped", "10 characters" in err(pg) or "note" in err(pg).lower(), err(pg))
pg.fill("#fch-lc-note", ""); pg.click("#fch-lc-approve"); pg.wait_for_timeout(1500)
check("a different person approves it", "Open" in txt(pg, "[data-location='FL-001']") and pg.locator("#fch-lc-approve").count() == 0, txt(pg, "[data-location='FL-001']") + err(pg))
exp = [per for per in (back(3), back(2), back(1), back(0)) if due(per, 5) < TODAY]
check("months past due with no report are listed", all(per in txt(pg, "#fch-missing") for per in exp) and len(exp) >= 3, txt(pg, "#fch-missing"))
check("an approved location cannot be decided again", st(A("POST", f"/locations/{s1}/reject", DARA, {"reason": "Trying to reject it later"})) == 409)

# ---- Tunde records on the first location ----
sign_in(pg, *TUNDE, "Meridian"); goto(pg, "/franchise"); tab(pg, "locations"); opn(pg, "FL-001")
pg.click("#fch-rp-save"); pg.wait_for_timeout(300)
check("an empty report is stopped", bool(txt(pg, "#report-problem")), txt(pg, "#report-problem"))
fill(pg, fch_rp_period="2026-13", fch_rp_sales="1,000.50", fch_rp_date=str(due(back(3), 5) + timedelta(days=9))); pg.click("#fch-rp-save"); pg.wait_for_timeout(300)
check("a bad month is stopped", "real month" in txt(pg, "#report-problem"), txt(pg, "#report-problem"))
fill(pg, fch_rp_period=back(3), fch_rp_sales="1.234"); pg.click("#fch-rp-save"); pg.wait_for_timeout(300)
check("a sales figure with three decimals is stopped", "sales" in txt(pg, "#report-problem").lower(), txt(pg, "#report-problem"))
fill(pg, fch_rp_sales="1,000.50"); pg.click("#fch-rp-save"); pg.wait_for_timeout(1500)
check("the report is recorded with the exact royalty, late and waiting", "royalty 50.03" in txt(pg, "[data-row='reports-1']") and "(late)" in txt(pg, "[data-row='reports-1']") and "Waiting for a decision" in txt(pg, "[data-row='reports-1']"), txt(pg, "#fch-reports") + err(pg))
fill(pg, fch_rp_period=back(3), fch_rp_sales="5", fch_rp_date=D(-1)); pg.click("#fch-rp-save"); pg.wait_for_timeout(1200)
check("a second report for the same month is refused", bool(err(pg)), err(pg))
fill(pg, fch_py_amount="0", fch_py_date=D(-2), fch_py_note="Bank transfer"); pg.click("#fch-py-save"); pg.wait_for_timeout(300)
check("a zero payment is stopped", "more than zero" in txt(pg, "#payment-problem"), txt(pg, "#payment-problem"))
fill(pg, fch_py_amount="20"); pg.click("#fch-py-save"); pg.wait_for_timeout(1500)
check("the payment is recorded and waits", "20.00" in txt(pg, "[data-row='payments-1']") and "Waiting for a decision" in txt(pg, "[data-row='payments-1']"), txt(pg, "#fch-payments") + err(pg))
check("an administrator sees no confirm button and no close button", pg.locator("#fch-reports-1-confirm").count() == 0 and pg.locator("#fch-cl-save").count() == 0)

# ---- Kwame decides ----
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/franchise"); tab(pg, "locations"); opn(pg, "FL-001")
check("closing is not offered while items wait", pg.locator("#fch-cl-save").count() == 0 and st(A("POST", f"/locations/{s1}/close", DARA, {"reason": "Closing while items wait"})) == 409)
pg.click("#fch-reports-1-reject"); pg.wait_for_timeout(400)
check("rejecting without a reason is stopped", "10 characters" in err(pg) or "reason" in err(pg).lower(), err(pg))
pg.fill("#fch-reports-1-note", "short"); pg.click("#fch-reports-1-confirm"); pg.wait_for_timeout(400)
check("a short confirmation note is stopped", "10 characters" in err(pg) or "note" in err(pg).lower(), err(pg))
pg.fill("#fch-reports-1-note", ""); pg.click("#fch-reports-1-confirm"); pg.wait_for_timeout(1500)
check("a different person confirms the report", "Confirmed" in txt(pg, "[data-row='reports-1']") and pg.locator("#fch-reports-1-confirm").count() == 0, txt(pg, "#fch-reports") + err(pg))
check("royalty due is exact and the unpaid part is owed and overdue", "royalty due 50.03; paid 0.00; balance 50.03 NGN" in txt(pg, "#fch-totals") and "Overdue amount 50.03" in txt(pg, "#fch-totals") and "Reports submitted late: 1" in txt(pg, "#fch-totals"), txt(pg, "#fch-totals"))
pg.click("#fch-payments-1-confirm"); pg.wait_for_timeout(1500)
check("a confirmed payment reduces the balance exactly", "paid 20.00; balance 30.03 NGN" in txt(pg, "#fch-totals") and "Royalty owed" in txt(pg, "#fch-totals") and "Overdue amount 30.03" in txt(pg, "#fch-totals"), txt(pg, "#fch-totals"))
check("a decided record cannot be decided again", st(A("POST", f"/locations/{s1}/reports/1/reject", DARA, {"reason": "Trying to reject it later"})) == 409)
pg.fill("#fch-cl-note", "short"); pg.click("#fch-cl-save"); pg.wait_for_timeout(400)
check("closing without a proper reason is stopped", "10 characters" in err(pg) or "reason" in err(pg).lower(), err(pg))
pg.fill("#fch-cl-note", "The franchise has ended"); pg.click("#fch-cl-save"); pg.wait_for_timeout(1500)
check("the location is closed with its reason", "Closed" in txt(pg, "[data-location='FL-001']") and "The franchise has ended" in txt(pg, "#fch-closed"), txt(pg, "[data-location='FL-001']") + err(pg))
check("a closed location takes no more records", st(rep(DARA, s1, period=back(2))) == 409 and st(pay(DARA, s1)) == 409)

# ---- overview (browser user is the owner) ----
mk(TUNDE, name="Waiting outlet", location_ref="OUT-4")
sign_in(pg, *DARA, "Meridian"); goto(pg, "/franchise"); tab(pg, "overview")
check("the counts add up", all(s in txt(pg, "#fch-counts") for s in ("Waiting for a decision: 1", "Open: 1", "Rejected: 1", "Closed: 1")), txt(pg, "#fch-counts"))
cur = txt(pg, "#fch-currency")
check("each currency is shown on its own and never added together", "NGN: 1 location(s), sales 1000.50, royalty due 50.03, paid 20.00, balance 30.03" in cur and "USD: 1 location(s), sales 200.50, royalty due 20.05, paid 50.00, balance -29.95" in cur, cur)
at = txt(pg, "#fch-attention").upper()
check("a location to approve, missing reports and an overpayment need attention", "LOCATIONS TO APPROVE" in at and "MISSING REPORTS" in at and "OVERPAID" in at, at)
pg.fill("#fch-set-grace_days", "abc"); pg.click("#fch-set-save"); pg.wait_for_timeout(400)
check("a bad grace period is stopped", "0 to 60" in txt(pg, "#setting-problem"), txt(pg, "#setting-problem"))
pg.fill("#fch-set-grace_days", "30"); pg.click("#fch-set-save"); pg.wait_for_timeout(1500)
check("the setting is saved", "after 30 day(s)" in txt(pg, "#fch-setting-meaning"), txt(pg, "#fch-setting-meaning"))
check("an administrator cannot change the setting", st(A("PUT", "/setting", TUNDE, {"grace_days": 3})) == 403)

# ---- isolation and audit ----
check("the other company sees none of it", A("GET", "/locations", OTHER, org="Other") == [])
check("the other company cannot read or act on a location", st(A("GET", f"/locations/{s2}", OTHER, org="Other")) == 404 and st(A("POST", f"/locations/{s2}/reports/1/confirm", OTHER, {}, org="Other")) == 404)
check("the other company's overview is empty", A("GET", "/overview", OTHER, org="Other")["counts"]["approved"] == 0)
acts = api("GET", "/_audit", KWAME, "Meridian")["actions"]
for a_ in ("FRANCHISE_LOCATION_PROPOSED", "FRANCHISE_LOCATION_APPROVED", "FRANCHISE_LOCATION_REJECTED", "FRANCHISE_LOCATION_CLOSED", "FRANCHISE_REPORT_RECORDED", "FRANCHISE_REPORT_CONFIRMED", "FRANCHISE_PAYMENT_RECORDED", "FRANCHISE_PAYMENT_CONFIRMED", "FRANCHISE_SETTING_SET"):
    check(f"the audit trail has {a_}", a_ in acts, [x for x in acts if "FRANCHISE" in x])
aud = str(api("GET", "/_audit", KWAME, "Meridian"))
check("no typed content is copied into the audit trail", all(s not in aud for s in ("Lekki", "OUT-", "Second outlet", "Bank transfer", "Duplicate of", "franchise has ended", "Agreement checked", "1000.50", "200.50")))
check("no page errors in the browser", not errs, errs[:3])
finish(p, b)
