"""One shared vocabulary for "how far has this record been checked?" (Stage 12).

Every module keeps its own status words (a journal is POSTED, evidence is VERIFIED, a finding is RESOLVED, a case is ACTION_DONE...). This module does not
replace them. It maps each one onto six plain kinds of assurance a record can carry, so a person can compare across modules without learning each one:

    recorded                the record exists and is part of the books or the register
    supported               something backs it up (a document, a matching bank line)
    reconciled              it was agreed to an independent outside record
    reviewed                a person looked at it and decided
    approved                a person with authority approved it
    independently_verified  a person who did NOT prepare, own or approve it confirmed it, enforced by the system, not just claimed

These are not a score and not a ladder: they are facts a record has. A record can carry several. "Reconciled" and "approved" are not ranked against each other.
Each status also gets a plain headline, and may carry ONE flag that says why it should not be relied on right now:

    CONTESTED     conflicts with, or duplicates, another record
    INCOMPLETE    something required is missing
    REJECTED      a person turned it down
    EXPIRED       it was good once but is out of date
    RETIRED       it has been replaced or reversed

`can_rely_on` is true only when the record carries at least one fact beyond being recorded AND has no flag. It says nothing about whether the figures are right.
Every native status of every mapped module is listed in TABLE, and a test fails if a module adds a status that is not mapped here.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional

FACETS = ("recorded", "supported", "reconciled", "reviewed", "approved", "independently_verified")
FLAGS = ("CONTESTED", "INCOMPLETE", "REJECTED", "EXPIRED", "RETIRED")

FACET_TEXT: Dict[str, Dict[str, str]] = {
    "recorded": {"label": "Recorded", "meaning": "The record exists in the books or a register. Nothing more is claimed."},
    "supported": {"label": "Supported", "meaning": "Something backs it up, such as a document or a matching bank line."},
    "reconciled": {"label": "Reconciled", "meaning": "It was agreed to an independent outside record, such as a bank statement."},
    "reviewed": {"label": "Reviewed", "meaning": "A person looked at it and decided."},
    "approved": {"label": "Approved", "meaning": "A person with the authority to approve it did so."},
    "independently_verified": {"label": "Independently verified", "meaning": "A person who did not prepare, own or approve it confirmed it, and the system enforces that."},
}
FLAG_TEXT = {
    "CONTESTED": "Conflicts with, or duplicates, another record.",
    "INCOMPLETE": "Something required is missing.",
    "REJECTED": "A person turned it down.",
    "EXPIRED": "It was good once but is out of date.",
    "RETIRED": "It has been replaced or reversed.",
}

R, S, RC, RV, A, IV = FACETS


def _row(facets, headline, flag=None, note=""):
    return {"facets": list(facets), "headline": headline, "flag": flag, "note": note}


# record type -> native status -> mapping. Native statuses are the exact words each module uses.
TABLE: Dict[str, Dict[str, dict]] = {
    "journal": {
        "DRAFT": _row([], "Draft", note="Not yet part of the books."),
        "POSTED": _row([R], "Recorded"),
        "REVERSED": _row([R], "Reversed", "RETIRED"),
    },
    "evidence": {
        "UPLOADED": _row([R], "Uploaded, not yet verified"),
        "VERIFIED": _row([R, RV], "Verified", note="Becomes independently verified when someone other than the uploader verified it (see classify)."),
        "INCOMPLETE": _row([R], "Incomplete", "INCOMPLETE"),
        "DUPLICATE": _row([R], "Duplicate", "CONTESTED"),
        "CONFLICTING": _row([R], "Conflicting", "CONTESTED"),
        "EXPIRED": _row([R], "Expired", "EXPIRED"),
        "REJECTED": _row([R], "Rejected", "REJECTED"),
    },
    "bank_transaction": {
        "IMPORTED": _row([R], "Imported"),
        "MATCHED": _row([R, S], "Matched, not yet reviewed"),
        "REVIEW_REQUIRED": _row([R, S], "Needs review", "INCOMPLETE"),
        "UNMATCHED": _row([R], "No match found", "INCOMPLETE"),
        "APPROVED": _row([R, S, RV, A], "Match approved"),
        "RECONCILED": _row([R, S, RC, RV, A], "Reconciled"),
        "REJECTED": _row([R], "Rejected", "REJECTED"),
    },
    "reconciliation": {
        "DRAFT": _row([], "Draft"),
        "SUBMITTED": _row([R], "Submitted, awaiting review"),
        "RECONCILED": _row([R, RC, RV, A], "Reconciled and approved"),
        "REJECTED": _row([R], "Rejected", "REJECTED"),
    },
    "period_close": {
        "REQUESTED": _row([R], "Close requested"),
        "READY_FOR_CLOSE": _row([R, RV], "Ready to close"),
        "CONTROLS_FAILED": _row([R], "Controls failed", "INCOMPLETE"),
        "CLOSED": _row([R, RV, A], "Closed"),
        "REJECTED": _row([R], "Rejected", "REJECTED"),
    },
    "finding": {
        "OPEN": _row([R], "Open"),
        "UNDER_REVIEW": _row([R], "Under review"),
        "REMEDIATION_REQUIRED": _row([R, RV], "Reviewed: action required"),
        "RESOLVED": _row([R, RV], "Resolved, awaiting independent check"),
        "VERIFIED": _row([R, RV, IV], "Independently verified", note="Only a different person can verify; the system refuses the same actor."),
        "CLOSED": _row([R, RV, IV], "Closed after verification", note="A finding cannot be closed without being verified first."),
    },
    "remediation": {
        "PLANNED": _row([R], "Planned"),
        "IN_PROGRESS": _row([R], "In progress"),
        "COMPLETED": _row([R], "Done, awaiting independent check"),
        "VERIFIED": _row([R, RV, IV], "Independently verified"),
    },
    "evidence_review_case": {
        "OPEN": _row([R], "Open: action needed"),
        "ACTION_PLANNED": _row([R], "Action planned"),
        "ACTION_DONE": _row([R], "Done, awaiting independent check"),
        "VERIFIED": _row([R, RV, IV], "Independently verified", note="The verifier cannot be the person who did or owns the work, and the figure is re-measured."),
        "REOPENED": _row([R], "Reopened: gaps returned", "INCOMPLETE"),
    },
    "standards_source": {
        "DRAFT": _row([], "Draft"),
        "UNDER_REVIEW": _row([R], "Under review"),
        "APPROVED": _row([R, RV, A, IV], "Approved by a second person", note="The approver cannot be the person who added or submitted it."),
        "SUPERSEDED": _row([R, RV, A, IV], "Replaced by a newer version", "RETIRED"),
        "WITHDRAWN": _row([R], "Withdrawn", "RETIRED"),
    },
    "analysis_report": {
        "DRAFT": _row([], "Draft"),
        "SUBMITTED": _row([R], "Submitted, awaiting review"),
        "APPROVED": _row([R, RV, A], "Approved"),
        "REJECTED": _row([R], "Rejected", "REJECTED"),
    },
    "agent_decision": {
        "NOT_NEEDED": _row([R], "Allowed by policy, no approval needed"),
        "PENDING": _row([R], "Waiting for approval"),
        "APPROVED": _row([R, RV, A, IV], "Approved by a different person", note="The approver cannot be the requester."),
        "REJECTED": _row([R], "Rejected", "REJECTED"),
        "REFUSED": _row([R], "Refused by policy", "REJECTED"),
        "EXPIRED": _row([R], "Approval expired", "EXPIRED"),
        "USED": _row([R, RV, A, IV], "Approved and used once"),
    },
}

RECORD_TEXT = {
    "journal": "Journal", "evidence": "Evidence", "bank_transaction": "Bank transaction", "reconciliation": "Reconciliation", "period_close": "Period close",
    "finding": "Finding", "remediation": "Remediation", "evidence_review_case": "Evidence Review case", "standards_source": "Standards source",
    "analysis_report": "Analysis report", "agent_decision": "Agent decision",
}


class UnknownStatus(ValueError):
    """A status that is not in the table. Callers must not guess: an unmapped status is shown as unknown, never as assured."""


def classify(record_type: str, status: str, facts: Optional[dict] = None) -> dict:
    """Maps one native status to the shared vocabulary.

    `facts` may carry `uploaded_by` and `verified_by` for evidence: verified by a DIFFERENT person than the uploader adds independently_verified.
    The result never claims more than the table allows."""
    rows = TABLE.get(record_type)
    if rows is None:
        raise UnknownStatus(f"Unknown record type {record_type!r}.")
    row = rows.get(str(status))
    if row is None:
        raise UnknownStatus(f"{record_type} has no status {status!r} in the vocabulary.")
    facets, headline = list(row["facets"]), row["headline"]
    if record_type == "evidence" and status == "VERIFIED":
        f = facts or {}
        if f.get("verified_by") and f.get("uploaded_by") and f["verified_by"] != f["uploaded_by"]:
            facets.append(IV); headline = "Independently verified"
        elif f.get("verified_by") and f.get("verified_by") == f.get("uploaded_by"):
            headline = "Verified by its own uploader"
    flag = row["flag"]
    return {"record_type": record_type, "status": status, "facets": facets, "headline": headline, "flag": flag,
            "can_rely_on": flag is None and any(x != R for x in facets), "note": row["note"]}


def unknown(record_type: str, status) -> dict:
    """What an unmapped status looks like to a person: honest about not knowing."""
    return {"record_type": record_type, "status": str(status), "facets": [], "headline": "Not mapped", "flag": None, "can_rely_on": False,
            "note": "This status is not in the shared vocabulary yet, so nothing is claimed for it."}


def safe_classify(record_type: str, status, facts: Optional[dict] = None) -> dict:
    try:
        return classify(record_type, status, facts)
    except UnknownStatus:
        return unknown(record_type, status)


def vocabulary() -> dict:
    """Everything a person needs to read the shared vocabulary: the six kinds of assurance, the flags, and how each module's words map."""
    return {
        "facets": [{"code": f, **FACET_TEXT[f]} for f in FACETS],
        "flags": [{"code": f, "meaning": FLAG_TEXT[f]} for f in FLAGS],
        "records": [{"type": t, "label": RECORD_TEXT[t],
                     "statuses": [{"status": s, "facets": r["facets"], "headline": r["headline"], "flag": r["flag"], "note": r["note"]} for s, r in rows.items()]}
                    for t, rows in TABLE.items()],
        "note": ("These are facts a record carries, not a score, and they are not ranked against each other. They describe how far a record was checked inside ASAVEXA. "
                 "They do not say the figures are right or that the organisation complies with any standard."),
    }
