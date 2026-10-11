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
mod("asavexa.api.deps", **{n: (lambda: None) for n in ["get_pubfin", "get_evidence_vault", "get_current_actor", "get_current_org"]}, require_permission=lambda p: ("perm", p))
import importlib, unittest
fr = importlib.import_module("asavexa.api.routers.pubfin")
from analysis_fixture import ORG, OTHER, PREP, REVIEWER, World
from asavexa.pubfin.service import PubFinService
from asavexa.pubfin.errors import PubFinForbiddenError

ROUTER_SRC = "/home/claude/asavexa/src/asavexa/api/routers/pubfin.py"


def guards():
    tree = ast.parse(open(ROUTER_SRC).read()); out = {}
    named = {"_prepare": "PUBFIN_PREPARE", "_approve": "PUBFIN_APPROVE"}
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
        self.w = World(); self.s = PubFinService(self.w.store, self.w.acc, self.w.vault, now=lambda: __import__('datetime').datetime(2026, 2, 15, 9, tzinfo=__import__('datetime').timezone.utc)); self.a = self.w.a

    def test_guards(self):
        g = guards()
        approve = {"set_policy", "approve_budget", "reject_budget", "approve_virement", "reject_virement", "approve_award", "reject_award", "approve_spend", "reject_spend", "approve_report", "reject_report"}
        prepare = {"create_budget", "update_budget", "discard_budget", "submit_budget", "close_budget", "propose_virement", "create_commitment", "settle_commitment", "cancel_commitment", "create_procurement",
                   "add_quote", "propose_award", "cancel_procurement", "create_grant", "record_receipt", "add_spend", "close_grant", "create_report", "submit_report"}
        for n in prepare: self.assertEqual(g[n], {"PUBFIN_PREPARE"}, n)
        for n in approve: self.assertEqual(g[n], {"PUBFIN_APPROVE"}, n)
        reads = set(g) - prepare - approve - {"_d"}
        self.assertTrue(reads >= {"options", "overview", "budgets", "get_budget", "commitments", "procurements", "get_procurement", "grants", "get_grant", "reports", "get_report", "export_report"})
        for n in reads: self.assertEqual(g[n], set(), n)
        self.assertIn("dependencies=[Depends(require_permission(REPORTING_READ))]", open(ROUTER_SRC).read())

    def test_full_flow_through_router_functions(self):
        lines = [{"account_id": self.a["5100"].id, "amount": "5000"}, {"account_id": self.a["5000"].id, "amount": "20000"}]
        b = fr.create_budget(fr.BudgetBody(name="Operations", start="2026-01-01", end="2026-02-28", currency="USD", lines=lines), ORG, PREP, self.s)
        up = fr.update_budget(b["id"], fr.BudgetBody(name="Operations H1"), ORG, PREP, self.s)
        self.assertEqual((up["name"], len(up["lines"])), ("Operations H1", 2))
        fr.submit_budget(b["id"], ORG, PREP, self.s)
        with self.assertRaises(PubFinForbiddenError): fr.approve_budget(b["id"], fr.NoteBody(), ORG, PREP, self.s)
        self.assertEqual(fr.approve_budget(b["id"], fr.NoteBody(), ORG, REVIEWER, self.s)["status"], "APPROVED")
        c = fr.create_commitment(fr.CommitmentBody(budget_id=b["id"], account_id=self.a["5100"].id, vendor="Landlord", description="Rent", amount="100", date="2026-02-10"), ORG, PREP, self.s)
        self.assertEqual(fr.get_budget(b["id"], ORG, self.s)["execution"]["expense_totals"]["committed"], "100.00")
        fr.settle_commitment(c["id"], fr.SettleBody(settled_amount="100", note="Posted as JE-1"), ORG, PREP, self.s)
        p = fr.create_procurement(fr.ProcurementBody(budget_id=b["id"], account_id=self.a["5100"].id, title="Office", estimate="400"), ORG, PREP, self.s)
        for i, amt in enumerate(("300", "350", "400")): p = fr.add_quote(p["id"], fr.QuoteBody(vendor=f"Vendor {i}", amount=amt), ORG, PREP, self.s)
        fr.propose_award(p["id"], fr.AwardBody(quote_id=p["quotes"][0]["id"]), ORG, PREP, self.s)
        self.assertEqual(fr.approve_award(p["id"], fr.NoteBody(), ORG, REVIEWER, self.s)["status"], "AWARDED")
        v = fr.propose_virement(b["id"], fr.VirementBody(from_account=self.a["5000"].id, to_account=self.a["5100"].id, amount="100", reason="Rent rose recently"), ORG, PREP, self.s)
        fr.approve_virement(b["id"], v["virements"][0]["id"], fr.NoteBody(), ORG, REVIEWER, self.s)
        g = fr.create_grant(fr.GrantBody(title="Water", donor="Fund", amount="1000", currency="USD", start="2026-01-01", end="2026-12-31"), ORG, PREP, self.s)
        fr.record_receipt(g["id"], fr.ReceiptBody(amount="500", date="2026-01-05", reference="BANK-1"), ORG, PREP, self.s)
        g = fr.add_spend(g["id"], fr.SpendBody(amount="200", date="2026-02-01", description="Pump"), ORG, PREP, self.s)
        self.assertEqual(fr.approve_spend(g["id"], g["spend"][0]["id"], fr.NoteBody(), ORG, REVIEWER, self.s)["spent"], "200.00")
        r = fr.create_report(fr.ReportBody(budget_id=b["id"], title="H1 report"), ORG, PREP, self.s); fr.submit_report(r["id"], ORG, PREP, self.s)
        fr.approve_report(r["id"], fr.NoteBody(), ORG, REVIEWER, self.s)
        resp = fr.export_report(r["id"], ORG, PREP, self.s)
        self.assertEqual(resp.media_type, "text/csv; charset=utf-8"); self.assertIn("attachment", resp.headers["Content-Disposition"]); self.assertEqual(resp.headers["Cache-Control"], "no-store")
        self.assertEqual(fr.set_policy(fr.PolicyBody(min_quotes=2, quote_threshold="100"), ORG, REVIEWER, self.s)["min_quotes"], 2)
        self.assertEqual(fr.overview(ORG, self.s)["counts"]["grants_active"], 1)
        self.assertEqual((fr.budgets(OTHER, self.s), fr.grants(OTHER, self.s), fr.commitments(None, None, OTHER, self.s)), ([], [], []))
        self.assertTrue(fr.options(ORG, self.s)["accounts"])


if __name__ == "__main__":
    unittest.main()
