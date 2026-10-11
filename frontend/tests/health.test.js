import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { Health, choices } from "../src/pages/Health.js";
import * as H from "../src/lib/health.js";
import { ApiClient } from "../src/api/client.js";
import { PERMISSIONS, ROLE_PERMISSIONS } from "../src/lib/permissions.js";

const text = (v) => JSON.stringify(v);
function find(v, pred, out = []) { if (!v || typeof v !== "object") return out; if (pred(v)) out.push(v); for (const c of v.children || []) find(c, pred, out); return out; }
const byId = (v, id) => find(v, (n) => n.props && n.props.id === id)[0];
const noop = new Proxy({}, { get: () => () => {} });
const FAC = { id: "f1", ref: "F-001", name: "North Clinic", status: "ACTIVE" };
const metric = (label, value, state = "OK", note = "") => ({ label, value, state, formula: "x / y", source: "Records", drill: "budgets", note });
const DASH = { facility: "North Clinic", facility_ref: "F-001", currency: "NGN", period_start: "2026-01-01", period_end: "2026-12-31", generated_at: "2026-02-15T09:00:00",
  metrics: { spent: metric("Actual expenditure", "1200.00"), claim_payments: metric("Claim payments received", null, "RESTRICTED", "You do not have access to claims information."), budget_total: metric("Total approved budget", null, "UNAVAILABLE", "Approve a budget") } };
const base = (o = {}) => ({ options: { categories: ["STAFFING"], facility_types: ["CLINIC"], facilities: [FAC], limitations: ["It holds no patient names."] }, facilityId: "f1", tab: "dashboard", data: {}, ref: { depts: [{ id: "d1", code: "OPD", name: "Outpatients", active: true }, { id: "d2", code: "OLD", name: "Closed", active: false }], suppliers: [{ id: "s1", name: "MedCo", status: "AUTHORISED" }, { id: "s2", name: "Bad", status: "SUSPENDED" }] },
  vault: [], dashboard: DASH, form: null, detail: null, noteText: "", busy: false, error: null, notice: null, ...o });
const page = (hc, role = "OWNER", userId = "u1") => Health({ hc, role, userId, loading: false, onRetry() {}, actions: noop });

describe("permissions mirror the backend", () => {
  test("role matrix", () => {
    const c = (r) => H.caps(r);
    assert.ok(c("OWNER").admin && c("OWNER").approve && c("OWNER").claims && c("OWNER").staffing);
    assert.ok(c("ADMINISTRATOR").admin && c("ADMINISTRATOR").prepare && !c("ADMINISTRATOR").claims && !c("ADMINISTRATOR").approve);
    assert.ok(c("ACCOUNTANT").claims && !c("ACCOUNTANT").staffing && !c("ACCOUNTANT").approve);
    assert.ok(c("FINANCE_OFFICER").staffing && c("FINANCE_OFFICER").claims);
    assert.ok(c("APPROVER").approve && !c("APPROVER").prepare);
    for (const r of ["AUDITOR", "READ_ONLY", "REVIEWER"]) assert.ok(c(r).read && !c(r).prepare && !c(r).claims && !c(r).staffing, r);
    for (const r of ["DONOR", "REGULATOR", "INVESTOR_REVIEWER"]) assert.ok(!c(r).read, r);
    assert.equal(PERMISSIONS.HEALTH_READ, "health:read"); assert.ok(ROLE_PERMISSIONS.OWNER.includes(PERMISSIONS.HEALTH_CLAIMS));
  });
});

describe("validators", () => {
  test("dates, amounts, quantities, months", () => {
    assert.ok(H.isRealDate("2026-02-28") && !H.isRealDate("2026-02-30") && !H.isRealDate("28/02/2026"));
    assert.ok(H.isAmount("1500") && H.isAmount("1500.5") && !H.isAmount("1,500") && !H.isAmount("-5") && !H.isAmount("1.234"));
    assert.ok(H.isQty("12.5") && !H.isQty("1.2345") && H.isSignedQty("-3") && !H.isQty("-3"));
    assert.ok(H.isMonth("2026-12") && !H.isMonth("2026-13"));
    assert.ok(H.noteProblem("ab") && !H.noteProblem("abc"));
  });
  test("a form reports the first problem and builds a trimmed body", () => {
    const def = H.FORMS.supplier;
    assert.match(H.formProblem(def, { name: "" }), /Name is required/);
    assert.match(H.formProblem(def, { name: "A" }), /at least 2/);
    assert.equal(H.formProblem(def, { name: "MedCo", contact: "" }), null);
    assert.deepEqual(H.formBody(def, { name: "  MedCo ", contact: "" }), { name: "MedCo" });
  });
  test("lines are checked one by one", () => {
    const def = H.FORMS.requisition, v = H.emptyForm(def);
    v.dept_id = "d1"; v.category = "MEDICAL_SUPPLIES"; v.justification = "Restock the pharmacy";
    assert.match(H.formProblem(def, v), /item 1: Description is required/);
    v.lines = [{ description: "Gloves", item_id: "", qty: "10", unit_price: "1.234" }];
    assert.match(H.formProblem(def, v), /Unit price/);
    v.lines = [{ description: "Gloves", item_id: "", qty: "10", unit_price: "2.50" }];
    assert.equal(H.formProblem(def, v), null);
    assert.deepEqual(H.formBody(def, v).lines, [{ description: "Gloves", qty: "10", unit_price: "2.50" }]);
    v.lines = []; assert.match(H.formProblem(def, v), /at least one item/);
  });
  test("the access form sends a list of facility ids, not a string", () => {
    const def = H.FORMS.access, v = H.emptyForm(def);
    v.user_id = "u9"; assert.match(H.formProblem(def, v), /at least one facility/);
    v.facility_ids = ["f1", "f2"]; assert.equal(H.formProblem(def, v), null);
    assert.deepEqual(H.formBody(def, v).facility_ids, ["f1", "f2"]);
  });
  test("no form has a patient field", () => {
    const names = JSON.stringify(Object.values(H.FORMS).map((f) => f.fields.map((x) => x.k)));
    for (const bad of ["patient", "diagnosis", "prescription", "national_id", "nin", "dob"]) assert.ok(!names.includes(bad), bad);
  });
});

describe("who sees which button", () => {
  const sec = H.SECTIONS;
  test("the person who submitted cannot approve", () => {
    const row = { status: "SUBMITTED", submitted_by: "u1" };
    assert.deepEqual(H.visibleActions(sec.budgets, row, H.caps("MANAGER"), "u1", {}).map((a) => a.id).filter((i) => i === "approve"), []);
    assert.ok(H.visibleActions(sec.budgets, row, H.caps("MANAGER"), "u2", {}).some((a) => a.id === "approve"));
    assert.ok(!H.visibleActions(sec.budgets, row, H.caps("ADMINISTRATOR"), "u2", {}).some((a) => a.id === "approve"));
  });
  test("an invoice needs two different approvers before it can be paid", () => {
    const row = { status: "VERIFIED", recorded_by: "u1", verified_by: "u2", match: { matched: true } };
    const ids = (u) => H.visibleActions(sec.invoices, row, H.caps("APPROVER"), u, {}).map((a) => a.id);
    assert.ok(!ids("u1").includes("approve-pay") && !ids("u2").includes("approve-pay") && ids("u3").includes("approve-pay"));
  });
  test("claims actions are hidden from people without claims access", () => {
    assert.deepEqual(H.visibleTabs(H.caps("AUDITOR")).map(([i]) => i).filter((i) => i === "claims"), []);
    assert.deepEqual(H.visibleSections("claims", H.caps("AUDITOR")).map(([i]) => i).filter((i) => i !== "payers"), []);
    assert.deepEqual(H.visibleTabs(H.caps("ADMINISTRATOR")).map(([i]) => i).filter((i) => i === "claims" || i === "staffing"), []);
    assert.ok(H.visibleTabs(H.caps("OWNER")).some(([i]) => i === "claims"));
  });
  test("a note is demanded where the server needs one", () => {
    const rej = sec.budgets.actions.find((a) => a.id === "reject"); assert.equal(H.needsNote(rej, {}), 3);
    const po = sec.orders.actions.find((a) => a.id === "approve"); assert.equal(H.needsNote(po, {}), 0);
  });
  test("a write-off needs a reason and a second person", () => {
    const wo = sec.claims.actions.find((a) => a.id === "writeoff"); assert.equal(H.needsNote(wo, {}), 10);
    const row = { status: "SUBMITTED", writeoff: { status: "PENDING", requested_by: "u1" } };
    const ids = (u) => H.visibleActions(sec.claims, row, H.caps("MANAGER"), u, {}).map((a) => a.id);
    assert.ok(!ids("u1").includes("approve-wo") && ids("u2").includes("approve-wo") && !ids("u2").includes("writeoff"));
  });
});

describe("page", () => {
  test("shows the privacy banner and the dashboard states", () => {
    const v = page(base());
    assert.match(text(byId(v, "hc-banner")), /no patient names/);
    assert.ok(byId(v, "hm-spent") && byId(v, "hm-claim_payments"));
    assert.match(text(byId(v, "hm-claim_payments")), /Restricted/);
    assert.match(text(byId(v, "hm-budget_total")), /Not available/);
    assert.match(text(byId(v, "hm-spent")), /1200.00/);
    assert.match(text(byId(v, "hc-limits")), /holds no patient names/);
  });
  test("tabs follow the role", () => {
    const tabs = (role) => find(page(base(), role), (n) => n.props && /^hc-tab-/.test(n.props.id || "")).map((n) => n.props.id);
    assert.ok(tabs("OWNER").includes("hc-tab-claims") && tabs("OWNER").includes("hc-tab-staffing"));
    assert.ok(!tabs("AUDITOR").includes("hc-tab-claims") && !tabs("ADMINISTRATOR").includes("hc-tab-staffing"));
  });
  test("a role with no access sees no workspace", () => { assert.match(text(page(base(), "DONOR")), /No access/); });
  test("no facility gives a clear message", () => {
    assert.match(text(page(base({ options: { facilities: [], limitations: [] } }), "READ_ONLY")), /No facility available/);
    assert.ok(byId(page(base({ options: { facilities: [], limitations: [] }, facilityId: "" }), "ADMINISTRATOR"), "hc-tab-setup"));
  });
  test("a list shows rows and only the permitted buttons", () => {
    const b = { id: "b1", ref: "B-001", name: "2026", period_start: "2026-01-01", period_end: "2026-12-31", version: 1, status: "SUBMITTED", submitted_by: "u1", lines: [], transfers: [] };
    const hc = base({ tab: "budgets", data: { budgets: [b] } });
    const mine = page(hc, "MANAGER", "u1"), other = page(hc, "MANAGER", "u2");
    assert.ok(byId(mine, "hc-table-budgets") && byId(mine, "hc-new-budgets"));
    assert.ok(!byId(mine, "hc-act-approve-b1") && byId(other, "hc-act-approve-b1"));
    assert.ok(!byId(page(hc, "AUDITOR", "u2"), "hc-new-budgets") && !byId(page(hc, "AUDITOR", "u2"), "hc-act-approve-b1"));
  });
  test("an open form is drawn with lines and a save button", () => {
    const def = H.FORMS.budget, hc = base({ tab: "budgets", data: { budgets: [] }, form: { name: "budget", secId: "budgets", row: null, values: H.emptyForm(def) } });
    const v = page(hc, "MANAGER");
    for (const id of ["hf-name", "hf-period_start", "hf-lines-0-dept_id", "hf-lines-0-amount", "hf-lines-add", "hf-save", "hf-cancel"]) assert.ok(byId(v, id), id);
  });
  test("drop-downs only offer active departments and authorised suppliers", () => {
    const hc = base();
    assert.deepEqual(choices("depts", hc).map(([i]) => i), ["d1"]);
    assert.deepEqual(choices("suppliers", hc).map(([i]) => i), ["s1"]);
    assert.deepEqual(choices("categories", hc), [["STAFFING", "Staffing"]]);
    assert.deepEqual(choices("row_lines", hc, { lines: [{ line_id: "l1", dept: "OPD", category: "STAFFING", amount: "10.00" }] }).map(([i]) => i), ["l1"]);
  });
  test("an error and a notice are shown", () => {
    const v = page(base({ error: "Something failed", notice: "Saved." }));
    assert.match(text(v), /Something failed/); assert.match(text(byId(v, "hc-notice")), /Saved/);
  });
});

describe("client", () => {
  test("paths go under /health and the report export sends the token", async () => {
    const calls = [];
    const fetch = async (url, init) => { calls.push([url, init]); return { ok: true, status: 200, headers: { get: (k) => (k === "Content-Disposition" ? 'attachment; filename="r.csv"' : null) }, blob: async () => "BLOB", text: async () => "{}", json: async () => ({}) }; };
    const api = new ApiClient({ baseUrl: "http://x", fetchImpl: fetch, getToken: () => "tok" });
    await api.hcGet("/facilities");
    assert.match(calls[0][0], /^http:\/\/x\/health\/facilities/);
    const out = await api.exportHcReport("a/b");
    assert.match(calls[1][0], /\/health\/reports\/a%2Fb\/export$/);
    assert.equal(calls[1][1].headers.Authorization, "Bearer tok"); assert.equal(out.filename, "r.csv");
  });
});

test("quantities drop trailing zeros", () => {
  assert.equal(H.qtyText("60.000"), "60"); assert.equal(H.qtyText("12.500"), "12.5"); assert.equal(H.qtyText("100"), "100"); assert.equal(H.qtyText("0.250"), "0.25");
});
