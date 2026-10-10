"""Puts the pilot's results together: measured figures from each client's own records, plus what people reported.

The data access is passed in (not imported) so the same code is exercised in tests with plain objects. The one rule that matters here is
privacy: the person asking only gets figures for client organisations they are *themselves* entitled to read. A client the viewer cannot read
is listed as "no access" and left out of every total, so a total can never be used to work out a figure the viewer is not allowed to see."""
from __future__ import annotations

from datetime import datetime
from typing import Callable, Iterable, List

from .evaluate import evaluate
from .metrics import aggregate, client_metrics, public


def compute_results(svc, firm_org: str, pid: str, *, can_read: Callable[[str], bool], fetch_inputs: Callable[[str], object], fetch_events: Callable[[str], list],
                    firm_user_ids: Iterable[str], now: datetime, include_comments: bool = False) -> dict:
    p = svc.view(firm_org, pid)
    firm_ids = list(firm_user_ids)
    rows, included, skipped = [], [], []
    for c in svc.active_clients(p):
        label = c["label"]
        if not can_read(c["org_id"]):
            skipped.append({"org_id": c["org_id"], "label": label, "reason": "You do not have permission to read this client's records, so it is left out of every figure."})
            continue
        try:
            m = client_metrics(fetch_inputs(c["org_id"]), fetch_events(c["org_id"]), datetime.fromisoformat(c["kickoff"]), now, firm_ids)
        except Exception as exc:   # a client whose data cannot be read must not silently vanish or sink the whole page
            skipped.append({"org_id": c["org_id"], "label": label, "reason": f"Its records could not be read ({type(exc).__name__}). It is left out of every figure."})
            continue
        included.append(m)
        rows.append({"org_id": c["org_id"], "label": label, "kickoff": c["kickoff"], "consent_reference": c["consent_reference"], "metrics": public(m)})
    agg = aggregate(included)
    inc = {r["org_id"] for r in rows}
    scoped = {**p, "clients": [c if c["org_id"] in inc or not c["active"] else {**c, "active": False} for c in p["clients"]]}   # reported figures follow the same visibility
    reported = svc.reported(scoped, include_comments)
    ev = evaluate(agg, reported, p["targets"], included)
    if skipped:
        ev["caution"] = f"{len(skipped)} of {len(svc.active_clients(p))} client(s) are not included in these figures. Treat the totals as partial. " + (ev.get("caution") or "")
    return {"pilot": {k: p[k] for k in ("id", "name", "status", "start_date", "end_date", "targets")}, "generated_at": now.isoformat(), "evaluation": ev,
            "clients": rows, "skipped": skipped, "reported": reported, "clients_included": len(included), "clients_total": len(svc.active_clients(p))}
