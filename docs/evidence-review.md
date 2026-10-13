# Evidence Review and verified cases (Stage 2)

Status: **VERIFIED IN TEST ENVIRONMENT.** Not deployed, not run on Render/PostgreSQL through real FastAPI, not independently reviewed.

## What it does
Open **Evidence Review** (menu: Books and evidence). Pick a period and a report, then press *Review the evidence*. The page shows, for the figures in that report:
- what is asserted;
- supporting records (journal, evidence, and whether the link was **recorded** by a person or only **inferred** from a transaction reference);
- what is missing, unverified, conflicting, expired, of the wrong kind, verified by its own uploader, or reused for several journals;
- figures that do not tie to their journals;
- what is still uncertain, and the action needed;
- a verdict: Fully supported, Partly supported, Not supported, Does not tie, or Nothing to review.

A verified document is **not** treated as proof the figure is right. The page says so.

## Cases: from gap to verified outcome
1. **Raise a case** (`finding:manage`). Only possible when the review finds gaps. It records a **baseline** (gap count, verdict, fingerprint), runs the control `ER-REVIEW` (created for the organisation on first use; the standard control library is unchanged), which creates a normal Finding, and moves the finding to *remediation required*.
2. **Plan the action** (`finding:manage`): what, who owns it (must be a member of the organisation), optional due date.
3. **Record it as done** (`finding:remediate`).
4. **Verify the outcome** (`finding:verify`). The server **re-measures the same figure**. Only a result with no gaps is VERIFIED (finding then CLOSED). Otherwise the work is sent back with the result IMPROVED or NOT_IMPROVED and the failed attempt is kept. Residual risk and reopen criteria are required.
5. **Re-check** a verified case later. If gaps have returned, the case and finding reopen.

**Independence:** the verifier cannot be the person who recorded the work as done or the action's owner, whatever role they hold (enforced in the service, not only the screen).

## API (all under `/evidence-review`, organisation taken from the session, never from the client)
`GET /review`, `GET /cases`, `GET /cases/{id}` (reporting:read); `POST /cases`, `POST /cases/{id}/plan` (finding:manage); `POST /cases/{id}/complete` (finding:remediate); `POST /cases/{id}/verify`, `POST /cases/{id}/recheck` (finding:verify). Every write is audited (`EVIDENCE_REVIEW_*`, plus the existing finding/remediation/control events). Every lookup is scoped to the organisation; another organisation gets 404.

## Rules
Default rules (`evidencereview/rules.py`): ER-001 every posted journal has linked evidence; ER-002 revenue needs an invoice or contract; ER-003 expenses need an invoice, receipt, payroll evidence or contract. They are data, validated on input; per-organisation editing is not built yet.

## Known limits
- The review reads the Evidence Vault link on each journal; it does not read documents.
- Journals per review are capped (400); the page warns when truncated.
- Case records live in the shared document store (`security_docs`), so no new table or migration is needed.
- Member names are shown as short ids and roles because the members endpoint returns ids only.

## Tests
`tests/test_evidence_review.py` (20), `frontend/tests/evidence-review.test.js` (22), the two Stage 1 static route/audit tests (pass with no new exceptions), and a real-browser journey with three people plus a second company (outside the repo; see `docs/stage2-test-report.md`).
