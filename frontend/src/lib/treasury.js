import { PERMISSIONS, ROLE_PERMISSIONS } from "./permissions.js";

/**
 * Treasury helpers (records and evidence; no bank connection, no money moves). No DOM, no network.
 * The server decides everything that matters. These check input early, word things, and hide buttons that could not work.
 * Amounts are handled as TEXT. Nothing here adds, subtracts or converts money; the server does all arithmetic with exact decimals.
 */
const has = (role, perm) => !!(ROLE_PERMISSIONS[role] && ROLE_PERMISSIONS[role].includes(perm));
export const canPrepare = (role) => has(role, PERMISSIONS.TREASURY_PREPARE);
export const canApprove = (role) => has(role, PERMISSIONS.TREASURY_APPROVE);

export const TABS = [["overview", "Overview"], ["accounts", "Cash accounts"], ["forecast", "Forecast and cash flows"], ["payments", "Payments"], ["covenants", "Covenants"]];
export const WEEK_CHOICES = [4, 8, 13, 26];

export const STATUS = {
  RECORDED: { tone: "warn", label: "Recorded, not confirmed" }, CONFIRMED: { tone: "pass", label: "Confirmed" }, ACTIVE: { tone: "info", label: "Open" }, CLOSED: { tone: "neutral", label: "Closed" },
  OPEN: { tone: "info", label: "Expected" }, REALISED: { tone: "pass", label: "Happened" }, CANCELLED: { tone: "neutral", label: "Cancelled" },
  REQUESTED: { tone: "warn", label: "Waiting for approval" }, APPROVED: { tone: "info", label: "Approved, not yet released" }, REJECTED: { tone: "fail", label: "Rejected" }, RELEASED: { tone: "pass", label: "Released" },
  MET: { tone: "pass", label: "Met" }, WATCH: { tone: "warn", label: "Close to the limit" }, BREACHED: { tone: "fail", label: "Breached" }, NOT_TESTED: { tone: "neutral", label: "Not tested yet" }, RETIRED: { tone: "neutral", label: "Retired" },
};
export const statusOf = (s) => STATUS[s] || { tone: "neutral", label: s ? String(s).replace(/_/g, " ").toLowerCase().replace(/^./, (c) => c.toUpperCase()) : "—" };
export const label = (s) => statusOf(s).label;
export const words = (s) => String(s == null ? "" : s).replace(/_/g, " ").toLowerCase().replace(/^./, (c) => c.toUpperCase());
export const FLAG_TEXT = {
  NEW_PAYEE: "No earlier payment to this payee has been released.",
  POSSIBLE_DUPLICATE: "Another payment to this payee for the same amount is close in date.",
  BALANCE_BELOW_AMOUNT: "The latest recorded balance of the account is lower than this payment, or no balance is recorded.",
  NO_EVIDENCE: "No supporting document is attached.",
};
export const ATTENTION_TONE = { SHORTFALL: "fail", COVENANT_BREACH: "fail", PAYMENTS_WAITING: "warn", PAYMENTS_READY: "info", NO_BALANCE: "warn", STALE_BALANCE: "warn", COVENANT_WATCH: "warn", COVENANT_TEST_OVERDUE: "warn", FLOWS_OVERDUE: "warn", COVENANT_BREACH_ACKNOWLEDGED: "neutral" };

/** 1234567.5 given as "1234567.50" -> "1,234,567.50". Text only, so no rounding and no floating-point surprises. */
export function fmt(amount, currency) {
  if (amount == null || amount === "") return "—";
  const m = /^(-?)(\d+)(\.\d+)?$/.exec(String(amount));
  if (!m) return String(amount);
  return `${m[1]}${m[2].replace(/\B(?=(\d{3})+(?!\d))/g, ",")}${m[3] || ""}${currency ? ` ${currency}` : ""}`;
}

export const isRealDate = (s) => {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(s || "").trim());
  if (!m) return false;
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
  return d.getUTCFullYear() === +m[1] && d.getUTCMonth() === +m[2] - 1 && d.getUTCDate() === +m[3];
};

const clean = (v) => String(v == null ? "" : v).trim();
const plain = (v) => clean(v).replace(/,/g, "");
/** Returns a problem sentence or "". `places` is the most decimals allowed. */
export function amountProblem(v, what, { positive = false, places = 2, allowNegative = false } = {}) {
  const t = plain(v);
  if (!t) return `${what} is required.`;
  const re = new RegExp(`^-?\\d{1,13}(\\.\\d{1,${places}})?$`);
  if (!re.test(t)) return `${what} must be a number with at most ${places} decimal places.`;
  if (t.startsWith("-") && !allowNegative) return `${what} cannot be negative.`;
  if (positive && !(/[1-9]/.test(t))) return `${what} must be more than zero.`;
  return "";
}
export const noteProblem = (v, what, min = 5) => (clean(v).length >= min ? "" : `${what} is required (at least ${min} characters).`);
const first = (...p) => p.find(Boolean) || "";
const dateProblem = (v, what) => (isRealDate(clean(v)) ? "" : `${what} must be a real date written YYYY-MM-DD.`);
const body = (b, ...problems) => { const p = first(...problems); return p ? { problem: p } : { body: b }; };

export const EMPTY = {
  account: { name: "", bank_name: "", currency: "", last4: "", purpose: "" },
  balance: { as_at: "", amount: "", source: "" },
  flow: { direction: "IN", flow_date: "", amount: "", currency: "", account_id: "", category: "CUSTOMER_RECEIPT", certainty: "EXPECTED", description: "" },
  payment: { account_id: "", payee: "", amount: "", due_date: "", reason: "", invoice_ref: "", flow_id: "", evidence_id: "" },
  covenant: { name: "", lender: "", description: "", comparator: "MIN", threshold: "", unit: "RATIO", currency: "", frequency: "QUARTERLY", watch_pct: "10", effective_from: "" },
  result: { period_end: "", value: "", source: "", note: "" },
};

export const accountPayload = (f) => body({ name: clean(f.name), bank_name: clean(f.bank_name), currency: clean(f.currency).toUpperCase(), last4: clean(f.last4), purpose: clean(f.purpose) },
  clean(f.name).length < 2 ? "Give the account a name." : "", /^[A-Za-z]{3}$/.test(clean(f.currency)) ? "" : "The currency is a three-letter code such as NGN or USD.",
  /^[A-Za-z0-9]{0,4}$/.test(clean(f.last4)) ? "" : "Give at most the last four letters or digits of the account number. Never the whole number.");

export const balancePayload = (f) => body({ as_at: clean(f.as_at), amount: plain(f.amount), source: clean(f.source) },
  dateProblem(f.as_at, "The balance date"), amountProblem(f.amount, "The balance", { allowNegative: true }), clean(f.source).length < 3 ? "Say where the balance came from, for example the statement." : "");

export const flowPayload = (f) => body({ direction: f.direction, flow_date: clean(f.flow_date), amount: plain(f.amount), category: f.category, certainty: f.certainty, description: clean(f.description),
  ...(f.account_id ? { account_id: f.account_id } : { currency: clean(f.currency).toUpperCase() }) },
  dateProblem(f.flow_date, "The expected date"), amountProblem(f.amount, "The amount", { positive: true }), clean(f.description).length < 3 ? "Describe the cash flow." : "",
  f.account_id || /^[A-Za-z]{3}$/.test(clean(f.currency)) ? "" : "Choose an account or give a three-letter currency code.");

export const paymentPayload = (f) => body({ account_id: f.account_id, payee: clean(f.payee), amount: plain(f.amount), due_date: clean(f.due_date), reason: clean(f.reason), invoice_ref: clean(f.invoice_ref),
  ...(f.flow_id ? { flow_id: f.flow_id } : {}), evidence_ids: f.evidence_id ? [f.evidence_id] : [] },
  f.account_id ? "" : "Choose the account the payment will leave.", clean(f.payee).length < 2 ? "Name the payee." : "", amountProblem(f.amount, "The amount", { positive: true }), dateProblem(f.due_date, "The due date"),
  clean(f.reason).length < 5 ? "Say why the payment is being made." : "");

export const releasePayload = (f) => body({ released_date: clean(f.released_date), bank_reference: clean(f.bank_reference) },
  dateProblem(f.released_date, "The date it was released"), clean(f.bank_reference).length < 3 ? "Enter the bank's own reference for the payment." : "");

export const covenantPayload = (f) => body({ name: clean(f.name), lender: clean(f.lender), description: clean(f.description), comparator: f.comparator, threshold: plain(f.threshold), unit: f.unit,
  ...(f.unit === "AMOUNT" ? { currency: clean(f.currency).toUpperCase() } : {}), frequency: f.frequency, watch_pct: Number(f.watch_pct), effective_from: clean(f.effective_from) },
  clean(f.name).length < 3 ? "Name the covenant." : "", clean(f.description).length < 3 ? "Say what it measures." : "", amountProblem(f.threshold, "The threshold", { places: 4, allowNegative: true }),
  f.unit === "AMOUNT" && !/^[A-Za-z]{3}$/.test(clean(f.currency)) ? "An amount covenant needs a three-letter currency code." : "",
  /^\d{1,2}$/.test(clean(f.watch_pct)) && Number(f.watch_pct) <= 50 ? "" : "The warning margin is a whole number from 0 to 50.", dateProblem(f.effective_from, "The date it starts"));

export const resultPayload = (f) => body({ period_end: clean(f.period_end), value: plain(f.value), source: clean(f.source), note: clean(f.note) },
  dateProblem(f.period_end, "The period end"), amountProblem(f.value, "The measured value", { places: 4, allowNegative: true }), clean(f.source).length < 3 ? "Say where the figure came from." : "");

/** "NGN=5000, USD=100" -> { NGN: "5000", USD: "100" }, or a problem. */
export function parseMap(text) {
  const out = {};
  for (const part of clean(text).split(/[;\n]+|,(?=\s*[A-Za-z])/).map((x) => x.trim()).filter(Boolean)) {
    const m = /^([A-Za-z]{3}|default)\s*[=:]\s*([\d,]+(\.\d{1,2})?)$/i.exec(part);
    if (!m) return { problem: `"${part}" should look like NGN=5000.` };
    out[m[1].toUpperCase()] = m[2].replace(/,/g, "");
  }
  return { map: out };
}
export const mapText = (m) => Object.entries(m || {}).map(([k, v]) => `${k}=${v}`).join(", ");
export const policyForm = (p) => ({ minimum_cash: mapText(p && p.minimum_cash), dual_limits: mapText(p && p.dual_limits), stale_days: String((p && p.stale_days) || 7) });
export function policyPayload(f) {
  const mc = parseMap(f.minimum_cash), dl = parseMap(f.dual_limits);
  if (mc.problem) return { problem: `Minimum cash: ${mc.problem}` };
  if (dl.problem) return { problem: `Approval limits: ${dl.problem}` };
  if (!/^\d{1,2}$/.test(clean(f.stale_days)) || Number(f.stale_days) < 1 || Number(f.stale_days) > 90) return { problem: "The balance age limit is a whole number of days from 1 to 90." };
  return { body: { minimum_cash: mc.map, dual_limits: dl.map, stale_days: Number(f.stale_days) } };
}

/** Which buttons a person can sensibly see on a payment. The server decides again. */
export function paymentMoves(p, me, role) {
  const open = p.status === "REQUESTED" || p.status === "APPROVED", mine = p.requested_by === me, out = [];
  if (p.status === "REQUESTED" && canApprove(role) && !mine && !(p.approvals || []).some((a) => a.by === me)) out.push("approve");
  if (open && canApprove(role) && !mine) out.push("reject");
  if (open && canPrepare(role) && mine) out.push("cancel");
  if (p.status === "APPROVED" && canPrepare(role) && !mine) out.push("release");
  return out;
}
export const MOVE_TEXT = { approve: "Approve", reject: "Reject", cancel: "Cancel my request", release: "Record as released" };
export const approvalText = (p) => (p.status === "REQUESTED" ? `${(p.approvals || []).length} of ${p.approvals_needed} approval${p.approvals_needed > 1 ? "s" : ""} given` : "");
export const canConfirmBalance = (b, me, role) => !!b && b.status === "RECORDED" && canApprove(role) && b.recorded_by !== me;
export const canAcknowledge = (r, me, role) => !!r && r.status === "BREACHED" && !r.acknowledged_by && canApprove(role) && r.recorded_by !== me;
export const ackText = (r) => (r.acknowledged_by ? `Acknowledged${r.waiver_obtained ? " (waiver or amendment obtained)" : " (no waiver)"}: ${r.acknowledgement}` : "");

export const headroomText = (r) => (r.headroom_pct == null ? "No percentage (threshold is zero)" : `${r.headroom_pct}% ${Number(r.headroom_pct) < 0 ? "beyond" : "of room before"} the limit`);
export const COMPARATOR_TEXT = { MIN: "Must stay at or above", MAX: "Must stay at or below" };
export const UNIT_TEXT = { RATIO: "Ratio", PERCENT: "Percent", AMOUNT: "Amount of money" };
export const CATEGORY_TEXT = (c) => words(c);

/** Cash-flow list, newest decision first for open items by date. */
export const openFirst = (flows) => [...(flows || [])].sort((a, b) => (a.status === "OPEN") === (b.status === "OPEN") ? String(a.flow_date).localeCompare(String(b.flow_date)) : a.status === "OPEN" ? -1 : 1);
