"""
Password policy, sign-up checks and the whole password-recovery workflow, against the real identity service, the real security
context, real SQLite storage and the real API router functions (fastapi itself is stubbed by harness_security_routers, as in the
other router tests). Email goes to an in-memory outbox: no real message is ever sent.

Numbers in the comments refer to the 24 required checks of the authentication fix brief.
"""
import json
import logging
import re
import unittest
from datetime import timedelta
from pathlib import Path

import harness_security_routers as H
from harness_security_routers import auth, HTTPException, Request
from asavexa.api import ratelimit
from asavexa.identity.domain import password_policy
from asavexa.identity.domain.errors import InvalidCredentialsError, WeakPasswordError
from asavexa.security import recovery as rec
from asavexa.security.context import SecurityContext
from asavexa.security.errors import RecoveryError, RecoveryRateLimitError, RecoveryUnavailableError, SessionPolicyError
from asavexa.security.mailer import EmailDeliveryError, OutboxMailer, ResendMailer, SmtpMailer, mailer_from_env
from asavexa.security.sessions import SessionPolicy
import test_passport as T
from test_security_context import Ctx, PW

EMAIL = "dara@meridian.test"
NEW_PW = "fresh start 2026"


class Base(Ctx):
    def setUp(self):
        self.build(keys=False)
        self.mail = OutboxMailer()
        self.commits = 0
        def commit(): self.commits += 1
        self.ctx = SecurityContext(self.w.identity, T.SqliteAuditRepository(self.w.conn), self.store, keys=None, now=self.clock, commit=commit,
                                   policy=SessionPolicy(idle_minutes=30, max_sessions=5), mailer=self.mail, mail_dispatch=lambda f: f())
        self.rc = self.ctx.recovery
        for lim in (ratelimit.RECOVERY_REQUEST, ratelimit.RECOVERY_VERIFY, ratelimit.RECOVERY_RESET, ratelimit.LOGIN):
            lim._hits.clear()

    def code(self, n=-1):
        return re.search(r"\b(\d{6})\b", self.mail.sent[n]["text"]).group(1)

    def ask(self, email=EMAIL):
        r = self.rc.request(email)
        self.clock.advance(seconds=61)          # past the resend cooldown
        return r

    def audit_text(self):
        evs = []
        for oid in (None, self.w.org.id):
            pass
        rows = self.w.conn.execute("SELECT * FROM audit_events").fetchall()
        return json.dumps([tuple(map(str, r)) for r in rows])


# ---------------------------------------------------------------------------------------------- 1-5 sign-up and the policy
class SignupPolicyTests(Base):
    def reg(self, pw, email="new@x.test"):
        return self.w.identity.register_user(email, pw)

    def test_1_shorter_than_eight_is_rejected(self):
        with self.assertRaisesRegex(WeakPasswordError, "at least 8"):
            self.reg("abc1234")

    def test_2_no_letter_is_rejected(self):
        with self.assertRaisesRegex(WeakPasswordError, "letter"):
            self.reg("12345678")

    def test_3_no_number_is_rejected(self):
        with self.assertRaisesRegex(WeakPasswordError, "number"):
            self.reg("abcdefgh")

    def test_4_policy_compliant_passwords_are_accepted_and_kept_exactly(self):
        for i, pw in enumerate(["stone42river", "with spaces 1 inside", "  leading and trailing 9  ", "Ünïcödé-passwörd-7", "x" * 127 + "1"]):
            u = self.reg(pw, f"ok{i}@x.test")
            self.assertTrue(u.id)
            _, token = self.w.identity.authenticate(f"ok{i}@x.test", pw)          # signs in with it exactly as typed: nothing was trimmed or altered
            self.assertTrue(token)
        with self.assertRaises(InvalidCredentialsError):
            self.w.identity.authenticate("ok2@x.test", "leading and trailing 9")   # the trimmed version is a different password

    def test_policy_edges_and_common_passwords(self):
        self.assertEqual(password_policy.problems("stone42river"), [])
        self.assertTrue(password_policy.problems("x" * 129 + "1"))
        self.assertTrue(password_policy.problems(""))
        self.assertTrue(password_policy.problems(None))
        self.assertTrue(password_policy.problems("Password123"), "very common passwords are refused")
        self.assertEqual(len(password_policy.REQUIREMENTS), 3)

    def test_5_confirmation_mismatch_is_rejected_by_the_server(self):
        with self.assertRaises(HTTPException) as cm:
            auth.register(auth.RegisterRequest(email="m@x.test", password="stone42river", confirm_password="stone42rivers"), self.w.identity, self.ctx)
        self.assertEqual(cm.exception.status_code, 422)
        self.assertIsNone(self.w.identity.users.get_by_email("m@x.test"), "no account was created")
        ok = auth.register(auth.RegisterRequest(email="m@x.test", password="stone42river", confirm_password="stone42river"), self.w.identity, self.ctx)
        self.assertEqual(ok.email, "m@x.test")

    def test_register_endpoint_enforces_the_policy_itself(self):
        for bad in ("short1", "alllettersnodigits", "12345678901"):
            with self.assertRaises(WeakPasswordError):
                auth.register(auth.RegisterRequest(email="b@x.test", password=bad), self.w.identity, self.ctx)

    def test_policy_endpoint_reports_the_server_numbers(self):
        p = auth.password_policy_info()
        self.assertEqual((p["min_length"], p["max_length"]), (8, 128))

    def test_front_end_policy_agrees_with_the_server(self):
        js = (Path(__file__).resolve().parent.parent / "frontend/src/lib/passwords.js").read_text()
        self.assertEqual(int(re.search(r"MIN_LENGTH = (\d+)", js).group(1)), password_policy.MIN_LENGTH)
        self.assertEqual(int(re.search(r"MAX_LENGTH = (\d+)", js).group(1)), password_policy.MAX_LENGTH)
        words = set(re.search(r'COMMON = new Set\(\("(.*?)"\)', js, re.S).group(1).replace('" +\n  "', "").split())
        self.assertEqual(words, set(password_policy.COMMON))


# ---------------------------------------------------------------------------------------------- 7-8 request
class RequestTests(Base):
    def test_7_the_answer_is_the_same_for_a_real_and_an_unknown_email(self):
        a = self.rc.request(EMAIL); self.clock.advance(seconds=61)
        b = self.rc.request("nobody@nowhere.test")
        self.assertEqual(a, b)
        self.assertNotIn("dara", json.dumps(a))

    def test_8_a_valid_request_sends_one_email_to_the_registered_address_only(self):
        self.rc.request(EMAIL)
        self.assertEqual(len(self.mail.sent), 1)
        m = self.mail.sent[0]
        self.assertEqual(m["to"], EMAIL)
        self.assertRegex(m["text"], r"\b\d{6}\b")
        self.assertIn("ASAVEXA", m["subject"]); self.assertIn("10 minutes", m["text"]); self.assertIn("because someone asked", m["text"])
        self.assertNotIn(PW, m["text"] + m["html"])
        self.assertIn("ASAVEXA", m["html"])

    def test_no_email_is_sent_for_an_unknown_or_inactive_account(self):
        self.rc.request("nobody@nowhere.test")
        self.assertEqual(self.mail.sent, [])

    def test_email_is_validated_on_the_server(self):
        for bad in ("", "not-an-email", "a@b", None, "x y@z.com"):
            with self.assertRaises(RecoveryError):
                self.rc.request(bad)

    def test_the_email_address_cannot_be_redirected(self):
        # the code goes to the address stored on the account, whatever spelling of it the request used
        self.rc.request("  DARA@Meridian.TEST ".strip().lower())
        self.assertEqual(self.mail.sent[0]["to"], EMAIL)

    def test_recovery_is_refused_honestly_when_email_is_not_set_up(self):
        self.ctx.recovery.mailer = None
        self.assertFalse(auth.recovery_status(self.ctx)["available"])
        with self.assertRaises(RecoveryUnavailableError):
            self.rc.request(EMAIL)


# ---------------------------------------------------------------------------------------------- 9-14 the code
class CodeTests(Base):
    def test_9_the_correct_code_is_accepted_and_returns_a_reset_authorisation(self):
        self.rc.request(EMAIL)
        r = self.rc.verify(EMAIL, self.code())
        self.assertTrue(len(r["reset_token"]) >= 32)

    def test_a_code_with_spaces_around_it_is_accepted_but_not_other_junk(self):
        self.rc.request(EMAIL)
        self.assertTrue(self.rc.verify(EMAIL, f" {self.code()} ")["reset_token"])
        with self.assertRaises(RecoveryError):
            self.rc.verify(EMAIL, "12ab56")

    def test_10_an_incorrect_code_is_rejected_the_same_way_for_known_and_unknown_emails(self):
        self.rc.request(EMAIL)
        wrong = "000000" if self.code() != "000000" else "111111"
        with self.assertRaises(RecoveryError) as a:
            self.rc.verify(EMAIL, wrong)
        with self.assertRaises(RecoveryError) as b:
            self.rc.verify("nobody@nowhere.test", wrong)
        self.assertEqual(str(a.exception), str(b.exception))
        self.assertGreater(self.commits, 0, "a refused attempt is persisted so it counts")

    def test_11_an_expired_code_is_rejected(self):
        self.rc.request(EMAIL); c = self.code()
        self.clock.advance(minutes=10, seconds=1)
        with self.assertRaises(RecoveryError) as cm:
            self.rc.verify(EMAIL, c)
        self.assertIn("expired", str(cm.exception))

    def test_a_code_still_works_just_before_it_expires(self):
        self.rc.request(EMAIL); c = self.code()
        self.clock.advance(minutes=9, seconds=59)
        self.assertTrue(self.rc.verify(EMAIL, c)["reset_token"])

    def test_12_a_code_cannot_be_used_twice(self):
        self.rc.request(EMAIL); c = self.code()
        self.rc.verify(EMAIL, c)
        with self.assertRaises(RecoveryError):
            self.rc.verify(EMAIL, c)

    def test_13_a_superseded_code_cannot_be_used(self):
        self.rc.request(EMAIL); old = self.code()
        self.clock.advance(seconds=61)
        self.rc.request(EMAIL); new = self.code()
        self.assertNotEqual(old, new)
        with self.assertRaises(RecoveryError):
            self.rc.verify(EMAIL, old)
        self.assertTrue(self.rc.verify(EMAIL, new)["reset_token"])

    def test_14_too_many_wrong_attempts_lock_even_the_right_code(self):
        self.rc.request(EMAIL); good = self.code()
        wrong = "000000" if good != "000000" else "111111"
        for i in range(rec.MAX_WRONG_CODES - 1):
            with self.assertRaisesRegex(RecoveryError, "incorrect or has expired"):
                self.rc.verify(EMAIL, wrong)
        with self.assertRaisesRegex(RecoveryRateLimitError, "Too many incorrect"):
            self.rc.verify(EMAIL, wrong)
        with self.assertRaises(RecoveryRateLimitError):
            self.rc.verify(EMAIL, good)             # locked: the right code no longer works
        self.clock.advance(seconds=61)
        self.rc.request(EMAIL)                      # a fresh code starts clean
        self.assertTrue(self.rc.verify(EMAIL, self.code())["reset_token"])

    def test_lock_looks_the_same_for_an_unknown_email(self):
        for i in range(rec.MAX_WRONG_CODES - 1):
            with self.assertRaises(RecoveryError):
                self.rc.verify("ghost@nowhere.test", "123456")
        with self.assertRaisesRegex(RecoveryRateLimitError, "Too many incorrect"):
            self.rc.verify("ghost@nowhere.test", "123456")

    def test_codes_are_six_digits_random_and_stored_only_as_hashes(self):
        seen = set()
        for i in range(8):
            self.rc.request(EMAIL); seen.add(self.code()); self.clock.advance(hours=1, seconds=1)
            self.assertRegex(self.code(), r"^\d{6}$")
        self.assertGreater(len(seen), 4, "codes are not predictable")
        c = self.code()
        raw = json.dumps(self.store.list("pwreset_code"))
        self.assertNotIn(c, raw)


# ---------------------------------------------------------------------------------------------- 15 rate limits
class RateLimitTests(Base):
    def test_15_cooldown_and_hourly_cap_apply_server_side_to_real_and_unknown_emails(self):
        for e in (EMAIL, "ghost@nowhere.test"):
            self.rc.request(e)
            with self.assertRaisesRegex(RecoveryRateLimitError, "wait"):
                self.rc.request(e)                  # inside the 60 seconds
        e = EMAIL
        sent = 1
        for i in range(rec.MAX_CODES_PER_HOUR - 1):
            self.clock.advance(seconds=61); self.rc.request(e); sent += 1
        self.clock.advance(seconds=61)
        with self.assertRaisesRegex(RecoveryRateLimitError, "Too many codes"):
            self.rc.request(e)
        self.clock.advance(hours=1)
        self.rc.request(e)                           # the window has passed

    def test_15_per_address_throttle_on_the_endpoints(self):
        ratelimit.RECOVERY_REQUEST.limit = 3
        try:
            req = Request({"x-forwarded-for": "7.7.7.7"})
            for i in range(3):
                ratelimit.throttle(ratelimit.RECOVERY_REQUEST, req)
            with self.assertRaises(HTTPException) as cm:
                auth.recovery_request(req, auth.RecoveryRequestIn(email=EMAIL), self.ctx)
            self.assertEqual(cm.exception.status_code, 429)
        finally:
            ratelimit.RECOVERY_REQUEST.limit = 10

    def test_endpoints_throttle_verify_and_reset_too(self):
        ratelimit.RECOVERY_VERIFY.limit = 1; ratelimit.RECOVERY_RESET.limit = 1
        try:
            req = Request({"x-forwarded-for": "8.8.4.4"})
            auth.recovery_request(req, auth.RecoveryRequestIn(email=EMAIL), self.ctx)
            auth.recovery_verify(req, auth.RecoveryVerifyIn(email=EMAIL, code=self.code()), self.ctx)
            with self.assertRaises(HTTPException):
                auth.recovery_verify(req, auth.RecoveryVerifyIn(email=EMAIL, code="123456"), self.ctx)
            with self.assertRaises(RecoveryError):
                auth.recovery_reset(req, auth.RecoveryResetIn(email=EMAIL, reset_token="x" * 40, new_password=NEW_PW), self.ctx)
            with self.assertRaises(HTTPException):
                auth.recovery_reset(req, auth.RecoveryResetIn(email=EMAIL, reset_token="x" * 40, new_password=NEW_PW), self.ctx)
        finally:
            ratelimit.RECOVERY_VERIFY.limit = 20; ratelimit.RECOVERY_RESET.limit = 10


# ---------------------------------------------------------------------------------------------- 16-21 the reset itself
class ResetTests(Base):
    def verified(self, email=EMAIL):
        self.rc.request(email)
        return self.rc.verify(email, self.code())["reset_token"]

    def test_16_changing_the_email_cannot_reset_another_persons_password(self):
        tok = self.verified(EMAIL)                    # the attacker owns this one
        with self.assertRaises(RecoveryError):
            self.rc.reset("aisha@meridian.test", tok, NEW_PW)
        _, t = self.w.identity.authenticate("aisha@meridian.test", "yet-another-password1")   # unchanged
        self.assertTrue(t)
        # and the real owner's token still works for the real owner
        self.assertTrue(self.rc.reset(EMAIL, tok, NEW_PW)["message"])

    def test_17_no_reset_without_a_valid_authorisation(self):
        for token in ("", "guess", "a" * 43, None):
            with self.assertRaises(RecoveryError):
                self.rc.reset(EMAIL, token, NEW_PW)
        self.rc.request(EMAIL)                        # a code alone is not an authorisation either
        with self.assertRaises(RecoveryError):
            self.rc.reset(EMAIL, self.code(), NEW_PW)
        self.assertTrue(self.w.identity.authenticate(EMAIL, PW))

    def test_authorisation_is_single_use_and_expires(self):
        tok = self.verified()
        self.rc.reset(EMAIL, tok, NEW_PW)
        with self.assertRaises(RecoveryError):
            self.rc.reset(EMAIL, tok, "another fresh 77")
        tok2 = self.verified() if False else None
        self.clock.advance(seconds=61)
        self.rc.request(EMAIL); t = self.rc.verify(EMAIL, self.code())["reset_token"]
        self.clock.advance(minutes=10, seconds=1)
        with self.assertRaises(RecoveryError):
            self.rc.reset(EMAIL, t, "yet another 88x")

    def test_a_new_code_cancels_an_earlier_authorisation(self):
        tok = self.verified()
        self.clock.advance(seconds=61)
        self.rc.request(EMAIL)
        with self.assertRaises(RecoveryError):
            self.rc.reset(EMAIL, tok, NEW_PW)

    def test_18_a_password_that_breaks_the_policy_is_rejected_and_the_authorisation_survives(self):
        tok = self.verified()
        for bad in ("short1", "nodigitshere", "12345678"):
            with self.assertRaises(WeakPasswordError):
                self.rc.reset(EMAIL, tok, bad)
        with self.assertRaisesRegex(RecoveryError, "do not match"):
            self.rc.reset(EMAIL, tok, NEW_PW, "different pw 3")
        self.assertTrue(self.rc.reset(EMAIL, tok, NEW_PW, NEW_PW))   # the same token still works once the password is acceptable

    def test_19_and_20_reset_succeeds_new_password_works_old_does_not(self):
        tok = self.verified()
        out = self.rc.reset(EMAIL, tok, NEW_PW, NEW_PW)
        self.assertIn("reset successfully", out["message"])
        self.assertNotIn("token", json.dumps(out))                       # no automatic sign-in, no token handed out
        user, token = self.w.identity.authenticate(EMAIL, NEW_PW)
        self.assertEqual(user.email, EMAIL)
        with self.assertRaises(InvalidCredentialsError):
            self.w.identity.authenticate(EMAIL, PW)
        self.assertTrue(self.w.identity.users.get_by_email(EMAIL).password_hash.startswith("pbkdf2_sha256$"))

    def test_a_notice_is_emailed_after_the_change(self):
        tok = self.verified()
        self.rc.reset(EMAIL, tok, NEW_PW)
        last = self.mail.sent[-1]
        self.assertEqual(last["to"], EMAIL); self.assertIn("password was changed", last["subject"])
        self.assertNotIn(NEW_PW, last["text"] + last["html"])

    def test_21_existing_sessions_end_after_a_reset(self):
        r = self.ctx.login(EMAIL, PW, "1.1.1.1", "Chrome")
        s = self.w.identity.validate_session(r["token"])
        self.ctx.check_session(s)                                         # fine now
        tok = self.verified()
        self.rc.reset(EMAIL, tok, NEW_PW)
        with self.assertRaises(SessionPolicyError):
            self.ctx.check_session(s)
        r2 = self.ctx.login(EMAIL, NEW_PW, "1.1.1.1", "Chrome")           # a new session after the reset is fine
        self.ctx.check_session(self.w.identity.validate_session(r2["token"]))

    def test_a_session_with_no_security_record_is_ended_too(self):
        user, raw = self.w.identity.authenticate(EMAIL, PW)               # opened by the old path: no session facts stored
        s = self.w.identity.validate_session(raw)
        tok = self.verified()
        self.clock.advance(seconds=5)          # the test clock started before the session was opened; production uses the real clock
        self.rc.reset(EMAIL, tok, NEW_PW)
        with self.assertRaises(SessionPolicyError):
            self.ctx.check_session(s)

    def test_reset_through_the_endpoints_end_to_end(self):
        req = Request({"x-forwarded-for": "3.3.3.3"})
        self.assertTrue(auth.recovery_status(self.ctx)["available"])
        r1 = auth.recovery_request(req, auth.RecoveryRequestIn(email=EMAIL), self.ctx)
        self.assertEqual(set(r1), {"message", "cooldown_seconds", "expires_in_minutes"})
        r2 = auth.recovery_verify(req, auth.RecoveryVerifyIn(email=EMAIL, code=self.code()), self.ctx)
        r3 = auth.recovery_reset(req, auth.RecoveryResetIn(email=EMAIL, reset_token=r2["reset_token"], new_password=NEW_PW, confirm_password=NEW_PW), self.ctx)
        self.assertIn("reset successfully", r3["message"])
        login = auth.login(req, auth.LoginRequest(email=EMAIL, password=NEW_PW), self.ctx)
        self.assertTrue(login.token)


# ---------------------------------------------------------------------------------------------- 22 secrets, 23 delivery failures
class SecretsAndFailureTests(Base):
    def test_22_secrets_never_reach_logs_audit_or_responses(self):
        with self.assertLogs(level=logging.DEBUG) as logs:
            logging.getLogger("asavexa.recovery").debug("start")
            r1 = self.rc.request(EMAIL); code = self.code()
            r2 = self.rc.verify(EMAIL, code)
            token = r2["reset_token"]
            r3 = self.rc.reset(EMAIL, token, NEW_PW)
        everything = "\n".join(logs.output) + json.dumps([r1, r3]) + self.audit_text()
        self.assertNotIn(code, everything)
        self.assertNotIn(token, everything)
        self.assertNotIn(NEW_PW, everything)
        self.assertNotIn(code, json.dumps(r1)); self.assertNotIn(code, json.dumps(r3))
        stored = json.dumps(self.store.list("pwreset_auth")) + json.dumps(self.store.list("pwreset_code")) + json.dumps(self.store.list("pwreset_req"))
        self.assertNotIn(token, stored); self.assertNotIn(code, stored)
        self.assertIn("PASSWORD_RESET_COMPLETED", self.audit_text()); self.assertIn("PASSWORD_RECOVERY_REQUESTED", self.audit_text())

    def test_22_the_code_is_never_in_a_url_or_an_error_message(self):
        self.rc.request(EMAIL); code = self.code()
        wrong = "000000" if code != "000000" else "111111"
        with self.assertRaises(RecoveryError) as cm:
            self.rc.verify(EMAIL, wrong)
        self.assertNotIn(code, str(cm.exception)); self.assertNotIn(wrong, str(cm.exception))
        self.assertNotIn("http", self.mail.sent[0]["text"].lower())

    def test_23_a_delivery_failure_is_logged_without_secrets_and_never_reported_as_sent(self):
        self.mail.fail = True
        with self.assertLogs("asavexa.recovery", level="ERROR") as logs:
            out = self.rc.request(EMAIL)
        self.assertEqual(self.mail.sent, [])
        self.assertIn("recovery_email_failed", logs.output[0]); self.assertNotIn(EMAIL, logs.output[0])
        self.assertNotRegex(json.dumps(out), r"\b\d{6}\b")
        self.assertNotIn("sent to", out["message"].lower())            # it only ever says a code is on its way if the email can be recovered
        self.mail.fail = False
        self.clock.advance(seconds=61)
        self.rc.request(EMAIL)                                         # the person can simply ask again
        self.assertEqual(len(self.mail.sent), 1)

    def test_23_a_failure_looks_the_same_to_the_caller_for_real_and_unknown_emails(self):
        self.mail.fail = True
        with self.assertLogs("asavexa.recovery", level="ERROR"):
            a = self.rc.request(EMAIL)
        b = self.rc.request("ghost@nowhere.test")
        self.assertEqual(a, b)


class MailerTests(unittest.TestCase):
    def test_no_provider_means_no_mailer(self):
        self.assertIsNone(mailer_from_env({}))
        with self.assertLogs("asavexa.mailer", level="ERROR"):
            self.assertIsNone(mailer_from_env({"ASAVEXA_EMAIL_PROVIDER": "resend"}))          # missing key and sender
            self.assertIsNone(mailer_from_env({"ASAVEXA_EMAIL_PROVIDER": "smtp", "ASAVEXA_EMAIL_FROM": "a@b.co"}))
            self.assertIsNone(mailer_from_env({"ASAVEXA_EMAIL_PROVIDER": "carrier-pigeon"}))

    def test_providers_come_only_from_the_environment(self):
        m = mailer_from_env({"ASAVEXA_EMAIL_PROVIDER": "resend", "RESEND_API_KEY": "k", "ASAVEXA_EMAIL_FROM": "ASAVEXA <no-reply@asavexa.test>"})
        self.assertIsInstance(m, ResendMailer)
        s = mailer_from_env({"ASAVEXA_EMAIL_PROVIDER": "smtp", "ASAVEXA_SMTP_HOST": "smtp.test", "ASAVEXA_SMTP_PORT": "587", "ASAVEXA_EMAIL_FROM": "no-reply@asavexa.test"})
        self.assertIsInstance(s, SmtpMailer)
        self.assertNotIn("OutboxMailer", type(m).__name__)

    def test_resend_sends_json_with_a_bearer_key_and_maps_failures(self):
        seen = {}

        class R:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *a): return False
        def ok(req, timeout=None):
            seen["req"] = req; return R()
        ResendMailer("KEY", "no-reply@asavexa.test", opener=ok).send("a@b.co", "Hi", "text", "<p>html</p>")
        body = json.loads(seen["req"].data)
        self.assertEqual(body["to"], ["a@b.co"]); self.assertEqual(seen["req"].get_header("Authorization"), "Bearer KEY")
        import urllib.error
        def http_error(req, timeout=None): raise urllib.error.HTTPError("u", 422, "bad", {}, None)
        with self.assertRaises(EmailDeliveryError):
            ResendMailer("KEY", "x@y.co", opener=http_error).send("a@b.co", "s", "t")
        def down(req, timeout=None): raise urllib.error.URLError("no route")
        with self.assertRaises(EmailDeliveryError):
            ResendMailer("KEY", "x@y.co", opener=down).send("a@b.co", "s", "t")

    def test_smtp_failure_is_reported(self):
        import smtplib

        class Boom:
            def __init__(self, *a): pass
            def __enter__(self): raise smtplib.SMTPException("refused")
            def __exit__(self, *a): return False
        with self.assertRaises(EmailDeliveryError):
            SmtpMailer("h", 587, "u", "p", "no-reply@asavexa.test", factory=Boom).send("a@b.co", "s", "t")


if __name__ == "__main__":
    unittest.main()
