import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { buildTrace, supplierStep, contractStep, orderStep, deliveryStep, invoiceStep, paymentStep, reviewStep, PROC_ORDER, PROC_VOCAB } from "../src/lib/procTrace.js";
import { Procurement } from "../src/pages/Procurement.js";
import { normaliseSteps, railSummary, ProofRail } from "../src/components/ProofRail.js";
import { TABS } from "../src/lib/procurement.js";

const walk = (v, fn) => { if (!v || typeof v !== "object") return; fn(v); (v.children || []).forEach((c) => walk(c, fn)); };
const all = (v, pred) => { const out = []; walk(v, (n) => { if (pred(n)) out.push(n); }); return out; };
const text = (v) => { if (v == null || v === false) return ""; if (typeof v !== "object") return String(v); return (v.children || []).map(text).join(""); };
const byId = (v, id) => all(v, (n) => n.props && n.props.id === id)[0];

const order = { id: "o1", ref: "PO-001", supplier_id: "s1", supplier_name: "Acme", contract_id: null, contract_ref: null, currency: "NGN", total: "1000.00", status: "APPROVED", fulfilment: "NOT_RECEIVED", requested_by: "u1", purpose: "Paper for the office", expected_date: "2026-11-01", approvals: [], approvals_needed: 1,
  lines: [{ n: 1, description: "Paper", qty: "10.000", unit_price: "100.00", received: "0.000", invoiced: "0.000", outstanding: "10.000" }] };
const sup = { id: "s1", ref: "SU-001", name: "Acme", status: "ACTIVE", related_party: false };
const inv = (status, over = {}) => ({ id: "i" + status, ref: "IV-001", order_id: "o1", invoice_number: "A1", status, flags: [], total: "1000.00", currency: "NGN", lines: [], ...over });

describe("each step says only what was recorded", () => {
  test("supplier: approved, waiting, suspended, missing, or not checked", () => {
    assert.equal(supplierStep(order, [sup]).state, "linked");
    assert.equal(supplierStep(order, [{ ...sup, status: "PENDING" }]).state, "pending");
    const sus = supplierStep(order, [{ ...sup, status: "SUSPENDED" }]);
    assert.deepEqual([sus.state, sus.stateLabel], ["missing", "Suspended"]);
    assert.equal(supplierStep(order, []).state, "missing");
    assert.equal(supplierStep(order, undefined).state, "unknown");
    assert.match(supplierStep(order, [{ ...sup, related_party: true, related_party_note: "cousin of the manager" }]).meta, /Connected party: cousin/);
  });
  test("contract: none is said plainly; ended is a gap; money is the server's own text", () => {
    assert.equal(contractStep(order, []).stateLabel, "No contract");
    const withC = { ...order, contract_id: "c1", contract_ref: "CT-001" };
    const c = { id: "c1", ref: "CT-001", title: "Supply", status: "ACTIVE", state: "IN_FORCE", currency: "NGN", ceiling: "6000.00", committed: "1000.00", remaining: "5000.00" };
    assert.equal(contractStep(withC, [c]).state, "linked");
    assert.match(contractStep(withC, [c]).meta, /Ceiling 6,000.00 NGN · committed 1,000.00 · remaining 5,000.00/);
    assert.equal(contractStep(withC, [{ ...c, state: "ENDED" }]).stateLabel, "Ended");
    assert.equal(contractStep(withC, undefined).state, "unknown");
  });
  test("order: waiting shows the approvals given; rejected is a gap", () => {
    assert.equal(orderStep({ ...order, status: "REQUESTED", approvals: [{ by: "x" }], approvals_needed: 2 }).state, "pending");
    assert.match(orderStep({ ...order, status: "REQUESTED", approvals: [{ by: "x" }], approvals_needed: 2 }).meta, /1 of 2 approvals given/);
    assert.equal(orderStep(order).state, "linked");
    assert.equal(orderStep({ ...order, status: "REJECTED" }).state, "missing");
  });
  test("delivery: none, partly and fully received; it says a person recorded it", () => {
    assert.equal(deliveryStep(order, []).state, "missing");
    const d = [{ order_id: "o1", ref: "DL-001", received_date: "2026-10-01" }];
    assert.equal(deliveryStep({ ...order, fulfilment: "PARTLY_RECEIVED" }, d).state, "pending");
    const full = deliveryStep({ ...order, fulfilment: "RECEIVED" }, d);
    assert.equal(full.state, "linked");
    assert.match(full.meta, /has not confirmed that anything arrived/);
    assert.equal(deliveryStep(order, undefined).state, "unknown");
  });
  test("invoice: the worst live invoice decides, and the server's flags are worded", () => {
    assert.equal(invoiceStep(order, []).state, "missing");
    assert.equal(invoiceStep(order, [inv("MATCHED")]).state, "pending");
    const ex = invoiceStep(order, [inv("MATCHED"), inv("EXCEPTION", { flags: ["PRICE_ABOVE_ORDER"] })]);
    assert.deepEqual([ex.state, ex.stateLabel], ["missing", "Exception, needs a decision"]);
    assert.match(ex.meta, /above the order price/);
    assert.equal(invoiceStep(order, [inv("APPROVED")]).state, "linked");
    assert.equal(invoiceStep(order, [inv("REJECTED")]).stateLabel, "Rejected");
    assert.equal(invoiceStep(order, [inv("REJECTED"), inv("APPROVED")]).state, "linked");
    assert.equal(invoiceStep(order, undefined).state, "unknown");
  });
  test("payment: not paid, partly, fully; it says ASAVEXA did not pay", () => {
    assert.equal(paymentStep(order, []).state, "missing");
    assert.equal(paymentStep(order, [inv("APPROVED")]).state, "missing");
    const paid = inv("PAID", { payment: { bank_reference: "BK-1", paid_date: "2026-10-02", treasury_ref: null } });
    const p = paymentStep(order, [paid]);
    assert.equal(p.state, "linked");
    assert.match(p.meta, /Bank reference BK-1/);
    assert.match(p.meta, /did not make the payment/);
    assert.equal(paymentStep(order, [paid, inv("APPROVED", { id: "z" })]).state, "pending");
  });
  test("review: none or latest; the average is the server's own text", () => {
    assert.equal(reviewStep(order, []).state, "missing");
    const r = reviewStep(order, [{ supplier_id: "s1", period: "2026-Q1", average: "3.5" }]);
    assert.equal(r.state, "linked");
    assert.match(r.title, /latest 2026-Q1, average 3\.5 of 5/);
    assert.equal(reviewStep(order, undefined).state, "unknown");
  });
});

describe("the whole trace", () => {
  test("seven steps in order; with nothing loaded all say Not checked, never clean", () => {
    const t = buildTrace({ order });
    assert.deepEqual(t.steps.map((s) => s.key), PROC_ORDER);
    assert.deepEqual(t.steps.filter((s) => s.key !== "contract" && s.key !== "order").map((s) => s.state), ["unknown", "unknown", "unknown", "unknown", "unknown"]);
    assert.equal(buildTrace({}), null);
  });
  test("the steps feed the rail untouched and the summary counts them", () => {
    const t = buildTrace({ order, suppliers: [sup], contracts: [], deliveries: [], invoices: [], reviews: [] });
    assert.equal(all(ProofRail({ id: "r", subject: "x", steps: t.steps, vocab: PROC_VOCAB }), (n) => n.props && n.props["data-stage"]).length, 7);   // already-built steps pass through
    const s = railSummary(t.steps);
    assert.equal(s.total, 7);
    assert.equal(s.linked, 2);   // supplier and order
    assert.equal(s.complete, false);
    assert.deepEqual(Object.keys(PROC_VOCAB), PROC_ORDER);
  });
  test("it does no arithmetic and no comparison of amounts or quantities", () => {
    const src = readFileSync(new URL("../src/lib/procTrace.js", import.meta.url), "utf8");
    assert.ok(!/parseFloat|Number\(|\.toFixed|Math\.|compareDecimals|addDecimals/.test(src));
  });
});

describe("the Trace tab", () => {
  const pc = (over = {}) => ({ tab: "trace", options: null, ov: null, suppliers: [sup], contracts: [], orders: [order], live: [], deliveries: [], invoices: [], reviews: [], released: [], orderFilter: "", sel: { supplier: null, order: null }, forms: {}, notes: {}, formError: null, busy: false, error: null, notice: null, traceId: null, ...over });
  const render = (p) => Procurement({ pc: p, role: "ACCOUNTANT", userId: "u9", loading: false, onRetry() {}, actions: { setTab() {}, setTrace() {}, traceOrder() {} } });
  test("the tab exists", () => assert.ok(TABS.some(([id]) => id === "trace")));
  test("before an order is chosen nothing is claimed", () => {
    const v = render(pc());
    assert.ok(byId(v, "pc-trace-empty"));
    assert.equal(byId(v, "pc-trace"), undefined);
  });
  test("once chosen it shows the match table, the exact total and the rail", () => {
    const v = render(pc({ traceId: "o1" }));
    assert.equal(byId(v, "pc-trace").props["data-sector"], "procurement");
    assert.match(text(byId(v, "pc-trace-total")), /NGN\s*1,000\.00/);
    assert.equal(all(byId(v, "pc-trace-match"), (n) => n.props && n.props["data-line"]).length, 1);
    assert.ok(byId(v, "pc-trace-rail"));
    assert.equal(all(byId(v, "pc-trace-rail"), (n) => n.props && n.props["data-stage"]).length, 7);
  });
  test("it offers no button that changes anything", () => {
    const v = render(pc({ traceId: "o1" }));
    assert.equal(all(byId(v, "pc-trace"), (n) => n.tag === "button").length, 0);
  });
  test("choosing an order calls the handler with its id", () => {
    let got = null;
    const v = Procurement({ pc: pc(), role: "ACCOUNTANT", userId: "u9", loading: false, onRetry() {}, actions: { setTab() {}, setTrace: (id) => { got = id; }, traceOrder() {} } });
    byId(v, "pc-trace-order").props.onChange({ target: { value: "o1" } });
    assert.equal(got, "o1");
  });
  test("a rail step can carry its own words without losing its shape", () => {
    const [s] = normaliseSteps({ supplier: { state: "missing", stateLabel: "Suspended", title: "x" } }, ["supplier"]);
    assert.deepEqual([s.state, s.stateLabel], ["missing", "Suspended"]);
  });
});
