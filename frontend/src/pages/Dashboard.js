import { h, Fragment } from "../lib/vdom.js";
import { allowed } from "../components/PermissionGate.js";
import { PERMISSIONS } from "../lib/permissions.js";

/**
 * Dashboard — pure render function. Takes already-fetched `data` (the
 * container component below is responsible for calling the real API;
 * this function never calls fetch itself, which is what makes it
 * testable without a network or DOM).
 *
 * `data` fields are ALL sourced from real endpoints — nothing
 * invented (Section 3: "Use information supported by the actual
 * backend"):
 *   trialBalance        <- GET /reports/trial-balance
 *   reconciliationSummary <- GET /reports/reconciliation-summary (per bank account; caller aggregates)
 *   activeCloseProcess   <- GET /period-close/periods/{id}/active
 *   findingCounts        <- derived by the caller from GET /compliance/findings (by status)
 *   evidenceStatusCounts <- derived by the caller from GET /evidence
 * A field the caller couldn't fetch (e.g. no active period selected
 * yet) is passed as null/undefined and rendered as an explicit empty
 * state — never a fabricated zero.
 */
export function Dashboard({ role, data, onNavigate }) {
  return h(
    "div",
    {},
    h("h1", {}, "Dashboard"),
    h("p", { style: "color: var(--ink-500); margin-top: -8px; margin-bottom: 24px;" },
      "Don't just report the number. Prove it."),
    h("div", { className: "card-grid" },
      financialPositionCard(data.trialBalance, onNavigate),
      reconciliationHealthCard(data.reconciliationSummary, onNavigate),
      periodCloseCard(data.activeCloseProcess, data.currentPeriod, onNavigate),
      controlsCard(data.controlSummary, onNavigate, role),
      findingsCard(data.findingCounts, onNavigate, role),
      evidenceCard(data.evidenceStatusCounts, onNavigate)
    )
  );
}

function metric(label, value, onClick) {
  return h(
    "div",
    { className: "card metric-card", onClick, tabindex: onClick ? "0" : undefined, role: onClick ? "button" : undefined },
    h("div", { className: "metric-value" }, value),
    h("div", { className: "metric-label" }, label)
  );
}

function financialPositionCard(trialBalance, onNavigate) {
  if (!trialBalance) {
    return emptyMetricCard("Financial Position", "No period selected yet.");
  }
  return metric(
    trialBalance.is_balanced ? "Trial Balance — Balanced" : "Trial Balance — OUT OF BALANCE",
    formatMoney(trialBalance.total_debits),
    () => onNavigate("/reporting/trial-balance")
  );
}

function reconciliationHealthCard(summary, onNavigate) {
  if (!summary) return emptyMetricCard("Reconciliation Health", "No bank accounts reconciled yet.");
  return h(
    "div",
    { className: "card metric-card", onClick: () => onNavigate("/reconciliation"), tabindex: "0", role: "button" },
    h("div", { className: "metric-label" }, "Reconciliation"),
    h("div", { style: "display:flex; gap:16px; margin-top:8px;" },
      countPill("Reconciled", summary.reconciled_count, "pass"),
      countPill("Outstanding", summary.outstanding_count, "warn"),
      countPill("Exceptions", summary.exception_count, "fail")
    )
  );
}

function periodCloseCard(process, currentPeriod, onNavigate) {
  if (!currentPeriod) return emptyMetricCard("Period Close", "No open period.");
  const status = process ? process.status : "Not started";
  return h(
    "div",
    { className: "card metric-card", onClick: () => onNavigate("/period-close"), tabindex: "0", role: "button" },
    h("div", { className: "metric-label" }, `Period Close — ${currentPeriod.name}`),
    h("div", { style: "margin-top: 8px; font-size: 18px;" }, status),
    process && process.status === "CONTROLS_FAILED"
      ? h("div", { style: "margin-top:4px; font-size:12.5px; color: var(--status-fail);" },
          "Blocked — see readiness for the exact controls that failed.")
      : null
  );
}

function controlsCard(summary, onNavigate, role) {
  if (!allowed(role, PERMISSIONS.CONTROL_READ)) return null;
  if (!summary) return emptyMetricCard("Controls", "No controls executed yet this period.");
  return h(
    "div",
    { className: "card metric-card", onClick: () => onNavigate("/compliance/controls"), tabindex: "0", role: "button" },
    h("div", { className: "metric-label" }, "Controls this period"),
    h("div", { style: "display:flex; gap:16px; margin-top:8px;" },
      countPill("Executed", summary.executed, "info"),
      countPill("Warnings", summary.warnings, "warn"),
      countPill("Failed", summary.failed, "fail")
    )
  );
}

function findingsCard(counts, onNavigate, role) {
  if (!allowed(role, PERMISSIONS.CONTROL_READ)) return null;
  if (!counts) return emptyMetricCard("Findings", "No findings recorded for this organisation.");
  return h(
    "div",
    { className: "card metric-card", onClick: () => onNavigate("/compliance/findings"), tabindex: "0", role: "button" },
    h("div", { className: "metric-label" }, "Findings"),
    h("div", { style: "display:flex; gap:12px; margin-top:8px; flex-wrap:wrap;" },
      countPill("Open", counts.OPEN || 0, "fail"),
      countPill("Under review", counts.UNDER_REVIEW || 0, "warn"),
      countPill("Remediation required", counts.REMEDIATION_REQUIRED || 0, "warn"),
      countPill("Awaiting verification", counts.RESOLVED || 0, "info")
    )
  );
}

function evidenceCard(counts, onNavigate) {
  if (!counts) return emptyMetricCard("Evidence", "No evidence records yet.");
  return h(
    "div",
    { className: "card metric-card", onClick: () => onNavigate("/evidence"), tabindex: "0", role: "button" },
    h("div", { className: "metric-label" }, "Evidence"),
    h("div", { style: "display:flex; gap:12px; margin-top:8px; flex-wrap:wrap;" },
      countPill("Verified", counts.VERIFIED || 0, "pass"),
      countPill("Needs attention", (counts.INCOMPLETE || 0) + (counts.CONFLICTING || 0), "warn"),
      countPill("Missing", counts.MISSING || 0, "fail")
    )
  );
}

function countPill(label, value, tone) {
  return h(
    "div",
    {},
    h("div", { className: `badge badge-${tone}` }, String(value)),
    h("div", { style: "font-size: 11px; color: var(--ink-500); margin-top:2px;" }, label)
  );
}

function emptyMetricCard(label, message) {
  return h(
    "div",
    { className: "card metric-card" },
    h("div", { className: "metric-label" }, label),
    h("div", { style: "margin-top:8px; color: var(--ink-500); font-size: 13px;" }, message)
  );
}

export function formatMoney(value) {
  if (value === undefined || value === null) return "—";
  // Presentation formatting ONLY — this never recomputes a figure the
  // backend didn't already return (Section 24: no parallel accounting
  // engine). `value` here is a Decimal-as-string from the backend.
  const num = Number(value);
  return Number.isFinite(num) ? num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : String(value);
}
