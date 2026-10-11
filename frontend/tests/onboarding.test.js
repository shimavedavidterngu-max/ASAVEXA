import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { Onboarding, ProgressBar } from "../src/components/Onboarding.js";
import { Setup } from "../src/pages/Setup.js";
import {
  CATEGORIES, STEPS, progress, cleanName, validateCreate, validateSettings, mergeProfile, currencyForCountry, fiscalYear, validatePeriod,
  suggestedWorkspaces, resumeStep, settingsComplete, joinDetails, canSetUp, canOpenPeriod,
} from "../src/lib/onboarding.js";
import { setupSteps, NAV_GROUPS, searchPages } from "../src/lib/home.js";
import { Login } from "../src/pages/Login.js";

const appSource = readFileSync(new URL("../src/app.js", import.meta.url), "utf8");
const cssSource = readFileSync(new URL("../src/styles/onboarding.css", import.meta.url), "utf8");
const htmlSource = readFileSync(new URL("../index.html", import.meta.url), "utf8");

const walk = (v, fn) => { if (!v || typeof v !== "object") return; fn(v); (v.children || []).forEach((c) => walk(c, fn)); };
const all = (v, pred) => { const out = []; walk(v, (n) => { if (pred(n)) out.push(n); }); return out; };
const byId = (v, id) => all(v, (n) => n.props && n.props.id === id)[0];
const text = (v) => { if (v == null || v === false) return ""; if (typeof v !== "object") return String(v); return (v.children || []).map(text).join(""); };

const COUNTRIES = [{ code: "NG", name: "Nigeria", currency: "NGN" }, { code: "GB", name: "United Kingdom", currency: "GBP" }, { code: "KE", name: "Kenya", currency: "KES" }];
const WS = [
  { id: "analysis", name: "Financial Analysis", path: "/analysis", permission: "reporting:read", status: "VERIFIED IN TEST ENVIRONMENT" },
  { id: "tax", name: "Tax Compliance", path: "/tax", permission: "reporting:read", status: "VERIFIED IN TEST ENVIRONMENT" },
  { id: "forensic", name: "Forensic Investigation", path: "/forensic", permission: "forensic:read", status: "VERIFIED IN TEST ENVIRONMENT" },
  { id: "grc", name: "GRC", path: "/grc", permission: "audit:read", status: "VERIFIED IN TEST ENVIRONMENT" },
  { id: "public_finance", name: "Public Finance", path: "/pubfin", permission: "reporting:read" },
  { id: "bizdev", name: "Business Development", path: "/bizdev", permission: "reporting:read" },
  { id: "cyber", name: "Cybersecurity", path: "/cyber", permission: "audit:read" },
  { id: "health", name: "Health Centre", path: "/health", permission: "health:read" },
];

describe("the journey's steps and progress", () => {
  test("five steps in the order of the spec's journey", () => assert.deepEqual(STEPS.map((s) => s.id), ["account", "organisation", "settings", "period", "workspaces"]));
  test("steps before the current one are done, the current one is marked, the rest are to do", () => {
    assert.deepEqual(progress("settings").map((s) => s.state), ["done", "done", "current", "todo", "todo"]);
    assert.deepEqual(progress("account").map((s) => s.state), ["current", "todo", "todo", "todo", "todo"]);
    assert.ok(progress("nonsense").every((s) => s.state === "todo"));
  });
  test("the progress bar tells assistive technology which step is current and which are done", () => {
    const v = ProgressBar({ current: "period" });
    assert.equal(all(v, (n) => n.props && n.props["aria-current"] === "step").length, 1);
    assert.match(text(v), /\(done\)/); assert.match(text(v), /\(current step\)/); assert.match(text(v), /\(to do\)/);
  });
});

describe("the organisation categories", () => {
  test("are exactly the eight in the spec", () => {
    assert.equal(CATEGORIES.length, 8);
    for (const c of ["Accounting or audit firm", "Business or SME", "NGO or nonprofit", "Church or faith-based organisation", "Government or public institution", "University or educational institution", "Health centre or healthcare facility", "Individual professional"]) assert.ok(CATEGORIES.includes(c), c);
  });
});

describe("creating an organisation", () => {
  test("cleans the name: trims, collapses spaces, removes control characters", () => {
    assert.equal(cleanName("  Meridian   Textiles \n Ltd "), "Meridian Textiles Ltd");
    assert.equal(cleanName("A\u0000B"), "A B");
    assert.equal(cleanName(null), "");
  });
  test("needs a real name and a category, and says which is missing", () => {
    assert.deepEqual(Object.keys(validateCreate({ name: "", category: "" }).errors).sort(), ["category", "name"]);
    assert.ok(validateCreate({ name: "A", category: CATEGORIES[0] }).errors.name);
    assert.ok(validateCreate({ name: "x".repeat(121), category: CATEGORIES[0] }).errors.name);
    assert.ok(validateCreate({ name: "Acme", category: "Something else" }).errors.category, "only the eight categories");
    const ok = validateCreate({ name: "  Acme   Ltd ", category: CATEGORIES[1] });
    assert.equal(ok.ok, true); assert.equal(ok.name, "Acme Ltd");
  });
  test("markup in a name is kept as text, never interpreted", () => {
    const v = Onboarding({ user: { email: "a@b.c" }, orgs: [{ id: "o1", name: "<img src=x onerror=alert(1)>" }], mode: "auto", form: {}, errors: {}, onMode() {}, onSelect() {}, onSignOut() {} });
    assert.match(text(all(v, (n) => n.props && n.props["data-org"])[0]), /<img src=x/);
    assert.ok(!all(v, (n) => n.tag === "img").length);
  });
});

describe("organisation settings", () => {
  const good = { legal_name: "Meridian Ltd", organisation_type: CATEGORIES[1], country: "NG", base_currency: "ngn", fiscal_year_start_month: "4" };
  test("accepts a complete form and normalises the currency", () => assert.equal(validateSettings(good).ok, true));
  test("reports each problem on its own field", () => {
    const e = validateSettings({ legal_name: "", organisation_type: "", country: "", base_currency: "US", fiscal_year_start_month: "13" }).errors;
    assert.deepEqual(Object.keys(e).sort(), ["base_currency", "country", "fiscal_year_start_month", "legal_name", "organisation_type"]);
  });
  test("a currency must be three letters; a month must be 1 to 12", () => {
    assert.ok(validateSettings({ ...good, base_currency: "US1" }).errors.base_currency);
    assert.ok(validateSettings({ ...good, fiscal_year_start_month: "0" }).errors.fiscal_year_start_month);
    assert.ok(validateSettings({ ...good, fiscal_year_start_month: "2.5" }).errors.fiscal_year_start_month);
    assert.equal(validateSettings({ ...good, fiscal_year_start_month: "12" }).ok, true);
  });
  test("the currency comes from the server's country list and is never guessed", () => {
    assert.equal(currencyForCountry(COUNTRIES, "KE"), "KES");
    assert.equal(currencyForCountry(COUNTRIES, "ZZ"), "");
    assert.equal(currencyForCountry(null, "NG"), "");
  });
  test("saving keeps every field the organisation already had, because the server replaces the whole profile", () => {
    const out = mergeProfile({ org_id: "o1", updated_at: "x", updated_by: "u", registration_number: "RC123", tax_id: "T-9", website: "", address: null, country: "Old" }, good);
    assert.equal(out.registration_number, "RC123"); assert.equal(out.tax_id, "T-9");
    assert.equal(out.country, "NG"); assert.equal(out.base_currency, "NGN"); assert.equal(out.fiscal_year_start_month, 4);
    for (const k of ["org_id", "updated_at", "updated_by", "website", "address"]) assert.ok(!(k in out), k);
  });
});

describe("the first accounting period", () => {
  test("a financial year starting in January is the calendar year", () => {
    assert.deepEqual(fiscalYear(1, new Date("2026-10-11T00:00:00Z")), { start: "2026-01-01", end: "2026-12-31", name: "FY2026" });
  });
  test("a year starting in April runs to the next March, and before April it is last year's", () => {
    assert.deepEqual(fiscalYear(4, new Date("2026-10-11T00:00:00Z")), { start: "2026-04-01", end: "2027-03-31", name: "FY2026/2027" });
    assert.deepEqual(fiscalYear(4, new Date("2026-02-01T00:00:00Z")), { start: "2025-04-01", end: "2026-03-31", name: "FY2025/2026" });
  });
  test("every month gives exactly twelve months, including a leap year", () => {
    for (let m = 1; m <= 12; m++) {
      const f = fiscalYear(m, new Date("2027-06-15T00:00:00Z"));
      const days = (Date.parse(f.end) - Date.parse(f.start)) / 86400000 + 1;
      assert.ok(days === 365 || days === 366, `${m}: ${days}`);
      assert.ok(f.start.endsWith("-01"));
    }
    assert.equal(fiscalYear(3, new Date("2027-06-15T00:00:00Z")).end, "2028-02-29");
  });
  test("a missing or bad month falls back to January", () => assert.equal(fiscalYear("", new Date("2026-05-05T00:00:00Z")).start, "2026-01-01"));
  test("validation: a name, two real dates, and the end after the start", () => {
    assert.equal(validatePeriod({ name: "FY2026", start: "2026-01-01", end: "2026-12-31" }).ok, true);
    assert.deepEqual(Object.keys(validatePeriod({ name: "", start: "", end: "" }).errors).sort(), ["end", "name", "start"]);
    assert.ok(validatePeriod({ name: "P", start: "2026-05-01", end: "2026-05-01" }).errors.end);
    assert.ok(validatePeriod({ name: "P", start: "2026-05-01", end: "2026-04-01" }).errors.end);
    assert.ok(validatePeriod({ name: "P", start: "2026-13-45", end: "2026-12-31" }).errors.start);
  });
});

describe("workspace suggestions", () => {
  test("each kind of organisation gets suggestions that exist in the catalogue", () => {
    for (const c of CATEGORIES) assert.ok(suggestedWorkspaces(c, WS, "ADMINISTRATOR").length >= 3, c);
  });
  test("a health centre is pointed at Health Centre Administration; a firm at forensic and tax", () => {
    assert.ok(suggestedWorkspaces("Health centre or healthcare facility", WS, "ADMINISTRATOR").some((w) => w.id === "health"));
    const firm = suggestedWorkspaces("Accounting or audit firm", WS, "ADMINISTRATOR").map((w) => w.id);
    assert.ok(firm.includes("forensic") && firm.includes("tax"));
  });
  test("a suggestion never opens a workspace the role cannot open", () => {
    const f = suggestedWorkspaces("Accounting or audit firm", WS, "FINANCE_OFFICER").find((w) => w.id === "forensic");
    assert.equal(f.canOpen, false);
    assert.equal(suggestedWorkspaces("Accounting or audit firm", WS, "ADMINISTRATOR").find((w) => w.id === "tax").canOpen, true);
  });
  test("an unknown category or no catalogue gives no suggestions rather than a guess", () => {
    assert.deepEqual(suggestedWorkspaces("", WS, "ADMINISTRATOR"), []);
    assert.deepEqual(suggestedWorkspaces(CATEGORIES[0], null, "ADMINISTRATOR"), []);
  });
});

describe("resuming where the person left off", () => {
  const full = { country: "Nigeria", base_currency: "NGN", fiscal_year_start_month: 1, organisation_type: CATEGORIES[1] };
  test("details missing, then period missing, then workspaces, worked out from what the server holds", () => {
    assert.equal(resumeStep({ profile: null, periods: [] }), "settings");
    assert.equal(resumeStep({ profile: { organisation_type: CATEGORIES[0] }, periods: [] }), "settings");
    assert.equal(resumeStep({ profile: full, periods: [] }), "period");
    assert.equal(resumeStep({ profile: full, periods: null }), "period");
    assert.equal(resumeStep({ profile: full, periods: [{ id: "p" }] }), "workspaces");
  });
  test("settingsComplete is true only for a full profile", () => {
    assert.equal(settingsComplete(full), true);
    assert.equal(settingsComplete({ country: "NG" }), false);
    assert.equal(settingsComplete(null), false);
  });
});

describe("before an organisation is open", () => {
  const base = (over = {}) => {
    const calls = [];
    const rec = (n) => (...a) => calls.push([n, ...a]);
    return { calls, p: { user: { id: "u-123", email: "new@x.test" }, orgs: [], mode: "auto", form: { name: "", category: "" }, errors: {}, pending: false, error: null, copied: false, checking: false, checkMessage: null,
      onMode: rec("mode"), onField: rec("field"), onCreate: rec("create"), onSelect: rec("select"), onCopy: rec("copy"), onRecheck: rec("recheck"), onRetry: rec("retry"), onSecurity: rec("sec"), onSignOut: rec("out"), ...over } };
  };
  test("a new person is offered exactly two choices, and each opens its own screen", () => {
    const { p, calls } = base();
    const v = Onboarding(p);
    byId(v, "ob-opt-create").props.onClick(); byId(v, "ob-opt-join").props.onClick();
    assert.deepEqual(calls, [["mode", "create"], ["mode", "join"]]);
    assert.equal(all(v, (n) => n.tag === "h2").length, 1);
  });
  test("loading, a failed load with a retry, and the progress bar are all shown", () => {
    assert.match(text(Onboarding(base({ orgs: null }).p)), /Looking for your organisations/);
    const { p, calls } = base({ orgs: false });
    const v = Onboarding(p); byId(v, "ob-retry").props.onClick();
    assert.deepEqual(calls, [["retry"]]);
    assert.ok(byId(v, "ob-progress"));
  });
  test("the create form is labelled, shows each error beside its field, and submits through one handler", () => {
    const { p, calls } = base({ mode: "create", errors: { name: "Enter the organisation's name (at least 2 characters).", category: "Choose the kind of organisation this is." } });
    const v = Onboarding(p);
    assert.equal(all(v, (n) => n.tag === "label").length, 2);
    assert.equal(byId(v, "ob-name").props["aria-invalid"], "true");
    assert.equal(byId(v, "ob-name").props["aria-describedby"], "ob-name-err");
    assert.ok(byId(v, "ob-name-err") && byId(v, "ob-category-err"));
    assert.equal(all(byId(v, "ob-category"), (n) => n.tag === "option").length, 9);
    const form = byId(v, "ob-create");
    form.props.onSubmit({ preventDefault() { calls.push(["prevented"]); } });
    assert.deepEqual(calls, [["prevented"], ["create"]]);
  });
  test("while creating, the button is disabled and says so, so a double click cannot create two", () => {
    const b = byId(Onboarding(base({ mode: "create", pending: true }).p), "ob-create-go");
    assert.equal(b.props.disabled, true); assert.match(text(b), /Creating/);
  });
  test("a server error is shown, and a person can go back", () => {
    const { p, calls } = base({ mode: "create", error: "boom" });
    const v = Onboarding(p);
    assert.match(text(byId(v, "ob-error")), /boom/);
    byId(v, "ob-back").props.onClick();
    assert.deepEqual(calls, [["mode", "auto"]]);
  });
  test("joining is honest: no invitation is promised, the person gets their id and email, and can check again", () => {
    const { p, calls } = base({ mode: "join" });
    const v = Onboarding(p);
    assert.match(text(byId(v, "ob-join")), /does not send invitations yet/);
    assert.equal(text(byId(v, "ob-join-id")), "u-123");
    assert.equal(text(byId(v, "ob-join-email")), "new@x.test");
    byId(v, "ob-copy").props.onClick(); byId(v, "ob-recheck").props.onClick();
    assert.deepEqual(calls.map((c) => c[0]), ["copy", "recheck"]);
    assert.match(text(Onboarding(base({ mode: "join", checkMessage: "You are not a member of any organisation yet." }).p)), /not a member/);
  });
  test("several organisations are listed by name and selecting one calls the handler; Create and Join remain available", () => {
    const { p, calls } = base({ orgs: [{ id: "o1", name: "Alpha" }, { id: "o2", name: "Beta" }] });
    const v = Onboarding(p);
    const items = all(v, (n) => n.props && n.props["data-org"]);
    assert.deepEqual(items.map((i) => text(i).slice(0, 5)), ["Alpha", "Beta"].map((s, i) => text(items[i]).slice(0, 5)));
    items[1].props.onClick();
    byId(v, "ob-new").props.onClick(); byId(v, "ob-join-more").props.onClick();
    assert.deepEqual(calls, [["select", "o2"], ["mode", "create"], ["mode", "join"]]);
  });
  test("sign out is always available", () => {
    const { p, calls } = base(); byId(Onboarding(p), "ob-signout").props.onClick(); assert.deepEqual(calls, [["out"]]);
  });
  test("joinDetails never invents an id", () => { assert.deepEqual(joinDetails(null), { id: "", email: "" }); assert.equal(joinDetails({ id: 5, email: "e" }).id, "5"); });
});

describe("the set-up page", () => {
  const newSt = (over = {}) => ({ loading: false, loadError: null, profile: {}, periods: [], countries: COUNTRIES, workspaces: WS, step: "settings",
    form: { legal_name: "Acme", organisation_type: CATEGORIES[1], country: "", base_currency: "", fiscal_year_start_month: "" }, period: { name: "FY2026", start: "2026-01-01", end: "2026-12-31" }, errors: {}, saving: false, error: null, notice: null, ...over });
  const mk = (st, role = "OWNER") => {
    const calls = [];
    const rec = (n) => (...a) => calls.push([n, ...a]);
    return { calls, v: Setup({ st, role, onField: rec("field"), onCountry: rec("country"), onSaveSettings: rec("saveSettings"), onPeriodField: rec("pfield"), onSavePeriod: rec("savePeriod"), onStep: rec("step"), onGo: rec("go"), onFinish: rec("finish"), onRetry: rec("retry") }) };
  };
  test("a role that cannot manage settings gets an explanation and a way back, not a broken form", () => {
    const { v, calls } = mk(newSt(), "READ_ONLY");
    assert.ok(byId(v, "su-denied")); assert.ok(!byId(v, "su-settings"));
    byId(v, "su-home").props.onClick(); assert.deepEqual(calls, [["go", "/"]]);
    assert.equal(canSetUp("READ_ONLY"), false); assert.equal(canSetUp("OWNER"), true);
  });
  test("loading and load-error states are shown, the error with a retry", () => {
    assert.match(text(mk(newSt({ loading: true })).v), /Loading/);
    const { v, calls } = mk(newSt({ loadError: "The set-up details could not be loaded." }));
    assert.match(text(v), /could not be loaded/);
  });
  test("details step: country list from the server, labelled fields, errors beside fields, one submit handler", () => {
    const { v, calls } = mk(newSt({ errors: { country: "Choose the country where the organisation operates.", base_currency: "Enter a 3-letter currency code such as USD, EUR or NGN." } }));
    assert.equal(all(byId(v, "su-country"), (n) => n.tag === "option").length, 4);
    assert.equal(byId(v, "su-country").props["aria-invalid"], "true");
    assert.ok(byId(v, "su-country-err") && byId(v, "su-currency-err"));
    assert.equal(all(byId(v, "su-month"), (n) => n.tag === "option").length, 13);
    byId(v, "su-settings").props.onSubmit({ preventDefault() {} });
    byId(v, "su-country").props.onChange({ target: { value: "KE" } });
    byId(v, "su-currency").props.onInput({ target: { value: "kes" } });
    assert.deepEqual(calls, [["saveSettings"], ["country", "KE"], ["field", "base_currency", "KES", true]]);
  });
  test("if the country list could not load, the person can type it and is told why", () => {
    const v = mk(newSt({ countries: null })).v;
    assert.equal(byId(v, "su-country").tag, "input"); assert.match(text(byId(v, "su-country-note")), /could not be loaded/);
  });
  test("every step can be skipped for now, and the page says each step is saved as it goes", () => {
    const a = mk(newSt()); byId(a.v, "su-skip-settings").props.onClick();
    const b = mk(newSt({ step: "period" })); byId(b.v, "su-skip-period").props.onClick(); byId(b.v, "su-back-period").props.onClick();
    assert.deepEqual(a.calls, [["step", "period"]]); assert.deepEqual(b.calls, [["step", "workspaces"], ["step", "settings"]]);
    assert.match(text(a.v), /saves as you go/);
  });
  test("saving disables the buttons so a double click cannot submit twice", () => {
    const v = mk(newSt({ saving: true })).v;
    assert.equal(byId(v, "su-save-settings").props.disabled, true); assert.match(text(byId(v, "su-save-settings")), /Saving/);
  });
  test("period step: a form with the dates filled in, or a note that periods already exist, or a role explanation", () => {
    const form = mk(newSt({ step: "period" })).v;
    assert.equal(byId(form, "su-start").props.value, "2026-01-01");
    const have = mk(newSt({ step: "period", periods: [{ name: "FY2025" }, { name: "FY2026" }] })).v;
    assert.match(text(byId(have, "su-period-msg")), /already has 2 accounting periods: FY2025, FY2026/);
    assert.ok(!byId(have, "su-period"));
    const denied = mk(newSt({ step: "period" }), "REVIEWER").v;
    assert.ok(byId(denied, "su-period-denied") || byId(denied, "su-denied"));
    assert.equal(canOpenPeriod("OWNER"), true);
  });
  test("period errors appear beside the fields; Back and Skip work", () => {
    const v = mk(newSt({ step: "period", errors: { end: "The last day must be after the first day." } })).v;
    assert.ok(byId(v, "su-end-err")); assert.equal(byId(v, "su-end").props["aria-invalid"], "true");
  });
  test("workspaces step: suggestions with their real status, Open only where the role allows, and a plain statement that roles come from the server", () => {
    const { v, calls } = mk(newSt({ step: "workspaces", profile: { organisation_type: "Accounting or audit firm" } }), "ADMINISTRATOR");
    const cards = all(byId(v, "su-ws-grid"), (n) => n.props && n.props["data-ws"]);
    assert.ok(cards.length >= 3);
    assert.match(text(byId(v, "su-ws-note")), /Nothing is switched on or off/);
    assert.match(text(byId(v, "su-role")), /Roles are set only by the server/);
    assert.match(text(byId(v, "su-role")), /Administrator/);
    assert.ok(byId(v, "su-open-tax"));
    byId(v, "su-open-tax").props.onClick(); byId(v, "su-finish").props.onClick(); byId(v, "su-standards").props.onClick();
    assert.deepEqual(calls, [["go", "/tax"], ["finish"], ["go", "/standards"]]);
  });
  test("with no category or no catalogue the page says so instead of inventing suggestions", () => {
    assert.ok(byId(mk(newSt({ step: "workspaces", form: { ...newSt().form, organisation_type: "" } })).v, "su-ws-nocat"));
    assert.ok(byId(mk(newSt({ step: "workspaces", workspaces: null })).v, "su-ws-none"));
  });
  test("every button has a handler", () => {
    for (const step of ["settings", "period", "workspaces"]) for (const b of all(mk(newSt({ step })).v, (n) => n.tag === "button")) assert.equal(typeof b.props.onClick === "function" || b.props.type === "submit", true, `${step}: ${b.props.id}`);
  });
});

describe("setup checklist and navigation", () => {
  test("the home checklist gains a details step only when that fact is known, and period points to set-up", () => {
    const withIt = setupSteps({ profile: false, accounts: true, periods: false, evidence: true, team: true }, "ADMINISTRATOR");
    assert.deepEqual(withIt.todo.map((s) => s.id), ["profile", "period"]);
    assert.equal(withIt.steps.find((s) => s.id === "period").path, "/setup");
    assert.equal(withIt.steps.find((s) => s.id === "profile").path, "/setup");
    const without = setupSteps({ accounts: true, periods: false, evidence: true, team: true }, "ADMINISTRATOR");
    assert.ok(!without.steps.some((s) => s.id === "profile"));
    assert.equal(without.steps.find((s) => s.id === "period").path, "/accounting");
  });
  test("an unknown details fact is shown as could-not-check, never as missing", () => {
    const s = setupSteps({ profile: null, accounts: true, periods: true, evidence: true, team: true }, "ADMINISTRATOR");
    assert.deepEqual(s.unknown.map((x) => x.id), ["profile"]); assert.equal(s.todo.length, 0);
  });
  test("a role without the settings permission is not told to complete the details", () => {
    assert.ok(!setupSteps({ profile: false, accounts: true, periods: true, evidence: true, team: true }, "READ_ONLY").steps.some((s) => s.id === "profile"));
  });
  test("Organisation setup is in the menu groups and findable by search", () => {
    assert.ok(NAV_GROUPS.some((g) => g.paths.includes("/setup")));
    const vis = [{ item: { path: "/setup", label: "Organisation setup" }, active: false }];
    assert.equal(searchPages("currency", vis)[0].path, "/setup");
  });
});

describe("source contracts in app.js", () => {
  test("/setup is a route, a menu entry that needs the settings permission, and renders the set-up page", () => {
    assert.match(appSource, /\{ path: "\/setup", name: "setup" \}/);
    assert.match(appSource, /\{ path: "\/setup", label: "Organisation setup", permission: PERMISSIONS\.ORG_MANAGE_SETTINGS \}/);
    assert.match(appSource, /name === "setup"\) return renderSetupPage/);
  });
  test("with no organisation open the new onboarding screen replaces the old window.prompt", () => {
    assert.match(appSource, /renderOnboarding\(authState\)/);
    assert.ok(!/window\.prompt\("Organisation name/.test(appSource));
  });
  test("creating an organisation validates first, ignores a second click, opens it, then goes to set-up", () => {
    const fn = appSource.slice(appSource.indexOf("async function handleCreateOrganisation"), appSource.indexOf("function newSetup"));
    assert.match(fn, /if \(o\.pending\) return;/);
    assert.ok(fn.indexOf("validateCreate") < fn.indexOf("api.createOrganisation"));
    assert.match(fn, /api\.selectOrganisation\(created\.id\)/);
    assert.match(fn, /router\.navigate\("\/setup"\)/);
    assert.match(fn, /was created, but it could not be opened/, "a half-finished create is explained, not hidden");
  });
  test("saving the details sends the merged profile, so nothing already saved is lost", () => {
    assert.match(appSource, /api\.updateOrganisationProfile\(mergeProfile\(st\.profile,/);
  });
  test("the set-up state is per organisation and role, and nothing is sent when the role cannot set up", () => {
    assert.match(appSource, /uiState\.setup\.loadedFor !== key/);
    assert.match(appSource, /if \(!canSetUp\(authState\.role\)\) return;/);
  });
  test("no code path sets a role or permission from the form", () => {
    const j = appSource.slice(appSource.indexOf("// Sign-up journey."), appSource.indexOf("/** Load the organisation list the first time"));
    assert.ok(!/addMember|changeMemberRole|role:\s*o\.form|role:\s*st\.form/.test(j));
    assert.match(j, /authStore\.setOrganisation\(created\.id, role\)/, "the role comes back from the server");
  });
  test("the top bar loads the organisation list on every page, so the name (not the id) shows after a reload", () => {
    assert.match(appSource, /if \(uiState\.orgList === null && !\(uiState\.home\.data && uiState\.home\.data\.orgs\)\) ensureOrgs\(\);/);
    assert.match(appSource, /if \(uiState\.orgList \|\| uiState\.orgLoading\) return;/, "and never starts a second request while one is running");
  });
  test("onboarding.css is linked, and the sign-in page is honest about recovery", () => {
    assert.match(htmlSource, /styles\/onboarding\.css/);
    assert.match(cssSource, /@media \(max-width: 620px\)/);
    const login = text(Login({ mode: "login", onSubmit() {}, onSwitchMode() {} }));
    assert.match(login, /Password recovery and email verification are not available yet/);
    assert.ok(!/not available yet/.test(text(Login({ mode: "register", onSubmit() {}, onSwitchMode() {} }))));
  });
});
