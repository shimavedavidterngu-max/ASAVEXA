import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { Pubfin } from "../src/pages/Pubfin.js";
import * as P from "../src/lib/pubfin.js";
import { ApiClient } from "../src/api/client.js";
import { can, PERMISSIONS } from "../src/lib/permissions.js";

const text = (v) => JSON.stringify(v);
function find(v, pred, out = []) { if (!v || typeof v !== "object") return out; if (pred(v)) out.push(v); for (const c of v.children || []) find(c, pred, out); return out; }
const byId = (v, id) => find(v, (n) => n.props && n.props.id === id)[0];
const noop = new Proxy({}, { get: () => () => {} });
const ACCTS = [{ id: "a1", code: "5100", name: "Rent", type: "EXPENSE" }, { id: "a2", code: "5000", name: "Cost of sales", type: "EXPENSE" }, { id: "a3", code: "4000", name: "Sales", type: "REVENUE" }];
const POLICY = { min_quotes: 3, quote_threshold: "0.00", meaning: "A procurement estimated at 0.00 or more needs at least 3 quotes." };
const OPTIONS = { accounts: ACCTS, policy: POLICY, limitations: ["ACTUAL figures come only from posted journals."] };
const OV = { as_of: "2026-02-15", policy: POLICY, counts: { budgets: 1, budgets_approved: 1, budgets_waiting: 0, commitments_open: 1, procurements_open: 0, awards_waiting: 0, grants_active: 1, spend_waiting: 0, virements_waiting: 0 },
  overspent_lines: [{ budget_ref: "B-001", code: "5100", name: "Rent", available: "-400.00" }], grants_expired: [], grants_overspent_vs_received: [{ ref: "G-001", title: "Water", spent: "200.00", received: "100.00" }], limitations: ["ACTUAL figures come only from posted journals."] };
const LINES = [{ account_id: "a1", code: "5100", name: "Rent", type: "EXPENSE", amount: "5000.00" }, { account_id: "a3", code: "4000", name: "Sales", type: "REVENUE", amount: "40000.00" }];
const EXEC = { basis: "ACTUAL = posted journals", journals_examined: 8, rows: [
  { account_id: "a1", code: "5100", name: "Rent", type: "EXPENSE", approved: "5000.00", adjustment: "500.00", budget: "5500.00", actual: "5600.00", committed: "100.00", available: "-200.00", used_pct: "101.82", overspent: true },
  { account_id: "a3", code: "4000", name: "Sales", type: "REVENUE", approved: "40000.00", adjustment: "0.00", budget: "40000.00", actual: "35000.00", committed: null, available: null, used_pct: "87.50", overspent: false }],
  expense_totals: { budget: "5500.00", actual: "5600.00", committed: "100.00", available: "-200.00" } };
const BUDGET = { id: "b1", ref: "B-001", name: "Operations", description: "", start: "2026-01-01", end: "2026-02-28", currency: "USD", status: "APPROVED", lines: LINES, created_by: "u1", submitted_by: "u1", decided_by: "u2", decision_note: "", fingerprint: "a".repeat(64),
  virements: [], history: [{ at: "2026-02-01T00:00:00", by: "u1", event: "CREATED", note: "" }], total_expense: "5000.00", total_revenue: "40000.00", execution: EXEC };
const COMMIT = { id: "c1", ref: "C-001", budget_id: "b1", budget_ref: "B-001", code: "5100", vendor: "Landlord", description: "Rent", amount: "100.00", status: "OPEN", settled_amount: null };
const PROC = { id: "p1", ref: "P-001", title: "Office space", description: "", budget_ref: "B-001", code: "5100", estimate: "400.00", status: "OPEN", quotes: [{ id: "q1", vendor: "V0", amount: "300.00", note: "" }, { id: "q2", vendor: "V1", amount: "350.00", note: "" }], award: null, history: [] };
const GRANT = { id: "g1", ref: "G-001", title: "Water", donor: "Fund", amount: "1000.00", currency: "USD", start: "2026-01-01", end: "2026-12-31", restricted: true, conditions: "Report quarterly", status: "ACTIVE", receipts: [{ date: "2026-01-05", amount: "100.00", reference: "BANK-1", by: "u1" }],
  spend: [{ id: "s1", date: "2026-02-01", description: "Pump", amount: "200.00", status: "PROPOSED", proposed_by: "u1", evidence: [] }], spent: "0.00", pending: "200.00", received: "100.00", remaining: "1000.00", utilisation_pct: "0.00", cash_on_hand: "100.00", overspent_vs_received: false, expired: false, history: [] };
const REPORT = { id: "r1", ref: "R-001", title: "H1", budget_ref: "B-001", status: "SUBMITTED", version: 1, submitted_by: "u1", decided_by: null, decision_note: "", fingerprint: "b".repeat(64), history: [],
  snapshot: { execution: { ...EXEC, ref: "B-001" }, commitments: [COMMIT], grants: [], virements: [] } };
const base = (o = {}) => ({ options: OPTIONS, ov: OV, budgets: [BUDGET], commitments: [COMMIT], procs: [PROC], grants: [GRANT], reports: [REPORT], vault: [], tab: "overview", budget: null, budgetForm: null, virementForm: null, commitForm: null,
  settleForm: null, cancelCommitId: null, procForm: null, proc: null, quoteForm: null, awardForm: null, grant: null, grantForm: null, receiptForm: null, spendForm: null, reportForm: null, report: null, notes: {},
  policyForm: { min_quotes: "3", quote_threshold: "0.00" }, busy: false, error: null, notice: null, ...o });
const page = (pf, role = "FINANCE_OFFICER", userId = "u2") => Pubfin({ pf, role, userId, loading: false, onRetry() {}, actions: noop });

describe("permissions", () => {
  test("who prepares and who approves", () => {
    for (const r of ["OWNER", "ACCOUNTANT", "FINANCE_OFFICER"]) assert.equal(can(r, PERMISSIONS.PUBFIN_PREPARE), true, r);
    for (const r of ["OWNER", "FINANCE_OFFICER", "APPROVER", "MANAGER"]) assert.equal(can(r, PERMISSIONS.PUBFIN_APPROVE), true, r);
    for (const r of ["READ_ONLY", "AUDITOR", "REVIEWER", "EXTERNAL_AUDITOR", "APPROVER", "MANAGER", "ADMINISTRATOR"]) assert.equal(can(r, PERMISSIONS.PUBFIN_PREPARE), false, r);
    for (const r of ["READ_ONLY", "AUDITOR", "ACCOUNTANT", "ADMINISTRATOR"]) assert.equal(can(r, PERMISSIONS.PUBFIN_APPROVE), false, r);
  });
});

describe("helpers", () => {
  test("money format and validation", () => {
    assert.equal(P.money("1234567.5"), "1,234,567.5"); assert.equal(P.money("-400.00"), "-400.00"); assert.equal(P.money(null), "—");
    for (const ok of ["0", "10", "10.5", "10.55"]) assert.equal(P.isMoney(ok), true, ok);
    for (const bad of ["", "-1", "1,000", "10.555", "abc", "1e5", " "]) assert.equal(P.isMoney(bad), false, bad);
    assert.equal(P.isPositive("0"), false); assert.equal(P.isPositive("0.01"), true);
  });
  test("budget validation and body", () => {
    const f = (o) => ({ ...P.emptyBudget(), name: "Operations", start: "2026-01-01", end: "2026-12-31", amounts: { a1: "5000" }, ...o });
    assert.equal(P.budgetProblem(f({})), null);
    assert.match(P.budgetProblem(f({ name: "ab" })), /name/); assert.match(P.budgetProblem(f({ start: "2026-02-30" })), /dates/); assert.match(P.budgetProblem(f({ end: "2025-12-31" })), /before/);
    assert.match(P.budgetProblem(f({ currency: "US" })), /currency/); assert.match(P.budgetProblem(f({ amounts: {} })), /at least one/); assert.match(P.budgetProblem(f({ amounts: { a1: "1,000" } })), /numbers/);
    const b = P.budgetBody(f({ currency: "usd", amounts: { a1: "5000", a2: "", a3: " 40000 " } }));
    assert.deepEqual(b.lines, [{ account_id: "a1", amount: "5000" }, { account_id: "a3", amount: "40000" }]); assert.equal(b.currency, "USD");
    assert.deepEqual(P.budgetForm(BUDGET).amounts, { a1: "5000.00", a3: "40000.00" });
  });
  test("budget moves: approver cannot decide own submission; only approved can close or move money", () => {
    const sub = { ...BUDGET, status: "SUBMITTED", submitted_by: "u1" };
    assert.equal(P.budgetMoves(sub, "APPROVER", "u1").decide, false); assert.equal(P.budgetMoves(sub, "APPROVER", "u1").ownSubmission, true);
    assert.equal(P.budgetMoves(sub, "APPROVER", "u2").decide, true); assert.equal(P.budgetMoves(sub, "ACCOUNTANT", "u2").decide, false);
    assert.equal(P.budgetMoves({ ...BUDGET, status: "DRAFT" }, "ACCOUNTANT", "u1").submit, true); assert.equal(P.budgetMoves(BUDGET, "ACCOUNTANT", "u1").edit, false);
    assert.equal(P.budgetMoves(BUDGET, "ACCOUNTANT", "u1").virement, true); assert.equal(P.budgetMoves(BUDGET, "READ_ONLY", "u1").close, false);
  });
  test("virement, commitment, settle validation", () => {
    assert.match(P.virementProblem({ from_account: "a1", to_account: "a1", amount: "5", reason: "x".repeat(12) }), /different/);
    assert.match(P.virementProblem({ from_account: "a1", to_account: "a2", amount: "0", reason: "x".repeat(12) }), /more than zero/);
    assert.match(P.virementProblem({ from_account: "a1", to_account: "a2", amount: "5", reason: "short" }), /why/);
    assert.equal(P.virementProblem({ from_account: "a1", to_account: "a2", amount: "5", reason: "x".repeat(12) }), null);
    const c = { ...P.emptyCommit("b1"), account_id: "a1", vendor: "Landlord", description: "Rent", amount: "100", date: "2026-02-10" };
    assert.equal(P.commitProblem(c), null); assert.match(P.commitProblem({ ...c, amount: "0" }), /more than zero/); assert.match(P.commitProblem({ ...c, date: "x" }), /date/); assert.match(P.commitProblem({ ...c, account_id: "" }), /line/);
    assert.match(P.settleProblem({ settled_amount: "x", note: "ok ok" }), /amount/); assert.match(P.settleProblem({ settled_amount: "5", note: "" }), /note/); assert.equal(P.settleProblem({ settled_amount: "0", note: "JE-1" }), null);
  });
  test("award validation mirrors the server policy", () => {
    const f = (o) => ({ quote_id: "q1", justification: "", exception_reason: "", ...o });
    assert.match(P.awardProblem(f({}), PROC, POLICY), /Policy needs 3 quotes and there are 2/);
    assert.equal(P.awardProblem(f({ exception_reason: "Only two suppliers exist in this district." }), PROC, POLICY), null);
    assert.match(P.awardProblem(f({ quote_id: "q2", exception_reason: "Only two suppliers exist in this district." }), PROC, POLICY), /not the lowest/);
    assert.equal(P.awardProblem(f({ quote_id: "q2", exception_reason: "Only two suppliers exist in this district.", justification: "Includes delivery and warranty cover." }), PROC, POLICY), null);
    assert.equal(P.awardProblem(f({}), PROC, { ...POLICY, quote_threshold: "1000" }), null);
    assert.match(P.awardProblem(f({ quote_id: "" }), PROC, POLICY), /Choose/);
    assert.match(P.policyProblem({ min_quotes: "0", quote_threshold: "1" }), /1 to 10/); assert.match(P.policyProblem({ min_quotes: "3", quote_threshold: "x" }), /threshold/); assert.equal(P.policyProblem({ min_quotes: "10", quote_threshold: "0" }), null);
  });
  test("grant and report validation and moves", () => {
    const g = { ...P.emptyGrant(), title: "Water", donor: "Fund", amount: "1000", start: "2026-01-01", end: "2026-12-31" };
    assert.equal(P.grantProblem(g), null); assert.match(P.grantProblem({ ...g, amount: "0" }), /more than zero/); assert.match(P.grantProblem({ ...g, end: "2025-01-01" }), /before/);
    assert.match(P.receiptProblem({ amount: "5", date: "2026-01-01", reference: "" }), /reference/); assert.match(P.spendProblem({ amount: "5", date: "bad", description: "Pump" }), /date/);
    assert.equal(P.spendMoves({ status: "PROPOSED", proposed_by: "u1" }, "APPROVER", "u1").decide, false); assert.equal(P.spendMoves({ status: "PROPOSED", proposed_by: "u1" }, "APPROVER", "u2").decide, true);
    assert.equal(P.reportMoves({ status: "SUBMITTED", submitted_by: "u1" }, "MANAGER", "u1").own, true); assert.equal(P.reportMoves({ status: "APPROVED" }, "READ_ONLY", "u1").exportable, true);
    assert.match(P.reportProblem({ budget_id: "", title: "H1 report" }), /budget/);
  });
});

describe("page", () => {
  test("overview shows counts, overspent lines, grant flags, policy and limits; approver can edit policy, preparer cannot", () => {
    const v = page(base());
    assert.match(text(byId(v, "pf-counts")), /1 approved budget/); assert.match(text(byId(v, "pf-overspent")), /-400\.00/); assert.match(text(v), /more than cash received/); assert.match(text(byId(v, "pf-policy")), /at least 3 quotes/);
    assert.ok(byId(v, "pol-save")); assert.equal(byId(page(base(), "ACCOUNTANT"), "pol-save"), undefined);
    assert.match(text(v), /posted journals/);
  });
  test("budget list and detail show ACTUAL, committed, available and flag overspending", () => {
    const l = page(base({ tab: "budgets" })); assert.match(text(byId(l, "pf-budget-table")), /B-001/); assert.ok(byId(l, "bud-new"));
    assert.equal(byId(page(base({ tab: "budgets" }), "READ_ONLY"), "bud-new"), undefined);
    const d = page(base({ tab: "budgets", budget: BUDGET }));
    assert.match(text(byId(d, "pf-exec")), /ACTUAL/); assert.match(text(byId(d, "pf-exec")), /OVER/); assert.match(text(byId(d, "pf-exec")), /5,600\.00/); assert.match(text(byId(d, "pf-exec-total")), /-200\.00/);
    assert.match(text(byId(d, "pf-exec")), /\+500\.00/);
    for (const id of ["vir-new", "bud-commit", "bc-save"]) assert.ok(byId(d, id), id);
  });
  test("draft budget shows lines without execution; submitted one shows decision box only to another approver", () => {
    const draft = { ...BUDGET, status: "DRAFT", execution: undefined };
    const d = page(base({ tab: "budgets", budget: draft }), "ACCOUNTANT", "u1"); assert.ok(byId(d, "pf-draft-lines")); assert.ok(byId(d, "bud-submit")); assert.ok(byId(d, "bud-edit")); assert.equal(byId(d, "pf-exec"), undefined);
    const sub = { ...draft, status: "SUBMITTED", submitted_by: "u1" };
    assert.ok(byId(page(base({ tab: "budgets", budget: sub }), "APPROVER", "u2"), "bud-decide"));
    const own = page(base({ tab: "budgets", budget: sub }), "APPROVER", "u1"); assert.equal(byId(own, "bud-decide"), undefined); assert.match(text(own), /different person must decide/);
  });
  test("budget form lists every expense and revenue account", () => {
    const v = page(base({ tab: "budgets", budgetForm: P.emptyBudget() }), "ACCOUNTANT");
    for (const a of ACCTS) assert.ok(byId(v, `bf-amt-${a.id}`), a.id);
  });
  test("virements: approver sees buttons for someone else's, a note for their own", () => {
    const b = { ...BUDGET, virements: [{ id: "v1", from_account: "a1", to_account: "a2", amount: "100.00", reason: "Rent rose", status: "PROPOSED", proposed_by: "u1" }] };
    assert.ok(byId(page(base({ tab: "budgets", budget: b }), "APPROVER", "u2"), "vir-ok-v1"));
    const own = page(base({ tab: "budgets", budget: b }), "APPROVER", "u1"); assert.equal(byId(own, "vir-ok-v1"), undefined); assert.match(text(own), /someone else decides/);
  });
  test("commitments: buttons only for preparers and open items; settle explains posting first", () => {
    const v = page(base({ tab: "commitments" }), "ACCOUNTANT"); assert.ok(byId(v, "com-settle-c1")); assert.ok(byId(v, "com-new"));
    assert.equal(byId(page(base({ tab: "commitments" }), "AUDITOR"), "com-settle-c1"), undefined);
    assert.equal(byId(page(base({ tab: "commitments", commitments: [{ ...COMMIT, status: "SETTLED", settled_amount: "90.00" }] }), "ACCOUNTANT"), "com-settle-c1"), undefined);
    assert.match(text(page(base({ tab: "commitments", settleForm: { id: "c1", settled_amount: "100.00", note: "" } }), "ACCOUNTANT")), /posted to the ledger/);
    assert.match(text(page(base({ tab: "commitments", commitForm: P.emptyCommit() }), "ACCOUNTANT")), /cannot be more than what is still available/);
  });
  test("procurement: quotes with lowest marked, award flow, policy text, approval by another person", () => {
    const d = page(base({ tab: "procurement", proc: PROC }), "ACCOUNTANT", "u1"); assert.match(text(byId(d, "pf-quotes")), /Lowest/); assert.ok(byId(d, "quote-new")); assert.ok(byId(d, "award-new")); assert.match(text(d), /at least 3 quotes/);
    const prop = { ...PROC, status: "AWARD_PROPOSED", award: { vendor: "V0", amount: "300.00", proposed_by: "u1", flags: ["NOT LOWEST QUOTE"], justification: "Better", exception_reason: "" } };
    const ap = page(base({ tab: "procurement", proc: prop }), "APPROVER", "u2"); assert.ok(byId(ap, "award-decide")); assert.match(text(byId(ap, "award-flags")), /NOT LOWEST/);
    const own = page(base({ tab: "procurement", proc: prop }), "FINANCE_OFFICER", "u1"); assert.equal(byId(own, "award-decide"), undefined); assert.match(text(own), /different person must decide/);
    assert.match(text(byId(page(base({ tab: "procurement", proc: { ...PROC, status: "AWARDED", commitment_ref: "C-001", award: { vendor: "V0", amount: "300.00", proposed_by: "u1", flags: [] } } }), "APPROVER", "u2"), "proc-commitment")), /C-001/);
  });
  test("grants: figures, spending approval by another person, expiry and cash warnings", () => {
    const d = page(base({ tab: "grants", grant: GRANT }), "APPROVER", "u2"); assert.match(text(byId(d, "grant-figures")), /remaining 1,000\.00/); assert.ok(byId(d, "sp-ok-s1"));
    const own = page(base({ tab: "grants", grant: GRANT }), "APPROVER", "u1"); assert.equal(byId(own, "sp-ok-s1"), undefined);
    const warn = page(base({ tab: "grants", grant: { ...GRANT, overspent_vs_received: true, expired: true } }), "ACCOUNTANT"); assert.match(text(warn), /more than the cash received/); assert.match(text(warn), /passed its end date/);
    assert.equal(byId(page(base({ tab: "grants", grant: GRANT }), "READ_ONLY"), "sp-new"), undefined); assert.ok(byId(page(base({ tab: "grants", grant: GRANT }), "ACCOUNTANT"), "sp-new"));
    assert.match(text(page(base({ tab: "grants", grant: GRANT, spendForm: { amount: "", date: "", description: "", reference: "", evidence_ids: [] } }), "ACCOUNTANT")), /only after a different person approves/);
  });
  test("reports: freeze note, approval box rules, export only when approved", () => {
    const sub = page(base({ tab: "reports", report: REPORT }), "MANAGER", "u2"); assert.ok(byId(sub, "rep-decide")); assert.equal(byId(sub, "rep-export"), undefined); assert.match(text(byId(sub, "rep-counts")), /1 commitment/);
    const own = page(base({ tab: "reports", report: REPORT }), "MANAGER", "u1"); assert.equal(byId(own, "rep-decide"), undefined);
    assert.ok(byId(page(base({ tab: "reports", report: { ...REPORT, status: "APPROVED", decided_by: "u2" } }), "READ_ONLY", "u3"), "rep-export"));
    assert.ok(byId(page(base({ tab: "reports", report: { ...REPORT, status: "DRAFT", snapshot: null } }), "ACCOUNTANT", "u1"), "rep-submit"));
    assert.match(text(page(base({ tab: "reports", report: { ...REPORT, status: "DRAFT", snapshot: null } }), "ACCOUNTANT", "u1")), /Nothing is frozen/);
  });
  test("empty states, error, notice, loading", () => {
    for (const [tab, re] of [["budgets", /No budgets/], ["commitments", /No commitments/], ["procurement", /No procurements/], ["grants", /No grants/], ["reports", /No reports/]])
      assert.match(text(page(base({ tab, budgets: [], commitments: [], procs: [], grants: [], reports: [] }))), re, tab);
    assert.match(text(page(base({ error: "boom" }))), /boom/); assert.match(text(page(base({ notice: "Saved." }))), /Saved\./);
    assert.match(text(Pubfin({ pf: base(), role: "OWNER", userId: "u1", loading: true, onRetry() {}, actions: noop })), /oading/);
    assert.match(text(page(base({ ov: null }))), /No data yet/);
  });
});

describe("client", () => {
  test("builds requests, encodes ids and downloads the report with the token", async () => {
    const calls = [];
    const api = new ApiClient({ baseUrl: "https://x.test", fetchImpl: async (url, init = {}) => { calls.push([init.method || "GET", url, init.body, init.headers && init.headers.Authorization]);
      return new Response(url.endsWith("/export") ? "a,b" : "{}", { status: 200, headers: { "Content-Type": url.endsWith("/export") ? "text/csv" : "application/json", "Content-Disposition": 'attachment; filename="R-001.csv"' } }); }, getToken: () => "tok" });
    await api.pubfinCommitments("b/1", "OPEN"); await api.approvePubfinVirement("b1", "v1", "ok"); await api.rejectPubfinSpend("g1", "s1", "no receipt"); await api.setPubfinPolicy({ min_quotes: 2, quote_threshold: "100" }); await api.discardPubfinBudget("b1");
    const out = await api.exportPubfinReport("r1");
    assert.match(calls[0][1], /\/pubfin\/commitments\?budget_id=b%2F1&status=OPEN/); assert.match(calls[1][1], /\/pubfin\/budgets\/b1\/virements\/v1\/approve$/); assert.match(calls[2][1], /\/pubfin\/grants\/g1\/spend\/s1\/reject$/);
    assert.equal(JSON.parse(calls[2][2]).note, "no receipt"); assert.equal(calls[3][0], "PUT"); assert.equal(calls[4][0], "DELETE"); assert.equal(calls[5][3], "Bearer tok"); assert.equal(out.filename, "R-001.csv");
  });
});
