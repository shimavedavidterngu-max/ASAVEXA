import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState, EmptyState } from "../components/DataState.js";
import { TABS, SEVERITIES, ASSET_TYPES, DATA_CLASSES, CRITICALITIES, CATEGORIES, FLAG_TEXT, canPrepare, canApprove, statusOf, label, vulnMoves, incidentMoves, reviewMoves, reportMoves } from "../lib/cyber.js";

/**
 * Cybersecurity and Digital Risk (defensive record-keeping). Nothing here scans or tests a system; it records what people find and do.
 * A fix is verified, a risk accepted, an incident closed and an access review approved by someone other than the person who did the work, and the page says so.
 */
const Badge = ({ tone, label: l, id }) => h("span", { className: `badge badge-${tone || "neutral"}`, id }, l);
const St = (s, id) => Badge({ ...statusOf(s), id });
const note = (t, kind = "info") => (t ? h("div", { className: `alert alert-${kind}`, style: "margin-bottom:12px;", role: kind === "error" ? "alert" : "status" }, t) : null);
const field = (l, id, inp, hint) => h("div", { className: "field" }, h("label", { for: id }, l), inp, hint ? h("small", { style: "color: var(--ink-500);" }, hint) : null);
const text = (id, f, k, on, ph) => h("input", { id, type: "text", value: f[k] == null ? "" : f[k], placeholder: ph || "", onInput: (e) => on(k, e.target.value) });
const area = (id, f, k, on, rows = 2) => h("textarea", { id, rows, onInput: (e) => on(k, e.target.value) }, f[k] || "");
const sel = (id, value, on, opts, blank) => h("select", { id, onChange: (e) => on(e.target.value) }, [...(blank ? [h("option", { value: "" }, blank)] : []), ...opts.map(([v, l]) => h("option", { value: v, selected: String(value) === String(v) }, l))]);
const table = (head, rows, id) => h("div", { className: "table-scroll" }, h("table", { className: "data-table", id }, h("thead", {}, h("tr", {}, head.map(([l, right]) => h("th", { style: right ? "text-align:right;" : undefined }, l)))), h("tbody", {}, rows)));
const td = (v, right) => h("td", { style: right ? "text-align:right;" : undefined }, v);
const btn = (l, id, onClick, kind = "secondary", disabled = false) => h("button", { className: `btn btn-${kind}`, id, disabled, onClick }, l);
const row = (...b) => h("div", { style: "display:flex; gap:8px; flex-wrap:wrap; margin:8px 0;" }, b.filter(Boolean));
const none = (t = "None.") => h("div", { style: "color: var(--ink-500);" }, t);
const opts = (list) => list.map((x) => [x, label(x)]);
const noteBox = (cy, key, a, l) => field(l, `note-${key}`, area(`note-${key}`, cy.notes, key, a.noteChange));
const hist = (items, id) => h("ul", { id }, (items || []).map((x) => h("li", {}, `${String(x.at).slice(0, 10)} ${String(x.event).replace(/_/g, " ").toLowerCase()} by ${x.by}${x.note ? ": " + x.note : ""}`)));
const flags = (v) => (v.flags || []).map((f) => h("span", { className: "badge badge-fail", style: "margin-left:6px;", title: FLAG_TEXT[f] }, f === "OVERDUE" ? `Overdue ${v.days_overdue}d` : "Acceptance expired"));

export function Cyber({ cy, role, userId, loading, onRetry, actions }) {
  return h("div", {},
    h("h1", {}, "Cybersecurity and Digital Risk"),
    note("This workspace records what people find and do. It does not scan, test or connect to any system, so it is only as complete as the records. Verification, risk acceptance, closure and approval are by a second person.", "warning"),
    cy.error ? ErrorState({ message: cy.error, onRetry }) : null,
    note(cy.notice, "success"),
    loading ? LoadingState() : h("div", {},
      h("div", { className: "tabs", role: "tablist", style: "display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px;" },
        TABS.map(([id, l]) => h("button", { className: `btn ${cy.tab === id ? "btn-primary" : "btn-secondary"}`, role: "tab", id: `cy-tab-${id}`, "aria-selected": cy.tab === id ? "true" : "false", onClick: () => actions.setTab(id) }, l))),
      cy.busy ? h("div", { style: "color: var(--ink-500);" }, "Working...") : null,
      cy.tab === "overview" ? overview(cy, role, actions) : cy.tab === "assets" ? assets(cy, role, actions) : cy.tab === "vulns" ? vulns(cy, role, userId, actions)
        : cy.tab === "incidents" ? incidents(cy, role, userId, actions) : cy.tab === "reviews" ? reviews(cy, role, userId, actions) : reports(cy, role, userId, actions)));
}

// ---------------------------------------------------------------- overview
function overview(cy, role, a) {
  const o = cy.ov;
  if (!o) return EmptyState({ title: "No data yet", message: "Add an asset to begin." });
  const c = o.counts, v = o.vulnerabilities, i = o.incidents, p = cy.policyForm;
  return h("div", { id: "cy-overview" },
    h("div", { className: "card", style: "margin-bottom:12px;" }, h("h3", {}, "At a glance"),
      h("div", { id: "cy-counts" }, `${c.assets} active asset(s); ${c.vulnerabilities_open} open vulnerabilit${c.vulnerabilities_open === 1 ? "y" : "ies"}, ${v.overdue} overdue; ${c.fixes_waiting} fix(es) waiting for verification; ${c.acceptances_waiting} risk acceptance(s) waiting; ${c.incidents_open} open incident(s), ${c.closures_waiting} waiting for closure; ${c.reviews_open} open access review(s); ${c.reports} report(s).`),
      h("div", { id: "cy-times" }, `Average days to fix a verified vulnerability: ${v.average_days_to_fix == null ? "not enough data" : v.average_days_to_fix}. Average days to contain an incident: ${i.average_days_to_contain == null ? "not enough data" : i.average_days_to_contain}.`)),
    h("div", { className: "card", style: "margin-bottom:12px;" }, h("h3", {}, "Vulnerabilities by severity"),
      table([["Severity"], ["Open", true], ["Overdue", true], ["Waiting for verification", true], ["Accepted", true], ["Verified fixed", true]], v.by_severity.map((x) => h("tr", { "data-sev": x.severity }, td(St(x.severity)), td(String(x.open), true), td(String(x.overdue), true), td(String(x.awaiting_verification), true), td(String(x.accepted), true), td(String(x.verified), true))))),
    h("div", { className: "card", style: "margin-bottom:12px;" }, h("h3", {}, "Needs attention"),
      h("h4", {}, "Past the fix deadline"), o.attention.overdue.length ? h("ul", { id: "cy-overdue" }, o.attention.overdue.map((x) => h("li", {}, `${x.ref} ${x.title} on ${x.asset_name} (${label(x.severity)}): ${x.days_overdue} day(s) overdue`))) : none(),
      h("h4", {}, "Accepted risks that have expired"), o.attention.acceptance_expired.length ? h("ul", { id: "cy-expired" }, o.attention.acceptance_expired.map((x) => h("li", {}, `${x.ref} ${x.title}: accepted until ${x.accepted_until}`))) : none(),
      h("h4", {}, "High-value assets with overdue serious vulnerabilities"), o.assets.high_value_with_overdue_serious_vulns.length ? h("div", { id: "cy-exposed" }, o.assets.high_value_with_overdue_serious_vulns.map((ref) => { const x = (cy.assets || []).find((y) => y.ref === ref); return x ? `${ref} ${x.name}` : ref; }).join(", ")) : none()),
    h("div", { className: "card", style: "margin-bottom:12px;" }, h("h3", {}, "Policy"), h("div", { id: "cy-policy" }, o.policy.meaning),
      canApprove(role) && p ? h("div", { style: "margin-top:8px;" }, SEVERITIES.map((s) => field(`${label(s)} deadline (days)`, `pol-sla-${s}`, text(`pol-sla-${s}`, p, `s_${s}`, a.policyChange))),
        field("Longest risk acceptance (days)", "pol-max", text("pol-max", p, "max", a.policyChange)), btn("Save policy", "pol-save", () => a.savePolicy(), "primary", cy.busy)) : null),
    h("div", { className: "card" }, h("h3", {}, "What this does not tell you"), h("ul", {}, o.limitations.map((l) => h("li", {}, l)))));
}

// ---------------------------------------------------------------- assets
function assets(cy, role, a) {
  if (cy.assetForm) return assetFormView(cy, a);
  if (cy.asset) return assetDetail(cy, role, a);
  return h("div", { id: "cy-assets" }, canPrepare(role) ? btn("New asset", "as-new", () => a.newAsset(), "primary") : null,
    cy.assets.length === 0 ? EmptyState({ title: "No assets yet", message: "An asset is a system, device, application or data store you want to protect." })
      : table([["Ref"], ["Name"], ["Type"], ["Criticality"], ["Data class"], ["Open issues", true], ["Status"], [""]], cy.assets.map((x) => h("tr", { "data-asset": x.id }, td(x.ref), td(x.name), td(label(x.type)), td(St(x.criticality)), td(label(x.data_class)), td(String(x.open_vulnerabilities), true), td(St(x.status)), td(btn("Open", `as-open-${x.id}`, () => a.openAsset(x.id)))))));
}

function assetFormView(cy, a) {
  const f = cy.assetForm;
  return h("div", { className: "card", id: "asset-form" }, h("h3", {}, f.id ? "Edit asset" : "New asset"),
    field("Name", "asf-name", text("asf-name", f, "name", a.assetChange)), field("Type", "asf-type", sel("asf-type", f.type, (v) => a.assetChange("type", v), opts(ASSET_TYPES))), field("Owner", "asf-owner", text("asf-owner", f, "owner", a.assetChange)),
    field("Criticality (how much the organisation depends on it)", "asf-crit", sel("asf-crit", f.criticality, (v) => a.assetChange("criticality", v), opts(CRITICALITIES))), field("Data class", "asf-data", sel("asf-data", f.data_class, (v) => a.assetChange("data_class", v), opts(DATA_CLASSES))),
    field("Location", "asf-loc", text("asf-loc", f, "location", a.assetChange)), field("Notes", "asf-notes", area("asf-notes", f, "notes", a.assetChange)),
    row(btn("Save asset", "asf-save", () => a.saveAsset(), "primary", cy.busy), btn("Cancel", "asf-cancel", () => a.cancelAsset())));
}

function assetDetail(cy, role, a) {
  const x = cy.asset;
  return h("div", { id: "asset-detail" }, btn("Back to assets", "as-back", () => a.closeAssetView()), h("h2", {}, `${x.ref} ${x.name}`), h("div", {}, St(x.criticality), " ", St(x.status)),
    h("div", { id: "asset-info" }, `${label(x.type)} owned by ${x.owner}. Data class: ${label(x.data_class)}.${x.location ? " " + x.location + "." : ""}`), x.notes ? h("p", {}, x.notes) : null,
    row(canPrepare(role) && x.status === "ACTIVE" ? btn("Edit", "as-edit", () => a.editAsset()) : null, canPrepare(role) && x.status === "ACTIVE" ? btn("Record a vulnerability", "as-newvuln", () => a.newVuln(x.id), "primary") : null),
    h("h3", {}, "Vulnerabilities"), x.vulnerabilities.length ? table([["Ref"], ["Title"], ["Severity"], ["Status"], ["Due"], [""]], x.vulnerabilities.map((v) => h("tr", {}, td(v.ref), td([v.title, flags(v)]), td(St(v.severity)), td(St(v.status)), td(v.due), td(btn("Open", `as-vuln-${v.id}`, () => a.openVuln(v.id)))))) : none("No vulnerabilities recorded."),
    canPrepare(role) && x.status === "ACTIVE" ? h("div", { className: "card", style: "margin-top:12px;" }, h("h3", {}, "Retire this asset"), noteBox(cy, "retire", a, "Why (required)"), btn("Retire", "as-retire", () => a.retireAsset(), "secondary", cy.busy)) : null,
    h("h3", {}, "History"), hist(x.history, "asset-history"));
}

// ---------------------------------------------------------------- vulnerabilities
function vulns(cy, role, userId, a) {
  if (cy.vulnForm) return vulnFormView(cy, a);
  if (cy.vuln) return vulnDetail(cy, role, userId, a);
  const rows = cy.vulns.filter((v) => !cy.vulnFilter || v.status === cy.vulnFilter);
  return h("div", { id: "cy-vulns" }, row(canPrepare(role) ? btn("Record a vulnerability", "vl-new", () => a.newVuln(""), "primary") : null),
    field("Show", "vl-filter", sel("vl-filter", cy.vulnFilter, (v) => a.filterVulns(v), ["OPEN", "IN_PROGRESS", "FIXED", "VERIFIED", "ACCEPTANCE_PENDING", "ACCEPTED"].map((s) => [s, label(s)]), "All statuses")),
    rows.length === 0 ? EmptyState({ title: "No vulnerabilities", message: "Record a vulnerability against an asset. Its fix deadline comes from your policy." })
      : table([["Ref"], ["Title"], ["Asset"], ["Severity"], ["Status"], ["Due"], [""]], rows.map((v) => h("tr", { "data-vuln": v.id }, td(v.ref), td([v.title, flags(v)]), td(v.asset_name), td(St(v.severity)), td(St(v.status)), td(v.due), td(btn("Open", `vl-open-${v.id}`, () => a.openVuln(v.id)))))));
}

function vulnFormView(cy, a) {
  const f = cy.vulnForm;
  return h("div", { className: "card", id: "vuln-form" }, h("h3", {}, "Record a vulnerability"),
    field("Asset", "vf-asset", sel("vf-asset", f.asset_id, (v) => a.vulnChange("asset_id", v), cy.options.assets.map((x) => [x.id, `${x.ref} ${x.name}`]), "Choose an asset")), field("Title", "vf-title", text("vf-title", f, "title", a.vulnChange)),
    field("Severity", "vf-sev", sel("vf-sev", f.severity, (v) => a.vulnChange("severity", v), opts(SEVERITIES)), `The fix deadline follows your policy for the severity chosen.`), field("CVE (optional)", "vf-cve", text("vf-cve", f, "cve", a.vulnChange, "CVE-2024-12345")),
    field("Where it was found", "vf-source", text("vf-source", f, "source", a.vulnChange, "quarterly scan, audit, vendor notice...")), field("Date found (blank = today)", "vf-found", text("vf-found", f, "found_date", a.vulnChange, "2026-02-10")),
    field("Description", "vf-desc", area("vf-desc", f, "description", a.vulnChange)), row(btn("Save", "vf-save", () => a.saveVuln(), "primary", cy.busy), btn("Cancel", "vf-cancel", () => a.cancelVuln())));
}

function vulnDetail(cy, role, userId, a) {
  const v = cy.vuln, m = vulnMoves(v, role, userId);
  return h("div", { id: "vuln-detail" }, btn("Back to vulnerabilities", "vl-back", () => a.closeVulnView()), h("h2", {}, `${v.ref} ${v.title}`),
    h("div", {}, St(v.severity), " ", St(v.status, "v-status"), flags(v)),
    h("div", { id: "v-summary" }, `On ${v.asset_name}. Found ${v.found_date} (${v.source}). Fix due ${v.due} (${v.sla_days} days under the policy at the time).${v.cve ? " " + v.cve + "." : ""}`),
    v.description ? h("p", {}, v.description) : null,
    v.fix_note ? h("div", { id: "v-fixnote" }, `Fix: ${v.fix_note}${(v.fix_evidence || []).length ? " Evidence: " + v.fix_evidence.map((e) => e.filename).join(", ") : ""}`) : null,
    v.status === "ACCEPTANCE_PENDING" ? h("div", { id: "v-acc-pending" }, `Risk acceptance requested by ${v.accept_requested_by} until ${v.accept_until_requested}: ${v.accept_reason}`) : null,
    v.status === "ACCEPTED" ? h("div", { id: "v-accepted" }, `Risk accepted until ${v.accepted_until}: ${v.accept_reason}`) : null,
    m.ownFix ? h("div", { id: "v-ownfix" }, "You marked this fixed, so a different person must verify it.") : null, m.ownAccept ? h("div", { id: "v-ownacc" }, "You asked for this risk to be accepted, so a different person must decide.") : null,
    row(m.start ? btn("Start work", "v-start", () => a.startVuln(), "secondary", cy.busy) : null, m.fix && !cy.fixForm ? btn("Mark as fixed", "v-fix", () => a.newFix(), "primary") : null, m.accept && !cy.acceptForm ? btn("Ask to accept the risk", "v-accept", () => a.newAccept()) : null,
      m.reopen ? btn("Reopen", "v-reopen", () => a.reopenVuln(), "secondary", cy.busy) : null),
    cy.fixForm ? h("div", { className: "card", id: "fix-form", style: "margin:12px 0;" }, h("h3", {}, "Mark as fixed"), field("What was done", "fx-note", area("fx-note", cy.fixForm, "note", a.fixChange)),
      h("div", {}, h("strong", {}, "Evidence (optional)"), (cy.vault || []).length === 0 ? none("Nothing in the Evidence Vault to link.") : cy.vault.map((e) => h("label", { style: "display:block;" }, h("input", { type: "checkbox", id: `fx-ev-${e.id}`, checked: cy.fixForm.evidence_ids.includes(e.id), onChange: () => a.fixEvidence(e.id) }), ` ${e.original_filename || e.filename || e.id}`))),
      h("small", {}, "A different person must verify the fix."), row(btn("Save", "fx-save", () => a.saveFix(), "primary", cy.busy), btn("Cancel", "fx-cancel", () => a.cancelFix()))) : null,
    cy.acceptForm ? h("div", { className: "card", id: "accept-form", style: "margin:12px 0;" }, h("h3", {}, "Ask to accept the risk"), field("Why is it acceptable? (at least 20 characters)", "ac-reason", area("ac-reason", cy.acceptForm, "reason", a.acceptChange)),
      field("Accepted until", "ac-until", text("ac-until", cy.acceptForm, "until", a.acceptChange, "2026-06-30"), `At most ${cy.ov ? cy.ov.policy.acceptance_max_days : 90} days from today (policy).`), h("small", {}, "A different person must approve it."),
      row(btn("Ask", "ac-save", () => a.saveAccept(), "primary", cy.busy), btn("Cancel", "ac-cancel", () => a.cancelAccept()))) : null,
    (m.verify || m.decideAccept) ? h("div", { className: "card", style: "margin:12px 0;", id: "v-decide" }, noteBox(cy, "v", a, "Note (required to send back)"),
      m.verify ? row(btn("Verify the fix", "v-verify", () => a.verifyVuln(true), "primary", cy.busy), btn("Not fixed, send back", "v-reject-fix", () => a.verifyVuln(false), "secondary", cy.busy)) : null,
      m.decideAccept ? row(btn("Accept the risk", "v-acc-approve", () => a.decideAccept(true), "primary", cy.busy), btn("Decline", "v-acc-reject", () => a.decideAccept(false), "secondary", cy.busy)) : null) : null,
    h("h3", {}, "History"), hist(v.history, "v-history"));
}

// ---------------------------------------------------------------- incidents
function incidents(cy, role, userId, a) {
  if (cy.incidentForm) return incidentFormView(cy, a);
  if (cy.incident) return incidentDetail(cy, role, userId, a);
  return h("div", { id: "cy-incidents" }, canPrepare(role) ? btn("Report an incident", "in-new", () => a.newIncident(), "primary") : null,
    cy.incidents.length === 0 ? EmptyState({ title: "No incidents", message: "Report a security incident as soon as it is detected." })
      : table([["Ref"], ["Title"], ["Category"], ["Severity"], ["Status"], ["Detected"], [""]], cy.incidents.map((n) => h("tr", { "data-incident": n.id }, td(n.ref), td(n.title), td(label(n.category)), td(St(n.severity)), td(St(n.status)), td(n.detected_date), td(btn("Open", `in-open-${n.id}`, () => a.openIncident(n.id)))))));
}

function incidentFormView(cy, a) {
  const f = cy.incidentForm;
  return h("div", { className: "card", id: "incident-form" }, h("h3", {}, "Report an incident"),
    field("Title", "if-title", text("if-title", f, "title", a.incidentChange)), field("What happened", "if-desc", area("if-desc", f, "description", a.incidentChange)),
    field("Category", "if-cat", sel("if-cat", f.category, (v) => a.incidentChange("category", v), opts(CATEGORIES))), field("Severity", "if-sev", sel("if-sev", f.severity, (v) => a.incidentChange("severity", v), opts(SEVERITIES))),
    field("Date detected (blank = today)", "if-date", text("if-date", f, "detected_date", a.incidentChange, "2026-02-10")),
    field("Could personal data be involved?", "if-pd", sel("if-pd", f.personal_data_involved, (v) => a.incidentChange("personal_data_involved", v), [["yes", "Yes, or possibly"], ["no", "No"]], "Choose")),
    h("div", {}, h("strong", {}, "Affected assets"), cy.options.assets.length === 0 ? none("No assets recorded.") : cy.options.assets.map((x) => h("label", { style: "display:block;" }, h("input", { type: "checkbox", id: `if-as-${x.id}`, checked: f.asset_ids.includes(x.id), onChange: () => a.incidentAsset(x.id) }), ` ${x.ref} ${x.name}`))),
    row(btn("Save", "if-save", () => a.saveIncident(), "primary", cy.busy), btn("Cancel", "if-cancel", () => a.cancelIncident())));
}

function incidentDetail(cy, role, userId, a) {
  const n = cy.incident, m = incidentMoves(n, role, userId);
  return h("div", { id: "incident-detail" }, btn("Back to incidents", "in-back", () => a.closeIncidentView()), h("h2", {}, `${n.ref} ${n.title}`), h("div", {}, St(n.severity), " ", St(n.status, "i-status")),
    h("div", { id: "i-summary" }, `${label(n.category)}. Detected ${n.detected_date}. ${n.asset_names.length ? "Affects " + n.asset_names.join(", ") + "." : "No asset recorded."} Personal data ${n.personal_data_involved ? "may be involved" : "not thought to be involved"}.`),
    h("p", {}, n.description),
    h("div", { id: "i-times" }, `Days to contain: ${n.days_to_contain == null ? "not yet" : n.days_to_contain}. Days to resolve: ${n.days_to_resolve == null ? "not yet" : n.days_to_resolve}.`),
    n.root_cause ? h("div", { id: "i-root" }, `Root cause: ${n.root_cause}`) : null,
    n.status === "CLOSED" ? h("div", { id: "i-closed" }, `Lessons learned: ${n.lessons_learned}${n.notification_decision ? " Notification decision: " + n.notification_decision : ""}`) : null,
    m.ownResolve ? h("div", { id: "i-ownresolve" }, "You resolved this incident, so a different person must close it.") : null,
    (m.investigate || m.contain || m.resolve) ? h("div", { className: "card", style: "margin:12px 0;" }, noteBox(cy, "i", a, m.resolve ? "Root cause (required, at least 10 characters)" : m.contain ? "How it was contained (required)" : "Note (optional)"),
      row(m.investigate ? btn("Start investigating", "i-investigate", () => a.incidentStep("investigate"), "primary", cy.busy) : null, m.contain ? btn("Mark as contained", "i-contain", () => a.incidentStep("contain"), "primary", cy.busy) : null,
        m.resolve ? btn("Mark as resolved", "i-resolve", () => a.incidentStep("resolve"), "primary", cy.busy) : null)) : null,
    m.close ? h("div", { className: "card", id: "close-form", style: "margin:12px 0;" }, h("h3", {}, "Close or send back"), field("Lessons learned (at least 20 characters)", "cl-lessons", area("cl-lessons", cy.closeForm, "lessons_learned", a.closeChange)),
      n.personal_data_involved ? field("Notification decision your organisation made", "cl-decision", area("cl-decision", cy.closeForm, "notification_decision", a.closeChange), "ASAVEXA records the decision; it does not decide whether anyone must be told.") : null,
      noteBox(cy, "iback", a, "Reason (only to send back)"), row(btn("Close the incident", "i-close", () => a.closeIncident(), "primary", cy.busy), btn("Send back for more work", "i-reopen", () => a.reopenIncident(), "secondary", cy.busy))) : null,
    h("h3", {}, "Timeline"), h("ul", { id: "i-timeline" }, n.timeline.map((t) => h("li", {}, `${t.date} ${t.event.toLowerCase()} (${t.by}): ${t.note}`))),
    m.note ? h("div", { className: "card", style: "margin:12px 0;" }, field("Add a timeline note", "tl-note", area("tl-note", cy.notes, "tl", a.noteChange)), btn("Add note", "tl-add", () => a.addTimeline(), "secondary", cy.busy)) : null);
}

// ---------------------------------------------------------------- access reviews
function reviews(cy, role, userId, a) {
  if (cy.reviewForm) return h("div", { className: "card", id: "review-form" }, h("h3", {}, "New access review"), field("Name", "rvf-name", text("rvf-name", cy.reviewForm, "name", a.reviewChange)),
    field("What is being reviewed", "rvf-scope", text("rvf-scope", cy.reviewForm, "scope", a.reviewChange, "for example the accounting system users")), field("Due date", "rvf-due", text("rvf-due", cy.reviewForm, "due_date", a.reviewChange, "2026-06-30")),
    row(btn("Create", "rvf-save", () => a.saveReview(), "primary", cy.busy), btn("Cancel", "rvf-cancel", () => a.cancelReview())));
  if (cy.review) return reviewDetail(cy, role, userId, a);
  return h("div", { id: "cy-reviews" }, canPrepare(role) ? btn("New access review", "rv-new", () => a.newReview(), "primary") : null,
    cy.reviews.length === 0 ? EmptyState({ title: "No access reviews", message: "An access review checks who still needs the access they hold." })
      : table([["Ref"], ["Name"], ["Scope"], ["Due"], ["Entries", true], ["Status"], [""]], cy.reviews.map((r) => h("tr", { "data-review": r.id }, td(r.ref), td(r.name), td(r.scope), td([r.due_date, r.overdue ? h("span", { className: "badge badge-fail", style: "margin-left:6px;" }, "Overdue") : null]), td(String(r.counts.entries), true), td(St(r.status)), td(btn("Open", `rv-open-${r.id}`, () => a.openReview(r.id)))))));
}

function reviewDetail(cy, role, userId, a) {
  const r = cy.review, m = reviewMoves(r, role, userId), c = r.counts;
  return h("div", { id: "review-detail" }, btn("Back to access reviews", "rv-back", () => a.closeReviewView()), h("h2", {}, `${r.ref} ${r.name}`), h("div", {}, St(r.status, "rv-status")),
    h("div", { id: "rv-counts" }, `${c.entries} entr${c.entries === 1 ? "y" : "ies"}: ${c.pending} undecided, ${c.keep} to keep, ${c.remove} to remove (${c.removed_confirmed} removal(s) confirmed).`),
    table([["Person or account"], ["System"], ["Access"], ["Decision"], ["Note"], [""]], r.entries.map((e) => h("tr", { "data-entry": e.id }, td(e.subject), td(e.system), td(e.access), td(St(e.decision)), td(e.note || ""),
      td(row(m.edit && !e.removed_by ? btn("Keep", `en-keep-${e.id}`, () => a.decideEntry(e.id, "KEEP")) : null, m.edit && !e.removed_by ? btn("Remove", `en-remove-${e.id}`, () => a.decideEntry(e.id, "REMOVE")) : null,
        m.confirm && e.decision === "REMOVE" && !e.removed_by ? btn("Confirm removed", `en-removed-${e.id}`, () => a.confirmRemoved(e.id)) : null, e.removed_by ? h("span", { className: "badge badge-pass" }, "Removed") : null))))),
    m.edit ? h("div", { className: "card", style: "margin:12px 0;" }, noteBox(cy, "entry", a, "Reason (required when removing)"), h("small", {}, "Type the reason, then press Keep or Remove on a row.")) : null,
    m.edit && cy.entryForm ? h("div", { className: "card", id: "entry-form", style: "margin:12px 0;" }, field("Person or account", "en-subject", text("en-subject", cy.entryForm, "subject", a.entryChange)), field("System", "en-system", text("en-system", cy.entryForm, "system", a.entryChange)),
      field("Access held", "en-access", text("en-access", cy.entryForm, "access", a.entryChange)), btn("Add entry", "en-add", () => a.addEntry(), "primary", cy.busy)) : null,
    m.submit ? row(btn("Submit for approval", "rv-submit", () => a.submitReview(), "primary", cy.busy)) : null,
    m.own ? h("div", { id: "rv-own" }, "You submitted this review, so a different person must decide it.") : null,
    m.decide ? h("div", { id: "rv-decide", className: "card" }, noteBox(cy, "rv", a, "Note (required to send back)"), row(btn("Approve the review", "rv-approve", () => a.decideReview(true), "primary", cy.busy), btn("Send back", "rv-reject", () => a.decideReview(false), "secondary", cy.busy))) : null,
    r.decision_note ? h("div", {}, `Decision note: ${r.decision_note}`) : null, h("h3", {}, "History"), hist(r.history, "rv-history"));
}

// ---------------------------------------------------------------- reports
function reports(cy, role, userId, a) {
  if (cy.reportForm) return h("div", { className: "card", id: "report-form" }, h("h3", {}, "New posture report"), field("Title", "rp-title", text("rp-title", cy.reportForm, "title", a.reportChange)),
    row(btn("Create", "rp-save", () => a.saveReport(), "primary", cy.busy), btn("Cancel", "rp-cancel", () => a.cancelReport())));
  if (cy.report) return reportDetail(cy, role, userId, a);
  return h("div", { id: "cy-reports" }, canPrepare(role) ? btn("New report", "rep-new", () => a.newReport(), "primary") : null,
    cy.reports.length === 0 ? EmptyState({ title: "No reports", message: "A report freezes the security posture at one moment so a second person can approve it." })
      : table([["Ref"], ["Title"], ["Version", true], ["Status"], [""]], cy.reports.map((r) => h("tr", { "data-report": r.id }, td(r.ref), td(r.title), td(String(r.version), true), td(St(r.status)), td(btn("Open", `rep-open-${r.id}`, () => a.openReport(r.id)))))));
}

function reportDetail(cy, role, userId, a) {
  const r = cy.report, m = reportMoves(r, role, userId), s = r.snapshot, p = s && s.posture;
  return h("div", { id: "report-detail" }, btn("Back to reports", "rep-back", () => a.closeReportView()), h("h2", {}, `${r.ref} ${r.title}`), h("div", {}, St(r.status, "rep-status")), h("small", {}, r.confidentiality),
    s ? h("div", { className: "card", style: "margin:12px 0;", id: "rep-frozen" }, h("div", {}, `Frozen ${String(s.generated_at).slice(0, 10)}, version ${r.version}. Fingerprint ${String(r.fingerprint).slice(0, 16)}...`),
      h("div", { id: "rep-figures" }, `${p.assets.active} active asset(s). ${p.vulnerabilities.open} open vulnerabilit${p.vulnerabilities.open === 1 ? "y" : "ies"}, ${p.vulnerabilities.overdue} overdue. ${p.incidents.open} open incident(s). ${p.reviews.completed} access review(s) completed.`),
      h("ul", {}, s.limitations.map((l) => h("li", {}, l)))) : note("Nothing is frozen yet. Submitting freezes the figures as they are at that moment.", "info"),
    row(m.submit ? btn("Freeze and submit for approval", "rep-submit", () => a.submitReport(), "primary", cy.busy) : null, m.exportable ? btn("Download CSV", "rep-export", () => a.exportReport(), "primary", cy.busy) : null),
    m.own ? h("div", { id: "rep-own" }, "You submitted this report, so a different person must decide it.") : null,
    m.decide ? h("div", { id: "rep-decide" }, noteBox(cy, "report", a, "Note (required to send back)"), row(btn("Approve", "rd-approve", () => a.decideReport(true), "primary", cy.busy), btn("Send back", "rd-reject", () => a.decideReport(false), "secondary", cy.busy))) : null,
    r.decision_note ? h("div", {}, `Decision note: ${r.decision_note}`) : null, h("h3", {}, "History"), hist(r.history, "rep-history"));
}
