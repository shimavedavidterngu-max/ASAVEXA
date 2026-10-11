"""Public Finance service.

Records (shared document store, per organisation): pf_budget (with its virements), pf_commitment, pf_procurement, pf_grant (with receipts and spend entries),
pf_report, pf_setting. It reads the ledger (posted journals) and the Evidence Vault and never changes either.

Principles enforced here: an approved budget is frozen (changes are separate virements a second person approves); a commitment can never exceed what is
available on its budget line; an award, a virement, a grant spend entry and a report are each approved by someone other than who proposed them; money is
exact Decimal; every step is audited. Figures labelled ACTUAL come only from posted journals."""
import csv
import hashlib
import io
import json
import uuid
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Callable, List, Optional

from .errors import PubFinError, PubFinForbiddenError, PubFinNotFoundError, PubFinStateError

ZERO = Decimal("0.00")
DEFAULT_MIN_QUOTES = 3
DEFAULT_QUOTE_THRESHOLD = "0.00"
CONFIDENTIAL = "CONFIDENTIAL - ASAVEXA public finance accountability report. For the organisation named and people it has authorised."
LIMITATIONS = [
    "ACTUAL figures come only from posted journals dated inside the budget period. Drafts are excluded. Amounts in different currencies are not converted.",
    "A commitment stops counting against the budget when it is settled. Until the invoice is posted to the ledger, settled spending is not in ACTUAL, so settle after posting.",
    "Procurement thresholds and the number of quotes are your own policy settings. The defaults are placeholders, not law or any government's rule.",
    "Approval records that a second person reviewed the item. It is not an audit opinion, a legal certification or a procurement-law compliance check.",
    "Grant conditions are text you enter. ASAVEXA tracks amounts and dates against the award; it does not judge whether donor conditions are met.",
]


def _utc(): return datetime.now(timezone.utc)
def _sha(o) -> str: return hashlib.sha256(json.dumps(o, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
def q2(x) -> Decimal: return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
def s2(x) -> str: return str(q2(x))


def _txt(v, name, lo=1, hi=1000, required=True) -> str:
    v = (v if isinstance(v, str) else ("" if v is None else str(v))).strip()
    if required and len(v) < lo:
        raise PubFinError(f"{name} is required (at least {lo} characters).")
    if len(v) > hi:
        raise PubFinError(f"{name} is too long (limit {hi} characters).")
    return v


def _dec(v, name, lo=None, positive=False) -> Decimal:
    if v is None or isinstance(v, bool) or (isinstance(v, str) and not v.strip()):
        raise PubFinError(f"{name} is required and must be a number.")
    try:
        x = Decimal(str(v).strip())
    except (InvalidOperation, ValueError):
        raise PubFinError(f"{name} must be a number.")
    if not x.is_finite():
        raise PubFinError(f"{name} must be a number.")
    if abs(x) > Decimal("999999999999999.99"):
        raise PubFinError(f"{name} is too large.")
    x = q2(x)
    if positive and x <= 0:
        raise PubFinError(f"{name} must be more than zero.")
    if lo is not None and x < Decimal(str(lo)):
        raise PubFinError(f"{name} must be at least {lo}.")
    return x


def _date(v, name) -> date:
    try:
        return date.fromisoformat(str(v).strip())
    except (ValueError, TypeError):
        raise PubFinError(f"{name} must be a real date written YYYY-MM-DD.")


class PubFinService:
    def __init__(self, store, accounting, vault, log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = _utc):
        self.store, self.accounting, self.vault, self.log, self.now = store, accounting, vault, log, now

    # ------------------------------------------------------------------ helpers
    def today(self) -> date: return self.now().date()
    def _put(self, kind, org, d): self.store.put(kind, f"{org}:{d['id']}", d, org_id=org)
    def _all(self, kind, org) -> list: return [d for _, d in self.store.list(kind, org_id=org, prefix=f"{org}:") if d.get("org") == org]

    def _get(self, kind, org, rid, label, for_update=False) -> dict:
        r = self.store.get(kind, f"{org}:{rid}", for_update=for_update)
        if r is None or r["org"] != org:
            raise PubFinNotFoundError(f"{label} not found.")
        return r

    def _settings(self, org, for_update=False) -> dict:
        s = self.store.get("pf_setting", f"{org}:settings", for_update=for_update)
        return s if s else {"id": "settings", "org": org, "min_quotes": DEFAULT_MIN_QUOTES, "quote_threshold": DEFAULT_QUOTE_THRESHOLD, "counters": {}, "updated_by": None, "updated_at": None}

    def _ref(self, org, prefix) -> str:
        s = self._settings(org, for_update=True)
        n = s["counters"].get(prefix, 0) + 1
        s["counters"][prefix] = n
        self._put("pf_setting", org, s)
        return f"{prefix}-{n:03d}"

    def _hist(self, r, actor, event, note=""):
        r.setdefault("history", []).append({"at": self.now().isoformat(), "by": actor, "event": event, "note": note})

    def _evidence(self, org, ids) -> List[dict]:
        out = []
        for i in dict.fromkeys(str(i) for i in (ids or [])):
            try:
                e = self.vault.get_evidence(org, i)
            except Exception:
                raise PubFinError("Linked evidence not found in this organisation's Evidence Vault.")
            out.append({"evidence_id": e.id, "filename": e.original_filename, "file_hash": e.file_hash})
        return out

    def _accounts(self, org) -> dict: return {a.id: a for a in self.accounting.accounts.list_for_org(org)}
    @staticmethod
    def _atype(a) -> str: return a.type.value if hasattr(a.type, "value") else str(a.type)

    def _two(self, actor, other, what):
        if actor == other:
            raise PubFinForbiddenError(f"You {what}, so you cannot decide it. A different person must.")

    # ------------------------------------------------------------------ policy
    def get_policy(self, org) -> dict:
        s = self._settings(org)
        return {"min_quotes": s["min_quotes"], "quote_threshold": s["quote_threshold"], "updated_by": s["updated_by"], "updated_at": s["updated_at"],
                "meaning": f"A procurement estimated at {s['quote_threshold']} or more needs at least {s['min_quotes']} quotes, or a written exception reason. These are your policy settings, not law."}

    def set_policy(self, org, min_quotes, quote_threshold, actor) -> dict:
        try:
            mq = int(str(min_quotes).strip()) if not isinstance(min_quotes, bool) else -1
        except ValueError:
            mq = -1
        if not 1 <= mq <= 10:
            raise PubFinError("The minimum number of quotes must be a whole number from 1 to 10.")
        th = _dec(quote_threshold, "Quote threshold", lo=0)
        s = self._settings(org, for_update=True)
        s.update(min_quotes=mq, quote_threshold=s2(th), updated_by=actor, updated_at=self.now().isoformat())
        self._put("pf_setting", org, s)
        self.log("PF_POLICY_SET", actor, "settings", org, f"quotes {mq}, threshold {s2(th)}")
        return self.get_policy(org)

    # ------------------------------------------------------------------ actuals and execution
    def _actuals(self, org, start: date, end: date) -> dict:
        types = {k: self._atype(a) for k, a in self._accounts(org).items()}
        out, n = {}, 0
        for j in self.accounting.journals.list_for_org(org):
            st = j.status.value if hasattr(j.status, "value") else str(j.status)
            if st == "DRAFT" or not (start <= j.date <= end):
                continue
            n += 1
            for ln in j.lines:
                t = types.get(ln.account_id)
                if t == "EXPENSE": out[ln.account_id] = out.get(ln.account_id, ZERO) + ln.debit_amount - ln.credit_amount
                elif t == "REVENUE": out[ln.account_id] = out.get(ln.account_id, ZERO) + ln.credit_amount - ln.debit_amount
        out["_journals"] = n
        return out

    def _open_commitments(self, org, bid) -> dict:
        out = {}
        for c in self._all("pf_commitment", org):
            if c["budget_id"] == bid and c["status"] == "OPEN":
                out[c["account_id"]] = out.get(c["account_id"], ZERO) + Decimal(c["amount"])
        return out

    def _effective(self, b) -> dict:
        eff = {ln["account_id"]: Decimal(ln["amount"]) for ln in b["lines"]}
        for v in b["virements"]:
            if v["status"] == "APPROVED":
                eff[v["from_account"]] -= Decimal(v["amount"]); eff[v["to_account"]] += Decimal(v["amount"])
        return eff

    def execution(self, org, bid) -> dict:
        b = self._get("pf_budget", org, bid, "Budget")
        act = self._actuals(org, date.fromisoformat(b["start"]), date.fromisoformat(b["end"]))
        com, eff = self._open_commitments(org, bid), self._effective(b)
        rows, tot = [], {"budget": ZERO, "actual": ZERO, "committed": ZERO, "available": ZERO}
        for ln in b["lines"]:
            a, base, e = ln["account_id"], Decimal(ln["amount"]), eff[ln["account_id"]]
            actual, committed = act.get(a, ZERO), com.get(a, ZERO)
            row = {"account_id": a, "code": ln["code"], "name": ln["name"], "type": ln["type"], "approved": s2(base), "adjustment": s2(e - base), "budget": s2(e), "actual": s2(actual)}
            if ln["type"] == "EXPENSE":
                avail = e - actual - committed
                row.update(committed=s2(committed), available=s2(avail), used_pct=s2(actual * 100 / e) if e else None, overspent=avail < 0)
                for k, v in (("budget", e), ("actual", actual), ("committed", committed), ("available", avail)): tot[k] += v
            else:
                row.update(committed=None, available=None, used_pct=s2(actual * 100 / e) if e else None, overspent=False, shortfall=s2(e - actual))
            rows.append(row)
        return {"budget_id": bid, "ref": b["ref"], "name": b["name"], "status": b["status"], "start": b["start"], "end": b["end"], "currency": b["currency"], "rows": rows,
                "expense_totals": {k: s2(v) for k, v in tot.items()}, "journals_examined": act["_journals"], "basis": "ACTUAL = posted journals dated inside the period; COMMITTED = open commitments", "limitations": LIMITATIONS}

    # ------------------------------------------------------------------ budgets
    def _lines(self, org, lines) -> List[dict]:
        if not isinstance(lines, list) or not lines:
            raise PubFinError("Enter at least one budget line.")
        accts, seen, out = self._accounts(org), set(), []
        for ln in lines:
            aid = str((ln or {}).get("account_id", ""))
            a = accts.get(aid)
            if a is None:
                raise PubFinNotFoundError("One of the budget accounts was not found in this organisation.")
            if aid in seen:
                raise PubFinError(f"{a.code} {a.name} appears twice. Use one line per account.")
            t = self._atype(a)
            if t not in ("EXPENSE", "REVENUE"):
                raise PubFinError(f"{a.code} {a.name} is not an expense or revenue account; only those can be budgeted.")
            seen.add(aid)
            out.append({"account_id": aid, "code": a.code, "name": a.name, "type": t, "amount": s2(_dec((ln or {}).get("amount"), f"Amount for {a.code}", lo=0))})
        return out

    def _bfields(self, org, d):
        s, e = _date(d.get("start"), "Start date"), _date(d.get("end"), "End date")
        if e < s:
            raise PubFinError("The end date cannot be before the start date.")
        cur = _txt(d.get("currency"), "Currency", 3, 3).upper()
        return {"name": _txt(d.get("name"), "Budget name", 3, 200), "description": _txt(d.get("description"), "Description", 0, 1500, required=False), "start": s.isoformat(), "end": e.isoformat(),
                "currency": cur, "lines": self._lines(org, d.get("lines"))}

    def create_budget(self, org, d, actor) -> dict:
        f = self._bfields(org, d)
        b = {"id": uuid.uuid4().hex, "org": org, "ref": self._ref(org, "B"), "status": "DRAFT", "created_by": actor, "created_at": self.now().isoformat(), "submitted_by": None, "decided_by": None,
             "decision_note": "", "fingerprint": None, "virements": [], "history": [], **f}
        self._hist(b, actor, "CREATED", f"{len(b['lines'])} line(s)")
        self._put("pf_budget", org, b); self.log("PF_BUDGET_CREATED", actor, b["id"], org, b["ref"])
        return self._bview(b)

    def update_budget(self, org, bid, d, actor) -> dict:
        b = self._get("pf_budget", org, bid, "Budget", for_update=True)
        if b["status"] not in ("DRAFT", "REJECTED"):
            raise PubFinStateError("Only a draft or sent-back budget can be edited. Approved budgets change only through approved virements.")
        b.update(self._bfields(org, {**{k: b[k] for k in ("name", "description", "start", "end", "currency", "lines")}, **d}))
        self._hist(b, actor, "UPDATED"); self._put("pf_budget", org, b); self.log("PF_BUDGET_UPDATED", actor, bid, org, b["ref"])
        return self._bview(b)

    def discard_budget(self, org, bid, actor) -> dict:
        b = self._get("pf_budget", org, bid, "Budget", for_update=True)
        if b["status"] not in ("DRAFT", "REJECTED"):
            raise PubFinStateError("Only a draft or sent-back budget can be discarded.")
        b["status"] = "DISCARDED"; self._hist(b, actor, "DISCARDED"); self._put("pf_budget", org, b); self.log("PF_BUDGET_DISCARDED", actor, bid, org, b["ref"])
        return self._bview(b)

    def submit_budget(self, org, bid, actor) -> dict:
        b = self._get("pf_budget", org, bid, "Budget", for_update=True)
        if b["status"] not in ("DRAFT", "REJECTED"):
            raise PubFinStateError(f"A {b['status'].lower()} budget cannot be submitted.")
        b.update(status="SUBMITTED", submitted_by=actor, decided_by=None, decision_note="", fingerprint=_sha({k: b[k] for k in ("name", "start", "end", "currency", "lines")}))
        self._hist(b, actor, "SUBMITTED", f"fingerprint {b['fingerprint'][:12]}"); self._put("pf_budget", org, b); self.log("PF_BUDGET_SUBMITTED", actor, bid, org, b["ref"])
        return self._bview(b)

    def _decide_budget(self, org, bid, actor, ok, note):
        b = self._get("pf_budget", org, bid, "Budget", for_update=True)
        if b["status"] != "SUBMITTED":
            raise PubFinStateError("Only a submitted budget can be approved or sent back.")
        self._two(actor, b["submitted_by"], "submitted this budget")
        if ok and _sha({k: b[k] for k in ("name", "start", "end", "currency", "lines")}) != b["fingerprint"]:
            raise PubFinStateError("The budget no longer matches its fingerprint. Submit it again.")
        note = _txt(note, "A reason", 3 if not ok else 0, 1000, required=not ok)
        b.update(status="APPROVED" if ok else "REJECTED", decided_by=actor, decision_note=note, decided_at=self.now().isoformat())
        self._hist(b, actor, b["status"], note); self._put("pf_budget", org, b); self.log("PF_BUDGET_APPROVED" if ok else "PF_BUDGET_REJECTED", actor, bid, org, b["ref"])
        return self._bview(b)

    def approve_budget(self, org, bid, actor, note="") -> dict: return self._decide_budget(org, bid, actor, True, note)
    def reject_budget(self, org, bid, actor, note) -> dict: return self._decide_budget(org, bid, actor, False, note)

    def close_budget(self, org, bid, note, actor) -> dict:
        b = self._get("pf_budget", org, bid, "Budget", for_update=True)
        if b["status"] != "APPROVED":
            raise PubFinStateError("Only an approved budget can be closed.")
        if any(c["budget_id"] == bid and c["status"] == "OPEN" for c in self._all("pf_commitment", org)):
            raise PubFinStateError("This budget still has open commitments. Settle or cancel them first.")
        if any(v["status"] == "PROPOSED" for v in b["virements"]):
            raise PubFinStateError("Decide the pending virement first.")
        b["status"] = "CLOSED"; b["close_note"] = _txt(note, "Closing note", 5, 500); self._hist(b, actor, "CLOSED", b["close_note"])
        self._put("pf_budget", org, b); self.log("PF_BUDGET_CLOSED", actor, bid, org, b["ref"])
        return self._bview(b)

    def _bview(self, b) -> dict:
        v = dict(b)
        v["total_expense"] = s2(sum((Decimal(x["amount"]) for x in b["lines"] if x["type"] == "EXPENSE"), ZERO))
        v["total_revenue"] = s2(sum((Decimal(x["amount"]) for x in b["lines"] if x["type"] == "REVENUE"), ZERO))
        return v

    def get_budget(self, org, bid) -> dict:
        v = self._bview(self._get("pf_budget", org, bid, "Budget"))
        if v["status"] in ("APPROVED", "CLOSED"):
            v["execution"] = self.execution(org, bid)
        return v

    def list_budgets(self, org) -> List[dict]:
        return [self._bview(b) for b in sorted(self._all("pf_budget", org), key=lambda b: b["ref"]) if b["status"] != "DISCARDED"]

    # ------------------------------------------------------------------ virements
    def propose_virement(self, org, bid, from_account, to_account, amount, reason, actor) -> dict:
        b = self._get("pf_budget", org, bid, "Budget", for_update=True)
        if b["status"] != "APPROVED":
            raise PubFinStateError("Virements apply to approved budgets only.")
        lines = {x["account_id"]: x for x in b["lines"]}
        if from_account == to_account:
            raise PubFinError("Choose two different budget lines.")
        for k in (from_account, to_account):
            if k not in lines or lines[k]["type"] != "EXPENSE":
                raise PubFinError("A virement moves money between two expense lines of this budget.")
        amt = _dec(amount, "Amount", positive=True)
        v = {"id": uuid.uuid4().hex, "from_account": from_account, "to_account": to_account, "amount": s2(amt), "reason": _txt(reason, "Reason", 10, 1000), "status": "PROPOSED", "proposed_by": actor,
             "proposed_at": self.now().isoformat(), "decided_by": None, "decision_note": ""}
        b["virements"].append(v); self._hist(b, actor, "VIREMENT_PROPOSED", f"{s2(amt)} from {lines[from_account]['code']} to {lines[to_account]['code']}")
        self._put("pf_budget", org, b); self.log("PF_VIREMENT_PROPOSED", actor, bid, org, f"{b['ref']} {s2(amt)}")
        return self._bview(b)

    def _decide_virement(self, org, bid, vid, actor, ok, note):
        b = self._get("pf_budget", org, bid, "Budget", for_update=True)
        v = next((x for x in b["virements"] if x["id"] == vid), None)
        if v is None: raise PubFinNotFoundError("Virement not found.")
        if v["status"] != "PROPOSED": raise PubFinStateError("This virement has already been decided.")
        self._two(actor, v["proposed_by"], "proposed this virement")
        note = _txt(note, "A reason", 3 if not ok else 0, 1000, required=not ok)
        if ok:
            ex = next(r for r in self.execution(org, bid)["rows"] if r["account_id"] == v["from_account"])
            if Decimal(ex["available"]) < Decimal(v["amount"]):
                raise PubFinStateError(f"Only {ex['available']} is available on the line being reduced, so {v['amount']} cannot be moved.")
        v.update(status="APPROVED" if ok else "REJECTED", decided_by=actor, decision_note=note, decided_at=self.now().isoformat())
        self._hist(b, actor, "VIREMENT_" + v["status"], note); self._put("pf_budget", org, b); self.log("PF_VIREMENT_" + v["status"], actor, bid, org, f"{b['ref']} {v['amount']}")
        return self._bview(b)

    def approve_virement(self, org, bid, vid, actor, note="") -> dict: return self._decide_virement(org, bid, vid, actor, True, note)
    def reject_virement(self, org, bid, vid, actor, note) -> dict: return self._decide_virement(org, bid, vid, actor, False, note)

    # ------------------------------------------------------------------ commitments
    def _make_commitment(self, org, bid, account_id, vendor, description, amount, on, evidence_ids, actor, procurement_id=None) -> dict:
        b = self._get("pf_budget", org, bid, "Budget", for_update=True)
        if b["status"] != "APPROVED":
            raise PubFinStateError("Commitments can only be made against an approved budget.")
        line = next((x for x in b["lines"] if x["account_id"] == account_id), None)
        if line is None or line["type"] != "EXPENSE":
            raise PubFinError("Choose an expense line of this budget.")
        amt, d = _dec(amount, "Amount", positive=True), _date(on, "Date")
        if not (date.fromisoformat(b["start"]) <= d <= date.fromisoformat(b["end"])):
            raise PubFinError(f"The commitment date {d} is outside the budget period ({b['start']} to {b['end']}).")
        ex = next(r for r in self.execution(org, bid)["rows"] if r["account_id"] == account_id)
        if amt > Decimal(ex["available"]):
            raise PubFinStateError(f"This commitment of {s2(amt)} is more than the {ex['available']} still available on {line['code']} {line['name']}. It was not recorded.")
        c = {"id": uuid.uuid4().hex, "org": org, "ref": self._ref(org, "C"), "budget_id": bid, "budget_ref": b["ref"], "account_id": account_id, "code": line["code"], "line_name": line["name"],
             "vendor": _txt(vendor, "Vendor or payee", 2, 200), "description": _txt(description, "What it is for", 3, 500), "amount": s2(amt), "date": d.isoformat(), "status": "OPEN", "created_by": actor,
             "created_at": self.now().isoformat(), "procurement_id": procurement_id, "evidence": self._evidence(org, evidence_ids), "settled_amount": None, "settle_note": "", "history": []}
        self._hist(c, actor, "COMMITTED", s2(amt)); self._put("pf_commitment", org, c); self.log("PF_COMMITMENT_CREATED", actor, c["id"], org, f"{c['ref']} {s2(amt)} on {b['ref']}")
        return c

    def create_commitment(self, org, d, actor) -> dict:
        return self._make_commitment(org, d.get("budget_id"), d.get("account_id"), d.get("vendor"), d.get("description"), d.get("amount"), d.get("date"), d.get("evidence_ids"), actor)

    def settle_commitment(self, org, cid, settled_amount, note, actor) -> dict:
        c = self._get("pf_commitment", org, cid, "Commitment", for_update=True)
        if c["status"] != "OPEN": raise PubFinStateError("Only an open commitment can be settled.")
        c.update(status="SETTLED", settled_amount=s2(_dec(settled_amount, "Amount actually paid or invoiced", lo=0)), settle_note=_txt(note, "Note (for example the journal number)", 3, 500), settled_by=actor)
        self._hist(c, actor, "SETTLED", c["settled_amount"]); self._put("pf_commitment", org, c); self.log("PF_COMMITMENT_SETTLED", actor, cid, org, c["ref"])
        return c

    def cancel_commitment(self, org, cid, note, actor) -> dict:
        c = self._get("pf_commitment", org, cid, "Commitment", for_update=True)
        if c["status"] != "OPEN": raise PubFinStateError("Only an open commitment can be cancelled.")
        c.update(status="CANCELLED", settle_note=_txt(note, "Reason", 5, 500)); self._hist(c, actor, "CANCELLED", c["settle_note"])
        self._put("pf_commitment", org, c); self.log("PF_COMMITMENT_CANCELLED", actor, cid, org, c["ref"])
        return c

    def list_commitments(self, org, budget_id=None, status=None) -> List[dict]:
        return [c for c in sorted(self._all("pf_commitment", org), key=lambda c: c["ref"]) if (not budget_id or c["budget_id"] == budget_id) and (not status or c["status"] == status)]

    # ------------------------------------------------------------------ procurement
    def create_procurement(self, org, d, actor) -> dict:
        b = self._get("pf_budget", org, d.get("budget_id"), "Budget")
        line = next((x for x in b["lines"] if x["account_id"] == d.get("account_id") and x["type"] == "EXPENSE"), None)
        if b["status"] != "APPROVED" or line is None:
            raise PubFinError("Choose an expense line of an approved budget.")
        p = {"id": uuid.uuid4().hex, "org": org, "ref": self._ref(org, "P"), "title": _txt(d.get("title"), "What is being bought", 3, 200), "description": _txt(d.get("description"), "Details", 0, 1500, required=False),
             "budget_id": b["id"], "budget_ref": b["ref"], "account_id": line["account_id"], "code": line["code"], "estimate": s2(_dec(d.get("estimate"), "Estimated cost", positive=True)), "status": "OPEN",
             "quotes": [], "award": None, "created_by": actor, "created_at": self.now().isoformat(), "commitment_id": None, "history": []}
        self._hist(p, actor, "CREATED"); self._put("pf_procurement", org, p); self.log("PF_PROCUREMENT_CREATED", actor, p["id"], org, p["ref"])
        return p

    def add_quote(self, org, pid, vendor, amount, note, evidence_ids, actor) -> dict:
        p = self._get("pf_procurement", org, pid, "Procurement", for_update=True)
        if p["status"] != "OPEN": raise PubFinStateError("Quotes can only be added while the procurement is open.")
        v = _txt(vendor, "Vendor", 2, 200)
        if any(q["vendor"].lower() == v.lower() for q in p["quotes"]): raise PubFinError("That vendor already has a quote. Each vendor gives one quote.")
        p["quotes"].append({"id": uuid.uuid4().hex, "vendor": v, "amount": s2(_dec(amount, "Quoted amount", positive=True)), "note": _txt(note, "Note", 0, 500, required=False), "evidence": self._evidence(org, evidence_ids), "added_by": actor, "added_at": self.now().isoformat()})
        self._hist(p, actor, "QUOTE_ADDED", v); self._put("pf_procurement", org, p); self.log("PF_QUOTE_ADDED", actor, pid, org, f"{p['ref']} {v}")
        return p

    def propose_award(self, org, pid, quote_id, justification, exception_reason, actor) -> dict:
        p = self._get("pf_procurement", org, pid, "Procurement", for_update=True)
        if p["status"] != "OPEN": raise PubFinStateError("Only an open procurement can have an award proposed.")
        q = next((x for x in p["quotes"] if x["id"] == quote_id), None)
        if q is None: raise PubFinNotFoundError("Quote not found.")
        st, notes = self._settings(org), []
        if Decimal(p["estimate"]) >= Decimal(st["quote_threshold"]) and len(p["quotes"]) < st["min_quotes"]:
            if len(_txt(exception_reason, "Reason for awarding with fewer quotes than policy requires", 0, 1000, required=False)) < 20:
                raise PubFinError(f"Policy needs {st['min_quotes']} quotes for this value and there are {len(p['quotes'])}. Add quotes, or give a written exception reason (at least 20 characters).")
            notes.append("EXCEPTION: fewer quotes than policy")
        lowest = min(Decimal(x["amount"]) for x in p["quotes"])
        if Decimal(q["amount"]) > lowest:
            if len(_txt(justification, "Why not the lowest quote", 0, 1000, required=False)) < 20:
                raise PubFinError("This is not the lowest quote. Say why it was chosen (at least 20 characters).")
            notes.append("NOT LOWEST QUOTE")
        p["award"] = {"quote_id": quote_id, "vendor": q["vendor"], "amount": q["amount"], "justification": _txt(justification, "Justification", 0, 1000, required=False), "exception_reason": _txt(exception_reason, "Exception", 0, 1000, required=False),
                      "flags": notes, "proposed_by": actor, "proposed_at": self.now().isoformat(), "decided_by": None, "decision_note": ""}
        p["status"] = "AWARD_PROPOSED"; self._hist(p, actor, "AWARD_PROPOSED", f"{q['vendor']} {q['amount']}")
        self._put("pf_procurement", org, p); self.log("PF_AWARD_PROPOSED", actor, pid, org, f"{p['ref']} {q['vendor']}")
        return p

    def approve_award(self, org, pid, actor, note="") -> dict:
        p = self._get("pf_procurement", org, pid, "Procurement", for_update=True)
        if p["status"] != "AWARD_PROPOSED": raise PubFinStateError("This procurement has no award waiting for a decision.")
        self._two(actor, p["award"]["proposed_by"], "proposed this award")
        c = self._make_commitment(org, p["budget_id"], p["account_id"], p["award"]["vendor"], p["title"], p["award"]["amount"], self.today().isoformat(), [], actor, procurement_id=p["id"])
        p["award"].update(decided_by=actor, decision_note=_txt(note, "Note", 0, 1000, required=False)); p.update(status="AWARDED", commitment_id=c["id"], commitment_ref=c["ref"])
        self._hist(p, actor, "AWARDED", f"commitment {c['ref']}"); self._put("pf_procurement", org, p); self.log("PF_AWARD_APPROVED", actor, pid, org, f"{p['ref']} -> {c['ref']}")
        return p

    def reject_award(self, org, pid, actor, note) -> dict:
        p = self._get("pf_procurement", org, pid, "Procurement", for_update=True)
        if p["status"] != "AWARD_PROPOSED": raise PubFinStateError("This procurement has no award waiting for a decision.")
        self._two(actor, p["award"]["proposed_by"], "proposed this award")
        p["award"]["decision_note"] = _txt(note, "A reason", 3, 1000); p["award"]["decided_by"] = actor
        p["status"] = "OPEN"; self._hist(p, actor, "AWARD_REJECTED", p["award"]["decision_note"]); self._put("pf_procurement", org, p); self.log("PF_AWARD_REJECTED", actor, pid, org, p["ref"])
        return p

    def cancel_procurement(self, org, pid, note, actor) -> dict:
        p = self._get("pf_procurement", org, pid, "Procurement", for_update=True)
        if p["status"] not in ("OPEN", "AWARD_PROPOSED"): raise PubFinStateError("Only an open procurement can be cancelled.")
        p["status"] = "CANCELLED"; p["cancel_note"] = _txt(note, "Reason", 5, 500); self._hist(p, actor, "CANCELLED", p["cancel_note"])
        self._put("pf_procurement", org, p); self.log("PF_PROCUREMENT_CANCELLED", actor, pid, org, p["ref"])
        return p

    def list_procurements(self, org) -> List[dict]: return sorted(self._all("pf_procurement", org), key=lambda p: p["ref"])
    def get_procurement(self, org, pid) -> dict: return self._get("pf_procurement", org, pid, "Procurement")

    # ------------------------------------------------------------------ grants
    def _gview(self, g) -> dict:
        v = dict(g)
        spent = sum((Decimal(s["amount"]) for s in g["spend"] if s["status"] == "APPROVED"), ZERO)
        pending = sum((Decimal(s["amount"]) for s in g["spend"] if s["status"] == "PROPOSED"), ZERO)
        received, amt = sum((Decimal(r["amount"]) for r in g["receipts"]), ZERO), Decimal(g["amount"])
        v.update(spent=s2(spent), pending=s2(pending), received=s2(received), remaining=s2(amt - spent), utilisation_pct=s2(spent * 100 / amt), cash_on_hand=s2(received - spent),
                 overspent_vs_received=spent > received, expired=g["status"] == "ACTIVE" and date.fromisoformat(g["end"]) < self.today())
        return v

    def create_grant(self, org, d, actor) -> dict:
        s, e = _date(d.get("start"), "Start date"), _date(d.get("end"), "End date")
        if e < s: raise PubFinError("The end date cannot be before the start date.")
        g = {"id": uuid.uuid4().hex, "org": org, "ref": self._ref(org, "G"), "title": _txt(d.get("title"), "Grant title", 3, 200), "donor": _txt(d.get("donor"), "Donor or grantor", 2, 200),
             "amount": s2(_dec(d.get("amount"), "Award amount", positive=True)), "currency": _txt(d.get("currency"), "Currency", 3, 3).upper(), "start": s.isoformat(), "end": e.isoformat(),
             "restricted": bool(d.get("restricted", True)), "conditions": _txt(d.get("conditions"), "Conditions", 0, 3000, required=False), "status": "ACTIVE", "receipts": [], "spend": [],
             "created_by": actor, "created_at": self.now().isoformat(), "history": []}
        self._hist(g, actor, "CREATED"); self._put("pf_grant", org, g); self.log("PF_GRANT_CREATED", actor, g["id"], org, f"{g['ref']} {g['amount']}")
        return self._gview(g)

    def record_receipt(self, org, gid, amount, on, reference, actor) -> dict:
        g = self._get("pf_grant", org, gid, "Grant", for_update=True)
        if g["status"] != "ACTIVE": raise PubFinStateError("This grant is closed.")
        amt = _dec(amount, "Amount received", positive=True)
        if sum((Decimal(r["amount"]) for r in g["receipts"]), ZERO) + amt > Decimal(g["amount"]):
            raise PubFinStateError("Receipts would exceed the award amount. Check the amount, or the award itself.")
        g["receipts"].append({"id": uuid.uuid4().hex, "amount": s2(amt), "date": _date(on, "Date received").isoformat(), "reference": _txt(reference, "Bank or receipt reference", 2, 200), "by": actor})
        self._hist(g, actor, "RECEIPT", s2(amt)); self._put("pf_grant", org, g); self.log("PF_GRANT_RECEIPT", actor, gid, org, f"{g['ref']} {s2(amt)}")
        return self._gview(g)

    def add_spend(self, org, gid, amount, on, description, reference, evidence_ids, actor) -> dict:
        g = self._get("pf_grant", org, gid, "Grant", for_update=True)
        if g["status"] != "ACTIVE": raise PubFinStateError("This grant is closed.")
        d = _date(on, "Date of spending")
        if not (date.fromisoformat(g["start"]) <= d <= date.fromisoformat(g["end"])):
            raise PubFinError("The spending date is outside the grant period.")
        g["spend"].append({"id": uuid.uuid4().hex, "amount": s2(_dec(amount, "Amount", positive=True)), "date": d.isoformat(), "description": _txt(description, "What it was for", 3, 500), "reference": _txt(reference, "Journal or voucher reference", 0, 200, required=False),
                           "evidence": self._evidence(org, evidence_ids), "status": "PROPOSED", "proposed_by": actor, "proposed_at": self.now().isoformat(), "decided_by": None, "decision_note": ""})
        self._hist(g, actor, "SPEND_PROPOSED", g["spend"][-1]["amount"]); self._put("pf_grant", org, g); self.log("PF_GRANT_SPEND_PROPOSED", actor, gid, org, g["ref"])
        return self._gview(g)

    def _decide_spend(self, org, gid, sid, actor, ok, note):
        g = self._get("pf_grant", org, gid, "Grant", for_update=True)
        s = next((x for x in g["spend"] if x["id"] == sid), None)
        if s is None: raise PubFinNotFoundError("Spending entry not found.")
        if s["status"] != "PROPOSED": raise PubFinStateError("This spending entry has already been decided.")
        self._two(actor, s["proposed_by"], "entered this spending")
        note = _txt(note, "A reason", 3 if not ok else 0, 1000, required=not ok)
        if ok:
            spent = sum((Decimal(x["amount"]) for x in g["spend"] if x["status"] == "APPROVED"), ZERO)
            if spent + Decimal(s["amount"]) > Decimal(g["amount"]):
                raise PubFinStateError(f"Approving this would take spending to {s2(spent + Decimal(s['amount']))}, above the award of {g['amount']}.")
        s.update(status="APPROVED" if ok else "REJECTED", decided_by=actor, decision_note=note, decided_at=self.now().isoformat())
        self._hist(g, actor, "SPEND_" + s["status"], s["amount"]); self._put("pf_grant", org, g); self.log("PF_GRANT_SPEND_" + s["status"], actor, gid, org, f"{g['ref']} {s['amount']}")
        return self._gview(g)

    def approve_spend(self, org, gid, sid, actor, note="") -> dict: return self._decide_spend(org, gid, sid, actor, True, note)
    def reject_spend(self, org, gid, sid, actor, note) -> dict: return self._decide_spend(org, gid, sid, actor, False, note)

    def close_grant(self, org, gid, note, actor) -> dict:
        g = self._get("pf_grant", org, gid, "Grant", for_update=True)
        if g["status"] != "ACTIVE": raise PubFinStateError("This grant is already closed.")
        if any(s["status"] == "PROPOSED" for s in g["spend"]): raise PubFinStateError("Decide the spending entries that are waiting first.")
        g["status"] = "CLOSED"; g["close_note"] = _txt(note, "Closing note", 5, 500); self._hist(g, actor, "CLOSED", g["close_note"])
        self._put("pf_grant", org, g); self.log("PF_GRANT_CLOSED", actor, gid, org, g["ref"])
        return self._gview(g)

    def list_grants(self, org) -> List[dict]: return [self._gview(g) for g in sorted(self._all("pf_grant", org), key=lambda g: g["ref"])]
    def get_grant(self, org, gid) -> dict: return self._gview(self._get("pf_grant", org, gid, "Grant"))

    # ------------------------------------------------------------------ overview
    def overview(self, org) -> dict:
        bs, cs, ps, gs = self.list_budgets(org), self.list_commitments(org), self.list_procurements(org), self.list_grants(org)
        over = []
        for b in bs:
            if b["status"] == "APPROVED":
                ex = self.execution(org, b["id"])
                over += [{"budget_ref": b["ref"], "code": r["code"], "name": r["name"], "available": r["available"]} for r in ex["rows"] if r["overspent"]]
        return {"as_of": self.today().isoformat(), "policy": self.get_policy(org),
                "counts": {"budgets": len(bs), "budgets_approved": sum(1 for b in bs if b["status"] == "APPROVED"), "budgets_waiting": sum(1 for b in bs if b["status"] == "SUBMITTED"),
                           "commitments_open": sum(1 for c in cs if c["status"] == "OPEN"), "procurements_open": sum(1 for p in ps if p["status"] in ("OPEN", "AWARD_PROPOSED")),
                           "awards_waiting": sum(1 for p in ps if p["status"] == "AWARD_PROPOSED"), "grants_active": sum(1 for g in gs if g["status"] == "ACTIVE"),
                           "spend_waiting": sum(1 for g in gs for s in g["spend"] if s["status"] == "PROPOSED"),
                           "virements_waiting": sum(1 for b in bs for v in b["virements"] if v["status"] == "PROPOSED")},
                "overspent_lines": over, "grants_expired": [{"ref": g["ref"], "title": g["title"], "end": g["end"], "remaining": g["remaining"]} for g in gs if g["expired"]],
                "grants_overspent_vs_received": [{"ref": g["ref"], "title": g["title"], "spent": g["spent"], "received": g["received"]} for g in gs if g["overspent_vs_received"]], "limitations": LIMITATIONS}

    # ------------------------------------------------------------------ reports
    def _report(self, org, rid, for_update=False) -> dict: return self._get("pf_report", org, rid, "Report", for_update)

    def create_report(self, org, budget_id, title, actor) -> dict:
        b = self._get("pf_budget", org, budget_id, "Budget")
        if b["status"] not in ("APPROVED", "CLOSED"): raise PubFinStateError("Reports are made from an approved or closed budget.")
        r = {"id": uuid.uuid4().hex, "org": org, "ref": self._ref(org, "R"), "budget_id": budget_id, "budget_ref": b["ref"], "title": _txt(title, "Report title", 3, 200), "status": "DRAFT", "created_by": actor,
             "created_at": self.now().isoformat(), "submitted_by": None, "decided_by": None, "decision_note": "", "snapshot": None, "fingerprint": None, "version": 0, "history": []}
        self._hist(r, actor, "CREATED"); self._put("pf_report", org, r); self.log("PF_REPORT_CREATED", actor, r["id"], org, r["ref"])
        return self._rview(r)

    def _snapshot(self, org, r) -> dict:
        b = self._get("pf_budget", org, r["budget_id"], "Budget")
        return {"generated_at": self.now().isoformat(), "kind": "ACTUALS (posted ledger) and recorded commitments", "execution": self.execution(org, r["budget_id"]),
                "virements": [v for v in b["virements"] if v["status"] == "APPROVED"], "commitments": self.list_commitments(org, r["budget_id"]),
                "grants": [{k: g[k] for k in ("ref", "title", "donor", "amount", "currency", "start", "end", "status", "spent", "received", "remaining", "utilisation_pct")} for g in self.list_grants(org)],
                "budget": {k: b[k] for k in ("ref", "name", "start", "end", "currency", "fingerprint", "decided_by")}, "limitations": LIMITATIONS}

    def submit_report(self, org, rid, actor) -> dict:
        r = self._report(org, rid, for_update=True)
        if r["status"] not in ("DRAFT", "REJECTED"): raise PubFinStateError(f"A {r['status'].lower()} report cannot be submitted.")
        snap = self._snapshot(org, r)
        r.update(snapshot=snap, fingerprint=_sha(snap), status="SUBMITTED", version=r["version"] + 1, submitted_by=actor, decided_by=None, decision_note="")
        self._hist(r, actor, "SUBMITTED", f"version {r['version']}"); self._put("pf_report", org, r); self.log("PF_REPORT_SUBMITTED", actor, rid, org, r["ref"])
        return self._rview(r)

    def _decide_report(self, org, rid, actor, ok, note):
        r = self._report(org, rid, for_update=True)
        if r["status"] != "SUBMITTED": raise PubFinStateError("Only a submitted report can be approved or sent back.")
        self._two(actor, r["submitted_by"], "submitted this report")
        if ok and _sha(r["snapshot"]) != r["fingerprint"]: raise PubFinStateError("The stored report no longer matches its fingerprint. Submit it again.")
        note = _txt(note, "A reason", 3 if not ok else 0, 1000, required=not ok)
        r.update(status="APPROVED" if ok else "REJECTED", decided_by=actor, decision_note=note, decided_at=self.now().isoformat())
        self._hist(r, actor, r["status"], note); self._put("pf_report", org, r); self.log("PF_REPORT_APPROVED" if ok else "PF_REPORT_REJECTED", actor, rid, org, r["ref"])
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
    def list_reports(self, org) -> List[dict]: return [self._rview(r, False) for r in sorted(self._all("pf_report", org), key=lambda r: r["ref"])]

    def export_csv(self, org, rid, actor) -> dict:
        r = self._report(org, rid)
        if r["status"] != "APPROVED": raise PubFinStateError("Only an approved report can be exported.")
        if _sha(r["snapshot"]) != r["fingerprint"]: raise PubFinStateError("The frozen report no longer matches its fingerprint; it cannot be exported.")
        s, buf = r["snapshot"], io.StringIO(); w = csv.writer(buf, lineterminator="\n")
        def safe(v):
            v = "" if v is None else str(v)
            return "'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v
        ex = s["execution"]
        w.writerow([CONFIDENTIAL])
        for k, v in [("Report", r["title"]), ("Budget", f"{ex['ref']} {ex['name']}"), ("Period", f"{ex['start']} to {ex['end']}"), ("Currency", ex["currency"]), ("Version", r["version"]), ("Prepared by (user id)", r["submitted_by"]),
                     ("Approved by (user id)", r["decided_by"]), ("Generated at", s["generated_at"]), ("Fingerprint (SHA-256)", r["fingerprint"]), ("Basis", ex["basis"])]:
            w.writerow([k, safe(v)])
        w.writerow([]); w.writerow(["BUDGET EXECUTION"]); w.writerow(["Code", "Line", "Type", "Approved", "Adjustment", "Budget", "ACTUAL", "Committed", "Available", "Used %"])
        for x in ex["rows"]: w.writerow([x["code"], safe(x["name"]), x["type"], x["approved"], x["adjustment"], x["budget"], x["actual"], x["committed"] or "", x["available"] or "", x["used_pct"] or ""])
        t = ex["expense_totals"]; w.writerow(["", "Expense total", "", "", "", t["budget"], t["actual"], t["committed"], t["available"], ""])
        w.writerow([]); w.writerow(["COMMITMENTS"]); w.writerow(["Ref", "Line", "Vendor", "What for", "Amount", "Status", "Settled amount"])
        for c in s["commitments"]: w.writerow([c["ref"], c["code"], safe(c["vendor"]), safe(c["description"]), c["amount"], c["status"], c["settled_amount"] or ""])
        w.writerow([]); w.writerow(["GRANTS"]); w.writerow(["Ref", "Title", "Donor", "Award", "Received", "Spent (approved)", "Remaining", "Utilisation %", "Status"])
        for g in s["grants"]: w.writerow([g["ref"], safe(g["title"]), safe(g["donor"]), g["amount"], g["received"], g["spent"], g["remaining"], g["utilisation_pct"], g["status"]])
        w.writerow([]); w.writerow(["LIMITATIONS"]); [w.writerow([x]) for x in s["limitations"]]
        self.log("PF_REPORT_EXPORTED", actor, rid, org, r["ref"])
        return {"filename": f"{r['ref']}-accountability-v{r['version']}.csv", "content": buf.getvalue(), "content_type": "text/csv; charset=utf-8"}

    def options(self, org) -> dict:
        accts = [{"id": a.id, "code": a.code, "name": a.name, "type": self._atype(a)} for a in sorted(self._accounts(org).values(), key=lambda a: a.code) if self._atype(a) in ("EXPENSE", "REVENUE")]
        return {"accounts": accts, "policy": self.get_policy(org), "limitations": LIMITATIONS}
