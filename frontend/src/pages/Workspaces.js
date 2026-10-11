import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState } from "../components/DataState.js";
import { WORKSPACE_TONE, canOpenWorkspace } from "../lib/analysis.js";

/** The professional workspace selector. Every workspace shows its true status; unbuilt ones say so and have no Open button. */
const Badge = ({ tone, label }) => h("span", { className: `badge badge-${tone || "neutral"}` }, label);

export function Workspaces({ data, loading, error, role, onOpen, onRetry }) {
  return h("div", {},
    h("h1", {}, "Professional Workspaces"),
    h("p", { style: "color: var(--ink-500); margin-top:-8px;" }, "Each workspace is built on the same ledger, evidence and audit trail. The status shown is what has actually been tested."),
    error ? ErrorState({ message: error, onRetry }) : null,
    loading || !data ? (error ? null : LoadingState()) : h("div", {},
      h("div", { id: "ws-list", style: "display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:12px;" }, data.workspaces.map((w) => {
        const open = canOpenWorkspace(w, role);
        return h("div", { className: "card", "data-ws": w.id },
          h("div", { style: "display:flex; justify-content:space-between; gap:8px; align-items:flex-start;" }, h("h3", { style: "margin:0;" }, w.name), Badge({ tone: WORKSPACE_TONE[w.status], label: w.status })),
          h("p", {}, w.purpose),
          w.note ? h("p", { style: "color: var(--ink-500); font-size:0.9em;" }, w.note) : null,
          h("p", { style: "color: var(--ink-500); font-size:0.85em;" }, `Builds on: ${w.depends_on.join(", ")}`),
          w.path ? h("button", { className: "btn btn-primary", id: `ws-open-${w.id}`, disabled: !open, onClick: () => onOpen(w.path) }, open ? "Open" : "You do not have access") : null);
      })),
      h("div", { className: "card", id: "ws-foundations", style: "margin-top:16px;" }, h("h3", {}, "Shared foundations"),
        h("ul", { style: "padding-left:18px;" }, data.foundations.map((f) => h("li", { style: "margin-bottom:6px;" }, h("strong", {}, f.name), " ", Badge({ tone: WORKSPACE_TONE[f.status], label: f.status }), h("div", { style: "color: var(--ink-500);" }, f.note))))),
      h("p", { style: "color: var(--ink-500); font-size:0.9em;" }, data.note)));
}
