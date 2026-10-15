"""Browser journey: Valuation (Stage 28). Run via e2e/run_all.py. The browser user and the user making API calls are always different people (one login at a time per person)."""
from datetime import datetime, timedelta, timezone

from common import *

TODAY = datetime.now(timezone.utc).date()
D = lambda n: (TODAY + timedelta(days=n)).isoformat()
def hrefs(pg): return [a.get_attribute("href") for a in pg.locator(".app-sidebar a").all()]
def tab(pg, name):
    pg.click(f"#vl-tab-{name}"); pg.wait_for_timeout(900)
def body(pg): return pg.inner_text("body")
def err(pg): return txt(pg, ".alert-error")
def A(m, path, who, bodyj=None, org="Meridian"): return api(m, "/valuation" + path, who, org, bodyj)
def st(r): return r.get("status") if isinstance(r, dict) else None
def details(pg, ref):
    tab(pg, "cases")
    if ref in txt(pg, "#vl-case-detail"): return      # already open (the page keeps its state while the same person stays signed in)
    pg.click(f"#vl-cs-open-{ref}"); pg.wait_for_timeout(1000)
def cid(ref, who): return next(i["id"] for i in A("GET", "/cases", who) if i["ref"] == ref)
def fill(pg, **ids):
    for k, v in ids.items(): pg.fill("#" + k.replace("_", "-"), v)
def case(who, **kw):
    d = dict(subject="Beta Foods Ltd", subject_kind="BUSINESS", purpose="REPORTING", basis="FAIR_VALUE", valuation_date=D(-1), currency="NGN"); d.update(kw); return A("POST", "/cases", who, d)
def meth(who, c, **kw):
    d = dict(kind="ASSET_BASED", label="Net assets", weight=100, total_assets="5000", total_liabilities="1500"); d.update(kw); return A("POST", f"/cases/{c}/methods", who, d)

start_web()
p, b, pg, errs = session()

# ---- an accountant has no business here ----
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/valuation")
check("the menu does not offer the workspace to an accountant", "#/valuation" not in hrefs(pg), hrefs(pg))
check("typing the address shows no content", "Start a valuation" not in body(pg), body(pg)[:200])
check("the server refuses an accountant (overview)", st(A("GET", "/overview", AISHA)) == 403)
check("the server refuses an accountant (cases)", st(A("GET", "/cases", AISHA)) == 403)

# ---- Tunde starts a valuation and adds methods ----
sign_in(pg, *TUNDE, "Meridian"); goto(pg, "/valuation")
check("the menu offers the workspace", "#/valuation" in hrefs(pg), hrefs(pg))
check("the banner says it reads no market data and is not a valuation report", "reads no market data" in txt(pg, "#vl-banner") and "not a valuation report" in txt(pg, "#vl-banner") and "gives no opinion of value" in txt(pg, "#vl-banner"), txt(pg, "#vl-banner"))
check("nothing needs attention yet", "Nothing needs attention" in txt(pg, "#vl-attention"), txt(pg, "#vl-attention"))
tab(pg, "cases")
pg.click("#vl-cs-save"); pg.wait_for_timeout(300)
check("an empty form is stopped with a plain sentence", "subject" in txt(pg, "#case-problem").lower(), txt(pg, "#case-problem"))
fill(pg, vl_cs_subject="Acme Ltd", vl_cs_date=D(-1), vl_cs_cur="naira"); pg.click("#vl-cs-save"); pg.wait_for_timeout(300)
check("a bad currency is stopped", "three-letter" in txt(pg, "#case-problem"), txt(pg, "#case-problem"))
fill(pg, vl_cs_date=D(5), vl_cs_cur="ngn"); pg.click("#vl-cs-save"); pg.wait_for_timeout(1200)
check("a future valuation date is refused", "future" in (err(pg) + txt(pg, "#case-problem")).lower(), err(pg) + txt(pg, "#case-problem"))
fill(pg, vl_cs_date=D(-1)); pg.click("#vl-cs-save"); pg.wait_for_timeout(1500)
check("the valuation is started", "VL-001" in txt(pg, "[data-case='VL-001']") and "Acme Ltd" in txt(pg, "[data-case='VL-001']"), txt(pg, "#vl-notice") + err(pg))
details(pg, "VL-001")
check("with no methods, submit is not offered", pg.locator("#vl-sb-save").count() == 0 and "No methods yet" in txt(pg, "#vl-methods"), txt(pg, "#vl-methods"))
fill(pg, vl_mt_label="Peer multiple", vl_mt_weight="60", vl_mt_metric="1000", vl_mt_multiple="6.5", vl_mt_debt="500")
fill(pg, vl_mt_weight="101"); pg.click("#vl-mt-save"); pg.wait_for_timeout(300)
check("a weight over 100 is stopped", "0 to 100" in txt(pg, "#method-problem"), txt(pg, "#method-problem"))
fill(pg, vl_mt_weight="60", vl_mt_multiple="6.12345"); pg.click("#vl-mt-save"); pg.wait_for_timeout(300)
check("a five-decimal multiple is stopped", "four decimals" in txt(pg, "#method-problem"), txt(pg, "#method-problem"))
fill(pg, vl_mt_multiple="6.5"); pg.click("#vl-mt-save"); pg.wait_for_timeout(1500)
check("the multiple method is worked out exactly", "Result NGN 6000.00, weight 60 percent" in txt(pg, "[data-method='1']"), txt(pg, "#vl-methods") + err(pg))
check("the weights are not yet 100", "add up to 60 percent" in txt(pg, "#vl-weights") and pg.locator("#vl-sb-save").is_disabled(), txt(pg, "#vl-weights"))
pg.select_option("#vl-mt-kind", "DCF"); pg.wait_for_timeout(500)
fill(pg, vl_mt_label="Cash flow forecast", vl_mt_weight="40", vl_mt_flows="100 110\n121", vl_mt_rate="10"); pg.click("#vl-mt-save"); pg.wait_for_timeout(1500)
check("the discounted cash flow is worked out exactly", "Result NGN 272.73, weight 40 percent" in txt(pg, "[data-method='2']"), txt(pg, "#vl-methods") + err(pg))
check("the weights now add up to 100", "add up to 100 percent" in txt(pg, "#vl-weights") and not pg.locator("#vl-sb-save").is_disabled(), txt(pg, "#vl-weights"))
pg.click("#vl-mt-2-sens"); pg.wait_for_timeout(1200)
check("the sensitivity shows one point either side", "10.00 percent: NGN 272.73" in txt(pg, "#vl-sens-2") and "9.00 percent: NGN 277.76" in txt(pg, "#vl-sens-2") and "11.00 percent: NGN 267.84" in txt(pg, "#vl-sens-2"), txt(pg, "#vl-sens-2"))
c1 = cid("VL-001", DARA)
check("a float weight is refused", st(meth(DARA, c1, weight=10.5)) == 400)
check("a float amount is refused", st(meth(DARA, c1, weight=10, total_assets=5000.5)) == 400)
check("a negative cash flow is refused", st(meth(DARA, c1, kind="DCF", label="Bad", weight=0, cash_flows=["-1", "5"], discount_rate="10")) == 400)
check("a terminal growth at or above the rate is refused", st(meth(DARA, c1, kind="DCF", label="Bad", weight=0, cash_flows=["5"], discount_rate="10", terminal_growth="10")) == 400)
check("a method that comes to nothing is refused", st(meth(DARA, c1, weight=0, total_assets="100", total_liabilities="200")) == 400)
over = meth(DARA, c1, label="Extra", weight=10)
check("a third method is added by the owner and worked out", over.get("methods", [{}])[-1].get("result") == "3500.00", over)
goto(pg, "/valuation"); details(pg, "VL-001")
check("the weights are now 110", "add up to 110 percent" in txt(pg, "#vl-weights") and pg.locator("#vl-sb-save").is_disabled(), txt(pg, "#vl-weights"))
check("the server refuses to submit with 110", st(A("POST", f"/cases/{c1}/submit", DARA, {"rationale": "Weights reflect comparability."})) == 409)
pg.fill("#vl-mt-3-note", "no"); pg.click("#vl-mt-3-remove"); pg.wait_for_timeout(500)
check("removing without a proper reason is stopped", "5 characters" in err(pg) or "reason" in err(pg).lower(), err(pg))
pg.fill("#vl-mt-3-note", "Not comparable enough"); pg.click("#vl-mt-3-remove"); pg.wait_for_timeout(1500)
check("the method is removed and the reason kept", "Removed" in txt(pg, "[data-method='3']") and "Not comparable enough" in txt(pg, "[data-method='3']") and "add up to 100 percent" in txt(pg, "#vl-weights"), txt(pg, "#vl-methods") + err(pg))
pg.fill("#vl-sb-rationale", "too short"); pg.click("#vl-sb-save"); pg.wait_for_timeout(300)
check("a short rationale is stopped", "20 characters" in txt(pg, "#submit-problem"), txt(pg, "#submit-problem"))
pg.fill("#vl-sb-rationale", "Weights favour the peer multiple because the peers are close matches."); pg.click("#vl-sb-save"); pg.wait_for_timeout(1500)
check("it is submitted with the exact concluded value", "Waiting for review" in txt(pg, "[data-case='VL-001']") and "Concluded value: NGN 3709.09" in txt(pg, "#vl-concluded") and "lowest method 272.73, highest 6000.00" in txt(pg, "[data-case='VL-001']"), txt(pg, "#vl-concluded") + err(pg))
check("a submitted valuation cannot be edited", pg.locator("#vl-mt-save").count() == 0 and st(meth(DARA, c1, weight=0)) == 409)
check("an administrator cannot approve (no approve permission)", st(A("POST", f"/cases/{c1}/approve", TUNDE, {})) == 403)

# ---- Kwame decides ----
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/valuation"); details(pg, "VL-001")
check("the approver sees no entry forms", pg.locator("#vl-mt-save").count() == 0 and pg.locator("#vl-cs-save").count() == 0)
pg.fill("#vl-dec-note", "no"); pg.click("#vl-dec-return"); pg.wait_for_timeout(500)
check("returning with a short reason is stopped", "10 characters" in err(pg) or "reason" in err(pg).lower(), err(pg))
pg.fill("#vl-dec-note", ""); pg.click("#vl-dec-approve"); pg.wait_for_timeout(1500)
check("a different person approves", "Approved" in txt(pg, "[data-case='VL-001']") and "NGN 3709.09" in txt(pg, "#vl-concluded"), txt(pg, "[data-case='VL-001']") + err(pg))
check("an approved valuation is final", st(A("POST", f"/cases/{c1}/return", DARA, {"reason": "Trying to return it later"})) == 409 and st(A("POST", f"/cases/{c1}/withdraw", DARA, {"reason": "Trying to withdraw it later"})) == 409)

# ---- a second valuation: exact figures, return, fix, resubmit ----
c2 = case(DARA, subject="Gamma Estates")["id"]
check("the second valuation is numbered", cid("VL-002", DARA) == c2)
check("a single-year cash flow with growth is exact", meth(DARA, c2, kind="DCF", label="Perpetuity", weight=30, cash_flows=["100"], discount_rate="10", terminal_growth="2")["methods"][-1]["result"] == "1250.00")
check("two flows at ten percent are exact", A("POST", f"/cases/{c2}/methods", DARA, dict(kind="DCF", label="Two years", weight=0, cash_flows=["100", "100"], discount_rate="10")).get("methods", [{}])[-1].get("result") == "173.55")
check("assets less liabilities is exact", meth(DARA, c2, weight=70)["methods"][-1]["result"] == "3500.00")
check("the sensitivity of the two-year method is exact", [r["result"] for r in A("GET", f"/cases/{c2}/methods/2/sensitivity", DARA)["rows"]] == ["175.91", "173.55", "171.25"])
check("a sensitivity of a non-DCF method is refused", st(A("GET", f"/cases/{c2}/methods/3/sensitivity", DARA)) == 409)
A("POST", f"/cases/{c2}/methods/2/remove", DARA, {"reason": "Not needed here"})
r = A("POST", f"/cases/{c2}/submit", DARA, {"rationale": "Property mostly asset based, with some income."})
check("the concluded value is exact (1250.00x30% + 3500.00x70%)", r.get("concluded_value") == "2825.00", r)
check("the owner cannot approve their own submission", st(A("POST", f"/cases/{c2}/approve", DARA, {})) == 403)
check("the owner cannot return their own submission", st(A("POST", f"/cases/{c2}/return", DARA, {"reason": "Returning my own work"})) == 403)
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/valuation"); details(pg, "VL-002")
pg.fill("#vl-dec-note", "Please justify the growth rate"); pg.click("#vl-dec-return"); pg.wait_for_timeout(1500)
check("a different person returns it with a reason", "Returned" in txt(pg, "[data-case='VL-002']") and "Please justify the growth rate" in txt(pg, "#vl-returned"), txt(pg, "[data-case='VL-002']") + err(pg))
check("the returned valuation can be edited again", st(A("POST", f"/cases/{c2}/methods/1/remove", DARA, {"reason": "Growth cannot be justified"})) == "RETURNED")
r = A("POST", f"/cases/{c2}/methods", DARA, dict(kind="ASSET_BASED", label="Top up", weight=30, total_assets="1000", total_liabilities="0")); 
r = A("POST", f"/cases/{c2}/submit", DARA, {"rationale": "Replaced the income method with a second asset view."})
check("it is resubmitted with a new exact value", r.get("status") == "SUBMITTED" and r.get("concluded_value") == "2750.00", r)
c3 = case(DARA, subject="Delta Plant", subject_kind="EQUIPMENT", currency="USD")["id"]
meth(DARA, c3, weight=100, total_assets="800", total_liabilities="100")
sign_in(pg, *TUNDE, "Meridian"); goto(pg, "/valuation"); details(pg, "VL-003")
pg.fill("#vl-wd-note", "short"); pg.click("#vl-wd-save"); pg.wait_for_timeout(500)
check("withdrawing without a proper reason is stopped", "10 characters" in err(pg) or "reason" in err(pg).lower(), err(pg))
pg.fill("#vl-wd-note", "Started for the wrong entity"); pg.click("#vl-wd-save"); pg.wait_for_timeout(1500)
check("the valuation is withdrawn and the reason kept", "Withdrawn" in txt(pg, "[data-case='VL-003']") and "Started for the wrong entity" in txt(pg, "#vl-case-detail"), txt(pg, "#vl-case-detail") + err(pg))
c4 = case(DARA, subject="Epsilon Holdings", currency="USD")["id"]
meth(DARA, c4, weight=100, total_assets="400", total_liabilities="50"); A("POST", f"/cases/{c4}/submit", DARA, {"rationale": "Straight net asset view of the holding company."})

# ---- overview ----
sign_in(pg, *DARA, "Meridian"); goto(pg, "/valuation"); tab(pg, "overview")
check("totals are shown per currency and never added together", "never added together" in txt(pg, "#vl-totals") and pg.locator("[data-currency='NGN']").count() == 1 and pg.locator("[data-currency='USD']").count() == 1, txt(pg, "#vl-totals"))
check("the NGN line counts approved and waiting", "1 approved, 1 waiting for review" in txt(pg, "[data-currency='NGN']"), txt(pg, "[data-currency='NGN']"))
check("waiting valuations need attention", "WAITING" in txt(pg, "#vl-attention").upper() or "REVIEW" in txt(pg, "#vl-attention").upper(), txt(pg, "#vl-attention"))
check("the counts add up", "Approved: 1" in txt(pg, "#vl-counts") and "Waiting for review: 2" in txt(pg, "#vl-counts") and "Withdrawn: 1" in txt(pg, "#vl-counts"), txt(pg, "#vl-counts"))
pg.fill("#vl-policy-days", "10"); pg.click("#vl-policy-save"); pg.wait_for_timeout(400)
check("fewer than 30 days is stopped", "30 to 1095" in txt(pg, "#policy-problem"), txt(pg, "#policy-problem"))
pg.fill("#vl-policy-days", "90"); pg.click("#vl-policy-save"); pg.wait_for_timeout(1500)
check("the setting is saved", "90 days" in txt(pg, "#vl-policy-meaning"), txt(pg, "#vl-policy-meaning"))
check("an administrator cannot change the setting", st(A("PUT", "/policy", TUNDE, {"review_days": 120})) == 403)

# ---- isolation and audit ----
check("the other company sees none of it", A("GET", "/cases", OTHER, org="Other") == [])
check("the other company cannot read or act on a record", st(A("GET", f"/cases/{c1}", OTHER, org="Other")) == 404 and st(A("POST", f"/cases/{c1}/methods", OTHER, dict(kind="ASSET_BASED", label="Net assets", weight=0, total_assets="1", total_liabilities="0"), org="Other")) == 404)
check("the other company's overview is empty", A("GET", "/overview", OTHER, org="Other")["totals"] == [])
acts = api("GET", "/_audit", KWAME, "Meridian")["actions"]
for a_ in ("VALUATION_CASE_CREATED", "VALUATION_METHOD_ADDED", "VALUATION_METHOD_REMOVED", "VALUATION_CASE_SUBMITTED", "VALUATION_CASE_APPROVED", "VALUATION_CASE_RETURNED", "VALUATION_CASE_WITHDRAWN", "VALUATION_POLICY_SET"):
    check(f"the audit trail has {a_}", a_ in acts, [x for x in acts if "VALUATION" in x])
aud = str(api("GET", "/_audit", KWAME, "Meridian"))
check("no typed content is copied into the audit trail", "Acme" not in aud and "Peer multiple" not in aud and "peers are close" not in aud and "growth rate" not in aud and "wrong entity" not in aud)
check("no page errors in the browser", not errs, errs[:3])
finish(p, b)
