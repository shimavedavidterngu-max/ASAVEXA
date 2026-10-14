import { PERMISSIONS, ROLE_PERMISSIONS } from "./permissions.js";
import { fmt, isRealDate, noteProblem, words } from "./treasury.js";

/**
 * Risk indicators and resilience helpers (records and checks; nothing is measured or connected). No DOM, no network.
 * The server does all arithmetic (ratings, recovery objectives, loss totals) with exact decimals. These check input early,
 * word things, and hide buttons that could not work. Amounts and readings are handled as TEXT.
 */
export { fmt, isRealDate, noteProblem, words };
const has = (role, perm) => !!(ROLE_PERMISSIONS[role] && ROLE_PERMISSIONS[role].includes(perm));
export const canRead = (role) => has(role, PERMISSIONS.AUDIT_READ);
export const canPrepare = (role) => has(role, PERMISSIONS.RESIL_PREPARE);
export const canApprove = (role) => has(role, PERMISSIONS.RESIL_APPROVE);

export const TABS = [["overview", "Overview"], ["kris", "Indicators"], ["losses", "Losses"], ["processes", "Processes"], ["drills", "Continuity tests"]];
export const DIRECTION_TEXT = { HIGHER_IS_WORSE: "Higher is worse", LOWER_IS_WORSE: "Lower is worse" };
export const LOSS_KIND_TEXT = { LOSS: "Loss (money lost)", NEAR_MISS: "Near miss (no money lost)" };
export const CATEGORY_TEXT = { PROCESS: "Process", PEOPLE: "People", SYSTEMS: "Systems", EXTERNAL: "External event", FRAUD: "Fraud", COMPLIANCE: "Compliance", OTHER: "Other" };
export const IMPACT_TEXT = { LOW: "Low", MEDIUM: "Medium", HIGH: "High" };
export const DRILL_TEXT = { TABLETOP: "Table-top walk-through", FAILOVER: "Failover", RESTORE: "Restore from backup", COMMUNICATION: "Communication", OTHER: "Other" };
export const STATUS = {
  PROPOSED: { tone: "warn", label: "Waiting for approval" }, ACTIVE: { tone: "info", label: "Active" }, REJECTED: { tone: "neutral", label: "Rejected" }, RETIRED: { tone: "neutral", label: "Retired" }, APPROVED: { tone: "pass", label: "Approved" },
  RECORDED: { tone: "warn", label: "Waiting for a different person" }, CONFIRMED: { tone: "pass", label: "Confirmed" }, REVIEWED: { tone: "pass", label: "Reviewed" }, VOIDED: { tone: "neutral", label: "Voided" },
  GREEN: { tone: "pass", label: "Green" }, AMBER: { tone: "warn", label: "Amber" }, RED: { tone: "fail", label: "Red" }, MET: { tone: "pass", label: "Objective met" }, NOT_MET: { tone: "fail", label: "Objective not met" },
  LOW: { tone: "neutral", label: "Low" }, MEDIUM: { tone: "warn", label: "Medium" }, HIGH: { tone: "fail", label: "High" },
};
export const statusOf = (s) => STATUS[s] || { tone: "neutral", label: s ? words(s) : "—" };
export const ATTENTION_TONE = { KRIS_RED: "fail", KRIS_AMBER: "warn", KRIS_STALE: "warn", READINGS_TO_CONFIRM: "info", PROPOSALS_TO_APPROVE: "info", LOSSES_REVIEW_OVERDUE: "warn", PROCESSES_NEVER_TESTED: "warn", PROCESSES_TEST_DUE: "warn", TESTS_NOT_MET: "fail", TESTS_TO_APPROVE: "info" };
/** A person is shown as "You" or a short form of their id. */
export const who = (id, me) => (!id ? "—" : id === me ? "You" : String(id).slice(0, 8));

const clean = (v) => String(v == null ? "" : v).trim();
const first = (...p) => p.find(Boolean) || "";
const body = (b, ...problems) => { const p = first(...problems); return p ? { problem: p } : { body: b }; };
const dateProblem = (v, what) => (isRealDate(clean(v)) ? "" : `${what} must be a real date written YYYY-MM-DD.`);
const textProblem = (v, what, min) => (clean(v).length >= min ? "" : `${what} needs at least ${min} characters.`);
const optionalText = (v, what, min) => (clean(v) && clean(v).length < min ? `${what} needs at least ${min} characters when given.` : "");
const decProblem = (v, what) => (/^-?\d{1,12}(\.\d{1,4})?$/.test(clean(v)) ? "" : `${what} must be a number with at most 4 decimal places.`);
const wholeProblem = (v, what, lo, hi) => (/^\d{1,4}$/.test(clean(v)) && Number(v) >= lo && Number(v) <= hi ? "" : `${what} must be a whole number from ${lo} to ${hi}.`);
/** A positive amount with at most two decimal places (commas allowed when typing). */
export function amountProblem(v, what) {
  const t = clean(v).replace(/,/g, "");
  if (!t) return `${what} is required.`;
  if (!/^\d{1,13}(\.\d{1,2})?$/.test(t)) return `${what} must be a number with at most 2 decimal places.`;
  if (/^0+(\.0+)?$/.test(t)) return `${what} must be more than zero.`;
  return "";
}

export const EMPTY = {
  kri: { name: "", description: "", unit: "", direction: "HIGHER_IS_WORSE", amber: "", red: "", owner_name: "", review_days: "30", risk_id: "" },
  reading: { value: "", as_of: "", note: "" },
  loss: { title: "", description: "", category: "PROCESS", kind: "LOSS", occurred_on: "", discovered_on: "", amount: "", currency: "", risk_id: "", evidence_id: "" },
  process: { name: "", description: "", owner_name: "", rto_hours: "", rpo_hours: "", impact_financial: "LOW", impact_legal: "LOW", impact_reputation: "LOW", dependencies: "" },
  drill: { process_id: "", drill_type: "FAILOVER", scenario: "", performed_on: "", achieved_recovery_hours: "", achieved_data_loss_hours: "", outcome: "", follow_up: "", evidence_id: "" },
};
const ev = (f) => (clean(f.evidence_id) ? [clean(f.evidence_id)] : []);

export const kriPayload = (f) => body({ name: clean(f.name), description: clean(f.description), unit: clean(f.unit), direction: f.direction, amber: clean(f.amber), red: clean(f.red), owner_name: clean(f.owner_name), review_days: Number(clean(f.review_days)),
  ...(clean(f.risk_id) ? { risk_id: clean(f.risk_id) } : {}) }, textProblem(f.name, "The indicator name", 5), textProblem(f.description, "What it measures", 10), textProblem(f.unit, "The unit", 1), decProblem(f.amber, "The amber threshold"), decProblem(f.red, "The red threshold"),
  textProblem(f.owner_name, "The owner", 2), wholeProblem(f.review_days, "How often a reading is expected (days)", 1, 365));
/** The note is required for an amber or red reading; the server rates it, so the page asks for a note only when the person says so. */
export const readingPayload = (f) => body({ value: clean(f.value), as_of: clean(f.as_of), ...(clean(f.note) ? { note: clean(f.note) } : {}) }, decProblem(f.value, "The reading"), dateProblem(f.as_of, "The date of the reading"), optionalText(f.note, "A note", 5));
export const lossPayload = (f) => {
  const near = f.kind === "NEAR_MISS";
  return body({ title: clean(f.title), description: clean(f.description), category: f.category, kind: f.kind, occurred_on: clean(f.occurred_on), discovered_on: clean(f.discovered_on),
    ...(near ? {} : { amount: clean(f.amount).replace(/,/g, ""), currency: clean(f.currency).toUpperCase() }), ...(clean(f.risk_id) ? { risk_id: clean(f.risk_id) } : {}), evidence_ids: ev(f) },
  textProblem(f.title, "The title", 5), textProblem(f.description, "What happened", 10), dateProblem(f.occurred_on, "The date it happened"), dateProblem(f.discovered_on, "The date it was found"),
  isRealDate(clean(f.occurred_on)) && isRealDate(clean(f.discovered_on)) && clean(f.discovered_on) < clean(f.occurred_on) ? "It cannot have been found before it happened." : "",
  near ? "" : first(amountProblem(f.amount, "The amount lost"), /^[A-Za-z]{3}$/.test(clean(f.currency)) ? "" : "The currency is a three-letter code such as NGN or USD."));
};
export const reviewPayload = (f) => body({ cause: clean(f.cause), lesson: clean(f.lesson) }, textProblem(f.cause, "The cause", 10), textProblem(f.lesson, "What was learned or changed", 20));
export const processPayload = (f) => body({ name: clean(f.name), description: clean(f.description), owner_name: clean(f.owner_name), rto_hours: Number(clean(f.rto_hours)), rpo_hours: Number(clean(f.rpo_hours)),
  impact_financial: f.impact_financial, impact_legal: f.impact_legal, impact_reputation: f.impact_reputation, ...(clean(f.dependencies) ? { dependencies: clean(f.dependencies) } : {}) },
  textProblem(f.name, "The process name", 5), textProblem(f.description, "What the process does", 10), textProblem(f.owner_name, "The owner", 2), wholeProblem(f.rto_hours, "The recovery time objective (hours)", 1, 8760),
  wholeProblem(f.rpo_hours, "The data loss tolerance (hours)", 0, 8760), optionalText(f.dependencies, "The dependencies", 5));
/** Whether a follow-up is required depends on the process objectives, which the server compares; the page asks for one when the person fills it in and the server refuses a miss without it. */
export const drillPayload = (f) => body({ process_id: f.process_id, drill_type: f.drill_type, scenario: clean(f.scenario), performed_on: clean(f.performed_on), achieved_recovery_hours: Number(clean(f.achieved_recovery_hours)),
  achieved_data_loss_hours: Number(clean(f.achieved_data_loss_hours)), outcome: clean(f.outcome), ...(clean(f.follow_up) ? { follow_up: clean(f.follow_up) } : {}), evidence_ids: ev(f) },
  f.process_id ? "" : "Choose the process that was tested.", textProblem(f.scenario, "The scenario", 10), dateProblem(f.performed_on, "The date of the test"), wholeProblem(f.achieved_recovery_hours, "The recovery time achieved (hours)", 0, 8760),
  wholeProblem(f.achieved_data_loss_hours, "The data lost (hours of work)", 0, 8760), textProblem(f.outcome, "What happened", 10), optionalText(f.follow_up, "What will be done about it", 10));
export const policyForm = (p) => ({ drill_days: String(p.drill_days), loss_review_days: String(p.loss_review_days) });
export function policyPayload(f) {
  const n = (v, lo, hi) => (/^\d{1,4}$/.test(clean(v)) && Number(v) >= lo && Number(v) <= hi ? Number(v) : null);
  const d = n(f.drill_days, 30, 1095), l = n(f.loss_review_days, 1, 90);
  if (d == null) return { problem: "The test interval is a whole number of days from 30 to 1095." };
  if (l == null) return { problem: "The loss review window is a whole number of days from 1 to 90." };
  return { body: { drill_days: d, loss_review_days: l } };
}
export const minNote = { reject: 10, retire: 10, void: 10, approveMiss: 10 };

// ---- who sees which button ----
export const canRecordReading = (k, role) => canPrepare(role) && k.status === "ACTIVE";
export const canDecideKri = (k, role, me) => canApprove(role) && k.status === "PROPOSED" && k.proposed_by !== me;
export const canRetireKri = (k, role) => canApprove(role) && k.status === "ACTIVE" && !k.pending_readings;
export const canConfirmReading = (rd, role, me) => canApprove(role) && rd.status === "RECORDED" && rd.recorded_by !== me;
export const canReviewLoss = (e, role, me) => canApprove(role) && e.status === "RECORDED" && e.recorded_by !== me;
export const canDecideProcess = (p, role, me) => canApprove(role) && p.status === "PROPOSED" && p.proposed_by !== me;
export const canRetireProcess = (p, role) => canApprove(role) && p.status === "APPROVED";
export const canTestProcess = (p, role) => canPrepare(role) && p.status === "APPROVED";
export const canDecideDrill = (t, role, me) => canApprove(role) && t.status === "RECORDED" && t.recorded_by !== me;
/** Told to the person who could decide but recorded or proposed the thing themselves. */
export const ownWorkText = (what) => `You ${what}, so a different person must decide it.`;
export const objectiveText = (t) => `Recovery ${t.achieved_recovery_hours} h against ${t.rto_hours} h; data lost ${t.achieved_data_loss_hours} h against ${t.rpo_hours} h.`;
export const thresholdText = (k) => `${DIRECTION_TEXT[k.direction] || k.direction}: amber at ${k.amber}, red at ${k.red} ${k.unit}.`;
