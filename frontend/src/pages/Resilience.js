import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState } from "../components/DataState.js";
import { TABS, DIRECTION_TEXT, LOSS_KIND_TEXT, CATEGORY_TEXT, IMPACT_TEXT, DRILL_TEXT, ATTENTION_TONE, canPrepare, canApprove, statusOf, words, who, thresholdText, objectiveText,
  canRecordReading, canDecideKri, canRetireKri, canConfirmReading, canReviewLoss, canDecideProcess, canRetireProcess, canTestProcess, canDecideDrill, ownWorkText } from "../lib/resilience.js";

/**
 * Risk indicators and resilience. It records and checks what people type in; it measures nothing and connects to no system.
 * Thresholds and recovery objectives cannot be changed once approved. A different person approves, confirms or reviews each record.
 */
const Badge = ({ tone, label, id }) => h("span", { className: `badge badge-${tone || "neutral"}`, id }, label);
const St = (s) => Badge({ ...statusOf(s) });
const note = (t, kind = "info", id) => (t ? h("div", { className: `alert alert-${kind}`, id, style: "margin-bottom:12px;", role: kind === "error" ? "alert" : "status" }, t) : null);
const field = (l, id, inp, hint) => h("div", { className: "field" }, h("label", { for: id }, l), inp, hint ? h("small", { style: "color: var(--ink-500);" }, hint) : null);
const text = (rs, a, form, k, id, ph) => h("input", { id, type: "text", value: (rs.forms[form] || {})[k] == null ? "" : (rs.forms[form] || {})[k], placeholder: ph || "", onInput: (e) => a.setForm(form, k, e.target.value) });
const area = (rs, a, form, k, id) => h("textarea", { id, rows: 3, onInput: (e) => a.setForm(form, k, e.target.value) }, (rs.forms[form] || {})[k] || "");
const sel = (rs, a, form, k, id, opts, blank) => h("select", { id, onChange: (e) => a.setForm(form, k, e.target.value, true) },
  [...(blank ? [h("option", { value: "" }, blank)] : []), ...opts.map(([v, l]) => h("option", { value: v, selected: String((rs.forms[form] || {})[k]) === String(v) }, l))]);
const btn = (l, id, onClick, kind = "secondary", disabled = false) => h("button", { className: `btn btn-${kind}`, id, disabled, onClick }, l);
const row = (...b) => h("div", { style: "display:flex; gap:8px; flex-wrap:wrap; margin:8px 0; align-items:end;" }, b.filter(Boolean));
const none = (t = "None.") => h("div", { style: "color: var(--ink-500);" }, t);
const card = (title, id, ...kids) => h("div", { className: "card", id, style: "margin-bottom:16px;" }, h("h3", {}, title), ...kids);
const hist = (items) => h("ul", {}, (items || []).map((x) => h("li", {}, `${String(x.at).slice(0, 10)} ${String(x.event).replace(/_/g, " ").toLowerCase()} by ${x.by}${x.note ? ": " + x.note : ""}`)));
const noteBox = (rs, a, key, l, id) => field(l, id || `note-${key}`, h("textarea", { id: id || `note-${key}`, rows: 2, onInput: (e) => a.setNote(key, e.target.value) }, rs.notes[key] || ""));
const formError = (rs, name) => (rs.formError && rs.formError.form === name ? note(rs.formError.text, "error", `${name}-problem`) : null);
const docs = (rs, a, form, id) => field("Attach a document (optional)", id, sel(rs, a, form, "evidence_id", id, (rs.vault || []).map((e) => [e.id, e.original_filename || e.filename || e.id]), "No document"), "A document from the Evidence Vault. Its file fingerprint is kept.");
const fileList = (list) => (list && list.length ? h("div", { style: "font-size:0.9em; color: var(--ink-500);" }, list.map((e) => `${e.filename} (fingerprint ${String(e.file_hash).slice(0, 12)})`).join("; ")) : null);
const risks = (rs) => (rs.options && rs.options.risks) || [];
const opt = (o) => Object.entries(o);

export function Resilience({ rs, role, userId, loading, onRetry, actions: a }) {
  return h("div", {},
    h("h1", {}, "Risk indicators and resilience"),
    note("This workspace records and checks what people type in. It measures nothing and connects to no system. Thresholds and recovery objectives cannot be changed once approved, and a different person approves, confirms or reviews each record. A rating or a met objective is arithmetic against your own numbers, not an assessment of how safe you are.", "info", "rs-banner"),
    rs.error ? ErrorState({ message: rs.error, onRetry }) : null,
    note(rs.notice, "success", "rs-notice"),
    loading ? LoadingState() : h("div", {},
      h("div", { className: "tabs", role: "tablist", style: "display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px;" },
        TABS.map(([id, l]) => h("button", { className: `btn ${rs.tab === id ? "btn-primary" : "btn-secondary"}`, role: "tab", id: `rs-tab-${id}`, "aria-selected": rs.tab === id ? "true" : "false", onClick: () => a.setTab(id) }, l))),
      rs.busy ? h("div", { style: "color: var(--ink-500);" }, "Working...") : null,
      rs.tab === "overview" ? overview(rs, role, a) : rs.tab === "kris" ? kris(rs, role, userId, a) : rs.tab === "losses" ? losses(rs, role, userId, a) : rs.tab === "processes" ? processes(rs, role, userId, a) : drills(rs, role, userId, a)));
}

// ---------------------------------------------------------------- overview
function overview(rs, role, a) {
  const o = rs.ov; if (!o) return none("Nothing loaded yet.");
  const c = o.counts;
  return h("div", {},
    card("What needs attention", "rs-attention", o.attention.length ? h("ul", {}, o.attention.map((x) => h("li", { "data-kind": x.kind }, Badge({ tone: ATTENTION_TONE[x.kind] || "info", label: words(x.kind) }), " ", `${x.count} ${x.text}`))) : none("Nothing needs attention.")),
    card("Counts", "rs-counts", h("ul", {}, [["Active indicators", c.kris_active], ["Red", c.kris_red], ["Amber", c.kris_amber], ["Green", c.kris_green], ["Loss events", c.losses], ["Near misses", c.near_misses],
      ["Approved processes", c.processes_approved], ["Processes of high criticality", c.processes_high], ["Approved continuity tests", c.drills_approved]].map(([l, n]) => h("li", {}, `${l}: ${n}`)))),
    card("Losses recorded (per currency, never added together)", "rs-totals", o.loss_totals.length ? h("ul", {}, o.loss_totals.map((t) => h("li", { "data-currency": t.currency }, `${t.currency}: ${t.total}`))) : none("No losses recorded.")),
    policyCard(rs, role, a),
    card("What this does not do", "rs-limits", h("ul", {}, o.limitations.map((x) => h("li", {}, x)))));
}

function policyCard(rs, role, a) {
  const p = rs.ov.policy, f = rs.forms.policy;
  return card("Settings", "rs-policy", h("p", { id: "rs-policy-meaning" }, p.meaning),
    canApprove(role) && f ? h("div", {},
      row(field("Days before a process is due for a continuity test", "rs-policy-drill", text(rs, a, "policy", "drill_days", "rs-policy-drill")), field("Days before an unreviewed loss event is flagged", "rs-policy-loss", text(rs, a, "policy", "loss_review_days", "rs-policy-loss"))),
      formError(rs, "policy"), btn("Save settings", "rs-policy-save", () => a.savePolicy(), "primary", rs.busy)) : h("p", { style: "color: var(--ink-500);" }, "Only an approver can change these settings."));
}

// ---------------------------------------------------------------- indicators
function kris(rs, role, me, a) {
  const open = rs.sel.kri;
  return h("div", {},
    card("Key risk indicators", "rs-kris", rs.kris.length ? rs.kris.map((k) => h("div", { className: "card", style: "margin-bottom:8px;", "data-kri": k.ref },
      h("div", {}, h("strong", {}, `${k.ref} · ${k.name}`), " ", St(k.status), k.rating ? [" ", St(k.rating)] : null, k.stale ? [" ", Badge({ tone: "warn", label: k.latest ? "Reading overdue" : "No confirmed reading" })] : null),
      h("div", { style: "color: var(--ink-500);" }, `${thresholdText(k)} Owner ${k.owner_name}; a reading every ${k.review_days} day(s)${k.risk_ref ? `; linked to risk ${k.risk_ref}` : ""}.`),
      k.latest ? h("div", {}, `Latest confirmed reading: ${k.latest.value} ${k.unit} on ${k.latest.as_of}`) : null,
      btn(open && open.id === k.id ? "Hide" : "Open", `rs-kri-open-${k.ref}`, () => a.selectKri(open && open.id === k.id ? null : k.id), "secondary", rs.busy))) : none("No indicators yet.")),
    open ? kriDetail(rs, role, me, a, open) : null,
    canPrepare(role) ? card("Propose an indicator", "rs-kri-card",
      h("p", { style: "color: var(--ink-500);" }, "Thresholds cannot be changed once a different person approves them, so set them before you see any reading. To change them later, retire the indicator and propose a new one."),
      row(field("Name", "rs-kri-name", text(rs, a, "kri", "name", "rs-kri-name")), field("Unit", "rs-kri-unit", text(rs, a, "kri", "unit", "rs-kri-unit", "%")), field("Direction", "rs-kri-dir", sel(rs, a, "kri", "direction", "rs-kri-dir", opt(DIRECTION_TEXT)))),
      field("What it measures", "rs-kri-desc", area(rs, a, "kri", "description", "rs-kri-desc")),
      row(field("Amber threshold", "rs-kri-amber", text(rs, a, "kri", "amber", "rs-kri-amber")), field("Red threshold", "rs-kri-red", text(rs, a, "kri", "red", "rs-kri-red")), field("Owner (name)", "rs-kri-owner", text(rs, a, "kri", "owner_name", "rs-kri-owner")),
        field("A reading is expected every (days)", "rs-kri-days", text(rs, a, "kri", "review_days", "rs-kri-days"))),
      risks(rs).length ? field("Linked risk (optional)", "rs-kri-risk", sel(rs, a, "kri", "risk_id", "rs-kri-risk", risks(rs).map((r) => [r.id, `${r.ref} · ${r.title}`]), "No risk")) : null,
      formError(rs, "kri"), btn("Propose indicator", "rs-kri-save", () => a.proposeKri(), "primary", rs.busy)) : null);
}

function kriDetail(rs, role, me, a, k) {
  const key = `kri-${k.id}`, decide = canDecideKri(k, role, me), anyConfirm = k.readings.some((r) => canConfirmReading(r, role, me));
  return card(`${k.ref} · ${k.name}`, "rs-kri-detail",
    h("p", {}, k.description), h("p", {}, St(k.status), k.rating ? [" ", St(k.rating)] : null, ` · proposed by ${who(k.proposed_by, me)}${k.decided_by ? ` · decided by ${who(k.decided_by, me)}` : ""}`),
    k.decision_note ? h("p", {}, `Note: ${k.decision_note}`) : null,
    decide || anyConfirm || canRetireKri(k, role) ? h("div", { id: "rs-kri-notes" }, noteBox(rs, a, key, "Reason (required, at least 10 characters, to reject, retire or reject a reading)")) : null,
    k.status === "PROPOSED" && canApprove(role) && !decide ? h("p", { id: "rs-kri-waiting" }, ownWorkText("proposed this indicator")) : null,
    decide ? h("div", {}, btn("Approve indicator", "rs-kri-approve", () => a.kriStep(k.id, "approve"), "primary", rs.busy), " ", btn("Reject", "rs-kri-reject", () => a.kriStep(k.id, "reject"), "secondary", rs.busy)) : null,
    canRetireKri(k, role) ? h("div", {}, btn("Retire indicator", "rs-kri-retire", () => a.kriStep(k.id, "retire"), "secondary", rs.busy)) : (k.status === "ACTIVE" && canApprove(role) ? h("p", { id: "rs-retire-hint" }, "Confirm or reject the waiting reading before this indicator can be retired.") : null),
    h("div", { id: "rs-readings" }, h("h4", {}, "Readings"),
      k.readings.length ? h("ul", {}, k.readings.map((r) => h("li", { "data-reading": r.seq }, `${r.as_of} · ${r.value} ${k.unit} `, St(r.rating), " ", St(r.status), r.note ? ` — ${r.note}` : "", ` (recorded by ${who(r.recorded_by, me)})`,
        canConfirmReading(r, role, me) ? h("span", {}, " ", btn("Confirm", `rs-rd-${r.seq}-confirm`, () => a.readingStep(k.id, r.id, "confirm"), "secondary", rs.busy), " ", btn("Reject", `rs-rd-${r.seq}-reject`, () => a.readingStep(k.id, r.id, "reject"), "secondary", rs.busy)) :
          (r.status === "RECORDED" && canApprove(role) ? h("span", { style: "color: var(--ink-500);" }, " — you recorded this, so a different person must confirm it") : null)))) : none("No readings yet."),
      canRecordReading(k, role) ? h("div", {}, row(field("Reading", "rs-rd-value", text(rs, a, "reading", "value", "rs-rd-value")), field("As of", "rs-rd-date", text(rs, a, "reading", "as_of", "rs-rd-date", "YYYY-MM-DD"))),
        field("Note (required for an amber or red reading)", "rs-rd-note", text(rs, a, "reading", "note", "rs-rd-note")), formError(rs, "reading"), btn("Record reading", "rs-rd-save", () => a.recordReading(k.id), "primary", rs.busy)) : null),
    h("div", {}, h("h4", {}, "History"), hist(k.history)));
}

// ---------------------------------------------------------------- losses
function losses(rs, role, me, a) {
  const open = rs.sel.loss, f = rs.forms.loss, near = f.kind === "NEAR_MISS";
  return h("div", {},
    card("Loss events and near misses", "rs-losses", rs.losses.length ? rs.losses.map((e) => h("div", { className: "card", style: "margin-bottom:8px;", "data-loss": e.ref },
      h("div", {}, h("strong", {}, `${e.ref} · ${e.title}`), " ", St(e.status), ` · ${e.kind === "LOSS" ? `${e.amount} ${e.currency}` : "near miss"} · ${CATEGORY_TEXT[e.category] || e.category}`, e.review_overdue ? [" ", Badge({ tone: "warn", label: "Review overdue" })] : null),
      h("div", { style: "color: var(--ink-500);" }, `Happened ${e.occurred_on}; found ${e.discovered_on}; recorded by ${who(e.recorded_by, me)}${e.risk_ref ? `; linked to risk ${e.risk_ref}` : ""}`), h("div", {}, e.description), fileList(e.evidence),
      e.status === "REVIEWED" ? h("div", {}, `Cause: ${e.cause} Lesson: ${e.lesson}`) : null, e.status === "VOIDED" ? h("div", {}, `Voided: ${e.void_note}`) : null,
      e.status === "RECORDED" ? btn(open && open.id === e.id ? "Hide" : "Open", `rs-loss-open-${e.ref}`, () => a.selectLoss(open && open.id === e.id ? null : e.id), "secondary", rs.busy) : null)) : none("No loss events yet.")),
    open ? lossDetail(rs, role, me, a, open) : null,
    canPrepare(role) ? card("Record a loss or near miss", "rs-loss-card",
      row(field("Title", "rs-loss-title", text(rs, a, "loss", "title", "rs-loss-title")), field("Kind", "rs-loss-kind", sel(rs, a, "loss", "kind", "rs-loss-kind", opt(LOSS_KIND_TEXT))), field("Category", "rs-loss-cat", sel(rs, a, "loss", "category", "rs-loss-cat", opt(CATEGORY_TEXT)))),
      field("What happened", "rs-loss-desc", area(rs, a, "loss", "description", "rs-loss-desc")),
      row(field("Happened on", "rs-loss-occ", text(rs, a, "loss", "occurred_on", "rs-loss-occ", "YYYY-MM-DD")), field("Found on", "rs-loss-dis", text(rs, a, "loss", "discovered_on", "rs-loss-dis", "YYYY-MM-DD")),
        near ? null : field("Amount lost", "rs-loss-amount", text(rs, a, "loss", "amount", "rs-loss-amount", "0.00")), near ? null : field("Currency", "rs-loss-cur", text(rs, a, "loss", "currency", "rs-loss-cur", "NGN"))),
      risks(rs).length ? field("Linked risk (optional)", "rs-loss-risk", sel(rs, a, "loss", "risk_id", "rs-loss-risk", risks(rs).map((r) => [r.id, `${r.ref} · ${r.title}`]), "No risk")) : null,
      docs(rs, a, "loss", "rs-loss-doc"), formError(rs, "loss"), btn("Record", "rs-loss-save", () => a.recordLoss(), "primary", rs.busy)) : null);
}

function lossDetail(rs, role, me, a, e) {
  const can = canReviewLoss(e, role, me);
  return card(`${e.ref} · ${e.title}`, "rs-loss-detail",
    can ? h("div", {}, h("p", {}, "Review: say what caused it and what was learned or changed."),
      field("Cause", "rs-rev-cause", h("textarea", { id: "rs-rev-cause", rows: 2, onInput: (ev) => a.setForm("review", "cause", ev.target.value) }, rs.forms.review.cause || "")),
      field("What was learned or changed (at least 20 characters)", "rs-rev-lesson", h("textarea", { id: "rs-rev-lesson", rows: 2, onInput: (ev) => a.setForm("review", "lesson", ev.target.value) }, rs.forms.review.lesson || "")),
      formError(rs, "review"), btn("Mark as reviewed", "rs-loss-review", () => a.reviewLoss(e.id), "primary", rs.busy),
      noteBox(rs, a, `void-${e.id}`, "Why this record is being voided (required, at least 10 characters)"), btn("Void record", "rs-loss-void", () => a.voidLoss(e.id), "secondary", rs.busy)) :
      (canApprove(role) ? h("p", { id: "rs-loss-waiting" }, ownWorkText("recorded this loss event")) : none("Waiting for a different person to review it.")),
    h("div", {}, h("h4", {}, "History"), hist(e.history)));
}

// ---------------------------------------------------------------- processes
function processes(rs, role, me, a) {
  return h("div", {},
    card("Business processes", "rs-processes", rs.processes.length ? rs.processes.map((p) => h("div", { className: "card", style: "margin-bottom:8px;", "data-process": p.ref },
      h("div", {}, h("strong", {}, `${p.ref} · ${p.name}`), " ", St(p.status), " ", St(p.criticality), p.status === "APPROVED" && p.drill_due ? [" ", Badge({ tone: "warn", label: p.last_tested_on ? "Test due" : "Never tested" })] : null),
      h("div", { style: "color: var(--ink-500);" }, `Owner ${p.owner_name} · recover within ${p.rto_hours} h · lose at most ${p.rpo_hours} h of work · impact: financial ${IMPACT_TEXT[p.impacts.financial]}, legal ${IMPACT_TEXT[p.impacts.legal]}, reputation ${IMPACT_TEXT[p.impacts.reputation]}`),
      h("div", {}, p.description), p.dependencies ? h("div", {}, `Depends on: ${p.dependencies}`) : null,
      p.status === "APPROVED" ? h("div", { style: "color: var(--ink-500);" }, p.last_tested_on ? `${p.drills} test(s); last approved ${p.last_tested_on} — ${statusOf(p.last_result).label}` : "No approved continuity test yet.") : null,
      p.decision_note && p.status !== "APPROVED" ? h("div", {}, `Note: ${p.decision_note}`) : null,
      canDecideProcess(p, role, me) ? h("div", {}, noteBox(rs, a, `proc-${p.id}`, "Reason (required, at least 10 characters, to reject)"), btn("Approve process", `rs-proc-${p.ref}-approve`, () => a.processStep(p.id, "approve"), "primary", rs.busy), " ", btn("Reject", `rs-proc-${p.ref}-reject`, () => a.processStep(p.id, "reject"), "secondary", rs.busy)) :
        (p.status === "PROPOSED" && canApprove(role) ? h("div", { style: "color: var(--ink-500);" }, ownWorkText("proposed this process")) : null),
      canRetireProcess(p, role) ? h("div", {}, noteBox(rs, a, `proc-${p.id}`, "Why this process is being retired (required, at least 10 characters)"), btn("Retire process", `rs-proc-${p.ref}-retire`, () => a.processStep(p.id, "retire"), "secondary", rs.busy)) : null)) : none("No processes yet.")),
    canPrepare(role) ? card("Propose a business process", "rs-proc-card",
      h("p", { style: "color: var(--ink-500);" }, "Objectives cannot be changed once approved. The criticality is the highest of the three impacts you choose."),
      row(field("Name", "rs-proc-name", text(rs, a, "process", "name", "rs-proc-name")), field("Owner (name)", "rs-proc-owner", text(rs, a, "process", "owner_name", "rs-proc-owner"))),
      field("What the process does", "rs-proc-desc", area(rs, a, "process", "description", "rs-proc-desc")),
      row(field("Must be back within (hours)", "rs-proc-rto", text(rs, a, "process", "rto_hours", "rs-proc-rto")), field("Can lose at most (hours of work)", "rs-proc-rpo", text(rs, a, "process", "rpo_hours", "rs-proc-rpo"))),
      row(field("Financial impact of an outage", "rs-proc-fin", sel(rs, a, "process", "impact_financial", "rs-proc-fin", opt(IMPACT_TEXT))), field("Legal impact", "rs-proc-leg", sel(rs, a, "process", "impact_legal", "rs-proc-leg", opt(IMPACT_TEXT))),
        field("Reputation impact", "rs-proc-rep", sel(rs, a, "process", "impact_reputation", "rs-proc-rep", opt(IMPACT_TEXT)))),
      field("Depends on (optional)", "rs-proc-deps", text(rs, a, "process", "dependencies", "rs-proc-deps")), formError(rs, "process"), btn("Propose process", "rs-proc-save", () => a.proposeProcess(), "primary", rs.busy)) : null);
}

// ---------------------------------------------------------------- continuity tests
function drills(rs, role, me, a) {
  const ready = rs.processes.filter((p) => canTestProcess(p, role));
  return h("div", {},
    card("Continuity tests", "rs-drills", rs.drills.length ? rs.drills.map((t) => h("div", { className: "card", style: "margin-bottom:8px;", "data-drill": t.ref },
      h("div", {}, h("strong", {}, `${t.ref} · ${t.process_ref} ${t.process_name}`), " ", St(t.status), " ", St(t.result), ` · ${DRILL_TEXT[t.drill_type] || t.drill_type} on ${t.performed_on}`),
      h("div", {}, objectiveText(t)), h("div", {}, t.scenario), h("div", {}, `What happened: ${t.outcome}`), t.follow_up ? h("div", {}, `Follow-up: ${t.follow_up}`) : null, fileList(t.evidence),
      h("div", { style: "color: var(--ink-500);" }, `Carried out by ${who(t.recorded_by, me)}${t.decided_by ? `; decided by ${who(t.decided_by, me)}` : ""}${t.decision_note ? `: ${t.decision_note}` : ""}`),
      canDecideDrill(t, role, me) ? h("div", {}, noteBox(rs, a, `drill-${t.id}`, t.result === "NOT_MET" ? "Note (required, at least 10 characters: this test missed its objective)" : "Note (optional to approve; required, at least 10 characters, to reject)"),
        btn("Approve test", `rs-drill-${t.ref}-approve`, () => a.drillStep(t.id, "approve", t), "primary", rs.busy), " ", btn("Reject", `rs-drill-${t.ref}-reject`, () => a.drillStep(t.id, "reject", t), "secondary", rs.busy)) :
        (t.status === "RECORDED" && canApprove(role) ? h("div", { style: "color: var(--ink-500);" }, ownWorkText("carried out this test")) : null))) : none("No continuity tests yet.")),
    canPrepare(role) ? card("Record a continuity test", "rs-drill-card",
      ready.length ? h("div", {}, row(field("Process", "rs-dr-process", sel(rs, a, "drill", "process_id", "rs-dr-process", ready.map((p) => [p.id, `${p.ref} · ${p.name} (${p.rto_hours} h / ${p.rpo_hours} h)`]), "Choose a process")),
        field("Type", "rs-dr-type", sel(rs, a, "drill", "drill_type", "rs-dr-type", opt(DRILL_TEXT))), field("Date of the test", "rs-dr-date", text(rs, a, "drill", "performed_on", "rs-dr-date", "YYYY-MM-DD"))),
        field("Scenario", "rs-dr-scenario", area(rs, a, "drill", "scenario", "rs-dr-scenario")),
        row(field("Hours it took to recover", "rs-dr-rec", text(rs, a, "drill", "achieved_recovery_hours", "rs-dr-rec")), field("Hours of work lost", "rs-dr-loss", text(rs, a, "drill", "achieved_data_loss_hours", "rs-dr-loss"))),
        field("What happened", "rs-dr-outcome", text(rs, a, "drill", "outcome", "rs-dr-outcome")), field("What will be done about it (required if an objective was missed)", "rs-dr-follow", text(rs, a, "drill", "follow_up", "rs-dr-follow")),
        docs(rs, a, "drill", "rs-dr-doc"), formError(rs, "drill"), btn("Record test", "rs-dr-save", () => a.recordDrill(), "primary", rs.busy)) : none("No approved process is waiting to be tested. Propose a process and have a different person approve it first.")) : null);
}
