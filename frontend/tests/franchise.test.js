import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { Franchise } from "../src/pages/Franchise.js";
import * as F from "../src/lib/franchise.js";
import { ApiClient } from "../src/api/client.js";
import { NAV_GROUPS } from "../src/lib/home.js";
import * as E from "../src/lib/entityConfig.js";

const text = (v) => JSON.stringify(v);
const noop = new Proxy({}, { get: () => () => {} });
const row = (o = {}) => ({ no: 1, status: "PROPOSED", proposed_by: "u1", decision_note: null, ...o });
const rep = (o = {}) => row({ period: "2026-01", gross_sales: "1000.50", royalty: "50.03", submitted_on: "2026-02-08", due_date: "2026-02-10", late: false, ...o });
const pay = (o = {}) => row({ amount: "20.00", paid_on: "2026-02-20", note: "Bank transfer", ...o });
const loc = (o = {}) => ({ id: "l1", ref: "FL-001", name: "Lekki outlet", location_ref: "OUT-1", currency: "NGN", royalty_rate_pct: "5.00", start_period: "2026-01", due_day: 10, description: "The outlet run by the franchisee", status: "PROPOSED", proposed_by: "u1",
  decision_note: null, close_note: null, sales_total: "0.00", royalty_due: "0.00", paid_total: "0.00", balance: "0.00", balance_state: "SETTLED", overdue_amount: "0.00", late_reports: 0, missing_periods: [], pending: 0, reports: [], payments: [], history: [], ...o });
const open = (o = {}) => loc({ status: "APPROVED", ...o });
const ovw = () => ({ counts: { proposed: 1, approved: 2, rejected: 0, closed: 1 }, attention: [{ kind: "MISSING_REPORTS", count: 2, text: "month(s) are past their due date with no sales report recorded." }],
  by_currency: [{ currency: "NGN", locations: 1, sales_total: "1000.00", royalty_due: "50.00", paid_total: "0.00", balance: "50.00" }, { currency: "USD", locations: 2, sales_total: "300.50", royalty_due: "30.05", paid_total: "50.00", balance: "-19.95" }],
  setting: { grace_days: 0, meaning: "A report is late after 0 day(s)." }, limitations: ["ASAVEXA reads no agreement."] });
const state = (o = {}) => ({ tab: "overview", ov: ovw(), locations: [open()], sel: { location: null }, forms: { ...JSON.parse(JSON.stringify(F.EMPTY)), setting: { grace_days: "0" } }, notes: {}, formError: null, busy: false, error: null, notice: null, ...o });
const page = (o = {}, role = "OWNER", me = "u9") => Franchise({ st: state(o), role, userId: me, loading: false, onRetry() {}, actions: noop });
const sel = (x, role = "OWNER", me = "u9") => page({ tab: "locations", sel: { location: x } }, role, me);

describe("permissions and buttons", () => {
  test("who can prepare and approve", () => {
    for (const r of ["OWNER", "ADMINISTRATOR", "MANAGER", "AUDITOR"]) assert.ok(F.canPrepare(r), r);
    for (const r of ["OWNER", "APPROVER", "MANAGER"]) assert.ok(F.canApprove(r), r);
    for (const r of ["ACCOUNTANT", "READ_ONLY", "EXTERNAL_AUDITOR"]) assert.ok(!F.canPrepare(r) && !F.canApprove(r), r);
  });
  test("button rules", () => {
    assert.ok(F.canDecideLocation(loc(), "APPROVER", "u9")); assert.ok(!F.canDecideLocation(loc({ proposed_by: "u9" }), "APPROVER", "u9")); assert.ok(!F.canDecideLocation(open(), "APPROVER", "u9"));
    assert.ok(F.canRecord(open(), "AUDITOR")); assert.ok(!F.canRecord(loc(), "AUDITOR")); assert.ok(!F.canRecord(open(), "READ_ONLY"));
    assert.ok(F.canDecideRow(open(), rep(), "APPROVER", "u9")); assert.ok(!F.canDecideRow(open(), rep({ proposed_by: "u9" }), "APPROVER", "u9")); assert.ok(!F.canDecideRow(open(), rep({ status: "CONFIRMED" }), "APPROVER", "u9"));
    assert.ok(F.canClose(open(), "APPROVER")); assert.ok(!F.canClose(open({ pending: 1 }), "APPROVER")); assert.ok(!F.canClose(open(), "AUDITOR"));
  });
});

describe("payload builders", () => {
  const f = { name: "Lekki outlet", location_ref: "OUT-1", currency: "ngn", royalty_rate_pct: "7.5", due_day: "10", start_period: "2026-01", description: "The outlet run by the franchisee" };
  test("location", () => {
    assert.deepEqual(F.locationPayload(f).body, { name: "Lekki outlet", location_ref: "OUT-1", currency: "NGN", royalty_rate_pct: "7.5", due_day: 10, start_period: "2026-01", description: "The outlet run by the franchisee" });
    for (const [o, re] of [[{ name: "ab" }, /name/i], [{ location_ref: "x" }, /reference/i], [{ currency: "NG" }, /three-letter/], [{ royalty_rate_pct: "0" }, /more than zero/], [{ royalty_rate_pct: "100.01" }, /more than 100/], [{ royalty_rate_pct: "5.123" }, /rate/i], [{ royalty_rate_pct: "x" }, /rate/i], [{ royalty_rate_pct: "-1" }, /rate/i],
      [{ start_period: "2026-13" }, /real month/], [{ start_period: "2100-12" }, /future/], [{ due_day: "0" }, /due day/i], [{ due_day: "29" }, /due day/i], [{ due_day: "x" }, /due day/i], [{ description: "short" }, /description/i]]) assert.match(F.locationPayload({ ...f, ...o }).problem || "", re, text(o));
    assert.equal(F.locationPayload({ ...f, royalty_rate_pct: "100" }).body.royalty_rate_pct, "100");
  });
  test("report", () => {
    const g = { period: "2026-01", gross_sales: "1,000.50", submitted_on: "2026-02-08" };
    assert.deepEqual(F.reportPayload(g, { location: open() }).body, { period: "2026-01", gross_sales: "1000.50", submitted_on: "2026-02-08" }); assert.equal(F.reportPayload({ ...g, gross_sales: "0" }, { location: open() }).body.gross_sales, "0");
    for (const [o, re] of [[{ period: "2026-13" }, /real month/], [{ period: "2025-12" }, /before the location/], [{ period: "2100-01" }, /future/], [{ gross_sales: "x" }, /sales/i], [{ gross_sales: "-1" }, /sales/i], [{ gross_sales: "1.234" }, /sales/i],
      [{ submitted_on: "2026-02-30" }, /real date/], [{ submitted_on: "2999-01-01" }, /future/], [{ submitted_on: "1999-12-31" }, /century/]]) assert.match(F.reportPayload({ ...g, ...o }, { location: open() }).problem || "", re, text(o));
  });
  test("payment", () => {
    const g = { amount: "1,020.00", paid_on: "2026-02-20", note: "Bank transfer" };
    assert.deepEqual(F.paymentPayload(g).body, { amount: "1020.00", paid_on: "2026-02-20", note: "Bank transfer" });
    for (const [o, re] of [[{ amount: "0" }, /more than zero/], [{ amount: "x" }, /amount/i], [{ amount: "1.234" }, /amount/i], [{ paid_on: "2026-02-30" }, /real date/], [{ paid_on: "2999-01-01" }, /future/], [{ paid_on: "1999-01-01" }, /century/], [{ note: "ab" }, /note/i]]) assert.match(F.paymentPayload({ ...g, ...o }).problem || "", re, text(o));
  });
  test("setting", () => {
    assert.deepEqual(F.settingPayload({ grace_days: "14" }).body, { grace_days: 14 }); assert.deepEqual(F.settingPayload({ grace_days: "0" }).body, { grace_days: 0 });
    for (const v of ["-1", "61", "x", "1.5", ""]) assert.ok(F.settingPayload({ grace_days: v }).problem, v);
  });
});

describe("page", () => {
  test("overview", () => {
    const t = text(page());
    for (const s of ["Open: 2", "ASAVEXA reads no agreement", "fch-banner", "Missing reports", "NGN: 1 location(s), sales 1000.00, royalty due 50.00", "USD: 2 location(s)", "balance -19.95", "never added together", "fch-set-save"]) assert.ok(t.includes(s), s);
    assert.ok(!text(page({}, "READ_ONLY")).includes("fch-set-save"));
  });
  test("proposing is for preparers only", () => {
    assert.ok(text(page({ tab: "locations" }, "AUDITOR")).includes("fch-lc-save")); assert.ok(!text(page({ tab: "locations" }, "READ_ONLY")).includes("fch-lc-save"));
  });
  test("list shows flags", () => {
    const t = text(page({ tab: "locations", locations: [open({ missing_periods: ["2026-01", "2026-02"], overdue_amount: "10.00", balance: "50.03" })] })); for (const s of ["2 report(s) missing", "Royalty overdue", "royalty rate 5.00 percent", "balance 50.03"]) assert.ok(t.includes(s), s);
  });
  test("a proposed location: another person decides", () => {
    assert.ok(text(sel(loc(), "APPROVER", "u9")).includes("fch-lc-approve")); const own = text(sel(loc({ proposed_by: "u9" }), "APPROVER", "u9")); assert.ok(!own.includes("fch-lc-approve")); assert.ok(own.includes("a different person must decide it"));
    const prep = text(sel(loc(), "AUDITOR", "u9")); assert.ok(!prep.includes("fch-lc-approve")); assert.ok(!prep.includes("fch-rp-save"));
  });
  test("an open location: totals, missing months and forms", () => {
    const x = open({ sales_total: "1000.50", royalty_due: "50.03", paid_total: "20.00", balance: "30.03", balance_state: "OWED", overdue_amount: "30.03", late_reports: 1, missing_periods: ["2026-02"], reports: [rep(), rep({ no: 2, period: "2026-02", status: "CONFIRMED", late: true })], payments: [pay()], pending: 2 });
    const prep = text(sel(x, "AUDITOR", "u9")); for (const s of ["Confirmed sales 1000.50; royalty due 50.03; paid 20.00; balance 30.03 NGN", "Royalty owed", "Overdue amount 30.03", "Reports submitted late: 1", "2026-02", "royalty 50.03", "(late)", "fch-rp-save", "fch-py-save"]) assert.ok(prep.includes(s), s);
    assert.ok(!prep.includes("fch-reports-1-confirm"));
    const appr = text(sel(x, "APPROVER", "u9")); for (const s of ["fch-reports-1-confirm", "fch-reports-1-reject", "fch-payments-1-confirm"]) assert.ok(appr.includes(s), s); assert.ok(!appr.includes("fch-reports-2-confirm")); assert.ok(!appr.includes("fch-cl-save"));
    const own = text(sel(x, "APPROVER", "u1")); assert.ok(!own.includes("fch-reports-1-confirm")); assert.ok(own.includes("a different person must decide it"));
  });
  test("closed and read-only", () => {
    assert.ok(text(sel(open({ status: "CLOSED", close_note: "The franchise has ended" }))).includes("The franchise has ended")); assert.ok(text(sel(open(), "APPROVER", "u9")).includes("fch-cl-save"));
    const t = text(sel(open({ reports: [rep()], pending: 1 }), "READ_ONLY")); for (const s of ["fch-rp-save", "fch-reports-1-confirm", "fch-cl-save", "fch-lc-approve"]) assert.ok(!t.includes(s), s); assert.ok(t.includes("1000.50"));
  });
  test("errors, problems and loading", () => {
    assert.ok(text(page({ error: "Boom" })).includes("Boom")); assert.ok(text(page({ tab: "locations", formError: { form: "location", text: "The location name needs at least 3 characters." } })).includes("location-problem"));
    assert.ok(text(Franchise({ st: state(), role: "OWNER", userId: "u9", loading: true, onRetry() {}, actions: noop })).length > 0);
  });
});

describe("wiring", () => {
  test("client methods hit the right paths", async () => {
    const calls = []; const c = new ApiClient("http://x"); c.request = async (m, p, b) => { calls.push([m, p, b]); return {}; };
    c.get = (p) => c.request("GET", p); c.post = (p, b) => c.request("POST", p, b); c.put = (p, b) => c.request("PUT", p, b);
    await c.fchOptions(); await c.fchOverview(); await c.fchSetting(); await c.setFchSetting({}); await c.fchLocations(); await c.createFchLocation({}); await c.fchLocation("a b"); await c.approveFchLocation("l1", ""); await c.rejectFchLocation("l1", "r"); await c.closeFchLocation("l1", "c");
    await c.addFchReport("l1", {}); await c.confirmFchReport("l1", 2, ""); await c.rejectFchReport("l1", 2, "r"); await c.addFchPayment("l1", {}); await c.confirmFchPayment("l1", 2, ""); await c.rejectFchPayment("l1", 2, "r");
    assert.deepEqual(calls.map((x) => x[0] + " " + x[1]), ["GET /franchise/options", "GET /franchise/overview", "GET /franchise/setting", "PUT /franchise/setting", "GET /franchise/locations", "POST /franchise/locations", "GET /franchise/locations/a%20b", "POST /franchise/locations/l1/approve", "POST /franchise/locations/l1/reject",
      "POST /franchise/locations/l1/close", "POST /franchise/locations/l1/reports", "POST /franchise/locations/l1/reports/2/confirm", "POST /franchise/locations/l1/reports/2/reject", "POST /franchise/locations/l1/payments", "POST /franchise/locations/l1/payments/2/confirm", "POST /franchise/locations/l1/payments/2/reject"]);
  });
  test("home group and entity path", () => {
    assert.ok(NAV_GROUPS.some((g) => g.paths.includes("/franchise"))); assert.equal(E.WORKSPACE_PATHS.franchise, "/franchise");
    for (const m of [...Object.values(F.CONFIRM), ...Object.values(F.REJECT)]) assert.equal(typeof ApiClient.prototype[m], "function", m);
  });
});
