"""
Automated tests for the Identity / Organisation / Multi-Tenant module.

Run with:  PYTHONPATH=src python3 -m unittest discover -s tests -v

Stdlib-only — no external dependencies required.
"""
import time
import unittest
from datetime import timedelta

from asavexa.audit.sqlite_repository import SqliteAuditRepository, ensure_schema as ensure_audit_schema
from asavexa.identity.domain.enums import MembershipStatus, Role
from asavexa.identity.domain.errors import (
    DuplicateEmailError,
    DuplicateMembershipError,
    InactiveUserError,
    InvalidCredentialsError,
    LastOwnerError,
    PermissionDeniedError,
    SelfRoleChangeError,
    SessionExpiredError,
    SessionRevokedError,
    WeakPasswordError,
)
from asavexa.identity.domain.permissions import JOURNAL_POST, ORG_MANAGE_USERS
from asavexa.identity.repository.sqlite_repository import (
    SqliteMembershipRepository,
    SqliteOrganisationRepository,
    SqliteSessionRepository,
    SqliteUserRepository,
    connect,
)
from asavexa.identity.services.service import IdentityService


def build_service(session_ttl=timedelta(hours=12)) -> IdentityService:
    conn = connect(":memory:")
    ensure_audit_schema(conn)
    return IdentityService(
        organisations=SqliteOrganisationRepository(conn),
        users=SqliteUserRepository(conn),
        memberships=SqliteMembershipRepository(conn),
        sessions=SqliteSessionRepository(conn),
        audit=SqliteAuditRepository(conn),
        session_ttl=session_ttl,
    )


class IdentityServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.identity = build_service()
        self.owner = self.identity.register_user("dara@meridian.test", "correct horse battery staple")
        self.org = self.identity.create_organisation("Meridian Textiles Ltd", actor=self.owner.id)
        # Bootstrap: first membership in a fresh org needs no permission check.
        self.identity.add_membership(self.org.id, self.owner.id, Role.OWNER, actor_user_id=self.owner.id)

    # ------------------------------------------------------------------
    def test_bootstrap_owner_can_add_a_second_member(self):
        accountant = self.identity.register_user("aisha@meridian.test", "another-strong-password")
        membership = self.identity.add_membership(
            self.org.id, accountant.id, Role.ACCOUNTANT, actor_user_id=self.owner.id
        )
        self.assertEqual(membership.role, Role.ACCOUNTANT)
        self.assertEqual(membership.status, MembershipStatus.ACTIVE)

    def test_non_member_cannot_add_members(self):
        outsider = self.identity.register_user("outsider@example.com", "irrelevant-password")
        someone_else = self.identity.register_user("someone@example.com", "irrelevant-password-2")
        with self.assertRaises(PermissionDeniedError):
            self.identity.add_membership(self.org.id, someone_else.id, Role.READ_ONLY, actor_user_id=outsider.id)

    def test_read_only_role_cannot_manage_users(self):
        viewer = self.identity.register_user("viewer@meridian.test", "viewer-password-123")
        self.identity.add_membership(self.org.id, viewer.id, Role.READ_ONLY, actor_user_id=self.owner.id)
        someone_else = self.identity.register_user("someone2@example.com", "password-123456")
        with self.assertRaises(PermissionDeniedError):
            self.identity.add_membership(self.org.id, someone_else.id, Role.READ_ONLY, actor_user_id=viewer.id)

    def test_duplicate_email_registration_is_rejected(self):
        with self.assertRaises(DuplicateEmailError):
            self.identity.register_user("dara@meridian.test", "some-other-password")

    def test_password_shorter_than_fifteen_characters_is_rejected(self):
        """NIST SP 800-63B Revision 4: 15 characters minimum for a
        password used as the sole authenticator. Found missing
        entirely during the Phase 4 security audit — previously any
        non-empty password was accepted."""
        with self.assertRaises(WeakPasswordError):
            self.identity.register_user("short@meridian.test", "short14chars12")  # 14 chars

    def test_password_exactly_fifteen_characters_is_accepted(self):
        user = self.identity.register_user("exactly15@meridian.test", "exactly15-chars")  # 15 chars
        self.assertIsNotNone(user.id)

    def test_empty_password_is_still_rejected(self):
        with self.assertRaises(WeakPasswordError):
            self.identity.register_user("empty@meridian.test", "")

    def test_duplicate_membership_is_rejected(self):
        with self.assertRaises(DuplicateMembershipError):
            self.identity.add_membership(self.org.id, self.owner.id, Role.ACCOUNTANT, actor_user_id=self.owner.id)

    # ------------------------------------------------------------------
    def test_cannot_revoke_the_last_owner(self):
        with self.assertRaises(LastOwnerError):
            self.identity.revoke_membership(self.org.id, self.owner.id, actor_user_id=self.owner.id)

    def test_cannot_demote_the_last_owner(self):
        """A different, authorized actor attempts the demotion — not
        the owner themselves — since self-targeting now hits
        SelfRoleChangeError first (see
        test_cannot_change_own_role_even_with_permission below). This
        keeps testing the original invariant (the last owner cannot be
        demoted, by anyone) rather than the newer, separate one."""
        administrator = self.identity.register_user("admin@meridian.test", "password-123456")
        self.identity.add_membership(self.org.id, administrator.id, Role.ADMINISTRATOR, actor_user_id=self.owner.id)
        with self.assertRaises(LastOwnerError):
            self.identity.change_role(self.org.id, self.owner.id, Role.MANAGER, actor_user_id=administrator.id)

    def test_cannot_change_own_role_even_with_permission(self):
        """Privilege-escalation regression test, Phase 4 security audit:
        ADMINISTRATOR holds org:manage_users (confirmed against the
        real permission registry, not assumed) but must not be able to
        call change_role on its own membership — without this guard,
        an ADMINISTRATOR could grant itself OWNER, which holds
        ALL_PERMISSIONS, a real escalation from a deliberately narrower
        role."""
        administrator = self.identity.register_user("admin2@meridian.test", "password-123456")
        self.identity.add_membership(self.org.id, administrator.id, Role.ADMINISTRATOR, actor_user_id=self.owner.id)
        with self.assertRaises(SelfRoleChangeError):
            self.identity.change_role(self.org.id, administrator.id, Role.OWNER, actor_user_id=administrator.id)
        # Confirm the escalation genuinely did not happen — still ADMINISTRATOR.
        self.assertEqual(self.identity.get_role(administrator.id, self.org.id), Role.ADMINISTRATOR)

    def test_owner_cannot_self_promote_either(self):
        """The guard is actor==target, not role-based — even OWNER
        (which already holds every permission and has nothing to gain)
        is blocked from calling change_role on itself, keeping the
        invariant simple and exceptionless rather than carving out
        the 'already-most-privileged' role as a special case."""
        second_owner = self.identity.register_user("second-owner2@meridian.test", "password-123456")
        self.identity.add_membership(self.org.id, second_owner.id, Role.OWNER, actor_user_id=self.owner.id)
        with self.assertRaises(SelfRoleChangeError):
            self.identity.change_role(self.org.id, second_owner.id, Role.MANAGER, actor_user_id=second_owner.id)

    def test_second_owner_allows_first_to_be_revoked(self):
        second_owner = self.identity.register_user("second-owner@meridian.test", "password-123456")
        self.identity.add_membership(self.org.id, second_owner.id, Role.OWNER, actor_user_id=self.owner.id)
        # Now there are two active owners — revoking one is fine.
        membership = self.identity.revoke_membership(self.org.id, self.owner.id, actor_user_id=second_owner.id)
        self.assertEqual(membership.status, MembershipStatus.REVOKED)
        self.assertIsNone(self.identity.get_role(self.owner.id, self.org.id))

    # ------------------------------------------------------------------
    def test_authenticate_with_correct_password_succeeds(self):
        user, token = self.identity.authenticate("dara@meridian.test", "correct horse battery staple")
        self.assertEqual(user.id, self.owner.id)
        self.assertTrue(token)

    def test_authenticate_with_wrong_password_fails(self):
        with self.assertRaises(InvalidCredentialsError):
            self.identity.authenticate("dara@meridian.test", "wrong-password")

    def test_authenticate_unknown_email_fails_with_same_error_type(self):
        with self.assertRaises(InvalidCredentialsError):
            self.identity.authenticate("nobody@example.com", "whatever-password")

    def test_authenticate_unknown_email_still_performs_password_verification(self):
        """Timing side-channel fix, found during the Phase 4 security
        audit: authenticate() previously returned immediately for a
        nonexistent email, skipping verify_password() entirely, while a
        wrong-password attempt against a real account always paid the
        full PBKDF2 cost — an attacker could enumerate registered
        emails purely from response time. Proven deterministically here
        (call-count, not wall-clock timing, which would be flaky) rather
        than only asserting the error type is the same."""
        from unittest.mock import patch
        from asavexa.identity.domain import password as password_utils

        with patch.object(password_utils, "verify_password", wraps=password_utils.verify_password) as spy:
            with self.assertRaises(InvalidCredentialsError):
                self.identity.authenticate("nobody@example.com", "whatever-password")
            self.assertEqual(spy.call_count, 1)
            # Verified against the dummy hash specifically, not skipped.
            self.assertEqual(spy.call_args.args[1], password_utils.DUMMY_HASH)

    def test_inactive_user_cannot_authenticate(self):
        user = self.identity.register_user("inactive@meridian.test", "password-123456")
        user.is_active = False
        self.identity.users.update(user)
        with self.assertRaises(InactiveUserError):
            self.identity.authenticate("inactive@meridian.test", "password-123456")

    # ------------------------------------------------------------------
    def test_session_lifecycle_select_org_logout(self):
        _, token = self.identity.authenticate("dara@meridian.test", "correct horse battery staple")
        session = self.identity.validate_session(token)
        self.assertIsNone(session.org_id)

        selected = self.identity.select_organisation(token, self.org.id)
        self.assertEqual(selected.org_id, self.org.id)

        self.identity.logout(token)
        with self.assertRaises(SessionRevokedError):
            self.identity.validate_session(token)

    def test_cannot_select_organisation_without_membership(self):
        other_org = self.identity.create_organisation("Other Org", actor=self.owner.id)
        _, token = self.identity.authenticate("dara@meridian.test", "correct horse battery staple")
        with self.assertRaises(PermissionDeniedError):
            self.identity.select_organisation(token, other_org.id)

    def test_expired_session_is_rejected(self):
        short_lived = build_service(session_ttl=timedelta(milliseconds=10))
        user = short_lived.register_user("quick@meridian.test", "password-123456")
        _, token = short_lived.authenticate("quick@meridian.test", "password-123456")
        time.sleep(0.05)
        with self.assertRaises(SessionExpiredError):
            short_lived.validate_session(token)

    # ------------------------------------------------------------------
    def test_require_permission_succeeds_for_owner(self):
        role = self.identity.require_permission(self.owner.id, self.org.id, ORG_MANAGE_USERS)
        self.assertEqual(role, Role.OWNER)

    def test_require_permission_denied_for_wrong_role(self):
        accountant = self.identity.register_user("accountant@meridian.test", "password-123456")
        self.identity.add_membership(self.org.id, accountant.id, Role.ACCOUNTANT, actor_user_id=self.owner.id)
        # Accountants can create journals but not post them (maker-checker).
        with self.assertRaises(PermissionDeniedError):
            self.identity.require_permission(accountant.id, self.org.id, JOURNAL_POST)

    def test_tenant_isolation_role_does_not_carry_across_organisations(self):
        other_org = self.identity.create_organisation("Other Org", actor=self.owner.id)
        # dara is OWNER of self.org but has no membership at all in other_org.
        self.assertIsNone(self.identity.get_role(self.owner.id, other_org.id))
        with self.assertRaises(PermissionDeniedError):
            self.identity.require_permission(self.owner.id, other_org.id, ORG_MANAGE_USERS)

    # ------------------------------------------------------------------
    def test_every_material_action_is_audit_logged(self):
        accountant = self.identity.register_user("audit-check@meridian.test", "password-123456")
        self.identity.add_membership(self.org.id, accountant.id, Role.ACCOUNTANT, actor_user_id=self.owner.id)
        self.identity.revoke_membership(self.org.id, accountant.id, actor_user_id=self.owner.id)

        events = self.identity.audit.list_for_org(self.org.id)
        actions = [e.action for e in events]
        self.assertIn("ORGANISATION_CREATED", actions)
        self.assertIn("MEMBERSHIP_CREATED", actions)
        self.assertIn("MEMBERSHIP_REVOKED", actions)
        self.assertTrue(all(e.actor for e in events))


if __name__ == "__main__":
    unittest.main()
