import { h, Fragment } from "../lib/vdom.js";
import { StatusBadge } from "../components/StatusBadge.js";
import { DataTable } from "../components/DataTable.js";
import { LoadingState, ErrorState, EmptyState } from "../components/DataState.js";
import { PermissionGate, allowed } from "../components/PermissionGate.js";
import { PERMISSIONS } from "../lib/permissions.js";

/**
 * Period Close & Financial Controls (Section 8). Never bypasses a
 * period-lock rule client-side — every action here (request/recheck/
 * review/approve/reject) simply calls the corresponding backend
 * endpoint and renders whatever it returns, including a
 * CONTROLS_FAILED status the backend re-verified at approval time
 * (Section 8: "The UI must clearly communicate why an action is
 * unavailable" — the readiness report's own `findings` list, each with
 * a real `message`, is shown verbatim rather than a generic "blocked").
 */
export function PeriodClose({
  role, periods, selectedPeriodId, onSelectPeriod,
  loading, error, readiness, activeProcess, processes,
  onCheckReadiness, onRequestClose, onRecheck, onReview, onApprove, onReject,
  approveReason, onApproveReasonChange, rejectReason, onRejectReasonChange,
  onRetry,
}) {
  if (!allowed(role, PERMISSIONS.PERIOD_CLOSE_READ)) {
    return h("div", { className: "empty-state card" },
      h("h3", {}, "You don't have access to this"),
      h("p", {}, "Period close read access is required to view this area."));
  }

  return h(
    "div",
    {},
    h("h1", {}, "Period Close & Financial Controls"),
    h("p", { style: "color: var(--ink-500); margin-top: -8px; margin-bottom: 24px;" },
      "Don't just close the period. Prove that it was properly closed."),
    h(
      "div",
      { className: "card" },
      h("div", { style: "display:flex; gap:12px; align-items:flex-end; flex-wrap:wrap;" },
        h("div", { className: "field" }, h("label", {}, "Period"),
          h("select", { value: selectedPeriodId || "", onChange: (e) => onSelectPeriod(e.target.value) },
            h("option", { value: "" }, "Select period…"),
            (periods || []).map((p) => h("option", { value: p.id }, `${p.name} (${p.status})`)))),
        h("button", { className: "btn btn-secondary", disabled: !selectedPeriodId, onClick: onCheckReadiness }, "Check readiness"),
        PermissionGate({ role, permission: PERMISSIONS.PERIOD_CLOSE_REQUEST },
          h("button", { className: "btn btn-primary", disabled: !selectedPeriodId, onClick: onRequestClose }, "Request close"))
      )
    ),
    error ? ErrorState({ message: error, onRetry }) : null,
    !selectedPeriodId
      ? EmptyState({ title: "No period selected", message: "Select an accounting period above to see its close readiness and history." })
      : (loading ? LoadingState() : Fragment([
          readiness ? readinessCard(readiness) : null,
          activeProcess ? processCard({ role, process: activeProcess, onRecheck, onReview, onApprove, onReject, approveReason, onApproveReasonChange, rejectReason, onRejectReasonChange }) : null,
          historySection(processes),
        ]))
  );
}

function readinessCard(r) {
  return h(
    "div",
    { className: "card" },
    h("div", { style: "display:flex; justify-content:space-between; align-items:center;" },
      h("h3", {}, "Close readiness"),
      h("span", { className: `badge badge-${r.is_ready ? "pass" : "fail"}` }, r.is_ready ? "Ready" : "Not ready")),
    DataTable({
      columns: [
        { key: "control", label: "Control" },
        { key: "status", label: "Status", render: (row) => StatusBadge({ status: row.status }) },
        { key: "blocking", label: "Blocking", render: (row) => (row.blocking ? "Yes" : "No") },
        { key: "message", label: "Message" },
      ],
      rows: r.findings || [],
      emptyTitle: "No control findings",
    })
  );
}

function processCard({ role, process, onRecheck, onReview, onApprove, onReject, approveReason, onApproveReasonChange, rejectReason, onRejectReasonChange }) {
  return h(
    "div",
    { className: "card" },
    h("div", { style: "display:flex; justify-content:space-between; align-items:center;" },
      h("h3", {}, "Active close process"), StatusBadge({ status: process.status })),
    h("div", { style: "color: var(--ink-500); font-size:12.5px;" }, `Requested by ${process.requested_by} at ${process.requested_at}`),
    process.status === "CONTROLS_FAILED"
      ? h("div", { className: "alert alert-warn", style: "margin-top:8px;" },
          "Blocked by the readiness report above. Resolve the blocking controls, then recheck.")
      : null,
    h(
      "div",
      { style: "margin-top:12px; display:flex; gap:8px; flex-wrap:wrap; align-items:center;" },
      (process.status === "CONTROLS_FAILED" || process.status === "REQUESTED")
        ? PermissionGate({ role, permission: PERMISSIONS.PERIOD_CLOSE_REQUEST },
            h("button", { className: "btn btn-secondary", onClick: () => onRecheck(process.id) }, "Recheck controls"))
        : null,
      process.status === "READY_FOR_CLOSE"
        ? PermissionGate({ role, permission: PERMISSIONS.PERIOD_CLOSE_REVIEW },
            h("button", { className: "btn btn-secondary", onClick: () => onReview(process.id) }, "Mark reviewed"))
        : null,
      process.status === "READY_FOR_CLOSE" && process.reviewed_by
        ? PermissionGate({ role, permission: PERMISSIONS.PERIOD_CLOSE_APPROVE },
            Fragment([
              h("input", { placeholder: "Approval note (optional)", value: approveReason || "", onInput: (e) => onApproveReasonChange(e.target.value) }),
              h("button", { className: "btn btn-primary", onClick: () => onApprove(process.id) }, "Approve close"),
            ]))
        : null,
      (process.status === "REQUESTED" || process.status === "READY_FOR_CLOSE" || process.status === "CONTROLS_FAILED")
        ? PermissionGate({ role, permission: PERMISSIONS.PERIOD_CLOSE_APPROVE },
            Fragment([
              h("input", { placeholder: "Reason to reject", value: rejectReason || "", onInput: (e) => onRejectReasonChange(e.target.value) }),
              h("button", { className: "btn btn-danger", disabled: !rejectReason, onClick: () => onReject(process.id) }, "Reject"),
            ]))
        : null
    ),
    process.status === "CLOSED" ? h("div", { className: "alert alert-info", style: "margin-top:12px;" }, "This period is now locked. No further postings are permitted.") : null
  );
}

function historySection(processes) {
  return h(
    "div",
    { className: "card" },
    h("h3", {}, "Close history"),
    DataTable({
      columns: [
        { key: "status", label: "Status", render: (r) => StatusBadge({ status: r.status }) },
        { key: "requested_by", label: "Requested by" },
        { key: "requested_at", label: "Requested at" },
        { key: "approved_by", label: "Approved by", render: (r) => r.approved_by || "—" },
      ],
      rows: processes || [],
      emptyTitle: "No close processes recorded for this period yet",
    })
  );
}
