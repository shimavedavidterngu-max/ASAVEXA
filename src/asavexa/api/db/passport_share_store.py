"""SQLAlchemy store for the sharing service (same methods as InMemoryShareStore)."""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import defer

from ...passport.sharing import Share, ShareSession
from .passport_models import PassportShareORM, PassportShareSessionORM

_FIELDS = (
    "id", "org_id", "recipient_name", "recipient_type", "recipient_email", "purpose", "include_detail",
    "allow_download", "closed_periods_only", "date_from", "date_to", "status", "created_at", "created_by",
    "expires_at", "secret_hash", "code_salt", "code_hash", "fingerprint", "failed_attempts", "access_count",
    "last_accessed_at", "revoked_at", "revoked_by", "revoke_reason",
)
_MUTABLE = (
    "status", "failed_attempts", "access_count", "last_accessed_at", "revoked_at", "revoked_by", "revoke_reason",
)


def _to_domain(row: PassportShareORM, light: bool = False) -> Share:
    snapshot = {"share": row.meta, "fingerprint": row.fingerprint} if light else row.snapshot
    return Share(scopes=list(row.scopes), snapshot=snapshot, **{f: getattr(row, f) for f in _FIELDS})


class SqlAlchemyShareStore:
    def __init__(self, session):
        self.session = session

    def add_share(self, s: Share) -> None:
        self.session.add(PassportShareORM(
            scopes=list(s.scopes), snapshot=s.snapshot, meta=s.snapshot.get("share", {}),
            **{f: getattr(s, f) for f in _FIELDS},
        ))
        self.session.flush()

    def get_share(self, share_id: str) -> Optional[Share]:
        row = self.session.get(PassportShareORM, share_id)
        return _to_domain(row) if row is not None else None

    def save_share(self, s: Share) -> None:
        row = self.session.get(PassportShareORM, s.id)
        for f in _MUTABLE:
            setattr(row, f, getattr(s, f))
        self.session.flush()

    def list_shares(self, org_id: str) -> List[Share]:
        rows = self.session.scalars(
            select(PassportShareORM).options(defer(PassportShareORM.snapshot))
            .where(PassportShareORM.org_id == org_id).order_by(PassportShareORM.created_at.desc())
        ).all()
        return [_to_domain(r, light=True) for r in rows]

    def add_session(self, s: ShareSession) -> None:
        self.session.add(PassportShareSessionORM(
            id=s.id, share_id=s.share_id, token_hash=s.token_hash, created_at=s.created_at, expires_at=s.expires_at))
        self.session.flush()

    def get_session(self, token_hash: str) -> Optional[ShareSession]:
        row = self.session.scalar(select(PassportShareSessionORM).where(PassportShareSessionORM.token_hash == token_hash))
        if row is None:
            return None
        return ShareSession(row.id, row.share_id, row.token_hash, row.created_at, row.expires_at)

    def delete_sessions(self, share_id: str) -> None:
        self.session.execute(delete(PassportShareSessionORM).where(PassportShareSessionORM.share_id == share_id))
