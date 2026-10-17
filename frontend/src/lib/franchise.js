import { PERMISSIONS } from "./permissions.js";
import { has, canRead, clean, first, dateProblem, textProblem, amt, amountProblem, wholeProblem, currencyProblem, mkStatus, fmt, isRealDate, noteProblem, words } from "./wsCommon.js";

/** Franchise and multi-location helpers (locations with a royalty rate, monthly sales reports and royalty payments; collects no money, applies no franchise law). No DOM, no network. The server does all the arithmetic. */
export { canRead, fmt, isRealDate, noteProblem, words };
export const canPrepare = (role) => has(role, PERMISSIONS.FCH_PREPARE);
export const canApprove = (role) => has(role, PERMISSIONS.FCH_APPROVE);
export const TABS = [["overview", "Overview"], ["locations", "Locations"]];
export const statusOf = mkStatus({
  PROPOSED: { tone: "warn", label: "Waiting for a decision" }, APPROVED: { tone: "pass", label: "Open" }, REJECTED: { tone: "neutral", label: "Rejected" }, CLOSED: { tone: "neutral", label: "Closed" }, CONFIRMED: { tone: "pass", label: "Confirmed" },
  OWED: { tone: "warn", label: "Royalty owed" }, OVERPAID: { tone: "info", label: "Overpaid" }, SETTLED: { tone: "pass", label: "Settled" },
});
export const ATTENTION_TONE = { LOCATIONS_TO_APPROVE: "info", ITEMS_TO_DECIDE: "info", MISSING_REPORTS: "warn", LATE_REPORTS: "warn", ROYALTY_OVERDUE: "warn", OVERPAID: "info" };
export const EMPTY = {
  location: { name: "", location_ref: "", currency: "", royalty_rate_pct: "", due_day: "", start_period: "", description: "" },
  report: { period: "", gross_sales: "", submitted_on: "" },
  payment: { amount: "", paid_on: "", note: "" },
};
export const CONFIRM = { reports: "confirmFchReport", payments: "confirmFchPayment" };
export const REJECT = { reports: "rejectFchReport", payments: "rejectFchPayment" };
const monthProblem = (v, what) => { const t = clean(v), m = /^(\d{4})-(\d{2})$/.exec(t); return m && Number(m[1]) >= 2000 && Number(m[1]) <= 2100 && Number(m[2]) >= 1 && Number(m[2]) <= 12 ? "" : `${what} must be a real month written YYYY-MM.`; };
const thisMonth = () => new Date().toISOString().slice(0, 7);
const notFuture = (v, what) => { const d = clean(v); return isRealDate(d) && d > new Date(Date.now() + 86400000).toISOString().slice(0, 10) ? `${what} cannot be in the future.` : ""; };
const after2000 = (v, what) => { const d = clean(v); return isRealDate(d) && d < "2000-01-01" ? `${what} must be in this century.` : ""; };
export function locationPayload(f) {
  const cur = clean(f.currency).toUpperCase(), sp = clean(f.start_period);
  const p = first(textProblem(f.name, "The location name", 3), textProblem(f.location_ref, "The location reference", 2), currencyProblem(cur), amountProblem(f.royalty_rate_pct, "The royalty rate in percent", { digits: 3 }),
    !amountProblem(f.royalty_rate_pct, "x", { digits: 3 }) && Number(amt(f.royalty_rate_pct)) > 100 ? "The royalty rate cannot be more than 100 percent." : "", monthProblem(sp, "The first reporting month"),
    !monthProblem(sp, "x") && sp > thisMonth() ? "The first reporting month cannot be in the future." : "", wholeProblem(f.due_day, "The due day of the month", 1, 28), textProblem(f.description, "The description", 10));
  return p ? { problem: p } : { body: { name: clean(f.name), location_ref: clean(f.location_ref), currency: cur, royalty_rate_pct: amt(f.royalty_rate_pct), due_day: Number(clean(f.due_day)), start_period: sp, description: clean(f.description) } };
}
export function reportPayload(f, sel) {
  const per = clean(f.period), sub = clean(f.submitted_on), sc = sel && sel.location;
  const p = first(monthProblem(per, "The month"), !monthProblem(per, "x") && per > thisMonth() ? "The month cannot be in the future." : "", sc && !monthProblem(per, "x") && per < sc.start_period ? "The month cannot be before the location's first reporting month." : "",
    amountProblem(f.gross_sales, "The gross sales", { zeroOk: true }), dateProblem(sub, "The date submitted"), notFuture(sub, "The date submitted"), after2000(sub, "The date submitted"));
  return p ? { problem: p } : { body: { period: per, gross_sales: amt(f.gross_sales), submitted_on: sub } };
}
export function paymentPayload(f) {
  const on = clean(f.paid_on);
  const p = first(amountProblem(f.amount, "The amount"), dateProblem(on, "The date paid"), notFuture(on, "The date paid"), after2000(on, "The date paid"), textProblem(f.note, "The note", 3));
  return p ? { problem: p } : { body: { amount: amt(f.amount), paid_on: on, note: clean(f.note) } };
}
export function settingPayload(f) {
  const p = wholeProblem(f.grace_days, "The grace period in days", 0, 60);
  return p ? { problem: p } : { body: { grace_days: Number(clean(f.grace_days)) } };
}
export const ownText = "You recorded this, so a different person must decide it.";
export const canDecideLocation = (x, role, me) => canApprove(role) && x.status === "PROPOSED" && x.proposed_by !== me;
export const canRecord = (x, role) => canPrepare(role) && x.status === "APPROVED";
export const canDecideRow = (x, r, role, me) => canApprove(role) && x.status === "APPROVED" && r.status === "PROPOSED" && r.proposed_by !== me;
export const canClose = (x, role) => canApprove(role) && x.status === "APPROVED" && x.pending === 0;
