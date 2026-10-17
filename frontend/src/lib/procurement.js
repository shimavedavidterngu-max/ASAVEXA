import { PERMISSIONS, ROLE_PERMISSIONS } from "./permissions.js";
import { fmt, isRealDate, amountProblem, noteProblem, words, parseMap, mapText } from "./treasury.js";

/**
 * Procurement helpers (records and checks; nothing is bought, paid or verified by ASAVEXA). No DOM, no network.
 * The server decides everything that matters. These check input early, word things, and hide buttons that could not work.
 * Amounts and quantities are handled as TEXT. Nothing here adds, multiplies or compares money; the server does all arithmetic with exact decimals.
 */
export { fmt, isRealDate, amountProblem, noteProblem, words };
const has = (role, perm) => !!(ROLE_PERMISSIONS[role] && ROLE_PERMISSIONS[role].includes(perm));
export const canPrepare = (role) => has(role, PERMISSIONS.PROCURE_PREPARE);
export const canApprove = (role) => has(role, PERMISSIONS.PROCURE_APPROVE);

export const TABS = [["overview", "Overview"], ["suppliers", "Suppliers"], ["contracts", "Contracts"], ["orders", "Purchase orders"], ["trace", "Trace an order"], ["receipts", "Deliveries and invoices"], ["reviews", "Supplier reviews"]];
export const SCORE_LABEL = { delivery: "Delivery", quality: "Quality", price: "Price", service: "Service" };

export const STATUS = {
  PENDING: { tone: "warn", label: "Waiting for approval" }, ACTIVE: { tone: "pass", label: "Approved" }, SUSPENDED: { tone: "fail", label: "Suspended" }, TERMINATED: { tone: "neutral", label: "Terminated" },
  REQUESTED: { tone: "warn", label: "Waiting for approval" }, APPROVED: { tone: "info", label: "Approved" }, REJECTED: { tone: "fail", label: "Rejected" }, CANCELLED: { tone: "neutral", label: "Cancelled" }, CLOSED: { tone: "neutral", label: "Closed" },
  MATCHED: { tone: "pass", label: "Matched, waiting for approval" }, EXCEPTION: { tone: "fail", label: "Exception, needs a decision" }, PAID: { tone: "pass", label: "Paid" },
  NOT_RECEIVED: { tone: "neutral", label: "Nothing received yet" }, PARTLY_RECEIVED: { tone: "warn", label: "Partly received" }, RECEIVED: { tone: "pass", label: "Fully received" },
  IN_FORCE: { tone: "pass", label: "In force" }, NOT_STARTED: { tone: "neutral", label: "Not started" }, ENDED: { tone: "neutral", label: "Ended" },
};
export const statusOf = (s) => STATUS[s] || { tone: "neutral", label: s ? words(s) : "—" };
export const FLAG_TEXT = {
  CURRENCY_DIFFERS: "The invoice is in a different currency from the order. It cannot be approved; reject it and ask for a corrected one.",
  NOT_YET_RECEIVED: "More is invoiced than has been recorded as received.",
  PRICE_ABOVE_ORDER: "A unit price is above the order price by more than the allowed tolerance.",
};
export const ATTENTION_TONE = { SUPPLIERS_PENDING: "warn", CONTRACTS_PENDING: "warn", CONTRACT_ENDING: "warn", CONTRACT_EXPIRED: "fail", CONTRACT_CEILING: "warn", ORDERS_WAITING: "warn", DELIVERIES_LATE: "warn", INVOICE_EXCEPTIONS: "fail", INVOICES_WAITING: "info", INVOICES_UNPAID: "warn", REVIEWS_MISSING: "info" };

const clean = (v) => String(v == null ? "" : v).trim();
const plain = (v) => clean(v).replace(/,/g, "");
const first = (...p) => p.find(Boolean) || "";
const body = (b, ...problems) => { const p = first(...problems); return p ? { problem: p } : { body: b }; };
const dateProblem = (v, what) => (isRealDate(clean(v)) ? "" : `${what} must be a real date written YYYY-MM-DD.`);
const qtyProblem = (v, what) => { const t = plain(v); if (!t) return `${what} is required.`; if (!/^\d{1,9}(\.\d{1,3})?$/.test(t)) return `${what} must be a number with at most 3 decimal places.`; return /[1-9]/.test(t) ? "" : `${what} must be more than zero.`; };
const currencyProblem = (v) => (/^[A-Za-z]{3}$/.test(clean(v)) ? "" : "The currency is a three-letter code such as NGN or USD.");

export const EMPTY = {
  supplier: { name: "", category: "GOODS", country: "", contact: "", tax_ref: "", related: "no", related_party_note: "" },
  contract: { supplier_id: "", title: "", description: "", currency: "", ceiling: "", start_date: "", end_date: "" },
  order: { supplier_id: "", contract_id: "", currency: "", expected_date: "", purpose: "", lines: [{ description: "", qty: "", unit_price: "" }, { description: "", qty: "", unit_price: "" }] },
  delivery: { order_id: "", received_date: "", note: "", qtys: {} },
  invoice: { order_id: "", invoice_number: "", invoice_date: "", due_date: "", currency: "", qtys: {}, prices: {} },
  review: { supplier_id: "", period: "", delivery: "", quality: "", price: "", service: "", comment: "" },
};

export const supplierPayload = (f) => body({ name: clean(f.name), category: f.category, country: clean(f.country), contact: clean(f.contact), tax_ref: clean(f.tax_ref), related_party: f.related === "yes", related_party_note: f.related === "yes" ? clean(f.related_party_note) : "" },
  clean(f.name).length < 2 ? "Give the supplier a name." : "", f.related === "yes" && clean(f.related_party_note).length < 10 ? "Describe the connection in at least 10 characters, for example who is connected and how." : "");

export const contractPayload = (f) => body({ supplier_id: f.supplier_id, title: clean(f.title), description: clean(f.description), currency: clean(f.currency).toUpperCase(), ceiling: plain(f.ceiling), start_date: clean(f.start_date), end_date: clean(f.end_date) },
  f.supplier_id ? "" : "Choose the supplier.", clean(f.title).length < 3 ? "Give the contract a title." : "", currencyProblem(f.currency), amountProblem(f.ceiling, "The ceiling", { positive: true }),
  dateProblem(f.start_date, "The start date"), dateProblem(f.end_date, "The end date"), isRealDate(clean(f.start_date)) && isRealDate(clean(f.end_date)) && clean(f.end_date) <= clean(f.start_date) ? "The end date must be after the start date." : "");

/** Only rows the person has touched are sent; a half-filled row is a problem, not silently dropped. */
export function orderLines(lines) {
  const rows = (lines || []).map((l, i) => ({ i, d: clean(l.description), q: clean(l.qty), p: clean(l.unit_price) })).filter((r) => r.d || r.q || r.p);
  return rows.map((r, n) => ({ n: n + 1, description: r.d, qty: plain(r.q), unit_price: plain(r.p), row: r.i }));
}
export function orderPayload(f) {
  const rows = orderLines(f.lines);
  let problem = first(f.supplier_id ? "" : "Choose the supplier.", currencyProblem(f.currency), dateProblem(f.expected_date, "The expected delivery date"), clean(f.purpose).length < 5 ? "Say what the order is for." : "", rows.length ? "" : "Add at least one line.");
  for (const r of rows) problem = problem || first(r.description.length < 3 ? `Line ${r.n}: describe what is being bought.` : "", qtyProblem(r.qty, `Line ${r.n}: the quantity`), amountProblem(r.unit_price, `Line ${r.n}: the unit price`, { positive: true }));
  if (problem) return { problem };
  return { body: { supplier_id: f.supplier_id, ...(f.contract_id ? { contract_id: f.contract_id } : {}), currency: clean(f.currency).toUpperCase(), expected_date: clean(f.expected_date), purpose: clean(f.purpose), lines: rows.map((r) => ({ description: r.description, qty: r.qty, unit_price: r.unit_price })) } };
}

/** Quantities typed against the lines of an order: { 1: "4", 2: "" } -> [{line:1, qty:"4"}]. */
export const qtyLines = (qtys) => Object.entries(qtys || {}).filter(([, v]) => clean(v)).map(([n, v]) => ({ line: Number(n), qty: plain(v) })).sort((a, b) => a.line - b.line);
export function deliveryPayload(f) {
  const lines = qtyLines(f.qtys);
  let problem = first(f.order_id ? "" : "Choose the order.", dateProblem(f.received_date, "The date received"), lines.length ? "" : "Enter the quantity received for at least one line.");
  for (const l of lines) problem = problem || qtyProblem(l.qty, `Line ${l.line}: the quantity`);
  return problem ? { problem } : { body: { received_date: clean(f.received_date), note: clean(f.note), lines } };
}
export function invoicePayload(f) {
  const lines = qtyLines(f.qtys).map((l) => ({ ...l, unit_price: plain((f.prices || {})[l.line]) }));
  let problem = first(f.order_id ? "" : "Choose the order.", clean(f.invoice_number).length < 1 ? "Enter the supplier's invoice number." : "", dateProblem(f.invoice_date, "The invoice date"), dateProblem(f.due_date, "The due date"),
    clean(f.currency) ? currencyProblem(f.currency) : "", lines.length ? "" : "Enter the quantity invoiced for at least one line.");
  for (const l of lines) problem = problem || first(qtyProblem(l.qty, `Line ${l.line}: the quantity`), amountProblem(l.unit_price, `Line ${l.line}: the unit price`, { positive: true }));
  return problem ? { problem } : { body: { invoice_number: clean(f.invoice_number), invoice_date: clean(f.invoice_date), due_date: clean(f.due_date), ...(clean(f.currency) ? { currency: clean(f.currency).toUpperCase() } : {}), lines } };
}
export function paidPayload(f) {
  if (f.treasury_payment_id) return { body: { treasury_payment_id: f.treasury_payment_id } };
  return body({ paid_date: clean(f.paid_date), bank_reference: clean(f.bank_reference) }, dateProblem(f.paid_date, "The date paid"), clean(f.bank_reference).length < 3 ? "Enter the bank's own reference, or link a released Treasury payment." : "");
}
export function reviewPayload(f) {
  const scores = {};
  for (const k of Object.keys(SCORE_LABEL)) {
    const v = clean(f[k]);
    if (!/^[1-5]$/.test(v)) return { problem: `${SCORE_LABEL[k]} must be a whole number from 1 to 5.` };
    scores[k] = Number(v);
  }
  const low = Object.values(scores).some((v) => v <= 2);
  return body({ period: clean(f.period), scores, comment: clean(f.comment) }, f.supplier_id ? "" : "Choose the supplier.", clean(f.period).length < 3 ? "Name the period, for example 2026-Q1." : "",
    low && clean(f.comment).length < 10 ? "A score of 1 or 2 needs a comment of at least 10 characters saying why." : "");
}

export const policyForm = (p) => ({ tolerance_pct: String((p && p.tolerance_pct) || "2"), dual_limits: mapText(p && p.dual_limits), warning_days: String((p && p.warning_days) || 60) });
export function policyPayload(f) {
  const dl = parseMap(f.dual_limits);
  if (dl.problem) return { problem: `Approval limits: ${dl.problem}` };
  if (!/^\d{1,2}(\.\d)?$/.test(clean(f.tolerance_pct)) || Number(f.tolerance_pct) > 20) return { problem: "The price tolerance is a percentage from 0 to 20, with at most one decimal place." };
  if (!/^\d{1,3}$/.test(clean(f.warning_days)) || Number(f.warning_days) < 1 || Number(f.warning_days) > 365) return { problem: "The contract warning period is a whole number of days from 1 to 365." };
  return { body: { tolerance_pct: clean(f.tolerance_pct), dual_limits: dl.map, warning_days: Number(f.warning_days) } };
}

const lastBy = (history, event) => { const e = [...(history || [])].reverse().find((x) => x.event === event); return e ? e.by : null; };
/** Which buttons a person can sensibly see. The server decides again. */
export function supplierMoves(s, me, role) {
  const out = [];
  if (s.status === "PENDING" && canApprove(role) && s.created_by !== me) out.push("approve");
  if (s.status === "ACTIVE" && canApprove(role)) out.push("suspend");
  if (s.status === "SUSPENDED" && canApprove(role) && lastBy(s.history, "SUSPENDED") !== me) out.push("reinstate");
  return out;
}
export function contractMoves(c, me, role) {
  const out = [];
  if (c.status === "PENDING" && canApprove(role) && c.created_by !== me) out.push("approve");
  if (c.status === "ACTIVE" && canApprove(role)) out.push("terminate");
  return out;
}
export function orderMoves(o, me, role) {
  const out = [], mine = o.requested_by === me;
  if (o.status === "REQUESTED" && canApprove(role) && !mine && !(o.approvals || []).some((a) => a.by === me)) out.push("approve");
  if (o.status === "REQUESTED" && canApprove(role) && !mine) out.push("reject");
  if ((o.status === "REQUESTED" || o.status === "APPROVED") && canPrepare(role) && mine) out.push("cancel");
  if (o.status === "APPROVED" && canPrepare(role)) out.push("close");
  return out;
}
export function invoiceMoves(i, me, role) {
  const out = [];
  if ((i.status === "MATCHED" || i.status === "EXCEPTION") && canApprove(role) && i.recorded_by !== me) { if (!(i.flags || []).includes("CURRENCY_DIFFERS")) out.push("approve"); out.push("reject"); }
  if (i.status === "APPROVED" && canPrepare(role)) out.push("paid");
  return out;
}
export const MOVE_TEXT = { approve: "Approve", reject: "Reject", cancel: "Cancel my order", close: "Close order", suspend: "Suspend", reinstate: "Reinstate", terminate: "Terminate", paid: "Record as paid" };
export const needsNote = { reject: 5, cancel: 5, close: 5, suspend: 5, reinstate: 5, terminate: 5 };
export const approvalText = (o) => (o.status === "REQUESTED" ? `${(o.approvals || []).length} of ${o.approvals_needed} approval${o.approvals_needed > 1 ? "s" : ""} given` : "");
export const overrideNeeded = (i) => !!(i && (i.flags || []).length && !(i.flags || []).includes("CURRENCY_DIFFERS"));

/** Payments the person could link: released in Treasury, same currency and payee name as the invoice's supplier, and the exact same amount. */
export const linkablePayments = (payments, inv) => (payments || []).filter((p) => p.status === "RELEASED" && p.currency === inv.currency && p.amount === inv.total && String(p.payee).trim().toLowerCase() === String(inv.supplier_name).trim().toLowerCase());
export const prefillDelivery = (order) => ({ ...EMPTY.delivery, order_id: order ? order.id : "", qtys: Object.fromEntries(((order && order.lines) || []).filter((l) => Number(l.outstanding) > 0).map((l) => [l.n, l.outstanding])) });
/** Quantities have at most 3 decimals, so they are compared as whole thousandths: no floating-point error. */
const milli = (v) => { const m = /^(\d+)(?:\.(\d{1,3}))?$/.exec(String(v == null ? "0" : v)); return m ? Number(m[1]) * 1000 + Number(((m[2] || "") + "000").slice(0, 3)) : 0; };
const fromMilli = (n) => `${Math.floor(n / 1000)}${n % 1000 ? "." + String(n % 1000).padStart(3, "0").replace(/0+$/, "") : ""}`;
export const prefillInvoice = (order) => {
  const lines = (order && order.lines) || [];
  return { ...EMPTY.invoice, order_id: order ? order.id : "", currency: order ? order.currency : "",
    qtys: Object.fromEntries(lines.filter((l) => milli(l.received) > milli(l.invoiced)).map((l) => [l.n, fromMilli(milli(l.received) - milli(l.invoiced))])),
    prices: Object.fromEntries(lines.map((l) => [l.n, l.unit_price])) };
};
export const stars = (n) => `${n} of 5`;
