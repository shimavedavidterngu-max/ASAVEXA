/** Pure helpers for the Standards Registry page. No DOM, no network. The server decides states and who may approve; this only words them. */

export const STATE_INFO = {
  VERIFIED: { tone: "pass", label: "Verified" },
  REVIEW_OVERDUE: { tone: "warn", label: "Review overdue" },
  NOT_YET_EFFECTIVE: { tone: "neutral", label: "Not yet effective" },
  UNVERIFIED: { tone: "fail", label: "Unverified" },
};
export const stateInfo = (s) => STATE_INFO[s] || { tone: "neutral", label: s || "—" };

export const STATUS_INFO = {
  DRAFT: { tone: "neutral", label: "Draft" }, UNDER_REVIEW: { tone: "warn", label: "Under review" }, APPROVED: { tone: "pass", label: "Approved" },
  SUPERSEDED: { tone: "neutral", label: "Superseded" }, WITHDRAWN: { tone: "fail", label: "Withdrawn" },
};
export const statusInfo = (s) => STATUS_INFO[s] || { tone: "neutral", label: s || "—" };

export const EMPTY_FORM = { framework: "", jurisdiction: "", title: "", url: "", authority: "", version: "", effective_from: "", review_by: "", summary: "" };

/** First problem with the add-source form, or null. The server checks again; this only saves a round trip. */
export function formProblem(f) {
  if (!f.framework) return "Choose a framework.";
  if (!f.title.trim()) return "Give the source a title.";
  if (!/^https:\/\/[^\s/]+\.[^\s/]+/.test(f.url.trim())) return "The source link must be a full https:// address.";
  if (!f.authority.trim()) return "Say who issued it.";
  if (!f.version.trim()) return "Give its version.";
  if (!/^\d{4}-\d{2}-\d{2}$/.test(f.effective_from)) return "Effective date must look like 2026-01-01.";
  if (!/^\d{4}-\d{2}-\d{2}$/.test(f.review_by)) return "Review-by date must look like 2027-01-01.";
  if (f.review_by <= f.effective_from) return "The review-by date must be after the effective date.";
  return null;
}

/** What a person may do to a source: the server still enforces permissions and independence. */
export function actionsFor(source, me, canPrepare, canApprove) {
  const out = [];
  if (!source) return out;
  if (source.status === "DRAFT" && canPrepare) out.push("submit");
  if (source.status === "UNDER_REVIEW" && canApprove && me !== source.created_by && me !== source.submitted_by) { out.push("approve"); out.push("send-back"); }
  if (["APPROVED", "UNDER_REVIEW", "DRAFT"].includes(source.status) && canApprove) out.push("withdraw");
  return out;
}

export const independentReviewNote = (source, me) => (source && source.status === "UNDER_REVIEW" && (me === source.created_by || me === source.submitted_by) ? "You added or submitted this source, so someone else must review it." : "");
