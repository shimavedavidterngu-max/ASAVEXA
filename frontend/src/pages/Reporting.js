import { h, Fragment } from "../lib/vdom.js";
import { DataTable } from "../components/DataTable.js";
import { LoadingState, ErrorState, EmptyState } from "../components/DataState.js";
import { allowed } from "../components/PermissionGate.js";
import { PERMISSIONS } from "../lib/permissions.js";
import { formatMoney } from "./Dashboard.js";

/**
 * Reporting (Section 7). This page displays exactly what the reporting
 * API returned and NOTHING it derived itself — no client-side sum, no
 * client-side balance check (Section 7: "Do not calculate authoritative
 * financial statements independently in the browser"). `is_balanced`,
 * `accounting_equation_holds`, every total: all read straight off the
 * response object.
 *
 * `reportType`: "trial-balance" | "income-statement" | "balance-sheet" | "general-ledger" | "trace"
 */
export function Reporting({
  role, reportType, periods, accounts, selectedPeriodId, selectedAccountId,
  loading, error, result, traceResult, completeness, reconciliationStatus,
  onSelectReportType, onSelectPeriod, onSelectAccount, onGenerate, onRetry,
  onDrillAccount, onOpenDrilldown,
}) {
  if (!allowed(role, PERMISSIONS.REPORTING_READ)) {
    return h("div", { className: "empty-state card" },
      h("h3", {}, "You don't have access to this"),
      h("p", {}, "Reporting read access is required to view this area."));
  }

  const type = reportType || "trial-balance";
  return h(
    "div",
    {},
    h("h1", {}, "Reporting"),
    h("p", { style: "color: var(--ink-500); margin-top: -8px; margin-bottom: 24px;" },
      "Every figure below is the backend's own authoritative calculation — this page never recomputes a total."),
    h(
      "div",
      { className: "card" },
      h("div", { style: "display:flex; gap:12px; flex-wrap:wrap; align-items:flex-end;" },
        h("div", { className: "field" }, h("label", {}, "Report"),
          h("select", { value: type, onChange: (e) => onSelectReportType(e.target.value) },
            [
              ["trial-balance", "Trial Balance"], ["income-statement", "Income Statement"],
              ["balance-sheet", "Balance Sheet"], ["general-ledger", "General Ledger"], ["trace", "Trace a line"],
            ].map(([v, label]) => h("option", { value: v }, label)))),
        h("div", { className: "field" }, h("label", {}, "Period"),
          h("select", { value: selectedPeriodId || "", onChange: (e) => onSelectPeriod(e.target.value) },
            h("option", { value: "" }, "Select period…"),
            (periods || []).map((p) => h("option", { value: p.id }, p.name)))),
        (type === "general-ledger" || type === "trace")
          ? h("div", { className: "field" }, h("label", {}, "Account"),
              h("select", { value: selectedAccountId || "", onChange: (e) => onSelectAccount(e.target.value) },
                h("option", { value: "" }, type === "trace" ? "Select account…" : "All accounts"),
                (accounts || []).map((a) => h("option", { value: a.id }, `${a.code} — ${a.name}`))))
          : null,
        h("button", { className: "btn btn-primary", disabled: !selectedPeriodId || (type === "trace" && !selectedAccountId), onClick: onGenerate }, "Generate")
      )
    ),
    error ? ErrorState({ message: error, onRetry }) : null,
    loading ? LoadingState("Generating…") : reportBody({ type, result, traceResult, completeness, reconciliationStatus, onDrillAccount, onOpenDrilldown })
  );
}

function reportBody({ type, result, traceResult, completeness, reconciliationStatus, onDrillAccount, onOpenDrilldown }) {
  if (type === "trace") {
    return traceResult
      ? traceBody(traceResult, { completeness, reconciliationStatus, onOpenDrilldown })
      : EmptyState({ title: "No trace yet", message: "Select a period and account, then Generate." });
  }
  if (!result) return EmptyState({ title: "No report generated yet", message: "Select a period and click Generate." });
  if (type === "trial-balance") return trialBalanceBody(result, onDrillAccount);
  if (type === "income-statement") return incomeStatementBody(result, onDrillAccount);
  if (type === "balance-sheet") return balanceSheetBody(result, onDrillAccount);
  if (type === "general-ledger") return generalLedgerBody(result, onOpenDrilldown);
  return null;
}

function trialBalanceBody(r, onDrillAccount) {
  return Fragment([
    h("div", { className: "card" },
      h("div", { style: "display:flex; gap:16px;" },
        metric("Total debits", formatMoney(r.total_debits)),
        metric("Total credits", formatMoney(r.total_credits)),
        h("div", {}, h("span", { className: `badge badge-${r.is_balanced ? "pass" : "fail"}` }, r.is_balanced ? "Balanced" : "OUT OF BALANCE"))
      )),
    h("div", { className: "card" },
      h("p", { style: "color: var(--ink-500); font-size:12.5px; margin-top:0;" }, "Click any line to see the evidence behind it."),
      DataTable({
        columns: [
          { key: "account_code", label: "Code" }, { key: "account_name", label: "Account" }, { key: "account_type", label: "Type" },
          { key: "debit_total", label: "Debit", align: "right", render: (row) => formatMoney(row.debit_total) },
          { key: "credit_total", label: "Credit", align: "right", render: (row) => formatMoney(row.credit_total) },
        ],
        rows: r.lines || [], emptyTitle: "No activity this period",
        onRowClick: onDrillAccount ? (row) => onDrillAccount(row.account_id) : undefined,
        getRowKey: (row) => row.account_id,
      })),
  ]);
}

function incomeStatementBody(r, onDrillAccount) {
  return Fragment([
    h("div", { className: "card" },
      h("div", { style: "display:flex; gap:16px;" },
        metric("Total revenue", formatMoney(r.total_revenue)),
        metric("Total expenses", formatMoney(r.total_expenses)),
        metric("Net income", formatMoney(r.net_income)))),
    h("div", { className: "card" }, h("h3", {}, "Revenue"),
      DataTable({ columns: statementColumns(), rows: r.revenue_lines || [], emptyTitle: "No revenue recorded",
        onRowClick: onDrillAccount ? (row) => onDrillAccount(row.account_id) : undefined, getRowKey: (row) => row.account_id })),
    h("div", { className: "card" }, h("h3", {}, "Expenses"),
      DataTable({ columns: statementColumns(), rows: r.expense_lines || [], emptyTitle: "No expenses recorded",
        onRowClick: onDrillAccount ? (row) => onDrillAccount(row.account_id) : undefined, getRowKey: (row) => row.account_id })),
  ]);
}

function balanceSheetBody(r, onDrillAccount) {
  const rowClick = onDrillAccount ? (row) => onDrillAccount(row.account_id) : undefined;
  return Fragment([
    h("div", { className: "card" },
      h("div", { style: "display:flex; gap:16px; flex-wrap:wrap;" },
        metric("Total assets", formatMoney(r.total_assets)),
        metric("Total liabilities", formatMoney(r.total_liabilities)),
        metric("Total equity", formatMoney(r.total_equity)),
        h("div", {}, h("span", { className: `badge badge-${r.accounting_equation_holds ? "pass" : "fail"}` },
          r.accounting_equation_holds ? "Equation holds" : `Imbalance: ${formatMoney(r.imbalance_amount)}`)))),
    h("div", { className: "card" }, h("h3", {}, "Assets"),
      DataTable({ columns: statementColumns(), rows: r.asset_lines || [], emptyTitle: "No assets", onRowClick: rowClick, getRowKey: (row) => row.account_id })),
    h("div", { className: "card" }, h("h3", {}, "Liabilities"),
      DataTable({ columns: statementColumns(), rows: r.liability_lines || [], emptyTitle: "No liabilities", onRowClick: rowClick, getRowKey: (row) => row.account_id })),
    h("div", { className: "card" }, h("h3", {}, "Equity"),
      DataTable({ columns: statementColumns(), rows: r.equity_lines || [], emptyTitle: "No equity", onRowClick: rowClick, getRowKey: (row) => row.account_id })),
  ]);
}

function generalLedgerBody(r, onOpenDrilldown) {
  const accounts = r.accounts || [];
  if (!accounts.length) return EmptyState({ title: "No ledger activity" });
  return Fragment(accounts.map((section) =>
    h("div", { className: "card" },
      h("h3", {}, `${section.account_code} — ${section.account_name}`),
      DataTable({
        columns: entryColumns(),
        rows: section.entries || [], emptyTitle: "No entries",
        onRowClick: onOpenDrilldown ? (row) => onOpenDrilldown(row.journal_id) : undefined,
        getRowKey: (row) => `${row.journal_id}-${row.date}`,
      }),
      h("div", { style: "margin-top:8px; font-weight:600;" }, `Closing balance: ${formatMoney(section.closing_balance)}`)
    )));
}

function traceBody(entries, { completeness, reconciliationStatus, onOpenDrilldown }) {
  return Fragment([
    h("div", { className: "card" },
      h("div", { style: "display:flex; justify-content:space-between; align-items:flex-start;" },
        h("h3", { style: "margin:0;" }, "Show Me the Number — trace result"),
      ),
      h("p", { style: "color: var(--ink-500); font-size:12.5px;" },
        "Every posted entry behind this account's balance, exactly as posted — click a row for its full evidence chain, approval history, and audit trail."),
      (completeness || reconciliationStatus)
        ? h("div", { style: "display:flex; gap:28px; flex-wrap:wrap; margin-top:8px;" }, [
            completeness ? traceMetric(
              "Evidence completeness",
              `${Math.round((completeness.completeness_ratio || 0) * 100)}%`,
              completeness.entries_missing_evidence > 0 ? "fail" : "pass",
              completeness.entries_missing_evidence > 0
                ? `${completeness.entries_missing_evidence} of ${completeness.total_entries} entries missing evidence`
                : `All ${completeness.total_entries} entries have evidence`
            ) : null,
            reconciliationStatus ? traceMetric(
              "Reconciliation exceptions",
              String(reconciliationStatus.exception_count ?? 0),
              (reconciliationStatus.exception_count || 0) > 0 ? "fail" : "pass",
              `${reconciliationStatus.reconciled_count || 0} reconciled · ${reconciliationStatus.outstanding_count || 0} outstanding`
            ) : null,
          ])
        : null),
    h("div", { className: "card" },
      DataTable({
        columns: [
          ...entryColumns(),
          {
            key: "show_evidence", label: "", render: (row) => h(
              "button",
              {
                className: "btn",
                onClick: (e) => { e.stopPropagation(); if (onOpenDrilldown) onOpenDrilldown(row.journal_id); },
              },
              "Show me the evidence"
            ),
          },
        ],
        rows: entries || [], emptyTitle: "No posted entries for this account and period",
        onRowClick: onOpenDrilldown ? (row) => onOpenDrilldown(row.journal_id) : undefined,
        getRowKey: (row) => `${row.journal_id}-${row.date}`,
      })),
  ]);
}

function traceMetric(label, value, tone, sub) {
  return h("div", {},
    h("div", { style: `font-size:20px; font-weight:600; color: var(--status-${tone});` }, value),
    h("div", { className: "metric-label" }, label),
    sub ? h("div", { style: "font-size:11.5px; color: var(--ink-500); margin-top:2px;" }, sub) : null);
}

function entryColumns() {
  return [
    { key: "date", label: "Date" },
    { key: "journal_number", label: "Journal #" },
    { key: "description", label: "Description" },
    { key: "debit", label: "Debit", align: "right", render: (row) => formatMoney(row.debit) },
    { key: "credit", label: "Credit", align: "right", render: (row) => formatMoney(row.credit) },
    { key: "running_balance", label: "Running balance", align: "right", render: (row) => formatMoney(row.running_balance) },
    { key: "evidence_ref", label: "Evidence", render: (row) => row.evidence_ref || "MISSING" },
  ];
}

function statementColumns() {
  return [
    { key: "account_code", label: "Code" }, { key: "account_name", label: "Account" },
    { key: "amount", label: "Amount", align: "right", render: (row) => formatMoney(row.amount) },
  ];
}

function metric(label, value) {
  return h("div", {}, h("div", { className: "metric-value", style: "font-size:22px;" }, value), h("div", { className: "metric-label" }, label));
}
