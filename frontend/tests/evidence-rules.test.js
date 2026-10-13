import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { EvidenceReview } from "../src/pages/EvidenceReview.js";
import * as R from "../src/lib/evidenceRules.js";
import { ApiClient } from "../src/api/client.js";

const text = (v) => JSON.stringify(v);
function find(v, pred, out = []) { if (!v || typeof v !== "object") return out; if (pred(v)) out.push(v); for (const c of v.children || []) find(c, pred, out); return out; }
const byId = (v, id) => find(v, (n) => n.props && n.props.id === id)[0];
const noop = new Proxy({}, { get: () => () => {} });
const DEFAULTS = [
  { id: "ER-001", name: "Every posted journal has linked evidence", account_types: null, expects_any: null, severity: "HIGH" },
  { id: "ER-002", name: "Revenue is supported by an invoice or a contract", account_types: ["REVENUE"], expects_any: ["INVOICE", "CONTRACT"], severity: "HIGH" },
];
const active = (o = {}) => ({ version: 0, status: "ACTIVE", source: "DEFAULT", rules: DEFAULTS, ...o });
const overview = (o = {}) => ({ active: active(), pending: null, history: [], note: "These are expectations your organisation chose. They are not a legal or accounting standard.", ...o });
const er = (o = {}) => ({ period_id: "p1", report: "income_statement", review: null, cases: [], members: [], openCase: null, forms: {}, busy: false, error: null, notice: null, rules: overview(), ...o });
const page = (e, role = "OWNER", me = "u1") => EvidenceReview({ er: e, periods: [{ id: "p1", name: "FY26" }], me, role, loading: false, onRetry() {}, actions: noop });

describe("rule helpers", () => {
  test("rules are described in plain words", () => {
    assert.deepEqual(R.describeRule(DEFAULTS[0]), { appliesTo: "every journal", expects: "any verified document" });
    assert.deepEqual(R.describeRule(DEFAULTS[1]), { appliesTo: "revenue", expects: "invoice or contract" });
  });
  test("a draft is a copy: editing it never changes the rules in use", () => {
    const d = R.draftFromRules(DEFAULTS); d[1].expects_any.push("RECEIPT"); d[0].name = "x";
    assert.deepEqual(DEFAULTS[1].expects_any, ["INVOICE", "CONTRACT"]); assert.notEqual(DEFAULTS[0].name, "x");
  });
  test("new rules get the next free id; toggling keeps catalogue order", () => {
    const d = R.draftFromRules(DEFAULTS);
    assert.equal(R.nextRuleId(d), "ER-003");
    assert.equal(R.newRule(d).id, "ER-003");
    let r = { id: "ER-009", account_types: [], expects_any: [] };
    r = R.toggleValue(r, "expects_any", "CONTRACT"); r = R.toggleValue(r, "expects_any", "INVOICE");
    assert.deepEqual(r.expects_any, ["INVOICE", "CONTRACT"]);
    r = R.toggleValue(r, "expects_any", "INVOICE");
    assert.deepEqual(r.expects_any, ["CONTRACT"]);
  });
  test("rulesPayload builds the request and keeps the baseline applying to every journal", () => {
    const d = R.draftFromRules(DEFAULTS); d[1].expects_any = ["RECEIPT"];
    const { body } = R.rulesPayload(d, " Revenue needs receipts ");
    assert.equal(body.reason, "Revenue needs receipts");
    assert.equal(body.rules[0].account_types, null); assert.equal(body.rules[0].expects_any, null);
    assert.deepEqual(body.rules[1].expects_any, ["RECEIPT"]);
    const odd = R.draftFromRules(DEFAULTS); odd[0].account_types = ["REVENUE"];
    assert.equal(R.rulesPayload(odd, "x").body.rules[0].account_types, null);
  });
  test("rulesPayload says what to fix before sending", () => {
    const d = () => R.draftFromRules(DEFAULTS);
    assert.match(R.rulesPayload([], "x").problem, /no rules/i);
    assert.match(R.rulesPayload(d(), "  ").problem, /why/i);
    const noName = d(); noName[1].name = " "; assert.match(R.rulesPayload(noName, "x").problem, /ER-002.*name/);
    const noTypes = d(); noTypes[1].account_types = []; assert.match(R.rulesPayload(noTypes, "x").problem, /kind of account/);
    const noEv = d(); noEv[1].expects_any = []; assert.match(R.rulesPayload(noEv, "x").problem, /kind of evidence/);
    const noBase = d().slice(1); assert.match(R.rulesPayload(noBase, "x").problem, /ER-001/);
    const many = d(); for (let i = 0; i < 30; i++) many.push(R.newRule(many)); assert.match(R.rulesPayload(many, "x").problem, /at most 25/);
  });
  test("words for status and version; only someone else may decide", () => {
    assert.equal(R.versionLabel({ version: 0 }), "Built-in defaults"); assert.equal(R.versionLabel({ version: 3 }), "Version 3");
    assert.equal(R.ruleStatus("PENDING").label, "Waiting for approval"); assert.equal(R.ruleStatus("REJECTED").tone, "fail");
    const p = { proposed_by: "u1" };
    assert.equal(R.canDecide(p, "u1", true), false); assert.equal(R.canDecide(p, "u2", true), true);
    assert.equal(R.canDecide(p, "u2", false), false); assert.equal(R.canDecide(null, "u2", true), false);
  });
});

describe("expected records card", () => {
  test("shows the rules in use with the not-a-standard note", () => {
    const v = page(er());
    const out = text(v);
    assert.ok(out.includes("er-rules-table")); assert.ok(out.includes("Built-in defaults")); assert.ok(out.includes("not a legal or accounting standard"));
    assert.ok(out.includes("er-rules-nohistory"));
  });
  test("a person who may prepare sees the propose button; an auditor-only role does not", () => {
    assert.ok(text(page(er(), "OWNER")).includes("er-rules-start"));
    assert.ok(!text(page(er(), "VIEWER")).includes("er-rules-start"));
  });
  test("the editor locks the baseline rule and offers account and evidence kinds for the others", () => {
    const d = R.draftFromRules(DEFAULTS);
    const out = text(page(er({ ruleDraft: d, ruleReason: "" })));
    assert.ok(out.includes("er-rules-editor")); assert.ok(out.includes("cannot be removed"));
    assert.equal((out.match(/data-remove-rule/g) || []).length, 1);          // only ER-002 can be removed
    assert.ok(out.includes("account_types:REVENUE")); assert.ok(out.includes("expects_any:RECEIPT"));
    assert.ok(out.includes("A different person must approve"));
  });
  test("an editor problem is shown, not sent", () => {
    assert.ok(text(page(er({ ruleDraft: R.draftFromRules(DEFAULTS), ruleError: "Say why the rules are changing." }))).includes("Say why the rules are changing."));
  });
  test("a pending change can be decided by someone else, not by its proposer", () => {
    const pending = { version: 1, status: "PENDING", proposed_by: "u1", reason: "Receipts please", rules: DEFAULTS };
    const mine = text(page(er({ rules: overview({ pending }) }), "OWNER", "u1"));
    assert.ok(mine.includes("er-rules-sod")); assert.ok(!mine.includes("er-rules-approve")); assert.ok(!mine.includes("er-rules-start"));
    const other = text(page(er({ rules: overview({ pending }) }), "OWNER", "u2"));
    assert.ok(other.includes("er-rules-approve")); assert.ok(other.includes("er-rules-reject")); assert.ok(!other.includes("er-rules-sod"));
  });
  test("history lists versions with their state", () => {
    const out = text(page(er({ rules: overview({ history: [{ version: 2, status: "ACTIVE", reason: "r2" }, { version: 1, status: "SUPERSEDED", reason: "r1" }] }) })));
    assert.ok(out.includes("Version 2")); assert.ok(out.includes("In use")); assert.ok(out.includes("Replaced"));
  });
});

describe("client", () => {
  test("rule endpoints", async () => {
    const calls = [];
    const c = new ApiClient("http://x"); c.get = (p) => (calls.push(["GET", p]), {}); c.post = (p, b) => (calls.push(["POST", p, b]), {});
    c.evidenceReviewRules(); c.proposeEvidenceReviewRules({ rules: [], reason: "r" }); c.approveEvidenceReviewRules(2, { note: "n" }); c.rejectEvidenceReviewRules(3, { reason: "no" });
    assert.deepEqual(calls.map((x) => x[1]), ["/evidence-review/rules", "/evidence-review/rules", "/evidence-review/rules/2/approve", "/evidence-review/rules/3/reject"]);
  });
});
