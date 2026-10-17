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
mod("asavexa.api.deps", **{n: (lambda: None) for n in ["get_cyber", "get_evidence_vault", "get_current_actor", "get_current_org"]}, require_permission=lambda p: ("perm", p))
import importlib, unittest
fr = importlib.import_module("asavexa.api.routers.cyber")
from analysis_fixture import ORG, OTHER, PREP, REVIEWER, World
from asavexa.cyber.service import CyberService
from asavexa.cyber.errors import CyberForbiddenError

ROUTER_SRC = _ROOT + "/src/asavexa/api/routers/cyber.py"


def guards():
    tree = ast.parse(open(ROUTER_SRC).read()); out = {}
    named = {"_prepare": "CYBER_PREPARE", "_approve": "CYBER_APPROVE"}
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
        self.w = World(); self.s = CyberService(self.w.store, self.w.vault, now=lambda: dt.datetime(2026, 2, 15, 9, tzinfo=dt.timezone.utc))

    def test_guards(self):
        g = guards()
        approve = {"set_policy", "verify_fix", "reject_fix", "approve_acceptance", "reject_acceptance", "close_incident", "reopen_incident", "approve_review", "reject_review", "approve_report", "reject_report"}
        prepare = {"create_asset", "update_asset", "retire_asset", "create_vulnerability", "start_vulnerability", "mark_fixed", "request_acceptance", "reopen_vulnerability", "create_incident", "add_timeline", "investigate_incident",
                   "contain_incident", "resolve_incident", "create_review", "add_entry", "decide_entry", "confirm_removed", "submit_review", "create_report", "submit_report"}
        for n in prepare: self.assertEqual(g[n], {"CYBER_PREPARE"}, n)
        for n in approve: self.assertEqual(g[n], {"CYBER_APPROVE"}, n)
        reads = set(g) - prepare - approve - {"_d"}
        self.assertTrue(reads >= {"options", "overview", "assets", "get_asset", "vulnerabilities", "get_vulnerability", "incidents", "get_incident", "reviews", "get_review", "reports", "get_report", "export_report"})
        for n in reads: self.assertEqual(g[n], set(), n)
        self.assertIn("dependencies=[Depends(require_permission(AUDIT_READ))]", open(ROUTER_SRC).read())

    def test_full_flow_through_router_functions(self):
        a = fr.create_asset(fr.AssetBody(name="Core server", type="SERVER", owner="IT", criticality="HIGH", data_class="CONFIDENTIAL"), ORG, PREP, self.s)
        self.assertEqual(fr.update_asset(a["id"], fr.AssetBody(location="Lagos"), ORG, PREP, self.s)["name"], "Core server")
        v = fr.create_vulnerability(fr.VulnBody(asset_id=a["id"], title="Old TLS library", severity="HIGH", source="Scan", found_date="2026-02-10"), ORG, PREP, self.s); self.assertEqual(v["due"], "2026-03-12")
        fr.start_vulnerability(v["id"], fr.NoteBody(), ORG, PREP, self.s); fr.mark_fixed(v["id"], fr.FixBody(note="Upgraded the library"), ORG, PREP, self.s)
        with self.assertRaises(CyberForbiddenError): fr.verify_fix(v["id"], fr.NoteBody(), ORG, PREP, self.s)
        self.assertEqual(fr.verify_fix(v["id"], fr.NoteBody(), ORG, REVIEWER, self.s)["status"], "VERIFIED")
        v2 = fr.create_vulnerability(fr.VulnBody(asset_id=a["id"], title="Weak cipher", severity="LOW", source="Scan"), ORG, PREP, self.s)
        fr.request_acceptance(v2["id"], fr.AcceptBody(reason="Vendor patch not available until March release.", until="2026-03-15"), ORG, PREP, self.s)
        self.assertEqual(fr.approve_acceptance(v2["id"], fr.NoteBody(), ORG, REVIEWER, self.s)["status"], "ACCEPTED"); self.assertEqual(fr.reopen_vulnerability(v2["id"], fr.NoteBody(note="Plan changed"), ORG, PREP, self.s)["status"], "OPEN")
        self.assertEqual(len(fr.vulnerabilities("OPEN", None, None, ORG, self.s)), 1); self.assertEqual(fr.get_vulnerability(v["id"], ORG, self.s)["ref"], "V-001")
        n = fr.create_incident(fr.IncidentBody(title="Phishing", description="User clicked a link", category="PHISHING", severity="HIGH", detected_date="2026-02-12", asset_ids=[a["id"]], personal_data_involved=True), ORG, PREP, self.s)
        fr.investigate_incident(n["id"], fr.NoteBody(), ORG, PREP, self.s); fr.add_timeline(n["id"], fr.TimelineBody(note="Mail logs pulled"), ORG, PREP, self.s)
        fr.contain_incident(n["id"], fr.NoteBody(note="Account disabled"), ORG, PREP, self.s); fr.resolve_incident(n["id"], fr.NoteBody(note="Credential harvesting page"), ORG, PREP, self.s)
        with self.assertRaises(CyberForbiddenError): fr.close_incident(n["id"], fr.CloseBody(lessons_learned="Train staff to report phishing early.", notification_decision="Regulator notified"), ORG, PREP, self.s)
        self.assertEqual(fr.close_incident(n["id"], fr.CloseBody(lessons_learned="Train staff to report phishing early.", notification_decision="Regulator notified on 20 Feb"), ORG, REVIEWER, self.s)["status"], "CLOSED")
        rv = fr.create_review(fr.ReviewBody(name="Q1 access", scope="Accounting system", due_date="2026-03-15"), ORG, PREP, self.s)
        rv = fr.add_entry(rv["id"], fr.EntryBody(subject="Temp contractor", system="Accounting", access="Posting"), ORG, PREP, self.s); eid = rv["entries"][0]["id"]
        fr.decide_entry(rv["id"], eid, fr.DecisionBody(decision="REMOVE", note="Contract ended"), ORG, PREP, self.s); fr.confirm_removed(rv["id"], eid, ORG, PREP, self.s); fr.submit_review(rv["id"], ORG, PREP, self.s)
        with self.assertRaises(CyberForbiddenError): fr.approve_review(rv["id"], fr.NoteBody(), ORG, PREP, self.s)
        self.assertEqual(fr.approve_review(rv["id"], fr.NoteBody(), ORG, REVIEWER, self.s)["status"], "COMPLETED"); self.assertEqual(fr.get_review(rv["id"], ORG, self.s)["ref"], "AR-001")
        r = fr.create_report(fr.ReportBody(title="Posture Feb"), ORG, PREP, self.s); fr.submit_report(r["id"], ORG, PREP, self.s); fr.approve_report(r["id"], fr.NoteBody(), ORG, REVIEWER, self.s)
        resp = fr.export_report(r["id"], ORG, PREP, self.s)
        self.assertEqual(resp.media_type, "text/csv; charset=utf-8"); self.assertIn("attachment", resp.headers["Content-Disposition"]); self.assertEqual(resp.headers["Cache-Control"], "no-store")
        self.assertEqual(fr.set_policy(fr.PolicyBody(sla_days={"CRITICAL": 3}, acceptance_max_days=60), ORG, REVIEWER, self.s)["acceptance_max_days"], 60)
        self.assertEqual(fr.overview(ORG, self.s)["counts"]["assets"], 1); self.assertEqual(len(fr.incidents(None, ORG, self.s)), 1); self.assertEqual(len(fr.reviews(ORG, self.s)), 1)
        self.assertEqual((fr.assets(OTHER, self.s), fr.vulnerabilities(None, None, None, OTHER, self.s), fr.incidents(None, OTHER, self.s), fr.reviews(OTHER, self.s), fr.reports(OTHER, self.s)), ([], [], [], [], []))
        self.assertTrue(fr.options(ORG, self.s)["assets"])


if __name__ == "__main__":
    unittest.main()
