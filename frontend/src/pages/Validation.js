import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState, EmptyState } from "../components/DataState.js";
import { allowed } from "../components/PermissionGate.js";
import { PERMISSIONS } from "../lib/permissions.js";
import {
  CONFIRMATIONS, STAGE_TONE, OUTCOME_TONE, SEVERITY_TONE, CONCLUSION_TONE, STAGE_STATUS_TEXT, OUTCOME_TEXT, humanize,
  actingMode, entries, reviewState, assignable, openSeriousObservations, credentialSummary,
} from "../lib/validation.js";

/**
 * Professional Validation. Software testing is not accounting validation: this page records what independent, named professionals
 * concluded about each stage — accounting treatment, controls, evidence, reporting, audit workflow, security, professional judgement —
 * on a frozen snapshot of the data. The platform never validates anything itself; every outcome shown is computed from reviews that a
 * reviewer signed, and the server enforces every rule (assignment, independence, who may sign) regardless of what is drawn here.
 */
export const TABS = [
  { id: "engagements", label: "Engagements" },
  { id: "panel", label: "Reviewer panel" },
  { id: "guide", label: "How it works" },
];

function Badge({ tone, label }) { return h("span", { className: `badge badge-${tone || "neutral"}` }, label); }

const when = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? String(iso) : d.toISOString().replace("T", " ").slice(0, 16) + " UTC";
};

function notice(text, kind = "info") {
  return text ? h("div", { className: `alert alert-${kind === "error" ? "error" : "info"}`, style: "margin-bottom:12px;", role: kind === "error" ? "alert" : "status" }, text) : null;
}
function field(label, id, input, hint) {
  return h("div", { className: "field" }, h("label", { for: id }, label), input, hint ? h("small", { style: "color: var(--ink-500);" }, hint) : null);
}
const text = (id, f, k, a, ph) => h("input", { id, type: "text", value: f[k] || "", placeholder: ph || "", onInput: (e) => a.formChange(k, e.target.value) });
const area = (id, f, k, a, rows = 3) => h("textarea", { id, rows, value: f[k] || "", onInput: (e) => a.formChange(k, e.target.value) }, f[k] || "");
const select = (id, f, k, a, options) => h("select", { id, onChange: (e) => a.formChange(k, e.target.value) },
  options.map(([v, l]) => h("option", { value: v, selected: (f[k] || "") === v }, l)));

export function Validation({ role, val, loading, onRetry, actions }) {
  const tab = TABS.find((t) => t.id === val.tab) ? val.tab : "engagements";
  return h("div", {},
    h("h1", {}, "Professional Validation"),
    h("p", { style: "color: var(--ink-500); margin-top:-8px;" },
      "Software testing is not accounting validation. This is where named, independent professionals review the work and sign what they conclude."),
    val.guide ? h("div", { className: "alert alert-info", id: "val-disclaimer" }, val.guide.disclaimer) : null,
    h("div", { className: "tabs", role: "tablist", style: "display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px;" },
      TABS.map((t) => h("button", {
        className: `btn ${t.id === tab && !val.detailId ? "btn-primary" : "btn-secondary"}`, role: "tab", id: `val-tab-${t.id}`,
        "aria-selected": t.id === tab && !val.detailId ? "true" : "false", onClick: () => actions.setTab(t.id),
      }, t.label))),
    val.notice ? notice(val.notice) : null,
    val.error ? ErrorState({ message: val.error, onRetry }) : null,
    loading ? LoadingState() : val.detailId ? detailView(val, actions) : h("div", {},
      tab === "engagements" ? engagementsTab(val, actions) : null,
      tab === "panel" ? panelTab(val, actions) : null,
      tab === "guide" ? guideTab(val) : null));
}

// ---------------------------------------------------------------- engagements list + create
function engagementsTab(val, a) {
  const manage = !!(val.me && val.me.can_manage);
  const list = val.list || [];
  return h("div", {},
    h("div", { className: "card", id: "engagements-card" }, h("h3", {}, "Validation engagements"),
      list.length === 0 ? EmptyState({ title: "No engagements yet", message: manage ? "Create one below to start." : "An owner or administrator creates engagements." })
        : h("div", { className: "table-scroll" }, h("table", {},
          h("thead", {}, h("tr", {}, ["Engagement", "Figures as at", "Status", "Outcome", "Stages covered", ""].map((c) => h("th", {}, c)))),
          h("tbody", {}, list.map((e) => h("tr", { "data-engagement": e.id },
            h("td", {}, e.title), h("td", {}, e.as_of), h("td", {}, Badge({ tone: e.status === "COMPLETED" ? "pass" : e.status === "WITHDRAWN" ? "neutral" : "info", label: humanize(e.status) })),
            h("td", {}, Badge({ tone: OUTCOME_TONE[e.outcome], label: humanize(e.outcome) })), h("td", {}, `${e.stages_covered} of ${e.stages_total}`),
            h("td", {}, h("button", { className: "btn btn-secondary", onClick: () => a.openDetail(e.id) }, "Open")))))))),
    manage ? createForm(val, a) : null);
}

function createForm(val, a) {
  const f = (val.form && val.form.kind === "engagement") ? val.form.f : {};
  const stages = ((val.guide && val.guide.stages) || []);
  const chosen = f.stages || stages.map((s) => s.id);
  if (!val.form || val.form.kind !== "engagement") {
    return h("div", { className: "card" }, h("button", { className: "btn btn-primary", id: "new-engagement", onClick: () => a.startForm("engagement", {}) }, "New validation engagement"));
  }
  return h("div", { className: "card", id: "engagement-form" }, h("h3", {}, "New validation engagement"),
    h("p", { style: "color: var(--ink-500);" }, "ASAVEXA freezes a snapshot of today's counts and statuses (not amounts or names). Reviewers attest to that snapshot; if the data moves afterwards, the statement says so."),
    field("Title", "eng-title", text("eng-title", f, "title", a, "e.g. Year-end 2026 independent validation")),
    field("Figures are as at (date)", "eng-asof", h("input", { id: "eng-asof", type: "date", value: f.as_of || "", onInput: (e) => a.formChange("as_of", e.target.value) })),
    field("Description (optional)", "eng-desc", area("eng-desc", f, "description", a, 2)),
    field("Reviewers needed per stage", "eng-min", select("eng-min", { min_each: f.min_each || "1" }, "min_each", a, [["1", "One"], ["2", "Two"], ["3", "Three"]])),
    h("fieldset", {}, h("legend", {}, "Stages in scope"),
      stages.map((s) => h("label", { style: "display:block;" }, h("input", { type: "checkbox", id: `eng-stage-${s.id}`, checked: chosen.includes(s.id), onChange: (e) => a.toggleStage(s.id, e.target.checked) }), ` ${s.label}`))),
    h("div", { style: "display:flex; gap:8px; margin-top:12px;" },
      h("button", { className: "btn btn-primary", id: "create-engagement", disabled: val.busy, onClick: a.createEngagement }, "Create (as a draft)"),
      h("button", { className: "btn btn-secondary", onClick: a.cancelForm }, "Cancel")));
}

// ---------------------------------------------------------------- panel
function panelTab(val, a) {
  const manage = !!(val.me && val.me.can_manage);
  const panel = val.panel || [];
  return h("div", {},
    h("div", { className: "card", id: "panel-card" }, h("h3", {}, "Reviewer panel"),
      h("p", { style: "color: var(--ink-500);" }, "Credentials are recorded as declared. They count as verified only after a person records how they checked them (for example, on the professional body's public register). ASAVEXA checks nothing itself."),
      panel.length === 0 ? EmptyState({ title: "No reviewers yet", message: manage ? "Add the professionals who will review." : "An owner or administrator maintains the panel." })
        : panel.map((r) => reviewerCard(r, val, a, manage))),
    manage ? addReviewerForm(val, a) : null);
}

function reviewerCard(r, val, a, manage) {
  const cs = credentialSummary(r);
  const vf = val.form && val.form.kind === "verify" && val.form.rid === r.id ? val.form : null;
  return h("div", { className: "card", "data-reviewer": r.id, style: "margin-bottom:12px;" },
    h("div", { style: "display:flex; justify-content:space-between; gap:8px; flex-wrap:wrap;" },
      h("strong", {}, r.name), h("span", {}, r.active ? null : Badge({ tone: "neutral", label: "Inactive" }), " ", Badge({ tone: cs.tone, label: cs.text }))),
    h("div", { style: "color: var(--ink-500);" }, `${r.email}${r.affiliation ? " · " + r.affiliation : ""}${r.user_id ? " · has an ASAVEXA account" : " · no ASAVEXA account (recorded on their behalf)"}`),
    h("div", {}, "Specialisms: ", r.specialisms.map(humanize).join(", ")),
    h("ul", {}, r.credentials.map((c, i) => h("li", {},
      `${c.body} ${c.membership_no}${c.jurisdiction ? " (" + c.jurisdiction + ")" : ""} `,
      Badge({ tone: c.status === "VERIFIED" ? "pass" : c.status === "REJECTED" ? "fail" : "warn", label: c.status === "VERIFIED" ? "Verified" : c.status === "REJECTED" ? "Rejected" : "Declared" }),
      c.method ? h("small", {}, ` — ${c.method}${c.note ? "; " + c.note : ""}`) : null,
      manage && c.status !== "VERIFIED" ? h("button", { className: "btn btn-secondary", style: "margin-left:8px;", onClick: () => a.startForm("verify", { method: "", note: "" }, { rid: r.id, idx: i }) }, "Record verification") : null))),
    vf ? h("div", { className: "card", id: "verify-form" },
      field("How was it checked?", "ver-method", text("ver-method", vf.f, "method", a, "e.g. Looked up on the ACCA public register, 1 Oct 2026")),
      field("Note (required if you reject it)", "ver-note", text("ver-note", vf.f, "note", a)),
      h("div", { style: "display:flex; gap:8px;" },
        h("button", { className: "btn btn-primary", id: "ver-accept", disabled: val.busy, onClick: () => a.submitVerify(true) }, "Checked — it is valid"),
        h("button", { className: "btn btn-danger", id: "ver-reject", disabled: val.busy, onClick: () => a.submitVerify(false) }, "Checked — could not be confirmed"),
        h("button", { className: "btn btn-secondary", onClick: a.cancelForm }, "Cancel"))) : null,
    manage ? h("button", { className: "btn btn-secondary", onClick: () => a.setActive(r.id, !r.active) }, r.active ? "Remove from panel" : "Restore to panel") : null);
}

function addReviewerForm(val, a) {
  if (!val.form || val.form.kind !== "reviewer") return h("div", { className: "card" }, h("button", { className: "btn btn-primary", id: "add-reviewer", onClick: () => a.startForm("reviewer", { specialisms: [] }) }, "Add a reviewer"));
  const f = val.form.f, g = val.guide || { bodies: {}, specialisms: {} }, members = val.members || [];
  return h("div", { className: "card", id: "reviewer-form" }, h("h3", {}, "Add a reviewer"),
    field("Full name", "rv-name", text("rv-name", f, "name", a)), field("Email", "rv-email", text("rv-email", f, "email", a)),
    field("Firm or institution", "rv-aff", text("rv-aff", f, "affiliation", a)),
    field("Professional body", "rv-body", select("rv-body", f, "body", a, [["", "Choose…"], ...entries(g.bodies).map(([b, d]) => [b, `${b} — ${d}`])])),
    field("Membership number", "rv-no", text("rv-no", f, "membership_no", a)), field("Country or jurisdiction", "rv-jur", text("rv-jur", f, "jurisdiction", a)),
    field("Year admitted (optional)", "rv-year", text("rv-year", f, "year_admitted", a)),
    h("fieldset", {}, h("legend", {}, "Areas they are competent in"),
      entries(g.specialisms).map(([s, d]) => h("label", { style: "display:block;" }, h("input", { type: "checkbox", id: `rv-spec-${s}`, checked: (f.specialisms || []).includes(s), onChange: (e) => a.toggleSpecialism(s, e.target.checked) }), ` ${d}`))),
    field("Link to a person with an ASAVEXA account (optional)", "rv-user", select("rv-user", f, "user_id", a, [["", "No account — an owner records their signed documents"], ...members.map((m) => [m.user_id, `${m.email} (${humanize(m.role)})`])]),
      "If linked, only that person can declare independence and sign — not even an owner can do it for them."),
    h("div", { style: "display:flex; gap:8px; margin-top:12px;" },
      h("button", { className: "btn btn-primary", id: "save-reviewer", disabled: val.busy, onClick: a.addReviewer }, "Add to panel"),
      h("button", { className: "btn btn-secondary", onClick: a.cancelForm }, "Cancel")));
}

// ---------------------------------------------------------------- guide
function guideTab(val) {
  const g = val.guide;
  if (!g) return EmptyState({ title: "Not loaded" });
  return h("div", {},
    h("div", { className: "card" }, h("h3", {}, "How professional validation works"),
      h("ol", {},
        h("li", {}, "An owner or administrator builds a panel of reviewers and records how each credential was checked."),
        h("li", {}, "They open an engagement. ASAVEXA freezes a snapshot of the data and the seven stages below are set up for review."),
        h("li", {}, "They assign reviewers to stages. A reviewer must be competent in the area, and must declare independence before reviewing."),
        h("li", {}, "Each reviewer concludes — concurs, concurs with comments, disagrees, or is unable to assess — and signs. A signed review cannot be edited; a changed mind is a new version."),
        h("li", {}, "Management must respond to every major or critical observation before the engagement can be completed."),
        h("li", {}, "The result is a statement with a fingerprint. It says who concluded what, on which snapshot, and which credentials were verified.")),
      h("p", {}, h("strong", {}, "What it is not: "), g.disclaimer)),
    h("div", { className: "card" }, h("h3", {}, "The seven stages"),
      g.stages.map((s, i) => h("div", { style: "margin-bottom:12px;" },
        h("strong", {}, `${i + 1}. ${s.label}`), h("div", { style: "color: var(--ink-500);" }, s.question),
        h("details", {}, h("summary", {}, "Prompts a reviewer may use (not exhaustive)"), h("ul", {}, s.checklist.map((c) => h("li", {}, c))),
          h("small", {}, `Reviewers competent in: ${s.specialisms.map(humanize).join(", ")}`))))));
}

// ---------------------------------------------------------------- engagement detail
function detailView(val, a) {
  const d = val.detail;
  if (!d) return val.error ? null : LoadingState();
  const manage = !!(val.me && val.me.can_manage);
  const cov = d.coverage;
  const serious = openSeriousObservations(d);
  return h("div", { id: "engagement-detail" },
    h("button", { className: "btn btn-secondary", id: "back-to-list", onClick: a.closeDetail, style: "margin-bottom:12px;" }, "← All engagements"),
    h("div", { className: "card" },
      h("h2", {}, d.title),
      h("div", { style: "display:flex; gap:8px; flex-wrap:wrap; align-items:center;" },
        Badge({ tone: d.status === "COMPLETED" ? "pass" : d.status === "WITHDRAWN" ? "neutral" : "info", label: humanize(d.status) }),
        h("span", { id: "outcome-badge" }, Badge({ tone: OUTCOME_TONE[d.statement ? d.statement.outcome : cov.outcome], label: OUTCOME_TEXT[d.statement ? d.statement.outcome : cov.outcome] || humanize(cov.outcome) })),
        h("span", {}, `Figures as at ${d.as_of}`)),
      d.description ? h("p", {}, d.description) : null,
      h("div", { id: "snapshot-line", style: "margin-top:8px;" },
        "Data snapshot ", h("code", {}, d.snapshot_hash.slice(0, 12)), " — ",
        d.snapshot_is_current === false ? Badge({ tone: "warn", label: "The data has changed since this snapshot" }) : d.snapshot_is_current === true ? Badge({ tone: "pass", label: "Data unchanged since snapshot" }) : "not compared"),
      d.snapshot ? h("details", {}, h("summary", {}, "What was frozen"), h("pre", { className: "mono", style: "white-space:pre-wrap;" }, JSON.stringify(d.snapshot, null, 2))) : null,
      cov.credential_verification === "SOME_UNVERIFIED" ? h("p", { id: "cred-warning", style: "color: var(--ink-500);" }, "Some signing reviewers' credentials are declared but not verified by a person.") : null,
      manage ? engagementActions(val, d, cov, serious, a) : null),
    d.statement ? statementCard(val, d, a) : null,
    cov.stages.map((s) => stageCard(val, d, s, a)));
}

function engagementActions(val, d, cov, serious, a) {
  const wf = val.form && val.form.kind === "withdraw" ? val.form : null;
  return h("div", { style: "margin-top:12px;" },
    h("div", { style: "display:flex; gap:8px; flex-wrap:wrap;" },
      d.status === "DRAFT" ? h("button", { className: "btn btn-primary", id: "open-engagement", disabled: val.busy, onClick: a.openEngagement }, "Open for review") : null,
      d.status === "DRAFT" || (d.status === "OPEN" && !d.reviews.some((r) => r.status === "SIGNED")) ? h("button", { className: "btn btn-secondary", id: "refresh-snapshot", disabled: val.busy, onClick: a.refreshSnapshot }, "Refresh the snapshot") : null,
      d.status === "OPEN" ? h("button", { className: "btn btn-primary", id: "complete-engagement", disabled: val.busy || !cov.complete || serious.length > 0, onClick: a.completeEngagement }, "Complete and issue statement") : null,
      d.status === "DRAFT" || d.status === "OPEN" ? h("button", { className: "btn btn-danger", id: "withdraw-start", onClick: () => a.startForm("withdraw", { reason: "" }) }, "Withdraw") : null),
    d.status === "OPEN" && !cov.complete ? h("small", { id: "complete-hint", style: "color: var(--ink-500);" }, "Every stage needs enough signed reviews with a conclusion before this can be completed.") : null,
    serious.length ? h("small", { id: "serious-hint", style: "display:block; color: var(--ink-500);" }, `${serious.length} major or critical observation(s) still need a management response.`) : null,
    wf ? h("div", { className: "card", id: "withdraw-form" }, field("Why is it being withdrawn?", "wd-reason", text("wd-reason", wf.f, "reason", a)),
      h("button", { className: "btn btn-danger", id: "withdraw-confirm", onClick: a.withdraw }, "Withdraw this engagement"), h("button", { className: "btn btn-secondary", onClick: a.cancelForm }, "Cancel")) : null);
}

function statementCard(val, d, a) {
  const s = val.statement || d.statement;
  const v = val.statement && val.statement.verification;
  return h("div", { className: "card", id: "statement-card" }, h("h3", {}, "Validation statement"),
    h("div", {}, "Outcome: ", Badge({ tone: OUTCOME_TONE[s.outcome], label: OUTCOME_TEXT[s.outcome] || humanize(s.outcome) })),
    h("div", {}, "Credentials: ", Badge({ tone: s.credential_verification === "ALL_VERIFIED" ? "pass" : "warn", label: s.credential_verification === "ALL_VERIFIED" ? "All verified by a person" : "Some declared only" })),
    h("div", {}, "Fingerprint: ", h("code", { id: "statement-hash" }, s.statement_hash.slice(0, 16)), s.mac ? " (signed with the platform's keys)" : " (hash only — no keys configured)"),
    v ? h("div", { id: "statement-verify" }, v.ok ? Badge({ tone: "pass", label: "Statement is unaltered" }) : Badge({ tone: "fail", label: "Statement does not match its fingerprint" }),
      val.statement.data_unchanged_since_review === false ? [" ", Badge({ tone: "warn", label: "Data has changed since the review" })] : null) : null,
    h("p", { style: "color: var(--ink-500);" }, s.disclaimer),
    s.stages.map((st) => h("div", { style: "margin-top:8px;" }, h("strong", {}, st.label), " — ", humanize(st.status),
      h("ul", {}, st.reviews.map((r) => h("li", {}, `${r.reviewer} (${r.credentials.map((c) => `${c.body} ${c.membership_no}: ${c.status.toLowerCase()}`).join("; ")}) — `,
        Badge({ tone: CONCLUSION_TONE[r.conclusion], label: humanize(r.conclusion) }), r.recorded_on_behalf ? ` · recorded on their behalf (ref ${r.source_reference})` : ""))))),
    h("button", { className: "btn btn-secondary", id: "check-statement", onClick: a.checkStatement }, "Check the statement again"));
}

function stageCard(val, d, s, a) {
  const meta = ((val.guide && val.guide.stages) || []).find((x) => x.id === s.stage) || {};
  const manage = !!(val.me && val.me.can_manage);
  const open = d.status === "OPEN" || d.status === "DRAFT";
  const assigns = d.assignments.filter((x) => x.stage === s.stage);
  const choices = open && manage ? assignable(val.panel, val.guide, d, s.stage) : [];
  const af = val.form && val.form.kind === "assign" && val.form.stage === s.stage ? val.form.f : {};
  return h("div", { className: "card", "data-stage": s.stage, style: "margin-top:12px;" },
    h("div", { style: "display:flex; justify-content:space-between; gap:8px; flex-wrap:wrap;" }, h("h3", {}, s.label),
      h("span", {}, Badge({ tone: STAGE_TONE[s.status], label: STAGE_STATUS_TEXT[s.status] || humanize(s.status) }), ` ${s.signed} of ${s.reviewers_needed} signed`)),
    meta.question ? h("div", { style: "color: var(--ink-500);" }, meta.question) : null,
    assigns.length === 0 ? h("p", {}, "No reviewer assigned.") : assigns.map((x) => reviewerRow(val, d, s.stage, x, a, manage)),
    open && manage ? h("div", { style: "margin-top:8px; display:flex; gap:8px; flex-wrap:wrap; align-items:end;" },
      choices.length ? [h("select", { id: `assign-${s.stage}`, onChange: (e) => a.startForm("assign", { reviewer_id: e.target.value }, { stage: s.stage }) },
        [h("option", { value: "" }, "Choose a reviewer…"), ...choices.map((r) => h("option", { value: r.id, selected: af.reviewer_id === r.id }, `${r.name} (${credentialSummary(r).text.toLowerCase()})`))]),
      h("button", { className: "btn btn-secondary", id: `assign-btn-${s.stage}`, disabled: !af.reviewer_id || val.busy, onClick: () => a.assign(s.stage) }, "Assign")]
        : h("small", { style: "color: var(--ink-500);" }, "No one on the panel who is competent for this stage and not yet assigned.")) : null);
}

function reviewerRow(val, d, stage, asg, a, manage) {
  const r = d.reviewers[asg.reviewer_id] || { name: "(removed)", credentials: [] };
  const st = reviewState(d, stage, asg.reviewer_id);
  const mode = actingMode(val.me, r.id ? r : null);
  const cs = r.id ? credentialSummary(r) : { tone: "warn", text: "" };
  const form = val.form && val.form.stage === stage && val.form.reviewerId === asg.reviewer_id ? val.form : null;
  const status = d.status;
  return h("div", { className: "card", "data-assignment": asg.id, style: "margin-top:8px;" },
    h("div", { style: "display:flex; justify-content:space-between; gap:8px; flex-wrap:wrap;" },
      h("strong", {}, r.name), h("span", {}, Badge({ tone: cs.tone, label: cs.text }), " ",
        st.declared ? Badge({ tone: st.independent ? "pass" : "fail", label: st.independent ? "Declared independent" : "Declared a conflict" }) : Badge({ tone: "warn", label: "Independence not declared" }))),
    st.declaration && st.declaration.on_behalf ? h("small", {}, `Declaration recorded on their behalf (ref ${st.declaration.source_reference || "—"})`) : null,
    st.signed ? signedReview(val, d, st.signed, a, manage) : null,
    st.draft && !form ? h("small", { style: "display:block;" }, "A draft review is saved and not yet signed.") : null,
    mode === "none" && !st.signed ? h("small", { style: "display:block; color: var(--ink-500);" }, r.user_id ? "Only this reviewer can act for themselves." : "Only an owner or administrator can record this reviewer's documents.") : null,
    mode !== "none" && status === "OPEN" ? h("div", { style: "display:flex; gap:8px; flex-wrap:wrap; margin-top:8px;" },
      !st.declared ? h("button", { className: "btn btn-secondary", id: `declare-${stage}-${asg.reviewer_id}`, onClick: () => a.startForm("declare", { confirmations: {}, independent: true, details: "", source_reference: "" }, { stage, reviewerId: asg.reviewer_id, mode }) }, "Declare independence") : null,
      st.declared ? h("button", { className: "btn btn-secondary", id: `declare-${stage}-${asg.reviewer_id}`, onClick: () => a.startForm("declare", { confirmations: {}, independent: true, details: "", source_reference: "" }, { stage, reviewerId: asg.reviewer_id, mode }) }, "Update declaration") : null,
      st.independent ? h("button", { className: "btn btn-primary", id: `review-${stage}-${asg.reviewer_id}`, onClick: () => a.startReview(stage, asg.reviewer_id, mode) }, st.signed ? "Write a new version" : st.draft ? "Continue draft" : "Write review") : null) : null,
    mode === "on_behalf" && status === "OPEN" ? h("small", { style: "display:block; color: var(--ink-500);" }, "You will be recording this on their behalf, with a reference to their signed document.") : null,
    form && form.kind === "declare" ? declareForm(val, form, a) : null,
    form && form.kind === "review" ? reviewFormView(val, form, st, a) : null,
    (d.status === "DRAFT" || d.status === "OPEN") && manage && !st.signed ? h("button", { className: "btn btn-secondary", style: "margin-top:8px;", onClick: () => a.unassign(asg.id) }, "Remove from this stage") : null);
}

function declareForm(val, form, a) {
  const f = form.f;
  return h("div", { className: "card", id: "declare-form" }, h("h4", {}, "Independence declaration"),
    CONFIRMATIONS.map(([k, label]) => h("label", { style: "display:block;" }, h("input", { type: "checkbox", id: `conf-${k}`, checked: !!f.confirmations[k], onChange: (e) => a.confirmChange(k, e.target.checked) }), ` ${label}`)),
    field("If any is not true, describe the relationship or interest", "decl-details", area("decl-details", f, "details", a, 2), "A reviewer who cannot confirm all four cannot review or sign."),
    form.mode === "on_behalf" ? field("Reference to their signed declaration", "decl-ref", text("decl-ref", f, "source_reference", a, "e.g. signed PDF received 2 Oct 2026, ref ABC-17")) : null,
    h("div", { style: "display:flex; gap:8px;" },
      h("button", { className: "btn btn-primary", id: "decl-submit", disabled: val.busy, onClick: a.submitDeclaration }, "Record declaration"), h("button", { className: "btn btn-secondary", onClick: a.cancelForm }, "Cancel")));
}

function reviewFormView(val, form, st, a) {
  const f = form.f, g = val.guide || { conclusions: {}, severities: [] };
  return h("div", { className: "card", id: "review-form" }, h("h4", {}, "Review"),
    field("Conclusion", "rv-concl", select("rv-concl", f, "conclusion", a, [["", "Choose…"], ...entries(g.conclusions).map(([c, d]) => [c, d])])),
    field("What was reviewed", "rv-scope", area("rv-scope", f, "scope_reviewed", a, 2)),
    field("Basis (framework and standards applied)", "rv-basis", text("rv-basis", f, "basis", a, "e.g. IFRS as issued by the IASB; ISA 500")),
    field("Limitations (required if unable to assess)", "rv-lim", area("rv-lim", f, "limitations", a, 2)),
    h("h5", {}, "Observations"),
    f.observations.map((o, i) => h("div", { className: "card", "data-observation-row": i },
      h("select", { id: `obs-sev-${i}`, onChange: (e) => a.obsChange(i, "severity", e.target.value) }, g.severities.map((s) => h("option", { value: s, selected: o.severity === s }, humanize(s)))),
      h("textarea", { id: `obs-text-${i}`, rows: 2, placeholder: "What did you find?", value: o.text, onInput: (e) => a.obsChange(i, "text", e.target.value) }, o.text),
      h("input", { id: `obs-rec-${i}`, type: "text", placeholder: "Recommendation (optional)", value: o.recommendation, onInput: (e) => a.obsChange(i, "recommendation", e.target.value) }),
      h("button", { className: "btn btn-secondary", onClick: () => a.removeObs(i) }, "Remove"))),
    h("button", { className: "btn btn-secondary", id: "add-observation", onClick: a.addObs }, "Add an observation"),
    h("label", { style: "display:block; margin-top:8px;" }, h("input", { type: "checkbox", id: "rv-competence", checked: !!f.competence_confirmed, onChange: (e) => a.formChange("competence_confirmed", e.target.checked) }),
      " I am competent to give a conclusion on this stage."),
    form.mode === "on_behalf" ? field("Reference to their signed report", "rv-ref", text("rv-ref", f, "source_reference", a, "e.g. signed report PDF, ref ABC-18")) : null,
    h("div", { style: "display:flex; gap:8px; margin-top:8px;" },
      h("button", { className: "btn btn-secondary", id: "rv-save", disabled: val.busy, onClick: () => a.saveReview(false) }, "Save draft"),
      h("button", { className: "btn btn-primary", id: "rv-sign", disabled: val.busy, onClick: () => a.saveReview(true) }, "Sign — this cannot be edited afterwards"),
      h("button", { className: "btn btn-secondary", onClick: a.cancelForm }, "Cancel")));
}

function signedReview(val, d, rv, a, manage) {
  const rf = val.form && val.form.kind === "respond" ? val.form : null;
  return h("div", { className: "card", "data-review": rv.id, style: "margin-top:8px;" },
    h("div", {}, Badge({ tone: CONCLUSION_TONE[rv.conclusion], label: humanize(rv.conclusion) }), ` signed ${when(rv.signed_at)} · version ${rv.version}${rv.on_behalf ? ` · recorded on their behalf (ref ${rv.source_reference})` : ""}`),
    h("div", { style: "color: var(--ink-500);" }, `Reviewed: ${rv.scope_reviewed} · Basis: ${rv.basis}`),
    rv.limitations ? h("div", {}, `Limitations: ${rv.limitations}`) : null,
    (rv.observations || []).map((o) => h("div", { "data-observation": o.id, style: "margin-top:6px;" },
      Badge({ tone: SEVERITY_TONE[o.severity], label: humanize(o.severity) }), ` ${o.text}`, o.recommendation ? h("div", { style: "color: var(--ink-500);" }, `Recommendation: ${o.recommendation}`) : null,
      o.response ? h("div", {}, Badge({ tone: "info", label: `Management: ${humanize(o.response.status)}` }), ` ${o.response.note}`)
        : manage && d.status === "OPEN" ? h("button", { className: "btn btn-secondary", id: `respond-${o.id}`, onClick: () => a.startForm("respond", { status: "ACCEPTED", note: "" }, { reviewId: rv.id, obsId: o.id }) }, "Respond") : null,
      rf && rf.obsId === o.id ? h("div", { className: "card", id: "respond-form" },
        field("Management response", "resp-status", select("resp-status", rf.f, "status", a, [["ACCEPTED", "Accepted — we will act"], ["DISPUTED", "Disputed — we disagree"], ["REMEDIATED", "Already remediated"]])),
        field("Explain", "resp-note", area("resp-note", rf.f, "note", a, 2)),
        h("button", { className: "btn btn-primary", id: "resp-submit", disabled: val.busy, onClick: a.submitResponse }, "Record response"), h("button", { className: "btn btn-secondary", onClick: a.cancelForm }, "Cancel")) : null)));
}

export function canSee(role) { return allowed(role, PERMISSIONS.AUDIT_READ); }
