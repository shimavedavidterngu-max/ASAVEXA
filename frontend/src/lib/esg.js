import { PERMISSIONS, ROLE_PERMISSIONS } from "./permissions.js";
import { fmt, isRealDate, noteProblem, words } from "./treasury.js";

/**
 * ESG and carbon helpers (emission records worked out from typed activity data and typed factors; no factors are supplied and nothing is measured). No DOM, no network.
 * The server enforces every rule and does all the arithmetic. These check input early, word things, and hide buttons that could not work.
 */
export { fmt, isRealDate, noteProblem, words };
const has = (role, perm) => !!(ROLE_PERMISSIONS[role] && ROLE_PERMISSIONS[role].includes(perm));
export const canRead = (role) => has(role, PERMISSIONS.AUDIT_READ);
export const canPrepare = (role) => has(role, PERMISSIONS.ESG_PREPARE);
export const canApprove = (role) => has(role, PERMISSIONS.ESG_APPROVE);

export const TABS = [["overview", "Overview"], ["entries", "Emission records"], ["targets", "Targets"]];
export const SCOPE_TEXT = { SCOPE_1: "Scope 1", SCOPE_2: "Scope 2", SCOPE_3: "Scope 3", ALL: "All scopes" };
export const CATEGORY_TEXT = { FUEL: "Fuel", ELECTRICITY: "Electricity", HEATING_COOLING: "Heating or cooling", TRAVEL: "Travel", FREIGHT: "Freight", WASTE: "Waste", WATER: "Water", PURCHASED_GOODS: "Purchased goods", REFRIGERANTS: "Refrigerants", OTHER: "Other" };
export const STATUS = {
  PROPOSED: { tone: "warn", label: "Waiting for a decision" }, VERIFIED: { tone: "pass", label: "Verified" }, APPROVED: { tone: "pass", label: "Approved" }, REJECTED: { tone: "neutral", label: "Rejected" },
};
export const statusOf = (s) => STATUS[s] || { tone: "neutral", label: s ? words(s) : "—" };
export const ATTENTION_TONE = { ENTRIES_TO_VERIFY: "info", TARGETS_TO_DECIDE: "info", OLD_FACTORS: "warn" };
export const who = (id, me) => (!id ? "—" : id === me ? "You" : String(id).slice(0, 8));

const clean = (v) => String(v == null ? "" : v).trim();
const first = (...p) => p.find(Boolean) || "";
const dateProblem = (v, what) => (isRealDate(clean(v)) ? "" : `${what} must be a real date written YYYY-MM-DD.`);
const textProblem = (v, what, min) => (clean(v).length >= min ? "" : `${what} needs at least ${min} characters.`);
const nonZero = (t) => /[1-9]/.test(t);
const num = (v) => clean(v).replace(/,/g, "");
const numProblem = (v, what, ints, places, example) => {
  const t = clean(v);
  if (t.includes(",") && !/^\d{1,3}(,\d{3})+(\.\d+)?$/.test(t)) return `${what} must be a number such as ${example} (commas only between groups of three digits).`;
  if (!new RegExp(`^\\d{1,${ints}}(\\.\\d{1,${places}})?$`).test(num(v))) return `${what} must be a number such as ${example} (at most ${places} decimals).`;
  return nonZero(num(v)) ? "" : `${what} must be more than zero.`;
};
const yearProblem = (v, what, lo, hi) => { const t = clean(v); return /^\d{4}$/.test(t) && Number(t) >= lo && Number(t) <= hi ? "" : `${what} must be a four-digit year from ${lo} to ${hi}.`; };
const thisYear = () => new Date().getUTCFullYear();

export const EMPTY = {
  entry: { scope: "SCOPE_1", category: "FUEL", description: "", period_start: "", period_end: "", quantity: "", unit: "", factor: "", factor_source: "", factor_year: "" },
  target: { label: "", scope: "ALL", baseline_year: "", baseline_tonnes: "", reduction_pct: "", target_year: "" },
};

export function entryPayload(f) {
  const s = clean(f.period_start), e = clean(f.period_end);
  const p = first(textProblem(f.description, "The description", 5), dateProblem(s, "The start of the period"), dateProblem(e, "The end of the period"),
    isRealDate(s) && isRealDate(e) && e < s ? "The period cannot end before it starts." : "", isRealDate(s) && isRealDate(e) && s.slice(0, 4) !== e.slice(0, 4) ? "A period must fall within one calendar year. Enter a separate record for each year." : "",
    numProblem(f.quantity, "The quantity", 12, 4, "1250.5"), textProblem(f.unit, "The unit", 1), numProblem(f.factor, "The emission factor", 6, 6, "2.68"), textProblem(f.factor_source, "The source of the factor", 5),
    yearProblem(f.factor_year, "The year of the factor", 1990, thisYear() + 1));
  if (p) return { problem: p };
  return { body: { scope: f.scope, category: f.category, description: clean(f.description), period_start: s, period_end: e, quantity: num(f.quantity), unit: clean(f.unit), factor: num(f.factor), factor_source: clean(f.factor_source), factor_year: Number(clean(f.factor_year)) } };
}
export function targetPayload(f) {
  const by = Number(clean(f.baseline_year)), ty = Number(clean(f.target_year));
  const pct = clean(f.reduction_pct);
  const p = first(textProblem(f.label, "The label", 3), yearProblem(f.baseline_year, "The baseline year", 1990, thisYear()), yearProblem(f.target_year, "The target year", 1991, 2100),
    /^\d{4}$/.test(clean(f.baseline_year)) && /^\d{4}$/.test(clean(f.target_year)) && ty <= by ? "The target year must be after the baseline year." : "",
    numProblem(f.baseline_tonnes, "The baseline emissions in tonnes", 12, 3, "1250.500"), numProblem(f.reduction_pct, "The reduction in percent", 3, 2, "42.5"),
    /^\d{1,3}(\.\d{1,2})?$/.test(pct) && Number(pct) > 100 ? "The reduction cannot be more than 100 percent." : "");
  if (p) return { problem: p };
  return { body: { label: clean(f.label), scope: f.scope, baseline_year: by, baseline_tonnes: num(f.baseline_tonnes), reduction_pct: pct, target_year: ty } };
}
export const settingPayload = (v) => { const t = clean(v); return /^\d{1,2}$/.test(t) && Number(t) >= 1 && Number(t) <= 20 ? { body: { factor_max_age_years: Number(t) } } : { problem: "The factor age limit is a whole number of years from 1 to 20." }; };
export const minNote = { reject: 10 };

// ---- who sees which button ----
export const canDecide = (x, role, me) => canApprove(role) && x.status === "PROPOSED" && x.proposed_by !== me;
export const ownWorkText = "You proposed this, so a different person must decide it.";
