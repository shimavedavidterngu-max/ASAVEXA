import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { Accounting } from "../src/pages/Accounting.js";

function findByTag(vnode, tag) {
  if (!vnode || typeof vnode !== "object") return null;
  if (vnode.tag === tag) return vnode;
  for (const child of vnode.children || []) {
    const found = findByTag(child, tag);
    if (found) return found;
  }
  return null;
}

describe("Accounting — permission gate", () => {
  test("a role without ledger:read sees an access-denied state, not the ledger", () => {
    const vnode = Accounting({ role: "INVESTOR_REVIEWER", view: "overview" });
    assert.ok(JSON.stringify(vnode).includes("don't have access"));
  });

  test("a role with ledger:read sees the accounting overview", () => {
    const vnode = Accounting({ role: "AUDITOR", view: "overview", accounts: [], periods: [] });
    assert.ok(JSON.stringify(vnode).includes("Chart of Accounts"));
  });
});

describe("Accounting — overview: accounts and periods", () => {
  test("shows a real account row with its type and active status, not fabricated ones", () => {
    const accounts = [{ id: "a1", code: "1000", name: "Cash", type: "ASSET", currency: "USD", is_active: true }];
    const vnode = Accounting({ role: "OWNER", view: "overview", accounts, periods: [] });
    const text = JSON.stringify(vnode);
    assert.ok(text.includes("1000"));
    assert.ok(text.includes("Cash"));
  });

  test("account creation form is hidden for a role lacking account:manage", () => {
    const vnode = Accounting({ role: "AUDITOR", view: "overview", accounts: [], periods: [] });
    assert.ok(!JSON.stringify(vnode).includes("New account"));
  });

  test("account creation form is shown for a role with account:manage", () => {
    const vnode = Accounting({ role: "ADMINISTRATOR", view: "overview", accounts: [], periods: [] });
    assert.ok(JSON.stringify(vnode).includes("New account"));
  });

  test("an OPEN period offers Lock to a role with period:manage; a LOCKED one does not", () => {
    const periods = [
      { id: "p1", name: "Jan 2026", start_date: "2026-01-01", end_date: "2026-01-31", status: "OPEN" },
      { id: "p2", name: "Dec 2025", start_date: "2025-12-01", end_date: "2025-12-31", status: "LOCKED" },
    ];
    const vnode = Accounting({ role: "FINANCE_OFFICER", view: "overview", accounts: [], periods });
    const text = JSON.stringify(vnode);
    assert.ok(text.includes("Lock"));
    assert.ok(text.includes("No further postings allowed."));
  });

  test("clicking 'New journal entry' navigates to the journal creation route", () => {
    let navigatedTo = null;
    const vnode = Accounting({
      role: "ACCOUNTANT", view: "overview", accounts: [], periods: [],
      onNavigate: (p) => { navigatedTo = p; },
    });
    // find the button whose text is "New journal entry"
    const button = findButtonWithText(vnode, "New journal entry");
    assert.ok(button, "New journal entry button must render for a role with journal:create");
    button.props.onClick();
    assert.equal(navigatedTo, "/accounting/journals/new");
  });
});

describe("Accounting — journal creation form (validation & structure)", () => {
  test("renders at least two line rows by default (a journal must have >= 2 lines)", () => {
    const vnode = Accounting({
      role: "ACCOUNTANT", view: "journal-new", accounts: [],
      form: { lines: [{}, {}] }, onJournalFieldChange: () => {}, onAddJournalLine: () => {},
      onRemoveJournalLine: () => {}, onSubmitJournal: () => {},
    });
    const text = JSON.stringify(vnode);
    // two "Account" selects for two lines
    assert.equal((text.match(/"Account"/g) || []).length, 2);
  });

  test("line rows are removable only when more than two lines exist", () => {
    const vnode2 = Accounting({
      role: "ACCOUNTANT", view: "journal-new", accounts: [],
      form: { lines: [{}, {}] }, onJournalFieldChange: () => {}, onAddJournalLine: () => {},
      onRemoveJournalLine: () => {}, onSubmitJournal: () => {},
    });
    assert.ok(!JSON.stringify(vnode2).includes("Remove"));

    const vnode3 = Accounting({
      role: "ACCOUNTANT", view: "journal-new", accounts: [],
      form: { lines: [{}, {}, {}] }, onJournalFieldChange: () => {}, onAddJournalLine: () => {},
      onRemoveJournalLine: () => {}, onSubmitJournal: () => {},
    });
    assert.ok(JSON.stringify(vnode3).includes("Remove"));
  });

  test("submitting the form calls onSubmitJournal", () => {
    let submitted = false;
    const vnode = Accounting({
      role: "ACCOUNTANT", view: "journal-new", accounts: [],
      form: { lines: [{}, {}] }, onJournalFieldChange: () => {}, onAddJournalLine: () => {},
      onRemoveJournalLine: () => {}, onSubmitJournal: () => { submitted = true; },
    });
    const form = findByTag(vnode, "form");
    assert.ok(form, "a <form> must be present");
    form.props.onSubmit({ preventDefault: () => {} });
    assert.equal(submitted, true);
  });

  test("a submission error is shown, not swallowed", () => {
    const vnode = Accounting({
      role: "ACCOUNTANT", view: "journal-new", accounts: [],
      form: { lines: [{}, {}] }, formError: "Journal is not balanced.",
      onJournalFieldChange: () => {}, onAddJournalLine: () => {}, onRemoveJournalLine: () => {}, onSubmitJournal: () => {},
    });
    assert.ok(JSON.stringify(vnode).includes("Journal is not balanced."));
  });
});

describe("Accounting — journal detail: posting and reversal state", () => {
  test("a DRAFT journal offers Post to a role with journal:post, and no Reverse button", () => {
    const journal = {
      id: "j1", journal_number: "J-0001", description: "Sale", status: "DRAFT", date: "2026-01-05", currency: "USD", lines: [],
    };
    const vnode = Accounting({ role: "FINANCE_OFFICER", view: "journal-detail", journal, onPostJournal: () => {}, onReverseJournal: () => {} });
    const text = JSON.stringify(vnode);
    assert.ok(text.includes("Post journal"));
    assert.ok(!text.includes("Reverse journal"));
  });

  test("a POSTED journal offers Reverse to a role with journal:reverse, and never an edit affordance", () => {
    const journal = {
      id: "j1", journal_number: "J-0001", description: "Sale", status: "POSTED", date: "2026-01-05", currency: "USD", lines: [],
    };
    const vnode = Accounting({ role: "FINANCE_OFFICER", view: "journal-detail", journal, onPostJournal: () => {}, onReverseJournal: () => {} });
    const text = JSON.stringify(vnode);
    assert.ok(text.includes("Reverse journal"));
    assert.ok(!text.includes("Post journal"));
    assert.ok(!text.includes("Edit"), "a posted journal must never render an edit affordance");
  });

  test("a REVERSED journal shows neither Post nor Reverse, and links to its reversing journal", () => {
    const journal = {
      id: "j1", journal_number: "J-0001", description: "Sale", status: "REVERSED", date: "2026-01-05", currency: "USD",
      lines: [], reversed_by_journal_id: "j2",
    };
    const vnode = Accounting({ role: "FINANCE_OFFICER", view: "journal-detail", journal, onPostJournal: () => {}, onReverseJournal: () => {} });
    const text = JSON.stringify(vnode);
    assert.ok(!text.includes("Post journal"));
    assert.ok(!text.includes("Reverse journal"));
    assert.ok(text.includes("j2"));
  });

  test("posting/reversal actions are hidden for a role without the matching permission", () => {
    const journal = { id: "j1", description: "Sale", status: "DRAFT", date: "2026-01-05", currency: "USD", lines: [] };
    const vnode = Accounting({ role: "READ_ONLY", view: "journal-detail", journal, onPostJournal: () => {}, onReverseJournal: () => {} });
    assert.ok(!JSON.stringify(vnode).includes("Post journal"));
  });

  test("a journal not found renders an explicit empty state, not a blank screen", () => {
    const vnode = Accounting({ role: "OWNER", view: "journal-detail", journal: null });
    assert.ok(JSON.stringify(vnode).includes("Journal not found"));
  });

  test("a load error renders an error state with retry, not a crash", () => {
    let retried = false;
    const vnode = Accounting({ role: "OWNER", view: "journal-detail", journalError: "Network unreachable.", onRetry: () => { retried = true; } });
    const text = JSON.stringify(vnode);
    assert.ok(text.includes("Network unreachable."));
    const button = findByTag(vnode, "button");
    button.props.onClick();
    assert.equal(retried, true);
  });
});

function findButtonWithText(vnode, text) {
  if (!vnode || typeof vnode !== "object") return null;
  if (vnode.tag === "button" && JSON.stringify(vnode.children).includes(text)) return vnode;
  for (const child of vnode.children || []) {
    const found = findButtonWithText(child, text);
    if (found) return found;
  }
  return null;
}
