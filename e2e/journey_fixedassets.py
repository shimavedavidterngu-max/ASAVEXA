"""Browser journey: Fixed assets (Stage 25). Run via e2e/run_all.py."""
import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from asavexa.fixedassets.service import accumulated
from common import *

TODAY = datetime.now(timezone.utc).date()
D = lambda n: (TODAY + timedelta(days=n)).isoformat()
def hrefs(pg): return [a.get_attribute("href") for a in pg.locator(".app-sidebar a").all()]
def tab(pg, name):
    pg.click(f"#fa-tab-{name}"); pg.wait_for_timeout(900)
def body(pg): return pg.inner_text("body")
def err(pg): return txt(pg, ".alert-error")
def A(m, path, who, bodyj=None, org="Meridian"): return api(m, "/fixedassets" + path, who, org, bodyj)
def st(r): return r.get("status") if isinstance(r, dict) else None
def details(pg, ref):
    tab(pg, "assets"); pg.click(f"#fa-as-open-{ref}"); pg.wait_for_timeout(1000)
VAN = dict(name="Delivery van", category="VEHICLES", location="Main yard", custodian_name="Ben Eze", acquired_on=D(-100), currency="NGN", cost="12000.00", residual_value="2000.00", life_months=60, serial_number="VAN-1")

start_web()
p, b, pg, errs = session()

# ---- an accountant has no business here ----
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/fixedassets")
check("the menu does not offer the workspace to an accountant", "#/fixedassets" not in hrefs(pg), hrefs(pg))
check("typing the address shows no content", "Propose an asset" not in body(pg), body(pg)[:200])
check("the server refuses an accountant (overview)", st(A("GET", "/overview", AISHA)) == 403)
check("the server refuses an accountant (assets)", st(A("GET", "/assets", AISHA)) == 403)

# ---- Dara proposes an asset ----
sign_in(pg, *DARA, "Meridian"); goto(pg, "/fixedassets")
check("the menu offers the workspace", "#/fixedassets" in hrefs(pg), hrefs(pg))
check("the banner says it posts nothing to a ledger", "posts nothing to a ledger" in txt(pg, "#fa-banner") and "cannot tell whether an asset exists" in txt(pg, "#fa-banner"), txt(pg, "#fa-banner"))
check("nothing needs attention yet", "Nothing needs attention" in txt(pg, "#fa-attention"), txt(pg, "#fa-attention"))
tab(pg, "assets")
pg.click("#fa-as-save"); pg.wait_for_timeout(300)
check("an empty form is stopped with a plain sentence", "name" in txt(pg, "#asset-problem").lower(), txt(pg, "#asset-problem"))
pg.fill("#fa-as-name", VAN["name"]); pg.fill("#fa-as-serial", "VAN-1"); pg.fill("#fa-as-loc", VAN["location"]); pg.fill("#fa-as-cust", VAN["custodian_name"]); pg.fill("#fa-as-date", VAN["acquired_on"]); pg.fill("#fa-as-cur", "ngn")
pg.fill("#fa-as-cost", "12000.505"); pg.fill("#fa-as-res", "2000"); pg.fill("#fa-as-life", "60"); pg.click("#fa-as-save"); pg.wait_for_timeout(300)
check("a three-decimal cost is stopped", "two decimals" in txt(pg, "#asset-problem"), txt(pg, "#asset-problem"))
pg.fill("#fa-as-cost", "1500"); pg.click("#fa-as-save"); pg.wait_for_timeout(300)
check("a residual value above the cost is stopped", "less than the cost" in txt(pg, "#asset-problem"), txt(pg, "#asset-problem"))
pg.fill("#fa-as-cost", "12000.00"); pg.fill("#fa-as-res", "2000.00"); pg.click("#fa-as-save"); pg.wait_for_timeout(1500)
check("the asset is proposed and waits for approval", "FA-001" in txt(pg, "#fa-assets") and "Waiting for approval" in txt(pg, "[data-asset='FA-001']") and "166.67 a month" in txt(pg, "[data-asset='FA-001']"), txt(pg, "#fa-notice") + err(pg))
check("the proposer sees no approve button, only the reason", pg.locator("#fa-as-FA-001-approve").count() == 0 and "different person" in txt(pg, "[data-asset='FA-001']"), txt(pg, "[data-asset='FA-001']"))
a1 = A("GET", "/assets", TUNDE)[0]["id"]
check("the server refuses the proposer approving", st(A("POST", f"/assets/{a1}/approve", DARA, {})) == 403)
check("a duplicate serial number is refused", st(A("POST", "/assets", TUNDE, VAN)) == 409)

# ---- Tunde proposes more ----
land = A("POST", "/assets", TUNDE, dict(name="Plot at the depot", category="LAND", location="Depot road", custodian_name="Ada Obi", acquired_on=D(-100), currency="NGN", cost="5000000", residual_value="0"))
check("land is proposed without a life", land.get("ref") == "FA-002" and land.get("depreciates") is False and land.get("accumulated") == "0.00", land)
check("land with a useful life is refused", st(A("POST", "/assets", TUNDE, dict(name="Odd plot", category="LAND", location="Depot road", custodian_name="Ada Obi", acquired_on=D(-1), currency="NGN", cost="100", residual_value="0", life_months=60))) == 400)
gen = A("POST", "/assets", TUNDE, dict(name="Generator", category="PLANT_AND_MACHINERY", location="Workshop", custodian_name="Ada Obi", acquired_on=D(-90), currency="USD", cost="900.00", residual_value="0", life_months=36))
lap = A("POST", "/assets", TUNDE, dict(name="Laptop", category="IT_EQUIPMENT", location="Office", custodian_name="Ada Obi", acquired_on=D(-5), currency="NGN", cost="800", residual_value="0", life_months=36))
check("a float amount is refused", st(A("POST", "/assets", TUNDE, dict(name="Float asset", category="OTHER", location="Office", custodian_name="Ada Obi", acquired_on=D(-1), currency="NGN", cost=12.5, life_months=12))) == 400)
check("the other proposals are numbered", (gen.get("ref"), lap.get("ref")) == ("FA-003", "FA-004"), [gen, lap])

# ---- Kwame decides ----
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/fixedassets"); tab(pg, "assets")
pg.click("#fa-as-FA-004-reject"); pg.wait_for_timeout(500)
check("rejecting without a reason is stopped", "10 characters" in err(pg) or "reason" in err(pg).lower(), err(pg))
pg.fill("#fa-as-FA-004-note", "Entered with the wrong cost"); pg.click("#fa-as-FA-004-reject"); pg.wait_for_timeout(1500)
check("a different person rejects with a reason", "Rejected: Entered with the wrong cost" in txt(pg, "[data-asset='FA-004']"), txt(pg, "[data-asset='FA-004']") + err(pg))
pg.click("#fa-as-FA-001-approve"); pg.wait_for_timeout(1500)
check("a different person approves the asset", "Active" in txt(pg, "[data-asset='FA-001']"), txt(pg, "[data-asset='FA-001']") + err(pg))
check("the land is approved", A("POST", f"/assets/{land['id']}/approve", KWAME, {}).get("status") == "ACTIVE")
check("the generator is approved", A("POST", f"/assets/{gen['id']}/approve", KWAME, {}).get("status") == "ACTIVE")
exp_acc = accumulated(Decimal("12000.00"), Decimal("2000.00"), 60, TODAY - timedelta(days=100), TODAY)
goto(pg, "/fixedassets"); tab(pg, "assets")
check("depreciation shown is the exact straight-line figure", f"Depreciation to {D(0)}: {exp_acc}" in txt(pg, "[data-asset='FA-001']"), txt(pg, "[data-asset='FA-001']"))
check("net book value is cost less depreciation", f"{Decimal('12000.00') - exp_acc}" in txt(pg, "[data-asset='FA-001']"), txt(pg, "[data-asset='FA-001']"))

# ---- overview totals are per currency ----
sign_in(pg, *DARA, "Meridian"); goto(pg, "/fixedassets"); tab(pg, "overview")
check("totals are shown per currency", "NGN: 2 asset" in txt(pg, "#fa-totals") and "USD: 1 asset" in txt(pg, "#fa-totals") and "never added together" in txt(pg, "#fa-totals"), txt(pg, "#fa-totals"))
check("the NGN cost adds only NGN assets", "cost 5012000.00" in txt(pg, "[data-currency='NGN']"), txt(pg, "[data-currency='NGN']"))

# ---- schedule and counts ----
sign_in(pg, *TUNDE, "Meridian"); goto(pg, "/fixedassets"); details(pg, "FA-001")
check("the schedule is shown", "Month" in txt(pg, "#fa-schedule") and "Net book value" in txt(pg, "#fa-schedule"), txt(pg, "#fa-schedule"))
pg.fill("#fa-ct-date", D(5)); pg.select_option("#fa-ct-result", "MISSING"); pg.fill("#fa-ct-note", "Not in the yard at the check"); pg.click("#fa-ct-save"); pg.wait_for_timeout(1200)
check("a future count date is refused", "future" in (err(pg) + txt(pg, "#count-problem")).lower(), err(pg) + txt(pg, "#count-problem"))
pg.fill("#fa-ct-date", D(0)); pg.fill("#fa-ct-note", "short"); pg.click("#fa-ct-save"); pg.wait_for_timeout(300)
check("a short note is stopped", "10 characters" in txt(pg, "#count-problem"), txt(pg, "#count-problem"))
pg.fill("#fa-ct-note", "Not in the yard at the check"); pg.click("#fa-ct-save"); pg.wait_for_timeout(1500)
check("the count is recorded and waits for review", "Not found (missing)" in txt(pg, "#fa-counts-list") and "Waiting for review" in txt(pg, "#fa-counts-list"), txt(pg, "#fa-counts-list") + err(pg))
check("the asset is flagged missing", "Missing" in txt(pg, "[data-asset='FA-001']"), txt(pg, "[data-asset='FA-001']"))
check("an administrator cannot review a count", st(A("POST", f"/assets/{a1}/counts/1/review", TUNDE, {"note": "Reviewing as administrator"})) == 403)
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/fixedassets"); details(pg, "FA-001")
pg.fill("#fa-ct-1-note", "ok"); pg.click("#fa-ct-1-review"); pg.wait_for_timeout(500)
check("a short review note is stopped", "10 characters" in err(pg) or "note" in err(pg).lower(), err(pg))
pg.fill("#fa-ct-1-note", "Checked with the custodian"); pg.click("#fa-ct-1-review"); pg.wait_for_timeout(1500)
check("a different person reviews the count", "Reviewed by" in txt(pg, "#fa-counts-list"), txt(pg, "#fa-counts-list") + err(pg))
c2 = A("POST", f"/assets/{gen['id']}/counts", DARA, dict(counted_on=D(0), result="FOUND", note="Found in the workshop"))
check("a count is recorded by the owner", c2.get("counts_to_review") == 1, c2)
check("the person who counted cannot review it", st(A("POST", f"/assets/{gen['id']}/counts/1/review", DARA, {"note": "Reviewing my own count"})) == 403)

# ---- disposal ----
sign_in(pg, *DARA, "Meridian"); goto(pg, "/fixedassets"); details(pg, "FA-003")
pg.fill("#fa-dp-date", D(-200)); pg.fill("#fa-dp-proceeds", "100"); pg.fill("#fa-dp-reason", "Sold to a dealer after the lease ended"); pg.click("#fa-dp-save"); pg.wait_for_timeout(1200)
check("a disposal before acquisition is refused", "before it was acquired" in (err(pg) + txt(pg, "#disposal-problem")), err(pg) + txt(pg, "#disposal-problem"))
pg.fill("#fa-dp-date", D(-1)); pg.fill("#fa-dp-proceeds", "-5"); pg.click("#fa-dp-save"); pg.wait_for_timeout(300)
check("negative proceeds are stopped", "proceeds" in txt(pg, "#disposal-problem").lower(), txt(pg, "#disposal-problem"))
pg.fill("#fa-dp-proceeds", "100"); pg.click("#fa-dp-save"); pg.wait_for_timeout(1500)
nbv = Decimal("900.00") - accumulated(Decimal("900.00"), Decimal("0.00"), 36, TODAY - timedelta(days=90), TODAY - timedelta(days=1)); gl = Decimal("100.00") - nbv
check("the disposal waits and shows the exact net book value and result", "Disposal waiting for approval" in txt(pg, "[data-asset='FA-003']") and f"Net book value then {nbv}" in txt(pg, "#fa-disposal-info") and (f"loss of {-gl}" if gl < 0 else f"gain of {gl}") in txt(pg, "#fa-disposal-info"), txt(pg, "#fa-disposal-info") + err(pg))
check("the proposer cannot decide it", pg.locator("#fa-disposal-approve").count() == 0 and "different person" in txt(pg, "#fa-disposal-waiting"), txt(pg, "#fa-asset-detail"))
check("the server refuses the proposer approving", st(A("POST", f"/assets/{gen['id']}/disposal/approve", DARA, {})) == 403)
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/fixedassets"); details(pg, "FA-003")
pg.click("#fa-disposal-approve"); pg.wait_for_timeout(1500)
check("a different person approves the disposal", "Disposed of" in txt(pg, "[data-asset='FA-003']"), txt(pg, "[data-asset='FA-003']") + err(pg))
check("a disposed asset cannot be counted or disposed again", st(A("POST", f"/assets/{gen['id']}/counts", TUNDE, dict(counted_on=D(0), result="FOUND", note="Counting a disposed asset"))) == 409 and st(A("POST", f"/assets/{gen['id']}/disposal", TUNDE, dict(disposed_on=D(0), reason="Disposing a second time"))) == 409)
check("the net book value is frozen at the disposal date", A("GET", f"/assets/{gen['id']}", KWAME)["as_of"] == D(-1))
LD = A("POST", f"/assets/{land['id']}/disposal", TUNDE, dict(disposed_on=D(-1), proceeds="4000000", reason="Offer received from a buyer"))
check("land disposal waits", LD.get("status") == "DISPOSAL_PENDING", LD)
check("a disposal can be rejected with a reason", A("POST", f"/assets/{land['id']}/disposal/reject", KWAME, {"reason": "The buyer withdrew the offer"}).get("status") == "ACTIVE")

# ---- settings ----
sign_in(pg, *DARA, "Meridian"); goto(pg, "/fixedassets"); tab(pg, "overview")
pg.fill("#fa-policy-days", "10"); pg.click("#fa-policy-save"); pg.wait_for_timeout(400)
check("fewer than 30 days is stopped", "30 to 730" in txt(pg, "#policy-problem"), txt(pg, "#policy-problem"))
pg.fill("#fa-policy-days", "30"); pg.click("#fa-policy-save"); pg.wait_for_timeout(1500)
check("the setting is saved", "30 days" in txt(pg, "#fa-policy-meaning"), txt(pg, "#fa-policy-meaning"))
check("the uncounted land is now flagged as due", "COUNTS OVERDUE" in txt(pg, "#fa-attention").upper(), txt(pg, "#fa-attention"))
check("the missing asset needs attention", "MISSING ASSETS" in txt(pg, "#fa-attention").upper(), txt(pg, "#fa-attention"))

# ---- isolation and audit ----
check("the other company sees none of it", A("GET", "/assets", OTHER, org="Other") == [])
check("the other company cannot read or act on a record", st(A("GET", f"/assets/{a1}", OTHER, org="Other")) == 404 and st(A("POST", f"/assets/{a1}/counts/1/review", OTHER, {"note": "Reviewing from outside the company"}, org="Other")) == 404)
check("the other company's overview is empty", A("GET", "/overview", OTHER, org="Other")["totals"] == [])
acts = api("GET", "/_audit", DARA, "Meridian")["actions"]
for a_ in ("FIXEDASSETS_ASSET_PROPOSED", "FIXEDASSETS_ASSET_APPROVED", "FIXEDASSETS_ASSET_REJECTED", "FIXEDASSETS_DISPOSAL_PROPOSED", "FIXEDASSETS_DISPOSAL_APPROVED", "FIXEDASSETS_DISPOSAL_REJECTED", "FIXEDASSETS_COUNT_RECORDED", "FIXEDASSETS_COUNT_REVIEWED", "FIXEDASSETS_POLICY_SET"):
    check(f"the audit trail has {a_}", a_ in acts, [x for x in acts if "FIXEDASSETS" in x])
check("no typed content is copied into the audit trail", "Delivery van" not in str(api("GET", "/_audit", DARA, "Meridian")) and "12000" not in str(api("GET", "/_audit", DARA, "Meridian")))
check("no page errors in the browser", not errs, errs[:3])
finish(p, b)
