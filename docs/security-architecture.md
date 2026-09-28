# ASAVEXA — Security Architecture

Companion to `docs/runtime-verification.md` and
`docs/postgresql-runtime-verification.md`. Covers authentication,
session security, authorization, tenant isolation, and the three real
vulnerabilities found and fixed during the Phase 4 security audit.

Same honesty rule as its companions: `fastapi`/`sqlalchemy`/`pydantic`/
`psycopg` remain unavailable in this sandbox — nothing here claims real
HTTP-level security testing occurred. What's below either executed for
real against the framework-independent domain/service layer, or was
verified by direct source inspection.

---

## Authentication architecture

`credentials → session → authenticated actor`

`POST /auth/register` (email, password) → `IdentityService.register_user`
hashes the password (`hashlib.pbkdf2_hmac`, never stored raw) and creates
a `User`. `POST /auth/login` → `IdentityService.authenticate` verifies
credentials and, on success, issues a session: a cryptographically
random 256-bit token (`secrets.token_urlsafe(32)`) returned to the
client exactly once; only its SHA-256 hash is persisted. Every
subsequent request sends `Authorization: Bearer <token>`;
`api/deps.py::get_current_session` re-hashes the presented token and
looks up the matching `Session` row — an unknown, expired, or revoked
token is rejected (401) before any handler code runs.

**Password hashing — PBKDF2-HMAC-SHA256, 600,000 iterations, 16-byte
random salt per password.** Verified directly against the OWASP
Password Storage Cheat Sheet during this audit: 600,000 is the actual
current OWASP recommendation for PBKDF2-HMAC-SHA256. **Fixed during this
audit**: the codebase previously used 260,000 iterations with a comment
incorrectly claiming this was "OWASP-recommended... as of early 2023
guidance" — it never was; the true 2023 figure was already 600,000. The
fix is fully backward-compatible: each stored hash embeds its own
iteration count (`pbkdf2_sha256$<iterations>$<salt>$<hash>`), so
existing hashes remain verifiable unchanged; only newly hashed
passwords use the higher count.

**Minimum password length — 15 characters, no complexity rules.**
Per NIST SP 800-63B Revision 4 (finalized 2025, current guidance): a
password used as the *sole* authenticator (this application's exact
situation — no MFA is enforced in the login flow, despite
`User.mfa_enabled` existing as an unused field) must be at least 15
characters; the 8-character floor some older guidance cites applies
only when a password is one factor alongside MFA. No mandatory
character-class rules are imposed, matching current guidance that such
rules push users toward worse, predictable passwords. **Fixed during
this audit**: previously the only check anywhere was non-empty — a
one-character password was accepted, hashed, and stored. Verified
against every password literal already used across the 245-test suite
before making this change (all were already ≥15 characters, so the fix
broke zero existing tests).

## Organization architecture

`actor → membership → organization`

A `User` has zero or more `Membership` rows, each binding them to one
`Organisation` with one `Role`. A `Session` carries an optional
`org_id` — `null` immediately after login, set by
`POST /auth/select-organisation`, which requires an active membership
in the target org (`IdentityService.select_organisation` calls
`_get_active_membership`; no membership → `PermissionDeniedError`, not
a silent grant). Every org-scoped endpoint's `get_current_org`
dependency reads `session.org_id`, never a client-supplied value, and
rejects with 400 if no organisation has been selected yet.

## Authorization architecture

`role → permission → protected operation`

Thirteen roles (OWNER, ADMINISTRATOR, ACCOUNTANT, FINANCE_OFFICER,
APPROVER, REVIEWER, MANAGER, AUDITOR, EXTERNAL_AUDITOR, READ_ONLY,
INVESTOR_REVIEWER, DONOR, REGULATOR), each mapped in
`identity/domain/permissions.py::ROLE_PERMISSIONS` to a `frozenset` of
canonical permission strings (`domain:action`, e.g. `journal:post`,
`finding:verify`). `api/deps.py::require_permission(permission)` is a
FastAPI dependency factory used identically across all seven modules'
routers — the *only* place in the entire codebase permission checks
happen, with one documented, justified exception (see "Role
assignment" below).

**Authorization is enforced exclusively at the API boundary, never
inside a service/domain method** — verified by direct repository-wide
search: zero business-logic service methods (across accounting,
evidence, reconciliation, reporting, period_close, compliance) call
`require_permission` or any permission-checking function. Every service
method takes a plain `actor: str` and trusts the caller. This is a
deliberate, consistent architectural choice, not an oversight — see
`docs/runtime-verification.md`'s framework-boundary table for the same
finding stated in Phase 2 terms.

## Tenant security

Every repository read across all seven modules filters by `org_id` in
its own query — proven exhaustively during the Phase 2/3 audits (every
`WHERE org_id=?` / `.where(...org_id == org_id)` checked directly
against source). A record belonging to another organisation is never
fetched, not filtered out after the fact; `get(org_id, id)` returns
`None` for a cross-tenant id, which every calling service maps to the
same `*NotFoundError` it would raise for a genuinely nonexistent id —
**an authenticated user cannot distinguish "this belongs to another
org" from "this doesn't exist"**, which is the correct behavior for
avoiding cross-tenant information disclosure (Section 10's requirement).
Object-level authorization (not just route-level) is proven with a real
second organisation across every module: accounting (journals via
`test_journals_get_returns_none_across_tenants`), identity, evidence,
reconciliation, reporting, period_close, and compliance all have
dedicated cross-tenant tests using real `org_id` values, not mocked.

`api/db/base.py`'s repository `update()` methods do not independently
re-filter by `org_id` (documented in `docs/postgresql-runtime-verification.md`)
— safe because the service layer only ever calls `update()` with an
object already obtained via an `org_id`-scoped `get()` in the same
operation.

## Session security

- **Creation**: `secrets.token_urlsafe(32)` (CSPRNG, 256 bits of
  entropy) — not `random`, not predictable.
- **Storage**: only `hashlib.sha256(token).hexdigest()` is persisted; a
  database read alone cannot yield a usable bearer token.
- **Validation**: `validate_session` checks, in order, that the token
  hash matches a real session, that it hasn't been revoked
  (`revoked_at is None`), and that it hasn't expired
  (`_now() > expires_at`, timezone-aware comparison) — each a distinct,
  real check with its own exception type
  (`SessionNotFoundError`/`SessionRevokedError`/`SessionExpiredError`),
  each mapped to `401` in `api/deps.py::get_current_session`.
- **Expiration**: enforced on every validation call, not just at issue
  time.
- **Revocation**: `logout()` sets `revoked_at`; a revoked session's
  token can never authenticate again, even before its natural
  expiration.
- **No refresh-token architecture** — not built, since nothing in the
  existing product requirements calls for one; sessions simply expire
  and require a new login, per this phase's own instruction not to
  invent one.

## Privilege escalation — tested, one real path found and fixed

**Found and fixed**: `IdentityService.change_role()` checked only that
the *actor* held `org:manage_users` — never whether the actor was
targeting *their own* membership. `org:manage_users` is held by both
`OWNER` and `ADMINISTRATOR` (confirmed against the real permission
registry, not assumed) — meaning an `ADMINISTRATOR` (a deliberately
narrower role) could call `change_role(org_id, <themselves>, OWNER,
actor_user_id=<themselves>)` and grant themselves `OWNER`, which holds
`ALL_PERMISSIONS`. This is a genuine, concrete, previously-exploitable
escalation path, not a theoretical one.

**Fix**: `change_role()` now raises `SelfRoleChangeError` (400/409) the
moment `target_user_id == actor_user_id`, before any other check —
a different, already-authorized actor must change your role. The
guard applies uniformly regardless of role (even `OWNER` cannot call
`change_role` on itself, keeping the invariant simple rather than
special-casing "already most-privileged").

**Every other escalation path in Section 8's checklist was tested and
confirmed already blocked**, not newly fixed:
- Self-grant of `OWNER`/`ADMINISTRATOR` at membership creation: only
  possible via the documented, necessary bootstrap case (`add_membership`
  performs no permission check *only* when the target organisation has
  zero existing memberships — i.e., only the very first membership ever
  granted, immediately after `create_organisation`, when no one else
  could have granted it). Every subsequent `add_membership` call requires
  `org:manage_users`.
- Unauthorized role assignment to another user: blocked by
  `require_permission(actor_user_id, org_id, "org:manage_users")`
  (`test_non_member_cannot_add_members`, `test_read_only_role_cannot_manage_users`).
- Cross-organisation resource access: blocked at the repository layer
  (see "Tenant security" above).
- Session manipulation: a session is looked up strictly by its own
  token hash; there is no operation that accepts an arbitrary session
  id from a client to act on someone else's session.
- Bypassing a required permission via a lower-level repository call
  through the API: not possible — routers hold no direct repository
  references, only service/engine instances injected via
  `Depends(get_X_service)`; verified by the Phase 2 audit's
  router-to-service call-site checker (170+ real call sites, zero bare
  repository access from any router).

## Security findings

| Finding | Classification |
|---|---|
| PBKDF2 iteration count (260,000) below current OWASP recommendation, with an inaccurate comment | **FIXED** — raised to 600,000, comment corrected |
| Login timing side-channel (email enumeration via response time) | **FIXED** — `authenticate()` now always pays the PBKDF2 cost, verifying against a dummy hash when no account matches |
| `change_role()` privilege escalation (`ADMINISTRATOR` → `OWNER` self-promotion) | **FIXED** — `SelfRoleChangeError` guard added |
| No minimum password length anywhere (a 1-character password was accepted) | **FIXED** — `WeakPasswordError` now enforces NIST SP 800-63B Rev. 4's 15-character minimum for single-factor passwords (no MFA is enforced in the login flow, so this application is single-factor) |
| Bootstrap-case permission bypass in `add_membership` | **VERIFIED, intentional** — only reachable for the first membership in a brand-new org; every subsequent call requires `org:manage_users` |
| Tenant isolation (repository + object-level) | **VERIFIED** — exhaustive, real cross-tenant tests across all seven modules |
| Authorization enforced only at API boundary | **VERIFIED, intentional architecture** — zero exceptions in service/domain code |
| No hardcoded credentials/secrets anywhere in `src/` | **VERIFIED** — repository-wide static sweep |
| No password/token ever logged, printed, or embedded in an audit event's `new_value` | **VERIFIED** — repository-wide static sweep |
| `UserOut` and every other `*Out` response schema never declares a password/token field | **VERIFIED** |
| No `X-Actor`/`X-Org-Id` (legacy header-trust) reference anywhere in `src/` | **VERIFIED** |
| Email format validated at the schema boundary (`EmailStr`) | **STATIC** — real Pydantic validation, unexecuted here |
| Rate limiting / brute-force protection on login | **ACCEPTED LIMITATION** — not implemented; see below |
| PostgreSQL-level `REVOKE` grants on `audit_events` (defense-in-depth beyond the Python API surface) | **ACCEPTED LIMITATION** — needs a role/grant model decision, not invented here (see `docs/postgresql-runtime-verification.md`) |
| Real HTTP-level authentication behavior (header parsing, actual 401/403 responses over the wire) | **REQUIRES FUTURE RUNTIME VERIFICATION** — fastapi/starlette unavailable here |

## Rate limiting / abuse controls

**Not implemented in this phase** — evaluated, not built speculatively,
per this phase's own instruction not to "blindly implement a complex
rate-limiting system." **Risk**: without it, an attacker with network
access to `/auth/login` can attempt unlimited password guesses per
account (the PBKDF2 cost slows each attempt to roughly 100-300ms, which
is a meaningful but not sufficient deterrent against a sustained
attack). **Intended production mechanism**: a per-IP and per-account
rate limit on `/auth/login` (e.g. a sliding-window counter, most simply
implemented at a reverse-proxy/API-gateway layer rather than in
application code, since that's where this class of control typically
belongs and where it can be applied uniformly across every route, not
just login). **Verification status**: not verifiable in this
environment regardless of implementation choice, since it requires a
real HTTP server receiving real repeated requests.

## Secret management

The application needs exactly one secret-adjacent configuration value:
`DATABASE_URL` (contains the database password). Confirmed via direct
inspection: no other secret exists — session tokens are opaque, random,
database-backed values (not JWT-signed), so there is no application
`SECRET_KEY` to manage. `.env.example` contains a placeholder only
(`postgresql+psycopg://asavexa:asavexa@localhost:5432/asavexa`, a
non-production local-dev value); the real `.env` is git-ignored by
convention (standard for this file pattern) and was never committed.

## Verified / Static / Runtime pending

**Verified (executed against real, framework-independent code)**: 245
tests, including 14 new ones added during this phase — password
hashing round-trip and minimum-length enforcement, session lifecycle
(create/validate/expire/revoke), the timing side-channel fix (via
call-count, not flaky wall-clock assertions), the privilege-escalation
fix (three dedicated tests), and every static sweep above (converted
from ad-hoc greps into permanent `ast`-based regression tests in
`tests/test_security_hardening.py`).

**Static (inspected, not executed)**: every router's
`Depends(require_permission(...))` wiring (already covered by Phase 2's
router-contract tests); `api/deps.py`'s exact exception-to-401/403
mapping logic.

**Runtime pending**: actual HTTP header parsing and rejection of a
malformed/missing `Authorization` header by Starlette itself; actual
`401`/`403` HTTP status codes observed over a real connection; real
concurrent-session behavior under load.

---

## Exact commands for real runtime security verification

Same environment and commands as `docs/runtime-verification.md`. Once
the API is running for real:

```bash
# Missing auth
curl -i http://localhost:8000/accounts
# expect: 401 (or 403, per FastAPI's HTTPBearer default when the
# header is absent — confirm the exact code once this runs for real)

# Malformed auth
curl -i -H "Authorization: NotBearer sometoken" http://localhost:8000/accounts
# expect: 401 or 403

# Invalid token
curl -i -H "Authorization: Bearer not-a-real-token" http://localhost:8000/accounts
# expect: 401

# Valid login, then a cross-tenant object-ID substitution attempt —
# the single most important real-world check this document cannot
# perform for you:
#   1. Register/login as a user in Org A; select Org A.
#   2. Note a real journal/evidence/finding id belonging to Org A.
#   3. Register/login as a different user in Org B; select Org B.
#   4. GET that same id under the Org B session.
#   5. Expect: 404 (not 403 — this codebase's design deliberately
#      makes "belongs to another org" indistinguishable from "doesn't
#      exist", per Section 10).
```
