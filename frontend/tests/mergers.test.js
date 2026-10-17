import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { Mergers } from "../src/pages/Mergers.js";
import * as F from "../src/lib/mergers.js";
import { ApiClient } from "../src/api/client.js";
import { NAV_GROUPS } from "../src/lib/home.js";
import * as E from "../src/lib/entityConfig.js";

const text = (v) => JSON.stringify(v);
const noop = new Proxy({}, { get: () => () => {} });
const step = (o = {}) => ({ no: 1, status: "OPEN", proposed_by: "u1", done_on: null, done_by: null, done_note: null, decision_note: null, ...o });
const ck = (o = {}) => step({ title: "Audited accounts reviewed", area: "FINANCIAL", ...o });
const cn = (o = {}) => step({ title: "Regulator consent received", due_date: "2026-04-20", overdue: false, due_soon: false, ...o });
const ad = (o = {}) => ({ no: 1, kind: "DECREASE", amount: "50000.00", basis: "Working capital shortfall", status: "PROPOSED", proposed_by: "u1", decision_note: null, ...o });
const deal = (o = {}) => ({ id: "d1", ref: "MD-001", name: "Project Falcon", deal_ref: "FALCON", currency: "NGN", deal_type: "ACQUISITION", base_price: "1000000.00", target_close_date: "2026-09-30", description: "Acquisition of a distribution business", status: "PROPOSED", proposed_by: "u1",
  outcome: null, decision_note: null, close_note: null, adjusted_price: "1000000.00", price_change: "0.00", price_change_pct: "0.00", checklist_total: 0, checklist_confirmed: 0, checklist_pct: null, by_area: {}, conditions_total: 0, conditions_confirmed: 0,
  overdue_conditions: 0, due_soon_conditions: 0, open_checklist: 0, target_passed: false, pending: 0, checklist: [], conditions: [], adjustments: [], history: [], ...o });
const open = (o = {}) => deal({ status: "APPROVED", ...o });
const ovw = () => ({ counts: { proposed: 1, approved: 2, rejected: 0, closed: 1 }, outcomes: { completed: 0, abandoned: 1 }, attention: [{ kind: "CONDITIONS_OVERDUE", count: 1, text: "closing condition(s) are open and past their due date." }],
  by_currency: [{ currency: "NGN", deals: 1, base_price: "1000000.00", adjusted_price: "950000.00" }, { currency: "USD", deals: 1, base_price: "500.50", adjusted_price: "510.75" }], setting: { due_soon_days: 14, meaning: "Due soon within 14 day(s)." }, limitations: ["ASAVEXA values nothing."] });
const state = (o = {}) => ({ tab: "overview", ov: ovw(), deals: [open()], sel: { deal: null }, forms: { ...JSON.parse(JSON.stringify(F.EMPTY)), setting: { due_soon_days: "14" } }, notes: {}, formError: null, busy: false, error: null, notice: null, ...o });
const page = (o = {}, role = "OWNER", me = "u9") => Mergers({ st: state(o), role, userId: me, loading: false, onRetry() {}, actions: noop });
const sel = (x, role = "OWNER", me = "u9") => page({ tab: "deals", sel: { deal: x } }, role, me);

describe("permissions and buttons", () => {
  test("who can prepare and approve", () => {
    for (const r of ["OWNER", "ADMINISTRATOR", "MANAGER", "AUDITOR"]) assert.ok(F.canPrepare(r), r);
    for (const r of ["OWNER", "APPROVER", "MANAGER"]) assert.ok(F.canApprove(r), r);
    for (const r of ["ACCOUNTANT", "READ_ONLY", "EXTERNAL_AUDITOR"]) assert.ok(!F.canPrepare(r) && !F.canApprove(r), r);
  });
  test("button rules", () => {
    assert.ok(F.canDecideDeal(deal(), "APPROVER", "u9")); assert.ok(!F.canDecideDeal(deal({ proposed_by: "u9" }), "APPROVER", "u9")); assert.ok(!F.canDecideDeal(open(), "APPROVER", "u9"));
    assert.ok(F.canRecord(open(), "AUDITOR")); assert.ok(!F.canRecord(deal(), "AUDITOR")); assert.ok(!F.canRecord(open(), "READ_ONLY"));
    assert.ok(F.canDecideRow(open(), ad(), "APPROVER", "u9", "adjustments")); assert.ok(!F.canDecideRow(open(), ad({ proposed_by: "u9" }), "APPROVER", "u9", "adjustments")); assert.ok(!F.canDecideRow(open(), ad({ status: "CONFIRMED" }), "APPROVER", "u9", "adjustments"));
    assert.ok(!F.canDecideRow(open(), ck(), "APPROVER", "u9", "checklist"));                                                                                          // not marked yet
    assert.ok(F.canDecideRow(open(), ck({ status: "DONE", done_by: "u1" }), "APPROVER", "u9", "checklist")); assert.ok(!F.canDecideRow(open(), ck({ status: "DONE", done_by: "u9" }), "APPROVER", "u9", "checklist"));
    assert.ok(F.canDecideRow(open(), cn({ status: "DONE", done_by: "u1" }), "APPROVER", "u9", "conditions"));
    assert.ok(F.canClose(open(), "APPROVER")); assert.ok(!F.canClose(open({ pending: 1 }), "APPROVER")); assert.ok(!F.canClose(open(), "AUDITOR"));
  });
});

describe("payload builders", () => {
  const f = { name: "Project Falcon", deal_ref: "FALCON", currency: "ngn", deal_type: "MERGER", base_price: "1,000,000", target_close_date: "2026-09-30", description: "Acquisition of a distribution business" };
  test("deal", () => {
    assert.deepEqual(F.dealPayload(f).body, { name: "Project Falcon", deal_ref: "FALCON", currency: "NGN", deal_type: "MERGER", base_price: "1000000", target_close_date: "2026-09-30", description: "Acquisition of a distribution business" });
    for (const [o, re] of [[{ name: "ab" }, /name/i], [{ deal_ref: "x" }, /reference/i], [{ currency: "NG" }, /three-letter/], [{ deal_type: "SWAP" }, /type/i], [{ base_price: "0" }, /more than zero/], [{ base_price: "x" }, /price/i], [{ base_price: "1.234" }, /price/i], [{ target_close_date: "2026-02-30" }, /real date/],
      [{ target_close_date: "1999-01-01" }, /between 2000/], [{ target_close_date: "2101-01-01" }, /between 2000/], [{ description: "short" }, /description/i]]) assert.match(F.dealPayload({ ...f, ...o }).problem || "", re, text(o));
  });
  test("checklist, condition, adjustment", () => {
    assert.deepEqual(F.checklistPayload({ title: "Contracts reviewed", area: "LEGAL" }).body, { title: "Contracts reviewed", area: "LEGAL" });
    for (const o of [{ title: "ab" }, { area: "SPACE" }]) assert.ok(F.checklistPayload({ title: "Contracts reviewed", area: "LEGAL", ...o }).problem, text(o));
    assert.deepEqual(F.conditionPayload({ title: "Regulator consent", due_date: "2026-04-20" }).body, { title: "Regulator consent", due_date: "2026-04-20" });
    for (const o of [{ title: "ab" }, { due_date: "2026-02-30" }, { due_date: "1999-01-01" }, { due_date: "2101-01-01" }]) assert.ok(F.conditionPayload({ title: "Regulator consent", due_date: "2026-04-20", ...o }).problem, text(o));
    assert.deepEqual(F.adjustmentPayload({ kind: "INCREASE", amount: "1,234.50", basis: "Inventory above the level" }).body, { kind: "INCREASE", amount: "1234.50", basis: "Inventory above the level" });
    for (const [o, re] of [[{ kind: "UP" }, /up or down/], [{ amount: "0" }, /more than zero/], [{ amount: "x" }, /amount/i], [{ amount: "1.234" }, /amount/i], [{ amount: "-1" }, /amount/i], [{ basis: "short" }, /basis/i]]) assert.match(F.adjustmentPayload({ kind: "INCREASE", amount: "10", basis: "Inventory above the level", ...o }).problem || "", re, text(o));
  });
  test("done and setting", () => {
    assert.deepEqual(F.donePayload({ done_on: "2026-03-30", note: "Documents received and filed" }).body, { done_on: "2026-03-30", note: "Documents received and filed" });
    for (const o of [{ done_on: "x" }, { done_on: "2999-01-01" }, { done_on: "1999-01-01" }, { note: "short" }]) assert.ok(F.donePayload({ done_on: "2026-03-30", note: "Documents received and filed", ...o }).problem, text(o));
    assert.deepEqual(F.settingPayload({ due_soon_days: "30" }).body, { due_soon_days: 30 }); for (const v of ["0", "366", "x", "1.5", ""]) assert.ok(F.settingPayload({ due_soon_days: v }).problem, v);
  });
});

describe("page", () => {
  test("overview", () => {
    const t = text(page());
    for (const s of ["Open: 2", "Closed as completed: 0; abandoned: 1", "ASAVEXA values nothing", "ma-banner", "Conditions overdue", "NGN: 1 deal(s), base price 1000000.00, adjusted price 950000.00", "USD: 1 deal(s)", "never added together", "ma-set-save"]) assert.ok(t.includes(s), s);
    assert.ok(!text(page({}, "READ_ONLY")).includes("ma-set-save"));
  });
  test("proposing is for preparers only", () => {
    assert.ok(text(page({ tab: "deals" }, "AUDITOR")).includes("ma-dl-save")); assert.ok(!text(page({ tab: "deals" }, "READ_ONLY")).includes("ma-dl-save"));
  });
  test("list shows flags", () => {
    const t = text(page({ tab: "deals", deals: [open({ target_passed: true, overdue_conditions: 2, adjusted_price: "950000.00" }), deal({ ref: "MD-002", status: "CLOSED", outcome: "ABANDONED" })] })); for (const s of ["Target date passed", "2 condition(s) overdue", "adjusted 950000.00", "Abandoned"]) assert.ok(t.includes(s), s);
  });
  test("a proposed deal: another person decides", () => {
    assert.ok(text(sel(deal(), "APPROVER", "u9")).includes("ma-dl-approve")); const own = text(sel(deal({ proposed_by: "u9" }), "APPROVER", "u9")); assert.ok(!own.includes("ma-dl-approve")); assert.ok(own.includes("a different person must decide it"));
    const prep = text(sel(deal(), "AUDITOR", "u9")); assert.ok(!prep.includes("ma-dl-approve")); assert.ok(!prep.includes("ma-ck-save"));
  });
  test("an open deal: price, progress, rows and forms", () => {
    const x = open({ adjusted_price: "949999.50", price_change: "-50000.50", price_change_pct: "-5.00", checklist_total: 3, checklist_confirmed: 1, checklist_pct: "33.33", by_area: { FINANCIAL: { total: 2, confirmed: 1 }, LEGAL: { total: 1, confirmed: 0 } }, conditions_total: 1, conditions_confirmed: 0,
      checklist: [ck(), ck({ no: 2, title: "Contracts reviewed", area: "LEGAL", status: "DONE", done_by: "u1", done_on: "2026-03-30", done_note: "Documents received" })], conditions: [cn({ overdue: true })], adjustments: [ad()], pending: 2 });
    const prep = text(sel(x, "AUDITOR", "u9")); for (const s of ["Adjusted price 949999.50 NGN (change -50000.50, -5.00 percent", "Checklist: 1 of 3 confirmed (33.33 percent)", "Financial: 1 of 2 confirmed", "Overdue", "ma-ck-save", "ma-cn-save", "ma-ad-save", "ma-checklist-1-done", "ma-conditions-1-done", "Mark as provided", "Mark as met"]) assert.ok(prep.includes(s), s);
    assert.ok(!prep.includes("ma-adjustments-1-confirm")); assert.ok(!prep.includes("ma-checklist-2-done"));
    const appr = text(sel(x, "APPROVER", "u9")); for (const s of ["ma-checklist-2-confirm", "ma-adjustments-1-confirm", "ma-adjustments-1-reject"]) assert.ok(appr.includes(s), s); assert.ok(!appr.includes("ma-checklist-1-confirm")); assert.ok(!appr.includes("ma-cl-save"));
    const own = text(sel(x, "APPROVER", "u1")); assert.ok(!own.includes("ma-adjustments-1-confirm")); assert.ok(own.includes("a different person must decide it"));
  });
  test("closing offers the outcome; closed shows it; read-only", () => {
    const t = text(sel(open(), "APPROVER", "u9")); for (const s of ["ma-cl-save", "ma-cl-outcome", "Completed", "Abandoned"]) assert.ok(t.includes(s), s);
    assert.ok(text(sel(open({ status: "CLOSED", outcome: "COMPLETED", close_note: "The deal has closed" }))).includes("Closed as completed: The deal has closed"));
    const ro = text(sel(open({ adjustments: [ad()], pending: 1 }), "READ_ONLY")); for (const s of ["ma-ad-save", "ma-adjustments-1-confirm", "ma-cl-save", "ma-dl-approve"]) assert.ok(!ro.includes(s), s); assert.ok(ro.includes("50000.00"));
    assert.ok(text(sel(open())).includes("Checklist: no items yet"));
  });
  test("errors, problems and loading", () => {
    assert.ok(text(page({ error: "Boom" })).includes("Boom")); assert.ok(text(page({ tab: "deals", formError: { form: "deal", text: "The deal name needs at least 3 characters." } })).includes("deal-problem"));
    assert.ok(text(Mergers({ st: state(), role: "OWNER", userId: "u9", loading: true, onRetry() {}, actions: noop })).length > 0);
  });
});

describe("wiring", () => {
  test("client methods hit the right paths", async () => {
    const calls = []; const c = new ApiClient("http://x"); c.request = async (m, p, b) => { calls.push([m, p, b]); return {}; };
    c.get = (p) => c.request("GET", p); c.post = (p, b) => c.request("POST", p, b); c.put = (p, b) => c.request("PUT", p, b);
    await c.maOptions(); await c.maOverview(); await c.maSetting(); await c.setMaSetting({}); await c.maDeals(); await c.createMaDeal({}); await c.maDeal("a b"); await c.approveMaDeal("d1", ""); await c.rejectMaDeal("d1", "r"); await c.closeMaDeal("d1", { outcome: "COMPLETED", reason: "done" });
    await c.addMaChecklist("d1", {}); await c.provideMaChecklist("d1", 2, {}); await c.confirmMaChecklist("d1", 2, ""); await c.rejectMaChecklist("d1", 2, "r");
    await c.addMaCondition("d1", {}); await c.meetMaCondition("d1", 2, {}); await c.confirmMaCondition("d1", 2, ""); await c.rejectMaCondition("d1", 2, "r");
    await c.addMaAdjustment("d1", {}); await c.confirmMaAdjustment("d1", 2, ""); await c.rejectMaAdjustment("d1", 2, "r");
    assert.deepEqual(calls.map((x) => x[0] + " " + x[1]), ["GET /mergers/options", "GET /mergers/overview", "GET /mergers/setting", "PUT /mergers/setting", "GET /mergers/deals", "POST /mergers/deals", "GET /mergers/deals/a%20b", "POST /mergers/deals/d1/approve", "POST /mergers/deals/d1/reject", "POST /mergers/deals/d1/close",
      "POST /mergers/deals/d1/checklist", "POST /mergers/deals/d1/checklist/2/provide", "POST /mergers/deals/d1/checklist/2/confirm", "POST /mergers/deals/d1/checklist/2/reject",
      "POST /mergers/deals/d1/conditions", "POST /mergers/deals/d1/conditions/2/meet", "POST /mergers/deals/d1/conditions/2/confirm", "POST /mergers/deals/d1/conditions/2/reject",
      "POST /mergers/deals/d1/adjustments", "POST /mergers/deals/d1/adjustments/2/confirm", "POST /mergers/deals/d1/adjustments/2/reject"]);
    assert.deepEqual(calls[9][2], { outcome: "COMPLETED", reason: "done" });
  });
  test("home group and entity path", () => {
    assert.ok(NAV_GROUPS.some((g) => g.paths.includes("/mergers"))); assert.equal(E.WORKSPACE_PATHS.mergers, "/mergers");
    for (const m of [...Object.values(F.PROVIDE), ...Object.values(F.CONFIRM), ...Object.values(F.REJECT)]) assert.equal(typeof ApiClient.prototype[m], "function", m);
  });
});
