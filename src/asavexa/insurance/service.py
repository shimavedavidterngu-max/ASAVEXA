"""Insurance and claims (records and evidence): policies, claims, settlements decided by a different person, and amounts received.

Records (shared document store, per organisation): ic_policy, ic_claim, ic_setting.

Principles enforced here
  * This keeps what people type in about policies and claims and does exact decimal arithmetic on it. It contacts no insurer, checks no cover, assesses no loss, gives no insurance or legal advice, holds no money and posts nothing to the ledger.
  * A policy is recorded by one person. A claim is recorded against it. A settlement or a decline is PROPOSED by one person and DECIDED by a different person; money received against a settled claim is recorded and can never exceed the settled amount.
  * Amounts are kept per currency (the currency of the policy) and never added across currencies.
Nothing is edited after it is decided or deleted; a receipt is a new line. Every step is audited by reference number only.
"""
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable, List

from .errors import InsuranceError, InsuranceForbiddenError, InsuranceNotFoundError, InsuranceStateError

COVER_TYPES = ["PROPERTY", "LIABILITY", "MOTOR", "HEALTH", "LIFE", "CYBER", "MARINE", "CROP", "OTHER"]
DEFAULTS = {"warning_days": 60}
CENT = Decimal("0.01")
MAX_PROPOSALS = 5
LIMITATIONS = [
    "ASAVEXA keeps what people type in. It contacts no insurer, checks no policy wording or cover, assesses no loss and gives no insurance or legal advice.",
    "An insurer's decision on a claim is a fact a person types in; ASAVEXA cannot confirm it. A settlement approved here is the organisation's own record, not the insurer's.",
    "Premiums are recorded as typed; no schedule of premium payments, instalments, taxes, commissions or reinsurance is handled.",
    "Money received is a typed record. ASAVEXA does not see a bank account and posts nothing to the ledger.",
    "Amounts in different currencies are never added together. Dates are compared with today in UTC with one day of leeway.",
]


def _utc(): return datetime.now(timezone.utc)


def _txt(v, name, lo=1, hi=1000, required=True) -> str:
    v = (v if isinstance(v, str) else ("" if v is None else str(v)))
    v = " ".join("".join(c if c >= " " and c != "\x7f" else " " for c in v).split())
    if required and len(v) < lo:
        raise InsuranceError(f"{name} is required (at least {lo} characters).")
    if v and len(v) < lo:
        raise InsuranceError(f"{name} needs at least {lo} characters.")
    if len(v) > hi:
        raise InsuranceError(f"{name} is too long (limit {hi} characters).")
    return v


def _date(v, name) -> date:
    try:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", str(v).strip()): raise ValueError
        return date.fromisoformat(str(v).strip())
    except (ValueError, TypeError):
        raise InsuranceError(f"{name} must be a real date written YYYY-MM-DD.")


def _enum(v, allowed, name) -> str:
    v = _txt(v, name, 1, 40).upper()
    if v not in allowed:
        raise InsuranceError(f"{name} must be one of {', '.join(allowed)}.")
    return v


def _int(v, name, lo, hi) -> int:
    if isinstance(v, bool) or not re.fullmatch(r"[0-9]{1,15}", str(v).strip()):
        raise InsuranceError(f"{name} must be a whole number from {lo} to {hi}.")
    n = int(str(v).strip())
    if not lo <= n <= hi:
        raise InsuranceError(f"{name} must be a whole number from {lo} to {hi}.")
    return n


def _amount(v, name, zero_ok=False) -> Decimal:
    """Text or a whole number: ASCII digits, at most two decimals, never a float, commas only as thousands separators."""
    if isinstance(v, bool) or isinstance(v, float) or v is None:
        raise InsuranceError(f"{name} must be an amount such as 1500.00.")
    t = str(v).strip()
    if "," in t and not re.fullmatch(r"[0-9]{1,3}(,[0-9]{3})+(\.[0-9]+)?", t):
        raise InsuranceError(f"{name} must be an amount such as 1500.00 (commas only between groups of three digits).")
    t = t.replace(",", "")
    if not re.fullmatch(r"[0-9]{1,12}(\.[0-9]{1,2})?", t):
        raise InsuranceError(f"{name} must be an amount such as 1500.00 (at most two decimals).")
    d = Decimal(t)
    if d == 0 and not zero_ok:
        raise InsuranceError(f"{name} must be more than zero.")
    return d.quantize(CENT)


def refnum(r) -> int:
    try: return int(str(r["ref"]).rsplit("-", 1)[1])
    except (KeyError, IndexError, ValueError): return 0


class InsuranceService:
    def __init__(self, store, vault=None, log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = _utc):
        self.store, self.vault, self.log, self.now = store, vault, log, now

    # ------------------------------------------------------------------ helpers
    def today(self) -> date: return self.now().date()

    def _not_future(self, d: date, what: str):
        if d > self.today() + timedelta(days=1):
            raise InsuranceError(f"{what} cannot be in the future.")

    def _put(self, kind, org, d): self.store.put(kind, f"{org}:{d['id']}", d, org_id=org)
    def _all(self, kind, org) -> list: return [d for _, d in self.store.list(kind, org_id=org, prefix=f"{org}:") if d.get("org") == org]

    def _get(self, kind, org, rid, label, for_update=False) -> dict:
        r = self.store.get(kind, f"{org}:{rid}", for_update=for_update)
        if r is None or r.get("org") != org:
            raise InsuranceNotFoundError(f"{label} not found.")
        return r

    def _settings(self, org, for_update=False) -> dict:
        s = self.store.get("ic_setting", f"{org}:settings", for_update=for_update)
        if s and s.get("org") == org:
            return s
        return {"id": "settings", "org": org, **DEFAULTS, "counters": {}, "updated_by": None, "updated_at": None}

    def _ref(self, org, prefix) -> str:
        s = self._settings(org, for_update=True)
        n = s["counters"].get(prefix, 0) + 1
        s["counters"][prefix] = n
        self._put("ic_setting", org, s)
        return f"{prefix}-{n:03d}"

    def _hist(self, r, actor, event, note=""):
        r.setdefault("history", []).append({"at": self.now().isoformat(), "by": actor, "event": event, "note": note})

    def _two(self, actor, other, what):
        if actor == other:
            raise InsuranceForbiddenError(f"You {what}, so you cannot do this. A different person must.")

    # ------------------------------------------------------------------ policy (setting)
    def ic_get_policy(self, org) -> dict:
        s = self._settings(org)
        return {"warning_days": s["warning_days"], "updated_by": s["updated_by"], "updated_at": s["updated_at"],
                "meaning": f"A policy that ends within {s['warning_days']} days is flagged as ending soon. This is your own setting, not a rule."}

    def ic_set_policy(self, org, d, actor) -> dict:
        s = self._settings(org, for_update=True)
        if d.get("warning_days") is not None: s["warning_days"] = _int(d["warning_days"], "The warning days", 7, 365)
        s.update(updated_by=actor, updated_at=self.now().isoformat())
        self._put("ic_setting", org, s)
        self.log("INSURANCE_SETTING_SET", actor, "settings", org, f"warning {s['warning_days']} days")
        return self.ic_get_policy(org)

    # ------------------------------------------------------------------ views
    def _claims_of(self, org, pid) -> list: return [c for c in self._all("ic_claim", org) if c["policy_id"] == pid]

    def _policy_view(self, p) -> dict:
        v = {x: p[x] for x in p if x != "org"}
        end = date.fromisoformat(p["end_date"]); today = self.today()
        open_claims = sum(1 for c in self._claims_of(p["org"], p["id"]) if c["status"] in ("OPEN", "PROPOSED"))
        v.update(open_claims=open_claims, expired=p["status"] == "ACTIVE" and end < today,
                 ending_soon=p["status"] == "ACTIVE" and today <= end <= today + timedelta(days=self._settings(p["org"])["warning_days"]))
        return v

    def _claim_view(self, c, p=None) -> dict:
        v = {x: c[x] for x in c if x != "org"}
        rec = sum((Decimal(r["amount"]) for r in c["receipts"]), Decimal(0))
        v.update(received=str(rec.quantize(CENT)), outstanding=str((Decimal(c["settled_amount"]) - rec).quantize(CENT)) if c["settled_amount"] is not None else None,
                 pending=sum(1 for q in c["proposals"] if q["status"] == "PENDING"))
        return v

    # ------------------------------------------------------------------ policies
    def ic_add_policy(self, org, d, actor) -> dict:
        insurer = _txt(d.get("insurer"), "The insurer", 2, 150); number = _txt(d.get("policy_number"), "The policy number", 2, 60); cover = _enum(d.get("cover_type"), COVER_TYPES, "The type of cover")
        cur = _txt(d.get("currency"), "The currency", 3, 3).upper()
        if not re.fullmatch(r"[A-Z]{3}", cur): raise InsuranceError("The currency must be a three-letter code such as NGN.")
        si = _amount(d.get("sum_insured"), "The sum insured"); prem = _amount(d.get("premium"), "The premium", True)
        excess = _amount(d.get("excess"), "The excess", True) if d.get("excess") not in (None, "") else Decimal("0.00")
        start = _date(d.get("start_date"), "The start date"); end = _date(d.get("end_date"), "The end date")
        if end <= start: raise InsuranceError("The end date must be after the start date.")
        if (end - start).days > 366 * 10: raise InsuranceError("A policy cannot run for more than ten years.")
        if excess > si: raise InsuranceError("The excess cannot be more than the sum insured.")
        covers = _txt(d.get("covers"), "What is covered", 5, 300)
        for p in self._all("ic_policy", org):
            if p["status"] == "ACTIVE" and p["insurer"].lower() == insurer.lower() and p["policy_number"].lower() == number.lower():
                raise InsuranceStateError("An active policy with that insurer and policy number already exists.")
        p = {"id": uuid.uuid4().hex, "org": org, "ref": None, "insurer": insurer, "policy_number": number, "cover_type": cover, "covers": covers, "currency": cur, "sum_insured": str(si), "premium": str(prem), "excess": str(excess),
             "start_date": start.isoformat(), "end_date": end.isoformat(), "status": "ACTIVE", "created_by": actor, "created_at": self.now().isoformat(), "cancel_note": None, "history": []}
        p["ref"] = self._ref(org, "IP"); self._hist(p, actor, "RECORDED")
        self._put("ic_policy", org, p); self.log("INSURANCE_POLICY_ADDED", actor, p["id"], org, p["ref"])
        return self._policy_view(p)

    def ic_list_policies(self, org, status=None) -> List[dict]:
        return [self._policy_view(p) for p in sorted(self._all("ic_policy", org), key=refnum) if not status or p["status"] == status]

    def ic_get_policy_record(self, org, pid) -> dict:
        p = self._get("ic_policy", org, pid, "Policy"); v = self._policy_view(p)
        v["claims"] = [self._claim_view(c) for c in sorted(self._claims_of(org, pid), key=refnum)]
        return v

    def ic_cancel_policy(self, org, pid, reason, actor) -> dict:
        p = self._get("ic_policy", org, pid, "Policy", for_update=True)
        if p["status"] != "ACTIVE": raise InsuranceStateError("That policy is already cancelled.")
        reason = _txt(reason, "A reason", 10, 500)
        if any(c["status"] in ("OPEN", "PROPOSED") for c in self._claims_of(org, pid)): raise InsuranceStateError("A policy with a claim still open or waiting cannot be cancelled.")
        p.update(status="CANCELLED", cancel_note=reason); self._hist(p, actor, "CANCELLED", reason)
        self._put("ic_policy", org, p); self.log("INSURANCE_POLICY_CANCELLED", actor, pid, org, p["ref"])
        return self._policy_view(p)

    # ------------------------------------------------------------------ claims
    def ic_add_claim(self, org, pid, d, actor) -> dict:
        p = self._get("ic_policy", org, pid, "Policy")
        if p["status"] != "ACTIVE": raise InsuranceStateError("Claims can only be recorded against an active policy.")
        loss = _date(d.get("loss_date"), "The date of the loss"); self._not_future(loss, "The date of the loss")
        rep = _date(d.get("reported_date"), "The date it was reported"); self._not_future(rep, "The date it was reported")
        if rep < loss: raise InsuranceError("It cannot be reported before the loss happened.")
        if not date.fromisoformat(p["start_date"]) <= loss <= date.fromisoformat(p["end_date"]): raise InsuranceError("The loss date is outside the period the policy runs.")
        desc = _txt(d.get("description"), "The description of the loss", 10, 1500); amount = _amount(d.get("claimed_amount"), "The amount claimed")
        if amount > Decimal(p["sum_insured"]): raise InsuranceError("The amount claimed cannot be more than the sum insured.")
        c = {"id": uuid.uuid4().hex, "org": org, "ref": None, "policy_id": pid, "policy_ref": p["ref"], "currency": p["currency"], "loss_date": loss.isoformat(), "reported_date": rep.isoformat(), "description": desc, "claimed_amount": str(amount),
             "claim_number": _txt(d.get("claim_number"), "The insurer's claim number", 2, 60, required=False) or None, "status": "OPEN", "settled_amount": None, "outcome": None, "decided_by": None, "decided_on": None, "decision_note": None,
             "proposals": [], "receipts": [], "created_by": actor, "created_at": self.now().isoformat(), "history": []}
        c["ref"] = self._ref(org, "CL"); self._hist(c, actor, "RECORDED")
        self._put("ic_claim", org, c); self.log("INSURANCE_CLAIM_ADDED", actor, c["id"], org, c["ref"])
        return self._claim_view(c)

    def ic_list_claims(self, org, status=None) -> List[dict]:
        return [self._claim_view(c) for c in sorted(self._all("ic_claim", org), key=refnum) if not status or c["status"] == status]

    def ic_get_claim(self, org, cid) -> dict: return self._claim_view(self._get("ic_claim", org, cid, "Claim"))

    def _open_claim(self, org, cid) -> dict:
        c = self._get("ic_claim", org, cid, "Claim", for_update=True)
        if c["status"] != "OPEN": raise InsuranceStateError("Only a claim that is open and has no proposal waiting can take a new proposal.")
        return c

    def ic_propose_outcome(self, org, cid, d, actor) -> dict:
        c = self._open_claim(org, cid); outcome = _enum(d.get("outcome"), ["SETTLE", "DECLINE"], "The outcome"); note = _txt(d.get("note"), "The note on the insurer's decision", 10, 1000)
        if len(c["proposals"]) >= MAX_PROPOSALS: raise InsuranceStateError(f"At most {MAX_PROPOSALS} proposals can be made on one claim.")
        amount = None
        if outcome == "SETTLE":
            amount = _amount(d.get("amount"), "The settled amount")
            if amount > Decimal(c["claimed_amount"]): raise InsuranceError("The settled amount cannot be more than the amount claimed.")
        elif d.get("amount") not in (None, "", 0, "0"): raise InsuranceError("A decline has no settled amount.")
        c["proposals"].append({"no": len(c["proposals"]) + 1, "outcome": outcome, "amount": str(amount) if amount is not None else None, "note": note, "by": actor, "at": self.now().isoformat(), "status": "PENDING", "decided_by": None, "decision_note": None})
        c["status"] = "PROPOSED"; self._hist(c, actor, "OUTCOME_PROPOSED")
        self._put("ic_claim", org, c); self.log("INSURANCE_OUTCOME_PROPOSED", actor, cid, org, f"{c['ref']} #{len(c['proposals'])}")
        return self._claim_view(c)

    def _pending(self, org, cid, no):
        c = self._get("ic_claim", org, cid, "Claim", for_update=True); n = _int(no, "The proposal number", 1, 1000)
        q = next((q for q in c["proposals"] if q["no"] == n), None)
        if q is None: raise InsuranceNotFoundError("Proposal not found.")
        if q["status"] != "PENDING" or c["status"] != "PROPOSED": raise InsuranceStateError("That proposal has already been decided.")
        return c, q

    def ic_approve_outcome(self, org, cid, no, d, actor) -> dict:
        c, q = self._pending(org, cid, no); self._two(actor, q["by"], "proposed this outcome")
        note = _txt(d.get("note"), "An approval note", 10, 1000, required=False)
        q.update(status="APPROVED", decided_by=actor, decision_note=note or None)
        c.update(status="SETTLED" if q["outcome"] == "SETTLE" else "DECLINED", outcome=q["outcome"], settled_amount=q["amount"], decided_by=actor, decided_on=self.today().isoformat(), decision_note=note or None)
        self._hist(c, actor, "OUTCOME_APPROVED", note)
        self._put("ic_claim", org, c); self.log("INSURANCE_OUTCOME_APPROVED", actor, cid, org, f"{c['ref']} #{q['no']}")
        return self._claim_view(c)

    def ic_reject_outcome(self, org, cid, no, reason, actor) -> dict:
        c, q = self._pending(org, cid, no); self._two(actor, q["by"], "proposed this outcome")
        reason = _txt(reason, "A reason", 10, 1000); q.update(status="REJECTED", decided_by=actor, decision_note=reason); c["status"] = "OPEN"; self._hist(c, actor, "OUTCOME_REJECTED", reason)
        self._put("ic_claim", org, c); self.log("INSURANCE_OUTCOME_REJECTED", actor, cid, org, f"{c['ref']} #{q['no']}")
        return self._claim_view(c)

    def ic_record_receipt(self, org, cid, d, actor) -> dict:
        c = self._get("ic_claim", org, cid, "Claim", for_update=True)
        if c["status"] != "SETTLED": raise InsuranceStateError("Money received can only be recorded against a settled claim.")
        amount = _amount(d.get("amount"), "The amount received"); on = _date(d.get("received_on"), "The date received"); self._not_future(on, "The date received")
        if on < date.fromisoformat(c["decided_on"]) - timedelta(days=1): raise InsuranceError("Money cannot be received before the settlement was approved.")
        ref = _txt(d.get("reference"), "The payment reference", 2, 80)
        rec = sum((Decimal(r["amount"]) for r in c["receipts"]), Decimal(0))
        if rec + amount > Decimal(c["settled_amount"]): raise InsuranceError(f"That would be more than was settled. At most {Decimal(c['settled_amount']) - rec} can still be recorded.")
        if any(r["reference"].lower() == ref.lower() for r in c["receipts"]): raise InsuranceStateError("A receipt with that reference is already recorded on this claim.")
        c["receipts"].append({"no": len(c["receipts"]) + 1, "amount": str(amount), "received_on": on.isoformat(), "reference": ref, "by": actor, "at": self.now().isoformat()})
        self._hist(c, actor, "RECEIPT_RECORDED")
        self._put("ic_claim", org, c); self.log("INSURANCE_RECEIPT_RECORDED", actor, cid, org, f"{c['ref']} #{len(c['receipts'])}")
        return self._claim_view(c)

    # ------------------------------------------------------------------ overview
    def ic_overview(self, org) -> dict:
        ps = self.ic_list_policies(org); cs = self.ic_list_claims(org); att = []

        def add(kind, n, text):
            if n: att.append({"kind": kind, "count": n, "text": text})
        add("OUTCOMES_TO_DECIDE", sum(1 for c in cs if c["status"] == "PROPOSED"), "claim outcome(s) are waiting for a different person to decide them.")
        add("SETTLED_UNPAID", sum(1 for c in cs if c["status"] == "SETTLED" and Decimal(c["outstanding"]) > 0), "settled claim(s) have money still to be received.")
        add("POLICIES_ENDING_SOON", sum(1 for p in ps if p["ending_soon"]), "active policy(ies) end within your warning window.")
        add("POLICIES_EXPIRED", sum(1 for p in ps if p["expired"]), "active policy(ies) have passed their end date and have not been cancelled or replaced.")
        tot = {}
        for p in ps:
            t = tot.setdefault(p["currency"], {"currency": p["currency"], "active_policies": 0, "sum_insured": Decimal(0), "premium": Decimal(0), "open_claims": 0, "claimed_open": Decimal(0), "settled": Decimal(0), "received": Decimal(0)})
            if p["status"] == "ACTIVE": t["active_policies"] += 1; t["sum_insured"] += Decimal(p["sum_insured"]); t["premium"] += Decimal(p["premium"])
        for c in cs:
            t = tot.get(c["currency"])
            if t is None: continue
            if c["status"] in ("OPEN", "PROPOSED"): t["open_claims"] += 1; t["claimed_open"] += Decimal(c["claimed_amount"])
            if c["status"] == "SETTLED": t["settled"] += Decimal(c["settled_amount"])
            t["received"] += Decimal(c["received"])
        out = []
        for t in sorted(tot.values(), key=lambda x: x["currency"]):
            t = dict(t)
            for k in ("sum_insured", "premium", "claimed_open", "settled", "received"): t[k] = str(t[k].quantize(CENT))
            t["outstanding"] = str((Decimal(t["settled"]) - Decimal(t["received"])).quantize(CENT)); out.append(t)
        counts = {"policies_active": sum(1 for p in ps if p["status"] == "ACTIVE"), "policies_cancelled": sum(1 for p in ps if p["status"] == "CANCELLED"), **{f"claims_{s.lower()}": sum(1 for c in cs if c["status"] == s) for s in ("OPEN", "PROPOSED", "SETTLED", "DECLINED")}}
        return {"counts": counts, "totals": out, "attention": att, "policy": self.ic_get_policy(org), "limitations": LIMITATIONS}

    def ic_options(self, org) -> dict:
        return {"cover_types": COVER_TYPES, "limitations": LIMITATIONS}
