import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { Validation, TABS } from "../src/pages/Validation.js";
import * as V from "../src/lib/validation.js";
import { ApiClient } from "../src/api/client.js";
import { PERMISSIONS, ROLE_PERMISSIONS } from "../src/lib/permissions.js";

const text = (v) => JSON.stringify(v);
function find(v, pred, out = []) {
  if (!v || typeof v !== "object") return out;
  if (pred(v)) out.push(v);
  for (const c of v.children || []) find(c, pred, out);
  return out;
}
const byId = (v, id) => find(v, (n) => n.props && n.props.id === id)[0];
const noop = new Proxy({}, { get: () => () => {} });
const STAGES = ["ACCOUNTING_TREATMENT", "CONTROLS", "EVIDENCE", "REPORTING", "AUDIT_WORKFLOW", "SECURITY", "PROFESSIONAL_JUDGEMENT"];
const guide = { disclaimer: "This is not an audit opinion or a certification.", bodies: { ICAN: "Institute of Chartered Accountants of Nigeria", ACCA: "ACCA" }, specialisms: { IFRS: "IFRS / IFRS for SMEs", AUDIT: "External audit (ISA)" }, conclusions: { CONCURS: "Concurs: nothing to change.", DISAGREES: "Disagrees." }, severities: ["MAJOR", "MINOR"],
  stages: STAGES.map((id) => ({ id, label: V.humanize(id), question: "q?", checklist: ["c1"], specialisms: id === "EVIDENCE" ? ["AUDIT"] : ["IFRS"] })) };
const rev = (id, over = {}) => ({ id, name: `Rev ${id}`, email: `${id}@x.test`, active: true, user_id: null, specialisms: ["IFRS"], credentials: [{ body: "ICAN", membership_no: "1", status: "DECLARED" }], ...over });
const cov = (over = {}) => ({ stages: STAGES.map((s) => ({ stage: s, label: V.humanize(s), status: "UNCOVERED", reviewers_needed: 1, signed: 0 })), complete: false, outcome: "INCOMPLETE", unresolved_serious_observations: 0, credential_verification: "NONE_SIGNED", ...over });
const detail = (over = {}) => ({ id: "e1", title: "FY26", status: "OPEN", as_of: "2026-09-30", description: "", snapshot_hash: "a".repeat(64), snapshot: { k: 1 }, snapshot_is_current: true,
  assignments: [], declarations: {}, reviews: [], reviewers: {}, coverage: cov(), statement: null, ...over });
const val = (over = {}) => ({ tab: "engagements", guide, me: { can_manage: true, reviewer: null }, list: [], panel: [], members: [], detailId: null, detail: null, form: null, ...over });
const page = (v, role = "OWNER") => Validation({ role, val: v, loading: false, onRetry() {}, actions: noop });

describe("permissions mirror", () => {
  test("validation:manage is held by OWNER and ADMINISTRATOR only", () => {
    assert.ok(ROLE_PERMISSIONS.OWNER.includes(PERMISSIONS.VALIDATION_MANAGE));
    assert.ok(ROLE_PERMISSIONS.ADMINISTRATOR.includes(PERMISSIONS.VALIDATION_MANAGE));
    for (const r of Object.keys(ROLE_PERMISSIONS).filter((x) => !["OWNER", "ADMINISTRATOR"].includes(x))) assert.ok(!ROLE_PERMISSIONS[r].includes(PERMISSIONS.VALIDATION_MANAGE), r);
  });
});

describe("helpers", () => {
  test("acting mode: linked reviewers act only as themselves, unlinked only through a manager", () => {
    const me = { can_manage: true, reviewer: { id: "r1" } };
    assert.equal(V.actingMode(me, rev("r1", { user_id: "u" })), "self");
    assert.equal(V.actingMode(me, rev("r2", { user_id: "u2" })), "none");           // a manager cannot act for a linked reviewer
    assert.equal(V.actingMode(me, rev("r3")), "on_behalf");
    assert.equal(V.actingMode({ can_manage: false, reviewer: null }, rev("r3")), "none");
    assert.equal(V.actingMode(null, rev("r3")), "none");
  });
  test("assignable: active, competent, not already assigned", () => {
    const d = detail({ assignments: [{ stage: "EVIDENCE", reviewer_id: "a" }] });
    const panel = [rev("a", { specialisms: ["AUDIT"] }), rev("b", { specialisms: ["AUDIT"] }), rev("c", { specialisms: ["IFRS"] }), rev("d", { specialisms: ["AUDIT"], active: false })];
    assert.deepEqual(V.assignable(panel, guide, d, "EVIDENCE").map((r) => r.id), ["b"]);
  });
  test("review state picks the draft and the latest signed version", () => {
    const d = detail({ reviews: [{ stage: "EVIDENCE", reviewer_id: "a", status: "SUPERSEDED", version: 1 }, { stage: "EVIDENCE", reviewer_id: "a", status: "SIGNED", version: 2 }, { stage: "EVIDENCE", reviewer_id: "a", status: "DRAFT", version: 3 }],
      declarations: { a: { independent: true } } });
    const s = V.reviewState(d, "EVIDENCE", "a");
    assert.equal(s.signed.version, 2); assert.equal(s.draft.version, 3); assert.ok(s.independent);
    assert.ok(!V.reviewState(d, "EVIDENCE", "zz").declared);
  });
  test("request bodies", () => {
    const f = V.reviewForm(null); f.conclusion = "CONCURS"; f.observations = [{ severity: "MAJOR", text: "  x ", recommendation: "" }, { severity: "MINOR", text: "  ", recommendation: "" }]; f.source_reference = " ref ";
    assert.deepEqual(V.reviewBody("EVIDENCE", "a", f, "on_behalf").observations, [{ severity: "MAJOR", text: "x", recommendation: "" }]);
    assert.equal(V.reviewBody("EVIDENCE", "a", f, "on_behalf").source_reference, "ref");
    assert.equal(V.reviewBody("EVIDENCE", "a", f, "self").source_reference, null);          // never sent for a person acting as themselves
    const d = V.declarationBody("a", { independent: true, confirmations: { no_financial_interest: true } }, "self");
    assert.equal(d.confirmations.not_involved_in_preparing_records, false); assert.equal(Object.keys(d.confirmations).length, 4);
    assert.deepEqual(V.engagementBody({ title: " T ", as_of: "2026-09-30", min_each: "2", stages: ["EVIDENCE"] }, STAGES).min_reviewers, { EVIDENCE: 2 });
    assert.equal(V.engagementBody({ title: "T", as_of: "d", min_each: "1" }, STAGES).stages.length, 7);
    assert.equal(V.reviewerBody({ name: "A", email: "a@b", body: "ACCA", membership_no: "9", year_admitted: "2010", specialisms: ["IFRS"] }).credentials[0].year_admitted, 2010);
  });
  test("open serious observations are found only on signed reviews", () => {
    const d = detail({ reviews: [{ status: "SIGNED", observations: [{ id: "1", severity: "MAJOR", response: null }, { id: "2", severity: "MINOR" }, { id: "3", severity: "CRITICAL", response: { status: "ACCEPTED" } }] },
      { status: "DRAFT", observations: [{ id: "4", severity: "CRITICAL" }] }] });
    assert.deepEqual(V.openSeriousObservations(d).map((x) => x.observation.id), ["1"]);
  });
  test("credential summary never calls declared credentials verified", () => {
    assert.equal(V.credentialSummary(rev("a")).tone, "warn");
    assert.equal(V.credentialSummary(rev("a", { credentials: [{ status: "VERIFIED" }] })).tone, "pass");
    assert.equal(V.credentialSummary(rev("a", { credentials: [{ status: "VERIFIED" }, { status: "DECLARED" }] })).tone, "info");
  });
});

describe("Validation page", () => {
  test("always shows the disclaimer and the three tabs", () => {
    const v = page(val());
    assert.ok(text(v).includes("not an audit opinion")); assert.equal(TABS.length, 3);
    assert.ok(byId(v, "val-tab-engagements") && byId(v, "val-tab-panel") && byId(v, "val-tab-guide"));
  });
  test("only managers see the create and add buttons", () => {
    assert.ok(byId(page(val()), "new-engagement")); assert.ok(!byId(page(val({ me: { can_manage: false, reviewer: null } })), "new-engagement"));
    assert.ok(byId(page(val({ tab: "panel" })), "add-reviewer")); assert.ok(!byId(page(val({ tab: "panel", me: { can_manage: false } })), "add-reviewer"));
  });
  test("engagement list shows outcome and stage coverage", () => {
    const v = page(val({ list: [{ id: "e1", title: "FY26", as_of: "2026-09-30", status: "OPEN", outcome: "INCOMPLETE", stages_covered: 2, stages_total: 7 }] }));
    assert.ok(text(v).includes("2 of 7")); assert.ok(text(v).includes("FY26"));
  });
  test("the guide lists all seven stages in order", () => {
    const t = text(page(val({ tab: "guide" })));
    const pos = STAGES.map((s) => t.indexOf(V.humanize(s)));
    assert.ok(pos.every((p) => p > 0)); assert.deepEqual([...pos].sort((a, b) => a - b), pos);
  });
  test("the detail shows the seven-stage pipeline and warns when data moved", () => {
    const v = page(val({ detailId: "e1", detail: detail({ snapshot_is_current: false }) }));
    assert.equal(find(v, (n) => n.props && n.props["data-stage"]).length, 7);
    assert.ok(text(byId(v, "snapshot-line")).includes("The data has changed"));
    assert.ok(text(byId(v, "outcome-badge")).includes("Incomplete"));
  });
  test("complete is disabled until every stage is covered and serious observations are answered", () => {
    const d1 = detail(); assert.equal(byId(page(val({ detailId: "e1", detail: d1 })), "complete-engagement").props.disabled, true);
    const d2 = detail({ coverage: cov({ complete: true }) }); assert.ok(!byId(page(val({ detailId: "e1", detail: d2 })), "complete-engagement").props.disabled);
    const d3 = detail({ coverage: cov({ complete: true }), reviews: [{ id: "r", stage: "EVIDENCE", reviewer_id: "a", status: "SIGNED", observations: [{ id: "o", severity: "MAJOR", response: null }] }] });
    assert.equal(byId(page(val({ detailId: "e1", detail: d3 })), "complete-engagement").props.disabled, true);
  });
  test("non-managers get no manager actions", () => {
    const v = page(val({ me: { can_manage: false, reviewer: null }, detailId: "e1", detail: detail() }));
    for (const id of ["complete-engagement", "withdraw-start", "refresh-snapshot", "open-engagement"]) assert.ok(!byId(v, id), id);
  });
  test("a linked reviewer sees actions only for themselves; a manager gets none for them", () => {
    const r = rev("a", { user_id: "u1" }); const base = { assignments: [{ id: "x", stage: "EVIDENCE", reviewer_id: "a" }], reviewers: { a: r } };
    const asSelf = page(val({ me: { can_manage: false, reviewer: r }, detailId: "e1", detail: detail(base) }));
    assert.ok(byId(asSelf, "declare-EVIDENCE-a"));
    const asOwner = page(val({ me: { can_manage: true, reviewer: null }, detailId: "e1", detail: detail(base) }));
    assert.ok(!byId(asOwner, "declare-EVIDENCE-a")); assert.ok(text(asOwner).includes("Only this reviewer can act for themselves"));
  });
  test("the review button appears only after an independent declaration", () => {
    const r = rev("a"); const base = { assignments: [{ id: "x", stage: "EVIDENCE", reviewer_id: "a" }], reviewers: { a: r } };
    assert.ok(!byId(page(val({ detailId: "e1", detail: detail(base) })), "review-EVIDENCE-a"));
    const conflict = detail({ ...base, declarations: { a: { independent: false } } });
    assert.ok(!byId(page(val({ detailId: "e1", detail: conflict })), "review-EVIDENCE-a"));
    assert.ok(text(page(val({ detailId: "e1", detail: conflict }))).includes("Declared a conflict"));
    const ok = detail({ ...base, declarations: { a: { independent: true } } });
    assert.ok(byId(page(val({ detailId: "e1", detail: ok })), "review-EVIDENCE-a"));
  });
  test("on-behalf forms ask for the source reference; self forms do not", () => {
    const r = rev("a"); const d = detail({ assignments: [{ id: "x", stage: "EVIDENCE", reviewer_id: "a" }], reviewers: { a: r }, declarations: { a: { independent: true } } });
    const mk = (mode) => page(val({ detailId: "e1", detail: d, form: { kind: "review", stage: "EVIDENCE", reviewerId: "a", mode, f: V.reviewForm(null) } }));
    assert.ok(byId(mk("on_behalf"), "rv-ref")); assert.ok(!byId(mk("self"), "rv-ref")); assert.ok(byId(mk("self"), "rv-sign"));
    const dm = (mode) => page(val({ detailId: "e1", detail: d, form: { kind: "declare", stage: "EVIDENCE", reviewerId: "a", mode, f: { confirmations: {} } } }));
    assert.ok(byId(dm("on_behalf"), "decl-ref")); assert.ok(!byId(dm("self"), "decl-ref"));
    assert.equal(find(dm("self"), (n) => n.props && String(n.props.id || "").startsWith("conf-")).length, 4);
  });
  test("a signed review shows its observations and a respond button to managers only", () => {
    const r = rev("a"); const rv = { id: "rv", stage: "EVIDENCE", reviewer_id: "a", status: "SIGNED", version: 1, conclusion: "CONCURS_WITH_COMMENTS", scope_reviewed: "s", basis: "b", signed_at: "2026-10-01T10:00:00+00:00",
      observations: [{ id: "o1", severity: "MAJOR", text: "Cut-off weak", response: null }] };
    const d = detail({ assignments: [{ id: "x", stage: "EVIDENCE", reviewer_id: "a" }], reviewers: { a: r }, declarations: { a: { independent: true } }, reviews: [rv] });
    assert.ok(byId(page(val({ detailId: "e1", detail: d })), "respond-o1"));
    assert.ok(!byId(page(val({ me: { can_manage: false, reviewer: null }, detailId: "e1", detail: d })), "respond-o1"));
    assert.ok(text(page(val({ detailId: "e1", detail: d }))).includes("Cut-off weak"));
  });
  test("statement shows verification result and the changed-data warning", () => {
    const st = { outcome: "VALIDATED", credential_verification: "SOME_UNVERIFIED", statement_hash: "f".repeat(64), mac: "m", disclaimer: "Not an audit opinion", stages: [], verification: { ok: true }, data_unchanged_since_review: false };
    const v = page(val({ detailId: "e1", detail: detail({ status: "COMPLETED", statement: st }), statement: st }));
    assert.ok(text(byId(v, "statement-verify")).includes("unaltered")); assert.ok(text(byId(v, "statement-verify")).includes("Data has changed"));
    assert.ok(text(byId(v, "statement-card")).includes("Some declared only"));
    const bad = { ...st, verification: { ok: false } };
    assert.ok(text(byId(page(val({ detailId: "e1", detail: detail({ status: "COMPLETED", statement: bad }), statement: bad })), "statement-verify")).includes("does not match"));
  });
  test("the add-reviewer form works with the server's real catalog shape (objects, not lists)", () => {
    const v = page(val({ tab: "panel", form: { kind: "reviewer", f: { specialisms: ["IFRS"] } } }));
    assert.ok(byId(v, "rv-spec-IFRS").props.checked); assert.ok(!byId(v, "rv-spec-AUDIT").props.checked);
    assert.ok(text(byId(v, "rv-body")).includes("Institute of Chartered Accountants of Nigeria"));
    assert.ok(text(byId(v, "reviewer-form")).includes("External audit (ISA)"));
    assert.deepEqual(V.entries(["A"]), [["A", "A"]]); assert.deepEqual(V.entries(undefined), []);
  });
  test("loading and error states", () => {
    assert.ok(text(Validation({ role: "OWNER", val: val({ error: "boom" }), loading: false, onRetry() {}, actions: noop })).includes("boom"));
    assert.ok(text(Validation({ role: "OWNER", val: val(), loading: true, onRetry() {}, actions: noop })).toLowerCase().includes("loading"));
  });
});

describe("api client paths", () => {
  test("methods, paths and bodies", async () => {
    const calls = [];
    const fetchImpl = async (url, init) => { calls.push({ url, init }); return { ok: true, status: 200, text: async () => "{}", headers: { get: () => null } }; };
    const c = new ApiClient({ baseUrl: "http://x", fetchImpl, getToken: () => "tok" });
    await c.verifyCredential("r 1", 0, { accepted: true, method: "m" });
    await c.setReviewerActive("r1", false); await c.setReviewerActive("r1", true);
    await c.assignReviewer("e1", "EVIDENCE", "r1"); await c.unassignReviewer("e1", "a1");
    await c.respondToObservation("e1", "rv", "o", "ACCEPTED", "n"); await c.signReview("e1", "rv"); await c.validationStatement("e1");
    assert.deepEqual(calls.map((x) => `${x.init.method} ${x.url.replace("http://x", "")}`), [
      "POST /validation/panel/r%201/credentials/0/verify", "POST /validation/panel/r1/deactivate", "POST /validation/panel/r1/activate",
      "POST /validation/engagements/e1/assignments", "DELETE /validation/engagements/e1/assignments/a1",
      "POST /validation/engagements/e1/reviews/rv/observations/o/response", "POST /validation/engagements/e1/reviews/rv/sign", "GET /validation/engagements/e1/statement"]);
    assert.deepEqual(JSON.parse(calls[3].init.body), { stage: "EVIDENCE", reviewer_id: "r1" });
  });
});
