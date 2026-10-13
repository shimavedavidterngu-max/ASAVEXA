import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState } from "../components/DataState.js";
import { PermissionGate } from "../components/PermissionGate.js";
import { PERMISSIONS, can } from "../lib/permissions.js";
import { stateInfo, statusInfo, actionsFor, independentReviewNote } from "../lib/standardsRegistry.js";

/**
 * Standards Registry: where each accounting framework's official source is recorded, that a person approved it, and when it must be reviewed again.
 * "Verified" means a person approved the source. It does not mean the organisation complies, and it is not legal advice.
 */
const Badge = ({ tone, label, id }) => h("span", { className: `badge badge-${tone || "neutral"}`, id }, label);
const ACTION_LABEL = { submit: "Submit for review", approve: "Approve", "send-back": "Send back", withdraw: "Withdraw" };

export function StandardsRegistry({ sr, me, role, loading, onRetry, actions }) {
  return h("div", {},
    h("h1", {}, "Standards Registry"),
    h("p", { style: "color: var(--ink-500); margin-top:-8px;" }, "Record the official source for each framework you rely on. A second person must approve it, and it must be reviewed again by its review date."),
    sr.error ? ErrorState({ message: sr.error, onRetry }) : null,
    sr.notice ? h("div", { className: "alert alert-success", id: "sr-notice", role: "status", style: "margin-bottom:12px;" }, sr.notice) : null,
    loading ? LoadingState() : h("div", {}, coverageCard(sr), PermissionGate({ role, permission: PERMISSIONS.GRC_PREPARE }, addCard(sr, actions)), sourcesCard(sr, me, role, actions)));
}

function coverageCard(sr) {
  const c = sr.coverage;
  return h("div", { className: "card", id: "sr-coverage", style: "margin-bottom:16px;" },
    h("h3", {}, "Which frameworks are verified?"),
    !c ? h("p", {}, "Not loaded.") : h("div", {},
      h("table", { className: "table" }, h("thead", {}, h("tr", {}, ["Framework", "State", "Source", "Review by"].map((t) => h("th", {}, t)))),
        h("tbody", {}, c.frameworks.map((f) => { const i = stateInfo(f.state); return h("tr", { "data-framework": f.framework },
          h("td", {}, f.name), h("td", {}, Badge({ tone: i.tone, label: i.label })),
          h("td", {}, f.source ? h("a", { href: f.source.url, target: "_blank", rel: "noopener noreferrer" }, `${f.source.title} (${f.source.version})`) : "None recorded"),
          h("td", {}, f.source ? f.source.review_by : "—")); }))),
      h("p", { style: "color: var(--ink-500); font-size:0.9em;", id: "sr-note" }, c.note)));
}

function addCard(sr, a) {
  const f = sr.form, set = (k) => (e) => a.setForm(k, e.target.value);
  const field = (k, label, type = "text", ph = "") => h("div", { className: "field" }, h("label", { for: `sr-${k}` }, label), h("input", { id: `sr-${k}`, type, value: f[k] || "", placeholder: ph, onInput: set(k) }));
  const fw = (sr.frameworks || []);
  return h("div", { className: "card", id: "sr-add", style: "margin-bottom:16px;" },
    h("h3", {}, "Add a source"),
    h("div", { style: "display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px;" },
      h("div", { className: "field" }, h("label", { for: "sr-framework" }, "Framework"), h("select", { id: "sr-framework", onChange: set("framework") }, [h("option", { value: "" }, "Choose a framework"), ...fw.map((x) => h("option", { value: x.code, selected: f.framework === x.code }, x.name))])),
      h("div", { className: "field" }, h("label", { for: "sr-jurisdiction" }, "Jurisdiction (blank = international)"), h("select", { id: "sr-jurisdiction", onChange: set("jurisdiction") }, [h("option", { value: "" }, "International"), ...(sr.jurisdictions || []).map((x) => h("option", { value: x.code, selected: f.jurisdiction === x.code }, x.name))])),
      field("title", "Title"), field("url", "Official source link", "url", "https://"), field("authority", "Issued by"), field("version", "Version"),
      field("effective_from", "Effective from", "text", "2026-01-01"), field("review_by", "Review by", "text", "2027-01-01"), field("summary", "Notes (optional)")),
    sr.formError ? h("div", { className: "alert alert-error", id: "sr-form-error", role: "alert" }, sr.formError) : null,
    h("button", { className: "btn btn-primary", id: "sr-add-go", disabled: sr.busy, onClick: () => a.add() }, "Add as draft"));
}

function sourcesCard(sr, me, role, a) {
  const list = sr.sources || [];
  return h("div", { className: "card", id: "sr-sources" },
    h("h3", {}, "Sources"),
    list.length === 0 ? h("p", { id: "sr-none", style: "color: var(--ink-500);" }, "No sources recorded yet.") : list.map((s) => {
      const st = statusInfo(s.status), acts = actionsFor(s, me, can(role, PERMISSIONS.GRC_PREPARE), can(role, PERMISSIONS.GRC_APPROVE)), form = sr.reasons[s.id] || "";
      return h("div", { className: "card", "data-source": s.id, "data-status": s.status, style: "margin-bottom:10px;" },
        h("div", { style: "display:flex; gap:8px; flex-wrap:wrap; align-items:center;" }, h("strong", {}, s.title), Badge({ tone: st.tone, label: st.label }), h("span", { style: "color: var(--ink-500);" }, `${s.framework}${s.jurisdiction ? " · " + s.jurisdiction : ""} · v${s.version} · ${s.authority}`)),
        h("div", {}, h("a", { href: s.url, target: "_blank", rel: "noopener noreferrer" }, s.url), h("span", { style: "color: var(--ink-500);" }, ` · effective ${s.effective_from} · review by ${s.review_by}`)),
        independentReviewNote(s, me) ? h("div", { className: "alert alert-warning", "data-sod": "1" }, independentReviewNote(s, me)) : null,
        acts.length ? h("div", { style: "margin-top:8px;" },
          acts.some((x) => x === "send-back" || x === "withdraw") ? h("input", { id: `sr-reason-${s.id}`, placeholder: "Reason (needed to send back or withdraw)", value: form, onInput: (e) => a.setReason(s.id, e.target.value), style: "width:100%; margin-bottom:6px;" }) : null,
          acts.map((x) => h("button", { className: x === "approve" || x === "submit" ? "btn btn-primary" : "btn btn-secondary", "data-act": x, disabled: sr.busy, style: "margin-right:6px;", onClick: () => a.act(s.id, x) }, ACTION_LABEL[x]))) : null,
        h("details", {}, h("summary", {}, "History"), h("ul", { style: "padding-left:18px;" }, (s.history || []).map((x) => h("li", {}, `${x.at.slice(0, 16).replace("T", " ")} · ${x.event}${x.note ? ": " + x.note : ""}`)))));
    }));
}

