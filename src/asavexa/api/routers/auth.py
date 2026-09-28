from fastapi import APIRouter, Depends, HTTPException

from ...identity.domain.enums import Role
from ...identity.services.service import IdentityService
from ..deps import get_bearer_token, get_current_actor, get_identity_service
from ..schemas.auth import (
    AddMembershipRequest,
    ChangeRoleRequest,
    LoginRequest,
    LoginResponse,
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
def login(body: LoginRequest, identity: IdentityService = Depends(get_identity_service)):
    user, token = identity.authenticate(body.email, body.password)
    return LoginResponse(user=user, token=token)


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
):
    """Also takes the raw token directly, for the same reason as
    logout — select_organisation needs to look the session up by its
    token hash and then mutate it."""
    session = identity.select_organisation(token, body.org_id)
    return {"org_id": session.org_id}


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
