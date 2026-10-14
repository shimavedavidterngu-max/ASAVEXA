import { test, describe } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { Resilience } from "../src/pages/Resilience.js";
import * as R from "../src/lib/resilience.js";
import { ApiClient } from "../src/api/client.js";
import { PERMISSIONS, can } from "../src/lib/permissions.js";
import { NAV_GROUPS } from "../src/lib/home.js";
import * as E from "../src/lib/entityConfig.js";

const text = (v) => JSON.stringify(v);
const noop = new Proxy({}, { get: () => () => {} });
// people: u1 prepares/proposes/records, u2 prepares too, u3 approves, u9 bystander
const reading = (o = {}) => ({ id: "r1", seq: 1, value: "5", as_of: "2026-02-10", note: "", status: "RECORDED", recorded_by: "u1", recorded_at: "2026-02-10", decided_by: null, decision_note: null, rating: "GREEN", ...o });
const kri = (o = {}) => ({ id: "k1", ref: "KR-001", name: "Overdue invoices", description: "Share of invoices more than 30 days overdue", unit: "%", direction: "HIGHER_IS_WORSE", amber: "10", red: "20", owner_name: "Ada Obi", review_days: 30,
  risk_id: null, risk_ref: null, status: "ACTIVE", proposed_by: "u1", proposed_at: "2026-02-01", decided_by: "u3", decision_note: null, history: [], readings: [], latest: null, rating: null, stale: true, pending_readings: 0, ...o });
const loss = (o = {}) => ({ id: "e1", ref: "LE-001", title: "Payment sent to the wrong account", description: "A payment went to a supplier with the same name", category: "PROCESS", kind: "LOSS", occurred_on: "2026-02-01", discovered_on: "2026-02-03", amount: "1500.50", currency: "NGN",
  risk_id: null, risk_ref: null, evidence: [], status: "RECORDED", recorded_by: "u1", recorded_at: "2026-02-03", reviewed_by: null, reviewed_on: null, cause: null, lesson: null, void_note: null, history: [], age_days: 2, review_overdue: false, ...o });
const proc = (o = {}) => ({ id: "p1", ref: "BP-001", name: "Payroll processing", description: "Monthly payroll calculation and payment", owner_name: "Ben Eze", rto_hours: 24, rpo_hours: 4, impacts: { financial: "HIGH", legal: "MEDIUM", reputation: "LOW" },
  criticality: "HIGH", dependencies: "", status: "PROPOSED", proposed_by: "u1", decided_by: null, decision_note: null, history: [], drills: 0, last_tested_on: null, last_result: null, drill_due: false, ...o });
const drill = (o = {}) => ({ id: "d1", ref: "DR-001", process_id: "p1", process_ref: "BP-001", process_name: "Payroll processing", drill_type: "FAILOVER", scenario: "The payroll server is lost", performed_on: "2026-02-10", rto_hours: 24, rpo_hours: 4,
  achieved_recovery_hours: 12, achieved_data_loss_hours: 2, rto_met: true, rpo_met: true, result: "MET", outcome: "Backup site took over", follow_up: "", evidence: [], status: "RECORDED", recorded_by: "u2", decided_by: null, decision_note: null, history: [], ...o });
const ovw = () => ({ counts: { kris_active: 2, kris_red: 1, kris_amber: 0, kris_green: 1, losses: 1, near_misses: 0, processes_approved: 1, processes_high: 1, drills_approved: 0 }, loss_totals: [{ currency: "NGN", total: "1500.50" }],
  attention: [{ kind: "KRIS_RED", count: 1, text: "indicator(s) are red on their latest confirmed reading." }], policy: { drill_days: 365, loss_review_days: 14, meaning: "A process not tested for 365 days is flagged as due." }, limitations: ["ASAVEXA measures nothing."] });
const state = (o = {}) => ({ tab: "overview", options: { risks: [{ id: "r9", ref: "R-001", title: "Late payment" }] }, ov: ovw(), kris: [kri()], losses: [loss()], processes: [proc()], drills: [drill()], sel: { kri: null, loss: null }, vault: [],
  forms: { ...JSON.parse(JSON.stringify(R.EMPTY)), review: { cause: "", lesson: "" }, policy: R.policyForm(ovw().policy) }, notes: {}, formError: null, busy: false, error: null, notice: null, ...o });
const page = (o = {}, role = "OWNER", me = "u9") => Resilience({ rs: state(o), role, userId: me, loading: false, onRetry() {}, actions: noop });

describe("permissions", () => {
  test("roles follow the IT-audit pattern and everyone who can act can view", () => {
    for (const r of ["OWNER", "ADMINISTRATOR", "MANAGER", "AUDITOR"]) assert.ok(R.canPrepare(r), r);
    for (const r of ["OWNER", "APPROVER", "MANAGER"]) assert.ok(R.canApprove(r), r);
    for (const r of ["ACCOUNTANT", "REVIEWER", "EXTERNAL_AUDITOR", "READ_ONLY", "DONOR", "REGULATOR", "INVESTOR_REVIEWER"]) assert.ok(!R.canPrepare(r) && !R.canApprove(r), r);
    for (const r of ["OWNER", "ADMINISTRATOR", "MANAGER", "AUDITOR", "APPROVER"]) assert.ok(R.canRead(r), r);
    assert.equal(PERMISSIONS.RESIL_PREPARE, "resilience:prepare"); assert.ok(!can("ACCOUNTANT", PERMISSIONS.AUDIT_READ));
  });
});

describe("payload builders", () => {
  test("indicator", () => {
    const k = { ...R.EMPTY.kri, name: "Overdue invoices", description: "Share of invoices overdue", unit: "%", amber: "10", red: "20", owner_name: "Ada Obi" };
    assert.deepEqual(R.kriPayload(k).body.review_days, 30); assert.match(R.kriPayload({ ...k, amber: "x" }).problem, /amber threshold/); assert.match(R.kriPayload({ ...k, red: "1.23456" }).problem, /4 decimal/);
    assert.match(R.kriPayload({ ...k, review_days: "0" }).problem, /1 to 365/); assert.match(R.kriPayload({ ...k, name: "abc" }).problem, /name/); assert.equal(R.kriPayload({ ...k, risk_id: "r9" }).body.risk_id, "r9"); assert.ok(!("risk_id" in R.kriPayload(k).body));
    assert.ok(R.kriPayload({ ...k, amber: "-5", red: "-1" }).body);
  });
  test("reading", () => {
    assert.deepEqual(R.readingPayload({ value: "12.5", as_of: "2026-02-10", note: "" }).body, { value: "12.5", as_of: "2026-02-10" }); assert.match(R.readingPayload({ value: "", as_of: "2026-02-10" }).problem, /reading/);
    assert.match(R.readingPayload({ value: "5", as_of: "2026-02-31" }).problem, /real date/); assert.match(R.readingPayload({ value: "5", as_of: "2026-02-10", note: "tiny" }).problem, /5 characters/);
  });
  test("loss: near miss has no amount; loss needs amount and currency; dates in order", () => {
    const l = { ...R.EMPTY.loss, title: "Payment to wrong account", description: "A payment went to the wrong supplier", occurred_on: "2026-02-01", discovered_on: "2026-02-03", amount: "1,500.5", currency: "ngn" };
    const b = R.lossPayload(l).body; assert.equal(b.amount, "1500.5"); assert.equal(b.currency, "NGN");
    assert.match(R.lossPayload({ ...l, amount: "1.234" }).problem, /2 decimal/); assert.match(R.lossPayload({ ...l, amount: "0" }).problem, /more than zero/); assert.match(R.lossPayload({ ...l, currency: "NG" }).problem, /three-letter/);
    assert.match(R.lossPayload({ ...l, discovered_on: "2026-01-01" }).problem, /before it happened/);
    const n = R.lossPayload({ ...l, kind: "NEAR_MISS", amount: "", currency: "" }).body; assert.ok(!("amount" in n) && !("currency" in n));
  });
  test("review, process, drill, policy", () => {
    assert.match(R.reviewPayload({ cause: "short", lesson: "x".repeat(25) }).problem, /cause/); assert.match(R.reviewPayload({ cause: "The names matched", lesson: "short" }).problem, /20/); assert.ok(R.reviewPayload({ cause: "The names matched", lesson: "x".repeat(25) }).body);
    const p = { ...R.EMPTY.process, name: "Payroll processing", description: "Monthly payroll run", owner_name: "Ben Eze", rto_hours: "24", rpo_hours: "0" };
    assert.equal(R.processPayload(p).body.rpo_hours, 0); assert.match(R.processPayload({ ...p, rto_hours: "0" }).problem, /1 to 8760/); assert.match(R.processPayload({ ...p, rpo_hours: "-1" }).problem, /0 to 8760/); assert.ok(!("dependencies" in R.processPayload(p).body));
    const d = { ...R.EMPTY.drill, process_id: "p1", scenario: "The payroll server is lost", performed_on: "2026-02-10", achieved_recovery_hours: "12", achieved_data_loss_hours: "2", outcome: "Backup site took over" };
    assert.equal(R.drillPayload(d).body.achieved_recovery_hours, 12); assert.match(R.drillPayload({ ...d, process_id: "" }).problem, /Choose the process/); assert.match(R.drillPayload({ ...d, achieved_recovery_hours: "x" }).problem, /recovery time/);
    assert.match(R.drillPayload({ ...d, follow_up: "short" }).problem, /10 characters/);
    assert.deepEqual(R.policyPayload({ drill_days: "90", loss_review_days: "7" }).body, { drill_days: 90, loss_review_days: 7 }); assert.match(R.policyPayload({ drill_days: "10", loss_review_days: "7" }).problem, /30 to 1095/); assert.match(R.policyPayload({ drill_days: "90", loss_review_days: "0" }).problem, /1 to 90/);
  });
});

describe("who sees which button", () => {
  test("separation of duties in the helpers", () => {
    assert.ok(R.canDecideKri(kri({ status: "PROPOSED" }), "APPROVER", "u3")); assert.ok(!R.canDecideKri(kri({ status: "PROPOSED" }), "OWNER", "u1")); assert.ok(!R.canDecideKri(kri(), "APPROVER", "u3")); assert.ok(!R.canDecideKri(kri({ status: "PROPOSED" }), "AUDITOR", "u3"));
    assert.ok(R.canRetireKri(kri(), "APPROVER")); assert.ok(!R.canRetireKri(kri({ pending_readings: 1 }), "APPROVER")); assert.ok(R.canRecordReading(kri(), "AUDITOR")); assert.ok(!R.canRecordReading(kri({ status: "PROPOSED" }), "AUDITOR")); assert.ok(!R.canRecordReading(kri(), "APPROVER"));
    assert.ok(R.canConfirmReading(reading(), "APPROVER", "u3")); assert.ok(!R.canConfirmReading(reading(), "OWNER", "u1")); assert.ok(!R.canConfirmReading(reading({ status: "CONFIRMED" }), "APPROVER", "u3"));
    assert.ok(R.canReviewLoss(loss(), "APPROVER", "u3")); assert.ok(!R.canReviewLoss(loss(), "OWNER", "u1")); assert.ok(!R.canReviewLoss(loss({ status: "REVIEWED" }), "APPROVER", "u3"));
    assert.ok(R.canDecideProcess(proc(), "APPROVER", "u3")); assert.ok(!R.canDecideProcess(proc(), "OWNER", "u1")); assert.ok(R.canRetireProcess(proc({ status: "APPROVED" }), "APPROVER")); assert.ok(R.canTestProcess(proc({ status: "APPROVED" }), "AUDITOR")); assert.ok(!R.canTestProcess(proc(), "AUDITOR"));
    assert.ok(R.canDecideDrill(drill(), "APPROVER", "u3")); assert.ok(!R.canDecideDrill(drill(), "OWNER", "u2")); assert.ok(!R.canDecideDrill(drill({ status: "APPROVED" }), "APPROVER", "u3"));
    assert.match(R.ownWorkText("recorded this"), /different person must decide/);
  });
  test("wording helpers are exact text", () => {
    assert.equal(R.objectiveText(drill()), "Recovery 12 h against 24 h; data lost 2 h against 4 h."); assert.equal(R.thresholdText(kri()), "Higher is worse: amber at 10, red at 20 %.");
  });
});

describe("page", () => {
  test("overview shows attention, counts, loss totals per currency, settings and limits", () => {
    const t = text(page());
    for (const id of ["rs-attention", "rs-counts", "rs-totals", "rs-policy", "rs-limits", "rs-banner"]) assert.match(t, new RegExp(id)); assert.match(t, /NGN: 1500.50/); assert.match(t, /rs-policy-save/);
    assert.doesNotMatch(text(page({}, "AUDITOR", "u1")), /rs-policy-save/);
  });
  test("indicators: list, propose form for preparers, decision and confirm buttons for a different approver", () => {
    const t = text(page({ tab: "kris" }, "AUDITOR", "u1")); assert.match(t, /KR-001/); assert.match(t, /rs-kri-save/); assert.match(t, /rs-kri-risk/); assert.match(t, /Higher is worse: amber at 10, red at 20/); assert.doesNotMatch(text(page({ tab: "kris" }, "APPROVER", "u3")), /rs-kri-save/);
    const pr = kri({ status: "PROPOSED", stale: false }); const open = (k, role, me) => text(page({ tab: "kris", kris: [k], sel: { kri: k, loss: null } }, role, me));
    assert.match(open(pr, "APPROVER", "u3"), /rs-kri-approve/); assert.match(open(pr, "APPROVER", "u3"), /rs-kri-reject/); assert.match(open(pr, "APPROVER", "u3"), /note-kri-k1/);
    assert.doesNotMatch(open(pr, "OWNER", "u1"), /rs-kri-approve/); assert.match(open(pr, "OWNER", "u1"), /rs-kri-waiting/);
    const act = kri({ readings: [reading()], pending_readings: 1 }); const w = open(act, "APPROVER", "u3"); assert.match(w, /rs-rd-1-confirm/); assert.match(w, /rs-rd-1-reject/); assert.doesNotMatch(w, /rs-kri-retire/); assert.match(w, /rs-retire-hint/);
    assert.doesNotMatch(open(act, "OWNER", "u1"), /rs-rd-1-confirm/); assert.match(open(act, "OWNER", "u1"), /must confirm it/); assert.match(open(act, "AUDITOR", "u2"), /rs-rd-save/);
    assert.match(open(kri(), "APPROVER", "u3"), /rs-kri-retire/);
  });
  test("losses: near miss form hides the amount; review needs a different person; overdue badge", () => {
    const f = JSON.parse(JSON.stringify(R.EMPTY)); f.loss.kind = "NEAR_MISS";
    const t = text(page({ tab: "losses", forms: { ...state().forms, loss: f.loss } }, "AUDITOR", "u2")); assert.doesNotMatch(t, /rs-loss-amount/); assert.match(text(page({ tab: "losses" }, "AUDITOR", "u2")), /rs-loss-amount/);
    const open = (e, role, me) => text(page({ tab: "losses", losses: [e], sel: { kri: null, loss: e } }, role, me));
    const a = open(loss(), "APPROVER", "u3"); assert.match(a, /rs-loss-review/); assert.match(a, /rs-loss-void/); assert.match(a, /rs-rev-cause/); assert.match(a, /rs-rev-lesson/);
    assert.doesNotMatch(open(loss(), "OWNER", "u1"), /rs-loss-review/); assert.match(open(loss(), "OWNER", "u1"), /rs-loss-waiting/);
    assert.match(text(page({ tab: "losses", losses: [loss({ review_overdue: true })] }, "AUDITOR", "u2")), /Review overdue/); assert.match(text(page({ tab: "losses", losses: [loss({ kind: "NEAR_MISS", amount: null, currency: null })] }, "AUDITOR", "u2")), /near miss/);
  });
  test("processes: approve for a different approver, retire when approved, tested/never-tested badges", () => {
    const t = text(page({ tab: "processes" }, "APPROVER", "u3")); assert.match(t, /rs-proc-BP-001-approve/); assert.match(t, /rs-proc-BP-001-reject/); assert.doesNotMatch(t, /rs-proc-save/);
    assert.doesNotMatch(text(page({ tab: "processes" }, "OWNER", "u1")), /rs-proc-BP-001-approve/); assert.match(text(page({ tab: "processes" }, "OWNER", "u1")), /must decide it/); assert.match(text(page({ tab: "processes" }, "AUDITOR", "u2")), /rs-proc-save/);
    const ap = proc({ status: "APPROVED", drill_due: true }); assert.match(text(page({ tab: "processes", processes: [ap] }, "APPROVER", "u3")), /rs-proc-BP-001-retire/); assert.match(text(page({ tab: "processes", processes: [ap] }, "APPROVER", "u3")), /Never tested/);
    assert.match(text(page({ tab: "processes", processes: [proc({ status: "APPROVED", drill_due: false, last_tested_on: "2026-02-10", last_result: "MET", drills: 1 })] }, "APPROVER", "u3")), /Objective met/);
  });
  test("tests: record form needs an approved process; approve/reject for a different approver; shows objectives", () => {
    const ap = proc({ status: "APPROVED" });
    assert.match(text(page({ tab: "drills", processes: [ap] }, "AUDITOR", "u2")), /rs-dr-save/); assert.match(text(page({ tab: "drills" }, "AUDITOR", "u2")), /No approved process is waiting/); assert.doesNotMatch(text(page({ tab: "drills", processes: [ap] }, "APPROVER", "u3")), /rs-dr-save/);
    const t = text(page({ tab: "drills" }, "APPROVER", "u3")); assert.match(t, /rs-drill-DR-001-approve/); assert.match(t, /rs-drill-DR-001-reject/); assert.match(t, /Recovery 12 h against 24 h/); assert.doesNotMatch(text(page({ tab: "drills" }, "APPROVER", "u2")), /rs-drill-DR-001-approve/);
    assert.match(text(page({ tab: "drills" }, "APPROVER", "u2")), /must decide it/);
    const miss = drill({ result: "NOT_MET", rto_met: false, achieved_recovery_hours: 30, follow_up: "Buy a second backup line" }); const m = text(page({ tab: "drills", drills: [miss] }, "APPROVER", "u3")); assert.match(m, /Objective not met/); assert.match(m, /Follow-up: Buy a second backup line/); assert.match(m, /this test missed its objective/);
  });
  test("errors, notices, loading, form problems", () => {
    assert.match(text(page({ error: "Boom" })), /Boom/); assert.match(text(page({ notice: "Saved." })), /rs-notice/);
    assert.match(text(Resilience({ rs: state(), role: "OWNER", userId: "u1", loading: true, onRetry() {}, actions: noop })), /Loading|loading/i);
    assert.match(text(page({ tab: "kris", formError: { form: "kri", text: "Name it." } }, "OWNER", "u1")), /kri-problem/);
  });
  test("every tab renders for every role and person without throwing", () => {
    const full = { kris: [kri({ readings: [reading(), reading({ id: "r2", seq: 2, status: "CONFIRMED", rating: "RED", note: "Late payers" })], latest: reading({ status: "CONFIRMED", rating: "RED" }), rating: "RED", pending_readings: 1 }), kri({ id: "k2", ref: "KR-002", status: "PROPOSED" })],
      losses: [loss(), loss({ id: "e2", ref: "LE-002", status: "REVIEWED", cause: "x".repeat(12), lesson: "y".repeat(22) }), loss({ id: "e3", ref: "LE-003", kind: "NEAR_MISS", amount: null, currency: null, status: "VOIDED", void_note: "Entered twice" })],
      processes: [proc(), proc({ id: "p2", ref: "BP-002", status: "APPROVED", drill_due: true }), proc({ id: "p3", ref: "BP-003", status: "RETIRED", decision_note: "Outsourced" })], drills: [drill(), drill({ id: "d2", ref: "DR-002", status: "APPROVED", result: "NOT_MET", follow_up: "Fix it later" })] };
    for (const role of ["OWNER", "ADMINISTRATOR", "ACCOUNTANT", "FINANCE_OFFICER", "APPROVER", "REVIEWER", "MANAGER", "AUDITOR", "EXTERNAL_AUDITOR", "READ_ONLY"]) for (const me of ["u1", "u2", "u3", "u9"]) for (const [tab] of R.TABS)
      for (const o of [{}, full, { ...full, sel: { kri: full.kris[0], loss: full.losses[0] } }, { ...full, sel: { kri: full.kris[1], loss: full.losses[1] } }]) assert.doesNotThrow(() => page({ tab, ...o }, role, me), `${role}/${me}/${tab}`);
  });
});

describe("wiring", () => {
  test("client calls the right paths and verbs", async () => {
    const calls = []; const c = new ApiClient("http://x"); c._request = async (m, p, o) => { calls.push([m, p, o && o.body]); return {}; };
    await c.rsOverview(); await c.setRsPolicy({ drill_days: 90 }); await c.rsKris(); await c.rsKri("k/1"); await c.proposeRsKri({}); await c.approveRsKri("k1", "ok"); await c.rejectRsKri("k1", "Not agreed"); await c.retireRsKri("k1", "Not used");
    await c.recordRsReading("k1", {}); await c.confirmRsReading("k1", "r1"); await c.rejectRsReading("k1", "r1", "Wrong day"); await c.rsLosses(); await c.rsLoss("e1"); await c.recordRsLoss({}); await c.reviewRsLoss("e1", {}); await c.voidRsLoss("e1", "Twice");
    await c.rsProcesses(); await c.proposeRsProcess({}); await c.approveRsProcess("p1", "ok"); await c.rejectRsProcess("p1", "No"); await c.retireRsProcess("p1", "Gone"); await c.rsDrills(); await c.recordRsDrill({}); await c.approveRsDrill("d1", "ok"); await c.rejectRsDrill("d1", "Mismatch");
    assert.deepEqual(calls.map((x) => x.slice(0, 2)), [["GET", "/resilience/overview"], ["PUT", "/resilience/policy"], ["GET", "/resilience/kris"], ["GET", "/resilience/kris/k%2F1"], ["POST", "/resilience/kris"], ["POST", "/resilience/kris/k1/approve"],
      ["POST", "/resilience/kris/k1/reject"], ["POST", "/resilience/kris/k1/retire"], ["POST", "/resilience/kris/k1/readings"], ["POST", "/resilience/kris/k1/readings/r1/confirm"], ["POST", "/resilience/kris/k1/readings/r1/reject"],
      ["GET", "/resilience/losses"], ["GET", "/resilience/losses/e1"], ["POST", "/resilience/losses"], ["POST", "/resilience/losses/e1/review"], ["POST", "/resilience/losses/e1/void"], ["GET", "/resilience/processes"], ["POST", "/resilience/processes"],
      ["POST", "/resilience/processes/p1/approve"], ["POST", "/resilience/processes/p1/reject"], ["POST", "/resilience/processes/p1/retire"], ["GET", "/resilience/drills"], ["POST", "/resilience/drills"], ["POST", "/resilience/drills/d1/approve"], ["POST", "/resilience/drills/d1/reject"]]);
    assert.deepEqual(calls[5][2], { note: "ok" }); assert.deepEqual(calls[6][2], { reason: "Not agreed" }); assert.deepEqual(calls[10][2], { reason: "Wrong day" }); assert.deepEqual(calls[15][2], { reason: "Twice" }); assert.deepEqual(calls[23][2], { note: "ok" });
  });
  test("the page is in the menu behind audit:read, in the workspaces group, searchable, and can be hidden by organisation set-up", () => {
    assert.ok(NAV_GROUPS.find((g) => g.id === "workspaces").paths.includes("/resilience"));
    const app = fs.readFileSync(new URL("../src/app.js", import.meta.url), "utf8");
    assert.match(app, /path: "\/resilience", label: "Risk indicators and resilience", permission: PERMISSIONS\.AUDIT_READ/); assert.match(app, /path: "\/resilience", name: "resilience"/); assert.match(app, /renderResiliencePage\(authState\)/);
    assert.match(app, /uiState\.rs = null; loadedOnce\.delete\("rsLoading"\)/);
    assert.equal(E.WORKSPACE_PATHS.resilience, "/resilience"); assert.deepEqual(E.filterNavByWorkspaces([{ path: "/resilience" }, { path: "/fpa" }], ["fpa"]).map((i) => i.path), ["/fpa"]);
  });
  test("the page uses only the shared client and no fetch or float arithmetic", () => {
    const src = fs.readFileSync(new URL("../src/pages/Resilience.js", import.meta.url), "utf8") + fs.readFileSync(new URL("../src/lib/resilience.js", import.meta.url), "utf8");
    assert.doesNotMatch(src, /fetch\(|XMLHttpRequest|parseFloat|toFixed/);
  });
});
