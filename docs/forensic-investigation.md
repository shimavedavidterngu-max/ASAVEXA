# Forensic Accounting and Investigation workspace

Menu: **Forensic Investigation** (also in Professional Workspaces).

## Who can do what (deliberate)
| Permission | Held by | Lets you |
|---|---|---|
| `forensic:read` | Owner, Auditor, Manager, Approver | see confidential cases at all |
| `forensic:prepare` | Owner, Auditor | open cases, add evidence, run tests, draft findings and reports |
| `forensic:approve` | Owner, Manager, Approver | approve or send back findings and reports; close cases |

Accountants, finance officers, administrators, external auditors, read-only users, donors and regulators cannot see investigations. This protects the person being looked at and the people looking. The server also refuses a person approving anything they prepared or submitted, and refuses closing a case you opened.

## A case, step by step
1. **Open a case** with a title and the facts that prompted it (not conclusions). It gets a reference (CASE-0001).
2. **Evidence:** add files that already sit in the Evidence Vault. The case stores a reference and the file's SHA-256 fingerprint at that moment.
3. **Analytics:** choose a period or dates and any of nine read-only tests on posted journals (drafts excluded): Benford first-digit pattern, possible duplicates, round numbers, entries just below an approval limit, weekend-dated entries, created-and-posted by the same person, large entries with no evidence, frequent reversals, late posting. Each run is saved, fingerprinted, and cannot be changed.
4. **Findings:** write what was found and what supports it, cite journals (one click from a flagged row), and rely on evidence in the case. A different person approves or sends back (with a reason).
5. **Report:** freezes the approved findings, evidence fingerprints and custody state; a different person approves; approved reports download as CSV (labelled strictly confidential; spreadsheet formulas neutralised).
6. **Close:** a different person closes the case, once no finding is draft or waiting.

## Chain of custody
Every action (opening, evidence, runs, findings, reports, closing) is appended to the case's custody log. Each entry holds the fingerprint of the previous one, so changing or removing an entry breaks the chain. **Check custody log and evidence** re-verifies the chain and compares each evidence file's fingerprint with the one recorded.

## What the tests do and do not mean
A flag means "worth a look", never "wrong" or "guilty". Each test lists its ordinary explanations (rent repeats; small teams do both jobs; weekends differ by country). Benford needs at least 100 amounts. Thresholds (approval limit, evidence limit, weekend days, windows) are settings you choose.

## Limits
- Tested with synthetic data in the build environment. Not reviewed by a forensic accountant or lawyer.
- Evidence authenticity is not judged. No device forensics, e-discovery, interviews or workpaper templates yet.
- Single-currency assumption: amounts in different currencies are not converted.
- Take legal advice before any disciplinary, employment or criminal step.
