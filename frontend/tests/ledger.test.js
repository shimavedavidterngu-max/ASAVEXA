import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { parseDecimal, formatDecimal, formatMoney, addDecimals, sumSameCurrency, compareDecimals } from "../src/lib/figures.js";
import { contrastRatio, hexToRgb } from "../src/lib/contrast.js";
import { Figure, Num, PROOF_TEXT, focusMark } from "../src/components/Figure.js";
import { ProofRail, normaliseSteps, railSummary, proofState, railKeydown, focusRail, STAGES, STATE_TEXT, Bead } from "../src/components/ProofRail.js";

const SRC = join(dirname(fileURLToPath(import.meta.url)), "..", "src");
const read = (p) => readFileSync(join(SRC, p), "utf8");
const text = (v) => JSON.stringify(v);
const find = (n, pred, out = []) => { if (n && typeof n === "object") { if (pred(n)) out.push(n); (n.children || []).forEach((c) => find(c, pred, out)); } return out; };

describe("figures: exact decimals, no floating point", () => {
  test("parseDecimal accepts exact decimals and refuses everything else", () => {
    assert.deepEqual(parseDecimal("1234.50"), { neg: false, int: "1234", frac: "50" });
    assert.deepEqual(parseDecimal("-0.05"), { neg: true, int: "0", frac: "05" });
    assert.deepEqual(parseDecimal(42), { neg: false, int: "42", frac: "" });
    assert.deepEqual(parseDecimal(12345678901234567890n), { neg: false, int: "12345678901234567890", frac: "" });
    for (const bad of [0.1, 1.5, NaN, Infinity, "1e5", "1,234.50", "", " ", "abc", "--1", "1.", ".5", null, undefined, {}, [], true]) assert.equal(parseDecimal(bad), null, `should refuse ${String(bad)}`);
  });
  test("negative zero is never shown as negative", () => {
    assert.equal(parseDecimal("-0").neg, false);
    assert.equal(parseDecimal("-0.00").neg, false);
    assert.equal(formatMoney("-0.00", "USD").text, "USD 0.00");
  });
  test("formatDecimal groups thousands, pads, and never rounds or drops digits", () => {
    assert.equal(formatDecimal("1234567.891").text, "1,234,567.891");
    assert.equal(formatDecimal("5").text, "5.00");
    assert.equal(formatDecimal("5", { minFraction: 0 }).text, "5");
    assert.equal(formatDecimal("0.1").text, "0.10");
    assert.equal(formatDecimal("999999999999999999999999.99").text, "999,999,999,999,999,999,999,999.99");
    assert.equal(formatDecimal("00012.3").text, "12.30");
    assert.equal(formatDecimal("-1234.5").text, "\u22121,234.50");
  });
  test("formatMoney needs a three-letter currency and shows an em dash, never zero, when it cannot read the amount", () => {
    assert.equal(formatMoney("1234.5", "NGN").text, "NGN 1,234.50");
    assert.equal(formatMoney("-1234.5", "NGN").text, "NGN \u22121,234.50");
    assert.equal(formatMoney("-1234.5", "NGN", { negative: "paren" }).text, "NGN (1,234.50)");
    const bad = formatMoney("abc", "NGN");
    assert.deepEqual([bad.ok, bad.text, bad.reason], [false, "\u2014", "AMOUNT"]);
    for (const c of ["ngn", "NG", "NGNN", "", null, undefined, 5]) { const r = formatMoney("1.00", c); assert.deepEqual([r.ok, r.text, r.reason], [false, "\u2014", "CURRENCY"]); }
    assert.equal(formatMoney(0.1, "USD").ok, false, "a JS fractional number is already inexact and is refused");
  });
  test("addDecimals is exact where floating point is not", () => {
    assert.equal(0.1 + 0.2 === 0.3, false);
    assert.equal(addDecimals(["0.1", "0.2"]), "0.3");
    assert.equal(addDecimals(["0.10", "0.20"]), "0.30");
    assert.equal(addDecimals(["1000000000000000000.01", "0.99"]), "1000000000000000001.00");
    assert.equal(addDecimals(["5", "-5"]), "0");
    assert.equal(addDecimals(["1.005", "-2"]), "-0.995");
    assert.equal(addDecimals(["-0.05", "0.01"]), "-0.04");
    assert.equal(addDecimals(["-100", "-0.5"]), "-100.5");
    assert.equal(addDecimals([]), null);
    assert.equal(addDecimals(["1", "x"]), null);
    assert.equal(addDecimals("1"), null);
  });
  test("different currencies are never added", () => {
    assert.deepEqual(sumSameCurrency([{ amount: "1.10", currency: "USD" }, { amount: "2.20", currency: "USD" }]), { ok: true, total: "3.30", currency: "USD" });
    assert.deepEqual(sumSameCurrency([{ amount: "1", currency: "USD" }, { amount: "1", currency: "NGN" }]), { ok: false, reason: "MIXED_CURRENCY" });
    assert.deepEqual(sumSameCurrency([]), { ok: false, reason: "EMPTY" });
    assert.deepEqual(sumSameCurrency([{ amount: "x", currency: "USD" }]), { ok: false, reason: "INVALID" });
    assert.deepEqual(sumSameCurrency([null]), { ok: false, reason: "MIXED_CURRENCY" });
  });
  test("compareDecimals orders exactly and refuses nonsense", () => {
    assert.equal(compareDecimals("0.30", "0.3"), 0);
    assert.equal(compareDecimals("0.3", "0.31"), -1);
    assert.equal(compareDecimals("-1", "-2"), 1);
    assert.equal(compareDecimals("100", "99.99"), 1);
    assert.equal(compareDecimals("x", "1"), null);
  });
  test("the money code never uses floating-point arithmetic", () => {
    const src = read("lib/figures.js").replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
    for (const banned of [/parseFloat/, /\.toFixed/, /Math\.round/, /Number\(/, /\*\s*100\b/]) assert.equal(banned.test(src), false, `found ${banned}`);
  });
});

describe("contrast maths", () => {
  test("matches the known WCAG values", () => {
    assert.ok(Math.abs(contrastRatio("#000000", "#ffffff") - 21) < 0.001);
    assert.ok(Math.abs(contrastRatio("#ffffff", "#ffffff") - 1) < 0.001);
    assert.ok(Math.abs(contrastRatio("#767676", "#ffffff") - 4.54) < 0.01, "#767676 on white is the well-known 4.54:1");
    assert.equal(contrastRatio("nope", "#fff"), null);
    assert.deepEqual(hexToRgb("#0b5c56"), [11, 92, 86]);
  });
});

describe("the colour tokens in the real stylesheets, measured", () => {
  const ds = read("styles/design-system.css"), lg = read("styles/ledger.css");
  const tok = (css, from, name) => { const i = css.indexOf(from); assert.ok(i >= 0, `${from} not found`); const m = new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`).exec(css.slice(i)); assert.ok(m, `${name} not found after ${from}`); return m[1]; };
  const light = { "paper-0": tok(ds, ":root {", "paper-0"), "paper-50": tok(ds, ":root {", "paper-50"), "paper-100": tok(ds, ":root {", "paper-100"), ledger: tok(lg, ":root {", "ledger-paper") };
  const dark = { "paper-0": tok(ds, ':root[data-theme="dark"] {', "paper-0"), "paper-50": tok(ds, ':root[data-theme="dark"] {', "paper-50"), "paper-100": tok(ds, ':root[data-theme="dark"] {', "paper-100"), ledger: tok(lg, ':root[data-theme="dark"] {', "ledger-paper") };
  const sectors = [...lg.matchAll(/\[data-sector="([a-z]+)"\]\s*\{\s*--accent-l:\s*(#[0-9a-fA-F]{6});\s*--accent-d:\s*(#[0-9a-fA-F]{6});/g)].map((m) => ({ name: m[1], l: m[2], d: m[3] }));
  const def = { name: "default", l: tok(lg, ":root {", "accent-l"), d: tok(lg, ":root {", "accent-d") };
  const lightInk = { "ink-700": tok(ds, ":root {", "ink-700"), "ink-500": tok(ds, ":root {", "ink-500"), "ink-900": tok(ds, ":root {", "ink-900") };
  const darkInk = { "ink-700": tok(ds, ':root[data-theme="dark"] {', "ink-700"), "ink-500": tok(ds, ':root[data-theme="dark"] {', "ink-500"), "ink-900": tok(ds, ':root[data-theme="dark"] {', "ink-900") };

  test("every sector the plan names has an accent pair", () => {
    assert.deepEqual(sectors.map((s) => s.name).sort(), ["accounting", "church", "government", "health", "ngo", "procurement", "school", "university"]);
  });
  test("accent text on every light surface is at least 4.5:1, and white on the accent is too", () => {
    for (const s of [def, ...sectors]) {
      for (const [n, bg] of Object.entries(light)) assert.ok(contrastRatio(s.l, bg) >= 4.5, `${s.name} ${s.l} on ${n} ${bg} = ${contrastRatio(s.l, bg).toFixed(2)}`);
      assert.ok(contrastRatio("#ffffff", s.l) >= 4.5, `white on ${s.name} = ${contrastRatio("#ffffff", s.l).toFixed(2)}`);
    }
  });
  test("accent text on every dark surface is at least 4.5:1, and dark text on the accent is too", () => {
    for (const s of [def, ...sectors]) {
      for (const [n, bg] of Object.entries(dark)) assert.ok(contrastRatio(s.d, bg) >= 4.5, `${s.name} ${s.d} on dark ${n} ${bg} = ${contrastRatio(s.d, bg).toFixed(2)}`);
      assert.ok(contrastRatio("#10151c", s.d) >= 4.5, `dark ink on ${s.name} = ${contrastRatio("#10151c", s.d).toFixed(2)}`);
    }
  });
  test("the secondary text colours used by the ledger components are at least 4.5:1 in both themes", () => {
    for (const [n, c] of Object.entries(lightInk)) for (const [b, bg] of Object.entries(light)) assert.ok(contrastRatio(c, bg) >= 4.5, `light ${n} ${c} on ${b} = ${contrastRatio(c, bg).toFixed(2)}`);
    for (const [n, c] of Object.entries(darkInk)) for (const [b, bg] of Object.entries(dark)) assert.ok(contrastRatio(c, bg) >= 4.5, `dark ${n} ${c} on ${b} = ${contrastRatio(c, bg).toFixed(2)}`);
  });
  test("the state colours used for mark and bead shapes are at least 3:1 (non-text graphics) on the light surfaces", () => {
    for (const n of ["status-pass", "status-warn", "status-fail"]) { const c = tok(ds, ":root {", n); for (const [b, bg] of Object.entries(light)) assert.ok(contrastRatio(c, bg) >= 3, `${n} ${c} on ${b} = ${contrastRatio(c, bg).toFixed(2)}`); }
  });
  test("the state colours for marks and beads are at least 3:1 on the dark surfaces too", () => {
    const dk = (name) => tok(lg, ':root[data-theme="dark"] {', name);
    for (const n of ["mark-pass", "mark-warn", "mark-fail"]) { const c = dk(n); for (const [b, bg] of Object.entries(dark)) assert.ok(contrastRatio(c, bg) >= 3, `${n} ${c} on dark ${b} = ${contrastRatio(c, bg).toFixed(2)}`); }
  });
});

describe("the font is real, licensed and wired in", () => {
  test("the Fraunces file exists, is a WOFF2 file, and ships with its licence", () => {
    const f = join(SRC, "fonts", "fraunces-latin-600-normal.woff2");
    assert.ok(existsSync(f));
    assert.equal(readFileSync(f).subarray(0, 4).toString("latin1"), "wOF2");
    assert.ok(statSync(f).size > 5000 && statSync(f).size < 60000);
    const lic = read("fonts/Fraunces-OFL.txt");
    assert.match(lic, /SIL OPEN FONT LICENSE Version 1\.1/);
    assert.match(lic, /Fraunces Project Authors/);
  });
  test("ledger.css declares it with font-display: swap and never fakes bold or italic from it", () => {
    const css = read("styles/ledger.css");
    assert.match(css, /@font-face\s*\{[^}]*font-family:\s*"Fraunces"[^}]*font-weight:\s*600[^}]*font-display:\s*swap[^}]*fraunces-latin-600-normal\.woff2/);
    assert.match(css, /font-synthesis:\s*none/);
  });
  test("index.html loads ledger.css right after the design system and before the page styles", () => {
    const html = readFileSync(join(SRC, "..", "index.html"), "utf8");
    const at = (n) => html.indexOf(n);
    assert.ok(at("design-system.css") >= 0 && at("ledger.css") > at("design-system.css") && at("ledger.css") < at("landing.css"));
  });
  test("the page does not ask a third-party host for fonts", () => {
    for (const f of ["styles/ledger.css", "styles/design-system.css"]) assert.equal(/https?:\/\//.test(read(f)), false, f);
  });
});

describe("Figure", () => {
  test("shows the currency and aligned amount, and no mark when there is no proof data", () => {
    const v = Figure({ id: "f1", label: "Revenue", amount: "1234567.5", currency: "NGN" });
    assert.match(text(v), /1,234,567\.50/);
    assert.equal(find(v, (n) => n.tag === "button").length, 0, "a plain figure must not imply evidence");
    assert.equal(find(v, (n) => /\bnum\b/.test(n.props.className || "")).length, 1);
  });
  test("a mark needs both a proof state and a handler", () => {
    assert.equal(find(Figure({ id: "f", label: "x", amount: "1", currency: "USD", proof: "complete" }), (n) => n.tag === "button").length, 0);
    assert.equal(find(Figure({ id: "f", label: "x", amount: "1", currency: "USD", proof: "bogus", onToggle() {} }), (n) => n.tag === "button").length, 0);
    assert.equal(find(Figure({ id: "f", label: "x", amount: "1", currency: "USD", proof: "complete", onToggle() {} }), (n) => n.tag === "button").length, 1);
  });
  test("the mark spells out its state, names the figure, and reports open or closed", () => {
    for (const st of Object.keys(PROOF_TEXT)) {
      const closed = find(Figure({ id: "f", label: "Revenue", amount: "1", currency: "USD", proof: st, mark: 3, onToggle() {} }), (n) => n.tag === "button")[0];
      assert.equal(closed.props["aria-expanded"], "false");
      assert.equal(closed.props["aria-controls"], undefined, "no controls reference to a panel that is not there");
      assert.match(closed.props["aria-label"], new RegExp(`^${PROOF_TEXT[st]} for Revenue\\. Show the proof\\.$`));
      const open = find(Figure({ id: "f", label: "Revenue", amount: "1", currency: "USD", proof: st, mark: 3, open: true, onToggle() {} }), (n) => n.tag === "button")[0];
      assert.equal(open.props["aria-expanded"], "true");
      assert.equal(open.props["aria-controls"], "f-rail");
      assert.match(open.props["aria-label"], /Hide the proof\.$/);
    }
  });
  test("the mark's number is hidden from screen readers because the label already says everything", () => {
    const b = find(Figure({ id: "f", label: "x", amount: "1", currency: "USD", proof: "none", mark: 2, onToggle() {} }), (n) => n.tag === "button")[0];
    assert.equal(find(b, (n) => n.props["aria-hidden"] === "true" && n.props.className === "pm-n").length, 1);
  });
  test("each state is a different shape, not only a different colour", () => {
    const shape = (st) => text(find(Figure({ id: "f", label: "x", amount: "1", currency: "USD", proof: st, onToggle() {} }), (n) => n.tag === "svg"));
    const shapes = Object.keys(PROOF_TEXT).map(shape);
    assert.equal(new Set(shapes).size, 4);
  });
  test("an unreadable amount is an em dash with a spoken warning, never zero", () => {
    const v = Figure({ id: "f", label: "x", amount: "n/a", currency: "USD" });
    assert.match(text(v), /\u2014/);
    assert.match(text(v), /Amount unavailable/);
    assert.equal(/0\.00/.test(text(v)), false);
    assert.match(text(Figure({ id: "f", label: "x", amount: "1.00", currency: "usd" })), /Amount unavailable/);
  });
  test("a negative figure is marked so it can be styled, and uses a real minus sign", () => {
    const v = Figure({ id: "f", label: "x", amount: "-5", currency: "USD" });
    assert.match(text(v), /\u22125\.00/);
    assert.equal(find(v, (n) => /\bneg\b/.test(n.props.className || "")).length, 1);
  });
  test("Num is aligned and handles a count", () => {
    assert.match(text(Num({ value: "1234", minFraction: 0 })), /1,234/);
    assert.match(text(Num({ value: "oops" })), /is-invalid/);
  });
});

describe("ProofRail", () => {
  const full = { source: { title: "Journal JE-104", href: "#/accounting" }, evidence: { title: "Invoice 8841", meta: "Fingerprinted 2026-03-02", href: "#/evidence" }, review: { state: "pending", title: "Waiting for second reviewer" }, decision: null, action: undefined };
  test("null means checked and not linked; a missing key means not checked; they read differently", () => {
    const s = normaliseSteps(full);
    assert.deepEqual(s.map((x) => x.state), ["linked", "linked", "pending", "missing", "unknown", "unknown"]);
    assert.deepEqual(s.map((x) => x.key), STAGES);
    assert.notEqual(STATE_TEXT.missing, STATE_TEXT.unknown);
  });
  test("an unrecognised state is treated as not checked, never as linked", () => {
    assert.equal(normaliseSteps({ source: { state: "verified!!" } })[0].state, "unknown");
    assert.equal(normaliseSteps({ source: "yes" })[0].state, "unknown");
    assert.equal(normaliseSteps({ source: {} })[0].state, "linked");
  });
  test("garbage input never throws and claims nothing", () => {
    for (const bad of [undefined, null, 5, "x", [], () => {}]) assert.ok(normaliseSteps(bad).every((s) => s.state === "unknown"));
  });
  test("only in-app hash links are drawn as links", () => {
    const s = normaliseSteps({ source: { title: "a", href: "https://evil.example/x" }, evidence: { title: "b", href: "javascript:alert(1)" }, review: { title: "c", href: "#/evidence" } });
    assert.deepEqual(s.slice(0, 3).map((x) => x.href), [null, null, "#/evidence"]);
    const v = ProofRail({ id: "r", subject: "s", steps: { source: { title: "a", href: "https://evil.example/x" }, review: { title: "c", href: "#/evidence" } } });
    assert.deepEqual(find(v, (n) => n.tag === "a").map((n) => n.props.href), ["#/evidence"]);
  });
  test("the summary counts each state and says so in words", () => {
    const sm = railSummary(normaliseSteps(full));
    assert.deepEqual([sm.linked, sm.pending, sm.missing, sm.unknown, sm.total, sm.complete], [2, 1, 1, 2, 6, false]);
    assert.equal(sm.text, "2 of 6 steps linked. 1 in progress. 1 not linked yet. 2 not checked.");
    assert.equal(railSummary(normaliseSteps(Object.fromEntries(STAGES.map((k) => [k, { title: k }])))).complete, true);
  });
  test("the figure's mark state follows the steps", () => {
    assert.equal(proofState(normaliseSteps({})), "unknown");
    assert.equal(proofState(normaliseSteps(Object.fromEntries(STAGES.map((k) => [k, {}])))), "complete");
    assert.equal(proofState(normaliseSteps(full)), "partial");
    assert.equal(proofState(normaliseSteps(Object.fromEntries(STAGES.map((k) => [k, null])))), "none");
    assert.equal(proofState(normaliseSteps({ source: null })), "none", "one step checked and empty, the rest not checked: nothing is linked");
  });
  test("renders one step per stage, each with its state in words and a distinct bead shape", () => {
    const v = ProofRail({ id: "r1", subject: "Revenue, March", steps: full, onClose() {} });
    assert.equal(find(v, (n) => /\bpr-step\b/.test(n.props.className || "")).length, 6);
    for (const w of ["Linked", "In progress", "Not linked yet", "Not checked"]) assert.match(text(v), new RegExp(w));
    const shapes = ["linked", "pending", "missing", "unknown"].map((s) => text(Bead({ state: s })));
    assert.equal(new Set(shapes).size, 4);
    assert.equal(v.props.role, "region");
    assert.equal(v.props["aria-labelledby"], "r1-title");
  });
  test("each sector can speak its own vocabulary", () => {
    const v = ProofRail({ id: "r", subject: "PO-17", steps: {}, vocab: { source: "Purchase request", action: "Payment", verification: "Three-way match" } });
    for (const w of ["Purchase request", "Payment", "Three-way match", "Evidence"]) assert.match(text(v), new RegExp(w));
  });
  test("an example is labelled as an example", () => {
    assert.match(text(ProofRail({ id: "r", steps: {}, sample: true })), /Example, not real data/);
    assert.equal(/Example, not real data/.test(text(ProofRail({ id: "r", steps: {} }))), false);
  });
  test("Escape closes it and is handled; other keys are not", () => {
    let closed = 0;
    assert.equal(railKeydown({ key: "Escape" }, () => { closed += 1; }), true);
    assert.equal(railKeydown({ key: "Enter" }, () => { closed += 1; }), false);
    assert.equal(railKeydown({ key: "Escape" }, undefined), false);
    assert.equal(closed, 1);
    const v = ProofRail({ id: "r", steps: {}, onClose: () => { closed += 1; } });
    v.props.onKeyDown({ key: "Escape" });
    find(v, (n) => n.tag === "button")[0].props.onClick();
    assert.equal(closed, 3);
  });
  test("the close button has a name and only appears when a handler is given", () => {
    assert.equal(find(ProofRail({ id: "r", steps: {} }), (n) => n.tag === "button").length, 0);
    assert.equal(find(ProofRail({ id: "r", steps: {}, onClose() {} }), (n) => n.tag === "button")[0].props["aria-label"], "Close the proof panel");
  });
  test("a long title or unusual text is rendered as text, never as markup", () => {
    const v = ProofRail({ id: "r", subject: "<img src=x onerror=alert(1)>", steps: { source: { title: "<script>alert(1)</script>" } } });
    assert.equal(find(v, (n) => n.tag === "img" || n.tag === "script").length, 0);
  });
});

describe("focus moves into the rail and back to the mark", () => {
  test("the rail can take focus (tabindex -1) and focusRail focuses it, saying so when it is not there", () => {
    assert.equal(ProofRail({ id: "r", steps: {} }).props.tabindex, "-1");
    let n = 0;
    const doc = { getElementById: (id) => (id === "rev-rail" ? { focus: () => { n += 1; } } : null) };
    assert.equal(focusRail("rev-rail", doc), true);
    assert.equal(focusRail("x", doc), false);
    assert.equal(focusRail("rev-rail", null), false);
    assert.equal(n, 1);
  });
});

describe("focus returns to the mark", () => {
  test("focusMark focuses the mark of that figure, and says so when it is not there", () => {
    let focused = 0;
    const doc = { getElementById: (id) => (id === "rev-mark" ? { focus: () => { focused += 1; } } : null) };
    assert.equal(focusMark("rev", doc), true);
    assert.equal(focusMark("nope", doc), false);
    assert.equal(focusMark("rev", null), false);
    assert.equal(focusMark("rev", {}), false);
    assert.equal(focused, 1);
  });
});
