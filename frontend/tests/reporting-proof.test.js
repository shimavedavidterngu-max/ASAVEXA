import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { Reporting } from "../src/pages/Reporting.js";
import { accountProofSteps } from "../src/lib/accountProof.js";

const walk = (v, fn) => { if (!v || typeof v !== "object") return; fn(v); (v.children || []).forEach((c) => walk(c, fn)); };
const all = (v, pred) => { const out = []; walk(v, (n) => { if (pred(n)) out.push(n); }); return out; };
const text = (v) => { if (v == null || v === false) return ""; if (typeof v !== "object") return String(v); return (v.children || []).map(text).join(""); };
const byId = (v, id) => all(v, (n) => n.props && n.props.id === id)[0];

const accounts = [{ id: "a1", code: "1000", name: "Cash at bank" }, { id: "a2", code: "4000", name: "Sales" }];
const tb = { total_debits: "1075000.00", total_credits: "1075000.00", is_balanced: true,
  lines: [{ account_id: "a1", account_code: "1000", account_name: "Cash at bank", account_type: "ASSET", debit_total: "1075000.00", credit_total: "0.00" },
          { account_id: "a2", account_code: "4000", account_name: "Sales", account_type: "REVENUE", debit_total: "0.00", credit_total: "1075000.00" }] };
const base = (over = {}) => ({ role: "OWNER", reportType: "trial-balance", periods: [], accounts, selectedPeriodId: "p1", result: tb, onSelectReportType() {}, onSelectPeriod() {}, onGenerate() {}, onToggleProof() {}, onCloseProof() {}, ...over });
const marks = (v) => all(v, (n) => n.tag === "button" && /\bpm\b/.test(n.props.className || ""));

describe("a proof mark on each report line", () => {
  test("each line gets one, and before anything is loaded it says the proof is not checked", () => {
    const m = marks(Reporting(base()));
    assert.equal(m.length, 2);
    for (const b of m) assert.match(b.props["aria-label"], /Proof not checked for/);
    assert.match(m[0].props["aria-label"], /1000 Cash at bank/);
  });
  test("without a handler there are no marks, so a plain report never implies proof", () => {
    assert.equal(marks(Reporting(base({ onToggleProof: undefined }))).length, 0);
  });
  test("income statement and balance sheet lines get them too", () => {
    const is = { total_revenue: "10.00", total_expenses: "5.00", net_income: "5.00", revenue_lines: [{ account_id: "a2", account_code: "4000", account_name: "Sales", amount: "10.00" }], expense_lines: [] };
    assert.equal(marks(Reporting(base({ reportType: "income-statement", result: is }))).length, 1);
    const bs = { total_assets: "1", total_liabilities: "0", total_equity: "1", accounting_equation_holds: true, asset_lines: [{ account_id: "a1", account_code: "1000", account_name: "Cash at bank", amount: "1.00" }], liability_lines: [], equity_lines: [] };
    assert.equal(marks(Reporting(base({ reportType: "balance-sheet", result: bs }))).length, 1);
  });
  test("once loaded, the mark shows what was found; the open one is expanded", () => {
    const steps = accountProofSteps({ trace: [{}, {}], completeness: { total_entries: 2, entries_missing_evidence: 1 }, reconciliation: null });
    const v = Reporting(base({ lineProof: { openId: "a1", loading: false, entries: { a1: { steps } } } }));
    const m = marks(v);
    assert.match(m[0].props["aria-label"], /Proof incomplete/);
    assert.equal(m[0].props["aria-expanded"], "true");
    assert.equal(m[0].props["aria-controls"], "lp-a1-rail");
    assert.match(m[1].props["aria-label"], /not checked/);
    assert.equal(m[1].props["aria-expanded"], "false");
  });
  test("the rail for the open line names the account and shows the steps", () => {
    const steps = accountProofSteps({ trace: [{}], completeness: { total_entries: 1, entries_missing_evidence: 0 }, reconciliation: null });
    const v = Reporting(base({ lineProof: { openId: "a1", loading: false, entries: { a1: { steps } } } }));
    const rail = byId(v, "lp-a1-rail");
    assert.ok(rail);
    assert.match(text(rail), /Proof behind 1000 — Cash at bank/);
    assert.match(text(rail), /1 posted entry/);
    assert.equal(all(rail, (n) => n.props && n.props["data-stage"]).length, 2);
  });
  test("while loading it says so; a failed load claims nothing and offers a retry", () => {
    const loading = Reporting(base({ lineProof: { openId: "a1", loading: true, entries: {} } }));
    assert.match(text(byId(loading, "lp-a1-rail-loading")), /Loading/);
    const calls = [];
    const failed = Reporting(base({ onToggleProof: (...a) => calls.push(a), lineProof: { openId: "a1", loading: false, entries: { a1: { error: "Could not load the posted entries for this account. Nothing is claimed about it." } } } }));
    assert.match(text(byId(failed, "lp-a1-rail-error")), /Nothing is claimed/);
    byId(failed, "lp-a1-rail-retry").props.onClick();
    assert.deepEqual(calls.pop(), ["a1", { retry: true }]);
  });
  test("a mark does not trigger the row's own drill-down", () => {
    let toggled = 0, drilled = 0, stopped = 0;
    const v = Reporting(base({ onToggleProof: () => { toggled += 1; }, onDrillAccount: () => { drilled += 1; } }));
    const m = marks(v)[0];
    m.props.onClick({ stopPropagation: () => { stopped += 1; } });
    m.props.onKeydown({ stopPropagation: () => { stopped += 1; } });
    assert.deepEqual([toggled, drilled, stopped], [1, 0, 2]);
  });
});

describe("the app wiring", () => {
  const app = readFileSync(new URL("../src/app.js", import.meta.url), "utf8");
  test("a line's proof is loaded only when asked, with three read-only calls, and a stale answer is dropped", () => {
    assert.match(app, /Promise\.allSettled\(\[api\.traceLine\(accountId, periodId\), api\.evidenceCompleteness\(accountId, periodId\), api\.reconciliationSummary\(accountId\)\]\)/);
    assert.match(app, /if \(uiState\.lineProof !== lp \|\| lp\.openId !== accountId\) return;/);
  });
  test("changing the period, the report or regenerating clears what was loaded", () => {
    assert.ok((app.match(/resetLineProof\(\)/g) || []).length >= 4);
  });
  test("focus moves into the rail on open and back to the mark on close", () => {
    assert.match(app, /focusRail\(`lp-\$\{accountId\}-rail`\)/);
    assert.match(app, /focusMark\(`lp-\$\{id\}`\)/);
  });
});
