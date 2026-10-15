"""Browser journey: Inventory (Stage 26). Run via e2e/run_all.py."""
from datetime import datetime, timedelta, timezone

from common import *

TODAY = datetime.now(timezone.utc).date()
D = lambda n: (TODAY + timedelta(days=n)).isoformat()
def hrefs(pg): return [a.get_attribute("href") for a in pg.locator(".app-sidebar a").all()]
def tab(pg, name):
    pg.click(f"#iv-tab-{name}"); pg.wait_for_timeout(900)
def body(pg): return pg.inner_text("body")
def err(pg): return txt(pg, ".alert-error")
def A(m, path, who, bodyj=None, org="Meridian"): return api(m, "/inventory" + path, who, org, bodyj)
def st(r): return r.get("status") if isinstance(r, dict) else None
def details(pg, ref):
    tab(pg, "items"); pg.click(f"#iv-it-open-{ref}"); pg.wait_for_timeout(1000)
def item_id(ref, who=DARA): return next(i["id"] for i in A("GET", "/items", who) if i["ref"] == ref)
def fill(pg, **ids):
    for k, v in ids.items(): pg.fill("#" + k.replace("_", "-"), v)

start_web()
p, b, pg, errs = session()

# ---- an accountant has no business here ----
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/inventory")
check("the menu does not offer the workspace to an accountant", "#/inventory" not in hrefs(pg), hrefs(pg))
check("typing the address shows no content", "Add an item" not in body(pg), body(pg)[:200])
check("the server refuses an accountant (overview)", st(A("GET", "/overview", AISHA)) == 403)
check("the server refuses an accountant (items)", st(A("GET", "/items", AISHA)) == 403)

# ---- Tunde adds an item and moves stock ----
sign_in(pg, *TUNDE, "Meridian"); goto(pg, "/inventory")
check("the menu offers the workspace", "#/inventory" in hrefs(pg), hrefs(pg))
check("the banner says it posts nothing to a ledger", "posts nothing to a ledger" in txt(pg, "#iv-banner") and "cannot tell whether the stock is really on the shelf" in txt(pg, "#iv-banner"), txt(pg, "#iv-banner"))
check("nothing needs attention yet", "Nothing needs attention" in txt(pg, "#iv-attention"), txt(pg, "#iv-attention"))
tab(pg, "items")
pg.click("#iv-it-save"); pg.wait_for_timeout(300)
check("an empty form is stopped with a plain sentence", "code" in txt(pg, "#item-problem").lower(), txt(pg, "#item-problem"))
fill(pg, iv_it_sku="rice-25", iv_it_name="Rice 25kg bag", iv_it_unit="bag", iv_it_cur="naira", iv_it_loc="Main store"); pg.click("#iv-it-save"); pg.wait_for_timeout(300)
check("a bad currency is stopped", "three-letter" in txt(pg, "#item-problem"), txt(pg, "#item-problem"))
fill(pg, iv_it_cur="ngn", iv_it_reorder="10"); pg.click("#iv-it-save"); pg.wait_for_timeout(1500)
check("the item is added", "IT-001" in txt(pg, "[data-item='IT-001']") and "RICE-25" in txt(pg, "[data-item='IT-001']") and "On hand 0 bag" in txt(pg, "[data-item='IT-001']"), txt(pg, "#iv-notice") + err(pg))
check("an empty item is shown as out of stock", "Out of stock" in txt(pg, "[data-item='IT-001']"), txt(pg, "[data-item='IT-001']"))
check("a duplicate code is refused", st(A("POST", "/items", DARA, dict(sku="Rice-25", name="Rice again", unit="bag", currency="NGN", location="Main store"))) == 409)
details(pg, "IT-001")
fill(pg, iv_rc_qty="10", iv_rc_cost="100.505", iv_rc_date=D(-2), iv_rc_ref="GRN-1"); pg.click("#iv-rc-save"); pg.wait_for_timeout(300)
check("a three-decimal cost is stopped", "two decimals" in txt(pg, "#receive-problem"), txt(pg, "#receive-problem"))
fill(pg, iv_rc_cost="100.00", iv_rc_date=D(5)); pg.click("#iv-rc-save"); pg.wait_for_timeout(1200)
check("a future date is refused", "future" in (err(pg) + txt(pg, "#receive-problem")).lower(), err(pg) + txt(pg, "#receive-problem"))
fill(pg, iv_rc_date=D(-2)); pg.click("#iv-rc-save"); pg.wait_for_timeout(1500)
check("the receipt is recorded and valued", "On hand 10 bag; value NGN 1000.00; average cost 100.00" in txt(pg, "#iv-item-figures"), txt(pg, "#iv-item-figures") + err(pg))
fill(pg, iv_rc_qty="10", iv_rc_cost="120.00", iv_rc_date=D(-1), iv_rc_ref="GRN-2"); pg.click("#iv-rc-save"); pg.wait_for_timeout(1500)
check("the average cost is the weighted average", "On hand 20 bag; value NGN 2200.00; average cost 110.00" in txt(pg, "#iv-item-figures"), txt(pg, "#iv-item-figures") + err(pg))
fill(pg, iv_is_qty="25", iv_is_date=D(-1), iv_is_ref="SIV-1"); pg.click("#iv-is-save"); pg.wait_for_timeout(1200)
check("issuing more than is on hand is refused", "below zero" in err(pg) or "on hand" in err(pg).lower(), err(pg))
fill(pg, iv_is_qty="5"); pg.click("#iv-is-save"); pg.wait_for_timeout(1500)
check("the issue is valued at the average cost", "On hand 15 bag; value NGN 1650.00" in txt(pg, "#iv-item-figures") and "Issued: 5 bag" in txt(pg, "#iv-moves"), txt(pg, "#iv-item-figures") + err(pg))
check("a float quantity is refused", st(A("POST", f"/items/{item_id('IT-001')}/issue", DARA, dict(qty=1.5, moved_on=D(-1), reference="SIV-9"))) == 400)
check("a float cost is refused", st(A("POST", f"/items/{item_id('IT-001')}/receive", DARA, dict(qty=1, unit_cost=12.5, moved_on=D(-1), reference="GRN-9"))) == 400)

# ---- an adjustment needs a different person ----
pg.select_option("#iv-ad-dir", "DECREASE"); fill(pg, iv_ad_qty="2"); pg.select_option("#iv-ad-kind", "DAMAGE"); fill(pg, iv_ad_reason="short"); pg.click("#iv-ad-save"); pg.wait_for_timeout(300)
check("a short reason is stopped", "10 characters" in txt(pg, "#adjust-problem"), txt(pg, "#adjust-problem"))
fill(pg, iv_ad_reason="Two bags were split open"); pg.click("#iv-ad-save"); pg.wait_for_timeout(1500)
check("the adjustment waits and stock does not change yet", "Waiting for approval" in txt(pg, "[data-move='4']") and "On hand 15 bag" in txt(pg, "#iv-item-figures"), txt(pg, "#iv-moves") + err(pg) + "|" + txt(pg, "#adjust-problem") + "|" + body(pg)[-900:])
check("the proposer sees no approve button", pg.locator("#iv-mv-4-approve").count() == 0 and pg.locator("#iv-mv-4-reject").count() == 0, txt(pg, "[data-move='4']"))
i1 = item_id("IT-001")
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/inventory"); details(pg, "IT-001")
check("the approver sees no entry forms", pg.locator("#iv-rc-save").count() == 0 and pg.locator("#iv-ad-save").count() == 0)
pg.fill("#iv-mv-4-note", "ok"); pg.click("#iv-mv-4-approve"); pg.wait_for_timeout(500)
check("a short approval note is stopped", "10 characters" in err(pg) or "note" in err(pg).lower(), err(pg))
pg.fill("#iv-mv-4-note", ""); pg.click("#iv-mv-4-approve"); pg.wait_for_timeout(1500)
check("a different person approves and the stock changes", "On hand 13 bag; value NGN 1430.00" in txt(pg, "#iv-item-figures") and "Applied" in txt(pg, "[data-move='4']"), txt(pg, "#iv-item-figures") + err(pg))

sign_in(pg, *DARA, "Meridian"); goto(pg, "/inventory")
check("an applied adjustment cannot be decided again", st(A("POST", f"/items/{i1}/adjustments/4/reject", KWAME, {"reason": "Trying to reject it later"})) == 409)
check("a pending increase is proposed by the administrator", A("POST", f"/items/{i1}/adjustments", TUNDE, dict(direction="INCREASE", qty=1, reason_kind="OTHER", reason="Found one more bag in the yard")).get("pending_adjustments") == 1)
check("the server refuses the proposer approving", st(A("POST", f"/items/{i1}/adjustments/5/approve", TUNDE, {})) == 403)
check("an administrator cannot reject their own either", st(A("POST", f"/items/{i1}/adjustments/5/reject", TUNDE, {"reason": "Rejecting my own proposal"})) == 403)
# ---- a rejected adjustment, in another currency ----
oil = A("POST", "/items", TUNDE, dict(sku="oil-5", name="Cooking oil 5L", unit="can", currency="USD", reorder_level=0, location="Cold room"))
check("the second item is numbered", oil.get("ref") == "IT-002", oil)
o1 = oil["id"]
check("USD stock is received", A("POST", f"/items/{o1}/receive", TUNDE, dict(qty=3, unit_cost="2.50", moved_on=D(-1), reference="GRN-7")).get("value") == "7.50")
ad = A("POST", f"/items/{o1}/adjustments", TUNDE, dict(direction="INCREASE", qty=2, reason_kind="COUNT_DIFFERENCE", reason="Shelf holds two more than the book"))
check("an increase is proposed", ad["moves"][-1]["status"] == "PENDING", ad)
check("rejecting without a reason is refused", st(A("POST", f"/items/{o1}/adjustments/2/reject", KWAME, {"reason": "no"})) == 400)
check("an approver rejects with a reason", A("POST", f"/items/{o1}/adjustments/2/reject", KWAME, {"reason": "The recount found no difference"})["moves"][-1]["status"] == "REJECTED")
check("the first item's stray increase is rejected too", A("POST", f"/items/{i1}/adjustments/5/reject", KWAME, {"reason": "That was a test entry only"})["pending_adjustments"] == 0)

# ---- overview ----
A("POST", f"/items/{i1}/issue", TUNDE, dict(qty=4, moved_on=D(-1), reference="SIV-2"))
salt = A("POST", "/items", TUNDE, dict(sku="salt-1", name="Table salt", unit="pack", currency="NGN", reorder_level=5, location="Main store"))
sign_in(pg, *DARA, "Meridian"); goto(pg, "/inventory"); tab(pg, "overview")
check("totals are shown per currency", "NGN: 2 item" in txt(pg, "#iv-totals") and "USD: 1 item" in txt(pg, "#iv-totals") and "never added together" in txt(pg, "#iv-totals"), txt(pg, "#iv-totals"))
check("the NGN value is exact", "9 unit(s), value 990.00" in txt(pg, "[data-currency='NGN']"), txt(pg, "[data-currency='NGN']"))
check("the USD value is exact", "3 unit(s), value 7.50" in txt(pg, "[data-currency='USD']"), txt(pg, "[data-currency='USD']"))
check("low stock needs attention", "LOW STOCK" in txt(pg, "#iv-attention").upper(), txt(pg, "#iv-attention"))
check("out of stock needs attention", "OUT OF STOCK" in txt(pg, "#iv-attention").upper(), txt(pg, "#iv-attention"))

# ---- settings ----
pg.fill("#iv-policy-days", "10"); pg.click("#iv-policy-save"); pg.wait_for_timeout(400)
check("fewer than 30 days is stopped", "30 to 730" in txt(pg, "#policy-problem"), txt(pg, "#policy-problem"))
pg.fill("#iv-policy-days", "30"); pg.click("#iv-policy-save"); pg.wait_for_timeout(1500)
check("the setting is saved", "30 days" in txt(pg, "#iv-policy-meaning"), txt(pg, "#iv-policy-meaning"))
check("an administrator cannot change the setting", st(A("PUT", "/policy", TUNDE, {"stale_days": 60})) == 403)

# ---- discontinue ----
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/inventory"); details(pg, "IT-003")
pg.click("#iv-disc-save"); pg.wait_for_timeout(500)
check("discontinuing without a reason is stopped", "10 characters" in err(pg) or "reason" in err(pg).lower(), err(pg))
pg.fill("#iv-disc-note", "No longer sold at this store"); pg.click("#iv-disc-save"); pg.wait_for_timeout(1500)
check("an approver discontinues an empty item", "Discontinued" in txt(pg, "[data-item='IT-003']"), txt(pg, "[data-item='IT-003']") + err(pg))
check("a discontinued item takes no more movements", st(A("POST", f"/items/{salt['id']}/receive", DARA, dict(qty=1, unit_cost="5", moved_on=D(-1), reference="GRN-8"))) == 409)
check("an item with stock cannot be discontinued", st(A("POST", f"/items/{i1}/discontinue", DARA, {"reason": "Trying to drop a stocked item"})) == 409)

# ---- isolation and audit ----
check("the other company sees none of it", A("GET", "/items", OTHER, org="Other") == [])
check("the other company cannot read or act on a record", st(A("GET", f"/items/{i1}", OTHER, org="Other")) == 404 and st(A("POST", f"/items/{i1}/issue", OTHER, dict(qty=1, moved_on=D(-1), reference="SIV-X"), org="Other")) == 404)
check("the other company's overview is empty", A("GET", "/overview", OTHER, org="Other")["totals"] == [])
acts = api("GET", "/_audit", DARA, "Meridian")["actions"]
for a_ in ("INVENTORY_ITEM_ADDED", "INVENTORY_ITEM_DISCONTINUED", "INVENTORY_RECEIPT_RECORDED", "INVENTORY_ISSUE_RECORDED", "INVENTORY_ADJUSTMENT_PROPOSED", "INVENTORY_ADJUSTMENT_APPROVED", "INVENTORY_ADJUSTMENT_REJECTED", "INVENTORY_POLICY_SET"):
    check(f"the audit trail has {a_}", a_ in acts, [x for x in acts if "INVENTORY" in x])
aud = str(api("GET", "/_audit", DARA, "Meridian"))
check("no typed content is copied into the audit trail", "Rice 25kg" not in aud and "GRN-1" not in aud and "split open" not in aud)
check("no page errors in the browser", not errs, errs[:3])
finish(p, b)
