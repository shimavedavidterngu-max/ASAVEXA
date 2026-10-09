import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState } from "../components/DataState.js";
import { allowed } from "../components/PermissionGate.js";
import { PERMISSIONS } from "../lib/permissions.js";

/**
 * ASAVEXA AI: Explain, Detect, Recommend, Prove. Pure render function; app.js owns the form state
 * and every API call. Every answer is drawn as the same chain:
 *   AI conclusion -> Source records -> Evidence -> Journal -> Accounting treatment
 *   -> Reporting framework -> Confidence -> Human review
 * This page never computes or adjusts an answer; it only shows what the server grounded.
 */

export const MODE_INFO = {
  EXPLAIN: { label: "AI Explain", prompt: "Why was this transaction classified this way?", button: "Explain" },
  DETECT: { label: "AI Detect", prompt: "Find unusual transactions.", button: "Find unusual transactions" },
  RECOMMEND: { label: "AI Recommend", prompt: "Suggest a reconciliation or adjustment.", button: "Suggest" },
  PROVE: { label: "AI Prove", prompt: "Show the evidence supporting your answer.", button: "Show the evidence" },
};
export const MODES = Object.keys(MODE_INFO);

export const CHAIN_STEPS = [
  ["conclusion", "AI conclusion"], ["source_records", "Source records"], ["evidence", "Evidence"], ["journal", "Journal"],
  ["accounting_treatment", "Accounting treatment"], ["reporting_framework", "Reporting framework"],
  ["confidence", "Confidence"], ["human_review", "Human review requirement"],
];

export const METRICS = [["revenue", "Revenue"], ["expenses", "Expenses"], ["net_income", "Net income"], ["assets", "Assets"], ["liabilities", "Liabilities"]];
export const RECOMMEND_SCOPES = [["all", "Everything"], ["reconciliation", "Bank reconciliation"], ["adjustment", "Adjustments"], ["evidence", "Evidence"]];
export const SAMPLE_QUESTIONS = [
  "Find unusual transactions.", "Suggest a reconciliation or adjustment.",
  "Why was JRN-000001 classified this way?", "Show the evidence for JRN-000001",
];

export function newAiForm() {
  return { journalId: "", periodId: "", scope: "all", kind: "journal", metric: "revenue" };
}

/** Pure: a plain-English problem with the form, or null. */
export function validateAiForm(mode, f) {
  if (mode === "EXPLAIN" && !f.journalId) return "Choose the journal you want explained.";
  if (mode === "PROVE") {
    if (f.kind === "journal" && !f.journalId) return "Choose the journal you want proof for.";
    if (f.kind === "figure" && !f.periodId) return "Choose the accounting period the figure is for.";
  }
  return null;
}

/** Pure: the request a mode's form turns into (the page never builds URLs itself). */
export function buildAiRequest(mode, f) {
  if (mode === "EXPLAIN") return { call: "aiExplain", args: { subjectType: "journal", subjectId: f.journalId } };
  if (mode === "DETECT") return { call: "aiDetect", args: { periodId: f.periodId || null, limit: 20 } };
  if (mode === "RECOMMEND") return { call: "aiRecommend", args: { scope: f.scope || "all", periodId: f.periodId || null, limit: 15 } };
  if (f.kind === "figure") return { call: "aiProve", args: { subjectType: "figure", metric: f.metric, periodId: f.periodId } };
  return { call: "aiProve", args: { subjectType: "journal", subjectId: f.journalId } };
}

/** Pure: which record an answer item is about, so the page can offer "Explain this / Prove this". */
export function itemSubject(item) {
  if (!item) return null;
  if (item.kind === "BANK_TRANSACTION") {
    const t = (item.source_records || []).find((r) => r.kind === "BANK_TRANSACTION");
    return t ? { subjectType: "bank_transaction", subjectId: t.id } : null;
  }
  if (item.journal && item.journal.available) return { subjectType: "journal", subjectId: item.journal.id };
  const t = (item.source_records || []).find((r) => r.kind === "BANK_TRANSACTION");
  return t ? { subjectType: "bank_transaction", subjectId: t.id } : null;
}

const TONE = { HIGH: "pass", MEDIUM: "warn", LOW: "fail", PROVEN: "pass", PARTIALLY_PROVEN: "warn", NOT_PROVEN: "fail",
  PASS: "pass", FAIL: "fail", NOT_APPLICABLE: "neutral", VERIFIED: "pass", UNVERIFIED: "warn", DEFECTIVE: "fail", MISSING: "fail", MIXED: "warn" };
const SEVERITY_TONE = { HIGH: "fail", MEDIUM: "warn", LOW: "neutral" };
const nice = (s) => String(s || "").replace(/_/g, " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase());

export function badge(text, tone) {
  return h("span", { className: `badge badge-${tone || "neutral"}` }, text);
}

function when(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? String(iso) : d.toISOString().slice(0, 16).replace("T", " ") + " UTC";
}

// ------------------------------------------------------------------ the chain
function step(n, title, id, ...body) {
  return h("div", { className: "ai-step", "data-step": id, style: "border:1px solid var(--line); border-radius:8px; padding:10px 14px;" },
    h("div", { style: "font-weight:600; font-size:13px; margin-bottom:6px;" }, `${n}. ${title}`), ...body);
}

function arrow() {
  return h("div", { className: "ai-arrow", "aria-hidden": "true", style: "text-align:center; color: var(--ink-500); line-height:1.2; font-size:18px;" }, "↓");
}

function unavailableNote(stage) {
  return h("div", { className: "alert alert-info", style: "margin:0;" }, stage.note);
}

function bullets(points) {
  return h("ul", { style: "margin:6px 0 0; padding-left:18px;" }, (points || []).map((p) => h("li", {}, p)));
}

function sourceChips(records) {
  return h("div", { style: "display:flex; gap:6px; flex-wrap:wrap;" }, records.map((r) => {
    const label = `${nice(r.kind)}: ${r.label}`;
    return r.path
      ? h("a", { className: "badge badge-info", href: `#${r.path}`, title: r.detail || "" }, label)
      : h("span", { className: "badge badge-neutral", title: r.detail || "" }, label);
  }));
}

function evidenceBody(ev) {
  if (!ev.available) return unavailableNote(ev);
  return h("div", {},
    h("div", { style: "margin-bottom:6px;" }, badge(nice(ev.state), TONE[ev.state]), " ", ev.note),
    ev.coverage ? h("div", { style: "font-size:12.5px; margin-bottom:6px;" },
      `${ev.coverage.verified} of ${ev.coverage.journals} contributing journal(s) verified (${ev.coverage.verified_amount_percent}% of the amount); ` +
      `${ev.coverage.unverified} unverified, ${ev.coverage.defective} defective, ${ev.coverage.missing} without evidence.`) : null,
    ev.records.length ? h("div", { style: "overflow-x:auto;" }, h("table", { className: "data-table" },
      h("thead", {}, h("tr", {}, ["File", "Type", "Status", "Uploaded by", "Verified by", "SHA-256"].map((t) => h("th", {}, t)))),
      h("tbody", {}, ev.records.slice(0, 15).map((r) => h("tr", {},
        h("td", {}, r.path ? h("a", { href: `#${r.path}` }, r.filename) : r.filename),
        h("td", {}, nice(r.type)), h("td", {}, badge(nice(r.status), TONE[r.status] || (r.status === "REJECTED" ? "fail" : "neutral"))),
        h("td", {}, r.uploaded_by || ""), h("td", {}, r.verified_by || ""),
        h("td", {}, h("code", { style: "font-size:11px;", title: r.sha256 }, String(r.sha256 || "").slice(0, 12) + "…")))))))
      : null);
}

function journalBody(j) {
  if (!j.available) return unavailableNote(j);
  return h("div", {},
    h("div", { style: "margin-bottom:6px;" }, h("a", { href: `#${j.path}` }, h("strong", {}, j.number)), ` · ${j.date} · ${j.status} · ${j.currency} ${j.amount}`,
      j.period ? ` · period ${j.period.name} (${j.period.status})` : ""),
    h("div", { style: "font-size:12.5px; color: var(--ink-500); margin-bottom:6px;" },
      `Prepared by ${j.created_by || "unknown"}` + (j.posted_by ? `, posted by ${j.posted_by}` : ", not yet posted")),
    h("div", { style: "overflow-x:auto;" }, h("table", { className: "data-table" },
      h("thead", {}, h("tr", {}, ["Account", "Type", "Debit", "Credit"].map((t, i) => h("th", { style: i > 1 ? "text-align:right;" : undefined }, t)))),
      h("tbody", {}, j.lines.map((l) => h("tr", {}, h("td", {}, `${l.account_code || ""} ${l.account_name || "unknown account"}`.trim()),
        h("td", {}, nice(l.account_type)), h("td", { style: "text-align:right;" }, l.debit), h("td", { style: "text-align:right;" }, l.credit)))))));
}

function treatmentBody(t) {
  if (!t.available) return unavailableNote(t);
  const side = (rows) => rows.map((r) => `${r.account} (${nice(r.type)}) ${r.amount}`).join("; ");
  return h("div", {},
    t.proposed ? h("div", { style: "margin-bottom:4px;" }, badge("Proposed, not recorded", "warn")) : null,
    h("div", {}, h("strong", {}, nice(t.classification.code)), ": ", t.classification.meaning, "."),
    h("div", { style: "font-size:12.5px; color: var(--ink-500);" }, "Rule: " + t.classification.rule),
    (t.debits || []).length ? h("div", { style: "margin-top:4px;" }, "Debit: " + side(t.debits)) : null,
    (t.credits || []).length ? h("div", {}, "Credit: " + side(t.credits)) : null,
    t.description_check && t.description_check.status !== "NOT_APPLICABLE"
      ? h("div", { style: "margin-top:4px;" }, "Wording check: ", badge(nice(t.description_check.status), t.description_check.status === "MISMATCH" ? "fail" : t.description_check.status === "CONSISTENT" ? "pass" : "neutral"), " ", t.description_check.detail) : null,
    (t.policies || []).length ? h("div", { style: "margin-top:6px;" }, h("strong", {}, "Accounting policies"),
      h("ul", { style: "margin:4px 0 0; padding-left:18px;" }, t.policies.map((p) => h("li", {},
        `${p.name}: ${p.effective_label}` + (p.locked ? " (fixed by the framework)" : "") + `. Relevant because ${p.why_relevant}.`)))) : null,
    t.note ? h("div", { style: "font-size:12.5px; color: var(--ink-500); margin-top:6px;" }, t.note) : null);
}

function frameworkBody(f) {
  if (!f.available) return unavailableNote(f);
  return h("div", {},
    h("div", {}, h("strong", {}, f.framework), ` · ${f.jurisdiction} · ${f.entity_type}`),
    f.statements_affected.length ? h("div", { style: "margin-top:4px;" }, "Appears in: " + f.statements_affected.join("; ") + ".") : null,
    h("div", { style: "font-size:12.5px; color: var(--ink-500); margin-top:4px;" }, f.note));
}

function confidenceBody(c) {
  return h("div", {},
    h("div", {}, badge(c.level, TONE[c.level]), " ", h("strong", {}, `${c.score} / 100`)),
    h("div", { style: "overflow-x:auto; margin-top:6px;" }, h("table", { className: "data-table" },
      h("thead", {}, h("tr", {}, ["Factor", "Effect", "Why"].map((t) => h("th", {}, t)))),
      h("tbody", {}, c.factors.map((f) => h("tr", {}, h("td", {}, f.factor), h("td", {}, f.effect === 0 ? "none" : String(f.effect)), h("td", {}, f.detail)))))),
    h("div", { style: "font-size:12px; color: var(--ink-500); margin-top:6px;" }, c.how));
}

function reviewBody(r) {
  return h("div", {},
    h("div", {}, badge(r.required ? "Human review required" : "No extra review needed", r.required ? "warn" : "pass")),
    r.reasons && r.reasons.length ? bullets(r.reasons) : null,
    r.suggested_reviewer ? h("div", { style: "margin-top:4px;" }, `Suggested reviewer: ${r.suggested_reviewer}.`) : null,
    h("div", { style: "font-size:12.5px; color: var(--ink-500); margin-top:4px;" }, r.note));
}

/** The eight-link chain for one answer item. */
export function ChainView(item) {
  const parts = [
    step(1, "AI conclusion", "conclusion", h("div", {}, item.conclusion.summary), bullets(item.conclusion.points)),
    step(2, "Source records", "source_records", sourceChips(item.source_records)),
    step(3, "Evidence", "evidence", evidenceBody(item.evidence)),
    step(4, "Journal", "journal", journalBody(item.journal)),
    step(5, "Accounting treatment", "accounting_treatment", treatmentBody(item.accounting_treatment)),
    step(6, "Reporting framework", "reporting_framework", frameworkBody(item.reporting_framework)),
    step(7, "Confidence", "confidence", confidenceBody(item.confidence)),
    step(8, "Human review requirement", "human_review", reviewBody(item.human_review)),
  ];
  const out = [];
  parts.forEach((p, i) => { if (i) out.push(arrow()); out.push(p); });
  return h("div", { className: "ai-chain", style: "display:flex; flex-direction:column; gap:4px;" }, out);
}

// ------------------------------------------------------------------ mode extras
function flagsBlock(item) {
  if (!item.flags) return null;
  return h("div", { className: "ai-flags", style: "margin:8px 0;" },
    h("div", {}, badge(`${item.severity} priority`, SEVERITY_TONE[item.severity]), " ", `score ${item.score}`),
    h("ul", { style: "margin:6px 0 0; padding-left:18px;" }, item.flags.map((f) =>
      h("li", {}, h("strong", {}, f.label), ": ", f.detail, " ", badge(f.primary ? (f.kind === "STATISTICAL" ? "statistical" : "rule") : "supporting", "neutral")))));
}

function proposalBlock(item) {
  const p = item.proposal;
  if (!p) return null;
  const pe = p.proposed_entry;
  return h("div", { className: "ai-proposal", style: "border:1px dashed var(--line); border-radius:8px; padding:10px 14px; margin:8px 0;" },
    h("div", {}, badge("Proposal only, not applied", "warn"), " ", h("strong", {}, p.action)),
    h("div", { style: "margin-top:4px;" }, "Expected effect: " + p.expected_effect),
    pe ? h("div", { style: "margin-top:6px;" }, h("strong", {}, "Proposed entry (a person must draft, evidence and approve it)"),
      h("table", { className: "data-table" },
        h("thead", {}, h("tr", {}, ["Side", "Account", "Amount"].map((t) => h("th", {}, t)))),
        h("tbody", {}, pe.lines.map((l) => h("tr", {}, h("td", {}, nice(l.side)), h("td", {}, l.account || "Choose an account"), h("td", {}, `${pe.currency} ${l.amount}`))))),
      pe.needs_account_choice ? h("div", { className: "alert alert-info" }, "ASAVEXA could not tell which account the other side belongs to. A person must choose it.") : null) : null,
    p.where ? h("a", { className: "btn btn-secondary", href: `#${p.where}`, style: "display:inline-block; margin-top:8px;" }, "Open the place to do this") : null);
}

function checksBlock(item) {
  if (!item.checks) return null;
  return h("div", { className: "ai-checks", style: "margin:8px 0;" },
    h("div", {}, badge(nice(item.verdict).toUpperCase(), TONE[item.verdict])),
    h("table", { className: "data-table" },
      h("thead", {}, h("tr", {}, ["Check", "Result", "Detail"].map((t) => h("th", {}, t)))),
      h("tbody", {}, item.checks.map((c) => h("tr", {}, h("td", {}, c.label + (c.critical ? " *" : "")), h("td", {}, badge(nice(c.result), TONE[c.result])), h("td", {}, c.detail))))),
    h("div", { style: "font-size:12px; color: var(--ink-500);" }, "* a critical check: all must pass for the answer to count as proven."));
}

function contributionsBlock(item) {
  if (!item.contributions || !item.contributions.length) return null;
  return h("div", { style: "margin:8px 0;" }, h("strong", {}, "Journals behind this figure"),
    h("table", { className: "data-table" },
      h("thead", {}, h("tr", {}, ["Journal", "Date", "Description", "Contribution", "Evidence"].map((t) => h("th", {}, t)))),
      h("tbody", {}, item.contributions.slice(0, 20).map((r) => h("tr", {},
        h("td", {}, h("a", { href: `#${r.path}` }, r.journal_number)), h("td", {}, r.date), h("td", {}, r.description),
        h("td", { style: "text-align:right;" }, r.contribution), h("td", {}, badge(nice(r.evidence_state), TONE[r.evidence_state])))))));
}

function itemCard(item, i, open, { onToggle, onDrill }) {
  const subj = itemSubject(item);
  const tag = item.verdict ? badge(nice(item.verdict).toUpperCase(), TONE[item.verdict])
    : item.severity ? badge(item.severity, SEVERITY_TONE[item.severity])
    : item.proposal ? badge("Proposal", "info") : null;
  return h("div", { className: "card ai-item", "data-item": String(i) },
    h("div", { style: "display:flex; justify-content:space-between; gap:8px; align-items:flex-start; flex-wrap:wrap;" },
      h("div", {}, tag, " ", h("strong", {}, item.title),
        h("div", { style: "font-size:13px; margin-top:4px;" }, item.conclusion.summary),
        h("div", { style: "margin-top:4px;" }, badge(`${item.confidence.level} confidence (${item.confidence.score})`, TONE[item.confidence.level]), " ",
          badge(item.human_review.required ? "Needs human review" : "No extra review", item.human_review.required ? "warn" : "pass"))),
      h("div", { style: "display:flex; gap:6px; flex-wrap:wrap;" },
        subj && onDrill ? h("button", { className: "btn btn-secondary", "data-action": "explain", onClick: () => onDrill("EXPLAIN", subj) }, "Explain this") : null,
        subj && onDrill ? h("button", { className: "btn btn-secondary", "data-action": "prove", onClick: () => onDrill("PROVE", subj) }, "Prove this") : null,
        h("button", { className: "btn btn-secondary", "data-action": "toggle", onClick: () => onToggle(i) }, open ? "Hide the chain" : "Show the chain"))),
    open ? h("div", { style: "margin-top:12px;" }, flagsBlock(item), proposalBlock(item), checksBlock(item), contributionsBlock(item), ChainView(item)) : null);
}

/** One whole answer: what was understood, the summary, every grounded item, the limits. */
export function AiAnswer({ result, expanded, onToggle, onDrill }) {
  if (!result) return null;
  const ip = result.interpreted_as || {};
  const open = (i) => (expanded ? !!expanded[i] : i === 0);
  if (result.grounded === false) {
    const r = result.refusal || {};
    return h("div", { className: "card ai-answer", id: "ai-answer" },
      h("h2", {}, r.title || "I cannot answer that from your records"),
      h("div", { className: "alert alert-info", role: "status" }, r.reason || result.summary),
      (r.can_do || []).length ? h("div", {}, h("strong", {}, "Try one of these"), bullets(r.can_do)) : null,
      h("p", { style: "font-size:12.5px; color: var(--ink-500);" }, "ASAVEXA will not guess. Every answer must come from your own records."));
  }
  return h("div", { id: "ai-answer" },
    h("div", { className: "card" },
      h("div", { style: "display:flex; gap:8px; flex-wrap:wrap; align-items:center;" }, badge(MODE_INFO[result.mode] ? MODE_INFO[result.mode].label : result.mode, "info"),
        ip.subject_label ? h("span", { style: "color: var(--ink-500);" }, `Understood as: ${ip.subject_label}`) : null),
      h("h2", { style: "margin-top:8px;" }, result.summary),
      result.verdict ? h("div", {}, badge(nice(result.verdict).toUpperCase(), TONE[result.verdict])) : null,
      !result.items.length && result.mode !== "DETECT" && result.mode !== "RECOMMEND" ? null : null),
    result.items.map((it, i) => itemCard(it, i, open(i), { onToggle, onDrill })),
    result.rules ? h("div", { className: "card" }, h("h3", {}, "How Detect decides"),
      h("p", { style: "font-size:13px; margin-top:0;" }, "These are all of the rules. A journal appears only if at least one of the first kind fires."),
      h("ul", { style: "margin:0; padding-left:18px; font-size:13px;" }, result.rules.map((r) =>
        h("li", {}, r.label, " ", badge(r.kind === "STATISTICAL" ? "statistical" : "fact", "neutral"), " ", r.can_flag_alone ? "" : badge("supporting only", "neutral"))))) : null,
    h("div", { className: "card", style: "font-size:12.5px; color: var(--ink-500);" },
      h("strong", {}, "Limits of this answer"), bullets(result.limitations),
      h("p", {}, result.disclosure),
      h("div", {}, `Fingerprint ${String(result.fingerprint).slice(0, 16)}… · generated ${when(result.generated_at)} · reference ${String(result.response_id).slice(0, 8)}`)));
}

// ------------------------------------------------------------------ the page
function field(label, control) {
  return h("div", { className: "field", style: "margin-bottom:10px; min-width:220px;" }, h("label", {}, label), control);
}

function journalSelect(journals, value, onChange, id) {
  return h("select", { id, value, onChange: (e) => onChange(e.target.value) },
    h("option", { value: "" }, "Choose a journal…"),
    (journals || []).map((j) => h("option", { value: j.id, selected: j.id === value }, `${j.journal_number} · ${j.date} · ${j.description}`)));
}

function periodSelect(periods, value, onChange, id, any) {
  return h("select", { id, value, onChange: (e) => onChange(e.target.value) },
    any ? h("option", { value: "" }, "All periods") : h("option", { value: "" }, "Choose a period…"),
    (periods || []).map((p) => h("option", { value: p.id, selected: p.id === value }, p.name)));
}

function modeForm({ mode, form, journals, periods, onFormChange }) {
  const set = (k) => (v) => onFormChange(k, v);
  if (mode === "EXPLAIN") return field("Transaction (journal)", journalSelect(journals, form.journalId, set("journalId"), "ai-journal"));
  if (mode === "DETECT") return field("Look in", periodSelect(periods, form.periodId, set("periodId"), "ai-period", true));
  if (mode === "RECOMMEND") {
    return h("div", { style: "display:flex; gap:12px; flex-wrap:wrap;" },
      field("What kind", h("select", { id: "ai-scope", value: form.scope, onChange: (e) => onFormChange("scope", e.target.value) },
        RECOMMEND_SCOPES.map(([v, l]) => h("option", { value: v, selected: v === form.scope }, l)))),
      field("Look in", periodSelect(periods, form.periodId, set("periodId"), "ai-period", true)));
  }
  return h("div", { style: "display:flex; gap:12px; flex-wrap:wrap;" },
    field("Prove", h("select", { id: "ai-kind", value: form.kind, onChange: (e) => onFormChange("kind", e.target.value) },
      h("option", { value: "journal", selected: form.kind === "journal" }, "A transaction (journal)"),
      h("option", { value: "figure", selected: form.kind === "figure" }, "A reported figure"))),
    form.kind === "journal"
      ? field("Transaction (journal)", journalSelect(journals, form.journalId, set("journalId"), "ai-journal"))
      : h("div", { style: "display:flex; gap:12px; flex-wrap:wrap;" },
          field("Figure", h("select", { id: "ai-metric", value: form.metric, onChange: (e) => onFormChange("metric", e.target.value) },
            METRICS.map(([v, l]) => h("option", { value: v, selected: v === form.metric }, l)))),
          field("Period", periodSelect(periods, form.periodId, set("periodId"), "ai-period", false))));
}

export function AiAssistant(props) {
  const { role, loading, error, onRetry, mode, form, running, formError, question, result, resultError } = props;
  if (!allowed(role, PERMISSIONS.LEDGER_READ)) {
    return h("div", { className: "empty-state card" }, h("h3", {}, "You don't have access to this"),
      h("p", {}, "ASAVEXA AI reads the ledger, so it is available to roles that can read the ledger."));
  }
  const head = h("h1", {}, "ASAVEXA AI");
  if (loading && !props.journals) return h("div", {}, head, LoadingState("Loading your journals and periods…"));
  if (error && !props.journals) return h("div", {}, head, ErrorState({ message: error, onRetry }));
  const info = MODE_INFO[mode] || MODE_INFO.EXPLAIN;
  return h("div", {}, head,
    h("p", { style: "color: var(--ink-500); margin-top:-8px;" },
      "Explain, detect, recommend and prove, using only your own records. It uses no outside AI model, never guesses, and changes nothing: every answer shows its sources and says when a person must review it."),
    h("div", { className: "card", id: "ai-ask" },
      h("h2", {}, "Ask a question"),
      h("form", { onSubmit: (e) => { e.preventDefault(); props.onAsk(); }, style: "display:flex; gap:8px; flex-wrap:wrap;" },
        h("input", { type: "text", id: "ai-question", value: question || "", maxlength: 500, style: "flex:1; min-width:260px;",
          placeholder: "For example: Why was JRN-000001 classified this way?", onInput: (e) => props.onQuestionChange(e.target.value) }),
        h("button", { className: "btn btn-primary", id: "ai-ask-button", type: "submit", disabled: running }, running ? "Working…" : "Ask")),
      h("div", { style: "display:flex; gap:6px; flex-wrap:wrap; margin-top:8px;" }, SAMPLE_QUESTIONS.map((q) =>
        h("button", { className: "btn btn-secondary", type: "button", "data-sample": "1", disabled: running, onClick: () => props.onSample(q) }, q)))),
    h("div", { className: "card", id: "ai-modes" },
      h("div", { style: "display:flex; gap:6px; flex-wrap:wrap; margin-bottom:12px;" }, MODES.map((m) =>
        h("button", { className: `btn ${m === mode ? "btn-primary" : "btn-secondary"}`, "data-mode": m, "aria-pressed": String(m === mode), onClick: () => props.onModeChange(m) }, MODE_INFO[m].label))),
      h("div", { style: "font-size:15px; margin-bottom:10px;" }, h("strong", {}, info.prompt)),
      modeForm({ mode, form, journals: props.journals, periods: props.periods, onFormChange: props.onFormChange }),
      formError ? h("div", { className: "alert alert-error", role: "alert" }, formError) : null,
      h("button", { className: "btn btn-primary", id: "ai-run", disabled: running, onClick: props.onRun }, running ? "Working…" : info.button)),
    resultError ? h("div", { className: "alert alert-error", role: "alert", id: "ai-error" }, resultError) : null,
    running && !result ? LoadingState("Reading your records…") : null,
    AiAnswer({ result, expanded: props.expanded, onToggle: props.onToggle, onDrill: props.onDrill }));
}
