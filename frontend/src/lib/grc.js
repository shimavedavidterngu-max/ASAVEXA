import { PERMISSIONS, ROLE_PERMISSIONS } from "./permissions.js";

/** Governance, Risk and Compliance helpers. Scores are people's judgements: likelihood x impact on a 1 to 5 scale, banded exactly as the server bands them. */
const has = (role, perm) => !!(ROLE_PERMISSIONS[role] && ROLE_PERMISSIONS[role].includes(perm));
export const canPrepare = (role) => has(role, PERMISSIONS.GRC_PREPARE);
export const canApprove = (role) => has(role, PERMISSIONS.GRC_APPROVE);
export const TABS = [["overview", "Overview"], ["risks", "Risks"], ["actions", "Actions"], ["obligations", "Obligations"]];

export const bandOf = (score) => (score <= 4 ? "LOW" : score <= 9 ? "MEDIUM" : score <= 16 ? "HIGH" : "CRITICAL");
export const BAND = { LOW: { tone: "pass", label: "Low" }, MEDIUM: { tone: "info", label: "Medium" }, HIGH: { tone: "warn", label: "High" }, CRITICAL: { tone: "fail", label: "Critical" } };
export const bandInfo = (b) => BAND[b] || { tone: "neutral", label: b || "—" };
export const RISK_STATUS = { ASSESSED: { tone: "info", label: "Assessed" }, TREATING: { tone: "info", label: "Being treated" }, ACCEPTANCE_REQUESTED: { tone: "warn", label: "Acceptance waiting for approval" },
  ACCEPTED: { tone: "neutral", label: "Accepted" }, CLOSED: { tone: "neutral", label: "Closed" } };
export const ACTION_STATUS = { OPEN: { tone: "info", label: "Open" }, DONE: { tone: "warn", label: "Done, waiting to be verified" }, VERIFIED: { tone: "pass", label: "Verified" }, CANCELLED: { tone: "neutral", label: "Cancelled" } };
export const OB_STATE = { ON_TRACK: { tone: "pass", label: "On track" }, DUE_SOON: { tone: "warn", label: "Due soon" }, OVERDUE: { tone: "fail", label: "Overdue" }, MET: { tone: "pass", label: "Met" }, RETIRED: { tone: "neutral", label: "Retired" } };
const pick = (m, k) => m[k] || { tone: "neutral", label: k || "—" };
export const riskStatus = (s) => pick(RISK_STATUS, s);
export const actionStatus = (s) => pick(ACTION_STATUS, s);
export const obState = (s) => pick(OB_STATE, s);

export const isRealDate = (s) => {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(s || "").trim());
  if (!m) return false;
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
  return d.getUTCFullYear() === +m[1] && d.getUTCMonth() === +m[2] - 1 && d.getUTCDate() === +m[3];
};
const scale = (v) => /^[1-5]$/.test(String(v).trim());

export const emptyRisk = () => ({ id: "", title: "", description: "", category: "OPERATIONAL", owner: "", inherent_l: "3", inherent_i: "3", residual_l: "3", residual_i: "3", residual_justification: "", treatment: "MITIGATE", next_review: "", control_ids: [] });
export function riskProblem(f) {
  if ((f.title || "").trim().length < 3) return "Give the risk a title (at least 3 characters).";
  if ((f.owner || "").trim().length < 2) return "Name the person who owns this risk.";
  for (const [k, l] of [["inherent_l", "Inherent likelihood"], ["inherent_i", "Inherent impact"], ["residual_l", "Residual likelihood"], ["residual_i", "Residual impact"]]) if (!scale(f[k])) return `${l} must be a whole number from 1 to 5.`;
  const inh = f.inherent_l * f.inherent_i, res = f.residual_l * f.residual_i;
  if (res > inh) return "The residual score cannot be higher than the inherent score.";
  if (res < inh && (f.residual_justification || "").trim().length < 10) return "A residual score lower than the inherent score needs a written reason (at least 10 characters).";
  if (!isRealDate(f.next_review)) return "Enter the next review date like 2026-12-31.";
  return null;
}
export const riskBody = (f) => ({ title: f.title.trim(), description: (f.description || "").trim(), category: f.category, owner: f.owner.trim(), inherent_l: +f.inherent_l, inherent_i: +f.inherent_i,
  residual_l: +f.residual_l, residual_i: +f.residual_i, residual_justification: (f.residual_justification || "").trim(), treatment: f.treatment, next_review: f.next_review.trim(), control_ids: f.control_ids });
export const riskForm = (r) => ({ id: r.id, title: r.title, description: r.description || "", category: r.category, owner: r.owner, inherent_l: String(r.inherent_l), inherent_i: String(r.inherent_i),
  residual_l: String(r.residual_l), residual_i: String(r.residual_i), residual_justification: r.residual_justification || "", treatment: r.treatment, next_review: r.next_review || "", control_ids: [...(r.control_ids || [])] });

export function riskMoves(r, role, userId) {
  const prep = canPrepare(role), s = r.status, acc = r.acceptance;
  return { edit: prep && (s === "ASSESSED" || s === "TREATING"), treat: prep && s === "ASSESSED" && r.treatment !== "ACCEPT", accept: prep && (s === "ASSESSED" || s === "TREATING"),
    decide: canApprove(role) && s === "ACCEPTANCE_REQUESTED" && !!acc && acc.requested_by !== userId, ownRequest: canApprove(role) && s === "ACCEPTANCE_REQUESTED" && !!acc && acc.requested_by === userId,
    reopen: prep && (s === "ACCEPTED" || s === "CLOSED"), close: prep && (s === "ASSESSED" || s === "TREATING" || s === "ACCEPTED"), addAction: prep && s !== "CLOSED" };
}

export const emptyAction = (riskId = "") => ({ id: "", risk_id: riskId, title: "", description: "", owner: "", due: "" });
export function actionProblem(f) {
  if (!f.id && !f.risk_id) return "Choose the risk this action is for.";
  if ((f.title || "").trim().length < 3) return "Give the action a title (at least 3 characters).";
  if ((f.owner || "").trim().length < 2) return "Name the person responsible for the action.";
  if (!isRealDate(f.due)) return "Enter the due date like 2026-12-31.";
  return null;
}
export const actionBody = (f) => { const b = { title: f.title.trim(), description: (f.description || "").trim(), owner: f.owner.trim(), due: f.due.trim() }; if (!f.id) b.risk_id = f.risk_id; return b; };
export const actionForm = (a) => ({ id: a.id, risk_id: a.risk_id, title: a.title, description: a.description || "", owner: a.owner, due: a.due });
export function actionMoves(a, role, userId) {
  const prep = canPrepare(role), appr = canApprove(role), s = a.status;
  return { edit: prep && s === "OPEN", complete: prep && s === "OPEN", cancel: prep && s === "OPEN", verify: appr && s === "DONE" && a.completed_by !== userId, ownCompletion: appr && s === "DONE" && a.completed_by === userId };
}
export const doneProblem = (f) => ((f.note || "").trim().length < 10 ? "Say what was done (at least 10 characters)." : null);

export const emptyObligation = () => ({ id: "", title: "", source_type: "LAW", authority: "", source_ref: "", source_url: "", description: "", owner: "", frequency: "ANNUAL", next_due: "", control_ids: [] });
export function obligationProblem(f) {
  if ((f.title || "").trim().length < 3) return "Give the obligation a title (at least 3 characters).";
  if ((f.authority || "").trim().length < 2) return "Say who the obligation is owed to (a regulator, a contract party, your board).";
  if ((f.description || "").trim().length < 5) return "Describe what must be done (at least 5 characters).";
  if ((f.owner || "").trim().length < 2) return "Name the person responsible.";
  if (f.source_url && f.source_url.trim() && !/^https?:\/\//i.test(f.source_url.trim())) return "The source link must start with http:// or https://.";
  if (!isRealDate(f.next_due)) return "Enter the next due date like 2026-12-31.";
  return null;
}
export const obligationBody = (f) => ({ title: f.title.trim(), source_type: f.source_type, authority: f.authority.trim(), source_ref: (f.source_ref || "").trim(), source_url: (f.source_url || "").trim(),
  description: f.description.trim(), owner: f.owner.trim(), frequency: f.frequency, next_due: f.next_due.trim(), control_ids: f.control_ids });
export const obligationForm = (o) => ({ id: o.id, title: o.title, source_type: o.source_type, authority: o.authority, source_ref: o.source_ref || "", source_url: o.source_url || "", description: o.description, owner: o.owner,
  frequency: o.frequency, next_due: o.next_due || "", control_ids: [...(o.control_ids || [])] });
export const emptyMet = (today = "") => ({ met_on: today, note: "", evidence_ids: [] });
export function metProblem(f, today) {
  if (!isRealDate(f.met_on)) return "Enter the date it was met like 2026-12-31.";
  if (today && f.met_on > today) return "The date met cannot be in the future.";
  if ((f.note || "").trim().length < 5) return "Say how it was met (at least 5 characters).";
  return null;
}
export const noteProblem = (n, what = "a reason", min = 5) => ((n || "").trim().length < min ? `Add ${what} (at least ${min} characters).` : null);
export const acceptProblem = (f, today) => {
  if ((f.justification || "").trim().length < 20) return "Say why this risk can be accepted (at least 20 characters).";
  if (!isRealDate(f.review_by)) return "Enter the review-by date like 2026-12-31.";
  if (today && f.review_by <= today) return "The review-by date must be in the future.";
  return null;
};
