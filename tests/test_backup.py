"""Backup / restore. The database-backed tests run only when ASAVEXA_TEST_PG_URL points at a throwaway PostgreSQL server
(they create and drop databases named bk_src_* / bk_drill_*); everything else always runs."""
import os
import shutil
import subprocess
import tempfile
import unittest
import urllib.parse
from datetime import datetime, timedelta, timezone

from asavexa.security import backup, crypto
from asavexa.security.errors import ValidationError

PG = os.environ.get("ASAVEXA_TEST_PG_URL")
HAVE_TOOLS = bool(shutil.which("pg_dump") and shutil.which("pg_restore"))


def keys():
    return crypto.LocalKeyring({"k1": crypto.LocalKeyring.generate_key()}, "k1")


class PgEnv(unittest.TestCase):
    def test_parses_url_without_putting_password_in_argv(self):
        e = backup.pg_env("postgresql+psycopg://u%40x:p%2Fw@db.example:6543/asavexa?sslmode=require")
        self.assertEqual((e["PGHOST"], e["PGPORT"], e["PGUSER"], e["PGPASSWORD"], e["PGDATABASE"], e["PGSSLMODE"]),
                         ("db.example", "6543", "u@x", "p/w", "asavexa", "require"))

    def test_rejects_non_postgres(self):
        for bad in ("sqlite:///x.db", "postgresql://", "http://x/y", ""):
            with self.assertRaises(ValidationError):
                backup.pg_env(bad)

    def test_same_db_detection_and_status_without_backups(self):
        self.assertTrue(backup._same_db("postgresql://a:b@h:5432/d", "postgresql+psycopg://x:y@h/d"))
        self.assertFalse(backup._same_db("postgresql://a:b@h:5432/d", "postgresql://a:b@h:5432/e"))
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(backup.status(d)["ok"])

    def test_no_keys_no_backup(self):
        with self.assertRaises(ValidationError):
            backup.create_backup("postgresql://a:b@h/d", None, "/tmp/x")


@unittest.skipUnless(PG and HAVE_TOOLS, "needs ASAVEXA_TEST_PG_URL and the PostgreSQL client tools")
class RealPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        u = urllib.parse.urlparse(PG)
        cls.admin = backup.pg_env(PG)
        cls.src, cls.drill = f"bk_src_{os.getpid()}", f"bk_drill_{os.getpid()}"
        for db in (cls.src, cls.drill):
            cls.psql("postgres", f'DROP DATABASE IF EXISTS {db}'); cls.psql("postgres", f"CREATE DATABASE {db}")
        cls.url = staticmethod(lambda db: u._replace(path="/" + db).geturl())
        cls.psql(cls.src, "CREATE TABLE people(id int primary key, name text); INSERT INTO people VALUES (1,'Ada'),(2,'Bola');"
                          "CREATE TABLE ledger(id int primary key, amount numeric(12,2)); INSERT INTO ledger VALUES (1, 100.25),(2,-40.10);")
        cls.tmp = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        for db in (cls.src, cls.drill):
            cls.psql("postgres", f"DROP DATABASE IF EXISTS {db}")
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def psql(cls, db, sql):
        env = dict(os.environ, **cls.admin); env["PGDATABASE"] = db
        r = subprocess.run(["psql", "-v", "ON_ERROR_STOP=1", "-Atc", sql], env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        return r.stdout.strip()

    def test_backup_verify_restore_roundtrip_and_tamper_detection(self):
        k = keys()
        m = backup.create_backup(self.url(self.src), k, self.tmp)
        path = os.path.join(self.tmp, m["name"])
        raw = open(path, "rb").read()
        self.assertNotIn(b"Ada", raw); self.assertNotIn(b"PGDMP", raw)            # really encrypted
        self.assertEqual(backup.verify_backup(path, k)["tables_in_backup"], 2)
        # restore into the drill database and compare
        backup.restore_backup(path, k, self.url(self.drill), live_url=self.url(self.src))
        self.assertEqual(self.psql(self.drill, "SELECT count(*) FROM people"), "2")
        self.assertEqual(self.psql(self.drill, "SELECT sum(amount) FROM ledger"), "60.15")
        # refuses the live database
        with self.assertRaises(ValidationError):
            backup.restore_backup(path, k, self.url(self.src), live_url=self.url(self.src))
        # wrong keys
        with self.assertRaises(backup.BackupError):
            backup.verify_backup(path, keys())
        # a single flipped byte is caught by the checksum
        bad = bytearray(raw); bad[len(bad) // 2] ^= 1
        open(path, "wb").write(bytes(bad))
        with self.assertRaises(backup.BackupError) as c:
            backup.verify_backup(path, k)
        self.assertIn("checksum", str(c.exception))
        open(path, "wb").write(raw)
        self.assertEqual(backup.verify_backup(path, k)["ok"], True)

    def test_status_age_and_pruning_and_object_copy(self):
        from asavexa.security.objectstore import MemoryObjectStore
        k, d, objs = keys(), tempfile.mkdtemp(), MemoryObjectStore("EU")
        t0 = datetime.now(timezone.utc)
        for i in range(4):
            backup.create_backup(self.url(self.src), k, d, objects=objs, now=lambda i=i: t0 + timedelta(seconds=i), keep=2)
        self.assertEqual(len([f for f in os.listdir(d) if f.endswith(".dump.enc")]), 2)
        self.assertEqual(len([key for key in objs.objects if key.endswith(".dump.enc")]), 4)       # object copies are kept separately
        self.assertIn("system/backups/latest.json", objs.objects)
        self.assertTrue(backup.status(d, now=lambda: t0 + timedelta(hours=1))["ok"])
        self.assertFalse(backup.status(d, now=lambda: t0 + timedelta(hours=30))["ok"])
        shutil.rmtree(d)

    def test_failure_is_reported_not_hidden(self):
        with self.assertRaises(backup.BackupError):
            backup.create_backup(self.url("no_such_db"), keys(), tempfile.mkdtemp())


if __name__ == "__main__":
    unittest.main()
