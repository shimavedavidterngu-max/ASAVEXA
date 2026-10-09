import { h } from "../lib/vdom.js";
import { LoadingState, ErrorState } from "../components/DataState.js";
import { allowed } from "../components/PermissionGate.js";
import { PERMISSIONS } from "../lib/permissions.js";
import { badge } from "./AiAssistant.js";

/**
 * Data Import. Pure render function; app.js owns the file, the form and every API call.
 *   choose what + file  ->  PREVIEW (nothing is written)  ->  read every problem  ->  confirm  ->  import
 * The page never decides what is importable: it shows the server's staged batch and its own verdict.
 */
export const PURPOSES = [
  { value: "BANK_STATEMENT", label: "Bank statement", perm: PERMISSIONS.RECONCILIATION_IMPORT, needsReconciliation: true,
    hint: "CSV, Excel, OFX, MT940, a PDF with text, or saved JSON from Plaid, Open Banking, Paystack, Flutterwave or Stripe.", accept: ".csv,.txt,.xlsx,.xlsm,.ofx,.qfx,.sta,.mt940,.pdf,.json" },
  { value: "DOCUMENT", label: "Invoice or receipt", perm: PERMISSIONS.EVIDENCE_UPLOAD,
    hint: "A PDF with text, a text file, or an image (images are stored but not read).", accept: ".pdf,.txt,.png,.jpg,.jpeg,.tif,.tiff,.webp" },
  { value: "PAYROLL", label: "Payroll register", perm: PERMISSIONS.EVIDENCE_UPLOAD,
    hint: "A CSV or Excel register from your payroll platform. It is checked and kept as evidence; nothing is posted.", accept: ".csv,.xlsx,.xlsm" },
  { value: "CHART_OF_ACCOUNTS", label: "Chart of accounts", perm: PERMISSIONS.ACCOUNT_MANAGE, needsCurrency: true,
    hint: "A CSV or Excel export from Xero, QuickBooks, Sage or similar (Code, Name, Type).", accept: ".csv,.xlsx,.xlsm" },
  { value: "JOURNALS", label: "Journals", perm: PERMISSIONS.JOURNAL_CREATE, needsCurrency: true,
    hint: "A journal export (Date, Journal number, Account, Debit, Credit). Imported as drafts for someone else to post.", accept: ".csv,.xlsx,.xlsm" },
];
export const DATE_FORMATS = ["YYYY-MM-DD", "DD/MM/YYYY", "MM/DD/YYYY", "DD-MM-YYYY", "MM-DD-YYYY", "DD.MM.YYYY", "DD/MM/YY", "MM/DD/YY", "DD-Mon-YYYY", "DD Mon YYYY", "YYYYMMDD"];
export const MAP_ROLES = [["date", "Date"], ["description", "Description"], ["amount", "One amount column (+in / -out)"], ["debit", "Money out (Debit)"],
  ["credit", "Money in (Credit)"], ["balance", "Running balance"], ["reference", "Reference"], ["dr_cr", "DR/CR marker"], ["value_date", "Value date"], ["currency", "Currency"]];
const STATUS_TONE = { WORKING: "pass", PARTIAL: "warn", FILES_ONLY: "neutral", PAYLOAD_ONLY: "neutral" };
const STATUS_LABEL = { WORKING: "Working", PARTIAL: "Partly", FILES_ONLY: "Files only", PAYLOAD_ONLY: "Saved data only" };
const ROW_TONE = { OK: "pass", WARNING: "warn", ERROR: "fail" };

export function purposeInfo(v) { return PURPOSES.find((p) => p.value === v) || PURPOSES[0]; }
export function allowedPurposes(role) { return PURPOSES.filter((p) => allowed(role, p.perm)); }

export function newImportForm(purpose = "BANK_STATEMENT") {
  return { purpose, reconciliationId: "", currency: "", headerRow: "", dateFormat: "", flip: false, sheet: "", docType: "", evidenceType: "", mapping: {} };
}

/** Pure: plain-English problem with the form before anything is sent, or null. */
export function validateImportForm(f, file) {
  const p = purposeInfo(f.purpose);
  if (!file) return "Choose the file first.";
  if (p.needsReconciliation && !f.reconciliationId) return "Choose the reconciliation this statement belongs to.";
  if (p.needsCurrency && !/^[A-Za-z]{3}$/.test((f.currency || "").trim())) return "Type the 3-letter currency code, for example NGN.";
  if (f.headerRow !== "" && !(Number.isInteger(Number(f.headerRow)) && Number(f.headerRow) >= 1 && Number(f.headerRow) <= 100)) return "The heading row must be a whole number from 1 to 100.";
  return null;
}

/** Pure: the options object sent to the server (empty things are left out so the server can auto-detect). */
export function buildImportOptions(f) {
  const o = {};
  if (f.headerRow !== "") o.header_row = Number(f.headerRow) - 1;
  const mapping = Object.fromEntries(Object.entries(f.mapping || {}).filter(([, v]) => v !== undefined));
  if (Object.keys(mapping).length) o.mapping = mapping;
  if (f.dateFormat) o.date_format = f.dateFormat;
  if (f.flip) o.flip = true;
  if (f.sheet && f.sheet.trim()) o.sheet = f.sheet.trim();
  if (f.docType) o.doc_type = f.docType;
  return o;
}

export function buildImportArgs(f, file) {
  const p = purposeInfo(f.purpose);
  return { file, purpose: f.purpose, reconciliationId: p.needsReconciliation ? f.reconciliationId : undefined,
    currency: p.needsCurrency ? f.currency.trim().toUpperCase() : undefined, options: buildImportOptions(f) };
}

function formatMoney(v) {
  const s = String(v);
  const [i, d] = s.replace("-", "").split(".");
  return (s.startsWith("-") ? "-" : "") + i.replace(/\B(?=(\d{3})+(?!\d))/g, ",") + (d !== undefined ? "." + d : "");
}
export { formatMoney };

function bullets(points) { return h("ul", { style: "margin:6px 0 0; padding-left:18px;" }, (points || []).map((p) => h("li", {}, p))); }
function field(label, control, hint) {
  return h("div", { className: "field", style: "margin-bottom:10px; min-width:220px;" }, h("label", {}, label), control, hint ? h("div", { style: "font-size:12px; color: var(--ink-500); margin-top:3px;" }, hint) : null);
}

export function LevelLadder(levels) {
  if (!levels) return null;
  return h("div", { className: "card", id: "import-levels" },
    h("h2", {}, "What ASAVEXA can read today"),
    h("table", { className: "data-table" },
      h("thead", {}, h("tr", {}, ["Level", "Source", "Status", "Notes"].map((t) => h("th", {}, t)))),
      h("tbody", {}, levels.map((l) => h("tr", {}, h("td", {}, String(l.level)), h("td", {}, l.name),
        h("td", {}, badge(STATUS_LABEL[l.status] || l.status, STATUS_TONE[l.status])), h("td", { style: "font-size:13px;" }, l.note))))),
    h("p", { style: "font-size:12.5px; color: var(--ink-500); margin-bottom:0;" },
      "ASAVEXA is not connected to any bank, accounting product or payment platform. It reads the files and saved data you give it."));
}

// ------------------------------------------------------------------ the preview
function summaryCards(batch) {
  const s = batch.summary || {};
  const cells = [];
  const add = (label, value) => { if (value !== undefined && value !== null && value !== "") cells.push([label, value]); };
  if (batch.kind === "BANK_TRANSACTIONS") {
    add("Lines", s.lines); add("Money in", formatMoney(s.money_in_total)); add("Money out", formatMoney(s.money_out_total)); add("Net", formatMoney(s.net));
    add("First date", s.first_date); add("Last date", s.last_date);
    if (s.opening_balance) add("Opening balance", formatMoney(s.opening_balance));
    if (s.closing_balance) add("Closing balance", formatMoney(s.closing_balance));
    if (s.already_imported !== undefined) { add("Already in ASAVEXA", s.already_imported); add("To import", s.to_import); }
  } else if (batch.kind === "PAYROLL") {
    add("Employees", s.employees); add("Gross", formatMoney(s.total_gross)); add("PAYE", formatMoney(s.total_tax)); add("Pension", formatMoney(s.total_pension)); add("Net pay", formatMoney(s.total_net));
  } else if (batch.kind === "CHART_OF_ACCOUNTS") {
    add("Accounts", s.accounts); add("New", s.new); add("Already exist", s.already_exist);
  } else if (batch.kind === "JOURNALS") {
    add("Journals", s.journals); add("Valid", s.valid); add("Lines", s.lines);
  }
  return h("div", { className: "import-summary", style: "display:flex; gap:10px; flex-wrap:wrap; margin:10px 0;" }, cells.map(([l, v]) =>
    h("div", { style: "border:1px solid var(--line); border-radius:8px; padding:8px 12px; min-width:110px;" },
      h("div", { style: "font-size:12px; color: var(--ink-500);" }, l), h("div", { style: "font-weight:600;" }, String(v)))));
}

function checksBlock(checks) {
  if (!checks || !checks.length) return null;
  return h("div", { id: "import-checks", style: "margin:10px 0;" }, h("strong", {}, "Checks"),
    h("table", { className: "data-table" }, h("tbody", {}, checks.map((c) => h("tr", {},
      h("td", {}, badge(c.result === "NOT_APPLICABLE" ? "N/A" : c.result, c.result === "PASS" ? "pass" : c.result === "FAIL" ? "fail" : "neutral")), h("td", {}, c.label), h("td", { style: "font-size:13px;" }, c.detail))))));
}

function issuesBlock(batch) {
  const items = (batch.issues || []);
  if (!items.length) return null;
  return h("div", { id: "import-issues" }, items.map((i) => h("div", { className: `alert ${i.level === "ERROR" ? "alert-error" : "alert-info"}`, role: i.level === "ERROR" ? "alert" : "status" }, i.message)));
}

function mappingBlock(batch, form, onMappingChange) {
  if (!batch.columns) return null;
  const cols = batch.columns;
  const chosen = (role) => (form.mapping && form.mapping[role] !== undefined ? form.mapping[role] : (batch.mapping || {})[role] || "");
  return h("details", { id: "import-mapping", open: !(batch.status && batch.status.importable), style: "margin:10px 0;" }, h("summary", {}, "Columns were read like this. Change them if they are wrong"),
    h("div", { style: "display:flex; gap:10px; flex-wrap:wrap; margin-top:8px;" }, MAP_ROLES.map(([role, label]) =>
      field(label, h("select", { "data-role": role, value: chosen(role), onChange: (e) => onMappingChange(role, e.target.value) },
        h("option", { value: "" }, "(none)"), cols.map((c) => h("option", { value: c, selected: c === chosen(role) }, c)))))));
}

function bankRows(batch, onlyProblems) {
  const rows = (batch.rows || []).filter((r) => !onlyProblems || r.status !== "OK");
  const shown = rows.slice(0, 200);
  return h("div", {}, h("table", { className: "data-table", id: "import-rows" },
    h("thead", {}, h("tr", {}, ["Row", "", "Date", "Description", "Money in", "Money out", "Balance", "Notes"].map((t) => h("th", {}, t)))),
    h("tbody", {}, shown.map((r) => h("tr", { "data-row-status": r.status },
      h("td", {}, String(r.row)), h("td", {}, badge(r.already_imported ? "Already in" : r.status, r.already_imported ? "neutral" : ROW_TONE[r.status])),
      h("td", {}, r.date || ""), h("td", {}, r.description), h("td", { style: "text-align:right;" }, r.money_in === "0.00" ? "" : formatMoney(r.money_in)),
      h("td", { style: "text-align:right;" }, r.money_out === "0.00" ? "" : formatMoney(r.money_out)), h("td", { style: "text-align:right;" }, r.balance ? formatMoney(r.balance) : ""),
      h("td", { style: "font-size:12.5px;" }, (r.issues || []).map((i) => i.message).join(" ")))))),
    rows.length > shown.length ? h("div", { style: "font-size:12.5px; color: var(--ink-500);" }, `Showing the first ${shown.length} of ${rows.length}.`) : null,
    batch.rows_total ? h("div", { style: "font-size:12.5px; color: var(--ink-500);" }, `The file has ${batch.rows_total} lines; the page shows the first ${batch.rows.length}. All of them are imported.`) : null);
}

function documentBlock(batch) {
  const d = batch.document || {};
  if (d.type === "UNREAD") return h("div", { className: "alert alert-info" }, d.reason || "This file was not read.");
  const f = d.fields || {};
  const names = { vendor: "Supplier / shop", document_number: "Number", issue_date: "Date", due_date: "Due date", subtotal: "Subtotal", tax: "Tax", total: "Total", currency: "Currency", tax_id: "Tax ID" };
  return h("div", {}, h("div", {}, badge(d.type, d.type === "UNKNOWN" ? "warn" : "info"), " ", "Read from the document. A person must still check these against it."),
    h("table", { className: "data-table", id: "import-fields" },
      h("thead", {}, h("tr", {}, ["Field", "Value", "How sure", "Where it came from"].map((t) => h("th", {}, t)))),
      h("tbody", {}, Object.keys(names).filter((k) => f[k]).map((k) => h("tr", {}, h("td", {}, names[k]), h("td", {}, ["subtotal", "tax", "total"].includes(k) ? formatMoney(f[k].value) : String(f[k].value ?? "not readable")),
        h("td", {}, badge(f[k].confidence, f[k].confidence === "HIGH" ? "pass" : f[k].confidence === "MEDIUM" ? "warn" : "fail")), h("td", { style: "font-size:12.5px;" }, [f[k].source_line, f[k].note].filter(Boolean).join(" · ")))))),
    proposalBlock(batch.proposal));
}

function proposalBlock(p) {
  if (!p) return null;
  return h("div", { className: "ai-proposal", style: "border:1px dashed var(--line); border-radius:8px; padding:10px 14px; margin:10px 0;" },
    h("div", {}, badge("Proposal only, not applied", "warn"), " ", h("strong", {}, p.action)),
    h("table", { className: "data-table" }, h("tbody", {}, p.lines.map((l) => h("tr", {}, h("td", {}, l.side === "DEBIT" ? "Debit" : "Credit"), h("td", {}, l.account || "Choose an account"), h("td", { style: "text-align:right;" }, formatMoney(l.amount)), h("td", { style: "font-size:12.5px;" }, l.note))))),
    h("div", { style: "font-size:12.5px; color: var(--ink-500);" }, p.note));
}

function payrollRows(batch) {
  return h("table", { className: "data-table", id: "import-rows" },
    h("thead", {}, h("tr", {}, ["Row", "", "Employee", "Gross", "PAYE", "Pension", "Net", "Notes"].map((t) => h("th", {}, t)))),
    h("tbody", {}, (batch.rows || []).map((r) => h("tr", { "data-row-status": r.status }, h("td", {}, String(r.row)), h("td", {}, badge(r.status, ROW_TONE[r.status])), h("td", {}, r.employee),
      ["gross", "tax", "pension", "net"].map((k) => h("td", { style: "text-align:right;" }, formatMoney(r[k]))), h("td", { style: "font-size:12.5px;" }, (r.issues || []).map((i) => i.message).join(" "))))));
}

function accountRows(batch) {
  return h("table", { className: "data-table", id: "import-rows" },
    h("thead", {}, h("tr", {}, ["Row", "", "Code", "Name", "Type in file", "Becomes", "Notes"].map((t) => h("th", {}, t)))),
    h("tbody", {}, (batch.rows || []).map((r) => h("tr", { "data-row-status": r.status }, h("td", {}, String(r.row)), h("td", {}, badge(r.already_exists ? "Exists" : r.status, r.already_exists ? "neutral" : ROW_TONE[r.status])),
      h("td", {}, r.code), h("td", {}, r.name), h("td", {}, r.source_type), h("td", {}, r.type || "?"), h("td", { style: "font-size:12.5px;" }, (r.issues || []).map((i) => i.message).join(" "))))));
}

function journalRows(batch) {
  return h("div", { id: "import-rows" }, (batch.rows || []).map((j) => h("div", { className: "card", "data-row-status": j.status, style: "margin:8px 0;" },
    h("div", {}, badge(j.status, ROW_TONE[j.status]), " ", h("strong", {}, `Journal ${j.journal}`), ` · ${j.date || "no date"} · ${j.currency} ${formatMoney(j.total)} · ${j.description}`),
    (j.issues || []).map((i) => h("div", { className: "alert alert-error" }, i.message)),
    h("table", { className: "data-table" }, h("tbody", {}, j.lines.map((l) => h("tr", {}, h("td", {}, l.account || `? ${l.account_ref}`), h("td", { style: "text-align:right;" }, l.debit === "0.00" ? "" : formatMoney(l.debit)),
      h("td", { style: "text-align:right;" }, l.credit === "0.00" ? "" : formatMoney(l.credit)), h("td", { style: "font-size:12.5px;" }, (l.issues || []).map((i) => i.message).join(" ")))))))));
}

export function PreviewView({ batch, form, onMappingChange, onlyProblems, onToggleProblems }) {
  const st = batch.status;
  const src = batch.source || {};
  const body = batch.kind === "BANK_TRANSACTIONS" ? bankRows(batch, onlyProblems) : batch.kind === "PAYROLL" ? h("div", {}, payrollRows(batch), proposalBlock(batch.proposal))
    : batch.kind === "CHART_OF_ACCOUNTS" ? accountRows(batch) : batch.kind === "JOURNALS" ? journalRows(batch) : documentBlock(batch);
  return h("div", { className: "card", id: "import-preview" },
    h("h2", {}, "2. Check what was read"),
    h("div", { style: "font-size:13px; color: var(--ink-500);" }, `${src.filename} · ${src.format || src.detected_as}${src.sheet ? ` · sheet ${src.sheet}` : ""}${src.provider_label ? ` · ${src.provider_label}` : ""}${src.looks_like && src.looks_like !== "GENERIC" ? ` · looks like ${src.looks_like}` : ""} · SHA-256 ${String(src.sha256).slice(0, 12)}…`),
    h("div", { style: "margin-top:8px;" },
      st.errors ? badge(`${st.errors} error(s). Cannot import`, "fail") : badge("No errors", "pass"), " ",
      st.warnings ? badge(`${st.warnings} warning(s)`, "warn") : null, " ", st.failed_checks ? badge(`${st.failed_checks} failed check(s)`, "fail") : null),
    summaryCards(batch), issuesBlock(batch), checksBlock(batch.checks),
    batch.kind === "BANK_TRANSACTIONS" ? mappingBlock(batch, form, onMappingChange) : null,
    batch.kind === "BANK_TRANSACTIONS" && (batch.status.warnings || batch.status.errors)
      ? h("label", { style: "display:block; margin:8px 0;" }, h("input", { type: "checkbox", id: "import-only-problems", checked: !!onlyProblems, onChange: onToggleProblems }), " Show only lines with problems") : null,
    body,
    h("h4", { style: "margin-bottom:4px;" }, "Limits"), bullets(batch.limits));
}

function confirmBlock(props) {
  const { batch, ack, onAck, onCommit, committing, commitError, form } = props;
  const st = batch.status;
  const p = purposeInfo(form.purpose);
  const needsAck = st.needs_acknowledgement;
  const can = st.importable && (!needsAck || ack) && !committing;
  const verb = form.purpose === "BANK_STATEMENT" ? "Import into the reconciliation" : form.purpose === "CHART_OF_ACCOUNTS" ? "Create the accounts"
    : form.purpose === "JOURNALS" ? "Create draft journals" : "Store as evidence";
  return h("div", { className: "card", id: "import-confirm" },
    h("h2", {}, "3. Confirm"),
    form.purpose === "BANK_STATEMENT" ? h("p", {}, "Lines go into the DRAFT reconciliation and are matched to posted ledger entries. The file is kept as unverified evidence. Nothing is posted.") : null,
    form.purpose === "JOURNALS" ? h("p", {}, "Journals are created as drafts. Someone other than you must post them.") : null,
    form.purpose === "DOCUMENT" || form.purpose === "PAYROLL" ? h("p", {}, "The file is stored in the Evidence Vault as unverified. A different person must verify it. No journal is created.") : null,
    form.purpose === "DOCUMENT" || form.purpose === "PAYROLL" ? field("Store it as", h("select", { id: "import-evidence-type", value: form.evidenceType || "", onChange: (e) => props.onFormChange("evidenceType", e.target.value) },
      [["", "Choose automatically"], ["INVOICE", "Invoice"], ["RECEIPT", "Receipt"], ["CONTRACT", "Contract"], ["TAX_DOCUMENT", "Tax document"], ["PAYROLL_EVIDENCE", "Payroll evidence"], ["OTHER", "Other"]]
        .map(([v, l]) => h("option", { value: v, selected: v === (form.evidenceType || "") }, l)))) : null,
    !st.importable ? h("div", { className: "alert alert-error", role: "alert" }, "Fix the errors above (in the file, or by choosing the right columns / date format) and read the file again. Nothing has been imported.") : null,
    needsAck && st.importable ? h("label", { style: "display:block; margin:8px 0;" }, h("input", { type: "checkbox", id: "import-ack", checked: !!ack, onChange: (e) => onAck(e.target.checked) }),
      " I have read the warnings and checked the totals against the original, and I accept them.") : null,
    commitError ? h("div", { className: "alert alert-error", role: "alert", id: "import-commit-error" }, commitError) : null,
    h("button", { className: "btn btn-primary", id: "import-commit", disabled: !can, onClick: onCommit }, committing ? "Importing…" : verb));
}

function resultBlock(props) {
  const { result, form, onReset, onNavigate } = props;
  const r = result.result;
  const lines = [];
  if (form.purpose === "BANK_STATEMENT") {
    lines.push(`${r.imported} line(s) imported.`);
    if (r.skipped_already_imported) lines.push(`${r.skipped_already_imported} line(s) were already there and were skipped.`);
    lines.push(`${r.matched_automatically} matched a posted ledger entry automatically; the rest need a person to match or explain them.`);
    lines.push(r.evidence_is_new ? "The statement file was stored as unverified evidence." : "This exact file was already in the Evidence Vault; the existing record was used.");
    if (!r.evidence_linked_to_reconciliation) lines.push("This reconciliation already had a different statement attached, so it was left as it was.");
  } else if (form.purpose === "CHART_OF_ACCOUNTS") lines.push(`${r.created} account(s) created, ${r.skipped_existing} already existed.`);
  else if (form.purpose === "JOURNALS") lines.push(`${r.drafts_created} draft journal(s) created: ${(r.journals || []).map((j) => j.journal_number).join(", ")}. ${r.note}`);
  else lines.push(`Stored as ${r.type} evidence. ${r.note}`);
  return h("div", { className: "card", id: "import-result" },
    h("h2", {}, "Done"), h("div", { className: "alert alert-info", role: "status" }, bullets(lines)),
    h("div", { style: "display:flex; gap:8px; flex-wrap:wrap; margin-top:10px;" },
      form.purpose === "BANK_STATEMENT" ? h("button", { className: "btn btn-primary", "data-go": "reconciliation", onClick: () => onNavigate(`/reconciliation/${form.reconciliationId}`) }, "Open the reconciliation") : null,
      form.purpose === "JOURNALS" ? h("button", { className: "btn btn-primary", "data-go": "accounting", onClick: () => onNavigate("/accounting") }, "Open Accounting") : null,
      form.purpose === "DOCUMENT" || form.purpose === "PAYROLL" ? h("button", { className: "btn btn-primary", "data-go": "evidence", onClick: () => onNavigate("/evidence") }, "Open Evidence") : null,
      h("button", { className: "btn btn-secondary", id: "import-another", onClick: onReset }, "Import another file")));
}

export function DataImport(props) {
  const { role, loading, error, onRetry, form, file, previewing, previewError, batch, result } = props;
  const offered = allowedPurposes(role);
  const head = h("h1", {}, "Data Import");
  if (!offered.length) return h("div", { className: "empty-state card" }, h("h3", {}, "You don't have access to this"),
    h("p", {}, "Importing needs permission to import bank lines, upload evidence, manage accounts or create journals."));
  if (loading && !props.reconciliations) return h("div", {}, head, LoadingState("Loading…"));
  if (error && !props.reconciliations) return h("div", {}, head, ErrorState({ message: error, onRetry }));
  const p = purposeInfo(form.purpose);
  const recs = (props.reconciliations || []).filter((r) => r.status === "DRAFT");
  return h("div", {}, head,
    h("p", { style: "color: var(--ink-500); margin-top:-8px;" },
      "Bring in files from outside. You always see what was read, and every problem, before anything is imported. Nothing is ever posted automatically."),
    result ? resultBlock(props) : h("div", {},
      h("div", { className: "card", id: "import-form" },
        h("h2", {}, "1. Choose the file"),
        field("What are you importing?", h("select", { id: "import-purpose", value: form.purpose, onChange: (e) => props.onPurpose(e.target.value) },
          offered.map((o) => h("option", { value: o.value, selected: o.value === form.purpose }, o.label))), p.hint),
        p.needsReconciliation ? field("Reconciliation (the bank account and period)", h("select", { id: "import-reconciliation", value: form.reconciliationId, onChange: (e) => props.onFormChange("reconciliationId", e.target.value) },
          h("option", { value: "" }, recs.length ? "Choose a draft reconciliation…" : "No draft reconciliation. Create one first"),
          recs.map((r) => h("option", { value: r.id, selected: r.id === form.reconciliationId }, `${r.name} · ${r.currency} · ${r.period_start} to ${r.period_end}`)))) : null,
        p.needsCurrency ? field("Currency", h("input", { type: "text", id: "import-currency", maxlength: 3, value: form.currency, style: "width:90px; text-transform:uppercase;", placeholder: "NGN", onInput: (e) => props.onFormChange("currency", e.target.value) })) : null,
        field("File", h("input", { type: "file", id: "import-file", accept: p.accept, onChange: (e) => props.onFile(e.target.files && e.target.files[0]) }),
          file ? `Selected: ${file.name} (${Math.max(1, Math.round(file.size / 1024))} KB)` : "Maximum 10 MB."),
        h("details", { id: "import-advanced", style: "margin:6px 0 10px;" }, h("summary", {}, "Options (only if the preview reads the file wrongly)"),
          h("div", { style: "display:flex; gap:12px; flex-wrap:wrap; margin-top:8px;" },
            field("Heading row number", h("input", { type: "number", id: "import-header-row", min: 1, max: 100, value: form.headerRow, style: "width:90px;", onInput: (e) => props.onFormChange("headerRow", e.target.value) }), "Leave empty to find it automatically."),
            field("Date format", h("select", { id: "import-date-format", value: form.dateFormat, onChange: (e) => props.onFormChange("dateFormat", e.target.value) },
              h("option", { value: "" }, "Detect automatically"), DATE_FORMATS.map((d) => h("option", { value: d, selected: d === form.dateFormat }, d)))),
            field("Excel sheet name", h("input", { type: "text", id: "import-sheet", value: form.sheet, onInput: (e) => props.onFormChange("sheet", e.target.value) })),
            form.purpose === "DOCUMENT" ? field("This is a", h("select", { id: "import-doc-type", value: form.docType, onChange: (e) => props.onFormChange("docType", e.target.value) },
              [["", "Detect automatically"], ["INVOICE", "Invoice"], ["RECEIPT", "Receipt"]].map(([v, l]) => h("option", { value: v, selected: v === form.docType }, l)))) : null),
          form.purpose === "BANK_STATEMENT" ? h("label", { style: "display:block;" }, h("input", { type: "checkbox", id: "import-flip", checked: !!form.flip, onChange: (e) => props.onFormChange("flip", e.target.checked) }),
            " Swap money in and money out (only if this bank's file shows them the other way round)") : null),
        props.formError ? h("div", { className: "alert alert-error", role: "alert", id: "import-form-error" }, props.formError) : null,
        previewError ? h("div", { className: "alert alert-error", role: "alert", id: "import-preview-error" }, previewError) : null,
        h("button", { className: "btn btn-primary", id: "import-preview-button", disabled: previewing, onClick: props.onPreview }, previewing ? "Reading the file…" : "Read the file and show me")),
      batch ? PreviewView({ batch, form, onMappingChange: props.onMappingChange, onlyProblems: props.onlyProblems, onToggleProblems: props.onToggleProblems }) : null,
      batch ? confirmBlock(props) : null),
    LevelLadder(props.levels));
}
