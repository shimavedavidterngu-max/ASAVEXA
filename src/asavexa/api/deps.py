"""
FastAPI dependencies — now backed by the real Identity module.

This replaces the header-trusting stubs from the Accounting Engine's
first pass. As promised in that pass's README: wiring in real auth only
required rewriting this file — the accounting routers (accounts.py,
periods.py, journals.py) are unchanged and get real auth for free
because they already depended on get_current_actor/get_current_org.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..audit.repository import AuditRepository
from ..accounting.services.engine import AccountingEngine
from ..evidence.services.vault import EvidenceVault
from ..reconciliation.services.service import ReconciliationService
from ..reporting.services.service import ReportingService
from ..period_close.services.service import PeriodCloseService
from ..compliance.services.service import ComplianceService
from ..identity.domain.errors import (
    PermissionDeniedError,
    SessionExpiredError,
    SessionNotFoundError,
    SessionRevokedError,
)
from ..identity.domain.models import Session as IdentitySession
from ..identity.services.service import IdentityService
from ..security.context import SecurityContext
from ..security.errors import SessionPolicyError
from .security_wiring import build_security, make_blobs
from .db.audit_sqlalchemy_repository import SqlAlchemyAuditRepository
from .db.base import get_session
from .db.evidence_sqlalchemy_repository import SqlAlchemyEvidenceRepository
from .db.identity_sqlalchemy_repository import (
    SqlAlchemyMembershipRepository,
    SqlAlchemyOrganisationRepository,
    SqlAlchemySessionRepository,
    SqlAlchemyUserRepository,
)
from .db.compliance_sqlalchemy_repository import (
    SqlAlchemyControlDefinitionRepository,
    SqlAlchemyControlExecutionRepository,
    SqlAlchemyFindingRepository,
    SqlAlchemyRemediationRepository,
)
from .db.period_close_sqlalchemy_repository import SqlAlchemyPeriodCloseRepository
from .db.reconciliation_sqlalchemy_repository import (
    SqlAlchemyBankTransactionRepository,
    SqlAlchemyReconciliationRepository,
)
from .db.sqlalchemy_repository import (
    SqlAlchemyAccountRepository,
    SqlAlchemyJournalRepository,
    SqlAlchemyPeriodRepository,
)

_bearer_scheme = HTTPBearer(
    description="Session token returned by POST /auth/login. "
    "Use POST /auth/select-organisation before any org-scoped call."
)


def get_audit_repository(session=Depends(get_session)) -> AuditRepository:
    """
    Generic, cross-module read access to the shared audit trail (see
    api/routers/audit.py's GET /audit/entity/{entity_type}/{entity_id}).
    Every other get_*_service factory below already builds its own
    SqlAlchemyAuditRepository(session) internally for WRITES scoped to
    that module; this is the same repository, exposed directly for the
    one generic READ endpoint that isn't scoped to any single module.
    """
    return SqlAlchemyAuditRepository(session)


def get_identity_service(session=Depends(get_session)) -> IdentityService:
    return IdentityService(
        organisations=SqlAlchemyOrganisationRepository(session),
        users=SqlAlchemyUserRepository(session),
        memberships=SqlAlchemyMembershipRepository(session),
        sessions=SqlAlchemySessionRepository(session),
        audit=SqlAlchemyAuditRepository(session),
    )


def get_security(session=Depends(get_session), identity: IdentityService = Depends(get_identity_service)) -> SecurityContext:
    return build_security(session, identity)


def get_validation(security: SecurityContext = Depends(get_security), session=Depends(get_session)):
    """Professional validation service over the shared document store; every action is written to the audit trail."""
    from ..validation.service import ValidationService
    from ..validation.wiring import make_log
    from .db.audit_chain_hook import platform_keys
    from .db.security_store import SqlAlchemyDocStore

    return ValidationService(SqlAlchemyDocStore(session), log=make_log(security), keys=platform_keys())


def get_pilot(security: SecurityContext = Depends(get_security), session=Depends(get_session)):
    """Pilot service over the shared document store; every action is written to the audit trail of the organisation concerned."""
    from ..pilot.service import PilotService
    from ..pilot.wiring import make_log
    from .db.security_store import SqlAlchemyDocStore

    return PilotService(SqlAlchemyDocStore(session), log=make_log(security))


def get_analysis(security: SecurityContext = Depends(get_security), session=Depends(get_session)):
    """Financial Analysis service: reads the real accounting ledger (never writes to it) and keeps its own records in the shared document store; every action is audited."""
    from ..analysis.service import AnalysisService
    from ..analysis.wiring import make_log
    from .db.security_store import SqlAlchemyDocStore

    return AnalysisService(SqlAlchemyDocStore(session), get_accounting_engine(session), log=make_log(security))


def get_tax(security: SecurityContext = Depends(get_security), session=Depends(get_session)):
    """Tax Compliance service: reviewed tax rules, calculator and filing calendar in the shared document store; reads the ledger only for starting amounts; every action is audited."""
    from ..tax.service import TaxService
    from ..tax.wiring import make_log
    from .db.security_store import SqlAlchemyDocStore

    return TaxService(SqlAlchemyDocStore(session), get_accounting_engine(session), log=make_log(security))


def get_grc(security: SecurityContext = Depends(get_security), session=Depends(get_session)):
    """GRC service: risks, actions and obligations in the shared document store; links to existing Controls and the Evidence Vault; never changes the ledger; every action is audited."""
    from ..grc.service import GrcService
    from ..grc.wiring import make_log
    from .db.security_store import SqlAlchemyDocStore

    compliance = get_compliance_service(session)
    return GrcService(SqlAlchemyDocStore(session), lambda org: compliance.list_controls(org), get_evidence_vault(session), log=make_log(security))


def get_agent_registry(security: SecurityContext = Depends(get_security), session=Depends(get_session)):
    """Agent registry and policy decisions in the shared document store. It only decides whether an action may go ahead; it never runs one. Every step is audited."""
    from ..agents.service import AgentRegistry
    from .db.security_store import SqlAlchemyDocStore

    memberships = SqlAlchemyMembershipRepository(session)

    def log(action, actor, entity_id, org, reason=""):
        security.log(action, actor, entity_id, org_id=org, entity_type="Agent", reason=reason)
    return AgentRegistry(SqlAlchemyDocStore(session), is_member=lambda org, user: memberships.get(org, user) is not None, log=log)


def get_standards_registry(security: SecurityContext = Depends(get_security), session=Depends(get_session)):
    """Verified Standards Registry: official sources, versions, effective and review dates, and a person's approval, in the shared document store; every action is audited."""
    from ..standards.registry import StandardsRegistry
    from .db.security_store import SqlAlchemyDocStore

    def log(action, actor, entity_id, org, reason=""):
        security.log(action, actor, entity_id, org_id=org, entity_type="StandardsRegistry", reason=reason)
    return StandardsRegistry(SqlAlchemyDocStore(session), log=log)


def get_evidence_review(security: SecurityContext = Depends(get_security), session=Depends(get_session)):
    """Evidence Review cases: reads the ledger and Evidence Vault, drives the existing Compliance findings and remediations, keeps its own measurements in the shared document store; never changes the ledger; every step is audited."""
    from ..evidencereview.service import EvidenceReviewService
    from ..evidencereview.wiring import make_log
    from .db.security_store import SqlAlchemyDocStore

    memberships = SqlAlchemyMembershipRepository(session)
    return EvidenceReviewService(
        SqlAlchemyDocStore(session), get_reporting_service(session), get_evidence_vault(session), get_compliance_service(session),
        is_member=lambda org, user: memberships.get(org, user) is not None, log=make_log(security), links=_build_proof_links(security, session))


def _build_proof_links(security, session):
    """The stored Proof-to-Action graph for this request: links between records, in the shared document store, audited. It reads record names and never changes them."""
    from ..proofgraph.links import ProofLinks
    from ..proofgraph.wiring import make_log, make_sources
    from .db.security_store import SqlAlchemyDocStore

    store = SqlAlchemyDocStore(session)
    return ProofLinks(store, make_sources(store, get_evidence_vault(session), get_compliance_service(session)), log=make_log(security))


def get_proof_links(security: SecurityContext = Depends(get_security), session=Depends(get_session)):
    return _build_proof_links(security, session)


def get_entity_config(security: SecurityContext = Depends(get_security), session=Depends(get_session)):
    """Organisation type, subtype and which workspaces the menu shows. Shared document store; audited; grants no permission."""
    from ..workspaces import WORKSPACES
    from ..entities.service import EntityConfigService
    from ..entities.wiring import make_log
    from .db.security_store import SqlAlchemyDocStore

    return EntityConfigService(SqlAlchemyDocStore(session), lambda: [w["id"] for w in WORKSPACES], log=make_log(security))


def get_assurance(vault=Depends(get_evidence_vault), compliance=Depends(get_compliance_service), review=Depends(get_evidence_review),
                  registry=Depends(get_standards_registry), agents=Depends(get_agent_registry), analysis=Depends(get_analysis)):
    """The shared status vocabulary and a read-only count across modules. It owns no data and never writes: each module supplies its own records."""
    from ..assurance.service import AssuranceService

    return AssuranceService({
        "evidence": lambda org: [(r.id, r.status.value, {"uploaded_by": r.uploaded_by, "verified_by": r.verified_by}) for r in vault.list_for_org(org)],
        "finding": lambda org: [(f.id, f.status.value, {}) for f in compliance.list_findings(org)],
        "evidence_review_case": lambda org: [(c["id"], c["status"], {}) for c in review.list_cases(org)],
        "standards_source": lambda org: [(x["id"], x["status"], {}) for x in registry.list_sources(org)],
        "agent_decision": lambda org: [(d["id"], d["state"], {}) for d in agents.list_decisions(org)],
        "analysis_report": lambda org: [(r["id"], r["status"], {}) for r in analysis.list_reports(org)],
    })


def get_health(security: SecurityContext = Depends(get_security), session=Depends(get_session), identity: IdentityService = Depends(get_identity_service)):
    """Health Centre Administration service: facilities, budgets, procurement, stock, claims administration, assets and staffing costs in the shared document store; reads the ledger and Evidence Vault, never changes them; every action is audited. Holds no patient information."""
    from ..health.service import HealthService
    from ..health.wiring import make_log
    from .db.security_store import SqlAlchemyDocStore

    def can(org, actor, perm):
        try:
            identity.require_permission(actor, org, perm)
            return True
        except PermissionDeniedError:
            return False

    return HealthService(SqlAlchemyDocStore(session), get_evidence_vault(session), get_accounting_engine(session), log=make_log(security), can=can)


def get_cyber(security: SecurityContext = Depends(get_security), session=Depends(get_session)):
    """Cybersecurity service: assets, vulnerabilities, incidents, access reviews and reports in the shared document store; reads the Evidence Vault, never changes it; every action is audited. It does not scan or connect to any system."""
    from ..cyber.service import CyberService
    from ..cyber.wiring import make_log
    from .db.security_store import SqlAlchemyDocStore

    return CyberService(SqlAlchemyDocStore(session), get_evidence_vault(session), log=make_log(security))


def get_treasury(security: SecurityContext = Depends(get_security), session=Depends(get_session)):
    """Treasury service: cash accounts, balances, expected cash flows, payment requests and covenants in the shared document store; reads the Evidence Vault, never changes it; every action is audited. It never moves money."""
    from ..treasury.service import TreasuryService
    from ..treasury.wiring import make_log
    from .db.security_store import SqlAlchemyDocStore

    return TreasuryService(SqlAlchemyDocStore(session), get_evidence_vault(session), log=make_log(security))


def get_procurement(security: SecurityContext = Depends(get_security), session=Depends(get_session)):
    """Procurement service: suppliers, contracts, purchase orders, deliveries, invoices and reviews in the shared document store; every action is audited. It reads Treasury payments to confirm an invoice was paid, and never changes them."""
    from ..procurement.service import ProcurementService
    from ..procurement.wiring import make_log
    from .db.security_store import SqlAlchemyDocStore

    return ProcurementService(SqlAlchemyDocStore(session), log=make_log(security))


def get_fpa(security: SecurityContext = Depends(get_security), session=Depends(get_session)):
    """Planning and KPIs service: KPI definitions, owners, readings and forecast accuracy in the shared document store; reads the Evidence Vault, never changes it; every action is audited."""
    from ..fpa.service import FpaService
    from ..fpa.wiring import make_log
    from ..identity.domain.permissions import FPA_PREPARE, ROLE_PERMISSIONS
    from .db.security_store import SqlAlchemyDocStore

    memberships = SqlAlchemyMembershipRepository(session)

    def member(org, user):
        m = memberships.get(org, user)
        return m is not None and m.status.value == "ACTIVE"

    def can_record(org, user):
        m = memberships.get(org, user)
        return m is not None and FPA_PREPARE in ROLE_PERMISSIONS.get(m.role, ())

    return FpaService(SqlAlchemyDocStore(session), get_evidence_vault(session), is_member=member, can_record=can_record, log=make_log(security))


def get_fincrime(security: SecurityContext = Depends(get_security), session=Depends(get_session)):
    """Financial-crime casework service: alerts, cases, conflict declarations, screening records, decisions, loss and recovery in the shared document store; reads the Evidence Vault, never changes it; every action is audited."""
    from ..fincrime.service import FincrimeService
    from ..fincrime.wiring import make_log
    from ..identity.domain.permissions import FINCRIME_PREPARE, ROLE_PERMISSIONS
    from .db.security_store import SqlAlchemyDocStore

    memberships = SqlAlchemyMembershipRepository(session)

    def member(org, user):
        m = memberships.get(org, user)
        return m is not None and m.status.value == "ACTIVE"

    def can_work(org, user):
        m = memberships.get(org, user)
        return m is not None and FINCRIME_PREPARE in ROLE_PERMISSIONS.get(m.role, ())

    return FincrimeService(SqlAlchemyDocStore(session), get_evidence_vault(session), is_member=member, can_work=can_work, log=make_log(security))


def get_itaudit(security: SecurityContext = Depends(get_security), session=Depends(get_session)):
    """IT audit service: change records, application controls and tests in the shared document store; reads the Evidence Vault and Cybersecurity assets, never changes them; every action is audited."""
    from ..itaudit.service import ItAuditService
    from ..itaudit.wiring import make_log
    from .db.security_store import SqlAlchemyDocStore

    return ItAuditService(SqlAlchemyDocStore(session), get_evidence_vault(session), log=make_log(security))


def get_resilience(security: SecurityContext = Depends(get_security), session=Depends(get_session)):
    """Risk indicators and resilience service: indicators, loss events, business processes and continuity tests in the shared document store; reads the Evidence Vault and risk register, never changes them; every action is audited."""
    from ..resilience.service import ResilienceService
    from ..resilience.wiring import make_log
    from .db.security_store import SqlAlchemyDocStore

    return ResilienceService(SqlAlchemyDocStore(session), get_evidence_vault(session), log=make_log(security))


def get_aigov(security: SecurityContext = Depends(get_security), session=Depends(get_session)):
    """AI governance service: AI systems, model changes and incidents in the shared document store; reads the Evidence Vault, never changes it; every action is audited."""
    from ..aigov.service import AigovService
    from ..aigov.wiring import make_log
    from .db.security_store import SqlAlchemyDocStore

    return AigovService(SqlAlchemyDocStore(session), get_evidence_vault(session), log=make_log(security))


def get_quality(security: SecurityContext = Depends(get_security), session=Depends(get_session)):
    """Quality management service: nonconformances and corrective actions in the shared document store; reads the Evidence Vault, never changes it; every action is audited."""
    from ..quality.service import QualityService
    from ..quality.wiring import make_log
    from .db.security_store import SqlAlchemyDocStore

    return QualityService(SqlAlchemyDocStore(session), get_evidence_vault(session), log=make_log(security))


def get_secretarial(security: SecurityContext = Depends(get_security), session=Depends(get_session)):
    """Company secretarial service: meetings, resolutions and filings in the shared document store; reads the Evidence Vault, never changes it; every action is audited."""
    from ..secretarial.service import SecretarialService
    from ..secretarial.wiring import make_log
    from .db.security_store import SqlAlchemyDocStore

    return SecretarialService(SqlAlchemyDocStore(session), get_evidence_vault(session), log=make_log(security))


def get_fixedassets(security: SecurityContext = Depends(get_security), session=Depends(get_session)):
    """Fixed assets service: assets, disposals and counts in the shared document store; reads the Evidence Vault, never changes it; posts nothing to a ledger; every action is audited."""
    from ..fixedassets.service import FixedAssetService
    from ..fixedassets.wiring import make_log
    from .db.security_store import SqlAlchemyDocStore

    return FixedAssetService(SqlAlchemyDocStore(session), get_evidence_vault(session), log=make_log(security))


def get_inventory(security: SecurityContext = Depends(get_security), session=Depends(get_session)):
    """Inventory service: stock items and movements in the shared document store; posts nothing to a ledger; every action is audited."""
    from ..inventory.service import InventoryService
    from ..inventory.wiring import make_log
    from .db.security_store import SqlAlchemyDocStore

    return InventoryService(SqlAlchemyDocStore(session), get_evidence_vault(session), log=make_log(security))


def get_investments(security: SecurityContext = Depends(get_security), session=Depends(get_session)):
    """Investments service: holdings, trades and typed prices in the shared document store; reads no market data and posts nothing to a ledger; every action is audited."""
    from ..investments.service import InvestmentsService
    from ..investments.wiring import make_log
    from .db.security_store import SqlAlchemyDocStore

    return InvestmentsService(SqlAlchemyDocStore(session), get_evidence_vault(session), log=make_log(security))


def get_valuation(security: SecurityContext = Depends(get_security), session=Depends(get_session)):
    """Valuation service: workpapers and typed inputs in the shared document store; reads no market data and gives no opinion of value; every action is audited."""
    from ..valuation.service import ValuationService
    from ..valuation.wiring import make_log
    from .db.security_store import SqlAlchemyDocStore

    return ValuationService(SqlAlchemyDocStore(session), get_evidence_vault(session), log=make_log(security))


def get_insurance(security: SecurityContext = Depends(get_security), session=Depends(get_session)):
    """Insurance service: policies, claims and receipts in the shared document store; contacts no insurer and gives no insurance advice; every action is audited."""
    from ..insurance.service import InsuranceService
    from ..insurance.wiring import make_log
    from .db.security_store import SqlAlchemyDocStore

    return InsuranceService(SqlAlchemyDocStore(session), get_evidence_vault(session), log=make_log(security))


def get_esg(security: SecurityContext = Depends(get_security), session=Depends(get_session)):
    """ESG service: emission records and targets in the shared document store; supplies no emission factors and measures nothing; every action is audited."""
    from ..esg.service import EsgService
    from ..esg.wiring import make_log
    from .db.security_store import SqlAlchemyDocStore

    return EsgService(SqlAlchemyDocStore(session), get_evidence_vault(session), log=make_log(security))


def get_projects(security: SecurityContext = Depends(get_security), session=Depends(get_session)):
    """Projects and grants service: projects, budget lines, spending and receipts in the shared document store; moves no money; every action is audited."""
    from ..projects.service import ProjectsService
    from ..projects.wiring import make_log
    from .db.security_store import SqlAlchemyDocStore

    return ProjectsService(SqlAlchemyDocStore(session), get_evidence_vault(session), log=make_log(security))


def get_payroll(security: SecurityContext = Depends(get_security), session=Depends(get_session)):
    """Payroll service: payroll runs and typed pay lines in the shared document store; calculates no tax or statutory amount and pays nobody; every action is audited."""
    from ..payroll.service import PayrollService
    from ..payroll.wiring import make_log
    from .db.security_store import SqlAlchemyDocStore

    return PayrollService(SqlAlchemyDocStore(session), get_evidence_vault(session), log=make_log(security))


def get_bizdev(security: SecurityContext = Depends(get_security), session=Depends(get_session)):
    """Business Development service: accounts, opportunities, proposals, targets and reports in the shared document store; reads the Evidence Vault, never changes it; every action is audited."""
    from ..bizdev.service import BizDevService
    from ..bizdev.wiring import make_log
    from .db.security_store import SqlAlchemyDocStore

    return BizDevService(SqlAlchemyDocStore(session), get_evidence_vault(session), log=make_log(security))


def get_pubfin(security: SecurityContext = Depends(get_security), session=Depends(get_session)):
    """Public Finance service: budgets, commitments, procurement, grants and reports in the shared document store; reads the ledger and Evidence Vault, never changes them; every action is audited."""
    from ..pubfin.service import PubFinService
    from ..pubfin.wiring import make_log
    from .db.security_store import SqlAlchemyDocStore

    return PubFinService(SqlAlchemyDocStore(session), get_accounting_engine(session), get_evidence_vault(session), log=make_log(security))


def get_forensic(security: SecurityContext = Depends(get_security), session=Depends(get_session)):
    """Forensic service: confidential cases in the shared document store; reads the ledger and Evidence Vault, never changes them; every action is audited."""
    from ..forensic.service import ForensicService
    from ..forensic.wiring import make_log
    from .db.security_store import SqlAlchemyDocStore

    return ForensicService(SqlAlchemyDocStore(session), get_accounting_engine(session), get_evidence_vault(session), log=make_log(security))


def get_network(security: SecurityContext = Depends(get_security), session=Depends(get_session)):
    """Network service over the shared document store; every action is written to the audit trail of the organisation concerned."""
    from ..network.service import NetworkService
    from ..network.wiring import make_log
    from .db.security_store import SqlAlchemyDocStore

    return NetworkService(SqlAlchemyDocStore(session), log=make_log(security))


def get_accounting_engine(session=Depends(get_session)) -> AccountingEngine:
    return AccountingEngine(
        accounts=SqlAlchemyAccountRepository(session),
        periods=SqlAlchemyPeriodRepository(session),
        journals=SqlAlchemyJournalRepository(session),
        audit=SqlAlchemyAuditRepository(session),
    )


def get_evidence_vault(session=Depends(get_session)) -> EvidenceVault:
    return EvidenceVault(
        evidence=SqlAlchemyEvidenceRepository(session),
        audit=SqlAlchemyAuditRepository(session),
        blobs=make_blobs(session),
    )


def get_reconciliation_service(session=Depends(get_session)) -> ReconciliationService:
    """
    Constructed with a *real* AccountingEngine (read-only usage) — see
    reconciliation/services/service.py's own docstring on why it needs
    one and never touches EvidenceVault or IdentityService directly.
    """
    return ReconciliationService(
        reconciliations=SqlAlchemyReconciliationRepository(session),
        transactions=SqlAlchemyBankTransactionRepository(session),
        audit=SqlAlchemyAuditRepository(session),
        accounting=get_accounting_engine(session),
    )


def get_reporting_service(session=Depends(get_session)) -> ReportingService:
    """
    Constructed with a real AccountingEngine (read-only) and, since
    Reporting's Reconciliation and Evidence integrations are both
    optional (see reporting/services/service.py), a real
    ReconciliationService and EvidenceVault too — there is no reason to
    withhold either here; get_reconciliation_summary/
    get_evidence_completeness simply raise their own
    *NotConfiguredError if a caller ever constructs ReportingService
    without one, which this factory never does.
    """
    return ReportingService(
        accounting=get_accounting_engine(session),
        audit=SqlAlchemyAuditRepository(session),
        reconciliation=get_reconciliation_service(session),
        evidence=get_evidence_vault(session),
    )


def get_period_close_service(session=Depends(get_session)) -> PeriodCloseService:
    """
    Constructed with real Accounting, Reporting, Reconciliation, and
    Evidence collaborators — Period Close's Reconciliation/Evidence
    integrations are optional at the class level (see
    period_close/services/service.py) but there is no reason to
    withhold them from the production API wiring.
    """
    return PeriodCloseService(
        accounting=get_accounting_engine(session),
        reporting=get_reporting_service(session),
        close_processes=SqlAlchemyPeriodCloseRepository(session),
        audit=SqlAlchemyAuditRepository(session),
        reconciliation=get_reconciliation_service(session),
        evidence=get_evidence_vault(session),
    )


def get_compliance_service(session=Depends(get_session)) -> ComplianceService:
    """
    Constructed with every collaborator available — Reconciliation,
    Evidence, and Period Close are all optional at the ComplianceService
    class level (each built-in check degrades to NOT_APPLICABLE without
    them), but there is no reason to withhold any from production API
    wiring. Never checks permissions itself — see
    compliance/services/service.py's own docstring; the routers below
    are where finding:manage / finding:remediate / finding:verify /
    control:execute / control:manage / control:read are actually
    enforced, via the same require_permission(...) every other module
    uses.
    """
    return ComplianceService(
        definitions=SqlAlchemyControlDefinitionRepository(session),
        executions=SqlAlchemyControlExecutionRepository(session),
        findings=SqlAlchemyFindingRepository(session),
        remediations=SqlAlchemyRemediationRepository(session),
        audit=SqlAlchemyAuditRepository(session),
        accounting=get_accounting_engine(session),
        reporting=get_reporting_service(session),
        reconciliation=get_reconciliation_service(session),
        evidence=get_evidence_vault(session),
        period_close=get_period_close_service(session),
    )


def get_bearer_token(credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme)) -> str:
    """Raw bearer token, for the two calls that need it directly
    (logout, select_organisation) rather than an already-resolved
    Session — only the token's hash is ever stored, so once
    get_current_session has resolved it, the raw value is gone."""
    return credentials.credentials


def get_current_session(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    identity: IdentityService = Depends(get_identity_service),
    security: SecurityContext = Depends(get_security),
) -> IdentitySession:
    try:
        session = identity.validate_session(credentials.credentials)
        security.check_session(session)      # idle timeout; signs the session out for real if it has been idle too long
        return session
    except SessionNotFoundError:
        raise HTTPException(status_code=401, detail="Invalid or unknown session token.")
    except SessionExpiredError:
        raise HTTPException(status_code=401, detail="Session expired — please log in again.")
    except SessionRevokedError:
        raise HTTPException(status_code=401, detail="Session has been logged out.")
    except SessionPolicyError as exc:
        raise HTTPException(status_code=401, detail=str(exc))


def get_current_actor(session: IdentitySession = Depends(get_current_session)) -> str:
    return session.user_id


def get_current_org(
    session: IdentitySession = Depends(get_current_session),
    security: SecurityContext = Depends(get_security),
) -> str:
    if session.org_id is None:
        raise HTTPException(
            status_code=400,
            detail="No organisation selected on this session — call "
                   "POST /auth/select-organisation first.",
        )
    security.gate_org(session, session.org_id)   # organisations can require multi-factor sign-in
    return session.org_id


def require_permission(permission: str):
    """
    Dependency factory. Usage in a router:

        @router.post("/{journal_id}/post")
        def post_journal(
            ...,
            _perm: None = Depends(require_permission(JOURNAL_POST)),
        ):
            ...

    Raises 403 rather than letting PermissionDeniedError reach a generic
    handler, since the identity of the denied user/org is already known
    here and a route-specific 403 is clearer than a caught exception.
    """
    def _check(
        actor: str = Depends(get_current_actor),
        org_id: str = Depends(get_current_org),
        identity: IdentityService = Depends(get_identity_service),
    ) -> None:
        try:
            identity.require_permission(actor, org_id, permission)
        except PermissionDeniedError:
            raise HTTPException(
                status_code=403,
                detail=f"You do not have {permission!r} in this organisation.",
            )
    return _check
