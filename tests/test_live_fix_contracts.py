"""Static contract tests for the live-app fixes (no fastapi needed):
error handlers, CORS, organisation profile, journal listing."""
import ast
import os
import re
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
MAIN = os.path.join(ROOT, "src", "asavexa", "api", "main.py")
ROUTERS = os.path.join(ROOT, "src", "asavexa", "api", "routers")


def _read(path):
    with open(path) as f:
        return f.read()


class ErrorHandlingContractTestCase(unittest.TestCase):
    def test_database_errors_have_dedicated_handlers(self):
        src = _read(MAIN)
        self.assertIn("@app.exception_handler(DataError)", src)
        self.assertIn("@app.exception_handler(IntegrityError)", src)

    def test_catch_all_500_includes_cors_headers(self):
        src = _read(MAIN)
        block = src[src.index("async def handle_unexpected_error"):src.index('@app.get("/health")')]
        self.assertIn("_cors_headers_for(request)", block)

    def test_cors_allows_put(self):
        self.assertRegex(_read(MAIN), r'allow_methods=\[[^\]]*"PUT"')

    def test_fastapi_is_pinned_below_the_release_that_defers_session_commit(self):
        req = _read(os.path.join(ROOT, "requirements.txt"))
        self.assertRegex(req, r"fastapi>=0\.110,<0\.118")


class OrganisationProfileContractTestCase(unittest.TestCase):
    def test_update_requires_manage_settings_and_read_requires_only_membership(self):
        src = _read(os.path.join(ROUTERS, "organisation_profile.py"))
        tree = ast.parse(src)
        funcs = {n.name: ast.unparse(n) for n in tree.body if isinstance(n, ast.FunctionDef)}
        self.assertIn("ORG_MANAGE_SETTINGS", "\n".join(ast.unparse(d) for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "update_profile" for d in n.decorator_list))
        self.assertNotIn("require_permission", "\n".join(ast.unparse(d) for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "get_profile" for d in n.decorator_list))
        self.assertIn("ORGANISATION_PROFILE_UPDATED", funcs["update_profile"])

    def test_profile_changes_are_audited_against_the_organisation_entity(self):
        src = _read(os.path.join(ROUTERS, "organisation_profile.py"))
        self.assertIn('entity_type="Organisation"', src)

    def test_table_is_created_at_startup_idempotently(self):
        self.assertIn("ensure_profile_table", _read(MAIN))
        models = _read(os.path.join(ROOT, "src", "asavexa", "api", "db", "profile_models.py"))
        self.assertIn("checkfirst=True", models)

    def test_framework_options_are_not_tied_to_one_country(self):
        src = _read(os.path.join(ROOT, "src", "asavexa", "api", "schemas", "organisation_profile.py"))
        for fw in ("IFRS", "US_GAAP", "IPSAS", "LOCAL_GAAP", "OTHER"):
            self.assertIn(f'"{fw}"', src)


class JournalListingContractTestCase(unittest.TestCase):
    def test_list_endpoint_exists_and_needs_ledger_read(self):
        src = _read(os.path.join(ROUTERS, "journals.py"))
        tree = ast.parse(src)
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "list_journals")
        decorators = " ".join(ast.unparse(d) for d in fn.decorator_list)
        self.assertIn("LEDGER_READ", decorators)
        self.assertRegex(decorators, r"router\.get\(''")


if __name__ == "__main__":
    unittest.main()
