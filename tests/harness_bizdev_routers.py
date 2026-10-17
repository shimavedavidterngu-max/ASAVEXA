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
mod("asavexa.api.deps", **{n: (lambda: None) for n in ["get_bizdev", "get_evidence_vault", "get_current_actor", "get_current_org"]}, require_permission=lambda p: ("perm", p))
import importlib, unittest
fr = importlib.import_module("asavexa.api.routers.bizdev")
from analysis_fixture import ORG, OTHER, PREP, REVIEWER, World
from asavexa.bizdev.service import BizDevService
from asavexa.bizdev.errors import BizDevForbiddenError

ROUTER_SRC = _ROOT + "/src/asavexa/api/routers/bizdev.py"


def guards():
    tree = ast.parse(open(ROUTER_SRC).read()); out = {}
    named = {"_prepare": "BD_PREPARE", "_approve": "BD_APPROVE"}
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
        import datetime as dt
        self.w = World(); self.s = BizDevService(self.w.store, self.w.vault, now=lambda: dt.datetime(2026, 2, 15, 9, tzinfo=dt.timezone.utc))

    def test_guards(self):
        g = guards()
        approve = {"set_policy", "approve_win", "reject_win", "approve_proposal", "reject_proposal", "create_target", "retire_target", "approve_report", "reject_report"}
        prepare = {"create_account", "update_account", "archive_account", "create_opportunity", "update_opportunity", "add_activity", "move_stage", "mark_lost", "request_win", "create_proposal", "update_proposal",
                   "submit_proposal", "send_proposal", "accept_proposal", "decline_proposal", "create_report", "submit_report"}
        for n in prepare: self.assertEqual(g[n], {"BD_PREPARE"}, n)
        for n in approve: self.assertEqual(g[n], {"BD_APPROVE"}, n)
        reads = set(g) - prepare - approve - {"_d"}
        self.assertTrue(reads >= {"options", "overview", "accounts", "get_account", "opportunities", "get_opportunity", "targets", "reports", "get_report", "export_report"})
        for n in reads: self.assertEqual(g[n], set(), n)
        self.assertIn("dependencies=[Depends(require_permission(REPORTING_READ))]", open(ROUTER_SRC).read())

    def test_full_flow_through_router_functions(self):
        a = fr.create_account(fr.AccountBody(name="Meridian Textiles", kind="CLIENT", contacts=[{"name": "Ada N", "email": "ada@example.com"}]), ORG, PREP, self.s)
        self.assertEqual(fr.update_account(a["id"], fr.AccountBody(notes="Warm"), ORG, PREP, self.s)["name"], "Meridian Textiles")
        o = fr.create_opportunity(fr.OpportunityBody(account_id=a["id"], title="Audit retainer", currency="NGN", value="1000", expected_close="2026-04-30"), ORG, PREP, self.s)
        up = fr.update_opportunity(o["id"], fr.OpportunityBody(value="2000"), ORG, PREP, self.s); self.assertEqual((up["value"], up["title"]), ("2000.00", "Audit retainer"))
        fr.add_activity(o["id"], fr.ActivityBody(type="CALL", date="2026-02-10", summary="Intro call"), ORG, PREP, self.s)
        o = fr.create_proposal(o["id"], fr.ProposalBody(items=[{"description": "Audit", "quantity": "1", "unit_price": "2000"}], discount_pct="20", valid_until="2026-03-31"), ORG, PREP, self.s)
        pid = o["proposals"][0]["id"]; fr.submit_proposal(o["id"], pid, ORG, PREP, self.s)
        with self.assertRaises(BizDevForbiddenError): fr.approve_proposal(o["id"], pid, fr.NoteBody(), ORG, PREP, self.s)
        self.assertEqual(fr.approve_proposal(o["id"], pid, fr.NoteBody(), ORG, REVIEWER, self.s)["proposals"][0]["status"], "APPROVED")
        self.assertEqual(fr.send_proposal(o["id"], pid, ORG, PREP, self.s)["stage"], "PROPOSAL")
        self.assertEqual(fr.move_stage(o["id"], fr.StageBody(stage="NEGOTIATION"), ORG, PREP, self.s)["stage"], "NEGOTIATION")
        fr.accept_proposal(o["id"], pid, fr.NoteBody(note="Signed"), ORG, PREP, self.s); fr.request_win(o["id"], fr.NoteBody(), ORG, PREP, self.s)
        with self.assertRaises(BizDevForbiddenError): fr.approve_win(o["id"], fr.NoteBody(), ORG, PREP, self.s)
        w = fr.approve_win(o["id"], fr.NoteBody(), ORG, REVIEWER, self.s); self.assertEqual((w["stage"], w["value"]), ("WON", "1600.00"))
        t = fr.create_target(fr.TargetBody(name="Q1 goal", start="2026-01-01", end="2026-03-31", currency="NGN", amount="10000"), ORG, REVIEWER, self.s)
        self.assertEqual(fr.targets(ORG, self.s)[0]["won"], "1600.00"); fr.retire_target(t["id"], fr.NoteBody(note="Replaced"), ORG, REVIEWER, self.s)
        o2 = fr.create_opportunity(fr.OpportunityBody(account_id=a["id"], title="Second deal", currency="NGN", value="500", expected_close="2026-04-30"), ORG, PREP, self.s)
        self.assertEqual(fr.mark_lost(o2["id"], fr.NoteBody(note="Went with a competitor"), ORG, PREP, self.s)["stage"], "LOST")
        self.assertEqual(len(fr.opportunities("WON", None, ORG, self.s)), 1); self.assertEqual(fr.get_opportunity(o["id"], ORG, self.s)["ref"], "O-001")
        r = fr.create_report(fr.ReportBody(currency="NGN", title="Q1 pipeline"), ORG, PREP, self.s); fr.submit_report(r["id"], ORG, PREP, self.s)
        fr.approve_report(r["id"], fr.NoteBody(), ORG, REVIEWER, self.s)
        resp = fr.export_report(r["id"], ORG, PREP, self.s)
        self.assertEqual(resp.media_type, "text/csv; charset=utf-8"); self.assertIn("attachment", resp.headers["Content-Disposition"]); self.assertEqual(resp.headers["Cache-Control"], "no-store")
        self.assertEqual(fr.set_policy(fr.PolicyBody(discount_limit_pct="5", probabilities={"LEAD": 5}), ORG, REVIEWER, self.s)["discount_limit_pct"], "5.00")
        self.assertEqual(fr.overview(ORG, self.s)["counts"]["opportunities"], 2)
        self.assertEqual((fr.accounts(OTHER, self.s), fr.opportunities(None, None, OTHER, self.s), fr.targets(OTHER, self.s), fr.reports(OTHER, self.s)), ([], [], [], []))
        self.assertTrue(fr.options(ORG, self.s)["accounts"]); fr.archive_account(a["id"], fr.NoteBody(note="Done with them"), ORG, PREP, self.s)


if __name__ == "__main__":
    unittest.main()
