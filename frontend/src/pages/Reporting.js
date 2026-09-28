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
  loading, error, result, traceResult,
  onSelectReportType, onSelectPeriod, onSelectAccount, onGenerate, onRetry,
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
                h("option", { value: "" }, "All accounts"),
                (accounts || []).map((a) => h("option", { value: a.id }, `${a.code} — ${a.name}`))))
          : null,
        h("button", { className: "btn btn-primary", disabled: !selectedPeriodId, onClick: onGenerate }, "Generate")
      )
    ),
    error ? ErrorState({ message: error, onRetry }) : null,
    loading ? LoadingState("Generating…") : reportBody({ type, result, traceResult })
  );
}

function reportBody({ type, result, traceResult }) {
  if (type === "trace") return traceResult ? traceBody(traceResult) : EmptyState({ title: "No trace yet", message: "Select a period and account, then Generate." });
  if (!result) return EmptyState({ title: "No report generated yet", message: "Select a period and click Generate." });
  if (type === "trial-balance") return trialBalanceBody(result);
  if (type === "income-statement") return incomeStatementBody(result);
  if (type === "balance-sheet") return balanceSheetBody(result);
  if (type === "general-ledger") return generalLedgerBody(result);
  return null;
}

function trialBalanceBody(r) {
  return Fragment([
    h("div", { className: "card" },
      h("div", { style: "display:flex; gap:16px;" },
        metric("Total debits", formatMoney(r.total_debits)),
        metric("Total credits", formatMoney(r.total_credits)),
        h("div", {}, h("span", { className: `badge badge-${r.is_balanced ? "pass" : "fail"}` }, r.is_balanced ? "Balanced" : "OUT OF BALANCE"))
      )),
    h("div", { className: "card" },
      DataTable({
        columns: [
          { key: "account_code", label: "Code" }, { key: "account_name", label: "Account" }, { key: "account_type", label: "Type" },
          { key: "debit_total", label: "Debit", align: "right", render: (row) => formatMoney(row.debit_total) },
          { key: "credit_total", label: "Credit", align: "right", render: (row) => formatMoney(row.credit_total) },
        ],
        rows: r.lines || [], emptyTitle: "No activity this period",
      })),
  ]);
}

function incomeStatementBody(r) {
  return Fragment([
    h("div", { className: "card" },
      h("div", { style: "display:flex; gap:16px;" },
        metric("Total revenue", formatMoney(r.total_revenue)),
        metric("Total expenses", formatMoney(r.total_expenses)),
        metric("Net income", formatMoney(r.net_income)))),
    h("div", { className: "card" }, h("h3", {}, "Revenue"),
      DataTable({ columns: statementColumns(), rows: r.revenue_lines || [], emptyTitle: "No revenue recorded" })),
    h("div", { className: "card" }, h("h3", {}, "Expenses"),
      DataTable({ columns: statementColumns(), rows: r.expense_lines || [], emptyTitle: "No expenses recorded" })),
  ]);
}

function balanceSheetBody(r) {
  return Fragment([
    h("div", { className: "card" },
      h("div", { style: "display:flex; gap:16px; flex-wrap:wrap;" },
        metric("Total assets", formatMoney(r.total_assets)),
        metric("Total liabilities", formatMoney(r.total_liabilities)),
        metric("Total equity", formatMoney(r.total_equity)),
        h("div", {}, h("span", { className: `badge badge-${r.accounting_equation_holds ? "pass" : "fail"}` },
          r.accounting_equation_holds ? "Equation holds" : `Imbalance: ${formatMoney(r.imbalance_amount)}`)))),
    h("div", { className: "card" }, h("h3", {}, "Assets"), DataTable({ columns: statementColumns(), rows: r.asset_lines || [], emptyTitle: "No assets" })),
    h("div", { className: "card" }, h("h3", {}, "Liabilities"), DataTable({ columns: statementColumns(), rows: r.liability_lines || [], emptyTitle: "No liabilities" })),
    h("div", { className: "card" }, h("h3", {}, "Equity"), DataTable({ columns: statementColumns(), rows: r.equity_lines || [], emptyTitle: "No equity" })),
  ]);
}

function generalLedgerBody(r) {
  const accounts = r.accounts || [];
  if (!accounts.length) return EmptyState({ title: "No ledger activity" });
  return Fragment(accounts.map((section) =>
    h("div", { className: "card" },
      h("h3", {}, `${section.account_code} — ${section.account_name}`),
      DataTable({
        columns: [{ key: "line", label: "Entry", render: (row) => JSON.stringify(row) }],
        rows: section.entries || [], emptyTitle: "No entries",
      }),
      h("div", { style: "margin-top:8px; font-weight:600;" }, `Closing balance: ${formatMoney(section.closing_balance)}`)
    )));
}

function traceBody(t) {
  return h("div", { className: "card" }, h("h3", {}, "Trace result"),
    h("pre", { style: "white-space:pre-wrap; font-family: var(--font-mono); font-size:12.5px;" }, JSON.stringify(t, null, 2)));
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
