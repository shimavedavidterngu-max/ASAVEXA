import { h } from "../lib/vdom.js";
import { ui, frame } from "../lib/wsKit.js";
import { TABS, TYPES, AREAS, ADJ_KINDS, OUTCOMES, ATTENTION_TONE, statusOf, words, canPrepare, canApprove, canDecideDeal, canRecord, canDecideRow, canClose, ownText } from "../lib/mergers.js";

/** Mergers and acquisitions. Deals with a due-diligence checklist, closing conditions and price adjustments. It values nothing and gives no deal, tax or legal advice. */
export function Mergers({ st, role, userId: me, loading, onRetry, actions: a }) {
  const k = ui(st, a, statusOf);
  return frame({ st, p: "ma", title: "Mergers and acquisitions", tabs: TABS, loading, onRetry, a, k,
    banner: "This workspace keeps a register of merger, acquisition and disposal deals: a due-diligence checklist and closing conditions that one person marks done and a different person confirms, and price adjustments that turn the base price into an exact adjusted price. It values nothing, reads no contract and gives no deal, tax or legal advice. Use codes for parties, not names.",
    body: () => (st.tab === "overview" ? overview(st, k, role, a) : deals(st, k, role, me, a)) });
}

function overview(st, k, role, a) {
  const o = st.ov; if (!o) return k.none("Nothing loaded yet.");
  const c = o.counts;
  return h("div", {},
    k.card("What needs attention", "ma-attention", o.attention.length ? h("ul", {}, o.attention.map((x) => h("li", { "data-kind": x.kind }, k.Badge({ tone: ATTENTION_TONE[x.kind] || "info", label: words(x.kind) }), " ", `${x.count} ${x.text}`))) : k.none("Nothing needs attention.")),
    k.card("Open deals by currency (currencies are never added together)", "ma-currency", o.by_currency.length ? h("ul", {}, o.by_currency.map((t) => h("li", { "data-currency": t.currency }, `${t.currency}: ${t.deals} deal(s), base price ${t.base_price}, adjusted price ${t.adjusted_price}`))) : k.none("No open deals yet.")),
    k.card("Counts", "ma-counts", h("ul", {}, [["Waiting for a decision", c.proposed], ["Open", c.approved], ["Rejected", c.rejected], ["Closed", c.closed]].map(([l, n]) => h("li", {}, `${l}: ${n}`)), h("li", {}, `Closed as completed: ${o.outcomes.completed}; abandoned: ${o.outcomes.abandoned}`))),
    k.settingCard("ma", role, canApprove, "Due soon means within this many days", "due_soon_days"),
    k.limits(o.limitations, "ma-limits"));
}

function deals(st, k, role, me, a) {
  const s = st.sel.deal;
  return h("div", {},
    k.card("Deals", "ma-deals", st.deals.length ? st.deals.map((x) => h("div", { className: "card", style: "margin-bottom:8px;", "data-deal": x.ref },
      h("div", {}, h("strong", {}, `${x.ref} · ${x.name}`), " ", k.St(x.status), x.outcome ? [" ", k.St(x.outcome)] : null, x.target_passed ? [" ", k.Badge({ tone: "warn", label: "Target date passed" })] : null, x.overdue_conditions ? [" ", k.Badge({ tone: "warn", label: `${x.overdue_conditions} condition(s) overdue` })] : null),
      h("div", { style: "color: var(--ink-500);" }, `Reference ${x.deal_ref} · ${words(x.deal_type)} · base price ${x.base_price} ${x.currency}${x.status === "APPROVED" ? " · adjusted " + x.adjusted_price : ""}`),
      k.btn(s && s.id === x.id ? "Hide details" : "Details", `ma-dl-open-${x.ref}`, () => a.selectDeal(s && s.id === x.id ? null : x.id), "secondary", st.busy))) : k.none("No deals yet.")),
    s ? detail(st, k, role, me, a, s) : null,
    canPrepare(role) ? k.card("Propose a deal", "ma-deal-card",
      k.row(k.field("Name (a codename)", "ma-dl-name", k.text("deal", "name", "ma-dl-name")), k.field("Deal reference (a code)", "ma-dl-ref", k.text("deal", "deal_ref", "ma-dl-ref")), k.field("Currency (for example NGN)", "ma-dl-cur", k.text("deal", "currency", "ma-dl-cur")),
        k.field("Type", "ma-dl-type", k.sel("deal", "deal_type", "ma-dl-type", TYPES.map((t) => [t, words(t)])))),
      k.row(k.field("Base price", "ma-dl-price", k.text("deal", "base_price", "ma-dl-price")), k.field("Target closing date", "ma-dl-target", k.text("deal", "target_close_date", "ma-dl-target", "YYYY-MM-DD"))),
      k.field("Description (at least 10 characters)", "ma-dl-desc", k.text("deal", "description", "ma-dl-desc")), k.formError("deal"), k.btn("Propose deal", "ma-dl-save", () => a.createDeal(), "primary", st.busy)) : null);
}

function decideBox(st, k, role, me, a, x, kind, r) {
  return canDecideRow(x, r, role, me, kind) ? h("div", {}, k.noteBox(`${kind}-${x.id}-${r.no}`, "Note (confirmation: optional, at least 10 characters if given; rejection: required)", `ma-${kind}-${r.no}-note`),
    k.btn("Confirm", `ma-${kind}-${r.no}-confirm`, () => a.confirm(kind, x.id, r.no), "primary", st.busy), " ", k.btn(kind === "adjustments" ? "Reject" : "Send back", `ma-${kind}-${r.no}-reject`, () => a.reject(kind, x.id, r.no), "secondary", st.busy)) :
    ((r.status === "DONE" || r.status === "PROPOSED") && canApprove(role) && x.status === "APPROVED" ? h("p", { className: "ma-own", style: "color: var(--ink-500);" }, ownText) : null);
}

function doneForm(st, k, a, x, kind, r, label) {
  const f = st.forms.done[`${kind}-${r.no}`] || {}, id = `ma-${kind}-${r.no}`;
  return h("div", {}, k.row(k.field("Date", `${id}-date`, h("input", { id: `${id}-date`, type: "text", placeholder: "YYYY-MM-DD", value: f.done_on || "", onInput: (e) => a.setDone(kind, r.no, "done_on", e.target.value) })),
    k.field("Note (at least 10 characters)", `${id}-text`, h("input", { id: `${id}-text`, type: "text", value: f.note || "", onInput: (e) => a.setDone(kind, r.no, "note", e.target.value) }))),
  k.formError(`done-${kind}-${r.no}`), k.btn(label, `${id}-done`, () => a.markDone(kind, x.id, r.no), "secondary", st.busy));
}

function detail(st, k, role, me, a, x) {
  const dec = canDecideDeal(x, role, me), rec = canRecord(x, role), live = x.status === "APPROVED" || x.status === "CLOSED";
  const stepList = (kind, title, line, label) => h("div", { id: `ma-${kind}` }, h("h4", {}, title), x[kind].length ? x[kind].map((r) => h("div", { "data-row": `${kind}-${r.no}` }, line(r), " ", k.St(r.status), r.overdue ? [" ", k.Badge({ tone: "warn", label: "Overdue" })] : null, r.due_soon ? [" ", k.Badge({ tone: "info", label: "Due soon" })] : null,
    r.done_on ? ` Marked ${r.done_on}: ${r.done_note}` : "", r.decision_note ? ` Note: ${r.decision_note}` : "", rec && r.status === "OPEN" ? doneForm(st, k, a, x, kind, r, label) : null, decideBox(st, k, role, me, a, x, kind, r))) : k.none("None yet."));
  return k.card(`${x.ref} · ${x.name}`, "ma-deal-detail",
    h("div", { id: "ma-facts" }, `Reference ${x.deal_ref}. ${words(x.deal_type)}, in ${x.currency}. Base price ${x.base_price}. Target closing date ${x.target_close_date}. ${x.description}`),
    x.decision_note ? h("div", {}, `Decision note: ${x.decision_note}`) : null, x.close_note ? h("div", { id: "ma-closed" }, `Closed as ${words(x.outcome).toLowerCase()}: ${x.close_note}`) : null,
    live ? h("div", { id: "ma-position" }, h("p", { id: "ma-price" }, `Adjusted price ${x.adjusted_price} ${x.currency} (change ${x.price_change}, ${x.price_change_pct} percent of the base price).`),
      h("p", { id: "ma-progress" }, x.checklist_total ? `Checklist: ${x.checklist_confirmed} of ${x.checklist_total} confirmed (${x.checklist_pct} percent). ` : "Checklist: no items yet. ", x.conditions_total ? `Conditions: ${x.conditions_confirmed} of ${x.conditions_total} confirmed.` : "Conditions: none yet."),
      Object.keys(x.by_area).length ? h("ul", { id: "ma-areas" }, Object.entries(x.by_area).map(([ar, v]) => h("li", { "data-area": ar }, `${words(ar)}: ${v.confirmed} of ${v.total} confirmed`))) : null) : null,
    dec ? h("div", {}, h("h4", {}, "Decide"), k.noteBox(`dl-${x.id}`, "Note (approval: optional, at least 10 characters if given; rejection: required)", "ma-dl-note"),
      k.btn("Approve deal", "ma-dl-approve", () => a.approveDeal(x.id), "primary", st.busy), " ", k.btn("Reject deal", "ma-dl-reject", () => a.rejectDeal(x.id), "secondary", st.busy)) :
      (x.status === "PROPOSED" && canApprove(role) ? h("p", { id: "ma-dl-waiting", style: "color: var(--ink-500);" }, ownText) : null),
    stepList("checklist", "Due-diligence checklist", (r) => `${words(r.area)}: ${r.title}.`, "Mark as provided"),
    rec ? h("div", {}, k.row(k.field("Item", "ma-ck-title", k.text("checklist", "title", "ma-ck-title")), k.field("Area", "ma-ck-area", k.sel("checklist", "area", "ma-ck-area", AREAS.map((t) => [t, words(t)])))), k.formError("checklist"), k.btn("Add checklist item", "ma-ck-save", () => a.addChecklist(x.id), "primary", st.busy)) : null,
    stepList("conditions", "Closing conditions", (r) => `${r.title}, due ${r.due_date}.`, "Mark as met"),
    rec ? h("div", {}, k.row(k.field("Condition", "ma-cn-title", k.text("condition", "title", "ma-cn-title")), k.field("Due date", "ma-cn-due", k.text("condition", "due_date", "ma-cn-due", "YYYY-MM-DD"))), k.formError("condition"), k.btn("Add condition", "ma-cn-save", () => a.addCondition(x.id), "primary", st.busy)) : null,
    h("div", { id: "ma-adjustments" }, h("h4", {}, "Price adjustments"), x.adjustments.length ? x.adjustments.map((r) => h("div", { "data-row": `adjustments-${r.no}` }, `${words(r.kind)} ${r.amount}: ${r.basis}. `, k.St(r.status), r.decision_note ? ` Note: ${r.decision_note}` : "", decideBox(st, k, role, me, a, x, "adjustments", r))) : k.none("None yet.")),
    rec ? h("div", {}, k.row(k.field("Price goes", "ma-ad-kind", k.sel("adjustment", "kind", "ma-ad-kind", ADJ_KINDS.map((t) => [t, t === "INCREASE" ? "Up" : "Down"]))), k.field("Amount", "ma-ad-amount", k.text("adjustment", "amount", "ma-ad-amount"))),
      k.field("Basis (at least 10 characters)", "ma-ad-basis", k.text("adjustment", "basis", "ma-ad-basis")), k.formError("adjustment"), k.btn("Record adjustment", "ma-ad-save", () => a.addAdjustment(x.id), "primary", st.busy)) : null,
    canClose(x, role) ? h("div", {}, h("h4", {}, "Close the deal"), k.field("Outcome", "ma-cl-outcome", k.sel("close", "outcome", "ma-cl-outcome", OUTCOMES.map((t) => [t, words(t)]))), k.noteBox(`cl-${x.id}`, "Reason (at least 10 characters)", "ma-cl-note"), k.btn("Close deal", "ma-cl-save", () => a.closeDeal(x.id), "secondary", st.busy)) : null,
    h("div", {}, h("h4", {}, "History"), k.hist(x.history)));
}
