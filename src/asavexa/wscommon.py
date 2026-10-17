"""Shared building blocks for the records-and-arithmetic workspaces (Stage 33 onwards): input cleaning, exact decimal amounts, per-organisation record storage, reference numbers, history and the different-person rule.

Every workspace service passes its own error classes so a failure keeps its own name and HTTP status."""
import re
import uuid  # noqa: F401  (workspaces build record ids with it)
from datetime import date, datetime, timezone
from decimal import Decimal
from fractions import Fraction


def utc(): return datetime.now(timezone.utc)


def txt(err, v, name, lo=1, hi=1000, required=True) -> str:
    v = (v if isinstance(v, str) else ("" if v is None else str(v)))
    v = " ".join("".join(c if c >= " " and c != "\x7f" else " " for c in v).split())
    if required and len(v) < lo: raise err(f"{name} is required (at least {lo} characters).")
    if v and len(v) < lo: raise err(f"{name} needs at least {lo} characters.")
    if len(v) > hi: raise err(f"{name} is too long (limit {hi} characters).")
    return v


def dt(err, v, name) -> date:
    try:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", str(v).strip()): raise ValueError
        return date.fromisoformat(str(v).strip())
    except (ValueError, TypeError):
        raise err(f"{name} must be a real date written YYYY-MM-DD.")


def amount(err, v, name, zero_ok=False, dp=2, digits=13, neg=False) -> Decimal:
    """Text or a whole number: ASCII digits, at most dp decimals, never a float, commas only as thousands separators."""
    if isinstance(v, bool) or isinstance(v, float) or v is None: raise err(f"{name} must be a number such as 1500.00.")
    t = str(v).strip(); sign = ""
    if neg and t.startswith("-"): sign, t = "-", t[1:]
    if "," in t and not re.fullmatch(r"[0-9]{1,3}(,[0-9]{3})+(\.[0-9]+)?", t): raise err(f"{name} must be a number such as 1500.00 (commas only between groups of three digits).")
    t = t.replace(",", "")
    if not re.fullmatch(r"[0-9]{1,%d}(\.[0-9]{1,%d})?" % (digits, dp), t):
        raise err(f"{name} must be a number such as 1500.00 (at most {dp} decimals)." if dp else f"{name} must be a whole number.")
    d = Decimal(sign + t)
    if d == 0 and not zero_ok: raise err(f"{name} must be more than zero.")
    return d.quantize(Decimal(1).scaleb(-dp))


def whole(err, v, name, lo, hi) -> int:
    if isinstance(v, bool) or isinstance(v, float) or v is None or not re.fullmatch(r"[0-9]{1,9}", str(v).strip()): raise err(f"{name} must be a whole number from {lo} to {hi}.")
    n = int(str(v).strip())
    if not lo <= n <= hi: raise err(f"{name} must be a whole number from {lo} to {hi}.")
    return n


def code(err, v, name, allowed) -> str:
    v = v.strip().upper() if isinstance(v, str) else ""
    if v not in allowed: raise err(f"{name} must be one of: {', '.join(allowed)}.")
    return v


def currency(err, v) -> str:
    c = txt(err, v, "The currency", 3, 3).upper()
    if not re.fullmatch(r"[A-Z]{3}", c): raise err("The currency must be a three-letter code such as NGN.")
    return c


def fr(d) -> Fraction:
    """An exact fraction from a Decimal, an int or a decimal text (never from a float)."""
    return Fraction(Decimal(str(d)))


def round2(f: Fraction) -> Decimal:
    """Two decimals, half away from zero, exactly."""
    n, d = f.numerator * 100, f.denominator; q = (abs(n) * 2 + d) // (2 * d)
    return Decimal(q if n >= 0 else -q).scaleb(-2).quantize(Decimal("0.01"))


def refnum(r) -> int:
    try: return int(str(r["ref"]).rsplit("-", 1)[1])
    except (KeyError, IndexError, ValueError): return 0


class WsMixin:
    """Storage, numbering, history and the different-person rule. A workspace sets SETTING_KIND, DEFAULTS and the four error classes ERR, NF, ST, FB."""
    SETTING_KIND = ""
    DEFAULTS: dict = {}
    ERR = NF = ST = FB = None

    def today(self) -> date: return self.now().date()
    def _put(self, kind, org, d): self.store.put(kind, f"{org}:{d['id']}", d, org_id=org)
    def _all(self, kind, org) -> list: return [d for _, d in self.store.list(kind, org_id=org, prefix=f"{org}:") if d.get("org") == org]

    def _get(self, kind, org, rid, label, for_update=False) -> dict:
        r = self.store.get(kind, f"{org}:{rid}", for_update=for_update)
        if r is None or r.get("org") != org: raise self.NF(f"{label} not found.")
        return r

    def _settings(self, org, for_update=False) -> dict:
        s = self.store.get(self.SETTING_KIND, f"{org}:settings", for_update=for_update)
        if s and s.get("org") == org: return s
        return {"id": "settings", "org": org, **self.DEFAULTS, "counters": {}, "updated_by": None, "updated_at": None}

    def _ref(self, org, prefix) -> str:
        s = self._settings(org, for_update=True); n = s["counters"].get(prefix, 0) + 1; s["counters"][prefix] = n
        self._put(self.SETTING_KIND, org, s)
        return f"{prefix}-{n:03d}"

    def _hist(self, r, actor, event, note=""):
        r.setdefault("history", []).append({"at": self.now().isoformat(), "by": actor, "event": event, "note": note})

    def _two(self, actor, other, what):
        if actor == other: raise self.FB(f"You {what}, so you cannot do this. A different person must.")

    def _row(self, r, no, label, key="lines"):
        """A numbered row inside a record (a line, an entry, a claim ...)."""
        if isinstance(no, bool) or not re.fullmatch(r"[0-9]{1,6}", str(no).strip()): raise self.ERR(f"The {label} number must be a whole number.")
        n = int(str(no).strip()); x = next((x for x in r[key] if x["no"] == n), None)
        if x is None: raise self.NF(f"{label.capitalize()} not found.")
        return x, n
