/** Pure helpers for organisation type and enabled workspaces (Stage 15). No DOM, no network.
 * The server decides who may change this and validates every value. This only words things, builds the request and decides which menu items to show.
 * Hiding a workspace removes a menu entry. It never grants or removes access: every action is still checked on the server. */

/** Menu path of each workspace in the server's catalogue (workspaces.py). A test pins this to the real catalogue and menu. */
export const WORKSPACE_PATHS = {
  analysis: "/analysis", forensic: "/forensic", grc: "/grc", tax: "/tax", public_finance: "/pubfin", health: "/health", cyber: "/cyber", bizdev: "/bizdev",
};
const PATH_TO_WS = Object.fromEntries(Object.entries(WORKSPACE_PATHS).map(([id, p]) => [p, id]));

/** `shown` is the server's list of shown workspace ids, or null when it is unknown or the organisation has not been configured: then everything is shown. */
export function filterNavByWorkspaces(items, shown) {
  if (!Array.isArray(shown)) return items;
  return items.filter((i) => !(i.path in PATH_TO_WS) || shown.includes(PATH_TO_WS[i.path]));
}
export const shownFor = (entity, orgId) => (entity && entity.org === orgId && entity.cfg && entity.cfg.configured && Array.isArray(entity.cfg.shown_workspaces) ? entity.cfg.shown_workspaces : null);

export const typeOptions = (catalog) => ((catalog && catalog.types) || []).map((t) => ({ code: t.code, label: t.label }));
export const typeOf = (catalog, code) => ((catalog && catalog.types) || []).find((t) => t.code === code) || null;
export const subtypeOptions = (catalog, code) => { const t = typeOf(catalog, code); return t ? t.subtypes : []; };
export const suggestedFor = (catalog, code, workspaces) => {
  const t = typeOf(catalog, code); const ids = new Set(t ? t.suggested_workspaces : []);
  return (workspaces || []).filter((w) => ids.has(w.id)).map((w) => w.id);
};

/** The legacy sign-up category (one of eight words) to a starting type, so an organisation that already chose one is not asked again from nothing. */
export const typeFromLegacy = (catalog, legacy) => ((catalog && catalog.types) || []).find((t) => t.legacy_category === legacy)?.code || "";

export function formFromConfig(cfg, catalog, workspaces, legacy) {
  if (cfg && cfg.configured) {
    return { entity_type: cfg.entity_type, subtype: cfg.subtype || "", custom_subtype: cfg.custom_subtype || "", enabled: [...cfg.enabled_workspaces], languages: (cfg.languages || []).join(", "), timezone: cfg.timezone || "", note: "" };
  }
  const t = typeFromLegacy(catalog, legacy);
  return { entity_type: t, subtype: "", custom_subtype: "", enabled: t ? suggestedFor(catalog, t, workspaces) : (workspaces || []).map((w) => w.id), languages: "", timezone: "", note: "" };
}
export const toggleWorkspace = (enabled, id) => (enabled.includes(id) ? enabled.filter((x) => x !== id) : [...enabled, id]);

export const parseLanguages = (s) => String(s || "").split(/[,\s]+/).map((x) => x.trim()).filter(Boolean);

export function configPayload(form, configured) {
  if (!form.entity_type) return { problem: "Choose the kind of organisation." };
  if (configured && !String(form.note || "").trim()) return { problem: "Say why you are changing how this organisation is set up." };
  const body = { entity_type: form.entity_type, subtype: form.subtype || null, custom_subtype: String(form.custom_subtype || "").trim() || null, enabled_workspaces: [...form.enabled],
    languages: parseLanguages(form.languages), timezone: String(form.timezone || "").trim() || null, note: String(form.note || "").trim() };
  return { body };
}

const FIELD = { entity_type: "Kind", subtype: "Subtype", custom_subtype: "Own description", enabled_workspaces: "Workspaces shown", languages: "Languages", timezone: "Time zone" };
const show = (v) => (Array.isArray(v) ? (v.length ? v.join(", ") : "none") : v === null || v === undefined || v === "" ? "not set" : String(v));
export function changeLines(entry) {
  return Object.entries((entry && entry.changes) || {}).map(([k, [a, b]]) => `${FIELD[k] || k}: ${show(a)} → ${show(b)}`);
}
export const hiddenCount = (cfg, workspaces) => (cfg && cfg.configured ? (workspaces || []).filter((w) => !cfg.shown_workspaces.includes(w.id)).length : 0);
