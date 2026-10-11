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
  await step("Proof-to-Report Graph", "Every figure links down to its journals, and the journal links to its evidence", ["posted", "period", "evidence"], async () => {
    const g = await api.proofGraph(ctx.period.id, "income_statement");
    check(["PROVEN", "PARTIAL"].includes(g.state), `the graph says ${g.state}: ${g.meaning}`);
    check(g.summary.tie_failures === 0, `${g.summary.tie_failures} figure(s) do not tie to their journals`);
    const ids = new Set(g.nodes.map((n) => n.id));
    check(g.edges.every((e) => ids.has(e.from) && ids.has(e.to)), "the graph has a link to something that is not in it");
    const j = g.nodes.find((n) => n.kind === "journal" && n.id === `journal:${ctx.journal.id}`);
    check(!!j, "the test journal is not in the graph");
    check(j.evidence_status !== "MISSING", "the test journal's evidence is not linked");
    check(g.edges.some((e) => e.kind === "supported_by" && e.from === j.id), "no link from the journal to its evidence");
    return `${g.state}: ${g.summary.journals} journal(s), ${g.summary.with_evidence} with evidence, every figure ties`;
  });
  await step("Proof-to-Report Graph", "Every layer of the architecture is present and wired", ["orgId"], async () => {
    const a = await api.proofArchitecture();
    const bad = a.layers.filter((l) => !l.ok);
    check(bad.length === 0, `not wired: ${bad.map((l) => `${l.name} (${l.problems.join("; ")})`).join(" | ")}`);
    check(a.layers.length >= 10, `only ${a.layers.length} layers reported`);
    return `${a.layers.length} layers loaded and mounted`;
  });
  await step("Financial Analysis", "The analysis agrees with the ledger and does not guess unclassified ratios", ["posted", "period"], async () => {
    const o = await api.analysisOverview(ctx.period.id);
    const t = o.totals, cents = (v) => Math.round(Number(v) * 100);
    check(cents(t.assets) - cents(t.liabilities) === cents(t.equity_total), `assets ${t.assets} less liabilities ${t.liabilities} is not total equity ${t.equity_total}`);
    check(cents(t.revenue) - cents(t.expenses) === cents(t.net_income), "revenue less expenses is not net income");
    const r = await api.analysisRatios(ctx.period.id);
    check(r.ratios.length > 0 && r.calculated <= r.total, "the ratio list is malformed");
    check(r.ratios.every((x) => x.status === "CALCULATED" ? x.value !== null && x.value !== undefined : x.value == null), "a ratio that could not be calculated still shows a number");
    return `${r.calculated} of ${r.total} ratios calculated, totals tie to the ledger`;
  });
  await step("Financial Analysis", "Forecasts are labelled and the workspace list is honest", ["orgId"], async () => {
    const be = await api.analysisBreakeven({ fixed_costs: "1000", price: "50", variable_cost: "30" });
    check(String(be.break_even_units) === "50", `break-even came back as ${be.break_even_units}, expected 50`);
    const w = await api.workspaces();
    const tax = w.workspaces.find((x) => x.id === "tax"), an = w.workspaces.find((x) => x.id === "analysis");
    check(!!an && an.path === "/analysis", "Financial Analysis is not listed");
    check(w.workspaces.every((x) => !["NOT STARTED", "BLOCKED"].includes(x.status) || !x.path), "an unbuilt workspace is shown as built");
    return "break-even correct, workspace statuses honest";
  });
  await step("Tax Compliance", "All countries are listed, and none has rules until a person enters and approves them", ["orgId"], async () => {
    const c = await api.taxCountries("", "");
    check(c.total >= 150 && c.countries.length === c.total, `only ${c.countries.length} countries listed`);
    check(new Set(c.countries.map((x) => x.code)).size === c.countries.length, "a country appears twice");
    const o = await api.taxOptions();
    check(Object.keys(o.tax_types).length >= 5, "the tax types are missing");
    return `${c.total} countries and territories listed`;
  });
  await step("Tax Compliance", "A draft tax rule cannot be used for a calculation until a second person approves it", ["orgId"], async () => {
    const stamp = Date.now().toString(36);
    const rule = await api.createTaxRule({ country: "GH", tax_type: "OTHER", name: `SelfTest rule ${stamp}`, method: "FLAT", rate: "1", rounding: "HALF_UP", effective_from: "2000-01-01", effective_to: "2000-12-31", authority: "Self-test", source_title: "Self-test only, not a real rule", source_url: "https://example.org/self-test", filing: null });
    try {
      check(rule.status === "DRAFT", `a new rule started as ${rule.status}`);
      const e = await expectRejected(() => api.taxCalculate({ rule_id: rule.id, amount: "100", date: "2000-06-01", inclusive: false }));
      check(e.status === 409, `calculating with a draft rule gave HTTP ${e.status}, expected 409`);
    } finally {
      await api.discardTaxRule(rule.id).catch(() => {});
    }
    return "draft refused (409), self-test rule discarded";
  });
  await step("Forensic Investigation", "The investigation tools load, and every test is described as an indicator", ["orgId"], async () => {
    const o = await api.forensicOptions();
    check(Object.keys(o.tests).length >= 9, `only ${Object.keys(o.tests).length} tests are offered`);
    check(o.limitations.some((l) => /not proof/i.test(l)), "the limitations do not say flags are not proof");
    const cases = await api.forensicCases();
    check(Array.isArray(cases), "the case list is malformed");
    return `${Object.keys(o.tests).length} tests, ${cases.length} case(s) in this organisation`;
  });
  await step("Governance, Risk and Compliance", "The risk register loads, the heat map is 5 by 5, and an impossible score is refused", ["orgId"], async () => {
    const o = await api.grcOptions();
    check(Object.keys(o.categories).length >= 8, "the risk categories are missing");
    check(o.limitations.some((l) => /judgement/i.test(l)), "the limitations do not say scores are judgements");
    const d = await api.grcDashboard();
    check(d.heatmap.cells.length === 5 && d.heatmap.cells.every((r) => r.length === 5), "the heat map is not 5 by 5");
    const risks = await api.grcRisks();
    check(Array.isArray(risks), "the risk list is malformed");
    const e = await expectRejected(() => api.createGrcRisk({ title: "Self-test", owner: "Self-test", category: "OTHER", inherent_l: 9, inherent_i: 1, treatment: "MITIGATE", next_review: "2099-01-01" }));
    check(e.status === 400, `a score of 9 gave HTTP ${e.status}, expected 400`);
    return `${risks.length} risk(s), appetite ${d.appetite}, score of 9 refused (400)`;
  });
  await step("Public Finance", "The public-finance tools load, the ledger-based limits are stated, and an empty budget is refused", ["orgId"], async () => {
    const o = await api.pubfinOptions();
    check(Array.isArray(o.accounts), "the account list is malformed");
    check(o.limitations.some((l) => /posted journals/i.test(l)), "the limitations do not say actuals come from posted journals");
    check(o.policy && o.policy.min_quotes >= 1, "the procurement policy is missing");
    const ov = await api.pubfinOverview();
    check(typeof ov.counts.budgets === "number", "the overview counts are missing");
    const e = await expectRejected(() => api.createPubfinBudget({ name: "Self-test", start: "2099-01-01", end: "2099-12-31", currency: "USD", lines: [] }));
    check(e.status === 400, `an empty budget gave HTTP ${e.status}, expected 400`);
    return `${ov.counts.budgets} budget(s), ${ov.counts.grants_active} active grant(s), empty budget refused (400)`;
  });
  await step("Business Development", "The pipeline tools load, the policy and limits are stated, and a worthless opportunity is refused", ["orgId"], async () => {
    const o = await api.bdOptions();
    check(Array.isArray(o.accounts) && Array.isArray(o.stages), "the option lists are malformed");
    check(o.policy && o.policy.probabilities && o.policy.discount_limit_pct != null, "the policy is missing");
    const ov = await api.bdOverview();
    check(ov.limitations.some((l) => /never converted|not converted/i.test(l)), "the limitations do not say currencies are never mixed");
    check(typeof ov.counts.opportunities === "number", "the overview counts are missing");
    const e = await expectRejected(() => api.createBdOpportunity({ account_id: "not-an-account", title: "Self-test", currency: "USD", value: "0", expected_close: "2099-01-01" }));
    check(e.status === 400 || e.status === 404, `a bad opportunity gave HTTP ${e.status}, expected 400 or 404`);
    return `${ov.counts.opportunities} opportunit(ies), ${ov.counts.accounts} account(s), bad opportunity refused (${e.status})`;
  });
  await step("Cybersecurity", "The records load, the limits say nothing is scanned, and a vulnerability on a missing asset is refused", ["orgId"], async () => {
    const o = await api.cyOptions();
    check(Array.isArray(o.assets) && Array.isArray(o.severities), "the option lists are malformed");
    check(o.policy && o.policy.sla_days && o.policy.acceptance_max_days >= 1, "the policy is missing");
    const ov = await api.cyOverview();
    check(ov.limitations.some((l) => /does not scan/i.test(l)), "the limitations do not say that nothing is scanned");
    check(typeof ov.counts.vulnerabilities_open === "number", "the overview counts are missing");
    const e = await expectRejected(() => api.createCyVuln({ asset_id: "not-an-asset", title: "Self-test", severity: "LOW", source: "self-test" }));
    check(e.status === 400 || e.status === 404, `a bad vulnerability gave HTTP ${e.status}, expected 400 or 404`);
    return `${ov.counts.assets} asset(s), ${ov.counts.vulnerabilities_open} open vulnerabilit(ies), bad vulnerability refused (${e.status})`;
  });
  await step("Health Centre", "The option lists load, the limits say no patient data is held, and an incomplete facility is refused", ["orgId"], async () => {
    const o = await api.hcOptions();
    check(Array.isArray(o.categories) && Array.isArray(o.facilities), "the option lists are malformed");
    check(o.limitations.some((l) => /no patient/i.test(l)), "the limitations do not say that no patient information is held");
    check(o.limitations.some((l) => /does not post|never post/i.test(l)), "the limitations do not say that nothing is posted to the ledger");
    const e = await expectRejected(() => api.hcPost("/facilities", { name: "Self-test" }));
    check(e.status === 400 || e.status === 403, `an incomplete facility gave HTTP ${e.status}, expected 400 or 403`);
    return `${o.facilities.length} facilit(ies) visible, incomplete facility refused (${e.status})`;
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

  // ---------------- 10b. Financial Passport ----------------
  const SECTIONS = ["identity", "financial_history", "evidence_quality", "governance", "reporting", "audit_trail"];
  await step("Passport", "Passport builds with all six sections and a fingerprint", ["orgId"], async () => {
    ctx.passport = await api.getPassport();
    const p = ctx.passport;
    for (const k of SECTIONS) check(p[k] && ["ok", "attention", "incomplete"].includes(p[k].status), `section ${k} missing or has no status`);
    check(/^[0-9a-f]{64}$/.test(p.fingerprint || ""), "fingerprint missing or malformed");
    check(p.schema_version, "no schema_version");
    return SECTIONS.map((k) => `${k}: ${p[k].status}`).join(", ");
  });
  await step("Passport", "Passport figures agree with the Reporting module for the self-test period", ["passport", "posted", "period"], async () => {
    const [is, bs] = await Promise.all([api.incomeStatement(ctx.period.id), api.balanceSheet(ctx.period.id)]);
    const row = ctx.passport.financial_history.periods.find((x) => x.period_id === ctx.period.id);
    check(row && row.has_activity, "the self-test period has no activity in the passport");
    check(dec(row.expenses) === dec(is.total_expenses), `passport expenses ${row.expenses} vs report ${is.total_expenses}`);
    check(dec(row.assets) === dec(bs.total_assets), `passport assets ${row.assets} vs report ${bs.total_assets}`);
    check(dec(row.liabilities) === dec(bs.total_liabilities), `passport liabilities ${row.liabilities} vs report ${bs.total_liabilities}`);
    return `expenses ${row.expenses}, assets ${row.assets}, liabilities ${row.liabilities} match the reports`;
  });
  await step("Passport", "Passport counts the self-test journal as supported by its evidence", ["passport", "posted", "evidence"], async () => {
    const e = ctx.passport.evidence_quality;
    check(e.transactions.total_posted >= 1, "no posted transactions counted");
    check(!e.missing_evidence.items.some((x) => x.journal_id === ctx.journal.id), "the journal is listed as missing evidence although evidence is linked to it");
    check(e.transactions.supported_verified + e.transactions.evidence_unverified + e.transactions.evidence_defective >= 1, "no journal has any evidence in the passport");
    return `${e.transactions.total_posted} posted, ${e.transactions.supported_verified} verified, ${e.transactions.evidence_unverified} unverified, ${e.transactions.missing_evidence} missing`;
  });
  await step("Passport", "Passport audit trail shows who created and who posted the journal", ["passport", "posted"], async () => {
    const j = ctx.passport.audit_trail.journal_provenance.find((x) => x.journal_id === ctx.journal.id);
    check(j, "journal not found in the audit provenance");
    check(j.created_by && j.created_at && j.posted_by && j.posted_at, `provenance incomplete: ${JSON.stringify(j)}`);
    check(ctx.passport.audit_trail.by_person.length >= 1, "no people listed in the audit trail");
    return `created by ${j.created_by}, posted by ${j.posted_by}`;
  });
  await step("Passport", "Segregation-of-duties check examines the journal", ["passport", "posted"], async () => {
    const c = ctx.passport.governance.segregation_of_duties.checks.find((x) => x.key === "journal_post");
    check(c && c.tested >= 1, "the journal creator/poster check tested nothing");
    return `${c.tested} journal(s) tested, ${c.violations} with the same person creating and posting`;
  });
  await step("Passport", "Reading the passport twice gives the same fingerprint", ["passport"], async () => {
    const again = await api.getPassport();
    check(again.fingerprint === ctx.passport.fingerprint, "fingerprint changed although nothing changed (generating a passport must not alter it)");
    return again.fingerprint.slice(0, 16) + "…";
  });
  await step("Passport", "Ownership above 100% is rejected with a clear message", ["orgId"], async () => {
    const e = await expectRejected(() => api.savePassportStructure({
      owners: [{ name: "SelfTest A", kind: "INDIVIDUAL", ownership_percent: 70 }, { name: "SelfTest B", kind: "INDIVIDUAL", ownership_percent: 50 }],
      subsidiaries: [],
    }), [400, 422]);
    return `HTTP ${e.status}: ${e.message}`;
  });
  await step("Passport", "Recorded ownership persists (re-saved unchanged if one exists)", ["passport"], async () => {
    const id = ctx.passport.identity;
    if (!id.ownership.recorded) return "no ownership recorded yet — save skipped so your setup is not changed";
    const keep = (o, keys) => Object.fromEntries(keys.filter((k) => o[k] !== undefined && o[k] !== null).map((k) => [k, o[k]]));
    await api.savePassportStructure({
      owners: id.ownership.owners.map((o) => keep(o, ["name", "kind", "ownership_percent", "notes"])),
      subsidiaries: id.subsidiaries.items.map((o) => keep(o, ["name", "relationship", "jurisdiction", "registration_number", "ownership_percent"])),
    });
    const after = await api.getPassport();
    check(after.identity.ownership.owners.length === id.ownership.owners.length, "owners changed on re-save");
    check(after.identity.subsidiaries.count === id.subsidiaries.count, "subsidiaries changed on re-save");
    return `${after.identity.ownership.owners.length} owner(s), ${after.identity.subsidiaries.count} subsidiary(ies)`;
  });

  // ---------------- 10c. Permissioned sharing ----------------
  const shareEmail = `selftest-${tag}@example.com`;
  await step("Sharing", "Creating a share returns a one-time link and access code", ["period", "posted"], async () => {
    ctx.shareRes = await api.createPassportShare({
      recipient_name: `SelfTest Bank ${tag}`, recipient_type: "BANK", recipient_email: shareEmail,
      purpose: "SelfTest", scopes: ["IDENTITY", "FINANCIAL_HISTORY"], date_from: `${year}-01-01`, date_to: `${year}-01-31`,
      include_detail: false, allow_download: false, closed_periods_only: false, expires_in_days: 1,
    });
    const r = ctx.shareRes;
    check(r.access_token && r.access_token.includes("."), "no secure link token returned");
    check(r.access_code && r.access_code.length >= 10, "no access code returned");
    check(r.share && r.share.status === "ACTIVE", "share is not ACTIVE");
    check(!JSON.stringify(r.share).includes(r.access_code), "the access code leaked into the share record");
    ctx.shareCreated = true;
    return `share ${r.share.id.slice(0, 8)}… ACTIVE`;
  });
  await step("Sharing", "The organisation's share list never reveals the code or link", ["shareCreated"], async () => {
    const list = await api.listPassportShares();
    const mine = list.find((x) => x.id === ctx.shareRes.share.id);
    check(mine, "the new share is not in the list");
    const text = JSON.stringify(list);
    check(!text.includes(ctx.shareRes.access_code) && !text.includes(ctx.shareRes.access_token.split(".")[1]), "a secret appears in the list");
    return `${list.length} share(s) listed`;
  });
  await step("Sharing", "A wrong access code is refused", ["shareCreated"], async () => {
    const e = await expectRejected(() => api.verifyShare({ accessToken: ctx.shareRes.access_token, accessCode: "WRONG-CODE0", email: shareEmail }), [403]);
    return `HTTP ${e.status}: ${e.message}`;
  });
  await step("Sharing", "The wrong email is refused even with the right code", ["shareCreated"], async () => {
    const e = await expectRejected(() => api.verifyShare({ accessToken: ctx.shareRes.access_token, accessCode: ctx.shareRes.access_code, email: "someone.else@example.com" }), [403]);
    return `HTTP ${e.status}`;
  });
  await step("Sharing", "A made-up link is refused without revealing anything", ["shareCreated"], async () => {
    const id = ctx.shareRes.share.id;
    const e = await expectRejected(() => api.verifyShare({ accessToken: `${id}.not-the-secret`, accessCode: ctx.shareRes.access_code, email: shareEmail }), [403]);
    return `HTTP ${e.status}`;
  });
  await step("Sharing", "The right code and email open exactly the chosen sections", ["shareCreated"], async () => {
    const v = await api.verifyShare({ accessToken: ctx.shareRes.access_token, accessCode: ctx.shareRes.access_code, email: shareEmail });
    check(v.session_token, "no session returned");
    ctx.shareSession = v.session_token;
    const view = await api.viewSharedPassport(v.session_token);
    const keys = Object.keys(view.sections).sort();
    check(keys.join(",") === "financial_history,identity", `recipient received ${keys.join(", ")} instead of only identity and financial_history`);
    check(view.integrity && view.integrity.verified === true, "integrity check did not pass");
    check(view.share.periods_included.some((pp) => pp.name === ctx.period.name), "the self-test period is missing from the shared periods");
    check(!JSON.stringify(view).includes(ctx.journal.id), "summary-level share exposes an individual journal id");
    ctx.shareView = view;
    return `sections: ${keys.join(", ")}; integrity verified`;
  });
  await step("Sharing", "Download is refused when the organisation did not allow it", ["shareSession"], async () => {
    const e = await expectRejected(() => api.downloadSharedPassport(ctx.shareSession), [403]);
    return `HTTP ${e.status}: ${e.message}`;
  });
  await step("Sharing", "Revoking stops access at once, even for an open session", ["shareSession"], async () => {
    await api.revokePassportShare(ctx.shareRes.share.id, "SelfTest finished");
    const a = await expectRejected(() => api.viewSharedPassport(ctx.shareSession), [403]);
    const b = await expectRejected(() => api.verifyShare({ accessToken: ctx.shareRes.access_token, accessCode: ctx.shareRes.access_code, email: shareEmail }), [403]);
    const after = (await api.listPassportShares()).find((x) => x.id === ctx.shareRes.share.id);
    check(after && after.status === "REVOKED", "share does not show as REVOKED");
    ctx.shareRevoked = true;
    return `open session → HTTP ${a.status}, new verification → HTTP ${b.status}`;
  });
  await step("Sharing", "The access log records every event", ["shareRevoked"], async () => {
    const log = await api.passportShareAccessLog(ctx.shareRes.share.id);
    const actions = new Set(log.map((e) => e.action));
    for (const need of ["PASSPORT_SHARE_CREATED", "PASSPORT_SHARE_DENIED", "PASSPORT_SHARE_VERIFIED", "PASSPORT_SHARE_VIEWED", "PASSPORT_SHARE_REVOKED"]) {
      check(actions.has(need), `the log has no ${need} entry`);
    }
    return `${log.length} entries`;
  });

  // ---------------- 10d. ASAVEXA AI ----------------
  const CHAIN = ["conclusion", "source_records", "evidence", "journal", "accounting_treatment", "reporting_framework", "confidence", "human_review"];
  const chainOk = (it) => CHAIN.every((k) => it && it[k] !== undefined && it[k] !== null);

  await step("AI", "Explain answers about the posted journal with the full grounded chain", ["posted"], async () => {
    ctx.aiExplain = await api.aiExplain({ subjectType: "journal", subjectId: ctx.journal.id });
    check(ctx.aiExplain.grounded === true && ctx.aiExplain.items.length >= 1, "the answer was not grounded");
    const it = ctx.aiExplain.items[0];
    check(chainOk(it), `the answer is missing a link of the chain (${CHAIN.filter((k) => !it || it[k] == null).join(", ")})`);
    check(["HIGH", "MEDIUM", "LOW"].includes(it.confidence.level), "confidence has no level");
    check(it.confidence.level === "HIGH" || it.human_review.required === true, "a less-than-high confidence answer did not ask for human review");
    return `confidence ${it.confidence.level}, human review ${it.human_review.required ? "required" : "not required"}`;
  });

  await step("AI", "Detect returns a grounded answer (an empty result is fine)", ["orgId"], async () => {
    const r = await api.aiDetect({ limit: 20 });
    check(r.grounded === true && Array.isArray(r.items), "Detect did not return a grounded list");
    for (const it of r.items) check(chainOk(it), "a flagged item has a broken chain");
    return `${r.items.length} item(s)`;
  });

  await step("AI", "Recommend only proposes: nothing is applied", ["orgId"], async () => {
    const r = await api.aiRecommend({ scope: "all", limit: 15 });
    check(r.grounded === true && Array.isArray(r.items), "Recommend did not return a grounded list");
    for (const it of r.items) {
      check(chainOk(it), "a recommendation has a broken chain");
      check(it.human_review.required === true, "a recommendation did not require a person");
      check(!it.proposal || it.proposal.applied === false, "a proposal claims to have been applied");
    }
    return `${r.items.length} proposal(s), none applied`;
  });

  await step("AI", "Prove gives a verdict backed by named checks", ["posted"], async () => {
    const r = await api.aiProve({ subjectType: "journal", subjectId: ctx.journal.id });
    check(r.grounded === true && r.verdict, "no verdict");
    check(["PROVEN", "PARTIALLY_PROVEN", "NOT_PROVEN"].includes(r.verdict), `unknown verdict ${r.verdict}`);
    check(chainOk(r.items[0]), "the proof has a broken chain");
    return r.verdict;
  });

  await step("AI", "Ask understands a plain question and refuses what it cannot ground", ["posted"], async () => {
    const good = await api.aiAsk("Find unusual transactions.");
    check(good.mode === "DETECT" && good.grounded === true, `routed to ${good.mode}`);
    const bad = await api.aiAsk("hello");
    check(bad.grounded === false && bad.refusal && bad.refusal.reason, "it answered something it could not ground");
    return "answered one, refused one";
  });

  await step("AI", "An unknown journal gives a clean 404, not a crash", ["orgId"], async () => {
    const e = await expectRejected(() => api.aiExplain({ subjectType: "journal", subjectId: "JRN-999999" }), [404]);
    return `HTTP ${e.status}`;
  });

  await step("AI", "Asking questions changes nothing in the books", ["posted"], async () => {
    const before = (await api.listJournals()).length;
    const fpBefore = (await api.getPassport()).fingerprint;
    await api.aiExplain({ subjectType: "journal", subjectId: ctx.journal.id });
    await api.aiRecommend({ scope: "all" });
    const after = (await api.listJournals()).length;
    const fpAfter = (await api.getPassport()).fingerprint;
    check(before === after, `journal count changed from ${before} to ${after}`);
    check(fpBefore === fpAfter, "the Financial Passport changed after asking AI questions");
    return "journal count and passport fingerprint unchanged";
  });

  // ---------------- 10e. External data ingestion ----------------
  const mkFile = (content, name) => (typeof File !== "undefined" ? new File([content], name, { type: "text/plain" }) : new Blob([content], { type: "text/plain" }));
  const STMT = `Date,Description,Debit,Credit,Balance\n${year}-01-12,SelfTest deposit ${tag},,5000.00,5000.00\n${year}-01-13,SelfTest fee ${tag},50.00,,4950.00\n${year}-01-14,SelfTest rent ${tag},900.00,,4050.00\n`;
  const imp = () => ({ purpose: "BANK_STATEMENT", reconciliationId: ctx.impRecon.id });

  await step("Import", "The import levels are listed honestly (no live connections claimed)", ["orgId"], async () => {
    const r = await api.ingestionLevels();
    check(Array.isArray(r.levels) && r.levels.length === 8, "expected the 8 import levels");
    check(!r.levels.some((l) => String(l.status).toUpperCase() === "LIVE"), "a level claims a live connection");
    return r.levels.map((l) => `${l.level}:${l.status}`).join(" ");
  });

  await step("Import", "Create a draft reconciliation to import into", ["bank"], async () => {
    ctx.impRecon = await api.createReconciliation({ bank_account_id: ctx.bank.id, name: `SelfTest import ${tag}`, period_start: `${year}-01-01`, period_end: `${year}-01-31`, currency: "NGN" });
    check(ctx.impRecon.status === "DRAFT", `status ${ctx.impRecon.status}`);
    return ctx.impRecon.status;
  });

  await step("Import", "Preview reads a bank statement and writes nothing", ["impRecon"], async () => {
    ctx.impJournalsBefore = (await api.listJournals()).length;
    ctx.impPreview = await api.ingestionPreview({ file: mkFile(STMT, "selftest-statement.csv"), ...imp(), options: {} });
    const p = ctx.impPreview;
    check(p.kind === "BANK_TRANSACTIONS" && p.status && p.status.importable === true, `not importable: ${JSON.stringify(p.status)}`);
    check(p.summary.lines === 3 && p.summary.money_in_total === "5000.00" && p.summary.money_out_total === "950.00", `unexpected totals ${JSON.stringify(p.summary)}`);
    check(typeof p.fingerprint === "string" && p.fingerprint.length === 64, "no fingerprint");
    const bc = (p.checks || []).find((c) => c.key === "BALANCE_CONTINUITY");
    check(bc && bc.result === "PASS", "the running-balance check did not pass");
    const txns = await api.listReconciliationTransactions(ctx.impRecon.id);
    check(txns.length === 0, `${txns.length} transaction(s) exist after a PREVIEW (a preview must write nothing)`);
    return `3 lines, money in 5000.00, out 950.00`;
  });

  await step("Import", "A statement with an unreadable date cannot be imported", ["impRecon"], async () => {
    const badCsv = `Date,Description,Amount\n${year}-01-12,ok ${tag},10.00\nnot-a-date,bad ${tag},10.00\n`;
    const p = await api.ingestionPreview({ file: mkFile(badCsv, "bad.csv"), ...imp(), options: {} });
    check(p.status.importable === false && p.status.errors >= 1, "an unreadable date was not reported as an error");
    const e = await expectRejected(() => api.ingestionCommit({ file: mkFile(badCsv, "bad.csv"), ...imp(), options: {}, fingerprint: p.fingerprint, acknowledge: true }), [400]);
    return `refused: HTTP ${e.status}`;
  });

  await step("Import", "Importing is refused if the file changed since the preview", ["impPreview"], async () => {
    const e = await expectRejected(() => api.ingestionCommit({ file: mkFile(STMT.replace("5000.00,5000.00", "9000.00,9000.00"), "selftest-statement.csv"), ...imp(), options: {},
      fingerprint: ctx.impPreview.fingerprint, acknowledge: true }), [400]);
    const txns = await api.listReconciliationTransactions(ctx.impRecon.id);
    check(txns.length === 0, "a refused import still wrote transactions");
    return `HTTP ${e.status}`;
  });

  await step("Import", "Import the statement: lines added, file kept as unverified evidence", ["impPreview"], async () => {
    const r = await api.ingestionCommit({ file: mkFile(STMT, "selftest-statement.csv"), ...imp(), options: {}, fingerprint: ctx.impPreview.fingerprint, acknowledge: true });
    check(r.result.imported === 3, `imported ${r.result.imported}`);
    const txns = await api.listReconciliationTransactions(ctx.impRecon.id);
    check(txns.length === 3, `${txns.length} transactions after import`);
    const dep = txns.find((t) => String(t.description).includes("deposit"));
    check(dep && Number(dep.debit_amount) === 5000 && Number(dep.credit_amount) === 0, "money in was not recorded on the debit side");
    const ev = await api.getEvidence(r.result.evidence_id);
    check(ev.status === "UPLOADED" && ev.type === "BANK_STATEMENT", `evidence is ${ev.type}/${ev.status} (it must be an UNVERIFIED bank statement)`);
    ctx.impEvidence = r.result.evidence_id;
    return `3 imported; evidence ${ev.status}`;
  });

  await step("Import", "Importing the same file again adds nothing and reuses the evidence", ["impEvidence"], async () => {
    const p = await api.ingestionPreview({ file: mkFile(STMT, "selftest-statement.csv"), ...imp(), options: {} });
    check(p.summary.already_imported === 3 && p.summary.to_import === 0, `preview says ${JSON.stringify(p.summary)}`);
    const r = await api.ingestionCommit({ file: mkFile(STMT, "selftest-statement.csv"), ...imp(), options: {}, fingerprint: p.fingerprint, acknowledge: true });
    check(r.result.imported === 0 && r.result.evidence_id === ctx.impEvidence, "the second import was not a no-op");
    check((await api.listReconciliationTransactions(ctx.impRecon.id)).length === 3, "duplicate lines were created");
    return "0 new lines, same evidence record";
  });

  await step("Import", "Bad requests are refused cleanly (unknown purpose, missing currency)", ["orgId"], async () => {
    const a = await expectRejected(() => api.ingestionPreview({ file: mkFile("x", "x.csv"), purpose: "NOPE", options: {} }), [400]);
    const b = await expectRejected(() => api.ingestionPreview({ file: mkFile("Code,Name,Type\n1,A,Bank\n", "c.csv"), purpose: "CHART_OF_ACCOUNTS", options: {} }), [400]);
    return `HTTP ${a.status} and ${b.status}`;
  });

  await step("Import", "An invoice is read, stored as unverified evidence, and nothing is posted", ["orgId"], async () => {
    const inv = `Kadena Supplies Ltd\nInvoice No: ST-${tag}\nInvoice Date: ${year}-01-15\nSubtotal NGN 1000.00\nVAT NGN 75.00\nTotal NGN 1075.00\n`;
    const p = await api.ingestionPreview({ file: mkFile(inv, "selftest-invoice.txt"), purpose: "DOCUMENT", options: {} });
    const f = p.document.fields;
    check(p.document.type === "INVOICE" && f.total && f.total.value === "1075.00" && f.document_number && f.document_number.value === `ST-${tag}`, `fields read wrongly: ${JSON.stringify(p.document)}`);
    check(p.proposal && p.proposal.applied === false, "the proposal claims to be applied");
    const r = await api.ingestionCommit({ file: mkFile(inv, "selftest-invoice.txt"), purpose: "DOCUMENT", options: {}, fingerprint: p.fingerprint, acknowledge: true });
    const ev = await api.getEvidence(r.result.evidence_id);
    check(ev.type === "INVOICE" && ev.status === "UPLOADED", `evidence is ${ev.type}/${ev.status}`);
    check((await api.listJournals()).length === ctx.impJournalsBefore, "importing changed the number of journals");
    return `INVOICE evidence ${ev.status}; journals unchanged`;
  });

  // ---------------- 10f. Advanced security & infrastructure ----------------
  // These never switch anything on or off. Where a feature is simply not configured on the server (no encryption keys,
  // no file storage) the step reports a WARNING that says so, never a pass.
  const notConfigured = (what) => Object.assign(new Error(`${what} is not switched on on the server yet (needs ASAVEXA_KEYS). Nothing is wrong, but it is not protecting you yet.`), { warn: true });

  await step("Security", "The security overview tells the truth about what is switched on", ["orgId"], async () => {
    const o = await api.securityOverview();
    check(o.encryption && o.audit_chain && o.mfa && o.storage && o.retention, "the overview is missing sections");
    if (!o.encryption.configured) throw notConfigured("Encryption");
    return `keys: ${o.encryption.keys.join(",")}; storage: ${o.storage.enabled ? o.storage.backend : "off"}; two-step: ${o.mfa.with_mfa}/${o.mfa.members}`;
  });

  await step("Security", "Your device list never exposes secrets", ["orgId"], async () => {
    const me = await api.mySecurity();
    check(Array.isArray(me.sessions) && me.sessions.some((x) => x.current), "this session is not listed as the current device");
    const text = JSON.stringify(me);
    check(!/token_hash|password|secret/i.test(text), "the device list contains something secret");
    return `${me.sessions.length} session(s); signs out after ${me.idle_minutes} idle minutes`;
  });

  await step("Security", "A wrong two-step code is refused and does not switch it on", ["orgId"], async () => {
    const me = await api.mySecurity();
    if (!me.mfa_available) throw notConfigured("Two-step sign-in");
    if (me.mfa.enabled) {
      const e = await expectRejected(() => api.mfaDisable("000000"), [400, 401, 403, 429]);
      return `already on; wrong code refused: HTTP ${e.status}`;
    }
    const begun = await api.mfaBegin();
    check(begun.secret && begun.secret.length >= 16 && /^otpauth:\/\//.test(begun.otpauth_uri), "no setup key returned");
    const e = await expectRejected(() => api.mfaConfirm("000000"), [400, 401, 403, 429]);
    const after = await api.mySecurity();
    check(!after.mfa.enabled, "a wrong code switched two-step sign-in on");
    return `HTTP ${e.status}; still off`;
  });

  await step("Security", "The audit trail's tamper-evident chain checks out", ["orgId"], async () => {
    const r = await api.verifyAuditChain();
    if (r.enabled === false) throw notConfigured("The tamper-evident audit chain");
    check(r.ok === true, `the chain reports ${r.problem_count} problem(s): ${JSON.stringify((r.problems || []).slice(0, 3))}`);
    if (!r.links) throw Object.assign(new Error("The chain is switched on but holds no events yet, so there is nothing to verify."), { warn: true });
    return `${r.links} events chained, intact${r.unchained_events ? `; ${r.unchained_events} older events pre-date the chain` : ""}`;
  });

  await step("Security", "The evidence file is stored encrypted and downloads back byte-for-byte", ["evidence"], async () => {
    const info = await api.evidenceStorage(ctx.evidence.id);
    if (!info.stored) throw Object.assign(new Error("File storage is off, so only the record and fingerprint are kept (set ASAVEXA_KEYS to store the file encrypted)."), { warn: true });
    check(info.info && info.info.state === "STORED", `storage state ${info.info && info.info.state}`);
    check(!JSON.stringify(info).match(/wrapped_dek|nonce/), "storage info exposes key material");
    const { blob } = await api.downloadEvidence(ctx.evidence.id);
    const buf = await blob.arrayBuffer();
    const digest = await globalThis.crypto.subtle.digest("SHA-256", buf);
    const hex = Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
    check(hex === ctx.evidence.file_hash, "the downloaded file does not match the evidence fingerprint");
    return `${buf.byteLength} bytes, fingerprint matches (${info.info.backend || "storage"})`;
  });

  await step("Security", "Keeping evidence for less than the legal minimum is refused", ["orgId"], async () => {
    const e = await expectRejected(() => api.setRetention(100), [400]);
    return `HTTP ${e.status}: ${e.message}`;
  });

  await step("Security", "Disposing of evidence before its retention date is refused", ["evidence"], async () => {
    const e = await expectRejected(() => api.disposeEvidence(ctx.evidence.id, "SelfTest early disposal"), [409]);
    return `HTTP ${e.status}`;
  });

  await step("Security", "A legal hold can be placed and released", ["evidence"], async () => {
    const hold = await api.placeHold(`SelfTest ${tag}`, ctx.evidence.id);
    check(hold.id && !hold.released_at, "hold was not placed");
    const r = await api.getRetention();
    check(r.holds.some((x) => x.id === hold.id && !x.released_at), "the hold is not listed");
    const rel = await api.releaseHold(hold.id);
    check(rel.released_at, "the hold was not released");
    return "placed, listed, released (a 'hold released' alert may now appear — that is expected)";
  });

  await step("Security", "Unknown data-location codes are refused", ["orgId"], async () => {
    const e = await expectRejected(() => api.updateSecuritySettings({ allowed_regions: ["ATLANTIS"] }), [400]);
    return `HTTP ${e.status}`;
  });

  await step("Security", "Vendor risk is worked out from facts, not typed in", ["orgId"], async () => {
    const v = await api.addVendor({ name: `SelfTest vendor ${tag}`, purpose: "self-test", data_categories: ["FINANCIAL"] });
    check(v.risk_tier && v.risk_tier !== "LOW", `a vendor with financial data, no agreement and no exit plan was rated ${v.risk_tier}`);
    check(Array.isArray(v.risk_reasons) && v.risk_reasons.length > 0, "no reasons given for the rating");
    return `${v.risk_tier} (${v.risk_reasons.length} reasons)`;
  });

  await step("Security", "Your data export contains no secrets", ["orgId"], async () => {
    const d = await api.exportMyData();
    const text = JSON.stringify(d);
    check(!/password_hash|token_hash|pbkdf2|wrapped_dek/i.test(text), "the export contains secret material");
    check(d.account && d.account.email, "the export has no account section");
    return `${(d.audit_events_about_you || []).length} audit events listed`;
  });

  await step("Security", "Detailed system health reports OK or says what is degraded", ["orgId"], async () => {
    const h = await api.securityHealth();
    check(["OK", "DEGRADED"].includes(h.status), `status ${h.status}`);
    if (h.status === "DEGRADED") throw Object.assign(new Error(`degraded: ${h.checks.filter((c) => !c.ok).map((c) => `${c.name}: ${c.detail}`).join("; ")}`), { warn: true });
    return h.checks.map((c) => c.name).join(", ");
  });

  // ---------------- 10g. Professional validation ----------------
  // Records only. These steps prove the RULES (competence, independence, source reference, signing, immutability, statement integrity);
  // they cannot and do not prove that any professional's conclusion is right. The reviewers they add are removed from the panel afterwards.
  const asOf = new Date().toISOString().slice(0, 10);
  const goodReview = (reviewerId, over = {}) => ({ stage: "CONTROLS", reviewer_id: reviewerId, conclusion: "CONCURS", scope_reviewed: "Self-test walkthrough", basis: "Self-test", competence_confirmed: true,
    source_reference: `selftest-${tag}`, observations: [], ...over });
  const allTrue = { no_financial_interest: true, not_involved_in_preparing_records: true, no_close_personal_relationship: true, no_other_threat_to_objectivity: true };

  await step("Professional Validation", "The seven review stages are set out in the required order, with the disclaimer", ["orgId"], async () => {
    const g = await api.validationGuide();
    const want = ["ACCOUNTING_TREATMENT", "CONTROLS", "EVIDENCE", "REPORTING", "AUDIT_WORKFLOW", "SECURITY", "PROFESSIONAL_JUDGEMENT"];
    check(JSON.stringify(g.stages.map((x) => x.id)) === JSON.stringify(want), `stages are ${g.stages.map((x) => x.id).join(" → ")}`);
    check(/not an audit opinion/i.test(g.disclaimer), "the disclaimer does not say this is not an audit opinion");
    return "Accounting treatment → Controls → Evidence → Reporting → Audit workflow → Security → Professional judgement";
  });

  await step("Professional Validation", "A credential is recorded as declared and never verified automatically", ["orgId"], async () => {
    const r = await api.addReviewer({ name: `SelfTest Auditor ${tag}`, email: `selftest-auditor-${tag}@example.com`, specialisms: ["AUDIT"], affiliation: "SelfTest LLP",
      credentials: [{ body: "ICAN", membership_no: `ST-${tag}`, jurisdiction: "Nigeria" }] });
    ctx.valReviewer = r;
    check(r.credentials[0].status === "DECLARED", `credential status is ${r.credentials[0].status}`);
    check(r.credential_state === "DECLARED_ONLY", `credential state is ${r.credential_state}`);
    const e = await expectRejected(() => api.addReviewer({ name: "X", email: "x@example.com", specialisms: ["AUDIT"], credentials: [] }), [400]);
    return `declared only; a reviewer with no credentials is refused (HTTP ${e.status})`;
  });

  await step("Professional Validation", "A reviewer who is not competent for a stage cannot be assigned to it", ["valReviewer"], async () => {
    const tax = await api.addReviewer({ name: `SelfTest Tax ${tag}`, email: `selftest-tax-${tag}@example.com`, specialisms: ["TAX"], credentials: [{ body: "ACCA", membership_no: `TX-${tag}` }] });
    try {
      const e = await api.createEngagement({ title: `SelfTest competence ${tag}`, as_of: asOf, stages: ["CONTROLS"] });
      const err = await expectRejected(() => api.assignReviewer(e.id, "CONTROLS", tax.id), [400]);
      await api.withdrawEngagement(e.id, "self-test: competence check only");
      return `refused (HTTP ${err.status})`;
    } finally {
      await api.setReviewerActive(tax.id, false);
    }
  });

  await step("Professional Validation", "A review counts only with independence, a source reference and a signature; a signed review cannot be signed again", ["valReviewer"], async () => {
    const r = ctx.valReviewer;
    const e = await api.createEngagement({ title: `SelfTest review ${tag}`, as_of: asOf, stages: ["CONTROLS"] });
    check(e.snapshot && e.snapshot.evidence && e.snapshot.ledger && e.snapshot.security, "the snapshot is missing sections");
    await api.openEngagement(e.id);
    await api.assignReviewer(e.id, "CONTROLS", r.id);
    const noDecl = await expectRejected(() => api.saveReview(e.id, goodReview(r.id)), [409]);
    const noRef = await expectRejected(() => api.declareIndependence(e.id, { reviewer_id: r.id, independent: true, confirmations: allTrue }), [400]);
    await api.declareIndependence(e.id, { reviewer_id: r.id, independent: true, confirmations: allTrue, source_reference: `selftest-decl-${tag}` });
    const noRefReview = await expectRejected(() => api.saveReview(e.id, goodReview(r.id, { source_reference: null })), [400]);
    let d = await api.saveReview(e.id, goodReview(r.id, { competence_confirmed: false }));
    const draft = d.reviews.find((x) => x.status === "DRAFT");
    const noCompetence = await expectRejected(() => api.signReview(e.id, draft.id), [400]);
    d = await api.saveReview(e.id, goodReview(r.id));
    d = await api.signReview(e.id, d.reviews.find((x) => x.status === "DRAFT").id);
    const signed = d.reviews.find((x) => x.status === "SIGNED");
    check(signed && signed.hash && signed.hash.length === 64, "the signed review has no content fingerprint");
    const again = await expectRejected(() => api.signReview(e.id, signed.id), [409]);
    check(d.coverage.complete && d.coverage.outcome === "VALIDATED", `outcome is ${d.coverage.outcome}`);
    d = await api.completeEngagement(e.id);
    const st = await api.validationStatement(e.id);
    check(st.verification && st.verification.ok, "the statement does not verify");
    check(st.credential_verification === "SOME_UNVERIFIED", `credential verification is ${st.credential_verification}`);
    check(/not an audit opinion/i.test(st.disclaimer), "the statement has no disclaimer");
    await api.setReviewerActive(r.id, false);
    return `refused without declaration (${noDecl.status}), source reference (${noRef.status}/${noRefReview.status}), competence (${noCompetence.status}); re-sign (${again.status}); statement fingerprint ${st.statement_hash.slice(0, 12)} verified`;
  });

  // ---------------- 10h. Real pilot ----------------
  // Proves the RULES of the pilot (consent, who may be added, honest results, privacy). It creates one clearly-named planning pilot with a very old
  // start date so it sorts last, and removes its throw-away client again. It does not prove the pilot's results mean anything: only real use does.
  const pilotWarn = (m) => Object.assign(new Error(m), { warn: true });
  await step("Real Pilot", "The eleven measures and the honest limits are set out", ["orgId"], async () => {
    const g = await api.pilotGuide();
    check(Object.keys(g.default_targets).length === 11, `${Object.keys(g.default_targets).length} default targets, not 11`);
    check(g.max_clients === 12, `the client cap is ${g.max_clients}`);
    check(/cannot prove/i.test(g.honesty) && /reported/i.test(g.honesty), "the honesty note does not say what a pilot cannot prove and what is only reported");
    return "11 measures; a pilot is small and says what it cannot prove";
  });

  await step("Real Pilot", "A client needs your own administrator rights, written consent and a free slot", ["orgId"], async () => {
    const me = await api.pilotMe();
    if (!me.can_manage) throw pilotWarn("Your role cannot set up a pilot (owners and administrators can), so this was not tested.");
    const p = await api.createPilot({ name: `SelfTest pilot ${tag} (safe to ignore)`, start_date: "2000-01-01", notes: "Created by the self-test" });
    ctx.pilotId = p.id;
    check(p.status === "PLANNING", `new pilot is ${p.status}`);
    const stranger = await expectRejected(() => api.addPilotClient(p.id, { client_org_id: "00000000-0000-4000-8000-0000000000ff", label: "Not mine", consent_reference: "selftest letter" }), [403]);
    const orgB = await api.createOrganisation(`SelfTest pilot client ${tag}`);
    ctx.pilotClient = orgB.id;
    const noConsent = await expectRejected(() => api.addPilotClient(p.id, { client_org_id: orgB.id, label: "Throw-away", consent_reference: " " }), [400]);
    const future = await expectRejected(() => api.addPilotClient(p.id, { client_org_id: orgB.id, label: "Throw-away", consent_reference: "selftest letter", kickoff: "2999-01-01" }), [400]);
    const self = await expectRejected(() => api.addPilotClient(p.id, { client_org_id: ctx.orgId, label: "Myself", consent_reference: "selftest letter" }), [400, 403]);
    const added = await api.addPilotClient(p.id, { client_org_id: orgB.id, label: "Throw-away", consent_reference: "selftest letter" });
    check(added.clients.length === 1 && added.clients[0].consent_reference === "selftest letter", "the consent reference was not kept");
    const dup = await expectRejected(() => api.addPilotClient(p.id, { client_org_id: orgB.id, label: "Twice", consent_reference: "selftest letter" }), [409]);
    const early = await expectRejected(() => api.takePilotSnapshot(p.id), [409]);
    return `refused: an organisation you do not administer (${stranger.status}), no consent (${noConsent.status}), future start (${future.status}), the firm itself (${self.status}), adding twice (${dup.status}), a snapshot before the pilot starts (${early.status})`;
  });

  await step("Real Pilot", "Results never invent a number, and what people only reported is labelled", ["pilotId", "pilotClient"], async () => {
    const id = ctx.pilotId, day = new Date().toISOString().slice(0, 10);
    const badTime = await expectRejected(() => api.logPilotTime(id, { client_org_id: ctx.pilotClient, kind: "REPORT", minutes: 10, performed_on: "2999-01-01" }), [400]);
    const noClient = await expectRejected(() => api.logPilotTime(id, { kind: "REPORT", minutes: 10, performed_on: day }), [400, 403]);
    await api.logPilotTime(id, { client_org_id: ctx.pilotClient, kind: "REPORT", minutes: 30, performed_on: day, baseline_minutes: 60 });
    const badSurvey = await expectRejected(() => api.submitPilotSurvey(id, { round: "SELFTEST", scores: { overall: 9, ease: 3, trust: 3, recommend: 5 } }), [400]);
    await api.submitPilotSurvey(id, { round: "SELFTEST", scores: { overall: 4, ease: 3, trust: 4, recommend: 8 } });
    const second = await api.submitPilotSurvey(id, { round: "SELFTEST", scores: { overall: 5, ease: 3, trust: 4, recommend: 9 } });
    check(second.revision === 2, `a second answer to the same round is revision ${second.revision}, not 2`);
    const r = await api.pilotResults(id);
    check(r.evaluation.measures.length === 11, `${r.evaluation.measures.length} measures, not 11`);
    check(r.evaluation.measures.every((m) => m.source === "MEASURED" || m.source === "REPORTED"), "a measure is not labelled measured or reported");
    const sat = r.evaluation.measures.find((m) => m.key === "satisfaction");
    check(sat && sat.source === "REPORTED", "satisfaction is not labelled as reported");
    check(sat.status === "INSUFFICIENT_DATA" && sat.value == null, `one respondent produced a satisfaction figure (${sat.value}, ${sat.status})`);
    check(/indicative/i.test(r.evaluation.caution), "the results carry no caution about the small sample");
    const gone = await api.removePilotClient(id, ctx.pilotClient, "self-test finished");
    check(gone.clients.every((c) => !c.active), "the throw-away client is still active");
    const after = await api.pilotResults(id);
    check(after.clients_total === 0 && after.clients.length === 0, "a removed client still counts in the results");
    check(after.reported.survey.respondents === 0 && after.reported.time.report.entries === 0, "a removed client's reported data still counts");
    return `refused: future date (${badTime.status}), no client named (${noClient.status}), a score of 9 out of 5 (${badSurvey.status}); one respondent gives no satisfaction figure; removed client leaves every result`;
  });

  // ---------------- 10i. ASAVEXA Network ----------------
  // Uses two throw-away organisations (one business, one auditor) so your real organisation's profile and data are never touched, then returns
  // the session to your organisation. Proves the RULES: both sides agree, the business decides, access is checked every time, ending is immediate.
  const netOrgs = async () => {
    if (ctx.netP) return;
    const p = await api.createOrganisation(`SelfTest network business ${tag}`), v = await api.createOrganisation(`SelfTest network auditor ${tag}`);
    ctx.netP = p.id; ctx.netV = v.id;
  };
  const as = async (orgId) => { await api.selectOrganisation(orgId); };

  await step("ASAVEXA Network", "Seven kinds of organisation, and the rules of connecting, are set out", ["orgId"], async () => {
    const g = await api.networkGuide();
    check(Object.keys(g.types).length === 7, `${Object.keys(g.types).length} kinds, not 7`);
    for (const t of ["BUSINESS", "ACCOUNTANT", "AUDITOR", "BANK", "INVESTOR", "DONOR", "REGULATOR"]) check(t in g.types, `${t} is missing`);
    check(/business always decides|business decides/i.test(g.how_it_works.join(" ")), "the guide does not say the business decides");
    return "Businesses, accountants, auditors, banks, investors, donors, regulators";
  });

  await step("ASAVEXA Network", "A connection needs both sides to agree, and only a business shares its information", ["orgId"], async () => {
    try {
      await netOrgs();
      await as(ctx.netP);
      await api.setNetworkProfile({ org_type: "BUSINESS", display_name: `SelfTest Bakery ${tag}` });
      const two = await expectRejected(() => api.createNetworkInvite({ counterparty_type: "BUSINESS", purpose: "Peer share", grant: { scopes: ["IDENTITY"] } }), [400]);
      const inv = await api.createNetworkInvite({ counterparty_type: "AUDITOR", purpose: "SelfTest audit", grant: { scopes: ["IDENTITY", "FINANCIAL_HISTORY", "EVIDENCE_QUALITY"] }, connection_days: 30 });
      check(/^ASX-/.test(inv.code), "the invitation code has no recognisable form");
      const own = await expectRejected(() => api.acceptNetworkInvite({ code: inv.code }), [400]);
      await as(ctx.netV);
      await api.setNetworkProfile({ org_type: "AUDITOR", display_name: `SelfTest Audit LLP ${tag}` });
      const wrong = await expectRejected(() => api.previewNetworkInvite("ASX-ZZZZZ-ZZZZZ"), [400]);
      const pv = await api.previewNetworkInvite(inv.code);
      check(pv.kind === "OFFER" && pv.you_decide === false, "an offer should be accepted as offered");
      const c = await api.acceptNetworkInvite({ code: inv.code });
      ctx.netConn = c.id;
      check(c.status === "ACTIVE" && c.role === "VIEWER", `connection is ${c.status}/${c.role}`);
      const again = await expectRejected(() => api.acceptNetworkInvite({ code: inv.code }), [400]);
      return `refused: business to business (${two.status}), accepting your own invitation (${own.status}), a wrong code (${wrong.status}), reusing a code (${again.status}); connected only after the other side agreed`;
    } finally {
      await as(ctx.orgId);
    }
  });

  await step("ASAVEXA Network", "A connected organisation sees only what the business granted, and ending it cuts access at once", ["netConn"], async () => {
    try {
      await as(ctx.netV);
      const v = await api.networkPassport(ctx.netConn);
      const keys = Object.keys(v.sections).sort().join(",");
      check(keys === "evidence_quality,financial_history,identity", `the auditor received sections: ${keys}`);
      check(v.share.include_detail === false, "line-level detail was included without being granted");
      check(typeof v.fingerprint === "string" && v.fingerprint.length === 64, "the view has no fingerprint");
      const widen = await expectRejected(() => api.updateNetworkConnection(ctx.netConn, { grant: { scopes: ["IDENTITY", "AUDIT_TRAIL"] } }), [403]);
      await as(ctx.netP);
      await api.updateNetworkConnection(ctx.netConn, { grant: { scopes: ["IDENTITY"] } });
      await as(ctx.netV);
      const narrow = await api.networkPassport(ctx.netConn);
      check(Object.keys(narrow.sections).join(",") === "identity", `after the business narrowed it, the auditor still received ${Object.keys(narrow.sections).join(",")}`);
      await as(ctx.netP);
      const fromProvider = await expectRejected(() => api.networkPassport(ctx.netConn), [403]);
      await api.endNetworkConnection(ctx.netConn, "self-test finished");
      await as(ctx.netV);
      const closed = await expectRejected(() => api.networkPassport(ctx.netConn), [403]);
      return `the auditor cannot widen its own access (${widen.status}); narrowing took effect at once; the business cannot use the viewer route (${fromProvider.status}); after ending, access is refused (${closed.status})`;
    } finally {
      await as(ctx.orgId);
    }
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
      const pb = await api.getPassport();
      check(pb.evidence_quality.transactions.total_posted === 0 && dec(pb.financial_history.totals.revenue) === 0 && !JSON.stringify(pb).includes(ctx.journal.id),
        "organisation B's passport contains organisation A's data");
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
