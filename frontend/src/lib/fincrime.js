import { PERMISSIONS, ROLE_PERMISSIONS } from "./permissions.js";
import { fmt, isRealDate, noteProblem, words } from "./treasury.js";

/**
 * Financial-crime casework helpers (records and checks; nothing is screened, monitored or filed). No DOM, no network.
 * The server decides everything that matters. These check input early, word things, and hide buttons that could not work.
 * Amounts are handled as TEXT. Nothing here adds, subtracts or compares figures; the server does all arithmetic with exact decimals.
 */
export { fmt, isRealDate, noteProblem, words };
const has = (role, perm) => !!(ROLE_PERMISSIONS[role] && ROLE_PERMISSIONS[role].includes(perm));
export const canRead = (role) => has(role, PERMISSIONS.FINCRIME_READ);
export const canPrepare = (role) => has(role, PERMISSIONS.FINCRIME_PREPARE);
export const canApprove = (role) => has(role, PERMISSIONS.FINCRIME_APPROVE);

export const TABS = [["overview", "Overview"], ["alerts", "Alerts"], ["cases", "Cases"]];
export const SOURCE_TEXT = { TRANSACTION_MONITORING: "Transaction monitoring", SCREENING_HIT: "Screening hit", STAFF_REPORT: "Staff report", EXTERNAL_TIP: "External tip", AUDIT_FINDING: "Audit finding", OTHER: "Other" };
export const SEVERITY_TEXT = { LOW: "Low", MEDIUM: "Medium", HIGH: "High" };
export const EVENT_TEXT = { TRANSACTION: "Transaction", CONTACT: "Contact", DOCUMENT: "Document", OBSERVATION: "Observation", OTHER: "Other" };
export const CHECK_TEXT = { SANCTIONS: "Sanctions list", PEP: "Politically exposed person", ADVERSE_MEDIA: "Adverse media", INTERNAL_LIST: "Internal list" };
export const SUBJECT_TEXT = { PERSON: "Person", ORGANISATION: "Organisation" };
export const RESULT_TEXT = { NO_MATCH: "No match", POSSIBLE_MATCH: "Possible match", CONFIRMED_MATCH: "Confirmed match" };
export const OUTCOME_TEXT = { NO_CONCERN: "No concern", CONCERN_RESOLVED: "Concern found and resolved", REFER_ONWARD: "Refer onward" };
export const RECOVERY_TEXT = { REPAID: "Repaid", INSURANCE: "Insurance", SEIZED_OR_FROZEN: "Seized or frozen", OTHER: "Other" };

export const STATUS = {
  NEW: { tone: "warn", label: "Not yet looked at" }, DISMISSED: { tone: "neutral", label: "Dismissed" }, IN_CASE: { tone: "info", label: "In a case" },
  OPEN: { tone: "info", label: "Open" }, DECISION_PROPOSED: { tone: "warn", label: "Outcome waiting for a decision" }, CLOSED: { tone: "pass", label: "Closed" },
  RECORDED: { tone: "warn", label: "Waiting for confirmation" }, CONFIRMED: { tone: "pass", label: "Confirmed" }, REJECTED: { tone: "fail", label: "Rejected" },
  LOW: { tone: "neutral", label: "Low" }, MEDIUM: { tone: "warn", label: "Medium" }, HIGH: { tone: "fail", label: "High" },
  NO_MATCH: { tone: "pass", label: "No match" }, POSSIBLE_MATCH: { tone: "warn", label: "Possible match" }, CONFIRMED_MATCH: { tone: "fail", label: "Confirmed match" },
};
export const statusOf = (s) => STATUS[s] || { tone: "neutral", label: s ? words(s) : "—" };
export const ATTENTION_TONE = { ALERTS_WAITING: "warn", CASES_NO_LEAD: "fail", DECISIONS_PENDING: "info", SCREENINGS_UNRESOLVED: "warn", RECOVERIES_TO_CONFIRM: "info", CASES_AGING: "warn" };

/** A person is shown as "You" or a short form of their id; the organisation's member list has no names. */
export const who = (id, me) => (!id ? "—" : id === me ? "You" : String(id).slice(0, 8));
/** People who could actually carry a case: active members whose role holds fincrime:prepare. */
export const leadChoices = (members, c) => (members || []).filter((m) => m.status === "ACTIVE" && has(m.role, PERMISSIONS.FINCRIME_PREPARE) && m.user_id !== c.lead && c.declarations && c.declarations[m.user_id] && c.declarations[m.user_id].status === "NONE");

const clean = (v) => String(v == null ? "" : v).trim();
const plain = (v) => clean(v).replace(/,/g, "");
const first = (...p) => p.find(Boolean) || "";
const body = (b, ...problems) => { const p = first(...problems); return p ? { problem: p } : { body: b }; };
const dateProblem = (v, what) => (isRealDate(clean(v)) ? "" : `${what} must be a real date written YYYY-MM-DD.`);
const currencyProblem = (v) => (/^[A-Za-z]{3}$/.test(clean(v)) ? "" : "The currency is a three-letter code such as NGN or USD.");
const textProblem = (v, what, min) => (clean(v).length >= min ? "" : `${what} needs at least ${min} characters.`);
/** A positive amount with at most two decimal places. */
export function amountProblem(v, what) {
  const t = plain(v);
  if (!t) return `${what} is required.`;
  if (!/^\d{1,13}(\.\d{1,2})?$/.test(t)) return `${what} must be a number with at most 2 decimal places.`;
  if (/^0+(\.0+)?$/.test(t)) return `${what} must be more than zero.`;
  return "";
}

export const EMPTY = {
  alert: { source: "STAFF_REPORT", summary: "", observed_on: "", amount: "", currency: "", evidence_id: "" },
  casef: { title: "", summary: "", severity: "MEDIUM", conflict: "no", conflict_note: "", alert_ids: [] },
  declare: { status: "NONE", note: "" },
  event: { occurred_on: "", kind: "OBSERVATION", text: "", evidence_id: "" },
  screening: { subject: "", subject_kind: "ORGANISATION", check: "SANCTIONS", list_name: "", screened_on: "", result: "NO_MATCH", note: "" },
  loss: { amount: "", currency: "", occurred_on: "", description: "", evidence_id: "" },
  recovery: { amount: "", currency: "", received_on: "", kind: "REPAID", note: "", evidence_id: "" },
  decision: { outcome: "CONCERN_RESOLVED", rationale: "", referral_to: "" },
  lead: { lead: "", reason: "" },
};

const ev = (f) => (clean(f.evidence_id) ? [clean(f.evidence_id)] : []);

export const alertPayload = (f) => body({ source: f.source, summary: clean(f.summary), observed_on: clean(f.observed_on), ...(clean(f.amount) ? { amount: plain(f.amount), currency: clean(f.currency).toUpperCase() } : {}), evidence_ids: ev(f) },
  textProblem(f.summary, "Say what was noticed:", 10).replace(":", ""), dateProblem(f.observed_on, "The date it was noticed"),
  clean(f.amount) ? first(amountProblem(f.amount, "The amount"), currencyProblem(f.currency)) : (clean(f.currency) ? "A currency needs an amount." : ""));
export const casePayload = (f) => body({ title: clean(f.title), summary: clean(f.summary), severity: f.severity, alert_ids: f.alert_ids || [], ...(f.conflict === "yes" ? { conflict: "CONFLICT", conflict_note: clean(f.conflict_note) } : {}) },
  textProblem(f.title, "The title", 5), textProblem(f.summary, "Say what the case is about; it", 20), f.conflict === "yes" ? textProblem(f.conflict_note, "Describe the conflict; it", 10) : "");
export const declarePayload = (f) => body({ status: f.status, ...(clean(f.note) ? { note: clean(f.note) } : {}) }, f.status === "CONFLICT" ? textProblem(f.note, "Describe the conflict; it", 10) : "");
export const eventPayload = (f) => body({ occurred_on: clean(f.occurred_on), kind: f.kind, text: clean(f.text), evidence_ids: ev(f) }, dateProblem(f.occurred_on, "The date it happened"), textProblem(f.text, "Say what happened; it", 5));
export const screeningPayload = (f) => body({ subject: clean(f.subject), subject_kind: f.subject_kind, check: f.check, list_name: clean(f.list_name), screened_on: clean(f.screened_on), result: f.result, note: clean(f.note) },
  textProblem(f.subject, "Who or what was screened;", 3).replace(";", ""), textProblem(f.list_name, "The list or source checked", 3), dateProblem(f.screened_on, "The date screened"), textProblem(f.note, "A note on the result", 5));
export const resolvePayload = (outcome, reason) => body({ outcome, reason: clean(reason) }, noteProblem(reason, "A reason", 10));
export const lossPayload = (f) => body({ amount: plain(f.amount), currency: clean(f.currency).toUpperCase(), occurred_on: clean(f.occurred_on), description: clean(f.description), evidence_ids: ev(f) },
  amountProblem(f.amount, "The amount"), currencyProblem(f.currency), dateProblem(f.occurred_on, "The date of the loss"), textProblem(f.description, "Say what was lost; it", 5));
export const recoveryPayload = (f) => body({ amount: plain(f.amount), currency: clean(f.currency).toUpperCase(), received_on: clean(f.received_on), kind: f.kind, note: clean(f.note), evidence_ids: ev(f) },
  amountProblem(f.amount, "The amount"), currencyProblem(f.currency), dateProblem(f.received_on, "The date recovered"), textProblem(f.note, "A note on the recovery", 5));
export const decisionPayload = (f) => body({ outcome: f.outcome, rationale: clean(f.rationale), ...(f.outcome === "REFER_ONWARD" ? { referral_to: clean(f.referral_to) } : {}) },
  textProblem(f.rationale, "The reasons for the outcome", 20), f.outcome === "REFER_ONWARD" ? textProblem(f.referral_to, "Who the referral is to", 3) : "");
export const leadPayload = (f) => body({ lead: f.lead, reason: clean(f.reason) }, f.lead ? "" : "Choose the new lead investigator.", textProblem(f.reason, "A reason", 5));
export const policyForm = (p) => ({ alert_sla_days: String(p.alert_sla_days), case_sla_days: String(p.case_sla_days) });
export function policyPayload(f) {
  const n = (v, lo, hi) => (/^\d{1,3}$/.test(clean(v)) && Number(v) >= lo && Number(v) <= hi ? Number(v) : null);
  const a = n(f.alert_sla_days, 0, 60), c = n(f.case_sla_days, 1, 365);
  if (a == null) return { problem: "The alert target is a whole number of days from 0 to 60." };
  if (c == null) return { problem: "The case target is a whole number of days from 1 to 365." };
  return { body: { alert_sla_days: a, case_sla_days: c } };
}
/** Minimum characters for a reason on each action (the server enforces the same). */
export const minNote = { dismiss: 10, reject: 10, reject_recovery: 10, reopen: 10 };

// ---- who sees which button ----
export const myDeclaration = (c, me) => (c.declarations && c.declarations[me]) || null;
export const isCleared = (c, me) => { const d = myDeclaration(c, me); return !!d && d.status === "NONE"; };
/** Anyone with the read permission may declare, until they have declared a conflict (a conflict is never withdrawn). */
export const canDeclare = (c, me) => { const d = myDeclaration(c, me); return !d || d.status === "NONE"; };
export const needsDeclaration = (c, me) => !myDeclaration(c, me);
export const hasConflict = (c, me) => { const d = myDeclaration(c, me); return !!d && d.status === "CONFLICT"; };
/** The lead works the case while it is not closed, once they have declared no conflict. */
export const canWork = (c, role, me) => canPrepare(role) && c.status !== "CLOSED" && c.lead === me && isCleared(c, me);
/** Common rule for anyone deciding something: not the lead, not the opener, declared no conflict, not closed. */
export const canDecideOn = (c, role, me) => canApprove(role) && c.status !== "CLOSED" && me !== c.lead && me !== c.opened_by && isCleared(c, me);
export const raisedLinkedAlert = (c, alerts, me) => (alerts || []).some((a) => (c.alert_ids || []).includes(a.id) && a.raised_by === me);
export const decisionMoves = (c, role, me, alerts) => {
  if (c.status !== "DECISION_PROPOSED" || !c.decision) return [];
  if (!canDecideOn(c, role, me) || me === c.decision.proposed_by || raisedLinkedAlert(c, alerts, me)) return [];
  return c.unresolved_screenings ? ["reject"] : ["approve", "reject"];
};
export const canPropose = (c, role, me) => canWork(c, role, me) && c.status === "OPEN";
export const screeningMoves = (c, s, role, me) => (s.result === "POSSIBLE_MATCH" && !s.resolution && me !== s.recorded_by && canDecideOn(c, role, me) ? ["false", "confirm"] : []);
export const recoveryMoves = (c, x, role, me) => (x.status === "RECORDED" && me !== x.recorded_by && canDecideOn(c, role, me) ? ["confirm", "reject"] : []);
export const canDismiss = (a, role, me) => canApprove(role) && a.status === "NEW" && a.raised_by !== me;
export const canReopen = (c, role, me) => canApprove(role) && c.status === "CLOSED" && isCleared(c, me);
export const canChangeLead = (c, role) => canApprove(role) && c.status !== "CLOSED";
export const waitingText = (c, role, me) => {
  if (c.status !== "DECISION_PROPOSED" || !canApprove(role)) return "";
  if (me === c.decision.proposed_by || me === c.lead) return "You proposed this outcome, so a different person must decide it.";
  if (me === c.opened_by) return "You opened this case, so a different person must decide it.";
  if (!isCleared(c, me)) return "Declare that you have no conflict of interest on this case before you decide it.";
  return "";
};
export const positionText = (p) => `Lost ${p.lost} ${p.currency}; recovered and confirmed ${p.recovered_confirmed}; waiting for confirmation ${p.recovered_unconfirmed}; still outstanding ${p.outstanding}.`;
export const headline = (c) => `${c.ref} · ${c.title}`;
