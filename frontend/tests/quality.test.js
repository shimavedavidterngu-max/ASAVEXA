import { test, describe } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { Quality } from "../src/pages/Quality.js";
import * as Q from "../src/lib/quality.js";
import { ApiClient } from "../src/api/client.js";
import { NAV_GROUPS } from "../src/lib/home.js";
import * as E from "../src/lib/entityConfig.js";

const text = (v) => JSON.stringify(v);
const noop = new Proxy({}, { get: () => () => {} });
// u1 raises, u2 prepares and completes, u3 approves, u9 bystander
const action = (o = {}) => ({ id: "a1", ref: "CA-001", nc_id: "n1", nc_ref: "NC-001", nc_title: "Late invoices", kind: "CORRECTIVE", description: "Add a weekly invoice check", owner_name: "Ada Obi", due_on: "2026-03-01", status: "OPEN", added_by: "u2", completed_on: null, completed_by: null, completion_note: null,
  evidence: [], checked_by: null, check_note: null, cancel_note: null, overdue: false, check_overdue: false, ...o });
const nc = (o = {}) => ({ id: "n1", ref: "NC-001", title: "Late invoices", description: "Invoices were posted late", source: "PROCESS_CHECK", severity: "MAJOR", area: "Payables", occurred_on: "2026-02-01", discovered_on: "2026-02-03", evidence: [], status: "ANALYSED", raised_by: "u1",
  root_cause: "No owner for the weekly check", containment: "Posted all late invoices by hand", closed_on: null, closing_note: null, no_action_reason: null, void_note: null, history: [{ at: "2026-02-03T10:00:00", event: "RAISED", by: "u1", note: "" }], actions: [action()], age_days: 5, close_problem: "An action is still open.", ...o });
const ovw = () => ({ counts: { open: 1, critical_open: 0, major_open: 1, minor_open: 0, closed: 0, actions_open: 1, actions_verified: 0, actions_not_effective: 0 }, attention: [{ kind: "NCS_WITHOUT_ACTIONS", count: 1, text: "analysed nonconformance(s) have no action yet." }],
  policy: { verify_days: 30, meaning: "An action should be checked within 30 days of completion." }, limitations: ["ASAVEXA inspects and measures nothing."] });
const state = (o = {}) => ({ tab: "overview", options: {}, ov: ovw(), ncs: [nc()], actions: [action()], sel: { nc: null }, vault: [], forms: { ...JSON.parse(JSON.stringify(Q.EMPTY)), policy: Q.policyForm(ovw().policy) }, notes: {}, formError: null, busy: false, error: null, notice: null, ...o });
const page = (o = {}, role = "OWNER", me = "u9") => Quality({ ql: state(o), role, userId: me, loading: false, onRetry() {}, actions: noop });

describe("permissions", () => {
  test("who can prepare and approve", () => {
    for (const r of ["OWNER", "ADMINISTRATOR", "MANAGER", "AUDITOR"]) assert.ok(Q.canPrepare(r), r);
    for (const r of ["OWNER", "APPROVER", "MANAGER"]) assert.ok(Q.canApprove(r), r);
    for (const r of ["ACCOUNTANT", "READ_ONLY", "EXTERNAL_AUDITOR"]) { assert.ok(!Q.canPrepare(r), r); assert.ok(!Q.canApprove(r), r); }
    assert.ok(!Q.canRead("ACCOUNTANT")); assert.ok(Q.canRead("AUDITOR"));
  });
});

describe("payload builders", () => {
  const good = { title: "Late invoices", description: "Invoices were posted late", source: "PROCESS_CHECK", severity: "MAJOR", area: "Payables", occurred_on: "2026-02-01", discovered_on: "2026-02-03", evidence_id: "" };
  test("nonconformance", () => {
    assert.deepEqual(Q.ncPayload(good).body.evidence_ids, []);
    assert.deepEqual(Q.ncPayload({ ...good, evidence_id: "e1" }).body.evidence_ids, ["e1"]);
    for (const bad of [{ title: "abc" }, { description: "short" }, { area: "x" }, { occurred_on: "2026-02-30" }, { discovered_on: "soon" }, { discovered_on: "2026-01-01" }]) assert.ok(Q.ncPayload({ ...good, ...bad }).problem, JSON.stringify(bad));
  });
  test("analysis, action, completion, check", () => {
    assert.ok(Q.analysePayload({ root_cause: "short", containment: "Posted by hand" }).problem);
    assert.ok(Q.analysePayload({ root_cause: "No owner for the weekly check", containment: "x" }).problem);
    assert.ok(Q.analysePayload({ root_cause: "No owner for the weekly check", containment: "Posted by hand" }).body);
    const a = { nc_id: "n1", kind: "CORRECTIVE", description: "Add a weekly invoice check", owner_name: "Ada", due_on: "2026-03-01" };
    assert.ok(Q.actionPayload(a).body); assert.ok(Q.actionPayload({ ...a, nc_id: "" }).problem); assert.ok(Q.actionPayload({ ...a, due_on: "2026-13-01" }).problem);
    assert.ok(Q.completePayload({ completed_on: "2026-03-01", note: "Check added and run once", evidence_id: "" }).body); assert.ok(Q.completePayload({ completed_on: "", note: "Check added and run once" }).problem);
    assert.ok(Q.verifyPayload({ result: "EFFECTIVE", note: "Reviewed four weeks of invoices, none late" }).body); assert.ok(Q.verifyPayload({ result: "EFFECTIVE", note: "ok" }).problem);
  });
  test("closing and settings", () => {
    assert.deepEqual(Q.closePayload({ note: "All actions verified", no_action_reason: "" }).body, { note: "All actions verified" });
    assert.ok(Q.closePayload({ note: "short", no_action_reason: "" }).problem);
    assert.ok(Q.closePayload({ note: "Nothing more needed", no_action_reason: "too short" }).problem);
    assert.equal(Q.closePayload({ note: "Nothing more needed", no_action_reason: "Cosmetic and has no effect on any record" }).body.no_action_reason.length > 19, true);
    assert.equal(Q.policyPayload({ verify_days: "45" }).body.verify_days, 45);
    for (const v of ["6", "181", "x", "", "4.5", "-9"]) assert.ok(Q.policyPayload({ verify_days: v }).problem, v);
  });
});

describe("who sees which button", () => {
  test("separation of duties", () => {
    assert.ok(Q.canAnalyse(nc({ status: "RAISED" }), "AUDITOR")); assert.ok(!Q.canAnalyse(nc(), "AUDITOR")); assert.ok(!Q.canAnalyse(nc({ status: "RAISED" }), "APPROVER"));
    assert.ok(Q.canAddAction(nc(), "MANAGER")); assert.ok(!Q.canAddAction(nc({ status: "RAISED" }), "MANAGER"));
    assert.ok(Q.canClose(nc(), "APPROVER", "u3")); assert.ok(!Q.canClose(nc(), "APPROVER", "u1")); assert.ok(!Q.canClose(nc({ status: "CLOSED" }), "APPROVER", "u3"));
    assert.ok(Q.canVoid(nc({ status: "RAISED" }), "APPROVER", "u3")); assert.ok(!Q.canVoid(nc({ status: "RAISED" }), "APPROVER", "u1")); assert.ok(!Q.canVoid(nc(), "APPROVER", "u3"));
    assert.ok(Q.canComplete(action(), "AUDITOR")); assert.ok(!Q.canComplete(action({ status: "COMPLETED" }), "AUDITOR"));
    const done = action({ status: "COMPLETED", completed_by: "u2" });
    assert.ok(Q.canVerify(done, "APPROVER", "u3")); assert.ok(!Q.canVerify(done, "MANAGER", "u2")); assert.ok(!Q.canVerify(action(), "APPROVER", "u3"));
    assert.ok(Q.canCancel(action(), "APPROVER")); assert.ok(!Q.canCancel(done, "APPROVER"));
  });
});

describe("page", () => {
  test("overview", () => {
    const t = text(page()); for (const id of ["ql-attention", "ql-counts", "ql-policy", "ql-limits", "ql-banner"]) assert.match(t, new RegExp(id));
    assert.match(t, /Open nonconformances: 1/); assert.match(t, /ql-policy-save/); assert.doesNotMatch(text(page({}, "AUDITOR", "u1")), /ql-policy-save/);
  });
  test("nonconformances tab", () => {
    assert.match(text(page({ tab: "ncs" }, "AUDITOR", "u1")), /ql-nc-save/); assert.doesNotMatch(text(page({ tab: "ncs" }, "APPROVER", "u3")), /ql-nc-save/);
    const open = (role, me, o = {}) => text(page({ tab: "ncs", sel: { nc: nc(o) } }, role, me));
    assert.match(open("APPROVER", "u3"), /ql-nc-close/); assert.doesNotMatch(open("APPROVER", "u1"), /ql-nc-close/); assert.match(open("APPROVER", "u1"), /ql-close-waiting/);
    assert.match(open("AUDITOR", "u2", { status: "RAISED", actions: [], close_problem: null }), /ql-nc-analyse/);
    assert.match(open("APPROVER", "u3", { status: "RAISED", actions: [] }), /ql-nc-void/); assert.match(open("APPROVER", "u3"), /ql-close-problem/);
    assert.match(open("APPROVER", "u3", { severity: "MINOR" }), /ql-close-reason/); assert.doesNotMatch(open("APPROVER", "u3"), /ql-close-reason/);
  });
  test("actions tab", () => {
    assert.match(text(page({ tab: "actions" }, "AUDITOR", "u2")), /ql-act-CA-001-complete/);
    const done = { actions: [action({ status: "COMPLETED", completed_by: "u2", completed_on: "2026-03-01", completion_note: "Check added" })] };
    assert.match(text(page({ tab: "actions", ...done }, "APPROVER", "u3")), /ql-act-CA-001-verify/); assert.doesNotMatch(text(page({ tab: "actions", ...done }, "MANAGER", "u2")), /ql-act-CA-001-verify/);
    assert.match(text(page({ tab: "actions" }, "APPROVER", "u3")), /ql-act-CA-001-cancel/); assert.match(text(page({ tab: "actions" }, "AUDITOR", "u2")), /ql-ac-save/);
    assert.match(text(page({ tab: "actions", ncs: [nc({ status: "RAISED" })] }, "AUDITOR", "u2")), /No analysed nonconformance/);
  });
  test("overdue badges and problems show and never print object text", () => {
    const t = text(page({ tab: "actions", actions: [action({ overdue: true, check_overdue: true })], formError: { form: "action", text: "Bad date" } }, "AUDITOR", "u2"));
    assert.match(t, /Overdue/); assert.match(t, /Check overdue/); assert.match(t, /action-problem/); assert.doesNotMatch(t, /object Object/);
    assert.match(text(page({ error: "Boom" })), /Boom/);
  });
  test("every tab, role and person renders", () => {
    const full = { ncs: [nc(), nc({ id: "n2", ref: "NC-002", status: "RAISED", actions: [] }), nc({ id: "n3", ref: "NC-003", status: "CLOSED", closed_on: "2026-03-05", closing_note: "Verified", severity: "MINOR", no_action_reason: "Cosmetic only", actions: [] }), nc({ id: "n4", ref: "NC-004", status: "VOIDED", void_note: "Entered twice", actions: [] })],
      actions: [action(), action({ id: "a2", ref: "CA-002", status: "COMPLETED", completed_by: "u2", completed_on: "2026-03-01", completion_note: "Done" }), action({ id: "a3", ref: "CA-003", status: "VERIFIED", completed_by: "u2", checked_by: "u3", check_note: "Looked at four weeks" }), action({ id: "a4", ref: "CA-004", status: "NOT_EFFECTIVE", check_note: "Still late" }), action({ id: "a5", ref: "CA-005", status: "CANCELLED", cancel_note: "Not needed" })] };
    for (const role of ["OWNER", "ADMINISTRATOR", "ACCOUNTANT", "FINANCE_OFFICER", "APPROVER", "REVIEWER", "MANAGER", "AUDITOR", "EXTERNAL_AUDITOR", "READ_ONLY"]) for (const me of ["u1", "u2", "u3", "u9"]) for (const [tab] of Q.TABS)
      for (const o of [{}, full, { ...full, sel: { nc: full.ncs[0] } }, { ...full, sel: { nc: full.ncs[1] } }]) assert.doesNotThrow(() => page({ tab, ...o }, role, me), `${role}/${me}/${tab}`);
  });
});

describe("wiring", () => {
  test("client calls the right paths and verbs", async () => {
    const calls = []; const c = new ApiClient("http://x"); c._request = async (m, p, o) => { calls.push([m, p, o && o.body]); return {}; };
    await c.qlOverview(); await c.qlOptions(); await c.setQlPolicy({}); await c.qlNcs(); await c.qlNc("n/1"); await c.raiseQlNc({}); await c.analyseQlNc("n1", {}); await c.closeQlNc("n1", {}); await c.voidQlNc("n1", "Twice");
    await c.qlActions(); await c.addQlAction({}); await c.completeQlAction("a1", {}); await c.verifyQlAction("a1", {}); await c.cancelQlAction("a1", "Not needed");
    assert.deepEqual(calls.map((x) => x.slice(0, 2)), [["GET", "/quality/overview"], ["GET", "/quality/options"], ["PUT", "/quality/policy"], ["GET", "/quality/ncs"], ["GET", "/quality/ncs/n%2F1"], ["POST", "/quality/ncs"], ["POST", "/quality/ncs/n1/analyse"],
      ["POST", "/quality/ncs/n1/close"], ["POST", "/quality/ncs/n1/void"], ["GET", "/quality/actions"], ["POST", "/quality/actions"], ["POST", "/quality/actions/a1/complete"], ["POST", "/quality/actions/a1/verify"], ["POST", "/quality/actions/a1/cancel"]]);
    assert.deepEqual(calls[8][2], { reason: "Twice" }); assert.deepEqual(calls[13][2], { reason: "Not needed" });
  });
  test("menu wiring", () => {
    assert.ok(NAV_GROUPS.find((g) => g.id === "workspaces").paths.includes("/quality"));
    const app = fs.readFileSync(new URL("../src/app.js", import.meta.url), "utf8");
    assert.match(app, /path: "\/quality", label: "Quality management", permission: PERMISSIONS\.AUDIT_READ/); assert.match(app, /path: "\/quality", name: "quality"/); assert.match(app, /renderQualityPage\(authState\)/);
    assert.match(app, /uiState\.ql = null; loadedOnce\.delete\("qlLoading"\)/);
    assert.equal(E.WORKSPACE_PATHS.quality, "/quality"); assert.deepEqual(E.filterNavByWorkspaces([{ path: "/quality" }, { path: "/fpa" }], ["fpa"]).map((i) => i.path), ["/fpa"]);
  });
  test("only the shared client, no fetch or float arithmetic", () => {
    const src = fs.readFileSync(new URL("../src/pages/Quality.js", import.meta.url), "utf8") + fs.readFileSync(new URL("../src/lib/quality.js", import.meta.url), "utf8");
    assert.doesNotMatch(src, /fetch\(|XMLHttpRequest|parseFloat|toFixed/);
  });
});
