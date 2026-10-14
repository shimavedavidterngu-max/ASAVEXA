import { test, describe } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { Secretarial } from "../src/pages/Secretarial.js";
import * as S from "../src/lib/secretarial.js";
import { ApiClient } from "../src/api/client.js";
import { NAV_GROUPS } from "../src/lib/home.js";
import * as E from "../src/lib/entityConfig.js";

const text = (v) => JSON.stringify(v);
const noop = new Proxy({}, { get: () => () => {} });
// u1 schedules and proposes, u2 records minutes and files, u3 approves, u9 bystander
const resolution = (o = {}) => ({ id: "r1", ref: "RS-001", kind: "ORDINARY", text: "That the budget for the year is approved as presented", meeting_id: "m1", meeting_ref: "MT-001", meeting_status: "HELD", can_decide: true, status: "PROPOSED", proposed_by: "u1",
  votes_for: null, votes_against: null, abstentions: null, decided_by: null, decision_note: null, withdraw_note: null, history: [], ...o });
const meeting = (o = {}) => ({ id: "m1", ref: "MT-001", kind: "BOARD", title: "Quarterly board meeting", held_on: "2026-03-12", location: "Head office", agenda: "Accounts and budget", status: "HELD", scheduled_by: "u1", attendees: "Ada Obi, Ben Eze", minutes: "The board reviewed the accounts.",
  minutes_by: "u2", evidence: [], approved_by: null, approve_note: null, cancel_note: null, record_due: false, resolutions: [resolution()], history: [], ...o });
const filing = (o = {}) => ({ id: "f1", ref: "FL-001", kind: "ANNUAL_RETURN", title: "Annual return for the year", authority: "Companies registry", due_on: "2026-04-30", owner_name: "Ada Obi", status: "OPEN", added_by: "u1", filed_on: null, filed_by: null, receipt_ref: null,
  evidence: [], confirmed_by: null, confirm_note: null, withdraw_note: null, overdue: false, due_soon: false, history: [], ...o });
const ovw = () => ({ counts: { meetings_scheduled: 0, meetings_held: 1, resolutions_passed: 0, resolutions_failed: 0, resolutions_open: 1, filings_open: 1, filings_filed: 0, filings_confirmed: 0 }, attention: [{ kind: "MINUTES_TO_APPROVE", count: 1, text: "set(s) of minutes are waiting for a different person to approve them." }],
  policy: { due_soon_days: 14, meaning: "An open filing due within 14 days is flagged as due soon." }, limitations: ["ASAVEXA checks no law."] });
const state = (o = {}) => ({ tab: "overview", options: {}, ov: ovw(), meetings: [meeting()], resolutions: [resolution()], filings: [filing()], vault: [], forms: { ...JSON.parse(JSON.stringify(S.EMPTY)), policy: S.policyForm(ovw().policy) }, notes: {}, formError: null, busy: false, error: null, notice: null, ...o });
const page = (o = {}, role = "OWNER", me = "u9") => Secretarial({ cs: state(o), role, userId: me, loading: false, onRetry() {}, actions: noop });

describe("permissions", () => {
  test("who can prepare and approve", () => {
    for (const r of ["OWNER", "ADMINISTRATOR", "MANAGER", "AUDITOR"]) assert.ok(S.canPrepare(r), r);
    for (const r of ["OWNER", "APPROVER", "MANAGER"]) assert.ok(S.canApprove(r), r);
    for (const r of ["ACCOUNTANT", "READ_ONLY", "EXTERNAL_AUDITOR"]) { assert.ok(!S.canPrepare(r), r); assert.ok(!S.canApprove(r), r); }
    assert.ok(!S.canRead("ACCOUNTANT")); assert.ok(S.canRead("AUDITOR"));
  });
});

describe("payload builders", () => {
  test("meeting and minutes", () => {
    const g = { kind: "BOARD", title: "Quarterly board", held_on: "2026-03-12", location: "Head office", agenda: "Accounts and budget" };
    assert.ok(S.meetingPayload(g).body); for (const bad of [{ title: "abc" }, { held_on: "2026-02-30" }, { location: "x" }, { agenda: "short" }]) assert.ok(S.meetingPayload({ ...g, ...bad }).problem, JSON.stringify(bad));
    assert.deepEqual(S.minutesPayload({ attendees: "Ada Obi", minutes: "The board reviewed the accounts.", evidence_id: "e1" }).body.evidence_ids, ["e1"]);
    assert.ok(S.minutesPayload({ attendees: "", minutes: "The board reviewed the accounts." }).problem); assert.ok(S.minutesPayload({ attendees: "Ada", minutes: "short" }).problem);
  });
  test("resolutions", () => {
    const g = { kind: "ORDINARY", meeting_id: "m1", text: "That the budget for the year is approved" };
    assert.equal(S.resolutionPayload(g).body.meeting_id, "m1"); assert.ok(S.resolutionPayload({ ...g, meeting_id: "" }).problem); assert.ok(S.resolutionPayload({ ...g, text: "short" }).problem);
    const w = S.resolutionPayload({ ...g, kind: "WRITTEN", meeting_id: "m1" }); assert.ok(w.body && !("meeting_id" in w.body));
  });
  test("decisions", () => {
    const g = { votes_for: "4", votes_against: "1", abstentions: "0", outcome: "PASSED", note: "Counted by the chair" };
    assert.deepEqual(S.decidePayload(g).body, { votes_for: 4, votes_against: 1, abstentions: 0, outcome: "PASSED", note: "Counted by the chair" });
    for (const bad of [{ votes_for: "x" }, { votes_for: "-1" }, { votes_for: "1.5" }, { votes_against: "" }, { note: "short" }, { votes_for: "2", votes_against: "2" }, { votes_for: "0", votes_against: "0", abstentions: "0", outcome: "FAILED" }]) assert.ok(S.decidePayload({ ...g, ...bad }).problem, JSON.stringify(bad));
    assert.equal(S.decidePayload({ ...g, votes_for: "1", votes_against: "3", outcome: "FAILED" }).body.outcome, "FAILED");
  });
  test("filings and settings", () => {
    const g = { kind: "ANNUAL_RETURN", title: "Annual return", authority: "Registry", due_on: "2026-04-30", owner_name: "Ada" };
    assert.ok(S.filingPayload(g).body); for (const bad of [{ title: "abc" }, { authority: "x" }, { due_on: "soon" }, { owner_name: "" }]) assert.ok(S.filingPayload({ ...g, ...bad }).problem);
    assert.ok(S.filedPayload({ filed_on: "2026-03-10", receipt_ref: "REG-1", evidence_id: "" }).body); assert.ok(S.filedPayload({ filed_on: "", receipt_ref: "REG-1" }).problem); assert.ok(S.filedPayload({ filed_on: "2026-03-10", receipt_ref: "x" }).problem);
    assert.ok(S.confirmPayload({ note: "Checked the receipt" }).body); assert.ok(S.confirmPayload({ note: "ok" }).problem);
    assert.equal(S.policyPayload({ due_soon_days: "30" }).body.due_soon_days, 30); for (const v of ["0", "91", "x", "", "4.5"]) assert.ok(S.policyPayload({ due_soon_days: v }).problem, v);
  });
});

describe("who sees which button", () => {
  test("separation of duties", () => {
    assert.ok(S.canRecordMinutes(meeting({ status: "SCHEDULED" }), "AUDITOR")); assert.ok(!S.canRecordMinutes(meeting(), "AUDITOR")); assert.ok(!S.canRecordMinutes(meeting({ status: "SCHEDULED" }), "APPROVER"));
    assert.ok(S.canApproveMinutes(meeting(), "APPROVER", "u3")); assert.ok(!S.canApproveMinutes(meeting(), "MANAGER", "u2")); assert.ok(!S.canApproveMinutes(meeting({ status: "MINUTES_APPROVED" }), "APPROVER", "u3"));
    assert.ok(S.canCancelMeeting(meeting({ status: "SCHEDULED" }), "APPROVER")); assert.ok(!S.canCancelMeeting(meeting(), "APPROVER"));
    assert.ok(S.canDecide(resolution(), "APPROVER", "u3")); assert.ok(!S.canDecide(resolution(), "MANAGER", "u1")); assert.ok(!S.canDecide(resolution({ can_decide: false }), "APPROVER", "u3"));
    assert.ok(S.canWithdrawResolution(resolution(), "APPROVER")); assert.ok(!S.canWithdrawResolution(resolution({ status: "PASSED" }), "APPROVER"));
    assert.ok(S.canFile(filing(), "AUDITOR")); assert.ok(!S.canFile(filing({ status: "FILED" }), "AUDITOR"));
    const f = filing({ status: "FILED", filed_by: "u2" }); assert.ok(S.canConfirm(f, "APPROVER", "u3")); assert.ok(!S.canConfirm(f, "MANAGER", "u2")); assert.ok(!S.canConfirm(filing(), "APPROVER", "u3"));
    assert.ok(S.canWithdrawFiling(filing(), "APPROVER")); assert.ok(!S.canWithdrawFiling(f, "APPROVER"));
  });
});

describe("page", () => {
  test("overview", () => {
    const t = text(page()); for (const id of ["cs-attention", "cs-counts", "cs-policy", "cs-limits", "cs-banner"]) assert.match(t, new RegExp(id));
    assert.match(t, /Meetings held: 1/); assert.match(t, /cs-policy-save/); assert.doesNotMatch(text(page({}, "AUDITOR", "u1")), /cs-policy-save/);
  });
  test("meetings tab", () => {
    const t = (role, me, o = {}) => text(page({ tab: "meetings", ...o }, role, me));
    assert.match(t("AUDITOR", "u1"), /cs-mt-save/); assert.doesNotMatch(t("APPROVER", "u3"), /cs-mt-save/);
    assert.match(t("APPROVER", "u3"), /cs-mt-MT-001-approve/); assert.doesNotMatch(t("MANAGER", "u2"), /cs-mt-MT-001-approve/); assert.match(t("MANAGER", "u2"), /different person/);
    const sch = { meetings: [meeting({ status: "SCHEDULED", minutes: null, attendees: null, record_due: true, resolutions: [] })] };
    assert.match(t("AUDITOR", "u2", sch), /cs-mt-MT-001-minutes/); assert.match(t("APPROVER", "u3", sch), /cs-mt-MT-001-cancel/); assert.match(t("AUDITOR", "u2", sch), /No minutes yet/);
  });
  test("resolutions tab", () => {
    const t = (role, me, o = {}) => text(page({ tab: "resolutions", ...o }, role, me));
    assert.match(t("APPROVER", "u3"), /cs-rs-RS-001-decide/); assert.doesNotMatch(t("MANAGER", "u1"), /cs-rs-RS-001-decide/); assert.match(t("MANAGER", "u1"), /different person/);
    assert.match(t("APPROVER", "u3", { resolutions: [resolution({ can_decide: false })] }), /once minutes of the meeting are recorded/);
    assert.match(t("AUDITOR", "u1"), /cs-rs-save/); assert.match(t("AUDITOR", "u1"), /cs-rs-meeting/);
    const written = t("AUDITOR", "u1", { forms: { ...state().forms, resolution: { kind: "WRITTEN", meeting_id: "", text: "" } } }); assert.match(written, /cs-rs-save/); assert.doesNotMatch(written, /cs-rs-meeting/);
    assert.match(t("AUDITOR", "u1", { resolutions: [resolution({ status: "PASSED", votes_for: 4, votes_against: 1, abstentions: 0, decision_note: "Counted" })] }), /Votes: 4 for, 1 against/);
  });
  test("filings tab", () => {
    const t = (role, me, o = {}) => text(page({ tab: "filings", ...o }, role, me));
    assert.match(t("AUDITOR", "u2"), /cs-fl-FL-001-file/); assert.match(t("AUDITOR", "u2"), /cs-fl-save/);
    const filed = { filings: [filing({ status: "FILED", filed_on: "2026-03-10", filed_by: "u2", receipt_ref: "REG-1" })] };
    assert.match(t("APPROVER", "u3", filed), /cs-fl-FL-001-confirm/); assert.doesNotMatch(t("MANAGER", "u2", filed), /cs-fl-FL-001-confirm/); assert.match(t("MANAGER", "u2", filed), /different person/);
    const bad = t("AUDITOR", "u2", { filings: [filing({ overdue: true, due_soon: true })], formError: { form: "filing", text: "Bad date" } });
    assert.match(bad, /Overdue/); assert.match(bad, /Due soon/); assert.match(bad, /filing-problem/); assert.doesNotMatch(bad, /object Object/);
  });
  test("every tab, role and person renders", () => {
    const full = { meetings: [meeting(), meeting({ id: "m2", ref: "MT-002", status: "SCHEDULED", minutes: null, record_due: true, resolutions: [] }), meeting({ id: "m3", ref: "MT-003", status: "MINUTES_APPROVED", approved_by: "u3", approve_note: "Fine" }), meeting({ id: "m4", ref: "MT-004", status: "CANCELLED", cancel_note: "Moved", minutes: null })],
      resolutions: [resolution(), resolution({ id: "r2", ref: "RS-002", status: "PASSED", votes_for: 3, votes_against: 0, abstentions: 1, decision_note: "Counted" }), resolution({ id: "r3", ref: "RS-003", kind: "WRITTEN", meeting_id: null, meeting_ref: null, meeting_status: null }), resolution({ id: "r4", ref: "RS-004", status: "WITHDRAWN", withdraw_note: "Not needed" })],
      filings: [filing(), filing({ id: "f2", ref: "FL-002", status: "FILED", filed_by: "u2", filed_on: "2026-03-10", receipt_ref: "R1" }), filing({ id: "f3", ref: "FL-003", status: "CONFIRMED", filed_by: "u2", confirmed_by: "u3", confirm_note: "Checked", filed_on: "2026-03-10", receipt_ref: "R1" }), filing({ id: "f4", ref: "FL-004", status: "WITHDRAWN", withdraw_note: "Not needed" })] };
    for (const role of ["OWNER", "ADMINISTRATOR", "ACCOUNTANT", "FINANCE_OFFICER", "APPROVER", "REVIEWER", "MANAGER", "AUDITOR", "EXTERNAL_AUDITOR", "READ_ONLY"]) for (const me of ["u1", "u2", "u3", "u9"]) for (const [tab] of S.TABS)
      for (const o of [{}, full]) assert.doesNotThrow(() => page({ tab, ...o }, role, me), `${role}/${me}/${tab}`);
  });
});

describe("wiring", () => {
  test("client calls the right paths and verbs", async () => {
    const calls = []; const c = new ApiClient("http://x"); c._request = async (m, p, o) => { calls.push([m, p, o && o.body]); return {}; };
    await c.csOverview(); await c.csOptions(); await c.setCsPolicy({}); await c.csMeetings(); await c.csMeeting("m/1"); await c.scheduleCsMeeting({}); await c.recordCsMinutes("m1", {}); await c.approveCsMinutes("m1", "ok"); await c.cancelCsMeeting("m1", "Moved");
    await c.csResolutions(); await c.proposeCsResolution({}); await c.decideCsResolution("r1", {}); await c.withdrawCsResolution("r1", "No"); await c.csFilings(); await c.addCsFiling({}); await c.fileCsFiling("f1", {}); await c.confirmCsFiling("f1", "Checked"); await c.withdrawCsFiling("f1", "No");
    assert.deepEqual(calls.map((x) => x.slice(0, 2)), [["GET", "/secretarial/overview"], ["GET", "/secretarial/options"], ["PUT", "/secretarial/policy"], ["GET", "/secretarial/meetings"], ["GET", "/secretarial/meetings/m%2F1"], ["POST", "/secretarial/meetings"],
      ["POST", "/secretarial/meetings/m1/minutes"], ["POST", "/secretarial/meetings/m1/approve"], ["POST", "/secretarial/meetings/m1/cancel"], ["GET", "/secretarial/resolutions"], ["POST", "/secretarial/resolutions"], ["POST", "/secretarial/resolutions/r1/decide"],
      ["POST", "/secretarial/resolutions/r1/withdraw"], ["GET", "/secretarial/filings"], ["POST", "/secretarial/filings"], ["POST", "/secretarial/filings/f1/file"], ["POST", "/secretarial/filings/f1/confirm"], ["POST", "/secretarial/filings/f1/withdraw"]]);
    assert.deepEqual(calls[7][2], { note: "ok" }); assert.deepEqual(calls[8][2], { reason: "Moved" }); assert.deepEqual(calls[16][2], { note: "Checked" }); assert.deepEqual(calls[17][2], { reason: "No" });
  });
  test("menu wiring", () => {
    assert.ok(NAV_GROUPS.find((g) => g.id === "workspaces").paths.includes("/secretarial"));
    const app = fs.readFileSync(new URL("../src/app.js", import.meta.url), "utf8");
    assert.match(app, /path: "\/secretarial", label: "Company secretarial", permission: PERMISSIONS\.AUDIT_READ/); assert.match(app, /path: "\/secretarial", name: "secretarial"/); assert.match(app, /renderSecretarialPage\(authState\)/);
    assert.match(app, /uiState\.cs = null; loadedOnce\.delete\("csLoading"\)/);
    assert.equal(E.WORKSPACE_PATHS.secretarial, "/secretarial"); assert.deepEqual(E.filterNavByWorkspaces([{ path: "/secretarial" }, { path: "/fpa" }], ["fpa"]).map((i) => i.path), ["/fpa"]);
  });
  test("only the shared client, no fetch or float arithmetic", () => {
    const src = fs.readFileSync(new URL("../src/pages/Secretarial.js", import.meta.url), "utf8") + fs.readFileSync(new URL("../src/lib/secretarial.js", import.meta.url), "utf8");
    assert.doesNotMatch(src, /fetch\(|XMLHttpRequest|parseFloat|toFixed/);
  });
});
