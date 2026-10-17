import { h } from "../lib/vdom.js";
import { ui, frame } from "../lib/wsKit.js";
import { TABS, ATTENTION_TONE, statusOf, words, canPrepare, canApprove, canDecideLocation, canRecord, canDecideRow, canClose, ownText } from "../lib/franchise.js";

/** Franchise and multi-location. Locations with a royalty rate, monthly sales reports and royalty payments. It collects no money and applies no franchise law. */
export function Franchise({ st, role, userId: me, loading, onRetry, actions: a }) {
  const k = ui(st, a, statusOf);
  return frame({ st, p: "fch", title: "Franchise and multi-location", tabs: TABS, loading, onRetry, a, k,
    banner: "This workspace keeps a register of franchise or branch locations with a royalty rate. Monthly sales reports and royalty payments are each recorded by one person and confirmed by a different person, and the royalty due, the amount paid and the balance are worked out exactly. It reads no agreement, collects no money, audits no sales and applies no franchise law. Use reference codes, not names.",
    body: () => (st.tab === "overview" ? overview(st, k, role, a) : locations(st, k, role, me, a)) });
}

function overview(st, k, role, a) {
  const o = st.ov; if (!o) return k.none("Nothing loaded yet.");
  const c = o.counts;
  return h("div", {},
    k.card("What needs attention", "fch-attention", o.attention.length ? h("ul", {}, o.attention.map((x) => h("li", { "data-kind": x.kind }, k.Badge({ tone: ATTENTION_TONE[x.kind] || "info", label: words(x.kind) }), " ", `${x.count} ${x.text}`))) : k.none("Nothing needs attention.")),
    k.card("Totals by currency (confirmed only; currencies are never added together)", "fch-currency", o.by_currency.length ? h("ul", {}, o.by_currency.map((t) => h("li", { "data-currency": t.currency }, `${t.currency}: ${t.locations} location(s), sales ${t.sales_total}, royalty due ${t.royalty_due}, paid ${t.paid_total}, balance ${t.balance}`))) : k.none("No open locations yet.")),
    k.card("Counts", "fch-counts", h("ul", {}, [["Waiting for a decision", c.proposed], ["Open", c.approved], ["Rejected", c.rejected], ["Closed", c.closed]].map(([l, n]) => h("li", {}, `${l}: ${n}`)))),
    k.settingCard("fch", role, canApprove, "Grace period in days", "grace_days"),
    k.limits(o.limitations, "fch-limits"));
}

function locations(st, k, role, me, a) {
  const s = st.sel.location;
  return h("div", {},
    k.card("Locations", "fch-locations", st.locations.length ? st.locations.map((x) => h("div", { className: "card", style: "margin-bottom:8px;", "data-location": x.ref },
      h("div", {}, h("strong", {}, `${x.ref} · ${x.name}`), " ", k.St(x.status), x.missing_periods.length ? [" ", k.Badge({ tone: "warn", label: `${x.missing_periods.length} report(s) missing` })] : null, Number(x.overdue_amount) > 0 ? [" ", k.Badge({ tone: "warn", label: "Royalty overdue" })] : null),
      h("div", { style: "color: var(--ink-500);" }, `Reference ${x.location_ref} · ${x.currency} · royalty rate ${x.royalty_rate_pct} percent${x.status === "APPROVED" || x.status === "CLOSED" ? " · balance " + x.balance : ""}`),
      k.btn(s && s.id === x.id ? "Hide details" : "Details", `fch-lc-open-${x.ref}`, () => a.selectLocation(s && s.id === x.id ? null : x.id), "secondary", st.busy))) : k.none("No locations yet.")),
    s ? detail(st, k, role, me, a, s) : null,
    canPrepare(role) ? k.card("Propose a location", "fch-location-card",
      k.row(k.field("Name", "fch-lc-name", k.text("location", "name", "fch-lc-name")), k.field("Location reference (a code)", "fch-lc-ref", k.text("location", "location_ref", "fch-lc-ref")), k.field("Currency (for example NGN)", "fch-lc-cur", k.text("location", "currency", "fch-lc-cur")),
        k.field("Royalty rate (percent)", "fch-lc-rate", k.text("location", "royalty_rate_pct", "fch-lc-rate"))),
      k.row(k.field("First reporting month", "fch-lc-start", k.text("location", "start_period", "fch-lc-start", "YYYY-MM")), k.field("Reports fall due on this day of the next month (1 to 28)", "fch-lc-day", k.text("location", "due_day", "fch-lc-day"))),
      k.field("Description (at least 10 characters)", "fch-lc-desc", k.text("location", "description", "fch-lc-desc")), k.formError("location"), k.btn("Propose location", "fch-lc-save", () => a.createLocation(), "primary", st.busy)) : null);
}

function rowList(st, k, role, me, a, x, kind, title, line) {
  return h("div", { id: `fch-${kind}` }, h("h4", {}, title), x[kind].length ? x[kind].map((r) => h("div", { "data-row": `${kind}-${r.no}` }, line(r), " ", k.St(r.status), r.decision_note ? ` Note: ${r.decision_note}` : "",
    canDecideRow(x, r, role, me) ? h("div", {}, k.noteBox(`${kind}-${x.id}-${r.no}`, "Note (confirmation: optional, at least 10 characters if given; rejection: required)", `fch-${kind}-${r.no}-note`),
      k.btn("Confirm", `fch-${kind}-${r.no}-confirm`, () => a.confirm(kind, x.id, r.no), "primary", st.busy), " ", k.btn("Reject", `fch-${kind}-${r.no}-reject`, () => a.reject(kind, x.id, r.no), "secondary", st.busy)) :
      (r.status === "PROPOSED" && canApprove(role) && x.status === "APPROVED" ? h("p", { className: "fch-own", style: "color: var(--ink-500);" }, ownText) : null))) : k.none("None yet."));
}

function detail(st, k, role, me, a, x) {
  const dec = canDecideLocation(x, role, me), rec = canRecord(x, role), live = x.status === "APPROVED" || x.status === "CLOSED";
  return k.card(`${x.ref} · ${x.name}`, "fch-location-detail",
    h("div", { id: "fch-facts" }, `Reference ${x.location_ref}. Royalty rate ${x.royalty_rate_pct} percent of gross sales, in ${x.currency}. First reporting month ${x.start_period}; reports fall due on day ${x.due_day} of the following month. ${x.description}`),
    x.decision_note ? h("div", {}, `Decision note: ${x.decision_note}`) : null, x.close_note ? h("div", { id: "fch-closed" }, `Closed: ${x.close_note}`) : null,
    live ? h("div", { id: "fch-position" }, h("p", { id: "fch-totals" }, `Confirmed sales ${x.sales_total}; royalty due ${x.royalty_due}; paid ${x.paid_total}; balance ${x.balance} ${x.currency}. `, k.St(x.balance_state), ` Overdue amount ${x.overdue_amount}. Reports submitted late: ${x.late_reports}.`),
      x.missing_periods.length ? h("p", { id: "fch-missing" }, `Months past due with no sales report recorded: ${x.missing_periods.join(", ")}.`) : null) : null,
    dec ? h("div", {}, h("h4", {}, "Decide"), k.noteBox(`lc-${x.id}`, "Note (approval: optional, at least 10 characters if given; rejection: required)", "fch-lc-note"),
      k.btn("Approve location", "fch-lc-approve", () => a.approveLocation(x.id), "primary", st.busy), " ", k.btn("Reject location", "fch-lc-reject", () => a.rejectLocation(x.id), "secondary", st.busy)) :
      (x.status === "PROPOSED" && canApprove(role) ? h("p", { id: "fch-lc-waiting", style: "color: var(--ink-500);" }, ownText) : null),
    rowList(st, k, role, me, a, x, "reports", "Sales reports", (r) => `${r.period}: gross sales ${r.gross_sales}, royalty ${r.royalty}, submitted ${r.submitted_on}, due ${r.due_date}${r.late ? " (late)" : ""}.`),
    rec ? h("div", {}, k.row(k.field("Month", "fch-rp-period", k.text("report", "period", "fch-rp-period", "YYYY-MM")), k.field("Gross sales", "fch-rp-sales", k.text("report", "gross_sales", "fch-rp-sales")), k.field("Date submitted", "fch-rp-date", k.text("report", "submitted_on", "fch-rp-date", "YYYY-MM-DD"))),
      k.formError("report"), k.btn("Record sales report", "fch-rp-save", () => a.addReport(x.id), "primary", st.busy)) : null,
    rowList(st, k, role, me, a, x, "payments", "Royalty payments", (r) => `${r.paid_on}: ${r.amount} (${r.note}).`),
    rec ? h("div", {}, k.row(k.field("Amount", "fch-py-amount", k.text("payment", "amount", "fch-py-amount")), k.field("Date paid", "fch-py-date", k.text("payment", "paid_on", "fch-py-date", "YYYY-MM-DD")), k.field("Note", "fch-py-note", k.text("payment", "note", "fch-py-note"))),
      k.formError("payment"), k.btn("Record payment", "fch-py-save", () => a.addPayment(x.id), "primary", st.busy)) : null,
    canClose(x, role) ? h("div", {}, h("h4", {}, "Close the location"), k.noteBox(`cl-${x.id}`, "Reason (at least 10 characters)", "fch-cl-note"), k.btn("Close location", "fch-cl-save", () => a.closeLocation(x.id), "secondary", st.busy)) : null,
    h("div", {}, h("h4", {}, "History"), k.hist(x.history)));
}
