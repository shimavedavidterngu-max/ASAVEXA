import { PERMISSIONS, ROLE_PERMISSIONS } from "./permissions.js";
import { fmt, isRealDate, noteProblem, words } from "./treasury.js";

/**
 * Investments helpers (a register of holdings built from typed purchases, sales and prices; nothing is posted to a ledger and no market data is read). No DOM, no network.
 * The server enforces every rule and does all cost and gain arithmetic. These check input early, word things, and hide buttons that could not work.
 */
export { fmt, isRealDate, noteProblem, words };
const has = (role, perm) => !!(ROLE_PERMISSIONS[role] && ROLE_PERMISSIONS[role].includes(perm));
export const canRead = (role) => has(role, PERMISSIONS.AUDIT_READ);
export const canPrepare = (role) => has(role, PERMISSIONS.INVEST_PREPARE);
export const canApprove = (role) => has(role, PERMISSIONS.INVEST_APPROVE);

export const TABS = [["overview", "Overview"], ["holdings", "Holdings"]];
export const CLASS_TEXT = { EQUITY: "Equity (shares)", BOND: "Bond", FUND: "Fund", DEPOSIT: "Deposit", PROPERTY: "Property", OTHER: "Other" };
export const KIND_TEXT = { BUY: "Bought", SELL: "Sold" };
export const STATUS = {
  ACTIVE: { tone: "pass", label: "Active" }, CLOSED: { tone: "neutral", label: "Closed" },
  PENDING: { tone: "warn", label: "Waiting for approval" }, APPLIED: { tone: "pass", label: "Applied" }, REJECTED: { tone: "neutral", label: "Rejected" },
};
export const statusOf = (s) => STATUS[s] || { tone: "neutral", label: s ? words(s) : "—" };
export const ATTENTION_TONE = { SELLS_TO_APPROVE: "info", NO_PRICE: "warn", PRICES_STALE: "warn" };
export const who = (id, me) => (!id ? "—" : id === me ? "You" : String(id).slice(0, 8));

const clean = (v) => String(v == null ? "" : v).trim();
const first = (...p) => p.find(Boolean) || "";
const body = (b, ...problems) => { const p = first(...problems); return p ? { problem: p } : { body: b }; };
const dateProblem = (v, what) => (isRealDate(clean(v)) ? "" : `${what} must be a real date written YYYY-MM-DD.`);
const textProblem = (v, what, min) => (clean(v).length >= min ? "" : `${what} needs at least ${min} characters.`);
const PLAIN = /^\d{1,9}(\.\d{1,4})?$/;
const MONEY = /^\d{1,10}(\.\d{1,2})?$/;
const nonZero = (t) => /[1-9]/.test(t);
const plainProblem = (v, what) => { const t = clean(v); if (!PLAIN.test(t)) return `${what} must be a number such as 12.5 (at most four decimals).`; return nonZero(t) ? "" : `${what} must be more than zero.`; };
const amount = (v) => clean(v).replace(/,/g, "");
const feeProblem = (v) => (clean(v) && !MONEY.test(amount(v)) ? "The fee must be an amount such as 5.00 (at most two decimals), or left empty." : "");
/** Units as a whole number of 0.0001s, so two quantities can be compared without fractions. */
export const tenThousandths = (v) => { const [w, f = ""] = clean(v).split("."); return Number(w) * 10000 + Number((f + "0000").slice(0, 4)); };

export const EMPTY = {
  holding: { name: "", identifier: "", asset_class: "EQUITY", currency: "", account: "" },
  buy: { units: "", price: "", fee: "", traded_on: "", reference: "" },
  sell: { units: "", price: "", fee: "", traded_on: "", reference: "" },
  mark: { price: "", as_of: "", source: "" },
};

export function holdingPayload(f) {
  const cur = clean(f.currency).toUpperCase(), id = clean(f.identifier);
  const p = first(textProblem(f.name, "The holding name", 3), id && id.length < 2 ? "The identifier needs at least 2 characters when given." : "", f.asset_class ? "" : "Choose an asset class.",
    /^[A-Z]{3}$/.test(cur) ? "" : "The currency must be a three-letter code such as NGN.", textProblem(f.account, "The account or custodian", 2));
  if (p) return { problem: p };
  return { body: { name: clean(f.name), ...(id ? { identifier: id } : {}), asset_class: f.asset_class, currency: cur, account: clean(f.account) } };
}
const tradeParts = (f, what) => first(plainProblem(f.units, "The units"), plainProblem(f.price, "The price per unit"), feeProblem(f.fee), dateProblem(f.traded_on, `The ${what} date`), textProblem(f.reference, "The contract note or reference", 2));
const tradeBody = (f) => ({ units: clean(f.units), price: clean(f.price), ...(clean(f.fee) ? { fee: amount(f.fee) } : {}), traded_on: clean(f.traded_on), reference: clean(f.reference) });
export const buyPayload = (f) => body(tradeBody(f), tradeParts(f, "purchase"));
export function sellPayload(f, held) {
  const p = first(tradeParts(f, "sale"), PLAIN.test(clean(f.units)) && tenThousandths(f.units) > tenThousandths(held) ? `Only ${held} units held. You cannot sell more than that.` : "");
  return p ? { problem: p } : { body: tradeBody(f) };
}
export const markPayload = (f) => body({ price: clean(f.price), as_of: clean(f.as_of), source: clean(f.source) }, plainProblem(f.price, "The price per unit"), dateProblem(f.as_of, "The price date"), textProblem(f.source, "The source of the price", 2));
export const policyForm = (p) => ({ stale_days: String(p.stale_days) });
export function policyPayload(f) {
  const t = clean(f.stale_days);
  if (!(/^\d{1,3}$/.test(t) && Number(t) >= 7 && Number(t) <= 365)) return { problem: "The days before a price is out of date is a whole number from 7 to 365." };
  return { body: { stale_days: Number(t) } };
}
export const minNote = { reject: 10, close: 10 };

// ---- who sees which button ----
export const canTrade = (h, role) => canPrepare(role) && h.status === "ACTIVE";
export const canClose = (h, role) => canApprove(role) && h.status === "ACTIVE" && Number(h.units) === 0 && h.pending_sells === 0;
export const canDecideSell = (t, role, me) => canApprove(role) && t.kind === "SELL" && t.status === "PENDING" && t.by !== me;
export const ownWorkText = (what) => `You ${what}, so a different person must decide it.`;
