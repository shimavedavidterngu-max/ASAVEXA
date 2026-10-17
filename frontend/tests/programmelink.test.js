import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { programmeLink, rowOf, refProblem, PROGRAMME_LIMIT } from "../src/lib/programmeLink.js";
import { grantProblem, grantBody, emptyGrant } from "../src/lib/pubfin.js";
import { Pubfin } from "../src/pages/Pubfin.js";

const walk = (v, fn) => { if (!v || typeof v !== "object") return; fn(v); (v.children || []).forEach((c) => walk(c, fn)); };
const all = (v, pred) => { const out = []; walk(v, (n) => { if (pred(n)) out.push(n); }); return out; };
const text = (v) => { if (v == null || v === false) return ""; if (typeof v !== "object") return String(v); return (v.children || []).map(text).join(""); };
const byId = (v, id) => all(v, (n) => n.props && n.props.id === id)[0];

const ind = (o = {}) => ({ id: "i1", ref: "IM-001", title: "Households with clean water", programme_ref: "WASH-01", unit: "households", status: "APPROVED", state: "ON_TRACK", latest_value: "420", latest_period_end: "2026-06-30", progress_pct: "42.00", stale: false, ...o });
const grant = (o = {}) => ({ id: "g1", ref: "G-001", title: "Clean water", donor: "Water Fund", amount: "20000.00", currency: "USD", start: "2026-01-01", end: "2026-12-31", restricted: true, conditions: "", programme_ref: "WASH-01",
  receipts: [], spend: [], received: "0.00", spent: "0.00", pending: "0.00", remaining: "20000.00", cash_on_hand: "0.00", overspent_vs_received: false, status: "ACTIVE", ...o });

describe("programmeLink", () => {
  test("no reference typed", () => { assert.equal(programmeLink(grant({ programme_ref: null }), [ind()]).kind, "no-ref"); assert.equal(programmeLink(grant({ programme_ref: "  " }), [ind()]).kind, "no-ref"); });
  test("not loaded is 'unknown', never 'none'", () => { assert.equal(programmeLink(grant(), undefined).kind, "unknown"); assert.equal(programmeLink(grant(), null).kind, "unknown"); });
  test("loaded and empty is 'none'", () => assert.equal(programmeLink(grant(), []).kind, "none"));
  test("matches the typed code ignoring case and spaces, only approved indicators", () => {
    const r = programmeLink(grant({ programme_ref: " wash-01 " }), [ind(), ind({ id: "i2", programme_ref: "OTHER" }), ind({ id: "i3", status: "PROPOSED" }), ind({ id: "i4", status: "CLOSED" })]);
    assert.equal(r.kind, "matched"); assert.deepEqual(r.rows.map((x) => x.id), ["i1"]);
  });
  test("restates the server's figures exactly", () => assert.equal(rowOf(ind()).text, "IM-001 Households with clean water: On track. Latest confirmed reading 420 households (period ending 2026-06-30); 42.00% of the way from the baseline to the target."));
  test("no confirmed reading is said in words, not zero", () => {
    const t = rowOf(ind({ state: "NO_DATA", latest_value: null, progress_pct: null })).text;
    assert.match(t, /No confirmed reading yet\. No confirmed reading yet\.$/); assert.doesNotMatch(t, /\b0\b/);
  });
  test("overdue and behind are worded, not coloured", () => { assert.match(rowOf(ind({ state: "OVERDUE" })).text, /Past the target date/); assert.match(rowOf(ind({ state: "BEHIND" })).text, /Behind the progress expected/); });
  test("the caveat says it is not proof of cause", () => assert.match(PROGRAMME_LIMIT, /does not show that the grant caused any change/));
  test("no browser arithmetic in the module", () => assert.doesNotMatch(readFileSync(new URL("../src/lib/programmeLink.js", import.meta.url), "utf8").replace(/\/\*[\s\S]*?\*\//g, ""), /parseFloat|Number\(|\.reduce\(|Math\./));
  test("refProblem", () => { assert.equal(refProblem(""), null); assert.equal(refProblem("WASH-01"), null); assert.ok(refProblem("x")); assert.ok(refProblem("y".repeat(41))); });
});

describe("grant form", () => {
  const f = (o = {}) => ({ ...emptyGrant(), title: "Clean water", donor: "Water Fund", amount: "100", start: "2026-01-01", end: "2026-12-31", ...o });
  test("reference is optional, and checked when given", () => { assert.equal(grantProblem(f()), null); assert.ok(grantProblem(f({ programme_ref: "x" }))); assert.equal(grantProblem(f({ programme_ref: "WASH-01" })), null); });
  test("body carries the reference only when typed", () => { assert.equal("programme_ref" in grantBody(f()), false); assert.equal(grantBody(f({ programme_ref: " WASH-01 " })).programme_ref, "WASH-01"); });
});

describe("Follow a grant shows programme results", () => {
  const base = (o = {}) => ({ tab: "follow", grants: [grant()], budgets: [], commitments: [], notes: {}, ...o });
  const page = (pf, role = "ACCOUNTANT", calls = []) => Pubfin({ pf, role, userId: "u", loading: false, onRetry() {}, actions: { setTab() {}, followGrant() {}, progChange: (i, v) => calls.push(["c", i, v]), saveProgramme: (i) => calls.push(["s", i]) }, sector: "ngo" });
  test("matched indicator is listed with the caveat", () => {
    const v = page(base({ programme: { grantId: "g1", indicators: [ind()] } }));
    assert.match(text(byId(v, "pf-programme-list")), /IM-001 Households with clean water: On track/);
    assert.match(text(byId(v, "pf-programme-limit")), /does not show that the grant caused/);
  });
  test("unloaded says Not checked", () => assert.match(text(byId(page(base()), "pf-programme-unknown")), /^Not checked/));
  test("no reference says so", () => assert.ok(byId(page(base({ grants: [grant({ programme_ref: null })] })), "pf-programme-noref")));
  test("no match says so with the code", () => assert.match(text(byId(page(base({ programme: { grantId: "g1", indicators: [] } })), "pf-programme-none")), /WASH-01/));
  test("a preparer can edit, a read-only role cannot, and a closed grant cannot", () => {
    const calls = [], v = page(base(), "ACCOUNTANT", calls);
    byId(v, "pf-programme-ref").props.onInput({ target: { value: "WASH-02" } }); byId(v, "pf-programme-save").props.onClick();
    assert.deepEqual(calls, [["c", "g1", "WASH-02"], ["s", "g1"]]);
    assert.equal(byId(page(base(), "AUDITOR"), "pf-programme-edit"), undefined);
    assert.equal(byId(page(base({ grants: [grant({ status: "CLOSED" })] })), "pf-programme-edit"), undefined);
  });
  test("works in fund mode too and never shows a donor", () => {
    const v = Pubfin({ pf: base({ grants: [grant({ donor: "Mrs Adeyemi" })], programme: { grantId: "g1", indicators: [ind()] } }), role: "ACCOUNTANT", userId: "u", loading: false, onRetry() {}, actions: { setTab() {}, followGrant() {} }, sector: "church" });
    assert.ok(byId(v, "pf-programme-list")); assert.doesNotMatch(text(v), /Adeyemi/);
  });
});
