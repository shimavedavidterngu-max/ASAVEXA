import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { Datagov } from "../src/pages/Datagov.js";
import * as F from "../src/lib/datagov.js";
import { ApiClient } from "../src/api/client.js";
import { NAV_GROUPS } from "../src/lib/home.js";
import * as E from "../src/lib/entityConfig.js";

const text = (v) => JSON.stringify(v);
const noop = new Proxy({}, { get: () => () => {} });
const gr = (o = {}) => ({ no: 1, person_ref: "STAFF-017", access_level: "READ", purpose: "Prepare the reconciliation", starts_on: "2026-04-01", expires_on: "2026-09-30", status: "PROPOSED", state: "PROPOSED", days_to_expiry: 100, proposed_by: "u1", decision_note: null, revoke_note: null, ...o });
const rv = (o = {}) => ({ no: 1, review_date: "2026-03-31", outcome: "Owner confirmed it is needed", status: "PROPOSED", proposed_by: "u1", decision_note: null, ...o });
const as = (o = {}) => ({ id: "a1", ref: "DA-001", name: "Customer ledger extracts", owner_ref: "FIN-LEAD", classification: "CONFIDENTIAL", personal_data: "YES", retention_months: 84, review_every_months: 6, description: "Monthly extracts of the ledger", status: "PROPOSED", proposed_by: "u1",
  next_review_due: null, review_overdue: false, active_grants: 0, expiring_grants: 0, pending_grants: 0, pending_reviews: 0, too_many_grants: false, decision_note: null, retire_note: null, grants: [], reviews: [], history: [], ...o });
const ovw = () => ({ counts: { proposed: 1, approved: 2, rejected: 0, retired: 0 }, by_classification: { PUBLIC: 0, INTERNAL: 1, CONFIDENTIAL: 1, RESTRICTED: 0 }, personal_data_assets: 1, active_grants: 3, reviews_on_time_pct: "66.67",
  attention: [{ kind: "REVIEWS_OVERDUE", count: 1, text: "asset(s) are overdue for review." }], setting: { expiry_warning_days: 30, max_restricted_grants: 5, meaning: "Within 30 days." }, limitations: ["ASAVEXA enforces no access."] });
const state = (o = {}) => ({ tab: "overview", ov: ovw(), assets: [as()], sel: { asset: null }, forms: { ...JSON.parse(JSON.stringify(F.EMPTY)), setting: { expiry_warning_days: "30", max_restricted_grants: "5" } }, notes: {}, formError: null, busy: false, error: null, notice: null, ...o });
const page = (o = {}, role = "OWNER", me = "u9") => Datagov({ st: state(o), role, userId: me, loading: false, onRetry() {}, actions: noop });
const sel = (x, role = "OWNER", me = "u9") => page({ tab: "assets", sel: { asset: x } }, role, me);

describe("permissions", () => {
  test("who can prepare and approve", () => {
    for (const r of ["OWNER", "ADMINISTRATOR", "MANAGER", "AUDITOR"]) assert.ok(F.canPrepare(r), r);
    for (const r of ["OWNER", "APPROVER", "MANAGER"]) assert.ok(F.canApprove(r), r);
    for (const r of ["ACCOUNTANT", "READ_ONLY", "EXTERNAL_AUDITOR"]) assert.ok(!F.canPrepare(r) && !F.canApprove(r), r);
  });
  test("button rules", () => {
    assert.ok(F.canDecideAsset(as(), "APPROVER", "u9")); assert.ok(!F.canDecideAsset(as({ proposed_by: "u9" }), "APPROVER", "u9")); assert.ok(!F.canDecideAsset(as({ status: "APPROVED" }), "APPROVER", "u9"));
    assert.ok(F.canReview(as({ status: "APPROVED" }), "AUDITOR")); assert.ok(!F.canReview(as(), "AUDITOR")); assert.ok(!F.canGrant(as({ status: "APPROVED" }), "READ_ONLY"));
    assert.ok(F.canDecideReview(as({ status: "APPROVED" }), rv(), "APPROVER", "u9")); assert.ok(!F.canDecideReview(as({ status: "APPROVED" }), rv({ proposed_by: "u9" }), "APPROVER", "u9"));
    assert.ok(F.canDecideGrant(as({ status: "APPROVED" }), gr(), "APPROVER", "u9")); assert.ok(!F.canDecideGrant(as({ status: "APPROVED" }), gr({ proposed_by: "u9" }), "APPROVER", "u9"));
    assert.ok(F.canRevoke(as({ status: "APPROVED" }), gr({ status: "APPROVED" }), "APPROVER")); assert.ok(!F.canRevoke(as({ status: "APPROVED" }), gr(), "APPROVER"));
    assert.ok(F.canRetire(as({ status: "APPROVED" }), "APPROVER")); assert.ok(!F.canRetire(as({ status: "APPROVED", active_grants: 1 }), "APPROVER")); assert.ok(!F.canRetire(as({ status: "APPROVED", pending_reviews: 1 }), "APPROVER"));
    assert.ok(!F.canRetire(as({ status: "APPROVED", grants: [gr({ status: "APPROVED", state: "NOT_YET_ACTIVE" })] }), "APPROVER"));
  });
});

describe("payload builders", () => {
  const f = { name: "Customer ledger", owner_ref: "FIN-LEAD", classification: "restricted", personal_data: "yes", retention_months: "84", review_every_months: "6", description: "Monthly extracts" };
  test("asset", () => {
    assert.deepEqual(F.assetPayload({ ...f, classification: "RESTRICTED", personal_data: "YES" }).body, { name: "Customer ledger", owner_ref: "FIN-LEAD", classification: "RESTRICTED", personal_data: "YES", retention_months: 84, review_every_months: 6, description: "Monthly extracts" });
    for (const [k, v, re] of [["name", "ab", /name/i], ["owner_ref", "x", /owner/i], ["classification", "SECRET", /classification/i], ["personal_data", "maybe", /personal data/i], ["retention_months", "0", /retention/i], ["retention_months", "1201", /retention/i], ["retention_months", "1.5", /retention/i],
      ["review_every_months", "61", /interval/i], ["description", "short", /description/i]]) assert.match(F.assetPayload({ ...f, classification: "PUBLIC", personal_data: "NO", [k]: v }).problem || "", re, k + v);
  });
  test("review", () => {
    assert.equal(F.reviewPayload({ review_date: "2026-03-31", outcome: "Still needed by us" }).body.review_date, "2026-03-31");
    assert.match(F.reviewPayload({ review_date: "2026-02-30", outcome: "Still needed by us" }).problem, /real date/); assert.match(F.reviewPayload({ review_date: "2026-03-31", outcome: "short" }).problem, /outcome/i);
  });
  test("grant limits follow the classification", () => {
    const g = { person_ref: "STAFF-017", access_level: "READ", purpose: "Prepare the reconciliation", starts_on: "2026-04-01", expires_on: "2029-03-31" };
    assert.ok(F.grantPayload(g, { asset: as() }).body); assert.match(F.grantPayload({ ...g, expires_on: "2029-04-02" }, { asset: as() }).problem, /three years/);
    assert.match(F.grantPayload({ ...g, expires_on: "2027-04-03" }, { asset: as({ classification: "RESTRICTED" }) }).problem, /one year/); assert.ok(F.grantPayload({ ...g, expires_on: "2027-04-02" }, { asset: as({ classification: "RESTRICTED" }) }).body);
    assert.match(F.grantPayload({ ...g, expires_on: "2026-03-01" }, { asset: as() }).problem, /before the start/); assert.match(F.grantPayload({ ...g, access_level: "ADMIN" }, { asset: as() }).problem, /access level/i); assert.match(F.grantPayload({ ...g, purpose: "short" }, { asset: as() }).problem, /purpose/i);
  });
  test("setting", () => {
    assert.deepEqual(F.settingPayload({ expiry_warning_days: "45", max_restricted_grants: "3" }).body, { expiry_warning_days: 45, max_restricted_grants: 3 });
    for (const [a, b] of [["0", "5"], ["366", "5"], ["x", "5"], ["30", "0"], ["30", "1001"], ["1.5", "5"]]) assert.ok(F.settingPayload({ expiry_warning_days: a, max_restricted_grants: b }).problem, a + b);
  });
});

describe("page", () => {
  test("overview", () => {
    const t = text(page());
    for (const s of ["66.67 percent", "Holding personal data: 1", "Active access grants: 3", "ASAVEXA enforces no access", "dg-banner", "Reviews overdue", "dg-set-save"]) assert.ok(t.includes(s), s);
    assert.ok(!text(page({}, "READ_ONLY")).includes("dg-set-save"));
  });
  test("proposing is for preparers only", () => {
    assert.ok(text(page({ tab: "assets" }, "AUDITOR")).includes("dg-as-save")); assert.ok(!text(page({ tab: "assets" }, "READ_ONLY")).includes("dg-as-save"));
  });
  test("a proposed asset: other person decides", () => {
    assert.ok(text(sel(as(), "APPROVER", "u9")).includes("dg-as-approve")); const own = text(sel(as({ proposed_by: "u9" }), "APPROVER", "u9")); assert.ok(!own.includes("dg-as-approve")); assert.ok(own.includes("a different person must decide it"));
    const prep = text(sel(as(), "AUDITOR", "u9")); assert.ok(!prep.includes("dg-as-approve")); assert.ok(!prep.includes("dg-rv-save"));
  });
  test("an approved asset: reviews, grants, retire", () => {
    const x = as({ status: "APPROVED", reviews: [rv()], grants: [gr(), gr({ no: 2, status: "APPROVED", state: "ACTIVE", proposed_by: "u1" })], pending_grants: 1, pending_reviews: 1 });
    const prep = text(sel(x, "AUDITOR", "u9")); for (const s of ["dg-rv-save", "dg-gr-save", "dg-gr-person"]) assert.ok(prep.includes(s), s); assert.ok(!prep.includes("dg-gr-1-approve"));
    const appr = text(sel(x, "APPROVER", "u9")); for (const s of ["dg-rv-1-confirm", "dg-rv-1-reject", "dg-gr-1-approve", "dg-gr-1-reject", "dg-gr-2-revoke"]) assert.ok(appr.includes(s), s); assert.ok(!appr.includes("dg-rt-save")); assert.ok(!appr.includes("dg-gr-2-approve"));
    const own = text(sel(x, "APPROVER", "u1")); assert.ok(!own.includes("dg-gr-1-approve")); assert.ok(!own.includes("dg-rv-1-confirm")); assert.ok(own.includes("a different person must decide it"));
    assert.ok(text(sel(as({ status: "APPROVED" }), "APPROVER", "u9")).includes("dg-rt-save"));
  });
  test("read-only sees data and no buttons", () => {
    const t = text(sel(as({ status: "APPROVED", reviews: [rv()], grants: [gr()] }), "READ_ONLY"));
    for (const s of ["dg-rv-save", "dg-gr-save", "dg-gr-1-approve", "dg-rv-1-confirm", "dg-rt-save", "dg-as-approve"]) assert.ok(!t.includes(s), s); assert.ok(t.includes("STAFF-017"));
  });
  test("flags, grant states and notes", () => {
    const t = text(sel(as({ status: "APPROVED", review_overdue: true, too_many_grants: true, next_review_due: "2026-09-30", decision_note: "Checked against the register", grants: [gr({ status: "APPROVED", state: "EXPIRING", days_to_expiry: 5 }), gr({ no: 2, status: "APPROVED", state: "EXPIRED", days_to_expiry: -3 })] })));
    for (const s of ["dg-overdue-note", "dg-many-note", "Checked against the register", "Expiring soon", "5 day(s) left", "Expired", "2026-09-30"]) assert.ok(t.includes(s), s); assert.ok(!t.includes("-3 day(s) left"));
    assert.ok(text(sel(as({ status: "RETIRED", retire_note: "The archive was destroyed" }))).includes("The archive was destroyed"));
  });
  test("errors, problems and loading", () => {
    assert.ok(text(page({ error: "Boom" })).includes("Boom")); assert.ok(text(page({ tab: "assets", formError: { form: "asset", text: "The name needs at least 3 characters." } })).includes("asset-problem"));
    assert.ok(text(Datagov({ st: state(), role: "OWNER", userId: "u9", loading: true, onRetry() {}, actions: noop })).length > 0);
  });
});

describe("wiring", () => {
  test("client methods hit the right paths", async () => {
    const calls = []; const c = new ApiClient("http://x"); c.request = async (m, p, b) => { calls.push([m, p, b]); return {}; };
    c.get = (p) => c.request("GET", p); c.post = (p, b) => c.request("POST", p, b); c.put = (p, b) => c.request("PUT", p, b);
    await c.dgOverview(); await c.dgSetting(); await c.setDgSetting({}); await c.dgAssets(); await c.createDgAsset({}); await c.dgAsset("a b"); await c.approveDgAsset("a1", ""); await c.rejectDgAsset("a1", "r"); await c.retireDgAsset("a1", "r");
    await c.addDgReview("a1", {}); await c.confirmDgReview("a1", 2, ""); await c.rejectDgReview("a1", 2, "r"); await c.addDgGrant("a1", {}); await c.approveDgGrant("a1", 3, ""); await c.rejectDgGrant("a1", 3, "r"); await c.revokeDgGrant("a1", 3, "r");
    const got = calls.map((x) => x[0] + " " + x[1]);
    for (const w of ["GET /datagov/overview", "GET /datagov/setting", "PUT /datagov/setting", "GET /datagov/assets", "POST /datagov/assets", "GET /datagov/assets/a%20b", "POST /datagov/assets/a1/approve", "POST /datagov/assets/a1/reject", "POST /datagov/assets/a1/retire",
      "POST /datagov/assets/a1/reviews", "POST /datagov/assets/a1/reviews/2/confirm", "POST /datagov/assets/a1/reviews/2/reject", "POST /datagov/assets/a1/grants", "POST /datagov/assets/a1/grants/3/approve", "POST /datagov/assets/a1/grants/3/reject", "POST /datagov/assets/a1/grants/3/revoke"]) assert.ok(got.includes(w), w);
  });
  test("home group and entity path", () => {
    assert.ok(NAV_GROUPS.some((g) => g.paths.includes("/datagov"))); assert.equal(E.WORKSPACE_PATHS.datagov, "/datagov");
  });
});
