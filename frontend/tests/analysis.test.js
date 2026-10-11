import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { Analysis } from "../src/pages/Analysis.js";
import { Workspaces } from "../src/pages/Workspaces.js";
import * as A from "../src/lib/analysis.js";
import { ApiClient } from "../src/api/client.js";

const text = (v) => JSON.stringify(v);
function find(v, pred, out = []) { if (!v || typeof v !== "object") return out; if (pred(v)) out.push(v); for (const c of v.children || []) find(c, pred, out); return out; }
const byId = (v, id) => find(v, (n) => n.props && n.props.id === id)[0];
const noop = new Proxy({}, { get: () => () => {} });
const base = (o = {}) => ({ tab: "overview", period_id: "p1", loaded: {}, busy: false, error: null, notice: null, open: {}, periodNames: { p1: "FY26-M01" },
  overview: null, ratios: null, variance: null, budget: null, budgetVar: null, config: null, scenarios: [], reports: [], report: null, noteFor: null, noteText: "", budgetForm: {}, budgetNote: "",
  scenarioForm: A.emptyScenario(), suggestNote: null, run: null, be: { fixed_costs: "", price: "", variable_cost: "" }, beResult: null, reportForm: A.emptyReportForm(), decisionNote: "", verify: null, tagDraft: {}, thresholdForm: { percent: "10", amount: "0" }, ...o });
const page = (an, role = "ACCOUNTANT", userId = "u1") => Analysis({ an, periods: [{ id: "p1", name: "FY26-M01" }], loading: false, role, userId, onRetry() {}, actions: noop });

describe("helpers", () => {
  test("num keeps decimals as text and adds thousands separators", () => {
    assert.equal(A.num("1234567.50"), "1,234,567.50");
    assert.equal(A.num("-1000.00"), "-1,000.00");
    assert.equal(A.num(null), "—");
    assert.equal(A.num("abc"), "abc");
  });
  test("a ratio that was not calculated shows a dash, never a number", () => {
    assert.equal(A.ratioText({ value: null, unit: "ratio" }), "—");
    assert.equal(A.ratioText({ value: "12.50", unit: "percent" }), "12.50%");
    assert.equal(A.ratioText({ value: "30.0", unit: "days" }), "30.0 days");
  });
  test("scenario validation", () => {
    const ok = { ...A.emptyScenario(), name: "Base", base_monthly_revenue: "100", base_monthly_expenses: "80", opening_cash: "50" };
    assert.equal(A.scenarioProblem(ok), null);
    assert.match(A.scenarioProblem({ ...ok, name: "" }), /name/);
    assert.match(A.scenarioProblem({ ...ok, months: "30" }), /1 to 24/);
    assert.match(A.scenarioProblem({ ...ok, base_monthly_revenue: "-1" }), /negative/);
    assert.match(A.scenarioProblem({ ...ok, opening_cash: "abc" }), /number/);
    assert.deepEqual(A.scenarioBody(ok, "p1").assumptions.months, 6);
  });
  test("budget boxes: blanks are left out, bad values refused", () => {
    assert.deepEqual(A.budgetBody({ a: "10", b: "  " }, "p1", " n ").lines, { a: "10" });
    assert.match(A.budgetProblem({ a: "" }), /at least one/);
    assert.match(A.budgetProblem({ a: "-5" }), /positive/);
    assert.equal(A.budgetProblem({ a: "5.25" }), null);
  });
  test("evidence ids are split on commas and spaces", () => {
    assert.deepEqual(A.evidenceList("a, b;c  d"), ["a", "b", "c", "d"]);
    assert.match(A.reportProblem({ title: "ab" }), /title/);
  });
  test("separation of duties: the submitter sees no Approve, another approver does", () => {
    const rep = { status: "SUBMITTED", submitted_by: "u1", has_snapshot: true };
    assert.equal(A.reportActions(rep, "OWNER", "u1").decide, false);
    assert.equal(A.reportActions(rep, "OWNER", "u1").ownSubmission, true);
    assert.equal(A.reportActions(rep, "OWNER", "u2").decide, true);
    assert.equal(A.reportActions(rep, "READ_ONLY", "u2").decide, false);
    assert.equal(A.reportActions({ ...rep, status: "DRAFT" }, "READ_ONLY", "u2").submit, false);
  });
  test("export is offered only for an approved report", () => {
    assert.equal(A.reportActions({ status: "SUBMITTED", submitted_by: "x" }, "OWNER", "u").export, false);
    assert.equal(A.reportActions({ status: "APPROVED", submitted_by: "x" }, "OWNER", "u").export, true);
  });
});

describe("Analysis page", () => {
  test("no periods gives an honest empty state", () => {
    assert.match(text(Analysis({ an: base(), periods: [], loading: false, role: "OWNER", userId: "u", onRetry() {}, actions: noop })), /No accounting periods/);
  });
  test("overview shows totals and the data issues", () => {
    const o = { totals: { assets: "100.00", liabilities: "40.00", equity_total: "60.00", revenue: "10.00", expenses: "4.00", net_income: "6.00" }, issues: ["2 accounts are not classified"], definitions: ["d1"], posted_entries: 3, classified: 1, live_accounts: 3, prior_period: null };
    const t = text(page(base({ overview: o })));
    assert.match(t, /2 accounts are not classified/);
    assert.match(t, /no earlier period/);
    assert.match(t, /60\.00/);
  });
  test("ratios: unclassified ratio shows 'Needs setup' and working is hidden until asked", () => {
    const r = { calculated: 1, total: 2, note: "n", ratios: [
      { id: "cr", name: "Current ratio", group: "Liquidity", unit: "ratio", status: "CALCULATED", value: "1.50", formula: "CA / CL", numerator: { label: "CA", amount: "150.00", accounts: [{ code: "1000", name: "Cash", amount: "150.00" }] }, denominator: { label: "CL", amount: "100.00", accounts: [] }, reading: "ok", reason: "" },
      { id: "qr", name: "Quick ratio", group: "Liquidity", unit: "ratio", status: "INCOMPLETE", value: null, formula: "x", numerator: { label: "n", amount: "0", accounts: [] }, denominator: null, reading: "", reason: "Account 1200 is not classified" }] };
    const t = text(page(base({ tab: "ratios", ratios: r })));
    assert.match(t, /Needs setup/);
    assert.match(t, /Account 1200 is not classified/);
    assert.doesNotMatch(t, /Formula: /);
    assert.match(text(page(base({ tab: "ratios", ratios: r, open: { cr: true } }))), /CA \/ CL/);
  });
  test("forecast tab always carries the FORECAST warning; read-only roles get no scenario form", () => {
    const t = text(page(base({ tab: "forecast" }), "READ_ONLY"));
    assert.match(t, /FORECAST/);
    assert.equal(byId(page(base({ tab: "forecast" }), "READ_ONLY"), "scn-save"), undefined);
    assert.ok(byId(page(base({ tab: "forecast" }), "ACCOUNTANT"), "scn-save"));
  });
  test("report detail: submitter cannot approve; other approver can; export only when approved", () => {
    const rep = { id: "r1", title: "Q1", status: "SUBMITTED", version: 1, submitted_by: "u1", created_by: "u1", confidentiality: "Confidential", history: [], snapshot: null, has_snapshot: true, fingerprint: "ab" };
    const mine = page(base({ tab: "reports", report: rep }), "OWNER", "u1");
    assert.equal(byId(mine, "rep-approve"), undefined);
    assert.match(text(mine), /does not let you approve your own work/);
    assert.ok(byId(page(base({ tab: "reports", report: rep }), "OWNER", "u2"), "rep-approve"));
    assert.equal(byId(page(base({ tab: "reports", report: rep }), "OWNER", "u2"), "rep-export"), undefined);
    assert.ok(byId(page(base({ tab: "reports", report: { ...rep, status: "APPROVED", decided_by: "u2", decision_note: "ok" } }), "OWNER", "u2"), "rep-export"));
  });
  test("tampered report verification is shown as a warning, not success", () => {
    const rep = { id: "r1", title: "Q1", status: "APPROVED", version: 1, submitted_by: "u1", created_by: "u1", confidentiality: "C", history: [], snapshot: null, has_snapshot: true, fingerprint: "ab" };
    const v = { integrity_ok: false, matches_ledger_now: true, account_differences: [], meaning: "The frozen figures were altered." };
    const n = find(page(base({ tab: "reports", report: rep, verify: v }), "OWNER", "u2"), (x) => x.props && /alert-warning/.test(x.props.className || ""));
    assert.ok(n.length >= 1);
  });
  test("an error is shown", () => {
    assert.match(text(page(base({ error: "Boom" }))), /Boom/);
  });
});

describe("Workspaces page", () => {
  const data = { workspaces: [
    { id: "analysis", name: "Financial Analysis", status: "VERIFIED IN TEST ENVIRONMENT", purpose: "p", depends_on: ["Ledger"], path: "/analysis", permission: "reporting:read" },
    { id: "tax", name: "Tax Compliance", status: "BLOCKED", purpose: "p", note: "needs a jurisdiction", depends_on: ["Ledger"], path: null }],
    foundations: [{ name: "Audit history", status: "VERIFIED IN TEST ENVIRONMENT", note: "n" }], note: "footer" };
  test("built workspace has an Open button; unbuilt/blocked has none and shows its true status", () => {
    const v = Workspaces({ data, loading: false, error: null, role: "OWNER", onOpen() {}, onRetry() {} });
    assert.ok(byId(v, "ws-open-analysis"));
    assert.equal(byId(v, "ws-open-tax"), undefined);
    assert.match(text(v), /BLOCKED/);
    assert.match(text(v), /needs a jurisdiction/);
  });
  test("a role without reporting access cannot open it", () => {
    const v = Workspaces({ data, loading: false, error: null, role: "DONOR", onOpen() {}, onRetry() {} });
    assert.equal(byId(v, "ws-open-analysis").props.disabled, true);
  });
});

describe("API client", () => {
  const mk = (resp) => { const calls = []; return { calls, api: new ApiClient({ baseUrl: "/api", getToken: () => "tok", fetchImpl: async (u, o) => { calls.push([u, o]); return resp; } }) }; };
  test("export sends the bearer token and returns a blob with the server's filename", async () => {
    const { api, calls } = mk({ ok: true, blob: async () => "BLOB", headers: { get: () => 'attachment; filename="analysis-x-v1.csv"' } });
    const r = await api.exportAnalysisReport("r 1");
    assert.equal(r.filename, "analysis-x-v1.csv");
    assert.equal(r.blob, "BLOB");
    assert.equal(calls[0][0], "/api/analysis/reports/r%201/export");
    assert.equal(calls[0][1].headers.Authorization, "Bearer tok");
  });
  test("export failure becomes a readable ApiError", async () => {
    const { api } = mk({ ok: false, status: 403, text: async () => JSON.stringify({ detail: "Only approved reports can be exported." }) });
    await assert.rejects(() => api.exportAnalysisReport("r1"), /approved/);
  });
  test("scenario save uses POST for new and PUT for existing", async () => {
    const seen = [];
    const api = new ApiClient({ baseUrl: "/api", getToken: () => "t", fetchImpl: async (u, o) => { seen.push(o.method + " " + u); return { ok: true, status: 200, text: async () => "{}" }; } });
    await api.saveAnalysisScenario({}, null); await api.saveAnalysisScenario({}, "s1");
    assert.deepEqual(seen, ["POST /api/analysis/scenarios", "PUT /api/analysis/scenarios/s1"]);
  });
});
