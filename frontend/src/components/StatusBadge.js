import { h } from "../lib/vdom.js";

/**
 * Maps a backend status string to a badge tone. Every value here is a
 * real enum value from the backend (ControlResult, FindingStatus,
 * RemediationStatus, JournalStatus, PeriodStatus, ReconciliationStatus,
 * BankTransactionStatus, PeriodCloseStatus, EvidenceStatus) — nothing
 * invented. Unknown values fall back to "neutral" rather than guessing.
 */
export const STATUS_TONE = {
  // ControlResult
  PASS: "pass", FAIL: "fail", WARNING: "warn", REQUIRES_REVIEW: "warn", NOT_APPLICABLE: "neutral",
  // FindingStatus
  OPEN: "fail", UNDER_REVIEW: "warn", REMEDIATION_REQUIRED: "warn",
  RESOLVED: "info", VERIFIED: "pass", CLOSED: "neutral",
  // RemediationStatus
  PLANNED: "neutral", IN_PROGRESS: "warn", COMPLETED: "info",
  // JournalStatus
  DRAFT: "neutral", POSTED: "pass", REVERSED: "neutral",
  // PeriodStatus / PeriodCloseStatus
  LOCKED: "info", READY_FOR_CLOSE: "pass", CONTROLS_FAILED: "fail", REJECTED: "fail",
  // ReconciliationStatus / BankTransactionStatus
  SUBMITTED: "warn", RECONCILED: "pass", MATCHED: "info",
  REVIEW_REQUIRED: "warn", UNMATCHED: "fail", APPROVED: "pass",
  // EvidenceStatus
  UPLOADED: "neutral", INCOMPLETE: "warn", DUPLICATE: "warn",
  CONFLICTING: "fail", EXPIRED: "fail",
};

export function StatusBadge({ status, label }) {
  const tone = STATUS_TONE[status] || "neutral";
  return h("span", { className: `badge badge-${tone}` }, label || humanize(status));
}

function humanize(status) {
  if (!status) return "Unknown";
  return status.replace(/_/g, " ").toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());
}
