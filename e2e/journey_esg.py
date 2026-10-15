"""Browser journey: ESG and carbon (Stage 30). Run via e2e/run_all.py. The browser user and the user making API calls are always different people (one login at a time per person)."""
from datetime import datetime, timedelta, timezone

from common import *

TODAY = datetime.now(timezone.utc).date()
D = lambda n: (TODAY + timedelta(days=n)).isoformat()
def hrefs(pg): return [a.get_attribute("href") for a in pg.locator(".app-sidebar a").all()]
def tab(pg, name):
    pg.click(f"#es-tab-{name}"); pg.wait_for_timeout(900)
def body(pg): return pg.inner_text("body")
def err(pg): return txt(pg, ".alert-error")
def A(m, path, who, bodyj=None, org="Meridian"): return api(m, "/esg" + path, who, org, bodyj)
def st(r): return r.get("status") if isinstance(r, dict) else None
def eid(ref, who): return next(i["id"] for i in A("GET", "/entries", who) if i["ref"] == ref)
def tid(ref, who): return next(i["id"] for i in A("GET", "/targets", who) if i["ref"] == ref)
def fill(pg, **ids):
    for k, v in ids.items(): pg.fill("#" + k.replace("_", "-"), v)
def ent(who, **kw):
    d = dict(scope="SCOPE_2", category="ELECTRICITY", description="Grid electricity for the office", period_start="2025-01-01", period_end="2025-12-31", quantity="1000", unit="kWh", factor="0.5", factor_source="Grid operator factor table", factor_year=2024); d.update(kw); return A("POST", "/entries", who, d)
def tg(who, **kw):
    d = dict(label="Scope one cut", scope="SCOPE_1", baseline_year=2024, baseline_tonnes="4.000", reduction_pct="10", target_year=2025); d.update(kw); return A("POST", "/targets", who, d)

start_web()
p, b, pg, errs = session()

# ---- an accountant has no business here ----
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/esg")
check("the menu does not offer the workspace to an accountant", "#/esg" not in hrefs(pg), hrefs(pg))
check("typing the address shows no content", "Propose an emission record" not in body(pg), body(pg)[:200])
check("the server refuses an accountant (overview)", st(A("GET", "/overview", AISHA)) == 403)
check("the server refuses an accountant (entries)", st(A("GET", "/entries", AISHA)) == 403)

# ---- Tunde proposes a record and a target ----
sign_in(pg, *TUNDE, "Meridian"); goto(pg, "/esg")
check("the menu offers the workspace", "#/esg" in hrefs(pg), hrefs(pg))
check("the banner says it supplies no factors and measures nothing", "supplies no emission factors" in txt(pg, "#es-banner") and "measures nothing" in txt(pg, "#es-banner") and "not an assured sustainability report" in txt(pg, "#es-banner"), txt(pg, "#es-banner"))
check("nothing needs attention yet", "Nothing needs attention" in txt(pg, "#es-attention"), txt(pg, "#es-attention"))
tab(pg, "entries")
pg.click("#es-en-save"); pg.wait_for_timeout(300)
check("an empty form is stopped with a plain sentence", "description" in txt(pg, "#entry-problem").lower(), txt(pg, "#entry-problem"))
fill(pg, es_en_desc="Diesel for the generator", es_en_start="2025-06-01", es_en_end="2026-01-31", es_en_qty="1250.5", es_en_unit="litres", es_en_factor="2.68", es_en_fsrc="National factor table 2024", es_en_fyear="2024"); pg.click("#es-en-save"); pg.wait_for_timeout(300)
check("a period across two years is stopped", "one calendar year" in txt(pg, "#entry-problem"), txt(pg, "#entry-problem"))
fill(pg, es_en_start="2025-01-01", es_en_end="2025-12-31", es_en_qty="1250.55555"); pg.click("#es-en-save"); pg.wait_for_timeout(300)
check("a five-decimal quantity is stopped", "4 decimals" in txt(pg, "#entry-problem") or "at most 4" in txt(pg, "#entry-problem"), txt(pg, "#entry-problem"))
fill(pg, es_en_qty="1250.5", es_en_end="2099-12-31"); pg.click("#es-en-save"); pg.wait_for_timeout(1200)
check("a period that starts and ends in different years or the future is refused", bool(err(pg) + txt(pg, "#entry-problem")), err(pg) + txt(pg, "#entry-problem"))
fill(pg, es_en_end="2025-12-31"); pg.click("#es-en-save"); pg.wait_for_timeout(1500)
check("the record is worked out exactly", "ER-001" in txt(pg, "[data-entry='ER-001']") and "1250.5 litres x 2.68" in txt(pg, "[data-entry='ER-001']") and "= 3351.34 kg CO2e (3.351 tonnes)" in txt(pg, "[data-entry='ER-001']"), txt(pg, "#es-notice") + err(pg))
check("it waits for a different person and the proposer cannot verify", "Waiting for a decision" in txt(pg, "[data-entry='ER-001']") and pg.locator("#es-en-ER-001-verify").count() == 0 and pg.locator("#es-en-ER-001-approve").count() == 0)
e1 = eid("ER-001", DARA)
check("an administrator cannot verify (no approve permission)", st(A("POST", f"/entries/{e1}/verify", TUNDE, {})) == 403)
check("a float quantity is refused", st(ent(DARA, quantity=1000.5)) == 400)
check("a zero factor is refused", st(ent(DARA, factor="0")) == 400)
check("an unknown scope is refused", st(ent(DARA, scope="SCOPE_9")) == 400)
tab(pg, "targets")
fill(pg, es_tg_label="Cut total emissions", es_tg_by="2024", es_tg_bt="1250.500", es_tg_pct="42.5", es_tg_ty="2024"); pg.click("#es-tg-save"); pg.wait_for_timeout(300)
check("a target year that is not after the baseline is stopped", "after the baseline" in txt(pg, "#target-problem"), txt(pg, "#target-problem"))
fill(pg, es_tg_pct="100.5", es_tg_ty="2025"); pg.click("#es-tg-save"); pg.wait_for_timeout(300)
check("a reduction over 100 percent is stopped", "100 percent" in txt(pg, "#target-problem") or "at most" in txt(pg, "#target-problem"), txt(pg, "#target-problem"))
fill(pg, es_tg_pct="42.5"); pg.click("#es-tg-save"); pg.wait_for_timeout(1500)
check("the target is worked out exactly", "TG-001" in txt(pg, "[data-tgt='TG-001']") and "target for 2025: 719.038 tonnes" in txt(pg, "[data-tgt='TG-001']"), txt(pg, "#es-notice") + err(pg))

# ---- Kwame decides ----
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/esg"); tab(pg, "entries")
check("the approver sees no entry form", pg.locator("#es-en-save").count() == 0)
pg.fill("#es-en-ER-001-note", "ok"); pg.click("#es-en-ER-001-approve"); pg.wait_for_timeout(500)
check("a short verification note is stopped", "10 characters" in err(pg) or "note" in err(pg).lower(), err(pg))
pg.fill("#es-en-ER-001-note", ""); pg.click("#es-en-ER-001-approve"); pg.wait_for_timeout(1500)
check("a different person verifies", "Verified" in txt(pg, "[data-entry='ER-001']"), txt(pg, "[data-entry='ER-001']") + err(pg))
check("a decided record cannot be decided again", st(A("POST", f"/entries/{e1}/reject", DARA, {"reason": "Trying to reject it later"})) == 409)
e2 = ent(DARA, factor_year=2018); e3 = ent(TUNDE, description="Staff flights", scope="SCOPE_3", category="TRAVEL", quantity="200", unit="km", factor="0.17")
e4 = ent(TUNDE, description="Duplicate electricity entry", quantity="999")
check("the records are numbered and worked out", (e2.get("ref"), e2.get("kg_co2e"), e3.get("ref"), e3.get("kg_co2e")) == ("ER-002", "500.00", "ER-003", "34.00"), (e2, e3))
check("the owner cannot verify their own record", st(A("POST", f"/entries/{e2['id']}/verify", DARA, {})) == 403)
check("the owner cannot reject their own record either", st(A("POST", f"/entries/{e2['id']}/reject", DARA, {"reason": "Rejecting my own record"})) == 403)
goto(pg, "/esg"); tab(pg, "entries")
pg.click("#es-en-ER-002-approve"); pg.wait_for_timeout(1500)
check("the second record is verified", "Verified" in txt(pg, "[data-entry='ER-002']"), txt(pg, "[data-entry='ER-002']") + err(pg))
check("an old factor is flagged", "Old factor" in txt(pg, "[data-entry='ER-002']"), txt(pg, "[data-entry='ER-002']"))
pg.click("#es-en-ER-004-reject"); pg.wait_for_timeout(500)
check("rejecting without a reason is stopped", "10 characters" in err(pg) or "reason" in err(pg).lower(), err(pg))
pg.fill("#es-en-ER-004-note", "Duplicate of the October invoice"); pg.click("#es-en-ER-004-reject"); pg.wait_for_timeout(1500)
check("a different person rejects with a reason", "Rejected" in txt(pg, "[data-entry='ER-004']") and "Duplicate of the October invoice" in txt(pg, "[data-entry='ER-004']"), txt(pg, "[data-entry='ER-004']") + err(pg))
A("POST", f"/entries/{e3['id']}/verify", DARA, {})
check("the records proposed by another person are verified through the API too", A("GET", f"/entries/{e3['id']}", DARA).get("status") == "VERIFIED")
t2 = tg(DARA); t3 = tg(DARA, label="Scope two cut", scope="SCOPE_2", baseline_tonnes="0.400")
check("the targets are worked out", (t2.get("ref"), t2.get("target_tonnes"), t3.get("ref"), t3.get("target_tonnes")) == ("TG-002", "3.600", "TG-003", "0.360"), (t2, t3))
check("the owner cannot approve their own target", st(A("POST", f"/targets/{t2['id']}/approve", DARA, {})) == 403)
check("the owner cannot reject their own target", st(A("POST", f"/targets/{t2['id']}/reject", DARA, {"reason": "Rejecting my own target"})) == 403)
goto(pg, "/esg"); tab(pg, "targets")
for ref in ("TG-001", "TG-002", "TG-003"):
    pg.click(f"#es-tg-{ref}-approve"); pg.wait_for_timeout(1500)
check("a different person approves the targets", all("Approved" in txt(pg, f"[data-tgt='{r}']") for r in ("TG-001", "TG-002", "TG-003")), txt(pg, "#es-targets") + err(pg))
check("an approved target cannot be decided again", st(A("POST", f"/targets/{t2['id']}/reject", DARA, {"reason": "Trying to reject it later"})) == 409)

# ---- overview ----
sign_in(pg, *DARA, "Meridian"); goto(pg, "/esg"); tab(pg, "overview")
check("only verified records are totalled, by year and scope", "2025: 3.885 tonnes CO2e (3885.34 kg)" in txt(pg, "[data-year='2025']") and "Scope 1: 3.351 tonnes (3351.34 kg)" in txt(pg, "[data-scope='SCOPE_1']") and "Scope 2: 0.500 tonnes (500.00 kg)" in txt(pg, "[data-scope='SCOPE_2']") and "Scope 3: 0.034 tonnes (34.00 kg)" in txt(pg, "[data-scope='SCOPE_3']"), txt(pg, "#es-years"))
check("the all-scopes target is within target with an exact change", "in 2025, 3.885 tonnes verified so far against a target of 719.038 tonnes (-99.69 percent against the 2024 baseline of 1250.5)" in txt(pg, "[data-target='TG-001']") and "Within target" in txt(pg, "[data-target='TG-001']"), txt(pg, "[data-target='TG-001']"))
check("the scope 1 target is within target", "3.351 tonnes verified so far against a target of 3.600 tonnes (-16.23 percent" in txt(pg, "[data-target='TG-002']") and "Within target" in txt(pg, "[data-target='TG-002']"), txt(pg, "[data-target='TG-002']"))
check("the scope 2 target is above target", "0.500 tonnes verified so far against a target of 0.360 tonnes (25.00 percent" in txt(pg, "[data-target='TG-003']") and "Above target" in txt(pg, "[data-target='TG-003']"), txt(pg, "[data-target='TG-003']"))
check("an old factor needs attention", "OLD FACTORS" in txt(pg, "#es-attention").upper(), txt(pg, "#es-attention"))
check("the counts add up", "Records verified: 3" in txt(pg, "#es-counts") and "Records rejected: 1" in txt(pg, "#es-counts") and "Targets approved: 3" in txt(pg, "#es-counts"), txt(pg, "#es-counts"))
pg.fill("#es-set-years", "0"); pg.click("#es-set-save"); pg.wait_for_timeout(400)
check("a limit of 0 years is stopped", "1 to 20" in txt(pg, "#setting-problem"), txt(pg, "#setting-problem"))
pg.fill("#es-set-years", "10"); pg.click("#es-set-save"); pg.wait_for_timeout(1500)
check("the setting is saved", "10 years" in txt(pg, "#es-setting-meaning"), txt(pg, "#es-setting-meaning"))
check("the longer limit clears the attention item", "OLD FACTORS" not in txt(pg, "#es-attention").upper(), txt(pg, "#es-attention"))
check("an administrator cannot change the setting", st(A("PUT", "/setting", TUNDE, {"factor_max_age_years": 3})) == 403)

# ---- isolation and audit ----
check("the other company sees none of it", A("GET", "/entries", OTHER, org="Other") == [] and A("GET", "/targets", OTHER, org="Other") == [])
check("the other company cannot read or act on a record", st(A("GET", f"/entries/{e1}", OTHER, org="Other")) == 404 and st(A("POST", f"/entries/{e1}/verify", OTHER, {}, org="Other")) == 404)
check("the other company's overview is empty", A("GET", "/overview", OTHER, org="Other")["years"] == [])
acts = api("GET", "/_audit", KWAME, "Meridian")["actions"]
for a_ in ("ESG_ENTRY_PROPOSED", "ESG_ENTRY_VERIFIED", "ESG_ENTRY_REJECTED", "ESG_TARGET_PROPOSED", "ESG_TARGET_APPROVED", "ESG_SETTING_SET"):
    check(f"the audit trail has {a_}", a_ in acts, [x for x in acts if "ESG" in x])
aud = str(api("GET", "/_audit", KWAME, "Meridian"))
check("no typed content is copied into the audit trail", "Diesel" not in aud and "generator" not in aud and "National factor" not in aud and "3351" not in aud and "October invoice" not in aud and "Scope one cut" not in aud and "Grid operator" not in aud)
check("no page errors in the browser", not errs, errs[:3])
finish(p, b)
