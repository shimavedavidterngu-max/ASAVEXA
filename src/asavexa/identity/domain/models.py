"""
Domain models for the Identity / Organisation / Multi-Tenant module.

Plain dataclasses, no framework dependency — same discipline as the
Accounting Engine (Blueprint Rule 19).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .enums import MembershipStatus, Role


@dataclass
class Organisation:
    """A tenant. Every other org-scoped record in Asavexa (accounts,
    journals, evidence, ...) is partitioned by `org_id` referencing this."""
    id: str
    name: str
    created_at: datetime


@dataclass
class User:
    """
    A person who can authenticate. A User is global — not scoped to one
    organisation — because the same person may belong to more than one
    organisation (e.g. an external auditor across several clients).
    Which organisations they can act in, and with what role, is entirely
    determined by their Membership records.
    """
    id: str
    email: str
    password_hash: str
    is_active: bool
    created_at: datetime
    mfa_enabled: bool = False  # placeholder — see README, real MFA not implemented yet


@dataclass
class Membership:
    """
    The only thing that grants a User any access to an Organisation's
    data. No Membership, no access — this is the entire tenant-isolation
    boundary (Blueprint: "no organisation may access another
    organisation's data unless an explicit authorised sharing mechanism
    exists").
    """
    id: str
    org_id: str
    user_id: str
    role: Role
    status: MembershipStatus
    created_at: datetime
    created_by: str


@dataclass
class Session:
    """
    An authenticated session. `token_hash` is the SHA-256 of the opaque
    bearer token handed to the client — the raw token itself is never
    stored, only ever returned once at login (Blueprint: security
    engineering — secrets are never persisted in recoverable form).

    `org_id` is the session's *currently selected* organisation context,
    set by `select_organisation` after login. It is None immediately
    after login — a user must explicitly select which organisation they
    are acting in before doing anything org-scoped.
    """
    id: str
    user_id: str
    token_hash: str
    created_at: datetime
    expires_at: datetime
    org_id: Optional[str] = None
    revoked_at: Optional[datetime] = None
