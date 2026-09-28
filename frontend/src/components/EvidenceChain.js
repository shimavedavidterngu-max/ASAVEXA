import { h, Fragment } from "../lib/vdom.js";
import { StatusBadge } from "./StatusBadge.js";

/**
 * EvidenceChain — ASAVEXA's central traceability component (Section
 * 11): Transaction -> Evidence -> Reconciliation -> Control -> Finding
 * -> Remediation -> Verification -> Audit Event.
 *
 * `links` is an ordered array the caller builds from real API
 * responses — this component NEVER fetches, infers, or fabricates a
 * relationship. A stage the caller has no data for must be passed as
 * `null`/absent, which renders literally as "No linked record" (per
 * Section 11's explicit instruction) — never silently omitted (that
 * would look like the chain simply ended, which is a different claim
 * than "this transaction has no evidence"), and never guessed.
 *
 * `link` shape: { stage: string, label: string, status?: string,
 * href?: string, meta?: string } or null.
 */
const STAGES = [
  "transaction", "evidence", "reconciliation", "control",
  "finding", "remediation", "verification", "audit_event",
];

const STAGE_TITLES = {
  transaction: "Transaction", evidence: "Evidence", reconciliation: "Reconciliation",
  control: "Control", finding: "Finding", remediation: "Remediation",
  verification: "Verification", audit_event: "Audit Event",
};

export function EvidenceChain({ links, onNavigate }) {
  const byStage = Object.fromEntries((links || []).filter(Boolean).map((l) => [l.stage, l]));

  const nodes = STAGES.map((stage, i) => {
    const link = byStage[stage] || null;
    const node = link ? renderLinkedNode(stage, link, onNavigate) : renderMissingNode(stage);
    const arrow = i < STAGES.length - 1 ? h("span", { className: "chain-arrow", "aria-hidden": "true" }, "→") : null;
    return Fragment([node, arrow]);
  });

  return h(
    "div",
    { className: "evidence-chain", role: "list", "aria-label": "Evidence and control traceability chain" },
    nodes
  );
}

function renderLinkedNode(stage, link, onNavigate) {
  const clickable = Boolean(onNavigate && link.href);
  return h(
    "div",
    {
      className: "chain-node",
      role: "listitem",
      tabindex: clickable ? "0" : undefined,
      onClick: clickable ? () => onNavigate(link.href) : undefined,
      onKeydown: clickable
        ? (e) => {
            if (e.key === "Enter" || e.key === " ") onNavigate(link.href);
          }
        : undefined,
      style: clickable ? "cursor: pointer;" : undefined,
    },
    h("div", { className: "mono", style: "font-size: 10.5px; color: var(--ink-500); text-transform: uppercase;" }, STAGE_TITLES[stage]),
    h("div", {}, link.label),
    link.status ? StatusBadge({ status: link.status }) : null,
    link.meta ? h("div", { style: "font-size: 11.5px; color: var(--ink-500);" }, link.meta) : null
  );
}

function renderMissingNode(stage) {
  return h(
    "div",
    { className: "chain-node chain-missing", role: "listitem" },
    h("div", { className: "mono", style: "font-size: 10.5px; text-transform: uppercase;" }, STAGE_TITLES[stage]),
    h("div", {}, "No linked record")
  );
}

export { STAGES as __CHAIN_STAGES__ };
