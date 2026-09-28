import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { AuditWorkspace, buildChainLinks } from "../src/pages/AuditWorkspace.js";

describe("buildChainLinks — maps raw API shapes without fabricating anything", () => {
  test("all-empty input produces an all-null links array (every stage renders 'No linked record')", () => {
    const links = buildChainLinks({});
    assert.equal(links.length, 8);
    assert.ok(links.every((l) => l === null));
  });

  test("a journal alone produces only the transaction link, nothing else guessed", () => {
    const links = buildChainLinks({ journal: { id: "j1", description: "Sale", status: "POSTED" } });
    assert.equal(links[0].stage, "transaction");
    assert.equal(links[0].label, "Sale");
    assert.equal(links[0].status, "POSTED");
    for (let i = 1; i < 8; i++) assert.equal(links[i], null);
  });

  test("a finding without a control_code does not fabricate a control link", () => {
    const links = buildChainLinks({
      finding: { id: "f1", description: "Outstanding reconciliation", status: "OPEN" },
    });
    assert.equal(links[3], null, "control stage must stay null when finding.control_code is absent");
    assert.equal(links[4].stage, "finding");
  });

  test("a remediation with no verified_by produces no verification link", () => {
    const links = buildChainLinks({
      remediation: { id: "r1", action: "Fix it", status: "IN_PROGRESS", verified_by: null },
    });
    assert.equal(links[5].stage, "remediation");
    assert.equal(links[6], null, "verification stage must stay null until verified_by is set");
  });

  test("a verified remediation produces both remediation and verification links", () => {
    const links = buildChainLinks({
      remediation: { id: "r1", action: "Fix it", status: "VERIFIED", verified_by: "kwame", verified_at: "2026-01-10" },
    });
    assert.equal(links[6].stage, "verification");
    assert.ok(links[6].label.includes("kwame"));
  });

  test("audit events summarize count and most recent action, not a fabricated single event", () => {
    const links = buildChainLinks({
      auditEvents: [{ action: "FINDING_CREATED" }, { action: "FINDING_CLOSED" }],
    });
    assert.equal(links[7].stage, "audit_event");
    assert.ok(links[7].label.includes("2"));
    assert.equal(links[7].meta, "FINDING_CLOSED");
  });

  test("a fully populated set of inputs produces all 8 links with correct hrefs", () => {
    const links = buildChainLinks({
      journal: { id: "j1", description: "Sale", status: "POSTED" },
      evidence: { id: "e1", original_filename: "invoice.pdf", status: "VERIFIED" },
      reconciliationTxn: { id: "t1", status: "RECONCILED" },
      finding: { id: "f1", description: "desc", status: "CLOSED", control_code: "REC-001", control_id: "c1" },
      remediation: { id: "r1", action: "act", status: "VERIFIED", verified_by: "kwame", verified_at: "2026-01-10" },
      auditEvents: [{ action: "FINDING_CLOSED" }],
    });
    assert.ok(links.every((l) => l !== null));
    assert.equal(links[1].href, "/evidence/e1");
    assert.equal(links[3].href, "/compliance/controls/c1");
    assert.equal(links[4].href, "/compliance/findings/f1");
  });
});

describe("AuditWorkspace page", () => {
  test("shows the empty state when nothing has been searched yet", () => {
    const vnode = AuditWorkspace({ onSearch: () => {}, onNavigate: () => {} });
    assert.ok(JSON.stringify(vnode).includes("Nothing traced yet"));
  });

  test("shows an error alert instead of a fabricated chain when the search fails", () => {
    const vnode = AuditWorkspace({ onSearch: () => {}, onNavigate: () => {}, error: "Journal not found." });
    const text = JSON.stringify(vnode);
    assert.ok(text.includes("Journal not found."));
    assert.ok(!text.includes("Nothing traced yet"));
  });

  test("renders the journal summary and the chain once a journal is found", () => {
    const journal = { id: "j1", description: "Cash sale", status: "POSTED", date: "2026-01-05", currency: "USD" };
    const chainLinks = [{ stage: "transaction", label: "Cash sale", status: "POSTED" }];
    const vnode = AuditWorkspace({ journal, chainLinks, onSearch: () => {}, onNavigate: () => {} });
    const text = JSON.stringify(vnode);
    assert.ok(text.includes("Cash sale"));
    assert.ok(text.includes("Traceability chain"));
  });

  test("pressing Enter in the search box triggers onSearch with the typed value", () => {
    let searched = null;
    const vnode = AuditWorkspace({ onSearch: (q) => { searched = q; }, onNavigate: () => {} });
    const inputVnode = findByTag(vnode, "input");
    assert.ok(inputVnode, "search input must be present in the tree");
    inputVnode.props.onKeydown({ key: "Enter", target: { value: "j-1001" } });
    assert.equal(searched, "j-1001");
  });
});

/** Depth-first search for the first vnode with the given tag —
 * robust against the exact nesting shape of the component tree,
 * unlike hand-counted index paths. */
function findByTag(vnode, tag) {
  if (!vnode || typeof vnode !== "object") return null;
  if (vnode.tag === tag) return vnode;
  for (const child of vnode.children || []) {
    const found = findByTag(child, tag);
    if (found) return found;
  }
  return null;
}
