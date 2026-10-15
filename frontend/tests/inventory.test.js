import { test, describe } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { Inventory } from "../src/pages/Inventory.js";
import * as F from "../src/lib/inventory.js";
import { ApiClient } from "../src/api/client.js";
import { NAV_GROUPS } from "../src/lib/home.js";
import * as E from "../src/lib/entityConfig.js";

const text = (v) => JSON.stringify(v);
const noop = new Proxy({}, { get: () => () => {} });
// u1 proposes, u3 approves, u9 bystander
const move = (o = {}) => ({ no: 1, kind: "RECEIPT", qty: 10, unit_cost: "100.00", value: "1000.00", reference: "GRN-001", moved_on: "2026-03-09", applied_on: "2026-03-09", status: "APPLIED", by: "u1", decided_by: null, decision_note: null, reason_kind: null, reason: null, qty_after: 10, value_after: "1000.00", ...o });
const adj = (o = {}) => move({ no: 2, kind: "ADJUST_DOWN", qty: 2, unit_cost: null, value: null, reference: null, moved_on: "2026-03-10", applied_on: null, status: "PENDING", reason_kind: "DAMAGE", reason: "Two bags were split open", qty_after: null, value_after: null, ...o });
const item = (o = {}) => ({ id: "i1", ref: "IT-001", sku: "RICE-25", name: "Rice 25kg bag", unit: "bag", currency: "NGN", reorder_level: 5, location: "Main store", status: "ACTIVE", on_hand: 10, value: "1000.00", average_cost: "100.00", moves: [move()], history: [],
  last_moved_on: "2026-03-09", pending_adjustments: 0, low_stock: false, out_of_stock: false, not_moving: false, ...o });
const ovw = () => ({ counts: { active: 2, discontinued: 1, low_stock: 1, out_of_stock: 0 }, totals: [{ currency: "NGN", items: 2, units: 14, value: "1500.00" }, { currency: "USD", items: 1, units: 4, value: "10.00" }],
  attention: [{ kind: "LOW_STOCK", count: 1, text: "item(s) are at or below their reorder level." }], policy: { stale_days: 180, meaning: "An item with stock but no movement for 180 days is flagged as not moving." }, limitations: ["ASAVEXA posts nothing to a ledger."] });
const state = (o = {}) => ({ tab: "overview", options: {}, ov: ovw(), items: [item()], sel: { item: null }, forms: { ...JSON.parse(JSON.stringify(F.EMPTY)), policy: F.policyForm(ovw().policy) }, notes: {}, formError: null, busy: false, error: null, notice: null, ...o });
const page = (o = {}, role = "OWNER", me = "u9") => Inventory({ iv: state(o), role, userId: me, loading: false, onRetry() {}, actions: noop });

describe("permissions", () => {
  test("who can prepare and approve", () => {
    for (const r of ["OWNER", "ADMINISTRATOR", "MANAGER", "AUDITOR"]) assert.ok(F.canPrepare(r), r);
    for (const r of ["OWNER", "APPROVER", "MANAGER"]) assert.ok(F.canApprove(r), r);
    for (const r of ["ACCOUNTANT", "READ_ONLY", "EXTERNAL_AUDITOR"]) { assert.ok(!F.canPrepare(r), r); assert.ok(!F.canApprove(r), r); }
    assert.ok(!F.canRead("ACCOUNTANT")); assert.ok(F.canRead("AUDITOR"));
  });
});

describe("payload builders", () => {
  const g = { sku: "rice-25", name: "Rice 25kg bag", unit: "bag", currency: "ngn", reorder_level: "1,000", location: "Main store" };
  test("item", () => {
    const ok = F.itemPayload(g).body; assert.deepEqual([ok.currency, ok.reorder_level, ok.sku], ["NGN", 1000, "rice-25"]); assert.equal(F.itemPayload({ ...g, reorder_level: "" }).body.reorder_level, 0);
    for (const bad of [{ sku: "x" }, { name: "ab" }, { unit: "" }, { currency: "NG" }, { currency: "N1A" }, { reorder_level: "-1" }, { reorder_level: "1.5" }, { reorder_level: "abc" }, { reorder_level: "99999999" }, { location: "x" }]) assert.ok(F.itemPayload({ ...g, ...bad }).problem, JSON.stringify(bad));
  });
  test("receipt and issue", () => {
    const r = { qty: "10", unit_cost: "1,500.5", moved_on: "2026-03-09", reference: "GRN-1" }; const b = F.receivePayload(r).body; assert.deepEqual([b.qty, b.unit_cost], [10, "1500.5"]);
    for (const bad of [{ qty: "0" }, { qty: "-1" }, { qty: "1.5" }, { qty: "" }, { qty: "10000001" }, { unit_cost: "0" }, { unit_cost: "1.234" }, { unit_cost: "abc" }, { moved_on: "2026-02-30" }, { reference: "x" }]) assert.ok(F.receivePayload({ ...r, ...bad }).problem, JSON.stringify(bad));
    const i = { qty: "3", moved_on: "2026-03-10", reference: "SIV-1" }; assert.equal(F.issuePayload(i).body.qty, 3);
    for (const bad of [{ qty: "0" }, { qty: "x" }, { moved_on: "soon" }, { reference: "" }]) assert.ok(F.issuePayload({ ...i, ...bad }).problem, JSON.stringify(bad));
  });
  test("adjustment", () => {
    const d = { direction: "DECREASE", qty: "2", unit_cost: "", reason_kind: "DAMAGE", reason: "Two bags were split open" }; assert.equal(F.adjustPayload(d, 10).body.qty, 2); assert.ok(!("unit_cost" in F.adjustPayload(d, 10).body));
    assert.match(F.adjustPayload({ ...d, qty: "11" }, 10).problem, /Only 10 on hand/); assert.ok(F.adjustPayload({ ...d, reason: "short" }, 10).problem); assert.ok(F.adjustPayload({ ...d, qty: "0" }, 10).problem);
    const up = { ...d, direction: "INCREASE" }; assert.ok(!("unit_cost" in F.adjustPayload(up, 10).body)); assert.equal(F.adjustPayload({ ...up, unit_cost: "2.50" }, 10).body.unit_cost, "2.50");
    assert.ok(F.adjustPayload(up, 0).problem); assert.ok(F.adjustPayload({ ...up, unit_cost: "x" }, 10).problem); assert.equal(F.adjustPayload({ ...up, unit_cost: "5" }, 0).body.unit_cost, "5");
  });
  test("settings", () => {
    assert.equal(F.policyPayload({ stale_days: "90" }).body.stale_days, 90); for (const v of ["29", "731", "x", "", "9", "4.5"]) assert.ok(F.policyPayload({ stale_days: v }).problem, v);
  });
});

describe("who sees which button", () => {
  test("separation of duties", () => {
    assert.ok(F.canMove(item(), "AUDITOR")); assert.ok(!F.canMove(item(), "APPROVER")); assert.ok(!F.canMove(item({ status: "DISCONTINUED" }), "AUDITOR"));
    assert.ok(F.canDecideAdjustment(adj(), "APPROVER", "u3")); assert.ok(!F.canDecideAdjustment(adj(), "MANAGER", "u1")); assert.ok(!F.canDecideAdjustment(adj({ status: "APPLIED" }), "APPROVER", "u3")); assert.ok(!F.canDecideAdjustment(adj(), "AUDITOR", "u3"));
    assert.ok(F.canDiscontinue(item({ on_hand: 0 }), "APPROVER")); assert.ok(!F.canDiscontinue(item(), "APPROVER")); assert.ok(!F.canDiscontinue(item({ on_hand: 0, pending_adjustments: 1 }), "APPROVER")); assert.ok(!F.canDiscontinue(item({ on_hand: 0 }), "AUDITOR"));
  });
});

describe("page", () => {
  test("overview", () => {
    const t = text(page()); for (const id of ["iv-attention", "iv-totals", "iv-counts", "iv-policy", "iv-limits", "iv-banner"]) assert.match(t, new RegExp(id));
    assert.match(t, /NGN: 2 item/); assert.match(t, /USD: 1 item/); assert.match(t, /never added together/); assert.match(t, /iv-policy-save/); assert.doesNotMatch(text(page({}, "AUDITOR", "u1")), /iv-policy-save/);
  });
  test("items tab", () => {
    const t = (role, me, o = {}) => text(page({ tab: "items", ...o }, role, me));
    assert.match(t("AUDITOR", "u1"), /iv-it-save/); assert.doesNotMatch(t("APPROVER", "u3"), /iv-it-save/);
    const bad = t("AUDITOR", "u1", { items: [item({ low_stock: true, not_moving: true, pending_adjustments: 1 })], formError: { form: "item", text: "Bad code" } });
    for (const w of ["Low stock", "Not moving", "adjustment\\(s\\) waiting", "item-problem"]) assert.match(bad, new RegExp(w)); assert.doesNotMatch(bad, /object Object/);
    assert.match(t("AUDITOR", "u1", { items: [item({ out_of_stock: true, on_hand: 0 })] }), /Out of stock/); assert.match(t("AUDITOR", "u1"), /average cost 100\.00/);
  });
  test("detail: movements and forms", () => {
    const open = (role, me, a, o = {}) => text(page({ tab: "items", items: [a], sel: { item: a }, ...o }, role, me));
    const a = item({ moves: [move(), adj()], pending_adjustments: 1 });
    for (const id of ["iv-rc-save", "iv-is-save", "iv-ad-save"]) assert.match(open("AUDITOR", "u1", a), new RegExp(id)); assert.doesNotMatch(open("APPROVER", "u3", a), /iv-rc-save/);
    assert.match(open("APPROVER", "u3", a), /iv-mv-2-approve/); assert.match(open("APPROVER", "u3", a), /iv-mv-2-reject/); assert.doesNotMatch(open("MANAGER", "u1", a), /iv-mv-2-approve/); assert.match(open("MANAGER", "u1", a), /so a different person must decide it/);
    assert.doesNotMatch(open("APPROVER", "u3", item({ moves: [move(), adj({ status: "APPLIED" })] })), /iv-mv-2-approve/);
    assert.doesNotMatch(open("AUDITOR", "u1", a), /iv-ad-cost/); const up = { forms: { ...state().forms, adjust: { ...state().forms.adjust, direction: "INCREASE" } } }; assert.match(open("AUDITOR", "u1", a, up), /iv-ad-cost/); assert.match(open("AUDITOR", "u1", item({ on_hand: 0, value: "0.00" }), up), /needed: no stock/);
    assert.match(open("APPROVER", "u3", item({ on_hand: 0, value: "0.00", moves: [] })), /iv-disc-save/); assert.doesNotMatch(open("APPROVER", "u3", a), /iv-disc-save/);
    assert.doesNotMatch(open("AUDITOR", "u1", item({ status: "DISCONTINUED" })), /iv-rc-save/);
    assert.match(open("AUDITOR", "u1", a), /Damage: Two bags were split open/); assert.match(open("AUDITOR", "u1", a), /After: 10 on hand, value 1000\.00/);
  });
  test("every tab, role and person renders", () => {
    const full = [item(), item({ id: "i2", ref: "IT-002", on_hand: 0, value: "0.00", out_of_stock: true, moves: [] }), item({ id: "i3", ref: "IT-003", moves: [move(), adj(), adj({ no: 3, kind: "ADJUST_UP", status: "REJECTED", decision_note: "No need", decided_by: "u3" })], pending_adjustments: 1, low_stock: true, not_moving: true }), item({ id: "i4", ref: "IT-004", status: "DISCONTINUED", on_hand: 0 })];
    for (const role of ["OWNER", "ADMINISTRATOR", "ACCOUNTANT", "FINANCE_OFFICER", "APPROVER", "REVIEWER", "MANAGER", "AUDITOR", "EXTERNAL_AUDITOR", "READ_ONLY"]) for (const me of ["u1", "u2", "u3", "u9"]) for (const [tab] of F.TABS)
      for (const sel of [null, ...full]) assert.doesNotThrow(() => page({ tab, items: full, sel: { item: sel } }, role, me), `${role}/${me}/${tab}`);
  });
});

describe("wiring", () => {
  test("client calls the right paths and verbs", async () => {
    const calls = []; const c = new ApiClient("http://x"); c._request = async (m, p, o) => { calls.push([m, p, o && o.body]); return {}; };
    await c.ivOverview(); await c.ivOptions(); await c.setIvPolicy({}); await c.ivItems(); await c.ivItem("a/1"); await c.addIvItem({}); await c.discontinueIvItem("i1", "No longer stocked"); await c.receiveIv("i1", {}); await c.issueIv("i1", {});
    await c.proposeIvAdjustment("i1", {}); await c.approveIvAdjustment("i1", 2, "ok"); await c.rejectIvAdjustment("i1", 2, "No");
    assert.deepEqual(calls.map((x) => x.slice(0, 2)), [["GET", "/inventory/overview"], ["GET", "/inventory/options"], ["PUT", "/inventory/policy"], ["GET", "/inventory/items"], ["GET", "/inventory/items/a%2F1"], ["POST", "/inventory/items"],
      ["POST", "/inventory/items/i1/discontinue"], ["POST", "/inventory/items/i1/receive"], ["POST", "/inventory/items/i1/issue"], ["POST", "/inventory/items/i1/adjustments"], ["POST", "/inventory/items/i1/adjustments/2/approve"], ["POST", "/inventory/items/i1/adjustments/2/reject"]]);
    assert.deepEqual(calls[6][2], { reason: "No longer stocked" }); assert.deepEqual(calls[10][2], { note: "ok" }); assert.deepEqual(calls[11][2], { reason: "No" });
  });
  test("menu wiring", () => {
    assert.ok(NAV_GROUPS.find((g) => g.id === "workspaces").paths.includes("/inventory"));
    const app = fs.readFileSync(new URL("../src/app.js", import.meta.url), "utf8");
    assert.match(app, /path: "\/inventory", label: "Inventory", permission: PERMISSIONS\.AUDIT_READ/); assert.match(app, /path: "\/inventory", name: "inventory"/); assert.match(app, /renderInventoryPage\(authState\)/);
    assert.match(app, /uiState\.iv = null; loadedOnce\.delete\("ivLoading"\)/);
    assert.equal(E.WORKSPACE_PATHS.inventory, "/inventory"); assert.deepEqual(E.filterNavByWorkspaces([{ path: "/inventory" }, { path: "/fpa" }], ["fpa"]).map((i) => i.path), ["/fpa"]);
  });
  test("only the shared client, no fetch or float arithmetic", () => {
    const src = fs.readFileSync(new URL("../src/pages/Inventory.js", import.meta.url), "utf8") + fs.readFileSync(new URL("../src/lib/inventory.js", import.meta.url), "utf8");
    assert.doesNotMatch(src, /fetch\(|XMLHttpRequest|parseFloat|toFixed/);
  });
});
