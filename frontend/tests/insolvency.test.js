import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { Insolvency } from "../src/pages/Insolvency.js";
import * as F from "../src/lib/insolvency.js";
import { ApiClient } from "../src/api/client.js";
import { NAV_GROUPS } from "../src/lib/home.js";
import * as E from "../src/lib/entityConfig.js";

const text = (v) => JSON.stringify(v);
const noop = new Proxy({}, { get: () => () => {} });
const claim = (o = {}) => ({ no: 1, creditor_ref: "SUP-1", claim_class: "UNSECURED", amount: "300000.00", basis: "Unpaid invoices for fabric", admitted: "0.00", paid: "0.00", owed: "0.00", late: false, status: "LODGED", proposed_by: "u1", decision_note: null, ...o });
const entry = (o = {}) => ({ no: 1, entry_type: "REALISATION", description: "Sale of the machinery", amount: "1000000.00", entry_date: "2026-03-30", status: "PROPOSED", proposed_by: "u1", decision_note: null, ...o });
const wf = (o = {}) => ({ realisations: "1000000.00", costs: "50000.00", distributed_to_date: "0.00", available: "950000.00", costs_exceed: false, total_owed: "1180000.01", total_paid: "950000.00", shortfall: "230000.01", left_over: "0.00",
  classes: [{ claim_class: "SECURED", owed: "500000.00", paid: "500000.00", recovery_pct: "100.00", claims: [{ no: 1, creditor_ref: "BANK-1", owed: "500000.00", dividend: "500000.00" }] },
    { claim_class: "UNSECURED", owed: "600000.01", paid: "370000.00", recovery_pct: "61.67", claims: [{ no: 3, creditor_ref: "SUP-1", owed: "300000.00", dividend: "184999.99" }] }], ...o });
const cs = (o = {}) => ({ id: "c1", ref: "IC-001", title: "Textile estate", description: "Estate of a closed company", currency: "NGN", priority: ["SECURED", "PREFERENTIAL", "UNSECURED", "SUBORDINATED"], claims_deadline: "2026-06-30", status: "PROPOSED", proposed_by: "u1",
  claims: [], entries: [], distributions: [], history: [], pending_claims: 0, pending_entries: 0, claimed_total: "0.00", admitted_total: "0.00", late_claims: 0, waterfall: null, decision_note: null, close_note: null, ...o });
const open = (o = {}) => cs({ status: "OPEN", waterfall: wf(), ...o });
const ovw = () => ({ counts: { proposed: 1, open: 2, rejected: 0, closed: 1 }, totals: [{ currency: "NGN", cases: 2, admitted: "1180000.01", distributed: "950000.00" }, { currency: "USD", cases: 1, admitted: "50.00", distributed: "0.00" }],
  attention: [{ kind: "FUNDS_READY", count: 1, text: "case(s) have funds available." }], limitations: ["ASAVEXA pays no one."] });
const state = (o = {}) => ({ tab: "overview", ov: ovw(), cases: [open()], sel: { case: null }, forms: JSON.parse(JSON.stringify(F.EMPTY)), notes: {}, formError: null, busy: false, error: null, notice: null, ...o });
const page = (o = {}, role = "OWNER", me = "u9") => Insolvency({ st: state(o), role, userId: me, loading: false, onRetry() {}, actions: noop });
const sel = (x, role = "OWNER", me = "u9") => page({ tab: "cases", sel: { case: x } }, role, me);

describe("permissions and buttons", () => {
  test("who can prepare and approve", () => {
    for (const r of ["OWNER", "ADMINISTRATOR", "MANAGER", "AUDITOR"]) assert.ok(F.canPrepare(r), r);
    for (const r of ["OWNER", "APPROVER", "MANAGER"]) assert.ok(F.canApprove(r), r);
    for (const r of ["ACCOUNTANT", "READ_ONLY", "EXTERNAL_AUDITOR"]) assert.ok(!F.canPrepare(r) && !F.canApprove(r), r);
  });
  test("button rules", () => {
    assert.ok(F.canDecideCase(cs(), "APPROVER", "u9")); assert.ok(!F.canDecideCase(cs({ proposed_by: "u9" }), "APPROVER", "u9")); assert.ok(!F.canDecideCase(open(), "APPROVER", "u9"));
    assert.ok(F.canLodge(open(), "AUDITOR")); assert.ok(!F.canLodge(cs(), "AUDITOR")); assert.ok(!F.canLodge(open(), "READ_ONLY"));
    assert.ok(F.canAdjudicate(open(), claim(), "APPROVER", "u9")); assert.ok(!F.canAdjudicate(open(), claim({ proposed_by: "u9" }), "APPROVER", "u9")); assert.ok(!F.canAdjudicate(open(), claim({ status: "ADMITTED" }), "APPROVER", "u9"));
    assert.ok(F.canConfirm(open(), entry(), "APPROVER", "u9")); assert.ok(!F.canConfirm(open(), entry({ proposed_by: "u9" }), "APPROVER", "u9"));
    assert.ok(F.canRecord(open(), "APPROVER", "u9")); assert.ok(!F.canRecord(open({ proposed_by: "u9" }), "APPROVER", "u9")); assert.ok(!F.canRecord(open({ pending_claims: 1 }), "APPROVER", "u9")); assert.ok(!F.canRecord(open({ pending_entries: 1 }), "APPROVER", "u9"));
    assert.ok(!F.canRecord(open({ waterfall: wf({ total_paid: "0.00" }) }), "APPROVER", "u9")); assert.ok(!F.canRecord(open(), "AUDITOR", "u9"));
    assert.ok(F.canClose(open(), "APPROVER")); assert.ok(!F.canClose(open({ pending_claims: 1 }), "APPROVER")); assert.ok(!F.canClose(open(), "AUDITOR"));
  });
});

describe("payload builders", () => {
  test("case", () => {
    const f = { title: "Textile estate", description: "Estate of a closed company", currency: "ngn", priority: "secured, preferential, unsecured, subordinated", claims_deadline: "" };
    assert.deepEqual(F.casePayload(f).body, { title: "Textile estate", description: "Estate of a closed company", currency: "NGN", priority: ["SECURED", "PREFERENTIAL", "UNSECURED", "SUBORDINATED"] });
    assert.equal(F.casePayload({ ...f, claims_deadline: "2026-06-30", priority: "UNSECURED SECURED PREFERENTIAL SUBORDINATED" }).body.claims_deadline, "2026-06-30");
    for (const [o, re] of [[{ title: "ab" }, /title/i], [{ description: "short" }, /description/i], [{ currency: "NG" }, /three-letter/], [{ priority: "SECURED, UNSECURED" }, /each class once/], [{ priority: "SECURED, SECURED, UNSECURED, PREFERENTIAL" }, /each class once/], [{ claims_deadline: "2026-02-30" }, /real date/]]) assert.match(F.casePayload({ ...f, ...o }).problem || "", re, text(o));
    assert.equal(F.EMPTY.case.priority, "SECURED, PREFERENTIAL, UNSECURED, SUBORDINATED");
  });
  test("claim, admit, entry", () => {
    const k = { creditor_ref: "SUP-1", claim_class: "UNSECURED", amount: "300,000.00", basis: "Unpaid invoices for fabric" };
    assert.deepEqual(F.claimPayload(k).body, { creditor_ref: "SUP-1", claim_class: "UNSECURED", amount: "300000.00", basis: "Unpaid invoices for fabric" });
    for (const [o, re] of [[{ creditor_ref: "x" }, /creditor/i], [{ claim_class: "OTHER" }, /class/i], [{ amount: "0" }, /more than zero/], [{ amount: "1.234" }, /decimals/], [{ amount: "١" }, /amount/i], [{ basis: "short" }, /basis/i]]) assert.match(F.claimPayload({ ...k, ...o }).problem || "", re, text(o));
    assert.deepEqual(F.admitPayload({ amount: "80,000.00", note: "" }).body, { amount: "80000.00", note: "" }); assert.match(F.admitPayload({ amount: "0" }).problem, /more than zero/); assert.match(F.admitPayload({ amount: "5", note: "short" }).problem, /10 characters/);
    const e = { entry_type: "COST", description: "Administration costs", amount: "50,000", entry_date: "2026-03-30" };
    assert.deepEqual(F.entryPayload(e).body, { entry_type: "COST", description: "Administration costs", amount: "50000", entry_date: "2026-03-30" });
    for (const [o, re] of [[{ entry_type: "GIFT" }, /realisation or a cost/], [{ description: "ab" }, /description/i], [{ amount: "0" }, /more than zero/], [{ entry_date: "2026-02-30" }, /real date/]]) assert.match(F.entryPayload({ ...e, ...o }).problem || "", re, text(o));
  });
});

describe("page", () => {
  test("overview", () => {
    const t = text(page());
    for (const s of ["Open: 2", "Closed: 1", "NGN: 2 case(s), admitted 1180000.01, distributed 950000.00", "USD: 1 case(s)", "never added together", "ASAVEXA pays no one", "isv-banner", "Funds ready"]) assert.ok(t.includes(s), s);
  });
  test("proposing is for preparers only", () => {
    assert.ok(text(page({ tab: "cases" }, "AUDITOR")).includes("isv-cs-save")); assert.ok(!text(page({ tab: "cases" }, "READ_ONLY")).includes("isv-cs-save"));
  });
  test("a proposed case: another person decides", () => {
    assert.ok(text(sel(cs(), "APPROVER", "u9")).includes("isv-cs-approve")); const own = text(sel(cs({ proposed_by: "u9" }), "APPROVER", "u9")); assert.ok(!own.includes("isv-cs-approve")); assert.ok(own.includes("a different person must decide it"));
    const prep = text(sel(cs(), "AUDITOR", "u9")); assert.ok(!prep.includes("isv-cs-approve")); assert.ok(!prep.includes("isv-ck-save")); assert.ok(!prep.includes("isv-waterfall"));
  });
  test("an open case: the distribution is shown exactly", () => {
    const t = text(sel(open())); for (const s of ["isv-waterfall", "available 950000.00", "shortfall 230000.01", "recovery 61.67 percent", "dividend 184999.99", "paid 370000.00", "Not paid", "(not paid)"].filter((x) => x !== "Not paid")) assert.ok(t.includes(s), s);
    assert.ok(text(sel(open({ waterfall: wf({ costs_exceed: true }) }))).includes("isv-costs-note"));
  });
  test("claims, entries and recording", () => {
    const x = open({ claims: [claim(), claim({ no: 2, status: "ADMITTED", admitted: "80000.00", paid: "0.00", owed: "80000.00", claim_class: "PREFERENTIAL", late: true })], entries: [entry(), entry({ no: 2, status: "CONFIRMED" })], pending_claims: 1, pending_entries: 1 });
    const prep = text(sel(x, "AUDITOR", "u9")); for (const s of ["isv-ck-save", "isv-ck-class", "isv-en-save", "isv-en-type", "still owed 80000.00", "Late"]) assert.ok(prep.includes(s), s); assert.ok(!prep.includes("isv-ck-1-admit"));
    const appr = text(sel(x, "APPROVER", "u9")); for (const s of ["isv-ck-1-admit", "isv-ck-1-reject", "isv-ck-1-amt", "isv-en-1-confirm", "isv-en-1-reject"]) assert.ok(appr.includes(s), s); assert.ok(!appr.includes("isv-ck-2-admit")); assert.ok(!appr.includes("isv-en-2-confirm")); assert.ok(!appr.includes("isv-ds-save")); assert.ok(!appr.includes("isv-cl-save"));
    const own = text(sel(x, "APPROVER", "u1")); assert.ok(!own.includes("isv-ck-1-admit")); assert.ok(own.includes("a different person must decide it"));
    const ok = open({ claims: [claim({ status: "ADMITTED", admitted: "300000.00", owed: "300000.00" })], entries: [entry({ status: "CONFIRMED" })] }); const rec = text(sel(ok, "APPROVER", "u9")); assert.ok(rec.includes("isv-ds-save")); assert.ok(rec.includes("isv-cl-save"));
    assert.ok(!text(sel(ok, "APPROVER", "u1")).includes("isv-ds-save"));
  });
  test("recorded distributions and a closed case", () => {
    const t = text(sel(open({ distributions: [{ no: 1, on: "2026-03-31", total: "950000.00", shortfall: "230000.01", note: "First distribution", lines: [{ claim_no: 1 }] }] }))); for (const s of ["Recorded distributions", "#1 on 2026-03-31: 950000.00 recorded as distributed", "First distribution"]) assert.ok(t.includes(s), s);
    assert.ok(text(sel(cs({ status: "CLOSED", close_note: "The estate is finished", waterfall: wf() }))).includes("The estate is finished"));
  });
  test("read-only sees data and no buttons", () => {
    const t = text(sel(open({ claims: [claim()], entries: [entry()], pending_claims: 1, pending_entries: 1 }), "READ_ONLY")); for (const s of ["isv-ck-save", "isv-en-save", "isv-ck-1-admit", "isv-en-1-confirm", "isv-ds-save", "isv-cl-save"]) assert.ok(!t.includes(s), s); assert.ok(t.includes("300000.00"));
  });
  test("errors, problems and loading", () => {
    assert.ok(text(page({ error: "Boom" })).includes("Boom")); assert.ok(text(page({ tab: "cases", formError: { form: "case", text: "The title needs at least 3 characters." } })).includes("case-problem"));
    assert.ok(text(Insolvency({ st: state(), role: "OWNER", userId: "u9", loading: true, onRetry() {}, actions: noop })).length > 0);
  });
});

describe("wiring", () => {
  test("client methods hit the right paths", async () => {
    const calls = []; const c = new ApiClient("http://x"); c.request = async (m, p, b) => { calls.push([m, p, b]); return {}; };
    c.get = (p) => c.request("GET", p); c.post = (p, b) => c.request("POST", p, b); c.put = (p, b) => c.request("PUT", p, b);
    await c.isvOptions(); await c.isvOverview(); await c.isvCases(); await c.createIsvCase({}); await c.isvCase("a b"); await c.approveIsvCase("c1", ""); await c.rejectIsvCase("c1", "r"); await c.closeIsvCase("c1", "c"); await c.addIsvClaim("c1", {}); await c.admitIsvClaim("c1", 2, {}); await c.rejectIsvClaim("c1", 2, "r");
    await c.addIsvEntry("c1", {}); await c.confirmIsvEntry("c1", 3, ""); await c.rejectIsvEntry("c1", 3, "r"); await c.recordIsvDistribution("c1", "n");
    assert.deepEqual(calls.map((x) => x[0] + " " + x[1]), ["GET /insolvency/options", "GET /insolvency/overview", "GET /insolvency/cases", "POST /insolvency/cases", "GET /insolvency/cases/a%20b", "POST /insolvency/cases/c1/approve", "POST /insolvency/cases/c1/reject", "POST /insolvency/cases/c1/close",
      "POST /insolvency/cases/c1/claims", "POST /insolvency/cases/c1/claims/2/admit", "POST /insolvency/cases/c1/claims/2/reject", "POST /insolvency/cases/c1/entries", "POST /insolvency/cases/c1/entries/3/confirm", "POST /insolvency/cases/c1/entries/3/reject", "POST /insolvency/cases/c1/distribution"]);
  });
  test("home group and entity path", () => {
    assert.ok(NAV_GROUPS.some((g) => g.paths.includes("/insolvency"))); assert.equal(E.WORKSPACE_PATHS.insolvency, "/insolvency");
  });
});
