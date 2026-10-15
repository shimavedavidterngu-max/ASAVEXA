"""Browser journey: Insurance and claims (Stage 29). Run via e2e/run_all.py. The browser user and the user making API calls are always different people (one login at a time per person)."""
from datetime import datetime, timedelta, timezone

from common import *

TODAY = datetime.now(timezone.utc).date()
D = lambda n: (TODAY + timedelta(days=n)).isoformat()
def hrefs(pg): return [a.get_attribute("href") for a in pg.locator(".app-sidebar a").all()]
def tab(pg, name):
    pg.click(f"#ic-tab-{name}"); pg.wait_for_timeout(900)
def body(pg): return pg.inner_text("body")
def err(pg): return txt(pg, ".alert-error")
def A(m, path, who, bodyj=None, org="Meridian"): return api(m, "/insurance" + path, who, org, bodyj)
def st(r): return r.get("status") if isinstance(r, dict) else None
def pdetails(pg, ref):
    tab(pg, "policies")
    if ref in txt(pg, "#ic-policy-detail"): return      # already open (the page keeps its state while the same person stays signed in)
    pg.click(f"#ic-po-open-{ref}"); pg.wait_for_timeout(1000)
def cdetails(pg, ref):
    tab(pg, "claims")
    if ref in txt(pg, "#ic-claim-detail"): return
    pg.click(f"#ic-cl-open-{ref}"); pg.wait_for_timeout(1000)
def pid(ref, who): return next(i["id"] for i in A("GET", "/policies", who) if i["ref"] == ref)
def cid(ref, who): return next(i["id"] for i in A("GET", "/claims", who) if i["ref"] == ref)
def fill(pg, **ids):
    for k, v in ids.items(): pg.fill("#" + k.replace("_", "-"), v)
def pol(who, **kw):
    d = dict(insurer="AXA Mansard", policy_number="AM-77", cover_type="MOTOR", covers="Delivery vans", currency="USD", sum_insured="5000", premium="300", start_date=D(-100), end_date=D(200)); d.update(kw); return A("POST", "/policies", who, d)
def clm(who, p, **kw):
    d = dict(loss_date=D(-10), reported_date=D(-9), description="Van damaged in a collision", claimed_amount="1000"); d.update(kw); return A("POST", f"/policies/{p}/claims", who, d)
def prop(who, c, **kw):
    d = dict(outcome="SETTLE", amount="500", note="Insurer confirmed by letter"); d.update(kw); return A("POST", f"/claims/{c}/proposals", who, d)

start_web()
p, b, pg, errs = session()

# ---- an accountant has no business here ----
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/insurance")
check("the menu does not offer the workspace to an accountant", "#/insurance" not in hrefs(pg), hrefs(pg))
check("typing the address shows no content", "Record a policy" not in body(pg), body(pg)[:200])
check("the server refuses an accountant (overview)", st(A("GET", "/overview", AISHA)) == 403)
check("the server refuses an accountant (claims)", st(A("GET", "/claims", AISHA)) == 403)

# ---- Tunde records a policy and a claim, and proposes an outcome ----
sign_in(pg, *TUNDE, "Meridian"); goto(pg, "/insurance")
check("the menu offers the workspace", "#/insurance" in hrefs(pg), hrefs(pg))
check("the banner says it contacts no insurer and gives no advice", "contacts no insurer" in txt(pg, "#ic-banner") and "no insurance or legal advice" in txt(pg, "#ic-banner") and "posts nothing to the ledger" in txt(pg, "#ic-banner"), txt(pg, "#ic-banner"))
check("nothing needs attention yet", "Nothing needs attention" in txt(pg, "#ic-attention"), txt(pg, "#ic-attention"))
tab(pg, "policies")
pg.click("#ic-po-save"); pg.wait_for_timeout(300)
check("an empty form is stopped with a plain sentence", "insurer" in txt(pg, "#policy-problem").lower(), txt(pg, "#policy-problem"))
fill(pg, ic_po_insurer="Leadway Assurance", ic_po_number="PL-1001", ic_po_covers="Warehouse and stock", ic_po_cur="ngn", ic_po_si="1,000,000", ic_po_prem="25000.5", ic_po_start=D(-60), ic_po_end=D(-70)); pg.click("#ic-po-save"); pg.wait_for_timeout(300)
check("an end date before the start is stopped", "after the start" in txt(pg, "#policy-problem"), txt(pg, "#policy-problem"))
fill(pg, ic_po_end=D(30), ic_po_excess="2000000"); pg.click("#ic-po-save"); pg.wait_for_timeout(300)
check("an excess over the sum insured is stopped", "excess" in txt(pg, "#policy-problem").lower(), txt(pg, "#policy-problem"))
fill(pg, ic_po_excess="5000"); pg.click("#ic-po-save"); pg.wait_for_timeout(1500)
check("the policy is recorded with exact amounts", "IP-001" in txt(pg, "[data-policy='IP-001']") and "sum insured NGN 1000000.00" in txt(pg, "[data-policy='IP-001']") and "premium 25000.50" in txt(pg, "[data-policy='IP-001']") and "excess 5000.00" in txt(pg, "[data-policy='IP-001']"), txt(pg, "#ic-notice") + err(pg))
check("a policy ending within the window is flagged", "Ending soon" in txt(pg, "[data-policy='IP-001']"), txt(pg, "[data-policy='IP-001']"))
check("a duplicate active policy is refused", st(A("POST", "/policies", DARA, dict(insurer="leadway assurance", policy_number="pl-1001", cover_type="PROPERTY", covers="Warehouse", currency="NGN", sum_insured="10", premium="1", start_date=D(-60), end_date=D(30)))) == 409)
check("a float sum insured is refused", st(pol(DARA, policy_number="FL-1", sum_insured=5000.5)) == 400)
pdetails(pg, "IP-001")
fill(pg, ic_cm_loss=D(-10), ic_cm_rep=D(-11), ic_cm_amt="200000", ic_cm_desc="Water damage to stock in the warehouse"); pg.click("#ic-cm-save"); pg.wait_for_timeout(300)
check("reporting before the loss is stopped", "before the loss" in txt(pg, "#claim-problem"), txt(pg, "#claim-problem"))
fill(pg, ic_cm_rep=D(-9), ic_cm_amt="1000000.01"); pg.click("#ic-cm-save"); pg.wait_for_timeout(300)
check("a claim over the sum insured is stopped", "more than the sum insured" in txt(pg, "#claim-problem"), txt(pg, "#claim-problem"))
fill(pg, ic_cm_amt="200000", ic_cm_num="CN-77"); pg.click("#ic-cm-save"); pg.wait_for_timeout(1500)
check("the claim is recorded against the policy", "CL-001" in txt(pg, "#ic-policy-claims") and "claimed NGN 200000.00" in txt(pg, "#ic-policy-claims"), txt(pg, "#ic-policy-claims") + err(pg))
check("a loss outside the policy period is refused", st(clm(DARA, pid("IP-001", DARA), loss_date=D(-200), reported_date=D(-199))) == 400)
check("the administrator cannot cancel (no approve permission)", st(A("POST", f"/policies/{pid('IP-001', DARA)}/cancel", TUNDE, {"reason": "Trying to cancel it now"})) == 403)
check("a policy with an open claim shows no cancel button", pg.locator("#ic-cancel-save").count() == 0)
cdetails(pg, "CL-001")
fill(pg, ic_oc_amt="200000.01", ic_oc_note="Insurer confirmed by letter"); pg.click("#ic-oc-save"); pg.wait_for_timeout(300)
check("a settlement over the claim is stopped", "more than the amount claimed" in txt(pg, "#outcome-problem"), txt(pg, "#outcome-problem"))
fill(pg, ic_oc_amt="150000.25", ic_oc_note="short"); pg.click("#ic-oc-save"); pg.wait_for_timeout(300)
check("a short note is stopped", "10 characters" in txt(pg, "#outcome-problem"), txt(pg, "#outcome-problem"))
fill(pg, ic_oc_note="Insurer confirmed by letter dated last week"); pg.click("#ic-oc-save"); pg.wait_for_timeout(1500)
check("the outcome waits for a decision", "Waiting for a decision" in txt(pg, "[data-proposal='1']") and "Settle for NGN 150000.25" in txt(pg, "[data-proposal='1']") and "Outcome waiting" in txt(pg, "[data-claim='CL-001']"), txt(pg, "#ic-proposals") + err(pg))
check("the proposer sees no approve button", pg.locator("#ic-pr-1-approve").count() == 0 and pg.locator("#ic-oc-save").count() == 0)
c1 = cid("CL-001", DARA)
check("an administrator cannot approve (no approve permission)", st(A("POST", f"/claims/{c1}/proposals/1/approve", TUNDE, {})) == 403)
check("a second proposal while one waits is refused", st(prop(DARA, c1)) == 409)

# ---- Kwame decides ----
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/insurance"); cdetails(pg, "CL-001")
check("the approver sees no entry forms", pg.locator("#ic-oc-save").count() == 0 and pg.locator("#ic-rc-save").count() == 0)
pg.fill("#ic-pr-1-note", "no"); pg.click("#ic-pr-1-approve"); pg.wait_for_timeout(500)
check("a short approval note is stopped", "10 characters" in err(pg) or "note" in err(pg).lower(), err(pg))
pg.fill("#ic-pr-1-note", ""); pg.click("#ic-pr-1-approve"); pg.wait_for_timeout(1500)
check("a different person approves and the claim is settled", "Settled for NGN 150000.25" in txt(pg, "#ic-settled") and "Still to receive 150000.25" in txt(pg, "#ic-settled"), txt(pg, "#ic-claim-detail") + err(pg))
check("a decided proposal cannot be decided again", st(A("POST", f"/claims/{c1}/proposals/1/reject", DARA, {"reason": "Trying to reject it later"})) == 409)

# ---- Tunde records money received ----
sign_in(pg, *TUNDE, "Meridian"); goto(pg, "/insurance"); cdetails(pg, "CL-001")
fill(pg, ic_rc_amt="150000.26", ic_rc_date=D(0), ic_rc_ref="PAY-1"); pg.click("#ic-rc-save"); pg.wait_for_timeout(300)
check("more than is still to be received is stopped", "more than is still to be received" in txt(pg, "#receipt-problem"), txt(pg, "#receipt-problem"))
fill(pg, ic_rc_amt="50000.10", ic_rc_date=D(5)); pg.click("#ic-rc-save"); pg.wait_for_timeout(1200)
check("a future date is refused", "future" in (err(pg) + txt(pg, "#receipt-problem")).lower(), err(pg) + txt(pg, "#receipt-problem"))
fill(pg, ic_rc_date=D(0)); pg.click("#ic-rc-save"); pg.wait_for_timeout(1500)
check("the receipt reduces what is still to be received exactly", "Received 50000.10. Still to receive 100000.15" in txt(pg, "#ic-settled") and "PAY-1" in txt(pg, "#ic-receipts"), txt(pg, "#ic-claim-detail") + err(pg))
check("a duplicate payment reference is refused", st(A("POST", f"/claims/{c1}/receipts", DARA, dict(amount="1", received_on=D(0), reference="pay-1"))) == 409)
check("a float amount is refused", st(A("POST", f"/claims/{c1}/receipts", DARA, dict(amount=1.5, received_on=D(0), reference="PAY-F"))) == 400)
r = A("POST", f"/claims/{c1}/receipts", DARA, dict(amount="100000.15", received_on=D(0), reference="PAY-2"))
check("the rest is received and nothing is left", r.get("outstanding") == "0.00" and r.get("received") == "150000.25", r)
check("nothing more can be received", st(A("POST", f"/claims/{c1}/receipts", DARA, dict(amount="0.01", received_on=D(0), reference="PAY-3"))) == 400)

# ---- more policies and claims: decline, reject, two-person rule ----
p2 = pol(TUNDE); check("the second policy is numbered", p2.get("ref") == "IP-002", p2)
k2 = clm(TUNDE, p2["id"]); check("a USD claim is recorded", k2.get("ref") == "CL-002" and k2.get("currency") == "USD", k2)
check("a decline with an amount is refused", st(prop(TUNDE, k2["id"], outcome="DECLINE", amount="5")) == 400)
check("the owner proposes a settlement", prop(DARA, k2["id"], amount="400.50").get("status") == "PROPOSED")
check("the owner cannot approve their own proposal", st(A("POST", f"/claims/{k2['id']}/proposals/1/approve", DARA, {})) == 403)
check("the owner cannot reject their own proposal either", st(A("POST", f"/claims/{k2['id']}/proposals/1/reject", DARA, {"reason": "Rejecting my own proposal"})) == 403)
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/insurance"); cdetails(pg, "CL-002")
pg.click("#ic-pr-1-reject"); pg.wait_for_timeout(500)
check("rejecting without a reason is stopped", "10 characters" in err(pg) or "reason" in err(pg).lower(), err(pg))
pg.fill("#ic-pr-1-note", "The figure does not match the letter"); pg.click("#ic-pr-1-reject"); pg.wait_for_timeout(1500)
check("a different person rejects with a reason and the claim reopens", "Rejected" in txt(pg, "[data-proposal='1']") and "does not match the letter" in txt(pg, "[data-proposal='1']") and "Open" in txt(pg, "[data-claim='CL-002']"), txt(pg, "#ic-claim-detail") + err(pg))
check("a decline is proposed again", prop(TUNDE, k2["id"], outcome="DECLINE", amount=None, note="Insurer declined: excluded peril").get("status") == "PROPOSED")
goto(pg, "/insurance"); cdetails(pg, "CL-002")
pg.click("#ic-pr-2-approve"); pg.wait_for_timeout(1500)
check("the decline is approved and no money can be received", "decline was recorded" in txt(pg, "#ic-declined") and st(A("POST", f"/claims/{k2['id']}/receipts", DARA, dict(amount="1", received_on=D(0), reference="PAY-X"))) == 409, txt(pg, "#ic-claim-detail") + err(pg))
p3 = pol(TUNDE, policy_number="AM-88", cover_type="CYBER", covers="Cyber liability", currency="NGN", sum_insured="2000", premium="50", start_date=D(-400), end_date=D(-30))
goto(pg, "/insurance"); pdetails(pg, "IP-003")
check("the expired policy is flagged", "Past its end date" in txt(pg, "[data-policy='IP-003']"), txt(pg, "[data-policy='IP-003']"))
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/insurance"); pdetails(pg, "IP-003")
pg.fill("#ic-cancel-note", "no"); pg.click("#ic-cancel-save"); pg.wait_for_timeout(500)
check("cancelling without a proper reason is stopped", "10 characters" in err(pg) or "reason" in err(pg).lower(), err(pg))
pg.fill("#ic-cancel-note", "Replaced by a new cyber policy"); pg.click("#ic-cancel-save"); pg.wait_for_timeout(1500)
check("the policy is cancelled and the reason kept", "Cancelled" in txt(pg, "[data-policy='IP-003']") and "Replaced by a new cyber policy" in txt(pg, "#ic-cancelled"), txt(pg, "#ic-policy-detail") + err(pg))
check("a cancelled policy takes no claims", st(clm(DARA, p3["id"], loss_date=D(-40), reported_date=D(-39))) == 409)
k3 = clm(TUNDE, p2["id"], claimed_amount="750.25"); prop(TUNDE, k3["id"], amount="700.10"); A("POST", f"/claims/{k3['id']}/proposals/1/approve", DARA, {})
A("POST", f"/claims/{k3['id']}/receipts", DARA, dict(amount="100.05", received_on=D(0), reference="PAY-U1"))
k4 = clm(TUNDE, p2["id"], claimed_amount="60")

# ---- overview ----
sign_in(pg, *DARA, "Meridian"); goto(pg, "/insurance"); tab(pg, "overview")
check("totals are shown per currency and never added together", "never added together" in txt(pg, "#ic-totals") and pg.locator("[data-currency='NGN']").count() == 1 and pg.locator("[data-currency='USD']").count() == 1, txt(pg, "#ic-totals"))
check("the NGN figures are exact", "1 active policy, sum insured 1000000.00, premium 25000.50; 0 open claim(s) claiming 0.00; settled 150000.25, received 150000.25, still to receive 0.00" in txt(pg, "[data-currency='NGN']"), txt(pg, "[data-currency='NGN']"))
check("the USD figures are exact", "1 active policy, sum insured 5000.00, premium 300.00; 1 open claim(s) claiming 60.00; settled 700.10, received 100.05, still to receive 600.05" in txt(pg, "[data-currency='USD']"), txt(pg, "[data-currency='USD']"))
check("a settled claim with money owed needs attention", "SETTLED UNPAID" in txt(pg, "#ic-attention").upper(), txt(pg, "#ic-attention"))
check("the counts add up", "Active policies: 2" in txt(pg, "#ic-counts") and "Cancelled policies: 1" in txt(pg, "#ic-counts") and "Open claims: 1" in txt(pg, "#ic-counts") and "Settled claims: 2" in txt(pg, "#ic-counts") and "Declined claims: 1" in txt(pg, "#ic-counts"), txt(pg, "#ic-counts"))
pg.fill("#ic-set-days", "3"); pg.click("#ic-set-save"); pg.wait_for_timeout(400)
check("fewer than 7 days is stopped", "7 to 365" in txt(pg, "#setting-problem"), txt(pg, "#setting-problem"))
pg.fill("#ic-set-days", "14"); pg.click("#ic-set-save"); pg.wait_for_timeout(1500)
check("the setting is saved", "14 days" in txt(pg, "#ic-setting-meaning"), txt(pg, "#ic-setting-meaning"))
check("an administrator cannot change the setting", st(A("PUT", "/setting", TUNDE, {"warning_days": 30})) == 403)
tab(pg, "policies")
check("the shorter window no longer flags the policy", "Ending soon" not in txt(pg, "[data-policy='IP-001']"), txt(pg, "[data-policy='IP-001']"))

# ---- isolation and audit ----
i1 = pid("IP-001", DARA)
check("the other company sees none of it", A("GET", "/policies", OTHER, org="Other") == [] and A("GET", "/claims", OTHER, org="Other") == [])
check("the other company cannot read or act on a record", st(A("GET", f"/policies/{i1}", OTHER, org="Other")) == 404 and st(A("POST", f"/claims/{c1}/receipts", OTHER, dict(amount="1", received_on=D(0), reference="PAY-O"), org="Other")) == 404)
check("the other company's overview is empty", A("GET", "/overview", OTHER, org="Other")["totals"] == [])
acts = api("GET", "/_audit", KWAME, "Meridian")["actions"]
for a_ in ("INSURANCE_POLICY_ADDED", "INSURANCE_POLICY_CANCELLED", "INSURANCE_CLAIM_ADDED", "INSURANCE_OUTCOME_PROPOSED", "INSURANCE_OUTCOME_APPROVED", "INSURANCE_OUTCOME_REJECTED", "INSURANCE_RECEIPT_RECORDED", "INSURANCE_SETTING_SET"):
    check(f"the audit trail has {a_}", a_ in acts, [x for x in acts if "INSURANCE" in x])
aud = str(api("GET", "/_audit", KWAME, "Meridian"))
check("no typed content is copied into the audit trail", "Leadway" not in aud and "PL-1001" not in aud and "Water damage" not in aud and "PAY-1" not in aud and "letter" not in aud and "cyber policy" not in aud and "150000" not in aud)
check("no page errors in the browser", not errs, errs[:3])
finish(p, b)
