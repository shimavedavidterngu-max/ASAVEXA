import { PERMISSIONS, ROLE_PERMISSIONS } from "./permissions.js";
import { fmt, isRealDate, noteProblem, words } from "./treasury.js";

/**
 * Projects and grants helpers (a project with a typed award and budget lines; spending and receipts that a different person decides; moves no money). No DOM, no network.
 * The server enforces every rule and does all the arithmetic. These check input early, word things, and hide buttons that could not work.
 */
export { fmt, isRealDate, noteProblem, words };
const has = (role, perm) => !!(ROLE_PERMISSIONS[role] && ROLE_PERMISSIONS[role].includes(perm));
export const canRead = (role) => has(role, PERMISSIONS.AUDIT_READ);
export const canPrepare = (role) => has(role, PERMISSIONS.PROJ_PREPARE);
export const canApprove = (role) => has(role, PERMISSIONS.PROJ_APPROVE);

export const TABS = [["overview", "Overview"], ["projects", "Projects"]];
export const STATUS = {
  DRAFT: { tone: "neutral", label: "Draft" }, SUBMITTED: { tone: "warn", label: "Waiting for review" }, ACTIVE: { tone: "pass", label: "Open" }, RETURNED: { tone: "warn", label: "Returned" }, CLOSED: { tone: "neutral", label: "Closed" }, WITHDRAWN: { tone: "neutral", label: "Withdrawn" },
  PROPOSED: { tone: "warn", label: "Waiting for a decision" }, APPROVED: { tone: "pass", label: "Approved" }, REJECTED: { tone: "neutral", label: "Rejected" }, REMOVED: { tone: "neutral", label: "Removed" },
};
export const statusOf = (s) => STATUS[s] || { tone: "neutral", label: s ? words(s) : "—" };
export const ATTENTION_TONE = { PROJECTS_TO_REVIEW: "info", PROJECTS_RETURNED: "warn", ENTRIES_TO_REVIEW: "info", OVER_BUDGET: "warn", RECEIVED_ABOVE_AWARD: "warn", ENDING_SOON: "warn", ENDED_STILL_OPEN: "warn" };

const clean = (v) => String(v == null ? "" : v).trim();
const first = (...p) => p.find(Boolean) || "";
const dateProblem = (v, what) => (isRealDate(clean(v)) ? "" : `${what} must be a real date written YYYY-MM-DD.`);
const textProblem = (v, what, min) => (clean(v).length >= min ? "" : `${what} needs at least ${min} characters.`);
const nonZero = (t) => /[1-9]/.test(t);
const amt = (v) => clean(v).replace(/,/g, "");
const AMOUNT = /^\d{1,13}(\.\d{1,2})?$/;
const amountProblem = (v, what) => {
  const t = clean(v);
  if (t.includes(",") && !/^\d{1,3}(,\d{3})+(\.\d+)?$/.test(t)) return `${what} must be an amount such as 1500.00 (commas only between groups of three digits).`;
  if (!AMOUNT.test(amt(v))) return `${what} must be an amount such as 1500.00 (at most two decimals).`;
  return nonZero(amt(v)) ? "" : `${what} must be more than zero.`;
};

export const EMPTY = {
  project: { title: "", funder_ref: "", currency: "", award: "", period_start: "", period_end: "" },
  budget: { category: "", amount: "" },
  entry: { entry_type: "EXPENSE", budget_no: "", amount: "", entry_date: "", description: "" },
  submit: { note: "" },
};

export function projectPayload(f) {
  const cur = clean(f.currency).toUpperCase();
  const p = first(textProblem(f.title, "The title", 3), textProblem(f.funder_ref, "The funder reference", 2), /^[A-Z]{3}$/.test(cur) ? "" : "The currency must be a three-letter code such as NGN.", amountProblem(f.award, "The award"),
    dateProblem(f.period_start, "The start of the project"), dateProblem(f.period_end, "The end of the project"),
    isRealDate(clean(f.period_start)) && isRealDate(clean(f.period_end)) && clean(f.period_end) < clean(f.period_start) ? "The project cannot end before it starts." : "");
  if (p) return { problem: p };
  return { body: { title: clean(f.title), funder_ref: clean(f.funder_ref), currency: cur, award: amt(f.award), period_start: clean(f.period_start), period_end: clean(f.period_end) } };
}
export function budgetPayload(f) {
  const p = first(textProblem(f.category, "The category", 2), amountProblem(f.amount, "The budget amount"));
  return p ? { problem: p } : { body: { category: clean(f.category), amount: amt(f.amount) } };
}
export function entryPayload(f, project) {
  const type = clean(f.entry_type), d = clean(f.entry_date);
  if (type !== "EXPENSE" && type !== "RECEIPT") return { problem: "Choose whether this is an expense or a receipt." };
  const p = first(amountProblem(f.amount, "The amount"), dateProblem(d, "The date"), textProblem(f.description, "The description", 3),
    type === "EXPENSE" && !/^\d+$/.test(clean(f.budget_no)) ? "Choose the budget line the expense belongs to." : "",
    project && isRealDate(d) && (d < project.period_start || d > project.period_end) ? "The date must fall inside the project period." : "");
  if (p) return { problem: p };
  return { body: { entry_type: type, ...(type === "EXPENSE" ? { budget_no: Number(clean(f.budget_no)) } : {}), amount: amt(f.amount), entry_date: d, description: clean(f.description) } };
}
export const submitPayload = (f) => (clean(f.note) && clean(f.note).length < 10 ? { problem: "The note needs at least 10 characters (or leave it empty)." } : { body: { note: clean(f.note) } });
export const settingPayload = (v) => (/^\d{1,3}$/.test(clean(v)) && Number(clean(v)) >= 1 && Number(clean(v)) <= 365 ? { body: { ending_soon_days: Number(clean(v)) } } : { problem: "The number of days must be a whole number from 1 to 365." });
export const minNote = { remove: 5, return: 10, withdraw: 10, reject: 10, close: 10 };

// ---- who sees which button ----
export const canEdit = (p, role) => canPrepare(role) && (p.status === "DRAFT" || p.status === "RETURNED");
export const canSubmit = (p, role) => canEdit(p, role) && p.active_lines > 0;
export const canDecide = (p, role, me) => canApprove(role) && p.status === "SUBMITTED" && p.submitted_by !== me;
export const canEnter = (p, role) => canPrepare(role) && p.status === "ACTIVE";
export const canDecideEntry = (p, e, role, me) => canApprove(role) && p.status === "ACTIVE" && e.status === "PROPOSED" && e.proposed_by !== me;
export const canClose = (p, role) => canApprove(role) && p.status === "ACTIVE" && p.pending_entries === 0;
export const ownWorkText = "You submitted this, so a different person must decide it.";
export const ownEntryText = "You proposed this entry, so a different person must decide it.";
