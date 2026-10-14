"""Planning and KPIs (records and evidence): KPI ownership and traceability, and forecast accuracy.

Records (shared document store, per organisation): fp_kpi, fp_reading, fp_forecast, fp_setting.

Principles enforced here
  * A KPI has one named owner who must accept the ownership. Only the owner records its readings. The owner cannot approve the target they are measured against, and
    nobody approves a KPI they defined themselves.
  * Every reading says where the number came from (a written source, and optionally documents from the Evidence Vault, whose file hashes are kept). A reading is
    reviewed by someone other than the owner who recorded it. A reading is never edited: a correction supersedes the old one, with a reason, and the old one is kept.
  * A forecast is stamped with TODAY's date by the system, never typed, so it cannot be back-dated. It cannot be changed, only withdrawn by who made it, with a reason.
    The actual is entered by someone other than the forecaster and confirmed by a third person. Accuracy counts confirmed actuals only.
  * Arithmetic is exact decimal. Units and currencies are never mixed or converted. A target judgement and an accuracy figure are fixed arithmetic, not a prediction.
Nothing is deleted. Every step is audited.
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Callable, List, Optional

from .errors import FpaError, FpaForbiddenError, FpaNotFoundError, FpaStateError

UNITS = {"AMOUNT": 2, "RATIO": 4, "PERCENT": 2, "COUNT": 0, "DAYS": 0}
DIRECTIONS = ["HIGHER_BETTER", "LOWER_BETTER"]
FREQUENCIES = ["MONTHLY", "QUARTERLY", "ANNUAL"]
DEFAULTS = {"watch_pct": 10, "grace_days": 15, "accuracy_pct": 10, "min_items": 3}
VALUE_LIMIT = Decimal("1000000000000")
LIMITATIONS = [
    "ASAVEXA records what people type in. It does not calculate a KPI from the ledger, and it does not check that a reading is true. It keeps who recorded it, where they say it came from and who reviewed it.",
    "A target judgement is fixed arithmetic against the target someone typed in. It is not a view on whether the target is a good one.",
    "Forecast accuracy is arithmetic over forecasts and confirmed actuals. It describes the past and does not predict the future. With very few items it means little.",
    "A forecast is stamped with the date it was registered. It cannot be back-dated or edited. Registering a forecast after the fact is not possible.",
    "Units and currencies are never added together or converted.",
    "Monthly and quarterly periods end on calendar month and quarter ends. Annual periods end on whatever date the owner records, one year apart.",
    "To change a target, retire the KPI and define a new one. The history of the old one stays.",
    "This is a management record. It is not an audit opinion or a performance guarantee.",
]


def _utc(): return datetime.now(timezone.utc)


def _txt(v, name, lo=1, hi=1000, required=True) -> str:
    v = (v if isinstance(v, str) else ("" if v is None else str(v)))
    v = " ".join("".join(c if c >= " " and c != "\x7f" else " " for c in v).split())
    if required and len(v) < lo:
        raise FpaError(f"{name} is required (at least {lo} characters).")
    if v and len(v) < lo:
        raise FpaError(f"{name} needs at least {lo} characters.")
    if len(v) > hi:
        raise FpaError(f"{name} is too long (limit {hi} characters).")
    return v


def _date(v, name) -> date:
    try:
        return date.fromisoformat(str(v).strip())
    except (ValueError, TypeError):
        raise FpaError(f"{name} must be a real date written YYYY-MM-DD.")


def _enum(v, allowed, name) -> str:
    v = _txt(v, name, 1, 40).upper()
    if v not in allowed:
        raise FpaError(f"{name} must be one of {', '.join(allowed)}.")
    return v


def _currency(v, name="Currency") -> str:
    v = _txt(v, name, 3, 3).upper()
    if not (len(v) == 3 and v.isalpha() and v.isascii()):
        raise FpaError(f"{name} must be a three-letter code such as NGN or USD.")
    return v


def _num(v, name, places) -> Decimal:
    """A signed number with at most `places` decimals (a KPI value or a target can be negative)."""
    if isinstance(v, bool) or v is None or (isinstance(v, str) and not v.strip()):
        raise FpaError(f"{name} is required (a number).")
    try:
        d = Decimal(str(v).strip().replace(",", ""))
    except InvalidOperation:
        raise FpaError(f"{name} must be a number.")
    if not d.is_finite():
        raise FpaError(f"{name} must be a number.")
    if abs(d) >= VALUE_LIMIT:
        raise FpaError(f"{name} is too large.")
    q = Decimal(1).scaleb(-places)
    try:
        exact = d == d.quantize(q)
    except InvalidOperation:
        exact = False
    if not exact:
        raise FpaError(f"{name} can have at most {places} decimal place{'s' if places != 1 else ''}." if places else f"{name} must be a whole number.")
    return d.quantize(q)


def _int(v, name, lo, hi) -> int:
    if isinstance(v, bool) or not str(v).strip().lstrip("-").isdigit():
        raise FpaError(f"{name} must be a whole number from {lo} to {hi}.")
    n = int(str(v).strip())
    if not lo <= n <= hi:
        raise FpaError(f"{name} must be a whole number from {lo} to {hi}.")
    return n


def refnum(r) -> int:
    """KP-012 -> 12, so references sort numerically (KP-1000 after KP-999), and records made in the same instant keep the order they were made in."""
    try: return int(str(r["ref"]).rsplit("-", 1)[1])
    except (KeyError, IndexError, ValueError): return 0


def fmt(d: Decimal, places: int) -> str: return f"{d.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP):.{places}f}"
def pct(n: Decimal, d: Decimal) -> Optional[str]: return None if d == 0 else fmt(n / d * 100, 2)


def month_end(y: int, m: int) -> date:
    return date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)


def period_end_for(d: date, freq: str) -> date:
    """The calendar month or quarter end that contains d (annual periods have no calendar rule, so d itself)."""
    if freq == "MONTHLY": return month_end(d.year, d.month)
    if freq == "QUARTERLY": return month_end(d.year, ((d.month - 1) // 3 + 1) * 3)
    return d


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, min(d.day, month_end(d.year + y, m + 1).day))


def next_period_end(last: date, freq: str) -> date:
    if freq == "ANNUAL": return add_months(last, 12)
    return period_end_for(last + timedelta(days=1), freq)


def judge(value: Decimal, target: Decimal, direction: str, watch_pct: int) -> dict:
    """ON_TARGET when the target is met or beaten; WATCH when short by no more than the warning margin (a share of the target); otherwise OFF_TARGET."""
    gap = value - target
    better = gap if direction == "HIGHER_BETTER" else -gap
    if better >= 0:
        return {"status": "ON_TARGET", "shortfall_pct": None}
    short = -better
    if target == 0:
        return {"status": "OFF_TARGET", "shortfall_pct": None}
    p = short / abs(target) * 100
    return {"status": "WATCH" if p <= watch_pct else "OFF_TARGET", "shortfall_pct": fmt(p, 2)}


class FpaService:
    def __init__(self, store, vault=None, is_member: Callable[[str, str], bool] = lambda org, user: True, can_record: Callable[[str, str], bool] = lambda org, user: True,
                 log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = _utc):
        self.store, self.vault, self.is_member, self.can_record, self.log, self.now = store, vault, is_member, can_record, log, now

    # ------------------------------------------------------------------ helpers
    def today(self) -> date: return self.now().date()

    def _not_future(self, d: date, what: str):
        if d > self.today() + timedelta(days=1):
            raise FpaError(f"{what} cannot be in the future.")

    def _put(self, kind, org, d): self.store.put(kind, f"{org}:{d['id']}", d, org_id=org)
    def _all(self, kind, org) -> list: return [d for _, d in self.store.list(kind, org_id=org, prefix=f"{org}:") if d.get("org") == org]

    def _get(self, kind, org, rid, label, for_update=False) -> dict:
        r = self.store.get(kind, f"{org}:{rid}", for_update=for_update)
        if r is None or r.get("org") != org:
            raise FpaNotFoundError(f"{label} not found.")
        return r

    def _settings(self, org, for_update=False) -> dict:
        s = self.store.get("fp_setting", f"{org}:settings", for_update=for_update)
        if s and s.get("org") == org:
            return s
        return {"id": "settings", "org": org, **DEFAULTS, "counters": {}, "updated_by": None, "updated_at": None}

    def _ref(self, org, prefix) -> str:
        s = self._settings(org, for_update=True)
        n = s["counters"].get(prefix, 0) + 1
        s["counters"][prefix] = n
        self._put("fp_setting", org, s)
        return f"{prefix}-{n:03d}"

    def _hist(self, r, actor, event, note=""):
        r.setdefault("history", []).append({"at": self.now().isoformat(), "by": actor, "event": event, "note": note})

    def _two(self, actor, other, what):
        if actor == other:
            raise FpaForbiddenError(f"You {what}, so you cannot decide it. A different person must.")

    def _evidence(self, org, ids) -> List[dict]:
        out = []
        for i in dict.fromkeys(str(i) for i in (ids or [])):
            try:
                if self.vault is None: raise LookupError
                e = self.vault.get_evidence(org, i)
            except Exception:
                raise FpaError("Linked evidence not found in this organisation's Evidence Vault.")
            out.append({"evidence_id": e.id, "filename": e.original_filename, "file_hash": e.file_hash})
        return out

    def _member(self, org, user, what):
        if not isinstance(user, str) or not user.strip() or not self.is_member(org, user.strip()):
            raise FpaError(f"{what} must be a member of this organisation.")
        if not self.can_record(org, user.strip()):
            raise FpaError(f"{what} must hold a role that can record KPI readings (Owner, Manager, Finance Officer or Accountant), otherwise nobody could record them.")
        return user.strip()

    # ------------------------------------------------------------------ policy
    def get_fpa_policy(self, org) -> dict:
        s = self._settings(org)
        return {"watch_pct": s["watch_pct"], "grace_days": s["grace_days"], "accuracy_pct": s["accuracy_pct"], "min_items": s["min_items"], "updated_by": s["updated_by"], "updated_at": s["updated_at"],
                "meaning": f"A new KPI is flagged 'close to target' when it is short of its target by no more than {s['watch_pct']}% of the target (fixed on each KPI when it is defined). A reading is overdue {s['grace_days']} days after its period ends. "
                           f"A forecast counts as accurate when it is within {s['accuracy_pct']}% of the confirmed actual (the band is fixed on each forecast when it is registered). An accuracy figure needs at least {s['min_items']} confirmed forecasts before it is called meaningful. These are your own settings, not a standard."}

    def set_fpa_policy(self, org, d, actor) -> dict:
        s = self._settings(org, for_update=True)
        for k, name, lo, hi in (("watch_pct", "The warning margin", 0, 50), ("grace_days", "The grace period", 0, 90), ("accuracy_pct", "The accuracy band", 0, 100), ("min_items", "The minimum number of forecasts", 1, 50)):
            if d.get(k) is not None: s[k] = _int(d[k], name, lo, hi)
        s.update(updated_by=actor, updated_at=self.now().isoformat())
        self._put("fp_setting", org, s)
        self.log("FPA_POLICY_SET", actor, "settings", org, f"watch {s['watch_pct']}, grace {s['grace_days']}, accuracy {s['accuracy_pct']}, min items {s['min_items']}")
        return self.get_fpa_policy(org)

    # ------------------------------------------------------------------ KPIs
    def _kmeaning(self, k) -> str:
        pl = UNITS[k["unit"]]; unit = k["currency"] if k["unit"] == "AMOUNT" else k["unit"].lower()
        side = "at or above" if k["direction"] == "HIGHER_BETTER" else "at or below"
        return f"{'Higher' if k['direction'] == 'HIGHER_BETTER' else 'Lower'} is better. On target when {side} {fmt(Decimal(k['target']), pl)} ({unit}); close to target when short by no more than {k['watch_pct']}% of the target."

    def define_kpi(self, org, d, actor) -> dict:
        name = _txt(d.get("name"), "The KPI name", 3, 120)
        if any(x["name"].casefold() == name.casefold() and x["status"] != "RETIRED" for x in self._all("fp_kpi", org)):
            raise FpaStateError("A KPI with that name already exists. Retire it first if you are replacing it.")
        unit = _enum(d.get("unit"), list(UNITS), "The unit")
        currency = _currency(d.get("currency")) if unit == "AMOUNT" else None
        if unit != "AMOUNT" and d.get("currency") not in (None, ""): raise FpaError("Only an amount KPI has a currency.")
        direction = _enum(d.get("direction"), DIRECTIONS, "The direction")
        freq = _enum(d.get("frequency"), FREQUENCIES, "The frequency")
        owner = self._member(org, d.get("owner"), "The owner")
        target = _num(d.get("target"), "The target", UNITS[unit])
        watch = _int(d["watch_pct"], "The warning margin", 0, 50) if d.get("watch_pct") not in (None, "") else self._settings(org)["watch_pct"]
        eff = _date(d.get("effective_from"), "The date it starts")
        k = {"id": uuid.uuid4().hex, "org": org, "ref": None, "name": name, "description": _txt(d.get("description"), "What it measures", 5, 500),
             "unit": unit, "currency": currency, "direction": direction, "frequency": freq, "owner": owner, "owner_accepted": False,
             "data_source": _txt(d.get("data_source"), "Where the number comes from", 10, 500), "method": _txt(d.get("method"), "How it is calculated", 10, 500),
             "target": fmt(target, UNITS[unit]), "watch_pct": watch, "effective_from": eff.isoformat(), "status": "DRAFT", "created_by": actor, "created_at": self.now().isoformat(),
             "approved_by": None, "history": [], "owner_history": [{"owner": owner, "at": self.now().isoformat(), "by": actor, "reason": "Named when the KPI was defined"}]}
        k["ref"] = self._ref(org, "KP"); self._hist(k, actor, "DEFINED", f"owner {owner}")
        self._put("fp_kpi", org, k); self.log("FPA_KPI_DEFINED", actor, k["id"], org, f"{k['ref']} {name}, owner {owner}")
        return self._kview(org, k)

    def approve_kpi(self, org, kid, actor, note="") -> dict:
        k = self._get("fp_kpi", org, kid, "KPI", for_update=True)
        if k["status"] != "DRAFT": raise FpaStateError("Only a KPI waiting for approval can be approved.")
        self._two(actor, k["created_by"], "defined this KPI")
        self._two(actor, k["owner"], "are the owner who is measured against this target")
        k.update(status="ACTIVE", approved_by=actor); self._hist(k, actor, "APPROVED", _txt(note, "The note", 0, 500, required=False))
        self._put("fp_kpi", org, k); self.log("FPA_KPI_APPROVED", actor, kid, org, k["ref"])
        return self._kview(org, k)

    def accept_kpi_ownership(self, org, kid, actor) -> dict:
        k = self._get("fp_kpi", org, kid, "KPI", for_update=True)
        if k["status"] == "RETIRED": raise FpaStateError("This KPI is retired.")
        if k["owner"] != actor: raise FpaForbiddenError("Only the named owner can accept ownership of a KPI.")
        if k["owner_accepted"]: raise FpaStateError("Ownership is already accepted.")
        k["owner_accepted"] = True; self._hist(k, actor, "OWNERSHIP_ACCEPTED")
        self._put("fp_kpi", org, k); self.log("FPA_KPI_OWNERSHIP_ACCEPTED", actor, kid, org, k["ref"])
        return self._kview(org, k)

    def reassign_kpi_owner(self, org, kid, new_owner, reason, actor) -> dict:
        k = self._get("fp_kpi", org, kid, "KPI", for_update=True)
        if k["status"] == "RETIRED": raise FpaStateError("This KPI is retired.")
        owner = self._member(org, new_owner, "The new owner")
        if owner == k["owner"]: raise FpaStateError("That person already owns this KPI.")
        reason = _txt(reason, "A reason", 5, 500)
        if k["status"] == "ACTIVE" and owner == k["approved_by"]:
            raise FpaForbiddenError("The person who approved this KPI's target cannot become its owner. Choose someone else.")
        k["owner_history"].append({"owner": owner, "at": self.now().isoformat(), "by": actor, "reason": reason})
        k.update(owner=owner, owner_accepted=False); self._hist(k, actor, "OWNER_CHANGED", f"to {owner}: {reason}")
        self._put("fp_kpi", org, k); self.log("FPA_KPI_OWNER_CHANGED", actor, kid, org, f"{k['ref']} to {owner}")
        return self._kview(org, k)

    def retire_kpi(self, org, kid, reason, actor) -> dict:
        k = self._get("fp_kpi", org, kid, "KPI", for_update=True)
        if k["status"] == "RETIRED": raise FpaStateError("This KPI is already retired.")
        reason = _txt(reason, "A reason", 5, 500)
        k["status"] = "RETIRED"; self._hist(k, actor, "RETIRED", reason)
        self._put("fp_kpi", org, k); self.log("FPA_KPI_RETIRED", actor, kid, org, k["ref"])
        return self._kview(org, k)

    def _readings(self, org, kid=None) -> list:
        rs = [r for r in self._all("fp_reading", org) if kid is None or r["kpi_id"] == kid]
        return sorted(rs, key=lambda r: (r["period_end"], r["recorded_at"], refnum(r)))

    def _live(self, rs) -> list: return [r for r in rs if r["status"] in ("RECORDED", "REVIEWED")]

    def _rview(self, k, r) -> dict:
        v = {x: r[x] for x in ("id", "ref", "kpi_id", "kpi_ref", "period_end", "value", "source_note", "evidence", "status", "recorded_by", "recorded_at", "reviewed_by", "reviewed_at", "superseded_by", "history")}
        j = judge(Decimal(r["value"]), Decimal(k["target"]), k["direction"], k["watch_pct"])
        v.update(judgement=j["status"], shortfall_pct=j["shortfall_pct"], gap=fmt(Decimal(r["value"]) - Decimal(k["target"]), UNITS[k["unit"]]), traceable=bool(r["evidence"]))
        return v

    def _kview(self, org, k, with_readings=True) -> dict:
        v = {x: k[x] for x in ("id", "ref", "name", "description", "unit", "currency", "direction", "frequency", "owner", "owner_accepted", "data_source", "method", "target", "watch_pct", "effective_from", "status", "created_by", "approved_by", "history", "owner_history")}
        rs = self._readings(org, k["id"]); live = self._live(rs)
        v["meaning"] = self._kmeaning(k)
        latest = live[-1] if live else None
        v["latest"] = self._rview(k, latest) if latest else None
        v["judgement"] = v["latest"]["judgement"] if latest else "NOT_MEASURED"
        v["unreviewed"] = bool(latest and latest["status"] == "RECORDED")
        g = self._settings(org)["grace_days"]
        if k["status"] == "ACTIVE":
            eff = date.fromisoformat(k["effective_from"])
            nxt = next_period_end(date.fromisoformat(latest["period_end"]), k["frequency"]) if latest else (add_months(eff, 12) - timedelta(days=1) if k["frequency"] == "ANNUAL" else period_end_for(eff, k["frequency"]))
            due = nxt + timedelta(days=g)
            v.update(next_period_end=nxt.isoformat(), due=due.isoformat(), overdue=due < self.today(), can_record=bool(k["owner_accepted"]))
        else:
            v.update(next_period_end=None, due=None, overdue=False, can_record=False)
        v["live_readings"] = len(live); v["untraceable"] = sum(1 for r in live if not r["evidence"])
        if with_readings: v["readings"] = [self._rview(k, r) for r in reversed(rs)]
        return v

    def list_kpis(self, org, status=None, owner=None) -> List[dict]:
        ks = sorted(self._all("fp_kpi", org), key=refnum)
        return [self._kview(org, k, with_readings=False) for k in ks if (not status or k["status"] == status) and (not owner or k["owner"] == owner)]

    def get_kpi(self, org, kid) -> dict: return self._kview(org, self._get("fp_kpi", org, kid, "KPI"))

    def record_kpi_reading(self, org, kid, d, actor) -> dict:
        k = self._get("fp_kpi", org, kid, "KPI", for_update=True)
        if k["status"] != "ACTIVE": raise FpaStateError("Readings can only be recorded for an approved KPI that is not retired.")
        if k["owner"] != actor: raise FpaForbiddenError("Only the owner of this KPI records its readings.")
        if not k["owner_accepted"]: raise FpaStateError("Accept ownership of this KPI before recording a reading.")
        pe = _date(d.get("period_end"), "The period end"); self._not_future(pe, "The period end")
        if pe < date.fromisoformat(k["effective_from"]): raise FpaError("The period ends before this KPI starts.")
        if k["frequency"] != "ANNUAL" and pe != period_end_for(pe, k["frequency"]):
            raise FpaError("A monthly KPI's period ends on the last day of a month; a quarterly KPI's on 31 March, 30 June, 30 September or 31 December.")
        value = _num(d.get("value"), "The value", UNITS[k["unit"]])
        note = _txt(d.get("source_note"), "Where the number came from", 10, 500)
        ev = self._evidence(org, d.get("evidence_ids"))
        old = [r for r in self._live(self._readings(org, kid)) if r["period_end"] == pe.isoformat()]
        why = _txt(d.get("correction_note"), "The reason for the correction", 10, 500, required=bool(old)) if (old or d.get("correction_note")) else ""
        r = {"id": uuid.uuid4().hex, "org": org, "ref": None, "kpi_id": kid, "kpi_ref": k["ref"], "period_end": pe.isoformat(), "value": fmt(value, UNITS[k["unit"]]), "source_note": note, "evidence": ev,
             "status": "RECORDED", "recorded_by": actor, "recorded_at": self.now().isoformat(), "reviewed_by": None, "reviewed_at": None, "superseded_by": None, "history": []}
        r["ref"] = self._ref(org, "KR"); self._hist(r, actor, "RECORDED", why)
        for o in old:
            o["status"] = "SUPERSEDED"; o["superseded_by"] = r["id"]; self._hist(o, actor, "SUPERSEDED", why); self._put("fp_reading", org, o)
        self._put("fp_reading", org, r); self.log("FPA_KPI_READING_RECORDED", actor, r["id"], org, f"{r['ref']} for {k['ref']} period {pe}" + (" (correction)" if old else ""))
        return self._rview(k, r)

    def _reading(self, org, kid, rid, for_update=False):
        r = self._get("fp_reading", org, rid, "Reading", for_update=for_update)
        if r["kpi_id"] != kid: raise FpaNotFoundError("Reading not found.")
        return r, self._get("fp_kpi", org, kid, "KPI")

    def review_kpi_reading(self, org, kid, rid, actor, note="") -> dict:
        r, k = self._reading(org, kid, rid, True)
        if r["status"] != "RECORDED": raise FpaStateError("Only a reading waiting for review can be reviewed.")
        self._two(actor, r["recorded_by"], "recorded this reading")
        r.update(status="REVIEWED", reviewed_by=actor, reviewed_at=self.now().isoformat()); self._hist(r, actor, "REVIEWED", _txt(note, "The note", 0, 500, required=False))
        self._put("fp_reading", org, r); self.log("FPA_KPI_READING_REVIEWED", actor, rid, org, r["ref"])
        return self._rview(k, r)

    def reject_kpi_reading(self, org, kid, rid, reason, actor) -> dict:
        r, k = self._reading(org, kid, rid, True)
        if r["status"] != "RECORDED": raise FpaStateError("Only a reading waiting for review can be rejected.")
        self._two(actor, r["recorded_by"], "recorded this reading")
        r["status"] = "REJECTED"; self._hist(r, actor, "REJECTED", _txt(reason, "A reason", 5, 500))
        self._put("fp_reading", org, r); self.log("FPA_KPI_READING_REJECTED", actor, rid, org, r["ref"])
        return self._rview(k, r)

    # ------------------------------------------------------------------ forecasts
    def _fview(self, org, f) -> dict:
        v = {x: f[x] for x in ("id", "ref", "metric", "unit", "currency", "period_end", "made_on", "value", "basis", "kpi_id", "kpi_ref", "forecaster", "status", "actual", "withdrawn_note", "history")}
        pe, made = date.fromisoformat(f["period_end"]), date.fromisoformat(f["made_on"])
        v["lead_days"] = (pe - made).days
        v["actual_due"] = f["status"] == "OPEN" and pe <= self.today() + timedelta(days=1)
        v["error"] = self._error(f) if f["actual"] else None
        return v

    def _error(self, f) -> dict:
        pl = UNITS[f["unit"]]; fc, ac = Decimal(f["value"]), Decimal(f["actual"]["value"]); e = fc - ac
        p = None if ac == 0 else abs(e) / abs(ac) * 100
        tol = f.get("accuracy_pct", DEFAULTS["accuracy_pct"])
        within = (e == 0) if p is None else p <= tol
        return {"error": fmt(e, pl), "abs_error": fmt(abs(e), pl), "pct_error": fmt(p, 2) if p is not None else None, "direction": "EXACT" if e == 0 else "OVER" if e > 0 else "UNDER", "within": within}

    def register_forecast(self, org, d, actor) -> dict:
        metric = _txt(d.get("metric"), "The metric", 3, 120)
        unit = _enum(d.get("unit"), list(UNITS), "The unit")
        currency = _currency(d.get("currency")) if unit == "AMOUNT" else None
        if unit != "AMOUNT" and d.get("currency") not in (None, ""): raise FpaError("Only an amount has a currency.")
        pe = _date(d.get("period_end"), "The period the forecast is for"); today = self.today()
        if pe < today: raise FpaError("A forecast must be for a period that has not yet ended. Forecasts are stamped with today's date and cannot be back-dated.")
        value = _num(d.get("value"), "The forecast value", UNITS[unit])
        basis = _txt(d.get("basis"), "The basis of the forecast", 10, 500)
        kpi_id = kpi_ref = None
        if d.get("kpi_id"):
            k = self._get("fp_kpi", org, str(d["kpi_id"]), "KPI")
            if k["unit"] != unit or k["currency"] != currency: raise FpaError("The forecast must use the same unit and currency as the KPI it is linked to.")
            kpi_id, kpi_ref = k["id"], k["ref"]
        f = {"id": uuid.uuid4().hex, "org": org, "ref": None, "metric": metric, "unit": unit, "currency": currency, "period_end": pe.isoformat(), "made_on": today.isoformat(), "value": fmt(value, UNITS[unit]),
             "basis": basis, "kpi_id": kpi_id, "kpi_ref": kpi_ref, "forecaster": actor, "status": "OPEN", "actual": None, "withdrawn_note": None, "accuracy_pct": self._settings(org)["accuracy_pct"], "history": []}
        f["ref"] = self._ref(org, "FC"); self._hist(f, actor, "REGISTERED")
        self._put("fp_forecast", org, f); self.log("FPA_FORECAST_REGISTERED", actor, f["id"], org, f"{f['ref']} {metric} for {pe}")
        return self._fview(org, f)

    def withdraw_forecast(self, org, fid, reason, actor) -> dict:
        f = self._get("fp_forecast", org, fid, "Forecast", for_update=True)
        if f["forecaster"] != actor: raise FpaForbiddenError("Only the person who made a forecast can withdraw it.")
        if f["status"] != "OPEN": raise FpaStateError("Only a forecast that has no actual recorded can be withdrawn.")
        reason = _txt(reason, "A reason", 5, 500); f.update(status="WITHDRAWN", withdrawn_note=reason); self._hist(f, actor, "WITHDRAWN", reason)
        self._put("fp_forecast", org, f); self.log("FPA_FORECAST_WITHDRAWN", actor, fid, org, f["ref"])
        return self._fview(org, f)

    def record_forecast_actual(self, org, fid, d, actor) -> dict:
        f = self._get("fp_forecast", org, fid, "Forecast", for_update=True)
        if f["status"] != "OPEN": raise FpaStateError("An actual can only be recorded for a forecast that is open.")
        self._two(actor, f["forecaster"], "made this forecast")
        if date.fromisoformat(f["period_end"]) > self.today() + timedelta(days=1): raise FpaStateError("The period has not ended yet, so there is no actual to record.")
        value = _num(d.get("value"), "The actual value", UNITS[f["unit"]])
        note = _txt(d.get("source_note"), "Where the actual came from", 10, 500); ev = self._evidence(org, d.get("evidence_ids"))
        f["actual"] = {"value": fmt(value, UNITS[f["unit"]]), "source_note": note, "evidence": ev, "recorded_by": actor, "recorded_at": self.now().isoformat(), "confirmed_by": None, "confirmed_at": None}
        f["status"] = "ACTUAL_RECORDED"; self._hist(f, actor, "ACTUAL_RECORDED")
        self._put("fp_forecast", org, f); self.log("FPA_ACTUAL_RECORDED", actor, fid, org, f["ref"])
        return self._fview(org, f)

    def confirm_forecast_actual(self, org, fid, actor, note="") -> dict:
        f = self._get("fp_forecast", org, fid, "Forecast", for_update=True)
        if f["status"] != "ACTUAL_RECORDED": raise FpaStateError("Only an actual waiting for confirmation can be confirmed.")
        self._two(actor, f["actual"]["recorded_by"], "recorded this actual")
        self._two(actor, f["forecaster"], "made this forecast")
        f["actual"].update(confirmed_by=actor, confirmed_at=self.now().isoformat()); f["status"] = "CONFIRMED"; self._hist(f, actor, "ACTUAL_CONFIRMED", _txt(note, "The note", 0, 500, required=False))
        self._put("fp_forecast", org, f); self.log("FPA_ACTUAL_CONFIRMED", actor, fid, org, f["ref"])
        return self._fview(org, f)

    def reject_forecast_actual(self, org, fid, reason, actor) -> dict:
        f = self._get("fp_forecast", org, fid, "Forecast", for_update=True)
        if f["status"] != "ACTUAL_RECORDED": raise FpaStateError("Only an actual waiting for confirmation can be rejected.")
        self._two(actor, f["actual"]["recorded_by"], "recorded this actual")
        self._two(actor, f["forecaster"], "made this forecast")
        reason = _txt(reason, "A reason", 5, 500); self._hist(f, actor, "ACTUAL_REJECTED", f"value {f['actual']['value']}: {reason}")
        f["actual"] = None; f["status"] = "OPEN"
        self._put("fp_forecast", org, f); self.log("FPA_ACTUAL_REJECTED", actor, fid, org, f["ref"])
        return self._fview(org, f)

    def list_forecasts(self, org, status=None) -> List[dict]:
        fs = sorted(self._all("fp_forecast", org), key=refnum)
        return [self._fview(org, f) for f in fs if not status or f["status"] == status]

    def get_forecast(self, org, fid) -> dict: return self._fview(org, self._get("fp_forecast", org, fid, "Forecast"))

    def forecast_accuracy_report(self, org, min_lead_days=0) -> dict:
        s = self._settings(org); min_lead = _int(min_lead_days, "The minimum lead time", 0, 3650)
        all_f = self._all("fp_forecast", org)
        done = [f for f in all_f if f["status"] == "CONFIRMED"]
        used = [f for f in done if (date.fromisoformat(f["period_end"]) - date.fromisoformat(f["made_on"])).days >= min_lead]
        groups, people = {}, {}
        for f in used:
            e = self._error(f); pl = UNITS[f["unit"]]
            key = (f["metric"].casefold(), f["unit"], f["currency"])
            g = groups.setdefault(key, {"metric": f["metric"], "unit": f["unit"], "currency": f["currency"], "n": 0, "abs": Decimal(0), "signed": Decimal(0), "actual_abs": Decimal(0), "over": 0, "under": 0, "exact": 0, "within": 0, "lead": 0})
            fc, ac = Decimal(f["value"]), Decimal(f["actual"]["value"])
            g["n"] += 1; g["abs"] += abs(fc - ac); g["signed"] += fc - ac; g["actual_abs"] += abs(ac)
            g[{"OVER": "over", "UNDER": "under", "EXACT": "exact"}[e["direction"]]] += 1; g["within"] += 1 if e["within"] else 0
            g["lead"] += (date.fromisoformat(f["period_end"]) - date.fromisoformat(f["made_on"])).days
            p = people.setdefault(f["forecaster"], {"forecaster": f["forecaster"], "n": 0, "within": 0, "over": 0, "under": 0})
            p["n"] += 1; p["within"] += 1 if e["within"] else 0; p["over"] += e["direction"] == "OVER"; p["under"] += e["direction"] == "UNDER"
        out = []
        for g in sorted(groups.values(), key=lambda g: (g["metric"].casefold(), g["unit"], g["currency"] or "")):
            pl = UNITS[g["unit"]]
            out.append({"metric": g["metric"], "unit": g["unit"], "currency": g["currency"], "n": g["n"], "wape": pct(g["abs"], g["actual_abs"]), "bias": pct(g["signed"], g["actual_abs"]), "mean_abs_error": fmt(g["abs"] / g["n"], pl),
                        "over": g["over"], "under": g["under"], "exact": g["exact"], "within": g["within"], "hit_rate": fmt(Decimal(g["within"]) / g["n"] * 100, 2), "average_lead_days": fmt(Decimal(g["lead"]) / g["n"], 1), "enough": g["n"] >= s["min_items"]})
        ppl = [{**p, "hit_rate": fmt(Decimal(p["within"]) / p["n"] * 100, 2), "enough": p["n"] >= s["min_items"]} for p in sorted(people.values(), key=lambda p: p["forecaster"])]
        return {"groups": out, "forecasters": ppl, "counted": len(used), "excluded_short_lead": len(done) - len(used), "awaiting_confirmation": sum(1 for f in all_f if f["status"] == "ACTUAL_RECORDED"),
                "open_due": sum(1 for f in all_f if f["status"] == "OPEN" and date.fromisoformat(f["period_end"]) <= self.today() + timedelta(days=1)), "accuracy_pct": s["accuracy_pct"], "min_items": s["min_items"],
                "min_lead_days": min_lead, "meaning": "Forecast error is forecast minus confirmed actual. Weighted absolute percentage error (WAPE) is the total absolute error divided by the total absolute actual. Bias is the total signed error divided by the same total: "
                "positive means forecasts ran too high, negative too low. Only confirmed actuals count. Each metric, unit and currency is reported on its own."}

    # ------------------------------------------------------------------ overview
    def fpa_overview(self, org) -> dict:
        ks = self._all("fp_kpi", org); views = [self._kview(org, k, with_readings=False) for k in sorted(ks, key=refnum)]
        active = [v for v in views if v["status"] == "ACTIVE"]
        fs = self._all("fp_forecast", org); rep = self.forecast_accuracy_report(org)
        att = []

        def add(kind, n, text):
            if n: att.append({"kind": kind, "count": n, "text": text})
        add("KPIS_PENDING", sum(1 for v in views if v["status"] == "DRAFT"), "KPI definition(s) are waiting for a different person to approve them.")
        add("OWNERSHIP_PENDING", sum(1 for v in views if v["status"] != "RETIRED" and not v["owner_accepted"]), "KPI(s) have an owner who has not accepted ownership yet.")
        add("KPI_OVERDUE", sum(1 for v in active if v["overdue"]), "KPI(s) have a reading overdue.")
        add("KPI_OFF_TARGET", sum(1 for v in active if v["judgement"] == "OFF_TARGET"), "KPI(s) are off target on their latest reading.")
        add("KPI_WATCH", sum(1 for v in active if v["judgement"] == "WATCH"), "KPI(s) are close to missing their target.")
        readings = [r for r in self._all("fp_reading", org) if r["status"] == "RECORDED"]
        add("READINGS_TO_REVIEW", len(readings), "KPI reading(s) are waiting for a different person to review them.")
        add("READINGS_UNTRACED", sum(v["untraceable"] for v in active), "live KPI reading(s) have no document attached, only a written source.")
        add("ACTUALS_DUE", rep["open_due"], "forecast(s) are for a period that has ended and have no actual yet.")
        add("ACTUALS_TO_CONFIRM", rep["awaiting_confirmation"], "forecast actual(s) are waiting for a third person to confirm them.")
        for g in rep["groups"]:
            if g["enough"] and g["bias"] is not None and abs(Decimal(g["bias"])) > rep["accuracy_pct"]:
                att.append({"kind": "FORECAST_BIAS", "count": 1, "text": f"{g['metric']}{' (' + g['currency'] + ')' if g['currency'] else ''}: forecasts have run {'high' if Decimal(g['bias']) > 0 else 'low'} by {abs(Decimal(g['bias']))}% over {g['n']} periods."})
        owners = {}
        for v in views:
            if v["status"] == "RETIRED": continue
            o = owners.setdefault(v["owner"], {"owner": v["owner"], "kpis": 0, "overdue": 0, "off_target": 0, "not_accepted": 0})
            o["kpis"] += 1; o["overdue"] += 1 if v["overdue"] else 0; o["off_target"] += 1 if v["judgement"] == "OFF_TARGET" else 0; o["not_accepted"] += 0 if v["owner_accepted"] else 1
        return {"counts": {"kpis": len(views), "active": len(active), "retired": sum(1 for v in views if v["status"] == "RETIRED"), "forecasts": len(fs), "forecasts_confirmed": rep["counted"] + rep["excluded_short_lead"]},
                "attention": att, "owners": sorted(owners.values(), key=lambda o: o["owner"]), "policy": self.get_fpa_policy(org), "limitations": LIMITATIONS}

    def fpa_options(self, org) -> dict:
        ks = [k for k in sorted(self._all("fp_kpi", org), key=refnum) if k["status"] != "RETIRED"]
        return {"units": [{"id": u, "places": p} for u, p in UNITS.items()], "directions": DIRECTIONS, "frequencies": FREQUENCIES,
                "kpis": [{"id": k["id"], "ref": k["ref"], "name": k["name"], "unit": k["unit"], "currency": k["currency"], "status": k["status"], "owner": k["owner"]} for k in ks], "limitations": LIMITATIONS}
