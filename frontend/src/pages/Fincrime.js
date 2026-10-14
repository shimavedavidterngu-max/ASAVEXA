import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState } from "../components/DataState.js";
import { TABS, SOURCE_TEXT, SEVERITY_TEXT, EVENT_TEXT, CHECK_TEXT, SUBJECT_TEXT, RESULT_TEXT, OUTCOME_TEXT, RECOVERY_TEXT, ATTENTION_TONE, canPrepare, canApprove, statusOf, words, who, leadChoices,
  myDeclaration, canDeclare, needsDeclaration, hasConflict, canWork, canPropose, canDecideOn, decisionMoves, screeningMoves, recoveryMoves, canDismiss, canReopen, canChangeLead, waitingText, positionText } from "../lib/fincrime.js";

/**
 * Financial-crime casework. It records and checks; it does not screen anyone, monitor transactions or file a report with any authority.
 * Nobody works or decides a case until they have declared whether they have a conflict of interest on it. The lead investigator works the case;
 * a different person decides the outcome, resolves possible screening matches and confirms recoveries.
 */
const Badge = ({ tone, label, id }) => h("span", { className: `badge badge-${tone || "neutral"}`, id }, label);
const St = (s) => Badge({ ...statusOf(s) });
const note = (t, kind = "info", id) => (t ? h("div", { className: `alert alert-${kind}`, id, style: "margin-bottom:12px;", role: kind === "error" ? "alert" : "status" }, t) : null);
const field = (l, id, inp, hint) => h("div", { className: "field" }, h("label", { for: id }, l), inp, hint ? h("small", { style: "color: var(--ink-500);" }, hint) : null);
const text = (fc, a, form, k, id, ph) => h("input", { id, type: "text", value: (fc.forms[form] || {})[k] == null ? "" : (fc.forms[form] || {})[k], placeholder: ph || "", onInput: (e) => a.setForm(form, k, e.target.value) });
const area = (fc, a, form, k, id) => h("textarea", { id, rows: 3, onInput: (e) => a.setForm(form, k, e.target.value) }, (fc.forms[form] || {})[k] || "");
const sel = (fc, a, form, k, id, opts, blank) => h("select", { id, onChange: (e) => a.setForm(form, k, e.target.value, true) },
  [...(blank ? [h("option", { value: "" }, blank)] : []), ...opts.map(([v, l]) => h("option", { value: v, selected: String((fc.forms[form] || {})[k]) === String(v) }, l))]);
const table = (head, rows, id) => h("div", { className: "table-scroll" }, h("table", { className: "data-table", id }, h("thead", {}, h("tr", {}, head.map(([l, right]) => h("th", { style: right ? "text-align:right;" : undefined }, l)))), h("tbody", {}, rows)));
const td = (v, right) => h("td", { style: right ? "text-align:right;" : undefined }, v);
const btn = (l, id, onClick, kind = "secondary", disabled = false) => h("button", { className: `btn btn-${kind}`, id, disabled, onClick }, l);
const row = (...b) => h("div", { style: "display:flex; gap:8px; flex-wrap:wrap; margin:8px 0; align-items:end;" }, b.filter(Boolean));
const none = (t = "None.") => h("div", { style: "color: var(--ink-500);" }, t);
const card = (title, id, ...kids) => h("div", { className: "card", id, style: "margin-bottom:16px;" }, h("h3", {}, title), ...kids);
const hist = (items) => h("ul", {}, (items || []).map((x) => h("li", {}, `${String(x.at).slice(0, 10)} ${String(x.event).replace(/_/g, " ").toLowerCase()} by ${x.by}${x.note ? ": " + x.note : ""}`)));
const noteBox = (fc, a, key, l, id) => field(l, id || `note-${key}`, h("textarea", { id: id || `note-${key}`, rows: 2, onInput: (e) => a.setNote(key, e.target.value) }, fc.notes[key] || ""));
const formError = (fc, name) => (fc.formError && fc.formError.form === name ? note(fc.formError.text, "error", `${name}-problem`) : null);
const docs = (fc, a, form, id) => field("Attach a document (optional)", id, sel(fc, a, form, "evidence_id", id, (fc.vault || []).map((e) => [e.id, e.original_filename || e.filename || e.id]), "No document"), "A document from the Evidence Vault. Its file fingerprint is kept.");
const fileList = (list) => (list && list.length ? h("div", { style: "font-size:0.9em; color: var(--ink-500);" }, list.map((e) => `${e.filename} (fingerprint ${String(e.file_hash).slice(0, 12)})`).join("; ")) : null);
const opt = (o) => Object.entries(o);

export function Fincrime({ fc, role, userId, loading, onRetry, actions: a }) {
  return h("div", {},
    h("h1", {}, "Financial-crime casework"),
    note("This workspace records and checks. It does not screen anyone against any list, monitor transactions or file a report with any authority, and an outcome is not a finding of guilt. Cases are confidential. Before anyone works or decides a case they must declare whether they have a conflict of interest, and the person who decides an outcome is never the person who led the case.", "info", "fx-banner"),
    fc.error ? ErrorState({ message: fc.error, onRetry }) : null,
    note(fc.notice, "success", "fx-notice"),
    loading ? LoadingState() : h("div", {},
      h("div", { className: "tabs", role: "tablist", style: "display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px;" },
        TABS.map(([id, l]) => h("button", { className: `btn ${fc.tab === id ? "btn-primary" : "btn-secondary"}`, role: "tab", id: `fx-tab-${id}`, "aria-selected": fc.tab === id ? "true" : "false", onClick: () => a.setTab(id) }, l))),
      fc.busy ? h("div", { style: "color: var(--ink-500);" }, "Working...") : null,
      fc.tab === "overview" ? overview(fc, role, a) : fc.tab === "alerts" ? alerts(fc, role, userId, a) : cases(fc, role, userId, a)));
}

// ---------------------------------------------------------------- overview
function overview(fc, role, a) {
  const o = fc.ov; if (!o) return none("Nothing loaded yet.");
  const c = o.counts, sev = c.open_by_severity || {};
  return h("div", {},
    card("What needs attention", "fx-attention", o.attention.length ? h("ul", {}, o.attention.map((x) => h("li", { "data-kind": x.kind }, Badge({ tone: ATTENTION_TONE[x.kind] || "info", label: words(x.kind) }), " ", `${x.count} ${x.text}`))) : none("Nothing needs attention.")),
    card("Counts", "fx-counts", h("ul", {}, [["Alerts", c.alerts], ["Alerts not yet looked at", c.alerts_new], ["Cases", c.cases], ["Open cases", c.cases_open], ["Closed cases", c.cases_closed],
      ["Open cases of high severity", sev.HIGH || 0], ["Open cases of medium severity", sev.MEDIUM || 0], ["Open cases of low severity", sev.LOW || 0]].map(([l, n]) => h("li", {}, `${l}: ${n}`)))),
    policyCard(fc, role, a),
    card("What this does not do", "fx-limits", h("ul", {}, o.limitations.map((x) => h("li", {}, x)))));
}

function policyCard(fc, role, a) {
  const p = fc.ov.policy, f = fc.forms.policy;
  return card("Targets", "fx-policy", h("p", { id: "fx-policy-meaning" }, p.meaning),
    canApprove(role) && f ? h("div", {},
      row(field("Days before an unlooked-at alert is flagged", "fx-policy-alert", text(fc, a, "policy", "alert_sla_days", "fx-policy-alert")), field("Days before an open case is flagged", "fx-policy-case", text(fc, a, "policy", "case_sla_days", "fx-policy-case"))),
      formError(fc, "policy"), btn("Save targets", "fx-policy-save", () => a.savePolicy(), "primary", fc.busy)) : h("p", { style: "color: var(--ink-500);" }, "Only a decision-maker can change these targets."));
}

// ---------------------------------------------------------------- alerts
function alerts(fc, role, me, a) {
  const f = fc.forms.alert;
  return h("div", {},
    card("Alerts", "fx-alerts", fc.alerts.length ? fc.alerts.map((x) => h("div", { className: "card", style: "margin-bottom:8px;", "data-alert": x.ref },
      h("div", {}, h("strong", {}, `${x.ref} · ${SOURCE_TEXT[x.source] || words(x.source)}`), " ", St(x.status), x.case_ref ? ` · in ${x.case_ref}` : ""),
      h("div", {}, x.summary), h("div", { style: "color: var(--ink-500);" }, `Noticed ${x.observed_on}${x.amount ? ` · ${x.amount} ${x.currency}` : ""} · raised by ${who(x.raised_by, me)} · ${x.age_days} day(s) ago`), fileList(x.evidence),
      x.status === "DISMISSED" ? h("div", {}, `Dismissed by ${who(x.dismissed_by, me)}: ${x.dismissed_note}`) : null,
      canDismiss(x, role, me) ? h("div", {}, noteBox(fc, a, `al-${x.id}`, "Why it can be dismissed (required, at least 10 characters)"), btn("Dismiss", `fx-al-${x.ref}-dismiss`, () => a.dismissAlert(x.id), "secondary", fc.busy)) :
        (x.status === "NEW" && canApprove(role) ? h("div", { style: "color: var(--ink-500);" }, "You raised this alert, so a different person must dismiss it.") : null))) : none("No alerts yet.")),
    canPrepare(role) ? card("Raise an alert", "fx-al-card",
      h("p", { style: "color: var(--ink-500);" }, "Record what was noticed and where it came from. This does not accuse anyone. A decision-maker or an investigator then dismisses it or opens a case."),
      row(field("Where it came from", "fx-al-source", sel(fc, a, "alert", "source", "fx-al-source", opt(SOURCE_TEXT))), field("Date noticed", "fx-al-date", text(fc, a, "alert", "observed_on", "fx-al-date", "YYYY-MM-DD")),
        field("Amount (optional)", "fx-al-amount", text(fc, a, "alert", "amount", "fx-al-amount", "0.00")), field("Currency", "fx-al-cur", text(fc, a, "alert", "currency", "fx-al-cur", "NGN"))),
      field("What was noticed", "fx-al-summary", area(fc, a, "alert", "summary", "fx-al-summary")), docs(fc, a, "alert", "fx-al-doc"),
      formError(fc, "alert"), btn("Raise alert", "fx-al-save", () => a.raiseAlert(), "primary", fc.busy)) : null);
}

// ---------------------------------------------------------------- cases
function cases(fc, role, me, a) {
  const f = fc.forms.casef, open = fc.sel.case;
  const fresh = fc.alerts.filter((x) => x.status === "NEW");
  return h("div", {},
    card("Cases", "fx-cases", fc.cases.length ? fc.cases.map((c) => h("div", { className: "card", style: "margin-bottom:8px;", "data-case": c.ref },
      h("div", {}, h("strong", {}, `${c.ref} · ${c.title}`), " ", St(c.status), " ", St(c.severity)),
      h("div", { style: "color: var(--ink-500);" }, `Lead ${c.lead ? who(c.lead, me) : "none (needs a new lead)"} · opened ${String(c.opened_at).slice(0, 10)} · ${c.age_days} day(s)${c.alert_refs.length ? ` · from ${c.alert_refs.join(", ")}` : ""}`),
      c.status === "CLOSED" ? h("div", {}, `Outcome: ${OUTCOME_TEXT[c.outcome] || words(c.outcome)} (closed ${c.closed_on})`) : null,
      btn(open && open.id === c.id ? "Hide" : "Open", `fx-case-open-${c.ref}`, () => a.selectCase(open && open.id === c.id ? null : c.id), "secondary", fc.busy))) : none("No cases yet.")),
    open ? caseDetail(fc, role, me, a, open) : null,
    canPrepare(role) ? card("Open a case", "fx-case-card",
      h("p", { style: "color: var(--ink-500);" }, "You become the lead investigator, so you must say now whether you have a conflict of interest. If you do, someone else has to open the case."),
      row(field("Title", "fx-case-title", text(fc, a, "casef", "title", "fx-case-title")), field("Severity", "fx-case-sev", sel(fc, a, "casef", "severity", "fx-case-sev", opt(SEVERITY_TEXT)))),
      field("What the case is about", "fx-case-summary", area(fc, a, "casef", "summary", "fx-case-summary")),
      fresh.length ? h("fieldset", { id: "fx-case-alerts" }, h("legend", {}, "Alerts to bring into this case"), fresh.map((x) => h("label", { style: "display:block;" },
        h("input", { type: "checkbox", id: `fx-case-alert-${x.ref}`, checked: (f.alert_ids || []).includes(x.id), onChange: (e) => a.toggleAlert(x.id, e.target.checked) }), ` ${x.ref} · ${x.summary}`))) : none("No alerts are waiting; a case can also be opened without one."),
      row(field("Do you have a conflict of interest?", "fx-case-conflict", sel(fc, a, "casef", "conflict", "fx-case-conflict", [["no", "No, I have none"], ["yes", "Yes, I have one"]])),
        f.conflict === "yes" ? field("Describe it", "fx-case-conflict-note", text(fc, a, "casef", "conflict_note", "fx-case-conflict-note")) : null),
      formError(fc, "casef"), btn("Open case", "fx-case-save", () => a.openCase(), "primary", fc.busy)) : null);
}

function caseDetail(fc, role, me, a, c) {
  const mine = myDeclaration(c, me), lead = canWork(c, role, me), moves = decisionMoves(c, role, me, fc.alerts), closed = c.status === "CLOSED";
  const wait = waitingText(c, role, me), nkey = `case-${c.id}`;
  return card(`${c.ref} · ${c.title}`, "fx-case-detail",
    h("p", {}, c.summary), h("p", {}, St(c.status), " ", St(c.severity), ` · lead ${c.lead ? who(c.lead, me) : "none"} · opened by ${who(c.opened_by, me)}`),
    // --- one reason box shared by every decision-maker action on this case (resolve a match, reject a recovery, send an outcome back, reopen)
    canDecideOn(c, role, me) || canReopen(c, role, me) ? h("div", { id: "fx-reason" }, noteBox(fc, a, nkey, "Reason (required, at least 10 characters, to resolve a match, reject a recovery, send an outcome back or reopen the case)")) : null,
    // --- conflict declarations
    h("div", { id: "fx-declarations" }, h("h4", {}, "Conflict-of-interest declarations"),
      Object.keys(c.declarations).length ? h("ul", {}, Object.entries(c.declarations).map(([u, d]) => h("li", { "data-declared": u }, `${who(u, me)}: ${d.status === "NONE" ? "no conflict" : "CONFLICT"}${d.status === "CONFLICT" ? " — " + d.note : ""}`))) : none("Nobody has declared yet."),
      hasConflict(c, me) ? h("p", { id: "fx-declared-conflict" }, "You declared a conflict of interest on this case, so you cannot work or decide it. A declared conflict cannot be withdrawn.") :
        canDeclare(c, me) ? h("div", {}, needsDeclaration(c, me) ? h("p", { id: "fx-need-declaration" }, "You have not declared yet. Declare before you work or decide this case.") : h("p", {}, "You declared no conflict. If one arises, declare it now."),
          row(field("Declaration", "fx-decl-status", sel(fc, a, "declare", "status", "fx-decl-status", [["NONE", "I have no conflict of interest"], ["CONFLICT", "I have a conflict of interest"]])),
            fc.forms.declare.status === "CONFLICT" ? field("Describe it", "fx-decl-note", text(fc, a, "declare", "note", "fx-decl-note")) : null),
          formError(fc, "declare"), btn("Declare", "fx-decl-save", () => a.declare(c.id), "primary", fc.busy)) : null),
    // --- timeline
    h("div", { id: "fx-timeline" }, h("h4", {}, "Timeline"),
      c.events.length ? h("ul", {}, c.events.map((e) => h("li", { "data-event": e.seq }, `${e.occurred_on} · ${EVENT_TEXT[e.kind] || words(e.kind)} · ${e.text} (recorded by ${who(e.recorded_by, me)})`, fileList(e.evidence)))) : none("Nothing on the timeline yet."),
      lead ? h("div", {}, row(field("Date it happened", "fx-ev-date", text(fc, a, "event", "occurred_on", "fx-ev-date", "YYYY-MM-DD")), field("Kind", "fx-ev-kind", sel(fc, a, "event", "kind", "fx-ev-kind", opt(EVENT_TEXT)))),
        field("What happened", "fx-ev-text", text(fc, a, "event", "text", "fx-ev-text")), docs(fc, a, "event", "fx-ev-doc"), formError(fc, "event"), btn("Add to timeline", "fx-ev-save", () => a.addEvent(c.id), "primary", fc.busy)) : null),
    // --- screening
    h("div", { id: "fx-screenings" }, h("h4", {}, "Screening results (typed in; ASAVEXA does not screen)"),
      c.screenings.length ? table([["Subject"], ["Check"], ["List or source"], ["Screened"], ["Result"], ["Resolution"], [""]], c.screenings.map((s) => h("tr", { "data-screening": s.seq },
        td(`${s.subject} (${SUBJECT_TEXT[s.subject_kind]})`), td(CHECK_TEXT[s.check] || s.check), td(s.list_name), td(s.screened_on), td(St(s.result)),
        td(s.resolution ? `${s.resolution.outcome === "FALSE_POSITIVE" ? "Not a match" : "Confirmed match"} (by ${who(s.resolution.by, me)}): ${s.resolution.reason}` : (s.result === "POSSIBLE_MATCH" ? "Waiting for a different person" : "—")),
        td(screeningMoves(c, s, role, me).map((m) => btn(m === "false" ? "Not a match" : "Confirm match", `fx-sc-${s.seq}-${m}`, () => a.resolveScreening(c.id, s.id, m === "false" ? "FALSE_POSITIVE" : "CONFIRMED"), "secondary", fc.busy)))))) : none("No screening results yet."),
      lead ? h("div", {}, row(field("Who or what", "fx-sc-subject", text(fc, a, "screening", "subject", "fx-sc-subject")), field("Kind", "fx-sc-kind", sel(fc, a, "screening", "subject_kind", "fx-sc-kind", opt(SUBJECT_TEXT))),
        field("Check", "fx-sc-check", sel(fc, a, "screening", "check", "fx-sc-check", opt(CHECK_TEXT)))),
        row(field("List or source checked", "fx-sc-list", text(fc, a, "screening", "list_name", "fx-sc-list")), field("Date screened", "fx-sc-date", text(fc, a, "screening", "screened_on", "fx-sc-date", "YYYY-MM-DD")),
          field("Result", "fx-sc-result", sel(fc, a, "screening", "result", "fx-sc-result", opt(RESULT_TEXT)))),
        field("Note on the result", "fx-sc-note", text(fc, a, "screening", "note", "fx-sc-note")), formError(fc, "screening"), btn("Record screening result", "fx-sc-save", () => a.recordScreening(c.id), "primary", fc.busy)) : null),
    // --- loss and recovery
    h("div", { id: "fx-money" }, h("h4", {}, "Losses and recoveries"),
      c.position.length ? h("ul", { id: "fx-position" }, c.position.map((p) => h("li", { "data-currency": p.currency }, positionText(p)))) : none("No loss recorded."),
      c.losses.length ? table([["Date"], ["Amount", true], ["Currency"], ["What was lost"]], c.losses.map((x) => h("tr", {}, td(x.occurred_on), td(x.amount, true), td(x.currency), td(x.description)))) : null,
      c.recoveries.length ? table([["Received"], ["Amount", true], ["Currency"], ["Kind"], ["Status"], [""]], c.recoveries.map((x) => h("tr", { "data-recovery": x.seq },
        td(x.received_on), td(x.amount, true), td(x.currency), td(`${RECOVERY_TEXT[x.kind] || x.kind}: ${x.note}`), td(St(x.status)),
        td(recoveryMoves(c, x, role, me).map((m) => btn(m === "confirm" ? "Confirm" : "Reject", `fx-rec-${x.seq}-${m}`, () => a.recoveryStep(c.id, x.id, m), "secondary", fc.busy)))))) : null,
      lead ? h("div", {}, h("h5", {}, "Record a loss"), row(field("Amount", "fx-loss-amount", text(fc, a, "loss", "amount", "fx-loss-amount", "0.00")), field("Currency", "fx-loss-cur", text(fc, a, "loss", "currency", "fx-loss-cur", "NGN")),
        field("Date of the loss", "fx-loss-date", text(fc, a, "loss", "occurred_on", "fx-loss-date", "YYYY-MM-DD"))), field("What was lost", "fx-loss-desc", text(fc, a, "loss", "description", "fx-loss-desc")),
        docs(fc, a, "loss", "fx-loss-doc"), formError(fc, "loss"), btn("Record loss", "fx-loss-save", () => a.recordLoss(c.id), "primary", fc.busy),
        h("h5", {}, "Record a recovery"), row(field("Amount", "fx-rec-amount", text(fc, a, "recovery", "amount", "fx-rec-amount", "0.00")), field("Currency", "fx-rec-cur", text(fc, a, "recovery", "currency", "fx-rec-cur", "NGN")),
          field("Date received", "fx-rec-date", text(fc, a, "recovery", "received_on", "fx-rec-date", "YYYY-MM-DD")), field("Kind", "fx-rec-kind", sel(fc, a, "recovery", "kind", "fx-rec-kind", opt(RECOVERY_TEXT)))),
        field("Note", "fx-rec-note", text(fc, a, "recovery", "note", "fx-rec-note")), docs(fc, a, "recovery", "fx-rec-doc"), formError(fc, "recovery"), btn("Record recovery", "fx-rec-save", () => a.recordRecovery(c.id), "primary", fc.busy)) : null),
    // --- decision
    h("div", { id: "fx-decision" }, h("h4", {}, "Outcome"),
      c.decision ? h("div", {}, h("p", { id: "fx-decision-text" }, `${OUTCOME_TEXT[c.decision.outcome] || c.decision.outcome}${c.decision.referral_to ? ` — referral to ${c.decision.referral_to}` : ""}: ${c.decision.rationale} (proposed by ${who(c.decision.proposed_by, me)}${c.decision.decided_by ? `, decided by ${who(c.decision.decided_by, me)}` : ""})`),
        c.decision.rejected_note ? h("p", {}, `Sent back: ${c.decision.rejected_note}`) : null) : none("No outcome proposed."),
      c.unresolved_screenings && c.status !== "CLOSED" ? h("p", { id: "fx-blocked" }, "A possible screening match has not been resolved yet, so no outcome can be approved.") : null,
      wait ? h("p", { id: "fx-waiting" }, wait) : null,
      moves.length ? h("div", {},
        moves.map((m) => btn(m === "approve" ? "Approve outcome and close" : "Send back", `fx-dec-${m}`, () => a.decisionStep(c.id, m), m === "approve" ? "primary" : "secondary", fc.busy))) : null,
      canPropose(c, role, me) ? h("div", {}, row(field("Outcome", "fx-dec-outcome", sel(fc, a, "decision", "outcome", "fx-dec-outcome", opt(OUTCOME_TEXT))),
        fc.forms.decision.outcome === "REFER_ONWARD" ? field("Who the referral is to", "fx-dec-referral", text(fc, a, "decision", "referral_to", "fx-dec-referral")) : null),
        field("Reasons", "fx-dec-rationale", area(fc, a, "decision", "rationale", "fx-dec-rationale")), formError(fc, "decision"), btn("Propose outcome", "fx-dec-save", () => a.propose(c.id), "primary", fc.busy)) : null,
      canReopen(c, role, me) ? h("div", {}, btn("Reopen case", "fx-case-reopen", () => a.reopen(c.id), "secondary", fc.busy)) :
        (c.status === "CLOSED" && canApprove(role) && !hasConflict(c, me) ? h("p", { id: "fx-reopen-hint" }, "To reopen this case, first declare that you have no conflict of interest on it.") : null)),
    // --- lead
    canChangeLead(c, role) ? h("div", { id: "fx-lead" }, h("h4", {}, "Lead investigator"),
      leadChoices(fc.members, c).length ? h("div", {}, row(field("New lead", "fx-lead-select", sel(fc, a, "lead", "lead", "fx-lead-select", leadChoices(fc.members, c).map((m) => [m.user_id, `${who(m.user_id, me)} · ${words(m.role)}`]), "Choose a person"), "Only people who can work cases and have declared no conflict on this case."),
        field("Reason", "fx-lead-reason", text(fc, a, "lead", "reason", "fx-lead-reason"))), formError(fc, "lead"), btn("Change lead", "fx-lead-save", () => a.changeLead(c.id), "secondary", fc.busy)) :
        none("No one else can take this case yet. A possible lead must be able to work cases and must first declare no conflict of interest on it.")) : null,
    h("div", {}, h("h4", {}, "History"), hist(c.history)));
}
