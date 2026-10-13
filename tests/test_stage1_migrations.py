"""Stage 1: the six tables that used to be created at start-up now come from a tracked, idempotent Alembic revision.
Static checks always run (no database needed). The real-PostgreSQL checks run only when ASAVEXA_TEST_PG_URL points at a
throwaway server; they create and drop databases named s1mig_*. They never touch any other database."""
import ast
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import types
import unittest
import urllib.parse

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SQL_DIR = os.path.join(ROOT, "migrations", "sql")
UP = os.path.join(SQL_DIR, "b7c1d2e3f4a5_late_tables.up.sql")
DOWN = os.path.join(SQL_DIR, "b7c1d2e3f4a5_late_tables.down.sql")
VERSIONS = os.path.join(ROOT, "migrations", "versions")
DBDIR = os.path.join(ROOT, "src", "asavexa", "api", "db")
LATE = {"organisation_profiles", "organisation_standards", "organisation_structures",
        "passport_shares", "passport_share_sessions", "security_docs"}
PG = os.environ.get("ASAVEXA_TEST_PG_URL")

sys.path.insert(0, os.path.join(ROOT, "src"))
from asavexa.api import schema_check  # noqa: E402  (pure python; imports sqlalchemy only inside verify_database)


def read(p):
    with open(p) as f:
        return f.read()


def orm_tables():
    """{table: {column names}} read from the four ORM files by parsing, not importing (SQLAlchemy is not needed)."""
    out = {}
    for fn in ("passport_models", "profile_models", "standards_models", "security_models"):
        for node in ast.parse(read(os.path.join(DBDIR, fn + ".py"))).body:
            if not isinstance(node, ast.ClassDef):
                continue
            name, cols = None, set()
            for st in node.body:
                if isinstance(st, ast.Assign) and getattr(st.targets[0], "id", "") == "__tablename__":
                    name = st.value.value
                elif isinstance(st, ast.AnnAssign) and isinstance(st.value, ast.Call) and getattr(st.value.func, "id", "") == "mapped_column":
                    cols.add(st.target.id)
            if name:
                out[name] = cols
    return out


def sql_tables(sql):
    out = {}
    for m in re.finditer(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\);", sql, re.S):
        cols = set()
        for line in m.group(2).splitlines():
            first = line.strip().split(" ")[0]
            if first and first not in ("PRIMARY", "FOREIGN", "UNIQUE") and not first.startswith("--"):
                cols.add(first)
        out[m.group(1)] = cols
    return out


def load_revision(fake_op):
    alembic = types.ModuleType("alembic"); alembic.op = fake_op
    saved = sys.modules.get("alembic"); sys.modules["alembic"] = alembic
    try:
        spec = importlib.util.spec_from_file_location("rev_b7c1", os.path.join(VERSIONS, "b7c1d2e3f4a5_late_tables.py"))
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        return mod
    finally:
        if saved is None:
            sys.modules.pop("alembic", None)
        else:
            sys.modules["alembic"] = saved


class Op:
    def __init__(self): self.calls = []
    def execute(self, sql): self.calls.append(sql)


class RevisionStructure(unittest.TestCase):
    def test_single_linear_history_with_this_revision_at_the_head(self):
        revs = {}
        for fn in os.listdir(VERSIONS):
            if fn.endswith(".py"):
                src = read(os.path.join(VERSIONS, fn))
                rid = re.search(r'^revision: str = "(\w+)"', src, re.M).group(1)
                down = re.search(r'^down_revision: Union\[str, None\] = (None|"(\w+)")', src, re.M)
                revs[rid] = down.group(2)
        self.assertEqual(revs["9ab0a651f090"], None)
        self.assertEqual(revs["b7c1d2e3f4a5"], "9ab0a651f090")
        self.assertEqual(revs["c4d5e6f7a8b9"], "b7c1d2e3f4a5")
        heads = set(revs) - {d for d in revs.values() if d}
        self.assertEqual(heads, {"c4d5e6f7a8b9"}, "exactly one head")

    def test_upgrade_runs_one_statement_per_call_and_only_creates(self):
        op = Op(); mod = load_revision(op); mod.upgrade()
        self.assertGreaterEqual(len(op.calls), 9)
        for stmt in op.calls:
            self.assertRegex(stmt, r"^CREATE (TABLE|INDEX) IF NOT EXISTS ")
            self.assertNotIn(";", stmt)
        created = {m.group(1) for s in op.calls for m in [re.match(r"CREATE TABLE IF NOT EXISTS (\w+)", s)] if m}
        self.assertEqual(created, LATE)

    def test_upgrade_sql_cannot_change_or_delete_existing_rows(self):
        text = "\n".join(l for l in read(UP).splitlines() if not l.strip().startswith("--")).upper()
        for banned in ("DROP ", "DELETE ", "TRUNCATE", "ALTER ", "UPDATE ", "INSERT ", "CASCADE"):
            self.assertNotIn(banned, text)

    def test_downgrade_refuses_without_explicit_permission(self):
        op = Op(); mod = load_revision(op)
        os.environ.pop("ASAVEXA_ALLOW_DESTRUCTIVE_DOWNGRADE", None)
        with self.assertRaises(RuntimeError):
            mod.downgrade()
        self.assertEqual(op.calls, [])
        os.environ["ASAVEXA_ALLOW_DESTRUCTIVE_DOWNGRADE"] = "0"
        try:
            with self.assertRaises(RuntimeError):
                mod.downgrade()
        finally:
            os.environ.pop("ASAVEXA_ALLOW_DESTRUCTIVE_DOWNGRADE", None)

    def test_downgrade_drops_children_before_parents_when_permitted(self):
        op = Op(); mod = load_revision(op)
        os.environ["ASAVEXA_ALLOW_DESTRUCTIVE_DOWNGRADE"] = "1"
        try:
            mod.downgrade()
        finally:
            os.environ.pop("ASAVEXA_ALLOW_DESTRUCTIVE_DOWNGRADE", None)
        names = [re.search(r"DROP TABLE IF EXISTS (\w+)", s).group(1) for s in op.calls]
        self.assertEqual(set(names), LATE)
        self.assertLess(names.index("passport_share_sessions"), names.index("passport_shares"))


class DriftGuards(unittest.TestCase):
    def test_orm_models_and_migration_describe_the_same_tables_and_columns(self):
        self.assertEqual(orm_tables(), sql_tables(read(UP)))

    def test_the_application_no_longer_creates_tables_itself(self):
        for fn in os.listdir(DBDIR):
            if fn.endswith(".py"):
                tree = ast.parse(read(os.path.join(DBDIR, fn)))
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        self.assertFalse(node.name.startswith("ensure_"), f"{fn}: {node.name}")
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                        self.assertNotIn(node.func.attr, ("create_all", "create"), f"{fn}: DDL call in code")
        main = read(os.path.join(ROOT, "src", "asavexa", "api", "main.py"))
        self.assertNotIn("_ensure_optional_tables", main)
        self.assertIn("verify_database", main)

    def test_alembic_env_registers_every_orm_module(self):
        env = read(os.path.join(ROOT, "migrations", "env.py"))
        for mod in ("passport_models", "profile_models", "standards_models", "security_models"):
            self.assertIn(mod, env)

    def test_required_tables_are_exactly_schema_sql_plus_the_migration(self):
        base = set(re.findall(r"^CREATE TABLE (\w+) \(", read(os.path.join(ROOT, "schema.sql")), re.M))
        self.assertEqual(set(schema_check.BASE_TABLES), base)
        self.assertEqual(set(schema_check.LATE_TABLES), LATE)

    def test_dockerfile_runs_migrations_before_the_server(self):
        cmd = [l for l in read(os.path.join(ROOT, "Dockerfile")).splitlines() if l.startswith("CMD")][0]
        self.assertLess(cmd.index("alembic upgrade head"), cmd.index("uvicorn"))
        self.assertIn("&&", cmd)
        self.assertIn("COPY migrations/", read(os.path.join(ROOT, "Dockerfile")))


class StartupSchemaCheck(unittest.TestCase):
    def test_complete_schema_passes(self):
        self.assertEqual(schema_check.check(list(schema_check.REQUIRED_TABLES) + ["alembic_version"], {}), [])

    def test_missing_table_fails_loudly_by_default(self):
        have = [t for t in schema_check.REQUIRED_TABLES if t != "security_docs"]
        with self.assertLogs("asavexa.schema", level="CRITICAL") as cm:
            with self.assertRaises(schema_check.SchemaError) as ctx:
                schema_check.check(have, {})
        self.assertIn("security_docs", str(ctx.exception))
        self.assertIn("alembic upgrade head", str(ctx.exception))
        self.assertTrue(cm.output)

    def test_warn_mode_logs_and_continues(self):
        have = [t for t in schema_check.REQUIRED_TABLES if t != "passport_shares"]
        with self.assertLogs("asavexa.schema", level="CRITICAL"):
            self.assertEqual(schema_check.check(have, {"ASAVEXA_SCHEMA_CHECK": "warn"}), ["passport_shares"])

    def test_unknown_mode_falls_back_to_strict(self):
        self.assertEqual(schema_check.mode({"ASAVEXA_SCHEMA_CHECK": "off"}), "strict")
        self.assertEqual(schema_check.mode({}), "strict")


def _psql(env_url, db, args, sql=None, path=None):
    u = urllib.parse.urlparse(env_url)
    env = dict(os.environ, PGHOST=u.hostname or "localhost", PGPORT=str(u.port or 5432), PGUSER=urllib.parse.unquote(u.username or "postgres"), PGDATABASE=db)
    if u.password:
        env["PGPASSWORD"] = urllib.parse.unquote(u.password)
    cmd = ["psql", "-v", "ON_ERROR_STOP=1", "-q", "-At"] + args
    if path:
        cmd += ["-f", path]
    r = subprocess.run(cmd, env=env, input=sql, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


@unittest.skipUnless(PG and shutil.which("psql"), "needs ASAVEXA_TEST_PG_URL and psql")
class RealPostgresMigration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fresh, cls.live = f"s1mig_fresh_{os.getpid()}", f"s1mig_live_{os.getpid()}"
        for db in (cls.fresh, cls.live):
            _psql(PG, "postgres", ["-c", f"DROP DATABASE IF EXISTS {db}"]); _psql(PG, "postgres", ["-c", f"CREATE DATABASE {db}"])

    @classmethod
    def tearDownClass(cls):
        for db in (cls.fresh, cls.live):
            _psql(PG, "postgres", ["-c", f"DROP DATABASE IF EXISTS {db}"])

    def tables(self, db):
        return set(_psql(PG, db, ["-c", "select table_name from information_schema.tables where table_schema='public'"]).splitlines())

    def test_1_fresh_database_gets_every_table_and_passes_the_startup_check(self):
        _psql(PG, self.fresh, [], path=os.path.join(ROOT, "schema.sql"))
        self.assertEqual(len(self.tables(self.fresh)), 17)
        _psql(PG, self.fresh, [], path=UP)
        have = self.tables(self.fresh)
        self.assertEqual(schema_check.check(have, {}), [])
        self.assertEqual(len(have), 23)
        before = _psql(PG, self.fresh, ["-c", "select count(*) from information_schema.columns where table_schema='public'"])
        _psql(PG, self.fresh, [], path=UP)                     # second run: no error, no change
        self.assertEqual(before, _psql(PG, self.fresh, ["-c", "select count(*) from information_schema.columns where table_schema='public'"]))

    def test_2_startup_check_catches_a_database_that_was_not_migrated(self):
        _psql(PG, self.live, [], path=os.path.join(ROOT, "schema.sql"))
        with self.assertLogs("asavexa.schema", level="CRITICAL"):
            with self.assertRaises(schema_check.SchemaError) as ctx:
                schema_check.check(self.tables(self.live), {})
        self.assertIn("organisation_profiles", str(ctx.exception))

    def test_3_existing_data_survives_the_upgrade_unchanged(self):
        _psql(PG, self.live, [], path=UP)
        _psql(PG, self.live, [], sql="""
            INSERT INTO organisations(id,name) VALUES ('11111111-1111-1111-1111-111111111111','Org A');
            INSERT INTO organisation_profiles VALUES ('11111111-1111-1111-1111-111111111111','{"legal_name":"A Ltd"}',now(),'u1');
            INSERT INTO security_docs VALUES ('mfa','u1','11111111-1111-1111-1111-111111111111','{"enabled":true}',now());""")
        snap = "select md5(string_agg(x::text,'|' order by x::text)) from (select * from organisation_profiles) x"
        snap2 = "select md5(string_agg(x::text,'|' order by x::text)) from (select * from security_docs) x"
        a = (_psql(PG, self.live, ["-c", snap]), _psql(PG, self.live, ["-c", snap2]))
        _psql(PG, self.live, [], path=UP)                      # what Alembic does on a production database that already has the tables
        b = (_psql(PG, self.live, ["-c", snap]), _psql(PG, self.live, ["-c", snap2]))
        self.assertEqual(a, b)
        self.assertEqual(_psql(PG, self.live, ["-c", "select count(*) from security_docs"]), "1")

    def test_4_the_destructive_down_script_removes_exactly_the_six_tables(self):
        _psql(PG, self.fresh, [], path=DOWN)
        self.assertEqual(self.tables(self.fresh) & LATE, set())
        self.assertEqual(len(self.tables(self.fresh)), 17)
        _psql(PG, self.fresh, [], path=UP)                     # and back up again
        self.assertEqual(len(self.tables(self.fresh)), 23)


if __name__ == "__main__":
    unittest.main()
