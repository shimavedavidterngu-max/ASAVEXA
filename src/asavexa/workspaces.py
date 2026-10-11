"""The professional-workspace catalogue, with honest status words. A workspace is only shown as built when it is built and tested; the rest say NOT STARTED.
Status words follow the product's Definition of Done: NOT STARTED, IN PROGRESS, BLOCKED, IMPLEMENTED—TESTS PENDING, VERIFIED IN TEST ENVIRONMENT, VERIFIED IN STAGING, VERIFIED IN PRODUCTION, INDEPENDENTLY REVIEWED."""

STATUSES = ("NOT STARTED", "IN PROGRESS", "BLOCKED", "IMPLEMENTED—TESTS PENDING", "VERIFIED IN TEST ENVIRONMENT", "VERIFIED IN STAGING", "VERIFIED IN PRODUCTION", "INDEPENDENTLY REVIEWED")

WORKSPACES = [
    {"id": "analysis", "name": "Financial Analysis", "phase": 2, "status": "VERIFIED IN TEST ENVIRONMENT", "path": "/analysis", "permission": "reporting:read",
     "purpose": "Ratios, variance against the previous period and a comparison budget, cash-flow forecasts, break-even, and analysis reports that a second person must approve.",
     "depends_on": ["Accounting ledger", "Evidence Vault", "Audit trail"], "note": "Tested in the build environment with synthetic data. Not yet verified in staging or production."},
    {"id": "forensic", "name": "Forensic Accounting and Investigation", "phase": 3, "status": "VERIFIED IN TEST ENVIRONMENT", "path": "/forensic", "permission": "forensic:read",
     "purpose": "Confidential cases, evidence with a tamper-evident chain of custody, nine read-only fraud-indicator tests on the ledger, findings and case reports that a second person must approve.",
     "depends_on": ["Accounting ledger (read only)", "Evidence Vault", "Audit trail", "Two-person approval"],
     "note": "Flags are indicators, never accusations. Viewing needs a special permission that ordinary operational roles do not hold. Tested with synthetic data; not reviewed by a forensic accountant or lawyer."},
    {"id": "grc", "name": "Governance, Risk and Compliance", "phase": 4, "status": "VERIFIED IN TEST ENVIRONMENT", "path": "/grc", "permission": "audit:read",
     "purpose": "A risk register on a transparent 5x5 matrix, treatment actions that a second person verifies, risk acceptance approved by a second person when above appetite, and a register of compliance obligations with due dates.",
     "depends_on": ["Existing Controls", "Evidence Vault", "Audit trail", "Two-person approval"],
     "note": "ASAVEXA ships no legal text: obligations are entered by people from their own sources. Scores are judgements, not calculations. Tested with synthetic data; not reviewed by a risk or compliance professional."},
    {"id": "tax", "name": "Tax Compliance", "phase": 5, "status": "VERIFIED IN TEST ENVIRONMENT", "path": "/tax", "permission": "reporting:read",
     "purpose": "A registry of 200 countries and territories, reviewed tax rules for each (with official source and effective dates), a calculator and a filing calendar.",
     "depends_on": ["Accounting ledger (read only)", "Audit trail", "Two-person rule review"],
     "note": "ASAVEXA ships with NO tax rates. A country has rules only after a person enters them from an official source and a second person approves them. Tested with invented rates in the build environment; not reviewed by a tax adviser."},
    {"id": "public_finance", "name": "Financial Management and Public Finance", "phase": 6, "status": "VERIFIED IN TEST ENVIRONMENT", "path": "/pubfin", "permission": "reporting:read",
     "purpose": "Approved budgets controlled against the posted ledger, commitments that cannot exceed what is available, virements, procurement with quotes and an approved award, grants with approved spending, and accountability reports.",
     "depends_on": ["Accounting ledger (read only)", "Evidence Vault", "Audit trail", "Two-person approval"],
     "note": "Procurement thresholds and quote counts are your own policy settings, not any government's law. Tested with synthetic data; not reviewed by a public-finance or procurement professional."},
    {"id": "health", "name": "Health Centre Administration", "phase": 7, "status": "VERIFIED IN TEST ENVIRONMENT", "path": "/health", "permission": "health:read",
     "purpose": "Facility budgets, procurement from requisition to payment with three-way matching, medical-supply stock with expiry, claims administration, receipts, equipment and maintenance, and staffing-cost summaries. Financial and administrative only.",
     "depends_on": ["Accounting ledger (read only)", "Evidence Vault", "Audit trail", "Two-person approval"],
     "note": "It holds no patient names, identifiers, diagnoses or clinical records, and must not be used to store them. It does not post to the ledger. Each person sees only the facilities they have been given; claims and staffing costs need their own permissions. Tested with synthetic data; not reviewed by a privacy, health-sector or audit professional, and no legal compliance is claimed."},    {"id": "cyber", "name": "Cybersecurity and Digital Risk", "phase": 8, "status": "VERIFIED IN TEST ENVIRONMENT", "path": "/cyber", "permission": "audit:read",
     "purpose": "An asset register, vulnerabilities with fix deadlines and second-person verification or risk acceptance, incidents with a controlled lifecycle, access reviews, and approved posture reports. Defensive record-keeping only.",
     "depends_on": ["Evidence Vault", "Audit trail", "Two-person approval"],
     "note": "It does not scan, test or connect to any system; it records what people find and do. Deadlines are your own policy settings. Whether an incident must be reported is a legal question it does not decide. Tested with synthetic data; not reviewed by a security professional."},
    {"id": "bizdev", "name": "Business Development and Strategy", "phase": 9, "status": "VERIFIED IN TEST ENVIRONMENT", "path": "/bizdev", "permission": "reporting:read",
     "purpose": "Accounts, a pipeline of opportunities, proposals whose large discounts a second person approves, wins a second person confirms, targets with a weighted forecast, and approved pipeline reports.",
     "depends_on": ["Evidence Vault", "Audit trail", "Two-person approval"],
     "note": "Stage probabilities and the discount limit are your own policy settings, so the forecast is an estimate under your policy, not a prediction. Amounts in different currencies are never combined. Tested with synthetic data; not reviewed by a sales or strategy professional."},
]

FOUNDATIONS = [
    {"name": "Organisations, tenants and roles", "status": "VERIFIED IN TEST ENVIRONMENT", "note": "Existing, reused. Two new permissions added: analysis:prepare and analysis:approve."},
    {"name": "Audit history", "status": "VERIFIED IN TEST ENVIRONMENT", "note": "Every analysis change and export is written to the organisation's audit trail."},
    {"name": "Evidence links", "status": "VERIFIED IN TEST ENVIRONMENT", "note": "Analysis reports can reference existing Evidence Vault items. No second evidence system."},
    {"name": "Approval with separation of duties", "status": "IMPLEMENTED—TESTS PENDING", "note": "Built for analysis reports only. A general, configurable workflow engine for all workspaces is the next shared slice."},
    {"name": "Shared reporting and export framework", "status": "IN PROGRESS", "note": "Analysis reports carry parameters, source, fingerprint, limitations and a confidentiality label; CSV export is audited. Other workspaces will reuse this."},
    {"name": "Controlled AI assistance", "status": "VERIFIED IN TEST ENVIRONMENT", "note": "Existing ASAVEXA AI is grounded and never posts or approves anything. Not yet connected to the new workspaces."},
]


def catalog() -> dict:
    return {"workspaces": WORKSPACES, "foundations": FOUNDATIONS, "statuses": list(STATUSES),
            "note": "A finished screen is not a finished feature. Statuses say what has actually been tested and where."}
