import { PERMISSIONS } from "./permissions.js";
import { has, canRead, clean, first, dateProblem, textProblem, amt, amountProblem, currencyProblem, mkStatus, fmt, isRealDate, noteProblem, words } from "./wsCommon.js";

/** Insolvency helpers (a case register with creditor claims, realisations, costs and an illustrative distribution; pays no one and applies no law). No DOM, no network. The server does all the arithmetic. */
export { canRead, fmt, isRealDate, noteProblem, words };
export const canPrepare = (role) => has(role, PERMISSIONS.ISV_PREPARE);
export const canApprove = (role) => has(role, PERMISSIONS.ISV_APPROVE);
export const TABS = [["overview", "Overview"], ["cases", "Cases"]];
export const CLASSES = ["SECURED", "PREFERENTIAL", "UNSECURED", "SUBORDINATED"];
export const statusOf = mkStatus({
  PROPOSED: { tone: "warn", label: "Waiting for a decision" }, OPEN: { tone: "pass", label: "Open" }, REJECTED: { tone: "neutral", label: "Rejected" }, CLOSED: { tone: "neutral", label: "Closed" },
  LODGED: { tone: "warn", label: "Waiting for a decision" }, ADMITTED: { tone: "pass", label: "Admitted" }, CONFIRMED: { tone: "pass", label: "Confirmed" },
});
export const ATTENTION_TONE = { CASES_TO_APPROVE: "info", CLAIMS_TO_DECIDE: "info", ENTRIES_TO_CONFIRM: "info", LATE_CLAIMS: "warn", COSTS_EXCEED_REALISATIONS: "warn", FUNDS_READY: "info" };
export const EMPTY = {
  case: { title: "", currency: "", description: "", priority: CLASSES.join(", "), claims_deadline: "" },
  claim: { creditor_ref: "", claim_class: "UNSECURED", amount: "", basis: "" },
  entry: { entry_type: "REALISATION", description: "", amount: "", entry_date: "" },
  admit: {},
};
export function casePayload(f) {
  const order = clean(f.priority).split(/[,;\s]+/).filter(Boolean).map((x) => x.toUpperCase()), dl = clean(f.claims_deadline);
  const p = first(textProblem(f.title, "The title", 3), textProblem(f.description, "The description", 10), currencyProblem(f.currency),
    order.length === 4 && CLASSES.every((c) => order.includes(c)) ? "" : "Type each class once, in the order they are paid: " + CLASSES.join(", ") + ".", dl ? dateProblem(dl, "The claims deadline") : "");
  return p ? { problem: p } : { body: { title: clean(f.title), description: clean(f.description), currency: clean(f.currency).toUpperCase(), priority: order, ...(dl ? { claims_deadline: dl } : {}) } };
}
export function claimPayload(f) {
  const p = first(textProblem(f.creditor_ref, "The creditor reference", 2), CLASSES.includes(clean(f.claim_class)) ? "" : "Choose the class of claim.", amountProblem(f.amount, "The amount claimed"), textProblem(f.basis, "The basis of the claim", 10));
  return p ? { problem: p } : { body: { creditor_ref: clean(f.creditor_ref), claim_class: clean(f.claim_class), amount: amt(f.amount), basis: clean(f.basis) } };
}
export function admitPayload(f) {
  const p = first(amountProblem(f.amount, "The amount admitted"), clean(f.note) && clean(f.note).length < 10 ? "The note needs at least 10 characters (or leave it empty)." : "");
  return p ? { problem: p } : { body: { amount: amt(f.amount), note: clean(f.note) } };
}
export function entryPayload(f) {
  const t = clean(f.entry_type);
  const p = first(t === "REALISATION" || t === "COST" ? "" : "Choose whether this is a realisation or a cost.", textProblem(f.description, "The description", 3), amountProblem(f.amount, "The amount"), dateProblem(f.entry_date, "The date"));
  return p ? { problem: p } : { body: { entry_type: t, description: clean(f.description), amount: amt(f.amount), entry_date: clean(f.entry_date) } };
}
export const canDecideCase = (c, role, me) => canApprove(role) && c.status === "PROPOSED" && c.proposed_by !== me;
export const canLodge = (c, role) => canPrepare(role) && c.status === "OPEN";
export const canAdjudicate = (c, x, role, me) => canApprove(role) && c.status === "OPEN" && x.status === "LODGED" && x.proposed_by !== me;
export const canConfirm = (c, e, role, me) => canApprove(role) && c.status === "OPEN" && e.status === "PROPOSED" && e.proposed_by !== me;
export const canRecord = (c, role, me) => canApprove(role) && c.status === "OPEN" && c.proposed_by !== me && c.pending_claims === 0 && c.pending_entries === 0 && !!c.waterfall && Number(amt(c.waterfall.total_paid)) > 0;
export const canClose = (c, role) => canApprove(role) && c.status === "OPEN" && c.pending_claims === 0 && c.pending_entries === 0;
export const ownText = "You proposed this, so a different person must decide it.";
