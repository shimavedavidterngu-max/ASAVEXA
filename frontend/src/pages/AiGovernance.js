import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState } from "../components/DataState.js";
import { TABS, ORIGIN_TEXT, TIER_TEXT, CHANGE_TEXT, INCIDENT_TEXT, SEVERITY_TEXT, ATTENTION_TONE, canPrepare, canApprove, statusOf, words, who, useText,
  canDecideSystem, canRetireSystem, canReviewSystem, canRecordChange, canDecideChange, canReviewIncident, ownWorkText } from "../lib/aigov.js";

/**
 * AI governance. It records and checks what people type in; it connects to no AI system, tests nothing and measures no output.
 * Intended use and risk tier cannot be changed once approved. A different person approves, reviews or decides each record.
 */
const Badge = ({ tone, label, id }) => h("span", { className: `badge badge-${tone || "neutral"}`, id }, label);
const St = (s) => Badge({ ...statusOf(s) });
const note = (t, kind = "info", id) => (t ? h("div", { className: `alert alert-${kind}`, id, style: "margin-bottom:12px;", role: kind === "error" ? "alert" : "status" }, t) : null);
const field = (l, id, inp, hint) => h("div", { className: "field" }, h("label", { for: id }, l), inp, hint ? h("small", { style: "color: var(--ink-500);" }, hint) : null);
const text = (gv, a, form, k, id, ph) => h("input", { id, type: "text", value: (gv.forms[form] || {})[k] == null ? "" : (gv.forms[form] || {})[k], placeholder: ph || "", onInput: (e) => a.setForm(form, k, e.target.value) });
const area = (gv, a, form, k, id) => h("textarea", { id, rows: 3, onInput: (e) => a.setForm(form, k, e.target.value) }, (gv.forms[form] || {})[k] || "");
const sel = (gv, a, form, k, id, opts, blank) => h("select", { id, onChange: (e) => a.setForm(form, k, e.target.value, true) },
  [...(blank ? [h("option", { value: "" }, blank)] : []), ...opts.map(([v, l]) => h("option", { value: v, selected: String((gv.forms[form] || {})[k]) === String(v) }, l))]);
const btn = (l, id, onClick, kind = "secondary", disabled = false) => h("button", { className: `btn btn-${kind}`, id, disabled, onClick }, l);
const row = (...b) => h("div", { style: "display:flex; gap:8px; flex-wrap:wrap; margin:8px 0; align-items:end;" }, b.filter(Boolean));
const none = (t = "None.") => h("div", { style: "color: var(--ink-500);" }, t);
const card = (title, id, ...kids) => h("div", { className: "card", id, style: "margin-bottom:16px;" }, h("h3", {}, title), ...kids);
const hist = (items) => h("ul", {}, (items || []).map((x) => h("li", {}, `${String(x.at).slice(0, 10)} ${String(x.event).replace(/_/g, " ").toLowerCase()} by ${x.by}${x.note ? ": " + x.note : ""}`)));
const noteBox = (gv, a, key, l, id) => field(l, id || `note-${key}`, h("textarea", { id: id || `note-${key}`, rows: 2, onInput: (e) => a.setNote(key, e.target.value) }, gv.notes[key] || ""));
const formError = (gv, name) => (gv.formError && gv.formError.form === name ? note(gv.formError.text, "error", `${name}-problem`) : null);
const docs = (gv, a, form, id) => field("Attach a document (optional)", id, sel(gv, a, form, "evidence_id", id, (gv.vault || []).map((e) => [e.id, e.original_filename || e.filename || e.id]), "No document"), "A document from the Evidence Vault. Its file fingerprint is kept.");
const fileList = (list) => (list && list.length ? h("div", { style: "font-size:0.9em; color: var(--ink-500);" }, list.map((e) => `${e.filename} (fingerprint ${String(e.file_hash).slice(0, 12)})`).join("; ")) : null);
const opt = (o) => Object.entries(o);
const approved = (gv) => gv.systems.filter((s) => s.status === "APPROVED");

export function AiGovernance({ gv, role, userId, loading, onRetry, actions: a }) {
  return h("div", {},
    h("h1", {}, "AI governance"),
    note("This workspace records what people type in about their AI systems. It connects to no AI system, tests nothing and measures no output. The risk tier is your own label, not a legal classification. Intended use and tier cannot be changed once approved, and a different person approves, reviews or decides each record.", "info", "gv-banner"),
    gv.error ? ErrorState({ message: gv.error, onRetry }) : null,
    note(gv.notice, "success", "gv-notice"),
    loading ? LoadingState() : h("div", {},
      h("div", { className: "tabs", role: "tablist", style: "display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px;" },
        TABS.map(([id, l]) => h("button", { className: `btn ${gv.tab === id ? "btn-primary" : "btn-secondary"}`, role: "tab", id: `gv-tab-${id}`, "aria-selected": gv.tab === id ? "true" : "false", onClick: () => a.setTab(id) }, l))),
      gv.busy ? h("div", { style: "color: var(--ink-500);" }, "Working...") : null,
      gv.tab === "overview" ? overview(gv, role, a) : gv.tab === "systems" ? systems(gv, role, userId, a) : gv.tab === "changes" ? changes(gv, role, userId, a) : incidents(gv, role, userId, a)));
}

function overview(gv, role, a) {
  const o = gv.ov; if (!o) return none("Nothing loaded yet.");
  const c = o.counts;
  return h("div", {},
    card("What needs attention", "gv-attention", o.attention.length ? h("ul", {}, o.attention.map((x) => h("li", { "data-kind": x.kind }, Badge({ tone: ATTENTION_TONE[x.kind] || "info", label: words(x.kind) }), " ", `${x.count} ${x.text}`))) : none("Nothing needs attention.")),
    card("Counts", "gv-counts", h("ul", {}, [["Approved AI systems", c.systems_approved], ["High tier", c.systems_high], ["Limited tier", c.systems_limited], ["Minimal tier", c.systems_minimal], ["Approved model changes", c.changes_approved],
      ["Incidents", c.incidents], ["Incidents not yet reviewed", c.incidents_open]].map(([l, n]) => h("li", {}, `${l}: ${n}`)))),
    policyCard(gv, role, a),
    card("What this does not do", "gv-limits", h("ul", {}, o.limitations.map((x) => h("li", {}, x)))));
}

function policyCard(gv, role, a) {
  const p = gv.ov.policy, f = gv.forms.policy;
  return card("Settings", "gv-policy", h("p", { id: "gv-policy-meaning" }, p.meaning),
    canApprove(role) && f ? h("div", {},
      row(field("Days before an approved system is due for a review", "gv-policy-review", text(gv, a, "policy", "review_days", "gv-policy-review")), field("Days before an unreviewed incident is flagged", "gv-policy-incident", text(gv, a, "policy", "incident_review_days", "gv-policy-incident"))),
      formError(gv, "policy"), btn("Save settings", "gv-policy-save", () => a.savePolicy(), "primary", gv.busy)) : h("p", { style: "color: var(--ink-500);" }, "Only an approver can change these settings."));
}

// ---------------------------------------------------------------- systems
function systems(gv, role, me, a) {
  const open = gv.sel.system;
  return h("div", {},
    card("AI systems", "gv-systems", gv.systems.length ? gv.systems.map((s) => h("div", { className: "card", style: "margin-bottom:8px;", "data-system": s.ref },
      h("div", {}, h("strong", {}, `${s.ref} · ${s.name}`), " ", St(s.status), " ", St(s.risk_tier), s.review_due ? [" ", Badge({ tone: "warn", label: "Review due" })] : null),
      h("div", { style: "color: var(--ink-500);" }, `${ORIGIN_TEXT[s.origin] || s.origin}${s.vendor_name ? ` (${s.vendor_name})` : ""} · owner ${s.owner_name} · ${s.changes} approved change(s) · ${s.incidents} incident(s)`),
      h("div", {}, s.description), h("div", {}, useText(s)),
      s.human_oversight ? h("div", {}, `Human oversight: ${s.human_oversight}`) : null,
      s.last_reviewed_on ? h("div", { style: "color: var(--ink-500);" }, `Last reviewed ${s.last_reviewed_on}`) : null,
      btn(open && open.id === s.id ? "Hide" : "Open", `gv-system-open-${s.ref}`, () => a.selectSystem(open && open.id === s.id ? null : s.id), "secondary", gv.busy))) : none("No AI systems yet.")),
    open ? systemDetail(gv, role, me, a, open) : null,
    canPrepare(role) ? card("Propose an AI system", "gv-system-card",
      h("p", { style: "color: var(--ink-500);" }, "The intended use, the uses that are not allowed and the risk tier cannot be changed once a different person approves them. To change them later, retire the system and propose a new one."),
      row(field("Name", "gv-sys-name", text(gv, a, "system", "name", "gv-sys-name")), field("Where it comes from", "gv-sys-origin", sel(gv, a, "system", "origin", "gv-sys-origin", opt(ORIGIN_TEXT))), field("Vendor or project name", "gv-sys-vendor", text(gv, a, "system", "vendor_name", "gv-sys-vendor"))),
      field("What it does", "gv-sys-desc", area(gv, a, "system", "description", "gv-sys-desc")),
      field("Intended use", "gv-sys-use", area(gv, a, "system", "intended_use", "gv-sys-use")),
      field("Uses that are not allowed", "gv-sys-out", area(gv, a, "system", "out_of_scope", "gv-sys-out")),
      row(field("Risk tier (your own label)", "gv-sys-tier", sel(gv, a, "system", "risk_tier", "gv-sys-tier", opt(TIER_TEXT))), field("Owner (name)", "gv-sys-owner", text(gv, a, "system", "owner_name", "gv-sys-owner")), field("Kinds of data it uses (optional)", "gv-sys-data", text(gv, a, "system", "data_categories", "gv-sys-data"))),
      field("How a person oversees it (required for the high tier)", "gv-sys-oversight", area(gv, a, "system", "human_oversight", "gv-sys-oversight")),
      formError(gv, "system"), btn("Propose AI system", "gv-sys-save", () => a.proposeSystem(), "primary", gv.busy)) : null);
}

function systemDetail(gv, role, me, a, s) {
  const key = `sys-${s.id}`, decide = canDecideSystem(s, role, me), review = canReviewSystem(s, role, me);
  return card(`${s.ref} · ${s.name}`, "gv-system-detail",
    h("p", {}, St(s.status), " ", St(s.risk_tier), ` · proposed by ${who(s.proposed_by, me)}${s.decided_by ? ` · decided by ${who(s.decided_by, me)}` : ""}`),
    s.decision_note ? h("p", {}, `Note: ${s.decision_note}`) : null,
    decide || review || canRetireSystem(s, role) ? h("div", { id: "gv-system-notes" }, noteBox(gv, a, key, "Note (required, at least 10 characters, to reject, retire or record a review)")) : null,
    s.status === "PROPOSED" && canApprove(role) && !decide ? h("p", { id: "gv-system-waiting" }, ownWorkText("proposed this AI system")) : null,
    decide ? h("div", {}, btn("Approve AI system", "gv-system-approve", () => a.systemStep(s.id, "approve"), "primary", gv.busy), " ", btn("Reject", "gv-system-reject", () => a.systemStep(s.id, "reject"), "secondary", gv.busy)) : null,
    review ? h("div", {}, btn("Record a review", "gv-system-review", () => a.systemStep(s.id, "review"), "primary", gv.busy)) : (s.status === "APPROVED" && canApprove(role) ? h("p", { id: "gv-review-waiting" }, ownWorkText("proposed this AI system")) : null),
    canRetireSystem(s, role) ? h("div", {}, btn("Retire AI system", "gv-system-retire", () => a.systemStep(s.id, "retire"), "secondary", gv.busy)) : (s.status === "APPROVED" && canApprove(role) ? h("p", { id: "gv-retire-hint" }, "Approve or reject the waiting change and review any open incident before retiring this system.") : null),
    h("div", {}, h("h4", {}, "History"), hist(s.history)));
}

// ---------------------------------------------------------------- changes
function changes(gv, role, me, a) {
  const ready = approved(gv).filter((s) => canRecordChange(s, role));
  return h("div", {},
    card("Model changes", "gv-changes", gv.changes.length ? gv.changes.map((c) => h("div", { className: "card", style: "margin-bottom:8px;", "data-change": c.ref },
      h("div", {}, h("strong", {}, `${c.ref} · ${c.system_ref} ${c.system_name}`), " ", St(c.status), " ", St(c.risk_tier), ` · ${CHANGE_TEXT[c.change_kind] || c.change_kind} · ${c.from_version} to ${c.to_version} on ${c.effective_on}`),
      h("div", {}, c.description), h("div", {}, `Testing: ${c.testing_summary}`), fileList(c.evidence),
      h("div", { style: "color: var(--ink-500);" }, `Recorded by ${who(c.recorded_by, me)}${c.decided_by ? `; decided by ${who(c.decided_by, me)}` : ""}${c.decision_note ? `: ${c.decision_note}` : ""}`),
      canDecideChange(c, role, me) ? h("div", {}, noteBox(gv, a, `chg-${c.id}`, "Reason (required, at least 10 characters, to reject)"), btn("Approve change", `gv-chg-${c.ref}-approve`, () => a.changeStep(c.id, "approve"), "primary", gv.busy), " ", btn("Reject", `gv-chg-${c.ref}-reject`, () => a.changeStep(c.id, "reject"), "secondary", gv.busy)) :
        (c.status === "RECORDED" && canApprove(role) ? h("div", { style: "color: var(--ink-500);" }, ownWorkText("recorded this change")) : null))) : none("No model changes yet.")),
    canPrepare(role) ? card("Record a model change", "gv-change-card",
      ready.length ? h("div", {}, row(field("AI system", "gv-chg-system", sel(gv, a, "change", "system_id", "gv-chg-system", ready.map((s) => [s.id, `${s.ref} · ${s.name} (${s.risk_tier.toLowerCase()} tier)`]), "Choose a system")),
        field("Kind of change", "gv-chg-kind", sel(gv, a, "change", "change_kind", "gv-chg-kind", opt(CHANGE_TEXT))), field("Date of the change", "gv-chg-date", text(gv, a, "change", "effective_on", "gv-chg-date", "YYYY-MM-DD"))),
        row(field("Version before", "gv-chg-from", text(gv, a, "change", "from_version", "gv-chg-from")), field("Version after", "gv-chg-to", text(gv, a, "change", "to_version", "gv-chg-to"))),
        field("What changed", "gv-chg-desc", area(gv, a, "change", "description", "gv-chg-desc")), field("How it was tested", "gv-chg-testing", area(gv, a, "change", "testing_summary", "gv-chg-testing")),
        docs(gv, a, "change", "gv-chg-doc"), h("small", { style: "color: var(--ink-500);" }, "A change to a high-tier system needs a linked test document."), formError(gv, "change"), btn("Record change", "gv-chg-save", () => a.recordChange(), "primary", gv.busy)) :
        none("No approved AI system is available. Propose a system and have a different person approve it first.")) : null);
}

// ---------------------------------------------------------------- incidents
function incidents(gv, role, me, a) {
  const open = gv.sel.incident, usable = gv.systems.filter((s) => s.status === "APPROVED" || s.status === "RETIRED"), f = gv.forms.incident, severe = f.severity === "HIGH" || f.severity === "CRITICAL";
  return h("div", {},
    card("AI incidents", "gv-incidents", gv.incidents.length ? gv.incidents.map((i) => h("div", { className: "card", style: "margin-bottom:8px;", "data-incident": i.ref },
      h("div", {}, h("strong", {}, `${i.ref} · ${i.system_ref} ${i.system_name}`), " ", St(i.status), " ", St(i.severity), i.review_overdue ? [" ", Badge({ tone: "warn", label: "Review overdue" })] : null, ` · ${INCIDENT_TEXT[i.incident_kind] || i.incident_kind}`),
      h("div", { style: "color: var(--ink-500);" }, `Happened ${i.occurred_on}; found ${i.discovered_on}; recorded by ${who(i.recorded_by, me)}${i.people_affected != null ? `; people affected: ${i.people_affected}` : ""}`),
      h("div", {}, i.description), i.harm ? h("div", {}, `Harm: ${i.harm}`) : null, fileList(i.evidence),
      i.status === "REVIEWED" ? h("div", {}, `Cause: ${i.cause} Corrective action: ${i.corrective_action}`) : null, i.status === "VOIDED" ? h("div", {}, `Voided: ${i.void_note}`) : null,
      i.status === "RECORDED" ? btn(open && open.id === i.id ? "Hide" : "Open", `gv-inc-open-${i.ref}`, () => a.selectIncident(open && open.id === i.id ? null : i.id), "secondary", gv.busy) : null)) : none("No incidents yet.")),
    open ? incidentDetail(gv, role, me, a, open) : null,
    canPrepare(role) ? card("Record an incident", "gv-incident-card",
      usable.length ? h("div", {}, row(field("AI system", "gv-inc-system", sel(gv, a, "incident", "system_id", "gv-inc-system", usable.map((s) => [s.id, `${s.ref} · ${s.name}`]), "Choose a system")),
        field("Kind", "gv-inc-kind", sel(gv, a, "incident", "incident_kind", "gv-inc-kind", opt(INCIDENT_TEXT))), field("Severity", "gv-inc-sev", sel(gv, a, "incident", "severity", "gv-inc-sev", opt(SEVERITY_TEXT)))),
        field("What happened", "gv-inc-desc", area(gv, a, "incident", "description", "gv-inc-desc")),
        row(field("Happened on", "gv-inc-occ", text(gv, a, "incident", "occurred_on", "gv-inc-occ", "YYYY-MM-DD")), field("Found on", "gv-inc-dis", text(gv, a, "incident", "discovered_on", "gv-inc-dis", "YYYY-MM-DD")),
          field("People affected (optional)", "gv-inc-people", text(gv, a, "incident", "people_affected", "gv-inc-people"))),
        field(severe ? "Harm done (required for a high or critical incident)" : "Harm done (optional)", "gv-inc-harm", area(gv, a, "incident", "harm", "gv-inc-harm")),
        docs(gv, a, "incident", "gv-inc-doc"), formError(gv, "incident"), btn("Record incident", "gv-inc-save", () => a.recordIncident(), "primary", gv.busy)) :
        none("No approved AI system is available. Propose a system and have a different person approve it first.")) : null);
}

function incidentDetail(gv, role, me, a, i) {
  const can = canReviewIncident(i, role, me);
  return card(`${i.ref} · ${i.system_name}`, "gv-incident-detail",
    can ? h("div", {}, h("p", {}, "Review: say what caused it and what was done about it."),
      field("Cause", "gv-rev-cause", h("textarea", { id: "gv-rev-cause", rows: 2, onInput: (ev) => a.setForm("review", "cause", ev.target.value) }, gv.forms.review.cause || "")),
      field("Corrective action (at least 20 characters)", "gv-rev-action", h("textarea", { id: "gv-rev-action", rows: 2, onInput: (ev) => a.setForm("review", "corrective_action", ev.target.value) }, gv.forms.review.corrective_action || "")),
      formError(gv, "review"), btn("Mark as reviewed", "gv-inc-review", () => a.reviewIncident(i.id), "primary", gv.busy),
      noteBox(gv, a, `void-${i.id}`, "Why this record is being voided (required, at least 10 characters)"), btn("Void record", "gv-inc-void", () => a.voidIncident(i.id), "secondary", gv.busy)) :
      (canApprove(role) ? h("p", { id: "gv-inc-waiting" }, ownWorkText("recorded this incident")) : none("Waiting for a different person to review it.")),
    h("div", {}, h("h4", {}, "History"), hist(i.history)));
}
