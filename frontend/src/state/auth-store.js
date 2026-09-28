/**
 * AuthStore — holds session token, current user, and current
 * organisation/role. Deliberately separate from "UI state" (Section
 * 21: server state / auth state / org state / UI state kept apart).
 *
 * Token storage: sessionStorage in the browser (cleared when the tab
 * closes — a reasonable default for a financial/audit tool; never
 * localStorage for a bearer token, and never a cookie here since this
 * app has no CSRF-protection layer built for cookie-based auth). This
 * module never touches `window`/`sessionStorage` directly except
 * through the injected `storage` — making it fully testable with an
 * in-memory fake, matching the same testability discipline as
 * api/client.js.
 */

const STORAGE_KEY = "asavexa.session";

function makeMemoryStorage() {
  const data = new Map();
  return {
    getItem: (k) => (data.has(k) ? data.get(k) : null),
    setItem: (k, v) => data.set(k, v),
    removeItem: (k) => data.delete(k),
  };
}

export class AuthStore {
  constructor({ storage, listeners } = {}) {
    this.storage = storage || (typeof sessionStorage !== "undefined" ? sessionStorage : makeMemoryStorage());
    this._listeners = new Set(listeners || []);
    this._state = this._load();
  }

  _load() {
    const raw = this.storage.getItem(STORAGE_KEY);
    if (!raw) return this._empty();
    try {
      return { ...this._empty(), ...JSON.parse(raw) };
    } catch {
      return this._empty();
    }
  }

  _empty() {
    return { token: null, user: null, organisationId: null, role: null };
  }

  _persist() {
    if (this._state.token) {
      this.storage.setItem(STORAGE_KEY, JSON.stringify(this._state));
    } else {
      this.storage.removeItem(STORAGE_KEY);
    }
    for (const listener of this._listeners) listener(this.getState());
  }

  getState() {
    return { ...this._state };
  }

  getToken() {
    return this._state.token;
  }

  isAuthenticated() {
    return Boolean(this._state.token);
  }

  hasSelectedOrganisation() {
    return Boolean(this._state.organisationId);
  }

  /** Called after a successful login. */
  setSession(token, user) {
    this._state = { ...this._empty(), token, user };
    this._persist();
  }

  /** Called after select-organisation succeeds — the role comes from
   * the membership the backend resolved, never chosen by the client
   * (see security-architecture.md's "Organization architecture"). */
  setOrganisation(organisationId, role) {
    this._state = { ...this._state, organisationId, role };
    this._persist();
  }

  /** Called on logout, or when the API client reports a 401 (session
   * expired/revoked server-side) — the two situations that end a
   * session; see ApiClient's onUnauthenticated hook. */
  clear() {
    this._state = this._empty();
    this._persist();
  }

  subscribe(listener) {
    this._listeners.add(listener);
    return () => this._listeners.delete(listener);
  }
}
