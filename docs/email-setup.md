# Account email: welcome message, email verification, password recovery

Status: **IMPLEMENTED, VERIFIED IN TEST ENVIRONMENT.** Every message in the tests goes to an in-memory outbox. **No real email has been delivered or received yet.** That needs the setup below, and it is not verified until you receive a message in a real mailbox.

## What happens, in order
1. **Sign-up** (button: *Create Account* → *Creating your account...*). The account is saved first. Then ASAVEXA sends two emails to the address typed: a welcome email and a separate email with a 6-digit verification code.
2. **The page tells the truth.** The success message ("Your account has been created successfully. A confirmation email has been sent…") appears only when the email provider **accepted** both messages. If the provider is down, rejects the request, or is not configured, the page says: "Your account was created, but we could not send the confirmation email. Please try resending it." The account is never deleted because of an email problem.
3. **Verify screen.** Enter the 6-digit code. *Resend verification code* waits 60 seconds. *Verify later and continue to ASAVEXA* signs the person in without verifying. The address is marked verified **only** by a correct code, checked on the server.
4. **Forgot password?** works as before and now uses the same templates and provider. After a reset the person gets a "password changed" email.

## Provider
Resend (HTTPS API) is built in and recommended: Render's free plan blocks SMTP. SMTP is also supported. The provider is chosen only by environment variables. The API key never appears in the frontend, in git, or in any API answer.

## Environment variables (set these on the Render **backend** service, Environment tab)
| Name | Required | Meaning |
|---|---|---|
| `EMAIL_PROVIDER` | yes | `resend` (or `smtp`) |
| `EMAIL_API_KEY` | yes (Resend) | the provider's private API key |
| `EMAIL_FROM_ADDRESS` | yes | sender on a **verified domain**, for example `no-reply@your-domain.com` |
| `EMAIL_FROM_NAME` | no | defaults to `ASAVEXA` |
| `APP_BASE_URL` | recommended | the link in the welcome email, for example `https://asavexa-frontend.vercel.app` |
| `SUPPORT_EMAIL` | no | shown as the place to get help |
| `EMAIL_VERIFICATION_CODE_TTL_MINUTES` | no | default 10 (allowed 1–60) |
| `PASSWORD_RESET_CODE_TTL_MINUTES` | no | default 10 (allowed 1–60) |
| `RESEND_WEBHOOK_SECRET` | optional | `whsec_…` from Resend, turns on delivery / bounce / complaint tracking |

The older names (`ASAVEXA_EMAIL_PROVIDER`, `RESEND_API_KEY`, `ASAVEXA_EMAIL_FROM`) still work. If anything required is missing, ASAVEXA logs a configuration error (no secrets) and the screens say email is not set up. Nothing is pretended.

## Step by step
1. **Create the account** at resend.com.
2. **Verify your sending domain** (Resend → Domains → Add domain). Resend shows DNS records to add where you manage your domain: SPF and DKIM are in that list. Wait until Resend shows *Verified*. (Without a verified domain, Resend only allows its own test sender and sending to your own account email; check Resend's current documentation. That is enough for a first test of your own address.)
3. **DMARC** (recommended): add a TXT record named `_dmarc` with the value `v=DMARC1; p=none; rua=mailto:you@your-domain.com`. Start with `p=none`, check the reports, then tighten.
4. **Create an API key** (Resend → API Keys, "sending access"). Copy it once. Do not paste it in chat, in git, or in the frontend.
5. **Render** → your backend service → **Environment** → add the variables above → Save. Render redeploys by itself.
6. **Check:** open `https://asavexa.onrender.com/auth/verification/status`. It should show `{"available":true}`.
7. **Optional webhook:** Resend → Webhooks → Add endpoint `https://asavexa.onrender.com/webhooks/email`, events *email.delivered*, *email.bounced*, *email.complained*, *email.delivery_delayed*. Copy the signing secret into `RESEND_WEBHOOK_SECRET` on Render.

## Test with a real mailbox (this is what makes it VERIFIED IN PRODUCTION)
1. Sign up with an address you can read. You should see the success message and receive **two** emails: the welcome message and "Verify your email address for ASAVEXA".
2. Enter the code. You should see "Email verified".
3. Try a wrong code (refused), then *Resend* (a new code arrives, the old one stops working).
4. Sign out, use **Forgot password?**, enter the code from the email, set a new password. You should receive "Your ASAVEXA password was changed" and the old password should stop working.
5. Check spam if nothing arrives, and look at Resend → Logs: it shows whether the message was delivered or bounced. Accepted is not delivered.

## Safety rules that are enforced and tested
- Codes: 6 digits from `secrets`, stored only as a salted hash, expire (default 10 minutes), single use, a new code replaces the old one. Never returned by the API, logged, or kept in browser storage.
- Limits: 60 seconds between codes, 5 codes per hour per address, 5 wrong guesses lock until a new code, plus per-IP limits on sign-up (10 per 10 minutes), resend and confirm.
- Resend and confirm give the **same answers** for a real, unknown and already-verified address.
- One account per address, whatever the capitalisation. A repeated or double-clicked sign-up fails before any email is sent. The welcome email is sent once per account.
- Provider errors are logged for the operator without the address, code or message body.
- Delivery webhooks are accepted only with a valid signature (Svix), a fresh timestamp and an unseen message id. Without `RESEND_WEBHOOK_SECRET` the endpoint refuses everything. Recipients are stored by hash.

## Templates (`src/asavexa/security/emailtemplates.py`)
Account created · Verify your email address · Password recovery code · Password changed · Security alert (available for important changes). Each has a subject, a responsive HTML version (600 px, system fonts, real heading) and a plain-text version. Code emails state the expiry and say to ignore the message if you did not ask. No email contains a password, session token or database identifier.

## Not built, on purpose or not yet
- **Verification does not block sign-in or any feature.** Existing accounts were never verified and would be locked out. `GET /auth/email-status` (signed in) tells you whether an address is verified, so a later decision can gate features on it.
- Per-IP limits are in memory (one server instance today).
- No automatic suppression of addresses that bounce: bounces are recorded and logged; acting on them is a later step.
- A 6-digit code can be guessed offline if someone could read the database; the hash is salted but the space is only one million values. The live limits above are what stop online guessing.
- Security-alert emails exist as a template but nothing sends them yet.
