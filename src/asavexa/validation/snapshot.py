"""The frozen picture of the platform's data that reviewers attest to. Counts and statuses only (no names, amounts or documents), and
deterministic: the same data always gives the same snapshot, so a later difference means the data really changed."""
from collections import Counter
from typing import Iterable, Optional


def _v(x):
    return getattr(x, "value", x)


def tally(items: Iterable, attr: str) -> dict:
    return dict(sorted(Counter(str(_v(getattr(i, attr, None)) or "UNKNOWN") for i in items).items()))


def build_snapshot(evidence=(), journals=(), periods=(), controls=(), executions=(), findings=(), audit_chain: Optional[dict] = None,
                   security: Optional[dict] = None) -> dict:
    evidence, journals, periods, controls, executions, findings = (list(x) for x in (evidence, journals, periods, controls, executions, findings))
    sec = security or {}
    return {
        "version": 1,
        "evidence": {"records": len(evidence), "by_status": tally(evidence, "status")},
        "ledger": {"journals": len(journals), "journals_by_status": tally(journals, "status"), "periods": len(periods), "periods_by_status": tally(periods, "status")},
        "controls": {"defined": len(controls), "active": sum(1 for c in controls if getattr(c, "active", True)), "executions": len(executions),
                     "executions_by_result": tally(executions, "result")},
        "findings": {"total": len(findings), "by_status": tally(findings, "status"), "by_severity": tally(findings, "severity")},
        "audit_chain": {"checked": bool(audit_chain and audit_chain.get("enabled")), "intact": (audit_chain or {}).get("ok")},
        "security": {"encryption_configured": bool((sec.get("encryption") or {}).get("configured")), "mfa_required": bool((sec.get("mfa") or {}).get("required")),
                     "members": (sec.get("mfa") or {}).get("members", 0), "members_with_mfa": (sec.get("mfa") or {}).get("with_mfa", 0),
                     "sso_configured": bool((sec.get("sso") or {}).get("configured")), "storage_enabled": bool((sec.get("storage") or {}).get("enabled")),
                     "audit_chain_enabled": bool((sec.get("audit_chain") or {}).get("enabled"))},
    }
