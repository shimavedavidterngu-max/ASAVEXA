import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { Pension } from "../src/pages/Pension.js";
import * as F from "../src/lib/pension.js";
import { ApiClient } from "../src/api/client.js";
import { NAV_GROUPS } from "../src/lib/home.js";
import * as E from "../src/lib/entityConfig.js";

const text = (v) => JSON.stringify(v);
const noop = new Proxy({}, { get: () => () => {} });
const row = (o = {}) => ({ no: 1, status: "PROPOSED", proposed_by: "u1", decision_note: null, ...o });
const con = (o = {}) => row({ period: "2026-01", employer_amount: "1000.50", employee_amount: "500.25", paid_on: "2026-02-10", due_date: "2026-02-15", late: false, total: "1500.75", ...o });
const val = (o = {}) => row({ as_of: "2026-03-01", assets: "900000.00", liabilities: "1000000.00", source_note: "From the actuary report", ...o });
const obl = (o = {}) => row({ title: "File the annual return", due_date: "2026-04-20", status: "OPEN", overdue: false, due_soon: true, done_late: false, completed_on: null, completed_by: null, completion_note: null, ...o });
const cf = (o = {}) => row({ person_ref: "TR-03", declared_on: "2026-03-01", nature: "Holds shares in a fund manager", ...o });
const sch = (o = {}) => ({ id: "s1", ref: "PS-001", name: "Staff retirement scheme", scheme_ref: "TRUST-1", currency: "NGN", scheme_type: "DEFINED_CONTRIBUTION", start_period: "2026-01", due_day: 15, description: "The staff scheme run by the trustees", status: "PROPOSED", proposed_by: "u1",
  decision_note: null, close_note: null, employer_total: "0.00", employee_total: "0.00", total_contributions: "0.00", late_contributions: 0, missing_periods: [], latest_valuation: null, funding_ratio_pct: null, position: null, position_amount: null, below_floor: false, valuation_stale: false,
  overdue_obligations: 0, due_soon_obligations: 0, pending: 0, contributions: [], valuations: [], obligations: [], conflicts: [], history: [], ...o });
const open = (o = {}) => sch({ status: "APPROVED", ...o });
const ovw = () => ({ counts: { proposed: 1, approved: 2, rejected: 0, closed: 1 }, attention: [{ kind: "MISSING_CONTRIBUTIONS", count: 2, text: "month(s) are past their due date with no contribution recorded." }], by_currency: [{ currency: "NGN", schemes: 1, total_contributions: "1500.75" }, { currency: "USD", schemes: 1, total_contributions: "15.00" }],
  setting: { funding_floor_pct: 90, valuation_stale_days: 365, due_soon_days: 30, meaning: "Flagged below 90%." }, limitations: ["ASAVEXA holds no member data."] });
const state = (o = {}) => ({ tab: "overview", ov: ovw(), schemes: [open()], sel: { scheme: null }, forms: { ...JSON.parse(JSON.stringify(F.EMPTY)), setting: { funding_floor_pct: "90", valuation_stale_days: "365", due_soon_days: "30" } }, notes: {}, formError: null, busy: false, error: null, notice: null, ...o });
const page = (o = {}, role = "OWNER", me = "u9") => Pension({ st: state(o), role, userId: me, loading: false, onRetry() {}, actions: noop });
const sel = (x, role = "OWNER", me = "u9") => page({ tab: "schemes", sel: { scheme: x } }, role, me);

describe("permissions and buttons", () => {
  test("who can prepare and approve", () => {
    for (const r of ["OWNER", "ADMINISTRATOR", "MANAGER", "AUDITOR"]) assert.ok(F.canPrepare(r), r);
    for (const r of ["OWNER", "APPROVER", "MANAGER"]) assert.ok(F.canApprove(r), r);
    for (const r of ["ACCOUNTANT", "READ_ONLY", "EXTERNAL_AUDITOR"]) assert.ok(!F.canPrepare(r) && !F.canApprove(r), r);
  });
  test("button rules", () => {
    assert.ok(F.canDecideScheme(sch(), "APPROVER", "u9")); assert.ok(!F.canDecideScheme(sch({ proposed_by: "u9" }), "APPROVER", "u9")); assert.ok(!F.canDecideScheme(open(), "APPROVER", "u9"));
    assert.ok(F.canRecord(open(), "AUDITOR")); assert.ok(!F.canRecord(sch(), "AUDITOR")); assert.ok(!F.canRecord(open(), "READ_ONLY"));
    assert.ok(F.canDecideRow(open(), con(), "APPROVER", "u9")); assert.ok(!F.canDecideRow(open(), con({ proposed_by: "u9" }), "APPROVER", "u9")); assert.ok(!F.canDecideRow(open(), con({ status: "CONFIRMED" }), "APPROVER", "u9"));
    assert.ok(!F.canDecideRow(open(), obl(), "APPROVER", "u9"));                                                                                                  // open: nothing to confirm yet
    assert.ok(F.canDecideRow(open(), obl({ status: "DONE", completed_by: "u1" }), "APPROVER", "u9")); assert.ok(!F.canDecideRow(open(), obl({ status: "DONE", completed_by: "u9" }), "APPROVER", "u9"));
    assert.ok(F.canClose(open(), "APPROVER")); assert.ok(!F.canClose(open({ pending: 1 }), "APPROVER")); assert.ok(!F.canClose(open(), "AUDITOR"));
  });
});

describe("payload builders", () => {
  const f = { name: "Staff retirement scheme", scheme_ref: "TRUST-1", currency: "ngn", scheme_type: "HYBRID", start_period: "2026-01", due_day: "15", description: "The staff scheme run by the trustees" };
  test("scheme", () => {
    assert.deepEqual(F.schemePayload(f).body, { name: "Staff retirement scheme", scheme_ref: "TRUST-1", currency: "NGN", scheme_type: "HYBRID", start_period: "2026-01", due_day: 15, description: "The staff scheme run by the trustees" });
    for (const [o, re] of [[{ name: "ab" }, /name/i], [{ scheme_ref: "x" }, /reference/i], [{ currency: "NG" }, /three-letter/], [{ scheme_type: "X" }, /type/i], [{ start_period: "2026-13" }, /real month/], [{ start_period: "2999-01" }, /real month|future/], [{ due_day: "0" }, /due day/i], [{ due_day: "29" }, /due day/i], [{ due_day: "x" }, /due day/i], [{ description: "short" }, /description/i]]) assert.match(F.schemePayload({ ...f, ...o }).problem || "", re, text(o));
    assert.match(F.schemePayload({ ...f, start_period: "2100-12" }).problem, /future/);
  });
  test("contribution", () => {
    const g = { period: "2026-01", employer_amount: "1,000.50", employee_amount: "500.25", paid_on: "2026-02-10" };
    assert.deepEqual(F.contributionPayload(g, { scheme: open() }).body, { period: "2026-01", employer_amount: "1000.50", employee_amount: "500.25", paid_on: "2026-02-10" });
    assert.equal(F.contributionPayload({ ...g, employer_amount: "0" }, { scheme: open() }).body.employer_amount, "0");
    for (const [o, re] of [[{ period: "2026-13" }, /real month/], [{ period: "2025-12" }, /before the scheme/], [{ period: "2100-01" }, /future/], [{ employer_amount: "x" }, /employer/i], [{ employee_amount: "-1" }, /employee/i], [{ employer_amount: "1.234" }, /employer/i], [{ employer_amount: "0", employee_amount: "0" }, /At least one/],
      [{ paid_on: "2026-02-30" }, /real date/], [{ paid_on: "2999-01-01" }, /future/], [{ paid_on: "1999-12-31" }, /century/]]) assert.match(F.contributionPayload({ ...g, ...o }, { scheme: open() }).problem || "", re, text(o));
  });
  test("valuation", () => {
    const g = { as_of: "2026-03-01", assets: "900,000", liabilities: "1000000", source_note: "From the actuary report" };
    assert.deepEqual(F.valuationPayload(g).body, { as_of: "2026-03-01", assets: "900000", liabilities: "1000000", source_note: "From the actuary report" }); assert.equal(F.valuationPayload({ ...g, assets: "0" }).body.assets, "0");
    for (const [o, re] of [[{ as_of: "2026-02-30" }, /real date/], [{ as_of: "2999-01-01" }, /future/], [{ as_of: "1999-01-01" }, /century/], [{ assets: "x" }, /assets/i], [{ assets: "-1" }, /assets/i], [{ liabilities: "0" }, /more than zero/], [{ liabilities: "x" }, /liabilities/i], [{ source_note: "short" }, /source/i]]) assert.match(F.valuationPayload({ ...g, ...o }).problem || "", re, text(o));
  });
  test("obligation, completion, conflict", () => {
    assert.deepEqual(F.obligationPayload({ title: "File the return", due_date: "2026-04-20" }).body, { title: "File the return", due_date: "2026-04-20" });
    for (const [o, re] of [[{ title: "ab" }, /title/i], [{ due_date: "2026-02-30" }, /real date/], [{ due_date: "1999-01-01" }, /between 2000/], [{ due_date: "2101-01-01" }, /between 2000/]]) assert.match(F.obligationPayload({ title: "File the return", due_date: "2026-04-20", ...o }).problem || "", re, text(o));
    assert.deepEqual(F.completePayload({ completed_on: "2026-03-30", note: "Filed with the regulator" }).body, { completed_on: "2026-03-30", note: "Filed with the regulator" });
    for (const o of [{ completed_on: "x" }, { completed_on: "2999-01-01" }, { note: "short" }]) assert.ok(F.completePayload({ completed_on: "2026-03-30", note: "Filed with the regulator", ...o }).problem, text(o));
    const c = { person_ref: "TR-03", declared_on: "2026-03-01", nature: "Holds shares in a fund manager" }; assert.deepEqual(F.conflictPayload(c).body, c);
    for (const o of [{ person_ref: "x" }, { declared_on: "2026-02-30" }, { declared_on: "2999-01-01" }, { declared_on: "1999-01-01" }, { nature: "short" }]) assert.ok(F.conflictPayload({ ...c, ...o }).problem, text(o));
  });
  test("setting", () => {
    assert.deepEqual(F.settingPayload({ funding_floor_pct: "80", valuation_stale_days: "180", due_soon_days: "14" }).body, { funding_floor_pct: 80, valuation_stale_days: 180, due_soon_days: 14 });
    for (const [a, b, c] of [["0", "1", "1"], ["301", "1", "1"], ["x", "1", "1"], ["90", "0", "1"], ["90", "1501", "1"], ["90", "1", "0"], ["90", "1", "366"], ["1.5", "1", "1"]]) assert.ok(F.settingPayload({ funding_floor_pct: a, valuation_stale_days: b, due_soon_days: c }).problem, a + b + c);
  });
});

describe("page", () => {
  test("overview", () => {
    const t = text(page());
    for (const s of ["Open: 2", "ASAVEXA holds no member data", "pen-banner", "Missing contributions", "NGN: 1500.75", "USD: 15.00", "never added together", "pen-set-save"]) assert.ok(t.includes(s), s);
    assert.ok(!text(page({}, "READ_ONLY")).includes("pen-set-save"));
  });
  test("proposing is for preparers only", () => {
    assert.ok(text(page({ tab: "schemes" }, "AUDITOR")).includes("pen-sc-save")); assert.ok(!text(page({ tab: "schemes" }, "READ_ONLY")).includes("pen-sc-save"));
  });
  test("list shows flags", () => {
    const t = text(page({ tab: "schemes", schemes: [open({ below_floor: true, missing_periods: ["2026-01", "2026-02"], funding_ratio_pct: "85.00" })] })); for (const s of ["Below funding floor", "2 month(s) missing", "funded 85.00 percent", "Defined contribution"]) assert.ok(t.includes(s), s);
  });
  test("a proposed scheme: another person decides", () => {
    assert.ok(text(sel(sch(), "APPROVER", "u9")).includes("pen-sc-approve")); const own = text(sel(sch({ proposed_by: "u9" }), "APPROVER", "u9")); assert.ok(!own.includes("pen-sc-approve")); assert.ok(own.includes("a different person must decide it"));
    const prep = text(sel(sch(), "AUDITOR", "u9")); assert.ok(!prep.includes("pen-sc-approve")); assert.ok(!prep.includes("pen-co-save"));
  });
  test("an open scheme: totals, funding and forms", () => {
    const x = open({ employer_total: "1000.50", employee_total: "500.25", total_contributions: "1500.75", late_contributions: 1, missing_periods: ["2026-02"], funding_ratio_pct: "90.00", position: "DEFICIT", position_amount: "100000.00", below_floor: true, valuation_stale: true,
      latest_valuation: val({ status: "CONFIRMED" }), contributions: [con(), con({ no: 2, period: "2026-02", status: "CONFIRMED", late: true })], valuations: [val({ status: "CONFIRMED" })], obligations: [obl()], conflicts: [cf()], pending: 1 });
    const prep = text(sel(x, "AUDITOR", "u9")); for (const s of ["total 1500.75 NGN", "Paid late: 1", "2026-02", "Funding at 2026-03-01: 90.00 percent", "100000.00 NGN", "Valuation is stale", "Below funding floor", "(late)", "pen-co-save", "pen-va-save", "pen-ob-save", "pen-cf-save", "pen-ob-1-done"]) assert.ok(prep.includes(s), s);
    assert.ok(!prep.includes("pen-contributions-1-confirm"));
    const appr = text(sel(x, "APPROVER", "u9")); for (const s of ["pen-contributions-1-confirm", "pen-contributions-1-reject", "pen-conflicts-1-confirm"]) assert.ok(appr.includes(s), s); assert.ok(!appr.includes("pen-contributions-2-confirm")); assert.ok(!appr.includes("pen-cl-save"));
    const own = text(sel(x, "APPROVER", "u1")); assert.ok(!own.includes("pen-contributions-1-confirm")); assert.ok(own.includes("a different person must decide it"));
  });
  test("a done obligation is confirmed by someone else", () => {
    const x = open({ obligations: [obl({ status: "DONE", completed_on: "2026-03-30", completed_by: "u1", completion_note: "Filed online", due_soon: false })], pending: 1 });
    const t = text(sel(x, "APPROVER", "u9")); assert.ok(t.includes("pen-obligations-1-confirm")); assert.ok(t.includes("Filed online")); assert.ok(!text(sel(x, "APPROVER", "u1")).includes("pen-obligations-1-confirm"));
  });
  test("no valuation, closed, read-only", () => {
    assert.ok(text(sel(open())).includes("No confirmed valuation yet")); assert.ok(text(sel(open({ status: "CLOSED", close_note: "The scheme has wound up" }))).includes("The scheme has wound up"));
    assert.ok(text(sel(open({ pending: 0 }), "APPROVER", "u9")).includes("pen-cl-save"));
    const t = text(sel(open({ contributions: [con()], pending: 1 }), "READ_ONLY")); for (const s of ["pen-co-save", "pen-contributions-1-confirm", "pen-cl-save", "pen-sc-approve"]) assert.ok(!t.includes(s), s); assert.ok(t.includes("1500.75") || t.includes("1000.50"));
  });
  test("errors, problems and loading", () => {
    assert.ok(text(page({ error: "Boom" })).includes("Boom")); assert.ok(text(page({ tab: "schemes", formError: { form: "scheme", text: "The scheme name needs at least 3 characters." } })).includes("scheme-problem"));
    assert.ok(text(Pension({ st: state(), role: "OWNER", userId: "u9", loading: true, onRetry() {}, actions: noop })).length > 0);
  });
});

describe("wiring", () => {
  test("client methods hit the right paths", async () => {
    const calls = []; const c = new ApiClient("http://x"); c.request = async (m, p, b) => { calls.push([m, p, b]); return {}; };
    c.get = (p) => c.request("GET", p); c.post = (p, b) => c.request("POST", p, b); c.put = (p, b) => c.request("PUT", p, b);
    await c.penOptions(); await c.penOverview(); await c.penSetting(); await c.setPenSetting({}); await c.penSchemes(); await c.createPenScheme({}); await c.penScheme("a b"); await c.approvePenScheme("s1", ""); await c.rejectPenScheme("s1", "r"); await c.closePenScheme("s1", "c");
    await c.addPenContribution("s1", {}); await c.confirmPenContribution("s1", 2, ""); await c.rejectPenContribution("s1", 2, "r"); await c.addPenValuation("s1", {}); await c.confirmPenValuation("s1", 2, ""); await c.rejectPenValuation("s1", 2, "r");
    await c.addPenObligation("s1", {}); await c.completePenObligation("s1", 2, {}); await c.confirmPenObligation("s1", 2, ""); await c.rejectPenObligation("s1", 2, "r"); await c.addPenConflict("s1", {}); await c.confirmPenConflict("s1", 2, ""); await c.rejectPenConflict("s1", 2, "r");
    const want = ["GET /pension/options", "GET /pension/overview", "GET /pension/setting", "PUT /pension/setting", "GET /pension/schemes", "POST /pension/schemes", "GET /pension/schemes/a%20b", "POST /pension/schemes/s1/approve", "POST /pension/schemes/s1/reject", "POST /pension/schemes/s1/close"];
    for (const k of ["contributions", "valuations", "obligations", "conflicts"]) { if (k === "obligations") want.push("POST /pension/schemes/s1/obligations"); else want.push(`POST /pension/schemes/s1/${k}`); if (k === "obligations") want.push("POST /pension/schemes/s1/obligations/2/complete"); want.push(`POST /pension/schemes/s1/${k}/2/confirm`, `POST /pension/schemes/s1/${k}/2/reject`); }
    assert.deepEqual(calls.map((x) => x[0] + " " + x[1]), want);
  });
  test("home group and entity path", () => {
    assert.ok(NAV_GROUPS.some((g) => g.paths.includes("/pension"))); assert.equal(E.WORKSPACE_PATHS.pension, "/pension");
    for (const [kind, m] of Object.entries(F.CONFIRM)) assert.equal(typeof ApiClient.prototype[m], "function", kind);
    for (const [kind, m] of Object.entries(F.REJECT)) assert.equal(typeof ApiClient.prototype[m], "function", kind);
  });
});
