import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { buildGrantTrace, fundingStep, receivedStep, spentStep, evidenceStep, sentence, GRANT_ORDER } from "../src/lib/grantTrace.js";
import { Pubfin } from "../src/pages/Pubfin.js";
import { TABS } from "../src/lib/pubfin.js";

const walk = (v, fn) => { if (!v || typeof v !== "object") return; fn(v); (v.children || []).forEach((c) => walk(c, fn)); };
const all = (v, pred) => { const out = []; walk(v, (n) => { if (pred(n)) out.push(n); }); return out; };
const text = (v) => { if (v == null || v === false) return ""; if (typeof v !== "object") return String(v); return (v.children || []).map(text).join(""); };
const byId = (v, id) => all(v, (n) => n.props && n.props.id === id)[0];

const sp = (o = {}) => ({ id: "s1", amount: "5000.00", date: "2026-03-01", description: "Borehole pump", reference: "V-1", status: "APPROVED", evidence: [], ...o });
const grant = (o = {}) => ({ id: "g1", ref: "G-001", title: "Clean water", donor: "Water Fund", amount: "20000.00", currency: "USD", start: "2026-01-01", end: "2026-12-31", restricted: true, conditions: "Wells only", status: "ACTIVE", expired: false,
  receipts: [{ id: "r1", amount: "12000.00", date: "2026-02-01", reference: "BANK-1" }], spend: [sp(), sp({ id: "s2", amount: "1000.00", status: "PROPOSED", reference: "V-2", description: "Pipes" })],
  received: "12000.00", spent: "5000.00", pending: "1000.00", remaining: "15000.00", cash_on_hand: "7000.00", overspent_vs_received: false, ...o });

describe("sentence", () => {
  test("plain words with the server's own figures", () => {
    assert.equal(sentence(grant()), "Of the 20,000.00 USD awarded by Water Fund (restricted), 12,000.00 USD has been received and 5,000.00 USD of spending is approved. 1,000.00 USD more is waiting for a second person to approve it. 15,000.00 USD of the award is still unspent.");
  });
  test("nothing waiting, unrestricted: no waiting sentence", () => {
    const s = sentence(grant({ restricted: false, pending: "0.00" }));
    assert.doesNotMatch(s, /waiting|restricted/);
  });
  test("no grant, no sentence", () => assert.equal(sentence(null), null));
});

describe("steps", () => {
  test("funding: awarded, closed, past its end date", () => {
    assert.equal(fundingStep(grant()).state, "linked");
    assert.match(fundingStep(grant()).meta, /Restricted: it may be spent only as the grant's conditions say. Conditions as entered: Wells only/);
    assert.equal(fundingStep(grant({ status: "CLOSED" })).stateLabel, "Closed");
    assert.equal(fundingStep(grant({ expired: true })).state, "pending");
    assert.match(fundingStep(grant({ conditions: "" })).meta, /No conditions were entered/);
  });
  test("received: none, part, in full", () => {
    assert.equal(receivedStep(grant({ receipts: [], received: "0.00" })).state, "missing");
    assert.equal(receivedStep(grant()).stateLabel, "Partly received");
    assert.equal(receivedStep(grant({ received: "20000.00" })).state, "linked");
  });
  test("spent: waiting is not spent; more than received is flagged in words", () => {
    const s = spentStep(grant());
    assert.deepEqual([s.state, s.stateLabel], ["pending", "Some waiting for approval"]);
    assert.match(s.title, /5,000.00 USD approved in 1 entry/);
    assert.equal(spentStep(grant({ spend: [sp()], pending: "0.00" })).state, "linked");
    assert.equal(spentStep(grant({ spend: [] })).state, "missing");
    const o = spentStep(grant({ overspent_vs_received: true }));
    assert.deepEqual([o.state, o.stateLabel], ["missing", "More spent than received"]);
    assert.match(o.meta, /more than the cash recorded as received/);
  });
  test("a sent-back entry is not counted", () => assert.equal(spentStep(grant({ spend: [sp({ status: "REJECTED" })] })).state, "missing"));
  test("evidence: none, some, all", () => {
    assert.equal(evidenceStep(grant({ spend: [] })).state, "missing");
    const some = evidenceStep(grant({ spend: [sp({ evidence: [{ filename: "inv.pdf" }] }), sp({ id: "s2", reference: "V-2" })] }));
    assert.deepEqual([some.state, some.title], ["pending", "1 of 2 spending entries without evidence"]);
    assert.match(some.meta, /V-2/);
    assert.equal(evidenceStep(grant({ spend: [sp({ evidence: [{ filename: "a" }] })] })).state, "linked");
    assert.equal(evidenceStep(grant()).state, "missing");
  });
});

describe("buildGrantTrace", () => {
  test("four steps in order", () => assert.deepEqual(buildGrantTrace(grant()).steps.map((s) => s.key), GRANT_ORDER));
  test("no grant, no trace", () => assert.equal(buildGrantTrace(null), null));
  test("no arithmetic in the source", () => {
    const src = readFileSync(new URL("../src/lib/grantTrace.js", import.meta.url), "utf8");
    assert.doesNotMatch(src, /parseFloat|Number\(|reduce\(|\bMath\./);
  });
});

describe("the tab and the page", () => {
  test("the tab sits after Grants", () => { const ids = TABS.map(([i]) => i); assert.equal(ids[ids.indexOf("grants") + 1], "follow"); });
  const pf = (o = {}) => ({ tab: "follow", grants: [grant()], budgets: [], commitments: [], notes: {}, ...o });
  const page = (p) => Pubfin({ pf: p, role: "ACCOUNTANT", userId: "u", loading: false, onRetry() {}, actions: { setTab() {}, followGrant() {} } });
  test("it draws the sentence, the figures, the entries and a four-step rail", () => {
    const v = page(pf());
    assert.match(text(byId(v, "pf-follow-sentence")), /awarded by Water Fund \(restricted\)/);
    assert.match(text(byId(v, "pf-follow-figures")), /20,000.00.*12,000.00.*5,000.00.*1,000.00.*15,000.00.*7,000.00/);
    assert.match(text(byId(v, "pf-follow-spend")), /waiting for a different person to approve it/);
    assert.equal(all(byId(v, "pf-follow-rail"), (n) => n.props && n.props.className && String(n.props.className).split(" ").includes("pr-step")).length, 4);
    assert.match(text(byId(v, "pf-follow-limit")), /does not prove the grant produced any programme result/);
  });
  test("no grants says so", () => assert.ok(byId(page(pf({ grants: [] })), "pf-follow-none")));
  test("a read view: no buttons in the ledger", () => assert.equal(all(byId(page(pf()), "pf-follow-ledger"), (n) => n.tag === "button").length, 0));
});

describe("fund mode (faith-based organisations): the donor is never shown", () => {
  const donor = "Mrs Adeyemi";
  const g = () => grant({ donor, title: "Building fund", conditions: "New roof only" });
  test("the sentence names the fund, not the giver", () => {
    const s = sentence(g(), "fund");
    assert.match(s, /set aside for this designated fund/);
    assert.doesNotMatch(s, /Adeyemi|awarded by/);
  });
  test("an undesignated fund is just a fund", () => assert.match(sentence(grant({ restricted: false }), "fund"), /set aside for this fund,/));
  test("no step in fund mode mentions the donor, and the words are about gifts and purpose", () => {
    const t = buildGrantTrace(g(), "fund");
    assert.equal(t.mode, "fund");
    assert.doesNotMatch(JSON.stringify(t.steps), /Adeyemi/);
    assert.match(t.steps[0].meta, /Designated: it may be spent only for its stated purpose. Purpose as entered: New roof only/);
    assert.equal(t.steps[0].stateLabel, "Set up");
    assert.equal(buildGrantTrace(grant({ receipts: [], received: "0.00", donor }), "fund").steps[1].stateLabel, "No gifts recorded yet");
  });
  test("grant mode is unchanged", () => assert.match(buildGrantTrace(g()).steps[0].title, /from Mrs Adeyemi/));
  const pf = (gr) => ({ tab: "follow", grants: [gr], budgets: [], commitments: [], notes: {} });
  const page = (sector) => Pubfin({ pf: pf(g()), role: "ACCOUNTANT", userId: "u", loading: false, onRetry() {}, actions: { setTab() {}, followGrant() {} }, sector });
  test("the whole page in church mode never contains the donor, and says Fund", () => {
    const t = text(page("church"));
    assert.doesNotMatch(t, /Adeyemi/);
    assert.match(t, /Follow a fund/);
    assert.match(text(byId(page("church"), "pf-follow-limit")), /never shows who gave/);
  });
  test("the same page for other sectors still shows the donor (the record is not altered)", () => {
    assert.match(text(page("ngo")), /Adeyemi/);
    assert.match(text(page(undefined)), /Follow a grant/);
  });
});

describe("fund mode also covers the Grants tab", () => {
  const donor = "Mrs Adeyemi";
  const gr = grant({ donor, title: "Building fund" });
  const base = (o = {}) => ({ tab: "grants", grants: [gr], budgets: [], commitments: [], notes: {}, ...o });
  const page = (pf, sector) => Pubfin({ pf, role: "ACCOUNTANT", userId: "u", loading: false, onRetry() {}, actions: { setTab() {}, openGrant() {}, newGrant() {} }, sector });
  test("the list has no donor column or value, and says so", () => {
    const v = page(base(), "church");
    assert.doesNotMatch(text(v), /Adeyemi/);
    assert.doesNotMatch(text(byId(v, "pf-grant-table")), /Donor/);
    assert.match(text(byId(v, "pf-grants-private")), /Who gave is not shown/);
  });
  test("the grant's own page has no donor", () => {
    const v = page(base({ grant: gr }), "church");
    assert.doesNotMatch(text(v), /Adeyemi/);
    assert.match(text(byId(v, "pf-grant")), /2026-01-01 to 2026-12-31\. Restricted/);
  });
  test("the new-fund form asks for a general source, not a person", () => {
    const v = page(base({ grantForm: { title: "", donor: "", amount: "", currency: "NGN", start: "", end: "", restricted: true, conditions: "" } }), "church");
    assert.match(text(byId(v, "grant-form")), /never a person's name/);
  });
  test("other sectors are unchanged: donor column and value are shown", () => {
    const v = page(base(), "ngo");
    assert.match(text(byId(v, "pf-grant-table")), /Donor/);
    assert.match(text(byId(v, "pf-grant-table")), /Adeyemi/);
    assert.equal(byId(v, "pf-grants-private"), undefined);
    assert.match(text(byId(page(base({ grant: gr }), undefined), "pf-grant")), /Mrs Adeyemi\. 2026-01-01/);
  });
});

describe("server-side donor privacy (Stage 12)", () => {
  const priv = (hide) => ({ hide_donor: hide, meaning: hide ? "Who gave is not stored for new grants and is not shown or exported. Names already stored are hidden, not erased." : "Who gave is stored and shown." });
  const pfOv = (hide) => ({ tab: "overview", options: { privacy: priv(hide) }, ov: { counts: { budgets_approved: 0, budgets_waiting: 0, commitments_open: 0, procurements_open: 0, awards_waiting: 0, grants_active: 0, spend_waiting: 0, virements_waiting: 0 }, overspent_lines: [], grants_expired: [], grants_overspent_vs_received: [], policy: { meaning: "p" }, limitations: [] }, policyForm: null, notes: {}, budgets: [], grants: [], commitments: [] });
  const page = (pf, role, calls = []) => Pubfin({ pf, role, userId: "u", loading: false, onRetry() {}, actions: { setTab() {}, setPrivacy: (x) => calls.push(x) }, sector: "ngo" });
  test("an approver sees the state and a toggle that sends the opposite value", () => {
    const calls = [], v = page(pfOv(false), "OWNER", calls);
    assert.match(text(byId(v, "pf-privacy-state")), /^Shown\./);
    byId(v, "pf-privacy-toggle").props.onClick(); assert.deepEqual(calls, [true]);
    assert.match(text(byId(page(pfOv(true), "OWNER"), "pf-privacy-state")), /^Hidden\..*hidden, not erased/);
  });
  test("someone who cannot approve sees the state but no toggle", () => {
    const v = page(pfOv(true), "ACCOUNTANT");
    assert.ok(byId(v, "pf-privacy-state")); assert.equal(byId(v, "pf-privacy-toggle"), undefined);
  });
  test("a hidden donor is never printed as if it were a name", () => {
    const g = grant({ donor: "Not recorded" });
    assert.doesNotMatch(sentence(g), /Not recorded|by /);
    assert.match(sentence(g), /^Of the 20,000.00 USD awarded \(restricted\)/);
    assert.doesNotMatch(buildGrantTrace(g, "grant").steps[0].title, /from|Not recorded/);
  });
});

describe("erasing stored donor names (Stage 13)", () => {
  const ov = (hide) => ({ tab: "overview", options: { privacy: { hide_donor: hide, meaning: "m" } }, ov: { counts: { budgets_approved: 0, budgets_waiting: 0, commitments_open: 0, procurements_open: 0, awards_waiting: 0, grants_active: 0, spend_waiting: 0, virements_waiting: 0 }, overspent_lines: [], grants_expired: [], grants_overspent_vs_received: [], policy: { meaning: "p" }, limitations: [] }, policyForm: null, notes: {}, budgets: [], grants: [], commitments: [] });
  const page = (pf, role, calls = []) => Pubfin({ pf, role, userId: "u", loading: false, onRetry() {}, actions: { setTab() {}, setPrivacy() {}, eraseChange: (v) => calls.push(["w", v]), eraseDonors: () => calls.push(["go"]) }, sector: "ngo" });
  test("offered only to approvers and only while hiding is on", () => {
    assert.ok(byId(page(ov(true), "OWNER"), "pf-erase-go"));
    assert.equal(byId(page(ov(false), "OWNER"), "pf-erase-go"), undefined);
    assert.equal(byId(page(ov(true), "ACCOUNTANT"), "pf-erase-go"), undefined);
  });
  test("says plainly it cannot be undone and what it does not reach", () => {
    assert.match(text(byId(page(ov(true), "OWNER"), "pf-erase")), /cannot be undone.*Submitted reports keep/s);
  });
  test("typing and pressing send the word and the action", () => {
    const calls = [], v = page(ov(true), "OWNER", calls);
    byId(v, "pf-erase-word").props.onInput({ target: { value: "ERASE" } }); byId(v, "pf-erase-go").props.onClick();
    assert.deepEqual(calls, [["w", "ERASE"], ["go"]]);
  });
});
