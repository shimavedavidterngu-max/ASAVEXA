"""Request throttling for the sign-in endpoints, and the caller's network address.
In-memory: each server instance counts separately (the platform runs one instance today; see docs/security-hardening.md)."""
from fastapi import HTTPException, Request

from ..security.monitoring import RateLimiter

LOGIN = RateLimiter(limit=20, window_seconds=60)       # per client address
MFA = RateLimiter(limit=10, window_seconds=60)
OIDC = RateLimiter(limit=20, window_seconds=60)


def client_ip(request: Request) -> str:
    """Render and Vercel sit behind a proxy: the first X-Forwarded-For hop is the caller."""
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "unknown")[:64]


def throttle(limiter: RateLimiter, request: Request) -> None:
    ok, wait = limiter.allow(client_ip(request))
    if not ok:
        raise HTTPException(status_code=429, detail=f"Too many attempts. Please wait {wait} seconds and try again.", headers={"Retry-After": str(wait)})
