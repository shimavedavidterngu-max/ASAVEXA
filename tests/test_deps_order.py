"""A FastAPI dependency function's `Depends(...)` defaults are evaluated when the `def` runs, so every function they name must already exist.
A violation crashes the server at start-up (NameError) yet passes every test that stubs FastAPI, so it is checked here by reading the source."""
import ast
import glob
import os
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "src", "asavexa", "api")


class DependencyOrder(unittest.TestCase):
    def test_no_default_uses_a_name_defined_later(self):
        problems = []
        for path in glob.glob(os.path.join(ROOT, "**", "*.py"), recursive=True):
            with open(path) as fh: tree = ast.parse(fh.read())
            defined = {}
            for n in tree.body:
                if isinstance(n, (ast.FunctionDef, ast.ClassDef)): defined[n.name] = n.lineno
                elif isinstance(n, ast.Assign):
                    for t in n.targets:
                        if isinstance(t, ast.Name): defined[t.id] = n.lineno
            for n in tree.body:
                if not isinstance(n, ast.FunctionDef): continue
                for d in n.args.defaults + [k for k in n.args.kw_defaults if k]:
                    for c in ast.walk(d):
                        if isinstance(c, ast.Name) and defined.get(c.id, 0) > n.lineno:
                            problems.append(f"{os.path.relpath(path, ROOT)}: {n.name} (line {n.lineno}) uses {c.id}, defined at line {defined[c.id]}")
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
