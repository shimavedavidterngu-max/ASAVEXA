import { PERMISSIONS } from "./permissions.js";
import { has, canRead, clean, first, textProblem, amt, amountProblem, wholeProblem, currencyProblem, mkStatus, fmt, isRealDate, noteProblem, words } from "./wsCommon.js";

/** Approval workflow helpers (policies with up to three steps and requests that move through them; a record only). No DOM, no network. The server decides every rule. */
export { canRead, fmt, isRealDate, noteProblem, words };
export const canPrepare = (role) => has(role, PERMISSIONS.APW_PREPARE);
export const canApprove = (role) => has(role, PERMISSIONS.APW_APPROVE);
export const TABS = [["overview", "Overview"], ["requests", "Requests"], ["policies", "Policies"]];
export const KINDS = ["PAYMENT", "PURCHASE", "CONTRACT", "EXPENSE", "ACCESS", "EXCEPTION", "OTHER"];
export const MAX_STEPS = 3;
export const statusOf = mkStatus({
  PROPOSED: { tone: "warn", label: "Waiting for a decision" }, ACTIVE: { tone: "pass", label: "Active" }, REJECTED: { tone: "neutral", label: "Rejected" }, RETIRED: { tone: "neutral", label: "Retired" },
  PENDING: { tone: "warn", label: "Waiting for approval" }, APPROVED: { tone: "pass", label: "Approved" }, WITHDRAWN: { tone: "neutral", label: "Withdrawn" },
});
export const ATTENTION_TONE = { POLICIES_TO_DECIDE: "info", REQUESTS_WAITING: "info", REQUESTS_STALE: "warn", NO_ACTIVE_POLICY: "warn" };
export const EMPTY = {
  policy: { name: "", request_kind: "PAYMENT", description: "", s1l: "", s1n: "1", s2l: "", s2n: "", s3l: "", s3n: "" },
  request: { policy_id: "", title: "", request_ref: "", amount: "", currency: "", description: "" },
};
export function policyPayload(f) {
  const kind = clean(f.request_kind), steps = [];
  let p = first(textProblem(f.name, "The policy name", 3), KINDS.includes(kind) ? "" : "Choose the kind of request.", textProblem(f.description, "The description", 10));
  for (let i = 1; i <= MAX_STEPS && !p; i++) {
    const l = clean(f[`s${i}l`]), n = clean(f[`s${i}n`]);
    if (!l && !n) { if (i === 1) p = "Step 1 needs a label and a number of approvals."; continue; }
    p = first(textProblem(l, `The label of step ${i}`, 3), wholeProblem(n, `The approvals needed at step ${i}`, 1, 5));
    if (!p && steps.some((s) => s.label.toLowerCase() === l.toLowerCase())) p = "Each step needs a different label.";
    if (!p && i > 1 && steps.length < i - 1) p = "Fill the steps in order, without gaps.";
    if (!p) steps.push({ label: l, required: Number(n) });
  }
  return p ? { problem: p } : { body: { name: clean(f.name), request_kind: kind, steps, description: clean(f.description) } };
}
export function requestPayload(f) {
  const hasAmt = clean(f.amount) !== "", hasCur = clean(f.currency) !== "", cur = clean(f.currency).toUpperCase();
  const p = first(clean(f.policy_id) ? "" : "Choose the policy this request follows.", textProblem(f.title, "The title", 3), textProblem(f.request_ref, "The request reference", 2), textProblem(f.description, "The description", 10),
    hasAmt !== hasCur ? "Give both the amount and its currency, or neither." : "", hasAmt ? amountProblem(f.amount, "The amount", { digits: 15 }) : "", hasCur ? currencyProblem(cur) : "");
  if (p) return { problem: p };
  const body = { policy_id: clean(f.policy_id), title: clean(f.title), request_ref: clean(f.request_ref), description: clean(f.description) };
  if (hasAmt) { body.amount = amt(f.amount); body.currency = cur; }
  return { body };
}
export function settingPayload(f) {
  const p = wholeProblem(f.stale_days, "The days that count as waiting too long", 1, 365);
  return p ? { problem: p } : { body: { stale_days: Number(clean(f.stale_days)) } };
}
export const ownText = "You submitted this, so a different person must decide it.";
export const decidedText = "You have already decided this request. A different person must decide the next step.";
export const hasDecided = (x, me) => (x.steps || []).some((s) => (s.decisions || []).some((d) => d.by === me));
export const canDecidePolicy = (x, role, me) => canApprove(role) && x.status === "PROPOSED" && x.proposed_by !== me;
export const canRetirePolicy = (x, role) => canApprove(role) && x.status === "ACTIVE";
export const canDecideRequest = (x, role, me) => canApprove(role) && x.status === "PENDING" && x.submitted_by !== me && !hasDecided(x, me);
export const canWithdraw = (x, role, me) => canPrepare(role) && x.status === "PENDING" && x.submitted_by === me;
export const stepLine = (s, current) => `Step ${s.no}: ${s.label} (${s.decisions.filter((d) => d.decision === "APPROVED").length} of ${s.required} approval${s.required === 1 ? "" : "s"})${current === s.no ? " — current" : ""}`;
