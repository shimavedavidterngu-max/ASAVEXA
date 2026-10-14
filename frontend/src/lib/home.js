import { PERMISSIONS, ROLE_PERMISSIONS } from "./permissions.js";
import { settingsComplete } from "./onboarding.js";
import { WORKSPACES as DOCK_WORKSPACES, fetchBrief, workspaceForPath, briefAllowed } from "./aidock.js";

/**
 * The signed-in home page and the shell around it (grouped menu, breadcrumbs, search, organisation switcher).
 * This file is pure logic: no network of its own except through the `api` object handed to the loaders, and no DOM.
 *
 * Honest by construction:
 *  - Every card, menu entry and search result points at a page that exists and that the role may open.
 *  - "Needs attention" is built only from each workspace's own server-checked overview. If a source fails, the page says
 *    which one could not be checked; it never shows a reassuring zero in its place.
 *  - Role checks here decide only what to offer. The server decides what is allowed.
 */
const has = (role, perm) => !perm || !!(ROLE_PERMISSIONS[role] && ROLE_PERMISSIONS[role].includes(perm));
const plural = (n, one, many) => `${n} ${n === 1 ? one : many || one + "s"}`;

// ------------------------------------------------------------------ menu groups
/** Where each menu entry lives. Every path in the app's menu must appear here (a test checks it). */
export const NAV_GROUPS = [
  { id: "home", label: "Home", paths: ["/"] },
  { id: "books", label: "Books and evidence", paths: ["/accounting", "/evidence", "/reconciliation", "/period-close", "/reporting", "/proof", "/evidence-review", "/audit", "/compliance"] },
  { id: "workspaces", label: "Professional workspaces", paths: ["/workspaces", "/analysis", "/tax", "/forensic", "/grc", "/pubfin", "/bizdev", "/cyber", "/itaudit", "/resilience", "/aigov", "/treasury", "/procurement", "/fpa", "/fincrime", "/health"] },
  { id: "trust", label: "Passport and network", paths: ["/passport", "/passport/sharing", "/network", "/validation", "/standards", "/standards-registry", "/agents", "/assurance", "/proof-links"] },
  { id: "data", label: "Data and administration", paths: ["/import", "/admin", "/setup", "/entity-config", "/ai"] },
  { id: "account", label: "Account and help", paths: ["/security", "/pilot", "/diagnostics"] },
];

/** Group the entries a role may see. Empty groups disappear. Anything not listed in a group is kept in "More", never dropped. */
export function groupNav(items) {
  const byPath = new Map(items.map((i) => [i.item.path, i]));
  const used = new Set();
  const groups = NAV_GROUPS.map((g) => {
    const list = g.paths.map((p) => byPath.get(p)).filter(Boolean);
    list.forEach((i) => used.add(i.item.path));
    return { id: g.id, label: g.label, items: list };
  }).filter((g) => g.items.length);
  const rest = items.filter((i) => !used.has(i.item.path));
  if (rest.length) groups.push({ id: "more", label: "More", items: rest });
  return groups;
}

/** Which group holds the active entry, so that group is always open. */
export function activeGroupId(groups) {
  const g = groups.find((x) => x.items.some((i) => i.active));
  return g ? g.id : null;
}

/** A group is open if the person chose so; otherwise it is open only when it holds the page they are on. Home is a single link. */
export function groupOpen(group, navOpen, activeId) {
  if (group.id === "home") return true;
  if (navOpen && typeof navOpen[group.id] === "boolean") return navOpen[group.id];
  return group.id === activeId;
}

// ------------------------------------------------------------------ breadcrumbs
const tail = (seg) => seg.replace(/[-_]/g, " ").replace(/^./, (c) => c.toUpperCase());
/** Home > group > page, plus one trailing crumb for a detail page. The last crumb is the current page and is not a link. */
export function breadcrumbs(path, visible) {
  const p = String(path || "/").split("?")[0];
  const home = { label: "Home", path: "/" };
  if (p === "/") return [{ label: "Home", path: null }];
  const items = visible.map((v) => v.item);
  const matches = items.filter((i) => i.path !== "/" && (p === i.path || p.startsWith(i.path + "/")));
  const best = matches.reduce((a, b) => (!a || b.path.length > a.path.length ? b : a), null);
  if (!best) return [home, { label: "Page not found", path: null }];
  const group = NAV_GROUPS.find((g) => g.paths.includes(best.path));
  const crumbs = [home];
  if (group && group.id !== "home") crumbs.push({ label: group.label, path: null });
  if (p === best.path) { crumbs.push({ label: best.label, path: null }); return crumbs; }
  crumbs.push({ label: best.label, path: best.path });
  const rest = p.slice(best.path.length + 1).split("/").filter(Boolean);
  // a long id is shown as "Detail"; a word like "new" or "trial-balance" is shown as itself
  crumbs.push({ label: rest.length === 1 && rest[0].length < 24 && /^[a-z-]+$/i.test(rest[0]) ? tail(rest[0]) : "Detail", path: null });
  return crumbs;
}

// ------------------------------------------------------------------ search
const KEYWORDS = {
  "/accounting": "journal ledger accounts chart of accounts posting", "/evidence": "documents invoices receipts upload vault", "/reconciliation": "bank statement match",
  "/reporting": "reports trial balance statements", "/proof": "proof graph trace", "/agents": "agents automation policy approval decisions", "/proof-links": "proof links evidence control finding remediation risk standard confirm dispute missing link trace", "/assurance": "assurance status vocabulary recorded supported reconciled reviewed approved independently verified", "/standards-registry": "standards registry sources verified framework review", "/evidence-review": "evidence review missing conflicting stale case verify", "/period-close": "close month year lock", "/compliance": "controls findings",
  "/audit": "audit trail search journal", "/analysis": "ratios variance budget forecast break-even", "/tax": "vat gst filing rates", "/forensic": "fraud investigation case",
  "/grc": "risk register governance obligations", "/pubfin": "budget procurement grants public sector", "/bizdev": "pipeline proposals accounts clients sales",
  "/cyber": "security vulnerabilities incidents assets", "/aigov": "ai artificial intelligence model system inventory incident change governance", "/resilience": "risk indicator kri loss event near miss business impact continuity recovery objective disaster", "/itaudit": "it audit change management application control sample test emergency change", "/treasury": "cash bank balance forecast liquidity payment approval covenant loan", "/procurement": "supplier vendor contract purchase order delivery invoice three-way match goods received payment review", "/fpa": "kpi key performance indicator owner target reading forecast accuracy bias budget planning fp&a variance", "/fincrime": "financial crime aml money laundering sanctions pep screening alert case investigation conflict of interest loss recovery fraud suspicious", "/health": "clinic stock claims facility", "/import": "csv upload data", "/admin": "users members roles team invite", "/entity-config": "organisation type subtype kind workspaces menu enable hide sector", "/setup": "onboarding organisation details currency country financial year period getting started",
  "/ai": "ask assistant question", "/passport": "financial passport share", "/passport/sharing": "share links", "/security": "password two-step mfa sign in",
  "/network": "network", "/validation": "professional review", "/standards": "ifrs gaap jurisdiction policies", "/diagnostics": "self-test connection", "/pilot": "pilot",
};
/** Pages the person can open that match what they typed. Label matches rank above keyword matches. Nothing outside the visible menu is ever returned. */
export function searchPages(query, visible, limit = 8) {
  const q = String(query || "").trim().toLowerCase();
  if (!q) return [];
  const words = q.split(/\s+/);
  const scored = [];
  for (const { item } of visible) {
    const label = item.label.toLowerCase();
    const kw = (KEYWORDS[item.path] || "").toLowerCase();
    let score = 0;
    if (label === q) score = 100;
    else if (label.startsWith(q)) score = 80;
    else if (label.includes(q)) score = 60;
    else if (words.every((w) => label.includes(w) || kw.includes(w))) score = 40;
    else if (kw.includes(q)) score = 30;
    if (score) scored.push({ score, item });
  }
  scored.sort((a, b) => b.score - a.score || a.item.label.localeCompare(b.item.label));
  const group = (path) => (NAV_GROUPS.find((g) => g.paths.includes(path)) || {}).label || "";
  return scored.slice(0, limit).map(({ item }) => ({ path: item.path, label: item.label, group: group(item.path) }));
}

// ------------------------------------------------------------------ people and organisations
export const roleLabel = (role) => String(role || "").toLowerCase().replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
export function displayName(user) {
  const email = user && user.email ? String(user.email) : "";
  return email ? email.split("@")[0] : "";
}
export const initialOf = (user) => (displayName(user)[0] || "?").toUpperCase();
/** The organisation's name, or its id until the name is known. */
export function orgName(orgs, orgId) {
  const o = (orgs || []).find((x) => x.id === orgId);
  return o && o.name ? o.name : orgId || "";
}

// ------------------------------------------------------------------ workspace cards
/** Static fallback if the workspace catalogue cannot be loaded: names and links only, no status claimed. */
const FALLBACK = Object.entries(DOCK_WORKSPACES).filter(([id]) => id !== "general").map(([id, w]) => ({ id, name: w.label, path: w.path, permission: w.perm, status: null, purpose: "", note: "" }));

/** Cards for the workspaces. The catalogue (with honest status words) is used when it loaded; otherwise the fallback says so. */
export function workspaceCards(catalog, role) {
  const list = catalog && Array.isArray(catalog.workspaces) && catalog.workspaces.length ? catalog.workspaces : FALLBACK;
  const cards = list.filter((w) => w.path).map((w) => ({
    id: w.id, name: w.name, path: w.path, status: w.status || null, purpose: w.purpose || "", permission: w.permission || null,
    canOpen: has(role, w.permission), statusKnown: !!w.status,
  }));
  return { cards, usedFallback: !(catalog && Array.isArray(catalog.workspaces) && catalog.workspaces.length), open: cards.filter((c) => c.canOpen), locked: cards.filter((c) => !c.canOpen) };
}

/** A short one-line form of a purpose text: the first sentence, capped. */
export function shortPurpose(text, max = 120) {
  const first = String(text || "").split(/(?<=[.!?])\s/)[0] || "";
  return first.length > max ? first.slice(0, max - 1).trimEnd() + "…" : first;
}

// ------------------------------------------------------------------ quick actions
const ACTIONS = [
  { id: "journal", label: "Record a journal", path: "/accounting/journals/new", perm: PERMISSIONS.JOURNAL_CREATE },
  { id: "evidence", label: "Upload evidence", path: "/evidence", perm: PERMISSIONS.EVIDENCE_UPLOAD },
  { id: "import", label: "Import data", path: "/import", perm: null, anyOf: [PERMISSIONS.RECONCILIATION_IMPORT, PERMISSIONS.EVIDENCE_UPLOAD, PERMISSIONS.ACCOUNT_MANAGE, PERMISSIONS.JOURNAL_CREATE] },
  { id: "reconcile", label: "Start a reconciliation", path: "/reconciliation/new", perm: PERMISSIONS.RECONCILIATION_CREATE || PERMISSIONS.RECONCILIATION_READ },
  { id: "reports", label: "Open reports", path: "/reporting", perm: PERMISSIONS.REPORTING_READ },
  { id: "team", label: "Manage your team", path: "/admin", perm: PERMISSIONS.ORG_MANAGE_USERS },
];
export function quickActions(role) {
  return ACTIONS.filter((a) => (a.anyOf ? a.anyOf.some((p) => has(role, p)) : has(role, a.perm))).slice(0, 5);
}

// ------------------------------------------------------------------ setup checklist
/**
 * Whether the organisation is set up enough for the finance pages to mean something.
 * `facts` values are true, false, or null when that source could not be checked (never guessed as false).
 */
export function setupSteps(facts, role) {
  const steps = [
    ...(facts.profile === undefined ? [] : [{ id: "profile", label: "Complete the organisation details", path: "/setup", done: facts.profile, perm: PERMISSIONS.ORG_MANAGE_SETTINGS }]),
    { id: "accounts", label: "Add your chart of accounts", path: "/accounting", done: facts.accounts, perm: PERMISSIONS.LEDGER_READ },
    { id: "period", label: "Open an accounting period", path: facts.profile === undefined ? "/accounting" : "/setup", done: facts.periods, perm: PERMISSIONS.LEDGER_READ },
    { id: "evidence", label: "Store your first piece of evidence", path: "/evidence", done: facts.evidence, perm: PERMISSIONS.EVIDENCE_READ },
    { id: "team", label: "Invite a second person to review and approve", path: "/admin", done: facts.team, perm: PERMISSIONS.ORG_MANAGE_USERS },
  ].filter((s) => has(role, s.perm));
  const known = steps.filter((s) => s.done !== null && s.done !== undefined);
  const todo = known.filter((s) => !s.done);
  const unknown = steps.filter((s) => s.done === null || s.done === undefined);
  return { steps, todo, unknown, complete: steps.length > 0 && todo.length === 0 && unknown.length === 0, show: todo.length > 0 };
}

// ------------------------------------------------------------------ attention
const BRIEF_WORKSPACES = ["analysis", "tax", "forensic", "grc", "pubfin", "bizdev", "cyber", "health"];
export const attentionSources = (role) => ["general", ...BRIEF_WORKSPACES].filter((ws) => (ws === "general" ? has(role, PERMISSIONS.EVIDENCE_READ) : briefAllowed(ws, role)));

/**
 * Turn the briefs into one list. Only urgent and watch items are kept, urgent first.
 * `failed` names every source that could not be read, so the page can say so instead of implying all is well.
 */
export function mergeAttention(results) {
  const items = [], failed = [], clear = [];
  const order = { urgent: 0, watch: 1 };
  for (const r of results) {
    const w = DOCK_WORKSPACES[r.ws];
    const label = w ? w.label : r.ws;
    const where = r.ws === "general" ? "/evidence" : w ? w.path : "/";
    if (!r.brief || !r.brief.ok) {
      if (r.brief && r.brief.reason === "none") continue;       // nothing set up there yet is not a failure
      if (r.brief && r.brief.reason === "denied") continue;     // the server declined; do not show it as a fault
      failed.push(label);
      continue;
    }
    const live = r.brief.items.filter((i) => i.tone === "urgent" || i.tone === "watch");
    if (!live.length) clear.push(label);
    for (const i of live) items.push({ tone: i.tone, text: i.text, workspace: label, link: i.link || where });
  }
  items.sort((a, b) => order[a.tone] - order[b.tone] || a.workspace.localeCompare(b.workspace));
  return { items, failed, clear, checked: results.length, urgent: items.filter((i) => i.tone === "urgent").length, watch: items.filter((i) => i.tone === "watch").length };
}
export const attentionSummary = (a) => {
  if (!a) return "";
  if (!a.items.length && a.checked === 0) return "Your role has no workspace overviews to show here, so there is nothing to check.";
  if (!a.items.length) return a.failed.length ? "Nothing found waiting in the sources that could be read." : "Nothing is waiting for you right now.";
  const parts = [];
  if (a.urgent) parts.push(plural(a.urgent, "urgent item"));
  if (a.watch) parts.push(plural(a.watch, "item") + " to watch");
  return parts.join(" and ");
};

// ------------------------------------------------------------------ loading
/**
 * Everything the home page shows, read through the caller's own permissions. Each source is independent: one failing
 * never hides the others. Returns plain data; the page decides how to draw it.
 */
export async function loadHome(api, role, orgId) {
  const safe = async (p) => { try { return { ok: true, value: await p }; } catch (err) { return { ok: false, error: err }; } };
  const [catalog, accounts, periods, evidence, members, orgs, profile] = await Promise.all([
    safe(api.workspaces()),
    has(role, PERMISSIONS.LEDGER_READ) ? safe(api.listAccounts()) : Promise.resolve(null),
    has(role, PERMISSIONS.LEDGER_READ) ? safe(api.listPeriods()) : Promise.resolve(null),
    has(role, PERMISSIONS.EVIDENCE_READ) ? safe(api.listEvidence()) : Promise.resolve(null),
    has(role, PERMISSIONS.ORG_MANAGE_USERS) && orgId ? safe(api.listMembers(orgId)) : Promise.resolve(null),
    safe(api.myOrganisations()),
    has(role, PERMISSIONS.ORG_MANAGE_SETTINGS) ? safe(api.getOrganisationProfile()) : Promise.resolve(null),
  ]);
  const count = (r) => (r === null ? null : r.ok && Array.isArray(r.value) ? r.value.length > 0 : null);
  const facts = { profile: profile === null ? undefined : profile.ok && profile.value && typeof profile.value === "object" ? settingsComplete(profile.value) : null, accounts: count(accounts), periods: count(periods), evidence: count(evidence), team: members === null ? null : members.ok && Array.isArray(members.value) ? members.value.filter((m) => m.status !== "REVOKED" && m.is_active !== false).length > 1 : null };
  const sources = attentionSources(role);
  const results = await Promise.all(sources.map(async (ws) => ({ ws, brief: await fetchBrief(api, ws, role) })));
  return {
    catalog: catalog.ok ? catalog.value : null,
    orgs: orgs.ok && Array.isArray(orgs.value) ? orgs.value : null,
    facts, attention: mergeAttention(results), at: new Date().toISOString(),
  };
}
export { workspaceForPath };
