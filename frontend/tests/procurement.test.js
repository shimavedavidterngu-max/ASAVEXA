import { test, describe } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { Procurement } from "../src/pages/Procurement.js";
import * as P from "../src/lib/procurement.js";
import { ApiClient } from "../src/api/client.js";
import { PERMISSIONS, can } from "../src/lib/permissions.js";
import { NAV_GROUPS } from "../src/lib/home.js";
import * as E from "../src/lib/entityConfig.js";

const text = (v) => JSON.stringify(v);
const noop = new Proxy({}, { get: () => () => {} });
const sup = (o = {}) => ({ id: "s1", ref: "SU-001", name: "Acme Supplies", category: "GOODS", country: "Nigeria", contact: "a@b.test", related_party: false, related_party_note: "", status: "PENDING", created_by: "u1", approved_spend: { NGN: "5200.00" },
  orders: 1, deliveries: 1, invoices: 1, needs_review: true, latest_review: null, history: [{ at: "2026-02-15T09:00", event: "REGISTERED", by: "u1", note: "" }], ...o });
const con = (o = {}) => ({ id: "c1", ref: "CT-001", supplier_id: "s1", supplier_name: "Acme Supplies", title: "Supply agreement", currency: "NGN", ceiling: "10000.00", start_date: "2026-01-01", end_date: "2026-12-31", status: "PENDING", created_by: "u1",
  committed: "0.00", remaining: "10000.00", state: "IN_FORCE", days_left: 319, expiring_soon: false, history: [], ...o });
const line = (o = {}) => ({ n: 1, description: "Laptops", qty: "10.000", unit_price: "500.00", total: "5000.00", received: "4.000", invoiced: "0.000", outstanding: "6.000", ...o });
const ord = (o = {}) => ({ id: "o1", ref: "PO-001", supplier_id: "s1", supplier_name: "Acme Supplies", contract_id: null, contract_ref: null, currency: "NGN", total: "5000.00", expected_date: "2026-02-28", purpose: "Office equipment", approvals_needed: 2,
  approvals: [{ by: "u3", at: "2026-02-15", note: "" }], status: "REQUESTED", requested_by: "u1", lines: [line()], fulfilment: null, overdue: false, history: [], deliveries: [], invoices: [], ...o });
const inv = (o = {}) => ({ id: "i1", ref: "IV-001", order_id: "o1", order_ref: "PO-001", supplier_id: "s1", supplier_name: "Acme Supplies", invoice_number: "INV-100", invoice_date: "2026-02-15", due_date: "2026-03-21", currency: "NGN", total: "5000.00",
  lines: [{ line: 1, description: "Laptops", qty: "10.000", unit_price: "500.00", total: "5000.00" }], flags: [], status: "MATCHED", override_note: null, payment: null, recorded_by: "u1", overdue: false, history: [], ...o });
const ovw = () => ({ counts: { suppliers: 2, contracts: 1, orders_open: 1, orders_waiting: 1, invoices_waiting: 1, invoices_unpaid: 0, invoices_paid: 0 }, attention: [{ kind: "INVOICE_EXCEPTIONS", text: "1 invoice(s) have a mismatch." }],
  limitations: ["ASAVEXA records what people type in."], policy: { tolerance_pct: "2", dual_limits: { DEFAULT: "10000.00" }, warning_days: 60, meaning: "An invoice price may be up to 2% above the order price." } });
const state = (o = {}) => ({ tab: "overview", options: { categories: ["GOODS", "SERVICES"], suppliers: [{ id: "s1", ref: "SU-001", name: "Acme" }], contracts: [{ id: "c1", ref: "CT-001", title: "T", supplier_id: "s1", currency: "NGN" }] },
  ov: ovw(), suppliers: [sup()], contracts: [con()], orders: [ord()], live: [ord({ status: "APPROVED" })], deliveries: [], invoices: [], reviews: [], released: [], orderFilter: "", sel: { supplier: null, order: null },
  forms: { ...JSON.parse(JSON.stringify(P.EMPTY)), policy: P.policyForm(ovw().policy) }, notes: {}, formError: null, busy: false, error: null, notice: null, ...o });
const page = (o = {}, role = "OWNER", me = "u9") => Procurement({ pc: state(o), role, userId: me, loading: false, onRetry() {}, actions: noop });

describe("permissions", () => {
  test("roles", () => {
    for (const r of ["OWNER", "MANAGER", "FINANCE_OFFICER"]) assert.ok(P.canPrepare(r) && P.canApprove(r), r);
    assert.ok(P.canPrepare("ACCOUNTANT") && !P.canApprove("ACCOUNTANT")); assert.ok(P.canApprove("APPROVER") && !P.canPrepare("APPROVER"));
    for (const r of ["ADMINISTRATOR", "REVIEWER", "AUDITOR", "EXTERNAL_AUDITOR", "READ_ONLY"]) assert.ok(!P.canPrepare(r) && !P.canApprove(r), r);
    assert.equal(PERMISSIONS.PROCURE_PREPARE, "procure:prepare"); assert.equal(PERMISSIONS.PROCURE_APPROVE, "procure:approve");
    for (const r of ["OWNER", "MANAGER", "FINANCE_OFFICER", "ACCOUNTANT", "APPROVER"]) assert.ok(can(r, PERMISSIONS.REPORTING_READ), r);
  });
});

describe("payload builders", () => {
  test("supplier", () => {
    assert.match(P.supplierPayload({ ...P.EMPTY.supplier, name: "x" }).problem, /name/);
    assert.match(P.supplierPayload({ ...P.EMPTY.supplier, name: "Acme", related: "yes", related_party_note: "short" }).problem, /10 characters/);
    assert.deepEqual(P.supplierPayload({ ...P.EMPTY.supplier, name: " Acme ", related: "no", related_party_note: "ignored" }).body, { name: "Acme", category: "GOODS", country: "", contact: "", tax_ref: "", related_party: false, related_party_note: "" });
    assert.equal(P.supplierPayload({ ...P.EMPTY.supplier, name: "Acme", related: "yes", related_party_note: "Cousin of the finance manager" }).body.related_party, true);
  });
  test("contract", () => {
    const ok = { supplier_id: "s1", title: "Supply", description: "", currency: "ngn", ceiling: "1,000.50", start_date: "2026-01-01", end_date: "2026-12-31" };
    assert.deepEqual(P.contractPayload(ok).body, { supplier_id: "s1", title: "Supply", description: "", currency: "NGN", ceiling: "1000.50", start_date: "2026-01-01", end_date: "2026-12-31" });
    for (const [k, v, re] of [["supplier_id", "", /supplier/i], ["title", "ab", /title/], ["currency", "N", /currency/], ["ceiling", "0", /more than zero/], ["ceiling", "1.234", /decimal/], ["start_date", "2026-02-30", /real date/], ["end_date", "2026-01-01", /after the start/]])
      assert.match(P.contractPayload({ ...ok, [k]: v }).problem, re, k);
  });
  test("order lines: untouched rows are ignored, half-filled rows are a problem", () => {
    const f = { supplier_id: "s1", contract_id: "", currency: "ngn", expected_date: "2026-02-28", purpose: "Office kit", lines: [{ description: "Laptops", qty: "10", unit_price: "500.00" }, { description: "", qty: "", unit_price: "" }] };
    assert.deepEqual(P.orderPayload(f).body, { supplier_id: "s1", currency: "NGN", expected_date: "2026-02-28", purpose: "Office kit", lines: [{ description: "Laptops", qty: "10", unit_price: "500.00" }] });
    assert.equal(P.orderPayload({ ...f, contract_id: "c1" }).body.contract_id, "c1");
    assert.match(P.orderPayload({ ...f, lines: [{ description: "", qty: "", unit_price: "" }] }).problem, /at least one line/);
    assert.match(P.orderPayload({ ...f, lines: [{ description: "Laptops", qty: "", unit_price: "5" }] }).problem, /Line 1: the quantity/);
    assert.match(P.orderPayload({ ...f, lines: [{ description: "Laptops", qty: "1.0001", unit_price: "5" }] }).problem, /3 decimal/);
    assert.match(P.orderPayload({ ...f, lines: [{ description: "Laptops", qty: "1", unit_price: "0" }] }).problem, /more than zero/);
    assert.match(P.orderPayload({ ...f, lines: [{ description: "ab", qty: "1", unit_price: "1" }] }).problem, /describe/);
    assert.match(P.orderPayload({ ...f, purpose: "no" }).problem, /what the order is for/);
    assert.match(P.orderPayload({ ...f, expected_date: "soon" }).problem, /real date/);
  });
  test("delivery and invoice quantities come from the per-line boxes", () => {
    assert.deepEqual(P.qtyLines({ 2: "3", 1: " 4 ", 3: "" }), [{ line: 1, qty: "4" }, { line: 2, qty: "3" }]);
    assert.deepEqual(P.deliveryPayload({ order_id: "o1", received_date: "2026-02-15", note: " ok ", qtys: { 1: "4" } }).body, { received_date: "2026-02-15", note: "ok", lines: [{ line: 1, qty: "4" }] });
    assert.match(P.deliveryPayload({ order_id: "", received_date: "2026-02-15", qtys: { 1: "4" } }).problem, /order/); assert.match(P.deliveryPayload({ order_id: "o1", received_date: "x", qtys: { 1: "4" } }).problem, /real date/);
    assert.match(P.deliveryPayload({ order_id: "o1", received_date: "2026-02-15", qtys: {} }).problem, /at least one line/); assert.match(P.deliveryPayload({ order_id: "o1", received_date: "2026-02-15", qtys: { 1: "0" } }).problem, /more than zero/);
    const f = { order_id: "o1", invoice_number: "INV-1", invoice_date: "2026-02-15", due_date: "2026-03-15", currency: "ngn", qtys: { 1: "4" }, prices: { 1: "500.00" } };
    assert.deepEqual(P.invoicePayload(f).body, { invoice_number: "INV-1", invoice_date: "2026-02-15", due_date: "2026-03-15", currency: "NGN", lines: [{ line: 1, qty: "4", unit_price: "500.00" }] });
    assert.equal("currency" in P.invoicePayload({ ...f, currency: "" }).body, false);
    assert.match(P.invoicePayload({ ...f, invoice_number: " " }).problem, /invoice number/); assert.match(P.invoicePayload({ ...f, prices: { 1: "" } }).problem, /unit price/); assert.match(P.invoicePayload({ ...f, currency: "N" }).problem, /currency/);
  });
  test("payment record: a linked Treasury payment, or a date and the bank's reference", () => {
    assert.deepEqual(P.paidPayload({ treasury_payment_id: "t1", paid_date: "ignored" }).body, { treasury_payment_id: "t1" });
    assert.deepEqual(P.paidPayload({ paid_date: "2026-02-15", bank_reference: " TRX-1 " }).body, { paid_date: "2026-02-15", bank_reference: "TRX-1" });
    assert.match(P.paidPayload({ paid_date: "2026-02-15", bank_reference: "x" }).problem, /bank/); assert.match(P.paidPayload({ paid_date: "", bank_reference: "TRX-1" }).problem, /real date/);
  });
  test("review scores are whole numbers 1 to 5 and a low one needs a comment", () => {
    const f = { supplier_id: "s1", period: "2026-Q1", delivery: "4", quality: "5", price: "3", service: "4", comment: "" };
    assert.deepEqual(P.reviewPayload(f).body, { period: "2026-Q1", scores: { delivery: 4, quality: 5, price: 3, service: 4 }, comment: "" });
    for (const v of ["0", "6", "x", "", "4.5"]) assert.match(P.reviewPayload({ ...f, price: v }).problem, /Price must be a whole number from 1 to 5/, v);
    assert.match(P.reviewPayload({ ...f, quality: "2" }).problem, /comment/); assert.equal(P.reviewPayload({ ...f, quality: "2", comment: "Three laptops arrived damaged" }).body.scores.quality, 2);
    assert.match(P.reviewPayload({ ...f, period: "x" }).problem, /period/); assert.match(P.reviewPayload({ ...f, supplier_id: "" }).problem, /supplier/i);
  });
  test("policy", () => {
    assert.deepEqual(P.policyForm({ tolerance_pct: "2", dual_limits: { DEFAULT: "10000.00", USD: "50.00" }, warning_days: 60 }), { tolerance_pct: "2", dual_limits: "DEFAULT=10000.00, USD=50.00", warning_days: "60" });
    assert.deepEqual(P.policyPayload({ tolerance_pct: "2.5", dual_limits: "DEFAULT=2,000, usd=5", warning_days: "30" }).body, { tolerance_pct: "2.5", dual_limits: { DEFAULT: "2000", USD: "5" }, warning_days: 30 });
    for (const [k, v, re] of [["tolerance_pct", "21", /0 to 20/], ["tolerance_pct", "1.25", /0 to 20/], ["tolerance_pct", "x", /0 to 20/], ["warning_days", "0", /1 to 365/], ["warning_days", "366", /1 to 365/], ["dual_limits", "oops", /Approval limits/]])
      assert.match(P.policyPayload({ tolerance_pct: "2", dual_limits: "", warning_days: "60", [k]: v }).problem, re, k);
  });
});

describe("which buttons a person can see", () => {
  test("supplier", () => {
    assert.deepEqual(P.supplierMoves(sup(), "u2", "APPROVER"), ["approve"]); assert.deepEqual(P.supplierMoves(sup(), "u1", "OWNER"), []); assert.deepEqual(P.supplierMoves(sup(), "u2", "ACCOUNTANT"), []);
    assert.deepEqual(P.supplierMoves(sup({ status: "ACTIVE" }), "u2", "APPROVER"), ["suspend"]);
    const s = sup({ status: "SUSPENDED", history: [{ event: "SUSPENDED", by: "u2" }] }); assert.deepEqual(P.supplierMoves(s, "u2", "APPROVER"), []); assert.deepEqual(P.supplierMoves(s, "u3", "APPROVER"), ["reinstate"]);
  });
  test("contract", () => {
    assert.deepEqual(P.contractMoves(con(), "u2", "APPROVER"), ["approve"]); assert.deepEqual(P.contractMoves(con(), "u1", "OWNER"), []); assert.deepEqual(P.contractMoves(con({ status: "ACTIVE" }), "u1", "OWNER"), ["terminate"]);
  });
  test("order: approve once, never your own, cancel only your own", () => {
    assert.deepEqual(P.orderMoves(ord(), "u2", "APPROVER"), ["approve", "reject"]); assert.deepEqual(P.orderMoves(ord(), "u3", "APPROVER"), ["reject"]);          // u3 already approved
    assert.deepEqual(P.orderMoves(ord(), "u1", "OWNER"), ["cancel"]); assert.deepEqual(P.orderMoves(ord(), "u2", "ACCOUNTANT"), []);
    assert.deepEqual(P.orderMoves(ord({ status: "APPROVED" }), "u1", "OWNER"), ["cancel", "close"]); assert.deepEqual(P.orderMoves(ord({ status: "APPROVED" }), "u2", "ACCOUNTANT"), ["close"]); assert.deepEqual(P.orderMoves(ord({ status: "CLOSED" }), "u1", "OWNER"), []);
  });
  test("invoice: a currency mismatch can only be rejected; recording and paying need prepare", () => {
    assert.deepEqual(P.invoiceMoves(inv(), "u2", "APPROVER"), ["approve", "reject"]); assert.deepEqual(P.invoiceMoves(inv(), "u1", "OWNER"), []);
    assert.deepEqual(P.invoiceMoves(inv({ status: "EXCEPTION", flags: ["CURRENCY_DIFFERS"] }), "u2", "APPROVER"), ["reject"]);
    assert.deepEqual(P.invoiceMoves(inv({ status: "APPROVED" }), "u2", "ACCOUNTANT"), ["paid"]); assert.deepEqual(P.invoiceMoves(inv({ status: "APPROVED" }), "u2", "APPROVER"), []);
    assert.equal(P.overrideNeeded(inv({ flags: ["NOT_YET_RECEIVED"] })), true); assert.equal(P.overrideNeeded(inv()), false); assert.equal(P.overrideNeeded(inv({ flags: ["CURRENCY_DIFFERS"] })), false);
  });
  test("a Treasury payment is offered only if it is released and matches", () => {
    const i = inv({ status: "APPROVED" }), mk = (o) => ({ id: "t1", ref: "PR-001", status: "RELEASED", currency: "NGN", amount: "5000.00", payee: " acme supplies ", ...o });
    assert.deepEqual(P.linkablePayments([mk(), mk({ id: "t2", status: "APPROVED" }), mk({ id: "t3", amount: "5000.01" }), mk({ id: "t4", currency: "USD" }), mk({ id: "t5", payee: "Other" })], i).map((p) => p.id), ["t1"]);
  });
});

describe("prefilled forms", () => {
  test("a delivery starts with what is still to come; an invoice with what was received and not yet invoiced, exactly", () => {
    const o = ord({ lines: [line({ n: 1, outstanding: "6.000" }), line({ n: 2, outstanding: "0.000", received: "10.000", invoiced: "0.300", unit_price: "20.00" }), line({ n: 3, received: "0.300", invoiced: "0.100", outstanding: "0.000", unit_price: "1.00" })] });
    assert.deepEqual(P.prefillDelivery(o).qtys, { 1: "6.000" });
    const f = P.prefillInvoice(o); assert.deepEqual(f.qtys, { 1: "4", 2: "9.7", 3: "0.2" }); assert.deepEqual(f.prices, { 1: "500.00", 2: "20.00", 3: "1.00" }); assert.equal(f.currency, "NGN");
    assert.deepEqual(P.prefillDelivery(null).qtys, {});
  });
  test("money is shown as text without rounding", () => { assert.equal(P.fmt("1234567.50", "NGN"), "1,234,567.50 NGN"); assert.equal(P.fmt("0.10"), "0.10"); assert.equal(P.fmt(null), "—"); });
});

describe("page", () => {
  test("banner says it records and checks, and a second person approves", () => {
    const t = text(page()); assert.match(t, /does not buy anything/); assert.match(t, /someone other than the person who created/); assert.match(t, /pc-banner/);
  });
  test("overview shows attention, counts, policy and limits; only an approver can edit the policy", () => {
    const t = text(page({}, "APPROVER")); assert.match(t, /INVOICE_EXCEPTIONS/); assert.match(t, /Open purchase orders: 1/); assert.match(t, /pc-policy-save/); assert.match(t, /pc-limits/);
    assert.doesNotMatch(text(page({}, "ACCOUNTANT")), /pc-policy-save/); assert.match(text(page({}, "ACCOUNTANT")), /Only an approver can change/);
  });
  test("suppliers: approve button for another approver, none for the creator, register form only for preparers", () => {
    const a = text(page({ tab: "suppliers", sel: { supplier: sup(), order: null } }, "APPROVER", "u2")); assert.match(a, /pc-sup-SU-001-approve/); assert.doesNotMatch(a, /pc-sup-save/);
    const b = text(page({ tab: "suppliers", sel: { supplier: sup(), order: null } }, "OWNER", "u1")); assert.doesNotMatch(b, /pc-sup-SU-001-approve/); assert.match(b, /pc-sup-save/);
    assert.match(text(page({ tab: "suppliers", sel: { supplier: sup({ related_party: true, related_party_note: "Cousin" }), order: null } }, "APPROVER", "u2")), /pc-sup-related-note/);
    assert.match(text(page({ tab: "suppliers", sel: { supplier: sup(), order: null } }, "OWNER", "u1")), /no review yet/);
  });
  test("a related-party note box appears only when the answer is yes", () => {
    assert.doesNotMatch(text(page({ tab: "suppliers" })), /pc-sup-relnote/);
    const s = state({ tab: "suppliers" }); s.forms.supplier.related = "yes"; assert.match(text(Procurement({ pc: s, role: "OWNER", userId: "u1", loading: false, onRetry() {}, actions: noop })), /pc-sup-relnote/);
  });
  test("orders show lines with received and invoiced, approvals given, and the right buttons", () => {
    const t = text(page({ tab: "orders" }, "APPROVER", "u2")); assert.match(t, /1 of 2 approvals given/); assert.match(t, /pc-po-PO-001-approve/); assert.match(t, /pc-po-PO-001-reject/); assert.doesNotMatch(t, /pc-po-save/); assert.match(t, /Still to come/);
    const u = text(page({ tab: "orders" }, "OWNER", "u1")); assert.match(u, /pc-po-PO-001-cancel/); assert.doesNotMatch(u, /pc-po-PO-001-approve/); assert.match(u, /pc-po-save/); assert.match(u, /pc-po-line-1-desc/);
  });
  test("order chain appears when opened", () => {
    const o = ord({ status: "APPROVED", deliveries: [{ ref: "DL-001", received_date: "2026-02-15", received_by: "u3", lines: [{ line: 1, qty: "4.000" }] }], invoices: [inv()] });
    const t = text(page({ tab: "orders", orders: [o], sel: { supplier: null, order: o } }, "OWNER", "u1")); assert.match(t, /DL-001 received 2026-02-15 by u3/); assert.match(t, /IV-001 \(INV-100\)/);
  });
  test("contracts show ceiling, committed and the ending warning", () => {
    const t = text(page({ tab: "contracts", contracts: [con({ status: "ACTIVE", expiring_soon: true, days_left: 20 })] }, "APPROVER", "u2")); assert.match(t, /Ends in 20 days/); assert.match(t, /ceiling 10,000.00 NGN/); assert.match(t, /pc-con-CT-001-terminate/);
  });
  test("receipts: lines for the chosen order, flags explained, exception needs a note, payment can link a released payment", () => {
    const o = ord({ status: "APPROVED", lines: [line()] }), s = state({ tab: "receipts", live: [o], invoices: [inv({ status: "EXCEPTION", flags: ["NOT_YET_RECEIVED"] })] });
    s.forms.delivery = P.prefillDelivery(o); s.forms.invoice = P.prefillInvoice(o);
    const t = text(Procurement({ pc: s, role: "OWNER", userId: "u9", loading: false, onRetry() {}, actions: noop })); for (const id of ["pc-dl-qty-1", "pc-dl-date", "pc-dl-save", "pc-iv-number", "pc-iv-qty-1", "pc-iv-price-1", "pc-iv-save", "pc-iv-IV-001-approve", "pc-iv-IV-001-reject"]) assert.ok(t.includes(id), id);
    assert.match(t, /More is invoiced than has been recorded as received/); assert.match(t, /say why it is acceptable/);
    const own = text(Procurement({ pc: s, role: "OWNER", userId: "u1", loading: false, onRetry() {}, actions: noop })); assert.doesNotMatch(own, /pc-iv-IV-001-approve/); assert.match(own, /Waiting for a different approver to decide/);
    const paid = state({ tab: "receipts", live: [o], invoices: [inv({ status: "APPROVED" })], released: [{ id: "t1", ref: "PR-001", status: "RELEASED", currency: "NGN", amount: "5000.00", payee: "Acme Supplies", released_date: "2026-02-15" }] });
    const p = text(Procurement({ pc: paid, role: "ACCOUNTANT", userId: "u9", loading: false, onRetry() {}, actions: noop })); assert.match(p, /pc-iv-link-IV-001/); assert.match(p, /pc-iv-paid-IV-001/); assert.match(p, /pc-iv-paid-date-IV-001/);
  });
  test("a currency difference cannot be approved from the page", () => {
    const s = state({ tab: "receipts", invoices: [inv({ status: "EXCEPTION", flags: ["CURRENCY_DIFFERS"] })] }), t = text(Procurement({ pc: s, role: "APPROVER", userId: "u2", loading: false, onRetry() {}, actions: noop }));
    assert.doesNotMatch(t, /pc-iv-IV-001-approve/); assert.match(t, /pc-iv-IV-001-reject/); assert.match(t, /cannot be approved/);
  });
  test("reviews show scores and the low-score flag; form only for preparers", () => {
    const r = { id: "r1", ref: "SR-001", supplier_name: "Acme", period: "2026-Q1", scores: { delivery: 4, quality: 2, price: 3, service: 4 }, average: "3.3", low: true, comment: "Damaged" };
    const t = text(page({ tab: "reviews", reviews: [r] }, "OWNER")); assert.match(t, /Low score/); assert.match(t, /pc-rv-save/); assert.match(t, /not a rating issued by ASAVEXA/); assert.doesNotMatch(text(page({ tab: "reviews", reviews: [r] }, "APPROVER")), /pc-rv-save/);
  });
  test("errors, notices and loading", () => {
    assert.match(text(page({ error: "Boom" })), /Boom/); assert.match(text(page({ notice: "Saved." })), /pc-notice/);
    assert.match(text(Procurement({ pc: state(), role: "OWNER", userId: "u1", loading: true, onRetry() {}, actions: noop })), /Loading|loading/i);
    const s = state({ tab: "suppliers", formError: { form: "supplier", text: "Give the supplier a name." } }); assert.match(text(Procurement({ pc: s, role: "OWNER", userId: "u1", loading: false, onRetry() {}, actions: noop })), /supplier-problem/);
  });
  test("every tab renders for every role without throwing", () => {
    for (const role of ["OWNER", "ADMINISTRATOR", "ACCOUNTANT", "FINANCE_OFFICER", "APPROVER", "REVIEWER", "MANAGER", "AUDITOR", "EXTERNAL_AUDITOR", "READ_ONLY"]) for (const [tab] of P.TABS)
      assert.doesNotThrow(() => page({ tab, sel: { supplier: sup(), order: ord() }, invoices: [inv(), inv({ id: "i2", ref: "IV-002", status: "APPROVED" })], deliveries: [{ id: "d1", ref: "DL-001", order_ref: "PO-001", supplier_name: "A", received_date: "2026-02-15", received_by: "u3", lines: [{ line: 1, qty: "1.000" }] }] }, role, "u2"), `${role}/${tab}`);
  });
});

describe("wiring", () => {
  test("client calls the right paths and verbs", async () => {
    const calls = []; const c = new ApiClient("http://x"); c._request = async (m, p, o) => { calls.push([m, p, o && o.body, o && o.query]); return {}; };
    await c.pcOverview(); await c.setPcPolicy({ warning_days: 3 }); await c.registerPcSupplier({}); await c.pcSupplierStep("s/1", "approve", "ok"); await c.draftPcContract({}); await c.pcContractStep("c1", "terminate", "why"); await c.pcOrders("APPROVED"); await c.raisePcOrder({});
    await c.pcOrderStep("o1", "reject", "no"); await c.addPcDelivery("o1", {}); await c.addPcInvoice("o1", {}); await c.pcInvoiceStep("i1", "approve", "fine"); await c.payPcInvoice("i1", {}); await c.addPcReview("s1", {}); await c.pcReviews(); await c.pcDeliveries(); await c.pcInvoices();
    assert.deepEqual(calls.map((x) => x.slice(0, 2)), [["GET", "/procurement/overview"], ["PUT", "/procurement/policy"], ["POST", "/procurement/suppliers"], ["POST", "/procurement/suppliers/s%2F1/approve"], ["POST", "/procurement/contracts"],
      ["POST", "/procurement/contracts/c1/terminate"], ["GET", "/procurement/orders"], ["POST", "/procurement/orders"], ["POST", "/procurement/orders/o1/reject"], ["POST", "/procurement/orders/o1/deliveries"], ["POST", "/procurement/orders/o1/invoices"],
      ["POST", "/procurement/invoices/i1/approve"], ["POST", "/procurement/invoices/i1/paid"], ["POST", "/procurement/suppliers/s1/reviews"], ["GET", "/procurement/reviews"], ["GET", "/procurement/deliveries"], ["GET", "/procurement/invoices"]]);
    assert.deepEqual(calls[6][3], { status: "APPROVED" }); assert.deepEqual(calls[5][2], { note: "why" });
  });
  test("the page is in the menu, in the workspaces group, behind reporting:read, searchable, and can be hidden by organisation set-up", () => {
    assert.ok(NAV_GROUPS.find((g) => g.id === "workspaces").paths.includes("/procurement"));
    const app = fs.readFileSync(new URL("../src/app.js", import.meta.url), "utf8");
    assert.match(app, /path: "\/procurement", label: "Procurement", permission: PERMISSIONS\.REPORTING_READ/); assert.match(app, /path: "\/procurement", name: "procurement"/); assert.match(app, /renderProcurementPage\(authState\)/);
    assert.match(app, /uiState\.pc = null; loadedOnce\.delete\("pcLoading"\)/);
    assert.equal(E.WORKSPACE_PATHS.procurement, "/procurement");
    assert.deepEqual(E.filterNavByWorkspaces([{ path: "/procurement" }, { path: "/cyber" }], ["cyber"]).map((i) => i.path), ["/cyber"]);
  });
  test("the page uses only the shared client and never builds a URL or arithmetic on money", () => {
    const src = fs.readFileSync(new URL("../src/pages/Procurement.js", import.meta.url), "utf8") + fs.readFileSync(new URL("../src/lib/procurement.js", import.meta.url), "utf8");
    assert.doesNotMatch(src, /fetch\(|XMLHttpRequest|parseFloat|toFixed|Number\(l\.(unit_price|total)\)/);
  });
});
