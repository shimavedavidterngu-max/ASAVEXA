import { fmt, statusOf, approvalText, words, FLAG_TEXT } from "./procurement.js";

/**
 * Procurement Trace: the whole chain behind ONE purchase order, read from records the Procurement page has already loaded.
 *   supplier -> contract -> purchase order (approvals) -> delivery -> invoice (three-way match) -> payment -> supplier review
 * Honest by construction:
 *  - It only restates what the server recorded (statuses, flags, quantities as text, totals). It adds, compares and recalculates nothing.
 *  - A missing link is shown as missing; a step the page could not look up is shown as "Not checked" (undefined), never as clean.
 *  - It records and checks. It does not buy, pay or confirm that goods arrived, and the trace says what each step means.
 * Shape of a step: { key, state: linked|missing|pending|unknown, stateLabel, title, meta }. The coarse state sets the SHAPE; stateLabel is the words.
 */
export const PROC_VOCAB = { supplier: "Supplier", contract: "Contract", order: "Purchase order", delivery: "Delivery", invoice: "Invoice (three-way match)", payment: "Payment record", review: "Supplier review" };
export const PROC_ORDER = ["supplier", "contract", "order", "delivery", "invoice", "payment", "review"];

const step = (key, state, stateLabel, title, meta) => ({ key, state, stateLabel: stateLabel || null, title: title || null, meta: meta || null });
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
const by = (list, pred) => (Array.isArray(list) ? list.filter(pred) : undefined);

export function supplierStep(order, suppliers) {
  const list = by(suppliers, (s) => s.id === order.supplier_id);
  if (list === undefined) return step("supplier", "unknown");
  const s = list[0];
  if (!s) return step("supplier", "missing", "Not found", order.supplier_name || null, "The supplier record for this order could not be found.");
  const meta = s.related_party ? `Connected party: ${s.related_party_note}` : null;
  if (s.status === "ACTIVE") return step("supplier", "linked", "Approved", `${s.ref} ${s.name}`, meta);
  if (s.status === "PENDING") return step("supplier", "pending", "Waiting for approval", `${s.ref} ${s.name}`, meta);
  return step("supplier", "missing", statusOf(s.status).label, `${s.ref} ${s.name}`, meta);
}

export function contractStep(order, contracts) {
  if (!order.contract_id) return step("contract", "missing", "No contract", null, "This order was not raised under a contract.");
  const list = by(contracts, (c) => c.id === order.contract_id);
  if (list === undefined) return step("contract", "unknown");
  const c = list[0];
  if (!c) return step("contract", "missing", "Not found", order.contract_ref || null, "The contract record for this order could not be found.");
  const money = `Ceiling ${fmt(c.ceiling, c.currency)} · committed ${fmt(c.committed)} · remaining ${fmt(c.remaining)}`;
  const title = `${c.ref} ${c.title}`;
  if (c.status === "ACTIVE" && c.state === "ENDED") return step("contract", "missing", "Ended", title, money);
  if (c.status === "ACTIVE") return step("contract", "linked", statusOf(c.state || c.status).label, title, money);
  if (c.status === "PENDING") return step("contract", "pending", "Waiting for approval", title, money);
  return step("contract", "missing", statusOf(c.status).label, title, money);
}

export function orderStep(order) {
  const title = `${order.ref} · ${fmt(order.total, order.currency)}`, meta = `Raised by ${order.requested_by}. ${order.purpose}`;
  if (order.status === "REQUESTED") return step("order", "pending", "Waiting for approval", title, `${approvalText(order)}. ${meta}`);
  if (order.status === "APPROVED" || order.status === "CLOSED") return step("order", "linked", statusOf(order.status).label, title, meta);
  return step("order", "missing", statusOf(order.status).label, title, order.closed_note ? `${order.closed_note}. ${meta}` : meta);
}

export function deliveryStep(order, deliveries) {
  const list = by(deliveries, (d) => d.order_id === order.id);
  if (list === undefined) return step("delivery", "unknown");
  if (!list.length) return step("delivery", "missing", "Nothing received yet", null, "No delivery has been recorded against this order.");
  const title = plural(list.length, "delivery recorded", "deliveries recorded");
  const meta = `Recorded by a person; ASAVEXA has not confirmed that anything arrived. Last ${list[list.length - 1].ref}, received ${list[list.length - 1].received_date}.`;
  return step("delivery", order.fulfilment === "RECEIVED" ? "linked" : "pending", statusOf(order.fulfilment).label, title, meta);
}

export function invoiceStep(order, invoices) {
  const list = by(invoices, (i) => i.order_id === order.id);
  if (list === undefined) return step("invoice", "unknown");
  if (!list.length) return step("invoice", "missing", "No invoice yet", null, "No invoice has been recorded against this order.");
  const live = list.filter((i) => i.status !== "REJECTED");
  const flags = [...new Set(live.flatMap((i) => i.flags || []))];
  const meta = flags.length ? flags.map((f) => FLAG_TEXT[f] || words(f)).join(" ") : null;
  const title = plural(list.length, "invoice recorded", "invoices recorded");
  if (!live.length) return step("invoice", "missing", "Rejected", title, "Every invoice for this order was rejected.");
  if (live.some((i) => i.status === "EXCEPTION")) return step("invoice", "missing", statusOf("EXCEPTION").label, title, meta);
  if (live.some((i) => i.status === "MATCHED")) return step("invoice", "pending", statusOf("MATCHED").label, title, meta);
  return step("invoice", "linked", "Approved", title, meta);
}

export function paymentStep(order, invoices) {
  const list = by(invoices, (i) => i.order_id === order.id && i.status !== "REJECTED");
  if (list === undefined) return step("payment", "unknown");
  if (!list.length) return step("payment", "missing", "Nothing to pay yet", null, "There is no live invoice to pay.");
  const paid = list.filter((i) => i.status === "PAID");
  const lastPaid = paid.length ? paid[paid.length - 1] : null;
  const meta = lastPaid && lastPaid.payment ? `Bank reference ${lastPaid.payment.bank_reference}, paid ${lastPaid.payment.paid_date}${lastPaid.payment.treasury_ref ? `, linked to Treasury payment ${lastPaid.payment.treasury_ref}` : ""}. ASAVEXA records this; it did not make the payment.` : "ASAVEXA records a payment; it does not make one.";
  if (!paid.length) return step("payment", "missing", "Not recorded as paid", null, meta);
  return step("payment", paid.length === list.length ? "linked" : "pending", paid.length === list.length ? "Recorded as paid" : "Partly paid", `${paid.length} of ${list.length} recorded as paid`, meta);
}

export function reviewStep(order, reviews) {
  const list = by(reviews, (r) => r.supplier_id === order.supplier_id);
  if (list === undefined) return step("review", "unknown");
  if (!list.length) return step("review", "missing", "No review yet", null, "No review of this supplier has been recorded.");
  const latest = list[0];
  return step("review", "linked", "Reviewed", `${plural(list.length, "review", "reviews")}; latest ${latest.period}, average ${latest.average} of 5`, "A review is a person's judgement, not a rating issued by ASAVEXA.");
}

/** Everything for one order. Any list passed as undefined (not loaded) makes the steps that need it say "Not checked". */
export function buildTrace({ order, suppliers, contracts, deliveries, invoices, reviews }) {
  if (!order) return null;
  return {
    order,
    steps: [supplierStep(order, suppliers), contractStep(order, contracts), orderStep(order), deliveryStep(order, deliveries), invoiceStep(order, invoices), paymentStep(order, invoices), reviewStep(order, reviews)],
    invoices: (invoices || []).filter((i) => i.order_id === order.id),
    deliveries: (deliveries || []).filter((d) => d.order_id === order.id),
  };
}
