import { h } from "../lib/vdom.js";
import { nextInputType, passwordRules } from "../lib/passwords.js";

const EYE = (off) => h("svg", { viewBox: "0 0 24 24", width: "18", height: "18", fill: "none", stroke: "currentColor", "stroke-width": "2", "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true", focusable: "false", className: off ? "pw-eye-off" : "pw-eye-on" },
  h("path", { d: "M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z" }), h("circle", { cx: "12", cy: "12", r: "3" }),
  off ? h("line", { x1: "3", y1: "3", x2: "21", y2: "21" }) : null);

/**
 * Flips one password input between hidden and visible. It only changes the input's `type` and the button's label: the typed
 * password stays exactly where it is (nothing is read, copied, stored or sent), and the field keeps focus and its caret.
 */
export function togglePasswordVisibility(button, input) {
  if (!button || !input) return false;
  const start = input.selectionStart, end = input.selectionEnd;
  input.type = nextInputType(input.type);
  const shown = input.type !== "password";
  button.setAttribute("aria-label", shown ? "Hide password" : "Show password");
  button.setAttribute("aria-pressed", shown ? "true" : "false");
  button.setAttribute("title", shown ? "Hide password" : "Show password");
  button.classList && button.classList.toggle("is-shown", shown);
  try { if (start != null) input.setSelectionRange(start, end); } catch { /* not a text-like input */ }
  return shown;
}

/** As soon as someone edits a field, the error shown for it is out of date: take it away (without re-rendering the page). */
export function clearFieldError(id) {
  if (typeof document === "undefined") return;
  const err = document.getElementById(`${id}-err`); if (err) err.remove();
  const input = document.getElementById(id); if (input) { input.removeAttribute("aria-invalid"); input.removeAttribute("aria-describedby"); }
}

/** A password input with an eye button inside it. Hidden by default. `describedBy` ids are joined to the error and hint ids. */
export function PasswordField({ id, name, label, value = "", autocomplete, error, hint, describedBy, onInput, required = true, autofocus = false, extra = null }) {
  const desc = [error ? `${id}-err` : null, hint ? `${id}-hint` : null, describedBy].filter(Boolean).join(" ") || undefined;
  return h("div", { className: "field pw-field" },
    h("div", { className: "pw-labelrow" }, h("label", { for: id }, label), extra),
    h("div", { className: "pw-wrap" },
      h("input", { id, name: name || id, type: "password", value, autocomplete, required, "aria-invalid": error ? "true" : undefined, "aria-describedby": desc, autofocus: autofocus || undefined,
        spellcheck: "false", autocapitalize: "none", autocorrect: "off", maxlength: "256", onInput: (e) => { clearFieldError(id); onInput && onInput(e.target.value); } }),
      h("button", { type: "button", className: "pw-eye", id: `${id}-eye`, "aria-label": "Show password", "aria-pressed": "false", "aria-controls": id, title: "Show password",
        onClick: (e) => { const b = e.currentTarget || e.target; togglePasswordVisibility(b, typeof document !== "undefined" ? document.getElementById(id) : null); } },
        EYE(false), EYE(true))),
    hint ? h("div", { className: "pw-hint", id: `${id}-hint` }, hint) : null,
    error ? h("div", { className: "ob-err", id: `${id}-err`, role: "alert" }, error) : null);
}

/** The rules beneath a new-password field. Each line says whether it is met, in words and not only colour. */
export function PasswordRules({ id, value }) {
  const rules = passwordRules(value);
  return h("ul", { className: "pw-rules", id, "aria-label": "Password requirements" },
    rules.map((r) => h("li", { className: r.ok ? "is-ok" : "", "data-rule": r.id },
      h("span", { className: "pw-tick", "aria-hidden": "true" }, r.ok ? "✓" : "○"), r.label, h("span", { className: "sr-only" }, r.ok ? " (met)" : " (not met yet)"))));
}

/** Updates the rules list in place while typing, without re-rendering the page (so focus and the caret are untouched). */
export function updateRulesList(listEl, value) {
  if (!listEl) return;
  for (const r of passwordRules(value)) {
    const li = listEl.querySelector(`[data-rule="${r.id}"]`);
    if (!li) continue;
    li.classList.toggle("is-ok", r.ok);
    const tick = li.querySelector(".pw-tick"); if (tick) tick.textContent = r.ok ? "✓" : "○";
    const sr = li.querySelector(".sr-only"); if (sr) sr.textContent = r.ok ? " (met)" : " (not met yet)";
  }
}
