import { PERMISSIONS, ROLE_PERMISSIONS } from "./permissions.js";

/** Public Finance helpers. Money stays a string (exact decimals); we only validate and format it, never do float arithmetic on it. */
const has = (role, perm) => !!(ROLE_PERMISSIONS[role] && ROLE_PERMISSIONS[role].includes(perm));
export const canPrepare = (role) => has(role, PERMISSIONS.PUBFIN_PREPARE);
export const canApprove = (role) => has(role, PERMISSIONS.PUBFIN_APPROVE);
export const TABS = [["overview", "Overview"], ["spend", "Where the money went"], ["budgets", "Budgets"], ["commitments", "Commitments"], ["procurement", "Procurement"], ["grants", "Grants"], ["follow", "Follow a grant"], ["reports", "Reports"]];

export const STATUS = {
  DRAFT: { tone: "neutral", label: "Draft" }, SUBMITTED: { tone: "info", label: "Waiting for approval" }, APPROVED: { tone: "pass", label: "Approved" }, REJECTED: { tone: "fail", label: "Sent back" },
  CLOSED: { tone: "neutral", label: "Closed" }, OPEN: { tone: "info", label: "Open" }, SETTLED: { tone: "pass", label: "Settled" }, CANCELLED: { tone: "neutral", label: "Cancelled" },
  AWARD_PROPOSED: { tone: "warn", label: "Award waiting for approval" }, AWARDED: { tone: "pass", label: "Awarded" }, ACTIVE: { tone: "info", label: "Active" }, PROPOSED: { tone: "warn", label: "Waiting for approval" },
};
export const statusOf = (s) => STATUS[s] || { tone: "neutral", label: s || "—" };

export const money = (v) => {
  if (v == null || v === "") return "—";
  const m = /^(-?)(\d+)(?:\.(\d+))?$/.exec(String(v));
  return m ? `${m[1]}${m[2].replace(/\B(?=(\d{3})+(?!\d))/g, ",")}${m[3] ? "." + m[3] : ""}` : String(v);
};
export const isMoney = (v) => /^\d{1,15}(\.\d{1,2})?$/.test(String(v == null ? "" : v).trim());
export const isPositive = (v) => isMoney(v) && Number(String(v).trim()) > 0;
export const isRealDate = (s) => {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(s || "").trim());
  if (!m) return false;
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
  return d.getUTCFullYear() === +m[1] && d.getUTCMonth() === +m[2] - 1 && d.getUTCDate() === +m[3];
};
export const noteProblem = (n, what = "a reason", min = 5) => ((n || "").trim().length < min ? `Add ${what} (at least ${min} characters).` : null);

export const emptyBudget = () => ({ id: "", name: "", description: "", start: "", end: "", currency: "USD", amounts: {} });
export function budgetProblem(f) {
  if ((f.name || "").trim().length < 3) return "Give the budget a name (at least 3 characters).";
  if (!isRealDate(f.start) || !isRealDate(f.end)) return "Enter the start and end dates like 2026-01-31.";
  if (f.end < f.start) return "The end date cannot be before the start date.";
  if (!/^[A-Za-z]{3}$/.test((f.currency || "").trim())) return "The currency is a 3-letter code like USD or NGN.";
  const used = Object.entries(f.amounts).filter(([, v]) => String(v).trim() !== "");
  if (!used.length) return "Enter an amount for at least one line.";
  for (const [, v] of used) if (!isMoney(v)) return "Amounts are numbers like 1500 or 1500.50 (no commas, at most 2 decimals).";
  return null;
}
export const budgetBody = (f) => ({ name: f.name.trim(), description: (f.description || "").trim(), start: f.start.trim(), end: f.end.trim(), currency: f.currency.trim().toUpperCase(),
  lines: Object.entries(f.amounts).filter(([, v]) => String(v).trim() !== "").map(([account_id, v]) => ({ account_id, amount: String(v).trim() })) });
export const budgetForm = (b) => ({ id: b.id, name: b.name, description: b.description || "", start: b.start, end: b.end, currency: b.currency, amounts: Object.fromEntries(b.lines.map((l) => [l.account_id, l.amount])) });
export function budgetMoves(b, role, userId) {
  const prep = canPrepare(role), appr = canApprove(role), s = b.status;
  return { edit: prep && (s === "DRAFT" || s === "REJECTED"), submit: prep && (s === "DRAFT" || s === "REJECTED"), discard: prep && (s === "DRAFT" || s === "REJECTED"),
    decide: appr && s === "SUBMITTED" && b.submitted_by !== userId, ownSubmission: appr && s === "SUBMITTED" && b.submitted_by === userId, close: prep && s === "APPROVED", virement: prep && s === "APPROVED" };
}
export function virementProblem(f, b) {
  if (!f.from_account || !f.to_account) return "Choose both budget lines.";
  if (f.from_account === f.to_account) return "Choose two different lines.";
  if (!isPositive(f.amount)) return "Enter the amount to move, more than zero.";
  if ((f.reason || "").trim().length < 10) return "Say why (at least 10 characters).";
  return null;
}
export const virementMoves = (v, role, userId) => ({ decide: canApprove(role) && v.status === "PROPOSED" && v.proposed_by !== userId, own: canApprove(role) && v.status === "PROPOSED" && v.proposed_by === userId });

export const emptyCommit = (budgetId = "") => ({ budget_id: budgetId, account_id: "", vendor: "", description: "", amount: "", date: "", evidence_ids: [] });
export function commitProblem(f) {
  if (!f.budget_id) return "Choose the budget.";
  if (!f.account_id) return "Choose the expense line.";
  if ((f.vendor || "").trim().length < 2) return "Name the vendor or payee.";
  if ((f.description || "").trim().length < 3) return "Say what it is for.";
  if (!isPositive(f.amount)) return "Enter the amount, more than zero (like 250.50).";
  if (!isRealDate(f.date)) return "Enter the date like 2026-02-10.";
  return null;
}
export const commitBody = (f) => ({ budget_id: f.budget_id, account_id: f.account_id, vendor: f.vendor.trim(), description: f.description.trim(), amount: f.amount.trim(), date: f.date.trim(), evidence_ids: f.evidence_ids });
export const settleProblem = (f) => (!isMoney(f.settled_amount) ? "Enter the amount actually paid or invoiced." : (f.note || "").trim().length < 3 ? "Add a note, such as the journal number it was posted as." : null);

export const emptyProc = () => ({ budget_id: "", account_id: "", title: "", description: "", estimate: "" });
export const procProblem = (f) => (!f.budget_id ? "Choose the budget." : !f.account_id ? "Choose the expense line." : (f.title || "").trim().length < 3 ? "Say what is being bought." : !isPositive(f.estimate) ? "Enter the estimated cost, more than zero." : null);
export const quoteProblem = (f) => ((f.vendor || "").trim().length < 2 ? "Name the vendor." : !isPositive(f.amount) ? "Enter the quoted amount, more than zero." : null);
export function awardProblem(f, p, policy) {
  if (!f.quote_id) return "Choose the quote to award.";
  const q = p.quotes.find((x) => x.id === f.quote_id);
  if (!q) return "Choose the quote to award.";
  if (Number(p.estimate) >= Number(policy.quote_threshold) && p.quotes.length < policy.min_quotes && (f.exception_reason || "").trim().length < 20)
    return `Policy needs ${policy.min_quotes} quotes and there ${p.quotes.length === 1 ? "is" : "are"} ${p.quotes.length}. Add quotes or give a written exception reason (at least 20 characters).`;
  const lowest = Math.min(...p.quotes.map((x) => Number(x.amount)));
  if (Number(q.amount) > lowest && (f.justification || "").trim().length < 20) return "This is not the lowest quote. Say why it was chosen (at least 20 characters).";
  return null;
}
export const procMoves = (p, role, userId) => ({ quote: canPrepare(role) && p.status === "OPEN", award: canPrepare(role) && p.status === "OPEN" && p.quotes.length > 0, cancel: canPrepare(role) && (p.status === "OPEN" || p.status === "AWARD_PROPOSED"),
  decide: canApprove(role) && p.status === "AWARD_PROPOSED" && p.award.proposed_by !== userId, own: canApprove(role) && p.status === "AWARD_PROPOSED" && p.award.proposed_by === userId });
export const policyProblem = (f) => (!/^([1-9]|10)$/.test(String(f.min_quotes).trim()) ? "The number of quotes is a whole number from 1 to 10." : !isMoney(f.quote_threshold) ? "The threshold is a number like 1000 or 0." : null);

export const emptyGrant = () => ({ title: "", donor: "", amount: "", currency: "USD", start: "", end: "", restricted: true, conditions: "" });
export function grantProblem(f) {
  if ((f.title || "").trim().length < 3) return "Give the grant a title.";
  if ((f.donor || "").trim().length < 2) return "Name the donor.";
  if (!isPositive(f.amount)) return "Enter the award amount, more than zero.";
  if (!/^[A-Za-z]{3}$/.test((f.currency || "").trim())) return "The currency is a 3-letter code.";
  if (!isRealDate(f.start) || !isRealDate(f.end)) return "Enter the start and end dates like 2026-01-31.";
  if (f.end < f.start) return "The end date cannot be before the start date.";
  return null;
}
export const grantBody = (f) => ({ title: f.title.trim(), donor: f.donor.trim(), amount: f.amount.trim(), currency: f.currency.trim().toUpperCase(), start: f.start.trim(), end: f.end.trim(), restricted: !!f.restricted, conditions: (f.conditions || "").trim() });
export const receiptProblem = (f) => (!isPositive(f.amount) ? "Enter the amount received, more than zero." : !isRealDate(f.date) ? "Enter the date received like 2026-02-10." : (f.reference || "").trim().length < 2 ? "Add the bank or receipt reference." : null);
export const spendProblem = (f) => (!isPositive(f.amount) ? "Enter the amount, more than zero." : !isRealDate(f.date) ? "Enter the date like 2026-02-10." : (f.description || "").trim().length < 3 ? "Say what it was for." : null);
export const spendMoves = (s, role, userId) => ({ decide: canApprove(role) && s.status === "PROPOSED" && s.proposed_by !== userId, own: canApprove(role) && s.status === "PROPOSED" && s.proposed_by === userId });

export const reportProblem = (f) => (!f.budget_id ? "Choose the budget to report on." : (f.title || "").trim().length < 3 ? "Give the report a title." : null);
export function reportMoves(r, role, userId) {
  const prep = canPrepare(role), appr = canApprove(role);
  return { submit: prep && (r.status === "DRAFT" || r.status === "REJECTED"), decide: appr && r.status === "SUBMITTED" && r.submitted_by !== userId, own: appr && r.status === "SUBMITTED" && r.submitted_by === userId, exportable: r.status === "APPROVED" };
}
