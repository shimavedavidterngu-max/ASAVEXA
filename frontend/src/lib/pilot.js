/** Pure helpers for the Real Pilot page: how results are described, and the request bodies. No DOM, no network. */

export const STATUS_TONE = { MET: "pass", NOT_MET: "fail", INSUFFICIENT_DATA: "warn" };
export const STATUS_TEXT = { MET: "Target met", NOT_MET: "Target not met", INSUFFICIENT_DATA: "Not enough data yet" };
export const SOURCE_TEXT = { MEASURED: "Measured by the system", REPORTED: "Reported by people" };
export const PILOT_STATUS_TEXT = { PLANNING: "Planning", ACTIVE: "Active", COMPLETED: "Completed" };
export const KIND_TEXT = {
  ONBOARDING: "Onboarding", AUDIT_PREP: "Audit preparation", REPORT: "Producing a report", MONTH_END: "Month-end", RECONCILIATION: "Reconciliation", OTHER: "Something else",
  USER_ERROR: "I made a mistake", CONFUSION: "I was confused", BUG: "Something broke", MISSING_FEATURE: "Something is missing", DATA_PROBLEM: "A problem with the data",
  LENDER: "A lender", TAX_AUTHORITY: "A tax authority", AUDITOR: "An auditor", INVESTOR: "An investor", REGULATOR: "A regulator", INTERNAL: "Internal use",
  HELPFUL: "It helped", PARTLY: "It partly helped", NOT_HELPFUL: "It did not help", LOW: "Low", MEDIUM: "Medium", HIGH: "High",
};
export const kindText = (k) => KIND_TEXT[k] || (k ? String(k).replace(/_/g, " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase()) : "—");

export const SURVEY_QUESTIONS = [
  ["overall", "Overall, how satisfied are you with ASAVEXA?", "1 = very unhappy, 5 = very happy", true, 1, 5],
  ["ease", "How easy is it to use?", "1 = very hard, 5 = very easy", true, 1, 5],
  ["trust", "How much do you trust the figures and records it shows?", "1 = not at all, 5 = completely", true, 1, 5],
  ["recommend", "How likely are you to recommend it to a colleague?", "0 = never, 10 = definitely", true, 0, 10],
  ["time_saving", "Does it save you time?", "1 = costs me time, 5 = saves a lot of time", false, 1, 5],
  ["passport_useful", "How useful was the Financial Passport when you used it?", "1 = useless, 5 = very useful. Leave blank if you have not used it.", false, 1, 5],
];

export const emptyPilotForm = () => ({ name: "", start_date: "", end_date: "", notes: "" });
export const emptyClientForm = () => ({ client_org_id: "", label: "", consent_reference: "", kickoff: "", audit_prep_minutes: "", report_minutes: "" });
export const today = (now = new Date()) => now.toISOString().slice(0, 10);

const whole = (v) => { const t = String(v == null ? "" : v).trim(); return /^\d+$/.test(t) ? parseInt(t, 10) : t === "" ? null : NaN; };

export function pilotBody(f) {
  const b = { name: (f.name || "").trim(), start_date: (f.start_date || "").trim(), notes: (f.notes || "").trim() };
  if ((f.end_date || "").trim()) b.end_date = f.end_date.trim();
  return b;
}

export function clientBody(f) {
  const b = { client_org_id: f.client_org_id, label: (f.label || "").trim(), consent_reference: (f.consent_reference || "").trim() };
  if ((f.kickoff || "").trim()) b.kickoff = f.kickoff.trim();
  const baseline = {};
  for (const k of ["audit_prep_minutes", "report_minutes"]) { const n = whole(f[k]); if (n !== null) baseline[k] = n; }
  if (Object.keys(baseline).length) b.baseline = baseline;
  return b;
}

/** Returns an error sentence, or null when the form is good enough to send. The server checks everything again. */
export function clientFormProblem(f) {
  if (!f.client_org_id) return "Choose the client organisation.";
  if (!(f.label || "").trim()) return "Give the client a short name.";
  if ((f.consent_reference || "").trim().length < 3) return "Write where the client's written consent is kept (for example a letter's date or filing reference).";
  for (const k of ["audit_prep_minutes", "report_minutes"]) if (Number.isNaN(whole(f[k]))) return "Baseline times must be whole numbers of minutes.";
  return null;
}

export function timeBody(f, isFirm) {
  const b = { kind: f.kind, minutes: whole(f.minutes), performed_on: (f.performed_on || "").trim(), note: (f.note || "").trim() };
  if (isFirm) b.client_org_id = f.client_org_id;
  const base = whole(f.baseline_minutes); if (base !== null) b.baseline_minutes = base;
  return b;
}

export function issueBody(f, isFirm) {
  const b = { kind: f.kind, severity: f.severity || "LOW", text: (f.text || "").trim() };
  if (isFirm) b.client_org_id = f.client_org_id;
  return b;
}

export function passportUseBody(f, isFirm) {
  const b = { purpose: f.purpose, outcome: f.outcome, note: (f.note || "").trim() };
  if (isFirm) b.client_org_id = f.client_org_id;
  const m = whole(f.saved_minutes); if (m !== null) b.saved_minutes = m;
  return b;
}

/** Only answered questions are sent; a question left blank is "not answered", never zero. */
export function surveyBody(f) {
  const scores = {};
  for (const q of SURVEY_QUESTIONS) { const k = q[0]; const n = whole((f.scores || {})[k]); if (n !== null) scores[k] = n; }
  return { round: (f.round || "GENERAL").trim() || "GENERAL", scores, comment: (f.comment || "").trim() };
}

export function surveyProblem(f) {
  for (const [k, label, , required, lo, hi] of SURVEY_QUESTIONS) {
    const n = whole((f.scores || {})[k]);
    if (n === null) { if (required) return `Please answer: ${label}`; continue; }
    if (Number.isNaN(n) || n < lo || n > hi) return `Answers to "${label}" must be a whole number from ${lo} to ${hi}.`;
  }
  return null;
}

/** Joins a number to its unit phrase: "12.5 days", "50% time saved against the baseline", or "—" when there is no value (never "0" for missing). */
const withUnit = (num, unit) => (!unit ? `${num}` : unit.startsWith("%") ? `${num}${unit}` : `${num} ${unit}`);
export function valueText(m) {
  if (m == null || m.value == null) return "—";
  return withUnit(Number.isInteger(m.value) ? m.value : Math.round(m.value * 10) / 10, m.unit);
}
export const targetText = (m) => `${m.direction === "<=" ? "at most" : "at least"} ${withUnit(m.target, m.unit)}`;

export function tally(measures) {
  const t = { MET: 0, NOT_MET: 0, INSUFFICIENT_DATA: 0 };
  for (const m of measures || []) t[m.status] = (t[m.status] || 0) + 1;
  return t;
}

/** Which tabs a person sees. A client organisation never sees the firm's other clients, targets or results. */
export function tabsFor(me) {
  const m = me && me.membership;
  if (m && m.role === "CLIENT") return ["log", "survey", "about"];
  if (me && me.can_manage) return ["dashboard", "clients", "log", "survey", "setup", "report"];
  return ["log", "survey"];
}

export const TAB_LABEL = { dashboard: "Results", clients: "Clients", log: "Record", survey: "Survey", setup: "Set-up", report: "Snapshots & report", about: "About" };

export function download(name, text, type = "text/markdown") {
  const blob = new Blob([text], { type });
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
