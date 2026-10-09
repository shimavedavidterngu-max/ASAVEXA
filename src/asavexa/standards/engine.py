"""Resolves: Organisation -> Entity Type -> Jurisdiction -> Framework ->
Accounting Policies -> Reporting Requirements."""
from __future__ import annotations

from typing import Dict, List, Optional

from . import catalog as C
from .errors import (
    InvalidPolicyChoiceError,
    UnknownEntityTypeError,
    UnknownFrameworkError,
    UnknownJurisdictionError,
    UnknownPolicyError,
)

DISCLAIMER = (
    "These are suggested defaults, not legal or accounting advice. Confirm the framework "
    "with your regulator or a qualified accountant."
)


def list_catalog() -> dict:
    return {
        "jurisdictions": [{"code": k, "name": v} for k, v in C.JURISDICTIONS.items()],
        "entity_types": [{"code": k, "name": v} for k, v in C.ENTITY_TYPES.items()],
        "frameworks": [{"code": k, **v} for k, v in C.FRAMEWORKS.items()],
        "disclaimer": DISCLAIMER,
    }


def _check_inputs(jurisdiction: str, entity_type: str) -> None:
    if jurisdiction not in C.JURISDICTIONS:
        raise UnknownJurisdictionError(f"Unknown jurisdiction {jurisdiction!r}. Choose one from the list, or OTHER.")
    if entity_type not in C.ENTITY_TYPES:
        raise UnknownEntityTypeError(f"Unknown entity type {entity_type!r}.")


def recommend(jurisdiction: str, entity_type: str) -> dict:
    """The usual framework for this jurisdiction and entity type, with the
    chain of reasoning. Falls back to the generic rule when the
    jurisdiction has no specific one, and says so."""
    _check_inputs(jurisdiction, entity_type)
    rule = C.RULES.get((jurisdiction, entity_type))
    specific = rule is not None
    if rule is None:
        rule = C.RULES[("*", entity_type)]
    default, alternatives, rationale, confidence = rule
    jurisdiction_name = C.JURISDICTIONS[jurisdiction]
    note = None
    if not specific:
        note = (
            f"No specific rule is recorded for {jurisdiction_name} and this entity type, "
            "so the international default is shown. Confirm with the local regulator."
        )
        confidence = "confirm"
    return {
        "jurisdiction": jurisdiction,
        "entity_type": entity_type,
        "framework": default,
        "alternatives": list(alternatives),
        "rationale": rationale,
        "confidence": confidence,
        "specific_rule": specific,
        "note": note,
        "chain": [
            {"step": "Jurisdiction", "value": jurisdiction_name},
            {"step": "Entity type", "value": C.ENTITY_TYPES[entity_type]},
            {"step": "Reporting framework", "value": C.FRAMEWORKS[default]["name"]},
        ],
    }


def policies_for(framework: str, overrides: Optional[Dict[str, str]] = None) -> List[dict]:
    """The accounting policies that apply under `framework`, with the
    effective choice for each (the organisation's override if valid,
    otherwise the framework default). Raises on an override that is not
    allowed — in particular on a treatment the framework forbids."""
    if framework not in C.FRAMEWORKS:
        raise UnknownFrameworkError(f"Unknown reporting framework {framework!r}.")
    overrides = overrides or {}
    known = {p["code"] for p in C.POLICIES}
    for code in overrides:
        if code not in known:
            raise UnknownPolicyError(f"Unknown accounting policy {code!r}.")
    result = []
    for policy in C.POLICIES:
        spec = policy["by_framework"].get(framework)
        if spec is None:
            if policy["code"] in overrides:
                raise InvalidPolicyChoiceError(
                    f"The policy {policy['name']!r} does not apply under {C.FRAMEWORKS[framework]['name']}."
                )
            continue
        chosen = overrides.get(policy["code"])
        if chosen is not None:
            if chosen not in spec["options"]:
                allowed = ", ".join(C.OPTION_LABELS.get(o, o) for o in spec["options"])
                raise InvalidPolicyChoiceError(
                    f"{C.OPTION_LABELS.get(chosen, chosen)!r} is not permitted for {policy['name']} under "
                    f"{C.FRAMEWORKS[framework]['name']}. Allowed: {allowed}."
                )
        effective = chosen if chosen is not None else spec["default"]
        result.append({
            "code": policy["code"],
            "name": policy["name"],
            "description": policy["description"],
            "note": policy["note"],
            "locked": spec["locked"],
            "options": [{"code": o, "label": C.OPTION_LABELS.get(o, o)} for o in spec["options"]],
            "default": spec["default"],
            "effective": effective,
            "overridden": chosen is not None and chosen != spec["default"],
        })
    return result


def requirements_for(framework: str, entity_type: str) -> List[dict]:
    if framework not in C.FRAMEWORKS:
        raise UnknownFrameworkError(f"Unknown reporting framework {framework!r}.")
    out = []
    for r in C.REQUIREMENTS.get(framework, []):
        if r["entity_types"] and entity_type not in r["entity_types"]:
            continue
        out.append({
            "code": r["code"], "name": r["name"], "description": r["description"],
            "mandatory": r["mandatory"],
            "available": r["report_key"] is not None,
            "report_key": r["report_key"],
        })
    return out


def readiness(requirements: List[dict]) -> dict:
    mandatory = [r for r in requirements if r["mandatory"]]
    available = [r for r in mandatory if r["available"]]
    return {
        "mandatory_total": len(mandatory),
        "mandatory_available": len(available),
        "missing": [r["name"] for r in mandatory if not r["available"]],
    }


def resolve_configuration(
    jurisdiction: str, entity_type: str, framework: Optional[str] = None,
    policy_overrides: Optional[Dict[str, str]] = None,
) -> dict:
    """The full resolved configuration for an organisation."""
    rec = recommend(jurisdiction, entity_type)
    chosen = framework or rec["framework"]
    if chosen not in C.FRAMEWORKS:
        raise UnknownFrameworkError(f"Unknown reporting framework {chosen!r}.")
    warnings: List[str] = []
    if rec["note"]:
        warnings.append(rec["note"])
    if chosen != rec["framework"]:
        name = C.FRAMEWORKS[chosen]["name"]
        usual = C.FRAMEWORKS[rec["framework"]]["name"]
        if chosen in rec["alternatives"]:
            warnings.append(f"{name} is a recognised alternative here; the usual choice is {usual}.")
        else:
            warnings.append(
                f"{name} is not a usual choice for this jurisdiction and entity type (usual: {usual}). "
                "Confirm with your regulator before relying on it."
            )
    policies = policies_for(chosen, policy_overrides)
    requirements = requirements_for(chosen, entity_type)
    ready = readiness(requirements)
    if ready["missing"]:
        warnings.append(
            "ASAVEXA cannot yet produce these mandatory statements: " + "; ".join(ready["missing"]) + "."
        )
    return {
        "jurisdiction": jurisdiction,
        "entity_type": entity_type,
        "framework": chosen,
        "recommendation": rec,
        "chain": [
            {"step": "Jurisdiction", "value": C.JURISDICTIONS[jurisdiction]},
            {"step": "Entity type", "value": C.ENTITY_TYPES[entity_type]},
            {"step": "Reporting framework", "value": C.FRAMEWORKS[chosen]["name"]},
            {"step": "Accounting policies", "value": f"{len(policies)} policies configured"},
            {"step": "Reporting requirements", "value": f"{len(requirements)} requirements ({ready['mandatory_available']}/{ready['mandatory_total']} mandatory available in ASAVEXA)"},
        ],
        "policies": policies,
        "requirements": requirements,
        "readiness": ready,
        "warnings": warnings,
        "disclaimer": DISCLAIMER,
    }
