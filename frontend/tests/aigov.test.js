import { test, describe } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { AiGovernance } from "../src/pages/AiGovernance.js";
import * as G from "../src/lib/aigov.js";
import { ApiClient } from "../src/api/client.js";
import { PERMISSIONS, can } from "../src/lib/permissions.js";
import { NAV_GROUPS } from "../src/lib/home.js";
import * as E from "../src/lib/entityConfig.js";

const text = (v) => JSON.stringify(v);
const noop = new Proxy({}, { get: () => () => {} });
// u1 proposes/records, u2 prepares too, u3 approves, u9 bystander
const system = (o = {}) => ({ id: "s1", ref: "AI-001", name: "Invoice reader", description: "Reads supplier invoices and suggests the account", origin: "VENDOR", vendor_name: "Acme AI", intended_use: "Suggest accounts for invoices", out_of_scope: "Must not post entries on its own",
  risk_tier: "LIMITED", data_categories: null, human_oversight: null, owner_name: "Ada Obi", status: "PROPOSED", proposed_by: "u1", proposed_at: "2026-02-01", decided_by: null, decision_note: null, last_reviewed_on: null, history: [], review_due: false, changes: 0, pending_changes: 0, incidents: 0, open_incidents: 0, ...o });
const change = (o = {}) => ({ id: "c1", ref: "MC-001", system_id: "s1", system_ref: "AI-001", system_name: "Invoice reader", risk_tier: "LIMITED", change_kind: "MODEL_UPDATE", from_version: "1.0", to_version: "1.1", description: "The vendor released a new version", effective_on: "2026-02-10", testing_summary: "Ran 50 sample invoices", evidence: [], status: "RECORDED", recorded_by: "u1", decided_by: null, decision_note: null, history: [], ...o });
const incident = (o = {}) => ({ id: "i1", ref: "AX-001", system_id: "s1", system_ref: "AI-001", system_name: "Invoice reader", incident_kind: "WRONG_OUTPUT", severity: "LOW", description: "The suggested account was wrong for a batch", occurred_on: "2026-02-08", discovered_on: "2026-02-09", harm: null, people_affected: null,
  evidence: [], status: "RECORDED", recorded_by: "u1", cause: null, corrective_action: null, void_note: null, history: [], age_days: 1, review_overdue: false, ...o });
const ovw = () => ({ counts: { systems_approved: 1, systems_high: 0, systems_limited: 1, systems_minimal: 0, changes_approved: 0, incidents: 1, incidents_open: 1 }, attention: [{ kind: "INCIDENTS_TO_REVIEW", count: 1, text: "incident(s) are waiting for a different person to review them." }],
  policy: { review_days: 180, incident_review_days: 7, meaning: "An approved AI system not reviewed for 180 days is flagged as due." }, limitations: ["ASAVEXA connects to no AI system."] });
const state = (o = {}) => ({ tab: "overview", options: {}, ov: ovw(), systems: [system({ status: "APPROVED" })], changes: [change()], incidents: [incident()], sel: { system: null, incident: null }, vault: [],
  forms: { ...JSON.parse(JSON.stringify(G.EMPTY)), policy: G.policyForm(ovw().policy) }, notes: {}, formError: null, busy: false, error: null, notice: null, ...o });
const page = (o = {}, role = "OWNER", me = "u9") => AiGovernance({ gv: state(o), role, userId: me, loading: false, onRetry() {}, actions: noop });

describe("permissions", () => {
  test("roles follow the resilience pattern", () => {
    for (const r of ["OWNER", "ADMINISTRATOR", "MANAGER", "AUDITOR"]) assert.ok(G.canPrepare(r), r);
    for (const r of ["OWNER", "APPROVER", "MANAGER"]) assert.ok(G.canApprove(r), r);
    for (const r of ["ACCOUNTANT", "REVIEWER", "EXTERNAL_AUDITOR", "READ_ONLY", "DONOR", "REGULATOR", "INVESTOR_REVIEWER"]) assert.ok(!G.canPrepare(r) && !G.canApprove(r), r);
    for (const r of ["OWNER", "ADMINISTRATOR", "MANAGER", "AUDITOR", "APPROVER"]) assert.ok(G.canRead(r), r);
    assert.equal(PERMISSIONS.AIG_PREPARE, "aigov:prepare"); assert.ok(!can("ACCOUNTANT", PERMISSIONS.AUDIT_READ));
  });
});

describe("payload builders", () => {
  test("system", () => {
    const s = { ...G.EMPTY.system, name: "Invoice reader", description: "Reads supplier invoices", vendor_name: "Acme AI", intended_use: "Suggest accounts for invoices", out_of_scope: "Must not post on its own", owner_name: "Ada Obi" };
    assert.ok(G.systemPayload(s).body); assert.match(G.systemPayload({ ...s, vendor_name: "" }).problem, /vendor/); assert.ok(G.systemPayload({ ...s, origin: "IN_HOUSE", vendor_name: "" }).body);
    assert.match(G.systemPayload({ ...s, risk_tier: "HIGH" }).problem, /oversees/); assert.ok(G.systemPayload({ ...s, risk_tier: "HIGH", human_oversight: "A person checks every output" }).body);
    assert.match(G.systemPayload({ ...s, name: "abc" }).problem, /name/); assert.match(G.systemPayload({ ...s, human_oversight: "short" }).problem, /when given/); assert.ok(!("data_categories" in G.systemPayload(s).body));
  });
  test("change", () => {
    const c = { ...G.EMPTY.change, system_id: "s1", from_version: "1.0", to_version: "1.1", description: "The vendor released a new version", effective_on: "2026-02-10", testing_summary: "Ran 50 sample invoices" };
    assert.deepEqual(G.changePayload(c).body.evidence_ids, []); assert.match(G.changePayload({ ...c, system_id: "" }).problem, /Choose/); assert.match(G.changePayload({ ...c, to_version: " 1.0 " }).problem, /differ/);
    assert.match(G.changePayload({ ...c, effective_on: "2026-02-31" }).problem, /real date/); assert.match(G.changePayload({ ...c, testing_summary: "x" }).problem, /tested/); assert.deepEqual(G.changePayload({ ...c, evidence_id: "e1" }).body.evidence_ids, ["e1"]);
  });
  test("incident, review and policy", () => {
    const i = { ...G.EMPTY.incident, system_id: "s1", description: "The suggested account was wrong", occurred_on: "2026-02-08", discovered_on: "2026-02-09" };
    assert.ok(G.incidentPayload(i).body); assert.match(G.incidentPayload({ ...i, discovered_on: "2026-02-01" }).problem, /before it happened/); assert.match(G.incidentPayload({ ...i, severity: "CRITICAL" }).problem, /harm/);
    assert.equal(G.incidentPayload({ ...i, severity: "HIGH", harm: "Forty invoices were mis-posted", people_affected: "12" }).body.people_affected, 12); assert.match(G.incidentPayload({ ...i, people_affected: "-3" }).problem, /whole number/);
    assert.match(G.reviewPayload({ cause: "short", corrective_action: "x".repeat(25) }).problem, /cause/); assert.match(G.reviewPayload({ cause: "The model lacked context", corrective_action: "short" }).problem, /20/); assert.ok(G.reviewPayload({ cause: "The model lacked context", corrective_action: "x".repeat(25) }).body);
    assert.deepEqual(G.policyPayload({ review_days: "90", incident_review_days: "7" }).body, { review_days: 90, incident_review_days: 7 }); assert.match(G.policyPayload({ review_days: "10", incident_review_days: "7" }).problem, /30 to 730/); assert.match(G.policyPayload({ review_days: "90", incident_review_days: "0" }).problem, /1 to 60/);
  });
});

describe("who sees which button", () => {
  test("separation of duties", () => {
    assert.ok(G.canDecideSystem(system(), "APPROVER", "u3")); assert.ok(!G.canDecideSystem(system(), "OWNER", "u1")); assert.ok(!G.canDecideSystem(system({ status: "APPROVED" }), "APPROVER", "u3"));
    const ap = system({ status: "APPROVED" }); assert.ok(G.canReviewSystem(ap, "APPROVER", "u3")); assert.ok(!G.canReviewSystem(ap, "OWNER", "u1")); assert.ok(G.canRetireSystem(ap, "APPROVER")); assert.ok(!G.canRetireSystem({ ...ap, pending_changes: 1 }, "APPROVER")); assert.ok(!G.canRetireSystem({ ...ap, open_incidents: 1 }, "APPROVER"));
    assert.ok(G.canRecordChange(ap, "AUDITOR")); assert.ok(!G.canRecordChange(system(), "AUDITOR")); assert.ok(!G.canRecordChange(ap, "APPROVER"));
    assert.ok(G.canDecideChange(change(), "APPROVER", "u3")); assert.ok(!G.canDecideChange(change(), "OWNER", "u1")); assert.ok(G.canReviewIncident(incident(), "APPROVER", "u3")); assert.ok(!G.canReviewIncident(incident(), "OWNER", "u1")); assert.ok(!G.canReviewIncident(incident({ status: "REVIEWED" }), "APPROVER", "u3"));
    assert.match(G.ownWorkText("recorded this"), /different person must decide/); assert.match(G.useText(system()), /Not allowed: Must not post/);
  });
});

describe("page", () => {
  test("overview", () => {
    const t = text(page()); for (const id of ["gv-attention", "gv-counts", "gv-policy", "gv-limits", "gv-banner", "gv-policy-save"]) assert.match(t, new RegExp(id)); assert.match(t, /Approved AI systems: 1/);
    assert.doesNotMatch(text(page({}, "AUDITOR", "u1")), /gv-policy-save/);
  });
  test("systems", () => {
    const pr = system(); const open = (s, role, me) => text(page({ tab: "systems", systems: [s], sel: { system: s, incident: null } }, role, me));
    assert.match(text(page({ tab: "systems" }, "AUDITOR", "u1")), /gv-sys-save/); assert.doesNotMatch(text(page({ tab: "systems" }, "APPROVER", "u3")), /gv-sys-save/);
    assert.match(open(pr, "APPROVER", "u3"), /gv-system-approve/); assert.match(open(pr, "APPROVER", "u3"), /gv-system-reject/); assert.match(open(pr, "APPROVER", "u3"), /note-sys-s1/);
    assert.doesNotMatch(open(pr, "OWNER", "u1"), /gv-system-approve/); assert.match(open(pr, "OWNER", "u1"), /gv-system-waiting/);
    const ap = system({ status: "APPROVED", review_due: true }); const w = open(ap, "APPROVER", "u3"); assert.match(w, /gv-system-review/); assert.match(w, /gv-system-retire/); assert.match(w, /Review due/);
    assert.doesNotMatch(open(ap, "OWNER", "u1"), /gv-system-review/); assert.match(open(ap, "OWNER", "u1"), /gv-review-waiting/);
    assert.match(open({ ...ap, pending_changes: 1 }, "APPROVER", "u3"), /gv-retire-hint/);
  });
  test("changes and incidents", () => {
    assert.match(text(page({ tab: "changes" }, "AUDITOR", "u2")), /gv-chg-save/); assert.match(text(page({ tab: "changes", systems: [system()] }, "AUDITOR", "u2")), /No approved AI system/); assert.doesNotMatch(text(page({ tab: "changes" }, "APPROVER", "u3")), /gv-chg-save/);
    const t = text(page({ tab: "changes" }, "APPROVER", "u3")); assert.match(t, /gv-chg-MC-001-approve/); assert.match(t, /gv-chg-MC-001-reject/); assert.doesNotMatch(text(page({ tab: "changes" }, "APPROVER", "u1")), /gv-chg-MC-001-approve/); assert.match(text(page({ tab: "changes" }, "APPROVER", "u1")), /must decide it/);
    const open = (i, role, me) => text(page({ tab: "incidents", incidents: [i], sel: { system: null, incident: i } }, role, me));
    assert.match(open(incident(), "APPROVER", "u3"), /gv-inc-review/); assert.match(open(incident(), "APPROVER", "u3"), /gv-inc-void/); assert.match(open(incident(), "APPROVER", "u3"), /gv-rev-action/);
    assert.doesNotMatch(open(incident(), "OWNER", "u1"), /gv-inc-review/); assert.match(open(incident(), "OWNER", "u1"), /gv-inc-waiting/);
    assert.match(text(page({ tab: "incidents", incidents: [incident({ review_overdue: true })] }, "AUDITOR", "u2")), /Review overdue/); assert.match(text(page({ tab: "incidents" }, "AUDITOR", "u2")), /gv-inc-save/);
    const f = JSON.parse(JSON.stringify(G.EMPTY)); f.incident.severity = "CRITICAL"; assert.match(text(page({ tab: "incidents", forms: { ...state().forms, incident: f.incident } }, "AUDITOR", "u2")), /required for a high or critical/);
  });
  test("errors, notices, loading, form problems", () => {
    assert.match(text(page({ error: "Boom" })), /Boom/); assert.match(text(page({ notice: "Saved." })), /gv-notice/); assert.match(text(AiGovernance({ gv: state(), role: "OWNER", userId: "u1", loading: true, onRetry() {}, actions: noop })), /Loading|loading/i);
    assert.match(text(page({ tab: "systems", formError: { form: "system", text: "Name it." } }, "OWNER", "u1")), /system-problem/);
  });
  test("no badge is ever joined to text", () => {
    assert.doesNotMatch(text(page({ tab: "systems", systems: [system({ status: "APPROVED", review_due: true })] }, "AUDITOR", "u1")), /object Object/);
    assert.doesNotMatch(text(page({ tab: "incidents", incidents: [incident({ review_overdue: true })] }, "AUDITOR", "u1")), /object Object/);
  });
  test("every tab renders for every role and person without throwing", () => {
    const full = { systems: [system(), system({ id: "s2", ref: "AI-002", status: "APPROVED", risk_tier: "HIGH", review_due: true, human_oversight: "A person checks everything", last_reviewed_on: "2026-01-01" }), system({ id: "s3", ref: "AI-003", status: "RETIRED", decision_note: "Replaced" })],
      changes: [change(), change({ id: "c2", ref: "MC-002", status: "APPROVED", evidence: [{ filename: "t.pdf", file_hash: "a".repeat(64) }] }), change({ id: "c3", ref: "MC-003", status: "REJECTED", decision_note: "Not enough testing" })],
      incidents: [incident(), incident({ id: "i2", ref: "AX-002", status: "REVIEWED", severity: "HIGH", harm: "Mis-posted entries", people_affected: 4, cause: "Missing context", corrective_action: "Context now added to every request" }), incident({ id: "i3", ref: "AX-003", status: "VOIDED", void_note: "Wrong system" })] };
    for (const role of ["OWNER", "ADMINISTRATOR", "ACCOUNTANT", "FINANCE_OFFICER", "APPROVER", "REVIEWER", "MANAGER", "AUDITOR", "EXTERNAL_AUDITOR", "READ_ONLY"]) for (const me of ["u1", "u2", "u3", "u9"]) for (const [tab] of G.TABS)
      for (const o of [{}, full, { ...full, sel: { system: full.systems[0], incident: full.incidents[0] } }, { ...full, sel: { system: full.systems[1], incident: full.incidents[1] } }]) assert.doesNotThrow(() => page({ tab, ...o }, role, me), `${role}/${me}/${tab}`);
  });
});

describe("wiring", () => {
  test("client calls the right paths and verbs", async () => {
    const calls = []; const c = new ApiClient("http://x"); c._request = async (m, p, o) => { calls.push([m, p, o && o.body]); return {}; };
    await c.gvOverview(); await c.gvOptions(); await c.setGvPolicy({}); await c.gvSystems(); await c.gvSystem("s/1"); await c.proposeGvSystem({}); await c.approveGvSystem("s1", "ok"); await c.rejectGvSystem("s1", "No"); await c.retireGvSystem("s1", "Gone"); await c.reviewGvSystem("s1", "Fine");
    await c.gvChanges(); await c.recordGvChange({}); await c.approveGvChange("c1", "ok"); await c.rejectGvChange("c1", "No"); await c.gvIncidents(); await c.gvIncident("i1"); await c.recordGvIncident({}); await c.reviewGvIncident("i1", { cause: "x" }); await c.voidGvIncident("i1", "Twice");
    assert.deepEqual(calls.map((x) => x.slice(0, 2)), [["GET", "/aigov/overview"], ["GET", "/aigov/options"], ["PUT", "/aigov/policy"], ["GET", "/aigov/systems"], ["GET", "/aigov/systems/s%2F1"], ["POST", "/aigov/systems"], ["POST", "/aigov/systems/s1/approve"],
      ["POST", "/aigov/systems/s1/reject"], ["POST", "/aigov/systems/s1/retire"], ["POST", "/aigov/systems/s1/review"], ["GET", "/aigov/changes"], ["POST", "/aigov/changes"], ["POST", "/aigov/changes/c1/approve"], ["POST", "/aigov/changes/c1/reject"],
      ["GET", "/aigov/incidents"], ["GET", "/aigov/incidents/i1"], ["POST", "/aigov/incidents"], ["POST", "/aigov/incidents/i1/review"], ["POST", "/aigov/incidents/i1/void"]]);
    assert.deepEqual(calls[6][2], { note: "ok" }); assert.deepEqual(calls[7][2], { reason: "No" }); assert.deepEqual(calls[9][2], { note: "Fine" }); assert.deepEqual(calls[18][2], { reason: "Twice" });
  });
  test("menu wiring", () => {
    assert.ok(NAV_GROUPS.find((g) => g.id === "workspaces").paths.includes("/aigov"));
    const app = fs.readFileSync(new URL("../src/app.js", import.meta.url), "utf8");
    assert.match(app, /path: "\/aigov", label: "AI governance", permission: PERMISSIONS\.AUDIT_READ/); assert.match(app, /path: "\/aigov", name: "aigov"/); assert.match(app, /renderAigovPage\(authState\)/);
    assert.match(app, /uiState\.gv = null; loadedOnce\.delete\("gvLoading"\)/);
    assert.equal(E.WORKSPACE_PATHS.aigov, "/aigov"); assert.deepEqual(E.filterNavByWorkspaces([{ path: "/aigov" }, { path: "/fpa" }], ["fpa"]).map((i) => i.path), ["/fpa"]);
  });
  test("only the shared client, no fetch or float arithmetic", () => {
    const src = fs.readFileSync(new URL("../src/pages/AiGovernance.js", import.meta.url), "utf8") + fs.readFileSync(new URL("../src/lib/aigov.js", import.meta.url), "utf8");
    assert.doesNotMatch(src, /fetch\(|XMLHttpRequest|parseFloat|toFixed/);
  });
});
