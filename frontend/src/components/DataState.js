import { h } from "../lib/vdom.js";

/**
 * Shared loading/empty/error state helpers (Section 17: "every page
 * must implement loading, success, empty, error ... avoid blank
 * screens"). Factored out here because seven new functional areas
 * built in this pass all need the exact same three states — Dashboard
 * and AuditWorkspace each inlined their own one-off empty-state markup
 * (Section 5's "no fabricated feature," not a redesign target), but
 * repeating that seven more times would be the accidental duplication
 * Section 22 asks this pass to avoid, not legitimate module-specific
 * behavior. Every one of these is a pure function — no fetching, no
 * DOM access — matching every other component in this app.
 */

export function LoadingState(message) {
  return h("div", { className: "loading-state" }, message || "Loading…");
}

export function ErrorState({ message, onRetry }) {
  return h(
    "div",
    { className: "alert alert-error", role: "alert" },
    h("div", {}, message || "Something went wrong."),
    onRetry
      ? h("button", { className: "btn btn-secondary", style: "margin-top:8px;", onClick: onRetry }, "Try again")
      : null
  );
}

export function EmptyState({ title, message }) {
  return h(
    "div",
    { className: "empty-state card" },
    h("h3", {}, title || "Nothing here yet"),
    message ? h("p", {}, message) : null
  );
}

/** A user without the permission to view a section — distinct from an
 * empty result set (Section 17: "permission denied" is its own state,
 * never indistinguishable from "there is nothing to show"). */
export function PermissionDeniedState({ message }) {
  return h(
    "div",
    { className: "empty-state card" },
    h("h3", {}, "You don't have access to this"),
    h("p", {}, message || "Ask an administrator to grant the permission this area requires.")
  );
}
