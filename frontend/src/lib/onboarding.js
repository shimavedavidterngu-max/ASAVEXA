import { PERMISSIONS, ROLE_PERMISSIONS } from "./permissions.js";

/**
 * The sign-up-to-dashboard journey. Pure logic, no network and no DOM.
 *
 * What the server really supports, and what this journey therefore does:
 *   register + sign in ........ POST /auth/register, /auth/login
 *   create an organisation .... POST /organisations (the creator becomes its Owner; the server decides the role)
 *   organisation details ...... PUT /organisation-profile (needs org:manage_settings)
 *   first accounting period ... POST /periods (needs period:manage)
 * What it does NOT have: invitations, email verification, password recovery, or a way to "switch on" a workspace.
 * So "join" tells the person to ask an administrator to add them, and workspace suggestions are suggestions only.
 * Nothing chosen here can raise anyone's permissions: roles are set only on the server.
 */
const has = (role, perm) => !!(ROLE_PERMISSIONS[role] && ROLE_PERMISSIONS[role].includes(perm));
export const canSetUp = (role) => has(role, PERMISSIONS.ORG_MANAGE_SETTINGS);
export const canOpenPeriod = (role) => has(role, PERMISSIONS.PERIOD_MANAGE);

export const CATEGORIES = [
  "Accounting or audit firm",
  "Business or SME",
  "NGO or nonprofit",
  "Church or faith-based organisation",
  "Government or public institution",
  "University or educational institution",
  "Health centre or healthcare facility",
  "Individual professional",
];

export const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

// ------------------------------------------------------------------ progress
export const STEPS = [
  { id: "account", label: "Account" },
  { id: "organisation", label: "Organisation" },
  { id: "settings", label: "Settings" },
  { id: "period", label: "First period" },
  { id: "workspaces", label: "Workspaces" },
];
/** Each step is done, current or still to do, given the one the person is on. */
export function progress(currentId) {
  const at = STEPS.findIndex((s) => s.id === currentId);
  return STEPS.map((s, i) => ({ ...s, state: at < 0 ? "todo" : i < at ? "done" : i === at ? "current" : "todo", number: i + 1 }));
}

// ------------------------------------------------------------------ organisation (step 2)
/** Name rules: trimmed, inner spaces collapsed, 2 to 120 characters, no control characters. */
export function cleanName(raw) {
  return String(raw == null ? "" : raw).replace(/[\u0000-\u001f\u007f]/g, " ").replace(/\s+/g, " ").trim();
}
export function validateCreate({ name, category }) {
  const errors = {};
  const n = cleanName(name);
  if (n.length < 2) errors.name = "Enter the organisation's name (at least 2 characters).";
  else if (n.length > 120) errors.name = "Keep the name to 120 characters or fewer.";
  if (!CATEGORIES.includes(category)) errors.category = "Choose the kind of organisation this is.";
  return { ok: Object.keys(errors).length === 0, errors, name: n };
}

// ------------------------------------------------------------------ settings (step 3)
const ISO = /^[A-Z]{3}$/;
/** The currency a country uses, from the server's own country list. Never guessed. */
export function currencyForCountry(countries, code) {
  const c = (countries || []).find((x) => x.code === code);
  return c ? c.currency : "";
}
export function validateSettings(f) {
  const errors = {};
  if (cleanName(f.legal_name).length < 2) errors.legal_name = "Enter the organisation's legal name.";
  if (!CATEGORIES.includes(f.organisation_type)) errors.organisation_type = "Choose the kind of organisation this is.";
  if (!String(f.country || "").trim()) errors.country = "Choose the country where the organisation operates.";
  const cur = String(f.base_currency || "").trim().toUpperCase();
  if (!ISO.test(cur)) errors.base_currency = "Enter a 3-letter currency code such as USD, EUR or NGN.";
  const m = Number(f.fiscal_year_start_month);
  if (!Number.isInteger(m) || m < 1 || m > 12) errors.fiscal_year_start_month = "Choose the month the financial year starts.";
  return { ok: Object.keys(errors).length === 0, errors };
}
/** What to send. The server replaces the whole profile, so existing fields are carried over and only these are changed. */
export function mergeProfile(existing, f) {
  const keep = {};
  for (const [k, v] of Object.entries(existing || {})) {
    if (["org_id", "updated_at", "updated_by"].includes(k)) continue;
    if (v === null || v === undefined || v === "") continue;
    keep[k] = v;
  }
  return {
    ...keep,
    legal_name: cleanName(f.legal_name),
    organisation_type: f.organisation_type,
    country: String(f.country).trim(),
    base_currency: String(f.base_currency).trim().toUpperCase(),
    fiscal_year_start_month: Number(f.fiscal_year_start_month),
  };
}

// ------------------------------------------------------------------ first period (step 4)
const pad = (n) => String(n).padStart(2, "0");
const iso = (d) => `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
/** The twelve months of the financial year that contains `today`, given the month it starts. */
export function fiscalYear(startMonth, today = new Date()) {
  const m = Number(startMonth) >= 1 && Number(startMonth) <= 12 ? Number(startMonth) : 1;
  const y = today.getUTCMonth() + 1 >= m ? today.getUTCFullYear() : today.getUTCFullYear() - 1;
  const start = `${y}-${pad(m)}-01`;
  const end = iso(new Date(Date.UTC(y + 1, m - 1, 0)));
  return { start, end, name: m === 1 ? `FY${y}` : `FY${y}/${y + 1}` };
}
export function validatePeriod({ name, start, end }) {
  const errors = {};
  if (cleanName(name).length < 1) errors.name = "Give the period a name, for example FY2026.";
  const ok = (d) => /^\d{4}-\d{2}-\d{2}$/.test(d || "") && !Number.isNaN(Date.parse(d));
  if (!ok(start)) errors.start = "Choose the first day of the period.";
  if (!ok(end)) errors.end = "Choose the last day of the period.";
  if (!errors.start && !errors.end && Date.parse(end) <= Date.parse(start)) errors.end = "The last day must be after the first day.";
  return { ok: Object.keys(errors).length === 0, errors };
}

// ------------------------------------------------------------------ workspaces (step 5)
/** Starting points by kind of organisation. Suggestions only: nothing is switched on or off, and access is decided by role. */
const SUGGEST = {
  "Accounting or audit firm": ["analysis", "tax", "forensic", "grc"],
  "Business or SME": ["analysis", "tax", "bizdev", "cyber"],
  "NGO or nonprofit": ["analysis", "public_finance", "grc"],
  "Church or faith-based organisation": ["analysis", "public_finance", "grc"],
  "Government or public institution": ["public_finance", "grc", "forensic", "tax"],
  "University or educational institution": ["analysis", "public_finance", "grc"],
  "Health centre or healthcare facility": ["health", "analysis", "public_finance", "cyber"],
  "Individual professional": ["analysis", "tax", "bizdev"],
};
export function suggestedWorkspaces(category, workspaces, role) {
  const ids = SUGGEST[category] || [];
  return ids.map((id) => (workspaces || []).find((w) => w.id === id)).filter(Boolean).map((w) => ({
    id: w.id, name: w.name, path: w.path, purpose: w.purpose || "", status: w.status || null,
    canOpen: !!w.path && (!w.permission || has(role, w.permission)),
  }));
}

// ------------------------------------------------------------------ resume
/** Where to pick up, worked out from what the server already holds, so closing the browser loses nothing. */
export function resumeStep({ profile, periods }) {
  const p = profile || {};
  if (!p.country || !p.base_currency || !p.fiscal_year_start_month || !p.organisation_type) return "settings";
  if (!Array.isArray(periods) || periods.length === 0) return "period";
  return "workspaces";
}
export const settingsComplete = (profile) => resumeStep({ profile, periods: [1] }) !== "settings";

// ------------------------------------------------------------------ the account id used to join
/** What an administrator needs to add this person: their account id and email. */
export function joinDetails(user) {
  return { id: user && user.id ? String(user.id) : "", email: user && user.email ? String(user.email) : "" };
}
