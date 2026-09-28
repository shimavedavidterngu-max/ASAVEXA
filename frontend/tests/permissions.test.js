import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { can, PERMISSIONS, ROLE_PERMISSIONS } from "../src/lib/permissions.js";

describe("permission model — mirrors the real backend registry", () => {
  test("OWNER holds every permission", () => {
    for (const perm of Object.values(PERMISSIONS)) {
      assert.equal(can("OWNER", perm), true, `OWNER should hold ${perm}`);
    }
  });

  test("ACCOUNTANT can execute controls but not manage findings (maker, not manager)", () => {
    assert.equal(can("ACCOUNTANT", PERMISSIONS.CONTROL_EXECUTE), true);
    assert.equal(can("ACCOUNTANT", PERMISSIONS.FINDING_MANAGE), false);
  });

  test("ACCOUNTANT can remediate but not verify — Phase 4's maker/checker finding", () => {
    assert.equal(can("ACCOUNTANT", PERMISSIONS.FINDING_REMEDIATE), true);
    assert.equal(can("ACCOUNTANT", PERMISSIONS.FINDING_VERIFY), false);
  });

  test("APPROVER can verify but neither manage nor remediate findings", () => {
    assert.equal(can("APPROVER", PERMISSIONS.FINDING_VERIFY), true);
    assert.equal(can("APPROVER", PERMISSIONS.FINDING_MANAGE), false);
    assert.equal(can("APPROVER", PERMISSIONS.FINDING_REMEDIATE), false);
  });

  test("ADMINISTRATOR manages findings but cannot remediate or verify them", () => {
    assert.equal(can("ADMINISTRATOR", PERMISSIONS.FINDING_MANAGE), true);
    assert.equal(can("ADMINISTRATOR", PERMISSIONS.FINDING_REMEDIATE), false);
    assert.equal(can("ADMINISTRATOR", PERMISSIONS.FINDING_VERIFY), false);
  });

  test("READ_ONLY holds only read-style permissions, no mutation permission", () => {
    const granted = ROLE_PERMISSIONS.READ_ONLY;
    for (const perm of granted) {
      assert.ok(perm.endsWith(":read"), `READ_ONLY should not hold ${perm}`);
    }
  });

  test("INVESTOR_REVIEWER, DONOR, and REGULATOR hold no general permissions (Passport-only by design)", () => {
    for (const role of ["INVESTOR_REVIEWER", "DONOR", "REGULATOR"]) {
      assert.deepEqual(ROLE_PERMISSIONS[role], []);
    }
  });

  test("can() is false for an unknown role or a missing permission", () => {
    assert.equal(can("NOT_A_REAL_ROLE", PERMISSIONS.LEDGER_READ), false);
    assert.equal(can(null, PERMISSIONS.LEDGER_READ), false);
    assert.equal(can("OWNER", null), false);
  });

  test("every role referenced by ROLE_PERMISSIONS grants only real, known permission strings", () => {
    const realPerms = new Set(Object.values(PERMISSIONS));
    for (const [role, granted] of Object.entries(ROLE_PERMISSIONS)) {
      for (const perm of granted) {
        assert.ok(realPerms.has(perm), `${role} grants unknown permission string ${perm}`);
      }
    }
  });
});
