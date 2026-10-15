import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { Payroll } from "../src/pages/Payroll.js";
import * as F from "../src/lib/payroll.js";
import { ApiClient } from "../src/api/client.js";
import { NAV_GROUPS } from "../src/lib/home.js";
import * as E from "../src/lib/entityConfig.js";

const text = (v) => JSON.stringify(v);
const noop = new Proxy({}, { get: () => () => {} });
const tot = (o = {}) => ({ lines: 2, gross: "460000.50", deductions: "63400.14", net: "396600.36", employer_contributions: "28000.05", employer_cost: "488000.55", ...o });
const line = (o = {}) => ({ no: 1, staff_ref: "EMP-001", department: "Finance", base_pay: "250000.00", allowances: "30000.50", gross: "280000.50", deductions: [{ label: "Pension", amount: "22400.04" }], total_deductions: "63400.14", net: "216600.36", employer_contributions: "28000.05", employer_cost: "308000.55", status: "ACTIVE", above_limit: false, overlap: false, ...o });
const run = (o = {}) => ({ id: "r1", ref: "PR-001", label: "October payroll", period_start: "2026-10-01", period_end: "2026-10-31", currency: "NGN", status: "DRAFT", submitted_by: null, active_lines: 2, lines: [line(), line({ no: 2, staff_ref: "EMP-002", department: "Sales" })], totals: tot(), overlaps: 0, departments: [{ department: "Finance", lines: 1, gross: "280000.50", net: "216600.36", employer_cost: "308000.55" }], history: [], ...o });
const ovw = () => ({ counts: { draft: 1, submitted: 1, approved: 1, returned: 0, withdrawn: 0 }, totals: [{ currency: "NGN", approved_runs: 1, waiting_runs: 1, gross: "460000.50", deductions: "63400.14", net: "396600.36", employer_contributions: "28000.05", employer_cost: "488000.55" }],
  attention: [{ kind: "RUNS_TO_REVIEW", count: 1, text: "payroll run(s) are waiting for a different person." }], setting: { review_limit: "0.00", meaning: "Off." }, limitations: ["ASAVEXA calculates no tax."] });
const state = (o = {}) => ({ tab: "overview", ov: ovw(), runs: [run()], sel: { run: null }, forms: { ...JSON.parse(JSON.stringify(F.EMPTY)), setting: { review_limit: "0.00" } }, notes: {}, formError: null, busy: false, error: null, notice: null, ...o });
const page = (o = {}, role = "OWNER", me = "u9") => Payroll({ pw: state(o), role, userId: me, loading: false, onRetry() {}, actions: noop });
const sel = (r, role = "OWNER", me = "u9") => page({ tab: "runs", sel: { run: r } }, role, me);

describe("permissions", () => {
  test("who can prepare and approve", () => {
    for (const r of ["OWNER", "ADMINISTRATOR", "MANAGER", "AUDITOR"]) assert.ok(F.canPrepare(r), r);
    for (const r of ["OWNER", "APPROVER", "MANAGER"]) assert.ok(F.canApprove(r), r);
    for (const r of ["ACCOUNTANT", "READ_ONLY", "EXTERNAL_AUDITOR"]) { assert.ok(!F.canPrepare(r), r); assert.ok(!F.canApprove(r), r); }
  });
  test("button rules", () => {
    assert.ok(F.canEdit(run(), "OWNER")); assert.ok(F.canEdit(run({ status: "RETURNED" }), "OWNER"));
    assert.ok(!F.canEdit(run({ status: "SUBMITTED" }), "OWNER")); assert.ok(!F.canEdit(run(), "READ_ONLY"));
    assert.ok(!F.canSubmit(run({ active_lines: 0 }), "OWNER"));
    assert.ok(F.canDecide(run({ status: "SUBMITTED", submitted_by: "u1" }), "APPROVER", "u9"));
    assert.ok(!F.canDecide(run({ status: "SUBMITTED", submitted_by: "u9" }), "APPROVER", "u9"));
  });
});

describe("payload builders", () => {
  test("run", () => {
    const r = F.runPayload({ label: "October payroll", period_start: "2026-10-01", period_end: "2026-10-31", currency: "ngn" });
    assert.equal(r.body.currency, "NGN");
    assert.match(F.runPayload({ label: "ab", period_start: "2026-10-01", period_end: "2026-10-31", currency: "NGN" }).problem, /label/);
    assert.match(F.runPayload({ label: "October", period_start: "2026-10-31", period_end: "2026-10-01", currency: "NGN" }).problem, /cannot end before/);
    assert.match(F.runPayload({ label: "October", period_start: "2026-02-30", period_end: "2026-10-01", currency: "NGN" }).problem, /real date/);
    assert.match(F.runPayload({ label: "October", period_start: "2026-10-01", period_end: "2026-10-31", currency: "NG" }).problem, /three-letter/);
  });
  test("deductions", () => {
    assert.deepEqual(F.parseDeductions("Pension: 22,400.04\nTax: 41000.10").list, [{ label: "Pension", amount: "22400.04" }, { label: "Tax", amount: "41000.10" }]);
    assert.deepEqual(F.parseDeductions("").list, []);
    assert.match(F.parseDeductions("Pension 22400").problem, /label: amount/);
    assert.match(F.parseDeductions("Pension: 0").problem, /more than zero/);
    assert.match(F.parseDeductions("Pension: 1.234").problem, /two decimals/);
    assert.match(F.parseDeductions(Array.from({ length: 9 }, (_, i) => `Item${i}: 1`).join("\n")).problem, /At most 8/);
  });
  test("line", () => {
    const f = { staff_ref: "EMP-001", department: "Finance", base_pay: "250,000.00", allowances: "30000.50", employer_contributions: "28000.05", deductions: "Pension: 22400.04\nTax: 41000.10" };
    const b = F.linePayload(f).body;
    assert.equal(b.base_pay, "250000.00"); assert.equal(b.deductions.length, 2); assert.equal(b.allowances, "30000.50");
    assert.match(F.linePayload({ ...f, base_pay: "0" }).problem, /more than zero/);
    assert.match(F.linePayload({ ...f, base_pay: "1,2,3" }).problem, /commas/);
    assert.match(F.linePayload({ ...f, base_pay: "٢٥٠" }).problem, /amount/);
    assert.match(F.linePayload({ ...f, staff_ref: "a" }).problem, /staff reference/);
    assert.match(F.linePayload({ ...f, deductions: "Tax: 999999999" }).problem, /more than the gross/);
    assert.ok(!("allowances" in F.linePayload({ ...f, allowances: "" }).body));
  });
  test("submit and setting", () => {
    assert.equal(F.submitPayload({ note: "" }).body.note, "");
    assert.match(F.submitPayload({ note: "short" }).problem, /10 characters/);
    assert.equal(F.settingPayload("250,000.00").body.review_limit, "250000.00");
    assert.ok(F.settingPayload("-1").problem); assert.ok(F.settingPayload("1,2").problem);
  });
});

describe("page", () => {
  test("overview shows exact figures and the limits", () => {
    const t = text(page());
    for (const s of ["460000.50", "396600.36", "488000.55", "never added together", "ASAVEXA calculates no tax", "pw-banner", "Settings"]) assert.ok(t.includes(s), s);
    assert.ok(t.includes("pw-set-save")); assert.ok(!text(page({}, "READ_ONLY")).includes("pw-set-save"));
  });
  test("owner sees editing on a draft", () => {
    const t = text(sel(run()));
    for (const s of ["pw-ln-save", "pw-sb-save", "pw-wd-save", "216600.36", "Finance", "pw-departments", "pw-ln-1-remove"]) assert.ok(t.includes(s), s);
  });
  test("read-only sees no buttons", () => {
    const t = text(sel(run(), "READ_ONLY"));
    for (const s of ["pw-ln-save", "pw-sb-save", "pw-wd-save", "pw-dec-approve", "pw-ln-1-remove"]) assert.ok(!t.includes(s), s);
    assert.ok(t.includes("216600.36"));
  });
  test("submitted: other person decides, submitter does not", () => {
    const r = run({ status: "SUBMITTED", submitted_by: "u1" });
    const t = text(sel(r, "APPROVER", "u9"));
    assert.ok(t.includes("pw-dec-approve") && t.includes("pw-dec-return")); assert.ok(!t.includes("pw-ln-save"));
    const own = text(sel(run({ status: "SUBMITTED", submitted_by: "u9" }), "APPROVER", "u9"));
    assert.ok(!own.includes("pw-dec-approve")); assert.ok(own.includes("a different person must decide it"));
  });
  test("flags and notes", () => {
    const t = text(sel(run({ status: "RETURNED", decision_note: "Check EMP-002", overlaps: 1, lines: [line({ above_limit: true, overlap: true })] })));
    for (const s of ["Above review limit", "Overlapping pay", "Check EMP-002", "pw-overlap-note"]) assert.ok(t.includes(s), s);
  });
  test("errors and form problems show; loading", () => {
    assert.ok(text(page({ error: "Boom" })).includes("Boom"));
    assert.ok(text(sel(run(), "OWNER", "u9")).length > 0);
    assert.ok(text(page({ tab: "runs", formError: { form: "run", text: "The label needs at least 3 characters." } })).includes("run-problem"));
    assert.ok(text(Payroll({ pw: state(), role: "OWNER", userId: "u9", loading: true, onRetry() {}, actions: noop })).length > 0);
  });
});

describe("wiring", () => {
  test("client methods hit the right paths", async () => {
    const calls = []; const c = new ApiClient("http://x"); c.request = async (m, p, b) => { calls.push([m, p, b]); return {}; };
    c.get = (p) => c.request("GET", p); c.post = (p, b) => c.request("POST", p, b); c.put = (p, b) => c.request("PUT", p, b);
    await c.pwOverview(); await c.pwRuns(); await c.pwRun("a b"); await c.createPwRun({ x: 1 }); await c.addPwLine("r1", { y: 1 }); await c.removePwLine("r1", 2, "wrong person"); await c.submitPw("r1", "n"); await c.withdrawPw("r1", "why"); await c.approvePw("r1", ""); await c.returnPw("r1", "why"); await c.setPwSetting({ review_limit: "1" });
    assert.deepEqual(calls.map((x) => x[0] + " " + x[1]), ["GET /payroll/overview", "GET /payroll/runs", "GET /payroll/runs/a%20b", "POST /payroll/runs", "POST /payroll/runs/r1/lines", "POST /payroll/runs/r1/lines/2/remove", "POST /payroll/runs/r1/submit", "POST /payroll/runs/r1/withdraw", "POST /payroll/runs/r1/approve", "POST /payroll/runs/r1/return", "PUT /payroll/setting"]);
  });
  test("home group and entity path", () => {
    assert.ok(NAV_GROUPS.some((g) => g.paths.includes("/payroll")));
    assert.equal(E.WORKSPACE_PATHS.payroll, "/payroll");
  });
});
