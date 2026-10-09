import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { Standards } from "../src/pages/Standards.js";

const catalog = {
  jurisdictions: [{ code: "NG", name: "Nigeria" }, { code: "US", name: "United States" }],
  entity_types: [{ code: "SME", name: "Small or medium-sized entity" }],
  frameworks: [{ code: "IFRS", name: "IFRS (full)" }, { code: "IFRS_FOR_SMES", name: "IFRS for SMEs" }],
};
const preview = {
  framework: "IFRS_FOR_SMES",
  chain: [{ step: "Jurisdiction", value: "Nigeria" }, { step: "Entity type", value: "SME" }, { step: "Reporting framework", value: "IFRS for SMEs" }],
  recommendation: { framework: "IFRS_FOR_SMES", alternatives: ["IFRS"], rationale: "Because SME.", confidence: "confirm" },
  warnings: ["ASAVEXA cannot yet produce these mandatory statements: Cash flows."],
  policies: [
    { code: "INVENTORY_COSTING", name: "Inventory costing", description: "d", note: "n", locked: false, default: "FIFO", effective: "FIFO", options: [{ code: "FIFO", label: "FIFO" }, { code: "WEIGHTED_AVERAGE", label: "Weighted" }] },
    { code: "BORROWING_COSTS", name: "Borrowing costs", description: "d", note: "n", locked: true, default: "EXPENSE", effective: "EXPENSE", options: [{ code: "EXPENSE", label: "Expense borrowing costs" }] },
  ],
  requirements: [
    { code: "SFP", name: "Statement of financial position", mandatory: true, available: true, description: "x" },
    { code: "SCF", name: "Statement of cash flows", mandatory: true, available: false, description: "y" },
  ],
  readiness: { mandatory_available: 1, mandatory_total: 2, missing: ["Statement of cash flows"] },
  disclaimer: "Not legal advice.",
};
const base = { role: "OWNER", organisationName: "Acme", catalog, form: { jurisdiction: "NG", entity_type: "SME" }, preview, onFieldChange: () => {}, onPolicyChange: () => {}, onUseRecommended: () => {}, onSave: () => {} };
const text = (v) => JSON.stringify(v);
function find(v, pred, acc = []) { if (!v || typeof v !== "object") return acc; if (pred(v)) acc.push(v); for (const c of v.children || []) find(c, pred, acc); return acc; }

describe("Standards page", () => {
  test("shows the full chain starting at the organisation", () => {
    const t = text(Standards(base));
    for (const s of ["Acme", "Nigeria", "IFRS for SMEs", "1. Jurisdiction and entity type", "2. Reporting framework", "3. Accounting policies", "4. Reporting requirements"]) assert.ok(t.includes(s), s);
  });
  test("is honest about statements ASAVEXA cannot produce yet", () => {
    const t = text(Standards(base));
    assert.ok(t.includes("Not yet available"));
    assert.ok(t.includes("1 of 2 mandatory"));
    assert.ok(t.includes("cannot yet produce"));
  });
  test("a locked policy has no dropdown and says it is required; a free one does", () => {
    const vn = Standards(base);
    const t = text(vn);
    assert.ok(t.includes("Required by this framework"));
    const selects = find(vn, (n) => n.tag === "select");
    // jurisdiction, entity type, framework, one free policy
    assert.equal(selects.length, 4);
  });
  test("changing a policy reports its code and the new treatment", () => {
    const calls = [];
    const vn = Standards({ ...base, onPolicyChange: (c, v) => calls.push([c, v]) });
    const sel = find(vn, (n) => n.tag === "select" && n.props.value === "FIFO")[0];
    sel.props.onChange({ target: { value: "WEIGHTED_AVERAGE" } });
    assert.deepEqual(calls, [["INVENTORY_COSTING", "WEIGHTED_AVERAGE"]]);
  });
  test("selecting a jurisdiction reports the field", () => {
    const calls = [];
    const vn = Standards({ ...base, onFieldChange: (f, v) => calls.push([f, v]) });
    find(vn, (n) => n.tag === "select" && n.props.value === "NG")[0].props.onChange({ target: { value: "US" } });
    assert.deepEqual(calls, [["jurisdiction", "US"]]);
  });
  test("'Use recommended' appears only when a non-recommended framework is in use", () => {
    assert.ok(!text(Standards(base)).includes("Use recommended"));
    const other = { ...preview, framework: "IFRS" };
    assert.ok(text(Standards({ ...base, preview: other })).includes("Use recommended"));
  });
  test("a viewer without settings permission sees everything read-only with no save button", () => {
    const vn = Standards({ ...base, role: "AUDITOR" });
    const t = text(vn);
    assert.ok(!t.includes("Save configuration"));
    assert.ok(t.includes("only an owner or administrator"));
    assert.ok(find(vn, (n) => n.tag === "select").every((s) => s.props.disabled));
  });
  test("owner can save", () => {
    let saved = false;
    const vn = Standards({ ...base, onSave: () => { saved = true; } });
    find(vn, (n) => n.tag === "button" && text(n.children).includes("Save configuration"))[0].props.onClick();
    assert.equal(saved, true);
  });
  test("no preview until jurisdiction and entity type are chosen; errors and loading render", () => {
    assert.ok(!text(Standards({ ...base, preview: null })).includes("How ASAVEXA reads"));
    assert.ok(text(Standards({ ...base, loading: true })).includes("Loading"));
    assert.ok(text(Standards({ ...base, error: "boom", preview: null })).includes("boom"));
    assert.ok(text(Standards({ ...base, previewError: "bad choice" })).includes("bad choice"));
  });
  test("shows the disclaimer", () => {
    assert.ok(text(Standards(base)).includes("Not legal advice."));
  });
});
