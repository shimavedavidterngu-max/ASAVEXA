/** Pure helpers for the Proof Graph page. No DOM, no network. */

export const STATE_INFO = {
  PROVEN: { tone: "pass", label: "Proven" },
  PARTIAL: { tone: "warn", label: "Partly proven" },
  BROKEN: { tone: "fail", label: "Does not tie" },
  EMPTY: { tone: "neutral", label: "Nothing to prove yet" },
};
export const stateInfo = (s) => STATE_INFO[s] || { tone: "neutral", label: s || "—" };

export const REPORT_CHOICES = [["balance_sheet", "Balance sheet"], ["income_statement", "Income statement"]];

const EVIDENCE_TEXT = { MISSING: "No evidence attached", VERIFIED: "Evidence verified", UPLOADED: "Evidence attached, not yet verified", INCOMPLETE: "Evidence incomplete", DUPLICATE: "Duplicate evidence", CONFLICTING: "Evidence conflicts", EXPIRED: "Evidence expired", REJECTED: "Evidence rejected" };
export const evidenceText = (s) => EVIDENCE_TEXT[s] || String(s || "—");
export const evidenceTone = (s) => (s === "VERIFIED" ? "pass" : s === "MISSING" || s === "REJECTED" || s === "CONFLICTING" ? "fail" : "warn");

export const pct = (v) => (v == null ? "—" : `${v}%`);

/** Turns the flat graph (nodes + edges) into report -> lines -> journals -> evidence, ready to draw. Order follows the report. */
export function chain(graph) {
  if (!graph) return [];
  const byId = new Map(graph.nodes.map((n) => [n.id, n]));
  const out = new Map(), journalEdges = new Map(), evidenceOf = new Map();
  for (const e of graph.edges) {
    if (e.kind === "built_from") { if (!journalEdges.has(e.from)) journalEdges.set(e.from, []); journalEdges.get(e.from).push(e); }
    if (e.kind === "supported_by") evidenceOf.set(e.from, byId.get(e.to));
    out.set(e.to, true);
  }
  return graph.nodes.filter((n) => n.kind === "line").map((line) => ({
    id: line.id, label: line.label, amount: line.amount, section: line.section,
    journals: (journalEdges.get(line.id) || []).map((e) => {
      const j = byId.get(e.to);
      return j ? { id: j.id, label: j.label, date: j.date, description: j.description, debit: e.debit, credit: e.credit, evidence_status: j.evidence_status, transaction_ref: j.transaction_ref, evidence: evidenceOf.get(j.id) || null } : null;
    }).filter(Boolean),
  }));
}

/** Groups the architecture layers for display, keeping the order they were sent in. */
export function groupLayers(layers) {
  const groups = [];
  for (const l of layers || []) {
    let g = groups.find((x) => x.name === l.group);
    if (!g) { g = { name: l.group, layers: [] }; groups.push(g); }
    g.layers.push(l);
  }
  return groups;
}

export const failingChecks = (graph) => (graph ? graph.checks.filter((c) => !c.ok) : []);
export const canBuild = (p) => !!(p && p.period_id && p.report && !p.busy);
