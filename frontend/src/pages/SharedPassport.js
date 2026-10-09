import { h } from "../lib/vdom.js";
import { LoadingState } from "../components/DataState.js";
import { PassportSections, sectionTiles, fmtWhen } from "./Passport.js";
import { SCOPE_OPTIONS, RECIPIENT_TYPES } from "./PassportSharing.js";

/**
 * What a recipient (not an ASAVEXA user) sees: a verification screen, then a read-only view of
 * the snapshot the organisation chose to share. Pure render function; no organisation login,
 * navigation or editing controls ever appear here.
 */

const scopeLabel = (s) => (SCOPE_OPTIONS.find((o) => o[0] === s) || [s, s])[1];

export function SharedPassport(props) {
  const { phase } = props;
  return h("div", { className: "shared-page", style: "max-width:1000px; margin:0 auto; padding:24px 16px;" },
    h("div", { className: "brand", style: "margin-bottom:16px;" }, "ASAVEXA", h("small", {}, " Verified financial passport")),
    phase === "view" && props.data ? viewScreen(props)
      : phase === "bad-link" ? badLink()
      : verifyScreen(props));
}

function badLink() {
  return h("div", { className: "card", id: "shared-bad-link" }, h("h2", {}, "This link is incomplete"),
    h("p", {}, "Please open the full link exactly as the organisation sent it."));
}

function verifyScreen({ pending, error, expired, code, email, onCodeChange, onEmailChange, onVerify }) {
  return h("form", { className: "card", id: "shared-verify", style: "max-width:460px; margin:40px auto;",
    onSubmit: (e) => { e.preventDefault(); onVerify(); } },
    h("h2", {}, "Open a shared financial passport"),
    h("p", { style: "color: var(--ink-500);" },
      "An organisation has shared verified financial information with you. Enter the access code they sent separately."),
    expired ? h("div", { className: "alert alert-info", role: "status" }, "Your session ended. Enter the code again to continue.") : null,
    h("div", { className: "field", style: "margin-bottom:12px;" }, h("label", {}, "Access code"),
      h("input", { type: "text", id: "shared-code", value: code || "", autocomplete: "off", autocapitalize: "characters",
        placeholder: "XXXXX-XXXXX", style: "font-family:monospace; letter-spacing:2px;", onInput: (e) => onCodeChange(e.target.value) })),
    h("div", { className: "field", style: "margin-bottom:12px;" }, h("label", {}, "Your email address"),
      h("input", { type: "email", id: "shared-email", value: email || "", autocomplete: "email", onInput: (e) => onEmailChange(e.target.value) }),
      h("div", { style: "font-size:12px; color: var(--ink-500); margin-top:4px;" }, "Required if the organisation named you by email address.")),
    error ? h("div", { className: "alert alert-error", role: "alert" }, error) : null,
    h("button", { className: "btn btn-primary", id: "shared-open", type: "submit", disabled: pending }, pending ? "Checking…" : "Open"));
}

function viewScreen({ data, onDownload, downloading, downloadError, onPrint, onClose, loading }) {
  if (loading) return LoadingState("Opening the passport…");
  const m = data.share || {};
  const integ = data.integrity || {};
  const typeLabel = (RECIPIENT_TYPES.find((o) => o[0] === m.recipient_type) || [0, m.recipient_type])[1];
  const periods = m.periods_included || [];
  return h("div", { id: "shared-view" },
    h("div", { className: "card" },
      h("div", { style: "display:flex; justify-content:space-between; gap:8px; flex-wrap:wrap;" },
        h("div", {},
          h("h1", { style: "margin:0 0 4px;" }, m.organisation || "Financial passport"),
          h("div", { style: "color: var(--ink-500);" }, `Shared with ${m.recipient_name || ""} (${typeLabel || ""})` + (m.purpose ? ` · ${m.purpose}` : ""))),
        h("div", { style: "display:flex; gap:8px; align-items:flex-start; flex-wrap:wrap;" },
          h("button", { className: "btn btn-secondary", id: "shared-print", onClick: onPrint }, "Print"),
          m.allow_download ? h("button", { className: "btn btn-secondary", id: "shared-download", disabled: downloading, onClick: onDownload }, downloading ? "Preparing…" : "Download") : null,
          h("button", { className: "btn btn-secondary", id: "shared-close", onClick: onClose }, "Close"))),
      downloadError ? h("div", { className: "alert alert-error", style: "margin-top:8px;" }, downloadError) : null,
      h("div", { id: "shared-banner", style: "margin-top:12px; font-size:13px;" },
        row("Information shared", (m.scopes || []).map(scopeLabel).join(", ")),
        row("Dates", `${m.date_from} to ${m.date_to}` + (m.closed_periods_only ? " (closed periods only)" : "")),
        row("Periods included", periods.length ? periods.map((p) => p.name).join(", ") : "None"),
        m.periods_excluded ? row("Periods left out", `${m.periods_excluded} (outside the dates${m.closed_periods_only ? " or not yet closed" : ""})`) : null,
        row("Level of detail", m.include_detail ? "Line-level detail included" : "Totals and statuses only"),
        row("Snapshot taken", fmtWhen(m.snapshot_taken_at)),
        row("Access ends", fmtWhen(m.expires_at))),
      h("div", { id: "shared-integrity", className: integ.verified ? "alert alert-info" : "alert alert-error", style: "margin-top:12px;" },
        integ.verified ? `Integrity check passed. Fingerprint ${String(integ.fingerprint || "").slice(0, 16)}…`
          : "The integrity check FAILED: this snapshot does not match its fingerprint. Do not rely on it."),
      h("div", { style: "font-size:12px; color: var(--ink-500); margin-top:6px;" },
        "This is a frozen snapshot, not live data. The check confirms the content has not changed since it was shared."),
      h("div", { style: "display:flex; gap:10px; flex-wrap:wrap; margin-top:12px;" }, sectionTiles(data.sections || {}))),
    PassportSections(data.sections || {}, {}));
}

function row(k, v) {
  return h("div", { style: "display:flex; gap:12px; padding:3px 0;" }, h("div", { style: "width:150px; color: var(--ink-500);" }, k), h("div", {}, v));
}
