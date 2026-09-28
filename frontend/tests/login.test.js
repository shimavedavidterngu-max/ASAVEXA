import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { Login, OrganisationPicker } from "../src/pages/Login.js";

function findByTag(vnode, tag) {
  if (!vnode || typeof vnode !== "object") return null;
  if (vnode.tag === tag) return vnode;
  for (const child of vnode.children || []) {
    const found = findByTag(child, tag);
    if (found) return found;
  }
  return null;
}

describe("Login", () => {
  test("submitting the form calls onSubmit with email and password", () => {
    let submitted = null;
    const vnode = Login({ onSubmit: (creds) => { submitted = creds; }, onSwitchMode: () => {} });
    const form = findByTag(vnode, "form");
    const fakeEvent = {
      preventDefault: () => {},
      target: { elements: { email: { value: "a@b.com" }, password: { value: "correct-horse-battery" } } },
    };
    form.props.onSubmit(fakeEvent);
    assert.deepEqual(submitted, { email: "a@b.com", password: "correct-horse-battery" });
  });

  test("shows an error message when one is provided, and none when absent", () => {
    const withError = Login({ error: "Invalid email or password.", onSubmit: () => {}, onSwitchMode: () => {} });
    assert.ok(JSON.stringify(withError).includes("Invalid email or password."));

    const withoutError = Login({ onSubmit: () => {}, onSwitchMode: () => {} });
    assert.ok(!JSON.stringify(withoutError).includes("alert-error"));
  });

  test("the submit button is disabled while a request is pending", () => {
    const vnode = Login({ pending: true, onSubmit: () => {}, onSwitchMode: () => {} });
    const button = findByTag(vnode, "button");
    assert.equal(button.props.disabled, true);
    assert.equal(button.children[0], "Please wait…");
  });

  test("register mode shows the 15-character password hint (matches the real backend minimum)", () => {
    const vnode = Login({ mode: "register", onSubmit: () => {}, onSwitchMode: () => {} });
    assert.ok(JSON.stringify(vnode).includes("At least 15 characters."));
  });

  test("clicking the mode switch link calls onSwitchMode with the other mode", () => {
    let switchedTo = null;
    const vnode = Login({ mode: "login", onSubmit: () => {}, onSwitchMode: (m) => { switchedTo = m; } });
    const link = findByTag(vnode, "a");
    link.props.onClick({ preventDefault: () => {} });
    assert.equal(switchedTo, "register");
  });
});

describe("OrganisationPicker", () => {
  test("shows a create-organisation prompt when the user has none — never fabricates an org", () => {
    const vnode = OrganisationPicker({ organisations: [], onSelect: () => {}, onCreateNew: () => {} });
    assert.ok(JSON.stringify(vnode).includes("don't belong to any organisation yet"));
  });

  test("lists every real organisation returned by the API, and clicking one selects it", () => {
    let selected = null;
    const orgs = [{ id: "org-1", name: "Meridian Textiles" }, { id: "org-2", name: "Kadena Ltd" }];
    const vnode = OrganisationPicker({ organisations: orgs, onSelect: (id) => { selected = id; }, onCreateNew: () => {} });
    const text = JSON.stringify(vnode);
    assert.ok(text.includes("Meridian Textiles"));
    assert.ok(text.includes("Kadena Ltd"));
    // Simulate clicking the second org's card.
    const orgCards = vnode.children[1].children;
    orgCards[1].props.onClick();
    assert.equal(selected, "org-2");
  });
});
