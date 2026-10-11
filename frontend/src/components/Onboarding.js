import { h } from "../lib/vdom.js";
import { Seal } from "./AiDock.js";
import { LoadingState } from "./DataState.js";
import { CATEGORIES, progress, joinDetails } from "../lib/onboarding.js";

/**
 * What a signed-in person sees before an organisation is open: choose one, create one, or find out how to join one.
 * Every control does something real. Joining is honest: the server has no invitation system, so an administrator adds the person.
 */
export function ProgressBar({ current }) {
  const steps = progress(current);
  return h("ol", { className: "ob-progress", id: "ob-progress", "aria-label": "Progress" },
    steps.map((s) => h("li", { className: `ob-step is-${s.state}`, "data-step": s.id, "aria-current": s.state === "current" ? "step" : undefined },
      h("span", { className: "ob-num", "aria-hidden": "true" }, s.state === "done" ? "✓" : String(s.number)),
      h("span", { className: "ob-steplabel" }, s.label, h("span", { className: "sr-only" }, s.state === "done" ? " (done)" : s.state === "current" ? " (current step)" : " (to do)")))));
}

function shell(children, { user, onSignOut }) {
  return h("div", { className: "ob", id: "onboarding" },
    h("header", { className: "ob-head" },
      h("div", { className: "ob-brand" }, Seal({ size: 30 }), h("span", {}, "ASAVEXA")),
      h("div", { className: "ob-who" }, user && user.email ? h("span", { id: "ob-email" }, user.email) : null,
        h("button", { className: "linklike", id: "ob-signout", onClick: onSignOut }, "Sign out"))),
    h("main", { className: "ob-main" }, children));
}

const err = (id, msg) => (msg ? h("div", { className: "ob-err", id: `${id}-err`, role: "alert" }, msg) : null);

function createForm(p) {
  const { form, errors, pending, error } = p;
  return h("form", { className: "card ob-card", id: "ob-create", noValidate: true, onSubmit: (e) => { e.preventDefault(); p.onCreate(); } },
    h("h2", { id: "ob-h-create" }, "Create an organisation"),
    h("p", { className: "hm-muted" }, "You will become its Owner. The server decides roles, and nothing you choose here can give anyone extra permissions."),
    error ? h("div", { className: "alert alert-error", id: "ob-error", role: "alert" }, error) : null,
    h("div", { className: "field" },
      h("label", { for: "ob-name" }, "Organisation name"),
      h("input", { id: "ob-name", name: "name", value: form.name, maxlength: "120", autocomplete: "organization", required: true, "aria-invalid": errors.name ? "true" : undefined, "aria-describedby": errors.name ? "ob-name-err" : undefined, onInput: (e) => p.onField("name", e.target.value) }),
      err("ob-name", errors.name)),
    h("div", { className: "field" },
      h("label", { for: "ob-category" }, "What kind of organisation is it?"),
      h("select", { id: "ob-category", name: "category", "aria-invalid": errors.category ? "true" : undefined, "aria-describedby": errors.category ? "ob-category-err" : undefined, onChange: (e) => p.onField("category", e.target.value) },
        h("option", { value: "", selected: !form.category }, "Choose one…"),
        CATEGORIES.map((c) => h("option", { value: c, selected: form.category === c }, c))),
      err("ob-category", errors.category)),
    h("div", { className: "ob-actions" },
      h("button", { type: "submit", className: "btn btn-primary", id: "ob-create-go", disabled: pending }, pending ? "Creating…" : "Create and continue"),
      p.canGoBack ? h("button", { type: "button", className: "btn btn-secondary", id: "ob-back", onClick: p.onBack, disabled: pending }, "Back") : null));
}

function joinHelp(p) {
  const d = joinDetails(p.user);
  return h("section", { className: "card ob-card", id: "ob-join", "aria-labelledby": "ob-h-join" },
    h("h2", { id: "ob-h-join" }, "Join an existing organisation"),
    h("p", {}, "ASAVEXA does not send invitations yet. To join, ask an administrator of that organisation to add you under ", h("strong", {}, "Administration"), ", and give them these details:"),
    h("dl", { className: "ob-details" },
      h("dt", {}, "Your email"), h("dd", { id: "ob-join-email" }, d.email || "Not available"),
      h("dt", {}, "Your account ID"), h("dd", { className: "mono", id: "ob-join-id" }, d.id || "Not available")),
    h("div", { className: "ob-actions" },
      d.id ? h("button", { className: "btn btn-secondary", id: "ob-copy", onClick: p.onCopy }, p.copied ? "Copied" : "Copy my account ID") : null,
      h("button", { className: "btn btn-primary", id: "ob-recheck", onClick: p.onRecheck, disabled: p.checking }, p.checking ? "Checking…" : "I have been added, check again"),
      p.canGoBack ? h("button", { className: "btn btn-secondary", id: "ob-back", onClick: p.onBack }, "Back") : null),
    p.checkMessage ? h("p", { className: "hm-muted", id: "ob-check-msg", role: "status" }, p.checkMessage) : null);
}

function choose(p) {
  return h("section", { className: "ob-choose", "aria-labelledby": "ob-h-choose" },
    h("h2", { id: "ob-h-choose" }, "Welcome. Let's get you to your organisation."),
    h("p", { className: "hm-muted" }, "You are signed in, but you do not belong to an organisation yet."),
    h("div", { className: "ob-two" },
      h("button", { className: "card ob-option", id: "ob-opt-create", onClick: () => p.onMode("create") }, h("strong", {}, "Create an organisation"), h("span", {}, "Start a new set of books and become its Owner.")),
      h("button", { className: "card ob-option", id: "ob-opt-join", onClick: () => p.onMode("join") }, h("strong", {}, "Join an existing one"), h("span", {}, "Ask an administrator to add you. Nothing to set up yourself."))));
}

function picker(p) {
  return h("section", { className: "card ob-card", id: "ob-picker", "aria-labelledby": "ob-h-pick" },
    h("h2", { id: "ob-h-pick" }, "Select an organisation"),
    h("p", { className: "hm-muted" }, "You belong to more than one. Choose where to work now. You can switch later from the top bar."),
    h("ul", { className: "ob-orgs" }, p.orgs.map((o) => h("li", {}, h("button", { className: "ob-org", "data-org": o.id, onClick: () => p.onSelect(o.id), disabled: p.pending }, h("strong", {}, o.name || o.id), h("span", { className: "mono" }, o.id))))),
    h("div", { className: "ob-actions" },
      h("button", { className: "btn btn-secondary", id: "ob-new", onClick: () => p.onMode("create") }, "Create a new organisation"),
      h("button", { className: "btn btn-secondary", id: "ob-join-more", onClick: () => p.onMode("join") }, "Join another")),
    p.error ? h("div", { className: "alert alert-error", id: "ob-error", role: "alert" }, p.error) : null,
    p.onSecurity ? h("p", { className: "ob-fine" }, h("a", { href: "#", id: "picker-security", onClick: (e) => { e.preventDefault(); p.onSecurity(); } }, "Security: set up two-step sign-in or manage my devices")) : null);
}

/** `mode`: "auto" shows the picker (or the first-time choice when there is no organisation), "create" and "join" show those forms. */
export function Onboarding(p) {
  let body;
  const none = p.orgs && p.orgs.length === 0;
  if (p.orgs === null) body = LoadingState("Looking for your organisations…");
  else if (p.orgs === false) body = h("div", { className: "alert alert-error", id: "ob-load-error", role: "alert" }, "Your organisations could not be loaded. ", h("button", { className: "linklike", id: "ob-retry", onClick: p.onRetry }, "Try again"));
  else if (p.mode === "create") body = createForm({ ...p, canGoBack: true, onBack: () => p.onMode("auto") });
  else if (p.mode === "join") body = joinHelp({ ...p, canGoBack: true, onBack: () => p.onMode("auto") });
  else body = none ? choose(p) : picker(p);
  return shell([ProgressBar({ current: "organisation" }), body], p);
}
