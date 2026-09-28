import { h, Fragment } from "../lib/vdom.js";
import { StatusBadge } from "../components/StatusBadge.js";
import { DataTable } from "../components/DataTable.js";
import { LoadingState, ErrorState, EmptyState } from "../components/DataState.js";
import { PermissionGate, allowed } from "../components/PermissionGate.js";
import { PERMISSIONS } from "../lib/permissions.js";
import { formatMoney } from "./Dashboard.js";

/**
 * Reconciliation (Section 6). Pure render function. Deterministic
 * matching itself (Section 6: "Do not introduce business rules that do
 * not exist in the domain layer") happens entirely server-side — this
 * page only ever displays a transaction's already-decided status
 * (IMPORTED/MATCHED/REVIEW_REQUIRED/UNMATCHED/APPROVED/RECONCILED/
 * REJECTED, per reconciliation/domain/enums.py) and offers the actions
 * the backend's own state machine allows from that status; it never
 * infers or computes a match itself.
 *
 * `view`: "list" | "new" | "detail"
 */
export function Reconciliation({
  role, view, loading, error,
  reconciliations, detail, transactions, detailError,
  form, formError, formPending, onFieldChange, onSubmitCreate,
  onNavigate, onRetry,
  onSubmitReconciliation, onApproveReconciliation, onRejectReconciliation, rejectReason, onRejectReasonChange,
  onManualMatch, matchJournalId, onMatchJournalIdChange,
  onApproveTransaction, onRejectMatch, matchRejectReason, onMatchRejectReasonChange,
}) {
  if (!allowed(role, PERMISSIONS.RECONCILIATION_READ)) {
    return h("div", { className: "empty-state card" },
      h("h3", {}, "You don't have access to this"),
      h("p", {}, "Reconciliation read access is required to view this area."));
  }

  if (view === "new") {
    return Fragment([
      breadcrumb(onNavigate, "New reconciliation"),
      createForm({ form, formError, formPending, onFieldChange, onSubmitCreate }),
    ]);
  }

  if (view === "detail") {
    if (loading) return LoadingState("Loading reconciliation…");
    if (detailError) return ErrorState({ message: detailError, onRetry });
    if (!detail) return EmptyState({ title: "Reconciliation not found" });
    return Fragment([
      breadcrumb(onNavigate, detail.name),
      reconciliationDetail({
        role, detail, transactions,
        onSubmitReconciliation, onApproveReconciliation, onRejectReconciliation, rejectReason, onRejectReasonChange,
        onManualMatch, matchJournalId, onMatchJournalIdChange,
        onApproveTransaction, onRejectMatch, matchRejectReason, onMatchRejectReasonChange,
      }),
    ]);
  }

  return h(
    "div",
    {},
    h("h1", {}, "Reconciliation"),
    h("p", { style: "color: var(--ink-500); margin-top: -8px; margin-bottom: 24px;" },
      "Bank statement lines matched, one by one, to the ledger — every match explainable, every exception visible until resolved."),
    error ? ErrorState({ message: error, onRetry }) : null,
    h(
      "div",
      { className: "card" },
      h("div", { style: "display:flex; justify-content:space-between; align-items:center;" },
        h("h2", {}, "Reconciliations"),
        PermissionGate({ role, permission: PERMISSIONS.RECONCILIATION_CREATE },
          h("button", { className: "btn btn-primary", onClick: () => onNavigate("/reconciliation/new") }, "New reconciliation"))
      ),
      loading ? LoadingState() : DataTable({
        columns: [
          { key: "name", label: "Name" },
          { key: "bank_account_id", label: "Bank account" },
          { key: "period_start", label: "From" },
          { key: "period_end", label: "To" },
          { key: "status", label: "Status", render: (r) => StatusBadge({ status: r.status }) },
        ],
        rows: reconciliations || [],
        emptyTitle: "No reconciliations yet",
        emptyMessage: "Start one above.",
        onRowClick: (r) => onNavigate(`/reconciliation/${r.id}`),
      })
    )
  );
}

function breadcrumb(onNavigate, label) {
  return h("div", { className: "breadcrumbs" },
    h("a", { href: "#/reconciliation", onClick: (e) => { e.preventDefault(); onNavigate("/reconciliation"); } }, "Reconciliation"),
    h("span", {}, "/"), h("span", {}, label));
}

function createForm({ form, formError, formPending, onFieldChange, onSubmitCreate }) {
  const f = form || {};
  return h(
    "div",
    { className: "card" },
    h("h2", {}, "New reconciliation"),
    formError ? h("div", { className: "alert alert-error" }, formError) : null,
    h(
      "form",
      { onSubmit: (e) => { e.preventDefault(); onSubmitCreate(); } },
      h("div", { style: "display:flex; gap:12px; flex-wrap:wrap;" },
        h("div", { className: "field" }, h("label", {}, "Bank account id"),
          h("input", { value: f.bank_account_id || "", required: true, onInput: (e) => onFieldChange("bank_account_id", e.target.value) })),
        h("div", { className: "field" }, h("label", {}, "Name"),
          h("input", { value: f.name || "", required: true, onInput: (e) => onFieldChange("name", e.target.value) })),
        h("div", { className: "field" }, h("label", {}, "Period start"),
          h("input", { type: "date", value: f.period_start || "", required: true, onInput: (e) => onFieldChange("period_start", e.target.value) })),
        h("div", { className: "field" }, h("label", {}, "Period end"),
          h("input", { type: "date", value: f.period_end || "", required: true, onInput: (e) => onFieldChange("period_end", e.target.value) }))
      ),
      h("button", { type: "submit", className: "btn btn-primary", disabled: formPending }, formPending ? "Creating…" : "Create reconciliation")
    )
  );
}

function reconciliationDetail({
  role, detail, transactions,
  onSubmitReconciliation, onApproveReconciliation, onRejectReconciliation, rejectReason, onRejectReasonChange,
  onManualMatch, matchJournalId, onMatchJournalIdChange,
  onApproveTransaction, onRejectMatch, matchRejectReason, onMatchRejectReasonChange,
}) {
  const isDraft = detail.status === "DRAFT";
  const isSubmitted = detail.status === "SUBMITTED";
  const summary = (transactions || []).reduce((acc, t) => ({ ...acc, [t.status]: (acc[t.status] || 0) + 1 }), {});
  return h(
    "div",
    {},
    h(
      "div",
      { className: "card" },
      h("div", { style: "display:flex; justify-content:space-between; align-items:flex-start;" },
        h("div", {}, h("h2", {}, detail.name), h("div", { style: "color: var(--ink-500); font-size:12.5px;" }, detail.bank_account_id)),
        StatusBadge({ status: detail.status })
      ),
      h("div", { style: "display:flex; gap:12px; margin-top:8px; flex-wrap:wrap;" },
        countPill("Matched", summary.MATCHED || 0, "info"),
        countPill("Review required", summary.REVIEW_REQUIRED || 0, "warn"),
        countPill("Unmatched", summary.UNMATCHED || 0, "fail"),
        countPill("Approved", summary.APPROVED || 0, "pass")
      ),
      isDraft ? PermissionGate({ role, permission: PERMISSIONS.RECONCILIATION_CREATE },
        h("button", { className: "btn btn-primary", style: "margin-top:12px;", onClick: () => onSubmitReconciliation(detail.id) }, "Submit for review")) : null,
      isSubmitted ? PermissionGate({ role, permission: PERMISSIONS.RECONCILIATION_APPROVE },
        h(
          "div",
          { style: "margin-top:12px; display:flex; gap:8px; align-items:center; flex-wrap:wrap;" },
          h("button", { className: "btn btn-primary", onClick: () => onApproveReconciliation(detail.id) }, "Approve"),
          h("input", { placeholder: "Reason to reject", value: rejectReason || "", onInput: (e) => onRejectReasonChange(e.target.value) }),
          h("button", { className: "btn btn-danger", disabled: !rejectReason, onClick: () => onRejectReconciliation(detail.id) }, "Reject")
        )) : null,
      detail.status === "REJECTED" && detail.rejection_reason
        ? h("div", { className: "alert alert-error", style: "margin-top:12px;" }, detail.rejection_reason)
        : null
    ),
    h(
      "div",
      { className: "card" },
      h("h3", {}, "Transactions"),
      DataTable({
        columns: [
          { key: "transaction_date", label: "Date" },
          { key: "description", label: "Description" },
          { key: "debit_amount", label: "Debit", align: "right", render: (r) => (Number(r.debit_amount) > 0 ? formatMoney(r.debit_amount) : "") },
          { key: "credit_amount", label: "Credit", align: "right", render: (r) => (Number(r.credit_amount) > 0 ? formatMoney(r.credit_amount) : "") },
          { key: "status", label: "Status", render: (r) => StatusBadge({ status: r.status }) },
          { key: "matched_journal_id", label: "Matched journal", render: (r) => r.matched_journal_id || "—" },
          {
            key: "actions", label: "",
            render: (r) => transactionActions({ role, r, onManualMatch, matchJournalId, onMatchJournalIdChange, onApproveTransaction, onRejectMatch, matchRejectReason, onMatchRejectReasonChange }),
          },
        ],
        rows: transactions || [],
        emptyTitle: "No transactions imported yet",
      })
    )
  );
}

function transactionActions({ role, r, onManualMatch, matchJournalId, onMatchJournalIdChange, onApproveTransaction, onRejectMatch, matchRejectReason, onMatchRejectReasonChange }) {
  if (r.status === "UNMATCHED" || r.status === "REVIEW_REQUIRED") {
    return PermissionGate({ role, permission: PERMISSIONS.RECONCILIATION_MATCH },
      h("div", { style: "display:flex; gap:4px;" },
        h("input", { placeholder: "Journal id", style: "width:110px;", value: (matchJournalId && matchJournalId[r.id]) || "", onInput: (e) => onMatchJournalIdChange(r.id, e.target.value) }),
        h("button", { className: "btn btn-secondary", onClick: () => onManualMatch(r.id) }, "Match")));
  }
  if (r.status === "MATCHED") {
    return PermissionGate({ role, permission: PERMISSIONS.RECONCILIATION_APPROVE },
      h("div", { style: "display:flex; gap:4px;" },
        h("button", { className: "btn btn-primary", onClick: () => onApproveTransaction(r.id) }, "Approve"),
        h("input", { placeholder: "Reject reason", style: "width:100px;", value: (matchRejectReason && matchRejectReason[r.id]) || "", onInput: (e) => onMatchRejectReasonChange(r.id, e.target.value) }),
        h("button", { className: "btn btn-danger", disabled: !(matchRejectReason && matchRejectReason[r.id]), onClick: () => onRejectMatch(r.id) }, "Reject")));
  }
  return null;
}

function countPill(label, value, tone) {
  return h("div", {}, h("div", { className: `badge badge-${tone}` }, String(value)), h("div", { style: "font-size:11px; color: var(--ink-500); margin-top:2px;" }, label));
}
