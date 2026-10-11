import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { Home } from "../src/pages/Home.js";
import { SideNav, TopBar, Breadcrumbs } from "../src/components/Shell.js";
import { ROLE_PERMISSIONS } from "../src/lib/permissions.js";
import {
  NAV_GROUPS, groupNav, activeGroupId, groupOpen, breadcrumbs, searchPages, roleLabel, displayName, orgName,
  workspaceCards, quickActions, setupSteps, mergeAttention, attentionSources, attentionSummary, loadHome, shortPurpose,
} from "../src/lib/home.js";

const appSource = readFileSync(new URL("../src/app.js", import.meta.url), "utf8");
const cssSource = readFileSync(new URL("../src/styles/home.css", import.meta.url), "utf8");
const htmlSource = readFileSync(new URL("../index.html", import.meta.url), "utf8");

const walk = (v, fn) => { if (!v || typeof v !== "object") return; fn(v); (v.children || []).forEach((c) => walk(c, fn)); };
const all = (v, pred) => { const out = []; walk(v, (n) => { if (pred(n)) out.push(n); }); return out; };
const byId = (v, id) => all(v, (n) => n.props && n.props.id === id)[0];
const text = (v) => { if (v == null || v === false) return ""; if (typeof v !== "object") return String(v); return (v.children || []).map(text).join(""); };

// The app's own menu, read from app.js so the test follows the real list.
const NAV = [...appSource.matchAll(/\{ path: "([^"]+)", label: "([^"]+)", permission: ([^,}]+)/g)].map((m) => ({ path: m[1], label: m[2] }));
const visibleAll = NAV.map((item) => ({ item, active: false }));
const withActive = (path) => { const best = NAV.filter((i) => path === i.path || (i.path !== "/" && path.startsWith(i.path + "/"))).sort((a, b) => b.path.length - a.path.length)[0]; return NAV.map((item) => ({ item, active: item === best })); };

const CATALOG = { workspaces: [
  { id: "analysis", name: "Financial Analysis", path: "/analysis", permission: "reporting:read", status: "VERIFIED IN TEST ENVIRONMENT", purpose: "Ratios, variance and forecasts. More text after." },
  { id: "forensic", name: "Forensic Investigation", path: "/forensic", permission: "forensic:read", status: "VERIFIED IN TEST ENVIRONMENT", purpose: "Confidential cases." },
  { id: "cyber", name: "Cybersecurity", path: "/cyber", permission: "audit:read", status: "VERIFIED IN TEST ENVIRONMENT", purpose: "Assets." },
] };

describe("the grouped menu", () => {
  test("the menu was read from app.js and is long enough to matter", () => assert.ok(NAV.length >= 25, `read ${NAV.length}`));
  test("every menu entry belongs to exactly one group, so nothing disappears or appears twice", () => {
    const listed = NAV_GROUPS.flatMap((g) => g.paths);
    assert.equal(new Set(listed).size, listed.length, "a path is in two groups");
    for (const i of NAV) assert.ok(listed.includes(i.path), `${i.path} is not in any group`);
    for (const p of listed) assert.ok(NAV.some((i) => i.path === p), `${p} is grouped but not in the menu`);
  });
  test("groupNav keeps every visible entry once and drops empty groups", () => {
    const groups = groupNav(visibleAll);
    assert.equal(groups.flatMap((g) => g.items).length, NAV.length);
    const few = groupNav(visibleAll.filter((v) => v.item.path === "/" || v.item.path === "/security"));
    assert.deepEqual(few.map((g) => g.id), ["home", "account"]);
  });
  test("an entry that no group lists is kept under More, never dropped", () => {
    const g = groupNav([...visibleAll, { item: { path: "/brand-new", label: "Brand new" }, active: false }]);
    assert.equal(g[g.length - 1].id, "more");
    assert.equal(g[g.length - 1].items[0].item.path, "/brand-new");
  });
  test("the group holding the current page is open; the person's own choice wins either way; Home never collapses", () => {
    const groups = groupNav(withActive("/tax"));
    const id = activeGroupId(groups);
    assert.equal(id, "workspaces");
    const ws = groups.find((g) => g.id === "workspaces"), books = groups.find((g) => g.id === "books"), home = groups.find((g) => g.id === "home");
    assert.equal(groupOpen(ws, {}, id), true);
    assert.equal(groupOpen(books, {}, id), false);
    assert.equal(groupOpen(books, { books: true }, id), true);
    assert.equal(groupOpen(ws, { workspaces: false }, id), false);
    assert.equal(groupOpen(home, { home: false }, id), true);
  });
  test("the side menu draws only the open groups' links, marks the current page, and every control has a handler", () => {
    const calls = [];
    const groups = groupNav(withActive("/tax"));
    const v = SideNav({ groups, navOpen: {}, activeId: "workspaces", mobileOpen: false, onToggleGroup: (...a) => calls.push(["toggle", ...a]), onGo: () => calls.push(["go"]) });
    const links = all(v, (n) => n.tag === "a");
    assert.ok(links.some((l) => l.props.href === "#/tax" && l.props["aria-current"] === "page"));
    assert.ok(!links.some((l) => l.props.href === "#/accounting"), "closed group links should not be drawn");
    const heads = all(v, (n) => n.tag === "button");
    assert.equal(heads.length, groups.length - 1);
    for (const b of heads) assert.equal(typeof b.props.onClick, "function");
    byId(v, "nav-group-books").props.onClick();
    assert.deepEqual(calls[0], ["toggle", "books", false]);
    byId(v, "nav-home").props.onClick();
    assert.deepEqual(calls[1], ["go"]);
    assert.equal(byId(v, "nav-group-workspaces").props["aria-expanded"], "true");
    assert.equal(byId(v, "nav-group-books").props["aria-expanded"], "false");
  });
  test("on a phone the menu opens as a drawer", () => {
    const g = groupNav(visibleAll);
    assert.ok(!SideNav({ groups: g, navOpen: {}, activeId: null, mobileOpen: false, onToggleGroup() {}, onGo() {} }).props.className.includes("is-open"));
    assert.ok(SideNav({ groups: g, navOpen: {}, activeId: null, mobileOpen: true, onToggleGroup() {}, onGo() {} }).props.className.includes("is-open"));
  });
});

describe("breadcrumbs", () => {
  test("home is just Home, a page shows its group, a detail page adds one more", () => {
    assert.deepEqual(breadcrumbs("/", visibleAll), [{ label: "Home", path: null }]);
    assert.deepEqual(breadcrumbs("/tax", visibleAll).map((c) => c.label), ["Home", "Professional workspaces", "Tax Compliance"]);
    const d = breadcrumbs("/accounting/journals/new", visibleAll);
    assert.deepEqual(d.map((c) => c.label), ["Home", "Books and evidence", "Accounting", "Detail"]);
    const e = breadcrumbs("/evidence/3f9a8c0e-1b2d-4c5e-9f00-aaaaaaaaaaaa", visibleAll);
    assert.equal(e[e.length - 1].label, "Detail");
  });
  test("only the last crumb is not a link; an unknown or not-permitted page says so rather than guessing", () => {
    const c = breadcrumbs("/tax", visibleAll);
    assert.equal(c[c.length - 1].path, null);
    assert.equal(c[0].path, "/");
    assert.equal(breadcrumbs("/nowhere", visibleAll).pop().label, "Page not found");
    assert.equal(breadcrumbs("/tax", visibleAll.filter((v) => v.item.path !== "/tax")).pop().label, "Page not found");
  });
  test("the crumbs component marks the current page", () => {
    const v = Breadcrumbs({ crumbs: breadcrumbs("/tax", visibleAll) });
    assert.equal(all(v, (n) => n.props && n.props["aria-current"] === "page").length, 1);
    assert.equal(all(v, (n) => n.tag === "a").length, 1);
  });
});

describe("search", () => {
  test("finds pages by name and by what people call them, best match first", () => {
    assert.equal(searchPages("tax", visibleAll)[0].path, "/tax");
    assert.equal(searchPages("evid", visibleAll)[0].path, "/evidence");
    assert.ok(searchPages("budget", visibleAll).some((r) => r.path === "/analysis" || r.path === "/pubfin"));
    assert.ok(searchPages("members", visibleAll).some((r) => r.path === "/admin"));
    assert.equal(searchPages("tax compliance", visibleAll)[0].path, "/tax");
  });
  test("returns nothing for an empty or unmatched query, and never more than the limit", () => {
    assert.deepEqual(searchPages("", visibleAll), []);
    assert.deepEqual(searchPages("   ", visibleAll), []);
    assert.deepEqual(searchPages("zzzzqq", visibleAll), []);
    assert.ok(searchPages("a", visibleAll).length <= 8);
  });
  test("can only ever return pages the person can see", () => {
    const some = visibleAll.filter((v) => v.item.path !== "/forensic" && v.item.path !== "/admin");
    for (const q of ["forensic", "fraud", "investigation", "admin", "users", "team"]) {
      for (const r of searchPages(q, some)) assert.ok(r.path !== "/forensic" && r.path !== "/admin", `${q} leaked ${r.path}`);
    }
  });
  test("typing is not treated as markup", () => assert.deepEqual(searchPages("<script>", visibleAll), []));
});

describe("the top bar", () => {
  const base = (over = {}) => {
    const calls = [];
    const rec = (n) => (...a) => calls.push([n, ...a]);
    const vnode = TopBar({
      crumbs: breadcrumbs("/tax", visibleAll), user: { email: "dara@meridian.test" }, role: "FINANCE_OFFICER",
      orgs: [{ id: "o1", name: "Meridian" }, { id: "o2", name: "Second Org" }], orgId: "o1", orgLabel: "Meridian", menu: null, switching: false, switchError: null, mobileOpen: false,
      search: { q: "", open: false, idx: 0 }, results: [],
      onToggleNav: rec("nav"), onToggle: rec("toggle"), onSwitch: rec("switch"), onAll: rec("all"), onGo: rec("go"), onSignOut: rec("out"),
      onInput: rec("input"), onKey: rec("key"), onPick: rec("pick"), ...over,
    });
    return { vnode, calls };
  };
  test("shows the organisation's name (not its id), the person, and the way to open the menu on a phone", () => {
    const { vnode } = base();
    assert.equal(text(byId(vnode, "org-label")), "Meridian");
    assert.ok(byId(vnode, "nav-toggle"));
    assert.equal(byId(vnode, "nav-toggle").props["aria-expanded"], "false");
    assert.equal(text(byId(vnode, "user-btn")), "D");
  });
  test("the organisation switcher lists the person's organisations, marks the current one, switches, and offers all organisations", () => {
    const { vnode, calls } = base({ menu: "org" });
    const items = all(byId(vnode, "org-menu"), (n) => n.props && n.props["data-org"]);
    assert.deepEqual(items.map((i) => i.props["data-org"]), ["o1", "o2"]);
    assert.equal(items[0].props["aria-checked"], "true");
    items[1].props.onClick();
    items[0].props.onClick();
    byId(vnode, "org-all").props.onClick();
    assert.deepEqual(calls.map((c) => c[0]), ["switch", "toggle", "all"]);
    assert.deepEqual(calls[0], ["switch", "o2"]);
  });
  test("the switcher says plainly when it is loading or failed, and shows a server refusal", () => {
    assert.match(text(byId(base({ menu: "org", orgs: null }).vnode, "org-loading")), /Loading/);
    assert.match(text(byId(base({ menu: "org", orgs: false }).vnode, "org-error")), /could not be loaded/);
    assert.match(text(byId(base({ menu: "org", switchError: "This organisation requires two-step sign-in." }).vnode, "org-switch-error")), /two-step/);
  });
  test("while switching, the organisation buttons are disabled", () => {
    const items = all(byId(base({ menu: "org", switching: true }).vnode, "org-menu"), (n) => n.props && n.props["data-org"]);
    assert.ok(items.every((i) => i.props.disabled));
  });
  test("the account menu shows the email and role and offers real actions", () => {
    const { vnode, calls } = base({ menu: "user" });
    assert.match(text(byId(vnode, "user-menu")), /dara@meridian\.test/);
    assert.match(text(byId(vnode, "user-role")), /Finance officer/);
    byId(vnode, "user-security").props.onClick(); byId(vnode, "user-diag").props.onClick(); byId(vnode, "user-signout").props.onClick();
    assert.deepEqual(calls, [["go", "/security"], ["go", "/diagnostics"], ["out"]]);
  });
  test("only one menu is drawn at a time", () => {
    assert.ok(!byId(base({ menu: "org" }).vnode, "user-menu"));
    assert.ok(!byId(base({ menu: "user" }).vnode, "org-menu"));
    assert.ok(!byId(base().vnode, "org-menu"));
  });
  test("the search box is a labelled combobox; results are links; an empty result says so", () => {
    const results = searchPages("tax", visibleAll);
    const { vnode } = base({ search: { q: "tax", open: true, idx: 0 }, results });
    const input = byId(vnode, "gsearch-input");
    assert.equal(input.props.role, "combobox");
    assert.equal(input.props["aria-expanded"], "true");
    assert.ok(all(vnode, (n) => n.tag === "label" && n.props.for === "gsearch-input").length === 1);
    assert.ok(all(byId(vnode, "gsearch-list"), (n) => n.tag === "a").some((a) => a.props.href === "#/tax"));
    assert.match(text(byId(base({ search: { q: "zzzz", open: true, idx: 0 }, results: [] }).vnode, "gsearch-none")), /No page matches/);
    assert.ok(!byId(base({ search: { q: "", open: true, idx: 0 }, results: [] }).vnode, "gsearch-list"));
  });
});

describe("workspace cards", () => {
  test("show the real status word from the catalogue, only open the ones the role may, and keep the rest separate", () => {
    const w = workspaceCards(CATALOG, "FINANCE_OFFICER");
    assert.equal(w.usedFallback, false);
    assert.ok(w.open.every((c) => c.canOpen) && w.locked.every((c) => !c.canOpen));
    assert.ok(w.locked.some((c) => c.id === "forensic"), "a finance officer does not hold forensic:read");
    assert.equal(w.open.find((c) => c.id === "analysis").status, "VERIFIED IN TEST ENVIRONMENT");
    assert.equal(w.open.length + w.locked.length, 3);
  });
  test("if the catalogue could not load, no status is claimed and the page says so", () => {
    const w = workspaceCards(null, "ADMINISTRATOR");
    assert.equal(w.usedFallback, true);
    assert.ok(w.cards.length >= 8);
    assert.ok(w.cards.every((c) => c.status === null && c.statusKnown === false));
  });
  test("a role with no workspace permission sees none open", () => {
    assert.equal(workspaceCards(CATALOG, "DONOR").open.length, 0);
  });
  test("a purpose is shortened to its first sentence", () => {
    assert.equal(shortPurpose("Ratios, variance and forecasts. More text after."), "Ratios, variance and forecasts.");
    assert.ok(shortPurpose("x".repeat(400)).length <= 120);
  });
});

describe("quick actions, names and roles", () => {
  test("offer only what the role may do, at most five", () => {
    assert.ok(quickActions("ADMINISTRATOR").length <= 5);
    assert.deepEqual(quickActions("DONOR"), []);
    assert.ok(!quickActions("READ_ONLY").some((a) => a.id === "team" || a.id === "journal"));
  });
  test("readable role and name text", () => {
    assert.equal(roleLabel("FINANCE_OFFICER"), "Finance officer");
    assert.equal(roleLabel(null), "");
    assert.equal(displayName({ email: "dara@meridian.test" }), "dara");
    assert.equal(displayName(null), "");
    assert.equal(orgName([{ id: "a", name: "Acme" }], "a"), "Acme");
    assert.equal(orgName(null, "a"), "a");
  });
});

describe("the setup checklist", () => {
  test("shows what is still to do, hides when everything is done, and never guesses what it could not check", () => {
    const s = setupSteps({ accounts: false, periods: false, evidence: true, team: null }, "ADMINISTRATOR");
    assert.equal(s.show, true);
    assert.deepEqual(s.todo.map((x) => x.id), ["accounts", "period"]);
    assert.deepEqual(s.unknown.map((x) => x.id), ["team"]);
    const done = setupSteps({ accounts: true, periods: true, evidence: true, team: true }, "ADMINISTRATOR");
    assert.equal(done.show, false);
    assert.equal(done.complete, true);
    const unsure = setupSteps({ accounts: null, periods: null, evidence: null, team: null }, "ADMINISTRATOR");
    assert.equal(unsure.show, false);
    assert.equal(unsure.complete, false);
    assert.ok(unsure.unknown.length > 0);
  });
  test("a role only sees steps it could act on", () => {
    const s = setupSteps({ accounts: false, periods: false, evidence: false, team: false }, "READ_ONLY");
    assert.ok(!s.steps.some((x) => x.id === "team"));
  });
});

describe("what needs attention", () => {
  const ok = (items) => ({ ok: true, items });
  test("keeps only urgent and watch items, urgent first, each with where it came from", () => {
    const a = mergeAttention([
      { ws: "tax", brief: ok([{ tone: "watch", text: "2 filings due soon", link: "/tax" }, { tone: "clear", text: "fine" }]) },
      { ws: "cyber", brief: ok([{ tone: "urgent", text: "1 vulnerability is past its fix deadline", link: "/cyber" }]) },
      { ws: "grc", brief: ok([{ tone: "clear", text: "Nothing is waiting in GRC right now." }]) },
    ]);
    assert.equal(a.items.length, 2);
    assert.equal(a.items[0].tone, "urgent");
    assert.equal(a.items[0].workspace, "Cybersecurity");
    assert.equal(a.urgent, 1); assert.equal(a.watch, 1);
    assert.deepEqual(a.clear, ["Governance, Risk and Compliance"]);
  });
  test("a source that failed is named; a refusal or an empty workspace is not shown as a fault", () => {
    const a = mergeAttention([
      { ws: "tax", brief: { ok: false, reason: "error", message: "boom" } },
      { ws: "forensic", brief: { ok: false, reason: "denied" } },
      { ws: "health", brief: { ok: false, reason: "none" } },
      { ws: "cyber", brief: ok([{ tone: "clear", text: "none" }]) },
    ]);
    assert.deepEqual(a.failed, ["Tax Compliance"]);
    assert.equal(a.items.length, 0);
    assert.match(attentionSummary(a), /sources that could be read/);
  });
  test("all clear and nothing failed says nothing is waiting", () => {
    assert.equal(attentionSummary(mergeAttention([{ ws: "tax", brief: ok([{ tone: "clear", text: "x" }]) }])), "Nothing is waiting for you right now.");
  });
  test("when no source could be asked at all, it does not claim that nothing is waiting", () => {
    const a = mergeAttention([]);
    assert.equal(a.checked, 0);
    assert.match(attentionSummary(a), /no workspace overviews to show/);
    assert.ok(!/Nothing is waiting/.test(attentionSummary(a)));
  });
  test("only asks workspaces the role may brief on", () => {
    assert.ok(!attentionSources("DONOR").length);
    assert.ok(attentionSources("ADMINISTRATOR").includes("cyber"));
    assert.ok(!attentionSources("FINANCE_OFFICER").includes("forensic"));
  });
});

describe("loading the home page", () => {
  const fakeApi = (over = {}) => ({
    workspaces: async () => CATALOG, listAccounts: async () => [{ id: 1 }], listPeriods: async () => [{ id: "p", name: "P1", end_date: "2026-01-31" }],
    listEvidence: async () => [], getOrganisationProfile: async () => ({ country: "Nigeria", base_currency: "NGN", fiscal_year_start_month: 1, organisation_type: "Business or SME" }), listMembers: async () => [{ id: "u1" }], myOrganisations: async () => [{ id: "o1", name: "Meridian" }],
    cyOverview: async () => ({ counts: {}, vulnerabilities: { overdue: 2 }, attention: {} }),
    ...over,
  });
  test("reads the catalogue, the organisations and the setup facts through the person's own permissions", async () => {
    const d = await loadHome(fakeApi(), "ADMINISTRATOR", "o1");
    assert.equal(d.catalog.workspaces.length, 3);
    assert.equal(d.orgs[0].name, "Meridian");
    assert.equal(d.facts.accounts, true);
    assert.equal(d.facts.profile, true);
    assert.equal(d.facts.evidence, false);
    assert.equal(d.facts.team, false, "one member is not a second person");
  });
  test("one failing source never hides the others, and is not reported as empty", async () => {
    const d = await loadHome(fakeApi({ workspaces: async () => { throw new Error("down"); }, listAccounts: async () => { throw new Error("down"); } }), "ADMINISTRATOR", "o1");
    assert.equal(d.catalog, null);
    assert.equal(d.facts.accounts, null);
    assert.equal(d.facts.periods, true);
    assert.ok(d.attention.failed.length > 0, "workspace overviews that threw are named");
  });
  test("does not call endpoints the role cannot use", async () => {
    const called = [];
    const spy = fakeApi({ listAccounts: async () => { called.push("accounts"); return []; }, listEvidence: async () => { called.push("evidence"); return []; }, listMembers: async () => { called.push("members"); return []; } });
    await loadHome(spy, "DONOR", "o1");
    assert.deepEqual(called, []);
  });
});

describe("the home page", () => {
  const data = (over = {}) => ({
    catalog: CATALOG, orgs: [], facts: { accounts: true, periods: true, evidence: true, team: true },
    attention: { items: [{ tone: "urgent", text: "1 vulnerability is past its fix deadline", workspace: "Cybersecurity", link: "/cyber" }], failed: [], clear: [], urgent: 1, watch: 0 }, ...over,
  });
  const props = (over = {}) => {
    const calls = [];
    const rec = (n) => (...a) => calls.push([n, ...a]);
    return { calls, p: { user: { email: "dara@meridian.test" }, role: "ADMINISTRATOR", orgLabel: "Meridian", data: data(), loading: false, error: null, dashboardData: {}, showLocked: false, aiAvailable: true,
      onNavigate: rec("nav"), onToggleLocked: rec("locked"), onOpenAi: rec("ai"), onRetry: rec("retry"), ...over } };
  };
  test("welcomes the person by name and states organisation and role; exactly one h1", () => {
    const v = Home(props().p);
    assert.equal(all(v, (n) => n.tag === "h1").length, 1);
    assert.match(text(byId(v, "hm-h1")), /Welcome back, dara/);
    assert.equal(text(byId(v, "hm-sub")), "Meridian · Administrator");
  });
  test("attention items are links that go to the right page; the AI card opens the AI", () => {
    const { p, calls } = props();
    const v = Home(p);
    const link = all(byId(v, "hm-attn-list"), (n) => n.tag === "a")[0];
    assert.equal(link.props.href, "#/cyber");
    link.props.onClick({ preventDefault() {} });
    byId(v, "hm-ai-open").props.onClick();
    assert.deepEqual(calls, [["nav", "/cyber"], ["ai"]]);
  });
  test("an all-clear shows one honest line; failed sources are named with a retry", () => {
    const clear = Home(props({ data: data({ attention: { items: [], failed: [], clear: ["Tax Compliance"], checked: 1, urgent: 0, watch: 0 } }) }).p);
    assert.match(text(byId(clear, "hm-attn-none")), /Nothing is waiting/);
    const { p, calls } = props({ data: data({ attention: { items: [], failed: ["Tax Compliance"], clear: [], urgent: 0, watch: 0 } }) });
    const v = Home(p);
    assert.match(text(byId(v, "hm-attn-failed")), /Could not be checked: Tax Compliance/);
    byId(v, "hm-attn-retry").props.onClick();
    assert.deepEqual(calls, [["retry"]]);
  });
  test("a loading page says loading and does not show an empty or all-clear state", () => {
    const v = Home(props({ data: null, loading: true }).p);
    assert.ok(!byId(v, "hm-attn-none"));
    assert.match(text(v), /Loading/i);
  });
  test("an error is shown with a retry", () => {
    const v = Home(props({ error: "The home page could not be loaded." }).p);
    assert.match(text(v), /could not be loaded/);
  });
  test("workspace cards: Open goes to the workspace; the locked ones are hidden until asked for", () => {
    const { p, calls } = props({ role: "FINANCE_OFFICER" });
    const v = Home(p);
    byId(v, "hm-open-analysis").props.onClick();
    assert.deepEqual(calls[0], ["nav", "/analysis"]);
    assert.ok(!byId(v, "hm-locked-grid"));
    assert.ok(!byId(v, "hm-open-forensic"), "a role that cannot open it gets no Open button");
    assert.match(text(byId(v, "hm-locked-toggle")), /Show 1 workspace your role cannot open/);
    byId(v, "hm-locked-toggle").props.onClick();
    assert.equal(calls[1][0], "locked");
    const shown = Home(props({ role: "FINANCE_OFFICER", showLocked: true }).p);
    assert.ok(byId(shown, "hm-locked-grid"));
    assert.match(text(byId(shown, "hm-locked-grid")), /Not available to your role/);
  });
  test("each card shows the catalogue's status word; with no catalogue it says none could be loaded", () => {
    assert.match(text(byId(Home(props().p), "hm-ws-grid")), /VERIFIED IN TEST ENVIRONMENT/);
    const v = Home(props({ data: data({ catalog: null }) }).p);
    assert.match(text(byId(v, "hm-ws-fallback")), /could not be loaded/);
    assert.ok(!/VERIFIED/.test(text(byId(v, "hm-ws-grid"))));
  });
  test("a role with no workspace says so instead of showing an empty page", () => {
    assert.match(text(byId(Home(props({ role: "DONOR" }).p), "hm-ws-none")), /No workspace is open to your role/);
  });
  test("the setup checklist appears when setup is incomplete and its Go buttons navigate", () => {
    const { p, calls } = props({ data: data({ facts: { accounts: false, periods: false, evidence: true, team: true } }) });
    const v = Home(p);
    assert.ok(byId(v, "hm-setup"));
    byId(v, "hm-setup-accounts").props.onClick();
    assert.deepEqual(calls[0], ["nav", "/accounting"]);
    assert.ok(!byId(Home(props().p), "hm-setup"));
  });
  test("a role that cannot ask the ledger is told AI is not offered", () => {
    const v = Home(props({ aiAvailable: false }).p);
    assert.ok(!byId(v, "hm-ai-open"));
    assert.match(text(byId(v, "hm-ai")), /not offered/);
  });
  test("the existing finance cards are still on the page, without a second h1", () => {
    const v = Home(props().p);
    assert.ok(byId(v, "hm-glance"));
    assert.equal(all(byId(v, "hm-glance"), (n) => n.tag === "h1").length, 0);
  });
  test("every button has a handler", () => {
    const v = Home(props({ role: "FINANCE_OFFICER", data: data({ facts: { accounts: false, periods: true, evidence: true, team: true }, attention: { items: [], failed: ["X"], clear: [], urgent: 0, watch: 0 } }) }).p);
    for (const b of all(v, (n) => n.tag === "button")) assert.equal(typeof b.props.onClick, "function", b.props.id || text(b));
  });
});

describe("source contracts in app.js and the styles", () => {
  test("the dashboard route renders the new home page and the old cards still load", () => {
    assert.match(appSource, /return Home\(\{/);
    assert.match(appSource, /loadDashboardData\(authState\);\s*loadHomeData\(authState\)/);
  });
  test("switching organisation reloads the page so nothing from the old organisation stays in memory", () => {
    const fn = appSource.slice(appSource.indexOf("async function switchOrganisation"), appSource.indexOf("/** Read everything the home page shows"));
    assert.match(fn, /api\.selectOrganisation\(orgId\)/);
    assert.match(fn, /authStore\.setOrganisation\(orgId, role\)/);
    assert.match(fn, /window\.location\.reload\(\)/);
    assert.match(fn, /catch \(err\)/, "a refusal (for example two-step required) is shown, not swallowed");
  });
  test("signing out reloads, and home data is keyed by organisation and role", () => {
    assert.match(appSource, /function handleLogout[\s\S]*?window\.location\.reload\(\)/);
    assert.match(appSource, /const key = `\$\{authState\.organisationId\}\|\$\{authState\.role\}`/);
  });
  test("focusing the search box cannot start a render loop (a render restores focus, which fires focus again)", () => {
    assert.match(appSource, /if \(focusOnly && \(uiState\.search\.open \|\| !uiState\.search\.q\.trim\(\)\)\) return;/);
  });
  test("Escape and clicking elsewhere close the menus; moving to another page closes them too", () => {
    assert.match(appSource, /e\.key !== "Escape"/);
    assert.match(appSource, /closest\("\.menu-wrap, \.gsearch"\)/);
    assert.match(appSource, /uiState\.lastPath !== path/);
  });
  test("home.css is linked and the phone menu, reduced motion and drawer rules exist", () => {
    assert.match(htmlSource, /styles\/home\.css/);
    assert.match(cssSource, /\.nav-toggle \{ display: flex; \}/);
    assert.match(cssSource, /prefers-reduced-motion/);
    assert.match(cssSource, /\.app-sidebar\.is-open/);
  });
  test("the permission tables used by the cards exist for every role named in the tests", () => {
    for (const r of ["ADMINISTRATOR", "FINANCE_OFFICER", "READ_ONLY", "DONOR"]) assert.ok(r in ROLE_PERMISSIONS, r);
  });
});
