"""Browser journey: Data governance (Stage 33). Run via e2e/run_all.py. The browser user and the user making API calls are always different people."""
from datetime import datetime, timedelta, timezone

from common import *

TODAY = datetime.now(timezone.utc).date()
D = lambda n: (TODAY + timedelta(days=n)).isoformat()
def hrefs(pg): return [a.get_attribute("href") for a in pg.locator(".app-sidebar a").all()]
def tab(pg, name):
    pg.wait_for_selector(f"#dg-tab-{name}"); pg.click(f"#dg-tab-{name}"); pg.wait_for_timeout(1200)
def body(pg): return pg.inner_text("body")
def err(pg): return txt(pg, ".alert-error")
def A(m, path, who, bodyj=None, org="Meridian"): return api(m, "/datagov" + path, who, org, bodyj)
def st(r): return r.get("status") if isinstance(r, dict) else None
def aid(ref, who): return next(i["id"] for i in A("GET", "/assets", who) if i["ref"] == ref)
def fill(pg, **ids):
    for k, v in ids.items(): pg.fill("#" + k.replace("_", "-"), v)
def opn(pg, ref):
    pg.wait_for_selector(f"#dg-as-open-{ref}", timeout=8000)
    if pg.locator("#dg-asset-detail").count() and ref in txt(pg, "#dg-asset-detail h3"): return
    pg.click(f"#dg-as-open-{ref}"); pg.wait_for_timeout(900)
def mk(who, **kw):
    d = dict(name="Payroll archive", owner_ref="HR-LEAD", classification="RESTRICTED", personal_data="YES", retention_months=120, review_every_months=12, description="Archived payroll files of former staff"); d.update(kw); return A("POST", "/assets", who, d)
def gr(who, a, **kw):
    d = dict(person_ref="STAFF-021", access_level="READ", purpose="Answer an audit query on payroll", starts_on=D(-1), expires_on=D(20)); d.update(kw); return A("POST", f"/assets/{a}/grants", who, d)

start_web()
p, b, pg, errs = session()

# ---- an accountant has no business here ----
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/datagov")
check("the menu does not offer the workspace to an accountant", "#/datagov" not in hrefs(pg), hrefs(pg))
check("typing the address shows no content", "Propose a data asset" not in body(pg), body(pg)[:200])
check("the server refuses an accountant (overview)", st(A("GET", "/overview", AISHA)) == 403)
check("the server refuses an accountant (assets)", st(A("GET", "/assets", AISHA)) == 403)

# ---- Tunde proposes an asset ----
sign_in(pg, *TUNDE, "Meridian"); goto(pg, "/datagov")
check("the menu offers the workspace", "#/datagov" in hrefs(pg), hrefs(pg))
check("the banner says it holds no data and enforces no access", "holds none of the data" in txt(pg, "#dg-banner") and "enforces no access" in txt(pg, "#dg-banner"), txt(pg, "#dg-banner"))
check("nothing needs attention yet", "Nothing needs attention" in txt(pg, "#dg-attention"), txt(pg, "#dg-attention"))
tab(pg, "assets")
pg.click("#dg-as-save"); pg.wait_for_timeout(300)
check("an empty form is stopped with a plain sentence", "name" in txt(pg, "#asset-problem").lower(), txt(pg, "#asset-problem"))
fill(pg, dg_as_name="Customer ledger extracts", dg_as_owner="FIN-LEAD", dg_as_ret="0", dg_as_rev="6", dg_as_desc="Monthly extracts of the customer ledger"); pg.select_option("#dg-as-class", "CONFIDENTIAL"); pg.select_option("#dg-as-pd", "YES"); pg.click("#dg-as-save"); pg.wait_for_timeout(300)
check("a zero retention period is stopped", "retention" in txt(pg, "#asset-problem").lower(), txt(pg, "#asset-problem"))
fill(pg, dg_as_ret="84", dg_as_rev="61"); pg.click("#dg-as-save"); pg.wait_for_timeout(300)
check("a review interval over 60 months is stopped", "interval" in txt(pg, "#asset-problem").lower(), txt(pg, "#asset-problem"))
fill(pg, dg_as_rev="6"); pg.click("#dg-as-save"); pg.wait_for_timeout(1500)
check("the asset is numbered and waits", "DA-001" in txt(pg, "[data-asset='DA-001']") and "Waiting for a decision" in txt(pg, "[data-asset='DA-001']") and "personal data: yes" in txt(pg, "[data-asset='DA-001']"), txt(pg, "#dg-notice") + err(pg))
opn(pg, "DA-001"); a1 = aid("DA-001", DARA)
check("nothing can be added to an unapproved asset", pg.locator("#dg-rv-save").count() == 0 and pg.locator("#dg-gr-save").count() == 0 and st(gr(DARA, a1)) == 409)
check("the proposer sees no approve button, only the reason", pg.locator("#dg-as-approve").count() == 0 and pg.locator("#dg-as-waiting").count() == 0, "")
check("the proposer cannot approve through the server", st(A("POST", f"/assets/{a1}/approve", TUNDE, {})) == 403)

# ---- the owner proposes more assets; the approver decides (browser user is Tunde / Kwame) ----
a2 = mk(DARA)["id"]; a3 = mk(DARA, name="Public price list", classification="PUBLIC", personal_data="NO", retention_months=12, review_every_months=6, description="The published price list of products")["id"]; a4 = mk(DARA, name="Duplicate ledger copy", classification="INTERNAL", description="A copy of the customer ledger asset")["id"]
check("the owner cannot approve their own asset", st(A("POST", f"/assets/{a2}/approve", DARA, {})) == 403 and st(A("POST", f"/assets/{a2}/reject", DARA, {"reason": "Rejecting my own asset"})) == 403)
check("an administrator cannot approve (no approve permission)", st(A("POST", f"/assets/{a2}/approve", TUNDE, {})) == 403)
check("a float retention period is refused", st(mk(DARA, retention_months=12.5)) == 400)
check("the approver approves two and rejects one", st(A("POST", f"/assets/{a2}/approve", KWAME, {})) == "APPROVED" and st(A("POST", f"/assets/{a3}/approve", KWAME, {"note": "Public page checked"})) == "APPROVED" and st(A("POST", f"/assets/{a4}/reject", KWAME, {"reason": "Duplicate of the ledger asset"})) == "REJECTED")

sign_in(pg, *KWAME, "Meridian"); goto(pg, "/datagov"); tab(pg, "assets"); opn(pg, "DA-001")
check("the approver sees the decision buttons but no editing", pg.locator("#dg-as-approve").count() == 1 and pg.locator("#dg-as-save").count() == 0 and pg.locator("#dg-rv-save").count() == 0)
pg.click("#dg-as-reject"); pg.wait_for_timeout(400)
check("rejecting without a reason is stopped", "10 characters" in err(pg) or "reason" in err(pg).lower(), err(pg))
pg.fill("#dg-as-note", "ok"); pg.click("#dg-as-approve"); pg.wait_for_timeout(400)
check("a short approval note is stopped", "10 characters" in err(pg) or "note" in err(pg).lower(), err(pg))
pg.fill("#dg-as-note", ""); pg.click("#dg-as-approve"); pg.wait_for_timeout(1500)
check("a different person approves it", "Approved" in txt(pg, "[data-asset='DA-001']") and pg.locator("#dg-as-approve").count() == 0 and "next review due" in txt(pg, "#dg-asset-facts"), txt(pg, "[data-asset='DA-001']") + err(pg))
check("an approved asset cannot be decided again", st(A("POST", f"/assets/{a1}/reject", DARA, {"reason": "Trying to reject it later"})) == 409)

# ---- Tunde records a review and proposes grants ----
sign_in(pg, *TUNDE, "Meridian"); goto(pg, "/datagov"); tab(pg, "assets"); opn(pg, "DA-001")
pg.click("#dg-rv-save"); pg.wait_for_timeout(300)
check("an empty review is stopped", bool(txt(pg, "#review-problem")), txt(pg, "#review-problem"))
fill(pg, dg_rv_date=D(5), dg_rv_out="The owner confirmed the data is needed"); pg.click("#dg-rv-save"); pg.wait_for_timeout(300)
check("a future review date is stopped by the server", "future" in err(pg).lower() or "future" in txt(pg, "#review-problem").lower(), err(pg) + txt(pg, "#review-problem"))
fill(pg, dg_rv_date=D(0)); pg.click("#dg-rv-save"); pg.wait_for_timeout(1500)
check("the review is recorded and waits", "Waiting for a decision" in txt(pg, "[data-review='1']") and "owner confirmed" in txt(pg, "[data-review='1']"), txt(pg, "#dg-reviews") + err(pg))
fill(pg, dg_gr_person="STAFF-017", dg_gr_purpose="Prepare the quarterly reconciliation", dg_gr_start=D(-1), dg_gr_end=D(-2)); pg.click("#dg-gr-save"); pg.wait_for_timeout(300)
check("an expiry before the start is stopped", "before the start" in txt(pg, "#grant-problem"), txt(pg, "#grant-problem"))
fill(pg, dg_gr_end=D(15)); pg.click("#dg-gr-save"); pg.wait_for_timeout(1500)
check("the grant is recorded and waits", "STAFF-017" in txt(pg, "[data-grant='1']") and "Waiting for a decision" in txt(pg, "[data-grant='1']"), txt(pg, "#dg-grants") + err(pg))
pg.click("#dg-gr-save"); pg.wait_for_timeout(1200)
check("a duplicate grant is refused", bool(err(pg)) or bool(txt(pg, "#grant-problem")), err(pg) + txt(pg, "#grant-problem"))
check("an administrator sees no approve buttons", pg.locator("#dg-gr-1-approve").count() == 0 and pg.locator("#dg-rv-1-confirm").count() == 0)
check("retiring is not offered while something waits", pg.locator("#dg-rt-save").count() == 0)
check("the server refuses to retire", st(A("POST", f"/assets/{a1}/retire", KWAME, {"reason": "Retiring while things wait"})) == 409)
# the rest through the server as the owner
check("an over-long grant is refused", st(gr(DARA, a2, starts_on=D(0), expires_on=D(400))) == 400)   # restricted: one year at most
check("a grant already past is refused", st(gr(DARA, a2, starts_on=D(-30), expires_on=D(-3))) == 400)
g2 = gr(DARA, a2); check("a grant on the restricted asset is numbered", g2["grants"][0]["no"] == 1, g2)
check("the owner cannot decide their own grant or review", st(A("POST", f"/assets/{a2}/grants/1/approve", DARA, {})) == 403 and st(A("POST", f"/assets/{a1}/reviews/1/confirm", TUNDE, {})) == 403)

# ---- Kwame decides ----
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/datagov"); tab(pg, "assets"); opn(pg, "DA-001")
pg.click("#dg-rv-1-reject"); pg.wait_for_timeout(400)
check("rejecting a review without a reason is stopped", "10 characters" in err(pg) or "reason" in err(pg).lower(), err(pg))
pg.click("#dg-rv-1-confirm"); pg.wait_for_timeout(1500)
check("a different person confirms the review", "Confirmed" in txt(pg, "[data-review='1']") and pg.locator("#dg-rv-1-confirm").count() == 0, txt(pg, "#dg-reviews") + err(pg))
pg.click("#dg-gr-1-approve"); pg.wait_for_timeout(1500)
check("a different person approves the grant", "Expiring soon" in txt(pg, "[data-grant='1']") or "Active" in txt(pg, "[data-grant='1']"), txt(pg, "#dg-grants") + err(pg))
check("the days left are shown", "day(s) left" in txt(pg, "[data-grant='1']"), txt(pg, "[data-grant='1']"))
check("a second grant to the same person and level is refused", st(gr(DARA, a1, person_ref="STAFF-017", purpose="Prepare the quarterly reconciliation", starts_on=D(0), expires_on=D(30))) == 409)
g3 = gr(DARA, a1, person_ref="STAFF-018", purpose="Weekend support cover work")
pg.click("#dg-gr-save") if False else None
goto(pg, "/datagov"); tab(pg, "assets"); opn(pg, "DA-001")
pg.fill("#dg-gr-2-note", "no"); pg.click("#dg-gr-2-reject"); pg.wait_for_timeout(400)
check("rejecting a grant without a reason is stopped", "10 characters" in err(pg) or "reason" in err(pg).lower(), err(pg))
pg.fill("#dg-gr-2-note", "Not needed for the weekend"); pg.click("#dg-gr-2-reject"); pg.wait_for_timeout(1500)
check("a different person rejects a grant with a reason", "Rejected" in txt(pg, "[data-grant='2']") and "Not needed for the weekend" in txt(pg, "[data-grant='2']"), txt(pg, "#dg-grants") + err(pg))
check("retiring is blocked while a grant is active", pg.locator("#dg-rt-save").count() == 0 and st(A("POST", f"/assets/{a1}/retire", DARA, {"reason": "Retiring while active"})) == 409)
pg.fill("#dg-gr-1-note", "short"); pg.click("#dg-gr-1-revoke"); pg.wait_for_timeout(400)
check("revoking without a proper reason is stopped", "10 characters" in err(pg) or "reason" in err(pg).lower(), err(pg))
pg.fill("#dg-gr-1-note", "Moved to another team"); pg.click("#dg-gr-1-revoke"); pg.wait_for_timeout(1500)
check("the grant is revoked and keeps its reason", "Revoked" in txt(pg, "[data-grant='1']") and "Moved to another team" in txt(pg, "[data-grant='1']"), txt(pg, "#dg-grants") + err(pg))
check("a revoked grant cannot be revoked again", st(A("POST", f"/assets/{a1}/grants/1/revoke", DARA, {"reason": "Revoking it a second time"})) == 409)
# a not-yet-started approved grant still blocks retiring (defect found by the Stage 33 tests)
gf = gr(TUNDE, a3, person_ref="STAFF-040", starts_on=D(10), expires_on=D(60)); A("POST", f"/assets/{a3}/grants/1/approve", DARA, {})
check("an approved grant that has not started yet still blocks retiring", st(A("POST", f"/assets/{a3}/retire", DARA, {"reason": "Retiring with a future grant"})) == 409)
A("POST", f"/assets/{a3}/grants/1/revoke", DARA, {"reason": "Not needed after all"})
goto(pg, "/datagov"); tab(pg, "assets"); opn(pg, "DA-001")
check("with nothing waiting or active, retiring is offered", pg.locator("#dg-rt-save").count() == 1)
pg.fill("#dg-rt-note", "short"); pg.click("#dg-rt-save"); pg.wait_for_timeout(400)
check("retiring without a proper reason is stopped", "10 characters" in err(pg) or "reason" in err(pg).lower(), err(pg))

# ---- flags and overview (restricted asset with grants); the browser is the owner, the API users are the approver and the administrator ----
sign_in(pg, *DARA, "Meridian")
A("PUT", "/setting", KWAME, {"expiry_warning_days": 30, "max_restricted_grants": 1})
for who in ("STAFF-031", "STAFF-032"): gr(TUNDE, a2, person_ref=who, starts_on=D(-1), expires_on=D(100))
for n in (1, 2, 3): A("POST", f"/assets/{a2}/grants/{n}/approve", KWAME, {})
goto(pg, "/datagov"); tab(pg, "overview")
at = txt(pg, "#dg-attention").upper()
check("grants expiring soon and too many restricted grants need attention", "GRANTS EXPIRING SOON" in at and "TOO MANY GRANTS" in at, at)
check("classification counts add up", "Restricted: 1" in txt(pg, "#dg-summary") and "Public: 1" in txt(pg, "#dg-summary") and "Holding personal data: 1" in txt(pg, "#dg-summary") or "Holding personal data: 2" in txt(pg, "#dg-summary"), txt(pg, "#dg-summary"))
check("the counts add up", "Approved: 3" in txt(pg, "#dg-counts") and "Rejected: 1" in txt(pg, "#dg-counts"), txt(pg, "#dg-counts"))
pg.fill("#dg-set-warn", "abc"); pg.click("#dg-set-save"); pg.wait_for_timeout(400)
check("a bad number of days is stopped", "1 to 365" in txt(pg, "#setting-problem"), txt(pg, "#setting-problem"))
pg.fill("#dg-set-warn", "10"); pg.fill("#dg-set-max", "5"); pg.click("#dg-set-save"); pg.wait_for_timeout(1500)
check("the settings are saved", "10 day(s)" in txt(pg, "#dg-setting-meaning") or "10" in txt(pg, "#dg-setting-meaning"), txt(pg, "#dg-setting-meaning"))
check("a higher limit clears the too many grants item", "TOO MANY GRANTS" not in txt(pg, "#dg-attention").upper(), txt(pg, "#dg-attention"))
check("an administrator cannot change the settings", st(A("PUT", "/setting", TUNDE, {"expiry_warning_days": 3, "max_restricted_grants": 3})) == 403)

# ---- isolation and audit ----
check("the other company sees none of it", A("GET", "/assets", OTHER, org="Other") == [])
check("the other company cannot read or act on an asset", st(A("GET", f"/assets/{a1}", OTHER, org="Other")) == 404 and st(A("POST", f"/assets/{a2}/approve", OTHER, {}, org="Other")) == 404)
check("the other company's overview is empty", A("GET", "/overview", OTHER, org="Other")["counts"]["approved"] == 0)
acts = api("GET", "/_audit", KWAME, "Meridian")["actions"]
for a_ in ("DATAGOV_ASSET_PROPOSED", "DATAGOV_ASSET_APPROVED", "DATAGOV_ASSET_REJECTED", "DATAGOV_REVIEW_RECORDED", "DATAGOV_REVIEW_CONFIRMED", "DATAGOV_GRANT_PROPOSED", "DATAGOV_GRANT_APPROVED", "DATAGOV_GRANT_REJECTED", "DATAGOV_GRANT_REVOKED", "DATAGOV_SETTING_SET"):
    check(f"the audit trail has {a_}", a_ in acts, [x for x in acts if "DATAGOV" in x])
aud = str(api("GET", "/_audit", KWAME, "Meridian"))
check("no typed content is copied into the audit trail", all(s not in aud for s in ("Customer ledger", "FIN-LEAD", "STAFF-01", "STAFF-02", "reconciliation", "owner confirmed", "Not needed for the weekend", "Moved to another team", "Payroll archive", "Duplicate of")))
check("no page errors in the browser", not errs, errs[:3])
finish(p, b)
