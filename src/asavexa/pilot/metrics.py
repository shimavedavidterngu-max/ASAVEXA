"""Measures taken from the platform's own records for ONE client organisation in the pilot. Pure functions: no database, no clock (the
caller passes `now`), so every number can be re-derived and checked by hand.

Everything here is MEASURED from what actually happened in the system. Things only people can say (satisfaction, how long audit
preparation took before, whether the Passport helped) are collected separately and never mixed into these numbers."""
from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional

from ..identity.domain.permissions import JOURNAL_CREATE, role_has_permission
from ..passport.builder import PassportInputs, build_evidence_quality, build_passport

# Actions that are not "work" (signing in, switching organisation, security/validation/pilot bookkeeping).
NON_WORK_PREFIXES = ("LOGIN_", "MFA_", "ORG_CONTEXT", "SESSION", "VALIDATION_", "PILOT_", "AI_", "KEY_", "SECURITY_", "AUDIT_CHAIN", "ALERT_", "RETENTION_",
                     "LEGAL_HOLD", "PRIVACY_", "VENDOR_", "EVIDENCE_DOWNLOADED", "BACKUP_", "USER_REGISTERED", "MEMBERSHIP_")
CORRECTION_ACTIONS = ("JOURNAL_REVERSED", "JOURNAL_DRAFT_DELETED", "EVIDENCE_REJECTED", "MATCH_REJECTED", "RECONCILIATION_REJECTED", "CLOSE_REJECTED",
                      "SENT_BACK", "REMEDIATION_REJECTED")
FEATURES = (("journals", ("JOURNAL_",)), ("evidence", ("EVIDENCE_",)), ("reconciliation", ("RECONCILIATION_", "MATCH_", "MANUAL_MATCH", "TRANSACTION_", "CANDIDATE_")),
            ("reports", ("REPORT_GENERATED",)), ("period_close", ("CLOSE_", "PERIOD_")), ("controls", ("CONTROL_", "FINDING_", "REMEDIATION_")), ("passport", ("PASSPORT_GENERATED",)))
OPEN_FINDING = ("OPEN", "UNDER_REVIEW", "REMEDIATION_REQUIRED", "RESOLVED")
STALE_DRAFT_DAYS = 7
OPERATIONAL = ("ACCOUNTS", "JOURNAL_POSTED", "EVIDENCE", "BANK_IMPORT")
MILESTONES = (("ACCOUNTS", "Chart of accounts set up"), ("JOURNAL_POSTED", "First journal posted"), ("EVIDENCE", "First evidence uploaded"),
              ("BANK_IMPORT", "First bank statement imported"), ("RECONCILIATION", "First reconciliation approved"), ("REPORT", "First report generated"),
              ("PASSPORT", "First Passport generated"))


def aware(dt) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _v(x):
    return getattr(x, "value", x)


def pct(part, whole) -> Optional[float]:
    return round(part * 100.0 / whole, 1) if whole else None


def is_work(e) -> bool:
    return not str(e.action).startswith(NON_WORK_PREFIXES)


def _first(values: Iterable[Optional[datetime]]) -> Optional[datetime]:
    vs = [aware(v) for v in values if v is not None]
    return min(vs) if vs else None


def client_metrics(inp: PassportInputs, events: list, kickoff: datetime, now: datetime, firm_user_ids: Iterable[str] = (), window_days: int = 30) -> dict:
    kickoff, now = aware(kickoff), aware(now)
    firm_ids = set(firm_user_ids)
    events = [e for e in events if aware(e.timestamp) <= now]
    by_action: Dict[str, list] = {}
    for e in events:
        by_action.setdefault(str(e.action), []).append(e)
    first_event = lambda *acts: _first(e.timestamp for a in acts for e in by_action.get(a, []))

    # ---- onboarding
    reached = {
        "ACCOUNTS": _first([a.created_at for a in inp.accounts] + [e.timestamp for e in by_action.get("ACCOUNT_CREATED", [])]),
        "JOURNAL_POSTED": _first(j.posted_at for j in inp.journals if j.posted_at),
        "EVIDENCE": _first(e.uploaded_at for e in inp.evidence),
        "BANK_IMPORT": _first(t.created_at for t in inp.bank_transactions),
        "RECONCILIATION": _first(r.approved_at for r in inp.reconciliations if r.approved_at),
        "REPORT": first_event("REPORT_GENERATED"),
        "PASSPORT": first_event("PASSPORT_GENERATED"),
    }
    days_from = lambda t: round(max(0.0, (t - kickoff).total_seconds() / 86400.0), 1)
    ms = [{"key": k, "label": lbl, "reached_at": reached[k].isoformat() if reached[k] else None, "days": days_from(reached[k]) if reached[k] else None} for k, lbl in MILESTONES]
    operational = all(reached[k] for k in OPERATIONAL)
    onboarding = {"kickoff": kickoff.isoformat(), "milestones": ms, "reached": sum(1 for m in ms if m["reached_at"]), "total": len(ms), "operational": operational,
                  "days_to_operational": days_from(max(reached[k] for k in OPERATIONAL)) if operational else None,
                  "days_since_kickoff": round(max(0.0, (now - kickoff).total_seconds() / 86400.0), 1)}

    # ---- transaction processing
    posted = [j for j in inp.journals if _v(j.status) in ("POSTED", "REVERSED")]
    hours = [round((aware(j.posted_at) - aware(j.created_at)).total_seconds() / 3600.0, 2) for j in posted if j.posted_at and j.created_at]
    hours = [max(0.0, h) for h in hours]
    drafts = [j for j in inp.journals if _v(j.status) == "DRAFT"]
    stale = [j for j in drafts if aware(j.created_at) <= now - timedelta(days=STALE_DRAFT_DAYS)]
    reversed_n = sum(1 for j in inp.journals if _v(j.status) == "REVERSED")
    processing = {"journals_posted": len(posted), "drafts_open": len(drafts), "stale_drafts": len(stale), "median_hours_to_post": round(statistics.median(hours), 1) if hours else None,
                  "reversed": reversed_n, "reversal_rate_percent": pct(reversed_n, len(posted)), "_hours": hours}

    # ---- evidence, reconciliation, exceptions (the Passport's own definitions, so the two never disagree)
    eq = build_evidence_quality(inp)
    t = eq["transactions"]
    evidence = {"posted": t["total_posted"], "with_any_percent": t["with_any_evidence_percent"], "verified_percent": t["supported_percent"], "verified": t["supported_verified"],
                "unverified": t["evidence_unverified"], "defective": t["evidence_defective"], "missing": t["missing_evidence"], "records": eq["evidence_records"]}
    br = eq["bank_reconciliation"]
    approved_recs = sum(1 for r in inp.reconciliations if _v(r.status) in ("RECONCILED",))
    reconciliation = {"bank_transactions": br["bank_transactions"], "reconciled": br["reconciled"], "unreconciled": br["unreconciled"],
                      "rate_percent": pct(br["reconciled"], br["bank_transactions"]), "reconciliations": len(inp.reconciliations), "reconciliations_approved": approved_recs}
    kinds: Dict[str, int] = {}
    for x in eq["exceptions"]["items"]:
        kinds[x["kind"]] = kinds.get(x["kind"], 0) + 1
    handled = t["total_posted"] + br["bank_transactions"]
    open_findings = sum(1 for f in inp.findings if _v(f.status) in OPEN_FINDING)
    exceptions = {"count": eq["exceptions"]["count"], "items_handled": handled, "per_100": round(eq["exceptions"]["count"] * 100.0 / handled, 1) if handled else None,
                  "open_findings": open_findings, "by_kind": kinds}

    # ---- reports
    gen, failed = len(by_action.get("REPORT_GENERATED", [])), len(by_action.get("REPORT_GENERATION_FAILED", []))
    rtypes = sorted({str(_v(getattr(e, "entity_type", "")) or "") for e in by_action.get("REPORT_GENERATED", [])} - {""})
    reports = {"generated": gen, "failed": failed, "success_percent": pct(gen, gen + failed), "periods_closed": sum(1 for p in inp.periods if _v(p.status) in ("LOCKED", "CLOSED")),
               "last_generated_at": max((aware(e.timestamp) for e in by_action.get("REPORT_GENERATED", [])), default=None), "kinds": rtypes}
    if reports["last_generated_at"]:
        reports["last_generated_at"] = reports["last_generated_at"].isoformat()

    # ---- corrections ("user errors" the system can see)
    work = [e for e in events if is_work(e)]
    corr = [e for e in work if str(e.action) in CORRECTION_ACTIONS]
    cb: Dict[str, int] = {}
    for e in corr:
        cb[str(e.action)] = cb.get(str(e.action), 0) + 1
    errors = {"corrections": len(corr), "work_actions": len(work), "per_100_actions": round(len(corr) * 100.0 / len(work), 1) if work else None, "breakdown": cb}

    # ---- adoption by the firm's accountants
    since = now - timedelta(days=window_days)
    member_acc = sorted({m.user_id for m in inp.memberships if _v(m.status) == "ACTIVE" and role_has_permission(m.role, JOURNAL_CREATE) and m.user_id in firm_ids})
    recent = [e for e in work if aware(e.timestamp) >= since and e.actor in member_acc]
    active = sorted({e.actor for e in recent})
    weeks_total = max(1, int(onboarding["days_since_kickoff"] // 7) + (1 if onboarding["days_since_kickoff"] % 7 else 0))
    weeks_active = {int((aware(e.timestamp) - kickoff).total_seconds() // (7 * 86400)) for e in work if e.actor in member_acc and aware(e.timestamp) >= kickoff}
    feats = sorted(name for name, pre in FEATURES if any(str(e.action).startswith(pre) for e in work if e.actor in member_acc))
    adoption = {"accountants_assigned": len(member_acc), "accountants_active": len(active), "rate_percent": pct(len(active), len(member_acc)), "window_days": window_days,
                "actions_in_window": len(recent), "active_weeks": len(weeks_active), "weeks_elapsed": weeks_total, "features_used": feats, "_assigned": member_acc, "_active": active}

    # ---- Passport
    summ = build_passport(inp, None, now)["summary"]
    ok_sections = [k for k, v in summ["sections"].items() if v == "ok"]
    passport = {"generated": len(by_action.get("PASSPORT_GENERATED", [])), "shares_created": len(by_action.get("PASSPORT_SHARE_CREATED", [])),
                "shares_viewed": len(by_action.get("PASSPORT_SHARE_VIEWED", [])), "shares_downloaded": len(by_action.get("PASSPORT_SHARE_DOWNLOADED", [])),
                "sections_ok": len(ok_sections), "sections_total": len(summ["sections"]), "sections_needing_attention": [k for k, v in summ["sections"].items() if v != "ok"]}
    return {"onboarding": onboarding, "processing": processing, "evidence": evidence, "reconciliation": reconciliation, "exceptions": exceptions, "reports": reports,
            "errors": errors, "adoption": adoption, "passport": passport}


def aggregate(clients: List[dict]) -> dict:
    """Combines client metrics. Ratios are recomputed from summed counts (never an average of percentages)."""
    S = lambda path: sum((_get(c, path) or 0) for c in clients)
    hours = [h for c in clients for h in c["processing"]["_hours"]]
    done = [c["onboarding"]["days_to_operational"] for c in clients if c["onboarding"]["days_to_operational"] is not None]
    posted, bank = S("evidence.posted"), S("reconciliation.bank_transactions")
    handled = posted + bank
    assigned = sorted({u for c in clients for u in c["adoption"]["_assigned"]})
    active = sorted({u for c in clients for u in c["adoption"]["_active"]})
    gen, fail = S("reports.generated"), S("reports.failed")
    work = S("errors.work_actions")
    return {
        "clients": len(clients),
        "onboarding": {"completed": len(done), "not_completed": len(clients) - len(done), "median_days": round(statistics.median(done), 1) if done else None,
                       "worst_days": max(done) if done else None, "days": sorted(done)},
        "processing": {"journals_posted": S("processing.journals_posted"), "drafts_open": S("processing.drafts_open"), "stale_drafts": S("processing.stale_drafts"),
                       "median_hours_to_post": round(statistics.median(hours), 1) if hours else None, "reversed": S("processing.reversed")},
        "evidence": {"posted": posted, "verified": S("evidence.verified"), "missing": S("evidence.missing"), "unverified": S("evidence.unverified"), "defective": S("evidence.defective"),
                     "with_any_percent": pct(posted - S("evidence.missing"), posted), "verified_percent": pct(S("evidence.verified"), posted)},
        "reconciliation": {"bank_transactions": bank, "reconciled": S("reconciliation.reconciled"), "rate_percent": pct(S("reconciliation.reconciled"), bank)},
        "exceptions": {"count": S("exceptions.count"), "items_handled": handled, "per_100": round(S("exceptions.count") * 100.0 / handled, 1) if handled else None, "open_findings": S("exceptions.open_findings")},
        "reports": {"generated": gen, "failed": fail, "success_percent": pct(gen, gen + fail), "clients_with_a_report": sum(1 for c in clients if c["reports"]["generated"] > 0)},
        "errors": {"corrections": S("errors.corrections"), "work_actions": work, "per_100_actions": round(S("errors.corrections") * 100.0 / work, 1) if work else None},
        "adoption": {"accountants_assigned": len(assigned), "accountants_active": len(active), "rate_percent": pct(len(active), len(assigned)),
                     "clients_with_activity": sum(1 for c in clients if c["adoption"]["actions_in_window"] > 0)},
        "passport": {"generated": S("passport.generated"), "shares_created": S("passport.shares_created"), "shares_viewed": S("passport.shares_viewed"), "shares_downloaded": S("passport.shares_downloaded"),
                     "clients_with_passport": sum(1 for c in clients if c["passport"]["generated"] > 0)},
    }


def _get(d, path):
    for k in path.split("."):
        d = d[k]
    return d


def public(client: dict) -> dict:
    """Strips internal working lists (raw hours, user ids) before a client's metrics are shown."""
    out = {k: dict(v) for k, v in client.items()}
    out["processing"].pop("_hours", None)
    out["adoption"].pop("_assigned", None); out["adoption"].pop("_active", None)
    return out
