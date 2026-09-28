import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { StatusBadge, STATUS_TONE } from "../src/components/StatusBadge.js";
import { PermissionGate, allowed } from "../src/components/PermissionGate.js";
import { h } from "../src/lib/vdom.js";
import { PERMISSIONS } from "../src/lib/permissions.js";

describe("StatusBadge", () => {
  test("maps a known FAIL status to the fail tone", () => {
    const vnode = StatusBadge({ status: "FAIL" });
    assert.equal(vnode.props.className, "badge badge-fail");
    assert.deepEqual(vnode.children, ["Fail"]);
  });

  test("maps VERIFIED to the pass tone (a real FindingStatus value)", () => {
    const vnode = StatusBadge({ status: "VERIFIED" });
    assert.equal(vnode.props.className, "badge badge-pass");
  });

  test("an unrecognized status falls back to neutral rather than crashing", () => {
    const vnode = StatusBadge({ status: "SOME_FUTURE_STATUS_NOT_YET_KNOWN" });
    assert.equal(vnode.props.className, "badge badge-neutral");
  });

  test("an explicit label overrides the humanized status text", () => {
    const vnode = StatusBadge({ status: "PASS", label: "All clear" });
    assert.deepEqual(vnode.children, ["All clear"]);
  });

  test("every backend enum value referenced in the app has a tone mapping", () => {
    // A representative sample of real backend enum values this app
    // displays — not exhaustive, but proves the mapping table wasn't
    // left empty or guessed.
    const realValues = [
      "PASS", "FAIL", "WARNING", "REQUIRES_REVIEW", "NOT_APPLICABLE",
      "OPEN", "UNDER_REVIEW", "REMEDIATION_REQUIRED", "RESOLVED", "VERIFIED", "CLOSED",
      "DRAFT", "POSTED", "REVERSED", "LOCKED",
      "RECONCILED", "UNMATCHED", "REVIEW_REQUIRED",
    ];
    for (const value of realValues) {
      assert.ok(value in STATUS_TONE, `missing tone mapping for real status ${value}`);
    }
  });
});

describe("PermissionGate", () => {
  const financeOfficer = "FINANCE_OFFICER";
  const accountant = "ACCOUNTANT";

  test("renders children when the role holds the permission", () => {
    const result = PermissionGate(
      { role: financeOfficer, permission: PERMISSIONS.FINDING_VERIFY },
      [h("button", {}, "Verify")]
    );
    assert.equal(result.tag, null); // Fragment
    assert.equal(result.children[0].tag, "button");
  });

  test("renders the fallback (not the children) when the role lacks the permission", () => {
    const fallback = h("span", {}, "Not permitted");
    const result = PermissionGate(
      { role: accountant, permission: PERMISSIONS.FINDING_VERIFY, fallback },
      [h("button", {}, "Verify")]
    );
    assert.equal(result, fallback);
  });

  test("defaults to rendering nothing (null) when no fallback is given", () => {
    const result = PermissionGate({ role: accountant, permission: PERMISSIONS.FINDING_VERIFY }, [
      h("button", {}, "Verify"),
    ]);
    assert.equal(result, null);
  });

  test("allowed() gives a plain boolean for non-DOM decisions", () => {
    assert.equal(allowed(financeOfficer, PERMISSIONS.FINDING_VERIFY), true);
    assert.equal(allowed(accountant, PERMISSIONS.FINDING_VERIFY), false);
  });

  test("the maker/checker split is visible through the gate itself: ACCOUNTANT sees remediate, not verify", () => {
    assert.equal(allowed(accountant, PERMISSIONS.FINDING_REMEDIATE), true);
    assert.equal(allowed(accountant, PERMISSIONS.FINDING_VERIFY), false);
  });
});
