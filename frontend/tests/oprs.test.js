import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { Oprs } from "../src/pages/Oprs.js";
import * as F from "../src/lib/oprs.js";
import { ApiClient } from "../src/api/client.js";
import { NAV_GROUPS } from "../src/lib/home.js";
import * as E from "../src/lib/entityConfig.js";

const text = (v) => JSON.stringify(v);
const noop = new Proxy({}, { get: () => () => {} });
const opt = (o = {}) => ({ no: 1, name: "Buy", upfront_cost: "1000.00", flows: ["600.00", "600.00"], status: "ACTIVE", removed_note: null, ...o });
const res = (o = {}) => ({ no: 1, name: "Buy", upfront_cost: "1000.00", years: 2, total_flows: "1200.00", net_value: "200.00", npv: "41.32", payback_year: 2, benefit_cost_ratio: "1.20", rank: 2, highest_npv: false, sensitivity: [{ rate: "8.00", npv: "69.14" }, { rate: "10.00", npv: "41.32" }], ...o });
const an = (o = {}) => ({ id: "a1", ref: "OA-001", title: "Replace the fleet", purpose: "Compare buying with leasing", currency: "NGN", discount_rate: "10.00", status: "DRAFT", submitted_by: null, active_options: 2, decision: null, decision_flag: false, decision_note: null,
  options: [opt(), opt({ no: 2, name: "Lease", upfront_cost: "200.00", flows: ["150.00", "150.00", "150.00"] })], results: [res(), res({ no: 2, name: "Lease", npv: "173.03", rank: 1, highest_npv: true, years: 3, payback_year: null })], history: [], ...o });
const ovw = () => ({ counts: { draft: 1, submitted: 1, approved: 2, returned: 0, withdrawn: 0 }, approved_by_currency: [{ currency: "NGN", analyses: 2 }, { currency: "USD", analyses: 1 }], decisions_recorded: 1,
  attention: [{ kind: "ANALYSES_TO_REVIEW", count: 1, text: "analysis(es) are waiting for a different person to review them." }], limitations: ["ASAVEXA recommends nothing."] });
const state = (o = {}) => ({ tab: "overview", ov: ovw(), analyses: [an()], sel: { analysis: null }, forms: JSON.parse(JSON.stringify(F.EMPTY)), notes: {}, formError: null, busy: false, error: null, notice: null, ...o });
const page = (o = {}, role = "OWNER", me = "u9") => Oprs({ st: state(o), role, userId: me, loading: false, onRetry() {}, actions: noop });
const sel = (x, role = "OWNER", me = "u9") => page({ tab: "analyses", sel: { analysis: x } }, role, me);

describe("permissions and buttons", () => {
  test("who can prepare and approve", () => {
    for (const r of ["OWNER", "ADMINISTRATOR", "MANAGER", "AUDITOR"]) assert.ok(F.canPrepare(r), r);
    for (const r of ["OWNER", "APPROVER", "MANAGER"]) assert.ok(F.canApprove(r), r);
    for (const r of ["ACCOUNTANT", "READ_ONLY", "EXTERNAL_AUDITOR"]) assert.ok(!F.canPrepare(r) && !F.canApprove(r), r);
  });
  test("button rules", () => {
    assert.ok(F.canEdit(an(), "OWNER")); assert.ok(F.canEdit(an({ status: "RETURNED" }), "OWNER")); assert.ok(!F.canEdit(an({ status: "APPROVED" }), "OWNER")); assert.ok(!F.canEdit(an(), "READ_ONLY"));
    assert.ok(F.canSubmit(an(), "OWNER")); assert.ok(!F.canSubmit(an({ active_options: 1 }), "OWNER"));
    assert.ok(F.canDecide(an({ status: "SUBMITTED", submitted_by: "u1" }), "APPROVER", "u9")); assert.ok(!F.canDecide(an({ status: "SUBMITTED", submitted_by: "u9" }), "APPROVER", "u9"));
    assert.ok(F.canRecord(an({ status: "APPROVED", submitted_by: "u1" }), "APPROVER", "u9")); assert.ok(!F.canRecord(an({ status: "APPROVED", submitted_by: "u9" }), "APPROVER", "u9")); assert.ok(!F.canRecord(an({ status: "APPROVED", submitted_by: "u1", decision: {} }), "APPROVER", "u9"));
  });
});

describe("payload builders", () => {
  test("analysis", () => {
    const f = { title: "Replace the fleet", purpose: "Compare buying with leasing", currency: "ngn", discount_rate: "7.25" };
    assert.deepEqual(F.analysisPayload(f).body, { title: "Replace the fleet", purpose: "Compare buying with leasing", currency: "NGN", discount_rate: "7.25" });
    for (const [k, v, re] of [["title", "ab", /title/i], ["purpose", "short", /purpose/i], ["currency", "NG", /three-letter/], ["discount_rate", "100.01", /more than 100/], ["discount_rate", "1.234", /decimals/], ["discount_rate", "-1", /rate/i], ["discount_rate", "abc", /rate/i], ["discount_rate", "", /rate/i]]) assert.match(F.analysisPayload({ ...f, [k]: v }).problem || "", re, k + v);
    assert.equal(F.analysisPayload({ ...f, discount_rate: "0" }).body.discount_rate, "0"); assert.equal(F.analysisPayload({ ...f, discount_rate: "100" }).body.discount_rate, "100");
  });
  test("option and flows", () => {
    assert.deepEqual(F.parseFlows("600; 600 ;  650"), ["600", "600", "650"]);
    assert.deepEqual(F.optionPayload({ name: "Buy", upfront_cost: "1,000.00", flows: "600; -50.5; 0" }).body, { name: "Buy", upfront_cost: "1000.00", flows: ["600", "-50.5", "0"] });
    for (const [f, re] of [[{ name: "x", upfront_cost: "5", flows: "1" }, /name/i], [{ name: "Buy", upfront_cost: "0", flows: "1" }, /more than zero/], [{ name: "Buy", upfront_cost: "5", flows: "" }, /each year/], [{ name: "Buy", upfront_cost: "5", flows: "1; x" }, /year 2/],
      [{ name: "Buy", upfront_cost: "5", flows: "1; 1.234" }, /year 2/], [{ name: "Buy", upfront_cost: "5", flows: "1;1;1;1;1;1;1;1;1;1;1" }, /at most 10/i], [{ name: "Buy", upfront_cost: "5", flows: "٣" }, /year 1/]]) assert.match(F.optionPayload(f).problem || "", re, text(f));
  });
  test("decision", () => {
    assert.deepEqual(F.decisionPayload({ option_no: "2", rationale: "Highest value over the period" }).body, { option_no: 2, rationale: "Highest value over the period" });
    assert.match(F.decisionPayload({ option_no: "", rationale: "Highest value over the period" }).problem, /option/i); assert.match(F.decisionPayload({ option_no: "1", rationale: "short" }).problem, /rationale/i);
  });
});

describe("page", () => {
  test("overview", () => {
    const t = text(page());
    for (const s of ["Decisions recorded: 1", "never added together", "ASAVEXA recommends nothing", "op-banner", "Analyses to review", "NGN: 2 analysis", "USD: 1 analysis"]) assert.ok(t.includes(s), s);
  });
  test("starting an analysis is for preparers only", () => {
    assert.ok(text(page({ tab: "analyses" }, "AUDITOR")).includes("op-an-save")); assert.ok(!text(page({ tab: "analyses" }, "READ_ONLY")).includes("op-an-save"));
  });
  test("draft: results, options, editing", () => {
    const t = text(sel(an()));
    for (const s of ["op-results", "NPV 41.32", "NPV 173.03", "Highest NPV", "not within 3 year(s)", "payback in year 2", "benefit-cost ratio 1.20", "8.00 percent: 69.14", "op-opt-save", "op-opt-1-remove", "op-sb-save", "op-wd-save"]) assert.ok(t.includes(s), s);
    assert.ok(!t.includes("op-dc-approve")); assert.ok(!text(sel(an({ active_options: 1 }))).includes("op-sb-save")); assert.ok(text(sel(an({ active_options: 1 }))).includes("op-need-two"));
  });
  test("read-only sees data and no buttons", () => {
    const t = text(sel(an({ status: "SUBMITTED", submitted_by: "u1" }), "READ_ONLY"));
    for (const s of ["op-opt-save", "op-sb-save", "op-dc-approve", "op-dec-save", "op-opt-1-remove"]) assert.ok(!t.includes(s), s); assert.ok(t.includes("1200.00"));
  });
  test("submitted: another person decides", () => {
    const x = an({ status: "SUBMITTED", submitted_by: "u1" });
    const t = text(sel(x, "APPROVER", "u9")); assert.ok(t.includes("op-dc-approve") && t.includes("op-dc-return")); assert.ok(!t.includes("op-opt-save"));
    const own = text(sel(an({ status: "SUBMITTED", submitted_by: "u9" }), "APPROVER", "u9")); assert.ok(!own.includes("op-dc-approve")); assert.ok(own.includes("a different person must decide it"));
  });
  test("approved: record the decision, then show it", () => {
    const x = an({ status: "APPROVED", submitted_by: "u1" });
    const t = text(sel(x, "APPROVER", "u9")); for (const s of ["op-dec-opt", "op-dec-why", "op-dec-save"]) assert.ok(t.includes(s), s);
    const own = text(sel(an({ status: "APPROVED", submitted_by: "u9" }), "APPROVER", "u9")); assert.ok(!own.includes("op-dec-save")); assert.ok(own.includes("op-dec-waiting"));
    const d = text(sel(an({ status: "APPROVED", submitted_by: "u1", decision: { option_no: 1, option_name: "Buy", rationale: "Cash is available now" }, decision_flag: true }), "APPROVER", "u9"));
    for (const s of ["Chosen: #1 Buy", "Cash is available now", "op-decision-flag"]) assert.ok(d.includes(s), s); assert.ok(!d.includes("op-dec-save"));
  });
  test("removed options show their reason; notes show", () => {
    const t = text(sel(an({ status: "RETURNED", decision_note: "Please add the quotes", options: [opt({ status: "REMOVED", removed_note: "Leasing is not on offer" }), opt({ no: 2, name: "Lease" })] }))); for (const s of ["Leasing is not on offer", "Please add the quotes", "Removed"]) assert.ok(t.includes(s), s);
  });
  test("errors, problems and loading", () => {
    assert.ok(text(page({ error: "Boom" })).includes("Boom")); assert.ok(text(page({ tab: "analyses", formError: { form: "analysis", text: "The title needs at least 3 characters." } })).includes("analysis-problem"));
    assert.ok(text(Oprs({ st: state(), role: "OWNER", userId: "u9", loading: true, onRetry() {}, actions: noop })).length > 0);
  });
});

describe("wiring", () => {
  test("client methods hit the right paths", async () => {
    const calls = []; const c = new ApiClient("http://x"); c.request = async (m, p, b) => { calls.push([m, p, b]); return {}; };
    c.get = (p) => c.request("GET", p); c.post = (p, b) => c.request("POST", p, b); c.put = (p, b) => c.request("PUT", p, b);
    await c.opOptions(); await c.opOverview(); await c.opAnalyses(); await c.createOpAnalysis({}); await c.opAnalysis("a b"); await c.addOpOption("a1", {}); await c.removeOpOption("a1", 2, "r"); await c.submitOpAnalysis("a1", "n"); await c.withdrawOpAnalysis("a1", "w");
    await c.approveOpAnalysis("a1", ""); await c.returnOpAnalysis("a1", "r"); await c.decideOpAnalysis("a1", {});
    assert.deepEqual(calls.map((x) => x[0] + " " + x[1]), ["GET /oprs/options", "GET /oprs/overview", "GET /oprs/analyses", "POST /oprs/analyses", "GET /oprs/analyses/a%20b", "POST /oprs/analyses/a1/options", "POST /oprs/analyses/a1/options/2/remove", "POST /oprs/analyses/a1/submit",
      "POST /oprs/analyses/a1/withdraw", "POST /oprs/analyses/a1/approve", "POST /oprs/analyses/a1/return", "POST /oprs/analyses/a1/decision"]);
  });
  test("home group and entity path", () => {
    assert.ok(NAV_GROUPS.some((g) => g.paths.includes("/oprs"))); assert.equal(E.WORKSPACE_PATHS.oprs, "/oprs");
  });
});
