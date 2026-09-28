import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { EvidenceChain, __CHAIN_STAGES__ } from "../src/components/EvidenceChain.js";

/** Flattens the Fragment-of-[node, arrow] structure EvidenceChain
 * returns into just the chain-node vnodes, for easy assertion. */
function extractNodes(vnode) {
  return vnode.children
    .map((fragment) => fragment.children[0])
    .filter(Boolean);
}

describe("EvidenceChain — never fabricates a relationship", () => {
  test("covers exactly the eight documented stages, in order", () => {
    assert.deepEqual(__CHAIN_STAGES__, [
      "transaction", "evidence", "reconciliation", "control",
      "finding", "remediation", "verification", "audit_event",
    ]);
  });

  test("an empty links array renders 'No linked record' for every single stage", () => {
    const vnode = EvidenceChain({ links: [] });
    const nodes = extractNodes(vnode);
    assert.equal(nodes.length, 8);
    for (const node of nodes) {
      assert.ok(node.props.className.includes("chain-missing"));
      // The text "No linked record" must be literally present — not
      // omitted, not replaced with a blank/empty node.
      const text = JSON.stringify(node.children);
      assert.ok(text.includes("No linked record"));
    }
  });

  test("a real transaction with no evidence shows evidence as missing, not silently skipped", () => {
    const vnode = EvidenceChain({
      links: [{ stage: "transaction", label: "Journal J-1001" }],
    });
    const nodes = extractNodes(vnode);
    assert.equal(nodes.length, 8, "all 8 stages must still be present, not just the ones with data");
    assert.ok(!nodes[0].props.className.includes("chain-missing"));
    assert.ok(nodes[1].props.className.includes("chain-missing"), "evidence stage must show as missing");
  });

  test("a fully linked chain shows every stage as populated, none missing", () => {
    const links = [
      { stage: "transaction", label: "Journal J-1001" },
      { stage: "evidence", label: "invoice-042.pdf", status: "VERIFIED" },
      { stage: "reconciliation", label: "Jan reconciliation", status: "RECONCILED" },
      { stage: "control", label: "ACC-001 Trial balance" },
      { stage: "finding", label: "FND-88", status: "CLOSED" },
      { stage: "remediation", label: "Re-post correcting entry", status: "COMPLETED" },
      { stage: "verification", label: "Verified by K. Osei" },
      { stage: "audit_event", label: "FINDING_CLOSED" },
    ];
    const vnode = EvidenceChain({ links });
    const nodes = extractNodes(vnode);
    assert.equal(nodes.length, 8);
    for (const node of nodes) {
      assert.ok(!node.props.className.includes("chain-missing"));
    }
  });

  test("clicking a linked node with an href calls onNavigate with that href", () => {
    let navigatedTo = null;
    const vnode = EvidenceChain({
      links: [{ stage: "finding", label: "FND-1", href: "/compliance/findings/FND-1" }],
      onNavigate: (href) => { navigatedTo = href; },
    });
    const findingNode = extractNodes(vnode)[4];
    findingNode.props.onClick();
    assert.equal(navigatedTo, "/compliance/findings/FND-1");
  });

  test("a node with no href is not made clickable even if onNavigate is provided", () => {
    const vnode = EvidenceChain({
      links: [{ stage: "control", label: "ACC-001" }], // no href
      onNavigate: () => { throw new Error("should not be called"); },
    });
    const controlNode = extractNodes(vnode)[3];
    assert.equal(controlNode.props.onClick, undefined);
  });

  test("an unrecognized stage name in the data is simply ignored, not rendered as a ninth node", () => {
    const vnode = EvidenceChain({
      links: [{ stage: "not_a_real_stage", label: "should not appear" }],
    });
    assert.equal(extractNodes(vnode).length, 8);
  });
});
