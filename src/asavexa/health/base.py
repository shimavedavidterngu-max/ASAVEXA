"""Shared helpers for the health-centre service: validation, numbering, history, facility access, evidence links."""
import hashlib
import json
import re
import uuid
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import List

from .errors import HealthError, HealthForbiddenError, HealthNotFoundError, HealthStateError

P_READ, P_PREPARE, P_APPROVE, P_ADMIN, P_CLAIMS, P_STAFFING = "health:read", "health:prepare", "health:approve", "health:admin", "health:claims", "health:staffing"
ZERO = Decimal("0.00")
CATEGORIES = ["STAFFING", "MEDICAL_SUPPLIES", "EQUIPMENT", "MAINTENANCE", "UTILITIES", "ADMINISTRATION", "OTHER"]
FACILITY_TYPES = ["PRIMARY_HEALTH_CENTRE", "CLINIC", "COMMUNITY_HEALTH_FACILITY", "SMALL_HOSPITAL"]
OWNERSHIP = ["PUBLIC", "PRIVATE", "FAITH_BASED", "NGO"]


def _utc(): return datetime.now(timezone.utc)
def sha(o) -> str: return hashlib.sha256(json.dumps(o, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
def q2(x) -> Decimal: return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
def s2(x) -> str: return str(q2(x))
def q3(x) -> Decimal: return Decimal(x).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
def s3(x) -> str: return str(q3(x))
def q4(x) -> Decimal: return Decimal(x).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
def norm(s) -> str: return re.sub(r"[^A-Z0-9]", "", str(s).upper())
def safe(v):
    v = "" if v is None else str(v)
    return "'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v


def txt(v, name, lo=1, hi=1000, required=True) -> str:
    v = (v if isinstance(v, str) else ("" if v is None else str(v))).strip()
    if required and len(v) < lo:
        raise HealthError(f"{name} is required (at least {lo} characters).")
    if len(v) > hi:
        raise HealthError(f"{name} is too long (limit {hi} characters).")
    return v


def dec(v, name, positive=False, lo=None) -> Decimal:
    if v is None or isinstance(v, bool) or (isinstance(v, str) and not v.strip()):
        raise HealthError(f"{name} is required and must be a number.")
    try:
        x = Decimal(str(v).strip())
    except (InvalidOperation, ValueError):
        raise HealthError(f"{name} must be a number.")
    if not x.is_finite() or abs(x) > Decimal("999999999999.99"):
        raise HealthError(f"{name} must be a reasonable number.")
    if positive and x <= 0:
        raise HealthError(f"{name} must be more than zero.")
    if lo is not None and x < Decimal(str(lo)):
        raise HealthError(f"{name} must be at least {lo}.")
    return x


def money(v, name, positive=True) -> Decimal: return q2(dec(v, name, positive=positive))
def qty(v, name, positive=True) -> Decimal: return q3(dec(v, name, positive=positive))


def day(v, name) -> date:
    try:
        return date.fromisoformat(str(v).strip())
    except (ValueError, TypeError):
        raise HealthError(f"{name} must be a real date written YYYY-MM-DD.")


def month(v, name) -> str:
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", str(v or "").strip()):
        raise HealthError(f"{name} must be a month written YYYY-MM.")
    return str(v).strip()


def enum(v, allowed, name) -> str:
    v = txt(v, name, 1, 40).upper()
    if v not in allowed:
        raise HealthError(f"{name} must be one of {', '.join(allowed)}.")
    return v


def whole(v, name, lo, hi) -> int:
    if isinstance(v, bool) or not str(v).strip().lstrip("-").isdigit():
        raise HealthError(f"{name} must be a whole number from {lo} to {hi}.")
    n = int(str(v).strip())
    if not lo <= n <= hi:
        raise HealthError(f"{name} must be a whole number from {lo} to {hi}.")
    return n


class Base:
    def __init__(self, store, vault, accounting=None, log=lambda *a, **k: None, now=_utc, can=lambda org, actor, perm: True):
        self.store, self.vault, self.accounting, self.log, self.now, self.can = store, vault, accounting, log, now, can

    # ---- storage
    def today(self) -> date: return self.now().date()
    def _put(self, kind, org, d): self.store.put(kind, f"{org}:{d['id']}", d, org_id=org)
    def _all(self, kind, org) -> list: return [d for _, d in self.store.list(kind, org_id=org, prefix=f"{org}:") if d.get("org") == org]
    def _of(self, kind, org, fid) -> list: return [d for d in self._all(kind, org) if d.get("facility_id") == fid]

    def _raw(self, kind, org, rid, label, for_update=False) -> dict:
        r = self.store.get(kind, f"{org}:{rid}", for_update=for_update)
        if r is None or r["org"] != org:
            raise HealthNotFoundError(f"{label} not found.")
        return r

    def _settings(self, org, for_update=False) -> dict:
        s = self.store.get("hc_setting", f"{org}:settings", for_update=for_update)
        return s if s else {"id": "settings", "org": org, "counters": {}, "access": {}}

    def _ref(self, org, prefix, scope="") -> str:
        s = self._settings(org, for_update=True)
        k = f"{scope}:{prefix}"
        n = s["counters"].get(k, 0) + 1
        s["counters"][k] = n
        self._put("hc_setting", org, s)
        return f"{prefix}-{n:03d}"

    def _hist(self, r, actor, event, note=""):
        r.setdefault("history", []).append({"at": self.now().isoformat(), "by": actor, "event": event, "note": note})

    # ---- who may do what
    def _need(self, org, actor, perm, what="do this"):
        if not self.can(org, actor, perm):
            raise HealthForbiddenError(f"You do not have permission to {what}.")

    def _unrestricted(self, org, actor) -> bool: return bool(self.can(org, actor, P_ADMIN))

    def _two(self, actor, other, what):
        if actor == other:
            raise HealthForbiddenError(f"You {what}, so you cannot decide it. A different person must.")

    def _fac(self, org, fid, actor, active=False) -> dict:
        """The facility, only if this person may see it. A facility they cannot see is reported as not found, so an identifier cannot be probed."""
        f = self.store.get("hc_facility", f"{org}:{fid}")
        if f is None or f["org"] != org:
            raise HealthNotFoundError("Facility not found.")
        if not self._unrestricted(org, actor) and fid not in self._settings(org)["access"].get(actor, []):
            raise HealthNotFoundError("Facility not found.")
        if active and f["status"] != "ACTIVE":
            raise HealthStateError("This facility is inactive. Its history is kept, but it cannot take new records.")
        return f

    def _rec(self, kind, org, rid, label, actor, for_update=False) -> dict:
        """A record, only if its facility is visible to this person."""
        r = self._raw(kind, org, rid, label, for_update)
        self._fac(org, r["facility_id"], actor)
        return r

    def _writable(self, org, r, actor):
        self._fac(org, r["facility_id"], actor, active=True)

    def _dept(self, org, fid, did, name="Department") -> dict:
        d = self.store.get("hc_dept", f"{org}:{did}") if did else None
        if d is None or d["org"] != org or d["facility_id"] != fid:
            raise HealthError(f"{name} not found in this facility.")
        if not d["active"]:
            raise HealthError(f"{d['name']} is not active.")
        return d

    def _evidence(self, org, ids) -> List[dict]:
        out = []
        for i in dict.fromkeys(str(i) for i in (ids or [])):
            try:
                e = self.vault.get_evidence(org, i)
            except Exception:
                raise HealthError("Linked evidence not found in this organisation's Evidence Vault.")
            out.append({"evidence_id": e.id, "filename": e.original_filename, "file_hash": e.file_hash})
        return out

    @staticmethod
    def _new(org, fid, **kw) -> dict:
        return {"id": uuid.uuid4().hex, "org": org, "facility_id": fid, **kw}
