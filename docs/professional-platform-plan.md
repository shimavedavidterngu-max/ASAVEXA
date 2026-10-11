# ASAVEXA Professional Intelligence Expansion: plan and status

## Honest status (what is true today)
| Item | Status |
|---|---|
| Shared foundation: workspace selector, two new permissions, shared report/approval pattern | VERIFIED IN TEST ENVIRONMENT (approval is built for analysis reports only; a general workflow engine is the next shared slice) |
| Financial Analysis workspace | VERIFIED IN TEST ENVIRONMENT (synthetic data) |
| Forensic Accounting and Investigation | VERIFIED IN TEST ENVIRONMENT (see forensic-investigation.md). Synthetic data only. |
| Governance, Risk and Compliance | VERIFIED IN TEST ENVIRONMENT (see grc.md). Synthetic data only; ships no legal text. |
| Public Finance | VERIFIED IN TEST ENVIRONMENT (see pubfin.md). Synthetic data only; policy defaults are placeholders, not law. |
| Business Development | VERIFIED IN TEST ENVIRONMENT (see bizdev.md). Synthetic data only; probabilities and discount limit are placeholders. |
| Cybersecurity and Digital Risk | VERIFIED IN TEST ENVIRONMENT (see cyber.md). Record-keeping only, never scans; synthetic data; deadlines are placeholders. |
| Health Centre Administration | VERIFIED IN TEST ENVIRONMENT (see health.md). Financial and administrative only; holds no patient data; never posts to the ledger; synthetic data. |
| Tax Compliance | VERIFIED IN TEST ENVIRONMENT as a framework for ~200 countries (see tax-compliance.md). It ships with NO tax rates: each country's rules must be entered from an official source and approved by a second person. Tested with invented rates only. |
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
3. Done: Forensic Accounting (reads the ledger and evidence; flags, never accuses).
4. Done: GRC (risk register, treatment actions, acceptance, obligations; links to existing Controls and Evidence Vault). Next for GRC: control-test scheduling, policy library, board reporting.
5. Done: Tax framework (rates are entered data with source, effective date and two-person approval; never hard-coded). Next for Tax: returns, withholding, e-filing guidance per country once real rules are loaded.
6. Done: Public Finance (approved budgets with ACTUAL taken from posted journals, commitments, virements, procurement with quote rules, grants, accountability reports). Next for Public Finance: multi-year budgets, appropriation hierarchy, a chosen standard (IPSAS or national).
7. Done: Health Centre Administration (facility-isolated budgets, procurement with three-way match, stock with expiry, receipts, claims totals, equipment, staffing totals, approved reports). Next for it: privacy review before any patient data, ledger posting, insurer connections.
8. Done: Cybersecurity (assets, vulnerabilities with second-person verification and risk acceptance, incidents with closure and notification decision, access reviews, approved posture reports). Next for it: import from scanners, ticket hand-off.
9. Done: Business Development (accounts, pipeline, proposals with discount approval, win confirmation, targets and forecast, approved reports). Next for it: multi-contact CRM, currency conversion with approved rates, invoicing hand-off to the ledger.

## Questions only you can answer
1. Which countries should have rules loaded first, and who will enter and review them (ideally a tax professional)?
2. Will Health Centre Administration store patient data, or only administrative and financial data?
3. Should Public Finance follow a specific public-finance standard (for example IPSAS or a national one)?

## Risks
- Ratios depend on how accounts are classified; unclassified accounts make a ratio "Needs setup" rather than guessing.
- Forecasts are assumptions, labelled FORECAST, and are never written to the ledger.
- Single-currency only; multi-currency organisations get a clear message instead of wrong ratios.

## Definition of done for a slice
Backend tests, frontend tests, a real-browser run against the real services, the Self-Test steps, permission and cross-organisation tests, documentation, and a status word that says only what was verified.
