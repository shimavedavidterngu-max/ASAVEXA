"""Levels 1 and 2: read CSV and Excel (.xlsx) files into plain rows, find the header, and map columns.

Pure functions over bytes. No guessing is hidden: the chosen delimiter, encoding, sheet, header row and
column mapping are all returned so a person can see (and override) them in the preview.
"""
from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from .errors import IngestionError, UnsupportedFileError
from .util import clean, norm_header

MAX_BYTES = 10 * 1024 * 1024
MAX_ROWS = 20000
HEADER_SCAN_ROWS = 40

FIELD_SYNONYMS: Dict[str, List[str]] = {
    "date": ["date", "transaction date", "trans date", "txn date", "tran date", "posting date", "booking date", "post date",
             "date posted", "entry date", "posted date", "trans dt"],
    "value_date": ["value date", "val date", "effective date", "value dt"],
    "description": ["description", "details", "narration", "narrative", "particulars", "memo", "transaction details", "remarks",
                    "transaction description", "payee", "reference description", "details of transaction"],
    "reference": ["reference", "ref", "ref no", "reference number", "reference no", "transaction id", "txn id", "transaction ref",
                  "cheque no", "check number", "cheque number", "trans ref", "transaction reference", "id", "tran id"],
    "amount": ["amount", "transaction amount", "amt", "net amount", "value"],
    "debit": ["debit", "debits", "withdrawal", "withdrawals", "money out", "paid out", "dr", "debit amount", "payments out",
              "amount debited", "debit amt"],
    "credit": ["credit", "credits", "deposit", "deposits", "money in", "paid in", "cr", "credit amount", "payments in",
               "amount credited", "credit amt", "lodgement", "lodgements"],
    "balance": ["balance", "running balance", "closing balance", "bal", "available balance", "ledger balance", "balance after"],
    "dr_cr": ["type", "dr cr", "debit credit", "cr dr", "transaction type", "indicator", "dc", "d c", "sign"],
    "currency": ["currency", "ccy", "cur", "currency code"],
}


@dataclass
class Table:
    rows: List[List[Any]]                      # every row of the chosen sheet/file, native cell values
    source: Dict[str, Any]                     # format, encoding, delimiter, sheet, sheets, ...
    warnings: List[str] = field(default_factory=list)


def _is_blank(row) -> bool:
    return all(clean(c) == "" for c in row)


# ------------------------------------------------------------------ CSV
def decode_text(content: bytes) -> Tuple[str, str, List[str]]:
    warns: List[str] = []
    if content.startswith(b"\xff\xfe") or content.startswith(b"\xfe\xff"):
        return content.decode("utf-16"), "utf-16", warns
    if content.startswith(b"\xef\xbb\xbf"):
        return content.decode("utf-8-sig"), "utf-8", warns
    try:
        return content.decode("utf-8"), "utf-8", warns
    except UnicodeDecodeError:
        warns.append("The file is not UTF-8; it was read as Windows-1252 (Excel's usual encoding). Check names with accents.")
        return content.decode("cp1252", errors="replace"), "windows-1252", warns


def _sniff_delimiter(text: str) -> str:
    sample = [ln for ln in text.splitlines()[:60] if ln.strip()]
    best, best_score = ",", -1.0
    for d in [",", ";", "\t", "|"]:
        counts = []
        for row in csv.reader(sample, delimiter=d):
            counts.append(len(row))
        if not counts:
            continue
        common = max(set(counts), key=counts.count)
        if common < 2:
            continue
        score = counts.count(common) / len(counts) + common * 0.01
        if score > best_score:
            best, best_score = d, score
    return best


def read_csv(content: bytes, delimiter: Optional[str] = None) -> Table:
    if not content.strip():
        raise IngestionError("The file is empty.")
    if b"\x00" in content[:4096] and not (content.startswith(b"\xff\xfe") or content.startswith(b"\xfe\xff")):
        raise UnsupportedFileError("This does not look like a text/CSV file (it contains binary data).")
    text, enc, warns = decode_text(content)
    d = delimiter or _sniff_delimiter(text)
    try:
        rows = [list(r) for r in csv.reader(io.StringIO(text, newline=""), delimiter=d, strict=False)]
    except csv.Error as e:
        raise IngestionError(f"The CSV file could not be read: {e}")
    if len(rows) > MAX_ROWS:
        raise IngestionError(f"The file has more than {MAX_ROWS:,} rows. Split it by month and import each part.")
    return Table(rows, {"format": "CSV", "encoding": enc, "delimiter": {"\t": "TAB"}.get(d, d)}, warns)


# ------------------------------------------------------------------ Excel
def _cell(v):
    if isinstance(v, datetime):
        return v.date() if (v.hour, v.minute, v.second) == (0, 0, 0) else v
    if isinstance(v, float):
        return int(v) if v.is_integer() and abs(v) < 1e15 else Decimal(repr(v))
    return v


def read_xlsx(content: bytes, sheet: Optional[str] = None) -> Table:
    if content[:8] == bytes.fromhex("D0CF11E0A1B11AE1"):
        raise UnsupportedFileError("This is an old Excel (.xls) file. Open it in Excel and use Save As > Excel Workbook (.xlsx), or save it as CSV.")
    if not zipfile.is_zipfile(io.BytesIO(content)):
        raise UnsupportedFileError("This is not a valid Excel (.xlsx) file.")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            if sum(i.file_size for i in z.infolist()) > 200 * 1024 * 1024:
                raise UnsupportedFileError("This Excel file expands to an unreasonable size and was refused.")
            has_macros = any(n.lower().endswith("vbaproject.bin") for n in z.namelist())
    except zipfile.BadZipFile:
        raise UnsupportedFileError("This is not a valid Excel (.xlsx) file.")
    try:
        from openpyxl import load_workbook
    except ImportError:  # pragma: no cover
        raise IngestionError("Excel support is not installed on this server (openpyxl).")
    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as e:
        raise UnsupportedFileError(f"The Excel file could not be opened: {e}")
    warns: List[str] = []
    if has_macros:
        warns.append("This workbook contains macros. They were ignored; only the cell values were read.")
    names = [ws.title for ws in wb.worksheets if ws.sheet_state == "visible"] or [ws.title for ws in wb.worksheets]
    if not names:
        raise IngestionError("The workbook has no sheets.")
    sheets: Dict[str, List[List[Any]]] = {}
    for n in names:
        ws = wb[n]
        rows = []
        for r in ws.iter_rows(values_only=True):
            rows.append([_cell(c) for c in r])
            if len(rows) > MAX_ROWS + HEADER_SCAN_ROWS:
                raise IngestionError(f"Sheet {n!r} has more than {MAX_ROWS:,} rows. Split it by month.")
        while rows and _is_blank(rows[-1]):
            rows.pop()
        sheets[n] = rows
    wb.close()
    if sheet is not None:
        if sheet not in sheets:
            raise IngestionError(f"There is no sheet called {sheet!r}. Sheets: {', '.join(names)}.")
        chosen = sheet
    else:
        chosen = max(names, key=lambda n: sum(1 for r in sheets[n] if not _is_blank(r)))
        if len([n for n in names if sheets[n]]) > 1:
            warns.append(f"The workbook has several sheets ({', '.join(names)}); the one with most rows ({chosen!r}) was read. Choose another if needed.")
    return Table(sheets[chosen], {"format": "XLSX", "sheet": chosen, "sheets": names}, warns)


# ------------------------------------------------------------------ header + mapping
def _field_for_header(h: str) -> Optional[str]:
    h = norm_header(h)
    if not h:
        return None
    for fld, syns in FIELD_SYNONYMS.items():
        if h in syns:
            return fld
    return None


def find_header_row(rows: List[List[Any]], need: Tuple[str, ...] = ("date",)) -> Optional[int]:
    """The first row (within the first 40) whose cells name at least two known fields, including every field in `need`."""
    best, best_score = None, 1
    for i, row in enumerate(rows[:HEADER_SCAN_ROWS]):
        fields = [_field_for_header(c) for c in row if isinstance(c, str)]
        fields = [f for f in fields if f]
        if not all(n in fields for n in need):
            continue
        score = len(set(fields))
        if score > best_score:
            best, best_score = i, score
    return best


def detect_mapping(header: List[Any]) -> Dict[str, int]:
    """field -> column index, each column and each field used once (first match wins)."""
    mapping: Dict[str, int] = {}
    for idx, cell in enumerate(header):
        f = _field_for_header(cell) if isinstance(cell, str) else None
        if f and f not in mapping:
            mapping[f] = idx
    return mapping


def resolve_mapping_override(header: List[Any], override: Optional[Dict[str, Any]]) -> Dict[str, int]:
    """`override` maps field -> header text or column index (or "" / None to un-map)."""
    mapping = detect_mapping(header)
    for f, v in (override or {}).items():
        if f not in FIELD_SYNONYMS:
            raise IngestionError(f"Unknown column role {f!r}.")
        if v in (None, ""):
            mapping.pop(f, None)
            continue
        if isinstance(v, int) or (isinstance(v, str) and v.isdigit() and norm_header(v) not in [norm_header(h) for h in header]):
            idx = int(v)
            if not (0 <= idx < len(header)):
                raise IngestionError(f"Column number {idx} does not exist.")
        else:
            matches = [i for i, h in enumerate(header) if norm_header(h) == norm_header(v)]
            if not matches:
                raise IngestionError(f"There is no column headed {v!r}.")
            idx = matches[0]
        mapping[f] = idx
    used: Dict[int, str] = {}
    for f, i in list(mapping.items()):
        if i in used:
            raise IngestionError(f"Column {clean(header[i])!r} is mapped to both {used[i]!r} and {f!r}.")
        used[i] = f
    return mapping


def read_table(filename: str, content: bytes, sheet: Optional[str] = None, delimiter: Optional[str] = None) -> Table:
    if len(content) > MAX_BYTES:
        raise IngestionError(f"The file is larger than {MAX_BYTES // (1024 * 1024)} MB.")
    if not content:
        raise IngestionError("The file is empty.")
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")) or content[:4] == b"PK\x03\x04":
        return read_xlsx(content, sheet)
    if name.endswith(".xls") or content[:8] == bytes.fromhex("D0CF11E0A1B11AE1"):
        return read_xlsx(content, sheet)  # raises the friendly .xls message
    return read_csv(content, delimiter)
