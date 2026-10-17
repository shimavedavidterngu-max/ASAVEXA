import { h } from "../lib/vdom.js";
import { ui, frame } from "../lib/wsKit.js";
import { TABS, TYPES, ATTENTION_TONE, statusOf, words, canPrepare, canApprove, canDecideScheme, canRecord, canDecideRow, canClose, ownText } from "../lib/pension.js";

/** Pension and fiduciary. Schemes with contributions, funding valuations, a fiduciary calendar and a conflict register. It holds no member data and applies no pension law. */
export function Pension({ st, role, userId: me, loading, onRetry, actions: a }) {
  const k = ui(st, a, statusOf);
  return frame({ st, p: "pen", title: "Pension and fiduciary", tabs: TABS, loading, onRetry, a, k,
    banner: "This workspace keeps a register of pension schemes: contributions (exact totals, late and missing months), funding valuations (assets against liabilities, as typed from the actuary's and custodian's reports), a calendar of fiduciary obligations and a conflict-of-interest register. A different person approves each scheme and confirms each record. It holds no member data, calculates no benefit or contribution rate and applies no pension or trust law. Use reference codes, not names.",
    body: () => (st.tab === "overview" ? overview(st, k, role, a) : schemes(st, k, role, me, a)) });
}

function overview(st, k, role, a) {
  const o = st.ov; if (!o) return k.none("Nothing loaded yet.");
  const c = o.counts;
  return h("div", {},
    k.card("What needs attention", "pen-attention", o.attention.length ? h("ul", {}, o.attention.map((x) => h("li", { "data-kind": x.kind }, k.Badge({ tone: ATTENTION_TONE[x.kind] || "info", label: words(x.kind) }), " ", `${x.count} ${x.text}`))) : k.none("Nothing needs attention.")),
    k.card("Contributions by currency (confirmed only; currencies are never added together)", "pen-currency", o.by_currency.length ? h("ul", {}, o.by_currency.map((t) => h("li", { "data-currency": t.currency }, `${t.currency}: ${t.total_contributions} across ${t.schemes} open scheme(s)`))) : k.none("No open schemes yet.")),
    k.card("Counts", "pen-counts", h("ul", {}, [["Waiting for a decision", c.proposed], ["Open", c.approved], ["Rejected", c.rejected], ["Closed", c.closed]].map(([l, n]) => h("li", {}, `${l}: ${n}`)))),
    k.card("Settings", "pen-setting", h("p", { id: "pen-setting-meaning" }, o.setting.meaning),
      canApprove(role) && st.forms.setting ? h("div", {}, k.row(k.field("Funding floor (percent)", "pen-set-floor", k.text("setting", "funding_floor_pct", "pen-set-floor")), k.field("A valuation is stale after this many days", "pen-set-stale", k.text("setting", "valuation_stale_days", "pen-set-stale")),
        k.field("Due soon means within this many days", "pen-set-soon", k.text("setting", "due_soon_days", "pen-set-soon"))), k.formError("setting"), k.btn("Save settings", "pen-set-save", () => a.saveSetting(), "primary", st.busy)) :
        h("p", { style: "color: var(--ink-500);" }, "Only an approver can change these settings.")),
    k.limits(o.limitations, "pen-limits"));
}

function schemes(st, k, role, me, a) {
  const s = st.sel.scheme;
  return h("div", {},
    k.card("Schemes", "pen-schemes", st.schemes.length ? st.schemes.map((x) => h("div", { className: "card", style: "margin-bottom:8px;", "data-scheme": x.ref },
      h("div", {}, h("strong", {}, `${x.ref} · ${x.name}`), " ", k.St(x.status), x.below_floor ? [" ", k.Badge({ tone: "warn", label: "Below funding floor" })] : null, x.missing_periods.length ? [" ", k.Badge({ tone: "warn", label: `${x.missing_periods.length} month(s) missing` })] : null),
      h("div", { style: "color: var(--ink-500);" }, `Reference ${x.scheme_ref} · ${words(x.scheme_type)} · ${x.currency}${x.funding_ratio_pct != null ? " · funded " + x.funding_ratio_pct + " percent" : ""}`),
      k.btn(s && s.id === x.id ? "Hide details" : "Details", `pen-sc-open-${x.ref}`, () => a.selectScheme(s && s.id === x.id ? null : x.id), "secondary", st.busy))) : k.none("No schemes yet.")),
    s ? detail(st, k, role, me, a, s) : null,
    canPrepare(role) ? k.card("Propose a scheme", "pen-scheme-card",
      k.row(k.field("Name", "pen-sc-name", k.text("scheme", "name", "pen-sc-name")), k.field("Scheme reference (a code)", "pen-sc-ref", k.text("scheme", "scheme_ref", "pen-sc-ref")), k.field("Currency (for example NGN)", "pen-sc-cur", k.text("scheme", "currency", "pen-sc-cur")),
        k.field("Type", "pen-sc-type", k.sel("scheme", "scheme_type", "pen-sc-type", TYPES.map((t) => [t, words(t)])))),
      k.row(k.field("First contribution month", "pen-sc-start", k.text("scheme", "start_period", "pen-sc-start", "YYYY-MM")), k.field("Contributions fall due on this day of the next month (1 to 28)", "pen-sc-day", k.text("scheme", "due_day", "pen-sc-day"))),
      k.field("Description (at least 10 characters)", "pen-sc-desc", k.text("scheme", "description", "pen-sc-desc")), k.formError("scheme"), k.btn("Propose scheme", "pen-sc-save", () => a.createScheme(), "primary", st.busy)) : null);
}

function rowList(st, k, role, me, a, x, kind, title, line) {
  return h("div", { id: `pen-${kind}` }, h("h4", {}, title), x[kind].length ? x[kind].map((r) => h("div", { "data-row": `${kind}-${r.no}` }, line(r), " ", k.St(r.status), r.decision_note ? ` Note: ${r.decision_note}` : "",
    canDecideRow(x, r, role, me) ? h("div", {}, k.noteBox(`${kind}-${x.id}-${r.no}`, "Note (confirmation: optional, at least 10 characters if given; rejection: required)", `pen-${kind}-${r.no}-note`),
      k.btn("Confirm", `pen-${kind}-${r.no}-confirm`, () => a.confirm(kind, x.id, r.no), "primary", st.busy), " ", k.btn("Reject", `pen-${kind}-${r.no}-reject`, () => a.reject(kind, x.id, r.no), "secondary", st.busy)) :
      ((r.status === "PROPOSED" || r.status === "DONE") && canApprove(role) && x.status === "APPROVED" ? h("p", { className: "pen-own", style: "color: var(--ink-500);" }, ownText) : null))) : k.none("None yet."));
}

function detail(st, k, role, me, a, x) {
  const dec = canDecideScheme(x, role, me), rec = canRecord(x, role), f = st.forms;
  return k.card(`${x.ref} · ${x.name}`, "pen-scheme-detail",
    h("div", { id: "pen-facts" }, `Reference ${x.scheme_ref}. ${words(x.scheme_type)}, in ${x.currency}. First contribution month ${x.start_period}; due on day ${x.due_day} of the following month. ${x.description}`),
    x.decision_note ? h("div", {}, `Decision note: ${x.decision_note}`) : null, x.close_note ? h("div", { id: "pen-closed" }, `Closed: ${x.close_note}`) : null,
    x.status === "APPROVED" || x.status === "CLOSED" ? h("div", { id: "pen-position" }, h("p", { id: "pen-totals" }, `Confirmed contributions: employer ${x.employer_total}, employee ${x.employee_total}, total ${x.total_contributions} ${x.currency}. Paid late: ${x.late_contributions}.`),
      x.missing_periods.length ? h("p", { id: "pen-missing" }, `Months past due with no contribution recorded: ${x.missing_periods.join(", ")}.`) : null,
      x.latest_valuation ? h("p", { id: "pen-funding" }, `Funding at ${x.latest_valuation.as_of}: ${x.funding_ratio_pct} percent (assets ${x.latest_valuation.assets}, liabilities ${x.latest_valuation.liabilities}). `, k.St(x.position), ` ${x.position_amount} ${x.currency}.`, x.below_floor ? [" ", k.Badge({ tone: "warn", label: "Below funding floor" })] : null, x.valuation_stale ? [" ", k.Badge({ tone: "warn", label: "Valuation is stale" })] : null) : h("p", { id: "pen-funding" }, "No confirmed valuation yet.")) : null,
    dec ? h("div", {}, h("h4", {}, "Decide"), k.noteBox(`sc-${x.id}`, "Note (approval: optional, at least 10 characters if given; rejection: required)", "pen-sc-note"),
      k.btn("Approve scheme", "pen-sc-approve", () => a.approveScheme(x.id), "primary", st.busy), " ", k.btn("Reject scheme", "pen-sc-reject", () => a.rejectScheme(x.id), "secondary", st.busy)) :
      (x.status === "PROPOSED" && canApprove(role) ? h("p", { id: "pen-sc-waiting", style: "color: var(--ink-500);" }, ownText) : null),
    rowList(st, k, role, me, a, x, "contributions", "Contributions", (r) => `${r.period}: employer ${r.employer_amount}, employee ${r.employee_amount}, paid ${r.paid_on}, due ${r.due_date}${r.late ? " (late)" : ""}.`),
    rec ? h("div", {}, k.row(k.field("Month", "pen-co-period", k.text("contribution", "period", "pen-co-period", "YYYY-MM")), k.field("Employer amount", "pen-co-emp", k.text("contribution", "employer_amount", "pen-co-emp")), k.field("Employee amount", "pen-co-ee", k.text("contribution", "employee_amount", "pen-co-ee")),
      k.field("Date paid", "pen-co-paid", k.text("contribution", "paid_on", "pen-co-paid", "YYYY-MM-DD"))), k.formError("contribution"), k.btn("Record contribution", "pen-co-save", () => a.addContribution(x.id), "primary", st.busy)) : null,
    rowList(st, k, role, me, a, x, "valuations", "Funding valuations", (r) => `${r.as_of}: assets ${r.assets}, liabilities ${r.liabilities} (${r.source_note}).`),
    rec ? h("div", {}, k.row(k.field("As of", "pen-va-date", k.text("valuation", "as_of", "pen-va-date", "YYYY-MM-DD")), k.field("Assets", "pen-va-assets", k.text("valuation", "assets", "pen-va-assets")), k.field("Liabilities", "pen-va-liab", k.text("valuation", "liabilities", "pen-va-liab"))),
      k.field("Where the figures came from (at least 10 characters)", "pen-va-source", k.text("valuation", "source_note", "pen-va-source")), k.formError("valuation"), k.btn("Record valuation", "pen-va-save", () => a.addValuation(x.id), "primary", st.busy)) : null,
    h("div", { id: "pen-obligations" }, h("h4", {}, "Fiduciary calendar"), x.obligations.length ? x.obligations.map((r) => h("div", { "data-row": `obligations-${r.no}` }, `${r.title}, due ${r.due_date} `, k.St(r.status), r.overdue ? [" ", k.Badge({ tone: "warn", label: "Overdue" })] : null, r.due_soon ? [" ", k.Badge({ tone: "info", label: "Due soon" })] : null,
      r.completed_on ? ` Done ${r.completed_on}${r.done_late ? " (late)" : ""}: ${r.completion_note}` : "", r.decision_note ? ` Note: ${r.decision_note}` : "",
      rec && r.status === "OPEN" ? h("div", {}, k.row(k.field("Date done", `pen-ob-${r.no}-date`, h("input", { id: `pen-ob-${r.no}-date`, type: "text", placeholder: "YYYY-MM-DD", value: (f.complete[r.no] || {}).completed_on || "", onInput: (e) => a.setComplete(r.no, "completed_on", e.target.value) })),
        k.field("Note (at least 10 characters)", `pen-ob-${r.no}-text`, h("input", { id: `pen-ob-${r.no}-text`, type: "text", value: (f.complete[r.no] || {}).note || "", onInput: (e) => a.setComplete(r.no, "note", e.target.value) }))),
        k.formError("complete-" + r.no), k.btn("Mark as done", `pen-ob-${r.no}-done`, () => a.completeObligation(x.id, r.no), "secondary", st.busy)) : null,
      canDecideRow(x, r, role, me) ? h("div", {}, k.noteBox(`obligations-${x.id}-${r.no}`, "Note (confirmation: optional, at least 10 characters if given; rejection: required)", `pen-obligations-${r.no}-note`),
        k.btn("Confirm", `pen-obligations-${r.no}-confirm`, () => a.confirm("obligations", x.id, r.no), "primary", st.busy), " ", k.btn("Send back", `pen-obligations-${r.no}-reject`, () => a.reject("obligations", x.id, r.no), "secondary", st.busy)) :
        (r.status === "DONE" && canApprove(role) && x.status === "APPROVED" ? h("p", { className: "pen-own", style: "color: var(--ink-500);" }, ownText) : null))) : k.none("None yet.")),
    rec ? h("div", {}, k.row(k.field("Obligation", "pen-ob-title", k.text("obligation", "title", "pen-ob-title")), k.field("Due date", "pen-ob-due", k.text("obligation", "due_date", "pen-ob-due", "YYYY-MM-DD"))), k.formError("obligation"), k.btn("Add obligation", "pen-ob-save", () => a.addObligation(x.id), "primary", st.busy)) : null,
    rowList(st, k, role, me, a, x, "conflicts", "Conflict-of-interest declarations", (r) => `${r.person_ref}, declared ${r.declared_on}: ${r.nature}.`),
    rec ? h("div", {}, k.row(k.field("Person reference (a code)", "pen-cf-ref", k.text("conflict", "person_ref", "pen-cf-ref")), k.field("Date declared", "pen-cf-date", k.text("conflict", "declared_on", "pen-cf-date", "YYYY-MM-DD"))),
      k.field("Nature of the interest (at least 10 characters)", "pen-cf-nature", k.text("conflict", "nature", "pen-cf-nature")), k.formError("conflict"), k.btn("Record declaration", "pen-cf-save", () => a.addConflict(x.id), "primary", st.busy)) : null,
    canClose(x, role) ? h("div", {}, h("h4", {}, "Close the scheme"), k.noteBox(`cl-${x.id}`, "Reason (at least 10 characters)", "pen-cl-note"), k.btn("Close scheme", "pen-cl-save", () => a.closeScheme(x.id), "secondary", st.busy)) : null,
    h("div", {}, h("h4", {}, "History"), k.hist(x.history)));
}
