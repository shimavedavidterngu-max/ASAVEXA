"""
PostgreSQL/SQLAlchemy implementation of the Identity repositories.
Implements the exact same Protocols as
identity/repository/sqlite_repository.py. Not executed in the sandbox
that produced this starter codebase — see api/__init__.py.
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from ...identity.domain.enums import MembershipStatus, Role
from ...identity.domain.models import Membership, Organisation, Session, User
from .identity_models import MembershipORM, OrganisationORM, SessionORM, UserORM


def _org_to_domain(row: OrganisationORM) -> Organisation:
    return Organisation(id=row.id, name=row.name, created_at=row.created_at)


def _user_to_domain(row: UserORM) -> User:
    return User(
        id=row.id, email=row.email, password_hash=row.password_hash,
        is_active=row.is_active, mfa_enabled=row.mfa_enabled, created_at=row.created_at,
    )


def _membership_to_domain(row: MembershipORM) -> Membership:
    return Membership(
        id=row.id, org_id=row.org_id, user_id=row.user_id, role=Role(row.role),
        status=MembershipStatus(row.status), created_at=row.created_at, created_by=row.created_by,
    )


def _session_to_domain(row: SessionORM) -> Session:
    return Session(
        id=row.id, user_id=row.user_id, org_id=row.org_id, token_hash=row.token_hash,
        created_at=row.created_at, expires_at=row.expires_at, revoked_at=row.revoked_at,
    )


class SqlAlchemyOrganisationRepository:
    def __init__(self, session: OrmSession):
        self.session = session

        def create(self, org: Organisation) -> Organisation:
        row = OrganisationORM(id=org.id, name=org.name, created_at=org.created_at)
        self.session.add(row)
        self.session.flush()
        return org

    def get(self, org_id: str) -> Optional[Organisation]:
        row = self.session.get(OrganisationORM, org_id)
        return _org_to_domain(row) if row else None

    def list_all(self) -> List[Organisation]:
        rows = self.session.scalars(select(OrganisationORM).order_by(OrganisationORM.name)).all()
        return [_org_to_domain(r) for r in rows]


class SqlAlchemyUserRepository:
    def __init__(self, session: OrmSession):
        self.session = session

    def create(self, user: User) -> User:
        row = UserORM(
            id=user.id, email=user.email, password_hash=user.password_hash,
            is_active=user.is_active, mfa_enabled=user.mfa_enabled, created_at=user.created_at,
        )
        self.session.add(row)
        return user

    def get(self, user_id: str) -> Optional[User]:
        row = self.session.get(UserORM, user_id)
        return _user_to_domain(row) if row else None

    def get_by_email(self, email: str) -> Optional[User]:
        row = self.session.scalar(select(UserORM).where(UserORM.email == email))
        return _user_to_domain(row) if row else None

    def update(self, user: User) -> User:
        row = self.session.get(UserORM, user.id)
        row.password_hash = user.password_hash
        row.is_active = user.is_active
        row.mfa_enabled = user.mfa_enabled
        return user


class SqlAlchemyMembershipRepository:
    def __init__(self, session: OrmSession):
        self.session = session

    def create(self, membership: Membership) -> Membership:
        row = MembershipORM(
            id=membership.id, org_id=membership.org_id, user_id=membership.user_id,
            role=membership.role.value, status=membership.status.value,
            created_at=membership.created_at, created_by=membership.created_by,
        )
        self.session.add(row)
        return membership

    def get(self, org_id: str, user_id: str) -> Optional[Membership]:
        row = self.session.scalar(
            select(MembershipORM).where(MembershipORM.org_id == org_id, MembershipORM.user_id == user_id)
        )
        return _membership_to_domain(row) if row else None

    def update(self, membership: Membership) -> Membership:
        row = self.session.get(MembershipORM, membership.id)
        row.role = membership.role.value
        row.status = membership.status.value
        return membership

    def list_for_org(self, org_id: str) -> List[Membership]:
        rows = self.session.scalars(
            select(MembershipORM).where(MembershipORM.org_id == org_id).order_by(MembershipORM.created_at)
        ).all()
        return [_membership_to_domain(r) for r in rows]

    def list_for_user(self, user_id: str) -> List[Membership]:
        rows = self.session.scalars(
            select(MembershipORM).where(MembershipORM.user_id == user_id).order_by(MembershipORM.created_at)
        ).all()
        return [_membership_to_domain(r) for r in rows]


class SqlAlchemySessionRepository:
    def __init__(self, session: OrmSession):
        self.session = session

    def create(self, session: Session) -> Session:
        row = SessionORM(
            id=session.id, user_id=session.user_id, org_id=session.org_id,
            token_hash=session.token_hash, created_at=session.created_at,
            expires_at=session.expires_at, revoked_at=session.revoked_at,
        )
        self.session.add(row)
        return session

    def get_by_token_hash(self, token_hash: str) -> Optional[Session]:
        row = self.session.scalar(select(SessionORM).where(SessionORM.token_hash == token_hash))
        return _session_to_domain(row) if row else None

    def update(self, session: Session) -> Session:
        row = self.session.get(SessionORM, session.id)
        row.org_id = session.org_id
        row.revoked_at = session.revoked_at
        return session
