import { h, Fragment } from "../lib/vdom.js";
import { can } from "../lib/permissions.js";

/**
 * PermissionGate — the ONE place UI decides whether to show a
 * privileged action. Used everywhere a maker/checker distinction
 * matters (Section 10): a Compliance finding's "Verify" button must
 * never render for a role lacking finding:verify, "Remediate" must
 * never render without finding:remediate, etc.
 *
 * This is explicitly a UX convenience, never a security boundary — the
 * backend independently re-checks every one of these on the real
 * request and will reject it regardless of what this function decided
 * to render (see docs/frontend-runtime-verification.md, "Permission-
 * aware UI is UX, not security", and lib/permissions.js's own
 * docstring). Hiding a button here is a courtesy; rejecting the
 * request is the backend's job and happens either way.
 *
 * No wrapping element (uses Fragment) — a gated action often lives
 * inside a table row or button toolbar, where an extra wrapping <div>
 * would break the surrounding layout.
 */
export function PermissionGate({ role, permission, fallback = null }, children) {
  if (can(role, permission)) {
    return Array.isArray(children) ? Fragment(children) : children;
  }
  return fallback;
}

/** Non-DOM helper for places that need a plain boolean rather than a
 * vnode wrapper (e.g. deciding whether to include a column at all). */
export function allowed(role, permission) {
  return can(role, permission);
}
