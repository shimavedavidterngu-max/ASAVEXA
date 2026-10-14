import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState } from "../components/DataState.js";
import { TABS, WEEK_CHOICES, ATTENTION_TONE, FLAG_TEXT, MOVE_TEXT, COMPARATOR_TEXT, UNIT_TEXT, canPrepare, canApprove, statusOf, words, fmt, paymentMoves, approvalText, canConfirmBalance, canAcknowledge, ackText, headroomText, openFirst } from "../lib/treasury.js";

/**
 * Treasury and Cash. It records and checks; it never moves money and is not connected to any bank.
 * A balance is confirmed, a payment approved and a covenant breach acknowledged by someone other than the person who recorded or asked for it, and the page says so.
 */
const Badge = ({ tone, label, id }) => h("span", { className: `badge badge-${tone || "neutral"}`, id }, label);
const St = (s, id) => Badge({ ...statusOf(s), id });
const note = (t, kind = "info", id) => (t ? h("div", { className: `alert alert-${kind}`, id, style: "margin-bottom:12px;", role: kind === "error" ? "alert" : "status" }, t) : null);
const field = (l, id, inp, hint) => h("div", { className: "field" }, h("label", { for: id }, l), inp, hint ? h("small", { style: "color: var(--ink-500);" }, hint) : null);
const text = (tr, a, form, k, id, ph, type = "text") => h("input", { id, type, value: (tr.forms[form] || {})[k] == null ? "" : (tr.forms[form] || {})[k], placeholder: ph || "", onInput: (e) => a.setForm(form, k, e.target.value) });
const sel = (tr, a, form, k, id, opts, blank) => h("select", { id, onChange: (e) => a.setForm(form, k, e.target.value, true) },
  [...(blank ? [h("option", { value: "" }, blank)] : []), ...opts.map(([v, l]) => h("option", { value: v, selected: String((tr.forms[form] || {})[k]) === String(v) }, l))]);
const table = (head, rows, id) => h("div", { className: "table-scroll" }, h("table", { className: "data-table", id }, h("thead", {}, h("tr", {}, head.map(([l, right]) => h("th", { style: right ? "text-align:right;" : undefined }, l)))), h("tbody", {}, rows)));
const td = (v, right) => h("td", { style: right ? "text-align:right;" : undefined }, v);
const btn = (l, id, onClick, kind = "secondary", disabled = false) => h("button", { className: `btn btn-${kind}`, id, disabled, onClick }, l);
const row = (...b) => h("div", { style: "display:flex; gap:8px; flex-wrap:wrap; margin:8px 0; align-items:end;" }, b.filter(Boolean));
const none = (t = "None.") => h("div", { style: "color: var(--ink-500);" }, t);
const card = (title, id, ...kids) => h("div", { className: "card", id, style: "margin-bottom:16px;" }, h("h3", {}, title), ...kids);
const hist = (items, id) => h("ul", { id }, (items || []).map((x) => h("li", {}, `${String(x.at).slice(0, 10)} ${String(x.event).replace(/_/g, " ").toLowerCase()} by ${x.by}${x.note ? ": " + x.note : ""}`)));
const noteBox = (tr, a, key, l) => field(l, `note-${key}`, h("textarea", { id: `note-${key}`, rows: 2, onInput: (e) => a.setNote(key, e.target.value) }, tr.notes[key] || ""));
const formError = (tr, name) => (tr.formError && tr.formError.form === name ? note(tr.formError.text, "error", `${name}-problem`) : null);

export function Treasury({ tr, role, userId, loading, onRetry, actions: a }) {
  return h("div", {},
    h("h1", {}, "Treasury and Cash"),
    note("This workspace records and checks. It never moves money and is not connected to any bank, so it is only as complete and as current as what people type in. Balances, payments and covenant breaches are confirmed, approved or acknowledged by a second person.", "warning", "tr-banner"),
    tr.error ? ErrorState({ message: tr.error, onRetry }) : null,
    note(tr.notice, "success", "tr-notice"),
    loading ? LoadingState() : h("div", {},
      h("div", { className: "tabs", role: "tablist", style: "display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px;" },
        TABS.map(([id, l]) => h("button", { className: `btn ${tr.tab === id ? "btn-primary" : "btn-secondary"}`, role: "tab", id: `tr-tab-${id}`, "aria-selected": tr.tab === id ? "true" : "false", onClick: () => a.setTab(id) }, l))),
      tr.busy ? h("div", { style: "color: var(--ink-500);" }, "Working...") : null,
      tr.tab === "overview" ? overview(tr, role, a) : tr.tab === "accounts" ? accounts(tr, role, userId, a) : tr.tab === "forecast" ? forecast(tr, role, a)
        : tr.tab === "payments" ? payments(tr, role, userId, a) : covenants(tr, role, userId, a)));
}

// ---------------------------------------------------------------- overview
function overview(tr, role, a) {
  const o = tr.ov; if (!o) return none("Nothing loaded yet.");
  return h("div", {},
    card("What needs attention", "tr-attention", o.attention.length ? h("ul", {}, o.attention.map((x) => h("li", { "data-kind": x.kind }, Badge({ tone: ATTENTION_TONE[x.kind] || "info", label: words(x.kind) }), " ", x.text))) : none("Nothing needs attention right now.")),
    card("Cash position", "tr-position", o.position.length ? o.position.map((g) => h("div", { "data-currency": g.currency, style: "margin-bottom:12px;" },
      h("div", { style: "font-size:1.4em;" }, fmt(g.total, g.currency)),
      h("div", { style: "color: var(--ink-500);" }, `${g.accounts.length} account${g.accounts.length === 1 ? "" : "s"}${g.accounts_without_balance ? `, ${g.accounts_without_balance} with no balance` : ""}${g.stale ? `, ${g.stale} out of date` : ""}${g.unconfirmed ? `, ${g.unconfirmed} not confirmed` : ""}`)))
      : none("No cash accounts are open yet."), h("p", { style: "color: var(--ink-500);" }, "Each currency is shown on its own. Nothing is converted or added across currencies.")),
    card("Counts", "tr-counts", h("ul", {}, [["Open accounts", o.counts.accounts], ["Expected cash flows", o.counts.open_flows], ["Payments waiting for approval", o.counts.payments_waiting], ["Approved payments waiting to be released", o.counts.payments_ready],
      ["Payments released", o.counts.payments_released], ["Active covenants", o.counts.covenants], ["Covenants in breach", o.counts.covenants_breached]].map(([l, n]) => h("li", {}, `${l}: ${n}`)))),
    policyCard(tr, role, a),
    card("What this does not do", "tr-limits", h("ul", {}, o.limitations.map((x) => h("li", {}, x)))));
}

function policyCard(tr, role, a) {
  const p = tr.ov.policy, f = tr.forms.policy;
  return card("Policy settings", "tr-policy", h("p", { id: "tr-policy-meaning" }, p.meaning),
    canApprove(role) && f ? h("div", {},
      field("Minimum cash per currency", "tr-policy-min", text(tr, a, "policy", "minimum_cash", "tr-policy-min", "NGN=500000, USD=1000"), "Weeks that end below this are flagged. Leave empty to use zero."),
      field("Two-approver limit per currency", "tr-policy-limit", text(tr, a, "policy", "dual_limits", "tr-policy-limit", "DEFAULT=10000, USD=5000"), "A payment at or above this needs two different approvers."),
      field("Balance counts as out of date after (days)", "tr-policy-stale", text(tr, a, "policy", "stale_days", "tr-policy-stale")),
      formError(tr, "policy"), btn("Save policy", "tr-policy-save", () => a.savePolicy(), "primary", tr.busy)) : h("p", { style: "color: var(--ink-500);" }, "Only an approver can change these settings."));
}

// ---------------------------------------------------------------- accounts
function accounts(tr, role, me, a) {
  const sel1 = tr.acct;
  return h("div", {},
    card("Cash accounts", "tr-accounts", tr.accounts.length ? table([["Ref"], ["Account"], ["Currency"], ["Latest balance", true], ["As at"], ["Status"], [""]], tr.accounts.map((c) => h("tr", { "data-account": c.id },
      td(c.ref), td(c.name + (c.last4 ? ` (…${c.last4})` : "")), td(c.currency), td(c.latest_balance ? fmt(c.latest_balance.amount) : "—", true), td(c.latest_balance ? c.latest_balance.as_at : "—"),
      td([St(c.status), c.status === "ACTIVE" && c.latest_balance ? [" ", St(c.latest_balance.status)] : null, c.stale ? [" ", Badge({ tone: "warn", label: c.latest_balance ? "Out of date" : "No balance" })] : null]),
      td(btn("Open", `tr-acct-open-${c.ref}`, () => a.selectAccount(c.id)))))) : none("No cash accounts yet."),
    ),
    sel1 ? accountDetail(tr, role, me, a, sel1) : null,
    canPrepare(role) ? card("Open a cash account", "tr-acct-card", h("p", { style: "color: var(--ink-500);" }, "Give at most the last four characters of the account number, never the whole number."),
      row(field("Name", "tr-acct-name", text(tr, a, "account", "name", "tr-acct-name", "Main current account")), field("Bank", "tr-acct-bank", text(tr, a, "account", "bank_name", "tr-acct-bank")),
        field("Currency", "tr-acct-cur", text(tr, a, "account", "currency", "tr-acct-cur", "NGN")), field("Last four", "tr-acct-last4", text(tr, a, "account", "last4", "tr-acct-last4"))),
      field("What it is used for", "tr-acct-purpose", text(tr, a, "account", "purpose", "tr-acct-purpose")), formError(tr, "account"), btn("Open account", "tr-acct-save", () => a.openAccount(), "primary", tr.busy)) : null);
}

function accountDetail(tr, role, me, a, c) {
  return card(`${c.ref} ${c.name}`, "tr-acct-detail",
    h("p", {}, `${c.bank_name || "No bank named"} · ${c.currency} · ${c.purpose || "no purpose given"}`),
    h("h4", {}, "Balances"), c.balances.length ? table([["As at"], ["Balance", true], ["Source"], ["Status"], ["Recorded by"], [""]], c.balances.map((b) => h("tr", { "data-balance": b.id },
      td(b.as_at), td(fmt(b.amount, c.currency), true), td(b.source), td(St(b.status)), td(b.recorded_by + (b.confirmed_by ? `, confirmed by ${b.confirmed_by}` : "")),
      td(canConfirmBalance(b, me, role) ? btn("Confirm", `tr-bal-confirm-${b.id}`, () => a.confirmBalance(c.id, b.id), "secondary", tr.busy) : (b.status === "RECORDED" ? h("small", { className: "tr-waiting" }, "Waiting for a different approver to confirm") : null))))) : none("No balance has been recorded."),
    c.status === "ACTIVE" && canPrepare(role) ? h("div", {}, h("h4", {}, "Record a balance"),
      row(field("As at", "tr-bal-date", text(tr, a, "balance", "as_at", "tr-bal-date", "YYYY-MM-DD")), field("Balance", "tr-bal-amount", text(tr, a, "balance", "amount", "tr-bal-amount", "0.00")), field("Where it came from", "tr-bal-source", text(tr, a, "balance", "source", "tr-bal-source", "Bank statement"))),
      formError(tr, "balance"), btn("Record balance", "tr-bal-save", () => a.recordBalance(c.id), "primary", tr.busy),
      h("h4", {}, "Close this account"), noteBox(tr, a, "close-account", "Reason"), btn("Close account", "tr-acct-close", () => a.closeAccount(c.id), "secondary", tr.busy)) : null,
    h("h4", {}, "History"), hist(c.history, "tr-acct-history"), btn("Close this panel", "tr-acct-hide", () => a.selectAccount(null)));
}

// ---------------------------------------------------------------- forecast and flows
function forecast(tr, role, a) {
  const f = tr.forecast;
  return h("div", {},
    card("Weekly cash forecast", "tr-forecast",
      h("p", { style: "color: var(--ink-500);" }, "Arithmetic over the latest balances, the open expected cash flows and the approved payments. It is not a prediction."),
      row(field("Weeks", "tr-weeks", h("select", { id: "tr-weeks", onChange: (e) => a.setWeeks(Number(e.target.value)) }, WEEK_CHOICES.map((w) => h("option", { value: w, selected: w === tr.weeks }, `${w} weeks`)))),
        h("label", {}, h("input", { type: "checkbox", id: "tr-possible", checked: tr.possible, onChange: (e) => a.setPossible(e.target.checked) }), " Include cash flows marked only possible"),
        btn("Show forecast", "tr-forecast-go", () => a.runForecast(), "primary", tr.busy)),
      f ? (f.currencies.length ? f.currencies.map((c) => forecastTable(c)) : none("Nothing to forecast yet. Open an account and record a balance.")) : none("Press Show forecast.")),
    accuracyCard(tr),
    flowsCard(tr, role, a));
}

function forecastTable(c) {
  return h("div", { "data-currency": c.currency, style: "margin-bottom:16px;" },
    h("h4", {}, `${c.currency}: opening ${fmt(c.opening)}, lowest ${fmt(c.lowest_closing)} in week ${c.lowest_week}`),
    h("p", { style: "color: var(--ink-500);" }, `Compared with ${c.floor_basis}${c.floor ? ` (${fmt(c.floor)})` : ""}. ${c.shortfall_weeks} week${c.shortfall_weeks === 1 ? "" : "s"} below.`),
    c.warnings.length ? h("ul", { className: "tr-warnings" }, c.warnings.map((w) => h("li", {}, w))) : null,
    table([["Week"], ["From"], ["To"], ["In", true], ["Out", true], ["Closing", true], [""]], c.weeks.map((w) => h("tr", { "data-week": w.week, className: w.below_floor ? "tr-below" : undefined },
      td(String(w.week)), td(w.start), td(w.end), td(fmt(w.inflow), true), td(fmt(w.outflow), true), td(fmt(w.closing), true), td(w.below_floor ? Badge({ tone: "fail", label: "Below" }) : null)))));
}

function accuracyCard(tr) {
  const x = tr.accuracy;
  return card("How well past expectations held", "tr-accuracy", x && x.currencies.length ? table([["Currency"], ["Items"], ["On time"], ["Expected", true], ["Actual", true], ["Difference", true], ["Average days late"]],
    x.currencies.map((c) => h("tr", {}, td(c.currency), td(String(c.count)), td(String(c.on_time)), td(fmt(c.forecast_total), true), td(fmt(c.actual_total), true), td(fmt(c.difference), true), td(String(c.average_days_late))))) : none("No expected cash flow has been marked as happened yet."),
    h("p", { style: "color: var(--ink-500);" }, "This compares what people expected with what they recorded as having happened."));
}

function flowsCard(tr, role, a) {
  const accs = tr.options ? tr.options.accounts : [], cats = tr.options ? tr.options.flow_categories : [];
  return card("Expected cash flows", "tr-flows", tr.flows.length ? table([["Ref"], ["Date"], ["Direction"], ["Amount", true], ["Description"], ["How sure"], ["Status"], [""]], openFirst(tr.flows).map((f) => h("tr", { "data-flow": f.id },
    td(f.ref), td(f.flow_date), td(f.direction === "IN" ? "In" : "Out"), td(fmt(f.amount, f.currency), true), td(f.description), td(words(f.certainty)),
    td([St(f.status), f.overdue ? [" ", Badge({ tone: "warn", label: "Past its date" })] : null, f.status === "REALISED" ? ` ${fmt(f.actual_amount)} on ${f.actual_date}` : null]),
    td(f.status === "OPEN" && canPrepare(role) ? [btn("Happened", `tr-flow-happened-${f.ref}`, () => a.realiseFlow(f.id), "secondary", tr.busy), " ", btn("Cancel", `tr-flow-cancel-${f.ref}`, () => a.cancelFlow(f.id), "secondary", tr.busy)] : null)))) : none("No expected cash flows yet."),
    tr.flows.some((f) => f.status === "OPEN") && canPrepare(role) ? h("div", {}, noteBox(tr, a, "flow-note", "Reason for cancelling, or the amount and date when marking one as happened is entered below"),
      row(field("Actual amount", "tr-flow-actual", text(tr, a, "realise", "actual_amount", "tr-flow-actual", "0.00")), field("Actual date", "tr-flow-actual-date", text(tr, a, "realise", "actual_date", "tr-flow-actual-date", "YYYY-MM-DD"))), formError(tr, "realise")) : null,
    canPrepare(role) ? h("div", {}, h("h4", {}, "Add an expected cash flow"),
      row(field("Direction", "tr-flow-dir", sel(tr, a, "flow", "direction", "tr-flow-dir", [["IN", "Money in"], ["OUT", "Money out"]])), field("Expected date", "tr-flow-date", text(tr, a, "flow", "flow_date", "tr-flow-date", "YYYY-MM-DD")),
        field("Amount", "tr-flow-amount", text(tr, a, "flow", "amount", "tr-flow-amount", "0.00")),
        field("Account", "tr-flow-account", sel(tr, a, "flow", "account_id", "tr-flow-account", accs.map((x) => [x.id, `${x.ref} ${x.name} (${x.currency})`]), "No account (give a currency)")),
        field("Currency", "tr-flow-cur", text(tr, a, "flow", "currency", "tr-flow-cur", "NGN"), "Only needed when no account is chosen.")),
      row(field("Kind", "tr-flow-cat", sel(tr, a, "flow", "category", "tr-flow-cat", cats.map((x) => [x, words(x)]))), field("How sure", "tr-flow-cert", sel(tr, a, "flow", "certainty", "tr-flow-cert", (tr.options ? tr.options.certainties : []).map((x) => [x, words(x)]))),
        field("Description", "tr-flow-desc", text(tr, a, "flow", "description", "tr-flow-desc", "What is expected"))),
      formError(tr, "flow"), btn("Add cash flow", "tr-flow-save", () => a.addFlow(), "primary", tr.busy)) : null);
}

// ---------------------------------------------------------------- payments
function payments(tr, role, me, a) {
  const accs = tr.options ? tr.options.accounts : [];
  return h("div", {},
    card("Payment requests", "tr-payments",
      row(field("Show", "tr-pay-filter", h("select", { id: "tr-pay-filter", onChange: (e) => a.filterPayments(e.target.value) }, [["", "All"], ["REQUESTED", "Waiting for approval"], ["APPROVED", "Approved"], ["RELEASED", "Released"], ["REJECTED", "Rejected"], ["CANCELLED", "Cancelled"]]
        .map(([v, l]) => h("option", { value: v, selected: tr.payFilter === v }, l))))),
      tr.payments.length ? tr.payments.map((p) => paymentRow(tr, role, me, a, p)) : none("No payment requests.")),
    canPrepare(role) ? card("Ask for a payment", "tr-pay-card",
      h("p", { style: "color: var(--ink-500);" }, "You cannot approve your own request. Payee, amount and account cannot be changed afterwards: cancel and ask again instead."),
      row(field("Pay from", "tr-pay-account", sel(tr, a, "payment", "account_id", "tr-pay-account", accs.map((x) => [x.id, `${x.ref} ${x.name} (${x.currency})`]), "Choose an account")), field("Payee", "tr-pay-payee", text(tr, a, "payment", "payee", "tr-pay-payee")),
        field("Amount", "tr-pay-amount", text(tr, a, "payment", "amount", "tr-pay-amount", "0.00")), field("Due date", "tr-pay-due", text(tr, a, "payment", "due_date", "tr-pay-due", "YYYY-MM-DD"))),
      row(field("Invoice or reference", "tr-pay-invoice", text(tr, a, "payment", "invoice_ref", "tr-pay-invoice")), field("Why", "tr-pay-reason", text(tr, a, "payment", "reason", "tr-pay-reason")),
        field("Expected cash flow it settles", "tr-pay-flow", sel(tr, a, "payment", "flow_id", "tr-pay-flow", (tr.options ? tr.options.open_payment_flows : []).map((x) => [x.id, `${x.ref} ${x.description} ${x.amount} ${x.currency}`]), "None")),
        field("Supporting document", "tr-pay-evidence", sel(tr, a, "payment", "evidence_id", "tr-pay-evidence", (tr.vault || []).map((e) => [e.id, e.original_filename || e.filename || e.id]), "None attached"))),
      formError(tr, "payment"), btn("Ask for payment", "tr-pay-save", () => a.requestPayment(), "primary", tr.busy)) : null);
}

function paymentRow(tr, role, me, a, p) {
  const moves = paymentMoves(p, me, role);
  return h("div", { className: "card", "data-payment": p.id, style: "margin-bottom:10px;" },
    h("div", {}, h("strong", {}, `${p.ref} · ${p.payee} · ${fmt(p.amount, p.currency)}`), " ", St(p.status), p.overdue ? [" ", Badge({ tone: "warn", label: "Past its due date" })] : null),
    h("div", { style: "color: var(--ink-500);" }, `From ${p.account_name} · due ${p.due_date} · asked by ${p.requested_by}${p.invoice_ref ? ` · invoice ${p.invoice_ref}` : ""} · ${p.reason}`),
    p.flags.length ? h("ul", { className: "tr-flags" }, p.flags.map((f) => h("li", { "data-flag": f }, Badge({ tone: "warn", label: words(f) }), " ", FLAG_TEXT[f] || f))) : null,
    approvalText(p) ? h("div", {}, approvalText(p)) : null,
    p.status === "RELEASED" ? h("div", {}, `Released on ${p.released_date} by ${p.released_by}. Bank reference ${p.bank_reference}.`) : null,
    moves.length ? h("div", { style: "margin-top:6px;" }, noteBox(tr, a, `pay-${p.id}`, p.flags.length ? "Note (required because of the warnings above)" : "Note"),
      moves.includes("release") ? row(field("Date released", `tr-rel-date-${p.ref}`, h("input", { id: `tr-rel-date-${p.ref}`, type: "text", placeholder: "YYYY-MM-DD", onInput: (e) => a.setNote(`reldate-${p.id}`, e.target.value) })),
        field("Bank's reference", `tr-rel-ref-${p.ref}`, h("input", { id: `tr-rel-ref-${p.ref}`, type: "text", onInput: (e) => a.setNote(`relref-${p.id}`, e.target.value) }))) : null,
      row(moves.map((m) => btn(MOVE_TEXT[m], `tr-pay-${m}-${p.ref}`, () => a.payStep(p.id, m), m === "approve" ? "primary" : "secondary", tr.busy)))) : null,
    h("details", {}, h("summary", {}, "History"), hist(p.history)));
}

// ---------------------------------------------------------------- covenants
function covenants(tr, role, me, a) {
  return h("div", {},
    card("Covenants", "tr-covenants", tr.covenants.length ? tr.covenants.map((c) => covenantRow(tr, role, me, a, c)) : none("No covenants recorded.")),
    canPrepare(role) ? card("Add a covenant", "tr-cov-card",
      h("p", { style: "color: var(--ink-500);" }, "Type in the threshold from your loan agreement. ASAVEXA has not read the agreement and only compares measured values with the number you enter."),
      row(field("Name", "tr-cov-name", text(tr, a, "covenant", "name", "tr-cov-name", "Debt service cover")), field("Lender", "tr-cov-lender", text(tr, a, "covenant", "lender", "tr-cov-lender")),
        field("What it measures", "tr-cov-desc", text(tr, a, "covenant", "description", "tr-cov-desc"))),
      row(field("Rule", "tr-cov-cmp", sel(tr, a, "covenant", "comparator", "tr-cov-cmp", Object.entries(COMPARATOR_TEXT))), field("Threshold", "tr-cov-thr", text(tr, a, "covenant", "threshold", "tr-cov-thr", "1.25")),
        field("Unit", "tr-cov-unit", sel(tr, a, "covenant", "unit", "tr-cov-unit", Object.entries(UNIT_TEXT))),
        (tr.forms.covenant || {}).unit === "AMOUNT" ? field("Currency", "tr-cov-cur", text(tr, a, "covenant", "currency", "tr-cov-cur", "NGN")) : null),
      row(field("Tested", "tr-cov-freq", sel(tr, a, "covenant", "frequency", "tr-cov-freq", (tr.options ? tr.options.frequencies : []).map((x) => [x, words(x)]))),
        field("Warn within (%)", "tr-cov-watch", text(tr, a, "covenant", "watch_pct", "tr-cov-watch")), field("Starts", "tr-cov-from", text(tr, a, "covenant", "effective_from", "tr-cov-from", "YYYY-MM-DD"))),
      formError(tr, "covenant"), btn("Add covenant", "tr-cov-save", () => a.addCovenant(), "primary", tr.busy)) : null);
}

function covenantRow(tr, role, me, a, c) {
  const rf = tr.forms[`result-${c.id}`];
  return h("div", { className: "card", "data-covenant": c.id, style: "margin-bottom:10px;" },
    h("div", {}, h("strong", {}, `${c.ref} · ${c.name}`), " ", St(c.latest_status), c.status === "RETIRED" ? [" ", St("RETIRED")] : null, c.unacknowledged_breach ? [" ", Badge({ tone: "fail", label: "Breach not acknowledged" })] : null, c.test_overdue ? [" ", Badge({ tone: "warn", label: "Test overdue" })] : null),
    h("div", { style: "color: var(--ink-500);" }, `${c.lender ? c.lender + " · " : ""}${c.meaning} Tested ${words(c.frequency).toLowerCase()}. Next period ends ${c.next_period_end}; result due by ${c.next_due}.`),
    c.results.length ? table([["Period end"], ["Value", true], ["Result"], ["Room"], ["Recorded by"], [""]], c.results.map((r) => h("tr", { "data-result": r.id },
      td(r.period_end), td(r.value, true), td(St(r.status)), td(headroomText(r)), td(r.recorded_by + (r.note ? `: ${r.note}` : "")),
      td(r.status === "BREACHED" ? (r.acknowledged_by ? ackText(r) : (canAcknowledge(r, me, role) ? ackBox(tr, a, c, r) : "Waiting for a second person to acknowledge")) : null)))) : none("No result recorded yet."),
    c.status === "ACTIVE" && canPrepare(role) ? h("div", {}, h("h4", {}, "Record a result"),
      row(field("Period end", `tr-res-date-${c.ref}`, h("input", { id: `tr-res-date-${c.ref}`, type: "text", placeholder: "YYYY-MM-DD", value: rf ? rf.period_end : "", onInput: (e) => a.setForm(`result-${c.id}`, "period_end", e.target.value) })),
        field("Measured value", `tr-res-value-${c.ref}`, h("input", { id: `tr-res-value-${c.ref}`, type: "text", value: rf ? rf.value : "", onInput: (e) => a.setForm(`result-${c.id}`, "value", e.target.value) })),
        field("Source", `tr-res-source-${c.ref}`, h("input", { id: `tr-res-source-${c.ref}`, type: "text", value: rf ? rf.source : "", onInput: (e) => a.setForm(`result-${c.id}`, "source", e.target.value) }))),
      field("Explanation (required if it is a breach)", `tr-res-note-${c.ref}`, h("textarea", { id: `tr-res-note-${c.ref}`, rows: 2, onInput: (e) => a.setForm(`result-${c.id}`, "note", e.target.value) }, rf ? rf.note : "")),
      formError(tr, `result-${c.id}`), row(btn("Record result", `tr-res-save-${c.ref}`, () => a.addResult(c.id), "primary", tr.busy), btn("Retire covenant", `tr-cov-retire-${c.ref}`, () => a.retireCovenant(c.id), "secondary", tr.busy)),
      noteBox(tr, a, `retire-${c.id}`, "Reason for retiring")) : null,
    h("details", {}, h("summary", {}, "History"), hist(c.history)));
}

function ackBox(tr, a, c, r) {
  const k = `ack-${r.id}`;
  return h("div", {}, noteBox(tr, a, k, "What happens next"),
    h("label", {}, h("input", { type: "checkbox", id: `tr-ack-waiver-${r.id}`, onChange: (e) => a.setNote(`${k}-waiver`, e.target.checked) }), " A written waiver or amendment was obtained from the lender"),
    btn("Acknowledge breach", `tr-ack-${r.id}`, () => a.acknowledge(c.id, r.id), "secondary", tr.busy));
}
