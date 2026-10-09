/**
 * End-to-end self-test: drives the REAL API (whatever baseUrl the
 * ApiClient was built with) through the full ASAVEXA workflow and
 * reports pass / fail / warn for each step, with the exact HTTP status
 * and server message on any failure. Nothing here is simulated: every
 * step is a real request, and every created record is a real record in
 * the organisation you are signed into (all clearly labelled
 * "SelfTest"). It never bypasses permissions or validation — it
 * deliberately sends invalid data too, and checks the API rejects it
 * with a proper 4xx instead of a crash or a lost connection.
 *
 * Status meanings: "pass" (did what was expected), "fail" (broken),
 * "warn" (the API answered correctly but a business rule stopped the
 * step — e.g. maker-checker: the same user cannot verify their own
 * work), "skip" (an earlier step this one depends on failed).
 */
import { ApiError, NetworkError } from "../api/client.js";

function describeError(err) {
  if (err instanceof NetworkError) return `NETWORK (${err.diagnosis}): ${err.message}`;
  if (err instanceof ApiError) return `HTTP ${err.status}: ${err.message}`;
  return String((err && err.message) || err);
}

/** Runs `fn` and requires it to be rejected by the API with a 4xx. */
async function expectRejected(fn, allowed = [400, 403, 404, 409, 422]) {
  try {
    await fn();
  } catch (err) {
    if (err instanceof ApiError && allowed.includes(err.status)) return err;
    throw new Error(`expected a clean 4xx rejection but got ${describeError(err)}`);
  }
  throw new Error("expected the API to reject this request, but it was accepted");
}

function check(cond, message) {
  if (!cond) throw new Error(message);
}

const dec = (v) => Number(v);

export async function runSelfTest(api, { onResult, orgId } = {}) {
  const ctx = {};
  const tag = String(Date.now()).slice(-7);
  const year = 2100 + (Number(tag) % 800);
  const results = [];
  const emit = (r) => { results.push(r); if (onResult) onResult(r); };

  async function step(group, name, needs, fn) {
    if (needs.some((k) => ctx[k] === undefined)) {
      emit({ group, name, status: "skip", detail: `skipped: needs an earlier step (${needs.filter((k) => ctx[k] === undefined).join(", ")})`, ms: 0 });
      return;
    }
    const started = Date.now();
    try {
      const detail = await fn();
      emit({ group, name, status: "pass", detail: detail || "", ms: Date.now() - started });
    } catch (err) {
      const warn = err && err.warn;
      emit({ group, name, status: warn ? "warn" : "fail", detail: warn ? err.message : describeError(err), ms: Date.now() - started });
    }
  }
  const warnOn = (err, statuses) => {
    if (err instanceof ApiError && statuses.includes(err.status)) {
      const w = new Error(`API answered correctly: ${err.message}`);
      w.warn = true;
      throw w;
    }
    throw err;
  };

  // ---------------- 1. Connectivity ----------------
  await step("Connectivity", "API health endpoint", [], async () => {
    const r = await api.rawGet("/health");
    if (r.error) throw r.error;
    check(r.ok, `HTTP ${r.status}`);
    return `HTTP ${r.status} in ${r.ms} ms`;
  });
  await step("Connectivity", "Database reachable (/ready)", [], async () => {
    const r = await api.rawGet("/ready");
    if (r.error) throw r.error;
    check(r.ok, `HTTP ${r.status}: ${JSON.stringify(r.body)}`);
    return "PostgreSQL answered";
  });
  await step("Connectivity", "Signed in and organisation selected", [], async () => {
    const orgs = await api.myOrganisations();
    check(orgs.some((o) => o.id === orgId), "your current organisation was not returned by /organisations/mine");
    ctx.orgId = orgId;
    return `${orgs.length} organisation(s) available`;
  });

  // ---------------- 2. Administration ----------------
  await step("Administration", "Save organisation profile", ["orgId"], async () => {
    const before = await api.getOrganisationProfile();
    const { org_id, updated_at, updated_by, ...fields } = before;
    ctx.profileBackup = fields;
    const payload = {
      ...fields,
      legal_name: fields.legal_name || `ASAVEXA SelfTest Organisation ${tag}`,
      base_currency: fields.base_currency || "NGN",
      fiscal_year_start_month: fields.fiscal_year_start_month || 1,
      reporting_framework: fields.reporting_framework || "IFRS_FOR_SMES",
      country: fields.country || "Nigeria",
    };
    const saved = await api.updateOrganisationProfile(payload);
    check(saved.legal_name === payload.legal_name, "saved profile did not echo legal_name");
    ctx.profile = saved;
    return "profile written";
  });
  await step("Administration", "Profile persisted (re-read from database)", ["profile"], async () => {
    const again = await api.getOrganisationProfile();
    check(again.legal_name === ctx.profile.legal_name, "profile did not persist");
    check(again.updated_by, "no updated_by recorded");
    return `legal name: ${again.legal_name}`;
  });
  await step("Administration", "Invalid email is rejected (422)", ["orgId"], async () => {
    const e = await expectRejected(() => api.updateOrganisationProfile({ contact_email: "not-an-email" }), [422]);
    return e.message;
  });
  await step("Administration", "Profile change is in the audit trail", ["profile"], async () => {
    const events = await api.entityAuditTrail("Organisation", ctx.orgId);
    check(events.some((e) => e.action === "ORGANISATION_PROFILE_UPDATED"), "no ORGANISATION_PROFILE_UPDATED event");
    return `${events.length} organisation audit event(s)`;
  });

  // ---------------- 2b. Standards ----------------
  await step("Standards", "Catalog lists jurisdictions, entity types and frameworks", ["orgId"], async () => {
    const c = await api.standardsCatalog();
    check(c.jurisdictions.length > 0 && c.entity_types.length > 0 && c.frameworks.length > 0, "catalog incomplete");
    return `${c.jurisdictions.length} jurisdictions, ${c.entity_types.length} entity types, ${c.frameworks.length} frameworks`;
  });
  await step("Standards", "Nigeria + SME resolves to IFRS for SMEs with policies and requirements", ["orgId"], async () => {
    const r = await api.resolveStandards({ jurisdiction: "NG", entity_type: "SME" });
    check(r.framework === "IFRS_FOR_SMES", `framework ${r.framework}`);
    check(r.policies.length > 0 && r.requirements.length > 0, "no policies / requirements");
    return `${r.policies.length} policies, ${r.requirements.length} requirements`;
  });
  await step("Standards", "Forbidden policy (LIFO under IFRS for SMEs) is rejected with a clear 400", ["orgId"], async () => {
    const e = await expectRejected(() => api.resolveStandards({ jurisdiction: "NG", entity_type: "SME", policy_overrides: { INVENTORY_COSTING: "LIFO" } }), [400]);
    return e.message;
  });
  await step("Standards", "Unknown jurisdiction is rejected with a clear 400", ["orgId"], async () => {
    const e = await expectRejected(() => api.resolveStandards({ jurisdiction: "ZZ", entity_type: "SME" }), [400]);
    return e.message;
  });
  await step("Standards", "Saved configuration persists (re-saved unchanged if one exists)", ["orgId"], async () => {
    const current = await api.getStandardsConfiguration();
    if (!current.configured) return "no configuration saved yet — save skipped so your setup is not changed";
    const saved = await api.saveStandardsConfiguration({
      jurisdiction: current.jurisdiction, entity_type: current.entity_type, framework: current.framework,
      policy_overrides: Object.fromEntries(current.policies.filter((p) => p.overridden).map((p) => [p.code, p.effective])),
    });
    check(saved.framework === current.framework, "framework changed on re-save");
    const again = await api.getStandardsConfiguration();
    check(again.configured && again.framework === current.framework, "did not persist");
    return `${again.jurisdiction} / ${again.entity_type} / ${again.framework}`;
  });

  // ---------------- 3. Accounting ----------------
  const acct = async (key, code, name, type) => {
    ctx[key] = await api.createAccount({ code: `ST${tag}${code}`, name: `SelfTest ${name}`, type, currency: "NGN" });
    check(ctx[key].id, "no id returned");
  };
  await step("Accounting", "Create bank account (asset)", ["orgId"], async () => { await acct("bank", "1", "Cash/Bank", "ASSET"); return ctx.bank.code; });
  await step("Accounting", "Create VAT input account (asset)", ["orgId"], async () => { await acct("vat", "2", "VAT Input", "ASSET"); return ctx.vat.code; });
  await step("Accounting", "Create accounts payable (liability)", ["orgId"], async () => { await acct("ap", "3", "Accounts Payable", "LIABILITY"); return ctx.ap.code; });
  await step("Accounting", "Create professional fees (expense)", ["orgId"], async () => { await acct("fees", "4", "Professional Fees Expense", "EXPENSE"); return ctx.fees.code; });
  await step("Accounting", "Create revenue account", ["orgId"], async () => { await acct("rev", "5", "Revenue", "REVENUE"); return ctx.rev.code; });
  await step("Accounting", "Duplicate account code is rejected", ["bank"], async () => {
    const e = await expectRejected(() => api.createAccount({ code: ctx.bank.code, name: "dup", type: "ASSET", currency: "NGN" }));
    return `HTTP ${e.status}: ${e.message}`;
  });
  await step("Accounting", "Accounts appear in chart of accounts", ["bank", "fees"], async () => {
    const list = await api.listAccounts();
    check(list.some((a) => a.id === ctx.bank.id) && list.some((a) => a.id === ctx.fees.id), "created accounts missing from list");
    return `${list.length} accounts`;
  });
  await step("Accounting", "Open accounting period", ["orgId"], async () => {
    ctx.period = await api.openPeriod({ name: `SelfTest ${tag}`, start_date: `${year}-01-01`, end_date: `${year}-01-31` });
    check(ctx.period.id, "no id returned");
    return `${ctx.period.name} (${ctx.period.status})`;
  });
  await step("Accounting", "Unbalanced journal is rejected", ["fees", "ap", "period"], async () => {
    const e = await expectRejected(() => api.createDraftJournal({
      date: `${year}-01-10`, description: "SelfTest unbalanced", currency: "NGN",
      lines: [
        { account_id: ctx.fees.id, debit_amount: "1000.00", credit_amount: "0.00" },
        { account_id: ctx.ap.id, debit_amount: "0.00", credit_amount: "900.00" },
      ],
    }));
    return `HTTP ${e.status}: ${e.message}`;
  });
  await step("Accounting", "Journal with a non-existent account is rejected", ["period"], async () => {
    const e = await expectRejected(() => api.createDraftJournal({
      date: `${year}-01-10`, description: "SelfTest bad account", currency: "NGN",
      lines: [
        { account_id: "00000000-0000-4000-8000-000000000000", debit_amount: "10.00", credit_amount: "0.00" },
        { account_id: "00000000-0000-4000-8000-000000000001", debit_amount: "0.00", credit_amount: "10.00" },
      ],
    }));
    return `HTTP ${e.status}: ${e.message}`;
  });
  await step("Accounting", "Create balanced journal: 1,000,000 + 75,000 VAT = 1,075,000", ["fees", "vat", "ap", "period"], async () => {
    ctx.journal = await api.createDraftJournal({
      date: `${year}-01-15`, description: `SelfTest professional services invoice ${tag}`, currency: "NGN",
      transaction_ref: `ST-INV-${tag}`,
      lines: [
        { account_id: ctx.fees.id, debit_amount: "1000000.00", credit_amount: "0.00", description: "Professional services" },
        { account_id: ctx.vat.id, debit_amount: "75000.00", credit_amount: "0.00", description: "VAT input 7.5%" },
        { account_id: ctx.ap.id, debit_amount: "0.00", credit_amount: "1075000.00", description: "Payable to supplier" },
      ],
    });
    check(ctx.journal.status === "DRAFT", `status ${ctx.journal.status}`);
    const d = ctx.journal.lines.reduce((s, l) => s + dec(l.debit_amount), 0);
    const c = ctx.journal.lines.reduce((s, l) => s + dec(l.credit_amount), 0);
    check(d === 1075000 && c === 1075000, `stored totals are debit ${d} / credit ${c}`);
    return `${ctx.journal.journal_number}: debits ${d.toLocaleString()} = credits ${c.toLocaleString()}`;
  });
  await step("Accounting", "Journal appears in journal list", ["journal"], async () => {
    const list = await api.listJournals();
    check(list.some((j) => j.id === ctx.journal.id), "new journal missing from GET /journals");
    return `${list.length} journal(s)`;
  });

  // ---------------- 4. Evidence ----------------
  await step("Evidence", "Upload invoice linked to the journal", ["journal"], async () => {
    const text = `SELF-TEST INVOICE ${tag}\nProfessional services NGN 1,000,000.00\nVAT 7.5% NGN 75,000.00\nTotal NGN 1,075,000.00\n`;
    ctx.invoiceText = text;
    const file = new File([text], `selftest-invoice-${tag}.txt`, { type: "text/plain" });
    ctx.evidence = await api.uploadEvidence({ file, type: "INVOICE", linkedJournalId: ctx.journal.id, linkedTransactionRef: `ST-INV-${tag}` });
    const e = ctx.evidence;
    check(e.id && e.file_hash && e.file_hash.length >= 32, "no id / hash returned");
    check(e.original_filename === file.name, `filename stored as ${e.original_filename}`);
    check(e.size_bytes === text.length, `size ${e.size_bytes} vs ${text.length}`);
    check(e.linked_journal_id === ctx.journal.id, "journal link not stored");
    return `${e.status}, ${e.size_bytes} bytes, ${e.content_type}, sha ${e.file_hash.slice(0, 12)}…`;
  });
  await step("Evidence", "Evidence retrievable by id", ["evidence"], async () => {
    const e = await api.getEvidence(ctx.evidence.id);
    check(e.file_hash === ctx.evidence.file_hash, "hash changed");
    check(e.uploaded_by && e.uploaded_at, "uploader / timestamp missing");
    return `uploaded by ${e.uploaded_by}`;
  });
  await step("Evidence", "Evidence appears in list", ["evidence"], async () => {
    const list = await api.listEvidence();
    check(list.some((e) => e.id === ctx.evidence.id), "uploaded evidence missing from GET /evidence");
    return `${list.length} record(s)`;
  });
  await step("Evidence", "Journal → evidence link resolves (Show me the evidence)", ["evidence"], async () => {
    const s = await api.evidenceStatus(ctx.journal.id);
    check(s.evidence_id === ctx.evidence.id, `status endpoint returned ${JSON.stringify(s)}`);
    return `status ${s.status}`;
  });
  await step("Evidence", "Duplicate upload is handled with a clear error", ["evidence"], async () => {
    const file = new File([ctx.invoiceText], `selftest-invoice-${tag}-copy.txt`, { type: "text/plain" });
    const e = await expectRejected(() => api.uploadEvidence({ file, type: "INVOICE" }));
    return `HTTP ${e.status}: ${e.message}`;
  });
  await step("Evidence", "Invalid linked journal id is rejected (not a crash)", ["journal"], async () => {
    const file = new File(["different content " + tag], `selftest-bad-${tag}.txt`, { type: "text/plain" });
    const e = await expectRejected(() => api.uploadEvidence({ file, type: "OTHER", linkedJournalId: "not-a-uuid" }));
    return `HTTP ${e.status}: ${e.message}`;
  });
  await step("Evidence", "Verify evidence", ["evidence"], async () => {
    try {
      const v = await api.verifyEvidence(ctx.evidence.id);
      check(v.status === "VERIFIED", `status ${v.status}`);
      return "VERIFIED";
    } catch (err) { return warnOn(err, [403, 409]); }
  });
  await step("Evidence", "Evidence upload is in the audit trail", ["evidence"], async () => {
    const events = await api.entityAuditTrail("EvidenceRecord", ctx.evidence.id);
    check(events.length >= 1, "no audit events");
    return events.map((e) => e.action).join(", ");
  });

  // ---------------- 5. Posting ----------------
  await step("Accounting", "Post journal", ["journal"], async () => {
    ctx.posted = await api.postJournal(ctx.journal.id);
    check(ctx.posted.status === "POSTED", `status ${ctx.posted.status}`);
    return "POSTED";
  });
  await step("Accounting", "Journal audit trail records create and post", ["posted"], async () => {
    const events = await api.journalAuditTrail(ctx.journal.id);
    check(events.length >= 2, `only ${events.length} event(s)`);
    return events.map((e) => e.action).join(", ");
  });

  // ---------------- 6. Reconciliation ----------------
  await step("Reconciliation", "Unknown bank account is rejected (not 'could not reach API')", ["period"], async () => {
    const e = await expectRejected(() => api.createReconciliation({
      bank_account_id: "00000000-0000-4000-8000-000000000000", name: "SelfTest bad", period_start: `${year}-01-01`, period_end: `${year}-01-31`, currency: "NGN",
    }));
    return `HTTP ${e.status}: ${e.message}`;
  });
  await step("Reconciliation", "Non-ID bank account text is rejected cleanly", ["period"], async () => {
    const e = await expectRejected(() => api.createReconciliation({
      bank_account_id: "my bank", name: "SelfTest text", period_start: `${year}-01-01`, period_end: `${year}-01-31`, currency: "NGN",
    }));
    return `HTTP ${e.status}: ${e.message}`;
  });
  await step("Reconciliation", "Create reconciliation for the real bank account", ["bank", "period"], async () => {
    ctx.recon = await api.createReconciliation({
      bank_account_id: ctx.bank.id, name: `SelfTest reconciliation ${tag}`, period_start: `${year}-01-01`, period_end: `${year}-01-31`, currency: "NGN",
    });
    check(ctx.recon.id && ctx.recon.status === "DRAFT", `status ${ctx.recon.status}`);
    return `${ctx.recon.status}`;
  });
  await step("Reconciliation", "Import bank statement line", ["recon"], async () => {
    await api.importTransactions(ctx.recon.id, [{
      transaction_date: `${year}-01-20`, description: `Payment to supplier ${tag}`, debit_amount: "0.00", credit_amount: "1075000.00",
      external_ref: `ST-BANK-${tag}`, currency: "NGN",
    }]);
    const txns = await api.listReconciliationTransactions(ctx.recon.id);
    check(txns.length === 1, `${txns.length} transaction(s) after import`);
    ctx.bankTxn = txns[0];
    return `imported; status ${ctx.bankTxn.status}`;
  });
  await step("Reconciliation", "Reconciliation persisted and listed", ["recon"], async () => {
    const list = await api.listReconciliations();
    check(list.some((r) => r.id === ctx.recon.id), "missing from list");
    const events = await api.entityAuditTrail("Reconciliation", ctx.recon.id);
    check(events.length >= 1, "no audit event");
    return `${list.length} reconciliation(s), ${events.length} audit event(s)`;
  });

  // ---------------- 7. Reporting ----------------
  await step("Reporting", "Trial balance is balanced", ["posted", "period"], async () => {
    const tb = await api.trialBalance(ctx.period.id);
    check(tb.is_balanced === true, "trial balance not balanced");
    check(dec(tb.total_debits) === 1075000 && dec(tb.total_credits) === 1075000, `totals ${tb.total_debits}/${tb.total_credits}`);
    return `debits ${tb.total_debits} = credits ${tb.total_credits}`;
  });
  await step("Reporting", "Income statement", ["posted", "period"], async () => {
    const is = await api.incomeStatement(ctx.period.id);
    check(dec(is.total_expenses) === 1000000, `expenses ${is.total_expenses}`);
    return `expenses ${is.total_expenses}`;
  });
  await step("Reporting", "Balance sheet", ["posted", "period"], async () => {
    const bs = await api.balanceSheet(ctx.period.id);
    return `assets ${bs.total_assets}, liabilities ${bs.total_liabilities}`;
  });
  await step("Reporting", "General ledger filtered to one account", ["posted", "period"], async () => {
    const gl = await api.generalLedger(ctx.period.id, ctx.fees.id);
    check(gl.accounts.length === 1 && gl.accounts[0].account_id === ctx.fees.id, `returned ${gl.accounts.length} account section(s)`);
    return "1 account section";
  });
  await step("Reporting", "Trace links account balance back to the journal", ["posted", "period"], async () => {
    const trace = await api.traceLine(ctx.fees.id, ctx.period.id);
    const text = JSON.stringify(trace);
    check(text.includes(ctx.journal.id), "journal id not present in trace");
    return "journal found in trace";
  });
  await step("Reporting", "Invalid account id gives a clean error", ["period"], async () => {
    const e = await expectRejected(() => api.traceLine("not-a-uuid", ctx.period.id));
    return `HTTP ${e.status}: ${e.message}`;
  });
  await step("Reporting", "Evidence completeness for the account", ["posted", "period"], async () => {
    const c = await api.evidenceCompleteness(ctx.fees.id, ctx.period.id);
    return JSON.stringify(c).slice(0, 120);
  });

  // ---------------- 8. Compliance ----------------
  await step("Compliance", "Seed standard controls (9)", ["orgId"], async () => {
    await api.seedStandardControls();
    const controls = await api.listControls();
    ctx.controls = Object.fromEntries(controls.map((c) => [c.code, c]));
    check(controls.length >= 9, `${controls.length} controls`);
    return `${controls.length} controls`;
  });
  const runControl = (code, withJournal) => async () => {
    const c = ctx.controls[code];
    const ex = await api.executeControl(c.id, ctx.period.id, withJournal ? { journal_id: ctx.journal.id } : {});
    check(ex.id && ex.result, "no result");
    ctx.execs = ctx.execs || {};
    ctx.execs[code] = ex;
    return `${ex.result}: ${ex.explanation}`.slice(0, 160);
  };
  for (const [code, withJournal] of [["ACC-001"], ["ACC-002"], ["ACC-003"], ["REC-001"], ["EVI-002", true], ["REP-001"], ["CLS-001"], ["CLS-002"]]) {
    await step("Compliance", `Execute ${code}`, ["controls", "period", "journal"], runControl(code, withJournal));
  }
  await step("Compliance", "Execute EVI-001 with the invoice as required evidence", ["controls", "period", "evidence"], async () => {
    const c = ctx.controls["EVI-001"];
    const ex = await api.executeControl(c.id, ctx.period.id, { evidence_refs: [ctx.evidence.id] });
    ctx.execs = ctx.execs || {};
    ctx.execs["EVI-001"] = ex;
    return `${ex.result}: ${ex.explanation}`.slice(0, 160);
  });
  await step("Compliance", "Executions are listed", ["execs"], async () => {
    const list = await api.listExecutions(ctx.period.id);
    check(list.length >= Object.keys(ctx.execs).length, `${list.length} executions listed`);
    return `${list.length} execution(s)`;
  });
  await step("Compliance", "A finding exists for a non-passing result", ["execs"], async () => {
    const bad = Object.values(ctx.execs).find((e) => ["FAIL", "WARNING", "REQUIRES_REVIEW"].includes(e.result));
    if (!bad) { return "every control passed — no finding needed"; }
    let findingId = bad.finding_id;
    if (!findingId) {
      const f = await api.createFindingFromExecution(bad.id, `SelfTest finding for ${bad.result} result`);
      findingId = f.id;
    }
    ctx.finding = await api.getFinding(findingId);
    check(ctx.finding.id, "finding not retrievable");
    return `finding ${ctx.finding.status} (${ctx.finding.severity})`;
  });
  await step("Compliance", "Finding → review → remediation → verification", ["finding"], async () => {
    let f = ctx.finding;
    if (f.status === "OPEN") f = await api.startFindingReview(f.id);
    if (f.status === "UNDER_REVIEW") f = await api.markRemediationRequired(f.id);
    check(f.status === "REMEDIATION_REQUIRED", `finding is ${f.status}`);
    const r = await api.createRemediation(f.id, "SelfTest remediation: attach evidence", "selftest", undefined);
    await api.startRemediation(r.id);
    await api.completeRemediation(r.id, ctx.evidence ? ctx.evidence.id : undefined);
    try {
      const v = await api.verifyRemediation(r.id, "SelfTest verification");
      return `remediation ${v.status}`;
    } catch (err) { return warnOn(err, [403, 409]); }
  });

  // ---------------- 9. Audit workspace ----------------
  await step("Audit Workspace", "Trace journal → evidence → audit trail", ["posted", "evidence"], async () => {
    const j = await api.getJournal(ctx.journal.id);
    const s = await api.evidenceStatus(ctx.journal.id);
    const ev = await api.getEvidence(s.evidence_id);
    const events = await api.journalAuditTrail(ctx.journal.id);
    check(j.id === ctx.journal.id && ev.id === ctx.evidence.id && events.length >= 2, "chain incomplete");
    return `journal ${j.journal_number} → evidence ${ev.original_filename} → ${events.length} audit events`;
  });
  await step("Audit Workspace", "Unknown journal id is a clean 404", ["orgId"], async () => {
    const e = await expectRejected(() => api.getJournal("00000000-0000-4000-8000-000000000000"));
    return `HTTP ${e.status}: ${e.message}`;
  });
  await step("Audit Workspace", "Malformed journal id is a clean 4xx", ["orgId"], async () => {
    const e = await expectRejected(() => api.getJournal("garbage"));
    return `HTTP ${e.status}: ${e.message}`;
  });

  // ---------------- 10. Period close ----------------
  await step("Period Close", "Close readiness report", ["period"], async () => {
    const r = await api.checkCloseReadiness(ctx.period.id);
    check(Array.isArray(r.findings), "no findings array");
    return `${r.is_ready ? "READY" : "NOT READY"}; ${r.findings.length} control(s) checked` +
      (r.blocking_failures && r.blocking_failures.length ? `; blocking: ${r.blocking_failures.join(", ")}` : "");
  });

  // ---------------- 11. Multi-tenancy ----------------
  await step("Multi-tenancy", "Another organisation cannot see this organisation's data", ["journal", "evidence", "orgId"], async () => {
    let orgB = null;
    try {
      orgB = await api.createOrganisation(`SelfTest isolation ${tag}`);
      await api.selectOrganisation(orgB.id);
      const accounts = await api.listAccounts();
      check(!accounts.some((a) => a.id === ctx.bank.id), "organisation B can see organisation A's accounts");
      const e1 = await expectRejected(() => api.getJournal(ctx.journal.id));
      const e2 = await expectRejected(() => api.getEvidence(ctx.evidence.id));
      const journals = await api.listJournals();
      check(!journals.some((j) => j.id === ctx.journal.id), "organisation B can list organisation A's journals");
      return `journal → HTTP ${e1.status}, evidence → HTTP ${e2.status}, B sees 0 of A's records`;
    } finally {
      await api.selectOrganisation(ctx.orgId); // always return the session to your organisation
    }
  });

  // ---------------- 12. Persistence ----------------
  await step("Persistence", "Everything is still there when re-read (like a page refresh)", ["posted", "evidence", "recon"], async () => {
    const [j, e, r, p] = await Promise.all([
      api.getJournal(ctx.journal.id), api.getEvidence(ctx.evidence.id), api.getReconciliation(ctx.recon.id), api.getOrganisationProfile(),
    ]);
    check(j.status === "POSTED" && e.file_hash === ctx.evidence.file_hash && r.id === ctx.recon.id && p.legal_name, "something changed or went missing");
    return "journal, evidence, reconciliation and profile all persisted";
  });

  return results;
}

export function summarise(results) {
  const count = (s) => results.filter((r) => r.status === s).length;
  return { total: results.length, pass: count("pass"), fail: count("fail"), warn: count("warn"), skip: count("skip") };
}
