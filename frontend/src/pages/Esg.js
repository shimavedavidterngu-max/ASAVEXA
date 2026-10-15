import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState } from "../components/DataState.js";
import { TABS, SCOPE_TEXT, CATEGORY_TEXT, ATTENTION_TONE, canPrepare, canApprove, statusOf, words, canDecide, ownWorkText } from "../lib/esg.js";

/**
 * ESG and carbon. Emission records worked out from typed activity data and typed emission factors, verified by a different person, totalled by year and scope, and compared with reduction targets.
 * It supplies no emission factors and measures nothing.
 */
const Badge = ({ tone, label, id }) => h("span", { className: `badge badge-${tone || "neutral"}`, id }, label);
const St = (s) => Badge({ ...statusOf(s) });
const note = (t, kind = "info", id) => (t ? h("div", { className: `alert alert-${kind}`, id, style: "margin-bottom:12px;", role: kind === "error" ? "alert" : "status" }, t) : null);
const field = (l, id, inp) => h("div", { className: "field" }, h("label", { for: id }, l), inp);
const text = (es, a, form, k, id, ph) => h("input", { id, type: "text", value: (es.forms[form] || {})[k] == null ? "" : (es.forms[form] || {})[k], placeholder: ph || "", onInput: (e) => a.setForm(form, k, e.target.value) });
const sel = (es, a, form, k, id, opts) => h("select", { id, onChange: (e) => a.setForm(form, k, e.target.value, true) }, opts.map(([v, l]) => h("option", { value: v, selected: String((es.forms[form] || {})[k]) === String(v) }, l)));
const btn = (l, id, onClick, kind = "secondary", disabled = false) => h("button", { className: `btn btn-${kind}`, id, disabled, onClick }, l);
const row = (...b) => h("div", { style: "display:flex; gap:8px; flex-wrap:wrap; margin:8px 0; align-items:end;" }, b.filter(Boolean));
const none = (t = "None.") => h("div", { style: "color: var(--ink-500);" }, t);
const card = (title, id, ...kids) => h("div", { className: "card", id, style: "margin-bottom:16px;" }, h("h3", {}, title), ...kids);
const noteBox = (es, a, key, l, id) => field(l, id, h("textarea", { id, rows: 2, onInput: (e) => a.setNote(key, e.target.value) }, es.notes[key] || ""));
const formError = (es, name) => (es.formError && es.formError.form === name ? note(es.formError.text, "error", `${name}-problem`) : null);
const decideBox = (es, a, role, me, x, prefix, onApprove, onReject) => (canDecide(x, role, me) ? h("div", {}, noteBox(es, a, `${prefix}-${x.id}`, "Note (approval: optional, at least 10 characters if given; rejection: required)", `es-${prefix}-${x.ref}-note`),
  btn("Approve", `es-${prefix}-${x.ref}-approve`, onApprove, "primary", es.busy), " ", btn("Reject", `es-${prefix}-${x.ref}-reject`, onReject, "secondary", es.busy)) :
  (x.status === "PROPOSED" && canApprove(role) ? h("p", { id: `es-${prefix}-${x.ref}-waiting`, style: "color: var(--ink-500);" }, ownWorkText) : null));

export function Esg({ es, role, userId, loading, onRetry, actions: a }) {
  return h("div", {},
    h("h1", {}, "ESG and carbon"),
    note("This workspace works out emission records from the activity data and emission factors that people type in (quantity x factor, in kg CO2e), requires a different person to verify each record, totals only verified records by year and scope, and compares them with reduction targets. It supplies no emission factors, measures nothing and applies no reporting or assurance standard. It is not an assured sustainability report.", "info", "es-banner"),
    es.error ? ErrorState({ message: es.error, onRetry }) : null,
    note(es.notice, "success", "es-notice"),
    loading ? LoadingState() : h("div", {},
      h("div", { className: "tabs", role: "tablist", style: "display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px;" },
        TABS.map(([id, l]) => h("button", { className: `btn ${es.tab === id ? "btn-primary" : "btn-secondary"}`, role: "tab", id: `es-tab-${id}`, "aria-selected": es.tab === id ? "true" : "false", onClick: () => a.setTab(id) }, l))),
      es.busy ? h("div", { style: "color: var(--ink-500);" }, "Working...") : null,
      es.tab === "overview" ? overview(es, role, a) : es.tab === "entries" ? entries(es, role, userId, a) : targets(es, role, userId, a)));
}

function overview(es, role, a) {
  const o = es.ov; if (!o) return none("Nothing loaded yet.");
  const c = o.counts;
  return h("div", {},
    card("What needs attention", "es-attention", o.attention.length ? h("ul", {}, o.attention.map((x) => h("li", { "data-kind": x.kind }, Badge({ tone: ATTENTION_TONE[x.kind] || "info", label: words(x.kind) }), " ", `${x.count} ${x.text}`))) : none("Nothing needs attention.")),
    card("Verified emissions by year", "es-years", o.years.length ? o.years.map((y) => h("div", { "data-year": String(y.year) }, h("strong", {}, `${y.year}: ${y.total_tonnes} tonnes CO2e (${y.total_kg} kg)`),
      h("ul", {}, ["SCOPE_1", "SCOPE_2", "SCOPE_3"].map((s) => h("li", { "data-scope": s }, `${SCOPE_TEXT[s]}: ${y.scopes[s].tonnes} tonnes (${y.scopes[s].kg} kg)`))))) : none("No verified records yet. Only verified records count.")),
    card("Approved targets", "es-target-progress", o.targets.length ? h("ul", {}, o.targets.map((t) => h("li", { "data-target": t.ref },
      `${t.ref} ${t.label} (${SCOPE_TEXT[t.scope]}): in ${t.target_year}, ${t.actual_tonnes} tonnes verified so far against a target of ${t.target_tonnes} tonnes (${t.change_vs_baseline_pct} percent against the ${t.baseline_year} baseline of ${t.baseline_tonnes}). `,
      Badge({ tone: t.within_target ? "pass" : "warn", label: t.within_target ? "Within target" : "Above target" }), t.year_ended ? "" : " The year is not over yet."))) : none("No approved targets.")),
    card("Counts", "es-counts", h("ul", {}, [["Records waiting", c.entries_proposed], ["Records verified", c.entries_verified], ["Records rejected", c.entries_rejected], ["Targets waiting", c.targets_proposed], ["Targets approved", c.targets_approved], ["Targets rejected", c.targets_rejected]].map(([l, n]) => h("li", {}, `${l}: ${n}`)))),
    settingCard(es, role, a),
    card("What this does not do", "es-limits", h("ul", {}, o.limitations.map((x) => h("li", {}, x)))));
}

function settingCard(es, role, a) {
  const s = es.ov.setting;
  return card("Settings", "es-setting", h("p", { id: "es-setting-meaning" }, s.meaning),
    canApprove(role) && es.forms.setting ? h("div", {}, row(field("Factor age limit (years)", "es-set-years", text(es, a, "setting", "factor_max_age_years", "es-set-years"))),
      formError(es, "setting"), btn("Save settings", "es-set-save", () => a.saveSetting(), "primary", es.busy)) : h("p", { style: "color: var(--ink-500);" }, "Only an approver can change this setting."));
}

function entries(es, role, me, a) {
  return h("div", {},
    card("Emission records", "es-entries", es.entries.length ? es.entries.map((x) => h("div", { className: "card", style: "margin-bottom:8px;", "data-entry": x.ref },
      h("div", {}, h("strong", {}, `${x.ref} · ${SCOPE_TEXT[x.scope]} · ${CATEGORY_TEXT[x.category] || x.category}`), " ", St(x.status), x.old_factor ? [" ", Badge({ tone: "warn", label: "Old factor" })] : null),
      h("div", {}, x.description), h("div", { style: "color: var(--ink-500);" }, `${x.period_start} to ${x.period_end} · ${x.quantity} ${x.unit} x ${x.factor} kg CO2e per ${x.unit} (${x.factor_source}, ${x.factor_year}) = ${x.kg_co2e} kg CO2e (${x.tonnes} tonnes)`),
      x.decision_note ? h("div", {}, `Decision note: ${x.decision_note}`) : null,
      decideBox(es, a, role, me, x, "en", () => a.verifyEntry(x.id, x.ref), () => a.rejectEntry(x.id, x.ref)))) : none("No records yet.")),
    canPrepare(role) ? card("Propose an emission record", "es-entry-card",
      row(field("Scope", "es-en-scope", sel(es, a, "entry", "scope", "es-en-scope", [["SCOPE_1", "Scope 1"], ["SCOPE_2", "Scope 2"], ["SCOPE_3", "Scope 3"]])), field("Category", "es-en-cat", sel(es, a, "entry", "category", "es-en-cat", Object.entries(CATEGORY_TEXT))), field("Description", "es-en-desc", text(es, a, "entry", "description", "es-en-desc"))),
      row(field("Period start", "es-en-start", text(es, a, "entry", "period_start", "es-en-start", "YYYY-MM-DD")), field("Period end", "es-en-end", text(es, a, "entry", "period_end", "es-en-end", "YYYY-MM-DD"))),
      row(field("Quantity", "es-en-qty", text(es, a, "entry", "quantity", "es-en-qty")), field("Unit", "es-en-unit", text(es, a, "entry", "unit", "es-en-unit", "litres")), field("Emission factor (kg CO2e per unit)", "es-en-factor", text(es, a, "entry", "factor", "es-en-factor"))),
      row(field("Source of the factor", "es-en-fsrc", text(es, a, "entry", "factor_source", "es-en-fsrc")), field("Year of the factor", "es-en-fyear", text(es, a, "entry", "factor_year", "es-en-fyear"))),
      formError(es, "entry"), btn("Propose record", "es-en-save", () => a.addEntry(), "primary", es.busy)) : null);
}

function targets(es, role, me, a) {
  return h("div", {},
    card("Targets", "es-targets", es.targets.length ? es.targets.map((t) => h("div", { className: "card", style: "margin-bottom:8px;", "data-tgt": t.ref },
      h("div", {}, h("strong", {}, `${t.ref} · ${t.label}`), " ", St(t.status)),
      h("div", { style: "color: var(--ink-500);" }, `${SCOPE_TEXT[t.scope]} · baseline ${t.baseline_year}: ${t.baseline_tonnes} tonnes · reduction ${t.reduction_pct} percent · target for ${t.target_year}: ${t.target_tonnes} tonnes`),
      t.decision_note ? h("div", {}, `Decision note: ${t.decision_note}`) : null,
      decideBox(es, a, role, me, t, "tg", () => a.approveTarget(t.id, t.ref), () => a.rejectTarget(t.id, t.ref)))) : none("No targets yet.")),
    canPrepare(role) ? card("Propose a target", "es-target-card",
      row(field("Label", "es-tg-label", text(es, a, "target", "label", "es-tg-label")), field("Scope", "es-tg-scope", sel(es, a, "target", "scope", "es-tg-scope", Object.entries(SCOPE_TEXT)))),
      row(field("Baseline year", "es-tg-by", text(es, a, "target", "baseline_year", "es-tg-by")), field("Baseline emissions (tonnes)", "es-tg-bt", text(es, a, "target", "baseline_tonnes", "es-tg-bt")), field("Reduction (percent)", "es-tg-pct", text(es, a, "target", "reduction_pct", "es-tg-pct")), field("Target year", "es-tg-ty", text(es, a, "target", "target_year", "es-tg-ty"))),
      formError(es, "target"), btn("Propose target", "es-tg-save", () => a.addTarget(), "primary", es.busy)) : null);
}
