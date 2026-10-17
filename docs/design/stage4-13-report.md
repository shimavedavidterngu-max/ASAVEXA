# Design programme: Stages 4 to 13 (Ledger Paper + Proof Rail)

Status: **verified in the test environment, NOT deployed.** Stages 1-4 were pushed as commit `ac1e9a0`; CI and Render for that push are unconfirmed. Stages 5-13 exist as zips and have not been confirmed applied or pushed.

| Stage | What | Where |
|---|---|---|
| 5 | Proof behind statement lines in Reporting | Reporting |
| 6 | Procurement Trace | Procurement |
| 7 | "Follow the money" (authorised, purchased, delivered, unresolved) | Health |
| 8 | "Where the money went" per budget line | Public Finance (schools, government) |
| 9 | "Follow a grant" | Public Finance (NGOs) |
| 10 | "Follow a fund"; donor never shown | Faith-based organisations |
| 11 | Donor hidden on Grants list, grant page, new-fund form (browser only) | Public Finance |
| 12 | `hide_donor` setting enforced by the server: new names not stored, masked in API, reports and CSV | Backend + Overview |
| 13 | Permanent erase of stored donor names (typed ERASE, approvers) | Backend + Overview |

Rules held throughout: server decimal strings restated with no browser arithmetic; missing is "missing", unloaded is "Not checked", never zero; state by words and shape, not colour alone; delivery and payment are records, ASAVEXA pays nothing.

## Test evidence (test environment only)
- Frontend 1506/1506. Python suite and release check 10/10 run at Stage 12 (2335 OK, 8 skipped); re-run for Stage 13 pending when written.
- Browser journeys passed individually for health trace, pubfin spend, grant, fund, privacy.

## Not verified
Real devices, screen readers, other browsers, performance, the live site; evidence linking in browser journeys; switching between several expense lines in the spend view (unit-tested only).

## Known limits
Submitted report snapshots are fingerprinted and are masked, not rewritten. Audit-log text and backups are outside donor erasure. Grants are not linked to programme results (impact module) yet.
