import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState } from "../components/DataState.js";
import { TABS, KIND_TEXT, PURPOSE_TEXT, BASIS_TEXT, METHOD_TEXT, ATTENTION_TONE, canPrepare, canApprove, statusOf, words, who, canEdit, canSubmit, canDecide, weightText, ownWorkText } from "../lib/valuation.js";

/**
 * Valuation. Workpapers whose methods are worked out from the inputs people type in and weighted into a concluded value. It reads no market data and gives no opinion of value.
 * A different person approves or returns every submitted valuation.
 */
const Badge = ({ tone, label, id }) => h("span", { className: `badge badge-${tone || "neutral"}`, id }, label);
const St = (s) => Badge({ ...statusOf(s) });
const note = (t, kind = "info", id) => (t ? h("div", { className: `alert alert-${kind}`, id, style: "margin-bottom:12px;", role: kind === "error" ? "alert" : "status" }, t) : null);
const field = (l, id, inp, hint) => h("div", { className: "field" }, h("label", { for: id }, l), inp, hint ? h("small", { style: "color: var(--ink-500);" }, hint) : null);
const text = (vl, a, form, k, id, ph) => h("input", { id, type: "text", value: (vl.forms[form] || {})[k] == null ? "" : (vl.forms[form] || {})[k], placeholder: ph || "", onInput: (e) => a.setForm(form, k, e.target.value) });
const area = (vl, a, form, k, id, rows = 3) => h("textarea", { id, rows, onInput: (e) => a.setForm(form, k, e.target.value) }, (vl.forms[form] || {})[k] || "");
const sel = (vl, a, form, k, id, opts) => h("select", { id, onChange: (e) => a.setForm(form, k, e.target.value, true) },
  opts.map(([v, l]) => h("option", { value: v, selected: String((vl.forms[form] || {})[k]) === String(v) }, l)));
const btn = (l, id, onClick, kind = "secondary", disabled = false) => h("button", { className: `btn btn-${kind}`, id, disabled, onClick }, l);
const row = (...b) => h("div", { style: "display:flex; gap:8px; flex-wrap:wrap; margin:8px 0; align-items:end;" }, b.filter(Boolean));
const none = (t = "None.") => h("div", { style: "color: var(--ink-500);" }, t);
const card = (title, id, ...kids) => h("div", { className: "card", id, style: "margin-bottom:16px;" }, h("h3", {}, title), ...kids);
const hist = (items) => h("ul", {}, (items || []).map((x) => h("li", {}, `${String(x.at).slice(0, 10)} ${String(x.event).replace(/_/g, " ").toLowerCase()} by ${x.by}${x.note ? ": " + x.note : ""}`)));
const noteBox = (vl, a, key, l, id) => field(l, id || `note-${key}`, h("textarea", { id: id || `note-${key}`, rows: 2, onInput: (e) => a.setNote(key, e.target.value) }, vl.notes[key] || ""));
const formError = (vl, name) => (vl.formError && vl.formError.form === name ? note(vl.formError.text, "error", `${name}-problem`) : null);

export function Valuation({ vl, role, userId, loading, onRetry, actions: a }) {
  return h("div", {},
    h("h1", {}, "Valuation"),
    note("This workspace works out values from the inputs that people type in (a multiple of a metric, discounted cash flows, assets less liabilities) and combines them using the weights they type. It reads no market data, chooses no multiples, rates or cash flows, gives no opinion of value, and is not a valuation report. A different person approves or returns every submitted valuation.", "info", "vl-banner"),
    vl.error ? ErrorState({ message: vl.error, onRetry }) : null,
    note(vl.notice, "success", "vl-notice"),
    loading ? LoadingState() : h("div", {},
      h("div", { className: "tabs", role: "tablist", style: "display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px;" },
        TABS.map(([id, l]) => h("button", { className: `btn ${vl.tab === id ? "btn-primary" : "btn-secondary"}`, role: "tab", id: `vl-tab-${id}`, "aria-selected": vl.tab === id ? "true" : "false", onClick: () => a.setTab(id) }, l))),
      vl.busy ? h("div", { style: "color: var(--ink-500);" }, "Working...") : null,
      vl.tab === "overview" ? overview(vl, role, a) : cases(vl, role, userId, a)));
}

function overview(vl, role, a) {
  const o = vl.ov; if (!o) return none("Nothing loaded yet.");
  const c = o.counts;
  return h("div", {},
    card("What needs attention", "vl-attention", o.attention.length ? h("ul", {}, o.attention.map((x) => h("li", { "data-kind": x.kind }, Badge({ tone: ATTENTION_TONE[x.kind] || "info", label: words(x.kind) }), " ", `${x.count} ${x.text}`))) : none("Nothing needs attention.")),
    card("Valuations per currency", "vl-totals", o.totals.length ? h("ul", {}, o.totals.map((t) => h("li", { "data-currency": t.currency }, `${t.currency}: ${t.approved} approved, ${t.waiting} waiting for review, ${t.in_progress} in progress`))) : none("No valuations yet."),
      h("p", { style: "color: var(--ink-500);" }, "Values in different currencies are never added together.")),
    card("Counts", "vl-counts", h("ul", {}, [["Draft", c.DRAFT], ["Waiting for review", c.SUBMITTED], ["Approved", c.APPROVED], ["Returned", c.RETURNED], ["Withdrawn", c.WITHDRAWN]].map(([l, n]) => h("li", {}, `${l}: ${n}`)))),
    policyCard(vl, role, a),
    card("What this does not do", "vl-limits", h("ul", {}, o.limitations.map((x) => h("li", {}, x)))));
}

function policyCard(vl, role, a) {
  const p = vl.ov.policy, f = vl.forms.policy;
  return card("Settings", "vl-policy", h("p", { id: "vl-policy-meaning" }, p.meaning),
    canApprove(role) && f ? h("div", {}, row(field("Days before an approved valuation is due for review", "vl-policy-days", text(vl, a, "policy", "review_days", "vl-policy-days"))),
      formError(vl, "policy"), btn("Save settings", "vl-policy-save", () => a.savePolicy(), "primary", vl.busy)) : h("p", { style: "color: var(--ink-500);" }, "Only an approver can change this setting."));
}

function cases(vl, role, me, a) {
  const sel_ = vl.sel.case;
  return h("div", {},
    card("Valuations", "vl-cases", vl.cases.length ? vl.cases.map((x) => h("div", { className: "card", style: "margin-bottom:8px;", "data-case": x.ref },
      h("div", {}, h("strong", {}, `${x.ref} · ${x.subject}`), " ", St(x.status), x.due_for_review ? [" ", Badge({ tone: "warn", label: "Due for review" })] : null),
      h("div", { style: "color: var(--ink-500);" }, `${KIND_TEXT[x.subject_kind] || x.subject_kind} · ${PURPOSE_TEXT[x.purpose] || x.purpose} · ${BASIS_TEXT[x.basis] || x.basis} · as at ${x.valuation_date}`),
      x.concluded_value ? h("div", {}, `Concluded value ${x.currency} ${x.concluded_value} (lowest method ${x.low}, highest ${x.high})`) : h("div", {}, `${x.active_methods} method(s); ${weightText(x)}`),
      btn(sel_ && sel_.id === x.id ? "Hide details" : "Details", `vl-cs-open-${x.ref}`, () => a.selectCase(sel_ && sel_.id === x.id ? null : x.id), "secondary", vl.busy))) : none("No valuations yet.")),
    sel_ ? detail(vl, role, me, a, sel_) : null,
    canPrepare(role) ? card("Start a valuation", "vl-case-card",
      row(field("Subject", "vl-cs-subject", text(vl, a, "case", "subject", "vl-cs-subject")), field("Kind of subject", "vl-cs-kind", sel(vl, a, "case", "subject_kind", "vl-cs-kind", Object.entries(KIND_TEXT))), field("Purpose", "vl-cs-purpose", sel(vl, a, "case", "purpose", "vl-cs-purpose", Object.entries(PURPOSE_TEXT)))),
      row(field("Basis of value (a label)", "vl-cs-basis", sel(vl, a, "case", "basis", "vl-cs-basis", Object.entries(BASIS_TEXT))), field("Valuation date", "vl-cs-date", text(vl, a, "case", "valuation_date", "vl-cs-date", "YYYY-MM-DD")), field("Currency", "vl-cs-cur", text(vl, a, "case", "currency", "vl-cs-cur", "NGN"))),
      formError(vl, "case"), btn("Start valuation", "vl-cs-save", () => a.createCase(), "primary", vl.busy)) : null);
}

const inputsText = (m) => (m.kind === "MULTIPLE" ? `metric ${m.inputs.metric} x multiple ${m.inputs.multiple}, less net debt ${m.inputs.net_debt}` :
  m.kind === "DCF" ? `cash flows ${m.inputs.cash_flows.join(", ")} at ${m.inputs.discount_rate} percent${m.inputs.terminal_growth ? `, terminal growth ${m.inputs.terminal_growth} percent` : ""}, less net debt ${m.inputs.net_debt}` :
    `assets ${m.inputs.total_assets} less liabilities ${m.inputs.total_liabilities}`);

function methodForm(vl, a, x) {
  const k = vl.forms.method.kind;
  return h("div", {}, h("h4", {}, "Add a method"),
    row(field("Method", "vl-mt-kind", sel(vl, a, "method", "kind", "vl-mt-kind", Object.entries(METHOD_TEXT))), field("Label", "vl-mt-label", text(vl, a, "method", "label", "vl-mt-label", "Peer EV/EBITDA")), field("Weight (percent)", "vl-mt-weight", text(vl, a, "method", "weight", "vl-mt-weight"))),
    k === "MULTIPLE" ? row(field("Metric (for example earnings)", "vl-mt-metric", text(vl, a, "method", "metric", "vl-mt-metric")), field("Multiple", "vl-mt-multiple", text(vl, a, "method", "multiple", "vl-mt-multiple", "6.5")), field("Net debt (optional)", "vl-mt-debt", text(vl, a, "method", "net_debt", "vl-mt-debt"))) : null,
    k === "DCF" ? h("div", {}, field("Yearly cash flows (separated by spaces or new lines, last year last)", "vl-mt-flows", area(vl, a, "method", "cash_flows", "vl-mt-flows", 2)),
      row(field("Discount rate (percent)", "vl-mt-rate", text(vl, a, "method", "discount_rate", "vl-mt-rate")), field("Terminal growth (percent, optional)", "vl-mt-growth", text(vl, a, "method", "terminal_growth", "vl-mt-growth")), field("Net debt (optional)", "vl-mt-debt", text(vl, a, "method", "net_debt", "vl-mt-debt")))) : null,
    k === "ASSET_BASED" ? row(field("Total assets", "vl-mt-assets", text(vl, a, "method", "total_assets", "vl-mt-assets")), field("Total liabilities", "vl-mt-liabs", text(vl, a, "method", "total_liabilities", "vl-mt-liabs"))) : null,
    formError(vl, "method"), btn("Add method", "vl-mt-save", () => a.addMethod(x.id), "primary", vl.busy));
}

function detail(vl, role, me, a, x) {
  const edit = canEdit(x, role), dec = canDecide(x, role, me);
  return card(`${x.ref} · ${x.subject}`, "vl-case-detail",
    h("div", { id: "vl-weights" }, weightText(x)),
    x.concluded_value ? h("div", { id: "vl-concluded" }, `Concluded value: ${x.currency} ${x.concluded_value}. Rationale: ${x.rationale}`) : null,
    x.status === "RETURNED" ? h("div", { id: "vl-returned" }, `Returned: ${x.decision_note}`) : null, x.status === "APPROVED" && x.decision_note ? h("div", {}, `Approval note: ${x.decision_note}`) : null, x.status === "WITHDRAWN" ? h("div", {}, `Withdrawn: ${x.withdraw_note}`) : null,
    h("div", { id: "vl-methods" }, h("h4", {}, "Methods"), x.methods.length ? x.methods.map((m) => h("div", { "data-method": String(m.no) },
      `#${m.no} ${METHOD_TEXT[m.kind] || m.kind}: ${m.label}. ${inputsText(m)}. Result ${x.currency} ${m.result}, weight ${m.weight} percent. `, St(m.status), m.removed_note ? ` Removed: ${m.removed_note}` : "",
      m.kind === "DCF" && m.status === "ACTIVE" ? [" ", btn("Show sensitivity", `vl-mt-${m.no}-sens`, () => a.showSensitivity(x.id, m.no), "secondary", vl.busy)] : null,
      vl.sens && vl.sens.method === m.no && vl.sens.caseId === x.id ? h("ul", { id: `vl-sens-${m.no}` }, vl.sens.rows.map((r) => h("li", {}, `${r.discount_rate} percent: ${r.result == null ? "not usable with the growth typed" : x.currency + " " + r.result}`))) : null,
      edit && m.status === "ACTIVE" ? h("div", {}, noteBox(vl, a, `rm-${x.id}-${m.no}`, "Reason for removing (at least 5 characters)", `vl-mt-${m.no}-note`), btn("Remove method", `vl-mt-${m.no}-remove`, () => a.removeMethod(x.id, m.no), "secondary", vl.busy)) : null)) : none("No methods yet.")),
    edit ? methodForm(vl, a, x) : null,
    edit && x.active_methods > 0 ? h("div", {}, h("h4", {}, "Submit for review"), field("Rationale for the weights and inputs (at least 20 characters)", "vl-sb-rationale", area(vl, a, "submit", "rationale", "vl-sb-rationale")),
      formError(vl, "submit"), btn("Submit for review", "vl-sb-save", () => a.submit(x.id), "primary", vl.busy || !canSubmit(x, role)), canSubmit(x, role) ? null : h("small", { id: "vl-sb-blocked", style: "color: var(--ink-500);" }, " Submit is available when the weights add up to 100 percent.")) : null,
    dec ? h("div", {}, h("h4", {}, "Decide"), noteBox(vl, a, `dec-${x.id}`, "Note (approval: optional, at least 10 characters if given; return: required)", "vl-dec-note"),
      btn("Approve valuation", "vl-dec-approve", () => a.approve(x.id), "primary", vl.busy), " ", btn("Return valuation", "vl-dec-return", () => a.returnCase(x.id), "secondary", vl.busy)) :
      (x.status === "SUBMITTED" && canApprove(role) ? h("p", { id: "vl-dec-waiting", style: "color: var(--ink-500);" }, ownWorkText("submitted this valuation")) : null),
    edit ? h("div", {}, h("h4", {}, "Withdraw"), noteBox(vl, a, `wd-${x.id}`, "Reason (at least 10 characters)", "vl-wd-note"), btn("Withdraw valuation", "vl-wd-save", () => a.withdraw(x.id), "secondary", vl.busy)) : null,
    h("div", {}, h("h4", {}, "History"), hist(x.history)));
}
