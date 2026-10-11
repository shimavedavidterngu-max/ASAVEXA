import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { Grc } from "../src/pages/Grc.js";
import * as G from "../src/lib/grc.js";
import { ApiClient } from "../src/api/client.js";
import { can, PERMISSIONS } from "../src/lib/permissions.js";

const text = (v) => JSON.stringify(v);
function find(v, pred, out = []) { if (!v || typeof v !== "object") return out; if (pred(v)) out.push(v); for (const c of v.children || []) find(c, pred, out); return out; }
const byId = (v, id) => find(v, (n) => n.props && n.props.id === id)[0];
const noop = new Proxy({}, { get: () => () => {} });
const OPTIONS = { categories: { FRAUD: "Fraud", OTHER: "Other" }, treatments: { MITIGATE: "Reduce it" }, source_types: { LAW: "Law" }, frequencies: ["ONE_OFF", "ANNUAL"], likelihood: { 1: "Rare", 5: "Almost certain" }, impact: { 1: "Negligible", 5: "Severe" },
  controls: [{ id: "c1", code: "ACC-001", name: "Balanced" }], settings: { appetite: 9 }, limitations: [] };
const cells = Array.from({ length: 5 }, () => [0, 0, 0, 0, 0]); cells[3][3] = 2;
const DASH = { as_of: "2026-06-15", appetite: 9, counts: { risks: 2, live_risks: 2, critical_or_high: 2, above_appetite: 2, actions_open: 1, actions_awaiting_verification: 0, obligations: 1, obligations_overdue: 1, obligations_due_soon: 0 },
  heatmap: { likelihood_labels: { 1: "Rare", 2: "Unlikely", 3: "Possible", 4: "Likely", 5: "Almost certain" }, impact_labels: { 1: "Negligible", 2: "Minor", 3: "Moderate", 4: "Major", 5: "Severe" }, cells, meaning: "Rows are likelihood." },
  by_band: {}, by_category: {}, top_risks: [], attention: { above_appetite_without_plan: [{ ref: "R-001", title: "Cash theft", residual_score: 16, owner: "Finance" }], acceptances_waiting: [], reviews_overdue: [], actions_overdue: [], actions_to_verify: [], obligations_overdue: [{ ref: "O-001", title: "Annual return", next_due: "2026-06-01", owner: "Sec" }], obligations_due_soon: [] },
  limitations: ["Scores are judgements entered by people."] };
const RISK = { id: "r1", ref: "R-001", title: "Cash theft", description: "d", category: "FRAUD", category_text: "Fraud and integrity", owner: "Finance lead", inherent_l: 4, inherent_i: 4, residual_l: 4, residual_i: 4, residual_justification: "", treatment: "MITIGATE", treatment_text: "Reduce it",
  inherent_score: 16, residual_score: 16, inherent_band: "HIGH", residual_band: "HIGH", above_appetite: true, review_overdue: false, next_review: "2026-12-01", status: "ASSESSED", controls: [], control_ids: [], acceptance: null, actions: [], history: [{ at: "2026-06-15T09:00:00", by: "u1", event: "CREATED", note: "" }], action_counts: {} };
const ACTION = { id: "a1", ref: "A-001", risk_id: "r1", risk_ref: "R-001", title: "Install safe", description: "", owner: "Ops", due: "2026-07-01", status: "OPEN", overdue: false, created_by: "u1", completed_by: null, completion_note: "", evidence: [], verify_note: "" };
const OB = { id: "o1", ref: "O-001", title: "Annual return", source_type: "LAW", source_text: "Law", authority: "Registrar", source_ref: "s.12", source_url: "https://example.org", description: "File it", owner: "Sec", frequency: "ANNUAL", next_due: "2026-06-01", state: "OVERDUE", status: "ACTIVE", history: [], control_ids: [], controls: [] };
const base = (o = {}) => ({ options: OPTIONS, dash: DASH, risks: [RISK], actions: [ACTION], obligations: [OB], vault: [], tab: "overview", filter: "", risk: null, riskForm: null, acceptForm: null, actionForm: null, doneForm: null, cancelId: null, obForm: null, metForm: null, retireId: null,
  notes: {}, appetiteInput: "9", busy: false, error: null, notice: null, ...o });
const page = (gc, role = "OWNER", userId = "u1") => Grc({ gc, role, userId, loading: false, onRetry() {}, actions: noop });

describe("permissions", () => {
  test("who can prepare, approve and see", () => {
    for (const r of ["OWNER", "ADMINISTRATOR", "FINANCE_OFFICER", "MANAGER"]) { assert.equal(can(r, PERMISSIONS.GRC_PREPARE), true, r); assert.equal(can(r, PERMISSIONS.AUDIT_READ), true, r); }
    for (const r of ["OWNER", "APPROVER", "MANAGER"]) assert.equal(can(r, PERMISSIONS.GRC_APPROVE), true, r);
    for (const r of ["ACCOUNTANT", "AUDITOR", "REVIEWER", "READ_ONLY", "EXTERNAL_AUDITOR", "FINANCE_OFFICER", "ADMINISTRATOR"]) assert.equal(can(r, PERMISSIONS.GRC_APPROVE), false, r);
    for (const r of ["AUDITOR", "READ_ONLY", "REVIEWER", "APPROVER"]) assert.equal(can(r, PERMISSIONS.GRC_PREPARE), false, r);
  });
});

describe("helpers", () => {
  test("bands match the server's boundaries", () => assert.deepEqual([1, 4, 5, 9, 10, 16, 17, 25].map(G.bandOf), ["LOW", "LOW", "MEDIUM", "MEDIUM", "HIGH", "HIGH", "CRITICAL", "CRITICAL"]));
  test("real-date check", () => { assert.equal(G.isRealDate("2026-02-28"), true); for (const x of ["2026-02-30", "2026-13-01", "26-1-1", "", null, "soon"]) assert.equal(G.isRealDate(x), false, String(x)); });
  test("risk validation", () => {
    const f = (o) => ({ ...G.emptyRisk(), title: "Cash theft", owner: "Finance lead", next_review: "2026-12-01", ...o });
    assert.equal(G.riskProblem(f({})), null);
    assert.match(G.riskProblem(f({ title: "ab" })), /title/); assert.match(G.riskProblem(f({ owner: "" })), /owns/);
    assert.match(G.riskProblem(f({ inherent_l: "6" })), /1 to 5/); assert.match(G.riskProblem(f({ residual_i: "x" })), /1 to 5/);
    assert.match(G.riskProblem(f({ residual_l: "4" })), /higher/);
    assert.match(G.riskProblem(f({ residual_l: "1" })), /written reason/);
    assert.equal(G.riskProblem(f({ residual_l: "1", residual_justification: "Dual signatures in place" })), null);
    assert.match(G.riskProblem(f({ next_review: "2026-02-30" })), /review date/);
  });
  test("risk body uses numbers and trims", () => {
    const b = G.riskBody({ ...G.emptyRisk(), title: " T ok ", owner: " Me too ", next_review: "2026-12-01 " });
    assert.deepEqual([b.title, b.owner, b.inherent_l, b.residual_i, b.next_review], ["T ok", "Me too", 3, 3, "2026-12-01"]);
  });
  test("risk moves respect roles, status and who asked", () => {
    const acc = { ...RISK, status: "ACCEPTANCE_REQUESTED", acceptance: { requested_by: "u1" } };
    assert.equal(G.riskMoves(acc, "MANAGER", "u1").decide, false); assert.equal(G.riskMoves(acc, "MANAGER", "u1").ownRequest, true);
    assert.equal(G.riskMoves(acc, "MANAGER", "u2").decide, true); assert.equal(G.riskMoves(acc, "FINANCE_OFFICER", "u2").decide, false);
    assert.equal(G.riskMoves(RISK, "AUDITOR", "u1").edit, false); assert.equal(G.riskMoves(RISK, "FINANCE_OFFICER", "u1").treat, true);
    assert.equal(G.riskMoves({ ...RISK, treatment: "ACCEPT" }, "OWNER", "u1").treat, false);
    assert.equal(G.riskMoves({ ...RISK, status: "CLOSED" }, "OWNER", "u1").addAction, false); assert.equal(G.riskMoves({ ...RISK, status: "CLOSED" }, "OWNER", "u1").reopen, true);
  });
  test("action moves: the completer cannot verify", () => {
    const done = { ...ACTION, status: "DONE", completed_by: "u1" };
    assert.equal(G.actionMoves(done, "MANAGER", "u1").verify, false); assert.equal(G.actionMoves(done, "MANAGER", "u1").ownCompletion, true);
    assert.equal(G.actionMoves(done, "MANAGER", "u2").verify, true); assert.equal(G.actionMoves(done, "ADMINISTRATOR", "u2").verify, false);
    assert.equal(G.actionMoves(ACTION, "ADMINISTRATOR", "u2").complete, true); assert.equal(G.actionMoves(ACTION, "READ_ONLY", "u2").complete, false);
  });
  test("action, obligation, met and acceptance validation", () => {
    assert.match(G.actionProblem({ ...G.emptyAction(), title: "Do it", owner: "Ops", due: "2026-07-01" }), /risk/);
    assert.equal(G.actionProblem({ ...G.emptyAction("r1"), title: "Do it", owner: "Ops", due: "2026-07-01" }), null);
    assert.match(G.actionProblem({ ...G.emptyAction("r1"), title: "Do it", owner: "Ops", due: "tomorrow" }), /due date/);
    const o = { ...G.emptyObligation(), title: "Return", authority: "Registrar", description: "File it", owner: "Sec", next_due: "2026-12-31" };
    assert.equal(G.obligationProblem(o), null); assert.match(G.obligationProblem({ ...o, source_url: "javascript:x" }), /http/); assert.match(G.obligationProblem({ ...o, authority: "" }), /owed/);
    assert.match(G.metProblem({ met_on: "2026-06-16", note: "Filed online" }, "2026-06-15"), /future/); assert.match(G.metProblem({ met_on: "2026-06-15", note: "" }, "2026-06-15"), /how/);
    assert.equal(G.metProblem({ met_on: "2026-06-15", note: "Filed online" }, "2026-06-15"), null);
    assert.match(G.acceptProblem({ justification: "short", review_by: "2026-12-01" }, "2026-06-15"), /20/); assert.match(G.acceptProblem({ justification: "x".repeat(25), review_by: "2026-06-15" }, "2026-06-15"), /future/);
    assert.equal(G.acceptProblem({ justification: "x".repeat(25), review_by: "2026-12-01" }, "2026-06-15"), null);
  });
  test("action body leaves out risk_id when editing", () => {
    assert.equal("risk_id" in G.actionBody({ id: "a1", risk_id: "r1", title: "t t", description: "", owner: "Ops", due: "2026-07-01" }), false);
    assert.equal(G.actionBody({ id: "", risk_id: "r1", title: "t t", description: "", owner: "Ops", due: "2026-07-01" }).risk_id, "r1");
  });
});

describe("page", () => {
  test("overview shows the 5x5 map, counts, appetite and what needs attention", () => {
    const v = page(base());
    assert.equal(find(byId(v, "gc-heatmap"), (n) => n.props && n.props["data-l"]).length, 25);
    const hot = find(v, (n) => n.props && n.props["data-l"] === "4" && n.props["data-i"] === "4")[0]; assert.match(text(hot), /2/);
    assert.match(text(byId(v, "gc-counts")), /2 live risk/); assert.match(text(byId(v, "gc-appetite")), /above 9/);
    assert.match(text(v), /Cash theft/); assert.match(text(v), /Annual return/); assert.match(text(v), /judgements/);
  });
  test("only approvers can change the appetite", () => {
    assert.ok(byId(page(base(), "OWNER"), "gc-appetite-in")); assert.equal(byId(page(base(), "FINANCE_OFFICER"), "gc-appetite-in"), undefined);
  });
  test("risk list shows score, band, appetite flag; add button only for preparers", () => {
    const v = page(base({ tab: "risks" }), "OWNER"); assert.match(text(byId(v, "gc-risk-table")), /16/); assert.match(text(v), /above appetite/); assert.ok(byId(v, "risk-new"));
    assert.equal(byId(page(base({ tab: "risks" }), "AUDITOR"), "risk-new"), undefined);
    assert.match(text(page(base({ tab: "risks", risks: [] }))), /No risks recorded/);
  });
  test("risk form shows the arithmetic and asks for a reason only when residual is lower", () => {
    const f = { ...G.emptyRisk(), inherent_l: "4", inherent_i: "4", residual_l: "4", residual_i: "4" };
    let v = page(base({ tab: "risks", riskForm: f })); assert.match(text(v), /4 x 4 = 16/); assert.equal(byId(v, "rf-just"), undefined);
    v = page(base({ tab: "risks", riskForm: { ...f, residual_l: "2" } })); assert.match(text(v), /2 x 4 = 8/); assert.ok(byId(v, "rf-just"));
    assert.ok(byId(v, "rf-ctl-c1"));
  });
  test("risk detail: acceptance box only for a different approver", () => {
    const r = { ...RISK, status: "ACCEPTANCE_REQUESTED", acceptance: { requested_by: "u1", justification: "Cost too high for the benefit.", review_by: "2026-12-01", within_appetite: false, decided_by: null } };
    assert.ok(byId(page(base({ tab: "risks", risk: r }), "MANAGER", "u2"), "decide-box"));
    const own = page(base({ tab: "risks", risk: r }), "MANAGER", "u1"); assert.equal(byId(own, "decide-box"), undefined); assert.match(text(own), /different person must decide/);
    assert.equal(byId(page(base({ tab: "risks", risk: r }), "FINANCE_OFFICER", "u2"), "decide-box"), undefined);
    assert.match(text(byId(page(base({ tab: "risks", risk: r }), "MANAGER", "u2"), "risk-acceptance")), /Waiting for a decision/);
  });
  test("risk detail shows history, scores with arithmetic and the buttons the state allows", () => {
    const v = page(base({ tab: "risks", risk: RISK }), "OWNER");
    assert.match(text(byId(v, "risk-scores")), /4 x 4 = 16/); assert.match(text(byId(v, "risk-history")), /created/);
    for (const id of ["risk-edit", "risk-treat", "risk-accept", "risk-add-action", "cl-save"]) assert.ok(byId(v, id), id);
    assert.equal(byId(page(base({ tab: "risks", risk: { ...RISK, status: "CLOSED", closed_by: "u1", close_note: "x" } }), "OWNER"), "risk-edit"), undefined);
  });
  test("done form in the risk view lists vault evidence; actions tab shows verification buttons by person", () => {
    const risk = { ...RISK, actions: [ACTION] };
    const v = page(base({ tab: "risks", risk, doneForm: { id: "a1", note: "", evidence_ids: [] }, vault: [{ id: "e1", original_filename: "proof.pdf" }] }), "OWNER");
    assert.ok(byId(v, "done-form")); assert.ok(byId(v, "dn-ev-e1"));
    const done = { ...ACTION, status: "DONE", completed_by: "u1", completion_note: "Installed", evidence: [] };
    const a2 = page(base({ tab: "actions", actions: [done] }), "MANAGER", "u2"); assert.ok(byId(a2, "act-verify-a1")); assert.ok(byId(a2, "vf-note"));
    const a1 = page(base({ tab: "actions", actions: [done] }), "MANAGER", "u1"); assert.equal(byId(a1, "act-verify-a1"), undefined); assert.match(text(a1), /someone else must verify/);
  });
  test("overdue actions say so", () => assert.match(text(page(base({ tab: "actions", actions: [{ ...ACTION, overdue: true }] }))), /overdue/));
  test("obligations tab: no legal content, source link is safe, mark-met only when something is due", () => {
    const v = page(base({ tab: "obligations" }), "OWNER"); assert.match(text(v), /ships none/); assert.match(text(v), /Overdue/);
    const link = find(v, (n) => n.tag === "a")[0]; assert.equal(link.props.rel, "noopener noreferrer"); assert.ok(byId(v, "ob-met-o1"));
    assert.equal(byId(page(base({ tab: "obligations", obligations: [{ ...OB, next_due: null, state: "MET" }] }), "OWNER"), "ob-met-o1"), undefined);
    assert.equal(byId(page(base({ tab: "obligations" }), "AUDITOR"), "ob-met-o1"), undefined);
    assert.match(text(page(base({ tab: "obligations", metForm: { id: "o1", met_on: "2026-06-15", note: "", evidence_ids: [] } }))), /does not check it/);
  });
  test("error, notice and loading states", () => {
    assert.match(text(page(base({ error: "boom" }))), /boom/); assert.match(text(page(base({ notice: "Saved." }))), /Saved\./);
    assert.match(text(Grc({ gc: base(), role: "OWNER", userId: "u1", loading: true, onRetry() {}, actions: noop })), /oading/);
  });
  test("dashboard tolerates no data", () => assert.match(text(page(base({ dash: null }))), /No data yet/));
});

describe("client", () => {
  test("builds the right requests, encodes ids, and downloads the register with the token", async () => {
    const calls = [];
    const api = new ApiClient({ baseUrl: "https://x.test", fetchImpl: async (url, init = {}) => { calls.push([init.method || "GET", url, init.body, init.headers && init.headers.Authorization]);
      return new Response(url.endsWith("/export") ? "a,b" : "{}", { status: 200, headers: { "Content-Type": url.endsWith("/export") ? "text/csv" : "application/json", "Content-Disposition": 'attachment; filename="reg.csv"' } }); }, getToken: () => "tok" });
    await api.grcRisks("ASSESSED"); await api.acceptGrcRisk("r/1", { justification: "x", review_by: "2026-12-01" }); await api.sendBackGrcAction("a1", "no photo"); await api.markGrcObligationMet("o1", { met_on: "2026-06-15", note: "n", evidence_ids: [] });
    const out = await api.exportGrcRegister();
    assert.match(calls[0][1], /\/grc\/risks\?status=ASSESSED/); assert.match(calls[1][1], /\/grc\/risks\/r%2F1\/accept$/); assert.match(calls[2][1], /\/grc\/actions\/a1\/send-back$/); assert.equal(JSON.parse(calls[2][2]).note, "no photo");
    assert.match(calls[3][1], /\/grc\/obligations\/o1\/met$/); assert.equal(calls[4][3], "Bearer tok"); assert.equal(out.filename, "reg.csv");
  });
});
