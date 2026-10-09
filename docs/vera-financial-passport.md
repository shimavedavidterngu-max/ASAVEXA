# VERA Financial Passport

A read-only snapshot of one organisation, built fresh from live records by `GET /passport`.
Nothing is estimated: where ASAVEXA holds no data, the Passport says so.

| Section | Source | Not available / limits |
|---|---|---|
| Identity | Organisation profile; owners and subsidiaries entered on the Passport page (`PUT /passport/structure`); accounting periods | Ownership and subsidiaries exist only if someone records them |
| Financial history | Posted journals, per period and in total: revenue, expenses, net income, margin, assets, liabilities, equity | **No classified cash-flow statement.** Cash flows shows movement on bank accounts that have been reconciled, and says so |
| Evidence quality | Evidence records linked to posted journals; bank transactions and reconciliations | "Supported" means evidence is VERIFIED |
| Governance | Audit trail (approvals), controls, executions, findings, segregation-of-duties checks | A violation means the same person is recorded as maker and checker |
| Reporting | Standards & Policies configuration, profile, periods | Shows "not configured" until the Standards page is saved |
| Audit trail | Shared audit events (latest 5,000), journal provenance, period locks | Older events are counted but not analysed; the Passport says when it truncates |

* **Access:** reading needs `passport:manage` (owner, administrator, manager); editing owners/subsidiaries needs `org:manage_settings`.
* **Fingerprint:** SHA-256 over the six sections. Generating a Passport is itself audited (`PASSPORT_GENERATED`) but those events are left out of the trail so the fingerprint does not change just because someone looked.
* **Isolation:** every read is scoped to the caller's organisation.
