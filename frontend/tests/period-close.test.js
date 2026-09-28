import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { PeriodClose } from "../src/pages/PeriodClose.js";

function collectByTag(vnode, tag, acc = []) {
  if (!vnode || typeof vnode !== "object") return acc;
  if (vnode.tag === tag) acc.push(vnode);
  for (const child of vnode.children || []) collectByTag(child, tag, acc);
  return acc;
}
function buttonWithText(vnode, text) {
  return collectByTag(vnode, "button").find((b) => JSON.stringify(b.children).includes(text));
}

describe("PeriodClose — permission gate", () => {
  test("a role without period_close:read is denied access", () => {
    const vnode = PeriodClose({ role: "DONOR", periods: [] });
    assert.ok(JSON.stringify(vnode).includes("don't have access"));
  });
});

describe("PeriodClose — no period selected", () => {
  test("shows an explicit empty state instead of an empty/misleading history table", () => {
    const vnode = PeriodClose({ role: "OWNER", periods: [] });
    const text = JSON.stringify(vnode);
    assert.ok(text.includes("No period selected"));
    assert.ok(!text.includes("No close processes recorded"));
  });
});

describe("PeriodClose — readiness report", () => {
  test("shows the real per-control findings and messages, never a generic 'blocked'", () => {
    const readiness = {
      is_ready: false,
      findings: [
        { control: "TRIAL_BALANCE_BALANCED", status: "PASSED", blocking: true, message: "Trial balance is balanced." },
        { control: "UNPOSTED_JOURNALS", status: "FAILED", blocking: true, message: "2 unposted draft journals remain in this period." },
      ],
    };
    const vnode = PeriodClose({ role: "OWNER", periods: [], selectedPeriodId: "p1", readiness });
    const text = JSON.stringify(vnode);
    assert.ok(text.includes("2 unposted draft journals remain in this period."));
    assert.ok(text.includes("Not ready"));
  });

  test("a ready report is labeled Ready, not silently identical to not-ready", () => {
    const readiness = { is_ready: true, findings: [] };
    const vnode = PeriodClose({ role: "OWNER", periods: [], selectedPeriodId: "p1", readiness });
    assert.ok(JSON.stringify(vnode).includes("Ready"));
  });
});

describe("PeriodClose — process actions respect status and permission", () => {
  test("CONTROLS_FAILED shows the blocked explanation and offers Recheck to period_close:request", () => {
    const activeProcess = { id: "pc1", status: "CONTROLS_FAILED", requested_by: "u1", requested_at: "2026-01-05" };
    const vnode = PeriodClose({ role: "ACCOUNTANT", periods: [], selectedPeriodId: "p1", activeProcess, onRecheck: () => {} });
    const text = JSON.stringify(vnode);
    assert.ok(text.includes("Blocked by the readiness report"));
    assert.ok(buttonWithText(vnode, "Recheck controls"));
  });

  test("READY_FOR_CLOSE with no review yet offers 'Mark reviewed' to period_close:review, not Approve", () => {
    const activeProcess = { id: "pc1", status: "READY_FOR_CLOSE", requested_by: "u1", requested_at: "2026-01-05", reviewed_by: null };
    const vnode = PeriodClose({ role: "FINANCE_OFFICER", periods: [], selectedPeriodId: "p1", activeProcess, onReview: () => {} });
    assert.ok(buttonWithText(vnode, "Mark reviewed"));
    assert.ok(!buttonWithText(vnode, "Approve close"));
  });

  test("READY_FOR_CLOSE after review offers Approve only to period_close:approve", () => {
    const activeProcess = { id: "pc1", status: "READY_FOR_CLOSE", requested_by: "u1", requested_at: "2026-01-05", reviewed_by: "u2" };
    const withApprove = PeriodClose({ role: "FINANCE_OFFICER", periods: [], selectedPeriodId: "p1", activeProcess, onApprove: () => {}, onApproveReasonChange: () => {} });
    assert.ok(buttonWithText(withApprove, "Approve close"));
    const withoutApprove = PeriodClose({ role: "ACCOUNTANT", periods: [], selectedPeriodId: "p1", activeProcess, onApprove: () => {}, onApproveReasonChange: () => {} });
    assert.ok(!buttonWithText(withoutApprove, "Approve close"));
  });

  test("a CLOSED process states plainly that the period is now locked", () => {
    const activeProcess = { id: "pc1", status: "CLOSED", requested_by: "u1", requested_at: "2026-01-05", approved_by: "u2" };
    const vnode = PeriodClose({ role: "OWNER", periods: [], selectedPeriodId: "p1", activeProcess });
    assert.ok(JSON.stringify(vnode).includes("now locked"));
  });

  test("clicking Approve calls onApprove with the process id", () => {
    let approvedId = null;
    const activeProcess = { id: "pc1", status: "READY_FOR_CLOSE", requested_by: "u1", requested_at: "2026-01-05", reviewed_by: "u2" };
    const vnode = PeriodClose({ role: "FINANCE_OFFICER", periods: [], selectedPeriodId: "p1", activeProcess, onApprove: (id) => { approvedId = id; }, onApproveReasonChange: () => {} });
    buttonWithText(vnode, "Approve close").props.onClick();
    assert.equal(approvedId, "pc1");
  });
});

describe("PeriodClose — history", () => {
  test("shows an explicit empty state when no close process has ever been recorded", () => {
    const vnode = PeriodClose({ role: "OWNER", periods: [], selectedPeriodId: "p1", processes: [] });
    assert.ok(JSON.stringify(vnode).includes("No close processes recorded"));
  });
});
