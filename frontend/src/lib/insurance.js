import { PERMISSIONS, ROLE_PERMISSIONS } from "./permissions.js";
import { fmt, isRealDate, noteProblem, words } from "./treasury.js";

/**
 * Insurance and claims helpers (a register of what people type in; no insurer is contacted and no advice is given). No DOM, no network.
 * The server enforces every rule and does all the arithmetic. These check input early, word things, and hide buttons that could not work.
 */
export { fmt, isRealDate, noteProblem, words };
const has = (role, perm) => !!(ROLE_PERMISSIONS[role] && ROLE_PERMISSIONS[role].includes(perm));
export const canRead = (role) => has(role, PERMISSIONS.AUDIT_READ);
export const canPrepare = (role) => has(role, PERMISSIONS.INS_PREPARE);
export const canApprove = (role) => has(role, PERMISSIONS.INS_APPROVE);

export const TABS = [["overview", "Overview"], ["policies", "Policies"], ["claims", "Claims"]];
export const COVER_TEXT = { PROPERTY: "Property", LIABILITY: "Liability", MOTOR: "Motor", HEALTH: "Health", LIFE: "Life", CYBER: "Cyber", MARINE: "Marine", CROP: "Crop", OTHER: "Other" };
export const STATUS = {
  ACTIVE: { tone: "pass", label: "Active" }, CANCELLED: { tone: "neutral", label: "Cancelled" },
  OPEN: { tone: "info", label: "Open" }, PROPOSED: { tone: "warn", label: "Outcome waiting for a decision" }, SETTLED: { tone: "pass", label: "Settled" }, DECLINED: { tone: "neutral", label: "Declined" },
  PENDING: { tone: "warn", label: "Waiting for a decision" }, APPROVED: { tone: "pass", label: "Approved" }, REJECTED: { tone: "neutral", label: "Rejected" },
};
export const statusOf = (s) => STATUS[s] || { tone: "neutral", label: s ? words(s) : "—" };
export const ATTENTION_TONE = { OUTCOMES_TO_DECIDE: "info", SETTLED_UNPAID: "warn", POLICIES_ENDING_SOON: "warn", POLICIES_EXPIRED: "warn" };
export const who = (id, me) => (!id ? "—" : id === me ? "You" : String(id).slice(0, 8));

const clean = (v) => String(v == null ? "" : v).trim();
const first = (...p) => p.find(Boolean) || "";
const dateProblem = (v, what) => (isRealDate(clean(v)) ? "" : `${what} must be a real date written YYYY-MM-DD.`);
const textProblem = (v, what, min) => (clean(v).length >= min ? "" : `${what} needs at least ${min} characters.`);
const nonZero = (t) => /[1-9]/.test(t);
const amt = (v) => clean(v).replace(/,/g, "");
const AMOUNT = /^\d{1,12}(\.\d{1,2})?$/;
const amountProblem = (v, what, zeroOk) => { const t = amt(v); if (!AMOUNT.test(t)) return `${what} must be an amount such as 1500.00 (at most two decimals).`; return zeroOk || nonZero(t) ? "" : `${what} must be more than zero.`; };
const cents = (v) => { const [w, f = ""] = amt(v).split("."); return Number(w) * 100 + Number((f + "00").slice(0, 2)); };

export const EMPTY = {
  policy: { insurer: "", policy_number: "", cover_type: "PROPERTY", covers: "", currency: "", sum_insured: "", premium: "", excess: "", start_date: "", end_date: "" },
  claim: { loss_date: "", reported_date: "", description: "", claimed_amount: "", claim_number: "" },
  outcome: { outcome: "SETTLE", amount: "", note: "" },
  receipt: { amount: "", received_on: "", reference: "" },
};

export function policyPayload(f) {
  const cur = clean(f.currency).toUpperCase();
  const p = first(textProblem(f.insurer, "The insurer", 2), textProblem(f.policy_number, "The policy number", 2), textProblem(f.covers, "What is covered", 5), /^[A-Z]{3}$/.test(cur) ? "" : "The currency must be a three-letter code such as NGN.",
    amountProblem(f.sum_insured, "The sum insured"), amountProblem(f.premium, "The premium", true), clean(f.excess) ? amountProblem(f.excess, "The excess", true) : "",
    dateProblem(f.start_date, "The start date"), dateProblem(f.end_date, "The end date"),
    isRealDate(clean(f.start_date)) && isRealDate(clean(f.end_date)) && clean(f.end_date) <= clean(f.start_date) ? "The end date must be after the start date." : "",
    clean(f.excess) && AMOUNT.test(amt(f.excess)) && AMOUNT.test(amt(f.sum_insured)) && cents(f.excess) > cents(f.sum_insured) ? "The excess cannot be more than the sum insured." : "");
  if (p) return { problem: p };
  return { body: { insurer: clean(f.insurer), policy_number: clean(f.policy_number), cover_type: f.cover_type, covers: clean(f.covers), currency: cur, sum_insured: amt(f.sum_insured), premium: amt(f.premium), ...(clean(f.excess) ? { excess: amt(f.excess) } : {}), start_date: clean(f.start_date), end_date: clean(f.end_date) } };
}
export function claimPayload(f, sumInsured) {
  const p = first(dateProblem(f.loss_date, "The date of the loss"), dateProblem(f.reported_date, "The date it was reported"),
    isRealDate(clean(f.loss_date)) && isRealDate(clean(f.reported_date)) && clean(f.reported_date) < clean(f.loss_date) ? "It cannot be reported before the loss happened." : "",
    textProblem(f.description, "The description", 10), amountProblem(f.claimed_amount, "The amount claimed"),
    sumInsured && AMOUNT.test(amt(f.claimed_amount)) && cents(f.claimed_amount) > cents(sumInsured) ? "The amount claimed cannot be more than the sum insured." : "",
    clean(f.claim_number) && clean(f.claim_number).length < 2 ? "The insurer's claim number needs at least 2 characters." : "");
  if (p) return { problem: p };
  return { body: { loss_date: clean(f.loss_date), reported_date: clean(f.reported_date), description: clean(f.description), claimed_amount: amt(f.claimed_amount), ...(clean(f.claim_number) ? { claim_number: clean(f.claim_number) } : {}) } };
}
export function outcomePayload(f, claimed) {
  const settle = f.outcome === "SETTLE";
  const p = first(settle ? amountProblem(f.amount, "The settled amount") : (clean(f.amount) ? "A decline has no settled amount." : ""),
    settle && claimed && AMOUNT.test(amt(f.amount)) && cents(f.amount) > cents(claimed) ? "The settled amount cannot be more than the amount claimed." : "", textProblem(f.note, "The note on the insurer's decision", 10));
  if (p) return { problem: p };
  return { body: { outcome: f.outcome, ...(settle ? { amount: amt(f.amount) } : {}), note: clean(f.note) } };
}
export function receiptPayload(f, outstanding) {
  const p = first(amountProblem(f.amount, "The amount received"), dateProblem(f.received_on, "The date received"), textProblem(f.reference, "The payment reference", 2),
    outstanding != null && AMOUNT.test(amt(f.amount)) && cents(f.amount) > cents(outstanding) ? `That is more than is still to be received (${outstanding}).` : "");
  if (p) return { problem: p };
  return { body: { amount: amt(f.amount), received_on: clean(f.received_on), reference: clean(f.reference) } };
}
export const settingPayload = (v) => { const t = clean(v); return /^\d{1,3}$/.test(t) && Number(t) >= 7 && Number(t) <= 365 ? { body: { warning_days: Number(t) } } : { problem: "The warning days is a whole number from 7 to 365." }; };
export const minNote = { cancel: 10, reject: 10 };

// ---- who sees which button ----
export const canDecideOutcome = (q, role, me) => canApprove(role) && q.status === "PENDING" && q.by !== me;
export const canPropose = (c, role) => canPrepare(role) && c.status === "OPEN";
export const canReceive = (c, role) => canPrepare(role) && c.status === "SETTLED" && Number(c.outstanding) > 0;
export const canCancel = (p, role) => canApprove(role) && p.status === "ACTIVE" && p.open_claims === 0;
export const canClaim = (p, role) => canPrepare(role) && p.status === "ACTIVE";
export const ownWorkText = "You proposed this outcome, so a different person must decide it.";
