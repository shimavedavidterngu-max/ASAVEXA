"""Financial-crime casework (records and evidence): alerts, cases, conflict declarations, timeline, screening records, two-person decisions, loss and recovery.

Records (shared document store, per organisation): fc_alert, fc_case, fc_setting.

Principles enforced here
  * Nobody works or decides a case without first declaring, on that case, whether they have a conflict of interest. A declared conflict keeps a person off the case;
    a conflict declaration is never withdrawn.
  * One lead investigator works a case. The person who decides it is a different person: not the lead, not the one who opened it, not the one who proposed the outcome
    and not anyone who raised an alert that is part of it.
  * A screening result is typed in by the investigator. ASAVEXA does not screen anyone against any list. A possible match must be resolved by a different person
    before an outcome can be proposed, and a confirmed match blocks a "no concern" outcome.
  * Losses and recoveries are exact decimals per currency and never converted. A recovery needs a loss in the same currency and a different person to confirm it.
  * Nothing is edited or deleted. The timeline only grows, and every step is audited.
This is a record of what people decided and who decided it. It is not a filing with any authority, not legal advice and not a finding of guilt.
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Callable, List

from .errors import FincrimeError, FincrimeForbiddenError, FincrimeNotFoundError, FincrimeStateError

SOURCES = ["TRANSACTION_MONITORING", "SCREENING_HIT", "STAFF_REPORT", "EXTERNAL_TIP", "AUDIT_FINDING", "OTHER"]
SEVERITIES = ["LOW", "MEDIUM", "HIGH"]
EVENT_KINDS = ["TRANSACTION", "CONTACT", "DOCUMENT", "OBSERVATION", "OTHER"]
SCREEN_CHECKS = ["SANCTIONS", "PEP", "ADVERSE_MEDIA", "INTERNAL_LIST"]
SUBJECT_KINDS = ["PERSON", "ORGANISATION"]
SCREEN_RESULTS = ["NO_MATCH", "POSSIBLE_MATCH", "CONFIRMED_MATCH"]
RESOLUTIONS = ["FALSE_POSITIVE", "CONFIRMED"]
OUTCOMES = ["NO_CONCERN", "CONCERN_RESOLVED", "REFER_ONWARD"]
RECOVERY_KINDS = ["REPAID", "INSURANCE", "SEIZED_OR_FROZEN", "OTHER"]
DEFAULTS = {"alert_sla_days": 5, "case_sla_days": 90}
VALUE_LIMIT = Decimal("1000000000000")
LIMITATIONS = [
    "ASAVEXA records what people type in. It does not screen anyone against sanctions, politically-exposed-person or other lists, and it does not monitor transactions.",
    "It does not file a report with any authority. 'Refer onward' only records that people decided a referral should be made, to whom they say, and who decided it.",
    "An outcome is a record of a decision. It is not a finding of guilt, not legal advice and not an audit opinion.",
    "A conflict-of-interest declaration is what the person says. ASAVEXA cannot know about a conflict that nobody declares.",
    "Cases are confidential. Only people given the financial-crime permissions can see them, and a case's content is not copied into the audit trail.",
    "Amounts are exact and kept per currency. Currencies are never added together or converted.",
    "Nothing is deleted. A closed case can be reopened by a decision-maker, with a reason, and the history stays.",
]


def _utc(): return datetime.now(timezone.utc)


def _txt(v, name, lo=1, hi=1000, required=True) -> str:
    v = (v if isinstance(v, str) else ("" if v is None else str(v)))
    v = " ".join("".join(c if c >= " " and c != "\x7f" else " " for c in v).split())
    if required and len(v) < lo:
        raise FincrimeError(f"{name} is required (at least {lo} characters).")
    if v and len(v) < lo:
        raise FincrimeError(f"{name} needs at least {lo} characters.")
    if len(v) > hi:
        raise FincrimeError(f"{name} is too long (limit {hi} characters).")
    return v


def _date(v, name) -> date:
    try:
        return date.fromisoformat(str(v).strip())
    except (ValueError, TypeError):
        raise FincrimeError(f"{name} must be a real date written YYYY-MM-DD.")


def _enum(v, allowed, name) -> str:
    v = _txt(v, name, 1, 40).upper()
    if v not in allowed:
        raise FincrimeError(f"{name} must be one of {', '.join(allowed)}.")
    return v


def _currency(v, name="Currency") -> str:
    v = _txt(v, name, 3, 3).upper()
    if not (len(v) == 3 and v.isalpha() and v.isascii()):
        raise FincrimeError(f"{name} must be a three-letter code such as NGN or USD.")
    return v


def _amount(v, name) -> Decimal:
    """A positive amount with at most 2 decimal places."""
    if isinstance(v, bool) or v is None or (isinstance(v, str) and not v.strip()):
        raise FincrimeError(f"{name} is required (a number).")
    try:
        d = Decimal(str(v).strip().replace(",", ""))
    except InvalidOperation:
        raise FincrimeError(f"{name} must be a number.")
    if not d.is_finite():
        raise FincrimeError(f"{name} must be a number.")
    if d <= 0:
        raise FincrimeError(f"{name} must be more than zero.")
    if d >= VALUE_LIMIT:
        raise FincrimeError(f"{name} is too large.")
    try:
        exact = d == d.quantize(Decimal("0.01"))
    except InvalidOperation:
        exact = False
    if not exact:
        raise FincrimeError(f"{name} can have at most 2 decimal places.")
    return d.quantize(Decimal("0.01"))


def _int(v, name, lo, hi) -> int:
    if isinstance(v, bool) or not str(v).strip().lstrip("-").isdigit():
        raise FincrimeError(f"{name} must be a whole number from {lo} to {hi}.")
    n = int(str(v).strip())
    if not lo <= n <= hi:
        raise FincrimeError(f"{name} must be a whole number from {lo} to {hi}.")
    return n


def fmt(d: Decimal) -> str: return f"{d.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}"


def refnum(r) -> int:
    """AL-012 -> 12, so references sort numerically and records made in the same instant keep the order they were made in."""
    try: return int(str(r["ref"]).rsplit("-", 1)[1])
    except (KeyError, IndexError, ValueError): return 0


class FincrimeService:
    def __init__(self, store, vault=None, is_member: Callable[[str, str], bool] = lambda org, user: True, can_work: Callable[[str, str], bool] = lambda org, user: True,
                 log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = _utc):
        self.store, self.vault, self.is_member, self.can_work, self.log, self.now = store, vault, is_member, can_work, log, now

    # ------------------------------------------------------------------ helpers
    def today(self) -> date: return self.now().date()

    def _not_future(self, d: date, what: str):
        if d > self.today() + timedelta(days=1):
            raise FincrimeError(f"{what} cannot be in the future.")

    def _put(self, kind, org, d): self.store.put(kind, f"{org}:{d['id']}", d, org_id=org)
    def _all(self, kind, org) -> list: return [d for _, d in self.store.list(kind, org_id=org, prefix=f"{org}:") if d.get("org") == org]

    def _get(self, kind, org, rid, label, for_update=False) -> dict:
        r = self.store.get(kind, f"{org}:{rid}", for_update=for_update)
        if r is None or r.get("org") != org:
            raise FincrimeNotFoundError(f"{label} not found.")
        return r

    def _settings(self, org, for_update=False) -> dict:
        s = self.store.get("fc_setting", f"{org}:settings", for_update=for_update)
        if s and s.get("org") == org:
            return s
        return {"id": "settings", "org": org, **DEFAULTS, "counters": {}, "updated_by": None, "updated_at": None}

    def _ref(self, org, prefix) -> str:
        s = self._settings(org, for_update=True)
        n = s["counters"].get(prefix, 0) + 1
        s["counters"][prefix] = n
        self._put("fc_setting", org, s)
        return f"{prefix}-{n:03d}"

    def _hist(self, r, actor, event, note=""):
        r.setdefault("history", []).append({"at": self.now().isoformat(), "by": actor, "event": event, "note": note})

    def _two(self, actor, other, what):
        if actor == other:
            raise FincrimeForbiddenError(f"You {what}, so you cannot decide it. A different person must.")

    def _evidence(self, org, ids) -> List[dict]:
        out = []
        for i in dict.fromkeys(str(i) for i in (ids or [])):
            try:
                if self.vault is None: raise LookupError
                e = self.vault.get_evidence(org, i)
            except Exception:
                raise FincrimeError("Linked evidence not found in this organisation's Evidence Vault.")
            out.append({"evidence_id": e.id, "filename": e.original_filename, "file_hash": e.file_hash})
        return out

    def _worker(self, org, user, what):
        if not isinstance(user, str) or not user.strip() or not self.is_member(org, user.strip()):
            raise FincrimeError(f"{what} must be a member of this organisation.")
        if not self.can_work(org, user.strip()):
            raise FincrimeError(f"{what} must hold a role that can work financial-crime cases, otherwise nobody could carry the case forward.")
        return user.strip()

    @staticmethod
    def _cleared(case, user) -> bool:
        d = case["declarations"].get(user)
        return bool(d and d["status"] == "NONE")

    def _need_cleared(self, case, user, what="act on"):
        d = case["declarations"].get(user)
        if d is None:
            raise FincrimeStateError(f"Declare whether you have a conflict of interest on {case['ref']} before you {what} it.")
        if d["status"] != "NONE":
            raise FincrimeForbiddenError(f"You declared a conflict of interest on {case['ref']}, so you cannot {what} it.")

    def _lead_only(self, case, actor, what):
        if case["status"] == "CLOSED": raise FincrimeStateError("This case is closed. Ask a decision-maker to reopen it first.")
        if case["lead"] != actor: raise FincrimeForbiddenError(f"Only the lead investigator can {what}.")
        self._need_cleared(case, actor, "work on")

    # ------------------------------------------------------------------ policy
    def fc_get_policy(self, org) -> dict:
        s = self._settings(org)
        return {"alert_sla_days": s["alert_sla_days"], "case_sla_days": s["case_sla_days"], "updated_by": s["updated_by"], "updated_at": s["updated_at"],
                "meaning": f"An alert not looked at within {s['alert_sla_days']} days, and a case still open {s['case_sla_days']} days after it was opened, are flagged on the overview. These are your own targets, not a legal deadline."}

    def fc_set_policy(self, org, d, actor) -> dict:
        s = self._settings(org, for_update=True)
        for k, name, lo, hi in (("alert_sla_days", "The alert target", 0, 60), ("case_sla_days", "The case target", 1, 365)):
            if d.get(k) is not None: s[k] = _int(d[k], name, lo, hi)
        s.update(updated_by=actor, updated_at=self.now().isoformat())
        self._put("fc_setting", org, s)
        self.log("FINCRIME_POLICY_SET", actor, "settings", org, f"alert target {s['alert_sla_days']}, case target {s['case_sla_days']}")
        return self.fc_get_policy(org)

    # ------------------------------------------------------------------ alerts
    def _aview(self, a) -> dict:
        v = {x: a[x] for x in ("id", "ref", "source", "summary", "observed_on", "amount", "currency", "evidence", "status", "raised_by", "raised_at", "case_id", "case_ref", "dismissed_by", "dismissed_note", "history")}
        raised = datetime.fromisoformat(a["raised_at"]).date()
        v["age_days"] = (self.today() - raised).days
        return v

    def fc_raise_alert(self, org, d, actor) -> dict:
        source = _enum(d.get("source"), SOURCES, "The source")
        summary = _txt(d.get("summary"), "What was noticed", 10, 1000)
        obs = _date(d.get("observed_on"), "The date it was noticed"); self._not_future(obs, "The date it was noticed")
        amount = currency = None
        if d.get("amount") not in (None, ""):
            amount = fmt(_amount(d.get("amount"), "The amount")); currency = _currency(d.get("currency"))
        elif d.get("currency") not in (None, ""):
            raise FincrimeError("A currency needs an amount.")
        a = {"id": uuid.uuid4().hex, "org": org, "ref": None, "source": source, "summary": summary, "observed_on": obs.isoformat(), "amount": amount, "currency": currency, "evidence": self._evidence(org, d.get("evidence_ids")),
             "status": "NEW", "raised_by": actor, "raised_at": self.now().isoformat(), "case_id": None, "case_ref": None, "dismissed_by": None, "dismissed_note": None, "history": []}
        a["ref"] = self._ref(org, "AL"); self._hist(a, actor, "RAISED")
        self._put("fc_alert", org, a); self.log("FINCRIME_ALERT_RAISED", actor, a["id"], org, a["ref"])
        return self._aview(a)

    def fc_dismiss_alert(self, org, aid, reason, actor) -> dict:
        a = self._get("fc_alert", org, aid, "Alert", for_update=True)
        if a["status"] != "NEW": raise FincrimeStateError("Only an alert that has not been dealt with can be dismissed.")
        self._two(actor, a["raised_by"], "raised this alert")
        reason = _txt(reason, "A reason", 10, 500)
        a.update(status="DISMISSED", dismissed_by=actor, dismissed_note=reason); self._hist(a, actor, "DISMISSED", reason)
        self._put("fc_alert", org, a); self.log("FINCRIME_ALERT_DISMISSED", actor, aid, org, a["ref"])
        return self._aview(a)

    def fc_list_alerts(self, org, status=None) -> List[dict]:
        return [self._aview(a) for a in sorted(self._all("fc_alert", org), key=refnum) if not status or a["status"] == status]

    # ------------------------------------------------------------------ cases
    def _declare(self, case, user, status, note):
        case["declarations"][user] = {"status": status, "note": note, "at": self.now().isoformat()}

    def _cview(self, org, c) -> dict:
        v = {x: c[x] for x in ("id", "ref", "title", "summary", "severity", "status", "lead", "opened_by", "opened_at", "alert_ids", "alert_refs", "declarations", "events", "screenings", "losses", "recoveries", "decision", "closed_on", "outcome", "history")}
        v["events"] = sorted(c["events"], key=lambda e: (e["occurred_on"], e["seq"]))
        v["position"] = self._position(c)
        opened = datetime.fromisoformat(c["opened_at"]).date()
        v["age_days"] = (self.today() - opened).days
        v["unresolved_screenings"] = sum(1 for s in c["screenings"] if s["result"] == "POSSIBLE_MATCH" and not s["resolution"])
        v["confirmed_matches"] = sum(1 for s in c["screenings"] if s["result"] == "CONFIRMED_MATCH" or (s["resolution"] and s["resolution"]["outcome"] == "CONFIRMED"))
        return v

    def _position(self, c) -> List[dict]:
        cur = sorted({x["currency"] for x in c["losses"]} | {x["currency"] for x in c["recoveries"]})
        out = []
        for k in cur:
            lost = sum((Decimal(x["amount"]) for x in c["losses"] if x["currency"] == k), Decimal(0))
            conf = sum((Decimal(x["amount"]) for x in c["recoveries"] if x["currency"] == k and x["status"] == "CONFIRMED"), Decimal(0))
            pend = sum((Decimal(x["amount"]) for x in c["recoveries"] if x["currency"] == k and x["status"] == "RECORDED"), Decimal(0))
            out.append({"currency": k, "lost": fmt(lost), "recovered_confirmed": fmt(conf), "recovered_unconfirmed": fmt(pend), "outstanding": fmt(lost - conf)})
        return out

    def fc_open_case(self, org, d, actor) -> dict:
        title = _txt(d.get("title"), "The case title", 5, 150)
        summary = _txt(d.get("summary"), "What the case is about", 20, 2000)
        severity = _enum(d.get("severity"), SEVERITIES, "The severity")
        decl = d.get("conflict")
        status = _enum(decl if decl else "NONE", ["NONE", "CONFLICT"], "The conflict declaration")
        note = _txt(d.get("conflict_note"), "The description of the conflict", 10, 500, required=(status == "CONFLICT"))
        if status == "CONFLICT":
            raise FincrimeForbiddenError("You declared a conflict of interest, so you cannot open or lead this case. Ask someone else to open it.")
        ids = list(dict.fromkeys(str(i) for i in (d.get("alert_ids") or [])))
        alerts = []
        for i in ids:
            a = self._get("fc_alert", org, i, "Alert", for_update=True)
            if a["status"] != "NEW": raise FincrimeStateError(f"Alert {a['ref']} has already been dealt with.")
            alerts.append(a)
        c = {"id": uuid.uuid4().hex, "org": org, "ref": None, "title": title, "summary": summary, "severity": severity, "status": "OPEN", "lead": actor, "opened_by": actor, "opened_at": self.now().isoformat(),
             "alert_ids": [a["id"] for a in alerts], "alert_refs": [a["ref"] for a in alerts], "declarations": {}, "events": [], "screenings": [], "losses": [], "recoveries": [], "decision": None,
             "closed_on": None, "outcome": None, "seq": 0, "history": []}
        self._declare(c, actor, "NONE", note)
        c["ref"] = self._ref(org, "CS"); self._hist(c, actor, "OPENED", f"{len(alerts)} alert(s)")
        for a in alerts:
            a.update(status="IN_CASE", case_id=c["id"], case_ref=c["ref"]); self._hist(a, actor, "MOVED_TO_CASE", c["ref"]); self._put("fc_alert", org, a)
        self._put("fc_case", org, c); self.log("FINCRIME_CASE_OPENED", actor, c["id"], org, f"{c['ref']} severity {severity}, {len(alerts)} alert(s)")
        return self._cview(org, c)

    def fc_declare_interest(self, org, cid, d, actor) -> dict:
        c = self._get("fc_case", org, cid, "Case", for_update=True)       # allowed on a closed case too: a decision-maker must declare before reopening it
        status = _enum(d.get("status"), ["NONE", "CONFLICT"], "The declaration")
        note = _txt(d.get("note"), "The description of the conflict", 10, 500, required=(status == "CONFLICT"))
        old = c["declarations"].get(actor)
        if old and old["status"] == "CONFLICT":
            raise FincrimeStateError("A declared conflict of interest cannot be withdrawn.")
        if old and old["status"] == status:
            raise FincrimeStateError("You have already made that declaration on this case.")
        self._declare(c, actor, status, note); self._hist(c, actor, "INTEREST_DECLARED", status)
        if status == "CONFLICT" and c["lead"] == actor:
            c["lead"] = None; self._hist(c, actor, "LEAD_REMOVED", "The lead declared a conflict of interest")
        self._put("fc_case", org, c); self.log("FINCRIME_INTEREST_DECLARED", actor, cid, org, f"{c['ref']} {status}")
        return self._cview(org, c)

    def fc_change_lead(self, org, cid, new_lead, reason, actor) -> dict:
        c = self._get("fc_case", org, cid, "Case", for_update=True)
        if c["status"] == "CLOSED": raise FincrimeStateError("This case is closed.")
        lead = self._worker(org, new_lead, "The new lead investigator")
        if lead == c["lead"]: raise FincrimeStateError("That person is already the lead investigator.")
        reason = _txt(reason, "A reason", 5, 500)
        self._need_cleared(c, lead, "lead")
        if lead == actor: raise FincrimeForbiddenError("You cannot make yourself the lead investigator while deciding who leads. Ask another decision-maker.")
        c["lead"] = lead; self._hist(c, actor, "LEAD_CHANGED", f"to {lead}: {reason}")
        self._put("fc_case", org, c); self.log("FINCRIME_LEAD_CHANGED", actor, cid, org, f"{c['ref']}")
        return self._cview(org, c)

    def fc_add_event(self, org, cid, d, actor) -> dict:
        c = self._get("fc_case", org, cid, "Case", for_update=True)
        self._lead_only(c, actor, "add to the timeline")
        occ = _date(d.get("occurred_on"), "The date it happened"); self._not_future(occ, "The date it happened")
        e = {"id": uuid.uuid4().hex, "seq": c["seq"] + 1, "occurred_on": occ.isoformat(), "kind": _enum(d.get("kind"), EVENT_KINDS, "The kind of event"), "text": _txt(d.get("text"), "What happened", 5, 1000),
             "evidence": self._evidence(org, d.get("evidence_ids")), "recorded_by": actor, "recorded_at": self.now().isoformat()}
        c["seq"] += 1; c["events"].append(e); self._hist(c, actor, "EVENT_ADDED", e["kind"])
        self._put("fc_case", org, c); self.log("FINCRIME_EVENT_ADDED", actor, cid, org, c["ref"])
        return self._cview(org, c)

    def fc_record_screening(self, org, cid, d, actor) -> dict:
        c = self._get("fc_case", org, cid, "Case", for_update=True)
        self._lead_only(c, actor, "record a screening result")
        on = _date(d.get("screened_on"), "The date screened"); self._not_future(on, "The date screened")
        s = {"id": uuid.uuid4().hex, "seq": len(c["screenings"]) + 1, "subject": _txt(d.get("subject"), "Who or what was screened", 3, 150), "subject_kind": _enum(d.get("subject_kind"), SUBJECT_KINDS, "The kind of subject"),
             "check": _enum(d.get("check"), SCREEN_CHECKS, "The kind of check"), "list_name": _txt(d.get("list_name"), "The list or source checked", 3, 150), "screened_on": on.isoformat(),
             "result": _enum(d.get("result"), SCREEN_RESULTS, "The result"), "note": _txt(d.get("note"), "A note on the result", 5, 500), "recorded_by": actor, "recorded_at": self.now().isoformat(), "resolution": None}
        c["screenings"].append(s); self._hist(c, actor, "SCREENING_RECORDED", f"{s['check']} {s['result']}")
        self._put("fc_case", org, c); self.log("FINCRIME_SCREENING_RECORDED", actor, cid, org, f"{c['ref']} {s['check']} {s['result']}")
        return self._cview(org, c)

    def _decider(self, c, actor, what):
        """Common rules for anyone deciding something on a case: not the lead, not the opener, and on record as having no conflict."""
        self._two(actor, c["lead"], "lead this case")
        self._two(actor, c["opened_by"], "opened this case")
        self._need_cleared(c, actor, what)

    def fc_resolve_screening(self, org, cid, sid, d, actor) -> dict:
        c = self._get("fc_case", org, cid, "Case", for_update=True)
        if c["status"] == "CLOSED": raise FincrimeStateError("This case is closed. Ask a decision-maker to reopen it first.")
        s = next((x for x in c["screenings"] if x["id"] == sid), None)
        if s is None: raise FincrimeNotFoundError("Screening result not found.")
        if s["result"] != "POSSIBLE_MATCH" or s["resolution"]: raise FincrimeStateError("Only a possible match that has not been resolved can be resolved.")
        self._two(actor, s["recorded_by"], "recorded this result")
        self._decider(c, actor, "decide")
        outcome = _enum(d.get("outcome"), RESOLUTIONS, "The resolution"); reason = _txt(d.get("reason"), "A reason", 10, 500)
        s["resolution"] = {"outcome": outcome, "reason": reason, "by": actor, "at": self.now().isoformat()}; self._hist(c, actor, "SCREENING_RESOLVED", outcome)
        self._put("fc_case", org, c); self.log("FINCRIME_SCREENING_RESOLVED", actor, cid, org, f"{c['ref']} {outcome}")
        return self._cview(org, c)

    def fc_record_loss(self, org, cid, d, actor) -> dict:
        c = self._get("fc_case", org, cid, "Case", for_update=True)
        self._lead_only(c, actor, "record a loss")
        on = _date(d.get("occurred_on"), "The date of the loss"); self._not_future(on, "The date of the loss")
        x = {"id": uuid.uuid4().hex, "seq": len(c["losses"]) + 1, "amount": fmt(_amount(d.get("amount"), "The amount")), "currency": _currency(d.get("currency")), "occurred_on": on.isoformat(),
             "description": _txt(d.get("description"), "What was lost", 5, 500), "evidence": self._evidence(org, d.get("evidence_ids")), "recorded_by": actor, "recorded_at": self.now().isoformat()}
        c["losses"].append(x); self._hist(c, actor, "LOSS_RECORDED", x["currency"])
        self._put("fc_case", org, c); self.log("FINCRIME_LOSS_RECORDED", actor, cid, org, f"{c['ref']} {x['currency']}")
        return self._cview(org, c)

    def fc_record_recovery(self, org, cid, d, actor) -> dict:
        c = self._get("fc_case", org, cid, "Case", for_update=True)
        self._lead_only(c, actor, "record a recovery")
        amount = _amount(d.get("amount"), "The amount"); cur = _currency(d.get("currency"))
        on = _date(d.get("received_on"), "The date recovered"); self._not_future(on, "The date recovered")
        lost = sum((Decimal(x["amount"]) for x in c["losses"] if x["currency"] == cur), Decimal(0))
        if lost == 0: raise FincrimeStateError(f"Record a loss in {cur} before recording a recovery in {cur}.")
        live = sum((Decimal(x["amount"]) for x in c["recoveries"] if x["currency"] == cur and x["status"] in ("RECORDED", "CONFIRMED")), Decimal(0))
        if live + amount > lost: raise FincrimeError(f"Recoveries in {cur} would be {fmt(live + amount)} against {fmt(lost)} lost. A recovery cannot be more than the loss recorded.")
        x = {"id": uuid.uuid4().hex, "seq": len(c["recoveries"]) + 1, "amount": fmt(amount), "currency": cur, "received_on": on.isoformat(), "kind": _enum(d.get("kind"), RECOVERY_KINDS, "The kind of recovery"),
             "note": _txt(d.get("note"), "A note on the recovery", 5, 500), "evidence": self._evidence(org, d.get("evidence_ids")), "status": "RECORDED", "recorded_by": actor, "recorded_at": self.now().isoformat(),
             "confirmed_by": None, "rejected_note": None}
        c["recoveries"].append(x); self._hist(c, actor, "RECOVERY_RECORDED", cur)
        self._put("fc_case", org, c); self.log("FINCRIME_RECOVERY_RECORDED", actor, cid, org, f"{c['ref']} {cur}")
        return self._cview(org, c)

    def _recovery(self, c, rid) -> dict:
        x = next((y for y in c["recoveries"] if y["id"] == rid), None)
        if x is None: raise FincrimeNotFoundError("Recovery not found.")
        if x["status"] != "RECORDED": raise FincrimeStateError("Only a recovery waiting for confirmation can be confirmed or rejected.")
        return x

    def fc_confirm_recovery(self, org, cid, rid, actor) -> dict:
        c = self._get("fc_case", org, cid, "Case", for_update=True)
        if c["status"] == "CLOSED": raise FincrimeStateError("This case is closed. Ask a decision-maker to reopen it first.")
        x = self._recovery(c, rid); self._two(actor, x["recorded_by"], "recorded this recovery"); self._decider(c, actor, "decide")
        x.update(status="CONFIRMED", confirmed_by=actor); self._hist(c, actor, "RECOVERY_CONFIRMED", x["currency"])
        self._put("fc_case", org, c); self.log("FINCRIME_RECOVERY_CONFIRMED", actor, cid, org, c["ref"])
        return self._cview(org, c)

    def fc_reject_recovery(self, org, cid, rid, reason, actor) -> dict:
        c = self._get("fc_case", org, cid, "Case", for_update=True)
        if c["status"] == "CLOSED": raise FincrimeStateError("This case is closed. Ask a decision-maker to reopen it first.")
        x = self._recovery(c, rid); self._two(actor, x["recorded_by"], "recorded this recovery"); self._decider(c, actor, "decide")
        x.update(status="REJECTED", rejected_note=_txt(reason, "A reason", 10, 500)); self._hist(c, actor, "RECOVERY_REJECTED", x["currency"])
        self._put("fc_case", org, c); self.log("FINCRIME_RECOVERY_REJECTED", actor, cid, org, c["ref"])
        return self._cview(org, c)

    # ------------------------------------------------------------------ decision
    def fc_propose_decision(self, org, cid, d, actor) -> dict:
        c = self._get("fc_case", org, cid, "Case", for_update=True)
        self._lead_only(c, actor, "propose an outcome")
        if c["status"] != "OPEN": raise FincrimeStateError("An outcome can only be proposed for an open case that has none waiting.")
        outcome = _enum(d.get("outcome"), OUTCOMES, "The outcome")
        rationale = _txt(d.get("rationale"), "The reasons for the outcome", 20, 2000)
        referral = _txt(d.get("referral_to"), "Who the referral is to", 3, 200, required=(outcome == "REFER_ONWARD")) if (outcome == "REFER_ONWARD" or d.get("referral_to")) else ""
        if outcome != "REFER_ONWARD" and referral: raise FincrimeError("Only a referral names who it is to.")
        if any(s["result"] == "POSSIBLE_MATCH" and not s["resolution"] for s in c["screenings"]):
            raise FincrimeStateError("A possible screening match has not been resolved by a different person yet.")
        confirmed = any(s["result"] == "CONFIRMED_MATCH" or (s["resolution"] and s["resolution"]["outcome"] == "CONFIRMED") for s in c["screenings"])
        if outcome == "NO_CONCERN" and (confirmed or c["losses"]):
            raise FincrimeStateError("'No concern' cannot be proposed when a screening match is confirmed or a loss has been recorded.")
        c["decision"] = {"outcome": outcome, "rationale": rationale, "referral_to": referral or None, "proposed_by": actor, "proposed_at": self.now().isoformat(), "decided_by": None, "decided_at": None, "rejected_note": None}
        c["status"] = "DECISION_PROPOSED"; self._hist(c, actor, "DECISION_PROPOSED", outcome)
        self._put("fc_case", org, c); self.log("FINCRIME_DECISION_PROPOSED", actor, cid, org, f"{c['ref']} {outcome}")
        return self._cview(org, c)

    def _decide_checks(self, org, c, actor):
        if c["status"] != "DECISION_PROPOSED": raise FincrimeStateError("There is no proposed outcome waiting for a decision.")
        self._two(actor, c["decision"]["proposed_by"], "proposed this outcome")
        self._decider(c, actor, "decide")
        for aid in c["alert_ids"]:
            a = self._get("fc_alert", org, aid, "Alert")
            self._two(actor, a["raised_by"], f"raised alert {a['ref']}, which is part of this case")

    def fc_approve_decision(self, org, cid, actor, note="") -> dict:
        c = self._get("fc_case", org, cid, "Case", for_update=True)
        self._decide_checks(org, c, actor)
        if any(s["result"] == "POSSIBLE_MATCH" and not s["resolution"] for s in c["screenings"]):
            raise FincrimeStateError("A possible screening match has not been resolved yet.")
        c["decision"].update(decided_by=actor, decided_at=self.now().isoformat())
        c.update(status="CLOSED", closed_on=self.today().isoformat(), outcome=c["decision"]["outcome"]); self._hist(c, actor, "DECISION_APPROVED", _txt(note, "The note", 0, 500, required=False))
        self._put("fc_case", org, c); self.log("FINCRIME_DECISION_APPROVED", actor, cid, org, f"{c['ref']} {c['outcome']}")
        return self._cview(org, c)

    def fc_reject_decision(self, org, cid, reason, actor) -> dict:
        c = self._get("fc_case", org, cid, "Case", for_update=True)
        self._decide_checks(org, c, actor)
        reason = _txt(reason, "A reason", 10, 500)
        c["decision"].update(rejected_note=reason); c["status"] = "OPEN"; self._hist(c, actor, "DECISION_REJECTED", reason)
        self._put("fc_case", org, c); self.log("FINCRIME_DECISION_REJECTED", actor, cid, org, c["ref"])
        return self._cview(org, c)

    def fc_reopen_case(self, org, cid, reason, actor) -> dict:
        c = self._get("fc_case", org, cid, "Case", for_update=True)
        if c["status"] != "CLOSED": raise FincrimeStateError("Only a closed case can be reopened.")
        reason = _txt(reason, "A reason", 10, 500)
        self._need_cleared(c, actor, "reopen")
        c.update(status="OPEN", closed_on=None, outcome=None); c["decision"] = None; self._hist(c, actor, "REOPENED", reason)
        self._put("fc_case", org, c); self.log("FINCRIME_CASE_REOPENED", actor, cid, org, c["ref"])
        return self._cview(org, c)

    # ------------------------------------------------------------------ reads
    def fc_list_cases(self, org, status=None) -> List[dict]:
        out = []
        for c in sorted(self._all("fc_case", org), key=refnum):
            if status and c["status"] != status: continue
            v = self._cview(org, c)
            for k in ("events", "screenings", "losses", "recoveries", "history"): v[k + "_count"] = len(v.pop(k))
            out.append(v)
        return out

    def fc_get_case(self, org, cid) -> dict: return self._cview(org, self._get("fc_case", org, cid, "Case"))

    def fc_overview(self, org) -> dict:
        alerts = self._all("fc_alert", org); cases = [self._cview(org, c) for c in sorted(self._all("fc_case", org), key=refnum)]
        s = self._settings(org); att = []

        def add(kind, n, text):
            if n: att.append({"kind": kind, "count": n, "text": text})
        live = [c for c in cases if c["status"] != "CLOSED"]
        add("ALERTS_WAITING", sum(1 for a in alerts if a["status"] == "NEW" and self._aview(a)["age_days"] > s["alert_sla_days"]), f"alert(s) have waited more than {s['alert_sla_days']} days and nobody has opened a case or dismissed them.")
        add("CASES_NO_LEAD", sum(1 for c in live if c["lead"] is None), "case(s) have no lead investigator because the lead declared a conflict of interest.")
        add("DECISIONS_PENDING", sum(1 for c in live if c["status"] == "DECISION_PROPOSED"), "case(s) have a proposed outcome waiting for a different person to decide.")
        add("SCREENINGS_UNRESOLVED", sum(c["unresolved_screenings"] for c in live), "possible screening match(es) are waiting for a different person to resolve them.")
        add("RECOVERIES_TO_CONFIRM", sum(1 for c in live for x in c["recoveries"] if x["status"] == "RECORDED"), "recovery record(s) are waiting for a different person to confirm them.")
        add("CASES_AGING", sum(1 for c in live if c["age_days"] > s["case_sla_days"]), f"case(s) have been open more than {s['case_sla_days']} days.")
        by_sev = {k: sum(1 for c in live if c["severity"] == k) for k in SEVERITIES}
        return {"counts": {"alerts": len(alerts), "alerts_new": sum(1 for a in alerts if a["status"] == "NEW"), "cases": len(cases), "cases_open": len(live), "cases_closed": len(cases) - len(live), "open_by_severity": by_sev},
                "attention": att, "policy": self.fc_get_policy(org), "limitations": LIMITATIONS}

    def fc_options(self, org) -> dict:
        return {"sources": SOURCES, "severities": SEVERITIES, "event_kinds": EVENT_KINDS, "checks": SCREEN_CHECKS, "subject_kinds": SUBJECT_KINDS, "results": SCREEN_RESULTS, "resolutions": RESOLUTIONS,
                "outcomes": OUTCOMES, "recovery_kinds": RECOVERY_KINDS, "limitations": LIMITATIONS}
