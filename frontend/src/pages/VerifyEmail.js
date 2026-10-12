import { h } from "../lib/vdom.js";
import { frame, alertError } from "./Recovery.js";
import { normaliseCode } from "../lib/passwords.js";

/**
 * Shown right after an account is created: confirm the email address with the 6-digit code that was emailed.
 * Pure render. app.js owns the state and talks to the real backend (POST /auth/verification/confirm and /request).
 * Honest by design: "sent" is shown only when the server says the email provider accepted the message; otherwise it says the
 * account exists but the email could not be sent, and offers to resend.
 */
export const MSG_SENT = "Your account has been created successfully. A confirmation email has been sent to your registered email address. Please check your inbox and spam folder.";
export const MSG_NOT_SENT = "Your account was created, but we could not send the confirmation email. Please try resending it.";
export const MSG_OFF = "Email is not set up on this platform yet, so no verification code can be sent. Ask the person who runs ASAVEXA to finish the email setup. Your account is saved, and you can continue and verify later.";
export const MSG_VERIFIED = "Your email address has been verified.";

export function VerifyEmail(p) {
  const fe = p.fieldErrors || {};
  const wait = p.cooldown || 0;
  if (p.verified) {
    return frame(h("div", { id: "vf-done" },
      h("h1", { className: "rc-title", id: "rc-title", tabindex: "-1" }, "Email verified"),
      h("div", { className: "alert alert-success", id: "vf-success", role: "status", style: "margin-bottom:16px;" }, MSG_VERIFIED),
      h("button", { type: "button", id: "vf-continue", className: "btn btn-primary", style: "width:100%;", disabled: p.pending, onClick: () => p.onContinue() }, p.pending ? "Signing you in…" : "Continue to ASAVEXA"),
      p.error ? alertError(p.error) : null));
  }
  return frame(h("form", { id: "vf-form", noValidate: true, onSubmit: (e) => { e.preventDefault(); p.onVerify(e.target.elements.code.value); } },
    h("h1", { className: "rc-title", id: "rc-title", tabindex: "-1" }, "Verify your email address"),
    p.resent ? null : h("div", { className: p.sent ? "alert alert-success" : "alert alert-error", id: "vf-status", role: "status", style: "margin-bottom:16px;" }, p.sent ? MSG_SENT : MSG_NOT_SENT),
    p.available === false ? h("div", { className: "alert alert-error", id: "vf-unavailable", role: "alert", style: "margin-bottom:16px;" }, MSG_OFF) : null,
    p.available === false || !p.sent
      ? h("p", { className: "rc-lead", id: "vf-lead" }, "When a 6-digit code reaches ", h("strong", {}, p.email || "your email address"), ", enter it here.", p.available === false ? "" : ` It expires in ${p.expiresMinutes || 10} minutes.`)
      : h("p", { className: "rc-lead", id: "vf-lead" }, "Enter the 6-digit code we emailed to ", h("strong", {}, p.email || "your email address"), ". It expires in ", String(p.expiresMinutes || 10), " minutes."),
    p.notice ? h("div", { className: "alert alert-success", id: "vf-notice", role: "status", style: "margin-bottom:16px;" }, p.notice) : null,
    p.available === false ? null : alertError(p.error),
    h("div", { className: "field" },
      h("label", { for: "vf-code" }, "Verification code"),
      h("input", { id: "vf-code", name: "code", type: "text", inputmode: "numeric", pattern: "[0-9]*", autocomplete: "one-time-code", maxlength: "12", value: p.code || "", required: true, spellcheck: "false",
        "aria-invalid": fe.code ? "true" : undefined, "aria-describedby": fe.code ? "vf-code-err vf-code-hint" : "vf-code-hint",
        onInput: (e) => { const v = normaliseCode(e.target.value); if (e.target.value !== v) e.target.value = v; p.onDraft && p.onDraft("code", v); } }),
      h("div", { className: "pw-hint", id: "vf-code-hint" }, "Six digits. You can paste the code."),
      fe.code ? h("div", { className: "ob-err", id: "vf-code-err", role: "alert" }, fe.code) : null),
    h("button", { type: "submit", id: "vf-go", className: "btn btn-primary", style: "width:100%; margin-top:8px;", disabled: p.pending, "aria-busy": p.pending ? "true" : undefined }, p.pending ? "Checking…" : "Verify email"),
    h("div", { className: "rc-secondary" },
      h("button", { type: "button", className: "btn btn-secondary", id: "vf-resend", disabled: p.pending || wait > 0 || p.available === false, onClick: () => p.onResend() },
        wait > 0 ? `Resend verification code (${wait}s)` : "Resend verification code")),
    h("div", { style: "margin-top:16px; text-align:center; font-size:12.5px;" },
      h("a", { href: "#", id: "vf-later", onClick: (e) => { e.preventDefault(); p.onContinue(); } }, "Verify later and continue to ASAVEXA"))));
}
