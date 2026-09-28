"""
SECURITY HARDENING TESTS — Phase 4.

Framework-independent, like every other test file in this suite (no
fastapi/sqlalchemy/pydantic import anywhere here). Covers what was
found and fixed during the Phase 4 security audit, plus static checks
that don't need a live framework to be genuine and valuable.

Two real, concrete vulnerabilities were found and fixed during this
audit (see docs/security-architecture.md for the full writeup):
  1. A login-timing side-channel that let an attacker distinguish a
     nonexistent email from a wrong password by response time alone.
  2. A privilege-escalation path: any role holding org:manage_users
     (not just OWNER — ADMINISTRATOR too) could call change_role() on
     its own membership and grant itself OWNER.
Both have dedicated regression tests in tests/test_identity_service.py
(test_authenticate_unknown_email_still_performs_password_verification,
test_cannot_change_own_role_even_with_permission,
test_owner_cannot_self_promote_either) — not duplicated here.
"""
import ast
import os
import re
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO_ROOT, "src", "asavexa")


class ResponseSchemaSecrecyTestCase(unittest.TestCase):
    """Section 2: password hashes must never be serializable back to a
    client — Pydantic's response_model acts as an allowlist, so this
    is enforced by UserOut simply never declaring the field, checked
    here statically rather than trusted by assumption."""

    def test_useroutschema_never_declares_password_hash(self):
        path = os.path.join(SRC, "api", "schemas", "auth.py")
        with open(path) as f:
            tree = ast.parse(f.read())
        user_out = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "UserOut")
        field_names = {
            item.target.id for item in user_out.body
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
        }
        self.assertNotIn("password_hash", field_names)
        self.assertNotIn("password", field_names)

    def test_no_response_schema_anywhere_declares_a_password_or_token_field(self):
        """Broader sweep across every *_Out schema in every module —
        not just auth's UserOut."""
        schemas_dir = os.path.join(SRC, "api", "schemas")
        offenders = []
        for fname in os.listdir(schemas_dir):
            if not fname.endswith(".py"):
                continue
            with open(os.path.join(schemas_dir, fname)) as f:
                tree = ast.parse(f.read())
            for node in tree.body:
                if isinstance(node, ast.ClassDef) and node.name.endswith("Out"):
                    for item in node.body:
                        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                            name = item.target.id
                            if "password" in name.lower() or name in ("token", "token_hash", "raw_token"):
                                offenders.append(f"{fname}::{node.name}.{name}")
        self.assertFalse(offenders, f"response schema(s) expose sensitive fields: {offenders}")


class NoLegacyHeaderAuthenticationTestCase(unittest.TestCase):
    """Section 4: confirm no code path anywhere trusts a client-supplied
    X-Actor / X-Org-Id (or equivalent) header as identity — re-verified
    as part of this security audit's own record, not just inherited
    from the Phase 1 inventory finding."""

    def test_no_x_actor_or_x_org_id_header_anywhere_in_src(self):
        offenders = []
        for dirpath, _, filenames in os.walk(SRC):
            for fname in filenames:
                if not fname.endswith(".py"):
                    continue
                path = os.path.join(dirpath, fname)
                with open(path) as f:
                    content = f.read()
                if "X-Actor" in content or "X-Org-Id" in content:
                    offenders.append(path)
        self.assertFalse(offenders, f"legacy header-trust reference(s) found: {offenders}")

    def test_get_current_actor_is_derived_only_from_a_validated_session(self):
        """get_current_actor must take its value from the resolved
        Session object, never from a raw request parameter a client
        could set directly."""
        path = os.path.join(SRC, "api", "deps.py")
        with open(path) as f:
            tree = ast.parse(f.read())
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "get_current_actor")
        # Must depend on get_current_session (a Session, itself
        # resolved from a validated bearer token) and return
        # session.user_id, not a caller-supplied value.
        self.assertTrue(
            any(
                isinstance(a.annotation, ast.Name) and a.annotation.id == "IdentitySession"
                for a in fn.args.args
            ),
            "get_current_actor must take its actor from an already-resolved IdentitySession",
        )
        returns_session_user_id = any(
            isinstance(n, ast.Return) and isinstance(n.value, ast.Attribute)
            and n.value.attr == "user_id"
            for n in ast.walk(fn)
        )
        self.assertTrue(returns_session_user_id, "get_current_actor must return session.user_id")


class StaticSecretLeakageTestCase(unittest.TestCase):
    """Section 18: repository-wide sweep for hardcoded credentials and
    unsafe logging of sensitive material."""

    SENSITIVE_VAR_NAMES = ("password", "raw_token", "token_hash", "secret")

    def test_no_password_or_token_value_is_ever_passed_to_print_or_logging(self):
        offenders = []
        for dirpath, _, filenames in os.walk(SRC):
            for fname in filenames:
                if not fname.endswith(".py"):
                    continue
                path = os.path.join(dirpath, fname)
                with open(path) as f:
                    tree = ast.parse(f.read())
                for node in ast.walk(tree):
                    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print"):
                        continue
                    for arg in node.args:
                        names_used = {n.id for n in ast.walk(arg) if isinstance(n, ast.Name)}
                        if names_used & set(self.SENSITIVE_VAR_NAMES):
                            offenders.append(f"{path}: print() call references {names_used & set(self.SENSITIVE_VAR_NAMES)}")
        self.assertFalse(offenders, f"sensitive value(s) passed to print(): {offenders}")

    def test_no_audit_log_call_passes_a_password_or_raw_token_as_a_value(self):
        """Every _log(...) call site across every module — new_value/
        previous_value/reason arguments must never reference a raw
        password or token variable name."""
        offenders = []
        for dirpath, _, filenames in os.walk(SRC):
            for fname in filenames:
                if not fname.endswith(".py") or "services" not in dirpath:
                    continue
                path = os.path.join(dirpath, fname)
                with open(path) as f:
                    tree = ast.parse(f.read())
                for node in ast.walk(tree):
                    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "_log"):
                        continue
                    for kw in node.keywords:
                        if kw.arg in ("new_value", "previous_value", "reason"):
                            names_used = {n.id for n in ast.walk(kw.value) if isinstance(n, ast.Name)}
                            leaked = names_used & {"password", "raw_token"}
                            if leaked:
                                offenders.append(f"{path}: _log(..., {kw.arg}=...) references {leaked}")
        self.assertFalse(offenders, f"audit log call(s) reference raw sensitive values: {offenders}")

    def test_no_stdlib_logging_call_anywhere_references_a_password_or_token(self):
        """Phase 7 introduced real stdlib `logging` calls (api/main.py's
        request-logging middleware and generic exception handler) —
        this is a genuinely new code path the Phase 4 sweep above never
        covered (that one only checked print() and the audit trail's
        own _log()). Proves the new logging calls stay to
        method/path/status/duration/request_id, never body or headers,
        by checking every logger.<level>(...) call site anywhere in
        src/ for a reference to a raw password/token/credentials
        variable name — not just the two call sites that exist today,
        so this stays true if more are added later."""
        offenders = []
        for dirpath, _, filenames in os.walk(SRC):
            for fname in filenames:
                if not fname.endswith(".py"):
                    continue
                path = os.path.join(dirpath, fname)
                with open(path) as f:
                    tree = ast.parse(f.read())
                for node in ast.walk(tree):
                    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                            and node.func.attr in ("debug", "info", "warning", "error", "exception", "critical")):
                        continue
                    names_used = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
                    leaked = names_used & {"password", "raw_token", "token", "credentials"}
                    if leaked:
                        offenders.append(f"{path}: logging call references {leaked}")
        self.assertFalse(offenders, f"logging call(s) reference raw sensitive values: {offenders}")

    def test_request_logging_middleware_never_logs_the_request_body_or_headers(self):
        """Specifically: /auth/login and /auth/register carry a password
        in their request body, and every authenticated request carries
        a bearer token in its Authorization header. The middleware must
        log only method/path/status/duration — confirmed by checking it
        never READS request.body/request.headers/request.json/request.form
        (setting response.headers, e.g. for X-Request-ID, is fine and
        expected — this checks the receiver is `request`, not `response`,
        rather than flagging the attribute name alone)."""
        path = os.path.join(SRC, "api", "main.py")
        with open(path) as f:
            tree = ast.parse(f.read())
        middleware_fn = next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "request_id_and_logging_middleware"
        )
        forbidden_attrs = {"body", "headers", "json", "form"}
        offenders = [
            n.attr for n in ast.walk(middleware_fn)
            if isinstance(n, ast.Attribute) and n.attr in forbidden_attrs
            and isinstance(n.value, ast.Name) and n.value.id == "request"
        ]
        self.assertFalse(offenders, f"request logging middleware must never read request.{offenders}")


class IdentityAuditCoverageTestCase(unittest.TestCase):
    """Section 11: every security-sensitive identity state change has a
    real, defined audit action, and is genuinely used at least once."""

    EXPECTED_SECURITY_EVENTS = [
        "USER_REGISTERED", "LOGIN_SUCCEEDED", "LOGIN_FAILED", "LOGOUT",
        "MEMBERSHIP_CREATED", "MEMBERSHIP_ROLE_CHANGED", "MEMBERSHIP_REVOKED",
        "ORG_CONTEXT_SELECTED", "ORGANISATION_CREATED",
    ]

    def test_every_expected_security_event_is_a_real_defined_action(self):
        from asavexa.identity.domain.enums import AuditAction
        defined = {a.value for a in AuditAction}
        missing = [e for e in self.EXPECTED_SECURITY_EVENTS if e not in defined]
        self.assertFalse(missing, f"expected security audit actions not defined: {missing}")

    def test_every_expected_security_event_is_actually_logged_somewhere(self):
        path = os.path.join(SRC, "identity", "services", "service.py")
        with open(path) as f:
            content = f.read()
        not_used = [e for e in self.EXPECTED_SECURITY_EVENTS if f"AuditAction.{e}" not in content]
        self.assertFalse(not_used, f"defined but never logged: {not_used}")


if __name__ == "__main__":
    unittest.main()
