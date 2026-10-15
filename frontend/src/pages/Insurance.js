import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState } from "../components/DataState.js";
import { TABS, COVER_TEXT, ATTENTION_TONE, canPrepare, canApprove, statusOf, words, who, canDecideOutcome, canPropose, canReceive, canCancel, canClaim, ownWorkText } from "../lib/insurance.js";

/**
 * Insurance and claims. A register of policies and claims, with settlements or declines proposed by one person and decided by a different person, and money received tracked against the settled amount.
 * It contacts no insurer and gives no insurance advice.
 */
const Badge = ({ tone, label, id }) => h("span", { className: `badge badge-${tone || "neutral"}`, id }, label);
const St = (s) => Badge({ ...statusOf(s) });
const note = (t, kind = "info", id) => (t ? h("div", { className: `alert alert-${kind}`, id, style: "margin-bottom:12px;", role: kind === "error" ? "alert" : "status" }, t) : null);
const field = (l, id, inp) => h("div", { className: "field" }, h("label", { for: id }, l), inp);
const text = (ic, a, form, k, id, ph) => h("input", { id, type: "text", value: (ic.forms[form] || {})[k] == null ? "" : (ic.forms[form] || {})[k], placeholder: ph || "", onInput: (e) => a.setForm(form, k, e.target.value) });
const area = (ic, a, form, k, id, rows = 2) => h("textarea", { id, rows, onInput: (e) => a.setForm(form, k, e.target.value) }, (ic.forms[form] || {})[k] || "");
const sel = (ic, a, form, k, id, opts) => h("select", { id, onChange: (e) => a.setForm(form, k, e.target.value, true) }, opts.map(([v, l]) => h("option", { value: v, selected: String((ic.forms[form] || {})[k]) === String(v) }, l)));
const btn = (l, id, onClick, kind = "secondary", disabled = false) => h("button", { className: `btn btn-${kind}`, id, disabled, onClick }, l);
const row = (...b) => h("div", { style: "display:flex; gap:8px; flex-wrap:wrap; margin:8px 0; align-items:end;" }, b.filter(Boolean));
const none = (t = "None.") => h("div", { style: "color: var(--ink-500);" }, t);
const card = (title, id, ...kids) => h("div", { className: "card", id, style: "margin-bottom:16px;" }, h("h3", {}, title), ...kids);
const hist = (items) => h("ul", {}, (items || []).map((x) => h("li", {}, `${String(x.at).slice(0, 10)} ${String(x.event).replace(/_/g, " ").toLowerCase()} by ${x.by}${x.note ? ": " + x.note : ""}`)));
const noteBox = (ic, a, key, l, id) => field(l, id, h("textarea", { id, rows: 2, onInput: (e) => a.setNote(key, e.target.value) }, ic.notes[key] || ""));
const formError = (ic, name) => (ic.formError && ic.formError.form === name ? note(ic.formError.text, "error", `${name}-problem`) : null);

export function Insurance({ ic, role, userId, loading, onRetry, actions: a }) {
  return h("div", {},
    h("h1", {}, "Insurance and claims"),
    note("This workspace keeps a register of insurance policies and claims that people type in, works out the money exactly, and requires a different person to decide each settlement or decline. It contacts no insurer, checks no cover or policy wording, assesses no loss, gives no insurance or legal advice, holds no money and posts nothing to the ledger.", "info", "ic-banner"),
    ic.error ? ErrorState({ message: ic.error, onRetry }) : null,
    note(ic.notice, "success", "ic-notice"),
    loading ? LoadingState() : h("div", {},
      h("div", { className: "tabs", role: "tablist", style: "display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px;" },
        TABS.map(([id, l]) => h("button", { className: `btn ${ic.tab === id ? "btn-primary" : "btn-secondary"}`, role: "tab", id: `ic-tab-${id}`, "aria-selected": ic.tab === id ? "true" : "false", onClick: () => a.setTab(id) }, l))),
      ic.busy ? h("div", { style: "color: var(--ink-500);" }, "Working...") : null,
      ic.tab === "overview" ? overview(ic, role, a) : ic.tab === "policies" ? policies(ic, role, a) : claims(ic, role, userId, a)));
}

function overview(ic, role, a) {
  const o = ic.ov; if (!o) return none("Nothing loaded yet.");
  const c = o.counts;
  return h("div", {},
    card("What needs attention", "ic-attention", o.attention.length ? h("ul", {}, o.attention.map((x) => h("li", { "data-kind": x.kind }, Badge({ tone: ATTENTION_TONE[x.kind] || "info", label: words(x.kind) }), " ", `${x.count} ${x.text}`))) : none("Nothing needs attention.")),
    card("Per currency", "ic-totals", o.totals.length ? h("ul", {}, o.totals.map((t) => h("li", { "data-currency": t.currency },
      `${t.currency}: ${t.active_policies} active polic${t.active_policies === 1 ? "y" : "ies"}, sum insured ${t.sum_insured}, premium ${t.premium}; ${t.open_claims} open claim(s) claiming ${t.claimed_open}; settled ${t.settled}, received ${t.received}, still to receive ${t.outstanding}`))) : none("No policies yet."),
      h("p", { style: "color: var(--ink-500);" }, "Amounts in different currencies are never added together.")),
    card("Counts", "ic-counts", h("ul", {}, [["Active policies", c.policies_active], ["Cancelled policies", c.policies_cancelled], ["Open claims", c.claims_open], ["Claims with an outcome waiting", c.claims_proposed], ["Settled claims", c.claims_settled], ["Declined claims", c.claims_declined]].map(([l, n]) => h("li", {}, `${l}: ${n}`)))),
    settingCard(ic, role, a),
    card("What this does not do", "ic-limits", h("ul", {}, o.limitations.map((x) => h("li", {}, x)))));
}

function settingCard(ic, role, a) {
  const p = ic.ov.policy;
  return card("Settings", "ic-setting", h("p", { id: "ic-setting-meaning" }, p.meaning),
    canApprove(role) && ic.forms.setting ? h("div", {}, row(field("Days before the end date to flag a policy as ending soon", "ic-set-days", text(ic, a, "setting", "warning_days", "ic-set-days"))),
      formError(ic, "setting"), btn("Save settings", "ic-set-save", () => a.saveSetting(), "primary", ic.busy)) : h("p", { style: "color: var(--ink-500);" }, "Only an approver can change this setting."));
}

function policies(ic, role, a) {
  const s = ic.sel.policy;
  return h("div", {},
    card("Policies", "ic-policies", ic.policies.length ? ic.policies.map((x) => h("div", { className: "card", style: "margin-bottom:8px;", "data-policy": x.ref },
      h("div", {}, h("strong", {}, `${x.ref} · ${x.insurer} · ${x.policy_number}`), " ", St(x.status), x.ending_soon ? [" ", Badge({ tone: "warn", label: "Ending soon" })] : null, x.expired ? [" ", Badge({ tone: "warn", label: "Past its end date" })] : null),
      h("div", { style: "color: var(--ink-500);" }, `${COVER_TEXT[x.cover_type] || x.cover_type} · ${x.start_date} to ${x.end_date} · sum insured ${x.currency} ${x.sum_insured} · premium ${x.premium} · excess ${x.excess} · ${x.open_claims} open claim(s)`),
      btn(s && s.id === x.id ? "Hide details" : "Details", `ic-po-open-${x.ref}`, () => a.selectPolicy(s && s.id === x.id ? null : x.id), "secondary", ic.busy))) : none("No policies yet.")),
    s ? policyDetail(ic, role, a, s) : null,
    canPrepare(role) ? card("Record a policy", "ic-policy-card",
      row(field("Insurer", "ic-po-insurer", text(ic, a, "policy", "insurer", "ic-po-insurer")), field("Policy number", "ic-po-number", text(ic, a, "policy", "policy_number", "ic-po-number")), field("Type of cover", "ic-po-cover", sel(ic, a, "policy", "cover_type", "ic-po-cover", Object.entries(COVER_TEXT)))),
      row(field("What is covered", "ic-po-covers", text(ic, a, "policy", "covers", "ic-po-covers")), field("Currency", "ic-po-cur", text(ic, a, "policy", "currency", "ic-po-cur", "NGN"))),
      row(field("Sum insured", "ic-po-si", text(ic, a, "policy", "sum_insured", "ic-po-si")), field("Premium", "ic-po-prem", text(ic, a, "policy", "premium", "ic-po-prem")), field("Excess (optional)", "ic-po-excess", text(ic, a, "policy", "excess", "ic-po-excess"))),
      row(field("Start date", "ic-po-start", text(ic, a, "policy", "start_date", "ic-po-start", "YYYY-MM-DD")), field("End date", "ic-po-end", text(ic, a, "policy", "end_date", "ic-po-end", "YYYY-MM-DD"))),
      formError(ic, "policy"), btn("Record policy", "ic-po-save", () => a.addPolicy(), "primary", ic.busy)) : null);
}

function policyDetail(ic, role, a, p) {
  return card(`${p.ref} · ${p.insurer}`, "ic-policy-detail",
    h("div", {}, `Covers: ${p.covers}`), p.status === "CANCELLED" ? h("div", { id: "ic-cancelled" }, `Cancelled: ${p.cancel_note}`) : null,
    h("div", { id: "ic-policy-claims" }, h("h4", {}, "Claims on this policy"), (p.claims || []).length ? p.claims.map((c) => h("div", { "data-pclaim": c.ref }, `${c.ref} · ${c.description} · claimed ${c.currency} ${c.claimed_amount} · `, St(c.status))) : none("No claims yet.")),
    canClaim(p, role) ? h("div", {}, h("h4", {}, "Record a claim"),
      row(field("Date of the loss", "ic-cm-loss", text(ic, a, "claim", "loss_date", "ic-cm-loss", "YYYY-MM-DD")), field("Date reported", "ic-cm-rep", text(ic, a, "claim", "reported_date", "ic-cm-rep", "YYYY-MM-DD")), field("Amount claimed", "ic-cm-amt", text(ic, a, "claim", "claimed_amount", "ic-cm-amt")), field("Insurer's claim number (optional)", "ic-cm-num", text(ic, a, "claim", "claim_number", "ic-cm-num"))),
      field("What happened", "ic-cm-desc", area(ic, a, "claim", "description", "ic-cm-desc")), formError(ic, "claim"), btn("Record claim", "ic-cm-save", () => a.addClaim(p.id), "primary", ic.busy)) : null,
    canCancel(p, role) ? h("div", {}, h("h4", {}, "Cancel this policy"), noteBox(ic, a, `cancel-${p.id}`, "Reason (at least 10 characters)", "ic-cancel-note"), btn("Cancel policy", "ic-cancel-save", () => a.cancelPolicy(p.id), "secondary", ic.busy)) : null,
    h("div", {}, h("h4", {}, "History"), hist(p.history)));
}

function claims(ic, role, me, a) {
  const s = ic.sel.claim;
  return h("div", {},
    card("Claims", "ic-claims", ic.claims.length ? ic.claims.map((x) => h("div", { className: "card", style: "margin-bottom:8px;", "data-claim": x.ref },
      h("div", {}, h("strong", {}, `${x.ref} · ${x.policy_ref}`), " ", St(x.status)),
      h("div", { style: "color: var(--ink-500);" }, `${x.description} · lost on ${x.loss_date} · claimed ${x.currency} ${x.claimed_amount}`),
      x.settled_amount ? h("div", {}, `Settled ${x.currency} ${x.settled_amount}; received ${x.received}; still to receive ${x.outstanding}`) : null,
      btn(s && s.id === x.id ? "Hide details" : "Details", `ic-cl-open-${x.ref}`, () => a.selectClaim(s && s.id === x.id ? null : x.id), "secondary", ic.busy))) : none("No claims yet. Claims are recorded from a policy.")),
    s ? claimDetail(ic, role, me, a, s) : null);
}

function claimDetail(ic, role, me, a, c) {
  const decide = (c.proposals || []).filter((q) => q.status === "PENDING");
  return card(`${c.ref} · ${c.policy_ref}`, "ic-claim-detail",
    h("div", {}, c.description, c.claim_number ? ` (insurer's claim number ${c.claim_number})` : ""),
    c.status === "SETTLED" ? h("div", { id: "ic-settled" }, `Settled for ${c.currency} ${c.settled_amount}. Received ${c.received}. Still to receive ${c.outstanding}.`) : null,
    c.status === "DECLINED" ? h("div", { id: "ic-declined" }, "The insurer's decline was recorded and approved.") : null,
    h("div", { id: "ic-proposals" }, h("h4", {}, "Proposed outcomes"), (c.proposals || []).length ? c.proposals.map((q) => h("div", { "data-proposal": String(q.no) },
      `#${q.no} ${q.outcome === "SETTLE" ? `Settle for ${c.currency} ${q.amount}` : "Decline"}: ${q.note}. `, St(q.status), q.decision_note ? ` Decision note: ${q.decision_note}` : "",
      canDecideOutcome(q, role, me) ? h("div", {}, noteBox(ic, a, `pr-${c.id}-${q.no}`, "Note (approval: optional, at least 10 characters if given; rejection: required)", `ic-pr-${q.no}-note`),
        btn("Approve", `ic-pr-${q.no}-approve`, () => a.approveOutcome(c.id, q.no), "primary", ic.busy), " ", btn("Reject", `ic-pr-${q.no}-reject`, () => a.rejectOutcome(c.id, q.no), "secondary", ic.busy)) :
        (q.status === "PENDING" && canApprove(role) ? h("p", { id: `ic-pr-${q.no}-waiting`, style: "color: var(--ink-500);" }, ownWorkText) : null))) : none("None yet.")),
    canPropose(c, role) ? h("div", {}, h("h4", {}, "Propose the insurer's outcome"),
      row(field("Outcome", "ic-oc-kind", sel(ic, a, "outcome", "outcome", "ic-oc-kind", [["SETTLE", "Settled"], ["DECLINE", "Declined"]])), ic.forms.outcome.outcome === "SETTLE" ? field("Settled amount", "ic-oc-amt", text(ic, a, "outcome", "amount", "ic-oc-amt")) : null),
      field("Note on the insurer's decision", "ic-oc-note", area(ic, a, "outcome", "note", "ic-oc-note")), formError(ic, "outcome"), btn("Propose outcome", "ic-oc-save", () => a.proposeOutcome(c.id, c.claimed_amount), "primary", ic.busy)) : null,
    h("div", { id: "ic-receipts" }, h("h4", {}, "Money received"), (c.receipts || []).length ? c.receipts.map((r) => h("div", { "data-receipt": String(r.no) }, `${r.received_on}: ${c.currency} ${r.amount} (${r.reference})`)) : none("None recorded.")),
    canReceive(c, role) ? h("div", {}, h("h4", {}, "Record money received"),
      row(field("Amount", "ic-rc-amt", text(ic, a, "receipt", "amount", "ic-rc-amt")), field("Date received", "ic-rc-date", text(ic, a, "receipt", "received_on", "ic-rc-date", "YYYY-MM-DD")), field("Payment reference", "ic-rc-ref", text(ic, a, "receipt", "reference", "ic-rc-ref"))),
      formError(ic, "receipt"), btn("Record receipt", "ic-rc-save", () => a.recordReceipt(c.id, c.outstanding), "primary", ic.busy)) : null,
    h("div", {}, h("h4", {}, "History"), hist(c.history)));
}
