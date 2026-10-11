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
mod("asavexa.api.deps", **{n: (lambda: None) for n in ["get_grc", "get_evidence_vault", "get_current_actor", "get_current_org"]}, require_permission=lambda p: ("perm", p))
import importlib, unittest
fr = importlib.import_module("asavexa.api.routers.grc")
from analysis_fixture import ORG, OTHER, PREP, REVIEWER, World
from asavexa.grc.service import GrcService
from asavexa.grc.errors import GrcForbiddenError

ROUTER_SRC = "/home/claude/asavexa/src/asavexa/api/routers/grc.py"


def guards():
    tree = ast.parse(open(ROUTER_SRC).read()); out = {}
    named = {"_prepare": "GRC_PREPARE", "_approve": "GRC_APPROVE"}
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
        self.w = World(); self.s = GrcService(self.w.store, lambda org: [{"id": "c1", "code": "ACC-001", "name": "Balanced"}], self.w.vault)

    def test_guards(self):
        g = guards()
        prepare = {"create_risk", "update_risk", "treat", "accept", "reopen", "close", "create_action", "update_action", "complete_action", "cancel_action", "create_obligation", "update_obligation", "mark_met", "retire"}
        approve = {"set_appetite", "approve_acceptance", "reject_acceptance", "verify_action", "send_back_action"}
        for n in prepare: self.assertEqual(g[n], {"GRC_PREPARE"}, n)
        for n in approve: self.assertEqual(g[n], {"GRC_APPROVE"}, n)
        reads = set(g) - prepare - approve - {"_d"}
        self.assertTrue(reads >= {"options", "dashboard", "risks", "get_risk", "actions", "obligations", "get_obligation", "export"})
        for n in reads: self.assertEqual(g[n], set(), n)
        self.assertIn("dependencies=[Depends(require_permission(AUDIT_READ))]", open(ROUTER_SRC).read())

    def test_partial_update_sends_only_given_fields(self):
        r = fr.create_risk(fr.RiskBody(title="Cash theft", owner="Finance lead", category="FRAUD", inherent_l=4, inherent_i=4, next_review="2026-12-01", control_ids=["c1"]), ORG, PREP, self.s)
        u = fr.update_risk(r["id"], fr.RiskBody(owner="New owner"), ORG, PREP, self.s)
        self.assertEqual((u["owner"], u["title"], u["inherent_score"], u["controls"][0]["code"]), ("New owner", "Cash theft", 16, "ACC-001"))

    def test_full_flow_through_router_functions(self):
        r = fr.create_risk(fr.RiskBody(title="Cash theft", owner="Finance lead", category="FRAUD", inherent_l=4, inherent_i=4, next_review="2026-12-01"), ORG, PREP, self.s)
        fr.treat(r["id"], ORG, PREP, self.s)
        a = fr.create_action(fr.ActionBody(risk_id=r["id"], title="Install safe", owner="Ops", due="2099-01-01"), ORG, PREP, self.s)
        fr.complete_action(a["id"], fr.DoneBody(note="Installed and logged."), ORG, PREP, self.s)
        with self.assertRaises(GrcForbiddenError): fr.verify_action(a["id"], fr.NoteBody(), ORG, PREP, self.s)
        self.assertEqual(fr.verify_action(a["id"], fr.NoteBody(note="seen"), ORG, REVIEWER, self.s)["status"], "VERIFIED")
        p = fr.accept(r["id"], fr.AcceptBody(justification="Cost of control exceeds the loss expected.", review_by="2099-06-01"), ORG, PREP, self.s)
        self.assertEqual(p["status"], "ACCEPTANCE_REQUESTED")
        with self.assertRaises(GrcForbiddenError): fr.approve_acceptance(r["id"], fr.NoteBody(), ORG, PREP, self.s)
        self.assertEqual(fr.approve_acceptance(r["id"], fr.NoteBody(), ORG, REVIEWER, self.s)["status"], "ACCEPTED")
        o = fr.create_obligation(fr.ObligationBody(title="Annual return", source_type="LAW", authority="Registrar", description="File it.", owner="Secretary", frequency="ANNUAL", next_due="2026-01-01"), ORG, PREP, self.s)
        m = fr.mark_met(o["id"], fr.MetBody(met_on="2026-01-01", note="Filed online."), ORG, PREP, self.s)
        self.assertEqual(m["next_due"], "2027-01-01")
        self.assertEqual(fr.set_appetite(fr.AppetiteBody(appetite=12), ORG, REVIEWER, self.s)["appetite"], 12)
        self.assertEqual(fr.dashboard(ORG, self.s)["counts"]["risks"], 1)
        resp = fr.export(ORG, PREP, self.s)
        self.assertEqual(resp.media_type, "text/csv; charset=utf-8"); self.assertIn("attachment", resp.headers["Content-Disposition"]); self.assertEqual(resp.headers["Cache-Control"], "no-store")
        self.assertEqual((fr.risks(None, None, OTHER, self.s), fr.obligations(None, OTHER, self.s)), ([], []))
        self.assertEqual(fr.options(ORG, self.s)["controls"][0]["code"], "ACC-001")


if __name__ == "__main__":
    unittest.main()
