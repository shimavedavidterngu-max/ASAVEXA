# Stage 6: Verified Standards Registry

Status: **VERIFIED IN TEST ENVIRONMENT** (service and router tests, 11 screen tests, a real-browser journey). Not deployed.

Page: **Standards Registry** (menu: Passport and network). It records, per organisation, the official source for each framework (title, https link, issuing authority, version, effective date, review-by date) and a person's approval.

- Lifecycle: DRAFT, UNDER_REVIEW, APPROVED, then SUPERSEDED (a newer approved version of the same framework and jurisdiction) or WITHDRAWN. A reviewer can send a source back with a reason. Submitted sources are never edited; a new version is a new source.
- Permissions: view `audit:read`; add and submit `grc:prepare`; approve, send back, withdraw `grc:approve`.
- Independence: the person who added or submitted a source cannot approve it (enforced in the service).
- A source whose review-by date has passed cannot be approved.
- Coverage per framework: VERIFIED (approved and not overdue), REVIEW_OVERDUE, NOT_YET_EFFECTIVE, UNVERIFIED. Nothing is verified until a person approves a source. The catalog's suggested defaults remain suggestions.
- Every step is audited (`STANDARDS_SOURCE_*`). Records live in the shared document store; no migration.

Limits: it stores links and approvals. It does not fetch the link, read the standard, or give legal advice. "Verified" is not "compliant".
