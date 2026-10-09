"""Static contracts for the pieces that cannot be imported without SQLAlchemy/FastAPI, plus the SQLite audit-id rule."""
import ast
import os
import re
import unittest
import uuid
from datetime import datetime, timezone

SRC = os.path.join(os.path.dirname(__file__), "..", "src", "asavexa")


def methods(path, cls):
    tree = ast.parse(open(os.path.join(SRC, path)).read())
    for n in tree.body:
        if isinstance(n, ast.ClassDef) and n.name == cls:
            return {f.name: [a.arg for a in f.args.args] for f in n.body if isinstance(f, ast.FunctionDef) and not f.name.startswith("_")}
    raise AssertionError(f"{cls} not found")


class DocStoreParity(unittest.TestCase):
    def test_all_three_stores_have_the_same_methods_and_parameters(self):
        mem = methods("security/store.py", "MemoryDocStore")
        sql = methods("security/store.py", "SqliteDocStore")
        pg = methods("api/db/security_store.py", "SqlAlchemyDocStore")
        for name in ("put", "get", "delete", "list"):
            self.assertEqual(mem[name], sql[name], name)
            self.assertEqual(mem[name], pg[name], name)

    def test_postgres_store_flushes_new_rows(self):
        self.assertIn("self.session.flush()", open(os.path.join(SRC, "api/db/security_store.py")).read())


class EverythingSecurityIsRegistered(unittest.TestCase):
    def test_startup_creates_the_security_table_and_headers_are_applied(self):
        main = open(os.path.join(SRC, "api/main.py")).read()
        self.assertIn("ensure_security_tables", main)
        self.assertIn("SECURITY_HEADERS", main)
        self.assertIn("handle_security_error", main)
        self.assertNotIn('f"database unreachable: {exc}"', main)       # /ready must not leak exception text

    def test_every_org_route_in_the_security_router_is_permission_guarded(self):
        src = open(os.path.join(SRC, "api/routers/security.py")).read()
        for m in re.finditer(r'@router\.(get|post|put|delete)\("([^"]+)"([^\n]*)\n', src):
            path, rest = m.group(2), m.group(3)
            if path.startswith("/me"):
                continue
            self.assertTrue("dependencies=" in rest, f"{path} has no permission dependency")

    def test_auth_routes_are_rate_limited(self):
        src = open(os.path.join(SRC, "api/routers/auth.py")).read()
        for fn in ("def login", "def mfa_verify", "def oidc_start", "def oidc_callback"):
            body = src[src.index(fn):]
            self.assertIn("ratelimit.throttle", body[:400], fn)


class SqliteAuditIds(unittest.TestCase):
    def test_non_uuid_entity_ids_are_stored_as_stable_uuids(self):
        from asavexa.audit.entity_ids import db_entity_id
        a = db_entity_id("someone@example.com")
        self.assertEqual(a, db_entity_id("someone@example.com"))
        uuid.UUID(a)
        real = str(uuid.uuid4())
        self.assertEqual(db_entity_id(real), real)


if __name__ == "__main__":
    unittest.main()
