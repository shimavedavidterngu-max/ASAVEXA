import { test, describe } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { FixedAssets } from "../src/pages/FixedAssets.js";
import * as F from "../src/lib/fixedassets.js";
import { ApiClient } from "../src/api/client.js";
import { NAV_GROUPS } from "../src/lib/home.js";
import * as E from "../src/lib/entityConfig.js";

const text = (v) => JSON.stringify(v);
const noop = new Proxy({}, { get: () => () => {} });
// u1 proposes, u2 counts, u3 approves, u9 bystander
const count = (o = {}) => ({ no: 1, counted_on: "2026-03-10", result: "FOUND", note: "Found in the yard", counted_by: "u2", evidence: [], status: "UNREVIEWED", reviewed_by: null, review_note: null, ...o });
const asset = (o = {}) => ({ id: "a1", ref: "FA-001", name: "Delivery van", category: "VEHICLES", location: "Main yard", custodian_name: "Ben Eze", acquired_on: "2026-01-15", currency: "NGN", cost: "12000.00", residual: "2000.00", life_months: 60, serial_number: null, evidence: [],
  status: "ACTIVE", proposed_by: "u1", decided_by: "u3", decision_note: null, disposal: null, counts: [], history: [], as_of: "2026-03-10", accumulated: "166.67", net_book_value: "11833.33", depreciates: true, monthly: "166.67", fully_depreciated: false,
  last_counted_on: null, count_due: false, counts_to_review: 0, missing: false, ...o });
const disposal = (o = {}) => ({ disposed_on: "2026-03-10", proceeds: "9000.00", reason: "Sold to a dealer after the lease ended", proposed_by: "u1", net_book_value: "11833.33", gain_or_loss: "-2833.33", decided_by: null, decision_note: null, ...o });
const ovw = () => ({ counts: { proposed: 1, active: 1, disposal_pending: 0, disposed: 0, fully_depreciated: 0 }, totals: [{ currency: "NGN", assets: 1, cost: "12000.00", accumulated: "166.67", net_book_value: "11833.33" }, { currency: "USD", assets: 1, cost: "900.00", accumulated: "0.00", net_book_value: "900.00" }],
  attention: [{ kind: "ASSETS_TO_APPROVE", count: 1, text: "asset(s) are waiting for a different person to approve them." }], policy: { count_days: 365, meaning: "An active asset not counted within 365 days is flagged." }, limitations: ["ASAVEXA posts nothing to a ledger."] });
const state = (o = {}) => ({ tab: "overview", options: {}, ov: ovw(), assets: [asset()], sel: { asset: null }, schedule: { rows: [{ month_no: 2, on: "2026-03-15", accumulated: "333.33", net_book_value: "11666.67" }] }, vault: [],
  forms: { ...JSON.parse(JSON.stringify(F.EMPTY)), policy: F.policyForm(ovw().policy) }, notes: {}, formError: null, busy: false, error: null, notice: null, ...o });
const page = (o = {}, role = "OWNER", me = "u9") => FixedAssets({ fa: state(o), role, userId: me, loading: false, onRetry() {}, actions: noop });

describe("permissions", () => {
  test("who can prepare and approve", () => {
    for (const r of ["OWNER", "ADMINISTRATOR", "MANAGER", "AUDITOR"]) assert.ok(F.canPrepare(r), r);
    for (const r of ["OWNER", "APPROVER", "MANAGER"]) assert.ok(F.canApprove(r), r);
    for (const r of ["ACCOUNTANT", "READ_ONLY", "EXTERNAL_AUDITOR"]) { assert.ok(!F.canPrepare(r), r); assert.ok(!F.canApprove(r), r); }
    assert.ok(!F.canRead("ACCOUNTANT")); assert.ok(F.canRead("AUDITOR"));
  });
});

describe("payload builders", () => {
  const g = { name: "Delivery van", category: "VEHICLES", location: "Main yard", custodian_name: "Ben Eze", acquired_on: "2026-01-15", currency: "ngn", cost: "12,000.50", residual_value: "2000", life_months: "60", serial_number: "", evidence_id: "" };
  test("asset", () => {
    const ok = F.assetPayload(g).body; assert.deepEqual([ok.currency, ok.cost, ok.residual_value, ok.life_months, "serial_number" in ok], ["NGN", "12000.50", "2000", 60, false]);
    assert.equal(F.assetPayload({ ...g, residual_value: "" }).body.residual_value, "0"); assert.deepEqual(F.assetPayload({ ...g, evidence_id: "e1", serial_number: "SN-1" }).body.evidence_ids, ["e1"]);
    for (const bad of [{ name: "ab" }, { location: "x" }, { custodian_name: "" }, { acquired_on: "2026-02-30" }, { currency: "NG" }, { currency: "N1A" }, { cost: "0" }, { cost: "abc" }, { cost: "1.234" }, { cost: "-5" }, { residual_value: "12000.50" }, { residual_value: "13000" }, { residual_value: "1.234" },
      { life_months: "" }, { life_months: "0" }, { life_months: "601" }, { life_months: "1.5" }, { serial_number: "x" }]) assert.ok(F.assetPayload({ ...g, ...bad }).problem, JSON.stringify(bad));
  });
  test("land has no life or residual value", () => {
    const l = { ...g, category: "LAND", life_months: "", residual_value: "" }; const b = F.assetPayload(l).body; assert.ok(b && !("life_months" in b));
    assert.ok(F.assetPayload({ ...l, life_months: "60" }).problem); assert.ok(F.assetPayload({ ...l, residual_value: "100" }).problem); assert.ok(F.assetPayload({ ...l, residual_value: "0.00" }).body);
  });
  test("cents are exact integers", () => { assert.equal(F.cents("12,000.5"), 1200050); assert.equal(F.cents("0.07"), 7); assert.equal(F.cents("3"), 300); });
  test("disposal, count, review, settings", () => {
    const d = { disposed_on: "2026-03-10", proceeds: "", reason: "Sold to a dealer after the lease" }; assert.equal(F.disposalPayload(d).body.proceeds, "0");
    for (const bad of [{ disposed_on: "soon" }, { proceeds: "-1" }, { proceeds: "1.234" }, { reason: "short" }]) assert.ok(F.disposalPayload({ ...d, ...bad }).problem, JSON.stringify(bad));
    const c = { counted_on: "2026-03-10", result: "MISSING", note: "Not in the yard", evidence_id: "" }; assert.equal(F.countPayload(c).body.result, "MISSING"); assert.ok(F.countPayload({ ...c, counted_on: "" }).problem); assert.ok(F.countPayload({ ...c, note: "short" }).problem);
    assert.ok(F.reviewPayload({ note: "Checked the photo" }).body); assert.ok(F.reviewPayload({ note: "ok" }).problem);
    assert.equal(F.policyPayload({ count_days: "90" }).body.count_days, 90); for (const v of ["29", "731", "x", "", "9", "4.5"]) assert.ok(F.policyPayload({ count_days: v }).problem, v);
  });
});

describe("who sees which button", () => {
  test("separation of duties", () => {
    const p = asset({ status: "PROPOSED" }); assert.ok(F.canApproveAsset(p, "APPROVER", "u3")); assert.ok(!F.canApproveAsset(p, "MANAGER", "u1")); assert.ok(!F.canApproveAsset(asset(), "APPROVER", "u3"));
    assert.ok(F.canDispose(asset(), "AUDITOR")); assert.ok(!F.canDispose(p, "AUDITOR")); assert.ok(!F.canDispose(asset(), "APPROVER"));
    const dp = asset({ status: "DISPOSAL_PENDING", disposal: disposal() }); assert.ok(F.canDecideDisposal(dp, "APPROVER", "u3")); assert.ok(!F.canDecideDisposal(dp, "MANAGER", "u1")); assert.ok(!F.canDecideDisposal(asset(), "APPROVER", "u3"));
    assert.ok(F.canCount(asset(), "AUDITOR")); assert.ok(!F.canCount(dp, "AUDITOR"));
    assert.ok(F.canReviewCount(count(), "APPROVER", "u3")); assert.ok(!F.canReviewCount(count(), "MANAGER", "u2")); assert.ok(!F.canReviewCount(count({ status: "REVIEWED" }), "APPROVER", "u3"));
  });
});

describe("page", () => {
  test("overview", () => {
    const t = text(page()); for (const id of ["fa-attention", "fa-totals", "fa-counts", "fa-policy", "fa-limits", "fa-banner"]) assert.match(t, new RegExp(id));
    assert.match(t, /NGN: 1 asset/); assert.match(t, /USD: 1 asset/); assert.match(t, /never added together/); assert.match(t, /fa-policy-save/); assert.doesNotMatch(text(page({}, "AUDITOR", "u1")), /fa-policy-save/);
  });
  test("assets tab", () => {
    const t = (role, me, o = {}) => text(page({ tab: "assets", ...o }, role, me));
    assert.match(t("AUDITOR", "u1"), /fa-as-save/); assert.doesNotMatch(t("APPROVER", "u3"), /fa-as-save/);
    const pr = { assets: [asset({ status: "PROPOSED" })] };
    assert.match(t("APPROVER", "u3", pr), /fa-as-FA-001-approve/); assert.match(t("APPROVER", "u3", pr), /fa-as-FA-001-reject/); assert.doesNotMatch(t("MANAGER", "u1", pr), /fa-as-FA-001-approve/); assert.match(t("MANAGER", "u1", pr), /different person/);
    const land = { forms: { ...state().forms, asset: { ...state().forms.asset, category: "LAND" } } }; assert.doesNotMatch(t("AUDITOR", "u1", land), /fa-as-life/); assert.match(t("AUDITOR", "u1"), /fa-as-life/);
    const bad = t("AUDITOR", "u1", { assets: [asset({ count_due: true, missing: true, fully_depreciated: true })], formError: { form: "asset", text: "Bad cost" } });
    for (const w of ["Count due", "Missing", "Fully depreciated", "asset-problem"]) assert.match(bad, new RegExp(w)); assert.doesNotMatch(bad, /object Object/);
    assert.match(t("AUDITOR", "u1"), /166\.67/); assert.match(t("AUDITOR", "u1"), /11833\.33/);
  });
  test("detail: schedule, disposal and counts", () => {
    const open = (role, me, a, o = {}) => text(page({ tab: "assets", assets: [a], sel: { asset: a }, ...o }, role, me));
    assert.match(open("AUDITOR", "u1", asset()), /fa-schedule/); assert.match(open("AUDITOR", "u1", asset()), /Month 2/); assert.match(open("AUDITOR", "u1", asset()), /fa-dp-save/); assert.match(open("AUDITOR", "u1", asset()), /fa-ct-save/);
    assert.doesNotMatch(open("AUDITOR", "u1", asset({ depreciates: false, life_months: 0 })), /fa-schedule/);
    const dp = asset({ status: "DISPOSAL_PENDING", disposal: disposal() });
    assert.match(open("APPROVER", "u3", dp), /fa-disposal-approve/); assert.match(open("APPROVER", "u3", dp), /loss of 2833\.33/); assert.match(open("APPROVER", "u3", dp), /Not posted to any ledger/);
    assert.doesNotMatch(open("MANAGER", "u1", dp), /fa-disposal-approve/); assert.match(open("MANAGER", "u1", dp), /fa-disposal-waiting/); assert.doesNotMatch(open("AUDITOR", "u1", dp), /fa-dp-save/);
    assert.match(open("APPROVER", "u3", asset({ status: "DISPOSAL_PENDING", disposal: disposal({ gain_or_loss: "1000.00" }) })), /gain of 1000\.00/); assert.match(open("APPROVER", "u3", asset({ status: "DISPOSAL_PENDING", disposal: disposal({ gain_or_loss: "0.00" }) })), /no gain or loss/);
    const c = asset({ counts: [count()] }); assert.match(open("APPROVER", "u3", c), /fa-ct-1-review/); assert.doesNotMatch(open("MANAGER", "u2", c), /fa-ct-1-review/); assert.match(open("MANAGER", "u2", c), /different person/);
  });
  test("every tab, role and person renders", () => {
    const full = [asset(), asset({ id: "a2", ref: "FA-002", status: "PROPOSED" }), asset({ id: "a3", ref: "FA-003", status: "DISPOSAL_PENDING", disposal: disposal() }), asset({ id: "a4", ref: "FA-004", status: "DISPOSED", disposal: disposal({ decided_by: "u3" }) }), asset({ id: "a5", ref: "FA-005", status: "REJECTED", decision_note: "Wrong" }),
      asset({ id: "a6", ref: "FA-006", counts: [count(), count({ no: 2, status: "REVIEWED", reviewed_by: "u3", review_note: "Fine", result: "MISSING" })], missing: true, count_due: true })];
    for (const role of ["OWNER", "ADMINISTRATOR", "ACCOUNTANT", "FINANCE_OFFICER", "APPROVER", "REVIEWER", "MANAGER", "AUDITOR", "EXTERNAL_AUDITOR", "READ_ONLY"]) for (const me of ["u1", "u2", "u3", "u9"]) for (const [tab] of F.TABS)
      for (const sel of [null, ...full]) assert.doesNotThrow(() => page({ tab, assets: full, sel: { asset: sel } }, role, me), `${role}/${me}/${tab}`);
    assert.doesNotThrow(() => page({ tab: "assets", schedule: null, sel: { asset: asset() } }));
  });
});

describe("wiring", () => {
  test("client calls the right paths and verbs", async () => {
    const calls = []; const c = new ApiClient("http://x"); c._request = async (m, p, o) => { calls.push([m, p, o && o.body]); return {}; };
    await c.faOverview(); await c.faOptions(); await c.setFaPolicy({}); await c.faAssets(); await c.faAsset("a/1"); await c.faSchedule("a1", 6); await c.proposeFaAsset({}); await c.approveFaAsset("a1", "ok"); await c.rejectFaAsset("a1", "No");
    await c.proposeFaDisposal("a1", {}); await c.approveFaDisposal("a1", "ok"); await c.rejectFaDisposal("a1", "No"); await c.recordFaCount("a1", {}); await c.reviewFaCount("a1", 2, "Checked");
    assert.deepEqual(calls.map((x) => x.slice(0, 2)), [["GET", "/fixedassets/overview"], ["GET", "/fixedassets/options"], ["PUT", "/fixedassets/policy"], ["GET", "/fixedassets/assets"], ["GET", "/fixedassets/assets/a%2F1"], ["GET", "/fixedassets/assets/a1/schedule?months=6"],
      ["POST", "/fixedassets/assets"], ["POST", "/fixedassets/assets/a1/approve"], ["POST", "/fixedassets/assets/a1/reject"], ["POST", "/fixedassets/assets/a1/disposal"], ["POST", "/fixedassets/assets/a1/disposal/approve"], ["POST", "/fixedassets/assets/a1/disposal/reject"],
      ["POST", "/fixedassets/assets/a1/counts"], ["POST", "/fixedassets/assets/a1/counts/2/review"]]);
    assert.deepEqual(calls[7][2], { note: "ok" }); assert.deepEqual(calls[8][2], { reason: "No" }); assert.deepEqual(calls[13][2], { note: "Checked" });
  });
  test("menu wiring", () => {
    assert.ok(NAV_GROUPS.find((g) => g.id === "workspaces").paths.includes("/fixedassets"));
    const app = fs.readFileSync(new URL("../src/app.js", import.meta.url), "utf8");
    assert.match(app, /path: "\/fixedassets", label: "Fixed assets", permission: PERMISSIONS\.AUDIT_READ/); assert.match(app, /path: "\/fixedassets", name: "fixedassets"/); assert.match(app, /renderFixedAssetsPage\(authState\)/);
    assert.match(app, /uiState\.fa = null; loadedOnce\.delete\("faLoading"\)/);
    assert.equal(E.WORKSPACE_PATHS.fixedassets, "/fixedassets"); assert.deepEqual(E.filterNavByWorkspaces([{ path: "/fixedassets" }, { path: "/fpa" }], ["fpa"]).map((i) => i.path), ["/fpa"]);
  });
  test("only the shared client, no fetch or float arithmetic", () => {
    const src = fs.readFileSync(new URL("../src/pages/FixedAssets.js", import.meta.url), "utf8") + fs.readFileSync(new URL("../src/lib/fixedassets.js", import.meta.url), "utf8");
    assert.doesNotMatch(src, /fetch\(|XMLHttpRequest|parseFloat|toFixed/);
  });
});
