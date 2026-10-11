import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState, EmptyState } from "../components/DataState.js";
import { TABS, canPrepare, ruleState, calState, ruleActions, num, rateText } from "../lib/tax.js";

/**
 * Tax Compliance. Every rate, band, date and source shown here came from a rule on the server that a person entered and a different person approved.
 * The page never contains a tax rate of its own and never claims to file anything.
 */
const Badge = ({ tone, label, id }) => h("span", { className: `badge badge-${tone || "neutral"}`, id }, label);
const note = (t, kind = "info") => (t ? h("div", { className: `alert alert-${kind}`, style: "margin-bottom:12px;", role: kind === "error" ? "alert" : "status" }, t) : null);
const field = (label, id, input, hint) => h("div", { className: "field" }, h("label", { for: id }, label), input, hint ? h("small", { style: "color: var(--ink-500);" }, hint) : null);
const input = (id, f, k, onChange, ph, type = "text") => h("input", { id, type, value: f[k] == null ? "" : f[k], placeholder: ph || "", onInput: (e) => onChange(k, e.target.value) });
const select = (id, f, k, onChange, opts) => h("select", { id, onChange: (e) => onChange(k, e.target.value) }, opts.map(([v, l]) => h("option", { value: v, selected: f[k] === v }, l)));
const table = (head, rows, id) => h("div", { className: "table-scroll" }, h("table", { className: "data-table", id }, h("thead", {}, h("tr", {}, head.map(([l, right]) => h("th", { style: right ? "text-align:right;" : undefined }, l)))), h("tbody", {}, rows)));
const td = (v, right) => h("td", { style: right ? "text-align:right;" : undefined }, v);

export function Tax({ tx, role, userId, loading, onRetry, actions }) {
  return h("div", {},
    h("h1", {}, "Tax Compliance"),
    h("p", { style: "color: var(--ink-500); margin-top:-8px;" }, "Every country has its own rules. ASAVEXA holds none of its own: you enter each rule from the official source, a second person approves it, and only then can it be used."),
    tx.error ? ErrorState({ message: tx.error, onRetry }) : null,
    note(tx.notice, "success"),
    loading ? LoadingState() : h("div", {},
      overviewBar(tx),
      h("div", { className: "tabs", role: "tablist", style: "display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px;" },
        TABS.map(([id, label]) => h("button", { className: `btn ${tx.tab === id ? "btn-primary" : "btn-secondary"}`, role: "tab", id: `tx-tab-${id}`, "aria-selected": tx.tab === id ? "true" : "false", onClick: () => actions.setTab(id) }, label))),
      tx.busy && !tx.loaded[tx.tab] ? LoadingState() : body(tx, role, userId, actions),
      h("p", { style: "color: var(--ink-500); font-size:0.9em; margin-top:16px;", id: "tx-disclaimer" }, "Calculations and deadlines here are estimates built from the rules you approved. They are not tax advice, not a return, and nothing is filed with any authority. Check the source and ask a qualified tax adviser before you file.")));
}

function overviewBar(tx) {
  const o = tx.overview; if (!o) return null;
  return h("div", { style: "display:flex; flex-wrap:wrap; gap:8px; margin-bottom:12px;", id: "tx-overview" },
    [["Countries selected", o.selected, "tx-o-sel"], ["Rules in force", o.rules_in_force, "tx-o-live"], ["Rules waiting for review", o.rules_waiting, "tx-o-wait"]].map(([k, v, id]) => h("div", { className: "card", style: "padding:8px 12px; min-width:140px;" }, h("div", { style: "color: var(--ink-500);" }, k), h("strong", { id }, String(v)))),
    o.selected_without_rules.length ? h("div", { className: "card", style: "padding:8px 12px; flex:1; min-width:240px;", id: "tx-norules" }, h("div", { style: "color: var(--ink-500);" }, "Selected but no rule in force yet"), h("span", {}, o.selected_without_rules.map((c) => c.name).join(", "))) : null);
}

function body(tx, role, userId, a) {
  switch (tx.tab) {
    case "countries": return countries(tx, role, a);
    case "rules": return tx.form ? ruleForm(tx, a) : tx.rule ? ruleDetail(tx, role, userId, a) : rules(tx, role, a);
    case "calculator": return calculator(tx, role, a);
    case "calendar": return calendar(tx, role, a);
    default: return null;
  }
}

// ---------------------------------------------------------------- countries
function countries(tx, role, a) {
  const c = tx.countries; if (!c) return null;
  const prep = canPrepare(role);
  return h("div", { id: "tx-countries" },
    note(c.note, "info"),
    h("div", { style: "display:flex; gap:12px; flex-wrap:wrap; align-items:flex-end; margin-bottom:12px;" },
      field("Search a country or code", "tx-q", h("input", { id: "tx-q", type: "search", value: tx.q, placeholder: "for example Kenya or KE", onInput: (e) => a.search(e.target.value) })),
      field("Region", "tx-region", h("select", { id: "tx-region", onChange: (e) => a.setRegion(e.target.value) }, [h("option", { value: "" }, "All regions"), ...c.regions.map((r) => h("option", { value: r, selected: tx.region === r }, r))])),
      h("div", { style: "color: var(--ink-500); padding-bottom:8px;", id: "tx-count" }, `Showing ${c.shown} of ${c.total} countries and territories. ${c.with_rules} with a rule in force.`)),
    c.countries.length === 0 ? EmptyState({ title: "No country matches", message: "Try a different spelling or clear the region." })
      : table([["Country"], ["Currency"], ["Region"], ["Rules in force", true], ["Waiting", true], ["Draft", true], ["Registration no."], [""]], c.countries.map((x) => h("tr", { "data-country": x.code },
        td(`${x.name} (${x.code})`), td(x.currency), td(x.region), td(String(x.rules_in_force), true), td(String(x.rules_waiting), true), td(String(x.rules_draft), true),
        td(x.selected && prep ? h("input", { id: `reg-${x.code}`, type: "text", value: tx.regDraft[x.code] !== undefined ? tx.regDraft[x.code] : x.registration, placeholder: "optional", onInput: (e) => a.regChange(x.code, e.target.value), onBlur: () => a.saveReg(x.code) }) : (x.registration || "")),
        td([x.selected ? Badge({ tone: "pass", label: "Selected" }) : null, " ",
          prep ? h("button", { className: "btn btn-secondary", id: `sel-${x.code}`, disabled: tx.busy, onClick: () => a.toggleCountry(x.code, !x.selected) }, x.selected ? "Remove" : "Select") : null,
          " ", h("button", { className: "btn btn-secondary", id: `rules-${x.code}`, onClick: () => a.viewRules(x.code) }, "Rules")]))), "tx-country-table"));
}

// ---------------------------------------------------------------- rules list
function rules(tx, role, a) {
  const prep = canPrepare(role);
  return h("div", { id: "tx-rules" },
    h("div", { style: "display:flex; gap:12px; flex-wrap:wrap; align-items:flex-end; margin-bottom:12px;" },
      field("Country", "tx-rule-country", h("select", { id: "tx-rule-country", onChange: (e) => a.filterRules(e.target.value) }, [h("option", { value: "" }, "All countries"), ...(tx.countryList || []).map((c) => h("option", { value: c.code, selected: tx.ruleFilter === c.code }, `${c.name} (${c.code})`))])),
      prep ? h("button", { className: "btn btn-primary", id: "rule-new", onClick: () => a.newRule() }, "Enter a new rule") : null),
    tx.rules.length === 0 ? EmptyState({ title: "No rules yet", message: "Nothing is assumed. Enter a rule from the official source for the country you need, then ask a colleague to review it." })
      : table([["Country"], ["Tax"], ["Rule"], ["Rate"], ["From"], ["To"], ["Status"], [""]], tx.rules.map((r) => h("tr", { "data-rule": r.id },
        td(`${r.country_name} (${r.country})`), td(r.tax_type_text), td(r.name), td(rateText(r)), td(r.effective_from), td(r.effective_to || "open"), td(Badge({ tone: ruleState(r.status).tone, label: ruleState(r.status).label })),
        td(h("button", { className: "btn btn-secondary", id: `rule-open-${r.id}`, onClick: () => a.openRule(r.id) }, "Open")))), "tx-rule-table"));
}

// ---------------------------------------------------------------- rule form
function ruleForm(tx, a) {
  const f = tx.form, o = tx.options;
  if (!o) return LoadingState();
  return h("div", { id: "tx-form", className: "card" },
    h("h2", {}, f.id ? "Edit rule" : f.replaces ? "Replacement rule" : "Enter a tax rule"),
    note("Copy the rate or bands from the official law or the authority's notice. Add the exact source so the reviewer can check it. Nothing here is guessed or pre-filled.", "info"),
    field("Country", "rf-country", h("select", { id: "rf-country", onChange: (e) => a.formChange("country", e.target.value) }, [h("option", { value: "" }, "Choose a country"), ...(tx.countryList || []).map((c) => h("option", { value: c.code, selected: f.country === c.code }, `${c.name} (${c.code})`))])),
    field("Type of tax", "rf-type", select("rf-type", f, "tax_type", a.formChange, Object.entries(o.tax_types))),
    field("Rule name", "rf-name", input("rf-name", f, "name", a.formChange, "for example Standard rate"), "Rules with the same country, type and name cannot overlap in time."),
    field("How is it calculated?", "rf-method", select("rf-method", f, "method", a.formChange, Object.entries(o.methods))),
    f.method === "FLAT" ? field("Rate (%)", "rf-rate", input("rf-rate", f, "rate", a.formChange)) : h("div", { id: "rf-bands" }, h("h4", {}, "Bands"),
      f.brackets.map((b, i) => h("div", { style: "display:flex; gap:8px; flex-wrap:wrap; align-items:flex-end; margin-bottom:6px;", "data-band": String(i) },
        field("From", `band-from-${i}`, h("input", { id: `band-from-${i}`, value: b.from, onInput: (e) => a.bandChange(i, "from", e.target.value) })),
        field("Up to (empty = no limit)", `band-to-${i}`, h("input", { id: `band-to-${i}`, value: b.up_to, onInput: (e) => a.bandChange(i, "up_to", e.target.value) })),
        field("Rate (%)", `band-rate-${i}`, h("input", { id: `band-rate-${i}`, value: b.rate, onInput: (e) => a.bandChange(i, "rate", e.target.value) })),
        f.brackets.length > 1 ? h("button", { className: "btn btn-secondary", onClick: () => a.removeBand(i) }, "Remove") : null)),
      h("button", { className: "btn btn-secondary", id: "band-add", onClick: () => a.addBand() }, "Add a band")),
    field("Rounding", "rf-round", select("rf-round", f, "rounding", a.formChange, o.rounding.map((x) => [x, { HALF_UP: "Half up (0.5 rounds up)", DOWN: "Down (always drop)", HALF_EVEN: "Half even (banker's rounding)" }[x] || x]))),
    field("Starts on (YYYY-MM-DD)", "rf-from", input("rf-from", f, "effective_from", a.formChange, "2026-01-01")),
    field("Ends on (optional)", "rf-to", input("rf-to", f, "effective_to", a.formChange, "leave empty if still in force")),
    field("Tax authority", "rf-auth", input("rf-auth", f, "authority", a.formChange)),
    field("Law, section or notice", "rf-src", input("rf-src", f, "source_title", a.formChange, "for example Finance Act 2026, section 12")),
    field("Link to the official source", "rf-url", input("rf-url", f, "source_url", a.formChange, "https://")),
    field("Notes (optional)", "rf-notes", input("rf-notes", f, "notes", a.formChange)),
    h("label", { style: "display:block; margin:8px 0;" }, h("input", { type: "checkbox", id: "rf-filing-on", checked: !!f.filing_on, onChange: (e) => a.formChange("filing_on", e.target.checked) }), " This tax has regular returns (adds it to the calendar)"),
    f.filing_on ? h("div", { id: "rf-filing" },
      field("How often", "rf-freq", select("rf-freq", f, "frequency", a.formChange, o.frequencies.map((x) => [x, x.replace("_", " ").toLowerCase()]))),
      field("Days after the period ends that the return is due", "rf-days", input("rf-days", f, "due_days", a.formChange)),
      field("First period starts on (empty = rule start date)", "rf-anchor", input("rf-anchor", f, "period_anchor", a.formChange, "2026-01-01")),
      field("Name of the return (optional)", "rf-form", input("rf-form", f, "form", a.formChange))) : null,
    h("div", { style: "display:flex; gap:8px;" }, h("button", { className: "btn btn-primary", id: "rf-save", disabled: tx.busy, onClick: () => a.saveRule() }, "Save as draft"), h("button", { className: "btn btn-secondary", id: "rf-cancel", onClick: () => a.cancelForm() }, "Cancel")));
}

// ---------------------------------------------------------------- rule detail
function ruleDetail(tx, role, userId, a) {
  const r = tx.rule, st = ruleState(r.status), act = ruleActions(r, role, userId);
  return h("div", { id: "tx-rule" },
    h("button", { className: "btn btn-secondary", id: "rule-back", onClick: () => a.closeRule() }, "Back to rules"),
    h("h2", {}, `${r.country_name}: ${r.name} `, Badge({ tone: st.tone, label: st.label, id: "rule-state" })),
    h("div", { className: "card", style: "margin-bottom:12px;", id: "rule-facts" },
      h("div", {}, h("strong", {}, r.tax_type_text), ` in ${r.country_name}, currency ${r.currency}. Version ${r.version}.`),
      h("div", {}, r.method === "FLAT" ? `Flat rate ${r.rate}%.` : "Progressive bands:"),
      r.method === "BRACKETS" ? table([["From", true], ["Up to", true], ["Rate", true]], r.brackets.map((b) => h("tr", {}, td(num(b.from), true), td(b.up_to == null ? "no limit" : num(b.up_to), true), td(`${b.rate}%`, true)))) : null,
      h("div", {}, `Applies from ${r.effective_from}${r.effective_to ? ` to ${r.effective_to}` : " with no end date"}. Rounding: ${r.rounding.replace("_", " ").toLowerCase()}.`),
      h("div", {}, `Authority: ${r.authority}. Source: ${r.source_title} `, h("a", { href: r.source_url, target: "_blank", rel: "noopener noreferrer" }, "(open the source)")),
      r.filing ? h("div", {}, `Returns: ${r.filing.frequency.replace("_", " ").toLowerCase()}${r.filing.form ? `, ${r.filing.form}` : ""}, due ${r.filing.due_days_after_period_end} days after each period ends.`) : null,
      r.notes ? h("div", { style: "color: var(--ink-500);" }, r.notes) : null,
      r.fingerprint ? h("div", { style: "color: var(--ink-500); font-size:0.85em;" }, `Fingerprint ${r.fingerprint}`) : null),
    act.ownSubmission ? note("You prepared or submitted this rule, so a different person must review it. ASAVEXA does not let you approve your own work.", "info") : null,
    r.decision_note ? note(`${r.status === "REJECTED" ? "Sent back" : "Reviewed"} by ${r.decided_by}: ${r.decision_note}`, r.status === "REJECTED" ? "warning" : "success") : null,
    h("div", { style: "display:flex; gap:8px; flex-wrap:wrap; margin-bottom:12px;" },
      act.edit ? h("button", { className: "btn btn-secondary", id: "rule-edit", onClick: () => a.editRule() }, "Edit") : null,
      act.submit ? h("button", { className: "btn btn-primary", id: "rule-submit", disabled: tx.busy, onClick: () => a.submitRule() }, "Submit for review") : null,
      act.discard ? h("button", { className: "btn btn-secondary", id: "rule-discard", disabled: tx.busy, onClick: () => a.discardRule() }, "Discard draft") : null,
      act.replace ? h("button", { className: "btn btn-secondary", id: "rule-replace", onClick: () => a.replaceRule() }, "Create a replacement (law changed)") : null),
    act.decide ? h("div", { className: "card", style: "margin-bottom:12px;" }, h("h3", {}, "Your review"), note("Open the source and check the rate, dates and wording against it before approving.", "warning"),
      field("Note or reason", "rule-decision", h("input", { id: "rule-decision", type: "text", value: tx.decisionNote, onInput: (e) => a.decisionChange(e.target.value) }), "A reason is required if you send it back."),
      h("button", { className: "btn btn-primary", id: "rule-approve", disabled: tx.busy, onClick: () => a.decide(true) }, "Approve"), " ", h("button", { className: "btn btn-secondary", id: "rule-reject", disabled: tx.busy, onClick: () => a.decide(false) }, "Send back")) : null,
    h("div", { className: "card" }, h("h3", {}, "History"), h("ul", { style: "padding-left:18px;" }, r.history.map((x) => h("li", {}, `${x.at.slice(0, 16).replace("T", " ")} · ${x.action} · ${x.actor}${x.note ? ` · ${x.note}` : ""}`)))));
}

// ---------------------------------------------------------------- calculator
function calculator(tx, role, a) {
  const f = tx.calcForm, prep = canPrepare(role), live = tx.liveRules, c = tx.calc;
  return h("div", { id: "tx-calc" },
    live.length === 0 ? note("No rule is in force yet, so there is nothing to calculate with. Enter a rule on the Rules tab and have a colleague approve it.", "warning") : null,
    prep ? h("div", { className: "card", style: "margin-bottom:12px;" }, h("h3", {}, "Calculate"),
      field("Rule (in force only)", "calc-rule", h("select", { id: "calc-rule", onChange: (e) => a.calcChange("rule_id", e.target.value) }, [h("option", { value: "" }, "Choose a rule"), ...live.map((r) => h("option", { value: r.id, selected: f.rule_id === r.id }, `${r.country_name}: ${r.name} (${rateText(r)}) from ${r.effective_from}`))])),
      field("Amount", "calc-amount", input("calc-amount", f, "amount", a.calcChange)),
      field("Date the amount relates to (YYYY-MM-DD)", "calc-date", input("calc-date", f, "date", a.calcChange)),
      h("label", { style: "display:block; margin:8px 0;" }, h("input", { type: "checkbox", id: "calc-incl", checked: !!f.inclusive, onChange: (e) => a.calcChange("inclusive", e.target.checked) }), " The amount already includes the tax (flat-rate rules only)"),
      h("div", { style: "margin:8px 0;" }, "Or start from your ledger: ",
        h("select", { id: "calc-period", onChange: (e) => a.calcChange("period_id", e.target.value) }, [h("option", { value: "" }, "Choose a period"), ...(tx.periods || []).map((p) => h("option", { value: p.id, selected: f.period_id === p.id }, p.name))]), " ",
        h("select", { id: "calc-kind", onChange: (e) => a.calcChange("kind", e.target.value) }, [["revenue", "Revenue"], ["expenses", "Expenses"], ["net_income", "Net income"]].map(([v, l]) => h("option", { value: v, selected: f.kind === v }, l))), " ",
        h("button", { className: "btn btn-secondary", id: "calc-ledger", disabled: !f.period_id || tx.busy, onClick: () => a.useLedger() }, "Use ledger amount")),
      tx.ledgerNote ? note(tx.ledgerNote, "info") : null,
      h("button", { className: "btn btn-primary", id: "calc-run", disabled: tx.busy, onClick: () => a.runCalc() }, "Calculate")) : note("Your role can view results but not run calculations.", "info"),
    c ? h("div", { className: "card", id: "calc-result", style: "margin-bottom:12px;" }, h("h3", {}, "ESTIMATE"),
      h("p", {}, `${c.rule.country_name}: ${c.rule.name} on ${c.date}, in ${c.currency}.`),
      h("div", { style: "display:flex; flex-wrap:wrap; gap:8px;" }, [["Before tax", c.net, "calc-net"], ["Tax", c.tax, "calc-tax"], ["Including tax", c.gross, "calc-gross"]].filter(([, v]) => v != null).map(([k, v, id]) => h("div", { className: "card", style: "padding:8px 12px; min-width:130px;" }, h("div", { style: "color: var(--ink-500);" }, k), h("strong", { id }, num(v))))),
      c.effective_rate_pct ? h("p", {}, `Effective rate ${c.effective_rate_pct}%.`) : null,
      c.bands ? table([["From", true], ["Up to", true], ["Rate", true], ["Amount taxed", true], ["Tax", true]], c.bands.map((b) => h("tr", {}, td(num(b.from), true), td(b.up_to == null ? "no limit" : num(b.up_to), true), td(`${b.rate}%`, true), td(num(b.taxed), true), td(num(b.tax), true)))) : null,
      h("h4", {}, "Working"), h("ul", { style: "padding-left:18px;" }, c.steps.map((s) => h("li", {}, s))),
      (c.warnings || []).map((w) => note(w, "warning")),
      c.basis ? h("p", { style: "color: var(--ink-500);" }, `Starting amount from the ledger: ${c.basis.label}.`) : null,
      h("p", { style: "color: var(--ink-500);" }, `Rule: ${c.rule.source_title} (${c.rule.authority}) `, h("a", { href: c.rule.source_url, target: "_blank", rel: "noopener noreferrer" }, "open the source"), `. Fingerprint ${c.rule.fingerprint}.`)) : null,
    tx.history.length ? h("div", { className: "card" }, h("h3", {}, "Recent calculations"), table([["When"], ["Country"], ["Rule"], ["Amount", true], ["Tax", true], ["By"]], tx.history.map((x) => h("tr", {}, td(x.calculated_at.slice(0, 16).replace("T", " ")), td(x.rule.country_name), td(x.rule.name), td(num(x.input), true), td(num(x.tax), true), td(x.calculated_by))), "calc-history")) : null);
}

// ---------------------------------------------------------------- calendar
function calendar(tx, role, a) {
  const cal = tx.cal, prep = canPrepare(role);
  return h("div", { id: "tx-calendar" },
    h("div", { style: "display:flex; gap:12px; flex-wrap:wrap; align-items:flex-end; margin-bottom:12px;" },
      field("From", "cal-from", input("cal-from", cal, "start", a.calRange)), field("To", "cal-to", input("cal-to", cal, "end", a.calRange)),
      h("button", { className: "btn btn-primary", id: "cal-load", disabled: tx.busy, onClick: () => a.loadCalendar() }, "Show deadlines")),
    cal.data ? h("div", {}, note(cal.data.note, "info"), cal.data.overdue ? note(`${cal.data.overdue} deadline(s) are past due and not recorded as filed.`, "warning") : null,
      cal.data.items.length === 0 ? EmptyState({ title: "No deadlines in this range", message: "Select a country, and have a rule with a return schedule approved, to see its deadlines." })
        : table([["Due"], ["Country"], ["Tax / return"], ["Period"], ["Status"], [""]], cal.data.items.map((i) => h("tr", { "data-due": i.key },
          td(i.due), td(i.country_name), td(`${i.rule}${i.form ? ` · ${i.form}` : ""}`), td(`${i.period_start} to ${i.period_end}`), td(Badge({ tone: calState(i.state).tone, label: calState(i.state).label })),
          td(i.state === "FILED" ? `Ref ${i.filed.reference}, recorded by ${i.filed.filed_by}` : prep ? [h("input", { id: `ref-${i.rule_id}-${i.period_end}`, type: "text", placeholder: "Filing reference", value: tx.refDraft[i.key] || "", onInput: (e) => a.refChange(i.key, e.target.value) }), " ",
            h("button", { className: "btn btn-secondary", id: `filed-${i.rule_id}-${i.period_end}`, onClick: () => a.markFiled(i) }, "I filed this")] : ""))), "cal-table"),
      h("p", { style: "color: var(--ink-500);" }, cal.data.limitations)) : null);
}
