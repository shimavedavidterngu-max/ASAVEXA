/**
 * Password rules and the small pure helpers for the sign-in, sign-up and recovery screens. No DOM, no network.
 * These numbers mirror the server (src/asavexa/identity/domain/password_policy.py); the server is what actually enforces them,
 * and tests/test_password_recovery.py checks the two files agree. A password is never trimmed or changed here.
 */
export const MIN_LENGTH = 8;
export const MAX_LENGTH = 128;
export const CODE_LENGTH = 6;

const COMMON = new Set(("password1 password12 password123 password1234 password12345 passw0rd p@ssw0rd p@ssword1 qwerty123 qwerty1234 qwertyuiop1 " +
  "1q2w3e4r 1qaz2wsx abc12345 abcd1234 abcd12345 admin123 admin1234 administrator1 welcome1 welcome123 letmein123 iloveyou1 " +
  "iloveyou123 monkey123 dragon123 football1 baseball1 sunshine1 princess1 trustno1 changeme1 changeme123 asavexa123 asavexa1 " +
  "12345678a a12345678 123456789a a123456789 11111111a 1234567a8").split(/\s+/));

const length = (s) => [...String(s)].length;

/** The live checklist shown beneath the password field: one entry per rule, with whether it is met right now. */
export function passwordRules(pw) {
  const s = typeof pw === "string" ? pw : "";
  return [
    { id: "length", label: `At least ${MIN_LENGTH} characters`, ok: length(s) >= MIN_LENGTH && length(s) <= MAX_LENGTH },
    { id: "letter", label: "At least one letter", ok: /\p{L}/u.test(s) },
    { id: "number", label: "At least one number", ok: /[0-9]/.test(s) },
  ];
}

/** Every rule the password breaks, as sentences (same wording as the server). Empty means acceptable. */
export function passwordProblems(pw) {
  if (typeof pw !== "string" || pw === "") return ["Enter a password."];
  const out = [];
  const n = length(pw);
  if (n < MIN_LENGTH) out.push(`Use at least ${MIN_LENGTH} characters.`);
  if (n > MAX_LENGTH) out.push(`Use no more than ${MAX_LENGTH} characters.`);
  if (!/\p{L}/u.test(pw)) out.push("Include at least one letter.");
  if (!/[0-9]/.test(pw)) out.push("Include at least one number.");
  if (COMMON.has(pw.toLowerCase())) out.push("That password is too common. Choose something less guessable.");
  return out;
}

export function emailProblem(email) {
  const e = typeof email === "string" ? email.trim() : "";
  if (!e) return "Enter your email address.";
  if (!/^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$/.test(e)) return "Enter a valid email address, like name@example.com.";
  return null;
}

/** Field-level errors for the sign-up form. The password is checked exactly as typed (no trimming). */
export function validateSignup({ email, password, confirm }) {
  const errors = {};
  const e = emailProblem(email);
  if (e) errors.email = e;
  const p = passwordProblems(password);
  if (p.length) errors.password = p.join(" ");
  if (!confirm) errors.confirm = "Type the password again to confirm it.";
  else if (confirm !== password) errors.confirm = "The two passwords do not match.";
  return { ok: Object.keys(errors).length === 0, errors };
}

export function validateLogin({ email, password }) {
  const errors = {};
  const e = emailProblem(email);
  if (e) errors.email = e;
  if (!password) errors.password = "Enter your password.";
  return { ok: Object.keys(errors).length === 0, errors };
}

export function validateNewPassword({ password, confirm }) {
  const errors = {};
  const p = passwordProblems(password);
  if (p.length) errors.password = p.join(" ");
  if (!confirm) errors.confirm = "Type the password again to confirm it.";
  else if (confirm !== password) errors.confirm = "The two passwords do not match.";
  return { ok: Object.keys(errors).length === 0, errors };
}

/** Keeps only digits, at most six: so a pasted "123 456" or "123-456" becomes 123456. */
export function normaliseCode(raw) {
  return String(raw == null ? "" : raw).replace(/\D/g, "").slice(0, CODE_LENGTH);
}
export const codeProblem = (code) => (normaliseCode(code).length === CODE_LENGTH ? null : `Enter the ${CODE_LENGTH}-digit code from the email.`);

/** Whole seconds left on a resend timer (never negative). */
export const secondsLeft = (until, now = Date.now()) => Math.max(0, Math.ceil((until - now) / 1000));

/** The password field's visibility: hidden unless the person asks. Pure so it can be tested without a browser. */
export const nextInputType = (type) => (type === "password" ? "text" : "password");
