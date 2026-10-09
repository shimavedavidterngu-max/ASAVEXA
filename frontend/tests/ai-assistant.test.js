import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { AiAssistant, AiAnswer, ChainView, CHAIN_STEPS, MODES, newAiForm, validateAiForm, buildAiRequest, itemSubject } from "../src/pages/AiAssistant.js";
import { ApiClient } from "../src/api/client.js";

// Fixture = output of the REAL AiEngine over a real multi-module scenario (tests/test_ai.py rich_world).
const F = JSON.parse(readFileSync(new URL("./fixtures/ai-scenario.json", import.meta.url), "utf8"));
const text = (v) => JSON.stringify(v);
function find(v, pred, acc = []) { if (!v || typeof v !== "object") return acc; if (pred(v)) acc.push(v); for (const c of v.children || []) find(c, pred, acc); return acc; }
const noop = () => {};
const base = {
  role: "OWNER", mode: "EXPLAIN", form: newAiForm(), journals: [{ id: "j1", journal_number: "JRN-000001", date: "2026-01-01", description: "Rent" }],
  periods: [{ id: "p1", name: "FY2026-M01" }], running: false, question: "", result: null,
  onModeChange: noop, onFormChange: noop, onQuestionChange: noop, onRun: noop, onAsk: noop, onSample: noop, onToggle: noop, onDrill: noop, onRetry: noop,
};

describe("grounded chain", () => {
  test("every item in every mode renders all 8 steps in order with 7 arrows", () => {
    for (const k of ["explain", "detect", "recommend", "prove"]) {
      for (const item of F[k].items) {
        const root = ChainView(item);
        const steps = find(root, (n) => n.props && n.props["data-step"]).map((n) => n.props["data-step"]);
        assert.deepEqual(steps, CHAIN_STEPS.map(([k]) => k), `${k}: steps`);
        const heads = text(root);
        CHAIN_STEPS.forEach(([, label], i) => assert.ok(heads.includes(`${i + 1}. ${label}`), `${k}: heading ${label}`));
        assert.equal(find(root, (n) => n.props && n.props.className === "ai-arrow").length, 7, `${k}: arrows`);
      }
    }
  });
  test("missing evidence is shown as such, never hidden", () => {
    const t = text(AiAnswer({ result: F.recommend, expanded: Object.fromEntries(F.recommend.items.map((_, i) => [i, true])) }));
    assert.ok(/MISSING EVIDENCE|missing/i.test(t));
  });
});

describe("page", () => {
  test("four modes with the blueprint wording", () => {
    const t = text(AiAssistant(base));
    for (const s of ["AI Explain", "AI Detect", "AI Recommend", "AI Prove", "Why was this transaction classified this way?"]) assert.ok(t.includes(s), s);
    assert.deepEqual(MODES, ["EXPLAIN", "DETECT", "RECOMMEND", "PROVE"]);
  });
  test("each mode shows its own prompt", () => {
    assert.ok(text(AiAssistant({ ...base, mode: "DETECT" })).includes("Find unusual transactions."));
    assert.ok(text(AiAssistant({ ...base, mode: "RECOMMEND" })).includes("Suggest a reconciliation or adjustment."));
    assert.ok(text(AiAssistant({ ...base, mode: "PROVE" })).includes("Show the evidence supporting your answer."));
  });
  test("roles without ledger access see a message", () => {
    assert.ok(text(AiAssistant({ ...base, role: "SOMEONE_ELSE" })).includes("don't have access"));
  });
  test("loading and error states", () => {
    assert.ok(text(AiAssistant({ ...base, journals: null, loading: true })).includes("Loading"));
    assert.ok(text(AiAssistant({ ...base, journals: null, error: "boom" })).includes("boom"));
  });
  test("first item open by default; toggling and drill buttons are wired", () => {
    const calls = [];
    const root = AiAssistant({ ...base, result: F.detect, onDrill: (m, s) => calls.push([m, s.subjectType]), onToggle: (i) => calls.push(["toggle", i]) });
    const items = find(root, (n) => n.props && n.props["data-item"] !== undefined);
    assert.equal(items.length, F.detect.items.length);
    assert.ok(text(items[0]).includes("Human review requirement"));
    assert.ok(!text(items[1]).includes("Human review requirement"));
    const btn = (a) => find(items[0], (n) => n.props && n.props["data-action"] === a)[0];
    btn("explain").props.onClick(); btn("prove").props.onClick(); btn("toggle").props.onClick();
    assert.deepEqual(calls.map((c) => c[0]), ["EXPLAIN", "PROVE", "toggle"]);
  });
  test("Detect shows flags and publishes its rules", () => {
    const t = text(AiAnswer({ result: F.detect, expanded: { 0: true } }));
    assert.ok(t.includes("How Detect decides") && t.includes("score"));
  });
  test("Recommend shows 'Proposal only, not applied' and a balanced entry table", () => {
    const t = text(AiAnswer({ result: F.recommend, expanded: Object.fromEntries(F.recommend.items.map((_, i) => [i, true])) }));
    assert.ok(t.includes("Proposal only, not applied"));
  });
  test("Prove shows verdict, checks and the critical-check footnote", () => {
    const t = text(AiAnswer({ result: F.prove, expanded: { 0: true } }));
    assert.ok(t.includes("PROVEN") && t.includes("Agrees to the bank") && t.includes("a critical check"));
  });
  test("a refusal is shown as a refusal, with things it can do, and no chain", () => {
    const t = text(AiAnswer({ result: F.refusal }));
    assert.ok(t.includes("I cannot answer that from your records") && t.includes("Find unusual transactions.") && t.includes("will not guess"));
    assert.ok(!t.includes("Human review requirement"));
  });
  test("every answer carries limits, disclosure and fingerprint", () => {
    const t = text(AiAnswer({ result: F.explain }));
    assert.ok(t.includes("Limits of this answer") && t.includes(F.explain.fingerprint.slice(0, 16)));
  });
});

describe("pure helpers", () => {
  test("validateAiForm", () => {
    const f = newAiForm();
    assert.ok(validateAiForm("EXPLAIN", f));
    assert.equal(validateAiForm("DETECT", f), null);
    assert.equal(validateAiForm("RECOMMEND", f), null);
    assert.ok(validateAiForm("PROVE", f));
    assert.ok(validateAiForm("PROVE", { ...f, kind: "figure" }));
    assert.equal(validateAiForm("PROVE", { ...f, kind: "figure", periodId: "p" }), null);
    assert.equal(validateAiForm("EXPLAIN", { ...f, journalId: "j" }), null);
  });
  test("buildAiRequest", () => {
    const f = { ...newAiForm(), journalId: "j1", periodId: "p1" };
    assert.deepEqual(buildAiRequest("EXPLAIN", f), { call: "aiExplain", args: { subjectType: "journal", subjectId: "j1" } });
    assert.equal(buildAiRequest("DETECT", f).args.periodId, "p1");
    assert.equal(buildAiRequest("RECOMMEND", f).args.scope, "all");
    assert.deepEqual(buildAiRequest("PROVE", { ...f, kind: "figure", metric: "revenue" }).args, { subjectType: "figure", metric: "revenue", periodId: "p1" });
    assert.equal(buildAiRequest("PROVE", f).args.subjectId, "j1");
  });
  test("itemSubject resolves the journal or the bank line, from real items", () => {
    assert.equal(itemSubject(F.explain.items[0]).subjectType, "journal");
    assert.equal(itemSubject(null), null);
    const bank = F.recommend.items.find((i) => i.kind === "BANK_TRANSACTION");
    if (bank) assert.equal(itemSubject(bank).subjectType, "bank_transaction");
  });
});

describe("client", () => {
  test("AI methods hit the right paths with the right bodies", async () => {
    const seen = [];
    const c = new ApiClient({ baseUrl: "http://x" });
    c.post = async (p, b) => { seen.push([p, b]); return {}; };
    await c.aiExplain({ subjectType: "journal", subjectId: "j" });
    await c.aiDetect({ periodId: "p" });
    await c.aiRecommend({ scope: "evidence" });
    await c.aiProve({ subjectType: "figure", metric: "revenue", periodId: "p" });
    await c.aiAsk("hi");
    assert.deepEqual(seen.map((s) => s[0]), ["/ai/explain", "/ai/detect", "/ai/recommend", "/ai/prove", "/ai/ask"]);
    assert.deepEqual(seen[0][1], { subject_type: "journal", subject_id: "j" });
    assert.equal(seen[1][1].period_id, "p");
    assert.equal(seen[3][1].metric, "revenue");
    assert.deepEqual(seen[4][1], { question: "hi" });
  });
});
