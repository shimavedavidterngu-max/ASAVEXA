import { h, Fragment } from "../lib/vdom.js";
import { StatusBadge } from "../components/StatusBadge.js";
import { DataTable } from "../components/DataTable.js";
import { LoadingState, ErrorState, EmptyState } from "../components/DataState.js";
import { PermissionGate, allowed } from "../components/PermissionGate.js";
import { PERMISSIONS } from "../lib/permissions.js";

/**
 * Evidence Vault (Section 5). Pure render function — the container
 * does every real fetch/upload; this file never reads a file's bytes
 * itself and never computes a hash (Section 5: "Do not fake
 * cryptographic hashes" — `file_hash` shown here is always exactly
 * what EvidenceOut.file_hash returned from the backend, or nothing).
 *
 * `view`: "list" | "detail"
 * A real <input type="file"> is used for upload — the container reads
 * `event.target.files[0]` and passes it straight to
 * ApiClient.uploadEvidence, so the actual bytes never pass through
 * this render function or any intermediate state at all.
 */
export function Evidence({
  role, view, loading, error, items, detail, detailError,
  filterStatus, filterType, onFilterChange,
  uploadForm, uploadError, uploadPending,
  onNavigate, onRetry, onUploadFieldChange, onFileSelected, onSubmitUpload,
  onVerify, onReject, rejectReason, onRejectReasonChange,
}) {
  if (!allowed(role, PERMISSIONS.EVIDENCE_READ)) {
    return h("div", { className: "empty-state card" },
      h("h3", {}, "You don't have access to this"),
      h("p", {}, "Evidence read access is required to view the Evidence Vault."));
  }

  if (view === "detail") {
    if (loading) return LoadingState("Loading evidence…");
    if (detailError) return ErrorState({ message: detailError, onRetry });
    if (!detail) return EmptyState({ title: "Evidence record not found" });
    return Fragment([
      h("div", { className: "breadcrumbs" },
        h("a", { href: "#/evidence", onClick: (e) => { e.preventDefault(); onNavigate("/evidence"); } }, "Evidence"),
        h("span", {}, "/"), h("span", {}, detail.original_filename || detail.id)),
      evidenceDetail({ role, detail, onVerify, onReject, rejectReason, onRejectReasonChange }),
    ]);
  }

  return h(
    "div",
    {},
    h("h1", {}, "Evidence Vault"),
    h("p", { style: "color: var(--ink-500); margin-top: -8px; margin-bottom: 24px;" },
      "Every financial claim in ASAVEXA should be traceable to a piece of supporting evidence. Nothing here is fabricated: a missing hash or status is shown as missing, never guessed."),
    error ? ErrorState({ message: error, onRetry }) : null,
    PermissionGate({ role, permission: PERMISSIONS.EVIDENCE_UPLOAD },
      uploadCard({ uploadForm, uploadError, uploadPending, onUploadFieldChange, onFileSelected, onSubmitUpload })),
    h(
      "div",
      { className: "card" },
      h("div", { style: "display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap;" },
        h("h2", {}, "All evidence"),
        filterBar({ filterStatus, filterType, onFilterChange })
      ),
      loading ? LoadingState() : evidenceTable({ items, onNavigate })
    )
  );
}

function filterBar({ filterStatus, filterType, onFilterChange }) {
  const statuses = ["", "UPLOADED", "VERIFIED", "INCOMPLETE", "DUPLICATE", "CONFLICTING", "EXPIRED", "REJECTED"];
  const types = ["", "INVOICE", "RECEIPT", "CONTRACT", "BANK_STATEMENT", "PURCHASE_ORDER", "DELIVERY_NOTE", "PAYROLL_EVIDENCE", "TAX_DOCUMENT", "APPROVAL_RECORD", "OTHER"];
  return h(
    "div",
    { style: "display:flex; gap:8px;" },
    h("select", { value: filterStatus || "", onChange: (e) => onFilterChange("status", e.target.value) },
      statuses.map((s) => h("option", { value: s }, s || "All statuses"))),
    h("select", { value: filterType || "", onChange: (e) => onFilterChange("type", e.target.value) },
      types.map((t) => h("option", { value: t }, t || "All types")))
  );
}

function evidenceTable({ items, onNavigate }) {
  const filtered = items || [];
  return DataTable({
    columns: [
      { key: "original_filename", label: "File" },
      { key: "type", label: "Type" },
      { key: "status", label: "Status", render: (r) => StatusBadge({ status: r.status }) },
      { key: "file_hash", label: "Hash", render: (r) => h("span", { className: "mono", style: "font-size:11px;" }, (r.file_hash || "").slice(0, 12) + "…") },
      { key: "uploaded_by", label: "Uploaded by" },
      { key: "linked_journal_id", label: "Linked to", render: (r) => r.linked_journal_id || r.linked_transaction_ref || "—" },
    ],
    rows: filtered,
    emptyTitle: "No evidence records",
    emptyMessage: "Upload the first supporting document above.",
    onRowClick: (r) => onNavigate(`/evidence/${r.id}`),
  });
}

function uploadCard({ uploadForm, uploadError, uploadPending, onUploadFieldChange, onFileSelected, onSubmitUpload }) {
  const f = uploadForm || {};
  return h(
    "div",
    { className: "card" },
    h("h2", {}, "Upload evidence"),
    uploadError ? h("div", { className: "alert alert-error" }, uploadError) : null,
    h(
      "form",
      { onSubmit: (e) => { e.preventDefault(); onSubmitUpload(); } },
      h("div", { style: "display:flex; gap:12px; flex-wrap:wrap;" },
        h("div", { className: "field" }, h("label", {}, "File"),
          h("input", { type: "file", required: true, onChange: (e) => onFileSelected(e.target.files && e.target.files[0]) })),
        h("div", { className: "field" }, h("label", {}, "Type"),
          h("select", { value: f.type || "INVOICE", onChange: (e) => onUploadFieldChange("type", e.target.value) },
            ["INVOICE", "RECEIPT", "CONTRACT", "BANK_STATEMENT", "PURCHASE_ORDER", "DELIVERY_NOTE", "PAYROLL_EVIDENCE", "TAX_DOCUMENT", "APPROVAL_RECORD", "OTHER"].map((t) => h("option", { value: t }, t)))),
        h("div", { className: "field" }, h("label", {}, "Linked journal id (optional)"),
          h("input", { value: f.linkedJournalId || "", onInput: (e) => onUploadFieldChange("linkedJournalId", e.target.value) })),
        h("div", { className: "field" }, h("label", {}, "Linked transaction ref (optional)"),
          h("input", { value: f.linkedTransactionRef || "", onInput: (e) => onUploadFieldChange("linkedTransactionRef", e.target.value) }))
      ),
      h("button", { type: "submit", className: "btn btn-primary", disabled: uploadPending }, uploadPending ? "Uploading…" : "Upload")
    )
  );
}

function evidenceDetail({ role, detail, onVerify, onReject, rejectReason, onRejectReasonChange }) {
  const canDecide = detail.status === "UPLOADED" || detail.status === "INCOMPLETE" || detail.status === "DUPLICATE" || detail.status === "CONFLICTING";
  return h(
    "div",
    {},
    h(
      "div",
      { className: "card" },
      h("div", { style: "display:flex; justify-content:space-between; align-items:flex-start;" },
        h("div", {},
          h("h2", {}, detail.original_filename),
          h("div", { className: "mono", style: "font-size:12.5px; color: var(--ink-500);" }, detail.id)),
        StatusBadge({ status: detail.status })
      ),
      h("div", { style: "margin-top:12px; font-size:13.5px;" },
        detailRow("Type", detail.type),
        detailRow("Content type", detail.content_type),
        detailRow("Size", `${detail.size_bytes} bytes`),
        detailRow("Hash (SHA-256)", detail.file_hash ? h("span", { className: "mono" }, detail.file_hash) : "—"),
        detailRow("Uploaded by", `${detail.uploaded_by} · ${detail.uploaded_at}`),
        detail.linked_journal_id ? detailRow("Linked journal", h("a", { href: `#/accounting/journals/${detail.linked_journal_id}` }, detail.linked_journal_id)) : null,
        detail.linked_transaction_ref ? detailRow("Linked transaction ref", detail.linked_transaction_ref) : null,
        detail.verified_by ? detailRow("Verified by", `${detail.verified_by} · ${detail.verified_at || ""}`) : null,
        detail.rejection_reason ? detailRow("Rejection reason", detail.rejection_reason) : null
      ),
      canDecide
        ? PermissionGate({ role, permission: PERMISSIONS.EVIDENCE_VERIFY },
            h(
              "div",
              { style: "margin-top:16px; border-top:1px solid var(--line); padding-top:16px;" },
              h("button", { className: "btn btn-primary", onClick: () => onVerify(detail.id) }, "Verify"),
              h("span", { style: "display:inline-block; width:12px;" }),
              h("input", { placeholder: "Reason to reject", value: rejectReason || "", onInput: (e) => onRejectReasonChange(e.target.value), style: "width:220px; margin-right:8px;" }),
              h("button", { className: "btn btn-danger", disabled: !rejectReason, onClick: () => onReject(detail.id) }, "Reject")
            ))
        : null
    )
  );
}

function detailRow(label, value) {
  if (value === null || value === undefined || value === "") return null;
  return h("div", { style: "display:flex; gap:8px; padding:4px 0;" },
    h("div", { style: "width:180px; color: var(--ink-500);" }, label),
    h("div", {}, value));
}
