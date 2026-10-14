import { PERMISSIONS, ROLE_PERMISSIONS } from "./permissions.js";
import { fmt, isRealDate, noteProblem, words } from "./treasury.js";

/**
 * AI governance helpers (records and checks; nothing is connected, tested or measured). No DOM, no network.
 * The server enforces every rule. These check input early, word things, and hide buttons that could not work.
 */
export { fmt, isRealDate, noteProblem, words };
const has = (role, perm) => !!(ROLE_PERMISSIONS[role] && ROLE_PERMISSIONS[role].includes(perm));
export const canRead = (role) => has(role, PERMISSIONS.AUDIT_READ);
export const canPrepare = (role) => has(role, PERMISSIONS.AIG_PREPARE);
export const canApprove = (role) => has(role, PERMISSIONS.AIG_APPROVE);

export const TABS = [["overview", "Overview"], ["systems", "AI systems"], ["changes", "Model changes"], ["incidents", "Incidents"]];
export const ORIGIN_TEXT = { IN_HOUSE: "Built in-house", VENDOR: "From a vendor", OPEN_SOURCE: "Open source" };
export const TIER_TEXT = { MINIMAL: "Minimal (your own label)", LIMITED: "Limited (your own label)", HIGH: "High (your own label)" };
export const CHANGE_TEXT = { MODEL_UPDATE: "Model update", PROMPT_CHANGE: "Prompt or instruction change", DATA_CHANGE: "Data change", CONFIG_CHANGE: "Settings change", VENDOR_CHANGE: "Change of vendor" };
export const INCIDENT_TEXT = { WRONG_OUTPUT: "Wrong output", BIAS: "Unfair or biased result", DATA_LEAK: "Data leak", MISUSE: "Misuse", OUTAGE: "Outage", OTHER: "Other" };
export const SEVERITY_TEXT = { LOW: "Low", MEDIUM: "Medium", HIGH: "High", CRITICAL: "Critical" };
export const STATUS = {
  PROPOSED: { tone: "warn", label: "Waiting for approval" }, APPROVED: { tone: "pass", label: "Approved" }, REJECTED: { tone: "neutral", label: "Rejected" }, RETIRED: { tone: "neutral", label: "Retired" },
  RECORDED: { tone: "warn", label: "Waiting for a different person" }, REVIEWED: { tone: "pass", label: "Reviewed" }, VOIDED: { tone: "neutral", label: "Voided" },
  MINIMAL: { tone: "neutral", label: "Minimal tier" }, LIMITED: { tone: "warn", label: "Limited tier" }, HIGH: { tone: "fail", label: "High tier" },
  LOW: { tone: "neutral", label: "Low" }, MEDIUM: { tone: "warn", label: "Medium" }, CRITICAL: { tone: "fail", label: "Critical" },
};
export const statusOf = (s) => STATUS[s] || { tone: "neutral", label: s ? words(s) : "—" };
export const ATTENTION_TONE = { SEVERE_INCIDENTS_OPEN: "fail", INCIDENTS_REVIEW_OVERDUE: "warn", SYSTEMS_REVIEW_DUE: "warn", SYSTEMS_TO_APPROVE: "info", CHANGES_TO_APPROVE: "info", INCIDENTS_TO_REVIEW: "info" };
/** A person is shown as "You" or a short form of their id. */
export const who = (id, me) => (!id ? "—" : id === me ? "You" : String(id).slice(0, 8));

const clean = (v) => String(v == null ? "" : v).trim();
const first = (...p) => p.find(Boolean) || "";
const body = (b, ...problems) => { const p = first(...problems); return p ? { problem: p } : { body: b }; };
const dateProblem = (v, what) => (isRealDate(clean(v)) ? "" : `${what} must be a real date written YYYY-MM-DD.`);
const textProblem = (v, what, min) => (clean(v).length >= min ? "" : `${what} needs at least ${min} characters.`);
const optionalText = (v, what, min) => (clean(v) && clean(v).length < min ? `${what} needs at least ${min} characters when given.` : "");
const wholeProblem = (v, what, lo, hi) => (/^\d{1,10}$/.test(clean(v)) && Number(v) >= lo && Number(v) <= hi ? "" : `${what} must be a whole number from ${lo} to ${hi}.`);

export const EMPTY = {
  system: { name: "", description: "", origin: "VENDOR", vendor_name: "", intended_use: "", out_of_scope: "", risk_tier: "LIMITED", data_categories: "", human_oversight: "", owner_name: "" },
  change: { system_id: "", change_kind: "MODEL_UPDATE", from_version: "", to_version: "", description: "", effective_on: "", testing_summary: "", evidence_id: "" },
  incident: { system_id: "", incident_kind: "WRONG_OUTPUT", severity: "LOW", description: "", occurred_on: "", discovered_on: "", harm: "", people_affected: "", evidence_id: "" },
  review: { cause: "", corrective_action: "" },
};
const ev = (f) => (clean(f.evidence_id) ? [clean(f.evidence_id)] : []);

export const systemPayload = (f) => body({ name: clean(f.name), description: clean(f.description), origin: f.origin, ...(clean(f.vendor_name) ? { vendor_name: clean(f.vendor_name) } : {}), intended_use: clean(f.intended_use),
  out_of_scope: clean(f.out_of_scope), risk_tier: f.risk_tier, ...(clean(f.data_categories) ? { data_categories: clean(f.data_categories) } : {}), ...(clean(f.human_oversight) ? { human_oversight: clean(f.human_oversight) } : {}), owner_name: clean(f.owner_name) },
  textProblem(f.name, "The system name", 5), textProblem(f.description, "What the system does", 10), f.origin !== "IN_HOUSE" ? textProblem(f.vendor_name, "The vendor or project name", 2) : "", textProblem(f.intended_use, "The intended use", 10),
  textProblem(f.out_of_scope, "The uses that are not allowed", 10), optionalText(f.data_categories, "The kinds of data", 3), f.risk_tier === "HIGH" ? textProblem(f.human_oversight, "How a person oversees it", 10) : optionalText(f.human_oversight, "How a person oversees it", 10),
  textProblem(f.owner_name, "The owner", 2));
export const changePayload = (f) => body({ system_id: f.system_id, change_kind: f.change_kind, from_version: clean(f.from_version), to_version: clean(f.to_version), description: clean(f.description), effective_on: clean(f.effective_on),
  testing_summary: clean(f.testing_summary), evidence_ids: ev(f) }, f.system_id ? "" : "Choose the AI system that changed.", textProblem(f.from_version, "The version before", 1), textProblem(f.to_version, "The version after", 1),
  clean(f.from_version).toLowerCase() === clean(f.to_version).toLowerCase() && clean(f.from_version) ? "The version after must differ from the version before." : "", textProblem(f.description, "What changed", 10),
  dateProblem(f.effective_on, "The date of the change"), textProblem(f.testing_summary, "How it was tested", 10));
export const incidentPayload = (f) => {
  const severe = f.severity === "HIGH" || f.severity === "CRITICAL";
  return body({ system_id: f.system_id, incident_kind: f.incident_kind, severity: f.severity, description: clean(f.description), occurred_on: clean(f.occurred_on), discovered_on: clean(f.discovered_on),
    ...(clean(f.harm) ? { harm: clean(f.harm) } : {}), ...(clean(f.people_affected) ? { people_affected: Number(clean(f.people_affected)) } : {}), evidence_ids: ev(f) },
  f.system_id ? "" : "Choose the AI system involved.", textProblem(f.description, "What happened", 10), dateProblem(f.occurred_on, "The date it happened"), dateProblem(f.discovered_on, "The date it was found"),
  isRealDate(clean(f.occurred_on)) && isRealDate(clean(f.discovered_on)) && clean(f.discovered_on) < clean(f.occurred_on) ? "It cannot have been found before it happened." : "",
  severe ? textProblem(f.harm, "The harm done", 10) : optionalText(f.harm, "The harm done", 10), clean(f.people_affected) ? wholeProblem(f.people_affected, "The number of people affected", 0, 1000000000) : "");
};
export const reviewPayload = (f) => body({ cause: clean(f.cause), corrective_action: clean(f.corrective_action) }, textProblem(f.cause, "The cause", 10), textProblem(f.corrective_action, "The corrective action", 20));
export const policyForm = (p) => ({ review_days: String(p.review_days), incident_review_days: String(p.incident_review_days) });
export function policyPayload(f) {
  const n = (v, lo, hi) => (/^\d{1,4}$/.test(clean(v)) && Number(v) >= lo && Number(v) <= hi ? Number(v) : null);
  const d = n(f.review_days, 30, 730), l = n(f.incident_review_days, 1, 60);
  if (d == null) return { problem: "The system review interval is a whole number of days from 30 to 730." };
  if (l == null) return { problem: "The incident review window is a whole number of days from 1 to 60." };
  return { body: { review_days: d, incident_review_days: l } };
}
export const minNote = { reject: 10, retire: 10, void: 10, review: 10 };

// ---- who sees which button ----
export const canDecideSystem = (s, role, me) => canApprove(role) && s.status === "PROPOSED" && s.proposed_by !== me;
export const canRetireSystem = (s, role) => canApprove(role) && s.status === "APPROVED" && !s.pending_changes && !s.open_incidents;
export const canReviewSystem = (s, role, me) => canApprove(role) && s.status === "APPROVED" && s.proposed_by !== me;
export const canRecordChange = (s, role) => canPrepare(role) && s.status === "APPROVED";
export const canDecideChange = (c, role, me) => canApprove(role) && c.status === "RECORDED" && c.recorded_by !== me;
export const canReviewIncident = (i, role, me) => canApprove(role) && i.status === "RECORDED" && i.recorded_by !== me;
/** Told to the person who could decide but recorded or proposed the thing themselves. */
export const ownWorkText = (what) => `You ${what}, so a different person must decide it.`;
export const useText = (s) => `Intended use: ${s.intended_use} Not allowed: ${s.out_of_scope}`;
