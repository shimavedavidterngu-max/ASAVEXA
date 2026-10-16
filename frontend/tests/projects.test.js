import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { Projects } from "../src/pages/Projects.js";
import * as F from "../src/lib/projects.js";
import { ApiClient } from "../src/api/client.js";
import { NAV_GROUPS } from "../src/lib/home.js";
import * as E from "../src/lib/entityConfig.js";

const text = (v) => JSON.stringify(v);
const noop = new Proxy({}, { get: () => () => {} });
const bl = (o = {}) => ({ no: 1, category: "Personnel", amount: "600000.00", spent: "350000.35", remaining: "249999.65", over_budget: false, status: "ACTIVE", removed_note: null, ...o });
const en = (o = {}) => ({ no: 1, entry_type: "EXPENSE", budget_no: 1, amount: "200000.25", entry_date: "2026-02-10", description: "Field staff salaries", status: "PROPOSED", proposed_by: "u1", decision_note: null, ...o });
const proj = (o = {}) => ({ id: "p1", ref: "PJ-001", title: "Clean water programme", funder_ref: "FND-1", currency: "NGN", award: "1000000.00", budgeted: "850000.50", unallocated: "149999.50", spent: "600000.86", remaining: "399999.14", received: "400000.00", still_to_receive: "600000.00", spent_pct: "60.00",
  period_start: "2026-01-01", period_end: "2026-12-31", status: "DRAFT", submitted_by: null, active_lines: 2, pending_entries: 0, over_budget_lines: 0, received_above_award: false, days_left: 200, ending_soon: false, ended_still_open: false,
  budget: [bl(), bl({ no: 2, category: "Equipment", amount: "250000.50", spent: "250000.51", remaining: "-0.01", over_budget: true })], entries: [], history: [], ...o });
const ovw = () => ({ counts: { draft: 1, submitted: 1, active: 1, returned: 0, closed: 0, withdrawn: 0 }, totals: [{ currency: "NGN", projects: 1, award: "1000000.00", budgeted: "850000.50", spent: "600000.86", received: "400000.00", remaining: "399999.14", still_to_receive: "600000.00" }],
  attention: [{ kind: "PROJECTS_TO_REVIEW", count: 1, text: "project(s) are waiting for a different person." }], setting: { ending_soon_days: 30, meaning: "Within 30 days." }, limitations: ["ASAVEXA moves no money."] });
const state = (o = {}) => ({ tab: "overview", ov: ovw(), projects: [proj()], sel: { project: null }, forms: { ...JSON.parse(JSON.stringify(F.EMPTY)), setting: { ending_soon_days: "30" } }, notes: {}, formError: null, busy: false, error: null, notice: null, ...o });
const page = (o = {}, role = "OWNER", me = "u9") => Projects({ pj: state(o), role, userId: me, loading: false, onRetry() {}, actions: noop });
const sel = (p, role = "OWNER", me = "u9") => page({ tab: "projects", sel: { project: p } }, role, me);

describe("permissions", () => {
  test("who can prepare and approve", () => {
    for (const r of ["OWNER", "ADMINISTRATOR", "MANAGER", "AUDITOR"]) assert.ok(F.canPrepare(r), r);
    for (const r of ["OWNER", "APPROVER", "MANAGER"]) assert.ok(F.canApprove(r), r);
    for (const r of ["ACCOUNTANT", "READ_ONLY", "EXTERNAL_AUDITOR"]) { assert.ok(!F.canPrepare(r), r); assert.ok(!F.canApprove(r), r); }
  });
  test("button rules", () => {
    assert.ok(F.canEdit(proj(), "OWNER")); assert.ok(F.canEdit(proj({ status: "RETURNED" }), "OWNER")); assert.ok(!F.canEdit(proj({ status: "ACTIVE" }), "OWNER")); assert.ok(!F.canEdit(proj(), "READ_ONLY"));
    assert.ok(!F.canSubmit(proj({ active_lines: 0 }), "OWNER"));
    assert.ok(F.canDecide(proj({ status: "SUBMITTED", submitted_by: "u1" }), "APPROVER", "u9")); assert.ok(!F.canDecide(proj({ status: "SUBMITTED", submitted_by: "u9" }), "APPROVER", "u9"));
    assert.ok(F.canEnter(proj({ status: "ACTIVE" }), "AUDITOR")); assert.ok(!F.canEnter(proj(), "AUDITOR"));
    assert.ok(F.canDecideEntry(proj({ status: "ACTIVE" }), en(), "APPROVER", "u9")); assert.ok(!F.canDecideEntry(proj({ status: "ACTIVE" }), en({ proposed_by: "u9" }), "APPROVER", "u9")); assert.ok(!F.canDecideEntry(proj({ status: "ACTIVE" }), en({ status: "APPROVED" }), "APPROVER", "u9"));
    assert.ok(F.canClose(proj({ status: "ACTIVE" }), "APPROVER")); assert.ok(!F.canClose(proj({ status: "ACTIVE", pending_entries: 1 }), "APPROVER")); assert.ok(!F.canClose(proj({ status: "ACTIVE" }), "AUDITOR"));
  });
});

describe("payload builders", () => {
  const f = { title: "Clean water programme", funder_ref: "FND-1", currency: "ngn", award: "1,000,000.00", period_start: "2026-01-01", period_end: "2026-12-31" };
  test("project", () => {
    const b = F.projectPayload(f).body; assert.equal(b.currency, "NGN"); assert.equal(b.award, "1000000.00");
    assert.match(F.projectPayload({ ...f, title: "ab" }).problem, /title/); assert.match(F.projectPayload({ ...f, funder_ref: "x" }).problem, /funder/); assert.match(F.projectPayload({ ...f, currency: "NG" }).problem, /three-letter/);
    assert.match(F.projectPayload({ ...f, award: "0" }).problem, /more than zero/); assert.match(F.projectPayload({ ...f, award: "1,2,3" }).problem, /commas/); assert.match(F.projectPayload({ ...f, award: "1.234" }).problem, /two decimals/);
    assert.match(F.projectPayload({ ...f, period_end: "2025-12-31" }).problem, /cannot end before/); assert.match(F.projectPayload({ ...f, period_start: "2026-02-30" }).problem, /real date/);
  });
  test("budget", () => {
    assert.deepEqual(F.budgetPayload({ category: "Personnel", amount: "600,000.00" }).body, { category: "Personnel", amount: "600000.00" });
    assert.match(F.budgetPayload({ category: "x", amount: "5" }).problem, /category/); assert.match(F.budgetPayload({ category: "Travel", amount: "٥" }).problem, /amount/); assert.match(F.budgetPayload({ category: "Travel", amount: "0.00" }).problem, /more than zero/);
  });
  test("entry", () => {
    const p = { period_start: "2026-01-01", period_end: "2026-12-31" }, e = { entry_type: "EXPENSE", budget_no: "2", amount: "200,000.25", entry_date: "2026-02-10", description: "Field staff" };
    assert.deepEqual(F.entryPayload(e, p).body, { entry_type: "EXPENSE", budget_no: 2, amount: "200000.25", entry_date: "2026-02-10", description: "Field staff" });
    assert.ok(!("budget_no" in F.entryPayload({ ...e, entry_type: "RECEIPT", budget_no: "" }, p).body));
    assert.match(F.entryPayload({ ...e, budget_no: "" }, p).problem, /budget line/); assert.match(F.entryPayload({ ...e, entry_date: "2027-01-01" }, p).problem, /inside the project period/);
    assert.match(F.entryPayload({ ...e, description: "ab" }, p).problem, /description/); assert.match(F.entryPayload({ ...e, entry_type: "x" }, p).problem, /expense or a receipt/); assert.match(F.entryPayload({ ...e, amount: "0" }, p).problem, /more than zero/);
  });
  test("submit and setting", () => {
    assert.equal(F.submitPayload({ note: "" }).body.note, ""); assert.match(F.submitPayload({ note: "short" }).problem, /10 characters/);
    assert.equal(F.settingPayload("45").body.ending_soon_days, 45); for (const bad of ["0", "366", "x", "1.5", "-1", ""]) assert.ok(F.settingPayload(bad).problem, bad);
  });
});

describe("page", () => {
  test("overview shows exact figures and the limits", () => {
    const t = text(page());
    for (const s of ["600000.86", "399999.14", "still to receive 600000.00", "never added together", "ASAVEXA moves no money", "pj-banner", "Settings", "Projects to review"]) assert.ok(t.includes(s), s);
    assert.ok(t.includes("pj-set-save")); assert.ok(!text(page({}, "READ_ONLY")).includes("pj-set-save"));
  });
  test("owner sees editing on a draft", () => {
    const t = text(sel(proj()));
    for (const s of ["pj-bl-save", "pj-sb-save", "pj-wd-save", "pj-bl-1-remove", "Over budget", "-0.01", "60.00 percent"]) assert.ok(t.includes(s), s);
    assert.ok(!t.includes("pj-en-save"));
  });
  test("read-only sees no buttons", () => {
    const t = text(sel(proj({ status: "ACTIVE", entries: [en()] }), "READ_ONLY"));
    for (const s of ["pj-bl-save", "pj-sb-save", "pj-en-save", "pj-en-1-approve", "pj-cl-save", "pj-dec-approve"]) assert.ok(!t.includes(s), s);
    assert.ok(t.includes("200000.25"));
  });
  test("submitted: other person decides, submitter does not", () => {
    const t = text(sel(proj({ status: "SUBMITTED", submitted_by: "u1" }), "APPROVER", "u9")); assert.ok(t.includes("pj-dec-approve") && t.includes("pj-dec-return"));
    const own = text(sel(proj({ status: "SUBMITTED", submitted_by: "u9" }), "APPROVER", "u9")); assert.ok(!own.includes("pj-dec-approve")); assert.ok(own.includes("a different person must decide it"));
  });
  test("open project: entries, decisions and closing", () => {
    const p = proj({ status: "ACTIVE", pending_entries: 1, entries: [en(), en({ no: 2, status: "APPROVED", proposed_by: "u1" })] });
    const prep = text(sel(p, "AUDITOR", "u9")); assert.ok(prep.includes("pj-en-save") && prep.includes("pj-en-type") && prep.includes("pj-en-line")); assert.ok(!prep.includes("pj-en-1-approve"));
    const appr = text(sel(p, "APPROVER", "u9")); assert.ok(appr.includes("pj-en-1-approve") && appr.includes("pj-en-1-reject")); assert.ok(!appr.includes("pj-en-2-approve")); assert.ok(appr.includes("pj-close-blocked")); assert.ok(!appr.includes("pj-cl-save"));
    const own = text(sel(p, "APPROVER", "u1")); assert.ok(!own.includes("pj-en-1-approve")); assert.ok(own.includes("a different person must decide it"));
    assert.ok(text(sel(proj({ status: "ACTIVE" }), "APPROVER", "u9")).includes("pj-cl-save"));
  });
  test("receipt form hides the budget line", () => {
    const t = text(page({ tab: "projects", sel: { project: proj({ status: "ACTIVE" }) }, forms: { ...state().forms, entry: { entry_type: "RECEIPT", budget_no: "", amount: "", entry_date: "", description: "" } } }, "OWNER", "u9"));
    assert.ok(!t.includes("pj-en-line")); assert.ok(t.includes("pj-en-type"));
  });
  test("flags and notes", () => {
    const t = text(sel(proj({ status: "ACTIVE", ending_soon: true, days_left: 10, received_above_award: true, decision_note: "Checked against the agreement" })));
    for (const s of ["pj-ending-note", "pj-received-note", "Checked against the agreement"]) assert.ok(t.includes(s), s);
    assert.ok(text(sel(proj({ status: "ACTIVE", ended_still_open: true }))).includes("pj-ended-note"));
    assert.ok(text(sel(proj({ status: "RETURNED", decision_note: "Fix the budget" }))).includes("Fix the budget"));
    assert.ok(text(sel(proj({ status: "CLOSED", close_note: "All done and audited" }))).includes("All done and audited"));
  });
  test("errors and form problems show; loading", () => {
    assert.ok(text(page({ error: "Boom" })).includes("Boom"));
    assert.ok(text(page({ tab: "projects", formError: { form: "project", text: "The title needs at least 3 characters." } })).includes("project-problem"));
    assert.ok(text(Projects({ pj: state(), role: "OWNER", userId: "u9", loading: true, onRetry() {}, actions: noop })).length > 0);
  });
});

describe("wiring", () => {
  test("client methods hit the right paths", async () => {
    const calls = []; const c = new ApiClient("http://x"); c.request = async (m, p, b) => { calls.push([m, p, b]); return {}; };
    c.get = (p) => c.request("GET", p); c.post = (p, b) => c.request("POST", p, b); c.put = (p, b) => c.request("PUT", p, b);
    await c.pjOverview(); await c.pjProjects(); await c.pjProject("a b"); await c.createPjProject({}); await c.addPjBudget("p1", {}); await c.removePjBudget("p1", 2, "wrong"); await c.submitPj("p1", "n"); await c.withdrawPj("p1", "w"); await c.approvePj("p1", ""); await c.returnPj("p1", "r"); await c.closePj("p1", "c");
    await c.addPjEntry("p1", {}); await c.approvePjEntry("p1", 3, ""); await c.rejectPjEntry("p1", 3, "r"); await c.setPjSetting({ ending_soon_days: 5 });
    assert.deepEqual(calls.map((x) => x[0] + " " + x[1]), ["GET /projects/overview", "GET /projects/projects", "GET /projects/projects/a%20b", "POST /projects/projects", "POST /projects/projects/p1/budget", "POST /projects/projects/p1/budget/2/remove", "POST /projects/projects/p1/submit",
      "POST /projects/projects/p1/withdraw", "POST /projects/projects/p1/approve", "POST /projects/projects/p1/return", "POST /projects/projects/p1/close", "POST /projects/projects/p1/entries", "POST /projects/projects/p1/entries/3/approve", "POST /projects/projects/p1/entries/3/reject", "PUT /projects/setting"]);
  });
  test("home group and entity path", () => {
    assert.ok(NAV_GROUPS.some((g) => g.paths.includes("/projects"))); assert.equal(E.WORKSPACE_PATHS.projects, "/projects");
  });
});
