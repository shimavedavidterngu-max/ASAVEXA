"""
API BOUNDARY CONTRACT TESTS.

These are explicitly NOT HTTP integration tests. FastAPI, Pydantic, and
SQLAlchemy cannot be imported in this environment (no network access;
no cached wheels anywhere on this filesystem — verified directly, not
assumed). Nothing in this file imports `fastapi`, `pydantic`, or
`sqlalchemy`, and nothing here pretends to.

What this file DOES verify, for real, by executing real Python against
the real (framework-independent) domain/service layer and by statically
parsing the real router source with `ast`:

1. Every exception class api/main.py classifies into an HTTP-status
   bucket is a real, correctly-subclassed, unambiguously-routed member
   of that bucket (exception_mapping_check.py, inlined below).
2. Every router->service call site references a real method with real
   keyword-argument names on the actual service class
   (router_service_contract_check.py, inlined below).
3. Every router named in api/main.py's `include_router(...)` calls is
   actually defined exactly once, with a coherent, non-overlapping
   prefix.
4. Every `require_permission(X)` call site across every router
   references a real, defined permission constant.
5. The specific domain-level behaviors that router 404/403/401 paths
   are built on top of (e.g. "a missing journal id resolves to None",
   "a non-member has no role") are the ones actually exercised by the
   existing domain test suite — cross-referenced here, not re-tested.

None of this proves FastAPI/Starlette actually route an HTTP request to
these handlers at runtime, that Pydantic validates a real request body,
or that SQLAlchemy executes real SQL against a real PostgreSQL
connection. See docs/runtime-verification.md for what remains
unverified and the exact commands to verify it once dependencies are
installable.
"""
import ast
import importlib
import inspect
import os
import sys
import unittest

ASAVEXA_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
API_ROOT = os.path.join(ASAVEXA_SRC, "asavexa", "api")
ROUTERS_DIR = os.path.join(API_ROOT, "routers")
MAIN_PY = os.path.join(API_ROOT, "main.py")


# ----------------------------------------------------------------------
# Shared static-analysis helpers
# ----------------------------------------------------------------------
def _resolve_relative_import(module, level, package_parts):
    base_parts = package_parts[: len(package_parts) - (level - 1)]
    if module:
        return ".".join(base_parts + module.split("."))
    return ".".join(base_parts)


class ExceptionMappingConsistencyTestCase(unittest.TestCase):
    """Section 3 'Error behavior' + section 4 'expected exception mappings'.

    Proves api/main.py's exception -> HTTP-status classification is
    internally correct by statically extracting the classification
    tuples and each handler's isinstance-chain, then dynamically
    importing the REAL domain error classes (pure Python — no fastapi
    needed) and checking real issubclass() relationships.
    """

    @classmethod
    def setUpClass(cls):
        with open(MAIN_PY) as f:
            tree = ast.parse(f.read())
        cls.tree = tree

        # local name -> (real dotted module, original name in that module)
        name_to_module = {}
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.level > 0:
                dotted = _resolve_relative_import(node.module, node.level, ["asavexa", "api"])
                for alias in node.names:
                    local_name = alias.asname or alias.name
                    name_to_module[local_name] = (dotted, alias.name)
        cls.name_to_module = name_to_module

        tuples = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                target = node.targets[0].id
                if target.startswith("_") and isinstance(node.value, ast.Tuple):
                    tuples[target] = [elt.id for elt in node.value.elts if isinstance(elt, ast.Name)]
        cls.tuples = tuples

        handlers = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Call) and getattr(dec.func, "attr", None) == "exception_handler":
                        base_type = dec.args[0].id if isinstance(dec.args[0], ast.Name) else None
                        chain = []
                        for stmt in node.body:
                            if isinstance(stmt, ast.If):
                                test = stmt.test
                                if (isinstance(test, ast.Call) and getattr(test.func, "id", None) == "isinstance"
                                        and isinstance(test.args[1], ast.Name)):
                                    chain.append(test.args[1].id)
                        handlers.append({"function": node.name, "base_type": base_type, "chain": chain})
        cls.handlers = handlers

    def test_every_handler_base_type_resolves_to_a_real_class(self):
        for h in self.handlers:
            entry = self.name_to_module.get(h["base_type"])
            self.assertIsNotNone(entry, f"{h['function']}: base type {h['base_type']} not importable")
            module, original = entry
            cls = getattr(importlib.import_module(module), original)
            self.assertTrue(issubclass(cls, Exception))

    def test_every_classified_exception_is_a_real_subclass_of_its_handler_base(self):
        checked = 0
        for h in self.handlers:
            base_module, base_original = self.name_to_module[h["base_type"]]
            BaseClass = getattr(importlib.import_module(base_module), base_original)
            seen = set()
            for tuple_name in h["chain"]:
                member_names = self.tuples.get(tuple_name) or (
                    [tuple_name] if tuple_name in self.name_to_module else None
                )
                self.assertIsNotNone(member_names, f"{h['function']}: {tuple_name} is neither a known "
                                                    f"tuple nor an importable class")
                for cls_name in member_names:
                    module, original = self.name_to_module[cls_name]
                    Cls = getattr(importlib.import_module(module), original)
                    checked += 1
                    self.assertTrue(
                        issubclass(Cls, BaseClass),
                        f"{h['function']}: {cls_name} is classified here but is not a subclass of {h['base_type']}",
                    )
                    self.assertNotIn(
                        cls_name, seen,
                        f"{h['function']}: {cls_name} classified twice — second occurrence is dead logic",
                    )
                    seen.add(cls_name)
        self.assertGreater(checked, 40, "sanity: expected dozens of classified exceptions across 7 handlers")


class RouterServiceCallSiteTestCase(unittest.TestCase):
    """Section 4: 'service methods that do not exist, incorrect argument
    names' — checked for real via inspect.signature on the actual,
    importable service classes (none of which need fastapi)."""

    SERVICE_CLASSES = {
        "accounts.py": ("asavexa.accounting.services.engine", "AccountingEngine"),
        "periods.py": ("asavexa.accounting.services.engine", "AccountingEngine"),
        "journals.py": ("asavexa.accounting.services.engine", "AccountingEngine"),
        "evidence.py": ("asavexa.evidence.services.vault", "EvidenceVault"),
        "reconciliation.py": ("asavexa.reconciliation.services.service", "ReconciliationService"),
        "reporting.py": ("asavexa.reporting.services.service", "ReportingService"),
        "period_close.py": ("asavexa.period_close.services.service", "PeriodCloseService"),
        "compliance.py": ("asavexa.compliance.services.service", "ComplianceService"),
        "auth.py": ("asavexa.identity.services.service", "IdentityService"),
        "audit.py": ("asavexa.audit.repository", "AuditRepository"),
    }

    def test_every_router_service_call_matches_a_real_method_signature(self):
        endpoints_found = 0
        calls_checked = 0
        for fname, (module_path, class_name) in self.SERVICE_CLASSES.items():
            path = os.path.join(ROUTERS_DIR, fname)
            with open(path) as f:
                tree = ast.parse(f.read())
            ServiceClass = getattr(importlib.import_module(module_path), class_name)

            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef):
                    continue
                is_endpoint = any(
                    isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                    and d.func.attr in ("get", "post", "patch", "delete", "put")
                    for d in node.decorator_list
                )
                if not is_endpoint:
                    continue
                endpoints_found += 1
                service_param_names = {
                    a.arg for a in node.args.args
                    if isinstance(a.annotation, ast.Name) and a.annotation.id == class_name
                }
                for call_node in ast.walk(node):
                    if not (isinstance(call_node, ast.Call) and isinstance(call_node.func, ast.Attribute)):
                        continue
                    receiver = call_node.func.value
                    method_name = call_node.func.attr
                    if not (isinstance(receiver, ast.Name) and receiver.id in service_param_names):
                        continue

                    calls_checked += 1
                    self.assertTrue(
                        hasattr(ServiceClass, method_name),
                        f"{fname}::{node.name}: {class_name} has no method {method_name!r}",
                    )
                    sig = inspect.signature(getattr(ServiceClass, method_name))
                    real_params = set(sig.parameters.keys()) - {"self"}
                    for kw in call_node.keywords:
                        if kw.arg is None:
                            continue
                        self.assertIn(
                            kw.arg, real_params,
                            f"{fname}::{node.name}: {class_name}.{method_name} has no parameter {kw.arg!r} "
                            f"(real params: {sorted(real_params)})",
                        )
        self.assertGreater(endpoints_found, 70, "sanity: expected ~80 endpoint functions across 9 routers")
        self.assertGreater(calls_checked, 60, "sanity: expected 60+ validated router->service call-site references")


class RouteRegistrationTestCase(unittest.TestCase):
    """Section 5: every intended router registered exactly once, with a
    coherent, non-overlapping prefix; every referenced router object
    actually exists in its module."""

    EXPECTED_PREFIXES = {
        "auth.router": "/auth", "auth.org_router": "/organisations",
        "accounts.router": "/accounts", "periods.router": "/periods",
        "journals.router": "/journals", "evidence.router": "/evidence",
        "reconciliation.router": "/reconciliations",
        "reconciliation.txn_router": "/reconciliations/transactions",
        "reporting.router": "/reports", "period_close.router": "/period-close",
        "compliance.router": "/compliance",
        "audit.router": "/audit",
        "organisation_profile.router": "/organisation-profile",
    }

    def test_every_expected_router_registered_exactly_once(self):
        with open(MAIN_PY) as f:
            tree = ast.parse(f.read())
        registered = []
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "include_router"):
                arg = node.args[0]
                if isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name):
                    registered.append(f"{arg.value.id}.{arg.attr}")

        self.assertEqual(
            sorted(registered), sorted(self.EXPECTED_PREFIXES.keys()),
            "registered routers must exactly match the expected set — nothing missing, nothing extra",
        )
        self.assertEqual(len(registered), len(set(registered)), "no router may be registered twice")

    def test_every_router_object_actually_exists_with_the_expected_prefix(self):
        for qualified_name, expected_prefix in self.EXPECTED_PREFIXES.items():
            module_file, attr = qualified_name.split(".")
            path = os.path.join(ROUTERS_DIR, module_file + ".py")
            with open(path) as f:
                tree = ast.parse(f.read())
            found_prefix = None
            for node in tree.body:
                if (isinstance(node, ast.Assign) and len(node.targets) == 1
                        and isinstance(node.targets[0], ast.Name) and node.targets[0].id == attr
                        and isinstance(node.value, ast.Call)):
                    for kw in node.value.keywords:
                        if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                            found_prefix = kw.value.value
            self.assertEqual(found_prefix, expected_prefix, f"{qualified_name} prefix mismatch")

    def test_no_two_router_prefixes_collide(self):
        prefixes = list(self.EXPECTED_PREFIXES.values())
        # /reconciliations and /reconciliations/transactions legitimately
        # nest — every other pair must not be a prefix of one another.
        allowed_nesting = {("/reconciliations", "/reconciliations/transactions")}
        for i, a in enumerate(prefixes):
            for b in prefixes[i + 1:]:
                if a == b:
                    self.fail(f"duplicate prefix: {a}")
                pair = (a, b) if a < b else (b, a)
                if b.startswith(a + "/") or a.startswith(b + "/"):
                    self.assertIn(pair, allowed_nesting, f"unexpected prefix nesting: {a} / {b}")


class PermissionConstantValidityTestCase(unittest.TestCase):
    """Every `require_permission(X)` call site across every router
    references a real, defined permission constant — not a typo'd
    string, not a stale name."""

    def test_every_require_permission_reference_is_a_real_constant(self):
        from asavexa.identity.domain import permissions as perm_module
        real_permission_names = {
            n for n in dir(perm_module)
            if n.isupper() and isinstance(getattr(perm_module, n), str)
        }
        checked = 0
        for fname in os.listdir(ROUTERS_DIR):
            if not fname.endswith(".py"):
                continue
            with open(os.path.join(ROUTERS_DIR, fname)) as f:
                tree = ast.parse(f.read())
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id == "require_permission" and node.args
                        and isinstance(node.args[0], ast.Name)):
                    checked += 1
                    self.assertIn(
                        node.args[0].id, real_permission_names,
                        f"{fname}: require_permission({node.args[0].id}) — not a real permission constant",
                    )
        self.assertGreater(checked, 40, "sanity: expected 40+ require_permission call sites")


class DatabaseInitializationTestCase(unittest.TestCase):
    """Section 6: proves engine/session construction in api/db/base.py is
    lazy (deferred to first call), not performed at module import time —
    checked statically via ast, since db/base.py itself imports
    sqlalchemy and cannot be imported in this environment."""

    def test_create_engine_is_never_called_at_module_top_level(self):
        base_path = os.path.join(API_ROOT, "db", "base.py")
        with open(base_path) as f:
            tree = ast.parse(f.read())

        for node in tree.body:
            # Anything inside a top-level function/class body is not
            # executed at import time — only look at the OTHER top-level
            # statements (Assign, Expr, If, ...), which in a correct
            # lazy-init module should contain no create_engine() call.
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
                        and sub.func.id == "create_engine"):
                    self.fail(
                        "create_engine() is called at module top level in db/base.py — "
                        "importing this module would require a live DB driver immediately"
                    )

    def test_create_engine_is_called_exactly_once_inside_a_function(self):
        base_path = os.path.join(API_ROOT, "db", "base.py")
        with open(base_path) as f:
            tree = ast.parse(f.read())
        calls_inside_functions = 0
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for sub in ast.walk(node):
                    if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
                            and sub.func.id == "create_engine"):
                        calls_inside_functions += 1
        self.assertEqual(calls_inside_functions, 1, "expected exactly one lazy create_engine() call site")

    def test_get_session_dependency_contract_is_unchanged(self):
        """get_session must remain a generator (yield, not return) with
        a finally-close, since every get_X_service factory in deps.py
        depends on this exact shape via Depends(get_session)."""
        base_path = os.path.join(API_ROOT, "db", "base.py")
        with open(base_path) as f:
            tree = ast.parse(f.read())
        get_session_fn = next(
            n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "get_session"
        )
        has_yield = any(isinstance(n, ast.Yield) for n in ast.walk(get_session_fn))
        has_finally = any(
            isinstance(n, ast.Try) and n.finalbody for n in ast.walk(get_session_fn)
        )
        self.assertTrue(has_yield, "get_session must yield a session")
        self.assertTrue(has_finally, "get_session must close the session in a finally block")

    def test_get_session_commits_once_on_success_and_rolls_back_on_exception(self):
        """Section 6 fix: the whole request must be one transaction —
        commit happens exactly once, immediately after the yield
        (i.e. after the request handler runs to completion), and a
        rollback happens if the request raised. Checked statically via
        ast, since db/base.py imports sqlalchemy and can't be executed
        here — but the *shape* of this control flow (commit right after
        yield, inside a try that also has an except-Exception branch
        calling rollback) is exactly what makes each request atomic."""
        base_path = os.path.join(API_ROOT, "db", "base.py")
        with open(base_path) as f:
            tree = ast.parse(f.read())
        get_session_fn = next(
            n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "get_session"
        )
        try_node = next(n for n in ast.walk(get_session_fn) if isinstance(n, ast.Try))

        # yield is immediately followed by a commit() call in the try body.
        yield_index = next(i for i, s in enumerate(try_node.body) if isinstance(s, ast.Expr) and isinstance(s.value, ast.Yield))
        commit_calls_after_yield = [
            s for s in try_node.body[yield_index + 1:]
            if isinstance(s, ast.Expr) and isinstance(s.value, ast.Call)
            and isinstance(s.value.func, ast.Attribute) and s.value.func.attr == "commit"
        ]
        self.assertTrue(commit_calls_after_yield, "commit() must be called right after yield, on success")

        # An except handler calls rollback().
        rollback_found = any(
            isinstance(h, ast.ExceptHandler)
            and any(
                isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "rollback"
                for n in ast.walk(h)
            )
            for h in try_node.handlers
        )
        self.assertTrue(rollback_found, "an except handler must call rollback() on failure")

    def test_no_sqlalchemy_repository_method_commits_independently(self):
        """The 29-call-site defect this fix closes: every
        create()/update() previously called self.session.commit()
        itself, making each individual write its own transaction with
        no atomicity across a multi-write service operation. Now the
        session-level commit in get_session() is the only commit —
        checked here by confirming zero '.commit()' call sites remain
        anywhere in the SQLAlchemy repository files."""
        db_dir = os.path.join(API_ROOT, "db")
        repo_files = [
            "sqlalchemy_repository.py", "identity_sqlalchemy_repository.py",
            "evidence_sqlalchemy_repository.py", "reconciliation_sqlalchemy_repository.py",
            "period_close_sqlalchemy_repository.py", "compliance_sqlalchemy_repository.py",
            "audit_sqlalchemy_repository.py",
        ]
        for fname in repo_files:
            with open(os.path.join(db_dir, fname)) as f:
                tree = ast.parse(f.read())
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "commit"):
                    self.fail(f"{fname} still calls .commit() independently — atomicity regression")


class RepositoryParityTestCase(unittest.TestCase):
    """Section 7: SQLite vs SQLAlchemy repository contract parity.
    SQLite classes are real, importable Python (inspect.signature gives
    ground truth); SQLAlchemy classes can't be imported here, so their
    signatures are extracted statically via ast. Found and fixed one
    real defect during this audit: SqlAlchemySessionRepository.create/
    update used parameter name `session_` instead of `session`,
    silently breaking any future caller using keyword-argument syntax
    even though every current call site is positional."""

    PAIRS = [
        ("asavexa.accounting.repository.sqlite_repository",
         ["SqliteAccountRepository", "SqliteJournalRepository", "SqlitePeriodRepository"],
         os.path.join(API_ROOT, "db", "sqlalchemy_repository.py"),
         ["SqlAlchemyAccountRepository", "SqlAlchemyJournalRepository", "SqlAlchemyPeriodRepository"]),
        ("asavexa.identity.repository.sqlite_repository",
         ["SqliteOrganisationRepository", "SqliteUserRepository", "SqliteMembershipRepository", "SqliteSessionRepository"],
         os.path.join(API_ROOT, "db", "identity_sqlalchemy_repository.py"),
         ["SqlAlchemyOrganisationRepository", "SqlAlchemyUserRepository", "SqlAlchemyMembershipRepository", "SqlAlchemySessionRepository"]),
        ("asavexa.evidence.repository.sqlite_repository",
         ["SqliteEvidenceRepository"],
         os.path.join(API_ROOT, "db", "evidence_sqlalchemy_repository.py"),
         ["SqlAlchemyEvidenceRepository"]),
        ("asavexa.reconciliation.repository.sqlite_repository",
         ["SqliteReconciliationRepository", "SqliteBankTransactionRepository"],
         os.path.join(API_ROOT, "db", "reconciliation_sqlalchemy_repository.py"),
         ["SqlAlchemyReconciliationRepository", "SqlAlchemyBankTransactionRepository"]),
        ("asavexa.period_close.repository.sqlite_repository",
         ["SqlitePeriodCloseRepository"],
         os.path.join(API_ROOT, "db", "period_close_sqlalchemy_repository.py"),
         ["SqlAlchemyPeriodCloseRepository"]),
        ("asavexa.compliance.repository.sqlite_repository",
         ["SqliteControlDefinitionRepository", "SqliteControlExecutionRepository", "SqliteFindingRepository", "SqliteRemediationRepository"],
         os.path.join(API_ROOT, "db", "compliance_sqlalchemy_repository.py"),
         ["SqlAlchemyControlDefinitionRepository", "SqlAlchemyControlExecutionRepository", "SqlAlchemyFindingRepository", "SqlAlchemyRemediationRepository"]),
        ("asavexa.audit.sqlite_repository", ["SqliteAuditRepository"],
         os.path.join(API_ROOT, "db", "audit_sqlalchemy_repository.py"), ["SqlAlchemyAuditRepository"]),
    ]

    @staticmethod
    def _sqlalchemy_class_methods(file_path, class_name):
        with open(file_path) as f:
            tree = ast.parse(f.read())
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                return {
                    item.name: [a.arg for a in item.args.args if a.arg != "self"]
                    for item in node.body
                    if isinstance(item, ast.FunctionDef) and not item.name.startswith("_")
                }
        return None

    def test_every_repository_pair_has_full_method_and_parameter_parity(self):
        pairs_checked = 0
        for sqlite_mod_path, sqlite_classes, sa_file, sa_classes in self.PAIRS:
            sqlite_mod = importlib.import_module(sqlite_mod_path)
            for sqlite_cls_name, sa_cls_name in zip(sqlite_classes, sa_classes):
                pairs_checked += 1
                SqliteCls = getattr(sqlite_mod, sqlite_cls_name)
                sqlite_methods = {
                    n: [p for p in inspect.signature(m).parameters if p != "self"]
                    for n, m in vars(SqliteCls).items()
                    if callable(m) and not n.startswith("_")
                }
                sa_methods = self._sqlalchemy_class_methods(sa_file, sa_cls_name)
                self.assertIsNotNone(sa_methods, f"{sa_cls_name} not found in {sa_file}")

                self.assertEqual(
                    set(sqlite_methods), set(sa_methods),
                    f"{sqlite_cls_name} vs {sa_cls_name}: method name mismatch",
                )
                for method_name in sqlite_methods:
                    self.assertEqual(
                        set(sqlite_methods[method_name]), set(sa_methods[method_name]),
                        f"{sqlite_cls_name} vs {sa_cls_name}.{method_name}(): parameter name mismatch — "
                        f"sqlite={sorted(sqlite_methods[method_name])} vs "
                        f"sqlalchemy={sorted(sa_methods[method_name])}",
                    )
        self.assertEqual(pairs_checked, 16, "expected exactly 16 repository pairs")


class CorsConfigurationTestCase(unittest.TestCase):
    """Phase 6, Step 15: CORS must never combine a wildcard origin with
    credentials, and must never be configured with allow_credentials
    without a real cookie-based auth model to protect (this API uses
    Bearer tokens, not cookies — see security-architecture.md)."""

    def test_cors_middleware_is_registered(self):
        with open(MAIN_PY) as f:
            tree = ast.parse(f.read())
        found = any(
            isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_middleware"
            and node.args and getattr(node.args[0], "id", None) == "CORSMiddleware"
            for node in ast.walk(tree)
        )
        self.assertTrue(found, "CORSMiddleware must be registered on the app")

    def test_cors_never_combines_wildcard_origin_with_credentials(self):
        with open(MAIN_PY) as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "add_middleware"):
                continue
            kwargs = {kw.arg: kw.value for kw in node.keywords}
            allow_credentials = kwargs.get("allow_credentials")
            allow_origins = kwargs.get("allow_origins")
            credentials_true = isinstance(allow_credentials, ast.Constant) and allow_credentials.value is True
            origins_is_wildcard_literal = (
                isinstance(allow_origins, ast.List) and len(allow_origins.elts) == 1
                and isinstance(allow_origins.elts[0], ast.Constant) and allow_origins.elts[0].value == "*"
            )
            self.assertFalse(
                credentials_true and origins_is_wildcard_literal,
                "CORS must never combine allow_origins=['*'] with allow_credentials=True",
            )

    def test_cors_allow_credentials_is_false_matching_the_bearer_token_auth_model(self):
        """This API has no cookie-based session and therefore no CSRF
        surface from CORS — allow_credentials must stay False unless
        the auth model changes to cookies, at which point CSRF
        protection must be added alongside it (documented in
        security-architecture.md, not silently changed here)."""
        with open(MAIN_PY) as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "add_middleware"
                    and node.args and getattr(node.args[0], "id", None) == "CORSMiddleware"):
                continue
            kwargs = {kw.arg: kw.value for kw in node.keywords}
            allow_credentials = kwargs.get("allow_credentials")
            self.assertIsInstance(allow_credentials, ast.Constant)
            self.assertFalse(allow_credentials.value)

    def test_cors_origins_are_configurable_via_environment_not_hardcoded_only(self):
        with open(MAIN_PY) as f:
            content = f.read()
        self.assertIn("CORS_ALLOWED_ORIGINS", content)
        self.assertIn("os.environ.get", content)


class HealthReadinessTestCase(unittest.TestCase):
    """Section 13: liveness (/health) must never depend on the database;
    readiness (/ready) must actually attempt one. Found missing during
    the Phase 3 audit — only /health existed, and it never touched the
    database, so nothing distinguished 'process alive' from 'database
    reachable' for an orchestrator's readiness probe."""

    def test_health_endpoint_has_no_database_dependency(self):
        with open(MAIN_PY) as f:
            tree = ast.parse(f.read())
        health_fn = next(
            n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "health"
        )
        self.assertEqual(len(health_fn.args.args), 0, "/health must take no dependencies — pure liveness")

    def test_ready_endpoint_depends_on_a_real_database_session(self):
        with open(MAIN_PY) as f:
            tree = ast.parse(f.read())
        ready_fn = next(
            n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "ready"
        )
        args = ready_fn.args
        # ast stores parameter defaults in a separate list, aligned to
        # the trailing N parameters of args.args — not as an attribute
        # of each ast.arg node itself.
        defaulted_args = list(zip(args.args[len(args.args) - len(args.defaults):], args.defaults))
        self.assertTrue(
            any(
                isinstance(default, ast.Call) and getattr(default.func, "id", None) == "Depends"
                and getattr(default.args[0], "id", None) == "get_session"
                for _, default in defaulted_args
            ),
            "/ready must depend on Depends(get_session) — a real database session",
        )

    def test_ready_endpoint_executes_a_real_query_and_handles_failure(self):
        with open(MAIN_PY) as f:
            source = f.read()
        tree = ast.parse(source)
        ready_fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "ready")
        has_execute_call = any(
            isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "execute"
            for n in ast.walk(ready_fn)
        )
        has_try_except = any(isinstance(n, ast.Try) for n in ast.walk(ready_fn))
        self.assertTrue(has_execute_call, "/ready must actually execute a query, not just return ok")
        self.assertTrue(has_try_except, "/ready must handle a failed connection explicitly, not 500")


class DomainContractsBehindRouterErrorPathsTestCase(unittest.TestCase):
    """Section 2: proves the specific domain-level facts a few router
    error paths are built on are real and tested — not re-testing what
    test_accounting_engine.py / test_identity_service.py already cover,
    but making the router<->domain link explicit and verified in one
    place, since routers cannot themselves be imported here."""

    def test_missing_journal_lookup_returns_none_not_raises(self):
        """Backs GET /journals/{id}'s `if journal is None: raise
        JournalNotFoundError` — the router's own null-check logic."""
        from asavexa.accounting.domain.enums import AccountType
        from asavexa.accounting.repository.sqlite_repository import (
            SqliteAccountRepository, SqliteJournalRepository, SqlitePeriodRepository,
        )
        from asavexa.accounting.services.engine import AccountingEngine
        from asavexa.audit.sqlite_repository import SqliteAuditRepository
        from asavexa.bootstrap import create_sqlite_connection

        conn = create_sqlite_connection(":memory:")
        engine = AccountingEngine(
            accounts=SqliteAccountRepository(conn), periods=SqlitePeriodRepository(conn),
            journals=SqliteJournalRepository(conn), audit=SqliteAuditRepository(conn),
        )
        self.assertIsNone(engine.journals.get("org-a", "does-not-exist"))

    def test_get_role_returns_none_for_non_member(self):
        """Backs GET /organisations/{id}/members's `if
        identity.get_role(actor, org_id) is None: raise
        HTTPException(403)`. This exact fact is already directly
        asserted twice in test_identity_service.py; re-executed here
        (not duplicated logic, just re-confirmed against a fresh
        instance) specifically to make the router<->domain link explicit,
        since the router itself cannot be imported in this environment."""
        from asavexa.identity.repository.sqlite_repository import (
            SqliteMembershipRepository, SqliteOrganisationRepository,
            SqliteSessionRepository, SqliteUserRepository, connect,
        )
        from asavexa.identity.services.service import IdentityService
        from asavexa.identity.domain.enums import Role
        from asavexa.audit.sqlite_repository import SqliteAuditRepository, ensure_schema

        conn = connect(":memory:")
        ensure_schema(conn)
        identity = IdentityService(
            organisations=SqliteOrganisationRepository(conn), users=SqliteUserRepository(conn),
            memberships=SqliteMembershipRepository(conn), sessions=SqliteSessionRepository(conn),
            audit=SqliteAuditRepository(conn),
        )
        outsider = identity.register_user("outsider@example.test", "correct horse battery staple")
        owner = identity.register_user("owner@example.test", "another-strong-password")
        org = identity.create_organisation("Some Org", actor=owner.id)
        identity.add_membership(org.id, owner.id, Role.OWNER, actor_user_id=owner.id)

        self.assertIsNone(identity.get_role(outsider.id, org.id))


if __name__ == "__main__":
    unittest.main()
