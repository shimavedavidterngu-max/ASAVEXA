"""Insolvency (records and evidence): a case register for an insolvent estate with creditor claims, realisations, costs and an illustrative distribution.

Records (shared document store, per organisation): isv_case, isv_setting.

Principles enforced here
  * A case has a title, a currency, a description, an optional claims deadline and the order in which the four classes of claim are paid (SECURED, PREFERENTIAL, UNSECURED, SUBORDINATED, in the order a person types). It is proposed by one person and approved or rejected by a different person. The order is a typed record; ASAVEXA knows no country's law.
  * A creditor claim (a reference code, a class, the amount claimed and the basis) is lodged by one person and admitted (for an amount up to the claim) or rejected by a different person. A claim lodged after the deadline is flagged, not refused.
  * A realisation (money coming in) or a cost of the administration (money going out first) is recorded by one person and confirmed or rejected by a different person. Only confirmed entries count.
  * The distribution is worked out exactly: what is available (confirmed realisations less confirmed costs less what was already distributed) is paid class by class in the case's order; inside a class it is shared in proportion to what each admitted claim is still owed, in whole cents, every cent allocated (largest remainder, ties to the lower claim number). A person other than the proposer records a distribution; it is a recorded calculation, not a payment.
  * ASAVEXA pays no one, files nothing and applies no insolvency law, ranking rule, set-off, interest or tax. Creditor references are codes, never names.
Nothing is edited after a decision or deleted. Every step is audited by reference number only.
"""
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from typing import Callable, List

from ..wscommon import WsMixin, amount, code, currency, dt, fr, refnum, round2, txt, utc
from .errors import InsolvencyError, InsolvencyForbiddenError, InsolvencyNotFoundError, InsolvencyStateError

DEFAULTS: dict = {}
CLASSES = ["SECURED", "PREFERENTIAL", "UNSECURED", "SUBORDINATED"]
MAX_CASES = 500
MAX_CLAIMS = 2000
MAX_ENTRIES = 2000
LIMITATIONS = [
    "ASAVEXA keeps the register and works out the arithmetic. It pays no one, files nothing with any court or office, and applies no insolvency law. The order of the classes is typed by a person and approved by a different person; it may not match the law that applies.",
    "No set-off, interest, tax, retention of title, fixed or floating charge rules, employee protections, or costs priority is applied. Secured creditors are paid from the same pool as everyone else in their class unless a person records the realisation that way.",
    "Claims, realisations and costs are typed by people. A different person admitting or confirming them is a review of what was typed, not a check against documents or the real world.",
    "A recorded distribution is a calculation saved with its date. Money must be paid, and any court or office informed, by people outside ASAVEXA. A claim admitted after a distribution is paid only from later funds; earlier payments are not equalised.",
    "Creditor references are codes people choose. Keep names and personal details out of every field.",
]


def split_cents(total_cents: int, weights: List[int]) -> List[int]:
    """Share total_cents in proportion to weights, in whole cents, every cent allocated (largest remainder, ties to the earlier position)."""
    w = sum(weights)
    if w == 0 or total_cents == 0: return [0] * len(weights)
    exact = [Fraction(total_cents * x, w) for x in weights]; base = [e.numerator // e.denominator for e in exact]; left = total_cents - sum(base)
    order = sorted(range(len(weights)), key=lambda i: (-(exact[i] - base[i]), i))
    for i in order[:left]: base[i] += 1
    return base


def cents(d) -> int: return int(Decimal(str(d)).scaleb(2))
def money(c: int) -> str: return str(Decimal(c).scaleb(-2).quantize(Decimal("0.01")))


class InsolvencyService(WsMixin):
    SETTING_KIND = "isv_setting"
    DEFAULTS = DEFAULTS
    ERR, NF, ST, FB = InsolvencyError, InsolvencyNotFoundError, InsolvencyStateError, InsolvencyForbiddenError

    def __init__(self, store, vault=None, log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = utc):
        self.store, self.vault, self.log, self.now = store, vault, log, now

    # ------------------------------------------------------------------ calculation
    def _waterfall(self, c) -> dict:
        real = sum(cents(e["amount"]) for e in c["entries"] if e["status"] == "CONFIRMED" and e["entry_type"] == "REALISATION")
        cost = sum(cents(e["amount"]) for e in c["entries"] if e["status"] == "CONFIRMED" and e["entry_type"] == "COST")
        done = sum(cents(d["total"]) for d in c["distributions"]); avail = max(0, real - cost - done); left = avail; classes = []; tot_owed = tot_paid = 0
        for cl in c["priority"]:
            cs = [x for x in c["claims"] if x["status"] == "ADMITTED" and x["claim_class"] == cl and cents(x["admitted"]) - cents(x["paid"]) > 0]
            owed = [cents(x["admitted"]) - cents(x["paid"]) for x in cs]; demand = sum(owed); pay = min(left, demand); shares = split_cents(pay, owed); left -= pay; tot_owed += demand; tot_paid += pay
            classes.append({"claim_class": cl, "owed": money(demand), "paid": money(pay), "recovery_pct": str(round2(Fraction(pay, demand) * 100)) if demand else "0.00",
                            "claims": [{"no": x["no"], "creditor_ref": x["creditor_ref"], "owed": money(o), "dividend": money(s)} for x, o, s in zip(cs, owed, shares)]})
        return {"realisations": money(real), "costs": money(cost), "distributed_to_date": money(done), "available": money(avail), "costs_exceed": cost > real, "classes": classes,
                "total_owed": money(tot_owed), "total_paid": money(tot_paid), "shortfall": money(tot_owed - tot_paid), "left_over": money(left)}

    def _view(self, c) -> dict:
        v = {k: c[k] for k in c if k != "org"}; claims = []; deadline = c.get("claims_deadline")
        for x in c["claims"]:
            x = dict(x); x["owed"] = money(cents(x["admitted"]) - cents(x["paid"])) if x["status"] == "ADMITTED" else "0.00"; claims.append(x)
        v["claims"] = claims; v["entries"] = [dict(e) for e in c["entries"]]; v["distributions"] = [dict(d) for d in c["distributions"]]
        v["pending_claims"] = sum(1 for x in c["claims"] if x["status"] == "LODGED"); v["pending_entries"] = sum(1 for e in c["entries"] if e["status"] == "PROPOSED")
        v["claimed_total"] = money(sum(cents(x["amount"]) for x in c["claims"] if x["status"] != "REJECTED")); v["admitted_total"] = money(sum(cents(x["admitted"]) for x in c["claims"] if x["status"] == "ADMITTED"))
        v["waterfall"] = self._waterfall(c) if c["status"] in ("OPEN", "CLOSED") else None
        v["late_claims"] = sum(1 for x in claims if x["late"])
        return v

    # ------------------------------------------------------------------ cases
    def isv_add_case(self, org, d, actor) -> dict:
        E = InsolvencyError; title = txt(E, d.get("title"), "The title", 3, 150); desc = txt(E, d.get("description"), "The description", 10, 500); cur = currency(E, d.get("currency"))
        pr = d.get("priority")
        if pr is None: pr = list(CLASSES)
        if not isinstance(pr, list) or sorted(str(x).strip().upper() for x in pr) != sorted(CLASSES): raise E("The order must list each class once: " + ", ".join(CLASSES) + ".")
        pr = [str(x).strip().upper() for x in pr]
        dl = d.get("claims_deadline"); dl = dt(E, dl, "The claims deadline").isoformat() if dl not in (None, "") else None
        if len(self._all("isv_case", org)) >= MAX_CASES: raise InsolvencyStateError(f"At most {MAX_CASES} cases can be kept.")
        c = {"id": uuid.uuid4().hex, "org": org, "ref": None, "title": title, "description": desc, "currency": cur, "priority": pr, "claims_deadline": dl, "status": "PROPOSED", "proposed_by": actor, "proposed_at": self.now().isoformat(),
             "decided_by": None, "decided_on": None, "decision_note": None, "closed_by": None, "closed_on": None, "close_note": None, "claims": [], "entries": [], "distributions": [], "history": []}
        c["ref"] = self._ref(org, "IC"); self._hist(c, actor, "PROPOSED")
        self._put("isv_case", org, c); self.log("INSOLVENCY_CASE_PROPOSED", actor, c["id"], org, c["ref"])
        return self._view(c)

    def isv_list_cases(self, org, status=None) -> List[dict]:
        out = []
        for c in sorted(self._all("isv_case", org), key=refnum):
            if status and c["status"] != status: continue
            v = self._view(c); v["claims"] = []; v["entries"] = []; v["distributions"] = []; v["history"] = []; v["waterfall"] = None; out.append(v)
        return out

    def isv_get_case(self, org, cid) -> dict: return self._view(self._get("isv_case", org, cid, "Case"))

    def _proposed(self, org, cid) -> dict:
        c = self._get("isv_case", org, cid, "Case", for_update=True)
        if c["status"] != "PROPOSED": raise InsolvencyStateError("Only a proposed case can be decided.")
        return c

    def isv_approve_case(self, org, cid, d, actor) -> dict:
        c = self._proposed(org, cid); self._two(actor, c["proposed_by"], "proposed this case")
        note = txt(InsolvencyError, d.get("note"), "An approval note", 10, 1000, required=False)
        c.update(status="OPEN", decided_by=actor, decided_on=self.today().isoformat(), decision_note=note or None); self._hist(c, actor, "APPROVED", note)
        self._put("isv_case", org, c); self.log("INSOLVENCY_CASE_APPROVED", actor, cid, org, c["ref"])
        return self._view(c)

    def isv_reject_case(self, org, cid, reason, actor) -> dict:
        c = self._proposed(org, cid); self._two(actor, c["proposed_by"], "proposed this case")
        reason = txt(InsolvencyError, reason, "A reason", 10, 1000); c.update(status="REJECTED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=reason); self._hist(c, actor, "REJECTED", reason)
        self._put("isv_case", org, c); self.log("INSOLVENCY_CASE_REJECTED", actor, cid, org, c["ref"])
        return self._view(c)

    def _open(self, org, cid) -> dict:
        c = self._get("isv_case", org, cid, "Case", for_update=True)
        if c["status"] != "OPEN": raise InsolvencyStateError("Only an open case can be changed this way.")
        return c

    def isv_close_case(self, org, cid, reason, actor) -> dict:
        c = self._open(org, cid)
        if any(x["status"] == "LODGED" for x in c["claims"]) or any(e["status"] == "PROPOSED" for e in c["entries"]): raise InsolvencyStateError("Decide every lodged claim and proposed entry before closing the case.")
        reason = txt(InsolvencyError, reason, "A reason", 10, 1000); c.update(status="CLOSED", closed_by=actor, closed_on=self.today().isoformat(), close_note=reason); self._hist(c, actor, "CLOSED", reason)
        self._put("isv_case", org, c); self.log("INSOLVENCY_CASE_CLOSED", actor, cid, org, c["ref"])
        return self._view(c)

    # ------------------------------------------------------------------ claims
    def isv_add_claim(self, org, cid, d, actor) -> dict:
        E = InsolvencyError; c = self._open(org, cid); ref = txt(E, d.get("creditor_ref"), "The creditor reference", 2, 40); cl = code(E, d.get("claim_class"), "The class of claim", CLASSES)
        amt = amount(E, d.get("amount"), "The amount claimed"); basis = txt(E, d.get("basis"), "The basis of the claim", 10, 300)
        if len(c["claims"]) >= MAX_CLAIMS: raise InsolvencyStateError(f"A case can have at most {MAX_CLAIMS} claims.")
        late = bool(c["claims_deadline"]) and self.today() > date.fromisoformat(c["claims_deadline"])
        c["claims"].append({"no": len(c["claims"]) + 1, "creditor_ref": ref, "claim_class": cl, "amount": str(amt), "basis": basis, "admitted": "0.00", "paid": "0.00", "late": late, "status": "LODGED", "proposed_by": actor, "lodged_on": self.today().isoformat(),
                            "decided_by": None, "decided_on": None, "decision_note": None})
        self._hist(c, actor, "CLAIM_LODGED"); self._put("isv_case", org, c); self.log("INSOLVENCY_CLAIM_LODGED", actor, cid, org, f"{c['ref']} #{len(c['claims'])}")
        return self._view(c)

    def _claim(self, org, cid, no):
        c = self._open(org, cid); x, n = self._row(c, no, "claim", "claims")
        if x["status"] != "LODGED": raise InsolvencyStateError("That claim has already been decided.")
        return c, x, n

    def isv_admit_claim(self, org, cid, no, d, actor) -> dict:
        c, x, n = self._claim(org, cid, no); self._two(actor, x["proposed_by"], "lodged this claim")
        adm = amount(InsolvencyError, d.get("amount"), "The amount admitted")
        if adm > Decimal(x["amount"]): raise InsolvencyError("The amount admitted cannot be more than the amount claimed.")
        note = txt(InsolvencyError, d.get("note"), "An admission note", 10, 1000, required=False)
        x.update(status="ADMITTED", admitted=str(adm), decided_by=actor, decided_on=self.today().isoformat(), decision_note=note or None); self._hist(c, actor, "CLAIM_ADMITTED", note)
        self._put("isv_case", org, c); self.log("INSOLVENCY_CLAIM_ADMITTED", actor, cid, org, f"{c['ref']} #{n}")
        return self._view(c)

    def isv_reject_claim(self, org, cid, no, reason, actor) -> dict:
        c, x, n = self._claim(org, cid, no); self._two(actor, x["proposed_by"], "lodged this claim")
        reason = txt(InsolvencyError, reason, "A reason", 10, 1000); x.update(status="REJECTED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=reason); self._hist(c, actor, "CLAIM_REJECTED", reason)
        self._put("isv_case", org, c); self.log("INSOLVENCY_CLAIM_REJECTED", actor, cid, org, f"{c['ref']} #{n}")
        return self._view(c)

    # ------------------------------------------------------------------ realisations and costs
    def isv_add_entry(self, org, cid, d, actor) -> dict:
        E = InsolvencyError; c = self._open(org, cid); kind = code(E, d.get("entry_type"), "The entry type", ["REALISATION", "COST"]); desc = txt(E, d.get("description"), "The description", 3, 300)
        amt = amount(E, d.get("amount"), "The amount"); when = dt(E, d.get("entry_date"), "The date")
        if when > self.today() + timedelta(days=1): raise E("The date cannot be in the future.")
        if len(c["entries"]) >= MAX_ENTRIES: raise InsolvencyStateError(f"A case can have at most {MAX_ENTRIES} entries.")
        c["entries"].append({"no": len(c["entries"]) + 1, "entry_type": kind, "description": desc, "amount": str(amt), "entry_date": when.isoformat(), "status": "PROPOSED", "proposed_by": actor, "decided_by": None, "decided_on": None, "decision_note": None})
        self._hist(c, actor, "ENTRY_RECORDED"); self._put("isv_case", org, c); self.log("INSOLVENCY_ENTRY_RECORDED", actor, cid, org, f"{c['ref']} #{len(c['entries'])}")
        return self._view(c)

    def _entry(self, org, cid, no):
        c = self._open(org, cid); e, n = self._row(c, no, "entry", "entries")
        if e["status"] != "PROPOSED": raise InsolvencyStateError("That entry has already been decided.")
        return c, e, n

    def isv_confirm_entry(self, org, cid, no, d, actor) -> dict:
        c, e, n = self._entry(org, cid, no); self._two(actor, e["proposed_by"], "recorded this entry")
        note = txt(InsolvencyError, d.get("note"), "A confirmation note", 10, 1000, required=False)
        e.update(status="CONFIRMED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=note or None); self._hist(c, actor, "ENTRY_CONFIRMED", note)
        self._put("isv_case", org, c); self.log("INSOLVENCY_ENTRY_CONFIRMED", actor, cid, org, f"{c['ref']} #{n}")
        return self._view(c)

    def isv_reject_entry(self, org, cid, no, reason, actor) -> dict:
        c, e, n = self._entry(org, cid, no); self._two(actor, e["proposed_by"], "recorded this entry")
        reason = txt(InsolvencyError, reason, "A reason", 10, 1000); e.update(status="REJECTED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=reason); self._hist(c, actor, "ENTRY_REJECTED", reason)
        self._put("isv_case", org, c); self.log("INSOLVENCY_ENTRY_REJECTED", actor, cid, org, f"{c['ref']} #{n}")
        return self._view(c)

    # ------------------------------------------------------------------ distribution
    def isv_record_distribution(self, org, cid, d, actor) -> dict:
        c = self._open(org, cid); self._two(actor, c["proposed_by"], "proposed this case")
        if any(x["status"] == "LODGED" for x in c["claims"]) or any(e["status"] == "PROPOSED" for e in c["entries"]): raise InsolvencyStateError("Decide every lodged claim and proposed entry before recording a distribution.")
        note = txt(InsolvencyError, d.get("note"), "A note", 10, 1000, required=False); w = self._waterfall(c)
        if cents(w["total_paid"]) == 0: raise InsolvencyStateError("There is nothing to distribute: no funds are available, or no admitted claim is still owed.")
        lines = []
        for cl in w["classes"]:
            for x in cl["claims"]:
                if cents(x["dividend"]) > 0:
                    lines.append({"claim_no": x["no"], "claim_class": cl["claim_class"], "amount": x["dividend"]}); cc = next(k for k in c["claims"] if k["no"] == x["no"]); cc["paid"] = money(cents(cc["paid"]) + cents(x["dividend"]))
        c["distributions"].append({"no": len(c["distributions"]) + 1, "on": self.today().isoformat(), "by": actor, "note": note or None, "total": w["total_paid"], "available": w["available"], "shortfall": w["shortfall"], "lines": lines})
        self._hist(c, actor, "DISTRIBUTION_RECORDED", note); self._put("isv_case", org, c); self.log("INSOLVENCY_DISTRIBUTION_RECORDED", actor, cid, org, f"{c['ref']} #{len(c['distributions'])}")
        return self._view(c)

    # ------------------------------------------------------------------ overview
    def isv_overview(self, org) -> dict:
        vs = [self._view(c) for c in sorted(self._all("isv_case", org), key=refnum)]; op = [v for v in vs if v["status"] == "OPEN"]; att = []

        def add(kind, n, text):
            if n: att.append({"kind": kind, "count": n, "text": text})
        add("CASES_TO_APPROVE", sum(1 for v in vs if v["status"] == "PROPOSED"), "case(s) are waiting for a different person to decide them.")
        add("CLAIMS_TO_DECIDE", sum(v["pending_claims"] for v in op), "claim(s) are waiting for a different person to admit or reject them.")
        add("ENTRIES_TO_CONFIRM", sum(v["pending_entries"] for v in op), "realisation(s) or cost(s) are waiting for a different person to confirm them.")
        add("LATE_CLAIMS", sum(v["late_claims"] for v in op), "claim(s) were lodged after the claims deadline. This is for a person to look at.")
        add("COSTS_EXCEED_REALISATIONS", sum(1 for v in op if v["waterfall"]["costs_exceed"]), "case(s) have confirmed costs above confirmed realisations.")
        add("FUNDS_READY", sum(1 for v in op if v["waterfall"] and Decimal(v["waterfall"]["total_paid"]) > 0 and not v["pending_claims"] and not v["pending_entries"]), "case(s) have funds available and admitted claims still owed, ready for a distribution to be recorded.")
        cur = {}
        for v in vs:
            if v["status"] in ("OPEN", "CLOSED"):
                t = cur.setdefault(v["currency"], {"currency": v["currency"], "cases": 0, "admitted": 0, "distributed": 0}); t["cases"] += 1; t["admitted"] += cents(v["admitted_total"]); t["distributed"] += sum(cents(x["total"]) for x in v["distributions"])
        totals = [{"currency": t["currency"], "cases": t["cases"], "admitted": money(t["admitted"]), "distributed": money(t["distributed"])} for _, t in sorted(cur.items())]
        counts = {s.lower(): sum(1 for v in vs if v["status"] == s) for s in ("PROPOSED", "OPEN", "REJECTED", "CLOSED")}
        return {"counts": counts, "totals": totals, "attention": att, "limitations": LIMITATIONS}

    def isv_options(self, org) -> dict: return {"classes": CLASSES, "entry_types": ["REALISATION", "COST"], "limitations": LIMITATIONS}
