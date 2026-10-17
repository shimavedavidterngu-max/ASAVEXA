import { h } from "../lib/vdom.js";
import { ui, frame } from "../lib/wsKit.js";
import { TABS, ATTENTION_TONE, CLASSES, statusOf, words, canPrepare, canApprove, canDecideCase, canLodge, canAdjudicate, canConfirm, canRecord, canClose, ownText } from "../lib/insolvency.js";

/** Insolvency. A case register: creditor claims, realisations, costs and an illustrative distribution. It pays no one, files nothing and applies no law. */
export function Insolvency({ st, role, userId: me, loading, onRetry, actions: a }) {
  const k = ui(st, a, statusOf);
  return frame({ st, p: "isv", title: "Insolvency", tabs: TABS, loading, onRetry, a, k,
    banner: "This workspace keeps a register of an insolvent estate: the creditor claims, the money coming in and the costs, and works out an illustrative distribution exactly, class by class in the order the case records, with every cent allocated. A different person approves each case, admits each claim and confirms each realisation and cost. It pays no one, files nothing and applies no insolvency law: the order of the classes is typed by a person. Use reference codes, not names.",
    body: () => (st.tab === "overview" ? overview(st, k) : cases(st, k, role, me, a)) });
}

function overview(st, k) {
  const o = st.ov; if (!o) return k.none("Nothing loaded yet.");
  const c = o.counts;
  return h("div", {},
    k.card("What needs attention", "isv-attention", o.attention.length ? h("ul", {}, o.attention.map((x) => h("li", { "data-kind": x.kind }, k.Badge({ tone: ATTENTION_TONE[x.kind] || "info", label: words(x.kind) }), " ", `${x.count} ${x.text}`))) : k.none("Nothing needs attention.")),
    k.card("Counts", "isv-counts", h("ul", {}, [["Waiting for a decision", c.proposed], ["Open", c.open], ["Rejected", c.rejected], ["Closed", c.closed]].map(([l, n]) => h("li", {}, `${l}: ${n}`)))),
    k.card("Totals by currency", "isv-totals", o.totals.length ? h("ul", {}, o.totals.map((t) => h("li", { "data-currency": t.currency }, `${t.currency}: ${t.cases} case(s), admitted ${t.admitted}, distributed ${t.distributed}. Currencies are never added together.`))) : k.none("No open or closed cases yet.")),
    k.limits(o.limitations, "isv-limits"));
}

function cases(st, k, role, me, a) {
  const s = st.sel.case;
  return h("div", {},
    k.card("Cases", "isv-cases", st.cases.length ? st.cases.map((x) => h("div", { className: "card", style: "margin-bottom:8px;", "data-case": x.ref },
      h("div", {}, h("strong", {}, `${x.ref} · ${x.title}`), " ", k.St(x.status), x.late_claims ? [" ", k.Badge({ tone: "warn", label: "Late claims" })] : null),
      h("div", { style: "color: var(--ink-500);" }, `${x.currency} · claimed ${x.claimed_total} · admitted ${x.admitted_total}`),
      k.btn(s && s.id === x.id ? "Hide details" : "Details", `isv-cs-open-${x.ref}`, () => a.selectCase(s && s.id === x.id ? null : x.id), "secondary", st.busy))) : k.none("No cases yet.")),
    s ? detail(st, k, role, me, a, s) : null,
    canPrepare(role) ? k.card("Propose a case", "isv-case-card",
      k.row(k.field("Title", "isv-cs-title", k.text("case", "title", "isv-cs-title")), k.field("Currency (three letters)", "isv-cs-cur", k.text("case", "currency", "isv-cs-cur")), k.field("Claims deadline (optional)", "isv-cs-dl", k.text("case", "claims_deadline", "isv-cs-dl", "YYYY-MM-DD"))),
      k.field("Description", "isv-cs-desc", k.text("case", "description", "isv-cs-desc")), k.field("Order the classes are paid, first to last (typed by a person, not law)", "isv-cs-order", k.text("case", "priority", "isv-cs-order")),
      k.formError("case"), k.btn("Propose case", "isv-cs-save", () => a.createCase(), "primary", st.busy)) : null);
}

function detail(st, k, role, me, a, x) {
  const dec = canDecideCase(x, role, me), w = x.waterfall;
  return k.card(`${x.ref} · ${x.title}`, "isv-case-detail",
    h("div", { id: "isv-facts" }, `${x.description}. Currency ${x.currency}; classes are paid in this order: ${x.priority.map(words).join(", ")}${x.claims_deadline ? "; claims deadline " + x.claims_deadline : ""}. Claimed ${x.claimed_total}; admitted ${x.admitted_total}.`),
    x.decision_note ? h("div", {}, `Decision note: ${x.decision_note}`) : null, x.close_note ? h("div", { id: "isv-closed" }, `Closed: ${x.close_note}`) : null,
    dec ? h("div", {}, h("h4", {}, "Decide"), k.noteBox(`cs-${x.id}`, "Note (approval: optional, at least 10 characters if given; rejection: required)", "isv-cs-note"),
      k.btn("Approve case", "isv-cs-approve", () => a.approveCase(x.id), "primary", st.busy), " ", k.btn("Reject case", "isv-cs-reject", () => a.rejectCase(x.id), "secondary", st.busy)) :
      (x.status === "PROPOSED" && canApprove(role) ? h("p", { id: "isv-cs-waiting", style: "color: var(--ink-500);" }, ownText) : null),
    w ? h("div", { id: "isv-waterfall" }, h("h4", {}, "Distribution worked out now (not paid)"),
      h("p", { id: "isv-funds" }, `Realisations ${w.realisations}; costs ${w.costs}; already distributed ${w.distributed_to_date}; available ${w.available}. Still owed to admitted claims ${w.total_owed}; would be paid ${w.total_paid}; shortfall ${w.shortfall}; left over ${w.left_over}.`),
      w.costs_exceed ? h("p", { id: "isv-costs-note" }, "Confirmed costs are above confirmed realisations. This is for a person to look at.") : null,
      w.classes.map((c) => h("div", { "data-class": c.claim_class }, h("strong", {}, words(c.claim_class)), ` owed ${c.owed}; paid ${c.paid}; recovery ${c.recovery_pct} percent`,
        c.claims.length ? h("ul", {}, c.claims.map((y) => h("li", { "data-dividend": String(y.no) }, `#${y.no} ${y.creditor_ref}: owed ${y.owed}, dividend ${y.dividend}`))) : null))) : null,
    x.distributions.length ? h("div", { id: "isv-distributions" }, h("h4", {}, "Recorded distributions"), x.distributions.map((d) => h("div", { "data-distribution": String(d.no) }, `#${d.no} on ${d.on}: ${d.total} recorded as distributed (${d.lines.length} claim(s)); shortfall then ${d.shortfall}.${d.note ? " Note: " + d.note : ""}`))) : null,
    canRecord(x, role, me) ? h("div", {}, h("h4", {}, "Record this distribution"), k.noteBox(`ds-${x.id}`, "Note (optional, at least 10 characters if given)", "isv-ds-note"), k.btn("Record distribution", "isv-ds-save", () => a.recordDistribution(x.id), "primary", st.busy),
      h("p", { style: "color: var(--ink-500);" }, "This saves the calculation. ASAVEXA pays nobody.")) : null,
    h("div", { id: "isv-claims" }, h("h4", {}, "Claims"), x.claims.length ? x.claims.map((y) => h("div", { "data-claim": String(y.no) },
      `#${y.no} ${y.creditor_ref} (${words(y.claim_class)}): claimed ${y.amount}${y.status === "ADMITTED" ? `, admitted ${y.admitted}, paid ${y.paid}, still owed ${y.owed}` : ""} (${y.basis}) `, k.St(y.status), y.late ? [" ", k.Badge({ tone: "warn", label: "Late" })] : null, y.decision_note ? ` Note: ${y.decision_note}` : "",
      canAdjudicate(x, y, role, me) ? h("div", {}, k.row(k.field("Amount admitted", `isv-ck-${y.no}-amt`, h("input", { id: `isv-ck-${y.no}-amt`, type: "text", value: (st.forms.admit[y.no] || {}).amount || "", onInput: (e) => a.setAdmit(y.no, "amount", e.target.value) })),
        k.field("Admission note (optional)", `isv-ck-${y.no}-adm-note`, h("input", { id: `isv-ck-${y.no}-adm-note`, type: "text", value: (st.forms.admit[y.no] || {}).note || "", onInput: (e) => a.setAdmit(y.no, "note", e.target.value) }))),
        st.formError && st.formError.form === `admit-${y.no}` ? k.note(st.formError.text, "error", `admit-${y.no}-problem`) : null,
        k.btn("Admit claim", `isv-ck-${y.no}-admit`, () => a.admitClaim(x.id, y.no), "primary", st.busy), " ", k.noteBox(`ck-${x.id}-${y.no}`, "Reason for rejecting (required)", `isv-ck-${y.no}-note`), k.btn("Reject claim", `isv-ck-${y.no}-reject`, () => a.rejectClaim(x.id, y.no), "secondary", st.busy)) :
        (y.status === "LODGED" && canApprove(role) && x.status === "OPEN" ? h("p", { className: "isv-own", style: "color: var(--ink-500);" }, ownText) : null))) : k.none("No claims yet.")),
    canLodge(x, role) ? h("div", {}, h("h4", {}, "Lodge a claim"), k.row(k.field("Creditor reference (a code)", "isv-ck-ref", k.text("claim", "creditor_ref", "isv-ck-ref")), k.field("Class", "isv-ck-class", k.sel("claim", "claim_class", "isv-ck-class", CLASSES.map((c) => [c, words(c)]))), k.field("Amount claimed", "isv-ck-amt", k.text("claim", "amount", "isv-ck-amt"))),
      k.field("Basis of the claim (at least 10 characters)", "isv-ck-basis", k.text("claim", "basis", "isv-ck-basis")), k.formError("claim"), k.btn("Lodge claim", "isv-ck-save", () => a.addClaim(x.id), "primary", st.busy)) : null,
    h("div", { id: "isv-entries" }, h("h4", {}, "Realisations and costs"), x.entries.length ? x.entries.map((e) => h("div", { "data-entry": String(e.no) }, `#${e.no} ${e.entry_type === "COST" ? "Cost" : "Realisation"} ${e.amount} on ${e.entry_date}: ${e.description} `, k.St(e.status), e.decision_note ? ` Note: ${e.decision_note}` : "",
      canConfirm(x, e, role, me) ? h("div", {}, k.noteBox(`en-${x.id}-${e.no}`, "Note (confirmation: optional, at least 10 characters if given; rejection: required)", `isv-en-${e.no}-note`),
        k.btn("Confirm entry", `isv-en-${e.no}-confirm`, () => a.confirmEntry(x.id, e.no), "primary", st.busy), " ", k.btn("Reject entry", `isv-en-${e.no}-reject`, () => a.rejectEntry(x.id, e.no), "secondary", st.busy)) :
        (e.status === "PROPOSED" && canApprove(role) && x.status === "OPEN" ? h("p", { className: "isv-own", style: "color: var(--ink-500);" }, ownText) : null))) : k.none("None yet.")),
    canLodge(x, role) ? h("div", {}, h("h4", {}, "Record a realisation or cost"), k.row(k.field("Type", "isv-en-type", k.sel("entry", "entry_type", "isv-en-type", [["REALISATION", "Realisation (money in)"], ["COST", "Cost of the administration"]])), k.field("Amount", "isv-en-amt", k.text("entry", "amount", "isv-en-amt")), k.field("Date", "isv-en-date", k.text("entry", "entry_date", "isv-en-date", "YYYY-MM-DD"))),
      k.field("Description", "isv-en-desc", k.text("entry", "description", "isv-en-desc")), k.formError("entry"), k.btn("Record entry", "isv-en-save", () => a.addEntry(x.id), "primary", st.busy)) : null,
    canClose(x, role) ? h("div", {}, h("h4", {}, "Close the case"), k.noteBox(`cl-${x.id}`, "Reason (at least 10 characters)", "isv-cl-note"), k.btn("Close case", "isv-cl-save", () => a.closeCase(x.id), "secondary", st.busy)) : null,
    h("div", {}, h("h4", {}, "History"), k.hist(x.history)));
}
