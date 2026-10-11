import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { Proof } from "../src/pages/Proof.js";
import * as P from "../src/lib/proof.js";
import { PERMISSIONS } from "../src/lib/permissions.js";
import { ApiClient } from "../src/api/client.js";

const text = (v) => JSON.stringify(v);
function find(v, pred, out = []) { if (!v || typeof v !== "object") return out; if (pred(v)) out.push(v); for (const c of v.children || []) find(c, pred, out); return out; }
const byId = (v, id) => find(v, (n) => n.props && n.props.id === id)[0];
const noop = new Proxy({}, { get: () => () => {} });
const graph = (o = {}) => ({ state: "PARTIAL", meaning: "Every figure ties, but some journals have no evidence.", limits: "This proves traceability.", period_id: "p1", report_type: "balance_sheet",
  summary: { lines: 2, journals: 2, with_evidence: 1, verified: 1, missing_evidence: 1, coverage_pct: 50, verified_pct: 50, tie_failures: 0, truncated: false },
  nodes: [{ id: "report:balance_sheet", kind: "report" }, { id: "line:c", kind: "line", label: "1000 Cash", section: "Assets", amount: "1500.00" }, { id: "line:q", kind: "line", label: "3000 Capital", section: "Equity", amount: "1000.00" },
    { id: "journal:j1", kind: "journal", label: "JE-1", date: "2026-01-02", description: "Owner investment", evidence_status: "MISSING" }, { id: "journal:j2", kind: "journal", label: "JE-2", date: "2026-01-05", description: "Cash sale", evidence_status: "VERIFIED" },
    { id: "evidence:e1", kind: "evidence", label: "invoice.pdf", status: "VERIFIED" }],
  edges: [{ from: "report:balance_sheet", to: "line:c", kind: "reports" }, { from: "report:balance_sheet", to: "line:q", kind: "reports" },
    { from: "line:c", to: "journal:j1", kind: "built_from", debit: "1000.00", credit: "0.00" }, { from: "line:c", to: "journal:j2", kind: "built_from", debit: "500.00", credit: "0.00" },
    { from: "line:q", to: "journal:j1", kind: "built_from", debit: "0.00", credit: "1000.00" }, { from: "journal:j2", to: "evidence:e1", kind: "supported_by" }],
  checks: [{ name: "1000 ties to its journals", ok: true, detail: "x" }], missing: [], unverified: [], ...o });
const layers = [{ id: "financial_core", group: "Core", name: "Financial Core", parts: ["Journals"], ok: true, problems: [] }, { id: "proof_graph", group: "Reporting", name: "Proof-to-Report Graph", parts: ["Report"], ok: false, problems: ["API prefix /proof is not mounted"] }];
const proof = (o = {}) => ({ period_id: "p1", report: "balance_sheet", graph: null, arch: null, open: {}, busy: false, error: null, ...o });
const page = (p, periods = [{ id: "p1", name: "FY2026-M01" }], loading = false) => Proof({ proof: p, periods, loading, onRetry() {}, actions: noop });

describe("chain", () => {
  test("lines list their journals, and a journal shows its evidence or says it has none", () => {
    const c = P.chain(graph());
    assert.equal(c.length, 2); assert.equal(c[0].journals.length, 2);
    assert.equal(c[0].journals[0].evidence, null); assert.equal(c[0].journals[0].evidence_status, "MISSING");
    assert.equal(c[0].journals[1].evidence.label, "invoice.pdf");
    assert.equal(c[1].journals[0].credit, "1000.00");
  });
  test("an empty or missing graph gives nothing", () => { assert.deepEqual(P.chain(null), []); assert.deepEqual(P.chain(graph({ nodes: [], edges: [] })), []); });
  test("states and evidence are described in plain words", () => {
    assert.equal(P.stateInfo("PROVEN").label, "Proven"); assert.equal(P.stateInfo("BROKEN").tone, "fail"); assert.equal(P.stateInfo("ZZ").label, "ZZ");
    assert.match(P.evidenceText("MISSING"), /No evidence/); assert.match(P.evidenceText("UPLOADED"), /not yet verified/);
    assert.equal(P.evidenceTone("VERIFIED"), "pass"); assert.equal(P.evidenceTone("MISSING"), "fail"); assert.equal(P.evidenceTone("UPLOADED"), "warn");
    assert.equal(P.pct(null), "—"); assert.equal(P.pct(50), "50%");
  });
  test("layers are grouped in the order sent, and only failing checks are picked out", () => {
    assert.deepEqual(P.groupLayers(layers).map((g) => g.name), ["Core", "Reporting"]); assert.deepEqual(P.groupLayers(null), []);
    assert.equal(P.failingChecks(graph({ checks: [{ ok: true }, { ok: false, name: "x", detail: "y" }] })).length, 1); assert.deepEqual(P.failingChecks(null), []);
    assert.equal(P.canBuild({ period_id: "p", report: "balance_sheet", busy: false }), true); assert.equal(P.canBuild({ period_id: "", report: "balance_sheet" }), false); assert.equal(P.canBuild({ period_id: "p", report: "x", busy: true }), false);
  });
});

describe("page", () => {
  test("loading, error and no-period states", () => {
    assert.match(text(page(proof(), [], true)), /Loading/i);
    assert.match(text(page(proof({ error: "boom" }))), /boom/);
    assert.match(text(page(proof(), [])), /No accounting periods yet/);
  });
  test("before building, it asks for a period; the build button is on only when a period is chosen", () => {
    assert.match(text(page(proof())), /press the button/);
    assert.equal(byId(page(proof({ period_id: "" })), "proof-build").props.disabled, true);
    assert.equal(byId(page(proof()), "proof-build").props.disabled, false);
    assert.equal(byId(page(proof({ busy: true })), "proof-build").props.disabled, true);
  });
  test("a partly proven report shows its state, counts and a line per figure; journals appear only when opened", () => {
    const v = page(proof({ graph: graph() }));
    assert.equal(byId(v, "proof-state").children.join(""), "Partly proven"); assert.match(text(byId(v, "proof-meaning")), /some journals have no evidence/);
    assert.equal(find(v, (n) => n.props && n.props["data-line"]).length, 2); assert.equal(find(v, (n) => n.props && n.props["data-journal"]).length, 0);
    const o = page(proof({ graph: graph(), open: { "line:c": true } }));
    assert.equal(find(o, (n) => n.props && n.props["data-journal"]).length, 2); assert.match(text(o), /No evidence attached/); assert.match(text(o), /invoice\.pdf/);
  });
  test("a figure that does not tie is shown as an alert, and truncation is said plainly", () => {
    const v = page(proof({ graph: graph({ state: "BROKEN", summary: { ...graph().summary, tie_failures: 1, truncated: true }, checks: [{ name: "1000 ties to its journals", ok: false, detail: "report 1 vs ledger 2" }] }) }));
    assert.equal(byId(v, "proof-state").children.join(""), "Does not tie"); assert.match(text(byId(v, "proof-bad")), /report 1 vs ledger 2/); assert.match(text(v), /only the first ones are drawn/);
  });
  test("the architecture panel shows each layer and the reason a layer is broken", () => {
    assert.ok(byId(page(proof()), "arch-run"));
    const v = page(proof({ arch: { ok: false, layers, flows: [], note: "n" } }));
    assert.equal(byId(v, "arch-state").children.join(""), "Something is missing"); assert.equal(find(v, (n) => n.props && n.props["data-layer"]).length, 2); assert.match(text(v), /API prefix \/proof is not mounted/);
    assert.equal(byId(page(proof({ arch: { ok: true, layers: [layers[0]], flows: [], note: "n" } })), "arch-state").children.join(""), "All layers present and wired");
  });
});

describe("wiring", () => {
  test("reading reports is what lets someone open the page (the server enforces it too)", () => { assert.ok(PERMISSIONS.REPORTING_READ); });
  test("the api client calls the right paths", async () => {
    const calls = []; const api = new ApiClient({ baseUrl: "http://x" }); api.get = async (p, q) => { calls.push([p, q]); return {}; };
    await api.proofGraph("p1", "income_statement"); await api.proofArchitecture();
    assert.deepEqual(calls, [["/proof/graph", { period_id: "p1", report: "income_statement" }], ["/proof/architecture", undefined]]);
  });
});
