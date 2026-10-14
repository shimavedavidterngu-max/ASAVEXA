import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState } from "../components/DataState.js";
import { TABS, UNIT_TEXT, DIRECTION_TEXT, FREQUENCY_TEXT, MIN_LEAD_CHOICES, ATTENTION_TONE, DIRECTION_WORD, MOVE_TEXT, canPrepare, canApprove, statusOf, words, who, ownerChoices, kpiMoves, canRecordReading, readingMoves, forecastMoves, unitLabel, waitingText, headline, shortfallText } from "../lib/fpa.js";

/**
 * Planning and KPIs. It records and checks; it does not calculate a KPI from the ledger or verify that a reading is true.
 * A KPI's owner accepts it and records its readings; a different person approves the target and reviews each reading.
 * A forecast is stamped with the day it was made and judged later against an actual that a second person records and a third confirms.
 */
const Badge = ({ tone, label, id }) => h("span", { className: `badge badge-${tone || "neutral"}`, id }, label);
const St = (s) => Badge({ ...statusOf(s) });
const note = (t, kind = "info", id) => (t ? h("div", { className: `alert alert-${kind}`, id, style: "margin-bottom:12px;", role: kind === "error" ? "alert" : "status" }, t) : null);
const field = (l, id, inp, hint) => h("div", { className: "field" }, h("label", { for: id }, l), inp, hint ? h("small", { style: "color: var(--ink-500);" }, hint) : null);
const text = (fp, a, form, k, id, ph) => h("input", { id, type: "text", value: (fp.forms[form] || {})[k] == null ? "" : (fp.forms[form] || {})[k], placeholder: ph || "", onInput: (e) => a.setForm(form, k, e.target.value) });
const sel = (fp, a, form, k, id, opts, blank) => h("select", { id, onChange: (e) => a.setForm(form, k, e.target.value, true) },
  [...(blank ? [h("option", { value: "" }, blank)] : []), ...opts.map(([v, l]) => h("option", { value: v, selected: String((fp.forms[form] || {})[k]) === String(v) }, l))]);
const table = (head, rows, id) => h("div", { className: "table-scroll" }, h("table", { className: "data-table", id }, h("thead", {}, h("tr", {}, head.map(([l, right]) => h("th", { style: right ? "text-align:right;" : undefined }, l)))), h("tbody", {}, rows)));
const td = (v, right) => h("td", { style: right ? "text-align:right;" : undefined }, v);
const btn = (l, id, onClick, kind = "secondary", disabled = false) => h("button", { className: `btn btn-${kind}`, id, disabled, onClick }, l);
const row = (...b) => h("div", { style: "display:flex; gap:8px; flex-wrap:wrap; margin:8px 0; align-items:end;" }, b.filter(Boolean));
const none = (t = "None.") => h("div", { style: "color: var(--ink-500);" }, t);
const card = (title, id, ...kids) => h("div", { className: "card", id, style: "margin-bottom:16px;" }, h("h3", {}, title), ...kids);
const hist = (items) => h("ul", {}, (items || []).map((x) => h("li", {}, `${String(x.at).slice(0, 10)} ${String(x.event).replace(/_/g, " ").toLowerCase()} by ${x.by}${x.note ? ": " + x.note : ""}`)));
const noteBox = (fp, a, key, l, id) => field(l, id || `note-${key}`, h("textarea", { id: id || `note-${key}`, rows: 2, onInput: (e) => a.setNote(key, e.target.value) }, fp.notes[key] || ""));
const formError = (fp, name) => (fp.formError && fp.formError.form === name ? note(fp.formError.text, "error", `${name}-problem`) : null);
const docs = (fp, a, form, id) => field("Attach a document (optional)", id, sel(fp, a, form, "evidence_id", id, (fp.vault || []).map((e) => [e.id, e.original_filename || e.filename || e.id]), "No document"), "A document from the Evidence Vault. Its file fingerprint is kept with the record.");

export function Fpa({ fp, role, userId, loading, onRetry, actions: a }) {
  return h("div", {},
    h("h1", {}, "Planning and KPIs"),
    note("This workspace records and checks. It does not calculate a KPI from the ledger or confirm that a reading is true. Each KPI has one owner who accepts it and records its readings; a different person approves the target and reviews each reading. A forecast is stamped with the day it is made and cannot be changed.", "warning", "fp-banner"),
    fp.error ? ErrorState({ message: fp.error, onRetry }) : null,
    note(fp.notice, "success", "fp-notice"),
    loading ? LoadingState() : h("div", {},
      h("div", { className: "tabs", role: "tablist", style: "display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px;" },
        TABS.map(([id, l]) => h("button", { className: `btn ${fp.tab === id ? "btn-primary" : "btn-secondary"}`, role: "tab", id: `fp-tab-${id}`, "aria-selected": fp.tab === id ? "true" : "false", onClick: () => a.setTab(id) }, l))),
      fp.busy ? h("div", { style: "color: var(--ink-500);" }, "Working...") : null,
      fp.tab === "overview" ? overview(fp, role, userId, a) : fp.tab === "kpis" ? kpis(fp, role, userId, a) : fp.tab === "forecasts" ? forecasts(fp, role, userId, a) : accuracy(fp, userId, a)));
}

// ---------------------------------------------------------------- overview
function overview(fp, role, me, a) {
  const o = fp.ov; if (!o) return none("Nothing loaded yet.");
  const c = o.counts;
  return h("div", {},
    card("What needs attention", "fp-attention", o.attention.length ? h("ul", {}, o.attention.map((x) => h("li", { "data-kind": x.kind }, Badge({ tone: ATTENTION_TONE[x.kind] || "info", label: words(x.kind) }), " ", x.kind === "FORECAST_BIAS" ? x.text : `${x.count} ${x.text}`))) : none("Nothing needs attention right now.")),
    card("Counts", "fp-counts", h("ul", {}, [["KPIs", c.kpis], ["Approved KPIs", c.active], ["Retired KPIs", c.retired], ["Forecasts", c.forecasts], ["Forecasts with a confirmed actual", c.forecasts_confirmed]].map(([l, n]) => h("li", {}, `${l}: ${n}`)))),
    card("Who owns what", "fp-owners", o.owners.length ? table([["Owner"], ["KPIs", true], ["Overdue", true], ["Off target", true], ["Not yet accepted", true]], o.owners.map((x) => h("tr", { "data-owner": x.owner }, td(who(x.owner, me)), td(String(x.kpis), true), td(String(x.overdue), true), td(String(x.off_target), true), td(String(x.not_accepted), true)))) : none("No KPI has an owner yet.")),
    policyCard(fp, role, a),
    card("What this does not do", "fp-limits", h("ul", {}, o.limitations.map((x) => h("li", {}, x)))));
}

function policyCard(fp, role, a) {
  const p = fp.ov.policy, f = fp.forms.policy;
  return card("Settings", "fp-policy", h("p", { id: "fp-policy-meaning" }, p.meaning),
    canApprove(role) && f ? h("div", {},
      row(field("Warning margin (% of target)", "fp-policy-watch", text(fp, a, "policy", "watch_pct", "fp-policy-watch"), "For KPIs defined from now on."), field("Days of grace before a reading is overdue", "fp-policy-grace", text(fp, a, "policy", "grace_days", "fp-policy-grace")),
        field("Accuracy band (% of actual)", "fp-policy-acc", text(fp, a, "policy", "accuracy_pct", "fp-policy-acc"), "For forecasts registered from now on."), field("Forecasts needed before an accuracy figure is meaningful", "fp-policy-min", text(fp, a, "policy", "min_items", "fp-policy-min"))),
      formError(fp, "policy"), btn("Save settings", "fp-policy-save", () => a.savePolicy(), "primary", fp.busy)) : h("p", { style: "color: var(--ink-500);" }, "Only an approver can change these settings."));
}

// ---------------------------------------------------------------- KPIs
function kpis(fp, role, me, a) {
  const f = fp.forms.kpi, owners = ownerChoices(fp.members);
  return h("div", {},
    card("KPIs", "fp-kpis", fp.kpis.length ? fp.kpis.map((k) => kpiCard(fp, role, me, a, k)) : none("No KPIs yet.")),
    canPrepare(role) ? card("Define a KPI", "fp-kpi-card",
      h("p", { style: "color: var(--ink-500);" }, "The target is typed in from your plan. A different person must approve it, and the owner cannot approve the target they are measured against. The owner must be someone who can record readings."),
      row(field("Name", "fp-kpi-name", text(fp, a, "kpi", "name", "fp-kpi-name", "Gross margin")), field("What it measures", "fp-kpi-desc", text(fp, a, "kpi", "description", "fp-kpi-desc")),
        field("Owner", "fp-kpi-owner", sel(fp, a, "kpi", "owner", "fp-kpi-owner", owners.map((m) => [m.user_id, `${who(m.user_id, me)} · ${words(m.role)}`]), "Choose a person"))),
      row(field("Unit", "fp-kpi-unit", sel(fp, a, "kpi", "unit", "fp-kpi-unit", Object.entries(UNIT_TEXT))), f.unit === "AMOUNT" ? field("Currency", "fp-kpi-cur", text(fp, a, "kpi", "currency", "fp-kpi-cur", "NGN")) : null,
        field("Better when", "fp-kpi-dir", sel(fp, a, "kpi", "direction", "fp-kpi-dir", Object.entries(DIRECTION_TEXT))), field("Measured", "fp-kpi-freq", sel(fp, a, "kpi", "frequency", "fp-kpi-freq", Object.entries(FREQUENCY_TEXT))),
        field("Target", "fp-kpi-target", text(fp, a, "kpi", "target", "fp-kpi-target", "0.00")), field("Warn within (% of target)", "fp-kpi-watch", text(fp, a, "kpi", "watch_pct", "fp-kpi-watch", "organisation setting")), field("Starts", "fp-kpi-from", text(fp, a, "kpi", "effective_from", "fp-kpi-from", "YYYY-MM-DD"))),
      row(field("Where the number comes from", "fp-kpi-source", text(fp, a, "kpi", "data_source", "fp-kpi-source")), field("How it is calculated", "fp-kpi-method", text(fp, a, "kpi", "method", "fp-kpi-method"))),
      formError(fp, "kpi"), btn("Define KPI", "fp-kpi-save", () => a.defineKpi(), "primary", fp.busy)) : null);
}

function kpiCard(fp, role, me, a, k) {
  const open = fp.sel.kpi && fp.sel.kpi.id === k.id ? fp.sel.kpi : null, moves = kpiMoves(k, me, role), key = `kpi-${k.id}`;
  return h("div", { className: "card", "data-kpi": k.id, style: "margin-bottom:10px;" },
    h("div", {}, h("strong", {}, `${k.ref} · ${k.name}`), " ", St(k.status), k.status !== "RETIRED" ? [" ", St(k.judgement)] : null, k.unreviewed ? [" ", Badge({ tone: "info", label: "Reading waiting for review" })] : null,
      k.overdue ? [" ", Badge({ tone: "warn", label: "Reading overdue" })] : null, k.status !== "RETIRED" && !k.owner_accepted ? [" ", Badge({ tone: "warn", label: "Owner has not accepted" })] : null),
    h("div", { style: "color: var(--ink-500);" }, `Owner ${who(k.owner, me)} · ${FREQUENCY_TEXT[k.frequency]} · ${unitLabel(k)} · ${k.meaning}`),
    h("div", {}, `Latest: ${headline(k)}${k.latest && k.latest.judgement !== "ON_TARGET" ? `. ${shortfallText(k.latest)}.` : ""}${k.due && k.status === "ACTIVE" ? ` Next period ends ${k.next_period_end}; reading due by ${k.due}.` : ""}`),
    waitingText(k, me, role) ? h("small", { className: "fp-waiting" }, waitingText(k, me, role)) : null,
    moves.length ? h("div", { style: "margin-top:6px;" }, noteBox(fp, a, key, "Note (required to retire)"), moves.includes("owner") ? ownerBox(fp, a, k, me) : null,
      row(moves.filter((m) => m !== "owner").map((m) => btn(MOVE_TEXT[m], `fp-kpi-${k.ref}-${m}`, () => a.kpiStep(k.id, m), m === "approve" ? "primary" : "secondary", fp.busy)))) : null,
    row(btn(open ? "Hide readings" : "Show readings", `fp-kpi-open-${k.ref}`, () => a.selectKpi(open ? null : k.id), "secondary", fp.busy)),
    open ? kpiDetail(fp, role, me, a, open) : null);
}

function ownerBox(fp, a, k, me) {
  const owners = ownerChoices(fp.members).filter((m) => m.user_id !== k.owner), f = fp.forms.reassign;
  return h("div", {}, row(field("New owner", `fp-owner-${k.ref}`, h("select", { id: `fp-owner-${k.ref}`, onChange: (e) => a.setForm("reassign", "owner", e.target.value) }, [h("option", { value: "" }, "Choose a person"), ...owners.map((m) => h("option", { value: m.user_id, selected: f.owner === m.user_id }, `${who(m.user_id, me)} · ${words(m.role)}`))])),
    field("Reason for the change", `fp-owner-reason-${k.ref}`, text(fp, a, "reassign", "reason", `fp-owner-reason-${k.ref}`)), btn("Change owner", `fp-kpi-${k.ref}-owner`, () => a.changeOwner(k.id), "secondary", fp.busy)), formError(fp, `owner-${k.id}`));
}

function kpiDetail(fp, role, me, a, k) {
  const f = fp.forms.reading;
  return h("div", { "data-detail": k.id },
    h("p", {}, `Where the number comes from: ${k.data_source}. How it is calculated: ${k.method}.`),
    h("h4", {}, "Readings"), k.readings.length ? table([["Ref"], ["Period ends"], ["Value", true], ["Against target"], ["Status"], ["Recorded by"], ["Source"], [""]], k.readings.map((r) => h("tr", { "data-reading": r.id },
      td(r.ref), td(r.period_end), td(r.value, true), td([St(r.judgement), r.shortfall_pct ? ` ${r.shortfall_pct}% short` : null]), td(St(r.status)), td(`${who(r.recorded_by, me)}${r.reviewed_by ? `, reviewed by ${who(r.reviewed_by, me)}` : ""}`),
      td([r.source_note, r.evidence.length ? h("div", {}, r.evidence.map((e) => h("small", { className: "fp-doc" }, `Document ${e.filename} (fingerprint ${String(e.file_hash).slice(0, 12)}…)`))) : h("small", { className: "fp-nodoc" }, "No document attached")]),
      td(readingMoves(r, me, role).length ? [btn(MOVE_TEXT.review, `fp-rd-review-${r.ref}`, () => a.readingStep(k.id, r.id, "review"), "primary", fp.busy), " ", btn(MOVE_TEXT.reject, `fp-rd-reject-${r.ref}`, () => a.readingStep(k.id, r.id, "reject"), "secondary", fp.busy)]
        : (r.status === "RECORDED" && canApprove(role) ? h("small", { className: "fp-waiting" }, "Waiting for a different approver") : null))))) : none("No reading recorded."),
    canApprove(role) && k.readings.some((r) => r.status === "RECORDED" && r.recorded_by !== me) ? noteBox(fp, a, `rd-${k.id}`, "Note (required to reject)") : null,
    canRecordReading(k, me, role) ? h("div", {}, h("h4", {}, "Record a reading"),
      row(field("Period ends", "fp-rd-date", text(fp, a, "reading", "period_end", "fp-rd-date", k.next_period_end || "YYYY-MM-DD")), field(`Value (${unitLabel(k)})`, "fp-rd-value", text(fp, a, "reading", "value", "fp-rd-value"))),
      field("Where this number came from", "fp-rd-source", text(fp, a, "reading", "source_note", "fp-rd-source")), docs(fp, a, "reading", "fp-rd-doc"),
      field("Reason for a correction (only if this period already has a reading)", "fp-rd-correction", text(fp, a, "reading", "correction_note", "fp-rd-correction")),
      formError(fp, "reading"), btn("Record reading", "fp-rd-save", () => a.recordReading(k.id), "primary", fp.busy))
      : (k.owner === me && k.status === "ACTIVE" && !k.owner_accepted ? note("Accept ownership of this KPI before recording a reading.", "info") : (k.status === "ACTIVE" ? h("small", { className: "fp-only-owner" }, "Only the owner records readings.") : null)),
    h("h4", {}, "History"), hist(k.history));
}

// ---------------------------------------------------------------- forecasts
function forecasts(fp, role, me, a) {
  const opts = fp.options ? fp.options.kpis : [], f = fp.forms.forecast;
  return h("div", {},
    card("Forecasts", "fp-forecasts", row(field("Show", "fp-fc-filter", h("select", { id: "fp-fc-filter", onChange: (e) => a.filterForecasts(e.target.value) }, [["", "All"], ["OPEN", "Waiting for the actual"], ["ACTUAL_RECORDED", "Actual waiting for confirmation"], ["CONFIRMED", "Confirmed"], ["WITHDRAWN", "Withdrawn"]]
        .map(([v, l]) => h("option", { value: v, selected: fp.forecastFilter === v }, l))))),
      fp.forecasts.length ? fp.forecasts.map((x) => forecastCard(fp, role, me, a, x)) : none("No forecasts.")),
    canPrepare(role) ? card("Register a forecast", "fp-fc-card",
      h("p", { style: "color: var(--ink-500);" }, "The forecast is stamped with today's date and cannot be changed or back-dated. You can only withdraw it. It must be for a period that has not yet ended."),
      row(field("What is forecast", "fp-fc-metric", text(fp, a, "forecast", "metric", "fp-fc-metric", "Monthly revenue")), field("Unit", "fp-fc-unit", sel(fp, a, "forecast", "unit", "fp-fc-unit", Object.entries(UNIT_TEXT))),
        f.unit === "AMOUNT" ? field("Currency", "fp-fc-cur", text(fp, a, "forecast", "currency", "fp-fc-cur", "NGN")) : null, field("For the period ending", "fp-fc-date", text(fp, a, "forecast", "period_end", "fp-fc-date", "YYYY-MM-DD")), field("Forecast value", "fp-fc-value", text(fp, a, "forecast", "value", "fp-fc-value"))),
      row(field("How it was made", "fp-fc-basis", text(fp, a, "forecast", "basis", "fp-fc-basis")), field("Linked KPI (optional)", "fp-fc-kpi", sel(fp, a, "forecast", "kpi_id", "fp-fc-kpi", opts.map((k) => [k.id, `${k.ref} ${k.name}`]), "No KPI"))),
      formError(fp, "forecast"), btn("Register forecast", "fp-fc-save", () => a.registerForecast(), "primary", fp.busy)) : null);
}

function forecastCard(fp, role, me, a, x) {
  const moves = forecastMoves(x, me, role), e = x.error;
  return h("div", { className: "card", "data-forecast": x.id, style: "margin-bottom:10px;" },
    h("div", {}, h("strong", {}, `${x.ref} · ${x.metric} · ${x.value} ${unitLabel(x)}`), " ", St(x.status), x.actual_due ? [" ", Badge({ tone: "warn", label: "Period ended: actual needed" })] : null),
    h("div", { style: "color: var(--ink-500);" }, `For the period ending ${x.period_end} · made on ${x.made_on} (${x.lead_days} days ahead) by ${who(x.forecaster, me)} · ${x.basis}${x.kpi_ref ? ` · KPI ${x.kpi_ref}` : ""}`),
    x.actual ? h("div", { className: "fp-actual" }, `Actual ${x.actual.value}, recorded by ${who(x.actual.recorded_by, me)} from: ${x.actual.source_note}${x.actual.confirmed_by ? `. Confirmed by ${who(x.actual.confirmed_by, me)}.` : ""}`) : null,
    e ? h("div", { className: "fp-error" }, `${DIRECTION_WORD[e.direction]}: forecast minus actual is ${e.error}${e.pct_error != null ? ` (${e.pct_error}% of the actual)` : " (the actual is zero, so no percentage)"}. ${e.within ? "Within" : "Outside"} the accuracy band.`) : null,
    x.status === "ACTUAL_RECORDED" && canApprove(role) && !moves.includes("confirm") ? h("small", { className: "fp-waiting" }, "Waiting for a third person to confirm") : null,
    moves.includes("actual") ? h("div", {}, h("h4", {}, "Record the actual"), row(field("Actual value", `fp-act-value-${x.ref}`, h("input", { id: `fp-act-value-${x.ref}`, type: "text", onInput: (ev) => a.setNote(`actval-${x.id}`, ev.target.value) })),
      field("Where it came from", `fp-act-source-${x.ref}`, h("input", { id: `fp-act-source-${x.ref}`, type: "text", onInput: (ev) => a.setNote(`actsrc-${x.id}`, ev.target.value) })),
      field("Attach a document (optional)", `fp-act-doc-${x.ref}`, h("select", { id: `fp-act-doc-${x.ref}`, onChange: (ev) => a.setNote(`actdoc-${x.id}`, ev.target.value) }, [h("option", { value: "" }, "No document"), ...(fp.vault || []).map((d) => h("option", { value: d.id }, d.original_filename || d.filename || d.id))])),
      btn(MOVE_TEXT.actual, `fp-fc-${x.ref}-actual`, () => a.forecastStep(x.id, "actual"), "primary", fp.busy))) : null,
    moves.filter((m) => m !== "actual").length ? h("div", { style: "margin-top:6px;" }, noteBox(fp, a, `fc-${x.id}`, "Note (required to reject or withdraw)"), row(moves.filter((m) => m !== "actual").map((m) => btn(MOVE_TEXT[m], `fp-fc-${x.ref}-${m}`, () => a.forecastStep(x.id, m), m === "confirm" ? "primary" : "secondary", fp.busy)))) : null,
    h("details", {}, h("summary", {}, "History"), hist(x.history)));
}

// ---------------------------------------------------------------- accuracy
function accuracy(fp, me, a) {
  const r = fp.accuracy; if (!r) return none("Nothing loaded yet.");
  return h("div", {},
    card("Forecast accuracy", "fp-accuracy", h("p", { id: "fp-acc-meaning", style: "color: var(--ink-500);" }, r.meaning),
      row(field("Only forecasts made at least this many days ahead", "fp-acc-lead", h("select", { id: "fp-acc-lead", onChange: (e) => a.setMinLead(Number(e.target.value)) }, MIN_LEAD_CHOICES.map((n) => h("option", { value: n, selected: r.min_lead_days === n }, `${n} days`))))),
      h("ul", { id: "fp-acc-counts" }, [`Forecasts counted: ${r.counted}`, `Left out because they were made too late: ${r.excluded_short_lead}`, `Actuals waiting for confirmation: ${r.awaiting_confirmation}`, `Forecasts whose period ended with no actual yet: ${r.open_due}`].map((x) => h("li", {}, x))),
      r.groups.length ? table([["What"], ["Unit"], ["Forecasts", true], ["Weighted error %", true], ["Bias %", true], ["Average error", true], ["Too high", true], ["Too low", true], ["Within band %", true], [""]], r.groups.map((g) => h("tr", { "data-group": `${g.metric}|${g.currency || g.unit}` },
        td(g.metric), td(g.currency || UNIT_TEXT[g.unit]), td(String(g.n), true), td(g.wape == null ? "—" : g.wape, true), td(g.bias == null ? "—" : g.bias, true), td(g.mean_abs_error, true), td(String(g.over), true), td(String(g.under), true), td(g.hit_rate, true),
        td(g.enough ? null : Badge({ tone: "warn", label: `Fewer than ${r.min_items}: not meaningful yet` }))))) : none("No forecast has a confirmed actual yet."),
      h("p", { style: "color: var(--ink-500);" }, "Bias above zero means forecasts ran too high; below zero, too low. Units and currencies are never added together.")),
    card("By forecaster", "fp-by-person", r.forecasters.length ? table([["Forecaster"], ["Forecasts", true], ["Within band %", true], ["Too high", true], ["Too low", true]], r.forecasters.map((p) => h("tr", {}, td(who(p.forecaster, me)), td(String(p.n), true), td(p.hit_rate, true), td(String(p.over), true), td(String(p.under), true)))) : none("Nothing to show yet.")));
}
