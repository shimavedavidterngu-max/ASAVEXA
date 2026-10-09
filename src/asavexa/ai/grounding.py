"""The grounded-answer contract. Every AI answer item must carry the whole chain

    conclusion -> source records -> evidence -> journal -> accounting treatment
    -> reporting framework -> confidence -> human review requirement

`validate_item` refuses to let an item out unless every link is present, the conclusion is not
empty, and the conclusion rests on at least one stored source record. A stage that genuinely does
not apply (for example "journal" for a bank line that was never matched) is stated as
unavailable with the reason, never silently left out."""
from __future__ import annotations

from typing import Dict, List, Optional

from .errors import AsavexaAiError

CHAIN = ("conclusion", "source_records", "evidence", "journal", "accounting_treatment",
         "reporting_framework", "confidence", "human_review")

HIGH, MEDIUM, LOW = "HIGH", "MEDIUM", "LOW"


class UngroundedAnswerError(AsavexaAiError):
    """An item was about to be returned without its full chain. A programming error, never user input."""


def confidence(factors: List[dict], floor: int = 0) -> dict:
    """factors: [{"factor": str, "effect": int (<=0 lowers, 0 neutral, >0 only for stated positives), "detail": str}].
    Starts at 100, adds every effect, clamps to [floor, 100]."""
    score = max(floor, min(100, 100 + sum(int(f.get("effect", 0)) for f in factors)))
    level = HIGH if score >= 80 else MEDIUM if score >= 50 else LOW
    return {
        "level": level, "score": score, "factors": factors,
        "how": "Starts at 100 and loses points for every weakness in the supporting records: "
               "HIGH is 80 or more, MEDIUM 50 to 79, LOW below 50. It measures how well your records "
               "support this answer, not the chance that the books are right.",
    }


def human_review(required: bool, reasons: List[str], role_hint: Optional[str] = None) -> dict:
    return {"required": bool(required), "reasons": reasons, "suggested_reviewer": role_hint,
            "note": ("A person must review this before anything is relied on or acted on." if required
                     else "Nothing in the records calls for extra review, but the answer is still read-only and advisory.")}


def unavailable(why: str) -> dict:
    return {"available": False, "note": why}


def source_record(kind: str, rid: str, label: str, detail: Optional[str] = None, path: Optional[str] = None) -> dict:
    return {"kind": kind, "id": rid, "label": label, "detail": detail, "path": path}


def validate_item(item: Dict) -> Dict:
    missing = [k for k in CHAIN if k not in item]
    if missing:
        raise UngroundedAnswerError(f"answer item is missing chain link(s): {', '.join(missing)}")
    c = item["conclusion"]
    if not isinstance(c, dict) or not str(c.get("summary") or "").strip():
        raise UngroundedAnswerError("answer item has no conclusion")
    if not item["source_records"]:
        raise UngroundedAnswerError("answer item cites no source record")
    for rec in item["source_records"]:
        if not rec.get("id") or not rec.get("kind"):
            raise UngroundedAnswerError("a source record has no id or kind")
    for stage in ("evidence", "journal", "accounting_treatment", "reporting_framework"):
        s = item[stage]
        if not isinstance(s, dict) or ("available" not in s):
            raise UngroundedAnswerError(f"chain link {stage!r} must state whether it is available")
        if not s["available"] and not s.get("note"):
            raise UngroundedAnswerError(f"chain link {stage!r} is unavailable but gives no reason")
    conf = item["confidence"]
    if conf.get("level") not in (HIGH, MEDIUM, LOW) or not isinstance(conf.get("score"), int):
        raise UngroundedAnswerError("confidence is malformed")
    if "required" not in item["human_review"]:
        raise UngroundedAnswerError("human review requirement is missing")
    # a low-confidence answer can never say review is optional
    if conf["level"] != HIGH and not item["human_review"]["required"]:
        raise UngroundedAnswerError("a MEDIUM/LOW-confidence answer must require human review")
    return item


def refusal(question: str, why: str, can_do: Optional[List[str]] = None) -> dict:
    """Used when the records cannot support an answer: the AI says so instead of guessing."""
    return {
        "title": "I cannot answer that from your records",
        "reason": why, "can_do": can_do or [],
        "grounded": False, "human_review": human_review(True, [why]),
    }
