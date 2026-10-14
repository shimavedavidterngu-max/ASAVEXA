import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState } from "../components/DataState.js";
import { TABS, CHANGE_TEXT, RISK_TEXT, CONTROL_TYPE_TEXT, FREQUENCY_TEXT, FLAG_TEXT, ATTENTION_TONE, canPrepare, canApprove, statusOf, words, who,
  canVoid, canRetire, canTestControl, canConclude, canAddCase, canSubmit, testBlockers, mineToWork, approveMoves, needsApprovalNote, waitingText, toleranceText, headline } from "../lib/itaudit.js";

/**
 * IT audit. It records and checks what people type in; it does not connect to any system, read any ticket or test any application.
 * A flag is a fixed rule over typed facts, not a finding. A sample is repeatable but not statistical. A different person approves every test.
 */
const Badge = ({ tone, label, id }) => h("span", { className: `badge badge-${tone || "neutral"}`, id }, label);
const St = (s) => Badge({ ...statusOf(s) });
const note = (t, kind = "info", id) => (t ? h("div", { className: `alert alert-${kind}`, id, style: "margin-bottom:12px;", role: kind === "error" ? "alert" : "status" }, t) : null);
const field = (l, id, inp, hint) => h("div", { className: "field" }, h("label", { for: id }, l), inp, hint ? h("small", { style: "color: var(--ink-500);" }, hint) : null);
const text = (ia, a, form, k, id, ph) => h("input", { id, type: "text", value: (ia.forms[form] || {})[k] == null ? "" : (ia.forms[form] || {})[k], placeholder: ph || "", onInput: (e) => a.setForm(form, k, e.target.value) });
const area = (ia, a, form, k, id) => h("textarea", { id, rows: 3, onInput: (e) => a.setForm(form, k, e.target.value) }, (ia.forms[form] || {})[k] || "");
const sel = (ia, a, form, k, id, opts, blank) => h("select", { id, onChange: (e) => a.setForm(form, k, e.target.value, true) },
  [...(blank ? [h("option", { value: "" }, blank)] : []), ...opts.map(([v, l]) => h("option", { value: v, selected: String((ia.forms[form] || {})[k]) === String(v) }, l))]);
const btn = (l, id, onClick, kind = "secondary", disabled = false) => h("button", { className: `btn btn-${kind}`, id, disabled, onClick }, l);
const row = (...b) => h("div", { style: "display:flex; gap:8px; flex-wrap:wrap; margin:8px 0; align-items:end;" }, b.filter(Boolean));
const none = (t = "None.") => h("div", { style: "color: var(--ink-500);" }, t);
const card = (title, id, ...kids) => h("div", { className: "card", id, style: "margin-bottom:16px;" }, h("h3", {}, title), ...kids);
const hist = (items) => h("ul", {}, (items || []).map((x) => h("li", {}, `${String(x.at).slice(0, 10)} ${String(x.event).replace(/_/g, " ").toLowerCase()} by ${x.by}${x.note ? ": " + x.note : ""}`)));
const noteBox = (ia, a, key, l, id) => field(l, id || `note-${key}`, h("textarea", { id: id || `note-${key}`, rows: 2, onInput: (e) => a.setNote(key, e.target.value) }, ia.notes[key] || ""));
const formError = (ia, name) => (ia.formError && ia.formError.form === name ? note(ia.formError.text, "error", `${name}-problem`) : null);
const docs = (ia, a, form, id) => field("Attach a document (optional)", id, sel(ia, a, form, "evidence_id", id, (ia.vault || []).map((e) => [e.id, e.original_filename || e.filename || e.id]), "No document"), "A document from the Evidence Vault. Its file fingerprint is kept.");
const fileList = (list) => (list && list.length ? h("div", { style: "font-size:0.9em; color: var(--ink-500);" }, list.map((e) => `${e.filename} (fingerprint ${String(e.file_hash).slice(0, 12)})`).join("; ")) : null);
const flagBadges = (flags) => (flags && flags.length ? flags.map((f) => Badge({ tone: "warn", label: FLAG_TEXT[f] || words(f) })) : [Badge({ tone: "pass", label: "No flags" })]);
const opt = (o) => Object.entries(o);

export function ItAudit({ ia, role, userId, loading, onRetry, actions: a }) {
  return h("div", {},
    h("h1", {}, "IT audit"),
    note("This workspace records and checks what people type in. It does not connect to any system, read any ticket or test any application, and a flag is a rule applied to typed facts, not a finding. A sample is repeatable but not statistical. A different person approves every test, and nobody tests their own records.", "info", "ia-banner"),
    ia.error ? ErrorState({ message: ia.error, onRetry }) : null,
    note(ia.notice, "success", "ia-notice"),
    loading ? LoadingState() : h("div", {},
      h("div", { className: "tabs", role: "tablist", style: "display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px;" },
        TABS.map(([id, l]) => h("button", { className: `btn ${ia.tab === id ? "btn-primary" : "btn-secondary"}`, role: "tab", id: `ia-tab-${id}`, "aria-selected": ia.tab === id ? "true" : "false", onClick: () => a.setTab(id) }, l))),
      ia.busy ? h("div", { style: "color: var(--ink-500);" }, "Working...") : null,
      ia.tab === "overview" ? overview(ia, role, a) : ia.tab === "changes" ? changes(ia, role, userId, a) : ia.tab === "controls" ? controls(ia, role, userId, a) : tests(ia, role, userId, a)));
}

// ---------------------------------------------------------------- overview
function overview(ia, role, a) {
  const o = ia.ov; if (!o) return none("Nothing loaded yet.");
  const c = o.counts, t = c.changes_by_type || {};
  return h("div", {},
    card("What needs attention", "ia-attention", o.attention.length ? h("ul", {}, o.attention.map((x) => h("li", { "data-kind": x.kind }, Badge({ tone: ATTENTION_TONE[x.kind] || "info", label: words(x.kind) }), " ", `${x.count} ${x.text}`))) : none("Nothing needs attention.")),
    card("Counts", "ia-counts", h("ul", {}, [["Change records", c.changes_live], ["Change records with a flag", c.changes_flagged], ["Standard changes", t.STANDARD || 0], ["Normal changes", t.NORMAL || 0], ["Emergency changes", t.EMERGENCY || 0],
      ["Active controls", c.controls_active], ["Tests", c.tests], ["Approved tests", c.tests_approved]].map(([l, n]) => h("li", {}, `${l}: ${n}`)))),
    policyCard(ia, role, a),
    card("What this does not do", "ia-limits", h("ul", {}, o.limitations.map((x) => h("li", {}, x)))));
}

function policyCard(ia, role, a) {
  const p = ia.ov.policy, f = ia.forms.policy;
  return card("Settings", "ia-policy", h("p", { id: "ia-policy-meaning" }, p.meaning),
    canApprove(role) && f ? h("div", {},
      row(field("Days an emergency change may be approved after go-live", "ia-policy-emerg", text(ia, a, "policy", "emergency_ratify_days", "ia-policy-emerg")), field("Days before a control is due for retest", "ia-policy-retest", text(ia, a, "policy", "retest_days", "ia-policy-retest"))),
      formError(ia, "policy"), btn("Save settings", "ia-policy-save", () => a.savePolicy(), "primary", ia.busy)) : h("p", { style: "color: var(--ink-500);" }, "Only an approver can change these settings."));
}

// ---------------------------------------------------------------- changes
function changes(ia, role, me, a) {
  const shown = ia.flaggedOnly ? ia.changes.filter((c) => c.flags.length) : ia.changes;
  const assets = (ia.options && ia.options.assets) || [];
  return h("div", {},
    card("Change records", "ia-changes",
      h("div", {}, btn(ia.flaggedOnly ? "Show all" : "Show only flagged", "ia-filter-flagged", () => a.toggleFlagged(), "secondary", ia.busy)),
      shown.length ? shown.map((c) => h("div", { className: "card", style: "margin-bottom:8px;", "data-change": c.ref },
        h("div", {}, h("strong", {}, `${c.ref} · ${c.title}`), " ", St(c.status), " ", St(c.risk), ` · ${CHANGE_TEXT[c.change_type] || c.change_type}`),
        h("div", { style: "color: var(--ink-500);" }, `${c.system}${c.asset_name ? ` (asset ${c.asset_name})` : ""} · ticket ${c.ticket_ref} · live ${c.implemented_on} · asked by ${c.requested_by} · ${c.approved_by_name ? `approved by ${c.approved_by_name} on ${c.approved_on}` : "no approval recorded"} · recorded by ${who(c.recorded_by, me)}`),
        h("div", {}, c.description), h("div", { className: "flags" }, flagBadges(c.flags)), fileList(c.evidence),
        c.status === "VOIDED" ? h("div", {}, `Voided: ${c.void_note}`) : null,
        canVoid(c, role, me) ? h("div", {}, noteBox(ia, a, `void-${c.id}`, "Why this record is being voided (required, at least 10 characters)"), btn("Void record", `ia-void-${c.ref}`, () => a.voidChange(c.id), "secondary", ia.busy)) :
          (c.status === "RECORDED" && canApprove(role) ? h("div", { style: "color: var(--ink-500);" }, "You recorded this change, so a different person must void it.") : null))) : none(ia.flaggedOnly ? "No change has a flag." : "No change records yet.")),
    canPrepare(role) ? card("Record a change", "ia-change-card",
      h("p", { style: "color: var(--ink-500);" }, "Type in the facts from your own change system. ASAVEXA applies fixed rules to them and shows what looks wrong; it cannot tell whether the facts are true."),
      row(field("System", "ia-ch-system", text(ia, a, "change", "system", "ia-ch-system", "Payroll")), field("Ticket or change number", "ia-ch-ticket", text(ia, a, "change", "ticket_ref", "ia-ch-ticket")),
        field("Type", "ia-ch-type", sel(ia, a, "change", "change_type", "ia-ch-type", opt(CHANGE_TEXT))), field("Risk", "ia-ch-risk", sel(ia, a, "change", "risk", "ia-ch-risk", opt(RISK_TEXT)))),
      assets.length ? field("Linked asset (optional)", "ia-ch-asset", sel(ia, a, "change", "asset_id", "ia-ch-asset", assets.map((x) => [x.id, `${x.ref} · ${x.name}`]), "No asset")) : null,
      field("Title", "ia-ch-title", text(ia, a, "change", "title", "ia-ch-title")), field("What was changed", "ia-ch-desc", area(ia, a, "change", "description", "ia-ch-desc")),
      row(field("Asked for by", "ia-ch-requested", text(ia, a, "change", "requested_by", "ia-ch-requested")), field("Approved by (name)", "ia-ch-approver", text(ia, a, "change", "approved_by_name", "ia-ch-approver")),
        field("Approved on", "ia-ch-approved", text(ia, a, "change", "approved_on", "ia-ch-approved", "YYYY-MM-DD")), field("Went live on", "ia-ch-live", text(ia, a, "change", "implemented_on", "ia-ch-live", "YYYY-MM-DD"))),
      field("Testing evidence (leave empty if there was none)", "ia-ch-testing", text(ia, a, "change", "testing_evidence", "ia-ch-testing")), field("Rollback plan (leave empty if there was none)", "ia-ch-rollback", text(ia, a, "change", "rollback_plan", "ia-ch-rollback")),
      docs(ia, a, "change", "ia-ch-doc"), formError(ia, "change"), btn("Record change", "ia-ch-save", () => a.recordChange(), "primary", ia.busy)) : null);
}

// ---------------------------------------------------------------- controls
function controls(ia, role, me, a) {
  const assets = (ia.options && ia.options.assets) || [];
  return h("div", {},
    card("Application controls", "ia-controls", ia.controls.length ? ia.controls.map((c) => h("div", { className: "card", style: "margin-bottom:8px;", "data-control": c.ref },
      h("div", {}, h("strong", {}, `${c.ref} · ${c.name}`), " ", St(c.status), c.retest_due ? " " + Badge({ tone: "warn", label: c.tests ? "Retest due" : "Never tested" }) : null),
      h("div", { style: "color: var(--ink-500);" }, `${c.system}${c.asset_name ? ` (asset ${c.asset_name})` : ""} · ${CONTROL_TYPE_TEXT[c.control_type] || c.control_type} · ${FREQUENCY_TEXT[c.frequency] || c.frequency} · ${c.tolerable} exception(s) tolerable · defined by ${who(c.created_by, me)}`),
      h("div", {}, c.description), h("div", {}, `Expected: ${c.expected_result}`),
      h("div", { style: "color: var(--ink-500);" }, c.tests ? `${c.tests} test(s); last approved ${c.last_tested_on || "none yet"}${c.last_conclusion ? ` — ${statusOf(c.last_conclusion).label}` : ""}` : "Never tested."),
      c.status === "RETIRED" ? h("div", {}, `Retired: ${c.retire_note}`) : null,
      canRetire(c, role) ? h("div", {}, noteBox(ia, a, `retire-${c.id}`, "Why this control is being retired (required, at least 10 characters)"), btn("Retire control", `ia-retire-${c.ref}`, () => a.retireControl(c.id), "secondary", ia.busy)) : null)) : none("No controls defined yet.")),
    canPrepare(role) ? card("Define a control", "ia-control-card",
      h("p", { style: "color: var(--ink-500);" }, "A control is something an application should always do, such as rejecting a duplicate payee. You cannot test a control you defined; a different person does."),
      row(field("System", "ia-ct-system", text(ia, a, "control", "system", "ia-ct-system", "Payroll")), field("Control name", "ia-ct-name", text(ia, a, "control", "name", "ia-ct-name")),
        field("Type", "ia-ct-type", sel(ia, a, "control", "control_type", "ia-ct-type", opt(CONTROL_TYPE_TEXT))), field("How often it operates", "ia-ct-freq", sel(ia, a, "control", "frequency", "ia-ct-freq", opt(FREQUENCY_TEXT)))),
      assets.length ? field("Linked asset (optional)", "ia-ct-asset", sel(ia, a, "control", "asset_id", "ia-ct-asset", assets.map((x) => [x.id, `${x.ref} · ${x.name}`]), "No asset")) : null,
      field("What the control does", "ia-ct-desc", area(ia, a, "control", "description", "ia-ct-desc")), field("Expected result", "ia-ct-expected", text(ia, a, "control", "expected_result", "ia-ct-expected")),
      field("Exceptions you can tolerate in a test", "ia-ct-tol", text(ia, a, "control", "tolerable", "ia-ct-tol"), "Your own number, from 0 to 20."),
      formError(ia, "control"), btn("Define control", "ia-ct-save", () => a.defineControl(), "primary", ia.busy)) : null);
}

// ---------------------------------------------------------------- tests
function tests(ia, role, me, a) {
  const open = ia.sel.test, testable = ia.controls.filter((c) => canTestControl(c, role, me));
  return h("div", {},
    card("Tests", "ia-tests", ia.tests.length ? ia.tests.map((t) => h("div", { className: "card", style: "margin-bottom:8px;", "data-test": t.ref },
      h("div", {}, h("strong", {}, headline(t)), " ", St(t.status), t.conclusion ? " " + St(t.conclusion) : null, ` · ${t.kind === "CHANGE" ? "Change management" : `Control ${t.control_ref}`}`),
      h("div", { style: "color: var(--ink-500);" }, `Prepared by ${who(t.prepared_by, me)} · ${t.concluded} concluded · ${t.exceptions} exception(s)`),
      btn(open && open.id === t.id ? "Hide" : "Open", `ia-test-open-${t.ref}`, () => a.selectTest(open && open.id === t.id ? null : t.id), "secondary", ia.busy))) : none("No tests yet.")),
    open ? testDetail(ia, role, me, a, open) : null,
    canPrepare(role) ? card("Plan a change-management test", "ia-ptest-card",
      h("p", { style: "color: var(--ink-500);" }, "ASAVEXA draws the sample by a rule anyone can repeat from the period, the size and your seed. It is not a statistical sample."),
      row(field("Title", "ia-pt-title", text(ia, a, "ptest", "title", "ia-pt-title")), field("System (optional)", "ia-pt-system", text(ia, a, "ptest", "system", "ia-pt-system"))),
      row(field("Went live from", "ia-pt-from", text(ia, a, "ptest", "period_from", "ia-pt-from", "YYYY-MM-DD")), field("Went live to", "ia-pt-to", text(ia, a, "ptest", "period_to", "ia-pt-to", "YYYY-MM-DD")),
        field("Sample size", "ia-pt-size", text(ia, a, "ptest", "sample_size", "ia-pt-size")), field("Seed (any words)", "ia-pt-seed", text(ia, a, "ptest", "seed", "ia-pt-seed")), field("Tolerable exceptions", "ia-pt-tol", text(ia, a, "ptest", "tolerable", "ia-pt-tol"))),
      formError(ia, "ptest"), btn("Plan test", "ia-pt-save", () => a.planChangeTest(), "primary", ia.busy)) : null,
    canPrepare(role) ? card("Plan a control test", "ia-ctest-card",
      testable.length ? h("div", {}, row(field("Title", "ia-cx-title", text(ia, a, "ctest", "title", "ia-cx-title")), field("Control", "ia-cx-control", sel(ia, a, "ctest", "control_id", "ia-cx-control", testable.map((c) => [c.id, `${c.ref} · ${c.name}`]), "Choose a control"))),
        formError(ia, "ctest"), btn("Plan test", "ia-cx-save", () => a.planControlTest(), "primary", ia.busy)) : none("No active control is available for you to test. You cannot test a control you defined.")) : null);
}

function testDetail(ia, role, me, a, t) {
  const moves = approveMoves(t, role, me), wait = waitingText(t, role, me), block = testBlockers(t, role, me), key = `test-${t.id}`;
  const f = ia.forms.case;
  return card(headline(t), "ia-test-detail",
    h("p", {}, St(t.status), t.conclusion ? " " + St(t.conclusion) : null, ` · prepared by ${who(t.prepared_by, me)}${t.approved_by ? ` · approved by ${who(t.approved_by, me)} on ${t.approved_on}` : ""}`),
    t.kind === "CHANGE" ? h("p", { id: "ia-sample-info" }, `Went live ${t.period_from} to ${t.period_to}${t.system ? ` on ${t.system}` : ""}. ${t.items.length} of ${t.population_count} change(s) sampled with seed "${t.seed}". Population fingerprint ${String(t.population_fingerprint).slice(0, 12)}.`) :
      h("p", {}, `Control ${t.control_ref} · ${t.control_name}. Expected: ${t.control_expected}`),
    h("p", { id: "ia-tolerance" }, toleranceText(t) + (t.conclusion ? ` Result: ${statusOf(t.conclusion).label}.` : "")),
    t.rejected_note && t.status === "DRAFT" ? note(`Sent back: ${t.rejected_note}`, "info", "ia-sent-back") : null,
    t.approval_note ? h("p", {}, `Approval note: ${t.approval_note}`) : null,
    t.kind === "CHANGE" ? h("div", { id: "ia-items" }, h("h4", {}, "Sampled changes"),
      t.items.map((i) => h("div", { className: "card", style: "margin-bottom:8px;", "data-item": i.ref },
        h("div", {}, h("strong", {}, `${i.ref} · ${i.snapshot.title}`), " ", i.result ? St(i.result) : Badge({ tone: "warn", label: "Not concluded" })),
        h("div", { style: "color: var(--ink-500);" }, `${i.snapshot.system} · ticket ${i.snapshot.ticket_ref} · live ${i.snapshot.implemented_on} · asked by ${i.snapshot.requested_by} · recorded by ${who(i.snapshot.recorded_by, me)}`),
        h("div", {}, flagBadges(i.flags)), i.result ? h("div", {}, `${i.note || "No note"} (by ${who(i.concluded_by, me)})${i.overrode_flags ? " — flags overridden with an explanation" : ""}`) : null,
        canConclude(t, i, role, me) ? h("div", {}, noteBox(ia, a, `it-${i.id}`, i.flags.length ? "Note (an explanation of at least 20 characters is needed to call a flagged change 'no exception')" : "Note (required for an exception)"),
          btn("No exception", `ia-item-${i.ref}-ok`, () => a.concludeItem(i, "NO_EXCEPTION"), "secondary", ia.busy), " ", btn("Exception", `ia-item-${i.ref}-exc`, () => a.concludeItem(i, "EXCEPTION"), "secondary", ia.busy)) :
          (!i.result && mineToWork(t, role, me) && i.snapshot.recorded_by === me ? h("div", { style: "color: var(--ink-500);" }, "You recorded this change, so you cannot test it. A different person must.") : null)))) :
      h("div", { id: "ia-cases" }, h("h4", {}, "Test cases"),
        t.cases.length ? h("ul", {}, t.cases.map((x) => h("li", { "data-case": x.seq }, `${x.performed_on} · ${x.description} → expected ${x.expected}; actual ${x.actual} `, St(x.result), x.note ? ` — ${x.note}` : "", fileList(x.evidence)))) : none("No test cases yet."),
        canAddCase(t, role, me) ? h("div", {}, row(field("What you tried", "ia-cs-desc", text(ia, a, "case", "description", "ia-cs-desc")), field("Date performed", "ia-cs-date", text(ia, a, "case", "performed_on", "ia-cs-date", "YYYY-MM-DD"))),
          row(field("Expected", "ia-cs-expected", text(ia, a, "case", "expected", "ia-cs-expected")), field("Actual", "ia-cs-actual", text(ia, a, "case", "actual", "ia-cs-actual")), field("Result", "ia-cs-result", sel(ia, a, "case", "result", "ia-cs-result", [["PASS", "Passed"], ["FAIL", "Failed"]]))),
          field(f.result === "FAIL" ? "Note (required for a failure)" : "Note (optional)", "ia-cs-note", text(ia, a, "case", "note", "ia-cs-note")), docs(ia, a, "case", "ia-cs-doc"), formError(ia, "case"), btn("Add test case", "ia-cs-save", () => a.addCase(t.id), "primary", ia.busy)) : null),
    block ? h("p", { id: "ia-blocked" }, block) : null,
    canSubmit(t, role, me) ? h("div", {}, btn("Submit for approval", "ia-test-submit", () => a.submitTest(t.id), "primary", ia.busy)) : null,
    mineToWork(t, role, me) ? h("div", { id: "ia-withdraw" }, noteBox(ia, a, `wd-${t.id}`, "Why this test is being withdrawn (required, at least 10 characters)"), btn("Withdraw test", "ia-test-withdraw", () => a.withdrawTest(t.id), "secondary", ia.busy)) : null,
    t.status === "WITHDRAWN" ? note(`Withdrawn: ${t.rejected_note}`, "info", "ia-withdrawn") : null,
    wait ? h("p", { id: "ia-waiting" }, wait) : null,
    moves.length ? h("div", { id: "ia-decide" }, noteBox(ia, a, key, needsApprovalNote(t) ? "Note (required to approve: this test has exceptions or overridden flags; at least 10 characters. Also the reason to send back.)" : "Note (optional to approve; required, at least 10 characters, to send back)"),
      moves.map((m) => btn(m === "approve" ? "Approve test" : "Send back", `ia-test-${m}`, () => a.decideTest(t.id, m, t), m === "approve" ? "primary" : "secondary", ia.busy))) : null,
    h("div", {}, h("h4", {}, "History"), hist(t.history)));
}
