import { h } from "../lib/vdom.js";
import { EvidenceChain } from "./EvidenceChain.js";
import { DataTable } from "./DataTable.js";
import { EmptyState } from "./DataState.js";
import { StatusBadge } from "./StatusBadge.js";

/**
 * DrilldownPanel — Phase 1's "Why is this number here?" view and the
 * destination of every "Show me the evidence" button in the app.
 *
 * This is deliberately NOT a new data-fetching path: every piece shown
 * here (journal, evidence, evidence completeness, reconciliation
 * status, audit trail) is the exact same already-live API this app
 * already calls elsewhere (AuditWorkspace's chain search, Reporting's
 * trace, /reports/evidence-completeness, /reports/reconciliation-summary,
 * /audit/entity/{type}/{id}) — this component only ever renders what
 * the container (app.js) already assembled. No client-side
 * calculation of any figure happens here (same discipline as
 * Reporting.js and AuditWorkspace.js).
 *
 * "Approval history" is not a separate feed — it is the same audit
 * event list as "audit-event history", split by whether the action
 * name looks like an approval/review/verification/rejection step. An
 * audit event's `action` is always one of the real AuditAction enum
 * values already logged by the relevant service (e.g.
 * RECONCILIATION_APPROVED, CLOSE_APPROVED, CONTROL_REVIEWED,
 * REMEDIATION_VERIFIED, MATCH_REJECTED) — this heuristic never invents
 * a new action, it only groups existing ones for display.
 */
const APPROVAL_ACTION_HINTS = ["APPROVED", "REVIEWED", "VERIFIED", "REJECTED", "CLOSED", "FINALIZED"];

function isApprovalLikeAction(action) {
  return APPROVAL_ACTION_HINTS.some((hint) => (action || "").includes(hint));
}

export function DrilldownPanel({
  open, loading, error, note,
  journal, chainLinks, completeness, reconciliationStatus, auditEvents,
  onClose, onNavigate, onShowEvidence,
}) {
  if (!open) return null;
  const events = auditEvents || [];
  const approvalEvents = events.filter((e) => isApprovalLikeAction(e.action));

  return h(
    "div",
    { className: "modal-backdrop", onClick: (e) => { if (e.target === e.currentTarget) onClose(); } },
    h(
      "div",
      { className: "modal", style: "max-width: 880px; width: 94%; max-height: 86vh; overflow-y: auto;" },
      h(
        "div",
        { style: "display:flex; justify-content:space-between; align-items:flex-start; gap:16px;" },
        h("div", {},
          h("h3", { style: "margin-bottom:2px;" }, "Why is this number here?"),
          h("p", { style: "color: var(--ink-500); font-size:12.5px; margin:0;" },
            "Every figure below is read straight from the backend — nothing on this panel is calculated in the browser.")),
        h("button", { className: "btn", onClick: onClose }, "Close")
      ),
      error ? h("div", { className: "alert alert-error", style: "margin-top:12px;" }, error) : null,
      note ? h("div", { className: "alert alert-info", style: "margin-top:12px;" }, note) : null,
      loading ? h("p", { style: "color: var(--ink-500); margin-top:12px;" }, "Loading…") : null,
      !loading && journal ? journalSummary(journal) : null,
      !loading && journal ? metricsRow({ completeness, reconciliationStatus }) : null,
      !loading && journal
        ? h(
            "div",
            { className: "card", style: "margin-top:16px;" },
            h("div", { style: "display:flex; justify-content:space-between; align-items:center;" },
              h("h4", { style: "margin:0;" }, "Evidence & control traceability chain"),
              h("button", { className: "btn btn-primary", onClick: () => onShowEvidence(journal) }, "Show me the evidence")),
            h("div", { style: "margin-top:12px;" }, EvidenceChain({ links: chainLinks || [], onNavigate }))
          )
        : null,
      !loading && journal ? approvalHistorySection(approvalEvents) : null,
      !loading && journal ? auditHistorySection(events) : null,
      !loading && !journal && !error ? EmptyState({ title: "Nothing to show yet" }) : null
    )
  );
}

function journalSummary(journal) {
  return h(
    "div",
    { className: "card", style: "margin-top:12px;" },
    h("div", { style: "display:flex; justify-content:space-between; align-items:flex-start;" },
      h("div", {},
        h("h3", { style: "margin-bottom:2px;" }, journal.description || "Journal"),
        h("div", { className: "mono", style: "color: var(--ink-500); font-size:12.5px;" }, journal.id)),
      StatusBadge({ status: journal.status })),
    h("div", { style: "margin-top:8px; font-size:13px; color: var(--ink-500);" },
      `${journal.date || ""}  ·  ${journal.currency || ""}`)
  );
}

function metricsRow({ completeness, reconciliationStatus }) {
  const pieces = [];
  if (completeness) {
    const pct = Math.round((completeness.completeness_ratio || 0) * 100);
    pieces.push(metric(
      "Evidence completeness", `${pct}%`,
      completeness.entries_missing_evidence > 0 ? "fail" : "pass",
      completeness.entries_missing_evidence > 0
        ? `${completeness.entries_missing_evidence} of ${completeness.total_entries} entries missing evidence`
        : `All ${completeness.total_entries} entries have evidence`
    ));
  }
  if (reconciliationStatus) {
    const exceptions = reconciliationStatus.exception_count || 0;
    pieces.push(metric(
      "Reconciliation exceptions", String(exceptions), exceptions > 0 ? "fail" : "pass",
      `${reconciliationStatus.reconciled_count || 0} reconciled · ${reconciliationStatus.outstanding_count || 0} outstanding`
    ));
  }
  if (!pieces.length) return null;
  return h("div", { className: "card", style: "margin-top:12px; display:flex; gap:28px; flex-wrap:wrap;" }, pieces);
}

function metric(label, value, tone, sub) {
  return h(
    "div",
    {},
    h("div", { style: `font-size:22px; font-weight:600; color: var(--status-${tone});` }, value),
    h("div", { className: "metric-label" }, label),
    sub ? h("div", { style: "font-size:11.5px; color: var(--ink-500); margin-top:2px;" }, sub) : null
  );
}

function approvalHistorySection(approvalEvents) {
  return h(
    "div",
    { className: "card", style: "margin-top:16px;" },
    h("h4", {}, "Approval history"),
    DataTable({
      columns: auditColumns(),
      rows: approvalEvents,
      emptyTitle: "No approval, review, or rejection events",
      emptyMessage: "Nothing on this entity's audit trail looks like an approval step yet.",
      getRowKey: (row) => row.id,
    })
  );
}

function auditHistorySection(events) {
  return h(
    "div",
    { className: "card", style: "margin-top:16px;" },
    h("h4", {}, "Full audit-event history"),
    DataTable({
      columns: auditColumns(),
      rows: events,
      emptyTitle: "No audit events recorded",
      getRowKey: (row) => row.id,
    })
  );
}

function auditColumns() {
  return [
    { key: "action", label: "Action", render: (row) => humanizeAction(row.action) },
    { key: "actor", label: "Actor" },
    { key: "timestamp", label: "When" },
    { key: "reason", label: "Reason", render: (row) => row.reason || "—" },
  ];
}

function humanizeAction(action) {
  if (!action) return "Unknown";
  return action.replace(/_/g, " ").toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());
}
