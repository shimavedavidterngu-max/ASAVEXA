import { test } from "node:test";
import assert from "node:assert/strict";
import { runSelfTest, summarise } from "../src/lib/selftest.js";
import { ApiError, NetworkError } from "../src/api/client.js";

// A small in-memory stand-in that enforces the same rules the real API
// does. It tests the SELF-TEST SCRIPT's own logic (every step reachable,
// correct expectations) — the real system is exercised by the
// Connection & Self-Test page in the live app.
function fakeApi({ breakEvidenceStatus = false, down = false, breakPassport = false, breakAiChain = false } = {}) {
  const db = { accounts: [], journals: [], evidence: [], recon: [], audit: {}, orgs: [{ id: "org1" }], org: "org1", profile: {} };
  let n = 0;
  const id = () => `00000000-0000-4000-8000-${String(++n).padStart(12, "0")}`;
  const bad = (st, m) => { throw new ApiError(st, { detail: m }); };
  const uuid = (v) => /^[0-9a-f]{8}-/.test(v) || bad(400, "invalid id");
  const log = (t, i, a) => { (db.audit[`${t}:${i}`] = db.audit[`${t}:${i}`] || []).push({ action: a }); };
  const ex = {};
  const api = {
    async rawGet(p) { if (down) return { ok: false, status: 0, error: new NetworkError(new Error("x")) }; return { ok: true, status: 200, body: {}, ms: 5 }; },
    async myOrganisations() { return db.orgs; },
    async getOrganisationProfile() { return { org_id: db.org, ...db.profile, updated_by: db.profile.legal_name ? "u" : undefined }; },
    async updateOrganisationProfile(p) { if (p.contact_email && !p.contact_email.includes("@")) bad(422, "contact_email invalid"); db.profile = p; log("Organisation", db.org, "ORGANISATION_PROFILE_UPDATED"); return { org_id: db.org, ...p }; },
    async entityAuditTrail(t, i) { return db.audit[`${t}:${i}`] || []; },
    async createAccount(b) { if (db.accounts.some((a) => a.code === b.code && a.org === db.org)) bad(409, "dup"); const a = { id: id(), org: db.org, ...b }; db.accounts.push(a); return a; },
    async listAccounts() { return db.accounts.filter((a) => a.org === db.org); },
    async openPeriod(b) { const p = { id: id(), status: "OPEN", ...b }; db.periodId = p.id; (db.periods = db.periods || []).push({ name: b.name, start_date: b.start_date, end_date: b.end_date }); return p; },
    async createDraftJournal(b) {
      const d = b.lines.reduce((s, l) => s + Number(l.debit_amount), 0), c = b.lines.reduce((s, l) => s + Number(l.credit_amount), 0);
      if (d !== c) bad(409, "unbalanced");
      for (const l of b.lines) if (!db.accounts.some((a) => a.id === l.account_id)) bad(404, "account not found");
      const j = { id: id(), org: db.org, journal_number: "J-1", status: "DRAFT", ...b }; db.journals.push(j); log("Journal", j.id, "JOURNAL_CREATED"); return j;
    },
    async listJournals() { return db.journals.filter((j) => j.org === db.org); },
    async getJournal(i) { uuid(i); const j = db.journals.find((x) => x.id === i && x.org === db.org); if (!j) bad(404, "journal not found"); return j; },
    async postJournal(i) { const j = await api.getJournal(i); j.status = "POSTED"; log("Journal", i, "JOURNAL_POSTED"); return j; },
    async journalAuditTrail(i) { return db.audit[`Journal:${i}`] || []; },
    async uploadEvidence({ file, type, linkedJournalId }) {
      if (linkedJournalId) uuid(linkedJournalId);
      const text = await file.text();
      if (db.evidence.some((e) => e.text === text)) bad(409, "duplicate");
      const e = { id: id(), org: db.org, text, file_hash: "a".repeat(64), original_filename: file.name, size_bytes: text.length, content_type: "text/plain", linked_journal_id: linkedJournalId || null, status: "UPLOADED", uploaded_by: "u", uploaded_at: "t" };
      db.evidence.push(e); log("EvidenceRecord", e.id, "EVIDENCE_UPLOADED"); return e;
    },
    async getEvidence(i) { const e = db.evidence.find((x) => x.id === i && x.org === db.org); if (!e) bad(404, "evidence not found"); return e; },
    async listEvidence() { return db.evidence; },
    async evidenceStatus(j) { const e = db.evidence.find((x) => x.linked_journal_id === j); return breakEvidenceStatus ? { status: e.status } : { status: e ? e.status : "MISSING", evidence_id: e && e.id }; },
    async verifyEvidence() { bad(403, "maker-checker: cannot verify own upload"); },
    async createReconciliation(b) { uuid(b.bank_account_id); if (!db.accounts.some((a) => a.id === b.bank_account_id)) bad(404, "bank account not found"); const r = { id: id(), status: "DRAFT", ...b }; db.recon.push(r); log("Reconciliation", r.id, "RECONCILIATION_CREATED"); return r; },
    async importTransactions(r) { db.txn = [{ id: id(), status: "IMPORTED" }]; return {}; },
    async listReconciliationTransactions() { return db.txn; },
    async listReconciliations() { return db.recon; },
    async getReconciliation(i) { return db.recon.find((r) => r.id === i); },
    async trialBalance() { return { is_balanced: true, total_debits: "1075000.00", total_credits: "1075000.00" }; },
    async incomeStatement() { return { total_expenses: "1000000.00" }; },
    async balanceSheet() { return { total_assets: "75000.00", total_liabilities: "1075000.00" }; },
    async generalLedger(p, a) { return { accounts: [{ account_id: a }] }; },
    async traceLine(a) { uuid(a); return { entries: [{ journal_id: db.journals[0].id }] }; },
    async evidenceCompleteness() { return { score: 1 }; },
    async seedStandardControls() { return []; },
    async listControls() { return ["ACC-001", "ACC-002", "ACC-003", "REC-001", "EVI-001", "EVI-002", "REP-001", "CLS-001", "CLS-002"].map((code) => ({ id: id(), code })); },
    async executeControl(cid) { const e = { id: id(), result: cid.endsWith("1") ? "FAIL" : "PASS", explanation: "e", finding_id: cid.endsWith("1") ? "f1" : null }; ex[e.id] = e; return e; },
    async listExecutions() { return Object.values(ex); },
    async getFinding(i) { return { id: i, status: "OPEN", severity: "HIGH" }; },
    async createFindingFromExecution() { return { id: "f1" }; },
    async startFindingReview(i) { return { id: i, status: "UNDER_REVIEW" }; },
    async markRemediationRequired(i) { return { id: i, status: "REMEDIATION_REQUIRED" }; },
    async createRemediation() { return { id: "r1" }; },
    async startRemediation() { return {}; },
    async completeRemediation() { return {}; },
    async verifyRemediation() { bad(409, "verifier must differ from completer"); },
    async checkCloseReadiness() { return { is_ready: false, findings: [{}, {}], blocking_failures: ["X"] }; },
    async standardsCatalog() { return { jurisdictions: [1], entity_types: [1], frameworks: [1] }; },
    async resolveStandards(c) {
      if (c.jurisdiction === "ZZ") bad(400, "Unknown jurisdiction");
      if (c.policy_overrides && c.policy_overrides.INVENTORY_COSTING === "LIFO") bad(400, "LIFO not permitted");
      return { framework: "IFRS_FOR_SMES", policies: [1], requirements: [1] };
    },
    async getStandardsConfiguration() { return db.std ? { configured: true, ...db.std, policies: [] } : { configured: false }; },
    async saveStandardsConfiguration(c) { db.std = c; return c; },
    async getPassport() {
      const mine = db.journals.filter((j) => j.org === db.org && j.status === "POSTED");
      const acct = (i) => db.accounts.find((a) => a.id === i) || {};
      const sum = (type, side) => mine.reduce((t, j) => t + j.lines.filter((l) => acct(l.account_id).type === type)
        .reduce((x, l) => x + Number(side === "dr" ? l.debit_amount : l.credit_amount) - Number(side === "dr" ? l.credit_amount : l.debit_amount), 0), 0);
      const per = mine.length ? [{ period_id: db.periodId, has_activity: true, expenses: String(sum("EXPENSE", "dr")), assets: String(sum("ASSET", "dr")), liabilities: String(sum("LIABILITY", "cr")) }] : [];
      const linked = new Set(db.evidence.filter((e) => e.org === db.org).map((e) => e.linked_journal_id));
      const missing = mine.filter((j) => !linked.has(j.id));
      const p = {
        schema_version: "vera-passport/1", fingerprint: "ab".repeat(32),
        identity: { status: "attention", ownership: { recorded: !!db.structure, owners: db.structure ? db.structure.owners : [] }, subsidiaries: { recorded: !!db.structure, items: db.structure ? db.structure.subsidiaries : [], count: db.structure ? db.structure.subsidiaries.length : 0 } },
        financial_history: { status: mine.length ? "ok" : "incomplete", periods: per, totals: { revenue: "0.00" } },
        evidence_quality: { status: "attention", transactions: { total_posted: mine.length, supported_verified: 0, evidence_unverified: mine.length - missing.length, evidence_defective: 0, missing_evidence: missing.length }, missing_evidence: { items: missing.map((j) => ({ journal_id: j.id })) } },
        governance: { status: "attention", segregation_of_duties: { checks: [{ key: "journal_post", tested: mine.length, violations: mine.length }] } },
        reporting: { status: "incomplete" },
        audit_trail: { status: "ok", by_person: [{ who: "u" }], journal_provenance: mine.map((j) => ({ journal_id: j.id, created_by: "u", created_at: "t", posted_by: "u", posted_at: "t" })) },
      };
      if (breakPassport) delete p.audit_trail;
      return p;
    },
    async savePassportStructure(b) {
      const total = b.owners.reduce((t, o) => t + Number(o.ownership_percent || 0), 0);
      if (total > 100) bad(422, "Owners' percentages add up to more than 100%.");
      db.structure = b; return b;
    },
    async createPassportShare(b) {
      const n1 = id();
      const share = { id: n1, org: db.org, status: "ACTIVE", recipient_email: b.recipient_email, scopes: b.scopes, periods_included: db.periods || [] };
      const rec = { share, secret: `sec${n1.slice(-4)}`, code: "ABCDE-FGHJK", email: (b.recipient_email || "").toLowerCase(), failed: 0, log: [{ action: "PASSPORT_SHARE_CREATED" }], sessions: new Set() };
      (db.shares = db.shares || {})[n1] = rec;
      return { share, access_token: `${n1}.${rec.secret}`, access_code: rec.code, warnings: [], note: "once" };
    },
    async listPassportShares() { return Object.values(db.shares || {}).filter((r) => r.org !== "x").map((r) => r.share); },
    async verifyShare({ accessToken, accessCode, email }) {
      const [sid, secret] = accessToken.split(".");
      const r = (db.shares || {})[sid];
      if (!r || r.secret !== secret || r.share.status !== "ACTIVE") bad(403, "This access link is not valid.");
      if (accessCode !== r.code || (r.email && (email || "").toLowerCase() !== r.email)) { r.failed++; r.log.push({ action: "PASSPORT_SHARE_DENIED" }); bad(403, "The access code or email is not correct."); }
      const tok = `sess${id()}`; r.sessions.add(tok); r.log.push({ action: "PASSPORT_SHARE_VERIFIED" });
      return { session_token: tok };
    },
    async viewSharedPassport(tok) {
      const r = Object.values(db.shares || {}).find((x) => x.sessions.has(tok));
      if (!r || r.share.status !== "ACTIVE") bad(403, "Your verified session has ended.");
      r.log.push({ action: "PASSPORT_SHARE_VIEWED" });
      const sections = {};
      for (const sc of r.share.scopes) sections[sc.toLowerCase()] = { status: "ok" };
      return { share: { periods_included: db.periods || [] }, sections, integrity: { verified: true } };
    },
    async downloadSharedPassport() { bad(403, "The organisation did not allow this share to be downloaded."); },
    async revokePassportShare(sid) { const r = db.shares[sid]; r.share.status = "REVOKED"; r.log.push({ action: "PASSPORT_SHARE_REVOKED" }); return r.share; },
    async passportShareAccessLog(sid) { return db.shares[sid].log; },
    // ---- ASAVEXA AI stand-in: enforces the grounded chain and the 404 / refusal rules
    _aiItem(extra = {}) {
      const it = { conclusion: "c", source_records: [{ kind: "JOURNAL" }], evidence: { available: true }, journal: { available: true },
        accounting_treatment: { available: true }, reporting_framework: { available: true },
        confidence: { level: "HIGH", score: 100 }, human_review: { required: false }, ...extra };
      if (breakAiChain) delete it.reporting_framework;
      return it;
    },
    _aiJournal(ref) { if (!db.journals.some((j) => j.id === ref && j.org === db.org)) bad(404, `There is no journal '${ref}'`); },
    async aiExplain({ subjectId }) { this._aiJournal(subjectId); return { grounded: true, mode: "EXPLAIN", items: [this._aiItem()] }; },
    async aiDetect() { return { grounded: true, mode: "DETECT", items: [] }; },
    async aiRecommend() { return { grounded: true, mode: "RECOMMEND", items: [this._aiItem({ human_review: { required: true }, proposal: { applied: false } })] }; },
    async aiProve({ subjectId }) { this._aiJournal(subjectId); return { grounded: true, mode: "PROVE", verdict: "PROVEN", items: [this._aiItem()] }; },
    async aiAsk(q) {
      if (/unusual/i.test(q)) return { grounded: true, mode: "DETECT", items: [] };
      return { grounded: false, mode: "ASK", items: [], refusal: { reason: "I cannot ground that." } };
    },
    async createOrganisation() { db.orgs.push({ id: "org2" }); return { id: "org2" }; },
    async selectOrganisation(o) { db.org = o; return {}; },
  };
  return api;
}

test("self-test: every step passes (or warns on maker-checker) against a rule-enforcing stand-in", async () => {
  const results = await runSelfTest(fakeApi(), { orgId: "org1" });
  const s = summarise(results);
  const failed = results.filter((r) => r.status === "fail");
  assert.deepEqual(failed, [], JSON.stringify(failed, null, 1));
  assert.equal(s.skip, 0);
  assert.ok(s.pass >= 50, `only ${s.pass} passed`);
  assert.ok(s.warn >= 1, "maker-checker rejections should be reported as warnings");
});

test("self-test: a passport missing a section is caught", async () => {
  const results = await runSelfTest(fakeApi({ breakPassport: true }), { orgId: "org1" });
  assert.ok(results.some((r) => r.status === "fail" && r.group === "Passport" && /six sections/.test(r.name)));
});

test("self-test: the Passport steps run and pass", async () => {
  const results = await runSelfTest(fakeApi(), { orgId: "org1" });
  const passport = results.filter((r) => r.group === "Passport");
  assert.equal(passport.length, 8);
  assert.deepEqual(passport.filter((r) => r.status !== "pass"), []);
});

test("self-test: the AI steps run and pass", async () => {
  const results = await runSelfTest(fakeApi(), { orgId: "org1" });
  const ai = results.filter((r) => r.group === "AI");
  assert.equal(ai.length, 7);
  assert.deepEqual(ai.filter((r) => r.status !== "pass"), [], JSON.stringify(ai, null, 1));
});

test("self-test: an AI answer with a broken chain is caught", async () => {
  const results = await runSelfTest(fakeApi({ breakAiChain: true }), { orgId: "org1" });
  assert.ok(results.some((r) => r.status === "fail" && r.group === "AI" && /grounded chain/.test(r.name)));
});

test("self-test: the Sharing steps run and pass", async () => {
  const results = await runSelfTest(fakeApi(), { orgId: "org1" });
  const sharing = results.filter((r) => r.group === "Sharing");
  assert.equal(sharing.length, 9);
  assert.deepEqual(sharing.filter((r) => r.status !== "pass"), [], JSON.stringify(sharing, null, 1));
});

test("self-test: a share that leaks the wrong sections is caught", async () => {
  const api = fakeApi();
  const orig = api.viewSharedPassport;
  api.viewSharedPassport = async (t) => { const v = await orig(t); v.sections.audit_trail = { status: "ok" }; return v; };
  const results = await runSelfTest(api, { orgId: "org1" });
  assert.ok(results.some((r) => r.status === "fail" && /exactly the chosen sections/.test(r.name)));
});

test("self-test: a backend that omits evidence_id (the bug fixed in this release) is caught", async () => {
  const results = await runSelfTest(fakeApi({ breakEvidenceStatus: true }), { orgId: "org1" });
  assert.ok(results.some((r) => r.status === "fail" && /Show me the evidence/.test(r.name)));
});

test("self-test: a dead API is reported as a connectivity failure and dependent steps still complete safely", async () => {
  const results = await runSelfTest(fakeApi({ down: true }), { orgId: "org1" });
  assert.equal(results[0].status, "fail");
  assert.match(results[0].detail, /NETWORK/);
});
