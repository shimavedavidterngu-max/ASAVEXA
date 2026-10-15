import { PERMISSIONS, ROLE_PERMISSIONS } from "./permissions.js";
import { fmt, isRealDate, noteProblem, words } from "./treasury.js";

/**
 * Payroll and workforce cost helpers (pay lines are typed in and added up; no tax or statutory amount is calculated and nobody is paid). No DOM, no network.
 * The server enforces every rule and does all the arithmetic. These check input early, word things, and hide buttons that could not work.
 */
export { fmt, isRealDate, noteProblem, words };
const has = (role, perm) => !!(ROLE_PERMISSIONS[role] && ROLE_PERMISSIONS[role].includes(perm));
export const canRead = (role) => has(role, PERMISSIONS.AUDIT_READ);
export const canPrepare = (role) => has(role, PERMISSIONS.PAY_PREPARE);
export const canApprove = (role) => has(role, PERMISSIONS.PAY_APPROVE);

export const TABS = [["overview", "Overview"], ["runs", "Payroll runs"]];
export const STATUS = {
  DRAFT: { tone: "neutral", label: "Draft" }, SUBMITTED: { tone: "warn", label: "Waiting for review" }, APPROVED: { tone: "pass", label: "Approved" }, RETURNED: { tone: "warn", label: "Returned" }, WITHDRAWN: { tone: "neutral", label: "Withdrawn" },
  ACTIVE: { tone: "pass", label: "In use" }, REMOVED: { tone: "neutral", label: "Removed" },
};
export const statusOf = (s) => STATUS[s] || { tone: "neutral", label: s ? words(s) : "—" };
export const ATTENTION_TONE = { RUNS_TO_REVIEW: "info", RUNS_RETURNED: "warn", OVERLAPPING_PAY: "warn", LINES_ABOVE_LIMIT: "warn" };
export const who = (id, me) => (!id ? "—" : id === me ? "You" : String(id).slice(0, 8));

const clean = (v) => String(v == null ? "" : v).trim();
const first = (...p) => p.find(Boolean) || "";
const dateProblem = (v, what) => (isRealDate(clean(v)) ? "" : `${what} must be a real date written YYYY-MM-DD.`);
const textProblem = (v, what, min) => (clean(v).length >= min ? "" : `${what} needs at least ${min} characters.`);
const nonZero = (t) => /[1-9]/.test(t);
const amt = (v) => clean(v).replace(/,/g, "");
const AMOUNT = /^\d{1,12}(\.\d{1,2})?$/;
const amountProblem = (v, what, zeroOk) => {
  const t = clean(v);
  if (t.includes(",") && !/^\d{1,3}(,\d{3})+(\.\d+)?$/.test(t)) return `${what} must be an amount such as 1500.00 (commas only between groups of three digits).`;
  if (!AMOUNT.test(amt(v))) return `${what} must be an amount such as 1500.00 (at most two decimals).`;
  return zeroOk || nonZero(amt(v)) ? "" : `${what} must be more than zero.`;
};
const cents = (v) => { const [w, f = ""] = amt(v).split("."); return Number(w) * 100 + Number((f + "00").slice(0, 2)); };

export const EMPTY = {
  run: { label: "", period_start: "", period_end: "", currency: "" },
  line: { staff_ref: "", department: "", base_pay: "", allowances: "", employer_contributions: "", deductions: "" },
  submit: { note: "" },
};

export function runPayload(f) {
  const cur = clean(f.currency).toUpperCase();
  const p = first(textProblem(f.label, "The label", 3), dateProblem(f.period_start, "The start of the pay period"), dateProblem(f.period_end, "The end of the pay period"),
    isRealDate(clean(f.period_start)) && isRealDate(clean(f.period_end)) && clean(f.period_end) < clean(f.period_start) ? "The pay period cannot end before it starts." : "", /^[A-Z]{3}$/.test(cur) ? "" : "The currency must be a three-letter code such as NGN.");
  if (p) return { problem: p };
  return { body: { label: clean(f.label), period_start: clean(f.period_start), period_end: clean(f.period_end), currency: cur } };
}
/** Deductions are typed one per line as "label: amount". */
export function parseDeductions(v) {
  const out = [];
  for (const raw of clean(v).split(/\n/).map((x) => x.trim()).filter(Boolean)) {
    const i = raw.lastIndexOf(":");
    if (i < 1) return { problem: `Write each deduction as "label: amount", for example "Pension: 22400.04". Check: ${raw}` };
    const label = raw.slice(0, i).trim(), a = raw.slice(i + 1).trim();
    const p = first(textProblem(label, "The label of a deduction", 2), amountProblem(a, `The amount of the deduction "${label}"`));
    if (p) return { problem: p };
    out.push({ label, amount: amt(a) });
  }
  return out.length > 8 ? { problem: "At most 8 deductions per line." } : { list: out };
}
export function linePayload(f) {
  const d = parseDeductions(f.deductions);
  const p = first(textProblem(f.staff_ref, "The staff reference", 2), textProblem(f.department, "The department", 2), amountProblem(f.base_pay, "The base pay"), clean(f.allowances) ? amountProblem(f.allowances, "The allowances", true) : "",
    clean(f.employer_contributions) ? amountProblem(f.employer_contributions, "The employer contributions", true) : "", d.problem || "");
  if (p) return { problem: p };
  const gross = (AMOUNT.test(amt(f.base_pay)) ? cents(f.base_pay) : 0) + (clean(f.allowances) ? cents(f.allowances) : 0);
  const ded = d.list.reduce((s, x) => s + cents(x.amount), 0);
  if (ded > gross) return { problem: "The deductions cannot be more than the gross pay." };
  return { body: { staff_ref: clean(f.staff_ref), department: clean(f.department), base_pay: amt(f.base_pay), ...(clean(f.allowances) ? { allowances: amt(f.allowances) } : {}), deductions: d.list, ...(clean(f.employer_contributions) ? { employer_contributions: amt(f.employer_contributions) } : {}) } };
}
export const submitPayload = (f) => (clean(f.note) && clean(f.note).length < 10 ? { problem: "The note needs at least 10 characters (or leave it empty)." } : { body: { note: clean(f.note) } });
export const settingPayload = (v) => { const t = clean(v); if (t.includes(",") && !/^\d{1,3}(,\d{3})+(\.\d+)?$/.test(t)) return { problem: "The review limit must be an amount such as 250000.00 (commas only between groups of three digits)." }; return AMOUNT.test(amt(t)) ? { body: { review_limit: amt(t) } } : { problem: "The review limit must be an amount such as 250000.00 (0 turns it off)." }; };
export const minNote = { remove: 5, return: 10, withdraw: 10 };

// ---- who sees which button ----
export const canEdit = (r, role) => canPrepare(role) && (r.status === "DRAFT" || r.status === "RETURNED");
export const canSubmit = (r, role) => canEdit(r, role) && r.active_lines > 0;
export const canDecide = (r, role, me) => canApprove(role) && r.status === "SUBMITTED" && r.submitted_by !== me;
export const ownWorkText = "You submitted this run, so a different person must decide it.";
