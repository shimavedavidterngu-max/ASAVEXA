import { test, describe } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { EntityConfig } from "../src/pages/EntityConfig.js";
import * as E from "../src/lib/entityConfig.js";
import { ApiClient } from "../src/api/client.js";
import { NAV_GROUPS } from "../src/lib/home.js";
import { CATEGORIES } from "../src/lib/onboarding.js";

const text = (v) => JSON.stringify(v);
const WS = [["analysis", "Financial Analysis", "/analysis"], ["forensic", "Forensic", "/forensic"], ["grc", "GRC", "/grc"], ["tax", "Tax", "/tax"], ["public_finance", "Public Finance", "/pubfin"],
  ["health", "Health", "/health"], ["cyber", "Cyber", "/cyber"], ["bizdev", "Bizdev", "/bizdev"]].map(([id, name, path]) => ({ id, name, path }));
const catalog = () => ({ types: [
  { code: "BUSINESS", label: "Businesses", legacy_category: "Business or SME", subtypes: [{ code: "SME", label: "Small or medium enterprise" }, { code: "STARTUP", label: "Startup" }], suggested_workspaces: ["analysis", "tax"] },
  { code: "HEALTH", label: "Health and care", legacy_category: "Health centre or healthcare facility", subtypes: [{ code: "HOSPITAL", label: "Hospital" }], suggested_workspaces: ["health", "analysis"] },
], note: "These lists are a starting point." });
const cfg = (o = {}) => ({ configured: true, entity_type: "HEALTH", subtype: "HOSPITAL", custom_subtype: null, languages: ["en"], timezone: "Africa/Lagos", enabled_workspaces: ["analysis", "health"], shown_workspaces: ["analysis", "health"],
  suggested_workspaces: ["analysis", "health"], version: 1, history: [{ version: 1, event: "CONFIGURED", by: "u1", note: "", changes: {} }], ...o });
const none = () => ({ configured: false, entity_type: null, shown_workspaces: WS.map((w) => w.id), history: [], languages: [], timezone: null });
const noop = new Proxy({}, { get: () => () => {} });
const state = (o = {}) => { const config = o.config || cfg(); return { catalog: catalog(), config, workspaces: WS, form: E.formFromConfig(config, catalog(), WS, null), formError: null, busy: false, error: null, notice: null, ...o }; };
const page = (o = {}, role = "OWNER") => EntityConfig({ ec: state(o), role, loading: false, onRetry() {}, actions: noop });

describe("menu filtering", () => {
  const items = [{ path: "/" }, { path: "/analysis" }, { path: "/forensic" }, { path: "/pubfin" }, { path: "/health" }, { path: "/accounting" }];
  test("an organisation that has not been set up sees everything", () => {
    assert.equal(E.filterNavByWorkspaces(items, null).length, items.length);
    assert.equal(E.shownFor({ org: "o1", cfg: none() }, "o1"), null);
  });
  test("only workspace entries are hidden; core pages are never touched", () => {
    const out = E.filterNavByWorkspaces(items, ["health"]).map((i) => i.path);
    assert.deepEqual(out, ["/", "/health", "/accounting"]);
  });
  test("an empty list hides every workspace but keeps the core menu", () => {
    assert.deepEqual(E.filterNavByWorkspaces(items, []).map((i) => i.path), ["/", "/accounting"]);
  });
  test("another organisation's set-up is never applied", () => {
    assert.equal(E.shownFor({ org: "o1", cfg: cfg() }, "o2"), null);
    assert.deepEqual(E.shownFor({ org: "o1", cfg: cfg() }, "o1"), ["analysis", "health"]);
    assert.equal(E.shownFor(null, "o1"), null);
  });
  test("the path map matches the server's workspace catalogue and the real menu", () => {
    const py = fs.readFileSync(new URL("../../src/asavexa/workspaces.py", import.meta.url), "utf8");
    const pairs = [...py.matchAll(/"id": "([a-z_]+)", "name": "[^"]+", "phase": \d+, "status": "[^"]+", "path": "([^"]+)"/g)].map((m) => [m[1], m[2]]);
    assert.equal(pairs.length, Object.keys(E.WORKSPACE_PATHS).length);
    for (const [id, path] of pairs) assert.equal(E.WORKSPACE_PATHS[id], path, id);
    const app = fs.readFileSync(new URL("../src/app.js", import.meta.url), "utf8");
    for (const p of Object.values(E.WORKSPACE_PATHS)) assert.ok(app.includes(`{ path: "${p}", label:`), p);
  });
});

describe("helpers", () => {
  test("types, subtypes and suggestions come from the server's catalogue", () => {
    const c = catalog();
    assert.deepEqual(E.typeOptions(c).map((t) => t.code), ["BUSINESS", "HEALTH"]);
    assert.deepEqual(E.subtypeOptions(c, "BUSINESS").map((s) => s.code), ["SME", "STARTUP"]);
    assert.deepEqual(E.subtypeOptions(c, "NOPE"), []);
    assert.deepEqual(E.suggestedFor(c, "HEALTH", WS), ["analysis", "health"]);
  });
  test("every sign-up category the old flow offered can be mapped by the server's catalogue shape", () => {
    const real = fs.readFileSync(new URL("../../src/asavexa/entities/catalog.py", import.meta.url), "utf8");
    for (const c of CATEGORIES) assert.ok(real.includes(`"${c}"`), c);
  });
  test("a sign-up category pre-selects a starting kind", () => {
    assert.equal(E.typeFromLegacy(catalog(), "Business or SME"), "BUSINESS");
    const f = E.formFromConfig(none(), catalog(), WS, "Health centre or healthcare facility");
    assert.equal(f.entity_type, "HEALTH"); assert.deepEqual(f.enabled, ["analysis", "health"]);
    assert.deepEqual(E.formFromConfig(none(), catalog(), WS, "").enabled, WS.map((w) => w.id));
  });
  test("toggling adds and removes", () => {
    assert.deepEqual(E.toggleWorkspace(["a"], "b"), ["a", "b"]); assert.deepEqual(E.toggleWorkspace(["a", "b"], "a"), ["b"]);
  });
  test("languages are split on commas and spaces", () => assert.deepEqual(E.parseLanguages("en, fr-CA  pt"), ["en", "fr-CA", "pt"]));
  test("payload: a kind is required; a reason is required once configured", () => {
    const f = { entity_type: "", subtype: "", custom_subtype: "", enabled: [], languages: "", timezone: "", note: "" };
    assert.match(E.configPayload(f, false).problem, /kind/);
    assert.ok(E.configPayload({ ...f, entity_type: "BUSINESS" }, false).body);
    assert.match(E.configPayload({ ...f, entity_type: "BUSINESS" }, true).problem, /why/);
    const r = E.configPayload({ ...f, entity_type: "BUSINESS", subtype: "SME", custom_subtype: " Co-op ", enabled: ["tax"], languages: "en, fr", timezone: " Africa/Lagos ", note: " moved " }, true);
    assert.deepEqual(r.body, { entity_type: "BUSINESS", subtype: "SME", custom_subtype: "Co-op", enabled_workspaces: ["tax"], languages: ["en", "fr"], timezone: "Africa/Lagos", note: "moved" });
  });
  test("history lines show before and after", () => {
    assert.deepEqual(E.changeLines({ changes: { entity_type: ["BUSINESS", "HEALTH"], enabled_workspaces: [["a"], []] } }), ["Kind: BUSINESS → HEALTH", "Workspaces shown: a → none"]);
  });
  test("hidden count is zero for an organisation that has not been set up", () => {
    assert.equal(E.hiddenCount(none(), WS), 0); assert.equal(E.hiddenCount(cfg(), WS), 6);
  });
});

describe("page", () => {
  test("says what is shown now and that no access changed", () => {
    const t = text(page());
    assert.match(t, /Health and care/); assert.match(t, /Hospital/); assert.match(t, /6 workspace\(s\) are hidden/); assert.match(t, /Nobody's access has changed/);
  });
  test("an unconfigured organisation is told every workspace is shown", () => {
    assert.match(text(page({ config: none(), form: E.formFromConfig(none(), catalog(), WS, "") })), /every workspace is shown/);
  });
  test("every workspace has a checkbox and suggested ones are marked", () => {
    const t = text(page());
    for (const w of WS) assert.ok(t.includes(`ec-ws-${w.id}`), w.id);
    assert.match(t, /\(suggested\)/);
  });
  test("changing asks for a reason; the first set-up does not", () => {
    assert.match(text(page()), /ec-reason/);
    assert.doesNotMatch(text(page({ config: none(), form: E.formFromConfig(none(), catalog(), WS, "") })), /ec-reason/);
  });
  test("a person without the settings permission sees it read-only", () => {
    const t = text(page({}, "AUDITOR"));
    assert.match(t, /ec-readonly/); assert.doesNotMatch(t, /ec-save/);
  });
  test("history lists versions with what changed", () => {
    const t = text(page({ config: cfg({ version: 2, history: [{ version: 1, event: "CONFIGURED", by: "u1", note: "", changes: {} }, { version: 2, event: "CHANGED", by: "u2", note: "we are a hospital", changes: { entity_type: ["BUSINESS", "HEALTH"] } }] }) }));
    assert.match(t, /v2 changed by u2: we are a hospital/); assert.match(t, /BUSINESS → HEALTH/);
  });
  test("errors and notices show", () => {
    assert.match(text(page({ error: "Nope" })), /Nope/); assert.match(text(page({ notice: "Saved." })), /Saved/); assert.match(text(page({ formError: "Choose" })), /ec-form-error/);
  });
});

describe("wiring", () => {
  test("client calls the right paths and verbs", async () => {
    const calls = []; const c = new ApiClient("http://x"); c._request = async (m, p, o) => { calls.push([m, p, o && o.body]); return {}; };
    await c.entityConfig(); await c.entityCatalog(); await c.saveEntityConfig({ entity_type: "BUSINESS" });
    assert.deepEqual(calls.map((x) => x.slice(0, 2)), [["GET", "/entity-config"], ["GET", "/entity-config/catalog"], ["PUT", "/entity-config"]]);
  });
  test("the page is in the menu, in the data group, behind the settings permission", () => {
    assert.ok(NAV_GROUPS.find((g) => g.id === "data").paths.includes("/entity-config"));
    const app = fs.readFileSync(new URL("../src/app.js", import.meta.url), "utf8");
    assert.match(app, /path: "\/entity-config", label: "Organisation type and workspaces", permission: PERMISSIONS\.ORG_MANAGE_SETTINGS/);
    assert.match(app, /ensureEntityConfig\(authState\)/);
  });
  test("a workspace hidden from the menu still gets a proper breadcrumb (not 'Page not found')", () => {
    const app = fs.readFileSync(new URL("../src/app.js", import.meta.url), "utf8");
    assert.match(app, /breadcrumbs\(path, visibleNav\(authState, path, true\)\)/);
  });
  test("signing out forgets the set-up so the next organisation never sees it", () => {
    const app = fs.readFileSync(new URL("../src/app.js", import.meta.url), "utf8");
    assert.match(app, /uiState\.entity = null; uiState\.ec = null/);
  });
});
