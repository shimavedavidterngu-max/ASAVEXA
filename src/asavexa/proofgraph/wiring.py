"""Connects the stored Proof-to-Action graph to the platform's audit trail and to the stores it reads record names from."""


def make_log(security):
    def log(action, actor, entity_id, org, reason=""):
        security.log(action, actor, entity_id, org_id=org, entity_type="ProofLink", reason=reason)
    return log


def make_sources(store, vault, compliance):
    """How the graph reaches each kind of record. Everything is looked up BY organisation, so a record from another organisation is simply 'not found'.
    Reads only; the graph never changes any of these records."""
    from .links import NodeSource

    def doc(kind, label_of, order=None):
        def label(org, rid):
            d = store.get(kind, f"{org}:{rid}")
            return label_of(d) if d is not None and d.get("org") == org else None

        def choices(org):
            rows = [d for _, d in store.list(kind, org_id=org) if d.get("org") == org]
            if order:
                rows.sort(key=order)
            return [(d["id"], label_of(d)) for d in rows]
        return NodeSource(label, choices)

    def evidence_label(e): return f"{e.original_filename} ({e.type.value})"

    def ev_label(org, rid):
        e = vault.get_evidence(org, rid)
        return evidence_label(e) if e.org_id == org else None

    def control_label(org, rid):
        c = compliance.get_control(org, rid)
        return f"{c.code} {c.name}" if c.org_id == org else None

    def finding_label(org, rid):
        f = compliance.get_finding(org, rid)
        return f"{f.severity.value}: {f.description[:80]}" if f.org_id == org else None

    def remediation_label(org, rid):
        r = compliance.get_remediation(org, rid)
        return f"Fix: {r.action[:80]}" if r.org_id == org else None

    def remediation_choices(org):
        out = []
        for f in compliance.list_findings(org):
            if f.remediation_id:
                try:
                    out.append((f.remediation_id, remediation_label(org, f.remediation_id)))
                except Exception:
                    continue
        return out

    return {
        "evidence": NodeSource(ev_label, lambda org: [(e.id, evidence_label(e)) for e in vault.list_for_org(org)]),
        "control": NodeSource(control_label, lambda org: [(c.id, f"{c.code} {c.name}") for c in compliance.list_controls(org)]),
        "finding": NodeSource(finding_label, lambda org: [(f.id, f"{f.severity.value}: {f.description[:80]}") for f in compliance.list_findings(org)]),
        "remediation": NodeSource(remediation_label, remediation_choices),
        "outcome": doc("evr_case", lambda d: f"{d.get('ref') or d['id'][:8]}: {str(d.get('status'))}"),
        "standard": doc("std_source", lambda d: f"{d['framework']}: {d['title']}"[:200]),
        "decision": doc("agent_decision", lambda d: f"{d['agent_name']}: {d['action']}"),
        "risk": doc("grc_risk", lambda d: f"{d['ref']} {d.get('title') or ''}".strip()),
        "action": doc("grc_action", lambda d: f"{d.get('ref') or d['id'][:8]} {d.get('title') or ''}".strip()),
    }
