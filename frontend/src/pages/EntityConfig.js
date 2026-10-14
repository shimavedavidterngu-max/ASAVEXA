import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState } from "../components/DataState.js";
import { PermissionGate } from "../components/PermissionGate.js";
import { PERMISSIONS, can } from "../lib/permissions.js";
import { typeOptions, subtypeOptions, typeOf, suggestedFor, changeLines, hiddenCount } from "../lib/entityConfig.js";

/**
 * Organisation type and workspaces: say what kind of organisation this is and which workspaces appear in the menu.
 * Choosing a type only changes suggestions and the menu. It does not give or take away anyone's access, and it does not pick an accounting or legal framework.
 */
export function EntityConfig({ ec, role, loading, onRetry, actions }) {
  return h("div", {},
    h("h1", {}, "Organisation type and workspaces"),
    h("p", { style: "color: var(--ink-500); margin-top:-8px;" }, "Say what kind of organisation this is, and choose which workspaces appear in the menu."),
    ec.error ? ErrorState({ message: ec.error, onRetry }) : null,
    ec.notice ? h("div", { className: "alert alert-success", id: "ec-notice", role: "status", style: "margin-bottom:12px;" }, ec.notice) : null,
    loading || !ec.catalog || !ec.config ? (ec.error ? null : LoadingState()) : h("div", {}, statusCard(ec), can(role, PERMISSIONS.ORG_MANAGE_SETTINGS) ? formCard(ec, actions) : readOnly(), historyCard(ec),
      h("p", { id: "ec-note", style: "color: var(--ink-500); font-size:0.9em;" }, ec.catalog.note)));
}

function statusCard(ec) {
  const c = ec.config, t = typeOf(ec.catalog, c.entity_type), st = t && t.subtypes.find((s) => s.code === c.subtype);
  return h("div", { className: "card", id: "ec-status", style: "margin-bottom:16px;" }, h("h3", {}, "Now"),
    !c.configured ? h("p", { id: "ec-unconfigured" }, "This organisation has not described itself yet, so every workspace is shown.")
      : h("div", {}, h("p", { id: "ec-current" }, `${t ? t.label : c.entity_type}${st ? ` · ${st.label}` : ""}${c.custom_subtype ? ` · ${c.custom_subtype}` : ""}`),
        h("p", { id: "ec-hidden" }, hiddenCount(c, ec.workspaces) ? `${hiddenCount(c, ec.workspaces)} workspace(s) are hidden from the menu. Nobody's access has changed.` : "Every workspace is shown."),
        c.languages.length || c.timezone ? h("p", { className: "hm-muted" }, `${c.languages.length ? `Languages: ${c.languages.join(", ")}. ` : ""}${c.timezone ? `Time zone: ${c.timezone}.` : ""}`) : null));
}

const readOnly = () => h("div", { className: "card", id: "ec-readonly", style: "margin-bottom:16px;" }, h("p", {}, "You can see how this organisation is set up. Changing it needs the “manage organisation settings” permission."));

function formCard(ec, a) {
  const f = ec.form, subs = subtypeOptions(ec.catalog, f.entity_type), configured = ec.config.configured, suggested = suggestedFor(ec.catalog, f.entity_type, ec.workspaces);
  return h("div", { className: "card", id: "ec-form", style: "margin-bottom:16px;" }, h("h3", {}, configured ? "Change the set-up" : "Describe this organisation"),
    h("label", { htmlFor: "ec-type" }, "Kind of organisation"),
    h("select", { id: "ec-type", onChange: (e) => a.setField("entity_type", e.target.value) }, [h("option", { value: "" }, "Choose…"), ...typeOptions(ec.catalog).map((t) => h("option", { value: t.code, selected: t.code === f.entity_type }, t.label))]),
    h("label", { htmlFor: "ec-subtype", style: "display:block;margin-top:8px;" }, "Subtype (optional)"),
    h("select", { id: "ec-subtype", disabled: !f.entity_type, onChange: (e) => a.setField("subtype", e.target.value) }, [h("option", { value: "" }, "Not listed"), ...subs.map((s) => h("option", { value: s.code, selected: s.code === f.subtype }, s.label))]),
    h("label", { htmlFor: "ec-custom", style: "display:block;margin-top:8px;" }, "Or describe it in your own words (optional)"),
    h("input", { type: "text", id: "ec-custom", maxLength: 80, value: f.custom_subtype, onInput: (e) => a.setField("custom_subtype", e.target.value) }),
    h("h4", {}, "Workspaces shown in the menu"),
    f.entity_type ? h("button", { className: "btn btn-secondary", id: "ec-suggest", onClick: () => a.useSuggested() }, `Use the suggested set (${suggested.length})`) : null,
    h("ul", { id: "ec-workspaces", style: "list-style:none;padding-left:0;" }, ec.workspaces.map((w) => h("li", { "data-ws": w.id },
      h("label", {}, h("input", { type: "checkbox", id: `ec-ws-${w.id}`, checked: f.enabled.includes(w.id), onChange: () => a.toggle(w.id) }), ` ${w.name}`, suggested.includes(w.id) ? h("span", { className: "hm-muted" }, " (suggested)") : null)))),
    h("label", { htmlFor: "ec-languages" }, "Languages (optional, for example en, fr)"),
    h("input", { type: "text", id: "ec-languages", value: f.languages, onInput: (e) => a.setField("languages", e.target.value) }),
    h("label", { htmlFor: "ec-timezone", style: "display:block;margin-top:8px;" }, "Time zone (optional, for example Africa/Lagos)"),
    h("input", { type: "text", id: "ec-timezone", value: f.timezone, onInput: (e) => a.setField("timezone", e.target.value) }),
    configured ? h("div", {}, h("label", { htmlFor: "ec-reason", style: "display:block;margin-top:8px;" }, "Why are you changing this?"), h("input", { type: "text", id: "ec-reason", value: f.note, onInput: (e) => a.setField("note", e.target.value) })) : null,
    ec.formError ? h("p", { className: "alert alert-error", id: "ec-form-error" }, ec.formError) : null,
    h("p", { className: "hm-muted" }, "Hiding a workspace only removes it from the menu. It does not take away anyone's access or delete anything."),
    h("button", { className: "btn btn-primary", id: "ec-save", disabled: ec.busy, onClick: () => a.save() }, ec.busy ? "Saving…" : "Save"));
}

function historyCard(ec) {
  const hist = ec.config.history || [];
  return h("div", { className: "card", id: "ec-history" }, h("h3", {}, "History"),
    !hist.length ? h("p", {}, "Nothing recorded yet.") : h("ol", {}, hist.slice().reverse().map((x) => h("li", { "data-version": String(x.version) },
      `v${x.version} ${x.event === "CONFIGURED" ? "set up" : "changed"} by ${x.by}${x.note ? `: ${x.note}` : ""}`, ...changeLines(x).map((l) => h("div", { className: "hm-muted" }, l))))));
}
