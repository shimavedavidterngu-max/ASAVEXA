"""Browser journey: Insolvency (Stage 36). Run via e2e/run_all.py. The browser user and the user making API calls are always different people."""
from datetime import datetime, timedelta, timezone

from common import *

TODAY = datetime.now(timezone.utc).date()
D = lambda n: (TODAY + timedelta(days=n)).isoformat()
def hrefs(pg): return [a.get_attribute("href") for a in pg.locator(".app-sidebar a").all()]
def tab(pg, name):
    pg.wait_for_selector(f"#isv-tab-{name}"); pg.click(f"#isv-tab-{name}"); pg.wait_for_timeout(1200)
def body(pg): return pg.inner_text("body")
def err(pg): return txt(pg, ".alert-error")
def A(m, path, who, bodyj=None, org="Meridian"): return api(m, "/insolvency" + path, who, org, bodyj)
def st(r): return r.get("status") if isinstance(r, dict) else None
def cid(ref, who): return next(i["id"] for i in A("GET", "/cases", who) if i["ref"] == ref)
def fill(pg, **ids):
    for k, v in ids.items(): pg.fill("#" + k.replace("_", "-"), v)
def opn(pg, ref):
    pg.wait_for_selector(f"#isv-cs-open-{ref}", timeout=8000)
    if pg.locator("#isv-case-detail").count() and ref in txt(pg, "#isv-case-detail h3"): return
    pg.click(f"#isv-cs-open-{ref}"); pg.wait_for_timeout(900)
def mk(who, **kw):
    d = dict(title="Second estate", currency="USD", description="Estate of a closed trading company", claims_deadline=D(-1)); d.update(kw); return A("POST", "/cases", who, d)
def ck(who, c, ref, cls, amt, **kw):
    d = dict(creditor_ref=ref, claim_class=cls, amount=amt, basis="Unpaid invoices for goods supplied"); d.update(kw); return A("POST", f"/cases/{c}/claims", who, d)
def en(who, c, kind="REALISATION", amt="1000.00", **kw):
    d = dict(entry_type=kind, description="Sale of the machinery", amount=amt, entry_date=D(-2)); d.update(kw); return A("POST", f"/cases/{c}/entries", who, d)
def shares(total, weights):
    tw = sum(weights); q = [total * w // tw for w in weights]; rem = [total * w % tw for w in weights]
    for i in sorted(range(len(weights)), key=lambda i: (-rem[i], i))[: total - sum(q)]: q[i] += 1
    return q
money = lambda c: f"{c // 100}.{c % 100:02d}"

start_web()
p, b, pg, errs = session()

# ---- an accountant has no business here ----
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/insolvency")
check("the menu does not offer the workspace to an accountant", "#/insolvency" not in hrefs(pg), hrefs(pg))
check("typing the address shows no content", "Propose a case" not in body(pg), body(pg)[:200])
check("the server refuses an accountant (overview)", st(A("GET", "/overview", AISHA)) == 403)
check("the server refuses an accountant (cases)", st(A("GET", "/cases", AISHA)) == 403)

# ---- Tunde proposes a case ----
sign_in(pg, *TUNDE, "Meridian"); goto(pg, "/insolvency")
check("the menu offers the workspace", "#/insolvency" in hrefs(pg), hrefs(pg))
check("the banner says it pays no one and applies no law", "pays no one" in txt(pg, "#isv-banner") and "applies no insolvency law" in txt(pg, "#isv-banner"), txt(pg, "#isv-banner"))
check("nothing needs attention yet", "Nothing needs attention" in txt(pg, "#isv-attention"), txt(pg, "#isv-attention"))
tab(pg, "cases")
pg.click("#isv-cs-save"); pg.wait_for_timeout(300)
check("an empty form is stopped with a plain sentence", "title" in txt(pg, "#case-problem").lower(), txt(pg, "#case-problem"))
fill(pg, isv_cs_title="Acme Textiles liquidation", isv_cs_cur="ngn", isv_cs_desc="Estate of a closed textile company", isv_cs_dl=D(30), isv_cs_order="SECURED, UNSECURED"); pg.click("#isv-cs-save"); pg.wait_for_timeout(300)
check("an order that leaves out a class is stopped", "each class once" in txt(pg, "#case-problem"), txt(pg, "#case-problem"))
fill(pg, isv_cs_order="SECURED, PREFERENTIAL, UNSECURED, SUBORDINATED"); pg.click("#isv-cs-save"); pg.wait_for_timeout(1500)
check("the case is numbered and waits", "IC-001" in txt(pg, "[data-case='IC-001']") and "Waiting for a decision" in txt(pg, "[data-case='IC-001']"), txt(pg, "#isv-notice") + err(pg))
opn(pg, "IC-001"); c1 = cid("IC-001", DARA)
check("claims are not offered before approval", pg.locator("#isv-ck-save").count() == 0 and st(ck(DARA, c1, "SUP-1", "UNSECURED", "100")) == 409)
check("the proposer sees no approve button", pg.locator("#isv-cs-approve").count() == 0)
check("the proposer cannot approve through the server", st(A("POST", f"/cases/{c1}/approve", TUNDE, {})) == 403)

# ---- the owner proposes a second case; the approver approves it by API (browser user is Tunde) ----
c2 = mk(DARA)["id"]
check("the owner cannot approve their own case", st(A("POST", f"/cases/{c2}/approve", DARA, {})) == 403 and st(A("POST", f"/cases/{c2}/reject", DARA, {"reason": "Rejecting my own case"})) == 403)
check("a bad order is refused by the server", st(mk(DARA, priority=["SECURED", "SECURED", "UNSECURED", "PREFERENTIAL"])) == 400)
check("the approver approves the second case", st(A("POST", f"/cases/{c2}/approve", KWAME, {"note": "Appointment documents seen"})) == "OPEN")
check("a claim after the deadline is accepted but flagged", ck(DARA, c2, "LATE-1", "UNSECURED", "250.00")["claims"][0]["late"] is True)
check("the owner cannot record a distribution on their own case", st(A("POST", f"/cases/{c2}/distribution", DARA, {})) == 403)

# ---- Kwame approves the first case ----
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/insolvency"); tab(pg, "cases"); opn(pg, "IC-001")
check("the approver sees the decision buttons but no proposing form", pg.locator("#isv-cs-approve").count() == 1 and pg.locator("#isv-cs-save").count() == 0)
pg.click("#isv-cs-reject"); pg.wait_for_timeout(400)
check("rejecting without a reason is stopped", "10 characters" in err(pg) or "reason" in err(pg).lower(), err(pg))
pg.fill("#isv-cs-note", "ok"); pg.click("#isv-cs-approve"); pg.wait_for_timeout(400)
check("a short approval note is stopped", "10 characters" in err(pg) or "note" in err(pg).lower(), err(pg))
pg.fill("#isv-cs-note", ""); pg.click("#isv-cs-approve"); pg.wait_for_timeout(1500)
check("a different person approves it and it opens", "Open" in txt(pg, "[data-case='IC-001']") and pg.locator("#isv-cs-approve").count() == 0 and pg.locator("#isv-waterfall").count() == 1, txt(pg, "[data-case='IC-001']") + err(pg))
check("an approved case cannot be decided again", st(A("POST", f"/cases/{c1}/reject", DARA, {"reason": "Trying to reject it later"})) == 409)

# ---- Tunde lodges claims and records entries ----
sign_in(pg, *TUNDE, "Meridian"); goto(pg, "/insolvency"); tab(pg, "cases"); opn(pg, "IC-001")
pg.click("#isv-ck-save"); pg.wait_for_timeout(300)
check("an empty claim is stopped", bool(txt(pg, "#claim-problem")), txt(pg, "#claim-problem"))
fill(pg, isv_ck_ref="BANK-1", isv_ck_amt="0", isv_ck_basis="Loan agreement and statement"); pg.select_option("#isv-ck-class", "SECURED"); pg.click("#isv-ck-save"); pg.wait_for_timeout(300)
check("a zero claim is stopped", "more than zero" in txt(pg, "#claim-problem"), txt(pg, "#claim-problem"))
fill(pg, isv_ck_amt="500,000.00"); pg.click("#isv-ck-save"); pg.wait_for_timeout(1500)
check("the secured claim is lodged and waits", "BANK-1" in txt(pg, "[data-claim='1']") and "Secured" in txt(pg, "[data-claim='1']") and "claimed 500000.00" in txt(pg, "[data-claim='1']") and "Waiting for a decision" in txt(pg, "[data-claim='1']"), txt(pg, "#isv-claims") + err(pg))
fill(pg, isv_ck_ref="TAX-1", isv_ck_amt="100000.00", isv_ck_basis="Tax assessment for the last year"); pg.select_option("#isv-ck-class", "PREFERENTIAL"); pg.click("#isv-ck-save"); pg.wait_for_timeout(1500)
check("the preferential claim is lodged", "TAX-1" in txt(pg, "[data-claim='2']"), txt(pg, "#isv-claims") + err(pg))
pg.select_option("#isv-en-type", "REALISATION"); fill(pg, isv_en_amt="1,000,000.00", isv_en_date=D(-2), isv_en_desc="Sale of the machinery"); pg.click("#isv-en-save"); pg.wait_for_timeout(1500)
check("the realisation is recorded and waits", "Realisation 1000000.00" in txt(pg, "[data-entry='1']") and "Waiting for a decision" in txt(pg, "[data-entry='1']"), txt(pg, "#isv-entries") + err(pg))
pg.select_option("#isv-en-type", "COST"); fill(pg, isv_en_amt="50000", isv_en_date=D(-1), isv_en_desc="Administration costs"); pg.click("#isv-en-save"); pg.wait_for_timeout(1500)
check("the cost is recorded and waits", "Cost 50000.00" in txt(pg, "[data-entry='2']"), txt(pg, "#isv-entries") + err(pg))
fill(pg, isv_en_date=D(30), isv_en_amt="10", isv_en_desc="A sale in the future"); pg.click("#isv-en-save"); pg.wait_for_timeout(1200)
check("a future date is stopped by the server", "future" in err(pg).lower(), err(pg))
check("a float amount is refused by the server", st(ck(DARA, c1, "SUP-X", "UNSECURED", 10.5)) == 400)
for ref, amt in (("SUP-1", "300000.00"), ("SUP-2", "200000.00"), ("SUP-3", "100000.01"), ("SUP-9", "50000.00")): ck(DARA, c1, ref, "UNSECURED", amt)
check("an administrator sees no admit or confirm buttons", pg.locator("#isv-ck-1-admit").count() == 0 and pg.locator("#isv-en-1-confirm").count() == 0 and pg.locator("#isv-ds-save").count() == 0)
check("closing is not offered while things wait", pg.locator("#isv-cl-save").count() == 0 and st(A("POST", f"/cases/{c1}/close", DARA, {"reason": "Closing while things wait"})) == 409)
check("the owner cannot admit their own claim", st(A("POST", f"/cases/{c1}/claims/3/admit", DARA, {"amount": "300000.00"})) == 403)

# ---- Kwame decides ----
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/insolvency"); tab(pg, "cases"); opn(pg, "IC-001")
check("with nothing decided, nothing is available to distribute", "available 0.00" in txt(pg, "#isv-funds") and pg.locator("#isv-ds-save").count() == 0, txt(pg, "#isv-funds"))
pg.fill("#isv-ck-1-amt", "600000.00"); pg.click("#isv-ck-1-admit"); pg.wait_for_timeout(1200)
check("admitting more than was claimed is refused", "more than the amount claimed" in err(pg), err(pg))
pg.fill("#isv-ck-1-amt", "0"); pg.click("#isv-ck-1-admit"); pg.wait_for_timeout(400)
check("admitting zero is stopped", "more than zero" in txt(pg, "#admit-1-problem"), txt(pg, "#admit-1-problem"))
for no, adm in ((1, "500000.00"), (2, "80000.00"), (3, "300000.00"), (4, "200000.00"), (5, "100000.01")):
    pg.fill(f"#isv-ck-{no}-amt", adm); pg.click(f"#isv-ck-{no}-admit"); pg.wait_for_timeout(1300)
check("the claims are admitted, the second only in part", "admitted 500000.00" in txt(pg, "[data-claim='1']") and "claimed 100000.00, admitted 80000.00" in txt(pg, "[data-claim='2']") and "Admitted" in txt(pg, "[data-claim='5']"), txt(pg, "#isv-claims") + err(pg))
pg.fill("#isv-ck-6-note", "no"); pg.click("#isv-ck-6-reject"); pg.wait_for_timeout(400)
check("rejecting a claim without a reason is stopped", "10 characters" in err(pg) or "reason" in err(pg).lower(), err(pg))
pg.fill("#isv-ck-6-note", "No proof of debt was supplied"); pg.click("#isv-ck-6-reject"); pg.wait_for_timeout(1500)
check("a different person rejects a claim with a reason", "Rejected" in txt(pg, "[data-claim='6']") and "No proof of debt was supplied" in txt(pg, "[data-claim='6']"), txt(pg, "#isv-claims") + err(pg))
check("a decided claim cannot be decided again", st(A("POST", f"/cases/{c1}/claims/1/reject", DARA, {"reason": "Trying to reject it later"})) == 409)
check("the waterfall waits for the entries", "available 0.00" in txt(pg, "#isv-funds"), txt(pg, "#isv-funds"))
pg.fill("#isv-en-1-note", "no"); pg.click("#isv-en-1-reject"); pg.wait_for_timeout(400)
check("rejecting an entry without a reason is stopped", "10 characters" in err(pg) or "reason" in err(pg).lower(), err(pg))
pg.fill("#isv-en-1-note", ""); pg.click("#isv-en-1-confirm"); pg.wait_for_timeout(1500); pg.click("#isv-en-2-confirm"); pg.wait_for_timeout(1500)
check("a different person confirms both entries", "Confirmed" in txt(pg, "[data-entry='1']") and "Confirmed" in txt(pg, "[data-entry='2']"), txt(pg, "#isv-entries") + err(pg))
f = txt(pg, "#isv-funds")
check("the funds are worked out exactly", all(s in f for s in ("Realisations 1000000.00", "costs 50000.00", "already distributed 0.00", "available 950000.00", "owed to admitted claims 1180000.01", "would be paid 950000.00", "shortfall 230000.01", "left over 0.00")), f)
w = [500000_00, 80000_00, 370000_00]; sh = shares(370000_00, [300000_00, 200000_00, 100000_01])
check("the secured and preferential classes are paid in full", "paid 500000.00; recovery 100.00" in txt(pg, "[data-class='SECURED']") and "paid 80000.00; recovery 100.00" in txt(pg, "[data-class='PREFERENTIAL']"), txt(pg, "#isv-waterfall"))
check("the unsecured class is paid in proportion", "owed 600000.01; paid 370000.00; recovery 61.67 percent" in txt(pg, "[data-class='UNSECURED']"), txt(pg, "[data-class='UNSECURED']"))
check("every cent is allocated and matches an independent calculation", all(f"dividend {money(s)}" in txt(pg, f"[data-dividend='{no}']") for no, s in zip((3, 4, 5), sh)) and sum(sh) == 370000_00, [txt(pg, f"[data-dividend='{n}']") for n in (3, 4, 5)])
check("the person who proposed the case could not record it, but another can", pg.locator("#isv-ds-save").count() == 1)
pg.click("#isv-ds-save"); pg.wait_for_timeout(1500)
check("the distribution is recorded and nobody is paid by ASAVEXA", "#1 on" in txt(pg, "[data-distribution='1']") and "950000.00 recorded as distributed" in txt(pg, "[data-distribution='1']") and "available 0.00" in txt(pg, "#isv-funds") and "already distributed 950000.00" in txt(pg, "#isv-funds"), txt(pg, "#isv-distributions") + err(pg))
check("what is still owed falls", "still owed 0.00" in txt(pg, "[data-claim='1']") and "paid 80000.00, still owed 0.00" in txt(pg, "[data-claim='2']"), txt(pg, "#isv-claims"))
check("a second record with nothing to distribute is refused", st(A("POST", f"/cases/{c1}/distribution", DARA, {})) == 409)

# ---- overview (browser user is the owner); a later realisation is distributed through the server ----
sign_in(pg, *DARA, "Meridian")
en(TUNDE, c1, amt="100000.00", description="Sale of the vehicles"); A("POST", f"/cases/{c1}/entries/3/confirm", KWAME, {}); r = A("POST", f"/cases/{c1}/distribution", KWAME, {"note": "Second distribution"})
check("a later distribution pays only what is still owed", len(r["distributions"]) == 2 and r["distributions"][1]["total"] == "100000.00" and r["waterfall"]["total_owed"] == "130000.01", r.get("distributions"))
check("the approver closes the case", st(A("POST", f"/cases/{c1}/close", KWAME, {"reason": "The estate has been wound up"})) == "CLOSED")
check("a closed case takes nothing more", st(ck(TUNDE, c1, "SUP-Z", "UNSECURED", "5")) == 409 and st(en(TUNDE, c1)) == 409)
mk(TUNDE, title="Waiting estate", claims_deadline=None, currency="NGN")
goto(pg, "/insolvency"); tab(pg, "overview")
check("the counts add up", all(s in txt(pg, "#isv-counts") for s in ("Waiting for a decision: 1", "Open: 1", "Closed: 1", "Rejected: 0")), txt(pg, "#isv-counts"))
check("totals are exact and per currency", "admitted 1180000.01, distributed 1050000.00" in txt(pg, "[data-currency='NGN']") and "USD: 1 case(s), admitted 0.00, distributed 0.00" in txt(pg, "[data-currency='USD']"), txt(pg, "#isv-totals"))
at = txt(pg, "#isv-attention").upper()
check("cases to approve, claims to decide and late claims need attention", all(s in at for s in ("CASES TO APPROVE", "CLAIMS TO DECIDE", "LATE CLAIMS")), at)

# ---- isolation and audit ----
check("the other company sees none of it", A("GET", "/cases", OTHER, org="Other") == [])
check("the other company cannot read or act on a case", st(A("GET", f"/cases/{c1}", OTHER, org="Other")) == 404 and st(A("POST", f"/cases/{c2}/distribution", OTHER, {}, org="Other")) == 404)
check("the other company's overview is empty", A("GET", "/overview", OTHER, org="Other")["totals"] == [])
acts = api("GET", "/_audit", KWAME, "Meridian")["actions"]
for a_ in ("INSOLVENCY_CASE_PROPOSED", "INSOLVENCY_CASE_APPROVED", "INSOLVENCY_CASE_CLOSED", "INSOLVENCY_CLAIM_LODGED", "INSOLVENCY_CLAIM_ADMITTED", "INSOLVENCY_CLAIM_REJECTED", "INSOLVENCY_ENTRY_RECORDED", "INSOLVENCY_ENTRY_CONFIRMED", "INSOLVENCY_DISTRIBUTION_RECORDED"):
    check(f"the audit trail has {a_}", a_ in acts, [x for x in acts if "INSOLVENCY" in x])
aud = str(api("GET", "/_audit", KWAME, "Meridian"))
check("no typed content is copied into the audit trail", all(s not in aud for s in ("Acme", "textile", "BANK-1", "TAX-1", "SUP-", "LATE-1", "500000", "1000000", "Sale of the", "No proof of debt", "Appointment documents", "wound up", "Second distribution")))
check("no page errors in the browser", not errs, errs[:3])
finish(p, b)
