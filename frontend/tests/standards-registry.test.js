import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { StandardsRegistry } from "../src/pages/StandardsRegistry.js";
import * as L from "../src/lib/standardsRegistry.js";
import { ApiClient } from "../src/api/client.js";

function find(v, pred, out = []) { if (!v || typeof v !== "object") return out; if (pred(v)) out.push(v); for (const c of v.children || []) find(c, pred, out); return out; }
const byId = (v, id) => find(v, (n) => n.props && n.props.id === id)[0];
const text = (v) => JSON.stringify(v);
const noop = new Proxy({}, { get: () => () => {} });
const src = (o = {}) => ({ id: "s1", framework: "IFRS", jurisdiction: null, title: "IFRS", url: "https://www.ifrs.org/", authority: "IASB", version: "1", effective_from: "2026-01-01", review_by: "2027-01-01", status: "DRAFT", created_by: "a", submitted_by: null, history: [{ at: "2026-10-12T10:00:00", event: "ADDED", note: "" }], ...o });
const cov = (rows) => ({ frameworks: rows, counts: {}, note: "VERIFIED means a person approved an official source. This is not legal advice." });
const row = (o = {}) => ({ framework: "IFRS", name: "IFRS (full)", state: "UNVERIFIED", source: null, ...o });
const sr = (o = {}) => ({ coverage: cov([row()]), sources: [], frameworks: [{ code: "IFRS", name: "IFRS (full)" }], jurisdictions: [{ code: "NG", name: "Nigeria" }], form: { ...L.EMPTY_FORM }, formError: null, reasons: {}, busy: false, error: null, notice: null, ...o });
const page = (s, role = "OWNER", me = "u1") => StandardsRegistry({ sr: s, me, role, loading: false, onRetry() {}, actions: noop });
const ok = { framework: "IFRS", title: "T", url: "https://www.ifrs.org/x", authority: "IASB", version: "1", effective_from: "2026-01-01", review_by: "2027-01-01" };

describe("helpers", () => {
  test("states and statuses are plain words", () => {
    assert.equal(L.stateInfo("REVIEW_OVERDUE").label, "Review overdue"); assert.equal(L.stateInfo("UNVERIFIED").tone, "fail"); assert.equal(L.statusInfo("UNDER_REVIEW").label, "Under review"); assert.equal(L.stateInfo("?").label, "?");
  });
  test("the form is checked before sending", () => {
    assert.equal(L.formProblem({ ...L.EMPTY_FORM, ...ok }), null);
    assert.match(L.formProblem({ ...L.EMPTY_FORM, ...ok, framework: "" }), /framework/);
    assert.match(L.formProblem({ ...L.EMPTY_FORM, ...ok, url: "http://x.org" }), /https/);
    assert.match(L.formProblem({ ...L.EMPTY_FORM, ...ok, url: "https://nodot" }), /https/);
    assert.match(L.formProblem({ ...L.EMPTY_FORM, ...ok, title: " " }), /title/);
    assert.match(L.formProblem({ ...L.EMPTY_FORM, ...ok, effective_from: "soon" }), /Effective/);
    assert.match(L.formProblem({ ...L.EMPTY_FORM, ...ok, review_by: "2025-01-01" }), /after/);
  });
  test("who may do what: preparer submits, only an independent approver approves", () => {
    assert.deepEqual(L.actionsFor(src(), "u", true, false), ["submit"]);
    assert.deepEqual(L.actionsFor(src({ status: "UNDER_REVIEW", created_by: "a", submitted_by: "a" }), "u", false, true), ["approve", "send-back", "withdraw"]);
    assert.deepEqual(L.actionsFor(src({ status: "UNDER_REVIEW", created_by: "a", submitted_by: "a" }), "a", true, true), ["withdraw"]);
    assert.deepEqual(L.actionsFor(src({ status: "UNDER_REVIEW", created_by: "x", submitted_by: "u" }), "u", true, true), ["withdraw"]);
    assert.deepEqual(L.actionsFor(src({ status: "SUPERSEDED" }), "u", true, true), []);
    assert.deepEqual(L.actionsFor(null, "u", true, true), []);
  });
});

describe("page", () => {
  test("nothing verified is shown as unverified with the honesty note", () => {
    const v = page(sr());
    assert.match(text(byId(v, "sr-coverage")), /Unverified/); assert.match(text(byId(v, "sr-coverage")), /None recorded/); assert.match(text(byId(v, "sr-note")), /not legal advice/);
    assert.ok(byId(v, "sr-none"));
  });
  test("a verified framework links to its official source", () => {
    const v = page(sr({ coverage: cov([row({ state: "VERIFIED", source: { url: "https://www.ifrs.org/", title: "IFRS", version: "2026", review_by: "2027-01-01" } })]) }));
    const a = find(v, (n) => n.tag === "a" && n.props && n.props.href === "https://www.ifrs.org/")[0];
    assert.ok(a); assert.equal(a.props.rel, "noopener noreferrer"); assert.match(text(byId(v, "sr-coverage")), /Verified/);
  });
  test("the add form only appears for someone who can prepare", () => {
    assert.ok(byId(page(sr(), "OWNER"), "sr-add")); assert.equal(byId(page(sr(), "READ_ONLY"), "sr-add"), undefined);
  });
  test("a form problem and an error are shown", () => {
    const v = page(sr({ formError: "Choose a framework.", error: "boom", notice: "Added." }));
    assert.match(text(byId(v, "sr-form-error")), /Choose a framework/); assert.match(text(v), /boom/); assert.ok(byId(v, "sr-notice"));
  });
  test("a draft offers Submit; a source you submitted shows why you cannot approve it", () => {
    assert.equal(find(page(sr({ sources: [src()] })), (n) => n.props && n.props["data-act"] === "submit").length, 1);
    const mine = page(sr({ sources: [src({ status: "UNDER_REVIEW", created_by: "u1", submitted_by: "u1" })] }), "OWNER", "u1");
    assert.equal(find(mine, (n) => n.props && n.props["data-act"] === "approve").length, 0); assert.equal(find(mine, (n) => n.props && n.props["data-sod"]).length, 1);
    const other = page(sr({ sources: [src({ status: "UNDER_REVIEW", created_by: "u1", submitted_by: "u1" })] }), "OWNER", "u2");
    assert.equal(find(other, (n) => n.props && n.props["data-act"] === "approve").length, 1);
  });
  test("source links open safely in a new tab", () => {
    const v = page(sr({ sources: [src()] }));
    const links = find(v, (n) => n.tag === "a" && n.props && n.props.href === "https://www.ifrs.org/");
    assert.ok(links.length >= 1); for (const l of links) assert.equal(l.props.rel, "noopener noreferrer");
  });
});

describe("wiring", () => {
  test("client endpoints", async () => {
    const calls = [];
    const api = new ApiClient({ baseUrl: "http://x", getToken: () => "t", fetchImpl: async (url, opt) => { calls.push([opt.method, url]); return { ok: true, status: 200, headers: { get: () => "application/json" }, json: async () => ({}), text: async () => "{}" }; } });
    await api.standardsRegistryCoverage(); await api.addStandardsSource({}); await api.standardsSourceAction("s1", "approve", { note: "x" });
    assert.deepEqual(calls.map((c) => c[0]), ["GET", "POST", "POST"]); assert.match(calls[2][1], /\/standards-registry\/sources\/s1\/approve$/);
  });
  test("route, menu and group are present", () => {
    const app = readFileSync(new URL("../src/app.js", import.meta.url), "utf8");
    assert.match(app, /\{ path: "\/standards-registry", name: "standards-registry" \}/); assert.match(app, /label: "Standards Registry"/); assert.match(app, /name === "standards-registry"/);
    assert.match(readFileSync(new URL("../src/lib/home.js", import.meta.url), "utf8"), /"\/standards-registry"/);
  });
});
