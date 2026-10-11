import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState, EmptyState } from "../components/DataState.js";
import { TABS, canPrepare, canApprove, stateOf, resultOf, SEVERITY_TEXT, num, itemActions, canClose } from "../lib/forensic.js";

/**
 * Forensic Accounting and Investigation. Analytics results are INDICATORS and are always worded that way. Findings are the investigator's reasoned conclusions,
 * approved by a second person. The page never accuses anyone; it shows what the ledger shows and what a person concluded.
 */
const Badge = ({ tone, label, id }) => h("span", { className: `badge badge-${tone || "neutral"}`, id }, label);
const note = (t, kind = "info") => (t ? h("div", { className: `alert alert-${kind}`, style: "margin-bottom:12px;", role: kind === "error" ? "alert" : "status" }, t) : null);
const field = (label, id, input, hint) => h("div", { className: "field" }, h("label", { for: id }, label), input, hint ? h("small", { style: "color: var(--ink-500);" }, hint) : null);
const input = (id, f, k, onChange, ph) => h("input", { id, type: "text", value: f[k] == null ? "" : f[k], placeholder: ph || "", onInput: (e) => onChange(k, e.target.value) });
const table = (head, rows, id) => h("div", { className: "table-scroll" }, h("table", { className: "data-table", id }, h("thead", {}, h("tr", {}, head.map(([l, right]) => h("th", { style: right ? "text-align:right;" : undefined }, l)))), h("tbody", {}, rows)));
const td = (v, right) => h("td", { style: right ? "text-align:right;" : undefined }, v);
const when = (iso) => String(iso || "").slice(0, 16).replace("T", " ");

export function Forensic({ fm, role, userId, loading, onRetry, actions }) {
  return h("div", {},
    h("h1", {}, "Forensic Accounting and Investigation"),
    note("Strictly confidential. Tests here flag indicators that deserve a human look; they are not proof of error, fraud or wrongdoing. Findings are a person's reasoned conclusions, approved by a second person. This is not legal advice.", "warning"),
    fm.error ? ErrorState({ message: fm.error, onRetry }) : null,
    note(fm.notice, "success"),
    loading ? LoadingState() : fm.case ? caseView(fm, role, userId, actions) : listView(fm, role, actions));
}

// ---------------------------------------------------------------- list
function listView(fm, role, a) {
  const prep = canPrepare(role), f = fm.caseForm;
  return h("div", { id: "fx-list" },
    prep && !f ? h("button", { className: "btn btn-primary", id: "case-new", onClick: () => a.newCase() }, "Open a case") : null,
    f ? h("div", { className: "card", id: "case-form", style: "margin:12px 0;" }, h("h3", {}, "Open a case"),
      field("Title", "cf-title", input("cf-title", f, "title", a.caseChange, "for example Review of January rent payments")),
      field("Type", "cf-type", h("select", { id: "cf-type", onChange: (e) => a.caseChange("case_type", e.target.value) }, Object.entries(fm.options.case_types).map(([k, v]) => h("option", { value: k, selected: f.case_type === k }, v)))),
      field("Why is this being looked at? (facts, not conclusions)", "cf-desc", h("textarea", { id: "cf-desc", rows: 3, onInput: (e) => a.caseChange("description", e.target.value) }, f.description)),
      h("button", { className: "btn btn-primary", id: "cf-save", disabled: fm.busy, onClick: () => a.saveCase() }, "Open case"), " ", h("button", { className: "btn btn-secondary", onClick: () => a.cancelCase() }, "Cancel")) : null,
    fm.cases.length === 0 ? EmptyState({ title: "No cases yet", message: "Open a case to keep evidence, run ledger tests and record findings for one matter." })
      : table([["Reference"], ["Title"], ["Type"], ["Status"], ["Findings", true], ["Opened by"], [""]], fm.cases.map((c) => h("tr", { "data-case": c.id }, td(c.reference), td(c.title), td(c.type_text), td(Badge({ tone: stateOf(c.status).tone, label: stateOf(c.status).label })),
        td(String(c.finding_count), true), td(c.opened_by), td(h("button", { className: "btn btn-secondary", id: `case-open-${c.id}`, onClick: () => a.openCase(c.id) }, "Open")))), "fx-case-table"));
}

// ---------------------------------------------------------------- case
function caseView(fm, role, userId, a) {
  const c = fm.case;
  return h("div", { id: "fx-case" },
    h("button", { className: "btn btn-secondary", id: "case-back", onClick: () => a.closeCaseView() }, "Back to cases"),
    h("h2", {}, `${c.reference}: ${c.title} `, Badge({ tone: stateOf(c.status).tone, label: stateOf(c.status).label, id: "case-status" })),
    h("div", { className: "tabs", role: "tablist", style: "display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px;" },
      TABS.map(([id, label]) => h("button", { className: `btn ${fm.tab === id ? "btn-primary" : "btn-secondary"}`, role: "tab", id: `fx-tab-${id}`, "aria-selected": fm.tab === id ? "true" : "false", onClick: () => a.setTab(id) }, label))),
    fm.busy ? h("div", { style: "color: var(--ink-500);" }, "Working...") : null,
    fm.tab === "overview" ? overview(fm, role, userId, a) : fm.tab === "evidence" ? evidence(fm, role, a) : fm.tab === "analytics" ? analytics(fm, role, a)
      : fm.tab === "findings" ? findings(fm, role, userId, a) : fm.tab === "reports" ? (fm.report ? reportDetail(fm, role, userId, a) : reports(fm, role, a)) : custody(fm, a));
}

function overview(fm, role, userId, a) {
  const c = fm.case;
  return h("div", { id: "fx-overview" },
    h("div", { className: "card", style: "margin-bottom:12px;" }, h("div", {}, h("strong", {}, c.type_text), `. Opened by ${c.opened_by} on ${when(c.opened_at)}.`), c.description ? h("p", {}, c.description) : null,
      c.status === "CLOSED" ? h("p", {}, `Closed by ${c.closed_by}: ${c.closure_note}`) : null,
      h("div", { style: "color: var(--ink-500);" }, `${c.evidence.length} evidence item(s), ${c.runs.length} analytics run(s), ${c.findings.length} finding(s), ${c.reports.length} report(s).`)),
    h("div", { className: "card", style: "margin-bottom:12px;" }, h("h3", {}, "Is the record intact?"), h("button", { className: "btn btn-secondary", id: "custody-verify", disabled: fm.busy, onClick: () => a.verifyCustody() }, "Check custody log and evidence"),
      fm.custodyCheck ? note(fm.custodyCheck.meaning, fm.custodyCheck.ok ? "success" : "error") : null),
    canClose(c, role, userId) ? h("div", { className: "card" }, h("h3", {}, "Close this case"), note("Only a different person from the one who opened the case can close it, and no finding may still be a draft or waiting for review.", "info"),
      field("Closing note", "case-close-note", h("input", { id: "case-close-note", type: "text", value: fm.closeNote, onInput: (e) => a.closeNoteChange(e.target.value) })), h("button", { className: "btn btn-secondary", id: "case-close", disabled: fm.busy, onClick: () => a.closeCase() }, "Close case")) : null);
}

function evidence(fm, role, a) {
  const c = fm.case, prep = canPrepare(role) && c.status === "OPEN", have = new Set(c.evidence.map((e) => e.evidence_id));
  return h("div", { id: "fx-evidence" },
    note("Evidence stays in the Evidence Vault. The case keeps a reference and the file's fingerprint (SHA-256) at the moment it was added, so any later change is detectable.", "info"),
    prep ? h("div", { className: "card", style: "margin-bottom:12px;" }, h("h3", {}, "Add evidence from the vault"),
      field("Evidence file", "ev-pick", h("select", { id: "ev-pick", onChange: (e) => a.evChange("id", e.target.value) }, [h("option", { value: "" }, "Choose a file"), ...fm.vault.filter((e) => !have.has(e.id)).map((e) => h("option", { value: e.id, selected: fm.ev.id === e.id }, `${e.original_filename} (${e.status.toLowerCase()})`))])),
      field("Why it matters (optional)", "ev-note", h("input", { id: "ev-note", type: "text", value: fm.ev.note, onInput: (e) => a.evChange("note", e.target.value) })), h("button", { className: "btn btn-primary", id: "ev-add", disabled: fm.busy, onClick: () => a.addEvidence() }, "Add to case")) : null,
    c.evidence.length === 0 ? EmptyState({ title: "No evidence in this case yet", message: "Upload documents on the Evidence page first, then add them here." })
      : table([["File"], ["Fingerprint when added (SHA-256)"], ["Added by"], ["When"], ["Note"]], c.evidence.map((e) => h("tr", { "data-evidence": e.evidence_id }, td(e.filename), td(h("code", {}, e.file_hash.slice(0, 20) + "...")), td(e.added_by), td(when(e.added_at)), td(e.note || ""))), "fx-evidence-table"));
}

function analytics(fm, role, a) {
  const f = fm.runForm, prep = canPrepare(role) && fm.case.status === "OPEN", o = fm.options, run = fm.run;
  return h("div", { id: "fx-analytics" },
    prep ? h("div", { className: "card", style: "margin-bottom:12px;" }, h("h3", {}, "Run tests on the posted ledger (read-only)"),
      h("div", { style: "display:flex; gap:12px; flex-wrap:wrap;" },
        field("What to examine", "rn-kind", h("select", { id: "rn-kind", onChange: (e) => a.runChange("scope_kind", e.target.value) }, [["period", "An accounting period"], ["dates", "A date range"]].map(([v, l]) => h("option", { value: v, selected: f.scope_kind === v }, l)))),
        f.scope_kind === "period" ? field("Period", "rn-period", h("select", { id: "rn-period", onChange: (e) => a.runChange("period_id", e.target.value) }, [h("option", { value: "" }, "Choose a period"), ...fm.periods.map((p) => h("option", { value: p.id, selected: f.period_id === p.id }, p.name))]))
          : [field("From", "rn-start", input("rn-start", f, "start", a.runChange, "2026-01-01")), field("To", "rn-end", input("rn-end", f, "end", a.runChange, "2026-12-31"))]),
      h("div", { className: "field" }, h("label", {}, "Tests"), Object.entries(o.tests).map(([k, v]) => h("label", { style: "display:block;" }, h("input", { type: "checkbox", id: `rn-t-${k}`, checked: f.tests.includes(k), onChange: (e) => a.runTest(k, e.target.checked) }), ` ${v}`))),
      h("details", {}, h("summary", {}, "Settings for the tests"),
        field("Approval limit (for 'just below')", "rn-limit", input("rn-limit", f, "approval_limit", a.runChange), "Needed only for that test."), field("Evidence expected above (for 'no evidence')", "rn-evid", input("rn-evid", f, "evidence_threshold", a.runChange), "Needed only for that test."),
        field("Round-number size", "rn-round", input("rn-round", f, "round_to", a.runChange)), field("Duplicate window (days)", "rn-dup", input("rn-dup", f, "duplicate_window_days", a.runChange)),
        field("Late posting after (days)", "rn-late", input("rn-late", f, "late_days", a.runChange)), field("Weekend days (0 = Monday ... 6 = Sunday)", "rn-wk", input("rn-wk", f, "weekend_days", a.runChange), "Differs by country, for example 4,5 in some places.")),
      h("button", { className: "btn btn-primary", id: "rn-run", disabled: fm.busy, onClick: () => a.runAnalytics() }, "Run tests")) : null,
    run ? runResult(fm, run, role, a) : null,
    fm.case.runs.length ? h("div", { className: "card" }, h("h3", {}, "Earlier runs"), table([["When"], ["Scope"], ["Journals", true], ["Tests worth a look", true], ["By"], [""]], fm.case.runs.map((r) => h("tr", {}, td(when(r.run_at)), td(r.scope.name || `${r.scope.start} to ${r.scope.end}`), td(String(r.journals_examined), true), td(`${r.indicator_count} of ${r.tests.length}`, true), td(r.run_by),
      td(h("button", { className: "btn btn-secondary", id: `run-open-${r.id}`, onClick: () => a.openRun(r.id) }, "Open")))), "fx-run-table")) : null);
}

function runResult(fm, run, role, a) {
  const prep = canPrepare(role) && fm.case.status === "OPEN";
  return h("div", { className: "card", id: "rn-result", style: "margin-bottom:12px;" },
    h("h3", {}, "Results: indicators only"), h("p", { style: "color: var(--ink-500);" }, `${run.journals_examined} posted journals examined. Fingerprint ${run.fingerprint.slice(0, 16)}...`),
    run.results.map((r) => h("div", { "data-test": r.id, style: "border-top:1px solid var(--line, #eee); padding:8px 0;" },
      h("div", {}, h("strong", {}, r.name), " ", Badge({ tone: resultOf(r.status).tone, label: resultOf(r.status).label })), h("div", {}, r.summary),
      r.detail && r.detail.digits ? table([["Digit", true], ["Count", true], ["Observed %", true], ["Expected %", true], ["Gap", true]], r.detail.digits.map((d) => h("tr", {}, td(String(d.digit), true), td(String(d.count), true), td(String(d.observed_pct), true), td(String(d.expected_pct), true), td(String(d.difference_pct), true)))) : null,
      r.hits.length ? table([["Journal"], ["Date"], ["Amount", true], ["Why it was flagged"], [""]], r.hits.map((x) => h("tr", { "data-hit": x.journal_id }, td(x.number), td(x.date), td(num(x.amount), true), td(x.reason),
        td(prep ? h("button", { className: "btn btn-secondary", onClick: () => a.citeJournal(x, run.id) }, "Use in a finding") : "")))) : null,
      r.truncated ? h("div", { style: "color: var(--ink-500);" }, `Showing the first ${r.hits.length} of ${r.hit_count}.`) : null,
      r.limits ? h("small", { style: "color: var(--ink-500);" }, r.limits) : null)));
}

function findings(fm, role, userId, a) {
  const c = fm.case, prep = canPrepare(role) && c.status === "OPEN", f = fm.findingForm;
  return h("div", { id: "fx-findings" },
    prep && !f ? h("button", { className: "btn btn-primary", id: "fd-new", onClick: () => a.newFinding() }, "Draft a finding") : null,
    f ? h("div", { className: "card", id: "fd-form", style: "margin:12px 0;" }, h("h3", {}, f.id ? "Edit finding" : "Draft a finding"),
      note("State what the records show and what supports it. Avoid naming anyone as guilty; describe facts and the reasoning.", "info"),
      field("Title", "fd-title", input("fd-title", f, "title", a.findingChange)), field("What was found, and what supports it", "fd-desc", h("textarea", { id: "fd-desc", rows: 4, onInput: (e) => a.findingChange("description", e.target.value) }, f.description)),
      field("Severity", "fd-sev", h("select", { id: "fd-sev", onChange: (e) => a.findingChange("severity", e.target.value) }, fm.options.severities.map((s) => h("option", { value: s, selected: f.severity === s }, SEVERITY_TEXT[s])))),
      h("div", { className: "field" }, h("label", {}, "Journals cited"), f.journals.length === 0 ? h("div", { style: "color: var(--ink-500);" }, "None yet. Use 'Use in a finding' beside a flagged journal on the Analytics tab.")
        : f.journals.map((j) => h("div", { "data-cited": j.id }, `${j.number} · ${j.date} · ${num(j.amount)} `, h("button", { className: "btn btn-secondary", onClick: () => a.uncite(j.id) }, "Remove")))),
      c.evidence.length ? h("div", { className: "field" }, h("label", {}, "Evidence relied on"), c.evidence.map((e) => h("label", { style: "display:block;" }, h("input", { type: "checkbox", id: `fd-ev-${e.evidence_id}`, checked: f.evidence_ids.includes(e.evidence_id), onChange: (ev) => a.findingEvidence(e.evidence_id, ev.target.checked) }), ` ${e.filename}`))) : null,
      h("button", { className: "btn btn-primary", id: "fd-save", disabled: fm.busy, onClick: () => a.saveFinding() }, "Save as draft"), " ", h("button", { className: "btn btn-secondary", id: "fd-cancel", onClick: () => a.cancelFinding() }, "Cancel")) : null,
    c.findings.length === 0 ? EmptyState({ title: "No findings yet", message: "A finding is your reasoned conclusion. It must be approved by a different person before it counts." })
      : c.findings.map((x) => { const act = itemActions(x, role, userId), st = stateOf(x.status); return h("div", { className: "card", "data-finding": x.id, style: "margin-bottom:12px;" },
        h("h3", {}, x.title, " ", Badge({ tone: st.tone, label: st.label }), " ", Badge({ tone: x.severity === "HIGH" ? "fail" : x.severity === "MEDIUM" ? "warn" : "neutral", label: SEVERITY_TEXT[x.severity] })),
        h("p", {}, x.description), x.journals.length ? h("div", { style: "color: var(--ink-500);" }, `Journals: ${x.journals.map((j) => j.number).join(", ")}`) : null,
        x.decision_note ? note(`${x.status === "REJECTED" ? "Sent back" : "Reviewed"} by ${x.decided_by}: ${x.decision_note}`, x.status === "REJECTED" ? "warning" : "success") : null,
        act.ownSubmission ? note("You prepared or submitted this, so a different person must review it.", "info") : null,
        h("div", { style: "display:flex; gap:8px; flex-wrap:wrap;" },
          act.edit && c.status === "OPEN" ? h("button", { className: "btn btn-secondary", id: `fd-edit-${x.id}`, onClick: () => a.editFinding(x.id) }, "Edit") : null,
          act.submit && c.status === "OPEN" ? h("button", { className: "btn btn-primary", id: `fd-submit-${x.id}`, disabled: fm.busy, onClick: () => a.submitFinding(x.id) }, "Submit for review") : null,
          act.discard && c.status === "OPEN" ? h("button", { className: "btn btn-secondary", id: `fd-discard-${x.id}`, disabled: fm.busy, onClick: () => a.discardFinding(x.id) }, "Discard") : null),
        act.decide ? h("div", { style: "margin-top:8px;" }, field("Note or reason", `fd-note-${x.id}`, h("input", { id: `fd-note-${x.id}`, type: "text", value: fm.decisionNotes[x.id] || "", onInput: (e) => a.decisionChange(x.id, e.target.value) }), "A reason is required if you send it back."),
          h("button", { className: "btn btn-primary", id: `fd-approve-${x.id}`, disabled: fm.busy, onClick: () => a.decideFinding(x.id, true) }, "Approve"), " ", h("button", { className: "btn btn-secondary", id: `fd-reject-${x.id}`, disabled: fm.busy, onClick: () => a.decideFinding(x.id, false) }, "Send back")) : null); }));
}

function reports(fm, role, a) {
  const c = fm.case, prep = canPrepare(role);
  return h("div", { id: "fx-reports" },
    prep ? h("div", { className: "card", style: "margin-bottom:12px;" }, h("h3", {}, "Freeze a case report"), note("A report freezes the approved findings, evidence fingerprints and the state of the custody log at this moment. A second person must approve it.", "info"),
      field("Report title", "rp-title", h("input", { id: "rp-title", type: "text", value: fm.reportTitle, onInput: (e) => a.reportTitleChange(e.target.value) })), h("button", { className: "btn btn-primary", id: "rp-create", disabled: fm.busy, onClick: () => a.createReport() }, "Create report")) : null,
    c.reports.length === 0 ? EmptyState({ title: "No reports yet", message: "" }) : table([["Title"], ["Status"], ["Created"], [""]], c.reports.map((r) => h("tr", { "data-report": r.id }, td(r.title), td(Badge({ tone: stateOf(r.status).tone, label: stateOf(r.status).label })), td(when(r.created_at)), td(h("button", { className: "btn btn-secondary", id: `rp-open-${r.id}`, onClick: () => a.openReport(r.id) }, "Open")))), "fx-report-table"));
}

function reportDetail(fm, role, userId, a) {
  const r = fm.report, s = r.snapshot, st = stateOf(r.status), act = itemActions(r, role, userId);
  return h("div", { id: "fx-report" },
    h("button", { className: "btn btn-secondary", id: "rp-back", onClick: () => a.closeReport() }, "Back to reports"),
    h("h3", {}, r.title, " ", Badge({ tone: st.tone, label: st.label, id: "rp-state" })),
    r.intact === false ? note("This report no longer matches its fingerprint. Do not rely on it.", "error") : null,
    note(s.integrity.meaning, s.integrity.ok ? "success" : "error"),
    h("div", { className: "card", style: "margin-bottom:12px;" }, h("p", { style: "color: var(--ink-500);" }, `Frozen ${when(s.generated_at)}. Fingerprint ${r.fingerprint}. Custody log head ${s.custody_head.slice(0, 16)}... (${s.custody_entries} entries).`),
      h("h4", {}, `Approved findings (${s.findings.length})`), s.findings.length === 0 ? h("p", {}, "None. No finding had been approved when this report was frozen.") : s.findings.map((f) => h("div", { style: "margin-bottom:8px;" }, h("strong", {}, `${f.title} (${SEVERITY_TEXT[f.severity]})`), h("div", {}, f.description), h("small", { style: "color: var(--ink-500);" }, `Journals: ${f.journals.map((j) => j.number).join(", ") || "none"}`))),
      h("h4", {}, "Limitations"), h("ul", { style: "padding-left:18px;" }, s.limitations.map((l) => h("li", {}, l)))),
    act.ownSubmission ? note("You prepared or submitted this report, so a different person must review it.", "info") : null,
    r.decision_note ? note(`${r.status === "REJECTED" ? "Sent back" : "Reviewed"} by ${r.decided_by}: ${r.decision_note}`, r.status === "REJECTED" ? "warning" : "success") : null,
    h("div", { style: "display:flex; gap:8px; flex-wrap:wrap; margin-bottom:12px;" },
      act.submit ? h("button", { className: "btn btn-primary", id: "rp-submit", disabled: fm.busy, onClick: () => a.submitReport() }, "Submit for review") : null,
      r.status === "APPROVED" ? h("button", { className: "btn btn-secondary", id: "rp-export", disabled: fm.busy, onClick: () => a.exportReport() }, "Download CSV") : null),
    act.decide ? h("div", { className: "card" }, h("h3", {}, "Your review"), field("Note or reason", "rp-decision", h("input", { id: "rp-decision", type: "text", value: fm.reportNote, onInput: (e) => a.reportNoteChange(e.target.value) }), "A reason is required if you send it back."),
      h("button", { className: "btn btn-primary", id: "rp-approve", disabled: fm.busy, onClick: () => a.decideReport(true) }, "Approve"), " ", h("button", { className: "btn btn-secondary", id: "rp-reject", disabled: fm.busy, onClick: () => a.decideReport(false) }, "Send back")) : null);
}

function custody(fm, a) {
  const c = fm.case;
  return h("div", { id: "fx-custody" }, note("Every action on this case is added to a chain: each entry carries the fingerprint of the one before it, so an entry that is changed or removed breaks the chain and is detected.", "info"),
    table([["#", true], ["When"], ["Who"], ["What"], ["Detail"], ["Fingerprint"]], c.custody.map((e) => h("tr", {}, td(String(e.seq), true), td(when(e.at)), td(e.actor), td(e.action.replace(/_/g, " ").toLowerCase()), td(e.detail), td(h("code", {}, e.hash.slice(0, 12) + "...")))), "fx-custody-table"));
}
