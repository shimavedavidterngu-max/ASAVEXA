"""Browser journey: Investments (Stage 27). Run via e2e/run_all.py. The browser user and the user making API calls are always different people (one login at a time per person)."""
from datetime import datetime, timedelta, timezone

from common import *

TODAY = datetime.now(timezone.utc).date()
D = lambda n: (TODAY + timedelta(days=n)).isoformat()
def hrefs(pg): return [a.get_attribute("href") for a in pg.locator(".app-sidebar a").all()]
def tab(pg, name):
    pg.click(f"#im-tab-{name}"); pg.wait_for_timeout(900)
def body(pg): return pg.inner_text("body")
def err(pg): return txt(pg, ".alert-error")
def A(m, path, who, bodyj=None, org="Meridian"): return api(m, "/investments" + path, who, org, bodyj)
def st(r): return r.get("status") if isinstance(r, dict) else None
def details(pg, ref):
    tab(pg, "holdings")
    if ref in txt(pg, "#im-holding-detail"): return      # already open from before (the page keeps its state while the same person stays signed in)
    pg.click(f"#im-hd-open-{ref}"); pg.wait_for_timeout(1000)
def hid(ref, who): return next(i["id"] for i in A("GET", "/holdings", who) if i["ref"] == ref)
def fill(pg, **ids):
    for k, v in ids.items(): pg.fill("#" + k.replace("_", "-"), v)
def hold(who, **kw):
    d = dict(name="Treasury bill", identifier="tb-1", asset_class="BOND", currency="NGN", account="Broker account 2"); d.update(kw); return A("POST", "/holdings", who, d)
def trade(**kw):
    d = dict(units=1, price="100", fee="0", traded_on=D(-1), reference="CN-API"); d.update(kw); return d

start_web()
p, b, pg, errs = session()

# ---- an accountant has no business here ----
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/investments")
check("the menu does not offer the workspace to an accountant", "#/investments" not in hrefs(pg), hrefs(pg))
check("typing the address shows no content", "Add a holding" not in body(pg), body(pg)[:200])
check("the server refuses an accountant (overview)", st(A("GET", "/overview", AISHA)) == 403)
check("the server refuses an accountant (holdings)", st(A("GET", "/holdings", AISHA)) == 403)

# ---- Tunde adds a holding, buys, proposes a sale and records a price ----
sign_in(pg, *TUNDE, "Meridian"); goto(pg, "/investments")
check("the menu offers the workspace", "#/investments" in hrefs(pg), hrefs(pg))
check("the banner says it reads no market data and posts nothing to a ledger", "reads no market data" in txt(pg, "#im-banner") and "posts nothing to a ledger" in txt(pg, "#im-banner") and "no investment advice" in txt(pg, "#im-banner"), txt(pg, "#im-banner"))
check("nothing needs attention yet", "Nothing needs attention" in txt(pg, "#im-attention"), txt(pg, "#im-attention"))
tab(pg, "holdings")
pg.click("#im-hd-save"); pg.wait_for_timeout(300)
check("an empty form is stopped with a plain sentence", "name" in txt(pg, "#holding-problem").lower(), txt(pg, "#holding-problem"))
fill(pg, im_hd_name="Dangote Cement shares", im_hd_ident="dangcem", im_hd_cur="naira", im_hd_acct="Broker account 1"); pg.click("#im-hd-save"); pg.wait_for_timeout(300)
check("a bad currency is stopped", "three-letter" in txt(pg, "#holding-problem"), txt(pg, "#holding-problem"))
fill(pg, im_hd_cur="ngn"); pg.click("#im-hd-save"); pg.wait_for_timeout(1500)
check("the holding is added", "HD-001" in txt(pg, "[data-holding='HD-001']") and "DANGCEM" in txt(pg, "[data-holding='HD-001']") and "Units 0;" in txt(pg, "[data-holding='HD-001']"), txt(pg, "#im-notice") + err(pg))
check("a duplicate identifier is refused", st(A("POST", "/holdings", DARA, dict(name="Dangote again", identifier="DangCem", asset_class="EQUITY", currency="NGN", account="Broker account 1"))) == 409)
details(pg, "HD-001")
fill(pg, im_by_units="10", im_by_price="100.12345", im_by_fee="5", im_by_date=D(-2), im_by_ref="CN-1"); pg.click("#im-by-save"); pg.wait_for_timeout(300)
check("a five-decimal price is stopped", "four decimals" in txt(pg, "#buy-problem"), txt(pg, "#buy-problem"))
fill(pg, im_by_price="100", im_by_fee="5.005"); pg.click("#im-by-save"); pg.wait_for_timeout(300)
check("a three-decimal fee is stopped", "two decimals" in txt(pg, "#buy-problem"), txt(pg, "#buy-problem"))
fill(pg, im_by_fee="5", im_by_date=D(5)); pg.click("#im-by-save"); pg.wait_for_timeout(1200)
check("a future date is refused", "future" in (err(pg) + txt(pg, "#buy-problem")).lower(), err(pg) + txt(pg, "#buy-problem"))
fill(pg, im_by_date=D(-2)); pg.click("#im-by-save"); pg.wait_for_timeout(1500)
check("the purchase adds the fee to the cost", "Units 10; cost NGN 1005.00; average cost 100.5000" in txt(pg, "#im-holding-figures"), txt(pg, "#im-holding-figures") + err(pg))
fill(pg, im_by_units="5", im_by_price="120.5", im_by_fee="", im_by_date=D(-1), im_by_ref="CN-2"); pg.click("#im-by-save"); pg.wait_for_timeout(1500)
check("the average cost is the weighted average", "Units 15; cost NGN 1607.50; average cost 107.1667" in txt(pg, "#im-holding-figures"), txt(pg, "#im-holding-figures") + err(pg))
fill(pg, im_sl_units="20", im_sl_price="130", im_sl_fee="3", im_sl_date=D(-1), im_sl_ref="CN-3"); pg.click("#im-sl-save"); pg.wait_for_timeout(300)
check("selling more than is held is stopped", "Only 15 units held" in txt(pg, "#sell-problem"), txt(pg, "#sell-problem"))
fill(pg, im_sl_units="6"); pg.click("#im-sl-save"); pg.wait_for_timeout(1500)
check("the sale waits and the units do not change yet", "Waiting for approval" in txt(pg, "[data-trade='3']") and "Units 15;" in txt(pg, "#im-holding-figures"), txt(pg, "#im-trades") + err(pg))
check("the proposer sees no approve button", pg.locator("#im-tr-3-approve").count() == 0 and pg.locator("#im-tr-3-reject").count() == 0)
fill(pg, im_mk_price="0", im_mk_date=D(-1), im_mk_source="Broker statement"); pg.click("#im-mk-save"); pg.wait_for_timeout(300)
check("a zero price is stopped", "more than zero" in txt(pg, "#mark-problem"), txt(pg, "#mark-problem"))
fill(pg, im_mk_price="110"); pg.click("#im-mk-save"); pg.wait_for_timeout(1500)
check("the price gives an exact market value and gain", "Market value NGN 1650.00; gain or loss so far 42.50" in txt(pg, "[data-holding='HD-001']"), txt(pg, "[data-holding='HD-001']") + err(pg))
check("the price is listed with its source", "110.0000 (Broker statement" in txt(pg, "#im-marks"), txt(pg, "#im-marks"))
i1 = hid("HD-001", DARA)
check("a float number of units is refused", st(A("POST", f"/holdings/{i1}/buy", DARA, trade(units=1.5))) == 400)
check("a float price is refused", st(A("POST", f"/holdings/{i1}/buy", DARA, trade(price=12.5))) == 400)
check("an administrator cannot approve (no approve permission)", st(A("POST", f"/holdings/{i1}/sells/3/approve", TUNDE, {})) == 403)

# ---- Kwame decides ----
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/investments"); details(pg, "HD-001")
check("the approver sees no entry forms", pg.locator("#im-by-save").count() == 0 and pg.locator("#im-sl-save").count() == 0)
pg.fill("#im-tr-3-note", "ok"); pg.click("#im-tr-3-approve"); pg.wait_for_timeout(500)
check("a short approval note is stopped", "10 characters" in err(pg) or "note" in err(pg).lower(), err(pg))
pg.fill("#im-tr-3-note", ""); pg.click("#im-tr-3-approve"); pg.wait_for_timeout(1500)
check("a different person approves and the units change", "Units 9; cost NGN 964.50" in txt(pg, "#im-holding-figures") and "Applied" in txt(pg, "[data-trade='3']"), txt(pg, "#im-holding-figures") + err(pg))
check("the sale shows exact proceeds, cost removed and gain", "Proceeds 777.00, cost removed 643.00, gain or loss 134.00" in txt(pg, "[data-trade='3']"), txt(pg, "[data-trade='3']"))
check("an applied sale cannot be decided again", st(A("POST", f"/holdings/{i1}/sells/3/reject", DARA, {"reason": "Trying to reject it later"})) == 409)
check("the owner proposes a sale", A("POST", f"/holdings/{i1}/sells", DARA, trade(units=1, price="100", reference="CN-4")).get("pending_sells") == 1)
check("the owner cannot approve their own sale", st(A("POST", f"/holdings/{i1}/sells/4/approve", DARA, {})) == 403)
check("the owner cannot reject their own sale either", st(A("POST", f"/holdings/{i1}/sells/4/reject", DARA, {"reason": "Rejecting my own proposal"})) == 403)
check("the administrator proposes a second sale", A("POST", f"/holdings/{i1}/sells", TUNDE, trade(units=1, price="100", reference="CN-5")).get("pending_sells") == 2)
goto(pg, "/investments"); details(pg, "HD-001")
pg.click("#im-tr-4-approve"); pg.wait_for_timeout(1500)
check("the second sale is approved with an exact loss", "Units 8; cost NGN 857.33" in txt(pg, "#im-holding-figures") and "gain or loss -7.17" in txt(pg, "[data-trade='4']"), txt(pg, "[data-trade='4']") + err(pg))
pg.click("#im-tr-5-reject"); pg.wait_for_timeout(500)
check("rejecting without a reason is stopped", "10 characters" in err(pg) or "reason" in err(pg).lower(), err(pg))
pg.fill("#im-tr-5-note", "The price was typed wrongly"); pg.click("#im-tr-5-reject"); pg.wait_for_timeout(1500)
check("a different person rejects with a reason", "Rejected" in txt(pg, "[data-trade='5']") and "The price was typed wrongly" in txt(pg, "[data-trade='5']") and "Units 8;" in txt(pg, "#im-holding-figures"), txt(pg, "[data-trade='5']") + err(pg))

# ---- more holdings in other currencies, and a fully sold one ----
usd = hold(TUNDE, name="Dollar fund", identifier="usd-1", asset_class="FUND", currency="USD", account="Fund platform")
check("the second holding is numbered", usd.get("ref") == "HD-002", usd)
check("USD units are bought", A("POST", f"/holdings/{usd['id']}/buy", TUNDE, trade(units=2, price="10.5", reference="CN-U1")).get("cost_basis") == "21.00")
check("a USD price is recorded", A("POST", f"/holdings/{usd['id']}/marks", TUNDE, dict(price="11", as_of=D(-1), source="Fund factsheet")).get("market_value") == "22.00")
tb = hold(TUNDE)
check("a holding with no price is bought", A("POST", f"/holdings/{tb['id']}/buy", TUNDE, trade(units=4, price="50", reference="CN-T1")).get("cost_basis") == "200.00" and tb["ref"] == "HD-003")
sb = hold(TUNDE, name="Sold bond", identifier="sb-1")
A("POST", f"/holdings/{sb['id']}/buy", TUNDE, trade(units=1, price="10", reference="CN-S1")); A("POST", f"/holdings/{sb['id']}/sells", TUNDE, trade(units=1, price="12", reference="CN-S2"))
check("selling everything leaves no cost and books the exact gain", (lambda r: (r["units"], r["cost_basis"], r["realised_total"]))(A("POST", f"/holdings/{sb['id']}/sells/2/approve", DARA, {})) == ("0", "0.00", "2.00"))
goto(pg, "/investments"); details(pg, "HD-004")
pg.fill("#im-close-note", "short"); pg.click("#im-close-save"); pg.wait_for_timeout(500)
check("closing without a proper reason is stopped", "10 characters" in err(pg) or "reason" in err(pg).lower(), err(pg))
pg.fill("#im-close-note", "Fully sold and settled"); pg.click("#im-close-save"); pg.wait_for_timeout(1500)
check("an approver closes an empty holding", "Closed" in txt(pg, "[data-holding='HD-004']"), txt(pg, "[data-holding='HD-004']") + err(pg))
check("a closed holding takes no more trades", st(A("POST", f"/holdings/{sb['id']}/buy", DARA, trade())) == 409)
check("a holding with units cannot be closed", st(A("POST", f"/holdings/{i1}/close", DARA, {"reason": "Trying to close a holding in use"})) == 409)

# ---- overview ----
sign_in(pg, *DARA, "Meridian"); goto(pg, "/investments"); tab(pg, "overview")
check("totals are shown per currency", "NGN: 2 active holding" in txt(pg, "#im-totals") and "USD: 1 active holding" in txt(pg, "#im-totals") and "never added together" in txt(pg, "#im-totals"), txt(pg, "#im-totals"))
check("the NGN figures are exact", "cost 1057.33; 1 with a price worth 880.00 (gain or loss so far 22.67)" in txt(pg, "[data-currency='NGN']"), txt(pg, "[data-currency='NGN']"))
check("the NGN holding without a price is left out of market value", "1 without a price" in txt(pg, "[data-currency='NGN']") and "realised 128.83" in txt(pg, "[data-currency='NGN']"), txt(pg, "[data-currency='NGN']"))
check("the USD figures are exact", "cost 21.00; 1 with a price worth 22.00 (gain or loss so far 1.00)" in txt(pg, "[data-currency='USD']") and "realised 0.00" in txt(pg, "[data-currency='USD']"), txt(pg, "[data-currency='USD']"))
check("a holding with no price needs attention", "NO PRICE" in txt(pg, "#im-attention").upper(), txt(pg, "#im-attention"))
pg.fill("#im-policy-days", "3"); pg.click("#im-policy-save"); pg.wait_for_timeout(400)
check("fewer than 7 days is stopped", "7 to 365" in txt(pg, "#policy-problem"), txt(pg, "#policy-problem"))
pg.fill("#im-policy-days", "60"); pg.click("#im-policy-save"); pg.wait_for_timeout(1500)
check("the setting is saved", "60 days" in txt(pg, "#im-policy-meaning"), txt(pg, "#im-policy-meaning"))
check("an administrator cannot change the setting", st(A("PUT", "/policy", TUNDE, {"stale_days": 90})) == 403)

# ---- isolation and audit ----
check("the other company sees none of it", A("GET", "/holdings", OTHER, org="Other") == [])
check("the other company cannot read or act on a record", st(A("GET", f"/holdings/{i1}", OTHER, org="Other")) == 404 and st(A("POST", f"/holdings/{i1}/buy", OTHER, trade(), org="Other")) == 404)
check("the other company's overview is empty", A("GET", "/overview", OTHER, org="Other")["totals"] == [])
acts = api("GET", "/_audit", KWAME, "Meridian")["actions"]
for a_ in ("INVESTMENTS_HOLDING_ADDED", "INVESTMENTS_HOLDING_CLOSED", "INVESTMENTS_BUY_RECORDED", "INVESTMENTS_SELL_PROPOSED", "INVESTMENTS_SELL_APPROVED", "INVESTMENTS_SELL_REJECTED", "INVESTMENTS_MARK_RECORDED", "INVESTMENTS_POLICY_SET"):
    check(f"the audit trail has {a_}", a_ in acts, [x for x in acts if "INVESTMENTS" in x])
aud = str(api("GET", "/_audit", KWAME, "Meridian"))
check("no typed content is copied into the audit trail", "Dangote" not in aud and "CN-1" not in aud and "Broker statement" not in aud and "typed wrongly" not in aud)
check("no page errors in the browser", not errs, errs[:3])
finish(p, b)
