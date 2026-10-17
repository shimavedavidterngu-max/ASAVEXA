import { PERMISSIONS, ROLE_PERMISSIONS } from "./permissions.js";
import { fmt, isRealDate, noteProblem, words } from "./treasury.js";

/** Shared input checks for the records-and-arithmetic workspaces (Stage 33 onwards). No DOM, no network. The server enforces every rule; these only stop obvious mistakes early. */
export { fmt, isRealDate, noteProblem, words };
export const has = (role, perm) => !!(ROLE_PERMISSIONS[role] && ROLE_PERMISSIONS[role].includes(perm));
export const canRead = (role) => has(role, PERMISSIONS.AUDIT_READ);
export const clean = (v) => String(v == null ? "" : v).trim();
export const first = (...p) => p.find(Boolean) || "";
export const dateProblem = (v, what) => (isRealDate(clean(v)) ? "" : `${what} must be a real date written YYYY-MM-DD.`);
export const textProblem = (v, what, min) => (clean(v).length >= min ? "" : `${what} needs at least ${min} characters.`);
export const amt = (v) => clean(v).replace(/,/g, "");
/** An amount: ASCII digits, at most dp decimals (default 2), commas only as thousands separators; neg allows a leading minus. */
export function amountProblem(v, what, o = {}) {
  const dp = o.dp == null ? 2 : o.dp, digits = o.digits || 13;
  let t = clean(v); if (o.neg && t.startsWith("-")) t = t.slice(1);
  if (t.includes(",") && !/^\d{1,3}(,\d{3})+(\.\d+)?$/.test(t)) return `${what} must be a number such as 1500.00 (commas only between groups of three digits).`;
  const re = new RegExp(`^\\d{1,${digits}}(\\.\\d{1,${dp}})?$`);
  if (!re.test(t.replace(/,/g, ""))) return dp ? `${what} must be a number such as 1500.00 (at most ${dp} decimals).` : `${what} must be a whole number.`;
  return o.zeroOk || /[1-9]/.test(t) ? "" : `${what} must be more than zero.`;
}
export const amtNeg = (v) => amt(v);
export const wholeProblem = (v, what, lo, hi) => (/^\d{1,9}$/.test(clean(v)) && Number(clean(v)) >= lo && Number(clean(v)) <= hi ? "" : `${what} must be a whole number from ${lo} to ${hi}.`);
export const currencyProblem = (v) => (/^[A-Z]{3}$/.test(clean(v).toUpperCase()) ? "" : "The currency must be a three-letter code such as NGN.");
export const mkStatus = (map) => (s) => map[s] || { tone: "neutral", label: s ? words(s) : "—" };
export const ownWorkText = "You prepared this, so a different person must decide it.";
/** Integer cents from a plain two-decimal amount string (for the screen's early checks only). */
export const cents = (v) => { const [w, f = ""] = amt(v).split("."); return Number(w) * 100 + Number((f + "00").slice(0, 2)); };
