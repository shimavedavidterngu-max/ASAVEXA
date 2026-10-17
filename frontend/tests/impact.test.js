import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { Impact } from "../src/pages/Impact.js";
import * as F from "../src/lib/impact.js";
import { ApiClient } from "../src/api/client.js";
import { NAV_GROUPS } from "../src/lib/home.js";
import * as E from "../src/lib/entityConfig.js";

const text = (v) => JSON.stringify(v);
const noop = new Proxy({}, { get: () => () => {} });
const rd = (o = {}) => ({ no: 1, period_end: "2026-03-31", value: "380.00", source_note: "Counted from the register", status: "PROPOSED", proposed_by: "u1", decision_note: null, ...o });
const ind = (o = {}) => ({ id: "i1", ref: "IM-001", title: "Households with clean water", programme_ref: "WASH-1", unit: "households", direction: "INCREASE", baseline: "200.00", target: "1000.00", baseline_date: "2026-01-01", target_date: "2026-12-31",
  status: "PROPOSED", proposed_by: "u1", latest_value: null, latest_period_end: null, progress_pct: null, expected_pct: null, state: null, stale: false, pending_readings: 0, confirmed_readings: 0, decision_note: null, close_note: null, readings: [], history: [], ...o });
const open = (o = {}) => ind({ status: "APPROVED", state: "ON_TRACK", latest_value: "380.00", latest_period_end: "2026-03-31", progress_pct: "22.50", expected_pct: "24.45", ...o });
const ovw = () => ({ counts: { proposed: 1, approved: 4, rejected: 0, closed: 1 }, states: { NO_DATA: 1, ACHIEVED: 1, ON_TRACK: 1, BEHIND: 1, OVERDUE: 0 }, attention: [{ kind: "BEHIND_TARGET", count: 1, text: "indicator(s) are behind the progress expected by today." }],
  setting: { tolerance_points: 10, stale_days: 120, meaning: "Flagged when more than 10 points behind." }, limitations: ["ASAVEXA verifies no result."] });
const state = (o = {}) => ({ tab: "overview", ov: ovw(), indicators: [open()], sel: { indicator: null }, forms: { ...JSON.parse(JSON.stringify(F.EMPTY)), setting: { tolerance_points: "10", stale_days: "120" } }, notes: {}, formError: null, busy: false, error: null, notice: null, ...o });
const page = (o = {}, role = "OWNER", me = "u9") => Impact({ st: state(o), role, userId: me, loading: false, onRetry() {}, actions: noop });
const sel = (x, role = "OWNER", me = "u9") => page({ tab: "indicators", sel: { indicator: x } }, role, me);

describe("permissions and buttons", () => {
  test("who can prepare and approve", () => {
    for (const r of ["OWNER", "ADMINISTRATOR", "MANAGER", "AUDITOR"]) assert.ok(F.canPrepare(r), r);
    for (const r of ["OWNER", "APPROVER", "MANAGER"]) assert.ok(F.canApprove(r), r);
    for (const r of ["ACCOUNTANT", "READ_ONLY", "EXTERNAL_AUDITOR"]) assert.ok(!F.canPrepare(r) && !F.canApprove(r), r);
  });
  test("button rules", () => {
    assert.ok(F.canDecideIndicator(ind(), "APPROVER", "u9")); assert.ok(!F.canDecideIndicator(ind({ proposed_by: "u9" }), "APPROVER", "u9")); assert.ok(!F.canDecideIndicator(open(), "APPROVER", "u9"));
    assert.ok(F.canRead_(open(), "AUDITOR")); assert.ok(!F.canRead_(ind(), "AUDITOR")); assert.ok(!F.canRead_(open(), "READ_ONLY"));
    assert.ok(F.canDecideReading(open(), rd(), "APPROVER", "u9")); assert.ok(!F.canDecideReading(open(), rd({ proposed_by: "u9" }), "APPROVER", "u9")); assert.ok(!F.canDecideReading(open(), rd({ status: "CONFIRMED" }), "APPROVER", "u9"));
    assert.ok(F.canClose(open(), "APPROVER")); assert.ok(!F.canClose(open({ pending_readings: 1 }), "APPROVER")); assert.ok(!F.canClose(open(), "AUDITOR"));
  });
});

describe("payload builders", () => {
  const f = { title: "Households with clean water", programme_ref: "WASH-1", unit: "households", direction: "INCREASE", baseline: "200", target: "1,000", baseline_date: "2026-01-01", target_date: "2026-12-31" };
  test("indicator", () => {
    assert.deepEqual(F.indicatorPayload(f).body, { title: "Households with clean water", programme_ref: "WASH-1", unit: "households", direction: "INCREASE", baseline: "200", target: "1000", baseline_date: "2026-01-01", target_date: "2026-12-31" });
    for (const [o, re] of [[{ title: "ab" }, /title/i], [{ programme_ref: "x" }, /programme/i], [{ unit: "" }, /unit/i], [{ direction: "UP" }, /increase or decrease/], [{ baseline: "abc" }, /baseline/i], [{ target: "1.234" }, /target/i], [{ baseline_date: "2026-02-30" }, /real date/],
      [{ target_date: "2026-01-01" }, /after the baseline/], [{ target: "100" }, /higher than the baseline/], [{ target_date: "2037-01-02" }, /ten years/], [{ direction: "DECREASE" }, /lower than the baseline/]]) assert.match(F.indicatorPayload({ ...f, ...o }).problem || "", re, text(o));
    assert.equal(F.indicatorPayload({ ...f, baseline: "0" }).body.baseline, "0"); assert.ok(F.indicatorPayload({ ...f, direction: "DECREASE", baseline: "40", target: "10" }).body);
  });
  test("reading", () => {
    const g = { period_end: "2026-03-31", value: "380", source_note: "Counted from the register" };
    assert.deepEqual(F.readingPayload(g, { indicator: open() }).body, g); assert.equal(F.readingPayload({ ...g, value: "0" }).body.value, "0");
    for (const [o, re] of [[{ period_end: "2026-02-30" }, /real date/], [{ value: "x" }, /value/i], [{ value: "-1" }, /value/i], [{ source_note: "short" }, /source/i], [{ period_end: "2025-12-31" }, /before the baseline/]]) assert.match(F.readingPayload({ ...g, ...o }, { indicator: open() }).problem || "", re, text(o));
  });
  test("setting", () => {
    assert.deepEqual(F.settingPayload({ tolerance_points: "0", stale_days: "60" }).body, { tolerance_points: 0, stale_days: 60 });
    for (const [a, b] of [["-1", "60"], ["101", "60"], ["x", "60"], ["10", "0"], ["10", "731"], ["1.5", "60"]]) assert.ok(F.settingPayload({ tolerance_points: a, stale_days: b }).problem, a + b);
  });
});

describe("page", () => {
  test("overview", () => {
    const t = text(page());
    for (const s of ["Behind: 1", "Target reached: 1", "On track: 1", "No reading yet: 1", "Open: 4", "ASAVEXA verifies no result", "imp-banner", "Behind target", "imp-set-save"]) assert.ok(t.includes(s), s);
    assert.ok(!text(page({}, "READ_ONLY")).includes("imp-set-save"));
  });
  test("proposing is for preparers only", () => {
    assert.ok(text(page({ tab: "indicators" }, "AUDITOR")).includes("imp-in-save")); assert.ok(!text(page({ tab: "indicators" }, "READ_ONLY")).includes("imp-in-save"));
  });
  test("list shows progress and the stale flag", () => {
    const t = text(page({ tab: "indicators", indicators: [open({ stale: true })] })); for (const s of ["progress 22.50 percent", "On track", "Reading is stale", "Programme WASH-1"]) assert.ok(t.includes(s), s);
  });
  test("a proposed indicator: another person decides", () => {
    assert.ok(text(sel(ind(), "APPROVER", "u9")).includes("imp-in-approve")); const own = text(sel(ind({ proposed_by: "u9" }), "APPROVER", "u9")); assert.ok(!own.includes("imp-in-approve")); assert.ok(own.includes("a different person must decide it"));
    const prep = text(sel(ind(), "AUDITOR", "u9")); assert.ok(!prep.includes("imp-in-approve")); assert.ok(!prep.includes("imp-rd-save"));
  });
  test("an open indicator: progress, readings, closing", () => {
    const x = open({ readings: [rd(), rd({ no: 2, status: "CONFIRMED", period_end: "2026-02-28", value: "300.00" })], pending_readings: 1 });
    const prep = text(sel(x, "AUDITOR", "u9")); for (const s of ["imp-rd-save", "imp-rd-date", "imp-rd-source", "progress 22.50 percent", "expected by today 24.45 percent"]) assert.ok(prep.includes(s), s); assert.ok(!prep.includes("imp-rd-1-confirm"));
    const appr = text(sel(x, "APPROVER", "u9")); for (const s of ["imp-rd-1-confirm", "imp-rd-1-reject"]) assert.ok(appr.includes(s), s); assert.ok(!appr.includes("imp-rd-2-confirm")); assert.ok(!appr.includes("imp-cl-save"));
    const own = text(sel(x, "APPROVER", "u1")); assert.ok(!own.includes("imp-rd-1-confirm")); assert.ok(own.includes("a different person must decide it"));
    assert.ok(text(sel(open(), "APPROVER", "u9")).includes("imp-cl-save"));
  });
  test("no reading yet; closed; read-only", () => {
    assert.ok(text(sel(open({ latest_value: null, progress_pct: null, state: "NO_DATA" }))).includes("No confirmed reading yet; expected by today 24.45 percent"));
    assert.ok(text(sel(ind({ status: "CLOSED", close_note: "Programme has finished" }))).includes("Programme has finished"));
    const t = text(sel(open({ readings: [rd()], pending_readings: 1 }), "READ_ONLY")); for (const s of ["imp-rd-save", "imp-rd-1-confirm", "imp-cl-save", "imp-in-approve"]) assert.ok(!t.includes(s), s); assert.ok(t.includes("380.00"));
  });
  test("errors, problems and loading", () => {
    assert.ok(text(page({ error: "Boom" })).includes("Boom")); assert.ok(text(page({ tab: "indicators", formError: { form: "indicator", text: "The title needs at least 3 characters." } })).includes("indicator-problem"));
    assert.ok(text(Impact({ st: state(), role: "OWNER", userId: "u9", loading: true, onRetry() {}, actions: noop })).length > 0);
  });
});

describe("wiring", () => {
  test("client methods hit the right paths", async () => {
    const calls = []; const c = new ApiClient("http://x"); c.request = async (m, p, b) => { calls.push([m, p, b]); return {}; };
    c.get = (p) => c.request("GET", p); c.post = (p, b) => c.request("POST", p, b); c.put = (p, b) => c.request("PUT", p, b);
    await c.impOptions(); await c.impOverview(); await c.impSetting(); await c.setImpSetting({}); await c.impIndicators(); await c.createImpIndicator({}); await c.impIndicator("a b"); await c.approveImpIndicator("i1", ""); await c.rejectImpIndicator("i1", "r"); await c.closeImpIndicator("i1", "c");
    await c.addImpReading("i1", {}); await c.confirmImpReading("i1", 2, ""); await c.rejectImpReading("i1", 2, "r");
    assert.deepEqual(calls.map((x) => x[0] + " " + x[1]), ["GET /impact/options", "GET /impact/overview", "GET /impact/setting", "PUT /impact/setting", "GET /impact/indicators", "POST /impact/indicators", "GET /impact/indicators/a%20b", "POST /impact/indicators/i1/approve", "POST /impact/indicators/i1/reject",
      "POST /impact/indicators/i1/close", "POST /impact/indicators/i1/readings", "POST /impact/indicators/i1/readings/2/confirm", "POST /impact/indicators/i1/readings/2/reject"]);
  });
  test("home group and entity path", () => {
    assert.ok(NAV_GROUPS.some((g) => g.paths.includes("/impact"))); assert.equal(E.WORKSPACE_PATHS.impact, "/impact");
  });
});
