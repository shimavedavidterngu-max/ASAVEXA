"""Live architecture check: confirms every layer in the ASAVEXA architecture diagram is really present and wired, not just drawn.
Each layer lists the Python modules that must import and the API prefixes that must be mounted. Nothing here touches data."""
import importlib
from typing import Dict, List

LAYERS: List[dict] = [
    {"id": "financial_core", "group": "Core", "name": "Financial Core", "parts": ["Journals", "Accounts", "Periods", "Reconciliation", "Reports"],
     "modules": ["asavexa.accounting.services.engine", "asavexa.reconciliation.services.service", "asavexa.reporting.services.service", "asavexa.period_close.services.service"],
     "prefixes": ["/accounts", "/periods", "/journals", "/reconciliations", "/reports", "/period-close"]},
    {"id": "evidence_layer", "group": "Core", "name": "Evidence Layer", "parts": ["Evidence Vault", "Documents", "Evidence graph", "Provenance", "Audit trail"],
     "modules": ["asavexa.evidence.services.vault", "asavexa.audit.repository", "asavexa.proofgraph.graph"],
     "prefixes": ["/evidence", "/audit", "/proof"]},
    {"id": "identity", "group": "Core", "name": "Identity", "parts": ["Users", "Organisations", "Memberships", "Roles", "Permissions"],
     "modules": ["asavexa.identity.services.service", "asavexa.identity.domain.permissions"],
     "prefixes": ["/auth", "/organisations"]},
    {"id": "standards", "group": "Standards", "name": "Standards Engine", "parts": ["IFRS", "IFRS for SMEs", "US GAAP", "IPSAS", "Local GAAP"],
     "modules": ["asavexa.standards.engine", "asavexa.standards.catalog"], "prefixes": ["/standards", "/organisation-profile"]},
    {"id": "reporting", "group": "Reporting", "name": "Reporting Engine", "parts": ["Trial balance", "Income statement", "Balance sheet", "General ledger"],
     "modules": ["asavexa.reporting.services.service"], "prefixes": ["/reports"]},
    {"id": "proof_graph", "group": "Reporting", "name": "Proof-to-Report Graph", "parts": ["Report", "Line", "Journal", "Evidence"],
     "modules": ["asavexa.proofgraph.graph"], "prefixes": ["/proof"]},
    {"id": "audit", "group": "Use", "name": "Audit", "parts": ["Audit workspace", "Professional validation", "Compliance"],
     "modules": ["asavexa.validation.catalog", "asavexa.compliance.services.service"], "prefixes": ["/audit", "/validation", "/compliance"]},
    {"id": "passport", "group": "Use", "name": "Passport", "parts": ["Financial Passport", "Permissioned sharing"],
     "modules": ["asavexa.passport.builder", "asavexa.passport.sharing"], "prefixes": ["/passport", "/shared-passport"]},
    {"id": "ai", "group": "Use", "name": "AI", "parts": ["ASAVEXA AI", "External data ingestion"],
     "modules": ["asavexa.ai", "asavexa.ingestion"], "prefixes": ["/ai", "/ingestion"]},
    {"id": "trust_network", "group": "Network", "name": "Trust Network", "parts": ["Banks", "Investors", "Auditors", "Donors", "Regulators", "Accountants"],
     "modules": ["asavexa.network.service", "asavexa.pilot.service", "asavexa.security.store"], "prefixes": ["/network", "/pilot", "/security"]},
]

# The links the diagram draws between layers; each is checked as "both ends present".
FLOWS = [("financial_core", "evidence_layer"), ("evidence_layer", "identity"), ("financial_core", "standards"), ("standards", "reporting"),
         ("reporting", "proof_graph"), ("proof_graph", "audit"), ("proof_graph", "passport"), ("proof_graph", "ai"),
         ("audit", "trust_network"), ("passport", "trust_network"), ("ai", "trust_network")]


def _is_mounted(prefix: str, route_paths: List[str]) -> bool:
    return any(p == prefix or p.startswith(prefix + "/") for p in route_paths)


def check_architecture(route_paths: List[str]) -> dict:
    layers = []
    for spec in LAYERS:
        problems, ok_modules = [], []
        for m in spec["modules"]:
            try:
                importlib.import_module(m)
                ok_modules.append(m)
            except Exception as exc:                                   # noqa: BLE001  report the real reason, never hide it
                problems.append(f"module {m} failed to load: {type(exc).__name__}: {exc}")
        missing = [p for p in spec["prefixes"] if not _is_mounted(p, route_paths)]
        problems += [f"API prefix {p} is not mounted" for p in missing]
        layers.append({"id": spec["id"], "group": spec["group"], "name": spec["name"], "parts": spec["parts"], "ok": not problems,
                       "modules_ok": len(ok_modules), "modules_total": len(spec["modules"]), "prefixes": spec["prefixes"], "problems": problems})
    by_id: Dict[str, dict] = {l["id"]: l for l in layers}
    flows = [{"from": a, "to": b, "ok": by_id[a]["ok"] and by_id[b]["ok"]} for a, b in FLOWS]
    return {"ok": all(l["ok"] for l in layers), "layers": layers, "flows": flows,
            "note": "This confirms the layers load and their API routes are mounted. It does not run your data; use Connection & Self-Test for that."}
