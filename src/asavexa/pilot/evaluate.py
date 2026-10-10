"""Turns measured figures and people-reported figures into the eleven pilot measures, each judged against a target.

Honest by construction: a measure with too little data says INSUFFICIENT_DATA and why; it is never passed or failed on a handful of records.
There is no overall score. With a few client organisations the results are indicative, not statistically significant."""
from typing import Dict, List, Optional

DEFAULT_TARGETS: Dict[str, float] = {
    "onboarding_days": 14.0,              # median days from kickoff until accounts, a posted journal, evidence and a bank import all exist (<=)
    "processing_median_hours": 48.0,      # median hours from draft to posted (<=)
    "evidence_verified_percent": 90.0,    # posted journals supported by VERIFIED evidence (>=)
    "reconciliation_rate_percent": 95.0,  # bank transactions reconciled (>=)
    "exceptions_per_100": 5.0,            # exceptions per 100 journals + bank transactions handled (<=)
    "report_success_percent": 95.0,       # report runs that succeeded; every client must also have produced one (>=)
    "audit_prep_saved_percent": 30.0,     # reported time saved on audit preparation versus the baseline (>=)
    "corrections_per_100_actions": 5.0,   # reversals, deleted drafts, rejections per 100 work actions (<=)
    "satisfaction_score": 4.0,            # mean overall rating 1-5 (>=)
    "accountant_adoption_percent": 75.0,  # firm accountants active in the last 30 days (>=)
    "passport_useful_score": 4.0,         # mean "the Passport was useful" rating 1-5 (>=)
}
TARGET_LABELS = {
    "onboarding_days": "Onboarding time (days, at most)", "processing_median_hours": "Draft to posted (hours, at most)", "evidence_verified_percent": "Evidence verified (% at least)",
    "reconciliation_rate_percent": "Reconciliation rate (% at least)", "exceptions_per_100": "Exceptions per 100 (at most)", "report_success_percent": "Report success (% at least)",
    "audit_prep_saved_percent": "Audit-prep time saved (% at least)", "corrections_per_100_actions": "Corrections per 100 actions (at most)", "satisfaction_score": "Satisfaction (1-5, at least)",
    "accountant_adoption_percent": "Accountant adoption (% at least)", "passport_useful_score": "Passport useful (1-5, at least)",
}
MIN_N = {"processing": 5, "evidence": 10, "reconciliation": 10, "exceptions": 20, "errors": 50, "survey": 3, "paired_time": 2}
LIMITS = {"onboarding_days": (1, 90), "processing_median_hours": (1, 720), "evidence_verified_percent": (1, 100), "reconciliation_rate_percent": (1, 100), "exceptions_per_100": (0, 100),
          "report_success_percent": (1, 100), "audit_prep_saved_percent": (1, 99), "corrections_per_100_actions": (0, 100), "satisfaction_score": (1, 5),
          "accountant_adoption_percent": (1, 100), "passport_useful_score": (1, 5)}


def clean_targets(given: Optional[dict]) -> Dict[str, float]:
    out = dict(DEFAULT_TARGETS)
    for k, v in (given or {}).items():
        if k not in DEFAULT_TARGETS:
            raise ValueError(f"Unknown target '{k}'.")
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError(f"{TARGET_LABELS[k]} must be a number.")
        lo, hi = LIMITS[k]
        if not lo <= v <= hi:
            raise ValueError(f"{TARGET_LABELS[k]} must be between {lo} and {hi}.")
        out[k] = float(v)
    return out


def _m(key, label, source, value, unit, target, direction, n, min_n, what, detail="", need=None):
    """One measure. direction '>=' or '<='. INSUFFICIENT_DATA when there is no value or fewer than min_n records."""
    if value is None or n < min_n:
        # Too little to judge: the headline value is withheld (a figure from two records looks more certain than it is) but shown in words.
        status, why = "INSUFFICIENT_DATA", need or f"Needs at least {min_n} {what}; has {n}." + (f" So far: {value:g} {unit}.".replace("  ", " ") if value is not None else "")
        value = None
    else:
        status, why = ("MET" if (value >= target if direction == ">=" else value <= target) else "NOT_MET"), ""
    return {"key": key, "label": label, "source": source, "value": value, "unit": unit, "target": target, "direction": direction, "n": n, "n_what": what, "status": status, "why": why, "detail": detail}


def evaluate(agg: dict, reported: dict, targets: Dict[str, float], clients: List[dict]) -> dict:
    T = targets
    on, pr, ev, rc, ex, rp, er, ad, pp = (agg[k] for k in ("onboarding", "processing", "evidence", "reconciliation", "exceptions", "reports", "errors", "adoption", "passport"))
    tm, sv, pu = reported["time"], reported["survey"], reported["passport_uses"]
    ms: List[dict] = []

    late = [c for c in clients if not c["onboarding"]["operational"] and c["onboarding"]["days_since_kickoff"] > T["onboarding_days"]]
    m = _m("onboarding", "Onboarding time", "MEASURED", on["median_days"], "days", T["onboarding_days"], "<=", on["completed"], 1, "client organisations that finished onboarding",
           f"{on['completed']} of {agg['clients']} operational (accounts, a posted journal, evidence and a bank import all in place); slowest {on['worst_days']} days." if on["completed"] else "",
           need=f"No client has finished onboarding yet ({agg['clients']} in the pilot).")
    if late and m["status"] == "MET":
        m["status"], m["why"] = "NOT_MET", f"{len(late)} client(s) are past {T['onboarding_days']:g} days since kickoff and still not operational."
    ms.append(m)
    ms.append(_m("processing", "Transaction processing", "MEASURED", pr["median_hours_to_post"], "hours (median, draft to posted)", T["processing_median_hours"], "<=", pr["journals_posted"], MIN_N["processing"],
                 "posted journals", f"{pr['journals_posted']} posted, {pr['drafts_open']} drafts open ({pr['stale_drafts']} older than 7 days), {pr['reversed']} reversed."))
    ms.append(_m("evidence", "Evidence completeness", "MEASURED", ev["verified_percent"], "% of posted journals with verified evidence", T["evidence_verified_percent"], ">=", ev["posted"], MIN_N["evidence"],
                 "posted journals", f"{ev['verified']} verified, {ev['unverified']} unverified, {ev['defective']} defective, {ev['missing']} with none; any evidence at all: {ev['with_any_percent']}%."))
    ms.append(_m("reconciliation", "Reconciliation rate", "MEASURED", rc["rate_percent"], "% of bank transactions reconciled", T["reconciliation_rate_percent"], ">=", rc["bank_transactions"], MIN_N["reconciliation"],
                 "bank transactions", f"{rc['reconciled']} of {rc['bank_transactions']} reconciled."))
    ms.append(_m("exceptions", "Exception rate", "MEASURED", ex["per_100"], "per 100 items handled", T["exceptions_per_100"], "<=", ex["items_handled"], MIN_N["exceptions"],
                 "journals and bank transactions", f"{ex['count']} exceptions across {ex['items_handled']} items; {ex['open_findings']} open finding(s)."))
    r = _m("reports", "Report generation", "MEASURED", rp["success_percent"], "% of report runs that succeeded", T["report_success_percent"], ">=", rp["generated"] + rp["failed"], 1, "report runs",
           f"{rp['generated']} generated, {rp['failed']} failed; {rp['clients_with_a_report']} of {agg['clients']} clients have produced a report." + (f" Reported time: {tm['report']['minutes']} min over {tm['report']['entries']} entries." if tm["report"]["entries"] else ""))
    if r["status"] == "MET" and rp["clients_with_a_report"] < agg["clients"]:
        r["status"], r["why"] = "NOT_MET", f"{agg['clients'] - rp['clients_with_a_report']} client(s) have not produced a report yet."
    ms.append(r)
    ms.append(_m("audit_prep", "Audit preparation time", "REPORTED", tm["audit_prep"]["saved_percent"], "% time saved against the baseline", T["audit_prep_saved_percent"], ">=", tm["audit_prep"]["paired_entries"],
                 MIN_N["paired_time"], "audit-preparation entries with a baseline", f"{tm['audit_prep']['entries']} logged, {tm['audit_prep']['minutes']} min taken against {tm['audit_prep']['baseline_minutes']} min baseline (self-reported)."))
    ms.append(_m("errors", "User errors", "MEASURED", er["per_100_actions"], "corrections per 100 work actions", T["corrections_per_100_actions"], "<=", er["work_actions"], MIN_N["errors"], "work actions",
                 f"{er['corrections']} corrections (reversals, deleted drafts, rejections). People also reported {reported['issues']['user_errors']} user error(s) and {reported['issues']['open']} open issue(s) in total."))
    ms.append(_m("satisfaction", "User satisfaction", "REPORTED", sv["overall_mean"], "mean overall rating (1-5)", T["satisfaction_score"], ">=", sv["respondents"], MIN_N["survey"], "survey respondents",
                 f"Recommend score {sv['nps']}; ease {sv['ease_mean']}; trust in numbers {sv['trust_mean']}; accountants {sv['by_group']['FIRM']['n']}, clients {sv['by_group']['CLIENT']['n']}."))
    ms.append(_m("adoption", "Accountant adoption", "MEASURED", ad["rate_percent"], "% of firm accountants active in 30 days", T["accountant_adoption_percent"], ">=", ad["accountants_assigned"], 1,
                 "firm accountants with access to a pilot client", f"{ad['accountants_active']} of {ad['accountants_assigned']} active; {ad['clients_with_activity']} of {agg['clients']} clients had activity."))
    ms.append(_m("passport", "Passport usefulness", "REPORTED", sv["passport_useful"]["mean"], "mean 'Passport was useful' rating (1-5)", T["passport_useful_score"], ">=", sv["passport_useful"]["n"], MIN_N["survey"],
                 "ratings of the Passport",
                 f"{pp['generated']} generated; {pp['shares_created']} shared, {pp['shares_viewed']} views, {pp['shares_downloaded']} downloads by others; {pu['total']} real uses logged "
                 f"({pu['helpful']} helpful, {pu['partly']} partly, {pu['not_helpful']} not helpful)."))
    c = {s: sum(1 for x in ms if x["status"] == s) for s in ("MET", "NOT_MET", "INSUFFICIENT_DATA")}
    return {"measures": ms, "counts": c, "headline": f"{c['MET']} met, {c['NOT_MET']} not met, {c['INSUFFICIENT_DATA']} need more data",
            "caution": f"Based on {agg['clients']} client organisation(s). Treat results as indicative, not statistically significant. Self-reported measures reflect what people said, not what the system observed."}
