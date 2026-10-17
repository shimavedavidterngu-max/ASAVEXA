import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { Approvals } from "../src/pages/Approvals.js";
import * as F from "../src/lib/approvals.js";
import { ApiClient } from "../src/api/client.js";
import { NAV_GROUPS } from "../src/lib/home.js";
import * as E from "../src/lib/entityConfig.js";

const text = (v) => JSON.stringify(v);
const noop = new Proxy({}, { get: () => () => {} });
const steps = (d1 = [], d2 = []) => [{ no: 1, label: "Finance review", required: 1, decisions: d1 }, { no: 2, label: "Director sign-off", required: 2, decisions: d2 }];
const dc = (by, o = {}) => ({ by, decision: "APPROVED", on: "2026-03-31", note: null, ...o });
const pol = (o = {}) => ({ id: "p1", ref: "AP-001", name: "Payments over limit", request_kind: "PAYMENT", description: "Large payments need two stages", status: "PROPOSED", proposed_by: "u1", decision_note: null, retire_note: null, requests_under_way: 0, people_per_request: 3,
  steps: [{ no: 1, label: "Finance review", required: 1 }, { no: 2, label: "Director sign-off", required: 2 }], history: [], ...o });
const act = (o = {}) => pol({ status: "ACTIVE", ...o });
const req = (o = {}) => ({ id: "r1", ref: "AR-001", policy_id: "p1", policy_ref: "AP-001", policy_name: "Payments over limit", request_kind: "PAYMENT", title: "Supplier payment", request_ref: "PAY-1", amount: "2500000.00", currency: "NGN",
  description: "Quarterly supplier payment run", status: "PENDING", submitted_by: "u1", current_step: 1, current_label: "Finance review", still_needed: 1, step_count: 2, approvals_so_far: 0, approvals_in_total: 3, waiting_days: 0, stale: false,
  decision_note: null, withdraw_note: null, steps: steps(), history: [], ...o });
const ovw = () => ({ policies: { proposed: 1, active: 2, rejected: 0, retired: 1 }, requests: { pending: 3, approved: 1, rejected: 0, withdrawn: 2 }, attention: [{ kind: "REQUESTS_STALE", count: 2, text: "request(s) have waited too long." }],
  pending_by_kind: { PAYMENT: 3 }, by_currency: [{ currency: "NGN", pending: "300.30", approved: "10.10" }, { currency: "USD", pending: "50.05", approved: "0.00" }], setting: { stale_days: 5, meaning: "Waiting too long after 5 days." }, limitations: ["An approval here is a record."] });
const state = (o = {}) => ({ tab: "overview", ov: ovw(), policies: [act()], requests: [req()], sel: { policy: null, request: null }, forms: { ...JSON.parse(JSON.stringify(F.EMPTY)), setting: { stale_days: "5" } }, notes: {}, formError: null, busy: false, error: null, notice: null, ...o });
const page = (o = {}, role = "OWNER", me = "u9") => Approvals({ st: state(o), role, userId: me, loading: false, onRetry() {}, actions: noop });
const selR = (x, role = "APPROVER", me = "u9") => page({ tab: "requests", sel: { policy: null, request: x } }, role, me);
const selP = (x, role = "APPROVER", me = "u9") => page({ tab: "policies", sel: { policy: x, request: null } }, role, me);

describe("permissions and buttons", () => {
  test("who can prepare and approve", () => {
    for (const r of ["OWNER", "ADMINISTRATOR", "MANAGER", "AUDITOR"]) assert.ok(F.canPrepare(r), r);
    for (const r of ["OWNER", "APPROVER", "MANAGER"]) assert.ok(F.canApprove(r), r);
    for (const r of ["ACCOUNTANT", "READ_ONLY", "EXTERNAL_AUDITOR"]) assert.ok(!F.canPrepare(r) && !F.canApprove(r), r);
  });
  test("button rules", () => {
    assert.ok(F.canDecidePolicy(pol(), "APPROVER", "u9")); assert.ok(!F.canDecidePolicy(pol({ proposed_by: "u9" }), "APPROVER", "u9")); assert.ok(!F.canDecidePolicy(act(), "APPROVER", "u9"));
    assert.ok(F.canRetirePolicy(act(), "APPROVER")); assert.ok(!F.canRetirePolicy(pol(), "APPROVER")); assert.ok(!F.canRetirePolicy(act(), "AUDITOR"));
    assert.ok(F.canDecideRequest(req(), "APPROVER", "u9")); assert.ok(!F.canDecideRequest(req({ submitted_by: "u9" }), "APPROVER", "u9")); assert.ok(!F.canDecideRequest(req({ status: "APPROVED" }), "APPROVER", "u9"));
    assert.ok(!F.canDecideRequest(req(), "AUDITOR", "u9"));
    assert.ok(!F.canDecideRequest(req({ steps: steps([dc("u9")]) }), "APPROVER", "u9"), "no second decision by the same person");
    assert.ok(F.canDecideRequest(req({ steps: steps([dc("u2")]) }), "APPROVER", "u9"));
    assert.ok(F.canWithdraw(req(), "AUDITOR", "u1")); assert.ok(!F.canWithdraw(req(), "AUDITOR", "u2")); assert.ok(!F.canWithdraw(req({ status: "APPROVED" }), "AUDITOR", "u1")); assert.ok(!F.canWithdraw(req(), "READ_ONLY", "u1"));
  });
});

describe("payload builders", () => {
  const pf = { name: "Payments over limit", request_kind: "PAYMENT", description: "Large payments need two stages", s1l: "Finance review", s1n: "1", s2l: "Director sign-off", s2n: "2", s3l: "", s3n: "" };
  test("policy", () => {
    assert.deepEqual(F.policyPayload(pf).body, { name: "Payments over limit", request_kind: "PAYMENT", steps: [{ label: "Finance review", required: 1 }, { label: "Director sign-off", required: 2 }], description: "Large payments need two stages" });
    assert.equal(F.policyPayload({ ...pf, s3l: "Board", s3n: "5" }).body.steps.length, 3);
    for (const [o, re] of [[{ name: "ab" }, /name/i], [{ request_kind: "SPACE" }, /kind/i], [{ description: "short" }, /description/i], [{ s1l: "", s1n: "" }, /Step 1/], [{ s1l: "ab" }, /label of step 1/], [{ s1n: "0" }, /approvals needed at step 1/],
      [{ s1n: "6" }, /approvals needed/], [{ s1n: "x" }, /approvals needed/], [{ s2l: "finance REVIEW" }, /different label/], [{ s2l: "Board", s2n: "" }, /step 2/], [{ s2l: "", s2n: "", s3l: "Board", s3n: "1" }, /in order/]]) assert.match(F.policyPayload({ ...pf, ...o }).problem || "", re, text(o));
  });
  test("request", () => {
    const f = { policy_id: "p1", title: "Supplier payment", request_ref: "PAY-1", amount: "2,500,000.50", currency: "ngn", description: "Quarterly supplier payment run" };
    assert.deepEqual(F.requestPayload(f).body, { policy_id: "p1", title: "Supplier payment", request_ref: "PAY-1", description: "Quarterly supplier payment run", amount: "2500000.50", currency: "NGN" });
    assert.deepEqual(F.requestPayload({ ...f, amount: "", currency: "" }).body, { policy_id: "p1", title: "Supplier payment", request_ref: "PAY-1", description: "Quarterly supplier payment run" });
    for (const [o, re] of [[{ policy_id: "" }, /policy/i], [{ title: "ab" }, /title/i], [{ request_ref: "x" }, /reference/i], [{ description: "short" }, /description/i], [{ currency: "" }, /both/], [{ amount: "" }, /both/], [{ amount: "0" }, /more than zero/],
      [{ amount: "x" }, /amount/i], [{ amount: "1.234" }, /amount/i], [{ currency: "NG" }, /three-letter/]]) assert.match(F.requestPayload({ ...f, ...o }).problem || "", re, text(o));
  });
  test("setting", () => {
    assert.deepEqual(F.settingPayload({ stale_days: "12" }).body, { stale_days: 12 }); for (const v of ["0", "366", "x", "1.5", ""]) assert.ok(F.settingPayload({ stale_days: v }).problem, v);
  });
  test("step line", () => { assert.equal(F.stepLine(steps([dc("u1")])[0], 1), "Step 1: Finance review (1 of 1 approval) — current"); assert.equal(F.stepLine(steps()[1], 1), "Step 2: Director sign-off (0 of 2 approvals)"); });
});

describe("page", () => {
  test("overview", () => {
    const t = text(page());
    for (const s of ["Requests: waiting for approval 3, approved 1, rejected 0, withdrawn 2", "Policies: waiting for a decision 1, active 2", "2 request(s) have waited too long.", "NGN: waiting 300.30, approved 10.10", "USD: waiting 50.05", "never added together", "apw-banner", "An approval here is a record", "apw-set-save"]) assert.ok(t.includes(s), s);
    assert.ok(!text(page({}, "READ_ONLY")).includes("apw-set-save"));
  });
  test("submitting is for preparers, and needs an active policy", () => {
    assert.ok(text(page({ tab: "requests" }, "AUDITOR")).includes("apw-rq-save")); assert.ok(!text(page({ tab: "requests" }, "READ_ONLY")).includes("apw-rq-save"));
    const none = text(page({ tab: "requests", policies: [pol()] }, "AUDITOR")); assert.ok(!none.includes("apw-rq-save")); assert.ok(none.includes("No policy is active yet"));
  });
  test("request list shows step and waiting flags", () => {
    const t = text(page({ tab: "requests", requests: [req({ stale: true, waiting_days: 7 }), req({ ref: "AR-002", status: "APPROVED", current_step: null })] })); for (const s of ["AR-001", "Waiting 7 day(s)", "step 1 of 2: Finance review, 1 more approval(s) needed", "2500000.00 NGN", "Approved"]) assert.ok(t.includes(s), s);
  });
  test("a pending request: only another person who has not decided sees the buttons", () => {
    const x = req(); const a = text(selR(x)); for (const s of ["apw-rq-approve", "apw-rq-reject", "Waiting at step 1 of 2 (Finance review); 1 more approval(s) needed", "0 of 3 approvals recorded", "Step 2: Director sign-off (0 of 2 approvals)"]) assert.ok(a.includes(s), s);
    const own = text(selR(req({ submitted_by: "u9" }))); assert.ok(!own.includes("apw-rq-approve")); assert.ok(own.includes("a different person must decide it"));
    const twice = text(selR(req({ steps: steps([dc("u9")]), current_step: 2 }))); assert.ok(!twice.includes("apw-rq-approve")); assert.ok(twice.includes("already decided this request"));
    const prep = text(selR(x, "AUDITOR")); assert.ok(!prep.includes("apw-rq-approve")); assert.ok(!prep.includes("apw-rq-waiting"));
    const ro = text(selR(x, "READ_ONLY")); assert.ok(!ro.includes("apw-rq-approve") && !ro.includes("apw-rq-withdraw"));
  });
  test("withdraw is for the submitter only", () => {
    assert.ok(text(selR(req(), "AUDITOR", "u1")).includes("apw-rq-withdraw")); assert.ok(!text(selR(req(), "AUDITOR", "u2")).includes("apw-rq-withdraw"));
  });
  test("decided requests show their record", () => {
    const t = text(selR(req({ status: "REJECTED", current_step: null, decision_note: "The second quote is missing", steps: steps([dc("u2"), ], []).map((s) => s), approvals_so_far: 1 }))); for (const s of ["Decision note: The second quote is missing", "Approved on 2026-03-31 by u2", "1 of 3 approvals were recorded"]) assert.ok(t.includes(s), s);
    assert.ok(!t.includes("apw-rq-approve"));
    assert.ok(text(selR(req({ status: "WITHDRAWN", withdraw_note: "Duplicate request" }))).includes("Withdrawn: Duplicate request"));
  });
  test("policies: another person decides, active ones can be retired", () => {
    assert.ok(text(selP(pol())).includes("apw-pl-activate")); const own = text(selP(pol({ proposed_by: "u9" }))); assert.ok(!own.includes("apw-pl-activate")); assert.ok(own.includes("a different person must decide it"));
    const a = text(selP(act())); assert.ok(a.includes("apw-pl-retire")); assert.ok(!a.includes("apw-pl-activate")); for (const s of ["Finance review: 1 different person", "Director sign-off: 2 different people"]) assert.ok(a.includes(s), s);
    assert.ok(text(selP(act({ status: "RETIRED", retire_note: "Replaced by a new policy" }))).includes("Retired: Replaced by a new policy"));
    const ro = text(selP(pol(), "READ_ONLY")); assert.ok(!ro.includes("apw-pl-activate") && !ro.includes("apw-pl-save"));
  });
  test("policy list and form", () => {
    const t = text(page({ tab: "policies", policies: [act({ requests_under_way: 2 }), pol({ ref: "AP-002" })] }, "AUDITOR")); for (const s of ["AP-001", "2 request(s) under way", "2 step(s) · 3 approval(s) in total", "apw-pl-save", "apw-pl-s3l"]) assert.ok(t.includes(s), s);
  });
  test("errors, problems and loading", () => {
    assert.ok(text(page({ error: "Boom" })).includes("Boom")); assert.ok(text(page({ tab: "policies", formError: { form: "policy", text: "The policy name needs at least 3 characters." } })).includes("policy-problem"));
    assert.ok(text(Approvals({ st: state(), role: "OWNER", userId: "u9", loading: true, onRetry() {}, actions: noop })).length > 0);
  });
});

describe("wiring", () => {
  test("client methods hit the right paths", async () => {
    const calls = []; const c = new ApiClient("http://x"); c.request = async (m, p, b) => { calls.push([m, p, b]); return {}; };
    c.get = (p) => c.request("GET", p); c.post = (p, b) => c.request("POST", p, b); c.put = (p, b) => c.request("PUT", p, b);
    await c.apwOptions(); await c.apwOverview(); await c.apwSetting(); await c.setApwSetting({}); await c.apwPolicies(); await c.createApwPolicy({}); await c.apwPolicy("a b"); await c.activateApwPolicy("p1", ""); await c.rejectApwPolicy("p1", "r"); await c.retireApwPolicy("p1", "r");
    await c.apwRequests(); await c.submitApwRequest({}); await c.apwRequest("r1"); await c.approveApwRequest("r1", ""); await c.rejectApwRequest("r1", "r"); await c.withdrawApwRequest("r1", "r");
    assert.deepEqual(calls.map((x) => x[0] + " " + x[1]), ["GET /approvals/options", "GET /approvals/overview", "GET /approvals/setting", "PUT /approvals/setting", "GET /approvals/policies", "POST /approvals/policies", "GET /approvals/policies/a%20b", "POST /approvals/policies/p1/activate",
      "POST /approvals/policies/p1/reject", "POST /approvals/policies/p1/retire", "GET /approvals/requests", "POST /approvals/requests", "GET /approvals/requests/r1", "POST /approvals/requests/r1/approve", "POST /approvals/requests/r1/reject", "POST /approvals/requests/r1/withdraw"]);
  });
  test("home group and entity path", () => {
    assert.ok(NAV_GROUPS.some((g) => g.paths.includes("/approvals"))); assert.equal(E.WORKSPACE_PATHS.approvals, "/approvals");
  });
});
