import { PERMISSIONS, ROLE_PERMISSIONS } from "./permissions.js";
import { fmt, isRealDate, noteProblem, words } from "./treasury.js";

/**
 * Company secretarial helpers (records only; no law is checked and no registry is contacted). No DOM, no network.
 * The server enforces every rule. These check input early, word things, and hide buttons that could not work.
 */
export { fmt, isRealDate, noteProblem, words };
const has = (role, perm) => !!(ROLE_PERMISSIONS[role] && ROLE_PERMISSIONS[role].includes(perm));
export const canRead = (role) => has(role, PERMISSIONS.AUDIT_READ);
export const canPrepare = (role) => has(role, PERMISSIONS.SEC_PREPARE);
export const canApprove = (role) => has(role, PERMISSIONS.SEC_APPROVE);

export const TABS = [["overview", "Overview"], ["meetings", "Meetings"], ["resolutions", "Resolutions"], ["filings", "Filings"]];
export const MEETING_TEXT = { BOARD: "Board meeting", COMMITTEE: "Committee meeting", ANNUAL_GENERAL: "Annual general meeting", GENERAL: "General meeting", OTHER: "Other meeting" };
export const RESOLUTION_TEXT = { ORDINARY: "Ordinary resolution", SPECIAL: "Special resolution", WRITTEN: "Written resolution (no meeting)" };
export const FILING_TEXT = { ANNUAL_RETURN: "Annual return", ACCOUNTS: "Accounts", CHANGE_OF_DIRECTORS: "Change of directors", CHANGE_OF_ADDRESS: "Change of address", SHARE_CHANGE: "Share change", TAX_RETURN: "Tax return", LICENCE_RENEWAL: "Licence renewal", OTHER: "Other filing" };
export const OUTCOME_TEXT = { PASSED: "Passed (more votes for than against)", FAILED: "Failed" };
export const STATUS = {
  SCHEDULED: { tone: "info", label: "Scheduled" }, HELD: { tone: "warn", label: "Minutes waiting for approval" }, MINUTES_APPROVED: { tone: "pass", label: "Minutes approved" }, CANCELLED: { tone: "neutral", label: "Cancelled" },
  PROPOSED: { tone: "warn", label: "Waiting for a decision" }, PASSED: { tone: "pass", label: "Passed" }, FAILED: { tone: "fail", label: "Failed" }, WITHDRAWN: { tone: "neutral", label: "Withdrawn" },
  OPEN: { tone: "warn", label: "Open" }, FILED: { tone: "info", label: "Filed: waiting for confirmation" }, CONFIRMED: { tone: "pass", label: "Confirmed" },
};
export const statusOf = (s) => STATUS[s] || { tone: "neutral", label: s ? words(s) : "—" };
export const ATTENTION_TONE = { FILINGS_OVERDUE: "fail", FILINGS_DUE_SOON: "warn", FILINGS_TO_CONFIRM: "info", MEETINGS_TO_RECORD: "warn", MINUTES_TO_APPROVE: "info", RESOLUTIONS_TO_DECIDE: "info" };
export const who = (id, me) => (!id ? "—" : id === me ? "You" : String(id).slice(0, 8));

const clean = (v) => String(v == null ? "" : v).trim();
const first = (...p) => p.find(Boolean) || "";
const body = (b, ...problems) => { const p = first(...problems); return p ? { problem: p } : { body: b }; };
const dateProblem = (v, what) => (isRealDate(clean(v)) ? "" : `${what} must be a real date written YYYY-MM-DD.`);
const textProblem = (v, what, min) => (clean(v).length >= min ? "" : `${what} needs at least ${min} characters.`);
const countProblem = (v, what) => (/^\d{1,6}$/.test(clean(v)) ? "" : `${what} must be a whole number (use 0 for none).`);
const ev = (f) => (clean(f.evidence_id) ? [clean(f.evidence_id)] : []);

export const EMPTY = {
  meeting: { kind: "BOARD", title: "", held_on: "", location: "", agenda: "" },
  minutes: { attendees: "", minutes: "", evidence_id: "" },
  resolution: { kind: "ORDINARY", meeting_id: "", text: "" },
  decide: { votes_for: "", votes_against: "", abstentions: "0", outcome: "PASSED", note: "" },
  filing: { kind: "ANNUAL_RETURN", title: "", authority: "", due_on: "", owner_name: "" },
  filed: { filed_on: "", receipt_ref: "", evidence_id: "" },
  confirm: { note: "" },
};

export const meetingPayload = (f) => body({ kind: f.kind, title: clean(f.title), held_on: clean(f.held_on), location: clean(f.location), agenda: clean(f.agenda) },
  textProblem(f.title, "The title", 5), dateProblem(f.held_on, "The meeting date"), textProblem(f.location, "The location", 2), textProblem(f.agenda, "The agenda", 10));
export const minutesPayload = (f) => body({ attendees: clean(f.attendees), minutes: clean(f.minutes), evidence_ids: ev(f) }, textProblem(f.attendees, "Who attended", 3), textProblem(f.minutes, "The minutes", 20));
export const resolutionPayload = (f) => body({ kind: f.kind, text: clean(f.text), ...(f.kind === "WRITTEN" ? {} : { meeting_id: f.meeting_id }) },
  textProblem(f.text, "The resolution", 20), f.kind !== "WRITTEN" && !f.meeting_id ? "Choose the meeting this resolution is put to." : "");
export const decidePayload = (f) => {
  const p = first(countProblem(f.votes_for, "Votes for"), countProblem(f.votes_against, "Votes against"), countProblem(f.abstentions, "Abstentions"), textProblem(f.note, "A decision note", 10));
  if (p) return { problem: p };
  const vf = Number(clean(f.votes_for)), va = Number(clean(f.votes_against)), ab = Number(clean(f.abstentions));
  if (vf + va + ab === 0) return { problem: "Record how many voted. At least one vote or abstention is needed." };
  if (f.outcome === "PASSED" && vf <= va) return { problem: "A resolution cannot be recorded as passed unless more votes were for than against." };
  return { body: { votes_for: vf, votes_against: va, abstentions: ab, outcome: f.outcome, note: clean(f.note) } };
};
export const filingPayload = (f) => body({ kind: f.kind, title: clean(f.title), authority: clean(f.authority), due_on: clean(f.due_on), owner_name: clean(f.owner_name) },
  textProblem(f.title, "The title", 5), textProblem(f.authority, "The authority or registry", 2), dateProblem(f.due_on, "The due date"), textProblem(f.owner_name, "The owner", 2));
export const filedPayload = (f) => body({ filed_on: clean(f.filed_on), receipt_ref: clean(f.receipt_ref), evidence_ids: ev(f) }, dateProblem(f.filed_on, "The date it was filed"), textProblem(f.receipt_ref, "The receipt or reference", 3));
export const confirmPayload = (f) => body({ note: clean(f.note) }, textProblem(f.note, "A confirmation note", 10));
export const policyForm = (p) => ({ due_soon_days: String(p.due_soon_days) });
export function policyPayload(f) {
  const t = clean(f.due_soon_days);
  if (!(/^\d{1,2}$/.test(t) && Number(t) >= 1 && Number(t) <= 90)) return { problem: "The days before a filing is due soon is a whole number from 1 to 90." };
  return { body: { due_soon_days: Number(t) } };
}
export const minNote = { cancel: 10, withdraw: 10 };

// ---- who sees which button ----
export const canRecordMinutes = (m, role) => canPrepare(role) && m.status === "SCHEDULED";
export const canApproveMinutes = (m, role, me) => canApprove(role) && m.status === "HELD" && m.minutes_by !== me;
export const canCancelMeeting = (m, role) => canApprove(role) && m.status === "SCHEDULED";
export const canDecide = (r, role, me) => canApprove(role) && r.can_decide && r.proposed_by !== me;
export const canWithdrawResolution = (r, role) => canApprove(role) && r.status === "PROPOSED";
export const canFile = (f, role) => canPrepare(role) && f.status === "OPEN";
export const canConfirm = (f, role, me) => canApprove(role) && f.status === "FILED" && f.filed_by !== me;
export const canWithdrawFiling = (f, role) => canApprove(role) && f.status === "OPEN";
export const ownWorkText = (what) => `You ${what}, so a different person must decide it.`;
