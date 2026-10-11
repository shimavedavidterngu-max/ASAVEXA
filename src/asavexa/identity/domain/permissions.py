"""
Permission constants and the Role -> permission matrix.

This is the single source of truth for "can this role do that action" —
callers (the API layer, primarily) ask `role_has_permission(role, PERM)`
rather than hard-coding role checks anywhere else.

The matrix below deliberately encodes segregation of duties (Blueprint
Rule 13 / Segregation-of-Duties Skill) rather than granting every
financial permission to every senior-sounding role:

- ACCOUNTANT can create journal drafts and upload evidence, but cannot
  post them or verify evidence — someone else must.
- APPROVER can post/reverse journals and verify evidence, but cannot
  create drafts — an approver approving their own work defeats the
  point of maker-checker.
- The same split applies to Reconciliation: ACCOUNTANT/FINANCE_OFFICER
  can import bank transactions, create a reconciliation, and match
  (auto or manual); only FINANCE_OFFICER, APPROVER or OWNER can approve
  one. A plain ACCOUNTANT can prepare a reconciliation end-to-end but
  never finalize it themselves.
- Period Close follows the identical pattern one level up: ACCOUNTANT
  can request a period close and read its status, but only
  FINANCE_OFFICER, APPROVER or OWNER can review or approve one — an
  accountant who requests their own period close can watch it sit in
  READY_FOR_CLOSE forever without ever being able to finalize it
  themselves.
- ADMINISTRATOR manages the organisation and its users, but is not
  itself a financial preparer or approver.
- INVESTOR_REVIEWER, DONOR and REGULATOR get no general permissions at
  all here — the blueprint's model for these roles is the (not yet
  built) Financial Passport's explicit, scoped sharing grants, not
  general ledger access. Do not add general permissions for these roles
  without re-reading Blueprint Section 3.3 (Financial Passport) first.

None of this is enforced by the Accounting Engine or Evidence Vault
services themselves — enforcement happens at the API boundary
(api/deps.py::require_permission), so the domain/service layers of
every module stay free of cross-module RBAC concerns, per Rule 19.
"""
from __future__ import annotations

from .enums import Role

# Organisation & user management
ORG_MANAGE_USERS = "org:manage_users"
ORG_MANAGE_SETTINGS = "org:manage_settings"

# Accounting Engine
ACCOUNT_MANAGE = "account:manage"
PERIOD_MANAGE = "period:manage"
JOURNAL_CREATE = "journal:create"
JOURNAL_POST = "journal:post"
JOURNAL_REVERSE = "journal:reverse"
LEDGER_READ = "ledger:read"

# Evidence Vault
EVIDENCE_UPLOAD = "evidence:upload"
EVIDENCE_VERIFY = "evidence:verify"
EVIDENCE_READ = "evidence:read"

# Reconciliation
RECONCILIATION_IMPORT = "reconciliation:import"
RECONCILIATION_CREATE = "reconciliation:create"
RECONCILIATION_MATCH = "reconciliation:match"
RECONCILIATION_APPROVE = "reconciliation:approve"
RECONCILIATION_READ = "reconciliation:read"

# Financial Reporting
# Only one permission: reports in this module are always freshly derived
# from the ledger — there is no separately-persisted artifact for
# "generate" to create and "read" to view later, so a generate/read
# split would gate two names to the exact same action. See
# reporting/README.md for the full reasoning.
REPORTING_READ = "reporting:read"

# Period Close & Financial Controls
PERIOD_CLOSE_REQUEST = "period_close:request"
PERIOD_CLOSE_REVIEW = "period_close:review"
PERIOD_CLOSE_APPROVE = "period_close:approve"
PERIOD_CLOSE_READ = "period_close:read"

# Controls & Compliance / Audit Workspace
CONTROL_READ = "control:read"
CONTROL_MANAGE = "control:manage"      # define/activate/deactivate control library entries
CONTROL_EXECUTE = "control:execute"    # run and review control executions
# Five deliberately independent permissions, one per distinct
# capability — never combined, never implied by one another:
#   finding:manage    — triage a finding (OPEN -> UNDER_REVIEW ->
#                        REMEDIATION_REQUIRED; send back; reopen a
#                        CLOSED finding). Governance/triage authority.
#   finding:remediate — do the fix (create/start/complete a Remediation).
#   finding:verify     — independently confirm a completed Remediation,
#                        closing the finding. The checker's role.
# Granting one never grants another: ACCOUNTANT has finding:remediate
# but not finding:manage or finding:verify; APPROVER has finding:verify
# but not finding:manage or finding:remediate — see ROLE_PERMISSIONS
# below and tests/test_compliance_permissions.py, which prove this with
# real roles rather than asserting it in a comment alone.
FINDING_MANAGE = "finding:manage"
FINDING_REMEDIATE = "finding:remediate"
FINDING_VERIFY = "finding:verify"

# Cross-cutting
AUDIT_READ = "audit:read"
PASSPORT_MANAGE = "passport:manage"
SECURITY_MANAGE = "security:manage"
VALIDATION_MANAGE = "validation:manage"
PILOT_MANAGE = "pilot:manage"
NETWORK_MANAGE = "network:manage"

# Professional workspaces. Viewing an analysis needs only REPORTING_READ.
ANALYSIS_PREPARE = "analysis:prepare"      # classify accounts, enter budgets and commentary, build scenarios, prepare and submit analysis reports
ANALYSIS_APPROVE = "analysis:approve"      # review and approve or reject a submitted analysis report (never your own)

TAX_PREPARE = "tax:prepare"                # select countries, draft and submit tax rules, run calculations, record filings
TAX_APPROVE = "tax:approve"                # review and approve or send back a tax rule (never your own)

FORENSIC_READ = "forensic:read"            # see confidential investigation cases (deliberately not held by operational roles)
FORENSIC_PREPARE = "forensic:prepare"      # open and work cases, add evidence, run analytics, draft findings and reports
FORENSIC_APPROVE = "forensic:approve"      # approve findings and reports, close cases (never your own work)

GRC_PREPARE = "grc:prepare"                # record risks, actions and obligations; request acceptance; mark obligations met. Viewing needs audit:read
GRC_APPROVE = "grc:approve"                # approve risk acceptance, verify completed actions, set risk appetite (never your own work)

PUBFIN_PREPARE = "pubfin:prepare"          # draft budgets, commitments, procurements, grants and reports; propose virements, awards and grant spending
PUBFIN_APPROVE = "pubfin:approve"          # approve budgets, virements, awards, grant spending and reports (never your own work); set procurement policy

BD_PREPARE = "bd:prepare"                  # record accounts, opportunities, activities and proposals; request wins; draft pipeline reports. Viewing needs reporting:read
BD_APPROVE = "bd:approve"                  # approve large discounts, confirm wins, set targets and policy, approve reports (never your own work)

CYBER_PREPARE = "cyber:prepare"            # record assets, vulnerabilities, incidents and access reviews; mark fixes done; draft reports. Viewing needs audit:read
CYBER_APPROVE = "cyber:approve"            # verify fixes, accept vulnerability risk, close incidents, approve access reviews and reports, set policy (never your own work)

HEALTH_READ = "health:read"                # see a facility's budgets, procurement, stock, assets and reports (only the facilities you have been given)
HEALTH_PREPARE = "health:prepare"          # raise requisitions and orders, receive goods, record invoices, stock moves, receipts, assets and maintenance
HEALTH_APPROVE = "health:approve"          # approve budgets, requisitions, orders, payments, adjustments, write-offs and reports (never your own work)
HEALTH_ADMIN = "health:admin"              # register facilities and departments, give people access to facilities. Sees every facility, but NOT claims or staffing costs
HEALTH_CLAIMS = "health:claims"            # see and work on claims, payers and payer reconciliation (confidential billing information)
HEALTH_STAFFING = "health:staffing"        # record and see department staffing-cost summaries

ALL_PERMISSIONS = frozenset(
    {
        ORG_MANAGE_USERS, ORG_MANAGE_SETTINGS, ACCOUNT_MANAGE, PERIOD_MANAGE,
        JOURNAL_CREATE, JOURNAL_POST, JOURNAL_REVERSE, LEDGER_READ,
        EVIDENCE_UPLOAD, EVIDENCE_VERIFY, EVIDENCE_READ,
        RECONCILIATION_IMPORT, RECONCILIATION_CREATE, RECONCILIATION_MATCH,
        RECONCILIATION_APPROVE, RECONCILIATION_READ, REPORTING_READ,
        PERIOD_CLOSE_REQUEST, PERIOD_CLOSE_REVIEW, PERIOD_CLOSE_APPROVE, PERIOD_CLOSE_READ,
        CONTROL_READ, CONTROL_MANAGE, CONTROL_EXECUTE,
        FINDING_MANAGE, FINDING_REMEDIATE, FINDING_VERIFY,
        AUDIT_READ, PASSPORT_MANAGE, SECURITY_MANAGE, VALIDATION_MANAGE, PILOT_MANAGE, NETWORK_MANAGE,
        ANALYSIS_PREPARE, ANALYSIS_APPROVE, TAX_PREPARE, TAX_APPROVE, FORENSIC_READ, FORENSIC_PREPARE, FORENSIC_APPROVE, GRC_PREPARE, GRC_APPROVE, PUBFIN_PREPARE, PUBFIN_APPROVE, BD_PREPARE, BD_APPROVE, CYBER_PREPARE, CYBER_APPROVE,
        HEALTH_READ, HEALTH_PREPARE, HEALTH_APPROVE, HEALTH_ADMIN, HEALTH_CLAIMS, HEALTH_STAFFING,
    }
)

ROLE_PERMISSIONS: dict[Role, frozenset[str]] = {
    Role.OWNER: ALL_PERMISSIONS,
    Role.ADMINISTRATOR: frozenset({
        ORG_MANAGE_USERS, ORG_MANAGE_SETTINGS, ACCOUNT_MANAGE, PERIOD_MANAGE,
        LEDGER_READ, EVIDENCE_READ, RECONCILIATION_READ, REPORTING_READ, PERIOD_CLOSE_READ,
        CONTROL_READ, CONTROL_MANAGE, FINDING_MANAGE,
        AUDIT_READ, PASSPORT_MANAGE, SECURITY_MANAGE, VALIDATION_MANAGE, PILOT_MANAGE, NETWORK_MANAGE, GRC_PREPARE, CYBER_PREPARE,
        HEALTH_READ, HEALTH_PREPARE, HEALTH_ADMIN,
    }),
    Role.ACCOUNTANT: frozenset({
        ACCOUNT_MANAGE, JOURNAL_CREATE, LEDGER_READ, EVIDENCE_UPLOAD, EVIDENCE_READ,
        RECONCILIATION_IMPORT, RECONCILIATION_CREATE, RECONCILIATION_MATCH, RECONCILIATION_READ,
        REPORTING_READ, PERIOD_CLOSE_REQUEST, PERIOD_CLOSE_READ,
        CONTROL_READ, CONTROL_EXECUTE, FINDING_REMEDIATE, ANALYSIS_PREPARE, TAX_PREPARE, PUBFIN_PREPARE, BD_PREPARE,
        HEALTH_READ, HEALTH_PREPARE, HEALTH_CLAIMS,
    }),
    Role.FINANCE_OFFICER: frozenset({
        JOURNAL_CREATE, JOURNAL_POST, JOURNAL_REVERSE, PERIOD_MANAGE,
        LEDGER_READ, EVIDENCE_VERIFY, EVIDENCE_READ, AUDIT_READ,
        RECONCILIATION_IMPORT, RECONCILIATION_CREATE, RECONCILIATION_MATCH,
        RECONCILIATION_APPROVE, RECONCILIATION_READ, REPORTING_READ,
        PERIOD_CLOSE_REQUEST, PERIOD_CLOSE_REVIEW, PERIOD_CLOSE_APPROVE, PERIOD_CLOSE_READ,
        CONTROL_READ, CONTROL_MANAGE, CONTROL_EXECUTE,
        FINDING_MANAGE, FINDING_REMEDIATE, FINDING_VERIFY, ANALYSIS_PREPARE, ANALYSIS_APPROVE, TAX_PREPARE, TAX_APPROVE, GRC_PREPARE, PUBFIN_PREPARE, PUBFIN_APPROVE, BD_PREPARE, BD_APPROVE,
        HEALTH_READ, HEALTH_PREPARE, HEALTH_CLAIMS, HEALTH_STAFFING,
    }),
    Role.APPROVER: frozenset({
        JOURNAL_POST, JOURNAL_REVERSE, LEDGER_READ, EVIDENCE_VERIFY,
        EVIDENCE_READ, AUDIT_READ, RECONCILIATION_APPROVE, RECONCILIATION_READ, REPORTING_READ,
        PERIOD_CLOSE_REVIEW, PERIOD_CLOSE_APPROVE, PERIOD_CLOSE_READ,
        CONTROL_READ, CONTROL_EXECUTE, FINDING_VERIFY, ANALYSIS_APPROVE, TAX_APPROVE, FORENSIC_READ, FORENSIC_APPROVE, GRC_APPROVE, PUBFIN_APPROVE, BD_APPROVE, CYBER_APPROVE,
        HEALTH_READ, HEALTH_APPROVE, HEALTH_CLAIMS,
    }),
    Role.REVIEWER: frozenset({
        LEDGER_READ, EVIDENCE_READ, RECONCILIATION_READ, REPORTING_READ, PERIOD_CLOSE_READ,
        CONTROL_READ, AUDIT_READ,
        HEALTH_READ,
    }),
    Role.MANAGER: frozenset({
        LEDGER_READ, EVIDENCE_READ, RECONCILIATION_READ, REPORTING_READ, PERIOD_CLOSE_READ,
        CONTROL_READ, AUDIT_READ, PASSPORT_MANAGE, FORENSIC_READ, FORENSIC_APPROVE, GRC_PREPARE, GRC_APPROVE, PUBFIN_APPROVE, BD_PREPARE, BD_APPROVE, CYBER_PREPARE, CYBER_APPROVE,
        HEALTH_READ, HEALTH_PREPARE, HEALTH_APPROVE, HEALTH_CLAIMS,
    }),
    Role.AUDITOR: frozenset({
        LEDGER_READ, EVIDENCE_READ, RECONCILIATION_READ, REPORTING_READ, PERIOD_CLOSE_READ,
        CONTROL_READ, AUDIT_READ, FORENSIC_READ, FORENSIC_PREPARE,
        HEALTH_READ,
    }),
    Role.EXTERNAL_AUDITOR: frozenset({
        LEDGER_READ, EVIDENCE_READ, RECONCILIATION_READ, REPORTING_READ, PERIOD_CLOSE_READ,
        CONTROL_READ, AUDIT_READ,
        HEALTH_READ,
    }),
    Role.READ_ONLY: frozenset({
        LEDGER_READ, EVIDENCE_READ, RECONCILIATION_READ, REPORTING_READ, PERIOD_CLOSE_READ,
        CONTROL_READ, AUDIT_READ,
        HEALTH_READ,
    }),
    # See the module docstring: these three are Passport-only by design.
    Role.INVESTOR_REVIEWER: frozenset(),
    Role.DONOR: frozenset(),
    Role.REGULATOR: frozenset(),
}


def role_has_permission(role: Role, permission: str) -> bool:
    if permission not in ALL_PERMISSIONS:
        raise ValueError(f"Unknown permission: {permission!r}")
    return permission in ROLE_PERMISSIONS.get(role, frozenset())
