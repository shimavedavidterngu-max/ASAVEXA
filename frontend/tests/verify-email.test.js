import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { VerifyEmail, MSG_SENT, MSG_NOT_SENT, MSG_VERIFIED, MSG_OFF } from "../src/pages/VerifyEmail.js";
import { Login } from "../src/pages/Login.js";

const walk = (v, f) => { if (!v || typeof v !== "object") return; f(v); for (const c of v.children || []) walk(c, f); };
const all = (v, pred) => { const out = []; walk(v, (n) => { if (pred(n)) out.push(n); }); return out; };
const byId = (v, id) => all(v, (n) => n.props && n.props.id === id)[0];
const text = (v) => JSON.stringify(v);
const noop = () => {};
const base = { email: "a@b.co", sent: true, code: "", pending: false, fieldErrors: {}, cooldown: 0, expiresMinutes: 10, onVerify: noop, onResend: noop, onContinue: noop, onDraft: noop };

describe("sign-up wording from the brief", () => {
  const login = (mode, pending) => Login({ draft: {}, fieldErrors: {}, mode, pending, onSubmit: noop, onSwitchMode: noop, onDraft: noop });
  test("the button says Create Account, then Creating your account...", () => {
    assert.equal(byId(login("register", false), "auth-submit").children[0], "Create Account");
    assert.equal(byId(login("register", true), "auth-submit").children[0], "Creating your account...");
  });
  test("signing in is unchanged", () => {
    assert.equal(byId(login("login", false), "auth-submit").children[0], "Sign in");
    assert.equal(byId(login("login", true), "auth-submit").children[0], "Please wait…");
  });
});

describe("verify-email screen", () => {
  test("the exact success message appears only when the server said the email was sent", () => {
    const v = VerifyEmail({ ...base, sent: true });
    assert.equal(MSG_SENT, "Your account has been created successfully. A confirmation email has been sent to your registered email address. Please check your inbox and spam folder.");
    assert.ok(text(byId(v, "vf-status")).includes(MSG_SENT)); assert.ok(byId(v, "vf-status").props.className.includes("alert-success"));
  });
  test("when the email could not be sent it says so and never claims it was sent", () => {
    const v = VerifyEmail({ ...base, sent: false });
    assert.equal(MSG_NOT_SENT, "Your account was created, but we could not send the confirmation email. Please try resending it.");
    assert.ok(text(byId(v, "vf-status")).includes(MSG_NOT_SENT)); assert.ok(!text(v).includes("has been sent"));
    assert.ok(byId(v, "vf-status").props.className.includes("alert-error"));
  });
  test("one numeric input that takes a pasted code, verify, resend that waits, and verify later", () => {
    const v = VerifyEmail({ ...base, cooldown: 42 });
    const code = byId(v, "vf-code");
    assert.equal(code.props.inputmode, "numeric"); assert.equal(code.props.autocomplete, "one-time-code"); assert.ok(code.props.required);
    assert.equal(byId(v, "vf-go").children[0], "Verify email");
    const resend = byId(v, "vf-resend");
    assert.equal(resend.props.disabled, true); assert.ok(text(resend).includes("Resend verification code (42s)"));
    assert.equal(byId(VerifyEmail({ ...base, cooldown: 0 }), "vf-resend").props.disabled, false);
    assert.ok(byId(v, "vf-later"));
  });
  test("it names the address the code went to and the expiry", () => {
    const v = VerifyEmail({ ...base, email: "dara@x.test", expiresMinutes: 10 });
    assert.ok(text(byId(v, "vf-lead")).includes("dara@x.test")); assert.ok(text(byId(v, "vf-lead")).includes("10"));
  });
  test("a bad code shows field and server errors", () => {
    const v = VerifyEmail({ ...base, fieldErrors: { code: "Enter the 6-digit code from the email." }, error: "That code is incorrect or has expired." });
    assert.equal(byId(v, "vf-code").props["aria-invalid"], "true"); assert.ok(byId(v, "vf-code-err")); assert.ok(byId(v, "rc-error"));
  });
  test("when email is not set up it says so, disables resend and does not repeat the message", () => {
    const v = VerifyEmail({ ...base, sent: false, available: false, error: "Email is not set up" });
    assert.ok(text(byId(v, "vf-unavailable")).includes(MSG_OFF)); assert.equal(byId(v, "vf-resend").props.disabled, true); assert.ok(!byId(v, "rc-error"));
  });
  test("after a correct code: the success message and a way to continue", () => {
    const v = VerifyEmail({ ...base, verified: true });
    assert.ok(text(byId(v, "vf-success")).includes(MSG_VERIFIED)); assert.ok(byId(v, "vf-continue")); assert.ok(!byId(v, "vf-code"));
  });
  test("after a resend the first banner gives way to the server's own answer", () => {
    const v = VerifyEmail({ ...base, sent: false, resent: true, notice: "If this email address can be verified, a new 6-digit code is on its way." });
    assert.ok(!byId(v, "vf-status")); assert.ok(text(byId(v, "vf-notice")).includes("on its way"));
  });
  test("pending disables the buttons so a double click cannot send twice", () => {
    const v = VerifyEmail({ ...base, pending: true });
    assert.equal(byId(v, "vf-go").props.disabled, true); assert.equal(byId(v, "vf-resend").props.disabled, true);
  });
});

describe("wiring", () => {
  const client = readFileSync(new URL("../src/api/client.js", import.meta.url), "utf8");
  const app = readFileSync(new URL("../src/app.js", import.meta.url), "utf8");
  test("the client talks to the real verification endpoints", () => {
    assert.ok(client.includes('"/auth/verification/request"') && client.includes('"/auth/verification/confirm"') && client.includes('"/auth/verification/status"'));
  });
  test("sign-up goes to the verify screen with the server's own delivery answer, and keeps the account either way", () => {
    assert.ok(app.includes("created.email_delivery")); assert.ok(app.includes('uiState.loginMode = "verify"'));
    assert.ok(app.includes("handleVerifyContinue") && app.includes("handleVerifyResend") && app.includes("handleVerifyConfirm"));
  });
  test("the password is held in memory only and signing out clears the verify screen", () => {
    assert.ok(app.includes("uiState.vf = null; stopVerifyTimer();"));
    assert.ok(!/sessionStorage\.setItem\([^)]*password/i.test(app));
  });
});
