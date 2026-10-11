/** Pure helpers for the Financial Analysis workspace. No DOM, no network. The server calculates everything; these only format and decide what to show. */
import { PERMISSIONS, ROLE_PERMISSIONS } from "./permissions.js";

export const TABS = [["overview", "Overview"], ["ratios", "Ratios"], ["variance", "Variance"], ["budget", "Budget"], ["forecast", "Forecast"], ["reports", "Reports"], ["setup", "Setup"]];
export const RATIO_TONE = { CALCULATED: "pass", INCOMPLETE: "warn", UNDEFINED: "neutral" };
export const RATIO_STATUS_TEXT = { CALCULATED: "Calculated", INCOMPLETE: "Needs setup", UNDEFINED: "Not meaningful" };
export const REPORT_STATE = { DRAFT: { tone: "neutral", label: "Draft" }, SUBMITTED: { tone: "info", label: "Waiting for review" }, APPROVED: { tone: "pass", label: "Approved" }, REJECTED: { tone: "fail", label: "Sent back" } };
export const reportState = (s) => REPORT_STATE[s] || { tone: "neutral", label: s || "—" };
export const TAG_TEXT = { CASH: "Cash and bank", RECEIVABLE: "Trade receivables", INVENTORY: "Inventory", CURRENT_ASSET: "Other current asset", NONCURRENT_ASSET: "Non-current asset", PAYABLE: "Trade payables", CURRENT_LIABILITY: "Other current liability",
  NONCURRENT_LIABILITY: "Non-current liability", COST_OF_SALES: "Cost of sales", OPERATING_EXPENSE: "Operating expense", FINANCE_COST: "Finance cost" };

export const has = (role, perm) => !!(ROLE_PERMISSIONS[role] && ROLE_PERMISSIONS[role].includes(perm));
export const canPrepare = (role) => has(role, PERMISSIONS.ANALYSIS_PREPARE);
export const canApprove = (role) => has(role, PERMISSIONS.ANALYSIS_APPROVE);

/** 1234567.5 -> "1,234,567.50". Works on the server's decimal strings; never converts through a float for display of whole figures. */
export function num(v) {
  if (v == null || v === "") return "—";
  const m = /^(-?)(\d+)(?:\.(\d+))?$/.exec(String(v));
  if (!m) return String(v);
  return `${m[1]}${m[2].replace(/\B(?=(\d{3})+(?!\d))/g, ",")}${m[3] ? "." + m[3] : ""}`;
}

export function ratioText(r) {
  if (r.value == null) return "—";
  if (r.unit === "percent") return `${num(r.value)}%`;
  if (r.unit === "days") return `${num(r.value)} days`;
  return num(r.value);
}

export function groupRatios(ratios) {
  const groups = [];
  for (const r of ratios || []) {
    let g = groups.find((x) => x.name === r.group);
    if (!g) { g = { name: r.group, ratios: [] }; groups.push(g); }
    g.ratios.push(r);
  }
  return groups;
}

export const changeTone = (row) => (row.material ? "warn" : "neutral");
export const pctText = (p) => (p == null ? "new" : `${num(p)}%`);
export const favText = (f) => (f === true ? "Favourable" : f === false ? "Unfavourable" : "On budget");
export const favTone = (f) => (f === true ? "pass" : f === false ? "fail" : "neutral");

/** What the person may do with a report right now. The server enforces all of it again; this only avoids showing buttons that would be refused. */
export function reportActions(report, role, userId) {
  const s = report ? report.status : null, mine = !!report && report.submitted_by === userId;
  return {
    edit: canPrepare(role) && (s === "DRAFT" || s === "REJECTED"),
    submit: canPrepare(role) && (s === "DRAFT" || s === "REJECTED"),
    decide: canApprove(role) && s === "SUBMITTED" && !mine,
    ownSubmission: canApprove(role) && s === "SUBMITTED" && mine,
    verify: !!report && report.has_snapshot,
    export: !!report && s === "APPROVED",
  };
}

export const emptyScenario = () => ({ id: "", name: "", months: "6", base_monthly_revenue: "", base_monthly_expenses: "", revenue_growth_pct: "0", expense_growth_pct: "0", opening_cash: "" });
export function scenarioProblem(f) {
  if ((f.name || "").trim().length < 2) return "Give the scenario a name.";
  const m = String(f.months).trim();
  if (!/^\d+$/.test(m) || +m < 1 || +m > 24) return "Months must be a whole number from 1 to 24.";
  for (const [k, label, nonneg] of [["base_monthly_revenue", "Base monthly revenue", true], ["base_monthly_expenses", "Base monthly expenses", true], ["revenue_growth_pct", "Revenue growth", false], ["expense_growth_pct", "Expense growth", false], ["opening_cash", "Opening cash", false]]) {
    const v = String(f[k] == null ? "" : f[k]).trim();
    if (!/^-?\d+(\.\d+)?$/.test(v)) return `${label} must be a number.`;
    if (nonneg && v.startsWith("-")) return `${label} cannot be negative.`;
  }
  return null;
}
export const scenarioBody = (f, periodId) => ({ name: f.name.trim(), base_period_id: periodId, assumptions: { months: parseInt(f.months, 10), base_monthly_revenue: f.base_monthly_revenue.trim(), base_monthly_expenses: f.base_monthly_expenses.trim(),
  revenue_growth_pct: f.revenue_growth_pct.trim(), expense_growth_pct: f.expense_growth_pct.trim(), opening_cash: f.opening_cash.trim() } });
export const scenarioForm = (s) => ({ id: s.id, name: s.name, months: String(s.assumptions.months), base_monthly_revenue: s.assumptions.base_monthly_revenue, base_monthly_expenses: s.assumptions.base_monthly_expenses,
  revenue_growth_pct: s.assumptions.revenue_growth_pct, expense_growth_pct: s.assumptions.expense_growth_pct, opening_cash: s.assumptions.opening_cash });

/** Budget lines typed into boxes: blank boxes are left out. */
export function budgetBody(values, periodId, note) {
  const lines = {};
  for (const [id, v] of Object.entries(values || {})) if (String(v).trim() !== "") lines[id] = String(v).trim();
  return { period_id: periodId, lines, note: (note || "").trim() };
}
export function budgetProblem(values) {
  const entries = Object.entries(values || {}).filter(([, v]) => String(v).trim() !== "");
  if (!entries.length) return "Enter at least one budget amount.";
  for (const [, v] of entries) if (!/^\d+(\.\d+)?$/.test(String(v).trim())) return "Budget amounts must be positive numbers (no letters or minus signs).";
  return null;
}

export const emptyReportForm = () => ({ title: "", note: "", scenario_ids: [], evidence_ids: "" });
export function reportProblem(f) { return (f.title || "").trim().length < 3 ? "Give the report a title (at least 3 characters)." : null; }
export const evidenceList = (text) => String(text || "").split(/[\s,;]+/).map((x) => x.trim()).filter(Boolean);
export const reportBody = (f, periodId) => ({ period_id: periodId, title: f.title.trim(), note: (f.note || "").trim(), scenario_ids: f.scenario_ids || [], evidence_ids: evidenceList(f.evidence_ids) });

export const WORKSPACE_TONE = { "NOT STARTED": "neutral", "IN PROGRESS": "info", BLOCKED: "warn", "IMPLEMENTED—TESTS PENDING": "info", "VERIFIED IN TEST ENVIRONMENT": "pass", "VERIFIED IN STAGING": "pass", "VERIFIED IN PRODUCTION": "pass", "INDEPENDENTLY REVIEWED": "pass" };
export const canOpenWorkspace = (w, role) => !!w.path && (!w.permission || has(role, w.permission));
