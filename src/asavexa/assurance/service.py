"""Counts, per kind of record, how many records carry each kind of assurance (Stage 12). Read-only.

It does not own any data. Each module supplies its records through a small provider function; this service maps each one with the shared vocabulary and
counts. A provider that fails is reported as unavailable instead of being left out silently, and a status that is not in the vocabulary is counted as "not mapped",
never as assured. Everything is for one organisation, and a provider is only ever called with that organisation's id."""
from __future__ import annotations

from typing import Callable, Dict, Iterable, List, Tuple

from .vocabulary import FACETS, FLAGS, RECORD_TEXT, safe_classify

Record = Tuple[str, str, dict]            # (id, native status, facts)
Provider = Callable[[str], Iterable[Record]]
MAX_EXAMPLES = 5


class AssuranceService:
    def __init__(self, providers: Dict[str, Provider]):
        self.providers = dict(providers)

    def summary(self, org: str) -> dict:
        rows: List[dict] = []
        for rtype in sorted(self.providers, key=lambda t: list(RECORD_TEXT).index(t) if t in RECORD_TEXT else 99):
            try:
                records = list(self.providers[rtype](org))
            except Exception:
                rows.append({"type": rtype, "label": RECORD_TEXT.get(rtype, rtype), "available": False, "total": 0, "facets": {}, "flags": {}, "unmapped": 0, "can_rely_on": 0, "attention": []})
                continue
            facets = {f: 0 for f in FACETS}; flags = {f: 0 for f in FLAGS}
            unmapped = rely = 0
            attention: List[dict] = []
            for rid, status, facts in records:
                c = safe_classify(rtype, status, facts)
                if c["headline"] == "Not mapped":
                    unmapped += 1
                for f in c["facets"]:
                    facets[f] += 1
                if c["flag"]:
                    flags[c["flag"]] += 1
                    if len(attention) < MAX_EXAMPLES:
                        attention.append({"id": rid, "status": status, "headline": c["headline"], "flag": c["flag"]})
                rely += bool(c["can_rely_on"])
            rows.append({"type": rtype, "label": RECORD_TEXT.get(rtype, rtype), "available": True, "total": len(records), "facets": facets, "flags": flags,
                         "unmapped": unmapped, "can_rely_on": rely, "attention": attention})
        return {"records": rows, "covered": [r["type"] for r in rows],
                "note": "Counts of what ASAVEXA has checked about each kind of record. They do not say the figures are right. Record types that are not listed are not yet included."}
