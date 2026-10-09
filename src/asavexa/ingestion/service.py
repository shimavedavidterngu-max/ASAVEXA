"""One entry point: bytes in -> staged batch out. Detects the file type and sends it to the right reader.
`preview` never writes anything; the API layer decides what a confirmed batch becomes."""
from __future__ import annotations

import json
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from . import model as M
from .accounting_export import stage_chart_of_accounts, stage_journals
from .bank import stage_bank_table
from .connectors import PROVIDERS, stage_provider_json
from .documents import stage_document
from .errors import IngestionError, NoTextError, UnsupportedFileError
from .formats import stage_mt940, stage_ofx
from .payroll import stage_payroll
from .pdfread import extract_pdf_text, stage_pdf_statement
from .tabular import MAX_BYTES, read_table
from .util import sha256_hex

PURPOSES = ("BANK_STATEMENT", "DOCUMENT", "CHART_OF_ACCOUNTS", "JOURNALS", "PAYROLL")
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".gif", ".tif", ".tiff", ".webp", ".heic", ".bmp")

LEVELS = [
    {"level": 1, "name": "CSV files", "status": "WORKING", "purposes": ["BANK_STATEMENT", "CHART_OF_ACCOUNTS", "JOURNALS", "PAYROLL"],
     "note": "Any delimiter, UTF-8 or Excel encoding, header row found automatically, columns mapped by name (you can override)."},
    {"level": 2, "name": "Excel files", "status": "WORKING", "purposes": ["BANK_STATEMENT", "CHART_OF_ACCOUNTS", "JOURNALS", "PAYROLL"],
     "note": "Excel (.xlsx). Old .xls files must be re-saved as .xlsx or CSV. Formulas are read as their saved values."},
    {"level": 3, "name": "Bank statements", "status": "WORKING", "purposes": ["BANK_STATEMENT"],
     "note": "CSV/Excel, OFX/QFX and MT940, with running-balance and opening/closing checks and duplicate handling."},
    {"level": 4, "name": "PDF documents", "status": "PARTIAL", "purposes": ["BANK_STATEMENT", "DOCUMENT"],
     "note": "PDFs that contain text. Scanned or photographed PDFs are not read (no OCR); they can be stored as evidence."},
    {"level": 5, "name": "Receipts and invoices", "status": "PARTIAL", "purposes": ["DOCUMENT"],
     "note": "Vendor, number, dates, subtotal/tax/total read from PDF or text with a source line and confidence for each. Line items and images are not read."},
    {"level": 6, "name": "Accounting software", "status": "FILES_ONLY", "purposes": ["CHART_OF_ACCOUNTS", "JOURNALS"],
     "note": "Imports exports from Xero, QuickBooks, Sage and similar. Live connections to those products are not available. Journals arrive as drafts."},
    {"level": 7, "name": "Bank APIs", "status": "PAYLOAD_ONLY", "purposes": ["BANK_STATEMENT"],
     "note": "Reads saved JSON from Plaid and UK Open Banking. Not connected to any bank; shapes are not verified against a live account."},
    {"level": 8, "name": "Payroll and payment platforms", "status": "PAYLOAD_ONLY", "purposes": ["BANK_STATEMENT", "PAYROLL"],
     "note": "Reads saved JSON from Paystack, Flutterwave and Stripe, and payroll registers (checked, with a proposed journal). Not connected to any provider."},
]


def sniff(filename: str, content: bytes) -> str:
    n = (filename or "").lower()
    head = content[:2048].lstrip()
    if content[:5] == b"%PDF-" or n.endswith(".pdf"):
        return "PDF"
    if n.endswith((".ofx", ".qfx")) or b"<OFX" in content[:4096].upper() or head.upper().startswith(b"OFXHEADER"):
        return "OFX"
    if n.endswith((".sta", ".mt940", ".940", ".swi")) or (b":20:" in content[:600] and (b":61:" in content or b":60F:" in content)):
        return "MT940"
    if n.endswith(".json") or head[:1] in (b"{", b"["):
        return "JSON"
    if n.endswith(IMAGE_EXT):
        return "IMAGE"
    if n.endswith((".xlsx", ".xlsm", ".xls")) or content[:4] == b"PK\x03\x04" or content[:8] == bytes.fromhex("D0CF11E0A1B11AE1"):
        return "EXCEL"
    if n.endswith((".txt",)):
        return "TEXT"
    return "CSV"


def preview(filename: str, content: bytes, purpose: str, options: Optional[dict] = None, *, accounts: Optional[List[dict]] = None,
            periods: Optional[List[dict]] = None, currency: Optional[str] = None, existing_codes: Optional[Dict[str, str]] = None) -> dict:
    """Parse `content` for `purpose` and return a staged batch. Raises IngestionError for files that cannot be read at all."""
    options = dict(options or {})
    if purpose not in PURPOSES:
        raise IngestionError(f"purpose must be one of: {', '.join(PURPOSES)}.")
    if not content:
        raise IngestionError("The file is empty.")
    if len(content) > MAX_BYTES:
        raise IngestionError(f"The file is larger than {MAX_BYTES // (1024 * 1024)} MB.")
    if currency and not options.get("currency"):
        options["currency"] = currency
    kind = sniff(filename, content)
    source = {"filename": (filename or "unnamed")[:200], "size": len(content), "sha256": sha256_hex(content), "detected_as": kind}

    if purpose == "DOCUMENT":
        if kind == "PDF":
            try:
                text, pages = extract_pdf_text(content)
            except NoTextError:
                return stage_document(source, options, None, "SCANNED_PDF")   # keep it as evidence; nothing is read
            return stage_document(source, options, text, "PDF", pages)
        if kind == "TEXT" or kind == "CSV" and (filename or "").lower().endswith(".txt"):
            from .tabular import decode_text
            return stage_document(source, options, decode_text(content)[0], "TEXT")
        if kind == "IMAGE":
            return stage_document(source, options, None, "IMAGE")
        raise UnsupportedFileError("Documents must be PDF (with text), a text file, or an image (stored without reading).")

    if purpose == "BANK_STATEMENT":
        if kind == "PDF":
            text, pages = extract_pdf_text(content)
            return stage_pdf_statement(filename, text, pages, source, options)
        if kind == "OFX":
            return stage_ofx(filename, content, source, options)
        if kind == "MT940":
            return stage_mt940(filename, content, source, options)
        if kind == "JSON":
            return stage_provider_json(content, source, options)
        if kind in ("CSV", "EXCEL", "TEXT"):
            table = read_table(filename, content, options.get("sheet"), options.get("delimiter"))
            return stage_bank_table(filename, table, source, options)
        raise UnsupportedFileError("A bank statement must be CSV, Excel, OFX, MT940, PDF (with text) or a provider JSON export.")

    if kind not in ("CSV", "EXCEL", "TEXT"):
        raise UnsupportedFileError(f"{purpose.replace('_', ' ').title()} imports need a CSV or Excel (.xlsx) file.")
    table = read_table(filename, content, options.get("sheet"), options.get("delimiter"))
    if purpose == "CHART_OF_ACCOUNTS":
        return stage_chart_of_accounts(table, source, options, existing_codes)
    if purpose == "JOURNALS":
        return stage_journals(table, source, options, accounts or [], periods or [], currency or options.get("currency") or "NGN")
    return stage_payroll(table, source, options)
