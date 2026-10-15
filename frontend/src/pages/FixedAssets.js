import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState } from "../components/DataState.js";
import { TABS, CATEGORY_TEXT, RESULT_TEXT, ATTENTION_TONE, canPrepare, canApprove, statusOf, words, who,
  canApproveAsset, canDispose, canDecideDisposal, canCount, canReviewCount, ownWorkText } from "../lib/fixedassets.js";

/**
 * Fixed assets. It records what people type in and does exact decimal arithmetic on it; it posts nothing to a ledger.
 * A different person approves an asset, approves a disposal and reviews a count.
 */
const Badge = ({ tone, label, id }) => h("span", { className: `badge badge-${tone || "neutral"}`, id }, label);
const St = (s) => Badge({ ...statusOf(s) });
const note = (t, kind = "info", id) => (t ? h("div", { className: `alert alert-${kind}`, id, style: "margin-bottom:12px;", role: kind === "error" ? "alert" : "status" }, t) : null);
const field = (l, id, inp, hint) => h("div", { className: "field" }, h("label", { for: id }, l), inp, hint ? h("small", { style: "color: var(--ink-500);" }, hint) : null);
const text = (fa, a, form, k, id, ph) => h("input", { id, type: "text", value: (fa.forms[form] || {})[k] == null ? "" : (fa.forms[form] || {})[k], placeholder: ph || "", onInput: (e) => a.setForm(form, k, e.target.value) });
const area = (fa, a, form, k, id) => h("textarea", { id, rows: 3, onInput: (e) => a.setForm(form, k, e.target.value) }, (fa.forms[form] || {})[k] || "");
const sel = (fa, a, form, k, id, opts, blank) => h("select", { id, onChange: (e) => a.setForm(form, k, e.target.value, true) },
  [...(blank ? [h("option", { value: "" }, blank)] : []), ...opts.map(([v, l]) => h("option", { value: v, selected: String((fa.forms[form] || {})[k]) === String(v) }, l))]);
const btn = (l, id, onClick, kind = "secondary", disabled = false) => h("button", { className: `btn btn-${kind}`, id, disabled, onClick }, l);
const row = (...b) => h("div", { style: "display:flex; gap:8px; flex-wrap:wrap; margin:8px 0; align-items:end;" }, b.filter(Boolean));
const none = (t = "None.") => h("div", { style: "color: var(--ink-500);" }, t);
const card = (title, id, ...kids) => h("div", { className: "card", id, style: "margin-bottom:16px;" }, h("h3", {}, title), ...kids);
const hist = (items) => h("ul", {}, (items || []).map((x) => h("li", {}, `${String(x.at).slice(0, 10)} ${String(x.event).replace(/_/g, " ").toLowerCase()} by ${x.by}${x.note ? ": " + x.note : ""}`)));
const noteBox = (fa, a, key, l, id) => field(l, id || `note-${key}`, h("textarea", { id: id || `note-${key}`, rows: 2, onInput: (e) => a.setNote(key, e.target.value) }, fa.notes[key] || ""));
const formError = (fa, name) => (fa.formError && fa.formError.form === name ? note(fa.formError.text, "error", `${name}-problem`) : null);
const docs = (fa, a, form, id) => field("Attach a document (optional)", id, sel(fa, a, form, "evidence_id", id, (fa.vault || []).map((e) => [e.id, e.original_filename || e.filename || e.id]), "No document"), "A document from the Evidence Vault. Its file fingerprint is kept.");
const fileList = (list) => (list && list.length ? h("div", { style: "font-size:0.9em; color: var(--ink-500);" }, list.map((e) => `${e.filename} (fingerprint ${String(e.file_hash).slice(0, 12)})`).join("; ")) : null);
const opt = (o) => Object.entries(o);

const money = (a, v) => `${a.currency} ${v}`;
export function FixedAssets({ fa, role, userId, loading, onRetry, actions: a }) {
  return h("div", {},
    h("h1", {}, "Fixed assets"),
    note("This workspace records assets that people type in and works out straight-line depreciation from the cost, residual value and life they typed. It posts nothing to a ledger, follows no accounting standard or tax rule, and cannot tell whether an asset exists. A different person approves an asset, approves a disposal and reviews a count.", "info", "fa-banner"),
    fa.error ? ErrorState({ message: fa.error, onRetry }) : null,
    note(fa.notice, "success", "fa-notice"),
    loading ? LoadingState() : h("div", {},
      h("div", { className: "tabs", role: "tablist", style: "display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px;" },
        TABS.map(([id, l]) => h("button", { className: `btn ${fa.tab === id ? "btn-primary" : "btn-secondary"}`, role: "tab", id: `fa-tab-${id}`, "aria-selected": fa.tab === id ? "true" : "false", onClick: () => a.setTab(id) }, l))),
      fa.busy ? h("div", { style: "color: var(--ink-500);" }, "Working...") : null,
      fa.tab === "overview" ? overview(fa, role, a) : assets(fa, role, userId, a)));
}

function overview(fa, role, a) {
  const o = fa.ov; if (!o) return none("Nothing loaded yet.");
  const c = o.counts;
  return h("div", {},
    card("What needs attention", "fa-attention", o.attention.length ? h("ul", {}, o.attention.map((x) => h("li", { "data-kind": x.kind }, Badge({ tone: ATTENTION_TONE[x.kind] || "info", label: words(x.kind) }), " ", `${x.count} ${x.text}`))) : none("Nothing needs attention.")),
    card("Totals for active assets, per currency", "fa-totals", o.totals.length ? h("ul", {}, o.totals.map((t) => h("li", { "data-currency": t.currency }, `${t.currency}: ${t.assets} asset(s), cost ${t.cost}, depreciation so far ${t.accumulated}, net book value ${t.net_book_value}`))) : none("No active assets yet."),
      h("p", { style: "color: var(--ink-500);" }, "Currencies are never added together.")),
    card("Counts", "fa-counts", h("ul", {}, [["Waiting for approval", c.proposed], ["Active", c.active], ["Disposal waiting", c.disposal_pending], ["Disposed of", c.disposed], ["Fully depreciated", c.fully_depreciated]].map(([l, n]) => h("li", {}, `${l}: ${n}`)))),
    policyCard(fa, role, a),
    card("What this does not do", "fa-limits", h("ul", {}, o.limitations.map((x) => h("li", {}, x)))));
}

function policyCard(fa, role, a) {
  const p = fa.ov.policy, f = fa.forms.policy;
  return card("Settings", "fa-policy", h("p", { id: "fa-policy-meaning" }, p.meaning),
    canApprove(role) && f ? h("div", {}, row(field("Days between physical counts", "fa-policy-days", text(fa, a, "policy", "count_days", "fa-policy-days"))),
      formError(fa, "policy"), btn("Save settings", "fa-policy-save", () => a.savePolicy(), "primary", fa.busy)) : h("p", { style: "color: var(--ink-500);" }, "Only an approver can change this setting."));
}

function assets(fa, role, me, a) {
  const sel_ = fa.sel.asset;
  return h("div", {},
    card("Assets", "fa-assets", fa.assets.length ? fa.assets.map((x) => h("div", { className: "card", style: "margin-bottom:8px;", "data-asset": x.ref },
      h("div", {}, h("strong", {}, `${x.ref} · ${x.name}`), " ", St(x.status), x.count_due ? [" ", Badge({ tone: "warn", label: "Count due" })] : null, x.missing ? [" ", Badge({ tone: "fail", label: "Missing" })] : null, x.fully_depreciated ? [" ", Badge({ tone: "neutral", label: "Fully depreciated" })] : null),
      h("div", { style: "color: var(--ink-500);" }, `${CATEGORY_TEXT[x.category] || x.category} · ${x.location} · custodian ${x.custodian_name} · acquired ${x.acquired_on} · proposed by ${who(x.proposed_by, me)}`),
      h("div", {}, `Cost ${money(x, x.cost)}; residual ${x.residual}; ${x.depreciates ? x.life_months + " months, " + x.monthly + " a month" : "not depreciated"}`),
      h("div", {}, `Depreciation to ${x.as_of}: ${x.accumulated}. Net book value: ${money(x, x.net_book_value)}`),
      x.status === "REJECTED" ? h("div", {}, `Rejected: ${x.decision_note}`) : null, fileList(x.evidence),
      canApproveAsset(x, role, me) ? h("div", {}, noteBox(fa, a, `asset-${x.id}`, "Note (approval: optional, at least 10 characters if given; rejection: required)", `fa-as-${x.ref}-note`),
        btn("Approve asset", `fa-as-${x.ref}-approve`, () => a.approveAsset(x.id), "primary", fa.busy), " ", btn("Reject asset", `fa-as-${x.ref}-reject`, () => a.rejectAsset(x.id), "secondary", fa.busy)) :
        (x.status === "PROPOSED" && canApprove(role) ? h("div", { style: "color: var(--ink-500);" }, ownWorkText("proposed this asset")) : null),
      x.status === "ACTIVE" || x.status === "DISPOSAL_PENDING" || x.status === "DISPOSED" ? btn(sel_ && sel_.id === x.id ? "Hide details" : "Details", `fa-as-open-${x.ref}`, () => a.selectAsset(sel_ && sel_.id === x.id ? null : x.id), "secondary", fa.busy) : null)) : none("No assets yet.")),
    sel_ ? detail(fa, role, me, a, sel_) : null,
    canPrepare(role) ? card("Propose an asset", "fa-asset-card",
      row(field("Name", "fa-as-name", text(fa, a, "asset", "name", "fa-as-name")), field("Category", "fa-as-cat", sel(fa, a, "asset", "category", "fa-as-cat", Object.entries(CATEGORY_TEXT))), field("Serial number (optional)", "fa-as-serial", text(fa, a, "asset", "serial_number", "fa-as-serial"))),
      row(field("Location", "fa-as-loc", text(fa, a, "asset", "location", "fa-as-loc")), field("Custodian", "fa-as-cust", text(fa, a, "asset", "custodian_name", "fa-as-cust")), field("Acquired on", "fa-as-date", text(fa, a, "asset", "acquired_on", "fa-as-date", "YYYY-MM-DD"))),
      row(field("Currency", "fa-as-cur", text(fa, a, "asset", "currency", "fa-as-cur", "NGN")), field("Cost", "fa-as-cost", text(fa, a, "asset", "cost", "fa-as-cost", "1500.00")), field("Residual value", "fa-as-res", text(fa, a, "asset", "residual_value", "fa-as-res", "0.00")),
        fa.forms.asset.category === "LAND" ? null : field("Useful life (months)", "fa-as-life", text(fa, a, "asset", "life_months", "fa-as-life"))),
      docs(fa, a, "asset", "fa-as-doc"), formError(fa, "asset"), btn("Propose asset", "fa-as-save", () => a.proposeAsset(), "primary", fa.busy)) : null);
}

function detail(fa, role, me, a, x) {
  const dec = canDecideDisposal(x, role, me);
  return card(`${x.ref} · ${x.name}`, "fa-asset-detail",
    x.life_months ? h("div", { id: "fa-schedule" }, h("h4", {}, "Depreciation schedule (next months)"), fa.schedule && fa.schedule.rows.length ? h("table", {}, h("tbody", {}, fa.schedule.rows.map((r) => h("tr", {}, h("td", {}, `Month ${r.month_no}`), h("td", {}, r.on), h("td", {}, `Depreciation ${r.accumulated}`), h("td", {}, `Net book value ${r.net_book_value}`))))) : none("No further depreciation.")) : null,
    x.disposal ? h("div", { id: "fa-disposal-info" }, h("h4", {}, "Disposal"), h("div", {}, `On ${x.disposal.disposed_on} for ${money(x, x.disposal.proceeds)}. Net book value then ${x.disposal.net_book_value}; ${Number(x.disposal.gain_or_loss.replace("-", "")) === 0 ? "no gain or loss" : (x.disposal.gain_or_loss.startsWith("-") ? "loss of " + x.disposal.gain_or_loss.slice(1) : "gain of " + x.disposal.gain_or_loss)}. ${x.disposal.reason}`),
      h("div", { style: "color: var(--ink-500);" }, `Arithmetic on the typed figures. Not posted to any ledger. Proposed by ${who(x.disposal.proposed_by, me)}.`)) : null,
    dec ? h("div", {}, noteBox(fa, a, `disposal-${x.id}`, "Note (approval: optional; rejection: required, at least 10 characters)", "fa-disposal-note"), btn("Approve disposal", "fa-disposal-approve", () => a.approveDisposal(x.id), "primary", fa.busy), " ", btn("Reject disposal", "fa-disposal-reject", () => a.rejectDisposal(x.id), "secondary", fa.busy)) :
      (x.status === "DISPOSAL_PENDING" && canApprove(role) ? h("p", { id: "fa-disposal-waiting" }, ownWorkText("proposed this disposal")) : null),
    canDispose(x, role) ? h("div", {}, h("h4", {}, "Propose a disposal"), row(field("Disposed on", "fa-dp-date", text(fa, a, "disposal", "disposed_on", "fa-dp-date", "YYYY-MM-DD")), field("Proceeds (0 if none)", "fa-dp-proceeds", text(fa, a, "disposal", "proceeds", "fa-dp-proceeds"))),
      field("Reason (at least 10 characters)", "fa-dp-reason", area(fa, a, "disposal", "reason", "fa-dp-reason")), formError(fa, "disposal"), btn("Propose disposal", "fa-dp-save", () => a.proposeDisposal(x.id), "primary", fa.busy)) : null,
    h("div", { id: "fa-counts-list" }, h("h4", {}, "Physical counts"), x.counts.length ? x.counts.map((c) => h("div", { "data-count": String(c.no) },
      `#${c.no} ${c.counted_on}: ${RESULT_TEXT[c.result] || c.result}. ${c.note} (by ${who(c.counted_by, me)}) `, St(c.status), c.review_note ? ` Reviewed by ${who(c.reviewed_by, me)}: ${c.review_note}` : "", fileList(c.evidence),
      canReviewCount(c, role, me) ? h("div", {}, noteBox(fa, a, `count-${x.id}-${c.no}`, "Review note (at least 10 characters)", `fa-ct-${c.no}-note`), btn("Review count", `fa-ct-${c.no}-review`, () => a.reviewCount(x.id, c.no), "primary", fa.busy)) :
        (c.status === "UNREVIEWED" && canApprove(role) ? h("div", { style: "color: var(--ink-500);" }, ownWorkText("recorded this count")) : null))) : none("No counts yet.")),
    canCount(x, role) ? h("div", {}, h("h4", {}, "Record a count"), row(field("Counted on", "fa-ct-date", text(fa, a, "count", "counted_on", "fa-ct-date", "YYYY-MM-DD")), field("Result", "fa-ct-result", sel(fa, a, "count", "result", "fa-ct-result", Object.entries(RESULT_TEXT)))),
      field("Note (at least 10 characters)", "fa-ct-note", area(fa, a, "count", "note", "fa-ct-note")), docs(fa, a, "count", "fa-ct-doc"), formError(fa, "count"), btn("Record count", "fa-ct-save", () => a.recordCount(x.id), "primary", fa.busy)) : null,
    h("div", {}, h("h4", {}, "History"), hist(x.history)));
}
