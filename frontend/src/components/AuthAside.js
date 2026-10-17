import { h } from "../lib/vdom.js";

/**
 * The left panel beside the sign-in, sign-up and recovery forms. Three statements the product really backs (the same ones the landing
 * page makes), no figures, no customer names. It is hidden on narrow screens, where the form comes first.
 */
export const AUTH_POINTS = [
  "Every figure can show the records behind it.",
  "A missing link is shown as missing, never hidden.",
  "A posted journal is never edited. A correction is a reversal, and both stay on record.",
];

export function AuthAside() {
  return h("aside", { className: "auth-aside", id: "auth-aside", "aria-label": "About ASAVEXA" },
    h("div", { className: "auth-aside-inner" },
      h("div", { className: "auth-aside-eyebrow" }, "Financial trust infrastructure"),
      h("p", { className: "auth-aside-tag" }, "Don't just report the number. Prove it."),
      h("ul", { className: "auth-aside-list" }, AUTH_POINTS.map((t) => h("li", {}, t)))));
}
