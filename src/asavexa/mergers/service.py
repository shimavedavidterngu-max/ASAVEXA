"""Mergers and acquisitions (records and evidence): deals with a due-diligence checklist, closing conditions and price adjustments, each recorded by one person and confirmed by a different person.

Records (shared document store, per organisation): ma_deal, ma_setting.

Principles enforced here
  * A deal has a name, a reference code (a codename, never a party's name), a currency, a type (acquisition, merger, disposal, other), a base price, a target closing date and a description. It is proposed by one person and approved or rejected by a different person. Only an approved deal takes records.
  * A due-diligence checklist item (a title and an area) and a closing condition (a title and a due date) are added by one person, marked as provided or met by a person (with a date and a note) and confirmed by a different person than the one who marked it; a rejection sends it back to open with the reason kept. Checklist progress is plain arithmetic: confirmed items over all items, exactly.
  * A price adjustment (an increase or a decrease, an amount and the basis) is recorded by one person and confirmed or rejected by a different person. The adjusted price is the base price plus confirmed increases less confirmed decreases, exactly. An adjustment that would take the price below zero cannot be confirmed.
  * An approver closes a deal as COMPLETED or ABANDONED with a reason once nothing waits for a decision. COMPLETED also needs every checklist item and condition confirmed.
  * ASAVEXA values nothing, reads no contract and gives no deal, tax or legal advice. Party references are codes, never names.
Nothing is edited after a decision or deleted. Every step is audited by reference number only.
"""
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from typing import Callable, List

from ..wscommon import WsMixin, amount, code, currency, dt, fr, refnum, round2, txt, utc, whole
from .errors import MergersError, MergersForbiddenError, MergersNotFoundError, MergersStateError

DEFAULTS = {"due_soon_days": 14}
TYPES = ["ACQUISITION", "MERGER", "DISPOSAL", "OTHER"]
AREAS = ["FINANCIAL", "LEGAL", "TAX", "COMMERCIAL", "OPERATIONAL", "OTHER"]
KINDS_ADJ = ["INCREASE", "DECREASE"]
OUTCOMES = ["COMPLETED", "ABANDONED"]
KINDS = {"checklist": "checklist item", "conditions": "condition", "adjustments": "adjustment"}
STEPS = ("checklist", "conditions")
MAX_DEALS = 500
MAX_ROWS = 500
LIMITATIONS = [
    "ASAVEXA keeps a register and works out plain arithmetic. It values nothing, reads no contract and gives no deal, tax or legal advice.",
    "Prices, adjustments, checklist items and conditions are typed by people. A different person confirming one is a review of what was typed, not a check against documents or the other party.",
    "The adjusted price is the base price plus confirmed increases less confirmed decreases. Real agreements may use completion accounts, earn-outs, escrow or currency terms that are not applied here.",
    "A checklist at 100 percent shows that every item typed has been confirmed. It does not show that the due diligence was complete or that nothing was missed.",
    "Party references are codes people choose. Keep names, personal details and confidential terms out of every field.",
]


class MergersService(WsMixin):
    SETTING_KIND = "ma_setting"
    DEFAULTS = DEFAULTS
    ERR, NF, ST, FB = MergersError, MergersNotFoundError, MergersStateError, MergersForbiddenError

    def __init__(self, store, vault=None, log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = utc):
        self.store, self.vault, self.log, self.now = store, vault, log, now

    # ------------------------------------------------------------------ settings
    def ma_get_setting(self, org) -> dict:
        s = self._settings(org); d = s["due_soon_days"]
        return {"due_soon_days": d, "updated_by": s["updated_by"], "updated_at": s["updated_at"],
                "meaning": f"An open closing condition is flagged as due soon when it falls due within {d} day(s). This is your own setting, not a rule."}

    def ma_set_setting(self, org, d, actor) -> dict:
        s = self._settings(org, for_update=True)
        if d.get("due_soon_days") is not None: s["due_soon_days"] = whole(MergersError, d["due_soon_days"], "The days that count as due soon", 1, 365)
        s.update(updated_by=actor, updated_at=self.now().isoformat()); self._put("ma_setting", org, s)
        self.log("MERGERS_SETTING_SET", actor, "settings", org, "settings")
        return self.ma_get_setting(org)

    # ------------------------------------------------------------------ views
    def _view(self, x) -> dict:
        v = {k: x[k] for k in x if k != "org"}
        for k in KINDS: v[k] = [dict(r) for r in x[k]]
        today = self.today(); soon = self._settings(x["org"])["due_soon_days"]; q = Decimal("0.01")
        for r in v["conditions"]:
            r["overdue"] = r["status"] == "OPEN" and date.fromisoformat(r["due_date"]) < today
            r["due_soon"] = r["status"] == "OPEN" and not r["overdue"] and (date.fromisoformat(r["due_date"]) - today).days <= soon
        v["pending"] = sum(1 for k, w in (("checklist", "DONE"), ("conditions", "DONE"), ("adjustments", "PROPOSED")) for r in v[k] if r["status"] == w)
        up = sum((Decimal(r["amount"]) for r in v["adjustments"] if r["status"] == "CONFIRMED" and r["kind"] == "INCREASE"), Decimal("0"))
        down = sum((Decimal(r["amount"]) for r in v["adjustments"] if r["status"] == "CONFIRMED" and r["kind"] == "DECREASE"), Decimal("0"))
        base = Decimal(x["base_price"]); adj = base + up - down; chg = adj - base
        cl = v["checklist"]; ct = len(cl); cc = sum(1 for r in cl if r["status"] == "CONFIRMED")
        by_area = {a: {"total": sum(1 for r in cl if r["area"] == a), "confirmed": sum(1 for r in cl if r["area"] == a and r["status"] == "CONFIRMED")} for a in AREAS if any(r["area"] == a for r in cl)}
        co = v["conditions"]
        v.update(adjusted_price=str(adj.quantize(q)), price_change=str(chg.quantize(q)), price_change_pct=str(round2(fr(chg) / fr(base) * 100)),
                 checklist_total=ct, checklist_confirmed=cc, checklist_pct=str(round2(Fraction(cc, ct) * 100)) if ct else None, by_area=by_area,
                 conditions_total=len(co), conditions_confirmed=sum(1 for r in co if r["status"] == "CONFIRMED"), overdue_conditions=sum(1 for r in co if r["overdue"]), due_soon_conditions=sum(1 for r in co if r["due_soon"]),
                 open_checklist=sum(1 for r in cl if r["status"] == "OPEN"), target_passed=x["status"] == "APPROVED" and date.fromisoformat(x["target_close_date"]) < today)
        return v

    def _summary(self, x) -> dict:
        v = self._view(x)
        for k in KINDS: v[k] = []
        v["history"] = []
        return v

    # ------------------------------------------------------------------ deals
    def ma_add_deal(self, org, d, actor) -> dict:
        E = MergersError
        name = txt(E, d.get("name"), "The deal name", 3, 150); dref = txt(E, d.get("deal_ref"), "The deal reference", 2, 40); cur = currency(E, d.get("currency")); typ = code(E, d.get("deal_type"), "The deal type", TYPES)
        price = amount(E, d.get("base_price"), "The base price", digits=15); target = dt(E, d.get("target_close_date"), "The target closing date")
        if not 2000 <= target.year <= 2100: raise E("The target closing date must be between 2000 and 2100.")
        desc = txt(E, d.get("description"), "The description", 10, 1000)
        if len(self._all("ma_deal", org)) >= MAX_DEALS: raise MergersStateError(f"The register can hold at most {MAX_DEALS} deals.")
        x = {"id": uuid.uuid4().hex, "org": org, "ref": None, "name": name, "deal_ref": dref, "currency": cur, "deal_type": typ, "base_price": str(price), "target_close_date": target.isoformat(), "description": desc,
             "status": "PROPOSED", "proposed_by": actor, "proposed_at": self.now().isoformat(), "decided_by": None, "decided_on": None, "decision_note": None, "closed_by": None, "closed_on": None, "outcome": None, "close_note": None,
             "checklist": [], "conditions": [], "adjustments": [], "history": []}
        x["ref"] = self._ref(org, "MD"); self._hist(x, actor, "PROPOSED")
        self._put("ma_deal", org, x); self.log("MERGERS_DEAL_PROPOSED", actor, x["id"], org, x["ref"])
        return self._view(x)

    def ma_list_deals(self, org, status=None) -> List[dict]:
        return [self._summary(x) for x in sorted(self._all("ma_deal", org), key=refnum) if not status or x["status"] == status]

    def ma_get_deal(self, org, did) -> dict: return self._view(self._get("ma_deal", org, did, "Deal"))

    def _proposed(self, org, did) -> dict:
        x = self._get("ma_deal", org, did, "Deal", for_update=True)
        if x["status"] != "PROPOSED": raise MergersStateError("Only a proposed deal can be decided.")
        return x

    def ma_approve_deal(self, org, did, d, actor) -> dict:
        x = self._proposed(org, did); self._two(actor, x["proposed_by"], "proposed this deal")
        note = txt(MergersError, d.get("note"), "An approval note", 10, 1000, required=False)
        x.update(status="APPROVED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=note or None); self._hist(x, actor, "APPROVED", note)
        self._put("ma_deal", org, x); self.log("MERGERS_DEAL_APPROVED", actor, did, org, x["ref"])
        return self._view(x)

    def ma_reject_deal(self, org, did, reason, actor) -> dict:
        x = self._proposed(org, did); self._two(actor, x["proposed_by"], "proposed this deal")
        reason = txt(MergersError, reason, "A reason", 10, 1000); x.update(status="REJECTED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=reason); self._hist(x, actor, "REJECTED", reason)
        self._put("ma_deal", org, x); self.log("MERGERS_DEAL_REJECTED", actor, did, org, x["ref"])
        return self._view(x)

    def _approved(self, org, did) -> dict:
        x = self._get("ma_deal", org, did, "Deal", for_update=True)
        if x["status"] != "APPROVED": raise MergersStateError("Only an approved deal can be changed this way.")
        return x

    def ma_close_deal(self, org, did, d, actor) -> dict:
        E = MergersError; x = self._approved(org, did); outcome = code(E, d.get("outcome"), "The outcome", OUTCOMES); reason = txt(E, d.get("reason"), "A reason", 10, 1000)
        if self._view(x)["pending"]: raise MergersStateError("Decide every item waiting for a decision before closing the deal.")
        if outcome == "COMPLETED" and any(r["status"] != "CONFIRMED" for k in STEPS for r in x[k]): raise MergersStateError("A deal can be completed only when every checklist item and condition is confirmed.")
        x.update(status="CLOSED", outcome=outcome, closed_by=actor, closed_on=self.today().isoformat(), close_note=reason); self._hist(x, actor, f"CLOSED_{outcome}", reason)
        self._put("ma_deal", org, x); self.log("MERGERS_DEAL_CLOSED", actor, did, org, x["ref"])
        return self._view(x)

    # ------------------------------------------------------------------ records
    def _append(self, x, kind, row, actor, org, label):
        if len(x[kind]) >= MAX_ROWS: raise MergersStateError(f"A deal can have at most {MAX_ROWS} {kind}.")
        row["no"] = len(x[kind]) + 1; x[kind].append(row); self._hist(x, actor, f"{label}_ADDED"); self._put("ma_deal", org, x)
        self.log(f"MERGERS_{label}_ADDED", actor, x["id"], org, f"{x['ref']} #{row['no']}")
        return self._view(x)

    def ma_add_checklist(self, org, did, d, actor) -> dict:
        E = MergersError; x = self._approved(org, did); title = txt(E, d.get("title"), "The title", 3, 200); area = code(E, d.get("area"), "The area", AREAS)
        if any(r["title"].lower() == title.lower() and r["area"] == area and r["status"] != "CONFIRMED" for r in x["checklist"]): raise MergersStateError("That checklist item is already open.")
        row = {"title": title, "area": area, "status": "OPEN", "proposed_by": actor, "done_on": None, "done_by": None, "done_note": None, "decided_by": None, "decided_on": None, "decision_note": None}
        return self._append(x, "checklist", row, actor, org, "CHECKLIST")

    def ma_add_condition(self, org, did, d, actor) -> dict:
        E = MergersError; x = self._approved(org, did); title = txt(E, d.get("title"), "The title", 3, 200); due = dt(E, d.get("due_date"), "The due date")
        if not 2000 <= due.year <= 2100: raise E("The due date must be between 2000 and 2100.")
        if any(r["title"].lower() == title.lower() and r["due_date"] == due.isoformat() and r["status"] != "CONFIRMED" for r in x["conditions"]): raise MergersStateError("That condition is already open for that date.")
        row = {"title": title, "due_date": due.isoformat(), "status": "OPEN", "proposed_by": actor, "done_on": None, "done_by": None, "done_note": None, "decided_by": None, "decided_on": None, "decision_note": None}
        return self._append(x, "conditions", row, actor, org, "CONDITION")

    def ma_add_adjustment(self, org, did, d, actor) -> dict:
        E = MergersError; x = self._approved(org, did); kind = code(E, d.get("kind"), "The kind of adjustment", KINDS_ADJ); amt = amount(E, d.get("amount"), "The amount", digits=15); basis = txt(E, d.get("basis"), "The basis", 10, 500)
        row = {"kind": kind, "amount": str(amt), "basis": basis, "status": "PROPOSED", "proposed_by": actor, "decided_by": None, "decided_on": None, "decision_note": None}
        return self._append(x, "adjustments", row, actor, org, "ADJUSTMENT")

    def ma_provide(self, org, did, kind, no, d, actor) -> dict:
        """Mark a checklist item as provided, or a condition as met."""
        E = MergersError
        if not isinstance(kind, str) or kind not in STEPS: raise E("That kind of record does not exist.")
        x = self._approved(org, did); label = KINDS[kind]; r, n = self._row(x, no, label, kind)
        if r["status"] != "OPEN": raise MergersStateError(f"Only an open {label} can be marked.")
        on = dt(E, d.get("done_on"), "The date")
        if on > self.today() + timedelta(days=1): raise E("The date cannot be in the future.")
        if on.year < 2000: raise E("The date must be in this century.")
        note = txt(E, d.get("note"), "A note", 10, 500)
        r.update(status="DONE", done_on=on.isoformat(), done_by=actor, done_note=note); ev = "CHECKLIST_PROVIDED" if kind == "checklist" else "CONDITION_MET"
        self._hist(x, actor, ev, note); self._put("ma_deal", org, x); self.log(f"MERGERS_{ev}", actor, did, org, f"{x['ref']} #{n}")
        return self._view(x)

    def ma_decide(self, org, did, kind, no, ok, note, actor) -> dict:
        """Confirm (ok) or reject a provided checklist item, a met condition or a price adjustment; never the person who recorded it."""
        if not isinstance(kind, str) or kind not in KINDS: raise MergersError("That kind of record does not exist.")
        label = KINDS[kind]; x = self._get("ma_deal", org, did, "Deal", for_update=True)
        if x["status"] != "APPROVED": raise MergersStateError("The deal is not open.")
        r, n = self._row(x, no, label, kind); step = kind in STEPS
        if r["status"] != ("DONE" if step else "PROPOSED"): raise MergersStateError(f"That {label} is not waiting for a decision.")
        self._two(actor, r["done_by"] if step else r["proposed_by"], "marked this " + label if step else "recorded this adjustment")
        stem = {"checklist": "CHECKLIST", "conditions": "CONDITION", "adjustments": "ADJUSTMENT"}[kind]
        if ok:
            text = txt(MergersError, note.get("note") if isinstance(note, dict) else note, "A confirmation note", 10, 1000, required=False)
            if kind == "adjustments" and r["kind"] == "DECREASE" and Decimal(self._view(x)["adjusted_price"]) - Decimal(r["amount"]) < 0: raise MergersStateError("Confirming this decrease would take the adjusted price below zero.")
            r.update(status="CONFIRMED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=text or None); ev = f"{stem}_CONFIRMED"
        else:
            text = txt(MergersError, note, "A reason", 10, 1000)
            r.update(status="OPEN" if step else "REJECTED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=text); ev = f"{stem}_REJECTED"
            if step: r.update(done_on=None, done_by=None, done_note=None)
        self._hist(x, actor, ev, text); self._put("ma_deal", org, x); self.log(f"MERGERS_{ev}", actor, did, org, f"{x['ref']} #{n}")
        return self._view(x)

    # ------------------------------------------------------------------ overview
    def ma_overview(self, org) -> dict:
        vs = [self._view(x) for x in sorted(self._all("ma_deal", org), key=refnum)]; ap = [v for v in vs if v["status"] == "APPROVED"]; att = []

        def add(kind, n, text):
            if n: att.append({"kind": kind, "count": n, "text": text})
        add("DEALS_TO_APPROVE", sum(1 for v in vs if v["status"] == "PROPOSED"), "deal(s) are waiting for a different person to decide them.")
        add("ITEMS_TO_DECIDE", sum(v["pending"] for v in ap), "recorded item(s) are waiting for a different person to decide them.")
        add("CHECKLIST_OPEN", sum(v["open_checklist"] for v in ap), "due-diligence checklist item(s) are still open.")
        add("CONDITIONS_OVERDUE", sum(v["overdue_conditions"] for v in ap), "closing condition(s) are open and past their due date.")
        add("CONDITIONS_DUE_SOON", sum(v["due_soon_conditions"] for v in ap), "closing condition(s) fall due soon.")
        add("TARGET_DATE_PASSED", sum(1 for v in ap if v["target_passed"]), "open deal(s) are past their target closing date.")
        counts = {s.lower(): sum(1 for v in vs if v["status"] == s) for s in ("PROPOSED", "APPROVED", "REJECTED", "CLOSED")}
        outcomes = {o.lower(): sum(1 for v in vs if v["outcome"] == o) for o in OUTCOMES}; roll = {}
        for v in ap:
            t = roll.setdefault(v["currency"], {"currency": v["currency"], "deals": 0, "base_price": Decimal("0"), "adjusted_price": Decimal("0")}); t["deals"] += 1; t["base_price"] += Decimal(v["base_price"]); t["adjusted_price"] += Decimal(v["adjusted_price"])
        q = Decimal("0.01"); by_cur = [{**t, "base_price": str(t["base_price"].quantize(q)), "adjusted_price": str(t["adjusted_price"].quantize(q))} for t in sorted(roll.values(), key=lambda t: t["currency"])]
        return {"counts": counts, "outcomes": outcomes, "attention": att, "by_currency": by_cur, "setting": self.ma_get_setting(org), "limitations": LIMITATIONS}

    def ma_options(self, org) -> dict: return {"deal_types": TYPES, "areas": AREAS, "adjustment_kinds": KINDS_ADJ, "outcomes": OUTCOMES, "limitations": LIMITATIONS}
