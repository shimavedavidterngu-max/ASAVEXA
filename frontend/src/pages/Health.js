import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState, EmptyState } from "../components/DataState.js";
import { FORMS, SECTIONS, caps, label, STATE_TEXT, visibleTabs, visibleSections, visibleActions, needsNote } from "../lib/health.js";

/**
 * Health Centre Administration: finance and administration only. There are no patient fields on any screen.
 * Every list, form and button is described as data in lib/health.js; this page only draws it. The server decides who may do what
 * (facility access, permissions, second-person approval); the buttons shown here just save people from pressing things that will be refused.
 */
const note = (t, kind = "info", id) => (t ? h("div", { id, className: `alert alert-${kind}`, style: "margin-bottom:12px;", role: kind === "error" ? "alert" : "status" }, t) : null);
const btn = (l, id, onClick, kind = "secondary", disabled = false) => h("button", { className: `btn btn-${kind}`, id, disabled, onClick }, l);
const field = (l, id, inp) => h("div", { className: "field" }, h("label", { for: id }, l), inp);

/** The choices for a select field, from the server's option lists or the facility's own reference lists. */
export function choices(name, hc, row) {
  const o = hc.options || {}, r = hc.ref || {};
  if (name === "depts") return (r.depts || []).filter((d) => d.active).map((d) => [d.id, `${d.code} ${d.name}`]);
  if (name === "suppliers") return (r.suppliers || []).filter((s) => s.status === "AUTHORISED").map((s) => [s.id, s.name]);
  if (name === "items") return (r.items || []).map((i) => [i.id, `${i.sku} ${i.name}`]);
  if (name === "payers") return (r.payers || []).map((p) => [p.id, p.name]);
  if (name === "fees") return (r.fees || []).filter((f) => f.status === "ACTIVE").map((f) => [f.id, `${f.name} (${f.price})`]);
  if (name === "row_lines") return ((row && row.lines) || []).map((l) => [l.line_id, `${l.dept || l.dept_id} / ${label(l.category)} (${l.amount})`]);
  return (o[name] || []).map((x) => [x, label(x)]);
}

export function Health({ hc, role, userId, loading, onRetry, actions }) {
  const c = caps(role);
  const tabs = visibleTabs(c);
  const tab = tabs.some(([id]) => id === hc.tab) ? hc.tab : (tabs[0] && tabs[0][0]);
  return h("div", {},
    h("h1", {}, "Health Centre Administration"),
    note("This workspace covers money and administration only: budgets, purchasing, stock, fees and claims totals, equipment and staffing costs. It holds no patient names, diagnoses, prescriptions, test results or national ID numbers, so do not type any here. It never posts to the ledger by itself, and it makes no claim of legal or regulatory compliance.", "info", "hc-banner"),
    hc.error ? ErrorState({ message: hc.error, onRetry }) : null,
    note(hc.notice, "success", "hc-notice"),
    loading ? LoadingState() : !hc.options ? null : !c.read ? EmptyState({ title: "No access", message: "Your role cannot open this workspace." }) : (hc.options.facilities || []).length === 0 && !c.admin
      ? EmptyState({ title: "No facility available to you", message: "An administrator must create a facility and give you access to it." })
      : h("div", {},
        facilityBar(hc, c, actions),
        h("div", { className: "tabs", role: "tablist", style: "display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px;" },
          tabs.map(([id, l]) => h("button", { className: `btn ${tab === id ? "btn-primary" : "btn-secondary"}`, role: "tab", id: `hc-tab-${id}`, "aria-selected": tab === id ? "true" : "false", onClick: () => actions.setTab(id) }, l))),
        hc.busy ? h("div", { style: "color: var(--ink-500);" }, "Working...") : null,
        tab === "dashboard" ? dashboard(hc, actions) : tabBody(tab, hc, c, userId, actions)));
}

function facilityBar(hc, c, a) {
  const fs = hc.options.facilities || [];
  return h("div", { style: "display:flex; gap:12px; align-items:center; flex-wrap:wrap; margin-bottom:12px;" },
    fs.length ? h("label", { for: "hc-facility" }, "Facility "): null,
    fs.length ? h("select", { id: "hc-facility", onChange: (e) => a.setFacility(e.target.value) }, fs.map((f) => h("option", { value: f.id, selected: f.id === hc.facilityId }, `${f.ref} ${f.name}${f.status === "ACTIVE" ? "" : " (inactive)"}`))) : h("span", {}, "No facility yet. Create one under Setup."));
}

function dashboard(hc, a) {
  const d = hc.dashboard;
  if (!hc.facilityId) return EmptyState({ title: "Nothing to show", message: "Create a facility first (Setup tab)." });
  if (!d) return EmptyState({ title: "No figures yet", message: "The dashboard could not be loaded." });
  const metrics = Object.entries(d.metrics);
  return h("div", { id: "hc-dashboard" },
    h("p", { id: "hc-dash-period" }, `${d.facility} (${d.facility_ref}), ${d.period_start} to ${d.period_end}, in ${d.currency}. Every figure shows how it is worked out and where it comes from.`),
    h("div", { style: "display:grid; grid-template-columns:repeat(auto-fill,minmax(230px,1fr)); gap:12px;" },
      metrics.map(([k, m]) => h("div", { className: "card", "data-metric": k, "data-state": m.state, id: `hm-${k}` },
        h("div", { style: "color: var(--ink-500); font-size:0.85em;" }, m.label),
        h("div", { style: "font-size:1.5em; font-weight:600;", className: "hm-value" }, m.value == null ? (STATE_TEXT[m.state] || "—") : String(m.value) + (m.note === "percent" ? "%" : "")),
        m.state !== "OK" ? h("div", { className: "badge badge-warn" }, STATE_TEXT[m.state] || m.state) : null,
        m.state !== "OK" && m.note ? h("div", { style: "font-size:0.8em;" }, m.note) : null,
        h("details", {}, h("summary", {}, "How this is worked out"), h("div", { style: "font-size:0.85em;" }, m.formula || "—"), h("div", { style: "font-size:0.85em; color: var(--ink-500);" }, `Source: ${m.source}`), m.state === "OK" && m.note && m.note !== "percent" ? h("div", { style: "font-size:0.85em;" }, m.note) : null)))),
    h("div", { className: "card", style: "margin-top:12px;" }, h("h3", {}, "What this does not tell you"), h("ul", { id: "hc-limits" }, (hc.options.limitations || []).map((l) => h("li", {}, l)))));
}

function tabBody(tab, hc, c, userId, a) {
  if (!hc.facilityId && tab !== "setup") return EmptyState({ title: "No facility selected", message: "Create a facility under Setup first." });
  const secs = visibleSections(tab, c);
  const anyNote = secs.some(([id, s]) => s.actions.some((x) => x.note && c[x.perm]));
  return h("div", { id: `hc-tabbody-${tab}` },
    hc.form ? formView(hc, a) : null,
    hc.detail ? h("div", { className: "card", id: "hc-detail", style: "margin-bottom:12px;" }, h("h3", {}, hc.detail.title), h("ul", {}, hc.detail.lines.map((l) => h("li", {}, l))), btn("Close", "hc-detail-close", () => a.closeDetail())) : null,
    anyNote && !hc.form ? field("Note or reason (used by the button you press; some buttons need one)", "hc-note", h("textarea", { id: "hc-note", rows: 2, onInput: (e) => a.noteChange(e.target.value) }, hc.noteText || "")) : null,
    secs.map(([id, s]) => section(id, s, hc, c, userId, a)));
}

function section(id, s, hc, c, userId, a) {
  const rows = hc.data[id], ctx = { facilities: hc.options.facilities || [], hc };
  const canCreate = s.create && c[s.create.perm];
  return h("div", { className: "card", id: `hc-sec-${id}`, style: "margin-bottom:12px;" },
    h("h3", {}, s.title), canCreate && !hc.form ? btn(s.create.label, `hc-new-${id}`, () => a.newForm(id), "primary") : null,
    rows == null ? h("div", { style: "color: var(--ink-500);" }, "Not loaded.") : rows.length === 0 ? h("div", { style: "color: var(--ink-500);", id: `hc-empty-${id}` }, "Nothing here yet.")
      : h("div", { className: "table-scroll" }, h("table", { className: "data-table", id: `hc-table-${id}` },
        h("thead", {}, h("tr", {}, [...s.cols.map(([l]) => h("th", {}, l)), h("th", {}, "")])),
        h("tbody", {}, rows.map((r) => h("tr", { "data-row": r.id },
          [...s.cols.map(([, f]) => h("td", {}, String(safe(() => f(r, ctx))))),
            h("td", {}, visibleActions(s, r, c, userId, ctx).map((x) => btn(x.label, `hc-act-${x.id}-${r.id}`, () => a.runAction(id, x.id, r.id), "secondary", hc.busy)))]))))));
}
const safe = (f) => { try { const v = f(); return v == null ? "" : v; } catch { return ""; } };

function formView(hc, a) {
  const f = hc.form, def = FORMS[f.name], v = f.values;
  const input = (fd, val, set, idp) => {
    const id = `hf-${idp}`;
    if (fd.type === "area") return h("textarea", { id, rows: 2, onInput: (e) => set(e.target.value) }, val || "");
    if (fd.type === "select") return h("select", { id, onChange: (e) => set(e.target.value) }, [h("option", { value: "" }, fd.req ? "Choose..." : "None"), ...choices(fd.opts, hc, f.row).map(([x, l]) => h("option", { value: x, selected: x === val }, l))]);
    if (fd.type === "check") return h("input", { id, type: "checkbox", checked: !!val, onChange: (e) => set(e.target.checked) });
    return h("input", { id, type: "text", value: val == null ? "" : val, onInput: (e) => set(e.target.value) });
  };
  const fieldView = (fd) => {
    if (fd.type === "lines") {
      return h("div", { className: "card", style: "margin-bottom:8px;" }, h("h4", {}, `${label(fd.item || "line")}s`),
        (v[fd.k] || []).map((row, i) => h("div", { "data-line": i, style: "border-bottom:1px solid var(--line, #ddd); margin-bottom:8px;" },
          fd.fields.map((sf) => field(sf.label, `hf-${fd.k}-${i}-${sf.k}`, input(sf, row[sf.k], (x) => a.lineChange(fd.k, i, sf.k, x), `${fd.k}-${i}-${sf.k}`))),
          (v[fd.k] || []).length > 1 ? btn("Remove", `hf-${fd.k}-${i}-remove`, () => a.removeLine(fd.k, i)) : null)),
        btn(`Add ${fd.item || "line"}`, `hf-${fd.k}-add`, () => a.addLine(fd.k)));
    }
    if (fd.type === "evidence") {
      const vault = hc.vault || [];
      return h("div", { className: "field" }, h("label", {}, fd.label), vault.length === 0 ? h("div", { style: "color: var(--ink-500);" }, "No evidence in the vault yet.")
        : vault.map((ev) => h("label", { style: "display:block;" }, h("input", { type: "checkbox", id: `hf-ev-${ev.id}`, checked: (v.evidence_ids || []).includes(ev.id), onChange: () => a.toggleEvidence(ev.id) }), ` ${ev.filename || ev.label || ev.id}`)));
    }
    if (fd.type === "facilities") {
      return h("div", { className: "field" }, h("label", {}, fd.label), (hc.options.facilities || []).map((x) => h("label", { style: "display:block;" }, h("input", { type: "checkbox", id: `hf-fac-${x.id}`, checked: (v.facility_ids || []).includes(x.id), onChange: () => a.toggleFacility(x.id) }), ` ${x.ref} ${x.name}`)));
    }
    return field(fd.label + (fd.req ? " *" : ""), `hf-${fd.k}`, input(fd, v[fd.k], (x) => a.formChange(fd.k, x), fd.k));
  };
  return h("div", { className: "card", id: "hc-form", style: "margin-bottom:12px;" }, h("h3", {}, f.row && def.prefill ? `Edit: ${def.title}` : def.title),
    def.fields.map(fieldView),
    h("div", { style: "display:flex; gap:8px; margin:8px 0;" }, btn("Save", "hf-save", () => a.saveForm(), "primary", hc.busy), btn("Cancel", "hf-cancel", () => a.cancelForm())));
}
