"""ESG and carbon (records and evidence): emission records, verification by a different person, and reduction targets.

Records (shared document store, per organisation): es_entry, es_target, es_setting.

Principles enforced here
  * An emission record is activity data a person types in (a quantity and a unit) multiplied by an emission factor a person types in, with its source and year. The product is worked out exactly (kg CO2e) and rounded once.
  * ASAVEXA supplies no emission factors, measures nothing, calculates no footprint of its own, and follows no reporting standard. A figure is only as good as the factor and the data typed.
  * An entry is proposed by one person and VERIFIED or REJECTED by a different person. Only verified entries count in the totals. A reduction target is proposed by one person and approved or rejected by a different person.
Nothing is edited or deleted after it is decided; a wrong entry is rejected and entered again. Every step is audited by reference number only.
"""
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Callable, List

from .errors import EsgError, EsgForbiddenError, EsgNotFoundError, EsgStateError

SCOPES = ["SCOPE_1", "SCOPE_2", "SCOPE_3"]
TARGET_SCOPES = ["ALL"] + SCOPES
CATEGORIES = ["FUEL", "ELECTRICITY", "HEATING_COOLING", "TRAVEL", "FREIGHT", "WASTE", "WATER", "PURCHASED_GOODS", "REFRIGERANTS", "OTHER"]
DEFAULTS = {"factor_max_age_years": 5}
CENT = Decimal("0.01")
MIL = Decimal("0.001")
LIMITATIONS = [
    "ASAVEXA supplies no emission factors and measures nothing. A person types in the activity data and the factor, with its source and year; a figure is only as good as what was typed.",
    "The arithmetic is quantity x factor, in kilograms of CO2 equivalent, rounded once to two decimals. Gases, global-warming-potential choices, market-based and location-based methods and uncertainty are not handled.",
    "Scope 1, 2 and 3 are labels a person chooses. ASAVEXA does not check that an entry is in the right scope or that nothing is double counted or left out.",
    "No reporting or assurance standard (GHG Protocol, ISO 14064, ISSB, CSRD or any other) is applied or claimed. This is not an assured sustainability report.",
    "Only verified entries count. Verification by a different person is a review of what was typed, not a check against the real world.",
    "A target compares verified totals for one calendar year with a figure computed from the typed baseline and percentage. It is arithmetic, not a claim that the target is science-based or has been met in the eyes of any body.",
]


def _utc(): return datetime.now(timezone.utc)


def _txt(v, name, lo=1, hi=1000, required=True) -> str:
    v = (v if isinstance(v, str) else ("" if v is None else str(v)))
    v = " ".join("".join(c if c >= " " and c != "\x7f" else " " for c in v).split())
    if required and len(v) < lo:
        raise EsgError(f"{name} is required (at least {lo} characters).")
    if v and len(v) < lo:
        raise EsgError(f"{name} needs at least {lo} characters.")
    if len(v) > hi:
        raise EsgError(f"{name} is too long (limit {hi} characters).")
    return v


def _date(v, name) -> date:
    try:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", str(v).strip()): raise ValueError
        return date.fromisoformat(str(v).strip())
    except (ValueError, TypeError):
        raise EsgError(f"{name} must be a real date written YYYY-MM-DD.")


def _enum(v, allowed, name) -> str:
    v = _txt(v, name, 1, 40).upper()
    if v not in allowed:
        raise EsgError(f"{name} must be one of {', '.join(allowed)}.")
    return v


def _int(v, name, lo, hi) -> int:
    if isinstance(v, bool) or not re.fullmatch(r"[0-9]{1,15}", str(v).strip()):
        raise EsgError(f"{name} must be a whole number from {lo} to {hi}.")
    n = int(str(v).strip())
    if not lo <= n <= hi:
        raise EsgError(f"{name} must be a whole number from {lo} to {hi}.")
    return n


def _num(v, name, int_digits, places, example, zero_ok=False) -> Decimal:
    """Text or a whole number: ASCII digits, at most `places` decimals, never a float, commas only as thousands separators."""
    if isinstance(v, bool) or isinstance(v, float) or v is None:
        raise EsgError(f"{name} must be a number such as {example}.")
    t = str(v).strip()
    if "," in t and not re.fullmatch(r"[0-9]{1,3}(,[0-9]{3})+(\.[0-9]+)?", t):
        raise EsgError(f"{name} must be a number such as {example} (commas only between groups of three digits).")
    t = t.replace(",", "")
    if not re.fullmatch(r"[0-9]{1,%d}(\.[0-9]{1,%d})?" % (int_digits, places), t):
        raise EsgError(f"{name} must be a number such as {example} (at most {places} decimals).")
    d = Decimal(t)
    if d == 0 and not zero_ok:
        raise EsgError(f"{name} must be more than zero.")
    return d


def _trim(d: Decimal) -> str:
    s = f"{d:f}"
    return s.rstrip("0").rstrip(".") if "." in s else s


def refnum(r) -> int:
    try: return int(str(r["ref"]).rsplit("-", 1)[1])
    except (KeyError, IndexError, ValueError): return 0


def tonnes(kg: Decimal) -> Decimal: return (kg / 1000).quantize(MIL, rounding=ROUND_HALF_UP)


class EsgService:
    def __init__(self, store, vault=None, log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = _utc):
        self.store, self.vault, self.log, self.now = store, vault, log, now

    # ------------------------------------------------------------------ helpers
    def today(self) -> date: return self.now().date()

    def _not_future(self, d: date, what: str):
        if d > self.today() + timedelta(days=1):
            raise EsgError(f"{what} cannot be in the future.")

    def _put(self, kind, org, d): self.store.put(kind, f"{org}:{d['id']}", d, org_id=org)
    def _all(self, kind, org) -> list: return [d for _, d in self.store.list(kind, org_id=org, prefix=f"{org}:") if d.get("org") == org]

    def _get(self, kind, org, rid, label, for_update=False) -> dict:
        r = self.store.get(kind, f"{org}:{rid}", for_update=for_update)
        if r is None or r.get("org") != org:
            raise EsgNotFoundError(f"{label} not found.")
        return r

    def _settings(self, org, for_update=False) -> dict:
        s = self.store.get("es_setting", f"{org}:settings", for_update=for_update)
        if s and s.get("org") == org:
            return s
        return {"id": "settings", "org": org, **DEFAULTS, "counters": {}, "updated_by": None, "updated_at": None}

    def _ref(self, org, prefix) -> str:
        s = self._settings(org, for_update=True)
        n = s["counters"].get(prefix, 0) + 1
        s["counters"][prefix] = n
        self._put("es_setting", org, s)
        return f"{prefix}-{n:03d}"

    def _hist(self, r, actor, event, note=""):
        r.setdefault("history", []).append({"at": self.now().isoformat(), "by": actor, "event": event, "note": note})

    def _two(self, actor, other, what):
        if actor == other:
            raise EsgForbiddenError(f"You {what}, so you cannot do this. A different person must.")

    # ------------------------------------------------------------------ setting
    def es_get_setting(self, org) -> dict:
        s = self._settings(org)
        return {"factor_max_age_years": s["factor_max_age_years"], "updated_by": s["updated_by"], "updated_at": s["updated_at"],
                "meaning": f"A verified entry whose emission factor is more than {s['factor_max_age_years']} years older than the year of the activity is flagged as an old factor. This is your own setting, not a rule."}

    def es_set_setting(self, org, d, actor) -> dict:
        s = self._settings(org, for_update=True)
        if d.get("factor_max_age_years") is not None: s["factor_max_age_years"] = _int(d["factor_max_age_years"], "The factor age limit in years", 1, 20)
        s.update(updated_by=actor, updated_at=self.now().isoformat())
        self._put("es_setting", org, s)
        self.log("ESG_SETTING_SET", actor, "settings", org, f"factor age {s['factor_max_age_years']} years")
        return self.es_get_setting(org)

    # ------------------------------------------------------------------ entries
    def _entry_view(self, e) -> dict:
        v = {x: e[x] for x in e if x != "org"}
        v["old_factor"] = e["status"] == "VERIFIED" and int(e["year"]) - e["factor_year"] > self._settings(e["org"])["factor_max_age_years"]
        v["tonnes"] = str(tonnes(Decimal(e["kg_co2e"])))
        return v

    def es_add_entry(self, org, d, actor) -> dict:
        scope = _enum(d.get("scope"), SCOPES, "The scope"); cat = _enum(d.get("category"), CATEGORIES, "The category"); desc = _txt(d.get("description"), "The description", 5, 300)
        start = _date(d.get("period_start"), "The start of the period"); end = _date(d.get("period_end"), "The end of the period"); self._not_future(end, "The end of the period")
        if end < start: raise EsgError("The period cannot end before it starts.")
        if start.year != end.year: raise EsgError("A period must fall within one calendar year. Enter a separate record for each year.")
        qty = _num(d.get("quantity"), "The quantity", 12, 4, "1250.5"); unit = _txt(d.get("unit"), "The unit", 1, 20)
        factor = _num(d.get("factor"), "The emission factor (kg CO2e per unit)", 6, 6, "2.68"); fsource = _txt(d.get("factor_source"), "The source of the factor", 5, 200)
        fyear = _int(d.get("factor_year"), "The year of the factor", 1990, self.today().year + 1)
        kg = (qty * factor).quantize(CENT, rounding=ROUND_HALF_UP)
        if kg == 0: raise EsgError("The result rounds to zero. Check the quantity and the factor.")
        e = {"id": uuid.uuid4().hex, "org": org, "ref": None, "scope": scope, "category": cat, "description": desc, "period_start": start.isoformat(), "period_end": end.isoformat(), "year": end.year, "quantity": _trim(qty), "unit": unit,
             "factor": _trim(factor), "factor_source": fsource, "factor_year": fyear, "kg_co2e": str(kg), "status": "PROPOSED", "proposed_by": actor, "created_at": self.now().isoformat(), "decided_by": None, "decided_on": None, "decision_note": None, "history": []}
        e["ref"] = self._ref(org, "ER"); self._hist(e, actor, "PROPOSED")
        self._put("es_entry", org, e); self.log("ESG_ENTRY_PROPOSED", actor, e["id"], org, e["ref"])
        return self._entry_view(e)

    def es_list_entries(self, org, status=None) -> List[dict]:
        return [self._entry_view(e) for e in sorted(self._all("es_entry", org), key=refnum) if not status or e["status"] == status]

    def es_get_entry(self, org, eid) -> dict: return self._entry_view(self._get("es_entry", org, eid, "Entry"))

    def _undecided(self, org, eid) -> dict:
        e = self._get("es_entry", org, eid, "Entry", for_update=True)
        if e["status"] != "PROPOSED": raise EsgStateError("That entry has already been decided.")
        return e

    def es_verify_entry(self, org, eid, d, actor) -> dict:
        e = self._undecided(org, eid); self._two(actor, e["proposed_by"], "entered this record")
        note = _txt(d.get("note"), "A verification note", 10, 1000, required=False)
        e.update(status="VERIFIED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=note or None); self._hist(e, actor, "VERIFIED", note)
        self._put("es_entry", org, e); self.log("ESG_ENTRY_VERIFIED", actor, eid, org, e["ref"])
        return self._entry_view(e)

    def es_reject_entry(self, org, eid, reason, actor) -> dict:
        e = self._undecided(org, eid); self._two(actor, e["proposed_by"], "entered this record")
        reason = _txt(reason, "A reason", 10, 1000); e.update(status="REJECTED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=reason); self._hist(e, actor, "REJECTED", reason)
        self._put("es_entry", org, e); self.log("ESG_ENTRY_REJECTED", actor, eid, org, e["ref"])
        return self._entry_view(e)

    # ------------------------------------------------------------------ targets
    def _verified_kg(self, org, year, scope) -> Decimal:
        return sum((Decimal(e["kg_co2e"]) for e in self._all("es_entry", org) if e["status"] == "VERIFIED" and e["year"] == year and (scope == "ALL" or e["scope"] == scope)), Decimal(0))

    def _target_view(self, t) -> dict:
        v = {x: t[x] for x in t if x != "org"}
        kg = self._verified_kg(t["org"], t["target_year"], t["scope"]); act = tonnes(kg); tgt = Decimal(t["target_tonnes"])
        base = Decimal(t["baseline_tonnes"])
        v.update(actual_tonnes=str(act), within_target=Decimal(kg) <= tgt * 1000, change_vs_baseline_pct=str(((act - base) / base * 100).quantize(CENT, rounding=ROUND_HALF_UP)), year_ended=date(t["target_year"], 12, 31) < self.today())
        return v

    def es_add_target(self, org, d, actor) -> dict:
        scope = _enum(d.get("scope"), TARGET_SCOPES, "The scope"); by = _int(d.get("baseline_year"), "The baseline year", 1990, self.today().year); ty = _int(d.get("target_year"), "The target year", 1991, 2100)
        if ty <= by: raise EsgError("The target year must be after the baseline year.")
        base = _num(d.get("baseline_tonnes"), "The baseline emissions in tonnes", 12, 3, "1250.500"); pct = _num(d.get("reduction_pct"), "The reduction in percent", 3, 2, "42.5")
        if pct > 100: raise EsgError("The reduction cannot be more than 100 percent.")
        label = _txt(d.get("label"), "The label", 3, 150)
        tgt = (base * (Decimal(100) - pct) / 100).quantize(MIL, rounding=ROUND_HALF_UP)
        t = {"id": uuid.uuid4().hex, "org": org, "ref": None, "label": label, "scope": scope, "baseline_year": by, "baseline_tonnes": _trim(base), "reduction_pct": _trim(pct), "target_year": ty, "target_tonnes": str(tgt),
             "status": "PROPOSED", "proposed_by": actor, "created_at": self.now().isoformat(), "decided_by": None, "decided_on": None, "decision_note": None, "history": []}
        t["ref"] = self._ref(org, "TG"); self._hist(t, actor, "PROPOSED")
        self._put("es_target", org, t); self.log("ESG_TARGET_PROPOSED", actor, t["id"], org, t["ref"])
        return self._target_view(t)

    def es_list_targets(self, org, status=None) -> List[dict]:
        return [self._target_view(t) for t in sorted(self._all("es_target", org), key=refnum) if not status or t["status"] == status]

    def _undecided_target(self, org, tid) -> dict:
        t = self._get("es_target", org, tid, "Target", for_update=True)
        if t["status"] != "PROPOSED": raise EsgStateError("That target has already been decided.")
        return t

    def es_approve_target(self, org, tid, d, actor) -> dict:
        t = self._undecided_target(org, tid); self._two(actor, t["proposed_by"], "proposed this target")
        note = _txt(d.get("note"), "An approval note", 10, 1000, required=False)
        t.update(status="APPROVED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=note or None); self._hist(t, actor, "APPROVED", note)
        self._put("es_target", org, t); self.log("ESG_TARGET_APPROVED", actor, tid, org, t["ref"])
        return self._target_view(t)

    def es_reject_target(self, org, tid, reason, actor) -> dict:
        t = self._undecided_target(org, tid); self._two(actor, t["proposed_by"], "proposed this target")
        reason = _txt(reason, "A reason", 10, 1000); t.update(status="REJECTED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=reason); self._hist(t, actor, "REJECTED", reason)
        self._put("es_target", org, t); self.log("ESG_TARGET_REJECTED", actor, tid, org, t["ref"])
        return self._target_view(t)

    # ------------------------------------------------------------------ overview
    def es_overview(self, org) -> dict:
        es = self.es_list_entries(org); ts = self.es_list_targets(org); att = []

        def add(kind, n, text):
            if n: att.append({"kind": kind, "count": n, "text": text})
        add("ENTRIES_TO_VERIFY", sum(1 for e in es if e["status"] == "PROPOSED"), "emission record(s) are waiting for a different person to verify them.")
        add("TARGETS_TO_DECIDE", sum(1 for t in ts if t["status"] == "PROPOSED"), "target(s) are waiting for a different person to decide them.")
        add("OLD_FACTORS", sum(1 for e in es if e["old_factor"]), "verified record(s) use an emission factor older than your limit.")
        years = {}
        for e in es:
            if e["status"] != "VERIFIED": continue
            y = years.setdefault(e["year"], {"year": e["year"], "kg": {s: Decimal(0) for s in SCOPES}})
            y["kg"][e["scope"]] += Decimal(e["kg_co2e"])
        out = []
        for y in sorted(years.values(), key=lambda x: -x["year"]):
            total = sum(y["kg"].values(), Decimal(0))
            out.append({"year": y["year"], "total_kg": str(total.quantize(CENT)), "total_tonnes": str(tonnes(total)), "scopes": {s: {"kg": str(y["kg"][s].quantize(CENT)), "tonnes": str(tonnes(y["kg"][s]))} for s in SCOPES}})
        counts = {f"entries_{s.lower()}": sum(1 for e in es if e["status"] == s) for s in ("PROPOSED", "VERIFIED", "REJECTED")}
        counts.update({f"targets_{s.lower()}": sum(1 for t in ts if t["status"] == s) for s in ("PROPOSED", "APPROVED", "REJECTED")})
        return {"counts": counts, "years": out, "targets": [t for t in ts if t["status"] == "APPROVED"], "attention": att, "setting": self.es_get_setting(org), "limitations": LIMITATIONS}

    def es_options(self, org) -> dict:
        return {"scopes": SCOPES, "target_scopes": TARGET_SCOPES, "categories": CATEGORIES, "limitations": LIMITATIONS}
