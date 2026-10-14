import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState } from "../components/DataState.js";
import { TABS, MEETING_TEXT, RESOLUTION_TEXT, FILING_TEXT, OUTCOME_TEXT, ATTENTION_TONE, canPrepare, canApprove, statusOf, words, who,
  canRecordMinutes, canApproveMinutes, canCancelMeeting, canDecide, canWithdrawResolution, canFile, canConfirm, canWithdrawFiling, ownWorkText } from "../lib/secretarial.js";

/**
 * Company secretarial. It records what people type in; it checks no law and contacts no registry.
 * A different person approves minutes, decides a resolution and confirms a filing.
 */
const Badge = ({ tone, label, id }) => h("span", { className: `badge badge-${tone || "neutral"}`, id }, label);
const St = (s) => Badge({ ...statusOf(s) });
const note = (t, kind = "info", id) => (t ? h("div", { className: `alert alert-${kind}`, id, style: "margin-bottom:12px;", role: kind === "error" ? "alert" : "status" }, t) : null);
const field = (l, id, inp, hint) => h("div", { className: "field" }, h("label", { for: id }, l), inp, hint ? h("small", { style: "color: var(--ink-500);" }, hint) : null);
const text = (cs, a, form, k, id, ph) => h("input", { id, type: "text", value: (cs.forms[form] || {})[k] == null ? "" : (cs.forms[form] || {})[k], placeholder: ph || "", onInput: (e) => a.setForm(form, k, e.target.value) });
const area = (cs, a, form, k, id) => h("textarea", { id, rows: 3, onInput: (e) => a.setForm(form, k, e.target.value) }, (cs.forms[form] || {})[k] || "");
const sel = (cs, a, form, k, id, opts, blank) => h("select", { id, onChange: (e) => a.setForm(form, k, e.target.value, true) },
  [...(blank ? [h("option", { value: "" }, blank)] : []), ...opts.map(([v, l]) => h("option", { value: v, selected: String((cs.forms[form] || {})[k]) === String(v) }, l))]);
const btn = (l, id, onClick, kind = "secondary", disabled = false) => h("button", { className: `btn btn-${kind}`, id, disabled, onClick }, l);
const row = (...b) => h("div", { style: "display:flex; gap:8px; flex-wrap:wrap; margin:8px 0; align-items:end;" }, b.filter(Boolean));
const none = (t = "None.") => h("div", { style: "color: var(--ink-500);" }, t);
const card = (title, id, ...kids) => h("div", { className: "card", id, style: "margin-bottom:16px;" }, h("h3", {}, title), ...kids);
const hist = (items) => h("ul", {}, (items || []).map((x) => h("li", {}, `${String(x.at).slice(0, 10)} ${String(x.event).replace(/_/g, " ").toLowerCase()} by ${x.by}${x.note ? ": " + x.note : ""}`)));
const noteBox = (cs, a, key, l, id) => field(l, id || `note-${key}`, h("textarea", { id: id || `note-${key}`, rows: 2, onInput: (e) => a.setNote(key, e.target.value) }, cs.notes[key] || ""));
const formError = (cs, name) => (cs.formError && cs.formError.form === name ? note(cs.formError.text, "error", `${name}-problem`) : null);
const docs = (cs, a, form, id) => field("Attach a document (optional)", id, sel(cs, a, form, "evidence_id", id, (cs.vault || []).map((e) => [e.id, e.original_filename || e.filename || e.id]), "No document"), "A document from the Evidence Vault. Its file fingerprint is kept.");
const fileList = (list) => (list && list.length ? h("div", { style: "font-size:0.9em; color: var(--ink-500);" }, list.map((e) => `${e.filename} (fingerprint ${String(e.file_hash).slice(0, 12)})`).join("; ")) : null);
const opt = (o) => Object.entries(o);

export function Secretarial({ cs, role, userId, loading, onRetry, actions: a }) {
  return h("div", {},
    h("h1", {}, "Company secretarial"),
    note("This workspace records what people type in about meetings, resolutions and statutory filings. It checks no law, your articles, quorum or notice, and contacts no registry. A different person approves minutes, decides a resolution and confirms a filing. Approved minutes are not a signed statutory record.", "info", "cs-banner"),
    cs.error ? ErrorState({ message: cs.error, onRetry }) : null,
    note(cs.notice, "success", "cs-notice"),
    loading ? LoadingState() : h("div", {},
      h("div", { className: "tabs", role: "tablist", style: "display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px;" },
        TABS.map(([id, l]) => h("button", { className: `btn ${cs.tab === id ? "btn-primary" : "btn-secondary"}`, role: "tab", id: `cs-tab-${id}`, "aria-selected": cs.tab === id ? "true" : "false", onClick: () => a.setTab(id) }, l))),
      cs.busy ? h("div", { style: "color: var(--ink-500);" }, "Working...") : null,
      cs.tab === "overview" ? overview(cs, role, a) : cs.tab === "meetings" ? meetings(cs, role, userId, a) : cs.tab === "resolutions" ? resolutions(cs, role, userId, a) : filings(cs, role, userId, a)));
}

function overview(cs, role, a) {
  const o = cs.ov; if (!o) return none("Nothing loaded yet.");
  const c = o.counts;
  return h("div", {},
    card("What needs attention", "cs-attention", o.attention.length ? h("ul", {}, o.attention.map((x) => h("li", { "data-kind": x.kind }, Badge({ tone: ATTENTION_TONE[x.kind] || "info", label: words(x.kind) }), " ", `${x.count} ${x.text}`))) : none("Nothing needs attention.")),
    card("Counts", "cs-counts", h("ul", {}, [["Meetings scheduled", c.meetings_scheduled], ["Meetings held", c.meetings_held], ["Resolutions passed", c.resolutions_passed], ["Resolutions failed", c.resolutions_failed], ["Resolutions waiting", c.resolutions_open],
      ["Filings open", c.filings_open], ["Filings waiting for confirmation", c.filings_filed], ["Filings confirmed", c.filings_confirmed]].map(([l, n]) => h("li", {}, `${l}: ${n}`)))),
    policyCard(cs, role, a),
    card("What this does not do", "cs-limits", h("ul", {}, o.limitations.map((x) => h("li", {}, x)))));
}

function policyCard(cs, role, a) {
  const p = cs.ov.policy, f = cs.forms.policy;
  return card("Settings", "cs-policy", h("p", { id: "cs-policy-meaning" }, p.meaning),
    canApprove(role) && f ? h("div", {}, row(field("Days before a filing is due soon", "cs-policy-days", text(cs, a, "policy", "due_soon_days", "cs-policy-days"))),
      formError(cs, "policy"), btn("Save settings", "cs-policy-save", () => a.savePolicy(), "primary", cs.busy)) : h("p", { style: "color: var(--ink-500);" }, "Only an approver can change this setting."));
}

// ---------------------------------------------------------------- meetings
function meetings(cs, role, me, a) {
  return h("div", {},
    card("Meetings", "cs-meetings", cs.meetings.length ? cs.meetings.map((m) => h("div", { className: "card", style: "margin-bottom:8px;", "data-meeting": m.ref },
      h("div", {}, h("strong", {}, `${m.ref} · ${m.title}`), " ", St(m.status), m.record_due ? [" ", Badge({ tone: "warn", label: "No minutes yet" })] : null),
      h("div", { style: "color: var(--ink-500);" }, `${MEETING_TEXT[m.kind] || m.kind} · ${m.held_on} · ${m.location} · scheduled by ${who(m.scheduled_by, me)}`), h("div", {}, `Agenda: ${m.agenda}`),
      m.minutes ? h("div", {}, h("div", {}, `Attended: ${m.attendees}`), h("div", {}, `Minutes: ${m.minutes}`), h("div", { style: "color: var(--ink-500);" }, `Recorded by ${who(m.minutes_by, me)}`)) : null, fileList(m.evidence),
      m.status === "MINUTES_APPROVED" ? h("div", {}, `Approved by ${who(m.approved_by, me)}${m.approve_note ? ": " + m.approve_note : ""}`) : null, m.status === "CANCELLED" ? h("div", {}, `Cancelled: ${m.cancel_note}`) : null,
      m.resolutions.length ? h("ul", {}, m.resolutions.map((r) => h("li", {}, `${r.ref} · ${r.text} · `, St(r.status)))) : null,
      canRecordMinutes(m, role) ? h("div", {}, field("Who attended", `cs-mn-${m.ref}-att`, text(cs, a, "minutes", "attendees", `cs-mn-${m.ref}-att`)), field("Minutes (at least 20 characters)", `cs-mn-${m.ref}-text`, area(cs, a, "minutes", "minutes", `cs-mn-${m.ref}-text`)),
        docs(cs, a, "minutes", `cs-mn-${m.ref}-doc`), formError(cs, `minutes-${m.id}`), btn("Record the minutes", `cs-mt-${m.ref}-minutes`, () => a.recordMinutes(m.id), "primary", cs.busy)) : null,
      canApproveMinutes(m, role, me) ? h("div", {}, noteBox(cs, a, `approve-${m.id}`, "Approval note (optional; at least 10 characters if given)", `cs-mt-${m.ref}-note`), btn("Approve the minutes", `cs-mt-${m.ref}-approve`, () => a.approveMinutes(m.id), "primary", cs.busy)) :
        (m.status === "HELD" && canApprove(role) ? h("div", { style: "color: var(--ink-500);" }, ownWorkText("recorded these minutes")) : null),
      canCancelMeeting(m, role) ? h("div", {}, noteBox(cs, a, `cancel-${m.id}`, "Why this meeting is being cancelled (required, at least 10 characters)"), btn("Cancel meeting", `cs-mt-${m.ref}-cancel`, () => a.cancelMeeting(m.id), "secondary", cs.busy)) : null)) : none("No meetings yet.")),
    canPrepare(role) ? card("Schedule a meeting", "cs-meeting-card",
      row(field("Kind", "cs-mt-kind", sel(cs, a, "meeting", "kind", "cs-mt-kind", Object.entries(MEETING_TEXT))), field("Title", "cs-mt-title", text(cs, a, "meeting", "title", "cs-mt-title")), field("Date", "cs-mt-date", text(cs, a, "meeting", "held_on", "cs-mt-date", "YYYY-MM-DD"))),
      field("Location", "cs-mt-loc", text(cs, a, "meeting", "location", "cs-mt-loc")), field("Agenda", "cs-mt-agenda", area(cs, a, "meeting", "agenda", "cs-mt-agenda")),
      formError(cs, "meeting"), btn("Schedule meeting", "cs-mt-save", () => a.scheduleMeeting(), "primary", cs.busy)) : null);
}

// ---------------------------------------------------------------- resolutions
function resolutions(cs, role, me, a) {
  const open = cs.meetings.filter((m) => m.status === "SCHEDULED" || m.status === "HELD");
  return h("div", {},
    card("Resolutions", "cs-resolutions", cs.resolutions.length ? cs.resolutions.map((r) => h("div", { className: "card", style: "margin-bottom:8px;", "data-resolution": r.ref },
      h("div", {}, h("strong", {}, `${r.ref} · ${RESOLUTION_TEXT[r.kind] || r.kind}`), " ", St(r.status)),
      h("div", {}, r.text), h("div", { style: "color: var(--ink-500);" }, `${r.meeting_ref ? "Put to " + r.meeting_ref : "Written resolution"} · proposed by ${who(r.proposed_by, me)}`),
      r.votes_for != null ? h("div", {}, `Votes: ${r.votes_for} for, ${r.votes_against} against, ${r.abstentions} abstained. ${r.decision_note}`) : null, r.withdraw_note ? h("div", {}, `Withdrawn: ${r.withdraw_note}`) : null,
      r.status === "PROPOSED" && !r.can_decide ? h("div", { style: "color: var(--ink-500);" }, "It can be decided once minutes of the meeting are recorded.") : null,
      canDecide(r, role, me) ? h("div", {}, row(field("Votes for", `cs-rs-${r.ref}-for`, text(cs, a, "decide", "votes_for", `cs-rs-${r.ref}-for`)), field("Votes against", `cs-rs-${r.ref}-against`, text(cs, a, "decide", "votes_against", `cs-rs-${r.ref}-against`)),
        field("Abstentions", `cs-rs-${r.ref}-abs`, text(cs, a, "decide", "abstentions", `cs-rs-${r.ref}-abs`)), field("Outcome", `cs-rs-${r.ref}-outcome`, sel(cs, a, "decide", "outcome", `cs-rs-${r.ref}-outcome`, Object.entries(OUTCOME_TEXT)))),
        field("Decision note (at least 10 characters)", `cs-rs-${r.ref}-note`, area(cs, a, "decide", "note", `cs-rs-${r.ref}-note`)), formError(cs, `decide-${r.id}`), btn("Record the decision", `cs-rs-${r.ref}-decide`, () => a.decideResolution(r.id), "primary", cs.busy)) :
        (r.can_decide && canApprove(role) ? h("div", { style: "color: var(--ink-500);" }, ownWorkText("proposed this resolution")) : null),
      canWithdrawResolution(r, role) ? h("div", {}, noteBox(cs, a, `withdraw-${r.id}`, "Why this is being withdrawn (required, at least 10 characters)"), btn("Withdraw resolution", `cs-rs-${r.ref}-withdraw`, () => a.withdrawResolution(r.id), "secondary", cs.busy)) : null)) : none("No resolutions yet.")),
    canPrepare(role) ? card("Propose a resolution", "cs-resolution-card",
      row(field("Kind", "cs-rs-kind", sel(cs, a, "resolution", "kind", "cs-rs-kind", Object.entries(RESOLUTION_TEXT))),
        cs.forms.resolution.kind === "WRITTEN" ? null : field("Meeting", "cs-rs-meeting", sel(cs, a, "resolution", "meeting_id", "cs-rs-meeting", open.map((m) => [m.id, `${m.ref} · ${m.title}`]), "Choose a meeting"))),
      field("The resolution (at least 20 characters)", "cs-rs-text", area(cs, a, "resolution", "text", "cs-rs-text")), formError(cs, "resolution"), btn("Propose resolution", "cs-rs-save", () => a.proposeResolution(), "primary", cs.busy)) : null);
}

// ---------------------------------------------------------------- filings
function filings(cs, role, me, a) {
  return h("div", {},
    card("Statutory filings", "cs-filings", cs.filings.length ? cs.filings.map((f) => h("div", { className: "card", style: "margin-bottom:8px;", "data-filing": f.ref },
      h("div", {}, h("strong", {}, `${f.ref} · ${f.title}`), " ", St(f.status), f.overdue ? [" ", Badge({ tone: "fail", label: "Overdue" })] : null, f.due_soon ? [" ", Badge({ tone: "warn", label: "Due soon" })] : null),
      h("div", { style: "color: var(--ink-500);" }, `${FILING_TEXT[f.kind] || f.kind} · ${f.authority} · due ${f.due_on} · owner ${f.owner_name}`),
      f.filed_on ? h("div", {}, `Filed ${f.filed_on} by ${who(f.filed_by, me)}. Reference: ${f.receipt_ref}`) : null, fileList(f.evidence),
      f.confirm_note ? h("div", {}, `Confirmed by ${who(f.confirmed_by, me)}: ${f.confirm_note}`) : null, f.withdraw_note ? h("div", {}, `Withdrawn: ${f.withdraw_note}`) : null,
      canFile(f, role) ? h("div", {}, row(field("Filed on", `cs-fl-${f.ref}-date`, text(cs, a, "filed", "filed_on", `cs-fl-${f.ref}-date`, "YYYY-MM-DD")), field("Receipt or reference", `cs-fl-${f.ref}-ref`, text(cs, a, "filed", "receipt_ref", `cs-fl-${f.ref}-ref`))),
        docs(cs, a, "filed", `cs-fl-${f.ref}-doc`), formError(cs, `filed-${f.id}`), btn("Record as filed", `cs-fl-${f.ref}-file`, () => a.fileFiling(f.id), "primary", cs.busy)) : null,
      canConfirm(f, role, me) ? h("div", {}, field("Confirmation note (at least 10 characters)", `cs-fl-${f.ref}-note`, area(cs, a, "confirm", "note", `cs-fl-${f.ref}-note`)), formError(cs, `confirm-${f.id}`), btn("Confirm the filing", `cs-fl-${f.ref}-confirm`, () => a.confirmFiling(f.id), "primary", cs.busy)) :
        (f.status === "FILED" && canApprove(role) ? h("div", { style: "color: var(--ink-500);" }, ownWorkText("recorded this filing as filed")) : null),
      canWithdrawFiling(f, role) ? h("div", {}, noteBox(cs, a, `fwithdraw-${f.id}`, "Why this is being withdrawn (required, at least 10 characters)"), btn("Withdraw filing", `cs-fl-${f.ref}-withdraw`, () => a.withdrawFiling(f.id), "secondary", cs.busy)) : null)) : none("No filings yet.")),
    canPrepare(role) ? card("Add a filing", "cs-filing-card",
      row(field("Kind", "cs-fl-kind", sel(cs, a, "filing", "kind", "cs-fl-kind", Object.entries(FILING_TEXT))), field("Title", "cs-fl-title", text(cs, a, "filing", "title", "cs-fl-title"))),
      row(field("Authority or registry", "cs-fl-auth", text(cs, a, "filing", "authority", "cs-fl-auth")), field("Due on", "cs-fl-due", text(cs, a, "filing", "due_on", "cs-fl-due", "YYYY-MM-DD")), field("Owner (name)", "cs-fl-owner", text(cs, a, "filing", "owner_name", "cs-fl-owner"))),
      formError(cs, "filing"), btn("Add filing", "cs-fl-save", () => a.addFiling(), "primary", cs.busy)) : null);
}
