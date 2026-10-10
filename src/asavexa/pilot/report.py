"""A plain-text pilot report that can be printed or attached to a board paper. Built only from the computed results, never from anything else."""
from __future__ import annotations

SYMBOL = {"MET": "MET", "NOT_MET": "NOT MET", "INSUFFICIENT_DATA": "NOT ENOUGH DATA"}


def _fmt(v, unit):
    return "-" if v is None else f"{v:g} {unit}".strip()


def to_markdown(results: dict, snapshots: list | None = None) -> str:
    p, ev = results["pilot"], results["evaluation"]
    out = [f"# {p['name']}", "", f"Status: {p['status'].title()}  |  Started {p['start_date']}" + (f"  |  Ends {p['end_date']}" if p.get("end_date") else ""),
           f"Generated {results['generated_at']}", f"Clients included: {results['clients_included']} of {results['clients_total']}", "", f"**{ev['headline']}**", "", f"_{ev['caution']}_", "",
           "## The eleven measures", "", "| Measure | Source | Result | Target | Based on | Status |", "|---|---|---|---|---|---|"]
    for m in ev["measures"]:
        tgt = f"{m['direction']} {m['target']:g} {m['unit']}".strip()
        out.append(f"| {m['label']} | {m['source'].title()} | {_fmt(m['value'], m['unit'])} | {tgt} | {m['n']} {m['n_what']} | {SYMBOL[m['status']]} |")
    notes = [m for m in ev["measures"] if m.get("why")]
    if notes:
        out += ["", "## Notes", ""] + [f"- **{m['label']}:** {m['why']}" for m in notes]
    if results["skipped"]:
        out += ["", "## Left out", ""] + [f"- {s['label']}: {s['reason']}" for s in results["skipped"]]
    out += ["", "## Clients", ""]
    for c in results["clients"]:
        m = c["metrics"]
        out.append(f"- **{c['label']}** (consent: {c['consent_reference']}): " + (f"operational in {m['onboarding']['days_to_operational']:g} days" if m["onboarding"]["operational"] else "not yet operational") +
                   f"; evidence verified {_fmt(m['evidence']['verified_percent'], '%')}; reconciled {_fmt(m['reconciliation']['rate_percent'], '%')}")
    if snapshots:
        out += ["", "## Snapshots taken", ""] + [f"- {s['taken_at'][:10]}: {s['clients_included']} of {s['clients_total']} clients, fingerprint {s['hash'][:16]}" for s in snapshots]
    out += ["", "---", "This report comes from a small pilot. It shows what happened in these organisations, not what will happen elsewhere. Measures marked 'Reported' are what people told us, not what the system observed."]
    return "\n".join(out)
