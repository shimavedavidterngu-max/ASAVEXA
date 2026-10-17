# Stage 13: erase stored donor names

Stage 12 hides who gave but leaves older names in the database. Stage 13 adds the deliberate, permanent step.

- `POST /pubfin/privacy/erase-donors {"confirm": "ERASE"}`, approvers only (PUBFIN_APPROVE), audited as `PF_DONORS_ERASED` with a count, and a `DONOR_ERASED` entry in each grant's history.
- Allowed only while hiding is on, and only with the exact word `ERASE`.
- Replaces every stored grant donor in this organisation with "Not recorded". Other organisations are untouched. It cannot be undone: turning hiding off afterwards does not bring names back.
- **Not reached:** submitted report snapshots are fingerprinted (changing them would break tamper checks), so they keep their copy. They are masked in every view and export while hiding is on. After an erase they stay masked even if hiding is later turned off (the fingerprinted copy itself is not rewritten). Audit-log text and backups are also outside this stage.
- Overview "Who gave" card shows the erase control to approvers only while hiding is on, with this warning in words.

Tests: 3 Python (`DonorErase`), 3 frontend, and 4 extra checks in `e2e/journey_pubfin_privacy.py` (14 total).
