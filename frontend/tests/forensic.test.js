import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { Forensic } from "../src/pages/Forensic.js";
import * as F from "../src/lib/forensic.js";
import { ApiClient } from "../src/api/client.js";
import { can, PERMISSIONS } from "../src/lib/permissions.js";

const text = (v) => JSON.stringify(v);
function find(v, pred, out = []) { if (!v || typeof v !== "object") return out; if (pred(v)) out.push(v); for (const c of v.children || []) find(c, pred, out); return out; }
const byId = (v, id) => find(v, (n) => n.props && n.props.id === id)[0];
const noop = new Proxy({}, { get: () => () => {} });
const OPTIONS = { case_types: { IRREGULARITY: "Accounting irregularity" }, tests: { same_person: "Created and posted by the same person", benford: "Benford" }, defaults: {}, severities: ["LOW", "MEDIUM", "HIGH"], limitations: [] };
const CASE = { id: "c1", reference: "CASE-0001", title: "Rent review", status: "OPEN", type_text: "Accounting irregularity", opened_by: "u1", opened_at: "2026-04-01T00:00:00", description: "d", evidence: [], runs: [], findings: [], reports: [], custody: [{ seq: 1, at: "2026-04-01T00:00:00", actor: "u1", action: "CASE_OPENED", detail: "x", hash: "a".repeat(64) }] };
const base = (o = {}) => ({ cases: [], case: null, tab: "overview", caseForm: null, options: OPTIONS, busy: false, error: null, notice: null, periods: [{ id: "p1", name: "Jan" }], vault: [], ev: { id: "", note: "" }, runForm: F.emptyRun(), run: null, findingForm: null, decisionNotes: {}, report: null, reportTitle: "", reportNote: "", closeNote: "", custodyCheck: null, ...o });
const page = (fm, role = "AUDITOR", userId = "u1") => Forensic({ fm, role, userId, loading: false, onRetry() {}, actions: noop });
const FINDING = { id: "f1", title: "Same user", description: "x".repeat(30), severity: "HIGH", journals: [{ id: "j1", number: "JE-1" }], evidence_ids: [], status: "SUBMITTED", created_by: "u1", submitted_by: "u1", decision_note: "" };

describe("permissions", () => {
  test("only investigation roles can see or work cases", () => {
    for (const r of ["ACCOUNTANT", "FINANCE_OFFICER", "ADMINISTRATOR", "READ_ONLY", "REVIEWER", "EXTERNAL_AUDITOR", "DONOR"]) assert.equal(can(r, PERMISSIONS.FORENSIC_READ), false, r);
    assert.equal(can("AUDITOR", PERMISSIONS.FORENSIC_PREPARE), true); assert.equal(can("AUDITOR", PERMISSIONS.FORENSIC_APPROVE), false);
    assert.equal(can("APPROVER", PERMISSIONS.FORENSIC_APPROVE), true); assert.equal(can("APPROVER", PERMISSIONS.FORENSIC_PREPARE), false);
    assert.equal(can("OWNER", PERMISSIONS.FORENSIC_PREPARE), true);
  });
});

describe("helpers", () => {
  test("run validation: scope, thresholds only when those tests are chosen", () => {
    const r = (o) => ({ ...F.emptyRun(), period_id: "p1", ...o });
    assert.equal(F.runProblem(r({})), null);
    assert.match(F.runProblem(r({ tests: [] })), /at least one/);
    assert.match(F.runProblem(r({ period_id: "" })), /period/);
    assert.match(F.runProblem(r({ scope_kind: "dates", start: "2026-01-01", end: "x" })), /dates/);
    assert.match(F.runProblem(r({ tests: ["just_below"] })), /approval limit/);
    assert.equal(F.runProblem(r({ tests: ["just_below"], approval_limit: "10000" })), null);
    assert.match(F.runProblem(r({ tests: ["no_evidence"] })), /evidence/);
    assert.match(F.runProblem(r({ round_to: "x" })), /whole number/);
    assert.match(F.runProblem(r({ weekend_days: "7" })), /0 \(Monday\)/);
  });
  test("run body builds scope and numeric weekend days", () => {
    const b = F.runBody({ ...F.emptyRun(), period_id: "p1", approval_limit: " 5000 ", weekend_days: "4, 5" });
    assert.deepEqual(b.scope, { period_id: "p1" }); assert.deepEqual(b.params.weekend_days, [4, 5]); assert.equal(b.params.approval_limit, "5000"); assert.equal(b.params.evidence_threshold, undefined);
    assert.deepEqual(F.runBody({ ...F.emptyRun(), scope_kind: "dates", start: "2026-01-01", end: "2026-02-01" }).scope, { start: "2026-01-01", end: "2026-02-01" });
  });
  test("finding validation and body", () => {
    assert.match(F.findingProblem({ title: "ab", description: "x".repeat(30) }), /title/);
    assert.match(F.findingProblem({ title: "Title", description: "short" }), /20 characters/);
    assert.equal(F.findingProblem({ title: "Title", description: "x".repeat(20) }), null);
    assert.deepEqual(F.findingBody({ ...F.emptyFinding(), title: " T ", description: "d", journals: [{ id: "j1" }] }).journal_ids, ["j1"]);
  });
  test("separation of duties for findings, reports and closing", () => {
    assert.equal(F.itemActions(FINDING, "OWNER", "u1").decide, false);
    assert.equal(F.itemActions(FINDING, "OWNER", "u1").ownSubmission, true);
    assert.equal(F.itemActions(FINDING, "OWNER", "u2").decide, true);
    assert.equal(F.itemActions({ ...FINDING, created_by: "u1", submitted_by: "u3" }, "OWNER", "u1").decide, false);
    assert.equal(F.itemActions(FINDING, "AUDITOR", "u2").decide, false);
    assert.equal(F.canClose(CASE, "OWNER", "u1"), false); assert.equal(F.canClose(CASE, "OWNER", "u2"), true); assert.equal(F.canClose({ ...CASE, status: "CLOSED" }, "OWNER", "u2"), false);
  });
});

describe("Forensic page", () => {
  test("always warns that this is confidential and flags are not proof", () => {
    const t = text(page(base()));
    assert.match(t, /Strictly confidential/); assert.match(t, /not proof of error, fraud or wrongdoing/);
  });
  test("empty case list, and Open a case only for people who prepare", () => {
    assert.match(text(page(base())), /No cases yet/);
    assert.ok(byId(page(base(), "AUDITOR"), "case-new")); assert.equal(byId(page(base(), "APPROVER"), "case-new"), undefined);
  });
  test("case view shows tabs, status and the integrity check", () => {
    const v = page(base({ case: CASE }));
    assert.ok(byId(v, "fx-tab-analytics")); assert.ok(byId(v, "custody-verify")); assert.match(text(v), /CASE-0001/);
    const bad = page(base({ case: CASE, custodyCheck: { ok: false, meaning: "Something does not match" } }));
    assert.equal(find(bad, (n) => n.props && /alert-error/.test(n.props.className || "")).length, 1);
  });
  test("analytics: results are worded as indicators with limits, journals can be cited", () => {
    const run = { id: "r1", fingerprint: "f".repeat(64), journals_examined: 8, results: [{ id: "same_person", name: "Created and posted by the same person", status: "INDICATORS", summary: "8 entries", hits: [{ journal_id: "j1", number: "JE-1", date: "2026-01-05", amount: "1000.00", reason: "same user" }], hit_count: 1, truncated: false, limits: "Small teams do this.", detail: {} }] };
    const t = text(page(base({ case: CASE, tab: "analytics", run })));
    assert.match(t, /indicators only/i); assert.match(t, /Worth a look/); assert.match(t, /Small teams do this/); assert.match(t, /Use in a finding/);
    assert.doesNotMatch(t, /guilty|fraud detected/i);
  });
  test("analytics form hidden for approvers; closed cases cannot be worked", () => {
    assert.equal(byId(page(base({ case: CASE, tab: "analytics" }), "APPROVER"), "rn-run"), undefined);
    assert.ok(byId(page(base({ case: CASE, tab: "analytics" }), "AUDITOR"), "rn-run"));
    assert.equal(byId(page(base({ case: { ...CASE, status: "CLOSED" }, tab: "analytics" }), "AUDITOR"), "rn-run"), undefined);
  });
  test("finding card: author sees no approve; another approver does", () => {
    const fm = base({ case: { ...CASE, findings: [FINDING] }, tab: "findings" });
    assert.equal(byId(page(fm, "OWNER", "u1"), "fd-approve-f1"), undefined);
    assert.match(text(page(fm, "OWNER", "u1")), /different person must review/);
    assert.ok(byId(page(fm, "OWNER", "u2"), "fd-approve-f1")); assert.ok(byId(page(fm, "OWNER", "u2"), "fd-reject-f1"));
  });
  test("finding form guides toward facts, not accusations", () => {
    assert.match(text(page(base({ case: CASE, tab: "findings", findingForm: F.emptyFinding() }))), /Avoid naming anyone as guilty/);
  });
  test("report: tamper warning, integrity note, export only when approved", () => {
    const r = { id: "p1", title: "R", status: "SUBMITTED", intact: false, fingerprint: "f".repeat(64), created_by: "u1", submitted_by: "u1", decision_note: "", snapshot: { generated_at: "2026-04-01T00:00:00", integrity: { ok: true, meaning: "Unbroken." }, custody_head: "a".repeat(64), custody_entries: 1, findings: [], limitations: ["Flags are not proof."] } };
    const t = text(page(base({ case: CASE, tab: "reports", report: r }), "OWNER", "u2"));
    assert.match(t, /no longer matches its fingerprint/); assert.equal(byId(page(base({ case: CASE, tab: "reports", report: r }), "OWNER", "u2"), "rp-export"), undefined);
    assert.ok(byId(page(base({ case: CASE, tab: "reports", report: { ...r, status: "APPROVED", intact: true } }), "OWNER", "u2"), "rp-export"));
    assert.equal(byId(page(base({ case: CASE, tab: "reports", report: r }), "OWNER", "u1"), "rp-approve"), undefined);
  });
  test("custody log lists entries", () => assert.match(text(page(base({ case: CASE, tab: "custody" }))), /case opened/));
});

describe("API client", () => {
  test("routes and verbs", async () => {
    const seen = [];
    const api = new ApiClient({ baseUrl: "/api", getToken: () => "t", fetchImpl: async (u, o) => { seen.push(o.method + " " + u); return { ok: true, status: 200, text: async () => "{}" }; } });
    await api.forensicCases(); await api.runForensicAnalytics("c 1", {}); await api.discardForensicFinding("f1"); await api.updateForensicFinding("f1", {}); await api.closeForensicCase("c1", "n");
    assert.deepEqual(seen, ["GET /api/forensic/cases", "POST /api/forensic/cases/c%201/analytics", "DELETE /api/forensic/findings/f1", "PUT /api/forensic/findings/f1", "POST /api/forensic/cases/c1/close"]);
  });
  test("export carries the bearer token", async () => {
    let hdr; const api = new ApiClient({ baseUrl: "/api", getToken: () => "tok", fetchImpl: async (u, o) => { hdr = o.headers; return { ok: true, blob: async () => "B", headers: { get: () => 'attachment; filename="CASE-0001-report.csv"' } }; } });
    const r = await api.exportForensicReport("r1"); assert.equal(r.filename, "CASE-0001-report.csv"); assert.equal(hdr.Authorization, "Bearer tok");
  });
});
