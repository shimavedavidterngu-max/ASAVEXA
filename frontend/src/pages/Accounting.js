import { h, Fragment } from "../lib/vdom.js";
import { StatusBadge } from "../components/StatusBadge.js";
import { DataTable } from "../components/DataTable.js";
import { LoadingState, ErrorState, EmptyState } from "../components/DataState.js";
import { PermissionGate, allowed } from "../components/PermissionGate.js";
import { PERMISSIONS } from "../lib/permissions.js";
import { formatMoney } from "./Dashboard.js";

/**
 * Accounting — chart of accounts, periods, and journals (Section 4).
 * Pure render function: the container (app.js) does every real API
 * call and passes the results in, exactly like Dashboard/AuditWorkspace
 * (Section 3's testability discipline — no fetch, no DOM, here).
 *
 * The UI never computes a balance, a debit/credit total, or a trial
 * figure itself — every number shown is a value the backend already
 * returned (Section 4: "Do not implement accounting calculations in
 * the frontend"). Posted journals render with no edit affordance at
 * all (not a disabled one — Section 4's "must not appear editable");
 * the only actions ever offered on a POSTED journal are Reverse (a new
 * offsetting journal, never a mutation of the original) and viewing
 * its audit trail.
 *
 * `view`: "overview" | "journal-new" | "journal-detail"
 */
export function Accounting({
  role, view, loading, error,
  accounts, periods, journal, journalError,
  accountForm, accountFormError, accountFormPending,
  periodForm, periodFormError, periodFormPending,
  form, formError, formPending,
  onNavigate, onRetry,
  onAccountFieldChange, onSubmitAccount,
  onPeriodFieldChange, onSubmitPeriod, onLockPeriod,
  onJournalFieldChange, onAddJournalLine, onRemoveJournalLine, onSubmitJournal,
  onPostJournal, onReverseJournal, onLoadJournalAuditTrail, journalAuditEvents,
}) {
  if (!allowed(role, PERMISSIONS.LEDGER_READ)) {
    return h("div", { className: "empty-state card" },
      h("h3", {}, "You don't have access to this"),
      h("p", {}, "Ledger read access is required to view Accounting."));
  }

  if (view === "journal-new") {
    return Fragment([
      breadcrumb(onNavigate, "New journal entry"),
      journalForm({ accounts, form, formError, formPending, onJournalFieldChange, onAddJournalLine, onRemoveJournalLine, onSubmitJournal }),
    ]);
  }

  if (view === "journal-detail") {
    if (loading) return LoadingState("Loading journal…");
    if (journalError) return ErrorState({ message: journalError, onRetry });
    if (!journal) return EmptyState({ title: "Journal not found" });
    return Fragment([
      breadcrumb(onNavigate, journal.journal_number || journal.id),
      journalDetail({ role, journal, onNavigate, onPostJournal, onReverseJournal, onLoadJournalAuditTrail, journalAuditEvents }),
    ]);
  }

  // Default: overview (accounts + periods + recent journal access)
  return h(
    "div",
    {},
    h("h1", {}, "Accounting"),
    h("p", { style: "color: var(--ink-500); margin-top: -8px; margin-bottom: 24px;" },
      "The chart of accounts, accounting periods, and journal entries — the authoritative ledger every other module reads from."),
    error ? ErrorState({ message: error, onRetry }) : null,
    loading ? LoadingState() : Fragment([
      accountsSection({ role, accounts, form: accountForm, formError: accountFormError, formPending: accountFormPending, onAccountFieldChange, onSubmitAccount }),
      periodsSection({ role, periods, form: periodForm, formError: periodFormError, formPending: periodFormPending, onPeriodFieldChange, onSubmitPeriod, onLockPeriod }),
      journalsSection({ role, onNavigate }),
    ])
  );
}

function breadcrumb(onNavigate, currentLabel) {
  return h(
    "div",
    { className: "breadcrumbs" },
    h("a", { href: "#/accounting", onClick: (e) => { e.preventDefault(); onNavigate("/accounting"); } }, "Accounting"),
    h("span", {}, "/"),
    h("span", {}, currentLabel)
  );
}

function accountsSection({ role, accounts, form, formError, formPending, onAccountFieldChange, onSubmitAccount }) {
  return h(
    "div",
    { className: "card" },
    h("h2", {}, "Chart of Accounts"),
    (accounts && accounts.length)
      ? DataTable({
          columns: [
            { key: "code", label: "Code" },
            { key: "name", label: "Name" },
            { key: "type", label: "Type", render: (r) => StatusBadge({ status: r.type, label: r.type }) },
            { key: "currency", label: "Currency" },
            { key: "is_active", label: "Active", render: (r) => (r.is_active ? "Yes" : "No") },
          ],
          rows: accounts,
          emptyTitle: "No accounts yet",
        })
      : EmptyState({ title: "No accounts yet", message: "Create the first account below." }),
    PermissionGate({ role, permission: PERMISSIONS.ACCOUNT_MANAGE },
      accountForm({ form, formError, formPending, onAccountFieldChange, onSubmitAccount }))
  );
}

function accountForm({ form, formError, formPending, onAccountFieldChange, onSubmitAccount }) {
  const f = form || {};
  return h(
    "form",
    { style: "margin-top:16px; border-top:1px solid var(--line); padding-top:16px;", onSubmit: (e) => { e.preventDefault(); onSubmitAccount(); } },
    h("h3", {}, "New account"),
    formError ? h("div", { className: "alert alert-error" }, formError) : null,
    h("div", { style: "display:flex; gap:12px; flex-wrap:wrap;" },
      h("div", { className: "field" }, h("label", {}, "Code"),
        h("input", { value: f.code || "", required: true, onInput: (e) => onAccountFieldChange("code", e.target.value) })),
      h("div", { className: "field" }, h("label", {}, "Name"),
        h("input", { value: f.name || "", required: true, onInput: (e) => onAccountFieldChange("name", e.target.value) })),
      h("div", { className: "field" }, h("label", {}, "Type"),
        h("select", { value: f.type || "ASSET", onChange: (e) => onAccountFieldChange("type", e.target.value) },
          ["ASSET", "LIABILITY", "EQUITY", "REVENUE", "EXPENSE"].map((t) => h("option", { value: t }, t)))),
      h("div", { className: "field" }, h("label", {}, "Currency"),
        h("input", { value: f.currency || "USD", onInput: (e) => onAccountFieldChange("currency", e.target.value) }))
    ),
    h("button", { type: "submit", className: "btn btn-primary", disabled: formPending }, formPending ? "Creating…" : "Create account")
  );
}

function periodsSection({ role, periods, form, formError, formPending, onPeriodFieldChange, onSubmitPeriod, onLockPeriod }) {
  return h(
    "div",
    { className: "card" },
    h("h2", {}, "Accounting Periods"),
    (periods && periods.length)
      ? DataTable({
          columns: [
            { key: "name", label: "Period" },
            { key: "start_date", label: "Start" },
            { key: "end_date", label: "End" },
            { key: "status", label: "Status", render: (r) => StatusBadge({ status: r.status }) },
            {
              key: "actions", label: "",
              render: (r) =>
                r.status === "OPEN"
                  ? PermissionGate({ role, permission: PERMISSIONS.PERIOD_MANAGE },
                      h("button", { className: "btn btn-secondary", onClick: () => onLockPeriod(r.id) }, "Lock"))
                  : h("span", { style: "color: var(--ink-500); font-size:12.5px;" }, "No further postings allowed."),
            },
          ],
          rows: periods,
          emptyTitle: "No periods opened yet",
        })
      : EmptyState({ title: "No periods opened yet", message: "Open the first accounting period below." }),
    PermissionGate({ role, permission: PERMISSIONS.PERIOD_MANAGE },
      periodForm({ form, formError, formPending, onPeriodFieldChange, onSubmitPeriod }))
  );
}

function periodForm({ form, formError, formPending, onPeriodFieldChange, onSubmitPeriod }) {
  const f = form || {};
  return h(
    "form",
    { style: "margin-top:16px; border-top:1px solid var(--line); padding-top:16px;", onSubmit: (e) => { e.preventDefault(); onSubmitPeriod(); } },
    h("h3", {}, "Open a new period"),
    formError ? h("div", { className: "alert alert-error" }, formError) : null,
    h("div", { style: "display:flex; gap:12px; flex-wrap:wrap;" },
      h("div", { className: "field" }, h("label", {}, "Name"),
        h("input", { value: f.name || "", required: true, onInput: (e) => onPeriodFieldChange("name", e.target.value) })),
      h("div", { className: "field" }, h("label", {}, "Start date"),
        h("input", { type: "date", value: f.start_date || "", required: true, onInput: (e) => onPeriodFieldChange("start_date", e.target.value) })),
      h("div", { className: "field" }, h("label", {}, "End date"),
        h("input", { type: "date", value: f.end_date || "", required: true, onInput: (e) => onPeriodFieldChange("end_date", e.target.value) }))
    ),
    h("button", { type: "submit", className: "btn btn-primary", disabled: formPending }, formPending ? "Opening…" : "Open period")
  );
}

function journalsSection({ role, onNavigate }) {
  return h(
    "div",
    { className: "card" },
    h("h2", {}, "Journal Entries"),
    h("p", { style: "color: var(--ink-500);" },
      "Look up a journal by id from the Audit Workspace, or create a new draft entry below. A draft is never part of the ledger until posted."),
    PermissionGate({ role, permission: PERMISSIONS.JOURNAL_CREATE },
      h("button", { className: "btn btn-primary", onClick: () => onNavigate("/accounting/journals/new") }, "New journal entry"))
  );
}

function journalForm({ accounts, form, formError, formPending, onJournalFieldChange, onAddJournalLine, onRemoveJournalLine, onSubmitJournal }) {
  const f = form || { lines: [{}, {}] };
  const lines = f.lines || [];
  return h(
    "div",
    { className: "card" },
    h("h2", {}, "New journal entry"),
    h("p", { style: "color: var(--ink-500);" }, "Every entry must balance: total debits must equal total credits (Rule 1). This form only submits what you enter — the backend is the sole judge of whether it balances."),
    formError ? h("div", { className: "alert alert-error" }, formError) : null,
    h(
      "form",
      { onSubmit: (e) => { e.preventDefault(); onSubmitJournal(); } },
      h("div", { style: "display:flex; gap:12px; flex-wrap:wrap;" },
        h("div", { className: "field" }, h("label", {}, "Date"),
          h("input", { type: "date", value: f.date || "", required: true, onInput: (e) => onJournalFieldChange("date", e.target.value) })),
        h("div", { className: "field", style: "flex:1; min-width:220px;" }, h("label", {}, "Description"),
          h("input", { value: f.description || "", required: true, onInput: (e) => onJournalFieldChange("description", e.target.value) })),
        h("div", { className: "field" }, h("label", {}, "Currency"),
          h("input", { value: f.currency || "USD", onInput: (e) => onJournalFieldChange("currency", e.target.value) }))
      ),
      h("div", { style: "display:flex; gap:12px; flex-wrap:wrap;" },
        h("div", { className: "field" }, h("label", {}, "Transaction reference (optional)"),
          h("input", { value: f.transaction_ref || "", onInput: (e) => onJournalFieldChange("transaction_ref", e.target.value) })),
        h("div", { className: "field" }, h("label", {}, "Evidence reference (optional)"),
          h("input", { value: f.evidence_ref || "", onInput: (e) => onJournalFieldChange("evidence_ref", e.target.value) }))
      ),
      h("h3", {}, "Lines"),
      lines.map((line, i) => journalLineRow({ line, i, accounts, onJournalFieldChange, onRemoveJournalLine, removable: lines.length > 2 })),
      h("button", { type: "button", className: "btn btn-secondary", onClick: onAddJournalLine, style: "margin-bottom:16px;" }, "+ Add line"),
      h("div", {},
        h("button", { type: "submit", className: "btn btn-primary", disabled: formPending }, formPending ? "Creating…" : "Create draft journal"))
    )
  );
}

function journalLineRow({ line, i, accounts, onJournalFieldChange, onRemoveJournalLine, removable }) {
  return h(
    "div",
    { style: "display:flex; gap:12px; align-items:flex-end; flex-wrap:wrap; margin-bottom:8px;" },
    h("div", { className: "field" }, h("label", {}, "Account"),
      h("select", { value: line.account_id || "", onChange: (e) => onJournalFieldChange(`lines.${i}.account_id`, e.target.value) },
        h("option", { value: "" }, "Select account…"),
        (accounts || []).map((a) => h("option", { value: a.id }, `${a.code} — ${a.name}`)))),
    h("div", { className: "field" }, h("label", {}, "Debit"),
      h("input", { type: "number", step: "0.01", value: line.debit_amount || "", onInput: (e) => onJournalFieldChange(`lines.${i}.debit_amount`, e.target.value) })),
    h("div", { className: "field" }, h("label", {}, "Credit"),
      h("input", { type: "number", step: "0.01", value: line.credit_amount || "", onInput: (e) => onJournalFieldChange(`lines.${i}.credit_amount`, e.target.value) })),
    h("div", { className: "field", style: "flex:1; min-width:160px;" }, h("label", {}, "Description"),
      h("input", { value: line.description || "", onInput: (e) => onJournalFieldChange(`lines.${i}.description`, e.target.value) })),
    removable ? h("button", { type: "button", className: "btn btn-danger", onClick: () => onRemoveJournalLine(i) }, "Remove") : null
  );
}

function journalDetail({ role, journal, onNavigate, onPostJournal, onReverseJournal, onLoadJournalAuditTrail, journalAuditEvents }) {
  const isDraft = journal.status === "DRAFT";
  const isPosted = journal.status === "POSTED";
  return h(
    "div",
    {},
    h(
      "div",
      { className: "card" },
      h("div", { style: "display:flex; justify-content:space-between; align-items:flex-start;" },
        h("div", {},
          h("h2", {}, journal.description),
          h("div", { className: "mono", style: "font-size:12.5px; color: var(--ink-500);" }, `${journal.journal_number || journal.id}`)),
        StatusBadge({ status: journal.status })
      ),
      h("div", { style: "margin-top:8px; color: var(--ink-500); font-size:13px;" },
        `${journal.date}  ·  ${journal.currency}${journal.transaction_ref ? `  ·  ref: ${journal.transaction_ref}` : ""}`),
      // Section 4: a POSTED journal has NO edit affordance at all — only
      // Post (while DRAFT) and Reverse (while POSTED) ever render.
      isDraft ? PermissionGate({ role, permission: PERMISSIONS.JOURNAL_POST },
        h("button", { className: "btn btn-primary", style: "margin-top:12px;", onClick: () => onPostJournal(journal.id) }, "Post journal")) : null,
      isPosted ? PermissionGate({ role, permission: PERMISSIONS.JOURNAL_REVERSE },
        h("button", { className: "btn btn-danger", style: "margin-top:12px;", onClick: () => onReverseJournal(journal.id) }, "Reverse journal")) : null,
      journal.status === "REVERSED" && journal.reversed_by_journal_id
        ? h("div", { className: "alert alert-info", style: "margin-top:12px;" },
            "This journal was reversed by ", h("a", { href: `#/accounting/journals/${journal.reversed_by_journal_id}` }, journal.reversed_by_journal_id))
        : null,
      journal.reversal_of_journal_id
        ? h("div", { className: "alert alert-info", style: "margin-top:12px;" },
            "This is a reversal of ", h("a", { href: `#/accounting/journals/${journal.reversal_of_journal_id}` }, journal.reversal_of_journal_id))
        : null
    ),
    h(
      "div",
      { className: "card" },
      h("h3", {}, "Lines"),
      DataTable({
        columns: [
          { key: "account_id", label: "Account" },
          { key: "description", label: "Description" },
          { key: "debit_amount", label: "Debit", align: "right", render: (r) => (Number(r.debit_amount) > 0 ? formatMoney(r.debit_amount) : "") },
          { key: "credit_amount", label: "Credit", align: "right", render: (r) => (Number(r.credit_amount) > 0 ? formatMoney(r.credit_amount) : "") },
        ],
        rows: journal.lines || [],
        emptyTitle: "No lines",
      })
    ),
    PermissionGate({ role, permission: PERMISSIONS.AUDIT_READ },
      h(
        "div",
        { className: "card" },
        h("div", { style: "display:flex; justify-content:space-between; align-items:center;" },
          h("h3", {}, "Audit trail"),
          !journalAuditEvents ? h("button", { className: "btn btn-secondary", onClick: () => onLoadJournalAuditTrail(journal.id) }, "Load audit trail") : null),
        journalAuditEvents
          ? DataTable({
              columns: [
                { key: "action", label: "Action" },
                { key: "actor", label: "Actor" },
                { key: "timestamp", label: "When" },
              ],
              rows: journalAuditEvents,
              emptyTitle: "No audit events recorded",
            })
          : null
      ))
  );
}
