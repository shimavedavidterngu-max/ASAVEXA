import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState, EmptyState } from "../components/DataState.js";
import { SCOPE_TEXT, STATUS_TONE, typeText, grantLine, roleLine, canOpen, canChange, canEnd, daysLeft, mapCounts } from "../lib/network.js";

/**
 * ASAVEXA Network: a business connected to its accountants, auditors, banks, investors, donors and regulators.
 * The business decides what each connection can see; both sides agree with a one-time code; either side can end it; everything is logged.
 * The server enforces all of that. This page only shows it plainly and never offers an action the person's organisation cannot take.
 */
export const TABS = [["connections", "Connections"], ["connect", "Connect"], ["invites", "Invitations"], ["profile", "Our profile"]];
const Badge = ({ tone, label, id }) => h("span", { className: `badge badge-${tone || "neutral"}`, id }, label);
const when = (iso) => { if (!iso) return "—"; const d = new Date(iso); return Number.isNaN(d.getTime()) ? String(iso) : d.toISOString().slice(0, 10); };
const notice = (t) => (t ? h("div", { className: "alert alert-info", style: "margin-bottom:12px;", role: "status" }, t) : null);
const field = (label, id, input, hint) => h("div", { className: "field" }, h("label", { for: id }, label), input, hint ? h("small", { style: "color: var(--ink-500);" }, hint) : null);
const text = (id, f, k, a, ph, type = "text") => h("input", { id, type, value: f[k] == null ? "" : f[k], placeholder: ph || "", onInput: (e) => a.formChange(k, e.target.value) });
const select = (id, f, k, a, options, blank) => h("select", { id, onChange: (e) => a.formChange(k, e.target.value) }, [blank ? h("option", { value: "" }, blank) : null, ...options.map(([v, l]) => h("option", { value: v, selected: (f[k] || "") === v }, l))]);
const check = (id, label, on, fn, disabled) => h("label", { style: "display:block; margin:4px 0;" }, h("input", { id, type: "checkbox", checked: !!on, disabled: !!disabled, onChange: (e) => fn(e.target.checked) }), " ", label);

export function Network({ net, loading, onRetry, actions }) {
  const o = net.me, manage = !!(o && o.can_manage), needProfile = o && !o.profile;
  const tabs = TABS.filter(([id]) => manage || id === "connections");
  const tab = needProfile && manage ? "profile" : tabs.find(([id]) => id === net.tab) ? net.tab : "connections";
  return h("div", {},
    h("h1", {}, "ASAVEXA Network"),
    h("p", { style: "color: var(--ink-500); margin-top:-8px;" }, "Connect a business to its accountants, auditors, banks, investors, donors and regulators. The business decides what each one can see."),
    net.guide ? h("div", { className: "alert alert-info", id: "net-how" }, net.guide.how_it_works.join(" ")) : null,
    net.notice ? notice(net.notice) : null,
    net.error ? ErrorState({ message: net.error, onRetry }) : null,
    loading || !o ? LoadingState() : h("div", {},
      h("div", { className: "tabs", role: "tablist", style: "display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px;" },
        tabs.map(([id, label]) => h("button", { className: `btn ${id === tab && !net.view ? "btn-primary" : "btn-secondary"}`, role: "tab", id: `net-tab-${id}`, "aria-selected": id === tab && !net.view ? "true" : "false", disabled: needProfile && manage && id !== "profile", onClick: () => actions.setTab(id) }, label))),
      net.view ? viewPanel(net, actions) : h("div", {},
        tab === "connections" ? connectionsTab(net, actions) : null, tab === "connect" ? connectTab(net, actions) : null,
        tab === "invites" ? invitesTab(net, actions) : null, tab === "profile" ? profileTab(net, actions) : null)));
}

// ---------------------------------------------------------------- map + connections
function mapCard(o) {
  const counts = mapCounts(o.connections, o.types), me = o.profile ? o.profile.org_type : null;
  return h("div", { className: "card", id: "net-map" }, h("h3", {}, "Your network"),
    h("div", { style: "display:flex; flex-wrap:wrap; gap:8px;" }, Object.keys(o.types).map((t) => h("div", { className: "card", "data-type": t, style: `padding:8px 12px; min-width:120px; ${t === me ? "outline:2px solid var(--accent, #0f5c4d);" : ""}` },
      h("strong", {}, typeText(t, o.types)), h("div", { style: "color: var(--ink-500);" }, t === me ? "This is you" : `${counts[t]} connected`)))));
}

function connectionCard(c, net, a) {
  const f = net.form && net.form.kind === "end" && net.form.f.id === c.id ? net.form : null;
  const ed = net.form && net.form.kind === "grant" && net.form.f.id === c.id ? net.form.f : null;
  return h("div", { className: "card", "data-conn": c.id, style: "margin-bottom:12px;" },
    h("div", { style: "display:flex; justify-content:space-between; gap:8px; flex-wrap:wrap;" }, h("h3", { style: "margin:0;" }, c.counterparty.name),
      h("div", {}, Badge({ tone: "neutral", label: typeText(c.counterparty.type, net.me.types) }), " ", Badge({ tone: STATUS_TONE[c.status], label: c.status.charAt(0) + c.status.slice(1).toLowerCase(), id: `conn-status-${c.id}` }))),
    h("p", { style: "margin:6px 0;" }, `${roleLine(c)}. Purpose: ${c.purpose}.`),
    h("p", { style: "color: var(--ink-500); margin:0;", id: `conn-grant-${c.id}` }, grantLine(c.grant)),
    h("p", { style: "color: var(--ink-500);" }, c.status === "ACTIVE" ? `Ends ${when(c.expires_at)} (${daysLeft(c)} days left).${c.role === "PROVIDER" ? ` Opened ${c.views} time${c.views === 1 ? "" : "s"}${c.last_viewed_at ? `, last on ${when(c.last_viewed_at)}` : ""}.` : ""}` : `Ended or expired ${when(c.expires_at)}.`),
    h("div", {}, canOpen(c) ? h("button", { className: "btn btn-primary", id: `open-${c.id}`, disabled: net.busy, onClick: () => a.openView(c.id) }, "Open their information") : null, " ",
      canChange(c) && net.me.can_manage ? h("button", { className: "btn btn-secondary", id: `change-${c.id}`, onClick: () => a.startGrant(c) }, "Change what they can see") : null, " ",
      c.role === "PROVIDER" && net.me.can_manage ? h("button", { className: "btn btn-secondary", id: `log-${c.id}`, onClick: () => a.loadLog(c.id) }, "Who opened it") : null, " ",
      canEnd(c) && net.me.can_manage ? h("button", { className: "btn btn-secondary", id: `end-${c.id}`, onClick: () => a.startEnd(c.id) }, "End connection") : null),
    ed ? h("div", { className: "card", id: "grant-form", style: "margin-top:8px;" }, h("h4", {}, "What they can see"),
      Object.keys(SCOPE_TEXT).map((s) => check(`g-${s}`, SCOPE_TEXT[s], ed.scopes.includes(s), (on) => a.toggleScope(s, on))),
      check("g-detail", "Include line-level detail (individual transactions and team e-mail addresses)", ed.include_detail, (on) => a.formChange("include_detail", on)),
      check("g-closed", "Finished periods only", ed.closed_periods_only, (on) => a.formChange("closed_periods_only", on)),
      field("Extend the connection by (days, optional)", "g-extend", text("g-extend", ed, "extend_days", a, "")),
      h("button", { className: "btn btn-primary", id: "grant-save", disabled: net.busy, onClick: a.saveGrant }, "Save"), " ", h("button", { className: "btn btn-secondary", onClick: a.cancelForm }, "Cancel")) : null,
    f ? h("div", { className: "card", id: "end-form", style: "margin-top:8px;" }, field("Why are you ending it?", "end-reason", text("end-reason", f.f, "reason", a)),
      h("button", { className: "btn btn-primary", id: "end-confirm", disabled: net.busy, onClick: a.endConnection }, "End now"), " ", h("button", { className: "btn btn-secondary", onClick: a.cancelForm }, "Cancel")) : null,
    net.logFor === c.id ? h("div", { id: `access-log-${c.id}`, style: "margin-top:8px;" }, h("h4", {}, "Opened by"), (net.log || []).length === 0 ? h("p", {}, "Not opened yet.") :
      h("ul", {}, net.log.map((r) => h("li", {}, `${when(r.at)} — ${r.viewer}`)))) : null);
}

function connectionsTab(net, a) {
  const o = net.me, list = o.connections;
  return h("div", {}, mapCard(o), h("div", { id: "net-connections" }, list.length === 0 ? EmptyState({ title: "No connections yet", message: o.can_manage ? "Use Connect to invite someone or to answer an invitation code." : "An owner or administrator makes connections." }) : list.map((c) => connectionCard(c, net, a))));
}

// ---------------------------------------------------------------- connect
function grantEditor(f, a, readOnly) {
  return h("div", {}, h("p", { style: "margin:8px 0 4px;" }, h("strong", {}, "Information")), Object.keys(SCOPE_TEXT).map((s) => check(`scope-${s}`, SCOPE_TEXT[s], (f.scopes || []).includes(s), (on) => a.toggleScope(s, on), readOnly)),
    check("opt-detail", "Include line-level detail (individual transactions and team e-mail addresses)", f.include_detail, (on) => a.formChange("include_detail", on), readOnly),
    check("opt-closed", "Finished periods only", f.closed_periods_only, (on) => a.formChange("closed_periods_only", on), readOnly));
}

function connectTab(net, a) {
  const o = net.me, f = net.form && net.form.kind === "invite" ? net.form.f : null, pv = net.preview;
  const opts = o.can_offer_to.map((t) => [t, typeText(t, o.types)]);
  const isBiz = o.profile && o.profile.org_type === "BUSINESS";
  return h("div", {},
    net.created ? h("div", { className: "card", id: "invite-created" }, h("h3", {}, "Invitation created"), h("p", { style: "font-size:1.6rem; letter-spacing:2px;", id: "invite-code" }, net.created.code), h("p", {}, net.created.note),
      h("button", { className: "btn btn-secondary", id: "invite-done", onClick: a.dismissCreated }, "I have sent the code")) : null,
    h("div", { className: "card", id: "net-invite" }, h("h3", {}, isBiz ? "Offer your information to someone" : "Ask a business for its information"),
      h("p", {}, isBiz ? "You choose exactly what they can see. They enter the code you give them to accept." : "The business can share less than you ask for, never more. They enter the code you give them to answer."),
      f ? h("div", {}, field(isBiz ? "Who are you offering it to?" : "Who are you asking?", "inv-type", select("inv-type", f, "counterparty_type", a, opts, "Choose…")),
        field("What is it for?", "inv-purpose", text("inv-purpose", f, "purpose", a, "e.g. Statutory audit 2026")), grantEditor(f, a),
        field("From date (optional)", "inv-from", text("inv-from", f, "date_from", a, "", "date")), field("To date (optional)", "inv-to", text("inv-to", f, "date_to", a, "", "date")),
        field("Connection lasts (days)", "inv-conn-days", text("inv-conn-days", f, "connection_days", a, "")), field("Code works for (days)", "inv-days", text("inv-days", f, "invite_days", a, "")),
        field("Message for them (optional)", "inv-note", text("inv-note", f, "note", a)),
        h("button", { className: "btn btn-primary", id: "invite-save", disabled: net.busy, onClick: a.createInvite }, "Create invitation code"), " ", h("button", { className: "btn btn-secondary", onClick: a.cancelForm }, "Cancel"))
        : h("button", { className: "btn btn-primary", id: "invite-start", onClick: a.startInvite }, "Create an invitation")),
    h("div", { className: "card", id: "net-accept" }, h("h3", {}, "I have a code"),
      h("p", {}, "Enter the code another organisation gave you. You will see exactly what is being agreed before you agree."),
      field("Invitation code", "code-input", h("input", { id: "code-input", type: "text", value: net.code || "", placeholder: "ASX-XXXXX-XXXXX", onInput: (e) => a.setCode(e.target.value) })),
      h("button", { className: "btn btn-secondary", id: "code-preview", disabled: net.busy, onClick: a.previewCode }, "Look at this invitation"),
      pv ? h("div", { className: "card", id: "preview-card", style: "margin-top:8px;" }, h("h4", {}, `${pv.from.name} (${typeText(pv.from.type, o.types)})`),
        h("p", {}, pv.explain), h("p", {}, `Purpose: ${pv.purpose}. Connection would last up to ${pv.connection_days} days.`), pv.note ? h("p", {}, `Message: ${pv.note}`) : null,
        pv.you_decide ? h("div", {}, h("p", {}, h("strong", {}, "Choose what to share (you can tick fewer, never more):")),
          pv.grant.scopes.map((s) => check(`pv-${s}`, SCOPE_TEXT[s] || s, net.accept.scopes.includes(s), (on) => a.toggleAcceptScope(s, on))),
          pv.grant.include_detail ? check("pv-detail", "Include line-level detail", net.accept.detail, (on) => a.setAcceptDetail(on)) : null)
          : h("p", { id: "pv-grant" }, grantLine(pv.grant)),
        h("p", { style: "color: var(--ink-500);" }, pv.you_decide ? grantLine(pv.grant).replace(/^.*?\. /, "Requested: ") : ""),
        h("button", { className: "btn btn-primary", id: "accept-btn", disabled: net.busy || (pv.you_decide && net.accept.scopes.length === 0), onClick: a.acceptCode }, pv.you_decide ? "Agree and connect" : "Accept and connect"), " ",
        h("button", { className: "btn btn-secondary", onClick: a.clearPreview }, "Not now")) : null));
}

// ---------------------------------------------------------------- invitations + profile
function invitesTab(net, a) {
  const list = net.invites || [];
  return h("div", { className: "card", id: "net-invites" }, h("h3", {}, "Invitations you have made"), list.length === 0 ? EmptyState({ title: "None yet", message: "Create one on the Connect tab." }) :
    h("div", { className: "table-scroll" }, h("table", {}, h("thead", {}, h("tr", {}, ["Created", "To", "Purpose", "Status", ""].map((c) => h("th", {}, c)))),
      h("tbody", {}, list.map((i) => h("tr", { "data-invite": i.id }, h("td", {}, when(i.created_at)), h("td", {}, typeText(i.counterparty_type, net.me.types)), h("td", {}, i.purpose), h("td", {}, Badge({ tone: STATUS_TONE[i.status], label: i.status.charAt(0) + i.status.slice(1).toLowerCase() })),
        h("td", {}, i.status === "PENDING" ? h("button", { className: "btn btn-secondary", "data-cancel": i.id, onClick: () => a.cancelInvite(i.id) }, "Cancel") : null)))))),
    h("p", { style: "color: var(--ink-500);" }, "Codes cannot be shown again after creation. If one is lost, cancel the invitation and make a new one."));
}

function profileTab(net, a) {
  const p = net.me.profile, f = net.form && net.form.kind === "profile" ? net.form.f : { org_type: p ? p.org_type : "", display_name: p ? p.display_name : "", description: p ? p.description : "" };
  return h("div", { className: "card", id: "net-profile" }, h("h3", {}, p ? "Our profile" : "Tell the network who you are"),
    h("p", {}, "Other organisations see this name and kind when you connect. The kind decides who you can connect with, and cannot change while you have active connections."),
    field("What kind of organisation are you?", "np-type", select("np-type", f, "org_type", a, Object.entries(net.me.types), "Choose…")),
    field("Name shown to others", "np-name", text("np-name", f, "display_name", a)), field("About (optional)", "np-desc", text("np-desc", f, "description", a)),
    h("button", { className: "btn btn-primary", id: "np-save", disabled: net.busy, onClick: a.saveProfile }, "Save profile"));
}

// ---------------------------------------------------------------- what a connected organisation sees
function viewPanel(net, a) {
  const v = net.view, s = v.share;
  return h("div", { id: "net-view" },
    h("button", { className: "btn btn-secondary", id: "view-back", onClick: a.closeView }, "Back to connections"),
    h("div", { className: "card", style: "margin-top:12px;" }, h("h3", {}, `${s.organisation}`), h("p", {}, `Shared with ${s.viewer} for: ${s.purpose}. Taken ${when(s.taken_at)}. Connection ends ${when(s.expires_at)}.`),
      h("p", { style: "color: var(--ink-500);", id: "view-scope" }, `${s.scopes.map((x) => SCOPE_TEXT[x] || x).join("; ")}. ${s.include_detail ? "Includes line-level detail." : "Summary only."} ${s.closed_periods_only ? "Finished periods only." : ""} ${s.date_from} to ${s.date_to}.`),
      h("p", { id: "view-disclaimer" }, v.disclaimer), h("p", { style: "color: var(--ink-500);" }, `Fingerprint ${v.fingerprint.slice(0, 24)}…`)),
    Object.entries(v.sections).map(([k, body]) => h("div", { className: "card", "data-section": k, style: "margin-top:12px;" }, h("h3", {}, SCOPE_TEXT[k.toUpperCase()] || k), h("pre", { style: "white-space:pre-wrap; max-height:340px; overflow:auto;" }, JSON.stringify(body, null, 2)))));
}
