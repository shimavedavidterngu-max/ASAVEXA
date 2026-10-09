from fastapi import APIRouter, Depends, HTTPException, Request

from ...identity.domain.enums import Role
from ...identity.services.service import IdentityService
from ...security.context import SecurityContext
from .. import ratelimit
from ..deps import get_bearer_token, get_current_actor, get_identity_service, get_security
from ..schemas.auth import (
    AddMembershipRequest,
    ChangeRoleRequest,
    LoginRequest,
    LoginResponse,
    MfaVerifyRequest,
    OidcCallbackRequest,
    OidcStartRequest,
    MembershipOut,
    OrganisationCreate,
    OrganisationOut,
    RegisterRequest,
    SelectOrganisationRequest,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["Authentication & Organisations"])
org_router = APIRouter(prefix="/organisations", tags=["Authentication & Organisations"])


@router.post("/register", response_model=UserOut, status_code=201)
def register(body: RegisterRequest, identity: IdentityService = Depends(get_identity_service)):
    return identity.register_user(body.email, body.password)


@router.post("/login", response_model=LoginResponse)
def login(request: Request, body: LoginRequest, security: SecurityContext = Depends(get_security)):
    """Password step. If the account has multi-factor sign-in on, no session is created yet: the response carries a
    short-lived single-use `challenge` that POST /auth/mfa/verify exchanges (with the authenticator code) for the session."""
    ratelimit.throttle(ratelimit.LOGIN, request)
    r = security.login(body.email, body.password, ratelimit.client_ip(request), request.headers.get("user-agent"))
    return LoginResponse(**r)


@router.post("/mfa/verify", response_model=LoginResponse)
def mfa_verify(request: Request, body: MfaVerifyRequest, security: SecurityContext = Depends(get_security)):
    ratelimit.throttle(ratelimit.MFA, request)
    return LoginResponse(**security.login_with_mfa(body.challenge, body.code, ratelimit.client_ip(request), request.headers.get("user-agent")))


@router.get("/oidc/config")
def oidc_config(security: SecurityContext = Depends(get_security)):
    """Lets the sign-in page show a single sign-on button only when it is actually set up."""
    return {"enabled": security.oidc_cfg is not None and security.keys is not None,
            "name": getattr(security.oidc_cfg, "name", None) if security.oidc_cfg else None}


@router.post("/oidc/start")
def oidc_start(request: Request, body: OidcStartRequest, security: SecurityContext = Depends(get_security)):
    ratelimit.throttle(ratelimit.OIDC, request)
    return security.oidc().start(body.binding)


@router.post("/oidc/callback", response_model=LoginResponse)
def oidc_callback(request: Request, body: OidcCallbackRequest, security: SecurityContext = Depends(get_security)):
    ratelimit.throttle(ratelimit.OIDC, request)
    return LoginResponse(**security.oidc_login(body.code, body.state, body.binding, ratelimit.client_ip(request), request.headers.get("user-agent")))


@router.post("/logout", status_code=204)
def logout(
    token: str = Depends(get_bearer_token),
    identity: IdentityService = Depends(get_identity_service),
):
    """Takes the raw bearer token directly (rather than depending on
    get_current_session) because only the token's hash is ever stored —
    IdentityService.logout re-hashes it to find the session itself."""
    identity.logout(token)


@router.get("/me", response_model=UserOut)
def get_me(
    actor: str = Depends(get_current_actor),
    identity: IdentityService = Depends(get_identity_service),
):
    user = identity.users.get(actor)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return user


@router.post("/select-organisation")
def select_organisation(
    body: SelectOrganisationRequest,
    token: str = Depends(get_bearer_token),
    identity: IdentityService = Depends(get_identity_service),
    security: SecurityContext = Depends(get_security),
):
    """Also takes the raw token directly, for the same reason as
    logout — select_organisation needs to look the session up by its
    token hash and then mutate it."""
    session = identity.select_organisation(token, body.org_id)
    security.check_session(session)
    security.gate_org(session, body.org_id)   # an organisation can require multi-factor sign-in before it can be opened
    # The frontend (frontend/src/app.js) destructures `{ role }` from
    # this response immediately after calling it — select_organisation
    # itself returns a Session, which has no role field (role lives on
    # the Membership, not the Session), so it must be looked up
    # separately via the same get_role() already used by
    # list_members() above. Without this, every "select organisation"
    # action looked successful but silently left the frontend's role
    # state undefined (visible on the Dashboard as "Role: undefined").
    role = identity.get_role(session.user_id, body.org_id)
    return {"org_id": session.org_id, "role": role.value if role else None}


# ----------------------------------------------------------------------
@org_router.post("", response_model=OrganisationOut, status_code=201)
def create_organisation(
    body: OrganisationCreate,
    actor: str = Depends(get_current_actor),
    identity: IdentityService = Depends(get_identity_service),
):
    """Creates the organisation and bootstraps the creator as its first
    OWNER in one step — mirrors the blueprint's onboarding sequence
    ("create account/organisation" as a single first step)."""
    org = identity.create_organisation(body.name, actor=actor)
    identity.add_membership(org.id, actor, Role.OWNER, actor_user_id=actor)
    return org


@org_router.get("/mine", response_model=list[OrganisationOut])
def list_my_organisations(
    actor: str = Depends(get_current_actor),
    identity: IdentityService = Depends(get_identity_service),
):
    memberships = identity.memberships.list_for_user(actor)
    orgs = [identity.organisations.get(m.org_id) for m in memberships if m.status.value == "ACTIVE"]
    return [o for o in orgs if o is not None]


@org_router.get("/{org_id}/members", response_model=list[MembershipOut])
def list_members(
    org_id: str,
    actor: str = Depends(get_current_actor),
    identity: IdentityService = Depends(get_identity_service),
):
    if identity.get_role(actor, org_id) is None:
        raise HTTPException(status_code=403, detail="You are not a member of this organisation.")
    return identity.list_members(org_id)


@org_router.post("/{org_id}/members", response_model=MembershipOut, status_code=201)
def add_member(
    org_id: str,
    body: AddMembershipRequest,
    actor: str = Depends(get_current_actor),
    identity: IdentityService = Depends(get_identity_service),
):
    """Permission (ORG_MANAGE_USERS) is enforced inside
    IdentityService.add_membership itself — no separate dependency
    needed here."""
    return identity.add_membership(org_id, body.user_id, body.role, actor_user_id=actor)


@org_router.patch("/{org_id}/members/{user_id}/role", response_model=MembershipOut)
def change_member_role(
    org_id: str,
    user_id: str,
    body: ChangeRoleRequest,
    actor: str = Depends(get_current_actor),
    identity: IdentityService = Depends(get_identity_service),
):
    return identity.change_role(org_id, user_id, body.role, actor_user_id=actor)


@org_router.delete("/{org_id}/members/{user_id}", response_model=MembershipOut)
def revoke_member(
    org_id: str,
    user_id: str,
    actor: str = Depends(get_current_actor),
    identity: IdentityService = Depends(get_identity_service),
):
    return identity.revoke_membership(org_id, user_id, actor_user_id=actor)
