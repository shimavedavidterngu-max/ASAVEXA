"""
Asavexa API — Accounting Engine + Identity/Organisation + Evidence Vault.

Run (once requirements.txt is installed and PostgreSQL is reachable):

    uvicorn asavexa.api.main:app --reload

Not executed inside the sandbox that produced this starter codebase —
see api/__init__.py and docs/runtime-verification.md for the full,
current account of what's verified vs. pending. The domain logic this
API exposes is proven by the tests/ directory (245 tests as of the
Phase 4 security-hardening pass) against the SQLite adapters.

Typical flow for a fresh client:
    1. POST /auth/register            — create a user
    2. POST /auth/login               — get a bearer session token
    3. POST /organisations            — create an org; caller becomes OWNER
       (or POST /organisations/{id}/members if invited to an existing org)
    4. POST /auth/select-organisation — pick which org this session acts in
    5. Every other endpoint requires "Authorization: Bearer <token>" and
       uses the session's selected organisation as its tenant scope.
"""
import os
import logging
import time
import uuid

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import DataError, IntegrityError

from .db.base import get_session

from ..accounting.domain.errors import (
    AccountNotFoundError,
    AsavexaAccountingError,
    ImmutableJournalError,
    InvalidJournalStateError,
    JournalNotFoundError,
    PeriodLockedError,
    PeriodNotFoundError,
    UnbalancedJournalError,
)
from ..evidence.domain.errors import (
    AsavexaEvidenceError,
    DuplicateEvidenceError,
    EvidenceNotFoundError,
    InvalidEvidenceStateError,
)
from ..identity.domain.errors import (
    AsavexaIdentityError,
    DuplicateEmailError,
    DuplicateMembershipError,
    InactiveUserError,
    InvalidCredentialsError,
    LastOwnerError,
    MembershipNotFoundError,
    OrganisationNotFoundError,
    PermissionDeniedError,
    SelfRoleChangeError,
    SessionExpiredError,
    SessionNotFoundError,
    SessionRevokedError,
    UserNotFoundError,
    WeakPasswordError,
)
from ..ai.errors import AiSubjectNotFoundError, AiValidationError, AsavexaAiError
from ..ingestion.errors import IngestionError
from ..passport.errors import (
    AsavexaPassportError,
    ShareAccessDeniedError,
    ShareNotFoundError,
    ShareStateError,
)
from ..standards.errors import AsavexaStandardsError
from ..reconciliation.domain.errors import (
    AsavexaReconciliationError,
    BankAccountNotFoundError,
    BankTransactionNotFoundError,
    DuplicateExternalTransactionError,
    InvalidReconciliationStateError,
    InvalidTransactionStateError,
    JournalAlreadyMatchedError,
    ReconciliationNotFoundError,
    UnresolvedTransactionsError,
)
from ..reporting.domain.errors import (
    AsavexaReportingError,
    EvidenceNotConfiguredError,
    ReconciliationNotConfiguredError,
    ReportingAccountNotFoundError,
    ReportingPeriodNotFoundError,
    UnknownReportTypeError,
    UnsupportedAccountClassificationError,
)
from ..period_close.domain.errors import (
    AsavexaPeriodCloseError,
    CloseAlreadyInProgressError,
    CloseNotReadyError,
    InvalidCloseStateError,
    NotReviewedError,
    PeriodCloseProcessNotFoundError,
    PeriodNotFoundError as PeriodClosePeriodNotFoundError,
)
from ..compliance.domain.errors import (
    AsavexaComplianceError,
    ControlDefinitionNotFoundError,
    ControlExecutionNotFoundError,
    DuplicateControlCodeError,
    FindingAlreadyExistsError,
    FindingNotFoundError,
    InactiveControlError,
    InvalidFindingStateError,
    InvalidRemediationStateError,
    RemediationNotFoundError,
    RemediationRequiredError,
    UnknownCheckKeyError,
)
from .routers import accounts, ai, audit, auth, compliance, evidence, ingestion, journals, organisation_profile, passport, period_close, periods, reconciliation, reporting, shared_passport, standards

app = FastAPI(
    title="Asavexa",
    description=(
        "Financial evidence, verification and reporting platform. "
        "Accounting Engine + Identity/Organisation/Multi-Tenant + "
        "Evidence Vault. See README.md."
    ),
    version="0.2.0",
)

# ----------------------------------------------------------------------
# CORS (Phase 6, Step 15). Origins come from CORS_ALLOWED_ORIGINS (a
# comma-separated env var), never a wildcard — this API uses Bearer
# tokens (not cookies), so allow_credentials is False and there is no
# CSRF exposure from CORS itself (a cross-origin page can't read an
# Authorization header it didn't set, and can't set one without
# already having the token). Defaults to the two local dev origins the
# frontend's own docs (frontend-runtime-verification.md) describe
# serving from (`python3 -m http.server`'s default 8000 would collide
# with the API's own default port, so that doc uses 5173) plus 5173
# itself, and 8080 as a second common static-file-server default.
# Never enable allow_credentials=True unless the auth model changes to
# cookies, at which point CSRF protection must be added alongside it —
# see docs/security-architecture.md.
_default_dev_origins = "http://localhost:5173,http://localhost:8080,http://127.0.0.1:5173"
_cors_origins = [
    origin.strip()
    for origin in os.environ.get("CORS_ALLOWED_ORIGINS", _default_dev_origins).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# ----------------------------------------------------------------------
# Observability (Phase 7, Step 9). Found entirely absent before this
# audit: no logging module was imported anywhere in this codebase.
# This is deliberately separate from the shared AUDIT trail
# (asavexa/audit/) — that records business-meaning events (who posted
# which journal, who verified which finding) and is append-only,
# permanent, and queried by the application itself. This logger
# records OPERATIONAL events (a request happened, an unexpected error
# occurred) for debugging and monitoring, is not queried by the
# application, and is expected to roll over/expire per whatever log
# infrastructure the deployment environment provides — the two must
# never be confused or merged into one store. See
# docs/security-architecture.md for the audit trail's own guarantees,
# unaffected by anything below.
logger = logging.getLogger("asavexa")


@app.middleware("http")
async def request_id_and_logging_middleware(request: Request, call_next):
    """Assigns a per-request id (also returned as the X-Request-ID
    response header, so a client can reference it when reporting an
    issue) and logs method/path/status/duration for every request.

    Deliberately logs ONLY method, path, status, and duration — never
    the request body and never any header. This matters concretely:
    POST /auth/login and /auth/register carry a password in their body,
    and every authenticated request carries a bearer token in its
    Authorization header. Logging "request received" generically enough
    to be useful, without ever touching body/headers, is what keeps
    this middleware from becoming the exact password/token leak Phase 4
    and Phase 6's static sweeps already proved doesn't exist elsewhere
    in this codebase.
    """
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    started = time.monotonic()
    response = await call_next(request)
    duration_ms = (time.monotonic() - started) * 1000
    logger.info(
        "request",
        extra={
            "request_id": request_id, "method": request.method, "path": request.url.path,
            "status_code": response.status_code, "duration_ms": round(duration_ms, 1),
        },
    )
    response.headers["X-Request-ID"] = request_id
    return response

app.include_router(auth.router)
app.include_router(auth.org_router)
app.include_router(accounts.router)
app.include_router(periods.router)
app.include_router(journals.router)
app.include_router(evidence.router)
app.include_router(reconciliation.router)
app.include_router(reconciliation.txn_router)
app.include_router(reporting.router)
app.include_router(period_close.router)
app.include_router(compliance.router)
app.include_router(audit.router)
app.include_router(organisation_profile.router)
app.include_router(standards.router)
app.include_router(passport.router)
app.include_router(ai.router)
app.include_router(ingestion.router)
app.include_router(shared_passport.router)


@app.on_event("startup")
def _ensure_optional_tables() -> None:
    """Creates tables added after the initial migration (idempotent).
    A failure here is logged, never fatal: the rest of the API must
    still start even if this one table cannot be created."""
    from .db.passport_models import ensure_share_tables, ensure_structure_table
    from .db.profile_models import ensure_profile_table
    from .db.standards_models import ensure_standards_table

    for name, ensure in (
        ("organisation_profiles", ensure_profile_table),
        ("organisation_standards", ensure_standards_table),
        ("organisation_structures", ensure_structure_table),
        ("passport_shares", ensure_share_tables),
    ):
        try:
            ensure()
        except Exception:  # pragma: no cover - environment dependent
            logger.exception("could not ensure table %s", name)


# ----------------------------------------------------------------------
# Error handling — the blueprint's Error Handling Rule: "never hide
# errors ... explain the problem". Every domain error becomes a clear,
# specific HTTP response instead of an opaque 500. Authentication and
# authorization failures are handled directly in api/deps.py (401/403)
# since those need request-specific context; everything else lands here.
# ----------------------------------------------------------------------
_ACCOUNTING_NOT_FOUND = (JournalNotFoundError, AccountNotFoundError, PeriodNotFoundError)
_ACCOUNTING_CONFLICT = (
    UnbalancedJournalError, ImmutableJournalError, InvalidJournalStateError, PeriodLockedError,
)

_IDENTITY_NOT_FOUND = (OrganisationNotFoundError, UserNotFoundError, MembershipNotFoundError)
_IDENTITY_UNAUTHORIZED = (InvalidCredentialsError, InactiveUserError,
                          SessionNotFoundError, SessionExpiredError, SessionRevokedError)
_IDENTITY_CONFLICT = (DuplicateEmailError, DuplicateMembershipError, LastOwnerError, SelfRoleChangeError)

_EVIDENCE_NOT_FOUND = (EvidenceNotFoundError,)
_EVIDENCE_CONFLICT = (DuplicateEvidenceError, InvalidEvidenceStateError)

_RECONCILIATION_NOT_FOUND = (ReconciliationNotFoundError, BankTransactionNotFoundError, BankAccountNotFoundError)
_RECONCILIATION_CONFLICT = (
    DuplicateExternalTransactionError, InvalidReconciliationStateError, InvalidTransactionStateError,
    JournalAlreadyMatchedError, UnresolvedTransactionsError,
)

_REPORTING_NOT_FOUND = (ReportingPeriodNotFoundError, ReportingAccountNotFoundError)
_REPORTING_CONFLICT = (UnsupportedAccountClassificationError,)
_REPORTING_BAD_REQUEST = (UnknownReportTypeError, ReconciliationNotConfiguredError, EvidenceNotConfiguredError)

_PERIOD_CLOSE_NOT_FOUND = (PeriodCloseProcessNotFoundError, PeriodClosePeriodNotFoundError)
_PERIOD_CLOSE_CONFLICT = (
    CloseAlreadyInProgressError, CloseNotReadyError, InvalidCloseStateError, NotReviewedError,
)

_COMPLIANCE_NOT_FOUND = (
    ControlDefinitionNotFoundError, ControlExecutionNotFoundError,
    FindingNotFoundError, RemediationNotFoundError,
)
_COMPLIANCE_CONFLICT = (
    DuplicateControlCodeError, InactiveControlError, InvalidFindingStateError,
    InvalidRemediationStateError, RemediationRequiredError, FindingAlreadyExistsError,
)
_COMPLIANCE_BAD_REQUEST = (UnknownCheckKeyError,)


def _error_response(
    request: Request, exc: Exception, status_code: int, human_review_required: bool = False,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None) if request is not None else None
    return JSONResponse(
        status_code=status_code,
        content={
            "error": type(exc).__name__,
            "message": str(exc),
            "human_review_required": human_review_required,
            "request_id": request_id,
        },
    )


@app.exception_handler(AsavexaStandardsError)
async def handle_standards_error(request: Request, exc: AsavexaStandardsError):
    return _error_response(request, exc, 400)


@app.exception_handler(AsavexaPassportError)
async def handle_passport_error(request: Request, exc: AsavexaPassportError):
    if isinstance(exc, ShareAccessDeniedError):
        return _error_response(request, exc, 403)
    if isinstance(exc, ShareNotFoundError):
        return _error_response(request, exc, 404)
    if isinstance(exc, ShareStateError):
        return _error_response(request, exc, 409)
    return _error_response(request, exc, 400)


@app.exception_handler(IngestionError)
async def handle_ingestion_error(request: Request, exc: IngestionError):
    return _error_response(request, exc, 400)


@app.exception_handler(AsavexaAiError)
async def handle_ai_error(request: Request, exc: AsavexaAiError):
    return _error_response(request, exc, 404 if isinstance(exc, AiSubjectNotFoundError) else 400)


@app.exception_handler(AsavexaAccountingError)
def handle_accounting_error(request: Request, exc: AsavexaAccountingError):
    if isinstance(exc, _ACCOUNTING_NOT_FOUND):
        return _error_response(request, exc, 404)
    if isinstance(exc, _ACCOUNTING_CONFLICT):
        return _error_response(request, exc, 409, human_review_required=True)
    return _error_response(request, exc, 400)


@app.exception_handler(AsavexaIdentityError)
def handle_identity_error(request: Request, exc: AsavexaIdentityError):
    if isinstance(exc, PermissionDeniedError):
        return _error_response(request, exc, 403)
    if isinstance(exc, _IDENTITY_UNAUTHORIZED):
        return _error_response(request, exc, 401)
    if isinstance(exc, _IDENTITY_NOT_FOUND):
        return _error_response(request, exc, 404)
    if isinstance(exc, _IDENTITY_CONFLICT):
        return _error_response(request, exc, 409, human_review_required=isinstance(exc, LastOwnerError))
    return _error_response(request, exc, 400)


@app.exception_handler(AsavexaEvidenceError)
def handle_evidence_error(request: Request, exc: AsavexaEvidenceError):
    if isinstance(exc, _EVIDENCE_NOT_FOUND):
        return _error_response(request, exc, 404)
    if isinstance(exc, _EVIDENCE_CONFLICT):
        return _error_response(request, exc, 409, human_review_required=True)
    return _error_response(request, exc, 400)


@app.exception_handler(AsavexaReconciliationError)
def handle_reconciliation_error(request: Request, exc: AsavexaReconciliationError):
    if isinstance(exc, _RECONCILIATION_NOT_FOUND):
        return _error_response(request, exc, 404)
    if isinstance(exc, _RECONCILIATION_CONFLICT):
        return _error_response(request, exc, 409, human_review_required=True)
    return _error_response(request, exc, 400)


@app.exception_handler(AsavexaReportingError)
def handle_reporting_error(request: Request, exc: AsavexaReportingError):
    if isinstance(exc, _REPORTING_NOT_FOUND):
        return _error_response(request, exc, 404)
    if isinstance(exc, _REPORTING_CONFLICT):
        return _error_response(request, exc, 409, human_review_required=True)
    if isinstance(exc, _REPORTING_BAD_REQUEST):
        return _error_response(request, exc, 400)
    return _error_response(request, exc, 400)


@app.exception_handler(AsavexaPeriodCloseError)
def handle_period_close_error(request: Request, exc: AsavexaPeriodCloseError):
    if isinstance(exc, _PERIOD_CLOSE_NOT_FOUND):
        return _error_response(request, exc, 404)
    if isinstance(exc, _PERIOD_CLOSE_CONFLICT):
        return _error_response(request, exc, 409, human_review_required=True)
    return _error_response(request, exc, 400)


@app.exception_handler(AsavexaComplianceError)
def handle_compliance_error(request: Request, exc: AsavexaComplianceError):
    if isinstance(exc, _COMPLIANCE_NOT_FOUND):
        return _error_response(request, exc, 404)
    if isinstance(exc, _COMPLIANCE_CONFLICT):
        return _error_response(request, exc, 409, human_review_required=True)
    if isinstance(exc, _COMPLIANCE_BAD_REQUEST):
        return _error_response(request, exc, 400)
    return _error_response(request, exc, 400)


def _cors_headers_for(request: Request) -> dict:
    """Starlette runs the catch-all 500 handler OUTSIDE CORSMiddleware,
    so without this a server error reaches the browser with no CORS
    headers and shows up as an opaque "Failed to fetch" (which the UI
    reports as "could not reach the API"). Echoing the allowed origin
    lets the real error message through."""
    origin = request.headers.get("origin")
    if origin and origin in _cors_origins:
        return {"Access-Control-Allow-Origin": origin, "Vary": "Origin"}
    return {}


@app.exception_handler(DataError)
async def handle_database_data_error(request: Request, exc: DataError):
    """A value the database cannot store — most commonly an id that is
    not a valid UUID, or text that is too long. This is a bad request,
    not a server fault."""
    logger.warning("database_data_error", extra={"path": request.url.path})
    response = _error_response(
        request, ValueError(
            "One of the submitted values is not valid — for example an ID that is not a real record ID, "
            "or text that is too long. Please check the fields and try again."
        ), 400,
    )
    response.headers.update(_cors_headers_for(request))
    return response


@app.exception_handler(IntegrityError)
async def handle_database_integrity_error(request: Request, exc: IntegrityError):
    """A uniqueness or reference rule was violated (duplicate, or a
    reference to a record that does not exist)."""
    logger.warning("database_integrity_error", extra={"path": request.url.path})
    response = _error_response(
        request, ValueError(
            "This conflicts with existing data — the record may already exist, or it refers to something "
            "that does not exist."
        ), 409,
    )
    response.headers.update(_cors_headers_for(request))
    return response


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception):
    """The catch-all this audit found missing entirely. Without this,
    any exception not already one of the seven domain error hierarchies
    above (a genuine bug, a database connectivity failure not wrapped
    in a domain error, anything unanticipated) would fall through to
    FastAPI/Starlette's own default handling — which is not guaranteed
    to keep a stack trace, environment detail, or internal path out of
    the response depending on framework debug configuration.

    Logs the full exception server-side (str(exc) here is safe — this
    is the server's own log, not the client response) and returns only
    a fixed, generic message plus the request id, never str(exc) or
    the real exception type name, to the client. The request id lets
    an operator correlate a user's bug report with the exact server
    log line that has the real detail, without ever exposing that
    detail over the wire."""
    request_id = getattr(request.state, "request_id", None)
    logger.exception("unhandled_exception", extra={"request_id": request_id, "path": request.url.path})
    return JSONResponse(
        status_code=500,
        headers=_cors_headers_for(request),
        content={
            "error": "InternalServerError",
            "message": "An unexpected error occurred. If this persists, contact support and reference the request_id below.",
            "human_review_required": True,
            "request_id": request_id,
        },
    )


@app.get("/health")
def health():
    """Liveness only: the application process is running and can
    respond to HTTP requests. Does NOT touch the database — a healthy
    response here says nothing about whether PostgreSQL is reachable.
    See /ready for that. Kept deliberately fast and dependency-free so
    an orchestrator's liveness probe never fails merely because the
    database is briefly unavailable (which should trigger readiness
    failures, not a container restart)."""
    return {"status": "ok", "modules": [
        "identity", "accounting", "evidence", "reconciliation", "reporting", "period_close", "compliance",
    ]}


@app.get("/ready")
def ready(session=Depends(get_session)):
    """Readiness: the application can actually reach the configured
    database. Found missing during the Phase 3 persistence audit —
    /health only ever proved the process was alive, never that
    PostgreSQL was reachable, so an orchestrator relying on /health
    alone could route real traffic to an instance with no working
    database connection. Runs one trivial, real query (`SELECT 1`)
    against the session FastAPI's own dependency injection provides —
    the same session every other endpoint uses, not a separate
    connection — and reports failure explicitly rather than raising an
    unhandled 500."""
    try:
        session.execute(text("SELECT 1"))
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "detail": f"database unreachable: {exc}"},
        )
    return {"status": "ready"}
