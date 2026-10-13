"""Stage 1, static route-security audit over EVERY route in api/routers (read with `ast`, so it needs no FastAPI and no database).

What it proves, for all routes at once:
  1. The set of routes that need no sign-in is exactly the reviewed list below. A new unprotected route fails the build.
  2. Every other route depends on a session (get_current_session / actor / org / require_permission).
  3. No route takes the organisation from the client (path, query, form or request body): it always comes from the session.
  4. Every authenticated write has a permission check, or is on a reviewed list with the reason.
  5. Every by-id route knows the caller's organisation (so it can scope the lookup).
What it does NOT prove: that each service query filters by organisation. That is the job of the two-tenant HTTP test in
tests/stack/ (needs the real FastAPI + PostgreSQL stack; it runs in CI)."""
import ast
import os
import re
import unittest

import route_inventory as ri

SCHEMAS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "asavexa", "api", "schemas")

# Reviewed 2026-10-12. Each of these is public on purpose; the reason says what protects it instead.
PUBLIC = {
    "GET /auth/password-policy": "static password rules",
    "POST /auth/register": "creating an account; rate limited, generic errors",
    "POST /auth/verification/status": None,
    "GET /auth/verification/status": "is email delivery configured (no user data)",
    "POST /auth/verification/request": "needs email + password; rate limited; generic answer",
    "POST /auth/verification/confirm": "needs email + password + code; attempt limited",
    "GET /auth/recovery/status": "is recovery available (no user data)",
    "POST /auth/recovery/request": "generic answer; rate limited; code hashed",
    "POST /auth/recovery/verify": "code, attempt limited",
    "POST /auth/recovery/reset": "recovery code + password policy",
    "POST /auth/login": "credentials; lockout; rate limited",
    "POST /auth/mfa/verify": "holds the half-signed-in challenge token",
    "GET /auth/oidc/config": "is single sign-on enabled",
    "POST /auth/oidc/start": "starts the OIDC redirect",
    "POST /auth/oidc/callback": "validates state and ID token",
    "POST /auth/logout": "bearer token read directly; ends that session",
    "POST /auth/select-organisation": "bearer token read directly; membership checked",
    "GET /network/guide": "static explanatory text",
    "POST /shared-passport/verify": "unguessable share secret + one-time code; attempt limited",
    "GET /shared-passport/view": "share-session token (hash stored); expires; revocable",
    "GET /shared-passport/download": "share-session token; only if the owner allowed download",
    "POST /webhooks/email": "Svix signature + timestamp tolerance + replay protection",
    "GET /health": "liveness probe: static answer",
    "GET /ready": "readiness probe: answers only ready / not ready, no detail",
    "GET /metrics-lite": "counters only since start: no paths, people or data",
}
PUBLIC.pop("POST /auth/verification/status")

# Authenticated writes without require_permission, each reviewed.
NO_PERMISSION_WRITES = {
    "POST /ingestion/preview": "inline _need(): purpose-specific permission",
    "POST /ingestion/commit": "inline _need(): purpose-specific permission",
    "POST /pilot/pilots/{pid}/leave": "inline _has(ORG_MANAGE_SETTINGS) and firm check",
    "POST /security/me/mfa/begin": "the caller's own account",
    "POST /security/me/mfa/confirm": "the caller's own account",
    "POST /security/me/mfa/disable": "the caller's own account (re-authenticates)",
    "POST /security/me/mfa/recovery-codes": "the caller's own account",
    "DELETE /security/me/sessions/{session_id}": "own sessions only: lookup is keyed by user id",
    "POST /security/me/sessions/revoke-others": "the caller's own sessions",
    "POST /security/me/erasure-request": "the caller's own data request",
    "POST /standards/resolve": "stateless preview, writes nothing",
    "POST /organisations": "any signed-in person may create their own new organisation and becomes its owner",
    "POST /organisations/{org_id}/members": "permission enforced inside IdentityService.add_membership",
    "PATCH /organisations/{org_id}/members/{user_id}/role": "permission enforced inside IdentityService.change_role",
    "DELETE /organisations/{org_id}/members/{user_id}": "permission enforced inside IdentityService.revoke_membership",
}
# The only routes that take an organisation id from the client. Each is for managing membership, and each is authorised
# against the CALLER'S role in THAT organisation inside IdentityService (tests: tests/test_stage1_tenant_isolation.py).
ORG_IN_PATH = {
    "GET /organisations/{org_id}/members": "handler refuses unless the caller has a role in that organisation",
    "POST /organisations/{org_id}/members": "IdentityService.add_membership requires ORG_MANAGE_USERS in that organisation",
    "PATCH /organisations/{org_id}/members/{user_id}/role": "IdentityService.change_role requires ORG_MANAGE_USERS in that organisation",
    "DELETE /organisations/{org_id}/members/{user_id}": "IdentityService.revoke_membership requires ORG_MANAGE_USERS in that organisation",
}
# Authenticated routes that deliberately have no organisation (they are about the person, not an organisation).
PERSONAL = {
    "POST /organisations", "GET /organisations/mine",
    "GET /auth/email-status", "GET /auth/me", "GET /security/me", "POST /security/me/mfa/begin", "POST /security/me/mfa/confirm",
    "POST /security/me/mfa/disable", "POST /security/me/mfa/recovery-codes", "DELETE /security/me/sessions/{session_id}",
    "POST /security/me/sessions/revoke-others", "GET /security/me/export", "POST /security/me/erasure-request",
}

ROWS = ri.inventory()


class RouteInventory(unittest.TestCase):
    def test_the_scan_sees_the_whole_api(self):
        self.assertGreaterEqual(len(ROWS), 500)
        self.assertEqual(len({ri.key(r) for r in ROWS}), len(ROWS), "duplicate method+path")
        self.assertTrue(all("<expr>" not in r["path"] for r in ROWS), "a route path the scanner could not read")

    def test_only_the_reviewed_routes_are_public(self):
        public = {ri.key(r) for r in ROWS if not ri.is_session_authenticated(r)}
        self.assertEqual(public - set(PUBLIC), set(), "NEW UNPROTECTED ROUTE: add authentication, or review it and list it with a reason")
        self.assertEqual(set(PUBLIC) - public, set(), "listed as public but is now protected or gone: update the list")

    def test_every_public_route_has_a_stated_reason(self):
        self.assertTrue(all(v for v in PUBLIC.values()))

    def test_no_route_takes_the_organisation_from_the_client(self):
        bad = []
        for r in ROWS:
            if ri.key(r) in ORG_IN_PATH:
                continue
            for name, deps in r["params"].items():
                if name in ("org_id", "organisation_id", "tenant_id") and "get_current_org" not in deps:
                    bad.append(f'{ri.key(r)} parameter {name}')
            if re.search(r"\{(org|organisation|tenant)\w*\}", r["path"]):
                bad.append(f'{ri.key(r)} path')
        self.assertEqual(bad, [])
        self.assertEqual({ri.key(r) for r in ROWS if "{org_id}" in r["path"]}, set(ORG_IN_PATH), "the list of client-named-organisation routes changed")

    def test_no_request_body_model_carries_an_organisation_id(self):
        with_org = set()
        for fn in os.listdir(SCHEMAS):
            if fn.endswith(".py"):
                for node in ast.parse(open(os.path.join(SCHEMAS, fn)).read()).body:
                    if isinstance(node, ast.ClassDef):
                        for st in node.body:
                            if isinstance(st, ast.AnnAssign) and getattr(st.target, "id", "") in ("org_id", "organisation_id", "tenant_id"):
                                with_org.add(node.name)
        used_as_input = []
        for r in ROWS:
            for a in r["node"].args.args + r["node"].args.kwonlyargs:
                names = {n.id for n in ast.walk(a.annotation) if isinstance(n, ast.Name)} if a.annotation is not None else set()
                if names & with_org:
                    used_as_input.append(f'{ri.key(r)} takes {sorted(names & with_org)}')
        used_as_input = [u for u in used_as_input if not u.startswith("POST /auth/select-organisation ")]   # reviewed: membership is verified by the identity service
        self.assertEqual(used_as_input, [], "a request body that lets the client name its organisation")

    def test_every_session_route_is_either_organisation_scoped_or_personal(self):
        loose = [ri.key(r) for r in ROWS if ri.is_session_authenticated(r) and "get_current_org" not in r["deps"]
                 and not any(x.startswith("require_") for x in r["deps"]) and ri.key(r) not in PERSONAL
                 and ri.key(r) not in ORG_IN_PATH]
        self.assertEqual(loose, [])

    def test_personal_routes_do_not_touch_an_organisation(self):
        for r in ROWS:
            if ri.key(r) in PERSONAL:
                self.assertNotIn("get_current_org", r["deps"], ri.key(r))
                if not r["path"].startswith("/organisations"):
                    self.assertFalse(re.search(r"org", r["path"]), ri.key(r))

    def test_every_authenticated_write_has_a_permission_check_or_a_reviewed_reason(self):
        no_perm = {ri.key(r) for r in ROWS if r["method"] != "GET" and ri.is_session_authenticated(r)
                   and not any(x.startswith("require_") for x in r["deps"])}
        self.assertEqual(no_perm - set(NO_PERMISSION_WRITES), set(), "write route with no permission check and no reviewed reason")
        self.assertEqual(set(NO_PERMISSION_WRITES) - no_perm, set(), "reviewed-exception list is stale")

    def test_inline_permission_checks_really_are_in_the_handlers(self):
        src = {ri.key(r): ast.unparse(r["node"]) for r in ROWS}
        self.assertIn("_need(identity, actor, org_id, purpose)", src["POST /ingestion/preview"])
        self.assertIn("_need(identity, actor, org_id, purpose)", src["POST /ingestion/commit"])
        self.assertIn("_has(identity, actor, org, ORG_MANAGE_SETTINGS)", src["POST /pilot/pilots/{pid}/leave"])

    def test_session_revoke_is_keyed_by_the_callers_own_user_id(self):
        src = ast.unparse(next(r["node"] for r in ROWS if ri.key(r) == "DELETE /security/me/sessions/{session_id}"))
        self.assertIn("security.guard.revoke(session.user_id, session_id)", src)

    def test_membership_routes_pass_the_caller_to_the_identity_service(self):
        src = {ri.key(r): ast.unparse(r["node"]) for r in ROWS}
        self.assertIn("identity.get_role(actor, org_id) is None", src["GET /organisations/{org_id}/members"])
        for k in ("POST /organisations/{org_id}/members", "PATCH /organisations/{org_id}/members/{user_id}/role", "DELETE /organisations/{org_id}/members/{user_id}"):
            self.assertIn("actor_user_id=actor", src[k], k)

    def test_every_by_id_route_has_the_callers_organisation(self):
        missing = [ri.key(r) for r in ROWS if re.search(r"\{\w+\}", r["path"]) and ri.is_session_authenticated(r)
                   and "get_current_org" not in r["deps"] and not any(x.startswith("require_") for x in r["deps"]) and ri.key(r) not in PERSONAL
                   and ri.key(r) not in ORG_IN_PATH]
        self.assertEqual(missing, [])

    def test_write_routes_do_not_exist_on_get(self):
        words = re.compile(r"/(create|delete|remove|approve|post|reverse|revoke|submit|commit|reset|close|lock|resolve-finding)\b")
        bad = [ri.key(r) for r in ROWS if r["method"] == "GET" and words.search(r["path"])]
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
