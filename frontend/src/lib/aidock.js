import { PERMISSIONS, ROLE_PERMISSIONS } from "./permissions.js";

/**
 * ASAVEXA AI, docked on every signed-in page ("the Proof Lens").
 *
 * Honest by construction:
 *  - The brief is built only from each workspace's own server-checked overview. If the server refuses (403) or the
 *    workspace has nothing, the dock says so; it never invents a figure and never reads anything the user cannot read.
 *  - Questions go to the existing ASAVEXA AI, which is rule-based, grounded in the organisation's own records, read-only,
 *    and uses no outside AI model. A question it cannot ground is refused, and the dock shows the refusal as it is.
 *  - Role checks here only decide what to offer. The server decides what is allowed.
 */
const has = (role, perm) => !!(ROLE_PERMISSIONS[role] && ROLE_PERMISSIONS[role].includes(perm));
export const canAsk = (role) => has(role, PERMISSIONS.LEDGER_READ);
const plural = (n, one, many) => `${n} ${n === 1 ? one : many || one + "s"}`;
const num = (v) => (Number.isFinite(Number(v)) ? Number(v) : 0);

/** Workspace the person is looking at, from the hash path. `general` covers the shared finance pages. */
export const WORKSPACES = {
  analysis: { label: "Financial Analysis", path: "/analysis", perm: PERMISSIONS.REPORTING_READ, starters: ["Find unusual transactions.", "Show the evidence for revenue."] },
  tax: { label: "Tax Compliance", path: "/tax", perm: PERMISSIONS.REPORTING_READ, starters: ["Find unusual transactions.", "Suggest a reconciliation or adjustment."] },
  forensic: { label: "Forensic Investigation", path: "/forensic", perm: PERMISSIONS.FORENSIC_READ, starters: ["Find unusual transactions.", "Show the evidence for expenses."] },
  grc: { label: "Governance, Risk and Compliance", path: "/grc", perm: PERMISSIONS.AUDIT_READ, starters: ["Find unusual transactions."] },
  pubfin: { label: "Public Finance", path: "/pubfin", perm: PERMISSIONS.REPORTING_READ, starters: ["Find unusual transactions.", "Show the evidence for expenses."] },
  bizdev: { label: "Business Development", path: "/bizdev", perm: PERMISSIONS.REPORTING_READ, starters: ["Show the evidence for revenue."] },
  cyber: { label: "Cybersecurity", path: "/cyber", perm: PERMISSIONS.AUDIT_READ, starters: ["Find unusual transactions."] },
  health: { label: "Health Centre", path: "/health", perm: PERMISSIONS.HEALTH_READ, starters: ["Find unusual transactions.", "Show the evidence for expenses."] },
  general: { label: "Your finance records", path: "/", perm: null, starters: ["Find unusual transactions.", "Suggest a reconciliation or adjustment.", "Show the evidence for revenue."] },
};
const PREFIXES = [["/analysis", "analysis"], ["/tax", "tax"], ["/forensic", "forensic"], ["/grc", "grc"], ["/pubfin", "pubfin"], ["/bizdev", "bizdev"], ["/cyber", "cyber"], ["/health", "health"]];
export function workspaceForPath(path) {
  const p = String(path || "/").split("?")[0];
  for (const [pre, id] of PREFIXES) if (p === pre || p.startsWith(pre + "/")) return id;
  return "general";
}

/** Whether the dock should be offered at all: it needs at least the question permission or one workspace to brief on. */
export function dockAvailable(role) {
  if (canAsk(role)) return true;
  return Object.entries(WORKSPACES).some(([id, w]) => id !== "general" && w.perm && has(role, w.perm));
}
export const briefAllowed = (ws, role) => (WORKSPACES[ws] && WORKSPACES[ws].perm ? has(role, WORKSPACES[ws].perm) : false);

// ------------------------------------------------------------------ brief items
const item = (tone, text, link) => ({ tone, text, link: link || null });
/** Items are ordered urgent, then watch, then clear. An empty list becomes one honest "nothing waiting" line. */
function finish(items, scope) {
  const order = { urgent: 0, watch: 1, clear: 2 };
  const out = items.filter(Boolean).sort((a, b) => order[a.tone] - order[b.tone]);
  return out.length ? out : [item("clear", `Nothing is waiting in ${scope} right now.`)];
}
const count = (n, tone, one, many, link) => (n > 0 ? item(tone, plural(n, one, many), link) : null);

const BUILDERS = {
  cyber(ov) {
    const c = ov.counts || {}, v = ov.vulnerabilities || {}, a = ov.attention || {};
    return finish([
      count(num(v.overdue), "urgent", "vulnerability is past its fix deadline", "vulnerabilities are past their fix deadline", "/cyber"),
      count((a.acceptance_expired || []).length, "urgent", "accepted risk has expired", "accepted risks have expired", "/cyber"),
      count(num(c.fixes_waiting), "watch", "fix is waiting for a different person to verify it", "fixes are waiting for a different person to verify them", "/cyber"),
      count(num(c.acceptances_waiting), "watch", "risk acceptance is waiting for approval", "risk acceptances are waiting for approval", "/cyber"),
      count(num(c.closures_waiting), "watch", "incident closure is waiting for approval", "incident closures are waiting for approval", "/cyber"),
      count(num(c.incidents_open), "watch", "incident is open", "incidents are open", "/cyber"),
    ], "Cybersecurity");
  },
  bizdev(ov) {
    const c = ov.counts || {};
    return finish([
      count(num(c.proposals_pending), "watch", "proposal discount is waiting for approval", "proposal discounts are waiting for approval", "/bizdev"),
      count(num(c.wins_pending), "watch", "win is waiting for confirmation", "wins are waiting for confirmation", "/bizdev"),
      num(c.open) ? item("clear", `${plural(num(c.open), "opportunity is", "opportunities are")} open in the pipeline.`, "/bizdev") : null,
    ], "Business Development");
  },
  grc(d) {
    const c = d.counts || {}, a = d.attention || {};
    return finish([
      count((a.actions_overdue || []).length, "urgent", "treatment action is overdue", "treatment actions are overdue", "/grc"),
      count(num(c.obligations_overdue), "urgent", "obligation is overdue", "obligations are overdue", "/grc"),
      count((a.above_appetite_without_plan || []).length, "urgent", "risk is above appetite with no treatment plan", "risks are above appetite with no treatment plan", "/grc"),
      count((a.reviews_overdue || []).length, "watch", "risk review is overdue", "risk reviews are overdue", "/grc"),
      count(num(c.actions_awaiting_verification), "watch", "completed action is waiting for someone else to verify it", "completed actions are waiting for someone else to verify them", "/grc"),
      count((a.acceptances_waiting || []).length, "watch", "risk acceptance is waiting for approval", "risk acceptances are waiting for approval", "/grc"),
      count(num(c.obligations_due_soon), "watch", "obligation is due soon", "obligations are due soon", "/grc"),
    ], "Governance, Risk and Compliance");
  },
  tax(ov) {
    return finish([
      num(ov.selected) === 0 ? item("watch", "No tax jurisdiction has been selected yet.", "/tax") : null,
      count((ov.selected_without_rules || []).length, "urgent", "selected jurisdiction has no approved rules in force", "selected jurisdictions have no approved rules in force", "/tax"),
      count(num(ov.rules_waiting), "watch", "tax rule is waiting for approval", "tax rules are waiting for approval", "/tax"),
    ], "Tax Compliance");
  },
  pubfin(ov) {
    const c = ov.counts || {};
    return finish([
      count((ov.overspent_lines || []).length, "urgent", "budget line is overspent", "budget lines are overspent", "/pubfin"),
      count((ov.grants_expired || []).length, "urgent", "grant has ended with money unspent or unreported", "grants have ended with money unspent or unreported", "/pubfin"),
      count((ov.grants_overspent_vs_received || []).length, "urgent", "grant has spent more than was received", "grants have spent more than was received", "/pubfin"),
      count(num(c.budgets_waiting), "watch", "budget is waiting for approval", "budgets are waiting for approval", "/pubfin"),
      count(num(c.awards_waiting), "watch", "procurement award is waiting for approval", "procurement awards are waiting for approval", "/pubfin"),
      count(num(c.spend_waiting), "watch", "grant spend is waiting for approval", "grant spends are waiting for approval", "/pubfin"),
      count(num(c.virements_waiting), "watch", "budget transfer is waiting for approval", "budget transfers are waiting for approval", "/pubfin"),
    ], "Public Finance");
  },
  analysis(ov) {
    const issues = (ov && ov.issues) || [];
    return finish(issues.map((t) => item("watch", t, "/analysis")), `the analysis for ${ov && ov.period ? ov.period.name : "the latest period"}`);
  },
  forensic(cases) {
    const open = (cases || []).filter((c) => c.status === "OPEN");
    return finish([count(open.length, "watch", "investigation is open", "investigations are open", "/forensic")], "Forensic Investigation");
  },
  health(d) {
    const m = (d && d.metrics) || {}, val = (k) => (m[k] && m[k].state === "OK" ? num(m[k].value) : 0), known = (k) => !!m[k] && m[k].state === "OK";
    const restricted = ["claims_pending", "unreconciled"].filter((k) => m[k] && m[k].state === "RESTRICTED").length;
    return finish([
      count(val("exceptions"), "urgent", "procurement exception is open", "procurement exceptions are open", "/health"),
      count(val("expiry"), "urgent", "stock lot has expired or expires soon", "stock lots have expired or expire soon", "/health"),
      count(val("low_stock"), "watch", "item is at or below its reorder level", "items are at or below their reorder level", "/health"),
      count(val("awaiting_approval"), "watch", "purchase request is waiting for approval", "purchase requests are waiting for approval", "/health"),
      count(val("maintenance_due"), "watch", "equipment maintenance job is due", "equipment maintenance jobs are due", "/health"),
      count(val("unreconciled"), "watch", "payer reconciliation has an unexplained difference", "payer reconciliations have an unexplained difference", "/health"),
      known("payables") && val("payables") > 0 ? item("clear", `Supplier payables outstanding: ${m.payables.value} ${d.currency || ""}.`.trim(), "/health") : null,
      restricted ? item("clear", "Claims figures are hidden from your role.") : null,
    ], `${d && d.facility ? d.facility : "this facility"}`);
  },
  general(ev) {
    const list = ev || [];
    const waiting = list.filter((e) => e.status === "UPLOADED").length;
    return finish([
      count(waiting, "watch", "evidence file is waiting for someone to verify it", "evidence files are waiting for someone to verify them", "/evidence"),
      count(list.filter((e) => ["INCOMPLETE", "CONFLICTING", "EXPIRED", "REJECTED", "DUPLICATE"].includes(e.status)).length, "urgent", "evidence file has a problem (incomplete, conflicting, expired, rejected or duplicate)", "evidence files have a problem (incomplete, conflicting, expired, rejected or duplicate)", "/evidence"),
    ], "the Evidence Vault");
  },
};
export const buildBrief = (ws, data) => BUILDERS[ws](data);

/** Latest period by end date, so the analysis brief covers the newest books. */
export function latestPeriod(periods) {
  const list = (periods || []).filter((p) => p && p.id);
  return list.reduce((a, b) => (!a || String(b.end_date || b.name) > String(a.end_date || a.name) ? b : a), null);
}

/**
 * Fetch and format the brief for one workspace through the caller's own permissions.
 * Returns { ok, items, source, asOf } or { ok:false, reason } where reason is "denied", "none" or "error" (with message).
 */
export async function fetchBrief(api, ws, role, hint = {}, now = () => new Date()) {
  if (ws === "general") {
    if (!has(role, PERMISSIONS.EVIDENCE_READ)) return { ok: false, reason: "denied", message: "Your role cannot see the Evidence Vault, so there is nothing to brief on here." };
  } else if (!briefAllowed(ws, role)) return { ok: false, reason: "denied", message: `Your role cannot open ${WORKSPACES[ws].label}.` };
  try {
    let data, source;
    if (ws === "cyber") { data = await api.cyOverview(); source = "Cybersecurity overview"; }
    else if (ws === "bizdev") { data = await api.bdOverview(); source = "Business Development overview"; }
    else if (ws === "grc") { data = await api.grcDashboard(); source = "GRC dashboard"; }
    else if (ws === "tax") { data = await api.taxOverview(); source = "Tax Compliance overview"; }
    else if (ws === "pubfin") { data = await api.pubfinOverview(); source = "Public Finance overview"; }
    else if (ws === "forensic") { data = await api.forensicCases(); source = "Forensic case list"; }
    else if (ws === "analysis") {
      const p = latestPeriod(await api.listPeriods());
      if (!p) return { ok: false, reason: "none", message: "There is no accounting period yet, so there is nothing to analyse." };
      data = await api.analysisOverview(p.id); source = `Financial Analysis overview, ${p.name}`;
    } else if (ws === "health") {
      const opts = await api.hcOptions(), fs = opts.facilities || [];
      if (!fs.length) return { ok: false, reason: "none", message: "No facility is available to you yet." };
      const f = fs.find((x) => x.id === hint.facilityId) || fs[0];
      data = await api.hcGet(`/facilities/${encodeURIComponent(f.id)}/dashboard`); source = `Health Centre dashboard, ${f.name}`;
    } else { data = await api.listEvidence(); source = "Evidence Vault"; }
    return { ok: true, items: buildBrief(ws, data), source, asOf: now().toISOString() };
  } catch (err) {
    if (err && (err.status === 403 || err.status === 401)) return { ok: false, reason: "denied", message: "The server did not allow this. Your access may have changed." };
    return { ok: false, reason: "error", message: (err && err.message) || "The brief could not be loaded." };
  }
}

// ------------------------------------------------------------------ answers
const STAGES = [["source_records", "Source records"], ["evidence", "Evidence"], ["journal", "Journal"], ["accounting_treatment", "Accounting treatment"], ["reporting_framework", "Reporting framework"]];
function stageState(it, key) {
  const s = it[key];
  if (key === "source_records") return { ok: Array.isArray(s) && s.length > 0, note: Array.isArray(s) && s.length ? `${plural(s.length, "record")}` : "No source record" };
  if (!s || s.available === false) return { ok: false, note: (s && s.note) || "Not available" };
  if (key === "evidence" && s.state && s.state !== "VERIFIED") return { ok: true, partial: true, note: `Evidence ${String(s.state).toLowerCase()}` };
  return { ok: true, note: key === "journal" && s.number ? s.number : "Linked" };
}
/** Compact, honest form of one AI answer: what was concluded, how sure, which links of the proof chain really exist. */
export function summariseAnswer(res) {
  if (!res) return null;
  if (res.grounded === false) {
    const r = res.refusal || {};
    return { grounded: false, headline: res.summary || "ASAVEXA AI could not answer that.", reason: r.reason || res.summary || "", suggestions: r.suggestions || [], items: [], limitations: res.limitations || [], disclosure: res.disclosure || "" };
  }
  const items = (res.items || []).slice(0, 5).map((it) => ({
    title: it.title || "", summary: (it.conclusion && it.conclusion.summary) || "", points: ((it.conclusion && it.conclusion.points) || []).slice(0, 3),
    confidence: it.confidence ? { level: it.confidence.level, score: it.confidence.score } : null,
    review: !!(it.human_review && it.human_review.required),
    thread: STAGES.map(([k, l]) => ({ key: k, label: l, ...stageState(it, k) })),
    severity: it.severity || null, verdict: it.verdict || null,
  }));
  return { grounded: true, headline: res.summary || "", items, more: Math.max(0, (res.items || []).length - items.length), limitations: (res.limitations || []).slice(0, 3), disclosure: res.disclosure || "",
    fingerprint: res.fingerprint ? String(res.fingerprint).slice(0, 12) : "", mode: res.mode || (res.interpreted_as && res.interpreted_as.mode) || "" };
}

export const newDock = () => ({ open: false, tab: "brief", ws: "general", brief: null, briefLoading: false, briefFor: "", question: "", asking: false, answer: null, askError: null, nonce: 0 });
