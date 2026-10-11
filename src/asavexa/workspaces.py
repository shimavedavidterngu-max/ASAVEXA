"""The professional-workspace catalogue, with honest status words. A workspace is only shown as built when it is built and tested; the rest say NOT STARTED.
Status words follow the product's Definition of Done: NOT STARTED, IN PROGRESS, BLOCKED, IMPLEMENTED—TESTS PENDING, VERIFIED IN TEST ENVIRONMENT, VERIFIED IN STAGING, VERIFIED IN PRODUCTION, INDEPENDENTLY REVIEWED."""

STATUSES = ("NOT STARTED", "IN PROGRESS", "BLOCKED", "IMPLEMENTED—TESTS PENDING", "VERIFIED IN TEST ENVIRONMENT", "VERIFIED IN STAGING", "VERIFIED IN PRODUCTION", "INDEPENDENTLY REVIEWED")

WORKSPACES = [
    {"id": "analysis", "name": "Financial Analysis", "phase": 2, "status": "VERIFIED IN TEST ENVIRONMENT", "path": "/analysis", "permission": "reporting:read",
     "purpose": "Ratios, variance against the previous period and a comparison budget, cash-flow forecasts, break-even, and analysis reports that a second person must approve.",
     "depends_on": ["Accounting ledger", "Evidence Vault", "Audit trail"], "note": "Tested in the build environment with synthetic data. Not yet verified in staging or production."},
    {"id": "forensic", "name": "Forensic Accounting and Investigation", "phase": 3, "status": "NOT STARTED", "path": None, "permission": None,
     "purpose": "Cases, evidence preservation with chain of custody, transaction analysis, workpapers, findings and reports.", "depends_on": ["Shared workflow engine", "Evidence Vault"], "note": "Next slice."},
    {"id": "grc", "name": "Governance, Risk and Compliance", "phase": 4, "status": "NOT STARTED", "path": None, "permission": None,
     "purpose": "Risk register, control testing, compliance obligations, findings and remediation.", "depends_on": ["Shared workflow engine", "Existing controls and findings"], "note": ""},
    {"id": "tax", "name": "Tax Compliance", "phase": 5, "status": "BLOCKED", "path": None, "permission": None,
     "purpose": "Tax calendar, calculations, reconciliations and draft returns.", "depends_on": ["A chosen pilot jurisdiction", "Authoritative tax rules for that jurisdiction"],
     "note": "Blocked until you choose the first jurisdiction. ASAVEXA will not build tax rules from memory."},
    {"id": "public_finance", "name": "Financial Management and Public Finance", "phase": 6, "status": "NOT STARTED", "path": None, "permission": None,
     "purpose": "Budgets, commitments, procurement, grants and accountability reports.", "depends_on": ["Shared workflow engine"], "note": "Will replace the simple comparison budget used in Financial Analysis."},
    {"id": "health", "name": "Health Centre Administration", "phase": 7, "status": "NOT STARTED", "path": None, "permission": None,
     "purpose": "Facility finance, procurement, inventory and receivables, without patient records.", "depends_on": ["Public finance workspace"], "note": "Needs a data-protection decision before any patient-level data."},
    {"id": "cyber", "name": "Cybersecurity and Digital Risk", "phase": 8, "status": "NOT STARTED", "path": None, "permission": None,
     "purpose": "Assets, risks, controls, incidents and remediation (defensive only).", "depends_on": ["GRC workspace"], "note": ""},
    {"id": "bizdev", "name": "Business Development and Strategy", "phase": 9, "status": "NOT STARTED", "path": None, "permission": None,
     "purpose": "CRM, opportunities, proposals and commercial performance.", "depends_on": ["Financial Analysis workspace"], "note": ""},
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
