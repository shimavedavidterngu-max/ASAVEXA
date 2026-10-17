"""Every router function may only use names that exist (parameters, locals, module names, builtins).
FastAPI is not needed: this reads the source, so a typo such as an undefined `status` is caught before it can fail on a live server."""
import builtins
import glob
import os
import symtable
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "src", "asavexa", "api", "routers")


def undefined(path):
    src = open(path).read(); top = symtable.symtable(src, path, "exec"); module = set(top.get_identifiers()); bad = []

    def walk(t):
        for ch in t.get_children():
            if ch.get_type() == "function":
                for s in ch.get_symbols():
                    if s.is_global() and s.is_referenced() and s.get_name() not in module and not hasattr(builtins, s.get_name()): bad.append((ch.get_name(), s.get_name()))
            walk(ch)
    walk(top); return bad


class RouterNames(unittest.TestCase):
    def test_no_router_uses_an_undefined_name(self):
        files = sorted(glob.glob(os.path.join(ROOT, "*.py"))); self.assertGreater(len(files), 20)
        for f in files: self.assertEqual(undefined(f), [], os.path.basename(f))

    def test_the_check_catches_the_bug_it_exists_for(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as t: t.write("def assets(org=None):\n    return list_it(org, status)\n")
        try: self.assertEqual(sorted(n for _, n in undefined(t.name)), ["list_it", "status"])
        finally: os.unlink(t.name)


if __name__ == "__main__":
    unittest.main()
