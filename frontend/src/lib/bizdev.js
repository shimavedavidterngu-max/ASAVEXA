import { PERMISSIONS, ROLE_PERMISSIONS } from "./permissions.js";

/** Business Development helpers. Money stays a string (exact decimals); previews use whole-cent BigInt arithmetic, never floats. The server always calculates the final figures. */
const has = (role, perm) => !!(ROLE_PERMISSIONS[role] && ROLE_PERMISSIONS[role].includes(perm));
export const canPrepare = (role) => has(role, PERMISSIONS.BD_PREPARE);
export const canApprove = (role) => has(role, PERMISSIONS.BD_APPROVE);
export const TABS = [["overview", "Overview"], ["accounts", "Accounts"], ["pipeline", "Pipeline"], ["targets", "Targets"], ["reports", "Reports"]];
export const OPEN_STAGES = ["LEAD", "QUALIFIED", "PROPOSAL", "NEGOTIATION"];
export const ACTIVE_STAGES = [...OPEN_STAGES, "WIN_PENDING"];
export const ACTIVITY_TYPES = ["CALL", "MEETING", "EMAIL", "NOTE"];
export const KINDS = ["PROSPECT", "CLIENT", "PARTNER"];

export const STATUS = {
  LEAD: { tone: "neutral", label: "Lead" }, QUALIFIED: { tone: "info", label: "Qualified" }, PROPOSAL: { tone: "info", label: "Proposal" }, NEGOTIATION: { tone: "warn", label: "Negotiation" },
  WIN_PENDING: { tone: "warn", label: "Win waiting for confirmation" }, WON: { tone: "pass", label: "Won" }, LOST: { tone: "fail", label: "Lost" },
  DRAFT: { tone: "neutral", label: "Draft" }, PENDING_APPROVAL: { tone: "warn", label: "Discount waiting for approval" }, APPROVED: { tone: "pass", label: "Approved" }, REJECTED: { tone: "fail", label: "Sent back" },
  SENT: { tone: "info", label: "Sent to client" }, ACCEPTED: { tone: "pass", label: "Accepted" }, DECLINED: { tone: "fail", label: "Declined" }, SUPERSEDED: { tone: "neutral", label: "Replaced" }, LAPSED: { tone: "neutral", label: "Lapsed" },
  SUBMITTED: { tone: "info", label: "Waiting for approval" }, ACTIVE: { tone: "info", label: "Active" }, ARCHIVED: { tone: "neutral", label: "Archived" }, RETIRED: { tone: "neutral", label: "Retired" },
  PROSPECT: { tone: "neutral", label: "Prospect" }, CLIENT: { tone: "pass", label: "Client" }, PARTNER: { tone: "info", label: "Partner" },
};
export const statusOf = (s) => STATUS[s] || { tone: "neutral", label: s || "—" };
export const FLAG_TEXT = { OVERDUE: "Past its expected close date", STALE: "No activity for a long time" };

export const money = (v) => {
  if (v == null || v === "") return "—";
  const m = /^(-?)(\d+)(?:\.(\d+))?$/.exec(String(v));
  return m ? `${m[1]}${m[2].replace(/\B(?=(\d{3})+(?!\d))/g, ",")}${m[3] ? "." + m[3] : ""}` : String(v);
};
export const isMoney = (v) => /^\d{1,15}(\.\d{1,2})?$/.test(String(v == null ? "" : v).trim());
export const isPositive = (v) => isMoney(v) && Number(String(v).trim()) > 0;
export const isRealDate = (s) => {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(s || "").trim());
  if (!m) return false;
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
  return d.getUTCFullYear() === +m[1] && d.getUTCMonth() === +m[2] - 1 && d.getUTCDate() === +m[3];
};
export const noteProblem = (n, what = "a reason", min = 3) => ((n || "").trim().length < min ? `Add ${what} (at least ${min} characters).` : null);
const isEmail = (e) => !e || (/^[^@\s]+@[^@\s]+$/.test(e));

// ---- accounts
export const emptyAccount = () => ({ id: "", name: "", kind: "PROSPECT", sector: "", country: "", notes: "", contact_name: "", contact_role: "", contact_email: "", contact_phone: "" });
export function accountProblem(f) {
  if ((f.name || "").trim().length < 2) return "Give the account a name (at least 2 characters).";
  if (!KINDS.includes(f.kind)) return "Choose prospect, client or partner.";
  const any = (f.contact_role || f.contact_email || f.contact_phone || "").trim();
  if (any && (f.contact_name || "").trim().length < 2) return "Give the contact a name, or clear the contact details.";
  if (!isEmail((f.contact_email || "").trim())) return "The contact email must look like name@example.com.";
  return null;
}
export const accountBody = (f) => ({ name: f.name.trim(), kind: f.kind, sector: (f.sector || "").trim(), country: (f.country || "").trim(), notes: (f.notes || "").trim(),
  contacts: (f.contact_name || "").trim() ? [{ name: f.contact_name.trim(), role: (f.contact_role || "").trim(), email: (f.contact_email || "").trim(), phone: (f.contact_phone || "").trim() }] : [] });
export const accountForm = (a) => { const c = (a.contacts || [])[0] || {}; return { id: a.id, name: a.name, kind: a.kind, sector: a.sector || "", country: a.country || "", notes: a.notes || "", contact_name: c.name || "", contact_role: c.role || "", contact_email: c.email || "", contact_phone: c.phone || "" }; };

// ---- opportunities
export const emptyOpp = (accountId = "") => ({ id: "", account_id: accountId, title: "", description: "", source: "", currency: "NGN", value: "", expected_close: "", stage: "LEAD" });
export function oppProblem(f, isNew) {
  if (isNew && !f.account_id) return "Choose the account.";
  if ((f.title || "").trim().length < 3) return "Give the opportunity a title (at least 3 characters).";
  if (isNew && !/^[A-Za-z]{3}$/.test((f.currency || "").trim())) return "The currency is a 3-letter code like NGN or USD.";
  if (!isPositive(f.value)) return "Enter the estimated value as a number more than zero (no commas, at most 2 decimals).";
  if (!isRealDate(f.expected_close)) return "Enter the expected close date like 2026-06-30.";
  return null;
}
export const oppBody = (f, isNew) => {
  const b = { title: f.title.trim(), description: (f.description || "").trim(), source: (f.source || "").trim(), value: f.value.trim(), expected_close: f.expected_close.trim() };
  return isNew ? { ...b, account_id: f.account_id, currency: f.currency.trim().toUpperCase(), stage: f.stage || "LEAD" } : b;
};
export const oppForm = (o) => ({ id: o.id, account_id: o.account_id, title: o.title, description: o.description || "", source: o.source || "", currency: o.currency, value: o.value, expected_close: o.expected_close, stage: o.stage });
export const emptyActivity = () => ({ type: "CALL", date: "", summary: "" });
export function activityProblem(f) {
  if (!ACTIVITY_TYPES.includes(f.type)) return "Choose the kind of activity.";
  if ((f.date || "").trim() && !isRealDate(f.date)) return "Enter the date like 2026-06-30, or leave it blank for today.";
  if ((f.summary || "").trim().length < 3) return "Say what happened (at least 3 characters).";
  return null;
}
export const activityBody = (f) => ({ type: f.type, ...((f.date || "").trim() ? { date: f.date.trim() } : {}), summary: f.summary.trim() });
export function oppMoves(o, role, userId) {
  const prep = canPrepare(role), appr = canApprove(role), open = OPEN_STAGES.includes(o.stage), active = ACTIVE_STAGES.includes(o.stage);
  const accepted = (o.proposals || []).some((p) => p.status === "ACCEPTED");
  return { edit: prep && open, move: prep && open, activity: prep && active, lost: prep && active, proposal: prep && open, requestWin: prep && open && accepted,
    decideWin: appr && o.stage === "WIN_PENDING" && o.win_requested_by !== userId, ownWin: appr && o.stage === "WIN_PENDING" && o.win_requested_by === userId, closed: !active };
}

// ---- proposals
export const emptyProposal = () => ({ id: "", items: [{ description: "", quantity: "1", unit_price: "" }], discount_pct: "0", valid_until: "", terms: "", evidence_ids: [] });
export const proposalForm = (p) => ({ id: p.id, items: p.items.map((i) => ({ description: i.description, quantity: i.quantity, unit_price: i.unit_price })), discount_pct: p.discount_pct, valid_until: p.valid_until, terms: p.terms || "", evidence_ids: (p.evidence || []).map((e) => e.evidence_id) });
export function proposalProblem(f) {
  if (!f.items.length) return "Add at least one line.";
  for (let i = 0; i < f.items.length; i++) {
    const it = f.items[i], n = i + 1;
    if ((it.description || "").trim().length < 2) return `Line ${n}: say what it is.`;
    if (!isPositive(it.quantity)) return `Line ${n}: the quantity must be a number more than zero.`;
    if (!isPositive(it.unit_price)) return `Line ${n}: the unit price must be a number more than zero (no commas).`;
  }
  const d = String(f.discount_pct == null || f.discount_pct === "" ? "0" : f.discount_pct).trim();
  if (!isMoney(d) || Number(d) >= 100) return "The discount is a percentage from 0 up to (not including) 100.";
  if (!isRealDate(f.valid_until)) return "Enter the date the proposal is valid until, like 2026-06-30.";
  return null;
}
export const proposalBody = (f) => ({ items: f.items.map((i) => ({ description: i.description.trim(), quantity: i.quantity.trim(), unit_price: i.unit_price.trim() })), discount_pct: String(f.discount_pct === "" ? "0" : f.discount_pct).trim(), valid_until: f.valid_until.trim(), terms: (f.terms || "").trim(), evidence_ids: f.evidence_ids || [] });
const hundredths = (v) => { const [a, b = ""] = String(v).trim().split("."); return BigInt(a) * 100n + BigInt((b + "00").slice(0, 2)); };
const fmtCents = (c) => `${c / 100n}.${String(c % 100n).padStart(2, "0")}`;
/** A preview only (whole-cent BigInt, half-up like the server). Returns null while the lines are incomplete. */
export function proposalPreview(f) {
  if (proposalProblem({ ...f, valid_until: "2000-01-01" })) return null;
  let sub = 0n;
  for (const it of f.items) sub += (hundredths(it.quantity) * hundredths(it.unit_price) + 50n) / 100n;
  const pct = hundredths(f.discount_pct === "" ? "0" : f.discount_pct), disc = (sub * pct + 5000n) / 10000n;
  return { subtotal: fmtCents(sub), discount: fmtCents(disc), total: fmtCents(sub - disc) };
}
export function proposalMoves(p, o, role, userId) {
  const prep = canPrepare(role), appr = canApprove(role), open = OPEN_STAGES.includes(o.stage);
  return { edit: prep && open && (p.status === "DRAFT" || p.status === "REJECTED"), submit: prep && open && p.status === "DRAFT", decide: appr && open && p.status === "PENDING_APPROVAL" && p.submitted_by !== userId,
    own: appr && open && p.status === "PENDING_APPROVAL" && p.submitted_by === userId, send: prep && open && p.status === "APPROVED", respond: prep && open && p.status === "SENT" };
}

// ---- targets, policy, reports
export const emptyTarget = () => ({ name: "", start: "", end: "", currency: "NGN", amount: "" });
export function targetProblem(f) {
  if ((f.name || "").trim().length < 3) return "Give the target a name (at least 3 characters).";
  if (!isRealDate(f.start) || !isRealDate(f.end)) return "Enter the start and end dates like 2026-01-01.";
  if (f.end < f.start) return "The end date cannot be before the start date.";
  if (!/^[A-Za-z]{3}$/.test((f.currency || "").trim())) return "The currency is a 3-letter code like NGN or USD.";
  if (!isPositive(f.amount)) return "Enter the target amount, more than zero.";
  return null;
}
export const targetBody = (f) => ({ name: f.name.trim(), start: f.start.trim(), end: f.end.trim(), currency: f.currency.trim().toUpperCase(), amount: f.amount.trim() });
export const policyForm = (p) => ({ discount_limit_pct: p.discount_limit_pct, stale_days: String(p.stale_days), ...Object.fromEntries(Object.entries(p.probabilities).map(([k, v]) => [`p_${k}`, String(v)])) });
export function policyProblem(f) {
  if (!isMoney(f.discount_limit_pct) || Number(f.discount_limit_pct) > 100) return "The discount limit is a percentage from 0 to 100.";
  if (!/^\d{1,3}$/.test(String(f.stale_days).trim()) || +f.stale_days < 1 || +f.stale_days > 365) return "Stale days is a whole number from 1 to 365.";
  let last = -1;
  for (const s of ACTIVE_STAGES) {
    const v = String(f[`p_${s}`]).trim();
    if (!/^\d{1,3}$/.test(v) || +v > 100) return `The ${statusOf(s).label} probability is a whole number from 0 to 100.`;
    if (+v < last) return "Probabilities must not go down as a deal moves forward.";
    last = +v;
  }
  return null;
}
export const policyBody = (f) => ({ discount_limit_pct: f.discount_limit_pct.trim(), stale_days: +f.stale_days, probabilities: Object.fromEntries(ACTIVE_STAGES.map((s) => [s, +String(f[`p_${s}`]).trim()])) });
export const reportProblem = (f) => (!/^[A-Za-z]{3}$/.test((f.currency || "").trim()) ? "Choose the currency to report on." : (f.title || "").trim().length < 3 ? "Give the report a title." : null);
export function reportMoves(r, role, userId) {
  const prep = canPrepare(role), appr = canApprove(role);
  return { submit: prep && (r.status === "DRAFT" || r.status === "REJECTED"), decide: appr && r.status === "SUBMITTED" && r.submitted_by !== userId, own: appr && r.status === "SUBMITTED" && r.submitted_by === userId, exportable: r.status === "APPROVED" };
}
