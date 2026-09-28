"""
Focused regression tests for the `finding:manage` permission gap fix.

These tests exist to prove — with real Role enum members and a real
IdentityService, not assertions about intent — that:

    1. finding:manage exists in the canonical permission registry.
    2. An authorized role can actually perform a finding-management
       operation (via require_permission, the same call the API layer
       makes).
    3. An unauthorized role is denied with the project's real
       PermissionDeniedError.
    4. Holding finding:verify does NOT implicitly grant finding:manage
       (APPROVER is the real counter-example: verifier, not manager).
    5. Holding finding:remediate does NOT implicitly grant
       finding:manage (ACCOUNTANT is the real counter-example: maker,
       not manager).
    6. control:read / control:manage / control:execute continue to
       behave exactly as they did before this change (regression
       coverage, not just the new permission in isolation).

Run with:  PYTHONPATH=src python3 -m unittest tests.test_compliance_permissions -v
"""
import unittest

from asavexa.audit.sqlite_repository import SqliteAuditRepository
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.errors import PermissionDeniedError
from asavexa.identity.domain.permissions import (
    ALL_PERMISSIONS,
    CONTROL_EXECUTE,
    CONTROL_MANAGE,
    CONTROL_READ,
    FINDING_MANAGE,
    FINDING_REMEDIATE,
    FINDING_VERIFY,
    ROLE_PERMISSIONS,
    role_has_permission,
)
from asavexa.identity.repository.sqlite_repository import (
    SqliteMembershipRepository,
    SqliteOrganisationRepository,
    SqliteSessionRepository,
    SqliteUserRepository,
    connect,
)
from asavexa.identity.services.service import IdentityService


class FindingManagePermissionRegistryTestCase(unittest.TestCase):
    """Pure data/registry checks — no Identity service needed."""

    def test_finding_manage_exists_as_distinct_canonical_permission(self):
        self.assertEqual(FINDING_MANAGE, "finding:manage")
        self.assertIn(FINDING_MANAGE, ALL_PERMISSIONS)
        # Distinct string identity from every neighbouring permission —
        # no accidental aliasing.
        self.assertNotEqual(FINDING_MANAGE, FINDING_REMEDIATE)
        self.assertNotEqual(FINDING_MANAGE, FINDING_VERIFY)
        self.assertNotEqual(FINDING_MANAGE, CONTROL_EXECUTE)
        self.assertNotEqual(FINDING_MANAGE, CONTROL_READ)
        self.assertNotEqual(FINDING_MANAGE, CONTROL_MANAGE)

    def test_no_duplicate_permission_identifiers_in_registry(self):
        """Every permission string used anywhere in ROLE_PERMISSIONS is
        unique — confirms finding:manage wasn't added as a second name
        for an existing permission, and nothing else collides with it."""
        all_seen = set()
        for role, perms in ROLE_PERMISSIONS.items():
            for p in perms:
                all_seen.add(p)
        # ALL_PERMISSIONS is itself a set/frozenset, so this mainly
        # confirms every granted permission is a known, canonical one —
        # an unrecognised or duplicate-but-differently-spelled
        # permission string would fail role_has_permission's own
        # membership check.
        self.assertTrue(all_seen.issubset(ALL_PERMISSIONS))
        self.assertIn(FINDING_MANAGE, all_seen)

    def test_finding_manage_role_grants_are_explicit_not_inferred(self):
        """role_has_permission is a flat frozenset membership test with
        no cross-permission implication logic — proven by checking that
        for every role, whether it has finding:manage is exactly the
        recorded ROLE_PERMISSIONS data, regardless of what other
        finding:* permissions that role also holds."""
        for role, perms in ROLE_PERMISSIONS.items():
            expected = FINDING_MANAGE in perms
            self.assertEqual(role_has_permission(role, FINDING_MANAGE), expected)

    def test_at_least_one_role_has_remediate_without_manage(self):
        """Real counter-example required for the independence claim to
        be non-vacuous — not just asserted, actually present in the
        matrix."""
        roles = {r for r, p in ROLE_PERMISSIONS.items() if FINDING_REMEDIATE in p and FINDING_MANAGE not in p}
        self.assertIn(Role.ACCOUNTANT, roles)

    def test_at_least_one_role_has_verify_without_manage(self):
        """Same, for finding:verify — this is the counter-example that
        did not previously exist and was the actual gap: every role
        with finding:verify also had finding:manage, so the
        independence claim was untested and untestable."""
        roles = {r for r, p in ROLE_PERMISSIONS.items() if FINDING_VERIFY in p and FINDING_MANAGE not in p}
        self.assertIn(Role.APPROVER, roles)

    def test_control_permissions_regression_unaffected(self):
        """The three control:* permissions must retain exactly the role
        sets they had before this change — proves the fix was additive/
        corrective to finding:manage's grants only, not a side effect
        on unrelated permissions."""
        expected_control_read = {
            Role.OWNER, Role.ADMINISTRATOR, Role.ACCOUNTANT, Role.FINANCE_OFFICER, Role.APPROVER,
            Role.REVIEWER, Role.MANAGER, Role.AUDITOR, Role.EXTERNAL_AUDITOR, Role.READ_ONLY,
        }
        actual_control_read = {r for r, p in ROLE_PERMISSIONS.items() if CONTROL_READ in p}
        self.assertEqual(actual_control_read, expected_control_read)

        expected_control_manage = {Role.OWNER, Role.ADMINISTRATOR, Role.FINANCE_OFFICER}
        actual_control_manage = {r for r, p in ROLE_PERMISSIONS.items() if CONTROL_MANAGE in p}
        self.assertEqual(actual_control_manage, expected_control_manage)

        expected_control_execute = {Role.OWNER, Role.ACCOUNTANT, Role.FINANCE_OFFICER, Role.APPROVER}
        actual_control_execute = {r for r, p in ROLE_PERMISSIONS.items() if CONTROL_EXECUTE in p}
        self.assertEqual(actual_control_execute, expected_control_execute)


class FindingManageEnforcementTestCase(unittest.TestCase):
    """End-to-end through a real IdentityService: real users, a real
    organisation, real memberships — proving enforcement, not just
    registry shape."""

    def setUp(self):
        self.conn = connect(":memory:")
        audit = SqliteAuditRepository(self.conn)
        # identity's own connect() doesn't create the audit table;
        # reuse the same pattern every identity test file already uses.
        from asavexa.audit.sqlite_repository import ensure_schema as ensure_audit_schema
        ensure_audit_schema(self.conn)

        self.identity = IdentityService(
            organisations=SqliteOrganisationRepository(self.conn),
            users=SqliteUserRepository(self.conn),
            memberships=SqliteMembershipRepository(self.conn),
            sessions=SqliteSessionRepository(self.conn),
            audit=audit,
        )
        self.owner = self.identity.register_user("dara@meridian.test", "correct horse battery staple")
        self.org = self.identity.create_organisation("Meridian Textiles Ltd", actor=self.owner.id)
        self.identity.add_membership(self.org.id, self.owner.id, Role.OWNER, actor_user_id=self.owner.id)

        self.administrator = self.identity.register_user("priya@meridian.test", "another-strong-password")
        self.identity.add_membership(self.org.id, self.administrator.id, Role.ADMINISTRATOR, actor_user_id=self.owner.id)

        self.accountant = self.identity.register_user("aisha@meridian.test", "yet-another-password")
        self.identity.add_membership(self.org.id, self.accountant.id, Role.ACCOUNTANT, actor_user_id=self.owner.id)

        self.approver = self.identity.register_user("kwame@meridian.test", "still-another-password")
        self.identity.add_membership(self.org.id, self.approver.id, Role.APPROVER, actor_user_id=self.owner.id)

    def test_authorized_role_can_perform_finding_management_operation(self):
        """ADMINISTRATOR holds finding:manage — the identical check the
        compliance router runs before calling
        ComplianceService.start_review/mark_remediation_required/etc.
        must succeed, not raise."""
        role = self.identity.require_permission(self.administrator.id, self.org.id, FINDING_MANAGE)
        self.assertEqual(role, Role.ADMINISTRATOR)

    def test_role_without_finding_manage_is_denied(self):
        """ACCOUNTANT lacks finding:manage entirely."""
        with self.assertRaises(PermissionDeniedError):
            self.identity.require_permission(self.accountant.id, self.org.id, FINDING_MANAGE)

    def test_finding_verify_does_not_implicitly_grant_finding_manage(self):
        """The actual gap this fix closes: APPROVER holds finding:verify
        and must still be refused finding:manage — proven by a real
        PermissionDeniedError, not by reading the matrix."""
        # Confirms the positive grant works (verify is real)...
        self.identity.require_permission(self.approver.id, self.org.id, FINDING_VERIFY)
        # ...and confirms it does not spill over into manage.
        with self.assertRaises(PermissionDeniedError):
            self.identity.require_permission(self.approver.id, self.org.id, FINDING_MANAGE)

    def test_remediation_does_not_implicitly_grant_finding_manage(self):
        """ACCOUNTANT holds finding:remediate and must still be refused
        finding:manage."""
        self.identity.require_permission(self.accountant.id, self.org.id, FINDING_REMEDIATE)
        with self.assertRaises(PermissionDeniedError):
            self.identity.require_permission(self.accountant.id, self.org.id, FINDING_MANAGE)

    def test_finding_manage_does_not_implicitly_grant_verify_or_remediate(self):
        """The independence cuts both ways — ADMINISTRATOR holds
        finding:manage but neither finding:verify nor
        finding:remediate."""
        self.identity.require_permission(self.administrator.id, self.org.id, FINDING_MANAGE)
        with self.assertRaises(PermissionDeniedError):
            self.identity.require_permission(self.administrator.id, self.org.id, FINDING_VERIFY)
        with self.assertRaises(PermissionDeniedError):
            self.identity.require_permission(self.administrator.id, self.org.id, FINDING_REMEDIATE)

    def test_finance_officer_senior_role_still_holds_all_three(self):
        """Regression check: the one role designed to hold the full
        breadth (mirroring its role everywhere else in this codebase)
        must still hold all three — this fix must not have narrowed
        FINANCE_OFFICER by accident."""
        finance_officer = self.identity.register_user("kenji@meridian.test", "one-more-password")
        self.identity.add_membership(self.org.id, finance_officer.id, Role.FINANCE_OFFICER, actor_user_id=self.owner.id)
        for permission in (FINDING_MANAGE, FINDING_REMEDIATE, FINDING_VERIFY):
            self.identity.require_permission(finance_officer.id, self.org.id, permission)  # must not raise

    def test_owner_still_holds_finding_manage(self):
        """Regression check: OWNER's blanket ALL_PERMISSIONS grant is
        unaffected by this change."""
        self.identity.require_permission(self.owner.id, self.org.id, FINDING_MANAGE)

    def test_control_read_execute_manage_unaffected_by_this_change(self):
        """Regression: the pre-existing control:* permissions still
        work exactly as before for the roles that always had them."""
        self.identity.require_permission(self.accountant.id, self.org.id, CONTROL_READ)
        self.identity.require_permission(self.accountant.id, self.org.id, CONTROL_EXECUTE)
        with self.assertRaises(PermissionDeniedError):
            self.identity.require_permission(self.accountant.id, self.org.id, CONTROL_MANAGE)

        self.identity.require_permission(self.administrator.id, self.org.id, CONTROL_MANAGE)
        with self.assertRaises(PermissionDeniedError):
            self.identity.require_permission(self.administrator.id, self.org.id, CONTROL_EXECUTE)

    def test_tenant_isolation_still_holds_for_finding_manage(self):
        """A role in one organisation confers no finding:manage
        authority in another — unchanged by this fix, reconfirmed here."""
        other_owner = self.identity.register_user("priya2@other.test", "unrelated-password")
        other_org = self.identity.create_organisation("Other Org Ltd", actor=other_owner.id)
        self.identity.add_membership(other_org.id, other_owner.id, Role.OWNER, actor_user_id=other_owner.id)

        # administrator has finding:manage in self.org, but no
        # membership at all in other_org.
        with self.assertRaises(PermissionDeniedError):
            self.identity.require_permission(self.administrator.id, other_org.id, FINDING_MANAGE)


if __name__ == "__main__":
    unittest.main()
