"""Error hierarchy for the Identity / Organisation / Multi-Tenant module."""


class AsavexaIdentityError(Exception):
    """Base class for all identity-module domain errors."""


class OrganisationNotFoundError(AsavexaIdentityError):
    pass


class UserNotFoundError(AsavexaIdentityError):
    pass


class DuplicateEmailError(AsavexaIdentityError):
    pass


class InvalidCredentialsError(AsavexaIdentityError):
    """Deliberately used for both 'no such user' and 'wrong password' —
    never reveal which one it was (Blueprint: security engineering,
    least information disclosure on authentication failure)."""


class InactiveUserError(AsavexaIdentityError):
    pass


class MembershipNotFoundError(AsavexaIdentityError):
    pass


class DuplicateMembershipError(AsavexaIdentityError):
    """Raised when adding a membership for a user who already has one
    (active or not) in the organisation — use change_role /
    reactivate_membership instead of creating a second record."""


class LastOwnerError(AsavexaIdentityError):
    """Raised when an action would leave an organisation with zero
    active OWNER memberships — an org must never become ownerless."""


class SelfRoleChangeError(AsavexaIdentityError):
    """Raised when an actor attempts to change their own role via
    change_role(). Found during the Phase 4 security audit: with only
    an org:manage_users permission check and no actor/target
    comparison, any role holding that permission (not just OWNER —
    ADMINISTRATOR holds it too) could call change_role() on its own
    membership and grant itself OWNER, a real, concrete privilege
    escalation path. A different, already-authorized actor must
    perform any change to your own role."""


class WeakPasswordError(AsavexaIdentityError):
    """Raised when a password does not meet the minimum length NIST SP
    800-63B Revision 4 requires for a password used as the sole
    authenticator (15 characters — see domain/password.py). Found
    during the Phase 4 security audit: previously the only check
    anywhere was non-empty, so a one-character password would be
    accepted, hashed, and stored."""


class SessionNotFoundError(AsavexaIdentityError):
    pass


class SessionExpiredError(AsavexaIdentityError):
    pass


class SessionRevokedError(AsavexaIdentityError):
    pass


class NoOrganisationSelectedError(AsavexaIdentityError):
    """Raised when an org-scoped action is attempted on a session that
    has not yet selected an organisation context."""


class PermissionDeniedError(AsavexaIdentityError):
    """
    Raised whenever a user has no active membership in the organisation,
    or has one but their role lacks the required permission. Deliberately
    does not distinguish the two cases in its message — Blueprint:
    "never expose ... organisation data to an unauthorised user", which
    includes not confirming or denying that a membership exists at all.
    """


class AccountLockedError(AsavexaIdentityError):
    """Too many failed sign-ins in a short time. The lock lifts by itself; it exists to stop password guessing."""
