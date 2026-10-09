"""The staged batch every importer returns. A batch is a *proposal*: it can be inspected, fingerprinted and
re-created from the same file, but it is never itself a ledger record."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

SCHEMA = "asavexa-ingest/1"
ERROR, WARNING, INFO = "ERROR", "WARNING", "INFO"
MAX_ROWS_SHOWN = 1000

KINDS = ("BANK_TRANSACTIONS", "DOCUMENT", "CHART_OF_ACCOUNTS", "JOURNALS", "PAYROLL")


def canonical(obj: Any) -> str:
    def default(o):
        if isinstance(o, (date, datetime)):
            return o.isoformat()
        if isinstance(o, Decimal):
            return f"{o:.2f}"
        raise TypeError(type(o))
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=default)


def issue(level: str, message: str, row: Optional[int] = None, field: Optional[str] = None) -> dict:
    d = {"level": level, "message": message}
    if row is not None:
        d["row"] = row
    if field:
        d["field"] = field
    return d


def check(key: str, label: str, result: str, detail: str) -> dict:
    return {"key": key, "label": label, "result": result, "detail": detail}


def new_batch(kind: str, source: dict, options: dict) -> dict:
    assert kind in KINDS
    return {"schema": SCHEMA, "kind": kind, "source": source, "options": options, "mapping": {}, "rows": [], "issues": [],
            "checks": [], "summary": {}, "limits": []}


def finalize(batch: dict, *, core: Any) -> dict:
    """Counts problems, decides importability, and fingerprints the staged content.
    `core` is the exact data that would be imported (so the fingerprint changes if and only if the import would)."""
    rows = batch["rows"]
    errors = sum(1 for r in rows if r.get("status") == "ERROR") + sum(1 for i in batch["issues"] if i["level"] == ERROR)
    warns = sum(1 for r in rows if r.get("status") == "WARNING") + sum(1 for i in batch["issues"] if i["level"] == WARNING)
    failed = [c for c in batch["checks"] if c["result"] == "FAIL"]
    batch["problem_rows"] = [r for r in rows if r.get("status") in ("ERROR", "WARNING")][:200]
    batch["status"] = {
        "errors": errors, "warnings": warns, "failed_checks": len(failed),
        "importable": errors == 0 and bool(core),
        "needs_acknowledgement": errors == 0 and (warns > 0 or bool(failed)),
    }
    batch["fingerprint"] = hashlib.sha256(canonical({"core": core, "source": batch["source"].get("sha256"),
                                                      "options": batch["options"], "kind": batch["kind"]}).encode()).hexdigest()
    return batch


def display_copy(batch: dict) -> dict:
    """The version sent to the browser: long batches show the first rows plus every problem row (the full set stays server-side)."""
    out = dict(batch)
    rows = batch.get("rows") or []
    if len(rows) > MAX_ROWS_SHOWN:
        out["rows_total"] = len(rows)
        out["rows"] = rows[:MAX_ROWS_SHOWN]
    return out
