"""
The Identity / Organisation / Multi-Tenant module.

Public entry point: `asavexa.identity.services.service.IdentityService`.
Owns Organisation, User, Membership and Session. This is the entire
tenant-isolation boundary for Asavexa — every other module (Accounting,
Evidence, ...) trusts an already-resolved `org_id` and `actor`, and
should never re-implement authentication or permission checks itself.
"""
from .services.service import IdentityService  # noqa: F401
