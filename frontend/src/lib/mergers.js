import { PERMISSIONS } from "./permissions.js";
import { has, canRead, clean, first, dateProblem, textProblem, amt, amountProblem, wholeProblem, currencyProblem, mkStatus, fmt, isRealDate, noteProblem, words } from "./wsCommon.js";

/** Mergers and acquisitions helpers (deals with a due-diligence checklist, closing conditions and price adjustments; values nothing and gives no deal advice). No DOM, no network. The server does all the arithmetic. */
export { canRead, fmt, isRealDate, noteProblem, words };
export const canPrepare = (role) => has(role, PERMISSIONS.MNA_PREPARE);
export const canApprove = (role) => has(role, PERMISSIONS.MNA_APPROVE);
export const TABS = [["overview", "Overview"], ["deals", "Deals"]];
export const TYPES = ["ACQUISITION", "MERGER", "DISPOSAL", "OTHER"];
export const AREAS = ["FINANCIAL", "LEGAL", "TAX", "COMMERCIAL", "OPERATIONAL", "OTHER"];
export const ADJ_KINDS = ["INCREASE", "DECREASE"];
export const OUTCOMES = ["COMPLETED", "ABANDONED"];
export const statusOf = mkStatus({
  PROPOSED: { tone: "warn", label: "Waiting for a decision" }, APPROVED: { tone: "pass", label: "Open" }, REJECTED: { tone: "neutral", label: "Rejected" }, CLOSED: { tone: "neutral", label: "Closed" }, CONFIRMED: { tone: "pass", label: "Confirmed" },
  OPEN: { tone: "info", label: "Open" }, DONE: { tone: "warn", label: "Marked, waiting for confirmation" }, COMPLETED: { tone: "pass", label: "Completed" }, ABANDONED: { tone: "neutral", label: "Abandoned" },
});
export const ATTENTION_TONE = { DEALS_TO_APPROVE: "info", ITEMS_TO_DECIDE: "info", CHECKLIST_OPEN: "info", CONDITIONS_OVERDUE: "warn", CONDITIONS_DUE_SOON: "info", TARGET_DATE_PASSED: "warn" };
export const EMPTY = {
  deal: { name: "", deal_ref: "", currency: "", deal_type: "ACQUISITION", base_price: "", target_close_date: "", description: "" },
  checklist: { title: "", area: "FINANCIAL" },
  condition: { title: "", due_date: "" },
  adjustment: { kind: "DECREASE", amount: "", basis: "" },
  done: {},
  close: { outcome: "COMPLETED" },
};
export const PROVIDE = { checklist: "provideMaChecklist", conditions: "meetMaCondition" };
export const CONFIRM = { checklist: "confirmMaChecklist", conditions: "confirmMaCondition", adjustments: "confirmMaAdjustment" };
export const REJECT = { checklist: "rejectMaChecklist", conditions: "rejectMaCondition", adjustments: "rejectMaAdjustment" };
const notFuture = (v, what) => { const d = clean(v); return isRealDate(d) && d > new Date(Date.now() + 86400000).toISOString().slice(0, 10) ? `${what} cannot be in the future.` : ""; };
const after2000 = (v, what) => { const d = clean(v); return isRealDate(d) && d < "2000-01-01" ? `${what} must be in this century.` : ""; };
const betweenYears = (v, what) => { const d = clean(v); return isRealDate(d) && (d < "2000-01-01" || d > "2100-12-31") ? `${what} must be between 2000 and 2100.` : ""; };
export function dealPayload(f) {
  const cur = clean(f.currency).toUpperCase(), type = clean(f.deal_type), t = clean(f.target_close_date);
  const p = first(textProblem(f.name, "The deal name", 3), textProblem(f.deal_ref, "The deal reference", 2), currencyProblem(cur), TYPES.includes(type) ? "" : "Choose the deal type.", amountProblem(f.base_price, "The base price", { digits: 15 }),
    dateProblem(t, "The target closing date"), betweenYears(t, "The target closing date"), textProblem(f.description, "The description", 10));
  return p ? { problem: p } : { body: { name: clean(f.name), deal_ref: clean(f.deal_ref), currency: cur, deal_type: type, base_price: amt(f.base_price), target_close_date: t, description: clean(f.description) } };
}
export function checklistPayload(f) {
  const area = clean(f.area), p = first(textProblem(f.title, "The title", 3), AREAS.includes(area) ? "" : "Choose the area.");
  return p ? { problem: p } : { body: { title: clean(f.title), area } };
}
export function conditionPayload(f) {
  const d = clean(f.due_date), p = first(textProblem(f.title, "The title", 3), dateProblem(d, "The due date"), betweenYears(d, "The due date"));
  return p ? { problem: p } : { body: { title: clean(f.title), due_date: d } };
}
export function adjustmentPayload(f) {
  const kind = clean(f.kind), p = first(ADJ_KINDS.includes(kind) ? "" : "Choose whether the price goes up or down.", amountProblem(f.amount, "The amount", { digits: 15 }), textProblem(f.basis, "The basis", 10));
  return p ? { problem: p } : { body: { kind, amount: amt(f.amount), basis: clean(f.basis) } };
}
export function donePayload(f) {
  const d = clean(f.done_on), p = first(dateProblem(d, "The date"), notFuture(d, "The date"), after2000(d, "The date"), textProblem(f.note, "A note", 10));
  return p ? { problem: p } : { body: { done_on: d, note: clean(f.note) } };
}
export function settingPayload(f) {
  const p = wholeProblem(f.due_soon_days, "The days that count as due soon", 1, 365);
  return p ? { problem: p } : { body: { due_soon_days: Number(clean(f.due_soon_days)) } };
}
export const ownText = "You recorded this, so a different person must decide it.";
export const canDecideDeal = (x, role, me) => canApprove(role) && x.status === "PROPOSED" && x.proposed_by !== me;
export const canRecord = (x, role) => canPrepare(role) && x.status === "APPROVED";
export const canDecideRow = (x, r, role, me, kind) => {
  const step = kind === "checklist" || kind === "conditions";
  return canApprove(role) && x.status === "APPROVED" && r.status === (step ? "DONE" : "PROPOSED") && (step ? r.done_by : r.proposed_by) !== me;
};
export const canClose = (x, role) => canApprove(role) && x.status === "APPROVED" && x.pending === 0;
