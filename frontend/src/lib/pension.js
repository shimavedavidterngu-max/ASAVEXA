import { PERMISSIONS } from "./permissions.js";
import { has, canRead, clean, first, dateProblem, textProblem, amt, amountProblem, wholeProblem, currencyProblem, mkStatus, fmt, isRealDate, noteProblem, words } from "./wsCommon.js";

/** Pension and fiduciary helpers (schemes with contributions, funding valuations, a fiduciary calendar and a conflict register; no member data, no pension law). No DOM, no network. The server does all the arithmetic. */
export { canRead, fmt, isRealDate, noteProblem, words };
export const canPrepare = (role) => has(role, PERMISSIONS.PEN_PREPARE);
export const canApprove = (role) => has(role, PERMISSIONS.PEN_APPROVE);
export const TABS = [["overview", "Overview"], ["schemes", "Schemes"]];
export const TYPES = ["DEFINED_BENEFIT", "DEFINED_CONTRIBUTION", "HYBRID", "OTHER"];
export const statusOf = mkStatus({
  PROPOSED: { tone: "warn", label: "Waiting for a decision" }, APPROVED: { tone: "pass", label: "Open" }, REJECTED: { tone: "neutral", label: "Rejected" }, CLOSED: { tone: "neutral", label: "Closed" }, CONFIRMED: { tone: "pass", label: "Confirmed" },
  OPEN: { tone: "info", label: "Open" }, DONE: { tone: "warn", label: "Done, waiting for confirmation" }, SURPLUS: { tone: "pass", label: "Surplus" }, DEFICIT: { tone: "warn", label: "Deficit" }, BALANCED: { tone: "pass", label: "Balanced" },
});
export const ATTENTION_TONE = { SCHEMES_TO_APPROVE: "info", ITEMS_TO_DECIDE: "info", MISSING_CONTRIBUTIONS: "warn", LATE_CONTRIBUTIONS: "warn", BELOW_FUNDING_FLOOR: "warn", VALUATIONS_STALE: "warn", NO_VALUATION: "info", OBLIGATIONS_OVERDUE: "warn", OBLIGATIONS_DUE_SOON: "info" };
export const EMPTY = {
  scheme: { name: "", scheme_ref: "", currency: "", scheme_type: "DEFINED_CONTRIBUTION", start_period: "", due_day: "", description: "" },
  contribution: { period: "", employer_amount: "", employee_amount: "", paid_on: "" },
  valuation: { as_of: "", assets: "", liabilities: "", source_note: "" },
  obligation: { title: "", due_date: "" },
  conflict: { person_ref: "", declared_on: "", nature: "" },
  complete: {},
};
export const CONFIRM = { contributions: "confirmPenContribution", valuations: "confirmPenValuation", obligations: "confirmPenObligation", conflicts: "confirmPenConflict" };
export const REJECT = { contributions: "rejectPenContribution", valuations: "rejectPenValuation", obligations: "rejectPenObligation", conflicts: "rejectPenConflict" };
const monthProblem = (v, what) => { const t = clean(v), m = /^(\d{4})-(\d{2})$/.exec(t); return m && Number(m[1]) >= 2000 && Number(m[1]) <= 2100 && Number(m[2]) >= 1 && Number(m[2]) <= 12 ? "" : `${what} must be a real month written YYYY-MM.`; };
const thisMonth = () => new Date().toISOString().slice(0, 7);
const notFuture = (v, what) => { const d = clean(v); return isRealDate(d) && d > new Date(Date.now() + 86400000).toISOString().slice(0, 10) ? `${what} cannot be in the future.` : ""; };
const after2000 = (v, what) => { const d = clean(v); return isRealDate(d) && d < "2000-01-01" ? `${what} must be in this century.` : ""; };
export function schemePayload(f) {
  const cur = clean(f.currency).toUpperCase(), type = clean(f.scheme_type), sp = clean(f.start_period);
  const p = first(textProblem(f.name, "The scheme name", 3), textProblem(f.scheme_ref, "The scheme reference", 2), currencyProblem(cur), TYPES.includes(type) ? "" : "Choose the scheme type.", monthProblem(sp, "The first contribution month"),
    !monthProblem(sp, "x") && sp > thisMonth() ? "The first contribution month cannot be in the future." : "", wholeProblem(f.due_day, "The due day of the month", 1, 28), textProblem(f.description, "The description", 10));
  return p ? { problem: p } : { body: { name: clean(f.name), scheme_ref: clean(f.scheme_ref), currency: cur, scheme_type: type, start_period: sp, due_day: Number(clean(f.due_day)), description: clean(f.description) } };
}
export function contributionPayload(f, sel) {
  const per = clean(f.period), paid = clean(f.paid_on), o = { zeroOk: true, digits: 13 }, sc = sel && sel.scheme;
  const p = first(monthProblem(per, "The month"), !monthProblem(per, "x") && per > thisMonth() ? "The month cannot be in the future." : "", sc && !monthProblem(per, "x") && per < sc.start_period ? "The month cannot be before the scheme's first contribution month." : "",
    amountProblem(f.employer_amount, "The employer amount", o), amountProblem(f.employee_amount, "The employee amount", o),
    !amountProblem(f.employer_amount, "x", o) && !amountProblem(f.employee_amount, "x", o) && Number(amt(f.employer_amount)) === 0 && Number(amt(f.employee_amount)) === 0 ? "At least one of the employer and employee amounts must be more than zero." : "",
    dateProblem(paid, "The date paid"), notFuture(paid, "The date paid"), after2000(paid, "The date paid"));
  return p ? { problem: p } : { body: { period: per, employer_amount: amt(f.employer_amount), employee_amount: amt(f.employee_amount), paid_on: paid } };
}
export function valuationPayload(f) {
  const d = clean(f.as_of);
  const p = first(dateProblem(d, "The valuation date"), notFuture(d, "The valuation date"), after2000(d, "The valuation date"), amountProblem(f.assets, "The assets", { zeroOk: true, digits: 15 }), amountProblem(f.liabilities, "The liabilities", { digits: 15 }), textProblem(f.source_note, "The source note", 10));
  return p ? { problem: p } : { body: { as_of: d, assets: amt(f.assets), liabilities: amt(f.liabilities), source_note: clean(f.source_note) } };
}
export function obligationPayload(f) {
  const d = clean(f.due_date);
  const p = first(textProblem(f.title, "The title", 3), dateProblem(d, "The due date"), isRealDate(d) && (d < "2000-01-01" || d > "2100-12-31") ? "The due date must be between 2000 and 2100." : "");
  return p ? { problem: p } : { body: { title: clean(f.title), due_date: d } };
}
export function completePayload(f) {
  const d = clean(f.completed_on);
  const p = first(dateProblem(d, "The date done"), notFuture(d, "The date done"), textProblem(f.note, "A note", 10));
  return p ? { problem: p } : { body: { completed_on: d, note: clean(f.note) } };
}
export function conflictPayload(f) {
  const d = clean(f.declared_on);
  const p = first(textProblem(f.person_ref, "The person reference", 2), dateProblem(d, "The date declared"), notFuture(d, "The date declared"), after2000(d, "The date declared"), textProblem(f.nature, "The nature of the interest", 10));
  return p ? { problem: p } : { body: { person_ref: clean(f.person_ref), declared_on: d, nature: clean(f.nature) } };
}
export function settingPayload(f) {
  const p = first(wholeProblem(f.funding_floor_pct, "The funding floor in percent", 1, 300), wholeProblem(f.valuation_stale_days, "The days before a valuation is stale", 1, 1500), wholeProblem(f.due_soon_days, "The days that count as due soon", 1, 365));
  return p ? { problem: p } : { body: { funding_floor_pct: Number(clean(f.funding_floor_pct)), valuation_stale_days: Number(clean(f.valuation_stale_days)), due_soon_days: Number(clean(f.due_soon_days)) } };
}
export const ownText = "You recorded this, so a different person must decide it.";
export const canDecideScheme = (x, role, me) => canApprove(role) && x.status === "PROPOSED" && x.proposed_by !== me;
export const canRecord = (x, role) => canPrepare(role) && x.status === "APPROVED";
export const canDecideRow = (x, r, role, me) => canApprove(role) && x.status === "APPROVED" && (r.status === "PROPOSED" || r.status === "DONE") && (r.status === "DONE" ? r.completed_by : r.proposed_by) !== me;
export const canClose = (x, role) => canApprove(role) && x.status === "APPROVED" && x.pending === 0;
