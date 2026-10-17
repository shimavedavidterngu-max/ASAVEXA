import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { accountProofSteps, reconciliationOrNull, lineMarkState, ACCOUNT_VOCAB } from "../src/lib/accountProof.js";
import { readFileSync } from "node:fs";

const by = (steps, k) => steps.find((s) => s.key === k);

describe("the proof behind an account line", () => {
  test("nothing checked: every step says Not checked, and the mark is unknown", () => {
    const s = accountProofSteps({});
    assert.deepEqual(s.map((x) => x.state), ["unknown", "unknown", "unknown"]);
    assert.equal(lineMarkState({ steps: s }), "unknown");
    assert.equal(lineMarkState(undefined), "unknown");
    assert.equal(lineMarkState({ error: "x" }), "unknown");
  });
  test("posted entries: counted from the server's list, worded, never recalculated", () => {
    assert.equal(by(accountProofSteps({ trace: [{}] }), "source").title, "1 posted entry");
    assert.equal(by(accountProofSteps({ trace: [{}, {}, {}] }), "source").title, "3 posted entries");
    assert.equal(by(accountProofSteps({ trace: [] }), "source").state, "missing");
    assert.equal(by(accountProofSteps({ trace: null }), "source").state, "missing");
    assert.equal(by(accountProofSteps({ trace: undefined }), "source").state, "unknown");
  });
  test("evidence: all, some or none, as the server counted them", () => {
    const e = (c) => by(accountProofSteps({ completeness: c }), "evidence");
    assert.equal(e({ total_entries: 4, entries_missing_evidence: 0 }).state, "linked");
    assert.equal(e({ total_entries: 4, entries_missing_evidence: 1 }).state, "pending");
    assert.match(e({ total_entries: 4, entries_missing_evidence: 1 }).title, /1 of 4 entries missing evidence/);
    assert.equal(e({ total_entries: 4, entries_missing_evidence: 4 }).state, "missing");
    assert.equal(e({ total_entries: 0, entries_missing_evidence: 0 }).state, "missing");
    assert.equal(e(null).state, "missing");
    assert.equal(e(undefined).state, "unknown");
  });
  test("reconciliation: left out when the account is not a bank account, otherwise worded from the server's counts", () => {
    assert.equal(by(accountProofSteps({ reconciliation: null }), "verification"), undefined);
    assert.equal(accountProofSteps({ reconciliation: null }).length, 2);
    assert.equal(reconciliationOrNull({ reconciled_count: 0, outstanding_count: 0, exception_count: 0 }), null);
    assert.equal(reconciliationOrNull(null), null);
    const v = (r) => by(accountProofSteps({ reconciliation: r }), "verification");
    assert.equal(v({ reconciled_count: 5, outstanding_count: 0, exception_count: 0 }).state, "linked");
    assert.equal(v({ reconciled_count: 5, outstanding_count: 2, exception_count: 0 }).state, "pending");
    assert.equal(v({ reconciled_count: 5, outstanding_count: 0, exception_count: 1 }).state, "pending");
    assert.match(v({ reconciled_count: 5, outstanding_count: 2, exception_count: 1 }).title, /5 reconciled · 2 outstanding · 1 exception$/);
    assert.equal(by(accountProofSteps({ reconciliation: undefined }), "verification").state, "unknown");
  });
  test("a complete account is complete; a partly evidenced one is incomplete; a bare one has none", () => {
    const full = accountProofSteps({ trace: [{}], completeness: { total_entries: 1, entries_missing_evidence: 0 }, reconciliation: null });
    assert.equal(lineMarkState({ steps: full }), "complete");
    const part = accountProofSteps({ trace: [{}], completeness: { total_entries: 2, entries_missing_evidence: 1 }, reconciliation: null });
    assert.equal(lineMarkState({ steps: part }), "partial");
    const none = accountProofSteps({ trace: [], completeness: null, reconciliation: null });
    assert.equal(lineMarkState({ steps: none }), "none");
  });
  test("it never does arithmetic on amounts", () => {
    const src = readFileSync(new URL("../src/lib/accountProof.js", import.meta.url), "utf8");
    assert.ok(!/parseFloat|Number\(|\.toFixed|Math\./.test(src));
    assert.deepEqual(Object.keys(ACCOUNT_VOCAB), ["source", "evidence", "verification"]);
  });
});
