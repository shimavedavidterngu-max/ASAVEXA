import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState, EmptyState } from "../components/DataState.js";
import { TABS, RATIO_TONE, RATIO_STATUS_TEXT, TAG_TEXT, num, ratioText, groupRatios, pctText, favText, favTone, reportState, reportActions, canPrepare, canApprove } from "../lib/analysis.js";

/**
 * Financial Analysis. Every number on this page is calculated by the server from the posted ledger and shown as received; the page never adds, divides or
 * estimates. Forecasts are always labelled FORECAST. Buttons appear only for what the person is allowed to do (the server checks again).
 */
const Badge = ({ tone, label, id }) => h("span", { className: `badge badge-${tone || "neutral"}`, id }, label);
const note = (t, kind = "info") => (t ? h("div", { className: `alert alert-${kind}`, style: "margin-bottom:12px;", role: kind === "error" ? "alert" : "status" }, t) : null);
const field = (label, id, input, hint) => h("div", { className: "field" }, h("label", { for: id }, label), input, hint ? h("small", { style: "color: var(--ink-500);" }, hint) : null);
const text = (id, f, k, onChange, ph, type = "text") => h("input", { id, type, value: f[k] == null ? "" : f[k], placeholder: ph || "", onInput: (e) => onChange(k, e.target.value) });
const tile = (k, v, id) => h("div", { className: "card", style: "padding:8px 12px; min-width:130px;" }, h("div", { style: "color: var(--ink-500);" }, k), h("strong", { id }, v));
const table = (head, rows, id) => h("div", { className: "table-scroll" }, h("table", { className: "data-table", id }, h("thead", {}, h("tr", {}, head.map(([l, right]) => h("th", { style: right ? "text-align:right;" : undefined }, l)))), h("tbody", {}, rows)));
const td = (v, right) => h("td", { style: right ? "text-align:right;" : undefined }, v);

export function Analysis({ an, periods, loading, role, userId, onRetry, actions }) {
  const periodList = periods || [];
  return h("div", {},
    h("h1", {}, "Financial Analysis"),
    h("p", { style: "color: var(--ink-500); margin-top:-8px;" }, "Ratios, variance, forecasts and analysis reports built from your posted ledger. Every figure shows its working."),
    an.error ? ErrorState({ message: an.error, onRetry }) : null,
    note(an.notice),
    loading ? LoadingState() : periodList.length === 0 ? EmptyState({ title: "No accounting periods yet", message: "Open a period and post journals first." }) : h("div", {},
      h("div", { style: "display:flex; gap:12px; flex-wrap:wrap; align-items:flex-end; margin-bottom:12px;" },
        field("Period", "an-period", h("select", { id: "an-period", onChange: (e) => actions.setPeriod(e.target.value) }, [h("option", { value: "" }, "Choose a period"), ...periodList.map((p) => h("option", { value: p.id, selected: an.period_id === p.id }, p.name))]))),
      h("div", { className: "tabs", role: "tablist", style: "display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px;" },
        TABS.map(([id, label]) => h("button", { className: `btn ${an.tab === id ? "btn-primary" : "btn-secondary"}`, role: "tab", id: `an-tab-${id}`, "aria-selected": an.tab === id ? "true" : "false", onClick: () => actions.setTab(id) }, label))),
      !an.period_id && an.tab !== "reports" && an.tab !== "setup" ? h("p", { style: "color: var(--ink-500);" }, "Choose a period to begin.") : an.busy && !an.loaded[an.tab] ? LoadingState() : body(an, role, userId, actions)));
}

function body(an, role, userId, a) {
  switch (an.tab) {
    case "overview": return overview(an);
    case "ratios": return ratios(an, a);
    case "variance": return variance(an, role, a);
    case "budget": return budget(an, role, a);
    case "forecast": return forecast(an, role, a);
    case "reports": return reports(an, role, userId, a);
    case "setup": return setup(an, role, a);
    default: return null;
  }
}

// ---------------------------------------------------------------- overview
function overview(an) {
  const o = an.overview; if (!o) return null;
  const t = o.totals;
  return h("div", { id: "an-overview" },
    h("div", { style: "display:flex; flex-wrap:wrap; gap:8px; margin-bottom:12px;" }, [["Assets", t.assets], ["Liabilities", t.liabilities], ["Total equity", t.equity_total], ["Revenue", t.revenue], ["Expenses", t.expenses], ["Net income", t.net_income]].map(([k, v]) => tile(k, num(v), `an-t-${k.toLowerCase().replace(" ", "-")}`))),
    o.issues.length ? h("div", { id: "an-issues" }, o.issues.map((i) => note(i, "warning"))) : note("The data for this period is ready for analysis.", "success"),
    h("div", { className: "card" }, h("h3", {}, "How these figures are defined"), h("ul", { style: "padding-left:18px;" }, o.definitions.map((d) => h("li", {}, d))),
      h("p", { style: "color: var(--ink-500);" }, `${o.posted_entries} posted ledger entries. ${o.classified} of ${o.live_accounts} accounts with a balance are classified. Compared with: ${o.prior_period ? o.prior_period.name : "no earlier period"}.`)));
}

// ---------------------------------------------------------------- ratios
function ratios(an, a) {
  const r = an.ratios; if (!r) return null;
  return h("div", { id: "an-ratios" },
    h("p", {}, `${r.calculated} of ${r.total} ratios calculated. `, h("span", { style: "color: var(--ink-500);" }, r.note)),
    groupRatios(r.ratios).map((g) => h("div", { className: "card", style: "margin-bottom:12px;" }, h("h3", {}, g.name), g.ratios.map((x) => {
      const open = !!an.open[x.id];
      return h("div", { "data-ratio": x.id, style: "border-top:1px solid var(--line, #eee); padding:8px 0;" },
        h("div", { style: "display:flex; justify-content:space-between; gap:8px; flex-wrap:wrap;" }, h("div", {}, h("strong", {}, x.name), " ", Badge({ tone: RATIO_TONE[x.status], label: RATIO_STATUS_TEXT[x.status] })),
          h("div", {}, h("strong", { id: `ratio-${x.id}` }, ratioText(x)), " ", h("button", { className: "btn btn-secondary", "aria-expanded": open ? "true" : "false", onClick: () => a.toggle(x.id) }, open ? "Hide working" : "Show working"))),
        x.reason ? h("div", { style: "color: var(--ink-500);" }, x.reason) : null,
        open ? h("div", { style: "margin-top:6px;" }, h("div", {}, h("em", {}, "Formula: "), x.formula),
          h("div", {}, `${x.numerator.label}: `, h("strong", {}, num(x.numerator.amount)), x.numerator.accounts.length ? h("span", { style: "color: var(--ink-500);" }, ` (${x.numerator.accounts.map((c) => `${c.code} ${c.name} ${num(c.amount)}`).join("; ")})`) : null),
          x.denominator ? h("div", {}, `${x.denominator.label}: `, h("strong", {}, num(x.denominator.amount)), x.denominator.accounts.length ? h("span", { style: "color: var(--ink-500);" }, ` (${x.denominator.accounts.map((c) => `${c.code} ${c.name} ${num(c.amount)}`).join("; ")})`) : null) : null,
          h("div", { style: "color: var(--ink-500);" }, x.reading)) : null);
    }))));
}

// ---------------------------------------------------------------- variance
function variance(an, role, a) {
  const v = an.variance; if (!v) return null;
  if (v.status !== "OK") return note(v.message);
  return h("div", { id: "an-variance" },
    h("p", {}, `${v.current_period.name} compared with ${v.prior_period.name}. ${v.material_count} line(s) differ by at least ${num(v.thresholds.percent)}%${Number(v.thresholds.amount) > 0 ? ` and ${num(v.thresholds.amount)}` : ""}. `, h("span", { style: "color: var(--ink-500);" }, v.basis_note)),
    table([["Account"], ["Current", true], ["Prior", true], ["Change", true], ["Change %", true], ["Flag"], ["Notes"]], v.rows.map((r) => h("tr", { "data-var": r.code },
      td(`${r.code} ${r.name}`), td(num(r.current), true), td(num(r.prior), true), td(num(r.change), true), td(pctText(r.change_pct), true),
      td(r.material ? Badge({ tone: "warn", label: "Look into" }) : ""),
      td([...r.comments.map((c) => h("div", { style: "font-size:0.9em;" }, `${c.text} `, h("span", { style: "color: var(--ink-500);" }, `(${c.actor})`))),
        canPrepare(role) ? (an.noteFor === r.account_id ? h("div", {}, h("input", { id: `an-note-${r.code}`, type: "text", placeholder: "Why did it change?", value: an.noteText, onInput: (e) => a.noteChange(e.target.value) }), h("button", { className: "btn btn-primary", id: `an-note-save-${r.code}`, onClick: () => a.saveNote() }, "Save")) : h("button", { className: "btn btn-secondary", id: `an-note-add-${r.code}`, onClick: () => a.noteFor(r.account_id) }, "Add note")) : null]))), "an-var-table"));
}

// ---------------------------------------------------------------- budget
function budget(an, role, a) {
  const b = an.budget, bv = an.budgetVar; if (!b || !bv) return null;
  const prep = canPrepare(role), accounts = (an.config ? an.config.accounts : []).filter((x) => x.type === "REVENUE" || x.type === "EXPENSE");
  return h("div", { id: "an-budget" },
    note("This budget is a set of figures a person types in for comparison. It is not an approved budget from a budgeting module.", "info"),
    b.meta ? h("p", {}, `Version ${b.meta.version} entered by ${b.meta.entered_by}${b.meta.note ? `: ${b.meta.note}` : ""}.`) : h("p", { style: "color: var(--ink-500);" }, "No comparison budget has been entered for this period."),
    prep ? h("div", { className: "card", style: "margin-bottom:12px;" }, h("h3", {}, "Enter or revise the comparison budget"),
      accounts.map((x) => field(`${x.code} ${x.name}`, `bud-${x.code}`, h("input", { id: `bud-${x.code}`, type: "text", inputmode: "decimal", value: an.budgetForm[x.id] == null ? "" : an.budgetForm[x.id], onInput: (e) => a.budgetChange(x.id, e.target.value) }))),
      field("Note (optional)", "bud-note", h("input", { id: "bud-note", type: "text", value: an.budgetNote, onInput: (e) => a.budgetNoteChange(e.target.value) })),
      h("button", { className: "btn btn-primary", id: "bud-save", disabled: an.busy, onClick: () => a.saveBudget() }, "Save budget")) : null,
    bv.status !== "OK" ? null : table([["Account"], ["Budget", true], ["Actual", true], ["Variance", true], ["%", true], ["Result"]], bv.rows.map((r) => h("tr", { "data-bvar": r.code },
      td(`${r.code} ${r.name}`), td(num(r.budget), true), td(num(r.actual), true), td(num(r.variance), true), td(pctText(r.variance_pct), true), td([Badge({ tone: favTone(r.favourable), label: favText(r.favourable) }), r.material ? [" ", Badge({ tone: "warn", label: "Look into" })] : null]))), "an-bvar-table"));
}

// ---------------------------------------------------------------- forecast
function forecast(an, role, a) {
  const prep = canPrepare(role), f = an.scenarioForm, run = an.run;
  return h("div", { id: "an-forecast" },
    note("Everything on this tab is a FORECAST made from the assumptions shown. It is not an actual result, not advice, and is never written to your ledger.", "warning"),
    h("div", { className: "card", style: "margin-bottom:12px;" }, h("h3", {}, "Scenarios"),
      an.scenarios.length === 0 ? h("p", { style: "color: var(--ink-500);" }, "No scenarios yet for this period.") : h("ul", { style: "padding-left:18px;" }, an.scenarios.map((s) => h("li", { "data-scn": s.id }, `${s.name} (version ${s.version}) `,
        h("button", { className: "btn btn-secondary", id: `scn-run-${s.id}`, onClick: () => a.runScenario(s.id) }, "Run"), prep ? [" ", h("button", { className: "btn btn-secondary", onClick: () => a.editScenario(s.id) }, "Edit")] : null)))),
    prep ? h("div", { className: "card", style: "margin-bottom:12px;" }, h("h3", {}, f.id ? "Edit scenario" : "New scenario"),
      h("button", { className: "btn btn-secondary", id: "scn-fill", onClick: () => a.fillFromActuals() }, "Fill from this period's actuals"), an.suggestNote ? h("p", { style: "color: var(--ink-500);" }, an.suggestNote) : null,
      field("Name", "scn-name", text("scn-name", f, "name", a.scenarioChange)), field("Months to project (1 to 24)", "scn-months", text("scn-months", f, "months", a.scenarioChange)),
      field("Base monthly revenue", "scn-rev", text("scn-rev", f, "base_monthly_revenue", a.scenarioChange)), field("Base monthly expenses", "scn-exp", text("scn-exp", f, "base_monthly_expenses", a.scenarioChange)),
      field("Revenue growth per month (%)", "scn-rg", text("scn-rg", f, "revenue_growth_pct", a.scenarioChange)), field("Expense growth per month (%)", "scn-eg", text("scn-eg", f, "expense_growth_pct", a.scenarioChange)),
      field("Opening cash", "scn-cash", text("scn-cash", f, "opening_cash", a.scenarioChange)),
      h("button", { className: "btn btn-primary", id: "scn-save", disabled: an.busy, onClick: () => a.saveScenario() }, "Save scenario")) : null,
    run ? h("div", { className: "card", id: "scn-result", style: "margin-bottom:12px;" }, h("h3", {}, `${run.scenario.name}: FORECAST`),
      h("p", {}, `Closing cash after ${run.assumptions.months} months: `, h("strong", { id: "scn-closing" }, num(run.closing_cash)), `. Lowest cash ${num(run.lowest_cash)} in month ${run.lowest_cash_month}.`, run.first_month_negative ? h("strong", { style: "color: var(--danger, #b00020);" }, ` Cash runs out in month ${run.first_month_negative}.`) : " Cash stays positive in every month."),
      table([["Month", true], ["Revenue", true], ["Expenses", true], ["Net cash", true], ["Closing cash", true], ["Kind"]], run.rows.map((r) => h("tr", {}, td(String(r.month), true), td(num(r.revenue), true), td(num(r.expenses), true), td(num(r.net_cash), true), td(num(r.closing_cash), true), td("FORECAST"))), "scn-table"),
      h("h4", {}, "Sensitivity: what if revenue growth were different?"),
      table([["Monthly revenue growth", true], ["Closing cash", true], ["Lowest cash", true], ["First negative month", true]], run.sensitivity.map((s) => h("tr", {}, td(`${num(s.revenue_growth_pct)}%`, true), td(num(s.closing_cash), true), td(num(s.lowest_cash), true), td(s.first_month_negative == null ? "none" : String(s.first_month_negative), true)))),
      h("p", { style: "color: var(--ink-500);" }, run.limits)) : null,
    breakevenCard(an, a));
}

function breakevenCard(an, a) {
  const f = an.be, r = an.beResult;
  return h("div", { className: "card", id: "an-breakeven" }, h("h3", {}, "Break-even"), h("p", { style: "color: var(--ink-500);" }, "How many units must be sold to cover fixed costs. An estimate, not a guarantee."),
    field("Fixed costs", "be-fixed", text("be-fixed", f, "fixed_costs", a.beChange)), field("Selling price per unit", "be-price", text("be-price", f, "price", a.beChange)), field("Variable cost per unit", "be-var", text("be-var", f, "variable_cost", a.beChange)),
    h("button", { className: "btn btn-primary", id: "be-run", disabled: an.busy, onClick: () => a.runBreakeven() }, "Calculate"),
    r ? h("div", { id: "be-result", style: "margin-top:10px;" }, h("p", {}, "Break-even at ", h("strong", { id: "be-units" }, `${num(r.break_even_units)} units`), `, which is revenue of ${num(r.break_even_revenue)} (each unit contributes ${num(r.contribution_per_unit)}, ${num(r.contribution_margin_pct)}% of the price).`),
      table([["Price change", true], ["Price", true], ["Units to break even", true]], r.price_sensitivity.map((x) => h("tr", {}, td(`${x.price_change_pct}%`, true), td(num(x.price), true), td(x.units == null ? "never" : num(x.units), true)))), h("p", { style: "color: var(--ink-500);" }, `${r.formula}. ${r.limits}`)) : null);
}

// ---------------------------------------------------------------- reports
function reports(an, role, userId, a) {
  if (an.report) return reportDetail(an, role, userId, a);
  const f = an.reportForm;
  return h("div", { id: "an-reports" },
    an.reports.length === 0 ? EmptyState({ title: "No analysis reports yet", message: "A report freezes the figures, ratios, variance and chosen forecasts so a second person can review and approve them." })
      : table([["Title"], ["Period"], ["Status"], ["Version", true], ["Prepared by"], [""]], an.reports.map((r) => h("tr", { "data-report": r.id }, td(r.title), td((an.periodNames[r.period_id]) || r.period_id), td(Badge({ tone: reportState(r.status).tone, label: reportState(r.status).label })), td(String(r.version), true), td(r.submitted_by || r.created_by), td(h("button", { className: "btn btn-secondary", id: `rep-open-${r.id}`, onClick: () => a.openReport(r.id) }, "Open")))), "an-report-table"),
    canPrepare(role) && an.period_id ? h("div", { className: "card", style: "margin-top:12px;" }, h("h3", {}, "New analysis report for the chosen period"),
      field("Title", "rep-title", text("rep-title", f, "title", a.reportChange)), field("Note (optional)", "rep-note", text("rep-note", f, "note", a.reportChange)),
      an.scenarios.length ? h("div", { className: "field" }, h("label", {}, "Include forecast scenarios"), an.scenarios.map((s) => h("label", { style: "display:block;" }, h("input", { type: "checkbox", id: `rep-scn-${s.id}`, checked: f.scenario_ids.includes(s.id), onChange: (e) => a.reportScenario(s.id, e.target.checked) }), ` ${s.name}`))) : null,
      field("Evidence IDs (optional)", "rep-evid", text("rep-evid", f, "evidence_ids", a.reportChange, "Paste IDs from the Evidence page, separated by commas"), "Only evidence already in your Evidence Vault can be linked."),
      h("button", { className: "btn btn-primary", id: "rep-create", disabled: an.busy, onClick: () => a.createReport() }, "Create draft")) : null);
}

function reportDetail(an, role, userId, a) {
  const r = an.report, st = reportState(r.status), act = reportActions(r, role, userId), s = r.snapshot;
  return h("div", { id: "an-report" },
    h("button", { className: "btn btn-secondary", id: "rep-back", onClick: () => a.closeReport() }, "Back to reports"),
    h("h2", {}, r.title, " ", Badge({ tone: st.tone, label: st.label, id: "rep-state" })),
    h("p", { style: "color: var(--ink-500);" }, r.confidentiality),
    r.note ? h("p", {}, r.note) : null,
    h("div", { style: "display:flex; gap:8px; flex-wrap:wrap; margin-bottom:12px;" },
      act.submit ? h("button", { className: "btn btn-primary", id: "rep-submit", disabled: an.busy, onClick: () => a.submitReport() }, r.status === "REJECTED" ? "Submit again" : "Submit for review") : null,
      act.verify ? h("button", { className: "btn btn-secondary", id: "rep-verify", disabled: an.busy, onClick: () => a.verifyReport() }, "Check it is intact") : null,
      act.export ? h("button", { className: "btn btn-secondary", id: "rep-export", disabled: an.busy, onClick: () => a.exportReport() }, "Download CSV") : null),
    act.ownSubmission ? note("You submitted this analysis, so a different person must review it. ASAVEXA does not let you approve your own work.", "info") : null,
    act.decide ? h("div", { className: "card", style: "margin-bottom:12px;" }, h("h3", {}, "Your review"),
      field("Note or reason", "rep-decision", h("input", { id: "rep-decision", type: "text", value: an.decisionNote, onInput: (e) => a.decisionChange(e.target.value) }), "A reason is required if you send it back."),
      h("button", { className: "btn btn-primary", id: "rep-approve", disabled: an.busy, onClick: () => a.decide(true) }, "Approve"), " ", h("button", { className: "btn btn-secondary", id: "rep-reject", disabled: an.busy, onClick: () => a.decide(false) }, "Send back")) : null,
    r.decision_note ? note(`${r.status === "REJECTED" ? "Sent back" : "Approved"} by ${r.decided_by}: ${r.decision_note}`, r.status === "REJECTED" ? "warning" : "success") : null,
    an.verify ? note(an.verify.meaning + (an.verify.account_differences.length ? ` Different accounts now: ${an.verify.account_differences.map((d) => `${d.account} (${num(d.then)} then, ${num(d.now)} now)`).join("; ")}.` : ""), an.verify.integrity_ok && an.verify.matches_ledger_now ? "success" : "warning") : null,
    s ? h("div", { className: "card", id: "rep-snapshot", style: "margin-bottom:12px;" }, h("h3", {}, `Frozen figures: version ${r.version}`),
      h("p", { style: "color: var(--ink-500);" }, `Generated ${s.generated_at}. Fingerprint ${r.fingerprint}.`),
      h("div", { style: "display:flex; flex-wrap:wrap; gap:8px;" }, [["Assets", s.totals.assets], ["Liabilities", s.totals.liabilities], ["Revenue", s.totals.revenue], ["Expenses", s.totals.expenses], ["Net income", s.totals.net_income]].map(([k, v]) => tile(k, num(v)))),
      h("p", {}, `${s.data_status.ratios_calculated} of ${s.data_status.ratios_total} ratios calculated; ${s.variance.status === "OK" ? `${s.variance.material_count} material variance(s)` : "no earlier period to compare"}; ${s.scenarios.length} forecast scenario(s); ${s.evidence.length} evidence item(s) linked.`),
      s.evidence.length ? h("ul", { style: "padding-left:18px;" }, s.evidence.map((e) => h("li", {}, `${e.filename} (${e.status})`))) : null,
      h("h4", {}, "Limitations"), h("ul", { style: "padding-left:18px;" }, s.limitations.map((l) => h("li", {}, l)))) : note("Nothing is frozen yet. Submitting takes a snapshot of the figures at that moment.", "info"),
    h("div", { className: "card" }, h("h3", {}, "History"), h("ul", { style: "padding-left:18px;" }, r.history.map((x) => h("li", {}, `${x.at.slice(0, 16).replace("T", " ")} · ${x.action} · ${x.actor}${x.note ? ` · ${x.note}` : ""}`)))));
}

// ---------------------------------------------------------------- setup
function setup(an, role, a) {
  const c = an.config; if (!c) return null;
  const prep = canPrepare(role), f = an.thresholdForm;
  return h("div", { id: "an-setup" },
    note("Tell ASAVEXA what each account is. Ratios that need this stay marked 'Needs setup' until it is done; nothing is guessed.", "info"),
    h("div", { className: "card", style: "margin-bottom:12px;" }, h("h3", {}, "Account classification"),
      table([["Account"], ["Type"], ["Classification"]], c.accounts.filter((x) => x.type !== "EQUITY" && x.type !== "REVENUE").map((x) => h("tr", { "data-acct": x.code }, td(`${x.code} ${x.name}`), td(x.type.toLowerCase()),
        td(prep ? h("select", { id: `tag-${x.code}`, onChange: (e) => a.tagChange(x.id, e.target.value) }, [h("option", { value: "" }, "Not classified"), ...Object.keys(c.tag_choices[x.type] || {}).map((t) => h("option", { value: t, selected: (an.tagDraft[x.id] !== undefined ? an.tagDraft[x.id] : x.tag) === t }, TAG_TEXT[t] || t))]) : (x.tag ? TAG_TEXT[x.tag] || x.tag : "Not classified")))), "an-tag-table")),
    h("div", { className: "card", style: "margin-bottom:12px;" }, h("h3", {}, "When is a change worth a look?"),
      field("Percent change at or above", "th-pct", prep ? text("th-pct", f, "percent", a.thresholdChange) : h("span", {}, `${c.thresholds.percent}%`)), field("and amount change at or above", "th-amt", prep ? text("th-amt", f, "amount", a.thresholdChange) : h("span", {}, num(c.thresholds.amount)), "Use 0 to flag by percent alone.")),
    prep ? h("button", { className: "btn btn-primary", id: "cfg-save", disabled: an.busy, onClick: () => a.saveConfig() }, "Save setup") : h("p", { style: "color: var(--ink-500);" }, "You can view this setup. Changing it needs permission to prepare analysis."),
    h("p", { style: "color: var(--ink-500);" }, `Setup version ${c.version}${c.updated_by ? `, last changed by ${c.updated_by}` : ""}.`));
}
