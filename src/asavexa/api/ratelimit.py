"""Request throttling for the sign-in endpoints, and the caller's network address.

By default each server instance counts separately (in memory; the platform runs one instance today). Set RATE_LIMIT_BACKEND=postgres, after
`alembic upgrade head` has created the rate_limit_hits table, and every instance counts together in the database. If the database cannot be reached
the limiter falls back to counting per instance, so a database problem never locks people out. See docs/stage9-rate-limiting.md."""
import os

from fastapi import HTTPException, Request

from ..security.monitoring import RateLimiter  # noqa: F401  (re-exported: tests and routes use ratelimit.RateLimiter)
from ..security.sharedlimit import SharedRateLimiter, SqlHitStore, make_limiter

BACKEND = os.environ.get("RATE_LIMIT_BACKEND", "memory").strip().lower()


def _store():
    if BACKEND != "postgres":
        return None
    from .db.base import get_engine
    return SqlHitStore(lambda: get_engine().raw_connection(), "%s")


_S = _store()
LOGIN = make_limiter("login", 20, 60, BACKEND, _S)       # per client address
MFA = make_limiter("mfa", 10, 60, BACKEND, _S)
OIDC = make_limiter("oidc", 20, 60, BACKEND, _S)
RECOVERY_REQUEST = make_limiter("recovery_request", 10, 600, BACKEND, _S)    # per client address, on top of the per-email cooldown and hourly cap
RECOVERY_VERIFY = make_limiter("recovery_verify", 20, 600, BACKEND, _S)
RECOVERY_RESET = make_limiter("recovery_reset", 10, 600, BACKEND, _S)
REGISTER = make_limiter("register", 10, 600, BACKEND, _S)            # new accounts per client address
VERIFY_REQUEST = make_limiter("verify_request", 10, 600, BACKEND, _S)       # resend a verification code, on top of the per-email cooldown
VERIFY_CONFIRM = make_limiter("verify_confirm", 20, 600, BACKEND, _S)


def client_ip(request: Request) -> str:
    """Render and Vercel sit behind a proxy: the first X-Forwarded-For hop is the caller."""
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "unknown")[:64]


def throttle(limiter, request: Request) -> None:
    ok, wait = limiter.allow(client_ip(request))
    if not ok:
        raise HTTPException(status_code=429, detail=f"Too many attempts. Please wait {wait} seconds and try again.", headers={"Retry-After": str(wait)})
