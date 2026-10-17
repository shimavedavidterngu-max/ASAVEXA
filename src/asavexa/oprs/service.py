"""Operations research (records and evidence): a decision analysis that compares options by typed costs and yearly flows, reviewed by a different person.

Records (shared document store, per organisation): op_analysis, op_setting.

Principles enforced here
  * An analysis has a title, a purpose, a currency and a yearly discount rate, and two to eight options. Each option has an upfront cost and the net flow (benefit less running cost) for each of one to ten years. Every figure is typed by a person.
  * For every option ASAVEXA works out, exactly (fractions, never floating point): total flows, net value, the net present value (NPV) at the typed rate, the payback year, the benefit-cost ratio and the NPV at the rate two points lower and higher. Results are rounded to two decimals only for display (half away from zero).
  * The option with the highest NPV is shown as a number, not as advice. ASAVEXA recommends nothing and decides nothing.
  * An analysis is prepared, submitted, and approved or returned by a different person. After approval a person other than the submitter records the decision (which option, and why); a decision against the highest NPV is flagged, not blocked.
Nothing is edited after approval or deleted; an option is marked removed with a reason. Every step is audited by reference number only.
"""
import uuid
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from typing import Callable, List

from ..wscommon import WsMixin, amount, currency, fr, refnum, round2, txt, utc, whole
from .errors import OprsError, OprsForbiddenError, OprsNotFoundError, OprsStateError

DEFAULTS: dict = {}
MAX_ANALYSES = 1000
MAX_OPTIONS = 8
MAX_YEARS = 10
LIMITATIONS = [
    "ASAVEXA works out the numbers from the figures people type in. It forecasts nothing, checks no cost or flow against the real world and applies no investment, public-sector or accounting standard.",
    "The highest NPV is a number, not advice. Risk, timing, funding, people and everything not typed in are left out; the person who decides must weigh them.",
    "Flows are the net amount for each whole year, discounted at the end of the year. Mid-year timing, inflation, tax and currency changes are not modelled. Option names and figures are not personal data; keep names of people out of every field.",
    "A decision by a different person is a review of what was typed, not a check of the decision itself. An approved analysis is final; a changed assumption is a new analysis.",
]
STATES = ("DRAFT", "SUBMITTED", "APPROVED", "RETURNED", "WITHDRAWN")


def npv(upfront: Fraction, flows: List[Fraction], rate: Fraction) -> Fraction:
    return -upfront + sum((f / (1 + rate) ** (i + 1) for i, f in enumerate(flows)), Fraction(0))


class OprsService(WsMixin):
    SETTING_KIND = "op_setting"
    DEFAULTS = DEFAULTS
    ERR, NF, ST, FB = OprsError, OprsNotFoundError, OprsStateError, OprsForbiddenError

    def __init__(self, store, vault=None, log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = utc):
        self.store, self.vault, self.log, self.now = store, vault, log, now

    # ------------------------------------------------------------------ calculation
    def _active(self, a) -> list: return [o for o in a["options"] if o["status"] == "ACTIVE"]

    def _results(self, a) -> list:
        rate = fr(a["discount_rate"]) / 100; out = []
        for o in self._active(a):
            up, fl = fr(o["upfront_cost"]), [fr(x) for x in o["flows"]]; total = sum(fl, Fraction(0)); cum = Fraction(0); pay = None
            for i, f in enumerate(fl):
                cum += f
                if pay is None and cum >= up: pay = i + 1
            sens = []
            for pts in (-2, 0, 2):
                r = fr(a["discount_rate"]) + pts
                if r >= 0: sens.append({"rate": str(round2(r)), "npv": str(round2(npv(up, fl, r / 100)))})
            out.append({"no": o["no"], "name": o["name"], "upfront_cost": o["upfront_cost"], "years": len(fl), "total_flows": str(round2(total)), "net_value": str(round2(total - up)),
                        "npv": str(round2(npv(up, fl, rate))), "payback_year": pay, "benefit_cost_ratio": str(round2(total / up)), "sensitivity": sens, "_npv": npv(up, fl, rate)})
        best = max((r["_npv"] for r in out), default=None); ranked = sorted(out, key=lambda r: (-r["_npv"], r["no"]))
        for r in out:
            r["rank"] = 1 + sum(1 for x in out if x["_npv"] > r["_npv"]); r["highest_npv"] = best is not None and r["_npv"] == best
        for r in out: del r["_npv"]
        return out

    def _view(self, a) -> dict:
        v = {x: a[x] for x in a if x != "org"}; v["options"] = [dict(o) for o in a["options"]]; v["results"] = self._results(a) if self._active(a) else []
        v["active_options"] = len(self._active(a)); d = a.get("decision")
        v["decision_flag"] = bool(d) and not next((r for r in v["results"] if r["no"] == d["option_no"]), {}).get("highest_npv", True)
        return v

    # ------------------------------------------------------------------ analyses
    def op_create_analysis(self, org, d, actor) -> dict:
        E = OprsError; title = txt(E, d.get("title"), "The title", 3, 150); purpose = txt(E, d.get("purpose"), "The purpose", 10, 500); cur = currency(E, d.get("currency"))
        rate = amount(E, d.get("discount_rate"), "The discount rate (percent a year)", zero_ok=True, dp=2, digits=3)
        if rate > 100: raise E("The discount rate cannot be more than 100 percent.")
        if len(self._all("op_analysis", org)) >= MAX_ANALYSES: raise OprsStateError(f"At most {MAX_ANALYSES} analyses can be kept.")
        a = {"id": uuid.uuid4().hex, "org": org, "ref": None, "title": title, "purpose": purpose, "currency": cur, "discount_rate": str(rate), "status": "DRAFT", "options": [], "created_by": actor, "created_at": self.now().isoformat(),
             "note": None, "submitted_by": None, "submitted_on": None, "decided_by": None, "decided_on": None, "decision_note": None, "decision": None, "history": []}
        a["ref"] = self._ref(org, "OA"); self._hist(a, actor, "CREATED")
        self._put("op_analysis", org, a); self.log("OPRS_ANALYSIS_CREATED", actor, a["id"], org, a["ref"])
        return self._view(a)

    def op_list_analyses(self, org, status=None) -> List[dict]:
        out = []
        for a in sorted(self._all("op_analysis", org), key=refnum):
            if status and a["status"] != status: continue
            v = self._view(a); v["options"] = []; v["results"] = []; v["history"] = []; out.append(v)
        return out

    def op_get_analysis(self, org, aid) -> dict: return self._view(self._get("op_analysis", org, aid, "Analysis"))

    def _editable(self, org, aid) -> dict:
        a = self._get("op_analysis", org, aid, "Analysis", for_update=True)
        if a["status"] not in ("DRAFT", "RETURNED"): raise OprsStateError("Only a draft or returned analysis can be changed.")
        return a

    def op_add_option(self, org, aid, d, actor) -> dict:
        E = OprsError; a = self._editable(org, aid); name = txt(E, d.get("name"), "The option name", 2, 100)
        up = amount(E, d.get("upfront_cost"), "The upfront cost"); flows = d.get("flows")
        if not isinstance(flows, list) or not 1 <= len(flows) <= MAX_YEARS: raise E(f"Give the net flow for each year, from 1 to {MAX_YEARS} years, as a list.")
        fl = [amount(E, x, f"The flow for year {i + 1}", zero_ok=True, neg=True) for i, x in enumerate(flows)]
        if any(o["status"] == "ACTIVE" and o["name"].lower() == name.lower() for o in a["options"]): raise OprsStateError("An option with that name is already in this analysis.")
        if self._active(a) and len(self._active(a)) >= MAX_OPTIONS: raise OprsStateError(f"An analysis can compare at most {MAX_OPTIONS} options.")
        if len(a["options"]) >= MAX_OPTIONS * 4: raise OprsStateError("This analysis has had too many options added and removed.")
        a["options"].append({"no": len(a["options"]) + 1, "name": name, "upfront_cost": str(up), "flows": [str(x) for x in fl], "status": "ACTIVE", "removed_by": None, "removed_note": None})
        self._hist(a, actor, "OPTION_ADDED"); self._put("op_analysis", org, a); self.log("OPRS_OPTION_ADDED", actor, aid, org, f"{a['ref']} #{len(a['options'])}")
        return self._view(a)

    def op_remove_option(self, org, aid, no, reason, actor) -> dict:
        a = self._editable(org, aid); o, n = self._row(a, no, "option", "options")
        if o["status"] != "ACTIVE": raise OprsStateError("That option has already been removed.")
        reason = txt(OprsError, reason, "A reason", 10, 1000); o.update(status="REMOVED", removed_by=actor, removed_note=reason); self._hist(a, actor, "OPTION_REMOVED", reason)
        self._put("op_analysis", org, a); self.log("OPRS_OPTION_REMOVED", actor, aid, org, f"{a['ref']} #{n}")
        return self._view(a)

    def op_submit(self, org, aid, d, actor) -> dict:
        a = self._editable(org, aid)
        if len(self._active(a)) < 2: raise OprsStateError("Add at least two options to compare before submitting.")
        note = txt(OprsError, d.get("note"), "The note for the approver", 10, 2000, required=False)
        a.update(status="SUBMITTED", note=note or None, submitted_by=actor, submitted_on=self.today().isoformat(), decided_by=None, decided_on=None, decision_note=None); self._hist(a, actor, "SUBMITTED")
        self._put("op_analysis", org, a); self.log("OPRS_ANALYSIS_SUBMITTED", actor, aid, org, a["ref"])
        return self._view(a)

    def op_withdraw(self, org, aid, reason, actor) -> dict:
        a = self._editable(org, aid); reason = txt(OprsError, reason, "A reason", 10, 1000)
        a.update(status="WITHDRAWN", decision_note=reason); self._hist(a, actor, "WITHDRAWN", reason)
        self._put("op_analysis", org, a); self.log("OPRS_ANALYSIS_WITHDRAWN", actor, aid, org, a["ref"])
        return self._view(a)

    def _submitted(self, org, aid) -> dict:
        a = self._get("op_analysis", org, aid, "Analysis", for_update=True)
        if a["status"] != "SUBMITTED": raise OprsStateError("Only a submitted analysis can be decided.")
        return a

    def op_approve(self, org, aid, d, actor) -> dict:
        a = self._submitted(org, aid); self._two(actor, a["submitted_by"], "submitted this analysis")
        note = txt(OprsError, d.get("note"), "An approval note", 10, 1000, required=False)
        a.update(status="APPROVED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=note or None); self._hist(a, actor, "APPROVED", note)
        self._put("op_analysis", org, a); self.log("OPRS_ANALYSIS_APPROVED", actor, aid, org, a["ref"])
        return self._view(a)

    def op_return(self, org, aid, reason, actor) -> dict:
        a = self._submitted(org, aid); self._two(actor, a["submitted_by"], "submitted this analysis")
        reason = txt(OprsError, reason, "A reason", 10, 1000); a.update(status="RETURNED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=reason); self._hist(a, actor, "RETURNED", reason)
        self._put("op_analysis", org, a); self.log("OPRS_ANALYSIS_RETURNED", actor, aid, org, a["ref"])
        return self._view(a)

    def op_decide(self, org, aid, d, actor) -> dict:
        a = self._get("op_analysis", org, aid, "Analysis", for_update=True)
        if a["status"] != "APPROVED": raise OprsStateError("A decision can be recorded only on an approved analysis.")
        if a.get("decision"): raise OprsStateError("A decision has already been recorded.")
        self._two(actor, a["submitted_by"], "submitted this analysis")
        n = whole(OprsError, d.get("option_no"), "The option number", 1, 999); o = next((x for x in a["options"] if x["no"] == n and x["status"] == "ACTIVE"), None)
        if o is None: raise OprsNotFoundError("Option not found.")
        why = txt(OprsError, d.get("rationale"), "The rationale", 10, 1000)
        a["decision"] = {"option_no": n, "option_name": o["name"], "rationale": why, "by": actor, "on": self.today().isoformat()}; self._hist(a, actor, "DECISION_RECORDED", why)
        self._put("op_analysis", org, a); self.log("OPRS_DECISION_RECORDED", actor, aid, org, f"{a['ref']} #{n}")
        return self._view(a)

    # ------------------------------------------------------------------ overview
    def op_overview(self, org) -> dict:
        vs = [self._view(a) for a in sorted(self._all("op_analysis", org), key=refnum)]; att = []

        def add(kind, n, text):
            if n: att.append({"kind": kind, "count": n, "text": text})
        add("ANALYSES_TO_REVIEW", sum(1 for v in vs if v["status"] == "SUBMITTED"), "analysis(es) are waiting for a different person to review them.")
        add("ANALYSES_RETURNED", sum(1 for v in vs if v["status"] == "RETURNED"), "analysis(es) were returned and need changes.")
        add("DECISIONS_NEEDED", sum(1 for v in vs if v["status"] == "APPROVED" and not v["decision"]), "approved analysis(es) have no decision recorded yet.")
        add("DECISION_NOT_HIGHEST_NPV", sum(1 for v in vs if v["decision_flag"]), "decision(s) chose an option that did not have the highest NPV. This is for a person to look at, not an error.")
        counts = {s.lower(): sum(1 for v in vs if v["status"] == s) for s in STATES}; cur = {}
        for v in vs:
            if v["status"] == "APPROVED": cur[v["currency"]] = cur.get(v["currency"], 0) + 1
        return {"counts": counts, "approved_by_currency": [{"currency": c, "analyses": n} for c, n in sorted(cur.items())], "decisions_recorded": sum(1 for v in vs if v["decision"]), "attention": att, "limitations": LIMITATIONS}

    def op_options(self, org) -> dict: return {"max_options": MAX_OPTIONS, "max_years": MAX_YEARS, "limitations": LIMITATIONS}
