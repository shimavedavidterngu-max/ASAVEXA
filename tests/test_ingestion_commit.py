"""Ingestion commit paths over the REAL accounting, evidence and reconciliation services (SQLite)."""
import unittest
import warnings
from datetime import date, datetime, timezone
from decimal import Decimal

from asavexa.accounting.domain.enums import JournalStatus
from asavexa.accounting.services.engine import LineInput
from asavexa.evidence.domain.enums import EvidenceStatus, EvidenceType
from asavexa.evidence.domain.errors import DuplicateEvidenceError
from asavexa.ingestion import commit as C
from asavexa.ingestion import service as S
from asavexa.ingestion.errors import BatchNotImportableError, IngestionError
from asavexa.reconciliation.domain.enums import BankTransactionStatus, ReconciliationStatus
from asavexa.reconciliation.domain.errors import ReconciliationNotFoundError
from ingest_helpers import text_pdf
from test_passport import World

warnings.filterwarnings("ignore")
NOW = datetime(2026, 3, 1, 12, tzinfo=timezone.utc)

STATEMENT = (b"Date,Description,Debit,Credit,Balance\n"
             b"2026-01-15,Cash sale,,7500.00,7500.00\n"
             b"2026-01-20,January rent,200000.00,,-192500.00\n"
             b"2026-01-28,Bank charges,500.00,,-193000.00\n")


class Base(unittest.TestCase):
    def setUp(self):
        self.w = World()
        w = self.w
        self.rec = w.recon.create_reconciliation(w.org.id, w.cash.id, "January statement", date(2026, 1, 1), date(2026, 1, 31),
                                                 actor=w.accountant.id, currency="NGN")
        sale = w.accounting.create_draft_journal(w.org.id, date(2026, 1, 15), "Cash sale", "NGN", [
            LineInput(w.cash.id, debit_amount=Decimal("7500.00")), LineInput(w.rev.id, credit_amount=Decimal("7500.00"))], created_by=w.accountant.id)
        self.sale = w.accounting.post_journal(w.org.id, sale.id, actor=w.approver.id)

    # the same sequence the API runs: stage -> mark -> guard -> commit
    def stage(self, content=STATEMENT, name="jan.csv", rid=None, **opts):
        w = self.w
        ctx = C.bank_context(w.recon, w.org.id, rid or self.rec.id)
        o = {"period": ctx["period"], **opts}
        b = S.preview(name, content, "BANK_STATEMENT", o, currency=ctx["currency"])
        C.mark_existing(b, w.recon, w.org.id, ctx)
        return b

    def commit_bank(self, b, content=STATEMENT, name="jan.csv", ack=True, fp=None, rid=None):
        w = self.w
        C.guard(b, fp or b["fingerprint"], ack)
        return C.commit_bank(b, recon_svc=w.recon, vault=w.vault, org_id=w.org.id, actor=w.accountant.id, reconciliation_id=rid or self.rec.id,
                             filename=name, content=content, content_type="text/csv")


class BankCommitTests(Base):
    def test_end_to_end_import_matches_stores_evidence_and_links_it(self):
        w = self.w
        b = self.stage()
        self.assertTrue(b["status"]["importable"], b["status"])
        self.assertEqual(b["summary"]["to_import"], 3)
        res = self.commit_bank(b)
        self.assertEqual(res["imported"], 3)
        txs = w.recon.list_transactions(w.org.id, self.rec.id)
        self.assertEqual(len(txs), 3)
        by = {t.description: t for t in txs}
        sale = by["Cash sale"]
        self.assertEqual((sale.debit_amount, sale.credit_amount), (Decimal("7500.00"), Decimal("0.00")))        # money in = ledger debit to cash
        self.assertEqual(sale.status, BankTransactionStatus.MATCHED)                                             # matched the posted journal
        self.assertEqual(sale.matched_journal_id, self.sale.id)
        rent = by["January rent"]
        self.assertEqual((rent.debit_amount, rent.credit_amount), (Decimal("0.00"), Decimal("200000.00")))
        self.assertEqual(rent.matched_journal_id, w.rent_journal.id)
        self.assertNotEqual(by["Bank charges"].status, BankTransactionStatus.MATCHED)                           # nothing in the ledger for it
        ev = w.vault.get_evidence(w.org.id, res["evidence_id"])
        self.assertEqual((ev.type, ev.status), (EvidenceType.BANK_STATEMENT, EvidenceStatus.UPLOADED))          # stored, NOT verified
        self.assertTrue(ev.metadata["ingestion"]["machine_read"])
        self.assertEqual(w.recon.get_reconciliation(w.org.id, self.rec.id).evidence_ref, ev.id)
        self.assertEqual(ev.uploaded_by, w.accountant.id)

    def test_the_accounting_ledger_is_untouched(self):
        w = self.w
        before = len(w.accounting.journals.list_for_org(w.org.id))
        self.commit_bank(self.stage())
        self.assertEqual(len(w.accounting.journals.list_for_org(w.org.id)), before)

    def test_importing_the_same_file_again_imports_nothing_and_reuses_the_evidence(self):
        first = self.commit_bank(self.stage())
        b2 = self.stage()
        self.assertEqual(b2["summary"]["already_imported"], 3)
        self.assertEqual(b2["summary"]["to_import"], 0)
        second = self.commit_bank(b2)
        self.assertEqual(second["imported"], 0)
        self.assertEqual(second["evidence_id"], first["evidence_id"])
        self.assertFalse(second["evidence_is_new"])
        self.assertEqual(len(self.w.recon.list_transactions(self.w.org.id, self.rec.id)), 3)

    def test_an_overlapping_statement_imports_only_the_new_lines(self):
        self.commit_bank(self.stage())
        more = STATEMENT + b"2026-01-30,Transfer fee,50.00,,874450.00\n"
        b = self.stage(more, name="jan2.csv")
        self.assertEqual((b["summary"]["already_imported"], b["summary"]["to_import"]), (3, 1))
        res = self.commit_bank(b, more, "jan2.csv")
        self.assertEqual(res["imported"], 1)
        self.assertEqual(len(self.w.recon.list_transactions(self.w.org.id, self.rec.id)), 4)

    def test_identical_lines_inside_one_file_all_import(self):
        content = b"Date,Description,Amount\n2026-01-10,Fee,-10.00\n2026-01-10,Fee,-10.00\n"
        b = self.stage(content)
        self.commit_bank(b, content)
        self.assertEqual(len(self.w.recon.list_transactions(self.w.org.id, self.rec.id)), 2)

    def test_guard_refuses_what_the_person_did_not_see(self):
        b = self.stage()
        with self.assertRaises(BatchNotImportableError):
            self.commit_bank(b, fp="0" * 64)                                       # changed since preview
        with self.assertRaises(BatchNotImportableError):
            C.guard(b, None, True)                                                 # no preview fingerprint at all
        bad = self.stage(b"Date,Description,Amount\nnot-a-date,x,1.00\n")
        with self.assertRaises(BatchNotImportableError) as c:
            C.guard(bad, bad["fingerprint"], True)
        self.assertIn("error", str(c.exception))
        warn = self.stage(b"Date,Description,Amount\n2026-03-05,Out of period,1.00\n")
        self.assertTrue(warn["status"]["needs_acknowledgement"])
        with self.assertRaises(BatchNotImportableError) as c:
            C.guard(warn, warn["fingerprint"], False)
        self.assertIn("confirm", str(c.exception))
        C.guard(warn, warn["fingerprint"], True)                                  # acknowledged: fine
        self.assertEqual(len(self.w.recon.list_transactions(self.w.org.id, self.rec.id)), 0, "refusals wrote nothing")

    def test_a_non_draft_reconciliation_is_refused(self):
        r = self.w.recon.get_reconciliation(self.w.org.id, self.rec.id)
        r.status = ReconciliationStatus.SUBMITTED
        self.w.recon.reconciliations.update(r)
        b = self.stage()
        self.assertFalse(b["status"]["importable"])
        with self.assertRaises(BatchNotImportableError):
            self.commit_bank(b)

    def test_another_organisations_reconciliation_is_invisible(self):
        with self.assertRaises(ReconciliationNotFoundError):
            C.bank_context(self.w.recon, self.w.other_org.id, self.rec.id)

    def test_currency_comes_from_the_reconciliation(self):
        b = self.stage(b"Date,Description,Amount,Currency\n2026-01-10,Fee,-10.00,USD\n")
        self.assertFalse(b["status"]["importable"])

    def test_pdf_statement_imports_the_same_way(self):
        pdf = text_pdf(["Opening Balance 1,000.00", "Date Description Debit Credit Balance", "2026-01-05 Deposit 500.00 1,500.00", "2026-01-06 Wire out 120.00 1,380.00", "Closing Balance 1,380.00"])
        b = self.stage(pdf, "s.pdf")
        self.assertTrue(b["status"]["importable"], b["issues"])
        res = self.commit_bank(b, pdf, "s.pdf")
        self.assertEqual(res["imported"], 2)

    def test_audit_event_has_summary_not_file_content(self):
        b = self.stage()
        res = self.commit_bank(b)
        ev = C.audit_event(self.w.org.id, self.w.accountant.id, "BANK_STATEMENT", b, res, NOW)
        self.assertEqual(ev.action, "INGEST_BANK_STATEMENT")
        self.assertEqual(ev.actor, self.w.accountant.id)
        dumped = str(ev.new_value)
        self.assertNotIn("Kadena", dumped)
        self.assertIn(b["source"]["sha256"], dumped)
        self.w.audit.record(ev)


class AccountsAndJournalsCommitTests(Base):
    COA = b"Code,Name,Type\n1000,Cash at bank,Bank\n1200,Prepaid rent,Current Asset\n6100,Software,Expense\n"

    def test_chart_of_accounts_creates_new_and_skips_existing(self):
        w = self.w
        b = S.preview("c.csv", self.COA, "CHART_OF_ACCOUNTS", {}, currency="NGN", existing_codes={a.code: a.id for a in w.accounting.accounts.list_for_org(w.org.id)})
        self.assertEqual(b["summary"]["already_exist"], 1)
        C.guard(b, b["fingerprint"], True)
        res = C.commit_accounts(b, accounting=w.accounting, org_id=w.org.id, actor=w.accountant.id, currency="NGN")
        self.assertEqual((res["created"], res["skipped_existing"]), (2, 1))
        a = w.accounting.accounts.get_by_code(w.org.id, "6100")
        self.assertEqual((a.name, a.type.value, a.currency, a.is_active), ("Software", "EXPENSE", "NGN", True))
        self.assertIsNone(w.accounting.accounts.get_by_code(w.other_org.id, "6100"), "other organisation untouched")

    def jrn(self, csv):
        w = self.w
        accts = [{"id": a.id, "code": a.code, "name": a.name} for a in w.accounting.accounts.list_for_org(w.org.id)]
        periods = [{"start": p.start_date, "end": p.end_date, "status": p.status.value} for p in w.accounting.periods.list_for_org(w.org.id)]
        return S.preview("j.csv", csv, "JOURNALS", {}, accounts=accts, periods=periods, currency="NGN")

    def test_journals_become_drafts_only_and_need_a_second_person_to_post(self):
        w = self.w
        b = self.jrn(b"Date,Journal Number,Account,Description,Debit,Credit\n2026-01-12,X1,5000,Rent top-up,300.00,\n2026-01-12,X1,1000,Rent top-up,,300.00\n")
        self.assertTrue(b["status"]["importable"], b)
        C.guard(b, b["fingerprint"], True)
        res = C.commit_journals(b, accounting=w.accounting, org_id=w.org.id, actor=w.accountant.id, currency="NGN")
        self.assertEqual(res["drafts_created"], 1)
        j = w.accounting.get_journal(w.org.id, res["journals"][0]["journal_id"]) if hasattr(w.accounting, "get_journal") else w.accounting.journals.get(w.org.id, res["journals"][0]["journal_id"])
        self.assertEqual(j.status, JournalStatus.DRAFT)
        self.assertEqual(j.created_by, w.accountant.id)
        self.assertEqual(sum(l.debit_amount for l in j.lines), Decimal("300.00"))
        posted = w.accounting.post_journal(w.org.id, j.id, actor=w.approver.id)
        self.assertEqual(posted.status, JournalStatus.POSTED)

    def test_unbalanced_unknown_account_and_closed_period_never_reach_the_engine(self):
        b = self.jrn(b"Date,Journal Number,Account,Debit,Credit\n2026-01-12,Y1,5000,10,\n2026-01-12,Y1,1000,,9\n")
        with self.assertRaises(BatchNotImportableError):
            C.guard(b, b["fingerprint"], True)
        b = self.jrn(b"Date,Journal Number,Account,Debit,Credit\n2026-01-12,Y2,7777,10,\n2026-01-12,Y2,1000,,10\n")
        self.assertFalse(b["status"]["importable"])
        b = self.jrn(b"Date,Journal Number,Account,Debit,Credit\n2027-01-12,Y3,5000,10,\n2027-01-12,Y3,1000,,10\n")
        self.assertIn("OPEN accounting period", b["rows"][0]["issues"][0]["message"])


class DocumentCommitTests(Base):
    INV = ["Kadena Supplies Ltd", "Invoice No: INV-2026-0042", "Invoice Date: 15/02/2026", "Subtotal NGN 50,000.00", "VAT (7.5%) NGN 3,750.00", "Total NGN 53,750.00"]

    def test_invoice_is_stored_unverified_with_machine_read_fields_and_nothing_is_posted(self):
        w = self.w
        pdf = text_pdf(self.INV)
        b = S.preview("inv.pdf", pdf, "DOCUMENT", {})
        before = len(w.accounting.journals.list_for_org(w.org.id))
        C.guard(b, b["fingerprint"], True)
        res = C.commit_evidence(b, vault=w.vault, org_id=w.org.id, actor=w.accountant.id, filename="inv.pdf", content=pdf, content_type="application/pdf", evidence_type="INVOICE")
        ev = w.vault.get_evidence(w.org.id, res["evidence_id"])
        self.assertEqual((ev.type, ev.status), (EvidenceType.INVOICE, EvidenceStatus.UPLOADED))
        self.assertEqual(ev.metadata["ingestion"]["fields"]["total"], "53750.00")
        self.assertTrue(ev.metadata["ingestion"]["machine_read"])
        self.assertEqual(len(w.accounting.journals.list_for_org(w.org.id)), before)

    def test_same_document_twice_is_a_duplicate_unless_allowed(self):
        w = self.w
        pdf = text_pdf(self.INV)
        b = S.preview("inv.pdf", pdf, "DOCUMENT", {})
        kw = dict(vault=w.vault, org_id=w.org.id, actor=w.accountant.id, filename="inv.pdf", content=pdf, content_type="application/pdf", evidence_type="INVOICE")
        C.commit_evidence(b, **kw)
        with self.assertRaises(DuplicateEvidenceError):
            C.commit_evidence(b, **kw)
        C.commit_evidence(b, allow_duplicate=True, **kw)

    def test_payroll_register_is_stored_as_payroll_evidence(self):
        w = self.w
        csv = b"Employee,Gross Pay,PAYE,Pension,Net Pay\nAisha,500000,50000,40000,410000\n"
        b = S.preview("p.csv", csv, "PAYROLL", {})
        res = C.commit_evidence(b, vault=w.vault, org_id=w.org.id, actor=w.accountant.id, filename="p.csv", content=csv, content_type="text/csv", evidence_type="PAYROLL_EVIDENCE")
        self.assertEqual(w.vault.get_evidence(w.org.id, res["evidence_id"]).type, EvidenceType.PAYROLL_EVIDENCE)
        self.assertEqual(len(w.accounting.journals.list_for_org(w.org.id)), len(w.accounting.journals.list_for_org(w.org.id)))

    def test_unknown_evidence_type(self):
        w = self.w
        b = S.preview("a.txt", b"Acme\nTotal 10.00", "DOCUMENT", {})
        with self.assertRaises(IngestionError):
            C.commit_evidence(b, vault=w.vault, org_id=w.org.id, actor=w.accountant.id, filename="a.txt", content=b"x", content_type="text/plain", evidence_type="NOPE")


if __name__ == "__main__":
    unittest.main()
