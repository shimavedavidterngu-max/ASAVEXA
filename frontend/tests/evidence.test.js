import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { Evidence } from "../src/pages/Evidence.js";

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

describe("Evidence — permission gate", () => {
  test("a role without evidence:read is denied access", () => {
    const vnode = Evidence({ role: "DONOR", view: "list", items: [] });
    assert.ok(JSON.stringify(vnode).includes("don't have access"));
  });
});

describe("Evidence — list view", () => {
  test("shows an empty state, not a fabricated table, when there is no evidence yet", () => {
    const vnode = Evidence({ role: "OWNER", view: "list", items: [] });
    assert.ok(JSON.stringify(vnode).includes("No evidence records"));
  });

  test("renders a real evidence row with its actual status and a truncated hash, never a fabricated hash", () => {
    const items = [{
      id: "e1", original_filename: "invoice.pdf", type: "INVOICE", status: "VERIFIED",
      file_hash: "abcdef0123456789abcdef0123456789", uploaded_by: "u1",
    }];
    const vnode = Evidence({ role: "OWNER", view: "list", items });
    const text = JSON.stringify(vnode);
    assert.ok(text.includes("invoice.pdf"));
    assert.ok(text.includes("abcdef012345")); // first 12 chars of the real hash
  });

  test("the upload form is hidden for a role without evidence:upload", () => {
    const vnode = Evidence({ role: "AUDITOR", view: "list", items: [] });
    assert.ok(!JSON.stringify(vnode).includes("Upload evidence"));
  });

  test("the upload form is shown for a role with evidence:upload, and submitting calls onSubmitUpload", () => {
    let submitted = false;
    const vnode = Evidence({
      role: "ACCOUNTANT", view: "list", items: [], uploadForm: { type: "INVOICE" },
      onUploadFieldChange: () => {}, onFileSelected: () => {}, onSubmitUpload: () => { submitted = true; },
    });
    assert.ok(JSON.stringify(vnode).includes("Upload evidence"));
    const form = findByTag(vnode, "form");
    form.props.onSubmit({ preventDefault: () => {} });
    assert.equal(submitted, true);
  });

  test("an upload error is surfaced, not swallowed", () => {
    const vnode = Evidence({
      role: "ACCOUNTANT", view: "list", items: [], uploadForm: {}, uploadError: "File too large.",
      onUploadFieldChange: () => {}, onFileSelected: () => {}, onSubmitUpload: () => {},
    });
    assert.ok(JSON.stringify(vnode).includes("File too large."));
  });

  test("clicking a row navigates to that evidence record's detail route", () => {
    let navigatedTo = null;
    const items = [{ id: "e1", original_filename: "invoice.pdf", type: "INVOICE", status: "UPLOADED" }];
    const vnode = Evidence({ role: "OWNER", view: "list", items, onNavigate: (p) => { navigatedTo = p; } });
    // The header row (inside <thead>) has no onClick — only body rows
    // do, so find the row that actually carries one rather than the
    // first <tr> in document order.
    const row = collectByTag(vnode, "tr").find((tr) => typeof tr.props.onClick === "function");
    assert.ok(row, "a clickable data row must be present");
    row.props.onClick();
    assert.equal(navigatedTo, "/evidence/e1");
  });
});

describe("Evidence — detail view", () => {
  test("a record not found renders an explicit empty state", () => {
    const vnode = Evidence({ role: "OWNER", view: "detail", detail: null });
    assert.ok(JSON.stringify(vnode).includes("Evidence record not found"));
  });

  test("shows the real hash, uploader, and status verbatim", () => {
    const detail = {
      id: "e1", original_filename: "invoice.pdf", type: "INVOICE", status: "UPLOADED",
      file_hash: "deadbeefcafefeed", uploaded_by: "kwame", uploaded_at: "2026-01-05T00:00:00Z", size_bytes: 4096, content_type: "application/pdf",
    };
    const vnode = Evidence({ role: "OWNER", view: "detail", detail });
    const text = JSON.stringify(vnode);
    assert.ok(text.includes("deadbeefcafefeed"));
    assert.ok(text.includes("kwame"));
  });

  test("Verify/Reject are offered only to a role with evidence:verify, and only while the status permits a decision", () => {
    const detail = { id: "e1", original_filename: "invoice.pdf", type: "INVOICE", status: "UPLOADED" };
    const withPermission = Evidence({ role: "FINANCE_OFFICER", view: "detail", detail, onVerify: () => {}, onReject: () => {}, onRejectReasonChange: () => {} });
    assert.ok(JSON.stringify(withPermission).includes("Verify"));

    const withoutPermission = Evidence({ role: "ACCOUNTANT", view: "detail", detail, onVerify: () => {}, onReject: () => {}, onRejectReasonChange: () => {} });
    const buttonTexts = collectButtons(withoutPermission).map((b) => JSON.stringify(b.children));
    assert.ok(!buttonTexts.some((t) => t.includes("Verify")));
  });

  test("a VERIFIED record no longer offers Verify/Reject", () => {
    const detail = { id: "e1", original_filename: "invoice.pdf", type: "INVOICE", status: "VERIFIED", verified_by: "amaka" };
    const vnode = Evidence({ role: "FINANCE_OFFICER", view: "detail", detail, onVerify: () => {}, onReject: () => {} });
    const text = JSON.stringify(vnode);
    const buttonTexts = collectButtons(vnode).map((b) => JSON.stringify(b.children));
    assert.ok(!buttonTexts.some((t) => t.includes("Verify")));
    assert.ok(text.includes("amaka"));
  });

  test("Reject is disabled until a reason is entered", () => {
    const detail = { id: "e1", original_filename: "invoice.pdf", type: "INVOICE", status: "UPLOADED" };
    const vnode = Evidence({ role: "FINANCE_OFFICER", view: "detail", detail, onVerify: () => {}, onReject: () => {}, rejectReason: "", onRejectReasonChange: () => {} });
    const buttons = collectButtons(vnode);
    const rejectButton = buttons.find((b) => JSON.stringify(b.children).includes("Reject"));
    assert.equal(rejectButton.props.disabled, true);
  });
});

function collectButtons(vnode, acc = []) {
  if (!vnode || typeof vnode !== "object") return acc;
  if (vnode.tag === "button") acc.push(vnode);
  for (const child of vnode.children || []) collectButtons(child, acc);
  return acc;
}
