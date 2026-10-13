import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState } from "../components/DataState.js";
import { PermissionGate } from "../components/PermissionGate.js";
import { PERMISSIONS, can } from "../lib/permissions.js";
import { linkStatus, gapStatus, basisText, linkSentence, nodeText, relationsFor, targetTypes, relationOf, linkActions, ACTION_TEXT, needsReason, canWaive, confirmedText, typeLabel } from "../lib/proofLinks.js";

/**
 * Proof Links: record, in one place, how a piece of evidence, a control, a finding, a fix, a case, a risk, a standard or an agent decision relate.
 * A link is a claim somebody made. It is kept with its history, a second person can confirm it, and it does not make the claim true.
 */
const Badge = ({ tone, label }) => h("span", { className: `badge badge-${tone || "neutral"}` }, label);

export function ProofLinks({ pl, me, role, loading, onRetry, actions }) {
  return h("div", {},
    h("h1", {}, "Proof Links"),
    h("p", { style: "color: var(--ink-500); margin-top:-8px;" }, "Record how evidence, controls, findings, fixes, cases, risks, standards and agent decisions relate, and note where an expected link is missing."),
    pl.error ? ErrorState({ message: pl.error, onRetry }) : null,
    pl.notice ? h("div", { className: "alert alert-success", id: "pl-notice", role: "status", style: "margin-bottom:12px;" }, pl.notice) : null,
    loading ? LoadingState() : h("div", {}, finder(pl, actions), pl.graph ? neighbourhood(pl, me, role, actions) : null,
      PermissionGate({ role, permission: PERMISSIONS.GRC_PREPARE }, addCard(pl, actions)), h("p", { id: "pl-note", style: "color: var(--ink-500); font-size:0.9em;" }, pl.vocabulary ? pl.vocabulary.note : "")));
}

const typeSelect = (pl, id, value, onChange, types) => h("select", { id, value, onChange: (e) => onChange(e.target.value) }, [h("option", { value: "" }, "Choose a kind…"), ...(types || pl.vocabulary.types).map((t) => h("option", { value: t.code, selected: t.code === value }, t.label))]);
const recordSelect = (pl, id, type, value, onChange) => h("select", { id, value, disabled: !type, onChange: (e) => onChange(e.target.value) },
  [h("option", { value: "" }, type ? ((pl.choices[type] || []).length ? "Choose a record…" : "No records of this kind") : "Choose a kind first"), ...(pl.choices[type] || []).map((c) => h("option", { value: c.id, selected: c.id === value }, c.label))]);

function finder(pl, a) {
  const f = pl.find;
  return h("div", { className: "card", id: "pl-find", style: "margin-bottom:16px;" }, h("h3", {}, "Look at one record"),
    h("div", { className: "form-row", style: "display:flex;gap:8px;flex-wrap:wrap;" },
      typeSelect(pl, "pl-find-type", f.type, (v) => a.setFind("type", v)), recordSelect(pl, "pl-find-id", f.type, f.id, (v) => a.setFind("id", v)),
      h("select", { id: "pl-find-depth", onChange: (e) => a.setFind("depth", Number(e.target.value)) }, [1, 2, 3].map((d) => h("option", { value: d, selected: d === f.depth }, d === 1 ? "Directly linked" : `Up to ${d} steps away`))),
      h("button", { className: "btn btn-primary", id: "pl-find-go", disabled: !f.type || !f.id || pl.busy, onClick: () => a.look() }, "Show links")));
}

function neighbourhood(pl, me, role, a) {
  const g = pl.graph, v = pl.vocabulary, prep = can(role, PERMISSIONS.GRC_PREPARE), appr = can(role, PERMISSIONS.GRC_APPROVE);
  return h("div", { className: "card", id: "pl-graph", style: "margin-bottom:16px;" },
    h("h3", {}, `Links around ${nodeText(v, g.focus)}`),
    g.truncated ? h("p", { className: "alert alert-warning", id: "pl-truncated" }, "This picture was cut short because it has a lot of records. Narrow it by looking at a closer step.") : null,
    g.links.length === 0 ? h("p", { id: "pl-none" }, "No links are recorded for this record yet.") : h("ul", { id: "pl-links", style: "padding-left:0;list-style:none;" }, g.links.map((l) => linkRow(pl, l, me, prep, appr, a))),
    h("h4", {}, "Links that are expected but missing"),
    g.gaps.length === 0 ? h("p", { id: "pl-nogaps" }, "None recorded.") : h("ul", { id: "pl-gaps", style: "padding-left:0;list-style:none;" }, g.gaps.map((x) => gapRow(pl, x, me, appr, a))),
    PermissionGate({ role, permission: PERMISSIONS.GRC_PREPARE }, gapForm(pl, a)));
}

function linkRow(pl, l, me, prep, appr, a) {
  const st = linkStatus(l.status), acts = linkActions(l, me, prep, appr);
  return h("li", { "data-link": l.id, style: "border-bottom:1px solid var(--ink-200);padding:8px 0;" },
    h("div", {}, Badge(st), " ", linkSentence(pl.vocabulary, l)),
    h("div", { style: "color: var(--ink-500); font-size:0.9em;" }, `${basisText(l.basis)}. ${confirmedText(l)}${l.note ? ` Note: ${l.note}` : ""}`),
    acts.length ? h("div", { style: "margin-top:6px;" },
      acts.some(needsReason) ? h("input", { type: "text", id: `pl-reason-${l.id}`, placeholder: "Reason", value: pl.reasons[l.id] || "", onInput: (e) => a.setReason(l.id, e.target.value) }) : null,
      acts.map((k) => h("button", { className: "btn btn-secondary", "data-act": k, disabled: pl.busy, onClick: () => a.act(l.id, k) }, ACTION_TEXT[k]))) : null,
    h("details", {}, h("summary", {}, "History"), h("ol", {}, (l.history || []).map((x) => h("li", {}, `${x.event} by ${x.by}${x.note ? `: ${x.note}` : ""}`)))));
}

function gapRow(pl, x, me, appr, a) {
  const r = relationOf(pl.vocabulary, x.relation), st = gapStatus(x.status);
  return h("li", { "data-gap": x.id, style: "padding:6px 0;" }, Badge(st), " ", `${nodeText(pl.vocabulary, x.from)} should ${r ? r.label : x.relation}${x.expected_type ? ` a ${typeLabel(pl.vocabulary, x.expected_type).toLowerCase()}` : " something"}: ${x.note}`,
    canWaive(x, me, appr) ? h("span", {}, " ", h("input", { type: "text", id: `pl-reason-${x.id}`, placeholder: "Reason for waiving", value: pl.reasons[x.id] || "", onInput: (e) => a.setReason(x.id, e.target.value) }),
      h("button", { className: "btn btn-secondary", "data-act": "waive", disabled: pl.busy, onClick: () => a.waive(x.id) }, "Waive")) : null);
}

function gapForm(pl, a) {
  const f = pl.gap, focus = pl.graph.focus, rels = relationsFor(pl.vocabulary, focus.type, ""), rel = relationOf(pl.vocabulary, f.relation);
  return h("div", { id: "pl-gap-form", style: "margin-top:10px;" }, h("h4", {}, "Note a missing link"),
    h("select", { id: "pl-gap-relation", onChange: (e) => a.setGap("relation", e.target.value) }, [h("option", { value: "" }, "This record should…"), ...rels.map((r) => h("option", { value: r.code, selected: r.code === f.relation }, r.label))]),
    h("select", { id: "pl-gap-type", onChange: (e) => a.setGap("expected_type", e.target.value) }, [h("option", { value: "" }, "…something"), ...(rel ? rel.to : []).map((t) => h("option", { value: t, selected: t === f.expected_type }, typeLabel(pl.vocabulary, t)))]),
    h("input", { type: "text", id: "pl-gap-note", placeholder: "What is missing and why it matters", value: f.note, onInput: (e) => a.setGap("note", e.target.value) }),
    pl.gapError ? h("p", { className: "alert alert-error", id: "pl-gap-error" }, pl.gapError) : null,
    h("button", { className: "btn btn-secondary", id: "pl-gap-go", disabled: pl.busy, onClick: () => a.addGap() }, "Note it as missing"));
}

function addCard(pl, a) {
  const f = pl.form, v = pl.vocabulary, rels = relationsFor(v, f.from_type, f.to_type);
  return h("div", { className: "card", id: "pl-add", style: "margin-bottom:16px;" }, h("h3", {}, "Record a link"),
    h("div", { style: "display:flex;gap:8px;flex-wrap:wrap;" }, typeSelect(pl, "pl-from-type", f.from_type, (x) => a.setForm("from_type", x)), recordSelect(pl, "pl-from-id", f.from_type, f.from_id, (x) => a.setForm("from_id", x))),
    h("div", { style: "margin:8px 0;" }, h("select", { id: "pl-relation", onChange: (e) => a.setForm("relation", e.target.value) }, [h("option", { value: "" }, "…is related to the next record by…"), ...rels.map((r) => h("option", { value: r.code, selected: r.code === f.relation }, r.label))])),
    h("div", { style: "display:flex;gap:8px;flex-wrap:wrap;" }, typeSelect(pl, "pl-to-type", f.to_type, (x) => a.setForm("to_type", x), f.from_type ? targetTypes(v, f.from_type) : null), recordSelect(pl, "pl-to-id", f.to_type, f.to_id, (x) => a.setForm("to_id", x))),
    h("input", { type: "text", id: "pl-note-in", placeholder: "Why you believe this (optional)", value: f.note, style: "display:block;margin:8px 0;width:100%;", onInput: (e) => a.setForm("note", e.target.value) }),
    pl.formError ? h("p", { className: "alert alert-error", id: "pl-form-error" }, pl.formError) : null,
    h("button", { className: "btn btn-primary", id: "pl-add-go", disabled: pl.busy, onClick: () => a.addLink() }, "Record the link"),
    h("p", { style: "color: var(--ink-500); font-size:0.9em;" }, "A different person with approval rights can confirm it. A link is a claim, kept with its history. It does not make the claim true."));
}
