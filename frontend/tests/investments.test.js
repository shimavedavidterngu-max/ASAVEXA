import { test, describe } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { Investments } from "../src/pages/Investments.js";
import * as F from "../src/lib/investments.js";
import { ApiClient } from "../src/api/client.js";
import { NAV_GROUPS } from "../src/lib/home.js";
import * as E from "../src/lib/entityConfig.js";

const text = (v) => JSON.stringify(v);
const noop = new Proxy({}, { get: () => () => {} });
// u1 proposes, u3 approves, u9 bystander
const buy = (o = {}) => ({ no: 1, kind: "BUY", units: "10", price: "100.0000", fee: "5.00", gross: "1000.00", amount: "1005.00", proceeds: null, cost_removed: null, realised: null, reference: "CN-001", traded_on: "2026-03-09", applied_on: "2026-03-09", status: "APPLIED", by: "u1", decided_by: null, decision_note: null, units_after: "10", basis_after: "1005.00", ...o });
const sell = (o = {}) => buy({ no: 2, kind: "SELL", units: "4", price: "130.0000", fee: "3.00", gross: "520.00", amount: null, reference: "CN-900", applied_on: null, status: "PENDING", units_after: null, basis_after: null, ...o });
const holding = (o = {}) => ({ id: "h1", ref: "HD-001", name: "Dangote Cement shares", identifier: "DANGCEM", asset_class: "EQUITY", currency: "NGN", account: "Broker account 1", status: "ACTIVE", units: "10", cost_basis: "1005.00", realised_total: "0.00", average_cost: "100.5000",
  trades: [buy()], marks: [], history: [], pending_sells: 0, latest_mark: null, market_value: null, unrealised: null, no_mark: true, mark_stale: false, ...o });
const ovw = () => ({ counts: { active: 2, closed: 1, no_price: 1, stale: 0 }, totals: [{ currency: "NGN", holdings: 2, cost: "1205.00", valued: 1, unvalued: 1, market_value: "1100.00", unrealised: "95.00", realised: "2.00" }, { currency: "USD", holdings: 1, cost: "21.00", valued: 1, unvalued: 0, market_value: "22.00", unrealised: "1.00", realised: "0.00" }],
  attention: [{ kind: "NO_PRICE", count: 1, text: "holding(s) with units have no price recorded." }], policy: { stale_days: 30, meaning: "A price older than 30 days is flagged as out of date." }, limitations: ["ASAVEXA reads no market data."] });
const state = (o = {}) => ({ tab: "overview", options: {}, ov: ovw(), holdings: [holding()], sel: { holding: null }, forms: { ...JSON.parse(JSON.stringify(F.EMPTY)), policy: F.policyForm(ovw().policy) }, notes: {}, formError: null, busy: false, error: null, notice: null, ...o });
const page = (o = {}, role = "OWNER", me = "u9") => Investments({ im: state(o), role, userId: me, loading: false, onRetry() {}, actions: noop });

describe("permissions", () => {
  test("who can prepare and approve", () => {
    for (const r of ["OWNER", "ADMINISTRATOR", "MANAGER", "AUDITOR"]) assert.ok(F.canPrepare(r), r);
    for (const r of ["OWNER", "APPROVER", "MANAGER"]) assert.ok(F.canApprove(r), r);
    for (const r of ["ACCOUNTANT", "READ_ONLY", "EXTERNAL_AUDITOR", "INVESTOR_REVIEWER"]) { assert.ok(!F.canPrepare(r), r); assert.ok(!F.canApprove(r), r); }
    assert.ok(!F.canRead("ACCOUNTANT")); assert.ok(F.canRead("AUDITOR"));
  });
});

describe("payload builders", () => {
  const g = { name: "Dangote Cement shares", identifier: "dangcem", asset_class: "EQUITY", currency: "ngn", account: "Broker account 1" };
  test("holding", () => {
    const ok = F.holdingPayload(g).body; assert.deepEqual([ok.currency, ok.identifier], ["NGN", "dangcem"]); assert.ok(!("identifier" in F.holdingPayload({ ...g, identifier: "" }).body));
    for (const bad of [{ name: "ab" }, { identifier: "x" }, { asset_class: "" }, { currency: "NG" }, { currency: "N1A" }, { account: "x" }]) assert.ok(F.holdingPayload({ ...g, ...bad }).problem, JSON.stringify(bad));
  });
  test("purchase and sale", () => {
    const b = { units: "12.5", price: "101.2500", fee: "5", traded_on: "2026-03-09", reference: "CN-1" }; const ok = F.buyPayload(b).body; assert.deepEqual([ok.units, ok.price, ok.fee], ["12.5", "101.2500", "5"]); assert.ok(!("fee" in F.buyPayload({ ...b, fee: "" }).body));
    for (const bad of [{ units: "0" }, { units: "-1" }, { units: "1.23456" }, { units: "x" }, { units: "" }, { price: "0" }, { price: "1.23456" }, { price: "abc" }, { fee: "1.234" }, { fee: "-1" }, { traded_on: "2026-02-30" }, { reference: "x" }]) assert.ok(F.buyPayload({ ...b, ...bad }).problem, JSON.stringify(bad));
    assert.ok(F.sellPayload({ ...b, units: "10" }, "10").body); assert.match(F.sellPayload({ ...b, units: "10.0001" }, "10").problem, /Only 10 units held/); assert.ok(F.sellPayload({ ...b, units: "0.5" }, "0.25").problem); assert.ok(F.sellPayload({ ...b, units: "0.25" }, "0.25").body);
    assert.equal(F.tenThousandths("12.5"), 125000); assert.equal(F.tenThousandths("0.0001"), 1);
  });
  test("price and settings", () => {
    const m = { price: "110", as_of: "2026-03-09", source: "Broker statement" }; assert.equal(F.markPayload(m).body.price, "110");
    for (const bad of [{ price: "0" }, { price: "x" }, { as_of: "soon" }, { source: "x" }]) assert.ok(F.markPayload({ ...m, ...bad }).problem, JSON.stringify(bad));
    assert.equal(F.policyPayload({ stale_days: "90" }).body.stale_days, 90); for (const v of ["6", "366", "x", "", "4.5"]) assert.ok(F.policyPayload({ stale_days: v }).problem, v); assert.ok(F.policyPayload({ stale_days: "7" }).body);
  });
});

describe("who sees which button", () => {
  test("separation of duties", () => {
    assert.ok(F.canTrade(holding(), "AUDITOR")); assert.ok(!F.canTrade(holding(), "APPROVER")); assert.ok(!F.canTrade(holding({ status: "CLOSED" }), "AUDITOR"));
    assert.ok(F.canDecideSell(sell(), "APPROVER", "u3")); assert.ok(!F.canDecideSell(sell(), "MANAGER", "u1")); assert.ok(!F.canDecideSell(sell({ status: "APPLIED" }), "APPROVER", "u3")); assert.ok(!F.canDecideSell(sell(), "AUDITOR", "u3")); assert.ok(!F.canDecideSell(buy({ status: "PENDING" }), "APPROVER", "u3"));
    assert.ok(F.canClose(holding({ units: "0" }), "APPROVER")); assert.ok(!F.canClose(holding(), "APPROVER")); assert.ok(!F.canClose(holding({ units: "0", pending_sells: 1 }), "APPROVER")); assert.ok(!F.canClose(holding({ units: "0" }), "AUDITOR"));
  });
});

describe("page", () => {
  test("overview", () => {
    const t = text(page()); for (const id of ["im-attention", "im-totals", "im-counts", "im-policy", "im-limits", "im-banner"]) assert.match(t, new RegExp(id));
    assert.match(t, /NGN: 2 active holding/); assert.match(t, /USD: 1 active holding/); assert.match(t, /never added together/); assert.match(t, /im-policy-save/); assert.doesNotMatch(text(page({}, "AUDITOR", "u1")), /im-policy-save/);
    assert.match(t, /gain or loss so far 95\.00/); assert.match(t, /1 without a price/);
  });
  test("holdings tab", () => {
    const t = (role, me, o = {}) => text(page({ tab: "holdings", ...o }, role, me));
    assert.match(t("AUDITOR", "u1"), /im-hd-save/); assert.doesNotMatch(t("APPROVER", "u3"), /im-hd-save/);
    const bad = t("AUDITOR", "u1", { holdings: [holding({ mark_stale: true, pending_sells: 1 })], formError: { form: "holding", text: "Bad name" } });
    for (const w of ["No price", "Old price", "sale\\(s\\) waiting", "holding-problem"]) assert.match(bad, new RegExp(w)); assert.doesNotMatch(bad, /object Object/);
    const priced = t("AUDITOR", "u1", { holdings: [holding({ no_mark: false, latest_mark: { no: 1, price: "110.0000", as_of: "2026-03-09", source: "Broker statement", by: "u1" }, market_value: "1100.00", unrealised: "95.00" })] });
    assert.match(priced, /Market value NGN 1100\.00; gain or loss so far 95\.00/); assert.match(t("AUDITOR", "u1"), /average cost 100\.5000/);
  });
  test("detail: trades, prices and forms", () => {
    const open = (role, me, a, o = {}) => text(page({ tab: "holdings", holdings: [a], sel: { holding: a }, ...o }, role, me));
    const a = holding({ trades: [buy(), sell()], pending_sells: 1 });
    for (const id of ["im-by-save", "im-sl-save", "im-mk-save"]) assert.match(open("AUDITOR", "u1", a), new RegExp(id)); assert.doesNotMatch(open("APPROVER", "u3", a), /im-by-save/);
    assert.match(open("APPROVER", "u3", a), /im-tr-2-approve/); assert.match(open("APPROVER", "u3", a), /im-tr-2-reject/); assert.doesNotMatch(open("MANAGER", "u1", a), /im-tr-2-approve/); assert.match(open("MANAGER", "u1", a), /so a different person must decide it/);
    assert.doesNotMatch(open("AUDITOR", "u1", a), /so a different person must decide it/);
    assert.doesNotMatch(open("APPROVER", "u3", holding({ trades: [buy(), sell({ status: "APPLIED", realised: "100.00", proceeds: "517.00", cost_removed: "402.00" })] })), /im-tr-2-approve/);
    assert.match(open("AUDITOR", "u1", holding({ trades: [buy(), sell({ status: "APPLIED", realised: "115.00", proceeds: "517.00", cost_removed: "402.00", units_after: "6", basis_after: "603.00" })] })), /gain or loss 115\.00/);
    assert.match(open("APPROVER", "u3", holding({ units: "0", trades: [buy()] })), /im-close-save/); assert.doesNotMatch(open("APPROVER", "u3", a), /im-close-save/); assert.doesNotMatch(open("AUDITOR", "u1", holding({ status: "CLOSED" })), /im-by-save/);
    assert.match(open("AUDITOR", "u1", holding({ marks: [{ no: 1, price: "110.0000", as_of: "2026-03-09", source: "Broker statement", by: "u1" }] })), /2026-03-09: 110\.0000 \(Broker statement/);
  });
  test("every tab, role and person renders", () => {
    const full = [holding(), holding({ id: "h2", ref: "HD-002", units: "0", trades: [] }), holding({ id: "h3", ref: "HD-003", trades: [buy(), sell(), sell({ no: 3, status: "REJECTED", decision_note: "No" })], pending_sells: 1, mark_stale: true, no_mark: false,
      marks: [{ no: 1, price: "1.0000", as_of: "2026-03-09", source: "Stmt", by: "u1" }], latest_mark: { no: 1, price: "1.0000", as_of: "2026-03-09", source: "Stmt", by: "u1" }, market_value: "10.00", unrealised: "-995.00" }), holding({ id: "h4", ref: "HD-004", status: "CLOSED", units: "0" })];
    for (const role of ["OWNER", "ADMINISTRATOR", "ACCOUNTANT", "FINANCE_OFFICER", "APPROVER", "REVIEWER", "MANAGER", "AUDITOR", "EXTERNAL_AUDITOR", "READ_ONLY", "INVESTOR_REVIEWER"]) for (const me of ["u1", "u2", "u3", "u9"]) for (const [tab] of F.TABS)
      for (const sel of [null, ...full]) assert.doesNotThrow(() => page({ tab, holdings: full, sel: { holding: sel } }, role, me), `${role}/${me}/${tab}`);
  });
});

describe("wiring", () => {
  test("client calls the right paths and verbs", async () => {
    const calls = []; const c = new ApiClient("http://x"); c._request = async (m, p, o) => { calls.push([m, p, o && o.body]); return {}; };
    await c.imOverview(); await c.imOptions(); await c.setImPolicy({}); await c.imHoldings(); await c.imHolding("a/1"); await c.addImHolding({}); await c.closeImHolding("h1", "Fully sold and settled"); await c.buyIm("h1", {}); await c.proposeImSell("h1", {});
    await c.approveImSell("h1", 2, "ok"); await c.rejectImSell("h1", 2, "No"); await c.recordImMark("h1", {});
    assert.deepEqual(calls.map((x) => x.slice(0, 2)), [["GET", "/investments/overview"], ["GET", "/investments/options"], ["PUT", "/investments/policy"], ["GET", "/investments/holdings"], ["GET", "/investments/holdings/a%2F1"], ["POST", "/investments/holdings"],
      ["POST", "/investments/holdings/h1/close"], ["POST", "/investments/holdings/h1/buy"], ["POST", "/investments/holdings/h1/sells"], ["POST", "/investments/holdings/h1/sells/2/approve"], ["POST", "/investments/holdings/h1/sells/2/reject"], ["POST", "/investments/holdings/h1/marks"]]);
    assert.deepEqual(calls[6][2], { reason: "Fully sold and settled" }); assert.deepEqual(calls[9][2], { note: "ok" }); assert.deepEqual(calls[10][2], { reason: "No" });
  });
  test("menu wiring", () => {
    assert.ok(NAV_GROUPS.find((g) => g.id === "workspaces").paths.includes("/investments"));
    const app = fs.readFileSync(new URL("../src/app.js", import.meta.url), "utf8");
    assert.match(app, /path: "\/investments", label: "Investments", permission: PERMISSIONS\.AUDIT_READ/); assert.match(app, /path: "\/investments", name: "investments"/); assert.match(app, /renderInvestmentsPage\(authState\)/);
    assert.match(app, /uiState\.im = null; loadedOnce\.delete\("imLoading"\)/);
    assert.equal(E.WORKSPACE_PATHS.investments, "/investments"); assert.deepEqual(E.filterNavByWorkspaces([{ path: "/investments" }, { path: "/fpa" }], ["fpa"]).map((i) => i.path), ["/fpa"]);
  });
  test("only the shared client, no fetch or float arithmetic", () => {
    const src = fs.readFileSync(new URL("../src/pages/Investments.js", import.meta.url), "utf8") + fs.readFileSync(new URL("../src/lib/investments.js", import.meta.url), "utf8");
    assert.doesNotMatch(src, /fetch\(|XMLHttpRequest|parseFloat|toFixed/);
  });
});
