import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { Pubfin } from "../src/pages/Pubfin.js";

const walk = (v, fn) => { if (!v || typeof v !== "object") return; fn(v); (v.children || []).forEach((c) => walk(c, fn)); };
const all = (v, pred) => { const out = []; walk(v, (n) => { if (pred(n)) out.push(n); }); return out; };
const text = (v) => { if (v == null || v === false) return ""; if (typeof v !== "object") return String(v); return (v.children || []).map(text).join(""); };
const byId = (v, id) => all(v, (n) => n.props && n.props.id === id)[0];

const ov = (o = {}) => ({ counts: { budgets_approved: 1, budgets_waiting: 0, commitments_open: 0, procurements_open: 0, awards_waiting: 0, grants_active: 1, spend_waiting: 0, virements_waiting: 0 },
  overspent_lines: [{ budget_id: "b1", account_id: "a1", budget_ref: "B-001", code: "5100", name: "Rent", available: "-3400.00" }],
  grants_expired: [{ id: "g1", ref: "G-001", title: "Old", end: "2025-12-31", remaining: "900.00" }],
  grants_overspent_vs_received: [{ id: "g2", ref: "G-002", title: "Late cash", spent: "500.00", received: "100.00" }], policy: { meaning: "p" }, limitations: [], ...o });
const page = (o, calls = []) => Pubfin({ pf: { tab: "overview", ov: ov(o), options: null, policyForm: null, notes: {}, budgets: [], grants: [], commitments: [] }, role: "ACCOUNTANT", userId: "u", loading: false, onRetry() {}, actions: { setTab() {}, openSpend: (...x) => calls.push(["spend", ...x]), openFollow: (x) => calls.push(["follow", x]) }, sector: "ngo" });

describe("Needs attention opens the proof", () => {
  test("an overspent line opens that budget and that line", () => {
    const calls = [], v = page({}, calls); byId(v, "pf-over-b1-5100").props.onClick(); assert.deepEqual(calls, [["spend", "b1", "a1"]]);
  });
  test("both grant lists open Follow for that grant", () => {
    const calls = [], v = page({}, calls); byId(v, "pf-expired-G-001").props.onClick(); byId(v, "pf-overrcv-G-002").props.onClick(); assert.deepEqual(calls, [["follow", "g1"], ["follow", "g2"]]);
  });
  test("the sentence is unchanged and the server's figure is restated", () => assert.match(text(byId(page(), "pf-overspent")), /B-001 5100 Rent: available -3,400\.00/));
  test("older server without ids: text only, no broken button", () => {
    const v = page({ overspent_lines: [{ budget_ref: "B-001", code: "5100", name: "Rent", available: "-3400.00" }], grants_expired: [{ ref: "G-001", title: "Old", end: "2025-12-31", remaining: "900.00" }] });
    assert.equal(all(byId(v, "pf-overspent"), (n) => n.tag === "button").length, 0); assert.equal(byId(v, "pf-expired-G-001"), undefined);
  });
});
