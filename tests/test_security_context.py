"""The sign-in flows and per-request checks, end to end against the real identity service and audit repository."""
import unittest
from datetime import datetime, timedelta, timezone

from asavexa.identity.domain.errors import AccountLockedError, InvalidCredentialsError
from asavexa.security import crypto, totp
from asavexa.security.context import SecurityContext
from asavexa.security.errors import KeysNotConfiguredError, MfaError, MfaLockedError, MfaRequiredError, OidcError, SessionPolicyError
from asavexa.security.objectstore import MemoryObjectStore
from asavexa.security.sessions import SessionPolicy
from asavexa.security.store import SqliteDocStore
import test_passport as T
from test_security_platform import FakeIdp, ISS, CID, REDIR, Clock
from asavexa.security.oidc import OidcConfig
import urllib.parse

PW = "correct horse battery staple"


class Ctx(unittest.TestCase):
    def build(self, keys=True, oidc=False):
        self.w = T.World()
        self.clock = Clock(datetime.now(timezone.utc))
        self.store = SqliteDocStore(self.w.conn)
        self.kr = crypto.LocalKeyring({"k1": crypto.LocalKeyring.generate_key()}, "k1") if keys else None
        self.commits = 0
        def commit(): self.commits += 1
        self.idp = FakeIdp(); self.idp.next_token = lambda: self.idp.token()
        self.ctx = SecurityContext(self.w.identity, T.SqliteAuditRepository(self.w.conn), self.store, keys=self.kr, objects=MemoryObjectStore("EU") if keys else None,
                                   oidc_cfg=OidcConfig(ISS, CID, "s", REDIR) if oidc else None, now=self.clock, commit=commit,
                                   policy=SessionPolicy(idle_minutes=30, max_sessions=5), oidc_http={"http_get": self.idp.get, "http_post": self.idp.post})
        return self.ctx

    def code_for(self, secret):
        return totp.totp_at(secret, self.clock().timestamp())


class SignInTests(Ctx):
    def setUp(self):
        self.build()

    def test_plain_login_without_mfa_is_unchanged(self):
        r = self.ctx.login("dara@meridian.test", PW, "1.1.1.1", "Chrome")
        self.assertFalse(r["mfa_required"]); self.assertEqual(r["user"].email, "dara@meridian.test")
        s = self.w.identity.validate_session(r["token"])
        self.assertEqual(self.ctx.guard.meta(s)["auth_method"], "PASSWORD"); self.assertEqual(self.ctx.guard.meta(s)["ip"], "1.1.1.1")

    def enrol(self, who="dara@meridian.test"):
        r = self.ctx.login(who, PW, None, None); uid = r["user"].id
        s = self.w.identity.validate_session(r["token"])
        b = self.ctx.mfa_begin(uid)
        self.clock.advance(seconds=1)
        self.ctx.mfa_confirm(uid, self.code_for(b["secret"]), s)
        return uid, b["secret"]

    def test_with_mfa_a_password_alone_gives_no_session(self):
        uid, secret = self.enrol()
        self.assertTrue(self.w.identity.users.get(uid).mfa_enabled)
        r = self.ctx.login("dara@meridian.test", PW, None, None)
        self.assertTrue(r["mfa_required"]); self.assertNotIn("token", r)
        self.clock.advance(seconds=30)
        ok = self.ctx.login_with_mfa(r["challenge"], self.code_for(secret), "2.2.2.2", "Safari")
        self.assertTrue(ok["mfa_verified"])
        s = self.w.identity.validate_session(ok["token"])
        self.assertIsNotNone(self.ctx.guard.meta(s)["mfa_verified_at"]); self.assertEqual(self.ctx.guard.meta(s)["auth_method"], "PASSWORD+MFA")

    def test_wrong_code_is_audited_and_committed_and_locks_after_five(self):
        uid, secret = self.enrol()
        before = self.commits
        for _ in range(5):
            ch = self.ctx.login("dara@meridian.test", PW, None, None)["challenge"]
            with self.assertRaises(MfaError):
                self.ctx.login_with_mfa(ch, "000000", None, None)
        self.assertGreaterEqual(self.commits - before, 5)          # each failure was persisted before raising
        actions = [e.action for e in T.SqliteAuditRepository(self.w.conn).list_for_actor(uid)]
        self.assertEqual(actions.count("MFA_FAILED"), 5); self.assertIn("MFA_LOCKED", actions)
        ch = self.ctx.login("dara@meridian.test", PW, None, None)["challenge"]
        self.clock.advance(seconds=30)
        with self.assertRaises(MfaLockedError):
            self.ctx.login_with_mfa(ch, self.code_for(secret), None, None)

    def test_a_challenge_cannot_be_used_for_another_account(self):
        uid, secret = self.enrol()
        ch = self.ctx.login("dara@meridian.test", PW, None, None)["challenge"]
        with self.assertRaises(MfaError):
            self.ctx.login_with_mfa(ch, "123456", None, None)
        with self.assertRaises(MfaError):
            self.ctx.login_with_mfa("junk", self.code_for(secret), None, None)

    def test_wrong_password_is_persisted_and_account_locks_after_ten(self):
        c0 = self.commits
        for _ in range(10):
            with self.assertRaises(InvalidCredentialsError):
                self.ctx.login("dara@meridian.test", "wrong password here", None, None)
        self.assertEqual(self.commits - c0, 10)
        with self.assertRaises(AccountLockedError):
            self.ctx.login("dara@meridian.test", PW, None, None)            # even the right password is refused during the lock

    def test_lockout_does_not_reveal_whether_an_email_exists(self):
        for _ in range(10):
            with self.assertRaises(InvalidCredentialsError):
                self.ctx.login("ghost@nowhere.test", "whatever password", None, None)
        with self.assertRaises(AccountLockedError):
            self.ctx.login("ghost@nowhere.test", "whatever password", None, None)

    def test_lock_expires(self):
        # events are stamped with the real clock by the identity service, so age them in the table
        for _ in range(10):
            with self.assertRaises(InvalidCredentialsError):
                self.ctx.login("dara@meridian.test", "wrong password here", None, None)
        self.w.conn.execute("UPDATE audit_events SET timestamp=? WHERE action='LOGIN_FAILED'", ((datetime.now(timezone.utc) - timedelta(minutes=16)).isoformat(),)); self.w.conn.commit()
        self.assertFalse(self.ctx.login("dara@meridian.test", PW, None, None)["mfa_required"])

    def test_organisation_can_require_mfa(self):
        org = self.w.org.id
        r = self.ctx.login("dara@meridian.test", PW, None, None); s = self.w.identity.validate_session(r["token"])
        self.ctx.gate_org(s, org)                                           # not required yet
        self.ctx.settings.update(org, "dara", require_mfa=True)
        with self.assertRaises(MfaRequiredError) as e:
            self.ctx.gate_org(s, org)
        self.assertIn("Set up multi-factor", str(e.exception))
        uid, secret = self.enrol()
        self.ctx.guard.revoke_all(uid)
        self.clock.advance(seconds=30)
        r = self.ctx.login("dara@meridian.test", PW, None, None)
        ok = self.ctx.login_with_mfa(r["challenge"], self.code_for(secret), None, None)
        self.ctx.gate_org(self.w.identity.validate_session(ok["token"]), org)      # passed MFA this session
        self.ctx.settings.update(self.w.other_org.id, "x", require_mfa=False)

    def test_mfa_cannot_be_turned_off_while_an_organisation_requires_it(self):
        uid, secret = self.enrol(); self.ctx.settings.update(self.w.org.id, "d", require_mfa=True)
        self.clock.advance(seconds=30)
        with self.assertRaises(MfaRequiredError):
            self.ctx.mfa_disable(uid, self.code_for(secret), org_ids=[self.w.org.id])
        self.ctx.settings.update(self.w.org.id, "d", require_mfa=False)
        self.clock.advance(seconds=30)
        self.ctx.mfa_disable(uid, self.code_for(secret), org_ids=[self.w.org.id])
        self.assertFalse(self.w.identity.users.get(uid).mfa_enabled)
        self.assertIn("MFA_DISABLED", [e.action for e in T.SqliteAuditRepository(self.w.conn).list_for_actor(uid)])

    def test_idle_session_is_refused(self):
        r = self.ctx.login("dara@meridian.test", PW, None, None); s = self.w.identity.validate_session(r["token"])
        self.ctx.check_session(s); self.clock.advance(minutes=31)
        with self.assertRaises(SessionPolicyError):
            self.ctx.check_session(s)


class WithoutKeysTests(Ctx):
    def setUp(self):
        self.build(keys=False)

    def test_everything_old_still_works_and_new_features_say_why_not(self):
        r = self.ctx.login("dara@meridian.test", PW, None, None)
        self.assertFalse(r["mfa_required"])
        for fn in (lambda: self.ctx.mfa_begin(r["user"].id), self.ctx.require_blobs, self.ctx.oidc):
            with self.assertRaises((KeysNotConfiguredError, OidcError)):
                fn()
        v = self.ctx.verify_audit(self.w.org.id)
        self.assertFalse(v["enabled"]); self.assertIsNone(v["ok"])
        self.assertFalse(self.ctx.overview(self.w.org.id, [])["encryption"]["configured"])
        self.assertEqual(self.ctx.health()["status"], "DEGRADED")


class OidcFlowTests(Ctx):
    def setUp(self):
        self.build(oidc=True); self.binding = "binding-0123456789abcdef"

    def begin(self):
        u = self.ctx.oidc().start(self.binding)["url"]
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(u).query)); self.idp.last_nonce = q["nonce"]; return q

    def test_sso_login_opens_a_session_and_is_audited(self):
        q = self.begin()
        r = self.ctx.oidc_login("code", q["state"], self.binding, "3.3.3.3", "Edge")
        self.assertEqual(r["user"].email, "dara@meridian.test")
        s = self.w.identity.validate_session(r["token"]); self.assertEqual(self.ctx.guard.meta(s)["auth_method"], "OIDC")
        self.assertIn("LOGIN_OIDC", [e.action for e in T.SqliteAuditRepository(self.w.conn).list_for_actor(r["user"].id)])

    def test_sso_does_not_bypass_local_mfa_unless_the_provider_did_mfa(self):
        r0 = self.ctx.login("dara@meridian.test", PW, None, None); uid = r0["user"].id
        b = self.ctx.mfa_begin(uid); self.clock.advance(seconds=1)
        self.ctx.mfa_confirm(uid, self.code_for(b["secret"]), self.w.identity.validate_session(r0["token"]))
        q = self.begin()
        self.assertTrue(self.ctx.oidc_login("c", q["state"], self.binding, None, None)["mfa_required"])
        self.idp.claims_override = {"amr": ["pwd", "mfa"]}
        q = self.begin()
        r = self.ctx.oidc_login("c", q["state"], self.binding, None, None)
        self.assertTrue(r["mfa_verified"])

    def test_failed_sso_is_committed(self):
        q = self.begin(); c0 = self.commits
        with self.assertRaises(OidcError):
            self.ctx.oidc_login("c", q["state"], "different-binding-0123456", None, None)
        self.assertEqual(self.commits, c0 + 1)

    def test_not_configured(self):
        self.build(oidc=False)
        with self.assertRaises(OidcError):
            self.ctx.oidc()


class AuditChainThroughContextTests(Ctx):
    def test_alerts_and_chain_report_through_the_context(self):
        from asavexa.security.auditchain import ChainedAuditRepository
        self.build()
        chained = ChainedAuditRepository(T.SqliteAuditRepository(self.w.conn), self.store, self.kr)
        self.ctx.audit = chained
        chained.record(__import__("asavexa.audit.models", fromlist=["AuditEvent"]).AuditEvent(
            id="00000000-0000-4000-8000-000000000001", entity_type="X", entity_id="00000000-0000-4000-9000-000000000001", action="MFA_DISABLED", actor="u",
            timestamp=self.clock(), org_id=self.w.org.id))
        self.assertTrue(self.ctx.verify_audit(self.w.org.id)["ok"])
        self.ctx.refresh_alerts(self.w.org.id, [], [])
        self.assertEqual([a["rule"] for a in self.ctx.alerts.list(self.w.org.id)], ["MFA_DISABLED"])
        self.w.conn.execute("UPDATE audit_events SET action='SOMETHING_ELSE' WHERE id='00000000-0000-4000-8000-000000000001'"); self.w.conn.commit()
        bad = self.ctx.verify_audit(self.w.org.id)
        self.assertFalse(bad["ok"])
        self.assertIn("AUDIT_CHAIN_FAILED", [e.action for e in T.SqliteAuditRepository(self.w.conn).list_for_org(self.w.org.id)])


if __name__ == "__main__":
    unittest.main()


class BackupStatusTests(Ctx):
    def test_unknown_then_fresh_then_stale(self):
        import json
        self.build()
        self.assertFalse(self.ctx.backup_status()["known"])
        self.ctx.objects.put("system/backups/latest.json", json.dumps({"name": "asavexa-x.dump.enc", "created_at": self.clock().isoformat(), "key_id": "k1"}).encode())
        self.assertTrue(self.ctx.backup_status()["ok"])
        self.clock.advance(hours=30)
        s = self.ctx.backup_status(); self.assertFalse(s["ok"]); self.assertIn("older", s["detail"])
        self.assertIn("backups", self.ctx.overview(self.w.org.id, []))
        self.build(keys=False); self.assertFalse(self.ctx.backup_status()["known"])
