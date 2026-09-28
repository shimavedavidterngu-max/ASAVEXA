/**
 * A minimal hash-based router. No dependency, no build step — matches
 * every other choice in this frontend. Deliberately small: route
 * matching logic is pure (testable), only the `start()`/`navigate()`
 * methods touch `window`/`location` (browser-only, matching the same
 * testability split as lib/vdom.js's render()).
 */

export function matchRoute(routes, path) {
  for (const route of routes) {
    const paramNames = [];
    const pattern = route.path.replace(/:([^/]+)/g, (_, name) => {
      paramNames.push(name);
      return "([^/]+)";
    });
    const match = path.match(new RegExp(`^${pattern}$`));
    if (match) {
      const params = Object.fromEntries(paramNames.map((name, i) => [name, decodeURIComponent(match[i + 1])]));
      return { route, params };
    }
  }
  return null;
}

export class Router {
  constructor(routes, { onChange } = {}) {
    this.routes = routes;
    this.onChange = onChange || (() => {});
  }

  currentPath() {
    const hash = window.location.hash.slice(1);
    return hash || "/";
  }

  start() {
    window.addEventListener("hashchange", () => this._handle());
    this._handle();
  }

  navigate(path) {
    window.location.hash = path;
  }

  _handle() {
    const path = this.currentPath();
    const matched = matchRoute(this.routes, path);
    this.onChange(matched, path);
  }
}
