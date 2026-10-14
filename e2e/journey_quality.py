"""Browser journey: Quality management (Stage 23). Run via e2e/run_all.py."""
from datetime import datetime, timedelta, timezone

from common import *

TODAY = datetime.now(timezone.utc).date()
D = lambda n: (TODAY + timedelta(days=n)).isoformat()
def hrefs(pg): return [a.get_attribute("href") for a in pg.locator(".app-sidebar a").all()]
def tab(pg, name):
    pg.click(f"#ql-tab-{name}"); pg.wait_for_timeout(900)
def body(pg): return pg.inner_text("body")
def err(pg): return txt(pg, ".alert-error")
def A(m, path, who, bodyj=None, org="Meridian"): return api(m, "/quality" + path, who, org, bodyj)
def st(r): return r.get("status") if isinstance(r, dict) else None
def open_nc(pg, ref):
    tab(pg, "ncs"); pg.click(f"#ql-nc-open-{ref}"); pg.wait_for_timeout(900)
NC = dict(title="Invoices posted late", description="Supplier invoices were posted a week after receipt", source="PROCESS_CHECK", severity="MAJOR", area="Payables", occurred_on=D(-12), discovered_on=D(-10))
CAUSE = "Nobody owned the weekly invoice check"
CONTAIN = "All late invoices were posted by hand"

start_web()
p, b, pg, errs = session()

# ---- an accountant has no business here ----
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/quality")
check("the menu does not offer the workspace to an accountant", "#/quality" not in hrefs(pg), hrefs(pg))
check("typing the address shows no content", "Raise a nonconformance" not in body(pg), body(pg)[:200])
check("the server refuses an accountant (overview)", st(A("GET", "/overview", AISHA)) == 403)
check("the server refuses an accountant (ncs)", st(A("GET", "/ncs", AISHA)) == 403)

# ---- Dara raises a nonconformance ----
sign_in(pg, *DARA, "Meridian"); goto(pg, "/quality")
check("the menu offers the workspace", "#/quality" in hrefs(pg), hrefs(pg))
check("the banner says it inspects nothing", "inspects nothing" in txt(pg, "#ql-banner") and "not a certification" in txt(pg, "#ql-banner"), txt(pg, "#ql-banner"))
check("nothing needs attention yet", "Nothing needs attention" in txt(pg, "#ql-attention"), txt(pg, "#ql-attention"))
tab(pg, "ncs")
pg.click("#ql-nc-save"); pg.wait_for_timeout(300)
check("an empty form is stopped with a plain sentence", "title" in txt(pg, "#nc-problem").lower(), txt(pg, "#nc-problem"))
pg.fill("#ql-nc-title", NC["title"]); pg.fill("#ql-nc-desc", NC["description"]); pg.fill("#ql-nc-area", NC["area"]); pg.fill("#ql-nc-occ", NC["occurred_on"]); pg.fill("#ql-nc-dis", D(-20))
pg.click("#ql-nc-save"); pg.wait_for_timeout(300)
check("found before it happened is stopped", "before it happened" in txt(pg, "#nc-problem"), txt(pg, "#nc-problem"))
pg.fill("#ql-nc-dis", D(5)); pg.click("#ql-nc-save"); pg.wait_for_timeout(1200)
check("a future date is refused by the server", "future" in (err(pg) + txt(pg, "#nc-problem")).lower(), err(pg) + txt(pg, "#nc-problem"))
pg.fill("#ql-nc-dis", NC["discovered_on"]); pg.click("#ql-nc-save"); pg.wait_for_timeout(1500)
check("the nonconformance is raised", "NC-001" in txt(pg, "#ql-ncs") and "Not analysed yet" in txt(pg, "[data-nc='NC-001']"), txt(pg, "#ql-notice") + err(pg))
nid1 = A("GET", "/ncs", TUNDE)[0]["id"]
check("the person who raised it cannot void it", st(A("POST", f"/ncs/{nid1}/void", DARA, {"reason": "Raised by mistake today"})) == 403)
check("no action can be added before the analysis", st(A("POST", "/actions", TUNDE, dict(nc_id=nid1, kind="CORRECTIVE", description="Add a weekly invoice check", owner_name="Ada Obi", due_on=D(10)))) == 409)
check("the server refuses a bad severity", st(A("POST", "/ncs", TUNDE, dict(NC, title="Bad severity here", severity="HUGE"))) == 400)

# ---- Tunde analyses ----
sign_in(pg, *TUNDE, "Meridian"); goto(pg, "/quality"); open_nc(pg, "NC-001")
pg.fill("#ql-an-cause", "too short"); pg.fill("#ql-an-contain", CONTAIN); pg.click("#ql-nc-analyse"); pg.wait_for_timeout(400)
check("a short root cause is stopped", "root cause" in txt(pg, "#analyse-problem").lower(), txt(pg, "#analyse-problem"))
pg.fill("#ql-an-cause", CAUSE); pg.click("#ql-nc-analyse"); pg.wait_for_timeout(1500)
check("the analysis is recorded", "Analysed" in txt(pg, "[data-nc='NC-001']") and CAUSE in txt(pg, "[data-nc='NC-001']"), txt(pg, "[data-nc='NC-001']") + err(pg))
check("analysing twice is refused", st(A("POST", f"/ncs/{nid1}/analyse", TUNDE, dict(root_cause=CAUSE, containment=CONTAIN))) == 409)

# ---- actions ----
pg.reload(); pg.wait_for_timeout(1200); tab(pg, "overview")
check("an analysed nonconformance with no action needs attention", "NCS WITHOUT ACTIONS" in txt(pg, "#ql-attention").upper(), txt(pg, "#ql-attention"))
tab(pg, "actions")
pg.select_option("#ql-ac-nc", index=1); pg.fill("#ql-ac-desc", "Add a weekly invoice check"); pg.fill("#ql-ac-owner", "Ada Obi"); pg.fill("#ql-ac-due", D(-30)); pg.click("#ql-ac-save"); pg.wait_for_timeout(1200)
check("a due date before it was found is refused", "due" in (err(pg) + txt(pg, "#action-problem")).lower(), err(pg) + txt(pg, "#action-problem"))
pg.fill("#ql-ac-due", D(-1)); pg.click("#ql-ac-save"); pg.wait_for_timeout(1500)
check("the action is added and shown overdue", "CA-001" in txt(pg, "#ql-actions") and "Overdue" in txt(pg, "[data-action='CA-001']"), txt(pg, "#ql-notice") + err(pg))
pg.click("#ql-act-CA-001-complete"); pg.wait_for_timeout(300)
aid1 = A("GET", "/actions", TUNDE)[0]["id"]
check("completing with nothing typed is stopped", "date" in txt(pg, "#complete-" + aid1 + "-problem").lower(), txt(pg, "#complete-" + aid1 + "-problem"))
pg.fill("#ql-cm-CA-001-date", D(-1)); pg.fill("#ql-cm-CA-001-note", "The weekly check was added and run once"); pg.click("#ql-act-CA-001-complete"); pg.wait_for_timeout(1500)
check("the action is recorded as completed", "Waiting for an effectiveness check" in txt(pg, "[data-action='CA-001']"), txt(pg, "[data-action='CA-001']") + err(pg))
check("a completion date in the future is refused", st(A("POST", f"/actions/{aid1}/complete", TUNDE, dict(completed_on=D(5), note="Completing in the future"))) in (400, 409))

# ---- Kwame checks it, finds it not effective ----
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/quality"); tab(pg, "actions")
pg.select_option("#ql-vf-CA-001-result", "NOT_EFFECTIVE"); pg.fill("#ql-vf-CA-001-note", "short"); pg.click("#ql-act-CA-001-verify"); pg.wait_for_timeout(400)
check("a short check note is stopped", "20 characters" in txt(pg, "#verify-" + aid1 + "-problem"), txt(pg, "#verify-" + aid1 + "-problem"))
pg.fill("#ql-vf-CA-001-note", "Three of the last ten invoices were still posted late"); pg.click("#ql-act-CA-001-verify"); pg.wait_for_timeout(1500)
check("the check is recorded as not effective", "Checked: not effective" in txt(pg, "[data-action='CA-001']"), txt(pg, "[data-action='CA-001']") + err(pg))
open_nc(pg, "NC-001")
check("closing says why it cannot close yet", "Cannot be closed yet" in txt(pg, "#ql-close-problem"), txt(pg, "#ql-nc-detail"))
check("the server refuses closing while the check failed", st(A("POST", f"/ncs/{nid1}/close", KWAME, dict(note="Trying to close it anyway"))) == 409)
overview = A("GET", "/overview", KWAME)
check("a not-effective action needs attention", any(x["kind"] == "NOT_EFFECTIVE" for x in overview["attention"]), overview["attention"])

# ---- second action: Dara completes it, so Dara cannot check it ----
a2 = A("POST", "/actions", TUNDE, dict(nc_id=nid1, kind="PREVENTIVE", description="Name an owner for every recurring check", owner_name="Ada Obi", due_on=D(20)))
check("a second action is added", a2.get("ref") == "CA-002", a2)
r = A("POST", f"/actions/{a2['id']}/complete", DARA, dict(completed_on=D(-1), note="Every recurring check now has a named owner"))
check("it is completed", r.get("status") == "COMPLETED", r)
check("the person who completed it cannot check it", st(A("POST", f"/actions/{a2['id']}/verify", DARA, dict(result="EFFECTIVE", note="Checking my own completed work now"))) == 403)
sign_in(pg, *DARA, "Meridian"); goto(pg, "/quality"); tab(pg, "actions")
check("the completer sees no check button, only the reason", pg.locator("#ql-act-CA-002-verify").count() == 0 and "different person" in txt(pg, "[data-action='CA-002']"), txt(pg, "[data-action='CA-002']"))
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/quality"); tab(pg, "actions")
pg.fill("#ql-vf-CA-002-note", "Looked at all recurring checks, each has an owner"); pg.click("#ql-act-CA-002-verify"); pg.wait_for_timeout(1500)
check("a different person records it effective", "Checked: effective" in txt(pg, "[data-action='CA-002']"), txt(pg, "[data-action='CA-002']") + err(pg))
check("the first not-effective action blocks closing until a later effective one exists", st(A("POST", f"/ncs/{nid1}/close", KWAME, dict(note="Closing after the second action"))) == "CLOSED")

# ---- closing as the person who raised it ----
n2 = A("POST", "/ncs", DARA, dict(NC, title="Wrong rate on one invoice"))
a3 = A("POST", f"/ncs/{n2['id']}/analyse", TUNDE, dict(root_cause="A rate table was out of date for a month", containment="The invoice was corrected by hand"))
check("the second nonconformance is analysed", a3.get("status") == "ANALYSED", a3)
check("the person who raised it cannot close it", st(A("POST", f"/ncs/{n2['id']}/close", DARA, dict(note="Closing my own record"))) == 403)
check("a major one cannot close without an action", st(A("POST", f"/ncs/{n2['id']}/close", KWAME, dict(note="No action is needed here"))) == 409)

# ---- minor, closed with a reason ----
n3 = A("POST", "/ncs", DARA, dict(NC, title="Typo on a label", severity="MINOR"))
A("POST", f"/ncs/{n3['id']}/analyse", TUNDE, dict(root_cause="A typing slip by one person on one day", containment="The label was reprinted"))
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/quality"); open_nc(pg, "NC-003")
pg.fill("#ql-close-note", "Reprinted and checked"); pg.click("#ql-nc-close"); pg.wait_for_timeout(1200)
check("a minor one without a reason is refused", "NC-003" in body(pg) and "Closed" not in txt(pg, "[data-nc='NC-003']"), txt(pg, "[data-nc='NC-003']") + err(pg))
pg.fill("#ql-close-reason", "A single typing slip with no effect on any record"); pg.click("#ql-nc-close"); pg.wait_for_timeout(1500)
check("a minor one closes with a reason", "Closed" in txt(pg, "[data-nc='NC-003']") and "no action needed" in txt(pg, "[data-nc='NC-003']"), txt(pg, "[data-nc='NC-003']") + err(pg))

# ---- void, cancel ----
n4 = A("POST", "/ncs", TUNDE, dict(NC, title="Recorded in error today"))
pg.reload(); pg.wait_for_timeout(1200); open_nc(pg, "NC-004")
pg.fill("#note-void-" + n4["id"], "short"); pg.click("#ql-nc-void"); pg.wait_for_timeout(500)
check("voiding with a short reason is refused", "Voided" not in txt(pg, "[data-nc='NC-004']"), txt(pg, "[data-nc='NC-004']"))
pg.fill("#note-void-" + n4["id"], "Recorded twice by mistake"); pg.click("#ql-nc-void"); pg.wait_for_timeout(1500)
check("a record can be voided with a reason", "Voided: Recorded twice by mistake" in txt(pg, "[data-nc='NC-004']"), txt(pg, "[data-nc='NC-004']"))
a4 = A("POST", "/actions", TUNDE, dict(nc_id=n2["id"], kind="CORRECTIVE", description="Refresh the rate table every month", owner_name="Ada Obi", due_on=D(30)))
check("an action can be cancelled with a reason", A("POST", f"/actions/{a4['id']}/cancel", KWAME, {"reason": "Replaced by a system change"}).get("status") == "CANCELLED")

# ---- settings, overview ----
sign_in(pg, *DARA, "Meridian"); goto(pg, "/quality"); tab(pg, "overview")
check("counts show the closed ones", "Closed: 2" in txt(pg, "#ql-counts"), txt(pg, "#ql-counts"))
pg.fill("#ql-policy-verify", "3"); pg.click("#ql-policy-save"); pg.wait_for_timeout(400)
check("a check window under 7 days is stopped", "7 to 180" in txt(pg, "#policy-problem"), txt(pg, "#policy-problem"))
pg.fill("#ql-policy-verify", "45"); pg.click("#ql-policy-save"); pg.wait_for_timeout(1500)
check("the setting is saved", "45 days" in txt(pg, "#ql-policy-meaning"), txt(pg, "#ql-policy-meaning"))

# ---- isolation and audit ----
check("the other company sees none of it", A("GET", "/ncs", OTHER, org="Other") == [] and A("GET", "/actions", OTHER, org="Other") == [])
check("the other company cannot read or act on a record", st(A("GET", f"/ncs/{nid1}", OTHER, org="Other")) == 404 and st(A("POST", f"/actions/{aid1}/verify", OTHER, dict(result="EFFECTIVE", note="Approving from outside the company"), org="Other")) == 404)
check("the other company's overview is empty", A("GET", "/overview", OTHER, org="Other")["counts"]["open"] == 0)
acts = api("GET", "/_audit", DARA, "Meridian")["actions"]
for a_ in ("QUALITY_NC_RAISED", "QUALITY_NC_ANALYSED", "QUALITY_NC_CLOSED", "QUALITY_NC_VOIDED", "QUALITY_ACTION_ADDED", "QUALITY_ACTION_COMPLETED", "QUALITY_ACTION_VERIFIED", "QUALITY_ACTION_CANCELLED", "QUALITY_POLICY_SET"):
    check(f"the audit trail has {a_}", a_ in acts, [x for x in acts if "QUALITY" in x])
check("no typed content is copied into the audit trail", "weekly invoice check" not in str(api("GET", "/_audit", DARA, "Meridian")))
check("no page errors in the browser", not errs, errs[:3])
finish(p, b)
