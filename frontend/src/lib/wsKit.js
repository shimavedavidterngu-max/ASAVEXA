import { h } from "./vdom.js";
import { LoadingState, ErrorState } from "../components/DataState.js";
import { noteProblem, words } from "./wsCommon.js";

/** Small shared building blocks for the Stage 33+ workspace pages, plus the shared action helpers app.js uses. */
export function ui(st, a, statusOf) {
  const Badge = ({ tone, label, id }) => h("span", { className: `badge badge-${tone || "neutral"}`, id }, label);
  const k = {
    Badge, St: (s) => Badge({ ...statusOf(s) }),
    note: (t, kind = "info", id) => (t ? h("div", { className: `alert alert-${kind}`, id, style: "margin-bottom:12px;", role: kind === "error" ? "alert" : "status" }, t) : null),
    field: (l, id, inp) => h("div", { className: "field" }, h("label", { for: id }, l), inp),
    text: (form, key, id, ph) => h("input", { id, type: "text", value: (st.forms[form] || {})[key] == null ? "" : (st.forms[form] || {})[key], placeholder: ph || "", onInput: (e) => a.setForm(form, key, e.target.value) }),
    area: (form, key, id, rows = 2) => h("textarea", { id, rows, onInput: (e) => a.setForm(form, key, e.target.value) }, (st.forms[form] || {})[key] || ""),
    sel: (form, key, id, opts) => h("select", { id, onChange: (e) => a.setForm(form, key, e.target.value, true) }, opts.map(([v, l]) => h("option", { value: v, selected: String((st.forms[form] || {})[key]) === String(v) }, l))),
    btn: (l, id, onClick, kind = "secondary", disabled = false) => h("button", { className: `btn btn-${kind}`, id, disabled, onClick }, l),
    row: (...b) => h("div", { style: "display:flex; gap:8px; flex-wrap:wrap; margin:8px 0; align-items:end;" }, b.filter(Boolean)),
    none: (t = "None.") => h("div", { style: "color: var(--ink-500);" }, t),
    card: (title, id, ...kids) => h("div", { className: "card", id, style: "margin-bottom:16px;" }, h("h3", {}, title), ...kids),
    hist: (items) => h("ul", {}, (items || []).map((x) => h("li", {}, `${String(x.at).slice(0, 10)} ${String(x.event).replace(/_/g, " ").toLowerCase()} by ${x.by}${x.note ? ": " + x.note : ""}`))),
    formError: (name) => (st.formError && st.formError.form === name ? k.note(st.formError.text, "error", `${name}-problem`) : null),
  };
  k.noteBox = (key, l, id) => k.field(l, id, h("textarea", { id, rows: 2, onInput: (e) => a.setNote(key, e.target.value) }, st.notes[key] || ""));
  k.limits = (list, id = "limits") => k.card("What this does not do", `${id}`, h("ul", {}, list.map((x) => h("li", {}, x))));
  k.settingCard = (p, role, canApprove, label, fieldKey) => k.card("Settings", `${p}-setting`, h("p", { id: `${p}-setting-meaning` }, st.ov.setting.meaning),
    canApprove(role) && st.forms.setting ? h("div", {}, k.row(k.field(label, `${p}-set-${fieldKey}`, k.text("setting", fieldKey, `${p}-set-${fieldKey}`))), k.formError("setting"), k.btn("Save settings", `${p}-set-save`, () => a.saveSetting(), "primary", st.busy)) : h("p", { style: "color: var(--ink-500);" }, "Only an approver can change this setting."));
  return k;
}

/** Page frame: title, banner, error, notice, tabs. body() is called only when loaded. */
export function frame({ st, p, title, banner, tabs, loading, onRetry, a, k, body }) {
  return h("div", {}, h("h1", {}, title), k.note(banner, "info", `${p}-banner`),
    st.error ? ErrorState({ message: st.error, onRetry }) : null, k.note(st.notice, "success", `${p}-notice`),
    loading ? LoadingState() : h("div", {},
      h("div", { className: "tabs", role: "tablist", style: "display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px;" },
        tabs.map(([id, l]) => h("button", { className: `btn ${st.tab === id ? "btn-primary" : "btn-secondary"}`, role: "tab", id: `${p}-tab-${id}`, "aria-selected": st.tab === id ? "true" : "false", onClick: () => a.setTab(id) }, l))),
      st.busy ? h("div", { style: "color: var(--ink-500);" }, "Working...") : null, body()));
}

/** Shared action helpers for a workspace state object. */
export function actionsKit(st, render, refresh, EMPTY) {
  const run = async (fn, ok) => { st.error = null; st.notice = null; st.formError = null; st.busy = true; render(); try { await fn(); if (ok) st.notice = ok; } catch (err) { st.error = err.message || "That did not work."; } st.busy = false; render(); };
  const problem = (form, text) => { st.formError = { form, text }; st.notice = null; st.error = null; render(); };
  const fail = (text) => { st.formError = null; st.notice = null; st.error = text; render(); };
  const reset = (name) => { st.forms[name] = JSON.parse(JSON.stringify(EMPTY[name])); };
  const note = (key) => (st.notes[key] || "").trim();
  const act = (form, errForm, build, call, ok, after) => { const r = build(st.forms[form], st.sel); if (r.problem) return problem(errForm, r.problem); return run(async () => { const x = await call(r.body); if (after) after(x); await refresh(); }, ok); };
  const needNote = (key, what, min, call, ok) => { const p = noteProblem(note(key), what, min); if (p) return fail(p); return run(async () => { await call(note(key)); st.notes = {}; await refresh(); }, ok); };
  const optNote = (key, what, call, ok) => { const n = note(key); if (n) { const p = noteProblem(n, what, 10); if (p) return fail(p); } return run(async () => { await call(n); st.notes = {}; await refresh(); }, ok); };
  const base = {
    setTab: (t) => run(async () => { st.tab = t; st.formError = null; await refresh(); }),
    setForm: (name, k, v, rerender) => { st.forms[name] = { ...(st.forms[name] || {}), [k]: v }; st.formError = null; if (rerender) render(); },
    setNote: (k, v) => { st.notes[k] = v; },
  };
  return { run, problem, fail, reset, note, act, needNote, optNote, base };
}
export { words };
