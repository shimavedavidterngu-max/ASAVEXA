"""Stage 9: the shared (multi-instance) rate limiter."""
import importlib.util
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

import harness_security_routers  # noqa: F401  (stands in for fastapi so api/ratelimit.py imports)
from asavexa.api import ratelimit
from asavexa.security.monitoring import RateLimiter
from asavexa.security.sharedlimit import SharedRateLimiter, SqlHitStore, make_limiter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UP = os.path.join(ROOT, "migrations", "sql", "c4d5e6f7a8b9_rate_limit_hits.up.sql")
DOWN = os.path.join(ROOT, "migrations", "sql", "c4d5e6f7a8b9_rate_limit_hits.down.sql")
PG = os.environ.get("ASAVEXA_TEST_PG_URL")


def create_table(path):
    c = sqlite3.connect(path)
    lines = [l for l in open(UP).read().splitlines() if not l.strip().startswith("--")]
    for stmt in [s.strip() for s in "\n".join(lines).split(";") if s.strip()]:
        c.execute(stmt)
    c.commit(); c.close()


class Clock:
    def __init__(self, t=1_000_000.0): self.t = t
    def __call__(self): return self.t


class SharedLimiterTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(); self.db = os.path.join(self.dir, "rl.db"); create_table(self.db)
        self.clock = Clock()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def instance(self, limit=3, window=60, name="login"):
        """One 'server instance': its own connections to the one shared database."""
        return SharedRateLimiter(name, limit, window, SqlHitStore(lambda: sqlite3.connect(self.db), "?"), wall_clock=self.clock)

    def test_the_limit_is_enforced_with_a_retry_time(self):
        a = self.instance()
        self.assertEqual([a.allow("1.1.1.1")[0] for _ in range(3)], [True, True, True])
        ok, wait = a.allow("1.1.1.1")
        self.assertFalse(ok); self.assertTrue(1 <= wait <= 60)
        self.assertTrue(a.allow("2.2.2.2")[0])                         # another caller is unaffected

    def test_two_instances_count_together(self):
        a, b = self.instance(), self.instance()
        a.allow("9.9.9.9"); b.allow("9.9.9.9"); a.allow("9.9.9.9")
        self.assertFalse(b.allow("9.9.9.9")[0])                        # the third instance-spanning hit is the last allowed; the fourth is refused
        self.assertFalse(a.allow("9.9.9.9")[0])

    def test_in_memory_limiters_do_not_share_which_is_why_this_exists(self):
        a, b = RateLimiter(3, 60), RateLimiter(3, 60)
        for _ in range(3): a.allow("k")
        self.assertTrue(b.allow("k")[0])

    def test_a_new_window_starts_fresh_and_old_rows_are_tidied(self):
        a = self.instance(limit=1)
        self.assertTrue(a.allow("k")[0]); self.assertFalse(a.allow("k")[0])
        self.clock.t += 61
        self.assertTrue(a.allow("k")[0])
        self.clock.t += 500
        a.allow("other")
        rows = sqlite3.connect(self.db).execute("select count(*) from rate_limit_hits").fetchone()[0]
        self.assertLessEqual(rows, 2)

    def test_names_keep_endpoints_apart(self):
        a, b = self.instance(limit=1, name="login"), self.instance(limit=1, name="mfa")
        self.assertTrue(a.allow("k")[0]); self.assertTrue(b.allow("k")[0])

    def test_when_the_database_fails_it_falls_back_and_never_locks_people_out(self):
        os.remove(self.db)
        open(self.db, "w").close()                                     # an empty database: the table is missing
        a = self.instance(limit=2)
        self.assertEqual([a.allow("k")[0] for _ in range(3)], [True, True, False])    # still throttled, locally
        self.assertEqual((a.shared_calls, a.fallback_calls), (0, 3))

    def test_it_recovers_when_the_table_appears(self):
        os.remove(self.db); open(self.db, "w").close()
        a = self.instance(limit=5)
        a.allow("k"); self.assertEqual(a.fallback_calls, 1)
        create_table(self.db)
        a.allow("k"); self.assertEqual(a.shared_calls, 1)

    def test_a_failed_request_cannot_roll_a_hit_back(self):
        a = self.instance(limit=2)
        a.allow("k"); a.allow("k")
        self.assertEqual(sqlite3.connect(self.db).execute("select hits from rate_limit_hits").fetchone()[0], 2)   # committed by its own connection

    def test_long_keys_are_bounded(self):
        a = self.instance(); a.allow("x" * 500)
        self.assertLessEqual(len(sqlite3.connect(self.db).execute("select key from rate_limit_hits").fetchone()[0]), 200)

    def test_limit_attribute_can_be_changed_like_the_original(self):
        a = self.instance(limit=1); a.limit = 5
        self.assertEqual([a.allow("k")[0] for _ in range(5)], [True] * 5)


class SelectionTests(unittest.TestCase):
    def test_default_is_the_original_in_memory_limiter(self):
        self.assertIsInstance(make_limiter("x", 1, 1), RateLimiter)
        self.assertIsInstance(make_limiter("x", 1, 1, "postgres", None), RateLimiter)      # no store: stay safe
        self.assertIsInstance(make_limiter("x", 1, 1, "memory", object()), RateLimiter)
        self.assertIsInstance(make_limiter("x", 1, 1, "postgres", object()), SharedRateLimiter)

    def test_unconfigured_deployment_behaves_exactly_as_before(self):
        self.assertEqual(ratelimit.BACKEND, "memory")
        for lim in (ratelimit.LOGIN, ratelimit.MFA, ratelimit.REGISTER, ratelimit.RECOVERY_REQUEST, ratelimit.VERIFY_CONFIRM):
            self.assertIsInstance(lim, RateLimiter)
        self.assertEqual((ratelimit.LOGIN.limit, ratelimit.LOGIN.window), (20, 60))
        self.assertEqual((ratelimit.REGISTER.limit, ratelimit.REGISTER.window), (10, 600))

    def test_postgres_mode_is_opt_in_and_wired_to_the_engine(self):
        src = open(os.path.join(ROOT, "src", "asavexa", "api", "ratelimit.py")).read()
        self.assertIn('RATE_LIMIT_BACKEND", "memory"', src); self.assertIn("raw_connection", src)


class MigrationFileTests(unittest.TestCase):
    def test_up_is_one_additive_idempotent_table(self):
        text = "\n".join(l for l in open(UP).read().splitlines() if not l.strip().startswith("--")).upper()
        self.assertIn("CREATE TABLE IF NOT EXISTS RATE_LIMIT_HITS", text)
        for banned in ("DROP ", "DELETE ", "TRUNCATE", "ALTER ", "UPDATE ", "INSERT ", "CASCADE", "REFERENCES"):
            self.assertNotIn(banned, text)

    def test_up_twice_is_harmless_and_down_removes_it(self):
        d = tempfile.mkdtemp()
        try:
            db = os.path.join(d, "x.db"); create_table(db); create_table(db)
            c = sqlite3.connect(db); self.assertEqual(c.execute("select count(*) from sqlite_master where name='rate_limit_hits'").fetchone()[0], 1)
            c.execute(open(DOWN).read().split("\n")[-2].rstrip(";")); self.assertEqual(c.execute("select count(*) from sqlite_master where name='rate_limit_hits'").fetchone()[0], 0)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_revision_runs_only_its_own_sql(self):
        import types
        calls = []
        fake = types.ModuleType("alembic"); fake.op = types.SimpleNamespace(execute=calls.append)
        saved = sys.modules.get("alembic"); sys.modules["alembic"] = fake
        try:
            spec = importlib.util.spec_from_file_location("rev_c4d5", os.path.join(ROOT, "migrations", "versions", "c4d5e6f7a8b9_rate_limit_hits.py"))
            m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        finally:
            if saved is None: sys.modules.pop("alembic", None)
            else: sys.modules["alembic"] = saved
        self.assertEqual((m.revision, m.down_revision), ("c4d5e6f7a8b9", "b7c1d2e3f4a5"))
        m.upgrade(); self.assertTrue(all(c.startswith("CREATE ") and "IF NOT EXISTS" in c for c in calls)); self.assertEqual(len(calls), 2)
        calls.clear(); m.downgrade(); self.assertEqual(calls, ["DROP TABLE IF EXISTS rate_limit_hits"])

    def test_the_schema_check_does_not_make_the_optional_table_mandatory(self):
        from asavexa.api import schema_check
        self.assertNotIn("rate_limit_hits", schema_check.REQUIRED_TABLES)


@unittest.skipUnless(PG and shutil.which("psql"), "needs ASAVEXA_TEST_PG_URL and psql")
class RealPostgresRateLimit(unittest.TestCase):
    """The exact SQL the limiter sends, against real PostgreSQL."""
    @classmethod
    def setUpClass(cls):
        from test_stage1_migrations import _psql
        cls.q, cls.db = staticmethod(_psql), f"s9rl_{os.getpid()}"
        _psql(PG, "postgres", ["-c", f"DROP DATABASE IF EXISTS {cls.db}"]); _psql(PG, "postgres", ["-c", f"CREATE DATABASE {cls.db}"])

    @classmethod
    def tearDownClass(cls):
        cls.q(PG, "postgres", ["-c", f"DROP DATABASE IF EXISTS {cls.db}"])

    def test_migration_twice_upsert_counts_cleanup_and_downgrade(self):
        from asavexa.security.sharedlimit import CLEANUP, UPSERT
        q, db = self.q, self.db
        q(PG, db, [], path=UP); q(PG, db, [], path=UP)                                    # idempotent
        self.assertEqual(q(PG, db, ["-c", "select count(*) from information_schema.tables where table_name='rate_limit_hits'"]), "1")
        sql = UPSERT.format(p="%s").replace("%s", "{}")
        got = [q(PG, db, [], sql=sql.format("'login:1.2.3.4'", 100) + ";").split()[0] for _ in range(3)]
        self.assertEqual(got, ["1", "2", "3"])
        self.assertEqual(q(PG, db, [], sql=sql.format("'login:5.6.7.8'", 100) + ";").split()[0], "1")   # another key starts at 1
        self.assertEqual(q(PG, db, [], sql=sql.format("'login:1.2.3.4'", 160) + ";").split()[0], "1")   # new window starts at 1
        q(PG, db, ["-c", CLEANUP.format(p="150")])
        self.assertEqual(q(PG, db, ["-c", "select count(*) from rate_limit_hits"]), "1")
        q(PG, db, [], path=DOWN)
        self.assertEqual(q(PG, db, ["-c", "select count(*) from information_schema.tables where table_name='rate_limit_hits'"]), "0")


if __name__ == "__main__":
    unittest.main()
