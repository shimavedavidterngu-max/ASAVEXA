import { h } from "../lib/vdom.js";
import { WORKSPACES, canAsk } from "../lib/aidock.js";

/**
 * ASAVEXA AI, docked on every signed-in page: "the Proof Lens".
 *  - The Seal: a navy disc ringed in gold with an A whose crossbar is a check mark. A gold drop shows how many things want attention.
 *  - The Margin Ledger: a ruled-paper panel with a red margin line. Brief entries are numbered like folios (f.1, f.2 ...).
 *  - The Proof Thread: each answer is a thread of beads. A solid bead is a link that really exists; a hollow bead is a link that is missing, and says so.
 * It draws what the server returned and nothing else.
 */
const TICKS = Array.from({ length: 48 }, (_, i) => {
  const a = (i / 48) * Math.PI * 2, long = i % 4 === 0, r1 = long ? 25.2 : 26.4, r2 = 28.4;
  return h("line", { x1: (32 + r1 * Math.sin(a)).toFixed(2), y1: (32 - r1 * Math.cos(a)).toFixed(2), x2: (32 + r2 * Math.sin(a)).toFixed(2), y2: (32 - r2 * Math.cos(a)).toFixed(2), "stroke-width": long ? 1.1 : 0.6 });
});

/** The Seal mark, reused as the launcher and in the panel header. */
export function Seal({ size = 56 }) {
  return h("svg", { className: "lens-seal-svg", viewBox: "0 0 64 64", width: size, height: size, "aria-hidden": "true", focusable: "false" },
    h("circle", { cx: 32, cy: 32, r: 31, className: "seal-disc" }),
    h("circle", { cx: 32, cy: 32, r: 29.6, className: "seal-rim", fill: "none" }),
    h("g", { className: "seal-ticks" }, TICKS),
    h("circle", { cx: 32, cy: 32, r: 22.5, className: "seal-inner", fill: "none" }),
    h("path", { d: "M20.5 44 L32 18.5 L43.5 44", className: "seal-a", fill: "none" }),
    h("path", { d: "M25.4 36.2 L30.4 40.8 L39.4 30.6", className: "seal-check", fill: "none" }));
}

const toneLabel = { urgent: "Needs action", watch: "Keep an eye on", clear: "For information" };
const hm = (iso) => { try { return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); } catch { return ""; } };

function briefView(d, ws, role, a) {
  const label = WORKSPACES[ws].label;
  if (d.briefLoading && !d.brief) return h("div", { className: "lens-skel", id: "lens-loading", role: "status", "aria-label": "Loading the brief" }, h("span"), h("span"), h("span"));
  const b = d.brief;
  if (!b) return h("div", { className: "lens-note" }, "Open the brief to see what is waiting.");
  if (!b.ok) {
    return h("div", { className: "lens-note", id: "lens-brief-problem", role: "status" },
      h("strong", {}, b.reason === "denied" ? "Not available to your role" : b.reason === "none" ? "Nothing to show yet" : "The brief could not be loaded"),
      h("p", {}, b.message || ""),
      b.reason === "error" ? h("button", { className: "lens-btn", id: "lens-retry", onClick: () => a.onRefresh() }, "Try again") : null);
  }
  return h("div", { id: "lens-brief" },
    h("ol", { className: "lens-entries" }, b.items.map((it, i) => h("li", { className: `lens-entry lens-${it.tone}`, id: `lens-entry-${i}`, "data-tone": it.tone },
      h("span", { className: "lens-folio", "aria-hidden": "true" }, `f.${i + 1}`),
      h("div", { className: "lens-entry-body" },
        h("span", { className: "lens-tone" }, toneLabel[it.tone]),
        h("div", { className: "lens-entry-text" }, it.text),
        it.link ? h("a", { className: "lens-open", href: `#${it.link}`, onClick: () => a.onNavigate(it.link) }, "Open the records ↗") : null)))),
    h("div", { className: "lens-meta", id: "lens-meta" }, `Source: ${b.source}. As of ${hm(b.asOf)}.`, " ",
      h("button", { className: "lens-link", id: "lens-refresh", onClick: () => a.onRefresh(), disabled: d.briefLoading }, d.briefLoading ? "Refreshing..." : "Refresh")),
    ws === "general" || !canAsk(role) ? null : h("div", { className: "lens-note lens-small" }, `This brief counts items in ${label}. It does not judge whether they are correct.`));
}

const stamp = (c) => (c ? h("span", { className: `lens-stamp lens-stamp-${String(c.level).toLowerCase()}`, title: `Confidence score ${c.score} out of 100` }, `${c.level} ${c.score}`) : null);

function threadView(thread) {
  return h("ol", { className: "lens-thread", "aria-label": "Proof thread" }, thread.map((s) => h("li", { className: `lens-bead ${s.ok ? (s.partial ? "is-partial" : "is-ok") : "is-missing"}`, "data-link": s.key },
    h("span", { className: "lens-bead-dot", "aria-hidden": "true" }),
    h("span", { className: "lens-bead-label" }, s.label, " ", h("span", { className: "lens-bead-state" }, s.ok ? (s.partial ? "(partly)" : "") : "(missing)")),
    h("span", { className: "lens-bead-note" }, s.note))));
}

function answerView(ans, a) {
  if (!ans) return null;
  if (!ans.grounded) {
    return h("div", { className: "lens-refusal", id: "lens-refusal", role: "status" },
      h("strong", {}, "ASAVEXA AI did not guess"), h("p", {}, ans.reason || ans.headline),
      ans.suggestions && ans.suggestions.length ? h("div", { className: "lens-chips" }, ans.suggestions.slice(0, 3).map((q) => h("button", { className: "lens-chip", onClick: () => a.onStarter(q) }, q))) : null);
  }
  return h("div", { id: "lens-answer" },
    h("h3", { className: "lens-headline", id: "lens-headline" }, ans.headline || "Answer"),
    ans.items.length === 0 ? h("div", { className: "lens-note" }, "Nothing matched in your records.") : null,
    ans.items.map((it, i) => h("article", { className: "lens-card", id: `lens-card-${i}` },
      h("div", { className: "lens-card-head" }, h("strong", {}, it.title || `Finding ${i + 1}`), stamp(it.confidence)),
      it.summary ? h("p", { className: "lens-summary" }, it.summary) : null,
      it.points.length ? h("ul", { className: "lens-points" }, it.points.map((p) => h("li", {}, p))) : null,
      threadView(it.thread),
      it.review ? h("div", { className: "lens-review" }, "A person must review this before anyone relies on it.") : null)),
    ans.more ? h("div", { className: "lens-note lens-small" }, `${ans.more} more result(s) are in the full view.`) : null,
    ans.limitations.length ? h("details", { className: "lens-limits" }, h("summary", {}, "Limits of this answer"), h("ul", {}, ans.limitations.map((l) => h("li", {}, l)))) : null,
    h("div", { className: "lens-meta" }, ans.fingerprint ? `Reference ${ans.fingerprint}. ` : "", h("a", { className: "lens-link", href: "#/ai", id: "lens-open-full", onClick: () => a.onNavigate("/ai") }, "Open the full ASAVEXA AI")));
}

function askView(d, ws, role, a) {
  if (!canAsk(role)) return h("div", { className: "lens-note", id: "lens-ask-locked" }, h("strong", {}, "Questions are not available to your role"), h("p", {}, "ASAVEXA AI answers from the ledger, which your role cannot read. The brief still works."));
  const starters = WORKSPACES[ws].starters;
  return h("div", { id: "lens-ask" },
    h("label", { className: "lens-label", for: "lens-q" }, "Ask about your own records"),
    h("div", { className: "lens-askrow" },
      h("input", { id: "lens-q", type: "text", maxlength: 500, value: d.question, placeholder: "e.g. Find unusual transactions.", autocomplete: "off",
        onInput: (e) => a.onQuestion(e.target.value), onKeydown: (e) => { if (e.key === "Enter") { e.preventDefault(); a.onAsk(); } } }),
      h("button", { className: "lens-btn lens-btn-primary", id: "lens-ask-btn", onClick: () => a.onAsk(), disabled: d.asking }, d.asking ? "Reading..." : "Ask")),
    h("div", { className: "lens-chips" }, starters.map((q) => h("button", { className: "lens-chip", onClick: () => a.onStarter(q), disabled: d.asking }, q))),
    d.askError ? h("div", { className: "lens-error", id: "lens-ask-error", role: "alert" }, d.askError) : null,
    d.asking ? h("div", { className: "lens-skel", role: "status", "aria-label": "Reading your records" }, h("span"), h("span"), h("span")) : null,
    answerView(d.answer, a));
}

/** The floating Seal, always present on signed-in pages. */
export function AiDock({ dock, role, workspace, urgent, a }) {
  const ws = WORKSPACES[workspace] ? workspace : "general";
  const label = WORKSPACES[ws].label;
  const badge = urgent > 0 ? h("span", { className: "lens-drop", id: "lens-drop", "aria-label": `${urgent} items need attention` }, urgent > 9 ? "9+" : String(urgent)) : null;
  const launcher = h("button", { className: `lens-launch${urgent > 0 ? " has-news" : ""}`, id: "lens-launch", "aria-expanded": dock.open ? "true" : "false", "aria-controls": "lens-panel", title: "ASAVEXA AI", onClick: () => a.onToggle() },
    Seal({ size: 56 }), badge, h("span", { className: "lens-sr" }, `ASAVEXA AI. ${dock.open ? "Close" : "Open"} the assistant for ${label}.`));
  if (!dock.open) return h("div", { className: "lens-root" }, launcher);
  const tab = dock.tab === "ask" ? "ask" : "brief";
  return h("div", { className: "lens-root is-open" },
    h("div", { className: "lens-scrim", onClick: () => a.onToggle() }),
    h("aside", { className: "lens-panel", id: "lens-panel", role: "complementary", "aria-label": "ASAVEXA AI" },
      h("header", { className: "lens-head" },
        h("div", { className: "lens-mark" }, Seal({ size: 40 })),
        h("div", { className: "lens-titles" }, h("div", { className: "lens-title" }, "ASAVEXA AI"), h("div", { className: "lens-sub", id: "lens-folio" }, `Proof Lens · ${label}`)),
        h("button", { className: "lens-x", id: "lens-close", "aria-label": "Close ASAVEXA AI", onClick: () => a.onToggle() }, "×")),
      h("div", { className: "lens-tabs", role: "tablist" },
        h("button", { role: "tab", id: "lens-tab-brief", "aria-selected": tab === "brief" ? "true" : "false", className: tab === "brief" ? "on" : "", onClick: () => a.onTab("brief") }, "Brief"),
        h("button", { role: "tab", id: "lens-tab-ask", "aria-selected": tab === "ask" ? "true" : "false", className: tab === "ask" ? "on" : "", onClick: () => a.onTab("ask") }, "Ask")),
      h("div", { className: `lens-body${tab === "brief" ? " is-brief" : ""}`, role: "tabpanel" }, tab === "brief" ? briefView(dock, ws, role, a) : askView(dock, ws, role, a)),
      h("footer", { className: "lens-foot", id: "lens-foot" }, "Rule-based and read-only. It uses no outside AI model, never changes your records, and shows only what your role may see.")));
}
