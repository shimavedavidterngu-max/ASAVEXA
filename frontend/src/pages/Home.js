import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState } from "../components/DataState.js";
import { Seal } from "../components/AiDock.js";
import { Dashboard } from "./Dashboard.js";
import { WORKSPACE_TONE } from "../lib/analysis.js";
import { workspaceCards, shortPurpose, quickActions, setupSteps, attentionSummary, roleLabel, displayName } from "../lib/home.js";

/**
 * The signed-in home page. It answers three questions in order: what do I need to do first, what is waiting for me,
 * and where do I go. Everything shown is read through the person's own permissions; a source that fails says so.
 */
const Badge = ({ tone, label }) => h("span", { className: `badge badge-${tone || "neutral"}` }, label);

function welcome({ user, role, orgLabel, sector }) {
  const name = displayName(user);
  return h("section", { className: "hm-welcome", id: "hm-welcome", "aria-labelledby": "hm-h1" },
    h("div", {}, sector ? h("p", { className: "ledger-eyebrow", id: "hm-sector" }, sector.label) : null, h("h1", { id: "hm-h1" }, name ? `Welcome back, ${name}` : "Welcome back"),
      h("p", { className: "hm-sub", id: "hm-sub" }, `${orgLabel} · ${roleLabel(role)}`)));
}

function setupCard(facts, role, onNavigate) {
  const s = setupSteps(facts || {}, role);
  if (!s.show && !s.unknown.length) return null;
  const row = (st) => h("li", { className: `hm-step is-${st.done === true ? "done" : st.done === false ? "todo" : "unknown"}`, "data-step": st.id },
    h("span", { className: "hm-tick", "aria-hidden": "true" }, st.done === true ? "✓" : st.done === false ? "○" : "?"),
    h("span", { className: "hm-steptext" }, st.label, st.done === null || st.done === undefined ? h("small", {}, " Could not be checked right now.") : null),
    st.done === true ? h("span", { className: "hm-donetag" }, "Done") : h("button", { className: "btn btn-secondary btn-sm", id: `hm-setup-${st.id}`, onClick: () => onNavigate(st.path) }, "Go"));
  return h("section", { className: "card hm-setup", id: "hm-setup", "aria-labelledby": "hm-h-setup" },
    h("h2", { id: "hm-h-setup" }, s.show ? "Finish setting up this organisation" : "Setup status"),
    h("p", { className: "hm-muted" }, s.show ? "These steps make the numbers on this page meaningful. Each one opens the page where you do it." : "Some setup steps could not be checked."),
    h("ol", { className: "hm-steps" }, s.steps.map(row)));
}

function attentionCard({ loading, data, onNavigate, onRetry }) {
  const body = loading || !data ? LoadingState()
    : data.attention.items.length ? h("ul", { className: "hm-attn", id: "hm-attn-list" }, data.attention.items.slice(0, 10).map((i) =>
      h("li", { className: `hm-attn-item is-${i.tone}`, "data-tone": i.tone },
        h("span", { className: "hm-attn-dot", "aria-hidden": "true" }),
        h("div", {}, h("a", { href: `#${i.link}`, onClick: (e) => { e.preventDefault(); onNavigate(i.link); } }, i.text), h("small", {}, `${i.workspace} · ${i.tone === "urgent" ? "Urgent" : "Watch"}`)))))
      : h("p", { className: "hm-ok", id: "hm-attn-none" }, attentionSummary(data.attention));
  return h("section", { className: "card hm-attention", id: "hm-attention", "aria-labelledby": "hm-h-attn" },
    h("div", { className: "hm-head" }, h("h2", { id: "hm-h-attn" }, "What needs attention"),
      data && data.attention.items.length ? h("span", { className: "hm-count", id: "hm-attn-count" }, attentionSummary(data.attention)) : null),
    body,
    data && data.attention.failed.length ? h("p", { className: "hm-warn", id: "hm-attn-failed", role: "status" },
      `Could not be checked: ${data.attention.failed.join(", ")}. This list may be incomplete.`,
      " ", h("button", { className: "linklike", id: "hm-attn-retry", onClick: onRetry }, "Try again")) : null,
    data && !loading ? h("p", { className: "hm-muted hm-fine" }, "Built from each workspace’s own overview, using only what your role can see.") : null);
}

function aiCard({ available, onOpenAi }) {
  return h("section", { className: "card hm-ai", id: "hm-ai", "aria-labelledby": "hm-h-ai" },
    h("div", { className: "hm-ai-seal" }, Seal({ size: 44 })),
    h("h2", { id: "hm-h-ai" }, "ASAVEXA AI"),
    h("p", {}, available ? "Ask about your own records. It shows the proof behind every answer, and it says so when it cannot find any. It never posts or approves anything." : "Your role cannot ask questions of the ledger, so ASAVEXA AI is not offered here."),
    available ? h("button", { className: "btn btn-primary", id: "hm-ai-open", onClick: onOpenAi }, "Open ASAVEXA AI") : null);
}

function workspacesSection({ catalogData, role, showLocked, onNavigate, onToggleLocked, loading }) {
  if (loading) return h("section", { id: "hm-workspaces" }, h("h2", {}, "Your workspaces"), LoadingState());
  const w = workspaceCards(catalogData, role);
  const card = (c) => h("article", { className: `card hm-ws${c.canOpen ? "" : " is-locked"}`, "data-ws": c.id },
    h("div", { className: "hm-ws-head" }, h("h3", {}, c.name), c.statusKnown ? Badge({ tone: WORKSPACE_TONE[c.status], label: c.status }) : null),
    c.purpose ? h("p", {}, shortPurpose(c.purpose)) : null,
    c.canOpen
      ? h("button", { className: "btn btn-primary", id: `hm-open-${c.id}`, onClick: () => onNavigate(c.path) }, "Open")
      : h("p", { className: "hm-muted" }, "Not available to your role."));
  return h("section", { id: "hm-workspaces", "aria-labelledby": "hm-h-ws" },
    h("div", { className: "hm-head" }, h("h2", { id: "hm-h-ws" }, "Your workspaces"), h("a", { href: "#/workspaces", id: "hm-all-ws" }, "See all and how each was tested")),
    w.usedFallback ? h("p", { className: "hm-warn", id: "hm-ws-fallback", role: "status" }, "The test status of each workspace could not be loaded, so none is shown. Open the Professional Workspaces page to try again.") : null,
    w.open.length ? h("div", { className: "hm-ws-grid", id: "hm-ws-grid" }, w.open.map(card))
      : h("div", { className: "card empty-state", id: "hm-ws-none" }, h("h3", {}, "No workspace is open to your role"), h("p", {}, "Ask an administrator of this organisation to change your role if you need one.")),
    w.locked.length ? h("div", { className: "hm-locked" },
      h("button", { className: "linklike", id: "hm-locked-toggle", "aria-expanded": showLocked ? "true" : "false", onClick: onToggleLocked },
        showLocked ? "Hide the workspaces your role cannot open" : `Show ${w.locked.length} workspace${w.locked.length === 1 ? "" : "s"} your role cannot open`),
      showLocked ? h("div", { className: "hm-ws-grid", id: "hm-locked-grid" }, w.locked.map(card)) : null) : null);
}

function actionsRow({ role, onNavigate }) {
  const list = quickActions(role);
  if (!list.length) return null;
  return h("section", { className: "card hm-actions", id: "hm-actions", "aria-labelledby": "hm-h-act" },
    h("h2", { id: "hm-h-act" }, "Quick actions"),
    h("div", { className: "hm-actions-row" }, list.map((a) => h("button", { className: "btn btn-secondary", id: `hm-act-${a.id}`, onClick: () => onNavigate(a.path) }, a.label))));
}

export function Home(p) {
  const { role, data, loading, error } = p;
  return h("div", { className: "hm", id: "home" },
    welcome(p),
    error ? ErrorState({ message: error, onRetry: p.onRetry }) : null,
    setupCard(data && data.facts, role, p.onNavigate),
    h("div", { className: "hm-two" }, attentionCard({ loading, data, onNavigate: p.onNavigate, onRetry: p.onRetry }), aiCard({ available: p.aiAvailable, onOpenAi: p.onOpenAi })),
    workspacesSection({ catalogData: data && data.catalog, role, showLocked: p.showLocked, onNavigate: p.onNavigate, onToggleLocked: p.onToggleLocked, loading: loading && !data }),
    actionsRow({ role, onNavigate: p.onNavigate }),
    h("section", { id: "hm-glance", "aria-labelledby": "hm-h-glance" },
      h("h2", { id: "hm-h-glance" }, "Finance at a glance"),
      Dashboard({ role, data: p.dashboardData || {}, onNavigate: p.onNavigate, bare: true })));
}
