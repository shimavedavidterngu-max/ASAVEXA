import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { Pilot } from "../src/pages/Pilot.js";
import * as P from "../src/lib/pilot.js";
import { PERMISSIONS, ROLE_PERMISSIONS } from "../src/lib/permissions.js";
import { ApiClient } from "../src/api/client.js";

const text = (v) => JSON.stringify(v);
function find(v, pred, out = []) { if (!v || typeof v !== "object") return out; if (pred(v)) out.push(v); for (const c of v.children || []) find(c, pred, out); return out; }
const byId = (v, id) => find(v, (n) => n.props && n.props.id === id)[0];
const noop = new Proxy({}, { get: () => () => {} });

const guide = { honesty: "A pilot of a few organisations shows whether it is workable for them.", time_kinds: ["AUDIT_PREP", "REPORT"], issue_kinds: ["USER_ERROR", "BUG"], severities: ["LOW", "HIGH"], passport_purposes: ["LENDER"], passport_outcomes: ["HELPFUL", "NOT_HELPFUL"],
  target_labels: { onboarding_days: "Onboarding (days)", satisfaction_score: "Satisfaction" }, default_targets: { onboarding_days: 14, satisfaction_score: 4 } };
const measure = (key, over = {}) => ({ key, label: `Label ${key}`, source: "MEASURED", value: 12.5, unit: "days", target: 14, direction: "<=", n: 3, n_what: "clients", status: "MET", why: "", detail: "", ...over });
const KEYS = ["onboarding", "processing", "evidence", "reconciliation", "exceptions", "reports", "audit_prep", "errors", "satisfaction", "adoption", "passport"];
const results = (over = {}) => ({ clients_included: 1, clients_total: 1, skipped: [], clients: [], reported: { survey: { respondents: 0, by_group: { FIRM: { n: 0 }, CLIENT: { n: 0 } } } },
  evaluation: { headline: "3 of 11 targets met", caution: "Treat results as indicative.", measures: KEYS.map((k) => measure(k)) }, ...over });
const current = (over = {}) => ({ id: "p1", name: "Lagos pilot", status: "ACTIVE", start_date: "2026-10-01", end_date: null, notes: "", targets: { onboarding_days: 14, satisfaction_score: 4 }, can_start: true, clients: [], ...over });
const firmMe = { can_manage: true, can_withdraw: true, membership: { role: "FIRM", pilots: [] } };
const clientMe = { can_manage: false, can_withdraw: true, membership: { role: "CLIENT", pilot_id: "p1", firm_org_id: "f", pilot: { id: "p1", name: "Lagos pilot", status: "ACTIVE" }, client: { label: "Bakery", kickoff: "2026-10-01T00:00:00+00:00", consent_reference: "Letter 7" } } };
const st = (over = {}) => ({ tab: null, guide, me: firmMe, current: current(), results: results(), logs: { time: [], issues: [], passport_uses: [], clients: [{ org_id: "c1", label: "Bakery" }] }, snapshots: [], form: null, busy: false, ...over });
const page = (s, loading = false) => Pilot({ pilot: s, loading, onRetry() {}, actions: noop });

describe("permission", () => {
  test("pilot:manage is held by OWNER and ADMINISTRATOR only", () => {
    assert.ok(ROLE_PERMISSIONS.OWNER.includes(PERMISSIONS.PILOT_MANAGE)); assert.ok(ROLE_PERMISSIONS.ADMINISTRATOR.includes(PERMISSIONS.PILOT_MANAGE));
    for (const r of Object.keys(ROLE_PERMISSIONS).filter((x) => !["OWNER", "ADMINISTRATOR"].includes(x))) assert.ok(!ROLE_PERMISSIONS[r].includes(PERMISSIONS.PILOT_MANAGE), r);
  });
});

describe("tabs", () => {
  test("a client never sees the firm's results, clients or set-up", () => {
    assert.deepEqual(P.tabsFor(clientMe), ["log", "survey", "about"]);
    assert.deepEqual(P.tabsFor({ can_manage: false, membership: { role: "FIRM", pilots: [] } }), ["log", "survey"]);
    assert.ok(P.tabsFor(firmMe).includes("dashboard") && P.tabsFor(firmMe).includes("report"));
    assert.deepEqual(P.tabsFor(null), ["log", "survey"]);
  });
  test("a stored tab the person may not see falls back to their first tab", () => {
    const v = text(page(st({ me: clientMe, tab: "dashboard", results: results(), current: clientMe.membership.pilot })));
    assert.ok(!v.includes("Label onboarding")); assert.ok(v.includes("Record what happened"));
  });
});

describe("results", () => {
  test("all eleven measures are drawn, each labelled measured or reported with its target and sample", () => {
    const r = results(); r.evaluation.measures[8] = measure("satisfaction", { source: "REPORTED", value: null, status: "INSUFFICIENT_DATA", why: "Needs at least 3 respondents; has 0.", n: 0, n_what: "survey respondents" });
    const v = page(st({ results: r }));
    assert.equal(find(v, (n) => n.props && n.props["data-measure"]).length, 11);
    const t = text(v);
    assert.ok(t.includes("Reported by people")); assert.ok(t.includes("Measured by the system")); assert.ok(t.includes("Not enough data yet")); assert.ok(t.includes("at most 14 days"));
    assert.equal(text(byId(v, "value-satisfaction")), text(byId(v, "value-satisfaction")));
    assert.ok(text(byId(v, "value-satisfaction")).includes("—"));         // a missing value is a dash, never 0
    assert.ok(!text(byId(v, "value-satisfaction")).includes('"0'));
  });
  test("the caution and the honesty note are always on screen", () => {
    const v = page(st()); assert.ok(text(byId(v, "pilot-caution")).includes("indicative")); assert.ok(text(byId(v, "pilot-honesty")).includes("workable"));
  });
  test("left-out clients are announced, not silently dropped", () => {
    const v = page(st({ results: results({ skipped: [{ org_id: "c2", label: "Tailor", reason: "You do not have permission" }], clients_included: 0 }) }));
    assert.ok(text(byId(v, "pilot-skipped")).includes("Tailor"));
  });
  test("valueText, targetText and tally", () => {
    assert.equal(P.valueText(measure("a", { value: 95, unit: "% of posted journals with verified evidence" })), "95% of posted journals with verified evidence"); assert.equal(P.valueText(measure("a", { value: 4.26, unit: "score" })), "4.3 score");
    assert.equal(P.valueText(measure("a", { value: null })), "—"); assert.equal(P.valueText(null), "—");
    assert.equal(P.targetText(measure("a", { direction: ">=", target: 90, unit: "% reconciled" })), "at least 90% reconciled"); assert.equal(P.targetText(measure("a")), "at most 14 days");
    assert.deepEqual(P.tally([{ status: "MET" }, { status: "NOT_MET" }, { status: "MET" }]), { MET: 2, NOT_MET: 1, INSUFFICIENT_DATA: 0 });
  });
});

describe("empty and loading states", () => {
  test("no pilot: a manager is offered set-up, anyone else is told who does it", () => {
    assert.ok(byId(page(st({ current: null, results: null })), "pilot-new-btn"));
    assert.ok(text(page(st({ current: null, me: { can_manage: false, membership: null } }))).includes("sets the pilot up"));
  });
  test("loading shows loading", () => assert.ok(text(page(st(), true)).toLowerCase().includes("loading")));
  test("an error is shown", () => assert.ok(text(page(st({ error: "Boom" }))).includes("Boom")));
});

describe("clients tab", () => {
  const withClient = { clients: [{ org_id: "c1", label: "Bakery", consent_reference: "Letter 7", active: true }, { org_id: "c2", label: "Tailor", active: false, left_reason: "moved away" }] };
  test("lists active clients, mentions withdrawn ones are excluded, and offers add", () => {
    const v = page(st({ tab: "clients", current: current(withClient) })); const t = text(v);
    assert.ok(t.includes("Letter 7")); assert.ok(t.includes("moved away")); assert.ok(t.includes("excluded from every result")); assert.ok(byId(v, "pilot-add-client"));
  });
  test("a completed pilot does not offer to add clients", () => assert.ok(!byId(page(st({ tab: "clients", current: current({ status: "COMPLETED" }) })), "pilot-add-client")));
  test("the add form requires consent wording and explains when nothing is eligible", () => {
    const v = page(st({ tab: "clients", eligible: [], form: { kind: "client", f: P.emptyClientForm() } })); const t = text(v);
    assert.ok(byId(v, "client-consent")); assert.ok(t.includes("No organisations are available")); assert.ok(t.includes("Required"));
  });
  test("client form validation", () => {
    const f = { ...P.emptyClientForm(), client_org_id: "c1", label: "Bakery", consent_reference: "Letter 7" };
    assert.equal(P.clientFormProblem(f), null);
    assert.match(P.clientFormProblem({ ...f, consent_reference: "ok" }), /consent/); assert.match(P.clientFormProblem({ ...f, client_org_id: "" }), /Choose/);
    assert.match(P.clientFormProblem({ ...f, label: " " }), /name/); assert.match(P.clientFormProblem({ ...f, audit_prep_minutes: "abc" }), /whole numbers/);
  });
  test("client body only sends what was filled in", () => {
    assert.deepEqual(P.clientBody({ client_org_id: "c1", label: " B ", consent_reference: " L7 ", kickoff: "", audit_prep_minutes: "600", report_minutes: "" }),
      { client_org_id: "c1", label: "B", consent_reference: "L7", baseline: { audit_prep_minutes: 600 } });
  });
});

describe("recording", () => {
  test("a firm must choose a client; a client organisation is never asked", () => {
    const firm = page(st({ tab: "log", form: { kind: "time", f: { performed_on: "2026-10-10" } } })); assert.ok(byId(firm, "log-client"));
    const cl = page(st({ me: clientMe, current: clientMe.membership.pilot, tab: "log", form: { kind: "time", f: {} }, logs: { time: [], issues: [], passport_uses: [], clients: [{ org_id: "me", label: "Bakery" }] } }));
    assert.ok(!byId(cl, "log-client")); assert.ok(byId(cl, "time-minutes"));
  });
  test("bodies", () => {
    assert.deepEqual(P.timeBody({ kind: "REPORT", minutes: "40", performed_on: "2026-10-10", baseline_minutes: "", client_org_id: "c1" }, true), { kind: "REPORT", minutes: 40, performed_on: "2026-10-10", note: "", client_org_id: "c1" });
    assert.ok(!("client_org_id" in P.timeBody({ kind: "REPORT", minutes: "40", performed_on: "x", client_org_id: "c1" }, false)));
    assert.equal(P.passportUseBody({ purpose: "LENDER", outcome: "HELPFUL", saved_minutes: "0" }, false).saved_minutes, 0);     // zero minutes saved is an answer, not a blank
    assert.equal(P.issueBody({ kind: "BUG", text: " x ", severity: "" }, false).severity, "LOW");
  });
  test("only the firm's managers can resolve an issue", () => {
    const logs = { time: [], passport_uses: [], clients: [], issues: [{ id: "i1", reported_at: "2026-10-10T00:00:00Z", client: "Bakery", kind: "BUG", severity: "HIGH", text: "Report would not load", status: "OPEN" }] };
    assert.equal(find(page(st({ tab: "log", logs })), (n) => n.props && n.props["data-resolve"]).length, 1);
    assert.equal(find(page(st({ tab: "log", logs, me: clientMe, current: clientMe.membership.pilot })), (n) => n.props && n.props["data-resolve"]).length, 0);
  });
});

describe("survey", () => {
  test("blank optional answers are not sent and never become zero", () => {
    const b = P.surveyBody({ round: " week 2 ", scores: { overall: "4", ease: "3", trust: "5", recommend: "0", time_saving: "", passport_useful: "" }, comment: " ok " });
    assert.deepEqual(b, { round: "week 2", scores: { overall: 4, ease: 3, trust: 5, recommend: 0 }, comment: "ok" });
  });
  test("validation names the first problem", () => {
    const ok = { overall: "4", ease: "3", trust: "5", recommend: "9" };
    assert.equal(P.surveyProblem({ scores: ok }), null);
    assert.match(P.surveyProblem({ scores: { ...ok, overall: "" } }), /satisfied/); assert.match(P.surveyProblem({ scores: { ...ok, ease: "6" } }), /1 to 5/);
    assert.match(P.surveyProblem({ scores: { ...ok, recommend: "11" } }), /0 to 10/); assert.match(P.surveyProblem({ scores: { ...ok, trust: "x" } }), /whole number/);
    assert.equal(P.surveyProblem({ scores: { ...ok, recommend: "0" } }), null);
  });
  test("the page explains the privacy rule and hides a small group's average", () => {
    const r = results({ reported: { survey: { respondents: 2, overall_mean: 4, ease_mean: 4, trust_mean: 4, nps: 50, by_group: { FIRM: { n: 0 }, CLIENT: { n: 2, overall: null, hidden: true } } } } });
    const t = text(page(st({ tab: "survey", results: r })));
    assert.ok(t.includes("hidden until at least three")); assert.ok(t.includes("average hidden until three people have answered"));
  });
});

describe("set-up, snapshots, about", () => {
  test("cannot start without a client; completing warns it is final", () => {
    const v = page(st({ tab: "setup", current: current({ status: "PLANNING", can_start: false }) })); assert.equal(byId(v, "pilot-advance").props.disabled, true);
    assert.ok(text(page(st({ tab: "setup", current: current() }))).includes("final"));
  });
  test("snapshots need an active pilot and show the fingerprint", () => {
    assert.equal(byId(page(st({ tab: "report", current: current({ status: "PLANNING" }) })), "snapshot-take").props.disabled, true);
    const s = { id: "s1", taken_at: "2026-10-20T00:00:00Z", clients_included: 1, clients_total: 1, hash: "ab".repeat(32), measures: KEYS.map((k) => ({ status: "MET" })) };
    assert.ok(text(page(st({ tab: "report", snapshots: [s] }))).includes("abababababababab"));
  });
  test("the client's about page says they can leave, and only administrators get the button", () => {
    const base = { me: clientMe, current: clientMe.membership.pilot, tab: "about" };
    assert.ok(byId(page(st(base)), "leave-start")); assert.ok(!byId(page(st({ ...base, me: { ...clientMe, can_withdraw: false } })), "leave-start"));
    assert.ok(text(page(st(base))).includes("removed from every result"));
  });
});

describe("api client", () => {
  test("paths", async () => {
    const calls = []; const c = new ApiClient("http://x", () => "t"); c._fetch = async (url, init) => { calls.push([init.method, url]); return new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } }); };
    await c.addPilotClient("p/1", {}); await c.removePilotClient("p1", "o 2", "r"); await c.pilotResults("p1"); await c.logPilotTime("p1", {}); await c.leavePilot("p1", "r");
    assert.deepEqual(calls.map((x) => x.join(" ")), ["POST /api/pilot/pilots/p%2F1/clients", "POST /api/pilot/pilots/p1/clients/o%202/remove", "GET /api/pilot/pilots/p1/results", "POST /api/pilot/pilots/p1/time", "POST /api/pilot/pilots/p1/leave"]);
  });
});
