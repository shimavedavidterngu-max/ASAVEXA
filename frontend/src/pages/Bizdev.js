import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState, EmptyState } from "../components/DataState.js";
import { TABS, OPEN_STAGES, ACTIVE_STAGES, ACTIVITY_TYPES, KINDS, FLAG_TEXT, canPrepare, canApprove, statusOf, money, oppMoves, proposalMoves, proposalPreview, reportMoves } from "../lib/bizdev.js";

/**
 * Business Development: accounts, a pipeline of opportunities, proposals, wins, targets and reports.
 * A large discount and every win are approved or confirmed by a second person, and the page says so. Probabilities are the organisation's own policy, so the forecast is an estimate.
 */
const Badge = ({ tone, label, id }) => h("span", { className: `badge badge-${tone || "neutral"}`, id }, label);
const St = (s, id) => Badge({ ...statusOf(s), id });
const note = (t, kind = "info") => (t ? h("div", { className: `alert alert-${kind}`, style: "margin-bottom:12px;", role: kind === "error" ? "alert" : "status" }, t) : null);
const field = (label, id, inp, hint) => h("div", { className: "field" }, h("label", { for: id }, label), inp, hint ? h("small", { style: "color: var(--ink-500);" }, hint) : null);
const text = (id, f, k, on, ph) => h("input", { id, type: "text", value: f[k] == null ? "" : f[k], placeholder: ph || "", onInput: (e) => on(k, e.target.value) });
const area = (id, f, k, on, rows = 2) => h("textarea", { id, rows, onInput: (e) => on(k, e.target.value) }, f[k] || "");
const sel = (id, value, on, opts, blank) => h("select", { id, onChange: (e) => on(e.target.value) }, [...(blank ? [h("option", { value: "" }, blank)] : []), ...opts.map(([v, l]) => h("option", { value: v, selected: String(value) === String(v) }, l))]);
const table = (head, rows, id) => h("div", { className: "table-scroll" }, h("table", { className: "data-table", id }, h("thead", {}, h("tr", {}, head.map(([l, right]) => h("th", { style: right ? "text-align:right;" : undefined }, l)))), h("tbody", {}, rows)));
const td = (v, right) => h("td", { style: right ? "text-align:right;" : undefined }, v);
const btn = (label, id, onClick, kind = "secondary", disabled = false) => h("button", { className: `btn btn-${kind}`, id, disabled, onClick }, label);
const row = (...b) => h("div", { style: "display:flex; gap:8px; flex-wrap:wrap; margin:8px 0;" }, b.filter(Boolean));
const none = (t = "None.") => h("div", { style: "color: var(--ink-500);" }, t);
const noteBox = (bd, key, a, label) => field(label, `note-${key}`, area(`note-${key}`, bd.notes, key, a.noteChange));
const hist = (items, id) => h("ul", { id }, (items || []).map((x) => h("li", {}, `${String(x.at).slice(0, 10)} ${String(x.event || `${x.from || "start"} to ${x.to}`).replace(/_/g, " ").toLowerCase()} by ${x.by}${x.note ? ": " + x.note : ""}`)));
const flags = (o) => (o.flags || []).map((f) => h("span", { className: "badge badge-warn", style: "margin-left:6px;", title: FLAG_TEXT[f] }, f === "OVERDUE" ? "Overdue" : "Stale"));

export function Bizdev({ bd, role, userId, loading, onRetry, actions }) {
  return h("div", {},
    h("h1", {}, "Business Development and Strategy"),
    note("Probabilities and the discount limit are your own policy settings, so the weighted forecast is an estimate, not a prediction. Currencies are never added together. A large discount and every win need a second person.", "warning"),
    bd.error ? ErrorState({ message: bd.error, onRetry }) : null,
    note(bd.notice, "success"),
    loading ? LoadingState() : h("div", {},
      h("div", { className: "tabs", role: "tablist", style: "display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px;" },
        TABS.map(([id, label]) => h("button", { className: `btn ${bd.tab === id ? "btn-primary" : "btn-secondary"}`, role: "tab", id: `bd-tab-${id}`, "aria-selected": bd.tab === id ? "true" : "false", onClick: () => actions.setTab(id) }, label))),
      bd.busy ? h("div", { style: "color: var(--ink-500);" }, "Working...") : null,
      bd.tab === "overview" ? overview(bd, role, actions) : bd.tab === "accounts" ? accounts(bd, role, actions) : bd.tab === "pipeline" ? pipeline(bd, role, userId, actions)
        : bd.tab === "targets" ? targets(bd, role, actions) : reports(bd, role, userId, actions)));
}

// ---------------------------------------------------------------- overview
function overview(bd, role, a) {
  const o = bd.ov;
  if (!o) return EmptyState({ title: "No data yet", message: "Add an account and an opportunity to begin." });
  const c = o.counts, p = bd.policyForm;
  const attention = bd.opps.filter((x) => (x.flags || []).length);
  return h("div", { id: "bd-overview" },
    h("div", { className: "card", style: "margin-bottom:12px;" }, h("h3", {}, "At a glance"),
      h("div", { id: "bd-counts" }, `${c.accounts} active account(s); ${c.opportunities} opportunit${c.opportunities === 1 ? "y" : "ies"}, ${c.open} open; ${c.proposals_pending} discount(s) waiting for approval; ${c.wins_pending} win(s) waiting for confirmation; ${c.reports} report(s).`)),
    o.currencies.length === 0 ? EmptyState({ title: "No opportunities yet", message: "Create an account, then an opportunity, to see the pipeline." }) : o.currencies.map((f) => h("div", { className: "card", style: "margin-bottom:12px;", id: `bd-cur-${f.currency}` },
      h("h3", {}, `Pipeline in ${f.currency}`),
      h("div", {}, `Open: ${f.open_count} deal(s) worth ${money(f.open_value)}. Weighted forecast: ${money(f.weighted)}. Won: ${f.won_count} worth ${money(f.won_value)}. Lost: ${f.lost_count} worth ${money(f.lost_value)}.`),
      h("div", { id: `bd-winrate-${f.currency}` }, f.win_rate_pct == null ? "Win rate: not enough closed deals yet." : `Win rate: ${f.win_rate_pct}% of closed deals by number, ${f.win_rate_value_pct}% by value.`),
      table([["Stage"], ["Deals", true], ["Value", true], ["Probability", true], ["Weighted", true]], f.stages.map((s) => h("tr", { "data-stage": `${f.currency}-${s.stage}` }, td(statusOf(s.stage).label), td(String(s.count), true), td(money(s.value), true), td(`${s.probability}%`, true), td(money(s.weighted), true)))))),
    h("div", { className: "card", style: "margin-bottom:12px;" }, h("h3", {}, "Targets"),
      o.targets.length ? table([["Target"], ["Period"], ["Goal", true], ["Won", true], ["Reached", true], ["Forecast", true]], o.targets.map((t) => h("tr", { "data-target": t.id }, td(`${t.ref} ${t.name}`), td(`${t.start} to ${t.end}`), td(`${t.currency} ${money(t.amount)}`, true), td(money(t.won), true), td(`${t.attainment_pct}%`, true), td(`${money(t.forecast)} (${t.forecast_pct}%)`, true)))) : none("No targets set.")),
    h("div", { className: "card", style: "margin-bottom:12px;" }, h("h3", {}, "Needs attention"),
      attention.length ? h("ul", { id: "bd-attention" }, attention.map((x) => h("li", {}, `${x.ref} ${x.title} (${x.account_name}): ${x.flags.map((f) => FLAG_TEXT[f].toLowerCase()).join("; ")}`))) : none()),
    h("div", { className: "card", style: "margin-bottom:12px;" }, h("h3", {}, "Policy"), h("div", { id: "bd-policy" }, o.policy.meaning),
      canApprove(role) && p ? h("div", { style: "margin-top:8px;" },
        field("Discount limit % (above this a second person approves)", "pol-disc", text("pol-disc", p, "discount_limit_pct", a.policyChange)), field("Days without activity before a deal is stale", "pol-stale", text("pol-stale", p, "stale_days", a.policyChange)),
        ACTIVE_STAGES.map((s) => field(`${statusOf(s).label} probability %`, `pol-p-${s}`, text(`pol-p-${s}`, p, `p_${s}`, a.policyChange))), btn("Save policy", "pol-save", () => a.savePolicy(), "primary", bd.busy)) : null),
    h("div", { className: "card" }, h("h3", {}, "What this does not tell you"), h("ul", {}, o.limitations.map((l) => h("li", {}, l)))));
}

// ---------------------------------------------------------------- accounts
function accounts(bd, role, a) {
  if (bd.accountForm) return accountFormView(bd, a);
  if (bd.account) return accountDetail(bd, role, a);
  return h("div", { id: "bd-accounts" }, canPrepare(role) ? btn("New account", "acc-new", () => a.newAccount(), "primary") : null,
    bd.accounts.length === 0 ? EmptyState({ title: "No accounts yet", message: "An account is a prospect, client or partner you want to sell to or work with." })
      : table([["Ref"], ["Name"], ["Kind"], ["Open deals", true], ["Won deals", true], ["Status"], [""]], bd.accounts.map((x) => h("tr", { "data-account": x.id }, td(x.ref), td(x.name), td(St(x.kind)), td(String(x.open_opportunities), true), td(String(x.won_opportunities), true), td(St(x.status)), td(btn("Open", `acc-open-${x.id}`, () => a.openAccount(x.id)))))));
}

function accountFormView(bd, a) {
  const f = bd.accountForm;
  return h("div", { className: "card", id: "account-form" }, h("h3", {}, f.id ? "Edit account" : "New account"),
    field("Name", "af-name", text("af-name", f, "name", a.accountChange)), field("Kind", "af-kind", sel("af-kind", f.kind, (v) => a.accountChange("kind", v), KINDS.map((k) => [k, statusOf(k).label]))),
    field("Sector", "af-sector", text("af-sector", f, "sector", a.accountChange)), field("Country", "af-country", text("af-country", f, "country", a.accountChange)), field("Notes", "af-notes", area("af-notes", f, "notes", a.accountChange)),
    h("h4", {}, "Main contact (personal data: enter only what you are allowed to hold)"), field("Name", "af-cname", text("af-cname", f, "contact_name", a.accountChange)), field("Role", "af-crole", text("af-crole", f, "contact_role", a.accountChange)),
    field("Email", "af-cemail", text("af-cemail", f, "contact_email", a.accountChange)), field("Phone", "af-cphone", text("af-cphone", f, "contact_phone", a.accountChange)),
    row(btn("Save account", "af-save", () => a.saveAccount(), "primary", bd.busy), btn("Cancel", "af-cancel", () => a.cancelAccount())));
}

function accountDetail(bd, role, a) {
  const x = bd.account;
  return h("div", { id: "account-detail" }, btn("Back to accounts", "acc-back", () => a.closeAccountView()),
    h("h2", {}, `${x.ref} ${x.name}`), h("div", {}, St(x.kind), " ", St(x.status)),
    h("div", { id: "account-info" }, [x.sector, x.country].filter(Boolean).join(", ") || "No sector or country recorded."), x.notes ? h("p", {}, x.notes) : null,
    h("h3", {}, "Contacts"), (x.contacts || []).length ? h("ul", {}, x.contacts.map((c) => h("li", {}, [c.name, c.role, c.email, c.phone].filter(Boolean).join(" · ")))) : none("No contact recorded."),
    row(canPrepare(role) && x.status === "ACTIVE" ? btn("Edit", "acc-edit", () => a.editAccount()) : null, canPrepare(role) && x.status === "ACTIVE" ? btn("New opportunity", "acc-newopp", () => a.newOpp(x.id), "primary") : null),
    h("h3", {}, "Opportunities"), x.opportunities.length ? table([["Ref"], ["Title"], ["Stage"], ["Value", true], [""]], x.opportunities.map((o) => h("tr", {}, td(o.ref), td(o.title), td(St(o.stage)), td(`${o.currency} ${money(o.value)}`, true), td(btn("Open", `acc-opp-${o.id}`, () => a.openOpp(o.id)))))) : none("No opportunities yet."),
    canPrepare(role) && x.status === "ACTIVE" ? h("div", { className: "card", style: "margin-top:12px;" }, h("h3", {}, "Archive this account"), noteBox(bd, "archive", a, "Why (required)"), btn("Archive", "acc-archive", () => a.archiveAccount(), "secondary", bd.busy)) : null,
    h("h3", {}, "History"), hist(x.history, "account-history"));
}

// ---------------------------------------------------------------- pipeline
function pipeline(bd, role, userId, a) {
  if (bd.oppForm) return oppFormView(bd, a);
  if (bd.opp) return oppDetail(bd, role, userId, a);
  const rows = bd.opps.filter((o) => !bd.stageFilter || o.stage === bd.stageFilter);
  return h("div", { id: "bd-pipeline" },
    row(canPrepare(role) ? btn("New opportunity", "opp-new", () => a.newOpp(""), "primary") : null),
    field("Show", "pl-stage", sel("pl-stage", bd.stageFilter, (v) => a.filterStage(v), ["LEAD", "QUALIFIED", "PROPOSAL", "NEGOTIATION", "WIN_PENDING", "WON", "LOST"].map((s) => [s, statusOf(s).label]), "All stages")),
    rows.length === 0 ? EmptyState({ title: "No opportunities", message: "Create an account first, then add an opportunity for it." })
      : table([["Ref"], ["Title"], ["Account"], ["Stage"], ["Value", true], ["Chance", true], ["Weighted", true], ["Expected close"], [""]], rows.map((o) => h("tr", { "data-opp": o.id }, td(o.ref), td([o.title, flags(o)]), td(o.account_name), td(St(o.stage)), td(`${o.currency} ${money(o.value)}`, true), td(`${o.probability}%`, true), td(money(o.weighted), true), td(o.expected_close), td(btn("Open", `opp-open-${o.id}`, () => a.openOpp(o.id)))))));
}

function oppFormView(bd, a) {
  const f = bd.oppForm, isNew = !f.id;
  return h("div", { className: "card", id: "opp-form" }, h("h3", {}, isNew ? "New opportunity" : "Edit opportunity"),
    isNew ? field("Account", "of-account", sel("of-account", f.account_id, (v) => a.oppChange("account_id", v), bd.options.accounts.map((x) => [x.id, `${x.ref} ${x.name}`]), "Choose an account")) : null,
    field("Title", "of-title", text("of-title", f, "title", a.oppChange)), field("Description", "of-desc", area("of-desc", f, "description", a.oppChange)), field("Where it came from", "of-source", text("of-source", f, "source", a.oppChange)),
    isNew ? field("Currency", "of-cur", text("of-cur", f, "currency", a.oppChange)) : null, field("Estimated value", "of-value", text("of-value", f, "value", a.oppChange)),
    field("Expected close date", "of-close", text("of-close", f, "expected_close", a.oppChange, "2026-06-30")),
    isNew ? field("Starts as", "of-stage", sel("of-stage", f.stage, (v) => a.oppChange("stage", v), [["LEAD", "Lead"], ["QUALIFIED", "Qualified"]])) : null,
    row(btn("Save", "of-save", () => a.saveOpp(), "primary", bd.busy), btn("Cancel", "of-cancel", () => a.cancelOpp())));
}

function oppDetail(bd, role, userId, a) {
  const o = bd.opp, m = oppMoves(o, role, userId);
  const accepted = o.proposals.find((p) => p.status === "ACCEPTED");
  return h("div", { id: "opp-detail" }, btn("Back to the pipeline", "opp-back", () => a.closeOppView()),
    h("h2", {}, `${o.ref} ${o.title}`),
    h("div", {}, St(o.stage, "opp-status"), flags(o)),
    h("div", { id: "opp-summary" }, `${o.account_name}. ${o.currency} ${money(o.value)}${o.probability != null ? `, ${o.probability}% chance, weighted ${money(o.weighted)}` : ""}. Expected close ${o.expected_close}.`),
    o.description ? h("p", {}, o.description) : null, o.lost_reason ? h("div", { id: "opp-lost-reason" }, `Lost because: ${o.lost_reason}`) : null, o.won_date ? h("div", { id: "opp-won" }, `Won on ${o.won_date}.`) : null,
    row(m.edit ? btn("Edit", "opp-edit", () => a.editOpp()) : null),
    m.move ? h("div", { className: "card", style: "margin:12px 0;" }, h("h3", {}, "Move the deal"),
      field("New stage", "mv-stage", sel("mv-stage", bd.moveTo, (v) => a.moveChange(v), OPEN_STAGES.filter((s) => s !== o.stage).map((s) => [s, statusOf(s).label]), "Choose a stage")),
      noteBox(bd, "move", a, "Note (required when moving backwards)"), h("small", {}, "Negotiation needs a proposal that has been sent to the client."), row(btn("Move", "mv-go", () => a.moveStage(), "secondary", bd.busy))) : null,
    h("h3", {}, "Proposals"), o.proposals.length === 0 ? none("No proposal yet.") : o.proposals.map((p) => proposalCard(bd, o, p, role, userId, a)),
    bd.proposalForm ? proposalFormView(bd, a) : (m.proposal ? row(btn("New proposal", "prop-new", () => a.newProposal(), "primary")) : null),
    (o.proposals.some((p) => p.status === "PENDING_APPROVAL" || p.status === "SENT")) && (m.proposal) ? h("div", { className: "card", style: "margin:12px 0;" }, noteBox(bd, "prop", a, "Note (required to send back, accept or decline)")) : null,
    h("h3", {}, "Win and loss"),
    m.requestWin ? h("div", { className: "card", id: "win-box", style: "margin:12px 0;" }, h("div", {}, `The client accepted proposal v${accepted.version} for ${o.currency} ${money(accepted.total)}.`), noteBox(bd, "win", a, "Note (optional)"),
      h("small", {}, "A different person must confirm the win before it counts toward targets."), row(btn("Ask for the win to be confirmed", "win-request", () => a.requestWin(), "primary", bd.busy))) : null,
    o.stage === "WIN_PENDING" ? h("div", { className: "card", id: "win-pending", style: "margin:12px 0;" }, h("div", {}, `Win waiting for confirmation (requested by ${o.win_requested_by}).`),
      m.ownWin ? h("div", { id: "win-own" }, "You asked for this win to be confirmed, so a different person must decide it.") : null,
      m.decideWin ? h("div", { id: "win-decide" }, noteBox(bd, "windecide", a, "Note (required to send back)"), row(btn("Confirm the win", "wd-approve", () => a.decideWin(true), "primary", bd.busy), btn("Send back", "wd-reject", () => a.decideWin(false), "secondary", bd.busy))) : null) : null,
    m.lost ? h("div", { className: "card", id: "lost-box", style: "margin:12px 0;" }, h("h3", {}, "Mark as lost"), noteBox(bd, "lost", a, "Why was it lost? (at least 10 characters)"), row(btn("Mark as lost", "lost-go", () => a.markLost(), "secondary", bd.busy))) : null,
    h("h3", {}, "Activity"), o.activities.length ? h("ul", { id: "opp-activities" }, [...o.activities].reverse().map((x) => h("li", {}, `${x.date} ${x.type.toLowerCase()}: ${x.summary}`))) : none("No activity yet."),
    bd.activityForm ? h("div", { className: "card", id: "activity-form" }, field("Kind", "ac-type", sel("ac-type", bd.activityForm.type, (v) => a.activityChange("type", v), ACTIVITY_TYPES.map((t) => [t, t.charAt(0) + t.slice(1).toLowerCase()]))),
      field("Date (blank = today)", "ac-date", text("ac-date", bd.activityForm, "date", a.activityChange, "2026-06-30")), field("What happened", "ac-summary", area("ac-summary", bd.activityForm, "summary", a.activityChange)),
      row(btn("Save activity", "ac-save", () => a.saveActivity(), "primary", bd.busy), btn("Cancel", "ac-cancel", () => a.cancelActivity()))) : (m.activity ? row(btn("Log an activity", "ac-new", () => a.newActivity())) : null),
    h("h3", {}, "History"), hist(o.stage_history, "opp-stages"), hist(o.history, "opp-history"));
}

function proposalCard(bd, o, p, role, userId, a) {
  const m = proposalMoves(p, o, role, userId);
  return h("div", { className: "card", "data-proposal": p.id, style: "margin:12px 0;" },
    h("div", {}, h("strong", {}, `Version ${p.version}`), " ", St(p.status)),
    table([["Item"], ["Qty", true], ["Unit price", true], ["Total", true]], p.items.map((i) => h("tr", {}, td(i.description), td(money(i.quantity), true), td(money(i.unit_price), true), td(money(i.total), true)))),
    h("div", { className: "prop-totals" }, `Subtotal ${p.currency} ${money(p.subtotal)}; discount ${p.discount_pct}% (${money(p.discount_amount)}); total ${p.currency} ${money(p.total)}. Valid until ${p.valid_until}.`),
    p.status === "PENDING_APPROVAL" ? h("div", { className: "prop-flag" }, `The discount of ${p.discount_pct}% is above the ${p.limit_at_submission}% limit, so a different person must approve it before it can be sent.`) : null,
    p.decision_note ? h("div", {}, `Note: ${p.decision_note}`) : null, (p.evidence || []).length ? h("div", {}, `Evidence: ${p.evidence.map((e) => e.filename).join(", ")}`) : null,
    m.own ? h("div", { className: "prop-own" }, "You submitted this proposal, so a different person must decide it.") : null,
    row(m.edit ? btn("Edit", `prop-edit-${p.id}`, () => a.editProposal(p)) : null, m.submit ? btn("Submit", `prop-submit-${p.id}`, () => a.submitProposal(p.id), "primary", bd.busy) : null,
      m.decide ? btn("Approve discount", `prop-approve-${p.id}`, () => a.decideProposal(p.id, true), "primary", bd.busy) : null, m.decide ? btn("Send back", `prop-reject-${p.id}`, () => a.decideProposal(p.id, false), "secondary", bd.busy) : null,
      m.send ? btn("Mark as sent to client", `prop-send-${p.id}`, () => a.sendProposal(p.id), "primary", bd.busy) : null,
      m.respond ? btn("Client accepted", `prop-accept-${p.id}`, () => a.acceptProposal(p.id), "primary", bd.busy) : null, m.respond ? btn("Client declined", `prop-decline-${p.id}`, () => a.declineProposal(p.id), "secondary", bd.busy) : null));
}

function proposalFormView(bd, a) {
  const f = bd.proposalForm, pv = proposalPreview(f);
  return h("div", { className: "card", id: "proposal-form", style: "margin:12px 0;" }, h("h3", {}, f.id ? "Edit proposal" : "New proposal"),
    table([["Item"], ["Qty", true], ["Unit price", true], [""]], f.items.map((it, i) => h("tr", {}, td(h("input", { id: `pp-d-${i}`, type: "text", value: it.description, onInput: (e) => a.itemChange(i, "description", e.target.value) })),
      td(h("input", { id: `pp-q-${i}`, type: "text", value: it.quantity, style: "max-width:80px; text-align:right;", onInput: (e) => a.itemChange(i, "quantity", e.target.value) }), true), td(h("input", { id: `pp-u-${i}`, type: "text", value: it.unit_price, style: "max-width:120px; text-align:right;", onInput: (e) => a.itemChange(i, "unit_price", e.target.value) }), true),
      td(f.items.length > 1 ? btn("Remove", `pp-rm-${i}`, () => a.removeItem(i)) : null)))),
    row(btn("Add a line", "pp-add", () => a.addItem())),
    field("Discount %", "pp-disc", text("pp-disc", f, "discount_pct", a.proposalChange)), field("Valid until", "pp-valid", text("pp-valid", f, "valid_until", a.proposalChange, "2026-06-30")), field("Terms", "pp-terms", area("pp-terms", f, "terms", a.proposalChange)),
    h("div", {}, h("strong", {}, "Evidence (for example a signed order form)"), (bd.vault || []).length === 0 ? none("Nothing in the Evidence Vault to link.") : bd.vault.map((e) => h("label", { style: "display:block;" }, h("input", { type: "checkbox", id: `pp-ev-${e.id}`, checked: (f.evidence_ids || []).includes(e.id), onChange: () => a.proposalEvidence(e.id) }), ` ${e.original_filename || e.filename || e.id}`))),
    h("div", { id: "pp-preview", style: "margin:8px 0;" }, pv ? `Preview: subtotal ${money(pv.subtotal)}, discount ${money(pv.discount)}, total ${money(pv.total)}. The server calculates the final figures.` : "Fill in every line to see a preview."),
    row(btn("Save draft", "pp-save", () => a.saveProposal(), "primary", bd.busy), btn("Cancel", "pp-cancel", () => a.cancelProposal())));
}

// ---------------------------------------------------------------- targets
function targets(bd, role, a) {
  return h("div", { id: "bd-targets" }, canApprove(role) && !bd.targetForm ? btn("New target", "tgt-new", () => a.newTarget(), "primary") : null,
    bd.targetForm ? h("div", { className: "card", id: "target-form" }, h("h3", {}, "New target"), field("Name", "tf-name", text("tf-name", bd.targetForm, "name", a.targetChange)), field("Starts", "tf-start", text("tf-start", bd.targetForm, "start", a.targetChange, "2026-01-01")),
      field("Ends", "tf-end", text("tf-end", bd.targetForm, "end", a.targetChange, "2026-12-31")), field("Currency", "tf-cur", text("tf-cur", bd.targetForm, "currency", a.targetChange)), field("Amount to win", "tf-amt", text("tf-amt", bd.targetForm, "amount", a.targetChange)),
      row(btn("Save target", "tf-save", () => a.saveTarget(), "primary", bd.busy), btn("Cancel", "tf-cancel", () => a.cancelTarget()))) : null,
    bd.targets.length === 0 ? EmptyState({ title: "No targets", message: "A target is an amount you aim to win in a period, in one currency." })
      : table([["Ref"], ["Name"], ["Period"], ["Goal", true], ["Won", true], ["Reached", true], ["Expected still to close", true], ["Forecast", true], ["Status"], [""]], bd.targets.map((t) => h("tr", { "data-target": t.id }, td(t.ref), td(t.name), td(`${t.start} to ${t.end}`), td(`${t.currency} ${money(t.amount)}`, true),
        td(money(t.won), true), td(`${t.attainment_pct}%`, true), td(money(t.weighted_expected), true), td(`${money(t.forecast)} (${t.forecast_pct}%)`, true), td(St(t.status)), td(canApprove(role) && t.status === "ACTIVE" ? btn("Retire", `tgt-retire-${t.id}`, () => a.retireTarget(t.id)) : null)))),
    canApprove(role) && bd.targets.some((t) => t.status === "ACTIVE") ? h("div", { className: "card", style: "margin-top:12px;" }, noteBox(bd, "retire", a, "Reason for retiring a target (required)")) : null);
}

// ---------------------------------------------------------------- reports
function reports(bd, role, userId, a) {
  if (bd.reportForm) return h("div", { className: "card", id: "report-form" }, h("h3", {}, "New pipeline report"), field("Currency", "rp-cur", sel("rp-cur", bd.reportForm.currency, (v) => a.reportChange("currency", v), (bd.ov ? bd.ov.currencies : []).map((c) => [c.currency, c.currency]), "Choose a currency")),
    field("Title", "rp-title", text("rp-title", bd.reportForm, "title", a.reportChange)), row(btn("Create", "rp-save", () => a.saveReport(), "primary", bd.busy), btn("Cancel", "rp-cancel", () => a.cancelReport())));
  if (bd.report) return reportDetail(bd, role, userId, a);
  return h("div", { id: "bd-reports" }, canPrepare(role) ? btn("New report", "rep-new", () => a.newReport(), "primary") : null,
    bd.reports.length === 0 ? EmptyState({ title: "No reports", message: "A report freezes the pipeline at one moment so a second person can approve it." })
      : table([["Ref"], ["Title"], ["Currency"], ["Version", true], ["Status"], [""]], bd.reports.map((r) => h("tr", { "data-report": r.id }, td(r.ref), td(r.title), td(r.currency), td(String(r.version), true), td(St(r.status)), td(btn("Open", `rep-open-${r.id}`, () => a.openReport(r.id)))))));
}

function reportDetail(bd, role, userId, a) {
  const r = bd.report, m = reportMoves(r, role, userId), s = r.snapshot, f = s && s.figures;
  return h("div", { id: "report-detail" }, btn("Back to reports", "rep-back", () => a.closeReportView()), h("h2", {}, `${r.ref} ${r.title}`), h("div", {}, St(r.status, "rep-status")),
    h("small", {}, r.confidentiality),
    s ? h("div", { className: "card", style: "margin:12px 0;", id: "rep-frozen" }, h("div", {}, `Frozen ${String(s.generated_at).slice(0, 10)}, version ${r.version}. Fingerprint ${String(r.fingerprint).slice(0, 16)}...`),
      h("div", { id: "rep-figures" }, `Open ${money(f.open_value)}, weighted ${money(f.weighted)}, won ${f.won_count} (${money(f.won_value)}), lost ${f.lost_count} (${money(f.lost_value)}), win rate ${f.win_rate_pct == null ? "n/a" : f.win_rate_pct + "%"}.`),
      h("div", { id: "rep-counts" }, `${s.opportunities.length} opportunit${s.opportunities.length === 1 ? "y" : "ies"} and ${s.targets.length} target(s) in this report.`), h("ul", {}, s.limitations.map((l) => h("li", {}, l))))
      : note("Nothing is frozen yet. Submitting freezes the figures as they are at that moment.", "info"),
    row(m.submit ? btn("Freeze and submit for approval", "rep-submit", () => a.submitReport(), "primary", bd.busy) : null, m.exportable ? btn("Download CSV", "rep-export", () => a.exportReport(), "primary", bd.busy) : null),
    m.own ? h("div", { id: "rep-own" }, "You submitted this report, so a different person must decide it.") : null,
    m.decide ? h("div", { id: "rep-decide" }, noteBox(bd, "report", a, "Note (required to send back)"), row(btn("Approve", "rd-approve", () => a.decideReport(true), "primary", bd.busy), btn("Send back", "rd-reject", () => a.decideReport(false), "secondary", bd.busy))) : null,
    r.decision_note ? h("div", {}, `Decision note: ${r.decision_note}`) : null, h("h3", {}, "History"), hist(r.history, "rep-history"));
}
