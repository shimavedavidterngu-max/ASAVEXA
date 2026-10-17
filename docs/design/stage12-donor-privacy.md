# Stage 12: donor privacy, enforced by the server

Stages 10 and 11 hid who gave **in the browser only**. The server still stored and returned the donor, and the approved-report CSV included it. Stage 12 moves the rule to the server.

## What it does
- New per-organisation setting `hide_donor` (default off). An approver (PUBFIN_APPROVE) turns it on or off: `PUT /pubfin/privacy {"hide_donor": true|false}`, audited as `PF_PRIVACY_SET`. The setting is returned in `GET /pubfin/options` as `privacy`.
- While on:
  - A new grant stores `Not recorded` instead of the supplied name. The name is never written.
  - Grant list and grant page return `Not recorded` for every grant, including older ones.
  - Report snapshots shown through the API, and the CSV export, show `Not recorded`.
- Overview shows a "Who gave" card with the state, and a button for approvers only. "Follow a grant" no longer prints "awarded by Not recorded".

## What is and is not protected
- Names stored **before** the setting was turned on are **hidden, not erased**. They stay in the database, are masked in every view and export, and reappear if the setting is turned off. Erasing them is a separate, deliberate step and is not done here.
- Reports already submitted keep their stored snapshot (it is fingerprinted and is not rewritten); it is masked when shown or exported.
- Audit-log text and database backups are outside this stage.

## Tests
Python: 4 new tests in `tests/test_pubfin.py` (default, no new name stored, old names masked and restored, validation, audit, per-organisation, report view and CSV); router guard test extended. Frontend: 3 new tests in `granttrace.test.js`. Browser: `e2e/journey_pubfin_privacy.py` (10 checks, fresh server).
