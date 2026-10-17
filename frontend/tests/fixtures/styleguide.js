// A living style guide for the Ledger Paper system. ILLUSTRATIVE DATA ONLY: nothing here is a real record.
// Open tests/fixtures/styleguide.html through any static web server (it is not part of the shipped site). Used by the browser checks.
import { h, mount } from "../../src/lib/vdom.js";
import { Figure, Num, focusMark } from "../../src/components/Figure.js";
import { ProofRail, normaliseSteps, proofState, focusRail } from "../../src/components/ProofRail.js";

const ROWS = [
  { id: "rev", label: "Revenue, March", amount: "18450320.50", currency: "NGN", steps: { source: { title: "Ledger JE-104", href: "#/accounting" }, evidence: { title: "Invoice batch 8841", meta: "Fingerprinted 2026-03-02", href: "#/evidence" }, review: { title: "Reviewed by A. Bello", meta: "2026-03-30" }, decision: { title: "Approved by the finance lead" }, action: { title: "Posted to the ledger" }, verification: { title: "Bank statement matched", meta: "2026-04-02" } } },
  { id: "cos", label: "Cost of sales, March", amount: "-9120044.10", currency: "NGN", steps: { source: { title: "Ledger JE-117", href: "#/accounting" }, evidence: { state: "pending", title: "2 of 5 supplier invoices attached" }, review: null, decision: null, action: { title: "Posted to the ledger" }, verification: undefined } },
  { id: "oth", label: "Other income, March", amount: "250000", currency: "NGN", steps: { source: { title: "Ledger JE-121", href: "#/accounting" }, evidence: null, review: null, decision: null, action: null, verification: null } },
  { id: "adj", label: "Year-end adjustment (not yet checked)", amount: "-1200.00", currency: "USD", steps: {} },
];
const state = { open: null, theme: "light", sector: "accounting" };

function statement() {
  return h("div", { className: "stmt-scroll" }, h("table", { className: "stmt", id: "sg-stmt" },
    h("caption", {}, "Income statement, March (illustrative)"),
    h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Line"), h("th", { scope: "col", className: "num" }, "Amount"))),
    h("tbody", {}, ROWS.map((r, i) => {
      const steps = normaliseSteps(r.steps);
      return h("tr", { id: `row-${r.id}` }, h("td", {}, r.label),
        h("td", { className: "num" }, Figure({ id: r.id, label: r.label, amount: r.amount, currency: r.currency, proof: proofState(steps), mark: i + 1, open: state.open === r.id, onToggle: () => toggle(r.id) })));
    }))));
}
function toggle(id) {
  const closing = state.open === id;
  state.open = closing ? null : id; draw();
  if (closing) focusMark(id); else focusRail(`${id}-rail`);
}
function close() { const id = state.open; state.open = null; draw(); if (id) focusMark(id); }
function margin() {
  const row = ROWS.find((r) => r.id === state.open);
  if (!row) return h("p", { className: "pr-summary", id: "sg-hint" }, "Select a numbered mark beside a figure to see the proof behind it.");
  return ProofRail({ id: `${row.id}-rail`, subject: row.label, steps: row.steps, sample: true, onClose: close });
}
function swatches() {
  return h("div", { className: "sg-row", id: "sg-sectors" }, ["accounting", "procurement", "health", "school", "university", "church", "ngo", "government"].map((s) =>
    h("div", { className: "sg-sw", "data-sector": s }, h("p", { className: "ledger-eyebrow" }, s), h("button", { type: "button", className: "sg-btn" }, "Action"))));
}
function draw() {
  document.documentElement.setAttribute("data-theme", state.theme);
  mount(h("main", { className: "sg", "data-sector": state.sector },
    h("div", { className: "sg-bar" },
      h("button", { type: "button", className: "btn btn-secondary", id: "sg-theme", onClick: () => { state.theme = state.theme === "light" ? "dark" : "light"; draw(); } }, `Theme: ${state.theme}`)),
    h("h1", {}, "ASAVEXA Ledger Paper"),
    h("p", { className: "pr-summary" }, "Illustrative data only. Nothing on this page is a real record."),
    h("section", { "aria-labelledby": "sg-h-fig" }, h("h2", { id: "sg-h-fig" }, "Figures"),
      h("div", { className: "sg-row" }, Figure({ id: "a", label: "a", amount: "1234567.5", currency: "USD", size: "xl" }), Figure({ id: "b", label: "b", amount: "-98.4", currency: "EUR", size: "lg" }), Figure({ id: "c", label: "c", amount: "0", currency: "GBP" }), Figure({ id: "d", label: "d", amount: "n/a", currency: "USD" }), h("span", {}, "Count: ", Num({ value: "1042", minFraction: 0 })))),
    h("section", { "aria-labelledby": "sg-h-ledger" }, h("h2", { id: "sg-h-ledger" }, "A statement, with the proof in the margin"),
      h("div", { className: "ledger", id: "sg-ledger" }, h("div", { className: "ledger-main" }, h("p", { className: "ledger-eyebrow" }, "Accounting"), statement()), h("aside", { className: "ledger-margin", "aria-label": "Proof for the selected figure" }, margin()))),
    h("section", { "aria-labelledby": "sg-h-states" }, h("h2", { id: "sg-h-states" }, "Every step state"),
      h("div", { className: "ledger-margin", style: "position:static; max-width:420px;" }, ProofRail({ id: "gallery", subject: "a sample figure", sample: true, steps: { source: { title: "A record" }, evidence: { state: "pending", title: "Being attached" }, review: null, decision: undefined, action: { title: "Done" }, verification: null }, vocab: { source: "Purchase request", action: "Payment", verification: "Three-way match" } }))),
    h("section", { "aria-labelledby": "sg-h-sec" }, h("h2", { id: "sg-h-sec" }, "Sector accents"), swatches())), document.getElementById("app-root"));
}
draw();
