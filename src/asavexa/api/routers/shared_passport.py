"""
Recipient side of Passport sharing. These routes are deliberately NOT behind the
organisation login: a bank or auditor has no ASAVEXA account. They are protected
by the share itself (link secret + access code [+ email]) and by a short-lived
session issued only after verification. Every refusal gives the same generic
message and nothing about the organisation.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header

from ...passport.errors import ShareAccessDeniedError
from ...passport.sharing import SESSION_EXPIRED, ShareService
from ..db.audit_sqlalchemy_repository import SqlAlchemyAuditRepository
from ..db.base import get_session
from ..db.passport_share_store import SqlAlchemyShareStore
from ..schemas.passport import ShareVerifyIn

router = APIRouter(prefix="/shared-passport", tags=["Shared Passport (recipient)"])


def _service(session) -> ShareService:
    return ShareService(SqlAlchemyShareStore(session), SqlAlchemyAuditRepository(session))


def _bearer(authorization: Optional[str]) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise ShareAccessDeniedError(SESSION_EXPIRED)
    return token.strip()


@router.post("/verify")
def verify(body: ShareVerifyIn, session=Depends(get_session)):
    """Exchanges link + access code (+ email) for a one-hour viewing session."""
    try:
        return _service(session).verify(body.access_token, body.access_code, body.email, datetime.now(timezone.utc))
    except ShareAccessDeniedError:
        # The request ends in an error, which would normally roll the transaction
        # back. A wrong attempt MUST be kept: it is what counts toward the lock and
        # what the organisation sees in the access log.
        session.commit()
        raise


@router.get("/view")
def view(authorization: Optional[str] = Header(None), session=Depends(get_session)):
    """The approved snapshot, with an integrity check against its fingerprint."""
    return _service(session).view(_bearer(authorization), datetime.now(timezone.utc))


@router.get("/download")
def download(authorization: Optional[str] = Header(None), session=Depends(get_session)):
    """The snapshot as a document - only if the organisation allowed downloads. Logged."""
    return _service(session).download(_bearer(authorization), datetime.now(timezone.utc))
