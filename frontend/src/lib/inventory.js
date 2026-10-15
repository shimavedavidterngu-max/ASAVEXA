import { PERMISSIONS, ROLE_PERMISSIONS } from "./permissions.js";
import { fmt, isRealDate, noteProblem, words } from "./treasury.js";

/**
 * Inventory helpers (a stock register built from typed receipts and issues; nothing is posted to a ledger). No DOM, no network.
 * The server enforces every rule and does all valuation arithmetic. These check input early, word things, and hide buttons that could not work.
 */
export { fmt, isRealDate, noteProblem, words };
const has = (role, perm) => !!(ROLE_PERMISSIONS[role] && ROLE_PERMISSIONS[role].includes(perm));
export const canRead = (role) => has(role, PERMISSIONS.AUDIT_READ);
export const canPrepare = (role) => has(role, PERMISSIONS.INV_PREPARE);
export const canApprove = (role) => has(role, PERMISSIONS.INV_APPROVE);

export const TABS = [["overview", "Overview"], ["items", "Items"]];
export const REASON_TEXT = { COUNT_DIFFERENCE: "Count difference", DAMAGE: "Damage", LOSS: "Loss", OTHER: "Other" };
export const DIRECTION_TEXT = { DECREASE: "Take stock off the book", INCREASE: "Add stock to the book" };
export const KIND_TEXT = { RECEIPT: "Received", ISSUE: "Issued", ADJUST_UP: "Adjustment up", ADJUST_DOWN: "Adjustment down" };
export const STATUS = {
  ACTIVE: { tone: "pass", label: "Active" }, DISCONTINUED: { tone: "neutral", label: "Discontinued" },
  PENDING: { tone: "warn", label: "Waiting for approval" }, APPLIED: { tone: "pass", label: "Applied" }, REJECTED: { tone: "neutral", label: "Rejected" },
};
export const statusOf = (s) => STATUS[s] || { tone: "neutral", label: s ? words(s) : "—" };
export const ATTENTION_TONE = { OUT_OF_STOCK: "fail", LOW_STOCK: "warn", ADJUSTMENTS_TO_APPROVE: "info", ITEMS_NOT_MOVING: "warn" };
export const who = (id, me) => (!id ? "—" : id === me ? "You" : String(id).slice(0, 8));

const clean = (v) => String(v == null ? "" : v).trim();
const first = (...p) => p.find(Boolean) || "";
const body = (b, ...problems) => { const p = first(...problems); return p ? { problem: p } : { body: b }; };
const dateProblem = (v, what) => (isRealDate(clean(v)) ? "" : `${what} must be a real date written YYYY-MM-DD.`);
const textProblem = (v, what, min) => (clean(v).length >= min ? "" : `${what} needs at least ${min} characters.`);
const MONEY = /^\d{1,10}(\.\d{1,2})?$/;
const amount = (v) => clean(v).replace(/,/g, "");
const moneyProblem = (v, what) => { const t = amount(v); if (!MONEY.test(t)) return `${what} must be an amount such as 150.00 (at most two decimals).`; return /[1-9]/.test(t) ? "" : `${what} must be more than zero.`; };
const MAX_QTY = 10000000;
const qtyText = (v) => clean(v).replace(/,/g, "");
const qtyProblem = (v, what, min = 1) => { const t = qtyText(v); return /^\d{1,8}$/.test(t) && Number(t) >= min && Number(t) <= MAX_QTY ? "" : `${what} must be a whole number from ${min} to ${MAX_QTY.toLocaleString("en-US")}.`; };

export const EMPTY = {
  item: { sku: "", name: "", unit: "", currency: "", reorder_level: "", location: "" },
  receive: { qty: "", unit_cost: "", moved_on: "", reference: "" },
  issue: { qty: "", moved_on: "", reference: "" },
  adjust: { direction: "DECREASE", qty: "", unit_cost: "", reason_kind: "COUNT_DIFFERENCE", reason: "" },
};

export function itemPayload(f) {
  const cur = clean(f.currency).toUpperCase(), ro = clean(f.reorder_level);
  const p = first(textProblem(f.sku, "The item code", 2), textProblem(f.name, "The item name", 3), textProblem(f.unit, "The unit", 1), /^[A-Z]{3}$/.test(cur) ? "" : "The currency must be a three-letter code such as NGN.",
    ro ? qtyProblem(ro, "The reorder level", 0) : "", textProblem(f.location, "The location", 2));
  if (p) return { problem: p };
  return { body: { sku: clean(f.sku), name: clean(f.name), unit: clean(f.unit), currency: cur, reorder_level: ro ? Number(qtyText(ro)) : 0, location: clean(f.location) } };
}
export const receivePayload = (f) => body({ qty: Number(qtyText(f.qty)), unit_cost: amount(f.unit_cost), moved_on: clean(f.moved_on), reference: clean(f.reference) },
  qtyProblem(f.qty, "The quantity"), moneyProblem(f.unit_cost, "The unit cost"), dateProblem(f.moved_on, "The date received"), textProblem(f.reference, "The reference (for example a delivery note number)", 2));
export const issuePayload = (f) => body({ qty: Number(qtyText(f.qty)), moved_on: clean(f.moved_on), reference: clean(f.reference) },
  qtyProblem(f.qty, "The quantity"), dateProblem(f.moved_on, "The date issued"), textProblem(f.reference, "The reference (for example an issue slip number)", 2));
export function adjustPayload(f, onHand) {
  const up = f.direction === "INCREASE", cost = clean(f.unit_cost);
  const p = first(qtyProblem(f.qty, "The quantity"), !up && /^\d{1,8}$/.test(qtyText(f.qty)) && Number(qtyText(f.qty)) > onHand ? `Only ${onHand} on hand. You cannot take off more than that.` : "",
    up && (onHand === 0 || cost) ? moneyProblem(f.unit_cost, "The unit cost" + (onHand === 0 ? " (needed when no stock is on hand)" : "")) : "", textProblem(f.reason, "The reason", 10));
  if (p) return { problem: p };
  return { body: { direction: f.direction, qty: Number(qtyText(f.qty)), ...(up && cost ? { unit_cost: amount(cost) } : {}), reason_kind: f.reason_kind, reason: clean(f.reason) } };
}
export const policyForm = (p) => ({ stale_days: String(p.stale_days) });
export function policyPayload(f) {
  const t = clean(f.stale_days);
  if (!(/^\d{2,3}$/.test(t) && Number(t) >= 30 && Number(t) <= 730)) return { problem: "The days without movement is a whole number from 30 to 730." };
  return { body: { stale_days: Number(t) } };
}
export const minNote = { reject: 10, discontinue: 10 };

// ---- who sees which button ----
export const canMove = (it, role) => canPrepare(role) && it.status === "ACTIVE";
export const canDiscontinue = (it, role) => canApprove(role) && it.status === "ACTIVE" && it.on_hand === 0 && it.pending_adjustments === 0;
export const canDecideAdjustment = (m, role, me) => canApprove(role) && m.status === "PENDING" && m.by !== me;
export const isAdjustment = (m) => m.kind === "ADJUST_UP" || m.kind === "ADJUST_DOWN";
export const ownWorkText = (what) => `You ${what}, so a different person must decide it.`;
