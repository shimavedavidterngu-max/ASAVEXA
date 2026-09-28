import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { Compliance } from "../src/pages/Compliance.js";

function collectByTag(vnode, tag, acc = []) {
  if (!vnode || typeof vnode !== "object") return acc;
  if (vnode.tag === tag) acc.push(vnode);
  for (const child of vnode.children || []) collectByTag(child, tag, acc);
  return acc;
}
function buttonWithText(vnode, text) {
  return collectByTag(vnode, "button").find((b) => JSON.stringify(b.children).includes(text));
}

describe("Compliance — permission gate", () => {
  test("a role without control:read is denied access", () => {
    const vnode = Compliance({ role: "DONOR", view: "controls" });
    assert.ok(JSON.stringify(vnode).includes("don't have access"));
  });
});

describe("Compliance — controls tab", () => {
  test("Seed standard controls and control:manage actions are hidden without control:manage", () => {
    const controls = [{ id: "c1", code: "REC-001", name: "Reconciliation exceptions", domain: "RECONCILIATION", severity: "HIGH", is_active: true }];
    const vnode = Compliance({ role: "ACCOUNTANT", view: "controls", controls, executions: [] });
    assert.ok(!buttonWithText(vnode, "Seed standard controls"));
    assert.ok(!buttonWithText(vnode, "Deactivate"));
  });

  test("control:manage sees Seed, Define, and Deactivate", () => {
    const controls = [{ id: "c1", code: "REC-001", name: "Reconciliation exceptions", domain: "RECONCILIATION", severity: "HIGH", is_active: true }];
    const vnode = Compliance({ role: "ADMINISTRATOR", view: "controls", controls, executions: [], defineForm: {} });
    assert.ok(buttonWithText(vnode, "Seed standard controls"));
    assert.ok(buttonWithText(vnode, "Deactivate"));
  });

  test("Execute is offered only to control:execute", () => {
    const controls = [{ id: "c1", code: "REC-001", name: "x", domain: "RECONCILIATION", severity: "HIGH", is_active: true }];
    const withExecute = Compliance({ role: "ACCOUNTANT", view: "controls", controls, executions: [] });
    assert.ok(buttonWithText(withExecute, "Execute"));
    const withoutExecute = Compliance({ role: "REVIEWER", view: "controls", controls, executions: [] });
    assert.ok(!buttonWithText(withoutExecute, "Execute"));
  });

  test("real execution results (including a real ControlResult value) render verbatim", () => {
    const executions = [{ id: "ex1", control_id: "c1", result: "FAIL", explanation: "3 unresolved reconciliation exceptions found.", reviewed_by: null }];
    const vnode = Compliance({ role: "OWNER", view: "controls", controls: [], executions });
    assert.ok(JSON.stringify(vnode).includes("3 unresolved reconciliation exceptions found."));
  });
});

describe("Compliance — findings tab", () => {
  test("shows an empty state when there are no findings", () => {
    const vnode = Compliance({ role: "OWNER", view: "findings", findings: [] });
    assert.ok(JSON.stringify(vnode).includes("No findings recorded"));
  });

  test("clicking a finding row navigates to its detail route", () => {
    let navigatedTo = null;
    const findings = [{ id: "f1", description: "Unresolved exception", severity: "HIGH", status: "OPEN", created_at: "2026-01-05" }];
    const vnode = Compliance({ role: "OWNER", view: "findings", findings, onNavigate: (p) => { navigatedTo = p; } });
    const row = collectByTag(vnode, "tr").find((tr) => typeof tr.props.onClick === "function");
    row.props.onClick();
    assert.equal(navigatedTo, "/compliance/findings/f1");
  });
});

describe("Compliance — finding detail: the five-permission separation (Section 9)", () => {
  const baseFinding = { id: "f1", description: "Unresolved exception", severity: "HIGH", status: "OPEN", created_by: "u1" };

  test("OPEN: Start review is offered only to finding:manage", () => {
    const withManage = Compliance({ role: "FINANCE_OFFICER", view: "finding-detail", finding: baseFinding, reasonInputs: {}, onReasonChange: () => {}, onStartReview: () => {} });
    assert.ok(buttonWithText(withManage, "Start review"));
    const withoutManage = Compliance({ role: "ACCOUNTANT", view: "finding-detail", finding: baseFinding, reasonInputs: {}, onReasonChange: () => {}, onStartReview: () => {} });
    assert.ok(!buttonWithText(withoutManage, "Start review"));
  });

  test("UNDER_REVIEW: send-back/mark-remediation-required/resolve-without-remediation are all finding:manage, never finding:remediate or finding:verify", () => {
    const finding = { ...baseFinding, status: "UNDER_REVIEW" };
    // APPROVER has finding:verify but not finding:manage — must NOT see these triage actions.
    const approver = Compliance({ role: "APPROVER", view: "finding-detail", finding, reasonInputs: {}, onReasonChange: () => {} });
    assert.ok(!buttonWithText(approver, "Send back to open"));
    assert.ok(!buttonWithText(approver, "Mark remediation required"));
    // FINANCE_OFFICER has finding:manage — must see them.
    const manager = Compliance({ role: "FINANCE_OFFICER", view: "finding-detail", finding, reasonInputs: {}, onReasonChange: () => {} });
    assert.ok(buttonWithText(manager, "Mark remediation required"));
  });

  test("send-back-to-open requires a reason before it can be submitted", () => {
    const finding = { ...baseFinding, status: "UNDER_REVIEW" };
    const vnode = Compliance({ role: "FINANCE_OFFICER", view: "finding-detail", finding, reasonInputs: {}, onReasonChange: () => {} });
    const button = buttonWithText(vnode, "Send back to open");
    assert.equal(button.props.disabled, true);
  });

  test("CLOSED: reopen is finding:manage; VERIFIED: close is finding:verify — never the same permission", () => {
    const closed = Compliance({ role: "FINANCE_OFFICER", view: "finding-detail", finding: { ...baseFinding, status: "CLOSED" }, reasonInputs: {}, onReasonChange: () => {} });
    assert.ok(buttonWithText(closed, "Reopen"));

    const verified = Compliance({ role: "APPROVER", view: "finding-detail", finding: { ...baseFinding, status: "VERIFIED" }, reasonInputs: {}, onReasonChange: () => {} });
    assert.ok(buttonWithText(verified, "Close finding"));

    // APPROVER holds finding:verify but not finding:manage — must not see Reopen on a CLOSED finding.
    const approverOnClosed = Compliance({ role: "APPROVER", view: "finding-detail", finding: { ...baseFinding, status: "CLOSED" }, reasonInputs: {}, onReasonChange: () => {} });
    assert.ok(!buttonWithText(approverOnClosed, "Reopen"));
  });
});

describe("Compliance — remediation lifecycle: remediate vs. verify are disjoint", () => {
  const finding = { id: "f1", description: "x", severity: "HIGH", status: "REMEDIATION_REQUIRED", created_by: "u1" };

  test("no remediation yet: create-remediation form is offered only to finding:remediate", () => {
    const withRemediate = Compliance({ role: "ACCOUNTANT", view: "finding-detail", finding, remediation: null, remediationForm: {}, reasonInputs: {}, onReasonChange: () => {} });
    assert.ok(JSON.stringify(withRemediate).includes("Create remediation"));
    const withoutRemediate = Compliance({ role: "APPROVER", view: "finding-detail", finding, remediation: null, remediationForm: {}, reasonInputs: {}, onReasonChange: () => {} });
    assert.ok(!JSON.stringify(withoutRemediate).includes("Create remediation"));
  });

  test("COMPLETED remediation: Verify/Reject are offered to finding:verify, never to finding:remediate alone", () => {
    const remediation = { id: "r1", action: "Resolve exception", owner: "u2", status: "COMPLETED" };
    const verifier = Compliance({ role: "APPROVER", view: "finding-detail", finding, remediation, reasonInputs: {}, onReasonChange: () => {} });
    assert.ok(buttonWithText(verifier, "Verify"));

    const remediator = Compliance({ role: "ACCOUNTANT", view: "finding-detail", finding, remediation, reasonInputs: {}, onReasonChange: () => {} });
    assert.ok(!buttonWithText(remediator, "Verify"));
  });

  test("a VERIFIED remediation shows who verified it, not just a status badge", () => {
    const remediation = { id: "r1", action: "Resolve exception", owner: "u2", status: "VERIFIED", verified_by: "amaka" };
    const vnode = Compliance({ role: "OWNER", view: "finding-detail", finding, remediation, reasonInputs: {}, onReasonChange: () => {} });
    assert.ok(JSON.stringify(vnode).includes("amaka"));
  });
});
