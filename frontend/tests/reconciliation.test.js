import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { Reconciliation } from "../src/pages/Reconciliation.js";

function findByTag(vnode, tag) {
  if (!vnode || typeof vnode !== "object") return null;
  if (vnode.tag === tag) return vnode;
  for (const child of vnode.children || []) {
    const found = findByTag(child, tag);
    if (found) return found;
  }
  return null;
}
function collectByTag(vnode, tag, acc = []) {
  if (!vnode || typeof vnode !== "object") return acc;
  if (vnode.tag === tag) acc.push(vnode);
  for (const child of vnode.children || []) collectByTag(child, tag, acc);
  return acc;
}

describe("Reconciliation — permission gate", () => {
  test("a role without reconciliation:read is denied access", () => {
    const vnode = Reconciliation({ role: "DONOR", view: "list", reconciliations: [] });
    assert.ok(JSON.stringify(vnode).includes("don't have access"));
  });
});

describe("Reconciliation — list view", () => {
  test("shows an empty state when there are no reconciliations yet", () => {
    const vnode = Reconciliation({ role: "OWNER", view: "list", reconciliations: [] });
    assert.ok(JSON.stringify(vnode).includes("No reconciliations yet"));
  });

  test("'New reconciliation' is offered only to a role with reconciliation:create", () => {
    const withPermission = Reconciliation({ role: "ACCOUNTANT", view: "list", reconciliations: [] });
    assert.ok(JSON.stringify(withPermission).includes("New reconciliation"));
    const withoutPermission = Reconciliation({ role: "READ_ONLY", view: "list", reconciliations: [] });
    assert.ok(!JSON.stringify(withoutPermission).includes("New reconciliation"));
  });

  test("clicking a reconciliation row navigates to its detail route", () => {
    let navigatedTo = null;
    const reconciliations = [{ id: "r1", name: "Jan bank", bank_account_id: "ba1", period_start: "2026-01-01", period_end: "2026-01-31", status: "DRAFT" }];
    const vnode = Reconciliation({ role: "OWNER", view: "list", reconciliations, onNavigate: (p) => { navigatedTo = p; } });
    // The header row (inside <thead>) has no onClick — only body rows
    // do, so find the row that actually carries one rather than the
    // first <tr> in document order.
    const clickableRow = collectByTag(vnode, "tr").find((tr) => typeof tr.props.onClick === "function");
    assert.ok(clickableRow, "a clickable data row must be present");
    clickableRow.props.onClick();
    assert.equal(navigatedTo, "/reconciliation/r1");
  });
});

describe("Reconciliation — detail view: matched/unmatched transaction states", () => {
  const detail = { id: "r1", name: "Jan bank", bank_account_id: "ba1", status: "DRAFT" };

  test("counts real transaction statuses rather than fabricating summary numbers", () => {
    const transactions = [
      { id: "t1", status: "MATCHED", transaction_date: "2026-01-02", description: "x", debit_amount: "10.00", credit_amount: "0.00" },
      { id: "t2", status: "UNMATCHED", transaction_date: "2026-01-03", description: "y", debit_amount: "0.00", credit_amount: "5.00" },
      { id: "t3", status: "UNMATCHED", transaction_date: "2026-01-04", description: "z", debit_amount: "0.00", credit_amount: "5.00" },
    ];
    const vnode = Reconciliation({ role: "OWNER", view: "detail", detail, transactions });
    const text = JSON.stringify(vnode);
    assert.ok(text.includes('"1"')); // Matched count
    assert.ok(text.includes('"2"')); // Unmatched count
  });

  test("an UNMATCHED transaction offers manual match only to a role with reconciliation:match", () => {
    const transactions = [{ id: "t1", status: "UNMATCHED", transaction_date: "2026-01-02", description: "x", debit_amount: "10.00", credit_amount: "0.00" }];
    const withPermission = Reconciliation({ role: "FINANCE_OFFICER", view: "detail", detail, transactions, matchJournalId: {}, onMatchJournalIdChange: () => {}, onManualMatch: () => {} });
    const matchButtons = (v) => collectByTag(v, "button").filter((b) => JSON.stringify(b.children) === '["Match"]');
    assert.equal(matchButtons(withPermission).length, 1);
    const withoutPermission = Reconciliation({ role: "REVIEWER", view: "detail", detail, transactions, matchJournalId: {}, onMatchJournalIdChange: () => {}, onManualMatch: () => {} });
    assert.equal(matchButtons(withoutPermission).length, 0);
  });

  test("a MATCHED transaction offers Approve/Reject only to a role with reconciliation:approve", () => {
    const transactions = [{ id: "t1", status: "MATCHED", transaction_date: "2026-01-02", description: "x", debit_amount: "10.00", credit_amount: "0.00", matched_journal_id: "j1" }];
    const withPermission = Reconciliation({
      role: "FINANCE_OFFICER", view: "detail", detail, transactions,
      onApproveTransaction: () => {}, onRejectMatch: () => {}, matchRejectReason: {}, onMatchRejectReasonChange: () => {},
    });
    assert.ok(JSON.stringify(withPermission).includes("Approve"));

    const withoutPermission = Reconciliation({
      role: "ACCOUNTANT", view: "detail", detail, transactions,
      onApproveTransaction: () => {}, onRejectMatch: () => {}, matchRejectReason: {}, onMatchRejectReasonChange: () => {},
    });
    const approveButtons = collectByTag(withoutPermission, "button").filter((b) => JSON.stringify(b.children).includes("Approve"));
    assert.equal(approveButtons.length, 0);
  });

  test("submit-for-review is offered only while DRAFT, to a role with reconciliation:create", () => {
    const draft = Reconciliation({ role: "ACCOUNTANT", view: "detail", detail: { ...detail, status: "DRAFT" }, transactions: [], onSubmitReconciliation: () => {} });
    assert.ok(JSON.stringify(draft).includes("Submit for review"));

    const submitted = Reconciliation({ role: "ACCOUNTANT", view: "detail", detail: { ...detail, status: "SUBMITTED" }, transactions: [], onSubmitReconciliation: () => {} });
    assert.ok(!JSON.stringify(submitted).includes("Submit for review"));
  });

  test("approve/reject the whole reconciliation is offered only while SUBMITTED, to a role with reconciliation:approve", () => {
    const vnode = Reconciliation({
      role: "FINANCE_OFFICER", view: "detail", detail: { ...detail, status: "SUBMITTED" }, transactions: [],
      onApproveReconciliation: () => {}, onRejectReconciliation: () => {}, rejectReason: "", onRejectReasonChange: () => {},
    });
    assert.ok(JSON.stringify(vnode).includes("Approve"));
  });

  test("a rejected reconciliation shows its rejection reason", () => {
    const vnode = Reconciliation({ role: "OWNER", view: "detail", detail: { ...detail, status: "REJECTED", rejection_reason: "Unresolved exceptions." }, transactions: [] });
    assert.ok(JSON.stringify(vnode).includes("Unresolved exceptions."));
  });
});

describe("Reconciliation — new reconciliation form", () => {
  test("submitting calls onSubmitCreate", () => {
    let submitted = false;
    const vnode = Reconciliation({ role: "ACCOUNTANT", view: "new", form: {}, onFieldChange: () => {}, onSubmitCreate: () => { submitted = true; } });
    findByTag(vnode, "form").props.onSubmit({ preventDefault: () => {} });
    assert.equal(submitted, true);
  });

  test("a creation error is surfaced", () => {
    const vnode = Reconciliation({ role: "ACCOUNTANT", view: "new", form: {}, formError: "Bank account not found.", onFieldChange: () => {}, onSubmitCreate: () => {} });
    assert.ok(JSON.stringify(vnode).includes("Bank account not found."));
  });
});
