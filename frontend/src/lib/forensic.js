import { PERMISSIONS, ROLE_PERMISSIONS } from "./permissions.js";

/** Forensic helpers. Indicators are never described as findings or proof; wording in this file and the page keeps that line. */
const has = (role, perm) => !!(ROLE_PERMISSIONS[role] && ROLE_PERMISSIONS[role].includes(perm));
export const canPrepare = (role) => has(role, PERMISSIONS.FORENSIC_PREPARE);
export const canApprove = (role) => has(role, PERMISSIONS.FORENSIC_APPROVE);
export const TABS = [["overview", "Overview"], ["evidence", "Evidence"], ["analytics", "Analytics"], ["findings", "Findings"], ["reports", "Reports"], ["custody", "Custody log"]];
export const STATE = { DRAFT: { tone: "neutral", label: "Draft" }, SUBMITTED: { tone: "info", label: "Waiting for review" }, APPROVED: { tone: "pass", label: "Approved" }, REJECTED: { tone: "fail", label: "Sent back" }, OPEN: { tone: "info", label: "Open" }, CLOSED: { tone: "neutral", label: "Closed" } };
export const stateOf = (s) => STATE[s] || { tone: "neutral", label: s || "—" };
export const RESULT = { INDICATORS: { tone: "warn", label: "Worth a look" }, NO_INDICATORS: { tone: "pass", label: "Nothing flagged" }, NOT_ENOUGH_DATA: { tone: "neutral", label: "Not enough data" }, NOT_CONFIGURED: { tone: "neutral", label: "Needs a setting" } };
export const resultOf = (s) => RESULT[s] || { tone: "neutral", label: s };
export const SEVERITY_TEXT = { LOW: "Low", MEDIUM: "Medium", HIGH: "High" };
export const num = (v) => {
  if (v == null || v === "") return "—";
  const m = /^(-?)(\d+)(?:\.(\d+))?$/.exec(String(v));
  return m ? `${m[1]}${m[2].replace(/\B(?=(\d{3})+(?!\d))/g, ",")}${m[3] ? "." + m[3] : ""}` : String(v);
};

export const emptyCase = () => ({ title: "", description: "", case_type: "IRREGULARITY" });
export const caseProblem = (f) => ((f.title || "").trim().length < 3 ? "Give the case a title (at least 3 characters)." : null);

export const emptyRun = (defaults = {}) => ({ scope_kind: "period", period_id: "", start: "", end: "", tests: ["same_person", "duplicates", "weekend", "round_numbers", "late_posting", "reversals"],
  approval_limit: "", evidence_threshold: "", round_to: String(defaults.round_to ?? 1000), duplicate_window_days: String(defaults.duplicate_window_days ?? 3), late_days: String(defaults.late_days ?? 30), weekend_days: "5,6" });
export function runProblem(f) {
  if (!f.tests.length) return "Choose at least one test.";
  if (f.scope_kind === "period" && !f.period_id) return "Choose the period to examine.";
  if (f.scope_kind === "dates" && (!/^\d{4}-\d{2}-\d{2}$/.test(f.start) || !/^\d{4}-\d{2}-\d{2}$/.test(f.end))) return "Enter the start and end dates like 2026-01-31.";
  if (f.tests.includes("just_below") && !/^\d+(\.\d+)?$/.test(String(f.approval_limit).trim())) return "Enter the approval limit to test against.";
  if (f.tests.includes("no_evidence") && !/^\d+(\.\d+)?$/.test(String(f.evidence_threshold).trim())) return "Enter the amount above which evidence is expected.";
  for (const [k, l] of [["round_to", "Round-number size"], ["duplicate_window_days", "Duplicate window"], ["late_days", "Late-posting days"]]) if (!/^\d+$/.test(String(f[k]).trim())) return `${l} must be a whole number.`;
  if (!/^[0-6](\s*,\s*[0-6])*$/.test(String(f.weekend_days).trim())) return "Weekend days are numbers from 0 (Monday) to 6 (Sunday), like 5,6.";
  return null;
}
export function runBody(f) {
  const params = { round_to: f.round_to.trim(), duplicate_window_days: f.duplicate_window_days.trim(), late_days: f.late_days.trim(), weekend_days: f.weekend_days.split(",").map((x) => parseInt(x.trim(), 10)) };
  if (f.approval_limit.trim()) params.approval_limit = f.approval_limit.trim();
  if (f.evidence_threshold.trim()) params.evidence_threshold = f.evidence_threshold.trim();
  return { scope: f.scope_kind === "period" ? { period_id: f.period_id } : { start: f.start, end: f.end }, tests: f.tests, params };
}

export const emptyFinding = () => ({ id: "", title: "", description: "", severity: "MEDIUM", journals: [], evidence_ids: [], run_id: "" });
export function findingProblem(f) {
  if ((f.title || "").trim().length < 3) return "Give the finding a title.";
  if ((f.description || "").trim().length < 20) return "Describe what was found and what supports it (at least 20 characters).";
  return null;
}
export const findingBody = (f) => ({ title: f.title.trim(), description: f.description.trim(), severity: f.severity, journal_ids: f.journals.map((j) => j.id), evidence_ids: f.evidence_ids, run_id: f.run_id || null });
export const findingForm = (x) => ({ id: x.id, title: x.title, description: x.description, severity: x.severity, journals: x.journals.map((j) => ({ ...j })), evidence_ids: [...x.evidence_ids], run_id: x.run_id || "" });

export function itemActions(item, role, userId) {
  const s = item ? item.status : null, mine = !!item && (item.created_by === userId || item.submitted_by === userId);
  return { edit: canPrepare(role) && (s === "DRAFT" || s === "REJECTED"), submit: canPrepare(role) && (s === "DRAFT" || s === "REJECTED"), discard: canPrepare(role) && (s === "DRAFT" || s === "REJECTED"),
    decide: canApprove(role) && s === "SUBMITTED" && !mine, ownSubmission: canApprove(role) && s === "SUBMITTED" && mine };
}
export const canClose = (c, role, userId) => canApprove(role) && c.status === "OPEN" && c.opened_by !== userId;
