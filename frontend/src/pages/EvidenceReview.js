import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState, EmptyState } from "../components/DataState.js";
import { PermissionGate } from "../components/PermissionGate.js";
import { PERMISSIONS } from "../lib/permissions.js";
import { REPORT_CHOICES, verdictInfo, issueText, linkText, caseStatus, problemRows, canOpenCase, nextStep, canVerify, gapCount, shortId } from "../lib/evidenceReview.js";

/**
 * Evidence Review: for one report figure, what is asserted, what supports it, what is missing, conflicting or stale, which links were made by a
 * person and which only inferred, what is still uncertain, and the action needed. From a review a person raises a case; someone plans the
 * action, someone does it, and a DIFFERENT person re-measures and verifies it. The server does all checking; this page only shows it.
 */
const Badge = ({ tone, label, id }) => h("span", { className: `badge badge-${tone || "neutral"}`, id }, label);
const Stat = (k, v) => h("div", { className: "card", style: "padding:8px 12px; min-width:110px;" }, h("div", { style: "color: var(--ink-500);" }, k), h("strong", {}, String(v)));

export function EvidenceReview({ er, periods, me, role, loading, onRetry, actions }) {
  return h("div", {},
    h("h1", {}, "Evidence Review"),
    h("p", { style: "color: var(--ink-500); margin-top:-8px;" }, "Check whether the records really support a reported figure. If they do not, raise a case, fix it, and have someone independent confirm the fix."),
    er.error ? ErrorState({ message: er.error, onRetry }) : null,
    er.notice ? h("div", { className: "alert alert-success", id: "er-notice", role: "status", style: "margin-bottom:12px;" }, er.notice) : null,
    loading ? LoadingState() : h("div", {}, reviewCard(er, periods || [], role, actions), casesCard(er, me, role, actions)));
}

function reviewCard(er, periods, role, a) {
  const r = er.review;
  return h("div", { className: "card", id: "er-review", style: "margin-bottom:16px;" },
    h("h3", {}, "Review a figure"),
    periods.length === 0 ? EmptyState({ title: "No accounting periods yet", message: "Open a period and post journals, then come back here." }) : h("div", {},
      h("div", { style: "display:flex; flex-wrap:wrap; gap:12px; align-items:flex-end;" },
        h("div", { className: "field" }, h("label", { for: "er-period" }, "Period"),
          h("select", { id: "er-period", onChange: (e) => a.setPeriod(e.target.value) }, [h("option", { value: "" }, "Choose a period"), ...periods.map((x) => h("option", { value: x.id, selected: er.period_id === x.id }, x.name))])),
        h("div", { className: "field" }, h("label", { for: "er-report" }, "Report"),
          h("select", { id: "er-report", onChange: (e) => a.setReport(e.target.value) }, REPORT_CHOICES.map(([v, l]) => h("option", { value: v, selected: er.report === v }, l)))),
        h("button", { className: "btn btn-primary", id: "er-run", disabled: !er.period_id || er.busy, onClick: () => a.run() }, er.busy ? "Checking…" : "Review the evidence")),
      r ? reviewBody(r, er, role, a) : h("p", { style: "color: var(--ink-500);" }, "Choose a period and press the button.")));
}

function reviewBody(r, er, role, a) {
  const info = verdictInfo(r.verdict), m = r.metrics, rows = problemRows(r);
  return h("div", { id: "er-result", style: "margin-top:16px;" },
    h("div", { style: "display:flex; gap:10px; align-items:center; flex-wrap:wrap;" }, Badge({ tone: info.tone, label: info.label, id: "er-verdict" }), h("span", { id: "er-assertion" }, r.assertion.statement)),
    h("div", { style: "display:flex; flex-wrap:wrap; gap:8px; margin:12px 0;", id: "er-metrics" },
      [["Journals", m.journals], ["With gaps", m.journals_with_gaps], ["Linked by a person", m.recorded_links], ["Matched by reference only", m.inferred_links], ["Figures that do not tie", m.tie_failures]].map(([k, v]) => Stat(k, v))),
    r.truncated ? h("div", { className: "alert alert-warning", role: "status" }, "This period has many journals, so only the first ones were reviewed. The counts cover only those.") : null,
    rows.length ? h("div", { id: "er-problems" }, h("h4", {}, "Missing, conflicting or stale"),
      h("ul", { style: "padding-left:18px;" }, rows.map((i) => h("li", { "data-journal": i.journal_id, style: "margin-bottom:6px;" },
        h("strong", {}, `${i.journal_number}`), " ", Badge({ tone: "fail", label: issueText(i.kind) }), h("span", {}, ` ${i.detail}`))))) : h("p", { id: "er-clean" }, "Every journal behind this figure has verified evidence of the expected kind."),
    (r.supporting || []).length ? h("div", { id: "er-supporting" }, h("h4", {}, "Supporting records"),
      h("ul", { style: "padding-left:18px;" }, r.supporting.map((s) => h("li", { "data-journal": s.journal_id, style: "margin-bottom:6px;" },
        h("strong", {}, s.journal_number), h("span", {}, ` ${s.description || ""} · ${s.evidence.type} ${s.evidence.filename} · ${s.evidence.status} · `), Badge({ tone: s.link.kind === "RECORDED" ? "pass" : "warn", label: linkText(s.link.kind) }))))) : null,
    (r.uncertain || []).length ? h("div", { id: "er-uncertain" }, h("h4", {}, "What is still uncertain"), h("ul", { style: "padding-left:18px;" }, r.uncertain.map((u) => h("li", {}, u)))) : null,
    (r.action_needed || []).length ? h("div", { id: "er-actions" }, h("h4", {}, "Action needed"), h("ul", { style: "padding-left:18px;" }, r.action_needed.map((x) => h("li", {}, h("strong", {}, `${x.journal_number}: `), x.text)))) : null,
    PermissionGate({ role, permission: PERMISSIONS.FINDING_MANAGE },
      canOpenCase(r, true, er.busy) ? h("button", { className: "btn btn-primary", id: "er-open-case", onClick: () => a.openCase() }, `Raise a case (${gapCount(r)} gap${gapCount(r) === 1 ? "" : "s"})`) : null),
    h("p", { style: "color: var(--ink-500); font-size:0.9em;", id: "er-limits" }, r.limits));
}

function casesCard(er, me, role, a) {
  const cases = er.cases || [];
  return h("div", { className: "card", id: "er-cases" },
    h("h3", {}, "Cases"),
    cases.length === 0 ? h("p", { style: "color: var(--ink-500);", id: "er-no-cases" }, "No cases yet. A case is raised from a review that finds gaps.") : h("div", {}, cases.map((c) => caseBlock(c, er, me, role, a))));
}

function caseBlock(c, er, me, role, a) {
  const st = caseStatus(c.status), open = er.openCase === c.id, f = (er.forms && er.forms[c.id]) || {};
  const input = (key, label, ph, area) => h("div", { className: "field" }, h("label", { for: `er-${key}-${c.id}` }, label),
    h(area ? "textarea" : "input", { id: `er-${key}-${c.id}`, value: f[key] || "", placeholder: ph || "", rows: area ? 2 : undefined, onInput: (e) => a.setForm(c.id, key, e.target.value) }));
  const members = er.members || [];
  return h("div", { className: "card", "data-case": c.id, style: "margin-bottom:10px;" },
    h("div", { style: "display:flex; justify-content:space-between; gap:8px; flex-wrap:wrap; align-items:center;" },
      h("div", {}, h("strong", {}, c.ref), " ", h("span", {}, c.title), " ", Badge({ tone: st.tone, label: st.label })),
      h("button", { className: "btn btn-secondary", "aria-expanded": open ? "true" : "false", onClick: () => a.toggleCase(c.id) }, open ? "Hide" : "Open")),
    h("div", { style: "color: var(--ink-500);" }, nextStep(c, me)),
    open ? h("div", { style: "margin-top:10px;" },
      h("div", { style: "display:flex; flex-wrap:wrap; gap:8px; margin-bottom:8px;" }, Stat("Gaps at the start", c.baseline.gaps), c.outcome ? Stat("Gaps after the fix", c.outcome.post_gaps) : null, c.owner ? Stat("Owner", c.owner === me ? "You" : shortId(c.owner)) : null),
      (c.attempts || []).length ? h("div", { className: "alert alert-warning", role: "status" }, `Verification was rejected ${c.attempts.length} time(s). Last result: ${c.attempts[c.attempts.length - 1].result}, ${c.attempts[c.attempts.length - 1].post_gaps} gap(s) remained.`) : null,
      c.outcome ? h("div", { className: "alert alert-success", "data-outcome": c.outcome.result }, h("strong", {}, `${c.outcome.result}: `), `${c.outcome.baseline_gaps} gap(s) before, ${c.outcome.post_gaps} after. Residual risk: ${c.outcome.residual_risk}. Reopen if: ${c.outcome.reopen_criteria}`) : null,
      (c.status === "OPEN" || c.status === "REOPENED") ? PermissionGate({ role, permission: PERMISSIONS.FINDING_MANAGE }, h("div", {},
        input("action", "What will be done", "e.g. Attach the signed lease and have it verified", true),
        h("div", { className: "field" }, h("label", { for: `er-owner-${c.id}` }, "Owner"),
          h("select", { id: `er-owner-${c.id}`, onChange: (e) => a.setForm(c.id, "owner", e.target.value) }, [h("option", { value: "" }, "Choose a person"), ...members.map((x) => h("option", { value: x.user_id, selected: f.owner === x.user_id }, `${x.user_id === me ? "You" : shortId(x.user_id)} · ${x.role}`))])),
        input("due_date", "Due date (optional)", "2026-12-31"),
        h("button", { className: "btn btn-primary", "data-act": "plan", disabled: er.busy, onClick: () => a.plan(c.id) }, "Plan the action"))) : null,
      c.status === "ACTION_PLANNED" ? PermissionGate({ role, permission: PERMISSIONS.FINDING_REMEDIATE }, h("div", {},
        h("p", {}, h("strong", {}, "Planned: "), c.action),
        input("note", "What was done", "", true), input("evidence_ref", "Evidence reference (optional)", ""),
        h("button", { className: "btn btn-primary", "data-act": "complete", disabled: er.busy, onClick: () => a.complete(c.id) }, "Record it as done"))) : null,
      c.status === "ACTION_DONE" ? h("div", {},
        h("p", {}, h("strong", {}, "Done: "), c.completion_note),
        canVerify(c, me, true) ? PermissionGate({ role, permission: PERMISSIONS.FINDING_VERIFY }, h("div", {},
          input("residual_risk", "Residual risk that remains", "", true), input("reopen_criteria", "Reopen this case if…", "", true), input("vnote", "Note (optional)", ""),
          h("button", { className: "btn btn-primary", "data-act": "verify", disabled: er.busy, onClick: () => a.verify(c.id) }, "Re-measure and verify"))) : h("p", { className: "alert alert-warning", "data-sod": "1" }, "Only someone who did not do or own this work can verify it."),) : null,
      c.status === "VERIFIED" ? PermissionGate({ role, permission: PERMISSIONS.FINDING_VERIFY }, h("button", { className: "btn btn-secondary", "data-act": "recheck", disabled: er.busy, onClick: () => a.recheck(c.id) }, "Re-check now")) : null,
      h("details", {}, h("summary", {}, "History"), h("ul", { style: "padding-left:18px;" }, (c.history || []).map((x) => h("li", {}, `${x.at.slice(0, 16).replace("T", " ")} · ${x.event}${x.note ? ": " + x.note : ""}`))))) : null);
}
