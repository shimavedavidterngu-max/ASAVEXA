import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { Valuation } from "../src/pages/Valuation.js";
import * as F from "../src/lib/valuation.js";
import { ApiClient } from "../src/api/client.js";
import { NAV_GROUPS } from "../src/lib/home.js";
import * as E from "../src/lib/entityConfig.js";

const text = (v) => JSON.stringify(v);
const noop = new Proxy({}, { get: () => () => {} });
// u1 submitted, u3 decides, u9 bystander
const method = (o = {}) => ({ no: 1, kind: "MULTIPLE", label: "Peer multiple", weight: 60, inputs: { metric: "1000.00", multiple: "6.5", net_debt: "500.00" }, result: "6000.00", status: "ACTIVE", removed_note: null, ...o });
const kase = (o = {}) => ({ id: "c1", ref: "VL-001", subject: "Acme Ltd", subject_kind: "BUSINESS", purpose: "TRANSACTION", basis: "MARKET_VALUE", valuation_date: "2026-03-09", currency: "NGN", status: "DRAFT", methods: [method()], active_methods: 1, weight_total: 60, concluded_value: null, low: null, high: null, rationale: null, submitted_by: null, decision_note: null, withdraw_note: null, due_for_review: false, history: [], ...o });
const ovw = () => ({ counts: { DRAFT: 1, SUBMITTED: 1, APPROVED: 2, RETURNED: 0, WITHDRAWN: 0 }, totals: [{ currency: "NGN", approved: "3709.09", waiting: "1", in_progress: "1" }], attention: [{ kind: "CASES_TO_REVIEW", count: 1, text: "valuation(s) are waiting for review." }], policy: { review_days: 365, meaning: "An approved valuation is due for review after 365 days." }, limitations: ["ASAVEXA reads no market data."] });
const state = (o = {}) => ({ tab: "overview", options: {}, ov: ovw(), cases: [kase()], sel: { case: null }, sens: null, forms: { ...JSON.parse(JSON.stringify(F.EMPTY)), policy: F.policyForm(ovw().policy) }, notes: {}, formError: null, busy: false, error: null, notice: null, ...o });
const page = (o = {}, role = "OWNER", me = "u9") => Valuation({ vl: state(o), role, userId: me, loading: false, onRetry() {}, actions: noop });

describe("permissions", () => {
  test("who can prepare and approve", () => {
    for (const r of ["OWNER", "ADMINISTRATOR", "MANAGER", "AUDITOR"]) assert.ok(F.canPrepare(r), r);
    for (const r of ["OWNER", "APPROVER", "MANAGER"]) assert.ok(F.canApprove(r), r);
    for (const r of ["ACCOUNTANT", "READ_ONLY", "EXTERNAL_AUDITOR", "INVESTOR_REVIEWER"]) { assert.ok(!F.canPrepare(r), r); assert.ok(!F.canApprove(r), r); }
  });
});

describe("payload builders", () => {
  const c = { subject: "Acme Ltd", subject_kind: "BUSINESS", purpose: "TRANSACTION", basis: "MARKET_VALUE", valuation_date: "2026-03-09", currency: "ngn" };
  test("case", () => {
    assert.equal(F.casePayload(c).body.currency, "NGN");
    for (const bad of [{ subject: "ab" }, { valuation_date: "2026-02-30" }, { currency: "NG" }, { currency: "N1A" }]) assert.ok(F.casePayload({ ...c, ...bad }).problem, text(bad));
  });
  const m = { ...F.EMPTY.method, label: "Peer multiple", weight: "60", metric: "1,000.00", multiple: "6.5", net_debt: "500" };
  test("multiple method", () => {
    const b = F.methodPayload(m).body; assert.deepEqual([b.metric, b.multiple, b.net_debt, b.weight], ["1000.00", "6.5", "500", 60]);
    assert.ok(!("net_debt" in F.methodPayload({ ...m, net_debt: "" }).body));
    for (const bad of [{ metric: "0" }, { metric: "x" }, { metric: "1.234" }, { multiple: "0" }, { multiple: "1.23456" }, { net_debt: "-1" }, { weight: "101" }, { weight: "x" }, { weight: "" }, { label: "x" }]) assert.ok(F.methodPayload({ ...m, ...bad }).problem, text(bad));
  });
  const d = { ...F.EMPTY.method, kind: "DCF", label: "DCF base", weight: "40", cash_flows: "100 110\n121", discount_rate: "10", terminal_growth: "2", net_debt: "" };
  test("dcf method", () => {
    const b = F.methodPayload(d).body; assert.deepEqual(b.cash_flows, ["100", "110", "121"]); assert.equal(b.terminal_growth, "2");
    assert.ok(!("terminal_growth" in F.methodPayload({ ...d, terminal_growth: "" }).body));
    for (const bad of [{ cash_flows: "" }, { cash_flows: "0 0" }, { cash_flows: "100 x" }, { cash_flows: Array(16).fill("1").join(" ") }, { discount_rate: "0" }, { discount_rate: "101" }, { discount_rate: "" }, { terminal_growth: "10" }, { terminal_growth: "12" }, { terminal_growth: "-1" }]) assert.ok(F.methodPayload({ ...d, ...bad }).problem, text(bad));
    assert.ok(F.methodPayload({ ...d, cash_flows: "0 100" }).body);
  });
  test("asset method", () => {
    const a = { ...F.EMPTY.method, kind: "ASSET_BASED", label: "Net assets", weight: "100", total_assets: "5000", total_liabilities: "1500" };
    assert.deepEqual(F.methodPayload(a).body.total_liabilities, "1500"); assert.ok(F.methodPayload({ ...a, total_liabilities: "0" }).body);
    for (const bad of [{ total_assets: "0" }, { total_assets: "" }, { total_liabilities: "-1" }]) assert.ok(F.methodPayload({ ...a, ...bad }).problem, text(bad));
  });
  test("submit and policy", () => {
    assert.ok(F.submitPayload({ rationale: "x".repeat(19) }).problem); assert.ok(F.submitPayload({ rationale: "x".repeat(20) }).body);
    assert.equal(F.policyPayload({ review_days: "365" }).body.review_days, 365);
    for (const bad of ["29", "1096", "x", "", "3.5"]) assert.ok(F.policyPayload({ review_days: bad }).problem, bad);
  });
});

describe("buttons", () => {
  test("edit, submit, decide", () => {
    assert.ok(F.canEdit(kase(), "AUDITOR")); assert.ok(!F.canEdit(kase({ status: "SUBMITTED" }), "AUDITOR")); assert.ok(F.canEdit(kase({ status: "RETURNED" }), "OWNER")); assert.ok(!F.canEdit(kase(), "READ_ONLY"));
    assert.ok(!F.canSubmit(kase(), "OWNER")); assert.ok(F.canSubmit(kase({ weight_total: 100 }), "OWNER")); assert.ok(!F.canSubmit(kase({ weight_total: 100, active_methods: 0 }), "OWNER"));
    const s = kase({ status: "SUBMITTED", submitted_by: "u1" });
    assert.ok(F.canDecide(s, "APPROVER", "u3")); assert.ok(!F.canDecide(s, "APPROVER", "u1")); assert.ok(!F.canDecide(s, "AUDITOR", "u3")); assert.ok(!F.canDecide(kase(), "APPROVER", "u3"));
  });
});

describe("page", () => {
  test("overview", () => {
    const t = text(page()); assert.match(t, /vl-banner/); assert.match(t, /not a valuation report/); assert.match(t, /never added together/); assert.match(t, /3709\.09/); assert.match(t, /vl-policy-save/);
    assert.ok(!/vl-policy-save/.test(text(page({}, "AUDITOR"))));
  });
  test("cases list and start form", () => {
    const t = text(page({ tab: "cases" })); assert.match(t, /VL-001/); assert.match(t, /vl-cs-save/); assert.ok(!/vl-cs-save/.test(text(page({ tab: "cases" }, "READ_ONLY"))));
  });
  test("detail shows methods, weights, sensitivity", () => {
    const c = kase(); const t = text(page({ tab: "cases", sel: { case: c } }));
    assert.match(t, /vl-methods/); assert.match(t, /6000\.00/); assert.match(t, /add up to 60 percent/); assert.match(t, /vl-mt-save/); assert.match(t, /vl-sb-blocked/);
    const dc = kase({ methods: [method({ kind: "DCF", inputs: { cash_flows: ["100", "110"], discount_rate: "10", terminal_growth: null, net_debt: "0.00" }, result: "173.55" })] });
    const t2 = text(page({ tab: "cases", sel: { case: dc }, sens: { caseId: "c1", method: 1, rows: [{ discount_rate: "9", result: "180.00" }, { discount_rate: "2", result: null }] } }));
    assert.match(t2, /vl-mt-1-sens/); assert.match(t2, /vl-sens-1/); assert.match(t2, /not usable/);
  });
  test("decision controls: different person only", () => {
    const s = kase({ status: "SUBMITTED", submitted_by: "u1", weight_total: 100, concluded_value: "3709.09", rationale: "Weights reflect comparability." });
    const other = text(page({ tab: "cases", sel: { case: s } }, "APPROVER", "u3")); assert.match(other, /vl-dec-approve/); assert.match(other, /vl-dec-return/); assert.match(other, /3709\.09/);
    const same = text(page({ tab: "cases", sel: { case: s } }, "APPROVER", "u1")); assert.ok(!/vl-dec-approve/.test(same)); assert.match(same, /so a different person must decide it/);
    assert.ok(!/vl-mt-save/.test(other));
  });
  test("returned and withdrawn notes", () => {
    assert.match(text(page({ tab: "cases", sel: { case: kase({ status: "RETURNED", decision_note: "Check the multiple." }) } })), /Check the multiple/);
  });
  test("loading and error", () => {
    assert.match(text(Valuation({ vl: state(), role: "OWNER", userId: "u9", loading: true, onRetry() {}, actions: noop })), /./);
    assert.match(text(page({ error: "Boom" })), /Boom/);
  });
});

describe("wiring", () => {
  test("client paths", async () => {
    const calls = []; const c = new ApiClient({ baseUrl: "http://x" }); for (const k of ["get", "post", "put"]) c[k] = async (p, b) => { calls.push([k, p, b]); return {}; };
    await c.vlSensitivity("a b", 2); await c.removeVlMethod("c1", 2, "r"); await c.submitVl("c1", "why"); await c.setVlPolicy({ review_days: 90 });
    assert.deepEqual(calls.map((x) => x[0] + " " + x[1]), ["get /valuation/cases/a%20b/methods/2/sensitivity", "post /valuation/cases/c1/methods/2/remove", "post /valuation/cases/c1/submit", "put /valuation/policy"]);
  });
  test("nav and entity paths", () => {
    assert.ok(text(NAV_GROUPS).includes("/valuation")); assert.equal(E.WORKSPACE_PATHS.valuation, "/valuation");
  });
});
