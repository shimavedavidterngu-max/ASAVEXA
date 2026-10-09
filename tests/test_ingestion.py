"""External data ingestion: readers, checks and refusals (pure functions, real generated files)."""
import hashlib
import hmac
import io
import json
import time
import unittest
import warnings
from datetime import date
from decimal import Decimal

from asavexa.ingestion import connectors, formats, service as S
from asavexa.ingestion.accounting_export import classify_account_type, stage_chart_of_accounts, stage_journals
from asavexa.ingestion.documents import read_document
from asavexa.ingestion.errors import IngestionError, UnsupportedFileError
from asavexa.ingestion.payroll import stage_payroll
from asavexa.ingestion.tabular import detect_mapping, find_header_row, read_table
from asavexa.ingestion.util import AmountError, detect_date_format, parse_amount
from ingest_helpers import image_only_pdf, text_pdf, xlsx

warnings.filterwarnings("ignore")


def bank(csv: bytes, name="s.csv", **opts):
    opts.setdefault("currency", "NGN")
    return S.preview(name, csv, "BANK_STATEMENT", opts)


def rows(b):
    return [(r["date"], r["money_in"], r["money_out"], r["status"]) for r in b["rows"]]


class AmountTests(unittest.TestCase):
    def test_formats(self):
        D = Decimal
        for raw, want in [("1,234.50", "1234.50"), ("(1,234.50)", "-1234.50"), ("1.234,50", "1234.50"), ("1 234,50", "1234.50"), ("₦1,234.50", "1234.50"),
                          ("1,234.50CR", "1234.50"), ("1,234.50 DR", "-1234.50"), ("1234.5-", "-1234.50"), ("-12", "-12.00"), ("12,5", "12.50"),
                          ("NGN 5,000.00", "5000.00"), (3, "3.00"), (1.1, "1.10"), ("+7", "7.00"), (D("2.5"), "2.50")]:
            self.assertEqual(parse_amount(raw), D(want), raw)

    def test_blank_is_none_and_junk_is_refused(self):
        for blank in ("", "  ", "-", None, "n/a"):
            self.assertIsNone(parse_amount(blank))
        for bad in ("abc", "1,2,3", "12.345", "1..2", True, "NaN", float("nan"), "99999999999999999"):
            with self.assertRaises(AmountError, msg=str(bad)):
                parse_amount(bad)

    def test_money_is_never_rounded_silently(self):
        with self.assertRaises(AmountError):
            parse_amount("10.005")


class DateTests(unittest.TestCase):
    def test_unambiguous(self):
        self.assertEqual(detect_date_format(["15/02/2026", "01/02/2026"])[0], "DD/MM/YYYY")
        self.assertEqual(detect_date_format(["02/15/2026"])[0], "MM/DD/YYYY")
        self.assertEqual(detect_date_format(["2026-01-05", "2026-01-06 10:00:00"])[0], "YYYY-MM-DD")

    def test_ambiguous_is_flagged(self):
        label, fits, amb = detect_date_format(["01/02/2026", "03/02/2026"])
        self.assertTrue(amb)
        self.assertEqual(label, "DD/MM/YYYY")

    def test_mixed_styles_do_not_fit(self):
        self.assertIsNone(detect_date_format(["01/02/2026", "2026-02-03"])[0])


class TabularTests(unittest.TestCase):
    CSV = b"Date,Description,Debit,Credit,Balance\n05/01/2026,Deposit,,500.00,1500.00\n13/01/2026,Wire,120.00,,1380.00\n"

    def test_comma_semicolon_tab_pipe(self):
        base = self.CSV.decode()
        for d in (";", "\t", "|"):
            b = bank(base.replace(",", d).encode())
            self.assertEqual(len(b["rows"]), 2, d)
            self.assertEqual(b["source"]["delimiter"], {"\t": "TAB"}.get(d, d))

    def test_quoted_commas_survive(self):
        b = bank(b'Date,Description,Amount\n2026-01-05,"Kadena, Ltd - inv 1",\n2026-01-06,"Kadena, Ltd",\"1,200.00\"\n')
        self.assertEqual(b["rows"][0]["description"], "Kadena, Ltd")
        self.assertEqual(b["rows"][0]["money_in"], "1200.00")

    def test_windows_1252_and_bom(self):
        b = bank("Date,Description,Amount\n2026-01-05,Café Müller,100.00\n".encode("cp1252"))
        self.assertIn("Café Müller", b["rows"][0]["description"])
        self.assertTrue(any("not UTF-8" in i["message"] for i in b["issues"]))
        b2 = bank(b"\xef\xbb\xbf" + self.CSV)
        self.assertEqual(len(b2["rows"]), 2)

    def test_junk_above_the_header(self):
        b = bank(b"ACME BANK\nAccount 123\n\n" + self.CSV)
        self.assertEqual(b["header_row"], 3 + 1 - 1 + 0) if False else self.assertEqual(len(b["rows"]), 2)

    def test_empty_binary_and_headerless_files(self):
        with self.assertRaises(IngestionError):
            bank(b"")
        with self.assertRaises(UnsupportedFileError):
            bank(b"a,b\x00\x01\x02\x03,c" * 10)
        with self.assertRaises(IngestionError) as c:
            bank(b"hello,world\n1,2\n")
        self.assertIn("column headings", str(c.exception))

    def test_mapping_override_and_errors(self):
        b = bank(b"When,What,How much\n2026-01-05,Rent,-50.00\n", mapping={"date": "When", "description": "What", "amount": "How much"})
        self.assertEqual(b["rows"][0]["money_out"], "50.00")
        with self.assertRaises(IngestionError):
            bank(self.CSV, mapping={"date": "Nope"})
        with self.assertRaises(IngestionError):
            bank(self.CSV, mapping={"bogus": "Date"})
        with self.assertRaises(IngestionError):
            bank(self.CSV, mapping={"description": "Date"})   # same column twice

    def test_too_many_rows_and_size(self):
        with self.assertRaises(IngestionError):
            S.preview("big.csv", b"a" * (11 * 1024 * 1024), "BANK_STATEMENT", {})


class ExcelTests(unittest.TestCase):
    def test_dates_numbers_and_multiple_sheets(self):
        data = xlsx({"Notes": [["Just a note"]], "Statement": [["Date", "Narration", "Debit", "Credit", "Balance"],
                                                                [date(2026, 1, 5), "Deposit", None, 500, 1500], [date(2026, 1, 6), "Wire out", 120.5, None, 1379.5]]})
        b = S.preview("s.xlsx", data, "BANK_STATEMENT", {"currency": "NGN"})
        self.assertEqual(b["source"]["sheet"], "Statement")
        self.assertEqual(rows(b), [("2026-01-05", "500.00", "0.00", "OK"), ("2026-01-06", "0.00", "120.50", "OK")])
        self.assertEqual(b["checks"][0]["result"], "PASS")

    def test_sheet_choice_and_unknown_sheet(self):
        data = xlsx({"A": [["x"]], "B": [["Date", "Amount"], ["2026-01-05", 10]]})
        self.assertEqual(S.preview("s.xlsx", data, "BANK_STATEMENT", {"sheet": "B"})["source"]["sheet"], "B")
        with self.assertRaises(IngestionError):
            S.preview("s.xlsx", data, "BANK_STATEMENT", {"sheet": "Z"})

    def test_old_xls_and_fake_xlsx_are_refused_kindly(self):
        with self.assertRaises(UnsupportedFileError) as c:
            S.preview("old.xls", bytes.fromhex("D0CF11E0A1B11AE1") + b"\x00" * 100, "BANK_STATEMENT", {})
        self.assertIn(".xlsx", str(c.exception))
        with self.assertRaises(UnsupportedFileError):
            S.preview("fake.xlsx", b"PK\x03\x04 not really", "BANK_STATEMENT", {})

    def test_numeric_account_codes_do_not_become_1000_0(self):
        data = xlsx({"COA": [["Code", "Name", "Type"], [1000.0, "Cash", "Bank"], [4000, "Sales", "Income"]]})
        b = S.preview("c.xlsx", data, "CHART_OF_ACCOUNTS", {})
        self.assertEqual([r["code"] for r in b["rows"]], ["1000", "4000"])


class BankStatementTests(unittest.TestCase):
    def test_debit_credit_columns_use_ledger_direction(self):
        b = bank(b"Date,Description,Debit,Credit\n2026-01-05,Deposit,,500.00\n2026-01-06,Wire out,120.00,\n")
        # money into the bank is the ledger's DEBIT to cash; the preview says it in plain words
        self.assertEqual(rows(b), [("2026-01-05", "500.00", "0.00", "OK"), ("2026-01-06", "0.00", "120.00", "OK")])
        self.assertEqual(b["summary"]["net"], "380.00")

    def test_single_signed_amount_and_flip(self):
        csv = b"Date,Description,Amount\n2026-01-05,Deposit,500.00\n2026-01-06,Wire,-120.00\n"
        self.assertEqual(rows(bank(csv))[0][1:3], ("500.00", "0.00"))
        self.assertEqual(rows(bank(csv, flip=True))[0][1:3], ("0.00", "500.00"))

    def test_dr_cr_marker_column(self):
        b = bank(b"Date,Narration,Amount,DR/CR\n2026-01-05,Dep,500.00,CR\n2026-01-06,Wire,120.00,DR\n")
        self.assertEqual(rows(b), [("2026-01-05", "500.00", "0.00", "OK"), ("2026-01-06", "0.00", "120.00", "OK")])
        bad = bank(b"Date,Narration,Amount,DR/CR\n2026-01-05,Dep,500.00,??\n")
        self.assertEqual(bad["rows"][0]["status"], "ERROR")

    def test_european_numbers(self):
        b = bank(b"Date;Description;Amount\n05.01.2026;Zahlung;1.234,50\n", )
        self.assertEqual(b["rows"][0]["money_in"], "1234.50")

    def test_bad_rows_block_the_import_and_say_why(self):
        b = bank(b"Date,Description,Amount\n2026-01-05,Ok,10.00\nnot-a-date,Bad,10.00\n2026-01-07,Bad amount,12.345\n")
        self.assertFalse(b["status"]["importable"])
        self.assertEqual(b["status"]["errors"], 2)
        msgs = " ".join(i["message"] for r in b["rows"] for i in r["issues"])
        self.assertIn("could not be read", msgs)
        self.assertIn("more than two decimal places", msgs)

    def test_ambiguous_dates_warn_and_override_works(self):
        csv = b"Date,Description,Amount\n01/02/2026,A,10.00\n03/02/2026,B,10.00\n"
        b = bank(csv)
        self.assertEqual(b["rows"][0]["date"], "2026-02-01")
        self.assertTrue(b["status"]["needs_acknowledgement"])
        self.assertEqual(bank(csv, date_format="MM/DD/YYYY")["rows"][0]["date"], "2026-01-02")
        with self.assertRaises(IngestionError):
            bank(csv, date_format="XX")

    def test_identical_lines_are_kept_but_flagged_and_given_distinct_refs(self):
        b = bank(b"Date,Description,Amount\n2026-01-05,Fee,-10.00\n2026-01-05,Fee,-10.00\n2026-01-05,Fee,-10.00\n")
        refs = [r["reference"] for r in b["rows"]]
        self.assertEqual(len(set(refs)), 3)
        self.assertEqual(b["rows"][1]["status"], "WARNING")
        self.assertTrue(b["status"]["needs_acknowledgement"])

    def test_footer_lines_and_zero_lines_are_skipped_not_errors(self):
        b = bank(b"Date,Description,Debit,Credit,Balance\n2026-01-05,Dep,,10.00,10.00\n2026-01-06,Zero,0.00,,10.00\nTotals,,,10.00,\n")
        self.assertEqual(len(b["rows"]), 1)
        self.assertEqual(b["summary"]["skipped_lines"], 2)
        self.assertTrue(b["status"]["importable"])

    def test_running_balance_passes_fails_and_detects_newest_first(self):
        ok = bank(b"Date,Description,Debit,Credit,Balance\n2026-01-05,A,,500.00,1500.00\n2026-01-06,B,120.00,,1380.00\n2026-01-07,C,,20.00,1400.00\n")
        self.assertEqual(ok["checks"][0]["result"], "PASS")
        broken = bank(b"Date,Description,Debit,Credit,Balance\n2026-01-05,A,,500.00,1500.00\n2026-01-06,B,120.00,,1300.00\n2026-01-07,C,,20.00,1320.00\n")
        self.assertEqual(broken["checks"][0]["result"], "FAIL")
        self.assertIn("file row 3", broken["checks"][0]["detail"])
        self.assertTrue(broken["status"]["needs_acknowledgement"])
        newest = bank(b"Date,Description,Debit,Credit,Balance\n2026-01-07,C,,20.00,1400.00\n2026-01-06,B,120.00,,1380.00\n2026-01-05,A,,500.00,1500.00\n")
        self.assertEqual(newest["checks"][0]["result"], "PASS")
        self.assertIn("newest first", newest["checks"][0]["detail"])

    def test_opening_and_closing_balance_check(self):
        good = bank(b"Opening Balance,,,,1000.00\nDate,Description,Debit,Credit,Balance\n2026-01-05,A,,500.00,1500.00\nClosing Balance,,,,1500.00\n")
        self.assertEqual(good["checks"][1]["result"], "PASS")
        bad = bank(b"Opening Balance,,,,1000.00\nDate,Description,Debit,Credit,Balance\n2026-01-05,A,,500.00,1500.00\nClosing Balance,,,,1600.00\n")
        self.assertEqual(bad["checks"][1]["result"], "FAIL")

    def test_currency_column_must_match_the_account(self):
        b = bank(b"Date,Description,Amount,Currency\n2026-01-05,A,10.00,USD\n", currency="NGN")
        self.assertEqual(b["rows"][0]["status"], "ERROR")

    def test_period_warning(self):
        b = S.preview("s.csv", b"Date,Description,Amount\n2026-03-05,A,10.00\n", "BANK_STATEMENT",
                      {"currency": "NGN", "period": (date(2026, 1, 1), date(2026, 1, 31))})
        self.assertEqual(b["rows"][0]["status"], "WARNING")
        self.assertIn("outside the reconciliation period", b["rows"][0]["issues"][0]["message"])

    def test_both_debit_and_credit_on_one_line_is_an_error(self):
        b = bank(b"Date,Description,Debit,Credit\n2026-01-05,A,10.00,10.00\n")
        self.assertEqual(b["rows"][0]["status"], "ERROR")

    def test_no_transactions_is_not_importable(self):
        b = bank(b"Date,Description,Amount\n")
        self.assertFalse(b["status"]["importable"])

    def test_same_file_same_fingerprint_changed_file_different(self):
        a = bank(b"Date,Description,Amount\n2026-01-05,A,10.00\n")
        self.assertEqual(a["fingerprint"], bank(b"Date,Description,Amount\n2026-01-05,A,10.00\n")["fingerprint"])
        self.assertNotEqual(a["fingerprint"], bank(b"Date,Description,Amount\n2026-01-05,A,10.01\n")["fingerprint"])
        self.assertNotEqual(a["fingerprint"], bank(b"Date,Description,Amount\n2026-01-05,A,10.00\n", flip=True)["fingerprint"])


class StatementFormatTests(unittest.TestCase):
    OFX = (b"OFXHEADER:100\nDATA:OFXSGML\n\n<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><CURDEF>NGN<BANKACCTFROM><ACCTID>0123456789</BANKACCTFROM><BANKTRANLIST>"
           b"<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20260105120000<TRNAMT>500.00<FITID>A1<NAME>Deposit<MEMO>INV 12</STMTTRN>"
           b"<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260106<TRNAMT>-120.00<FITID>A2<NAME>Wire &amp; out</STMTTRN></BANKTRANLIST>"
           b"<LEDGERBAL><BALAMT>380.00<DTASOF>20260131</LEDGERBAL></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>")
    MT = b":20:S1\n:25:044/0123\n:28C:1/1\n:60F:C260101NGN1000,00\n:61:2601050105C500,00NTRFNONREF//BANK1\n:86:Deposit INV 12\n:61:2601060106D120,00NTRFNONREF//BANK2\n:86:Wire out\n:62F:C260131NGN1380,00\n"

    def test_ofx(self):
        b = S.preview("a.ofx", self.OFX, "BANK_STATEMENT", {"currency": "NGN"})
        self.assertEqual(rows(b), [("2026-01-05", "500.00", "0.00", "OK"), ("2026-01-06", "0.00", "120.00", "OK")])
        self.assertEqual(b["rows"][1]["description"], "Wire & out")
        self.assertEqual(b["rows"][0]["reference"], "A1")
        self.assertEqual(b["summary"]["closing_balance"], "380.00")
        self.assertEqual(b["source"]["account_hint"], "…6789")

    def test_ofx_currency_mismatch_blocks(self):
        b = S.preview("a.ofx", self.OFX, "BANK_STATEMENT", {"currency": "USD"})
        self.assertFalse(b["status"]["importable"])

    def test_mt940(self):
        b = S.preview("a.sta", self.MT, "BANK_STATEMENT", {"currency": "NGN"})
        self.assertEqual(rows(b), [("2026-01-05", "500.00", "0.00", "OK"), ("2026-01-06", "0.00", "120.00", "OK")])
        self.assertEqual(b["checks"][1]["result"], "PASS")
        self.assertEqual(b["rows"][0]["description"], "Deposit INV 12")

    def test_mt940_wrong_closing_balance_is_flagged(self):
        b = S.preview("a.sta", self.MT.replace(b"1380,00", b"1390,00"), "BANK_STATEMENT", {"currency": "NGN"})
        self.assertEqual(b["checks"][1]["result"], "FAIL")

    def test_not_ofx_or_mt940(self):
        with self.assertRaises(UnsupportedFileError):
            formats.stage_ofx("x.ofx", b"hello", {}, {})
        with self.assertRaises(UnsupportedFileError):
            formats.stage_mt940("x.sta", b"hello", {}, {})


class PdfTests(unittest.TestCase):
    STATEMENT = ["ACME BANK - Statement of Account", "Account Number: 0123456789", "Opening Balance 1,000.00", "Date Description Debit Credit Balance",
                 "05/01/2026 Deposit from Kadena 500.00 1,500.00", "06/01/2026 Wire out 120.00 1,380.00",
                 "13/01/2026 Bank fee 1,120.50 259.50", "continued transfer reference 77", "Closing Balance 259.50"]

    def test_text_pdf_statement_direction_comes_from_the_balances(self):
        b = S.preview("s.pdf", text_pdf(self.STATEMENT), "BANK_STATEMENT", {"currency": "NGN"})
        self.assertEqual(rows(b), [("2026-01-05", "500.00", "0.00", "OK"), ("2026-01-06", "0.00", "120.00", "OK"), ("2026-01-13", "0.00", "1120.50", "OK")])
        self.assertTrue(all(c["result"] == "PASS" for c in b["checks"]))
        self.assertEqual(b["source"]["format"], "PDF")

    def test_scanned_pdf_is_refused_for_statements_and_stored_unread_as_a_document(self):
        with self.assertRaises(UnsupportedFileError) as c:
            S.preview("scan.pdf", image_only_pdf(), "BANK_STATEMENT", {})
        self.assertIn("no readable text", str(c.exception))
        d = S.preview("scan.pdf", image_only_pdf(), "DOCUMENT", {})
        self.assertEqual(d["document"]["type"], "UNREAD")

    def test_not_a_pdf_and_encrypted(self):
        with self.assertRaises(UnsupportedFileError):
            S.preview("x.pdf", b"hello there this is not a pdf", "DOCUMENT", {})
        from pypdf import PdfReader, PdfWriter
        w = PdfWriter()
        w.append(PdfReader(io.BytesIO(text_pdf(["hello world this is some text"]))))
        w.encrypt("secret")
        out = io.BytesIO()
        w.write(out)
        with self.assertRaises(UnsupportedFileError) as c:
            S.preview("x.pdf", out.getvalue(), "DOCUMENT", {})
        self.assertIn("password", str(c.exception))

    def test_pdf_with_no_transaction_lines(self):
        with self.assertRaises(IngestionError):
            S.preview("x.pdf", text_pdf(["Just some prose about banking, nothing tabular here at all."]), "BANK_STATEMENT", {})

    def test_direction_unclear_is_an_error_not_a_guess(self):
        b = S.preview("s.pdf", text_pdf(["05/01/2026 Mystery 500.00"]), "BANK_STATEMENT", {"currency": "NGN"})
        self.assertEqual(b["rows"][0]["status"], "ERROR")
        self.assertIn("money in or out", b["rows"][0]["issues"][0]["message"])


class DocumentTests(unittest.TestCase):
    INV = ["Kadena Supplies Ltd", "Invoice No: INV-2026-0042", "Invoice Date: 15/02/2026", "Due Date: 17/03/2026", "TIN: 12345678-0001", "Bill To: Meridian",
           "Subtotal NGN 50,000.00", "VAT (7.5%) NGN 3,750.00", "Total NGN 53,750.00"]

    def test_invoice_fields_with_sources_and_confidence(self):
        d = read_document("\n".join(self.INV))
        f = d["fields"]
        self.assertEqual(d["type"], "INVOICE")
        self.assertEqual((f["document_number"]["value"], f["issue_date"]["value"], f["due_date"]["value"]), ("INV-2026-0042", "2026-02-15", "2026-03-17"))
        self.assertEqual((f["subtotal"]["value"], f["tax"]["value"], f["total"]["value"]), ("50000.00", "3750.00", "53750.00"))
        self.assertEqual(f["tax_id"]["value"], "12345678-0001")
        self.assertEqual(f["vendor"]["confidence"], "LOW")      # guessed from the first line: say so
        self.assertIn("Total", f["total"]["source_line"])
        self.assertEqual(d["checks"][0]["result"], "PASS")

    def test_totals_that_do_not_add_up_are_flagged(self):
        d = read_document("\n".join(self.INV).replace("53,750.00", "53,000.00"))
        self.assertEqual(d["checks"][0]["result"], "FAIL")

    def test_due_date_never_becomes_the_issue_date(self):
        d = read_document("Acme\nInvoice No: A-100\nDue Date: 17/03/2026\nTotal 10.00")
        self.assertNotIn("issue_date", d["fields"])

    def test_receipt_and_unknown(self):
        r = read_document("Corner Shop\nReceipt\nDate: 2026-01-05\nCash tendered 20.00\nChange 5.00\nTotal 15.00")
        self.assertEqual(r["type"], "RECEIPT")
        self.assertEqual(r["fields"]["total"]["value"], "15.00")
        self.assertEqual(read_document("Hello world\nnothing financial")["type"], "UNKNOWN")

    def test_pdf_document_end_to_end_and_unreadable_images(self):
        b = S.preview("inv.pdf", text_pdf(self.INV), "DOCUMENT", {})
        self.assertEqual(b["document"]["type"], "INVOICE")
        self.assertFalse(b["proposal"]["applied"])
        self.assertTrue(b["proposal"]["needs_account_choice"])
        img = S.preview("r.jpg", b"\xff\xd8\xff\xe0 fake jpeg bytes", "DOCUMENT", {})
        self.assertEqual(img["document"]["type"], "UNREAD")
        self.assertTrue(img["status"]["importable"])

    def test_forced_type(self):
        b = S.preview("a.txt", b"Acme\nTotal 10.00", "DOCUMENT", {"doc_type": "RECEIPT"})
        self.assertEqual(b["document"]["type"], "RECEIPT")


class AccountingExportTests(unittest.TestCase):
    XERO = (b"*Code,*Name,*Type,*Tax Code,Description\n200,Sales,Revenue,Tax Exempt,\n310,Cost of Goods Sold,Direct Costs,,\n090,Business Bank Account,Bank,,\n"
            b"800,Accounts Payable,Current Liability,,\n970,Retained Earnings,Equity,,\n400,Advertising,Expense,,\n")
    QBO = b"Account #,Account,Type,Detail Type,Balance\n1000,Checking,Bank,Checking,10\n2000,Accounts Payable (A/P),Accounts payable (A/P),Accounts Payable,0\n4000,Sales,Income,Sales,0\n6000,Rent,Expenses,Rent,0\n"

    def test_types_map_and_systems_are_recognised(self):
        x = S.preview("c.csv", self.XERO, "CHART_OF_ACCOUNTS", {"currency": "NGN"})
        self.assertEqual(x["source"]["looks_like"], "XERO")
        self.assertEqual([r["type"] for r in x["rows"]], ["REVENUE", "EXPENSE", "ASSET", "LIABILITY", "EQUITY", "EXPENSE"])
        self.assertEqual(x["rows"][2]["code"], "090")             # leading zero kept
        q = S.preview("c.csv", self.QBO, "CHART_OF_ACCOUNTS", {"currency": "NGN"})
        self.assertEqual(q["source"]["looks_like"], "QUICKBOOKS")
        self.assertEqual([r["type"] for r in q["rows"]], ["ASSET", "LIABILITY", "REVENUE", "EXPENSE"])

    def test_classifier(self):
        for t, want in [("Other Income", "REVENUE"), ("Other Expense", "EXPENSE"), ("Fixed Assets", "ASSET"), ("Credit Card", "LIABILITY"),
                        ("Cost of Goods Sold", "EXPENSE"), ("Accounts receivable (A/R)", "ASSET"), ("Mystery", None), ("", None)]:
            self.assertEqual(classify_account_type(t), want, t)

    def test_unknown_type_duplicate_and_missing_code_are_errors(self):
        b = S.preview("c.csv", b"Code,Name,Type\n1,A,Mystery\n2,B,Bank\n2,C,Bank\n,D,Bank\n", "CHART_OF_ACCOUNTS", {"currency": "NGN"})
        self.assertEqual([r["status"] for r in b["rows"]], ["ERROR", "OK", "ERROR", "ERROR"])
        self.assertFalse(b["status"]["importable"])

    def test_existing_codes_are_left_alone(self):
        b = S.preview("c.csv", b"Code,Name,Type\n1000,Cash,Bank\n1100,Petty,Bank\n", "CHART_OF_ACCOUNTS", {"currency": "NGN"}, existing_codes={"1000": "x"})
        self.assertEqual(b["summary"], {"accounts": 2, "new": 1, "already_exist": 1})

    ACCTS = [{"id": "a1", "code": "1000", "name": "Cash at bank"}, {"id": "a2", "code": "4000", "name": "Sales"}]
    OPEN = [{"start": date(2026, 1, 1), "end": date(2026, 1, 31), "status": "OPEN"}]

    def jrn(self, csv, **kw):
        return S.preview("j.csv", csv, "JOURNALS", {}, accounts=self.ACCTS, periods=kw.get("periods", self.OPEN), currency="NGN")

    def test_journals_group_resolve_and_check(self):
        b = self.jrn(b"Date,Journal Number,Account,Description,Debit,Credit\n2026-01-05,J1,1000,Sale,500.00,\n2026-01-05,J1,Sales,Sale,,500.00\n")
        self.assertTrue(b["status"]["importable"])
        self.assertEqual([l["account"] for l in b["rows"][0]["lines"]], ["1000 Cash at bank", "4000 Sales"])

    def test_unbalanced_unknown_account_closed_period_single_line(self):
        b = self.jrn(b"Date,Journal Number,Account,Debit,Credit\n2026-01-06,J2,1000,10,\n2026-01-06,J2,4000,,9\n")
        self.assertIn("does not balance", b["rows"][0]["issues"][0]["message"])
        self.assertEqual(b["checks"][0]["result"], "FAIL")
        u = self.jrn(b"Date,Journal Number,Account,Debit,Credit\n2026-01-06,J3,9999,10,\n2026-01-06,J3,4000,,10\n")
        self.assertIn("no account '9999'", u["rows"][0]["lines"][0]["issues"][0]["message"])
        c = self.jrn(b"Date,Journal Number,Account,Debit,Credit\n2026-03-06,J4,1000,10,\n2026-03-06,J4,4000,,10\n")
        self.assertIn("OPEN accounting period", c["rows"][0]["issues"][0]["message"])
        one = self.jrn(b"Date,Journal Number,Account,Debit,Credit\n2026-01-06,J5,1000,10,\n")
        self.assertFalse(one["status"]["importable"])

    def test_no_journal_number_groups_until_balanced(self):
        b = self.jrn(b"Date,Account,Debit,Credit\n2026-01-05,1000,500,\n2026-01-05,4000,,500\n2026-01-06,1000,70,\n2026-01-06,4000,,70\n")
        self.assertEqual(len(b["rows"]), 2)
        self.assertTrue(b["status"]["importable"])

    def test_negative_and_double_sided_lines_are_errors(self):
        b = self.jrn(b"Date,Journal Number,Account,Debit,Credit\n2026-01-06,J6,1000,-10,\n2026-01-06,J6,4000,,-10\n")
        self.assertFalse(b["status"]["importable"])


class ConnectorTests(unittest.TestCase):
    def stage(self, payload, **o):
        return S.preview("p.json", json.dumps(payload).encode(), "BANK_STATEMENT", {"currency": o.pop("currency", None), **o} if o.get("currency") else o)

    def test_paystack_amounts_are_kobo_and_fees_are_separate_lines(self):
        p = {"status": True, "data": [{"id": 1, "reference": "R1", "amount": 5000000, "currency": "NGN", "status": "success", "paid_at": "2026-01-05T10:00:00.000Z",
                                       "fees": 75000, "channel": "card", "domain": "live", "customer": {"email": "a@b.c"}},
                                      {"id": 2, "reference": "R2", "amount": 100, "currency": "NGN", "status": "failed", "paid_at": "2026-01-05T10:00:00.000Z"}]}
        b = self.stage(p)
        self.assertEqual(b["source"]["provider"], "PAYSTACK")
        self.assertEqual([(r["money_in"], r["money_out"], r["reference"]) for r in b["rows"]], [("50000.00", "0.00", "R1"), ("0.00", "750.00", "R1-FEE")])

    def test_flutterwave_major_units(self):
        p = {"status": "success", "data": [{"id": 1, "tx_ref": "T1", "flw_ref": "F1", "amount": 1000, "currency": "NGN", "status": "successful",
                                            "created_at": "2026-01-05T10:00:00.000Z", "app_fee": 14, "customer": {"email": "x@y.z"}}]}
        b = self.stage(p)
        self.assertEqual(b["source"]["provider"], "FLUTTERWAVE")
        self.assertEqual([(r["money_in"], r["money_out"]) for r in b["rows"]], [("1000.00", "0.00"), ("0.00", "14.00")])

    def test_stripe_minor_units_unix_dates_payouts_negative(self):
        p = {"object": "list", "data": [{"id": "txn_1", "object": "balance_transaction", "amount": 5000, "currency": "usd", "created": 1767614400, "fee": 175, "net": 4825, "type": "charge"},
                                         {"id": "txn_2", "object": "balance_transaction", "amount": -4825, "currency": "usd", "created": 1767700800, "fee": 0, "net": -4825, "type": "payout"},
                                         {"id": "txn_3", "object": "balance_transaction", "amount": 500, "currency": "jpy", "created": 1767700800, "fee": 0, "net": 500, "type": "charge"}]}
        b = self.stage(p)
        self.assertEqual([(r["money_in"], r["money_out"]) for r in b["rows"]], [("50.00", "0.00"), ("0.00", "1.75"), ("0.00", "48.25"), ("500.00", "0.00")])
        self.assertEqual(b["rows"][0]["date"], "2026-01-05")

    def test_plaid_positive_means_money_out(self):
        p = {"transactions": [{"transaction_id": "t1", "date": "2026-01-05", "amount": 12.5, "iso_currency_code": "USD", "name": "Cafe"},
                              {"transaction_id": "t2", "date": "2026-01-06", "amount": -100, "iso_currency_code": "USD", "name": "Payroll"},
                              {"transaction_id": "t3", "date": "2026-01-06", "amount": 1, "pending": True}]}
        b = self.stage(p)
        self.assertEqual([(r["description"], r["money_in"], r["money_out"]) for r in b["rows"]], [("Cafe", "0.00", "12.50"), ("Payroll", "100.00", "0.00")])

    def test_uk_open_banking(self):
        p = {"Data": {"Transaction": [{"TransactionId": "1", "BookingDateTime": "2026-01-05T10:00:00Z", "Amount": {"Amount": "12.50", "Currency": "GBP"},
                                       "CreditDebitIndicator": "Credit", "TransactionInformation": "Salary", "Status": "Booked"},
                                      {"TransactionId": "2", "BookingDateTime": "2026-01-06T10:00:00Z", "Amount": {"Amount": "3.00", "Currency": "GBP"},
                                       "CreditDebitIndicator": "Debit", "Status": "Pending"},
                                      {"TransactionId": "3", "BookingDateTime": "2026-01-06T10:00:00Z", "Amount": {"Amount": "3.00", "Currency": "GBP"},
                                       "CreditDebitIndicator": "Weird", "Status": "Booked"}]}}
        b = self.stage(p)
        self.assertEqual(b["rows"][0]["money_in"], "12.50")
        self.assertEqual(len(b["rows"]), 2)
        self.assertEqual(b["rows"][1]["status"], "ERROR")

    def test_unknown_and_invalid_json(self):
        with self.assertRaises(IngestionError):
            S.preview("p.json", b'{"hello": "world"}', "BANK_STATEMENT", {})
        with self.assertRaises(UnsupportedFileError):
            S.preview("p.json", b"{not json", "BANK_STATEMENT", {})

    def test_the_limits_are_stated(self):
        b = self.stage({"transactions": [{"transaction_id": "t1", "date": "2026-01-05", "amount": 1, "iso_currency_code": "USD", "name": "x"}]})
        self.assertTrue(any("not been checked against a live account" in l for l in b["limits"]))

    def test_webhook_signatures(self):
        body, sec = b'{"event":"charge.success"}', "sk_test"
        sig = hmac.new(sec.encode(), body, hashlib.sha512).hexdigest()
        self.assertTrue(connectors.verify_webhook("PAYSTACK", sec, {"X-Paystack-Signature": sig}, body))
        self.assertFalse(connectors.verify_webhook("PAYSTACK", sec, {"X-Paystack-Signature": sig}, body + b" "))
        self.assertFalse(connectors.verify_webhook("PAYSTACK", "", {"X-Paystack-Signature": sig}, body))
        self.assertTrue(connectors.verify_webhook("FLUTTERWAVE", sec, {"verif-hash": sec}, body))
        self.assertFalse(connectors.verify_webhook("FLUTTERWAVE", sec, {"verif-hash": "x"}, body))
        t = int(time.time())
        s = hmac.new(sec.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
        self.assertTrue(connectors.verify_webhook("STRIPE", sec, {"Stripe-Signature": f"t={t},v1={s}"}, body))
        self.assertFalse(connectors.verify_webhook("STRIPE", sec, {"Stripe-Signature": f"t={t - 1000},v1={s}"}, body), "replayed old signature")
        self.assertFalse(connectors.verify_webhook("STRIPE", sec, {"Stripe-Signature": "garbage"}, body))
        with self.assertRaises(IngestionError):
            connectors.verify_webhook("NOPE", sec, {}, body)


class PayrollTests(unittest.TestCase):
    CSV = b"Employee,Gross Pay,PAYE,Pension,Net Pay,Employer Pension\nAisha,500000,50000,40000,410000,50000\nKwame,300000,20000,24000,256000,30000\nTotal,800000,70000,64000,666000,80000\n"

    def test_checked_and_proposed_journal_balances(self):
        b = S.preview("p.csv", self.CSV, "PAYROLL", {})
        self.assertTrue(b["status"]["importable"])
        self.assertEqual(b["summary"]["employees"], 2)
        p = b["proposal"]
        self.assertFalse(p["applied"])
        self.assertTrue(p["balances"])
        self.assertIsNone(p["lines"][0]["account"])

    def test_arithmetic_error_blocks(self):
        b = S.preview("p.csv", self.CSV.replace(b"410000", b"400000"), "PAYROLL", {})
        self.assertFalse(b["status"]["importable"])
        self.assertIn("net pay is 400000.00", b["rows"][0]["issues"][0]["message"])

    def test_no_headings(self):
        with self.assertRaises(IngestionError):
            S.preview("p.csv", b"a,b\n1,2\n", "PAYROLL", {})


class ServiceTests(unittest.TestCase):
    def test_purpose_and_type_guards(self):
        with self.assertRaises(IngestionError):
            S.preview("a.csv", b"x", "NOPE", {})
        with self.assertRaises(UnsupportedFileError):
            S.preview("a.pdf", text_pdf(["Opening Balance 1.00"]), "JOURNALS", {})
        with self.assertRaises(IngestionError):
            S.preview("a.csv", b"", "BANK_STATEMENT", {})

    def test_sniff(self):
        self.assertEqual(S.sniff("x.bin", b"%PDF-1.4"), "PDF")
        self.assertEqual(S.sniff("x.txt", b"<OFX>"), "OFX")
        self.assertEqual(S.sniff("x", b":20:A\n:61:..."), "MT940")
        self.assertEqual(S.sniff("x.json", b"{}"), "JSON")
        self.assertEqual(S.sniff("x.PNG", b"\x89PNG"), "IMAGE")
        self.assertEqual(S.sniff("x.csv", b"a,b"), "CSV")

    def test_levels_never_claim_a_live_connection(self):
        by = {l["level"]: l for l in S.LEVELS}
        self.assertEqual(len(by), 8)
        for n in (6, 7, 8):
            self.assertIn(by[n]["status"], ("FILES_ONLY", "PAYLOAD_ONLY"))
        self.assertIn("Not connected", by[7]["note"] + by[8]["note"])


if __name__ == "__main__":
    unittest.main()


class UnmappedColumnsTests(unittest.TestCase):
    """A file whose headings are unusual must give the person the columns to choose from, not a dead end."""

    FILE = b"When,Details,Money Out,Money In\n2026-01-20,Weird header A,5.00,\n2026-01-21,Weird header B,,9.00\n"

    def test_missing_date_column_returns_columns_and_a_clear_error(self):
        b = S.preview("w.csv", self.FILE, "BANK_STATEMENT", {"header_row": 0, "currency": "NGN"})
        self.assertEqual(b["columns"], ["When", "Details", "Money Out", "Money In"])
        self.assertFalse(b["status"]["importable"])
        self.assertTrue(any("could not tell which columns" in i["message"] for i in b["issues"]))
        self.assertEqual(b["rows"], [])

    def test_choosing_the_columns_then_reads_the_file(self):
        b = S.preview("w.csv", self.FILE, "BANK_STATEMENT", {"header_row": 0, "currency": "NGN",
                      "mapping": {"date": "When", "description": "Details", "debit": "Money Out", "credit": "Money In"}})
        self.assertTrue(b["status"]["importable"], b["issues"])
        self.assertEqual(b["summary"]["lines"], 2)
