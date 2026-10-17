import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { buildDeptTrace, authorisedStep, purchasedStep, deliveredStep, unresolvedStep, HEALTH_ORDER, HEALTH_VOCAB } from "../src/lib/healthTrace.js";
import { Health } from "../src/pages/Health.js";
import { TABS, visibleTabs, caps } from "../src/lib/health.js";
import { ProofRail } from "../src/components/ProofRail.js";

const walk = (v, fn) => { if (!v || typeof v !== "object") return; fn(v); (v.children || []).forEach((c) => walk(c, fn)); };
const all = (v, pred) => { const out = []; walk(v, (n) => { if (pred(n)) out.push(n); }); return out; };
const text = (v) => { if (v == null || v === false) return ""; if (typeof v !== "object") return String(v); return (v.children || []).map(text).join(""); };
const byId = (v, id) => all(v, (n) => n.props && n.props.id === id)[0];

const D = { id: "d1", code: "PHARM", name: "Pharmacy", active: true };
const exec = { ref: "B-001", period_start: "2026-01-01", period_end: "2026-12-31", rows: [{ dept_id: "d1", dept: "Pharmacy", category: "MEDICAL_SUPPLIES", budget: "10000.00", committed: "0.00", spent: "1000.00", available: "9000.00", overspent: false }], unbudgeted: [] };
const po = (status, over = {}) => ({ id: "p" + status, ref: "PO-1", dept_id: "d1", supplier: "MedSupply", total: "1000.00", status, exception: null, lines: [{ line_no: 1, qty: "10.000", received_qty: "0.000" }], ...over });
const inv = (status, over = {}) => ({ id: "i" + status, ref: "INV-1", po_id: "pRECEIVED", invoice_no: "MS-1", amount: "1000.00", status, match: { matched: true, allowed: "1000.00" }, ...over });

describe("authorised", () => {
  test("approved line restated exactly, no sums", () => {
    const s = authorisedStep("d1", exec);
    assert.equal(s.state, "linked");
    assert.match(s.meta, /authorised 10000.00, committed 0.00, spent 1000.00, available 9000.00/);
  });
  test("no approved budget is missing; not loaded is not checked", () => {
    assert.equal(authorisedStep("d1", null).state, "missing");
    assert.equal(authorisedStep("d1", undefined).state, "unknown");
  });
  test("a department without a line is missing, not zero", () => {
    assert.equal(authorisedStep("zzz", exec).stateLabel, "No budget line");
  });
  test("overspent is said in words", () => {
    const s = authorisedStep("d1", { ...exec, rows: [{ ...exec.rows[0], overspent: true }] });
    assert.match(s.meta, /overspent/);
  });
});

describe("purchased and delivered", () => {
  test("none, waiting, approved, not checked", () => {
    assert.equal(purchasedStep([]).state, "missing");
    assert.equal(purchasedStep([po("PENDING_APPROVAL")]).state, "pending");
    assert.equal(purchasedStep([po("OPEN")]).state, "linked");
    assert.equal(purchasedStep(undefined).state, "unknown");
    assert.equal(purchasedStep([po("CANCELLED")]).state, "missing");
  });
  test("an over-budget approval is surfaced", () => {
    assert.match(purchasedStep([po("OPEN", { exception: { note: "x" } })]).meta, /over budget/);
  });
  test("delivery uses the server status and never claims confirmation", () => {
    assert.equal(deliveredStep([po("OPEN")]).state, "missing");
    assert.equal(deliveredStep([po("PARTIAL")]).state, "pending");
    const full = deliveredStep([po("RECEIVED")]);
    assert.equal(full.state, "linked");
    assert.match(full.meta, /has not confirmed that anything arrived/);
    assert.equal(deliveredStep([po("PENDING_APPROVAL")]).state, "missing");
    assert.equal(deliveredStep(undefined).state, "unknown");
  });
});

describe("unresolved", () => {
  test("clean only when it was checked", () => {
    assert.equal(unresolvedStep("d1", exec, []).state, "linked");
    assert.equal(unresolvedStep("d1", exec, undefined).state, "unknown");
  });
  test("an unmatched invoice is a missing-shaped step with the numbers", () => {
    const s = unresolvedStep("d1", exec, [inv("EXCEPTION", { amount: "900.00", match: { matched: false, allowed: "400.00" } })]);
    assert.deepEqual([s.state, s.stateLabel], ["missing", "Does not match"]);
    assert.match(s.meta, /amount 900.00 does not match: only 400.00/);
  });
  test("a matched, unverified invoice is in progress", () => {
    assert.equal(unresolvedStep("d1", exec, [inv("MATCHED")]).state, "pending");
  });
  test("verified, paid and cancelled invoices are not open", () => {
    assert.equal(unresolvedStep("d1", exec, [inv("VERIFIED"), inv("PAID"), inv("CANCELLED")]).state, "linked");
  });
  test("overspent lines and unbudgeted spending need a decision", () => {
    assert.equal(unresolvedStep("d1", { ...exec, rows: [{ ...exec.rows[0], overspent: true }] }, []).stateLabel, "Needs a decision");
    assert.equal(unresolvedStep("d1", { ...exec, unbudgeted: [{ dept_id: "d1", category: "OTHER" }] }, []).state, "missing");
    assert.equal(unresolvedStep("d1", { ...exec, unbudgeted: [{ dept_id: "other", category: "OTHER" }] }, []).state, "linked");
  });
});

describe("buildDeptTrace", () => {
  test("four steps in order, only this department's records", () => {
    const pos = [po("RECEIVED"), po("OPEN", { id: "x", dept_id: "d2" })];
    const t = buildDeptTrace({ dept: D, exec, pos, invoices: [inv("EXCEPTION"), inv("EXCEPTION", { id: "j", po_id: "x" })] });
    assert.deepEqual(t.steps.map((s) => s.key), HEALTH_ORDER);
    assert.equal(t.orders.length, 1);
    assert.equal(t.invoices.length, 1);
  });
  test("when orders could not be loaded, invoices cannot be placed either and nothing reads clean", () => {
    const t = buildDeptTrace({ dept: D, exec, pos: undefined, invoices: [inv("EXCEPTION")] });
    assert.equal(t.steps[1].state, "unknown");
    assert.equal(t.steps[3].state, "unknown");
    assert.equal(t.invoicesKnown, false);
  });
  test("no department, no trace", () => assert.equal(buildDeptTrace({ dept: null, exec, pos: [], invoices: [] }), null));
  test("it does no arithmetic: the source has no money maths", () => {
    const src = readFileSync(new URL("../src/lib/healthTrace.js", import.meta.url), "utf8");
    assert.doesNotMatch(src, /parseFloat|Number\(|\+ *r\.|reduce\(/);
  });
  test("no patient wording anywhere in the trace", () => {
    const src = readFileSync(new URL("../src/lib/healthTrace.js", import.meta.url), "utf8").replace(/no patient field|no patient information|There is no patient/gi, "");
    assert.doesNotMatch(src, /patient/i);
  });
});

describe("the tab and the page", () => {
  test("the Follow the money tab is offered to anyone who can read", () => {
    assert.ok(TABS.some(([id]) => id === "trace"));
    assert.ok(visibleTabs(caps("ACCOUNTANT")).some(([id]) => id === "trace"));
  });
  const hc = (over = {}) => ({ options: { facilities: [{ id: "f1", ref: "F-001", name: "Centre", status: "ACTIVE", currency: "NGN" }], limitations: [] }, facilityId: "f1", tab: "trace", data: {}, ref: { depts: [D, { id: "d2", code: "LAB", name: "Lab", active: true }] }, vault: [], trace: { exec, pos: [po("RECEIVED")], invoices: [inv("EXCEPTION", { match: { matched: false, allowed: "400.00" }, amount: "900.00" })] }, ...over });
  const page = (h2) => Health({ hc: h2, role: "ACCOUNTANT", userId: "u", loading: false, onRetry() {}, actions: { setTab() {}, setFacility() {}, setTraceDept() {} } });
  test("it draws the ledger with the health accent and a four-step rail", () => {
    const v = page(hc());
    const l = byId(v, "hc-trace-ledger");
    assert.equal(l.props["data-sector"], "health");
    assert.equal(all(byId(v, "hc-trace-rail"), (n) => n.props && n.props.className && String(n.props.className).split(" ").includes("pr-step")).length, 4);
    assert.match(text(byId(v, "hc-trace-invoices")), /Does not match: 400.00/);
  });
  test("an unchecked budget is said, not shown as zero", () => {
    const v = page(hc({ trace: { exec: undefined, pos: [], invoices: [] } }));
    assert.ok(byId(v, "hc-trace-budget-unknown"));
  });
  test("no approved budget says so", () => assert.ok(byId(page(hc({ trace: { exec: null, pos: [], invoices: [] } })), "hc-trace-nobudget")));
  test("lists that failed to load are 'Not checked', not empty", () => {
    const v = page(hc({ trace: { exec, pos: undefined, invoices: undefined } }));
    assert.ok(byId(v, "hc-trace-orders-unknown") && byId(v, "hc-trace-invoices-unknown"));
  });
  test("it is a read view: the trace contains no buttons that change records", () => {
    const l = byId(page(hc()), "hc-trace-ledger");
    assert.equal(all(l, (n) => n.tag === "button").length, 0);
  });
  test("the page text carries no patient fields", () => {
    const t = text(byId(page(hc()), "hc-trace"));
    assert.doesNotMatch(t, /diagnos|prescri|patient name/i);
  });
});
