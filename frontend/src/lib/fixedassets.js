import { PERMISSIONS, ROLE_PERMISSIONS } from "./permissions.js";
import { fmt, isRealDate, noteProblem, words } from "./treasury.js";

/**
 * Fixed assets helpers (records and arithmetic on typed figures; nothing is posted to a ledger). No DOM, no network.
 * The server enforces every rule and does all depreciation arithmetic. These check input early, word things, and hide buttons that could not work.
 */
export { fmt, isRealDate, noteProblem, words };
const has = (role, perm) => !!(ROLE_PERMISSIONS[role] && ROLE_PERMISSIONS[role].includes(perm));
export const canRead = (role) => has(role, PERMISSIONS.AUDIT_READ);
export const canPrepare = (role) => has(role, PERMISSIONS.FIX_PREPARE);
export const canApprove = (role) => has(role, PERMISSIONS.FIX_APPROVE);

export const TABS = [["overview", "Overview"], ["assets", "Assets"]];
export const CATEGORY_TEXT = { LAND: "Land (not depreciated)", BUILDINGS: "Buildings", PLANT_AND_MACHINERY: "Plant and machinery", VEHICLES: "Vehicles", FURNITURE_AND_FITTINGS: "Furniture and fittings", IT_EQUIPMENT: "IT equipment", OTHER: "Other" };
export const RESULT_TEXT = { FOUND: "Found", MISSING: "Not found (missing)", DAMAGED: "Found damaged" };
export const STATUS = {
  PROPOSED: { tone: "warn", label: "Waiting for approval" }, ACTIVE: { tone: "pass", label: "Active" }, REJECTED: { tone: "neutral", label: "Rejected" },
  DISPOSAL_PENDING: { tone: "warn", label: "Disposal waiting for approval" }, DISPOSED: { tone: "neutral", label: "Disposed of" },
  UNREVIEWED: { tone: "warn", label: "Waiting for review" }, REVIEWED: { tone: "pass", label: "Reviewed" },
};
export const statusOf = (s) => STATUS[s] || { tone: "neutral", label: s ? words(s) : "—" };
export const ATTENTION_TONE = { MISSING_ASSETS: "fail", COUNTS_OVERDUE: "warn", ASSETS_TO_APPROVE: "info", DISPOSALS_TO_DECIDE: "info", COUNTS_TO_REVIEW: "info" };
export const who = (id, me) => (!id ? "—" : id === me ? "You" : String(id).slice(0, 8));

const clean = (v) => String(v == null ? "" : v).trim();
const first = (...p) => p.find(Boolean) || "";
const body = (b, ...problems) => { const p = first(...problems); return p ? { problem: p } : { body: b }; };
const dateProblem = (v, what) => (isRealDate(clean(v)) ? "" : `${what} must be a real date written YYYY-MM-DD.`);
const textProblem = (v, what, min) => (clean(v).length >= min ? "" : `${what} needs at least ${min} characters.`);
const MONEY = /^\d{1,12}(\.\d{1,2})?$/;
const amount = (v) => clean(v).replace(/,/g, "");
const moneyProblem = (v, what, zeroOk) => { const t = amount(v); if (!MONEY.test(t)) return `${what} must be an amount such as 1500.00 (at most two decimals).`; return zeroOk || /[1-9]/.test(t) ? "" : `${what} must be more than zero.`; };
/** Whole cents from a valid amount, so two amounts can be compared without fractions. */
export const cents = (v) => { const [w, f = ""] = amount(v).split("."); return Number(w) * 100 + Number((f + "00").slice(0, 2)); };
const ev = (f) => (clean(f.evidence_id) ? [clean(f.evidence_id)] : []);

export const EMPTY = {
  asset: { name: "", category: "VEHICLES", location: "", custodian_name: "", acquired_on: "", currency: "", cost: "", residual_value: "", life_months: "", serial_number: "", evidence_id: "" },
  disposal: { disposed_on: "", proceeds: "", reason: "" },
  count: { counted_on: "", result: "FOUND", note: "", evidence_id: "" },
  review: { note: "" },
};

export function assetPayload(f) {
  const land = f.category === "LAND", cur = clean(f.currency).toUpperCase(), life = clean(f.life_months), res = clean(f.residual_value);
  const p = first(textProblem(f.name, "The asset name", 3), textProblem(f.location, "The location", 2), textProblem(f.custodian_name, "The custodian", 2), dateProblem(f.acquired_on, "The acquisition date"),
    /^[A-Z]{3}$/.test(cur) ? "" : "The currency must be a three-letter code such as NGN.", moneyProblem(f.cost, "The cost"), res ? moneyProblem(res, "The residual value", true) : "",
    first(...(!land ? [/^\d{1,3}$/.test(life) && Number(life) >= 1 && Number(life) <= 600 ? "" : "The useful life is a whole number of months from 1 to 600."] : [life ? "Land is not depreciated. Leave the useful life empty." : ""])),
    !moneyProblem(f.cost, "x") && res && !moneyProblem(res, "x", true) && cents(res) >= cents(f.cost) ? "The residual value must be less than the cost." : "",
    land && res && cents(res) !== 0 ? "Land has no residual value in this register. Leave it at zero." : "", clean(f.serial_number) && clean(f.serial_number).length < 2 ? "The serial number needs at least 2 characters when given." : "");
  if (p) return { problem: p };
  return { body: { name: clean(f.name), category: f.category, location: clean(f.location), custodian_name: clean(f.custodian_name), acquired_on: clean(f.acquired_on), currency: cur, cost: amount(f.cost), residual_value: res ? amount(res) : "0",
    ...(land ? {} : { life_months: Number(life) }), ...(clean(f.serial_number) ? { serial_number: clean(f.serial_number) } : {}), evidence_ids: ev(f) } };
}
export const disposalPayload = (f) => body({ disposed_on: clean(f.disposed_on), proceeds: clean(f.proceeds) ? amount(f.proceeds) : "0", reason: clean(f.reason) },
  dateProblem(f.disposed_on, "The disposal date"), clean(f.proceeds) ? moneyProblem(f.proceeds, "The proceeds", true) : "", textProblem(f.reason, "The reason for disposal", 10));
export const countPayload = (f) => body({ counted_on: clean(f.counted_on), result: f.result, note: clean(f.note), evidence_ids: ev(f) }, dateProblem(f.counted_on, "The count date"), textProblem(f.note, "The count note", 10));
export const reviewPayload = (f) => body({ note: clean(f.note) }, textProblem(f.note, "A review note", 10));
export const policyForm = (p) => ({ count_days: String(p.count_days) });
export function policyPayload(f) {
  const t = clean(f.count_days);
  if (!(/^\d{2,3}$/.test(t) && Number(t) >= 30 && Number(t) <= 730)) return { problem: "The days between physical counts is a whole number from 30 to 730." };
  return { body: { count_days: Number(t) } };
}
export const minNote = { reject: 10, rejectDisposal: 10 };

// ---- who sees which button ----
export const canApproveAsset = (a, role, me) => canApprove(role) && a.status === "PROPOSED" && a.proposed_by !== me;
export const canDispose = (a, role) => canPrepare(role) && a.status === "ACTIVE";
export const canDecideDisposal = (a, role, me) => canApprove(role) && a.status === "DISPOSAL_PENDING" && !!a.disposal && a.disposal.proposed_by !== me;
export const canCount = (a, role) => canPrepare(role) && a.status === "ACTIVE";
export const canReviewCount = (c, role, me) => canApprove(role) && c.status === "UNREVIEWED" && c.counted_by !== me;
export const ownWorkText = (what) => `You ${what}, so a different person must decide it.`;
