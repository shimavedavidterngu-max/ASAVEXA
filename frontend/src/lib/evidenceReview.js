/** Pure helpers for the Evidence Review page. No DOM, no network. The server decides everything; this only words and orders it. */

export const REPORT_CHOICES = [["income_statement", "Income statement"], ["balance_sheet", "Balance sheet"]];

export const VERDICT_INFO = {
  SUPPORTED: { tone: "pass", label: "Fully supported" },
  PARTLY_SUPPORTED: { tone: "warn", label: "Partly supported" },
  NOT_SUPPORTED: { tone: "fail", label: "Not supported" },
  CONTRADICTED: { tone: "fail", label: "Does not tie to its journals" },
  NOTHING_TO_REVIEW: { tone: "neutral", label: "Nothing to review" },
};
export const verdictInfo = (v) => VERDICT_INFO[v] || { tone: "neutral", label: v || "—" };

export const ISSUE_TEXT = {
  MISSING: "No evidence", UNVERIFIED: "Not yet verified", CONFLICT: "Evidence has a problem", STALE: "Evidence expired",
  WRONG_TYPE: "Wrong kind of evidence", SELF_VERIFIED: "Verified by its own uploader", DOCUMENT_REUSED: "Same document used for several journals",
};
export const issueText = (k) => ISSUE_TEXT[k] || String(k || "—");

export const LINK_TEXT = { RECORDED: "Linked by a person", INFERRED: "Matched by reference only", MISSING: "No link" };
export const linkText = (k) => LINK_TEXT[k] || String(k || "—");

export const CASE_STATUS = {
  OPEN: { tone: "fail", label: "Open: action needed" },
  ACTION_PLANNED: { tone: "warn", label: "Action planned" },
  ACTION_DONE: { tone: "warn", label: "Done: waiting for independent check" },
  VERIFIED: { tone: "pass", label: "Verified" },
  REOPENED: { tone: "fail", label: "Reopened: gaps returned" },
};
export const caseStatus = (s) => CASE_STATUS[s] || { tone: "neutral", label: s || "—" };

/** The gaps the baseline and re-check count: journals with problems plus figures that do not tie. */
export const gapCount = (review) => (review && review.metrics ? review.metrics.journals_with_gaps + review.metrics.tie_failures : 0);

/** Every problem journal in one list, each once per problem kind, for the table. */
export function problemRows(review) {
  if (!review) return [];
  const rows = [];
  for (const key of ["missing", "unverified", "conflicting", "stale"]) for (const i of review[key] || []) rows.push({ ...i, group: key });
  for (const t of review.tie_failures || []) rows.push({ kind: "TIE", journal_number: t.label || t.account || "Figure", detail: t.detail || "Does not tie to its journals.", group: "tie" });
  return rows;
}

/** Can this review become a case? Only with gaps, and only for someone allowed to manage findings. */
export const canOpenCase = (review, mayManage, busy) => !!(review && gapCount(review) > 0 && mayManage && !busy);

/** What the next person has to do on a case, in plain words. */
export function nextStep(c, me) {
  if (!c) return "";
  switch (c.status) {
    case "OPEN": case "REOPENED": return "Plan the action: say what will be done and who owns it.";
    case "ACTION_PLANNED": return "The owner does the work, then records it as done.";
    case "ACTION_DONE": return me && (me === c.completed_by || me === c.owner) ? "Waiting for someone else to verify. You did or own this work, so you cannot." : "An independent person re-measures the figure and verifies the outcome.";
    case "VERIFIED": return "Finished. Re-check later to confirm the gaps have not come back.";
    default: return "";
  }
}

export const canVerify = (c, me, mayVerify) => !!(c && c.status === "ACTION_DONE" && mayVerify && me !== c.completed_by && me !== c.owner);

export const shortId = (id) => (id ? String(id).slice(0, 8) : "—");

export const RESIDUAL_LEVELS = [["LOW", "Low"], ["MEDIUM", "Medium"], ["HIGH", "High"]];
export const residualLevelText = (l) => (RESIDUAL_LEVELS.find((x) => x[0] === l) || [null, "Not rated"])[1];
export const RESIDUAL_TONE = { LOW: "pass", MEDIUM: "warn", HIGH: "fail" };

const whole = (v) => (v === "" || v == null ? null : /^\d+$/.test(String(v).trim()) ? Number(String(v).trim()) : NaN);

/** The body sent to POST /cases/{id}/verify, from the form. Returns { body } or { problem } so the page can say what to fix before any request is made. */
export function verifyPayload(f = {}) {
  const residual_risk = (f.residual_risk || "").trim(), reopen_criteria = (f.reopen_criteria || "").trim();
  if (!residual_risk) return { problem: "Say what residual risk remains." };
  if (!reopen_criteria) return { problem: "Say when this case should be reopened." };
  if (!f.residual_level) return { problem: "Rate the residual risk: low, medium or high." };
  const tol = whole(f.reopen_if_gaps_above), days = whole(f.recheck_after_days);
  if (Number.isNaN(tol)) return { problem: "The reopen threshold must be a whole number (0 means reopen on any gap)." };
  if (Number.isNaN(days) || days === 0) return { problem: "The re-check interval must be a whole number of days, or empty for no schedule." };
  return { body: { residual_risk, reopen_criteria, note: (f.vnote || "").trim(), residual_level: f.residual_level, reopen_if_gaps_above: tol == null ? 0 : tol, recheck_after_days: days } };
}

/** A verified case whose scheduled re-check date has come. */
export const recheckDue = (c) => !!(c && c.status === "VERIFIED" && c.recheck_due_now);

export const MEASUREMENT_TEXT = { BASELINE: "Baseline", REJECTED_ATTEMPT: "Rejected attempt", VERIFIED: "Verified", RECHECK: "Re-check" };
export const measurementText = (k) => MEASUREMENT_TEXT[k] || String(k || "—");
