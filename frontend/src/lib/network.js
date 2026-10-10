/** Pure helpers for the ASAVEXA Network page. No DOM, no network. */

export const SCOPE_TEXT = {
  IDENTITY: "Who the organisation is", FINANCIAL_HISTORY: "Financial history (totals by period)", EVIDENCE_QUALITY: "How well transactions are supported by evidence",
  GOVERNANCE: "Controls, findings and who does what", REPORTING: "Reports and period closes", AUDIT_TRAIL: "Audit trail summary",
};
export const STATUS_TONE = { ACTIVE: "pass", EXPIRED: "warn", REVOKED: "neutral", PENDING: "info", ACCEPTED: "pass", CANCELLED: "neutral" };
export const DEFAULT_TYPE_TEXT = { BUSINESS: "Business or NGO", ACCOUNTANT: "Accountant / accounting firm", AUDITOR: "Auditor", BANK: "Bank or lender", INVESTOR: "Investor", DONOR: "Donor or funder", REGULATOR: "Regulator" };
export const typeText = (t, types) => ((types && types[t]) || DEFAULT_TYPE_TEXT[t] || t || "—");

export const emptyInviteForm = () => ({ counterparty_type: "", purpose: "", scopes: ["IDENTITY", "FINANCIAL_HISTORY", "EVIDENCE_QUALITY"], include_detail: false, closed_periods_only: true,
  date_from: "", date_to: "", connection_days: "90", invite_days: "14", note: "" });

const whole = (v) => { const t = String(v == null ? "" : v).trim(); return /^\d+$/.test(t) ? parseInt(t, 10) : NaN; };

export function grantBody(f) {
  const g = { scopes: [...(f.scopes || [])], include_detail: !!f.include_detail, closed_periods_only: f.closed_periods_only !== false };
  if ((f.date_from || "").trim()) g.date_from = f.date_from.trim();
  if ((f.date_to || "").trim()) g.date_to = f.date_to.trim();
  return g;
}

export function inviteProblem(f, allowedTypes) {
  if (!f.counterparty_type) return "Choose who you are connecting with.";
  if (allowedTypes && !allowedTypes.includes(f.counterparty_type)) return "That kind of organisation cannot be connected to yours.";
  if ((f.purpose || "").trim().length < 3) return "Say what the connection is for (for example 'Statutory audit 2026').";
  if (!(f.scopes || []).length) return "Choose at least one kind of information.";
  if (Number.isNaN(whole(f.connection_days)) || whole(f.connection_days) < 1 || whole(f.connection_days) > 365) return "A connection can last from 1 to 365 days.";
  if (Number.isNaN(whole(f.invite_days)) || whole(f.invite_days) < 1 || whole(f.invite_days) > 30) return "An invitation stays open for 1 to 30 days.";
  if (f.date_from && f.date_to && f.date_from > f.date_to) return "The start date cannot be after the end date.";
  return null;
}

export const inviteBody = (f) => ({ counterparty_type: f.counterparty_type, purpose: (f.purpose || "").trim(), grant: grantBody(f), invite_days: whole(f.invite_days), connection_days: whole(f.connection_days), note: (f.note || "").trim() });

/** The business may share less than a request asked for. Returns the grant to send, or null (= accept exactly as asked). */
export function acceptGrant(preview, chosenScopes, detail, closedOnly) {
  const g = preview.grant, scopes = g.scopes.filter((s) => chosenScopes.includes(s));
  const same = scopes.length === g.scopes.length && (!!detail === !!g.include_detail || !g.include_detail) && (closedOnly !== false) === !!g.closed_periods_only;
  return same ? null : { scopes, include_detail: !!detail && !!g.include_detail, closed_periods_only: closedOnly !== false };
}

export function grantLine(g) {
  if (!g) return "";
  return `${g.scopes.map((s) => SCOPE_TEXT[s] || s).join("; ")}. ${g.include_detail ? "Includes line-level detail." : "Summary only."} ${g.closed_periods_only ? "Finished periods only." : "Includes unfinished periods."} ${g.date_from} to ${g.date_to}.`;
}

export const roleLine = (c) => (c.role === "PROVIDER" ? `You share your information with ${c.counterparty.name}` : `${c.counterparty.name} shares its information with you`);
export const canOpen = (c) => c.role === "VIEWER" && c.status === "ACTIVE";
export const canChange = (c) => c.role === "PROVIDER" && c.status === "ACTIVE";
export const canEnd = (c) => c.status === "ACTIVE";
export const daysLeft = (c, now = Date.now()) => Math.max(0, Math.ceil((new Date(c.expires_at).getTime() - now) / 86400000));

/** Counts of active connections per kind, for the map. */
export function mapCounts(connections, types) {
  const out = Object.fromEntries(Object.keys(types || DEFAULT_TYPE_TEXT).map((t) => [t, 0]));
  for (const c of connections || []) if (c.status === "ACTIVE" && c.counterparty.type in out) out[c.counterparty.type] += 1;
  return out;
}
