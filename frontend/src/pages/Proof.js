import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState, EmptyState } from "../components/DataState.js";
import { REPORT_CHOICES, stateInfo, evidenceText, evidenceTone, pct, chain, groupLayers, failingChecks, canBuild } from "../lib/proof.js";

/**
 * Proof Graph: how each figure in a report is built from journals, and how each journal is supported by evidence; plus a live check that every
 * layer of ASAVEXA is present and wired. Read-only. The server does the checking; this page only shows it.
 */
const Badge = ({ tone, label, id }) => h("span", { className: `badge badge-${tone || "neutral"}`, id }, label);

export function Proof({ proof, periods, loading, onRetry, actions }) {
  return h("div", {},
    h("h1", {}, "Proof Graph"),
    h("p", { style: "color: var(--ink-500); margin-top:-8px;" }, "Pick a report and see where every figure comes from: the journals behind it and the evidence behind each journal."),
    proof.error ? ErrorState({ message: proof.error, onRetry }) : null,
    loading ? LoadingState() : h("div", {}, graphCard(proof, periods || [], actions), architectureCard(proof, actions)));
}

function graphCard(p, periods, a) {
  const g = p.graph;
  return h("div", { className: "card", id: "proof-graph", style: "margin-bottom:16px;" },
    h("h3", {}, "Report to evidence"),
    periods.length === 0 ? EmptyState({ title: "No accounting periods yet", message: "Open a period and post journals, then come back here." }) : h("div", {},
      h("div", { style: "display:flex; flex-wrap:wrap; gap:12px; align-items:flex-end;" },
        h("div", { className: "field" }, h("label", { for: "proof-period" }, "Period"),
          h("select", { id: "proof-period", onChange: (e) => a.setPeriod(e.target.value) }, [h("option", { value: "" }, "Choose a period"), ...periods.map((x) => h("option", { value: x.id, selected: p.period_id === x.id }, x.name))])),
        h("div", { className: "field" }, h("label", { for: "proof-report" }, "Report"),
          h("select", { id: "proof-report", onChange: (e) => a.setReport(e.target.value) }, REPORT_CHOICES.map(([v, l]) => h("option", { value: v, selected: p.report === v }, l)))),
        h("button", { className: "btn btn-primary", id: "proof-build", disabled: !canBuild(p), onClick: () => a.build() }, p.busy ? "Checking…" : "Build the proof")),
      g ? graphBody(g, p, a) : h("p", { style: "color: var(--ink-500);" }, "Choose a period and press the button.")));
}

function graphBody(g, p, a) {
  const info = stateInfo(g.state), s = g.summary, bad = failingChecks(g), rows = chain(g);
  return h("div", { id: "proof-result", style: "margin-top:16px;" },
    h("div", { style: "display:flex; gap:10px; align-items:center; flex-wrap:wrap;" }, Badge({ tone: info.tone, label: info.label, id: "proof-state" }), h("span", { id: "proof-meaning" }, g.meaning)),
    h("div", { style: "display:flex; flex-wrap:wrap; gap:8px; margin:12px 0;", id: "proof-summary" },
      [["Lines", s.lines], ["Journals", s.journals], ["With evidence", `${s.with_evidence} (${pct(s.coverage_pct)})`], ["Verified", `${s.verified} (${pct(s.verified_pct)})`], ["No evidence", s.missing_evidence], ["Figures that do not tie", s.tie_failures]].map(([k, v]) =>
        h("div", { className: "card", style: "padding:8px 12px; min-width:110px;" }, h("div", { style: "color: var(--ink-500);" }, k), h("strong", {}, String(v))))),
    s.truncated ? h("div", { className: "alert alert-warning", role: "status" }, "This period has many journals, so only the first ones are drawn. The counts above cover only what is drawn.") : null,
    bad.length ? h("div", { className: "alert alert-error", id: "proof-bad", role: "alert" }, h("strong", {}, "Needs attention: "), bad.map((c) => `${c.name} (${c.detail})`).join("; ")) : null,
    rows.length === 0 ? h("p", {}, "No report lines in this period.") : h("div", { id: "proof-lines" }, rows.map((r) => lineBlock(r, p, a))),
    h("p", { style: "color: var(--ink-500); font-size:0.9em;" }, g.limits));
}

function lineBlock(r, p, a) {
  const open = !!(p.open && p.open[r.id]);
  return h("div", { className: "card", "data-line": r.id, style: "margin-bottom:8px;" },
    h("div", { style: "display:flex; justify-content:space-between; gap:8px; flex-wrap:wrap;" },
      h("div", {}, h("strong", {}, r.label), h("span", { style: "color: var(--ink-500);" }, ` · ${r.section}`)),
      h("div", {}, h("strong", {}, r.amount), " ", h("button", { className: "btn btn-secondary", "aria-expanded": open ? "true" : "false", onClick: () => a.toggle(r.id) }, open ? "Hide journals" : `Show ${r.journals.length} journal${r.journals.length === 1 ? "" : "s"}`))),
    open ? h("ul", { style: "margin:8px 0 0; padding-left:18px;" }, r.journals.map((j) => h("li", { "data-journal": j.id, style: "margin-bottom:6px;" },
      h("span", {}, `${j.label} · ${j.date} · ${j.description || "no description"} · `), h("span", {}, `debit ${j.debit}, credit ${j.credit} `),
      Badge({ tone: evidenceTone(j.evidence_status), label: evidenceText(j.evidence_status) }), j.evidence ? h("span", { style: "color: var(--ink-500);" }, ` ${j.evidence.label}`) : null))) : null);
}

function architectureCard(p, a) {
  const arch = p.arch;
  return h("div", { className: "card", id: "proof-arch" },
    h("h3", {}, "Is every layer connected?"),
    h("p", { style: "color: var(--ink-500); margin-top:-6px;" }, "A live check that each part of ASAVEXA loads and its routes are mounted on this server."),
    !arch ? h("button", { className: "btn btn-secondary", id: "arch-run", onClick: () => a.checkArchitecture() }, "Check now") : h("div", {},
      h("div", { style: "margin-bottom:10px;" }, Badge({ tone: arch.ok ? "pass" : "fail", label: arch.ok ? "All layers present and wired" : "Something is missing", id: "arch-state" }), " ", h("button", { className: "btn btn-secondary", onClick: () => a.checkArchitecture() }, "Check again")),
      groupLayers(arch.layers).map((grp) => h("div", { style: "margin-bottom:10px;" }, h("div", { style: "color: var(--ink-500); font-size:0.85em; text-transform:uppercase;" }, grp.name),
        h("div", { style: "display:flex; flex-wrap:wrap; gap:8px;" }, grp.layers.map((l) => h("div", { className: "card", "data-layer": l.id, style: "padding:8px 12px; min-width:170px;" },
          h("div", {}, h("strong", {}, l.name), " ", Badge({ tone: l.ok ? "pass" : "fail", label: l.ok ? "OK" : "Problem" })),
          h("div", { style: "color: var(--ink-500); font-size:0.85em;" }, l.parts.join(", ")),
          l.problems.length ? h("ul", { style: "color: var(--danger, #b00020); font-size:0.85em; padding-left:16px;" }, l.problems.map((x) => h("li", {}, x))) : null))))),
      h("p", { style: "color: var(--ink-500); font-size:0.9em;" }, arch.note)));
}
