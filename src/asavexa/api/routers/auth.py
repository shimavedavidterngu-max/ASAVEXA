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
    RecoveryRequestIn,
    RecoveryResetIn,
    RecoveryVerifyIn,
    MembershipOut,
    OrganisationCreate,
    OrganisationOut,
    RegisterRequest,
    RegisterResponse,
    VerificationConfirmIn,
    VerificationRequestIn,
    SelectOrganisationRequest,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["Authentication & Organisations"])
org_router = APIRouter(prefix="/organisations", tags=["Authentication & Organisations"])


@router.get("/password-policy")
def password_policy_info():
    """The password rules, so the sign-up and reset screens show exactly what the server enforces."""
    from ...identity.domain import password_policy as pp
    return {"min_length": pp.MIN_LENGTH, "max_length": pp.MAX_LENGTH, "requirements": pp.REQUIREMENTS}


@router.post("/register", response_model=RegisterResponse, status_code=201)
def register(body: RegisterRequest, identity: IdentityService = Depends(get_identity_service), security: SecurityContext = Depends(get_security),
             request: Request = None):
    """Creates the account, then sends the welcome email and the 6-digit verification code. The account is kept even if the email
    cannot be sent; `email_delivery.sent` says truthfully whether the provider accepted it. A second sign-up with the same address
    fails with 409 before any email is sent, so a double click can never send two."""
    if request is not None:
        ratelimit.throttle(ratelimit.REGISTER, request)
    if body.confirm_password is not None and body.confirm_password != body.password:
        raise HTTPException(status_code=422, detail="The two passwords do not match.")
    user = identity.register_user(body.email, body.password)
    delivery = security.verification.on_registered(user)
    return RegisterResponse(id=user.id, email=user.email, is_active=user.is_active, created_at=user.created_at, email_delivery=delivery)


# ---- email verification: confirm the address with a 6-digit code (same generic answers for real and unknown emails)
@router.get("/verification/status")
def verification_status(security: SecurityContext = Depends(get_security)):
    """Lets the sign-up screen say honestly when email is not set up, instead of promising a code that will never come."""
    return {"available": security.verification.available}


@router.post("/verification/request")
def verification_request(request: Request, body: VerificationRequestIn, security: SecurityContext = Depends(get_security)):
    ratelimit.throttle(ratelimit.VERIFY_REQUEST, request)
    return security.verification.request(body.email)


@router.post("/verification/confirm")
def verification_confirm(request: Request, body: VerificationConfirmIn, security: SecurityContext = Depends(get_security)):
    ratelimit.throttle(ratelimit.VERIFY_CONFIRM, request)
    return security.verification.confirm(body.email, body.code)


@router.get("/email-status")
def email_status(actor: str = Depends(get_current_actor), security: SecurityContext = Depends(get_security)):
    """Whether the signed-in person's email address has been verified."""
    return {"email_verified": security.verification.is_verified(actor)}


# ---- password recovery: request a code, verify it, set a new password. Every answer is the same for real and unknown emails.
@router.get("/recovery/status")
def recovery_status(security: SecurityContext = Depends(get_security)):
    """Lets the screen say honestly when email is not set up, instead of promising a code that will never come."""
    return {"available": security.recovery.available}


@router.post("/recovery/request")
def recovery_request(request: Request, body: RecoveryRequestIn, security: SecurityContext = Depends(get_security)):
    ratelimit.throttle(ratelimit.RECOVERY_REQUEST, request)
    return security.recovery.request(body.email)


@router.post("/recovery/verify")
def recovery_verify(request: Request, body: RecoveryVerifyIn, security: SecurityContext = Depends(get_security)):
    ratelimit.throttle(ratelimit.RECOVERY_VERIFY, request)
    return security.recovery.verify(body.email, body.code)


@router.post("/recovery/reset")
def recovery_reset(request: Request, body: RecoveryResetIn, security: SecurityContext = Depends(get_security)):
    ratelimit.throttle(ratelimit.RECOVERY_RESET, request)
    return security.recovery.reset(body.email, body.reset_token, body.new_password, body.confirm_password)


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
