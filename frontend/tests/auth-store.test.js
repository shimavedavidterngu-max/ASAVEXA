import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { AuthStore } from "../src/state/auth-store.js";

function makeStore() {
  const data = new Map();
  const storage = {
    getItem: (k) => (data.has(k) ? data.get(k) : null),
    setItem: (k, v) => data.set(k, v),
    removeItem: (k) => data.delete(k),
  };
  return { store: new AuthStore({ storage }), storage };
}

describe("AuthStore", () => {
  test("starts unauthenticated with no persisted session", () => {
    const { store } = makeStore();
    assert.equal(store.isAuthenticated(), false);
    assert.equal(store.hasSelectedOrganisation(), false);
    assert.equal(store.getToken(), null);
  });

  test("setSession makes the store authenticated and clears any prior org", () => {
    const { store } = makeStore();
    store.setOrganisation("org-1", "OWNER"); // stray call before login, shouldn't matter
    store.setSession("tok-abc", { id: "u1", email: "a@b.com" });
    assert.equal(store.isAuthenticated(), true);
    assert.equal(store.getToken(), "tok-abc");
    assert.equal(store.hasSelectedOrganisation(), false, "a fresh session must not carry over a stale org");
  });

  test("setOrganisation records org id and role from the backend's resolved membership", () => {
    const { store } = makeStore();
    store.setSession("tok-abc", { id: "u1" });
    store.setOrganisation("org-1", "FINANCE_OFFICER");
    const state = store.getState();
    assert.equal(state.organisationId, "org-1");
    assert.equal(state.role, "FINANCE_OFFICER");
  });

  test("clear() resets everything and removes persisted storage", () => {
    const { store, storage } = makeStore();
    store.setSession("tok-abc", { id: "u1" });
    store.setOrganisation("org-1", "OWNER");
    store.clear();
    assert.equal(store.isAuthenticated(), false);
    assert.equal(store.getState().organisationId, null);
    assert.equal(storage.getItem("asavexa.session"), null);
  });

  test("session survives being reloaded from the same storage (simulates a page refresh)", () => {
    const { store: store1, storage } = makeStore();
    store1.setSession("tok-xyz", { id: "u2" });
    store1.setOrganisation("org-2", "APPROVER");

    const store2 = new (store1.constructor)({ storage });
    assert.equal(store2.isAuthenticated(), true);
    assert.equal(store2.getState().organisationId, "org-2");
    assert.equal(store2.getState().role, "APPROVER");
  });

  test("subscribers are notified on every state change", () => {
    const { store } = makeStore();
    const seen = [];
    store.subscribe((state) => seen.push(state.token));
    store.setSession("tok-1", { id: "u1" });
    store.setOrganisation("org-1", "OWNER");
    store.clear();
    assert.deepEqual(seen, ["tok-1", "tok-1", null]);
  });

  test("unsubscribe stops further notifications", () => {
    const { store } = makeStore();
    let count = 0;
    const unsubscribe = store.subscribe(() => { count += 1; });
    store.setSession("tok-1", { id: "u1" });
    unsubscribe();
    store.setOrganisation("org-1", "OWNER");
    assert.equal(count, 1);
  });

  test("corrupted storage content is treated as no session, not a crash", () => {
    const { storage } = makeStore();
    storage.setItem("asavexa.session", "{not-valid-json");
    const store = new AuthStore({ storage });
    assert.equal(store.isAuthenticated(), false);
  });
});
