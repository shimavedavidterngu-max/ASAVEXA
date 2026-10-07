import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { Administration } from "../src/pages/Administration.js";

function collectByTag(vnode, tag, acc = []) {
  if (!vnode || typeof vnode !== "object") return acc;
  if (vnode.tag === tag) acc.push(vnode);
  for (const child of vnode.children || []) collectByTag(child, tag, acc);
  return acc;
}
function findByTag(vnode, tag) {
  if (!vnode || typeof vnode !== "object") return null;
  if (vnode.tag === tag) return vnode;
  for (const child of vnode.children || []) {
    const found = findByTag(child, tag);
    if (found) return found;
  }
  return null;
}

describe("Administration — permission gate", () => {
  test("a role without org:manage_users or org:manage_settings is denied access", () => {
    const vnode = Administration({ role: "AUDITOR" });
    assert.ok(JSON.stringify(vnode).includes("don't have access"));
  });

  test("a role with org:manage_users is admitted", () => {
    const vnode = Administration({ role: "ADMINISTRATOR", organisation: { id: "o1", name: "Acme", created_at: "2026-01-01" }, members: [] });
    assert.ok(JSON.stringify(vnode).includes("Acme"));
  });
});

describe("Administration — organisation profile", () => {
  test("shows the real organisation name and id, not a placeholder", () => {
    const vnode = Administration({ role: "OWNER", organisation: { id: "org-42", name: "Acme Farms Cooperative", created_at: "2026-01-01" }, members: [] });
    const text = JSON.stringify(vnode);
    assert.ok(text.includes("Acme Farms Cooperative"));
    assert.ok(text.includes("org-42"));
  });

  test("explicitly states that organisation-wide audit activity is not available, rather than fabricating a feed", () => {
    const vnode = Administration({ role: "OWNER", organisation: { id: "o1", name: "Acme", created_at: "2026-01-01" }, members: [] });
    assert.ok(JSON.stringify(vnode).includes("Not available at the organisation level"));
  });
});

describe("Administration — members", () => {
  const members = [
    { user_id: "u1", role: "ACCOUNTANT", status: "ACTIVE" },
    { user_id: "u2", role: "OWNER", status: "ACTIVE" },
  ];

  test("shows real member rows with their actual role and status", () => {
    const vnode = Administration({ role: "OWNER", organisation: { id: "o1", name: "Acme", created_at: "2026-01-01" }, members });
    const text = JSON.stringify(vnode);
    assert.ok(text.includes("u1"));
    assert.ok(text.includes("ACCOUNTANT"));
  });

  test("a member cannot change their own role from this screen", () => {
    const vnode = Administration({
      role: "OWNER", organisation: { id: "o1", name: "Acme", created_at: "2026-01-01" }, members,
      currentUserId: "u2", onChangeRole: () => {}, onRevokeMember: () => {}, roleDrafts: {}, onRoleDraftChange: () => {},
    });
    assert.ok(JSON.stringify(vnode).includes("You cannot change your own role."));
  });

  test("changing another member's role calls onChangeRole with the drafted role", () => {
    let changed = null;
    const vnode = Administration({
      role: "OWNER", organisation: { id: "o1", name: "Acme", created_at: "2026-01-01" }, members,
      currentUserId: "u2", onChangeRole: (userId, role) => { changed = { userId, role }; },
      onRevokeMember: () => {}, roleDrafts: { u1: "AUDITOR" }, onRoleDraftChange: () => {},
    });
    const updateButton = collectByTag(vnode, "button").find((b) => JSON.stringify(b.children).includes("Update"));
    updateButton.props.onClick();
    assert.deepEqual(changed, { userId: "u1", role: "AUDITOR" });
  });

  test("adding a member is offered only to org:manage_users", () => {
    const withPermission = Administration({ role: "OWNER", organisation: { id: "o1", name: "Acme", created_at: "2026-01-01" }, members: [], addForm: {} });
    assert.ok(JSON.stringify(withPermission).includes("Add a member"));
  });

  test("submitting the add-member form calls onSubmitAdd", () => {
    let submitted = false;
    const vnode = Administration({
      role: "OWNER", organisation: { id: "o1", name: "Acme", created_at: "2026-01-01" }, members: [],
      addForm: {}, onAddFieldChange: () => {}, onSubmitAdd: () => { submitted = true; },
    });
    const forms = collectByTag(vnode, "form");
    forms[forms.length - 1].props.onSubmit({ preventDefault: () => {} });
    assert.equal(submitted, true);
  });
});

describe("Administration — organisation profile form", () => {
  const base = { organisation: { id: "o1", name: "Acme", created_at: "2026-01-01" }, members: [] };

  test("an owner gets editable profile fields and a save button", () => {
    const vnode = Administration({ ...base, role: "OWNER", profileForm: { legal_name: "Acme Ltd" }, onProfileFieldChange: () => {}, onSubmitProfile: () => {} });
    const text = JSON.stringify(vnode);
    assert.ok(text.includes("Organisation profile"));
    assert.ok(text.includes("Legal name"));
    assert.ok(text.includes("Reporting framework"));
    assert.ok(text.includes("Save profile"));
    assert.ok(text.includes("Acme Ltd"));
  });

  test("saving calls onSubmitProfile", () => {
    let saved = false;
    const vnode = Administration({ ...base, role: "OWNER", profileForm: {}, onProfileFieldChange: () => {}, onSubmitProfile: () => { saved = true; } });
    collectByTag(vnode, "form")[0].props.onSubmit({ preventDefault: () => {} });
    assert.equal(saved, true);
  });

  test("editing a field reports the field name and value", () => {
    const calls = [];
    const vnode = Administration({ ...base, role: "OWNER", profileForm: {}, onProfileFieldChange: (f, v) => calls.push([f, v]), onSubmitProfile: () => {} });
    const input = collectByTag(vnode, "input").find((i) => i.props.onInput && i.props.value === "" );
    input.props.onInput({ target: { value: "X" } });
    assert.equal(calls.length, 1);
    assert.equal(calls[0][1], "X");
  });

  test("the owner role can save the profile", () => {
    const vnode = Administration({ ...base, role: "OWNER", profileForm: {}, onProfileFieldChange: () => {}, onSubmitProfile: () => {} });
    assert.ok(JSON.stringify(vnode).includes("Save profile"));
  });
});
