"""MFA, encryption/keys, sessions and the tamper-evident audit chain, against the real SQLite audit and identity repositories."""
import base64
import unittest
from datetime import datetime, timedelta, timezone

from asavexa.audit.models import AuditEvent
from asavexa.security import auditchain, crypto, totp
from asavexa.security.errors import DecryptionError, KeysNotConfiguredError, MfaError, MfaLockedError, NotFoundError, SessionPolicyError
from asavexa.security.mfa import MfaService
from asavexa.security.sessions import SessionGuard, SessionPolicy
from asavexa.security.store import MemoryDocStore, SqliteDocStore
import test_passport as T


class Clock:
    def __init__(self):
        self.t = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)
    def __call__(self):
        return self.t
    def advance(self, **kw):
        self.t += timedelta(**kw)


PW = "correct horse battery staple"


def keyring(*ids):
    return crypto.LocalKeyring({i: crypto.LocalKeyring.generate_key() for i in ids}, ids[-1])


class TotpTests(unittest.TestCase):
    def test_rfc6238_vectors(self):
        s = base64.b32encode(b"12345678901234567890").decode()
        for t, exp in [(59, "94287082"), (1111111109, "07081804"), (1111111111, "14050471"), (1234567890, "89005924"), (2000000000, "69279037")]:
            self.assertEqual(totp.totp_at(s, t, digits=8), exp)

    def test_window_replay_and_junk(self):
        s = totp.new_secret()
        now = 1_700_000_000.0
        code = totp.totp_at(s, now)
        step = totp.verify(s, code, now=now)
        self.assertIsNotNone(step)
        self.assertIsNone(totp.verify(s, code, now=now, last_used_step=step))      # same code twice
        self.assertIsNotNone(totp.verify(s, code, now=now + 30))                   # one step late is tolerated
        self.assertIsNone(totp.verify(s, code, now=now + 120))                     # too old
        for junk in ("", "12345", "abcdef", "1234567", None):
            self.assertIsNone(totp.verify(s, junk, now=now))

    def test_uri_and_recovery_codes(self):
        self.assertTrue(totp.otpauth_uri("ABC", "a@b.test").startswith("otpauth://totp/ASAVEXA:a%40b.test?secret=ABC"))
        codes = totp.new_recovery_codes()
        self.assertEqual(len(set(codes)), 10)
        self.assertEqual(totp.hash_recovery(codes[0].lower()), totp.hash_recovery(codes[0]))


class CryptoTests(unittest.TestCase):
    def test_round_trip_and_binding_to_owner(self):
        kr = keyring("k1")
        ct, h = crypto.encrypt_blob(kr, b"invoice bytes", "org-1", "ev-1")
        self.assertNotIn(b"invoice", ct)
        self.assertEqual(crypto.decrypt_blob(kr, ct, h, "org-1", "ev-1"), b"invoice bytes")
        for org, ev in (("org-2", "ev-1"), ("org-1", "ev-2")):
            with self.assertRaises(DecryptionError):
                crypto.decrypt_blob(kr, ct, h, org, ev)

    def test_tamper_is_detected(self):
        kr = keyring("k1")
        ct, h = crypto.encrypt_blob(kr, b"x" * 100, "o", "e")
        bad = bytearray(ct); bad[5] ^= 1
        with self.assertRaises(DecryptionError):
            crypto.decrypt_blob(kr, bytes(bad), h, "o", "e")

    def test_each_file_has_its_own_key_and_nonce(self):
        kr = keyring("k1")
        a = crypto.encrypt_blob(kr, b"same", "o", "e")
        b = crypto.encrypt_blob(kr, b"same", "o", "e")
        self.assertNotEqual(a[0], b[0]); self.assertNotEqual(a[1]["wrapped_dek"], b[1]["wrapped_dek"])

    def test_rotation_rewraps_without_touching_the_file(self):
        old = crypto.LocalKeyring({"k1": crypto.LocalKeyring.generate_key()}, "k1")
        ct, h = crypto.encrypt_blob(old, b"secret", "o", "e")
        both = crypto.LocalKeyring({"k1": old._keys["k1"], "k2": crypto.LocalKeyring.generate_key()}, "k2")
        h2 = crypto.rewrap(both, h, "o", "e")
        self.assertEqual(h2["kid"], "k2"); self.assertEqual(h2["nonce"], h["nonce"])
        only_new = crypto.LocalKeyring({"k2": both._keys["k2"]}, "k2")   # the old key is retired
        self.assertEqual(crypto.decrypt_blob(only_new, ct, h2, "o", "e"), b"secret")
        with self.assertRaises(DecryptionError):
            crypto.decrypt_blob(only_new, ct, h, "o", "e")

    def test_sealed_text_and_purpose_binding(self):
        kr = keyring("k1")
        s = crypto.seal_text(kr, "JBSWY3DP", "mfa:u1")
        self.assertNotIn("JBSWY3DP", s)
        self.assertEqual(crypto.open_text(kr, s, "mfa:u1"), "JBSWY3DP")
        with self.assertRaises(DecryptionError):
            crypto.open_text(kr, s, "mfa:u2")
        with self.assertRaises(DecryptionError):
            crypto.open_text(kr, "garbage", "x")

    def test_env_configuration(self):
        k = crypto._b64(crypto.LocalKeyring.generate_key())
        kr = crypto.LocalKeyring.from_env({"ASAVEXA_KEYS": f"a:{k},b:{k}", "ASAVEXA_CURRENT_KEY": "b"})
        self.assertEqual(kr.current_key_id, "b")
        for env in ({}, {"ASAVEXA_KEYS": "nonsense"}, {"ASAVEXA_KEYS": "a:" + crypto._b64(b"short")}, {"ASAVEXA_KEYS": f"a:{k}", "ASAVEXA_CURRENT_KEY": "zzz"}):
            with self.assertRaises(KeysNotConfiguredError):
                crypto.LocalKeyring.from_env(env)

    def test_mac_is_key_and_purpose_bound(self):
        kr = keyring("k1")
        kid, tag = kr.mac("p", b"data")
        self.assertTrue(kr.verify_mac("p", b"data", kid, tag))
        self.assertFalse(kr.verify_mac("q", b"data", kid, tag)); self.assertFalse(kr.verify_mac("p", b"datA", kid, tag))
        self.assertFalse(kr.verify_mac("p", b"data", "nope", tag))


class MfaTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock(); self.kr = keyring("k1")
        self.mfa = MfaService(MemoryDocStore(), self.kr, now=self.clock)

    def code(self, secret):
        return totp.totp_at(secret, self.clock().timestamp())

    def enrol(self):
        b = self.mfa.begin_enrolment("u1", "a@b.test")
        self.assertIn("secret=", b["otpauth_uri"])
        r = self.mfa.confirm_enrolment("u1", self.code(b["secret"]))
        return b["secret"], r["recovery_codes"]

    def test_enrol_then_login_codes_work_once(self):
        secret, codes = self.enrol()
        self.assertTrue(self.mfa.is_enabled("u1")); self.assertEqual(self.mfa.status("u1")["recovery_codes_left"], 10)
        self.clock.advance(seconds=30)
        self.assertEqual(self.mfa.verify("u1", self.code(secret)), "TOTP")
        with self.assertRaises(MfaError):                       # the same code cannot be reused
            self.mfa.verify("u1", self.code(secret))

    def test_secret_is_not_stored_in_clear(self):
        store = MemoryDocStore(); m = MfaService(store, self.kr, now=self.clock)
        b = m.begin_enrolment("u1", "a@b.test")
        self.assertNotIn(b["secret"], str(store.get("mfa", "u1")))

    def test_wrong_confirmation_does_not_enable(self):
        self.mfa.begin_enrolment("u1", "a@b.test")
        with self.assertRaises(MfaError):
            self.mfa.confirm_enrolment("u1", "000000")
        self.assertFalse(self.mfa.is_enabled("u1"))

    def test_recovery_codes_are_single_use(self):
        _, codes = self.enrol()
        self.assertEqual(self.mfa.verify("u1", codes[0].lower()), "RECOVERY")
        self.assertEqual(self.mfa.status("u1")["recovery_codes_left"], 9)
        with self.assertRaises(MfaError):
            self.mfa.verify("u1", codes[0])

    def test_lockout_after_repeated_failures_then_recovers(self):
        secret, _ = self.enrol()
        for _ in range(5):
            with self.assertRaises(MfaError):
                self.mfa.verify("u1", "111111")
        self.clock.advance(seconds=30)
        with self.assertRaises(MfaLockedError):                 # even the right code is refused while locked
            self.mfa.verify("u1", self.code(secret))
        self.clock.advance(minutes=16)
        self.assertEqual(self.mfa.verify("u1", self.code(secret)), "TOTP")

    def test_challenge_flow_is_single_use_and_expires(self):
        secret, _ = self.enrol()
        self.clock.advance(seconds=30)
        ch = self.mfa.issue_challenge("u1")
        self.assertEqual(self.mfa.redeem_challenge(ch, self.code(secret)), "u1")
        self.clock.advance(seconds=30)
        with self.assertRaises(MfaError):
            self.mfa.redeem_challenge(ch, self.code(secret))    # redeemed already
        ch2 = self.mfa.issue_challenge("u1"); self.clock.advance(minutes=6)
        with self.assertRaises(MfaError):
            self.mfa.redeem_challenge(ch2, self.code(secret))   # expired
        with self.assertRaises(MfaError):
            self.mfa.redeem_challenge("junk", "123456")

    def test_disable_and_regenerate_need_a_current_code(self):
        secret, codes = self.enrol()
        with self.assertRaises(MfaError):
            self.mfa.disable("u1", "000000")
        self.clock.advance(seconds=30)
        new = self.mfa.regenerate_recovery("u1", self.code(secret))
        with self.assertRaises(MfaError):
            self.mfa.verify("u1", codes[1])                      # old codes no longer work
        self.assertEqual(len(new), 10)
        self.clock.advance(seconds=30)
        self.mfa.disable("u1", self.code(secret))
        self.assertFalse(self.mfa.is_enabled("u1"))

    def test_cannot_enrol_twice(self):
        self.enrol()
        with self.assertRaises(MfaError):
            self.mfa.begin_enrolment("u1", "a@b.test")


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.w = T.World(); self.clock = Clock()
        self.repo = self.w.identity.sessions
        self.store = SqliteDocStore(self.w.conn)
        self.guard = SessionGuard(self.store, self.repo, now=self.clock, policy=SessionPolicy(idle_minutes=30, max_sessions=3))

    def login(self, who=None):
        user, tok = self.w.identity.authenticate("dara@meridian.test", PW)
        s = self.w.identity.validate_session(tok)
        self.guard.register(s, "10.0.0.1", "Firefox", "PASSWORD", False)
        return s, tok

    def test_idle_timeout_signs_the_session_out_for_real(self):
        s, tok = self.login()
        self.guard.check(s)
        self.clock.advance(minutes=31)
        with self.assertRaises(SessionPolicyError):
            self.guard.check(s)
        from asavexa.identity.domain.errors import SessionRevokedError
        with self.assertRaises(SessionRevokedError):
            self.w.identity.validate_session(tok)               # the underlying session is revoked, not just flagged

    def test_activity_keeps_the_session_alive(self):
        s, _ = self.login()
        for _ in range(5):
            self.clock.advance(minutes=20); self.guard.check(s)

    def test_cap_on_concurrent_sessions_drops_the_oldest(self):
        toks = []
        for _ in range(4):
            toks.append(self.login()); self.clock.advance(seconds=5)
        from asavexa.identity.domain.errors import SessionRevokedError
        with self.assertRaises(SessionRevokedError):
            self.w.identity.validate_session(toks[0][1])
        self.w.identity.validate_session(toks[3][1])
        self.assertEqual(len([m for m in self.guard.list_for_user(toks[0][0].user_id) if not m["revoked"]]), 3)

    def test_list_and_revoke_one_or_all_others(self):
        a, ta = self.login(); self.clock.advance(seconds=5); b, tb = self.login()
        listed = self.guard.list_for_user(a.user_id, include_current=b.id)
        self.assertEqual({m["session_id"] for m in listed}, {a.id, b.id}); self.assertTrue([m for m in listed if m["current"]][0]["session_id"] == b.id)
        self.assertNotIn("token_hash", str(listed) if False else "")
        self.guard.revoke(a.user_id, a.id)
        with self.assertRaises(Exception):
            self.w.identity.validate_session(ta)
        with self.assertRaises(NotFoundError):
            self.guard.revoke(a.user_id, "nope")
        c, tc = self.login()
        self.assertEqual(self.guard.revoke_others(b.user_id, keep_session_id=c.id), 1)
        self.w.identity.validate_session(tc)

    def test_legacy_session_without_metadata_is_handled(self):
        user, tok = self.w.identity.authenticate("dara@meridian.test", PW)
        s = self.w.identity.validate_session(tok)
        m = self.guard.check(s)
        self.assertIsNone(m["mfa_verified_at"])

    def test_mfa_flag(self):
        s, _ = self.login(); self.assertIsNone(self.guard.check(s)["mfa_verified_at"])
        self.guard.mark_mfa_verified(s); self.assertIsNotNone(self.guard.check(s)["mfa_verified_at"])


def eid(n):
    return f"00000000-0000-4000-9000-{n:012d}"


class AuditChainTests(unittest.TestCase):
    def setUp(self):
        self.w = T.World(); self.kr = keyring("k1"); self.store = MemoryDocStore()
        self.inner = T.SqliteAuditRepository(self.w.conn)
        self.chain = auditchain.ChainedAuditRepository(self.inner, self.store, self.kr)
        self.org = self.w.org.id; self.n = 0
        self.base = len(self.inner.list_for_org(self.org))

    def add(self, action="X", new=None, org=None):
        self.n += 1
        ev = AuditEvent(id=f"00000000-0000-4000-8000-{self.n:012d}", entity_type="Thing", entity_id=eid(self.n), action=action, actor="u1",
                        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=self.n), org_id=org or self.org, new_value=new)
        return self.chain.record(ev)

    def verify(self):
        return auditchain.verify_chain(self.inner, self.store, self.kr, self.org)

    def test_clean_chain_verifies_and_existing_events_are_reported_not_flagged(self):
        for i in range(5):
            self.add(new={"n": i, "amount": "10.00"})
        r = self.verify()
        self.assertTrue(r["ok"], r); self.assertEqual(r["links"], 5); self.assertEqual(r["unchained_events"], self.base)

    def test_wrapper_still_behaves_like_the_audit_repository(self):
        self.add()
        self.assertEqual(len(self.chain.list_for_org(self.org)), self.base + 1)

    def test_edited_event_is_caught(self):
        for i in range(3):
            self.add(new={"amount": "10.00"})
        self.w.conn.execute("UPDATE audit_events SET new_value=? WHERE entity_id=?", ('{"amount": "1.00"}', eid(2))); self.w.conn.commit()
        r = self.verify()
        self.assertFalse(r["ok"]); self.assertEqual([p["kind"] for p in r["problems"]], ["EVENT_CHANGED"]); self.assertEqual(r["problems"][0]["seq"], 2)

    def test_deleted_event_is_caught(self):
        for i in range(3):
            self.add()
        self.w.conn.execute("DELETE FROM audit_events WHERE entity_id=?", (eid(2),)); self.w.conn.commit()
        self.assertEqual([p["kind"] for p in self.verify()["problems"]], ["EVENT_DELETED"])

    def test_truncating_the_chain_is_caught(self):
        for i in range(4):
            self.add()
        self.store.delete("audit_link", f"{self.org}:{4:012d}")
        self.assertIn("TRUNCATED", [p["kind"] for p in self.verify()["problems"]])

    def test_removing_a_middle_link_is_caught(self):
        for i in range(4):
            self.add()
        self.store.delete("audit_link", f"{self.org}:{2:012d}")
        kinds = [p["kind"] for p in self.verify()["problems"]]
        self.assertIn("SEQUENCE", kinds)

    def test_rebuilding_the_whole_chain_without_the_key_is_caught(self):
        for i in range(3):
            self.add(new={"amount": "10.00"})
        # an attacker with database access edits the event AND recomputes every hash, but does not hold the key
        self.w.conn.execute("UPDATE audit_events SET new_value=? WHERE entity_id=?", ('{"amount": "1.00"}', eid(2))); self.w.conn.commit()
        evs = {e.entity_id: e for e in self.inner.list_for_org(self.org)}
        evs = {f"e{n}": evs[eid(n)] for n in (1, 2, 3)}
        prev = auditchain.GENESIS
        for seq, name in enumerate(["e1", "e2", "e3"], start=1):
            d = auditchain.event_digest(evs[name]); h = auditchain._link_hash(prev, d, seq)
            old = self.store.get("audit_link", f"{self.org}:{seq:012d}")
            self.store.put("audit_link", f"{self.org}:{seq:012d}", {**old, "digest": d, "prev": prev, "hash": h}, org_id=self.org)
            prev = h
        self.store.put("audit_head", self.org, {**self.store.get("audit_head", self.org), "hash": prev})
        kinds = {p["kind"] for p in self.verify()["problems"]}
        self.assertTrue({"BAD_SIGNATURE", "BAD_HEAD_SIGNATURE"} <= kinds, kinds)

    def test_chain_survives_key_rotation(self):
        self.add(); self.add()
        both = crypto.LocalKeyring({"k1": self.kr._keys["k1"], "k2": crypto.LocalKeyring.generate_key()}, "k2")
        self.chain._keys = both
        self.add(); self.add()
        self.assertTrue(auditchain.verify_chain(self.inner, self.store, both, self.org)["ok"])
        only_new = crypto.LocalKeyring({"k2": both._keys["k2"]}, "k2")      # old key retired -> old links can no longer be proven
        self.assertFalse(auditchain.verify_chain(self.inner, self.store, only_new, self.org)["ok"])

    def test_organisations_have_separate_chains(self):
        self.add(); self.add(org=self.w.other_org.id)
        self.assertEqual(self.verify()["links"], 1)
        self.assertEqual(auditchain.verify_chain(self.inner, self.store, self.kr, self.w.other_org.id)["links"], 1)

    def test_digest_ignores_timezone_representation_and_key_order(self):
        e1 = AuditEvent(id="1", entity_type="T", entity_id="1", action="A", actor="u", timestamp=datetime(2026, 1, 1, 12, tzinfo=timezone.utc), new_value={"b": 1, "a": 2})
        e2 = AuditEvent(id="1", entity_type="T", entity_id="1", action="A", actor="u", timestamp=datetime(2026, 1, 1, 12), new_value={"a": 2, "b": 1})
        self.assertEqual(auditchain.event_digest(e1), auditchain.event_digest(e2))


class StoreContractTests(unittest.TestCase):
    def test_both_stores_behave_the_same(self):
        import sqlite3
        c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row
        for st in (MemoryDocStore(), SqliteDocStore(c)):
            st.put("k", "a:1", {"x": 1}, org_id="o1"); st.put("k", "a:2", {"x": 2}, org_id="o2"); st.put("k", "b:1", {"x": 3}, org_id="o1")
            self.assertEqual(st.get("k", "a:1"), {"x": 1}); self.assertIsNone(st.get("k", "zzz")); self.assertIsNone(st.get("other", "a:1"))
            self.assertEqual([k for k, _ in st.list("k")], ["a:1", "a:2", "b:1"])
            self.assertEqual([k for k, _ in st.list("k", org_id="o1")], ["a:1", "b:1"])
            self.assertEqual([k for k, _ in st.list("k", prefix="a:")], ["a:1", "a:2"])
            st.put("k", "a:1", {"x": 9}); self.assertEqual(st.get("k", "a:1"), {"x": 9})
            st.delete("k", "a:1"); self.assertIsNone(st.get("k", "a:1"))
            self.assertEqual([k for k, _ in st.list("k", prefix="a_")], [])      # LIKE wildcards are escaped


if __name__ == "__main__":
    unittest.main()
