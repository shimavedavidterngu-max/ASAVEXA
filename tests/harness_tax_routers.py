"""Runs the REAL analysis router functions (fastapi stubbed) over the real accounting engine, evidence vault and analysis service on one SQLite connection.
Also checks, from the router source itself, which permission guards every endpoint carries."""
import ast, os, sys, types
sys.path.insert(0, "/home/claude/asavexa/src"); sys.path.insert(0, "/home/claude/asavexa/tests")
def mod(name, **attrs):
    m = types.ModuleType(name); m.__dict__.update(attrs); sys.modules[name] = m; return m
class APIRouter:
    def __init__(self, **k): self.k = k
    def _d(self, *a, **k): return lambda f: f
    get = post = put = patch = delete = _d
class Response:
    def __init__(self, content=None, media_type=None, headers=None): self.content, self.media_type, self.headers = content, media_type, headers or {}
mod("fastapi", APIRouter=APIRouter, Depends=lambda x=None: ("dep", x), Response=Response)
import asavexa
for pkg, path in [("asavexa.api", "api"), ("asavexa.api.routers", "api/routers"), ("asavexa.api.schemas", "api/schemas")]:
    m = types.ModuleType(pkg); m.__path__ = ["/home/claude/asavexa/src/asavexa/" + path]; sys.modules[pkg] = m
mod("asavexa.api.deps", **{n: (lambda: None) for n in ["get_tax", "get_current_actor", "get_current_org"]}, require_permission=lambda p: ("perm", p))
import importlib, unittest
tr = importlib.import_module("asavexa.api.routers.tax")
from analysis_fixture import ORG, OTHER, PREP, REVIEWER, World
from asavexa.tax.service import TaxService
from asavexa.tax.errors import TaxForbiddenError

ROUTER_SRC = "/home/claude/asavexa/src/asavexa/api/routers/tax.py"


def guards():
    tree = ast.parse(open(ROUTER_SRC).read()); out = {}
    named = {"_prepare": "TAX_PREPARE", "_approve": "TAX_APPROVE"}
    for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef)]:
        g = set()
        for dec in fn.decorator_list:
            for kw in getattr(dec, "keywords", []):
                if kw.arg == "dependencies":
                    g |= {named[e.id] for e in kw.value.elts if isinstance(e, ast.Name) and e.id in named}
        out[fn.name] = g
    return out


RULE = dict(country="NG", tax_type="VAT_GST", name="Test VAT", method="FLAT", rate="7.5", effective_from="2026-01-01", authority="Test Authority", source_title="Test Act s5", source_url="https://example.org/a")


class Run(unittest.TestCase):
    def setUp(self):
        self.w = World(); self.s = TaxService(self.w.store, self.w.acc)

    def test_guards(self):
        g = guards()
        writes = {"set_country", "create_rule", "update_rule", "discard_rule", "submit_rule", "calculate", "mark_filed"}
        for n in writes: self.assertEqual(g[n], {"TAX_PREPARE"}, n)
        for n in ("approve_rule", "reject_rule"): self.assertEqual(g[n], {"TAX_APPROVE"}, n)
        reads = set(g) - writes - {"approve_rule", "reject_rule"}
        self.assertTrue(reads >= {"overview", "countries", "options", "rules", "get_rule", "ledger_base", "calculations", "calendar"})
        for n in reads: self.assertEqual(g[n], set(), n)
        self.assertIn("dependencies=[Depends(require_permission(REPORTING_READ))]", open(ROUTER_SRC).read())

    def test_full_flow_through_router_functions(self):
        r = tr.create_rule(tr.RuleBody(**RULE), ORG, PREP, self.s)
        tr.submit_rule(r["id"], ORG, PREP, self.s)
        with self.assertRaises(TaxForbiddenError): tr.approve_rule(r["id"], tr.NoteBody(note=""), ORG, PREP, self.s)
        a = tr.approve_rule(r["id"], tr.NoteBody(note="ok"), ORG, REVIEWER, self.s)
        self.assertEqual(a["status"], "APPROVED")
        c = tr.calculate(tr.CalcBody(rule_id=r["id"], amount="200", date="2026-02-02", inclusive=False), ORG, PREP, self.s)
        self.assertEqual(c["tax"], "15.00")
        self.assertEqual(len(tr.calculations(ORG, self.s)), 1)
        self.assertEqual(tr.rules(country="NG", status=None, org=ORG, svc=self.s)[0]["id"], r["id"])
        self.assertEqual(tr.rules(country=None, status=None, org=OTHER, svc=self.s), [])
        self.assertEqual(tr.countries(q="ken", region="", org=ORG, svc=self.s)["countries"][0]["code"], "KE")
        tr.set_country("NG", tr.CountryBody(selected=True, registration="T1"), ORG, PREP, self.s)
        self.assertEqual(tr.overview(ORG, self.s)["selected"], 1)

    def test_replacement_passes_through(self):
        r = tr.create_rule(tr.RuleBody(**RULE), ORG, PREP, self.s); tr.submit_rule(r["id"], ORG, PREP, self.s); tr.approve_rule(r["id"], tr.NoteBody(), ORG, REVIEWER, self.s)
        n = tr.create_rule(tr.RuleBody(**{**RULE, "rate": "8", "effective_from": "2026-06-01", "replaces": r["id"]}), ORG, PREP, self.s)
        self.assertEqual(n["replaces"], r["id"])


if __name__ == "__main__":
    unittest.main()
