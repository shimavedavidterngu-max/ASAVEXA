import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { Login } from "../src/pages/Login.js";
import { Recovery } from "../src/pages/Recovery.js";
import { PasswordField, PasswordRules, togglePasswordVisibility, updateRulesList } from "../src/components/PasswordField.js";
import {
  MIN_LENGTH, MAX_LENGTH, passwordRules, passwordProblems, validateSignup, validateLogin, validateNewPassword, emailProblem, normaliseCode, codeProblem, secondsLeft, nextInputType,
} from "../src/lib/passwords.js";

const walk = (v, f) => { if (!v || typeof v !== "object") return; f(v); for (const c of v.children || []) walk(c, f); };
const all = (v, pred) => { const out = []; walk(v, (n) => { if (pred(n)) out.push(n); }); return out; };
const byId = (v, id) => all(v, (n) => n.props && n.props.id === id)[0];
const text = (v) => JSON.stringify(v);

describe("password rules", () => {
  test("the numbers are 8 to 128", () => { assert.equal(MIN_LENGTH, 8); assert.equal(MAX_LENGTH, 128); });
  test("1-3: too short, no letter, no number are each refused with a clear sentence", () => {
    assert.deepEqual(passwordProblems("abc1234"), ["Use at least 8 characters."]);
    assert.deepEqual(passwordProblems("12345678"), ["Include at least one letter."]);
    assert.deepEqual(passwordProblems("abcdefgh"), ["Include at least one number."]);
  });
  test("4: a compliant password passes, including spaces, symbols and other alphabets, exactly as typed", () => {
    for (const ok of ["stone42river", "with spaces 1 inside", "  padded 9  ", "Ünïcödé-7-passwörd", "Пароль-1234x", "x".repeat(127) + "1"]) assert.deepEqual(passwordProblems(ok), [], ok);
  });
  test("a very long or very common password is refused, and empty asks for one", () => {
    assert.ok(passwordProblems("x".repeat(129) + "1").length);
    assert.ok(passwordProblems("Password123").some((p) => /too common/.test(p)));
    assert.deepEqual(passwordProblems(""), ["Enter a password."]);
    assert.deepEqual(passwordProblems(undefined), ["Enter a password."]);
  });
  test("the live checklist says which rules are met", () => {
    assert.deepEqual(passwordRules("abc").map((r) => r.ok), [false, true, false]);
    assert.deepEqual(passwordRules("abcdefg1").map((r) => r.ok), [true, true, true]);
    assert.deepEqual(passwordRules("").map((r) => r.ok), [false, false, false]);
  });
  test("5: sign-up needs the two passwords to match, and checks the email", () => {
    assert.equal(validateSignup({ email: "a@b.co", password: "stone42river", confirm: "stone42river" }).ok, true);
    assert.equal(validateSignup({ email: "a@b.co", password: "stone42river", confirm: "stone42rivers" }).errors.confirm, "The two passwords do not match.");
    assert.ok(validateSignup({ email: "a@b.co", password: "stone42river", confirm: "" }).errors.confirm);
    assert.ok(validateSignup({ email: "nope", password: "stone42river", confirm: "stone42river" }).errors.email);
    const v = validateSignup({ email: "", password: "x", confirm: "y" });
    assert.ok(v.errors.email && v.errors.password && v.errors.confirm);
  });
  test("login and reset validation", () => {
    assert.equal(validateLogin({ email: "a@b.co", password: "x" }).ok, true);
    assert.ok(validateLogin({ email: "a@b.co", password: "" }).errors.password);
    assert.equal(validateNewPassword({ password: "stone42river", confirm: "stone42river" }).ok, true);
    assert.ok(validateNewPassword({ password: "short", confirm: "short" }).errors.password);
    assert.ok(emailProblem(" ") && emailProblem("a@b") && !emailProblem("a@b.co"));
  });
  test("the code is digits only, six at most, so a pasted code with spaces or dashes works", () => {
    assert.equal(normaliseCode("123 456"), "123456"); assert.equal(normaliseCode("123-456-789"), "123456"); assert.equal(normaliseCode("ab12"), "12"); assert.equal(normaliseCode(null), "");
    assert.ok(codeProblem("12345")); assert.equal(codeProblem("123456"), null);
  });
  test("timer helpers", () => { assert.equal(secondsLeft(10_500, 10_000), 1); assert.equal(secondsLeft(9_000, 10_000), 0); assert.equal(nextInputType("password"), "text"); assert.equal(nextInputType("text"), "password"); });
});

describe("the eye button (6)", () => {
  const fakeButton = () => { const a = {}; return { setAttribute: (k, v) => { a[k] = v; }, a, classList: { toggle: () => {} } }; };
  test("hidden by default, with an accessible button", () => {
    const f = PasswordField({ id: "password", label: "Password", autocomplete: "current-password", onInput: () => {} });
    const input = byId(f, "password"), eye = byId(f, "password-eye");
    assert.equal(input.props.type, "password");
    assert.equal(eye.tag, "button"); assert.equal(eye.props.type, "button");
    assert.equal(eye.props["aria-label"], "Show password"); assert.equal(eye.props["aria-pressed"], "false"); assert.equal(eye.props["aria-controls"], "password");
  });
  test("clicking flips the type and the label, and clicking again hides it; the typed value is untouched", () => {
    const input = { type: "password", value: "stone42river", selectionStart: 3, selectionEnd: 3, setSelectionRange() {} };
    const b = fakeButton();
    assert.equal(togglePasswordVisibility(b, input), true);
    assert.equal(input.type, "text"); assert.equal(b.a["aria-label"], "Hide password"); assert.equal(b.a["aria-pressed"], "true");
    assert.equal(togglePasswordVisibility(b, input), false);
    assert.equal(input.type, "password"); assert.equal(b.a["aria-label"], "Show password");
    assert.equal(input.value, "stone42river");
  });
  test("it is a real button (keyboard and screen readers) and the rules list reads in words", () => {
    const rules = PasswordRules({ id: "r", value: "abc" });
    assert.ok(text(rules).includes("(not met yet)")); assert.ok(text(rules).includes("(met)"));
  });
  test("updating the rules while typing changes the list in place", () => {
    const li = (id) => { const o = { cls: new Set(), tick: { textContent: "" }, sr: { textContent: "" }, classList: { toggle: (c, on) => (on ? o.cls.add(c) : o.cls.delete(c)) }, querySelector: (q) => (q === ".pw-tick" ? o.tick : o.sr) }; return o; };
    const items = { length: li(), letter: li(), number: li() };
    updateRulesList({ querySelector: (q) => items[/data-rule="(\w+)"/.exec(q)[1]] }, "abcdefg1");
    assert.ok(items.length.cls.has("is-ok") && items.number.cls.has("is-ok")); assert.equal(items.number.tick.textContent, "✓");
  });
});

describe("login and sign-up screens", () => {
  const base = { onSubmit: () => {}, onSwitchMode: () => {} };
  test("login has the eye, a visible Forgot password link near the password, and no 'not available' note", () => {
    const v = Login({ ...base, onForgot: () => {} });
    assert.ok(byId(v, "password-eye")); assert.ok(byId(v, "login-forgot"));
    assert.equal(byId(v, "login-forgot").children[0], "Forgot password?");
    assert.ok(!text(v).includes("not available yet"));
    assert.equal(byId(v, "password").props.autocomplete, "current-password");
  });
  test("clicking Forgot password opens recovery and does not follow the link", () => {
    let n = 0, prevented = false;
    byId(Login({ ...base, onForgot: () => { n++; } }), "login-forgot").props.onClick({ preventDefault: () => { prevented = true; } });
    assert.equal(n, 1); assert.ok(prevented);
  });
  test("sign-up has password and confirm fields, each with an eye, the rules, and new-password autocomplete", () => {
    const v = Login({ ...base, mode: "register" });
    assert.ok(byId(v, "password-eye") && byId(v, "confirm-eye") && byId(v, "su-rules"));
    assert.equal(byId(v, "confirm").props.type, "password"); assert.equal(byId(v, "confirm").props.autocomplete, "new-password");
    assert.ok(!byId(Login(base), "confirm"));
  });
  test("the form submits email, password and (in sign-up) the confirmation exactly as typed, without trimming the password", () => {
    let got;
    const form = all(Login({ onSubmit: (x) => { got = x; }, onSwitchMode: () => {}, mode: "register" }), (n) => n.tag === "form")[0];
    form.props.onSubmit({ preventDefault() {}, target: { elements: { email: { value: "a@b.co" }, password: { value: "  pass 12  " }, confirm: { value: "  pass 12  " } } } });
    assert.deepEqual(got, { email: "a@b.co", password: "  pass 12  ", confirm: "  pass 12  " });
  });
  test("field errors show beneath the fields and mark them invalid; values from the draft are kept", () => {
    const v = Login({ ...base, mode: "register", draft: { email: "a@b.co", password: "x", confirm: "y" }, fieldErrors: { password: "Use at least 8 characters.", confirm: "The two passwords do not match." } });
    assert.equal(byId(v, "password").props["aria-invalid"], "true"); assert.equal(byId(v, "password").props.value, "x");
    assert.equal(byId(v, "email").props.value, "a@b.co");
    assert.equal(byId(v, "password-err").props.role, "alert"); assert.ok(text(byId(v, "confirm-err")).includes("do not match"));
    assert.ok(byId(v, "password").props["aria-describedby"].includes("password-err"));
  });
  test("a pending form disables the button against double submission and says so", () => {
    const b = byId(Login({ ...base, pending: true }), "auth-submit");
    assert.equal(b.props.disabled, true); assert.equal(b.props["aria-busy"], "true");
  });
  test("a success notice (after a reset) is shown on the login screen", () => {
    assert.ok(text(Login({ ...base, notice: "Your password was reset." })).includes("Your password was reset."));
  });
});

describe("recovery screens (3)", () => {
  const p = { onRequest() {}, onVerify() {}, onReset() {}, onResend() {}, onBack() {}, onChangeEmail() {}, onDraft() {} };
  test("step 1 has the exact title, instructions, email field, button and a way back", () => {
    const v = Recovery({ ...p, step: "request" });
    assert.equal(byId(v, "rc-title").children[0], "Reset your password");
    assert.ok(text(v).includes("Enter the email address associated with your ASAVEXA account. We'll send you a verification code if the account is eligible for recovery."));
    assert.equal(byId(v, "rc-email").props.type, "email"); assert.equal(byId(v, "rc-send").children[0], "Send verification code"); assert.ok(byId(v, "rc-back"));
  });
  test("step 1 is honest when email is not set up: the button is off and it says why", () => {
    const v = Recovery({ ...p, step: "request", available: false });
    assert.equal(byId(v, "rc-send").props.disabled, true); assert.ok(text(byId(v, "rc-unavailable")).includes("not set up"));
    assert.ok(!byId(Recovery({ ...p, step: "request", available: true }), "rc-unavailable"));
  });
  test("the 'not set up' message is shown once, even if a stale error is also passed in", () => {
    const v = Recovery({ ...p, step: "request", available: false, error: "Password recovery by email is not set up on this platform yet." });
    assert.ok(byId(v, "rc-unavailable")); assert.ok(!byId(v, "rc-error"));
    assert.ok(byId(Recovery({ ...p, step: "request", available: true, error: "Too many attempts." }), "rc-error"));
  });
  test("step 2: one numeric input that takes a pasted code, a clear button, verify, and a resend that waits", () => {
    const v = Recovery({ ...p, step: "verify", email: "a@b.co", cooldown: 42 });
    const c = byId(v, "rc-code");
    assert.equal(c.props.inputmode, "numeric"); assert.equal(c.props.autocomplete, "one-time-code");
    assert.ok(byId(v, "rc-clear")); assert.equal(byId(v, "rc-verify-go").children[0], "Verify code");
    assert.equal(byId(v, "rc-resend").props.disabled, true); assert.equal(byId(v, "rc-resend").children[0], "Resend code (42s)");
    assert.equal(byId(Recovery({ ...p, step: "verify", email: "a@b.co", cooldown: 0 }), "rc-resend").props.disabled, false);
    const e = { target: { value: "123 456" } }; let drafted;
    byId(Recovery({ ...p, step: "verify", email: "a@b.co", onDraft: (k, x) => { drafted = [k, x]; } }), "rc-code").props.onInput(e);
    assert.equal(e.target.value, "123456"); assert.deepEqual(drafted, ["code", "123456"]);
  });
  test("step 2 never claims the code was sent: it says one is on its way if the email can be recovered", () => {
    const t = text(Recovery({ ...p, step: "verify", email: "a@b.co" }));
    assert.ok(t.includes("If an account can be recovered with")); assert.ok(!/we sent|has been sent|was sent/i.test(t));
  });
  test("step 3: new and confirm password, both with eyes, the rules and a reset button", () => {
    const v = Recovery({ ...p, step: "reset", draft: { password: "", confirm: "" } });
    assert.ok(byId(v, "password-eye") && byId(v, "confirm-eye") && byId(v, "rc-rules"));
    assert.equal(byId(v, "rc-reset-go").children[0], "Reset password");
  });
  test("step 4: the exact success message and a Return to login button", () => {
    const v = Recovery({ ...p, step: "done" });
    assert.ok(text(byId(v, "rc-success")).includes("Your password has been reset successfully. You can now sign in with your new password."));
    assert.equal(byId(v, "rc-return").children[0], "Return to login");
  });
  test("pending states disable the submit buttons; errors are announced", () => {
    assert.equal(byId(Recovery({ ...p, step: "request", pending: true }), "rc-send").props.disabled, true);
    assert.equal(byId(Recovery({ ...p, step: "verify", pending: true }), "rc-verify-go").props.disabled, true);
    assert.equal(byId(Recovery({ ...p, step: "reset", pending: true }), "rc-reset-go").props.disabled, true);
    assert.equal(byId(Recovery({ ...p, step: "request", error: "Too many." }), "rc-error").props.role, "alert");
  });
});

describe("app.js wiring contracts", () => {
  const src = readFileSync(new URL("../src/app.js", import.meta.url), "utf8");
  test("a double submit is ignored and the same checks run before the network", () => {
    assert.match(src, /if \(uiState\.loginPending\) return;\s*\/\/ a double click/);
    assert.match(src, /validateSignup\(\{ email: cleanEmail, password, confirm \}\)/);
  });
  test("the password is never trimmed, and the recovery token is never put in a URL or storage", () => {
    assert.ok(!/password\.trim\(\)|password: String\(password\)\.trim/.test(src));
    const rc = src.slice(src.indexOf("// ---- password recovery"), src.indexOf("async function handleMfaSubmit"));
    assert.ok(!/localStorage|sessionStorage|location\.|history\./.test(rc), "recovery state stays in memory");
    assert.ok(!/console\./.test(rc));
  });
  test("a reset does not sign the person in: it goes back to the login screen with a notice", () => {
    const done = src.slice(src.indexOf("async function handleRecoveryReset"), src.indexOf("async function handleMfaSubmit"));
    assert.ok(!/setSession/.test(done)); assert.match(src, /Your password was reset\. Sign in with your new password\./);
  });
  test("sign-out clears the form drafts", () => { assert.match(src, /clearAuthDraft\(\); uiState\.rc = null; uiState\.vf = null; stopVerifyTimer\(\); uiState\.loginMode = "login";/); });
  test("the api client has the four recovery calls and sends the confirmation on sign-up", () => {
    const c = readFileSync(new URL("../src/api/client.js", import.meta.url), "utf8");
    for (const m of ["recoveryStatus", "recoveryRequest", "recoveryVerify", "recoveryReset"]) assert.ok(c.includes(m + "("));
    assert.ok(c.includes("confirm_password"));
  });
});
