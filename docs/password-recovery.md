# Passwords and password recovery

See also `docs/email-setup.md` for the shared email provider, templates, sign-up verification and step-by-step setup.

Status: **IMPLEMENTED, TESTED WITH TEST DATA.** Not yet verified on the live site. Real emails will only be sent once an email provider is configured (below).

## Password policy (sign-up, reset, everywhere a password is created)
- 8 to 128 characters, at least one letter and one number, and not one of a short list of very common passwords.
- Spaces and symbols are allowed and kept exactly as typed. A password is never trimmed or changed.
- One definition: `src/asavexa/identity/domain/password_policy.py`. The screens mirror it in `frontend/src/lib/passwords.js`; a test checks the two agree.
- **Change from before:** the earlier build required 15 characters. You asked for 8 + letter + number, so that is what is enforced. Existing accounts are unaffected (they can still sign in); the rule applies when a password is created or changed. The common-password check and the sign-in lockout (10 failures, 15 minutes) are what make the shorter length reasonable.

## Screens
Sign in: email, password with an eye button, **Forgot password?** beside the password label, Sign in, link to sign up.
Sign up: email, password, confirm password (each with an eye), live rules list, field-level errors, no field is cleared by an error.
Recovery: Reset your password → Enter your verification code (paste works, Clear button, Resend with a countdown) → Choose a new password → success with **Return to login**. The person is not signed in automatically.

## API (all under `/auth`)
| Method and path | Purpose |
|---|---|
| GET `/password-policy` | the rules the server enforces |
| POST `/register` | now also accepts `confirm_password` (must match when sent) and enforces the policy |
| GET `/recovery/status` | `{available}`: lets the screen say honestly when email is not set up |
| POST `/recovery/request` | ask for a code (also used to resend). Same answer for real and unknown emails |
| POST `/recovery/verify` | check the code, returns a single-use `reset_token` (10 minutes) |
| POST `/recovery/reset` | `email`, `reset_token`, `new_password`, `confirm_password` |

## How it stays safe
- Same response whether or not the email has an account; counters (cooldown 60 s, 5 codes per hour, 5 wrong guesses) are keyed by the email, not the account, so they look identical for made-up addresses. Per-address throttles apply too.
- The 6-digit code comes from `secrets`, is stored only as a salted hash, expires in 10 minutes, works once, and a new code replaces the old one. It is never returned, logged, put in a URL or kept in browser storage.
- The reset token is bound to one account, stored as a hash, single use, 10 minutes. Changing the email in the request cannot reuse it for someone else.
- The email is sent in a background thread so a real account and an unknown one take the same time. A delivery failure is logged (no code, no address) and never reported as sent.
- After a reset: password hash replaced (same PBKDF2 function as sign-up), all other codes and tokens removed, every session ended (also sessions with no security record, via a "password changed at" marker), an audit event written, a notice emailed.
- Audit events: `PASSWORD_RECOVERY_REQUESTED`, `..._CODE_VERIFIED`, `..._CODE_REJECTED`, `PASSWORD_RESET_COMPLETED`, `PASSWORD_RESET_REFUSED`, `PASSWORD_CHANGED`. No secrets are recorded.

## Database changes
None. Recovery state uses the existing `security_docs` table (kinds `pwreset_code`, `pwreset_auth`, `pwreset_req`, `pwreset_try`, `pwd_epoch`).

## Email provider (you must do this for real codes to arrive)
No email service existed before. Set these on the Render backend (Environment tab), then redeploy:

Recommended (Render's free plan blocks SMTP, so use an HTTPS provider):
- `ASAVEXA_EMAIL_PROVIDER` = `resend`
- `RESEND_API_KEY` = your key from resend.com
- `ASAVEXA_EMAIL_FROM` = `ASAVEXA <no-reply@your-verified-domain>` (the domain must be verified in Resend; check Resend's documentation for what its test sender allows)

Or SMTP: `ASAVEXA_EMAIL_PROVIDER=smtp`, `ASAVEXA_SMTP_HOST`, `ASAVEXA_SMTP_PORT` (587 or 465), `ASAVEXA_SMTP_USER`, `ASAVEXA_SMTP_PASSWORD`, `ASAVEXA_EMAIL_FROM`.

With nothing set, the recovery screen says email is not set up and the API answers 503. Nothing is faked. Credentials are read only from environment variables. The test mailer exists only in tests and can never be chosen from the environment.

## Known limits
- Rate limits and cooldown counters for the per-address throttle are in memory (one server instance today); the per-email cooldown, hourly cap and wrong-guess lock are stored in the database and survive restarts.
- The 6-digit code is brute-forceable offline if someone could read the database; the guess limit and 10-minute life protect it online.
- Email verification at sign-up is not part of this change.

## Rollback
Revert the commit. No data migration is needed; the `pwreset_*` rows can stay or be deleted from `security_docs`. Passwords already changed stay changed (they are ordinary hashes).

## Tests
`tests/test_password_recovery.py` (46), `frontend/tests/auth-screens.test.js` and updated `login.test.js`, plus a real-browser run (73 checks): sign-up errors, eye toggles with mouse and keyboard, the full recovery journey, unavailable email, provider failure, phone, dark mode.
