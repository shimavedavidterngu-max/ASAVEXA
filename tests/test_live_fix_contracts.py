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


class FrontendBackendContractTestCase(unittest.TestCase):
    def test_evidence_status_endpoint_returns_the_linked_evidence_id(self):
        schema = _read(os.path.join(ROOT, "src", "asavexa", "api", "schemas", "evidence.py"))
        self.assertIn("evidence_id: Optional[str] = None", schema)
        router = _read(os.path.join(ROUTERS, "evidence.py"))
        self.assertIn("evidence_id=record.id", router)

    def test_general_ledger_filter_uses_the_parameter_name_the_backend_reads(self):
        client = _read(os.path.join(ROOT, "frontend", "src", "api", "client.js"))
        reporting = _read(os.path.join(ROUTERS, "reporting.py"))
        self.assertIn("account_ids: Optional[List[str]] = Query", reporting)
        self.assertRegex(client, r"general-ledger\", \{ period_id: periodId, account_ids: accountId \}")

    def test_every_client_path_exists_on_the_backend(self):
        client = _read(os.path.join(ROOT, "frontend", "src", "api", "client.js"))
        paths = set(re.findall(r'this\.(?:get|post|put|patch|del|delete)\(\s*[`"](/[^`"?]*)', client))
        backend = ""
        for f in os.listdir(ROUTERS):
            if f.endswith(".py"):
                backend += _read(os.path.join(ROUTERS, f))
        prefixes = re.findall(r'prefix="(/[^"]*)"', backend)
        self.assertTrue(paths)
        for p in sorted(paths - {"/health", "/ready"}):
            root = "/" + p.strip("/").split("/")[0]
            self.assertTrue(any(root == pre or pre.startswith(root) for pre in prefixes), f"client calls {p} but no router has prefix {root}")


class StandardsRouterContractTestCase(unittest.TestCase):
    def test_saving_requires_manage_settings_and_is_audited(self):
        src = _read(os.path.join(ROUTERS, "standards.py"))
        tree = ast.parse(src)
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "save_configuration")
        self.assertIn("ORG_MANAGE_SETTINGS", " ".join(ast.unparse(d) for d in fn.decorator_list))
        self.assertIn("STANDARDS_CONFIGURATION_UPDATED", src)

    def test_standards_errors_map_to_http_400_and_table_is_created_at_startup(self):
        main = _read(MAIN)
        self.assertIn("@app.exception_handler(AsavexaStandardsError)", main)
        self.assertIn("ensure_standards_table", main)
        self.assertIn("checkfirst=True", _read(os.path.join(ROOT, "src", "asavexa", "api", "db", "standards_models.py")))

    def test_every_frontend_standards_call_has_a_matching_route(self):
        client = _read(os.path.join(ROOT, "frontend", "src", "api", "client.js"))
        src = _read(os.path.join(ROUTERS, "standards.py"))
        for route in ("/catalog", "/resolve", "/configuration"):
            self.assertIn(f'"{route}"', src)
            self.assertIn(f"/standards{route}", client)


class PassportContractTestCase(unittest.TestCase):
    def _router(self):
        return ast.parse(_read(os.path.join(ROUTERS, "passport.py")))

    def test_reading_requires_passport_manage_and_saving_requires_manage_settings(self):
        src = _read(os.path.join(ROUTERS, "passport.py"))
        tree = self._router()
        get = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "get_passport")
        put = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "save_structure")
        self.assertIn("PASSPORT_MANAGE", " ".join(ast.unparse(d) for d in get.decorator_list))
        self.assertIn("ORG_MANAGE_SETTINGS", " ".join(ast.unparse(d) for d in put.decorator_list))
        self.assertIn("ORGANISATION_STRUCTURE_UPDATED", src)
        self.assertIn("PASSPORT_GENERATED", src)

    def test_every_query_is_scoped_to_the_callers_organisation(self):
        # gather_inputs must pass org_id to every repository read; none may be unscoped.
        src = _read(os.path.join(ROUTERS, "passport.py"))
        body = src[src.index("def gather_inputs"):src.index("@router.get")]
        for call in ("list_for_org(org_id", "list_for_reconciliation(org_id", "list_for_period(org_id", "list_recent_for_org(\n        org_id"):
            self.assertIn(call, body, call)
        self.assertNotIn("list_for_actor", body)

    def test_the_passport_never_writes_financial_records(self):
        body = _read(os.path.join(ROOT, "src", "asavexa", "passport", "builder.py"))
        for forbidden in ("session", ".create(", ".update(", ".record(", "post_journal", "INSERT", "UPDATE "):
            self.assertNotIn(forbidden, body, f"builder must be pure and read-only: found {forbidden!r}")

    def test_structure_table_is_created_at_startup_and_outside_schema_sql(self):
        main = _read(MAIN)
        self.assertIn("ensure_structure_table", main)
        self.assertIn("checkfirst=True", _read(os.path.join(ROOT, "src", "asavexa", "api", "db", "passport_models.py")))

    def test_every_frontend_passport_call_has_a_matching_route(self):
        client = _read(os.path.join(ROOT, "frontend", "src", "api", "client.js"))
        src = _read(os.path.join(ROUTERS, "passport.py"))
        self.assertIn('prefix="/passport"', src)
        self.assertIn('"/passport"', client)
        self.assertIn('"/passport/structure"', client)
        self.assertIn('"/structure"', src)

    def test_passport_page_is_routed_and_permission_gated_in_the_nav(self):
        app = _read(os.path.join(ROOT, "frontend", "src", "app.js"))
        self.assertIn('{ path: "/passport", name: "passport" }', app)
        self.assertIn('permission: PERMISSIONS.PASSPORT_MANAGE', app)


class PassportSharingContractTestCase(unittest.TestCase):
    def _fn(self, path, name):
        tree = ast.parse(_read(os.path.join(ROUTERS, path)))
        return next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)

    def test_creating_and_revoking_need_manage_settings_listing_needs_passport_manage(self):
        for name, perm in (("create_share", "ORG_MANAGE_SETTINGS"), ("revoke_share", "ORG_MANAGE_SETTINGS"),
                           ("list_shares", "PASSPORT_MANAGE")):
            fn = self._fn("passport.py", name)
            self.assertIn(perm, ast.unparse(fn) + " ".join(ast.unparse(d) for d in fn.decorator_list), name)

    def test_public_router_has_no_organisation_auth_and_never_returns_401(self):
        src = _read(os.path.join(ROUTERS, "shared_passport.py"))
        for forbidden in ("get_current_org", "get_current_actor", "require_permission", "HTTP_401", "status_code=401"):
            self.assertNotIn(forbidden, src, forbidden)
        self.assertIn('prefix="/shared-passport"', src)

    def test_a_failed_verification_is_committed_before_the_error_is_raised(self):
        verify = self._fn("shared_passport.py", "verify")
        text = ast.unparse(verify)
        self.assertLess(text.index("session.commit()"), text.index("raise"))
        self.assertIn("ShareAccessDeniedError", text)

    def test_share_tables_are_created_at_startup(self):
        main = _read(MAIN)
        self.assertIn("ensure_share_tables", main)
        self.assertIn("shared_passport.router", main)

    def test_frontend_paths_match_backend_routes(self):
        client = _read(os.path.join(ROOT, "frontend", "src", "api", "client.js"))
        for p in ('"/passport/shares"', "/shared-passport/verify", "/shared-passport/view", "/shared-passport/download", "/access-log", "/revoke"):
            self.assertIn(p, client, p)
        pr = _read(os.path.join(ROUTERS, "passport.py"))
        sp = _read(os.path.join(ROUTERS, "shared_passport.py"))
        for p in ('"/shares"', "/access-log", "/revoke"):
            self.assertIn(p, pr, p)
        for p in ('"/verify"', '"/view"', '"/download"'):
            self.assertIn(p, sp, p)

    def test_recipient_route_is_handled_before_the_login_gate(self):
        app = _read(os.path.join(ROOT, "frontend", "src", "app.js"))
        self.assertIn('{ path: "/shared/:token", name: "shared" }', app)
        self.assertLess(app.index('"shared"', app.index("function render()")), app.index("if (!authState.token)"))
        self.assertIn('{ path: "/passport/sharing", name: "passport-sharing" }', app)
        self.assertLess(app.index('"/passport/sharing", name'), app.index('{ path: "/passport", name'))
