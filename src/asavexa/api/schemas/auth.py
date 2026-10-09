from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr

from ...identity.domain.enums import MembershipStatus, Role


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    """Either a finished sign-in (user + token) or, when the account has multi-factor sign-in on, a challenge
    that /auth/mfa/verify turns into one."""
    user: Optional[UserOut] = None
    token: Optional[str] = None
    mfa_required: bool = False
    challenge: Optional[str] = None
    mfa_verified: bool = False


class MfaVerifyRequest(BaseModel):
    challenge: str
    code: str


class OidcStartRequest(BaseModel):
    binding: str


class OidcCallbackRequest(BaseModel):
    code: str
    state: str
    binding: str


class OrganisationCreate(BaseModel):
    name: str


class OrganisationOut(BaseModel):
    id: str
    name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SelectOrganisationRequest(BaseModel):
    org_id: str


class AddMembershipRequest(BaseModel):
    user_id: str
    role: Role


class ChangeRoleRequest(BaseModel):
    role: Role


class MembershipOut(BaseModel):
    id: str
    org_id: str
    user_id: str
    role: Role
    status: MembershipStatus
    created_at: datetime
    created_by: str

    model_config = {"from_attributes": True}
