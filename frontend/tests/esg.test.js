import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { Esg } from "../src/pages/Esg.js";
import * as F from "../src/lib/esg.js";
import { ApiClient } from "../src/api/client.js";
import { NAV_GROUPS } from "../src/lib/home.js";
import * as E from "../src/lib/entityConfig.js";

const text = (v) => JSON.stringify(v);
const noop = new Proxy({}, { get: () => () => {} });
// u1 proposes, u3 decides, u9 bystander
const entry = (o = {}) => ({ id: "e1", ref: "ER-001", scope: "SCOPE_1", category: "FUEL", description: "Diesel for the generator", period_start: "2025-01-01", period_end: "2025-12-31", year: 2025, quantity: "1250.5", unit: "litres", factor: "2.68", factor_source: "National factor table 2024", factor_year: 2024,
  kg_co2e: "3351.34", tonnes: "3.351", status: "PROPOSED", proposed_by: "u1", decision_note: null, old_factor: false, history: [], ...o });
const target = (o = {}) => ({ id: "t1", ref: "TG-001", label: "Cut total emissions", scope: "ALL", baseline_year: 2024, baseline_tonnes: "1250.5", reduction_pct: "42.5", target_year: 2025, target_tonnes: "719.038", status: "PROPOSED", proposed_by: "u1", decision_note: null, actual_tonnes: "3.851", within_target: true, change_vs_baseline_pct: "-99.69", year_ended: false, history: [], ...o });
const ovw = () => ({ counts: { entries_proposed: 1, entries_verified: 2, entries_rejected: 0, targets_proposed: 1, targets_approved: 1, targets_rejected: 0 },
  years: [{ year: 2025, total_kg: "3851.34", total_tonnes: "3.851", scopes: { SCOPE_1: { kg: "3351.34", tonnes: "3.351" }, SCOPE_2: { kg: "500.00", tonnes: "0.500" }, SCOPE_3: { kg: "0.00", tonnes: "0.000" } } }],
  targets: [target({ status: "APPROVED" })], attention: [{ kind: "ENTRIES_TO_VERIFY", count: 1, text: "emission record(s) are waiting for a different person to verify them." }], setting: { factor_max_age_years: 5, meaning: "A verified entry whose factor is older than 5 years is flagged." }, limitations: ["ASAVEXA supplies no emission factors."] });
const state = (o = {}) => ({ tab: "overview", ov: ovw(), entries: [entry()], targets: [target()], forms: { ...JSON.parse(JSON.stringify(F.EMPTY)), setting: { factor_max_age_years: "5" } }, notes: {}, formError: null, busy: false, error: null, notice: null, ...o });
const page = (o = {}, role = "OWNER", me = "u9") => Esg({ es: state(o), role, userId: me, loading: false, onRetry() {}, actions: noop });

describe("permissions", () => {
  test("who can prepare and approve", () => {
    for (const r of ["OWNER", "ADMINISTRATOR", "MANAGER", "AUDITOR"]) assert.ok(F.canPrepare(r), r);
    for (const r of ["OWNER", "APPROVER", "MANAGER"]) assert.ok(F.canApprove(r), r);
    for (const r of ["ACCOUNTANT", "READ_ONLY", "EXTERNAL_AUDITOR", "INVESTOR_REVIEWER"]) { assert.ok(!F.canPrepare(r), r); assert.ok(!F.canApprove(r), r); }
  });
});

describe("payload builders", () => {
  const e = { scope: "SCOPE_1", category: "FUEL", description: "Diesel for the generator", period_start: "2025-01-01", period_end: "2025-12-31", quantity: "1,250.5", unit: "litres", factor: "2.68", factor_source: "National factor table", factor_year: "2024" };
  test("entry", () => {
    const b = F.entryPayload(e).body; assert.deepEqual([b.quantity, b.factor, b.factor_year], ["1250.5", "2.68", 2024]);
    for (const bad of [{ description: "abc" }, { period_start: "2025-02-30" }, { period_end: "2024-12-31" }, { period_end: "2026-01-02" }, { quantity: "0" }, { quantity: "1.23456" }, { quantity: "x" }, { quantity: "1,00" }, { unit: "" }, { factor: "0" }, { factor: "1.2345678" }, { factor_source: "abc" }, { factor_year: "1980" }, { factor_year: "24" }, { factor_year: "" }]) assert.ok(F.entryPayload({ ...e, ...bad }).problem, text(bad));
  });
  const t = { label: "Cut total emissions", scope: "ALL", baseline_year: "2024", baseline_tonnes: "1250.500", reduction_pct: "42.5", target_year: "2030" };
  test("target", () => {
    const b = F.targetPayload(t).body; assert.deepEqual([b.baseline_year, b.target_year, b.reduction_pct], [2024, 2030, "42.5"]);
    for (const bad of [{ label: "ab" }, { baseline_year: "1980" }, { target_year: "2024" }, { target_year: "2023" }, { target_year: "2101" }, { baseline_tonnes: "0" }, { baseline_tonnes: "1.2345" }, { reduction_pct: "100.01" }, { reduction_pct: "0" }, { reduction_pct: "1.234" }]) assert.ok(F.targetPayload({ ...t, ...bad }).problem, text(bad));
    assert.ok(F.targetPayload({ ...t, reduction_pct: "100" }).body);
  });
  test("setting", () => { assert.equal(F.settingPayload("5").body.factor_max_age_years, 5); for (const bad of ["0", "21", "x", "", "2.5"]) assert.ok(F.settingPayload(bad).problem, bad); });
});

describe("buttons", () => {
  test("only a different approver decides", () => {
    const x = entry();
    assert.ok(F.canDecide(x, "APPROVER", "u3")); assert.ok(!F.canDecide(x, "APPROVER", "u1")); assert.ok(!F.canDecide(x, "AUDITOR", "u3")); assert.ok(!F.canDecide(entry({ status: "VERIFIED" }), "APPROVER", "u3"));
  });
});

describe("page", () => {
  test("overview", () => {
    const t = text(page()); assert.match(t, /es-banner/); assert.match(t, /supplies no emission factors/); assert.match(t, /3\.851 tonnes CO2e \(3851\.34 kg\)/); assert.match(t, /Within target/); assert.match(t, /es-set-save/);
    assert.ok(!/es-set-save/.test(text(page({}, "AUDITOR"))));
    assert.match(text(page({ ov: { ...ovw(), years: [] } })), /Only verified records count/);
  });
  test("entries list and form", () => {
    const t = text(page({ tab: "entries" })); assert.match(t, /ER-001/); assert.match(t, /1250\.5 litres x 2\.68/); assert.match(t, /= 3351\.34 kg CO2e \(3\.351 tonnes\)/); assert.match(t, /es-en-save/); assert.ok(!/es-en-save/.test(text(page({ tab: "entries" }, "READ_ONLY"))));
    assert.match(text(page({ tab: "entries", entries: [entry({ status: "VERIFIED", old_factor: true })] })), /Old factor/);
  });
  test("different person only", () => {
    const other = text(page({ tab: "entries" }, "APPROVER", "u3")); assert.match(other, /es-en-ER-001-approve/); assert.match(other, /es-en-ER-001-reject/);
    const same = text(page({ tab: "entries" }, "APPROVER", "u1")); assert.ok(!/es-en-ER-001-approve/.test(same)); assert.match(same, /so a different person must decide it/);
    const tg = text(page({ tab: "targets" }, "APPROVER", "u3")); assert.match(tg, /es-tg-TG-001-approve/); assert.match(tg, /719\.038/);
    assert.ok(!/es-tg-TG-001-approve/.test(text(page({ tab: "targets" }, "APPROVER", "u1"))));
    assert.match(text(page({ tab: "targets" })), /es-tg-save/);
  });
  test("loading and error", () => { assert.match(text(Esg({ es: state(), role: "OWNER", userId: "u9", loading: true, onRetry() {}, actions: noop })), /./); assert.match(text(page({ error: "Boom" })), /Boom/); });
});

describe("wiring", () => {
  test("client paths", async () => {
    const calls = []; const c = new ApiClient({ baseUrl: "http://x" }); for (const k of ["get", "post", "put"]) c[k] = async (p, b) => { calls.push([k, p, b]); return {}; };
    await c.verifyEsEntry("e 1", "ok"); await c.rejectEsTarget("t1", "why"); await c.setEsSetting({ factor_max_age_years: 3 }); await c.addEsEntry({});
    assert.deepEqual(calls.map((x) => x[0] + " " + x[1]), ["post /esg/entries/e%201/verify", "post /esg/targets/t1/reject", "put /esg/setting", "post /esg/entries"]);
  });
  test("nav and entity paths", () => { assert.ok(text(NAV_GROUPS).includes("/esg")); assert.equal(E.WORKSPACE_PATHS.esg, "/esg"); });
});
