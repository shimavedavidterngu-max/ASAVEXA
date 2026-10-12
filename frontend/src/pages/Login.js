import { h } from "../lib/vdom.js";
import { PasswordField, PasswordRules, updateRulesList, clearFieldError } from "../components/PasswordField.js";

/**
 * Login — pure render function. Follows the real backend auth
 * mechanism exactly (Section 13: "Follow the actual backend
 * authentication mechanism. Do not invent a second authentication
 * system."): email + password -> POST /auth/login -> bearer token.
 * No client-side "remember me" cookie, no second auth path.
 */
export function Login({ mode = "login", pending, error, onSubmit, onSwitchMode, mfaStep = false, onMfaSubmit, onMfaCancel, sso = null, onSso, onHome,
  draft = {}, fieldErrors = {}, onDraft, onForgot, notice = null }) {
  const isRegister = mode === "register";
  if (mfaStep) return MfaStep({ pending, error, onMfaSubmit, onMfaCancel });
  const keep = (k) => (v) => {
    if (onDraft) onDraft(k, v);
    if (isRegister && k === "password" && typeof document !== "undefined") updateRulesList(document.getElementById("su-rules"), v);
    if (isRegister && (k === "password" || k === "confirm") && typeof document !== "undefined") liveMatch();
  };
  const fe = fieldErrors || {};
  return h(
    "div",
    { className: "login-screen", id: "auth-screen", style: "min-height:100vh; display:flex; align-items:center; justify-content:center; background: var(--navy-950);" },
    h(
      "div",
      { className: "card auth-card", style: "width: 360px;" },
      onHome ? h("a", { href: "#/", id: "login-home", style: "display:inline-block; font-size:12.5px; margin-bottom:12px;", onClick: (e) => { e.preventDefault(); onHome(); } }, "\u2190 Back to the home page") : null,
      h("div", { className: "auth-brand", style: "font-family: var(--font-display); font-size:22px; margin-bottom:4px;" }, "ASAVEXA"),
      h("div", { style: "color: var(--ink-500); font-size:12.5px; margin-bottom:24px;" }, "Don't just report the number. Prove it."),
      notice ? h("div", { className: "alert alert-success", id: "auth-notice", role: "status", style: "margin-bottom:16px;" }, notice) : null,
      error ? h("div", { className: "alert alert-error", id: "auth-error", role: "alert", style: "margin-bottom:16px;" }, error) : null,
      h(
        "form",
        {
          id: isRegister ? "signup-form" : "login-form", noValidate: true,
          onSubmit: (e) => {
            e.preventDefault();
            const form = e.target;
            const out = { email: form.elements.email.value, password: form.elements.password.value };
            if (isRegister) out.confirm = form.elements.confirm ? form.elements.confirm.value : "";
            onSubmit(out);
          },
        },
        h("div", { className: "field" },
          h("label", { for: "email" }, "Email"),
          h("input", { id: "email", name: "email", type: "email", required: true, autocomplete: "email", value: draft.email || "", "aria-invalid": fe.email ? "true" : undefined, "aria-describedby": fe.email ? "email-err" : undefined,
            onInput: (e) => { clearFieldError("email"); keep("email")(e.target.value); } }),
          fe.email ? h("div", { className: "ob-err", id: "email-err", role: "alert" }, fe.email) : null
        ),
        PasswordField({
          id: "password", label: "Password", value: draft.password || "", autocomplete: isRegister ? "new-password" : "current-password", error: fe.password,
          describedBy: isRegister ? "su-rules" : undefined, onInput: keep("password"),
          extra: !isRegister && onForgot ? h("a", { href: "#", id: "login-forgot", className: "pw-forgot", onClick: (e) => { e.preventDefault(); onForgot(); } }, "Forgot password?") : null,
        }),
        isRegister ? PasswordRules({ id: "su-rules", value: draft.password || "" }) : null,
        isRegister ? PasswordField({ id: "confirm", label: "Confirm password", value: draft.confirm || "", autocomplete: "new-password", error: fe.confirm, describedBy: "confirm-live", onInput: keep("confirm") }) : null,
        isRegister ? h("div", { className: "pw-live", id: "confirm-live", "aria-live": "polite" }) : null,
        h("button", { type: "submit", id: "auth-submit", className: "btn btn-primary", style: "width:100%; margin-top:8px;", disabled: pending, "aria-busy": pending ? "true" : undefined },
          pending ? (isRegister ? "Creating your account..." : "Please wait…") : isRegister ? "Create Account" : "Sign in")
      ),
      sso && sso.enabled && !isRegister
        ? h("button", { type: "button", className: "btn btn-secondary", style: "width:100%; margin-top:8px;", disabled: pending, onClick: () => onSso && onSso() },
            "Sign in with single sign-on")
        : null,
      h(
        "div",
        { style: "margin-top:16px; text-align:center; font-size:12.5px;" },
        isRegister ? "Already have an account? " : "Need an account? ",
        h("a", { href: "#", onClick: (e) => { e.preventDefault(); onSwitchMode(isRegister ? "login" : "register"); } },
          isRegister ? "Sign in" : "Create one")
      )
    )
  );
}

/** Says, under the confirm field and without re-rendering, whether the two passwords match yet. */
function liveMatch() {
  const a = document.getElementById("password"), b = document.getElementById("confirm"), out = document.getElementById("confirm-live");
  if (!a || !b || !out) return;
  out.textContent = !b.value ? "" : a.value === b.value ? "Passwords match." : "Passwords do not match yet.";
  out.className = "pw-live" + (b.value && a.value === b.value ? " is-ok" : "");
}

/** Second sign-in step for accounts with multi-factor on: the 6-digit code from the authenticator app, or a recovery code. */
export function MfaStep({ pending, error, onMfaSubmit, onMfaCancel }) {
  return h(
    "div",
    { className: "login-screen", style: "min-height:100vh; display:flex; align-items:center; justify-content:center; background: var(--navy-950);" },
    h(
      "div",
      { className: "card", style: "width: 360px;" },
      h("div", { style: "font-family: var(--font-display); font-size:22px; color: var(--navy-900); margin-bottom:4px;" }, "Check it is you"),
      h("div", { style: "color: var(--ink-500); font-size:12.5px; margin-bottom:20px;" },
        "Open your authenticator app and type the 6-digit code for ASAVEXA. Lost your phone? Use one of your recovery codes instead."),
      error ? h("div", { className: "alert alert-error", style: "margin-bottom:16px;" }, error) : null,
      h(
        "form",
        {
          onSubmit: (e) => {
            e.preventDefault();
            onMfaSubmit({ code: String(e.target.elements.code.value || "").trim() });
          },
        },
        h("div", { className: "field" },
          h("label", { for: "code" }, "Code"),
          h("input", { id: "code", name: "code", type: "text", required: true, autocomplete: "one-time-code", inputmode: "text", autofocus: true, maxlength: "32" })
        ),
        h("button", { type: "submit", className: "btn btn-primary", style: "width:100%; margin-top:8px;", disabled: pending }, pending ? "Checking…" : "Continue")
      ),
      h("div", { style: "margin-top:16px; text-align:center; font-size:12.5px;" },
        h("a", { href: "#", onClick: (e) => { e.preventDefault(); onMfaCancel && onMfaCancel(); } }, "Back to sign in"))
    )
  );
}

/**
 * OrganisationPicker — shown after login when the user belongs to
 * more than one organisation, or none. A user's authentication never
 * automatically grants org access (Section 5) — this screen only
 * lists organisations a real GET /organisations/mine call returned.
 */
export function OrganisationPicker({ organisations, onSelect, onCreateNew, onSecurity }) {
  return h(
    "div",
    { className: "card", style: "max-width: 480px; margin: 80px auto;" },
    h("h2", {}, "Select an organisation"),
    !organisations || organisations.length === 0
      ? h("div", { className: "empty-state" },
          h("p", {}, "You don't belong to any organisation yet."),
          h("button", { className: "btn btn-primary", onClick: onCreateNew }, "Create one"))
      : h(
          "div",
          {},
          organisations.map((org) =>
            h(
              "div",
              {
                className: "card", style: "cursor:pointer; margin-bottom:8px;",
                onClick: () => onSelect(org.id), tabindex: "0", role: "button",
              },
              h("div", {}, org.name),
              h("div", { className: "mono", style: "font-size:11.5px; color: var(--ink-500);" }, org.id)
            )
          )
        ),
    onSecurity ? h("div", { style: "margin-top:16px; font-size:12.5px;" },
      h("a", { href: "#", id: "picker-security", onClick: (e) => { e.preventDefault(); onSecurity(); } }, "Security: set up two-step sign-in or manage my devices")) : null
  );
}
