import { h } from "../lib/vdom.js";
import { formatMoney, formatDecimal } from "../lib/figures.js";

/**
 * A figure in the ledger: the amount set in aligned (tabular) numerals, its currency code, and, only when proof data was supplied,
 * a numbered margin mark that opens the Proof Rail for that figure.
 *
 * No proof data means no mark. A plain figure never implies that evidence exists.
 * The mark's state is spelled out for screen readers and drawn as a different shape (filled, half, hollow, dotted), never by colour alone.
 */
export const PROOF_TEXT = { complete: "Proof complete", partial: "Proof incomplete", none: "No proof linked", unknown: "Proof not checked" };

function markGlyph(state) {
  const c = { cx: 9, cy: 9, r: 7, className: "pm-ring" };
  const inner = state === "complete" ? h("circle", { ...c, className: "pm-ring pm-fill" })
    : state === "partial" ? [h("circle", c), h("path", { d: "M9 2 A7 7 0 0 1 9 16 Z", className: "pm-half" })]
    : state === "none" ? h("circle", { ...c, className: "pm-ring pm-dash" })
    : h("circle", { ...c, className: "pm-ring pm-dots" });
  return h("svg", { className: "pm-glyph", viewBox: "0 0 18 18", width: 18, height: 18, "aria-hidden": "true", focusable: "false" }, inner);
}

/** A bare number (a count, a quantity). Aligned numerals, no currency. */
export function Num({ value, minFraction = 0, id }) {
  const f = formatDecimal(value, { minFraction });
  return h("span", { className: `num${f.ok ? "" : " is-invalid"}${f.neg ? " neg" : ""}`, id }, f.text);
}

/** The margin mark on its own (a button with a state glyph and a label that says the state in words). Used inside table cells as well as beside a Figure. */
export function ProofMark({ id, label, proof, mark, open = false, onToggle }) {
  if (!(proof && PROOF_TEXT[proof] && typeof onToggle === "function")) return null;
  return h("button", { type: "button", className: `pm pm-${proof}`, id: id ? `${id}-mark` : undefined, "aria-expanded": open ? "true" : "false", "aria-controls": open && id ? `${id}-rail` : undefined,
    "aria-label": `${PROOF_TEXT[proof]} for ${label || "this figure"}. ${open ? "Hide" : "Show"} the proof.`, onClick: (e) => { if (e && e.stopPropagation) e.stopPropagation(); onToggle(); },
    onKeydown: (e) => { if (e && e.stopPropagation) e.stopPropagation(); } },   // a mark inside a clickable table row must not also trigger the row
    markGlyph(proof), mark != null ? h("span", { className: "pm-n", "aria-hidden": "true" }, String(mark)) : null);
}

export function Figure({ id, label, amount, currency, proof, mark, open = false, onToggle, size = "md", negative }) {
  const m = formatMoney(amount, currency, { negative });
  const body = m.ok
    ? [h("span", { className: "fig-cur" }, m.currency), " ", h("span", { className: `num fig-amount${m.neg ? " neg" : ""}` }, m.number)]
    : [h("span", { className: "num fig-amount is-invalid", title: "This amount could not be read" }, m.number), h("span", { className: "sr-only" }, " Amount unavailable")];
  return h("span", { className: `fig fig-${size}${open ? " is-open" : ""}`, id, "data-proof": proof || undefined },
    body, ProofMark({ id, label, proof, mark, open, onToggle }));
}

/**
 * The app redraws a whole page after every change, which drops keyboard focus. After closing a proof panel, call this so focus goes back
 * to the mark that opened it (a keyboard user must not be thrown to the top of the page). Returns true when it found the mark.
 */
export function focusMark(figId, doc = globalThis.document) {
  const el = doc && typeof doc.getElementById === "function" ? doc.getElementById(`${figId}-mark`) : null;
  if (!el || typeof el.focus !== "function") return false;
  el.focus();
  return true;
}
