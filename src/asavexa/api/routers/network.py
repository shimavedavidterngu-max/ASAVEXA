"""ASAVEXA Network endpoints: businesses connected to accountants, auditors, banks, investors, donors and regulators. Thin: rules live in asavexa.network.

- Setting the profile, inviting, accepting, changing or ending a connection needs network:manage (owners and administrators) in YOUR organisation.
- Any signed-in member of an organisation can see its connections, and a member of the VIEWING organisation can open what a connection allows.
  Opening checks, every time, that the connection is active, unexpired and made with the viewer's own organisation.
- Wrong invitation codes are kept (committed) so the lock-out counts them even though the request ends in an error."""
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...identity.domain.errors import PermissionDeniedError
from ...identity.domain.permissions import NETWORK_MANAGE
from ...identity.services.service import IdentityService
from ...network.errors import NetworkError, NetworkForbiddenError
from ...network.service import NetworkService, TYPES, TYPE_TEXT, default_grant
from ...passport.sharing import SCOPES, build_share_content, share_fingerprint
from ..deps import get_current_actor, get_current_org, get_identity_service, get_network, get_session, require_permission

router = APIRouter(prefix="/network", tags=["ASAVEXA Network"])
_manage = Depends(require_permission(NETWORK_MANAGE))
DISCLAIMER = ("This is a view of the information the business chose to share with you, built from its own records at the moment you opened it. "
              "It is not an audit opinion or a guarantee. The fingerprint lets you check later that a copy you kept has not been altered.")


class ProfileBody(BaseModel):
    org_type: str
    display_name: str
    description: str = ""


class GrantBody(BaseModel):
    scopes: Optional[List[str]] = None
    include_detail: Optional[bool] = None
    closed_periods_only: Optional[bool] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None


class InviteBody(BaseModel):
    counterparty_type: str
    purpose: str
    grant: Optional[GrantBody] = None
    invite_days: int = 14
    connection_days: int = 90
    note: str = ""


class CodeBody(BaseModel):
    code: str


class AcceptBody(BaseModel):
    code: str
    grant: Optional[GrantBody] = None
    connection_days: Optional[int] = None


class UpdateBody(BaseModel):
    grant: Optional[GrantBody] = None
    extend_days: Optional[int] = None


class EndBody(BaseModel):
    reason: str


def _g(b: Optional[GrantBody]) -> Optional[dict]:
    return b.model_dump(exclude_none=True) if b is not None else None


def _can_manage(identity: IdentityService, actor: str, org: str) -> bool:
    try:
        identity.require_permission(actor, org, NETWORK_MANAGE)
        return True
    except PermissionDeniedError:
        return False


@router.get("/guide")
def guide():
    return {"types": {t: TYPE_TEXT[t] for t in TYPES}, "scopes": list(SCOPES), "default_grant": default_grant(datetime.now(timezone.utc).date()),
            "how_it_works": ["Data flows from a business to an accountant, auditor, bank, investor, donor or regulator.", "The business always decides what is shared. Others can ask for more; the business can say less.",
                             "Both sides must agree, using a one-time code given by one side and entered by the other.", "Either side can end a connection at any time. It also ends by itself on its expiry date.",
                             "Everything is written to both organisations' audit trails."]}


@router.get("/me")
def me(actor: str = Depends(get_current_actor), org: str = Depends(get_current_org), identity: IdentityService = Depends(get_identity_service), svc: NetworkService = Depends(get_network)):
    return {**svc.overview(org), "can_manage": _can_manage(identity, actor, org)}


@router.put("/profile", dependencies=[_manage])
def set_profile(body: ProfileBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: NetworkService = Depends(get_network)):
    return svc.set_profile(org, actor, body.org_type, body.display_name, body.description)


# ------------------------------------------------------------------ invitations
@router.get("/invites", dependencies=[_manage])
def invites(org: str = Depends(get_current_org), svc: NetworkService = Depends(get_network)):
    return svc.list_invites(org)


@router.post("/invites", dependencies=[_manage], status_code=201)
def create_invite(body: InviteBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: NetworkService = Depends(get_network)):
    return svc.create_invite(org, actor, body.counterparty_type, body.purpose, _g(body.grant), body.invite_days, body.connection_days, body.note)


@router.post("/invites/{invite_id}/cancel", dependencies=[_manage])
def cancel_invite(invite_id: str, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: NetworkService = Depends(get_network)):
    return svc.cancel_invite(org, actor, invite_id)


@router.post("/invites/preview", dependencies=[_manage])
def preview(body: CodeBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: NetworkService = Depends(get_network), session=Depends(get_session)):
    try:
        return svc.preview_invite(org, actor, body.code)
    except NetworkError:
        session.commit()      # keep the failed attempt: it counts toward the lock-out
        raise


@router.post("/invites/accept", dependencies=[_manage], status_code=201)
def accept(body: AcceptBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: NetworkService = Depends(get_network), session=Depends(get_session)):
    try:
        return svc.accept_invite(org, actor, body.code, _g(body.grant), body.connection_days)
    except NetworkError:
        session.commit()
        raise


# ------------------------------------------------------------------ connections
@router.get("/connections")
def connections(org: str = Depends(get_current_org), svc: NetworkService = Depends(get_network)):
    return svc.list_connections(org)


@router.put("/connections/{conn_id}", dependencies=[_manage])
def update(conn_id: str, body: UpdateBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: NetworkService = Depends(get_network)):
    return svc.update_grant(org, actor, conn_id, _g(body.grant), body.extend_days)


@router.post("/connections/{conn_id}/end", dependencies=[_manage])
def end(conn_id: str, body: EndBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: NetworkService = Depends(get_network)):
    return svc.revoke(org, actor, conn_id, body.reason)


@router.get("/connections/{conn_id}/access-log", dependencies=[_manage])
def access_log(conn_id: str, org: str = Depends(get_current_org), svc: NetworkService = Depends(get_network)):
    """For the business: which organisation looked, and when. Not who personally."""
    return [{"at": r["at"], "viewer": r["viewer_name"], "fingerprint": r["fingerprint"]} for r in svc.access_log(org, conn_id)]


def build_view(svc: NetworkService, session, identity: IdentityService, actor: str, org: str, conn_id: str, gather) -> dict:
    """What a connected organisation sees. The business's own data is read only AFTER the connection has passed every check."""
    if identity.get_role(actor, org) is None:
        raise NetworkForbiddenError("This connection is not active, so its information cannot be opened.")
    conn, req = svc.authorize_view(org, actor, conn_id)
    now = datetime.now(timezone.utc)
    inp = gather(session, conn["provider_org"])
    sections, included, excluded = build_share_content(inp, req, now)
    meta = {"organisation": (inp.profile or {}).get("legal_name") or conn["provider_name"], "viewer": conn["viewer_name"], "purpose": conn["purpose"], "scopes": req["scopes"],
            "include_detail": req["include_detail"], "closed_periods_only": req["closed_periods_only"], "date_from": req["date_from"].isoformat(), "date_to": req["date_to"].isoformat(),
            "expires_at": conn["expires_at"], "taken_at": now.isoformat(),
            "periods_included": [{"name": p.name, "start_date": p.start_date.isoformat(), "end_date": p.end_date.isoformat(), "status": getattr(p.status, "value", p.status)} for p in included],
            "periods_excluded": excluded}
    fp = share_fingerprint(meta, sections)
    svc.record_view(conn, actor, fp)
    return {"connection": svc.public(conn, org), "share": meta, "sections": sections, "fingerprint": fp, "disclaimer": DISCLAIMER}


@router.get("/connections/{conn_id}/passport")
def view_passport(conn_id: str, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), identity: IdentityService = Depends(get_identity_service),
                  svc: NetworkService = Depends(get_network), session=Depends(get_session)):
    from .passport import gather_inputs
    return build_view(svc, session, identity, actor, org, conn_id, gather_inputs)
