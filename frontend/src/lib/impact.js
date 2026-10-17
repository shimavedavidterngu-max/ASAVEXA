import { PERMISSIONS } from "./permissions.js";
import { has, canRead, clean, first, dateProblem, textProblem, amt, amountProblem, wholeProblem, mkStatus, fmt, isRealDate, noteProblem, words } from "./wsCommon.js";

/** Impact measurement helpers (indicators with a baseline and a target, and the readings reported against them; collects and verifies no data). No DOM, no network. The server does all the arithmetic. */
export { canRead, fmt, isRealDate, noteProblem, words };
export const canPrepare = (role) => has(role, PERMISSIONS.IMP_PREPARE);
export const canApprove = (role) => has(role, PERMISSIONS.IMP_APPROVE);
export const TABS = [["overview", "Overview"], ["indicators", "Indicators"]];
export const DIRECTIONS = ["INCREASE", "DECREASE"];
export const statusOf = mkStatus({
  PROPOSED: { tone: "warn", label: "Waiting for a decision" }, APPROVED: { tone: "pass", label: "Open" }, REJECTED: { tone: "neutral", label: "Rejected" }, CLOSED: { tone: "neutral", label: "Closed" }, CONFIRMED: { tone: "pass", label: "Confirmed" },
  NO_DATA: { tone: "neutral", label: "No reading yet" }, ACHIEVED: { tone: "pass", label: "Target reached" }, ON_TRACK: { tone: "pass", label: "On track" }, BEHIND: { tone: "warn", label: "Behind" }, OVERDUE: { tone: "warn", label: "Target date passed" },
});
export const ATTENTION_TONE = { INDICATORS_TO_APPROVE: "info", READINGS_TO_CONFIRM: "info", BEHIND_TARGET: "warn", TARGET_PASSED: "warn", READINGS_STALE: "warn", NO_READINGS: "info" };
export const EMPTY = {
  indicator: { title: "", programme_ref: "", unit: "", direction: "INCREASE", baseline: "", target: "", baseline_date: "", target_date: "" },
  reading: { period_end: "", value: "", source_note: "" },
};
const num = (v) => Number(amt(v));
export function indicatorPayload(f) {
  const dir = clean(f.direction), bd = clean(f.baseline_date), td = clean(f.target_date), o = { zeroOk: true, digits: 12 };
  const p = first(textProblem(f.title, "The title", 3), textProblem(f.programme_ref, "The programme reference", 2), textProblem(f.unit, "The unit", 1), DIRECTIONS.includes(dir) ? "" : "Choose whether the indicator should increase or decrease.",
    amountProblem(f.baseline, "The baseline", o), amountProblem(f.target, "The target", o), dateProblem(bd, "The baseline date"), dateProblem(td, "The target date"),
    isRealDate(bd) && isRealDate(td) && td <= bd ? "The target date must be after the baseline date." : "",
    isRealDate(bd) && isRealDate(td) && td > bd && (Date.parse(td) - Date.parse(bd)) / 86400000 > 3660 ? "The baseline and target dates can be at most ten years apart." : "",
    dir === "INCREASE" && num(f.target) <= num(f.baseline) ? "For an increase the target must be higher than the baseline." : "", dir === "DECREASE" && num(f.target) >= num(f.baseline) ? "For a decrease the target must be lower than the baseline." : "");
  return p ? { problem: p } : { body: { title: clean(f.title), programme_ref: clean(f.programme_ref), unit: clean(f.unit), direction: dir, baseline: amt(f.baseline), target: amt(f.target), baseline_date: bd, target_date: td } };
}
export function readingPayload(f, sel) {
  const d = clean(f.period_end), ind = sel && sel.indicator;
  const p = first(dateProblem(d, "The period end"), amountProblem(f.value, "The value", { zeroOk: true, digits: 12 }), textProblem(f.source_note, "The source note", 10),
    ind && isRealDate(d) && d < ind.baseline_date ? "The period end cannot be before the baseline date." : "");
  return p ? { problem: p } : { body: { period_end: d, value: amt(f.value), source_note: clean(f.source_note) } };
}
export function settingPayload(f) {
  const p = first(wholeProblem(f.tolerance_points, "The tolerance in percentage points", 0, 100), wholeProblem(f.stale_days, "The days before a reading is stale", 1, 730));
  return p ? { problem: p } : { body: { tolerance_points: Number(clean(f.tolerance_points)), stale_days: Number(clean(f.stale_days)) } };
}
export const canDecideIndicator = (x, role, me) => canApprove(role) && x.status === "PROPOSED" && x.proposed_by !== me;
export const canRead_ = (x, role) => canPrepare(role) && x.status === "APPROVED";
export const canDecideReading = (x, r, role, me) => canApprove(role) && x.status === "APPROVED" && r.status === "PROPOSED" && r.proposed_by !== me;
export const canClose = (x, role) => canApprove(role) && x.status === "APPROVED" && x.pending_readings === 0;
export const ownText = "You proposed this, so a different person must decide it.";
