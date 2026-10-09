"""Security & infrastructure endpoints. Thin: every rule lives in asavexa.security.* and is tested there.

Personal routes (/security/me/...) need only a signed-in session, so a person can set up multi-factor sign-in even when
their organisation already requires it. Organisation routes need security:manage (owners and administrators)."""
from typing import List, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ...identity.domain.errors import PermissionDeniedError
from ...identity.domain.permissions import AUDIT_READ, SECURITY_MANAGE
from ...identity.domain.enums import Role
from ...identity.services.service import IdentityService
from ...evidence.services.vault import EvidenceVault
from ...security.context import SecurityContext
from ...security.errors import NotFoundError, ValidationError
from ..deps import (get_current_actor, get_current_org, get_current_session, get_evidence_vault, get_identity_service, get_security,
                    require_permission)
from .. import ratelimit

router = APIRouter(prefix="/security", tags=["Security & Infrastructure"])
_manage = Depends(require_permission(SECURITY_MANAGE))


class CodeBody(BaseModel):
    code: str


class SettingsBody(BaseModel):
    require_mfa: Optional[bool] = None
    allowed_regions: Optional[List[str]] = None


class RetentionBody(BaseModel):
    evidence_days: int


class HoldBody(BaseModel):
    reason: str
    evidence_id: Optional[str] = None


class DisposeBody(BaseModel):
    reason: str


class DecideBody(BaseModel):
    approve: bool
    note: str = ""


class AckBody(BaseModel):
    note: str


class VendorBody(BaseModel):
    name: str
    purpose: str = ""
    data_categories: List[str] = []
    region: str = ""
    dpa_signed: bool = False
    security_attestation: str = ""
    subprocessors_known: Optional[bool] = None
    exit_plan: bool = False
    status: str = "ACTIVE"
    last_reviewed: Optional[str] = None
    owner: str = ""
    notes: str = ""


class RotateBody(BaseModel):
    to_key_id: Optional[str] = None


def _members(identity: IdentityService, org_id: str):
    ms = [m for m in identity.list_members(org_id) if m.status.value == "ACTIVE"]
    ids = [m.user_id for m in ms]
    emails = [u.email for u in (identity.users.get(i) for i in ids) if u]
    return ids, emails


# ------------------------------------------------------------------ personal: multi-factor
@router.get("/me")
def my_security(session=Depends(get_current_session), security: SecurityContext = Depends(get_security)):
    uid = session.user_id
    meta = security.guard.meta(session)
    return {
        "mfa": security.mfa.status(uid) if security.keys is not None else {"enabled": False, "available": False},
        "mfa_available": security.keys is not None,
        "this_session": {"id": session.id, "auth_method": meta.get("auth_method"), "mfa_verified": bool(meta.get("mfa_verified_at"))},
        "sessions": [security.guard.public(m) for m in security.guard.list_for_user(uid, include_current=session.id)],
        "privacy_requests": security.privacy.requests(user_id=uid),
        "idle_minutes": security.guard.policy.idle_minutes,
    }


@router.post("/me/mfa/begin")
def mfa_begin(request: Request, session=Depends(get_current_session), security: SecurityContext = Depends(get_security)):
    ratelimit.throttle(ratelimit.MFA, request)
    return security.mfa_begin(session.user_id)


@router.post("/me/mfa/confirm")
def mfa_confirm(request: Request, body: CodeBody, session=Depends(get_current_session), security: SecurityContext = Depends(get_security)):
    ratelimit.throttle(ratelimit.MFA, request)
    return security.mfa_confirm(session.user_id, body.code, session)


@router.post("/me/mfa/disable", status_code=204)
def mfa_disable(request: Request, body: CodeBody, session=Depends(get_current_session), security: SecurityContext = Depends(get_security),
                identity: IdentityService = Depends(get_identity_service)):
    ratelimit.throttle(ratelimit.MFA, request)
    orgs = [m.org_id for m in identity.memberships.list_for_user(session.user_id) if m.status.value == "ACTIVE"]
    security.mfa_disable(session.user_id, body.code, orgs)


@router.post("/me/mfa/recovery-codes")
def mfa_recovery(request: Request, body: CodeBody, session=Depends(get_current_session), security: SecurityContext = Depends(get_security)):
    ratelimit.throttle(ratelimit.MFA, request)
    return {"recovery_codes": security.mfa.regenerate_recovery(session.user_id, body.code)}


# ------------------------------------------------------------------ personal: sessions
@router.delete("/me/sessions/{session_id}", status_code=204)
def revoke_session(session_id: str, session=Depends(get_current_session), security: SecurityContext = Depends(get_security)):
    security.guard.revoke(session.user_id, session_id)


@router.post("/me/sessions/revoke-others")
def revoke_other_sessions(session=Depends(get_current_session), security: SecurityContext = Depends(get_security)):
    return {"revoked": security.guard.revoke_others(session.user_id, session.id)}


# ------------------------------------------------------------------ personal: privacy
@router.get("/me/export")
def export_my_data(actor: str = Depends(get_current_actor), security: SecurityContext = Depends(get_security)):
    return security.privacy.export(actor)


@router.post("/me/erasure-request")
def request_erasure(actor: str = Depends(get_current_actor), security: SecurityContext = Depends(get_security)):
    return security.privacy.request_erasure(actor)


# ------------------------------------------------------------------ organisation: overview and settings
@router.get("/overview", dependencies=[_manage])
def overview(org_id: str = Depends(get_current_org), identity: IdentityService = Depends(get_identity_service),
             security: SecurityContext = Depends(get_security)):
    ids, _ = _members(identity, org_id)
    return security.overview(org_id, ids)


@router.put("/settings", dependencies=[_manage])
def update_settings(body: SettingsBody, org_id: str = Depends(get_current_org), actor: str = Depends(get_current_actor),
                    security: SecurityContext = Depends(get_security)):
    before = security.settings.get(org_id)
    after = security.settings.update(org_id, actor, require_mfa=body.require_mfa, allowed_regions=body.allowed_regions)
    security.log("SECURITY_SETTINGS_CHANGED", actor, org_id, org_id=org_id, entity_type="Organisation",
                 reason=f"require_mfa {before['require_mfa']}->{after['require_mfa']}; regions {before['allowed_regions']}->{after['allowed_regions']}")
    return after


@router.get("/members", dependencies=[_manage])
def member_security(org_id: str = Depends(get_current_org), identity: IdentityService = Depends(get_identity_service),
                    security: SecurityContext = Depends(get_security)):
    """Who has multi-factor on. Never exposes secrets."""
    out = []
    for m in identity.list_members(org_id):
        u = identity.users.get(m.user_id)
        out.append({"user_id": m.user_id, "email": u.email if u else None, "role": m.role.value, "status": m.status.value,
                    "mfa": bool(security.mfa.is_enabled(m.user_id)) if security.keys is not None else False})
    return out


# ------------------------------------------------------------------ organisation: keys, audit chain, health
@router.post("/keys/rotate", dependencies=[_manage])
def rotate_keys(body: RotateBody, org_id: str = Depends(get_current_org), actor: str = Depends(get_current_actor),
                security: SecurityContext = Depends(get_security)):
    r = security.require_blobs().rotate(org_id, body.to_key_id)
    security.log("KEY_ROTATION_RUN", actor, org_id, org_id=org_id, entity_type="Organisation", reason=f"{r['rotated']} re-wrapped, {r['failed']} failed")
    return r


@router.get("/audit/verify", dependencies=[Depends(require_permission(AUDIT_READ))])
def verify_audit(org_id: str = Depends(get_current_org), security: SecurityContext = Depends(get_security)):
    return security.verify_audit(org_id)


@router.get("/health", dependencies=[_manage])
def detailed_health(security: SecurityContext = Depends(get_security)):
    h = security.health()
    return JSONResponse(status_code=200 if h["status"] != "DOWN" else 503, content=h)


# ------------------------------------------------------------------ organisation: alerts
@router.get("/alerts", dependencies=[_manage])
def list_alerts(status: Optional[str] = None, org_id: str = Depends(get_current_org), security: SecurityContext = Depends(get_security)):
    return security.alerts.list(org_id, status=status)


@router.post("/alerts/refresh", dependencies=[_manage])
def refresh_alerts(org_id: str = Depends(get_current_org), identity: IdentityService = Depends(get_identity_service),
                   security: SecurityContext = Depends(get_security)):
    ids, emails = _members(identity, org_id)
    r = security.refresh_alerts(org_id, ids, emails)
    return {**r, "alerts": security.alerts.list(org_id)}


@router.post("/alerts/{alert_id}/acknowledge", dependencies=[_manage])
def acknowledge_alert(alert_id: str, body: AckBody, org_id: str = Depends(get_current_org), actor: str = Depends(get_current_actor),
                      security: SecurityContext = Depends(get_security)):
    return security.alerts.acknowledge(org_id, alert_id, actor, body.note)


# ------------------------------------------------------------------ organisation: retention
@router.get("/retention", dependencies=[_manage])
def retention(org_id: str = Depends(get_current_org), vault: EvidenceVault = Depends(get_evidence_vault),
              security: SecurityContext = Depends(get_security)):
    return {"policy": security.retention.policy(org_id), "holds": security.retention.holds(org_id),
            "due_for_disposal": security.retention.candidates(org_id, vault.list_for_org(org_id))}


@router.put("/retention", dependencies=[_manage])
def set_retention(body: RetentionBody, org_id: str = Depends(get_current_org), actor: str = Depends(get_current_actor),
                  security: SecurityContext = Depends(get_security)):
    r = security.retention.set_policy(org_id, actor, body.evidence_days)
    security.log("RETENTION_POLICY_CHANGED", actor, org_id, org_id=org_id, entity_type="Organisation", reason=f"evidence kept {body.evidence_days} days")
    return r


@router.post("/retention/holds", dependencies=[_manage], status_code=201)
def place_hold(body: HoldBody, org_id: str = Depends(get_current_org), actor: str = Depends(get_current_actor),
               vault: EvidenceVault = Depends(get_evidence_vault), security: SecurityContext = Depends(get_security)):
    if body.evidence_id:
        vault.get_evidence(org_id, body.evidence_id)          # must exist in THIS organisation
    h = security.retention.place_hold(org_id, actor, body.reason, body.evidence_id)
    security.log("LEGAL_HOLD_PLACED", actor, org_id, org_id=org_id, entity_type="Organisation", reason=h["reason"])
    return h


@router.post("/retention/holds/{hold_id}/release", dependencies=[_manage])
def release_hold(hold_id: str, org_id: str = Depends(get_current_org), actor: str = Depends(get_current_actor),
                 security: SecurityContext = Depends(get_security)):
    h = security.retention.release_hold(org_id, hold_id, actor)
    security.log("LEGAL_HOLD_RELEASED", actor, org_id, org_id=org_id, entity_type="Organisation", reason=h.get("reason") or "")
    return h


@router.post("/retention/dispose/{evidence_id}", dependencies=[_manage])
def dispose_evidence(evidence_id: str, body: DisposeBody, org_id: str = Depends(get_current_org), actor: str = Depends(get_current_actor),
                     vault: EvidenceVault = Depends(get_evidence_vault), security: SecurityContext = Depends(get_security)):
    record = vault.get_evidence(org_id, evidence_id)
    r = security.retention.dispose(org_id, record, actor, body.reason)
    security.log("EVIDENCE_DISPOSED", actor, evidence_id, org_id=org_id, entity_type="EvidenceRecord", reason=body.reason[:300])
    return r


# ------------------------------------------------------------------ organisation: privacy requests
@router.get("/privacy/requests", dependencies=[_manage])
def privacy_requests(org_id: str = Depends(get_current_org), security: SecurityContext = Depends(get_security)):
    return security.privacy.requests(org_id=org_id)


@router.post("/privacy/requests/{request_id}/decide", dependencies=[_manage])
def decide_privacy_request(request_id: str, body: DecideBody, org_id: str = Depends(get_current_org), actor: str = Depends(get_current_actor),
                           identity: IdentityService = Depends(get_identity_service), security: SecurityContext = Depends(get_security)):
    r = next((x for x in security.privacy.requests(org_id=org_id) if x["id"] == request_id), None)
    if r is None:
        raise NotFoundError("Request not found in this organisation.")
    if identity.get_role(actor, org_id) != Role.OWNER:
        raise PermissionDeniedError("Only an owner can decide an erasure request.")
    return security.privacy.decide(request_id, actor, body.approve, body.note)


# ------------------------------------------------------------------ organisation: residency and vendors
@router.get("/residency", dependencies=[_manage])
def residency(org_id: str = Depends(get_current_org), security: SecurityContext = Depends(get_security)):
    return security.residency.report(org_id, getattr(security.objects, "data_region", "unspecified") if security.objects else "unspecified",
                                     security.database_region)


@router.get("/vendors", dependencies=[_manage])
def vendors(org_id: str = Depends(get_current_org), security: SecurityContext = Depends(get_security)):
    return security.vendors.list(org_id)


@router.post("/vendors", dependencies=[_manage], status_code=201)
def add_vendor(body: VendorBody, org_id: str = Depends(get_current_org), actor: str = Depends(get_current_actor),
               security: SecurityContext = Depends(get_security)):
    return security.vendors.add(org_id, actor, body.model_dump())


@router.put("/vendors/{vendor_id}", dependencies=[_manage])
def update_vendor(vendor_id: str, body: VendorBody, org_id: str = Depends(get_current_org), actor: str = Depends(get_current_actor),
                  security: SecurityContext = Depends(get_security)):
    return security.vendors.update(org_id, vendor_id, actor, body.model_dump())


@router.post("/vendors/seed", dependencies=[_manage])
def seed_vendors(org_id: str = Depends(get_current_org), actor: str = Depends(get_current_actor), security: SecurityContext = Depends(get_security)):
    return security.vendors.seed_platform_vendors(org_id, actor)
