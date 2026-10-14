import { test, describe } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { ItAudit } from "../src/pages/ItAudit.js";
import * as I from "../src/lib/itaudit.js";
import { ApiClient } from "../src/api/client.js";
import { PERMISSIONS, can } from "../src/lib/permissions.js";
import { NAV_GROUPS } from "../src/lib/home.js";
import * as E from "../src/lib/entityConfig.js";

const text = (v) => JSON.stringify(v);
const noop = new Proxy({}, { get: () => () => {} });
// people: u1 recorded the changes and defined the control, u2 tests, u3 approves, u9 bystander
const change = (o = {}) => ({ id: "c1", ref: "CH-001", system: "Payroll", asset_id: null, asset_name: null, title: "Update tax tables", description: "Applied the new tax tables", change_type: "NORMAL", risk: "LOW", requested_by: "Ada", approved_by_name: "Ben",
  approved_on: "2026-02-01", ticket_ref: "CHG-1", implemented_on: "2026-02-03", testing_evidence: "Tested", rollback_plan: "Restore", evidence: [], ratify_days: 5, status: "RECORDED", recorded_by: "u1", recorded_at: "2026-02-03", void_note: null, history: [], flags: [], flag_texts: [], ...o });
const control = (o = {}) => ({ id: "k1", ref: "AC-001", system: "Payroll", asset_id: null, asset_name: null, name: "Duplicate payee check", control_type: "INPUT_VALIDATION", description: "Rejects duplicates", expected_result: "Rejected", frequency: "CONTINUOUS", tolerable: 0,
  status: "ACTIVE", created_by: "u1", created_at: "2026-02-01", retire_note: null, history: [], tests: 0, last_tested_on: null, last_conclusion: null, retest_due: true, ...o });
const item = (o = {}) => ({ id: "i1", change_id: "c1", ref: "CH-001", snapshot: { system: "Payroll", title: "Update tax tables", change_type: "NORMAL", risk: "LOW", requested_by: "Ada", approved_by_name: "Ben", approved_on: "2026-02-01", ticket_ref: "CHG-1", implemented_on: "2026-02-03", recorded_by: "u1" },
  flags: [], result: null, note: null, overrode_flags: false, concluded_by: null, ...o });
const ctest = (o = {}) => ({ id: "t1", ref: "TS-001", kind: "CHANGE", title: "February change test", status: "DRAFT", prepared_by: "u2", prepared_at: "2026-02-15", approved_by: null, approved_on: null, conclusion: null, approval_note: null, rejected_note: null, history: [], system: null,
  period_from: "2026-02-01", period_to: "2026-02-14", sample_size: 3, seed: "feb", tolerable: 0, population_count: 4, population_fingerprint: "a".repeat(64), items: [item()], control_id: null, control_ref: null, cases: [], concluded: 0, exceptions: 0, overrides: 0, ...o });
const ktest = (o = {}) => ctest({ kind: "CONTROL", period_from: null, period_to: null, sample_size: null, seed: null, population_count: null, population_fingerprint: null, items: [], control_id: "k1", control_ref: "AC-001", control_name: "Duplicate payee check", control_expected: "Rejected", control_created_by: "u1",
  cases: [], ...o });
const caseRec = (o = {}) => ({ id: "x1", seq: 1, description: "Entered a duplicate payee", expected: "Rejected", actual: "Rejected", result: "PASS", note: "", performed_on: "2026-02-14", evidence: [], recorded_by: "u2", ...o });
const ovw = () => ({ counts: { changes: 2, changes_live: 2, changes_flagged: 1, changes_by_type: { STANDARD: 0, NORMAL: 2, EMERGENCY: 0 }, controls: 1, controls_active: 1, tests: 1, tests_approved: 0 },
  attention: [{ kind: "CONTROLS_NEVER_TESTED", count: 1, text: "active control(s) have never been tested." }], policy: { emergency_ratify_days: 5, retest_days: 365, meaning: "An emergency change should be approved within 5 days." }, limitations: ["ASAVEXA records what people type in."] });
const state = (o = {}) => ({ tab: "overview", options: { assets: [{ id: "a1", ref: "AS-001", name: "Payroll server" }] }, ov: ovw(), changes: [change(), change({ id: "c2", ref: "CH-002", flags: ["NO_APPROVAL"], approved_by_name: null, approved_on: null })], controls: [control()], tests: [ctest()],
  sel: { test: null }, vault: [], flaggedOnly: false, forms: { ...JSON.parse(JSON.stringify(I.EMPTY)), policy: I.policyForm(ovw().policy) }, notes: {}, formError: null, busy: false, error: null, notice: null, ...o });
const page = (o = {}, role = "OWNER", me = "u9") => ItAudit({ ia: state(o), role, userId: me, loading: false, onRetry() {}, actions: noop });
const open = (t, o = {}) => ({ tab: "tests", tests: [t], sel: { test: t }, ...o });

describe("permissions", () => {
  test("roles follow the cyber pattern and everyone who can act can view", () => {
    for (const r of ["OWNER", "ADMINISTRATOR", "MANAGER", "AUDITOR"]) assert.ok(I.canPrepare(r), r);
    for (const r of ["OWNER", "APPROVER", "MANAGER"]) assert.ok(I.canApprove(r), r);
    for (const r of ["ACCOUNTANT", "REVIEWER", "EXTERNAL_AUDITOR", "READ_ONLY", "DONOR", "REGULATOR", "INVESTOR_REVIEWER"]) assert.ok(!I.canPrepare(r) && !I.canApprove(r), r);
    for (const r of ["OWNER", "ADMINISTRATOR", "MANAGER", "AUDITOR", "APPROVER"]) assert.ok(I.canRead(r), r);
    assert.equal(PERMISSIONS.ITAUDIT_PREPARE, "itaudit:prepare"); assert.ok(!can("ACCOUNTANT", PERMISSIONS.AUDIT_READ));
  });
});

describe("payload builders", () => {
  const f = (o = {}) => ({ ...I.EMPTY.change, system: "Payroll", title: "Update tax tables", description: "Applied the new tax tables", requested_by: "Ada", ticket_ref: "CHG-1", implemented_on: "2026-02-03", ...o });
  test("change: valid, optional approval pair, dates, optional text minimums", () => {
    assert.deepEqual(I.changePayload(f()).body.evidence_ids, []);
    assert.equal(I.changePayload(f({ approved_by_name: "Ben" })).problem, "Give both who approved the change and when, or neither.");
    assert.match(I.changePayload(f({ approved_by_name: "Ben", approved_on: "2026-02-30" })).problem, /real date/);
    assert.match(I.changePayload(f({ implemented_on: "" })).problem, /go-live date/);
    assert.match(I.changePayload(f({ testing_evidence: "short" })).problem, /Testing evidence needs|testing evidence needs/i);
    assert.match(I.changePayload(f({ title: "abc" })).problem, /title/); assert.equal(I.changePayload(f({ asset_id: "a1", evidence_id: "e1" })).body.asset_id, "a1");
  });
  test("control, change test and control test", () => {
    const c = { ...I.EMPTY.control, system: "Payroll", name: "Duplicate payee check", description: "Rejects duplicates", expected_result: "Rejected" };
    assert.equal(I.controlPayload(c).body.tolerable, 0); assert.match(I.controlPayload({ ...c, tolerable: "21" }).problem, /0 to 20/); assert.match(I.controlPayload({ ...c, name: "abc" }).problem, /name/);
    const p = { ...I.EMPTY.ptest, title: "February test", period_from: "2026-02-01", period_to: "2026-02-14", seed: "feb" };
    assert.equal(I.ptestPayload(p).body.sample_size, 5); assert.match(I.ptestPayload({ ...p, period_to: "2026-01-01" }).problem, /cannot end before/); assert.match(I.ptestPayload({ ...p, sample_size: "0" }).problem, /1 to 100/);
    assert.match(I.ptestPayload({ ...p, seed: "a" }).problem, /seed/); assert.ok(!("system" in I.ptestPayload(p).body));
    assert.match(I.ctestPayload({ title: "Test the control", control_id: "" }).problem, /Choose the control/); assert.deepEqual(I.ctestPayload({ title: "Test the control", control_id: "k1" }).body, { title: "Test the control", control_id: "k1" });
  });
  test("case and item rules match the server", () => {
    const c = { ...I.EMPTY.case, description: "Entered a duplicate payee", expected: "Rejected", actual: "Rejected", performed_on: "2026-02-14" };
    assert.ok(I.casePayload(c).body); assert.match(I.casePayload({ ...c, result: "FAIL" }).problem, /failure/); assert.match(I.casePayload({ ...c, note: "tiny" }).problem, /note needs/i);
    assert.match(I.itemPayload("NO_EXCEPTION", "short", true).problem, /20 characters/); assert.ok(I.itemPayload("NO_EXCEPTION", "Approval email filed under the ticket", true).body);
    assert.match(I.itemPayload("EXCEPTION", "", false).problem, /10 characters/); assert.deepEqual(I.itemPayload("NO_EXCEPTION", "", false).body, { result: "NO_EXCEPTION" }); assert.match(I.itemPayload("NO_EXCEPTION", "tiny", false).problem, /5 characters/);
  });
  test("policy", () => {
    assert.deepEqual(I.policyPayload({ emergency_ratify_days: "2", retest_days: "90" }).body, { emergency_ratify_days: 2, retest_days: 90 });
    assert.match(I.policyPayload({ emergency_ratify_days: "61", retest_days: "90" }).problem, /0 to 60/); assert.match(I.policyPayload({ emergency_ratify_days: "2", retest_days: "10" }).problem, /30 to 1095/);
  });
});

describe("who sees which button", () => {
  test("void and retire need an approver; a recorder cannot void their own record", () => {
    assert.ok(I.canVoid(change(), "APPROVER", "u3")); assert.ok(!I.canVoid(change(), "APPROVER", "u1")); assert.ok(!I.canVoid(change({ status: "VOIDED" }), "APPROVER", "u3")); assert.ok(!I.canVoid(change(), "AUDITOR", "u3"));
    assert.ok(I.canRetire(control(), "APPROVER")); assert.ok(!I.canRetire(control({ status: "RETIRED" }), "APPROVER")); assert.ok(!I.canRetire(control(), "AUDITOR"));
    assert.ok(I.canTestControl(control(), "AUDITOR", "u2")); assert.ok(!I.canTestControl(control(), "AUDITOR", "u1"));
  });
  test("tester works only their own draft, never their own records", () => {
    const t = ctest(); assert.ok(I.canConclude(t, t.items[0], "AUDITOR", "u2")); assert.ok(!I.canConclude(t, t.items[0], "AUDITOR", "u1")); assert.ok(!I.canConclude(t, t.items[0], "AUDITOR", "u3"));
    assert.ok(!I.canConclude(ctest({ status: "SUBMITTED" }), t.items[0], "AUDITOR", "u2")); assert.ok(!I.canSubmit(t, "AUDITOR", "u2")); assert.match(I.testBlockers(t, "AUDITOR", "u2"), /1 sampled change/);
    const done = ctest({ items: [item({ result: "NO_EXCEPTION" })] }); assert.ok(I.canSubmit(done, "AUDITOR", "u2")); assert.equal(I.testBlockers(done, "AUDITOR", "u2"), "");
    const k = ktest(); assert.ok(I.canAddCase(k, "AUDITOR", "u2")); assert.ok(!I.canSubmit(k, "AUDITOR", "u2")); assert.ok(I.canSubmit(ktest({ cases: [caseRec()] }), "AUDITOR", "u2"));
  });
  test("approval moves exclude the tester, the recorder of a sampled change and the control's definer", () => {
    const s = ctest({ status: "SUBMITTED", items: [item({ result: "NO_EXCEPTION" })] });
    assert.deepEqual(I.approveMoves(s, "APPROVER", "u3"), ["approve", "reject"]); assert.deepEqual(I.approveMoves(s, "APPROVER", "u2"), []); assert.deepEqual(I.approveMoves(s, "APPROVER", "u1"), []); assert.deepEqual(I.approveMoves(s, "AUDITOR", "u3"), []);
    const k = ktest({ status: "SUBMITTED", cases: [caseRec()] }); assert.deepEqual(I.approveMoves(k, "APPROVER", "u3"), ["approve", "reject"]); assert.deepEqual(I.approveMoves(k, "APPROVER", "u1"), []);
    assert.match(I.waitingText(s, "APPROVER", "u2"), /carried out this test/); assert.match(I.waitingText(s, "APPROVER", "u1"), /recorded one of the sampled/); assert.match(I.waitingText(k, "APPROVER", "u1"), /defined this control/); assert.equal(I.waitingText(s, "APPROVER", "u3"), "");
    assert.ok(I.needsApprovalNote(ctest({ exceptions: 1 }))); assert.ok(I.needsApprovalNote(ctest({ overrides: 1 }))); assert.ok(!I.needsApprovalNote(ctest()));
  });
});

describe("page", () => {
  test("overview shows attention, counts, settings and limits", () => {
    const t = text(page());
    for (const id of ["ia-attention", "ia-counts", "ia-policy", "ia-limits", "ia-banner"]) assert.match(t, new RegExp(id)); assert.match(t, /ia-policy-save/);
    assert.doesNotMatch(text(page({}, "AUDITOR", "u2")), /ia-policy-save/);
  });
  test("changes: flags shown, filter, void only for another approver, record form only for preparers, linked asset offered", () => {
    const t = text(page({ tab: "changes" }, "APPROVER", "u3")); assert.match(t, /CH-002/); assert.match(t, /No approval recorded/); assert.match(t, /ia-void-CH-001/); assert.doesNotMatch(t, /ia-ch-save/);
    assert.doesNotMatch(text(page({ tab: "changes", flaggedOnly: true }, "APPROVER", "u3")), /data-change":"CH-001"/);
    assert.doesNotMatch(text(page({ tab: "changes" }, "APPROVER", "u1")), /ia-void-CH-001/);
    const p = text(page({ tab: "changes" }, "AUDITOR", "u2")); assert.match(p, /ia-ch-save/); assert.match(p, /ia-ch-asset/); assert.doesNotMatch(p, /ia-void-/);
  });
  test("controls: retest badge, retire for approvers, define form for preparers", () => {
    const t = text(page({ tab: "controls" }, "APPROVER", "u3")); assert.match(t, /Never tested/); assert.match(t, /ia-retire-AC-001/); assert.doesNotMatch(t, /ia-ct-save/);
    assert.match(text(page({ tab: "controls" }, "AUDITOR", "u2")), /ia-ct-save/);
  });
  test("tests: tester sees item buttons and submit once all concluded; approver sees approve/send back with a note box", () => {
    const t = ctest(); const w = text(page(open(t), "AUDITOR", "u2")); assert.match(w, /ia-item-CH-001-ok/); assert.match(w, /ia-item-CH-001-exc/); assert.match(w, /ia-blocked/); assert.doesNotMatch(w, /ia-test-submit/); assert.match(w, /ia-sample-info/);
    assert.doesNotMatch(text(page(open(t), "AUDITOR", "u1")), /ia-item-CH-001-ok/); const own = ctest({ prepared_by: "u1" }); assert.doesNotMatch(text(page(open(own), "AUDITOR", "u1")), /ia-item-CH-001-ok/); assert.match(text(page(open(own), "AUDITOR", "u1")), /cannot test it/);
    assert.match(text(page(open(ctest({ items: [item({ result: "NO_EXCEPTION" })] })), "AUDITOR", "u2")), /ia-test-submit/);
    const s = ctest({ status: "SUBMITTED", items: [item({ result: "NO_EXCEPTION" })] }); const a = text(page(open(s), "APPROVER", "u3")); assert.match(a, /ia-test-approve/); assert.match(a, /ia-test-reject/); assert.match(a, /note-test-t1/);
    assert.doesNotMatch(text(page(open(s), "OWNER", "u2")), /ia-test-approve/); assert.match(text(page(open(s), "OWNER", "u2")), /ia-waiting/);
  });
  test("the planner can withdraw a draft; nobody else can; a withdrawn test says so", () => {
    const w = text(page(open(ctest()), "AUDITOR", "u2")); assert.match(w, /ia-test-withdraw/); assert.match(w, /note-wd-t1/);
    assert.doesNotMatch(text(page(open(ctest()), "AUDITOR", "u1")), /ia-test-withdraw/); assert.doesNotMatch(text(page(open(ctest({ status: "SUBMITTED" })), "AUDITOR", "u2")), /ia-test-withdraw/);
    const x = text(page(open(ctest({ status: "WITHDRAWN", rejected_note: "Planned by mistake" })), "AUDITOR", "u2")); assert.match(x, /ia-withdrawn/); assert.doesNotMatch(x, /ia-test-withdraw/);
  });
  test("control test: case form, tolerance text and result", () => {
    const k = ktest({ cases: [caseRec({ result: "FAIL", note: "Accepted a duplicate" })], exceptions: 1, concluded: 1 }); const w = text(page(open(k), "AUDITOR", "u2")); assert.match(w, /ia-cs-save/); assert.match(w, /1 exception\(s\) found; 0 tolerable/); assert.match(w, /Accepted a duplicate/);
    const done = ktest({ status: "APPROVED", conclusion: "ABOVE_TOLERANCE", approved_by: "u3", approved_on: "2026-02-16", cases: k.cases, exceptions: 1 }); const d = text(page(open(done), "APPROVER", "u3")); assert.match(d, /Above tolerance/); assert.doesNotMatch(d, /ia-cs-save/);
  });
  test("sent-back note, errors, notices, loading, form problems", () => {
    assert.match(text(page(open(ctest({ rejected_note: "Please add the email" }), {}), "AUDITOR", "u2")), /ia-sent-back/);
    assert.match(text(page({ error: "Boom" })), /Boom/); assert.match(text(page({ notice: "Saved." })), /ia-notice/);
    assert.match(text(ItAudit({ ia: state(), role: "OWNER", userId: "u1", loading: true, onRetry() {}, actions: noop })), /Loading|loading/i);
    assert.match(text(page({ tab: "changes", formError: { form: "change", text: "Say what changed." } }, "OWNER", "u1")), /change-problem/);
  });
  test("every tab renders for every role and person without throwing", () => {
    const sub = ctest({ status: "SUBMITTED", items: [item({ result: "EXCEPTION", note: "No testing evidence" })], exceptions: 1, concluded: 1 });
    const apr = ktest({ status: "APPROVED", conclusion: "WITHIN_TOLERANCE", approved_by: "u3", approved_on: "2026-02-16", cases: [caseRec()], concluded: 1 });
    for (const role of ["OWNER", "ADMINISTRATOR", "ACCOUNTANT", "FINANCE_OFFICER", "APPROVER", "REVIEWER", "MANAGER", "AUDITOR", "EXTERNAL_AUDITOR", "READ_ONLY"]) for (const me of ["u1", "u2", "u3", "u9"]) for (const [tab] of I.TABS)
      for (const t of [null, ctest(), sub, ktest(), apr]) assert.doesNotThrow(() => page({ tab, tests: t ? [t] : [], sel: { test: t } }, role, me), `${role}/${me}/${tab}`);
  });
});

describe("wiring", () => {
  test("client calls the right paths and verbs", async () => {
    const calls = []; const c = new ApiClient("http://x"); c._request = async (m, p, o) => { calls.push([m, p, o && o.body]); return {}; };
    await c.iaOverview(); await c.setIaPolicy({ retest_days: 90 }); await c.iaChanges(); await c.recordIaChange({}); await c.voidIaChange("c/1", "Entered in error"); await c.iaControls(); await c.defineIaControl({}); await c.retireIaControl("k1", "No longer used");
    await c.iaTests(); await c.iaTest("t1"); await c.planIaChangeTest({}); await c.planIaControlTest({}); await c.concludeIaItem("t1", "i1", {}); await c.addIaCase("t1", {}); await c.withdrawIaTest("t1", "Planned by mistake"); await c.submitIaTest("t1"); await c.approveIaTest("t1", "ok"); await c.rejectIaTest("t1", "Add the email");
    assert.deepEqual(calls.map((x) => x.slice(0, 2)), [["GET", "/itaudit/overview"], ["PUT", "/itaudit/policy"], ["GET", "/itaudit/changes"], ["POST", "/itaudit/changes"], ["POST", "/itaudit/changes/c%2F1/void"], ["GET", "/itaudit/controls"], ["POST", "/itaudit/controls"],
      ["POST", "/itaudit/controls/k1/retire"], ["GET", "/itaudit/tests"], ["GET", "/itaudit/tests/t1"], ["POST", "/itaudit/tests/change"], ["POST", "/itaudit/tests/control"], ["POST", "/itaudit/tests/t1/items/i1"], ["POST", "/itaudit/tests/t1/cases"],
      ["POST", "/itaudit/tests/t1/withdraw"], ["POST", "/itaudit/tests/t1/submit"], ["POST", "/itaudit/tests/t1/approve"], ["POST", "/itaudit/tests/t1/reject"]]);
    assert.deepEqual(calls[4][2], { reason: "Entered in error" }); assert.deepEqual(calls[14][2], { reason: "Planned by mistake" }); assert.deepEqual(calls[16][2], { note: "ok" }); assert.deepEqual(calls[17][2], { reason: "Add the email" });
  });
  test("the page is in the menu behind audit:read, in the workspaces group, searchable, and can be hidden by organisation set-up", () => {
    assert.ok(NAV_GROUPS.find((g) => g.id === "workspaces").paths.includes("/itaudit"));
    const app = fs.readFileSync(new URL("../src/app.js", import.meta.url), "utf8");
    assert.match(app, /path: "\/itaudit", label: "IT audit", permission: PERMISSIONS\.AUDIT_READ/); assert.match(app, /path: "\/itaudit", name: "itaudit"/); assert.match(app, /renderItAuditPage\(authState\)/);
    assert.match(app, /uiState\.ia = null; loadedOnce\.delete\("iaLoading"\)/);
    assert.equal(E.WORKSPACE_PATHS.itaudit, "/itaudit"); assert.deepEqual(E.filterNavByWorkspaces([{ path: "/itaudit" }, { path: "/fpa" }], ["fpa"]).map((i) => i.path), ["/fpa"]);
  });
  test("the page uses only the shared client and no fetch or float arithmetic", () => {
    const src = fs.readFileSync(new URL("../src/pages/ItAudit.js", import.meta.url), "utf8") + fs.readFileSync(new URL("../src/lib/itaudit.js", import.meta.url), "utf8");
    assert.doesNotMatch(src, /fetch\(|XMLHttpRequest|parseFloat|toFixed/);
  });
});
