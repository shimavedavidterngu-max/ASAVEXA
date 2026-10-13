import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { Assurance } from "../src/pages/Assurance.js";
import * as A from "../src/lib/assurance.js";
import { ApiClient } from "../src/api/client.js";
import { NAV_GROUPS } from "../src/lib/home.js";

const text = (v) => JSON.stringify(v);
const vocab = () => ({
  facets: A.FACET_ORDER.map((c) => ({ code: c, label: A.SHORT_FACET[c], meaning: `${c} means` })),
  flags: Object.keys(A.FLAG_TEXT).map((c) => ({ code: c, meaning: `${c} meaning` })),
  records: [{ type: "finding", label: "Finding", statuses: [{ status: "VERIFIED", headline: "Independently verified", facets: ["recorded", "reviewed", "independently_verified"], flag: null, note: "" }, { status: "OPEN", headline: "Open", facets: [], flag: "INCOMPLETE", note: "" }] }],
  note: "These are facts a record carries, not a score.",
});
const row = (o = {}) => ({ type: "finding", label: "Finding", available: true, total: 4, facets: { recorded: 4, reviewed: 3, independently_verified: 2 }, flags: { REJECTED: 1, CONTESTED: 0 }, unmapped: 0, can_rely_on: 2, attention: [], ...o });
const summary = (rows) => ({ records: rows, note: "Counts of what ASAVEXA has checked." });
const page = (o = {}) => Assurance({ as: { vocabulary: vocab(), summary: summary([row()]), error: null, ...o }, loading: false, onRetry() {} });

describe("helpers", () => {
  test("rows keep the vocabulary's order and drop zero flags", () => {
    const [r] = A.summaryRows(summary([row()]));
    assert.deepEqual(r.counts, [4, 0, 0, 3, 0, 2]);
    assert.deepEqual(r.flagged, [{ flag: "REJECTED", text: "Rejected", n: 1 }]);
    assert.equal(r.canRely, 2);
  });
  test("an unavailable type is flagged, never shown as empty", () => {
    const [r] = A.summaryRows(summary([row({ available: false, total: 0 })]));
    assert.equal(r.available, false); assert.match(A.unavailableText(r), /could not be read/);
  });
  test("reliance is worded as a count, with 'none yet' for an empty type", () => {
    assert.equal(A.relyText({ total: 4, canRely: 3 }), "3 of 4 (75%)"); assert.equal(A.relyText({ total: 0, canRely: 0 }), "none yet");
    assert.equal(A.percent(1, 3), 33.3); assert.equal(A.percent(0, 0), 0);
  });
  test("empty input is safe", () => { assert.deepEqual(A.summaryRows(null), []); assert.equal(A.flagText("NOPE"), "NOPE"); });
});

describe("page", () => {
  test("shows the six kinds, the flags, the counts and the not-a-score note", () => {
    const out = text(page());
    for (const f of A.FACET_ORDER) assert.ok(out.includes(`"data-facet":"${f}"`), f);
    for (const f of Object.keys(A.FLAG_TEXT)) assert.ok(out.includes(`"data-flag":"${f}"`), f);
    assert.ok(out.includes("not a score")); assert.ok(out.includes("2 of 4 (50%)")); assert.ok(out.includes("1 rejected"));
  });
  test("an unavailable record type is stated on its row", () => {
    const out = text(page({ summary: summary([row({ available: false })]) }));
    assert.ok(out.includes("data-unavailable")); assert.ok(out.includes("could not be read just now"));
  });
  test("unmapped statuses are shown as such", () => {
    assert.ok(text(page({ summary: summary([row({ unmapped: 2 })]) })).includes("2 not mapped"));
  });
  test("the mapping tables list each module's own status words", () => {
    const out = text(page());
    assert.ok(out.includes('"data-map":"finding"')); assert.ok(out.includes('"data-status":"VERIFIED"')); assert.ok(out.includes("Nothing yet"));
  });
  test("a refresh button is offered when the page can reload, and is disabled while loading", () => {
    const find = (v, pred, out = []) => { if (!v || typeof v !== "object") return out; if (pred(v)) out.push(v); for (const c of v.children || []) find(c, pred, out); return out; };
    const btn = (v) => find(v, (n) => n.props && n.props.id === "as-refresh")[0];
    assert.equal(btn(Assurance({ as: { error: null }, loading: false, onRetry() {} })), undefined);
    assert.equal(btn(Assurance({ as: { error: null }, loading: false, onRetry() {}, onRefresh() {} })).props.disabled, false);
    assert.equal(btn(Assurance({ as: { error: null }, loading: true, onRetry() {}, onRefresh() {} })).props.disabled, true);
  });
  test("loading and error states", () => {
    assert.ok(text(Assurance({ as: { error: null }, loading: true, onRetry() {} })).length > 0);
    assert.ok(text(Assurance({ as: { error: "No." }, loading: false, onRetry() {} })).includes("No."));
  });
});

describe("wiring", () => {
  test("client endpoints", () => {
    const calls = []; const c = new ApiClient("http://x"); c.get = (p) => (calls.push(p), {});
    c.assuranceVocabulary(); c.assuranceSummary();
    assert.deepEqual(calls, ["/assurance/vocabulary", "/assurance/summary"]);
  });
  test("it is in the navigation", () => {
    assert.ok(NAV_GROUPS.some((g) => g.paths.includes("/assurance")));
  });
});
