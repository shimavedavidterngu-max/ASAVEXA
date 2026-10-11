import { h } from "../lib/vdom.js";
import { groupOpen, roleLabel, initialOf, displayName } from "../lib/home.js";

/**
 * The parts of the signed-in frame: grouped side menu, top bar (menu button, breadcrumbs, search, organisation switcher,
 * user menu). Pure render functions; app.js owns the state and passes handlers. Every control here does something real.
 */

export function SideNav({ groups, navOpen, activeId, mobileOpen, onToggleGroup, onGo }) {
  return h("nav", { className: `app-sidebar${mobileOpen ? " is-open" : ""}`, id: "app-sidebar", "aria-label": "Main menu" },
    h("div", { className: "brand" }, "ASAVEXA", h("small", {}, "Don't just report it. Prove it.")),
    groups.map((g) => {
      if (g.id === "home") return g.items.map(({ item, active }) => h("a", { className: `nav-link nav-home${active ? " active" : ""}`, href: `#${item.path}`, id: "nav-home", "aria-current": active ? "page" : undefined, onClick: () => onGo() }, item.label));
      const open = groupOpen(g, navOpen, activeId);
      return h("div", { className: `nav-group${open ? " is-open" : ""}`, "data-group": g.id },
        h("button", { className: "nav-group-head", id: `nav-group-${g.id}`, "aria-expanded": open ? "true" : "false", "aria-controls": `nav-list-${g.id}`,
          onClick: () => onToggleGroup(g.id, open) },
          h("span", {}, g.label), h("span", { className: "nav-caret", "aria-hidden": "true" }, open ? "–" : "+")),
        open ? h("div", { className: "nav-list", id: `nav-list-${g.id}` }, g.items.map(({ item, active }) =>
          h("a", { className: `nav-link${active ? " active" : ""}`, href: `#${item.path}`, "aria-current": active ? "page" : undefined, onClick: () => onGo() }, item.label))) : null);
    }));
}

export function Breadcrumbs({ crumbs }) {
  return h("nav", { className: "crumbs", id: "crumbs", "aria-label": "You are here" },
    h("ol", {}, crumbs.map((c, i) => h("li", { "aria-current": i === crumbs.length - 1 ? "page" : undefined },
      c.path ? h("a", { href: `#${c.path}` }, c.label) : h("span", {}, c.label)))));
}

function searchBox({ search, results, onInput, onKey, onPick, onClose }) {
  const open = search.open && search.q.trim().length > 0;
  return h("div", { className: "gsearch", id: "gsearch" },
    h("label", { className: "sr-only", for: "gsearch-input" }, "Search pages"),
    h("input", { id: "gsearch-input", type: "search", placeholder: "Search pages", autocomplete: "off", value: search.q,
      role: "combobox", "aria-expanded": open ? "true" : "false", "aria-controls": "gsearch-list", "aria-autocomplete": "list",
      "aria-activedescendant": open && results.length ? `gs-${search.idx}` : undefined,
      onInput: (e) => onInput(e.target.value), onKeyDown: (e) => onKey(e, results), onFocus: () => onInput(search.q, true) }),
    open ? h("ul", { className: "gsearch-list", id: "gsearch-list", role: "listbox", "aria-label": "Matching pages" },
      results.length
        ? results.map((r, i) => h("li", { id: `gs-${i}`, role: "option", "aria-selected": i === search.idx ? "true" : "false", className: i === search.idx ? "is-on" : "" },
          h("a", { href: `#${r.path}`, onClick: () => onPick(r) }, h("strong", {}, r.label), r.group ? h("span", {}, r.group) : null)))
        : h("li", { className: "gsearch-none", id: "gsearch-none", role: "option", "aria-selected": "false" }, "No page matches that. Try a word like “evidence”, “tax” or “budget”.")) : null);
}

function orgMenu({ menu, orgs, orgId, orgLabel, switching, switchError, onToggle, onSwitch, onAll }) {
  const open = menu === "org";
  return h("div", { className: "menu-wrap", id: "org-wrap" },
    h("button", { className: "menu-btn", id: "org-btn", "aria-haspopup": "true", "aria-expanded": open ? "true" : "false", "aria-controls": "org-menu", onClick: () => onToggle("org") },
      h("span", { className: "menu-kicker" }, "Organisation"), h("span", { className: "menu-main", id: "org-label" }, orgLabel), h("span", { className: "nav-caret", "aria-hidden": "true" }, "▾")),
    open ? h("div", { className: "menu-pop", id: "org-menu", role: "menu", "aria-label": "Organisations" },
      orgs === null ? h("div", { className: "menu-note", id: "org-loading" }, "Loading your organisations…")
        : orgs === false ? h("div", { className: "menu-note menu-err", id: "org-error" }, "Your organisations could not be loaded. Try again in a moment.")
        : orgs.map((o) => h("button", { role: "menuitemradio", "aria-checked": o.id === orgId ? "true" : "false", className: `menu-item${o.id === orgId ? " is-current" : ""}`, "data-org": o.id, disabled: switching || undefined,
          onClick: () => (o.id === orgId ? onToggle(null) : onSwitch(o.id)) }, h("span", {}, o.name || o.id), o.id === orgId ? h("small", {}, "Current") : null)),
      switchError ? h("div", { className: "menu-note menu-err", id: "org-switch-error", role: "alert" }, switchError) : null,
      h("div", { className: "menu-sep" }),
      h("button", { role: "menuitem", className: "menu-item", id: "org-all", onClick: () => onAll() }, h("span", {}, "All organisations / create a new one"))) : null);
}

function userMenu({ menu, user, role, onToggle, onGo, onSignOut }) {
  const open = menu === "user";
  const name = displayName(user) || "Account";
  return h("div", { className: "menu-wrap", id: "user-wrap" },
    h("button", { className: "menu-btn menu-user", id: "user-btn", "aria-haspopup": "true", "aria-expanded": open ? "true" : "false", "aria-controls": "user-menu", "aria-label": `Account menu for ${name}`, onClick: () => onToggle("user") },
      h("span", { className: "avatar", "aria-hidden": "true" }, initialOf(user))),
    open ? h("div", { className: "menu-pop menu-right", id: "user-menu", role: "menu", "aria-label": "Account" },
      h("div", { className: "menu-who" }, h("strong", {}, user && user.email ? user.email : name), h("small", { id: "user-role" }, `Role: ${roleLabel(role)}`)),
      h("div", { className: "menu-sep" }),
      h("button", { role: "menuitem", className: "menu-item", id: "user-security", onClick: () => onGo("/security") }, h("span", {}, "Security and two-step sign-in")),
      h("button", { role: "menuitem", className: "menu-item", id: "user-diag", onClick: () => onGo("/diagnostics") }, h("span", {}, "Connection and self-test")),
      h("div", { className: "menu-sep" }),
      h("button", { role: "menuitem", className: "menu-item", id: "user-signout", onClick: () => onSignOut() }, h("span", {}, "Sign out"))) : null);
}

export function TopBar(p) {
  return h("header", { className: "app-topbar2", id: "app-topbar" },
    h("div", { className: "topbar-row" },
      h("button", { className: "nav-toggle", id: "nav-toggle", "aria-label": p.mobileOpen ? "Close the menu" : "Open the menu", "aria-expanded": p.mobileOpen ? "true" : "false", "aria-controls": "app-sidebar", onClick: () => p.onToggleNav() },
        h("span", {}), h("span", {}), h("span", {})),
      searchBox(p),
      h("div", { className: "topbar-right" }, orgMenu(p), userMenu(p))),
    Breadcrumbs({ crumbs: p.crumbs }));
}
