import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { Landing } from "../src/pages/Landing.js";
import { Login } from "../src/pages/Login.js";
import {
  LANDING_PATHS, isLandingPath, signedOutScreen, NAV, HERO, CAPABILITIES, WORKSPACES, ORG_TYPES, STEPS, TRUST, STATUS, FOOTER,
  FORBIDDEN_CLAIMS, allCopy,
} from "../src/lib/landing.js";

const appSource = readFileSync(new URL("../src/app.js", import.meta.url), "utf8");

const walk = (v, fn) => { if (!v || typeof v !== "object") return; fn(v); (v.children || []).forEach((c) => walk(c, fn)); };
const all = (v, pred) => { const out = []; walk(v, (n) => { if (pred(n)) out.push(n); }); return out; };
const byId = (v, id) => all(v, (n) => n.props && n.props.id === id)[0];
const text = (v) => { if (v == null || v === false) return ""; if (typeof v !== "object") return String(v); return (v.children || []).map(text).join(""); };

function page(over = {}) {
  const calls = [];
  const rec = (n) => (...a) => { calls.push([n, ...a]); };
  const vnode = Landing({ menuOpen: false, onSignIn: rec("signin"), onGetStarted: rec("start"), onJump: rec("jump"), onToggleMenu: rec("toggle"), ...over });
  return { vnode, calls };
}

describe("when the landing page is shown", () => {
  test("only on the home addresses, and only until the visitor chooses Sign in or Get Started", () => {
    assert.deepEqual(LANDING_PATHS, ["/", "/welcome"]);
    for (const p of ["/", "/welcome", "/welcome/", "", undefined, "/?x=1"]) assert.equal(isLandingPath(p), true, String(p));
    for (const p of ["/accounting", "/shared/abc", "/analysis", "/ai"]) assert.equal(isLandingPath(p), false, p);
    assert.equal(signedOutScreen({ path: "/", enteredAuth: false }), "landing");
    assert.equal(signedOutScreen({ path: "/welcome", enteredAuth: false }), "landing");
    assert.equal(signedOutScreen({ path: "/", enteredAuth: true }), "auth");
  });
  test("a deep link while signed out goes straight to sign-in so the visitor still arrives where they meant to", () => {
    assert.equal(signedOutScreen({ path: "/accounting", enteredAuth: false }), "auth");
    assert.equal(signedOutScreen({ path: "/forensic", enteredAuth: false }), "auth");
  });
});

describe("what the page says", () => {
  test("the headline and calls to action are exactly the ones in the spec", () => {
    assert.equal(HERO.headline, "Financial Truth. Backed by Evidence.");
    assert.equal(HERO.message, "Connect financial records, supporting evidence, controls and reporting in one traceable workspace.");
    assert.equal(HERO.primary, "Get Started");
    assert.equal(HERO.secondary, "Explore the Platform");
    const { vnode } = page();
    assert.equal(all(vnode, (n) => n.tag === "h1").length, 1);
    assert.equal(text(all(vnode, (n) => n.tag === "h1")[0]), HERO.headline);
  });
  test("no invented claims: no testimonials, certifications, partners, guarantees or performance figures", () => {
    const copy = allCopy();
    for (const re of FORBIDDEN_CLAIMS) assert.ok(!re.test(copy), `forbidden claim ${re} found`);
    assert.ok(!/\d+(\.\d+)?\s*(%|x faster|million|billion)/i.test(copy), "a performance figure appeared");
  });
  test("it says plainly that the platform is not yet audited, certified or professionally reviewed", () => {
    const s = STATUS.lines.join(" ");
    assert.match(s, /synthetic data/);
    assert.match(s, /not yet been independently audited/);
    assert.match(s, /certified/);
    assert.match(s, /licensed/);
    assert.match(s, /does not replace/);
    assert.ok(byId(page().vnode, "ld-status"));
  });
  test("contact details, privacy policy and terms are never invented: they are shown as not published yet", () => {
    assert.equal(FOOTER.notPublished.length, 3);
    for (const n of FOOTER.notPublished) assert.match(n.note, /not published yet|to be added/);
    const copy = allCopy();
    assert.ok(!/@[a-z0-9-]+\.[a-z]/i.test(copy), "an email address appeared");
    assert.ok(!/https?:\/\//i.test(copy), "a web address appeared");
    assert.ok(!/\+?\d[\d\s().-]{7,}\d/.test(copy), "a phone number appeared");
    const list = byId(page().vnode, "ld-unpublished");
    assert.match(text(list), /Privacy policy .*not published yet/);
    assert.match(text(list), /Terms of use .*not published yet/);
    assert.match(text(byId(page().vnode, "ld-legal")), /does not give legal, tax, audit or medical advice/);
  });
  test("it lists the eight professional workspaces, once each", () => {
    assert.equal(WORKSPACES.length, 8);
    assert.equal(new Set(WORKSPACES.map((w) => w.id)).size, 8);
    const cards = all(page().vnode, (n) => n.props && n.props["data-ws"]);
    assert.equal(cards.length, 8);
  });
  test("organisation types are described as design intent, not as a customer list", () => {
    assert.ok(ORG_TYPES.length >= 4);
    assert.match(text(page().vnode), /not a list of customers/);
  });
  test("how it works has the six steps in order", () => {
    assert.deepEqual(STEPS.map((s) => s.n), [1, 2, 3, 4, 5, 6]);
    assert.equal(all(page().vnode, (n) => n.props && n.props["data-step"]).length, 6);
  });
  test("security statements are about what the product does and promise nothing absolute", () => {
    assert.equal(TRUST.length, 6);
    assert.match(text(page().vnode), /not a guarantee/);
    assert.ok(!/impossible to breach|completely secure|fully secure/i.test(allCopy().replace(/no system can promise to be impossible to breach/i, "")));
  });
});

describe("every capability the page advertises exists in the app", () => {
  const routePaths = [...appSource.matchAll(/\{ path: "([^"]+)", name: "/g)].map((m) => m[1]);
  const navPaths = [...appSource.matchAll(/\{ path: "([^"]+)", label: /g)].map((m) => m[1]);
  test("each product capability points at a real route that is also in the menu", () => {
    assert.equal(CAPABILITIES.length, 8);
    for (const c of CAPABILITIES) { assert.ok(routePaths.includes(c.route), `${c.id}: ${c.route} is not a route`); assert.ok(navPaths.includes(c.route), `${c.id}: ${c.route} is not in the menu`); }
  });
  test("each workspace points at a real route that is also in the menu", () => {
    for (const w of WORKSPACES) { assert.ok(routePaths.includes(w.route), `${w.id}: ${w.route} is not a route`); assert.ok(navPaths.includes(w.route), `${w.id}: ${w.route} is not in the menu`); }
  });
  test("the welcome address is a route, so a signed-in visitor is redirected rather than shown Page not found", () => {
    assert.ok(routePaths.includes("/welcome"));
    assert.match(appSource, /authState\.token && router\.currentPath\(\) === "\/welcome"\) \{ router\.navigate\("\/"\)/);
  });
});

describe("every control on the page does something real", () => {
  test("every button has a click handler", () => {
    const buttons = all(page().vnode, (n) => n.tag === "button");
    assert.ok(buttons.length >= 15, `only ${buttons.length} buttons`);
    for (const b of buttons) assert.equal(typeof b.props.onClick, "function", `button "${text(b) || b.props.id}" has no handler`);
  });
  test("every link has a handler too, so none can change the address by accident", () => {
    for (const a of all(page().vnode, (n) => n.tag === "a")) assert.equal(typeof a.props.onClick, "function");
  });
  test("Sign In opens sign-in; Get Started (top, hero, bottom) opens registration", () => {
    const { vnode, calls } = page();
    byId(vnode, "ld-signin").props.onClick();
    byId(vnode, "ld-foot-signin").props.onClick();
    assert.deepEqual(calls.map((c) => c[0]), ["signin", "signin"]);
    calls.length = 0;
    for (const id of ["ld-start-top", "ld-start", "ld-start-bottom"]) byId(vnode, id).props.onClick();
    assert.deepEqual(calls.map((c) => c[0]), ["start", "start", "start"]);
  });
  test("Explore the Platform and every header link jump to a section that exists", () => {
    const { vnode, calls } = page();
    byId(vnode, "ld-explore").props.onClick();
    assert.deepEqual(calls.pop(), ["jump", "product"]);
    for (const n of NAV) {
      byId(vnode, `ld-nav-${n.id}`).props.onClick();
      assert.deepEqual(calls.pop(), ["jump", n.id]);
      assert.ok(byId(vnode, `ld-${n.id}`), `no section for ${n.id}`);
    }
    byId(vnode, "ld-brand").props.onClick();
    assert.deepEqual(calls.pop(), ["jump", "top"]);
    assert.ok(byId(vnode, "ld-top"));
  });
  test("footer links jump to real sections", () => {
    for (const l of FOOTER.product) assert.ok(byId(page().vnode, `ld-${l.id}`), l.id);
  });
});

describe("the mobile menu", () => {
  test("is closed by default, and the burger says so", () => {
    const { vnode } = page();
    assert.equal(byId(vnode, "ld-burger").props["aria-expanded"], "false");
    assert.ok(!byId(vnode, "ld-nav").props.className.includes("is-open"));
  });
  test("opens when asked, and the burger says so", () => {
    const { vnode } = page({ menuOpen: true });
    assert.equal(byId(vnode, "ld-burger").props["aria-expanded"], "true");
    assert.ok(byId(vnode, "ld-nav").props.className.includes("is-open"));
    assert.match(byId(vnode, "ld-burger").props["aria-label"], /Close/);
  });
  test("the burger toggles it", () => {
    const { vnode, calls } = page();
    byId(vnode, "ld-burger").props.onClick();
    assert.deepEqual(calls, [["toggle"]]);
  });
});

describe("the hero picture is honest", () => {
  test("it is labelled as an example with sample figures, and shows a missing link as missing", () => {
    const t = byId(page().vnode, "ld-thread");
    assert.match(text(t), /Example/);
    assert.match(text(t), /not real data/);
    assert.equal(all(t, (n) => n.props && n.props["data-bead"]).length, 4);
    const missing = all(t, (n) => n.props && n.props.className && n.props.className.includes("is-missing"));
    assert.equal(missing.length, 1);
    assert.match(text(missing[0]), /missing/);
  });
  test("the illustration contains no numbers that could be mistaken for real results", () => {
    assert.ok(!/\d/.test(text(byId(page().vnode, "ld-thread"))));
  });
});

describe("the thread animation", () => {
  test("plays on the first paint only, so opening the menu does not replay it", () => {
    assert.ok(byId(page({ animate: true }).vnode, "ld-thread").props.className.includes("is-animated"));
    assert.ok(!byId(page({ animate: false }).vnode, "ld-thread").props.className.includes("is-animated"));
    assert.ok(!byId(page().vnode, "ld-thread").props.className.includes("is-animated"));
    assert.match(appSource, /const animate = !uiState\.landingSeen; uiState\.landingSeen = true;/);
  });
});

describe("accessibility basics", () => {
  test("sections are labelled by their headings, and a skip link exists", () => {
    const { vnode } = page();
    for (const s of all(vnode, (n) => n.tag === "section")) {
      const id = s.props["aria-labelledby"];
      assert.ok(id && byId(vnode, id), `section ${s.props.id} points at a heading that does not exist (${id})`);
    }
    assert.ok(all(vnode, (n) => n.props && n.props.className === "ld-skip").length === 1);
  });
  test("the page has a main landmark and a footer", () => {
    const { vnode } = page();
    assert.equal(all(vnode, (n) => n.tag === "main").length, 1);
    assert.equal(all(vnode, (n) => n.tag === "footer").length, 1);
  });
});

describe("sign-in screen from the landing page", () => {
  test("shows a Back to the home page link only when it can go back", () => {
    const without = Login({ onSubmit: () => {}, onSwitchMode: () => {} });
    assert.ok(!byId(without, "login-home"));
    let went = 0;
    const withHome = Login({ onSubmit: () => {}, onSwitchMode: () => {}, onHome: () => { went += 1; } });
    const link = byId(withHome, "login-home");
    assert.ok(link);
    let prevented = false;
    link.props.onClick({ preventDefault: () => { prevented = true; } });
    assert.equal(went, 1);
    assert.equal(prevented, true);
  });
  test("the app returns to the landing page on sign-out, and to sign-in when a session expires or SSO returns", () => {
    assert.match(appSource, /function handleLogout\(\) \{[\s\S]*?uiState\.enteredAuth = false/);
    assert.match(appSource, /onUnauthenticated: \(\) => \{[\s\S]*?hadSession[\s\S]*?if \(hadSession\) uiState\.enteredAuth = true/);
    assert.match(appSource, /async function handleSsoReturn\(\) \{[\s\S]*?uiState\.enteredAuth = true/);
  });
});

describe("the side-by-side card fix", () => {
  test("cards in a flex or grid row are not pushed down by the stacking margin", () => {
    const css = readFileSync(new URL("../src/styles/design-system.css", import.meta.url), "utf8");
    assert.match(css, /\[style\*="display:flex"\] > \.card \+ \.card[\s\S]*?margin-top: 0/);
    assert.match(css, /\[style\*="display:grid"\] > \.card \+ \.card/);
  });
  test("the landing stylesheet is linked from the page", () => {
    assert.match(readFileSync(new URL("../index.html", import.meta.url), "utf8"), /styles\/landing\.css/);
  });
});
