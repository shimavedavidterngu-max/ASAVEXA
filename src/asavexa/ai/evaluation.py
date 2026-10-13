"""Evaluation of the rule-based assistant against LABELLED cases (Stage 5).

Why: the assistant says it is rule-based and makes no accuracy claim. This module is how a claim could be earned. It measures, on a labelled set a
person wrote down in advance:
  * detection: for each rule, did it fire on the journals it should, and stay quiet on the ones it should not (precision and recall);
  * grounding: does every answer carry its source records, and does it REFUSE what it cannot support;
  * stability: does the same question give the same answer fingerprint.
A result describes only the labelled set it was run on. It is never evidence of accuracy on a customer's own books, and the report says so.
No outside model is called; nothing here changes any data.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from .grounding import UngroundedAnswerError, validate_item

DEFAULT_CRITERIA = {"min_precision": 0.9, "min_recall": 0.9, "min_grounded": 1.0, "min_refused_correctly": 1.0, "min_stable": 1.0, "min_labels_per_rule": 2}
SCOPE_NOTE = ("These figures describe only the labelled cases listed here. They are not a measure of accuracy on any organisation's own records, "
              "and a rule that passes here can still be wrong elsewhere. The assistant stays rule-based and advisory; a person decides.")


def _ratio(num: int, den: int) -> Optional[float]:
    return None if den == 0 else round(num / den, 4)


def fired_rules(engine):
    """Returns (journal_id -> rule codes that fired, total flagged, number returned). detect() returns at most one page, so callers compare the last two."""
    out: Dict[str, set] = {}
    result = engine.detect(limit=50)
    for item in result["items"]:
        jid = (item.get("journal") or {}).get("id") or next((s["id"] for s in item["source_records"] if s["kind"] == "JOURNAL"), None)
        if jid:
            out.setdefault(jid, set()).update(f["rule"] for f in item.get("flags", []))
    return out, result["total_flagged"], len(result["items"])


def validate_labels(labels: Iterable[dict]) -> List[dict]:
    clean = []
    for l in labels:
        if not isinstance(l, dict) or not l.get("rule") or not l.get("journal_id") or not isinstance(l.get("expected"), bool):
            raise ValueError("each label needs rule, journal_id and expected (true or false)")
        clean.append({"rule": str(l["rule"]), "journal_id": str(l["journal_id"]), "expected": l["expected"], "why": str(l.get("why", ""))})
    if not clean:
        raise ValueError("there are no labels to evaluate")
    return clean


def evaluate_detection(engine, labels: Iterable[dict], criteria: Optional[dict] = None) -> dict:
    labels = validate_labels(labels)
    crit = {**DEFAULT_CRITERIA, **(criteria or {})}
    fired, total_flagged, returned = fired_rules(engine)
    known = {r[0] for r in engine.DETECT_RULES}
    rules: Dict[str, dict] = {}
    mistakes = []
    for l in labels:
        if l["rule"] not in known:
            raise ValueError(f"unknown rule {l['rule']!r}")
        r = rules.setdefault(l["rule"], {"tp": 0, "fp": 0, "fn": 0, "tn": 0, "labels": 0})
        got = l["rule"] in fired.get(l["journal_id"], set())
        r["labels"] += 1
        key = ("tp" if got else "fn") if l["expected"] else ("fp" if got else "tn")
        r[key] += 1
        if key in ("fp", "fn"):
            mistakes.append({"rule": l["rule"], "journal_id": l["journal_id"], "outcome": key, "why": l["why"]})
    for code, r in rules.items():
        r["precision"] = _ratio(r["tp"], r["tp"] + r["fp"])
        r["recall"] = _ratio(r["tp"], r["tp"] + r["fn"])
        problems = []
        if r["labels"] < crit["min_labels_per_rule"]:
            problems.append(f"only {r['labels']} labelled case(s); need {crit['min_labels_per_rule']}")
        if r["precision"] is not None and r["precision"] < crit["min_precision"]:
            problems.append("precision below the target")
        if r["recall"] is not None and r["recall"] < crit["min_recall"]:
            problems.append("recall below the target")
        r["meets_criteria"] = not problems
        r["problems"] = problems
    truncated = total_flagged > returned
    return {"rules": rules, "mistakes": mistakes, "labels": len(labels), "truncated": truncated,
            "unlabelled_rules": sorted(known - set(rules)), "meets_criteria": all(r["meets_criteria"] for r in rules.values()) and not truncated}


def evaluate_questions(engine, cases: Iterable[dict], criteria: Optional[dict] = None) -> dict:
    """cases: {"question": str, "expect": "answer" | "refuse"}. An answer must be grounded (every item passes the grounding contract); a refusal must say so."""
    crit = {**DEFAULT_CRITERIA, **(criteria or {})}
    rows, grounded_ok, grounded_n, refuse_ok, refuse_n, stable_ok = [], 0, 0, 0, 0, 0
    cases = list(cases)
    for c in cases:
        q, expect = c["question"], c["expect"]
        if expect not in ("answer", "refuse"):
            raise ValueError("expect must be 'answer' or 'refuse'")
        first = engine.ask(q)
        second = engine.ask(q)
        stable = first.get("fingerprint") == second.get("fingerprint")
        stable_ok += stable
        refused = (not first.get("grounded")) and bool(first.get("refusal"))
        row = {"question": q, "expect": expect, "refused": refused, "stable": stable}
        if expect == "refuse":
            refuse_n += 1
            row["correct"] = refused and not first.get("items")
            refuse_ok += row["correct"]
        else:
            grounded_n += 1
            try:
                if refused or not first.get("items"):
                    raise UngroundedAnswerError("no grounded answer was given")
                for item in first["items"]:
                    validate_item(item)
                row["correct"] = True
            except UngroundedAnswerError as exc:
                row["correct"], row["problem"] = False, str(exc)
            grounded_ok += row["correct"]
        rows.append(row)
    g, rf, st = _ratio(grounded_ok, grounded_n), _ratio(refuse_ok, refuse_n), _ratio(stable_ok, len(cases))
    ok = all((v is None or v >= t) for v, t in ((g, crit["min_grounded"]), (rf, crit["min_refused_correctly"]), (st, crit["min_stable"])))
    return {"cases": rows, "grounded_rate": g, "refused_correctly_rate": rf, "stable_rate": st, "meets_criteria": ok and bool(cases)}


def run_evaluation(engine, labels: Iterable[dict], questions: Iterable[dict], criteria: Optional[dict] = None) -> dict:
    det = evaluate_detection(engine, labels, criteria)
    qs = evaluate_questions(engine, questions, criteria)
    return {"schema": "ai_evaluation/1", "detection": det, "questions": qs, "criteria": {**DEFAULT_CRITERIA, **(criteria or {})},
            "meets_criteria": det["meets_criteria"] and qs["meets_criteria"], "scope_note": SCOPE_NOTE,
            "claim_allowed": "None beyond the labelled set. No accuracy claim about real organisations is supported."}


def format_report(result: dict) -> str:
    d, q = result["detection"], result["questions"]
    lines = ["ASAVEXA assistant evaluation", "=" * 28, f"Overall: {'MEETS' if result['meets_criteria'] else 'DOES NOT MEET'} the stated criteria", "", "Detection (per rule: precision, recall, labelled cases)"]
    for code, r in sorted(d["rules"].items()):
        lines.append(f"  {code:34s} P={r['precision']} R={r['recall']} n={r['labels']} {'ok' if r['meets_criteria'] else 'NOT OK: ' + '; '.join(r['problems'])}")
    if d["unlabelled_rules"]:
        lines.append("  Rules with no labelled cases (unmeasured): " + ", ".join(d["unlabelled_rules"]))
    for m in d["mistakes"]:
        lines.append(f"  MISTAKE {m['outcome'].upper()} {m['rule']} on {m['journal_id']} {m['why']}")
    lines += ["", f"Questions: grounded {q['grounded_rate']}, refused correctly {q['refused_correctly_rate']}, stable {q['stable_rate']}", "", result["scope_note"]]
    return "\n".join(lines)
