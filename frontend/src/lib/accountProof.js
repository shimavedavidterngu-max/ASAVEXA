import { proofState, railSummary } from "../components/ProofRail.js";

/**
 * The proof behind one account's line on a report, built ONLY from what the server returned for that account and period:
 *   trace (the posted entries), evidence completeness, and the reconciliation summary.
 * Nothing is computed from amounts. Counts the server sent are worded, never recalculated.
 *
 * Each input can be: the server's object; `undefined` = the request failed or was not made (shows "Not checked");
 * `null` = checked and there is nothing (shows "Not linked yet"). The reconciliation step is left out entirely when the account is
 * not a reconciled bank account (the server returned all zeros), because "not applicable" is not a gap.
 */
export const ACCOUNT_VOCAB = { source: "Posted entries", evidence: "Evidence", verification: "Reconciliation" };
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

export function accountProofSteps({ trace, completeness, reconciliation } = {}) {
  const steps = [];

  if (trace === undefined) steps.push({ key: "source", state: "unknown" });
  else if (!Array.isArray(trace) || trace.length === 0) steps.push({ key: "source", state: "missing", title: null, meta: "No posted entry is recorded for this account in this period." });
  else steps.push({ key: "source", state: "linked", title: plural(trace.length, "posted entry", "posted entries"), meta: "Open Trace a line to read each one.", href: null });

  if (completeness === undefined) steps.push({ key: "evidence", state: "unknown" });
  else if (completeness === null || !(completeness.total_entries > 0)) steps.push({ key: "evidence", state: "missing", title: null, meta: "There are no entries to hold evidence." });
  else {
    const total = completeness.total_entries, missing = completeness.entries_missing_evidence || 0;
    if (missing === 0) steps.push({ key: "evidence", state: "linked", title: `All ${plural(total, "entry", "entries")} have evidence`, meta: null });
    else if (missing >= total) steps.push({ key: "evidence", state: "missing", title: `${plural(missing, "entry", "entries")} missing evidence`, meta: `None of the ${total} entries has evidence linked.` });
    else steps.push({ key: "evidence", state: "pending", title: `${missing} of ${total} entries missing evidence`, meta: null });
  }

  if (reconciliation === undefined) steps.push({ key: "verification", state: "unknown" });
  else if (reconciliation !== null) {
    const ex = reconciliation.exception_count || 0, rec = reconciliation.reconciled_count || 0, out = reconciliation.outstanding_count || 0;
    const detail = `${rec} reconciled · ${out} outstanding · ${plural(ex, "exception", "exceptions")}`;
    steps.push({ key: "verification", state: ex === 0 && out === 0 && rec > 0 ? "linked" : "pending", title: detail, meta: null });
  }
  return steps;
}

/** The server returns all zeros for an account that is not a reconciled bank account; that means "not applicable", not "clean". */
export const reconciliationOrNull = (r) => (r && (r.reconciled_count || r.outstanding_count || r.exception_count) ? r : null);

/** The mark's state for a line: "unknown" until its proof has been loaded. */
export function lineMarkState(entry) {
  if (!entry || entry.error || !entry.steps) return "unknown";
  return proofState(entry.steps);
}
export { railSummary };
