"""Impact measurement (records and evidence): programme indicators with a baseline and a target, and the readings reported against them, decided by different people.

Records (shared document store, per organisation): imp_indicator, imp_setting.

Principles enforced here
  * An indicator is a measure of a programme (a title, a programme reference code, a unit, a direction INCREASE or DECREASE, a baseline and a target value with their dates). It is proposed by one person and approved or rejected by a different person. Only an approved indicator takes readings.
  * A reading (a period-end date, a value and a source note) is recorded by one person and confirmed or rejected by a different person. Only confirmed readings count. There is at most one live reading per period end.
  * Progress is plain arithmetic, worked out exactly: (latest confirmed value - baseline) / (target - baseline). The progress expected by today is the share of the time between the two dates that has passed. Neither is evidence that a programme caused any change.
  * ASAVEXA collects no data, verifies no result and applies no framework (no logframe, no standard). Values are typed; units are never combined across indicators.
Nothing is edited after a decision or deleted. Every step is audited by reference number only.
"""
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from typing import Callable, List

from ..wscommon import WsMixin, amount, code, dt, fr, refnum, round2, txt, utc, whole
from .errors import ImpactError, ImpactForbiddenError, ImpactNotFoundError, ImpactStateError

DEFAULTS = {"tolerance_points": 10, "stale_days": 120}
DIRECTIONS = ["INCREASE", "DECREASE"]
MAX_INDICATORS = 2000
MAX_ROWS = 500
LIMITATIONS = [
    "ASAVEXA keeps indicators, readings and the arithmetic around them. It collects no data, verifies no result and applies no framework or standard.",
    "Baselines, targets and readings are typed by people. A different person confirming a reading is a review of what was typed, not a check against the real world.",
    "Progress is the share of the way from the baseline to the target. It does not show that a programme caused the change, and it says nothing about quality, equity or side effects.",
    "Progress expected by today assumes steady change between the two dates. Real programmes are rarely steady; a flag is a prompt for a person to look, not a finding.",
    "Units are kept as typed and never combined across indicators. Keep names and personal details out of every field.",
]
STATES = ("NO_DATA", "ACHIEVED", "ON_TRACK", "BEHIND", "OVERDUE")


class ImpactService(WsMixin):
    SETTING_KIND = "imp_setting"
    DEFAULTS = DEFAULTS
    ERR, NF, ST, FB = ImpactError, ImpactNotFoundError, ImpactStateError, ImpactForbiddenError

    def __init__(self, store, vault=None, log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = utc):
        self.store, self.vault, self.log, self.now = store, vault, log, now

    # ------------------------------------------------------------------ settings
    def imp_get_setting(self, org) -> dict:
        s = self._settings(org); t, d = s["tolerance_points"], s["stale_days"]
        return {"tolerance_points": t, "stale_days": d, "updated_by": s["updated_by"], "updated_at": s["updated_at"],
                "meaning": f"An indicator is flagged as behind when its progress is more than {t} percentage point(s) below the progress expected by today. A latest confirmed reading older than {d} day(s) is flagged as stale. These are your own settings, not rules."}

    def imp_set_setting(self, org, d, actor) -> dict:
        s = self._settings(org, for_update=True)
        if d.get("tolerance_points") is not None: s["tolerance_points"] = whole(ImpactError, d["tolerance_points"], "The tolerance in percentage points", 0, 100)
        if d.get("stale_days") is not None: s["stale_days"] = whole(ImpactError, d["stale_days"], "The days before a reading is stale", 1, 730)
        s.update(updated_by=actor, updated_at=self.now().isoformat()); self._put("imp_setting", org, s)
        self.log("IMPACT_SETTING_SET", actor, "settings", org, "settings")
        return self.imp_get_setting(org)

    # ------------------------------------------------------------------ views
    def _view(self, x) -> dict:
        v = {k: x[k] for k in x if k != "org"}; v["readings"] = [dict(r) for r in x["readings"]]; s = self._settings(x["org"]); today = self.today()
        v.update(latest_value=None, latest_period_end=None, progress_pct=None, expected_pct=None, state=None, stale=False, pending_readings=sum(1 for r in x["readings"] if r["status"] == "PROPOSED"),
                 confirmed_readings=sum(1 for r in x["readings"] if r["status"] == "CONFIRMED"))
        if x["status"] != "APPROVED": return v
        base, tgt = fr(x["baseline"]), fr(x["target"]); b_on, t_on = date.fromisoformat(x["baseline_date"]), date.fromisoformat(x["target_date"])
        total, passed = (t_on - b_on).days, max(0, min((today - b_on).days, (t_on - b_on).days)); expected = Fraction(passed, total) * 100; v["expected_pct"] = str(round2(expected))
        conf = [r for r in x["readings"] if r["status"] == "CONFIRMED"]
        if not conf: v["state"] = "OVERDUE" if t_on < today else "NO_DATA"; return v
        last = max(conf, key=lambda r: (r["period_end"], r["no"])); prog = (fr(last["value"]) - base) / (tgt - base) * 100
        v.update(latest_value=last["value"], latest_period_end=last["period_end"], progress_pct=str(round2(prog)), stale=(today - date.fromisoformat(last["period_end"])).days > s["stale_days"])
        v["state"] = "ACHIEVED" if prog >= 100 else ("OVERDUE" if t_on < today else ("BEHIND" if prog < expected - s["tolerance_points"] else "ON_TRACK"))
        return v

    # ------------------------------------------------------------------ indicators
    def imp_add_indicator(self, org, d, actor) -> dict:
        E = ImpactError
        title = txt(E, d.get("title"), "The title", 3, 150); prog = txt(E, d.get("programme_ref"), "The programme reference", 2, 40); unit = txt(E, d.get("unit"), "The unit", 1, 30)
        direction = code(E, d.get("direction"), "The direction", DIRECTIONS)
        base = amount(E, d.get("baseline"), "The baseline", zero_ok=True, digits=12); tgt = amount(E, d.get("target"), "The target", zero_ok=True, digits=12)
        b_on = dt(E, d.get("baseline_date"), "The baseline date"); t_on = dt(E, d.get("target_date"), "The target date")
        if t_on <= b_on: raise E("The target date must be after the baseline date.")
        if (t_on - b_on).days > 3660: raise E("The baseline and target dates can be at most ten years apart.")
        if direction == "INCREASE" and tgt <= base: raise E("For an increase the target must be higher than the baseline.")
        if direction == "DECREASE" and tgt >= base: raise E("For a decrease the target must be lower than the baseline.")
        if len(self._all("imp_indicator", org)) >= MAX_INDICATORS: raise ImpactStateError(f"The register can hold at most {MAX_INDICATORS} indicators.")
        x = {"id": uuid.uuid4().hex, "org": org, "ref": None, "title": title, "programme_ref": prog, "unit": unit, "direction": direction, "baseline": str(base), "target": str(tgt), "baseline_date": b_on.isoformat(), "target_date": t_on.isoformat(),
             "status": "PROPOSED", "proposed_by": actor, "proposed_at": self.now().isoformat(), "decided_by": None, "decided_on": None, "decision_note": None, "closed_by": None, "closed_on": None, "close_note": None, "readings": [], "history": []}
        x["ref"] = self._ref(org, "IM"); self._hist(x, actor, "PROPOSED")
        self._put("imp_indicator", org, x); self.log("IMPACT_INDICATOR_PROPOSED", actor, x["id"], org, x["ref"])
        return self._view(x)

    def imp_list_indicators(self, org, status=None) -> List[dict]:
        out = []
        for x in sorted(self._all("imp_indicator", org), key=refnum):
            if status and x["status"] != status: continue
            v = self._view(x); v["readings"] = []; v["history"] = []; out.append(v)
        return out

    def imp_get_indicator(self, org, iid) -> dict: return self._view(self._get("imp_indicator", org, iid, "Indicator"))

    def _proposed(self, org, iid) -> dict:
        x = self._get("imp_indicator", org, iid, "Indicator", for_update=True)
        if x["status"] != "PROPOSED": raise ImpactStateError("Only a proposed indicator can be decided.")
        return x

    def imp_approve_indicator(self, org, iid, d, actor) -> dict:
        x = self._proposed(org, iid); self._two(actor, x["proposed_by"], "proposed this indicator")
        note = txt(ImpactError, d.get("note"), "An approval note", 10, 1000, required=False)
        x.update(status="APPROVED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=note or None); self._hist(x, actor, "APPROVED", note)
        self._put("imp_indicator", org, x); self.log("IMPACT_INDICATOR_APPROVED", actor, iid, org, x["ref"])
        return self._view(x)

    def imp_reject_indicator(self, org, iid, reason, actor) -> dict:
        x = self._proposed(org, iid); self._two(actor, x["proposed_by"], "proposed this indicator")
        reason = txt(ImpactError, reason, "A reason", 10, 1000); x.update(status="REJECTED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=reason); self._hist(x, actor, "REJECTED", reason)
        self._put("imp_indicator", org, x); self.log("IMPACT_INDICATOR_REJECTED", actor, iid, org, x["ref"])
        return self._view(x)

    def _approved(self, org, iid) -> dict:
        x = self._get("imp_indicator", org, iid, "Indicator", for_update=True)
        if x["status"] != "APPROVED": raise ImpactStateError("Only an approved indicator can be changed this way.")
        return x

    def imp_close_indicator(self, org, iid, reason, actor) -> dict:
        x = self._approved(org, iid)
        if any(r["status"] == "PROPOSED" for r in x["readings"]): raise ImpactStateError("Decide every proposed reading before closing the indicator.")
        reason = txt(ImpactError, reason, "A reason", 10, 1000); x.update(status="CLOSED", closed_by=actor, closed_on=self.today().isoformat(), close_note=reason); self._hist(x, actor, "CLOSED", reason)
        self._put("imp_indicator", org, x); self.log("IMPACT_INDICATOR_CLOSED", actor, iid, org, x["ref"])
        return self._view(x)

    # ------------------------------------------------------------------ readings
    def imp_add_reading(self, org, iid, d, actor) -> dict:
        E = ImpactError; x = self._approved(org, iid); when = dt(E, d.get("period_end"), "The period end")
        if when > self.today() + timedelta(days=1): raise E("The period end cannot be in the future.")
        if when < date.fromisoformat(x["baseline_date"]): raise E("The period end cannot be before the baseline date.")
        value = amount(E, d.get("value"), "The value", zero_ok=True, digits=12); src = txt(E, d.get("source_note"), "The source note", 10, 500)
        if any(r["period_end"] == when.isoformat() and r["status"] in ("PROPOSED", "CONFIRMED") for r in x["readings"]): raise ImpactStateError("There is already a reading, or one waiting for a decision, for that period end.")
        if len(x["readings"]) >= MAX_ROWS: raise ImpactStateError(f"An indicator can have at most {MAX_ROWS} readings.")
        x["readings"].append({"no": len(x["readings"]) + 1, "period_end": when.isoformat(), "value": str(value), "source_note": src, "status": "PROPOSED", "proposed_by": actor, "decided_by": None, "decided_on": None, "decision_note": None})
        self._hist(x, actor, "READING_RECORDED"); self._put("imp_indicator", org, x); self.log("IMPACT_READING_RECORDED", actor, iid, org, f"{x['ref']} #{len(x['readings'])}")
        return self._view(x)

    def _reading(self, org, iid, no):
        x = self._get("imp_indicator", org, iid, "Indicator", for_update=True); r, n = self._row(x, no, "reading", "readings")
        if r["status"] != "PROPOSED": raise ImpactStateError("That reading has already been decided.")
        if x["status"] != "APPROVED": raise ImpactStateError("The indicator is not open.")
        return x, r, n

    def imp_confirm_reading(self, org, iid, no, d, actor) -> dict:
        x, r, n = self._reading(org, iid, no); self._two(actor, r["proposed_by"], "recorded this reading")
        note = txt(ImpactError, d.get("note"), "A confirmation note", 10, 1000, required=False)
        r.update(status="CONFIRMED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=note or None); self._hist(x, actor, "READING_CONFIRMED", note)
        self._put("imp_indicator", org, x); self.log("IMPACT_READING_CONFIRMED", actor, iid, org, f"{x['ref']} #{n}")
        return self._view(x)

    def imp_reject_reading(self, org, iid, no, reason, actor) -> dict:
        x, r, n = self._reading(org, iid, no); self._two(actor, r["proposed_by"], "recorded this reading")
        reason = txt(ImpactError, reason, "A reason", 10, 1000); r.update(status="REJECTED", decided_by=actor, decided_on=self.today().isoformat(), decision_note=reason); self._hist(x, actor, "READING_REJECTED", reason)
        self._put("imp_indicator", org, x); self.log("IMPACT_READING_REJECTED", actor, iid, org, f"{x['ref']} #{n}")
        return self._view(x)

    # ------------------------------------------------------------------ overview
    def imp_overview(self, org) -> dict:
        vs = [self._view(x) for x in sorted(self._all("imp_indicator", org), key=refnum)]; ap = [v for v in vs if v["status"] == "APPROVED"]; att = []

        def add(kind, n, text):
            if n: att.append({"kind": kind, "count": n, "text": text})
        add("INDICATORS_TO_APPROVE", sum(1 for v in vs if v["status"] == "PROPOSED"), "indicator(s) are waiting for a different person to decide them.")
        add("READINGS_TO_CONFIRM", sum(v["pending_readings"] for v in ap), "reading(s) are waiting for a different person to confirm them.")
        add("BEHIND_TARGET", sum(1 for v in ap if v["state"] == "BEHIND"), "indicator(s) are behind the progress expected by today.")
        add("TARGET_PASSED", sum(1 for v in ap if v["state"] == "OVERDUE"), "indicator(s) are past their target date without reaching the target.")
        add("READINGS_STALE", sum(1 for v in ap if v["stale"]), "indicator(s) have a latest confirmed reading older than your limit.")
        add("NO_READINGS", sum(1 for v in ap if v["state"] == "NO_DATA"), "approved indicator(s) have no confirmed reading yet.")
        counts = {s.lower(): sum(1 for v in vs if v["status"] == s) for s in ("PROPOSED", "APPROVED", "REJECTED", "CLOSED")}
        states = {s: sum(1 for v in ap if v["state"] == s) for s in STATES}
        return {"counts": counts, "states": states, "attention": att, "setting": self.imp_get_setting(org), "limitations": LIMITATIONS}

    def imp_options(self, org) -> dict: return {"directions": DIRECTIONS, "limitations": LIMITATIONS}
