import { PERMISSIONS, ROLE_PERMISSIONS } from "./permissions.js";
import { fmt, isRealDate, noteProblem, words } from "./treasury.js";

/**
 * Planning and KPIs helpers (records and checks; nothing is calculated from the ledger and nothing is verified). No DOM, no network.
 * The server decides everything that matters. These check input early, word things, and hide buttons that could not work.
 * Values are handled as TEXT. Nothing here adds, subtracts or compares figures; the server does all arithmetic with exact decimals.
 */
export { fmt, isRealDate, noteProblem, words };
const has = (role, perm) => !!(ROLE_PERMISSIONS[role] && ROLE_PERMISSIONS[role].includes(perm));
export const canPrepare = (role) => has(role, PERMISSIONS.FPA_PREPARE);
export const canApprove = (role) => has(role, PERMISSIONS.FPA_APPROVE);

export const TABS = [["overview", "Overview"], ["kpis", "KPIs"], ["forecasts", "Forecasts"], ["accuracy", "Forecast accuracy"]];
export const UNIT_PLACES = { AMOUNT: 2, RATIO: 4, PERCENT: 2, COUNT: 0, DAYS: 0 };
export const UNIT_TEXT = { AMOUNT: "Amount of money", RATIO: "Ratio", PERCENT: "Percent", COUNT: "Count", DAYS: "Days" };
export const DIRECTION_TEXT = { HIGHER_BETTER: "Higher is better", LOWER_BETTER: "Lower is better" };
export const FREQUENCY_TEXT = { MONTHLY: "Monthly", QUARTERLY: "Quarterly", ANNUAL: "Annual" };
export const MIN_LEAD_CHOICES = [0, 7, 14, 30, 60, 90];

export const STATUS = {
  DRAFT: { tone: "warn", label: "Waiting for approval" }, ACTIVE: { tone: "pass", label: "Approved" }, RETIRED: { tone: "neutral", label: "Retired" },
  ON_TARGET: { tone: "pass", label: "On target" }, WATCH: { tone: "warn", label: "Close to target" }, OFF_TARGET: { tone: "fail", label: "Off target" }, NOT_MEASURED: { tone: "neutral", label: "Not measured yet" },
  RECORDED: { tone: "warn", label: "Waiting for review" }, REVIEWED: { tone: "pass", label: "Reviewed" }, REJECTED: { tone: "fail", label: "Rejected" }, SUPERSEDED: { tone: "neutral", label: "Replaced by a correction" },
  OPEN: { tone: "info", label: "Waiting for the actual" }, ACTUAL_RECORDED: { tone: "warn", label: "Actual waiting for confirmation" }, CONFIRMED: { tone: "pass", label: "Confirmed" }, WITHDRAWN: { tone: "neutral", label: "Withdrawn" },
};
export const statusOf = (s) => STATUS[s] || { tone: "neutral", label: s ? words(s) : "—" };
export const ATTENTION_TONE = { KPIS_PENDING: "warn", OWNERSHIP_PENDING: "warn", KPI_OVERDUE: "warn", KPI_OFF_TARGET: "fail", KPI_WATCH: "warn", READINGS_TO_REVIEW: "info", READINGS_UNTRACED: "info", ACTUALS_DUE: "warn", ACTUALS_TO_CONFIRM: "info", FORECAST_BIAS: "warn" };
export const DIRECTION_WORD = { OVER: "Too high", UNDER: "Too low", EXACT: "Exact" };

/** A person is shown as "You" or a short form of their id; the organisation's member list has no names. */
export const who = (id, me) => (!id ? "—" : id === me ? "You" : String(id).slice(0, 8));
/** People who could actually record a KPI's readings: active members whose role holds fpa:prepare. */
export const ownerChoices = (members) => (members || []).filter((m) => m.status === "ACTIVE" && has(m.role, PERMISSIONS.FPA_PREPARE));

const clean = (v) => String(v == null ? "" : v).trim();
const plain = (v) => clean(v).replace(/,/g, "");
const first = (...p) => p.find(Boolean) || "";
const body = (b, ...problems) => { const p = first(...problems); return p ? { problem: p } : { body: b }; };
const dateProblem = (v, what) => (isRealDate(clean(v)) ? "" : `${what} must be a real date written YYYY-MM-DD.`);
const currencyProblem = (v) => (/^[A-Za-z]{3}$/.test(clean(v)) ? "" : "The currency is a three-letter code such as NGN or USD.");
/** A signed number (a target or a value can be negative) with at most the unit's decimal places. */
export function valueProblem(v, what, unit) {
  const places = UNIT_PLACES[unit] == null ? 2 : UNIT_PLACES[unit], t = plain(v);
  if (!t) return `${what} is required.`;
  if (!new RegExp(`^-?\\d{1,13}${places ? `(\\.\\d{1,${places}})?` : ""}$`).test(t)) return places ? `${what} must be a number with at most ${places} decimal place${places === 1 ? "" : "s"}.` : `${what} must be a whole number.`;
  return "";
}

export const EMPTY = {
  kpi: { name: "", description: "", unit: "AMOUNT", currency: "", direction: "HIGHER_BETTER", frequency: "MONTHLY", owner: "", data_source: "", method: "", target: "", watch_pct: "", effective_from: "" },
  reading: { period_end: "", value: "", source_note: "", evidence_id: "", correction_note: "" },
  reassign: { owner: "", reason: "" },
  forecast: { metric: "", unit: "AMOUNT", currency: "", period_end: "", value: "", basis: "", kpi_id: "" },
  actual: { value: "", source_note: "", evidence_id: "" },
};

export const kpiPayload = (f) => body({ name: clean(f.name), description: clean(f.description), unit: f.unit, ...(f.unit === "AMOUNT" ? { currency: clean(f.currency).toUpperCase() } : {}), direction: f.direction, frequency: f.frequency, owner: f.owner,
  data_source: clean(f.data_source), method: clean(f.method), target: plain(f.target), ...(clean(f.watch_pct) ? { watch_pct: Number(f.watch_pct) } : {}), effective_from: clean(f.effective_from) },
  clean(f.name).length < 3 ? "Give the KPI a name." : "", clean(f.description).length < 5 ? "Say what it measures." : "", f.unit === "AMOUNT" ? currencyProblem(f.currency) : "", f.owner ? "" : "Choose the owner.",
  clean(f.data_source).length < 10 ? "Say where the number comes from (at least 10 characters)." : "", clean(f.method).length < 10 ? "Say how it is calculated (at least 10 characters)." : "",
  valueProblem(f.target, "The target", f.unit), clean(f.watch_pct) && !(/^\d{1,2}$/.test(clean(f.watch_pct)) && Number(f.watch_pct) <= 50) ? "The warning margin is a whole number from 0 to 50, or leave it empty to use the organisation's setting." : "",
  dateProblem(f.effective_from, "The date it starts"));

export const readingPayload = (f, unit) => body({ period_end: clean(f.period_end), value: plain(f.value), source_note: clean(f.source_note), evidence_ids: f.evidence_id ? [f.evidence_id] : [], ...(clean(f.correction_note) ? { correction_note: clean(f.correction_note) } : {}) },
  dateProblem(f.period_end, "The period end"), valueProblem(f.value, "The value", unit), clean(f.source_note).length < 10 ? "Say where the number came from (at least 10 characters)." : "",
  clean(f.correction_note) && clean(f.correction_note).length < 10 ? "The reason for the correction needs at least 10 characters." : "");

export const forecastPayload = (f) => body({ metric: clean(f.metric), unit: f.unit, ...(f.unit === "AMOUNT" ? { currency: clean(f.currency).toUpperCase() } : {}), period_end: clean(f.period_end), value: plain(f.value), basis: clean(f.basis), ...(f.kpi_id ? { kpi_id: f.kpi_id } : {}) },
  clean(f.metric).length < 3 ? "Name what is being forecast." : "", f.unit === "AMOUNT" ? currencyProblem(f.currency) : "", dateProblem(f.period_end, "The period the forecast is for"), valueProblem(f.value, "The forecast value", f.unit),
  clean(f.basis).length < 10 ? "Say how the forecast was made (at least 10 characters)." : "");

export const actualPayload = (f, unit) => body({ value: plain(f.value), source_note: clean(f.source_note), evidence_ids: f.evidence_id ? [f.evidence_id] : [] },
  valueProblem(f.value, "The actual value", unit), clean(f.source_note).length < 10 ? "Say where the actual came from (at least 10 characters)." : "");

export const reassignPayload = (f) => (f.owner ? (clean(f.reason).length < 5 ? { problem: "A reason is required (at least 5 characters)." } : { body: { owner: f.owner, reason: clean(f.reason) } }) : { problem: "Choose the new owner." });

export const policyForm = (p) => ({ watch_pct: String(p ? p.watch_pct : 10), grace_days: String(p ? p.grace_days : 15), accuracy_pct: String(p ? p.accuracy_pct : 10), min_items: String(p ? p.min_items : 3) });
export function policyPayload(f) {
  const rules = [["watch_pct", "The warning margin", 0, 50], ["grace_days", "The grace period", 0, 90], ["accuracy_pct", "The accuracy band", 0, 100], ["min_items", "The minimum number of forecasts", 1, 50]], out = {};
  for (const [k, name, lo, hi] of rules) {
    if (!/^\d{1,3}$/.test(clean(f[k])) || Number(f[k]) < lo || Number(f[k]) > hi) return { problem: `${name} is a whole number from ${lo} to ${hi}.` };
    out[k] = Number(f[k]);
  }
  return { body: out };
}

/** Which buttons a person can sensibly see. The server decides again. */
export function kpiMoves(k, me, role) {
  const out = [];
  if (k.status === "DRAFT" && canApprove(role) && k.created_by !== me && k.owner !== me) out.push("approve");
  if (k.status !== "RETIRED" && k.owner === me && !k.owner_accepted && canPrepare(role)) out.push("accept");
  if (k.status !== "RETIRED" && canApprove(role)) out.push("owner");
  if (k.status !== "RETIRED" && canApprove(role)) out.push("retire");
  return out;
}
export const canRecordReading = (k, me, role) => k.status === "ACTIVE" && k.owner === me && k.owner_accepted && canPrepare(role);
export const readingMoves = (r, me, role) => (r.status === "RECORDED" && canApprove(role) && r.recorded_by !== me ? ["review", "reject"] : []);
export function forecastMoves(f, me, role) {
  const out = [];
  if (f.status === "OPEN" && f.forecaster === me && canPrepare(role)) out.push("withdraw");
  if (f.status === "OPEN" && f.actual_due && f.forecaster !== me && canPrepare(role)) out.push("actual");
  if (f.status === "ACTUAL_RECORDED" && canApprove(role) && f.actual && f.actual.recorded_by !== me && f.forecaster !== me) out.push("confirm", "reject");
  return out;
}
export const MOVE_TEXT = { approve: "Approve", accept: "Accept ownership", owner: "Change owner", retire: "Retire", review: "Mark as reviewed", reject: "Reject", withdraw: "Withdraw", actual: "Record the actual", confirm: "Confirm the actual" };
export const minNote = { retire: 5, reject: 5, withdraw: 5 };

export const unitLabel = (x) => (x.unit === "AMOUNT" ? x.currency : UNIT_TEXT[x.unit] || x.unit);
export const waitingText = (k, me, role) => (k.status === "DRAFT" ? (canApprove(role) && k.owner === me ? "You are the owner, so a different approver must approve this target." : canApprove(role) && k.created_by === me ? "Waiting for a different approver." : "Waiting for an approver.") : "");
export const headline = (k) => (k.latest ? `${k.latest.value} for the period ending ${k.latest.period_end}` : "No reading yet");
export const shortfallText = (r) => (r.judgement === "ON_TARGET" ? "" : r.shortfall_pct == null ? "Short of the target (the target is zero, so no percentage)" : `Short of the target by ${r.shortfall_pct}% of the target`);
