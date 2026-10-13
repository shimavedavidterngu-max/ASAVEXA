import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState } from "../components/DataState.js";
import { PermissionGate } from "../components/PermissionGate.js";
import { PERMISSIONS, can } from "../lib/permissions.js";
import { decisionInfo, stateInfo, agentStatus, stricterChoices, grantable, agentActions, canResolve, needsIndependent } from "../lib/agents.js";

/**
 * Agents: the control point for any automation. Register an agent, let a second person activate it, and see every request it makes decided
 * ALLOW, REQUIRE_APPROVAL or DENY. Nothing here runs an agent: this only decides whether an action may go ahead. Only rule-based agents are approved.
 */
const Badge = ({ tone, label, id }) => h("span", { className: `badge badge-${tone || "neutral"}`, id }, label);

export function Agents({ ag, me, role, loading, onRetry, actions }) {
  return h("div", {},
    h("h1", {}, "Agents"),
    h("p", { style: "color: var(--ink-500); margin-top:-8px;" }, "Every automated helper must be registered, approved by a second person, and asks permission for anything risky. Posting, verifying and approving are never allowed for an agent: a person must do them."),
    ag.error ? ErrorState({ message: ag.error, onRetry }) : null,
    ag.notice ? h("div", { className: "alert alert-success", id: "ag-notice", role: "status", style: "margin-bottom:12px;" }, ag.notice) : null,
    loading ? LoadingState() : h("div", {}, policyCard(ag, role, actions), agentsCard(ag, me, role, actions), decisionsCard(ag, me, role, actions)));
}

function policyCard(ag, role, a) {
  return h("div", { className: "card", id: "ag-policy", style: "margin-bottom:16px;" },
    h("h3", {}, "What agents may do"),
    h("table", { className: "table" }, h("thead", {}, h("tr", {}, ["Action", "Built-in rule", "Your rule", ""].map((t) => h("th", {}, t)))),
      h("tbody", {}, (ag.policy || []).map((p) => { const b = decisionInfo(p.builtin), e = decisionInfo(p.effective), more = stricterChoices(p.effective); return h("tr", { "data-policy": p.action },
        h("td", {}, p.label), h("td", {}, Badge({ tone: b.tone, label: b.label })), h("td", {}, Badge({ tone: e.tone, label: e.label })),
        h("td", {}, more.length ? PermissionGate({ role, permission: PERMISSIONS.GRC_APPROVE }, h("select", { "data-tighten": p.action, onChange: (ev) => { if (ev.target.value) a.tighten(p.action, ev.target.value); } },
          [h("option", { value: "" }, "Make stricter…"), ...more.map((m) => h("option", { value: m }, decisionInfo(m).label))])) : null)); }))),
    h("p", { style: "color: var(--ink-500); font-size:0.9em;" }, "You can make a rule stricter, never looser."));
}

function agentsCard(ag, me, role, a) {
  const f = ag.form, members = ag.members || [];
  const chosen = new Set(f.actions);
  return h("div", { className: "card", id: "ag-agents", style: "margin-bottom:16px;" },
    h("h3", {}, "Registered agents"),
    (ag.agents || []).length === 0 ? h("p", { id: "ag-none", style: "color: var(--ink-500);" }, "No agents registered. Nothing in ASAVEXA runs automatically without one.") : ag.agents.map((x) => {
      const st = agentStatus(x.status), acts = agentActions(x, me, can(role, PERMISSIONS.GRC_PREPARE), can(role, PERMISSIONS.GRC_APPROVE));
      return h("div", { className: "card", "data-agent": x.id, "data-status": x.status, style: "margin-bottom:8px;" },
        h("div", { style: "display:flex; gap:8px; flex-wrap:wrap; align-items:center;" }, h("strong", {}, x.name), Badge({ tone: st.tone, label: st.label }), h("span", { style: "color: var(--ink-500);" }, `${x.provider} · may ask to: ${x.actions.join(", ")}`)),
        h("div", {}, x.purpose),
        x.status === "PROPOSED" && x.proposed_by === me ? h("div", { className: "alert alert-warning", "data-sod": "1" }, "You proposed this agent, so someone else must activate it.") : null,
        acts.length ? h("div", { style: "margin-top:6px;" }, h("input", { id: `ag-reason-${x.id}`, placeholder: "Reason (needed to suspend or retire)", value: ag.reasons[x.id] || "", onInput: (e) => a.setReason(x.id, e.target.value), style: "width:100%; margin-bottom:6px;" }),
          acts.map((k) => h("button", { className: "btn btn-secondary", "data-act": k, disabled: ag.busy, style: "margin-right:6px;", onClick: () => a.agentAct(x.id, k) }, k[0].toUpperCase() + k.slice(1)))) : null);
    }),
    PermissionGate({ role, permission: PERMISSIONS.GRC_PREPARE }, h("div", { id: "ag-add", style: "margin-top:12px;" },
      h("h4", {}, "Propose an agent"),
      h("div", { className: "field" }, h("label", { for: "ag-name" }, "Name"), h("input", { id: "ag-name", value: f.name, onInput: (e) => a.setForm("name", e.target.value) })),
      h("div", { className: "field" }, h("label", { for: "ag-purpose" }, "What it is for"), h("input", { id: "ag-purpose", value: f.purpose, onInput: (e) => a.setForm("purpose", e.target.value) })),
      h("div", { className: "field" }, h("label", { for: "ag-owner" }, "Owner"), h("select", { id: "ag-owner", onChange: (e) => a.setForm("owner", e.target.value) }, [h("option", { value: "" }, "Choose a person"), ...members.map((m) => h("option", { value: m.user_id, selected: f.owner === m.user_id }, `${m.user_id === me ? "You" : m.user_id.slice(0, 8)} · ${m.role}`))])),
      h("fieldset", {}, h("legend", {}, "Actions it may ask to perform"), grantable(ag.catalog).map((c) => h("label", { style: "display:block;" }, h("input", { type: "checkbox", "data-action": c.action, checked: chosen.has(c.action), onChange: () => a.toggleAction(c.action) }), ` ${c.label}`))),
      ag.formError ? h("div", { className: "alert alert-error", id: "ag-form-error", role: "alert" }, ag.formError) : null,
      h("button", { className: "btn btn-primary", id: "ag-propose", disabled: ag.busy, onClick: () => a.propose() }, "Propose agent"))));
}

function decisionsCard(ag, me, role, a) {
  const active = (ag.agents || []).filter((x) => x.status === "ACTIVE");
  const r = ag.request;
  return h("div", { className: "card", id: "ag-decisions" },
    h("h3", {}, "Requests and decisions"),
    PermissionGate({ role, permission: PERMISSIONS.GRC_PREPARE }, h("div", { id: "ag-request", style: "margin-bottom:12px;" },
      h("div", { style: "display:flex; flex-wrap:wrap; gap:8px; align-items:flex-end;" },
        h("div", { className: "field" }, h("label", { for: "ag-req-agent" }, "Agent"), h("select", { id: "ag-req-agent", onChange: (e) => a.setRequest("agent_id", e.target.value) }, [h("option", { value: "" }, "Choose an active agent"), ...active.map((x) => h("option", { value: x.id, selected: r.agent_id === x.id }, x.name))])),
        h("div", { className: "field" }, h("label", { for: "ag-req-action" }, "Action"), h("select", { id: "ag-req-action", onChange: (e) => a.setRequest("action", e.target.value) }, [h("option", { value: "" }, "Choose an action"), ...(ag.catalog || []).map((c) => h("option", { value: c.action, selected: r.action === c.action }, c.label))])),
        h("div", { className: "field" }, h("label", { for: "ag-req-subject" }, "About (optional)"), h("input", { id: "ag-req-subject", value: r.subject || "", onInput: (e) => a.setRequest("subject", e.target.value) })),
        h("button", { className: "btn btn-primary", id: "ag-ask", disabled: ag.busy || !r.agent_id || !r.action, onClick: () => a.ask() }, "Ask for a decision"))),),
    (ag.decisions || []).length === 0 ? h("p", { id: "ag-no-decisions", style: "color: var(--ink-500);" }, "No requests yet.") : ag.decisions.map((d) => {
      const di = decisionInfo(d.decision), si = stateInfo(d.state);
      return h("div", { className: "card", "data-decision": d.id, "data-state": d.state, style: "margin-bottom:8px;" },
        h("div", { style: "display:flex; gap:8px; flex-wrap:wrap; align-items:center;" }, h("strong", {}, d.agent_name), h("span", {}, d.action), Badge({ tone: di.tone, label: di.label }), Badge({ tone: si.tone, label: si.label })),
        h("div", { style: "color: var(--ink-500);" }, `${d.reason}${d.subject ? " · " + d.subject : ""}`),
        needsIndependent(d, me) ? h("div", { className: "alert alert-warning", "data-sod": "1" }, "You made this request, so someone else must approve or reject it.") : null,
        canResolve(d, me, can(role, PERMISSIONS.GRC_APPROVE)) ? h("div", { style: "margin-top:6px;" },
          h("input", { id: `ag-note-${d.id}`, placeholder: "Reason (needed to reject)", value: ag.reasons[d.id] || "", onInput: (e) => a.setReason(d.id, e.target.value), style: "width:100%; margin-bottom:6px;" }),
          h("button", { className: "btn btn-primary", "data-act": "approve-request", disabled: ag.busy, style: "margin-right:6px;", onClick: () => a.resolve(d.id, true) }, "Approve"),
          h("button", { className: "btn btn-secondary", "data-act": "reject-request", disabled: ag.busy, onClick: () => a.resolve(d.id, false) }, "Reject")) : null);
    }));
}
