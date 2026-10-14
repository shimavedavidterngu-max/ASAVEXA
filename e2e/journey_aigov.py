"""Browser journey: AI governance (Stage 22). Run via e2e/run_all.py."""
from datetime import datetime, timedelta, timezone

from common import *

TODAY = datetime.now(timezone.utc).date()
D = lambda n: (TODAY + timedelta(days=n)).isoformat()
def hrefs(pg): return [a.get_attribute("href") for a in pg.locator(".app-sidebar a").all()]
def tab(pg, name):
    pg.click(f"#gv-tab-{name}"); pg.wait_for_timeout(900)
def body(pg): return pg.inner_text("body")
def err(pg): return txt(pg, ".alert-error")
def A(m, path, who, bodyj=None, org="Meridian"): return api(m, "/aigov" + path, who, org, bodyj)
def st(r): return r.get("status") if isinstance(r, dict) else None
def open_system(pg, ref):
    tab(pg, "systems"); pg.click(f"#gv-system-open-{ref}"); pg.wait_for_timeout(900)
SYS = dict(name="Invoice reader", description="Reads supplier invoices and suggests the account to post to", origin="VENDOR", vendor_name="Acme AI", intended_use="Suggest accounts for invoices; a person posts every entry",
           out_of_scope="Must not post entries or approve payments on its own", risk_tier="LIMITED", owner_name="Ada Obi")

start_web()
p, b, pg, errs = session()

# ---- an accountant has no business here ----
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/aigov")
check("the menu does not offer the workspace to an accountant", "#/aigov" not in hrefs(pg), hrefs(pg))
check("typing the address shows no content", "Propose an AI system" not in body(pg) and "Record an incident" not in body(pg), body(pg)[:200])
check("the server refuses an accountant (overview)", st(A("GET", "/overview", AISHA)) == 403)
check("the server refuses an accountant (systems)", st(A("GET", "/systems", AISHA)) == 403)

# ---- Dara (owner) proposes a system ----
sign_in(pg, *DARA, "Meridian"); goto(pg, "/aigov")
check("the menu offers the workspace", "#/aigov" in hrefs(pg), hrefs(pg))
check("the banner says it connects to nothing", "connects to no AI system" in txt(pg, "#gv-banner") and "not a legal classification" in txt(pg, "#gv-banner"), txt(pg, "#gv-banner"))
check("nothing needs attention yet", "Nothing needs attention" in txt(pg, "#gv-attention"), txt(pg, "#gv-attention"))
tab(pg, "systems")
pg.click("#gv-sys-save"); pg.wait_for_timeout(300)
check("an empty system is stopped with a plain sentence", "name" in txt(pg, "#system-problem").lower(), txt(pg, "#system-problem"))
pg.fill("#gv-sys-name", SYS["name"]); pg.fill("#gv-sys-vendor", "Acme AI"); pg.fill("#gv-sys-desc", SYS["description"]); pg.fill("#gv-sys-use", SYS["intended_use"]); pg.fill("#gv-sys-out", SYS["out_of_scope"]); pg.fill("#gv-sys-owner", "Ada Obi")
pg.select_option("#gv-sys-tier", "HIGH"); pg.click("#gv-sys-save"); pg.wait_for_timeout(300)
check("a high-tier system without oversight is stopped", "oversees" in txt(pg, "#system-problem"), txt(pg, "#system-problem"))
pg.select_option("#gv-sys-tier", "LIMITED"); pg.click("#gv-sys-save"); pg.wait_for_timeout(1500)
check("the system is proposed", "AI-001" in txt(pg, "#gv-systems") and "Waiting for approval" in txt(pg, "[data-system='AI-001']"), txt(pg, "#gv-notice") + err(pg))
check("the card states the intended use and what is not allowed", "Must not post entries" in txt(pg, "[data-system='AI-001']"), txt(pg, "[data-system='AI-001']"))
check("a duplicate name is refused", st(A("POST", "/systems", DARA, SYS)) == 409)
pg.click("#gv-system-open-AI-001"); pg.wait_for_timeout(800)
check("the proposer cannot approve their own system", pg.locator("#gv-system-approve").count() == 0 and "different person" in txt(pg, "#gv-system-waiting"), txt(pg, "#gv-system-detail"))
sid1 = A("GET", "/systems", TUNDE)[0]["id"]
check("the server refuses the proposer approving it", st(A("POST", f"/systems/{sid1}/approve", DARA, {"note": ""})) == 403)
tab(pg, "changes")
check("no change can be recorded yet", "No approved AI system" in txt(pg, "#gv-change-card"), txt(pg, "#gv-change-card"))
check("the server refuses a change on an unapproved system", st(A("POST", "/changes", DARA, dict(system_id=sid1, change_kind="MODEL_UPDATE", from_version="1.0", to_version="1.1", description="The vendor released a new version", effective_on=D(-2), testing_summary="Ran 50 sample invoices"))) == 409)

# ---- Tunde (second preparer) proposes a high-tier system ----
s2 = A("POST", "/systems", TUNDE, dict(SYS, name="Credit scoring helper", description="Ranks loan applications for a person to look at first", risk_tier="HIGH", human_oversight="A credit officer decides every application"))
check("a second preparer proposes a high-tier system", s2.get("ref") == "AI-002" and s2.get("risk_tier") == "HIGH", s2)
check("a high-tier system without oversight is refused by the server", st(A("POST", "/systems", TUNDE, dict(SYS, name="No oversight tool", risk_tier="HIGH"))) == 400)
check("a vendor system without a vendor is refused", st(A("POST", "/systems", TUNDE, dict(SYS, name="Mystery vendor tool", vendor_name=""))) == 400)

# ---- Kwame (approver) decides ----
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/aigov"); open_system(pg, "AI-001")
pg.click("#gv-system-reject"); pg.wait_for_timeout(500)
check("rejecting without a reason is stopped", "10 characters" in err(pg) or "reason" in err(pg).lower(), err(pg))
pg.click("#gv-system-approve"); pg.wait_for_timeout(1500)
check("a different person approves the system", "Approved" in txt(pg, "[data-system='AI-001']"), txt(pg, "[data-system='AI-001']") + err(pg))
sid2 = s2["id"]
check("the second system is approved", A("POST", f"/systems/{sid2}/approve", DARA, {"note": ""}).get("status") == "APPROVED")

# ---- model changes ----
sign_in(pg, *DARA, "Meridian"); goto(pg, "/aigov"); tab(pg, "changes")
pg.select_option("#gv-chg-system", index=1); pg.fill("#gv-chg-from", "1.0"); pg.fill("#gv-chg-to", "1.0"); pg.fill("#gv-chg-date", D(-3)); pg.fill("#gv-chg-desc", "The vendor released a new version"); pg.fill("#gv-chg-testing", "Ran 50 sample invoices"); pg.click("#gv-chg-save"); pg.wait_for_timeout(400)
check("the same version before and after is stopped", "differ" in txt(pg, "#change-problem"), txt(pg, "#change-problem"))
pg.fill("#gv-chg-to", "1.1"); pg.fill("#gv-chg-date", D(5)); pg.click("#gv-chg-save"); pg.wait_for_timeout(1200)
check("a change dated in the future is refused by the server", "future" in (err(pg) + txt(pg, "#change-problem")).lower(), err(pg) + txt(pg, "#change-problem"))
pg.fill("#gv-chg-date", D(-3)); pg.click("#gv-chg-save"); pg.wait_for_timeout(1500)
check("the change is recorded and waits", "MC-001" in txt(pg, "#gv-changes") and "Waiting for a different person" in txt(pg, "[data-change='MC-001']"), txt(pg, "#gv-notice") + err(pg))
check("the recorder sees no approve button", pg.locator("#gv-chg-MC-001-approve").count() == 0 and "different person" in txt(pg, "[data-change='MC-001']"))
check("a change to a high-tier system needs a test document", st(A("POST", "/changes", TUNDE, dict(system_id=sid2, change_kind="MODEL_UPDATE", from_version="1.0", to_version="1.1", description="The vendor released a new version", effective_on=D(-2), testing_summary="Ran 50 sample applications"))) == 400)
cid1 = A("GET", "/changes", TUNDE)[0]["id"]
check("the server refuses the recorder approving", st(A("POST", f"/changes/{cid1}/approve", DARA, {"note": ""})) == 403)
check("a retire is blocked while a change waits", st(A("POST", f"/systems/{sid1}/retire", KWAME, {"reason": "Replaced by another tool"})) == 409)

# ---- incidents ----
i1 = A("POST", "/incidents", TUNDE, dict(system_id=sid1, incident_kind="WRONG_OUTPUT", severity="LOW", description="The suggested account was wrong for a batch of invoices", occurred_on=D(-6), discovered_on=D(-5)))
i2 = A("POST", "/incidents", TUNDE, dict(system_id=sid1, incident_kind="WRONG_OUTPUT", severity="LOW", description="Recorded against the wrong system by mistake", occurred_on=D(-4), discovered_on=D(-4)))
i3 = A("POST", "/incidents", TUNDE, dict(system_id=sid2, incident_kind="BIAS", severity="HIGH", description="Applications from one region were ranked lower", occurred_on=D(-3), discovered_on=D(-2), harm="Forty applicants were ranked unfairly", people_affected=40))
check("incidents are recorded", [x.get("ref") for x in (i1, i2, i3)] == ["AX-001", "AX-002", "AX-003"], [i1, i2, i3])
check("a high incident without harm is refused", st(A("POST", "/incidents", TUNDE, dict(system_id=sid2, incident_kind="BIAS", severity="HIGH", description="Applications from one region were ranked lower", occurred_on=D(-3), discovered_on=D(-2)))) == 400)
check("found before it happened is refused", st(A("POST", "/incidents", TUNDE, dict(system_id=sid1, incident_kind="OTHER", severity="LOW", description="Dates the wrong way round", occurred_on=D(-2), discovered_on=D(-4)))) == 400)
check("an incident on an unapproved system is refused", st(A("POST", "/incidents", TUNDE, dict(system_id=A("POST", "/systems", TUNDE, dict(SYS, name="Not approved yet"))["id"], incident_kind="OTHER", severity="LOW", description="This system was never approved", occurred_on=D(-2), discovered_on=D(-2)))) == 409)
pg.reload(); pg.wait_for_timeout(1500); tab(pg, "overview")
check("a severe unreviewed incident needs attention", "SEVERE INCIDENTS OPEN" in txt(pg, "#gv-attention").upper(), txt(pg, "#gv-attention"))
check("counts show two approved systems and a high tier one", "Approved AI systems: 2" in txt(pg, "#gv-counts") and "High tier: 1" in txt(pg, "#gv-counts"), txt(pg, "#gv-counts"))

# ---- Kwame approves the change, reviews and voids incidents, reviews a system ----
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/aigov"); tab(pg, "changes")
pg.click("#gv-chg-MC-001-approve"); pg.wait_for_timeout(1500)
check("a different person approves the change", "Approved" in txt(pg, "[data-change='MC-001']"), txt(pg, "[data-change='MC-001']") + err(pg))
tab(pg, "incidents"); pg.click("#gv-inc-open-AX-001"); pg.wait_for_timeout(800)
pg.fill("#gv-rev-cause", "short"); pg.fill("#gv-rev-action", "also short"); pg.click("#gv-inc-review"); pg.wait_for_timeout(400)
check("a short cause is stopped", "cause" in txt(pg, "#review-problem").lower(), txt(pg, "#review-problem"))
pg.fill("#gv-rev-cause", "The model was not given the chart of accounts"); pg.fill("#gv-rev-action", "The chart of accounts is now sent with every request"); pg.click("#gv-inc-review"); pg.wait_for_timeout(1500)
check("the incident is reviewed", "Cause: The model was not given" in txt(pg, "[data-incident='AX-001']"), txt(pg, "[data-incident='AX-001']") + err(pg))
pg.click("#gv-inc-open-AX-002"); pg.wait_for_timeout(800)
pg.fill("#note-void-" + i2["id"], "short"); pg.click("#gv-inc-void"); pg.wait_for_timeout(500)
check("voiding with a short reason is refused", "Voided" not in txt(pg, "[data-incident='AX-002']"), txt(pg, "[data-incident='AX-002']"))
pg.fill("#note-void-" + i2["id"], "Recorded against the wrong system"); pg.click("#gv-inc-void"); pg.wait_for_timeout(1500)
check("an incident can be voided with a reason", "Voided: Recorded against the wrong system" in txt(pg, "[data-incident='AX-002']"), txt(pg, "[data-incident='AX-002']"))
check("the high incident is still waiting", "Waiting for a different person" in txt(pg, "[data-incident='AX-003']"), txt(pg, "[data-incident='AX-003']"))
check("a retire is blocked while the high-tier system has an open incident", st(A("POST", f"/systems/{sid2}/retire", DARA, {"reason": "Replaced by another tool"})) == 409)
open_system(pg, "AI-001"); pg.fill("#note-sys-" + sid1, "short"); pg.click("#gv-system-review"); pg.wait_for_timeout(500)
check("a review with a short note is stopped", "10 characters" in err(pg) or "note" in err(pg).lower(), err(pg))
pg.fill("#note-sys-" + sid1, "Still used as approved and nothing has changed"); pg.click("#gv-system-review"); pg.wait_for_timeout(1500)
check("a different person records a review", "Last reviewed" in txt(pg, "[data-system='AI-001']"), txt(pg, "[data-system='AI-001']") + err(pg))
sign_in(pg, *DARA, "Meridian"); goto(pg, "/aigov"); open_system(pg, "AI-001")
check("the proposer cannot review their own system", pg.locator("#gv-system-review").count() == 0 and "different person" in txt(pg, "#gv-review-waiting"), txt(pg, "#gv-system-detail"))
check("the server refuses the proposer reviewing it", st(A("POST", f"/systems/{sid1}/review", DARA, {"note": "Reviewing my own proposal"})) == 403)

# ---- settings ----
tab(pg, "overview"); pg.fill("#gv-policy-review", "10"); pg.click("#gv-policy-save"); pg.wait_for_timeout(500)
check("a review interval under 30 days is stopped", "30 to 730" in txt(pg, "#policy-problem"), txt(pg, "#policy-problem"))
pg.fill("#gv-policy-review", "90"); pg.click("#gv-policy-save"); pg.wait_for_timeout(1500)
check("the interval is saved", "90 days" in txt(pg, "#gv-policy-meaning"), txt(pg, "#gv-policy-meaning"))

# ---- retire, then isolation and audit ----
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/aigov")
r = A("POST", f"/changes/{A('POST', '/changes', TUNDE, dict(system_id=sid1, change_kind='PROMPT_CHANGE', from_version='p1', to_version='p2', description='The instructions were reworded', effective_on=D(-1), testing_summary='Ran 20 sample invoices'))['id']}/reject", DARA, {"reason": "Not enough invoices were tested"})
check("a change can be rejected with a reason", r.get("status") == "REJECTED", r)
check("a system with nothing waiting can be retired", A("POST", f"/systems/{sid1}/retire", DARA, {"reason": "Replaced by another tool"}).get("status") == "RETIRED")
check("a change cannot be recorded on a retired system", st(A("POST", "/changes", TUNDE, dict(system_id=sid1, change_kind="MODEL_UPDATE", from_version="2.0", to_version="2.1", description="After retirement", effective_on=D(-1), testing_summary="Ran 20 sample invoices"))) == 409)
check("the other company sees none of it", A("GET", "/systems", OTHER, org="Other") == [] and A("GET", "/changes", OTHER, org="Other") == [] and A("GET", "/incidents", OTHER, org="Other") == [])
check("the other company cannot read or act on a record", st(A("GET", f"/systems/{sid2}", OTHER, org="Other")) == 404 and st(A("POST", f"/incidents/{i3['id']}/review", OTHER, {"cause": "Approving from outside the company", "corrective_action": "Approving from outside the company too"}, org="Other")) == 404)
check("the other company's overview is empty", A("GET", "/overview", OTHER, org="Other")["counts"]["systems_approved"] == 0)
acts = api("GET", "/_audit", DARA, "Meridian")["actions"]
for a_ in ("AIGOV_SYSTEM_PROPOSED", "AIGOV_SYSTEM_APPROVED", "AIGOV_SYSTEM_REVIEWED", "AIGOV_SYSTEM_RETIRED", "AIGOV_CHANGE_RECORDED", "AIGOV_CHANGE_APPROVED", "AIGOV_CHANGE_REJECTED", "AIGOV_INCIDENT_RECORDED", "AIGOV_INCIDENT_REVIEWED", "AIGOV_INCIDENT_VOIDED", "AIGOV_POLICY_SET"):
    check(f"the audit trail has {a_}", a_ in acts, [x for x in acts if "AIGOV" in x])
check("no typed content is copied into the audit trail", "chart of accounts" not in str(api("GET", "/_audit", DARA, "Meridian")))
check("no page errors in the browser", not errs, errs[:3])
finish(p, b)
