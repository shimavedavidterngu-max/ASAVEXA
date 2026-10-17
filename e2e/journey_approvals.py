"""Browser journey: Approval workflows (Stage 41). Run via e2e/run_all.py. The browser user and the user making API calls are always different people."""
from common import *

def hrefs(pg): return [a.get_attribute("href") for a in pg.locator(".app-sidebar a").all()]
def tab(pg, name):
    pg.wait_for_selector(f"#apw-tab-{name}"); pg.click(f"#apw-tab-{name}"); pg.wait_for_timeout(1200)
def body(pg): return pg.inner_text("body")
def err(pg): return txt(pg, ".alert-error")
def A(m, path, who, bodyj=None, org="Meridian"): return api(m, "/approvals" + path, who, org, bodyj)
def st(r): return r.get("status") if isinstance(r, dict) else None
def pid(ref, who): return next(i["id"] for i in A("GET", "/policies", who) if i["ref"] == ref)
def rid(ref, who): return next(i["id"] for i in A("GET", "/requests", who) if i["ref"] == ref)
def fill(pg, **ids):
    for k, v in ids.items(): pg.fill("#" + k.replace("_", "-"), v)
def open_pl(pg, ref):
    pg.wait_for_selector(f"#apw-pl-open-{ref}", timeout=8000)
    if pg.locator("#apw-policy-detail").count() and ref in txt(pg, "#apw-policy-detail h3"): return
    pg.click(f"#apw-pl-open-{ref}"); pg.wait_for_timeout(900)
def open_rq(pg, ref):
    pg.wait_for_selector(f"#apw-rq-open-{ref}", timeout=8000)
    if pg.locator("#apw-request-detail").count() and ref in txt(pg, "#apw-request-detail h3"): return
    pg.click(f"#apw-rq-open-{ref}"); pg.wait_for_timeout(900)
def mkpol(who, name, steps, kind="PAYMENT"): return A("POST", "/policies", who, dict(name=name, request_kind=kind, steps=steps, description="Approval path for large supplier payments"))
def mkreq(who, policy, ref="PAY-9", **kw):
    d = dict(policy_id=policy, title="Supplier payment", request_ref=ref, amount="1500.50", currency="USD", description="Quarterly supplier payment run"); d.update(kw); return A("POST", "/requests", who, d)

start_web()
p, b, pg, errs = session()

# ---- an accountant has no business here ----
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/approvals")
check("the menu does not offer the workspace to an accountant", "#/approvals" not in hrefs(pg), hrefs(pg))
check("typing the address shows no content", "Propose a policy" not in body(pg), body(pg)[:200])
check("the server refuses an accountant (overview)", st(A("GET", "/overview", AISHA)) == 403)
check("the server refuses an accountant (requests)", st(A("GET", "/requests", AISHA)) == 403)

# ---- Tunde proposes the first policy ----
sign_in(pg, *TUNDE, "Meridian"); goto(pg, "/approvals")
check("the menu offers the workspace", "#/approvals" in hrefs(pg), hrefs(pg))
check("the banner says an approval is only a record", "record" in txt(pg, "#apw-banner") and "nothing else is blocked" in txt(pg, "#apw-banner"), txt(pg, "#apw-banner"))
check("with no policy, attention says so", "No policy is active yet" in txt(pg, "#apw-attention"), txt(pg, "#apw-attention"))
tab(pg, "requests")
check("no request can be submitted before a policy is active", pg.locator("#apw-rq-save").count() == 0 and "No policy is active yet" in txt(pg, "#apw-rq-nopolicy"), body(pg)[:300])
tab(pg, "policies")
pg.click("#apw-pl-save"); pg.wait_for_timeout(300)
check("an empty policy form is stopped with a plain sentence", "name" in txt(pg, "#policy-problem").lower(), txt(pg, "#policy-problem"))
fill(pg, apw_pl_name="Supplier payments", apw_pl_desc="Approval path for large supplier payments", apw_pl_s1l="Finance review", apw_pl_s1n="0"); pg.click("#apw-pl-save"); pg.wait_for_timeout(300)
check("zero approvals at a step is stopped", "approvals needed at step 1" in txt(pg, "#policy-problem"), txt(pg, "#policy-problem"))
fill(pg, apw_pl_s1n="1", apw_pl_s2l="finance REVIEW", apw_pl_s2n="1"); pg.click("#apw-pl-save"); pg.wait_for_timeout(300)
check("two steps with the same label are stopped", "different label" in txt(pg, "#policy-problem"), txt(pg, "#policy-problem"))
fill(pg, apw_pl_s2l="Director sign-off"); pg.click("#apw-pl-save"); pg.wait_for_timeout(1500)
check("the policy is numbered and waits", "AP-001" in txt(pg, "[data-policy='AP-001']") and "Waiting for a decision" in txt(pg, "[data-policy='AP-001']") and "2 step(s) · 2 approval(s) in total" in txt(pg, "[data-policy='AP-001']"), txt(pg, "#apw-notice") + err(pg))
open_pl(pg, "AP-001"); p1 = pid("AP-001", DARA)
check("the proposer sees no activate button", pg.locator("#apw-pl-activate").count() == 0 and pg.locator("#apw-pl-reject").count() == 0)
check("the proposer cannot activate through the server", st(A("POST", f"/policies/{p1}/activate", TUNDE, {})) == 403)
check("a waiting policy takes no requests", st(mkreq(TUNDE, p1)) == 409)

# ---- more policies; the owner decides them (browser user is Tunde) ----
p2 = mkpol(TUNDE, "Panel decisions", [{"label": "Panel", "required": 2}])["id"]; p3 = mkpol(TUNDE, "Duplicate policy", [{"label": "Only step", "required": 1}])["id"]
check("a policy with the same name is refused", st(mkpol(TUNDE, "supplier PAYMENTS", [{"label": "Only step", "required": 1}])) == 409)
check("more than three steps are refused", st(mkpol(TUNDE, "Too many", [{"label": f"Step {i}", "required": 1} for i in range(4)])) == 400)
check("the owner activates one and rejects one", st(A("POST", f"/policies/{p2}/activate", DARA, {"note": "Matches our delegation of authority"})) == "ACTIVE" and st(A("POST", f"/policies/{p3}/reject", DARA, {"reason": "Duplicate of the supplier policy"})) == "REJECTED")
check("the owner cannot decide a policy they proposed", st(A("POST", f"/policies/{mkpol(DARA, 'Owner policy', [{'label': 'Only step', 'required': 1}])['id']}/activate", DARA, {})) == 403)

# ---- Kwame activates the first policy in the browser ----
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/approvals"); tab(pg, "policies"); open_pl(pg, "AP-001")
check("the approver sees activate and reject", pg.locator("#apw-pl-activate").count() == 1 and pg.locator("#apw-pl-reject").count() == 1)
pg.click("#apw-pl-reject"); pg.wait_for_timeout(500)
check("rejecting needs a reason", "reason" in err(pg).lower() or "reason" in txt(pg, "#apw-notice").lower() or pg.locator(".alert-error").count() > 0, err(pg))
pg.click("#apw-pl-activate"); pg.wait_for_timeout(1500)
check("the policy is active", "Active" in txt(pg, "[data-policy='AP-001']") and "Policy activated" in txt(pg, "#apw-notice"), txt(pg, "[data-policy='AP-001']") + txt(pg, "#apw-notice") + err(pg))
check("an active policy has no activate button but can be retired", pg.locator("#apw-pl-activate").count() == 0 and pg.locator("#apw-pl-retire").count() == 1)

# ---- Tunde submits a request in the browser ----
sign_in(pg, *TUNDE, "Meridian"); goto(pg, "/approvals"); tab(pg, "requests")
pg.click("#apw-rq-save"); pg.wait_for_timeout(300)
check("an empty request form is stopped", "policy" in txt(pg, "#request-problem").lower(), txt(pg, "#request-problem"))
pg.select_option("#apw-rq-policy", index=1); fill(pg, apw_rq_title="Supplier payment", apw_rq_ref="PAY-1", apw_rq_desc="Quarterly supplier payment run", apw_rq_amount="2,500,000.50"); pg.click("#apw-rq-save"); pg.wait_for_timeout(300)
check("an amount without a currency is stopped", "both the amount and its currency" in txt(pg, "#request-problem"), txt(pg, "#request-problem"))
fill(pg, apw_rq_cur="ngn", apw_rq_amount="1.234"); pg.click("#apw-rq-save"); pg.wait_for_timeout(300)
check("an amount with three decimals is stopped", "amount" in txt(pg, "#request-problem").lower(), txt(pg, "#request-problem"))
fill(pg, apw_rq_amount="2,500,000.50"); pg.click("#apw-rq-save"); pg.wait_for_timeout(1500)
check("the request is numbered and waits at step 1", "AR-001" in txt(pg, "[data-request='AR-001']") and "Waiting for approval" in txt(pg, "[data-request='AR-001']") and "2500000.50 NGN" in txt(pg, "[data-request='AR-001']") and "step 1 of 2: Finance review" in txt(pg, "[data-request='AR-001']"), txt(pg, "#apw-notice") + err(pg))
open_rq(pg, "AR-001"); r1 = rid("AR-001", DARA)
check("the submitter sees no approve button and may withdraw", pg.locator("#apw-rq-approve").count() == 0 and pg.locator("#apw-rq-withdraw").count() == 1)
check("the submitter cannot approve or reject through the server", st(A("POST", f"/requests/{r1}/approve", TUNDE, {})) == 403 and st(A("POST", f"/requests/{r1}/reject", TUNDE, {"reason": "Rejecting my own request"})) == 403)
check("someone else cannot withdraw it", st(A("POST", f"/requests/{r1}/withdraw", DARA, {"reason": "Withdrawing for someone else"})) == 403)

# ---- Kwame approves step 1 in the browser ----
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/approvals"); tab(pg, "requests"); open_rq(pg, "AR-001")
check("the approver sees approve and reject", pg.locator("#apw-rq-approve").count() == 1 and pg.locator("#apw-rq-reject").count() == 1)
pg.click("#apw-rq-reject"); pg.wait_for_timeout(500)
check("rejecting needs a reason", "reason" in err(pg).lower() or pg.locator(".alert-error").count() > 0, err(pg))
check("the request is still waiting after the refused rejection", "Waiting for approval" in txt(pg, "[data-request='AR-001']"), txt(pg, "[data-request='AR-001']"))
pg.fill("#apw-rq-note", "Invoice matches the order"); pg.click("#apw-rq-approve"); pg.wait_for_timeout(1500)
check("step 1 passed and the request moved to step 2", "step 2 of 2: Director sign-off" in txt(pg, "[data-request='AR-001']") and "Your approval is recorded" in txt(pg, "#apw-notice"), txt(pg, "[data-request='AR-001']") + txt(pg, "#apw-notice") + err(pg))
check("the same person is not offered a second decision", pg.locator("#apw-rq-approve").count() == 0 and "already decided" in txt(pg, "#apw-request-detail"), txt(pg, "#apw-request-detail")[:300])
check("the server refuses a second decision by the same person", st(A("POST", f"/requests/{r1}/approve", KWAME, {})) == 403 and st(A("POST", f"/requests/{r1}/reject", KWAME, {"reason": "Changing my mind afterwards"})) == 403)
check("the decision and its note are listed under the step", "Approved on" in txt(pg, "#apw-steps") and "Invoice matches the order" in txt(pg, "#apw-steps"), txt(pg, "#apw-steps"))

# ---- the owner finishes it through the server, then the browser shows it approved ----
done = A("POST", f"/requests/{r1}/approve", DARA, {"note": "Within the delegated limit"})
check("the second step approval completes the request", done.get("status") == "APPROVED" and done.get("current_step") is None, done)
check("an approved request takes no more decisions", st(A("POST", f"/requests/{r1}/approve", TUNDE, {})) in (403, 409))

# ---- reject and withdraw paths ----
r2 = mkreq(TUNDE, p2, "PAY-2", amount="900", currency="NGN")["id"]
r3 = mkreq(TUNDE, p1, "PAY-3")["id"]; r4 = mkreq(TUNDE, p1, "PAY-4", amount=None, currency=None)["id"]
sign_in(pg, *DARA, "Meridian"); goto(pg, "/approvals"); tab(pg, "requests"); open_rq(pg, "AR-002")
pg.fill("#apw-rq-note", "short"); pg.click("#apw-rq-reject"); pg.wait_for_timeout(600)
check("a short rejection reason is stopped", pg.locator(".alert-error").count() > 0 and "Waiting for approval" in txt(pg, "[data-request='AR-002']"), err(pg))
pg.fill("#apw-rq-note", "The second quote is missing"); pg.click("#apw-rq-reject"); pg.wait_for_timeout(1500)
check("the request is rejected with its reason", "Rejected" in txt(pg, "[data-request='AR-002']") and "The second quote is missing" in txt(pg, "#apw-decision"), txt(pg, "[data-request='AR-002']") + err(pg))
check("a rejected request takes no more decisions", st(A("POST", f"/requests/{r2}/approve", KWAME, {})) == 409)
sign_in(pg, *TUNDE, "Meridian"); goto(pg, "/approvals"); tab(pg, "requests"); open_rq(pg, "AR-003")
pg.fill("#apw-rq-wd-note", "short"); pg.click("#apw-rq-withdraw"); pg.wait_for_timeout(600)
check("a short withdrawal reason is stopped", pg.locator(".alert-error").count() > 0 and "Waiting for approval" in txt(pg, "[data-request='AR-003']"), err(pg))
pg.fill("#apw-rq-wd-note", "Supplier cancelled the order"); pg.click("#apw-rq-withdraw"); pg.wait_for_timeout(1500)
check("the request is withdrawn with its reason", "Withdrawn" in txt(pg, "[data-request='AR-003']") and "Supplier cancelled the order" in txt(pg, "#apw-withdrawn"), txt(pg, "[data-request='AR-003']") + err(pg))

# ---- retiring a policy leaves requests under way alone (browser user is the owner) ----
sign_in(pg, *DARA, "Meridian"); goto(pg, "/approvals"); tab(pg, "policies"); open_pl(pg, "AP-001")
check("the policy shows the request under way", "1 request(s) under way" in txt(pg, "[data-policy='AP-001']"), txt(pg, "[data-policy='AP-001']"))
pg.fill("#apw-pl-retire-note", "Replaced by a new delegation of authority"); pg.click("#apw-pl-retire"); pg.wait_for_timeout(1500)
check("the policy is retired with its reason", "Retired" in txt(pg, "[data-policy='AP-001']") and "Replaced by a new delegation" in txt(pg, "#apw-pl-retired"), txt(pg, "[data-policy='AP-001']") + err(pg))
check("a retired policy takes no new requests", st(mkreq(TUNDE, p1, "PAY-5")) == 409)
still = A("POST", f"/requests/{r4}/approve", KWAME, {})
check("a request under way still finishes under the steps it started with", still.get("status") == "PENDING" and still.get("current_step") == 2 and still.get("current_label") == "Director sign-off", still)

# ---- overview ----
tab(pg, "overview")
cn = txt(pg, "#apw-counts")
check("the counts add up", "waiting for approval 1, approved 1, rejected 1, withdrawn 1" in cn and "active 1" in cn and "retired 1" in cn and "rejected 1" in cn, cn)
cur = txt(pg, "#apw-currency")
check("amounts are shown per currency, never added", "NGN: waiting 0.00, approved 2500000.50" in cur and "USD" not in cur, cur)
check("the waiting request needs attention", "REQUESTS WAITING" in txt(pg, "#apw-attention").upper(), txt(pg, "#apw-attention"))
pg.fill("#apw-set-stale_days", "abc"); pg.click("#apw-set-save"); pg.wait_for_timeout(400)
check("a bad setting is stopped", "1 to 365" in txt(pg, "#setting-problem"), txt(pg, "#setting-problem"))
pg.fill("#apw-set-stale_days", "9"); pg.click("#apw-set-save"); pg.wait_for_timeout(1500)
check("the setting is saved", "after 9 day(s)" in txt(pg, "#apw-setting-meaning") or "9 day(s)" in txt(pg, "#apw-setting-meaning"), txt(pg, "#apw-setting-meaning"))
check("an administrator cannot change the setting", st(A("PUT", "/setting", TUNDE, {"stale_days": 3})) == 403)

# ---- isolation and audit ----
check("the other company sees none of it", A("GET", "/requests", OTHER, org="Other") == [] and A("GET", "/policies", OTHER, org="Other") == [])
check("the other company cannot read or act on a request", st(A("GET", f"/requests/{r1}", OTHER, org="Other")) == 404 and st(A("POST", f"/requests/{r1}/approve", OTHER, {}, org="Other")) == 404 and st(A("POST", f"/policies/{p1}/retire", OTHER, {"reason": "From another company"}, org="Other")) == 404)
check("the other company cannot submit against this company's policy", st(A("POST", "/requests", OTHER, dict(policy_id=p2, title="Supplier payment", request_ref="PAY-X", description="Quarterly supplier payment run"), org="Other")) == 404)
check("the other company's overview is empty", A("GET", "/overview", OTHER, org="Other")["requests"]["pending"] == 0)
acts = api("GET", "/_audit", KWAME, "Meridian")["actions"]
for a_ in ("APPROVALS_POLICY_PROPOSED", "APPROVALS_POLICY_ACTIVATED", "APPROVALS_POLICY_REJECTED", "APPROVALS_POLICY_RETIRED", "APPROVALS_REQUEST_SUBMITTED", "APPROVALS_REQUEST_STEP_APPROVED", "APPROVALS_REQUEST_APPROVED", "APPROVALS_REQUEST_REJECTED", "APPROVALS_REQUEST_WITHDRAWN", "APPROVALS_SETTING_SET"):
    check(f"the audit trail has {a_}", a_ in acts, [x for x in acts if "APPROVALS" in x])
aud = str(api("GET", "/_audit", KWAME, "Meridian"))
check("no typed content is copied into the audit trail", all(s not in aud for s in ("Supplier payments", "Panel decisions", "Duplicate policy", "Quarterly supplier", "2500000", "PAY-1", "Invoice matches", "Within the delegated", "second quote", "Supplier cancelled", "Replaced by a new", "Director sign-off", "Finance review")), "found typed text in the audit trail")
check("no page errors in the browser", not errs, errs[:3])
finish(p, b)
