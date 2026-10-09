import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState, EmptyState } from "../components/DataState.js";
import { allowed } from "../components/PermissionGate.js";
import { PERMISSIONS } from "../lib/permissions.js";

/**
 * Security (Advanced Security & Infrastructure). Everything here is a view over real endpoints in
 * api/routers/security.py; where a feature is switched off on the server (no encryption keys, no SSO, no backup report)
 * the page says so plainly instead of showing a fake "green" state.
 *
 * "My account" is open to every signed-in person (two-step sign-in, devices, their own data). The organisation tabs need
 * security:manage (owners and administrators); the server re-checks every call regardless of what is drawn here.
 */
export const TABS = [
  { id: "me", label: "My account", org: false },
  { id: "overview", label: "Overview", org: true },
  { id: "alerts", label: "Alerts", org: true },
  { id: "audit", label: "Audit trail integrity", org: true },
  { id: "retention", label: "Retention & holds", org: true },
  { id: "privacy", label: "Privacy requests", org: true },
  { id: "vendors", label: "Vendors & data location", org: true },
];

export function visibleTabs(role) {
  const manage = allowed(role, PERMISSIONS.SECURITY_MANAGE);
  return TABS.filter((t) => !t.org || manage);
}

/** A coloured label. `status` here is already a tone: pass | fail | warn | info | neutral. */
function StatusBadge({ status, label }) {
  return h("span", { className: `badge badge-${status || "neutral"}` }, label);
}

const SEVERITY_TONE = { CRITICAL: "fail", HIGH: "fail", MEDIUM: "warn", LOW: "info", INFO: "neutral" };
const TIER_TONE = { CRITICAL: "fail", HIGH: "fail", MEDIUM: "warn", LOW: "pass" };

function when(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? String(iso) : d.toISOString().replace("T", " ").slice(0, 16) + " UTC";
}

function fact(label, value, tone) {
  return h("div", { className: "kv", style: "display:flex; justify-content:space-between; gap:12px; padding:6px 0; border-bottom:1px solid var(--ink-100, #eee);" },
    h("span", { style: "color: var(--ink-500);" }, label),
    tone ? StatusBadge({ status: tone, label: String(value) }) : h("span", {}, String(value)));
}

function notice(text, kind = "info") {
  return text ? h("div", { className: `alert alert-${kind === "error" ? "error" : "info"}`, style: "margin-bottom:12px;", role: kind === "error" ? "alert" : "status" }, text) : null;
}

function field(label, id, input) {
  return h("div", { className: "field" }, h("label", { for: id }, label), input);
}

export function Security({ role, sec, loading, onRetry, actions }) {
  const tabs = visibleTabs(role);
  const tab = tabs.find((t) => t.id === sec.tab) ? sec.tab : "me";
  return h("div", {},
    h("h1", {}, "Security"),
    h("p", { style: "color: var(--ink-500); margin-top:-8px; margin-bottom:16px;" },
      "Sign-in protection, devices, data protection and the evidence that the audit trail has not been altered."),
    h("div", { className: "tabs", role: "tablist", style: "display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px;" },
      tabs.map((t) => h("button", {
        className: `btn ${t.id === tab ? "btn-primary" : "btn-secondary"}`, role: "tab", "aria-selected": t.id === tab ? "true" : "false",
        id: `sec-tab-${t.id}`, onClick: () => actions.setTab(t.id),
      }, t.label))),
    sec.notice ? notice(sec.notice) : null,
    sec.error ? ErrorState({ message: sec.error, onRetry }) : null,
    loading ? LoadingState() : h("div", {},
      tab === "me" ? mineTab(sec, actions) : null,
      tab === "overview" ? overviewTab(sec, actions) : null,
      tab === "alerts" ? alertsTab(sec, actions) : null,
      tab === "audit" ? auditTab(sec, actions) : null,
      tab === "retention" ? retentionTab(sec, actions) : null,
      tab === "privacy" ? privacyTab(sec, actions) : null,
      tab === "vendors" ? vendorsTab(sec, actions) : null)
  );
}

// ---------------------------------------------------------------- My account
function mineTab(sec, a) {
  const me = sec.me;
  if (!me) return EmptyState({ title: "Not loaded", message: "Your security details could not be loaded." });
  return h("div", {}, mfaCard(sec, me, a), sessionsCard(me, a), privacyCard(sec, me, a));
}

function mfaCard(sec, me, a) {
  const m = sec.mfa || {}; // transient UI: { setup, error, pending, recovery }
  const status = me.mfa || {};
  if (!me.mfa_available) {
    return h("div", { className: "card", id: "mfa-card" }, h("h3", {}, "Two-step sign-in"),
      h("p", {}, "Two-step sign-in is not switched on for this platform yet. The person who runs the platform needs to add the encryption keys first (see the Security guide)."));
  }
  return h("div", { className: "card", id: "mfa-card" },
    h("h3", {}, "Two-step sign-in"),
    h("p", { style: "color: var(--ink-500);" }, "After your password, you type a 6-digit code from an authenticator app (for example Google Authenticator, Microsoft Authenticator or 1Password)."),
    notice(m.error, "error"),
    m.recovery ? h("div", { className: "alert alert-info", id: "recovery-codes" },
      h("strong", {}, "Save these recovery codes now. They are shown only once."),
      h("p", {}, "Each code works one time if you lose your phone."),
      h("pre", { className: "mono", style: "white-space:pre-wrap;" }, m.recovery.join("\n")),
      h("button", { className: "btn btn-secondary", onClick: a.mfaDismissRecovery }, "I have saved them")) : null,
    status.enabled
      ? h("div", {},
        fact("Status", "On", "pass"), fact("Recovery codes left", status.recovery_codes_left ?? "—"),
        h("div", { className: "field", style: "margin-top:12px;" }, h("label", { for: "mfa-code" }, "To change anything, type a current code"),
          h("input", { id: "mfa-code", type: "text", autocomplete: "one-time-code", maxlength: "32", onInput: (e) => a.mfaCodeChange(e.target.value) })),
        h("div", { style: "display:flex; gap:8px; flex-wrap:wrap;" },
          h("button", { className: "btn btn-secondary", disabled: m.pending, onClick: a.mfaNewRecovery }, "Get new recovery codes"),
          h("button", { className: "btn btn-danger", disabled: m.pending, onClick: a.mfaDisable }, "Turn off")))
      : m.setup
        ? h("div", {},
          h("p", {}, "1. In your authenticator app choose “Add account” → “Enter a setup key”, and type this key:"),
          h("pre", { className: "mono", id: "mfa-secret", style: "white-space:pre-wrap; word-break:break-all;" }, m.setup.secret),
          h("p", {}, "2. Type the 6-digit code the app now shows:"),
          h("div", { className: "field" }, h("input", { id: "mfa-code", type: "text", inputmode: "numeric", autocomplete: "one-time-code", maxlength: "8", onInput: (e) => a.mfaCodeChange(e.target.value) })),
          h("div", { style: "display:flex; gap:8px;" },
            h("button", { className: "btn btn-primary", disabled: m.pending, onClick: a.mfaConfirm }, m.pending ? "Checking…" : "Turn on"),
            h("button", { className: "btn btn-secondary", onClick: a.mfaCancelSetup }, "Cancel")),
          h("details", { style: "margin-top:12px;" }, h("summary", {}, "Setup link (for apps that accept one)"), h("div", { className: "mono", style: "word-break:break-all; font-size:11.5px;" }, m.setup.otpauth_uri || "")))
        : h("div", {}, fact("Status", "Off", "warn"),
          h("button", { className: "btn btn-primary", style: "margin-top:12px;", disabled: m.pending, onClick: a.mfaBegin }, "Set up two-step sign-in")));
}

function sessionsCard(me, a) {
  const rows = me.sessions || [];
  const idOf = (s) => s.session_id || s.id;
  return h("div", { className: "card", id: "sessions-card" },
    h("h3", {}, "Where you are signed in"),
    h("p", { style: "color: var(--ink-500);" }, `You are signed out automatically after ${me.idle_minutes || 30} minutes of inactivity.`),
    rows.length === 0 ? EmptyState({ title: "No sessions" }) : h("div", { className: "table-scroll" }, h("table", {},
      h("thead", {}, h("tr", {}, ["Device", "Network address", "Signed in", "Last active", "Method", ""].map((c) => h("th", {}, c)))),
      h("tbody", {}, rows.map((s) => h("tr", {},
        h("td", {}, (s.user_agent || "Unknown device").slice(0, 60), s.current ? StatusBadge({ status: "info", label: "This device" }) : null),
        h("td", { className: "mono" }, s.ip || "—"), h("td", {}, when(s.created_at)), h("td", {}, when(s.last_seen)),
        h("td", {}, (s.auth_method || "").replace(/\+/g, " + ") + (s.mfa_verified_at ? " ✓" : "")),
        h("td", {}, s.revoked ? "Signed out" : s.current ? "" : h("button", { className: "btn btn-secondary", onClick: () => a.revokeSession(idOf(s)) }, "Sign out"))))))),
    rows.filter((s) => !s.current && !s.revoked).length > 0
      ? h("button", { className: "btn btn-secondary", style: "margin-top:12px;", id: "revoke-others", onClick: a.revokeOthers }, "Sign out all other devices") : null);
}

function privacyCard(sec, me, a) {
  const pending = (me.privacy_requests || []).find((r) => r.status === "PENDING");
  return h("div", { className: "card", id: "privacy-card" },
    h("h3", {}, "Your data"),
    h("p", { style: "color: var(--ink-500);" }, "You can download everything ASAVEXA holds about your account, or ask for your account to be erased. Accounting records and audit events belong to your organisation and are kept, under an anonymous ID."),
    h("div", { style: "display:flex; gap:8px; flex-wrap:wrap;" },
      h("button", { className: "btn btn-secondary", id: "export-data", onClick: a.exportData }, "Download my data"),
      pending ? StatusBadge({ status: "warn", label: "Erasure requested — waiting for an owner" })
        : sec.confirmErase
          ? h("span", {}, h("strong", {}, "This cannot be undone once approved. "), h("button", { className: "btn btn-danger", id: "erase-confirm", onClick: a.requestErasure }, "Yes, request erasure"),
            h("button", { className: "btn btn-secondary", onClick: a.cancelErase }, "Cancel"))
          : h("button", { className: "btn btn-secondary", id: "erase-start", onClick: a.startErase }, "Request account erasure")),
    (me.privacy_requests || []).length ? h("div", { style: "margin-top:12px;" }, me.privacy_requests.map((r) => fact(`Request ${when(r.created_at)}`, r.status, r.status === "COMPLETED" ? "pass" : r.status === "DECLINED" ? "fail" : "warn"))) : null);
}

// ---------------------------------------------------------------- Overview
function overviewTab(sec, a) {
  const o = sec.overview;
  if (!o) return EmptyState({ title: "Not loaded" });
  const enc = o.encryption || {}, st = o.storage || {}, ch = o.audit_chain || {}, mfa = o.mfa || {}, sso = o.sso || {}, res = o.residency || {}, bk = o.backups || {};
  const sp = o.session_policy || {};
  return h("div", {},
    h("div", { className: "card", id: "overview-card" }, h("h3", {}, "Protection at a glance"),
      fact("Encryption keys", enc.configured ? `On — current key “${enc.current_key}”` : "Not set up", enc.configured ? "pass" : "fail"),
      fact("Encrypted evidence files", st.enabled ? `On — ${st.backend}, region ${st.region || "unspecified"}` : "Off", st.enabled ? "pass" : "warn"),
      fact("Tamper-evident audit trail", ch.enabled ? `On — ${ch.head} events chained` : "Off (needs encryption keys)", ch.enabled ? "pass" : "warn"),
      fact("Two-step sign-in", mfa.available ? `${mfa.with_mfa} of ${mfa.members} people${mfa.required ? " — required" : ""}` : "Not available", mfa.available && mfa.with_mfa === mfa.members && mfa.members > 0 ? "pass" : "warn"),
      fact("Single sign-on", sso.configured ? `On — ${sso.issuer}` : "Not set up", sso.configured ? "pass" : "neutral"),
      fact("Open security alerts", o.alerts_open, o.alerts_open ? "warn" : "pass"),
      fact("Legal holds in force", o.holds),
      fact("Vendors overdue for review", o.vendors_overdue, o.vendors_overdue ? "warn" : "pass"),
      fact("Backups", bk.detail || "Unknown", bk.known ? (bk.ok ? "pass" : "fail") : "warn"),
      fact("Idle sign-out", `${sp.idle_minutes} minutes; up to ${sp.max_sessions} devices`)),
    h("div", { className: "card", id: "settings-card" }, h("h3", {}, "Organisation rules"),
      h("label", { style: "display:flex; gap:8px; align-items:center;" },
        h("input", { type: "checkbox", id: "require-mfa", checked: !!mfa.required, onChange: (e) => a.setRequireMfa(e.target.checked) }),
        "Require two-step sign-in for everyone in this organisation"),
      h("p", { style: "color: var(--ink-500); font-size:12.5px;" }, "People without it set up are blocked from opening the organisation until they turn it on. Turn it on for yourself first."),
      field("Keep data in these regions (comma-separated codes, blank = no restriction)", "regions",
        h("input", { id: "regions", type: "text", value: (res.allowed_regions || []).join(", "), placeholder: "e.g. NG, GH", onInput: (e) => a.regionsChange(e.target.value) })),
      h("button", { className: "btn btn-secondary", id: "save-regions", onClick: a.saveRegions }, "Save regions")),
    h("div", { className: "card", id: "keys-card" }, h("h3", {}, "Encryption keys"),
      fact("Keys loaded", (enc.keys || []).join(", ") || "none"),
      fact("Files per key", Object.entries(enc.keys_in_use || {}).map(([k, n]) => `${k}: ${n}`).join(", ") || "none stored"),
      h("p", { style: "color: var(--ink-500); font-size:12.5px;" }, "After adding a new key and making it current, re-wrap the stored file keys. The files themselves are not touched."),
      h("button", { className: "btn btn-secondary", id: "rotate-keys", disabled: !enc.configured || !st.enabled, onClick: a.rotateKeys }, "Re-wrap file keys under the current key"),
      sec.rotateResult ? h("p", { id: "rotate-result" }, `Done: ${sec.rotateResult.rotated} re-wrapped, ${sec.rotateResult.already_current} already current, ${sec.rotateResult.failed} failed.`) : null),
    h("div", { className: "card", id: "health-card" }, h("h3", {}, "System health"),
      h("button", { className: "btn btn-secondary", id: "check-health", onClick: a.checkHealth }, "Run checks now"),
      sec.health ? h("div", { style: "margin-top:12px;" }, fact("Overall", sec.health.status, sec.health.status === "OK" ? "pass" : sec.health.status === "DEGRADED" ? "warn" : "fail"),
        (sec.health.checks || []).map((c) => fact(c.name, c.detail || (c.ok ? "OK" : "Failed"), c.ok ? "pass" : "fail"))) : null));
}

// ---------------------------------------------------------------- Alerts
function alertsTab(sec, a) {
  const list = sec.alerts || [];
  return h("div", { className: "card", id: "alerts-card" },
    h("h3", {}, "Security alerts"),
    h("p", { style: "color: var(--ink-500);" }, "Raised from the audit trail: repeated failed sign-ins, two-step sign-in turned off, new owners or administrators, rule changes, key rotations, legal holds released, records disposed of, bursts of downloads."),
    h("button", { className: "btn btn-secondary", id: "scan-alerts", onClick: a.refreshAlerts }, "Scan now"),
    list.length === 0 ? EmptyState({ title: "No alerts", message: "Nothing unusual has been found. This is not a guarantee: alerts only cover the rules listed above." })
      : h("div", { className: "table-scroll", style: "margin-top:12px;" }, h("table", {},
        h("thead", {}, h("tr", {}, ["Severity", "What happened", "When", "Status", ""].map((c) => h("th", {}, c)))),
        h("tbody", {}, list.map((al) => h("tr", {},
          h("td", {}, StatusBadge({ status: SEVERITY_TONE[al.severity] || "neutral", label: al.severity })),
          h("td", {}, h("strong", {}, al.title), h("div", { style: "color: var(--ink-500); font-size:12.5px;" }, al.detail)),
          h("td", {}, when(al.time)),
          h("td", {}, al.status === "OPEN" ? StatusBadge({ status: "fail", label: "Open" }) : h("span", {}, "Reviewed" + (al.ack_note ? ` — ${al.ack_note}` : ""))),
          h("td", {}, al.status === "OPEN" ? (sec.ackTarget === al.id
            ? h("span", {}, h("input", { type: "text", id: "ack-note", placeholder: "What did you find?", onInput: (e) => a.ackNoteChange(e.target.value) }),
              h("button", { className: "btn btn-primary", onClick: () => a.ackConfirm(al.id) }, "Save"))
            : h("button", { className: "btn btn-secondary", onClick: () => a.ackStart(al.id) }, "Mark reviewed")) : null)))))));
}

// ---------------------------------------------------------------- Audit integrity
function auditTab(sec, a) {
  const r = sec.auditResult;
  return h("div", { className: "card", id: "audit-card" },
    h("h3", {}, "Is the audit trail intact?"),
    h("p", { style: "color: var(--ink-500);" }, "Every audit event is linked to the one before it with a cryptographic signature. Editing, deleting or inserting an event breaks the chain. This check re-reads the whole chain."),
    h("button", { className: "btn btn-primary", id: "verify-audit", onClick: a.verifyAudit }, "Check now"),
    r ? h("div", { style: "margin-top:12px;" },
      r.enabled === false ? notice(r.note) : null,
      r.enabled !== false ? (r.ok && !r.links
        ? fact("Result", "Nothing to check yet — no events have been chained", "warn")
        : fact("Result", r.ok ? "Intact" : `${r.problem_count} problem(s) found`, r.ok ? "pass" : "fail")) : null,
      r.enabled !== false ? fact("Events checked", r.links ?? "—") : null,
      r.unchained_events ? fact("Older events from before protection was switched on", r.unchained_events) : null,
      (r.problems || []).slice(0, 20).map((p) => h("div", { className: "alert alert-error" }, `${p.kind}: ${p.detail || ""}${p.seq ? ` (position ${p.seq})` : ""}`))) : null);
}

// ---------------------------------------------------------------- Retention
function retentionTab(sec, a) {
  const r = sec.retention;
  if (!r) return EmptyState({ title: "Not loaded" });
  const p = r.policy || {};
  return h("div", {},
    h("div", { className: "card", id: "retention-card" }, h("h3", {}, "How long evidence is kept"),
      fact("Evidence kept for", `${(p.days || {}).EVIDENCE} days`), fact("Minimum allowed", `${(p.floor_days || {}).EVIDENCE} days`),
      h("p", { style: "color: var(--ink-500); font-size:12.5px;" }, p.audit || ""),
      field("Change to (days)", "ret-days", h("input", { id: "ret-days", type: "number", min: (p.floor_days || {}).EVIDENCE, onInput: (e) => a.retDaysChange(e.target.value) })),
      h("button", { className: "btn btn-secondary", id: "save-retention", onClick: a.saveRetention }, "Save")),
    h("div", { className: "card", id: "holds-card" }, h("h3", {}, "Legal holds"),
      h("p", { style: "color: var(--ink-500); font-size:12.5px;" }, "While a hold is in force nothing it covers can be disposed of."),
      (r.holds || []).length === 0 ? h("p", {}, "No holds.") : r.holds.map((hd) => h("div", { className: "kv", style: "display:flex; justify-content:space-between; gap:8px; padding:6px 0;" },
        h("span", {}, `${hd.scope === "ORG" ? "Whole organisation" : hd.scope.replace("EVIDENCE:", "Evidence ")} — ${hd.reason}`),
        hd.released_at ? StatusBadge({ status: "neutral", label: "Released" }) : h("button", { className: "btn btn-secondary", onClick: () => a.releaseHold(hd.id) }, "Release"))),
      field("Reason", "hold-reason", h("input", { id: "hold-reason", type: "text", onInput: (e) => a.holdReasonChange(e.target.value) })),
      field("Evidence ID (leave empty to cover the whole organisation)", "hold-evidence", h("input", { id: "hold-evidence", type: "text", onInput: (e) => a.holdEvidenceChange(e.target.value) })),
      h("button", { className: "btn btn-primary", id: "place-hold", onClick: a.placeHold }, "Place hold")),
    h("div", { className: "card", id: "due-card" }, h("h3", {}, "Evidence past its retention date"),
      (r.due_for_disposal || []).length === 0 ? h("p", {}, "Nothing is due for disposal.") : h("div", { className: "table-scroll" }, h("table", {},
        h("thead", {}, h("tr", {}, ["File", "Uploaded", "Due", "Status", ""].map((c) => h("th", {}, c)))),
        h("tbody", {}, r.due_for_disposal.map((d) => h("tr", {}, h("td", {}, d.filename), h("td", {}, when(d.uploaded_at)), h("td", {}, when(d.due_at)),
          h("td", {}, d.on_hold ? StatusBadge({ status: "warn", label: `On hold: ${d.hold_reason}` }) : "Ready"),
          h("td", {}, d.on_hold ? null : (sec.disposeTarget === d.evidence_id
            ? h("span", {}, h("input", { type: "text", id: "dispose-reason", placeholder: "Reason", onInput: (e) => a.disposeReasonChange(e.target.value) }),
              h("button", { className: "btn btn-danger", onClick: () => a.disposeConfirm(d.evidence_id) }, "Dispose of the file"))
            : h("button", { className: "btn btn-secondary", onClick: () => a.disposeStart(d.evidence_id) }, "Dispose…")))))))),
      h("p", { style: "color: var(--ink-500); font-size:12.5px;" }, "Disposal deletes the stored file and its key. The evidence record, its fingerprint and the audit trail are kept.")));
}

// ---------------------------------------------------------------- Privacy requests
function privacyTab(sec, a) {
  const list = sec.requests || [];
  return h("div", { className: "card", id: "requests-card" }, h("h3", {}, "Account erasure requests"),
    h("p", { style: "color: var(--ink-500);" }, "Only an owner can decide. Approving removes the person's email and sign-in, ends their sessions and memberships, and keeps accounting records and audit events under an anonymous ID. The only owner of an organisation cannot be erased."),
    list.length === 0 ? EmptyState({ title: "No requests" }) : list.map((r) => h("div", { className: "card", style: "margin-bottom:8px;" },
      fact("Requested", when(r.created_at)), fact("Status", r.status, r.status === "COMPLETED" ? "pass" : r.status === "DECLINED" ? "fail" : "warn"),
      r.note ? fact("Note", r.note) : null,
      r.status === "PENDING" ? h("div", {},
        h("input", { type: "text", id: `decide-note-${r.id}`, placeholder: "Note (required to decline)", onInput: (e) => a.decideNoteChange(e.target.value) }),
        h("button", { className: "btn btn-danger", onClick: () => a.decide(r.id, true) }, "Approve erasure"),
        h("button", { className: "btn btn-secondary", onClick: () => a.decide(r.id, false) }, "Decline")) : null)));
}

// ---------------------------------------------------------------- Vendors & residency
function vendorsTab(sec, a) {
  const res = sec.residency, vs = sec.vendors || [];
  return h("div", {},
    res ? h("div", { className: "card", id: "residency-card" }, h("h3", {}, "Where the data lives"),
      res.restricted ? fact("Restricted to", (res.allowed_regions || []).join(", ")) : fact("Restriction", "None set"),
      (res.locations || []).map((l) => fact(l.what, l.region, res.restricted ? (l.ok ? "pass" : "fail") : null)),
      (res.vendors_outside_policy || []).map((v) => h("div", { className: "alert alert-error" }, `${v.vendor} handles data in ${v.region}, outside the allowed regions.`)),
      h("p", { style: "color: var(--ink-500); font-size:12.5px;" }, res.note || "")) : null,
    h("div", { className: "card", id: "vendors-card" }, h("h3", {}, "Vendors that touch your data"),
      h("p", { style: "color: var(--ink-500);" }, "Risk is worked out from the facts you record (what data, signed data-processing agreement, security attestation, location, sub-processors, exit plan), not typed in."),
      h("button", { className: "btn btn-secondary", id: "seed-vendors", onClick: a.seedVendors }, "Add the services ASAVEXA runs on"),
      vs.length === 0 ? EmptyState({ title: "No vendors recorded" }) : h("div", { className: "table-scroll", style: "margin-top:12px;" }, h("table", {},
        h("thead", {}, h("tr", {}, ["Vendor", "Data", "Region", "Risk", "Next review", "Why"].map((c) => h("th", {}, c)))),
        h("tbody", {}, vs.map((v) => h("tr", {}, h("td", {}, h("strong", {}, v.name), h("div", { style: "font-size:12px; color: var(--ink-500);" }, v.purpose)),
          h("td", {}, (v.data_categories || []).join(", ") || "—"), h("td", {}, v.region || "Not confirmed"),
          h("td", {}, StatusBadge({ status: TIER_TONE[v.risk_tier] || "neutral", label: v.risk_tier })),
          h("td", {}, v.review_overdue ? StatusBadge({ status: "warn", label: v.next_review_due ? `Overdue (${v.next_review_due})` : "Never reviewed" }) : v.next_review_due || "—"),
          h("td", { style: "font-size:12px;" }, (v.risk_reasons || []).join(" "))))))),
      h("h4", { style: "margin-top:16px;" }, "Add a vendor"),
      field("Name", "v-name", h("input", { id: "v-name", type: "text", onInput: (e) => a.vendorChange("name", e.target.value) })),
      field("What it does for you", "v-purpose", h("input", { id: "v-purpose", type: "text", onInput: (e) => a.vendorChange("purpose", e.target.value) })),
      field("Data it receives", "v-cats", h("select", { id: "v-cats", onChange: (e) => a.vendorChange("data_categories", e.target.value ? [e.target.value] : []) },
        ["", "FINANCIAL", "PERSONAL", "CREDENTIALS", "SOURCE_CODE", "TELEMETRY", "NONE"].map((c) => h("option", { value: c }, c || "Choose…")))),
      field("Region (e.g. EU, US, NG)", "v-region", h("input", { id: "v-region", type: "text", onInput: (e) => a.vendorChange("region", e.target.value) })),
      h("label", { style: "display:block;" }, h("input", { type: "checkbox", id: "v-dpa", onChange: (e) => a.vendorChange("dpa_signed", e.target.checked) }), " Data-processing agreement signed"),
      h("label", { style: "display:block;" }, h("input", { type: "checkbox", id: "v-exit", onChange: (e) => a.vendorChange("exit_plan", e.target.checked) }), " We have a plan for leaving this vendor"),
      h("button", { className: "btn btn-primary", id: "add-vendor", style: "margin-top:8px;", onClick: a.addVendor }, "Add vendor")));
}
