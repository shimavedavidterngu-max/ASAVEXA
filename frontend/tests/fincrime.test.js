import { test, describe } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { Fincrime } from "../src/pages/Fincrime.js";
import * as F from "../src/lib/fincrime.js";
import { ApiClient } from "../src/api/client.js";
import { PERMISSIONS, can } from "../src/lib/permissions.js";
import { NAV_GROUPS } from "../src/lib/home.js";
import * as E from "../src/lib/entityConfig.js";

const text = (v) => JSON.stringify(v);
const noop = new Proxy({}, { get: () => () => {} });
// people: u1 = lead (opened the case), u2 = decision-maker, u3 = second decision-maker, u9 = bystander
const decl = (o = {}) => ({ u1: { status: "NONE", note: "", at: "2026-02-15" }, u2: { status: "NONE", note: "", at: "2026-02-15" }, ...o });
const alertRec = (o = {}) => ({ id: "a1", ref: "AL-001", source: "STAFF_REPORT", summary: "A supplier asked for payment to a personal account", observed_on: "2026-02-10", amount: "2500.00", currency: "NGN", evidence: [], status: "NEW", raised_by: "u1", raised_at: "2026-02-10", case_id: null, case_ref: null, dismissed_by: null, dismissed_note: null, history: [], age_days: 5, ...o });
const screening = (o = {}) => ({ id: "s1", seq: 1, subject: "Acme Trading Ltd", subject_kind: "ORGANISATION", check: "SANCTIONS", list_name: "Internal list v3", screened_on: "2026-02-12", result: "POSSIBLE_MATCH", note: "Similar name", recorded_by: "u1", resolution: null, ...o });
const recovery = (o = {}) => ({ id: "r1", seq: 1, amount: "400.00", currency: "NGN", received_on: "2026-02-12", kind: "REPAID", note: "Part repaid", evidence: [], status: "RECORDED", recorded_by: "u1", confirmed_by: null, ...o });
const kase = (o = {}) => ({ id: "c1", ref: "CS-001", title: "Payments to a personal account", summary: "A supplier asked for payment into an account in a person's name", severity: "MEDIUM", status: "OPEN", lead: "u1", opened_by: "u1", opened_at: "2026-02-10T09:00",
  alert_ids: ["a1"], alert_refs: ["AL-001"], declarations: decl(), events: [{ id: "e1", seq: 1, occurred_on: "2026-02-10", kind: "CONTACT", text: "Supplier phoned", evidence: [{ filename: "call.pdf", file_hash: "a".repeat(64) }], recorded_by: "u1" }],
  screenings: [], losses: [], recoveries: [], decision: null, closed_on: null, outcome: null, history: [], position: [], age_days: 5, unresolved_screenings: 0, confirmed_matches: 0, ...o });
const ovw = () => ({ counts: { alerts: 2, alerts_new: 1, cases: 1, cases_open: 1, cases_closed: 0, open_by_severity: { LOW: 0, MEDIUM: 1, HIGH: 0 } }, attention: [{ kind: "ALERTS_WAITING", count: 1, text: "alert(s) have waited more than 5 days." }],
  policy: { alert_sla_days: 5, case_sla_days: 90, meaning: "An alert not looked at within 5 days is flagged." }, limitations: ["ASAVEXA records what people type in."] });
const members = [{ user_id: "u1", role: "AUDITOR", status: "ACTIVE" }, { user_id: "u2", role: "APPROVER", status: "ACTIVE" }, { user_id: "u3", role: "AUDITOR", status: "ACTIVE" }, { user_id: "u4", role: "AUDITOR", status: "REMOVED" }, { user_id: "u5", role: "OWNER", status: "ACTIVE" }];
const state = (o = {}) => ({ tab: "overview", options: {}, ov: ovw(), alerts: [alertRec()], cases: [kase()], sel: { case: null }, members, vault: [], forms: { ...JSON.parse(JSON.stringify(F.EMPTY)), policy: F.policyForm(ovw().policy) }, notes: {}, formError: null, busy: false, error: null, notice: null, ...o });
const page = (o = {}, role = "OWNER", me = "u9") => Fincrime({ fc: state(o), role, userId: me, loading: false, onRetry() {}, actions: noop });
const open = (c, o = {}) => ({ tab: "cases", cases: [c], sel: { case: c }, ...o });

describe("permissions", () => {
  test("roles follow the forensic pattern and nobody who can act is blocked from viewing", () => {
    for (const r of ["OWNER", "AUDITOR"]) assert.ok(F.canPrepare(r), r);
    for (const r of ["OWNER", "APPROVER", "MANAGER"]) assert.ok(F.canApprove(r), r);
    for (const r of ["ACCOUNTANT", "FINANCE_OFFICER", "ADMINISTRATOR", "REVIEWER", "EXTERNAL_AUDITOR", "READ_ONLY"]) assert.ok(!F.canRead(r) && !F.canPrepare(r) && !F.canApprove(r), r);
    for (const r of ["OWNER", "AUDITOR", "APPROVER", "MANAGER"]) assert.ok(F.canRead(r), r);
    assert.equal(PERMISSIONS.FINCRIME_READ, "fincrime:read"); assert.ok(!can("ACCOUNTANT", PERMISSIONS.FINCRIME_READ));
  });
  test("lead choices are active workers who declared no conflict on this case", () => {
    const c = kase({ declarations: decl({ u3: { status: "NONE" }, u5: { status: "CONFLICT" }, u4: { status: "NONE" } }) });
    assert.deepEqual(F.leadChoices(members, c).map((m) => m.user_id), ["u3"]);
    assert.deepEqual(F.leadChoices(null, c), []);
  });
  test("people are shown as You or a short id", () => { assert.equal(F.who("u1", "u1"), "You"); assert.equal(F.who("abcdefghijkl", "u1"), "abcdefgh"); assert.equal(F.who(null, "u1"), "—"); });
});

describe("payload builders", () => {
  test("amounts are positive with two places", () => {
    assert.equal(F.amountProblem("1,234.50", "x"), ""); assert.match(F.amountProblem("1.005", "x"), /2 decimal/); assert.match(F.amountProblem("0", "x"), /more than zero/); assert.match(F.amountProblem("-5", "x"), /number/); assert.match(F.amountProblem("", "x"), /required/);
  });
  test("alert", () => {
    const g = { source: "STAFF_REPORT", summary: " A supplier asked for a personal account ", observed_on: "2026-02-10", amount: "2,500.00", currency: "ngn", evidence_id: "ev1" };
    assert.deepEqual(F.alertPayload(g).body, { source: "STAFF_REPORT", summary: "A supplier asked for a personal account", observed_on: "2026-02-10", amount: "2500.00", currency: "NGN", evidence_ids: ["ev1"] });
    assert.equal("amount" in F.alertPayload({ ...g, amount: "", currency: "" }).body, false);
    for (const [k, v, re] of [["summary", "short", /at least 10/], ["observed_on", "2026-02-30", /real date/], ["amount", "1.005", /decimal/], ["currency", "N", /currency/]]) assert.match(F.alertPayload({ ...g, [k]: v }).problem, re, k);
    assert.match(F.alertPayload({ ...g, amount: "", currency: "NGN" }).problem, /needs an amount/);
  });
  test("case, declaration, event", () => {
    const g = { title: "Payments to a personal account", summary: "A supplier asked for payment into a person's account", severity: "HIGH", conflict: "no", conflict_note: "", alert_ids: ["a1"] };
    assert.deepEqual(F.casePayload(g).body, { title: g.title, summary: g.summary, severity: "HIGH", alert_ids: ["a1"] });
    assert.deepEqual(F.casePayload({ ...g, conflict: "yes", conflict_note: "The supplier is my cousin" }).body.conflict, "CONFLICT");
    for (const [k, v, re] of [["title", "abc", /title/], ["summary", "too short", /at least 20/]]) assert.match(F.casePayload({ ...g, [k]: v }).problem, re, k);
    assert.match(F.casePayload({ ...g, conflict: "yes", conflict_note: "short" }).problem, /conflict/i);
    assert.deepEqual(F.declarePayload({ status: "NONE", note: "" }).body, { status: "NONE" }); assert.match(F.declarePayload({ status: "CONFLICT", note: "short" }).problem, /conflict/i);
    assert.deepEqual(F.eventPayload({ occurred_on: "2026-02-10", kind: "CONTACT", text: "Supplier phoned", evidence_id: "" }).body, { occurred_on: "2026-02-10", kind: "CONTACT", text: "Supplier phoned", evidence_ids: [] });
    assert.match(F.eventPayload({ occurred_on: "x", kind: "OTHER", text: "Supplier phoned" }).problem, /real date/); assert.match(F.eventPayload({ occurred_on: "2026-02-10", kind: "OTHER", text: "abc" }).problem, /at least 5/);
  });
  test("screening, resolution, loss, recovery, decision, lead, settings", () => {
    const s = { subject: "Acme Trading Ltd", subject_kind: "ORGANISATION", check: "SANCTIONS", list_name: "Internal list v3", screened_on: "2026-02-12", result: "POSSIBLE_MATCH", note: "Similar name" };
    assert.equal(F.screeningPayload(s).body.result, "POSSIBLE_MATCH");
    for (const [k, v, re] of [["subject", "ab", /Who or what/], ["list_name", "ab", /list/], ["screened_on", "x", /real date/], ["note", "ab", /note/]]) assert.match(F.screeningPayload({ ...s, [k]: v }).problem, re, k);
    assert.deepEqual(F.resolvePayload("FALSE_POSITIVE", " Different date of birth ").body, { outcome: "FALSE_POSITIVE", reason: "Different date of birth" }); assert.match(F.resolvePayload("CONFIRMED", "short").problem, /reason/i);
    const l = { amount: "1,000.10", currency: "ngn", occurred_on: "2026-02-01", description: "Paid to wrong account", evidence_id: "" };
    assert.deepEqual(F.lossPayload(l).body, { amount: "1000.10", currency: "NGN", occurred_on: "2026-02-01", description: "Paid to wrong account", evidence_ids: [] });
    for (const [k, v, re] of [["amount", "0", /more than zero/], ["currency", "N", /currency/], ["occurred_on", "x", /real date/], ["description", "ab", /lost/]]) assert.match(F.lossPayload({ ...l, [k]: v }).problem, re, k);
    const r = { amount: "400", currency: "ngn", received_on: "2026-02-12", kind: "REPAID", note: "Part repaid", evidence_id: "ev2" }; assert.deepEqual(F.recoveryPayload(r).body.evidence_ids, ["ev2"]);
    for (const [k, v, re] of [["amount", "x", /number/], ["received_on", "x", /real date/], ["note", "ab", /note/]]) assert.match(F.recoveryPayload({ ...r, [k]: v }).problem, re, k);
    const d = { outcome: "REFER_ONWARD", rationale: "The payment pattern needs a specialist unit to look at it", referral_to: "The financial intelligence unit" };
    assert.equal(F.decisionPayload(d).body.referral_to, "The financial intelligence unit"); assert.equal("referral_to" in F.decisionPayload({ ...d, outcome: "NO_CONCERN" }).body, false);
    assert.match(F.decisionPayload({ ...d, rationale: "short" }).problem, /at least 20/); assert.match(F.decisionPayload({ ...d, referral_to: "ab" }).problem, /referral/);
    assert.deepEqual(F.leadPayload({ lead: "u3", reason: " Handing over " }).body, { lead: "u3", reason: "Handing over" }); assert.match(F.leadPayload({ lead: "", reason: "Handing over" }).problem, /new lead/);
    assert.deepEqual(F.policyPayload({ alert_sla_days: "0", case_sla_days: "365" }).body, { alert_sla_days: 0, case_sla_days: 365 });
    for (const [k, v, re] of [["alert_sla_days", "61", /0 to 60/], ["case_sla_days", "0", /1 to 365/], ["case_sla_days", "x", /1 to 365/]]) assert.match(F.policyPayload({ alert_sla_days: "5", case_sla_days: "90", [k]: v }).problem, re, k);
  });
});

describe("which buttons a person can see", () => {
  test("declarations", () => {
    const c = kase(); assert.ok(F.needsDeclaration(c, "u9")); assert.ok(!F.needsDeclaration(c, "u1")); assert.ok(F.isCleared(c, "u1")); assert.ok(F.canDeclare(c, "u1")); assert.ok(F.canDeclare(c, "u9"));
    const k = kase({ declarations: decl({ u2: { status: "CONFLICT", note: "x" } }) }); assert.ok(F.hasConflict(k, "u2")); assert.ok(!F.canDeclare(k, "u2")); assert.ok(!F.isCleared(k, "u2"));
  });
  test("only the declared, cleared lead works the case, and not once it is closed", () => {
    assert.ok(F.canWork(kase(), "AUDITOR", "u1")); assert.ok(!F.canWork(kase(), "AUDITOR", "u3")); assert.ok(!F.canWork(kase(), "APPROVER", "u1")); assert.ok(!F.canWork(kase({ status: "CLOSED" }), "AUDITOR", "u1"));
    assert.ok(!F.canWork(kase({ declarations: {} }), "AUDITOR", "u1"));
  });
  test("deciding needs a different, cleared decision-maker who did not propose, open, lead or raise an alert", () => {
    const dec = { outcome: "NO_CONCERN", rationale: "x".repeat(25), referral_to: null, proposed_by: "u1" }, c = kase({ status: "DECISION_PROPOSED", decision: dec });
    assert.deepEqual(F.decisionMoves(c, "APPROVER", "u2", [alertRec()]), ["approve", "reject"]);
    assert.deepEqual(F.decisionMoves(c, "OWNER", "u1", []), []); assert.deepEqual(F.decisionMoves(c, "APPROVER", "u9", []), []);           // the lead / not declared
    assert.deepEqual(F.decisionMoves(c, "AUDITOR", "u2", []), []);                                                                                   // cannot approve
    assert.deepEqual(F.decisionMoves(c, "APPROVER", "u2", [alertRec({ raised_by: "u2" })]), []);                                                     // raised a linked alert
    assert.deepEqual(F.decisionMoves(kase({ status: "DECISION_PROPOSED", decision: dec, opened_by: "u2", lead: "u3" }), "APPROVER", "u2", []), []);   // opened it
    assert.deepEqual(F.decisionMoves(kase({ status: "DECISION_PROPOSED", decision: dec, unresolved_screenings: 1 }), "APPROVER", "u2", []), ["reject"]);
    assert.deepEqual(F.decisionMoves(kase(), "APPROVER", "u2", []), []);
    assert.match(F.waitingText(c, "OWNER", "u1"), /different person/); assert.match(F.waitingText(c, "APPROVER", "u9"), /Declare that you have no conflict/); assert.equal(F.waitingText(c, "APPROVER", "u2"), "");
    assert.match(F.waitingText(kase({ status: "DECISION_PROPOSED", decision: dec, opened_by: "u2", lead: "u3" }), "APPROVER", "u2"), /You opened this case/);
  });
  test("screening, recovery, dismissal, reopening, lead changes", () => {
    const c = kase();
    assert.deepEqual(F.screeningMoves(c, screening(), "APPROVER", "u2"), ["false", "confirm"]); assert.deepEqual(F.screeningMoves(c, screening(), "OWNER", "u1"), []);
    assert.deepEqual(F.screeningMoves(c, screening({ result: "NO_MATCH" }), "APPROVER", "u2"), []); assert.deepEqual(F.screeningMoves(c, screening({ resolution: { outcome: "CONFIRMED" } }), "APPROVER", "u2"), []);
    assert.deepEqual(F.recoveryMoves(c, recovery(), "APPROVER", "u2"), ["confirm", "reject"]); assert.deepEqual(F.recoveryMoves(c, recovery({ status: "CONFIRMED" }), "APPROVER", "u2"), []); assert.deepEqual(F.recoveryMoves(c, recovery(), "OWNER", "u1"), []);
    assert.ok(F.canDismiss(alertRec(), "APPROVER", "u2")); assert.ok(!F.canDismiss(alertRec(), "OWNER", "u1")); assert.ok(!F.canDismiss(alertRec({ status: "IN_CASE" }), "APPROVER", "u2")); assert.ok(!F.canDismiss(alertRec(), "AUDITOR", "u3"));
    assert.ok(F.canReopen(kase({ status: "CLOSED" }), "APPROVER", "u2")); assert.ok(!F.canReopen(kase({ status: "CLOSED" }), "APPROVER", "u9")); assert.ok(!F.canReopen(kase(), "APPROVER", "u2"));
    assert.ok(F.canChangeLead(kase(), "APPROVER")); assert.ok(!F.canChangeLead(kase({ status: "CLOSED" }), "APPROVER")); assert.ok(!F.canChangeLead(kase(), "AUDITOR"));
    assert.ok(F.canPropose(kase(), "AUDITOR", "u1")); assert.ok(!F.canPropose(kase({ status: "DECISION_PROPOSED" }), "AUDITOR", "u1"));
  });
  test("wording", () => {
    assert.match(F.positionText({ currency: "NGN", lost: "1000.30", recovered_confirmed: "400.05", recovered_unconfirmed: "0.00", outstanding: "600.25" }), /Lost 1000.30 NGN; recovered and confirmed 400.05; waiting for confirmation 0.00; still outstanding 600.25/);
    assert.equal(F.statusOf("DECISION_PROPOSED").label, "Outcome waiting for a decision"); assert.equal(F.headline(kase()), "CS-001 · Payments to a personal account");
  });
});

describe("page", () => {
  test("banner is explicit that nothing is screened or filed and that a conflict must be declared", () => {
    const t = text(page({}, "OWNER")); assert.match(t, /does not screen anyone/); assert.match(t, /conflict of interest/); assert.match(t, /fx-banner/);
  });
  test("overview: attention, counts, targets only editable by a decision-maker", () => {
    const t = text(page({}, "APPROVER")); assert.match(t, /ALERTS_WAITING/); assert.match(t, /Open cases of medium severity: 1/); assert.match(t, /fx-policy-save/); assert.doesNotMatch(text(page({}, "AUDITOR")), /fx-policy-save/);
  });
  test("alerts: raise form for preparers only; dismiss for a different decision-maker; raiser is told", () => {
    const a = text(page({ tab: "alerts" }, "AUDITOR", "u1")); assert.match(a, /fx-al-save/); assert.doesNotMatch(a, /fx-al-AL-001-dismiss/);
    const d = text(page({ tab: "alerts" }, "APPROVER", "u2")); assert.match(d, /fx-al-AL-001-dismiss/); assert.doesNotMatch(d, /fx-al-save/); assert.match(d, /note-al-a1/);
    assert.match(text(page({ tab: "alerts" }, "OWNER", "u1")), /You raised this alert, so a different person must dismiss it/);
    assert.match(text(page({ tab: "alerts", alerts: [alertRec({ status: "DISMISSED", dismissed_by: "u2", dismissed_note: "Checked the invoice" })] }, "OWNER", "u1")), /Dismissed by.*Checked the invoice/);
  });
  test("cases: open form lists waiting alerts and asks about a conflict; hidden from decision-makers", () => {
    const t = text(page({ tab: "cases" }, "AUDITOR", "u1")); assert.match(t, /fx-case-save/); assert.match(t, /fx-case-alert-AL-001/); assert.match(t, /fx-case-conflict/); assert.match(t, /cousin|you must say now/i);
    assert.doesNotMatch(text(page({ tab: "cases" }, "APPROVER", "u2")), /fx-case-save/);
    assert.match(text(page({ tab: "cases", forms: { ...state().forms, casef: { ...F.EMPTY.casef, conflict: "yes" } } }, "AUDITOR", "u1")), /fx-case-conflict-note/);
  });
  test("case detail: a person who has not declared is asked to; a person with a conflict is told they are out", () => {
    const c = kase(); assert.match(text(page(open(c), "APPROVER", "u9")), /fx-need-declaration/); assert.match(text(page(open(c), "APPROVER", "u9")), /fx-decl-save/);
    const k = kase({ declarations: decl({ u2: { status: "CONFLICT", note: "Used to manage the supplier" } }) }); const t = text(page(open(k), "APPROVER", "u2"));
    assert.match(t, /fx-declared-conflict/); assert.doesNotMatch(t, /fx-decl-save/); assert.match(t, /Used to manage the supplier/);
  });
  test("case detail: the lead sees the working forms; others do not", () => {
    const c = kase(); const lead = text(page(open(c), "AUDITOR", "u1"));
    for (const id of ["fx-ev-save", "fx-sc-save", "fx-loss-save", "fx-rec-save", "fx-dec-save"]) assert.match(lead, new RegExp(id), id);
    const other = text(page(open(c), "AUDITOR", "u3")); for (const id of ["fx-ev-save", "fx-sc-save", "fx-loss-save", "fx-rec-save", "fx-dec-save"]) assert.doesNotMatch(other, new RegExp(id), id);
    assert.match(lead, /Supplier phoned/); assert.match(lead, /fingerprint aaaaaaaaaaaa/); assert.match(lead, /data-event/);
  });
  test("screening: resolve buttons for a different cleared decision-maker; blocked message when unresolved", () => {
    const c = kase({ screenings: [screening()], unresolved_screenings: 1 });
    const d = text(page(open(c), "APPROVER", "u2")); assert.match(d, /fx-sc-1-false/); assert.match(d, /fx-sc-1-confirm/); assert.match(d, /Waiting for a different person/);
    assert.doesNotMatch(text(page(open(c), "AUDITOR", "u1")), /fx-sc-1-false/);
    const p = kase({ status: "DECISION_PROPOSED", screenings: [screening()], unresolved_screenings: 1, decision: { outcome: "CONCERN_RESOLVED", rationale: "x".repeat(25), proposed_by: "u1", decided_by: null, rejected_note: null } });
    const t = text(page(open(p), "APPROVER", "u2")); assert.match(t, /fx-blocked/); assert.doesNotMatch(t, /fx-dec-approve/); assert.match(t, /fx-dec-reject/);
  });
  test("a decision-maker always has a reason box when they could resolve a match or reject a recovery, even with no outcome proposed", () => {
    const c = kase({ screenings: [screening()], unresolved_screenings: 1, recoveries: [recovery()] });
    assert.match(text(page(open(c), "APPROVER", "u2")), /note-case-c1/);
    assert.doesNotMatch(text(page(open(c), "APPROVER", "u9")), /note-case-c1/);                       // not declared: nothing to decide yet
    assert.doesNotMatch(text(page(open(c), "AUDITOR", "u1")), /note-case-c1/);                       // the lead decides nothing
  });
  test("losses and recoveries: exact position text; confirm for a different person", () => {
    const c = kase({ losses: [{ id: "l1", seq: 1, amount: "1000.30", currency: "NGN", occurred_on: "2026-02-01", description: "Wrong account" }], recoveries: [recovery()], position: [{ currency: "NGN", lost: "1000.30", recovered_confirmed: "0.00", recovered_unconfirmed: "400.00", outstanding: "1000.30" }] });
    const t = text(page(open(c), "APPROVER", "u2")); assert.match(t, /Lost 1000.30 NGN/); assert.match(t, /fx-rec-1-confirm/); assert.match(t, /fx-rec-1-reject/); assert.doesNotMatch(text(page(open(c), "AUDITOR", "u1")), /fx-rec-1-confirm/);
  });
  test("decision: approve and send back for a different decision-maker; reopen needs a declaration first", () => {
    const dec = { outcome: "REFER_ONWARD", rationale: "x".repeat(25), referral_to: "The financial intelligence unit", proposed_by: "u1", decided_by: null, rejected_note: null };
    const c = kase({ status: "DECISION_PROPOSED", decision: dec }); const t = text(page(open(c), "APPROVER", "u2"));
    assert.match(t, /fx-dec-approve/); assert.match(t, /fx-dec-reject/); assert.match(t, /referral to The financial intelligence unit/); assert.match(t, /note-case-c1/);
    assert.match(text(page(open(c), "OWNER", "u1")), /You proposed this outcome, so a different person must decide it/);
    const closed = kase({ status: "CLOSED", outcome: "NO_CONCERN", closed_on: "2026-02-20" });
    assert.match(text(page(open(closed), "APPROVER", "u2")), /fx-case-reopen/); assert.match(text(page(open(closed), "APPROVER", "u9")), /fx-reopen-hint/); assert.doesNotMatch(text(page(open(closed), "APPROVER", "u9")), /fx-case-reopen"/);
    assert.doesNotMatch(text(page(open(closed), "AUDITOR", "u1")), /fx-ev-save/);
  });
  test("lead change: only cleared workers are offered", () => {
    const c = kase({ declarations: decl({ u3: { status: "NONE" } }) }); const t = text(page(open(c), "APPROVER", "u2"));
    assert.match(t, /fx-lead-save/); assert.match(t, /"value":"u3"/); assert.doesNotMatch(t, /"value":"u5"/);
    assert.match(text(page(open(kase()), "APPROVER", "u2")), /No one else can take this case yet/);
  });
  test("errors, notices, loading, form problems", () => {
    assert.match(text(page({ error: "Boom" })), /Boom/); assert.match(text(page({ notice: "Saved." })), /fx-notice/);
    assert.match(text(Fincrime({ fc: state(), role: "OWNER", userId: "u1", loading: true, onRetry() {}, actions: noop })), /Loading|loading/i);
    assert.match(text(page({ tab: "alerts", formError: { form: "alert", text: "Say what was noticed." } }, "OWNER", "u1")), /alert-problem/);
  });
  test("every tab renders for every role without throwing, with and without an open case", () => {
    const full = kase({ screenings: [screening()], unresolved_screenings: 1, recoveries: [recovery()], losses: [{ id: "l1", seq: 1, amount: "1.00", currency: "NGN", occurred_on: "2026-02-01", description: "x" }],
      position: [{ currency: "NGN", lost: "1.00", recovered_confirmed: "0.00", recovered_unconfirmed: "0.40", outstanding: "1.00" }], status: "DECISION_PROPOSED", decision: { outcome: "NO_CONCERN", rationale: "x".repeat(25), proposed_by: "u1", decided_by: null, rejected_note: "Sent back once" } });
    for (const role of ["OWNER", "ADMINISTRATOR", "ACCOUNTANT", "FINANCE_OFFICER", "APPROVER", "REVIEWER", "MANAGER", "AUDITOR", "EXTERNAL_AUDITOR", "READ_ONLY"]) for (const me of ["u1", "u2", "u9"]) for (const [tab] of F.TABS)
      for (const sel of [null, full, kase({ status: "CLOSED", outcome: "NO_CONCERN" }), kase({ lead: null, declarations: {} })])
        assert.doesNotThrow(() => page({ tab, cases: sel ? [sel] : [], sel: { case: sel } }, role, me), `${role}/${me}/${tab}`);
  });
});

describe("wiring", () => {
  test("client calls the right paths and verbs", async () => {
    const calls = []; const c = new ApiClient("http://x"); c._request = async (m, p, o) => { calls.push([m, p, o && o.body]); return {}; };
    await c.fcOverview(); await c.setFcPolicy({ alert_sla_days: 3 }); await c.fcAlerts(); await c.raiseFcAlert({}); await c.dismissFcAlert("a/1", "Nothing found"); await c.fcCases(); await c.fcCase("c1"); await c.openFcCase({}); await c.declareFc("c1", {}); await c.changeFcLead("c1", {});
    await c.addFcEvent("c1", {}); await c.recordFcScreening("c1", {}); await c.resolveFcScreening("c1", "s1", {}); await c.recordFcLoss("c1", {}); await c.recordFcRecovery("c1", {}); await c.confirmFcRecovery("c1", "r1"); await c.rejectFcRecovery("c1", "r1", "Never arrived");
    await c.proposeFcDecision("c1", {}); await c.approveFcDecision("c1", "ok"); await c.rejectFcDecision("c1", "Add the third payment"); await c.reopenFcCase("c1", "New information");
    assert.deepEqual(calls.map((x) => x.slice(0, 2)), [["GET", "/fincrime/overview"], ["PUT", "/fincrime/policy"], ["GET", "/fincrime/alerts"], ["POST", "/fincrime/alerts"], ["POST", "/fincrime/alerts/a%2F1/dismiss"], ["GET", "/fincrime/cases"], ["GET", "/fincrime/cases/c1"],
      ["POST", "/fincrime/cases"], ["POST", "/fincrime/cases/c1/declaration"], ["POST", "/fincrime/cases/c1/lead"], ["POST", "/fincrime/cases/c1/events"], ["POST", "/fincrime/cases/c1/screenings"], ["POST", "/fincrime/cases/c1/screenings/s1/resolve"],
      ["POST", "/fincrime/cases/c1/losses"], ["POST", "/fincrime/cases/c1/recoveries"], ["POST", "/fincrime/cases/c1/recoveries/r1/confirm"], ["POST", "/fincrime/cases/c1/recoveries/r1/reject"],
      ["POST", "/fincrime/cases/c1/decision"], ["POST", "/fincrime/cases/c1/decision/approve"], ["POST", "/fincrime/cases/c1/decision/reject"], ["POST", "/fincrime/cases/c1/reopen"]]);
    assert.deepEqual(calls[4][2], { reason: "Nothing found" }); assert.deepEqual(calls[16][2], { reason: "Never arrived" }); assert.deepEqual(calls[18][2], { note: "ok" }); assert.deepEqual(calls[19][2], { reason: "Add the third payment" });
  });
  test("the page is in the menu behind fincrime:read, in the workspaces group, searchable, and can be hidden by organisation set-up", () => {
    assert.ok(NAV_GROUPS.find((g) => g.id === "workspaces").paths.includes("/fincrime"));
    const app = fs.readFileSync(new URL("../src/app.js", import.meta.url), "utf8");
    assert.match(app, /path: "\/fincrime", label: "Financial-crime casework", permission: PERMISSIONS\.FINCRIME_READ/); assert.match(app, /path: "\/fincrime", name: "fincrime"/); assert.match(app, /renderFincrimePage\(authState\)/);
    assert.match(app, /uiState\.fx = null; loadedOnce\.delete\("fxLoading"\)/);
    assert.equal(E.WORKSPACE_PATHS.fincrime, "/fincrime"); assert.deepEqual(E.filterNavByWorkspaces([{ path: "/fincrime" }, { path: "/cyber" }], ["cyber"]).map((i) => i.path), ["/cyber"]);
  });
  test("the page uses only the shared client and never does arithmetic on figures", () => {
    const src = fs.readFileSync(new URL("../src/pages/Fincrime.js", import.meta.url), "utf8") + fs.readFileSync(new URL("../src/lib/fincrime.js", import.meta.url), "utf8");
    assert.doesNotMatch(src, /fetch\(|XMLHttpRequest|parseFloat|toFixed|Number\((r|x|p|l|s)\.(amount|lost|outstanding|recovered)/);
  });
});
