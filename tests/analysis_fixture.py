"""A small, fully controlled organisation built through the real accounting engine so every analysis figure can be checked by hand.
January: cash 50,500; receivables 12,000; inventory 2,000; equipment 20,000 (assets 84,500). Payables 8,000; loan 20,000 (liabilities 28,000). Capital 50,000.
Revenue 15,000; cost of sales 6,000; rent 2,000; interest 500 (net income 6,500). February: revenue 20,000; cost of sales 9,000; rent 2,400 (net income 8,600)."""
from datetime import date
from decimal import Decimal

from asavexa.accounting.domain.enums import AccountType
from asavexa.accounting.repository.sqlite_repository import SqliteAccountRepository, SqliteJournalRepository, SqlitePeriodRepository
from asavexa.accounting.services.engine import AccountingEngine, LineInput
from asavexa.analysis.service import AnalysisService
from asavexa.audit.sqlite_repository import SqliteAuditRepository
from asavexa.bootstrap import create_sqlite_connection
from asavexa.evidence.repository.sqlite_repository import SqliteEvidenceRepository
from asavexa.evidence.services.vault import EvidenceVault
from asavexa.security.store import SqliteDocStore

ORG, OTHER = "org-a", "org-b"
PREP, PREP2, REVIEWER = "preparer-1", "preparer-2", "reviewer-1"
TAGS = {"1000": "CASH", "1100": "RECEIVABLE", "1200": "INVENTORY", "1500": "NONCURRENT_ASSET", "2000": "PAYABLE", "2500": "NONCURRENT_LIABILITY",
        "5000": "COST_OF_SALES", "5100": "OPERATING_EXPENSE", "5200": "FINANCE_COST"}


class World:
    def __init__(self):
        self.conn = create_sqlite_connection(":memory:")
        self.audit = SqliteAuditRepository(self.conn)
        self.acc = AccountingEngine(accounts=SqliteAccountRepository(self.conn), periods=SqlitePeriodRepository(self.conn), journals=SqliteJournalRepository(self.conn), audit=self.audit)
        self.vault = EvidenceVault(evidence=SqliteEvidenceRepository(self.conn), audit=self.audit)
        self.store = SqliteDocStore(self.conn)
        self.events = []
        self.svc = AnalysisService(self.store, self.acc, log=lambda action, actor, eid, org, reason="": self.events.append((action, actor, eid, org, reason)))
        a = {}
        for code, name, t in [("1000", "Cash at bank", AccountType.ASSET), ("1100", "Trade receivables", AccountType.ASSET), ("1200", "Inventory", AccountType.ASSET), ("1500", "Equipment", AccountType.ASSET),
                              ("2000", "Trade payables", AccountType.LIABILITY), ("2500", "Bank loan", AccountType.LIABILITY), ("3000", "Capital", AccountType.EQUITY), ("4000", "Sales", AccountType.REVENUE),
                              ("5000", "Cost of sales", AccountType.EXPENSE), ("5100", "Rent", AccountType.EXPENSE), ("5200", "Interest", AccountType.EXPENSE)]:
            a[code] = self.acc.create_account(ORG, code, name, t, actor=PREP)
        self.a = a
        self.jan = self.acc.open_period(ORG, "Jan 2026", date(2026, 1, 1), date(2026, 1, 31), actor=PREP)
        self.feb = self.acc.open_period(ORG, "Feb 2026", date(2026, 2, 1), date(2026, 2, 28), actor=PREP)
        self.mar = self.acc.open_period(ORG, "Mar 2026", date(2026, 3, 1), date(2026, 3, 31), actor=PREP)
        for d, text, lines in [
            (date(2026, 1, 2), "Capital", [("1000", "50000", 0), ("3000", 0, "50000")]),
            (date(2026, 1, 3), "Equipment on loan", [("1500", "20000", 0), ("2500", 0, "20000")]),
            (date(2026, 1, 5), "Stock bought", [("1200", "8000", 0), ("2000", 0, "8000")]),
            (date(2026, 1, 10), "Credit sale", [("1100", "12000", 0), ("4000", 0, "12000")]),
            (date(2026, 1, 12), "Cash sale", [("1000", "3000", 0), ("4000", 0, "3000")]),
            (date(2026, 1, 15), "Cost of sales", [("5000", "6000", 0), ("1200", 0, "6000")]),
            (date(2026, 1, 20), "Rent", [("5100", "2000", 0), ("1000", 0, "2000")]),
            (date(2026, 1, 25), "Interest", [("5200", "500", 0), ("1000", 0, "500")]),
            (date(2026, 2, 3), "Cash sale", [("1000", "20000", 0), ("4000", 0, "20000")]),
            (date(2026, 2, 10), "Cost of sales", [("5000", "9000", 0), ("1200", 0, "2000"), ("2000", 0, "7000")]),
            (date(2026, 2, 15), "Rent", [("5100", "2400", 0), ("1000", 0, "2400")]),
        ]:
            self.post(d, text, lines)

    def post(self, d, text, lines):
        j = self.acc.create_draft_journal(ORG, d, text, "USD", [LineInput(self.a[c].id, debit_amount=Decimal(str(dr)), credit_amount=Decimal(str(cr))) for c, dr, cr in lines], created_by=PREP)
        return self.acc.post_journal(ORG, j.id, actor=PREP)

    def classify(self):
        self.svc.set_config(ORG, {self.a[c].id: t for c, t in TAGS.items()}, None, PREP)

    def ratio(self, period, rid):
        return next(r for r in self.svc.ratios(ORG, period.id)["ratios"] if r["id"] == rid)
