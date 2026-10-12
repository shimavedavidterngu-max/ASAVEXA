import { h } from "../lib/vdom.js";
import { PasswordField, PasswordRules, updateRulesList, clearFieldError } from "../components/PasswordField.js";
import { normaliseCode } from "../lib/passwords.js";

/**
 * The password recovery screens: request a code -> enter the code -> choose a new password -> done.
 * Pure render. app.js owns the state and talks to the real backend (POST /auth/recovery/request, /verify, /reset).
 * Honest by design: it never says a code was sent, only that one is on its way if the email can be recovered, and it says
 * plainly when email is not set up on this platform.
 */
export const RECOVERY_STEPS = ["request", "verify", "reset", "done"];

export function frame(children, { onBack } = {}) {
  return h("div", { className: "login-screen", id: "recovery-screen", style: "min-height:100vh; display:flex; align-items:center; justify-content:center; background: var(--navy-950);" },
    h("div", { className: "card auth-card", style: "width: 380px;" },
      h("div", { className: "auth-brand", style: "font-family: var(--font-display); font-size:22px; margin-bottom:4px;" }, "ASAVEXA"),
      h("div", { style: "color: var(--ink-500); font-size:12.5px; margin-bottom:20px;" }, "Don't just report the number. Prove it."),
      children));
}

export const alertError = (error) => (error ? h("div", { className: "alert alert-error", id: "rc-error", role: "alert", style: "margin-bottom:16px;" }, error) : null);
const backLink = (onBack, text = "Back to sign in") => h("div", { style: "margin-top:16px; text-align:center; font-size:12.5px;" }, h("a", { href: "#", id: "rc-back", onClick: (e) => { e.preventDefault(); onBack(); } }, text));

function requestStep(p) {
  const fe = p.fieldErrors || {};
  const off = p.available === false;
  return h("form", { id: "rc-request", noValidate: true, onSubmit: (e) => { e.preventDefault(); p.onRequest(e.target.elements.email.value); } },
    h("h1", { className: "rc-title", id: "rc-title", tabindex: "-1" }, "Reset your password"),
    h("p", { className: "rc-lead" }, "Enter the email address associated with your ASAVEXA account. We'll send you a verification code if the account is eligible for recovery."),
    off ? h("div", { className: "alert alert-error", id: "rc-unavailable", role: "alert", style: "margin-bottom:16px;" },
      "Password recovery by email is not set up on this platform yet, so no code can be sent. Ask your organisation's administrator, or the person who runs ASAVEXA, to reset your password.") : null,
    off ? null : alertError(p.error),
    h("div", { className: "field" },
      h("label", { for: "rc-email" }, "Email address"),
      h("input", { id: "rc-email", name: "email", type: "email", required: true, autocomplete: "email", value: p.email || "", autofocus: true, "aria-invalid": fe.email ? "true" : undefined, "aria-describedby": fe.email ? "rc-email-err" : undefined,
        onInput: (e) => { clearFieldError("rc-email"); p.onDraft && p.onDraft("email", e.target.value); } }),
      fe.email ? h("div", { className: "ob-err", id: "rc-email-err", role: "alert" }, fe.email) : null),
    h("button", { type: "submit", id: "rc-send", className: "btn btn-primary", style: "width:100%; margin-top:8px;", disabled: p.pending || off, "aria-busy": p.pending ? "true" : undefined }, p.pending ? "Sending…" : "Send verification code"),
    backLink(p.onBack));
}

function verifyStep(p) {
  const fe = p.fieldErrors || {};
  const wait = p.cooldown || 0;
  return h("form", { id: "rc-verify", noValidate: true, onSubmit: (e) => { e.preventDefault(); p.onVerify(e.target.elements.code.value); } },
    h("h1", { className: "rc-title", id: "rc-title", tabindex: "-1" }, "Enter your verification code"),
    h("p", { className: "rc-lead", id: "rc-sent" }, "If an account can be recovered with ", h("strong", {}, p.email), ", a 6-digit code is on its way. It can take a few minutes, and it expires in ", String(p.expiresMinutes || 10), " minutes. Check your spam folder too."),
    p.notice ? h("div", { className: "alert alert-success", id: "rc-notice", role: "status", style: "margin-bottom:16px;" }, p.notice) : null,
    alertError(p.error),
    h("div", { className: "field" },
      h("label", { for: "rc-code" }, "Verification code"),
      h("div", { className: "rc-coderow" },
        h("input", { id: "rc-code", name: "code", type: "text", inputmode: "numeric", pattern: "[0-9]*", autocomplete: "one-time-code", maxlength: "12", value: p.code || "", autofocus: true, required: true,
          "aria-invalid": fe.code ? "true" : undefined, "aria-describedby": fe.code ? "rc-code-err rc-code-hint" : "rc-code-hint", spellcheck: "false",
          onInput: (e) => { clearFieldError("rc-code"); const v = normaliseCode(e.target.value); if (e.target.value !== v) e.target.value = v; p.onDraft && p.onDraft("code", v); } }),
        h("button", { type: "button", className: "btn btn-secondary", id: "rc-clear", "aria-label": "Clear the code", onClick: () => { const i = document.getElementById("rc-code"); if (i) { i.value = ""; p.onDraft && p.onDraft("code", ""); i.focus(); } } }, "Clear")),
      h("div", { className: "pw-hint", id: "rc-code-hint" }, "Six digits. You can paste the code."),
      fe.code ? h("div", { className: "ob-err", id: "rc-code-err", role: "alert" }, fe.code) : null),
    h("button", { type: "submit", id: "rc-verify-go", className: "btn btn-primary", style: "width:100%; margin-top:8px;", disabled: p.pending, "aria-busy": p.pending ? "true" : undefined }, p.pending ? "Checking…" : "Verify code"),
    h("div", { className: "rc-secondary" },
      h("button", { type: "button", className: "btn btn-secondary", id: "rc-resend", disabled: p.pending || wait > 0 || p.available === false, onClick: () => p.onResend() }, wait > 0 ? `Resend code (${wait}s)` : "Resend code"),
      h("button", { type: "button", className: "linklike", id: "rc-change-email", onClick: () => p.onChangeEmail() }, "Use a different email")),
    backLink(p.onBack));
}

function resetStep(p) {
  const fe = p.fieldErrors || {};
  const d = p.draft || {};
  return h("form", { id: "rc-reset", noValidate: true, onSubmit: (e) => { e.preventDefault(); p.onReset({ password: e.target.elements.password.value, confirm: e.target.elements.confirm.value }); } },
    h("h1", { className: "rc-title", id: "rc-title", tabindex: "-1" }, "Choose a new password"),
    h("p", { className: "rc-lead" }, "Your email is verified. Choose a new password for your ASAVEXA account."),
    alertError(p.error),
    PasswordField({ id: "password", label: "New password", value: d.password || "", autocomplete: "new-password", error: fe.password, describedBy: "rc-rules", autofocus: true,
      onInput: (v) => { p.onDraft && p.onDraft("password", v); if (typeof document !== "undefined") updateRulesList(document.getElementById("rc-rules"), v); } }),
    PasswordRules({ id: "rc-rules", value: d.password || "" }),
    PasswordField({ id: "confirm", label: "Confirm new password", value: d.confirm || "", autocomplete: "new-password", error: fe.confirm, onInput: (v) => p.onDraft && p.onDraft("confirm", v) }),
    h("button", { type: "submit", id: "rc-reset-go", className: "btn btn-primary", style: "width:100%; margin-top:8px;", disabled: p.pending, "aria-busy": p.pending ? "true" : undefined }, p.pending ? "Resetting…" : "Reset password"),
    backLink(p.onBack, "Cancel and return to sign in"));
}

function doneStep(p) {
  return h("div", { id: "rc-done" },
    h("h1", { className: "rc-title", id: "rc-title", tabindex: "-1" }, "Password reset"),
    h("div", { className: "alert alert-success", id: "rc-success", role: "status", style: "margin-bottom:16px;" }, "Your password has been reset successfully. You can now sign in with your new password."),
    h("p", { className: "rc-lead" }, "For your security you were signed out everywhere, and we sent a notice to your email address."),
    h("button", { type: "button", id: "rc-return", className: "btn btn-primary", style: "width:100%;", onClick: () => p.onBack() }, "Return to login"));
}

export function Recovery(p) {
  const step = RECOVERY_STEPS.includes(p.step) ? p.step : "request";
  const body = step === "request" ? requestStep(p) : step === "verify" ? verifyStep(p) : step === "reset" ? resetStep(p) : doneStep(p);
  return frame(body, p);
}
