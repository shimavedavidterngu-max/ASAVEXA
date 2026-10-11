import { h } from "../lib/vdom.js";
import { Seal } from "../components/AiDock.js";
import { NAV, HERO, CAPABILITIES, WORKSPACES, ORG_TYPES, STEPS, TRUST, STATUS, ABOUT, FOOTER } from "../lib/landing.js";

/**
 * The public front page, shown to visitors who are not signed in.
 * Every button does something real: Sign in and Get Started open the sign-in screen, the others scroll to a section on this page.
 * The "proof thread" in the hero is an illustration and is labelled as one. It uses no real figures.
 * It draws itself in once, on the first paint (animate); later re-renders (opening the menu, say) must not replay it.
 */

function header({ menuOpen, onSignIn, onGetStarted, onJump, onToggleMenu }) {
  const jump = (id) => () => onJump(id);
  return h("header", { className: "ld-header", id: "ld-header" },
    h("div", { className: "ld-wrap ld-header-row" },
      h("button", { className: "ld-brand", id: "ld-brand", "aria-label": "ASAVEXA, back to the top", onClick: jump("top") },
        Seal({ size: 34 }), h("span", { className: "ld-brand-name" }, "ASAVEXA")),
      h("nav", { className: `ld-nav${menuOpen ? " is-open" : ""}`, id: "ld-nav", "aria-label": "Sections" },
        NAV.map((n) => h("button", { className: "ld-navlink", id: `ld-nav-${n.id}`, onClick: jump(n.id) }, n.label))),
      h("div", { className: "ld-actions" },
        h("button", { className: "ld-btn ld-btn-ghost", id: "ld-signin", onClick: () => onSignIn() }, "Sign In"),
        h("button", { className: "ld-btn ld-btn-gold", id: "ld-start-top", onClick: () => onGetStarted() }, "Get Started"),
        h("button", { className: "ld-burger", id: "ld-burger", "aria-expanded": menuOpen ? "true" : "false", "aria-controls": "ld-nav", "aria-label": menuOpen ? "Close the menu" : "Open the menu", onClick: () => onToggleMenu() },
          h("span", {}), h("span", {}), h("span", {})))));
}

/** The hero picture: one figure and the thread of proof behind it. A solid bead is a link that exists; a hollow bead is one that is missing. */
function proofThread(animate) {
  const beads = [
    { k: "report", label: "Reported figure", note: "Revenue for the period", state: "ok" },
    { k: "journal", label: "Journal", note: "Posted, with who approved it", state: "ok" },
    { k: "evidence", label: "Evidence", note: "Invoice, fingerprinted when stored", state: "ok" },
    { k: "bank", label: "Bank statement", note: "No document linked yet", state: "missing" },
  ];
  return h("figure", { className: `ld-thread${animate ? " is-animated" : ""}`, id: "ld-thread", "aria-label": "Example of a proof thread" },
    h("div", { className: "ld-thread-head" }, h("span", { className: "ld-thread-tag" }, "Example"), h("span", {}, "Sample figures, not real data")),
    h("ol", { className: "ld-beads" }, beads.map((b, i) => h("li", { className: `ld-bead is-${b.state}`, "data-bead": b.k, style: `--i:${i}` },
      h("span", { className: "ld-dot", "aria-hidden": "true" }),
      h("div", { className: "ld-bead-text" },
        h("strong", {}, b.label, b.state === "missing" ? h("span", { className: "ld-missing" }, " missing") : null),
        h("span", {}, b.note))))),
    h("figcaption", {}, "Every figure shows the links behind it, and says plainly which ones are not there yet."));
}

function hero({ onGetStarted, onJump, animate }) {
  return h("section", { className: "ld-hero", id: "ld-top", "aria-labelledby": "ld-h1" },
    h("div", { className: "ld-wrap ld-hero-grid" },
      h("div", { className: "ld-hero-copy" },
        h("div", { className: "ld-eyebrow" }, HERO.eyebrow),
        h("h1", { id: "ld-h1" }, HERO.headline),
        h("p", { className: "ld-lead" }, HERO.message),
        h("div", { className: "ld-cta-row" },
          h("button", { className: "ld-btn ld-btn-gold ld-btn-lg", id: "ld-start", onClick: () => onGetStarted() }, HERO.primary),
          h("button", { className: "ld-btn ld-btn-outline ld-btn-lg", id: "ld-explore", onClick: () => onJump("product") }, HERO.secondary)),
        h("p", { className: "ld-tagline" }, HERO.tagline)),
      proofThread(animate)));
}

const sectionHead = (key, eyebrow, title, intro) => h("div", { className: "ld-sechead" }, h("div", { className: "ld-eyebrow ld-eyebrow-dark" }, eyebrow), h("h2", { id: `ld-h-${key}` }, title), intro ? h("p", {}, intro) : null);

function product() {
  return h("section", { className: "ld-section", id: "ld-product", "aria-labelledby": "ld-h-product" },
    h("div", { className: "ld-wrap" },
      sectionHead("product", "Product", "What works today", "These are built and running. Each one connects to the same ledger, evidence and audit trail."),
      h("div", { className: "ld-grid ld-grid-4" }, CAPABILITIES.map((c) => h("article", { className: "ld-card", "data-cap": c.id }, h("h3", {}, c.title), h("p", {}, c.text))))));
}

function solutions() {
  return h("section", { className: "ld-section ld-alt", id: "ld-solutions", "aria-labelledby": "ld-h-solutions" },
    h("div", { className: "ld-wrap" },
      sectionHead("solutions", "Solutions", "Eight professional workspaces", "Each one sits on the same accounting ledger, Evidence Vault and audit trail."),
      h("div", { className: "ld-grid ld-grid-4" }, WORKSPACES.map((w) => h("article", { className: "ld-card ld-ws", "data-ws": w.id }, h("h3", {}, w.title), h("p", {}, w.text)))),
      h("div", { className: "ld-orgs" },
        h("h3", {}, "Designed for"),
        h("ul", {}, ORG_TYPES.map((t) => h("li", {}, t))),
        h("p", { className: "ld-fine" }, "These are the kinds of organisation the platform is designed for. They are not a list of customers."))));
}

function how() {
  return h("section", { className: "ld-section", id: "ld-how", "aria-labelledby": "ld-h-how" },
    h("div", { className: "ld-wrap" },
      sectionHead("how", "How it works", "From sign-up to a traceable report"),
      h("ol", { className: "ld-steps" }, STEPS.map((s) => h("li", { className: "ld-step", "data-step": String(s.n) }, h("span", { className: "ld-stepnum", "aria-hidden": "true" }, String(s.n)), h("div", {}, h("h3", {}, s.title), h("p", {}, s.text)))))));
}

function security() {
  return h("section", { className: "ld-section ld-dark", id: "ld-security", "aria-labelledby": "ld-h-security" },
    h("div", { className: "ld-wrap" },
      sectionHead("security", "Security", "Protections the product has today", "These describe what the software does. They are not a guarantee, and no system can promise to be impossible to breach."),
      h("div", { className: "ld-grid ld-grid-3" }, TRUST.map((t) => h("article", { className: "ld-card ld-card-dark", "data-trust": t.title }, h("h3", {}, t.title), h("p", {}, t.text)))),
      h("div", { className: "ld-status", id: "ld-status", role: "note" }, h("h3", {}, STATUS.title), h("ul", {}, STATUS.lines.map((l) => h("li", {}, l))))));
}

function about({ onGetStarted }) {
  return h("section", { className: "ld-section", id: "ld-about", "aria-labelledby": "ld-h-about" },
    h("div", { className: "ld-wrap ld-about" },
      h("div", {}, h("div", { className: "ld-eyebrow ld-eyebrow-dark" }, "About"), h("h2", { id: "ld-h-about" }, ABOUT.title), h("p", {}, ABOUT.text)),
      h("div", { className: "ld-final" }, h("h3", {}, "Ready to look at your own numbers?"), h("p", {}, "Create an account, set up an organisation, and open the workspace you need."),
        h("button", { className: "ld-btn ld-btn-gold ld-btn-lg", id: "ld-start-bottom", onClick: () => onGetStarted() }, "Get Started"))));
}

function footer({ onJump, onSignIn }) {
  return h("footer", { className: "ld-footer", id: "ld-footer" },
    h("div", { className: "ld-wrap ld-footer-grid" },
      h("div", {}, h("div", { className: "ld-brand-static" }, Seal({ size: 30 }), h("span", {}, "ASAVEXA")), h("p", { className: "ld-fine ld-on-dark" }, HERO.tagline)),
      h("div", {}, h("h4", {}, "Product"),
        h("ul", {}, FOOTER.product.map((l) => h("li", {}, h("button", { className: "ld-linkbtn", onClick: () => onJump(l.id) }, l.label))),
          h("li", {}, h("button", { className: "ld-linkbtn", id: "ld-foot-signin", onClick: () => onSignIn() }, "Sign In")))),
      h("div", {}, h("h4", {}, "Information"),
        h("ul", { id: "ld-unpublished" }, FOOTER.notPublished.map((n) => h("li", {}, h("span", {}, n.label, " "), h("span", { className: "ld-note" }, `(${n.note})`)))))),
    h("div", { className: "ld-wrap ld-legal", id: "ld-legal" }, FOOTER.disclosure));
}

export function Landing(p) {
  return h("div", { className: "ld", id: "landing" },
    h("a", { className: "ld-skip", href: "#ld-product", onClick: (e) => { e.preventDefault(); p.onJump("product"); } }, "Skip to the product"),
    header(p), h("main", { id: "ld-main" }, hero(p), product(), solutions(), how(), security(), about(p)), footer(p));
}
