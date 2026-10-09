"""
IdentityService — the public service facade for the Identity /
Organisation / Multi-Tenant module.

This is the ONE place that should ever check "does this user have
permission to do X in org Y" (require_permission) or create/authenticate
users and organisations. The API layer's auth dependencies
(api/deps.py) call into this; no other module's domain or service layer
should import from here — they receive an already-authorised
`actor` string and an already-resolved `org_id`, exactly as the
Accounting Engine and Evidence Vault already do.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from ...audit.entity_ids import db_entity_id
from ...audit.models import AuditEvent
from ...audit.repository import AuditRepository
from ..domain import password as password_utils
from ..domain import tokens as token_utils
from ..domain.enums import AuditAction, MembershipStatus, Role
from ..domain.errors import (
    AccountLockedError,
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
)
from ..domain.models import Membership, Organisation, Session, User
from ..domain.permissions import role_has_permission
from ..repository.interfaces import (
    MembershipRepository,
    OrganisationRepository,
    SessionRepository,
    UserRepository,
)

DEFAULT_SESSION_TTL = timedelta(hours=12)


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class IdentityService:
    def __init__(
        self,
        organisations: OrganisationRepository,
        users: UserRepository,
        memberships: MembershipRepository,
        sessions: SessionRepository,
        audit: AuditRepository,
        session_ttl: timedelta = DEFAULT_SESSION_TTL,
    ):
        self.organisations = organisations
        self.users = users
        self.memberships = memberships
        self.sessions = sessions
        self.audit = audit
        self.session_ttl = session_ttl

    # ------------------------------------------------------------------
    # Organisations
    # ------------------------------------------------------------------
    def create_organisation(self, name: str, actor: str) -> Organisation:
        org = Organisation(id=_new_id(), name=name, created_at=_now())
        self.organisations.create(org)
        self._log(AuditAction.ORGANISATION_CREATED, actor, "Organisation", org.id,
                   org_id=org.id, new_value={"name": name})
        return org

    def _get_organisation(self, org_id: str) -> Organisation:
        org = self.organisations.get(org_id)
        if org is None:
            raise OrganisationNotFoundError(f"Organisation {org_id} not found.")
        return org

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------
    def register_user(self, email: str, password: str, actor: Optional[str] = None) -> User:
        if self.users.get_by_email(email) is not None:
            raise DuplicateEmailError(f"An account already exists for {email}.")
        user = User(
            id=_new_id(), email=email, password_hash=password_utils.hash_password(password),
            is_active=True, created_at=_now(),
        )
        self.users.create(user)
        self._log(AuditAction.USER_REGISTERED, actor or user.id, "User", user.id,
                   new_value={"email": email})
        return user

    def _get_user(self, user_id: str) -> User:
        user = self.users.get(user_id)
        if user is None:
            raise UserNotFoundError(f"User {user_id} not found.")
        return user

    # ------------------------------------------------------------------
    # Memberships (the entire tenant-isolation boundary)
    # ------------------------------------------------------------------
    def _get_active_membership(self, org_id: str, user_id: str) -> Optional[Membership]:
        membership = self.memberships.get(org_id, user_id)
        if membership is None or membership.status != MembershipStatus.ACTIVE:
            return None
        return membership

    def _count_active_owners(self, org_id: str) -> int:
        return sum(
            1 for m in self.memberships.list_for_org(org_id)
            if m.role == Role.OWNER and m.status == MembershipStatus.ACTIVE
        )

    def add_membership(
        self, org_id: str, user_id: str, role: Role, actor_user_id: str
    ) -> Membership:
        """
        Grants `user_id` a role in `org_id`. If the organisation has no
        memberships at all yet, this is treated as the bootstrap case
        (creating the first OWNER right after `create_organisation`) and
        no permission check is performed — there is nobody yet who could
        have granted permission. Every subsequent call requires the
        actor to hold ORG_MANAGE_USERS in this organisation.
        """
        self._get_organisation(org_id)
        self._get_user(user_id)
        if self.memberships.get(org_id, user_id) is not None:
            raise DuplicateMembershipError(
                f"User {user_id} already has a membership in organisation {org_id}."
            )

        is_bootstrap = len(self.memberships.list_for_org(org_id)) == 0
        if not is_bootstrap:
            self.require_permission(actor_user_id, org_id, "org:manage_users")

        membership = Membership(
            id=_new_id(), org_id=org_id, user_id=user_id, role=role,
            status=MembershipStatus.ACTIVE, created_at=_now(), created_by=actor_user_id,
        )
        self.memberships.create(membership)
        self._log(AuditAction.MEMBERSHIP_CREATED, actor_user_id, "Membership", membership.id,
                   org_id=org_id, new_value={"user_id": user_id, "role": role.value})
        return membership

    def change_role(
        self, org_id: str, target_user_id: str, new_role: Role, actor_user_id: str
    ) -> Membership:
        self.require_permission(actor_user_id, org_id, "org:manage_users")
        if target_user_id == actor_user_id:
            raise SelfRoleChangeError(
                "You cannot change your own role — ask another authorized member to do it."
            )
        membership = self.memberships.get(org_id, target_user_id)
        if membership is None:
            raise MembershipNotFoundError(f"No membership for user {target_user_id} in org {org_id}.")
        if (
            membership.role == Role.OWNER
            and new_role != Role.OWNER
            and self._count_active_owners(org_id) <= 1
        ):
            raise LastOwnerError(
                "Cannot change the role of the organisation's last active owner."
            )
        previous_role = membership.role.value
        membership.role = new_role
        self.memberships.update(membership)
        self._log(AuditAction.MEMBERSHIP_ROLE_CHANGED, actor_user_id, "Membership", membership.id,
                   org_id=org_id, previous_value={"role": previous_role},
                   new_value={"role": new_role.value})
        return membership

    def revoke_membership(self, org_id: str, target_user_id: str, actor_user_id: str) -> Membership:
        self.require_permission(actor_user_id, org_id, "org:manage_users")
        membership = self.memberships.get(org_id, target_user_id)
        if membership is None:
            raise MembershipNotFoundError(f"No membership for user {target_user_id} in org {org_id}.")
        if (
            membership.role == Role.OWNER
            and membership.status == MembershipStatus.ACTIVE
            and self._count_active_owners(org_id) <= 1
        ):
            raise LastOwnerError("Cannot revoke the organisation's last active owner.")
        membership.status = MembershipStatus.REVOKED
        self.memberships.update(membership)
        self._log(AuditAction.MEMBERSHIP_REVOKED, actor_user_id, "Membership", membership.id, org_id=org_id)
        return membership

    def list_members(self, org_id: str) -> List[Membership]:
        return self.memberships.list_for_org(org_id)

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------
    MAX_FAILED_SIGNINS = 10
    LOCK_WINDOW = timedelta(minutes=15)

    def verify_credentials(self, email: str, password: str) -> User:
        """Checks the password and returns the user. Always calls verify_password() exactly once on every path,
        including when no account matches the given email — verifying against password_utils.DUMMY_HASH in that
        case — so a nonexistent-email attempt and a wrong-password attempt cost the same PBKDF2 work and are not
        distinguishable by response timing (found during the Phase 4 security audit).

        After MAX_FAILED_SIGNINS failures within LOCK_WINDOW the account (or the email, if there is no such account,
        so the lock does not reveal which emails exist) refuses further attempts until the window passes."""
        user = self.users.get_by_email(email)
        who = user.id if user is not None else email
        if self.audit.count_recent_for_actor(who, AuditAction.LOGIN_FAILED.value, _now() - self.LOCK_WINDOW) >= self.MAX_FAILED_SIGNINS:
            raise AccountLockedError("Too many failed sign-in attempts. Please wait 15 minutes and try again.")
        if user is None:
            password_utils.verify_password(password, password_utils.DUMMY_HASH)
            self._log(AuditAction.LOGIN_FAILED, email, "User", db_entity_id(email), reason="no such account")
            raise InvalidCredentialsError("Invalid email or password.")
        if not user.is_active:
            password_utils.verify_password(password, password_utils.DUMMY_HASH)
            self._log(AuditAction.LOGIN_FAILED, user.id, "User", user.id, reason="inactive account")
            raise InactiveUserError("This account is inactive.")
        if not password_utils.verify_password(password, user.password_hash):
            self._log(AuditAction.LOGIN_FAILED, user.id, "User", user.id, reason="wrong password")
            raise InvalidCredentialsError("Invalid email or password.")
        return user

    def issue_session(self, user: User) -> tuple:
        """Creates a session for an already-verified user. Returns (Session, raw_token); the raw token is shown to
        the caller exactly once — only its hash is ever stored."""
        raw_token = token_utils.generate_token()
        session = Session(
            id=_new_id(), user_id=user.id, token_hash=token_utils.hash_token(raw_token),
            created_at=_now(), expires_at=_now() + self.session_ttl, org_id=None,
        )
        self.sessions.create(session)
        self._log(AuditAction.LOGIN_SUCCEEDED, user.id, "User", user.id)
        return session, raw_token

    def authenticate(self, email: str, password: str) -> tuple[User, str]:
        """Returns (user, raw_session_token)."""
        user = self.verify_credentials(email, password)
        _, raw_token = self.issue_session(user)
        return user, raw_token

    def select_organisation(self, raw_token: str, org_id: str) -> Session:
        session = self.validate_session(raw_token)
        if self._get_active_membership(org_id, session.user_id) is None:
            raise PermissionDeniedError(
                "You do not have access to this organisation."
            )
        session.org_id = org_id
        self.sessions.update(session)
        self._log(AuditAction.ORG_CONTEXT_SELECTED, session.user_id, "Session", session.id, org_id=org_id)
        return session

    def logout(self, raw_token: str) -> None:
        session = self.sessions.get_by_token_hash(token_utils.hash_token(raw_token))
        if session is None:
            raise SessionNotFoundError("Session not found.")
        if session.revoked_at is None:
            session.revoked_at = _now()
            self.sessions.update(session)
            self._log(AuditAction.LOGOUT, session.user_id, "Session", session.id, org_id=session.org_id)

    def validate_session(self, raw_token: str) -> Session:
        session = self.sessions.get_by_token_hash(token_utils.hash_token(raw_token))
        if session is None:
            raise SessionNotFoundError("Session not found or token invalid.")
        if session.revoked_at is not None:
            raise SessionRevokedError("This session has been logged out.")
        expires_at = session.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if _now() > expires_at:
            raise SessionExpiredError("This session has expired — please log in again.")
        return session

    # ------------------------------------------------------------------
    # Authorization — the primitive every other module's API routes use
    # ------------------------------------------------------------------
    def get_role(self, user_id: str, org_id: str) -> Optional[Role]:
        membership = self._get_active_membership(org_id, user_id)
        return membership.role if membership else None

    def require_permission(self, user_id: str, org_id: str, permission: str) -> Role:
        """
        Raises PermissionDeniedError if the user has no active
        membership in org_id, or has one but their role lacks the
        permission. Deliberately gives the same error either way (see
        PermissionDeniedError's docstring).
        """
        membership = self._get_active_membership(org_id, user_id)
        if membership is None or not role_has_permission(membership.role, permission):
            raise PermissionDeniedError(
                f"User {user_id} does not have {permission!r} in organisation {org_id}."
            )
        return membership.role

    # ------------------------------------------------------------------
    def _log(
        self,
        action: AuditAction,
        actor: str,
        entity_type: str,
        entity_id: str,
        org_id: Optional[str] = None,
        previous_value: Optional[dict] = None,
        new_value: Optional[dict] = None,
        reason: Optional[str] = None,
    ) -> None:
        self.audit.record(
            AuditEvent(
                id=_new_id(), org_id=org_id, entity_type=entity_type, entity_id=entity_id,
                action=action.value, actor=actor, timestamp=_now(),
                previous_value=previous_value, new_value=new_value, reason=reason,
            )
        )
