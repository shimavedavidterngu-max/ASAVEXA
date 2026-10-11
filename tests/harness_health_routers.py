"""Runs the REAL health router functions (fastapi stubbed) over the real service, and checks from the router source which permission guards every endpoint carries."""
import ast, sys, types
sys.path.insert(0, "/home/claude/asavexa/src"); sys.path.insert(0, "/home/claude/asavexa/tests")
def mod(name, **attrs):
    m = types.ModuleType(name); m.__dict__.update(attrs); sys.modules[name] = m; return m
class APIRouter:
    def __init__(self, **k): self.k = k
    def _d(self, *a, **k): return lambda f: f
    get = post = put = patch = delete = _d
class Response:
    def __init__(self, content=None, media_type=None, headers=None): self.content, self.media_type, self.headers = content, media_type, headers or {}
class HTTPException(Exception):
    def __init__(self, status_code, detail): self.status_code, self.detail = status_code, detail
mod("fastapi", APIRouter=APIRouter, Depends=lambda x=None: ("dep", x), Response=Response, HTTPException=HTTPException)
for pkg, path in [("asavexa.api", "api"), ("asavexa.api.routers", "api/routers"), ("asavexa.api.schemas", "api/schemas")]:
    m = types.ModuleType(pkg); m.__path__ = ["/home/claude/asavexa/src/asavexa/" + path]; sys.modules[pkg] = m
mod("asavexa.api.deps", **{n: (lambda: None) for n in ["get_health", "get_current_actor", "get_current_org"]}, require_permission=lambda p: ("perm", p))
import importlib, unittest
hr = importlib.import_module("asavexa.api.routers.health")
from analysis_fixture import ORG, World
from asavexa.health.service import HealthService
from asavexa.health.errors import HealthForbiddenError, HealthNotFoundError
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.permissions import ROLE_PERMISSIONS

SRC = "/home/claude/asavexa/src/asavexa/api/routers/health.py"
ALIAS = {"_prepare": {"PREPARE"}, "_approve": {"APPROVE"}, "_admin": {"ADMIN"}, "_claims": {"CLAIMS"}, "_claims_prepare": {"CLAIMS", "PREPARE"}, "_claims_approve": {"CLAIMS", "APPROVE"}, "_staff": {"STAFFING"}, "_staff_approve": {"STAFFING", "APPROVE"}}


def guards():
    tree = ast.parse(open(SRC).read()); out = {}
    for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef)]:
        g, method = set(), None
        for dec in fn.decorator_list:
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute): method = dec.func.attr
            for kw in getattr(dec, "keywords", []):
                if kw.arg == "dependencies" and isinstance(kw.value, ast.Name): g |= ALIAS[kw.value.id]
        out[fn.name] = (method, g)
    return out


ROLES = {"adm": Role.ADMINISTRATOR, "pre": Role.ACCOUNTANT, "mgr": Role.MANAGER, "fin": Role.FINANCE_OFFICER}


class Run(unittest.TestCase):
    def setUp(self):
        import datetime as dt
        self.w = World(); self.s = HealthService(self.w.store, self.w.vault, None, now=lambda: dt.datetime(2026, 2, 15, 9, tzinfo=dt.timezone.utc), can=lambda org, u, p: p in ROLE_PERMISSIONS[ROLES[u]])

    def test_every_write_is_guarded_and_sensitive_areas_need_their_own_permission(self):
        g = guards(); writes = {n for n, (m, _) in g.items() if m in ("post", "put")}
        self.assertGreater(len(writes), 60)
        for n in writes: self.assertTrue(g[n][1], f"{n} has no permission guard")
        for n in ("create_facility", "update_facility", "facility_status", "add_department", "department_active", "set_access", "get_access"): self.assertEqual(g[n][1], {"ADMIN"}, n)
        for n in ("approve_budget", "reject_budget", "decide_transfer", "decide_requisition", "approve_po", "verify_invoice", "approve_payment", "credit_note", "decide_adjustment", "decide_refund", "decide_retirement", "decide_report"):
            self.assertEqual(g[n][1], {"APPROVE"}, n)
        for n in ("claims", "get_claim", "receivables_ageing", "reconciliations"): self.assertEqual(g[n][1], {"CLAIMS"}, n)
        for n in ("create_claim", "submit_claim", "reject_claim", "resubmit_claim", "pay_claim", "request_writeoff", "reconcile_payer", "resolve_reconciliation"): self.assertEqual(g[n][1], {"CLAIMS", "PREPARE"}, n)
        self.assertEqual(g["decide_writeoff"][1], {"CLAIMS", "APPROVE"}); self.assertEqual(g["staffing"][1], {"STAFFING"}); self.assertEqual(g["record_staffing"][1], {"STAFFING"}); self.assertEqual(g["decide_staffing"][1], {"STAFFING", "APPROVE"})
        for n in ("dashboard", "budgets", "stock", "get_report", "export_report", "assets", "payables_ageing"): self.assertEqual(g[n][1], set(), n)
        self.assertIn("dependencies=[Depends(require_permission(HEALTH_READ))]", open(SRC).read())

    def test_flow_through_router_functions_and_facility_isolation(self):
        O = ORG
        f = hr.create_facility(dict(name="Ikoyi PHC", type="PRIMARY_HEALTH_CENTRE", ownership="PUBLIC", region="Lagos", currency="NGN"), O, "adm", self.s); fid = f["id"]
        d = hr.add_department(fid, dict(code="OPD", name="Outpatient"), O, "adm", self.s)
        f2 = hr.create_facility(dict(name="Other PHC", type="CLINIC", ownership="PRIVATE", region="Kano", currency="NGN"), O, "adm", self.s)
        hr.set_access("pre", dict(facility_ids=[fid]), O, "adm", self.s); hr.set_access("mgr", dict(facility_ids=[fid]), O, "adm", self.s)
        self.assertEqual([x["ref"] for x in hr.facilities(O, "pre", self.s)], ["F-001"]); self.assertEqual(len(hr.facilities(O, "adm", self.s)), 2)
        with self.assertRaises(HealthNotFoundError): hr.get_facility(f2["id"], O, "pre", self.s)
        b = hr.create_budget(fid, dict(name="2026", period_start="2026-01-01", period_end="2026-12-31", lines=[dict(dept_id=d["id"], category="MEDICAL_SUPPLIES", amount="100000")]), O, "pre", self.s)
        hr.submit_budget(b["id"], O, "pre", self.s)
        with self.assertRaises(HealthForbiddenError): hr.approve_budget(b["id"], O, "pre", self.s)
        self.assertEqual(hr.approve_budget(b["id"], O, "mgr", self.s)["status"], "APPROVED")
        sup = hr.create_supplier(fid, dict(name="MediSupply"), O, "pre", self.s)
        r = hr.create_requisition(fid, dict(dept_id=d["id"], category="MEDICAL_SUPPLIES", lines=[dict(description="Gloves", qty="10", unit_price="100")], justification="Restock"), O, "pre", self.s)
        hr.submit_requisition(r["id"], O, "pre", self.s); hr.decide_requisition(r["id"], dict(ok=True), O, "mgr", self.s)
        p = hr.create_po(r["id"], dict(supplier_id=sup["id"]), O, "pre", self.s); hr.approve_po(p["id"], dict(), O, "mgr", self.s)
        hr.receive_goods(p["id"], dict(lines=[dict(line_no=1, qty="10")], delivery_note="DN-1"), O, "pre", self.s)
        inv = hr.record_invoice(p["id"], dict(invoice_no="I-1", amount="1000", invoice_date="2026-02-10"), O, "pre", self.s); self.assertEqual(inv["status"], "MATCHED")
        dash = hr.dashboard(fid, None, None, O, "mgr", self.s)["metrics"]; self.assertEqual((dash["committed"]["value"], dash["claims_pending"]["state"]), ("1000.00", "OK"))
        self.assertEqual(hr.dashboard(fid, None, None, O, "adm", self.s)["metrics"]["claims_pending"]["state"], "RESTRICTED")
        rp = hr.create_report(fid, dict(title="Q1 performance", period_start="2026-01-01", period_end="2026-03-31"), O, "pre", self.s); hr.submit_report(rp["id"], O, "pre", self.s); hr.decide_report(rp["id"], dict(ok=True), O, "mgr", self.s)
        out = hr.export_report(rp["id"], O, "mgr", self.s); self.assertEqual(out.media_type, "text/csv; charset=utf-8"); self.assertIn("attachment", out.headers["Content-Disposition"]); self.assertTrue(out.content.startswith("CONFIDENTIAL"))
        with self.assertRaises(HTTPException): hr.dashboard(fid, "13/01/2026", None, O, "mgr", self.s)


if __name__ == "__main__":
    unittest.main()
