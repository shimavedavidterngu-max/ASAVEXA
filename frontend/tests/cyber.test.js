import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { Cyber } from "../src/pages/Cyber.js";
import * as C from "../src/lib/cyber.js";
import { ApiClient } from "../src/api/client.js";
import { can, PERMISSIONS } from "../src/lib/permissions.js";

const text = (v) => JSON.stringify(v);
function find(v, pred, out = []) { if (!v || typeof v !== "object") return out; if (pred(v)) out.push(v); for (const c of v.children || []) find(c, pred, out); return out; }
const byId = (v, id) => find(v, (n) => n.props && n.props.id === id)[0];
const noop = new Proxy({}, { get: () => () => {} });
const POLICY = { sla_days: { CRITICAL: 7, HIGH: 30, MEDIUM: 90, LOW: 180 }, acceptance_max_days: 90, meaning: "A critical vulnerability must be fixed within 7 days." };
const SEV = C.SEVERITIES.map((s) => ({ severity: s, open: s === "HIGH" ? 1 : 0, overdue: s === "HIGH" ? 1 : 0, awaiting_verification: 0, accepted: 0, verified: 0 }));
const OV = { counts: { assets: 1, vulnerabilities_open: 1, incidents_open: 1, reviews_open: 0, acceptances_waiting: 0, fixes_waiting: 0, closures_waiting: 0, reports: 0 },
  vulnerabilities: { open: 1, overdue: 1, average_days_to_fix: null, by_severity: SEV }, incidents: { open: 1, average_days_to_contain: null }, assets: { active: 1, high_value_with_overdue_serious_vulns: ["AS-001"] },
  attention: { overdue: [{ ref: "V-001", title: "Old TLS", asset_name: "Payroll server", severity: "HIGH", days_overdue: 4 }], acceptance_expired: [] }, policy: POLICY, limitations: ["ASAVEXA does not scan, test or connect to any system."] };
const ASSET = { id: "a1", ref: "AS-001", name: "Payroll server", type: "SERVER", owner: "IT", criticality: "CRITICAL", data_class: "RESTRICTED", location: "HQ", notes: "", status: "ACTIVE", open_vulnerabilities: 1, history: [{ at: "2026-02-01T10:00:00", event: "CREATED", by: "u1" }],
  vulnerabilities: [] };
const VULN = { id: "v1", ref: "V-001", asset_id: "a1", asset_name: "Payroll server", title: "Old TLS", severity: "HIGH", status: "OPEN", cve: "", source: "scan", found_date: "2026-02-01", sla_days: 30, due: "2026-03-03", flags: ["OVERDUE"], days_overdue: 4, description: "", history: [], fixed_by: null };
const INC = { id: "i1", ref: "I-001", title: "Phish", description: "Staff clicked", category: "PHISHING", severity: "HIGH", status: "REPORTED", detected_date: "2026-02-01", asset_names: ["Payroll server"], asset_ids: ["a1"], personal_data_involved: true,
  days_to_contain: null, days_to_resolve: null, timeline: [{ date: "2026-02-01", event: "REPORTED", by: "u1", note: "" }], resolved_by: null };
const ENTRY = { id: "e1", subject: "ada", system: "Ledger", access: "Admin", decision: "PENDING", note: "", removed_by: null };
const REVIEW = { id: "r1", ref: "AR-001", name: "Q1 ledger", scope: "ledger users", due_date: "2026-03-31", status: "OPEN", overdue: false, counts: { entries: 1, pending: 1, keep: 0, remove: 0, removed_confirmed: 0 }, entries: [ENTRY], history: [], submitted_by: null, decision_note: "" };
const REPORT = { id: "p1", ref: "R-001", title: "Q1 posture", status: "SUBMITTED", version: 1, submitted_by: "u1", fingerprint: "c".repeat(64), confidentiality: "CONFIDENTIAL", decision_note: "", history: [],
  snapshot: { generated_at: "2026-02-15T09:00:00", posture: { assets: { active: 1 }, vulnerabilities: { open: 1, overdue: 1 }, incidents: { open: 1 }, reviews: { completed: 0 } }, limitations: ["Nothing is scanned."] } };
const base = (o = {}) => ({ options: { assets: [{ id: "a1", ref: "AS-001", name: "Payroll server" }], policy: POLICY }, ov: OV, assets: [ASSET], vulns: [VULN], incidents: [INC], reviews: [REVIEW], reports: [REPORT], vault: [], tab: "overview", vulnFilter: "",
  asset: null, assetForm: null, vuln: null, vulnForm: null, fixForm: null, acceptForm: null, incident: null, incidentForm: null, closeForm: { lessons_learned: "", notification_decision: "" }, review: null, reviewForm: null, entryForm: null, report: null, reportForm: null,
  notes: {}, policyForm: C.policyForm(POLICY), busy: false, error: null, notice: null, ...o });
const page = (cy, role = "OWNER", userId = "u1") => Cyber({ cy, role, userId, loading: false, onRetry() {}, actions: noop });

describe("permissions", () => {
  test("mirror the backend matrix", () => {
    for (const r of ["OWNER", "MANAGER"]) assert.ok(C.canPrepare(r) && C.canApprove(r), r);
    assert.ok(C.canPrepare("ADMINISTRATOR") && !C.canApprove("ADMINISTRATOR")); assert.ok(C.canApprove("APPROVER") && !C.canPrepare("APPROVER"));
    for (const r of ["FINANCE_OFFICER", "ACCOUNTANT", "AUDITOR", "REVIEWER", "READ_ONLY"]) assert.ok(!C.canPrepare(r) && !C.canApprove(r), r);
    assert.equal(PERMISSIONS.CYBER_PREPARE, "cyber:prepare"); assert.ok(can("OWNER", PERMISSIONS.CYBER_APPROVE));
  });
});

describe("validators", () => {
  test("dates and notes", () => {
    assert.ok(C.isRealDate("2026-02-28") && !C.isRealDate("2026-02-30") && !C.isRealDate("26-1-1"));
    assert.ok(C.noteProblem("ab") && !C.noteProblem("abc")); assert.ok(/at least 10/.test(C.noteProblem("x", "a reason", 10)));
    assert.equal(C.label("ACCEPTANCE_PENDING"), "Risk acceptance waiting"); assert.equal(C.label("SOME_NEW"), "Some new");
  });
  test("asset", () => {
    assert.ok(C.assetProblem(C.emptyAsset())); const f = { ...C.emptyAsset(), name: "Web", owner: "IT" }; assert.equal(C.assetProblem(f), null);
    assert.equal(C.assetBody({ ...f, name: " Web " }).name, "Web"); assert.ok(C.assetProblem({ ...f, type: "TOASTER" }));
    assert.equal(C.assetForm({ id: "a1", name: "W", type: "SERVER", owner: "o", criticality: "LOW", data_class: "PUBLIC" }).location, "");
  });
  test("vulnerability", () => {
    const f = { ...C.emptyVuln("a1"), title: "Old TLS", source: "scan" }; assert.equal(C.vulnProblem(f), null);
    assert.ok(C.vulnProblem({ ...f, asset_id: "" })); assert.ok(C.vulnProblem({ ...f, cve: "CVE-24-1" })); assert.equal(C.vulnProblem({ ...f, cve: "cve-2024-12345" }), null);
    assert.ok(C.vulnProblem({ ...f, found_date: "2026-13-01" })); assert.ok(!("found_date" in C.vulnBody(f))); assert.equal(C.vulnBody({ ...f, found_date: "2026-02-10" }).found_date, "2026-02-10");
    assert.ok(C.acceptProblem({ reason: "too short", until: "2026-03-01" })); assert.ok(C.acceptProblem({ reason: "x".repeat(20), until: "soon" })); assert.equal(C.acceptProblem({ reason: "x".repeat(20), until: "2026-03-01" }), null);
  });
  test("incident", () => {
    const f = { ...C.emptyIncident(), title: "Phish", description: "Staff clicked" }; assert.ok(C.incidentProblem(f)); assert.equal(C.incidentProblem({ ...f, personal_data_involved: "no" }), null);
    assert.equal(C.incidentBody({ ...f, personal_data_involved: "yes" }).personal_data_involved, true); assert.equal(C.incidentBody({ ...f, personal_data_involved: "no" }).personal_data_involved, false);
    assert.ok(C.closeProblem({ lessons_learned: "short" }, { personal_data_involved: false }));
    assert.ok(/notification/i.test(C.closeProblem({ lessons_learned: "x".repeat(20), notification_decision: "" }, { personal_data_involved: true })));
    assert.equal(C.closeProblem({ lessons_learned: "x".repeat(20), notification_decision: "" }, { personal_data_involved: false }), null);
  });
  test("review, entry, report", () => {
    assert.equal(C.reviewProblem({ name: "Q1 review", scope: "ledger", due_date: "2026-03-31" }), null); assert.ok(C.reviewProblem({ name: "Q1 review", scope: "ledger", due_date: "" }));
    assert.ok(C.entryProblem(C.emptyEntry())); assert.equal(C.entryProblem({ subject: "ada", system: "Ledger", access: "Admin" }), null);
    assert.ok(C.reportProblem({ title: "" })); assert.equal(C.reportProblem({ title: "Q1 posture" }), null);
  });
  test("policy", () => {
    const f = C.policyForm(POLICY); assert.equal(C.policyProblem(f), null); assert.deepEqual(C.policyBody(f), { sla_days: POLICY.sla_days, acceptance_max_days: 90 });
    assert.ok(/longer/.test(C.policyProblem({ ...f, s_CRITICAL: "60", s_HIGH: "30" }))); assert.ok(C.policyProblem({ ...f, s_LOW: "0" })); assert.ok(C.policyProblem({ ...f, s_LOW: "1.5" })); assert.ok(C.policyProblem({ ...f, max: "400" }));
  });
});

describe("who may press which button (second-person rule)", () => {
  test("vulnerabilities", () => {
    const fixed = { ...VULN, status: "FIXED", fixed_by: "u1" };
    assert.ok(C.vulnMoves(fixed, "OWNER", "u1").ownFix && !C.vulnMoves(fixed, "OWNER", "u1").verify); assert.ok(C.vulnMoves(fixed, "APPROVER", "u2").verify);
    assert.ok(!C.vulnMoves(fixed, "ADMINISTRATOR", "u2").verify); assert.ok(C.vulnMoves(VULN, "ADMINISTRATOR", "u2").start); assert.ok(!C.vulnMoves(VULN, "APPROVER", "u2").start);
    const pend = { ...VULN, status: "ACCEPTANCE_PENDING", accept_requested_by: "u1" };
    assert.ok(C.vulnMoves(pend, "MANAGER", "u1").ownAccept && !C.vulnMoves(pend, "MANAGER", "u1").decideAccept); assert.ok(C.vulnMoves(pend, "APPROVER", "u2").decideAccept);
    assert.ok(C.vulnMoves({ ...VULN, status: "ACCEPTED" }, "MANAGER", "u1").reopen);
  });
  test("incidents, reviews, reports", () => {
    const res = { ...INC, status: "RESOLVED", resolved_by: "u1" };
    assert.ok(C.incidentMoves(res, "OWNER", "u1").ownResolve && !C.incidentMoves(res, "OWNER", "u1").close); assert.ok(C.incidentMoves(res, "APPROVER", "u2").close);
    assert.ok(C.incidentMoves({ ...INC, status: "REPORTED" }, "ADMINISTRATOR", "u1").investigate); assert.ok(!C.incidentMoves({ ...INC, status: "CLOSED" }, "OWNER", "u1").note);
    const sub = { ...REVIEW, status: "SUBMITTED", submitted_by: "u1" };
    assert.ok(C.reviewMoves(sub, "OWNER", "u1").own && !C.reviewMoves(sub, "OWNER", "u1").decide); assert.ok(C.reviewMoves(sub, "APPROVER", "u2").decide); assert.ok(C.reviewMoves(REVIEW, "OWNER", "u1").submit && !C.reviewMoves(sub, "OWNER", "u1").submit);
    assert.ok(C.reportMoves(REPORT, "APPROVER", "u2").decide && C.reportMoves(REPORT, "OWNER", "u1").own); assert.ok(C.reportMoves({ ...REPORT, status: "APPROVED" }, "AUDITOR", "u9").exportable);
    assert.ok(!C.reportMoves({ ...REPORT, status: "DRAFT" }, "AUDITOR", "u9").submit);
  });
});

describe("page", () => {
  test("overview shows counts, overdue, exposure, policy and limits; only approvers see the policy form", () => {
    const v = page(base());
    assert.match(text(byId(v, "cy-counts")), /1 active asset/); assert.match(text(byId(v, "cy-overdue")), /4 day\(s\) overdue/); assert.match(text(byId(v, "cy-exposed")), /AS-001 Payroll server/);
    assert.match(text(v), /does not scan/); assert.equal(find(v, (n) => n.props && n.props["data-sev"]).length, 4); assert.ok(byId(v, "pol-save"));
    assert.ok(!byId(page(base(), "AUDITOR"), "pol-save")); assert.ok(!byId(page(base(), "ADMINISTRATOR"), "pol-save"));
  });
  test("asset list and detail by role", () => {
    const v = page(base({ tab: "assets" })); assert.ok(byId(v, "as-new")); assert.equal(find(v, (n) => n.props && n.props["data-asset"]).length, 1); assert.ok(!byId(page(base({ tab: "assets" }), "AUDITOR"), "as-new"));
    const d = page(base({ tab: "assets", asset: { ...ASSET, vulnerabilities: [VULN] } })); assert.ok(byId(d, "as-newvuln") && byId(d, "as-retire") && byId(d, "as-vuln-v1")); assert.match(text(d), /Overdue 4d/);
    assert.ok(!byId(page(base({ tab: "assets", asset: ASSET }), "AUDITOR"), "as-retire"));
    assert.ok(byId(page(base({ tab: "assets", assetForm: C.emptyAsset() })), "asf-save"));
  });
  test("vulnerability form, filter and detail", () => {
    assert.ok(byId(page(base({ tab: "vulns" })), "vl-new")); assert.equal(find(page(base({ tab: "vulns", vulnFilter: "FIXED" })), (n) => n.props && n.props["data-vuln"]).length, 0);
    assert.ok(byId(page(base({ tab: "vulns", vulnForm: C.emptyVuln("") })), "vf-save"));
    const d = page(base({ tab: "vulns", vuln: VULN })); assert.ok(byId(d, "v-start") && byId(d, "v-fix") && byId(d, "v-accept")); assert.match(text(byId(d, "v-summary")), /Fix due 2026-03-03/);
    assert.ok(byId(page(base({ tab: "vulns", vuln: VULN, fixForm: { note: "", evidence_ids: [] } })), "fx-save")); assert.ok(byId(page(base({ tab: "vulns", vuln: VULN, acceptForm: { reason: "", until: "" } })), "ac-save"));
    const fixed = { ...VULN, status: "FIXED", fixed_by: "u1", fix_note: "patched" };
    assert.ok(byId(page(base({ tab: "vulns", vuln: fixed }), "OWNER", "u1"), "v-ownfix")); assert.ok(!byId(page(base({ tab: "vulns", vuln: fixed }), "OWNER", "u1"), "v-verify"));
    const other = page(base({ tab: "vulns", vuln: fixed }), "APPROVER", "u2"); assert.ok(byId(other, "v-verify") && byId(other, "v-reject-fix") && !byId(other, "v-fix"));
    const pend = page(base({ tab: "vulns", vuln: { ...VULN, status: "ACCEPTANCE_PENDING", accept_requested_by: "u1", accept_until_requested: "2026-04-01", accept_reason: "x" } }), "APPROVER", "u2"); assert.ok(byId(pend, "v-acc-approve") && byId(pend, "v-acc-reject") && byId(pend, "v-acc-pending"));
  });
  test("incident detail: the notification decision field appears only when personal data is involved", () => {
    const res = { ...INC, status: "RESOLVED", resolved_by: "u1", root_cause: "weak password" };
    const a = page(base({ tab: "incidents", incident: res }), "APPROVER", "u2"); assert.ok(byId(a, "cl-lessons") && byId(a, "cl-decision") && byId(a, "i-close") && byId(a, "i-reopen"));
    assert.ok(!byId(page(base({ tab: "incidents", incident: { ...res, personal_data_involved: false } }), "APPROVER", "u2"), "cl-decision"));
    const own = page(base({ tab: "incidents", incident: res }), "OWNER", "u1"); assert.ok(byId(own, "i-ownresolve") && !byId(own, "i-close"));
    assert.ok(byId(page(base({ tab: "incidents", incident: INC })), "i-investigate")); assert.ok(byId(page(base({ tab: "incidents", incident: { ...INC, status: "CONTAINED" } })), "i-resolve"));
    assert.ok(byId(page(base({ tab: "incidents", incident: INC })), "tl-add")); assert.ok(!byId(page(base({ tab: "incidents", incident: { ...INC, status: "CLOSED", lessons_learned: "x".repeat(20) } })), "tl-add"));
    assert.ok(byId(page(base({ tab: "incidents", incidentForm: C.emptyIncident() })), "if-save"));
  });
  test("access review: edit, confirm removal, second-person approval", () => {
    const d = page(base({ tab: "reviews", review: REVIEW, entryForm: C.emptyEntry() })); assert.ok(byId(d, "en-keep-e1") && byId(d, "en-remove-e1") && byId(d, "en-add") && byId(d, "rv-submit"));
    const rem = { ...REVIEW, entries: [{ ...ENTRY, decision: "REMOVE" }] }; assert.ok(byId(page(base({ tab: "reviews", review: rem })), "en-removed-e1"));
    const sub = { ...REVIEW, status: "SUBMITTED", submitted_by: "u1" };
    assert.ok(byId(page(base({ tab: "reviews", review: sub }), "OWNER", "u1"), "rv-own")); assert.ok(!byId(page(base({ tab: "reviews", review: sub }), "OWNER", "u1"), "rv-approve"));
    assert.ok(byId(page(base({ tab: "reviews", review: sub }), "APPROVER", "u2"), "rv-approve")); assert.ok(!byId(page(base({ tab: "reviews", review: sub }), "APPROVER", "u2"), "en-keep-e1"));
    assert.ok(byId(page(base({ tab: "reviews", reviewForm: C.emptyReview() })), "rvf-save"));
  });
  test("reports: freeze, approve by another person, export only when approved", () => {
    const d = page(base({ tab: "reports", report: REPORT }), "APPROVER", "u2"); assert.match(text(byId(d, "rep-figures")), /1 active asset/); assert.ok(byId(d, "rd-approve") && !byId(d, "rep-export"));
    assert.ok(byId(page(base({ tab: "reports", report: REPORT }), "OWNER", "u1"), "rep-own"));
    assert.ok(byId(page(base({ tab: "reports", report: { ...REPORT, status: "APPROVED" } }), "AUDITOR", "u9"), "rep-export"));
    assert.ok(byId(page(base({ tab: "reports", report: { ...REPORT, status: "DRAFT", snapshot: null } })), "rep-submit")); assert.ok(byId(page(base({ tab: "reports", reportForm: { title: "" } })), "rp-save"));
  });
  test("loading, error and tab buttons", () => {
    assert.match(text(Cyber({ cy: base(), role: "OWNER", userId: "u1", loading: true, onRetry() {}, actions: noop })), /Loading|loading/);
    assert.match(text(page(base({ error: "Boom" }))), /Boom/); for (const [id] of C.TABS) assert.ok(byId(page(base()), `cy-tab-${id}`), id);
  });
});

describe("api client", () => {
  function client() {
    const calls = []; const c = new ApiClient({ baseUrl: "http://x", getToken: () => "tok", fetchImpl: async (url, init = {}) => { calls.push({ url, method: init.method || "GET", body: init.body }); return new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } }); } });
    return { c, calls };
  }
  test("paths and verbs", async () => {
    const { c, calls } = client();
    await c.cyOptions(); await c.setCyPolicy({ a: 1 }); await c.createCyAsset({ name: "w" }); await c.updateCyAsset("a 1", {}); await c.retireCyAsset("a1", "gone"); await c.cyVulns("OPEN", "", "a1"); await c.cyVulnStep("v1", "acceptance/approve", { note: "ok" });
    await c.cyIncidentStep("i1", "close", { lessons_learned: "x" }); await c.decideCyEntry("r1", "e1", "REMOVE", "n"); await c.confirmCyRemoved("r1", "e1"); await c.cyReviewStep("r1", "submit"); await c.approveCyReport("p1", "ok");
    const m = calls.map((x) => `${x.method} ${x.url.replace("http://x", "")}`);
    assert.deepEqual(m, ["GET /cyber/options", "PUT /cyber/policy", "POST /cyber/assets", "PUT /cyber/assets/a%201", "POST /cyber/assets/a1/retire", "GET /cyber/vulnerabilities?status=OPEN&asset_id=a1", "POST /cyber/vulnerabilities/v1/acceptance/approve",
      "POST /cyber/incidents/i1/close", "POST /cyber/reviews/r1/entries/e1/decide", "POST /cyber/reviews/r1/entries/e1/removed", "POST /cyber/reviews/r1/submit", "POST /cyber/reports/p1/approve"]);
    assert.deepEqual(JSON.parse(calls[8].body), { decision: "REMOVE", note: "n" });
  });
  test("export sends the bearer token and falls back to a file name", async () => {
    let seen; const c = new ApiClient({ baseUrl: "http://x", getToken: () => "tok", fetchImpl: async (url, init) => { seen = init; return new Response("a,b", { status: 200 }); } });
    const r = await c.exportCyReport("p1"); assert.equal(seen.headers.Authorization, "Bearer tok"); assert.equal(r.filename, "posture-report.csv");
    const bad = new ApiClient({ baseUrl: "http://x", getToken: () => "t", fetchImpl: async () => new Response(JSON.stringify({ detail: "Approve it first." }), { status: 409 }) });
    await assert.rejects(() => bad.exportCyReport("p1"), (e) => e.status === 409);
  });
});
