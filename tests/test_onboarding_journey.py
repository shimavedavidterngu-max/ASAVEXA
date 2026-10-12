"""
The sign-up-to-dashboard journey, checked against the real identity service and the real permission tables.

What these tests pin down:
  - a person who registers and creates an organisation becomes its Owner, and only of that organisation;
  - nothing they do can reach another organisation (tenant isolation);
  - a person cannot add or promote themselves, and joining happens only when someone holding the permission adds them;
  - the permissions the set-up page relies on (organisation settings, accounting periods, managing users) are held by the
    right roles and not by the others, so hiding a button is never the only protection;
  - the front end's copy of the role table agrees with the server's for those permissions.
"""
import re
import unittest
from pathlib import Path

from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.errors import PermissionDeniedError
from asavexa.identity.domain.permissions import (
    ORG_MANAGE_SETTINGS, ORG_MANAGE_USERS, PERIOD_MANAGE, ROLE_PERMISSIONS,
)

from test_identity_service import build_service

PW = "correct horse battery staple1"


class OnboardingJourneyTests(unittest.TestCase):
    def setUp(self):
        self.svc = build_service()

    def _new_person(self, email):
        return self.svc.register_user(email, PW)

    def test_creator_becomes_owner_of_only_their_own_organisation(self):
        a, b = self._new_person("a@x.test"), self._new_person("b@x.test")
        org_a = self.svc.create_organisation("A Ltd", actor=a.id)
        self.svc.add_membership(org_a.id, a.id, Role.OWNER, actor_user_id=a.id)
        org_b = self.svc.create_organisation("B Ltd", actor=b.id)
        self.svc.add_membership(org_b.id, b.id, Role.OWNER, actor_user_id=b.id)
        self.assertEqual(self.svc.get_role(a.id, org_a.id), Role.OWNER)
        self.assertIsNone(self.svc.get_role(a.id, org_b.id), "no role at all in someone else's organisation")
        self.assertIsNone(self.svc.get_role(b.id, org_a.id))

    def test_a_person_cannot_open_an_organisation_they_do_not_belong_to(self):
        a, b = self._new_person("a2@x.test"), self._new_person("b2@x.test")
        org_a = self.svc.create_organisation("A Ltd", actor=a.id)
        self.svc.add_membership(org_a.id, a.id, Role.OWNER, actor_user_id=a.id)
        _, token = self.svc.authenticate("b2@x.test", PW)
        with self.assertRaises(PermissionDeniedError):
            self.svc.select_organisation(token, org_a.id)

    def test_nobody_can_add_themselves_to_an_existing_organisation(self):
        a, b = self._new_person("a3@x.test"), self._new_person("b3@x.test")
        org = self.svc.create_organisation("A Ltd", actor=a.id)
        self.svc.add_membership(org.id, a.id, Role.OWNER, actor_user_id=a.id)
        with self.assertRaises(PermissionDeniedError):
            self.svc.add_membership(org.id, b.id, Role.ADMINISTRATOR, actor_user_id=b.id)
        self.assertIsNone(self.svc.get_role(b.id, org.id))

    def test_joining_gives_exactly_the_role_the_administrator_chose(self):
        a, b = self._new_person("a4@x.test"), self._new_person("b4@x.test")
        org = self.svc.create_organisation("A Ltd", actor=a.id)
        self.svc.add_membership(org.id, a.id, Role.OWNER, actor_user_id=a.id)
        self.svc.add_membership(org.id, b.id, Role.READ_ONLY, actor_user_id=a.id)
        self.assertEqual(self.svc.get_role(b.id, org.id), Role.READ_ONLY)
        c = self._new_person("c4@x.test")
        with self.assertRaises(PermissionDeniedError):
            self.svc.add_membership(org.id, c.id, Role.READ_ONLY, actor_user_id=b.id)
        self.assertIsNone(self.svc.get_role(c.id, org.id), "a read-only member cannot bring anyone in")

    def test_set_up_permissions_belong_to_the_right_roles(self):
        owner = ROLE_PERMISSIONS[Role.OWNER]
        for perm in (ORG_MANAGE_SETTINGS, PERIOD_MANAGE, ORG_MANAGE_USERS):
            self.assertIn(perm, owner)
        for role in (Role.READ_ONLY, Role.DONOR, Role.REGULATOR, Role.INVESTOR_REVIEWER, Role.EXTERNAL_AUDITOR, Role.AUDITOR):
            for perm in (ORG_MANAGE_SETTINGS, PERIOD_MANAGE, ORG_MANAGE_USERS):
                self.assertNotIn(perm, ROLE_PERMISSIONS[role], f"{role.value} must not hold {perm}")

    def test_the_front_end_role_table_agrees_with_the_server_for_the_set_up_permissions(self):
        js = (Path(__file__).resolve().parent.parent / "frontend" / "src" / "lib" / "permissions.js").read_text()
        for role in Role:
            m = re.search(rf"^\s*{role.name}: \[(.*?)\],?\s*$", js, re.S | re.M)
            if not m:
                continue
            front = m.group(1)
            for const, perm in (("ORG_MANAGE_SETTINGS", ORG_MANAGE_SETTINGS), ("PERIOD_MANAGE", PERIOD_MANAGE), ("ORG_MANAGE_USERS", ORG_MANAGE_USERS)):
                self.assertEqual(f"PERMISSIONS.{const}" in front, perm in ROLE_PERMISSIONS[role],
                                 f"{role.value}: front end and server disagree about {perm}")


if __name__ == "__main__":
    unittest.main()
