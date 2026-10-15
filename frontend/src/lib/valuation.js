import { PERMISSIONS, ROLE_PERMISSIONS } from "./permissions.js";
import { fmt, isRealDate, noteProblem, words } from "./treasury.js";

/**
 * Valuation helpers (workpapers worked out from typed inputs; no market data is read and no opinion of value is given). No DOM, no network.
 * The server enforces every rule and does all the arithmetic. These check input early, word things, and hide buttons that could not work.
 */
export { fmt, isRealDate, noteProblem, words };
const has = (role, perm) => !!(ROLE_PERMISSIONS[role] && ROLE_PERMISSIONS[role].includes(perm));
export const canRead = (role) => has(role, PERMISSIONS.AUDIT_READ);
export const canPrepare = (role) => has(role, PERMISSIONS.VAL_PREPARE);
export const canApprove = (role) => has(role, PERMISSIONS.VAL_APPROVE);

export const TABS = [["overview", "Overview"], ["cases", "Valuations"]];
export const KIND_TEXT = { BUSINESS: "Business", SHARES: "Shares", PROPERTY: "Property", EQUIPMENT: "Equipment", INTANGIBLE: "Intangible asset", OTHER: "Other" };
export const PURPOSE_TEXT = { TRANSACTION: "Transaction", REPORTING: "Reporting", TAX: "Tax", LENDING: "Lending", INTERNAL: "Internal use", OTHER: "Other" };
export const BASIS_TEXT = { MARKET_VALUE: "Market value", FAIR_VALUE: "Fair value", INVESTMENT_VALUE: "Investment value", LIQUIDATION_VALUE: "Liquidation value", OTHER: "Other" };
export const METHOD_TEXT = { MULTIPLE: "Multiple of a metric", DCF: "Discounted cash flows", ASSET_BASED: "Assets less liabilities" };
export const STATUS = {
  DRAFT: { tone: "neutral", label: "Draft" }, SUBMITTED: { tone: "warn", label: "Waiting for review" }, APPROVED: { tone: "pass", label: "Approved" }, RETURNED: { tone: "warn", label: "Returned" }, WITHDRAWN: { tone: "neutral", label: "Withdrawn" },
  ACTIVE: { tone: "pass", label: "In use" }, REMOVED: { tone: "neutral", label: "Removed" },
};
export const statusOf = (s) => STATUS[s] || { tone: "neutral", label: s ? words(s) : "—" };
export const ATTENTION_TONE = { CASES_TO_REVIEW: "info", CASES_RETURNED: "warn", DUE_FOR_REVIEW: "warn" };
export const who = (id, me) => (!id ? "—" : id === me ? "You" : String(id).slice(0, 8));

const clean = (v) => String(v == null ? "" : v).trim();
const first = (...p) => p.find(Boolean) || "";
const dateProblem = (v, what) => (isRealDate(clean(v)) ? "" : `${what} must be a real date written YYYY-MM-DD.`);
const textProblem = (v, what, min) => (clean(v).length >= min ? "" : `${what} needs at least ${min} characters.`);
const nonZero = (t) => /[1-9]/.test(t);
const amt = (v) => clean(v).replace(/,/g, "");
const AMOUNT = /^\d{1,12}(\.\d{1,2})?$/;
const amountProblem = (v, what, zeroOk) => { const t = amt(v); if (!AMOUNT.test(t)) return `${what} must be an amount such as 1500.00 (at most two decimals).`; return zeroOk || nonZero(t) ? "" : `${what} must be more than zero.`; };
const PCT = /^\d{1,3}(\.\d{1,2})?$/;
const pctProblem = (v, what, zeroOk) => { const t = clean(v); if (!PCT.test(t) || Number(t) > 100) return `${what} must be a percentage such as 12.5 (at most two decimals, not more than 100).`; return zeroOk || nonZero(t) ? "" : `${what} must be more than zero.`; };
const MULT = /^\d{1,6}(\.\d{1,4})?$/;
const hundredths = (v) => { const [w, f = ""] = clean(v).split("."); return Number(w) * 100 + Number((f + "00").slice(0, 2)); };

export const EMPTY = {
  case: { subject: "", subject_kind: "BUSINESS", purpose: "TRANSACTION", basis: "MARKET_VALUE", valuation_date: "", currency: "" },
  method: { kind: "MULTIPLE", label: "", weight: "", metric: "", multiple: "", net_debt: "", cash_flows: "", discount_rate: "", terminal_growth: "", total_assets: "", total_liabilities: "" },
  submit: { rationale: "" },
};

export function casePayload(f) {
  const cur = clean(f.currency).toUpperCase();
  const p = first(textProblem(f.subject, "The subject", 3), dateProblem(f.valuation_date, "The valuation date"), /^[A-Z]{3}$/.test(cur) ? "" : "The currency must be a three-letter code such as NGN.");
  if (p) return { problem: p };
  return { body: { subject: clean(f.subject), subject_kind: f.subject_kind, purpose: f.purpose, basis: f.basis, valuation_date: clean(f.valuation_date), currency: cur } };
}
/** Cash flows are typed one per line or separated by spaces. */
export const flowList = (v) => clean(v).split(/\s+/).filter(Boolean);

export function methodPayload(f) {
  const w = clean(f.weight), common = first(textProblem(f.label, "The label", 2), /^\d{1,3}$/.test(w) && Number(w) <= 100 ? "" : "The weight is a whole number of percent from 0 to 100.");
  const b = { kind: f.kind, label: clean(f.label), weight: Number(w) };
  let p = "";
  if (f.kind === "MULTIPLE") {
    p = first(amountProblem(f.metric, "The metric"), MULT.test(clean(f.multiple)) && nonZero(clean(f.multiple)) ? "" : "The multiple must be a number such as 6.5 (at most four decimals) and more than zero.", clean(f.net_debt) ? amountProblem(f.net_debt, "The net debt", true) : "");
    Object.assign(b, { metric: amt(f.metric), multiple: clean(f.multiple), ...(clean(f.net_debt) ? { net_debt: amt(f.net_debt) } : {}) });
  } else if (f.kind === "DCF") {
    const flows = flowList(f.cash_flows);
    p = first(flows.length >= 1 && flows.length <= 15 ? "" : "Give 1 to 15 yearly cash flows, separated by spaces or new lines.", first(...flows.map((x, i) => amountProblem(x, `Cash flow ${i + 1}`, true))), flows.some((x) => AMOUNT.test(amt(x)) && nonZero(amt(x))) ? "" : "At least one cash flow must be more than zero.",
      pctProblem(f.discount_rate, "The discount rate"), clean(f.terminal_growth) ? pctProblem(f.terminal_growth, "The terminal growth", true) : "",
      clean(f.terminal_growth) && PCT.test(clean(f.terminal_growth)) && PCT.test(clean(f.discount_rate)) && hundredths(f.terminal_growth) >= hundredths(f.discount_rate) ? "The terminal growth must be less than the discount rate." : "", clean(f.net_debt) ? amountProblem(f.net_debt, "The net debt", true) : "");
    Object.assign(b, { cash_flows: flows.map(amt), discount_rate: clean(f.discount_rate), ...(clean(f.terminal_growth) ? { terminal_growth: clean(f.terminal_growth) } : {}), ...(clean(f.net_debt) ? { net_debt: amt(f.net_debt) } : {}) });
  } else {
    p = first(amountProblem(f.total_assets, "The total assets"), amountProblem(f.total_liabilities, "The total liabilities", true));
    Object.assign(b, { total_assets: amt(f.total_assets), total_liabilities: amt(f.total_liabilities) });
  }
  const problem = first(common, p);
  return problem ? { problem } : { body: b };
}
export const submitPayload = (f) => (clean(f.rationale).length >= 20 ? { body: { rationale: clean(f.rationale) } } : { problem: "The rationale needs at least 20 characters." });
export const policyForm = (p) => ({ review_days: String(p.review_days) });
export function policyPayload(f) {
  const t = clean(f.review_days);
  if (!(/^\d{2,4}$/.test(t) && Number(t) >= 30 && Number(t) <= 1095)) return { problem: "The days before a valuation is due for review is a whole number from 30 to 1095." };
  return { body: { review_days: Number(t) } };
}
export const minNote = { remove: 5, return: 10, withdraw: 10 };
export const weightText = (c) => (c.weight_total === 100 ? "The weights add up to 100 percent." : `The weights add up to ${c.weight_total} percent. They must add up to 100 before you can submit.`);

// ---- who sees which button ----
export const canEdit = (c, role) => canPrepare(role) && (c.status === "DRAFT" || c.status === "RETURNED");
export const canSubmit = (c, role) => canEdit(c, role) && c.active_methods > 0 && c.weight_total === 100;
export const canDecide = (c, role, me) => canApprove(role) && c.status === "SUBMITTED" && c.submitted_by !== me;
export const ownWorkText = (what) => `You ${what}, so a different person must decide it.`;
