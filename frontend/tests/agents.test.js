import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { Agents } from "../src/pages/Agents.js";
import * as L from "../src/lib/agents.js";
import { ApiClient } from "../src/api/client.js";

function find(v, pred, out = []) { if (!v || typeof v !== "object") return out; if (pred(v)) out.push(v); for (const c of v.children || []) find(c, pred, out); return out; }
const byId = (v, id) => find(v, (n) => n.props && n.props.id === id)[0];
const text = (v) => JSON.stringify(v);
const noop = new Proxy({}, { get: () => () => {} });
const agent = (o = {}) => ({ id: "a1", name: "Reviewer", purpose: "Reads the ledger", provider: "RULE_BASED", actions: ["READ_LEDGER"], status: "PROPOSED", proposed_by: "u1", ...o });
const dec = (o = {}) => ({ id: "d1", agent_name: "Reviewer", action: "DRAFT_JOURNAL", subject: "rent", decision: "REQUIRE_APPROVAL", reason: "A person must approve.", state: "PENDING", requested_by: "u1", ...o });
const catalog = [{ action: "READ_LEDGER", label: "Read the ledger", builtin: "ALLOW" }, { action: "DRAFT_JOURNAL", label: "Draft a journal", builtin: "REQUIRE_APPROVAL" }, { action: "POST_JOURNAL", label: "Post a journal", builtin: "DENY" }];
const policy = [{ action: "READ_LEDGER", label: "Read the ledger", builtin: "ALLOW", effective: "ALLOW" }, { action: "POST_JOURNAL", label: "Post a journal", builtin: "DENY", effective: "DENY" }];
const ag = (o = {}) => ({ agents: [], decisions: [], policy, catalog, members: [{ user_id: "u2", role: "OWNER" }], form: { ...L.EMPTY_AGENT }, formError: null, request: { agent_id: "", action: "", subject: "" }, reasons: {}, busy: false, error: null, notice: null, ...o });
const page = (s, role = "OWNER", me = "u1") => Agents({ ag: s, me, role, loading: false, onRetry() {}, actions: noop });

describe("helpers", () => {
  test("words for decisions, states and statuses", () => {
    assert.equal(L.decisionInfo("DENY").label, "Refused"); assert.equal(L.stateInfo("USED").label, "Used once"); assert.equal(L.agentStatus("ACTIVE").tone, "pass"); assert.equal(L.decisionInfo("x").label, "x");
  });
  test("only stricter policy choices are offered", () => {
    assert.deepEqual(L.stricterChoices("ALLOW"), ["REQUIRE_APPROVAL", "DENY"]); assert.deepEqual(L.stricterChoices("REQUIRE_APPROVAL"), ["DENY"]); assert.deepEqual(L.stricterChoices("DENY"), []);
  });
  test("forbidden actions cannot be granted", () => {
    assert.deepEqual(L.grantable(catalog).map((a) => a.action), ["READ_LEDGER", "DRAFT_JOURNAL"]);
  });
  test("who can activate and who can approve a request", () => {
    assert.deepEqual(L.agentActions(agent(), "u1", true, true), ["retire"]);
    assert.deepEqual(L.agentActions(agent(), "u2", true, true), ["activate", "retire"]);
    assert.deepEqual(L.agentActions(agent({ status: "ACTIVE" }), "u2", true, true), ["suspend", "retire"]);
    assert.deepEqual(L.agentActions(agent({ status: "RETIRED" }), "u2", true, true), []);
    assert.deepEqual(L.agentActions(agent(), "u2", true, false), []);
    assert.equal(L.canResolve(dec(), "u1", true), false); assert.equal(L.canResolve(dec(), "u2", true), true); assert.equal(L.canResolve(dec(), "u2", false), false); assert.equal(L.canResolve(dec({ state: "USED" }), "u2", true), false);
    assert.equal(L.needsIndependent(dec(), "u1"), true);
  });
  test("agent form is checked", () => {
    assert.match(L.agentFormProblem({ ...L.EMPTY_AGENT }), /name/); assert.match(L.agentFormProblem({ name: "a", purpose: "", owner: "x", actions: ["A"] }), /for/);
    assert.match(L.agentFormProblem({ name: "a", purpose: "p", owner: "", actions: ["A"] }), /owns/); assert.match(L.agentFormProblem({ name: "a", purpose: "p", owner: "x", actions: [] }), /action/);
    assert.equal(L.agentFormProblem({ name: "a", purpose: "p", owner: "x", actions: ["A"] }), null);
  });
});

describe("page", () => {
  test("empty registry says nothing runs automatically; the policy shows built-in and effective rules", () => {
    const v = page(ag());
    assert.match(text(byId(v, "ag-none")), /Nothing in ASAVEXA runs automatically/); assert.match(text(byId(v, "ag-policy")), /Refused/); assert.ok(byId(v, "ag-no-decisions"));
  });
  test("a forbidden action has no way to be loosened or granted", () => {
    const v = page(ag());
    assert.equal(find(v, (n) => n.props && n.props["data-tighten"] === "POST_JOURNAL").length, 0); assert.equal(find(v, (n) => n.props && n.props["data-tighten"] === "READ_LEDGER").length, 1);
    assert.equal(find(v, (n) => n.props && n.props["data-action"] === "POST_JOURNAL").length, 0); assert.equal(find(v, (n) => n.props && n.props["data-action"] === "READ_LEDGER").length, 1);
  });
  test("a viewer cannot propose, ask or tighten", () => {
    const v = page(ag(), "READ_ONLY");
    assert.equal(byId(v, "ag-add"), undefined); assert.equal(byId(v, "ag-request"), undefined); assert.equal(find(v, (n) => n.props && n.props["data-tighten"]).length, 0);
  });
  test("the proposer is told someone else must activate; another person can", () => {
    const mine = page(ag({ agents: [agent()] }), "OWNER", "u1");
    assert.equal(find(mine, (n) => n.props && n.props["data-sod"]).length, 1); assert.equal(find(mine, (n) => n.props && n.props["data-act"] === "activate").length, 0);
    assert.equal(find(page(ag({ agents: [agent()] }), "OWNER", "u2"), (n) => n.props && n.props["data-act"] === "activate").length, 1);
  });
  test("a request you made shows why you cannot approve it; another person gets Approve and Reject", () => {
    const s = ag({ decisions: [dec()] });
    const mine = page(s, "OWNER", "u1");
    assert.equal(find(mine, (n) => n.props && n.props["data-sod"]).length, 1); assert.equal(find(mine, (n) => n.props && n.props["data-act"] === "approve-request").length, 0);
    const other = page(s, "OWNER", "u2");
    assert.equal(find(other, (n) => n.props && n.props["data-act"] === "approve-request").length, 1); assert.equal(find(other, (n) => n.props && n.props["data-act"] === "reject-request").length, 1);
  });
  test("a refused decision is shown with its reason", () => {
    const v = page(ag({ decisions: [dec({ decision: "DENY", state: "REFUSED", reason: "No agent may do this: a person must." })] }));
    assert.match(text(v), /Refused/); assert.match(text(v), /a person must/);
  });
  test("Ask is disabled until an agent and action are chosen; only active agents are offered", () => {
    assert.equal(byId(page(ag()), "ag-ask").props.disabled, true);
    assert.equal(byId(page(ag({ request: { agent_id: "a1", action: "READ_LEDGER", subject: "" }, agents: [agent({ status: "ACTIVE" })] })), "ag-ask").props.disabled, false);
    const opts = find(byId(page(ag({ agents: [agent({ status: "ACTIVE" }), agent({ id: "a2", name: "Other", status: "PROPOSED" })] })), "ag-req-agent"), (n) => n.tag === "option");
    assert.deepEqual(opts.map((o) => o.props.value), ["", "a1"]);
  });
  test("errors and notices", () => {
    const v = page(ag({ error: "boom", notice: "Done.", formError: "Give the agent a name." }));
    assert.match(text(v), /boom/); assert.ok(byId(v, "ag-notice")); assert.ok(byId(v, "ag-form-error"));
  });
});

describe("wiring", () => {
  test("client endpoints", async () => {
    const calls = [];
    const api = new ApiClient({ baseUrl: "http://x", getToken: () => "t", fetchImpl: async (url, opt) => { calls.push([opt.method, url]); return { ok: true, status: 200, headers: { get: () => "application/json" }, json: async () => ({}), text: async () => "{}" }; } });
    await api.agents(); await api.proposeAgent({}); await api.agentAction("a1", "activate"); await api.resolveAgentDecision("d1", { approve: true }); await api.tightenAgentPolicy({});
    assert.deepEqual(calls.map((c) => c[0]), ["GET", "POST", "POST", "POST", "POST"]);
    assert.match(calls[2][1], /\/agents\/a1\/activate$/); assert.match(calls[3][1], /\/agents\/decisions\/d1\/resolve$/);
  });
  test("route, menu and group", () => {
    const app = readFileSync(new URL("../src/app.js", import.meta.url), "utf8");
    assert.match(app, /\{ path: "\/agents", name: "agents" \}/); assert.match(app, /label: "Agents"/); assert.match(app, /name === "agents"/);
    assert.match(readFileSync(new URL("../src/lib/home.js", import.meta.url), "utf8"), /"\/agents"\]/);
  });
});
