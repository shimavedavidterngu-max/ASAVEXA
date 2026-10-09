import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { DataImport, PreviewView, LevelLadder, PURPOSES, allowedPurposes, newImportForm, validateImportForm, buildImportOptions, buildImportArgs, formatMoney } from "../src/pages/DataImport.js";
import { ApiClient } from "../src/api/client.js";

// Fixture = output of the REAL ingestion readers and checks (see tests/test_ingestion*.py): the page is tested against actual response shapes.
const F = JSON.parse(readFileSync(new URL("./fixtures/import-scenario.json", import.meta.url), "utf8"));
const text = (v) => JSON.stringify(v);
function find(v, pred, acc = []) { if (!v || typeof v !== "object") return acc; if (pred(v)) acc.push(v); for (const c of v.children || []) find(c, pred, acc); return acc; }
const noop = () => {};
const file = { name: "jan.csv", size: 2048 };
const base = {
  role: "ACCOUNTANT", form: newImportForm(), file: null, reconciliations: [{ id: "r1", name: "Jan", currency: "NGN", status: "DRAFT", period_start: "2026-01-01", period_end: "2026-01-31" }, { id: "r2", name: "Old", currency: "NGN", status: "RECONCILED", period_start: "2025-01-01", period_end: "2025-01-31" }],
  levels: [{ level: 1, name: "CSV files", status: "WORKING", note: "n" }, { level: 7, name: "Bank APIs", status: "PAYLOAD_ONLY", note: "Not connected" }],
  onPurpose: noop, onFormChange: noop, onFile: noop, onPreview: noop, onMappingChange: noop, onToggleProblems: noop, onAck: noop, onCommit: noop, onReset: noop, onNavigate: noop, onRetry: noop,
};
const withBatch = (b, extra = {}) => ({ ...base, file, batch: b, ...extra });

describe("form helpers", () => {
  test("money formatting", () => {
    assert.equal(formatMoney("1234567.50"), "1,234,567.50");
    assert.equal(formatMoney("-1200.00"), "-1,200.00");
    assert.equal(formatMoney("0.00"), "0.00");
  });
  test("validateImportForm", () => {
    const f = newImportForm("BANK_STATEMENT");
    assert.match(validateImportForm(f, null), /Choose the file/);
    assert.match(validateImportForm(f, file), /reconciliation/);
    assert.equal(validateImportForm({ ...f, reconciliationId: "r1" }, file), null);
    assert.match(validateImportForm({ ...newImportForm("JOURNALS") }, file), /currency/);
    assert.equal(validateImportForm({ ...newImportForm("JOURNALS"), currency: "ngn" }, file), null);
    assert.match(validateImportForm({ ...f, reconciliationId: "r1", headerRow: "0" }, file), /heading row/);
    assert.match(validateImportForm({ ...f, reconciliationId: "r1", headerRow: "2.5" }, file), /heading row/);
    assert.equal(validateImportForm(newImportForm("DOCUMENT"), file), null);
  });
  test("buildImportOptions leaves empty things out and converts the heading row to 0-based", () => {
    assert.deepEqual(buildImportOptions(newImportForm()), {});
    const o = buildImportOptions({ ...newImportForm(), headerRow: "4", dateFormat: "DD/MM/YYYY", flip: true, sheet: " Stmt ", docType: "INVOICE", mapping: { amount: "Value", debit: "" } });
    assert.deepEqual(o, { header_row: 3, date_format: "DD/MM/YYYY", flip: true, sheet: "Stmt", doc_type: "INVOICE", mapping: { amount: "Value", debit: "" } });
  });
  test("buildImportArgs sends only what the purpose needs", () => {
    const a = buildImportArgs({ ...newImportForm("BANK_STATEMENT"), reconciliationId: "r1", currency: "usd" }, file);
    assert.equal(a.reconciliationId, "r1"); assert.equal(a.currency, undefined);
    const b = buildImportArgs({ ...newImportForm("JOURNALS"), reconciliationId: "r1", currency: " ngn " }, file);
    assert.equal(b.reconciliationId, undefined); assert.equal(b.currency, "NGN");
  });
  test("each role is offered only the imports it may do", () => {
    const names = (r) => allowedPurposes(r).map((p) => p.value);
    assert.deepEqual(names("OWNER").sort(), PURPOSES.map((p) => p.value).sort());
    assert.deepEqual(names("ADMINISTRATOR"), ["CHART_OF_ACCOUNTS"]);
    assert.deepEqual(names("AUDITOR"), []);
    assert.ok(!names("APPROVER").includes("BANK_STATEMENT"));
  });
});

describe("page", () => {
  test("no access for roles that cannot import anything", () => {
    assert.ok(text(DataImport({ ...base, role: "AUDITOR" })).includes("don't have access"));
  });
  test("loading and error states", () => {
    assert.ok(text(DataImport({ ...base, reconciliations: null, loading: true })).includes("Loading"));
    assert.ok(text(DataImport({ ...base, reconciliations: null, error: "boom" })).includes("boom"));
  });
  test("the form offers only DRAFT reconciliations and states the safety promise", () => {
    const t = text(DataImport(base));
    assert.ok(t.includes("Jan") && !t.includes("Old"));
    assert.ok(t.includes("Nothing is ever posted automatically"));
  });
  test("the level ladder is honest: files only / saved data only, never 'live'", () => {
    const t = text(LevelLadder(base.levels));
    assert.ok(t.includes("Saved data only") && t.includes("Working") && t.includes("not connected to any bank"));
    assert.ok(!/\bLive\b/.test(t));
  });
  test("the preview button calls back; a validation message is shown", () => {
    let n = 0;
    const root = DataImport({ ...base, onPreview: () => n++, formError: "Choose the file first." });
    find(root, (x) => x.props && x.props.id === "import-preview-button")[0].props.onClick();
    assert.equal(n, 1);
    assert.ok(text(root).includes("Choose the file first."));
  });
});

describe("preview of real batches", () => {
  test("a clean statement: totals, checks, rows and an enabled import button", () => {
    const root = DataImport(withBatch(F.good));
    const t = text(root);
    assert.ok(t.includes("No errors") && t.includes("Money in") && t.includes("7,500.00"));
    assert.ok(t.includes("Running balance adds up"));
    const btn = find(root, (x) => x.props && x.props.id === "import-commit")[0];
    assert.equal(btn.props.disabled, false);
    assert.equal(find(root, (x) => x.props && x.props.id === "import-ack").length, 0, "no acknowledgement needed without warnings");
  });
  test("errors block the import and say so; the button is disabled", () => {
    const root = DataImport(withBatch(F.bad));
    const t = text(root);
    assert.ok(t.includes("Cannot import") && t.includes("Nothing has been imported"));
    assert.equal(find(root, (x) => x.props && x.props.id === "import-commit")[0].props.disabled, true);
    assert.ok(t.includes("could not be read") && t.includes("more than two decimal places"));
  });
  test("warnings need the tick box before the button works", () => {
    const off = DataImport(withBatch(F.dup, { ack: false }));
    assert.equal(find(off, (x) => x.props && x.props.id === "import-commit")[0].props.disabled, true);
    assert.equal(find(off, (x) => x.props && x.props.id === "import-ack").length, 1);
    const on = DataImport(withBatch(F.dup, { ack: true }));
    assert.equal(find(on, (x) => x.props && x.props.id === "import-commit")[0].props.disabled, false);
  });
  test("a failed running-balance check is shown and needs acknowledgement", () => {
    const root = DataImport(withBatch(F.brk, { ack: false }));
    assert.ok(text(root).includes("do not follow from the one before"));
    assert.equal(find(root, (x) => x.props && x.props.id === "import-commit")[0].props.disabled, true);
  });
  test("lines already in ASAVEXA are labelled and counted", () => {
    const t = text(DataImport(withBatch(F.overlap)));
    assert.ok(t.includes("Already in") && t.includes("To import"));
  });
  test("the column mapping shows what was detected and lets it be changed", () => {
    let got = null;
    const root = PreviewView({ batch: F.good, form: newImportForm(), onMappingChange: (r, c) => (got = [r, c]), onlyProblems: false, onToggleProblems: noop });
    const sel = find(root, (x) => x.props && x.props["data-role"] === "date")[0];
    assert.equal(sel.props.value, "Date");
    sel.props.onChange({ target: { value: "Description" } });
    assert.deepEqual(got, ["date", "Description"]);
  });
  test("an invoice shows each field with its confidence and source, and a proposal that is not applied", () => {
    const t = text(DataImport(withBatch(F.inv, { form: newImportForm("DOCUMENT") })));
    assert.ok(t.includes("INV-2026-0042") && t.includes("53,750.00") && t.includes("HIGH") && t.includes("LOW"));
    assert.ok(t.includes("Proposal only, not applied") && t.includes("Choose an account"));
    assert.ok(t.includes("A person must still check"));
  });
  test("an unreadable image says so but can still be stored", () => {
    const root = DataImport(withBatch(F.scan, { form: newImportForm("DOCUMENT") }));
    assert.ok(text(root).includes("no OCR"));
    assert.equal(find(root, (x) => x.props && x.props.id === "import-commit")[0].props.disabled, false);
  });
  test("payroll shows employees, totals and a balanced proposal", () => {
    const t = text(DataImport(withBatch(F.pay, { form: newImportForm("PAYROLL") })));
    assert.ok(t.includes("Aisha") && t.includes("800,000.00") && t.includes("Proposal only, not applied") && t.includes("Nothing is posted"));
  });
  test("chart of accounts shows type mapping and unmappable rows", () => {
    const t = text(DataImport(withBatch(F.coa, { form: newImportForm("CHART_OF_ACCOUNTS") })));
    assert.ok(t.includes("REVENUE") && t.includes("Exists") && t.includes("looks like XERO"));
  });
  test("journals show resolved accounts and the unbalanced one", () => {
    const t = text(DataImport(withBatch(F.jr, { form: newImportForm("JOURNALS") })));
    assert.ok(t.includes("1000 Cash") && t.includes("does not balance"));
  });
  test("the confirm button label depends on what is being imported", () => {
    for (const [p, label] of [["BANK_STATEMENT", "Import into the reconciliation"], ["CHART_OF_ACCOUNTS", "Create the accounts"], ["JOURNALS", "Create draft journals"], ["DOCUMENT", "Store as evidence"]]) {
      assert.ok(text(DataImport(withBatch(F.good, { form: newImportForm(p), ack: true }))).includes(label), p);
    }
  });
  test("a commit error is shown and the result screen explains what happened", () => {
    assert.ok(text(DataImport(withBatch(F.good, { commitError: "changed since the preview" }))).includes("changed since the preview"));
    const result = { purpose: "BANK_STATEMENT", result: { imported: 2, skipped_already_imported: 1, matched_automatically: 1, evidence_is_new: true, evidence_linked_to_reconciliation: true } };
    const form = { ...newImportForm("BANK_STATEMENT"), reconciliationId: "r1" };
    const root = DataImport({ ...base, form, result });
    const t = text(root);
    assert.ok(t.includes("2 line(s) imported") && t.includes("1 line(s) were already there") && t.includes("unverified evidence"));
    let went = null;
    find(DataImport({ ...base, form, result, onNavigate: (p) => (went = p) }), (x) => x.props && x.props["data-go"] === "reconciliation")[0].props.onClick();
    assert.equal(went, "/reconciliation/r1");
  });
});

describe("client", () => {
  test("preview and commit send multipart forms with the right fields", async () => {
    const calls = [];
    const c = new ApiClient({ baseUrl: "http://x" });
    c._postForm = async (p, form) => { calls.push([p, Object.fromEntries([...form.entries()].map(([k, v]) => [k, typeof v === "string" ? v : "FILE"]))]); return {}; };
    const f = new Blob(["a,b"], { type: "text/csv" });
    await c.ingestionPreview({ file: f, purpose: "BANK_STATEMENT", reconciliationId: "r1", options: { flip: true }, currency: "NGN" });
    await c.ingestionPreview({ file: f, purpose: "DOCUMENT", options: {} });
    await c.ingestionCommit({ file: f, purpose: "BANK_STATEMENT", reconciliationId: "r1", options: {}, fingerprint: "abc", acknowledge: true, evidenceType: "OTHER", allowDuplicate: true });
    assert.deepEqual(calls[0], ["/ingestion/preview", { file: "FILE", purpose: "BANK_STATEMENT", reconciliation_id: "r1", options: '{"flip":true}', currency: "NGN" }]);
    assert.deepEqual(calls[1][1], { file: "FILE", purpose: "DOCUMENT" });
    assert.deepEqual(calls[2][1], { file: "FILE", purpose: "BANK_STATEMENT", reconciliation_id: "r1", fingerprint: "abc", acknowledge: "true", evidence_type: "OTHER", allow_duplicate: "true" });
  });
});
