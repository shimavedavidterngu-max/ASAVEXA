import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState } from "../components/DataState.js";
import { TABS, REASON_TEXT, DIRECTION_TEXT, KIND_TEXT, ATTENTION_TONE, canPrepare, canApprove, statusOf, words, who,
  canMove, canDiscontinue, canDecideAdjustment, isAdjustment, ownWorkText } from "../lib/inventory.js";

/**
 * Inventory. A stock register built from the receipts and issues people type in, valued at a weighted average cost. It posts nothing to a ledger.
 * A different person approves every stock adjustment.
 */
const Badge = ({ tone, label, id }) => h("span", { className: `badge badge-${tone || "neutral"}`, id }, label);
const St = (s) => Badge({ ...statusOf(s) });
const note = (t, kind = "info", id) => (t ? h("div", { className: `alert alert-${kind}`, id, style: "margin-bottom:12px;", role: kind === "error" ? "alert" : "status" }, t) : null);
const field = (l, id, inp, hint) => h("div", { className: "field" }, h("label", { for: id }, l), inp, hint ? h("small", { style: "color: var(--ink-500);" }, hint) : null);
const text = (iv, a, form, k, id, ph) => h("input", { id, type: "text", value: (iv.forms[form] || {})[k] == null ? "" : (iv.forms[form] || {})[k], placeholder: ph || "", onInput: (e) => a.setForm(form, k, e.target.value) });
const area = (iv, a, form, k, id) => h("textarea", { id, rows: 3, onInput: (e) => a.setForm(form, k, e.target.value) }, (iv.forms[form] || {})[k] || "");
const sel = (iv, a, form, k, id, opts) => h("select", { id, onChange: (e) => a.setForm(form, k, e.target.value, true) },
  opts.map(([v, l]) => h("option", { value: v, selected: String((iv.forms[form] || {})[k]) === String(v) }, l)));
const btn = (l, id, onClick, kind = "secondary", disabled = false) => h("button", { className: `btn btn-${kind}`, id, disabled, onClick }, l);
const row = (...b) => h("div", { style: "display:flex; gap:8px; flex-wrap:wrap; margin:8px 0; align-items:end;" }, b.filter(Boolean));
const none = (t = "None.") => h("div", { style: "color: var(--ink-500);" }, t);
const card = (title, id, ...kids) => h("div", { className: "card", id, style: "margin-bottom:16px;" }, h("h3", {}, title), ...kids);
const hist = (items) => h("ul", {}, (items || []).map((x) => h("li", {}, `${String(x.at).slice(0, 10)} ${String(x.event).replace(/_/g, " ").toLowerCase()} by ${x.by}${x.note ? ": " + x.note : ""}`)));
const noteBox = (iv, a, key, l, id) => field(l, id || `note-${key}`, h("textarea", { id: id || `note-${key}`, rows: 2, onInput: (e) => a.setNote(key, e.target.value) }, iv.notes[key] || ""));
const formError = (iv, name) => (iv.formError && iv.formError.form === name ? note(iv.formError.text, "error", `${name}-problem`) : null);

export function Inventory({ iv, role, userId, loading, onRetry, actions: a }) {
  return h("div", {},
    h("h1", {}, "Inventory"),
    note("This workspace is a stock register built from the receipts and issues that people type in. It values stock at a weighted average cost worked out from those figures. It posts nothing to a ledger, follows no accounting standard, and cannot tell whether the stock is really on the shelf. A different person approves every stock adjustment.", "info", "iv-banner"),
    iv.error ? ErrorState({ message: iv.error, onRetry }) : null,
    note(iv.notice, "success", "iv-notice"),
    loading ? LoadingState() : h("div", {},
      h("div", { className: "tabs", role: "tablist", style: "display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px;" },
        TABS.map(([id, l]) => h("button", { className: `btn ${iv.tab === id ? "btn-primary" : "btn-secondary"}`, role: "tab", id: `iv-tab-${id}`, "aria-selected": iv.tab === id ? "true" : "false", onClick: () => a.setTab(id) }, l))),
      iv.busy ? h("div", { style: "color: var(--ink-500);" }, "Working...") : null,
      iv.tab === "overview" ? overview(iv, role, a) : items(iv, role, userId, a)));
}

function overview(iv, role, a) {
  const o = iv.ov; if (!o) return none("Nothing loaded yet.");
  const c = o.counts;
  return h("div", {},
    card("What needs attention", "iv-attention", o.attention.length ? h("ul", {}, o.attention.map((x) => h("li", { "data-kind": x.kind }, Badge({ tone: ATTENTION_TONE[x.kind] || "info", label: words(x.kind) }), " ", `${x.count} ${x.text}`))) : none("Nothing needs attention.")),
    card("Stock value for active items, per currency", "iv-totals", o.totals.length ? h("ul", {}, o.totals.map((t) => h("li", { "data-currency": t.currency }, `${t.currency}: ${t.items} item(s), ${t.units} unit(s), value ${t.value}`))) : none("No active items yet."),
      h("p", { style: "color: var(--ink-500);" }, "Currencies are never added together.")),
    card("Counts", "iv-counts", h("ul", {}, [["Active items", c.active], ["Low stock", c.low_stock], ["Out of stock", c.out_of_stock], ["Discontinued", c.discontinued]].map(([l, n]) => h("li", {}, `${l}: ${n}`)))),
    policyCard(iv, role, a),
    card("What this does not do", "iv-limits", h("ul", {}, o.limitations.map((x) => h("li", {}, x)))));
}

function policyCard(iv, role, a) {
  const p = iv.ov.policy, f = iv.forms.policy;
  return card("Settings", "iv-policy", h("p", { id: "iv-policy-meaning" }, p.meaning),
    canApprove(role) && f ? h("div", {}, row(field("Days without movement before an item is flagged", "iv-policy-days", text(iv, a, "policy", "stale_days", "iv-policy-days"))),
      formError(iv, "policy"), btn("Save settings", "iv-policy-save", () => a.savePolicy(), "primary", iv.busy)) : h("p", { style: "color: var(--ink-500);" }, "Only an approver can change this setting."));
}

function items(iv, role, me, a) {
  const sel_ = iv.sel.item;
  return h("div", {},
    card("Items", "iv-items", iv.items.length ? iv.items.map((x) => h("div", { className: "card", style: "margin-bottom:8px;", "data-item": x.ref },
      h("div", {}, h("strong", {}, `${x.ref} · ${x.sku} · ${x.name}`), " ", St(x.status), x.out_of_stock ? [" ", Badge({ tone: "fail", label: "Out of stock" })] : (x.low_stock ? [" ", Badge({ tone: "warn", label: "Low stock" })] : null),
        x.not_moving ? [" ", Badge({ tone: "warn", label: "Not moving" })] : null, x.pending_adjustments ? [" ", Badge({ tone: "info", label: `${x.pending_adjustments} adjustment(s) waiting` })] : null),
      h("div", { style: "color: var(--ink-500);" }, `${x.location} · reorder level ${x.reorder_level} · last moved ${x.last_moved_on || "never"}`),
      h("div", {}, `On hand ${x.on_hand} ${x.unit}; value ${x.currency} ${x.value}; average cost ${x.average_cost}`),
      btn(sel_ && sel_.id === x.id ? "Hide details" : "Details", `iv-it-open-${x.ref}`, () => a.selectItem(sel_ && sel_.id === x.id ? null : x.id), "secondary", iv.busy))) : none("No items yet.")),
    sel_ ? detail(iv, role, me, a, sel_) : null,
    canPrepare(role) ? card("Add an item", "iv-item-card",
      row(field("Item code", "iv-it-sku", text(iv, a, "item", "sku", "iv-it-sku", "RICE-25")), field("Name", "iv-it-name", text(iv, a, "item", "name", "iv-it-name")), field("Unit", "iv-it-unit", text(iv, a, "item", "unit", "iv-it-unit", "bag"))),
      row(field("Currency", "iv-it-cur", text(iv, a, "item", "currency", "iv-it-cur", "NGN")), field("Reorder level (optional)", "iv-it-reorder", text(iv, a, "item", "reorder_level", "iv-it-reorder")), field("Location", "iv-it-loc", text(iv, a, "item", "location", "iv-it-loc"))),
      formError(iv, "item"), btn("Add item", "iv-it-save", () => a.addItem(), "primary", iv.busy)) : null);
}

function detail(iv, role, me, a, x) {
  const move = canMove(x, role), up = iv.forms.adjust.direction === "INCREASE";
  return card(`${x.ref} · ${x.name}`, "iv-item-detail",
    h("div", { id: "iv-item-figures" }, `On hand ${x.on_hand} ${x.unit}; value ${x.currency} ${x.value}; average cost ${x.average_cost}`),
    h("div", { id: "iv-moves" }, h("h4", {}, "Movements"), x.moves.length ? x.moves.map((m) => h("div", { "data-move": String(m.no) },
      `#${m.no} ${KIND_TEXT[m.kind] || m.kind}: ${m.qty} ${x.unit}${m.unit_cost ? " at " + m.unit_cost : ""}${m.value ? ", value " + m.value : ""}${m.moved_on ? ", dated " + m.moved_on : ""}${m.reference ? ", ref " + m.reference : ""}. `,
      isAdjustment(m) ? `${REASON_TEXT[m.reason_kind] || m.reason_kind}: ${m.reason} (proposed by ${who(m.by, me)}) ` : "", isAdjustment(m) ? St(m.status) : null,
      m.qty_after != null ? ` After: ${m.qty_after} on hand, value ${m.value_after}.` : "", m.decision_note ? ` Decision note: ${m.decision_note}` : "",
      canDecideAdjustment(m, role, me) ? h("div", {}, noteBox(iv, a, `adj-${x.id}-${m.no}`, "Note (approval: optional, at least 10 characters if given; rejection: required)", `iv-mv-${m.no}-note`),
        btn("Approve adjustment", `iv-mv-${m.no}-approve`, () => a.approveAdjustment(x.id, m.no), "primary", iv.busy), " ", btn("Reject adjustment", `iv-mv-${m.no}-reject`, () => a.rejectAdjustment(x.id, m.no), "secondary", iv.busy)) :
        (m.status === "PENDING" && canApprove(role) ? h("div", { style: "color: var(--ink-500);" }, ownWorkText("proposed this adjustment")) : null))) : none("No movements yet.")),
    move ? h("div", {}, h("h4", {}, "Receive stock"),
      row(field("Quantity", "iv-rc-qty", text(iv, a, "receive", "qty", "iv-rc-qty")), field("Unit cost", "iv-rc-cost", text(iv, a, "receive", "unit_cost", "iv-rc-cost", "150.00")), field("Date received", "iv-rc-date", text(iv, a, "receive", "moved_on", "iv-rc-date", "YYYY-MM-DD")), field("Reference", "iv-rc-ref", text(iv, a, "receive", "reference", "iv-rc-ref"))),
      formError(iv, "receive"), btn("Record receipt", "iv-rc-save", () => a.receive(x.id), "primary", iv.busy)) : null,
    move ? h("div", {}, h("h4", {}, "Issue stock"),
      row(field("Quantity", "iv-is-qty", text(iv, a, "issue", "qty", "iv-is-qty")), field("Date issued", "iv-is-date", text(iv, a, "issue", "moved_on", "iv-is-date", "YYYY-MM-DD")), field("Reference", "iv-is-ref", text(iv, a, "issue", "reference", "iv-is-ref"))),
      formError(iv, "issue"), btn("Record issue", "iv-is-save", () => a.issue(x.id), "primary", iv.busy)) : null,
    move ? h("div", {}, h("h4", {}, "Propose a stock adjustment"),
      row(field("Direction", "iv-ad-dir", sel(iv, a, "adjust", "direction", "iv-ad-dir", Object.entries(DIRECTION_TEXT))), field("Quantity", "iv-ad-qty", text(iv, a, "adjust", "qty", "iv-ad-qty")),
        up ? field(x.on_hand === 0 ? "Unit cost (needed: no stock on hand)" : "Unit cost (optional: the average is used)", "iv-ad-cost", text(iv, a, "adjust", "unit_cost", "iv-ad-cost")) : null,
        field("Kind of reason", "iv-ad-kind", sel(iv, a, "adjust", "reason_kind", "iv-ad-kind", Object.entries(REASON_TEXT)))),
      field("Reason (at least 10 characters)", "iv-ad-reason", area(iv, a, "adjust", "reason", "iv-ad-reason")), formError(iv, "adjust"), btn("Propose adjustment", "iv-ad-save", () => a.proposeAdjustment(x.id, x.on_hand), "primary", iv.busy)) : null,
    canDiscontinue(x, role) ? h("div", {}, h("h4", {}, "Discontinue this item"), noteBox(iv, a, `disc-${x.id}`, "Reason (required, at least 10 characters)", "iv-disc-note"), btn("Discontinue item", "iv-disc-save", () => a.discontinue(x.id), "secondary", iv.busy)) : null,
    h("div", {}, h("h4", {}, "History"), hist(x.history)));
}
