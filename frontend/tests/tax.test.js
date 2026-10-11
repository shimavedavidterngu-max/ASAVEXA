import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { Tax } from "../src/pages/Tax.js";
import * as X from "../src/lib/tax.js";
import { ApiClient } from "../src/api/client.js";

const text = (v) => JSON.stringify(v);
function find(v, pred, out = []) { if (!v || typeof v !== "object") return out; if (pred(v)) out.push(v); for (const c of v.children || []) find(c, pred, out); return out; }
const byId = (v, id) => find(v, (n) => n.props && n.props.id === id)[0];
const noop = new Proxy({}, { get: () => () => {} });
const OPTIONS = { tax_types: { VAT_GST: "VAT", OTHER: "Other" }, frequencies: ["MONTHLY", "QUARTERLY"], rounding: ["HALF_UP", "DOWN"], methods: { FLAT: "Flat", BRACKETS: "Bands" }, guidance: [] };
const base = (o = {}) => ({ tab: "countries", busy: false, error: null, notice: null, loaded: { countries: true, rules: true, calculator: true, calendar: true }, overview: { selected: 1, rules_in_force: 0, rules_waiting: 0, selected_without_rules: [{ code: "NG", name: "Nigeria" }] },
  countries: { total: 200, shown: 1, with_rules: 0, regions: ["Africa"], note: "A country appearing in this list does not mean ASAVEXA knows its tax rules.", countries: [{ code: "NG", name: "Nigeria", currency: "NGN", region: "Africa", selected: true, registration: "", rules_in_force: 0, rules_waiting: 0, rules_draft: 0 }] },
  q: "", region: "", regDraft: {}, countryList: [{ code: "NG", name: "Nigeria" }], options: OPTIONS, rules: [], ruleFilter: "", rule: null, form: null, decisionNote: "", liveRules: [], periods: [],
  calcForm: { rule_id: "", amount: "", date: "2026-03-01", inclusive: false, period_id: "", kind: "revenue" }, calc: null, ledgerNote: null, history: [], cal: { start: "2026-01-01", end: "2026-12-31", data: null }, refDraft: {}, ...o });
const page = (tx, role = "ACCOUNTANT", userId = "u1") => Tax({ tx, role, userId, loading: false, onRetry() {}, actions: noop });
const RULE = { id: "r1", country: "NG", country_name: "Nigeria", currency: "NGN", tax_type: "VAT_GST", tax_type_text: "VAT", name: "Standard", method: "FLAT", rate: "7.5", rounding: "HALF_UP", effective_from: "2026-01-01", effective_to: null, authority: "Auth", source_title: "Act s5", source_url: "https://e.org/a", status: "SUBMITTED", version: 1, created_by: "u1", submitted_by: "u1", history: [], filing: null, notes: "" };

describe("helpers", () => {
  const f = (o = {}) => ({ ...X.emptyRule("NG"), name: "Standard", rate: "7.5", effective_from: "2026-01-01", authority: "Auth", source_title: "Act section 5", source_url: "https://e.org/a", ...o });
  test("a complete flat rule passes and builds the request", () => {
    assert.equal(X.ruleProblem(f()), null);
    const b = X.ruleBody(f({ filing_on: true, due_days: "30" }));
    assert.equal(b.rate, "7.5"); assert.equal(b.filing.frequency, "QUARTERLY"); assert.equal(b.filing.period_anchor, "2026-01-01"); assert.equal(b.effective_to, null);
  });
  test("every missing piece of evidence is refused", () => {
    assert.match(X.ruleProblem(f({ country: "" })), /country/i);
    assert.match(X.ruleProblem(f({ name: "x" })), /name/);
    assert.match(X.ruleProblem(f({ effective_from: "" })), /starts/);
    assert.match(X.ruleProblem(f({ effective_to: "2025-01-01" })), /before/);
    assert.match(X.ruleProblem(f({ authority: "" })), /authority/);
    assert.match(X.ruleProblem(f({ source_title: "abc" })), /law/);
    assert.match(X.ruleProblem(f({ source_url: "javascript:alert(1)" })), /link/);
    assert.match(X.ruleProblem(f({ source_url: "" })), /link/);
    assert.match(X.ruleProblem(f({ rate: "101" })), /0 to 100/);
    assert.match(X.ruleProblem(f({ rate: "" })), /0 to 100/);
    assert.match(X.ruleProblem(f({ filing_on: true, due_days: "x" })), /whole number/);
  });
  test("band checks: start at 0, contiguous, only last open", () => {
    const bands = (b) => f({ method: "BRACKETS", brackets: b });
    assert.equal(X.ruleProblem(bands([{ from: "0", up_to: "100", rate: "0" }, { from: "100", up_to: "", rate: "10" }])), null);
    assert.match(X.ruleProblem(bands([{ from: "5", up_to: "100", rate: "0" }])), /start at 0/);
    assert.match(X.ruleProblem(bands([{ from: "0", up_to: "100", rate: "0" }, { from: "200", up_to: "", rate: "1" }])), /start at 100/);
    assert.match(X.ruleProblem(bands([{ from: "0", up_to: "", rate: "0" }, { from: "10", up_to: "", rate: "1" }])), /last band/);
    assert.match(X.ruleProblem(bands([{ from: "0", up_to: "0", rate: "0" }])), /above/);
    assert.deepEqual(X.ruleBody(bands([{ from: "0", up_to: "", rate: "5" }])).brackets, [{ from: "0", up_to: null, rate: "5" }]);
  });
  test("calculator input checks", () => {
    assert.match(X.calcProblem({ rule_id: "", amount: "1", date: "2026-01-01" }), /rule/);
    assert.match(X.calcProblem({ rule_id: "r", amount: "-1", date: "2026-01-01" }), /amount/);
    assert.match(X.calcProblem({ rule_id: "r", amount: "1", date: "soon" }), /date/);
    assert.equal(X.calcProblem({ rule_id: "r", amount: "10.5", date: "2026-01-01" }), null);
  });
  test("separation of duties on rules", () => {
    assert.equal(X.ruleActions(RULE, "OWNER", "u1").decide, false);
    assert.equal(X.ruleActions(RULE, "OWNER", "u1").ownSubmission, true);
    assert.equal(X.ruleActions(RULE, "OWNER", "u2").decide, true);
    assert.equal(X.ruleActions({ ...RULE, created_by: "u1", submitted_by: "u3" }, "OWNER", "u1").decide, false);
    assert.equal(X.ruleActions(RULE, "ACCOUNTANT", "u2").decide, false);
    assert.equal(X.ruleActions({ ...RULE, status: "APPROVED" }, "OWNER", "u2").replace, true);
    assert.equal(X.ruleActions({ ...RULE, status: "APPROVED" }, "OWNER", "u2").edit, false);
    assert.equal(X.ruleActions({ ...RULE, status: "DRAFT" }, "READ_ONLY", "u2").submit, false);
  });
  test("edit form round-trips", () => {
    const form = X.ruleForm({ ...RULE, method: "BRACKETS", brackets: [{ from: "0", up_to: null, rate: "5" }], filing: { frequency: "MONTHLY", due_days_after_period_end: 15, period_anchor: "2026-01-01", form: "R1" } });
    assert.equal(form.brackets[0].up_to, ""); assert.equal(form.filing_on, true); assert.equal(form.due_days, "15");
  });
});

describe("Tax page", () => {
  test("says plainly that a listed country does not mean rules exist", () => {
    const t = text(page(base()));
    assert.match(t, /does not mean ASAVEXA knows its tax rules/);
    assert.match(t, /Selected but no rule in force/);
    assert.match(t, /not tax advice/);
  });
  test("select buttons only for people who may prepare", () => {
    assert.ok(byId(page(base(), "ACCOUNTANT"), "sel-NG"));
    assert.equal(byId(page(base(), "READ_ONLY"), "sel-NG"), undefined);
    assert.ok(byId(page(base(), "READ_ONLY"), "rules-NG"));
  });
  test("empty rules list explains that nothing is assumed", () => {
    assert.match(text(page(base({ tab: "rules" }))), /Nothing is assumed/);
    assert.ok(byId(page(base({ tab: "rules" }), "ACCOUNTANT"), "rule-new"));
    assert.equal(byId(page(base({ tab: "rules" }), "READ_ONLY"), "rule-new"), undefined);
  });
  test("rule detail: reviewer other than the author sees Approve; the author does not", () => {
    const tx = base({ tab: "rules", rule: RULE });
    assert.equal(byId(page(tx, "OWNER", "u1"), "rule-approve"), undefined);
    assert.match(text(page(tx, "OWNER", "u1")), /does not let you approve your own work/);
    assert.ok(byId(page(tx, "OWNER", "u2"), "rule-approve"));
    assert.ok(byId(page(tx, "OWNER", "u2"), "rule-reject"));
    assert.match(text(page(tx, "OWNER", "u2")), /Open the source and check/);
  });
  test("rule detail links the official source safely", () => {
    const a = find(page(base({ tab: "rules", rule: RULE })), (n) => n.props && n.props.href === "https://e.org/a")[0];
    assert.equal(a.props.rel, "noopener noreferrer"); assert.equal(a.props.target, "_blank");
  });
  test("calculator warns when no rule is in force and shows working with the source after a result", () => {
    assert.match(text(page(base({ tab: "calculator" }))), /nothing to calculate with/);
    const calc = { rule: { country_name: "Nigeria", name: "Standard", source_title: "Act s5", authority: "Auth", source_url: "https://e.org/a", fingerprint: "abc" }, date: "2026-03-01", currency: "NGN", net: "100.00", tax: "7.50", gross: "107.50", steps: ["Tax = 100 x 7.5% = 7.50"], effective_rate_pct: null, bands: null };
    const v = page(base({ tab: "calculator", liveRules: [{ ...RULE, status: "APPROVED" }], calc }));
    assert.match(text(v), /ESTIMATE/); assert.match(text(v), /Tax = 100 x 7.5%/); assert.equal(text(byId(v, "calc-tax")).includes("7.50"), true);
  });
  test("calendar says an empty result is not the same as no deadlines", () => {
    const data = { items: [], overdue: 0, note: "...which is not the same as having no deadlines.", limitations: "Authorities can move dates." };
    assert.match(text(page(base({ tab: "calendar", cal: { start: "2026-01-01", end: "2026-12-31", data } }))), /not the same as having no deadlines/);
  });
  test("calendar: filed items show the reference, overdue shows a warning", () => {
    const item = { key: "r1:2026-03-31", rule_id: "r1", country_name: "Nigeria", rule: "Standard", form: "R1", period_start: "2026-01-01", period_end: "2026-03-31", due: "2026-04-30", state: "FILED", filed: { reference: "REF9", filed_by: "u1" } };
    const t = text(page(base({ tab: "calendar", cal: { start: "a", end: "b", data: { items: [item, { ...item, key: "k2", state: "OVERDUE", period_end: "2026-06-30" }], overdue: 1, note: "n", limitations: "l" } } })));
    assert.match(t, /Ref REF9/); assert.match(t, /past due/); assert.match(t, /I filed this/);
  });
  test("rule form shows band editor only for band rules and requires a source", () => {
    const f = { ...X.emptyRule("NG"), method: "BRACKETS" };
    const v = page(base({ tab: "rules", form: f }));
    assert.ok(byId(v, "rf-bands")); assert.equal(byId(v, "rf-rate"), undefined); assert.ok(byId(v, "rf-url"));
    assert.ok(byId(page(base({ tab: "rules", form: X.emptyRule("NG") })), "rf-rate"));
  });
  test("error shown", () => assert.match(text(page(base({ error: "Boom" }))), /Boom/));
});

describe("API client", () => {
  test("routes and verbs", async () => {
    const seen = [];
    const api = new ApiClient({ baseUrl: "/api", getToken: () => "t", fetchImpl: async (u, o) => { seen.push(o.method + " " + u); return { ok: true, status: 200, text: async () => "{}" }; } });
    await api.taxCountries("ken", "Africa"); await api.setTaxCountry("KE", { selected: true, registration: "" }); await api.discardTaxRule("a b"); await api.taxCalendar("2026-01-01", "2026-12-31"); await api.approveTaxRule("r1", "ok");
    assert.deepEqual(seen, ["GET /api/tax/countries?q=ken&region=Africa", "PUT /api/tax/countries/KE", "DELETE /api/tax/rules/a%20b", "GET /api/tax/calendar?start=2026-01-01&end=2026-12-31", "POST /api/tax/rules/r1/approve"]);
  });
});
