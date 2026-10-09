import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { runSelfTest, summarise } from "../src/lib/selftest.js";
import { ApiError, NetworkError } from "../src/api/client.js";

// A small in-memory stand-in that enforces the same rules the real API
// does. It tests the SELF-TEST SCRIPT's own logic (every step reachable,
// correct expectations) — the real system is exercised by the
// Connection & Self-Test page in the live app.
function fakeApi({ breakEvidenceStatus = false, down = false, breakPassport = false, breakAiChain = false, breakImportPreviewWrites = false, breakImportDedupe = false, noKeys = false, breakChain = false, leakSessions = false } = {}) {
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
      const e = { id: id(), org: db.org, text, file_hash: createHash("sha256").update(text).digest("hex"), original_filename: file.name, size_bytes: text.length, content_type: "text/plain", linked_journal_id: linkedJournalId || null, status: "UPLOADED", uploaded_by: "u", uploaded_at: "t" };
      db.evidence.push(e); log("EvidenceRecord", e.id, "EVIDENCE_UPLOADED"); return e;
    },
    async getEvidence(i) { const e = db.evidence.find((x) => x.id === i && x.org === db.org); if (!e) bad(404, "evidence not found"); return e; },
    async listEvidence() { return db.evidence; },
    async evidenceStatus(j) { const e = db.evidence.find((x) => x.linked_journal_id === j); return breakEvidenceStatus ? { status: e.status } : { status: e ? e.status : "MISSING", evidence_id: e && e.id }; },
    async verifyEvidence() { bad(403, "maker-checker: cannot verify own upload"); },
    async createReconciliation(b) { uuid(b.bank_account_id); if (!db.accounts.some((a) => a.id === b.bank_account_id)) bad(404, "bank account not found"); const r = { id: id(), status: "DRAFT", ...b }; db.recon.push(r); log("Reconciliation", r.id, "RECONCILIATION_CREATED"); return r; },
    async importTransactions(rid) { (db.txns = db.txns || {})[rid] = [{ id: id(), status: "IMPORTED" }]; return {}; },
    async listReconciliationTransactions(rid) { return (db.txns || {})[rid] || []; },
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
    // ---- External data ingestion stand-in: preview writes nothing, commit re-stages and checks the fingerprint
    async ingestionLevels() {
      return { levels: [[1, "WORKING"], [2, "WORKING"], [3, "WORKING"], [4, "PARTIAL"], [5, "PARTIAL"], [6, "FILES_ONLY"], [7, "PAYLOAD_ONLY"], [8, "PAYLOAD_ONLY"]].map(([level, status]) => ({ level, status, name: `L${level}` })) };
    },
    async ingestionPreview({ file, purpose, reconciliationId, options, currency }) {
      if (!["BANK_STATEMENT", "DOCUMENT", "PAYROLL", "CHART_OF_ACCOUNTS", "JOURNALS"].includes(purpose)) bad(400, "purpose must be one of: BANK_STATEMENT, ...");
      const text = await file.text();
      const hash = (str) => { let h = 7; for (const c of str) h = (h * 31 + c.charCodeAt(0)) >>> 0; return h.toString(16).padStart(8, "0").repeat(8); };
      if (purpose === "DOCUMENT") {
        const m = (re) => { const x = text.match(re); return x ? { value: x[1], confidence: "HIGH" } : undefined; };
        return { kind: "DOCUMENT", document: { type: /invoice/i.test(text) ? "INVOICE" : "UNKNOWN", fields: { document_number: m(/Invoice No:\s*(\S+)/), total: m(/^Total NGN ([\d.]+)/m) } },
          proposal: { applied: false }, status: { errors: 0, importable: true, needs_acknowledgement: false }, fingerprint: hash(text + purpose), source: { sha256: hash(text) }, summary: {} };
      }
      if (purpose !== "BANK_STATEMENT") { if (!currency) bad(400, "Choose the currency for the accounts/journals."); return { kind: purpose, status: { errors: 0, importable: true }, fingerprint: hash(text), summary: {} }; }
      if (!reconciliationId) bad(400, "Choose the reconciliation the statement belongs to.");
      const rec = db.recon.find((r) => r.id === reconciliationId); if (!rec) bad(404, "Reconciliation not found.");
      const [head, ...lines] = text.trim().split("\n").map((l) => l.split(","));
      const col = (n) => head.indexOf(n);
      let inT = 0, outT = 0, errors = 0, prev = null, brokenBalance = false, already = 0; const rows = [];
      for (const l of lines) {
        const date = l[col("Date")], desc = l[col("Description")];
        const amt = col("Amount") >= 0 ? Number(l[col("Amount")]) : Number(l[col("Credit")] || 0) - Number(l[col("Debit")] || 0);
        if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) { errors++; continue; }
        const mi = amt > 0 ? amt : 0, mo = amt < 0 ? -amt : 0; inT += mi; outT += mo;
        if (col("Balance") >= 0) { const bal = Number(l[col("Balance")]); if (prev !== null && Math.abs(prev + amt - bal) > 0.001) brokenBalance = true; prev = bal; }
        const key = `${date}|${desc}|${mi}|${mo}`; if (((db.imported || {})[rec.id] || new Set()).has(key)) already++;
        rows.push(key);
      }
      return { kind: "BANK_TRANSACTIONS", status: { errors, importable: errors === 0 && rows.length > 0, needs_acknowledgement: brokenBalance }, rows: rows.map((k) => ({ key: k })),
        summary: { lines: rows.length, money_in_total: inT.toFixed(2), money_out_total: outT.toFixed(2), already_imported: already, to_import: rows.length - already },
        checks: [{ key: "BALANCE_CONTINUITY", result: col("Balance") < 0 ? "NOT_APPLICABLE" : brokenBalance ? "FAIL" : "PASS" }], fingerprint: hash(text + JSON.stringify(options || {})), source: { sha256: hash(text) } };
    },
    async ingestionCommit(a) {
      const p = await this.ingestionPreview(a);
      if (p.fingerprint !== a.fingerprint) bad(400, "The file or the settings changed since the preview.");
      if (p.status.errors) bad(400, "The file still has errors.");
      if (p.status.needs_acknowledgement && !a.acknowledge) bad(400, "Confirm the warnings first.");
      const text = await a.file.text();
      let ev = db.evidence.find((e) => e.file_hash === p.source.sha256 && e.org === db.org);
      if (!ev) { ev = { id: id(), org: db.org, type: a.purpose === "DOCUMENT" ? p.document.type : "BANK_STATEMENT", status: "UPLOADED", file_hash: p.source.sha256 }; db.evidence.push(ev); }
      if (a.purpose === "DOCUMENT") return { purpose: a.purpose, result: { evidence_id: ev.id, status: "UPLOADED", type: ev.type } };
      const store = ((db.imported = db.imported || {})[a.reconciliationId] = db.imported[a.reconciliationId] || new Set());
      let n = 0; (db.txns = db.txns || {})[a.reconciliationId] = db.txns[a.reconciliationId] || [];
      const [head, ...lines] = text.trim().split("\n").map((l) => l.split(","));
      for (const k of p.rows.map((r) => r.key)) {
        if (store.has(k) && !breakImportDedupe) continue;
        store.add(k); n++;
        const [date, desc, mi, mo] = k.split("|");
        db.txns[a.reconciliationId].push({ id: id(), description: desc, debit_amount: mi, credit_amount: mo, status: "UNMATCHED" });
      }
      return { purpose: a.purpose, result: { imported: n, evidence_id: ev.id } };
    },
    // ---- Security stand-in
    async securityOverview() { return { encryption: { configured: !noKeys, current_key: "k1", keys: noKeys ? [] : ["k1"], keys_in_use: {} }, storage: { enabled: !noKeys, backend: "database", region: "unspecified" },
      audit_chain: { enabled: !noKeys, head: 3 }, mfa: { members: 1, with_mfa: 0, required: false, available: !noKeys }, sso: { configured: false }, residency: { allowed_regions: [] },
      retention: { days: { EVIDENCE: 2555 } }, holds: 0, alerts_open: 0, vendors_overdue: 0, backups: { known: false }, session_policy: { idle_minutes: 30, max_sessions: 5 } }; },
    async mySecurity() { return { mfa: { enabled: false }, mfa_available: !noKeys, sessions: [{ session_id: "s1", current: true, ...(leakSessions ? { token_hash: "abc" } : {}) }], idle_minutes: 30, privacy_requests: [] }; },
    async mfaBegin() { return { secret: "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP", otpauth_uri: "otpauth://totp/ASAVEXA:x?secret=JBSWY3DP" }; },
    async mfaConfirm() { bad(400, "That code is not right."); },
    async mfaDisable() { bad(400, "not enrolled"); },
    async verifyAuditChain() { return noKeys ? { enabled: false, ok: null, note: "off" } : breakChain ? { enabled: true, ok: false, links: 3, problem_count: 1, problems: [{ kind: "EVENT_CHANGED" }] } : { enabled: true, ok: true, links: 3, unchained_events: 0, problems: [], problem_count: 0 }; },
    async evidenceStorage(i) { return noKeys ? { stored: false, info: null } : { stored: true, info: { state: "STORED", backend: "database" } }; },
    async downloadEvidence(i) { const e = db.evidence.find((x) => x.id === i); return { blob: new Blob([e.text]), filename: "x.txt" }; },
    async setRetention(d) { if (d < 2190) bad(400, "Evidence must be kept for at least 2190 days"); return {}; },
    async disposeEvidence() { bad(409, "This evidence must be kept until 2033-01-01."); },
    async placeHold(reason) { db.hold = { id: "h1", reason, released_at: null }; return db.hold; },
    async getRetention() { return { holds: [db.hold], policy: {}, due_for_disposal: [] }; },
    async releaseHold() { db.hold.released_at = "now"; return db.hold; },
    async updateSecuritySettings(b) { if ((b.allowed_regions || []).some((r) => !["NG", "EU"].includes(r))) bad(400, "Unknown region code(s)"); return b; },
    async addVendor(v) { return { ...v, risk_tier: "HIGH", risk_reasons: ["No signed agreement.", "No plan for leaving."] }; },
    async exportMyData() { return { account: { email: "a@b.c" }, audit_events_about_you: [] }; },
    async securityHealth() { return { status: "OK", checks: [{ name: "database", ok: true }] }; },
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

test("self-test: the Import steps run and pass", async () => {
  const results = await runSelfTest(fakeApi(), { orgId: "org1" });
  const imp = results.filter((r) => r.group === "Import");
  assert.equal(imp.length, 9);
  assert.deepEqual(imp.filter((r) => r.status !== "pass"), [], JSON.stringify(imp, null, 1));
});

test("self-test: an import that creates duplicates on re-import is caught", async () => {
  const results = await runSelfTest(fakeApi({ breakImportDedupe: true }), { orgId: "org1" });
  assert.ok(results.some((r) => r.status === "fail" && r.group === "Import" && /same file again/.test(r.name)));
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


test("self-test: the Security steps run and pass", async () => {
  const results = await runSelfTest(fakeApi(), { orgId: "org1" });
  const sec = results.filter((r) => r.group === "Security");
  assert.equal(sec.length, 12);
  assert.deepEqual(sec.filter((r) => r.status !== "pass"), [], JSON.stringify(sec, null, 1));
});

test("self-test: without encryption keys the Security steps warn instead of passing", async () => {
  const results = await runSelfTest(fakeApi({ noKeys: true }), { orgId: "org1" });
  const sec = results.filter((r) => r.group === "Security");
  assert.equal(sec.filter((r) => r.status === "fail").length, 0, JSON.stringify(sec.filter((r) => r.status === "fail")));
  for (const name of [/overview/, /two-step code/, /tamper-evident/, /stored encrypted/]) {
    const r = sec.find((x) => name.test(x.name));
    assert.equal(r.status, "warn", `${r.name} should warn when keys are missing`);
  }
});

test("self-test: a broken audit chain is caught", async () => {
  const results = await runSelfTest(fakeApi({ breakChain: true }), { orgId: "org1" });
  assert.ok(results.some((r) => r.status === "fail" && r.group === "Security" && /tamper-evident/.test(r.name)));
});

test("self-test: a device list that leaks a token fingerprint is caught", async () => {
  const results = await runSelfTest(fakeApi({ leakSessions: true }), { orgId: "org1" });
  assert.ok(results.some((r) => r.status === "fail" && r.group === "Security" && /device list/.test(r.name)));
});
