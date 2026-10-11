# Cybersecurity and Digital Risk workspace

Status: VERIFIED IN TEST ENVIRONMENT (synthetic data). Not reviewed by a security professional. Not verified in staging or production.

This workspace is defensive record-keeping. It does not scan, test, monitor or connect to any system, and it contains no attack tooling. It is only as complete as what people record in it.

## What it does
- **Assets**: systems, devices, applications, databases and so on, with an owner, criticality and data class. Retiring needs a reason.
- **Vulnerabilities**: recorded against an asset with a severity, optional CVE and where it was found. The fix deadline is set from your policy when the vulnerability is recorded and does not change later. Open items past the deadline are flagged overdue.
  - Flow: Open, Being fixed, Fixed, Verified. Marking it fixed needs a note and can link Evidence Vault items. A **different person** verifies the fix or sends it back.
  - Risk acceptance: a reason of 20+ characters and an end date within the policy maximum. A **different person** approves. After the end date it is flagged as expired.
- **Incidents**: Reported, Investigating, Contained, Resolved, Closed, with a timeline and days-to-contain and days-to-resolve. Closing needs a **different person** than the resolver, lessons learned (20+ characters) and, if personal data may be involved, the notification decision your organisation made. ASAVEXA records that decision; it does not decide whether anyone must be told.
- **Access reviews**: people type in who holds what access. Each entry is kept or removed (removal needs a reason). Removals must be confirmed before approval. A **different person** approves.
- **Reports**: a frozen posture snapshot with a SHA-256 fingerprint, approved by a different person. CSV export only once approved, labelled confidential, spreadsheet formulas neutralised.
- **Policy**: fix deadline in days per severity (a more severe level cannot have a longer deadline) and the longest risk acceptance.

## Permissions
Viewing needs audit:read. Prepare (record, start, mark fixed, ask to accept, report, review entries, submit): Owner, Administrator, Manager. Approve (verify, accept, close, approve reviews and reports, policy): Owner, Approver, Manager. Finance officer, Accountant, Auditor and Reviewer hold neither. Whoever did the work cannot be the person who verifies, accepts, closes or approves it, even if their role allows it.

## Honest limits
- It does not scan. A clean overview means nothing has been recorded, not that nothing is wrong.
- The default deadlines (critical 7, high 30, medium 90, low 180 days) and the 90-day acceptance maximum are placeholders, not a standard or a legal requirement.
- Verification means a second person confirmed the fix. It is not a penetration test.
- Whether an incident must be notified to a regulator or to people is a legal question for your organisation.
- Access review entries are typed in; nothing is read from other systems.
- Tested with invented data only: 27 service tests, 2 router checks, 19 frontend tests, and an 82-step real-browser run with five user roles.
