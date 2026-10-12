"""
Email at sign-up: the welcome email, the 6-digit verification code, resend, delivery events (webhooks), the provider settings and the templates.
Real identity service, real security context, real SQLite storage and the real API router functions (fastapi itself is stubbed by
harness_security_routers). Email goes to an in-memory outbox: no real message is ever sent, so nothing here claims a live delivery.
"""
import base64
import hashlib
import hmac
import json
import logging
import re
import unittest
from datetime import timedelta

import harness_security_routers as H
from harness_security_routers import auth, HTTPException, Request
from asavexa.api import ratelimit
from asavexa.identity.domain.errors import DuplicateEmailError
from asavexa.security import emailtemplates as T
from asavexa.security import verification as ver
from asavexa.security.context import SecurityContext
from asavexa.security.errors import VerificationError, VerificationRateLimitError, VerificationUnavailableError, WebhookError
from asavexa.security.mailer import EmailSettings, OutboxMailer, email_settings_from_env, mailer_from_env, sender_from_env, ResendMailer
from asavexa.security.mailevents import MailEvents
from asavexa.security.sessions import SessionPolicy
import test_passport as T0
from test_security_context import Ctx

NEW = "newbie@x.test"
PASSWORD = "stone42river"
SECRET_BYTES = b"unit-test-signing-key"
WEBHOOK_SECRET = "whsec_" + base64.b64encode(SECRET_BYTES).decode()


class Base(Ctx):
    def build_ctx(self, mailer="outbox", settings=None, webhook_secret=WEBHOOK_SECRET):
        self.mail = OutboxMailer() if mailer == "outbox" else mailer
        self.ctx = SecurityContext(self.w.identity, T0.SqliteAuditRepository(self.w.conn), self.store, keys=None, now=self.clock, commit=lambda: None,
                                   policy=SessionPolicy(idle_minutes=30, max_sessions=5), mailer=self.mail, mail_dispatch=lambda f: f(),
                                   email_settings=settings, webhook_secret=webhook_secret)
        self.v = self.ctx.verification

    def setUp(self):
        self.build(keys=False)
        self.build_ctx()
        for lim in (ratelimit.REGISTER, ratelimit.VERIFY_REQUEST, ratelimit.VERIFY_CONFIRM, ratelimit.RECOVERY_REQUEST):
            lim._hits.clear()

    def signup(self, email=NEW, password=PASSWORD, request=None):
        return auth.register(auth.RegisterRequest(email=email, password=password), self.w.identity, self.ctx, request)

    def code(self, n=-1, to=None):
        msgs = [m for m in self.mail.sent if "verification code" in m["text"].lower() and "email" in m["subject"].lower()]
        return re.search(r"\b(\d{6})\b", msgs[n]["text"]).group(1)

    def subjects(self):
        return [m["subject"] for m in self.mail.sent]

    def everything_stored(self):
        docs = json.dumps([(k, d) for kind in ("emailv_code", "emailv_ok", "emailv_req", "emailv_try", "welcome_sent")
                           for k, d in self.store.list(kind)], default=str)
        audit = json.dumps([tuple(map(str, r)) for r in self.w.conn.execute("SELECT * FROM audit_events").fetchall()])
        return docs + audit


# ------------------------------------------------------------------------------------------------ welcome email + signup answer
class WelcomeTests(Base):
    def test_registration_sends_the_welcome_and_the_code_to_the_registered_address_only(self):
        r = self.signup()
        self.assertEqual(r.email, NEW)
        self.assertEqual({m["to"] for m in self.mail.sent}, {NEW})
        self.assertEqual(self.subjects(), ["Welcome to ASAVEXA — Your Account Has Been Created Successfully", "Verify your email address for ASAVEXA"])

    def test_the_answer_says_sent_only_because_the_provider_accepted_both(self):
        r = self.signup()
        d = r.email_delivery
        self.assertTrue(d["sent"]); self.assertIsNone(d["reason"]); self.assertEqual(d["expires_in_minutes"], 10); self.assertEqual(d["cooldown_seconds"], 60)

    def test_provider_down_keeps_the_account_and_says_not_sent(self):
        self.mail.fail = True
        with self.assertLogs("asavexa.verification", level="ERROR"):
            r = self.signup()
        self.assertFalse(r.email_delivery["sent"]); self.assertEqual(r.email_delivery["reason"], "delivery_failed")
        self.assertIsNotNone(self.w.identity.users.get_by_email(NEW), "the account was NOT deleted because email failed")
        self.assertEqual(r.email_delivery["cooldown_seconds"], 0, "a failed send does not start a wait: retry at once")

    def test_no_provider_configured_is_reported_honestly_and_the_account_is_kept(self):
        self.build_ctx(mailer=None)
        with self.assertLogs("asavexa.verification", level="ERROR"):
            r = self.signup()
        self.assertFalse(r.email_delivery["sent"]); self.assertEqual(r.email_delivery["reason"], "not_configured")
        self.assertIsNotNone(self.w.identity.users.get_by_email(NEW))

    def test_double_submit_cannot_create_two_accounts_or_send_two_emails(self):
        self.signup()
        n = len(self.mail.sent)
        with self.assertRaises(DuplicateEmailError):
            self.signup()
        with self.assertRaises(DuplicateEmailError):
            self.signup(email=NEW.upper())                   # same address, different capitalisation
        self.assertEqual(len(self.mail.sent), n, "no extra email for the refused sign-ups")
        users = [r[0] for r in self.w.conn.execute("SELECT email FROM users WHERE lower(email)=?", (NEW,)).fetchall()]
        self.assertEqual(users, [NEW])

    def test_mixed_case_sign_in_still_finds_the_account(self):
        self.signup(email="Mixed@X.test")
        self.assertIsNotNone(self.w.identity.users.get_by_email("mixed@x.test"))
        self.assertIsNotNone(self.w.identity.users.get_by_email("MIXED@x.TEST"))

    def test_welcome_is_sent_once_per_account_even_if_the_flow_is_called_again(self):
        u = self.w.identity.users.get_by_email(self.signup().email)
        self.v.on_registered(u)                              # a retry of the same step
        self.assertEqual(sum("Welcome" in s for s in self.subjects()), 1)

    def test_register_route_is_rate_limited_per_address(self):
        req = Request({"x-forwarded-for": "7.7.7.7"})
        for i in range(10):
            self.signup(email=f"u{i}@x.test", request=req)
        with self.assertRaises(HTTPException) as cm:
            self.signup(email="u11@x.test", request=req)
        self.assertEqual(cm.exception.status_code, 429)


# ------------------------------------------------------------------------------------------------ the code itself
class CodeTests(Base):
    def test_code_is_six_digits_hashed_and_never_stored_returned_or_logged(self):
        with self.assertLogs("asavexa.verification", level="DEBUG") as logs:
            logging.getLogger("asavexa.verification").debug("marker")
            r = self.signup()
        code = self.code()
        self.assertRegex(code, r"^\d{6}$")
        self.assertNotIn(code, self.everything_stored(), "neither the store nor the audit trail holds the code")
        self.assertNotIn(code, json.dumps(r.model_dump(), default=str) if hasattr(r, "model_dump") else str(r.__dict__))
        self.assertNotIn(code, "\n".join(logs.output))
        rec = self.store.get("emailv_code", r.id)
        self.assertEqual(set(rec), {"salt", "hash", "expires_at", "created_at", "state"})

    def test_correct_code_verifies_the_registered_address_and_is_single_use(self):
        r = self.signup()
        self.assertFalse(self.v.is_verified(r.id))
        out = self.v.confirm(NEW, self.code())
        self.assertTrue(out["verified"]); self.assertTrue(self.v.is_verified(r.id))
        with self.assertRaises(VerificationError):
            self.v.confirm(NEW, self.code())                 # the same code again: refused

    def test_sending_alone_never_marks_verified(self):
        r = self.signup()
        self.assertFalse(self.v.is_verified(r.id))

    def test_wrong_code_is_refused_and_does_not_verify(self):
        r = self.signup()
        wrong = "000000" if self.code() != "000000" else "111111"
        with self.assertRaisesRegex(VerificationError, "incorrect or has expired"):
            self.v.confirm(NEW, wrong)
        self.assertFalse(self.v.is_verified(r.id))

    def test_expired_code_is_refused(self):
        r = self.signup(); c = self.code()
        self.clock.advance(minutes=10, seconds=1)
        with self.assertRaisesRegex(VerificationError, "incorrect or has expired"):
            self.v.confirm(NEW, c)
        self.assertFalse(self.v.is_verified(r.id))

    def test_expiry_is_configurable(self):
        self.build_ctx(settings=EmailSettings(verification_ttl_minutes=3))
        r = self.signup(email="short@x.test"); c = self.code()
        self.assertEqual(r.email_delivery["expires_in_minutes"], 3)
        self.assertIn("3 minutes", self.mail.sent[-1]["text"])
        self.clock.advance(minutes=3, seconds=1)
        with self.assertRaises(VerificationError):
            self.v.confirm("short@x.test", c)

    def test_a_new_code_supersedes_the_old_one(self):
        self.signup(); old = self.code()
        self.clock.advance(seconds=61)
        self.v.request(NEW)
        new = self.code()
        if new != old:
            with self.assertRaises(VerificationError):
                self.v.confirm(NEW, old)
        self.assertTrue(self.v.confirm(NEW, new)["verified"])

    def test_five_wrong_guesses_lock_it_and_even_the_right_code_then_waits_for_a_new_one(self):
        self.signup(); c = self.code()
        bad = "000000" if c != "000000" else "111111"
        for i in range(4):
            with self.assertRaises(VerificationError):
                self.v.confirm(NEW, bad)
        with self.assertRaises(VerificationRateLimitError):
            self.v.confirm(NEW, bad)
        with self.assertRaises(VerificationRateLimitError):
            self.v.confirm(NEW, c)                           # locked: brute force cannot finish by luck
        self.clock.advance(seconds=61)
        self.v.request(NEW)                                  # a new code resets the guesses
        self.assertTrue(self.v.confirm(NEW, self.code())["verified"])

    def test_a_code_cannot_verify_another_persons_address(self):
        self.signup(email="a@x.test"); self.signup(email="b@x.test")
        a_code = [re.search(r"\b(\d{6})\b", m["text"]).group(1) for m in self.mail.sent if m["to"] == "a@x.test" and "Verify" in m["subject"]][0]
        b = self.w.identity.users.get_by_email("b@x.test")
        try:
            self.v.confirm("b@x.test", a_code)
        except VerificationError:
            pass
        self.assertFalse(self.v.is_verified(b.id))

    def test_malformed_codes_and_emails_are_refused(self):
        for bad in ("", "12345", "1234567", "abcdef", None):
            with self.assertRaises(VerificationError):
                self.v.confirm(NEW, bad)
        with self.assertRaises(VerificationError):
            self.v.confirm("not-an-email", "123456")


# ------------------------------------------------------------------------------------------------ resend and privacy
class ResendTests(Base):
    def test_resend_waits_60_seconds_then_works(self):
        self.signup()
        with self.assertRaisesRegex(VerificationRateLimitError, "wait"):
            self.v.request(NEW)
        self.clock.advance(seconds=61)
        out = self.v.request(NEW)
        self.assertEqual(out["cooldown_seconds"], 60)
        self.assertEqual(sum("Verify your email" in s for s in self.subjects()), 2)

    def test_resend_does_not_send_a_second_welcome(self):
        self.signup(); self.clock.advance(seconds=61); self.v.request(NEW)
        self.assertEqual(sum("Welcome" in s for s in self.subjects()), 1)

    def test_resend_sends_the_welcome_that_never_got_through(self):
        self.mail.fail = True
        with self.assertLogs("asavexa.verification", level="ERROR"):
            self.signup()
        self.mail.fail = False
        out = self.v.request(NEW)                             # a failed first send does not start the 60 second wait
        self.assertTrue(out["message"])
        self.assertEqual(self.subjects(), ["Welcome to ASAVEXA — Your Account Has Been Created Successfully", "Verify your email address for ASAVEXA"])

    def test_at_most_five_codes_an_hour(self):
        self.signup()
        for i in range(4):
            self.clock.advance(seconds=61); self.v.request(NEW)
        self.clock.advance(seconds=61)
        with self.assertRaisesRegex(VerificationRateLimitError, "hour"):
            self.v.request(NEW)
        self.clock.advance(hours=1)
        self.v.request(NEW)

    def test_answers_are_identical_for_real_unknown_and_already_verified_emails(self):
        self.signup(); self.v.confirm(NEW, self.code())
        self.signup(email="other@x.test")
        self.clock.advance(seconds=61)
        a = self.v.request("other@x.test"); b = self.v.request("ghost@nowhere.test"); c = self.v.request(NEW)
        self.assertEqual(a, b); self.assertEqual(b, c)
        n = len(self.mail.sent)
        self.clock.advance(seconds=61); self.v.request(NEW); self.v.request("ghost@nowhere.test")
        self.assertEqual(len(self.mail.sent), n, "nothing is emailed to an unknown or already-verified address")

    def test_unavailable_when_no_provider_is_configured(self):
        self.build_ctx(mailer=None)
        self.assertFalse(self.v.available)
        with self.assertRaises(VerificationUnavailableError):
            self.v.request(NEW)
        self.assertEqual(auth.verification_status(self.ctx), {"available": False})

    def test_routes(self):
        req = Request({"x-forwarded-for": "8.8.8.8"})
        self.assertEqual(auth.verification_status(self.ctx), {"available": True})
        self.signup()
        r = auth.verification_confirm(req, auth.VerificationConfirmIn(email=NEW, code=self.code()), self.ctx)
        self.assertTrue(r["verified"])
        u = self.w.identity.users.get_by_email(NEW)
        self.assertEqual(auth.email_status(u.id, self.ctx), {"email_verified": True})
        self.clock.advance(seconds=61)
        self.assertIn("message", auth.verification_request(req, auth.VerificationRequestIn(email="ghost@x.test"), self.ctx))

    def test_routes_are_throttled_per_address(self):
        req = Request({"x-forwarded-for": "9.1.1.1"})
        for i in range(20):
            try:
                auth.verification_confirm(req, auth.VerificationConfirmIn(email="a@x.test", code="123456"), self.ctx)
            except VerificationError:
                pass
        with self.assertRaises(HTTPException) as cm:
            auth.verification_confirm(req, auth.VerificationConfirmIn(email="a@x.test", code="123456"), self.ctx)
        self.assertEqual(cm.exception.status_code, 429)


# ------------------------------------------------------------------------------------------------ delivery events
def _sign(body: bytes, mid="msg_1", ts=None, key=SECRET_BYTES, clock=None):
    ts = str(ts if ts is not None else int(clock().timestamp()))
    sig = base64.b64encode(hmac.new(key, f"{mid}.{ts}.".encode() + body, hashlib.sha256).digest()).decode()
    return {"svix-id": mid, "svix-timestamp": ts, "svix-signature": f"v1,{sig}"}


class WebhookTests(Base):
    def event(self, kind="email.delivered", to=NEW):
        return json.dumps({"type": kind, "data": {"email_id": "re_123", "to": [to]}}).encode()

    def test_a_correctly_signed_delivery_event_is_recorded_without_the_address(self):
        body = self.event("email.bounced")
        out = self.ctx.mail_events.handle(body, _sign(body, clock=self.clock))
        self.assertEqual(out, {"ok": True, "recorded": True})
        st = self.ctx.mail_events.status_for(NEW)
        self.assertEqual(st["status"], "bounced")
        dump = json.dumps([(k, d) for k, d in self.store.list("mail_status")])
        self.assertNotIn(NEW, dump)

    def test_delivered_and_complained_are_understood(self):
        for i, (t, want) in enumerate([("email.delivered", "delivered"), ("email.complained", "complained")]):
            body = self.event(t, to=f"p{i}@x.test")
            self.ctx.mail_events.handle(body, _sign(body, mid=f"m{i}", clock=self.clock))
            self.assertEqual(self.ctx.mail_events.status_for(f"p{i}@x.test")["status"], want)

    def test_wrong_signature_is_refused_and_records_nothing(self):
        body = self.event()
        with self.assertRaises(WebhookError):
            self.ctx.mail_events.handle(body, _sign(body, key=b"someone-elses-key", clock=self.clock))
        self.assertIsNone(self.ctx.mail_events.status_for(NEW))

    def test_tampered_body_is_refused(self):
        body = self.event(); headers = _sign(body, clock=self.clock)
        with self.assertRaises(WebhookError):
            self.ctx.mail_events.handle(self.event("email.bounced"), headers)

    def test_missing_headers_and_old_timestamps_are_refused(self):
        body = self.event()
        with self.assertRaises(WebhookError):
            self.ctx.mail_events.handle(body, {})
        with self.assertRaises(WebhookError):
            self.ctx.mail_events.handle(body, _sign(body, ts=int(self.clock().timestamp()) - 3600))

    def test_a_replayed_message_id_is_ignored(self):
        body = self.event(); h = _sign(body, clock=self.clock)
        self.ctx.mail_events.handle(body, h)
        again = self.ctx.mail_events.handle(self.event("email.bounced"), _sign(self.event("email.bounced"), mid="msg_1", clock=self.clock))
        self.assertTrue(again["duplicate"])
        self.assertEqual(self.ctx.mail_events.status_for(NEW)["status"], "delivered", "the replay changed nothing")

    def test_without_a_secret_the_webhook_is_off_and_trusts_nothing(self):
        self.build_ctx(webhook_secret=None)
        body = self.event()
        with self.assertRaisesRegex(WebhookError, "not set up"):
            self.ctx.mail_events.handle(body, _sign(body, clock=self.clock))

    def test_unknown_event_types_are_acknowledged_but_not_recorded(self):
        body = json.dumps({"type": "domain.created", "data": {}}).encode()
        self.assertEqual(self.ctx.mail_events.handle(body, _sign(body, clock=self.clock)), {"ok": True, "recorded": False})


# ------------------------------------------------------------------------------------------------ provider settings
class SettingsTests(unittest.TestCase):
    def test_new_variable_names_configure_resend_with_a_named_sender(self):
        env = {"EMAIL_PROVIDER": "resend", "EMAIL_API_KEY": "k", "EMAIL_FROM_ADDRESS": "no-reply@asavexa.test", "EMAIL_FROM_NAME": "ASAVEXA"}
        m = mailer_from_env(env)
        self.assertIsInstance(m, ResendMailer); self.assertEqual(m.sender, "ASAVEXA <no-reply@asavexa.test>")

    def test_old_variable_names_still_work(self):
        m = mailer_from_env({"ASAVEXA_EMAIL_PROVIDER": "resend", "RESEND_API_KEY": "k", "ASAVEXA_EMAIL_FROM": "ASAVEXA <no-reply@asavexa.test>"})
        self.assertIsInstance(m, ResendMailer)

    def test_default_sender_name_and_prebuilt_sender(self):
        self.assertEqual(sender_from_env({"EMAIL_FROM_ADDRESS": "a@b.co"}), "ASAVEXA <a@b.co>")
        self.assertEqual(sender_from_env({"EMAIL_FROM_ADDRESS": "Team <a@b.co>"}), "Team <a@b.co>")

    def test_missing_pieces_mean_no_mailer(self):
        with self.assertLogs("asavexa.mailer", level="ERROR"):
            self.assertIsNone(mailer_from_env({"EMAIL_PROVIDER": "resend", "EMAIL_API_KEY": "k"}))     # no sender
            self.assertIsNone(mailer_from_env({"EMAIL_PROVIDER": "resend", "EMAIL_FROM_ADDRESS": "a@b.co"}))  # no key

    def test_non_secret_settings(self):
        s = email_settings_from_env({"APP_BASE_URL": "https://app.asavexa.test/", "SUPPORT_EMAIL": "help@asavexa.test",
                                     "EMAIL_VERIFICATION_CODE_TTL_MINUTES": "15", "PASSWORD_RESET_CODE_TTL_MINUTES": "5"})
        self.assertEqual((s.app_base_url, s.support_email, s.verification_ttl_minutes, s.reset_ttl_minutes), ("https://app.asavexa.test", "help@asavexa.test", 15, 5))
        d = email_settings_from_env({})
        self.assertEqual((d.app_base_url, d.verification_ttl_minutes, d.reset_ttl_minutes), (None, 10, 10))
        with self.assertLogs("asavexa.mailer", level="ERROR"):
            self.assertIsNone(email_settings_from_env({"APP_BASE_URL": "javascript:alert(1)"}).app_base_url)
        self.assertEqual(email_settings_from_env({"EMAIL_VERIFICATION_CODE_TTL_MINUTES": "abc"}).verification_ttl_minutes, 10)

    def test_the_app_link_and_support_address_reach_the_welcome_email(self):
        m = T.account_created("https://app.asavexa.test", "help@asavexa.test")
        self.assertIn("https://app.asavexa.test", m.text); self.assertIn("href='https://app.asavexa.test'", m.html)
        self.assertIn("help@asavexa.test", m.text)
        self.assertNotIn("href=", T.account_created().html.replace("mailto", ""), "no link when no app address is configured")


# ------------------------------------------------------------------------------------------------ templates
class TemplateTests(unittest.TestCase):
    def all(self):
        return [T.account_created("https://a.test", "h@a.test"), T.verify_email("123456", 10), T.recovery_code("654321", 10),
                T.password_changed("h@a.test"), T.security_alert("New sign-in method", "Single sign-on was switched on.", "h@a.test")]

    def test_every_template_has_subject_text_and_responsive_html(self):
        for m in self.all():
            self.assertTrue(m.subject and m.text and m.html)
            self.assertIn("viewport", m.html); self.assertIn("max-width:600px", m.html); self.assertIn("<h1", m.html); self.assertIn("lang='en'", m.html)

    def test_code_emails_state_expiry_and_the_ignore_advice_in_both_versions(self):
        for m in (T.verify_email("123456", 10), T.recovery_code("654321", 10)):
            self.assertIn("10 minutes", m.text); self.assertIn("10 minutes", m.html)
            self.assertRegex(m.text.lower(), r"ignore this email"); self.assertRegex(m.html.lower(), r"ignore this email")

    def test_the_welcome_email_explains_the_remaining_step_and_safety(self):
        m = T.account_created()
        self.assertIn("verification code", m.text); self.assertIn("Never share your password", m.text)

    def test_html_escapes_everything_it_is_given(self):
        m = T.security_alert("<script>x</script>", "<img src=x onerror=alert(1)>")
        self.assertNotIn("<script>", m.html); self.assertNotIn("<img src=x", m.html)

    def test_no_template_carries_a_session_token_or_identifier(self):
        for m in self.all():
            blob = (m.text + m.html).lower()
            for bad in ("token", "uuid", "session id", "bearer"):
                self.assertNotIn(bad, blob)

    def test_the_security_note_is_in_the_code_emails(self):
        self.assertIn("never ask you for your password", T.verify_email("123456", 10).text)


if __name__ == "__main__":
    unittest.main()
