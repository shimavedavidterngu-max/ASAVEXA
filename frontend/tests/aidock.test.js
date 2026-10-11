import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import * as D from "../src/lib/aidock.js";
import { AiDock, Seal } from "../src/components/AiDock.js";
import { ApiError } from "../src/api/client.js";

const F = JSON.parse(readFileSync(new URL("./fixtures/ai-scenario.json", import.meta.url), "utf8"));
const text = (v) => JSON.stringify(v);
function find(v, pred, out = []) { if (!v || typeof v !== "object") return out; if (pred(v)) out.push(v); for (const c of v.children || []) find(c, pred, out); return out; }
const byId = (v, id) => find(v, (n) => n.props && n.props.id === id)[0];
const noop = new Proxy({}, { get: () => () => {} });

describe("which workspace the person is in", () => {
  test("paths map to workspaces; everything else is general", () => {
    const m = { "/": "general", "/accounting": "general", "/evidence/abc": "general", "/cyber": "cyber", "/health": "health", "/health/x": "health", "/grc": "grc", "/pubfin": "pubfin", "/bizdev": "bizdev", "/tax": "tax", "/analysis": "analysis", "/forensic": "forensic", "/healthy": "general", "/cyberx": "general" };
    for (const [p, w] of Object.entries(m)) assert.equal(D.workspaceForPath(p), w, p);
  });
  test("the dock is offered only to roles that can ask or brief", () => {
    for (const r of ["OWNER", "ACCOUNTANT", "AUDITOR", "READ_ONLY", "ADMINISTRATOR", "MANAGER"]) assert.ok(D.dockAvailable(r), r);
    for (const r of ["DONOR", "REGULATOR", "INVESTOR_REVIEWER"]) assert.ok(!D.dockAvailable(r), r);
    assert.ok(D.canAsk("OWNER") && !D.canAsk("DONOR"));
  });
});

describe("briefs are honest", () => {
  test("empty data gives one 'nothing waiting' line, never an invented figure", () => {
    for (const [ws, data] of [["cyber", { counts: {}, vulnerabilities: {}, attention: {} }], ["bizdev", { counts: {} }], ["grc", { counts: {}, attention: {} }], ["tax", { selected: 2, selected_without_rules: [], rules_waiting: 0 }], ["pubfin", { counts: {} }], ["forensic", []], ["health", { facility: "North", metrics: {} }], ["general", []]]) {
      const items = D.buildBrief(ws, data);
      assert.equal(items.length, 1, ws); assert.equal(items[0].tone, "clear", ws); assert.match(items[0].text, /Nothing is waiting/, ws);
    }
  });
  test("urgent items come before watch items, with correct singular and plural", () => {
    const items = D.buildBrief("cyber", { counts: { fixes_waiting: 2, incidents_open: 1 }, vulnerabilities: { overdue: 1 }, attention: { acceptance_expired: [{}, {}] } });
    assert.deepEqual(items.map((i) => i.tone), ["urgent", "urgent", "watch", "watch"]);
    assert.match(items[0].text, /^1 vulnerability is past its fix deadline$/); assert.match(items[1].text, /^2 accepted risks have expired$/);
    assert.match(items[2].text, /^2 fixes are waiting/); assert.match(items[3].text, /^1 incident is open$/);
  });
  test("tax says so when no jurisdiction is selected", () => {
    assert.match(D.buildBrief("tax", { selected: 0, selected_without_rules: [], rules_waiting: 0 })[0].text, /No tax jurisdiction/);
  });
  test("health only counts metrics the server marked OK and says when claims are hidden", () => {
    const m = (value, state = "OK") => ({ value, state });
    const items = D.buildBrief("health", { facility: "North", currency: "NGN", metrics: { exceptions: m(2), expiry: m(null, "UNAVAILABLE"), low_stock: m(3), awaiting_approval: m(1), payables: m("500.00"), unreconciled: m(null, "RESTRICTED"), claims_pending: m(null, "RESTRICTED") } });
    const t = items.map((i) => i.text).join("|");
    assert.match(t, /2 procurement exceptions/); assert.match(t, /3 items are at or below/); assert.match(t, /1 purchase request is waiting/); assert.match(t, /Supplier payables outstanding: 500.00 NGN/); assert.match(t, /Claims figures are hidden/);
    assert.ok(!/expire/.test(t));
  });
  test("evidence brief separates unverified from problem files", () => {
    const items = D.buildBrief("general", [{ status: "UPLOADED" }, { status: "UPLOADED" }, { status: "VERIFIED" }, { status: "REJECTED" }]);
    assert.equal(items[0].tone, "urgent"); assert.match(items[0].text, /^1 evidence file has a problem/); assert.match(items[1].text, /^2 evidence files are waiting/);
  });
  test("latest period is chosen by end date", () => {
    assert.equal(D.latestPeriod([{ id: "a", end_date: "2026-01-31" }, { id: "b", end_date: "2026-03-31" }, { id: "c", end_date: "2026-02-28" }]).id, "b");
    assert.equal(D.latestPeriod([]), null);
  });
});

describe("fetching a brief goes through the person's own permissions", () => {
  const api = (over = {}) => new Proxy({ calls: [], async cyOverview() { this.calls.push("cy"); return { counts: { fixes_waiting: 1 }, vulnerabilities: {}, attention: {} }; },
    async listEvidence() { this.calls.push("ev"); return []; }, async hcOptions() { return { facilities: [{ id: "f1", name: "North" }, { id: "f2", name: "South" }] }; },
    async hcGet(p) { this.calls.push(p); return { facility: "South", metrics: {} }; }, ...over }, { get: (t, k) => t[k] });
  test("a role without the workspace permission never calls the server", async () => {
    const a = api(); const out = await D.fetchBrief(a, "cyber", "DONOR");
    assert.deepEqual([out.ok, out.reason], [false, "denied"]); assert.deepEqual(a.calls, []);
  });
  test("a permitted role gets items, a source and a time", async () => {
    const a = api(); const out = await D.fetchBrief(a, "cyber", "OWNER", {}, () => new Date("2026-02-15T09:30:00Z"));
    assert.ok(out.ok && out.items.length === 1 && out.source === "Cybersecurity overview" && out.asOf === "2026-02-15T09:30:00.000Z");
  });
  test("the server's refusal is shown as a refusal, not an empty brief", async () => {
    const a = api({ async cyOverview() { throw new ApiError(403, { message: "no" }, "/cyber/overview"); } });
    const out = await D.fetchBrief(a, "cyber", "OWNER"); assert.deepEqual([out.ok, out.reason], [false, "denied"]);
  });
  test("a failure says it failed", async () => {
    const a = api({ async cyOverview() { throw new Error("Network down"); } });
    const out = await D.fetchBrief(a, "cyber", "OWNER"); assert.deepEqual([out.ok, out.reason, out.message], [false, "error", "Network down"]);
  });
  test("health uses the facility the person is on, else the first one they can see", async () => {
    let a = api(); await D.fetchBrief(a, "health", "OWNER", { facilityId: "f2" }); assert.ok(a.calls.includes("/facilities/f2/dashboard"));
    a = api(); await D.fetchBrief(a, "health", "OWNER", { facilityId: "gone" }); assert.ok(a.calls.includes("/facilities/f1/dashboard"));
    a = api({ async hcOptions() { return { facilities: [] }; } }); assert.equal((await D.fetchBrief(a, "health", "OWNER")).reason, "none");
  });
  test("general brief needs evidence access", async () => {
    assert.equal((await D.fetchBrief(api(), "general", "DONOR")).reason, "denied");
    assert.ok((await D.fetchBrief(api(), "general", "OWNER")).ok);
  });
});

describe("answers from the real AI engine", () => {
  test("a real Detect answer becomes cards with stamps and a five-bead proof thread", () => {
    const a = D.summariseAnswer(F.detect);
    assert.ok(a.grounded && a.items.length >= 1 && a.items.length <= 5);
    for (const it of a.items) {
      assert.deepEqual(it.thread.map((t) => t.key), ["source_records", "evidence", "journal", "accounting_treatment", "reporting_framework"]);
      assert.ok(it.confidence && ["HIGH", "MEDIUM", "LOW"].includes(it.confidence.level));
      if (it.confidence.level !== "HIGH") assert.ok(it.review, "anything below HIGH must be flagged for a person");
    }
  });
  test("a missing evidence link is shown as missing", () => {
    const raw = JSON.parse(JSON.stringify(F.detect)); const it = raw.items[0];
    it.evidence = { available: false, note: "No evidence is linked." };
    const t = D.summariseAnswer(raw).items[0].thread.find((x) => x.key === "evidence");
    assert.equal(t.ok, false); assert.equal(t.note, "No evidence is linked.");
  });
  test("unverified evidence is 'partly', not solid", () => {
    const raw = JSON.parse(JSON.stringify(F.detect)); raw.items[0].evidence = { available: true, state: "UPLOADED", records: [] };
    const t = D.summariseAnswer(raw).items[0].thread.find((x) => x.key === "evidence");
    assert.ok(t.ok && t.partial);
  });
  test("an ungrounded answer is a refusal with no items", () => {
    const a = D.summariseAnswer({ grounded: false, summary: "I cannot answer that from your records.", refusal: { reason: "No mode matched." }, limitations: [] });
    assert.deepEqual([a.grounded, a.items.length, a.reason], [false, 0, "No mode matched."]);
  });
  test("null in, null out", () => assert.equal(D.summariseAnswer(null), null));
});

describe("the dock", () => {
  const dock = (o = {}) => ({ ...D.newDock(), ...o });
  const view = (d, role = "OWNER", ws = "cyber", urgent = 0) => AiDock({ dock: d, role, workspace: ws, urgent, a: noop });
  test("closed: only the Seal, with an accessible name, and a badge only when something needs attention", () => {
    const v = view(dock(), "OWNER", "cyber", 3);
    assert.ok(byId(v, "lens-launch") && !byId(v, "lens-panel"));
    assert.equal(byId(v, "lens-launch").props["aria-expanded"], "false"); assert.match(text(byId(v, "lens-launch")), /ASAVEXA AI\. Open the assistant for Cybersecurity/);
    assert.equal(text(byId(v, "lens-drop")).includes("3"), true); assert.ok(!byId(view(dock(), "OWNER", "cyber", 0), "lens-drop"));
    assert.match(text(byId(view(dock(), "OWNER", "cyber", 25), "lens-drop")), /9\+/);
  });
  test("open: names the workspace, has two tabs and the honesty footer", () => {
    const v = view(dock({ open: true }));
    assert.match(text(byId(v, "lens-folio")), /Proof Lens · Cybersecurity/); assert.ok(byId(v, "lens-tab-brief") && byId(v, "lens-tab-ask"));
    assert.match(text(byId(v, "lens-foot")), /no outside AI model/); assert.equal(byId(v, "lens-panel").props.role, "complementary");
  });
  test("a loaded brief is drawn as numbered folio entries with a source line", () => {
    const brief = { ok: true, items: [{ tone: "urgent", text: "1 vulnerability is past its fix deadline", link: "/cyber" }, { tone: "watch", text: "2 fixes are waiting", link: "/cyber" }], source: "Cybersecurity overview", asOf: "2026-02-15T09:30:00Z" };
    const v = view(dock({ open: true, brief }));
    assert.match(text(byId(v, "lens-entry-0")), /f\.1/); assert.match(text(byId(v, "lens-entry-1")), /f\.2/); assert.match(text(byId(v, "lens-meta")), /Source: Cybersecurity overview/);
  });
  test("loading, denied and error states never leave a blank panel", () => {
    assert.ok(byId(view(dock({ open: true, briefLoading: true })), "lens-loading"));
    assert.match(text(byId(view(dock({ open: true, brief: { ok: false, reason: "denied", message: "Your role cannot open it." } })), "lens-brief-problem")), /Not available to your role/);
    const e = view(dock({ open: true, brief: { ok: false, reason: "error", message: "Network down" } })); assert.ok(byId(e, "lens-retry")); assert.match(text(byId(e, "lens-brief-problem")), /Network down/);
  });
  test("the Ask tab is locked for a role without ledger access", () => {
    assert.ok(byId(view(dock({ open: true, tab: "ask" }), "OWNER"), "lens-q"));
    const locked = view(dock({ open: true, tab: "ask" }), "REGULATOR"); assert.ok(byId(locked, "lens-ask-locked") && !byId(locked, "lens-q"));
  });
  test("an answer draws stamps, beads and a human-review warning; a refusal draws no cards", () => {
    const ans = D.summariseAnswer(F.detect), v = view(dock({ open: true, tab: "ask", answer: ans }));
    assert.ok(byId(v, "lens-answer") && find(v, (n) => n.props && /lens-stamp /.test(n.props.className || "")).length >= 1);
    assert.equal(find(v, (n) => n.props && /lens-bead /.test(n.props.className || "")).length, ans.items.length * 5);
    assert.match(text(v), /A person must review this/);
    const r = view(dock({ open: true, tab: "ask", answer: D.summariseAnswer({ grounded: false, summary: "No.", refusal: { reason: "Not in your records." } }) }));
    assert.ok(byId(r, "lens-refusal") && !byId(r, "lens-answer"));
  });
  test("the Seal is an SVG with a check-mark crossbar", () => {
    const s = Seal({ size: 56 }); assert.equal(s.tag, "svg"); assert.ok(find(s, (n) => n.props && n.props.className === "seal-check").length === 1);
    assert.equal(find(s, (n) => n.tag === "line").length, 48);
  });
});
