import { PERMISSIONS } from "./permissions.js";
import { has, canRead, clean, first, dateProblem, textProblem, amt, amountProblem, wholeProblem, currencyProblem, mkStatus, fmt, isRealDate, noteProblem, words } from "./wsCommon.js";

/** Operations research helpers (compare options with typed costs and yearly flows; the server does all the arithmetic; nothing is recommended). No DOM, no network. */
export { canRead, fmt, isRealDate, noteProblem, words, dateProblem };
export const canPrepare = (role) => has(role, PERMISSIONS.OPR_PREPARE);
export const canApprove = (role) => has(role, PERMISSIONS.OPR_APPROVE);
export const TABS = [["overview", "Overview"], ["analyses", "Analyses"]];
export const statusOf = mkStatus({
  DRAFT: { tone: "neutral", label: "Draft" }, SUBMITTED: { tone: "warn", label: "Waiting for review" }, APPROVED: { tone: "pass", label: "Approved" }, RETURNED: { tone: "warn", label: "Returned" }, WITHDRAWN: { tone: "neutral", label: "Withdrawn" },
  ACTIVE: { tone: "pass", label: "In the comparison" }, REMOVED: { tone: "neutral", label: "Removed" },
});
export const ATTENTION_TONE = { ANALYSES_TO_REVIEW: "info", ANALYSES_RETURNED: "warn", DECISIONS_NEEDED: "info", DECISION_NOT_HIGHEST_NPV: "warn" };
export const EMPTY = {
  analysis: { title: "", currency: "", discount_rate: "", purpose: "" },
  option: { name: "", upfront_cost: "", flows: "" },
  decision: { option_no: "", rationale: "" },
};
export function analysisPayload(f) {
  const p = first(textProblem(f.title, "The title", 3), textProblem(f.purpose, "The purpose", 10), currencyProblem(f.currency), amountProblem(f.discount_rate, "The discount rate", { zeroOk: true, digits: 3 }),
    /^\d/.test(amt(f.discount_rate)) && Number(amt(f.discount_rate)) > 100 ? "The discount rate cannot be more than 100 percent." : "");
  return p ? { problem: p } : { body: { title: clean(f.title), purpose: clean(f.purpose), currency: clean(f.currency).toUpperCase(), discount_rate: amt(f.discount_rate) } };
}
/** Yearly flows are typed separated by semicolons or spaces, for example "600; 600; 650". */
export const parseFlows = (v) => clean(v).split(/[;\s]+/).filter(Boolean);
export function optionPayload(f) {
  const flows = parseFlows(f.flows);
  const p = first(textProblem(f.name, "The option name", 2), amountProblem(f.upfront_cost, "The upfront cost"), flows.length ? "" : "Type the net flow for each year, separated by semicolons.", flows.length > 10 ? "At most 10 years can be compared." : "",
    ...flows.map((x, i) => amountProblem(x, `The flow for year ${i + 1}`, { neg: true, zeroOk: true })));
  return p ? { problem: p } : { body: { name: clean(f.name), upfront_cost: amt(f.upfront_cost), flows: flows.map(amt) } };
}
export function decisionPayload(f) {
  const p = first(wholeProblem(f.option_no, "The option", 1, 999), textProblem(f.rationale, "The rationale", 10));
  return p ? { problem: p } : { body: { option_no: Number(clean(f.option_no)), rationale: clean(f.rationale) } };
}
export const canEdit = (a, role) => canPrepare(role) && (a.status === "DRAFT" || a.status === "RETURNED");
export const canSubmit = (a, role) => canEdit(a, role) && a.active_options >= 2;
export const canDecide = (a, role, me) => canApprove(role) && a.status === "SUBMITTED" && a.submitted_by !== me;
export const canRecord = (a, role, me) => canApprove(role) && a.status === "APPROVED" && !a.decision && a.submitted_by !== me;
export const ownText = "You submitted this, so a different person must decide it.";
