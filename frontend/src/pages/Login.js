import { h } from "../lib/vdom.js";

/**
 * Login — pure render function. Follows the real backend auth
 * mechanism exactly (Section 13: "Follow the actual backend
 * authentication mechanism. Do not invent a second authentication
 * system."): email + password -> POST /auth/login -> bearer token.
 * No client-side "remember me" cookie, no second auth path.
 */
export function Login({ mode = "login", pending, error, onSubmit, onSwitchMode, mfaStep = false, onMfaSubmit, onMfaCancel, sso = null, onSso }) {
  const isRegister = mode === "register";
  if (mfaStep) return MfaStep({ pending, error, onMfaSubmit, onMfaCancel });
  return h(
    "div",
    { className: "login-screen", style: "min-height:100vh; display:flex; align-items:center; justify-content:center; background: var(--navy-950);" },
    h(
      "div",
      { className: "card", style: "width: 360px;" },
      h("div", { style: "font-family: var(--font-display); font-size:22px; color: var(--navy-900); margin-bottom:4px;" }, "ASAVEXA"),
      h("div", { style: "color: var(--ink-500); font-size:12.5px; margin-bottom:24px;" }, "Don't just report the number. Prove it."),
      error ? h("div", { className: "alert alert-error", style: "margin-bottom:16px;" }, error) : null,
      h(
        "form",
        {
          onSubmit: (e) => {
            e.preventDefault();
            const form = e.target;
            onSubmit({
              email: form.elements.email.value,
              password: form.elements.password.value,
            });
          },
        },
        h("div", { className: "field" },
          h("label", { for: "email" }, "Email"),
          h("input", { id: "email", name: "email", type: "email", required: true, autocomplete: "email" })
        ),
        h("div", { className: "field" },
          h("label", { for: "password" }, "Password"),
          h("input", {
            id: "password", name: "password", type: "password", required: true, minlength: "15",
            autocomplete: isRegister ? "new-password" : "current-password",
          }),
          isRegister
            ? h("div", { style: "font-size:11.5px; color: var(--ink-500);" }, "At least 15 characters.")
            : null
        ),
        h("button", { type: "submit", className: "btn btn-primary", style: "width:100%; margin-top:8px;", disabled: pending },
          pending ? "Please wait…" : isRegister ? "Create account" : "Sign in")
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
