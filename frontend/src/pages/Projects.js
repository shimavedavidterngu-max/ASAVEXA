import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState } from "../components/DataState.js";
import { TABS, ATTENTION_TONE, canPrepare, canApprove, statusOf, words, canEdit, canSubmit, canDecide, canEnter, canDecideEntry, canClose, ownWorkText, ownEntryText } from "../lib/projects.js";

/**
 * Projects and grants. A project has a typed award and budget lines; spending and receipts are proposed by one person and decided by another.
 * It moves no money and applies no funder's rules.
 */
const Badge = ({ tone, label, id }) => h("span", { className: `badge badge-${tone || "neutral"}`, id }, label);
const St = (s) => Badge({ ...statusOf(s) });
const note = (t, kind = "info", id) => (t ? h("div", { className: `alert alert-${kind}`, id, style: "margin-bottom:12px;", role: kind === "error" ? "alert" : "status" }, t) : null);
const field = (l, id, inp) => h("div", { className: "field" }, h("label", { for: id }, l), inp);
const text = (pj, a, form, k, id, ph) => h("input", { id, type: "text", value: (pj.forms[form] || {})[k] == null ? "" : (pj.forms[form] || {})[k], placeholder: ph || "", onInput: (e) => a.setForm(form, k, e.target.value) });
const area = (pj, a, form, k, id, rows = 2) => h("textarea", { id, rows, onInput: (e) => a.setForm(form, k, e.target.value) }, (pj.forms[form] || {})[k] || "");
const sel = (pj, a, form, k, id, opts) => h("select", { id, onChange: (e) => a.setForm(form, k, e.target.value, true) }, opts.map(([v, l]) => h("option", { value: v, selected: String((pj.forms[form] || {})[k]) === String(v) }, l)));
const btn = (l, id, onClick, kind = "secondary", disabled = false) => h("button", { className: `btn btn-${kind}`, id, disabled, onClick }, l);
const row = (...b) => h("div", { style: "display:flex; gap:8px; flex-wrap:wrap; margin:8px 0; align-items:end;" }, b.filter(Boolean));
const none = (t = "None.") => h("div", { style: "color: var(--ink-500);" }, t);
const card = (title, id, ...kids) => h("div", { className: "card", id, style: "margin-bottom:16px;" }, h("h3", {}, title), ...kids);
const hist = (items) => h("ul", {}, (items || []).map((x) => h("li", {}, `${String(x.at).slice(0, 10)} ${String(x.event).replace(/_/g, " ").toLowerCase()} by ${x.by}${x.note ? ": " + x.note : ""}`)));
const noteBox = (pj, a, key, l, id) => field(l, id, h("textarea", { id, rows: 2, onInput: (e) => a.setNote(key, e.target.value) }, pj.notes[key] || ""));
const formError = (pj, name) => (pj.formError && pj.formError.form === name ? note(pj.formError.text, "error", `${name}-problem`) : null);
const money = (p) => `award ${p.award}, budgeted ${p.budgeted}, unallocated ${p.unallocated}, spent ${p.spent}, remaining ${p.remaining}, received ${p.received}, still to receive ${p.still_to_receive}`;

export function Projects({ pj, role, userId, loading, onRetry, actions: a }) {
  return h("div", {},
    h("h1", {}, "Projects and grants"),
    note("This workspace records a project's typed award, budget lines, spending and funder receipts, adds them up exactly, and requires a different person to approve each project and each entry. It moves no money, applies no funder or donor rules and checks no eligibility. Use a funder reference code, not a name or a personal detail.", "info", "pj-banner"),
    pj.error ? ErrorState({ message: pj.error, onRetry }) : null,
    note(pj.notice, "success", "pj-notice"),
    loading ? LoadingState() : h("div", {},
      h("div", { className: "tabs", role: "tablist", style: "display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px;" },
        TABS.map(([id, l]) => h("button", { className: `btn ${pj.tab === id ? "btn-primary" : "btn-secondary"}`, role: "tab", id: `pj-tab-${id}`, "aria-selected": pj.tab === id ? "true" : "false", onClick: () => a.setTab(id) }, l))),
      pj.busy ? h("div", { style: "color: var(--ink-500);" }, "Working...") : null,
      pj.tab === "overview" ? overview(pj, role, a) : projects(pj, role, userId, a)));
}

function overview(pj, role, a) {
  const o = pj.ov; if (!o) return none("Nothing loaded yet.");
  const c = o.counts;
  return h("div", {},
    card("What needs attention", "pj-attention", o.attention.length ? h("ul", {}, o.attention.map((x) => h("li", { "data-kind": x.kind }, Badge({ tone: ATTENTION_TONE[x.kind] || "info", label: words(x.kind) }), " ", `${x.count} ${x.text}`))) : none("Nothing needs attention.")),
    card("Open and closed projects per currency", "pj-totals", o.totals.length ? h("ul", {}, o.totals.map((t) => h("li", { "data-currency": t.currency }, `${t.currency}: ${t.projects} project(s), award ${t.award}, budgeted ${t.budgeted}, spent ${t.spent}, remaining ${t.remaining}, received ${t.received}, still to receive ${t.still_to_receive}`))) : none("No open projects yet."),
      h("p", { style: "color: var(--ink-500);" }, "Amounts in different currencies are never added together. Only approved spending and receipts are counted.")),
    card("Counts", "pj-counts", h("ul", {}, [["Draft", c.draft], ["Waiting for review", c.submitted], ["Open", c.active], ["Returned", c.returned], ["Closed", c.closed], ["Withdrawn", c.withdrawn]].map(([l, n]) => h("li", {}, `${l}: ${n}`)))),
    settingCard(pj, role, a),
    card("What this does not do", "pj-limits", h("ul", {}, o.limitations.map((x) => h("li", {}, x)))));
}

function settingCard(pj, role, a) {
  const s = pj.ov.setting;
  return card("Settings", "pj-setting", h("p", { id: "pj-setting-meaning" }, s.meaning),
    canApprove(role) && pj.forms.setting ? h("div", {}, row(field("Flag open projects ending within this many days", "pj-set-days", text(pj, a, "setting", "ending_soon_days", "pj-set-days"))),
      formError(pj, "setting"), btn("Save settings", "pj-set-save", () => a.saveSetting(), "primary", pj.busy)) : h("p", { style: "color: var(--ink-500);" }, "Only an approver can change this setting."));
}

function projects(pj, role, me, a) {
  const s = pj.sel.project;
  return h("div", {},
    card("Projects", "pj-projects", pj.projects.length ? pj.projects.map((x) => h("div", { className: "card", style: "margin-bottom:8px;", "data-project": x.ref },
      h("div", {}, h("strong", {}, `${x.ref} · ${x.title}`), " ", St(x.status), x.ending_soon ? [" ", Badge({ tone: "warn", label: "Ending soon" })] : null, x.ended_still_open ? [" ", Badge({ tone: "warn", label: "Past end date" })] : null, x.over_budget_lines ? [" ", Badge({ tone: "warn", label: "Over budget" })] : null),
      h("div", { style: "color: var(--ink-500);" }, `${x.period_start} to ${x.period_end} · ${x.currency} · ${money(x)}`),
      btn(s && s.id === x.id ? "Hide details" : "Details", `pj-pr-open-${x.ref}`, () => a.selectProject(s && s.id === x.id ? null : x.id), "secondary", pj.busy))) : none("No projects yet.")),
    s ? detail(pj, role, me, a, s) : null,
    canPrepare(role) ? card("Start a project", "pj-project-card",
      row(field("Title", "pj-pr-title", text(pj, a, "project", "title", "pj-pr-title")), field("Funder reference (a code, not a name)", "pj-pr-fund", text(pj, a, "project", "funder_ref", "pj-pr-fund")), field("Currency", "pj-pr-cur", text(pj, a, "project", "currency", "pj-pr-cur", "NGN")), field("Award", "pj-pr-award", text(pj, a, "project", "award", "pj-pr-award"))),
      row(field("Starts", "pj-pr-start", text(pj, a, "project", "period_start", "pj-pr-start", "YYYY-MM-DD")), field("Ends", "pj-pr-end", text(pj, a, "project", "period_end", "pj-pr-end", "YYYY-MM-DD"))),
      formError(pj, "project"), btn("Start project", "pj-pr-save", () => a.createProject(), "primary", pj.busy)) : null);
}

function budgetForm(pj, a, x) {
  return h("div", {}, h("h4", {}, "Add a budget line"),
    row(field("Category", "pj-bl-cat", text(pj, a, "budget", "category", "pj-bl-cat")), field("Budget amount", "pj-bl-amt", text(pj, a, "budget", "amount", "pj-bl-amt"))),
    formError(pj, "budget"), btn("Add budget line", "pj-bl-save", () => a.addBudget(x.id), "primary", pj.busy));
}

function entryForm(pj, a, x) {
  const lines = x.budget.filter((l) => l.status === "ACTIVE"), isExp = (pj.forms.entry || {}).entry_type !== "RECEIPT";
  return h("div", {}, h("h4", {}, "Propose spending or a receipt"),
    row(field("Kind", "pj-en-type", sel(pj, a, "entry", "entry_type", "pj-en-type", [["EXPENSE", "Spending (expense)"], ["RECEIPT", "Money received from the funder"]])),
      isExp ? field("Budget line", "pj-en-line", sel(pj, a, "entry", "budget_no", "pj-en-line", [["", "Choose a line"], ...lines.map((l) => [String(l.no), `#${l.no} ${l.category}`])])) : null,
      field("Amount", "pj-en-amt", text(pj, a, "entry", "amount", "pj-en-amt")), field("Date", "pj-en-date", text(pj, a, "entry", "entry_date", "pj-en-date", "YYYY-MM-DD"))),
    field("Description (no personal details)", "pj-en-desc", text(pj, a, "entry", "description", "pj-en-desc")),
    formError(pj, "entry"), btn("Propose entry", "pj-en-save", () => a.addEntry(x.id), "primary", pj.busy));
}

function detail(pj, role, me, a, x) {
  const edit = canEdit(x, role), dec = canDecide(x, role, me);
  return card(`${x.ref} · ${x.title}`, "pj-project-detail",
    h("div", { id: "pj-project-totals" }, `Totals (${x.currency}): ${money(x)}; ${x.spent_pct} percent of the award spent`),
    x.ending_soon ? h("div", { id: "pj-ending-note" }, `This project ends in ${x.days_left} day(s).`) : null, x.ended_still_open ? h("div", { id: "pj-ended-note" }, "This project is past its end date and is still open.") : null,
    x.received_above_award ? h("div", { id: "pj-received-note" }, "Approved receipts are above the award. This is a flag for a person to look at, not an error.") : null,
    x.status === "RETURNED" ? h("div", { id: "pj-returned" }, `Returned: ${x.decision_note}`) : null, x.status === "ACTIVE" && x.decision_note ? h("div", {}, `Approval note: ${x.decision_note}`) : null, x.status === "WITHDRAWN" ? h("div", {}, `Withdrawn: ${x.withdraw_note}`) : null,
    x.status === "CLOSED" ? h("div", { id: "pj-closed" }, `Closed: ${x.close_note}`) : null, x.note ? h("div", {}, `Note from the preparer: ${x.note}`) : null,
    h("div", { id: "pj-budget" }, h("h4", {}, "Budget lines"), x.budget.length ? x.budget.map((l) => h("div", { "data-line": String(l.no) },
      `#${l.no} ${l.category}: budget ${l.amount}, spent ${l.spent}, remaining ${l.remaining}. `, St(l.status), l.over_budget && l.status === "ACTIVE" ? [" ", Badge({ tone: "warn", label: "Over budget" })] : null, l.removed_note ? ` Removed: ${l.removed_note}` : "",
      edit && l.status === "ACTIVE" ? h("div", {}, noteBox(pj, a, `rm-${x.id}-${l.no}`, "Reason for removing (at least 5 characters)", `pj-bl-${l.no}-note`), btn("Remove line", `pj-bl-${l.no}-remove`, () => a.removeBudget(x.id, l.no), "secondary", pj.busy)) : null)) : none("No budget lines yet.")),
    edit ? budgetForm(pj, a, x) : null,
    edit && x.active_lines > 0 ? h("div", {}, h("h4", {}, "Submit for review"), field("Note for the approver (optional, at least 10 characters if given)", "pj-sb-note", area(pj, a, "submit", "note", "pj-sb-note")),
      formError(pj, "submit"), btn("Submit for review", "pj-sb-save", () => a.submit(x.id), "primary", pj.busy || !canSubmit(x, role))) : null,
    dec ? h("div", {}, h("h4", {}, "Decide"), noteBox(pj, a, `dec-${x.id}`, "Note (approval: optional, at least 10 characters if given; return: required)", "pj-dec-note"),
      btn("Approve project", "pj-dec-approve", () => a.approve(x.id), "primary", pj.busy), " ", btn("Return project", "pj-dec-return", () => a.returnProject(x.id), "secondary", pj.busy)) :
      (x.status === "SUBMITTED" && canApprove(role) ? h("p", { id: "pj-dec-waiting", style: "color: var(--ink-500);" }, ownWorkText) : null),
    edit ? h("div", {}, h("h4", {}, "Withdraw"), noteBox(pj, a, `wd-${x.id}`, "Reason (at least 10 characters)", "pj-wd-note"), btn("Withdraw project", "pj-wd-save", () => a.withdraw(x.id), "secondary", pj.busy)) : null,
    h("div", { id: "pj-entries" }, h("h4", {}, "Spending and receipts"), x.entries.length ? x.entries.map((e) => h("div", { "data-entry": String(e.no) },
      `#${e.no} ${e.entry_type === "RECEIPT" ? "Receipt" : "Expense"}${e.budget_no ? " on line #" + e.budget_no : ""}: ${e.amount} on ${e.entry_date}. ${e.description} `, St(e.status), e.decision_note ? ` Note: ${e.decision_note}` : "",
      canDecideEntry(x, e, role, me) ? h("div", {}, noteBox(pj, a, `en-${x.id}-${e.no}`, "Note (approval: optional, at least 10 characters if given; rejection: required)", `pj-en-${e.no}-note`),
        btn("Approve entry", `pj-en-${e.no}-approve`, () => a.approveEntry(x.id, e.no), "primary", pj.busy), " ", btn("Reject entry", `pj-en-${e.no}-reject`, () => a.rejectEntry(x.id, e.no), "secondary", pj.busy)) :
        (e.status === "PROPOSED" && canApprove(role) && x.status === "ACTIVE" ? h("p", { className: "pj-own-entry", style: "color: var(--ink-500);" }, ownEntryText) : null))) : none("No entries yet.")),
    canEnter(x, role) ? entryForm(pj, a, x) : null,
    canClose(x, role) ? h("div", {}, h("h4", {}, "Close the project"), noteBox(pj, a, `cl-${x.id}`, "Closing note (at least 10 characters)", "pj-cl-note"), btn("Close project", "pj-cl-save", () => a.close(x.id), "secondary", pj.busy)) :
      (x.status === "ACTIVE" && canApprove(role) && x.pending_entries > 0 ? h("p", { id: "pj-close-blocked", style: "color: var(--ink-500);" }, "Decide every proposed entry before closing the project.") : null),
    h("div", {}, h("h4", {}, "History"), hist(x.history)));
}
