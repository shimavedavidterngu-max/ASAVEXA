import { money } from "./pubfin.js";

/**
 * "Where the money went": one budget line of an approved budget, in plain words, with the proof behind it.
 *   authorised -> promised (commitments) -> spent (posted to the ledger) -> evidence
 * Used by schools, public bodies and any organisation that budgets with Public Finance. A budget line is an ACCOUNT; this view does not invent departments.
 * Honest by construction:
 *  - It restates what the server recorded. Amounts are the server's decimal strings; nothing is added, subtracted or compared as a number here.
 *  - "Spent" means posted to the ledger. A purchase that is only promised is shown as promised, never as spent.
 *  - A list that could not be loaded (undefined) is "Not checked". An empty list is said plainly as nothing yet.
 * A step is { key, state: linked|missing|pending|unknown, stateLabel, title, meta }.
 */
export const SPEND_VOCAB = { authorised: "Authorised", committed: "Promised", spent: "Spent (posted)", evidence: "Evidence" };
export const SPEND_ORDER = ["authorised", "committed", "spent", "evidence"];

const step = (key, state, stateLabel, title, meta) => ({ key, state, stateLabel: stateLabel || null, title: title || null, meta: meta || null });
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
export const isZero = (v) => /^-?0+(\.0+)?$/.test(String(v == null ? "" : v).trim());
const unsigned = (v) => String(v).replace(/^-/, "");

/** Expense rows are the ones with a committed figure. Revenue rows have committed === null. */
export const isExpense = (row) => !!row && row.type === "EXPENSE";

export function sentence(row, currency) {
  if (!row) return null;
  const c = currency ? ` ${currency}` : "";
  if (!isExpense(row)) return `${row.code} ${row.name}: ${money(row.budget)}${c} of income is expected, and ${money(row.actual)}${c} has been posted so far.`;
  const tail = row.overspent ? `${money(unsigned(row.available))}${c} more has been spent or promised than was approved.` : `${money(row.available)}${c} is still available.`;
  return `Of the ${money(row.budget)}${c} approved for ${row.code} ${row.name}, ${money(row.actual)}${c} has been spent (posted to the ledger), ${money(row.committed)}${c} is promised in open commitments, and ${tail}`;
}

export function authorisedStep(budget, row) {
  if (budget === undefined || row === undefined) return step("authorised", "unknown");
  if (!budget || !row) return step("authorised", "missing", "Not found", null, "This budget line could not be found.");
  if (budget.status === "SUBMITTED") return step("authorised", "pending", "Waiting for approval", `Budget ${budget.ref}`, "A different person must approve this budget before anything can be promised against it.");
  if (budget.status !== "APPROVED" && budget.status !== "CLOSED") return step("authorised", "missing", "Not approved", `Budget ${budget.ref}`, "Only an approved budget authorises spending.");
  const adj = isZero(row.adjustment) ? "" : ` Moved by approved virements (${money(row.adjustment)}), so the line now stands at ${money(row.budget)}.`;
  return step("authorised", "linked", budget.status === "CLOSED" ? "Approved, now closed" : "Approved", `Budget ${budget.ref}: ${money(row.approved)} approved for this line`, `Approved by a second person.${adj}`);
}

const forLine = (list, budgetId, accountId) => (Array.isArray(list) ? list.filter((c) => c.budget_id === budgetId && c.account_id === accountId && c.status !== "CANCELLED") : undefined);

export function committedStep(coms) {
  if (coms === undefined) return step("committed", "unknown");
  if (!coms.length) return step("committed", "missing", "Nothing promised yet", null, "No commitment has been made against this line.");
  const open = coms.filter((c) => c.status === "OPEN");
  const title = plural(coms.length, "commitment", "commitments");
  const meta = coms.map((c) => `${c.ref} ${c.vendor} ${money(c.amount)} (${c.status === "OPEN" ? "open" : "settled"})`).join("; ") + ".";
  return open.length ? step("committed", "pending", `${open.length} still open`, title, meta) : step("committed", "linked", "All settled", title, meta);
}

export function spentStep(row, exec) {
  if (row === undefined || exec === undefined) return step("spent", "unknown");
  if (!row) return step("spent", "missing", "Not found");
  if (isZero(row.actual)) return step("spent", "missing", "Nothing posted yet", null, "Spending counts only once a journal is posted to the ledger. A purchase that is only promised is not counted as spent.");
  const n = exec && typeof exec.journals_examined === "number" ? ` ${plural(exec.journals_examined, "posted journal was", "posted journals were")} read for ${exec.start} to ${exec.end}.` : "";
  return step("spent", "linked", "Posted", money(row.actual), `Read from the ledger; ASAVEXA did not make any payment.${n}`);
}

export function evidenceStep(coms) {
  if (coms === undefined) return step("evidence", "unknown");
  if (!coms.length) return step("evidence", "missing", "Nothing to evidence yet", null, "There is no commitment on this line yet.");
  const without = coms.filter((c) => !(c.evidence || []).length);
  if (!without.length) return step("evidence", "linked", "Linked", `Evidence on all ${plural(coms.length, "commitment", "commitments")}`, null);
  return step("evidence", without.length === coms.length ? "missing" : "pending", "Not linked yet", `${without.length} of ${plural(coms.length, "commitment", "commitments")} without evidence`, `Without evidence: ${without.map((c) => c.ref).join(", ")}.`);
}

/** `detail` = the budget with its execution (undefined if it could not be loaded). `commitments` = the organisation's list (undefined if not loaded). */
export function buildLineTrace({ detail, commitments, accountId }) {
  const exec = detail ? detail.execution : undefined;
  const row = exec ? (exec.rows || []).find((r) => r.account_id === accountId) : undefined;
  if (detail && exec && !row) return null;
  const coms = detail ? forLine(commitments, detail.id, accountId) : undefined;
  const steps = [authorisedStep(detail, row), committedStep(coms), spentStep(row, exec), evidenceStep(coms)];
  return { row: row || null, steps, commitments: coms || [], commitmentsKnown: coms !== undefined, sentence: sentence(row, exec && exec.currency) };
}
