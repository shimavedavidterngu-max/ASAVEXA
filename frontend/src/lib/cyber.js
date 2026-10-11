import { PERMISSIONS, ROLE_PERMISSIONS } from "./permissions.js";

/** Cybersecurity helpers (defensive record-keeping). The server decides everything that matters; these check input early and say who may press which button. */
const has = (role, perm) => !!(ROLE_PERMISSIONS[role] && ROLE_PERMISSIONS[role].includes(perm));
export const canPrepare = (role) => has(role, PERMISSIONS.CYBER_PREPARE);
export const canApprove = (role) => has(role, PERMISSIONS.CYBER_APPROVE);
export const TABS = [["overview", "Overview"], ["assets", "Assets"], ["vulns", "Vulnerabilities"], ["incidents", "Incidents"], ["reviews", "Access reviews"], ["reports", "Reports"]];
export const SEVERITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];
export const ASSET_TYPES = ["SERVER", "ENDPOINT", "APPLICATION", "DATABASE", "NETWORK", "CLOUD", "OTHER"];
export const DATA_CLASSES = ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"];
export const CRITICALITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];
export const CATEGORIES = ["PHISHING", "MALWARE", "UNAUTHORISED_ACCESS", "DATA_EXPOSURE", "DENIAL_OF_SERVICE", "LOSS_OR_THEFT", "OTHER"];
export const OPEN_VULN = ["OPEN", "IN_PROGRESS", "ACCEPTANCE_PENDING"];

export const STATUS = {
  CRITICAL: { tone: "fail", label: "Critical" }, HIGH: { tone: "warn", label: "High" }, MEDIUM: { tone: "info", label: "Medium" }, LOW: { tone: "neutral", label: "Low" },
  OPEN: { tone: "warn", label: "Open" }, IN_PROGRESS: { tone: "info", label: "Being fixed" }, FIXED: { tone: "info", label: "Fixed, waiting for verification" }, VERIFIED: { tone: "pass", label: "Verified fixed" },
  ACCEPTANCE_PENDING: { tone: "warn", label: "Risk acceptance waiting" }, ACCEPTED: { tone: "neutral", label: "Risk accepted" },
  REPORTED: { tone: "warn", label: "Reported" }, INVESTIGATING: { tone: "info", label: "Investigating" }, CONTAINED: { tone: "info", label: "Contained" }, RESOLVED: { tone: "warn", label: "Resolved, waiting for closure" }, CLOSED: { tone: "pass", label: "Closed" },
  SUBMITTED: { tone: "info", label: "Waiting for approval" }, REJECTED: { tone: "fail", label: "Sent back" }, COMPLETED: { tone: "pass", label: "Completed" }, DRAFT: { tone: "neutral", label: "Draft" }, APPROVED: { tone: "pass", label: "Approved" },
  ACTIVE: { tone: "info", label: "Active" }, RETIRED: { tone: "neutral", label: "Retired" }, PENDING: { tone: "warn", label: "Undecided" }, KEEP: { tone: "pass", label: "Keep" }, REMOVE: { tone: "fail", label: "Remove" },
};
export const statusOf = (s) => STATUS[s] || { tone: "neutral", label: s ? String(s).replace(/_/g, " ").toLowerCase().replace(/^./, (c) => c.toUpperCase()) : "—" };
export const label = (s) => statusOf(s).label;
export const FLAG_TEXT = { OVERDUE: "Past its fix deadline", ACCEPTANCE_EXPIRED: "Risk acceptance has expired" };

export const isRealDate = (s) => {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(s || "").trim());
  if (!m) return false;
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
  return d.getUTCFullYear() === +m[1] && d.getUTCMonth() === +m[2] - 1 && d.getUTCDate() === +m[3];
};
export const noteProblem = (n, what = "a reason", min = 3) => ((n || "").trim().length < min ? `Add ${what} (at least ${min} characters).` : null);
const short = (v, n) => (v || "").trim().length < n;

// ---- assets
export const emptyAsset = () => ({ id: "", name: "", type: "SERVER", owner: "", criticality: "MEDIUM", data_class: "INTERNAL", location: "", notes: "" });
export function assetProblem(f) {
  if (short(f.name, 2)) return "Give the asset a name (at least 2 characters).";
  if (short(f.owner, 2)) return "Say who owns it.";
  if (!ASSET_TYPES.includes(f.type) || !CRITICALITIES.includes(f.criticality) || !DATA_CLASSES.includes(f.data_class)) return "Choose the type, criticality and data class.";
  return null;
}
export const assetBody = (f) => ({ name: f.name.trim(), type: f.type, owner: f.owner.trim(), criticality: f.criticality, data_class: f.data_class, location: (f.location || "").trim(), notes: (f.notes || "").trim() });
export const assetForm = (a) => ({ id: a.id, name: a.name, type: a.type, owner: a.owner, criticality: a.criticality, data_class: a.data_class, location: a.location || "", notes: a.notes || "" });

// ---- vulnerabilities
export const emptyVuln = (assetId = "") => ({ asset_id: assetId, title: "", severity: "HIGH", cve: "", source: "", found_date: "", description: "" });
export function vulnProblem(f) {
  if (!f.asset_id) return "Choose the asset.";
  if (short(f.title, 3)) return "Give the vulnerability a title (at least 3 characters).";
  if (!SEVERITIES.includes(f.severity)) return "Choose a severity.";
  if ((f.cve || "").trim() && !/^CVE-\d{4}-\d{4,7}$/i.test(f.cve.trim())) return "A CVE looks like CVE-2024-12345 (or leave it blank).";
  if (short(f.source, 2)) return "Say where it was found (scan, review, report...).";
  if ((f.found_date || "").trim() && !isRealDate(f.found_date)) return "Enter the date found like 2026-02-10, or leave it blank for today.";
  return null;
}
export const vulnBody = (f) => ({ asset_id: f.asset_id, title: f.title.trim(), severity: f.severity, cve: (f.cve || "").trim(), source: f.source.trim(), description: (f.description || "").trim(), ...((f.found_date || "").trim() ? { found_date: f.found_date.trim() } : {}) });
export function acceptProblem(f) {
  if (short(f.reason, 20)) return "Explain why the risk is acceptable (at least 20 characters).";
  if (!isRealDate(f.until)) return "Enter the date the acceptance ends, like 2026-06-30.";
  return null;
}
export function vulnMoves(v, role, userId) {
  const prep = canPrepare(role), appr = canApprove(role), s = v.status;
  return { start: prep && s === "OPEN", fix: prep && ["OPEN", "IN_PROGRESS", "ACCEPTED"].includes(s), accept: prep && ["OPEN", "IN_PROGRESS"].includes(s), reopen: prep && s === "ACCEPTED",
    verify: appr && s === "FIXED" && v.fixed_by !== userId, ownFix: appr && s === "FIXED" && v.fixed_by === userId, decideAccept: appr && s === "ACCEPTANCE_PENDING" && v.accept_requested_by !== userId, ownAccept: appr && s === "ACCEPTANCE_PENDING" && v.accept_requested_by === userId };
}

// ---- incidents
export const emptyIncident = () => ({ title: "", description: "", category: "PHISHING", severity: "HIGH", detected_date: "", asset_ids: [], personal_data_involved: "" });
export function incidentProblem(f) {
  if (short(f.title, 3)) return "Give the incident a title (at least 3 characters).";
  if (short(f.description, 5)) return "Say what happened (at least 5 characters).";
  if (!CATEGORIES.includes(f.category) || !SEVERITIES.includes(f.severity)) return "Choose the category and severity.";
  if ((f.detected_date || "").trim() && !isRealDate(f.detected_date)) return "Enter the date detected like 2026-02-10, or leave it blank for today.";
  if (f.personal_data_involved !== "yes" && f.personal_data_involved !== "no") return "Say whether personal data may be involved.";
  return null;
}
export const incidentBody = (f) => ({ title: f.title.trim(), description: f.description.trim(), category: f.category, severity: f.severity, asset_ids: f.asset_ids, personal_data_involved: f.personal_data_involved === "yes", ...((f.detected_date || "").trim() ? { detected_date: f.detected_date.trim() } : {}) });
export function incidentMoves(n, role, userId) {
  const prep = canPrepare(role), appr = canApprove(role), s = n.status;
  return { note: prep && s !== "CLOSED", investigate: prep && s === "REPORTED", contain: prep && s === "INVESTIGATING", resolve: prep && s === "CONTAINED", close: appr && s === "RESOLVED" && n.resolved_by !== userId, ownResolve: appr && s === "RESOLVED" && n.resolved_by === userId };
}
export function closeProblem(f, n) {
  if (short(f.lessons_learned, 20)) return "Write the lessons learned (at least 20 characters).";
  if (n.personal_data_involved && short(f.notification_decision, 10)) return "Personal data may be involved: record the notification decision your organisation made (at least 10 characters).";
  return null;
}

// ---- access reviews
export const emptyReview = () => ({ name: "", scope: "", due_date: "" });
export function reviewProblem(f) {
  if (short(f.name, 3)) return "Give the review a name (at least 3 characters).";
  if (short(f.scope, 3)) return "Say what is being reviewed (a system or group).";
  if (!isRealDate(f.due_date)) return "Enter the due date like 2026-06-30.";
  return null;
}
export const emptyEntry = () => ({ subject: "", system: "", access: "" });
export const entryProblem = (f) => (short(f.subject, 2) ? "Name the person or account." : short(f.system, 2) ? "Name the system." : short(f.access, 2) ? "Say what access they hold." : null);
export function reviewMoves(r, role, userId) {
  const prep = canPrepare(role), appr = canApprove(role), editable = r.status === "OPEN" || r.status === "REJECTED";
  return { edit: prep && editable, confirm: prep && (editable || r.status === "SUBMITTED"), submit: prep && editable, decide: appr && r.status === "SUBMITTED" && r.submitted_by !== userId, own: appr && r.status === "SUBMITTED" && r.submitted_by === userId };
}

// ---- policy and reports
export const policyForm = (p) => ({ max: String(p.acceptance_max_days), ...Object.fromEntries(Object.entries(p.sla_days).map(([k, v]) => [`s_${k}`, String(v)])) });
export function policyProblem(f) {
  let last = 0;
  for (const s of SEVERITIES) {
    const v = String(f[`s_${s}`]).trim();
    if (!/^\d{1,3}$/.test(v) || +v < 1 || +v > 730) return `The ${label(s).toLowerCase()} deadline is a whole number of days from 1 to 730.`;
    if (+v < last) return "A more severe vulnerability cannot have a longer deadline than a less severe one.";
    last = +v;
  }
  if (!/^\d{1,3}$/.test(String(f.max).trim()) || +f.max < 1 || +f.max > 365) return "The longest risk acceptance is a whole number of days from 1 to 365.";
  return null;
}
export const policyBody = (f) => ({ sla_days: Object.fromEntries(SEVERITIES.map((s) => [s, +String(f[`s_${s}`]).trim()])), acceptance_max_days: +String(f.max).trim() });
export const reportProblem = (f) => (short(f.title, 3) ? "Give the report a title." : null);
export function reportMoves(r, role, userId) {
  const prep = canPrepare(role), appr = canApprove(role);
  return { submit: prep && (r.status === "DRAFT" || r.status === "REJECTED"), decide: appr && r.status === "SUBMITTED" && r.submitted_by !== userId, own: appr && r.status === "SUBMITTED" && r.submitted_by === userId, exportable: r.status === "APPROVED" };
}
