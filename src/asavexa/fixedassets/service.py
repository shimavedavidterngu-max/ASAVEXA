"""Fixed assets register (records and evidence): assets, a straight-line depreciation schedule, disposals and physical counts.

Records (shared document store, per organisation): fa_asset, fa_setting.

Principles enforced here
  * This records what people say about assets and works out straight-line depreciation from the figures they typed, using exact decimal arithmetic. It posts nothing to the ledger and values nothing.
  * An asset becomes active only when a person other than the one who proposed it approves it. A disposal is approved by a person other than the one who proposed it. A physical count is reviewed by a person other than the one who recorded it.
  * Amounts are kept per currency and never added across currencies. Land is recorded but not depreciated.
Nothing is edited or deleted; records are rejected or decided with a reason. Every step is audited. No accounting standard or tax rule is claimed.
"""
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Callable, List

from .errors import FixedAssetError, FixedAssetForbiddenError, FixedAssetNotFoundError, FixedAssetStateError

CATEGORIES = ["LAND", "BUILDINGS", "PLANT_AND_MACHINERY", "VEHICLES", "FURNITURE_AND_FITTINGS", "IT_EQUIPMENT", "OTHER"]
COUNT_RESULTS = ["FOUND", "MISSING", "DAMAGED"]
DEFAULTS = {"count_days": 365}
CENT = Decimal("0.01")
LIMITATIONS = [
    "ASAVEXA records the cost, residual value and useful life that people type in and works out straight-line depreciation from them. It does not post to the ledger, value or revalue anything, or check the figures against invoices.",
    "Net book value and any gain or loss on disposal here are arithmetic on those figures, month by month from the acquisition date. They are not an accounting or tax result and follow no accounting standard.",
    "Only straight-line depreciation is supported. Land is recorded without depreciation. Impairment, component accounting and tax allowances are not handled.",
    "A physical count is a person's statement that they found, did not find or found damaged an asset. ASAVEXA cannot tell whether the asset exists.",
    "Amounts in different currencies are never added together.",
    "ASAVEXA cannot know about an asset nobody records.",
]


def _utc(): return datetime.now(timezone.utc)


def _txt(v, name, lo=1, hi=1000, required=True) -> str:
    v = (v if isinstance(v, str) else ("" if v is None else str(v)))
    v = " ".join("".join(c if c >= " " and c != "\x7f" else " " for c in v).split())
    if required and len(v) < lo:
        raise FixedAssetError(f"{name} is required (at least {lo} characters).")
    if v and len(v) < lo:
        raise FixedAssetError(f"{name} needs at least {lo} characters.")
    if len(v) > hi:
        raise FixedAssetError(f"{name} is too long (limit {hi} characters).")
    return v


def _date(v, name) -> date:
    try:
        return date.fromisoformat(str(v).strip())
    except (ValueError, TypeError):
        raise FixedAssetError(f"{name} must be a real date written YYYY-MM-DD.")


def _enum(v, allowed, name) -> str:
    v = _txt(v, name, 1, 40).upper()
    if v not in allowed:
        raise FixedAssetError(f"{name} must be one of {', '.join(allowed)}.")
    return v


def _int(v, name, lo, hi) -> int:
    if isinstance(v, bool) or not str(v).strip().isdigit():
        raise FixedAssetError(f"{name} must be a whole number from {lo} to {hi}.")
    n = int(str(v).strip())
    if not lo <= n <= hi:
        raise FixedAssetError(f"{name} must be a whole number from {lo} to {hi}.")
    return n


def _money(v, name, allow_zero=False) -> Decimal:
    """An amount written as text or a whole number, at most two decimals. Never a float."""
    if isinstance(v, bool) or isinstance(v, float) or v is None:
        raise FixedAssetError(f"{name} must be an amount such as 1500.00.")
    t = str(v).strip().replace(",", "")
    if not re.fullmatch(r"\d{1,12}(\.\d{1,2})?", t):
        raise FixedAssetError(f"{name} must be an amount such as 1500.00 (at most two decimals).")
    d = Decimal(t)
    if d == 0 and not allow_zero:
        raise FixedAssetError(f"{name} must be more than zero.")
    return d.quantize(CENT)


def refnum(r) -> int:
    try: return int(str(r["ref"]).rsplit("-", 1)[1])
    except (KeyError, IndexError, ValueError): return 0


def months_between(a: date, b: date) -> int:
    """Whole months from a to b (a month is complete on the same day of the month)."""
    if b < a: return 0
    m = (b.year - a.year) * 12 + b.month - a.month
    return max(m - (1 if b.day < a.day else 0), 0)


def accumulated(cost: Decimal, residual: Decimal, life: int, acquired: date, as_of: date) -> Decimal:
    """Straight-line depreciation to as_of; never more than cost less residual."""
    if not life: return Decimal("0.00")
    base = cost - residual; m = months_between(acquired, as_of)
    if m >= life: return base.quantize(CENT)
    return (base * m / life).quantize(CENT, rounding=ROUND_HALF_UP)


class FixedAssetService:
    def __init__(self, store, vault=None, log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = _utc):
        self.store, self.vault, self.log, self.now = store, vault, log, now

    # ------------------------------------------------------------------ helpers
    def today(self) -> date: return self.now().date()

    def _not_future(self, d: date, what: str):
        if d > self.today() + timedelta(days=1):
            raise FixedAssetError(f"{what} cannot be in the future.")

    def _put(self, kind, org, d): self.store.put(kind, f"{org}:{d['id']}", d, org_id=org)
    def _all(self, kind, org) -> list: return [d for _, d in self.store.list(kind, org_id=org, prefix=f"{org}:") if d.get("org") == org]

    def _get(self, kind, org, rid, label, for_update=False) -> dict:
        r = self.store.get(kind, f"{org}:{rid}", for_update=for_update)
        if r is None or r.get("org") != org:
            raise FixedAssetNotFoundError(f"{label} not found.")
        return r

    def _settings(self, org, for_update=False) -> dict:
        s = self.store.get("fa_setting", f"{org}:settings", for_update=for_update)
        if s and s.get("org") == org:
            return s
        return {"id": "settings", "org": org, **DEFAULTS, "counters": {}, "updated_by": None, "updated_at": None}

    def _ref(self, org, prefix) -> str:
        s = self._settings(org, for_update=True)
        n = s["counters"].get(prefix, 0) + 1
        s["counters"][prefix] = n
        self._put("fa_setting", org, s)
        return f"{prefix}-{n:03d}"

    def _hist(self, r, actor, event, note=""):
        r.setdefault("history", []).append({"at": self.now().isoformat(), "by": actor, "event": event, "note": note})

    def _two(self, actor, other, what):
        if actor == other:
            raise FixedAssetForbiddenError(f"You {what}, so you cannot do this. A different person must.")

    def _evidence(self, org, ids) -> List[dict]:
        out = []
        for i in dict.fromkeys(str(i) for i in (ids or [])):
            try:
                if self.vault is None: raise LookupError
                e = self.vault.get_evidence(org, i)
            except Exception:
                raise FixedAssetError("Linked evidence not found in this organisation's Evidence Vault.")
            out.append({"evidence_id": e.id, "filename": e.original_filename, "file_hash": e.file_hash})
        return out

    # ------------------------------------------------------------------ policy
    def fa_get_policy(self, org) -> dict:
        s = self._settings(org)
        return {"count_days": s["count_days"], "updated_by": s["updated_by"], "updated_at": s["updated_at"],
                "meaning": f"An active asset not counted within {s['count_days']} days of its last count (or acquisition) is flagged. This is your own setting, not a rule."}

    def fa_set_policy(self, org, d, actor) -> dict:
        s = self._settings(org, for_update=True)
        if d.get("count_days") is not None: s["count_days"] = _int(d["count_days"], "The days between physical counts", 30, 730)
        s.update(updated_by=actor, updated_at=self.now().isoformat())
        self._put("fa_setting", org, s)
        self.log("FIXEDASSETS_POLICY_SET", actor, "settings", org, f"count {s['count_days']} days")
        return self.fa_get_policy(org)

    # ------------------------------------------------------------------ views
    def _view(self, a) -> dict:
        v = {x: a[x] for x in a if x != "org"}
        cost, res = Decimal(a["cost"]), Decimal(a["residual"]); acq = date.fromisoformat(a["acquired_on"])
        as_of = date.fromisoformat(a["disposed_on"]) if a["status"] == "DISPOSED" else self.today()
        acc = accumulated(cost, res, a["life_months"] or 0, acq, as_of)
        v.update(as_of=as_of.isoformat(), accumulated=str(acc), net_book_value=str(cost - acc), depreciates=bool(a["life_months"]),
                 monthly=str(((cost - res) / a["life_months"]).quantize(CENT, rounding=ROUND_HALF_UP)) if a["life_months"] else "0.00",
                 fully_depreciated=bool(a["life_months"]) and acc == (cost - res).quantize(CENT))
        counts = a.get("counts", [])
        last = max((c["counted_on"] for c in counts), default=a["acquired_on"])
        v["last_counted_on"] = max((c["counted_on"] for c in counts), default=None)
        v["count_due"] = a["status"] == "ACTIVE" and date.fromisoformat(last) + timedelta(days=self._settings(a["org"])["count_days"]) < self.today()
        v["counts_to_review"] = sum(1 for c in counts if c["status"] == "UNREVIEWED")
        v["missing"] = a["status"] == "ACTIVE" and bool(counts) and sorted(counts, key=lambda c: (c["counted_on"], c["no"]))[-1]["result"] == "MISSING"
        return v

    # ------------------------------------------------------------------ assets
    def fa_propose_asset(self, org, d, actor) -> dict:
        name = _txt(d.get("name"), "The asset name", 3, 150); cat = _enum(d.get("category"), CATEGORIES, "The category"); loc = _txt(d.get("location"), "The location", 2, 150); cust = _txt(d.get("custodian_name"), "The custodian", 2, 100)
        acq = _date(d.get("acquired_on"), "The acquisition date"); self._not_future(acq, "The acquisition date")
        cur = _txt(d.get("currency"), "The currency", 3, 3).upper()
        if not re.fullmatch(r"[A-Z]{3}", cur): raise FixedAssetError("The currency must be a three-letter code such as NGN.")
        cost = _money(d.get("cost"), "The cost"); res = _money(d.get("residual_value") if d.get("residual_value") not in (None, "") else "0", "The residual value", allow_zero=True)
        if res >= cost: raise FixedAssetError("The residual value must be less than the cost.")
        if cat == "LAND":
            if d.get("life_months") not in (None, "", 0, "0"): raise FixedAssetError("Land is not depreciated. Leave the useful life empty.")
            if res != 0: raise FixedAssetError("Land has no residual value in this register. Leave it at zero.")
            life = 0
        else:
            life = _int(d.get("life_months"), "The useful life in months", 1, 600)
        serial = _txt(d.get("serial_number"), "The serial number", 2, 80, required=False); ev = self._evidence(org, d.get("evidence_ids"))
        for o in self._all("fa_asset", org):
            if serial and o.get("serial_number") == serial and o["status"] in ("PROPOSED", "ACTIVE", "DISPOSAL_PENDING"):
                raise FixedAssetStateError(f"An asset with serial number {serial} is already recorded ({o['ref']}).")
        a = {"id": uuid.uuid4().hex, "org": org, "ref": None, "name": name, "category": cat, "location": loc, "custodian_name": cust, "acquired_on": acq.isoformat(), "currency": cur, "cost": str(cost), "residual": str(res),
             "life_months": life, "serial_number": serial or None, "evidence": ev, "status": "PROPOSED", "proposed_by": actor, "proposed_at": self.now().isoformat(), "decided_by": None, "decision_note": None,
             "disposal": None, "counts": [], "history": []}
        a["ref"] = self._ref(org, "FA"); self._hist(a, actor, "PROPOSED")
        self._put("fa_asset", org, a); self.log("FIXEDASSETS_ASSET_PROPOSED", actor, a["id"], org, f"{a['ref']} {cat}")
        return self._view(a)

    def fa_approve_asset(self, org, aid, d, actor) -> dict:
        a = self._get("fa_asset", org, aid, "Asset", for_update=True)
        if a["status"] != "PROPOSED": raise FixedAssetStateError("Only a proposed asset can be approved.")
        self._two(actor, a["proposed_by"], "proposed this asset")
        note = _txt(d.get("note"), "An approval note", 10, 1000, required=False)
        a.update(status="ACTIVE", decided_by=actor, decision_note=note or None); self._hist(a, actor, "APPROVED", note)
        self._put("fa_asset", org, a); self.log("FIXEDASSETS_ASSET_APPROVED", actor, aid, org, a["ref"])
        return self._view(a)

    def fa_reject_asset(self, org, aid, reason, actor) -> dict:
        a = self._get("fa_asset", org, aid, "Asset", for_update=True)
        if a["status"] != "PROPOSED": raise FixedAssetStateError("Only a proposed asset can be rejected.")
        self._two(actor, a["proposed_by"], "proposed this asset")
        reason = _txt(reason, "A reason", 10, 500); a.update(status="REJECTED", decided_by=actor, decision_note=reason); self._hist(a, actor, "REJECTED", reason)
        self._put("fa_asset", org, a); self.log("FIXEDASSETS_ASSET_REJECTED", actor, aid, org, a["ref"])
        return self._view(a)

    def fa_list_assets(self, org, status=None, category=None) -> List[dict]:
        return [self._view(a) for a in sorted(self._all("fa_asset", org), key=refnum) if (not status or a["status"] == status) and (not category or a["category"] == category)]

    def fa_get_asset(self, org, aid) -> dict: return self._view(self._get("fa_asset", org, aid, "Asset"))

    def fa_schedule(self, org, aid, months=12) -> dict:
        """Month-end accumulated depreciation for the next months (or up to the end of life), as arithmetic on the typed figures."""
        a = self._get("fa_asset", org, aid, "Asset"); months = _int(months, "The number of months", 1, 120)
        cost, res = Decimal(a["cost"]), Decimal(a["residual"]); acq = date.fromisoformat(a["acquired_on"]); rows = []
        if a["life_months"]:
            start = months_between(acq, self.today())
            for k in range(start + 1, min(start + months, a["life_months"]) + 1):
                y, mo = divmod(acq.month - 1 + k, 12); day = min(acq.day, [31, 29 if (acq.year + y) % 4 == 0 and ((acq.year + y) % 100 or (acq.year + y) % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mo])
                on = date(acq.year + y, mo + 1, day); acc = accumulated(cost, res, a["life_months"], acq, on); rows.append({"month_no": k, "on": on.isoformat(), "accumulated": str(acc), "net_book_value": str(cost - acc)})
        return {"asset": a["ref"], "currency": a["currency"], "rows": rows, "note": "Arithmetic on the figures typed in. Not posted to any ledger."}

    # ------------------------------------------------------------------ disposals
    def fa_propose_disposal(self, org, aid, d, actor) -> dict:
        a = self._get("fa_asset", org, aid, "Asset", for_update=True)
        if a["status"] != "ACTIVE": raise FixedAssetStateError("Only an active asset can be disposed of.")
        on = _date(d.get("disposed_on"), "The disposal date"); self._not_future(on, "The disposal date")
        if on < date.fromisoformat(a["acquired_on"]): raise FixedAssetError("It cannot have been disposed of before it was acquired.")
        proceeds = _money(d.get("proceeds") if d.get("proceeds") not in (None, "") else "0", "The proceeds", allow_zero=True); reason = _txt(d.get("reason"), "The reason for disposal", 10, 1000)
        acc = accumulated(Decimal(a["cost"]), Decimal(a["residual"]), a["life_months"] or 0, date.fromisoformat(a["acquired_on"]), on); nbv = Decimal(a["cost"]) - acc
        a["disposal"] = {"disposed_on": on.isoformat(), "proceeds": str(proceeds), "reason": reason, "proposed_by": actor, "net_book_value": str(nbv), "gain_or_loss": str(proceeds - nbv), "decided_by": None, "decision_note": None}
        a["status"] = "DISPOSAL_PENDING"; self._hist(a, actor, "DISPOSAL_PROPOSED")
        self._put("fa_asset", org, a); self.log("FIXEDASSETS_DISPOSAL_PROPOSED", actor, aid, org, a["ref"])
        return self._view(a)

    def fa_approve_disposal(self, org, aid, d, actor) -> dict:
        a = self._get("fa_asset", org, aid, "Asset", for_update=True)
        if a["status"] != "DISPOSAL_PENDING": raise FixedAssetStateError("Only an asset with a disposal waiting can have it approved.")
        self._two(actor, a["disposal"]["proposed_by"], "proposed this disposal")
        note = _txt(d.get("note"), "An approval note", 10, 1000, required=False)
        a["disposal"].update(decided_by=actor, decision_note=note or None); a["status"] = "DISPOSED"; a["disposed_on"] = a["disposal"]["disposed_on"]; self._hist(a, actor, "DISPOSAL_APPROVED", note)
        self._put("fa_asset", org, a); self.log("FIXEDASSETS_DISPOSAL_APPROVED", actor, aid, org, a["ref"])
        return self._view(a)

    def fa_reject_disposal(self, org, aid, reason, actor) -> dict:
        a = self._get("fa_asset", org, aid, "Asset", for_update=True)
        if a["status"] != "DISPOSAL_PENDING": raise FixedAssetStateError("Only an asset with a disposal waiting can have it rejected.")
        self._two(actor, a["disposal"]["proposed_by"], "proposed this disposal")
        reason = _txt(reason, "A reason", 10, 500); self._hist(a, actor, "DISPOSAL_REJECTED", reason)
        a.setdefault("rejected_disposals", []).append({**a["disposal"], "decided_by": actor, "decision_note": reason}); a["disposal"] = None; a["status"] = "ACTIVE"
        self._put("fa_asset", org, a); self.log("FIXEDASSETS_DISPOSAL_REJECTED", actor, aid, org, a["ref"])
        return self._view(a)

    # ------------------------------------------------------------------ physical counts
    def fa_record_count(self, org, aid, d, actor) -> dict:
        a = self._get("fa_asset", org, aid, "Asset", for_update=True)
        if a["status"] != "ACTIVE": raise FixedAssetStateError("Only an active asset can be counted.")
        on = _date(d.get("counted_on"), "The count date"); self._not_future(on, "The count date")
        if on < date.fromisoformat(a["acquired_on"]): raise FixedAssetError("It cannot have been counted before it was acquired.")
        res = _enum(d.get("result"), COUNT_RESULTS, "The result"); note = _txt(d.get("note"), "The count note", 10, 1000); ev = self._evidence(org, d.get("evidence_ids"))
        a["counts"].append({"no": len(a["counts"]) + 1, "counted_on": on.isoformat(), "result": res, "note": note, "counted_by": actor, "evidence": ev, "status": "UNREVIEWED", "reviewed_by": None, "review_note": None})
        self._hist(a, actor, f"COUNTED_{res}")
        self._put("fa_asset", org, a); self.log("FIXEDASSETS_COUNT_RECORDED", actor, aid, org, f"{a['ref']} {res}")
        return self._view(a)

    def fa_review_count(self, org, aid, no, d, actor) -> dict:
        a = self._get("fa_asset", org, aid, "Asset", for_update=True)
        c = next((c for c in a["counts"] if c["no"] == _int(no, "The count number", 1, 100000)), None)
        if c is None: raise FixedAssetNotFoundError("Count not found.")
        if c["status"] != "UNREVIEWED": raise FixedAssetStateError("That count has already been reviewed.")
        self._two(actor, c["counted_by"], "recorded this count")
        note = _txt(d.get("note"), "A review note", 10, 1000)
        c.update(status="REVIEWED", reviewed_by=actor, review_note=note); self._hist(a, actor, "COUNT_REVIEWED", note)
        self._put("fa_asset", org, a); self.log("FIXEDASSETS_COUNT_REVIEWED", actor, aid, org, f"{a['ref']} #{c['no']}")
        return self._view(a)

    # ------------------------------------------------------------------ overview
    def fa_overview(self, org) -> dict:
        assets = self.fa_list_assets(org); att = []; live = [a for a in assets if a["status"] in ("ACTIVE", "DISPOSAL_PENDING")]

        def add(kind, n, text):
            if n: att.append({"kind": kind, "count": n, "text": text})
        add("MISSING_ASSETS", sum(1 for a in assets if a["missing"]), "active asset(s) were last counted as missing.")
        add("COUNTS_OVERDUE", sum(1 for a in assets if a["count_due"]), "active asset(s) have not been counted within your window.")
        add("ASSETS_TO_APPROVE", sum(1 for a in assets if a["status"] == "PROPOSED"), "asset(s) are waiting for a different person to approve them.")
        add("DISPOSALS_TO_DECIDE", sum(1 for a in assets if a["status"] == "DISPOSAL_PENDING"), "disposal(s) are waiting for a different person to decide them.")
        add("COUNTS_TO_REVIEW", sum(a["counts_to_review"] for a in assets), "count(s) are waiting for a different person to review them.")
        totals = {}
        for a in live:
            t = totals.setdefault(a["currency"], {"currency": a["currency"], "assets": 0, "cost": Decimal("0"), "accumulated": Decimal("0"), "net_book_value": Decimal("0")})
            t["assets"] += 1; t["cost"] += Decimal(a["cost"]); t["accumulated"] += Decimal(a["accumulated"]); t["net_book_value"] += Decimal(a["net_book_value"])
        totals = [{**t, "cost": str(t["cost"]), "accumulated": str(t["accumulated"]), "net_book_value": str(t["net_book_value"])} for t in sorted(totals.values(), key=lambda x: x["currency"])]
        return {"counts": {"proposed": sum(1 for a in assets if a["status"] == "PROPOSED"), "active": sum(1 for a in assets if a["status"] == "ACTIVE"), "disposal_pending": sum(1 for a in assets if a["status"] == "DISPOSAL_PENDING"),
                           "disposed": sum(1 for a in assets if a["status"] == "DISPOSED"), "fully_depreciated": sum(1 for a in live if a["fully_depreciated"])},
                "totals": totals, "attention": att, "policy": self.fa_get_policy(org), "limitations": LIMITATIONS}

    def fa_options(self, org) -> dict:
        return {"categories": CATEGORIES, "count_results": COUNT_RESULTS, "limitations": LIMITATIONS}
