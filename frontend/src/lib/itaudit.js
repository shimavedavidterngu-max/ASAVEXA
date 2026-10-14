import { PERMISSIONS, ROLE_PERMISSIONS } from "./permissions.js";
import { fmt, isRealDate, noteProblem, words } from "./treasury.js";

/**
 * IT audit helpers (records and evidence; nothing is connected to, scanned or tested). No DOM, no network.
 * The server decides everything that matters. These check input early, word things, and hide buttons that could not work.
 */
export { fmt, isRealDate, noteProblem, words };
const has = (role, perm) => !!(ROLE_PERMISSIONS[role] && ROLE_PERMISSIONS[role].includes(perm));
export const canRead = (role) => has(role, PERMISSIONS.AUDIT_READ);
export const canPrepare = (role) => has(role, PERMISSIONS.ITAUDIT_PREPARE);
export const canApprove = (role) => has(role, PERMISSIONS.ITAUDIT_APPROVE);

export const TABS = [["overview", "Overview"], ["changes", "Changes"], ["controls", "Controls"], ["tests", "Tests"]];
export const CHANGE_TEXT = { STANDARD: "Standard (pre-approved routine)", NORMAL: "Normal", EMERGENCY: "Emergency" };
export const RISK_TEXT = { LOW: "Low", MEDIUM: "Medium", HIGH: "High" };
export const CONTROL_TYPE_TEXT = { INPUT_VALIDATION: "Input validation", ACCESS: "Access", CALCULATION: "Calculation", INTERFACE: "Interface", SEGREGATION_OF_DUTIES: "Segregation of duties", REPORTING: "Reporting", OTHER: "Other" };
export const FREQUENCY_TEXT = { CONTINUOUS: "Continuous", DAILY: "Daily", WEEKLY: "Weekly", MONTHLY: "Monthly", ANNUAL: "Annual", EVENT_DRIVEN: "When an event happens" };
export const RESULT_TEXT = { NO_EXCEPTION: "No exception", EXCEPTION: "Exception" };
export const CASE_RESULT_TEXT = { PASS: "Passed", FAIL: "Failed" };
export const FLAG_TEXT = {
  NO_APPROVAL: "No approval recorded", APPROVED_AFTER_GO_LIVE: "Approved after go-live", EMERGENCY_RATIFIED_LATE: "Emergency approval too late", SELF_APPROVED: "Approved by the person who asked",
  NO_TESTING_EVIDENCE: "No testing evidence", NO_ROLLBACK_PLAN: "No rollback plan",
};
export const STATUS = {
  RECORDED: { tone: "info", label: "Recorded" }, VOIDED: { tone: "neutral", label: "Voided" }, ACTIVE: { tone: "info", label: "Active" }, RETIRED: { tone: "neutral", label: "Retired" },
  DRAFT: { tone: "warn", label: "Being worked on" }, WITHDRAWN: { tone: "neutral", label: "Withdrawn" }, SUBMITTED: { tone: "info", label: "Waiting for approval" }, APPROVED: { tone: "pass", label: "Approved" },
  WITHIN_TOLERANCE: { tone: "pass", label: "Within tolerance" }, ABOVE_TOLERANCE: { tone: "fail", label: "Above tolerance" },
  NO_EXCEPTION: { tone: "pass", label: "No exception" }, EXCEPTION: { tone: "fail", label: "Exception" }, PASS: { tone: "pass", label: "Passed" }, FAIL: { tone: "fail", label: "Failed" },
  LOW: { tone: "neutral", label: "Low" }, MEDIUM: { tone: "warn", label: "Medium" }, HIGH: { tone: "fail", label: "High" },
};
export const statusOf = (s) => STATUS[s] || { tone: "neutral", label: s ? words(s) : "—" };
export const ATTENTION_TONE = { CHANGES_FLAGGED_UNTESTED: "warn", EMERGENCY_CHANGES_FLAGGED: "warn", TESTS_TO_APPROVE: "info", TESTS_ABOVE_TOLERANCE: "fail", CONTROLS_NEVER_TESTED: "warn", CONTROLS_RETEST_DUE: "warn" };

/** A person is shown as "You" or a short form of their id. */
export const who = (id, me) => (!id ? "—" : id === me ? "You" : String(id).slice(0, 8));

const clean = (v) => String(v == null ? "" : v).trim();
const first = (...p) => p.find(Boolean) || "";
const body = (b, ...problems) => { const p = first(...problems); return p ? { problem: p } : { body: b }; };
const dateProblem = (v, what) => (isRealDate(clean(v)) ? "" : `${what} must be a real date written YYYY-MM-DD.`);
const textProblem = (v, what, min) => (clean(v).length >= min ? "" : `${what} needs at least ${min} characters.`);
const optionalText = (v, what, min) => (clean(v) && clean(v).length < min ? `${what} needs at least ${min} characters when given.` : "");
const wholeProblem = (v, what, lo, hi) => (/^\d{1,4}$/.test(clean(v)) && Number(v) >= lo && Number(v) <= hi ? "" : `${what} must be a whole number from ${lo} to ${hi}.`);

export const EMPTY = {
  change: { system: "", asset_id: "", title: "", description: "", change_type: "NORMAL", risk: "LOW", requested_by: "", approved_by_name: "", approved_on: "", ticket_ref: "", implemented_on: "", testing_evidence: "", rollback_plan: "", evidence_id: "" },
  control: { system: "", asset_id: "", name: "", control_type: "INPUT_VALIDATION", description: "", expected_result: "", frequency: "CONTINUOUS", tolerable: "0" },
  ptest: { title: "", system: "", period_from: "", period_to: "", sample_size: "5", seed: "", tolerable: "0" },
  ctest: { title: "", control_id: "" },
  case: { description: "", expected: "", actual: "", result: "PASS", note: "", performed_on: "", evidence_id: "" },
};

const ev = (f) => (clean(f.evidence_id) ? [clean(f.evidence_id)] : []);
export const changePayload = (f) => {
  const both = (clean(f.approved_by_name) && !clean(f.approved_on)) || (!clean(f.approved_by_name) && clean(f.approved_on));
  return body({
    system: clean(f.system), ...(clean(f.asset_id) ? { asset_id: clean(f.asset_id) } : {}), title: clean(f.title), description: clean(f.description), change_type: f.change_type, risk: f.risk, requested_by: clean(f.requested_by),
    approved_by_name: clean(f.approved_by_name), approved_on: clean(f.approved_on), ticket_ref: clean(f.ticket_ref), implemented_on: clean(f.implemented_on), testing_evidence: clean(f.testing_evidence), rollback_plan: clean(f.rollback_plan), evidence_ids: ev(f),
  }, textProblem(f.system, "The system", 2), textProblem(f.title, "The change title", 5), textProblem(f.description, "What was changed", 10), textProblem(f.requested_by, "Who asked for the change", 2), textProblem(f.ticket_ref, "The ticket or change number", 2),
  both ? "Give both who approved the change and when, or neither." : "", clean(f.approved_on) ? dateProblem(f.approved_on, "The approval date") : "", optionalText(f.approved_by_name, "Who approved it", 2), dateProblem(f.implemented_on, "The go-live date"),
  optionalText(f.testing_evidence, "The testing evidence", 10), optionalText(f.rollback_plan, "The rollback plan", 10));
};
export const controlPayload = (f) => body({
  system: clean(f.system), ...(clean(f.asset_id) ? { asset_id: clean(f.asset_id) } : {}), name: clean(f.name), control_type: f.control_type, description: clean(f.description), expected_result: clean(f.expected_result), frequency: f.frequency, tolerable: Number(clean(f.tolerable) || 0),
}, textProblem(f.system, "The system", 2), textProblem(f.name, "The control name", 5), textProblem(f.description, "What the control does", 10), textProblem(f.expected_result, "The expected result", 5), wholeProblem(clean(f.tolerable) || "0", "The tolerable number of exceptions", 0, 20));
export const ptestPayload = (f) => body({
  title: clean(f.title), ...(clean(f.system) ? { system: clean(f.system) } : {}), period_from: clean(f.period_from), period_to: clean(f.period_to), sample_size: Number(clean(f.sample_size)), seed: clean(f.seed), tolerable: Number(clean(f.tolerable) || 0),
}, textProblem(f.title, "The test title", 5), dateProblem(f.period_from, "The period start"), dateProblem(f.period_to, "The period end"),
isRealDate(clean(f.period_from)) && isRealDate(clean(f.period_to)) && clean(f.period_to) < clean(f.period_from) ? "The period cannot end before it starts." : "",
wholeProblem(f.sample_size, "The sample size", 1, 100), textProblem(f.seed, "The seed", 3), wholeProblem(clean(f.tolerable) || "0", "The tolerable number of exceptions", 0, 20), optionalText(f.system, "The system", 2));
export const ctestPayload = (f) => body({ title: clean(f.title), control_id: f.control_id }, textProblem(f.title, "The test title", 5), f.control_id ? "" : "Choose the control to test.");
export const casePayload = (f) => body({ description: clean(f.description), expected: clean(f.expected), actual: clean(f.actual), result: f.result, ...(clean(f.note) ? { note: clean(f.note) } : {}), performed_on: clean(f.performed_on), evidence_ids: ev(f) },
  textProblem(f.description, "What was tried", 10), textProblem(f.expected, "The expected result", 5), textProblem(f.actual, "The actual result", 3), dateProblem(f.performed_on, "The date performed"),
  f.result === "FAIL" ? textProblem(f.note, "A note on the failure", 10) : optionalText(f.note, "A note", 5));
/** A sampled change is concluded with a result and a note. A flagged item called "no exception" needs a real explanation. */
export function itemPayload(result, note, flagged) {
  const n = clean(note);
  if (result === "NO_EXCEPTION" && flagged) return n.length >= 20 ? { body: { result, note: n } } : { problem: "A flagged change can only be called 'no exception' with an explanation of at least 20 characters." };
  if (result === "EXCEPTION") return n.length >= 10 ? { body: { result, note: n } } : { problem: "An exception needs a note of at least 10 characters." };
  return n && n.length < 5 ? { problem: "A note needs at least 5 characters when given." } : { body: { result, ...(n ? { note: n } : {}) } };
}
export const policyForm = (p) => ({ emergency_ratify_days: String(p.emergency_ratify_days), retest_days: String(p.retest_days) });
export function policyPayload(f) {
  const n = (v, lo, hi) => (/^\d{1,4}$/.test(clean(v)) && Number(v) >= lo && Number(v) <= hi ? Number(v) : null);
  const e = n(f.emergency_ratify_days, 0, 60), r = n(f.retest_days, 30, 1095);
  if (e == null) return { problem: "The emergency approval window is a whole number of days from 0 to 60." };
  if (r == null) return { problem: "The retest interval is a whole number of days from 30 to 1095." };
  return { body: { emergency_ratify_days: e, retest_days: r } };
}
export const minNote = { void: 10, retire: 10, reject: 10, approve: 10, withdraw: 10 };

// ---- who sees which button ----
export const canVoid = (c, role, me) => canApprove(role) && c.status === "RECORDED" && c.recorded_by !== me;
export const canRetire = (ct, role) => canApprove(role) && ct.status === "ACTIVE";
export const canTestControl = (ct, role, me) => canPrepare(role) && ct.status === "ACTIVE" && ct.created_by !== me;
export const mineToWork = (t, role, me) => canPrepare(role) && t.status === "DRAFT" && t.prepared_by === me;
export const canConclude = (t, it, role, me) => mineToWork(t, role, me) && t.kind === "CHANGE" && it.snapshot.recorded_by !== me;
export const canAddCase = (t, role, me) => mineToWork(t, role, me) && t.kind === "CONTROL";
export const canSubmit = (t, role, me) => mineToWork(t, role, me) && (t.kind === "CHANGE" ? t.items.length > 0 && t.items.every((i) => i.result) : t.cases.length > 0);
export const testBlockers = (t, role, me) => (mineToWork(t, role, me) && !canSubmit(t, role, me) ? (t.kind === "CHANGE" ? `${t.items.filter((i) => !i.result).length} sampled change(s) still need a conclusion.` : "Record at least one test case before submitting.") : "");
export const approveMoves = (t, role, me) => {
  if (t.status !== "SUBMITTED" || !canApprove(role) || me === t.prepared_by) return [];
  if (t.kind === "CHANGE" ? t.items.some((i) => i.snapshot.recorded_by === me) : t.control_created_by === me) return [];
  return ["approve", "reject"];
};
export const needsApprovalNote = (t) => t.exceptions > 0 || t.overrides > 0;
export const waitingText = (t, role, me) => {
  if (t.status !== "SUBMITTED" || !canApprove(role)) return "";
  if (me === t.prepared_by) return "You carried out this test, so a different person must approve it.";
  if (t.kind === "CHANGE" && t.items.some((i) => i.snapshot.recorded_by === me)) return "You recorded one of the sampled changes, so a different person must approve this test.";
  if (t.kind === "CONTROL" && t.control_created_by === me) return "You defined this control, so a different person must approve its test.";
  return "";
};
export const toleranceText = (t) => `${t.exceptions} exception(s) found; ${t.tolerable} tolerable.`;
export const headline = (t) => `${t.ref} · ${t.title}`;
