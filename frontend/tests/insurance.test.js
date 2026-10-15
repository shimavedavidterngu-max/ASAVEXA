import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { Insurance } from "../src/pages/Insurance.js";
import * as F from "../src/lib/insurance.js";
import { ApiClient } from "../src/api/client.js";
import { NAV_GROUPS } from "../src/lib/home.js";
import * as E from "../src/lib/entityConfig.js";

const text = (v) => JSON.stringify(v);
const noop = new Proxy({}, { get: () => () => {} });
// u1 proposes, u3 decides, u9 bystander
const claim = (o = {}) => ({ id: "c1", ref: "CL-001", policy_id: "p1", policy_ref: "IP-001", currency: "NGN", loss_date: "2026-02-20", reported_date: "2026-02-21", description: "Water damage to stock", claimed_amount: "200000.00", claim_number: "CN-77", status: "OPEN", settled_amount: null, outcome: null,
  proposals: [], receipts: [], received: "0.00", outstanding: null, pending: 0, history: [], ...o });
const policy = (o = {}) => ({ id: "p1", ref: "IP-001", insurer: "Leadway Assurance", policy_number: "PL-1001", cover_type: "PROPERTY", covers: "Warehouse and stock", currency: "NGN", sum_insured: "1000000.00", premium: "25000.50", excess: "5000.00", start_date: "2026-01-01", end_date: "2026-12-31",
  status: "ACTIVE", cancel_note: null, open_claims: 0, expired: false, ending_soon: false, claims: [], history: [], ...o });
const ovw = () => ({ counts: { policies_active: 2, policies_cancelled: 1, claims_open: 1, claims_proposed: 1, claims_settled: 1, claims_declined: 0 }, totals: [{ currency: "NGN", active_policies: 2, sum_insured: "3000000.00", premium: "75001.50", open_claims: 2, claimed_open: "400000.00", settled: "150000.25", received: "50000.10", outstanding: "100000.15" }],
  attention: [{ kind: "OUTCOMES_TO_DECIDE", count: 1, text: "claim outcome(s) are waiting for a different person to decide them." }], policy: { warning_days: 60, meaning: "A policy that ends within 60 days is flagged as ending soon." }, limitations: ["ASAVEXA contacts no insurer."] });
const state = (o = {}) => ({ tab: "overview", ov: ovw(), policies: [policy()], claims: [claim()], sel: { policy: null, claim: null }, forms: { ...JSON.parse(JSON.stringify(F.EMPTY)), setting: { warning_days: "60" } }, notes: {}, formError: null, busy: false, error: null, notice: null, ...o });
const page = (o = {}, role = "OWNER", me = "u9") => Insurance({ ic: state(o), role, userId: me, loading: false, onRetry() {}, actions: noop });

describe("permissions", () => {
  test("who can prepare and approve", () => {
    for (const r of ["OWNER", "ADMINISTRATOR", "MANAGER", "AUDITOR"]) assert.ok(F.canPrepare(r), r);
    for (const r of ["OWNER", "APPROVER", "MANAGER"]) assert.ok(F.canApprove(r), r);
    for (const r of ["ACCOUNTANT", "READ_ONLY", "EXTERNAL_AUDITOR", "INVESTOR_REVIEWER"]) { assert.ok(!F.canPrepare(r), r); assert.ok(!F.canApprove(r), r); }
  });
});

describe("payload builders", () => {
  const p = { insurer: "Leadway Assurance", policy_number: "PL-1001", cover_type: "PROPERTY", covers: "Warehouse", currency: "ngn", sum_insured: "1,000,000", premium: "25000.5", excess: "", start_date: "2026-01-01", end_date: "2026-12-31" };
  test("policy", () => {
    const b = F.policyPayload(p).body; assert.deepEqual([b.currency, b.sum_insured, b.premium], ["NGN", "1000000", "25000.5"]); assert.ok(!("excess" in b));
    assert.ok(F.policyPayload({ ...p, premium: "0" }).body);
    for (const bad of [{ insurer: "x" }, { policy_number: "" }, { covers: "abc" }, { currency: "NG" }, { currency: "N1A" }, { sum_insured: "0" }, { sum_insured: "x" }, { premium: "1.234" }, { premium: "" }, { excess: "2000000" }, { excess: "-1" }, { start_date: "2026-02-30" }, { end_date: "2026-01-01" }, { end_date: "2025-01-01" }]) assert.ok(F.policyPayload({ ...p, ...bad }).problem, text(bad));
  });
  const c = { loss_date: "2026-02-20", reported_date: "2026-02-21", description: "Water damage to stock", claimed_amount: "200000", claim_number: "" };
  test("claim", () => {
    const b = F.claimPayload(c, "1000000.00").body; assert.equal(b.claimed_amount, "200000"); assert.ok(!("claim_number" in b));
    for (const bad of [{ loss_date: "x" }, { reported_date: "2026-02-19" }, { description: "short" }, { claimed_amount: "0" }, { claimed_amount: "1000000.01" }, { claimed_amount: "1.234" }, { claim_number: "x" }]) assert.ok(F.claimPayload({ ...c, ...bad }, "1000000.00").problem, text(bad));
  });
  test("outcome", () => {
    const s = { outcome: "SETTLE", amount: "150000.25", note: "Insurer confirmed by letter" };
    assert.equal(F.outcomePayload(s, "200000.00").body.amount, "150000.25");
    for (const bad of [{ amount: "" }, { amount: "0" }, { amount: "200000.01" }, { note: "short" }]) assert.ok(F.outcomePayload({ ...s, ...bad }, "200000.00").problem, text(bad));
    const d = F.outcomePayload({ outcome: "DECLINE", amount: "", note: "Insurer declined: excluded peril" }, "200000.00").body; assert.ok(!("amount" in d));
    assert.ok(F.outcomePayload({ outcome: "DECLINE", amount: "5", note: "Insurer declined: excluded peril" }, "200000.00").problem);
  });
  test("receipt and setting", () => {
    const r = { amount: "100", received_on: "2026-03-10", reference: "PAY-1" };
    assert.ok(F.receiptPayload(r, "100.00").body); assert.ok(F.receiptPayload({ ...r, amount: "100.01" }, "100.00").problem);
    for (const bad of [{ amount: "0" }, { amount: "1.234" }, { received_on: "2026-13-01" }, { reference: "x" }]) assert.ok(F.receiptPayload({ ...r, ...bad }, "100.00").problem, text(bad));
    assert.equal(F.settingPayload("60").body.warning_days, 60); for (const bad of ["6", "366", "x", "", "3.5"]) assert.ok(F.settingPayload(bad).problem, bad);
  });
});

describe("buttons", () => {
  test("rules", () => {
    const pend = { no: 1, status: "PENDING", by: "u1" };
    assert.ok(F.canDecideOutcome(pend, "APPROVER", "u3")); assert.ok(!F.canDecideOutcome(pend, "APPROVER", "u1")); assert.ok(!F.canDecideOutcome(pend, "AUDITOR", "u3")); assert.ok(!F.canDecideOutcome({ ...pend, status: "APPROVED" }, "APPROVER", "u3"));
    assert.ok(F.canPropose(claim(), "AUDITOR")); assert.ok(!F.canPropose(claim({ status: "PROPOSED" }), "AUDITOR")); assert.ok(!F.canPropose(claim(), "APPROVER"));
    assert.ok(F.canReceive(claim({ status: "SETTLED", outstanding: "10.00" }), "OWNER")); assert.ok(!F.canReceive(claim({ status: "SETTLED", outstanding: "0.00" }), "OWNER")); assert.ok(!F.canReceive(claim(), "OWNER"));
    assert.ok(F.canCancel(policy(), "APPROVER")); assert.ok(!F.canCancel(policy({ open_claims: 1 }), "APPROVER")); assert.ok(!F.canCancel(policy(), "AUDITOR")); assert.ok(!F.canCancel(policy({ status: "CANCELLED" }), "OWNER"));
    assert.ok(F.canClaim(policy(), "AUDITOR")); assert.ok(!F.canClaim(policy({ status: "CANCELLED" }), "AUDITOR"));
  });
});

describe("page", () => {
  test("overview", () => {
    const t = text(page()); assert.match(t, /ic-banner/); assert.match(t, /contacts no insurer/); assert.match(t, /never added together/); assert.match(t, /still to receive 100000\.15/); assert.match(t, /ic-set-save/);
    assert.ok(!/ic-set-save/.test(text(page({}, "AUDITOR"))));
  });
  test("policies list and form", () => {
    const t = text(page({ tab: "policies" })); assert.match(t, /IP-001/); assert.match(t, /ic-po-save/); assert.ok(!/ic-po-save/.test(text(page({ tab: "policies" }, "READ_ONLY"))));
    assert.match(text(page({ tab: "policies", policies: [policy({ ending_soon: true }), policy({ id: "p2", ref: "IP-002", expired: true })] })), /Ending soon.*Past its end date/);
  });
  test("policy detail", () => {
    const p = policy({ claims: [claim()] }); const t = text(page({ tab: "policies", sel: { policy: p, claim: null } }, "OWNER"));
    assert.match(t, /ic-policy-detail/); assert.match(t, /CL-001/); assert.match(t, /ic-cm-save/); assert.match(t, /ic-cancel-save/);
    const busy = text(page({ tab: "policies", sel: { policy: policy({ open_claims: 1 }), claim: null } })); assert.ok(!/ic-cancel-save/.test(busy));
    assert.match(text(page({ tab: "policies", sel: { policy: policy({ status: "CANCELLED", cancel_note: "Replaced by a new policy" }), claim: null } })), /Replaced by a new policy/);
  });
  test("claim detail: different person only", () => {
    const c = claim({ status: "PROPOSED", proposals: [{ no: 1, outcome: "SETTLE", amount: "150000.25", note: "Insurer letter", by: "u1", status: "PENDING" }] });
    const other = text(page({ tab: "claims", sel: { policy: null, claim: c } }, "APPROVER", "u3")); assert.match(other, /ic-pr-1-approve/); assert.match(other, /ic-pr-1-reject/); assert.match(other, /150000\.25/);
    const same = text(page({ tab: "claims", sel: { policy: null, claim: c } }, "APPROVER", "u1")); assert.ok(!/ic-pr-1-approve/.test(same)); assert.match(same, /so a different person must decide it/);
    assert.ok(!/ic-oc-save/.test(other));
  });
  test("open claim shows the proposal form; settled shows receipts", () => {
    assert.match(text(page({ tab: "claims", sel: { policy: null, claim: claim() } })), /ic-oc-save/);
    const s = claim({ status: "SETTLED", settled_amount: "150000.25", received: "50000.10", outstanding: "100000.15", receipts: [{ no: 1, amount: "50000.10", received_on: "2026-03-10", reference: "PAY-1" }] });
    const t = text(page({ tab: "claims", sel: { policy: null, claim: s } })); assert.match(t, /ic-rc-save/); assert.match(t, /Still to receive 100000\.15/); assert.match(t, /PAY-1/); assert.ok(!/ic-oc-save/.test(t));
  });
  test("loading and error", () => {
    assert.match(text(Insurance({ ic: state(), role: "OWNER", userId: "u9", loading: true, onRetry() {}, actions: noop })), /./); assert.match(text(page({ error: "Boom" })), /Boom/);
  });
});

describe("wiring", () => {
  test("client paths", async () => {
    const calls = []; const c = new ApiClient({ baseUrl: "http://x" }); for (const k of ["get", "post", "put"]) c[k] = async (p, b) => { calls.push([k, p, b]); return {}; };
    await c.approveIcOutcome("c1", 2, "ok"); await c.recordIcReceipt("a b", { amount: "1" }); await c.setIcSetting({ warning_days: 30 }); await c.addIcClaim("p1", {});
    assert.deepEqual(calls.map((x) => x[0] + " " + x[1]), ["post /insurance/claims/c1/proposals/2/approve", "post /insurance/claims/a%20b/receipts", "put /insurance/setting", "post /insurance/policies/p1/claims"]);
  });
  test("nav and entity paths", () => { assert.ok(text(NAV_GROUPS).includes("/insurance")); assert.equal(E.WORKSPACE_PATHS.insurance, "/insurance"); });
});
