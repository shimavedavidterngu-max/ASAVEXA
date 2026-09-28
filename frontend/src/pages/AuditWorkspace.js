import { h } from "../lib/vdom.js";
import { EvidenceChain } from "../components/EvidenceChain.js";
import { StatusBadge } from "../components/StatusBadge.js";

/**
 * AuditWorkspace — "one of ASAVEXA's most important interfaces"
 * (Section 11). Lets a user start from a journal and follow:
 *   Transaction -> Evidence -> Reconciliation -> Control -> Finding
 *   -> Remediation -> Verification -> Audit Event
 *
 * Pure render function, same testability discipline as Dashboard.js —
 * the container component (not built in this pass; see
 * docs/frontend-runtime-verification.md) is responsible for the real
 * sequence of API calls that assembles `chainData`:
 *   1. GET /journals/{id}                          -> transaction
 *   2. GET /evidence/status?journal_id={id}         -> evidence (or MISSING)
 *   3. GET /evidence/{evidence_id}                  -> evidence detail, if found
 *   4. GET /reconciliations/transactions/{id}        -> reconciliation, if the
 *      evidence/journal is linked to one (no single endpoint resolves
 *      journal -> bank transaction directly; the container looks it up
 *      via the reconciliation the user is already viewing, or leaves
 *      this stage "No linked record" — never guessed)
 *   5. GET /compliance/findings?...                  -> a finding
 *      referencing this control_id/execution_id, if any
 *   6. GET /compliance/remediations/{id}             -> remediation, if the
 *      finding has one
 *   7. remediation.verified_by/verified_at            -> verification
 *   8. GET /journals/{id}/audit-trail                 -> audit_event(s)
 *
 * This function never performs that lookup itself — it only renders
 * whatever the container already assembled, exactly reflecting
 * Section 11's "where a relationship does not exist, clearly state
 * 'No linked record'. Do not fabricate relationships."
 */
export function AuditWorkspace({ searchQuery, journal, chainLinks, onSearch, onNavigate, error }) {
  return h(
    "div",
    {},
    h("h1", {}, "Audit Workspace"),
    h("p", { style: "color: var(--ink-500); margin-top: -8px; margin-bottom: 24px;" },
      "Trace any transaction from its financial entry to its evidence, control, and audit history."),
    searchBar(searchQuery, onSearch),
    error ? h("div", { className: "alert alert-error", style: "margin-top:16px;" }, error) : null,
    journal ? journalSummaryCard(journal) : null,
    journal
      ? h(
          "div",
          { className: "card", style: "margin-top:16px;" },
          h("h3", {}, "Traceability chain"),
          EvidenceChain({ links: chainLinks || [], onNavigate })
        )
      : (!error ? emptyState() : null)
  );
}

function searchBar(searchQuery, onSearch) {
  return h(
    "div",
    { className: "card" },
    h("div", { className: "field", style: "margin-bottom: 0;" },
      h("label", { for: "audit-search" }, "Journal ID or reference"),
      h("div", { style: "display:flex; gap:8px;" },
        h("input", {
          id: "audit-search", type: "text", value: searchQuery || "",
          placeholder: "e.g. a journal id, or a transaction reference",
          onKeydown: (e) => {
            if (e.key === "Enter") onSearch(e.target.value);
          },
        }),
        h("button", { className: "btn btn-primary", onClick: () => onSearch(document.getElementById("audit-search").value) }, "Trace")
      )
    )
  );
}

function journalSummaryCard(journal) {
  return h(
    "div",
    { className: "card", style: "margin-top:16px;" },
    h("div", { style: "display:flex; justify-content:space-between; align-items:flex-start;" },
      h("div", {},
        h("h3", {}, journal.description || "Journal"),
        h("div", { className: "mono", style: "color: var(--ink-500); font-size:12.5px;" }, journal.id)
      ),
      StatusBadge({ status: journal.status })
    ),
    h("div", { style: "margin-top:8px; font-size:13px; color: var(--ink-500);" },
      `${journal.date || ""}  ·  ${journal.currency || ""}`)
  );
}

function emptyState() {
  return h(
    "div",
    { className: "empty-state card" },
    h("h3", {}, "Nothing traced yet"),
    h("p", {}, "Search for a journal above to see its complete evidence and control history.")
  );
}

/**
 * Pure helper: builds the ordered `links` array EvidenceChain expects
 * from the raw pieces a container would fetch. Kept separate from any
 * fetching so it's independently testable — proves the mapping from
 * raw API shapes to chain links is correct without needing a network.
 */
export function buildChainLinks({ journal, evidence, reconciliationTxn, finding, remediation, auditEvents }) {
  return [
    journal ? { stage: "transaction", label: journal.description || journal.id, status: journal.status } : null,
    evidence
      ? {
          stage: "evidence",
          label: evidence.original_filename || evidence.id,
          status: evidence.status,
          href: `/evidence/${evidence.id}`,
        }
      : null,
    reconciliationTxn
      ? {
          stage: "reconciliation",
          label: `Bank txn ${reconciliationTxn.id}`,
          status: reconciliationTxn.status,
          href: `/reconciliation/transactions/${reconciliationTxn.id}`,
        }
      : null,
    finding && finding.control_code
      ? { stage: "control", label: finding.control_code, href: `/compliance/controls/${finding.control_id}` }
      : null,
    finding
      ? { stage: "finding", label: finding.description, status: finding.status, href: `/compliance/findings/${finding.id}` }
      : null,
    remediation
      ? { stage: "remediation", label: remediation.action, status: remediation.status, href: `/compliance/remediations/${remediation.id}` }
      : null,
    remediation && remediation.verified_by
      ? { stage: "verification", label: `Verified by ${remediation.verified_by}`, meta: remediation.verified_at }
      : null,
    auditEvents && auditEvents.length
      ? {
          stage: "audit_event",
          label: `${auditEvents.length} audit event${auditEvents.length === 1 ? "" : "s"}`,
          meta: auditEvents[auditEvents.length - 1].action,
        }
      : null,
  ];
}
