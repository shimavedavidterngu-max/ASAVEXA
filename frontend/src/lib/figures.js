/**
 * Money and figure formatting for the ledger design system.
 *
 * Rules (the same ones the backend keeps):
 *  - An amount is a decimal STRING (or an integer / bigint). It is never parsed into a floating-point number, so 0.1 + 0.2 problems cannot happen.
 *  - Nothing is rounded. A figure shows the digits it was given; it is only padded with zeros up to a minimum number of decimals.
 *  - A currency is a three-letter code. Different currencies are never added together.
 *  - Anything that cannot be read is shown as an em dash and flagged, never as 0.
 * Pure functions, no DOM, so every rule is testable in plain Node.
 */
const DEC = /^(-?)(\d+)(?:\.(\d+))?$/;
const MINUS = "−"; // a real minus sign, which lines up with digits better than a hyphen

/** Split a decimal string / integer / bigint into { neg, int, frac }. Returns null when it is not an exact decimal. */
export function parseDecimal(v) {
  let s = v;
  if (typeof s === "bigint") s = s.toString();
  else if (typeof s === "number") { if (!Number.isSafeInteger(s)) return null; s = String(s); } // a fractional JS number is already inexact
  if (typeof s !== "string") return null;
  const m = DEC.exec(s.trim());
  if (!m) return null;
  const int = m[2].replace(/^0+(?=\d)/, "");
  const frac = m[3] || "";
  const zero = /^0*$/.test(int) && /^0*$/.test(frac);
  return { neg: m[1] === "-" && !zero, int, frac };
}

const group = (int) => int.replace(/\B(?=(\d{3})+(?!\d))/g, ",");

/** Format a number with thousands separators. opts.minFraction pads with zeros (default 2); digits are never dropped or rounded. */
export function formatDecimal(v, opts = {}) {
  const p = parseDecimal(v);
  if (!p) return { ok: false, text: "—", neg: false, int: "", frac: "" };
  const min = Number.isInteger(opts.minFraction) && opts.minFraction >= 0 ? opts.minFraction : 2;
  const frac = p.frac.length >= min ? p.frac : p.frac + "0".repeat(min - p.frac.length);
  const body = group(p.int) + (frac ? "." + frac : "");
  return { ok: true, neg: p.neg, int: group(p.int), frac, text: (p.neg ? MINUS : "") + body };
}

/**
 * An amount with its currency code, e.g. "NGN 1,234.50" or "NGN −1,234.50".
 * opts.negative = "paren" shows a negative as "NGN (1,234.50)", the usual statement convention.
 */
export function formatMoney(amount, currency, opts = {}) {
  const cur = typeof currency === "string" && /^[A-Z]{3}$/.test(currency) ? currency : null;
  const d = formatDecimal(amount, opts);
  if (!d.ok || !cur) return { ok: false, text: "—", currency: cur, neg: false, number: "—", reason: !d.ok ? "AMOUNT" : "CURRENCY" };
  const number = d.neg && opts.negative === "paren" ? `(${d.text.slice(1)})` : d.text;
  return { ok: true, text: `${cur} ${number}`, currency: cur, neg: d.neg, number };
}

/** Exact sum of decimal strings. Returns a decimal string, or null when any entry is not an exact decimal (or the list is empty). */
export function addDecimals(list) {
  if (!Array.isArray(list) || !list.length) return null;
  const parts = list.map(parseDecimal);
  if (parts.some((p) => !p)) return null;
  const scale = Math.max(...parts.map((p) => p.frac.length));
  let total = 0n;
  for (const p of parts) {
    const n = BigInt(p.int + p.frac.padEnd(scale, "0"));
    total += p.neg ? -n : n;
  }
  const neg = total < 0n;
  let digits = (neg ? -total : total).toString().padStart(scale + 1, "0");
  const int = scale ? digits.slice(0, digits.length - scale) : digits;
  const frac = scale ? digits.slice(digits.length - scale) : "";
  return (neg ? "-" : "") + int + (frac ? "." + frac : "");
}

/** Sum rows of { amount, currency } that share ONE currency. Mixed currencies are refused, never converted or added. */
export function sumSameCurrency(rows) {
  if (!Array.isArray(rows) || !rows.length) return { ok: false, reason: "EMPTY" };
  const cur = rows[0] && rows[0].currency;
  if (rows.some((r) => !r || r.currency !== cur)) return { ok: false, reason: "MIXED_CURRENCY" };
  const total = addDecimals(rows.map((r) => r.amount));
  if (total === null) return { ok: false, reason: "INVALID" };
  return { ok: true, total, currency: cur };
}

/** Compare two exact decimals: -1, 0 or 1, or null when either is not an exact decimal. */
export function compareDecimals(a, b) {
  const pa = parseDecimal(a), pb = parseDecimal(b);
  if (!pa || !pb) return null;
  const diff = addDecimals([a, pb.neg ? pb.int + (pb.frac ? "." + pb.frac : "") : "-" + pb.int + (pb.frac ? "." + pb.frac : "")]);
  if (diff === null) return null;
  const q = parseDecimal(diff);
  return /^0*$/.test(q.int + q.frac) ? 0 : q.neg ? -1 : 1;
}
