import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState } from "../components/DataState.js";
import { TABS, CLASS_TEXT, KIND_TEXT, ATTENTION_TONE, canPrepare, canApprove, statusOf, words, who, canTrade, canClose, canDecideSell, ownWorkText } from "../lib/investments.js";

/**
 * Investments. A register of holdings built from the purchases, sales and prices people type in, at weighted-average cost. It reads no market data, gives no advice and posts nothing to a ledger.
 * A different person approves every sale.
 */
const Badge = ({ tone, label, id }) => h("span", { className: `badge badge-${tone || "neutral"}`, id }, label);
const St = (s) => Badge({ ...statusOf(s) });
const note = (t, kind = "info", id) => (t ? h("div", { className: `alert alert-${kind}`, id, style: "margin-bottom:12px;", role: kind === "error" ? "alert" : "status" }, t) : null);
const field = (l, id, inp, hint) => h("div", { className: "field" }, h("label", { for: id }, l), inp, hint ? h("small", { style: "color: var(--ink-500);" }, hint) : null);
const text = (im, a, form, k, id, ph) => h("input", { id, type: "text", value: (im.forms[form] || {})[k] == null ? "" : (im.forms[form] || {})[k], placeholder: ph || "", onInput: (e) => a.setForm(form, k, e.target.value) });
const sel = (im, a, form, k, id, opts) => h("select", { id, onChange: (e) => a.setForm(form, k, e.target.value, true) },
  opts.map(([v, l]) => h("option", { value: v, selected: String((im.forms[form] || {})[k]) === String(v) }, l)));
const btn = (l, id, onClick, kind = "secondary", disabled = false) => h("button", { className: `btn btn-${kind}`, id, disabled, onClick }, l);
const row = (...b) => h("div", { style: "display:flex; gap:8px; flex-wrap:wrap; margin:8px 0; align-items:end;" }, b.filter(Boolean));
const none = (t = "None.") => h("div", { style: "color: var(--ink-500);" }, t);
const card = (title, id, ...kids) => h("div", { className: "card", id, style: "margin-bottom:16px;" }, h("h3", {}, title), ...kids);
const hist = (items) => h("ul", {}, (items || []).map((x) => h("li", {}, `${String(x.at).slice(0, 10)} ${String(x.event).replace(/_/g, " ").toLowerCase()} by ${x.by}${x.note ? ": " + x.note : ""}`)));
const noteBox = (im, a, key, l, id) => field(l, id || `note-${key}`, h("textarea", { id: id || `note-${key}`, rows: 2, onInput: (e) => a.setNote(key, e.target.value) }, im.notes[key] || ""));
const formError = (im, name) => (im.formError && im.formError.form === name ? note(im.formError.text, "error", `${name}-problem`) : null);

export function Investments({ im, role, userId, loading, onRetry, actions: a }) {
  return h("div", {},
    h("h1", {}, "Investments"),
    note("This workspace is a register of holdings built from the purchases, sales and prices that people type in. It works out cost at a weighted average and the gain or loss from those figures. It reads no market data, gives no investment advice, holds no money and posts nothing to a ledger. A different person approves every sale.", "info", "im-banner"),
    im.error ? ErrorState({ message: im.error, onRetry }) : null,
    note(im.notice, "success", "im-notice"),
    loading ? LoadingState() : h("div", {},
      h("div", { className: "tabs", role: "tablist", style: "display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px;" },
        TABS.map(([id, l]) => h("button", { className: `btn ${im.tab === id ? "btn-primary" : "btn-secondary"}`, role: "tab", id: `im-tab-${id}`, "aria-selected": im.tab === id ? "true" : "false", onClick: () => a.setTab(id) }, l))),
      im.busy ? h("div", { style: "color: var(--ink-500);" }, "Working...") : null,
      im.tab === "overview" ? overview(im, role, a) : holdings(im, role, userId, a)));
}

function overview(im, role, a) {
  const o = im.ov; if (!o) return none("Nothing loaded yet.");
  const c = o.counts;
  return h("div", {},
    card("What needs attention", "im-attention", o.attention.length ? h("ul", {}, o.attention.map((x) => h("li", { "data-kind": x.kind }, Badge({ tone: ATTENTION_TONE[x.kind] || "info", label: words(x.kind) }), " ", `${x.count} ${x.text}`))) : none("Nothing needs attention.")),
    card("Totals per currency", "im-totals", o.totals.length ? h("ul", {}, o.totals.map((t) => h("li", { "data-currency": t.currency },
      `${t.currency}: ${t.holdings} active holding(s), cost ${t.cost}; ${t.valued} with a price worth ${t.market_value} (gain or loss so far ${t.unrealised}); ${t.unvalued} without a price; gain or loss already realised ${t.realised}`))) : none("No holdings yet."),
      h("p", { style: "color: var(--ink-500);" }, "Currencies are never added together. Holdings without a price are left out of market value and unrealised gain.")),
    card("Counts", "im-counts", h("ul", {}, [["Active holdings", c.active], ["Closed", c.closed], ["Without a price", c.no_price], ["With an old price", c.stale]].map(([l, n]) => h("li", {}, `${l}: ${n}`)))),
    policyCard(im, role, a),
    card("What this does not do", "im-limits", h("ul", {}, o.limitations.map((x) => h("li", {}, x)))));
}

function policyCard(im, role, a) {
  const p = im.ov.policy, f = im.forms.policy;
  return card("Settings", "im-policy", h("p", { id: "im-policy-meaning" }, p.meaning),
    canApprove(role) && f ? h("div", {}, row(field("Days before a price is out of date", "im-policy-days", text(im, a, "policy", "stale_days", "im-policy-days"))),
      formError(im, "policy"), btn("Save settings", "im-policy-save", () => a.savePolicy(), "primary", im.busy)) : h("p", { style: "color: var(--ink-500);" }, "Only an approver can change this setting."));
}

function holdings(im, role, me, a) {
  const sel_ = im.sel.holding;
  return h("div", {},
    card("Holdings", "im-holdings", im.holdings.length ? im.holdings.map((x) => h("div", { className: "card", style: "margin-bottom:8px;", "data-holding": x.ref },
      h("div", {}, h("strong", {}, `${x.ref} · ${x.name}${x.identifier ? " · " + x.identifier : ""}`), " ", St(x.status), x.no_mark ? [" ", Badge({ tone: "warn", label: "No price" })] : null,
        x.mark_stale ? [" ", Badge({ tone: "warn", label: "Old price" })] : null, x.pending_sells ? [" ", Badge({ tone: "info", label: `${x.pending_sells} sale(s) waiting` })] : null),
      h("div", { style: "color: var(--ink-500);" }, `${CLASS_TEXT[x.asset_class] || x.asset_class} · ${x.account}`),
      h("div", {}, `Units ${x.units}; cost ${x.currency} ${x.cost_basis}; average cost ${x.average_cost}`),
      x.latest_mark ? h("div", {}, `Price ${x.latest_mark.price} on ${x.latest_mark.as_of} (${x.latest_mark.source}). Market value ${x.currency} ${x.market_value}; gain or loss so far ${x.unrealised}`) : null,
      h("div", {}, `Gain or loss already realised: ${x.currency} ${x.realised_total}`),
      btn(sel_ && sel_.id === x.id ? "Hide details" : "Details", `im-hd-open-${x.ref}`, () => a.selectHolding(sel_ && sel_.id === x.id ? null : x.id), "secondary", im.busy))) : none("No holdings yet.")),
    sel_ ? detail(im, role, me, a, sel_) : null,
    canPrepare(role) ? card("Add a holding", "im-holding-card",
      row(field("Name", "im-hd-name", text(im, a, "holding", "name", "im-hd-name")), field("Identifier (optional)", "im-hd-ident", text(im, a, "holding", "identifier", "im-hd-ident", "DANGCEM")), field("Asset class", "im-hd-class", sel(im, a, "holding", "asset_class", "im-hd-class", Object.entries(CLASS_TEXT)))),
      row(field("Currency", "im-hd-cur", text(im, a, "holding", "currency", "im-hd-cur", "NGN")), field("Account or custodian", "im-hd-acct", text(im, a, "holding", "account", "im-hd-acct"))),
      formError(im, "holding"), btn("Add holding", "im-hd-save", () => a.addHolding(), "primary", im.busy)) : null);
}

function tradeForm(im, a, form, prefix, title, saveLabel, onSave, withNote) {
  return h("div", {}, h("h4", {}, title),
    row(field("Units", `${prefix}-units`, text(im, a, form, "units", `${prefix}-units`)), field("Price per unit", `${prefix}-price`, text(im, a, form, "price", `${prefix}-price`)), field("Fee (optional)", `${prefix}-fee`, text(im, a, form, "fee", `${prefix}-fee`)),
      field("Trade date", `${prefix}-date`, text(im, a, form, "traded_on", `${prefix}-date`, "YYYY-MM-DD")), field("Reference", `${prefix}-ref`, text(im, a, form, "reference", `${prefix}-ref`))),
    formError(im, form), btn(saveLabel, `${prefix}-save`, onSave, "primary", im.busy));
}

function detail(im, role, me, a, x) {
  const trade = canTrade(x, role);
  return card(`${x.ref} · ${x.name}`, "im-holding-detail",
    h("div", { id: "im-holding-figures" }, `Units ${x.units}; cost ${x.currency} ${x.cost_basis}; average cost ${x.average_cost}`),
    h("div", { id: "im-trades" }, h("h4", {}, "Trades"), x.trades.length ? x.trades.map((t) => h("div", { "data-trade": String(t.no) },
      `#${t.no} ${KIND_TEXT[t.kind] || t.kind}: ${t.units} at ${t.price}, fee ${t.fee}, dated ${t.traded_on}, ref ${t.reference}. `, t.kind === "SELL" ? St(t.status) : null,
      t.kind === "BUY" ? ` Cost added ${t.amount}.` : "", t.realised != null ? ` Proceeds ${t.proceeds}, cost removed ${t.cost_removed}, gain or loss ${t.realised}.` : "", t.units_after != null ? ` After: ${t.units_after} units, cost ${t.basis_after}.` : "",
      t.decision_note ? ` Decision note: ${t.decision_note}` : "",
      canDecideSell(t, role, me) ? h("div", {}, noteBox(im, a, `sell-${x.id}-${t.no}`, "Note (approval: optional, at least 10 characters if given; rejection: required)", `im-tr-${t.no}-note`),
        btn("Approve sale", `im-tr-${t.no}-approve`, () => a.approveSell(x.id, t.no), "primary", im.busy), " ", btn("Reject sale", `im-tr-${t.no}-reject`, () => a.rejectSell(x.id, t.no), "secondary", im.busy)) :
        (t.kind === "SELL" && t.status === "PENDING" && canApprove(role) ? h("div", { style: "color: var(--ink-500);" }, ownWorkText("proposed this sale")) : null))) : none("No trades yet.")),
    h("div", { id: "im-marks" }, h("h4", {}, "Prices"), x.marks.length ? h("ul", {}, x.marks.map((m) => h("li", { "data-mark": String(m.no) }, `${m.as_of}: ${m.price} (${m.source}, by ${who(m.by, me)})`))) : none("No prices yet.")),
    trade ? tradeForm(im, a, "buy", "im-by", "Record a purchase", "Record purchase", () => a.buy(x.id)) : null,
    trade ? tradeForm(im, a, "sell", "im-sl", "Propose a sale", "Propose sale", () => a.proposeSell(x.id, x.units)) : null,
    trade ? h("div", {}, h("h4", {}, "Record a price"), row(field("Price per unit", "im-mk-price", text(im, a, "mark", "price", "im-mk-price")), field("Price date", "im-mk-date", text(im, a, "mark", "as_of", "im-mk-date", "YYYY-MM-DD")), field("Source", "im-mk-source", text(im, a, "mark", "source", "im-mk-source", "Broker statement"))),
      formError(im, "mark"), btn("Record price", "im-mk-save", () => a.recordMark(x.id), "primary", im.busy)) : null,
    canClose(x, role) ? h("div", {}, h("h4", {}, "Close this holding"), noteBox(im, a, `close-${x.id}`, "Reason (required, at least 10 characters)", "im-close-note"), btn("Close holding", "im-close-save", () => a.close(x.id), "secondary", im.busy)) : null,
    h("div", {}, h("h4", {}, "History"), hist(x.history)));
}
