import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState } from "../components/DataState.js";
import { TABS, SCORE_LABEL, ATTENTION_TONE, FLAG_TEXT, MOVE_TEXT, canPrepare, canApprove, statusOf, words, fmt, supplierMoves, contractMoves, orderMoves, invoiceMoves, approvalText, overrideNeeded, linkablePayments } from "../lib/procurement.js";

/**
 * Procurement: supplier, contract, purchase order, delivery, invoice (three-way match), payment record and supplier review.
 * It records and checks. It does not buy, pay or verify anything, and a match is only as good as what people typed in.
 * Every approval is by someone other than the person who created the thing, and the page says so.
 */
const Badge = ({ tone, label, id }) => h("span", { className: `badge badge-${tone || "neutral"}`, id }, label);
const St = (s) => Badge({ ...statusOf(s) });
const note = (t, kind = "info", id) => (t ? h("div", { className: `alert alert-${kind}`, id, style: "margin-bottom:12px;", role: kind === "error" ? "alert" : "status" }, t) : null);
const field = (l, id, inp, hint) => h("div", { className: "field" }, h("label", { for: id }, l), inp, hint ? h("small", { style: "color: var(--ink-500);" }, hint) : null);
const text = (pc, a, form, k, id, ph) => h("input", { id, type: "text", value: (pc.forms[form] || {})[k] == null ? "" : (pc.forms[form] || {})[k], placeholder: ph || "", onInput: (e) => a.setForm(form, k, e.target.value) });
const sel = (pc, a, form, k, id, opts, blank) => h("select", { id, onChange: (e) => a.setForm(form, k, e.target.value, true) },
  [...(blank ? [h("option", { value: "" }, blank)] : []), ...opts.map(([v, l]) => h("option", { value: v, selected: String((pc.forms[form] || {})[k]) === String(v) }, l))]);
const table = (head, rows, id) => h("div", { className: "table-scroll" }, h("table", { className: "data-table", id }, h("thead", {}, h("tr", {}, head.map(([l, right]) => h("th", { style: right ? "text-align:right;" : undefined }, l)))), h("tbody", {}, rows)));
const td = (v, right) => h("td", { style: right ? "text-align:right;" : undefined }, v);
const btn = (l, id, onClick, kind = "secondary", disabled = false) => h("button", { className: `btn btn-${kind}`, id, disabled, onClick }, l);
const row = (...b) => h("div", { style: "display:flex; gap:8px; flex-wrap:wrap; margin:8px 0; align-items:end;" }, b.filter(Boolean));
const none = (t = "None.") => h("div", { style: "color: var(--ink-500);" }, t);
const card = (title, id, ...kids) => h("div", { className: "card", id, style: "margin-bottom:16px;" }, h("h3", {}, title), ...kids);
const hist = (items) => h("ul", {}, (items || []).map((x) => h("li", {}, `${String(x.at).slice(0, 10)} ${String(x.event).replace(/_/g, " ").toLowerCase()} by ${x.by}${x.note ? ": " + x.note : ""}`)));
const noteBox = (pc, a, key, l, id) => field(l, id || `note-${key}`, h("textarea", { id: id || `note-${key}`, rows: 2, onInput: (e) => a.setNote(key, e.target.value) }, pc.notes[key] || ""));
const formError = (pc, name) => (pc.formError && pc.formError.form === name ? note(pc.formError.text, "error", `${name}-problem`) : null);
const sm = (t) => h("small", { style: "color: var(--ink-500);" }, t);

export function Procurement({ pc, role, userId, loading, onRetry, actions: a }) {
  return h("div", {},
    h("h1", {}, "Procurement"),
    note("This workspace records and checks. It does not buy anything, make any payment or confirm that goods arrived. A match is only as good as what people type in, and every approval is by someone other than the person who created the item.", "warning", "pc-banner"),
    pc.error ? ErrorState({ message: pc.error, onRetry }) : null,
    note(pc.notice, "success", "pc-notice"),
    loading ? LoadingState() : h("div", {},
      h("div", { className: "tabs", role: "tablist", style: "display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px;" },
        TABS.map(([id, l]) => h("button", { className: `btn ${pc.tab === id ? "btn-primary" : "btn-secondary"}`, role: "tab", id: `pc-tab-${id}`, "aria-selected": pc.tab === id ? "true" : "false", onClick: () => a.setTab(id) }, l))),
      pc.busy ? h("div", { style: "color: var(--ink-500);" }, "Working...") : null,
      pc.tab === "overview" ? overview(pc, role, a) : pc.tab === "suppliers" ? suppliers(pc, role, userId, a) : pc.tab === "contracts" ? contracts(pc, role, userId, a)
        : pc.tab === "orders" ? orders(pc, role, userId, a) : pc.tab === "receipts" ? receipts(pc, role, userId, a) : reviews(pc, role, a)));
}

// ---------------------------------------------------------------- overview
function overview(pc, role, a) {
  const o = pc.ov; if (!o) return none("Nothing loaded yet.");
  const c = o.counts;
  return h("div", {},
    card("What needs attention", "pc-attention", o.attention.length ? h("ul", {}, o.attention.map((x) => h("li", { "data-kind": x.kind }, Badge({ tone: ATTENTION_TONE[x.kind] || "info", label: words(x.kind) }), " ", x.text))) : none("Nothing needs attention right now.")),
    card("Counts", "pc-counts", h("ul", {}, [["Suppliers", c.suppliers], ["Contracts", c.contracts], ["Open purchase orders", c.orders_open], ["Orders waiting for approval", c.orders_waiting], ["Invoices waiting for approval", c.invoices_waiting],
      ["Approved invoices not yet paid", c.invoices_unpaid], ["Invoices recorded as paid", c.invoices_paid]].map(([l, n]) => h("li", {}, `${l}: ${n}`)))),
    policyCard(pc, role, a),
    card("What this does not do", "pc-limits", h("ul", {}, o.limitations.map((x) => h("li", {}, x)))));
}

function policyCard(pc, role, a) {
  const p = pc.ov.policy, f = pc.forms.policy;
  return card("Policy settings", "pc-policy", h("p", { id: "pc-policy-meaning" }, p.meaning),
    canApprove(role) && f ? h("div", {},
      field("Price tolerance (% above the order price)", "pc-policy-tol", text(pc, a, "policy", "tolerance_pct", "pc-policy-tol"), "An invoice price above this is an exception. 0 means no tolerance."),
      field("Two-approver limit per currency", "pc-policy-limit", text(pc, a, "policy", "dual_limits", "pc-policy-limit", "DEFAULT=10000, USD=5000"), "An order at or above this needs two different approvers."),
      field("Warn about a contract this many days before it ends", "pc-policy-days", text(pc, a, "policy", "warning_days", "pc-policy-days")),
      formError(pc, "policy"), btn("Save policy", "pc-policy-save", () => a.savePolicy(), "primary", pc.busy)) : h("p", { style: "color: var(--ink-500);" }, "Only an approver can change these settings."));
}

// ---------------------------------------------------------------- suppliers
function suppliers(pc, role, me, a) {
  const s1 = pc.sel.supplier, cats = pc.options ? pc.options.categories : [];
  return h("div", {},
    card("Suppliers", "pc-suppliers", pc.suppliers.length ? table([["Ref"], ["Supplier"], ["Kind"], ["Country"], ["Status"], [""]], pc.suppliers.map((s) => h("tr", { "data-supplier": s.id },
      td(s.ref), td(s.name), td(words(s.category)), td(s.country || "—"), td([St(s.status), s.related_party ? [" ", Badge({ tone: "warn", label: "Connected party" })] : null]), td(btn("Open", `pc-sup-open-${s.ref}`, () => a.selectSupplier(s.id)))))) : none("No suppliers yet.")),
    s1 ? supplierDetail(pc, role, me, a, s1) : null,
    canPrepare(role) ? card("Register a supplier", "pc-sup-card",
      h("p", { style: "color: var(--ink-500);" }, "A different person must approve the supplier before anything can be ordered from it."),
      row(field("Name", "pc-sup-name", text(pc, a, "supplier", "name", "pc-sup-name")), field("Kind", "pc-sup-cat", sel(pc, a, "supplier", "category", "pc-sup-cat", cats.map((x) => [x, words(x)]))),
        field("Country", "pc-sup-country", text(pc, a, "supplier", "country", "pc-sup-country")), field("Contact", "pc-sup-contact", text(pc, a, "supplier", "contact", "pc-sup-contact")), field("Tax reference", "pc-sup-tax", text(pc, a, "supplier", "tax_ref", "pc-sup-tax"))),
      row(field("Is anyone here connected to this supplier?", "pc-sup-related", sel(pc, a, "supplier", "related", "pc-sup-related", [["no", "No"], ["yes", "Yes"]]), "For example an owner, a relative or a staff member."),
        (pc.forms.supplier || {}).related === "yes" ? field("Describe the connection", "pc-sup-relnote", text(pc, a, "supplier", "related_party_note", "pc-sup-relnote")) : null),
      formError(pc, "supplier"), btn("Register supplier", "pc-sup-save", () => a.registerSupplier(), "primary", pc.busy)) : null);
}

function moveRow(pc, a, key, id, moves, run, label = "Note") {
  if (!moves.length) return null;
  return h("div", { style: "margin-top:6px;" }, noteBox(pc, a, key, label, `note-${key}`), row(moves.map((m) => btn(MOVE_TEXT[m], `${id}-${m}`, () => run(m), m === "approve" ? "primary" : "secondary", pc.busy))));
}

function supplierDetail(pc, role, me, a, s) {
  const spend = Object.entries(s.approved_spend || {});
  return card(`${s.ref} ${s.name}`, "pc-sup-detail",
    h("p", {}, [St(s.status), " ", `${words(s.category)} · ${s.country || "no country given"} · ${s.contact || "no contact given"}`]),
    s.related_party ? note(`Connected party: ${s.related_party_note}`, "warning", "pc-sup-related-note") : null,
    h("ul", {}, [`Orders: ${s.orders}`, `Deliveries: ${s.deliveries}`, `Invoices: ${s.invoices}`, `Approved invoice spend: ${spend.length ? spend.map(([c, v]) => fmt(v, c)).join(", ") : "none yet"}`].map((x) => h("li", {}, x))),
    s.needs_review ? note("This supplier has deliveries but no review yet.", "info", "pc-sup-needs-review") : null,
    s.latest_review ? h("p", { id: "pc-sup-latest" }, `Latest review ${s.latest_review.period}: average ${s.latest_review.average} of 5.`) : null,
    moveRow(pc, a, `sup-${s.id}`, `pc-sup-${s.ref}`, supplierMoves(s, me, role), (m) => a.supplierStep(s.id, m), "Note (required to suspend or reinstate; required to approve a connected party)"),
    h("h4", {}, "History"), hist(s.history), btn("Close this panel", "pc-sup-hide", () => a.selectSupplier(null)));
}

// ---------------------------------------------------------------- contracts
function contracts(pc, role, me, a) {
  const sups = pc.options ? pc.options.suppliers : [];
  return h("div", {},
    card("Contracts", "pc-contracts", pc.contracts.length ? pc.contracts.map((c) => h("div", { className: "card", "data-contract": c.id, style: "margin-bottom:10px;" },
      h("div", {}, h("strong", {}, `${c.ref} · ${c.title} · ${c.supplier_name}`), " ", St(c.status), c.status === "ACTIVE" ? [" ", St(c.state)] : null, c.expiring_soon ? [" ", Badge({ tone: "warn", label: `Ends in ${c.days_left} days` })] : null),
      h("div", { style: "color: var(--ink-500);" }, `${c.start_date} to ${c.end_date} · ceiling ${fmt(c.ceiling, c.currency)} · committed ${fmt(c.committed)} · remaining ${fmt(c.remaining)}`),
      moveRow(pc, a, `con-${c.id}`, `pc-con-${c.ref}`, contractMoves(c, me, role), (m) => a.contractStep(c.id, m), "Note (required to terminate)"),
      h("details", {}, h("summary", {}, "History"), hist(c.history)))) : none("No contracts yet.")),
    canPrepare(role) ? card("Draft a contract", "pc-con-card",
      h("p", { style: "color: var(--ink-500);" }, "Type in the ceiling and dates from the signed agreement. ASAVEXA has not read it and only holds orders against the numbers you enter."),
      row(field("Supplier", "pc-con-supplier", sel(pc, a, "contract", "supplier_id", "pc-con-supplier", sups.map((x) => [x.id, `${x.ref} ${x.name}`]), "Choose a supplier")), field("Title", "pc-con-title", text(pc, a, "contract", "title", "pc-con-title")),
        field("Currency", "pc-con-cur", text(pc, a, "contract", "currency", "pc-con-cur", "NGN")), field("Ceiling", "pc-con-ceiling", text(pc, a, "contract", "ceiling", "pc-con-ceiling", "0.00"))),
      row(field("Starts", "pc-con-start", text(pc, a, "contract", "start_date", "pc-con-start", "YYYY-MM-DD")), field("Ends", "pc-con-end", text(pc, a, "contract", "end_date", "pc-con-end", "YYYY-MM-DD")), field("Description", "pc-con-desc", text(pc, a, "contract", "description", "pc-con-desc"))),
      formError(pc, "contract"), btn("Draft contract", "pc-con-save", () => a.draftContract(), "primary", pc.busy)) : null);
}

// ---------------------------------------------------------------- purchase orders
function orders(pc, role, me, a) {
  const sups = pc.options ? pc.options.suppliers : [], f = pc.forms.order, cons = (pc.options ? pc.options.contracts : []).filter((c) => !f.supplier_id || c.supplier_id === f.supplier_id);
  return h("div", {},
    card("Purchase orders", "pc-orders", h("div", {}, field("Show", "pc-po-filter", h("select", { id: "pc-po-filter", onChange: (e) => a.filterOrders(e.target.value) }, [["", "All"], ["REQUESTED", "Waiting for approval"], ["APPROVED", "Approved"], ["CLOSED", "Closed"], ["REJECTED", "Rejected"], ["CANCELLED", "Cancelled"]]
        .map(([v, l]) => h("option", { value: v, selected: pc.orderFilter === v }, l))))),
      pc.orders.length ? pc.orders.map((o) => orderCard(pc, role, me, a, o)) : none("No purchase orders.")),
    canPrepare(role) ? card("Raise a purchase order", "pc-po-card",
      h("p", { style: "color: var(--ink-500);" }, "You cannot approve your own order. The total is worked out for you."),
      row(field("Supplier", "pc-po-supplier", sel(pc, a, "order", "supplier_id", "pc-po-supplier", sups.map((x) => [x.id, `${x.ref} ${x.name}`]), "Choose a supplier")),
        field("Contract (optional)", "pc-po-contract", sel(pc, a, "order", "contract_id", "pc-po-contract", cons.map((x) => [x.id, `${x.ref} ${x.title} (${x.currency})`]), "No contract")),
        field("Currency", "pc-po-cur", text(pc, a, "order", "currency", "pc-po-cur", "NGN")), field("Expected by", "pc-po-date", text(pc, a, "order", "expected_date", "pc-po-date", "YYYY-MM-DD"))),
      field("What it is for", "pc-po-purpose", text(pc, a, "order", "purpose", "pc-po-purpose")),
      h("h4", {}, "Lines"), f.lines.map((l, i) => row(field(`Line ${i + 1}: what`, `pc-po-line-${i}-desc`, h("input", { id: `pc-po-line-${i}-desc`, type: "text", value: l.description, onInput: (e) => a.setLine(i, "description", e.target.value) })),
        field("Quantity", `pc-po-line-${i}-qty`, h("input", { id: `pc-po-line-${i}-qty`, type: "text", value: l.qty, onInput: (e) => a.setLine(i, "qty", e.target.value) })),
        field("Unit price", `pc-po-line-${i}-price`, h("input", { id: `pc-po-line-${i}-price`, type: "text", value: l.unit_price, onInput: (e) => a.setLine(i, "unit_price", e.target.value) })))),
      row(btn("Add another line", "pc-po-addline", () => a.addLine(), "secondary", pc.busy || f.lines.length >= 50)),
      formError(pc, "order"), btn("Raise order", "pc-po-save", () => a.raiseOrder(), "primary", pc.busy)) : null);
}

function orderCard(pc, role, me, a, o) {
  const open = pc.sel.order && pc.sel.order.id === o.id ? pc.sel.order : null;
  return h("div", { className: "card", "data-order": o.id, style: "margin-bottom:10px;" },
    h("div", {}, h("strong", {}, `${o.ref} · ${o.supplier_name} · ${fmt(o.total, o.currency)}`), " ", St(o.status), o.fulfilment ? [" ", St(o.fulfilment)] : null, o.overdue ? [" ", Badge({ tone: "warn", label: "Past its expected date" })] : null),
    h("div", { style: "color: var(--ink-500);" }, `${o.purpose} · expected by ${o.expected_date} · raised by ${o.requested_by}${o.contract_ref ? ` · contract ${o.contract_ref}` : ""}`),
    approvalText(o) ? h("div", {}, approvalText(o)) : null,
    table([["#"], ["What"], ["Ordered", true], ["Unit price", true], ["Received", true], ["Invoiced", true], ["Still to come", true]], o.lines.map((l) => h("tr", {}, td(String(l.n)), td(l.description), td(l.qty, true), td(fmt(l.unit_price), true), td(l.received, true), td(l.invoiced, true), td(l.outstanding, true)))),
    moveRow(pc, a, `po-${o.id}`, `pc-po-${o.ref}`, orderMoves(o, me, role), (m) => a.orderStep(o.id, m), "Note (required to reject, cancel or close)"),
    row(btn(open ? "Hide chain" : "Show deliveries and invoices", `pc-po-open-${o.ref}`, () => a.selectOrder(open ? null : o.id), "secondary", pc.busy)),
    open ? h("div", { "data-chain": o.id }, h("h4", {}, "Deliveries"), open.deliveries.length ? h("ul", {}, open.deliveries.map((d) => h("li", {}, `${d.ref} received ${d.received_date} by ${d.received_by}: ${d.lines.map((l) => `line ${l.line} × ${l.qty}`).join(", ")}`))) : none("No delivery recorded."),
      h("h4", {}, "Invoices"), open.invoices.length ? h("ul", {}, open.invoices.map((i) => h("li", {}, `${i.ref} (${i.invoice_number}) ${fmt(i.total, i.currency)} — ${statusOf(i.status).label}`))) : none("No invoice recorded.")) : null,
    h("details", {}, h("summary", {}, "History"), hist(o.history)));
}

// ---------------------------------------------------------------- deliveries and invoices
function receipts(pc, role, me, a) {
  const live = pc.live || [];
  const dOrder = live.find((o) => o.id === pc.forms.delivery.order_id), iOrder = live.find((o) => o.id === pc.forms.invoice.order_id);
  return h("div", {},
    card("Invoices", "pc-invoices", pc.invoices.length ? pc.invoices.map((i) => invoiceCard(pc, role, me, a, i)) : none("No invoices yet.")),
    card("Deliveries", "pc-deliveries", pc.deliveries.length ? table([["Ref"], ["Order"], ["Supplier"], ["Received"], ["What arrived"], ["Recorded by"]], pc.deliveries.map((d) => h("tr", { "data-delivery": d.id },
      td(d.ref), td(d.order_ref), td(d.supplier_name), td(d.received_date), td(d.lines.map((l) => `line ${l.line} × ${l.qty}`).join(", ")), td(d.received_by)))) : none("No deliveries recorded.")),
    canPrepare(role) ? card("Record a delivery", "pc-dl-card",
      h("p", { style: "color: var(--ink-500);" }, "The person who raised an order cannot record its delivery. Enter only what actually arrived."),
      field("Order", "pc-dl-order", sel(pc, a, "delivery", "order_id", "pc-dl-order", live.map((o) => [o.id, `${o.ref} ${o.supplier_name}`]), "Choose an approved order")),
      dOrder ? h("div", {}, dOrder.lines.map((l) => row(h("span", {}, `Line ${l.n}: ${l.description} (still to come ${l.outstanding})`), field("Quantity received", `pc-dl-qty-${l.n}`, h("input", { id: `pc-dl-qty-${l.n}`, type: "text", value: (pc.forms.delivery.qtys || {})[l.n] || "", onInput: (e) => a.setQty("delivery", l.n, e.target.value) })))),
        row(field("Date received", "pc-dl-date", text(pc, a, "delivery", "received_date", "pc-dl-date", "YYYY-MM-DD")), field("Note", "pc-dl-note", text(pc, a, "delivery", "note", "pc-dl-note"))), formError(pc, "delivery"),
        btn("Record delivery", "pc-dl-save", () => a.addDelivery(), "primary", pc.busy)) : null) : null,
    canPrepare(role) ? card("Record an invoice", "pc-iv-card",
      h("p", { style: "color: var(--ink-500);" }, "The invoice is compared with the order and with what was recorded as received. A difference makes it an exception that a different person must decide."),
      field("Order", "pc-iv-order", sel(pc, a, "invoice", "order_id", "pc-iv-order", live.map((o) => [o.id, `${o.ref} ${o.supplier_name}`]), "Choose an approved order")),
      iOrder ? h("div", {}, row(field("Supplier's invoice number", "pc-iv-number", text(pc, a, "invoice", "invoice_number", "pc-iv-number")), field("Invoice date", "pc-iv-date", text(pc, a, "invoice", "invoice_date", "pc-iv-date", "YYYY-MM-DD")),
        field("Due date", "pc-iv-due", text(pc, a, "invoice", "due_date", "pc-iv-due", "YYYY-MM-DD")), field("Currency on the invoice", "pc-iv-cur", text(pc, a, "invoice", "currency", "pc-iv-cur"))),
        iOrder.lines.map((l) => row(h("span", {}, `Line ${l.n}: ${l.description}`), field("Quantity invoiced", `pc-iv-qty-${l.n}`, h("input", { id: `pc-iv-qty-${l.n}`, type: "text", value: (pc.forms.invoice.qtys || {})[l.n] || "", onInput: (e) => a.setQty("invoice", l.n, e.target.value) })),
          field("Unit price on the invoice", `pc-iv-price-${l.n}`, h("input", { id: `pc-iv-price-${l.n}`, type: "text", value: (pc.forms.invoice.prices || {})[l.n] || "", onInput: (e) => a.setPrice(l.n, e.target.value) })))),
        formError(pc, "invoice"), btn("Record invoice", "pc-iv-save", () => a.addInvoice(), "primary", pc.busy)) : null) : null);
}

function invoiceCard(pc, role, me, a, i) {
  const moves = invoiceMoves(i, me, role), links = moves.includes("paid") ? linkablePayments(pc.released, i) : [];
  const key = `iv-${i.id}`, over = overrideNeeded(i);
  return h("div", { className: "card", "data-invoice": i.id, style: "margin-bottom:10px;" },
    h("div", {}, h("strong", {}, `${i.ref} · ${i.supplier_name} · ${i.invoice_number} · ${fmt(i.total, i.currency)}`), " ", St(i.status), i.overdue ? [" ", Badge({ tone: "warn", label: "Past its due date" })] : null),
    h("div", { style: "color: var(--ink-500);" }, `Order ${i.order_ref} · dated ${i.invoice_date} · due ${i.due_date} · recorded by ${i.recorded_by}`),
    i.flags.length ? h("ul", { className: "pc-flags" }, i.flags.map((f) => h("li", { "data-flag": f }, Badge({ tone: "fail", label: words(f) }), " ", FLAG_TEXT[f] || f))) : null,
    i.override_note ? h("div", {}, `Approved despite the warnings: ${i.override_note}`) : null,
    i.payment ? h("div", {}, `Paid ${i.payment.paid_date}. Bank reference ${i.payment.bank_reference}${i.payment.treasury_ref ? `. Linked to Treasury payment ${i.payment.treasury_ref}` : ""}.`) : null,
    (i.status === "MATCHED" || i.status === "EXCEPTION") && canApprove(role) && i.recorded_by === me ? h("small", { className: "pc-waiting" }, "Waiting for a different approver to decide") : null,
    moves.filter((m) => m !== "paid").length ? moveRow(pc, a, key, `pc-iv-${i.ref}`, moves.filter((m) => m !== "paid"), (m) => a.invoiceStep(i.id, m), over ? "Note (required to approve an exception: say why it is acceptable)" : "Note (required to reject)") : null,
    moves.includes("paid") ? h("div", { style: "margin-top:6px;" }, h("h4", {}, "Record payment"),
      links.length ? field("Link a released Treasury payment", `pc-iv-link-${i.ref}`, h("select", { id: `pc-iv-link-${i.ref}`, onChange: (e) => a.setNote(`link-${i.id}`, e.target.value) }, [h("option", { value: "" }, "Do not link"), ...links.map((p) => h("option", { value: p.id }, `${p.ref} ${p.payee} ${fmt(p.amount, p.currency)} released ${p.released_date}`))])) : null,
      row(field("Date paid", `pc-iv-paid-date-${i.ref}`, h("input", { id: `pc-iv-paid-date-${i.ref}`, type: "text", placeholder: "YYYY-MM-DD", onInput: (e) => a.setNote(`paiddate-${i.id}`, e.target.value) })),
        field("Bank's reference", `pc-iv-paid-ref-${i.ref}`, h("input", { id: `pc-iv-paid-ref-${i.ref}`, type: "text", onInput: (e) => a.setNote(`paidref-${i.id}`, e.target.value) }))),
      btn(MOVE_TEXT.paid, `pc-iv-paid-${i.ref}`, () => a.invoiceStep(i.id, "paid"), "secondary", pc.busy)) : null,
    h("details", {}, h("summary", {}, "Lines and history"), table([["#"], ["What"], ["Quantity", true], ["Unit price", true], ["Total", true]], i.lines.map((l) => h("tr", {}, td(String(l.line)), td(l.description), td(l.qty, true), td(fmt(l.unit_price), true), td(fmt(l.total), true)))), hist(i.history)));
}

// ---------------------------------------------------------------- reviews
function reviews(pc, role, a) {
  const sups = pc.options ? pc.options.suppliers : [];
  return h("div", {},
    card("Supplier reviews", "pc-reviews", pc.reviews.length ? table([["Ref"], ["Supplier"], ["Period"], ["Delivery", true], ["Quality", true], ["Price", true], ["Service", true], ["Average", true], ["Comment"]], pc.reviews.map((r) => h("tr", { "data-review": r.id },
      td(r.ref), td(r.supplier_name), td(r.period), td(String(r.scores.delivery), true), td(String(r.scores.quality), true), td(String(r.scores.price), true), td(String(r.scores.service), true), td([r.average, r.low ? [" ", Badge({ tone: "warn", label: "Low score" })] : null], true), td(r.comment || "—")))) : none("No reviews yet."),
      h("p", { style: "color: var(--ink-500);" }, "A review is a person's judgement on a 1 to 5 scale. The average is plain arithmetic, not a rating issued by ASAVEXA.")),
    canPrepare(role) ? card("Review a supplier", "pc-rv-card",
      row(field("Supplier", "pc-rv-supplier", sel(pc, a, "review", "supplier_id", "pc-rv-supplier", sups.map((x) => [x.id, `${x.ref} ${x.name}`]), "Choose a supplier")), field("Period", "pc-rv-period", text(pc, a, "review", "period", "pc-rv-period", "2026-Q1"))),
      row(Object.entries(SCORE_LABEL).map(([k, l]) => field(`${l} (1 to 5)`, `pc-rv-${k}`, text(pc, a, "review", k, `pc-rv-${k}`)))),
      field("Comment (required for any score of 1 or 2)", "pc-rv-comment", text(pc, a, "review", "comment", "pc-rv-comment")),
      formError(pc, "review"), btn("Save review", "pc-rv-save", () => a.addReview(), "primary", pc.busy)) : null);
}
