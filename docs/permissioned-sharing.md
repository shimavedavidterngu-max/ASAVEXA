# Permissioned Sharing of the VERA Financial Passport

The organisation decides who sees what, for which dates, for how long, and can take it back at any time.

## Flow
Passport → **Share…** → Recipient → Information → Date range → Permissions → Review → **Generate secure access** → Recipient verifies.

1. **Recipient**: name, type (bank, auditor, investor, regulator, donor, other), optional email, purpose. Choosing a type pre-fills sensible defaults (e.g. a bank: identity, financial history, evidence quality, last 3 years, closed periods only).
2. **Information**: any of the six Passport sections, and whether line-level detail (transactions, names, team emails) is included. Off by default.
3. **Date range**: last 1/3/5 years or custom. Only accounting periods lying entirely inside the range are shared; optionally only closed periods.
4. **Permissions**: allow download (off by default) and how long access lasts (1–365 days).
5. **Generate**: a secret link and a separate access code are shown **once**. Send them by different routes.
6. **Recipient** opens the link (no ASAVEXA account), enters the code (and email, if one was set) and gets a read-only view with a banner showing exactly what was shared, plus an integrity check.

## Guarantees (enforced on the server)
- Frozen snapshot at creation. Later ledger changes never alter what the recipient sees; the fingerprint proves it.
- Link secret and code are stored only as hashes (code: salted PBKDF2). Neither can be recovered.
- 5 wrong code/email attempts lock the share. A wrong link secret is not counted, so strangers cannot lock a share.
- Verified sessions last 60 minutes at most, and never past expiry. Revoking or expiry cuts off an open session immediately.
- Creating and revoking need Owner/Administrator; listing needs Passport access. Every share, view, download, refusal, lock and revoke is audited and visible per share ("Activity").
- Recipient endpoints never return 401, so they cannot log out an organisation user.

## Honest limits
- Anything shown on screen can be copied or screenshotted. "Allow download" only controls the logged download endpoint.
- The integrity check is the server recomputing the fingerprint of its own stored snapshot. It detects accidental or database-level alteration; it is not an independent third-party attestation.
- If the access code is lost, revoke the share and create a new one.

## Endpoints
Organisation: `POST/GET /passport/shares`, `GET /passport/shares/{id}`, `GET /passport/shares/{id}/access-log`, `POST /passport/shares/{id}/revoke`.
Public: `POST /shared-passport/verify`, `GET /shared-passport/view`, `GET /shared-passport/download` (Bearer session token).
Tables `passport_shares`, `passport_share_sessions` are created at startup (checkfirst), not by migration.
