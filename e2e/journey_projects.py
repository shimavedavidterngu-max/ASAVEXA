"""Browser journey: Projects and grants (Stage 32). Run via e2e/run_all.py. The browser user and the user making API calls are always different people."""
from datetime import datetime, timedelta, timezone

from common import *

TODAY = datetime.now(timezone.utc).date()
D = lambda n: (TODAY + timedelta(days=n)).isoformat()
def hrefs(pg): return [a.get_attribute("href") for a in pg.locator(".app-sidebar a").all()]
def tab(pg, name):
    pg.click(f"#pj-tab-{name}"); pg.wait_for_timeout(900)
def body(pg): return pg.inner_text("body")
def err(pg): return txt(pg, ".alert-error")
def A(m, path, who, bodyj=None, org="Meridian"): return api(m, "/projects" + path, who, org, bodyj)
def st(r): return r.get("status") if isinstance(r, dict) else None
def pid(ref, who): return next(i["id"] for i in A("GET", "/projects", who) if i["ref"] == ref)
def fill(pg, **ids):
    for k, v in ids.items(): pg.fill("#" + k.replace("_", "-"), v)
def opn(pg, ref):
    pg.click(f"#pj-pr-open-{ref}"); pg.wait_for_timeout(900)
def mk(who, **kw):
    d = dict(title="Second programme", funder_ref="FND-2", currency="NGN", award="50000.00", period_start=D(-30), period_end=D(10)); d.update(kw); return A("POST", "/projects", who, d)
def bd(who, p, **kw):
    d = dict(category="Supplies", amount="50000.00"); d.update(kw); return A("POST", f"/projects/{p}/budget", who, d)
def ent(who, p, **kw):
    d = dict(entry_type="EXPENSE", budget_no=1, amount="150000.10", entry_date=D(-40), description="Field staff salaries for March"); d.update(kw); return A("POST", f"/projects/{p}/entries", who, d)

start_web()
p, b, pg, errs = session()

# ---- an accountant has no business here ----
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/projects")
check("the menu does not offer the workspace to an accountant", "#/projects" not in hrefs(pg), hrefs(pg))
check("typing the address shows no content", "Start a project" not in body(pg), body(pg)[:200])
check("the server refuses an accountant (overview)", st(A("GET", "/overview", AISHA)) == 403)
check("the server refuses an accountant (projects)", st(A("GET", "/projects", AISHA)) == 403)

# ---- Tunde prepares a project ----
sign_in(pg, *TUNDE, "Meridian"); goto(pg, "/projects")
check("the menu offers the workspace", "#/projects" in hrefs(pg), hrefs(pg))
check("the banner says it moves no money and applies no funder rules", "moves no money" in txt(pg, "#pj-banner") and "applies no funder or donor rules" in txt(pg, "#pj-banner"), txt(pg, "#pj-banner"))
check("nothing needs attention yet", "Nothing needs attention" in txt(pg, "#pj-attention"), txt(pg, "#pj-attention"))
tab(pg, "projects")
pg.click("#pj-pr-save"); pg.wait_for_timeout(300)
check("an empty form is stopped with a plain sentence", "title" in txt(pg, "#project-problem").lower(), txt(pg, "#project-problem"))
fill(pg, pj_pr_title="Clean water programme", pj_pr_fund="FND-2026-01", pj_pr_cur="ngn", pj_pr_award="1,000,000.00", pj_pr_start=D(-100), pj_pr_end=D(-150)); pg.click("#pj-pr-save"); pg.wait_for_timeout(300)
check("a project that ends before it starts is stopped", "cannot end before" in txt(pg, "#project-problem"), txt(pg, "#project-problem"))
fill(pg, pj_pr_end=D(200), pj_pr_award="1.234"); pg.click("#pj-pr-save"); pg.wait_for_timeout(300)
check("a three-decimal award is stopped", "two decimals" in txt(pg, "#project-problem"), txt(pg, "#project-problem"))
fill(pg, pj_pr_award="1,000,000.00"); pg.click("#pj-pr-save"); pg.wait_for_timeout(1500)
check("the project is numbered", "PJ-001" in txt(pg, "[data-project='PJ-001']") and "award 1000000.00" in txt(pg, "[data-project='PJ-001']"), txt(pg, "#pj-notice") + err(pg))
opn(pg, "PJ-001"); p1 = pid("PJ-001", DARA)
check("submitting a project with no budget is not offered", pg.locator("#pj-sb-save").count() == 0)
check("the server refuses to submit it", st(A("POST", f"/projects/{p1}/submit", TUNDE, {"note": ""})) == 409)
check("entries are not offered before approval", pg.locator("#pj-en-save").count() == 0 and st(ent(DARA, p1)) == 409)
fill(pg, pj_bl_cat="Personnel", pj_bl_amt="0"); pg.click("#pj-bl-save"); pg.wait_for_timeout(300)
check("a zero budget is stopped", "more than zero" in txt(pg, "#budget-problem"), txt(pg, "#budget-problem"))
fill(pg, pj_bl_amt="600,000.00"); pg.click("#pj-bl-save"); pg.wait_for_timeout(1500)
fill(pg, pj_bl_cat="Equipment", pj_bl_amt="250000.50"); pg.click("#pj-bl-save"); pg.wait_for_timeout(1500)
check("the budget lines are added", "Personnel: budget 600000.00" in txt(pg, "[data-line='1']") and "Equipment: budget 250000.50" in txt(pg, "[data-line='2']"), txt(pg, "#pj-budget") + err(pg))
check("unallocated is worked out exactly", "budgeted 850000.50, unallocated 149999.50" in txt(pg, "#pj-project-totals"), txt(pg, "#pj-project-totals"))
fill(pg, pj_bl_cat="Travel", pj_bl_amt="150000.00"); pg.click("#pj-bl-save"); pg.wait_for_timeout(1200)
check("a budget above the award is refused", "more than the award" in err(pg), err(pg))
fill(pg, pj_bl_cat="Equipment", pj_bl_amt="1.00"); pg.click("#pj-bl-save"); pg.wait_for_timeout(1200)
check("the same category twice is refused", bool(err(pg)), err(pg))
fill(pg, pj_bl_cat="Travel", pj_bl_amt="149999.50"); pg.click("#pj-bl-save"); pg.wait_for_timeout(1500)
check("a budget equal to the award is accepted", "unallocated 0.00" in txt(pg, "#pj-project-totals"), txt(pg, "#pj-project-totals") + err(pg))
pg.fill("#pj-bl-3-note", "no"); pg.click("#pj-bl-3-remove"); pg.wait_for_timeout(400)
check("removing without a reason is stopped", "5 characters" in err(pg) or "reason" in err(pg).lower(), err(pg))
pg.fill("#pj-bl-3-note", "Travel is not funded here"); pg.click("#pj-bl-3-remove"); pg.wait_for_timeout(1500)
check("a removed line keeps its reason and drops out of the budget", "Removed: Travel is not funded here" in txt(pg, "[data-line='3']") and "budgeted 850000.50" in txt(pg, "#pj-project-totals"), txt(pg, "[data-line='3']") + txt(pg, "#pj-project-totals"))
check("a float amount is refused by the server", st(bd(DARA, p1, category="Floaty", amount=10.5)) == 400)
pg.fill("#pj-sb-note", "short"); pg.click("#pj-sb-save"); pg.wait_for_timeout(300)
check("a short note is stopped", "10 characters" in txt(pg, "#submit-problem"), txt(pg, "#submit-problem"))
pg.fill("#pj-sb-note", ""); pg.click("#pj-sb-save"); pg.wait_for_timeout(1500)
check("the project is submitted and locked", "Waiting for review" in txt(pg, "[data-project='PJ-001']") and pg.locator("#pj-bl-save").count() == 0 and pg.locator("#pj-dec-approve").count() == 0, txt(pg, "[data-project='PJ-001']") + err(pg))
check("the submitter cannot approve through the server", st(A("POST", f"/projects/{p1}/approve", TUNDE, {"note": ""})) == 403)
check("adding a budget line to a submitted project is refused", st(bd(DARA, p1)) == 409)

# ---- two more projects by the owner, approved by the approver (browser user is Tunde) ----
p2 = mk(DARA)["id"]; bd(DARA, p2); A("POST", f"/projects/{p2}/submit", DARA, {"note": ""})
p3 = mk(DARA, title="Dollar programme", funder_ref="FND-3", currency="USD", award="20000.00", period_start=D(-60), period_end=D(-5))["id"]; bd(DARA, p3, amount="20000.00"); A("POST", f"/projects/{p3}/submit", DARA, {"note": ""})
check("the owner cannot approve their own project", st(A("POST", f"/projects/{p2}/approve", DARA, {"note": ""})) == 403)
check("the owner cannot return their own project", st(A("POST", f"/projects/{p2}/return", DARA, {"reason": "Returning my own project"})) == 403)
check("an administrator cannot approve (no approve permission)", st(A("POST", f"/projects/{p2}/approve", TUNDE, {"note": ""})) == 403)
check("the approver approves both", st(A("POST", f"/projects/{p2}/approve", KWAME, {"note": ""})) == "ACTIVE" and st(A("POST", f"/projects/{p3}/approve", KWAME, {"note": ""})) == "ACTIVE")

# ---- Kwame returns the first project ----
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/projects"); tab(pg, "projects"); opn(pg, "PJ-001")
check("the approver sees no editing", pg.locator("#pj-bl-save").count() == 0 and pg.locator("#pj-sb-save").count() == 0)
pg.click("#pj-dec-return"); pg.wait_for_timeout(400)
check("returning without a reason is stopped", "10 characters" in err(pg) or "reason" in err(pg).lower(), err(pg))
pg.fill("#pj-dec-note", "Please add the equipment quotes"); pg.click("#pj-dec-return"); pg.wait_for_timeout(1500)
check("a different person returns it with a reason", "Returned" in txt(pg, "[data-project='PJ-001']") and "Please add the equipment quotes" in txt(pg, "#pj-returned"), txt(pg, "[data-project='PJ-001']") + err(pg))
sign_in(pg, *TUNDE, "Meridian"); goto(pg, "/projects"); tab(pg, "projects"); opn(pg, "PJ-001")
check("a returned project can be edited again", pg.locator("#pj-bl-save").count() == 1 and pg.locator("#pj-sb-save").count() == 1)
pg.click("#pj-sb-save"); pg.wait_for_timeout(1500)
check("and submitted again", "Waiting for review" in txt(pg, "[data-project='PJ-001']"), txt(pg, "[data-project='PJ-001']") + err(pg))
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/projects"); tab(pg, "projects"); opn(pg, "PJ-001")
pg.click("#pj-dec-approve"); pg.wait_for_timeout(1500)
check("a different person approves", "Open" in txt(pg, "[data-project='PJ-001']") and pg.locator("#pj-dec-approve").count() == 0, txt(pg, "[data-project='PJ-001']") + err(pg))
check("an approved project cannot be decided again", st(A("POST", f"/projects/{p1}/return", DARA, {"reason": "Trying to return it later"})) == 409)
check("an approved project's budget cannot be changed", st(bd(DARA, p1)) == 409 and st(A("POST", f"/projects/{p1}/withdraw", TUNDE, {"reason": "Trying to withdraw it later"})) == 409)

# ---- Tunde proposes spending through the form ----
sign_in(pg, *TUNDE, "Meridian"); goto(pg, "/projects"); tab(pg, "projects"); opn(pg, "PJ-001")
pg.click("#pj-en-save"); pg.wait_for_timeout(300)
check("an empty entry form is stopped", bool(txt(pg, "#entry-problem")), txt(pg, "#entry-problem"))
fill(pg, pj_en_amt="200,000.25", pj_en_date=D(-200), pj_en_desc="Field staff salaries for February"); pg.select_option("#pj-en-line", "1"); pg.click("#pj-en-save"); pg.wait_for_timeout(300)
check("a date outside the project period is stopped", "inside the project period" in txt(pg, "#entry-problem"), txt(pg, "#entry-problem"))
fill(pg, pj_en_date=D(-50)); pg.click("#pj-en-save"); pg.wait_for_timeout(1500)
check("the expense is recorded and waits", "Expense on line #1: 200000.25" in txt(pg, "[data-entry='1']") and "Waiting for a decision" in txt(pg, "[data-entry='1']"), txt(pg, "#pj-entries") + err(pg))
check("an administrator sees no approve button", pg.locator("#pj-en-1-approve").count() == 0 and pg.locator("#pj-en-1-reject").count() == 0)
pg.select_option("#pj-en-type", "RECEIPT"); pg.wait_for_timeout(300)
check("a receipt has no budget line", pg.locator("#pj-en-line").count() == 0)
# the rest through the server as the owner
check("a float amount is refused", st(ent(DARA, p1, amount=5.5)) == 400)
check("an expense without a budget line is refused", st(ent(DARA, p1, budget_no=None)) == 400)
check("a future date is refused", st(ent(DARA, p1, entry_date=D(100))) == 400)
check("a receipt on a budget line is refused", st(ent(DARA, p1, entry_type="RECEIPT", budget_no=1)) == 400)
e2 = ent(DARA, p1); e3 = ent(DARA, p1, budget_no=2, amount="250000.51", description="Water pumps"); e4 = ent(DARA, p1, entry_type="RECEIPT", budget_no=None, amount="400000.00", description="First instalment from the funder")
e5 = ent(DARA, p1, amount="5.00", description="Duplicate of the first spending entry")
check("the entries are numbered", [e["no"] for e in e5["entries"]] == [1, 2, 3, 4, 5] and e5["pending_entries"] == 5, e5.get("entries"))
check("the owner cannot decide their own entry", st(A("POST", f"/projects/{p1}/entries/2/approve", DARA, {"note": ""})) == 403 and st(A("POST", f"/projects/{p1}/entries/2/reject", DARA, {"reason": "Rejecting my own entry"})) == 403)

# ---- Kwame decides ----
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/projects"); tab(pg, "projects"); opn(pg, "PJ-001")
check("closing is blocked while an entry waits", "Decide every proposed entry" in txt(pg, "#pj-close-blocked") and pg.locator("#pj-cl-save").count() == 0, body(pg)[:100])
check("the server refuses to close too", st(A("POST", f"/projects/{p1}/close", KWAME, {"reason": "Project finished on time"})) == 409)
pg.fill("#pj-en-5-note", "no"); pg.click("#pj-en-5-reject"); pg.wait_for_timeout(400)
check("rejecting without a reason is stopped", "10 characters" in err(pg) or "reason" in err(pg).lower(), err(pg))
pg.fill("#pj-en-5-note", "Duplicate of the first spending entry"); pg.click("#pj-en-5-reject"); pg.wait_for_timeout(1500)
check("a different person rejects with a reason", "Rejected" in txt(pg, "[data-entry='5']") and "Duplicate of the first spending entry" in txt(pg, "[data-entry='5']"), txt(pg, "[data-entry='5']") + err(pg))
pg.fill("#pj-en-1-note", "ok"); pg.click("#pj-en-1-approve"); pg.wait_for_timeout(400)
check("a short approval note is stopped", "10 characters" in err(pg) or "note" in err(pg).lower(), err(pg))
pg.fill("#pj-en-1-note", ""); pg.click("#pj-en-1-approve"); pg.wait_for_timeout(1500)
for n in (2, 3, 4):
    pg.click(f"#pj-en-{n}-approve"); pg.wait_for_timeout(1500)
check("a different person approves the entries", all("Approved" in txt(pg, f"[data-entry='{n}']") for n in (1, 2, 3, 4)), txt(pg, "#pj-entries") + err(pg))
check("totals are worked out exactly", all(s in txt(pg, "#pj-project-totals") for s in ("spent 600000.86", "remaining 399999.14", "received 400000.00", "still to receive 600000.00", "60.00 percent")), txt(pg, "#pj-project-totals"))
check("per line spending is exact and the equipment line is over budget", "spent 350000.35, remaining 249999.65" in txt(pg, "[data-line='1']") and "spent 250000.51, remaining -0.01" in txt(pg, "[data-line='2']") and "Over budget" in txt(pg, "[data-line='2']"), txt(pg, "#pj-budget"))
check("a decided entry cannot be decided again", st(A("POST", f"/projects/{p1}/entries/5/approve", DARA, {"note": ""})) == 409)
pg.fill("#pj-cl-note", "short"); pg.click("#pj-cl-save"); pg.wait_for_timeout(400)
check("closing without a proper note is stopped", "10 characters" in err(pg) or "note" in err(pg).lower(), err(pg))
pg.fill("#pj-cl-note", "Project finished and audited"); pg.click("#pj-cl-save"); pg.wait_for_timeout(1500)
check("the project is closed and no more entries are possible", "Closed" in txt(pg, "[data-project='PJ-001']") and "Project finished and audited" in txt(pg, "#pj-closed") and st(ent(DARA, p1)) == 409, txt(pg, "[data-project='PJ-001']") + err(pg))

# ---- overview ----
sign_in(pg, *DARA, "Meridian"); goto(pg, "/projects"); tab(pg, "overview")
check("naira projects are totalled exactly", all(s in txt(pg, "[data-currency='NGN']") for s in ("2 project(s)", "award 1050000.00", "budgeted 900000.50", "spent 600000.86", "remaining 449999.14", "received 400000.00", "still to receive 650000.00")), txt(pg, "#pj-totals"))
check("dollar projects are kept apart", all(s in txt(pg, "[data-currency='USD']") for s in ("1 project(s)", "award 20000.00", "spent 0.00")), txt(pg, "#pj-totals"))
at = txt(pg, "#pj-attention").upper()
check("over budget, ending soon and past end date need attention", "OVER BUDGET" in at and "ENDING SOON" in at and "ENDED STILL OPEN" in at, at)
check("the counts add up", "Closed: 1" in txt(pg, "#pj-counts") and "Open: 2" in txt(pg, "#pj-counts"), txt(pg, "#pj-counts"))
pg.fill("#pj-set-days", "abc"); pg.click("#pj-set-save"); pg.wait_for_timeout(400)
check("a bad number of days is stopped", "1 to 365" in txt(pg, "#setting-problem"), txt(pg, "#setting-problem"))
pg.fill("#pj-set-days", "5"); pg.click("#pj-set-save"); pg.wait_for_timeout(1500)
check("the setting is saved", "5 day(s)" in txt(pg, "#pj-setting-meaning"), txt(pg, "#pj-setting-meaning"))
check("the shorter window clears the ending soon item", "ENDING SOON" not in txt(pg, "#pj-attention").upper(), txt(pg, "#pj-attention"))
check("an administrator cannot change the setting", st(A("PUT", "/setting", TUNDE, {"ending_soon_days": 3})) == 403)

# ---- isolation and audit ----
check("the other company sees none of it", A("GET", "/projects", OTHER, org="Other") == [])
check("the other company cannot read or act on a project", st(A("GET", f"/projects/{p1}", OTHER, org="Other")) == 404 and st(A("POST", f"/projects/{p2}/approve", OTHER, {}, org="Other")) == 404)
check("the other company's overview is empty", A("GET", "/overview", OTHER, org="Other")["totals"] == [])
acts = api("GET", "/_audit", KWAME, "Meridian")["actions"]
for a_ in ("PROJECTS_PROJECT_CREATED", "PROJECTS_BUDGET_ADDED", "PROJECTS_BUDGET_REMOVED", "PROJECTS_PROJECT_SUBMITTED", "PROJECTS_PROJECT_RETURNED", "PROJECTS_PROJECT_APPROVED", "PROJECTS_ENTRY_PROPOSED", "PROJECTS_ENTRY_APPROVED", "PROJECTS_ENTRY_REJECTED", "PROJECTS_PROJECT_CLOSED", "PROJECTS_SETTING_SET"):
    check(f"the audit trail has {a_}", a_ in acts, [x for x in acts if "PROJECTS" in x])
aud = str(api("GET", "/_audit", KWAME, "Meridian"))
check("no typed content is copied into the audit trail", all(s not in aud for s in ("Clean water", "FND-2026", "Personnel", "Equipment", "1000000", "600000", "200000", "Field staff", "Water pumps", "equipment quotes", "Duplicate of", "finished and audited", "not funded here")))
check("no page errors in the browser", not errs, errs[:3])
finish(p, b)
