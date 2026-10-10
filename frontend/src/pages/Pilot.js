import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState, EmptyState } from "../components/DataState.js";
import { SURVEY_QUESTIONS, STATUS_TONE, STATUS_TEXT, SOURCE_TEXT, PILOT_STATUS_TEXT, TAB_LABEL, kindText, valueText, targetText, tally, tabsFor } from "../lib/pilot.js";

/**
 * Real Pilot: an accounting firm and a few small-business clients using ASAVEXA for real work, with eleven measures.
 * Figures marked "Measured" are counted from the platform's own records; figures marked "Reported" are what people told us.
 * Nothing here is invented: a measure without enough data says so instead of showing a number. The server enforces who may see what.
 */
function Badge({ tone, label, id }) { return h("span", { className: `badge badge-${tone || "neutral"}`, id }, label); }
const when = (iso) => { if (!iso) return "—"; const d = new Date(iso); return Number.isNaN(d.getTime()) ? String(iso) : d.toISOString().slice(0, 10); };
const notice = (t, kind) => (t ? h("div", { className: `alert alert-${kind === "error" ? "error" : "info"}`, style: "margin-bottom:12px;", role: kind === "error" ? "alert" : "status" }, t) : null);
const field = (label, id, input, hint) => h("div", { className: "field" }, h("label", { for: id }, label), input, hint ? h("small", { style: "color: var(--ink-500);" }, hint) : null);
const text = (id, f, k, a, ph, type = "text") => h("input", { id, type, value: f[k] == null ? "" : f[k], placeholder: ph || "", onInput: (e) => a.formChange(k, e.target.value) });
const area = (id, f, k, a, rows = 3) => h("textarea", { id, rows, value: f[k] || "", onInput: (e) => a.formChange(k, e.target.value) }, f[k] || "");
const select = (id, f, k, a, options, blank) => h("select", { id, onChange: (e) => a.formChange(k, e.target.value) },
  [blank ? h("option", { value: "" }, blank) : null, ...options.map(([v, l]) => h("option", { value: v, selected: (f[k] || "") === v }, l))]);

export function Pilot({ pilot, loading, onRetry, actions }) {
  const tabs = tabsFor(pilot.me);
  const tab = tabs.includes(pilot.tab) ? pilot.tab : tabs[0];
  const isClient = !!(pilot.me && pilot.me.membership && pilot.me.membership.role === "CLIENT");
  return h("div", {},
    h("h1", {}, "Real Pilot"),
    h("p", { style: "color: var(--ink-500); margin-top:-8px;" }, isClient ? "Your organisation is taking part in a pilot. Tell us honestly how it is going." :
      "An accounting firm and a few small-business clients, using ASAVEXA for real work. Eleven measures, each marked as measured or reported."),
    pilot.guide ? h("div", { className: "alert alert-info", id: "pilot-honesty" }, pilot.guide.honesty) : null,
    pilot.notice ? notice(pilot.notice) : null,
    pilot.error ? ErrorState({ message: pilot.error, onRetry }) : null,
    loading ? LoadingState() : h("div", {},
      pilot.current ? h("div", { className: "tabs", role: "tablist", style: "display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px;" },
        tabs.map((t) => h("button", { className: `btn ${t === tab ? "btn-primary" : "btn-secondary"}`, role: "tab", id: `pilot-tab-${t}`, "aria-selected": t === tab ? "true" : "false", onClick: () => actions.setTab(t) }, TAB_LABEL[t]))) : null,
      !pilot.current ? noPilot(pilot, actions) : h("div", {},
        tab === "dashboard" ? dashboard(pilot, actions) : null, tab === "clients" ? clientsTab(pilot, actions) : null, tab === "log" ? logTab(pilot, actions, isClient) : null,
        tab === "survey" ? surveyTab(pilot, actions) : null, tab === "setup" ? setupTab(pilot, actions) : null, tab === "report" ? reportTab(pilot, actions) : null,
        tab === "about" ? aboutTab(pilot, actions) : null)));
}

// ---------------------------------------------------------------- nothing to show yet
function noPilot(pilot, a) {
  if (!pilot.me.can_manage) return EmptyState({ title: "No pilot yet", message: "An owner or administrator of the accounting firm sets the pilot up. Your organisation is not in one yet." });
  const f = (pilot.form && pilot.form.kind === "pilot" ? pilot.form.f : null);
  return h("div", { className: "card", id: "pilot-create" },
    h("h3", {}, "Set up your pilot"),
    h("p", {}, "Start small: one accounting firm and up to four client businesses. You can add clients after you create the pilot."),
    f ? h("div", {},
      field("Pilot name", "pilot-name", text("pilot-name", f, "name", a, "e.g. Lagos small-business pilot")),
      field("Start date", "pilot-start", text("pilot-start", f, "start_date", a, "2026-10-12", "date")),
      field("End date (optional)", "pilot-end", text("pilot-end", f, "end_date", a, "", "date")),
      field("Notes (optional)", "pilot-notes", area("pilot-notes", f, "notes", a, 2)),
      h("button", { className: "btn btn-primary", id: "pilot-create-btn", disabled: pilot.busy, onClick: a.createPilot }, "Create pilot"),
      " ", h("button", { className: "btn btn-secondary", onClick: a.cancelForm }, "Cancel"))
      : h("button", { className: "btn btn-primary", id: "pilot-new-btn", onClick: () => a.startForm("pilot") }, "Start setting up"));
}

// ---------------------------------------------------------------- results
function measureCard(m) {
  return h("div", { className: "card", "data-measure": m.key, style: "margin-bottom:12px;" },
    h("div", { style: "display:flex; justify-content:space-between; gap:8px; flex-wrap:wrap;" },
      h("h3", { style: "margin:0;" }, m.label), h("div", {}, Badge({ tone: STATUS_TONE[m.status], label: STATUS_TEXT[m.status], id: `status-${m.key}` }), " ",
        Badge({ tone: m.source === "MEASURED" ? "info" : "neutral", label: SOURCE_TEXT[m.source], id: `source-${m.key}` }))),
    h("p", { style: "font-size:1.6rem; margin:8px 0 2px;", id: `value-${m.key}` }, valueText(m)),
    h("p", { style: "margin:0; color: var(--ink-500);" }, `Target: ${targetText(m)}. Based on ${m.n} ${m.n_what}.`),
    m.why ? h("p", { style: "margin:6px 0 0;" }, m.why) : m.detail ? h("p", { style: "margin:6px 0 0; color: var(--ink-500);" }, m.detail) : null);
}

function dashboard(pilot, a) {
  const r = pilot.results;
  if (!r) return pilot.busy ? LoadingState() : h("div", { className: "card" }, h("button", { className: "btn btn-primary", onClick: a.loadResults }, "Calculate results"));
  const ev = r.evaluation, t = tally(ev.measures);
  return h("div", {},
    h("div", { className: "card", id: "pilot-headline" }, h("h3", {}, ev.headline),
      h("p", {}, `${t.MET} met · ${t.NOT_MET} not met · ${t.INSUFFICIENT_DATA} not enough data. Clients included: ${r.clients_included} of ${r.clients_total}.`),
      h("p", { style: "color: var(--ink-500);", id: "pilot-caution" }, ev.caution),
      h("button", { className: "btn btn-secondary", id: "pilot-refresh", disabled: pilot.busy, onClick: a.loadResults }, "Recalculate")),
    r.skipped.length ? h("div", { className: "alert alert-error", id: "pilot-skipped" }, h("strong", {}, "Left out of every figure: "), r.skipped.map((s) => `${s.label} — ${s.reason}`).join(" ")) : null,
    ev.measures.map(measureCard));
}

// ---------------------------------------------------------------- clients
function clientCard(c, a, canEdit) {
  const m = c.metrics, on = m.onboarding;
  return h("div", { className: "card", "data-client": c.org_id, style: "margin-bottom:12px;" },
    h("div", { style: "display:flex; justify-content:space-between; gap:8px; flex-wrap:wrap;" }, h("h3", { style: "margin:0;" }, c.label),
      canEdit ? h("button", { className: "btn btn-secondary", onClick: () => a.startForm("remove", { org: c.org_id, label: c.label, reason: "" }) }, "Remove from pilot") : null),
    h("p", { style: "color: var(--ink-500);" }, `Consent: ${c.consent_reference}. Started ${when(c.kickoff)}. ${on.operational ? `Operational after ${on.days_to_operational} days.` : `Not yet operational (${on.days_since_kickoff} days in).`}`),
    h("ul", { className: "clean" }, on.milestones.map((x) => h("li", {}, `${x.reached_at ? "✔" : "○"} ${x.label}${x.days != null ? ` — day ${x.days}` : ""}`))),
    h("p", {}, `Journals posted ${m.processing.journals_posted} · evidence verified ${m.evidence.verified_percent == null ? "—" : m.evidence.verified_percent + "%"} · bank lines reconciled ${m.reconciliation.rate_percent == null ? "—" : m.reconciliation.rate_percent + "%"} · exceptions per 100 items ${m.exceptions.per_100 == null ? "—" : m.exceptions.per_100} · reports generated ${m.reports.generated}`));
}

function clientsTab(pilot, a) {
  const p = pilot.current, r = pilot.results, f = pilot.form;
  const active = p.clients.filter((c) => c.active), left = p.clients.filter((c) => !c.active);
  const byOrg = new Map(((r && r.clients) || []).map((c) => [c.org_id, c]));
  return h("div", {},
    h("div", { className: "card", id: "pilot-clients" }, h("h3", {}, `Client organisations (${active.length})`),
      h("p", {}, "Each client agrees in writing before it is added. You can only add an organisation that you administer yourself, which is how its consent is given. A client can withdraw at any time."),
      active.length === 0 ? EmptyState({ title: "No clients yet", message: "Add your first client below." }) : null,
      active.map((c) => byOrg.get(c.org_id) ? clientCard(byOrg.get(c.org_id), a, true) : h("div", { className: "card", "data-client": c.org_id, style: "margin-bottom:12px;" },
        h("h3", { style: "margin:0;" }, c.label), h("p", { style: "color: var(--ink-500);" }, `Consent: ${c.consent_reference}. Results are not shown until you calculate them on the Results tab.`),
        h("button", { className: "btn btn-secondary", onClick: () => a.startForm("remove", { org: c.org_id, label: c.label, reason: "" }) }, "Remove from pilot"))),
      left.length ? h("p", { style: "color: var(--ink-500);" }, `Withdrawn: ${left.map((c) => `${c.label} (${c.left_reason})`).join("; ")}. Their data is excluded from every result.`) : null),
    f && f.kind === "remove" ? h("div", { className: "card", id: "pilot-remove" }, h("h3", {}, `Remove ${f.f.label}`),
      field("Reason", "remove-reason", text("remove-reason", f.f, "reason", a)), h("button", { className: "btn btn-primary", id: "pilot-remove-btn", disabled: pilot.busy, onClick: a.removeClient }, "Remove"), " ",
      h("button", { className: "btn btn-secondary", onClick: a.cancelForm }, "Cancel")) : null,
    p.status !== "COMPLETED" ? addClientForm(pilot, a) : null);
}

function addClientForm(pilot, a) {
  const f = pilot.form && pilot.form.kind === "client" ? pilot.form.f : null;
  if (!f) return h("button", { className: "btn btn-primary", id: "pilot-add-client", onClick: a.startClientForm }, "Add a client organisation");
  const opts = (pilot.eligible || []).map((o) => [o.org_id, o.name]);
  return h("div", { className: "card", id: "pilot-client-form" }, h("h3", {}, "Add a client organisation"),
    opts.length === 0 ? h("div", { className: "alert alert-info" }, "No organisations are available. You can only add an organisation that you are an owner or administrator of, and that is not already in a pilot. Ask the client's owner to make you an administrator of their ASAVEXA organisation first.") : null,
    field("Client organisation", "client-org", select("client-org", f, "client_org_id", a, opts, "Choose…")),
    field("Short name", "client-label", text("client-label", f, "label", a, "e.g. Adaeze Bakery")),
    field("Where is their written consent kept?", "client-consent", text("client-consent", f, "consent_reference", a, "e.g. Signed letter 2026-10-01, file C-014"), "Required. This is recorded in both organisations' audit trails."),
    field("Start date (optional)", "client-kickoff", text("client-kickoff", f, "kickoff", a, "", "date"), "Defaults to today. Cannot be in the future."),
    field("Minutes audit preparation took before ASAVEXA (optional)", "client-base-audit", text("client-base-audit", f, "audit_prep_minutes", a, "e.g. 1200"), "Needed to say how much time was saved. Without it, no percentage is shown."),
    field("Minutes producing a report took before (optional)", "client-base-report", text("client-base-report", f, "report_minutes", a, "e.g. 180")),
    h("button", { className: "btn btn-primary", id: "pilot-client-save", disabled: pilot.busy, onClick: a.addClient }, "Add client"), " ", h("button", { className: "btn btn-secondary", onClick: a.cancelForm }, "Cancel"));
}

// ---------------------------------------------------------------- recording
function logTab(pilot, a, isClient) {
  const L = pilot.logs, g = pilot.guide;
  if (!L || !g) return LoadingState();
  const f = pilot.form, clientOpts = L.clients.map((c) => [c.org_id, c.label]);
  const who = (ff) => (isClient ? null : field("Which client?", "log-client", select("log-client", ff, "client_org_id", a, clientOpts, "Choose…")));
  const kindOpts = (list) => list.map((k) => [k, kindText(k)]);
  const forms = {
    time: () => h("div", { className: "card", id: "log-time-form" }, h("h3", {}, "Record time taken"), who(f.f),
      field("What was it?", "time-kind", select("time-kind", f.f, "kind", a, kindOpts(g.time_kinds), "Choose…")),
      field("Minutes it took", "time-minutes", text("time-minutes", f.f, "minutes", a, "e.g. 45")),
      field("Date", "time-date", text("time-date", f.f, "performed_on", a, "", "date")),
      field("Minutes it used to take (optional)", "time-base", text("time-base", f.f, "baseline_minutes", a, ""), "Used to work out time saved. Leave blank if you do not know."),
      field("Note (optional)", "time-note", text("time-note", f.f, "note", a)), saveCancel(a, "time")),
    issue: () => h("div", { className: "card", id: "log-issue-form" }, h("h3", {}, "Report a problem or mistake"), who(f.f),
      field("What kind?", "issue-kind", select("issue-kind", f.f, "kind", a, kindOpts(g.issue_kinds), "Choose…")),
      field("How much did it matter?", "issue-sev", select("issue-sev", f.f, "severity", a, kindOpts(g.severities))),
      field("What happened?", "issue-text", area("issue-text", f.f, "text", a)), saveCancel(a, "issue")),
    passport: () => h("div", { className: "card", id: "log-passport-form" }, h("h3", {}, "Record a use of the Financial Passport"), who(f.f),
      field("Who was it for?", "pp-purpose", select("pp-purpose", f.f, "purpose", a, kindOpts(g.passport_purposes), "Choose…")),
      field("Did it help?", "pp-outcome", select("pp-outcome", f.f, "outcome", a, kindOpts(g.passport_outcomes), "Choose…")),
      field("Minutes it saved (optional)", "pp-saved", text("pp-saved", f.f, "saved_minutes", a, "")), field("Note (optional)", "pp-note", text("pp-note", f.f, "note", a)), saveCancel(a, "passport")),
  };
  const row = (t) => h("tr", {}, ...t);
  return h("div", {},
    h("div", { className: "card", id: "pilot-record" }, h("h3", {}, "Record what happened"),
      h("p", {}, "A few lines a week is enough. Honest entries — including mistakes and things that did not help — are what make the pilot worth running."),
      h("button", { className: "btn btn-primary", id: "log-time-btn", onClick: () => a.startForm("time") }, "Record time"), " ",
      h("button", { className: "btn btn-secondary", id: "log-issue-btn", onClick: () => a.startForm("issue") }, "Report a problem"), " ",
      h("button", { className: "btn btn-secondary", id: "log-passport-btn", onClick: () => a.startForm("passport") }, "Passport use")),
    f && forms[f.kind] ? forms[f.kind]() : null,
    h("div", { className: "card", id: "pilot-time-list" }, h("h3", {}, "Time recorded"), L.time.length === 0 ? h("p", {}, "Nothing recorded yet.") :
      h("div", { className: "table-scroll" }, h("table", {}, h("thead", {}, row(["Date", "Client", "What", "Minutes", "Used to take"].map((c) => h("th", {}, c)))),
        h("tbody", {}, L.time.map((t) => row([when(t.performed_on), t.client, kindText(t.kind), String(t.minutes), t.baseline_minutes ? String(t.baseline_minutes) : "—"].map((c) => h("td", {}, c)))))))),
    h("div", { className: "card", id: "pilot-issue-list" }, h("h3", {}, "Problems and mistakes"), L.issues.length === 0 ? h("p", {}, "None reported yet.") :
      h("div", { className: "table-scroll" }, h("table", {}, h("thead", {}, row(["Reported", "Client", "Kind", "Matter", "What happened", "Status", ""].map((c) => h("th", {}, c)))),
        h("tbody", {}, L.issues.map((i) => row([when(i.reported_at), i.client, kindText(i.kind), kindText(i.severity), i.text, i.status === "RESOLVED" ? `Resolved: ${i.resolution}` : "Open"].map((c) => h("td", {}, c)).concat(
          h("td", {}, pilot.me.can_manage && i.status === "OPEN" ? h("button", { className: "btn btn-secondary", "data-resolve": i.id, onClick: () => a.startForm("resolve", { id: i.id, resolution: "" }) }, "Resolve") : null)))))))),
    f && f.kind === "resolve" ? h("div", { className: "card", id: "resolve-form" }, field("How was it resolved?", "resolve-text", text("resolve-text", f.f, "resolution", a)),
      h("button", { className: "btn btn-primary", id: "resolve-save", disabled: pilot.busy, onClick: a.resolveIssue }, "Mark resolved"), " ", h("button", { className: "btn btn-secondary", onClick: a.cancelForm }, "Cancel")) : null,
    h("div", { className: "card", id: "pilot-passport-list" }, h("h3", {}, "Financial Passport uses"), L.passport_uses.length === 0 ? h("p", {}, "None recorded yet.") :
      h("div", { className: "table-scroll" }, h("table", {}, h("thead", {}, row(["Date", "Client", "For", "Outcome", "Minutes saved"].map((c) => h("th", {}, c)))),
        h("tbody", {}, L.passport_uses.map((u) => row([when(u.logged_at), u.client, kindText(u.purpose), kindText(u.outcome), u.saved_minutes == null ? "—" : String(u.saved_minutes)].map((c) => h("td", {}, c)))))))));
}

const saveCancel = (a, which) => h("div", {}, h("button", { className: "btn btn-primary", id: `log-save-${which}`, onClick: () => a.saveLog(which) }, "Save"), " ", h("button", { className: "btn btn-secondary", onClick: a.cancelForm }, "Cancel"));

// ---------------------------------------------------------------- survey
function surveyTab(pilot, a) {
  const f = pilot.form && pilot.form.kind === "survey" ? pilot.form.f : null;
  const mine = pilot.mySurvey || [];
  return h("div", {},
    h("div", { className: "card", id: "pilot-survey-card" }, h("h3", {}, "How is it going?"),
      h("p", {}, "One short survey per person per round. Answers are shown only as combined figures. The average for a group is hidden until at least three people have answered, so nobody can be picked out."),
      mine.length ? h("p", { id: "pilot-survey-done" }, `You have answered: ${mine.map((s) => `${s.round} (revision ${s.revision})`).join(", ")}. Submitting the same round again replaces your earlier answers.`) : null,
      f ? h("div", {}, field("Round", "survey-round", text("survey-round", f, "round", a, "e.g. WEEK 4"), "Letters, numbers, spaces. The same name replaces your earlier answers."),
        SURVEY_QUESTIONS.map(([k, label, hint, req]) => field(`${label}${req ? "" : " (optional)"}`, `survey-${k}`, h("input", { id: `survey-${k}`, type: "text", inputmode: "numeric", value: (f.scores || {})[k] ?? "", onInput: (e) => a.surveyScore(k, e.target.value) }), hint)),
        field("Anything else you want us to know? (optional)", "survey-comment", area("survey-comment", f, "comment", a)),
        h("button", { className: "btn btn-primary", id: "survey-save", disabled: pilot.busy, onClick: a.submitSurvey }, "Submit"), " ", h("button", { className: "btn btn-secondary", onClick: a.cancelForm }, "Cancel"))
        : h("button", { className: "btn btn-primary", id: "survey-start", onClick: a.startSurvey }, mine.length ? "Answer another round" : "Answer the survey")),
    pilot.results ? surveySummary(pilot.results.reported.survey) : null);
}

function surveySummary(s) {
  return h("div", { className: "card", id: "pilot-survey-summary" }, h("h3", {}, "What people said so far"),
    s.respondents === 0 ? h("p", {}, "No one has answered yet.") : h("div", {},
      h("p", {}, `${s.respondents} ${s.respondents === 1 ? "person has" : "people have"} answered. Overall ${s.overall_mean ?? "—"} / 5 · ease ${s.ease_mean ?? "—"} · trust ${s.trust_mean ?? "—"} · would recommend (net score) ${s.nps ?? "—"}.`),
      ["FIRM", "CLIENT"].map((g) => h("p", { style: "color: var(--ink-500);" }, `${g === "FIRM" ? "Firm" : "Clients"}: ${s.by_group[g].n} answered${s.by_group[g].hidden ? " — average hidden until three people have answered" : s.by_group[g].overall != null ? `, overall ${s.by_group[g].overall}` : ""}.`)),
      (s.comments || []).length ? h("ul", {}, s.comments.map((c) => h("li", {}, `${c.group === "FIRM" ? "Firm" : "Client"}: ${c.comment}`))) : null));
}

// ---------------------------------------------------------------- setup
function setupTab(pilot, a) {
  const p = pilot.current, g = pilot.guide, f = pilot.form && pilot.form.kind === "targets" ? pilot.form.f : null;
  const next = { PLANNING: "ACTIVE", ACTIVE: "COMPLETED" }[p.status];
  return h("div", {},
    h("div", { className: "card", id: "pilot-status-card" }, h("h3", {}, `${p.name} — ${PILOT_STATUS_TEXT[p.status]}`),
      h("p", {}, `Starts ${p.start_date}${p.end_date ? `, ends ${p.end_date}` : ""}. ${p.notes || ""}`),
      next ? h("button", { className: "btn btn-primary", id: "pilot-advance", disabled: pilot.busy || (next === "ACTIVE" && !p.can_start), onClick: () => a.setStatus(next) }, next === "ACTIVE" ? "Start the pilot" : "Mark completed") : null,
      next === "ACTIVE" && !p.can_start ? h("p", { style: "color: var(--ink-500);" }, "Add at least one client first.") : null,
      next === "COMPLETED" ? h("p", { style: "color: var(--ink-500);" }, "Completing a pilot is final. Take a snapshot first so the results are kept.") : null),
    h("div", { className: "card", id: "pilot-targets" }, h("h3", {}, "Targets"),
      h("p", {}, "Decide what success means before you look at results. Changes are recorded in the audit trail, and the log says whether the pilot had started."),
      f ? h("div", {}, Object.entries(g.target_labels).map(([k, label]) => field(label, `target-${k}`, text(`target-${k}`, f, k, a))),
        h("button", { className: "btn btn-primary", id: "targets-save", disabled: pilot.busy, onClick: a.saveTargets }, "Save targets"), " ", h("button", { className: "btn btn-secondary", onClick: a.cancelForm }, "Cancel"))
        : h("div", {}, h("ul", { className: "clean" }, Object.entries(g.target_labels).map(([k, label]) => h("li", {}, `${label}: ${p.targets[k]}`))),
          h("button", { className: "btn btn-secondary", id: "targets-edit", onClick: () => a.startForm("targets", Object.fromEntries(Object.keys(g.target_labels).map((k) => [k, p.targets[k]]))) }, "Change targets"))));
}

// ---------------------------------------------------------------- snapshots + report
function reportTab(pilot, a) {
  const snaps = pilot.snapshots || [];
  return h("div", {},
    h("div", { className: "card", id: "pilot-snapshots" }, h("h3", {}, "Snapshots"),
      h("p", {}, "A snapshot freezes the combined results at a moment, with a fingerprint, so you can show later what the figures were. It stores only combined figures, never a client's own."),
      h("button", { className: "btn btn-primary", id: "snapshot-take", disabled: pilot.busy || pilot.current.status === "PLANNING", onClick: a.takeSnapshot }, "Take a snapshot"),
      pilot.current.status === "PLANNING" ? h("p", { style: "color: var(--ink-500);" }, "Start the pilot first.") : null,
      snaps.length === 0 ? h("p", {}, "No snapshots yet.") : h("ul", {}, snaps.slice().reverse().map((s) => h("li", { "data-snapshot": s.id }, `${when(s.taken_at)} — ${s.clients_included} of ${s.clients_total} clients, ${s.measures.filter((m) => m.status === "MET").length} of 11 targets met. Fingerprint ${s.hash.slice(0, 16)}…`)))),
    h("div", { className: "card", id: "pilot-report" }, h("h3", {}, "Pilot report"),
      h("p", {}, "A plain document for a board, a funder or your own records. It repeats the limits of the pilot at the bottom."),
      h("button", { className: "btn btn-secondary", id: "report-build", disabled: pilot.busy, onClick: a.buildReport }, "Build report"), " ",
      pilot.report ? h("button", { className: "btn btn-secondary", id: "report-download", onClick: a.downloadReport }, "Download") : null,
      pilot.report ? h("pre", { id: "report-text", style: "white-space:pre-wrap; margin-top:12px;" }, pilot.report.markdown) : null));
}

// ---------------------------------------------------------------- client "about"
function aboutTab(pilot, a) {
  const m = pilot.me.membership, left = pilot.form && pilot.form.kind === "leave" ? pilot.form.f : null;
  return h("div", { className: "card", id: "pilot-about" }, h("h3", {}, m.pilot.name),
    h("p", {}, `Your organisation (${m.client.label}) joined on ${when(m.client.kickoff)} with your written consent (${m.client.consent_reference}). The firm running the pilot can see figures from your ASAVEXA records only through people it has been given access for, and sees your time and survey entries as part of combined results.`),
    h("p", {}, "You can leave at any time. When you do, your data is removed from every result."),
    m.pilot.status === "COMPLETED" ? h("p", {}, "This pilot is completed.") : null,
    left ? h("div", {}, field("Why are you leaving?", "leave-reason", text("leave-reason", left, "reason", a)),
      h("button", { className: "btn btn-primary", id: "leave-confirm", disabled: pilot.busy, onClick: a.leave }, "Leave the pilot"), " ", h("button", { className: "btn btn-secondary", onClick: a.cancelForm }, "Cancel"))
      : pilot.me.can_withdraw ? h("button", { className: "btn btn-secondary", id: "leave-start", onClick: () => a.startForm("leave", { reason: "" }) }, "Leave the pilot") : h("p", { style: "color: var(--ink-500);" }, "Only an owner or administrator of your organisation can withdraw it."));
}
