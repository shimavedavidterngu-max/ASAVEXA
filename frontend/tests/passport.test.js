import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { Passport, fmtMoney, fmtWhen } from "../src/pages/Passport.js";

// This fixture is the output of the REAL backend Passport builder for a
// real multi-module scenario (see tests/test_passport.py): the page is
// tested against the actual response shape, not a hand-written guess.
const passport = JSON.parse(readFileSync(new URL("./fixtures/passport-scenario.json", import.meta.url), "utf8"));

const text = (v) => JSON.stringify(v);
function find(v, pred, acc = []) { if (!v || typeof v !== "object") return acc; if (pred(v)) acc.push(v); for (const c of v.children || []) find(c, pred, acc); return acc; }
const noop = () => {};
const form = { owners: [{ name: "Dara A.", kind: "INDIVIDUAL", ownership_percent: "60", notes: "" }], subsidiaries: [{ name: "Meridian Ghana", relationship: "SUBSIDIARY", jurisdiction: "Ghana", registration_number: "", ownership_percent: "100" }] };
const base = {
  role: "OWNER", passport, structureForm: form,
  onRefresh: noop, onDownload: noop, onPrint: noop, onStructureChange: noop, onAddRow: noop, onRemoveRow: noop, onSaveStructure: noop, onRetry: noop,
};

describe("Passport page", () => {
  test("shows all six sections", () => {
    const t = text(Passport(base));
    for (const s of ["1. Identity", "2. Financial history", "3. Evidence quality", "4. Governance", "5. Reporting", "6. Audit trail"]) assert.ok(t.includes(s), s);
  });

  test("shows the fingerprint, who generated it, and the legal entity", () => {
    const t = text(Passport(base));
    assert.ok(t.includes(passport.fingerprint));
    assert.ok(t.includes("dara@meridian.test"));
    assert.ok(t.includes("Meridian Textiles Limited"));
    assert.ok(t.includes("RC123456"));
  });

  test("identity shows owners, subsidiaries and the reporting periods", () => {
    const t = text(Passport(base));
    for (const s of ["Dara A.", "Holdco", "Meridian Ghana", "FY2026-M01", "FY2026-M02"]) assert.ok(t.includes(s), s);
  });

  test("financial history shows the exact figures from the ledger", () => {
    const t = text(Passport(base));
    assert.ok(t.includes("NGN 1,000,000.00"), "revenue");
    assert.ok(t.includes("NGN 200,000.00"), "expenses");
    assert.ok(t.includes("NGN 800,000.00"), "net income");
    assert.ok(t.includes("80%"), "margin");
    assert.ok(t.includes("NGN 875,000.00"), "assets");
    assert.ok(t.includes("NGN 75,000.00"), "liabilities");
  });

  test("cash flow section is honest that it is not a classified statement", () => {
    const t = text(Passport(base));
    assert.ok(t.includes("does not yet produce a classified cash-flow statement"));
    assert.ok(t.includes("NGN 1,075,000.00"), "money in");
  });

  test("evidence quality lists the transaction with missing evidence and the unreconciled bank line", () => {
    const t = text(Passport(base));
    assert.ok(t.includes("January rent"));
    assert.ok(t.includes("Unknown debit"));
    assert.ok(t.includes("50%"));
  });

  test("governance reports segregation-of-duties violations plainly", () => {
    const t = text(Passport(base));
    assert.ok(t.includes("Violations found"));
    assert.ok(t.includes("Journals: creator is not the poster"));
    assert.ok(t.includes("Not tested yet"));
    assert.ok(t.includes("Can both create and post journals"));
  });

  test("reporting shows the framework and jurisdiction from the standards configuration", () => {
    const t = text(Passport(base));
    assert.ok(t.includes("Nigeria"));
    assert.ok(t.includes("IFRS"));
  });

  test("audit trail shows who created and who posted each journal", () => {
    const t = text(Passport(base));
    assert.ok(t.includes("aisha@meridian.test"));
    assert.ok(t.includes("kwame@meridian.test"));
    assert.ok(t.includes("Created by") && t.includes("Posted by"));
  });

  test("attention messages from the backend are displayed", () => {
    const t = text(Passport(base));
    assert.ok(t.includes("posted journal(s) have no evidence attached"));
  });

  test("an unauthorised role sees an access message, not data", () => {
    const t = text(Passport({ ...base, role: "ACCOUNTANT" }));
    assert.ok(t.includes("don't have access"));
    assert.ok(!t.includes("Meridian"));
  });

  test("loading, error and empty states", () => {
    assert.ok(text(Passport({ ...base, passport: null, loading: true })).includes("Assembling"));
    assert.ok(text(Passport({ ...base, passport: null, error: "boom" })).includes("boom"));
    assert.ok(text(Passport({ ...base, passport: null })).includes("No passport yet"));
  });

  test("a refresh error is shown without discarding the passport", () => {
    const t = text(Passport({ ...base, error: "refresh failed" }));
    assert.ok(t.includes("refresh failed") && t.includes("1. Identity"));
  });

  test("an empty organisation renders without errors", () => {
    const empty = {
      ...passport,
      identity: { ...passport.identity, ownership: { recorded: false, owners: [], total_percent: null }, subsidiaries: { recorded: false, items: [], count: 0 }, reporting_periods: [] },
      financial_history: { ...passport.financial_history, periods: [], status: "incomplete", cash_flows: { available: false, statement_available: false, note: "n", reason: "No bank account has been reconciled yet." } },
      evidence_quality: { ...passport.evidence_quality, exceptions: { count: 0, items: [] }, missing_evidence: { count: 0, items: [] }, bank_reconciliation: { ...passport.evidence_quality.bank_reconciliation, unreconciled: 0, unreconciled_items: [] } },
    };
    const t = text(Passport({ ...base, passport: empty }));
    assert.ok(t.includes("Not recorded yet"));
    assert.ok(t.includes("No bank account has been reconciled yet."));
  });

  test("buttons call their handlers", () => {
    const calls = [];
    const v = Passport({ ...base, onRefresh: () => calls.push("refresh"), onDownload: () => calls.push("download"), onPrint: () => calls.push("print") });
    for (const label of ["Refresh", "Download JSON", "Print"]) {
      const [btn] = find(v, (n) => n.tag === "button" && (n.children || []).includes(label));
      assert.ok(btn, label);
      btn.props.onClick();
    }
    assert.deepEqual(calls, ["refresh", "download", "print"]);
  });
});

describe("Passport ownership editor", () => {
  test("is shown to roles that can manage settings and hidden otherwise", () => {
    assert.ok(text(Passport(base)).includes("Edit owners and subsidiaries"));
    assert.ok(!text(Passport({ ...base, role: "MANAGER" })).includes("Edit owners and subsidiaries"), "a manager may view but not edit");
    assert.ok(text(Passport({ ...base, role: "MANAGER" })).includes("1. Identity"), "a manager can still see the passport");
  });

  test("typing, adding, removing and saving call the right handlers", () => {
    const calls = [];
    const v = Passport({
      ...base,
      onStructureChange: (...a) => calls.push(["change", ...a]), onAddRow: (k) => calls.push(["add", k]),
      onRemoveRow: (k, i) => calls.push(["remove", k, i]), onSaveStructure: () => calls.push(["save"]),
    });
    const [nameInput] = find(v, (n) => n.tag === "input" && n.props.placeholder === "Owner name");
    nameInput.props.onInput({ target: { value: "New Name" } });
    const [pctInput] = find(v, (n) => n.tag === "input" && n.props.placeholder === "e.g. 60");
    pctInput.props.onInput({ target: { value: "55" } });
    const [add] = find(v, (n) => n.tag === "button" && (n.children || []).includes("Add owner"));
    add.props.onClick();
    const [addSub] = find(v, (n) => n.tag === "button" && (n.children || []).includes("Add subsidiary"));
    addSub.props.onClick();
    const [rm] = find(v, (n) => n.tag === "button" && (n.children || []).includes("Remove"));
    rm.props.onClick();
    const [formNode] = find(v, (n) => n.tag === "form");
    let prevented = false;
    formNode.props.onSubmit({ preventDefault: () => { prevented = true; } });
    assert.ok(prevented);
    assert.deepEqual(calls, [["change", "owners", 0, "name", "New Name"], ["change", "owners", 0, "ownership_percent", "55"], ["add", "owners"], ["add", "subsidiaries"], ["remove", "owners", 0], ["save"]]);
  });

  test("shows save errors and the saving state", () => {
    const t = text(Passport({ ...base, structureError: "Owners' percentages add up to 110%", structureSaving: true }));
    assert.ok(t.includes("110%") && t.includes("Saving…"));
    assert.ok(text(Passport({ ...base, structureSaved: true })).includes("Saved."));
  });
});

describe("formatting helpers", () => {
  test("fmtMoney", () => {
    assert.equal(fmtMoney("1075000.00", "NGN"), "NGN 1,075,000.00");
    assert.equal(fmtMoney("0.5"), "0.50");
    assert.equal(fmtMoney(null, "NGN"), "—");
    assert.equal(fmtMoney("abc", "NGN"), "abc");
  });
  test("fmtWhen", () => {
    assert.equal(fmtWhen("2026-03-01T12:00:00+00:00"), "2026-03-01 12:00 UTC");
    assert.equal(fmtWhen(null), "—");
  });
});
