"""The production preflight must be read-only, must never print the database URL, and must give the right advice."""
import importlib.util
import os
import re
import unittest

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "db_preflight.py")
SRC = open(PATH).read()
spec = importlib.util.spec_from_file_location("db_preflight", PATH); M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
BASE = ["t%d" % i for i in range(17)]


class Preflight(unittest.TestCase):
    def test_it_only_reads(self):
        sql = " ".join(re.findall(r'text\((?:f)?["\']([^"\']+)["\']', SRC)).upper()
        for banned in ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE", "GRANT"):
            self.assertNotRegex(sql, rf"\b{banned}\b")
        self.assertIn("SET TRANSACTION READ ONLY", SRC)
        self.assertNotIn(".commit(", SRC)

    def test_it_never_prints_the_connection_string(self):
        self.assertNotRegex(SRC, r"print\([^)]*\burl\b")
        self.assertNotRegex(SRC, r"f[\"'][^\"']*\{url")

    def test_advice(self):
        code, msg = M.advise(None, BASE, [])                       # empty database
        self.assertEqual(code, 0); self.assertIn("EMPTY", msg)
        code, msg = M.advise(None, [], [])                         # tables but no alembic_version
        self.assertEqual(code, 1); self.assertIn("alembic stamp 9ab0a651f090", msg)
        code, msg = M.advise("9ab0a651f090", [], ["security_docs"])
        self.assertEqual(code, 0); self.assertIn("b7c1d2e3f4a5", msg); self.assertIn("backup", msg)
        code, msg = M.advise("b7c1d2e3f4a5", [], [])
        self.assertEqual(code, 0)
        code, msg = M.advise("unknown", [], [])
        self.assertEqual(code, 1)
        code, msg = M.advise("9ab0a651f090", ["accounts"], [])
        self.assertEqual(code, 1)

    def test_revision_ids_match_the_migrations(self):
        self.assertTrue(os.path.exists(os.path.join(os.path.dirname(PATH), "..", "migrations", "versions", f"{M.HEAD}_late_tables.py")))
        self.assertTrue(os.path.exists(os.path.join(os.path.dirname(PATH), "..", "migrations", "versions", f"{M.INITIAL}_initial_schema.py")))


if __name__ == "__main__":
    unittest.main()
