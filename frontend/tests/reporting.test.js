import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { Reporting } from "../src/pages/Reporting.js";

function findByTag(vnode, tag) {
  if (!vnode || typeof vnode !== "object") return null;
  if (vnode.tag === tag) return vnode;
  for (const child of vnode.children || []) {
    const found = findByTag(child, tag);
    if (found) return found;
  }
  return null;
}

describe("Reporting — permission gate", () => {
  test("a role without reporting:read is denied access", () => {
    const vnode = Reporting({ role: "DONOR" });
    assert.ok(JSON.stringify(vnode).includes("don't have access"));
  });
});

describe("Reporting — report/period selection", () => {
  test("Generate is disabled until a period is selected", () => {
    const vnode = Reporting({ role: "OWNER", periods: [], onSelectReportType: () => {}, onSelectPeriod: () => {}, onGenerate: () => {} });
    const button = findByTag(vnode, "button");
    assert.equal(button.props.disabled, true);
  });

  test("selecting a report type calls onSelectReportType with the real value, not a label", () => {
    let selected = null;
    const vnode = Reporting({ role: "OWNER", periods: [], onSelectReportType: (v) => { selected = v; }, onSelectPeriod: () => {}, onGenerate: () => {} });
    const select = findByTag(vnode, "select");
    select.props.onChange({ target: { value: "income-statement" } });
    assert.equal(selected, "income-statement");
  });
});

describe("Reporting — result rendering: never recomputes what the backend returned", () => {
  test("shows an explicit empty state before anything is generated", () => {
    const vnode = Reporting({ role: "OWNER", periods: [], selectedPeriodId: "p1", result: null });
    assert.ok(JSON.stringify(vnode).includes("No report generated yet"));
  });

  test("trial balance renders the backend's own totals and balanced flag verbatim", () => {
    const result = {
      total_debits: "1000.00", total_credits: "1000.00", is_balanced: true,
      lines: [{ account_id: "a1", account_code: "1000", account_name: "Cash", account_type: "ASSET", debit_total: "1000.00", credit_total: "0.00" }],
    };
    const vnode = Reporting({ role: "OWNER", reportType: "trial-balance", periods: [], selectedPeriodId: "p1", result });
    const text = JSON.stringify(vnode);
    assert.ok(text.includes("1,000.00"));
    assert.ok(text.includes("Balanced"));
    assert.ok(!text.includes("OUT OF BALANCE"));
  });

  test("an out-of-balance trial balance is labeled as such, never hidden", () => {
    const result = { total_debits: "1000.00", total_credits: "900.00", is_balanced: false, lines: [] };
    const vnode = Reporting({ role: "OWNER", reportType: "trial-balance", periods: [], selectedPeriodId: "p1", result });
    assert.ok(JSON.stringify(vnode).includes("OUT OF BALANCE"));
  });

  test("balance sheet shows the backend's own imbalance amount when the equation does not hold", () => {
    const result = {
      total_assets: "500.00", total_liabilities: "200.00", total_equity: "200.00",
      accounting_equation_holds: false, imbalance_amount: "100.00",
      asset_lines: [], liability_lines: [], equity_lines: [],
    };
    const vnode = Reporting({ role: "OWNER", reportType: "balance-sheet", periods: [], selectedPeriodId: "p1", result });
    assert.ok(JSON.stringify(vnode).includes("100.00"));
  });

  test("income statement renders net income exactly as returned, not recomputed from revenue - expenses locally", () => {
    const result = { total_revenue: "500.00", total_expenses: "300.00", net_income: "199.99", revenue_lines: [], expense_lines: [] };
    const vnode = Reporting({ role: "OWNER", reportType: "income-statement", periods: [], selectedPeriodId: "p1", result });
    // 199.99, not the locally-recomputable 200.00 — proves this is the backend's own figure
    assert.ok(JSON.stringify(vnode).includes("199.99"));
  });
});

describe("Reporting — error state", () => {
  test("a generation failure is shown with a retry action, not a silent blank report", () => {
    let retried = false;
    const vnode = Reporting({ role: "OWNER", periods: [], selectedPeriodId: "p1", error: "Period not found.", onRetry: () => { retried = true; } });
    const text = JSON.stringify(vnode);
    assert.ok(text.includes("Period not found."));
    const buttons = [];
    (function collect(v) { if (!v || typeof v !== "object") return; if (v.tag === "button") buttons.push(v); for (const c of v.children || []) collect(c); })(vnode);
    const retryButton = buttons.find((b) => JSON.stringify(b.children).includes("Try again"));
    retryButton.props.onClick();
    assert.equal(retried, true);
  });
});
