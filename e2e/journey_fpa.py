"""Browser journey: Planning and KPIs (Stage 18). Run via e2e/run_all.py."""
import json
from datetime import date, datetime, timedelta, timezone

from common import *

TODAY = datetime.now(timezone.utc).date()          # the server works in UTC dates
D = lambda n: (TODAY + timedelta(days=n)).isoformat()
LM = (TODAY.replace(day=1) - timedelta(days=1))                 # last month end
LM2 = (LM.replace(day=1) - timedelta(days=1))                   # the month end before
def hrefs(pg): return [a.get_attribute("href") for a in pg.locator(".app-sidebar a").all()]
def tab(pg, name):
    pg.click(f"#fp-tab-{name}"); pg.wait_for_timeout(900)
def body(pg): return pg.inner_text("body")
def err(pg): return txt(pg, ".alert-error")
def A(m, path, who, bodyj=None, org="Meridian"): return api(m, "/fpa" + path, who, org, bodyj)

start_web()
p, b, pg, errs = session()
mem = api("GET", "/organisations/x/members", DARA, "Meridian")
UID = {m["role"]: m["user_id"] for m in mem}
DARA_ID, AISHA_ID, KWAME_ID = UID["OWNER"], UID["ACCOUNTANT"], UID["APPROVER"]

# ---- Aisha defines a KPI and names Dara as its owner ----
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/fpa")
check("the menu offers Planning and KPIs", "#/fpa" in hrefs(pg), hrefs(pg))
check("the banner says it records and checks, not calculates", "does not calculate a KPI from the ledger" in txt(pg, "#fp-banner") and "cannot be changed" in txt(pg, "#fp-banner"), txt(pg, "#fp-banner"))
check("nothing needs attention yet", "Nothing needs attention" in txt(pg, "#fp-attention"), txt(pg, "#fp-attention"))
tab(pg, "kpis")
pg.click("#fp-kpi-save"); pg.wait_for_timeout(300)
check("an empty KPI form is stopped with a plain sentence", "name" in txt(pg, "#kpi-problem").lower(), txt(pg, "#kpi-problem"))
opts = pg.locator("#fp-kpi-owner option").evaluate_all("o => o.map(x => x.value)")
check("only people who can record readings are offered as owners", DARA_ID in opts and AISHA_ID in opts and KWAME_ID not in opts, opts)
pg.fill("#fp-kpi-name", "Gross margin"); pg.fill("#fp-kpi-desc", "Share left after direct costs"); pg.select_option("#fp-kpi-owner", DARA_ID)
pg.fill("#fp-kpi-cur", "ngn"); pg.fill("#fp-kpi-target", "1,000.505"); pg.fill("#fp-kpi-from", D(-150))
pg.fill("#fp-kpi-source", "Monthly management accounts"); pg.fill("#fp-kpi-method", "Revenue less direct costs")
pg.click("#fp-kpi-save"); pg.wait_for_timeout(300)
check("a target with too many decimals is stopped", "decimal" in txt(pg, "#kpi-problem").lower(), txt(pg, "#kpi-problem"))
pg.fill("#fp-kpi-target", "1,000.00"); pg.click("#fp-kpi-save"); pg.wait_for_timeout(1500)
check("KPI defined and waiting for a different approver", "KP-001" in txt(pg, "#fp-notice") and "Waiting for approval" in txt(pg, "#fp-kpis"), txt(pg, "#fp-kpis") + txt(pg, "#kpi-problem") + err(pg))
K = {k["ref"]: k["id"] for k in A("GET", "/kpis", AISHA)}["KP-001"]
check("the definer cannot approve (server)", A("POST", f"/kpis/{K}/approve", AISHA, {}).get("status") in (403, 409))
check("the owner cannot approve their own target (server)", A("POST", f"/kpis/{K}/approve", DARA, {}).get("status") in (403, 409))
check("a reading cannot be recorded before approval (server)", A("POST", f"/kpis/{K}/readings", DARA, {"period_end": LM.isoformat(), "value": "900", "source_note": "From the management accounts"}).get("status") in (403, 409))

# ---- Kwame approves; Dara accepts and records ----
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/fpa"); tab(pg, "kpis")
check("an approver sees no define form", pg.locator("#fp-kpi-save").count() == 0)
pg.click("#fp-kpi-open-KP-001"); pg.wait_for_timeout(700)
pg.click("#fp-kpi-KP-001-approve"); pg.wait_for_timeout(1500)
check("KPI approved", "approved" in txt(pg, "#fp-notice").lower() and "approved" in txt(pg, "#fp-kpis").lower(), txt(pg, "#fp-notice") + err(pg))
check("an unaccepted owner cannot record yet (server)", A("POST", f"/kpis/{K}/readings", DARA, {"period_end": LM.isoformat(), "value": "900", "source_note": "From the management accounts"}).get("status") in (403, 409))

sign_in(pg, *DARA, "Meridian"); goto(pg, "/fpa"); tab(pg, "kpis")
pg.click("#fp-kpi-open-KP-001"); pg.wait_for_timeout(700)
check("the owner is told to accept ownership first", "Accept ownership" in body(pg), body(pg)[:300])
pg.click("#fp-kpi-KP-001-accept"); pg.wait_for_timeout(1500)
check("ownership accepted", pg.locator("#fp-rd-save").count() == 1, txt(pg, "#fp-notice") + err(pg))
pg.fill("#fp-rd-date", D(0)); pg.fill("#fp-rd-value", "900"); pg.fill("#fp-rd-source", "short"); pg.click("#fp-rd-save"); pg.wait_for_timeout(400)
check("a short source note is stopped", "came from" in txt(pg, "#reading-problem"), txt(pg, "#reading-problem"))
pg.fill("#fp-rd-source", "From the management accounts"); pg.click("#fp-rd-save"); pg.wait_for_timeout(1200)
check("a period end that is not a month end is refused by the server", "month" in err(pg).lower() or "month" in txt(pg, "#reading-problem").lower(), err(pg) + txt(pg, "#reading-problem"))
pg.fill("#fp-rd-date", LM.isoformat()); pg.click("#fp-rd-save"); pg.wait_for_timeout(1500)
check("reading recorded and judged close to target", "KR-001" in txt(pg, "#fp-notice") and "close to target" in body(pg).lower(), txt(pg, "#fp-notice") + err(pg))
check("the reading says no document is attached", "No document attached" in body(pg), body(pg)[:300])
check("the recorder cannot review their own reading", pg.locator("#fp-rd-review-KR-001").count() == 0)
RD = A("GET", f"/kpis/{K}", DARA)["readings"][0]["id"]
check("the recorder cannot review (server)", A("POST", f"/kpis/{K}/readings/{RD}/review", DARA, {}).get("status") in (403, 409))
check("someone who is not the owner cannot record (server)", A("POST", f"/kpis/{K}/readings", AISHA, {"period_end": LM2.isoformat(), "value": "950", "source_note": "From the management accounts"}).get("status") in (403, 409))

# ---- a correction supersedes the old reading ----
pg.fill("#fp-rd-date", LM.isoformat()); pg.fill("#fp-rd-value", "1,000.00"); pg.fill("#fp-rd-source", "Restated management accounts"); pg.click("#fp-rd-save"); pg.wait_for_timeout(1200)
check("a second reading for the same period needs a reason", "correction" in (err(pg) + txt(pg, "#reading-problem")).lower() or "reason" in (err(pg) + txt(pg, "#reading-problem")).lower(), err(pg) + txt(pg, "#reading-problem"))
pg.fill("#fp-rd-correction", "The first figure left out one invoice"); pg.click("#fp-rd-save"); pg.wait_for_timeout(1500)
check("correction recorded; old reading kept as superseded", "KR-002" in txt(pg, "#fp-notice") and "replaced" in body(pg).lower() and "on target" in body(pg).lower(), txt(pg, "#fp-notice") + err(pg))

# ---- Kwame reviews the live reading ----
sign_in(pg, *KWAME, "Meridian"); goto(pg, "/fpa"); tab(pg, "kpis")
pg.click("#fp-kpi-open-KP-001"); pg.wait_for_timeout(700)
check("a different approver is offered review and reject", pg.locator("#fp-rd-review-KR-002").count() == 1 and pg.locator("#fp-rd-reject-KR-002").count() == 1)
pg.click("#fp-rd-review-KR-002"); pg.wait_for_timeout(1500)
check("reading reviewed", "reviewed" in txt(pg, "#fp-notice").lower(), txt(pg, "#fp-notice") + err(pg))

# ---- forecasts: Aisha registers; Dara records the actual; Kwame confirms ----
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/fpa"); tab(pg, "forecasts")
pg.fill("#fp-fc-metric", "Revenue"); pg.fill("#fp-fc-cur", "ngn"); pg.fill("#fp-fc-date", D(-5)); pg.fill("#fp-fc-value", "100"); pg.fill("#fp-fc-basis", "Run-rate of the last three months"); pg.click("#fp-fc-save"); pg.wait_for_timeout(1200)
check("a forecast for a period that has already ended is refused", "not yet ended" in err(pg) + txt(pg, "#forecast-problem") or "back-dated" in err(pg) + txt(pg, "#forecast-problem"), err(pg) + txt(pg, "#forecast-problem"))
pg.fill("#fp-fc-date", D(10)); pg.click("#fp-fc-save"); pg.wait_for_timeout(1500)
check("forecast registered, stamped with today", "FC-001" in txt(pg, "#fp-notice") and f"made on {D(0)}" in body(pg), txt(pg, "#fp-notice") + err(pg))
FC = A("GET", "/forecasts", AISHA)[0]["id"]
check("an actual cannot be recorded before the period ends (server)", A("POST", f"/forecasts/{FC}/actual", DARA, {"value": "90", "source_note": "Closed management accounts"}).get("status") == 409)
api("GET", "/_fpa_clock?days=20", DARA, "Meridian")           # test-only: move the Planning clock past the forecast period
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/fpa"); tab(pg, "forecasts")
check("after the period ends, the forecaster is not offered the actual", "Period ended: actual needed" in txt(pg, "#fp-forecasts") and pg.locator(f"#fp-act-value-FC-001").count() == 0, txt(pg, "#fp-forecasts"))
check("the forecaster cannot record the actual (server)", A("POST", f"/forecasts/{FC}/actual", AISHA, {"value": "90", "source_note": "Closed management accounts"}).get("status") in (403, 409))

sign_in(pg, *DARA, "Meridian"); goto(pg, "/fpa"); tab(pg, "forecasts")
pg.fill("#fp-act-value-FC-001", "80"); pg.fill("#fp-act-source-FC-001", "Closed management accounts"); pg.click("#fp-fc-FC-001-actual"); pg.wait_for_timeout(1500)
check("actual recorded: forecast too high by 20.00", "Too high" in body(pg) and "20.00" in body(pg) and "25.00%" in body(pg), txt(pg, "#fp-notice") + err(pg))
check("the person who recorded the actual cannot confirm it", pg.locator("#fp-fc-FC-001-confirm").count() == 0 and "third person" in body(pg))
check("the recorder cannot confirm (server)", A("POST", f"/forecasts/{FC}/actual/confirm", DARA, {}).get("status") in (403, 409))
tab(pg, "accuracy")
check("accuracy ignores an unconfirmed actual", "No forecast has a confirmed actual yet" in body(pg) and "waiting for confirmation: 1" in body(pg), txt(pg, "#fp-accuracy") + body(pg)[:300])

sign_in(pg, *KWAME, "Meridian"); goto(pg, "/fpa"); tab(pg, "forecasts")
pg.click("#fp-fc-FC-001-confirm"); pg.wait_for_timeout(1500)
check("actual confirmed by a third person", "confirmed" in txt(pg, "#fp-notice").lower(), txt(pg, "#fp-notice") + err(pg))
tab(pg, "accuracy")
acc = txt(pg, "#fp-accuracy")
check("accuracy shows the exact figures and says there are too few to mean much", "25.00" in acc and "Fewer than 3: not meaningful yet" in acc and "Forecasts counted: 1" in acc, acc[:500])
pg.select_option("#fp-acc-lead", "60"); pg.wait_for_timeout(1500)
check("a minimum lead filter excludes it", "Forecasts counted: 0" in body(pg) or "No forecast has a confirmed actual yet" in body(pg), body(pg)[:300])

# ---- overview, settings and isolation ----
tab(pg, "overview")
check("approver sees the settings form", pg.locator("#fp-policy-save").count() == 1)
pg.fill("#fp-policy-watch", "99"); pg.click("#fp-policy-save"); pg.wait_for_timeout(400)
check("an out-of-range setting is stopped", "0 to 50" in body(pg), body(pg)[:300])
pg.fill("#fp-policy-watch", "5"); pg.click("#fp-policy-save"); pg.wait_for_timeout(1500)
check("settings saved", "saved" in txt(pg, "#fp-notice").lower() or "Settings" in txt(pg, "#fp-notice"), txt(pg, "#fp-notice") + err(pg))
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/fpa"); tab(pg, "overview")
check("an accountant sees no settings form", pg.locator("#fp-policy-save").count() == 0)
check("the other company sees none of it", A("GET", "/kpis", OTHER, org="Other") == [] and A("GET", f"/kpis/{K}", OTHER, org="Other").get("status") == 404 and A("GET", f"/forecasts/{FC}", OTHER, org="Other").get("status") == 404)
check("the other company cannot act on it", A("POST", f"/kpis/{K}/retire", OTHER, {"note": "No right to do this"}, org="Other").get("status") in (403, 404))
api("GET", "/_fpa_clock?days=0", DARA, "Meridian")

acts = api("GET", "/_audit", DARA, "Meridian")["actions"]
need_ = ["FPA_KPI_DEFINED", "FPA_KPI_APPROVED", "FPA_KPI_OWNERSHIP_ACCEPTED", "FPA_KPI_READING_RECORDED", "FPA_KPI_READING_REVIEWED", "FPA_FORECAST_REGISTERED", "FPA_ACTUAL_RECORDED", "FPA_ACTUAL_CONFIRMED", "FPA_POLICY_SET"]
check("every step was written to the audit trail", all(x in acts for x in need_), [x for x in need_ if x not in acts])
check("no page errors in the browser", not errs, errs[:3])
finish(p, b)
