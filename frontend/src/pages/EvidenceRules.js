import { h } from "../lib/vdom.js";
import { PermissionGate } from "../components/PermissionGate.js";
import { PERMISSIONS } from "../lib/permissions.js";
import { ACCOUNT_TYPES, EVIDENCE_TYPES, SEVERITIES, BASELINE_RULE, describeRule, ruleStatus, versionLabel, canDecide, MAX_RULES } from "../lib/evidenceRules.js";

/**
 * Expected records: what evidence each kind of journal should have. These are the organisation's own expectations, not a legal or accounting standard.
 * A change is proposed by one person and approved by another before it applies. The baseline rule (every journal needs evidence) cannot be removed.
 */
const Badge = ({ tone, label, id }) => h("span", { className: `badge badge-${tone || "neutral"}`, id }, label);
const short = (id) => (id ? String(id).slice(0, 8) : "—");

export function RulesCard({ er, me, role, actions: a }) {
  const ov = er.rules;
  return h("div", { className: "card", id: "er-rules", style: "margin-bottom:16px;" },
    h("h3", {}, "Expected records"),
    !ov ? h("p", { id: "er-rules-none" }, "Not loaded.") : h("div", {},
      h("p", { style: "color: var(--ink-500);", id: "er-rules-note" }, ov.note),
      h("p", {}, h("strong", {}, "In use: "), h("span", { id: "er-rules-version" }, versionLabel(ov.active))),
      activeTable(ov.active),
      ov.pending ? pendingBox(ov.pending, er, me, role, a) : PermissionGate({ role, permission: PERMISSIONS.GRC_PREPARE }, editor(er, ov, a)),
      historyList(ov)));
}

function activeTable(active) {
  return h("table", { className: "table", id: "er-rules-table" }, h("thead", {}, h("tr", {}, ["Rule", "Applies to", "Expects", "Importance"].map((t) => h("th", {}, t)))),
    h("tbody", {}, active.rules.map((r) => { const d = describeRule(r); return h("tr", { "data-rule": r.id }, h("td", {}, h("strong", {}, r.id), ` ${r.name}`), h("td", {}, d.appliesTo), h("td", {}, d.expects), h("td", {}, r.severity)); })));
}

function pendingBox(p, er, me, role, a) {
  const mine = me === p.proposed_by;
  return h("div", { className: "alert alert-warning", id: "er-rules-pending", role: "status", style: "margin:12px 0;" },
    h("strong", {}, `Version ${p.version} is waiting for approval. `), `Proposed by ${mine ? "you" : short(p.proposed_by)}: ${p.reason}`,
    h("table", { className: "table", style: "margin-top:8px;" }, h("tbody", {}, p.rules.map((r) => { const d = describeRule(r); return h("tr", { "data-pending-rule": r.id }, h("td", {}, h("strong", {}, r.id), ` ${r.name}`), h("td", {}, d.appliesTo), h("td", {}, d.expects)); }))),
    PermissionGate({ role, permission: PERMISSIONS.GRC_APPROVE }, canDecide(p, me, true) ? h("div", {},
      h("div", { className: "field" }, h("label", { for: "er-rules-note-in" }, "Note (needed to reject)"), h("input", { id: "er-rules-note-in", value: er.ruleNote || "", onInput: (e) => a.setRuleNote(e.target.value) })),
      h("button", { className: "btn btn-primary", id: "er-rules-approve", disabled: er.busy, onClick: () => a.approveRules(p.version) }, "Approve and start using"), " ",
      h("button", { className: "btn btn-secondary", id: "er-rules-reject", disabled: er.busy, onClick: () => a.rejectRules(p.version) }, "Reject"))
      : h("p", { "data-sod": "1", id: "er-rules-sod" }, mine ? "You proposed this change, so someone else must approve it." : "You are not allowed to decide on this change.")));
}

function editor(er, ov, a) {
  const d = er.ruleDraft;
  if (!d) return h("button", { className: "btn btn-secondary", id: "er-rules-start", onClick: () => a.startRuleDraft() }, "Propose a change");
  const group = (i, r, field, list, title) => h("fieldset", { style: "border:0; padding:0; margin:6px 0;" }, h("legend", { style: "font-size:0.9em;" }, title),
    list.map(([v, t]) => h("label", { style: "margin-right:10px; white-space:nowrap;" }, h("input", { type: "checkbox", "data-rule-field": `${field}:${v}`, checked: !!(r[field] && r[field].includes(v)), onChange: () => a.toggleRuleValue(i, field, v) }), ` ${t}`)));
  return h("div", { id: "er-rules-editor", style: "margin-top:12px;" },
    h("h4", {}, "Propose a change"),
    d.map((r, i) => { const base = r.id === BASELINE_RULE; return h("div", { className: "card", "data-edit-rule": r.id, style: "margin-bottom:8px;" },
      h("div", { style: "display:flex; gap:8px; flex-wrap:wrap; align-items:flex-end;" },
        h("strong", {}, r.id),
        h("div", { className: "field", style: "flex:1; min-width:200px;" }, h("label", { for: `er-rule-name-${i}` }, "Name"), h("input", { id: `er-rule-name-${i}`, value: r.name, onInput: (e) => a.setRuleField(i, "name", e.target.value) })),
        h("div", { className: "field" }, h("label", { for: `er-rule-sev-${i}` }, "Importance"), h("select", { id: `er-rule-sev-${i}`, onChange: (e) => a.setRuleField(i, "severity", e.target.value, true) }, SEVERITIES.map(([v, t]) => h("option", { value: v, selected: r.severity === v }, t)))),
        base ? h("span", { style: "color: var(--ink-500);" }, "Baseline: applies to every journal and cannot be removed.") : h("button", { className: "btn btn-secondary", "data-remove-rule": r.id, onClick: () => a.removeRule(i) }, "Remove")),
      base ? null : group(i, r, "account_types", ACCOUNT_TYPES, "Applies to journals touching"),
      group(i, r, "expects_any", EVIDENCE_TYPES, base ? "Expects (leave empty for any verified document)" : "Expects at least one of")); }),
    d.length < MAX_RULES ? h("button", { className: "btn btn-secondary", id: "er-rules-add", onClick: () => a.addRule() }, "Add a rule") : null,
    h("div", { className: "field", style: "margin-top:8px;" }, h("label", { for: "er-rules-reason" }, "Why is this changing?"), h("input", { id: "er-rules-reason", value: er.ruleReason || "", onInput: (e) => a.setRuleReason(e.target.value) })),
    er.ruleError ? h("div", { className: "alert alert-error", id: "er-rules-error", role: "alert" }, er.ruleError) : null,
    h("button", { className: "btn btn-primary", id: "er-rules-submit", disabled: er.busy, onClick: () => a.proposeRules() }, "Send for approval"), " ",
    h("button", { className: "btn btn-secondary", id: "er-rules-cancel", onClick: () => a.cancelRuleDraft() }, "Cancel"),
    h("p", { style: "color: var(--ink-500); font-size:0.9em;" }, "A different person must approve this before it applies. Open cases keep the rules they were measured with."));
}

function historyList(ov) {
  if (!ov.history.length) return h("p", { style: "color: var(--ink-500);", id: "er-rules-nohistory" }, "No changes yet. The built-in defaults are in use.");
  return h("details", { id: "er-rules-history" }, h("summary", {}, "Change history"), h("ul", { style: "padding-left:18px;" }, ov.history.map((x) => { const s = ruleStatus(x.status);
    return h("li", { "data-version": x.version }, h("strong", {}, `Version ${x.version} `), Badge({ tone: s.tone, label: s.label }), ` ${x.reason || ""}${x.decision_note ? ` · ${x.decision_note}` : ""}`); })));
}
