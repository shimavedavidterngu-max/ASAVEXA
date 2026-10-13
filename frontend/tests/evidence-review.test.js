import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { EvidenceReview } from "../src/pages/EvidenceReview.js";
import * as L from "../src/lib/evidenceReview.js";
import { ApiClient } from "../src/api/client.js";

function find(v, pred, out = []) { if (!v || typeof v !== "object") return out; if (pred(v)) out.push(v); for (const c of v.children || []) find(c, pred, out); return out; }
const byId = (v, id) => find(v, (n) => n.props && n.props.id === id)[0];
const text = (v) => JSON.stringify(v);
const noop = new Proxy({}, { get: () => () => {} });
const metrics = (o = {}) => ({ journals: 2, journals_with_gaps: 1, gap_issues: 1, tie_failures: 0, recorded_links: 1, inferred_links: 0, ...o });
const review = (o = {}) => ({ verdict: "PARTLY_SUPPORTED", assertion: { statement: "The income statement shows 2 figure(s)." }, metrics: metrics(), limits: "It does not prove the figure is correct.",
  supporting: [{ journal_id: "j1", journal_number: "JRN-1", description: "Invoice", evidence: { type: "INVOICE", filename: "inv.pdf", status: "VERIFIED" }, link: { kind: "RECORDED" } }],
  missing: [{ journal_id: "j2", journal_number: "JRN-2", kind: "MISSING", detail: "No evidence is linked." }], unverified: [], conflicting: [], stale: [], tie_failures: [],
  uncertain: ["A verified document is still not proof."], action_needed: [{ journal_number: "JRN-2", text: "Attach evidence." }], truncated: false, ...o });
const kase = (o = {}) => ({ id: "c1", ref: "EVR-001", title: "Gaps", status: "OPEN", baseline: { gaps: 1 }, owner: null, completed_by: null, attempts: [], history: [{ at: "2026-10-12T10:00:00", event: "OPENED", note: "x" }], ...o });
const er = (o = {}) => ({ period_id: "p1", report: "income_statement", review: null, cases: [], members: [], openCase: null, forms: {}, busy: false, error: null, notice: null, ...o });
const page = (e, role = "OWNER", me = "u1", periods = [{ id: "p1", name: "FY26-M01" }]) => EvidenceReview({ er: e, periods, me, role, loading: false, onRetry() {}, actions: noop });

describe("helpers", () => {
  test("verdicts and issue words are plain", () => {
    assert.equal(L.verdictInfo("SUPPORTED").label, "Fully supported");
    assert.equal(L.verdictInfo("CONTRADICTED").tone, "fail");
    assert.equal(L.issueText("SELF_VERIFIED"), "Verified by its own uploader");
    assert.equal(L.linkText("INFERRED"), "Matched by reference only");
    assert.equal(L.verdictInfo("???").label, "???");
  });
  test("gaps count journals with gaps plus figures that do not tie", () => {
    assert.equal(L.gapCount(review({ metrics: metrics({ journals_with_gaps: 2, tie_failures: 1 }) })), 3);
    assert.equal(L.gapCount(null), 0);
  });
  test("a case can only be raised from a review with gaps, by someone allowed, and not while busy", () => {
    assert.equal(L.canOpenCase(review(), true, false), true);
    assert.equal(L.canOpenCase(review(), false, false), false);
    assert.equal(L.canOpenCase(review(), true, true), false);
    assert.equal(L.canOpenCase(review({ metrics: metrics({ journals_with_gaps: 0 }) }), true, false), false);
    assert.equal(L.canOpenCase(null, true, false), false);
  });
  test("the person who did or owns the work cannot verify it", () => {
    const c = kase({ status: "ACTION_DONE", completed_by: "a", owner: "b" });
    assert.equal(L.canVerify(c, "a", true), false);
    assert.equal(L.canVerify(c, "b", true), false);
    assert.equal(L.canVerify(c, "z", true), true);
    assert.equal(L.canVerify(c, "z", false), false);
    assert.equal(L.canVerify(kase({ status: "OPEN" }), "z", true), false);
  });
  test("next step tells each person what to do", () => {
    assert.match(L.nextStep(kase(), "u"), /Plan the action/);
    assert.match(L.nextStep(kase({ status: "ACTION_DONE", completed_by: "u" }), "u"), /cannot/);
    assert.match(L.nextStep(kase({ status: "ACTION_DONE", completed_by: "a" }), "u"), /independent/);
    assert.match(L.nextStep(kase({ status: "VERIFIED" }), "u"), /Re-check/);
  });
  test("problem rows gather every kind of problem", () => {
    const rows = L.problemRows(review({ stale: [{ journal_id: "j3", journal_number: "JRN-3", kind: "STALE", detail: "old" }], tie_failures: [{ label: "1000 Cash", detail: "off by 5" }] }));
    assert.equal(rows.length, 3);
    assert.deepEqual(L.problemRows(null), []);
  });
});

describe("page", () => {
  test("before a review it asks for a period, with no case button", () => {
    const v = page(er());
    assert.ok(byId(v, "er-run")); assert.equal(byId(v, "er-result"), undefined); assert.equal(byId(v, "er-open-case"), undefined);
    assert.ok(byId(v, "er-no-cases"));
  });
  test("run is disabled with no period", () => {
    assert.equal(byId(page(er({ period_id: "" })), "er-run").props.disabled, true);
  });
  test("a review shows verdict, problems, supporting records, uncertainty, action and limits", () => {
    const v = page(er({ review: review() }));
    assert.match(text(byId(v, "er-verdict")), /Partly supported/);
    assert.match(text(byId(v, "er-problems")), /JRN-2/); assert.match(text(byId(v, "er-problems")), /No evidence/);
    assert.match(text(byId(v, "er-supporting")), /Linked by a person/);
    assert.match(text(byId(v, "er-uncertain")), /not proof/);
    assert.match(text(byId(v, "er-actions")), /Attach evidence/);
    assert.ok(byId(v, "er-limits")); assert.ok(byId(v, "er-open-case"));
  });
  test("a fully supported review says so and offers no case", () => {
    const v = page(er({ review: review({ verdict: "SUPPORTED", metrics: metrics({ journals_with_gaps: 0 }), missing: [], action_needed: [] }) }));
    assert.ok(byId(v, "er-clean")); assert.equal(byId(v, "er-open-case"), undefined);
  });
  test("a role without finding:manage does not see the raise button", () => {
    assert.equal(byId(page(er({ review: review() }), "READ_ONLY"), "er-open-case"), undefined);
  });
  test("inferred links are flagged as not made by a person", () => {
    const r = review(); r.supporting[0].link = { kind: "INFERRED" };
    assert.match(text(byId(page(er({ review: r })), "er-supporting")), /Matched by reference only/);
  });
  test("a truncated review warns that counts are partial", () => {
    assert.match(text(page(er({ review: review({ truncated: true }) }))), /only the first ones/);
  });
  test("an error and a notice are shown", () => {
    const v = page(er({ error: "boom", notice: "Case raised." }));
    assert.match(text(v), /boom/); assert.ok(byId(v, "er-notice"));
  });
  test("an open case shows its form for its stage", () => {
    const planned = page(er({ cases: [kase({ status: "ACTION_PLANNED", action: "Attach lease", owner: "u2" })], openCase: "c1" }));
    assert.match(text(planned), /Record it as done/);
    const open = page(er({ cases: [kase()], openCase: "c1", members: [{ user_id: "u1", role: "OWNER" }] }));
    assert.match(text(open), /Plan the action/);
  });
  test("a verifier who did the work sees why they cannot verify, anyone else sees the button", () => {
    const c = kase({ status: "ACTION_DONE", completed_by: "u1", owner: "u2", completion_note: "done" });
    const mine = page(er({ cases: [c], openCase: "c1" }), "OWNER", "u1");
    assert.ok(find(mine, (n) => n.props && n.props["data-sod"]).length); assert.equal(find(mine, (n) => n.props && n.props["data-act"] === "verify").length, 0);
    const other = page(er({ cases: [c], openCase: "c1" }), "OWNER", "u3");
    assert.equal(find(other, (n) => n.props && n.props["data-act"] === "verify").length, 1);
  });
  test("a verified case shows its measured outcome and offers a re-check", () => {
    const c = kase({ status: "VERIFIED", outcome: { result: "RESOLVED", baseline_gaps: 1, post_gaps: 0, residual_risk: "low", reopen_criteria: "new gap" } });
    const v = page(er({ cases: [c], openCase: "c1" }));
    assert.match(text(v), /1 gap\(s\) before, 0 after/); assert.equal(find(v, (n) => n.props && n.props["data-act"] === "recheck").length, 1);
  });
  test("a rejected verification is reported", () => {
    const c = kase({ status: "ACTION_PLANNED", action: "x", attempts: [{ result: "NOT_IMPROVED", post_gaps: 1 }] });
    assert.match(text(page(er({ cases: [c], openCase: "c1" }))), /rejected 1 time/);
  });
  test("no periods gives an empty state", () => {
    assert.match(text(page(er(), "OWNER", "u1", [])), /No accounting periods/);
  });
});

describe("api client", () => {
  test("calls the right endpoints", async () => {
    const calls = [];
    const api = new ApiClient({ baseUrl: "http://x", getToken: () => "t", fetchImpl: async (url, opt) => { calls.push([opt.method, url]); return { ok: true, status: 200, headers: { get: () => "application/json" }, json: async () => ({}), text: async () => "{}" }; } });
    await api.evidenceReview("p1", "income_statement"); await api.openEvidenceReviewCase({ period_id: "p1" }); await api.verifyEvidenceReviewOutcome("c1", {}); await api.recheckEvidenceReviewCase("c1");
    assert.deepEqual(calls.map((c) => c[0]), ["GET", "POST", "POST", "POST"]);
    assert.match(calls[0][1], /\/evidence-review\/review\?period_id=p1&report=income_statement/);
    assert.match(calls[2][1], /\/evidence-review\/cases\/c1\/verify$/);
  });
});

describe("routing", async () => {
  const { readFileSync } = await import("node:fs");
  const app = readFileSync(new URL("../src/app.js", import.meta.url), "utf8");
  test("the Evidence Vault dispatch does not swallow the Evidence Review route", () => {
    assert.match(app, /name\.startsWith\("evidence"\) && name !== "evidence-review"/);
    assert.match(app, /if \(name === "evidence-review"\) return renderEvidenceReviewPage/);
  });
  test("the route, the menu item and the home group are all present", () => {
    assert.match(app, /\{ path: "\/evidence-review", name: "evidence-review" \}/);
    assert.match(app, /path: "\/evidence-review", label: "Evidence Review"/);
    assert.match(readFileSync(new URL("../src/lib/home.js", import.meta.url), "utf8"), /"\/evidence-review"/);
  });
});

describe("Stage 10: outcome measurement", () => {
  const f = (o = {}) => ({ residual_risk: "Lease may lapse", reopen_criteria: "New unsupported journal", residual_level: "LOW", ...o });
  test("verifyPayload builds the request and fills the defaults", () => {
    const { body } = L.verifyPayload(f({ vnote: " ok ", reopen_if_gaps_above: "2", recheck_after_days: "30" }));
    assert.deepEqual(body, { residual_risk: "Lease may lapse", reopen_criteria: "New unsupported journal", note: "ok", residual_level: "LOW", reopen_if_gaps_above: 2, recheck_after_days: 30 });
    const d = L.verifyPayload(f()).body;
    assert.equal(d.reopen_if_gaps_above, 0); assert.equal(d.recheck_after_days, null);
  });
  test("verifyPayload says what to fix before any request is sent", () => {
    assert.match(L.verifyPayload(f({ residual_risk: " " })).problem, /residual risk/i);
    assert.match(L.verifyPayload(f({ reopen_criteria: "" })).problem, /reopened/i);
    assert.match(L.verifyPayload(f({ residual_level: "" })).problem, /rate/i);
    for (const bad of ["-1", "1.5", "abc"]) assert.match(L.verifyPayload(f({ reopen_if_gaps_above: bad })).problem, /whole number/);
    for (const bad of ["0", "x", "2.5"]) assert.match(L.verifyPayload(f({ recheck_after_days: bad })).problem, /whole number of days/);
  });
  test("rating words, due flag and measurement words", () => {
    assert.equal(L.residualLevelText("MEDIUM"), "Medium"); assert.equal(L.residualLevelText(null), "Not rated");
    assert.equal(L.recheckDue({ status: "VERIFIED", recheck_due_now: true }), true);
    assert.equal(L.recheckDue({ status: "OPEN", recheck_due_now: true }), false);
    assert.equal(L.recheckDue(null), false);
    assert.equal(L.measurementText("REJECTED_ATTEMPT"), "Rejected attempt");
  });
  test("an ACTION_DONE case shows the rating, threshold and interval fields to an independent verifier", () => {
    const c = kase({ status: "ACTION_DONE", completed_by: "u2", owner: "u2", completion_note: "done" });
    const out = text(page(er({ cases: [c], openCase: "c1" }), "OWNER", "u9"));
    for (const id of ["er-residual_level-c1", "er-reopen_if_gaps_above-c1", "er-recheck_after_days-c1"]) assert.ok(out.includes(id), id);
  });
  test("a verified case shows its rating, next re-check, due notice and measurements", () => {
    const c = kase({ status: "VERIFIED", recheck_due: "2026-11-01", recheck_due_now: true,
      outcome: { result: "RESOLVED", baseline_gaps: 1, post_gaps: 0, residual_risk: "Lease may lapse", residual_level: "MEDIUM", reopen_criteria: "New gap", reopen_if_gaps_above: 2 },
      measurements: [{ kind: "BASELINE", at: "2026-10-01T09:00:00", gaps: 1 }, { kind: "VERIFIED", at: "2026-10-02T09:00:00", gaps: 0 }] });
    const out = text(page(er({ cases: [c], openCase: "c1" })));
    assert.ok(out.includes("Medium")); assert.ok(out.includes("more than 2 gap(s)")); assert.ok(out.includes("Next re-check: 2026-11-01"));
    assert.ok(out.includes("data-recheck-due")); assert.ok(out.includes("data-measurements"));
  });
  test("no due notice when it is not due", () => {
    const c = kase({ status: "VERIFIED", outcome: { result: "RESOLVED", baseline_gaps: 1, post_gaps: 0, residual_risk: "r", reopen_criteria: "c" } });
    assert.ok(!text(page(er({ cases: [c], openCase: "c1" }))).includes("data-recheck-due"));
  });
});
