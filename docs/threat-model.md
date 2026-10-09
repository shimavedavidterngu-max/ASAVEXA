# ASAVEXA threat model

What we are protecting, from whom, how, and what is **not** covered. Written for the first external pilots. It is a working
document: when something in the system changes, change this file in the same commit.

Honesty rule: a control is listed as **built and tested**, **built, needs the operator to switch it on**, or **not built**. Nothing
here claims a live result: the code was tested in a build environment, not against your live Render, Vercel or database.

## 1. Assets (what an attacker wants)

| Asset | Why it matters | Where it lives |
|---|---|---|
| Ledger, journals, reconciliations | The financial truth the product sells | PostgreSQL |
| Evidence files (invoices, statements) | Proof behind every number; often contain personal data | Database table `security_docs` (encrypted) or S3-compatible bucket (encrypted) |
| Audit trail | The record of who did what; the product's credibility | PostgreSQL `audit_events` + hash chain in `security_docs` |
| Credentials and sessions | Gives access to everything above | `users` (PBKDF2 hashes), `sessions` (SHA-256 of tokens), MFA secrets (encrypted) |
| Encryption keys (`ASAVEXA_KEYS`) | Unlock every encrypted file, MFA secret and backup | Render environment variables only |
| Shared passports | Deliberately leave the organisation | `passport_shares` (token hashes only) |

## 2. Trust boundaries

1. Browser ↔ API (HTTPS, bearer token, no cookies, so no CSRF surface).
2. API ↔ PostgreSQL (private network on Render).
3. API ↔ object storage (HTTPS, signed requests) if enabled.
4. API ↔ identity provider (HTTPS) if single sign-on is enabled.
5. Organisation ↔ organisation (multi-tenancy: every query is scoped by `org_id`).
6. Organisation ↔ external recipient (permissioned sharing).
7. Operator (person with Render/GitHub access) ↔ the platform. **The operator is trusted** (see residual risks).

## 3. Threats and controls (STRIDE)

Status: ✅ built and tested · 🔧 built, operator must switch on · ⛔ not built

### Spoofing: pretending to be someone
| Threat | Control | Status |
|---|---|---|
| Stolen or guessed password | PBKDF2 hashing; 15-character minimum; sign-in lock after 10 failures in 15 minutes (counted by account, or by email for unknown accounts so the lock reveals nothing); constant-time check even for unknown emails; per-address rate limit | ✅ |
| Password alone is enough | Authenticator-app codes (TOTP, RFC 6238, tested against the RFC vectors) + 10 single-use recovery codes; 5 wrong codes lock the factor for 15 minutes; a code cannot be replayed; secrets stored encrypted | 🔧 needs `ASAVEXA_KEYS` |
| Organisation wants everyone on MFA | Organisation rule "require two-step sign-in": people whose session did not use it cannot open the organisation | ✅ (with keys) |
| Corporate identity | OpenID Connect sign-in (authorization-code + PKCE, signed `state`, nonce, browser binding, strict token checks, no automatic account creation) | 🔧 needs `ASAVEXA_OIDC_*`; tested against a local fake provider only, **never a real one** |
| Stolen token | Idle sign-out (30 min default), cap of 5 devices, device list with sign-out, "sign out everywhere", tokens stored only as hashes | ✅ |
| Login-by-phishing / fake site | Not addressed by the application (no WebAuthn/passkeys yet) | ⛔ |

### Tampering: changing data
| Threat | Control | Status |
|---|---|---|
| Altering or deleting audit events | Per-organisation hash chain; every link and the head are signed with a key held outside the database. Verifier reports changed, deleted, inserted, reordered and truncated events. A database-only attacker cannot recompute valid signatures | ✅ (with keys). Events recorded before keys existed are listed as "not covered" |
| Altering an evidence file | SHA-256 fingerprint on the record; AES-256-GCM authenticated encryption; file bound to its organisation and record, so a moved blob fails to decrypt; download re-checks the fingerprint | ✅ (with keys) |
| Editing posted journals | Posted journals are immutable; corrections are reversals (existing accounting engine) | ✅ |
| Tampering with backups | Backups are encrypted and checksummed; restore refuses a modified file | ✅ |

### Repudiation: denying an action
Every security-relevant action is written to the audit trail (sign-ins, failures, MFA changes, settings, holds, disposals, key
rotations, downloads, erasures). Alerts are raised from it. ✅. Audit events are never deleted, even on erasure (the person's
identity is removed; the record remains under an opaque id).

### Information disclosure: seeing what you should not
| Threat | Control | Status |
|---|---|---|
| Database copy or stolen backup read in the clear | Evidence files, MFA secrets and backups are encrypted with keys that are not in the database | 🔧 needs `ASAVEXA_KEYS` |
| One organisation reading another's data | `org_id` scoping on every query; tested; permission checks on every route | ✅ |
| Secrets in logs, errors, responses | Logs record method, path, status and time only; `/ready` no longer prints exception text; the device list and exports never contain token fingerprints, password hashes or key material; `redact()` helper | ✅ |
| Browsers rendering uploaded files | Downloads are always `attachment` + `nosniff`, content type forced to `application/octet-stream` | ✅ |
| Data leaving the agreed region | Residency rules refuse to store files outside allowed regions; report lists where data and vendors are | ✅ for what the operator declares. **We cannot detect where a provider really keeps data** |
| Over-collection / no way to see or remove personal data | Export of everything held about a person; erasure request approved by an owner; data inventory | ✅ |

### Denial of service
Per-address throttling of sign-in, MFA and SSO endpoints (in memory, **per server instance**). Idle sessions are cut. No
protection against volumetric attacks (rely on Render/Vercel's edge). Evidence uploads are capped (25 MB default, `ASAVEXA_MAX_UPLOAD_MB`). ⚠ partial.

### Elevation of privilege
Roles and permissions (`security:manage` for owners and administrators only); last owner cannot be removed or erased; privilege
grants raise an alert; the person who deletes an account cannot be the only owner. ✅.

## 4. Supply chain and vendors
Render, Vercel and GitHub are recorded in the vendor register as **"needs review"**: the platform asserts nothing about their
agreements, certifications or locations until you record the facts. Risk is computed from those facts (data touched, signed
agreement, attestation, region, sub-processors, exit plan) and reviews fall due on a schedule by tier. Dependencies are pinned by
minimum version only; no automated dependency scanning yet ⛔.

## 5. Residual risks (honest list)
1. **A malicious or compromised operator** with access to Render can read the keys and the database. Mitigation is organisational (two-person access, MFA on Render/GitHub, a KMS later), not in this code.
2. **Keys in environment variables.** Losing `ASAVEXA_KEYS` means encrypted evidence and backups are unrecoverable. Store them in a password manager separate from Render. The `KeyProvider` interface allows a cloud KMS later ⛔.
3. **No passkeys/WebAuthn**; TOTP can be phished in real time.
4. **Rate limits are per instance** and in memory.
5. **TOTP is entered by typing the setup key**; there is no QR code.
6. **Alerts are rule-based** (listed in the app) and are not a substitute for monitoring; the optional webhook is best effort.
7. **Backups are only proven by restore drills.** A backup nobody has restored is a hope, not a control.
8. **The database-backed file store** suits pilots; move to S3/R2 as volume grows.
9. **Retention floor (6 years) and region codes are operator-declared**, not legal advice. Check with counsel for each jurisdiction.
10. **Not independently audited or penetration-tested.** This work was tested by its author in a build environment.

## 6. Before a serious pilot, do these
1. Set `ASAVEXA_KEYS` and `ASAVEXA_CURRENT_KEY` on Render; save a copy in a password manager.
2. Turn on two-step sign-in for every owner and administrator; then switch on "require two-step" for the organisation.
3. Run the first backup and a restore drill; note how long it took.
4. Fill in the vendor register for Render, Vercel and GitHub (and any bank/ID/payments providers).
5. Turn on MFA for the Render, GitHub and Vercel accounts themselves.
6. Review open alerts weekly; set `ASAVEXA_ALERT_WEBHOOK` if you want them pushed to Slack.
