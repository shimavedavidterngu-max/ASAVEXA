import { test, describe } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { Fpa } from "../src/pages/Fpa.js";
import * as F from "../src/lib/fpa.js";
import { ApiClient } from "../src/api/client.js";
import { PERMISSIONS, can } from "../src/lib/permissions.js";
import { NAV_GROUPS } from "../src/lib/home.js";
import * as E from "../src/lib/entityConfig.js";

const text = (v) => JSON.stringify(v);
const noop = new Proxy({}, { get: () => () => {} });
const reading = (o = {}) => ({ id: "r1", ref: "KR-001", kpi_id: "k1", kpi_ref: "KP-001", period_end: "2026-01-31", value: "900.00", source_note: "From the January management accounts", evidence: [], status: "RECORDED", recorded_by: "u3", recorded_at: "2026-02-15T09:00",
  reviewed_by: null, superseded_by: null, history: [], judgement: "WATCH", shortfall_pct: "10.00", gap: "-100.00", traceable: false, ...o });
const kpi = (o = {}) => ({ id: "k1", ref: "KP-001", name: "Gross margin", description: "Share left after direct costs", unit: "AMOUNT", currency: "NGN", direction: "HIGHER_BETTER", frequency: "MONTHLY", owner: "u3", owner_accepted: true, data_source: "Monthly management accounts",
  method: "Revenue less direct costs", target: "1000.00", watch_pct: 10, effective_from: "2026-01-01", status: "ACTIVE", created_by: "u1", approved_by: "u2", history: [], owner_history: [], meaning: "Higher is better. On target when at or above 1000.00 (NGN); close to target when short by no more than 10% of the target.",
  latest: reading(), judgement: "WATCH", unreviewed: true, next_period_end: "2026-02-28", due: "2026-03-15", overdue: false, can_record: true, live_readings: 1, untraceable: 1, readings: [reading()], ...o });
const fc = (o = {}) => ({ id: "f1", ref: "FC-001", metric: "Revenue", unit: "AMOUNT", currency: "NGN", period_end: "2026-02-28", made_on: "2026-02-01", value: "100.00", basis: "Run-rate of the last three months", kpi_id: null, kpi_ref: null, forecaster: "u1", status: "OPEN",
  actual: null, withdrawn_note: null, history: [], lead_days: 27, actual_due: false, error: null, ...o });
const ovw = () => ({ counts: { kpis: 2, active: 1, retired: 0, forecasts: 3, forecasts_confirmed: 1 }, attention: [{ kind: "KPI_OFF_TARGET", count: 1, text: "KPI(s) are off target on their latest reading." }, { kind: "FORECAST_BIAS", count: 1, text: "Revenue (NGN): forecasts have run high by 12.50% over 4 periods." }],
  owners: [{ owner: "u3", kpis: 2, overdue: 1, off_target: 1, not_accepted: 0 }], limitations: ["ASAVEXA records what people type in."], policy: { watch_pct: 10, grace_days: 15, accuracy_pct: 10, min_items: 3, meaning: "A new KPI is flagged close to target when ..." } });
const acc = () => ({ groups: [{ metric: "Revenue", unit: "AMOUNT", currency: "NGN", n: 2, wape: "8.33", bias: "-2.78", mean_abs_error: "10.00", over: 1, under: 1, exact: 0, within: 1, hit_rate: "50.00", average_lead_days: "20.0", enough: false }],
  forecasters: [{ forecaster: "u1", n: 2, within: 1, over: 1, under: 1, hit_rate: "50.00", enough: false }], counted: 2, excluded_short_lead: 0, awaiting_confirmation: 1, open_due: 1, accuracy_pct: 10, min_items: 3, min_lead_days: 0, meaning: "Forecast error is forecast minus confirmed actual." });
const members = [{ user_id: "u3", role: "ACCOUNTANT", status: "ACTIVE" }, { user_id: "u2", role: "APPROVER", status: "ACTIVE" }, { user_id: "u4", role: "MANAGER", status: "ACTIVE" }, { user_id: "u5", role: "ACCOUNTANT", status: "REMOVED" }];
const state = (o = {}) => ({ tab: "overview", options: { kpis: [{ id: "k1", ref: "KP-001", name: "Gross margin", unit: "AMOUNT", currency: "NGN" }] }, ov: ovw(), kpis: [kpi()], forecasts: [fc()], accuracy: acc(), members, vault: [], forecastFilter: "", minLead: 0, sel: { kpi: null },
  forms: { ...JSON.parse(JSON.stringify(F.EMPTY)), policy: F.policyForm(ovw().policy) }, notes: {}, formError: null, busy: false, error: null, notice: null, ...o });
const page = (o = {}, role = "OWNER", me = "u9") => Fpa({ fp: state(o), role, userId: me, loading: false, onRetry() {}, actions: noop });

describe("permissions and helpers", () => {
  test("roles", () => {
    for (const r of ["OWNER", "MANAGER", "FINANCE_OFFICER"]) assert.ok(F.canPrepare(r) && F.canApprove(r), r);
    assert.ok(F.canPrepare("ACCOUNTANT") && !F.canApprove("ACCOUNTANT")); assert.ok(F.canApprove("APPROVER") && !F.canPrepare("APPROVER"));
    for (const r of ["ADMINISTRATOR", "REVIEWER", "AUDITOR", "EXTERNAL_AUDITOR", "READ_ONLY"]) assert.ok(!F.canPrepare(r) && !F.canApprove(r), r);
    assert.equal(PERMISSIONS.FPA_PREPARE, "fpa:prepare"); assert.equal(PERMISSIONS.FPA_APPROVE, "fpa:approve");
    for (const r of ["OWNER", "MANAGER", "FINANCE_OFFICER", "ACCOUNTANT", "APPROVER"]) assert.ok(can(r, PERMISSIONS.REPORTING_READ), r);
  });
  test("only people who can record readings are offered as owners", () => { assert.deepEqual(F.ownerChoices(members).map((m) => m.user_id), ["u3", "u4"]); assert.deepEqual(F.ownerChoices(null), []); });
  test("people are shown as You or a short id", () => { assert.equal(F.who("u1", "u1"), "You"); assert.equal(F.who("abcdefghijkl", "u1"), "abcdefgh"); assert.equal(F.who(null, "u1"), "—"); });
  test("values keep the unit's decimal places and may be negative", () => {
    assert.equal(F.valueProblem("-1,234.50", "x", "AMOUNT"), ""); assert.match(F.valueProblem("1.005", "x", "AMOUNT"), /2 decimal places/); assert.equal(F.valueProblem("1.2500", "x", "RATIO"), ""); assert.match(F.valueProblem("1.25001", "x", "RATIO"), /4 decimal/);
    assert.equal(F.valueProblem("7", "x", "COUNT"), ""); assert.match(F.valueProblem("7.5", "x", "COUNT"), /whole number/); assert.match(F.valueProblem("", "x", "DAYS"), /required/); assert.match(F.valueProblem("abc", "x", "PERCENT"), /number/);
  });
});

describe("payload builders", () => {
  const good = { name: " Gross margin ", description: "Share left after direct costs", unit: "AMOUNT", currency: "ngn", direction: "HIGHER_BETTER", frequency: "MONTHLY", owner: "u3", data_source: "Monthly management accounts", method: "Revenue less direct costs", target: "1,000.00", watch_pct: "", effective_from: "2026-01-01" };
  test("kpi", () => {
    assert.deepEqual(F.kpiPayload(good).body, { name: "Gross margin", description: "Share left after direct costs", unit: "AMOUNT", currency: "NGN", direction: "HIGHER_BETTER", frequency: "MONTHLY", owner: "u3", data_source: "Monthly management accounts", method: "Revenue less direct costs", target: "1000.00", effective_from: "2026-01-01" });
    assert.equal(F.kpiPayload({ ...good, watch_pct: "7" }).body.watch_pct, 7); assert.equal("currency" in F.kpiPayload({ ...good, unit: "COUNT", target: "5" }).body, false);
    for (const [k, v, re] of [["name", "ab", /name/], ["description", "no", /measures/], ["currency", "N", /currency/], ["owner", "", /owner/], ["data_source", "short", /comes from/], ["method", "short", /calculated/], ["target", "x", /number/], ["watch_pct", "51", /0 to 50/], ["effective_from", "2026-02-30", /real date/]])
      assert.match(F.kpiPayload({ ...good, [k]: v }).problem, re, k);
    assert.match(F.kpiPayload({ ...good, unit: "COUNT", target: "5.5" }).problem, /whole number/);
  });
  test("reading", () => {
    const f = { period_end: "2026-01-31", value: "1,250.50", source_note: "From the January management accounts", evidence_id: "ev1", correction_note: "" };
    assert.deepEqual(F.readingPayload(f, "AMOUNT").body, { period_end: "2026-01-31", value: "1250.50", source_note: "From the January management accounts", evidence_ids: ["ev1"] });
    assert.equal(F.readingPayload({ ...f, evidence_id: "", correction_note: "The first figure left out one invoice" }, "AMOUNT").body.correction_note, "The first figure left out one invoice");
    assert.deepEqual(F.readingPayload({ ...f, evidence_id: "" }, "AMOUNT").body.evidence_ids, []);
    for (const [k, v, re] of [["period_end", "soon", /real date/], ["value", "1.005", /decimal/], ["source_note", "short", /came from/], ["correction_note", "short", /correction/]]) assert.match(F.readingPayload({ ...f, [k]: v }, "AMOUNT").problem, re, k);
  });
  test("forecast and actual", () => {
    const f = { metric: "Revenue", unit: "AMOUNT", currency: "ngn", period_end: "2026-03-31", value: "100", basis: "Run-rate of the last three months", kpi_id: "" };
    assert.deepEqual(F.forecastPayload(f).body, { metric: "Revenue", unit: "AMOUNT", currency: "NGN", period_end: "2026-03-31", value: "100", basis: "Run-rate of the last three months" });
    assert.equal(F.forecastPayload({ ...f, kpi_id: "k1" }).body.kpi_id, "k1"); assert.equal("currency" in F.forecastPayload({ ...f, unit: "PERCENT", value: "5" }).body, false);
    for (const [k, v, re] of [["metric", "ab", /forecast/], ["currency", "N", /currency/], ["period_end", "x", /real date/], ["value", "x", /number/], ["basis", "short", /how the forecast/i]]) assert.match(F.forecastPayload({ ...f, [k]: v }).problem, re, k);
    assert.deepEqual(F.actualPayload({ value: "90", source_note: "Closed management accounts", evidence_id: "" }, "AMOUNT").body, { value: "90", source_note: "Closed management accounts", evidence_ids: [] });
    assert.match(F.actualPayload({ value: "", source_note: "Closed management accounts" }, "AMOUNT").problem, /required/); assert.match(F.actualPayload({ value: "9", source_note: "short" }, "AMOUNT").problem, /came from/);
  });
  test("reassign and settings", () => {
    assert.deepEqual(F.reassignPayload({ owner: "u4", reason: " Moved to budgets " }).body, { owner: "u4", reason: "Moved to budgets" }); assert.match(F.reassignPayload({ owner: "", reason: "Moved to budgets" }).problem, /new owner/); assert.match(F.reassignPayload({ owner: "u4", reason: "no" }).problem, /reason/);
    assert.deepEqual(F.policyPayload({ watch_pct: "5", grace_days: "0", accuracy_pct: "100", min_items: "1" }).body, { watch_pct: 5, grace_days: 0, accuracy_pct: 100, min_items: 1 });
    for (const [k, v, re] of [["watch_pct", "51", /0 to 50/], ["grace_days", "91", /0 to 90/], ["accuracy_pct", "101", /0 to 100/], ["min_items", "0", /1 to 50/], ["min_items", "x", /1 to 50/]]) assert.match(F.policyPayload({ watch_pct: "10", grace_days: "15", accuracy_pct: "10", min_items: "3", [k]: v }).problem, re, k);
    assert.deepEqual(F.policyForm({ watch_pct: 10, grace_days: 15, accuracy_pct: 10, min_items: 3 }), { watch_pct: "10", grace_days: "15", accuracy_pct: "10", min_items: "3" });
  });
});

describe("which buttons a person can see", () => {
  test("approve is hidden from the definer and from the owner", () => {
    const d = kpi({ status: "DRAFT", owner_accepted: false });
    assert.ok(F.kpiMoves(d, "u2", "APPROVER").includes("approve")); assert.ok(!F.kpiMoves(d, "u1", "OWNER").includes("approve")); assert.ok(!F.kpiMoves(d, "u3", "OWNER").includes("approve")); assert.ok(!F.kpiMoves(d, "u2", "ACCOUNTANT").includes("approve"));
    assert.match(F.waitingText(d, "u3", "OWNER"), /You are the owner/); assert.match(F.waitingText(d, "u1", "OWNER"), /different approver/); assert.equal(F.waitingText(kpi(), "u1", "OWNER"), "");
  });
  test("only the owner is offered to accept, and only until they have", () => {
    const d = kpi({ owner_accepted: false }); assert.ok(F.kpiMoves(d, "u3", "ACCOUNTANT").includes("accept")); assert.ok(!F.kpiMoves(d, "u1", "OWNER").includes("accept")); assert.ok(!F.kpiMoves(kpi(), "u3", "ACCOUNTANT").includes("accept"));
    assert.ok(!F.kpiMoves(kpi({ owner_accepted: false, owner: "u2" }), "u2", "APPROVER").includes("accept"));                                   // an approver-only owner cannot accept
  });
  test("owner change and retire are for approvers, never on a retired KPI", () => {
    assert.deepEqual(F.kpiMoves(kpi(), "u2", "APPROVER"), ["owner", "retire"]); assert.deepEqual(F.kpiMoves(kpi(), "u1", "ACCOUNTANT"), []); assert.deepEqual(F.kpiMoves(kpi({ status: "RETIRED" }), "u2", "APPROVER"), []);
  });
  test("recording a reading needs the owner, an approved KPI, accepted ownership and the right role", () => {
    assert.ok(F.canRecordReading(kpi(), "u3", "ACCOUNTANT")); assert.ok(!F.canRecordReading(kpi(), "u1", "OWNER")); assert.ok(!F.canRecordReading(kpi({ owner_accepted: false }), "u3", "ACCOUNTANT"));
    assert.ok(!F.canRecordReading(kpi({ status: "DRAFT" }), "u3", "ACCOUNTANT")); assert.ok(!F.canRecordReading(kpi(), "u3", "APPROVER"));
  });
  test("readings: another approver may review or reject; never the recorder", () => {
    assert.deepEqual(F.readingMoves(reading(), "u2", "APPROVER"), ["review", "reject"]); assert.deepEqual(F.readingMoves(reading(), "u3", "OWNER"), []); assert.deepEqual(F.readingMoves(reading(), "u2", "ACCOUNTANT"), []); assert.deepEqual(F.readingMoves(reading({ status: "REVIEWED" }), "u2", "APPROVER"), []);
  });
  test("forecasts: withdraw is the forecaster's, the actual is someone else's, confirmation is a third person's", () => {
    assert.deepEqual(F.forecastMoves(fc(), "u1", "ACCOUNTANT"), ["withdraw"]); assert.deepEqual(F.forecastMoves(fc(), "u3", "ACCOUNTANT"), []);
    assert.deepEqual(F.forecastMoves(fc({ actual_due: true }), "u3", "ACCOUNTANT"), ["actual"]); assert.deepEqual(F.forecastMoves(fc({ actual_due: true }), "u1", "ACCOUNTANT"), ["withdraw"]);
    const r = fc({ status: "ACTUAL_RECORDED", actual: { recorded_by: "u3", value: "90.00" } });
    assert.deepEqual(F.forecastMoves(r, "u2", "APPROVER"), ["confirm", "reject"]); assert.deepEqual(F.forecastMoves(r, "u3", "OWNER"), []); assert.deepEqual(F.forecastMoves(r, "u1", "OWNER"), []);
  });
  test("wording", () => {
    assert.match(F.shortfallText(reading()), /10.00% of the target/); assert.match(F.shortfallText(reading({ shortfall_pct: null, judgement: "OFF_TARGET" })), /target is zero/); assert.equal(F.shortfallText(reading({ judgement: "ON_TARGET" })), "");
    assert.equal(F.headline(kpi({ latest: null })), "No reading yet"); assert.match(F.headline(kpi()), /900.00 for the period ending 2026-01-31/); assert.equal(F.unitLabel(kpi()), "NGN"); assert.equal(F.unitLabel(kpi({ unit: "RATIO", currency: null })), "Ratio");
  });
});

describe("page", () => {
  test("banner says it records and checks and that a forecast cannot change", () => {
    const t = text(page()); assert.match(t, /does not calculate a KPI from the ledger/); assert.match(t, /cannot be changed/); assert.match(t, /fp-banner/);
  });
  test("overview: attention, owners, settings only editable by an approver", () => {
    const t = text(page({}, "APPROVER")); assert.match(t, /KPI_OFF_TARGET/); assert.match(t, /run high by 12.50%/); assert.match(t, /Forecasts with a confirmed actual: 1/); assert.match(t, /data-owner/); assert.match(t, /fp-policy-save/);
    assert.doesNotMatch(text(page({}, "ACCOUNTANT")), /fp-policy-save/);
  });
  test("kpis: approve for a different approver; none for the owner; define form only for preparers; owners are only people who can record", () => {
    const d = kpi({ status: "DRAFT", owner_accepted: false, latest: null, judgement: "NOT_MEASURED", unreviewed: false });
    const a = text(page({ tab: "kpis", kpis: [d] }, "APPROVER", "u2")); assert.match(a, /fp-kpi-KP-001-approve/); assert.doesNotMatch(a, /fp-kpi-save/);
    const o = text(page({ tab: "kpis", kpis: [d] }, "OWNER", "u3")); assert.doesNotMatch(o, /fp-kpi-KP-001-approve/); assert.match(o, /You are the owner/); assert.match(o, /fp-kpi-save/); assert.match(o, /fp-kpi-KP-001-accept/);
    assert.doesNotMatch(o, /"value":"u2"/); assert.match(o, /"value":"u4"/);
  });
  test("a KPI card shows owner, acceptance, judgement, unreviewed and the meaning in words", () => {
    const t = text(page({ tab: "kpis" }, "OWNER", "u1")); assert.match(t, /Close to target/); assert.match(t, /Reading waiting for review/); assert.match(t, /On target when at or above 1000.00/); assert.match(t, /Short of the target by 10.00% of the target/);
    assert.match(text(page({ tab: "kpis", kpis: [kpi({ overdue: true, owner_accepted: false })] }, "OWNER", "u1")), /Reading overdue.*Owner has not accepted/);
  });
  test("readings: shown with source and file fingerprint; untraced ones say so; review buttons for another approver", () => {
    const ev = reading({ evidence: [{ evidence_id: "e1", filename: "jan.pdf", file_hash: "a".repeat(64) }], traceable: true }), k = kpi({ readings: [ev, reading({ id: "r2", ref: "KR-002" })] });
    const t = text(page({ tab: "kpis", kpis: [k], sel: { kpi: k } }, "APPROVER", "u2")); assert.match(t, /fingerprint aaaaaaaaaaaa/); assert.match(t, /No document attached/); assert.match(t, /fp-rd-review-KR-001/); assert.match(t, /fp-rd-reject-KR-002/); assert.match(t, /note-rd-k1/);
    const own = text(page({ tab: "kpis", kpis: [k], sel: { kpi: k } }, "OWNER", "u3")); assert.doesNotMatch(own, /fp-rd-review-KR-001/); assert.match(own, /fp-rd-save/);
    const other = text(page({ tab: "kpis", kpis: [k], sel: { kpi: k } }, "OWNER", "u1")); assert.doesNotMatch(other, /fp-rd-save/); assert.match(other, /Only the owner records readings/);
    assert.match(text(page({ tab: "kpis", kpis: [kpi({ owner_accepted: false })], sel: { kpi: kpi({ owner_accepted: false }) } }, "ACCOUNTANT", "u3")), /Accept ownership of this KPI before recording/);
  });
  test("forecasts: stamped date and lead time shown; withdraw for the forecaster; actual for someone else once the period has ended", () => {
    const t = text(page({ tab: "forecasts", forecasts: [fc()] }, "ACCOUNTANT", "u1")); assert.match(t, /made on 2026-02-01 \(27 days ahead\)/); assert.match(t, /fp-fc-FC-001-withdraw/); assert.match(t, /cannot be changed or back-dated/);
    const d = text(page({ tab: "forecasts", forecasts: [fc({ actual_due: true })] }, "ACCOUNTANT", "u3")); assert.match(d, /Period ended: actual needed/); assert.match(d, /fp-act-value-FC-001/); assert.match(d, /fp-fc-FC-001-actual/); assert.doesNotMatch(d, /fp-fc-FC-001-withdraw/);
  });
  test("forecast error and confirmation", () => {
    const x = fc({ status: "ACTUAL_RECORDED", actual: { value: "80.00", source_note: "Closed management accounts", recorded_by: "u3", confirmed_by: null, evidence: [] }, error: { error: "20.00", abs_error: "20.00", pct_error: "25.00", direction: "OVER", within: false } });
    const t = text(page({ tab: "forecasts", forecasts: [x] }, "APPROVER", "u2")); assert.match(t, /Too high: forecast minus actual is 20.00 \(25.00% of the actual\)/); assert.match(t, /Outside the accuracy band/); assert.match(t, /fp-fc-FC-001-confirm/);
    assert.match(text(page({ tab: "forecasts", forecasts: [x] }, "OWNER", "u3")), /Waiting for a third person to confirm/);
    assert.match(text(page({ tab: "forecasts", forecasts: [fc({ status: "CONFIRMED", actual: { value: "0.00", source_note: "x", recorded_by: "u3", confirmed_by: "u2" }, error: { error: "5.00", abs_error: "5.00", pct_error: null, direction: "OVER", within: false } })] })), /the actual is zero, so no percentage/);
  });
  test("accuracy: figures, the not-meaningful warning, counts and the lead filter", () => {
    const t = text(page({ tab: "accuracy" })); assert.match(t, /8.33/); assert.match(t, /-2.78/); assert.match(t, /Fewer than 3: not meaningful yet/); assert.match(t, /Forecasts counted: 2/); assert.match(t, /Actuals waiting for confirmation: 1/); assert.match(t, /fp-acc-lead/); assert.match(t, /by forecaster|By forecaster/i);
    const none = acc(); none.groups = []; none.forecasters = []; assert.match(text(page({ tab: "accuracy", accuracy: none })), /No forecast has a confirmed actual yet/);
  });
  test("errors, notices and loading", () => {
    assert.match(text(page({ error: "Boom" })), /Boom/); assert.match(text(page({ notice: "Saved." })), /fp-notice/);
    assert.match(text(Fpa({ fp: state(), role: "OWNER", userId: "u1", loading: true, onRetry() {}, actions: noop })), /Loading|loading/i);
    assert.match(text(page({ tab: "kpis", formError: { form: "kpi", text: "Give the KPI a name." } })), /kpi-problem/);
  });
  test("every tab renders for every role without throwing", () => {
    for (const role of ["OWNER", "ADMINISTRATOR", "ACCOUNTANT", "FINANCE_OFFICER", "APPROVER", "REVIEWER", "MANAGER", "AUDITOR", "EXTERNAL_AUDITOR", "READ_ONLY"]) for (const [tab] of F.TABS)
      assert.doesNotThrow(() => page({ tab, sel: { kpi: kpi() }, forecasts: [fc(), fc({ id: "f2", ref: "FC-002", actual_due: true }), fc({ id: "f3", ref: "FC-003", status: "ACTUAL_RECORDED", actual: { recorded_by: "u3", value: "1" } })] }, role, "u2"), `${role}/${tab}`);
  });
});

describe("wiring", () => {
  test("client calls the right paths and verbs", async () => {
    const calls = []; const c = new ApiClient("http://x"); c._request = async (m, p, o) => { calls.push([m, p, o && o.body, o && o.query]); return {}; };
    await c.fpOverview(); await c.setFpPolicy({ watch_pct: 5 }); await c.defineFpKpi({}); await c.fpKpiStep("k/1", "approve", "ok"); await c.acceptFpKpi("k1"); await c.changeFpOwner("k1", { owner: "u4" }); await c.addFpReading("k1", {}); await c.fpReadingStep("k1", "r1", "review", "fine");
    await c.fpForecasts("OPEN"); await c.registerFpForecast({}); await c.fpForecastStep("f1", "actual/confirm", "ok"); await c.addFpActual("f1", {}); await c.fpAccuracy(14); await c.fpKpis(); await c.fpKpi("k1");
    assert.deepEqual(calls.map((x) => x.slice(0, 2)), [["GET", "/fpa/overview"], ["PUT", "/fpa/policy"], ["POST", "/fpa/kpis"], ["POST", "/fpa/kpis/k%2F1/approve"], ["POST", "/fpa/kpis/k1/accept"], ["POST", "/fpa/kpis/k1/owner"], ["POST", "/fpa/kpis/k1/readings"],
      ["POST", "/fpa/kpis/k1/readings/r1/review"], ["GET", "/fpa/forecasts"], ["POST", "/fpa/forecasts"], ["POST", "/fpa/forecasts/f1/actual/confirm"], ["POST", "/fpa/forecasts/f1/actual"], ["GET", "/fpa/accuracy"], ["GET", "/fpa/kpis"], ["GET", "/fpa/kpis/k1"]]);
    assert.deepEqual(calls[8][3], { status: "OPEN" }); assert.deepEqual(calls[12][3], { min_lead_days: 14 }); assert.deepEqual(calls[3][2], { note: "ok" });
  });
  test("the page is in the menu, in the workspaces group, behind reporting:read, searchable, and can be hidden by organisation set-up", () => {
    assert.ok(NAV_GROUPS.find((g) => g.id === "workspaces").paths.includes("/fpa"));
    const app = fs.readFileSync(new URL("../src/app.js", import.meta.url), "utf8");
    assert.match(app, /path: "\/fpa", label: "Planning and KPIs", permission: PERMISSIONS\.REPORTING_READ/); assert.match(app, /path: "\/fpa", name: "fpa"/); assert.match(app, /renderFpaPage\(authState\)/);
    assert.match(app, /uiState\.fp = null; loadedOnce\.delete\("fpLoading"\)/);
    assert.equal(E.WORKSPACE_PATHS.fpa, "/fpa"); assert.deepEqual(E.filterNavByWorkspaces([{ path: "/fpa" }, { path: "/cyber" }], ["cyber"]).map((i) => i.path), ["/cyber"]);
  });
  test("the page uses only the shared client and never does arithmetic on figures", () => {
    const src = fs.readFileSync(new URL("../src/pages/Fpa.js", import.meta.url), "utf8") + fs.readFileSync(new URL("../src/lib/fpa.js", import.meta.url), "utf8");
    assert.doesNotMatch(src, /fetch\(|XMLHttpRequest|parseFloat|toFixed|Number\((r|k|x|g)\.(value|target|shortfall_pct|bias|wape)\)/);
  });
});
