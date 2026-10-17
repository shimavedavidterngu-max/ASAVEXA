import { h } from "../lib/vdom.js";

/**
 * The Proof Rail: ASAVEXA's signature component. Opened from the mark beside a figure, it shows the thread of proof behind THAT figure:
 * source record, evidence, review, decision, authorised action, independent verification.
 *
 * Honesty rules, the same as EvidenceChain:
 *  - It never fetches, infers or invents a relationship. The caller passes what the server returned.
 *  - A step the caller passes as `null` means "checked, nothing is linked": shown as a hollow bead reading "Not linked yet".
 *  - A step the caller leaves out (undefined) means "not checked": shown as a dotted bead reading "Not checked". These are different claims.
 *  - State is always spelled out in words and drawn as a different SHAPE, never by colour alone.
 *  - A link is only drawn for an in-app route ("#/..."); anything else is shown as plain text.
 * Each sector passes its own `vocab` so the same rail speaks the language of the work (procurement, grants, funds, ...).
 */
export const STAGES = ["source", "evidence", "review", "decision", "action", "verification"];
export const DEFAULT_VOCAB = {
  source: "Source record", evidence: "Evidence", review: "Review", decision: "Decision", action: "Authorised action", verification: "Independent verification",
};
export const STATE_TEXT = { linked: "Linked", missing: "Not linked yet", pending: "In progress", unknown: "Not checked" };
const STATES = new Set(Object.keys(STATE_TEXT));

/** Turn what the caller has into one entry per stage. null -> missing, undefined -> unknown, an object -> its own state (default "linked"). */
export function normaliseSteps(input, order = STAGES) {
  const src = input && typeof input === "object" ? input : {};
  return order.map((key) => {
    const v = src[key];
    if (v === null) return { key, state: "missing" };
    if (v === undefined) return { key, state: "unknown" };
    if (typeof v !== "object") return { key, state: "unknown" };
    const state = STATES.has(v.state) ? v.state : v.state === undefined ? "linked" : "unknown";
    return { key, state, title: typeof v.title === "string" ? v.title : null, meta: typeof v.meta === "string" ? v.meta : null, href: typeof v.href === "string" && v.href.startsWith("#/") ? v.href : null };
  });
}

/** Counts and a plain sentence, e.g. "3 of 6 steps linked. 1 not linked yet. 2 not checked." */
export function railSummary(steps) {
  const n = { linked: 0, missing: 0, pending: 0, unknown: 0 };
  steps.forEach((s) => { n[s.state] += 1; });
  const parts = [`${n.linked} of ${steps.length} steps linked`];
  if (n.pending) parts.push(`${n.pending} in progress`);
  if (n.missing) parts.push(`${n.missing} not linked yet`);
  if (n.unknown) parts.push(`${n.unknown} not checked`);
  const complete = n.linked === steps.length;
  return { ...n, total: steps.length, complete, text: parts.join(". ") + "." };
}

/** What the figure's margin mark should say, from the steps: complete, partial (something linked) or none. Unchecked stays "unknown". */
export function proofState(steps) {
  const s = railSummary(steps);
  if (s.unknown === s.total) return "unknown";
  if (s.complete) return "complete";
  return s.linked + s.pending > 0 ? "partial" : "none";
}

/** Escape closes the rail. Returns true when it handled the key (so the caller can stop it reaching anything else). */
export function railKeydown(e, onClose) {
  if (e && e.key === "Escape" && typeof onClose === "function") { onClose(); return true; }
  return false;
}

/** A bead whose SHAPE carries the state: solid + tick, half, hollow dashed, dotted with a question mark. */
export function Bead({ state }) {
  const ring = { cx: 10, cy: 10, r: 8, className: "pr-ring" };
  const body = state === "linked" ? [h("circle", { ...ring, className: "pr-ring pr-fill" }), h("path", { d: "M6 10.4 L9 13.2 L14.2 7.2", className: "pr-tick", fill: "none" })]
    : state === "pending" ? [h("circle", ring), h("path", { d: "M10 2 A8 8 0 0 1 10 18 Z", className: "pr-half" })]
    : state === "missing" ? [h("circle", { ...ring, className: "pr-ring pr-dash" })]
    : [h("circle", { ...ring, className: "pr-ring pr-dots" }), h("text", { x: 10, y: 13.6, className: "pr-q", "text-anchor": "middle" }, "?")];
  return h("svg", { className: `pr-bead is-${state}`, viewBox: "0 0 20 20", width: 20, height: 20, "aria-hidden": "true", focusable: "false" }, ...body);
}

export function ProofRail({ id = "proof-rail", subject, steps, vocab = {}, sample = false, onClose }) {
  const list = Array.isArray(steps) && steps.length && steps[0] && steps[0].state ? steps : normaliseSteps(steps);
  const words = { ...DEFAULT_VOCAB, ...vocab };
  const sum = railSummary(list);
  return h("section", { className: `pr${sum.complete ? " is-complete" : ""}`, id, role: "region", tabindex: "-1", "aria-labelledby": `${id}-title`, onKeyDown: (e) => railKeydown(e, onClose) },
    h("header", { className: "pr-head" },
      h("div", {}, h("h3", { className: "pr-title", id: `${id}-title` }, "Proof behind ", h("span", { className: "pr-subject" }, subject || "this figure")),
        sample ? h("span", { className: "pr-sample" }, "Example, not real data") : null),
      typeof onClose === "function" ? h("button", { type: "button", className: "pr-close", id: `${id}-close`, "aria-label": "Close the proof panel", onClick: () => onClose() }, "Close") : null),
    h("p", { className: "pr-summary", id: `${id}-summary` }, sum.text),
    h("ol", { className: "pr-steps" }, list.map((s) => h("li", { className: `pr-step is-${s.state}`, "data-stage": s.key },
      Bead({ state: s.state }),
      h("div", { className: "pr-body" },
        h("strong", { className: "pr-label" }, words[s.key] || s.key),
        h("span", { className: "pr-state" }, STATE_TEXT[s.state]),
        s.title ? (s.href ? h("a", { className: "pr-link", href: s.href }, s.title) : h("span", { className: "pr-what" }, s.title)) : null,
        s.meta ? h("span", { className: "pr-meta" }, s.meta) : null)))));
}

/**
 * Opening the rail moves keyboard focus INTO it (so Tab continues through its links and the Close button, and a screen reader announces
 * "Proof behind ..."). Escape or Close then gives focus back to the mark (see focusMark in Figure.js). Returns true when it found the panel.
 */
export function focusRail(railId, doc = globalThis.document) {
  const el = doc && typeof doc.getElementById === "function" ? doc.getElementById(railId) : null;
  if (!el || typeof el.focus !== "function") return false;
  el.focus();
  return true;
}
