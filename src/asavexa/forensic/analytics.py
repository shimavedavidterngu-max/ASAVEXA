"""Read-only ledger analytics. Each test returns INDICATORS: patterns that deserve a human look. A flag is NOT proof of error, fraud or wrongdoing; most flags
have ordinary explanations. Pure functions over normalised journal rows (no database access), exact Decimal arithmetic, deterministic output."""
import math
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional

from .errors import ForensicError

MAX_HITS = 200
TESTS = {
    "benford": "First-digit pattern of amounts (Benford's law)",
    "duplicates": "Possible duplicate entries (same amount and accounts, close dates)",
    "round_numbers": "Unusually many round-number entries",
    "just_below": "Entries just below an approval limit",
    "weekend": "Entries dated on weekend days",
    "same_person": "Created and posted by the same person",
    "no_evidence": "Large entries with no evidence attached",
    "reversals": "Frequent reversals",
    "late_posting": "Posted long after the entry date",
}
DEFAULTS = {"duplicate_window_days": 3, "round_to": 1000, "round_min_amount": 1000, "round_share_pct": 25, "just_below_pct": 5, "weekend_days": [5, 6], "late_days": 30,
            "benford_min_values": 100, "approval_limit": None, "evidence_threshold": None}
BENFORD_EXPECTED = {d: math.log10(1 + 1 / d) for d in range(1, 10)}


def _dec(v, name, lo=0, hi=None, allow_none=True):
    if v in (None, ""):
        if allow_none:
            return None
        raise ForensicError(f"{name} is required.")
    try:
        x = Decimal(str(v))
    except Exception:
        raise ForensicError(f"{name} must be a number.")
    if not x.is_finite() or x < lo or (hi is not None and x > hi):
        raise ForensicError(f"{name} must be a number{' from ' + str(lo) if hi is not None else ' of at least ' + str(lo)}{' to ' + str(hi) if hi is not None else ''}.")
    return x


def clean_params(p: Optional[dict]) -> dict:
    p = dict(p or {})
    out = dict(DEFAULTS)
    for k in ("duplicate_window_days", "late_days", "benford_min_values"):
        if p.get(k) not in (None, ""):
            out[k] = int(_dec(p[k], k, 0, 3650, False))
    for k in ("round_to", "round_min_amount"):
        if p.get(k) not in (None, ""):
            v = _dec(p[k], k, 1, None, False); out[k] = int(v)
    for k in ("round_share_pct", "just_below_pct"):
        if p.get(k) not in (None, ""):
            out[k] = float(_dec(p[k], k, 0, 100, False))
    for k in ("approval_limit", "evidence_threshold"):
        v = _dec(p.get(k), k, 0)
        out[k] = None if v is None else str(v)
    if p.get("weekend_days") not in (None, ""):
        w = p["weekend_days"]
        if not isinstance(w, list) or not all(isinstance(i, int) and 0 <= i <= 6 for i in w):
            raise ForensicError("Weekend days must be numbers 0 (Monday) to 6 (Sunday).")
        out["weekend_days"] = sorted(set(w))
    return out


def _hit(j, reason, **extra):
    return {"journal_id": j["id"], "number": j["number"], "date": j["date"].isoformat(), "amount": str(j["total"]), "description": j["description"][:120], "reason": reason, **extra}


def _result(tid, status, summary, hits=None, extra=None, limits=""):
    hits = hits or []
    return {"id": tid, "name": TESTS[tid], "status": status, "summary": summary, "hit_count": len(hits), "hits": hits[:MAX_HITS], "truncated": len(hits) > MAX_HITS, "detail": extra or {}, "limits": limits}


def benford(rows, p):
    vals = []
    for j in rows:
        for _, d, c in j["lines"]:
            a = d if d > 0 else c
            if a >= 10:
                vals.append(a)
    n = len(vals)
    if n < p["benford_min_values"]:
        return _result("benford", "NOT_ENOUGH_DATA", f"Only {n} amounts of 10 or more; at least {p['benford_min_values']} are needed for this test to mean anything.")
    counts = defaultdict(int)
    for a in vals:
        s = format(abs(a), "f").lstrip("0.").replace(".", "")
        counts[int(s[0])] += 1
    table, mad = [], 0.0
    for d in range(1, 10):
        obs = counts[d] / n; exp = BENFORD_EXPECTED[d]; mad += abs(obs - exp)
        table.append({"digit": d, "count": counts[d], "observed_pct": round(obs * 100, 2), "expected_pct": round(exp * 100, 2), "difference_pct": round((obs - exp) * 100, 2)})
    mad /= 9
    band = "close conformity" if mad < 0.006 else "acceptable conformity" if mad < 0.012 else "marginal conformity" if mad < 0.015 else "non-conformity"
    chi = sum(((counts[d] - n * BENFORD_EXPECTED[d]) ** 2) / (n * BENFORD_EXPECTED[d]) for d in range(1, 10))
    worst = sorted(table, key=lambda r: -abs(r["difference_pct"]))[:2]
    st = "INDICATORS" if mad >= 0.012 else "NO_INDICATORS"
    return _result("benford", st, f"{n} amounts tested. Mean absolute deviation {mad:.4f} ({band}). Largest gaps: digits {worst[0]['digit']} and {worst[1]['digit']}.",
                   extra={"n": n, "mad": round(mad, 5), "band": band, "chi_square": round(chi, 2), "chi_square_critical_5pct_8df": 15.51, "digits": table},
                   limits="Benford's law suits large sets of naturally occurring amounts. Fixed prices, rents, salaries and small samples all depart from it for ordinary reasons. It points to where to look, not to a conclusion.")


def duplicates(rows, p):
    groups = defaultdict(list)
    for j in rows:
        if j["reversal_of"] or j["reversed_by"]:
            continue
        groups[(j["total"], frozenset(a for a, _, _ in j["lines"]))].append(j)
    hits = []
    for (_, _), g in groups.items():
        g.sort(key=lambda x: (x["date"], x["number"]))
        for i in range(len(g)):
            for k in range(i + 1, len(g)):
                if (g[k]["date"] - g[i]["date"]).days > p["duplicate_window_days"]:
                    break
                hits.append(_hit(g[k], f"Same amount and accounts as {g[i]['number']} ({g[i]['date'].isoformat()}), {(g[k]['date'] - g[i]['date']).days} day(s) apart", matches=g[i]["number"]))
    hits.sort(key=lambda h: (h["date"], h["number"]))
    return _result("duplicates", "INDICATORS" if hits else "NO_INDICATORS", f"{len(hits)} possible duplicate(s) within {p['duplicate_window_days']} day(s).", hits,
                   limits="Regular payments (rent, salaries, subscriptions) legitimately repeat. Reversed entries and their reversals are excluded.")


def round_numbers(rows, p):
    cand = [j for j in rows if j["total"] >= p["round_min_amount"]]
    if len(cand) < 10:
        return _result("round_numbers", "NOT_ENOUGH_DATA", f"Only {len(cand)} entries of {p['round_min_amount']} or more; at least 10 are needed.")
    hits = [_hit(j, f"Exact multiple of {p['round_to']}") for j in cand if j["total"] % p["round_to"] == 0]
    share = len(hits) / len(cand) * 100
    st = "INDICATORS" if len(hits) >= 5 and share >= p["round_share_pct"] else "NO_INDICATORS"
    return _result("round_numbers", st, f"{len(hits)} of {len(cand)} entries ({share:.1f}%) are exact multiples of {p['round_to']}; the alert level is {p['round_share_pct']}% and at least 5.", hits if st == "INDICATORS" else [],
                   extra={"share_pct": round(share, 1)}, limits="Contracts, salaries, loans and grants are often round. A high share can be normal for the business.")


def just_below(rows, p):
    if p["approval_limit"] is None:
        return _result("just_below", "NOT_CONFIGURED", "Enter the approval limit you want to test against.")
    lim = Decimal(p["approval_limit"]); low = lim * (1 - Decimal(str(p["just_below_pct"])) / 100)
    hits = [_hit(j, f"Within {p['just_below_pct']}% below the limit of {lim}") for j in rows if low <= j["total"] < lim]
    return _result("just_below", "INDICATORS" if hits else "NO_INDICATORS", f"{len(hits)} entr(ies) from {low.quantize(Decimal('0.01'))} up to (not including) {lim}.", hits,
                   limits="Amounts cluster below limits naturally when budgets are set near them. Compare with the volume just above the limit before drawing any view.")


def weekend(rows, p):
    hits = [_hit(j, f"Dated {j['date'].strftime('%A')}") for j in rows if j["date"].weekday() in p["weekend_days"]]
    return _result("weekend", "INDICATORS" if hits else "NO_INDICATORS", f"{len(hits)} entr(ies) dated on a weekend day.", hits,
                   limits="Weekend days differ by country and business. Set them in the options. Month-end entries and online sales legitimately fall on weekends.")


def same_person(rows, p):
    hits = [_hit(j, f"Created and posted by the same user ({j['created_by']})") for j in rows if j["posted_by"] and j["created_by"] == j["posted_by"]]
    return _result("same_person", "INDICATORS" if hits else "NO_INDICATORS", f"{len(hits)} entr(ies) where one person both created and posted.", hits,
                   limits="In a very small team one person may have to do both. This shows missing segregation of duties, not misuse.")


def no_evidence(rows, p):
    if p["evidence_threshold"] is None:
        return _result("no_evidence", "NOT_CONFIGURED", "Enter the amount above which an entry should have evidence.")
    t = Decimal(p["evidence_threshold"])
    hits = [_hit(j, f"No evidence reference on an entry of {t} or more") for j in rows if j["total"] >= t and not j["evidence_ref"]]
    return _result("no_evidence", "INDICATORS" if hits else "NO_INDICATORS", f"{len(hits)} entr(ies) of {t} or more without an evidence reference.", hits,
                   limits="Evidence may exist outside ASAVEXA. This only shows nothing is linked here.")


def reversals(rows, p):
    rev = [j for j in rows if j["reversed_by"]]
    share = len(rev) / len(rows) * 100 if rows else 0
    hits = [_hit(j, f"Later reversed by {j['reversed_by']}") for j in rev]
    st = "INDICATORS" if len(rev) >= 3 and share > 10 else "NO_INDICATORS"
    return _result("reversals", st, f"{len(rev)} of {len(rows)} entries were reversed ({share:.1f}%); alert level is more than 10% and at least 3.", hits if st == "INDICATORS" else [],
                   extra={"share_pct": round(share, 1)}, limits="Corrections are a normal, healthy use of reversals. A high rate may mean weak review before posting.")


def late_posting(rows, p):
    hits = []
    for j in rows:
        if j["posted_at"] is not None:
            lag = (j["posted_at"].date() - j["date"]).days
            if lag > p["late_days"]:
                hits.append(_hit(j, f"Posted {lag} days after its entry date", lag_days=lag))
    return _result("late_posting", "INDICATORS" if hits else "NO_INDICATORS", f"{len(hits)} entr(ies) posted more than {p['late_days']} days after their date.", hits,
                   limits="Late invoices and catch-up bookkeeping are common. Look at who posted and why.")


RUNNERS = {"benford": benford, "duplicates": duplicates, "round_numbers": round_numbers, "just_below": just_below, "weekend": weekend, "same_person": same_person,
           "no_evidence": no_evidence, "reversals": reversals, "late_posting": late_posting}


def run_tests(rows: List[dict], tests: List[str], params: dict) -> List[dict]:
    unknown = [t for t in tests if t not in RUNNERS]
    if unknown:
        raise ForensicError(f"Unknown test: {unknown[0]}.")
    if not tests:
        raise ForensicError("Choose at least one test.")
    return [RUNNERS[t](rows, params) for t in dict.fromkeys(tests)]
