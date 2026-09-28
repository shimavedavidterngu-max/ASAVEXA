import { h, Fragment } from "../lib/vdom.js";
import { StatusBadge } from "../components/StatusBadge.js";
import { DataTable } from "../components/DataTable.js";
import { LoadingState, ErrorState, EmptyState } from "../components/DataState.js";
import { PermissionGate, allowed } from "../components/PermissionGate.js";
import { PERMISSIONS } from "../lib/permissions.js";

/**
 * Controls & Compliance / Audit Workspace (Section 9). The single most
 * important place in this pass to get maker-checker-checker-verify
 * separation visually right (Section 9's "Respect the existing
 * permission model" — control:read/control:execute, finding:manage,
 * finding:remediate, finding:verify are FIVE disjoint gates, see
 * api/routers/compliance.py's own module docstring). Every action
 * button below is wrapped in the ONE PermissionGate matching the
 * single permission the real backend endpoint requires — never a
 * broader "canManageCompliance" catch-all, because no such backend
 * permission exists and inventing one here would misrepresent the
 * real separation to the user.
 *
 * `view`: "controls" | "findings" | "finding-detail"
 */
export function Compliance({
  role, view, loading, error, onRetry, onNavigate,
  controls, onSeedStandard, defineForm, defineError, definePending, onDefineFieldChange, onSubmitDefine, onDeactivateControl,
  executions, onExecuteControl, executeParams, onExecuteParamsChange, onReviewExecution, selectedControlId, onSelectControl,
  findings, findingFilter, onFindingFilterChange,
  finding, findingError, remediation,
  reasonInputs, onReasonChange,
  onStartReview, onSendBackToOpen, onMarkRemediationRequired, onMarkResolvedWithoutRemediation, onReopenFinding, onCloseFinding,
  remediationForm, onRemediationFieldChange, onCreateRemediation, onStartRemediation, onCompleteRemediation, onVerifyRemediation, onRejectRemediation,
}) {
  if (!allowed(role, PERMISSIONS.CONTROL_READ)) {
    return h("div", { className: "empty-state card" },
      h("h3", {}, "You don't have access to this"),
      h("p", {}, "Control read access is required to view Controls & Compliance."));
  }

  if (view === "finding-detail") {
    if (loading) return LoadingState("Loading finding…");
    if (findingError) return ErrorState({ message: findingError, onRetry });
    if (!finding) return EmptyState({ title: "Finding not found" });
    return Fragment([
      breadcrumb(onNavigate, finding.id),
      findingDetail({
        role, finding, remediation, reasonInputs, onReasonChange,
        onStartReview, onSendBackToOpen, onMarkRemediationRequired, onMarkResolvedWithoutRemediation, onReopenFinding, onCloseFinding,
        remediationForm, onRemediationFieldChange, onCreateRemediation, onStartRemediation, onCompleteRemediation, onVerifyRemediation, onRejectRemediation,
      }),
    ]);
  }

  const tab = view === "findings" ? "findings" : "controls";
  return h(
    "div",
    {},
    h("h1", {}, "Controls & Compliance"),
    h("p", { style: "color: var(--ink-500); margin-top: -8px; margin-bottom: 24px;" },
      "Don't just claim compliance. Prove the control."),
    tabBar(tab, onNavigate),
    error ? ErrorState({ message: error, onRetry }) : null,
    loading ? LoadingState() : (tab === "controls"
      ? controlsView({ role, controls, onSeedStandard, defineForm, defineError, definePending, onDefineFieldChange, onSubmitDefine, onDeactivateControl, executions, onExecuteControl, executeParams, onExecuteParamsChange, onReviewExecution, selectedControlId, onSelectControl })
      : findingsView({ findings, findingFilter, onFindingFilterChange, onNavigate }))
  );
}

function breadcrumb(onNavigate, label) {
  return h("div", { className: "breadcrumbs" },
    h("a", { href: "#/compliance", onClick: (e) => { e.preventDefault(); onNavigate("/compliance"); } }, "Controls & Compliance"),
    h("span", {}, "/"), h("span", {}, label));
}

function tabBar(tab, onNavigate) {
  return h("div", { style: "display:flex; gap:8px; margin-bottom:16px;" },
    h("button", { className: `btn ${tab === "controls" ? "btn-primary" : "btn-secondary"}`, onClick: () => onNavigate("/compliance") }, "Controls & Executions"),
    h("button", { className: `btn ${tab === "findings" ? "btn-primary" : "btn-secondary"}`, onClick: () => onNavigate("/compliance/findings") }, "Findings"));
}

function controlsView({ role, controls, onSeedStandard, defineForm, defineError, definePending, onDefineFieldChange, onSubmitDefine, onDeactivateControl, executions, onExecuteControl, executeParams, onExecuteParamsChange, onReviewExecution, selectedControlId, onSelectControl }) {
  return Fragment([
    h(
      "div", { className: "card" },
      h("div", { style: "display:flex; justify-content:space-between; align-items:center;" },
        h("h2", {}, "Control library"),
        PermissionGate({ role, permission: PERMISSIONS.CONTROL_MANAGE },
          h("button", { className: "btn btn-secondary", onClick: onSeedStandard }, "Seed standard controls"))),
      DataTable({
        columns: [
          { key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "domain", label: "Domain" },
          { key: "severity", label: "Severity" }, { key: "is_active", label: "Active", render: (r) => (r.is_active ? "Yes" : "No") },
          {
            key: "actions", label: "",
            render: (r) => Fragment([
              PermissionGate({ role, permission: PERMISSIONS.CONTROL_EXECUTE },
                h("button", { className: "btn btn-secondary", onClick: () => onSelectControl(r.id) }, "Execute")),
              r.is_active ? PermissionGate({ role, permission: PERMISSIONS.CONTROL_MANAGE },
                h("button", { className: "btn btn-danger", style: "margin-left:4px;", onClick: () => onDeactivateControl(r.id) }, "Deactivate")) : null,
            ]),
          },
        ],
        rows: controls || [], emptyTitle: "No controls defined yet", emptyMessage: "Seed the standard library above, or define one.",
      }),
      PermissionGate({ role, permission: PERMISSIONS.CONTROL_MANAGE }, defineControlForm({ defineForm, defineError, definePending, onDefineFieldChange, onSubmitDefine }))
    ),
    selectedControlId
      ? h("div", { className: "card" }, h("h3", {}, "Execute control"),
          h("div", { style: "display:flex; gap:8px; align-items:center;" },
            h("input", { placeholder: "Period id (optional)", value: executeParams || "", onInput: (e) => onExecuteParamsChange(e.target.value) }),
            h("button", { className: "btn btn-primary", onClick: () => onExecuteControl(selectedControlId) }, "Run")))
      : null,
    h(
      "div", { className: "card" }, h("h3", {}, "Recent executions"),
      DataTable({
        columns: [
          { key: "control_id", label: "Control" },
          { key: "result", label: "Result", render: (r) => StatusBadge({ status: r.result }) },
          { key: "explanation", label: "Explanation" },
          { key: "reviewed_by", label: "Reviewed by", render: (r) => r.reviewed_by || "—" },
          {
            key: "actions", label: "",
            render: (r) => (!r.reviewed_by ? PermissionGate({ role, permission: PERMISSIONS.CONTROL_EXECUTE },
              h("button", { className: "btn btn-secondary", onClick: () => onReviewExecution(r.id) }, "Mark reviewed")) : null),
          },
        ],
        rows: executions || [], emptyTitle: "No executions yet",
      })
    ),
  ]);
}

function defineControlForm({ defineForm, defineError, definePending, onDefineFieldChange, onSubmitDefine }) {
  const f = defineForm || {};
  return h(
    "form",
    { style: "margin-top:16px; border-top:1px solid var(--line); padding-top:16px;", onSubmit: (e) => { e.preventDefault(); onSubmitDefine(); } },
    h("h3", {}, "Define a new control"),
    defineError ? h("div", { className: "alert alert-error" }, defineError) : null,
    h("div", { style: "display:flex; gap:12px; flex-wrap:wrap;" },
      h("div", { className: "field" }, h("label", {}, "Code"), h("input", { value: f.code || "", required: true, onInput: (e) => onDefineFieldChange("code", e.target.value) })),
      h("div", { className: "field" }, h("label", {}, "Name"), h("input", { value: f.name || "", required: true, onInput: (e) => onDefineFieldChange("name", e.target.value) })),
      h("div", { className: "field" }, h("label", {}, "Domain"),
        h("select", { value: f.domain || "ACCOUNTING", onChange: (e) => onDefineFieldChange("domain", e.target.value) },
          ["ACCOUNTING", "RECONCILIATION", "EVIDENCE", "REPORTING", "PERIOD_CLOSE"].map((d) => h("option", { value: d }, d)))),
      h("div", { className: "field" }, h("label", {}, "Severity"),
        h("select", { value: f.severity || "MEDIUM", onChange: (e) => onDefineFieldChange("severity", e.target.value) },
          ["LOW", "MEDIUM", "HIGH", "CRITICAL"].map((s) => h("option", { value: s }, s)))),
      h("div", { className: "field" }, h("label", {}, "Check key"), h("input", { value: f.check_key || "", required: true, onInput: (e) => onDefineFieldChange("check_key", e.target.value) }))
    ),
    h("div", { className: "field" }, h("label", {}, "Description"), h("textarea", { value: f.description || "", onInput: (e) => onDefineFieldChange("description", e.target.value) })),
    h("div", { className: "field" }, h("label", {}, "Objective"), h("textarea", { value: f.objective || "", onInput: (e) => onDefineFieldChange("objective", e.target.value) })),
    h("button", { type: "submit", className: "btn btn-primary", disabled: definePending }, definePending ? "Defining…" : "Define control")
  );
}

function findingsView({ findings, findingFilter, onFindingFilterChange, onNavigate }) {
  const statuses = ["", "OPEN", "UNDER_REVIEW", "REMEDIATION_REQUIRED", "RESOLVED", "VERIFIED", "CLOSED"];
  return h(
    "div", { className: "card" },
    h("div", { style: "display:flex; justify-content:space-between; align-items:center;" },
      h("h2", {}, "Findings"),
      h("select", { value: findingFilter || "", onChange: (e) => onFindingFilterChange(e.target.value) },
        statuses.map((s) => h("option", { value: s }, s || "All statuses")))),
    DataTable({
      columns: [
        { key: "description", label: "Description" },
        { key: "severity", label: "Severity" },
        { key: "status", label: "Status", render: (r) => StatusBadge({ status: r.status }) },
        { key: "created_at", label: "Created" },
      ],
      rows: findings || [], emptyTitle: "No findings recorded",
      onRowClick: (r) => onNavigate(`/compliance/findings/${r.id}`),
    })
  );
}

function findingDetail({
  role, finding, remediation, reasonInputs, onReasonChange,
  onStartReview, onSendBackToOpen, onMarkRemediationRequired, onMarkResolvedWithoutRemediation, onReopenFinding, onCloseFinding,
  remediationForm, onRemediationFieldChange, onCreateRemediation, onStartRemediation, onCompleteRemediation, onVerifyRemediation, onRejectRemediation,
}) {
  const reason = (field) => (reasonInputs && reasonInputs[field]) || "";
  return h(
    "div",
    {},
    h(
      "div", { className: "card" },
      h("div", { style: "display:flex; justify-content:space-between; align-items:flex-start;" },
        h("div", {}, h("h2", {}, finding.description), h("div", { className: "mono", style: "font-size:12.5px; color: var(--ink-500);" }, finding.id)),
        StatusBadge({ status: finding.status })),
      h("div", { style: "margin-top:8px; color: var(--ink-500); font-size:13px;" }, `Severity: ${finding.severity}  ·  Created by ${finding.created_by}`),
      // finding:manage triage actions — never combined with finding:remediate/verify (Section 9)
      h(
        "div", { style: "margin-top:12px; display:flex; gap:8px; flex-wrap:wrap; align-items:center;" },
        finding.status === "OPEN" ? PermissionGate({ role, permission: PERMISSIONS.FINDING_MANAGE },
          h("button", { className: "btn btn-primary", onClick: () => onStartReview(finding.id) }, "Start review")) : null,
        finding.status === "UNDER_REVIEW" ? PermissionGate({ role, permission: PERMISSIONS.FINDING_MANAGE },
          Fragment([
            h("input", { placeholder: "Reason", value: reason("sendBack"), onInput: (e) => onReasonChange("sendBack", e.target.value) }),
            h("button", { className: "btn btn-secondary", disabled: !reason("sendBack"), onClick: () => onSendBackToOpen(finding.id) }, "Send back to open"),
          ])) : null,
        finding.status === "UNDER_REVIEW" ? PermissionGate({ role, permission: PERMISSIONS.FINDING_MANAGE },
          h("button", { className: "btn btn-secondary", onClick: () => onMarkRemediationRequired(finding.id) }, "Mark remediation required")) : null,
        finding.status === "UNDER_REVIEW" ? PermissionGate({ role, permission: PERMISSIONS.FINDING_MANAGE },
          Fragment([
            h("input", { placeholder: "Reason (required)", value: reason("resolveNoRemediation"), onInput: (e) => onReasonChange("resolveNoRemediation", e.target.value) }),
            h("button", { className: "btn btn-secondary", disabled: !reason("resolveNoRemediation"), onClick: () => onMarkResolvedWithoutRemediation(finding.id) }, "Resolve without remediation"),
          ])) : null,
        finding.status === "CLOSED" ? PermissionGate({ role, permission: PERMISSIONS.FINDING_MANAGE },
          Fragment([
            h("input", { placeholder: "Reason (required)", value: reason("reopen"), onInput: (e) => onReasonChange("reopen", e.target.value) }),
            h("button", { className: "btn btn-secondary", disabled: !reason("reopen"), onClick: () => onReopenFinding(finding.id) }, "Reopen"),
          ])) : null,
        finding.status === "VERIFIED" ? PermissionGate({ role, permission: PERMISSIONS.FINDING_VERIFY },
          h("button", { className: "btn btn-primary", onClick: () => onCloseFinding(finding.id) }, "Close finding")) : null
      )
    ),
    (finding.status === "REMEDIATION_REQUIRED" || remediation)
      ? remediationCard({ role, finding, remediation, remediationForm, onRemediationFieldChange, onCreateRemediation, onStartRemediation, onCompleteRemediation, onVerifyRemediation, onRejectRemediation, reason, onReasonChange })
      : null
  );
}

function remediationCard({ role, finding, remediation, remediationForm, onRemediationFieldChange, onCreateRemediation, onStartRemediation, onCompleteRemediation, onVerifyRemediation, onRejectRemediation, reason, onReasonChange }) {
  if (!remediation) {
    const f = remediationForm || {};
    return h(
      "div", { className: "card" }, h("h3", {}, "Remediation"),
      PermissionGate({ role, permission: PERMISSIONS.FINDING_REMEDIATE },
        h(
          "form", { onSubmit: (e) => { e.preventDefault(); onCreateRemediation(finding.id); } },
          h("div", { style: "display:flex; gap:12px; flex-wrap:wrap;" },
            h("div", { className: "field" }, h("label", {}, "Action"), h("input", { value: f.action || "", required: true, onInput: (e) => onRemediationFieldChange("action", e.target.value) })),
            h("div", { className: "field" }, h("label", {}, "Owner"), h("input", { value: f.owner || "", required: true, onInput: (e) => onRemediationFieldChange("owner", e.target.value) })),
            h("div", { className: "field" }, h("label", {}, "Due date"), h("input", { type: "date", value: f.due_date || "", onInput: (e) => onRemediationFieldChange("due_date", e.target.value) }))
          ),
          h("button", { type: "submit", className: "btn btn-primary" }, "Create remediation")
        ))
    );
  }
  return h(
    "div", { className: "card" },
    h("div", { style: "display:flex; justify-content:space-between; align-items:center;" }, h("h3", {}, "Remediation"), StatusBadge({ status: remediation.status })),
    h("div", { style: "margin-top:4px;" }, remediation.action, " · ", h("span", { style: "color: var(--ink-500);" }, `owner: ${remediation.owner}`)),
    h(
      "div", { style: "margin-top:12px; display:flex; gap:8px; flex-wrap:wrap; align-items:center;" },
      remediation.status === "PLANNED" ? PermissionGate({ role, permission: PERMISSIONS.FINDING_REMEDIATE },
        h("button", { className: "btn btn-primary", onClick: () => onStartRemediation(remediation.id) }, "Start")) : null,
      remediation.status === "IN_PROGRESS" ? PermissionGate({ role, permission: PERMISSIONS.FINDING_REMEDIATE },
        h("button", { className: "btn btn-primary", onClick: () => onCompleteRemediation(remediation.id) }, "Mark complete")) : null,
      // finding:verify — deliberately never gated by finding:remediate too (Section 9's disjointness proof)
      remediation.status === "COMPLETED" ? PermissionGate({ role, permission: PERMISSIONS.FINDING_VERIFY },
        Fragment([
          h("button", { className: "btn btn-primary", onClick: () => onVerifyRemediation(remediation.id) }, "Verify"),
          h("input", { placeholder: "Reject reason", value: reason("rejectRemediation"), onInput: (e) => onReasonChange("rejectRemediation", e.target.value) }),
          h("button", { className: "btn btn-danger", disabled: !reason("rejectRemediation"), onClick: () => onRejectRemediation(remediation.id) }, "Reject"),
        ])) : null,
      remediation.status === "VERIFIED" ? h("div", { className: "alert alert-info" }, `Verified by ${remediation.verified_by}`) : null
    )
  );
}
