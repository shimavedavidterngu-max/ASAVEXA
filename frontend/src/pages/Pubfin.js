import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState, EmptyState } from "../components/DataState.js";
import { ProofRail } from "../components/ProofRail.js";
import { buildLineTrace, SPEND_VOCAB, isExpense } from "../lib/spendTrace.js";
import { programmeLink, PROGRAMME_LIMIT } from "../lib/programmeLink.js";
import { buildGrantTrace, GRANT_VOCAB, GRANT_LIMIT, FUND_VOCAB, FUND_LIMIT } from "../lib/grantTrace.js";
import { TABS, canPrepare, canApprove, statusOf, money, budgetMoves, virementMoves, procMoves, spendMoves, reportMoves } from "../lib/pubfin.js";

/**
 * Financial Management and Public Finance. ACTUAL figures come only from the posted ledger; COMMITTED figures are open commitments.
 * Every approval is by a second person and the page says so. Procurement thresholds are the organisation's own policy, never law.
 */
const Badge = ({ tone, label, id }) => h("span", { className: `badge badge-${tone || "neutral"}`, id }, label);
const St = (s, id) => Badge({ ...statusOf(s), id });
const note = (t, kind = "info") => (t ? h("div", { className: `alert alert-${kind}`, style: "margin-bottom:12px;", role: kind === "error" ? "alert" : "status" }, t) : null);
const field = (label, id, inp, hint) => h("div", { className: "field" }, h("label", { for: id }, label), inp, hint ? h("small", { style: "color: var(--ink-500);" }, hint) : null);
const text = (id, f, k, on, ph) => h("input", { id, type: "text", value: f[k] == null ? "" : f[k], placeholder: ph || "", onInput: (e) => on(k, e.target.value) });
const area = (id, f, k, on, rows = 2) => h("textarea", { id, rows, onInput: (e) => on(k, e.target.value) }, f[k] || "");
const sel = (id, value, on, opts, blank) => h("select", { id, onChange: (e) => on(e.target.value) }, [...(blank ? [h("option", { value: "" }, blank)] : []), ...opts.map(([v, l]) => h("option", { value: v, selected: String(value) === String(v) }, l))]);
const table = (head, rows, id) => h("div", { className: "table-scroll" }, h("table", { className: "data-table", id }, h("thead", {}, h("tr", {}, head.map(([l, right]) => h("th", { style: right ? "text-align:right;" : undefined }, l)))), h("tbody", {}, rows)));
const td = (v, right) => h("td", { style: right ? "text-align:right;" : undefined }, v);
const btn = (label, id, onClick, kind = "secondary", disabled = false) => h("button", { className: `btn btn-${kind}`, id, disabled, onClick }, label);
const row = (...b) => h("div", { style: "display:flex; gap:8px; flex-wrap:wrap; margin:8px 0;" }, b.filter(Boolean));
const checks = (idp, ids, items, onToggle, label) => h("div", {}, items.length === 0 ? h("small", { style: "color: var(--ink-500);" }, "Nothing available to link.") : items.map((c) =>
  h("label", { style: "display:block;" }, h("input", { type: "checkbox", id: `${idp}-${c.id}`, checked: ids.includes(c.id), onChange: () => onToggle(c.id) }), ` ${label(c)}`)));
const noteBox = (pf, key, a, label, id) => field(label, id, area(id, pf.notes, key, a.noteChange));
const hist = (items, id) => h("ul", { id }, (items || []).map((x) => h("li", {}, `${String(x.at).slice(0, 10)} ${x.event.replace(/_/g, " ").toLowerCase()} by ${x.by}${x.note ? ": " + x.note : ""}`)));

export function Pubfin({ pf, role, userId, loading, onRetry, actions, sector }) {
  const mode = sector === "church" ? "fund" : "grant";
  return h("div", {},
    h("h1", {}, "Financial Management and Public Finance"),
    note("ACTUAL figures come only from posted journals. Approvals are by a second person and are not an audit opinion or a legal certification. Procurement thresholds are your own policy settings, not law.", "warning"),
    pf.error ? ErrorState({ message: pf.error, onRetry }) : null,
    note(pf.notice, "success"),
    loading ? LoadingState() : h("div", {},
      h("div", { className: "tabs", role: "tablist", style: "display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px;" },
        TABS.map(([id, label]) => h("button", { className: `btn ${pf.tab === id ? "btn-primary" : "btn-secondary"}`, role: "tab", id: `pf-tab-${id}`, "aria-selected": pf.tab === id ? "true" : "false", onClick: () => actions.setTab(id) }, id === "follow" && mode === "fund" ? "Follow a fund" : label))),
      pf.busy ? h("div", { style: "color: var(--ink-500);" }, "Working...") : null,
      pf.tab === "overview" ? overview(pf, role, actions) : pf.tab === "spend" ? spend(pf, actions) : pf.tab === "budgets" ? budgets(pf, role, userId, actions) : pf.tab === "commitments" ? commitments(pf, role, actions)
        : pf.tab === "procurement" ? procurement(pf, role, userId, actions) : pf.tab === "grants" ? grants(pf, role, userId, actions, mode) : pf.tab === "follow" ? follow(pf, actions, mode, role) : reports(pf, role, userId, actions)));
}

// ---------------------------------------------------------------- overview
function overview(pf, role, a) {
  const o = pf.ov;
  if (!o) return EmptyState({ title: "No data yet", message: "Create a budget to begin." });
  const c = o.counts, p = pf.policyForm;
  return h("div", { id: "pf-overview" },
    h("div", { className: "card", style: "margin-bottom:12px;" }, h("h3", {}, "At a glance"),
      h("div", { id: "pf-counts" }, `${c.budgets_approved} approved budget(s), ${c.budgets_waiting} waiting for approval; ${c.commitments_open} open commitment(s); ${c.procurements_open} open procurement(s), ${c.awards_waiting} award(s) waiting; ${c.grants_active} active grant(s); ${c.spend_waiting} grant spending entr${c.spend_waiting === 1 ? "y" : "ies"} waiting; ${c.virements_waiting} virement(s) waiting.`)),
    h("div", { className: "card", style: "margin-bottom:12px;" }, h("h3", {}, "Needs attention"),
      h("h4", {}, "Budget lines spent or committed beyond the budget"), o.overspent_lines.length ? h("ul", { id: "pf-overspent" }, o.overspent_lines.map((x) => h("li", {}, `${x.budget_ref} ${x.code} ${x.name}: available ${money(x.available)}`))) : h("div", { style: "color: var(--ink-500);" }, "None."),
      h("h4", {}, "Grants past their end date and still active"), o.grants_expired.length ? h("ul", {}, o.grants_expired.map((x) => h("li", {}, `${x.ref} ${x.title}: ended ${x.end}, ${money(x.remaining)} unspent`))) : h("div", { style: "color: var(--ink-500);" }, "None."),
      h("h4", {}, "Grants where approved spending is more than cash received"), o.grants_overspent_vs_received.length ? h("ul", {}, o.grants_overspent_vs_received.map((x) => h("li", {}, `${x.ref} ${x.title}: spent ${money(x.spent)}, received ${money(x.received)}`))) : h("div", { style: "color: var(--ink-500);" }, "None.")),
    h("div", { className: "card", style: "margin-bottom:12px;" }, h("h3", {}, "Procurement policy"), h("div", { id: "pf-policy" }, o.policy.meaning),
      canApprove(role) && p ? h("div", { style: "margin-top:8px;" }, field("Minimum quotes (1 to 10)", "pol-q", text("pol-q", p, "min_quotes", a.policyChange)), field("Quotes needed from this estimated value (0 = always)", "pol-t", text("pol-t", p, "quote_threshold", a.policyChange)), btn("Save policy", "pol-save", () => a.savePolicy(), "secondary", pf.busy)) : null),
    privacyCard(pf, role, a),
    h("div", { className: "card" }, h("h3", {}, "What this does not tell you"), h("ul", {}, o.limitations.map((l) => h("li", {}, l)))));
}

function privacyCard(pf, role, a) {
  const pr = pf.options && pf.options.privacy;
  if (!pr) return null;
  return h("div", { className: "card", id: "pf-privacy", style: "margin-bottom:12px;" }, h("h3", {}, "Who gave"),
    h("div", { id: "pf-privacy-state" }, pr.hide_donor ? "Hidden. " + pr.meaning : "Shown. " + pr.meaning),
    canApprove(role) ? h("div", { style: "margin-top:8px;" }, btn(pr.hide_donor ? "Show who gave" : "Hide who gave", "pf-privacy-toggle", () => a.setPrivacy(!pr.hide_donor), "secondary", pf.busy)) : null,
    canApprove(role) && pr.hide_donor ? h("div", { id: "pf-erase", style: "margin-top:12px;" },
      h("p", { style: "color: var(--ink-500);" }, "Names stored before hiding was turned on are hidden, not erased. You can erase them for good. This cannot be undone. Submitted reports keep their fingerprinted copy, which stays hidden."),
      field('Type ERASE to confirm', "pf-erase-word", text("pf-erase-word", pf.eraseForm || { word: "" }, "word", (k, v) => a.eraseChange(v))),
      btn("Erase stored donor names", "pf-erase-go", () => a.eraseDonors(), "secondary", pf.busy)) : null);
}

// ---------------------------------------------------------------- budgets
function budgets(pf, role, userId, a) {
  if (pf.budgetForm) return budgetFormView(pf, a);
  if (pf.budget) return budgetDetail(pf, role, userId, a);
  return h("div", { id: "pf-budgets" }, canPrepare(role) ? btn("New budget", "bud-new", () => a.newBudget(), "primary") : null,
    pf.budgets.length === 0 ? EmptyState({ title: "No budgets yet", message: "A budget lists, for a period, what each expense and revenue account is expected to be." })
      : table([["Ref"], ["Name"], ["Period"], ["Expense budget", true], ["Status"], [""]], pf.budgets.map((b) => h("tr", { "data-budget": b.id }, td(b.ref), td(b.name), td(`${b.start} to ${b.end}`), td(`${b.currency} ${money(b.total_expense)}`, true), td(St(b.status)), td(btn("Open", `bud-open-${b.id}`, () => a.openBudget(b.id))))), "pf-budget-table"));
}

function budgetFormView(pf, a) {
  const f = pf.budgetForm;
  return h("div", { className: "card", id: "budget-form" }, h("h3", {}, f.id ? "Edit budget" : "New budget"),
    field("Name", "bf-name", text("bf-name", f, "name", a.budgetChange, "for example Operations 2026")), field("Description", "bf-desc", area("bf-desc", f, "description", a.budgetChange)),
    field("Starts", "bf-start", text("bf-start", f, "start", a.budgetChange, "2026-01-01")), field("Ends", "bf-end", text("bf-end", f, "end", a.budgetChange, "2026-12-31")), field("Currency", "bf-cur", text("bf-cur", f, "currency", a.budgetChange)),
    h("h4", {}, "Amounts by account (leave blank to leave an account out)"),
    table([["Account"], ["Type"], ["Amount", true]], pf.options.accounts.map((x) => h("tr", {}, td(`${x.code} ${x.name}`), td(x.type.toLowerCase()), td(h("input", { id: `bf-amt-${x.id}`, type: "text", value: f.amounts[x.id] || "", style: "text-align:right; max-width:140px;", onInput: (e) => a.budgetAmount(x.id, e.target.value) })))), "bf-lines"),
    row(btn("Save draft", "bf-save", () => a.saveBudget(), "primary", pf.busy), btn("Cancel", "bf-cancel", () => a.cancelBudget())));
}

function budgetDetail(pf, role, userId, a) {
  const b = pf.budget, m = budgetMoves(b, role, userId), ex = b.execution;
  return h("div", { id: "pf-budget" }, btn("Back to budgets", "bud-back", () => a.closeBudgetView()),
    h("h2", {}, `${b.ref}: ${b.name} `, St(b.status, "bud-status")),
    h("div", { className: "card", style: "margin-bottom:12px;" }, h("div", {}, `${b.start} to ${b.end}, ${b.currency}. Prepared by ${b.created_by}.`), b.description ? h("p", {}, b.description) : null,
      b.decided_by ? h("div", {}, `Decided by ${b.decided_by}${b.decision_note ? ": " + b.decision_note : ""}.`) : null, b.fingerprint ? h("small", {}, `Fingerprint ${b.fingerprint.slice(0, 16)}...`) : null),
    row(m.edit ? btn("Edit", "bud-edit", () => a.editBudget()) : null, m.submit ? btn("Submit for approval", "bud-submit", () => a.submitBudget(), "primary", pf.busy) : null, m.discard ? btn("Discard draft", "bud-discard", () => a.discardBudget()) : null,
      m.virement && !pf.virementForm ? btn("Move money between lines", "vir-new", () => a.newVirement()) : null, m.virement && !pf.commitForm ? btn("Record a commitment", "bud-commit", () => a.newCommit(b.id)) : null),
    m.decide ? h("div", { className: "card", id: "bud-decide", style: "margin-bottom:12px;" }, h("h3", {}, "Decide on this budget"), noteBox(pf, "decide", a, "Note (required to send back)", "bd-note"),
      row(btn("Approve", "bd-approve", () => a.decideBudget(true), "primary", pf.busy), btn("Send back", "bd-reject", () => a.decideBudget(false), "secondary", pf.busy))) : null,
    m.ownSubmission ? note("You submitted this budget, so a different person must decide it.") : null,
    m.close ? h("div", { className: "card", style: "margin-bottom:12px;" }, noteBox(pf, "close", a, "Closing note (when the period is finished)", "bc-note"), btn("Close budget", "bc-save", () => a.closeBudget(), "secondary", pf.busy)) : null,
    pf.virementForm ? virementForm(pf, a) : null, pf.commitForm ? commitForm(pf, a) : null,
    ex ? execTable(ex) : table([["Account"], ["Type"], ["Amount", true]], b.lines.map((l) => h("tr", {}, td(`${l.code} ${l.name}`), td(l.type.toLowerCase()), td(money(l.amount), true))), "pf-draft-lines"),
    b.virements.length ? h("div", {}, h("h3", {}, "Virements (moves between lines)"), table([["From"], ["To"], ["Amount", true], ["Why"], ["Status"], [""]], b.virements.map((v) => { const mv = virementMoves(v, role, userId), nm = (id) => { const l = b.lines.find((x) => x.account_id === id); return l ? `${l.code} ${l.name}` : id; };
      return h("tr", { "data-virement": v.id }, td(nm(v.from_account)), td(nm(v.to_account)), td(money(v.amount), true), td(v.reason), td(St(v.status)), td(mv.decide ? row(btn("Approve", `vir-ok-${v.id}`, () => a.decideVirement(v.id, true), "primary", pf.busy), btn("Send back", `vir-no-${v.id}`, () => a.decideVirement(v.id, false), "secondary", pf.busy)) : mv.own ? h("small", {}, "You proposed this, so someone else decides.") : null)); }), "pf-virements"),
      b.virements.some((v) => v.status === "PROPOSED") && canApprove(role) ? noteBox(pf, "virement", a, "Note for the virement decision (required to send back)", "vir-note") : null) : null,
    h("h3", {}, "History"), hist(b.history, "bud-history"));
}

function execTable(ex) {
  return h("div", {}, h("h3", {}, "Budget against ACTUAL (posted ledger) and committed"), h("small", { style: "color: var(--ink-500);" }, `${ex.basis}. ${ex.journals_examined} posted journal(s) in the period.`),
    table([["Account"], ["Type"], ["Budget", true], ["ACTUAL", true], ["Committed", true], ["Available", true], ["Used %", true]], [...ex.rows.map((r) => h("tr", { "data-line": r.code, className: r.overspent ? "row-warn" : "" }, td(`${r.code} ${r.name}`), td(r.type.toLowerCase()),
      td(money(r.budget) + (r.adjustment !== "0.00" ? ` (${money(r.approved)} ${r.adjustment.startsWith("-") ? "" : "+"}${money(r.adjustment)})` : ""), true), td(money(r.actual), true), td(r.committed == null ? "—" : money(r.committed), true),
      td(r.available == null ? "—" : money(r.available) + (r.overspent ? " OVER" : ""), true), td(r.used_pct == null ? "—" : r.used_pct + "%", true))),
      h("tr", { id: "pf-exec-total" }, td(h("strong", {}, "Expense total")), td(""), td(money(ex.expense_totals.budget), true), td(money(ex.expense_totals.actual), true), td(money(ex.expense_totals.committed), true), td(money(ex.expense_totals.available), true), td(""))], "pf-exec"));
}

function virementForm(pf, a) {
  const f = pf.virementForm, lines = pf.budget.lines.filter((l) => l.type === "EXPENSE").map((l) => [l.account_id, `${l.code} ${l.name}`]);
  return h("div", { className: "card", id: "virement-form", style: "margin:12px 0;" }, h("h3", {}, "Move money between expense lines"),
    field("Take from", "vf-from", sel("vf-from", f.from_account, (v) => a.virementChange("from_account", v), lines, "Choose a line")), field("Give to", "vf-to", sel("vf-to", f.to_account, (v) => a.virementChange("to_account", v), lines, "Choose a line")),
    field("Amount", "vf-amt", text("vf-amt", f, "amount", a.virementChange)), field("Why", "vf-reason", area("vf-reason", f, "reason", a.virementChange)),
    h("small", {}, "A different person must approve this before the budget changes."), row(btn("Propose", "vf-save", () => a.saveVirement(), "primary", pf.busy), btn("Cancel", "vf-cancel", () => a.cancelVirement())));
}

// ---------------------------------------------------------------- commitments
function commitForm(pf, a) {
  const f = pf.commitForm, b = pf.budgets.find((x) => x.id === f.budget_id), lines = b ? b.lines.filter((l) => l.type === "EXPENSE").map((l) => [l.account_id, `${l.code} ${l.name}`]) : [];
  return h("div", { className: "card", id: "commit-form", style: "margin:12px 0;" }, h("h3", {}, "Record a commitment"),
    h("p", {}, "A commitment sets money aside for something ordered. It cannot be more than what is still available on the line."),
    !f.fixedBudget ? field("Budget", "cf-budget", sel("cf-budget", f.budget_id, (v) => a.commitChange("budget_id", v), pf.budgets.filter((x) => x.status === "APPROVED").map((x) => [x.id, `${x.ref} ${x.name}`]), "Choose a budget")) : null,
    field("Expense line", "cf-line", sel("cf-line", f.account_id, (v) => a.commitChange("account_id", v), lines, "Choose a line")), field("Vendor or payee", "cf-vendor", text("cf-vendor", f, "vendor", a.commitChange)),
    field("What it is for", "cf-desc", text("cf-desc", f, "description", a.commitChange)), field("Amount", "cf-amt", text("cf-amt", f, "amount", a.commitChange)), field("Date", "cf-date", text("cf-date", f, "date", a.commitChange, "2026-02-10")),
    h("div", { className: "field" }, h("label", {}, "Evidence (optional)"), checks("cf-ev", f.evidence_ids, pf.vault, a.commitEvidence, (e) => e.original_filename)),
    row(btn("Record", "cf-save", () => a.saveCommit(), "primary", pf.busy), btn("Cancel", "cf-cancel", () => a.cancelCommit())));
}

function commitments(pf, role, a) {
  const s = pf.settleForm;
  return h("div", { id: "pf-commitments" }, canPrepare(role) && !pf.commitForm ? btn("Record a commitment", "com-new", () => a.newCommit(""), "primary") : null, pf.commitForm ? commitForm(pf, a) : null,
    s ? h("div", { className: "card", id: "settle-form", style: "margin:12px 0;" }, h("h3", {}, "Settle a commitment"), h("p", {}, "Settle after the invoice is posted to the ledger, so the spending moves from committed to ACTUAL."),
      field("Amount actually paid or invoiced", "sf-amt", text("sf-amt", s, "settled_amount", a.settleChange)), field("Note, such as the journal number", "sf-note", text("sf-note", s, "note", a.settleChange)), row(btn("Settle", "sf-save", () => a.saveSettle(), "primary", pf.busy), btn("Cancel", "sf-cancel", () => a.cancelSettle()))) : null,
    pf.cancelCommitId ? h("div", { className: "card", id: "cancel-commit", style: "margin:12px 0;" }, noteBox(pf, "cancelCommit", a, "Why is it being cancelled?", "cc-note"), row(btn("Cancel the commitment", "cc-save", () => a.confirmCancelCommit(), "secondary", pf.busy), btn("Keep it", "cc-keep", () => a.keepCommit()))) : null,
    pf.commitments.length === 0 ? EmptyState({ title: "No commitments", message: "Record a commitment when you order something against an approved budget." })
      : table([["Ref"], ["Budget"], ["Line"], ["Vendor"], ["What for"], ["Amount", true], ["Status"], [""]], pf.commitments.map((c) => h("tr", { "data-commitment": c.id }, td(c.ref), td(c.budget_ref), td(c.code), td(c.vendor), td(c.description), td(money(c.amount), true),
        td(h("span", {}, St(c.status), c.settled_amount ? ` paid ${money(c.settled_amount)}` : "")), td(canPrepare(role) && c.status === "OPEN" ? row(btn("Settle", `com-settle-${c.id}`, () => a.openSettle(c), "primary"), btn("Cancel", `com-cancel-${c.id}`, () => a.askCancelCommit(c.id))) : null))), "pf-commit-table"));
}

// ---------------------------------------------------------------- procurement
function procurement(pf, role, userId, a) {
  if (pf.procForm) return h("div", { className: "card", id: "proc-form" }, h("h3", {}, "New procurement"), field("Budget", "pr-budget", sel("pr-budget", pf.procForm.budget_id, (v) => a.procChange("budget_id", v), pf.budgets.filter((x) => x.status === "APPROVED").map((x) => [x.id, `${x.ref} ${x.name}`]), "Choose a budget")),
    field("Expense line", "pr-line", sel("pr-line", pf.procForm.account_id, (v) => a.procChange("account_id", v), ((pf.budgets.find((x) => x.id === pf.procForm.budget_id) || { lines: [] }).lines).filter((l) => l.type === "EXPENSE").map((l) => [l.account_id, `${l.code} ${l.name}`]), "Choose a line")),
    field("What is being bought", "pr-title", text("pr-title", pf.procForm, "title", a.procChange)), field("Details", "pr-desc", area("pr-desc", pf.procForm, "description", a.procChange)), field("Estimated cost", "pr-est", text("pr-est", pf.procForm, "estimate", a.procChange)),
    row(btn("Create", "pr-save", () => a.saveProc(), "primary", pf.busy), btn("Cancel", "pr-cancel", () => a.cancelProc())));
  if (pf.proc) return procDetail(pf, role, userId, a);
  return h("div", { id: "pf-procurement" }, canPrepare(role) ? btn("New procurement", "proc-new", () => a.newProc(), "primary") : null,
    pf.procs.length === 0 ? EmptyState({ title: "No procurements", message: "Start one when you need quotes before buying." })
      : table([["Ref"], ["What"], ["Estimate", true], ["Quotes", true], ["Status"], [""]], pf.procs.map((p) => h("tr", { "data-proc": p.id }, td(p.ref), td(p.title), td(money(p.estimate), true), td(String(p.quotes.length), true), td(St(p.status)), td(btn("Open", `proc-open-${p.id}`, () => a.openProc(p.id))))), "pf-proc-table"));
}

function procDetail(pf, role, userId, a) {
  const p = pf.proc, m = procMoves(p, role, userId), q = pf.quoteForm, aw = pf.awardForm, lowest = p.quotes.length ? Math.min(...p.quotes.map((x) => Number(x.amount))) : null;
  return h("div", { id: "pf-proc" }, btn("Back to procurements", "proc-back", () => a.closeProcView()), h("h2", {}, `${p.ref}: ${p.title} `, St(p.status, "proc-status")),
    h("div", { className: "card", style: "margin-bottom:12px;" }, h("div", {}, `${p.budget_ref}, line ${p.code}. Estimated ${money(p.estimate)}.`), p.description ? h("p", {}, p.description) : null,
      p.commitment_ref ? h("div", { id: "proc-commitment" }, `Awarded to ${p.award.vendor}. Commitment ${p.commitment_ref} created.`) : null),
    h("div", { className: "card", style: "margin-bottom:12px;" }, h("small", {}, pf.ov ? pf.ov.policy.meaning : "")),
    h("h3", {}, "Quotes"), p.quotes.length === 0 ? h("div", { style: "color: var(--ink-500);" }, "No quotes yet.") : table([["Vendor"], ["Amount", true], ["Note"], [""]], p.quotes.map((x) => h("tr", { "data-quote": x.id }, td(x.vendor), td(money(x.amount), true), td(x.note || ""), td(Number(x.amount) === lowest ? Badge({ tone: "pass", label: "Lowest" }) : null))), "pf-quotes"),
    m.quote && !q ? btn("Add a quote", "quote-new", () => a.newQuote()) : null,
    q ? h("div", { className: "card", id: "quote-form", style: "margin:12px 0;" }, field("Vendor", "qf-vendor", text("qf-vendor", q, "vendor", a.quoteChange)), field("Quoted amount", "qf-amt", text("qf-amt", q, "amount", a.quoteChange)), field("Note", "qf-note", text("qf-note", q, "note", a.quoteChange)),
      row(btn("Save quote", "qf-save", () => a.saveQuote(), "primary", pf.busy), btn("Cancel", "qf-cancel", () => a.cancelQuote()))) : null,
    m.award && !aw ? btn("Propose an award", "award-new", () => a.newAward(), "primary") : null,
    aw ? h("div", { className: "card", id: "award-form", style: "margin:12px 0;" }, h("h3", {}, "Propose an award"), field("Quote to award", "aw-quote", sel("aw-quote", aw.quote_id, (v) => a.awardChange("quote_id", v), p.quotes.map((x) => [x.id, `${x.vendor} ${money(x.amount)}`]), "Choose a quote")),
      field("Why this one (required if it is not the lowest)", "aw-just", area("aw-just", aw, "justification", a.awardChange)), field("Exception reason (required if there are fewer quotes than policy)", "aw-exc", area("aw-exc", aw, "exception_reason", a.awardChange)),
      h("small", {}, "A different person must approve before any money is committed."), row(btn("Propose", "aw-save", () => a.saveAward(), "primary", pf.busy), btn("Cancel", "aw-cancel", () => a.cancelAward()))) : null,
    p.award && p.status !== "OPEN" ? h("div", { className: "card", id: "award-box", style: "margin:12px 0;" }, h("div", {}, `Award proposed to ${p.award.vendor} for ${money(p.award.amount)} by ${p.award.proposed_by}.`), p.award.flags.length ? h("div", { id: "award-flags" }, p.award.flags.join("; ")) : null,
      p.award.justification ? h("div", {}, `Why: ${p.award.justification}`) : null, p.award.exception_reason ? h("div", {}, `Exception: ${p.award.exception_reason}`) : null) : null,
    m.decide ? h("div", { className: "card", id: "award-decide", style: "margin:12px 0;" }, noteBox(pf, "award", a, "Note (required to send back)", "ad-note"), row(btn("Approve award", "ad-approve", () => a.decideAward(true), "primary", pf.busy), btn("Send back", "ad-reject", () => a.decideAward(false), "secondary", pf.busy))) : null,
    m.own ? note("You proposed this award, so a different person must decide it.") : null,
    m.cancel ? h("div", { className: "card", style: "margin:12px 0;" }, noteBox(pf, "procCancel", a, "Reason for cancelling", "pc-note"), btn("Cancel procurement", "pc-save", () => a.cancelProcurement(), "secondary", pf.busy)) : null,
    h("h3", {}, "History"), hist(p.history, "proc-history"));
}

// ---------------------------------------------------------------- grants
function grants(pf, role, userId, a, mode) {
  const fund = mode === "fund";
  if (pf.grantForm) { const f = pf.grantForm; return h("div", { className: "card", id: "grant-form" }, h("h3", {}, "New grant"), field("Title", "gf-title", text("gf-title", f, "title", a.grantChange)), field(fund ? "Source (a general description such as \"Congregation\"; never a person's name)" : "Donor", "gf-donor", text("gf-donor", f, "donor", a.grantChange)),
    field("Award amount", "gf-amt", text("gf-amt", f, "amount", a.grantChange)), field("Currency", "gf-cur", text("gf-cur", f, "currency", a.grantChange)), field("Programme reference (optional, to match impact indicators)", "gf-prog", text("gf-prog", f, "programme_ref", a.grantChange, "for example WASH-01")), field("Starts", "gf-start", text("gf-start", f, "start", a.grantChange, "2026-01-01")), field("Ends", "gf-end", text("gf-end", f, "end", a.grantChange, "2026-12-31")),
    field("Conditions (text you copy from the agreement)", "gf-cond", area("gf-cond", f, "conditions", a.grantChange, 3)), row(btn("Create", "gf-save", () => a.saveGrant(), "primary", pf.busy), btn("Cancel", "gf-cancel", () => a.cancelGrant()))); }
  if (pf.grant) return grantDetail(pf, role, userId, a, mode);
  return h("div", { id: "pf-grants" }, fund ? h("div", { className: "alert alert-info", id: "pf-grants-private", role: "status", style: "margin-bottom:12px;" }, "Who gave is not shown on this page for faith-based organisations.") : null, canPrepare(role) ? btn("New grant", "grant-new", () => a.newGrant(), "primary") : null,
    pf.grants.length === 0 ? EmptyState({ title: "No grants", message: "Record a grant to track receipts and approved spending against the award." })
      : table([["Ref"], ["Title"], ...(fund ? [] : [["Donor"]]), ["Award", true], ["Spent", true], ["Used %", true], ["Status"], [""]], pf.grants.map((g) => h("tr", { "data-grant": g.id }, td(g.ref), td(g.title), ...(fund ? [] : [td(g.donor)]), td(`${g.currency} ${money(g.amount)}`, true), td(money(g.spent), true), td(g.utilisation_pct + "%", true), td(St(g.status)), td(btn("Open", `grant-open-${g.id}`, () => a.openGrant(g.id))))), "pf-grant-table"));
}

function grantDetail(pf, role, userId, a, mode) {
  const fund = mode === "fund";
  const g = pf.grant, r = pf.receiptForm, s = pf.spendForm;
  return h("div", { id: "pf-grant" }, btn("Back to grants", "grant-back", () => a.closeGrantView()), h("h2", {}, `${g.ref}: ${g.title} `, St(g.status, "grant-status")),
    h("div", { className: "card", style: "margin-bottom:12px;" }, h("div", {}, `${fund ? "" : g.donor + ". "}${g.start} to ${g.end}. ${g.restricted ? "Restricted" : "Unrestricted"}.`),
      h("div", { id: "grant-figures" }, `Award ${g.currency} ${money(g.amount)}; received ${money(g.received)}; approved spending ${money(g.spent)} (${g.utilisation_pct}%); waiting ${money(g.pending)}; remaining ${money(g.remaining)}; cash on hand ${money(g.cash_on_hand)}.`),
      g.overspent_vs_received ? note("Approved spending is more than the cash received for this grant.", "warning") : null, g.expired ? note("This grant has passed its end date and is still active.", "warning") : null, g.conditions ? h("p", {}, `Conditions: ${g.conditions}`) : null),
    g.status === "ACTIVE" && canPrepare(role) ? row(!r ? btn("Record cash received", "rec-new", () => a.newReceipt()) : null, !s ? btn("Record spending", "sp-new", () => a.newSpend()) : null) : null,
    r ? h("div", { className: "card", id: "receipt-form", style: "margin:12px 0;" }, field("Amount received", "rf-amt", text("rf-amt", r, "amount", a.receiptChange)), field("Date received", "rf-date", text("rf-date", r, "date", a.receiptChange)), field("Bank or receipt reference", "rf-ref", text("rf-ref", r, "reference", a.receiptChange)),
      row(btn("Save", "rf-save", () => a.saveReceipt(), "primary", pf.busy), btn("Cancel", "rf-cancel", () => a.cancelReceipt()))) : null,
    s ? h("div", { className: "card", id: "spend-form", style: "margin:12px 0;" }, h("h3", {}, "Record spending against this grant"), field("Amount", "sp-amt", text("sp-amt", s, "amount", a.spendChange)), field("Date", "sp-date", text("sp-date", s, "date", a.spendChange)),
      field("What it was for", "sp-desc", text("sp-desc", s, "description", a.spendChange)), field("Journal or voucher reference", "sp-ref", text("sp-ref", s, "reference", a.spendChange)),
      h("div", { className: "field" }, h("label", {}, "Evidence (optional)"), checks("sp-ev", s.evidence_ids, pf.vault, a.spendEvidence, (e) => e.original_filename)),
      h("small", {}, "It counts against the award only after a different person approves it."), row(btn("Save", "sp-save", () => a.saveSpend(), "primary", pf.busy), btn("Cancel", "sp-cancel", () => a.cancelSpend()))) : null,
    h("h3", {}, "Cash received"), g.receipts.length ? table([["Date"], ["Amount", true], ["Reference"], ["By"]], g.receipts.map((x) => h("tr", {}, td(x.date), td(money(x.amount), true), td(x.reference), td(x.by))), "pf-receipts") : h("div", { style: "color: var(--ink-500);" }, "None yet."),
    h("h3", {}, "Spending"), g.spend.length ? table([["Date"], ["What for"], ["Amount", true], ["Entered by"], ["Status"], [""]], g.spend.map((x) => { const mv = spendMoves(x, role, userId);
      return h("tr", { "data-spend": x.id }, td(x.date), td(x.description + (x.evidence.length ? ` (evidence: ${x.evidence.map((e) => e.filename).join(", ")})` : "")), td(money(x.amount), true), td(x.proposed_by), td(St(x.status)),
        td(mv.decide ? row(btn("Approve", `sp-ok-${x.id}`, () => a.decideSpend(x.id, true), "primary", pf.busy), btn("Send back", `sp-no-${x.id}`, () => a.decideSpend(x.id, false), "secondary", pf.busy)) : mv.own ? h("small", {}, "You entered this, so someone else decides.") : null)); }), "pf-spend") : h("div", { style: "color: var(--ink-500);" }, "None yet."),
    g.spend.some((x) => x.status === "PROPOSED") && canApprove(role) ? noteBox(pf, "spend", a, "Note for the decision (required to send back)", "sp-note") : null,
    g.status === "ACTIVE" && canPrepare(role) ? h("div", { className: "card", style: "margin:12px 0;" }, noteBox(pf, "grantClose", a, "Closing note", "gc-note"), btn("Close grant", "gc-save", () => a.closeGrant(), "secondary", pf.busy)) : null,
    h("h3", {}, "History"), hist(g.history, "grant-history"));
}

// ---------------------------------------------------------------- reports
function reports(pf, role, userId, a) {
  if (pf.reportForm) return h("div", { className: "card", id: "report-form" }, h("h3", {}, "New accountability report"), field("Budget", "rp-budget", sel("rp-budget", pf.reportForm.budget_id, (v) => a.reportChange("budget_id", v), pf.budgets.filter((x) => x.status === "APPROVED" || x.status === "CLOSED").map((x) => [x.id, `${x.ref} ${x.name}`]), "Choose a budget")),
    field("Title", "rp-title", text("rp-title", pf.reportForm, "title", a.reportChange)), row(btn("Create", "rp-save", () => a.saveReport(), "primary", pf.busy), btn("Cancel", "rp-cancel", () => a.cancelReport())));
  if (pf.report) { const r = pf.report, m = reportMoves(r, role, userId), ex = r.snapshot && r.snapshot.execution;
    return h("div", { id: "pf-report" }, btn("Back to reports", "rep-back", () => a.closeReportView()), h("h2", {}, `${r.ref}: ${r.title} `, St(r.status, "rep-status")),
      h("div", { className: "card", style: "margin-bottom:12px;" }, h("div", {}, `Budget ${r.budget_ref}. Version ${r.version}.${r.fingerprint ? " Fingerprint " + r.fingerprint.slice(0, 16) + "..." : ""}`), r.decided_by ? h("div", {}, `Decided by ${r.decided_by}${r.decision_note ? ": " + r.decision_note : ""}.`) : null),
      row(m.submit ? btn("Freeze and submit for approval", "rep-submit", () => a.submitReport(), "primary", pf.busy) : null, m.exportable ? btn("Download CSV", "rep-export", () => a.exportReport(), "primary", pf.busy) : null),
      m.decide ? h("div", { className: "card", id: "rep-decide", style: "margin-bottom:12px;" }, noteBox(pf, "report", a, "Note (required to send back)", "rd-note"), row(btn("Approve", "rd-approve", () => a.decideReport(true), "primary", pf.busy), btn("Send back", "rd-reject", () => a.decideReport(false), "secondary", pf.busy))) : null,
      m.own ? note("You submitted this report, so a different person must decide it.") : null,
      ex ? h("div", {}, execTable(ex), h("p", { id: "rep-counts" }, `${r.snapshot.commitments.length} commitment(s), ${r.snapshot.grants.length} grant(s), ${r.snapshot.virements.length} approved virement(s) frozen in this report.`)) : h("div", { style: "color: var(--ink-500);" }, "Nothing is frozen until it is submitted."),
      h("h3", {}, "History"), hist(r.history, "rep-history")); }
  return h("div", { id: "pf-reports" }, canPrepare(role) ? btn("New report", "rep-new", () => a.newReport(), "primary") : null,
    pf.reports.length === 0 ? EmptyState({ title: "No reports", message: "A report freezes a budget's figures, commitments and grants for a second person to approve." })
      : table([["Ref"], ["Title"], ["Budget"], ["Version", true], ["Status"], [""]], pf.reports.map((r) => h("tr", { "data-report": r.id }, td(r.ref), td(r.title), td(r.budget_ref), td(String(r.version), true), td(St(r.status)), td(btn("Open", `rep-open-${r.id}`, () => a.openReport(r.id))))), "pf-report-table"));
}

// ---------------------------------------------------------------- where the money went (Stage 8)
function spend(pf, a) {
  const done = (pf.budgets || []).filter((b) => b.status === "APPROVED" || b.status === "CLOSED");
  const sp = pf.spend || {};
  if (!done.length) return h("div", { className: "card", id: "pf-spend-none" }, EmptyState({ title: "No approved budget yet", message: "Once a budget is approved, this page shows where its money went, line by line, in plain words." }));
  const chosen = done.find((b) => b.id === sp.budgetId) || done[done.length - 1];
  const detail = sp.detail && sp.detail.id === chosen.id ? sp.detail : undefined;
  const exec = detail ? detail.execution : undefined;
  const rows = exec ? exec.rows || [] : [];
  const exp = rows.filter(isExpense), inc = rows.filter((r) => !isExpense(r));
  const row = exp.find((r) => r.account_id === sp.line) || exp[0] || null;
  const tr = detail && row ? buildLineTrace({ detail, commitments: pf.commitments, accountId: row.account_id }) : null;
  const cur = exec ? exec.currency : "";
  return h("div", { id: "pf-spend" },
    h("div", { className: "card" },
      h("p", { style: "color: var(--ink-500);" }, "Pick a budget to see, for each line, what was approved, what is promised, and what has actually been spent (posted to the ledger). Every figure is the one the server recorded; nothing is estimated here. This records and checks; it does not pay anything."),
      field("Budget", "pf-spend-budget", sel("pf-spend-budget", chosen.id, (v) => a.spendBudget(v), done.map((b) => [b.id, `${b.ref} ${b.name} (${b.start} to ${b.end})`]))),
      sp.error ? h("div", { className: "alert alert-warn", id: "pf-spend-unknown", role: "status" }, "Not checked: the figures for this budget could not be loaded. " + sp.error) : null),
    exec ? h("div", { className: "ledger", id: "pf-spend-ledger" },
      h("div", { className: "ledger-main" },
        h("p", { className: "ledger-eyebrow" }, "Where the money went"),
        h("h2", { id: "pf-spend-title" }, `${exec.ref} ${exec.name}`),
        h("p", { className: "hm-muted" }, `${exec.start} to ${exec.end}, in ${cur}. Spent means posted to the ledger.`),
        h("div", { className: "stmt-scroll" }, h("table", { className: "stmt", id: "pf-spend-lines" },
          h("caption", {}, "Spending lines"),
          h("thead", {}, h("tr", {}, [["Line"], ["Authorised", 1], ["Promised", 1], ["Spent", 1], ["Available", 1]].map(([l, r]) => h("th", { scope: "col", className: r ? "num" : undefined }, l)))),
          h("tbody", {}, exp.map((r) => h("tr", { "data-account": r.account_id, "data-state": r.overspent ? "overspent" : "ok" }, h("td", {}, h("div", {}, `${r.code} ${r.name}`), row && row.account_id === r.account_id ? h("small", { "aria-current": "true", className: "hm-muted" }, "Showing") : btn("Follow", `pf-spend-follow-${r.code}`, () => a.spendLine(r.account_id))), h("td", { className: "num" }, money(r.budget)), h("td", { className: "num" }, money(r.committed)), h("td", { className: "num" }, money(r.actual)),
            h("td", { className: "num" }, money(r.available), r.overspent ? h("span", { className: "badge badge-fail", style: "margin-left:6px;" }, "Over budget") : null),
            ))))),
        tr && tr.sentence ? h("p", { id: "pf-spend-sentence", style: "font-size:1.05em; margin-top:12px;" }, tr.sentence) : null,
        tr && tr.commitmentsKnown ? (tr.commitments.length ? h("ul", { id: "pf-spend-commitments" }, tr.commitments.map((c) => h("li", { "data-commitment": c.id }, `${c.ref} ${c.vendor}: ${money(c.amount)} ${cur}, ${c.status === "OPEN" ? "open" : "settled"}. ${(c.evidence || []).length ? `Evidence: ${c.evidence.map((e) => e.filename).join(", ")}.` : "No evidence linked."}`))) : h("p", { className: "hm-muted", id: "pf-spend-no-commitments" }, "Nothing has been promised on this line.")) : null,
        inc.length ? h("div", { className: "stmt-scroll" }, h("table", { className: "stmt", id: "pf-spend-income" },
          h("caption", {}, "Income lines"),
          h("thead", {}, h("tr", {}, [["Line"], ["Expected", 1], ["Posted so far", 1]].map(([l, r]) => h("th", { scope: "col", className: r ? "num" : undefined }, l)))),
          h("tbody", {}, inc.map((r) => h("tr", { "data-account": r.account_id }, h("td", {}, `${r.code} ${r.name}`), h("td", { className: "num" }, money(r.budget)), h("td", { className: "num" }, money(r.actual))))))) : null,
        h("div", { className: "card" }, h("h3", {}, "What this does not tell you"), h("ul", {}, (exec.limitations || []).map((l) => h("li", {}, l))))),
      h("aside", { className: "ledger-margin", "aria-label": "The proof thread for this budget line" },
        tr ? ProofRail({ id: "pf-spend-rail", subject: `${row.code} ${row.name}`, steps: tr.steps, vocab: SPEND_VOCAB }) : null)) : (sp.error ? null : h("div", { className: "card", id: "pf-spend-loading" }, "Loading the figures…")));
}

// ---------------------------------------------------------------- follow a grant (Stage 9)
const SPEND_WORDS = { APPROVED: "approved", PROPOSED: "waiting for a different person to approve it", REJECTED: "sent back" };
function follow(pf, a, mode, role) {
  const fund = mode === "fund";
  const grants = pf.grants || [];
  if (!grants.length) return h("div", { className: "card", id: "pf-follow-none" }, EmptyState({ title: fund ? "No funds yet" : "No grants yet", message: fund ? "Record a fund to follow it from the gifts received to the spending and its evidence." : "Record a grant to follow it from the award to the spending and its evidence." }));
  const g = grants.find((x) => x.id === pf.followId) || grants[grants.length - 1];
  const t = buildGrantTrace(g, mode);
  return h("div", { id: "pf-follow" },
    h("div", { className: "card" },
      h("p", { style: "color: var(--ink-500);" }, fund ? "Follow one fund from the gifts received, to the spending a second person approved, to the evidence behind it. Who gave is never shown here. Every figure is the one the server recorded; nothing is estimated." : "Follow one grant from the award, to the cash received, to the spending a second person approved, to the evidence behind it. Every figure is the one the server recorded; nothing is estimated here."),
      field(fund ? "Fund" : "Grant", "pf-follow-pick", sel("pf-follow-pick", g.id, (v) => a.followGrant(v), grants.map((x) => [x.id, fund ? `${x.ref} ${x.title}` : `${x.ref} ${x.title} (${x.donor})`])))),
    h("div", { className: "ledger", id: "pf-follow-ledger" },
      h("div", { className: "ledger-main" },
        h("p", { className: "ledger-eyebrow" }, fund ? "Follow a fund" : "Follow a grant"),
        h("h2", { id: "pf-follow-title" }, `${g.ref} ${g.title}`),
        h("p", { id: "pf-follow-sentence", style: "font-size:1.05em;" }, t.sentence),
        h("div", { className: "stmt-scroll" }, h("table", { className: "stmt", id: "pf-follow-figures" },
          h("caption", {}, `Figures, in ${g.currency}`),
          h("tbody", {}, [[fund ? "Set aside" : "Awarded", g.amount], ["Received", g.received], ["Approved spending", g.spent], ["Waiting for approval", g.pending], ["Unspent", g.remaining], ["Cash held", g.cash_on_hand]].map(([l, v]) => h("tr", {}, h("th", { scope: "row" }, l), h("td", { className: "num" }, money(v))))))),
        h("h3", {}, "Spending entries"),
        t.spend.length ? h("ul", { id: "pf-follow-spend" }, t.spend.map((s) => h("li", { "data-spend": s.id, "data-status": s.status }, `${money(s.amount)} ${g.currency} on ${s.date}: ${s.description}${s.reference ? ` (${s.reference})` : ""}. ${SPEND_WORDS[s.status] || s.status}. ${(s.evidence || []).length ? `Evidence: ${s.evidence.map((e) => e.filename).join(", ")}.` : "No evidence linked."}`)))
          : h("p", { className: "hm-muted", id: "pf-follow-no-spend" }, "No spending has been recorded against this grant."),
        programmeSection(g, pf, role, a),
        h("p", { className: "hm-muted", id: "pf-follow-limit" }, fund ? FUND_LIMIT : GRANT_LIMIT)),
      h("aside", { className: "ledger-margin", "aria-label": "The proof thread for this grant" },
        ProofRail({ id: "pf-follow-rail", subject: `${fund ? "fund" : "grant"} ${g.ref}`, steps: t.steps, vocab: fund ? FUND_VOCAB : GRANT_VOCAB }))),
    programmeEdit(g, pf, role, a));
}

function programmeSection(g, pf, role, a) {
  const pr = pf.programme, L = programmeLink(g, pr && pr.grantId === g.id ? pr.indicators : undefined);
  return h("div", { id: "pf-follow-programme" }, h("h3", {}, "Programme results"),
    L.kind === "no-ref" ? h("p", { className: "hm-muted", id: "pf-programme-noref" }, "No programme reference has been typed on this grant, so no indicators are matched.")
      : L.kind === "unknown" ? h("p", { className: "hm-muted", id: "pf-programme-unknown" }, `Not checked. The impact indicators for reference ${L.ref} could not be loaded; you may not have permission to see them.`)
      : L.kind === "none" ? h("p", { className: "hm-muted", id: "pf-programme-none" }, `No approved indicator carries the reference ${L.ref}.`)
      : h("ul", { id: "pf-programme-list" }, L.rows.map((x) => h("li", { "data-indicator": x.id, "data-state": x.state }, x.text, x.stale ? " The latest reading is older than your limit." : ""))),
    h("p", { className: "hm-muted", id: "pf-programme-limit" }, PROGRAMME_LIMIT));
}

/** The one place a person changes the reference. Kept outside the read-only ledger. */
function programmeEdit(g, pf, role, a) {
  if (!(canPrepare(role) && g.status === "ACTIVE")) return null;
  const f = pf.progForm && pf.progForm.id === g.id ? pf.progForm : { id: g.id, value: g.programme_ref || "" };
  return h("div", { className: "card", id: "pf-programme-edit" }, field("Programme reference (2 to 40 characters; empty removes it)", "pf-programme-ref", h("input", { id: "pf-programme-ref", type: "text", value: f.value, onInput: (e) => a.progChange(g.id, e.target.value) })),
    btn("Save reference", "pf-programme-save", () => a.saveProgramme(g.id), "secondary", pf.busy));
}
