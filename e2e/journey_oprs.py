"""Browser journey: Operations research (Stage 34). Run via e2e/run_all.py. The browser user and the user making API calls are always different people."""
from fractions import Fraction

from common import *

def hrefs(pg): return [a.get_attribute("href") for a in pg.locator(".app-sidebar a").all()]
def tab(pg, name):
    pg.wait_for_selector(f"#op-tab-{name}"); pg.click(f"#op-tab-{name}"); pg.wait_for_timeout(1200)
def body(pg): return pg.inner_text("body")
def err(pg): return txt(pg, ".alert-error")
def A(m, path, who, bodyj=None, org="Meridian"): return api(m, "/oprs" + path, who, org, bodyj)
def st(r): return r.get("status") if isinstance(r, dict) else None
def aid(ref, who): return next(i["id"] for i in A("GET", "/analyses", who) if i["ref"] == ref)
def fill(pg, **ids):
    for k, v in ids.items(): pg.fill("#" + k.replace("_", "-"), v)
def opn(pg, ref):
    pg.wait_for_selector(f"#op-an-open-{ref}", timeout=8000)
    if pg.locator("#op-analysis-detail").count() and ref in txt(pg, "#op-analysis-detail h3"): return
    pg.click(f"#op-an-open-{ref}"); pg.wait_for_timeout(900)
def mk(who, **kw):
    d = dict(title="Second analysis", currency="USD", discount_rate="5", purpose="Compare two suppliers for the packaging"); d.update(kw); return A("POST", "/analyses", who, d)
def ad(who, a, **kw):
    d = dict(name="Supplier one", upfront_cost="5000.00", flows=["2000", "2000", "2000"]); d.update(kw); return A("POST", f"/analyses/{a}/options", who, d)
def npv(up, flows, pct):
    r = Fraction(str(pct)) / 100; v = -Fraction(str(up)) + sum(Fraction(str(f)) / (1 + r) ** (i + 1) for i, f in enumerate(flows)); n = v.numerator * 100; q = (abs(n) * 2 + v.denominator) // (2 * v.denominator)
    return f"{(q if n >= 0 else -q) / 100:.2f}"

start_web()
p, b, pg, errs = session()

# ---- an accountant has no business here ----
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/oprs")
check("the menu does not offer the workspace to an accountant", "#/oprs" not in hrefs(pg), hrefs(pg))
check("typing the address shows no content", "Start an analysis" not in body(pg), body(pg)[:200])
check("the server refuses an accountant (overview)", st(A("GET", "/overview", AISHA)) == 403)
check("the server refuses an accountant (analyses)", st(A("GET", "/analyses", AISHA)) == 403)

# ---- Tunde prepares an analysis ----
sign_in(pg, *TUNDE, "Meridian"); goto(pg, "/oprs")
check("the menu offers the workspace", "#/oprs" in hrefs(pg), hrefs(pg))
check("the banner says it recommends nothing", "recommends nothing" in txt(pg, "#op-banner") and "not advice" in txt(pg, "#op-banner"), txt(pg, "#op-banner"))
check("nothing needs attention yet", "Nothing needs attention" in txt(pg, "#op-attention"), txt(pg, "#op-attention"))
tab(pg, "analyses")
pg.click("#op-an-save"); pg.wait_for_timeout(300)
check("an empty form is stopped with a plain sentence", "title" in txt(pg, "#analysis-problem").lower(), txt(pg, "#analysis-problem"))
fill(pg, op_an_title="Replace the delivery fleet", op_an_cur="ngn", op_an_rate="100.01", op_an_purpose="Compare buying with leasing vans"); pg.click("#op-an-save"); pg.wait_for_timeout(300)
check("a rate above 100 percent is stopped", "more than 100" in txt(pg, "#analysis-problem"), txt(pg, "#analysis-problem"))
fill(pg, op_an_rate="10"); pg.click("#op-an-save"); pg.wait_for_timeout(1500)
check("the analysis is numbered", "OA-001" in txt(pg, "[data-analysis='OA-001']") and "discount rate 10.00 percent" in txt(pg, "[data-analysis='OA-001']"), txt(pg, "#op-notice") + err(pg))
opn(pg, "OA-001"); a1 = aid("OA-001", DARA)
check("submitting without two options is not offered", pg.locator("#op-sb-save").count() == 0 and pg.locator("#op-need-two").count() == 1)
check("the server refuses to submit it", st(A("POST", f"/analyses/{a1}/submit", TUNDE, {})) == 409)
pg.click("#op-opt-save"); pg.wait_for_timeout(300)
check("an empty option is stopped", bool(txt(pg, "#option-problem")), txt(pg, "#option-problem"))
fill(pg, op_opt_name="Buy", op_opt_up="0", op_opt_flows="600; 600"); pg.click("#op-opt-save"); pg.wait_for_timeout(300)
check("a zero upfront cost is stopped", "more than zero" in txt(pg, "#option-problem"), txt(pg, "#option-problem"))
fill(pg, op_opt_up="1,000.00", op_opt_flows="600; x"); pg.click("#op-opt-save"); pg.wait_for_timeout(300)
check("a bad flow is stopped and named by year", "year 2" in txt(pg, "#option-problem"), txt(pg, "#option-problem"))
fill(pg, op_opt_flows="600; 600"); pg.click("#op-opt-save"); pg.wait_for_timeout(1500)
check("the first option is added and worked out exactly", f"NPV {npv(1000, [600, 600], 10)}" in txt(pg, "[data-option='1']") and "payback in year 2" in txt(pg, "[data-option='1']") and "benefit-cost ratio 1.20" in txt(pg, "[data-option='1']"), txt(pg, "#op-results") + err(pg))
fill(pg, op_opt_name="buy", op_opt_up="200", op_opt_flows="150; 150; 150"); pg.click("#op-opt-save"); pg.wait_for_timeout(1200)
check("the same name twice is refused", bool(err(pg)), err(pg))
fill(pg, op_opt_name="Lease", op_opt_up="200", op_opt_flows="150; 150; 150"); pg.click("#op-opt-save"); pg.wait_for_timeout(1500)
check("the second option is added", f"NPV {npv(200, [150, 150, 150], 10)}" in txt(pg, "[data-option='2']"), txt(pg, "#op-results") + err(pg))
check("only the option with the highest NPV is marked", "Highest NPV" in txt(pg, "[data-option='2']") and "Highest NPV" not in txt(pg, "[data-option='1']"), txt(pg, "#op-results"))
check("other rates are shown", "8.00 percent" in txt(pg, "[data-option='1'] .op-sens") and "12.00 percent" in txt(pg, "[data-option='1'] .op-sens"), txt(pg, "[data-option='1'] .op-sens"))
check("a float amount is refused by the server", st(ad(DARA, a1, name="Floaty", upfront_cost=10.5)) == 400)
check("more than ten years are refused by the server", st(ad(DARA, a1, name="Long one", flows=["1"] * 11)) == 400)
fill(pg, op_opt_name="Third", op_opt_up="10", op_opt_flows="5"); pg.click("#op-opt-save"); pg.wait_for_timeout(1500)
pg.fill("#op-opt-3-note", "no"); pg.click("#op-opt-3-remove"); pg.wait_for_timeout(400)
check("removing without a reason is stopped", "10 characters" in err(pg) or "reason" in err(pg).lower(), err(pg))
pg.fill("#op-opt-3-note", "Not a real choice for us"); pg.click("#op-opt-3-remove"); pg.wait_for_timeout(1500)
check("a removed option keeps its reason and leaves the results", "Removed: Not a real choice for us" in txt(pg, "[data-opt='3']") and pg.locator("[data-option='3']").count() == 0, txt(pg, "#op-options"))
pg.fill("#op-sb-note", "short"); pg.click("#op-sb-save"); pg.wait_for_timeout(500)
check("a short note is stopped", "10 characters" in err(pg) or "note" in err(pg).lower(), err(pg))
pg.fill("#op-sb-note", ""); pg.click("#op-sb-save"); pg.wait_for_timeout(1500)
check("the analysis is submitted and locked", "Waiting for review" in txt(pg, "[data-analysis='OA-001']") and pg.locator("#op-opt-save").count() == 0 and pg.locator("#op-dc-approve").count() == 0, txt(pg, "[data-analysis='OA-001']") + err(pg))
check("adding an option to a submitted analysis is refused", st(ad(DARA, a1, name="Late one")) == 409)

# ---- the owner prepares two more (browser user is Tunde); the approver approves one ----
a2 = mk(DARA)["id"]; ad(DARA, a2); ad(DARA, a2, name="Supplier two", upfront_cost="3000", flows=["1200", "1200", "1200"]); A("POST", f"/analyses/{a2}/submit", DARA, {})
a3 = mk(DARA, title="Warehouse lighting", currency="NGN")["id"]; ad(DARA, a3, name="LED"); ad(DARA, a3, name="Halogen", upfront_cost="900", flows=["300", "300"]); A("POST", f"/analyses/{a3}/submit", DARA, {})
check("the owner cannot approve their own analysis", st(A("POST", f"/analyses/{a2}/approve", DARA, {})) == 403)
check("the owner cannot return their own analysis", st(A("POST", f"/analyses/{a2}/return", DARA, {"reason": "Returning my own analysis"})) == 403)
check("an administrator cannot approve (no approve permission)", st(A("POST", f"/analyses/{a2}/approve", TUNDE, {})) == 403)
check("the approver approves the dollar analysis", st(A("POST", f"/analyses/{a2}/approve", KWAME, {"note": "Quotes were checked"})) == "APPROVED")
check("the owner cannot record a decision on their own analysis", st(A("POST", f"/analyses/{a2}/decision", DARA, {"option_no": 2, "rationale": "Chosen by the person who submitted it"})) == 403)
check("a decision cannot be recorded before approval", st(A("POST", f"/analyses/{a3}/decision", KWAME, {"option_no": 1, "rationale": "Chosen before it was approved"})) == 409)

# ---- Kwame returns the first analysis, Tunde edits and resubmits, Kwame approves and records the decision ----
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/oprs"); tab(pg, "analyses"); opn(pg, "OA-001")
check("the approver sees the review buttons but no editing", pg.locator("#op-dc-approve").count() == 1 and pg.locator("#op-opt-save").count() == 0 and pg.locator("#op-an-save").count() == 0)
pg.click("#op-dc-return"); pg.wait_for_timeout(400)
check("returning without a reason is stopped", "10 characters" in err(pg) or "reason" in err(pg).lower(), err(pg))
pg.fill("#op-dc-note", "Please add a third supplier quote"); pg.click("#op-dc-return"); pg.wait_for_timeout(1500)
check("a different person returns it with a reason", "Returned" in txt(pg, "[data-analysis='OA-001']") and "Please add a third supplier quote" in txt(pg, "#op-decision-note"), txt(pg, "[data-analysis='OA-001']") + err(pg))
sign_in(pg, *TUNDE, "Meridian"); goto(pg, "/oprs"); tab(pg, "analyses"); opn(pg, "OA-001")
check("a returned analysis can be edited again", pg.locator("#op-opt-save").count() == 1 and pg.locator("#op-sb-save").count() == 1)
fill(pg, op_opt_name="Hire", op_opt_up="50", op_opt_flows="30; 30"); pg.click("#op-opt-save"); pg.wait_for_timeout(1500)
check("a third option is added", "Hire" in txt(pg, "#op-options") and pg.locator("[data-option='4']").count() == 1, txt(pg, "#op-options") + err(pg))
pg.click("#op-sb-save"); pg.wait_for_timeout(1500)
check("and submitted again", "Waiting for review" in txt(pg, "[data-analysis='OA-001']"), txt(pg, "[data-analysis='OA-001']") + err(pg))
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/oprs"); tab(pg, "analyses"); opn(pg, "OA-001")
pg.click("#op-dc-approve"); pg.wait_for_timeout(1500)
check("a different person approves", "Approved" in txt(pg, "[data-analysis='OA-001']") and pg.locator("#op-dc-approve").count() == 0, txt(pg, "[data-analysis='OA-001']") + err(pg))
check("an approved analysis cannot be decided again", st(A("POST", f"/analyses/{a1}/return", DARA, {"reason": "Trying to return it later"})) == 409)
check("an approved analysis cannot be changed", st(ad(DARA, a1, name="After")) == 409 and st(A("POST", f"/analyses/{a1}/withdraw", TUNDE, {"reason": "Trying to withdraw it later"})) == 409)
check("the decision form is offered to a different person", pg.locator("#op-dec-save").count() == 1)
pg.click("#op-dec-save"); pg.wait_for_timeout(300)
check("an empty decision is stopped", "option" in txt(pg, "#decision-problem").lower(), txt(pg, "#decision-problem"))
pg.select_option("#op-dec-opt", "1"); fill(pg, op_dec_why="short"); pg.click("#op-dec-save"); pg.wait_for_timeout(300)
check("a short rationale is stopped", "rationale" in txt(pg, "#decision-problem").lower(), txt(pg, "#decision-problem"))
fill(pg, op_dec_why="Cash is available now and buying is simpler"); pg.click("#op-dec-save"); pg.wait_for_timeout(1500)
check("the decision is recorded with its reason", "Chosen: #1 Buy" in txt(pg, "#op-decision") and "Cash is available now" in txt(pg, "#op-decision"), txt(pg, "#op-decision") + err(pg))
check("choosing an option without the highest NPV is flagged, not blocked", pg.locator("#op-decision-flag").count() == 1, "")
check("the decision cannot be recorded twice", pg.locator("#op-dec-save").count() == 0 and st(A("POST", f"/analyses/{a1}/decision", DARA, {"option_no": 2, "rationale": "Changing my mind later on"})) == 409)

# ---- overview (browser user is the owner) ----
sign_in(pg, *DARA, "Meridian"); goto(pg, "/oprs"); tab(pg, "overview")
at = txt(pg, "#op-attention").upper()
check("review, decision and not-highest-NPV items need attention", all(s in at for s in ("ANALYSES TO REVIEW", "DECISIONS NEEDED", "DECISION NOT HIGHEST NPV")), at)
check("the counts add up", "Approved: 2" in txt(pg, "#op-counts") and "Waiting for review: 1" in txt(pg, "#op-counts") and "Decisions recorded: 1" in txt(pg, "#op-decisions"), txt(pg, "#op-counts"))
check("currencies are kept apart", "NGN: 1 analysis" in txt(pg, "[data-currency='NGN']") and "USD: 1 analysis" in txt(pg, "[data-currency='USD']"), txt(pg, "#op-currencies"))

# ---- isolation and audit ----
check("the other company sees none of it", A("GET", "/analyses", OTHER, org="Other") == [])
check("the other company cannot read or act on an analysis", st(A("GET", f"/analyses/{a1}", OTHER, org="Other")) == 404 and st(A("POST", f"/analyses/{a3}/approve", OTHER, {}, org="Other")) == 404)
check("the other company's overview is empty", A("GET", "/overview", OTHER, org="Other")["counts"]["approved"] == 0)
acts = api("GET", "/_audit", KWAME, "Meridian")["actions"]
for a_ in ("OPRS_ANALYSIS_CREATED", "OPRS_OPTION_ADDED", "OPRS_OPTION_REMOVED", "OPRS_ANALYSIS_SUBMITTED", "OPRS_ANALYSIS_RETURNED", "OPRS_ANALYSIS_APPROVED", "OPRS_DECISION_RECORDED"):
    check(f"the audit trail has {a_}", a_ in acts, [x for x in acts if "OPRS" in x])
aud = str(api("GET", "/_audit", KWAME, "Meridian"))
check("no typed content is copied into the audit trail", all(s not in aud for s in ("delivery fleet", "vans", "Supplier", "Warehouse", "LED", "Halogen", "Not a real choice", "third supplier", "Cash is available", "Quotes were checked")))
check("no page errors in the browser", not errs, errs[:3])
finish(p, b)
