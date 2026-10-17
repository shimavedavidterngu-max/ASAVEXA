import { PERMISSIONS } from "./permissions.js";
import { has, canRead, clean, first, dateProblem, textProblem, amt, wholeProblem, mkStatus, fmt, isRealDate, noteProblem, words } from "./wsCommon.js";

/** Data governance helpers (a register of data assets, reviews and time-limited access grants; holds no data and enforces no access). No DOM, no network. */
export { canRead, fmt, isRealDate, noteProblem, words };
export const canPrepare = (role) => has(role, PERMISSIONS.DG_PREPARE);
export const canApprove = (role) => has(role, PERMISSIONS.DG_APPROVE);
export const TABS = [["overview", "Overview"], ["assets", "Assets"]];
export const CLASSES = ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"];
export const statusOf = mkStatus({
  PROPOSED: { tone: "warn", label: "Waiting for a decision" }, APPROVED: { tone: "pass", label: "Approved" }, REJECTED: { tone: "neutral", label: "Rejected" }, RETIRED: { tone: "neutral", label: "Retired" },
  CONFIRMED: { tone: "pass", label: "Confirmed" }, REVOKED: { tone: "neutral", label: "Revoked" }, ACTIVE: { tone: "pass", label: "Active" }, EXPIRING: { tone: "warn", label: "Expiring soon" }, EXPIRED: { tone: "warn", label: "Expired" }, NOT_YET_ACTIVE: { tone: "info", label: "Not yet active" },
});
export const ATTENTION_TONE = { ASSETS_TO_APPROVE: "info", GRANTS_TO_DECIDE: "info", REVIEWS_TO_CONFIRM: "info", REVIEWS_OVERDUE: "warn", GRANTS_EXPIRING_SOON: "warn", TOO_MANY_GRANTS: "warn" };
export const EMPTY = {
  asset: { name: "", owner_ref: "", classification: "INTERNAL", personal_data: "NO", retention_months: "", review_every_months: "", description: "" },
  review: { review_date: "", outcome: "" },
  grant: { person_ref: "", access_level: "READ", purpose: "", starts_on: "", expires_on: "" },
};
export function assetPayload(f) {
  const p = first(textProblem(f.name, "The name", 3), textProblem(f.owner_ref, "The owner reference", 2), CLASSES.includes(clean(f.classification)) ? "" : "Choose a classification.", ["YES", "NO"].includes(clean(f.personal_data)) ? "" : "Say whether it holds personal data.",
    wholeProblem(f.retention_months, "The retention period in months", 1, 1200), wholeProblem(f.review_every_months, "The review interval in months", 1, 60), textProblem(f.description, "The description", 10));
  if (p) return { problem: p };
  return { body: { name: clean(f.name), owner_ref: clean(f.owner_ref), classification: clean(f.classification), personal_data: clean(f.personal_data), retention_months: Number(clean(f.retention_months)), review_every_months: Number(clean(f.review_every_months)), description: clean(f.description) } };
}
export function reviewPayload(f) {
  const p = first(dateProblem(f.review_date, "The review date"), textProblem(f.outcome, "The outcome", 10));
  return p ? { problem: p } : { body: { review_date: clean(f.review_date), outcome: clean(f.outcome) } };
}
const days = (a, b) => Math.round((Date.UTC(...b.split("-").map((x, i) => (i === 1 ? Number(x) - 1 : Number(x)))) - Date.UTC(...a.split("-").map((x, i) => (i === 1 ? Number(x) - 1 : Number(x))))) / 86400000);
export function grantPayload(f, sel) {
  const cls = sel && sel.asset ? sel.asset.classification : "INTERNAL", s = clean(f.starts_on), e = clean(f.expires_on);
  const p = first(textProblem(f.person_ref, "The person reference", 2), ["READ", "WRITE"].includes(clean(f.access_level)) ? "" : "Choose an access level.", textProblem(f.purpose, "The purpose", 10), dateProblem(s, "The start date"), dateProblem(e, "The expiry date"),
    isRealDate(s) && isRealDate(e) && e < s ? "The expiry date cannot be before the start date." : "",
    isRealDate(s) && isRealDate(e) && e >= s && days(s, e) > (cls === "RESTRICTED" ? 366 : 1096) ? `Access to a ${cls} asset can last at most ${cls === "RESTRICTED" ? "one year" : "three years"}.` : "");
  return p ? { problem: p } : { body: { person_ref: clean(f.person_ref), access_level: clean(f.access_level), purpose: clean(f.purpose), starts_on: s, expires_on: e } };
}
export function settingPayload(f) {
  const p = first(wholeProblem(f.expiry_warning_days, "The warning days", 1, 365), wholeProblem(f.max_restricted_grants, "The most grants on a restricted asset", 1, 1000));
  return p ? { problem: p } : { body: { expiry_warning_days: Number(clean(f.expiry_warning_days)), max_restricted_grants: Number(clean(f.max_restricted_grants)) } };
}
export const canDecideAsset = (a, role, me) => canApprove(role) && a.status === "PROPOSED" && a.proposed_by !== me;
export const canReview = (a, role) => canPrepare(role) && a.status === "APPROVED";
export const canGrant = (a, role) => canPrepare(role) && a.status === "APPROVED";
export const canDecideReview = (a, r, role, me) => canApprove(role) && a.status === "APPROVED" && r.status === "PROPOSED" && r.proposed_by !== me;
export const canDecideGrant = (a, g, role, me) => canApprove(role) && a.status === "APPROVED" && g.status === "PROPOSED" && g.proposed_by !== me;
export const canRevoke = (a, g, role) => canApprove(role) && a.status === "APPROVED" && g.status === "APPROVED";
export const canRetire = (a, role) => canApprove(role) && a.status === "APPROVED" && a.active_grants === 0 && a.pending_grants === 0 && a.pending_reviews === 0 && !(a.grants || []).some((g) => g.state === "NOT_YET_ACTIVE");
export const ownText = "You proposed this, so a different person must decide it.";
