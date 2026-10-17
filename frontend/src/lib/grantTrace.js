import { money } from "./pubfin.js";

/**
 * "Follow a grant": funding -> received -> spent (approved) -> evidence, for ONE grant, in plain words. Built for nonprofits that must show a funder
 * where restricted money went, and it works for any grant recorded in Public Finance.
 * Honest by construction:
 *  - It restates what the server recorded (amounts as the server's decimal text; the server's own spent, received, remaining and cash figures). Nothing is added or compared as a number here.
 *  - "Spent" means approved by a second person. Spending still waiting for that person is shown as waiting, never as spent.
 *  - ASAVEXA records and checks. It does not judge whether donor conditions are met, and it does not prove a grant produced any programme result (Stage 14 matches indicators by a typed reference only): the page says so.
 * A step is { key, state: linked|missing|pending|unknown, stateLabel, title, meta }.
 */
export const GRANT_VOCAB = { funding: "Funding awarded", received: "Cash received", spent: "Spent (approved)", evidence: "Evidence" };
/** Faith-based organisations see the same records as "funds": wording changes and the donor is never shown. The stored record is untouched. */
export const FUND_VOCAB = { funding: "Fund", received: "Gifts received", spent: "Spent (approved)", evidence: "Evidence" };
export const FUND_LIMIT = "This view does not judge whether a fund is spent as intended, and it never shows who gave. Enter a general description (for example \"Congregation\") rather than a person's name when you record the source.";
/** The server can hide who gave (donor is then "Not recorded"). Never print that as if it were a donor's name. */
export const hasDonor = (g) => !!g.donor && g.donor !== "Not recorded";
export const isFund = (mode) => mode === "fund";
export const GRANT_ORDER = ["funding", "received", "spent", "evidence"];
export const GRANT_LIMIT = "This view does not judge whether donor conditions are met, and it does not prove the grant produced any programme result. Results shown under Programme results are matched only by a typed reference.";

const step = (key, state, stateLabel, title, meta) => ({ key, state, stateLabel: stateLabel || null, title: title || null, meta: meta || null });
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

export function sentence(g, mode) {
  if (!g) return null;
  const c = g.currency, none = /^0+(\.0+)?$/;
  const wait = g.pending && !none.test(g.pending) ? ` ${money(g.pending)} ${c} more is waiting for a second person to approve it.` : "";
  if (isFund(mode)) return `Of the ${money(g.amount)} ${c} set aside for ${g.restricted ? "this designated fund" : "this fund"}, ${money(g.received)} ${c} has been received and ${money(g.spent)} ${c} of spending is approved.${wait} ${money(g.remaining)} ${c} is still unspent.`;
  return `Of the ${money(g.amount)} ${c} awarded${hasDonor(g) ? ` by ${g.donor}` : ""}${g.restricted ? " (restricted)" : ""}, ${money(g.received)} ${c} has been received and ${money(g.spent)} ${c} of spending is approved.${wait} ${money(g.remaining)} ${c} of the award is still unspent.`;
}

export function fundingStep(g, mode) {
  const fund = isFund(mode);
  const terms = g.restricted ? (fund ? "Designated: it may be spent only for its stated purpose." : "Restricted: it may be spent only as the grant's conditions say.") : (fund ? "Not designated to a particular purpose." : "Not restricted to particular purposes.");
  const cond = g.conditions ? ` ${fund ? "Purpose as entered" : "Conditions as entered"}: ${g.conditions}` : ` ${fund ? "No purpose was entered." : "No conditions were entered."}`;
  const title = fund ? `${g.ref} ${g.title}: ${money(g.amount)} ${g.currency}` : `${g.ref} ${g.title}: ${money(g.amount)} ${g.currency}${hasDonor(g) ? ` from ${g.donor}` : ""}`;
  if (g.status !== "ACTIVE") return step("funding", "linked", "Closed", title, `${terms}${cond}`);
  if (g.expired) return step("funding", "pending", "Past its end date", title, `Ended ${g.end} and still active. ${terms}${cond}`);
  return step("funding", "linked", fund ? "Set up" : "Awarded", title, `${g.start} to ${g.end}. ${terms}${cond}`);
}

export function receivedStep(g, mode) {
  const list = g.receipts || [];
  if (!list.length) return step("received", "missing", isFund(mode) ? "No gifts recorded yet" : "No cash received yet", null, isFund(mode) ? "No receipt has been recorded against this fund." : "No receipt has been recorded against this grant.");
  const meta = list.map((r) => `${money(r.amount)} on ${r.date} (${r.reference})`).join("; ") + ".";
  const title = `${money(g.received)} of ${money(g.amount)} ${g.currency}`;
  return g.received === g.amount ? step("received", "linked", "Received in full", title, meta) : step("received", "pending", "Partly received", title, meta);
}

export function spentStep(g, mode) {
  const live = (g.spend || []).filter((s) => s.status !== "REJECTED");
  const approved = live.filter((s) => s.status === "APPROVED"), waiting = live.filter((s) => s.status === "PROPOSED");
  if (!live.length) return step("spent", "missing", "Nothing spent yet", null, isFund(mode) ? "No spending has been recorded against this fund." : "No spending has been recorded against this grant.");
  const over = g.overspent_vs_received ? " Approved spending is more than the cash recorded as received." : "";
  const title = `${money(g.spent)} ${g.currency} approved in ${plural(approved.length, "entry", "entries")}`;
  const meta = `${waiting.length ? `${plural(waiting.length, "entry is", "entries are")} waiting for a different person to approve it (${money(g.pending)} ${g.currency}). ` : ""}Approval records that a second person reviewed it.${over}`;
  if (g.overspent_vs_received) return step("spent", "missing", "More spent than received", title, meta);
  if (waiting.length) return step("spent", "pending", "Some waiting for approval", title, meta);
  return step("spent", "linked", "Approved", title, meta);
}

export function evidenceStep(g) {
  const live = (g.spend || []).filter((s) => s.status !== "REJECTED");
  if (!live.length) return step("evidence", "missing", "Nothing to evidence yet", null, "No spending has been recorded yet.");
  const without = live.filter((s) => !(s.evidence || []).length);
  if (!without.length) return step("evidence", "linked", "Linked", `Evidence on all ${plural(live.length, "spending entry", "spending entries")}`, null);
  const title = `${without.length} of ${plural(live.length, "spending entry", "spending entries")} without evidence`;
  const meta = `Without evidence: ${without.map((s) => s.reference || s.description).join(", ")}.`;
  return step("evidence", without.length === live.length ? "missing" : "pending", "Not linked yet", title, meta);
}

/** `grant` is a grant exactly as Public Finance returns it. Returns null when there is none. */
export function buildGrantTrace(grant, mode) {
  if (!grant) return null;
  return { grant, mode: isFund(mode) ? "fund" : "grant", steps: [fundingStep(grant, mode), receivedStep(grant, mode), spentStep(grant, mode), evidenceStep(grant)], sentence: sentence(grant, mode), spend: grant.spend || [] };
}
