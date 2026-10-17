"""Runs the REAL analysis router functions (fastapi stubbed) over the real accounting engine, evidence vault and analysis service on one SQLite connection.
Also checks, from the router source itself, which permission guards every endpoint carries."""
import ast, os, sys, types
import os as _os; _ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), ".."))   # works wherever the repository is checked out
sys.path.insert(0, _ROOT + "/src"); sys.path.insert(0, _ROOT + "/tests")
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
    m = types.ModuleType(pkg); m.__path__ = [_ROOT + "/src/asavexa/" + path]; sys.modules[pkg] = m
mod("asavexa.api.deps", **{n: (lambda: None) for n in ["get_forensic", "get_evidence_vault", "get_current_actor", "get_current_org"]}, require_permission=lambda p: ("perm", p))
import importlib, unittest
fr = importlib.import_module("asavexa.api.routers.forensic")
from analysis_fixture import ORG, OTHER, PREP, REVIEWER, World
from asavexa.forensic.service import ForensicService
from asavexa.forensic.errors import ForensicForbiddenError

ROUTER_SRC = _ROOT + "/src/asavexa/api/routers/forensic.py"


def guards():
    tree = ast.parse(open(ROUTER_SRC).read()); out = {}
    named = {"_prepare": "FORENSIC_PREPARE", "_approve": "FORENSIC_APPROVE"}
    for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef)]:
        g = set()
        for dec in fn.decorator_list:
            for kw in getattr(dec, "keywords", []):
                if kw.arg == "dependencies":
                    g |= {named[e.id] for e in kw.value.elts if isinstance(e, ast.Name) and e.id in named}
        out[fn.name] = g
    return out


class Run(unittest.TestCase):
    def setUp(self):
        self.w = World(); self.s = ForensicService(self.w.store, self.w.acc, self.w.vault)

    def test_guards(self):
        g = guards()
        prepare = {"create_case", "update_case", "add_evidence", "run_analytics", "create_finding", "update_finding", "discard_finding", "submit_finding", "create_report", "submit_report"}
        approve = {"close_case", "approve_finding", "reject_finding", "approve_report", "reject_report"}
        for n in prepare: self.assertEqual(g[n], {"FORENSIC_PREPARE"}, n)
        for n in approve: self.assertEqual(g[n], {"FORENSIC_APPROVE"}, n)
        reads = set(g) - prepare - approve
        self.assertTrue(reads >= {"options", "cases", "get_case", "verify_custody", "get_run", "get_report", "export_report"})
        for n in reads: self.assertEqual(g[n], set(), n)
        self.assertIn("dependencies=[Depends(require_permission(FORENSIC_READ))]", open(ROUTER_SRC).read())

    def test_full_flow_through_router_functions(self):
        c = fr.create_case(fr.CaseBody(title="Rent review", description="d", case_type="IRREGULARITY"), ORG, PREP, self.s)
        run = fr.run_analytics(c["id"], fr.RunBody(scope={"period_id": self.w.jan.id}, tests=["same_person", "weekend"]), ORG, PREP, self.s)
        self.assertEqual(run["journals_examined"], 8); self.assertEqual(fr.get_run(run["id"], ORG, self.s)["id"], run["id"])
        jid = self.w.acc.journals.list_for_org(ORG)[0].id
        f = fr.create_finding(c["id"], fr.FindingBody(title="Same person", description="The same user created and posted every January entry.", severity="MEDIUM", journal_ids=[jid], run_id=run["id"]), ORG, PREP, self.s)
        fr.submit_finding(f["id"], ORG, PREP, self.s)
        with self.assertRaises(ForensicForbiddenError): fr.approve_finding(f["id"], fr.NoteBody(), ORG, PREP, self.s)
        self.assertEqual(fr.approve_finding(f["id"], fr.NoteBody(note="ok"), ORG, REVIEWER, self.s)["status"], "APPROVED")
        r = fr.create_report(c["id"], fr.ReportBody(title="Report"), ORG, PREP, self.s); fr.submit_report(r["id"], ORG, PREP, self.s)
        fr.approve_report(r["id"], fr.NoteBody(), ORG, REVIEWER, self.s)
        resp = fr.export_report(r["id"], ORG, PREP, self.s)
        self.assertEqual(resp.media_type, "text/csv; charset=utf-8"); self.assertIn("attachment", resp.headers["Content-Disposition"]); self.assertEqual(resp.headers["Cache-Control"], "no-store")
        self.assertTrue(fr.verify_custody(c["id"], ORG, self.s)["ok"])
        self.assertEqual(fr.close_case(c["id"], fr.NoteBody(note="done"), ORG, REVIEWER, self.s)["status"], "CLOSED")
        self.assertEqual(fr.cases(OTHER, self.s), [])


if __name__ == "__main__":
    unittest.main()
