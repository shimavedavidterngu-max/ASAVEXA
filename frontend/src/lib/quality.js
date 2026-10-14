import { PERMISSIONS, ROLE_PERMISSIONS } from "./permissions.js";
import { fmt, isRealDate, noteProblem, words } from "./treasury.js";

/**
 * Quality management helpers (records and checks; nothing is inspected or measured). No DOM, no network.
 * The server enforces every rule. These check input early, word things, and hide buttons that could not work.
 */
export { fmt, isRealDate, noteProblem, words };
const has = (role, perm) => !!(ROLE_PERMISSIONS[role] && ROLE_PERMISSIONS[role].includes(perm));
export const canRead = (role) => has(role, PERMISSIONS.AUDIT_READ);
export const canPrepare = (role) => has(role, PERMISSIONS.QUAL_PREPARE);
export const canApprove = (role) => has(role, PERMISSIONS.QUAL_APPROVE);

export const TABS = [["overview", "Overview"], ["ncs", "Nonconformances"], ["actions", "Actions"]];
export const SOURCE_TEXT = { INTERNAL_AUDIT: "Internal audit", CUSTOMER_COMPLAINT: "Customer complaint", PROCESS_CHECK: "Process check", SUPPLIER: "Supplier", INCIDENT: "Incident", OTHER: "Other" };
export const SEVERITY_TEXT = { MINOR: "Minor", MAJOR: "Major", CRITICAL: "Critical" };
export const KIND_TEXT = { CORRECTIVE: "Corrective (fixes this problem)", PREVENTIVE: "Preventive (stops it happening elsewhere)" };
export const RESULT_TEXT = { EFFECTIVE: "Effective: the problem has not come back", NOT_EFFECTIVE: "Not effective: the problem is still there" };
export const STATUS = {
  RAISED: { tone: "warn", label: "Not analysed yet" }, ANALYSED: { tone: "info", label: "Analysed" }, CLOSED: { tone: "pass", label: "Closed" }, VOIDED: { tone: "neutral", label: "Voided" },
  OPEN: { tone: "warn", label: "Open" }, COMPLETED: { tone: "warn", label: "Waiting for an effectiveness check" }, VERIFIED: { tone: "pass", label: "Checked: effective" }, NOT_EFFECTIVE: { tone: "fail", label: "Checked: not effective" }, CANCELLED: { tone: "neutral", label: "Cancelled" },
  MINOR: { tone: "neutral", label: "Minor" }, MAJOR: { tone: "warn", label: "Major" }, CRITICAL: { tone: "fail", label: "Critical" },
};
export const statusOf = (s) => STATUS[s] || { tone: "neutral", label: s ? words(s) : "—" };
export const ATTENTION_TONE = { CRITICAL_OPEN: "fail", ACTIONS_OVERDUE: "warn", CHECKS_OVERDUE: "warn", NOT_EFFECTIVE: "fail", ACTIONS_TO_CHECK: "info", NCS_TO_ANALYSE: "info", NCS_WITHOUT_ACTIONS: "warn", NCS_READY_TO_CLOSE: "info" };
/** A person is shown as "You" or a short form of their id. */
export const who = (id, me) => (!id ? "—" : id === me ? "You" : String(id).slice(0, 8));

const clean = (v) => String(v == null ? "" : v).trim();
const first = (...p) => p.find(Boolean) || "";
const body = (b, ...problems) => { const p = first(...problems); return p ? { problem: p } : { body: b }; };
const dateProblem = (v, what) => (isRealDate(clean(v)) ? "" : `${what} must be a real date written YYYY-MM-DD.`);
const textProblem = (v, what, min) => (clean(v).length >= min ? "" : `${what} needs at least ${min} characters.`);

export const EMPTY = {
  nc: { title: "", description: "", source: "PROCESS_CHECK", severity: "MAJOR", area: "", occurred_on: "", discovered_on: "", evidence_id: "" },
  analyse: { root_cause: "", containment: "" },
  action: { nc_id: "", kind: "CORRECTIVE", description: "", owner_name: "", due_on: "" },
  complete: { completed_on: "", note: "", evidence_id: "" },
  verify: { result: "EFFECTIVE", note: "" },
  close: { note: "", no_action_reason: "" },
};
const ev = (f) => (clean(f.evidence_id) ? [clean(f.evidence_id)] : []);

export const ncPayload = (f) => body({ title: clean(f.title), description: clean(f.description), source: f.source, severity: f.severity, area: clean(f.area), occurred_on: clean(f.occurred_on), discovered_on: clean(f.discovered_on), evidence_ids: ev(f) },
  textProblem(f.title, "The title", 5), textProblem(f.description, "What was found", 10), textProblem(f.area, "The area or process", 2), dateProblem(f.occurred_on, "The date it happened"), dateProblem(f.discovered_on, "The date it was found"),
  isRealDate(clean(f.occurred_on)) && isRealDate(clean(f.discovered_on)) && clean(f.discovered_on) < clean(f.occurred_on) ? "It cannot have been found before it happened." : "");
export const analysePayload = (f) => body({ root_cause: clean(f.root_cause), containment: clean(f.containment) }, textProblem(f.root_cause, "The root cause", 20), textProblem(f.containment, "What was done straight away to contain it", 10));
export const actionPayload = (f) => body({ nc_id: f.nc_id, kind: f.kind, description: clean(f.description), owner_name: clean(f.owner_name), due_on: clean(f.due_on) },
  f.nc_id ? "" : "Choose the nonconformance this action is for.", textProblem(f.description, "The action", 10), textProblem(f.owner_name, "The owner", 2), dateProblem(f.due_on, "The due date"));
export const completePayload = (f) => body({ completed_on: clean(f.completed_on), note: clean(f.note), evidence_ids: ev(f) }, dateProblem(f.completed_on, "The date it was completed"), textProblem(f.note, "What was done", 10));
export const verifyPayload = (f) => body({ result: f.result, note: clean(f.note) }, textProblem(f.note, "The effectiveness check", 20));
export const closePayload = (f) => body({ note: clean(f.note), ...(clean(f.no_action_reason) ? { no_action_reason: clean(f.no_action_reason) } : {}) }, textProblem(f.note, "A closing note", 10),
  clean(f.no_action_reason) && clean(f.no_action_reason).length < 20 ? "The reason no action is needed needs at least 20 characters when given." : "");
export const policyForm = (p) => ({ verify_days: String(p.verify_days) });
export function policyPayload(f) {
  const t = clean(f.verify_days);
  if (!(/^\d{1,3}$/.test(t) && Number(t) >= 7 && Number(t) <= 180)) return { problem: "The days allowed for an effectiveness check is a whole number from 7 to 180." };
  return { body: { verify_days: Number(t) } };
}
export const minNote = { cancel: 10, void: 10 };

// ---- who sees which button ----
export const canAnalyse = (n, role) => canPrepare(role) && n.status === "RAISED";
export const canAddAction = (n, role) => canPrepare(role) && n.status === "ANALYSED";
export const canVoid = (n, role, me) => canApprove(role) && n.status === "RAISED" && n.raised_by !== me;
export const canClose = (n, role, me) => canApprove(role) && n.status === "ANALYSED" && n.raised_by !== me;
export const canComplete = (a, role) => canPrepare(role) && a.status === "OPEN";
export const canVerify = (a, role, me) => canApprove(role) && a.status === "COMPLETED" && a.completed_by !== me;
export const canCancel = (a, role) => canApprove(role) && a.status === "OPEN";
/** Told to the person who could decide but did the work themselves. */
export const ownWorkText = (what) => `You ${what}, so a different person must decide it.`;
export const dueText = (a) => `Due ${a.due_on}${a.overdue ? " (overdue)" : ""}`;
