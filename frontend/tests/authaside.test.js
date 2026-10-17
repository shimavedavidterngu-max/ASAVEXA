import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { AuthAside, AUTH_POINTS } from "../src/components/AuthAside.js";
import { Login, MfaStep } from "../src/pages/Login.js";
import { frame } from "../src/pages/Recovery.js";
import { allCopy, FORBIDDEN_CLAIMS } from "../src/lib/landing.js";

const walk = (v, fn) => { if (!v || typeof v !== "object") return; fn(v); (v.children || []).forEach((c) => walk(c, fn)); };
const all = (v, pred) => { const out = []; walk(v, (n) => { if (pred(n)) out.push(n); }); return out; };
const text = (v) => { if (v == null || v === false) return ""; if (typeof v !== "object") return String(v); return (v.children || []).map(text).join(""); };
const css = readFileSync(new URL("../src/styles/auth.css", import.meta.url), "utf8");

describe("the panel beside sign-in", () => {
  test("it says only things the product backs: no figures, no customers, no absolute claims", () => {
    const t = text(AuthAside());
    assert.ok(!/\d/.test(t), "a number appeared");
    for (const re of FORBIDDEN_CLAIMS) assert.ok(!re.test(t), String(re));
    assert.equal(AUTH_POINTS.length, 3);
  });
  test("sign-in, sign-up, the second step and recovery all carry it, and the form is still there", () => {
    const screens = [Login({ onSubmit() {}, onSwitchMode() {} }), Login({ mode: "register", onSubmit() {}, onSwitchMode() {} }), MfaStep({ onMfaSubmit() {} }), frame(null)];
    for (const s of screens) {
      assert.equal(all(s, (n) => n.tag === "aside").length, 1);
      assert.ok(s.props.className.includes("auth-split"));
      assert.equal(all(s, (n) => n.props && n.props.className === "card auth-card").length, 1);
    }
  });
  test("the sign-in form keeps its ids, labels and submit button", () => {
    const v = Login({ onSubmit() {}, onSwitchMode() {} });
    for (const id of ["login-form", "email", "password", "auth-submit"]) assert.ok(all(v, (n) => n.props && n.props.id === id).length >= 1, id);
  });
  test("on a phone the panel is hidden so the form comes first, and nothing fixed-width remains", () => {
    assert.match(css, /@media \(max-width: 900px\)[\s\S]*?\.auth-aside \{ display: none; \}/);
    const src = readFileSync(new URL("../src/pages/Login.js", import.meta.url), "utf8") + readFileSync(new URL("../src/pages/Recovery.js", import.meta.url), "utf8");
    assert.ok(!/width: ?3[68]0px/.test(src));
  });
});
