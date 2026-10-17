"""Browser journey: Mergers and acquisitions (Stage 39). Run via e2e/run_all.py. The browser user and the user making API calls are always different people."""
from datetime import datetime, timedelta, timezone

from common import *

TODAY = datetime.now(timezone.utc).date()
D = lambda n: (TODAY + timedelta(days=n)).isoformat()
def hrefs(pg): return [a.get_attribute("href") for a in pg.locator(".app-sidebar a").all()]
def tab(pg, name):
    pg.wait_for_selector(f"#ma-tab-{name}"); pg.click(f"#ma-tab-{name}"); pg.wait_for_timeout(1200)
def body(pg): return pg.inner_text("body")
def err(pg): return txt(pg, ".alert-error")
def A(m, path, who, bodyj=None, org="Meridian"): return api(m, "/mergers" + path, who, org, bodyj)
def st(r): return r.get("status") if isinstance(r, dict) else None
def did(ref, who): return next(i["id"] for i in A("GET", "/deals", who) if i["ref"] == ref)
def fill(pg, **ids):
    for k, v in ids.items(): pg.fill("#" + k.replace("_", "-"), v)
def opn(pg, ref):
    pg.wait_for_selector(f"#ma-dl-open-{ref}", timeout=8000)
    if pg.locator("#ma-deal-detail").count() and ref in txt(pg, "#ma-deal-detail h3"): return
    pg.click(f"#ma-dl-open-{ref}"); pg.wait_for_timeout(900)
def mk(who, **kw):
    d = dict(name="Project Heron", deal_ref="HERON", currency="USD", deal_type="DISPOSAL", base_price="500.50", target_close_date=D(-10), description="Disposal of a regional business unit"); d.update(kw); return A("POST", "/deals", who, d)
def adj(who, s, **kw):
    d = dict(kind="INCREASE", amount="10.25", basis="Inventory above the agreed level"); d.update(kw); return A("POST", f"/deals/{s}/adjustments", who, d)

start_web()
p, b, pg, errs = session()

# ---- an accountant has no business here ----
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/mergers")
check("the menu does not offer the workspace to an accountant", "#/mergers" not in hrefs(pg), hrefs(pg))
check("typing the address shows no content", "Propose a deal" not in body(pg), body(pg)[:200])
check("the server refuses an accountant (overview)", st(A("GET", "/overview", AISHA)) == 403)
check("the server refuses an accountant (deals)", st(A("GET", "/deals", AISHA)) == 403)

# ---- Tunde proposes a deal ----
sign_in(pg, *TUNDE, "Meridian"); goto(pg, "/mergers")
check("the menu offers the workspace", "#/mergers" in hrefs(pg), hrefs(pg))
check("the banner says it values nothing and gives no advice", "values nothing" in txt(pg, "#ma-banner") and "no deal, tax or legal advice" in txt(pg, "#ma-banner"), txt(pg, "#ma-banner"))
check("nothing needs attention yet", "Nothing needs attention" in txt(pg, "#ma-attention"), txt(pg, "#ma-attention"))
tab(pg, "deals")
pg.click("#ma-dl-save"); pg.wait_for_timeout(300)
check("an empty form is stopped with a plain sentence", "name" in txt(pg, "#deal-problem").lower(), txt(pg, "#deal-problem"))
fill(pg, ma_dl_name="Project Falcon", ma_dl_ref="FALCON", ma_dl_cur="ngn", ma_dl_price="0", ma_dl_target=D(120), ma_dl_desc="Acquisition of a distribution business"); pg.click("#ma-dl-save"); pg.wait_for_timeout(300)
check("a zero price is stopped", "more than zero" in txt(pg, "#deal-problem"), txt(pg, "#deal-problem"))
fill(pg, ma_dl_price="1.234"); pg.click("#ma-dl-save"); pg.wait_for_timeout(300)
check("a price with three decimals is stopped", "price" in txt(pg, "#deal-problem").lower(), txt(pg, "#deal-problem"))
fill(pg, ma_dl_price="1,000,000", ma_dl_target="2101-01-01"); pg.click("#ma-dl-save"); pg.wait_for_timeout(300)
check("a target date outside 2000 to 2100 is stopped", "between 2000" in txt(pg, "#deal-problem"), txt(pg, "#deal-problem"))
fill(pg, ma_dl_target=D(120)); pg.click("#ma-dl-save"); pg.wait_for_timeout(1500)
check("the deal is numbered and waits", "MD-001" in txt(pg, "[data-deal='MD-001']") and "Waiting for a decision" in txt(pg, "[data-deal='MD-001']") and "base price 1000000.00" in txt(pg, "[data-deal='MD-001']"), txt(pg, "#ma-notice") + err(pg))
opn(pg, "MD-001"); s1 = did("MD-001", DARA)
check("records are not offered before approval", pg.locator("#ma-ck-save").count() == 0 and st(A("POST", f"/deals/{s1}/checklist", DARA, {"title": "Contracts reviewed", "area": "LEGAL"})) == 409)
check("the proposer sees no approve button", pg.locator("#ma-dl-approve").count() == 0)
check("the proposer cannot approve through the server", st(A("POST", f"/deals/{s1}/approve", TUNDE, {})) == 403)

# ---- the owner proposes more; the approver decides some (browser user is Tunde) ----
s2 = mk(DARA)["id"]; s3 = mk(DARA, name="Duplicate deal", deal_ref="HERON-2")["id"]; s4 = mk(DARA, name="Project Osprey", deal_ref="OSPREY", target_close_date=D(60))["id"]
check("the owner cannot approve or reject their own deal", st(A("POST", f"/deals/{s2}/approve", DARA, {})) == 403 and st(A("POST", f"/deals/{s2}/reject", DARA, {"reason": "Rejecting my own deal"})) == 403)
check("a zero price is refused", st(mk(DARA, base_price="0")) == 400)
check("a float price is refused", st(mk(DARA, base_price=5.5)) == 400)
check("a bad deal type is refused", st(mk(DARA, deal_type="SWAP")) == 400)
check("a bad currency is refused", st(mk(DARA, currency="NG")) == 400)
check("the approver approves two and rejects one", st(A("POST", f"/deals/{s2}/approve", KWAME, {"note": "Board minute seen"})) == "APPROVED" and st(A("POST", f"/deals/{s4}/approve", KWAME, {})) == "APPROVED" and st(A("POST", f"/deals/{s3}/reject", KWAME, {"reason": "Duplicate of another deal"})) == "REJECTED")
check("a rejected deal takes no records", st(adj(DARA, s3)) == 409)
check("a bad adjustment kind is refused", st(adj(DARA, s2, kind="UP")) == 400)
check("a zero adjustment is refused", st(adj(DARA, s2, amount="0")) == 400)
check("a float adjustment is refused", st(adj(DARA, s2, amount=5.5)) == 400)
check("a short basis is refused", st(adj(DARA, s2, basis="short")) == 400)
r = adj(DARA, s2); check("an adjustment is numbered and waits", r["adjustments"][0]["status"] == "PROPOSED" and r["adjusted_price"] == "500.50", r)
check("the owner cannot confirm their own adjustment", st(A("POST", f"/deals/{s2}/adjustments/1/confirm", DARA, {})) == 403)
x = A("POST", f"/deals/{s2}/adjustments/1/confirm", KWAME, {})
check("a confirmed adjustment gives an exact adjusted price and percentage", (x["adjusted_price"], x["price_change"], x["price_change_pct"]) == ("510.75", "10.25", "2.05"), x)
adj(DARA, s2, kind="DECREASE", amount="9999")
check("an adjustment that would take the price below zero cannot be confirmed", st(A("POST", f"/deals/{s2}/adjustments/2/confirm", KWAME, {})) == 409)
check("it can be rejected with a reason", A("POST", f"/deals/{s2}/adjustments/2/reject", KWAME, {"reason": "Amount was entered wrongly"})["adjustments"][1]["status"] == "REJECTED")
check("a deal with nothing outstanding can be completed", A("POST", f"/deals/{s4}/close", KWAME, {"outcome": "COMPLETED", "reason": "The deal has closed"})["outcome"] == "COMPLETED")

# ---- Kwame approves the first deal ----
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/mergers"); tab(pg, "deals"); opn(pg, "MD-001")
check("the approver sees the decision buttons but no proposing form", pg.locator("#ma-dl-approve").count() == 1 and pg.locator("#ma-dl-save").count() == 0)
pg.click("#ma-dl-reject"); pg.wait_for_timeout(400)
check("rejecting without a reason is stopped", "10 characters" in err(pg) or "reason" in err(pg).lower(), err(pg))
pg.fill("#ma-dl-note", "ok"); pg.click("#ma-dl-approve"); pg.wait_for_timeout(400)
check("a short approval note is stopped", "10 characters" in err(pg) or "note" in err(pg).lower(), err(pg))
pg.fill("#ma-dl-note", ""); pg.click("#ma-dl-approve"); pg.wait_for_timeout(1500)
check("a different person approves it", "Open" in txt(pg, "[data-deal='MD-001']") and pg.locator("#ma-dl-approve").count() == 0, txt(pg, "[data-deal='MD-001']") + err(pg))
check("with nothing confirmed the price is the base price and the checklist is empty", "Adjusted price 1000000.00 NGN" in txt(pg, "#ma-price") and "Checklist: no items yet" in txt(pg, "#ma-progress"), txt(pg, "#ma-position"))
check("an approved deal cannot be decided again", st(A("POST", f"/deals/{s1}/reject", DARA, {"reason": "Trying to reject it later"})) == 409)

# ---- Tunde records on the first deal ----
sign_in(pg, *TUNDE, "Meridian"); goto(pg, "/mergers"); tab(pg, "deals"); opn(pg, "MD-001")
pg.click("#ma-ck-save"); pg.wait_for_timeout(300)
check("an empty checklist item is stopped", bool(txt(pg, "#checklist-problem")), txt(pg, "#checklist-problem"))
fill(pg, ma_ck_title="Audited accounts reviewed"); pg.click("#ma-ck-save"); pg.wait_for_timeout(1500)
check("the checklist item is added and open", "Audited accounts reviewed" in txt(pg, "[data-row='checklist-1']") and "Open" in txt(pg, "[data-row='checklist-1']"), txt(pg, "#ma-checklist") + err(pg))
pg.select_option("#ma-ck-area", "LEGAL"); fill(pg, ma_ck_title="Contracts reviewed"); pg.click("#ma-ck-save"); pg.wait_for_timeout(1500)
check("a second item in another area is added", "Contracts reviewed" in txt(pg, "[data-row='checklist-2']"), txt(pg, "#ma-checklist") + err(pg))
pg.select_option("#ma-ck-area", "LEGAL"); fill(pg, ma_ck_title="Contracts reviewed"); pg.click("#ma-ck-save"); pg.wait_for_timeout(1200)
check("the same item twice is refused", bool(err(pg)), err(pg))
fill(pg, ma_cn_title="Regulator consent received", ma_cn_due="2026-02-30"); pg.click("#ma-cn-save"); pg.wait_for_timeout(300)
check("a bad due date is stopped", "real date" in txt(pg, "#condition-problem"), txt(pg, "#condition-problem"))
fill(pg, ma_cn_due=D(10)); pg.click("#ma-cn-save"); pg.wait_for_timeout(1500)
check("the condition is added and due soon", "Regulator consent received" in txt(pg, "[data-row='conditions-1']") and "Due soon" in txt(pg, "[data-row='conditions-1']"), txt(pg, "#ma-conditions") + err(pg))
fill(pg, ma_cn_title="Board approval obtained", ma_cn_due=D(-2)); pg.click("#ma-cn-save"); pg.wait_for_timeout(1500)
check("a condition past its date is overdue", "Overdue" in txt(pg, "[data-row='conditions-2']"), txt(pg, "#ma-conditions") + err(pg))
pg.select_option("#ma-ad-kind", "DECREASE"); fill(pg, ma_ad_amount="0", ma_ad_basis="Working capital shortfall found"); pg.click("#ma-ad-save"); pg.wait_for_timeout(300)
check("a zero adjustment is stopped", "more than zero" in txt(pg, "#adjustment-problem"), txt(pg, "#adjustment-problem"))
fill(pg, ma_ad_amount="50,000.50"); pg.click("#ma-ad-save"); pg.wait_for_timeout(1500)
check("the adjustment is recorded and waits", "50000.50" in txt(pg, "[data-row='adjustments-1']") and "Waiting for a decision" in txt(pg, "[data-row='adjustments-1']"), txt(pg, "#ma-adjustments") + err(pg))
pg.click("#ma-checklist-1-done"); pg.wait_for_timeout(300)
check("marking with nothing typed is stopped", bool(txt(pg, "#done-checklist-1-problem")), txt(pg, "#done-checklist-1-problem"))
fill(pg, ma_checklist_1_date=D(-1), ma_checklist_1_text="Signed accounts received"); pg.click("#ma-checklist-1-done"); pg.wait_for_timeout(1500)
check("the item is marked and waits for confirmation", "Marked, waiting for confirmation" in txt(pg, "[data-row='checklist-1']"), txt(pg, "#ma-checklist") + err(pg))
check("an administrator sees no confirm button and no close button", pg.locator("#ma-checklist-1-confirm").count() == 0 and pg.locator("#ma-cl-save").count() == 0)

# ---- Kwame decides ----
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/mergers"); tab(pg, "deals"); opn(pg, "MD-001")
check("closing is not offered while items wait", pg.locator("#ma-cl-save").count() == 0 and st(A("POST", f"/deals/{s1}/close", DARA, {"outcome": "ABANDONED", "reason": "Closing while items wait"})) == 409)
pg.click("#ma-adjustments-1-reject"); pg.wait_for_timeout(400)
check("rejecting without a reason is stopped", "10 characters" in err(pg) or "reason" in err(pg).lower(), err(pg))
pg.fill("#ma-adjustments-1-note", "short"); pg.click("#ma-adjustments-1-confirm"); pg.wait_for_timeout(400)
check("a short confirmation note is stopped", "10 characters" in err(pg) or "note" in err(pg).lower(), err(pg))
pg.fill("#ma-adjustments-1-note", ""); pg.click("#ma-adjustments-1-confirm"); pg.wait_for_timeout(1500)
check("a different person confirms the adjustment", "Confirmed" in txt(pg, "[data-row='adjustments-1']") and pg.locator("#ma-adjustments-1-confirm").count() == 0, txt(pg, "#ma-adjustments") + err(pg))
check("the adjusted price is exact", "Adjusted price 949999.50 NGN (change -50000.50, -5.00 percent" in txt(pg, "#ma-price"), txt(pg, "#ma-price"))
pg.fill("#ma-checklist-1-note", "The accounts were unsigned"); pg.click("#ma-checklist-1-reject"); pg.wait_for_timeout(1500)
check("sending an item back opens it again with the reason kept", "Open" in txt(pg, "[data-row='checklist-1']") and "The accounts were unsigned" in txt(pg, "[data-row='checklist-1']"), txt(pg, "#ma-checklist") + err(pg))
x = A("POST", f"/deals/{s1}/checklist/1/provide", DARA, {"done_on": D(-1), "note": "Signed accounts received"})
check("the person who marked it cannot confirm it", st(A("POST", f"/deals/{s1}/checklist/1/confirm", DARA, {})) == 403)
pg.reload(); pg.wait_for_timeout(1500); tab(pg, "deals"); opn(pg, "MD-001")
pg.click("#ma-checklist-1-confirm"); pg.wait_for_timeout(1500)
check("a different person confirms the item and progress is exact", "Checklist: 1 of 2 confirmed (50.00 percent)" in txt(pg, "#ma-progress") and "Financial: 1 of 1 confirmed" in txt(pg, "#ma-areas") and "Legal: 0 of 1 confirmed" in txt(pg, "#ma-areas"), txt(pg, "#ma-progress") + err(pg))
check("a decided item cannot be decided again", st(A("POST", f"/deals/{s1}/checklist/1/reject", DARA, {"reason": "Trying to reject it later"})) == 409)
pg.select_option("#ma-cl-outcome", "COMPLETED"); pg.fill("#ma-cl-note", "The deal has closed"); pg.click("#ma-cl-save"); pg.wait_for_timeout(1500)
check("a deal cannot be completed while an item or condition is unconfirmed", "completed only when every" in err(pg), err(pg))
pg.select_option("#ma-cl-outcome", "ABANDONED"); pg.fill("#ma-cl-note", "short"); pg.click("#ma-cl-save"); pg.wait_for_timeout(400)
check("closing without a proper reason is stopped", "10 characters" in err(pg) or "reason" in err(pg).lower(), err(pg))
pg.fill("#ma-cl-note", "Talks have ended"); pg.click("#ma-cl-save"); pg.wait_for_timeout(1500)
check("the deal is closed as abandoned with its reason", "Closed" in txt(pg, "[data-deal='MD-001']") and "Closed as abandoned: Talks have ended" in txt(pg, "#ma-closed"), txt(pg, "[data-deal='MD-001']") + err(pg))
check("a closed deal takes no more records", st(adj(DARA, s1)) == 409 and st(A("POST", f"/deals/{s1}/checklist", DARA, {"title": "Another item", "area": "TAX"})) == 409)

# ---- overview (browser user is the owner) ----
mk(TUNDE, name="Waiting deal", deal_ref="WAIT-1")
sign_in(pg, *DARA, "Meridian"); goto(pg, "/mergers"); tab(pg, "overview")
cn = txt(pg, "#ma-counts")
check("the counts add up", all(s in cn for s in ("Waiting for a decision: 1", "Open: 1", "Rejected: 1", "Closed: 2", "Closed as completed: 1; abandoned: 1")), cn)
cur = txt(pg, "#ma-currency")
check("open deals are shown per currency with the exact adjusted price", "USD: 1 deal(s), base price 500.50, adjusted price 510.75" in cur and "NGN" not in cur, cur)
at = txt(pg, "#ma-attention").upper()
check("a deal to approve and a passed target date need attention", "DEALS TO APPROVE" in at and "TARGET DATE PASSED" in at, at)
pg.fill("#ma-set-due_soon_days", "abc"); pg.click("#ma-set-save"); pg.wait_for_timeout(400)
check("a bad setting is stopped", "1 to 365" in txt(pg, "#setting-problem"), txt(pg, "#setting-problem"))
pg.fill("#ma-set-due_soon_days", "30"); pg.click("#ma-set-save"); pg.wait_for_timeout(1500)
check("the setting is saved", "within 30 day(s)" in txt(pg, "#ma-setting-meaning"), txt(pg, "#ma-setting-meaning"))
check("an administrator cannot change the setting", st(A("PUT", "/setting", TUNDE, {"due_soon_days": 3})) == 403)

# ---- isolation and audit ----
check("the other company sees none of it", A("GET", "/deals", OTHER, org="Other") == [])
check("the other company cannot read or act on a deal", st(A("GET", f"/deals/{s2}", OTHER, org="Other")) == 404 and st(A("POST", f"/deals/{s2}/adjustments/1/confirm", OTHER, {}, org="Other")) == 404)
check("the other company's overview is empty", A("GET", "/overview", OTHER, org="Other")["counts"]["approved"] == 0)
acts = api("GET", "/_audit", KWAME, "Meridian")["actions"]
for a_ in ("MERGERS_DEAL_PROPOSED", "MERGERS_DEAL_APPROVED", "MERGERS_DEAL_REJECTED", "MERGERS_DEAL_CLOSED", "MERGERS_CHECKLIST_ADDED", "MERGERS_CHECKLIST_PROVIDED", "MERGERS_CHECKLIST_CONFIRMED", "MERGERS_CHECKLIST_REJECTED", "MERGERS_CONDITION_ADDED", "MERGERS_ADJUSTMENT_ADDED", "MERGERS_ADJUSTMENT_CONFIRMED", "MERGERS_SETTING_SET"):
    check(f"the audit trail has {a_}", a_ in acts, [x for x in acts if "MERGERS" in x])
aud = str(api("GET", "/_audit", KWAME, "Meridian"))
check("no typed content is copied into the audit trail", all(s not in aud for s in ("Falcon", "FALCON", "Heron", "Osprey", "Audited accounts", "Regulator consent", "Signed accounts", "unsigned", "Duplicate of", "Talks have ended", "Board minute", "50000", "1000000")))
check("no page errors in the browser", not errs, errs[:3])
finish(p, b)
