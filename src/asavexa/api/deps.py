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
