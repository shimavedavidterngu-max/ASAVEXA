import { test, describe } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { Treasury } from "../src/pages/Treasury.js";
import * as T from "../src/lib/treasury.js";
import { ApiClient } from "../src/api/client.js";
import { PERMISSIONS, can } from "../src/lib/permissions.js";
import { NAV_GROUPS } from "../src/lib/home.js";
import * as E from "../src/lib/entityConfig.js";

const text = (v) => JSON.stringify(v);
const noop = new Proxy({}, { get: () => () => {} });
const ov = (o = {}) => ({ counts: { accounts: 2, open_flows: 3, payments_waiting: 1, payments_ready: 1, payments_released: 4, covenants: 2, covenants_breached: 1 },
  position: [{ currency: "NGN", total: "1234567.50", accounts: [{ ref: "CA-001" }, { ref: "CA-002" }], accounts_without_balance: 1, stale: 1, unconfirmed: 1 }, { currency: "USD", total: "5.05", accounts: [{ ref: "CA-003" }], accounts_without_balance: 0, stale: 0, unconfirmed: 0 }],
  attention: [{ kind: "SHORTFALL", text: "NGN: cash is below zero in 2 of the next 13 weeks." }, { kind: "COVENANT_BREACH", text: "Covenant CV-001 has a breach nobody has acknowledged." }],
  limitations: ["ASAVEXA never moves money and is not connected to any bank."], policy: { minimum_cash: {}, dual_limits: { DEFAULT: "10000.00" }, stale_days: 7, meaning: "Payments at or above 10000.00 need two different approvers." }, ...o });
const acct = (o = {}) => ({ id: "a1", ref: "CA-001", name: "Main account", bank_name: "First Bank", currency: "NGN", last4: "4321", purpose: "Operations", status: "ACTIVE", stale: false, age_days: 1,
  latest_balance: { id: "b0002", as_at: "2026-02-14", amount: "10000.00", status: "RECORDED", source: "Statement", recorded_by: "u1", confirmed_by: null },
  balances: [{ id: "b0002", as_at: "2026-02-14", amount: "10000.00", status: "RECORDED", source: "Statement", recorded_by: "u1", confirmed_by: null }, { id: "b0001", as_at: "2026-02-01", amount: "9000.00", status: "CONFIRMED", source: "Statement", recorded_by: "u1", confirmed_by: "u2" }], history: [], ...o });
const pay = (o = {}) => ({ id: "p1", ref: "PR-001", account_id: "a1", account_name: "Main account", currency: "NGN", payee: "Acme", amount: "500.00", due_date: "2026-02-20", reason: "Supplies", invoice_ref: "INV-1", flags: ["NEW_PAYEE", "NO_EVIDENCE"],
  approvals_needed: 1, approvals: [], status: "REQUESTED", requested_by: "u1", released_by: null, released_date: null, bank_reference: null, overdue: false, history: [{ at: "2026-02-15T09:00", event: "REQUESTED", by: "u1", note: "" }], ...o });
const cov = (o = {}) => ({ id: "c1", ref: "CV-001", name: "Debt service cover", lender: "Big Bank", description: "x", comparator: "MIN", threshold: "1.2500", unit: "RATIO", currency: null, frequency: "QUARTERLY", watch_pct: 10, status: "ACTIVE",
  meaning: "The measured value must stay at or above 1.2500.", latest_status: "BREACHED", unacknowledged_breach: true, test_overdue: false, next_period_end: "2026-06-30", next_due: "2026-07-30", history: [],
  latest: null, results: [{ id: "r0001", period_end: "2026-03-31", value: "1.1000", status: "BREACHED", headroom_pct: "-12.0", note: "Revenue fell", recorded_by: "u1", acknowledged_by: null }], ...o });
const fc = () => ({ currencies: [{ currency: "NGN", opening: "10000.00", floor: "11000.00", floor_basis: "your minimum cash setting", lowest_closing: "7000.00", lowest_week: 1, shortfall_weeks: 1,
  warnings: ["1 balance(s) have not been confirmed by a second person."], weeks: [{ week: 1, start: "2026-02-15", end: "2026-02-21", inflow: "0.00", outflow: "3000.00", closing: "7000.00", below_floor: true, overdue_included: 0 }, { week: 2, start: "2026-02-22", end: "2026-02-28", inflow: "5000.00", outflow: "0.00", closing: "12000.00", below_floor: false, overdue_included: 0 }] }] });
const state = (o = {}) => ({ tab: "overview", options: { accounts: [{ id: "a1", ref: "CA-001", name: "Main", currency: "NGN" }], flow_categories: ["CUSTOMER_RECEIPT"], certainties: ["EXPECTED"], frequencies: ["QUARTERLY"], open_payment_flows: [] },
  ov: ov(), accounts: [acct()], flows: [], payments: [], covenants: [], vault: [], forecast: null, accuracy: { currencies: [] }, weeks: 13, possible: false, acct: null, payFilter: "",
  forms: { account: { ...T.EMPTY.account }, balance: { ...T.EMPTY.balance }, flow: { ...T.EMPTY.flow }, payment: { ...T.EMPTY.payment }, covenant: { ...T.EMPTY.covenant }, realise: {}, policy: T.policyForm(ov().policy) }, notes: {}, formError: null, busy: false, error: null, notice: null, ...o });
const page = (o = {}, role = "OWNER", me = "u9") => Treasury({ tr: state(o), role, userId: me, loading: false, onRetry() {}, actions: noop });

describe("money text", () => {
  test("fmt groups digits without touching the value", () => {
    assert.equal(T.fmt("1234567.50", "NGN"), "1,234,567.50 NGN"); assert.equal(T.fmt("-250.5"), "-250.5"); assert.equal(T.fmt("0.10"), "0.10"); assert.equal(T.fmt(null), "—"); assert.equal(T.fmt("abc"), "abc");
    assert.equal(T.fmt("999"), "999"); assert.equal(T.fmt("1000"), "1,000");
  });
  test("the helper library never does arithmetic on money", () => {
    const src = fs.readFileSync(new URL("../src/lib/treasury.js", import.meta.url), "utf8");
    assert.doesNotMatch(src, /parseFloat|toFixed|Math\.round/);
  });
  test("amounts are checked early with plain sentences", () => {
    assert.equal(T.amountProblem("1,234.50", "The amount"), ""); assert.equal(T.amountProblem("10", "The amount", { positive: true }), "");
    assert.match(T.amountProblem("", "The amount"), /required/); assert.match(T.amountProblem("1.234", "The amount"), /2 decimal/); assert.match(T.amountProblem("abc", "The amount"), /number/);
    assert.match(T.amountProblem("0", "The amount", { positive: true }), /more than zero/); assert.match(T.amountProblem("0.00", "The amount", { positive: true }), /more than zero/); assert.match(T.amountProblem("-1", "The amount"), /negative/);
    assert.equal(T.amountProblem("-1", "The balance", { allowNegative: true }), ""); assert.equal(T.amountProblem("1.2500", "T", { places: 4 }), ""); assert.match(T.amountProblem("1e5", "T"), /number/);
    assert.match(T.amountProblem("12345678901234", "T"), /number/);
  });
  test("dates must be real", () => { assert.ok(T.isRealDate("2026-02-28")); assert.ok(!T.isRealDate("2026-02-30")); assert.ok(!T.isRealDate("28/02/2026")); assert.ok(!T.isRealDate("")); });
});

describe("request builders", () => {
  test("account: name, a three-letter currency and no whole account numbers", () => {
    assert.deepEqual(T.accountPayload({ ...T.EMPTY.account, name: "Main", currency: "ngn", last4: "4321" }).body.currency, "NGN");
    assert.match(T.accountPayload({ ...T.EMPTY.account, name: "M", currency: "NGN" }).problem, /name/); assert.match(T.accountPayload({ ...T.EMPTY.account, name: "Main", currency: "NG" }).problem, /three-letter/);
    assert.match(T.accountPayload({ ...T.EMPTY.account, name: "Main", currency: "NGN", last4: "0123456789" }).problem, /last four/);
  });
  test("balance", () => {
    assert.deepEqual(T.balancePayload({ as_at: "2026-02-14", amount: "1,000.50", source: "Statement" }).body, { as_at: "2026-02-14", amount: "1000.50", source: "Statement" });
    assert.ok(T.balancePayload({ as_at: "2026-02-14", amount: "-5", source: "Statement" }).body); assert.match(T.balancePayload({ as_at: "x", amount: "1", source: "Statement" }).problem, /date/);
    assert.match(T.balancePayload({ as_at: "2026-02-14", amount: "1", source: "" }).problem, /came from/);
  });
  test("flow sends the account or a currency, never both", () => {
    const f = { ...T.EMPTY.flow, flow_date: "2026-02-24", amount: "5000", description: "Customer pays", currency: "ngn" };
    assert.equal(T.flowPayload(f).body.currency, "NGN"); assert.equal("account_id" in T.flowPayload(f).body, false);
    const g = T.flowPayload({ ...f, account_id: "a1" }).body; assert.equal(g.account_id, "a1"); assert.equal("currency" in g, false);
    assert.match(T.flowPayload({ ...f, currency: "" }).problem, /account or give/); assert.match(T.flowPayload({ ...f, amount: "0" }).problem, /more than zero/);
  });
  test("payment needs an account, payee, amount, date and reason; evidence is optional", () => {
    const f = { ...T.EMPTY.payment, account_id: "a1", payee: "Acme", amount: "500", due_date: "2026-02-20", reason: "Supplies" };
    assert.deepEqual(T.paymentPayload(f).body.evidence_ids, []); assert.deepEqual(T.paymentPayload({ ...f, evidence_id: "e1" }).body.evidence_ids, ["e1"]);
    assert.equal("flow_id" in T.paymentPayload(f).body, false); assert.equal(T.paymentPayload({ ...f, flow_id: "f1" }).body.flow_id, "f1");
    for (const bad of [{ account_id: "" }, { payee: "A" }, { amount: "0" }, { due_date: "soon" }, { reason: "no" }]) assert.ok(T.paymentPayload({ ...f, ...bad }).problem, JSON.stringify(bad));
  });
  test("release needs the bank's own reference", () => {
    assert.ok(T.releasePayload({ released_date: "2026-02-15", bank_reference: "TRX-1" }).body); assert.match(T.releasePayload({ released_date: "2026-02-15", bank_reference: "" }).problem, /reference/);
  });
  test("covenant: amount covenants need a currency, others do not send one", () => {
    const f = { ...T.EMPTY.covenant, name: "Cover", description: "Cash over debt", threshold: "1.25", effective_from: "2025-12-31" };
    assert.equal("currency" in T.covenantPayload(f).body, false); assert.equal(T.covenantPayload(f).body.watch_pct, 10);
    assert.match(T.covenantPayload({ ...f, unit: "AMOUNT" }).problem, /currency/); assert.equal(T.covenantPayload({ ...f, unit: "AMOUNT", currency: "usd" }).body.currency, "USD");
    assert.match(T.covenantPayload({ ...f, threshold: "1.23456" }).problem, /4 decimal/); assert.match(T.covenantPayload({ ...f, watch_pct: "60" }).problem, /0 to 50/);
  });
  test("result", () => {
    assert.ok(T.resultPayload({ period_end: "2026-01-31", value: "1.5", source: "Accounts", note: "" }).body); assert.match(T.resultPayload({ period_end: "2026-01-31", value: "x", source: "Accounts" }).problem, /number/);
  });
  test("policy maps", () => {
    assert.deepEqual(T.parseMap("NGN=5000, usd = 100.5; default:2,000").map, { NGN: "5000", USD: "100.5", DEFAULT: "2000" }); assert.match(T.parseMap("NGN 5000").problem, /NGN=5000/); assert.match(T.parseMap("NGN=-5").problem, /NGN=5000/);
    assert.deepEqual(T.policyPayload({ minimum_cash: "NGN=5000", dual_limits: "DEFAULT=1000", stale_days: "3" }).body, { minimum_cash: { NGN: "5000" }, dual_limits: { DEFAULT: "1000" }, stale_days: 3 });
    assert.match(T.policyPayload({ minimum_cash: "", dual_limits: "", stale_days: "0" }).problem, /1 to 90/); assert.match(T.policyPayload({ minimum_cash: "x", dual_limits: "", stale_days: "3" }).problem, /Minimum cash/);
    assert.equal(T.mapText({ NGN: "5", USD: "6" }), "NGN=5, USD=6");
  });
});

describe("who sees which button", () => {
  test("roles mirror the server", () => {
    assert.ok(can("OWNER", PERMISSIONS.TREASURY_PREPARE) && can("OWNER", PERMISSIONS.TREASURY_APPROVE)); assert.ok(can("ACCOUNTANT", PERMISSIONS.TREASURY_PREPARE) && !can("ACCOUNTANT", PERMISSIONS.TREASURY_APPROVE));
    assert.ok(can("APPROVER", PERMISSIONS.TREASURY_APPROVE) && !can("APPROVER", PERMISSIONS.TREASURY_PREPARE)); for (const r of ["AUDITOR", "READ_ONLY", "REVIEWER", "ADMINISTRATOR"]) assert.ok(!T.canPrepare(r) && !T.canApprove(r), r);
  });
  test("a requester cannot approve, reject or release their own payment; only they can cancel it", () => {
    assert.deepEqual(T.paymentMoves(pay(), "u1", "OWNER"), ["cancel"]);
    assert.deepEqual(T.paymentMoves(pay(), "u2", "OWNER"), ["approve", "reject"]);
    assert.deepEqual(T.paymentMoves(pay({ status: "APPROVED" }), "u2", "OWNER"), ["reject", "release"]);
    assert.deepEqual(T.paymentMoves(pay({ status: "APPROVED" }), "u1", "OWNER"), ["cancel"]);
  });
  test("someone who already approved cannot approve again", () => {
    assert.deepEqual(T.paymentMoves(pay({ approvals_needed: 2, approvals: [{ by: "u2" }] }), "u2", "OWNER"), ["reject"]);
    assert.deepEqual(T.paymentMoves(pay({ approvals_needed: 2, approvals: [{ by: "u2" }] }), "u3", "OWNER"), ["approve", "reject"]);
  });
  test("a finished payment has no buttons, and read-only roles have none", () => {
    for (const s of ["RELEASED", "REJECTED", "CANCELLED"]) assert.deepEqual(T.paymentMoves(pay({ status: s }), "u2", "OWNER"), [], s);
    assert.deepEqual(T.paymentMoves(pay(), "u2", "AUDITOR"), []); assert.deepEqual(T.paymentMoves(pay(), "u2", "ACCOUNTANT"), []);
  });
  test("balances and breaches", () => {
    const b = { status: "RECORDED", recorded_by: "u1" }; assert.ok(T.canConfirmBalance(b, "u2", "APPROVER")); assert.ok(!T.canConfirmBalance(b, "u1", "OWNER")); assert.ok(!T.canConfirmBalance(b, "u2", "ACCOUNTANT"));
    assert.ok(!T.canConfirmBalance({ ...b, status: "CONFIRMED" }, "u2", "OWNER"));
    const r = { status: "BREACHED", recorded_by: "u1", acknowledged_by: null }; assert.ok(T.canAcknowledge(r, "u2", "APPROVER")); assert.ok(!T.canAcknowledge(r, "u1", "OWNER"));
    assert.ok(!T.canAcknowledge({ ...r, acknowledged_by: "u2" }, "u3", "OWNER")); assert.ok(!T.canAcknowledge({ ...r, status: "MET" }, "u2", "OWNER"));
  });
  test("words", () => {
    assert.equal(T.approvalText(pay({ approvals_needed: 2, approvals: [{ by: "u2" }] })), "1 of 2 approvals given"); assert.equal(T.approvalText(pay({ status: "APPROVED" })), "");
    assert.match(T.headroomText({ headroom_pct: "-12.0" }), /beyond/); assert.match(T.headroomText({ headroom_pct: "20.0" }), /room/); assert.match(T.headroomText({ headroom_pct: null }), /zero/);
    assert.match(T.ackText({ acknowledged_by: "u2", waiver_obtained: false, acknowledgement: "Lender told" }), /no waiver/);
  });
  test("open cash flows come first, by date", () => {
    const l = T.openFirst([{ status: "REALISED", flow_date: "2026-01-01" }, { status: "OPEN", flow_date: "2026-03-01" }, { status: "OPEN", flow_date: "2026-02-01" }]);
    assert.deepEqual(l.map((x) => x.flow_date), ["2026-02-01", "2026-03-01", "2026-01-01"]);
  });
});

describe("pages", () => {
  test("the banner always says it never moves money", () => { assert.match(text(page()), /never moves money and is not connected to any bank/); });
  test("overview shows attention, each currency on its own, and the limits", () => {
    const t = text(page());
    assert.match(t, /tr-attention/); assert.match(t, /below zero in 2 of the next 13 weeks/); assert.match(t, /1,234,567\.50 NGN/); assert.match(t, /5\.05 USD/); assert.match(t, /Nothing is converted or added across currencies/);
    assert.match(t, /1 with no balance/); assert.match(t, /tr-limits/); assert.match(t, /Payments at or above/);
  });
  test("overview with nothing wrong says so", () => { assert.match(text(page({ ov: ov({ attention: [], position: [] }) })), /Nothing needs attention/); });
  test("only an approver can edit the policy", () => {
    assert.match(text(page({}, "APPROVER")), /tr-policy-save/); assert.doesNotMatch(text(page({}, "AUDITOR")), /tr-policy-save/); assert.match(text(page({}, "AUDITOR")), /Only an approver/);
  });
  test("accounts: list with status badges, and creation only for preparers", () => {
    const t = text(page({ tab: "accounts" }));
    assert.match(t, /tr-accounts/); assert.match(t, /CA-001/); assert.match(t, /Recorded, not confirmed/); assert.match(t, /tr-acct-save/);
    assert.doesNotMatch(text(page({ tab: "accounts" }, "AUDITOR")), /tr-acct-save/);
    assert.match(text(page({ tab: "accounts", accounts: [acct({ stale: true, latest_balance: null })] })), /No balance/);
  });
  test("an account's balances can be confirmed only by a different approver", () => {
    const t = text(page({ tab: "accounts", acct: acct() }, "OWNER", "u2")); assert.match(t, /tr-bal-confirm-b0002/); assert.doesNotMatch(t, /tr-bal-confirm-b0001/);
    assert.doesNotMatch(text(page({ tab: "accounts", acct: acct() }, "OWNER", "u1")), /tr-bal-confirm-/); assert.match(text(page({ tab: "accounts", acct: acct() }, "OWNER", "u1")), /Waiting for a different approver to confirm/);
    assert.doesNotMatch(text(page({ tab: "accounts", acct: acct() }, "AUDITOR", "u2")), /tr-bal-save|tr-bal-confirm/);
  });
  test("a closed account offers no new balance", () => { assert.doesNotMatch(text(page({ tab: "accounts", acct: acct({ status: "CLOSED" }) })), /tr-bal-save/); });
  test("forecast table shows every week, flags the ones below the floor, and lists warnings", () => {
    const t = text(page({ tab: "forecast", forecast: fc() }));
    assert.match(t, /data-week/); assert.match(t, /7,000\.00/); assert.match(t, /12,000\.00/); assert.match(t, /Below/); assert.match(t, /your minimum cash setting/); assert.match(t, /not been confirmed by a second person/);
    assert.match(text(page({ tab: "forecast" })), /Press Show forecast/); assert.match(text(page({ tab: "forecast", forecast: { currencies: [] } })), /Nothing to forecast/);
    for (const w of T.WEEK_CHOICES) assert.match(t, new RegExp(`${w} weeks`));
  });
  test("cash flows: add form for preparers, actions only on open ones", () => {
    const f = [{ id: "f1", ref: "CF-001", flow_date: "2026-02-24", direction: "IN", amount: "5000.00", currency: "NGN", description: "Customer", certainty: "EXPECTED", status: "OPEN", overdue: true }, { id: "f2", ref: "CF-002", flow_date: "2026-02-10", direction: "OUT", amount: "10.00", currency: "NGN", description: "Done", certainty: "CONFIRMED", status: "REALISED", actual_amount: "9.00", actual_date: "2026-02-11" }];
    const t = text(page({ tab: "forecast", flows: f })); assert.match(t, /tr-flow-happened-CF-001/); assert.doesNotMatch(t, /tr-flow-happened-CF-002/); assert.match(t, /Past its date/); assert.match(t, /tr-flow-save/);
    assert.doesNotMatch(text(page({ tab: "forecast", flows: f }, "AUDITOR")), /tr-flow-save|tr-flow-happened/);
  });
  test("payments: warnings are listed in plain words and the right buttons appear", () => {
    const t = text(page({ tab: "payments", payments: [pay()] }, "OWNER", "u2"));
    assert.match(t, /NEW_PAYEE|New payee/); assert.match(t, /No earlier payment to this payee/); assert.match(t, /No supporting document/); assert.match(t, /tr-pay-approve-PR-001/); assert.match(t, /tr-pay-reject-PR-001/); assert.doesNotMatch(t, /tr-pay-cancel-PR-001/);
    const mine = text(page({ tab: "payments", payments: [pay()] }, "OWNER", "u1")); assert.match(mine, /tr-pay-cancel-PR-001/); assert.doesNotMatch(mine, /tr-pay-approve-PR-001/);
  });
  test("an approved payment can be released by someone else, with the bank's reference", () => {
    const t = text(page({ tab: "payments", payments: [pay({ status: "APPROVED" })] }, "OWNER", "u3")); assert.match(t, /tr-pay-release-PR-001/); assert.match(t, /tr-rel-ref-PR-001/); assert.match(t, /tr-rel-date-PR-001/);
    assert.match(text(page({ tab: "payments", payments: [pay({ approvals_needed: 2, approvals: [{ by: "u2" }] })] }, "OWNER", "u3")), /1 of 2 approvals given/);
    assert.match(text(page({ tab: "payments", payments: [pay({ status: "RELEASED", released_by: "u3", released_date: "2026-02-15", bank_reference: "TRX-9" })] })), /Bank reference TRX-9/);
  });
  test("the payment form is for preparers only", () => { assert.match(text(page({ tab: "payments" })), /tr-pay-save/); assert.doesNotMatch(text(page({ tab: "payments" }, "APPROVER")), /tr-pay-save/); });
  test("covenants: a breach shows its room, who recorded it, and a second person can acknowledge it", () => {
    const c = cov(); const t = text(page({ tab: "covenants", covenants: [c] }, "OWNER", "u2"));
    assert.match(t, /Breach not acknowledged/); assert.match(t, /12\.0% beyond the limit/); assert.match(t, /tr-ack-r0001/); assert.match(t, /tr-ack-waiver-r0001/);
    const own = text(page({ tab: "covenants", covenants: [c] }, "OWNER", "u1")); assert.doesNotMatch(own, /tr-ack-r0001/); assert.match(own, /Waiting for a second person/);
    const done = cov({ unacknowledged_breach: false, results: [{ ...c.results[0], acknowledged_by: "u2", waiver_obtained: true, acknowledgement: "Waiver on file" }] });
    const d = text(page({ tab: "covenants", covenants: [done] }, "OWNER", "u3")); assert.match(d, /Acknowledged \(waiver or amendment obtained\)/); assert.match(d, /Breached/); assert.doesNotMatch(d, /tr-ack-r0001/);
  });
  test("covenant forms are for preparers; retired covenants take no result", () => {
    assert.match(text(page({ tab: "covenants", covenants: [cov()] })), /tr-res-save-CV-001/); assert.doesNotMatch(text(page({ tab: "covenants", covenants: [cov()] }, "APPROVER")), /tr-res-save|tr-cov-save/);
    assert.doesNotMatch(text(page({ tab: "covenants", covenants: [cov({ status: "RETIRED" })] })), /tr-res-save/);
  });
  test("a covenant amount field appears only for amount covenants", () => {
    const base = { ...T.EMPTY.covenant };
    assert.doesNotMatch(text(page({ tab: "covenants", forms: { ...state().forms, covenant: base } })), /tr-cov-cur/); assert.match(text(page({ tab: "covenants", forms: { ...state().forms, covenant: { ...base, unit: "AMOUNT" } } })), /tr-cov-cur/);
  });
  test("errors, notices and form problems show", () => {
    assert.match(text(page({ error: "Nope" })), /Nope/); assert.match(text(page({ notice: "Saved." })), /tr-notice/);
    assert.match(text(page({ tab: "accounts", formError: { form: "account", text: "Give the account a name." } })), /account-problem/);
    assert.match(text(Treasury({ tr: state(), role: "OWNER", userId: "u1", loading: true, onRetry() {}, actions: noop })), /Loading|loading/i);
  });
  test("every tab renders for every role without throwing", () => {
    for (const role of ["OWNER", "ADMINISTRATOR", "ACCOUNTANT", "FINANCE_OFFICER", "APPROVER", "REVIEWER", "MANAGER", "AUDITOR", "EXTERNAL_AUDITOR", "READ_ONLY"]) for (const [tab] of T.TABS)
      assert.doesNotThrow(() => page({ tab, acct: acct(), payments: [pay()], covenants: [cov()], forecast: fc() }, role, "u2"), `${role}/${tab}`);
  });
});

describe("wiring", () => {
  test("client calls the right paths and verbs", async () => {
    const calls = []; const c = new ApiClient("http://x"); c._request = async (m, p, o) => { calls.push([m, p, o && o.body, o && o.query]); return {}; };
    await c.trOverview(); await c.setTrPolicy({ stale_days: 3 }); await c.trForecast(8, true); await c.openTrAccount({ name: "A" }); await c.addTrBalance("a/1", { amount: "1" }); await c.confirmTrBalance("a1", "b1");
    await c.addTrFlow({}); await c.realiseTrFlow("f1", {}); await c.cancelTrFlow("f1", "why"); await c.trPayments("APPROVED"); await c.requestTrPayment({}); await c.trPaymentStep("p1", "approve", { note: "ok" });
    await c.addTrCovenant({}); await c.addTrResult("c1", {}); await c.ackTrBreach("c1", "r1", { note: "n" }); await c.retireTrCovenant("c1", "done"); await c.closeTrAccount("a1", "no longer");
    assert.deepEqual(calls.map((x) => x.slice(0, 2)), [["GET", "/treasury/overview"], ["PUT", "/treasury/policy"], ["GET", "/treasury/forecast"], ["POST", "/treasury/accounts"], ["POST", "/treasury/accounts/a%2F1/balances"],
      ["POST", "/treasury/accounts/a1/balances/b1/confirm"], ["POST", "/treasury/flows"], ["POST", "/treasury/flows/f1/realise"], ["POST", "/treasury/flows/f1/cancel"], ["GET", "/treasury/payments"], ["POST", "/treasury/payments"],
      ["POST", "/treasury/payments/p1/approve"], ["POST", "/treasury/covenants"], ["POST", "/treasury/covenants/c1/results"], ["POST", "/treasury/covenants/c1/results/r1/acknowledge"], ["POST", "/treasury/covenants/c1/retire"], ["POST", "/treasury/accounts/a1/close"]]);
    assert.deepEqual(calls[2][3], { weeks: 8, include_possible: "true" }); assert.deepEqual(calls[9][3], { status: "APPROVED" }); assert.deepEqual(calls[8][2], { note: "why" });
  });
  test("the page is in the menu, in the workspaces group, behind reporting:read, and can be hidden by organisation set-up", () => {
    assert.ok(NAV_GROUPS.find((g) => g.id === "workspaces").paths.includes("/treasury"));
    const app = fs.readFileSync(new URL("../src/app.js", import.meta.url), "utf8");
    assert.match(app, /path: "\/treasury", label: "Treasury and Cash", permission: PERMISSIONS\.REPORTING_READ/); assert.match(app, /path: "\/treasury", name: "treasury"/); assert.match(app, /renderTreasuryPage\(authState\)/);
    assert.match(app, /uiState\.tr = null; loadedOnce\.delete\("trLoading"\)/);
    assert.equal(E.WORKSPACE_PATHS.treasury, "/treasury");
    assert.deepEqual(E.filterNavByWorkspaces([{ path: "/treasury" }, { path: "/cyber" }], ["cyber"]).map((i) => i.path), ["/cyber"]);
  });
  test("every element id the page needs for buttons exists on the right tab", () => {
    const t = text(page({ tab: "payments", payments: [pay()] }, "OWNER", "u2")); for (const id of ["tr-pay-filter", "tr-pay-account", "tr-pay-payee", "tr-pay-amount", "tr-pay-due", "tr-pay-reason", "tr-pay-save"]) assert.ok(t.includes(id), id);
  });
});
