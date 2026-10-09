# Security & infrastructure: setup guide and runbooks

For the person who runs ASAVEXA. Plain steps; no programming needed. Everything protective is **off until you add keys**, and the app
says so on the Security page. There are no default keys or passwords.

## 1. Switch it on (15 minutes)

**Step 1: make your keys.** On your computer, in Command Prompt:

```
cd /d "C:\Users\Surface\Downloads\New folder\asavexa"
set PYTHONPATH=src
python -m asavexa.security.keygen
```

It prints two lines, `ASAVEXA_KEYS=...` and `ASAVEXA_CURRENT_KEY=...`. (If Python is not installed on your PC, ask for the keys to be generated for you: they are just a random 32-byte value; never reuse one from an example.)

**Step 2: keep a copy.** Paste both lines into your password manager *now*. If these keys are lost, encrypted evidence files and backups **cannot be recovered by anyone**.

**Step 3: add them to Render.** Render → your ASAVEXA service → *Environment* → add `ASAVEXA_KEYS` and `ASAVEXA_CURRENT_KEY` (value only, no quotes) → Save. Render redeploys.

**Step 4: check.** Sign in → *Security* → *Overview*: "Encryption keys: On". Then *Connection & Self-Test* → run it; the Security group should pass or explain what is off.

**Step 5: protect your own sign-in.** *Security* → *My account* → *Set up two-step sign-in*. Install an authenticator app (Google Authenticator, Microsoft Authenticator, 1Password), choose "enter a setup key", type the key shown, then the 6-digit code. **Save the recovery codes.** Do this for every owner and administrator. Only then, *Overview* → tick *Require two-step sign-in*.

## 2. Environment variables

| Variable | Needed? | What it does |
|---|---|---|
| `ASAVEXA_KEYS`, `ASAVEXA_CURRENT_KEY` | Recommended first | Switches on encryption of evidence files, MFA, the tamper-evident audit chain, encrypted backups, single sign-on |
| `ASAVEXA_DATA_REGION` | If you use region rules | Where the database/files really are, e.g. `EU`, `NG`, `US`. Codes: NG GH KE ZA EU UK US CA AE SG IN AU |
| `ASAVEXA_STORAGE` | Optional | `database` (default, fine for pilots), `s3`, `local`, or `none` (keep only record + fingerprint) |
| `ASAVEXA_S3_ENDPOINT`, `ASAVEXA_S3_BUCKET`, `ASAVEXA_S3_REGION`, `ASAVEXA_S3_ACCESS_KEY`, `ASAVEXA_S3_SECRET_KEY`, `ASAVEXA_S3_PATH_STYLE` | If `s3` | Any S3-compatible bucket (AWS S3, Cloudflare R2, Backblaze B2, MinIO). Use a key that can only touch this bucket |
| `ASAVEXA_OIDC_ISSUER`, `ASAVEXA_OIDC_CLIENT_ID`, `ASAVEXA_OIDC_CLIENT_SECRET`, `ASAVEXA_OIDC_REDIRECT_URI`, `ASAVEXA_OIDC_ALLOWED_DOMAINS` | Optional | Single sign-on. Redirect URI = your web app's address (e.g. `https://your-app.vercel.app/`). People must already have an ASAVEXA account; SSO never creates one |
| `ASAVEXA_IDLE_MINUTES` (30), `ASAVEXA_MAX_SESSIONS` (5) | Optional | Idle sign-out and devices per person |
| `ASAVEXA_MAX_UPLOAD_MB` (25) | Optional | Largest evidence file |
| `ASAVEXA_ALERT_WEBHOOK` | Optional | An `https://` Slack-style incoming-webhook URL; new alerts are posted there (best effort) |

## 3. What each protection does and its honest limit

| Protection | Does | Limit |
|---|---|---|
| Two-step sign-in | Code from an authenticator app after the password | Can be phished in real time; no passkeys yet |
| Single sign-on (OIDC) | Sign in through your company identity provider | Tested against a local fake provider only: **verify with your real provider** before relying on it |
| Sessions | Idle sign-out, device list, sign out everywhere, 5-device cap | Idle timer is checked on each request |
| Encrypted evidence | Files stored AES-256-GCM, each with its own key, wrapped by your master key | Master key is an environment variable; use a KMS for higher assurance |
| Key rotation | Add a new key, make it current, press *Re-wrap file keys* | Old keys must stay loaded until re-wrap finishes |
| Tamper-evident audit | Signed hash chain; *Audit trail integrity* → *Check now* | Events before keys existed are not covered |
| Retention | Evidence kept ≥ 6 years (default 7); legal holds; disposal deletes the file and keeps the record and fingerprint | Periods are yours to confirm with counsel |
| Privacy | Download my data; erasure request approved by an owner | Accounting and audit records are kept under an anonymous ID |
| Data residency | Refuses to store files outside allowed regions; reports where things live | Regions are declared by you, not detected |
| Vendor register | Computed risk, review dates | Facts are entered by you |
| Alerts | Rule-based, from the audit trail | Not a monitoring service |

## 4. Runbook: rotating the encryption key

1. Generate a new key: `python -m asavexa.security.keygen`.
2. On Render **append** it to `ASAVEXA_KEYS` (comma-separated: `new:...,old:...`) and set `ASAVEXA_CURRENT_KEY` to the new id. Save the new full value in the password manager.
3. After redeploy: *Security → Overview → Re-wrap file keys under the current key*. "Files per key" should show everything under the new key.
4. Only when no files remain under the old key, and no backup you still need was made with it, remove the old key. **Backups made with an old key need that key to be restored.**

## 5. Runbook: backups and disaster recovery

**What is backed up:** the whole PostgreSQL database (accounting, evidence records, audit events, and the security tables including encrypted files when `ASAVEXA_STORAGE=database`). If you use S3/R2, the files live in the bucket and need the provider's versioning/replication switched on separately.

**Make a backup** (needs: Python with `pip install cryptography`, and the PostgreSQL client tools whose major version matches your database, so `pg_dump` and `pg_restore` run in Command Prompt; use the database's *External* connection string from Render):

```
cd /d "C:\Users\Surface\Downloads\New folder\asavexa"
set DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DBNAME
set ASAVEXA_KEYS=...paste...
set ASAVEXA_CURRENT_KEY=...paste...
set PYTHONPATH=src
python scripts\backup.py --verify
```

The file is encrypted and saved in `backups\`, with a checksum file next to it. With `ASAVEXA_STORAGE=s3` it is also copied to the bucket, and *Security → Overview → Backups* then shows its age. **Schedule this daily** (a Render Cron Job, or your own scheduler). Render's own database backups are an extra layer, not a replacement.

**Targets (set by you, proven by drills):** RPO = time since the last good backup (daily schedule → up to 24 hours of data). RTO = how long a restore takes: run a drill and write the number down; it is not guessed here.

**Restore drill (do this before the pilot, then quarterly):**

1. Create a new, empty database (Render → New → PostgreSQL, or a local one).
2. `python scripts\restore.py backups\asavexa-....dump.enc --verify-only` (proves it decrypts and lists).
3. `python scripts\restore.py backups\asavexa-....dump.enc --target postgresql://USER:PASS@HOST:5432/NEWDB`.
4. Point a test copy of the API at it, sign in, open *Security → Audit trail integrity → Check now* and *Connection & Self-Test*.
5. Record the time taken and any problems.

**A real disaster:** restore into a **new** database, switch `DATABASE_URL` on Render to it, redeploy, run the checks above, then tell users. The restore script refuses to overwrite the live database unless you add `--overwrite-live` on purpose.

**If keys are lost:** encrypted backups and files are unrecoverable. This is why Step 2 matters.

## 6. Runbook: monitoring and alerts

- `GET /health`: process alive. `GET /ready`: database reachable (no details leaked). `GET /metrics-lite`: request and error counters since start. Point an uptime monitor (UptimeRobot, Better Stack) at `/ready` and alert on failure.
- *Security → Overview → Run checks now*: database, keys and file-storage write/read-back.
- *Security → Alerts → Scan now*: repeated failed sign-ins, success after failures, MFA turned off or locked, new owner/administrator, rule changes, key rotation, legal hold released, evidence disposed, download bursts, failed audit-chain check. Review weekly; add a note when you clear one.
- Every response carries `X-Request-ID`; quote it when investigating.

## 7. Runbook: something looks wrong

1. *Security → Alerts*: what and when. 2. *Audit trail integrity → Check now*: if it reports problems, treat it as a possible tampering incident: stop changes, take a backup, preserve logs. 3. Suspected stolen account: *My account → Sign out all other devices* (the person), reset the password, re-enrol MFA. 4. Suspected key exposure: rotate keys (Section 4), then also rotate the S3 and database credentials. 5. Write down what happened and when.

## 8. Not built (so you are not surprised)
Passkeys/WebAuthn, QR codes for MFA, cloud KMS, automated penetration testing, automated dependency scanning, distributed rate limiting, automatic backup scheduling inside the app, multi-region failover.
