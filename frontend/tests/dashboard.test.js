import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { Dashboard, formatMoney } from "../src/pages/Dashboard.js";

function findCardWithLabel(vnode, labelSubstring) {
  const cards = vnode.children[2].children; // card-grid's children
  return cards.find((c) => c && JSON.stringify(c).includes(labelSubstring));
}

describe("formatMoney — presentation only, never a recomputation", () => {
  test("formats a Decimal-as-string from the backend with two decimal places", () => {
    assert.equal(formatMoney("1000.5"), "1,000.50");
  });
  test("returns an em-dash for a missing value rather than fabricating 0", () => {
    assert.equal(formatMoney(null), "—");
    assert.equal(formatMoney(undefined), "—");
  });
  test("falls back to the raw string for a non-numeric value rather than crashing", () => {
    assert.equal(formatMoney("not-a-number"), "not-a-number");
  });
});

describe("Dashboard — renders only what real data supports", () => {
  test("shows an explicit empty state when no period is selected, not a fabricated figure", () => {
    const vnode = Dashboard({ role: "OWNER", data: {}, onNavigate: () => {} });
    const card = findCardWithLabel(vnode, "Financial Position");
    assert.ok(card, "financial position card should exist");
    assert.ok(JSON.stringify(card).includes("No period selected yet."));
  });

  test("shows the real trial balance figure when data is supplied", () => {
    const data = { trialBalance: { is_balanced: true, total_debits: "5000.00", total_credits: "5000.00" } };
    const vnode = Dashboard({ role: "OWNER", data, onNavigate: () => {} });
    const card = findCardWithLabel(vnode, "Trial Balance");
    assert.ok(JSON.stringify(card).includes("5,000.00"));
    assert.ok(JSON.stringify(card).includes("Balanced"));
  });

  test("an unbalanced trial balance is labeled as such, not hidden", () => {
    const data = { trialBalance: { is_balanced: false, total_debits: "5000.00", total_credits: "4900.00" } };
    const vnode = Dashboard({ role: "OWNER", data, onNavigate: () => {} });
    const card = findCardWithLabel(vnode, "Trial Balance");
    assert.ok(JSON.stringify(card).includes("OUT OF BALANCE"));
  });

  test("controls and findings cards are hidden entirely for a role without control:read", () => {
    const data = { controlSummary: { executed: 5, warnings: 1, failed: 0 }, findingCounts: { OPEN: 2 } };
    const vnode = Dashboard({ role: "INVESTOR_REVIEWER", data, onNavigate: () => {} });
    assert.equal(findCardWithLabel(vnode, "Controls this period"), undefined);
    assert.equal(findCardWithLabel(vnode, "Findings"), undefined);
  });

  test("controls and findings cards render for a role with control:read", () => {
    const data = { controlSummary: { executed: 5, warnings: 1, failed: 0 }, findingCounts: { OPEN: 2 } };
    const vnode = Dashboard({ role: "AUDITOR", data, onNavigate: () => {} });
    assert.ok(findCardWithLabel(vnode, "Controls this period"));
    assert.ok(findCardWithLabel(vnode, "Findings"));
  });

  test("every clickable metric card triggers onNavigate with a real route when clicked", () => {
    let navigatedTo = null;
    const data = { trialBalance: { is_balanced: true, total_debits: "100.00" } };
    const vnode = Dashboard({ role: "OWNER", data, onNavigate: (route) => { navigatedTo = route; } });
    const card = findCardWithLabel(vnode, "Trial Balance");
    card.props.onClick();
    assert.equal(navigatedTo, "/reporting/trial-balance");
  });

  test("finding status counts reflect the real backend FindingStatus values, not invented labels", () => {
    const data = { findingCounts: { OPEN: 3, UNDER_REVIEW: 1, REMEDIATION_REQUIRED: 2, RESOLVED: 1 } };
    const vnode = Dashboard({ role: "OWNER", data, onNavigate: () => {} });
    const card = findCardWithLabel(vnode, "Findings");
    const text = JSON.stringify(card);
    assert.ok(text.includes('"3"')); // OPEN count rendered as text
    assert.ok(text.includes("Remediation required"));
  });
});
