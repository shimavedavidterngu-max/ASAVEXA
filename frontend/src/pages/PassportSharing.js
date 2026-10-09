import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState } from "../components/DataState.js";
import { allowed } from "../components/PermissionGate.js";
import { PERMISSIONS } from "../lib/permissions.js";
import { fmtWhen } from "./Passport.js";

/**
 * Permissioned sharing: Passport -> Share -> recipient -> information -> date range ->
 * permissions -> generate secure access. Pure render function; app.js owns the wizard
 * state and every API call. Nothing here decides what a recipient may see: the server
 * builds the snapshot from exactly what is chosen here and enforces it.
 */

export const STEPS = ["Recipient", "Information", "Date range", "Permissions", "Review"];

export const RECIPIENT_TYPES = [
  ["BANK", "Bank / lender"], ["AUDITOR", "Auditor"], ["INVESTOR", "Investor"],
  ["REGULATOR", "Regulator"], ["DONOR", "Donor / grant-maker"], ["OTHER", "Other"],
];

export const SCOPE_OPTIONS = [
  ["IDENTITY", "Identity", "Legal entity, ownership and structure"],
  ["FINANCIAL_HISTORY", "Financial history", "Verified figures for the periods in the date range"],
  ["EVIDENCE_QUALITY", "Evidence quality", "How well the figures are supported by evidence"],
  ["GOVERNANCE", "Governance", "Controls, findings and approvals"],
  ["REPORTING", "Reporting", "Reporting framework and statements"],
  ["AUDIT_TRAIL", "Audit trail", "Who did what, and when"],
];

/** Starting suggestions for each recipient type, so "Give Bank X my last three years" is two clicks. */
export const RECIPIENT_DEFAULTS = {
  BANK: { scopes: ["IDENTITY", "FINANCIAL_HISTORY", "EVIDENCE_QUALITY"], preset: "3y", closed_periods_only: true },
  AUDITOR: { scopes: ["IDENTITY", "FINANCIAL_HISTORY", "EVIDENCE_QUALITY", "GOVERNANCE", "AUDIT_TRAIL"], preset: "1y", closed_periods_only: false },
  INVESTOR: { scopes: ["IDENTITY", "FINANCIAL_HISTORY", "EVIDENCE_QUALITY", "REPORTING"], preset: "3y", closed_periods_only: true },
};

export const PRESETS = [["1y", "Last year"], ["3y", "Last 3 years"], ["5y", "Last 5 years"], ["custom", "Custom dates"]];

function iso(d) { return d.toISOString().slice(0, 10); }

/** Pure: the date range a preset means, ending at `today` (a Date). */
export function presetRange(preset, today) {
  const years = { "1y": 1, "3y": 3, "5y": 5 }[preset];
  if (!years) return null;
  const end = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate()));
  let start = new Date(Date.UTC(end.getUTCFullYear() - years, end.getUTCMonth(), end.getUTCDate()));
  if (start.getUTCMonth() !== end.getUTCMonth()) start = new Date(Date.UTC(end.getUTCFullYear() - years, end.getUTCMonth() + 1, 0)); // 29 Feb
  // a range that starts the day after the same date a year ago, so "last year" is a full year
  start = new Date(start.getTime() + 86400000);
  return { date_from: iso(start), date_to: iso(end) };
}

export function newWizard(today = new Date()) {
  const r = presetRange("3y", today);
  return {
    step: 0, recipient_name: "", recipient_type: "BANK", recipient_email: "", purpose: "",
    scopes: [...RECIPIENT_DEFAULTS.BANK.scopes], include_detail: false,
    preset: "3y", date_from: r.date_from, date_to: r.date_to,
    allow_download: false, closed_periods_only: true, expires_in_days: 30,
  };
}

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/** Pure: a plain-English problem with the given step, or null. */
export function validateStep(step, w) {
  if (step === 0) {
    if (!(w.recipient_name || "").trim()) return "Enter who you are sharing with.";
    const e = (w.recipient_email || "").trim();
    if (e && !EMAIL_RE.test(e)) return "That email address does not look right.";
  }
  if (step === 1 && !(w.scopes || []).length) return "Choose at least one kind of information to share.";
  if (step === 2) {
    if (!w.date_from || !w.date_to) return "Choose a start and an end date.";
    if (w.date_from > w.date_to) return "The start date must not be after the end date.";
  }
  if (step === 3) {
    const n = Number(w.expires_in_days);
    if (!Number.isInteger(n) || n < 1 || n > 365) return "Access must last between 1 and 365 days.";
  }
  return null;
}

export function buildSharePayload(w) {
  return {
    recipient_name: w.recipient_name.trim(), recipient_type: w.recipient_type,
    recipient_email: (w.recipient_email || "").trim() || null, purpose: (w.purpose || "").trim() || null,
    scopes: [...w.scopes], date_from: w.date_from, date_to: w.date_to,
    include_detail: !!w.include_detail, allow_download: !!w.allow_download,
    closed_periods_only: !!w.closed_periods_only, expires_in_days: Number(w.expires_in_days),
  };
}

export function formatCode(code) { return String(code || ""); }

const STATUS_STYLE = {
  ACTIVE: "badge badge-pass", REVOKED: "badge badge-fail", EXPIRED: "badge badge-neutral", LOCKED: "badge badge-warn",
};
const ACTION_LABEL = {
  PASSPORT_SHARE_CREATED: "Share created", PASSPORT_SHARE_VERIFIED: "Recipient verified",
  PASSPORT_SHARE_VIEWED: "Recipient viewed", PASSPORT_SHARE_DOWNLOADED: "Recipient downloaded",
  PASSPORT_SHARE_REVOKED: "Access revoked", PASSPORT_SHARE_DENIED: "Access refused",
  PASSPORT_SHARE_LOCKED: "Locked after repeated wrong codes",
};
export const actionLabel = (a) => ACTION_LABEL[a] || a;
const scopeLabel = (s) => (SCOPE_OPTIONS.find((o) => o[0] === s) || [s, s])[1];
const typeLabel = (t) => (RECIPIENT_TYPES.find((o) => o[0] === t) || [t, t])[1];

function field(label, control, hint) {
  return h("div", { className: "field", style: "margin-bottom:12px;" }, h("label", {}, label), control,
    hint ? h("div", { style: "font-size:12px; color: var(--ink-500); margin-top:4px;" }, hint) : null);
}

function check(label, checked, onChange, hint, id) {
  return h("label", { style: "display:flex; gap:8px; align-items:flex-start; margin:8px 0; cursor:pointer;" },
    h("input", { type: "checkbox", id, checked: !!checked, onChange: (e) => onChange(e.target.checked) }),
    h("span", {}, h("span", {}, label), hint ? h("div", { style: "font-size:12px; color: var(--ink-500);" }, hint) : null));
}

function stepper(step) {
  return h("div", { style: "display:flex; gap:6px; flex-wrap:wrap; margin-bottom:16px;" },
    STEPS.map((s, i) => h("div", {
      className: "wizard-step", "data-state": i === step ? "current" : i < step ? "done" : "todo",
      style: `padding:4px 10px; border-radius:14px; font-size:12.5px; border:1px solid var(--line); ${i === step ? "background: var(--ink-900); color:#fff;" : i < step ? "color: var(--ink-500);" : "color: var(--ink-500);"}`,
    }, `${i + 1}. ${s}`)));
}

function stepBody(w, on) {
  if (w.step === 0) {
    return h("div", {},
      field("Who is this for?", h("input", { type: "text", id: "share-name", value: w.recipient_name, maxlength: 200,
        placeholder: "e.g. First National Bank", onInput: (e) => on("recipient_name", e.target.value) })),
      field("Type of recipient", h("select", { id: "share-type", value: w.recipient_type, onChange: (e) => on("recipient_type", e.target.value) },
        RECIPIENT_TYPES.map(([v, l]) => h("option", { value: v, selected: v === w.recipient_type }, l))),
        "Choosing a type suggests sensible defaults. You can change everything on the next steps."),
      field("Recipient's email (recommended)", h("input", { type: "email", id: "share-email", value: w.recipient_email, maxlength: 200,
        placeholder: "name@bank.com", onInput: (e) => on("recipient_email", e.target.value) }),
        "If given, the recipient must type this address to open the passport. Without it, anyone holding both the link and the code can."),
      field("Purpose (shown to the recipient)", h("input", { type: "text", id: "share-purpose", value: w.purpose, maxlength: 500,
        placeholder: "e.g. Loan application, FY audit", onInput: (e) => on("purpose", e.target.value) })));
  }
  if (w.step === 1) {
    return h("div", {},
      h("p", { style: "margin-top:0;" }, "Choose exactly what the recipient may see. Anything you leave out is not included in what they receive."),
      SCOPE_OPTIONS.map(([key, label, hint]) => check(label, w.scopes.includes(key), (v) => on("scope:" + key, v), hint, "scope-" + key)),
      h("hr", {}),
      check("Include line-level detail", w.include_detail, (v) => on("include_detail", v),
        "Off: the recipient sees totals, counts and statuses only. On: they also see individual transactions, names and the email addresses of your team.", "share-detail"));
  }
  if (w.step === 2) {
    return h("div", {},
      field("Period covered", h("select", { id: "share-preset", value: w.preset, onChange: (e) => on("preset", e.target.value) },
        PRESETS.map(([v, l]) => h("option", { value: v, selected: v === w.preset }, l)))),
      h("div", { style: "display:flex; gap:12px; flex-wrap:wrap;" },
        field("From", h("input", { type: "date", id: "share-from", value: w.date_from, disabled: w.preset !== "custom", onChange: (e) => on("date_from", e.target.value) })),
        field("To", h("input", { type: "date", id: "share-to", value: w.date_to, disabled: w.preset !== "custom", onChange: (e) => on("date_to", e.target.value) }))),
      h("p", { style: "font-size:12.5px; color: var(--ink-500);" },
        "Only accounting periods that fall entirely inside these dates are included."),
      check("Only periods that have been closed (final figures)", w.closed_periods_only, (v) => on("closed_periods_only", v),
        "Recommended for banks and investors: open periods can still change.", "share-closed"));
  }
  if (w.step === 3) {
    return h("div", {},
      check("Allow the recipient to download a copy", w.allow_download, (v) => on("allow_download", v),
        "Off: view only. Either way, anything shown on screen can be copied, so share only with parties you trust.", "share-download"),
      field("Access lasts for (days)", h("input", { type: "number", id: "share-expiry", min: 1, max: 365, value: w.expires_in_days,
        onInput: (e) => on("expires_in_days", e.target.value) }), "After this the link stops working. You can revoke it sooner at any time."),
      h("div", { className: "alert alert-info" }, "You stay in control: you can revoke this share at any moment and access stops immediately, even for someone already viewing it."));
  }
  const range = `${w.date_from} to ${w.date_to}`;
  return h("div", { id: "share-review" },
    h("p", { style: "margin-top:0;" }, "Check this before generating. The recipient receives a frozen snapshot of exactly this."),
    reviewRow("Recipient", `${w.recipient_name.trim()} (${typeLabel(w.recipient_type)})`),
    reviewRow("Verified by", (w.recipient_email || "").trim() ? `Access code and the email ${w.recipient_email.trim()}` : "Access code only (no email set)"),
    reviewRow("Purpose", (w.purpose || "").trim() || "Not stated"),
    reviewRow("Information", w.scopes.map(scopeLabel).join(", ")),
    reviewRow("Detail", w.include_detail ? "Line-level detail included" : "Totals and statuses only"),
    reviewRow("Dates", range + (w.closed_periods_only ? ", closed periods only" : "")),
    reviewRow("Download", w.allow_download ? "Allowed" : "View only"),
    reviewRow("Expires", `after ${w.expires_in_days} day(s)`));
}

function reviewRow(k, v) {
  return h("div", { style: "display:flex; gap:12px; padding:6px 0; border-bottom:1px solid var(--line);" },
    h("div", { style: "width:130px; color: var(--ink-500);" }, k), h("div", {}, v));
}

function wizardCard({ wizard, wizardError, creating, onWizardChange, onNext, onBack, onCreate, onCancel }) {
  const last = wizard.step === STEPS.length - 1;
  return h("div", { className: "card", id: "share-wizard" },
    h("h2", {}, "Share the Passport"),
    stepper(wizard.step),
    stepBody(wizard, onWizardChange),
    wizardError ? h("div", { className: "alert alert-error", role: "alert", style: "margin-top:12px;" }, wizardError) : null,
    h("div", { style: "display:flex; gap:8px; margin-top:16px;" },
      wizard.step > 0 ? h("button", { className: "btn btn-secondary", disabled: creating, onClick: onBack }, "Back") : null,
      !last ? h("button", { className: "btn btn-primary", id: "share-next", onClick: onNext }, "Next") : null,
      last ? h("button", { className: "btn btn-primary", id: "share-create", disabled: creating, onClick: onCreate },
        creating ? "Generating…" : "Generate secure access") : null,
      h("button", { className: "btn btn-secondary", disabled: creating, onClick: onCancel }, "Cancel")));
}

function resultCard({ result, link, copied, onCopy, onDone }) {
  const code = formatCode(result.access_code);
  return h("div", { className: "card", id: "share-result" },
    h("h2", {}, "Secure access generated"),
    h("div", { className: "alert alert-info" }, result.note),
    (result.warnings || []).map((w) => h("div", { className: "alert alert-error", style: "margin-top:8px;" }, w)),
    field("1. Secure link", h("div", { style: "display:flex; gap:8px;" },
      h("input", { type: "text", readonly: true, id: "share-link", value: link, style: "flex:1;" }),
      h("button", { className: "btn btn-secondary", id: "copy-link", onClick: () => onCopy("link", link) }, copied === "link" ? "Copied" : "Copy")),
      "Send this to the recipient."),
    field("2. Access code", h("div", { style: "display:flex; gap:8px;" },
      h("input", { type: "text", readonly: true, id: "share-code", value: code, style: "flex:1; font-family:monospace; font-size:18px; letter-spacing:2px;" }),
      h("button", { className: "btn btn-secondary", id: "copy-code", onClick: () => onCopy("code", code) }, copied === "code" ? "Copied" : "Copy")),
      "Send this by a different route (for example a phone call or text message), never in the same email as the link."),
    h("p", { style: "font-size:12.5px; color: var(--ink-500);" },
      "These are shown only now and cannot be recovered. If lost, revoke this share and create a new one."),
    h("button", { className: "btn btn-primary", id: "share-done", onClick: onDone }, "I have saved them"));
}

function sharesTable({ shares, canRevoke, onRevokeStart, onShowLog }) {
  if (!shares.length) {
    return h("p", { style: "color: var(--ink-500);" }, "Nothing has been shared yet.");
  }
  return h("div", { style: "overflow-x:auto;" }, h("table", { className: "data-table", id: "shares-table" },
    h("thead", {}, h("tr", {}, ["Recipient", "Information", "Dates", "Status", "Expires", "Opened", ""].map((t) => h("th", {}, t)))),
    h("tbody", {}, shares.map((s) => h("tr", { "data-share": s.id },
      h("td", {}, h("strong", {}, s.recipient_name), h("div", { style: "font-size:12px; color: var(--ink-500);" }, typeLabel(s.recipient_type) + (s.purpose ? " · " + s.purpose : ""))),
      h("td", {}, s.scopes.map(scopeLabel).join(", "), h("div", { style: "font-size:12px; color: var(--ink-500);" },
        (s.include_detail ? "With detail" : "Summary only") + (s.allow_download ? " · download allowed" : " · view only"))),
      h("td", {}, `${s.date_from} to ${s.date_to}`),
      h("td", {}, h("span", { className: STATUS_STYLE[s.status] || "badge" }, s.status),
        s.status === "LOCKED" ? h("div", { style: "font-size:12px;" }, "Too many wrong codes") : null,
        s.revoke_reason ? h("div", { style: "font-size:12px; color: var(--ink-500);" }, s.revoke_reason) : null),
      h("td", {}, fmtWhen(s.expires_at)),
      h("td", {}, `${s.access_count} time(s)`, s.failed_attempts ? h("div", { style: "font-size:12px; color: var(--ink-500);" }, `${s.failed_attempts} wrong attempt(s)`) : null),
      h("td", { style: "white-space:nowrap;" },
        h("button", { className: "btn btn-secondary", "data-action": "log", onClick: () => onShowLog(s.id) }, "Activity"),
        canRevoke && (s.status === "ACTIVE" || s.status === "LOCKED")
          ? h("button", { className: "btn btn-secondary", "data-action": "revoke", style: "margin-left:6px;", onClick: () => onRevokeStart(s.id) }, "Revoke") : null))))));
}

function revokeCard({ share, reason, revoking, error, onReasonChange, onConfirm, onCancel }) {
  return h("div", { className: "card", id: "revoke-panel" },
    h("h2", {}, `Revoke access for ${share.recipient_name}`),
    h("p", {}, "The link and code stop working immediately, including for anyone currently viewing. This cannot be undone; you would need to create a new share."),
    field("Reason (kept in the record)", h("input", { type: "text", id: "revoke-reason", value: reason, maxlength: 500, onInput: (e) => onReasonChange(e.target.value) })),
    error ? h("div", { className: "alert alert-error" }, error) : null,
    h("div", { style: "display:flex; gap:8px;" },
      h("button", { className: "btn btn-primary", id: "revoke-confirm", disabled: revoking, onClick: onConfirm }, revoking ? "Revoking…" : "Revoke access"),
      h("button", { className: "btn btn-secondary", disabled: revoking, onClick: onCancel }, "Keep access")));
}

function logCard({ share, log, loading, error, onClose }) {
  return h("div", { className: "card", id: "access-log" },
    h("div", { style: "display:flex; justify-content:space-between;" }, h("h2", {}, `Activity: ${share ? share.recipient_name : ""}`),
      h("button", { className: "btn btn-secondary", onClick: onClose }, "Close")),
    loading ? LoadingState("Loading activity…") : null,
    error ? h("div", { className: "alert alert-error" }, error) : null,
    !loading && !error && log && !log.length ? h("p", { style: "color: var(--ink-500);" }, "No activity yet.") : null,
    !loading && log && log.length ? h("table", { className: "data-table" },
      h("thead", {}, h("tr", {}, ["When", "What", "Who", "Note"].map((t) => h("th", {}, t)))),
      h("tbody", {}, log.map((e) => h("tr", {}, h("td", {}, fmtWhen(e.when)), h("td", {}, actionLabel(e.action)), h("td", {}, e.who || ""), h("td", {}, e.reason || ""))))) : null);
}

export function PassportSharing(props) {
  const { role, loading, error, onRetry, shares, wizard, result, onStart, onBackToPassport, revokeTarget, logTarget } = props;
  if (!allowed(role, PERMISSIONS.PASSPORT_MANAGE)) {
    return h("div", { className: "empty-state card" }, h("h3", {}, "You don't have access to this"),
      h("p", {}, "Sharing is available to owners, administrators and managers."));
  }
  const canShare = allowed(role, PERMISSIONS.ORG_MANAGE_SETTINGS);
  const head = h("div", { style: "display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;" },
    h("h1", {}, "Passport Sharing"),
    h("div", { style: "display:flex; gap:8px;" },
      h("button", { className: "btn btn-secondary", onClick: onBackToPassport }, "Back to Passport"),
      canShare && !wizard && !result ? h("button", { className: "btn btn-primary", id: "share-new", onClick: onStart }, "New share") : null));
  if (loading && !shares) return h("div", {}, head, LoadingState("Loading shares…"));
  if (error && !shares) return h("div", {}, head, ErrorState({ message: error, onRetry }));
  const list = shares || [];
  const rt = revokeTarget ? list.find((s) => s.id === revokeTarget) : null;
  const lt = logTarget ? list.find((s) => s.id === logTarget) : null;
  return h("div", {}, head,
    h("p", { style: "color: var(--ink-500); margin-top:-8px;" },
      "You decide who sees what, for which dates, and for how long. Every share is a frozen snapshot, protected by a secret link plus an access code, and every access is recorded."),
    !canShare ? h("div", { className: "alert alert-info" }, "Only an owner or administrator can create or revoke shares. You can see them here.") : null,
    error ? h("div", { className: "alert alert-error" }, error) : null,
    result ? resultCard(props) : null,
    wizard && !result ? wizardCard(props) : null,
    rt ? revokeCard({ share: rt, reason: props.revokeReason, revoking: props.revoking, error: props.revokeError,
      onReasonChange: props.onRevokeReasonChange, onConfirm: props.onRevokeConfirm, onCancel: props.onRevokeCancel }) : null,
    lt ? logCard({ share: lt, log: props.log, loading: props.logLoading, error: props.logError, onClose: props.onCloseLog }) : null,
    h("div", { className: "card" }, h("h2", {}, "Shares"),
      sharesTable({ shares: list, canRevoke: canShare, onRevokeStart: props.onRevokeStart, onShowLog: props.onShowLog })));
}
