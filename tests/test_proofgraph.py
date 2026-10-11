"""Proof-to-Report Graph and architecture check, over the real accounting, evidence and reporting services on one SQLite connection."""
import os, re, unittest
from datetime import date
from decimal import Decimal

from asavexa.accounting.domain.enums import AccountType
from asavexa.accounting.repository.sqlite_repository import SqliteAccountRepository, SqliteJournalRepository, SqlitePeriodRepository
from asavexa.accounting.services.engine import AccountingEngine, LineInput
from asavexa.audit.sqlite_repository import SqliteAuditRepository
from asavexa.bootstrap import create_sqlite_connection
from asavexa.evidence.domain.enums import EvidenceType
from asavexa.evidence.repository.sqlite_repository import SqliteEvidenceRepository
from asavexa.evidence.services.vault import EvidenceVault
from asavexa.proofgraph import architecture as arch
from asavexa.proofgraph import graph as pg
from asavexa.reporting.domain.errors import ReportingPeriodNotFoundError
from asavexa.reporting.services.service import ReportingService

ROUTERS = os.path.join(os.path.dirname(__file__), "..", "src", "asavexa", "api", "routers")
ORG, OTHER, ME = "org-a", "org-b", "tester"


class Base(unittest.TestCase):
    def setUp(self):
        self.conn = create_sqlite_connection(":memory:")
        audit = SqliteAuditRepository(self.conn)
        self.acc = AccountingEngine(accounts=SqliteAccountRepository(self.conn), periods=SqlitePeriodRepository(self.conn), journals=SqliteJournalRepository(self.conn), audit=audit)
        self.vault = EvidenceVault(evidence=SqliteEvidenceRepository(self.conn), audit=audit)
        self.rep = ReportingService(accounting=self.acc, audit=audit, evidence=self.vault)
        self.cash = self.acc.create_account(ORG, "1000", "Cash", AccountType.ASSET, actor=ME)
        self.cap = self.acc.create_account(ORG, "3000", "Capital", AccountType.EQUITY, actor=ME)
        self.rev = self.acc.create_account(ORG, "4000", "Sales", AccountType.REVENUE, actor=ME)
        self.period = self.acc.open_period(ORG, "P1", date(2026, 1, 1), date(2026, 1, 31), actor=ME)
        self.empty = self.acc.open_period(ORG, "P2", date(2026, 2, 1), date(2026, 2, 28), actor=ME)
        self.invest = self.post(date(2026, 1, 2), "Owner investment", self.cash, self.cap, "1000.00")
        self.sale = self.post(date(2026, 1, 5), "Cash sale", self.cash, self.rev, "500.00")

    def post(self, d, text, debit_acc, credit_acc, amount):
        j = self.acc.create_draft_journal(ORG, d, text, "USD", [LineInput(debit_acc.id, debit_amount=Decimal(amount)), LineInput(credit_acc.id, credit_amount=Decimal(amount))], created_by=ME)
        return self.acc.post_journal(ORG, j.id, actor=ME)

    def attach(self, journal, verify=False):
        r = self.vault.upload_evidence(ORG, EvidenceType.INVOICE, f"doc for {journal.id}".encode(), "doc.pdf", "application/pdf", uploaded_by=ME, linked_journal_id=journal.id)
        if verify:
            self.vault.verify_evidence(ORG, r.id, ME)
        return r

    def graph(self, report="balance_sheet", period=None):
        return pg.build_graph(self.rep, ORG, (period or self.period).id, report, ME)


class Graph(Base):
    def test_without_any_evidence_every_journal_is_listed_as_missing(self):
        g = self.graph("income_statement")
        self.assertEqual(g["state"], pg.PARTIAL); self.assertEqual(g["summary"]["journals"], 1); self.assertEqual(g["summary"]["missing_evidence"], 1)
        self.assertEqual(g["missing"][0]["journal_id"], self.sale.id)
        self.assertEqual(g["summary"]["coverage_pct"], 0.0)

    def test_unverified_evidence_counts_as_present_but_not_proven(self):
        self.attach(self.sale)
        g = self.graph("income_statement")
        self.assertEqual(g["state"], pg.PARTIAL); self.assertEqual(g["summary"]["with_evidence"], 1); self.assertEqual(g["summary"]["verified"], 0)
        self.assertEqual(g["unverified"][0]["status"], "UPLOADED")

    def test_verified_evidence_on_every_journal_gives_proven(self):
        self.attach(self.sale, verify=True)
        g = self.graph("income_statement")
        self.assertEqual(g["state"], pg.PROVEN); self.assertEqual(g["summary"]["verified_pct"], 100.0)
        self.assertTrue(all(c["ok"] for c in g["checks"]))
        kinds = {n["kind"] for n in g["nodes"]}; self.assertEqual(kinds, {"report", "line", "journal", "evidence"})
        by = {n["id"]: n for n in g["nodes"]}
        for e in g["edges"]: self.assertIn(e["from"], by); self.assertIn(e["to"], by)           # no dangling edge

    def test_balance_sheet_shares_one_journal_node_across_lines_and_lists_the_gap(self):
        self.attach(self.sale, verify=True)
        g = self.graph("balance_sheet")
        self.assertEqual(g["state"], pg.PARTIAL)
        self.assertEqual([m["journal_id"] for m in g["missing"]], [self.invest.id])
        ids = [n["id"] for n in g["nodes"] if n["kind"] == "journal"]; self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(g["summary"]["journals"], 2)

    def test_line_amounts_come_from_the_report_and_match_the_ledger(self):
        g = self.graph("balance_sheet")
        amounts = {n["label"]: n["amount"] for n in g["nodes"] if n["kind"] == "line"}
        self.assertEqual(amounts["1000 Cash"], "1500.00"); self.assertEqual(amounts["3000 Capital"], "1000.00")
        self.assertEqual(g["summary"]["tie_failures"], 0)

    def test_a_figure_that_does_not_tie_is_reported_broken(self):
        real = self.rep.trace_line
        self.rep.trace_line = lambda org, acc, period_id=None: real(org, acc, period_id=period_id)[:-1] if acc == self.cash.id else real(org, acc, period_id=period_id)
        g = self.graph("balance_sheet")
        self.assertEqual(g["state"], pg.BROKEN); self.assertEqual(g["summary"]["tie_failures"], 1)
        bad = [c for c in g["checks"] if not c["ok"]]; self.assertEqual(len(bad), 1); self.assertIn("1000", bad[0]["name"])

    def test_empty_period(self):
        g = self.graph("balance_sheet", period=self.empty)
        self.assertEqual(g["state"], pg.EMPTY); self.assertIsNone(g["summary"]["coverage_pct"])

    def test_truncation_is_flagged_and_never_proven(self):
        self.attach(self.sale, verify=True); self.attach(self.invest, verify=True)
        old = pg.MAX_JOURNAL_NODES; pg.MAX_JOURNAL_NODES = 1
        try: g = self.graph("balance_sheet")
        finally: pg.MAX_JOURNAL_NODES = old
        self.assertTrue(g["summary"]["truncated"]); self.assertNotEqual(g["state"], pg.PROVEN); self.assertEqual(g["summary"]["journals"], 1)
        self.assertTrue(any(c["name"] == "graph size" and not c["ok"] for c in g["checks"]))

    def test_unknown_report_and_other_organisation(self):
        with self.assertRaises(pg.UnknownReportError): self.graph("cash_flow")
        with self.assertRaises(ReportingPeriodNotFoundError): pg.build_graph(self.rep, OTHER, self.period.id, "balance_sheet", ME)

    def test_building_the_graph_never_changes_the_books(self):
        before = self.acc.get_trial_balance(ORG, self.period.id); n = len(self.acc.journals.list_for_org(ORG))
        self.graph("balance_sheet"); self.graph("income_statement")
        self.assertEqual(self.acc.get_trial_balance(ORG, self.period.id), before); self.assertEqual(len(self.acc.journals.list_for_org(ORG)), n)

    def test_works_without_an_evidence_vault(self):
        rep = ReportingService(accounting=self.acc, audit=SqliteAuditRepository(self.conn))
        g = pg.build_graph(rep, ORG, self.period.id, "income_statement", ME)
        self.assertEqual(g["summary"]["missing_evidence"], 1); self.assertEqual(g["state"], pg.PARTIAL)


def router_paths():
    out = []
    for f in os.listdir(ROUTERS):
        if f.endswith(".py"):
            out += re.findall(r'prefix="(/[^"]*)"', open(os.path.join(ROUTERS, f)).read())
    return out


class Architecture(unittest.TestCase):
    def test_every_layer_loads_and_is_mounted_in_the_real_code(self):
        paths = router_paths(); self.assertIn("/proof", paths)
        r = arch.check_architecture(paths)
        self.assertEqual([l["problems"] for l in r["layers"] if not l["ok"]], []); self.assertTrue(r["ok"])
        self.assertEqual(len(r["layers"]), 10); self.assertTrue(all(f["ok"] for f in r["flows"]))

    def test_the_diagram_is_fully_covered(self):
        names = {l["name"] for l in arch.LAYERS}
        for n in ("Financial Core", "Evidence Layer", "Identity", "Standards Engine", "Reporting Engine", "Proof-to-Report Graph", "Audit", "Passport", "AI", "Trust Network"): self.assertIn(n, names)
        parts = {p for l in arch.LAYERS for p in l["parts"]}
        for p in ("IFRS", "IFRS for SMEs", "US GAAP", "IPSAS", "Local GAAP", "Banks", "Investors", "Auditors", "Donors", "Regulators", "Journals", "Reconciliation", "Provenance"): self.assertIn(p, parts)

    def test_a_missing_route_breaks_that_layer_and_its_flows(self):
        paths = [p for p in router_paths() if p != "/proof"]
        r = arch.check_architecture(paths); self.assertFalse(r["ok"])
        bad = {l["id"] for l in r["layers"] if not l["ok"]}; self.assertEqual(bad, {"evidence_layer", "proof_graph"})
        self.assertTrue(any("/proof" in p for l in r["layers"] for p in l["problems"]))
        self.assertTrue(any(not f["ok"] for f in r["flows"]))

    def test_a_module_that_fails_to_import_is_reported_with_its_reason(self):
        arch.LAYERS.append({"id": "x", "group": "t", "name": "X", "parts": [], "modules": ["asavexa.does_not_exist"], "prefixes": []})
        try: r = arch.check_architecture(router_paths())
        finally: arch.LAYERS.pop()
        x = [l for l in r["layers"] if l["id"] == "x"][0]; self.assertFalse(x["ok"]); self.assertIn("ModuleNotFoundError", x["problems"][0]); self.assertFalse(r["ok"])

    def test_every_layer_flow_references_a_real_layer(self):
        ids = {l["id"] for l in arch.LAYERS}
        for a, b in arch.FLOWS: self.assertIn(a, ids); self.assertIn(b, ids)


if __name__ == "__main__":
    unittest.main()
