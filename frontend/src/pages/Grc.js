import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState, EmptyState } from "../components/DataState.js";
import { TABS, canPrepare, canApprove, bandOf, bandInfo, riskStatus, actionStatus, obState, riskMoves, actionMoves } from "../lib/grc.js";

/**
 * Governance, Risk and Compliance. Scores are people's judgements on a 1 to 5 scale and are shown with the arithmetic (likelihood x impact).
 * 'Met' on an obligation is an attestation by a named person. The page contains no legal text.
 */
const Badge = ({ tone, label, id }) => h("span", { className: `badge badge-${tone || "neutral"}`, id }, label);
const note = (t, kind = "info") => (t ? h("div", { className: `alert alert-${kind}`, style: "margin-bottom:12px;", role: kind === "error" ? "alert" : "status" }, t) : null);
const field = (label, id, inp, hint) => h("div", { className: "field" }, h("label", { for: id }, label), inp, hint ? h("small", { style: "color: var(--ink-500);" }, hint) : null);
const text = (id, f, k, on, ph) => h("input", { id, type: "text", value: f[k] == null ? "" : f[k], placeholder: ph || "", onInput: (e) => on(k, e.target.value) });
const area = (id, f, k, on, rows = 3) => h("textarea", { id, rows, onInput: (e) => on(k, e.target.value) }, f[k] || "");
const sel = (id, f, k, on, opts) => h("select", { id, onChange: (e) => on(k, e.target.value) }, opts.map(([v, l]) => h("option", { value: v, selected: String(f[k]) === String(v) }, l)));
const table = (head, rows, id) => h("div", { className: "table-scroll" }, h("table", { className: "data-table", id }, h("thead", {}, h("tr", {}, head.map(([l, right]) => h("th", { style: right ? "text-align:right;" : undefined }, l)))), h("tbody", {}, rows)));
const td = (v, right) => h("td", { style: right ? "text-align:right;" : undefined }, v);
const btn = (label, id, onClick, kind = "secondary", disabled = false) => h("button", { className: `btn btn-${kind}`, id, disabled, onClick }, label);
const score = (l, i) => `${l} x ${i} = ${l * i}`;
const scoreOpts = (labels) => [1, 2, 3, 4, 5].map((n) => [String(n), `${n} - ${labels[n] || ""}`]);
const checks = (idp, ids, items, onToggle, label) => h("div", {}, items.length === 0 ? h("small", { style: "color: var(--ink-500);" }, "Nothing available to link.") : items.map((c) =>
  h("label", { style: "display:block;" }, h("input", { type: "checkbox", id: `${idp}-${c.id}`, checked: ids.includes(c.id), onChange: () => onToggle(c.id) }), ` ${label(c)}`)));

export function Grc({ gc, role, userId, loading, onRetry, actions }) {
  return h("div", {},
    h("h1", {}, "Governance, Risk and Compliance"),
    note("Scores are judgements entered by people (likelihood x impact, 1 to 5). ASAVEXA applies fixed bands and holds a second person to account for acceptance and verification. It contains no legal text and is not legal advice or an audit opinion.", "warning"),
    gc.error ? ErrorState({ message: gc.error, onRetry }) : null,
    note(gc.notice, "success"),
    loading ? LoadingState() : h("div", {},
      h("div", { className: "tabs", role: "tablist", style: "display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px;" },
        TABS.map(([id, label]) => h("button", { className: `btn ${gc.tab === id ? "btn-primary" : "btn-secondary"}`, role: "tab", id: `gc-tab-${id}`, "aria-selected": gc.tab === id ? "true" : "false", onClick: () => actions.setTab(id) }, label)),
        btn("Download register (CSV)", "gc-export", () => actions.exportRegister(), "secondary", gc.busy)),
      gc.busy ? h("div", { style: "color: var(--ink-500);" }, "Working...") : null,
      gc.tab === "overview" ? overview(gc, role, actions) : gc.tab === "risks" ? (gc.riskForm ? riskForm(gc, actions) : gc.risk ? riskDetail(gc, role, userId, actions) : risks(gc, role, actions))
        : gc.tab === "actions" ? actionsTab(gc, role, userId, actions) : obligations(gc, role, actions)));
}

// ---------------------------------------------------------------- overview
function heat(d) {
  const c = d.heatmap.cells;
  return h("table", { className: "data-table", id: "gc-heatmap", style: "max-width:560px;" },
    h("thead", {}, h("tr", {}, h("th", {}, "Likelihood \\ Impact"), [1, 2, 3, 4, 5].map((i) => h("th", { style: "text-align:center;" }, `${i} ${d.heatmap.impact_labels[i]}`)))),
    h("tbody", {}, [5, 4, 3, 2, 1].map((l) => h("tr", {}, h("th", {}, `${l} ${d.heatmap.likelihood_labels[l]}`),
      [1, 2, 3, 4, 5].map((i) => { const b = bandInfo(bandOf(l * i)), n = c[l - 1][i - 1];
        return h("td", { className: `heat heat-${b.tone}`, "data-l": String(l), "data-i": String(i), title: `${b.label} (${l * i})`, style: "text-align:center;" }, n ? h("strong", {}, String(n)) : "·"); })))));
}
const list = (items, render, empty) => (items.length ? h("ul", {}, items.map(render)) : h("div", { style: "color: var(--ink-500);" }, empty));
function overview(gc, role, a) {
  const d = gc.dash;
  if (!d) return EmptyState({ title: "No data yet", message: "Add a risk to begin." });
  const k = d.counts, at = d.attention;
  return h("div", { id: "gc-overview" },
    h("div", { className: "card", style: "margin-bottom:12px;" }, h("h3", {}, "At a glance"),
      h("div", { id: "gc-counts" }, `${k.live_risks} live risk(s); ${k.critical_or_high} high or critical; ${k.above_appetite} above appetite; ${k.actions_open} open action(s); ${k.actions_awaiting_verification} awaiting verification; ${k.obligations_overdue} obligation(s) overdue, ${k.obligations_due_soon} due soon.`),
      h("div", { style: "margin-top:8px;" }, h("strong", {}, "Risk appetite: "), h("span", { id: "gc-appetite" }, `a residual score above ${d.appetite} (of 25) is outside appetite.`)),
      canApprove(role) ? h("div", { className: "field", style: "margin-top:8px;" }, h("label", { for: "gc-appetite-in" }, "Change the appetite (1 to 25)"),
        h("input", { id: "gc-appetite-in", type: "text", value: gc.appetiteInput, onInput: (e) => a.appetiteChange(e.target.value) }), " ", btn("Save appetite", "gc-appetite-save", () => a.saveAppetite(), "secondary", gc.busy)) : null),
    h("div", { className: "card", style: "margin-bottom:12px;" }, h("h3", {}, "Residual risk map"), heat(d), h("small", { style: "color: var(--ink-500);" }, d.heatmap.meaning)),
    h("div", { className: "card", style: "margin-bottom:12px;" }, h("h3", {}, "Needs attention"),
      h("h4", {}, "Above appetite with no action plan"), list(at.above_appetite_without_plan, (r) => h("li", {}, `${r.ref} ${r.title} (score ${r.residual_score}, owner ${r.owner})`), "None."),
      h("h4", {}, "Acceptances waiting for a decision"), list(at.acceptances_waiting, (r) => h("li", {}, `${r.ref} ${r.title} (score ${r.residual_score})`), "None."),
      h("h4", {}, "Risk reviews overdue"), list(at.reviews_overdue, (r) => h("li", {}, `${r.ref} ${r.title}, review was due ${r.next_review}`), "None."),
      h("h4", {}, "Actions overdue"), list(at.actions_overdue, (x) => h("li", {}, `${x.ref} ${x.title} (${x.risk_ref}), due ${x.due}, ${x.owner}`), "None."),
      h("h4", {}, "Actions waiting to be verified"), list(at.actions_to_verify, (x) => h("li", {}, `${x.ref} ${x.title} (${x.risk_ref}), done by ${x.completed_by}`), "None."),
      h("h4", {}, "Obligations overdue"), list(at.obligations_overdue, (o) => h("li", {}, `${o.ref} ${o.title}, was due ${o.next_due}, ${o.owner}`), "None."),
      h("h4", {}, "Obligations due soon"), list(at.obligations_due_soon, (o) => h("li", {}, `${o.ref} ${o.title}, due ${o.next_due}, ${o.owner}`), "None.")),
    h("div", { className: "card" }, h("h3", {}, "What this does not tell you"), h("ul", {}, d.limitations.map((l) => h("li", {}, l)))));
}

// ---------------------------------------------------------------- risks
function risks(gc, role, a) {
  return h("div", { id: "gc-risks" },
    h("div", { style: "display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-bottom:12px;" },
      canPrepare(role) ? btn("Add a risk", "risk-new", () => a.newRisk(), "primary") : null,
      h("label", { for: "risk-filter" }, "Show"),
      h("select", { id: "risk-filter", onChange: (e) => a.setFilter(e.target.value) }, [["", "All"], ["ASSESSED", "Assessed"], ["TREATING", "Being treated"], ["ACCEPTANCE_REQUESTED", "Acceptance waiting"], ["ACCEPTED", "Accepted"], ["CLOSED", "Closed"]].map(([v, l]) => h("option", { value: v, selected: gc.filter === v }, l)))),
    gc.risks.length === 0 ? EmptyState({ title: "No risks recorded", message: "Add the risks you want to keep an eye on, score them, and decide what to do about each." })
      : table([["Ref"], ["Risk"], ["Category"], ["Owner"], ["Residual", true], ["Status"], [""]], gc.risks.map((r) => h("tr", { "data-risk": r.id }, td(r.ref), td(r.title), td(r.category_text), td(r.owner),
        td(h("span", {}, `${r.residual_score} `, Badge({ tone: bandInfo(r.residual_band).tone, label: bandInfo(r.residual_band).label }), r.above_appetite ? " above appetite" : ""), true),
        td(h("span", {}, Badge({ tone: riskStatus(r.status).tone, label: riskStatus(r.status).label }), r.review_overdue ? " review overdue" : "")),
        td(btn("Open", `risk-open-${r.id}`, () => a.openRisk(r.id))))), "gc-risk-table"));
}

function riskForm(gc, a) {
  const f = gc.riskForm, o = gc.options, inh = f.inherent_l * f.inherent_i, res = f.residual_l * f.residual_i;
  return h("div", { className: "card", id: "risk-form" }, h("h3", {}, f.id ? "Edit risk" : "Add a risk"),
    field("Title", "rf-title", text("rf-title", f, "title", a.riskChange, "for example Cash taken from the till")),
    field("What could happen, and why it matters", "rf-desc", area("rf-desc", f, "description", a.riskChange)),
    field("Category", "rf-cat", sel("rf-cat", f, "category", a.riskChange, Object.entries(o.categories))),
    field("Risk owner", "rf-owner", text("rf-owner", f, "owner", a.riskChange, "the person accountable")),
    h("h4", {}, `Before any controls (inherent): ${score(f.inherent_l, f.inherent_i)}`),
    field("Likelihood", "rf-il", sel("rf-il", f, "inherent_l", a.riskChange, scoreOpts(o.likelihood))), field("Impact", "rf-ii", sel("rf-ii", f, "inherent_i", a.riskChange, scoreOpts(o.impact))),
    h("h4", {}, `After the controls you rely on (residual): ${score(f.residual_l, f.residual_i)}`),
    field("Likelihood", "rf-rl", sel("rf-rl", f, "residual_l", a.riskChange, scoreOpts(o.likelihood))), field("Impact", "rf-ri", sel("rf-ri", f, "residual_i", a.riskChange, scoreOpts(o.impact))),
    res < inh ? field("What reduces the risk? (required when residual is lower)", "rf-just", area("rf-just", f, "residual_justification", a.riskChange, 2)) : null,
    field("What will you do about it?", "rf-treat", sel("rf-treat", f, "treatment", a.riskChange, Object.entries(o.treatments))),
    field("Next review date", "rf-review", text("rf-review", f, "next_review", a.riskChange, "2026-12-31")),
    h("div", { className: "field" }, h("label", {}, "Controls that help (from the Controls page)"), checks("rf-ctl", f.control_ids, o.controls, a.riskControl, (c) => `${c.code} ${c.name}`)),
    btn("Save risk", "rf-save", () => a.saveRisk(), "primary", gc.busy), " ", btn("Cancel", "rf-cancel", () => a.cancelRisk()));
}

function riskDetail(gc, role, userId, a) {
  const r = gc.risk, m = riskMoves(r, role, userId), acc = r.acceptance, st = riskStatus(r.status);
  return h("div", { id: "gc-risk" },
    btn("Back to risks", "risk-back", () => a.closeRiskView()),
    h("h2", {}, `${r.ref}: ${r.title} `, Badge({ tone: st.tone, label: st.label, id: "risk-status" })),
    h("div", { className: "card", style: "margin-bottom:12px;" },
      h("div", {}, `${r.category_text}. Owner: ${r.owner}. Plan: ${r.treatment_text}.`), r.description ? h("p", {}, r.description) : null,
      h("div", { id: "risk-scores" }, `Inherent ${score(r.inherent_l, r.inherent_i)} (${bandInfo(r.inherent_band).label}). Residual ${score(r.residual_l, r.residual_i)} (${bandInfo(r.residual_band).label})${r.above_appetite ? ", above the risk appetite" : ", within the risk appetite"}.`),
      r.residual_justification ? h("div", {}, `Why the residual is lower: ${r.residual_justification}`) : null,
      h("div", {}, `Next review: ${r.next_review || "—"}${r.review_overdue ? " (overdue)" : ""}.`),
      r.controls.length ? h("div", {}, "Controls: ", r.controls.map((c) => `${c.code} ${c.name}`).join("; ")) : null,
      acc ? h("div", { id: "risk-acceptance", style: "margin-top:8px;" }, h("strong", {}, "Acceptance: "), `requested by ${acc.requested_by}${acc.within_appetite ? " (within appetite, no second approval needed)" : ""}. Reason: ${acc.justification} Review by ${acc.review_by}.`,
        acc.decided_by ? ` Decided by ${acc.decided_by}${acc.decision_note ? ": " + acc.decision_note : ""}.` : " Waiting for a decision by a different person.") : null,
      r.status === "CLOSED" ? h("div", {}, `Closed by ${r.closed_by}: ${r.close_note}`) : null),
    h("div", { style: "display:flex; gap:8px; flex-wrap:wrap; margin-bottom:12px;" },
      m.edit ? btn("Edit", "risk-edit", () => a.editRisk()) : null, m.treat ? btn("Start treatment", "risk-treat", () => a.treatRisk(), "primary", gc.busy) : null,
      m.accept && !gc.acceptForm ? btn("Accept this risk", "risk-accept", () => a.openAccept()) : null, m.addAction ? btn("Add an action", "risk-add-action", () => a.newAction(r.id)) : null),
    gc.acceptForm ? h("div", { className: "card", id: "accept-form", style: "margin-bottom:12px;" }, h("h3", {}, "Accept this risk"),
      h("p", {}, r.above_appetite ? "This risk is above the appetite, so a different person must approve the acceptance." : "This risk is within the appetite, so the acceptance takes effect immediately and is recorded."),
      field("Why is accepting it reasonable?", "ac-just", area("ac-just", gc.acceptForm, "justification", a.acceptChange)), field("Review by", "ac-review", text("ac-review", gc.acceptForm, "review_by", a.acceptChange, "2026-12-31")),
      btn("Submit", "ac-save", () => a.submitAccept(), "primary", gc.busy), " ", btn("Cancel", "ac-cancel", () => a.cancelAccept())) : null,
    m.decide ? h("div", { className: "card", id: "decide-box", style: "margin-bottom:12px;" }, h("h3", {}, "Decide on this acceptance"),
      field("Note (required if you send it back)", "dc-note", area("dc-note", gc.notes, "decide", a.noteChange, 2)),
      btn("Approve acceptance", "dc-approve", () => a.decideAcceptance(true), "primary", gc.busy), " ", btn("Send back", "dc-reject", () => a.decideAcceptance(false), "secondary", gc.busy)) : null,
    m.ownRequest ? note("You asked for this acceptance, so a different person must decide it.") : null,
    m.reopen ? h("div", { className: "card", style: "margin-bottom:12px;" }, field("Reason for reopening", "ro-note", area("ro-note", gc.notes, "reopen", a.noteChange, 2)), btn("Reopen risk", "ro-save", () => a.reopenRisk(), "secondary", gc.busy)) : null,
    m.close ? h("div", { className: "card", style: "margin-bottom:12px;" }, field("Reason for closing (the risk no longer exists or applies)", "cl-note", area("cl-note", gc.notes, "close", a.noteChange, 2)), btn("Close risk", "cl-save", () => a.closeRisk(), "secondary", gc.busy)) : null,
    h("h3", {}, "Actions"), gc.actionForm ? actionForm(gc, a) : null,
    actionPanels(gc, r.actions, role, a),
    r.actions.length === 0 ? h("div", { style: "color: var(--ink-500);" }, "No actions yet.") : actionTable(r.actions, gc, role, userId, a, false),
    h("h3", {}, "History"), h("ul", { id: "risk-history" }, r.history.map((x) => h("li", {}, `${String(x.at).slice(0, 10)} ${x.event.replace(/_/g, " ").toLowerCase()} by ${x.by}${x.note ? ": " + x.note : ""}`))));
}

// ---------------------------------------------------------------- actions
function actionForm(gc, a) {
  const f = gc.actionForm;
  return h("div", { className: "card", id: "action-form", style: "margin:12px 0;" }, h("h3", {}, f.id ? "Edit action" : "Add an action"),
    !f.id && !f.fixedRisk ? field("For which risk", "af-risk", h("select", { id: "af-risk", onChange: (e) => a.actionChange("risk_id", e.target.value) }, [h("option", { value: "" }, "Choose a risk"), ...gc.risks.filter((r) => r.status !== "CLOSED").map((r) => h("option", { value: r.id, selected: f.risk_id === r.id }, `${r.ref} ${r.title}`))])) : null,
    field("What will be done", "af-title", text("af-title", f, "title", a.actionChange)), field("Details", "af-desc", area("af-desc", f, "description", a.actionChange, 2)),
    field("Who is responsible", "af-owner", text("af-owner", f, "owner", a.actionChange)), field("Due date", "af-due", text("af-due", f, "due", a.actionChange, "2026-12-31")),
    btn("Save action", "af-save", () => a.saveAction(), "primary", gc.busy), " ", btn("Cancel", "af-cancel", () => a.cancelAction()));
}

function actionTable(rows, gc, role, userId, a, withRisk) {
  return h("div", {}, table([["Ref"], ...(withRisk ? [["Risk"]] : []), ["Action"], ["Owner"], ["Due"], ["Status"], [""]], rows.map((x) => {
    const mv = actionMoves(x, role, userId), st = actionStatus(x.status);
    return h("tr", { "data-action": x.id }, td(x.ref), ...(withRisk ? [td(x.risk_ref)] : []), td(x.title), td(x.owner), td(x.due + (x.overdue ? " (overdue)" : "")), td(Badge({ tone: st.tone, label: st.label })),
      td(h("div", { style: "display:flex; gap:6px; flex-wrap:wrap;" },
        mv.edit ? btn("Edit", `act-edit-${x.id}`, () => a.editAction(x)) : null, mv.complete ? btn("Mark done", `act-done-${x.id}`, () => a.openDone(x), "primary") : null, mv.cancel ? btn("Cancel", `act-cancel-${x.id}`, () => a.cancelActionRec(x.id)) : null,
        mv.verify ? btn("Verify", `act-verify-${x.id}`, () => a.verifyAction(x.id, true), "primary", gc.busy) : null, mv.verify ? btn("Send back", `act-back-${x.id}`, () => a.verifyAction(x.id, false), "secondary", gc.busy) : null,
        mv.ownCompletion ? h("small", {}, "You did this, so someone else must verify it.") : null)));
  }), withRisk ? "gc-action-table" : "gc-risk-actions"),
  rows.some((x) => x.status === "DONE" || x.evidence.length) ? h("div", { style: "margin-top:6px;" }, rows.filter((x) => x.completion_note).map((x) => h("div", {}, h("small", {}, `${x.ref}: ${x.completion_note}${x.evidence.length ? " Evidence: " + x.evidence.map((e) => e.filename).join(", ") : ""}${x.verify_note ? " Reviewer: " + x.verify_note : ""}`)))) : null);
}

function actionsTab(gc, role, userId, a) {
  return h("div", { id: "gc-actions" },
    canPrepare(role) && !gc.actionForm ? btn("Add an action", "act-new", () => a.newAction(""), "primary") : null, gc.actionForm ? actionForm(gc, a) : null,
    actionPanels(gc, gc.actions, role, a),
    gc.actions.length === 0 ? EmptyState({ title: "No actions yet", message: "Open a risk and add what will be done about it." }) : actionTable(gc.actions, gc, role, userId, a, true),);
}

function actionPanels(gc, rows, role, a) {
  const d = gc.doneForm, open = rows.find((x) => d && x.id === d.id);
  return h("div", {},
    d && open ? h("div", { className: "card", id: "done-form", style: "margin:12px 0;" }, h("h3", {}, `Mark ${open.ref} as done`),
      field("What was done", "dn-note", area("dn-note", d, "note", a.doneChange, 3)),
      h("div", { className: "field" }, h("label", {}, "Evidence (from the Evidence Vault, optional)"), checks("dn-ev", d.evidence_ids, gc.vault, a.doneEvidence, (e) => e.original_filename)),
      btn("Mark done", "dn-save", () => a.submitDone(), "primary", gc.busy), " ", btn("Cancel", "dn-cancel", () => a.cancelDone())) : null,
    gc.cancelId ? h("div", { className: "card", id: "cancel-form", style: "margin:12px 0;" }, field("Why is it being cancelled?", "cx-note", area("cx-note", gc.notes, "cancel", a.noteChange, 2)), btn("Cancel the action", "cx-save", () => a.confirmCancelAction(), "secondary", gc.busy), " ", btn("Keep it", "cx-keep", () => a.keepAction())) : null,
    rows.some((x) => x.status === "DONE") && canApprove(role) ? h("div", { className: "field", style: "margin-top:8px;" }, h("label", { for: "vf-note" }, "Note for verifying or sending back (a note is required to send back)"), area("vf-note", gc.notes, "verify", a.noteChange, 2)) : null);
}

// ---------------------------------------------------------------- obligations
function obligations(gc, role, a) {
  const f = gc.obForm, o = gc.options, m = gc.metForm;
  return h("div", { id: "gc-obligations" },
    note("Obligations are entered by people from their own legal, contract or policy sources. ASAVEXA ships none and does not check that what you enter is correct or complete.", "info"),
    canPrepare(role) && !f ? btn("Add an obligation", "ob-new", () => a.newObligation(), "primary") : null,
    f ? h("div", { className: "card", id: "ob-form", style: "margin:12px 0;" }, h("h3", {}, f.id ? "Edit obligation" : "Add an obligation"),
      field("Title", "of-title", text("of-title", f, "title", a.obChange, "for example File the annual return")),
      field("Where it comes from", "of-type", sel("of-type", f, "source_type", a.obChange, Object.entries(o.source_types))), field("Owed to (regulator, counterparty, board)", "of-auth", text("of-auth", f, "authority", a.obChange)),
      field("Where in the source (section, clause)", "of-ref", text("of-ref", f, "source_ref", a.obChange)), field("Link to the source (optional)", "of-url", text("of-url", f, "source_url", a.obChange, "https://")),
      field("What must be done", "of-desc", area("of-desc", f, "description", a.obChange, 2)), field("Who is responsible", "of-owner", text("of-owner", f, "owner", a.obChange)),
      field("How often", "of-freq", sel("of-freq", f, "frequency", a.obChange, o.frequencies.map((x) => [x, x.replace(/_/g, " ").toLowerCase()]))), field("Next due date", "of-due", text("of-due", f, "next_due", a.obChange, "2026-12-31")),
      h("div", { className: "field" }, h("label", {}, "Controls that help (optional)"), checks("of-ctl", f.control_ids, o.controls, a.obControl, (c) => `${c.code} ${c.name}`)),
      btn("Save obligation", "of-save", () => a.saveObligation(), "primary", gc.busy), " ", btn("Cancel", "of-cancel", () => a.cancelObligation())) : null,
    m ? h("div", { className: "card", id: "met-form", style: "margin:12px 0;" }, h("h3", {}, "Record that this was met"),
      field("Date it was met", "mf-date", text("mf-date", m, "met_on", a.metChange)), field("How it was met", "mf-note", area("mf-note", m, "note", a.metChange, 2)),
      h("div", { className: "field" }, h("label", {}, "Evidence (optional)"), checks("mf-ev", m.evidence_ids, gc.vault, a.metEvidence, (e) => e.original_filename)),
      h("small", {}, "This is a statement by you that it was done. ASAVEXA does not check it."), h("div", {}, btn("Record", "mf-save", () => a.submitMet(), "primary", gc.busy), " ", btn("Cancel", "mf-cancel", () => a.cancelMet()))) : null,
    gc.retireId ? h("div", { className: "card", id: "retire-form", style: "margin:12px 0;" }, field("Why is it no longer an obligation?", "rt-note", area("rt-note", gc.notes, "retire", a.noteChange, 2)), btn("Retire", "rt-save", () => a.confirmRetire(), "secondary", gc.busy), " ", btn("Keep it", "rt-keep", () => a.keepObligation())) : null,
    gc.obligations.length === 0 ? EmptyState({ title: "No obligations recorded", message: "Add the laws, contract terms and policies you must meet, with due dates." })
      : table([["Ref"], ["Obligation"], ["Owed to"], ["Owner"], ["Frequency"], ["Next due"], ["State"], [""]], gc.obligations.map((x) => { const st = obState(x.state);
        return h("tr", { "data-ob": x.id }, td(h("span", {}, x.ref)), td(h("span", {}, x.title, x.source_url ? h("a", { href: x.source_url, target: "_blank", rel: "noopener noreferrer", style: "margin-left:6px;" }, "source") : null)), td(x.authority), td(x.owner), td(x.frequency.replace(/_/g, " ").toLowerCase()),
          td(x.next_due || "—"), td(Badge({ tone: st.tone, label: st.label })), td(canPrepare(role) && x.state !== "RETIRED" ? h("div", { style: "display:flex; gap:6px; flex-wrap:wrap;" },
            x.next_due ? btn("Mark met", `ob-met-${x.id}`, () => a.openMet(x), "primary") : null, btn("Edit", `ob-edit-${x.id}`, () => a.editObligation(x)), btn("Retire", `ob-retire-${x.id}`, () => a.retireObligation(x.id))) : null)); }), "gc-ob-table"),
    gc.obligations.some((x) => x.history.length) ? h("div", { className: "card", style: "margin-top:12px;" }, h("h3", {}, "Recent attestations"), h("ul", { id: "ob-history" }, gc.obligations.flatMap((x) => x.history.map((e) => ({ x, e }))).sort((p, q) => String(q.e.at).localeCompare(String(p.e.at))).slice(0, 10)
      .map(({ x, e }) => h("li", {}, `${x.ref} ${x.title}: due ${e.due}, met ${e.met_on}${e.late ? " (late)" : ""} by ${e.by}. ${e.note}`)))) : null);
}
