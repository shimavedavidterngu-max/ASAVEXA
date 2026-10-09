import { h, Fragment } from "../lib/vdom.js";
import { DataTable } from "../components/DataTable.js";
import { LoadingState, ErrorState } from "../components/DataState.js";
import { allowed } from "../components/PermissionGate.js";
import { PERMISSIONS } from "../lib/permissions.js";

/**
 * Standards & Policies. Pure render function. Walks the chain
 * Organisation -> Jurisdiction -> Entity type -> Reporting framework
 * -> Accounting policies -> Reporting requirements. Every
 * recommendation, policy rule and requirement shown here is computed by
 * the backend's Standards Configuration Engine; this page never decides
 * which framework or treatment applies.
 */
export function Standards({
  role, organisationName, loading, error, onRetry,
  catalog, form, preview, previewError, previewing, saving, saveError, saved,
  onFieldChange, onPolicyChange, onUseRecommended, onSave,
}) {
  const canEdit = allowed(role, PERMISSIONS.ORG_MANAGE_SETTINGS);
  if (loading) return h("div", {}, h("h1", {}, "Standards & Policies"), LoadingState());
  if (error) return h("div", {}, h("h1", {}, "Standards & Policies"), ErrorState({ message: error, onRetry }));
  const f = form || {};
  return h(
    "div",
    {},
    h("h1", {}, "Standards & Policies"),
    h("p", { style: "color: var(--ink-500); margin-top: -8px; margin-bottom: 24px;" },
      "Tell ASAVEXA where the organisation operates and what kind of entity it is. It recommends the reporting framework, the accounting policies that go with it, and the statements you must produce."),
    selectorCard({ catalog, f, canEdit, onFieldChange }),
    previewError ? h("div", { className: "alert alert-error" }, previewError) : null,
    previewing && !preview ? LoadingState("Working out the recommendation…") : null,
    preview ? Fragment([
      chainCard(organisationName, preview),
      frameworkCard({ catalog, preview, f, canEdit, onFieldChange, onUseRecommended }),
      policiesCard({ preview, canEdit, onPolicyChange }),
      requirementsCard(preview),
      h("div", { className: "card" },
        saveError ? h("div", { className: "alert alert-error" }, saveError) : null,
        saved ? h("div", { className: "alert alert-info" }, "Configuration saved.") : null,
        canEdit
          ? h("button", { className: "btn btn-primary", disabled: saving, onClick: onSave }, saving ? "Saving…" : "Save configuration")
          : h("div", { style: "color: var(--ink-500);" }, "You can view this configuration but only an owner or administrator can change it."),
        h("p", { style: "color: var(--ink-500); font-size:12.5px; margin-top:12px;" }, preview.disclaimer)),
    ]) : null
  );
}

function selectorCard({ catalog, f, canEdit, onFieldChange }) {
  const c = catalog || { jurisdictions: [], entity_types: [] };
  return h(
    "div", { className: "card" },
    h("h2", {}, "1. Jurisdiction and entity type"),
    h("div", { style: "display:flex; gap:12px; flex-wrap:wrap;" },
      h("div", { className: "field" }, h("label", {}, "Jurisdiction (country of reporting)"),
        h("select", { value: f.jurisdiction || "", disabled: !canEdit, onChange: (e) => onFieldChange("jurisdiction", e.target.value) },
          h("option", { value: "" }, "Select jurisdiction…"),
          c.jurisdictions.map((j) => h("option", { value: j.code }, j.name)))),
      h("div", { className: "field" }, h("label", {}, "Entity type"),
        h("select", { value: f.entity_type || "", disabled: !canEdit, onChange: (e) => onFieldChange("entity_type", e.target.value) },
          h("option", { value: "" }, "Select entity type…"),
          c.entity_types.map((t) => h("option", { value: t.code }, t.name)))))
  );
}

function chainCard(organisationName, preview) {
  const steps = [{ step: "Organisation", value: organisationName || "This organisation" }, ...preview.chain];
  return h(
    "div", { className: "card" },
    h("h2", {}, "How ASAVEXA reads this organisation"),
    h("div", { style: "display:flex; flex-wrap:wrap; gap:8px; align-items:stretch;" },
      steps.map((s, i) => Fragment([
        h("div", { style: "border:1px solid var(--line); border-radius:8px; padding:8px 12px; min-width:150px;" },
          h("div", { style: "font-size:11.5px; color: var(--ink-500); text-transform:uppercase;" }, s.step),
          h("div", { style: "font-weight:600; font-size:13.5px;" }, s.value)),
        i < steps.length - 1 ? h("div", { style: "align-self:center; color: var(--ink-500);" }, "→") : null,
      ])))
  );
}

function frameworkCard({ catalog, preview, f, canEdit, onFieldChange, onUseRecommended }) {
  const rec = preview.recommendation;
  const frameworks = (catalog && catalog.frameworks) || [];
  const nameOf = (code) => (frameworks.find((x) => x.code === code) || { name: code }).name;
  const isRecommended = preview.framework === rec.framework;
  return h(
    "div", { className: "card" },
    h("h2", {}, "2. Reporting framework"),
    h("div", { style: "margin-bottom:8px;" },
      h("strong", {}, "Recommended: "), nameOf(rec.framework),
      h("span", { style: "color: var(--ink-500); font-size:12.5px; margin-left:8px;" },
        rec.confidence === "established" ? "(well-established rule)" : "(commonly applied — confirm for your situation)")),
    h("div", { style: "color: var(--ink-500); font-size:13px; margin-bottom:12px;" }, rec.rationale),
    rec.alternatives.length ? h("div", { style: "font-size:13px; margin-bottom:12px;" }, `Recognised alternatives: ${rec.alternatives.map(nameOf).join(", ")}`) : null,
    h("div", { style: "display:flex; gap:12px; align-items:flex-end; flex-wrap:wrap;" },
      h("div", { className: "field" }, h("label", {}, "Framework in use"),
        h("select", { value: preview.framework, disabled: !canEdit, onChange: (e) => onFieldChange("framework", e.target.value) },
          frameworks.map((fw) => h("option", { value: fw.code }, fw.name)))),
      (!isRecommended && canEdit) ? h("button", { className: "btn btn-secondary", onClick: onUseRecommended }, "Use recommended") : null),
    (preview.warnings || []).map((w) => h("div", { className: "alert alert-info", style: "margin-top:8px;" }, w))
  );
}

function policiesCard({ preview, canEdit, onPolicyChange }) {
  const policies = preview.policies;
  return h(
    "div", { className: "card" },
    h("h2", {}, "3. Accounting policies"),
    policies.length === 0
      ? h("p", { style: "color: var(--ink-500);" }, "This framework has no accrual accounting policies to configure.")
      : h("div", { className: "table-scroll" }, h("table", { className: "data-table" },
          h("thead", {}, h("tr", {}, h("th", {}, "Policy"), h("th", {}, "Treatment"), h("th", {}, "Why"))),
          h("tbody", {}, policies.map((p) => h("tr", {},
            h("td", {}, h("div", { style: "font-weight:600;" }, p.name), h("div", { style: "font-size:12px; color: var(--ink-500);" }, p.description)),
            h("td", {},
              p.locked
                ? h("div", {}, p.options[0].label, h("div", { style: "font-size:12px; color: var(--ink-500);" }, "Required by this framework"))
                : h("select", { value: p.effective, disabled: !canEdit, onChange: (e) => onPolicyChange(p.code, e.target.value) },
                    p.options.map((o) => h("option", { value: o.code }, o.label + (o.code === p.default ? " (default)" : ""))))),
            h("td", { style: "font-size:12.5px; color: var(--ink-500);" }, p.note))))))
  );
}

function requirementsCard(preview) {
  const r = preview.readiness;
  return h(
    "div", { className: "card" },
    h("h2", {}, "4. Reporting requirements"),
    h("p", { style: "color: var(--ink-500); font-size:13px;" },
      `ASAVEXA can currently produce ${r.mandatory_available} of ${r.mandatory_total} mandatory statements for this framework. The rest are shown honestly as not yet available.`),
    DataTable({
      columns: [
        { key: "name", label: "Statement / disclosure" },
        { key: "mandatory", label: "Required", render: (x) => (x.mandatory ? "Mandatory" : "Supporting") },
        { key: "available", label: "In ASAVEXA", render: (x) => (x.available ? "✓ Available" : "Not yet available") },
        { key: "description", label: "What it is" },
      ],
      rows: preview.requirements,
    })
  );
}
