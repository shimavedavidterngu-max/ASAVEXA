"""
VERA Financial Passport: built from a real, multi-module scenario using
the real services over in-memory SQLite (no mocks), then checked
figure by figure. Scenario (NGN): an invoice of 1,000,000 + 75,000 VAT
is drafted by an accountant, posted by an approver, with verified
evidence; a 200,000 rent journal is drafted AND posted by the owner with
no evidence; the bank statement has one matching deposit and one
unexplained debit.
"""
import json
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

from asavexa.accounting.domain.enums import AccountType
from asavexa.accounting.repository.sqlite_repository import (
    SqliteAccountRepository, SqliteJournalRepository, SqlitePeriodRepository,
)
from asavexa.accounting.services.engine import AccountingEngine, LineInput
from asavexa.audit.sqlite_repository import SqliteAuditRepository
from asavexa.bootstrap import create_sqlite_connection
from asavexa.compliance.repository.sqlite_repository import (
    SqliteControlDefinitionRepository, SqliteControlExecutionRepository,
    SqliteFindingRepository, SqliteRemediationRepository,
)
from asavexa.compliance.services.service import ComplianceService
from asavexa.evidence.domain.enums import EvidenceType
from asavexa.evidence.repository.sqlite_repository import SqliteEvidenceRepository
from asavexa.evidence.services.vault import EvidenceVault
from asavexa.identity.domain.enums import Role
from asavexa.identity.repository.sqlite_repository import (
    SqliteMembershipRepository, SqliteOrganisationRepository, SqliteSessionRepository, SqliteUserRepository,
)
from asavexa.identity.services.service import IdentityService
from asavexa.passport import builder
from asavexa.passport.builder import PassportInputs, build_passport
from asavexa.period_close.repository.sqlite_repository import SqlitePeriodCloseRepository
from asavexa.reconciliation.domain.models import BankTransactionInput
from asavexa.reconciliation.repository.sqlite_repository import (
    SqliteBankTransactionRepository, SqliteReconciliationRepository,
)
from asavexa.reconciliation.services.service import ReconciliationService
from asavexa.reporting.services.service import ReportingService
from asavexa.standards import engine as standards_engine

NOW = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)


class World:
    def __init__(self):
        self.conn = create_sqlite_connection(":memory:")
        self.audit = SqliteAuditRepository(self.conn)
        self.identity = IdentityService(
            organisations=SqliteOrganisationRepository(self.conn), users=SqliteUserRepository(self.conn),
            memberships=SqliteMembershipRepository(self.conn), sessions=SqliteSessionRepository(self.conn),
            audit=self.audit)
        self.accounting = AccountingEngine(
            accounts=SqliteAccountRepository(self.conn), periods=SqlitePeriodRepository(self.conn),
            journals=SqliteJournalRepository(self.conn), audit=self.audit)
        self.vault = EvidenceVault(evidence=SqliteEvidenceRepository(self.conn), audit=self.audit)
        self.reporting = ReportingService(accounting=self.accounting, audit=self.audit)
        self.recon = ReconciliationService(
            reconciliations=SqliteReconciliationRepository(self.conn),
            transactions=SqliteBankTransactionRepository(self.conn), audit=self.audit, accounting=self.accounting)
        self.compliance = ComplianceService(
            definitions=SqliteControlDefinitionRepository(self.conn),
            executions=SqliteControlExecutionRepository(self.conn),
            findings=SqliteFindingRepository(self.conn), remediations=SqliteRemediationRepository(self.conn),
            audit=self.audit, accounting=self.accounting, reporting=self.reporting, reconciliation=self.recon)
        self.close_repo = SqlitePeriodCloseRepository(self.conn)

        reg = self.identity.register_user
        self.owner = reg("dara@meridian.test", "correct horse battery staple")
        self.org = self.identity.create_organisation("Meridian Textiles Ltd", actor=self.owner.id)
        self.identity.add_membership(self.org.id, self.owner.id, Role.OWNER, actor_user_id=self.owner.id)
        self.accountant = reg("aisha@meridian.test", "yet-another-password")
        self.identity.add_membership(self.org.id, self.accountant.id, Role.ACCOUNTANT, actor_user_id=self.owner.id)
        self.approver = reg("kwame@meridian.test", "still-another-password")
        self.identity.add_membership(self.org.id, self.approver.id, Role.APPROVER, actor_user_id=self.owner.id)
        self.other_owner = reg("other@other.test", "unrelated-password")
        self.other_org = self.identity.create_organisation("Other Ltd", actor=self.other_owner.id)
        self.identity.add_membership(self.other_org.id, self.other_owner.id, Role.OWNER, actor_user_id=self.other_owner.id)

        a, o = self.accounting, self.org.id
        self.cash = a.create_account(o, "1000", "Cash at bank", AccountType.ASSET, self.owner.id, currency="NGN")
        self.vat = a.create_account(o, "2100", "VAT payable", AccountType.LIABILITY, self.owner.id, currency="NGN")
        self.rev = a.create_account(o, "4000", "Sales", AccountType.REVENUE, self.owner.id, currency="NGN")
        self.rent = a.create_account(o, "5000", "Rent", AccountType.EXPENSE, self.owner.id, currency="NGN")
        self.period = a.open_period(o, "FY2026-M01", date(2026, 1, 1), date(2026, 1, 31), actor=self.owner.id)
        self.empty_period = a.open_period(o, "FY2026-M02", date(2026, 2, 1), date(2026, 2, 28), actor=self.owner.id)

        inv = a.create_draft_journal(o, date(2026, 1, 5), "Invoice 001 to Kadena", "NGN", [
            LineInput(self.cash.id, debit_amount=Decimal("1075000.00")),
            LineInput(self.rev.id, credit_amount=Decimal("1000000.00")),
            LineInput(self.vat.id, credit_amount=Decimal("75000.00"))], created_by=self.accountant.id)
        self.invoice = a.post_journal(o, inv.id, actor=self.approver.id)
        ev = self.vault.upload_evidence(o, EvidenceType.INVOICE, b"invoice-001", "inv001.pdf", "application/pdf",
                                        uploaded_by=self.accountant.id, linked_journal_id=self.invoice.id)
        self.evidence = self.vault.verify_evidence(o, ev.id, actor=self.approver.id)

        rent = a.create_draft_journal(o, date(2026, 1, 20), "January rent", "NGN", [
            LineInput(self.rent.id, debit_amount=Decimal("200000.00")),
            LineInput(self.cash.id, credit_amount=Decimal("200000.00"))], created_by=self.owner.id)
        self.rent_journal = a.post_journal(o, rent.id, actor=self.owner.id)

        a.create_draft_journal(o, date(2026, 1, 25), "Draft only", "NGN", [
            LineInput(self.rent.id, debit_amount=Decimal("1.00")),
            LineInput(self.cash.id, credit_amount=Decimal("1.00"))], created_by=self.owner.id)

        rec = self.recon.create_reconciliation(o, self.cash.id, "January", date(2026, 1, 1), date(2026, 1, 31),
                                               actor=self.accountant.id)
        self.recon.import_transactions(o, rec.id, [
            BankTransactionInput(date(2026, 1, 5), "Deposit Kadena", debit_amount=Decimal("1075000.00"), currency="NGN"),
            BankTransactionInput(date(2026, 1, 28), "Unknown debit", credit_amount=Decimal("5000.00"), currency="NGN"),
        ], actor=self.accountant.id, import_source="bank_feed")
        self.reconciliation = rec

        controls = self.compliance.seed_standard_controls(o, actor=self.owner.id)
        for c in controls[:2]:
            self.compliance.execute_control(o, c.id, actor=self.accountant.id, period_id=self.period.id)

    def inputs(self, org_id=None, structure=None, standards=None, profile=None) -> PassportInputs:
        o = org_id or self.org.id
        c = self.conn
        recs = SqliteReconciliationRepository(c).list_for_org(o)
        txs = []
        for r in recs:
            txs.extend(SqliteBankTransactionRepository(c).list_for_reconciliation(o, r.id))
        periods = self.accounting.periods.list_for_org(o)
        closes = []
        for p in periods:
            closes.extend(self.close_repo.list_for_period(o, p.id))
        events, total = self.audit.list_recent_for_org(o, 5000, exclude_action_prefix="PASSPORT_")
        labels = {u.id: u.email for u in (self.owner, self.accountant, self.approver, self.other_owner)}
        org = SqliteOrganisationRepository(c).get(o)
        return PassportInputs(
            org_id=o, org_name=org.name, profile=profile or {}, structure=structure,
            standards=standards or {"configured": False}, periods=periods,
            accounts=self.accounting.accounts.list_for_org(o), journals=self.accounting.journals.list_for_org(o),
            evidence=self.vault.list_for_org(o), reconciliations=recs, bank_transactions=txs,
            controls=self.compliance.list_controls(o), executions=self.compliance.list_executions(o),
            findings=self.compliance.list_findings(o), close_processes=closes,
            memberships=SqliteMembershipRepository(c).list_for_org(o), audit_events=events, audit_total=total,
            user_labels=labels)


class PassportScenarioTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.w = World()
        std = standards_engine.resolve_configuration("NG", "PRIVATE_COMPANY")
        std["configured"] = True
        cls.passport = build_passport(
            cls.w.inputs(
                profile={"legal_name": "Meridian Textiles Limited", "registration_number": "RC123456",
                         "tax_id": "TIN-9", "country": "Nigeria", "base_currency": "NGN",
                         "fiscal_year_start_month": 1},
                structure={"owners": [{"name": "Dara A.", "kind": "INDIVIDUAL", "ownership_percent": "60"},
                                      {"name": "Holdco", "kind": "COMPANY", "ownership_percent": "40"}],
                           "subsidiaries": [{"name": "Meridian Ghana", "relationship": "SUBSIDIARY",
                                             "jurisdiction": "Ghana", "ownership_percent": "100"}],
                           "updated_at": NOW, "updated_by": cls.w.owner.id},
                standards=std),
            "dara@meridian.test", NOW)

    def test_is_plain_json_with_six_sections(self):
        json.dumps(self.passport)  # no Decimals, dates or enums may leak through
        for k in ("identity", "financial_history", "evidence_quality", "governance", "reporting", "audit_trail"):
            self.assertIn(k, self.passport)
            self.assertIn(self.passport[k]["status"], ("ok", "attention", "incomplete"))
        self.assertEqual(self.passport["schema_version"], "vera-passport/1")
        self.assertEqual(len(self.passport["fingerprint"]), 64)

    # ---- identity
    def test_identity(self):
        i = self.passport["identity"]
        self.assertEqual(i["legal_entity"]["legal_name"], "Meridian Textiles Limited")
        self.assertEqual(i["ownership"]["total_percent"], "100")
        self.assertEqual(len(i["ownership"]["owners"]), 2)
        self.assertEqual(i["subsidiaries"]["count"], 1)
        self.assertEqual([p["name"] for p in i["reporting_periods"]], ["FY2026-M01", "FY2026-M02"])
        self.assertEqual(i["ownership"]["updated_by"], "dara@meridian.test")
        self.assertEqual(i["status"], "ok", i["attention"])

    # ---- financial history
    def test_financial_figures_are_exact(self):
        f = self.passport["financial_history"]
        jan = next(p for p in f["periods"] if p["period_name"] == "FY2026-M01")
        self.assertEqual(jan["revenue"], "1000000.00")
        self.assertEqual(jan["expenses"], "200000.00")
        self.assertEqual(jan["net_income"], "800000.00")
        self.assertEqual(jan["profit_margin_percent"], 80.0)
        self.assertEqual(jan["assets"], "875000.00")
        self.assertEqual(jan["liabilities"], "75000.00")
        self.assertTrue(jan["is_balanced"])
        self.assertEqual(jan["journal_count"], 2)  # the draft is not counted
        feb = next(p for p in f["periods"] if p["period_name"] == "FY2026-M02")
        self.assertFalse(feb["has_activity"])
        self.assertEqual(f["totals"]["net_income"], "800000.00")
        self.assertEqual(f["totals"]["profitability"], "profit")
        self.assertEqual(f["currency"], "NGN")

    def test_figures_agree_with_the_reporting_module(self):
        r = self.w.reporting
        is_ = r.get_income_statement(self.w.org.id, self.w.period.id, actor="x")
        bs = r.get_balance_sheet(self.w.org.id, self.w.period.id, actor="x")
        jan = next(p for p in self.passport["financial_history"]["periods"] if p["period_name"] == "FY2026-M01")
        self.assertEqual(jan["revenue"], str(is_.total_revenue.quantize(Decimal("0.01"))))
        self.assertEqual(jan["expenses"], str(is_.total_expenses.quantize(Decimal("0.01"))))
        self.assertEqual(jan["assets"], str(bs.total_assets.quantize(Decimal("0.01"))))
        self.assertEqual(jan["liabilities"], str(bs.total_liabilities.quantize(Decimal("0.01"))))

    def test_cash_flow_is_honest_about_what_it_is(self):
        c = self.passport["financial_history"]["cash_flows"]
        self.assertTrue(c["available"])
        self.assertFalse(c["statement_available"])
        self.assertEqual(c["totals"], {"inflow": "1075000.00", "outflow": "200000.00", "net": "875000.00"})

    # ---- evidence quality
    def test_evidence_quality(self):
        e = self.passport["evidence_quality"]
        t = e["transactions"]
        self.assertEqual((t["total_posted"], t["supported_verified"], t["missing_evidence"]), (2, 1, 1))
        self.assertEqual(t["supported_percent"], 50.0)
        self.assertEqual(e["missing_evidence"]["items"][0]["description"], "January rent")
        self.assertEqual(e["missing_evidence"]["items"][0]["amount"], "200000.00")
        b = e["bank_reconciliation"]
        self.assertEqual(b["bank_transactions"], 2)
        self.assertGreaterEqual(b["unreconciled"], 1)
        self.assertTrue(any(x["description"] == "Unknown debit" for x in b["unreconciled_items"]))
        self.assertGreaterEqual(e["exceptions"]["count"], 1)
        self.assertEqual(e["status"], "attention")

    # ---- governance
    def test_segregation_of_duties_detects_the_owner_doing_both(self):
        g = self.passport["governance"]["segregation_of_duties"]
        chk = {c["key"]: c for c in g["checks"]}
        self.assertEqual(chk["journal_post"]["tested"], 2)
        self.assertEqual(chk["journal_post"]["violations"], 1)
        self.assertEqual(chk["journal_post"]["status"], "fail")
        self.assertEqual(chk["journal_post"]["examples"][0]["person"], "dara@meridian.test")
        self.assertEqual(chk["evidence_verify"]["status"], "pass")  # uploader != verifier
        self.assertEqual(chk["reconciliation_approve"]["status"], "not_tested")
        self.assertEqual(g["status"], "fail")
        people = {c["person"] for c in g["role_conflicts"]}
        self.assertIn("dara@meridian.test", people)       # OWNER can create and post
        self.assertNotIn("aisha@meridian.test", people)   # ACCOUNTANT cannot post

    def test_approvals_controls_and_exceptions(self):
        g = self.passport["governance"]
        self.assertEqual(g["approvals"]["by_action"]["JOURNAL_POSTED"], 2)
        self.assertEqual(g["approvals"]["by_action"]["EVIDENCE_VERIFIED"], 1)
        self.assertGreaterEqual(g["controls"]["defined"], 2)
        self.assertEqual(g["controls"]["executions"], 2)
        self.assertGreater(g["controls"]["never_executed"], 0)

    # ---- reporting
    def test_reporting_section_uses_the_standards_configuration(self):
        r = self.passport["reporting"]
        self.assertTrue(r["configured"])
        self.assertEqual(r["jurisdiction"], "Nigeria")
        self.assertEqual(r["framework"], "IFRS")
        self.assertEqual(len(r["reporting_periods"]), 2)

    # ---- audit trail
    def test_audit_trail_says_who_and_when(self):
        a = self.passport["audit_trail"]
        self.assertGreater(a["total_events"], 5)
        self.assertGreater(a["by_category"]["created"], 0)
        self.assertGreater(a["by_category"]["approved"], 0)
        who = {p["who"] for p in a["by_person"]}
        self.assertTrue({"dara@meridian.test", "aisha@meridian.test", "kwame@meridian.test"} <= who)
        inv = next(j for j in a["journal_provenance"] if j["journal_number"] == self.w.invoice.journal_number)
        self.assertEqual((inv["created_by"], inv["posted_by"]), ("aisha@meridian.test", "kwame@meridian.test"))
        self.assertTrue(inv["created_at"] and inv["posted_at"])
        self.assertIsNotNone(a["first_event_at"])

    # ---- integrity
    def test_fingerprint_is_stable_and_sensitive(self):
        again = build_passport(self.w.inputs(profile={"legal_name": "Meridian Textiles Limited"}), "x", NOW)
        same = build_passport(self.w.inputs(profile={"legal_name": "Meridian Textiles Limited"}), "someone else",
                              datetime(2030, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(again["fingerprint"], same["fingerprint"])  # time and viewer do not change it
        self.assertNotEqual(again["fingerprint"], self.passport["fingerprint"])  # different profile does

    def test_other_tenant_sees_none_of_it(self):
        p = build_passport(self.w.inputs(org_id=self.w.other_org.id), None, NOW)
        self.assertEqual(p["financial_history"]["status"], "incomplete")
        self.assertEqual(p["financial_history"]["totals"]["revenue"], "0.00")
        self.assertEqual(p["evidence_quality"]["transactions"]["total_posted"], 0)
        self.assertEqual(p["identity"]["legal_entity"]["legal_name"], "Other Ltd")
        self.assertNotIn("Meridian", json.dumps(p))


class PassportEdgeCasesTestCase(unittest.TestCase):
    def test_empty_organisation_is_incomplete_not_a_crash(self):
        p = build_passport(PassportInputs(org_id="o1"), None, NOW)
        json.dumps(p)
        self.assertEqual(p["financial_history"]["status"], "incomplete")
        self.assertFalse(p["financial_history"]["cash_flows"]["available"])
        self.assertEqual(p["evidence_quality"]["transactions"]["supported_percent"], None)
        self.assertEqual(p["governance"]["segregation_of_duties"]["status"], "not_tested")
        self.assertFalse(p["identity"]["ownership"]["recorded"])

    def test_ownership_over_100_percent_is_flagged(self):
        i = builder.build_identity(PassportInputs(org_id="o", structure={
            "owners": [{"name": "A", "ownership_percent": "70"}, {"name": "B", "ownership_percent": "50"}]}))
        self.assertTrue(any("more than 100" in m for m in i["attention"]))

    def test_classify_action(self):
        c = builder.classify_action
        self.assertEqual(c("JOURNAL_DRAFTED"), "created")
        self.assertEqual(c("EVIDENCE_UPLOADED"), "created")
        self.assertEqual(c("JOURNAL_POSTED"), "approved")
        self.assertEqual(c("RECONCILIATION_APPROVED"), "approved")
        self.assertEqual(c("ORGANISATION_PROFILE_UPDATED"), "changed")
        self.assertEqual(c("JOURNAL_REVERSED"), "changed")
        self.assertEqual(c("USER_LOGGED_IN"), "other")

    def test_mixed_currencies_are_called_out(self):
        w = World()
        w.accounting.create_draft_journal(w.org.id, date(2026, 1, 9), "USD sale", "USD", [
            LineInput(w.cash.id, debit_amount=Decimal("10.00")), LineInput(w.rev.id, credit_amount=Decimal("10.00"))],
            created_by=w.accountant.id)
        j = [x for x in w.accounting.journals.list_for_org(w.org.id) if x.description == "USD sale"][0]
        w.accounting.post_journal(w.org.id, j.id, actor=w.approver.id)
        f = builder.build_financial_history(w.inputs(profile={"base_currency": "NGN"}))
        self.assertEqual(f["currencies_seen"], ["NGN", "USD"])
        self.assertTrue(any("more than one currency" in m for m in f["attention"]))

    def test_audit_window_truncation_is_reported(self):
        w = World()
        events, total = w.audit.list_recent_for_org(w.org.id, 3)
        self.assertEqual(len(events), 3)
        self.assertGreater(total, 3)
        inp = w.inputs()
        inp.audit_events, inp.audit_total = events, total
        a = builder.build_audit_trail(inp)
        self.assertTrue(a["truncated"])
        self.assertTrue(any("Only the most recent" in m for m in a["attention"]))

    def test_passport_events_are_excluded_from_the_trail(self):
        w = World()
        from asavexa.audit.models import AuditEvent
        w.audit.record(AuditEvent(id="p1", org_id=w.org.id, entity_type="Passport", entity_id=w.org.id,
                                  action="PASSPORT_GENERATED", actor=w.owner.id, timestamp=NOW))
        events, _ = w.audit.list_recent_for_org(w.org.id, 5000, exclude_action_prefix="PASSPORT_")
        self.assertFalse(any(e.action.startswith("PASSPORT_") for e in events))
        events_all, _ = w.audit.list_recent_for_org(w.org.id, 5000)
        self.assertTrue(any(e.action == "PASSPORT_GENERATED" for e in events_all))


if __name__ == "__main__":
    unittest.main()
