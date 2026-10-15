import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState } from "../components/DataState.js";
import { TABS, ATTENTION_TONE, canPrepare, canApprove, statusOf, words, canEdit, canSubmit, canDecide, ownWorkText } from "../lib/payroll.js";

/**
 * Payroll and workforce cost. Runs made of typed pay lines, added up exactly, and approved or returned by a different person.
 * It calculates no tax or statutory amount and pays nobody.
 */
const Badge = ({ tone, label, id }) => h("span", { className: `badge badge-${tone || "neutral"}`, id }, label);
const St = (s) => Badge({ ...statusOf(s) });
const note = (t, kind = "info", id) => (t ? h("div", { className: `alert alert-${kind}`, id, style: "margin-bottom:12px;", role: kind === "error" ? "alert" : "status" }, t) : null);
const field = (l, id, inp) => h("div", { className: "field" }, h("label", { for: id }, l), inp);
const text = (pw, a, form, k, id, ph) => h("input", { id, type: "text", value: (pw.forms[form] || {})[k] == null ? "" : (pw.forms[form] || {})[k], placeholder: ph || "", onInput: (e) => a.setForm(form, k, e.target.value) });
const area = (pw, a, form, k, id, rows = 2) => h("textarea", { id, rows, onInput: (e) => a.setForm(form, k, e.target.value) }, (pw.forms[form] || {})[k] || "");
const btn = (l, id, onClick, kind = "secondary", disabled = false) => h("button", { className: `btn btn-${kind}`, id, disabled, onClick }, l);
const row = (...b) => h("div", { style: "display:flex; gap:8px; flex-wrap:wrap; margin:8px 0; align-items:end;" }, b.filter(Boolean));
const none = (t = "None.") => h("div", { style: "color: var(--ink-500);" }, t);
const card = (title, id, ...kids) => h("div", { className: "card", id, style: "margin-bottom:16px;" }, h("h3", {}, title), ...kids);
const hist = (items) => h("ul", {}, (items || []).map((x) => h("li", {}, `${String(x.at).slice(0, 10)} ${String(x.event).replace(/_/g, " ").toLowerCase()} by ${x.by}${x.note ? ": " + x.note : ""}`)));
const noteBox = (pw, a, key, l, id) => field(l, id, h("textarea", { id, rows: 2, onInput: (e) => a.setNote(key, e.target.value) }, pw.notes[key] || ""));
const formError = (pw, name) => (pw.formError && pw.formError.form === name ? note(pw.formError.text, "error", `${name}-problem`) : null);
const totalsText = (t) => `gross ${t.gross}, deductions ${t.deductions}, net ${t.net}, employer contributions ${t.employer_contributions}, cost to the employer ${t.employer_cost}`;

export function Payroll({ pw, role, userId, loading, onRetry, actions: a }) {
  return h("div", {},
    h("h1", {}, "Payroll and workforce cost"),
    note("This workspace adds up the pay lines that people type in (gross = base pay + allowances; net = gross - deductions; cost to the employer = gross + employer contributions) and requires a different person to approve each run. It calculates no tax, pension or other statutory amount, pays nobody, moves no money and holds no names, bank details or national identifiers: use a staff reference code, not a name.", "info", "pw-banner"),
    pw.error ? ErrorState({ message: pw.error, onRetry }) : null,
    note(pw.notice, "success", "pw-notice"),
    loading ? LoadingState() : h("div", {},
      h("div", { className: "tabs", role: "tablist", style: "display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px;" },
        TABS.map(([id, l]) => h("button", { className: `btn ${pw.tab === id ? "btn-primary" : "btn-secondary"}`, role: "tab", id: `pw-tab-${id}`, "aria-selected": pw.tab === id ? "true" : "false", onClick: () => a.setTab(id) }, l))),
      pw.busy ? h("div", { style: "color: var(--ink-500);" }, "Working...") : null,
      pw.tab === "overview" ? overview(pw, role, a) : runs(pw, role, userId, a)));
}

function overview(pw, role, a) {
  const o = pw.ov; if (!o) return none("Nothing loaded yet.");
  const c = o.counts;
  return h("div", {},
    card("What needs attention", "pw-attention", o.attention.length ? h("ul", {}, o.attention.map((x) => h("li", { "data-kind": x.kind }, Badge({ tone: ATTENTION_TONE[x.kind] || "info", label: words(x.kind) }), " ", `${x.count} ${x.text}`))) : none("Nothing needs attention.")),
    card("Approved runs per currency", "pw-totals", o.totals.length ? h("ul", {}, o.totals.map((t) => h("li", { "data-currency": t.currency }, `${t.currency}: ${t.approved_runs} approved run(s), ${totalsText(t)}; ${t.waiting_runs} run(s) waiting for review`))) : none("No runs yet."),
      h("p", { style: "color: var(--ink-500);" }, "Amounts in different currencies are never added together. Only approved runs are totalled.")),
    card("Counts", "pw-counts", h("ul", {}, [["Draft", c.draft], ["Waiting for review", c.submitted], ["Approved", c.approved], ["Returned", c.returned], ["Withdrawn", c.withdrawn]].map(([l, n]) => h("li", {}, `${l}: ${n}`)))),
    settingCard(pw, role, a),
    card("What this does not do", "pw-limits", h("ul", {}, o.limitations.map((x) => h("li", {}, x)))));
}

function settingCard(pw, role, a) {
  const s = pw.ov.setting;
  return card("Settings", "pw-setting", h("p", { id: "pw-setting-meaning" }, s.meaning),
    canApprove(role) && pw.forms.setting ? h("div", {}, row(field("Flag lines with gross pay above (0 = off)", "pw-set-limit", text(pw, a, "setting", "review_limit", "pw-set-limit"))),
      formError(pw, "setting"), btn("Save settings", "pw-set-save", () => a.saveSetting(), "primary", pw.busy)) : h("p", { style: "color: var(--ink-500);" }, "Only an approver can change this setting."));
}

function runs(pw, role, me, a) {
  const s = pw.sel.run;
  return h("div", {},
    card("Payroll runs", "pw-runs", pw.runs.length ? pw.runs.map((x) => h("div", { className: "card", style: "margin-bottom:8px;", "data-run": x.ref },
      h("div", {}, h("strong", {}, `${x.ref} · ${x.label}`), " ", St(x.status), x.overlaps ? [" ", Badge({ tone: "warn", label: "Overlapping pay" })] : null),
      h("div", { style: "color: var(--ink-500);" }, `${x.period_start} to ${x.period_end} · ${x.currency} · ${x.totals.lines} line(s) · ${totalsText(x.totals)}`),
      btn(s && s.id === x.id ? "Hide details" : "Details", `pw-rn-open-${x.ref}`, () => a.selectRun(s && s.id === x.id ? null : x.id), "secondary", pw.busy))) : none("No runs yet.")),
    s ? detail(pw, role, me, a, s) : null,
    canPrepare(role) ? card("Start a payroll run", "pw-run-card",
      row(field("Label", "pw-rn-label", text(pw, a, "run", "label", "pw-rn-label")), field("Pay period start", "pw-rn-start", text(pw, a, "run", "period_start", "pw-rn-start", "YYYY-MM-DD")), field("Pay period end", "pw-rn-end", text(pw, a, "run", "period_end", "pw-rn-end", "YYYY-MM-DD")), field("Currency", "pw-rn-cur", text(pw, a, "run", "currency", "pw-rn-cur", "NGN"))),
      formError(pw, "run"), btn("Start run", "pw-rn-save", () => a.createRun(), "primary", pw.busy)) : null);
}

function lineForm(pw, a, x) {
  return h("div", {}, h("h4", {}, "Add a pay line"),
    row(field("Staff reference (a code, not a name)", "pw-ln-ref", text(pw, a, "line", "staff_ref", "pw-ln-ref")), field("Department", "pw-ln-dept", text(pw, a, "line", "department", "pw-ln-dept")), field("Base pay", "pw-ln-base", text(pw, a, "line", "base_pay", "pw-ln-base")),
      field("Allowances (optional)", "pw-ln-allow", text(pw, a, "line", "allowances", "pw-ln-allow")), field("Employer contributions (optional)", "pw-ln-emp", text(pw, a, "line", "employer_contributions", "pw-ln-emp"))),
    field('Deductions, one per line as "label: amount"', "pw-ln-deds", area(pw, a, "line", "deductions", "pw-ln-deds", 3)),
    formError(pw, "line"), btn("Add line", "pw-ln-save", () => a.addLine(x.id), "primary", pw.busy));
}

function detail(pw, role, me, a, x) {
  const edit = canEdit(x, role), dec = canDecide(x, role, me);
  return card(`${x.ref} · ${x.label}`, "pw-run-detail",
    h("div", { id: "pw-run-totals" }, `Totals (${x.currency}): ${totalsText(x.totals)}`),
    x.overlaps ? h("div", { id: "pw-overlap-note" }, `${x.overlaps} staff reference(s) also appear in another submitted or approved run for an overlapping period. This is a flag for a person to look at, not an error.`) : null,
    x.status === "RETURNED" ? h("div", { id: "pw-returned" }, `Returned: ${x.decision_note}`) : null, x.status === "APPROVED" && x.decision_note ? h("div", {}, `Approval note: ${x.decision_note}`) : null, x.status === "WITHDRAWN" ? h("div", {}, `Withdrawn: ${x.withdraw_note}`) : null, x.note ? h("div", {}, `Note from the preparer: ${x.note}`) : null,
    h("div", { id: "pw-departments" }, h("h4", {}, "By department"), x.departments.length ? h("ul", {}, x.departments.map((d) => h("li", { "data-dept": d.department }, `${d.department}: ${d.lines} line(s), gross ${d.gross}, net ${d.net}, cost to the employer ${d.employer_cost}`))) : none("No lines yet.")),
    h("div", { id: "pw-lines" }, h("h4", {}, "Pay lines"), x.lines.length ? x.lines.map((l) => h("div", { "data-line": String(l.no) },
      `#${l.no} ${l.staff_ref} (${l.department}): base ${l.base_pay}, allowances ${l.allowances}, gross ${l.gross}; deductions ${l.total_deductions}${l.deductions.length ? " (" + l.deductions.map((d) => `${d.label} ${d.amount}`).join(", ") + ")" : ""}; net ${l.net}; employer contributions ${l.employer_contributions}; cost to the employer ${l.employer_cost}. `,
      St(l.status), l.above_limit ? [" ", Badge({ tone: "warn", label: "Above review limit" })] : null, l.overlap ? [" ", Badge({ tone: "warn", label: "Overlapping pay" })] : null, l.removed_note ? ` Removed: ${l.removed_note}` : "",
      edit && l.status === "ACTIVE" ? h("div", {}, noteBox(pw, a, `rm-${x.id}-${l.no}`, "Reason for removing (at least 5 characters)", `pw-ln-${l.no}-note`), btn("Remove line", `pw-ln-${l.no}-remove`, () => a.removeLine(x.id, l.no), "secondary", pw.busy)) : null)) : none("No lines yet.")),
    edit ? lineForm(pw, a, x) : null,
    edit && x.active_lines > 0 ? h("div", {}, h("h4", {}, "Submit for review"), field("Note for the approver (optional, at least 10 characters if given)", "pw-sb-note", area(pw, a, "submit", "note", "pw-sb-note")),
      formError(pw, "submit"), btn("Submit for review", "pw-sb-save", () => a.submit(x.id), "primary", pw.busy || !canSubmit(x, role))) : null,
    dec ? h("div", {}, h("h4", {}, "Decide"), noteBox(pw, a, `dec-${x.id}`, "Note (approval: optional, at least 10 characters if given; return: required)", "pw-dec-note"),
      btn("Approve run", "pw-dec-approve", () => a.approve(x.id), "primary", pw.busy), " ", btn("Return run", "pw-dec-return", () => a.returnRun(x.id), "secondary", pw.busy)) :
      (x.status === "SUBMITTED" && canApprove(role) ? h("p", { id: "pw-dec-waiting", style: "color: var(--ink-500);" }, ownWorkText) : null),
    edit ? h("div", {}, h("h4", {}, "Withdraw"), noteBox(pw, a, `wd-${x.id}`, "Reason (at least 10 characters)", "pw-wd-note"), btn("Withdraw run", "pw-wd-save", () => a.withdraw(x.id), "secondary", pw.busy)) : null,
    h("div", {}, h("h4", {}, "History"), hist(x.history)));
}
