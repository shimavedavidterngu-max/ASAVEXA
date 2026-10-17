import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { buildLineTrace, authorisedStep, committedStep, spentStep, evidenceStep, sentence, isZero, SPEND_ORDER } from "../src/lib/spendTrace.js";
import { Pubfin } from "../src/pages/Pubfin.js";
import { TABS } from "../src/lib/pubfin.js";

const walk = (v, fn) => { if (!v || typeof v !== "object") return; fn(v); (v.children || []).forEach((c) => walk(c, fn)); };
const all = (v, pred) => { const out = []; walk(v, (n) => { if (pred(n)) out.push(n); }); return out; };
const text = (v) => { if (v == null || v === false) return ""; if (typeof v !== "object") return String(v); return (v.children || []).map(text).join(""); };
const byId = (v, id) => all(v, (n) => n.props && n.props.id === id)[0];

const row = (o = {}) => ({ account_id: "a1", code: "5100", name: "Teaching materials", type: "EXPENSE", approved: "10000.00", adjustment: "0.00", budget: "10000.00", actual: "2000.00", committed: "1500.00", available: "6500.00", overspent: false, ...o });
const exec = (rows = [row()]) => ({ ref: "B-001", name: "Term budget", start: "2026-01-01", end: "2026-12-31", currency: "NGN", rows, journals_examined: 4, limitations: ["x"] });
const detail = (o = {}) => ({ id: "b1", ref: "B-001", status: "APPROVED", execution: exec(), ...o });
const com = (o = {}) => ({ id: "c1", ref: "C-001", budget_id: "b1", account_id: "a1", vendor: "Book Seller", amount: "1500.00", status: "OPEN", evidence: [], ...o });

describe("sentence", () => {
  test("says approved, spent, promised and available in plain words, with the server's own figures", () => {
    assert.equal(sentence(row(), "NGN"), "Of the 10,000.00 NGN approved for 5100 Teaching materials, 2,000.00 NGN has been spent (posted to the ledger), 1,500.00 NGN is promised in open commitments, and 6,500.00 NGN is still available.");
  });
  test("overspent says so and never shows a minus sign", () => {
    const s = sentence(row({ overspent: true, available: "-300.00" }), "NGN");
    assert.match(s, /300.00 NGN more has been spent or promised than was approved/);
    assert.doesNotMatch(s, /-300/);
  });
  test("income lines read differently", () => assert.match(sentence(row({ type: "REVENUE", committed: null }), "NGN"), /of income is expected/));
  test("no row, no sentence", () => assert.equal(sentence(null), null));
});

describe("steps", () => {
  test("authorised: approved, closed, waiting, not approved, not checked", () => {
    assert.equal(authorisedStep(detail(), row()).state, "linked");
    assert.equal(authorisedStep(detail({ status: "CLOSED" }), row()).stateLabel, "Approved, now closed");
    assert.equal(authorisedStep(detail({ status: "SUBMITTED" }), row()).state, "pending");
    assert.equal(authorisedStep(detail({ status: "DRAFT" }), row()).state, "missing");
    assert.equal(authorisedStep(undefined, undefined).state, "unknown");
  });
  test("a virement is said, with the new standing", () => {
    const s = authorisedStep(detail(), row({ adjustment: "500.00", budget: "10500.00" }));
    assert.match(s.meta, /virements \(500.00\).*10,500.00/);
  });
  test("committed: none, open, settled, not checked", () => {
    assert.equal(committedStep([]).state, "missing");
    assert.equal(committedStep([com()]).state, "pending");
    assert.equal(committedStep([com({ status: "SETTLED" })]).state, "linked");
    assert.equal(committedStep(undefined).state, "unknown");
  });
  test("spent: promised is not spent", () => {
    const s = spentStep(row({ actual: "0.00" }), exec());
    assert.deepEqual([s.state, s.stateLabel], ["missing", "Nothing posted yet"]);
    assert.match(s.meta, /only promised is not counted as spent/);
    const p = spentStep(row(), exec());
    assert.equal(p.state, "linked");
    assert.match(p.meta, /did not make any payment/);
    assert.match(p.meta, /4 posted journals were read/);
    assert.equal(spentStep(undefined, undefined).state, "unknown");
  });
  test("evidence: none, some, all, not checked", () => {
    assert.equal(evidenceStep([]).state, "missing");
    assert.equal(evidenceStep([com({ evidence: [{ filename: "q.pdf" }] })]).state, "linked");
    const some = evidenceStep([com({ evidence: [{ filename: "q" }] }), com({ id: "c2", ref: "C-002" })]);
    assert.deepEqual([some.state, some.title], ["pending", "1 of 2 commitments without evidence"]);
    assert.equal(evidenceStep([com()]).state, "missing");
    assert.equal(evidenceStep(undefined).state, "unknown");
  });
  test("isZero reads text, not numbers", () => { assert.ok(isZero("0.00") && isZero("0") && isZero("-0.00")); assert.ok(!isZero("0.01") && !isZero("10.00") && !isZero(null)); });
});

describe("buildLineTrace", () => {
  test("four steps in order; cancelled and other lines' commitments are left out", () => {
    const t = buildLineTrace({ detail: detail(), commitments: [com(), com({ id: "x", account_id: "other" }), com({ id: "y", status: "CANCELLED" }), com({ id: "z", budget_id: "b2" })], accountId: "a1" });
    assert.deepEqual(t.steps.map((s) => s.key), SPEND_ORDER);
    assert.equal(t.commitments.length, 1);
  });
  test("when the budget could not be loaded nothing reads clean", () => {
    const t = buildLineTrace({ detail: undefined, commitments: [], accountId: "a1" });
    assert.ok(t.steps.every((s) => s.state === "unknown"));
  });
  test("when commitments could not be loaded they are not checked, not none", () => {
    const t = buildLineTrace({ detail: detail(), commitments: undefined, accountId: "a1" });
    assert.equal(t.steps[1].state, "unknown"); assert.equal(t.steps[3].state, "unknown"); assert.equal(t.commitmentsKnown, false);
  });
  test("an unknown account gives no trace", () => assert.equal(buildLineTrace({ detail: detail(), commitments: [], accountId: "nope" }), null));
  test("it does no arithmetic", () => {
    const src = readFileSync(new URL("../src/lib/spendTrace.js", import.meta.url), "utf8");
    assert.doesNotMatch(src, /parseFloat|Number\(|reduce\(|\bMath\./);
  });
});

describe("the tab and the page", () => {
  test("the tab exists after Overview", () => assert.deepEqual(TABS.slice(0, 2).map(([i]) => i), ["overview", "spend"]));
  const pf = (o = {}) => ({ tab: "spend", budgets: [{ id: "b1", ref: "B-001", name: "Term budget", start: "2026-01-01", end: "2026-12-31", status: "APPROVED" }], commitments: [com({ evidence: [{ filename: "quote.pdf" }] })], spend: { budgetId: "b1", detail: detail(), line: null }, notes: {}, ...o });
  const page = (p) => Pubfin({ pf: p, role: "ACCOUNTANT", userId: "u", loading: false, onRetry() {}, actions: { setTab() {}, spendBudget() {}, spendLine() {} } });
  test("it draws the ledger, the plain sentence and a four-step rail", () => {
    const v = page(pf());
    assert.ok(byId(v, "pf-spend-ledger"));
    assert.match(text(byId(v, "pf-spend-sentence")), /has been spent \(posted to the ledger\)/);
    assert.equal(all(byId(v, "pf-spend-rail"), (n) => n.props && n.props.className && String(n.props.className).split(" ").includes("pr-step")).length, 4);
    assert.match(text(byId(v, "pf-spend-commitments")), /Evidence: quote.pdf/);
  });
  test("no approved budget says so", () => assert.ok(byId(page(pf({ budgets: [{ id: "b", status: "DRAFT" }] })), "pf-spend-none")));
  test("a failed load is Not checked, never zero", () => {
    const v = page(pf({ spend: { budgetId: "b1", detail: undefined, line: null, error: "boom" } }));
    assert.match(text(byId(v, "pf-spend-unknown")), /Not checked/);
    assert.equal(byId(v, "pf-spend-ledger"), undefined);
  });
  test("overspent lines carry a word, not only colour", () => {
    const d = detail({ execution: exec([row({ overspent: true, available: "-5.00" })]) });
    assert.match(text(byId(page(pf({ spend: { budgetId: "b1", detail: d, line: null } })), "pf-spend-lines")), /Over budget/);
  });
  test("it is a read view: no approve, pay or settle buttons in the ledger", () => {
    const l = byId(page(pf()), "pf-spend-ledger");
    assert.deepEqual(all(l, (n) => n.tag === "button").map((b) => text(b)), []);
  });
});
