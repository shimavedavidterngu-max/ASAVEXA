"""Business Development service.

Records (shared document store, per organisation): bd_account, bd_opportunity (with activities, stage history and proposals), bd_target, bd_report, bd_setting.

Principles enforced here: a proposal whose discount is above the policy limit needs a second person's approval before it can be sent; a win is requested by
one person and confirmed by another before it counts toward targets or win rate; a lost deal needs a reason; closed deals are frozen; money is exact Decimal
and never converted between currencies; every step is audited. Probabilities are the organisation's own policy settings, so the weighted forecast is an
estimate of that policy, not a prediction."""
import csv
import hashlib
import io
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Callable, List, Optional

from .errors import BizDevError, BizDevForbiddenError, BizDevNotFoundError, BizDevStateError

ZERO = Decimal("0.00")
OPEN_STAGES = ["LEAD", "QUALIFIED", "PROPOSAL", "NEGOTIATION"]
ACTIVE_STAGES = OPEN_STAGES + ["WIN_PENDING"]
STAGES = ACTIVE_STAGES + ["WON", "LOST"]
KINDS = ["PROSPECT", "CLIENT", "PARTNER"]
ACTIVITY_TYPES = ["CALL", "MEETING", "EMAIL", "NOTE"]
DEFAULT_PROBABILITIES = {"LEAD": 10, "QUALIFIED": 25, "PROPOSAL": 50, "NEGOTIATION": 75, "WIN_PENDING": 90}
DEFAULT_DISCOUNT_LIMIT = "10.00"
DEFAULT_STALE_DAYS = 30
CONFIDENTIAL = "CONFIDENTIAL - ASAVEXA business development pipeline report. For the organisation named and people it has authorised."
LIMITATIONS = [
    "Probabilities are your own policy settings. The weighted forecast is value multiplied by those settings. It is an estimate under your policy, not a prediction or a guarantee.",
    "Amounts in different currencies are never converted or added together. Each currency is reported separately.",
    "A win counts only after a second person confirms it. Confirmation records review of the accepted proposal; it does not check that the client signed or paid.",
    "This workspace records commercial activity. It does not post to the ledger, issue invoices or recognise revenue.",
    "Contact details are personal data. Enter only what your organisation is allowed to hold.",
]


def _utc(): return datetime.now(timezone.utc)
def _sha(o) -> str: return hashlib.sha256(json.dumps(o, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
def q2(x) -> Decimal: return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
def s2(x) -> str: return str(q2(x))


def _txt(v, name, lo=1, hi=1000, required=True) -> str:
    v = (v if isinstance(v, str) else ("" if v is None else str(v))).strip()
    if required and len(v) < lo:
        raise BizDevError(f"{name} is required (at least {lo} characters).")
    if len(v) > hi:
        raise BizDevError(f"{name} is too long (limit {hi} characters).")
    return v


def _dec(v, name, lo=None, positive=False) -> Decimal:
    if v is None or isinstance(v, bool) or (isinstance(v, str) and not v.strip()):
        raise BizDevError(f"{name} is required and must be a number.")
    try:
        x = Decimal(str(v).strip())
    except (InvalidOperation, ValueError):
        raise BizDevError(f"{name} must be a number.")
    if not x.is_finite():
        raise BizDevError(f"{name} must be a number.")
    if abs(x) > Decimal("999999999999999.99"):
        raise BizDevError(f"{name} is too large.")
    x = q2(x)
    if positive and x <= 0:
        raise BizDevError(f"{name} must be more than zero.")
    if lo is not None and x < Decimal(str(lo)):
        raise BizDevError(f"{name} must be at least {lo}.")
    return x


def _date(v, name) -> date:
    try:
        return date.fromisoformat(str(v).strip())
    except (ValueError, TypeError):
        raise BizDevError(f"{name} must be a real date written YYYY-MM-DD.")


def _cur(v) -> str:
    v = _txt(v, "Currency", 3, 3).upper()
    if not v.isalpha() or not v.isascii():
        raise BizDevError("Currency must be a 3-letter code such as NGN or USD.")
    return v


class BizDevService:
    def __init__(self, store, vault, log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = _utc):
        self.store, self.vault, self.log, self.now = store, vault, log, now

    # ------------------------------------------------------------------ helpers
    def today(self) -> date: return self.now().date()
    def _put(self, kind, org, d): self.store.put(kind, f"{org}:{d['id']}", d, org_id=org)
    def _all(self, kind, org) -> list: return [d for _, d in self.store.list(kind, org_id=org, prefix=f"{org}:") if d.get("org") == org]

    def _get(self, kind, org, rid, label, for_update=False) -> dict:
        r = self.store.get(kind, f"{org}:{rid}", for_update=for_update)
        if r is None or r["org"] != org:
            raise BizDevNotFoundError(f"{label} not found.")
        return r

    def _settings(self, org, for_update=False) -> dict:
        s = self.store.get("bd_setting", f"{org}:settings", for_update=for_update)
        return s if s else {"id": "settings", "org": org, "probabilities": dict(DEFAULT_PROBABILITIES), "discount_limit_pct": DEFAULT_DISCOUNT_LIMIT, "stale_days": DEFAULT_STALE_DAYS,
                            "counters": {}, "updated_by": None, "updated_at": None}

    def _ref(self, org, prefix) -> str:
        s = self._settings(org, for_update=True)
        n = s["counters"].get(prefix, 0) + 1
        s["counters"][prefix] = n
        self._put("bd_setting", org, s)
        return f"{prefix}-{n:03d}"

    def _hist(self, r, actor, event, note=""):
        r.setdefault("history", []).append({"at": self.now().isoformat(), "by": actor, "event": event, "note": note})

    def _two(self, actor, other, what):
        if actor == other:
            raise BizDevForbiddenError(f"You {what}, so you cannot decide it. A different person must.")

    def _evidence(self, org, ids) -> List[dict]:
        out = []
        for i in dict.fromkeys(str(i) for i in (ids or [])):
            try:
                e = self.vault.get_evidence(org, i)
            except Exception:
                raise BizDevError("Linked evidence not found in this organisation's Evidence Vault.")
            out.append({"evidence_id": e.id, "filename": e.original_filename, "file_hash": e.file_hash})
        return out

    # ------------------------------------------------------------------ policy
    def get_policy(self, org) -> dict:
        s = self._settings(org)
        return {"probabilities": s["probabilities"], "discount_limit_pct": s["discount_limit_pct"], "stale_days": s["stale_days"], "updated_by": s["updated_by"], "updated_at": s["updated_at"],
                "meaning": f"A proposal with a discount above {s['discount_limit_pct']}% needs a second person's approval. A deal untouched for more than {s['stale_days']} days is flagged stale. "
                           "The probabilities are your own policy settings, not predictions."}

    def set_policy(self, org, d, actor) -> dict:
        s = self._settings(org, for_update=True)
        probs = dict(s["probabilities"])
        if d.get("probabilities") is not None:
            if not isinstance(d["probabilities"], dict): raise BizDevError("Probabilities must be a list of stage percentages.")
            for k, v in d["probabilities"].items():
                if k not in DEFAULT_PROBABILITIES: raise BizDevError(f"{k} is not a stage that has a probability.")
                if isinstance(v, bool) or not isinstance(v, (int, str)) or not str(v).strip().lstrip("-").isdigit(): raise BizDevError(f"The {k} probability must be a whole number from 0 to 100.")
                n = int(v)
                if not 0 <= n <= 100: raise BizDevError(f"The {k} probability must be a whole number from 0 to 100.")
                probs[k] = n
            vals = [probs[k] for k in ACTIVE_STAGES]
            if vals != sorted(vals): raise BizDevError("Probabilities must not go down as a deal moves forward (Lead, Qualified, Proposal, Negotiation, Win pending).")
        limit = s["discount_limit_pct"]
        if d.get("discount_limit_pct") is not None:
            x = _dec(d["discount_limit_pct"], "Discount limit", lo=0)
            if x > 100: raise BizDevError("The discount limit cannot be more than 100.")
            limit = s2(x)
        stale = s["stale_days"]
        if d.get("stale_days") is not None:
            v = d["stale_days"]
            if isinstance(v, bool) or not str(v).strip().isdigit() or not 1 <= int(v) <= 365: raise BizDevError("Stale days must be a whole number from 1 to 365.")
            stale = int(v)
        s.update(probabilities=probs, discount_limit_pct=limit, stale_days=stale, updated_by=actor, updated_at=self.now().isoformat())
        self._put("bd_setting", org, s); self.log("BD_POLICY_SET", actor, "settings", org, f"discount limit {limit}%, stale {stale} days")
        return self.get_policy(org)

    # ------------------------------------------------------------------ accounts
    @staticmethod
    def _contacts(v) -> List[dict]:
        if v is None: return []
        if not isinstance(v, list) or len(v) > 20: raise BizDevError("Contacts must be a list of at most 20 people.")
        out = []
        for c in v:
            if not isinstance(c, dict): raise BizDevError("Each contact needs a name.")
            email = _txt(c.get("email"), "Contact email", 0, 200, required=False)
            if email and ("@" not in email or " " in email or email.startswith("@") or email.endswith("@")): raise BizDevError("A contact email must look like name@example.com.")
            out.append({"name": _txt(c.get("name"), "Contact name", 2, 200), "role": _txt(c.get("role"), "Contact role", 0, 200, required=False), "email": email, "phone": _txt(c.get("phone"), "Contact phone", 0, 50, required=False)})
        return out

    def _acct_fields(self, d) -> dict:
        kind = _txt(d.get("kind") or "PROSPECT", "Kind", 1, 20).upper()
        if kind not in KINDS: raise BizDevError(f"Kind must be one of {', '.join(KINDS)}.")
        return {"name": _txt(d.get("name"), "Name", 2, 200), "kind": kind, "sector": _txt(d.get("sector"), "Sector", 0, 100, required=False), "country": _txt(d.get("country"), "Country", 0, 100, required=False),
                "notes": _txt(d.get("notes"), "Notes", 0, 2000, required=False), "contacts": self._contacts(d.get("contacts"))}

    def _dup(self, org, name, skip=None):
        n = name.strip().lower()
        for a in self._all("bd_account", org):
            if a["id"] != skip and a["status"] == "ACTIVE" and a["name"].strip().lower() == n:
                raise BizDevError(f"An active account called {a['name']} already exists ({a['ref']}).")

    def create_account(self, org, d, actor) -> dict:
        f = self._acct_fields(d); self._dup(org, f["name"])
        a = {"id": uuid.uuid4().hex, "org": org, "ref": self._ref(org, "A"), **f, "status": "ACTIVE", "created_by": actor, "created_at": self.now().isoformat(), "history": []}
        self._hist(a, actor, "CREATED"); self._put("bd_account", org, a); self.log("BD_ACCOUNT_CREATED", actor, a["id"], org, f"{a['ref']} {a['name']}")
        return a

    def update_account(self, org, aid, d, actor) -> dict:
        a = self._get("bd_account", org, aid, "Account", for_update=True)
        if a["status"] != "ACTIVE": raise BizDevStateError("An archived account cannot be changed.")
        f = self._acct_fields({**a, **{k: v for k, v in d.items() if v is not None}}); self._dup(org, f["name"], skip=aid)
        a.update(f); self._hist(a, actor, "UPDATED"); self._put("bd_account", org, a); self.log("BD_ACCOUNT_UPDATED", actor, aid, org, a["ref"])
        return a

    def archive_account(self, org, aid, note, actor) -> dict:
        a = self._get("bd_account", org, aid, "Account", for_update=True)
        if a["status"] != "ACTIVE": raise BizDevStateError("This account is already archived.")
        open_ = [o["ref"] for o in self._all("bd_opportunity", org) if o["account_id"] == aid and o["stage"] in ACTIVE_STAGES]
        if open_: raise BizDevStateError(f"This account still has open opportunities ({', '.join(sorted(open_))}). Close them first.")
        a.update(status="ARCHIVED", archive_note=_txt(note, "Reason", 3, 500)); self._hist(a, actor, "ARCHIVED", a["archive_note"]); self._put("bd_account", org, a); self.log("BD_ACCOUNT_ARCHIVED", actor, aid, org, a["ref"])
        return a

    def list_accounts(self, org) -> List[dict]:
        opps = self._all("bd_opportunity", org)
        out = []
        for a in sorted(self._all("bd_account", org), key=lambda a: a["ref"]):
            mine = [o for o in opps if o["account_id"] == a["id"]]
            out.append({**a, "open_opportunities": sum(1 for o in mine if o["stage"] in ACTIVE_STAGES), "won_opportunities": sum(1 for o in mine if o["stage"] == "WON")})
        return out

    def get_account(self, org, aid) -> dict:
        a = self._get("bd_account", org, aid, "Account")
        return {**a, "opportunities": [self._oview(org, o, full=False) for o in sorted(self._all("bd_opportunity", org), key=lambda o: o["ref"]) if o["account_id"] == aid]}

    # ------------------------------------------------------------------ opportunities
    def _prob(self, st, stage) -> Optional[int]:
        if stage == "WON": return 100
        if stage == "LOST": return 0
        return st["probabilities"].get(stage)

    def _last_touch(self, o) -> date:
        days = [date.fromisoformat(o["created_at"][:10])] + [date.fromisoformat(a["date"]) for a in o["activities"]] + [date.fromisoformat(h["at"][:10]) for h in o["stage_history"]]
        return max(days)

    def _oview(self, org, o, full=True, st=None, acct=None) -> dict:
        st = st or self._settings(org)
        v = {k: x for k, x in o.items() if full or k not in ("activities", "proposals", "history", "stage_history")}
        p = self._prob(st, o["stage"]); v["probability"] = p
        v["weighted"] = s2(Decimal(o["value"]) * p / 100) if p is not None else "0.00"
        if acct is None:
            a = self.store.get("bd_account", f"{org}:{o['account_id']}")
            acct = a["name"] if a else "(unknown)"
        v["account_name"] = acct
        active = o["stage"] in ACTIVE_STAGES
        flags = []
        if active and date.fromisoformat(o["expected_close"]) < self.today(): flags.append("OVERDUE")
        if active and (self.today() - self._last_touch(o)).days > st["stale_days"]: flags.append("STALE")
        v["flags"] = flags
        v["days_in_stage"] = (self.today() - date.fromisoformat(o["stage_history"][-1]["at"][:10])).days
        if not full: v["proposal_count"] = len(o["proposals"]); v["activity_count"] = len(o["activities"])
        return v

    def create_opportunity(self, org, d, actor) -> dict:
        a = self._get("bd_account", org, str(d.get("account_id") or ""), "Account")
        if a["status"] != "ACTIVE": raise BizDevStateError("An opportunity cannot be started on an archived account.")
        stage = _txt(d.get("stage") or "LEAD", "Stage", 1, 20).upper()
        if stage not in ("LEAD", "QUALIFIED"): raise BizDevError("A new opportunity starts as a Lead or Qualified.")
        close = _date(d.get("expected_close"), "Expected close date")
        if close < self.today(): raise BizDevError("The expected close date cannot be in the past.")
        now = self.now().isoformat()
        o = {"id": uuid.uuid4().hex, "org": org, "ref": self._ref(org, "O"), "account_id": a["id"], "title": _txt(d.get("title"), "Title", 3, 200), "description": _txt(d.get("description"), "Description", 0, 2000, required=False),
             "source": _txt(d.get("source"), "Source", 0, 200, required=False), "currency": _cur(d.get("currency")), "value": s2(_dec(d.get("value"), "Estimated value", positive=True)), "expected_close": close.isoformat(),
             "stage": stage, "owner": actor, "created_by": actor, "created_at": now, "activities": [], "proposals": [], "stage_history": [{"at": now, "by": actor, "from": None, "to": stage, "note": "created"}],
             "lost_reason": "", "won_date": None, "closed_at": None, "win_requested_by": None, "win_note": "", "history": []}
        self._hist(o, actor, "CREATED"); self._put("bd_opportunity", org, o); self.log("BD_OPPORTUNITY_CREATED", actor, o["id"], org, f"{o['ref']} {o['title']}")
        return self._oview(org, o, acct=a["name"])

    def _opp(self, org, oid, for_update=True) -> dict: return self._get("bd_opportunity", org, oid, "Opportunity", for_update=for_update)

    def _need_active(self, o):
        if o["stage"] not in ACTIVE_STAGES: raise BizDevStateError(f"This opportunity is {o['stage'].lower()} and can no longer be changed.")

    def _need_open(self, o):
        if o["stage"] not in OPEN_STAGES:
            raise BizDevStateError("This opportunity is waiting for a win decision." if o["stage"] == "WIN_PENDING" else f"This opportunity is {o['stage'].lower()} and can no longer be changed.")

    def update_opportunity(self, org, oid, d, actor) -> dict:
        o = self._opp(org, oid); self._need_open(o)
        if d.get("title") is not None: o["title"] = _txt(d["title"], "Title", 3, 200)
        if d.get("description") is not None: o["description"] = _txt(d["description"], "Description", 0, 2000, required=False)
        if d.get("source") is not None: o["source"] = _txt(d["source"], "Source", 0, 200, required=False)
        if d.get("value") is not None: o["value"] = s2(_dec(d["value"], "Estimated value", positive=True))
        if d.get("expected_close") is not None:
            close = _date(d["expected_close"], "Expected close date")
            if close < self.today(): raise BizDevError("The expected close date cannot be in the past.")
            o["expected_close"] = close.isoformat()
        self._hist(o, actor, "UPDATED"); self._put("bd_opportunity", org, o); self.log("BD_OPPORTUNITY_UPDATED", actor, oid, org, o["ref"])
        return self._oview(org, o)

    def add_activity(self, org, oid, d, actor) -> dict:
        o = self._opp(org, oid); self._need_active(o)
        t = _txt(d.get("type"), "Activity type", 1, 20).upper()
        if t not in ACTIVITY_TYPES: raise BizDevError(f"Activity type must be one of {', '.join(ACTIVITY_TYPES)}.")
        when = _date(d.get("date") or self.today().isoformat(), "Activity date")
        if when > self.today(): raise BizDevError("An activity cannot be dated in the future.")
        o["activities"].append({"id": uuid.uuid4().hex, "type": t, "date": when.isoformat(), "summary": _txt(d.get("summary"), "Summary", 3, 1000), "by": actor})
        self._hist(o, actor, "ACTIVITY", t); self._put("bd_opportunity", org, o); self.log("BD_ACTIVITY_ADDED", actor, oid, org, f"{o['ref']} {t}")
        return self._oview(org, o)

    def _move(self, o, actor, to, note):
        o["stage_history"].append({"at": self.now().isoformat(), "by": actor, "from": o["stage"], "to": to, "note": note}); o["stage"] = to

    def move_stage(self, org, oid, stage, note, actor) -> dict:
        o = self._opp(org, oid); self._need_open(o)
        to = _txt(stage, "Stage", 1, 20).upper()
        if to not in OPEN_STAGES: raise BizDevError("A deal moves between Lead, Qualified, Proposal and Negotiation. Use the win and lost steps to close it.")
        if to == o["stage"]: raise BizDevError("The deal is already at that stage.")
        back = OPEN_STAGES.index(to) < OPEN_STAGES.index(o["stage"])
        note = _txt(note, "A reason for moving backwards" if back else "Note", 3 if back else 0, 500, required=back)
        if to == "NEGOTIATION" and not any(p["status"] in ("SENT", "ACCEPTED") for p in o["proposals"]):
            raise BizDevStateError("A deal can go to Negotiation only after a proposal has been sent to the client.")
        self._move(o, actor, to, note); self._hist(o, actor, "STAGE", f"{to}"); self._put("bd_opportunity", org, o); self.log("BD_STAGE_MOVED", actor, oid, org, f"{o['ref']} -> {to}")
        return self._oview(org, o)

    def mark_lost(self, org, oid, reason, actor) -> dict:
        o = self._opp(org, oid); self._need_active(o)
        reason = _txt(reason, "The reason it was lost", 10, 1000)
        for p in o["proposals"]:
            if p["status"] in ("SENT", "PENDING_APPROVAL", "APPROVED", "ACCEPTED"): p["status"] = "LAPSED"
        o.update(lost_reason=reason, closed_at=self.now().isoformat()); self._move(o, actor, "LOST", reason)
        self._hist(o, actor, "LOST", reason); self._put("bd_opportunity", org, o); self.log("BD_OPPORTUNITY_LOST", actor, oid, org, o["ref"])
        return self._oview(org, o)

    def request_win(self, org, oid, note, actor) -> dict:
        o = self._opp(org, oid); self._need_open(o)
        acc = next((p for p in o["proposals"] if p["status"] == "ACCEPTED"), None)
        if not acc: raise BizDevStateError("Record that the client accepted a proposal before asking for the win to be confirmed.")
        o.update(win_requested_by=actor, win_note=_txt(note, "Note", 0, 500, required=False)); self._move(o, actor, "WIN_PENDING", o["win_note"])
        self._hist(o, actor, "WIN_REQUESTED", f"proposal v{acc['version']} {acc['total']}"); self._put("bd_opportunity", org, o); self.log("BD_WIN_REQUESTED", actor, oid, org, o["ref"])
        return self._oview(org, o)

    def approve_win(self, org, oid, actor, note="") -> dict:
        o = self._opp(org, oid)
        if o["stage"] != "WIN_PENDING": raise BizDevStateError("This opportunity has no win waiting for confirmation.")
        self._two(actor, o["win_requested_by"], "asked for this win to be confirmed")
        acc = next((p for p in o["proposals"] if p["status"] == "ACCEPTED"), None)
        if not acc: raise BizDevStateError("There is no accepted proposal to confirm.")
        o.update(value=acc["total"], won_date=self.today().isoformat(), closed_at=self.now().isoformat(), win_decided_by=actor, win_decision_note=_txt(note, "Note", 0, 500, required=False))
        self._move(o, actor, "WON", o["win_decision_note"]); self._hist(o, actor, "WON", f"{acc['total']} {o['currency']}"); self._put("bd_opportunity", org, o); self.log("BD_WIN_CONFIRMED", actor, oid, org, f"{o['ref']} {acc['total']} {o['currency']}")
        return self._oview(org, o)

    def reject_win(self, org, oid, actor, note) -> dict:
        o = self._opp(org, oid)
        if o["stage"] != "WIN_PENDING": raise BizDevStateError("This opportunity has no win waiting for confirmation.")
        self._two(actor, o["win_requested_by"], "asked for this win to be confirmed")
        note = _txt(note, "A reason", 3, 500)
        o.update(win_requested_by=None, win_note="", win_decision_note=note); self._move(o, actor, "NEGOTIATION", note)
        self._hist(o, actor, "WIN_REJECTED", note); self._put("bd_opportunity", org, o); self.log("BD_WIN_REJECTED", actor, oid, org, o["ref"])
        return self._oview(org, o)

    def list_opportunities(self, org, stage=None, account_id=None) -> List[dict]:
        if stage and stage.upper() not in STAGES: raise BizDevError("Unknown stage.")
        st = self._settings(org); names = {a["id"]: a["name"] for a in self._all("bd_account", org)}
        rows = [o for o in self._all("bd_opportunity", org) if (not stage or o["stage"] == stage.upper()) and (not account_id or o["account_id"] == account_id)]
        return [self._oview(org, o, full=False, st=st, acct=names.get(o["account_id"], "(unknown)")) for o in sorted(rows, key=lambda o: o["ref"])]

    def get_opportunity(self, org, oid) -> dict: return self._oview(org, self._opp(org, oid, for_update=False))

    # ------------------------------------------------------------------ proposals
    def _items(self, v):
        if not isinstance(v, list) or not 1 <= len(v) <= 50: raise BizDevError("A proposal needs between 1 and 50 line items.")
        items, sub = [], ZERO
        for i, it in enumerate(v, 1):
            if not isinstance(it, dict): raise BizDevError(f"Line {i} is not valid.")
            qty, price = _dec(it.get("quantity"), f"Line {i} quantity", positive=True), _dec(it.get("unit_price"), f"Line {i} unit price", positive=True)
            total = q2(qty * price); sub += total
            items.append({"description": _txt(it.get("description"), f"Line {i} description", 2, 300), "quantity": s2(qty), "unit_price": s2(price), "total": s2(total)})
        return items, sub

    def _prop_fields(self, org, o, d) -> dict:
        items, sub = self._items(d.get("items"))
        pct = _dec(d.get("discount_pct") if d.get("discount_pct") not in (None, "") else "0", "Discount", lo=0)
        if pct >= 100: raise BizDevError("The discount must be less than 100%.")
        disc = q2(sub * pct / 100); total = sub - disc
        if total <= 0: raise BizDevError("The proposal total must be more than zero.")
        valid = _date(d.get("valid_until"), "Valid until")
        if valid < self.today(): raise BizDevError("The proposal cannot already be expired.")
        return {"items": items, "subtotal": s2(sub), "discount_pct": s2(pct), "discount_amount": s2(disc), "total": s2(total), "valid_until": valid.isoformat(), "terms": _txt(d.get("terms"), "Terms", 0, 2000, required=False),
                "evidence": self._evidence(org, d.get("evidence_ids"))}

    def _prop(self, o, pid) -> dict:
        p = next((p for p in o["proposals"] if p["id"] == pid), None)
        if not p: raise BizDevNotFoundError("Proposal not found.")
        return p

    def create_proposal(self, org, oid, d, actor) -> dict:
        o = self._opp(org, oid); self._need_open(o)
        p = {"id": uuid.uuid4().hex, "version": len(o["proposals"]) + 1, "status": "DRAFT", "currency": o["currency"], **self._prop_fields(org, o, d), "created_by": actor, "created_at": self.now().isoformat(),
             "submitted_by": None, "decided_by": None, "decision_note": "", "limit_at_submission": None, "history": []}
        o["proposals"].append(p); self._hist(p, actor, "CREATED"); self._hist(o, actor, "PROPOSAL_CREATED", f"v{p['version']}"); self._put("bd_opportunity", org, o); self.log("BD_PROPOSAL_CREATED", actor, oid, org, f"{o['ref']} v{p['version']}")
        return self._oview(org, o)

    def update_proposal(self, org, oid, pid, d, actor) -> dict:
        o = self._opp(org, oid); self._need_open(o); p = self._prop(o, pid)
        if p["status"] not in ("DRAFT", "REJECTED"): raise BizDevStateError(f"A {p['status'].lower().replace('_', ' ')} proposal cannot be edited. Create a new version instead.")
        p.update(self._prop_fields(org, o, d), status="DRAFT", submitted_by=None, decided_by=None, decision_note=""); self._hist(p, actor, "EDITED"); self._put("bd_opportunity", org, o); self.log("BD_PROPOSAL_EDITED", actor, oid, org, f"{o['ref']} v{p['version']}")
        return self._oview(org, o)

    def submit_proposal(self, org, oid, pid, actor) -> dict:
        o = self._opp(org, oid); self._need_open(o); p = self._prop(o, pid)
        if p["status"] != "DRAFT": raise BizDevStateError("Only a draft proposal can be submitted.")
        limit = Decimal(self._settings(org)["discount_limit_pct"]); p.update(limit_at_submission=s2(limit), submitted_by=actor)
        if Decimal(p["discount_pct"]) > limit:
            p["status"] = "PENDING_APPROVAL"; self._hist(p, actor, "SUBMITTED", f"discount {p['discount_pct']}% is above the {s2(limit)}% limit")
        else:
            p["status"] = "APPROVED"; p["decision_note"] = f"Discount {p['discount_pct']}% is within the {s2(limit)}% limit."; self._hist(p, actor, "APPROVED", "within the discount limit")
        self._put("bd_opportunity", org, o); self.log("BD_PROPOSAL_SUBMITTED", actor, oid, org, f"{o['ref']} v{p['version']} {p['status']}")
        return self._oview(org, o)

    def _decide_proposal(self, org, oid, pid, actor, ok, note):
        o = self._opp(org, oid); self._need_open(o); p = self._prop(o, pid)
        if p["status"] != "PENDING_APPROVAL": raise BizDevStateError("Only a proposal waiting for approval can be approved or sent back.")
        self._two(actor, p["submitted_by"], "submitted this proposal")
        note = _txt(note, "A reason", 0 if ok else 3, 1000, required=not ok)
        p.update(status="APPROVED" if ok else "REJECTED", decided_by=actor, decision_note=note); self._hist(p, actor, p["status"], note)
        self._put("bd_opportunity", org, o); self.log("BD_PROPOSAL_APPROVED" if ok else "BD_PROPOSAL_REJECTED", actor, oid, org, f"{o['ref']} v{p['version']}")
        return self._oview(org, o)

    def approve_proposal(self, org, oid, pid, actor, note="") -> dict: return self._decide_proposal(org, oid, pid, actor, True, note)
    def reject_proposal(self, org, oid, pid, actor, note) -> dict: return self._decide_proposal(org, oid, pid, actor, False, note)

    def send_proposal(self, org, oid, pid, actor) -> dict:
        o = self._opp(org, oid); self._need_open(o); p = self._prop(o, pid)
        if p["status"] != "APPROVED": raise BizDevStateError("Only an approved proposal can be sent. A proposal with a large discount needs a second person's approval first.")
        if date.fromisoformat(p["valid_until"]) < self.today(): raise BizDevStateError("This proposal has expired. Create a new version.")
        for x in o["proposals"]:
            if x["status"] == "SENT": x["status"] = "SUPERSEDED"
        p.update(status="SENT", sent_at=self.now().isoformat(), sent_by=actor); self._hist(p, actor, "SENT")
        if o["stage"] in ("LEAD", "QUALIFIED"): self._move(o, actor, "PROPOSAL", f"proposal v{p['version']} sent")
        self._hist(o, actor, "PROPOSAL_SENT", f"v{p['version']}"); self._put("bd_opportunity", org, o); self.log("BD_PROPOSAL_SENT", actor, oid, org, f"{o['ref']} v{p['version']}")
        return self._oview(org, o)

    def accept_proposal(self, org, oid, pid, note, actor) -> dict:
        o = self._opp(org, oid); self._need_open(o); p = self._prop(o, pid)
        if p["status"] != "SENT": raise BizDevStateError("Only a proposal that has been sent can be marked accepted.")
        if date.fromisoformat(p["valid_until"]) < self.today(): raise BizDevStateError("This proposal expired before it was accepted.")
        for x in o["proposals"]:
            if x["status"] in ("SENT", "ACCEPTED") and x is not p: x["status"] = "SUPERSEDED"
        p.update(status="ACCEPTED", accepted_at=self.now().isoformat(), accept_note=_txt(note, "Note", 3, 500)); o["value"] = p["total"]
        self._hist(p, actor, "ACCEPTED", p["accept_note"]); self._hist(o, actor, "PROPOSAL_ACCEPTED", f"v{p['version']} {p['total']}"); self._put("bd_opportunity", org, o); self.log("BD_PROPOSAL_ACCEPTED", actor, oid, org, f"{o['ref']} v{p['version']}")
        return self._oview(org, o)

    def decline_proposal(self, org, oid, pid, reason, actor) -> dict:
        o = self._opp(org, oid); self._need_open(o); p = self._prop(o, pid)
        if p["status"] != "SENT": raise BizDevStateError("Only a proposal that has been sent can be marked declined.")
        p.update(status="DECLINED", decline_reason=_txt(reason, "The reason", 3, 500)); self._hist(p, actor, "DECLINED", p["decline_reason"]); self._put("bd_opportunity", org, o); self.log("BD_PROPOSAL_DECLINED", actor, oid, org, f"{o['ref']} v{p['version']}")
        return self._oview(org, o)

    # ------------------------------------------------------------------ targets
    def create_target(self, org, d, actor) -> dict:
        s, e = _date(d.get("start"), "Start date"), _date(d.get("end"), "End date")
        if e < s: raise BizDevError("The end date cannot be before the start date.")
        t = {"id": uuid.uuid4().hex, "org": org, "ref": self._ref(org, "T"), "name": _txt(d.get("name"), "Target name", 3, 200), "start": s.isoformat(), "end": e.isoformat(), "currency": _cur(d.get("currency")),
             "amount": s2(_dec(d.get("amount"), "Target amount", positive=True)), "status": "ACTIVE", "created_by": actor, "created_at": self.now().isoformat(), "history": []}
        self._hist(t, actor, "CREATED"); self._put("bd_target", org, t); self.log("BD_TARGET_CREATED", actor, t["id"], org, f"{t['ref']} {t['amount']} {t['currency']}")
        return self._tview(org, t)

    def retire_target(self, org, tid, note, actor) -> dict:
        t = self._get("bd_target", org, tid, "Target", for_update=True)
        if t["status"] != "ACTIVE": raise BizDevStateError("This target is already retired.")
        t.update(status="RETIRED", retire_note=_txt(note, "Reason", 3, 500)); self._hist(t, actor, "RETIRED", t["retire_note"]); self._put("bd_target", org, t); self.log("BD_TARGET_RETIRED", actor, tid, org, t["ref"])
        return self._tview(org, t)

    def _tview(self, org, t, opps=None, st=None) -> dict:
        opps = self._all("bd_opportunity", org) if opps is None else opps; st = st or self._settings(org)
        s, e = date.fromisoformat(t["start"]), date.fromisoformat(t["end"])
        won = sum((Decimal(o["value"]) for o in opps if o["stage"] == "WON" and o["currency"] == t["currency"] and s <= date.fromisoformat(o["won_date"]) <= e), ZERO)
        exp = sum((Decimal(o["value"]) * st["probabilities"][o["stage"]] / 100 for o in opps if o["stage"] in ACTIVE_STAGES and o["currency"] == t["currency"] and s <= date.fromisoformat(o["expected_close"]) <= e), ZERO)
        amt = Decimal(t["amount"]); v = dict(t)
        v.update(won=s2(won), attainment_pct=s2(won * 100 / amt), gap=s2(max(amt - won, ZERO)), weighted_expected=s2(exp), forecast=s2(won + exp), forecast_pct=s2((won + exp) * 100 / amt), in_period=s <= self.today() <= e)
        return v

    def list_targets(self, org) -> List[dict]:
        opps, st = self._all("bd_opportunity", org), self._settings(org)
        return [self._tview(org, t, opps, st) for t in sorted(self._all("bd_target", org), key=lambda t: t["ref"])]

    # ------------------------------------------------------------------ overview and forecast
    def _currency_figures(self, org, cur, opps=None, st=None) -> dict:
        opps = self._all("bd_opportunity", org) if opps is None else opps; st = st or self._settings(org)
        mine = [o for o in opps if o["currency"] == cur]
        rows = []
        for stage in ACTIVE_STAGES:
            xs = [o for o in mine if o["stage"] == stage]; val = sum((Decimal(o["value"]) for o in xs), ZERO)
            rows.append({"stage": stage, "count": len(xs), "value": s2(val), "probability": st["probabilities"][stage], "weighted": s2(sum((Decimal(o["value"]) * st["probabilities"][stage] / 100 for o in xs), ZERO))})
        act = [o for o in mine if o["stage"] in ACTIVE_STAGES]; won = [o for o in mine if o["stage"] == "WON"]; lost = [o for o in mine if o["stage"] == "LOST"]
        wv, lv = sum((Decimal(o["value"]) for o in won), ZERO), sum((Decimal(o["value"]) for o in lost), ZERO)
        stale = overdue = 0
        for o in act:
            f = self._oview(org, o, full=False, st=st, acct="")["flags"]; stale += "STALE" in f; overdue += "OVERDUE" in f
        return {"currency": cur, "open_count": len(act), "open_value": s2(sum((Decimal(r["value"]) for r in rows), ZERO)), "weighted": s2(sum((Decimal(r["weighted"]) for r in rows), ZERO)), "stages": rows,
                "won_count": len(won), "won_value": s2(wv), "lost_count": len(lost), "lost_value": s2(lv),
                "win_rate_pct": s2(Decimal(len(won)) * 100 / (len(won) + len(lost))) if won or lost else None, "win_rate_value_pct": s2(wv * 100 / (wv + lv)) if wv + lv > 0 else None,
                "stale": stale, "overdue": overdue}

    def overview(self, org) -> dict:
        opps, st = self._all("bd_opportunity", org), self._settings(org)
        curs = sorted({o["currency"] for o in opps} | {t["currency"] for t in self._all("bd_target", org)})
        proposals = sum(1 for o in opps if o["stage"] in OPEN_STAGES for p in o["proposals"] if p["status"] == "PENDING_APPROVAL")
        return {"currencies": [self._currency_figures(org, c, opps, st) for c in curs], "targets": [t for t in self.list_targets(org) if t["status"] == "ACTIVE"],
                "counts": {"accounts": sum(1 for a in self._all("bd_account", org) if a["status"] == "ACTIVE"), "opportunities": len(opps), "open": sum(1 for o in opps if o["stage"] in ACTIVE_STAGES),
                           "proposals_pending": proposals, "wins_pending": sum(1 for o in opps if o["stage"] == "WIN_PENDING"), "reports": len(self._all("bd_report", org))},
                "policy": self.get_policy(org), "limitations": LIMITATIONS}

    def options(self, org) -> dict:
        return {"stages": STAGES, "open_stages": OPEN_STAGES, "kinds": KINDS, "activity_types": ACTIVITY_TYPES, "policy": self.get_policy(org),
                "accounts": [{"id": a["id"], "ref": a["ref"], "name": a["name"], "kind": a["kind"]} for a in sorted(self._all("bd_account", org), key=lambda a: a["ref"]) if a["status"] == "ACTIVE"]}

    # ------------------------------------------------------------------ reports
    def _report(self, org, rid, for_update=False) -> dict: return self._get("bd_report", org, rid, "Report", for_update=for_update)

    def create_report(self, org, currency, title, actor) -> dict:
        cur = _cur(currency)
        if not any(o["currency"] == cur for o in self._all("bd_opportunity", org)): raise BizDevError(f"There are no opportunities in {cur} to report on.")
        r = {"id": uuid.uuid4().hex, "org": org, "ref": self._ref(org, "R"), "currency": cur, "title": _txt(title, "Report title", 3, 200), "status": "DRAFT", "created_by": actor, "created_at": self.now().isoformat(),
             "submitted_by": None, "decided_by": None, "decision_note": "", "snapshot": None, "fingerprint": None, "version": 0, "history": []}
        self._hist(r, actor, "CREATED"); self._put("bd_report", org, r); self.log("BD_REPORT_CREATED", actor, r["id"], org, r["ref"])
        return self._rview(r)

    def _snapshot(self, org, r) -> dict:
        cur, opps, st = r["currency"], self._all("bd_opportunity", org), self._settings(org)
        names = {a["id"]: a["name"] for a in self._all("bd_account", org)}
        rows = [self._oview(org, o, full=False, st=st, acct=names.get(o["account_id"], "(unknown)")) for o in sorted(opps, key=lambda o: o["ref"]) if o["currency"] == cur]
        keep = ("ref", "title", "account_name", "stage", "value", "probability", "weighted", "expected_close", "owner", "flags", "won_date", "lost_reason")
        return {"generated_at": self.now().isoformat(), "currency": cur, "figures": self._currency_figures(org, cur, opps, st), "opportunities": [{k: x[k] for k in keep} for x in rows],
                "targets": [t for t in self.list_targets(org) if t["currency"] == cur and t["status"] == "ACTIVE"],
                "policy": {"probabilities": st["probabilities"], "discount_limit_pct": st["discount_limit_pct"], "stale_days": st["stale_days"]}, "limitations": LIMITATIONS}

    def submit_report(self, org, rid, actor) -> dict:
        r = self._report(org, rid, for_update=True)
        if r["status"] not in ("DRAFT", "REJECTED"): raise BizDevStateError(f"A {r['status'].lower()} report cannot be submitted.")
        snap = self._snapshot(org, r)
        r.update(snapshot=snap, fingerprint=_sha(snap), status="SUBMITTED", version=r["version"] + 1, submitted_by=actor, decided_by=None, decision_note="")
        self._hist(r, actor, "SUBMITTED", f"version {r['version']}"); self._put("bd_report", org, r); self.log("BD_REPORT_SUBMITTED", actor, rid, org, r["ref"])
        return self._rview(r)

    def _decide_report(self, org, rid, actor, ok, note):
        r = self._report(org, rid, for_update=True)
        if r["status"] != "SUBMITTED": raise BizDevStateError("Only a submitted report can be approved or sent back.")
        self._two(actor, r["submitted_by"], "submitted this report")
        if ok and _sha(r["snapshot"]) != r["fingerprint"]: raise BizDevStateError("The stored report no longer matches its fingerprint. Submit it again.")
        note = _txt(note, "A reason", 0 if ok else 3, 1000, required=not ok)
        r.update(status="APPROVED" if ok else "REJECTED", decided_by=actor, decision_note=note, decided_at=self.now().isoformat())
        self._hist(r, actor, r["status"], note); self._put("bd_report", org, r); self.log("BD_REPORT_APPROVED" if ok else "BD_REPORT_REJECTED", actor, rid, org, r["ref"])
        return self._rview(r)

    def approve_report(self, org, rid, actor, note="") -> dict: return self._decide_report(org, rid, actor, True, note)
    def reject_report(self, org, rid, actor, note) -> dict: return self._decide_report(org, rid, actor, False, note)

    def _rview(self, r, full=True) -> dict:
        v = {k: x for k, x in r.items() if k != "snapshot"}
        v["has_snapshot"] = r["snapshot"] is not None
        if full: v["snapshot"] = r["snapshot"]
        v["confidentiality"] = CONFIDENTIAL
        return v

    def get_report(self, org, rid) -> dict: return self._rview(self._report(org, rid))
    def list_reports(self, org) -> List[dict]: return [self._rview(r, False) for r in sorted(self._all("bd_report", org), key=lambda r: r["ref"])]

    def export_csv(self, org, rid, actor) -> dict:
        r = self._report(org, rid)
        if r["status"] != "APPROVED": raise BizDevStateError("Only an approved report can be exported.")
        if _sha(r["snapshot"]) != r["fingerprint"]: raise BizDevStateError("The frozen report no longer matches its fingerprint; it cannot be exported.")
        s, buf = r["snapshot"], io.StringIO(); w = csv.writer(buf, lineterminator="\n")
        def safe(v):
            v = "" if v is None else str(v)
            return "'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v
        f = s["figures"]
        w.writerow([CONFIDENTIAL])
        for k, v in [("Report", r["title"]), ("Currency", s["currency"]), ("Version", r["version"]), ("Prepared by (user id)", r["submitted_by"]), ("Approved by (user id)", r["decided_by"]),
                     ("Generated at", s["generated_at"]), ("Fingerprint (SHA-256)", r["fingerprint"]), ("Open pipeline", f["open_value"]), ("Weighted forecast", f["weighted"]),
                     ("Won", f"{f['won_count']} worth {f['won_value']}"), ("Lost", f"{f['lost_count']} worth {f['lost_value']}"), ("Win rate by count %", f["win_rate_pct"] or "n/a")]:
            w.writerow([k, safe(v)])
        w.writerow([]); w.writerow(["PIPELINE BY STAGE"]); w.writerow(["Stage", "Deals", "Value", "Probability %", "Weighted"])
        for x in f["stages"]: w.writerow([x["stage"], x["count"], x["value"], x["probability"], x["weighted"]])
        w.writerow([]); w.writerow(["OPPORTUNITIES"]); w.writerow(["Ref", "Title", "Account", "Stage", "Value", "Probability %", "Weighted", "Expected close", "Won date", "Flags", "Lost reason"])
        for o in s["opportunities"]: w.writerow([o["ref"], safe(o["title"]), safe(o["account_name"]), o["stage"], o["value"], o["probability"], o["weighted"], o["expected_close"], o["won_date"] or "", " ".join(o["flags"]), safe(o["lost_reason"])])
        w.writerow([]); w.writerow(["TARGETS"]); w.writerow(["Ref", "Name", "Start", "End", "Target", "Won", "Attainment %", "Weighted expected", "Forecast", "Forecast %"])
        for t in s["targets"]: w.writerow([t["ref"], safe(t["name"]), t["start"], t["end"], t["amount"], t["won"], t["attainment_pct"], t["weighted_expected"], t["forecast"], t["forecast_pct"]])
        w.writerow([]); w.writerow(["LIMITATIONS"]); [w.writerow([x]) for x in s["limitations"]]
        self.log("BD_REPORT_EXPORTED", actor, rid, org, r["ref"])
        return {"filename": f"{r['ref']}-pipeline-v{r['version']}.csv", "content": buf.getvalue(), "content_type": "text/csv; charset=utf-8"}
