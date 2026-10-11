import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { Bizdev } from "../src/pages/Bizdev.js";
import * as B from "../src/lib/bizdev.js";
import { ApiClient } from "../src/api/client.js";
import { can, PERMISSIONS, ROLE_PERMISSIONS } from "../src/lib/permissions.js";

const text = (v) => JSON.stringify(v);
function find(v, pred, out = []) { if (!v || typeof v !== "object") return out; if (pred(v)) out.push(v); for (const c of v.children || []) find(c, pred, out); return out; }
const byId = (v, id) => find(v, (n) => n.props && n.props.id === id)[0];
const noop = new Proxy({}, { get: () => () => {} });
const POLICY = { probabilities: { LEAD: 10, QUALIFIED: 25, PROPOSAL: 50, NEGOTIATION: 75, WIN_PENDING: 90 }, discount_limit_pct: "10.00", stale_days: 30, meaning: "A proposal with a discount above 10.00% needs a second person's approval." };
const STAGES = ["LEAD", "QUALIFIED", "PROPOSAL", "NEGOTIATION", "WIN_PENDING"].map((s, i) => ({ stage: s, count: i === 0 ? 1 : 0, value: i === 0 ? "1000.00" : "0.00", probability: [10, 25, 50, 75, 90][i], weighted: i === 0 ? "100.00" : "0.00" }));
const CUR = { currency: "NGN", open_count: 1, open_value: "1000.00", weighted: "100.00", stages: STAGES, won_count: 1, won_value: "5000.00", lost_count: 1, lost_value: "700.00", win_rate_pct: "50.00", win_rate_value_pct: "87.72", stale: 1, overdue: 0 };
const TARGET = { id: "t1", ref: "T-001", name: "Q1", start: "2026-01-01", end: "2026-03-31", currency: "NGN", amount: "10000.00", status: "ACTIVE", won: "5000.00", attainment_pct: "50.00", gap: "5000.00", weighted_expected: "100.00", forecast: "5100.00", forecast_pct: "51.00" };
const OV = { currencies: [CUR], targets: [TARGET], counts: { accounts: 1, opportunities: 3, open: 1, proposals_pending: 1, wins_pending: 0, reports: 1 }, policy: POLICY, limitations: ["Amounts in different currencies are never converted or added together."] };
const ITEM = { description: "Audit", quantity: "1.00", unit_price: "2000.00", total: "2000.00" };
const PROP = { id: "pp1", version: 1, status: "DRAFT", currency: "NGN", items: [ITEM], subtotal: "2000.00", discount_pct: "20.00", discount_amount: "400.00", total: "1600.00", valid_until: "2026-03-31", terms: "", evidence: [], submitted_by: null, decided_by: null, decision_note: "", limit_at_submission: null, history: [] };
const OPP = { id: "o1", ref: "O-001", account_id: "a1", account_name: "Meridian", title: "Audit retainer", description: "", currency: "NGN", value: "1000.00", stage: "LEAD", probability: 10, weighted: "100.00", expected_close: "2026-04-30", flags: [], proposals: [], activities: [], stage_history: [{ at: "2026-02-15T09:00:00", by: "u1", from: null, to: "LEAD", note: "created" }], history: [], lost_reason: "", won_date: null, win_requested_by: null };
const ACC = { id: "a1", ref: "A-001", name: "Meridian", kind: "PROSPECT", status: "ACTIVE", sector: "Textiles", country: "Nigeria", notes: "", contacts: [{ name: "Ada", role: "CFO", email: "ada@example.com", phone: "" }], open_opportunities: 1, won_opportunities: 0, history: [], opportunities: [OPP] };
const REPORT = { id: "r1", ref: "R-001", title: "Q1 pipeline", currency: "NGN", status: "SUBMITTED", version: 1, submitted_by: "u1", decided_by: null, decision_note: "", fingerprint: "c".repeat(64), history: [], confidentiality: "CONFIDENTIAL - x",
  snapshot: { generated_at: "2026-02-15T09:00:00", figures: CUR, opportunities: [OPP], targets: [TARGET], limitations: ["Probabilities are your own policy settings."] } };
const base = (o = {}) => ({ options: { accounts: [{ id: "a1", ref: "A-001", name: "Meridian" }], policy: POLICY }, ov: OV, accounts: [ACC], opps: [OPP], targets: [TARGET], reports: [REPORT], vault: [], tab: "overview", stageFilter: "", account: null, accountForm: null,
  opp: null, oppForm: null, moveTo: "", activityForm: null, proposalForm: null, targetForm: null, reportForm: null, report: null, notes: {}, policyForm: B.policyForm(POLICY), busy: false, error: null, notice: null, ...o });
const page = (bd, role = "OWNER", userId = "u1") => Bizdev({ bd, role, userId, loading: false, onRetry() {}, actions: noop });

describe("permissions", () => {
  test("mirror the backend matrix", () => {
    for (const r of ["OWNER", "FINANCE_OFFICER", "MANAGER"]) assert.ok(B.canPrepare(r) && B.canApprove(r), r);
    assert.ok(B.canPrepare("ACCOUNTANT") && !B.canApprove("ACCOUNTANT")); assert.ok(B.canApprove("APPROVER") && !B.canPrepare("APPROVER"));
    for (const r of ["REVIEWER", "AUDITOR", "ADMINISTRATOR", "READ_ONLY"]) assert.ok(!B.canPrepare(r) && !B.canApprove(r), r);
    assert.equal(PERMISSIONS.BD_PREPARE, "bd:prepare"); assert.ok(can("OWNER", PERMISSIONS.BD_APPROVE));
  });
});

describe("validators", () => {
  test("money, dates, notes", () => {
    assert.equal(B.money("1234567.5"), "1,234,567.5"); assert.equal(B.money(null), "—");
    assert.ok(B.isMoney("10.50") && !B.isMoney("1,000") && !B.isMoney("1.234") && !B.isMoney("")); assert.ok(B.isPositive("0.01") && !B.isPositive("0"));
    assert.ok(B.isRealDate("2026-02-28") && !B.isRealDate("2026-02-30") && !B.isRealDate("26-1-1"));
    assert.match(B.noteProblem("ab"), /at least 3/); assert.equal(B.noteProblem("abc"), null);
  });
  test("accounts", () => {
    const f = { ...B.emptyAccount(), name: "Meridian", contact_name: "Ada", contact_email: "ada@example.com" };
    assert.equal(B.accountProblem(f), null); assert.deepEqual(B.accountBody(f).contacts, [{ name: "Ada", role: "", email: "ada@example.com", phone: "" }]);
    assert.match(B.accountProblem({ ...f, name: "x" }), /name/); assert.match(B.accountProblem({ ...f, contact_email: "ada example" }), /email/);
    assert.match(B.accountProblem({ ...B.emptyAccount(), name: "Meridian", contact_phone: "123" }), /contact a name/);
    assert.deepEqual(B.accountBody({ ...B.emptyAccount(), name: "Meridian" }).contacts, []); assert.equal(B.accountForm(ACC).contact_email, "ada@example.com");
  });
  test("opportunities and activities", () => {
    const f = { ...B.emptyOpp("a1"), title: "Deal", value: "100", expected_close: "2026-06-30" };
    assert.equal(B.oppProblem(f, true), null); assert.equal(B.oppBody({ ...f, currency: "ngn" }, true).currency, "NGN"); assert.equal(B.oppBody(f, false).account_id, undefined);
    for (const bad of [{ account_id: "" }, { title: "ab" }, { currency: "N" }, { value: "0" }, { value: "1,000" }, { expected_close: "2026-02-30" }]) assert.ok(B.oppProblem({ ...f, ...bad }, true), JSON.stringify(bad));
    assert.equal(B.oppProblem({ ...f, account_id: "", currency: "" }, false), null);
    assert.equal(B.activityProblem({ type: "CALL", date: "", summary: "Intro call" }), null); assert.ok(B.activityProblem({ type: "TEXT", date: "", summary: "Intro call" })); assert.ok(B.activityProblem({ type: "CALL", date: "2026-13-01", summary: "x call" }));
    assert.equal(B.activityBody({ type: "CALL", date: "", summary: " Hi there " }).date, undefined);
  });
  test("proposals: validation, body and a cent-exact preview", () => {
    const f = { ...B.emptyProposal(), items: [{ description: "Service", quantity: "3", unit_price: "333.33" }], discount_pct: "12.5", valid_until: "2026-03-31" };
    assert.equal(B.proposalProblem(f), null); assert.deepEqual(B.proposalPreview(f), { subtotal: "999.99", discount: "125.00", total: "874.99" });
    assert.deepEqual(B.proposalPreview({ ...f, items: [{ description: "x1", quantity: "1.5", unit_price: "0.01" }], discount_pct: "0" }), { subtotal: "0.02", discount: "0.00", total: "0.02" });
    assert.equal(B.proposalPreview({ ...f, items: [{ description: "", quantity: "1", unit_price: "5" }] }), null); assert.equal(B.proposalPreview({ ...f, valid_until: "" }) !== null, true);
    for (const bad of [{ items: [] }, { items: [{ description: "x1", quantity: "0", unit_price: "5" }] }, { items: [{ description: "x1", quantity: "1", unit_price: "1,000" }] }, { discount_pct: "100" }, { discount_pct: "abc" }, { valid_until: "soon" }]) assert.ok(B.proposalProblem({ ...f, ...bad }), JSON.stringify(bad));
    assert.equal(B.proposalBody({ ...f, discount_pct: "" }).discount_pct, "0"); assert.equal(B.proposalForm(PROP).discount_pct, "20.00");
  });
  test("targets, policy, reports", () => {
    const t = { ...B.emptyTarget(), name: "Q1 goal", start: "2026-01-01", end: "2026-03-31", amount: "5000" };
    assert.equal(B.targetProblem(t), null); assert.equal(B.targetBody({ ...t, currency: "usd" }).currency, "USD");
    for (const bad of [{ name: "ab" }, { start: "x" }, { end: "2025-12-31" }, { currency: "US" }, { amount: "0" }]) assert.ok(B.targetProblem({ ...t, ...bad }), JSON.stringify(bad));
    const p = B.policyForm(POLICY); assert.equal(B.policyProblem(p), null); assert.deepEqual(B.policyBody(p).probabilities, POLICY.probabilities); assert.equal(B.policyBody(p).stale_days, 30);
    for (const bad of [{ discount_limit_pct: "101" }, { discount_limit_pct: "x" }, { stale_days: "0" }, { p_LEAD: "101" }, { p_LEAD: "60" }, { p_QUALIFIED: "x" }]) assert.ok(B.policyProblem({ ...p, ...bad }), JSON.stringify(bad));
    assert.equal(B.reportProblem({ currency: "NGN", title: "Q1 report" }), null); assert.ok(B.reportProblem({ currency: "", title: "Q1 report" })); assert.ok(B.reportProblem({ currency: "NGN", title: "x" }));
  });
});

describe("moves (who sees which buttons)", () => {
  test("opportunity", () => {
    const acc = { ...OPP, stage: "NEGOTIATION", proposals: [{ ...PROP, status: "ACCEPTED" }] };
    assert.ok(B.oppMoves(acc, "ACCOUNTANT", "u1").requestWin); assert.ok(!B.oppMoves(OPP, "ACCOUNTANT", "u1").requestWin); assert.ok(!B.oppMoves(acc, "APPROVER", "u1").requestWin);
    const wp = { ...OPP, stage: "WIN_PENDING", win_requested_by: "u1" };
    assert.ok(B.oppMoves(wp, "MANAGER", "u1").ownWin && !B.oppMoves(wp, "MANAGER", "u1").decideWin); assert.ok(B.oppMoves(wp, "MANAGER", "u2").decideWin && !B.oppMoves(wp, "MANAGER", "u2").ownWin);
    assert.ok(!B.oppMoves(wp, "ACCOUNTANT", "u2").decideWin); assert.ok(!B.oppMoves(wp, "ACCOUNTANT", "u2").edit && B.oppMoves(wp, "ACCOUNTANT", "u2").activity && B.oppMoves(wp, "ACCOUNTANT", "u2").lost);
    const won = B.oppMoves({ ...OPP, stage: "WON" }, "OWNER", "u1"); assert.ok(won.closed && !won.lost && !won.edit && !won.activity);
  });
  test("proposal", () => {
    const pend = { ...PROP, status: "PENDING_APPROVAL", submitted_by: "u1" };
    assert.ok(B.proposalMoves(pend, OPP, "FINANCE_OFFICER", "u2").decide); assert.ok(B.proposalMoves(pend, OPP, "FINANCE_OFFICER", "u1").own && !B.proposalMoves(pend, OPP, "FINANCE_OFFICER", "u1").decide);
    assert.ok(!B.proposalMoves(pend, OPP, "ACCOUNTANT", "u2").decide); assert.ok(B.proposalMoves({ ...PROP, status: "REJECTED" }, OPP, "ACCOUNTANT", "u1").edit);
    assert.ok(B.proposalMoves({ ...PROP, status: "APPROVED" }, OPP, "ACCOUNTANT", "u1").send); assert.ok(B.proposalMoves({ ...PROP, status: "SENT" }, OPP, "ACCOUNTANT", "u1").respond);
    const m = B.proposalMoves({ ...PROP, status: "DRAFT" }, { ...OPP, stage: "WIN_PENDING" }, "OWNER", "u1"); assert.ok(!m.edit && !m.submit);
  });
  test("report", () => {
    assert.ok(B.reportMoves(REPORT, "MANAGER", "u2").decide); assert.ok(B.reportMoves(REPORT, "MANAGER", "u1").own && !B.reportMoves(REPORT, "MANAGER", "u1").decide);
    assert.ok(B.reportMoves({ ...REPORT, status: "APPROVED" }, "READ_ONLY", "u3").exportable); assert.ok(B.reportMoves({ ...REPORT, status: "DRAFT" }, "ACCOUNTANT", "u1").submit);
  });
});

describe("page", () => {
  test("always shows the warning and tabs", () => {
    const p = page(base()); assert.match(text(p), /second person/); assert.match(text(p), /not a prediction/);
    for (const [id] of B.TABS) assert.ok(byId(p, `bd-tab-${id}`), id);
  });
  test("overview: currency cards, win rate, stages, targets, attention, policy", () => {
    const p = page(base({ opps: [{ ...OPP, flags: ["STALE"] }] }));
    assert.match(text(byId(p, "bd-counts")), /1 discount\(s\) waiting for approval/); assert.ok(byId(p, "bd-cur-NGN")); assert.match(text(byId(p, "bd-winrate-NGN")), /50\.00% of closed deals by number, 87\.72% by value/);
    assert.equal(find(p, (n) => n.props && n.props["data-stage"] && /^NGN-/.test(n.props["data-stage"])).length, 5); assert.equal(find(p, (n) => n.props && n.props["data-target"] === "t1").length, 1);
    assert.match(text(byId(p, "bd-attention")), /no activity for a long time/); assert.ok(byId(p, "pol-save")); assert.ok(byId(p, "pol-p-WIN_PENDING"));
    assert.equal(byId(page(base(), "ACCOUNTANT"), "pol-save"), undefined);
    assert.match(text(page(base({ ov: { ...OV, currencies: [CUR].map((c) => ({ ...c, win_rate_pct: null })) } }))), /not enough closed deals/);
    assert.match(text(page(base({ ov: { ...OV, currencies: [] } }))), /No opportunities yet/);
  });
  test("accounts: list, form, detail", () => {
    const p = page(base({ tab: "accounts" })); assert.ok(byId(p, "acc-new")); assert.ok(byId(p, "acc-open-a1")); assert.equal(byId(page(base({ tab: "accounts" }), "REVIEWER"), "acc-new"), undefined);
    const f = page(base({ tab: "accounts", accountForm: B.emptyAccount() })); for (const id of ["af-name", "af-kind", "af-cname", "af-cemail", "af-save"]) assert.ok(byId(f, id), id); assert.match(text(f), /personal data/);
    const d = page(base({ tab: "accounts", account: ACC })); assert.match(text(d), /Meridian/); assert.ok(byId(d, "acc-newopp")); assert.ok(byId(d, "acc-archive")); assert.ok(byId(d, "acc-opp-o1"));
    const arch = page(base({ tab: "accounts", account: { ...ACC, status: "ARCHIVED" } })); assert.equal(byId(arch, "acc-archive"), undefined); assert.equal(byId(arch, "acc-newopp"), undefined);
  });
  test("pipeline: table, filter, form", () => {
    const p = page(base({ tab: "pipeline" })); assert.equal(find(p, (n) => n.props && n.props["data-opp"] === "o1").length, 1); assert.ok(byId(p, "pl-stage")); assert.ok(byId(p, "opp-new"));
    assert.match(text(page(base({ tab: "pipeline", stageFilter: "WON" }))), /No opportunities/); assert.match(text(page(base({ tab: "pipeline", opps: [{ ...OPP, flags: ["OVERDUE", "STALE"] }] }))), /Overdue/);
    const f = page(base({ tab: "pipeline", oppForm: B.emptyOpp("a1") })); for (const id of ["of-account", "of-title", "of-cur", "of-value", "of-close", "of-stage", "of-save"]) assert.ok(byId(f, id), id);
    const e = page(base({ tab: "pipeline", oppForm: B.oppForm(OPP) })); assert.equal(byId(e, "of-account"), undefined); assert.equal(byId(e, "of-cur"), undefined);
  });
  test("opportunity detail: stage tools, win, lost, activity, proposals", () => {
    const d = page(base({ tab: "pipeline", opp: OPP }), "ACCOUNTANT"); assert.match(text(byId(d, "opp-summary")), /Meridian\. NGN 1,000\.00, 10% chance, weighted 100\.00/); for (const id of ["opp-edit", "mv-go", "prop-new", "lost-go", "ac-new"]) assert.ok(byId(d, id), id);
    assert.equal(byId(page(base({ tab: "pipeline", opp: OPP }), "APPROVER"), "mv-go"), undefined);
    const acc = { ...OPP, stage: "NEGOTIATION", proposals: [{ ...PROP, status: "ACCEPTED", submitted_by: "u1" }] };
    assert.ok(byId(page(base({ tab: "pipeline", opp: acc }), "ACCOUNTANT"), "win-request"));
    const wp = { ...OPP, stage: "WIN_PENDING", win_requested_by: "u1", proposals: [{ ...PROP, status: "ACCEPTED" }] };
    assert.ok(byId(page(base({ tab: "pipeline", opp: wp }), "MANAGER", "u1"), "win-own")); assert.equal(byId(page(base({ tab: "pipeline", opp: wp }), "MANAGER", "u1"), "win-decide"), undefined);
    const dec = page(base({ tab: "pipeline", opp: wp }), "MANAGER", "u2"); assert.ok(byId(dec, "wd-approve")); assert.ok(byId(dec, "wd-reject"));
    assert.equal(byId(page(base({ tab: "pipeline", opp: wp }), "MANAGER", "u2"), "mv-go"), undefined);
    const lost = page(base({ tab: "pipeline", opp: { ...OPP, stage: "LOST", lost_reason: "Went elsewhere" } })); assert.match(text(byId(lost, "opp-lost-reason")), /Went elsewhere/); assert.equal(byId(lost, "lost-go"), undefined); assert.equal(byId(lost, "prop-new"), undefined);
    assert.match(text(byId(page(base({ tab: "pipeline", opp: { ...OPP, stage: "WON", won_date: "2026-02-15" } })), "opp-won")), /2026-02-15/);
    assert.ok(byId(page(base({ tab: "pipeline", opp: OPP, activityForm: B.emptyActivity() })), "ac-save"));
  });
  test("proposal cards and form", () => {
    const withP = (p, role, uid) => page(base({ tab: "pipeline", opp: { ...OPP, proposals: [p] } }), role, uid);
    assert.ok(byId(withP(PROP, "ACCOUNTANT", "u1"), "prop-submit-pp1")); assert.ok(byId(withP(PROP, "ACCOUNTANT", "u1"), "prop-edit-pp1"));
    const pend = { ...PROP, status: "PENDING_APPROVAL", submitted_by: "u1", limit_at_submission: "10.00" };
    assert.match(text(withP(pend, "FINANCE_OFFICER", "u1")), /different person must approve/); assert.equal(byId(withP(pend, "FINANCE_OFFICER", "u1"), "prop-approve-pp1"), undefined); assert.ok(find(withP(pend, "FINANCE_OFFICER", "u1"), (n) => n.props && n.props.className === "prop-own").length);
    assert.ok(byId(withP(pend, "FINANCE_OFFICER", "u2"), "prop-approve-pp1")); assert.ok(byId(withP(pend, "FINANCE_OFFICER", "u2"), "prop-reject-pp1")); assert.equal(byId(withP(pend, "ACCOUNTANT", "u2"), "prop-approve-pp1"), undefined);
    assert.ok(byId(withP({ ...PROP, status: "APPROVED" }, "ACCOUNTANT", "u1"), "prop-send-pp1"));
    const sent = withP({ ...PROP, status: "SENT" }, "ACCOUNTANT", "u1"); assert.ok(byId(sent, "prop-accept-pp1")); assert.ok(byId(sent, "prop-decline-pp1"));
    const f = page(base({ tab: "pipeline", opp: OPP, proposalForm: { ...B.emptyProposal(), items: [{ description: "Service", quantity: "3", unit_price: "333.33" }], discount_pct: "12.5", valid_until: "2026-03-31" } }));
    for (const id of ["pp-d-0", "pp-q-0", "pp-u-0", "pp-disc", "pp-valid", "pp-add", "pp-save"]) assert.ok(byId(f, id), id); assert.equal(byId(f, "pp-rm-0"), undefined); assert.match(text(byId(f, "pp-preview")), /total 874\.99/);
    assert.match(text(byId(page(base({ tab: "pipeline", opp: OPP, proposalForm: B.emptyProposal() }), "OWNER"), "pp-preview")), /Fill in every line/);
  });
  test("targets and reports", () => {
    const t = page(base({ tab: "targets" })); assert.ok(byId(t, "tgt-new")); assert.ok(byId(t, "tgt-retire-t1")); assert.match(text(t), /50\.00%/); assert.equal(byId(page(base({ tab: "targets" }), "ACCOUNTANT"), "tgt-new"), undefined);
    assert.ok(byId(page(base({ tab: "targets", targetForm: B.emptyTarget() })), "tf-save")); assert.match(text(page(base({ tab: "targets", targets: [] }))), /No targets/);
    const r = page(base({ tab: "reports" })); assert.ok(byId(r, "rep-new")); assert.ok(byId(r, "rep-open-r1")); assert.ok(byId(page(base({ tab: "reports", reportForm: { currency: "", title: "" } })), "rp-cur"));
    const d = (st, role, uid) => page(base({ tab: "reports", report: { ...REPORT, ...st } }), role, uid);
    assert.match(text(byId(d({}, "MANAGER", "u2"), "rep-figures")), /Open 1,000\.00, weighted 100\.00, won 1 \(5,000\.00\)/); assert.ok(byId(d({}, "MANAGER", "u2"), "rep-decide")); assert.ok(byId(d({}, "MANAGER", "u1"), "rep-own")); assert.equal(byId(d({}, "MANAGER", "u1"), "rep-decide"), undefined);
    assert.ok(byId(d({ status: "APPROVED", decided_by: "u2" }, "READ_ONLY", "u3"), "rep-export")); assert.equal(byId(d({}, "MANAGER", "u2"), "rep-export"), undefined);
    assert.ok(byId(d({ status: "DRAFT", snapshot: null }, "ACCOUNTANT", "u1"), "rep-submit")); assert.match(text(d({ status: "DRAFT", snapshot: null }, "ACCOUNTANT", "u1")), /Nothing is frozen/);
  });
  test("empty states, error, notice, loading", () => {
    for (const [tab, re] of [["accounts", /No accounts/], ["pipeline", /No opportunities/], ["targets", /No targets/], ["reports", /No reports/]]) assert.match(text(page(base({ tab, accounts: [], opps: [], targets: [], reports: [] }))), re, tab);
    assert.match(text(page(base({ error: "boom" }))), /boom/); assert.match(text(page(base({ notice: "Saved." }))), /Saved\./);
    assert.match(text(Bizdev({ bd: base(), role: "OWNER", userId: "u1", loading: true, onRetry() {}, actions: noop })), /oading/); assert.match(text(page(base({ ov: null }))), /No data yet/);
  });
});

describe("client", () => {
  test("builds requests, encodes ids and downloads the report with the token", async () => {
    const calls = [];
    const api = new ApiClient({ baseUrl: "https://x.test", fetchImpl: async (url, init = {}) => { calls.push([init.method || "GET", url, init.body, init.headers && init.headers.Authorization]);
      return new Response(url.endsWith("/export") ? "a,b" : "{}", { status: 200, headers: { "Content-Type": url.endsWith("/export") ? "text/csv" : "application/json", "Content-Disposition": 'attachment; filename="R-001-pipeline-v1.csv"' } }); }, getToken: () => "tok" });
    await api.bdOpportunities("WON", "a/1"); await api.bdProposalStep("o1", "p1", "approve", "fine"); await api.bdProposalStep("o1", "p1", "send"); await api.moveBdStage("o1", "QUALIFIED", "x"); await api.setBdPolicy({ stale_days: 20 }); await api.rejectBdWin("o1", "no");
    const out = await api.exportBdReport("r1");
    assert.match(calls[0][1], /\/bizdev\/opportunities\?stage=WON&account_id=a%2F1/); assert.match(calls[1][1], /\/bizdev\/opportunities\/o1\/proposals\/p1\/approve$/); assert.equal(JSON.parse(calls[1][2]).note, "fine");
    assert.match(calls[2][1], /\/proposals\/p1\/send$/); assert.ok(calls[2][2] === undefined || calls[2][2] === "{}"); assert.match(calls[3][1], /\/o1\/stage$/); assert.equal(calls[4][0], "PUT"); assert.match(calls[5][1], /\/win\/reject$/);
    assert.equal(calls[6][3], "Bearer tok"); assert.equal(out.filename, "R-001-pipeline-v1.csv");
  });
  test("a failed export becomes an ApiError", async () => {
    const api = new ApiClient({ baseUrl: "https://x.test", fetchImpl: async () => new Response(JSON.stringify({ detail: "Only an approved report can be exported." }), { status: 409, headers: { "Content-Type": "application/json" } }), getToken: () => "tok" });
    await assert.rejects(() => api.exportBdReport("r1"), (e) => e.status === 409 && /approved/.test(e.message));
  });
});
