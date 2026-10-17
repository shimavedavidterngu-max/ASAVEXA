import { h } from "../lib/vdom.js";
import { ui, frame } from "../lib/wsKit.js";
import { TABS, ATTENTION_TONE, statusOf, words, canPrepare, canApprove, canEdit, canSubmit, canDecide, canRecord, ownText } from "../lib/oprs.js";

/** Operations research. Compare options by typed costs and yearly flows. The numbers are worked out by the server; nothing is recommended. */
export function Oprs({ st, role, userId: me, loading, onRetry, actions: a }) {
  const k = ui(st, a, statusOf);
  return frame({ st, p: "op", title: "Operations research", tabs: TABS, loading, onRetry, a, k,
    banner: "This workspace compares options by the costs and yearly flows that people type in, and works out the net value, the discounted value (NPV), the payback year and the benefit-cost ratio exactly. A different person reviews each analysis. It recommends nothing and decides nothing: the highest NPV is a number, not advice. Nothing is forecast or checked against the real world.",
    body: () => (st.tab === "overview" ? overview(st, k) : analyses(st, k, role, me, a)) });
}

function overview(st, k) {
  const o = st.ov; if (!o) return k.none("Nothing loaded yet.");
  const c = o.counts;
  return h("div", {},
    k.card("What needs attention", "op-attention", o.attention.length ? h("ul", {}, o.attention.map((x) => h("li", { "data-kind": x.kind }, k.Badge({ tone: ATTENTION_TONE[x.kind] || "info", label: words(x.kind) }), " ", `${x.count} ${x.text}`))) : k.none("Nothing needs attention.")),
    k.card("Counts", "op-counts", h("ul", {}, [["Draft", c.draft], ["Waiting for review", c.submitted], ["Approved", c.approved], ["Returned", c.returned], ["Withdrawn", c.withdrawn]].map(([l, n]) => h("li", {}, `${l}: ${n}`)),
      h("li", { id: "op-decisions" }, `Decisions recorded: ${o.decisions_recorded}`))),
    k.card("Approved analyses by currency", "op-currencies", o.approved_by_currency.length ? h("ul", {}, o.approved_by_currency.map((x) => h("li", { "data-currency": x.currency }, `${x.currency}: ${x.analyses} analysis(es). Currencies are never added together.`))) : k.none("None yet.")),
    k.limits(o.limitations, "op-limits"));
}

function analyses(st, k, role, me, a) {
  const s = st.sel.analysis;
  return h("div", {},
    k.card("Analyses", "op-analyses", st.analyses.length ? st.analyses.map((x) => h("div", { className: "card", style: "margin-bottom:8px;", "data-analysis": x.ref },
      h("div", {}, h("strong", {}, `${x.ref} · ${x.title}`), " ", k.St(x.status), x.decision ? [" ", k.Badge({ tone: "pass", label: "Decision recorded" })] : null),
      h("div", { style: "color: var(--ink-500);" }, `${x.currency} · discount rate ${x.discount_rate} percent · ${x.active_options} option(s)`),
      k.btn(s && s.id === x.id ? "Hide details" : "Details", `op-an-open-${x.ref}`, () => a.selectAnalysis(s && s.id === x.id ? null : x.id), "secondary", st.busy))) : k.none("No analyses yet.")),
    s ? detail(st, k, role, me, a, s) : null,
    canPrepare(role) ? k.card("Start an analysis", "op-analysis-card",
      k.row(k.field("Title", "op-an-title", k.text("analysis", "title", "op-an-title")), k.field("Currency (three letters)", "op-an-cur", k.text("analysis", "currency", "op-an-cur")), k.field("Discount rate (percent a year)", "op-an-rate", k.text("analysis", "discount_rate", "op-an-rate"))),
      k.field("Purpose (what is being decided)", "op-an-purpose", k.text("analysis", "purpose", "op-an-purpose")), k.formError("analysis"), k.btn("Start analysis", "op-an-save", () => a.createAnalysis(), "primary", st.busy)) : null);
}

function detail(st, k, role, me, a, x) {
  const edit = canEdit(x, role), dec = canDecide(x, role, me), rec = canRecord(x, role, me), active = x.options.filter((o) => o.status === "ACTIVE");
  return k.card(`${x.ref} · ${x.title}`, "op-analysis-detail",
    h("div", { id: "op-facts" }, `${x.purpose}. Currency ${x.currency}; discount rate ${x.discount_rate} percent a year; ${x.active_options} option(s) compared.`),
    x.decision_note ? h("div", { id: "op-decision-note" }, `Note: ${x.decision_note}`) : null,
    x.results.length ? h("div", { id: "op-results" }, h("h4", {}, "Results (worked out exactly)"), x.results.map((r) => h("div", { className: "card", style: "margin-bottom:6px;", "data-option": String(r.no) },
      h("strong", {}, r.name), " ", r.highest_npv ? k.Badge({ tone: "info", label: "Highest NPV" }) : null,
      h("div", {}, `Upfront ${r.upfront_cost}; flows over ${r.years} year(s) total ${r.total_flows}; net value ${r.net_value}; NPV ${r.npv}; payback ${r.payback_year ? "in year " + r.payback_year : "not within " + r.years + " year(s)"}; benefit-cost ratio ${r.benefit_cost_ratio}; rank ${r.rank}.`),
      h("div", { style: "color: var(--ink-500);", className: "op-sens" }, "NPV at other rates: " + r.sensitivity.map((s) => `${s.rate} percent: ${s.npv}`).join("; "))))) : k.none("Add options to see the results."),
    h("div", { id: "op-options" }, h("h4", {}, "Options"), x.options.length ? x.options.map((o) => h("div", { "data-opt": String(o.no) }, `#${o.no} ${o.name}: upfront ${o.upfront_cost}; flows ${o.flows.join(", ")} `, k.St(o.status), o.removed_note ? ` Removed: ${o.removed_note}` : "",
      edit && o.status === "ACTIVE" ? h("div", {}, k.noteBox(`ro-${x.id}-${o.no}`, "Reason for removing (at least 10 characters)", `op-opt-${o.no}-note`), k.btn("Remove option", `op-opt-${o.no}-remove`, () => a.removeOption(x.id, o.no), "secondary", st.busy)) : null)) : k.none("No options yet.")),
    edit ? h("div", {}, h("h4", {}, "Add an option"), k.row(k.field("Name", "op-opt-name", k.text("option", "name", "op-opt-name")), k.field("Upfront cost", "op-opt-up", k.text("option", "upfront_cost", "op-opt-up"))),
      k.field("Net flow for each year, separated by semicolons (for example 600; 600; 650)", "op-opt-flows", k.text("option", "flows", "op-opt-flows")), k.formError("option"), k.btn("Add option", "op-opt-save", () => a.addOption(x.id), "primary", st.busy)) : null,
    canSubmit(x, role) ? h("div", {}, h("h4", {}, "Submit for review"), k.noteBox(`sb-${x.id}`, "Note for the approver (optional, at least 10 characters if given)", "op-sb-note"), k.btn("Submit", "op-sb-save", () => a.submit(x.id), "primary", st.busy), " ",
      h("span", {}, ""), k.noteBox(`wd-${x.id}`, "Reason for withdrawing (at least 10 characters)", "op-wd-note"), k.btn("Withdraw analysis", "op-wd-save", () => a.withdraw(x.id), "secondary", st.busy)) :
      (edit ? h("p", { id: "op-need-two", style: "color: var(--ink-500);" }, "Add at least two options before submitting.") : null),
    dec ? h("div", {}, h("h4", {}, "Review"), k.noteBox(`dc-${x.id}`, "Note (approval: optional, at least 10 characters if given; returning: required)", "op-dc-note"),
      k.btn("Approve analysis", "op-dc-approve", () => a.approve(x.id), "primary", st.busy), " ", k.btn("Return analysis", "op-dc-return", () => a.returnIt(x.id), "secondary", st.busy)) :
      (x.status === "SUBMITTED" && st.sel.analysis && canApprove(role) ? h("p", { id: "op-waiting", style: "color: var(--ink-500);" }, ownText) : null),
    x.decision ? h("div", { id: "op-decision" }, h("h4", {}, "Decision"), `Chosen: #${x.decision.option_no} ${x.decision.option_name}. Reason: ${x.decision.rationale}`,
      x.decision_flag ? h("div", { id: "op-decision-flag" }, "The chosen option did not have the highest NPV. This is for a person to look at, not an error.") : null) : null,
    rec ? h("div", {}, h("h4", {}, "Record the decision"), k.row(k.field("Option chosen", "op-dec-opt", k.sel("decision", "option_no", "op-dec-opt", [["", "Choose..."], ...active.map((o) => [String(o.no), `#${o.no} ${o.name}`])])), k.field("Why (at least 10 characters)", "op-dec-why", k.text("decision", "rationale", "op-dec-why"))),
      k.formError("decision"), k.btn("Record decision", "op-dec-save", () => a.decide(x.id), "primary", st.busy)) :
      (x.status === "APPROVED" && !x.decision && canApprove(role) ? h("p", { id: "op-dec-waiting", style: "color: var(--ink-500);" }, ownText) : null),
    h("div", {}, h("h4", {}, "History"), k.hist(x.history)));
}
