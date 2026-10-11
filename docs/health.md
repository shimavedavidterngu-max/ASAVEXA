# Health Centre Administration

**Status: VERIFIED IN TEST ENVIRONMENT.** Tested with synthetic data only. Not reviewed by a privacy, health-sector, accounting or audit professional. Nothing here is a claim of legal or regulatory compliance, and it has not been run in production.

## What it is

A financial and administrative workspace for one or more health facilities. It is **not** a clinical record system. It holds **no patient names, identifiers, national ID numbers, diagnoses, prescriptions, test results or clinical notes**, and must not be used to store them. Claims carry a random internal reference, the payer's own claim reference (letters, numbers and `. _ / -` only, so a person's name is refused), the service month, the category and the amount.

## What it does

| Area | What you can do |
|---|---|
| Facilities | Create facilities and departments (administrator). Each person sees only the facilities they have been given; a facility that is not theirs is reported as not found. |
| Budgets | Draft, submit, approve (by a different person), reject, revise as a new version, move money between lines (second person approves). Budget versus actual shows spent, committed and available per line, and spending that has **no** budget line is listed separately and still counted in the total. |
| Procurement | Requisition, optional quotes, purchase order, goods receipt (partial allowed, no over-delivery), supplier invoice, three-way match, verification, payment approval by a third person, payment, credit notes, duplicate-invoice refusal, payables ageing, exceptions list. |
| Inventory | Item catalogue, batches and expiry, earliest-expiry-first issue, moving weighted-average cost, no negative stock, transfers between locations, counts, adjustments and write-offs approved by a second person, low-stock and expiry alerts, immutable movement history. |
| Revenue | Fee schedule, receipts (no patient details), refunds approved by a second person. |
| Claims | Payers, claims with a lifecycle (draft, submitted, rejected, resubmitted, partly paid, paid, written off), write-off approved by a second person, receivables ageing, reconciliation against a statement total typed in by a person. |
| Equipment | Register, warranty, service schedule, maintenance requests and completion with cost and downtime, retirement approved by a second person. |
| Staffing costs | Department totals per month only (no individual pay). |
| Dashboard and reports | Every figure shows how it is worked out and where it comes from; a figure that cannot be computed says "Not available", and one you may not see says "Restricted". Reports are frozen with a fingerprint when submitted, approved by a different person, and exported as a CSV marked confidential. |

## Who can do what

| Role | Access |
|---|---|
| Owner | Everything, all facilities |
| Administrator | Facilities, departments, access; prepare. **No** claims and **no** staffing costs |
| Accountant | Prepare, claims. No staffing costs |
| Finance officer | Prepare, claims, staffing costs |
| Approver | Approve, claims |
| Manager | Prepare, approve, claims |
| Reviewer, auditor, external auditor, read-only | View only; no claims, no staffing |
| Investor reviewer, donor, regulator | No access |

Approvals are always by someone other than the person who raised the item; the server enforces this, and the screens only hide buttons that would be refused.

## Honest limits

- It does **not** post to the accounting ledger. Budgets, orders, invoices, write-offs and disposals are recorded here; matching journals are posted by an authorised person. Ledger figures shown are read-only.
- "Spent" is verified supplier invoices (net of credits), approved staffing summaries and completed maintenance bought outside a purchase order. Other spending is not seen until recorded.
- No insurer or national-scheme connection. Reconciliation compares recorded payments with an amount a person types from the payer's statement.
- No depreciation. No payroll calculation.
- Stock accuracy depends on the receipts, issues and counts people record.
- Findings raised in the Controls workspace are not linked to procurement exceptions here.
- Concurrency was not tested with real simultaneous users. Backup and restore were not assessed.
- Before any patient-identifiable data is added, a documented lawful basis, a privacy impact assessment and a privacy review are required. None has been done.
- Approval records that a second person reviewed the item. It is not an audit opinion or certification.

## How it was tested

- Backend unit tests (`tests/test_health.py`) and a router harness (`tests/harness_health_routers.py`) covering isolation, budgets, procurement, inventory, claims, assets, staffing, dashboard and reports.
- Frontend tests (`frontend/tests/health.test.js`) for validators, the role matrix, who sees which button and page rendering.
- A real-browser run against the real router functions, covering the full flow with seven different users.
- A self-test step ("Health Centre") in Connection & Self-Test.
