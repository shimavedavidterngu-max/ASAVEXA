"""The pilot: an accounting firm and a small number of client SMEs, measured honestly.

Stores only what people tell us (the pilot set-up, time logs, issues, survey answers, real Passport uses, weekly snapshots). Everything the
system can observe for itself is computed from the clients' own records in metrics.py and is never copied in here.

Rules enforced here (and tested):
  * a client organisation is in at most one active pilot, and never in a pilot with itself as the firm;
  * adding a client needs a recorded consent reference (the router additionally requires owner/administrator authority in the client);
  * a client that leaves stops being measured from that moment; what it logged is kept but excluded from results;
  * a client organisation sees only its own part of a pilot, never the other clients;
  * survey answers are one-per-person-per-round, and group averages are hidden until at least 3 people are in the group."""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional

from .errors import PilotError, PilotForbiddenError, PilotNotFoundError, PilotStateError
from .evaluate import DEFAULT_TARGETS, clean_targets

TIME_KINDS = ("ONBOARDING", "AUDIT_PREP", "REPORT", "MONTH_END", "RECONCILIATION", "OTHER")
ISSUE_KINDS = ("USER_ERROR", "CONFUSION", "BUG", "MISSING_FEATURE", "DATA_PROBLEM", "OTHER")
SEVERITIES = ("LOW", "MEDIUM", "HIGH")
PASSPORT_PURPOSES = ("LENDER", "TAX_AUTHORITY", "AUDITOR", "INVESTOR", "REGULATOR", "INTERNAL", "OTHER")
PASSPORT_OUTCOMES = ("HELPFUL", "PARTLY", "NOT_HELPFUL")
STATUSES = ("PLANNING", "ACTIVE", "COMPLETED")
MAX_CLIENTS = 12
MIN_GROUP_FOR_AVERAGE = 3
SCORES = {"overall": (1, 5, True), "ease": (1, 5, True), "trust": (1, 5, True), "recommend": (0, 10, True), "time_saving": (1, 5, False), "passport_useful": (1, 5, False)}
BASELINE_FOR = {"AUDIT_PREP": "audit_prep_minutes", "REPORT": "report_minutes"}


def _utc():
    return datetime.now(timezone.utc)


def sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _txt(v, name, lo=1, hi=1000, required=True) -> str:
    v = (v if isinstance(v, str) else ("" if v is None else str(v))).strip()
    if required and len(v) < lo:
        raise PilotError(f"{name} is required.")
    if len(v) > hi:
        raise PilotError(f"{name} is too long (limit {hi} characters).")
    return v


def _int(v, name, lo, hi, required=True):
    if v in (None, ""):
        if required:
            raise PilotError(f"{name} is required.")
        return None
    if isinstance(v, bool) or not isinstance(v, int) and not (isinstance(v, str) and v.strip().isdigit()):
        raise PilotError(f"{name} must be a whole number.")
    v = int(v)
    if not lo <= v <= hi:
        raise PilotError(f"{name} must be between {lo} and {hi}.")
    return v


def _day(v, name) -> date:
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        raise PilotError(f"{name} must be a date like 2026-10-12.")


class PilotService:
    def __init__(self, store, log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = _utc):
        self.store, self.log, self.now = store, log, now

    # ------------------------------------------------------------------ pilots
    def _key(self, org, pid, sub=""): return f"{org}:{pid}" + (f":{sub}" if sub else "")

    def _pilot(self, org, pid, for_update=False) -> dict:
        p = self.store.get("pilot", self._key(org, pid), for_update=for_update)
        if p is None:
            raise PilotNotFoundError("Pilot not found.")
        return p

    def _save(self, org, p): self.store.put("pilot", self._key(org, p["id"]), p, org_id=org)

    def create_pilot(self, org: str, actor: str, name: str, start_date: str, end_date: Optional[str] = None, notes: str = "", targets: Optional[dict] = None) -> dict:
        start = _day(start_date, "Start date")
        end = _day(end_date, "End date") if end_date else None
        if end and end < start:
            raise PilotError("The end date cannot be before the start date.")
        try:
            tg = clean_targets(targets)
        except ValueError as e:
            raise PilotError(str(e))
        pid = str(uuid.uuid4())
        p = {"id": pid, "org_id": org, "name": _txt(name, "Pilot name", hi=120), "status": "PLANNING", "start_date": start.isoformat(), "end_date": end.isoformat() if end else None,
             "notes": _txt(notes, "Notes", hi=2000, required=False), "targets": tg, "clients": [], "created_by": actor, "created_at": self.now().isoformat()}
        self._save(org, p)
        self.log("PILOT_CREATED", actor, pid, org, p["name"])
        return self.view(org, pid)

    def list_pilots(self, org: str) -> List[dict]:
        out = [{"id": p["id"], "name": p["name"], "status": p["status"], "start_date": p["start_date"], "clients": sum(1 for c in p["clients"] if c["active"])} for _, p in self.store.list("pilot", org_id=org)]
        return sorted(out, key=lambda x: x["start_date"], reverse=True)

    def view(self, org: str, pid: str) -> dict:
        p = dict(self._pilot(org, pid))
        p["clients"] = [dict(c) for c in p["clients"]]
        p["can_start"] = any(c["active"] for c in p["clients"])
        return p

    def update_targets(self, org: str, actor: str, pid: str, targets: dict) -> dict:
        p = self._pilot(org, pid, True)
        try:
            p["targets"] = clean_targets({**p["targets"], **(targets or {})})
        except ValueError as e:
            raise PilotError(str(e))
        self._save(org, p)
        self.log("PILOT_TARGETS_UPDATED", actor, pid, org, "targets changed before results were judged" if p["status"] == "PLANNING" else "targets changed mid-pilot")
        return self.view(org, pid)

    def set_status(self, org: str, actor: str, pid: str, status: str) -> dict:
        p = self._pilot(org, pid, True)
        status = (status or "").upper()
        order = {"PLANNING": 0, "ACTIVE": 1, "COMPLETED": 2}
        if status not in order:
            raise PilotError(f"Status must be one of: {', '.join(STATUSES)}.")
        if order[status] != order[p["status"]] + 1:
            raise PilotStateError(f"A pilot goes Planning, then Active, then Completed. It is {p['status'].title()}, so it cannot become {status.title()}.")
        if status == "ACTIVE" and not any(c["active"] for c in p["clients"]):
            raise PilotStateError("Add at least one client organisation before starting the pilot.")
        p["status"] = status
        self._save(org, p)
        self.log("PILOT_STATUS_CHANGED", actor, pid, org, status)
        return self.view(org, pid)

    # ------------------------------------------------------------------ clients
    def _parse_kickoff(self, v) -> datetime:
        if v in (None, ""):
            return self.now()
        s = str(v)
        try:
            d = datetime.fromisoformat(s) if len(s) > 10 else datetime.combine(date.fromisoformat(s), datetime.min.time())
        except ValueError:
            raise PilotError("Kickoff must be a date like 2026-10-12.")
        d = d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
        if d > self.now() + timedelta(days=1):
            raise PilotError("Kickoff cannot be in the future.")
        return d

    def _baseline(self, b) -> dict:
        b = b or {}
        return {"audit_prep_minutes": _int(b.get("audit_prep_minutes"), "Audit-preparation baseline (minutes)", 1, 100000, False),
                "report_minutes": _int(b.get("report_minutes"), "Report baseline (minutes)", 1, 100000, False)}

    def add_client(self, org: str, actor: str, pid: str, client_org: str, label: str, consent_reference: str, kickoff: Optional[str] = None, baseline: Optional[dict] = None) -> dict:
        p = self._pilot(org, pid, True)
        if p["status"] == "COMPLETED":
            raise PilotStateError("This pilot is completed, so clients cannot be added.")
        if client_org == org:
            raise PilotError("The firm's own organisation cannot be a client of its own pilot.")
        if len([c for c in p["clients"] if c["active"]]) >= MAX_CLIENTS:
            raise PilotStateError(f"A pilot can have at most {MAX_CLIENTS} client organisations. Start small and add more only when the first ones work.")
        idx = self.store.get("pilot_client", client_org, for_update=True)
        if idx and idx.get("active"):
            raise PilotStateError("That organisation is already a client in an active pilot. It must leave that pilot first.")
        entry = {"org_id": client_org, "label": _txt(label, "Client name", hi=80), "kickoff": self._parse_kickoff(kickoff).isoformat(),
                 "consent_reference": _txt(consent_reference, "Consent reference", lo=3, hi=300), "baseline": self._baseline(baseline), "active": True,
                 "added_by": actor, "added_at": self.now().isoformat(), "left_at": None, "left_reason": None, "left_by": None}
        p["clients"] = [c for c in p["clients"] if c["org_id"] != client_org] + [entry]
        self._save(org, p)
        self.store.put("pilot_client", client_org, {"pilot_id": pid, "firm_org_id": org, "active": True, "since": entry["added_at"]}, org_id=client_org)
        self.log("PILOT_CLIENT_ADDED", actor, pid, org, f"{entry['label']} (consent: {entry['consent_reference']})")
        self.log("PILOT_CLIENT_ADDED", actor, pid, client_org, f"This organisation joined the pilot '{p['name']}' run by another organisation (consent: {entry['consent_reference']})")
        return self.view(org, pid)

    def update_client(self, org: str, actor: str, pid: str, client_org: str, label: Optional[str] = None, kickoff: Optional[str] = None, baseline: Optional[dict] = None) -> dict:
        p = self._pilot(org, pid, True)
        c = self._client(p, client_org, active=True)
        if label:
            c["label"] = _txt(label, "Client name", hi=80)
        if kickoff:
            c["kickoff"] = self._parse_kickoff(kickoff).isoformat()
        if baseline is not None:
            c["baseline"] = {**c["baseline"], **{k: v for k, v in self._baseline(baseline).items() if k in baseline}}
        self._save(org, p)
        self.log("PILOT_CLIENT_UPDATED", actor, pid, org, c["label"])
        return self.view(org, pid)

    def _client(self, p, client_org, active=None):
        c = next((c for c in p["clients"] if c["org_id"] == client_org), None)
        if c is None or (active is not None and c["active"] != active):
            raise PilotNotFoundError("That organisation is not an active client of this pilot.")
        return c

    def remove_client(self, org: str, actor: str, pid: str, client_org: str, reason: str) -> dict:
        p = self._pilot(org, pid, True)
        c = self._client(p, client_org, active=True)
        c.update(active=False, left_at=self.now().isoformat(), left_reason=_txt(reason, "Reason", hi=300), left_by=actor)
        self._save(org, p)
        self.store.put("pilot_client", client_org, {"pilot_id": pid, "firm_org_id": org, "active": False, "since": c["added_at"], "left_at": c["left_at"]}, org_id=client_org)
        self.log("PILOT_CLIENT_REMOVED", actor, pid, org, f"{c['label']}: {c['left_reason']}")
        self.log("PILOT_CLIENT_REMOVED", actor, pid, client_org, f"This organisation left the pilot '{p['name']}': {c['left_reason']}")
        return self.view(org, pid)

    # ------------------------------------------------------------------ who is taking part
    def membership(self, org: str) -> Optional[dict]:
        """How the given organisation relates to a pilot: as the firm running one, or as an active client in one (never both views mixed)."""
        idx = self.store.get("pilot_client", org)
        if idx and idx.get("active"):
            p = self._pilot(idx["firm_org_id"], idx["pilot_id"])
            c = self._client(p, org, active=True)
            return {"role": "CLIENT", "pilot_id": p["id"], "firm_org_id": p["org_id"], "pilot": {"id": p["id"], "name": p["name"], "status": p["status"], "start_date": p["start_date"], "end_date": p["end_date"]},
                    "client": {"org_id": org, "label": c["label"], "kickoff": c["kickoff"], "consent_reference": c["consent_reference"]}}
        pilots = self.list_pilots(org)
        return {"role": "FIRM", "pilots": pilots} if pilots else None

    def is_active_client(self, org: str) -> bool:
        idx = self.store.get("pilot_client", org)
        return bool(idx and idx.get("active"))

    def firm_for(self, session_org: str, pid: str) -> str:
        """The organisation running pilot `pid`, as seen from the session's organisation (the firm itself, or an active client of it)."""
        if self.store.get("pilot", self._key(session_org, pid)) is not None:
            return session_org
        idx = self.store.get("pilot_client", session_org)
        if idx and idx.get("active") and idx["pilot_id"] == pid:
            return idx["firm_org_id"]
        raise PilotNotFoundError("Pilot not found.")

    def _participant(self, session_org: str, firm_org: str, pid: str, client_org: Optional[str] = None) -> tuple:
        """Returns (pilot, group). The firm may act for any active client; a client only for itself."""
        p = self._pilot(firm_org, pid)
        if session_org == firm_org:
            if client_org is not None:
                self._client(p, client_org, active=True)
            return p, "FIRM"
        c = next((c for c in p["clients"] if c["org_id"] == session_org and c["active"]), None)
        if c is None:
            raise PilotForbiddenError("Your organisation is not taking part in this pilot.")
        if client_org is not None and client_org != session_org:
            raise PilotForbiddenError("You can only record things about your own organisation.")
        return p, "CLIENT"

    def active_clients(self, p) -> List[dict]:
        return [c for c in p["clients"] if c["active"]]

    # ------------------------------------------------------------------ logs: time, issues, Passport use
    def log_time(self, session_org: str, actor: str, firm_org: str, pid: str, client_org: str, kind: str, minutes, performed_on: str, baseline_minutes=None, note: str = "") -> dict:
        p, group = self._participant(session_org, firm_org, pid, client_org)
        kind = (kind or "").upper()
        if kind not in TIME_KINDS:
            raise PilotError(f"Kind must be one of: {', '.join(TIME_KINDS)}.")
        day = _day(performed_on, "Date")
        if day > self.now().date():
            raise PilotError("The date cannot be in the future.")
        rec = {"id": str(uuid.uuid4()), "pilot_id": pid, "client_org_id": client_org, "kind": kind, "minutes": _int(minutes, "Minutes taken", 1, 100000),
               "baseline_minutes": _int(baseline_minutes, "Baseline minutes", 1, 100000, False), "performed_on": day.isoformat(), "note": _txt(note, "Note", hi=500, required=False),
               "logged_by": actor, "group": group, "logged_at": self.now().isoformat()}
        self.store.put("pilot_log", self._key(firm_org, pid, rec["id"]), rec, org_id=firm_org)
        self.log("PILOT_TIME_LOGGED", actor, pid, firm_org, f"{kind} {rec['minutes']} min")
        return rec

    def _docs(self, kind, firm_org, pid) -> List[dict]:
        return [d for _, d in self.store.list(kind, org_id=firm_org, prefix=f"{firm_org}:{pid}:")]

    def log_issue(self, session_org: str, actor: str, firm_org: str, pid: str, client_org: str, kind: str, severity: str, text: str) -> dict:
        p, group = self._participant(session_org, firm_org, pid, client_org)
        kind, severity = (kind or "").upper(), (severity or "").upper()
        if kind not in ISSUE_KINDS:
            raise PilotError(f"Kind must be one of: {', '.join(ISSUE_KINDS)}.")
        if severity not in SEVERITIES:
            raise PilotError(f"Severity must be one of: {', '.join(SEVERITIES)}.")
        rec = {"id": str(uuid.uuid4()), "pilot_id": pid, "client_org_id": client_org, "kind": kind, "severity": severity, "text": _txt(text, "What happened", lo=5, hi=1500), "status": "OPEN",
               "reported_by": actor, "group": group, "reported_at": self.now().isoformat(), "resolution": None, "resolved_by": None, "resolved_at": None}
        self.store.put("pilot_issue", self._key(firm_org, pid, rec["id"]), rec, org_id=firm_org)
        self.log("PILOT_ISSUE_LOGGED", actor, pid, firm_org, f"{kind}/{severity}")
        return rec

    def resolve_issue(self, firm_org: str, actor: str, pid: str, issue_id: str, resolution: str) -> dict:
        self._pilot(firm_org, pid)
        rec = self.store.get("pilot_issue", self._key(firm_org, pid, issue_id), for_update=True)
        if rec is None:
            raise PilotNotFoundError("Issue not found.")
        if rec["status"] == "RESOLVED":
            raise PilotStateError("That issue is already resolved.")
        rec.update(status="RESOLVED", resolution=_txt(resolution, "Resolution", lo=3, hi=500), resolved_by=actor, resolved_at=self.now().isoformat())
        self.store.put("pilot_issue", self._key(firm_org, pid, issue_id), rec, org_id=firm_org)
        self.log("PILOT_ISSUE_RESOLVED", actor, pid, firm_org, rec["kind"])
        return rec

    def log_passport_use(self, session_org: str, actor: str, firm_org: str, pid: str, client_org: str, purpose: str, outcome: str, saved_minutes=None, note: str = "") -> dict:
        p, group = self._participant(session_org, firm_org, pid, client_org)
        purpose, outcome = (purpose or "").upper(), (outcome or "").upper()
        if purpose not in PASSPORT_PURPOSES:
            raise PilotError(f"Purpose must be one of: {', '.join(PASSPORT_PURPOSES)}.")
        if outcome not in PASSPORT_OUTCOMES:
            raise PilotError(f"Outcome must be one of: {', '.join(PASSPORT_OUTCOMES)}.")
        rec = {"id": str(uuid.uuid4()), "pilot_id": pid, "client_org_id": client_org, "purpose": purpose, "outcome": outcome, "saved_minutes": _int(saved_minutes, "Minutes saved", 0, 100000, False),
               "note": _txt(note, "Note", hi=500, required=False), "logged_by": actor, "group": group, "logged_at": self.now().isoformat()}
        self.store.put("pilot_passport_use", self._key(firm_org, pid, rec["id"]), rec, org_id=firm_org)
        self.log("PILOT_PASSPORT_USE_LOGGED", actor, pid, firm_org, f"{purpose}: {outcome}")
        return rec

    # ------------------------------------------------------------------ survey
    def submit_survey(self, session_org: str, actor: str, firm_org: str, pid: str, round_label: str, scores: dict, comment: str = "") -> dict:
        p, group = self._participant(session_org, firm_org, pid)
        label = (round_label or "GENERAL").strip().upper() or "GENERAL"
        if not re.fullmatch(r"[A-Z0-9_ -]{1,30}", label):
            raise PilotError("The survey round name can use letters, numbers, spaces, - and _ (up to 30 characters).")
        clean = {}
        for k, (lo, hi, required) in SCORES.items():
            clean[k] = _int((scores or {}).get(k), k.replace("_", " ").capitalize(), lo, hi, required)
        extra = set(scores or {}) - set(SCORES)
        if extra:
            raise PilotError(f"Unknown answer(s): {', '.join(sorted(extra))}.")
        key = self._key(firm_org, pid, f"{label}:{actor}")
        prev = self.store.get("pilot_survey", key, for_update=True)
        rec = {"pilot_id": pid, "round": label, "group": group, "org_id": session_org, "user_id": actor, "scores": clean, "comment": _txt(comment, "Comment", hi=1000, required=False),
               "submitted_at": self.now().isoformat(), "revision": (prev["revision"] + 1) if prev else 1}
        self.store.put("pilot_survey", key, rec, org_id=firm_org)
        self.log("PILOT_SURVEY_SUBMITTED", actor, pid, firm_org, f"{label} ({group.lower()})" + (" — updated" if prev else ""))
        return {"round": label, "revision": rec["revision"], "group": group}

    def my_survey(self, session_org: str, actor: str, firm_org: str, pid: str) -> List[dict]:
        self._participant(session_org, firm_org, pid)
        return sorted(({"round": d["round"], "scores": d["scores"], "comment": d["comment"], "submitted_at": d["submitted_at"], "revision": d["revision"]}
                       for d in self._docs("pilot_survey", firm_org, pid) if d["user_id"] == actor), key=lambda x: x["submitted_at"], reverse=True)

    def _survey_rows(self, p) -> List[dict]:
        """Each person's most recent answers (across rounds), counting only the firm and organisations still in the pilot."""
        live = {c["org_id"] for c in self.active_clients(p)} | {p["org_id"]}
        latest: Dict[str, dict] = {}
        for d in self._docs("pilot_survey", p["org_id"], p["id"]):
            if d["org_id"] in live and (d["user_id"] not in latest or d["submitted_at"] > latest[d["user_id"]]["submitted_at"]):
                latest[d["user_id"]] = d
        return list(latest.values())

    @staticmethod
    def _mean(vals) -> Optional[float]:
        vals = [v for v in vals if v is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    def survey_summary(self, p, include_comments: bool = False) -> dict:
        rows = self._survey_rows(p)
        S = lambda key, rs=rows: [r["scores"].get(key) for r in rs]
        rec = [v for v in S("recommend") if v is not None]
        nps = round((sum(1 for v in rec if v >= 9) - sum(1 for v in rec if v <= 6)) * 100.0 / len(rec)) if rec else None
        by_group = {}
        for g in ("FIRM", "CLIENT"):
            rs = [r for r in rows if r["group"] == g]
            shown = len(rs) >= MIN_GROUP_FOR_AVERAGE
            by_group[g] = {"n": len(rs), "overall": self._mean(S("overall", rs)) if shown else None, "hidden": bool(rs) and not shown}
        pu = [v for v in S("passport_useful") if v is not None]
        out = {"respondents": len(rows), "overall_mean": self._mean(S("overall")), "ease_mean": self._mean(S("ease")), "trust_mean": self._mean(S("trust")), "time_saving_mean": self._mean(S("time_saving")),
               "nps": nps, "by_group": by_group, "passport_useful": {"n": len(pu), "mean": self._mean(pu)},
               "rounds": sorted({r["round"] for r in rows}), "privacy_note": f"Averages for a group are hidden until it has {MIN_GROUP_FOR_AVERAGE} people, so no one's answers can be picked out."}
        if include_comments:
            out["comments"] = sorted(({"group": r["group"], "round": r["round"], "comment": r["comment"], "at": r["submitted_at"]} for r in rows if r["comment"]), key=lambda x: x["at"], reverse=True)
        return out

    # ------------------------------------------------------------------ what people reported, summarised for the evaluation
    def reported(self, p, include_comments: bool = False) -> dict:
        live = {c["org_id"]: c for c in self.active_clients(p)}
        logs = [d for d in self._docs("pilot_log", p["org_id"], p["id"]) if d["client_org_id"] in live]
        time = {}
        for kind in TIME_KINDS:
            es = [d for d in logs if d["kind"] == kind]
            paired = []
            for d in es:
                base = d["baseline_minutes"] or live[d["client_org_id"]]["baseline"].get(BASELINE_FOR.get(kind, ""), None)
                if base:
                    paired.append((d["minutes"], base))
            m, b = sum(x for x, _ in paired), sum(y for _, y in paired)
            time[kind.lower()] = {"entries": len(es), "minutes": sum(d["minutes"] for d in es), "paired_entries": len(paired), "baseline_minutes": b,
                                  "saved_percent": round((1 - m / b) * 100.0, 1) if b else None}
        issues = [d for d in self._docs("pilot_issue", p["org_id"], p["id"]) if d["client_org_id"] in live]
        bk: Dict[str, int] = {}
        for d in issues:
            bk[d["kind"]] = bk.get(d["kind"], 0) + 1
        uses = [d for d in self._docs("pilot_passport_use", p["org_id"], p["id"]) if d["client_org_id"] in live]
        bp: Dict[str, int] = {}
        for d in uses:
            bp[d["purpose"]] = bp.get(d["purpose"], 0) + 1
        return {"time": time, "issues": {"total": len(issues), "open": sum(1 for d in issues if d["status"] == "OPEN"), "user_errors": bk.get("USER_ERROR", 0), "by_kind": bk},
                "survey": self.survey_summary(p, include_comments),
                "passport_uses": {"total": len(uses), "helpful": sum(1 for d in uses if d["outcome"] == "HELPFUL"), "partly": sum(1 for d in uses if d["outcome"] == "PARTLY"),
                                  "not_helpful": sum(1 for d in uses if d["outcome"] == "NOT_HELPFUL"), "by_purpose": bp,
                                  "minutes_saved": sum(d["saved_minutes"] or 0 for d in uses)}}

    def logs(self, session_org: str, firm_org: str, pid: str) -> dict:
        """Entries a person may see: the firm sees all (for active clients); a client sees only its own."""
        p, group = self._participant(session_org, firm_org, pid)
        names = {c["org_id"]: c["label"] for c in p["clients"]}
        mine = lambda d: group == "FIRM" or d["client_org_id"] == session_org
        out = {}
        for kind, key in (("pilot_log", "time"), ("pilot_issue", "issues"), ("pilot_passport_use", "passport_uses")):
            rows = [{**{k: v for k, v in d.items() if k not in ("logged_by", "reported_by", "resolved_by")}, "client": names.get(d["client_org_id"], "?")}
                    for d in self._docs(kind, firm_org, pid) if mine(d)]
            out[key] = sorted(rows, key=lambda r: r.get("logged_at") or r.get("reported_at"), reverse=True)
        out["clients"] = [{"org_id": c["org_id"], "label": c["label"]} for c in self.active_clients(p)] if group == "FIRM" else [{"org_id": session_org, "label": names.get(session_org, "")}]
        out["group"] = group
        return out

    # ------------------------------------------------------------------ snapshots (aggregate only: no per-client figures are stored)
    def take_snapshot(self, firm_org: str, actor: str, pid: str, evaluation: dict, clients_included: int, clients_total: int) -> dict:
        p = self._pilot(firm_org, pid)
        if p["status"] == "PLANNING":
            raise PilotStateError("Start the pilot before taking snapshots.")
        body = {"id": str(uuid.uuid4()), "pilot_id": pid, "taken_at": self.now().isoformat(), "taken_by": actor, "clients_included": clients_included, "clients_total": clients_total,
                "measures": [{k: m[k] for k in ("key", "label", "source", "value", "unit", "target", "direction", "n", "status")} for m in evaluation["measures"]], "counts": evaluation["counts"]}
        body["hash"] = sha({k: v for k, v in body.items() if k != "hash"})
        self.store.put("pilot_snapshot", self._key(firm_org, pid, body["id"]), body, org_id=firm_org)
        self.log("PILOT_SNAPSHOT_TAKEN", actor, pid, firm_org, f"{evaluation['headline']} ({body['hash'][:12]})")
        return body

    def snapshots(self, firm_org: str, pid: str) -> List[dict]:
        self._pilot(firm_org, pid)
        return sorted(self._docs("pilot_snapshot", firm_org, pid), key=lambda s: s["taken_at"])
