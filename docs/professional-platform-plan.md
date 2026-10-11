# ASAVEXA Professional Intelligence Expansion: plan and status

## Honest status (what is true today)
| Item | Status |
|---|---|
| Shared foundation: workspace selector, two new permissions, shared report/approval pattern | VERIFIED IN TEST ENVIRONMENT (approval is built for analysis reports only; a general workflow engine is the next shared slice) |
| Financial Analysis workspace | VERIFIED IN TEST ENVIRONMENT (synthetic data) |
| Forensic Accounting, GRC, Health Centre Administration, Cybersecurity, Business Development, Public Finance | NOT STARTED |
| Tax Compliance | BLOCKED until you choose the jurisdiction(s) and who supplies the current rules |
| Anything in staging or production | Not yet verified. Run Connection & Self-Test on the deployed site. |

Nothing here has been independently reviewed by an accountant, auditor, tax adviser or lawyer.

## Phase 0 findings (what already existed and was reused)
Accounting engine (journals, periods, posting), Evidence Vault, reporting, period close, identity and roles, audit log (hash-chained), standards, passport, ASAVEXA AI, proof graph, network. The new work **reads** the ledger; it never writes to it. No second accounting or evidence system was created. New records use the existing document store, so there are no database migrations.

## Shared foundations
- Roles and permissions: reused; added `analysis:prepare` and `analysis:approve`.
- Audit: every configuration change, budget, note, scenario, report step and export is written to the existing audit log.
- Evidence: reports hold references to existing Evidence Vault items (checked to belong to the same organisation).
- Approval: preparer submits, a different person approves or sends back. Enforced on the server, not only in the screen.
- Report framework: frozen snapshot, SHA-256 fingerprint, limitations, confidentiality label, audited CSV export (approved reports only).
- AI: existing ASAVEXA AI is grounded and cannot post or approve. Not yet connected to the new workspaces.

## Roadmap (one vertical slice at a time, each tested before the next)
1. Done: foundation + Financial Analysis.
2. Next shared slice: general approval/workflow engine, case management, policy library.
3. Forensic Accounting (reads the ledger and evidence; flags, never accuses).
4. GRC (risk register, controls, findings; reuses Controls & Compliance).
5. Tax: **needs your decision on jurisdiction first.** Tax rates and deadlines change; they will be configuration with an effective date and a named source, never hard-coded.
6. Public Finance (proper budgeting; replaces the manual comparison budget in Analysis).
7. Health Centre Administration (needs a decision on patient-data rules before any patient data is stored).
8. Cybersecurity, 9. Business Development.

## Questions only you can answer
1. Which country/countries should Tax support first, and who will keep the rules current?
2. Will Health Centre Administration store patient data, or only administrative and financial data?
3. Should Public Finance follow a specific public-finance standard (for example IPSAS or a national one)?

## Risks
- Ratios depend on how accounts are classified; unclassified accounts make a ratio "Needs setup" rather than guessing.
- Forecasts are assumptions, labelled FORECAST, and are never written to the ledger.
- Single-currency only; multi-currency organisations get a clear message instead of wrong ratios.

## Definition of done for a slice
Backend tests, frontend tests, a real-browser run against the real services, the Self-Test steps, permission and cross-organisation tests, documentation, and a status word that says only what was verified.
