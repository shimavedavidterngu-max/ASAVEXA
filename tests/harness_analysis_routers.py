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
mod("asavexa.api.deps", **{n: (lambda: None) for n in ["get_analysis", "get_current_actor", "get_current_org", "get_evidence_vault"]}, require_permission=lambda p: ("perm", p))
import importlib, unittest
ar = importlib.import_module("asavexa.api.routers.analysis")
from analysis_fixture import ORG, OTHER, PREP, REVIEWER, TAGS, World
from asavexa.analysis.errors import AnalysisForbiddenError, AnalysisStateError
from asavexa.evidence.domain.enums import EvidenceType

ROUTER_SRC = _ROOT + "/src/asavexa/api/routers/analysis.py"


def guards():
    """endpoint function name -> set of permission names guarding it (router-wide guard included)."""
    tree = ast.parse(open(ROUTER_SRC).read()); out = {}
    named = {"_prepare": "ANALYSIS_PREPARE", "_approve": "ANALYSIS_APPROVE"}
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
        self.w = World(); self.w.classify(); self.s = self.w.svc

    def test_every_write_needs_prepare_and_every_decision_needs_approve(self):
        g = guards()
        writes = {"set_config", "set_budget", "add_comment", "save_scenario", "update_scenario", "create_report", "update_report", "submit_report"}
        decisions = {"approve_report", "reject_report"}
        for name in writes: self.assertEqual(g[name], {"ANALYSIS_PREPARE"}, name)
        for name in decisions: self.assertEqual(g[name], {"ANALYSIS_APPROVE"}, name)
        reads = {n for n in g if n not in writes | decisions}
        self.assertTrue(reads >= {"overview", "ratios", "variance", "get_report", "verify_report", "export_report", "breakeven", "reports"})
        for name in reads: self.assertEqual(g[name], set(), name)      # reads rely on the router-wide reporting:read guard
        src = open(ROUTER_SRC).read(); self.assertIn("dependencies=[Depends(require_permission(REPORTING_READ))]", src)

    def test_a_complete_report_through_the_router_functions(self):
        ev = self.w.vault.upload_evidence(ORG, EvidenceType.BANK_STATEMENT if hasattr(EvidenceType, "BANK_STATEMENT") else list(EvidenceType)[0], b"statement", "bank.pdf", "application/pdf", uploaded_by=PREP)
        sc = ar.save_scenario(ar.ScenarioBody(name="Base", base_period_id=self.w.feb.id, assumptions={"months": 3, "base_monthly_revenue": "10000", "base_monthly_expenses": "8000", "revenue_growth_pct": "10", "expense_growth_pct": "0", "opening_cash": "5000"}), ORG, PREP, self.s)
        r = ar.create_report(ar.ReportBody(period_id=self.w.feb.id, title="February analysis", note="n", scenario_ids=[sc["id"]], evidence_ids=[ev.id, ev.id]), ORG, PREP, self.s, self.w.vault)
        self.assertEqual(len(r["evidence"]), 1); self.assertEqual(r["evidence"][0]["filename"], "bank.pdf"); self.assertEqual(r["evidence"][0]["file_hash"], ev.file_hash)
        ar.submit_report(r["id"], ORG, PREP, self.s)
        with self.assertRaises(AnalysisForbiddenError): ar.approve_report(r["id"], ar.NoteBody(note="ok"), ORG, PREP, self.s)
        a = ar.approve_report(r["id"], ar.NoteBody(note="Reviewed"), ORG, REVIEWER, self.s); self.assertEqual(a["status"], "APPROVED")
        v = ar.verify_report(r["id"], ORG, self.s); self.assertTrue(v["integrity_ok"] and v["matches_ledger_now"])
        resp = ar.export_report(r["id"], ORG, REVIEWER, self.s)
        self.assertEqual(resp.media_type, "text/csv; charset=utf-8"); self.assertIn("attachment; filename=", resp.headers["Content-Disposition"]); self.assertEqual(resp.headers["Cache-Control"], "no-store"); self.assertIn("CONFIDENTIAL", resp.content)

    def test_evidence_must_exist_in_this_organisation(self):
        other_ev = self.w.vault.upload_evidence(OTHER, list(EvidenceType)[0], b"secret", "other.pdf", "application/pdf", uploaded_by="x")
        with self.assertRaises(Exception) as cm: ar.create_report(ar.ReportBody(period_id=self.w.feb.id, title="Stolen ref", evidence_ids=[other_ev.id]), ORG, PREP, self.s, self.w.vault)
        self.assertNotIn("secret", str(cm.exception)); self.assertEqual(self.s.list_reports(ORG), [])

    def test_export_before_approval_is_refused(self):
        r = ar.create_report(ar.ReportBody(period_id=self.w.feb.id, title="Not yet"), ORG, PREP, self.s, self.w.vault)
        with self.assertRaises(AnalysisStateError): ar.export_report(r["id"], ORG, PREP, self.s)

    def test_breakeven_and_overview_endpoints(self):
        b = ar.breakeven(ar.BreakevenBody(fixed_costs="10000", price="25", variable_cost="15"), self.s); self.assertEqual(b["break_even_units"], "1000")
        o = ar.overview(self.w.jan.id, ORG, self.s)
        self.assertEqual(o["totals"]["net_income"], "6500.00"); self.assertTrue(any("not closed" in i or "open" in i for i in o["issues"]))


if __name__ == "__main__":
    unittest.main()
