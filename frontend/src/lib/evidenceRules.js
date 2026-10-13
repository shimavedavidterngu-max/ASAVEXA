/** Pure helpers for the expected-record rules card. No DOM, no network. The server validates everything again; this only words, edits and checks early. */

export const BASELINE_RULE = "ER-001";
export const ACCOUNT_TYPES = [["ASSET", "Assets"], ["LIABILITY", "Liabilities"], ["EQUITY", "Equity"], ["REVENUE", "Revenue"], ["EXPENSE", "Expenses"]];
export const EVIDENCE_TYPES = [["INVOICE", "Invoice"], ["RECEIPT", "Receipt"], ["CONTRACT", "Contract"], ["BANK_STATEMENT", "Bank statement"], ["PURCHASE_ORDER", "Purchase order"],
  ["DELIVERY_NOTE", "Delivery note"], ["PAYROLL_EVIDENCE", "Payroll evidence"], ["TAX_DOCUMENT", "Tax document"], ["APPROVAL_RECORD", "Approval record"], ["OTHER", "Other"]];
export const SEVERITIES = [["HIGH", "High"], ["MEDIUM", "Medium"], ["LOW", "Low"]];
export const MAX_RULES = 25;

const label = (list, v) => (list.find((x) => x[0] === v) || [v, String(v)])[1];

/** "Applies to: revenue · Expects: invoice or contract" */
export function describeRule(r) {
  const to = r.account_types ? r.account_types.map((t) => label(ACCOUNT_TYPES, t).toLowerCase()).join(", ") : "every journal";
  const exp = r.expects_any ? r.expects_any.map((t) => label(EVIDENCE_TYPES, t).toLowerCase()).join(" or ") : "any verified document";
  return { appliesTo: to, expects: exp };
}

/** A copy of the rules to edit, so editing never touches what is in use. */
export const draftFromRules = (rules) => (rules || []).map((r) => ({ id: r.id, name: r.name, account_types: r.account_types ? [...r.account_types] : null, expects_any: r.expects_any ? [...r.expects_any] : null, severity: r.severity || "MEDIUM" }));

export function nextRuleId(draft) {
  const used = new Set((draft || []).map((r) => r.id));
  for (let n = 1; n < 1000; n++) { const id = `ER-${String(n).padStart(3, "0")}`; if (!used.has(id)) return id; }
  return `ER-${Date.now()}`;
}

export const newRule = (draft) => ({ id: nextRuleId(draft), name: "", account_types: [], expects_any: [], severity: "MEDIUM" });

/** Ticks or unticks one value in a list field, keeping the list in the catalogue's order. */
export function toggleValue(rule, field, value) {
  const order = (field === "account_types" ? ACCOUNT_TYPES : EVIDENCE_TYPES).map((x) => x[0]);
  const cur = new Set(rule[field] || []);
  cur.has(value) ? cur.delete(value) : cur.add(value);
  return { ...rule, [field]: order.filter((v) => cur.has(v)) };
}

/** The request body for a proposed change, or the first problem to fix. An empty list of account types means "every journal" only for the baseline rule. */
export function rulesPayload(draft, reason) {
  const why = (reason || "").trim();
  if (!Array.isArray(draft) || !draft.length) return { problem: "There are no rules to propose." };
  if (draft.length > MAX_RULES) return { problem: `A rule set can have at most ${MAX_RULES} rules.` };
  if (!why) return { problem: "Say why the rules are changing." };
  const rules = [];
  for (const r of draft) {
    const name = (r.name || "").trim();
    if (!name) return { problem: `${r.id}: give the rule a name.` };
    if (r.id !== BASELINE_RULE && !(r.account_types && r.account_types.length)) return { problem: `${r.id}: choose at least one kind of account it applies to.` };
    if (r.id !== BASELINE_RULE && !(r.expects_any && r.expects_any.length)) return { problem: `${r.id}: choose at least one kind of evidence it expects.` };
    rules.push({ id: r.id, name, account_types: r.id === BASELINE_RULE ? null : r.account_types, expects_any: r.expects_any && r.expects_any.length ? r.expects_any : null, severity: r.severity || "MEDIUM" });
  }
  if (!rules.some((r) => r.id === BASELINE_RULE)) return { problem: "The baseline rule ER-001 must stay." };
  return { body: { rules, reason: why } };
}

/** Is the draft different from what is in use? Used to disable the button when nothing changed. */
export const draftChanged = (draft, active) => JSON.stringify(rulesPayload(draft, "x").body ? rulesPayload(draft, "x").body.rules : draft) !== JSON.stringify((active || []).map((r) => ({ id: r.id, name: r.name, account_types: r.account_types, expects_any: r.expects_any, severity: r.severity })));

export const RULE_STATUS = { ACTIVE: { tone: "pass", label: "In use" }, PENDING: { tone: "warn", label: "Waiting for approval" }, SUPERSEDED: { tone: "neutral", label: "Replaced" }, REJECTED: { tone: "fail", label: "Rejected" } };
export const ruleStatus = (s) => RULE_STATUS[s] || { tone: "neutral", label: s || "—" };
export const versionLabel = (d) => (!d || d.version === 0 ? "Built-in defaults" : `Version ${d.version}`);
/** Only someone other than the proposer may approve. */
export const canDecide = (pending, me, mayApprove) => !!(pending && mayApprove && me && me !== pending.proposed_by);
