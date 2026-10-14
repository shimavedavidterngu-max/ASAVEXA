import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState } from "../components/DataState.js";
import { TABS, SOURCE_TEXT, SEVERITY_TEXT, KIND_TEXT, RESULT_TEXT, ATTENTION_TONE, canPrepare, canApprove, statusOf, words, who, dueText,
  canAnalyse, canAddAction, canVoid, canClose, canComplete, canVerify, canCancel, ownWorkText } from "../lib/quality.js";

/**
 * Quality management. It records and checks what people type in; it inspects nothing and measures nothing.
 * A different person checks that a corrective action worked, and a different person closes a nonconformance.
 */
const Badge = ({ tone, label, id }) => h("span", { className: `badge badge-${tone || "neutral"}`, id }, label);
const St = (s) => Badge({ ...statusOf(s) });
const note = (t, kind = "info", id) => (t ? h("div", { className: `alert alert-${kind}`, id, style: "margin-bottom:12px;", role: kind === "error" ? "alert" : "status" }, t) : null);
const field = (l, id, inp, hint) => h("div", { className: "field" }, h("label", { for: id }, l), inp, hint ? h("small", { style: "color: var(--ink-500);" }, hint) : null);
const text = (ql, a, form, k, id, ph) => h("input", { id, type: "text", value: (ql.forms[form] || {})[k] == null ? "" : (ql.forms[form] || {})[k], placeholder: ph || "", onInput: (e) => a.setForm(form, k, e.target.value) });
const area = (ql, a, form, k, id) => h("textarea", { id, rows: 3, onInput: (e) => a.setForm(form, k, e.target.value) }, (ql.forms[form] || {})[k] || "");
const sel = (ql, a, form, k, id, opts, blank) => h("select", { id, onChange: (e) => a.setForm(form, k, e.target.value, true) },
  [...(blank ? [h("option", { value: "" }, blank)] : []), ...opts.map(([v, l]) => h("option", { value: v, selected: String((ql.forms[form] || {})[k]) === String(v) }, l))]);
const btn = (l, id, onClick, kind = "secondary", disabled = false) => h("button", { className: `btn btn-${kind}`, id, disabled, onClick }, l);
const row = (...b) => h("div", { style: "display:flex; gap:8px; flex-wrap:wrap; margin:8px 0; align-items:end;" }, b.filter(Boolean));
const none = (t = "None.") => h("div", { style: "color: var(--ink-500);" }, t);
const card = (title, id, ...kids) => h("div", { className: "card", id, style: "margin-bottom:16px;" }, h("h3", {}, title), ...kids);
const hist = (items) => h("ul", {}, (items || []).map((x) => h("li", {}, `${String(x.at).slice(0, 10)} ${String(x.event).replace(/_/g, " ").toLowerCase()} by ${x.by}${x.note ? ": " + x.note : ""}`)));
const noteBox = (ql, a, key, l, id) => field(l, id || `note-${key}`, h("textarea", { id: id || `note-${key}`, rows: 2, onInput: (e) => a.setNote(key, e.target.value) }, ql.notes[key] || ""));
const formError = (ql, name) => (ql.formError && ql.formError.form === name ? note(ql.formError.text, "error", `${name}-problem`) : null);
const docs = (ql, a, form, id) => field("Attach a document (optional)", id, sel(ql, a, form, "evidence_id", id, (ql.vault || []).map((e) => [e.id, e.original_filename || e.filename || e.id]), "No document"), "A document from the Evidence Vault. Its file fingerprint is kept.");
const fileList = (list) => (list && list.length ? h("div", { style: "font-size:0.9em; color: var(--ink-500);" }, list.map((e) => `${e.filename} (fingerprint ${String(e.file_hash).slice(0, 12)})`).join("; ")) : null);
const opt = (o) => Object.entries(o);

export function Quality({ ql, role, userId, loading, onRetry, actions: a }) {
  return h("div", {},
    h("h1", {}, "Quality management"),
    note("This workspace records what people type in about quality problems and what was done about them. It inspects nothing and measures nothing. A different person checks that a corrective action worked, and a different person closes a nonconformance. Closing one here is not a certification.", "info", "ql-banner"),
    ql.error ? ErrorState({ message: ql.error, onRetry }) : null,
    note(ql.notice, "success", "ql-notice"),
    loading ? LoadingState() : h("div", {},
      h("div", { className: "tabs", role: "tablist", style: "display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px;" },
        TABS.map(([id, l]) => h("button", { className: `btn ${ql.tab === id ? "btn-primary" : "btn-secondary"}`, role: "tab", id: `ql-tab-${id}`, "aria-selected": ql.tab === id ? "true" : "false", onClick: () => a.setTab(id) }, l))),
      ql.busy ? h("div", { style: "color: var(--ink-500);" }, "Working...") : null,
      ql.tab === "overview" ? overview(ql, role, a) : ql.tab === "ncs" ? ncs(ql, role, userId, a) : actionsTab(ql, role, userId, a)));
}

function overview(ql, role, a) {
  const o = ql.ov; if (!o) return none("Nothing loaded yet.");
  const c = o.counts;
  return h("div", {},
    card("What needs attention", "ql-attention", o.attention.length ? h("ul", {}, o.attention.map((x) => h("li", { "data-kind": x.kind }, Badge({ tone: ATTENTION_TONE[x.kind] || "info", label: words(x.kind) }), " ", `${x.count} ${x.text}`))) : none("Nothing needs attention.")),
    card("Counts", "ql-counts", h("ul", {}, [["Open nonconformances", c.open], ["Critical", c.critical_open], ["Major", c.major_open], ["Minor", c.minor_open], ["Closed", c.closed], ["Open actions", c.actions_open], ["Actions checked effective", c.actions_verified], ["Actions checked not effective", c.actions_not_effective]]
      .map(([l, n]) => h("li", {}, `${l}: ${n}`)))),
    policyCard(ql, role, a),
    card("What this does not do", "ql-limits", h("ul", {}, o.limitations.map((x) => h("li", {}, x)))));
}

function policyCard(ql, role, a) {
  const p = ql.ov.policy, f = ql.forms.policy;
  return card("Settings", "ql-policy", h("p", { id: "ql-policy-meaning" }, p.meaning),
    canApprove(role) && f ? h("div", {}, row(field("Days allowed for an effectiveness check", "ql-policy-verify", text(ql, a, "policy", "verify_days", "ql-policy-verify"))),
      formError(ql, "policy"), btn("Save settings", "ql-policy-save", () => a.savePolicy(), "primary", ql.busy)) : h("p", { style: "color: var(--ink-500);" }, "Only an approver can change this setting."));
}

// ---------------------------------------------------------------- nonconformances
function ncs(ql, role, me, a) {
  const open = ql.sel.nc;
  return h("div", {},
    card("Nonconformances", "ql-ncs", ql.ncs.length ? ql.ncs.map((n) => h("div", { className: "card", style: "margin-bottom:8px;", "data-nc": n.ref },
      h("div", {}, h("strong", {}, `${n.ref} · ${n.title}`), " ", St(n.status), " ", St(n.severity)),
      h("div", { style: "color: var(--ink-500);" }, `${SOURCE_TEXT[n.source] || n.source} · ${n.area} · happened ${n.occurred_on}; found ${n.discovered_on}; raised by ${who(n.raised_by, me)} · ${n.actions.length} action(s)`),
      h("div", {}, n.description), fileList(n.evidence),
      n.root_cause ? h("div", {}, `Root cause: ${n.root_cause}`) : null, n.containment ? h("div", {}, `Contained by: ${n.containment}`) : null,
      n.status === "CLOSED" ? h("div", {}, `Closed ${n.closed_on}: ${n.closing_note}${n.no_action_reason ? ` (no action needed: ${n.no_action_reason})` : ""}`) : null, n.status === "VOIDED" ? h("div", {}, `Voided: ${n.void_note}`) : null,
      n.status === "RAISED" || n.status === "ANALYSED" ? btn(open && open.id === n.id ? "Hide" : "Open", `ql-nc-open-${n.ref}`, () => a.selectNc(open && open.id === n.id ? null : n.id), "secondary", ql.busy) : null)) : none("No nonconformances yet.")),
    open ? ncDetail(ql, role, me, a, open) : null,
    canPrepare(role) ? card("Raise a nonconformance", "ql-nc-card",
      row(field("Title", "ql-nc-title", text(ql, a, "nc", "title", "ql-nc-title")), field("Source", "ql-nc-source", sel(ql, a, "nc", "source", "ql-nc-source", opt(SOURCE_TEXT))), field("Severity", "ql-nc-sev", sel(ql, a, "nc", "severity", "ql-nc-sev", opt(SEVERITY_TEXT)))),
      field("What was found", "ql-nc-desc", area(ql, a, "nc", "description", "ql-nc-desc")),
      row(field("Area or process", "ql-nc-area", text(ql, a, "nc", "area", "ql-nc-area")), field("Happened on", "ql-nc-occ", text(ql, a, "nc", "occurred_on", "ql-nc-occ", "YYYY-MM-DD")), field("Found on", "ql-nc-dis", text(ql, a, "nc", "discovered_on", "ql-nc-dis", "YYYY-MM-DD"))),
      docs(ql, a, "nc", "ql-nc-doc"), formError(ql, "nc"), btn("Raise nonconformance", "ql-nc-save", () => a.raiseNc(), "primary", ql.busy)) : null);
}

function ncDetail(ql, role, me, a, n) {
  const key = `nc-${n.id}`, close = canClose(n, role, me), void_ = canVoid(n, role, me);
  return card(`${n.ref} · ${n.title}`, "ql-nc-detail",
    canAnalyse(n, role) ? h("div", {}, h("p", {}, "Analysis: say what caused it and what was done straight away to contain it."),
      field("Root cause (at least 20 characters)", "ql-an-cause", h("textarea", { id: "ql-an-cause", rows: 2, onInput: (ev) => a.setForm("analyse", "root_cause", ev.target.value) }, ql.forms.analyse.root_cause || "")),
      field("Contained by (what was done straight away)", "ql-an-contain", h("textarea", { id: "ql-an-contain", rows: 2, onInput: (ev) => a.setForm("analyse", "containment", ev.target.value) }, ql.forms.analyse.containment || "")),
      formError(ql, "analyse"), btn("Record the analysis", "ql-nc-analyse", () => a.analyseNc(n.id), "primary", ql.busy)) : null,
    n.status === "ANALYSED" ? h("div", { id: "ql-nc-actions" }, h("h4", {}, "Actions"), n.actions.length ? h("ul", {}, n.actions.map((x) => h("li", {}, `${x.ref} · ${x.description} · ${dueText(x)} · `, St(x.status)))) : none("No action yet. Add one on the Actions tab.")) : null,
    n.status === "ANALYSED" && n.close_problem ? h("p", { id: "ql-close-problem" }, `Cannot be closed yet: ${n.close_problem}`) : null,
    n.status === "ANALYSED" && canApprove(role) && !close ? h("p", { id: "ql-close-waiting" }, ownWorkText("raised this nonconformance")) : null,
    close ? h("div", {}, field("Closing note (at least 10 characters)", "ql-close-note", h("textarea", { id: "ql-close-note", rows: 2, onInput: (ev) => a.setForm("close", "note", ev.target.value) }, ql.forms.close.note || "")),
      n.severity === "MINOR" ? field("Reason no action is needed (minor only, at least 20 characters)", "ql-close-reason", h("textarea", { id: "ql-close-reason", rows: 2, onInput: (ev) => a.setForm("close", "no_action_reason", ev.target.value) }, ql.forms.close.no_action_reason || "")) : null,
      formError(ql, "close"), btn("Close nonconformance", "ql-nc-close", () => a.closeNc(n.id), "primary", ql.busy)) : null,
    void_ ? h("div", {}, noteBox(ql, a, `void-${n.id}`, "Why this record is being voided (required, at least 10 characters)"), btn("Void record", "ql-nc-void", () => a.voidNc(n.id), "secondary", ql.busy)) :
      (n.status === "RAISED" && canApprove(role) ? h("p", { id: "ql-void-waiting" }, ownWorkText("raised this nonconformance")) : null),
    h("div", {}, h("h4", {}, "History"), hist(n.history)));
}

// ---------------------------------------------------------------- actions
function actionsTab(ql, role, me, a) {
  const analysed = ql.ncs.filter((n) => n.status === "ANALYSED");
  return h("div", {},
    card("Corrective and preventive actions", "ql-actions", ql.actions.length ? ql.actions.map((x) => h("div", { className: "card", style: "margin-bottom:8px;", "data-action": x.ref },
      h("div", {}, h("strong", {}, `${x.ref} · ${x.nc_ref} ${x.nc_title}`), " ", St(x.status), x.overdue ? [" ", Badge({ tone: "warn", label: "Overdue" })] : null, x.check_overdue ? [" ", Badge({ tone: "warn", label: "Check overdue" })] : null),
      h("div", {}, x.description), h("div", { style: "color: var(--ink-500);" }, `${KIND_TEXT[x.kind] || x.kind} · owner ${x.owner_name} · ${dueText(x)} · added by ${who(x.added_by, me)}`),
      x.completed_on ? h("div", {}, `Completed ${x.completed_on} by ${who(x.completed_by, me)}: ${x.completion_note}`) : null, fileList(x.evidence),
      x.check_note ? h("div", {}, `Effectiveness check by ${who(x.checked_by, me)}: ${x.check_note}`) : null, x.cancel_note ? h("div", {}, `Cancelled: ${x.cancel_note}`) : null,
      canComplete(x, role) ? h("div", {}, row(field("Completed on", `ql-cm-${x.ref}-date`, text(ql, a, "complete", "completed_on", `ql-cm-${x.ref}-date`, "YYYY-MM-DD"))),
        field("What was done", `ql-cm-${x.ref}-note`, area(ql, a, "complete", "note", `ql-cm-${x.ref}-note`)), docs(ql, a, "complete", `ql-cm-${x.ref}-doc`),
        formError(ql, `complete-${x.id}`), btn("Record as completed", `ql-act-${x.ref}-complete`, () => a.completeAction(x.id), "primary", ql.busy)) : null,
      canVerify(x, role, me) ? h("div", {}, field("Result of the check", `ql-vf-${x.ref}-result`, sel(ql, a, "verify", "result", `ql-vf-${x.ref}-result`, opt(RESULT_TEXT))),
        field("What you checked (at least 20 characters)", `ql-vf-${x.ref}-note`, area(ql, a, "verify", "note", `ql-vf-${x.ref}-note`)), formError(ql, `verify-${x.id}`), btn("Record the check", `ql-act-${x.ref}-verify`, () => a.verifyAction(x.id), "primary", ql.busy)) :
        (x.status === "COMPLETED" && canApprove(role) ? h("div", { style: "color: var(--ink-500);" }, ownWorkText("recorded this action as completed")) : null),
      canCancel(x, role) ? h("div", {}, noteBox(ql, a, `cancel-${x.id}`, "Why this action is being cancelled (required, at least 10 characters)"), btn("Cancel action", `ql-act-${x.ref}-cancel`, () => a.cancelAction(x.id), "secondary", ql.busy)) : null)) : none("No actions yet.")),
    canPrepare(role) ? card("Add an action", "ql-action-card",
      analysed.length ? h("div", {}, row(field("Nonconformance", "ql-ac-nc", sel(ql, a, "action", "nc_id", "ql-ac-nc", analysed.map((n) => [n.id, `${n.ref} · ${n.title}`]), "Choose a nonconformance")), field("Kind", "ql-ac-kind", sel(ql, a, "action", "kind", "ql-ac-kind", opt(KIND_TEXT)))),
        field("The action", "ql-ac-desc", area(ql, a, "action", "description", "ql-ac-desc")), row(field("Owner (name)", "ql-ac-owner", text(ql, a, "action", "owner_name", "ql-ac-owner")), field("Due on", "ql-ac-due", text(ql, a, "action", "due_on", "ql-ac-due", "YYYY-MM-DD"))),
        formError(ql, "action"), btn("Add action", "ql-ac-save", () => a.addAction(), "primary", ql.busy)) : none("No analysed nonconformance is waiting for an action. Raise one and record its analysis first.")) : null);
}
