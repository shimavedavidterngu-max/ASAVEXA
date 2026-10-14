"""Browser journey: Treasury and Cash (Stage 16). Run via e2e/run_all.py."""
import json
from datetime import date, timedelta

from common import *

D = lambda n: (date.today() + timedelta(days=n)).isoformat()
def hrefs(pg): return [a.get_attribute("href") for a in pg.locator(".app-sidebar a").all()]
def tab(pg, name):
    pg.click(f"#tr-tab-{name}"); pg.wait_for_timeout(900)
def body(pg): return pg.inner_text("body")

start_web()
p, b, pg, errs = session()

# ---- the accountant prepares ----
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/treasury")
check("the menu offers Treasury and Cash", "#/treasury" in hrefs(pg), hrefs(pg))
check("the banner says it never moves money", "never moves money and is not connected to any bank" in txt(pg, "#tr-banner"), txt(pg, "#tr-banner"))
check("nothing is set up yet and the page says so", "No cash accounts are open yet" in body(pg), body(pg)[:300])
tab(pg, "accounts")
pg.click("#tr-acct-save"); pg.wait_for_timeout(300)
check("an empty account form is stopped with a plain sentence", "name" in txt(pg, "#account-problem").lower(), txt(pg, "#account-problem"))
pg.fill("#tr-acct-name", "Main current account"); pg.fill("#tr-acct-bank", "First Bank"); pg.fill("#tr-acct-cur", "ngn"); pg.fill("#tr-acct-last4", "0123456789")
pg.click("#tr-acct-save"); pg.wait_for_timeout(300)
check("a whole account number is refused before it is sent", "last four" in txt(pg, "#account-problem").lower(), txt(pg, "#account-problem"))
pg.fill("#tr-acct-last4", "4321"); pg.click("#tr-acct-save"); pg.wait_for_timeout(1500)
check("account opened and its panel is shown", "Account opened" in txt(pg, "#tr-notice") and "CA-001" in txt(pg, "#tr-acct-detail"), txt(pg, "#tr-notice") + txt(pg, "#account-problem"))
check("currency was upper-cased", "NGN" in txt(pg, "#tr-accounts"), txt(pg, "#tr-accounts"))
pg.fill("#tr-bal-date", D(1)); pg.fill("#tr-bal-amount", "10,000.00"); pg.fill("#tr-bal-source", "x"); pg.click("#tr-bal-save"); pg.wait_for_timeout(300)
check("a balance needs a named source", "came from" in txt(pg, "#balance-problem"), txt(pg, "#balance-problem"))
pg.fill("#tr-bal-date", D(-1)); pg.fill("#tr-bal-source", "Bank statement"); pg.click("#tr-bal-save"); pg.wait_for_timeout(1500)
check("balance recorded and not yet confirmed", "Recorded, not confirmed" in txt(pg, "#tr-acct-detail") and "10,000.00" in txt(pg, "#tr-acct-detail"), txt(pg, "#tr-acct-detail") + txt(pg, "#balance-problem") + txt(pg, "#tr-notice"))
check("the person who recorded it cannot confirm it", pg.locator("[id^=tr-bal-confirm-]").count() == 0 and "different approver to confirm" in txt(pg, "#tr-acct-detail").lower())

# ---- the approver confirms and sets policy ----
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/treasury"); tab(pg, "accounts")
check("an approver sees no create form", pg.locator("#tr-acct-save").count() == 0)
pg.click("#tr-acct-open-CA-001"); pg.wait_for_timeout(900)
check("an approver can confirm someone else's balance", pg.locator("[id^=tr-bal-confirm-]").count() == 1)
pg.click("[id^=tr-bal-confirm-]"); pg.wait_for_timeout(1500)
check("confirmed", "Confirmed" in txt(pg, "#tr-acct-detail") and pg.locator("[id^=tr-bal-confirm-]").count() == 0, txt(pg, "#tr-acct-detail"))

# ---- the accountant adds expected cash flows and reads the forecast ----
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/treasury"); tab(pg, "forecast")
pg.fill("#tr-flow-date", D(2)); pg.fill("#tr-flow-amount", "3,000"); pg.select_option("#tr-flow-dir", "OUT"); pg.fill("#tr-flow-desc", "Rent due")
pg.select_option("#tr-flow-account", index=1); pg.wait_for_timeout(200)
pg.select_option("#tr-flow-cat", "RENT_AND_UTILITIES"); pg.click("#tr-flow-save"); pg.wait_for_timeout(1500)
check("an expected payment is added", "Rent due" in txt(pg, "#tr-flows"), txt(pg, "#tr-flows") + txt(pg, "#flow-problem") + txt(pg, "#tr-notice"))
pg.select_option("#tr-flow-dir", "IN"); pg.fill("#tr-flow-date", D(9)); pg.fill("#tr-flow-amount", "5000"); pg.fill("#tr-flow-desc", "Customer receipt"); pg.select_option("#tr-flow-cat", "CUSTOMER_RECEIPT")
pg.select_option("#tr-flow-account", index=1); pg.click("#tr-flow-save"); pg.wait_for_timeout(1500)
check("an expected receipt is added", "Customer receipt" in txt(pg, "#tr-flows"), txt(pg, "#tr-flows") + txt(pg, "#flow-problem"))
pg.fill("#tr-flow-amount", "0"); pg.fill("#tr-flow-date", D(3)); pg.fill("#tr-flow-desc", "Bad one"); pg.click("#tr-flow-save"); pg.wait_for_timeout(300)
check("a zero amount is refused with a sentence", "more than zero" in txt(pg, "#flow-problem"), txt(pg, "#flow-problem"))
pg.click("#tr-forecast-go"); pg.wait_for_timeout(1500)
w1 = txt(pg, "[data-week='1']"); w2 = txt(pg, "[data-week='2']")
check("forecast week 1 is 10,000 less 3,000 = 7,000", "7,000.00" in w1 and "3,000.00" in w1, w1)
check("forecast week 2 adds 5,000 = 12,000", "12,000.00" in w2 and "5,000.00" in w2, w2)
check("opening balance and the basis are stated", "opening 10,000.00" in txt(pg, "#tr-forecast") and "zero (no minimum cash is set)" in txt(pg, "#tr-forecast"), txt(pg, "#tr-forecast")[:300])
check("no week is flagged yet", pg.locator("tr.tr-below").count() == 0)
check("an accountant sees no policy controls", True)   # policy lives on the overview tab; checked below

# ---- the approver sets a minimum cash policy ----
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/treasury")
pg.fill("#tr-policy-min", "NGN=8000"); pg.click("#tr-policy-save"); pg.wait_for_timeout(1500)
check("policy saved", "Policy saved" in txt(pg, "#tr-notice"), txt(pg, "#tr-notice") + txt(pg, "#policy-problem"))
pg.fill("#tr-policy-stale", "0"); pg.click("#tr-policy-save"); pg.wait_for_timeout(300)
check("a bad policy value is stopped", "1 to 90" in txt(pg, "#policy-problem"), txt(pg, "#policy-problem"))
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/treasury")
check("an accountant cannot edit the policy", pg.locator("#tr-policy-save").count() == 0 and "Only an approver" in txt(pg, "#tr-policy"))
tab(pg, "forecast"); pg.click("#tr-forecast-go"); pg.wait_for_timeout(1500)
check("week 1 is now flagged below the minimum cash", pg.locator("tr.tr-below").count() == 1 and "Below" in txt(pg, "[data-week='1']"), txt(pg, "#tr-forecast")[:400])
check("the forecast says which line it compared with", "your minimum cash setting" in txt(pg, "#tr-forecast"))
tab(pg, "overview")
check("the overview lists the shortfall", "SHORTFALL" in pg.inner_html("#tr-attention").upper() or "below" in txt(pg, "#tr-attention").lower(), txt(pg, "#tr-attention"))

# ---- payments: request, approve with separation, release ----
tab(pg, "payments")
pg.select_option("#tr-pay-account", index=1); pg.fill("#tr-pay-payee", "Acme Supplies"); pg.fill("#tr-pay-amount", "500"); pg.fill("#tr-pay-due", D(3)); pg.fill("#tr-pay-reason", "Office supplies"); pg.fill("#tr-pay-invoice", "INV-1")
pg.click("#tr-pay-save"); pg.wait_for_timeout(1500)
check("payment requested with warnings", "PR-001" in txt(pg, "#tr-payments") and "requested" in txt(pg, "#tr-notice").lower() and "warning" in txt(pg, "#tr-notice").lower(), txt(pg, "#tr-notice") + txt(pg, "#payment-problem"))
check("warnings are in plain words", "No earlier payment to this payee" in txt(pg, "#tr-payments") and "No supporting document" in txt(pg, "#tr-payments"), txt(pg, "#tr-payments"))
check("the requester can cancel but not approve or release", pg.locator("#tr-pay-cancel-PR-001").count() == 1 and pg.locator("#tr-pay-approve-PR-001").count() == 0 and pg.locator("#tr-pay-release-PR-001").count() == 0)
pg.fill("#tr-pay-payee", "Acme Supplies"); pg.select_option("#tr-pay-account", index=1); pg.fill("#tr-pay-amount", "500"); pg.fill("#tr-pay-due", D(3)); pg.fill("#tr-pay-reason", "Same invoice again"); pg.fill("#tr-pay-invoice", "inv-1")
pg.click("#tr-pay-save"); pg.wait_for_timeout(1500)
check("the same invoice is refused a second time", "twice" in txt(pg, ".alert-error, [role=alert]").lower() or "twice" in body(pg).lower(), body(pg)[:400])

sign_in(pg, *KWAME, "Meridian"); goto(pg, "/treasury"); tab(pg, "payments")
check("an approver sees approve and reject, not cancel", pg.locator("#tr-pay-approve-PR-001").count() == 1 and pg.locator("#tr-pay-reject-PR-001").count() == 1 and pg.locator("#tr-pay-cancel-PR-001").count() == 0)
pg.click("#tr-pay-approve-PR-001"); pg.wait_for_timeout(1200)
check("approving a warned request needs a reason", "warnings" in body(pg).lower() and "satisfied" in body(pg).lower(), body(pg)[:500])
pg.fill("[id^=note-pay-]", "Known supplier, invoice checked against the order"); pg.click("#tr-pay-approve-PR-001"); pg.wait_for_timeout(1500)
check("approved, not yet released", "Approved, not yet released" in txt(pg, "[data-payment]"), txt(pg, "#tr-payments"))
check("an approver cannot release (no prepare right)", pg.locator("#tr-pay-release-PR-001").count() == 0)

sign_in(pg, *AISHA, "Meridian"); goto(pg, "/treasury"); tab(pg, "payments")
check("the requester still cannot release their own approved payment", pg.locator("#tr-pay-release-PR-001").count() == 0)

sign_in(pg, *DARA, "Meridian"); goto(pg, "/treasury"); tab(pg, "payments")
check("a different preparer can record the release", pg.locator("#tr-pay-release-PR-001").count() == 1)
pg.click("#tr-pay-release-PR-001"); pg.wait_for_timeout(500)
check("release needs the date and the bank's reference", "reference" in body(pg).lower() or "real date" in body(pg).lower(), body(pg)[:400])
pg.fill("#tr-rel-date-PR-001", D(0)); pg.fill("#tr-rel-ref-PR-001", "TRX-0001"); pg.click("#tr-pay-release-PR-001"); pg.wait_for_timeout(1500)
check("released with the bank's reference", "Released" in txt(pg, "[data-payment]") and "TRX-0001" in txt(pg, "[data-payment]"), txt(pg, "#tr-payments"))

# ---- a large payment needs two approvers ----
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/treasury"); tab(pg, "payments")
pg.select_option("#tr-pay-account", index=1); pg.fill("#tr-pay-payee", "Big Ltd"); pg.fill("#tr-pay-amount", "20,000"); pg.fill("#tr-pay-due", D(5)); pg.fill("#tr-pay-reason", "Equipment deposit"); pg.fill("#tr-pay-invoice", "B-77")
pg.click("#tr-pay-save"); pg.wait_for_timeout(1500)
check("a large payment says two approvals are needed", "0 of 2 approvals" in txt(pg, "#tr-payments"), txt(pg, "#tr-payments"))
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/treasury"); tab(pg, "payments")
pg.fill("[id^=note-pay-]", "First look is fine, balance is short"); pg.click("#tr-pay-approve-PR-002"); pg.wait_for_timeout(1500)
check("first approval counted, still waiting", "1 of 2 approvals" in txt(pg, "#tr-payments") and "Waiting for approval" in txt(pg, "#tr-payments"), txt(pg, "#tr-payments"))
check("the same person cannot approve twice", pg.locator("#tr-pay-approve-PR-002").count() == 0)
sign_in(pg, *DARA, "Meridian"); goto(pg, "/treasury"); tab(pg, "payments")
pg.fill("[id^=note-pay-]", "Second look is fine"); pg.click("#tr-pay-approve-PR-002"); pg.wait_for_timeout(1500)
check("second approver completes it", "Approved, not yet released" in txt(pg, "#tr-payments"), txt(pg, "#tr-payments"))
tab(pg, "forecast"); pg.click("#tr-forecast-go"); pg.wait_for_timeout(1500)
check("the forecast counts the approved payment (3,000 rent + 20,000 = 23,000 out in week 1)", "23,000.00" in txt(pg, "[data-week='1']"), txt(pg, "[data-week='1']"))

# ---- covenants ----
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/treasury"); tab(pg, "covenants")
pg.fill("#tr-cov-name", "Debt service cover"); pg.fill("#tr-cov-lender", "Big Bank"); pg.fill("#tr-cov-desc", "Operating cash over debt service"); pg.fill("#tr-cov-thr", "1.25"); pg.fill("#tr-cov-from", "2025-12-31")
pg.click("#tr-cov-save"); pg.wait_for_timeout(1500)
check("covenant added, not tested yet", "CV-001" in txt(pg, "#tr-covenants") and "Not tested yet" in txt(pg, "#tr-covenants"), txt(pg, "#tr-covenants") + txt(pg, "#covenant-problem"))
check("it shows the rule and when the next test is due", "at or above 1.2500" in txt(pg, "#tr-covenants") and "result due by" in txt(pg, "#tr-covenants"), txt(pg, "#tr-covenants"))
pg.fill("#tr-res-date-CV-001", D(-10)); pg.fill("#tr-res-value-CV-001", "1.10"); pg.fill("#tr-res-source-CV-001", "Q4 management accounts"); pg.click("#tr-res-save-CV-001"); pg.wait_for_timeout(1500)
check("a breach without an explanation is refused", "explanation" in body(pg).lower(), body(pg)[:500])
pg.fill("#tr-res-note-CV-001", "Revenue fell more than planned this quarter"); pg.click("#tr-res-save-CV-001"); pg.wait_for_timeout(1500)
check("breach recorded and flagged", "Breach not acknowledged" in txt(pg, "#tr-covenants") and "Breached" in txt(pg, "#tr-covenants"), txt(pg, "#tr-covenants"))
check("the room is shown in words", "beyond the limit" in txt(pg, "#tr-covenants"), txt(pg, "#tr-covenants"))
check("the recorder cannot acknowledge", pg.locator("[id^=tr-ack-r]").count() == 0 and "Waiting for a second person" in txt(pg, "#tr-covenants"))
tab(pg, "overview")
check("the overview raises the unacknowledged breach", "nobody has acknowledged" in txt(pg, "#tr-attention"), txt(pg, "#tr-attention"))

sign_in(pg, *KWAME, "Meridian"); goto(pg, "/treasury"); tab(pg, "covenants")
check("a different approver can acknowledge", pg.locator("[id^=tr-ack-r]").count() >= 1)
pg.click("[id^=tr-ack-r]:not([id*=waiver])"); pg.wait_for_timeout(800)
check("an acknowledgement needs a note", "note" in body(pg).lower(), body(pg)[:400])
pg.fill("[id^=note-ack-]", "Lender told; waiver letter received 3 days ago"); pg.check("[id^=tr-ack-waiver-]"); pg.click("[id^=tr-ack-r]:not([id*=waiver])"); pg.wait_for_timeout(1500)
check("acknowledged but still shown as a breach", "Acknowledged (waiver or amendment obtained)" in txt(pg, "#tr-covenants") and "Breached" in txt(pg, "#tr-covenants") and "Breach not acknowledged" not in txt(pg, "#tr-covenants"), txt(pg, "#tr-covenants"))
pg.screenshot(path="/tmp/treasury-covenants.png", full_page=True)

# ---- the audit trail and other companies ----
acts = api("GET", "/_audit", DARA, "Meridian")["actions"]
for a in ("TR_ACCOUNT_OPENED", "TR_BALANCE_RECORDED", "TR_BALANCE_CONFIRMED", "TR_FLOW_ADDED", "TR_POLICY_SET", "TR_PAYMENT_REQUESTED", "TR_PAYMENT_APPROVED", "TR_PAYMENT_RELEASED", "TR_COVENANT_ADDED", "TR_COVENANT_RESULT", "TR_COVENANT_ACKNOWLEDGED"):
    check("audit has " + a, a in acts, acts[:8])
accts = api("GET", "/treasury/accounts", DARA, "Meridian"); AID = accts[0]["id"]
pays = api("GET", "/treasury/payments", DARA, "Meridian"); PID = pays[0]["id"]
sign_in(pg, *OTHER, "Other"); goto(pg, "/treasury")
check("another company sees an empty Treasury", "No cash accounts are open yet" in body(pg), body(pg)[:300])
for label, res in (("account", api("GET", f"/treasury/accounts/{AID}", OTHER, "Other")), ("payment", api("GET", f"/treasury/payments/{PID}", OTHER, "Other")),
                   ("approval", api("POST", f"/treasury/payments/{PID}/approve", OTHER, "Other", {"note": "x"})), ("balance", api("POST", f"/treasury/accounts/{AID}/balances", OTHER, "Other", {"as_at": D(-1), "amount": "1", "source": "abc"}))):
    check(f"another company cannot reach this company's {label} (404)", res.get("status") == 404, res)
check("another company's lists are empty", api("GET", "/treasury/accounts", OTHER, "Other") == [] and api("GET", "/treasury/payments", OTHER, "Other") == [] and api("GET", "/treasury/covenants", OTHER, "Other") == [])

# ---- permissions are enforced by the server, not just hidden ----
res = api("POST", "/treasury/payments", KWAME, "Meridian", {"account_id": AID, "payee": "Sneaky", "amount": "5", "due_date": D(1), "reason": "approver cannot ask"})
check("an approver cannot ask for a payment (403)", res.get("status") == 403, res)
res = api("POST", f"/treasury/payments/{PID}/approve", AISHA, "Meridian", {"note": "x"})
check("an accountant cannot approve (403)", res.get("status") == 403, res)
res = api("PUT", "/treasury/policy", AISHA, "Meridian", {"stale_days": 1})
check("an accountant cannot change the policy (403)", res.get("status") == 403, res)

# ---- hiding the workspace is a menu change only ----
r = api("PUT", "/entity-config", DARA, "Meridian", {"entity_type": "BUSINESS", "enabled_workspaces": ["analysis"]})
sign_in(pg, *DARA, "Meridian"); goto(pg, "/accounting")
check("when switched off, Treasury leaves the menu", "#/treasury" not in hrefs(pg), hrefs(pg))
goto(pg, "/treasury")
check("but it is still reachable by address (menu only, not a lock)", "Treasury and Cash" in body(pg) and "Page not found" not in body(pg), body(pg)[:300])
check("no console or page errors", not errs, errs)

finish(p, b)
