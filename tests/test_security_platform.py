"""Object storage (against a local fake S3 that checks SigV4), encrypted evidence, retention and holds, privacy, alerts,
residency, vendor risk, monitoring, and OIDC (against an in-process fake identity provider with a real RSA key)."""
import hashlib
import json
import threading
import time
import unittest
import urllib.parse
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from asavexa.audit.models import AuditEvent
from asavexa.evidence.domain.enums import EvidenceType
from asavexa.security import alerts, crypto, objectstore, privacy
from asavexa.security.blobs import BlobService
from asavexa.security.errors import (DecryptionError, LegalHoldError, NotFoundError, OidcError, ResidencyError, RetentionError, StorageError, ValidationError)
from asavexa.security.governance import ResidencyService, SettingsService, VendorRegister
from asavexa.security.mfa import MfaService
from asavexa.security.monitoring import HealthChecker, Metrics, RateLimiter
from asavexa.security.oidc import OidcConfig, OidcService
from asavexa.security.retention import RetentionService
from asavexa.security.sessions import SessionGuard
from asavexa.security.store import MemoryDocStore, SqliteDocStore
import test_passport as T

PW = "correct horse battery staple"


class Clock:
    def __init__(self, t=None):
        self.t = t or datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    def __call__(self): return self.t
    def advance(self, **kw): self.t += timedelta(**kw)


def kr(*ids):
    ids = ids or ("k1",)
    return crypto.LocalKeyring({i: crypto.LocalKeyring.generate_key() for i in ids}, ids[-1])


# ------------------------------------------------------------------------------------------------- object stores
class FakeS3(BaseHTTPRequestHandler):
    objects = {}
    secret = "SECRET"
    access = "AK"
    region = "eu-west-1"
    bucket = "bkt"

    def log_message(self, *a): pass

    def _auth(self, body):
        h = {"host": self.headers["Host"], "x-amz-date": self.headers["x-amz-date"], "x-amz-content-sha256": self.headers["x-amz-content-sha256"]}
        if hashlib.sha256(body).hexdigest() != h["x-amz-content-sha256"]:
            return False
        expect = objectstore.sign_v4(self.command, "http://" + h["host"] + self.path, h, h["x-amz-content-sha256"], self.access, self.secret, self.region, "s3", h["x-amz-date"])
        return self.headers.get("Authorization") == expect

    def _handle(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        if not self._auth(body):
            self.send_response(403); self.send_header("Content-Length", "0"); self.end_headers(); return
        key = urllib.parse.unquote(self.path)
        out, code = b"", 200
        if self.command == "PUT": self.objects[key] = body
        elif self.command == "GET":
            if key in self.objects: out = self.objects[key]
            else: code = 404
        elif self.command == "HEAD": code = 200 if key in self.objects else 404
        elif self.command == "DELETE": self.objects.pop(key, None); code = 204
        self.send_response(code); self.send_header("Content-Length", str(len(out) if self.command != "HEAD" else 0)); self.end_headers()
        if self.command != "HEAD": self.wfile.write(out)

    do_PUT = do_GET = do_HEAD = do_DELETE = _handle


class ObjectStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        FakeS3.objects = {}
        cls.srv = HTTPServer(("127.0.0.1", 0), FakeS3)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def s3(self, secret="SECRET"):
        return objectstore.S3ObjectStore(f"http://127.0.0.1:{self.port}", "bkt", "eu-west-1", "AK", secret)

    def contract(self, s):
        s.put("org/a/evidence/e1", b"\x00\x01cipher")
        self.assertTrue(s.exists("org/a/evidence/e1")); self.assertFalse(s.exists("org/a/evidence/nope"))
        self.assertEqual(s.get("org/a/evidence/e1"), b"\x00\x01cipher")
        s.put("org/a/evidence/e1", b"v2"); self.assertEqual(s.get("org/a/evidence/e1"), b"v2")
        s.delete("org/a/evidence/e1"); s.delete("org/a/evidence/e1")
        with self.assertRaises(NotFoundError):
            s.get("org/a/evidence/e1")

    def test_all_backends_share_one_contract(self):
        import tempfile
        self.contract(objectstore.MemoryObjectStore())
        self.contract(objectstore.DatabaseObjectStore(MemoryDocStore()))
        with tempfile.TemporaryDirectory() as d:
            self.contract(objectstore.LocalObjectStore(d))
        self.contract(self.s3())

    def test_s3_requests_are_really_signed(self):
        bad = self.s3(secret="WRONG")
        with self.assertRaises(StorageError):
            bad.put("org/a/x", b"data")
        with self.assertRaises(StorageError):
            bad.get("org/a/x")

    def test_sigv4_matches_the_published_aws_test_vector(self):
        a = objectstore.sign_v4("GET", "https://example.amazonaws.com/", {"host": "example.amazonaws.com", "x-amz-date": "20150830T123600Z"},
                                hashlib.sha256(b"").hexdigest(), "AKIDEXAMPLE", "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY", "us-east-1", "service", "20150830T123600Z")
        self.assertIn("Signature=5fa00fa31553b73ebf1942676e86291e8372ff2a2260956d9b8aae1d763fbf31", a)

    def test_unreachable_storage_is_a_clear_error(self):
        s = objectstore.S3ObjectStore("http://127.0.0.1:1", "b", "r", "a", "s", timeout=2)
        with self.assertRaises(StorageError):
            s.put("k", b"x")

    def test_keys_cannot_escape(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            ls = objectstore.LocalObjectStore(d)
            for bad in ("../x", "a/../../x", "/abs", "a b", "", "a\x00b"):
                with self.assertRaises(StorageError):
                    ls.put(bad, b"x")

    def test_configuration_must_be_complete(self):
        with self.assertRaises(StorageError):
            objectstore.S3ObjectStore.from_env({"ASAVEXA_S3_ENDPOINT": "https://x"})


# ------------------------------------------------------------------------------------------------- encrypted evidence
class BlobTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock(); self.store = MemoryDocStore(); self.objects = objectstore.MemoryObjectStore(region="EU")
        self.keys = kr("k1")
        self.settings = SettingsService(self.store, self.clock)
        self.blobs = BlobService(self.store, self.objects, self.keys, residency=ResidencyService(self.settings), now=self.clock)

    def test_only_ciphertext_reaches_storage_and_round_trips(self):
        m = self.blobs.put("o1", "e1", b"Invoice 42 for NGN 53,750.00")
        raw = self.objects.objects[BlobService.object_key("o1", "e1")]
        self.assertNotIn(b"Invoice", raw)
        self.assertEqual(self.blobs.get("o1", "e1"), b"Invoice 42 for NGN 53,750.00")
        self.assertEqual(m["key_id"], "k1"); self.assertEqual(m["region"], "EU")
        self.assertNotIn("wrapped_dek", json.dumps(m))

    def test_other_organisations_cannot_read_it(self):
        self.blobs.put("o1", "e1", b"secret")
        with self.assertRaises(NotFoundError):
            self.blobs.get("o2", "e1")
        self.assertIsNone(self.blobs.info("o2", "e1"))

    def test_tampered_or_swapped_storage_is_detected(self):
        self.blobs.put("o1", "e1", b"AAAA"); self.blobs.put("o1", "e2", b"BBBB")
        k1, k2 = BlobService.object_key("o1", "e1"), BlobService.object_key("o1", "e2")
        self.objects.objects[k1] = self.objects.objects[k2]          # an attacker swaps one file for another
        with self.assertRaises(DecryptionError):
            self.blobs.get("o1", "e1")
        self.assertFalse(self.blobs.verify("o1", "e1")["ok"]); self.assertTrue(self.blobs.verify("o1", "e2")["ok"])

    def test_rotation_moves_keys_without_touching_files(self):
        self.blobs.put("o1", "e1", b"one"); self.blobs.put("o2", "e2", b"two")
        before = dict(self.objects.objects)
        both = crypto.LocalKeyring({"k1": self.keys._keys["k1"], "k2": crypto.LocalKeyring.generate_key()}, "k2")
        self.blobs.keys = both
        self.assertEqual(self.blobs.keys_in_use(), {"k1": 2})
        r = self.blobs.rotate(); self.assertEqual((r["rotated"], r["failed"]), (2, 0))
        self.assertEqual(self.blobs.keys_in_use(), {"k2": 2}); self.assertEqual(before, self.objects.objects)
        self.assertEqual(self.blobs.rotate()["rotated"], 0)       # idempotent
        self.blobs.keys = crypto.LocalKeyring({"k2": both._keys["k2"]}, "k2")        # old key retired
        self.assertEqual(self.blobs.get("o1", "e1"), b"one")

    def test_shredding_destroys_the_key_and_the_file(self):
        self.blobs.put("o1", "e1", b"gone soon")
        r = self.blobs.shred("o1", "e1", "retention ended")
        self.assertEqual(r["state"], "SHREDDED")
        self.assertFalse(self.objects.exists(BlobService.object_key("o1", "e1")))
        self.assertNotIn("wrapped_dek", json.dumps(self.store.get("blob", "e1")))
        with self.assertRaises(NotFoundError):
            self.blobs.get("o1", "e1")
        self.blobs.shred("o1", "e1", "again")      # idempotent

    def test_residency_blocks_storage_in_the_wrong_place(self):
        self.settings.update("o1", "u", allowed_regions=["NG"])
        with self.assertRaises(ResidencyError):
            self.blobs.put("o1", "e1", b"x")
        self.assertEqual(self.objects.objects, {})                  # nothing was stored
        self.objects.data_region = "NG"
        self.blobs.put("o1", "e1", b"x")
        self.objects.data_region = "unspecified"
        with self.assertRaises(ResidencyError):
            self.blobs.put("o1", "e2", b"x")                        # cannot prove where it is -> refuse

    def test_unrestricted_org_can_use_any_region(self):
        self.objects.data_region = "unspecified"
        self.blobs.put("o9", "e1", b"x")


# ------------------------------------------------------------------------------------------------- the vault integration
class VaultIntegrationTests(unittest.TestCase):
    def test_vault_stores_encrypted_content_and_serves_it_back(self):
        w = T.World(); store = MemoryDocStore(); objects = objectstore.MemoryObjectStore("EU")
        blobs = BlobService(store, objects, kr("k1"))
        w.vault.blobs = blobs
        rec = w.vault.upload_evidence(w.org.id, EvidenceType.INVOICE, b"%PDF fake invoice", "inv.pdf", "application/pdf", w.accountant.id)
        self.assertEqual(w.vault.read_content(w.org.id, rec.id), b"%PDF fake invoice")
        self.assertNotIn(b"fake invoice", b"".join(objects.objects.values()))
        with self.assertRaises(Exception):
            w.vault.read_content(w.other_org.id, rec.id)
        self.assertEqual(w.vault.content_info(w.org.id, rec.id)["state"], "STORED")

    def test_vault_without_storage_behaves_as_before(self):
        w = T.World()
        rec = w.vault.upload_evidence(w.org.id, EvidenceType.INVOICE, b"x", "a.pdf", "application/pdf", w.accountant.id)
        self.assertIsNone(w.vault.content_info(w.org.id, rec.id))
        with self.assertRaises(Exception):
            w.vault.read_content(w.org.id, rec.id)

    def test_a_storage_failure_does_not_leave_a_half_made_record(self):
        w = T.World(); objects = objectstore.MemoryObjectStore("EU")
        objects.put = lambda *a, **k: (_ for _ in ()).throw(StorageError("down"))
        w.vault.blobs = BlobService(MemoryDocStore(), objects, kr("k1"))
        n = len(w.vault.list_for_org(w.org.id))
        with self.assertRaises(StorageError):
            w.vault.upload_evidence(w.org.id, EvidenceType.INVOICE, b"x", "a.pdf", "application/pdf", w.accountant.id)
        self.assertEqual(len(w.vault.list_for_org(w.org.id)), n)


# ------------------------------------------------------------------------------------------------- retention
class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.w = T.World(); self.clock = Clock(); self.store = MemoryDocStore()
        self.blobs = BlobService(self.store, objectstore.MemoryObjectStore("EU"), kr("k1"), now=self.clock)
        self.w.vault.blobs = self.blobs
        self.ret = RetentionService(self.store, self.blobs, self.clock)
        self.org = self.w.org.id
        self.rec = self.w.vault.upload_evidence(self.org, EvidenceType.INVOICE, b"old invoice", "old.pdf", "application/pdf", self.w.accountant.id)
        self.rec.uploaded_at = self.clock() - timedelta(days=100)       # make it old when needed

    def age(self, days):
        self.rec.uploaded_at = self.clock() - timedelta(days=days)

    def test_policy_floor_and_validation(self):
        self.assertEqual(self.ret.policy(self.org)["days"]["EVIDENCE"], 2555)
        for bad in (30, 2189, 99999, "7", None, True):
            with self.assertRaises(ValidationError):
                self.ret.set_policy(self.org, "u", bad)
        self.assertEqual(self.ret.set_policy(self.org, "u", 3650)["days"]["EVIDENCE"], 3650)

    def test_nothing_is_disposed_early(self):
        with self.assertRaises(RetentionError):
            self.ret.dispose(self.org, self.rec, "u", "tidy up")
        self.assertEqual(self.ret.candidates(self.org, [self.rec]), [])
        self.assertEqual(self.w.vault.read_content(self.org, self.rec.id), b"old invoice")

    def test_due_evidence_can_be_disposed_and_leaves_a_tombstone(self):
        self.age(3000)
        c = self.ret.candidates(self.org, [self.rec]); self.assertEqual(len(c), 1); self.assertFalse(c[0]["on_hold"])
        self.ret.dispose(self.org, self.rec, "u", "retention period ended")
        with self.assertRaises(NotFoundError):
            self.w.vault.read_content(self.org, self.rec.id)
        self.assertEqual(self.w.vault.get_evidence(self.org, self.rec.id).file_hash, self.rec.file_hash)      # the record and fingerprint remain
        self.assertEqual(self.ret.candidates(self.org, [self.rec]), [])

    def test_legal_hold_blocks_disposal_until_released(self):
        self.age(3000)
        h = self.ret.place_hold(self.org, "u", "Tax inquiry 2026", evidence_id=self.rec.id)
        self.assertTrue(self.ret.candidates(self.org, [self.rec])[0]["on_hold"])
        with self.assertRaises(LegalHoldError):
            self.ret.dispose(self.org, self.rec, "u", "x")
        self.ret.release_hold(self.org, h["id"], "u")
        with self.assertRaises(RetentionError):
            self.ret.release_hold(self.org, h["id"], "u")
        self.ret.dispose(self.org, self.rec, "u", "x")

    def test_organisation_wide_hold_covers_everything(self):
        self.age(3000)
        self.ret.place_hold(self.org, "u", "Litigation")
        with self.assertRaises(LegalHoldError):
            self.ret.dispose(self.org, self.rec, "u", "x")

    def test_holds_need_a_reason_and_are_org_scoped(self):
        with self.assertRaises(ValidationError):
            self.ret.place_hold(self.org, "u", "  ")
        self.ret.place_hold(self.org, "u", "r")
        self.assertEqual(self.ret.holds(self.w.other_org.id), [])
        with self.assertRaises(NotFoundError):
            self.ret.release_hold(self.w.other_org.id, "nope", "u")

    def test_disposal_needs_a_reason(self):
        self.age(3000)
        with self.assertRaises(ValidationError):
            self.ret.dispose(self.org, self.rec, "u", "")


# ------------------------------------------------------------------------------------------------- privacy
class PrivacyTests(unittest.TestCase):
    def setUp(self):
        self.w = T.World(); self.clock = Clock(); self.store = SqliteDocStore(self.w.conn); self.keys = kr("k1")
        self.mfa = MfaService(self.store, self.keys, now=self.clock)
        self.guard = SessionGuard(self.store, self.w.identity.sessions, now=self.clock)
        self.audit = T.SqliteAuditRepository(self.w.conn)
        self.svc = privacy.PrivacyService(self.w.identity, self.mfa, self.guard, self.audit, self.store, self.clock)

    def test_export_contains_the_persons_data_and_no_secrets(self):
        _, tok = self.w.identity.authenticate("dara@meridian.test", PW)
        self.guard.register(self.w.identity.validate_session(tok), "1.2.3.4", "Firefox", "PASSWORD", False)
        x = self.svc.export(self.w.owner.id)
        txt = json.dumps(x)
        self.assertEqual(x["account"]["email"], "dara@meridian.test"); self.assertTrue(x["memberships"]); self.assertEqual(x["sessions"][0]["ip"], "1.2.3.4")
        for secret in ("password_hash", "pbkdf2", tok, "token_hash"):
            self.assertNotIn(secret, txt)
        self.assertTrue(any(e.action == "PRIVACY_EXPORT" for e in self.audit.list_for_actor(self.w.owner.id)))

    def test_erasure_flow_anonymises_but_keeps_records(self):
        uid = self.w.accountant.id
        r = self.svc.request_erasure(uid)
        self.assertEqual(r["status"], "PENDING"); self.assertEqual(self.svc.request_erasure(uid)["id"], r["id"])      # no duplicate requests
        done = self.svc.decide(r["id"], self.w.owner.id, True)
        self.assertEqual(done["status"], "COMPLETED")
        u = self.w.identity.users.get(uid)
        self.assertTrue(u.email.endswith("@erased.invalid")); self.assertFalse(u.is_active)
        from asavexa.identity.domain.password import verify_password
        self.assertFalse(verify_password(PW, u.password_hash))
        self.assertIsNone(self.w.identity.get_role(uid, self.w.org.id))                     # access gone
        self.assertTrue(self.w.accounting.journals.list_for_org(self.w.org.id))              # accounting records untouched
        self.assertTrue(self.audit.list_for_actor(uid))                                      # audit events keep the opaque id
        with self.assertRaises(RetentionError):
            self.svc.decide(r["id"], self.w.owner.id, True)

    def test_last_owner_cannot_be_erased(self):
        r = self.svc.request_erasure(self.w.owner.id)
        with self.assertRaises(RetentionError):
            self.svc.decide(r["id"], self.w.owner.id, True)
        self.assertTrue(self.w.identity.users.get(self.w.owner.id).is_active)

    def test_declining_needs_a_reason(self):
        r = self.svc.request_erasure(self.w.accountant.id)
        with self.assertRaises(ValidationError):
            self.svc.decide(r["id"], self.w.owner.id, False)
        d = self.svc.decide(r["id"], self.w.owner.id, False, "Open audit; records needed")
        self.assertEqual(d["status"], "DECLINED"); self.assertTrue(self.w.identity.users.get(self.w.accountant.id).is_active)

    def test_redaction_for_logs(self):
        t = privacy.redact("user jane.doe@example.com sent Authorization: Bearer abcdef1234567890 acct 0123456789012")
        self.assertNotIn("jane.doe", t); self.assertNotIn("abcdef1234567890", t); self.assertNotIn("0123456789012", t)
        self.assertIn("@example.com", t)


# ------------------------------------------------------------------------------------------------- alerts
def ev(i, action, actor="u1", when=None, new=None, org="o1"):
    return AuditEvent(id=f"e{i}", entity_type="X", entity_id=f"x{i}", action=action, actor=actor, timestamp=when or datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc), org_id=org, new_value=new)


class AlertTests(unittest.TestCase):
    NOW = datetime(2026, 10, 1, 13, 0, tzinfo=timezone.utc)

    def rules(self, events):
        return sorted(a["rule"] for a in alerts.detect(events, self.NOW))

    def test_repeated_failures_and_takeover_pattern(self):
        t = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
        fails = [ev(i, "LOGIN_FAILED", when=t + timedelta(minutes=i)) for i in range(5)]
        self.assertEqual(self.rules(fails), ["REPEATED_LOGIN_FAILURES"])
        self.assertEqual(self.rules(fails + [ev(9, "LOGIN_SUCCEEDED", when=t + timedelta(minutes=6))]), ["FAILED_THEN_SUCCEEDED"])
        self.assertEqual(self.rules(fails[:4]), [])
        spread = [ev(i, "LOGIN_FAILED", when=t + timedelta(minutes=20 * i)) for i in range(5)]
        self.assertEqual(self.rules(spread), [])

    def test_privilege_and_mfa_and_chain_events(self):
        r = self.rules([ev(1, "MFA_DISABLED"), ev(2, "MEMBERSHIP_ROLE_CHANGED", new={"role": "OWNER"}), ev(3, "MEMBERSHIP_ROLE_CHANGED", new={"role": "READ_ONLY"}),
                        ev(4, "AUDIT_CHAIN_FAILED"), ev(5, "MFA_LOCKED")])
        self.assertEqual(r, ["AUDIT_CHAIN_FAILED", "MFA_DISABLED", "MFA_LOCKED", "PRIVILEGE_GRANTED"])

    def test_download_burst(self):
        t = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
        self.assertEqual(self.rules([ev(i, "EVIDENCE_DOWNLOADED", when=t + timedelta(seconds=i * 10)) for i in range(20)]), ["DOWNLOAD_BURST"])
        self.assertEqual(self.rules([ev(i, "EVIDENCE_DOWNLOADED", when=t + timedelta(minutes=i)) for i in range(15)]), [])

    def test_old_events_are_ignored_and_most_severe_first(self):
        old = ev(1, "MFA_DISABLED", when=self.NOW - timedelta(days=30))
        self.assertEqual(self.rules([old]), [])
        out = alerts.detect([ev(1, "KEY_ROTATION_RUN"), ev(2, "AUDIT_CHAIN_FAILED")], self.NOW)
        self.assertEqual(out[0]["rule"], "AUDIT_CHAIN_FAILED")

    def test_service_deduplicates_notifies_once_and_acknowledges(self):
        sent = []
        svc = alerts.AlertService(MemoryDocStore(), lambda: self.NOW, notifier=sent.append)
        events = [ev(1, "MFA_DISABLED")]
        self.assertEqual(svc.refresh("o1", events)["new"], 1); self.assertEqual(svc.refresh("o1", events)["new"], 0)
        self.assertEqual(len(sent), 1)
        a = svc.list("o1")[0]; self.assertEqual(a["status"], "OPEN")
        with self.assertRaises(ValidationError):
            svc.acknowledge("o1", a["id"], "u", " ")
        self.assertEqual(svc.acknowledge("o1", a["id"], "u", "Checked with Sam")["status"], "ACKNOWLEDGED")
        self.assertEqual(svc.list("o1", status="OPEN"), []); self.assertEqual(svc.list("o2"), [])
        with self.assertRaises(NotFoundError):
            svc.acknowledge("o2", a["id"], "u", "x")

    def test_a_broken_webhook_never_breaks_the_check(self):
        def boom(a): raise RuntimeError("down")
        svc = alerts.AlertService(MemoryDocStore(), lambda: self.NOW, notifier=boom)
        self.assertEqual(svc.refresh("o1", [ev(1, "MFA_DISABLED")])["new"], 1)


# ------------------------------------------------------------------------------------------------- governance
class GovernanceTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock(); self.store = MemoryDocStore()
        self.settings = SettingsService(self.store, self.clock); self.vendors = VendorRegister(self.store, self.clock)

    def test_settings_validation(self):
        self.assertEqual(self.settings.get("o1"), {"require_mfa": False, "allowed_regions": []})
        s = self.settings.update("o1", "u", require_mfa=True, allowed_regions=["ng", "gh", "NG"])
        self.assertEqual((s["require_mfa"], s["allowed_regions"]), (True, ["GH", "NG"]))
        for kw in ({"allowed_regions": ["ZZ"]}, {"require_mfa": "yes"}):
            with self.assertRaises(ValidationError):
                self.settings.update("o1", "u", **kw)
        self.assertEqual(self.settings.get("o2")["require_mfa"], False)       # per organisation

    def test_vendor_risk_is_computed_from_facts(self):
        weak = self.vendors.add("o1", "u", {"name": "PayCo", "data_categories": ["FINANCIAL"], "region": ""})
        strong = self.vendors.add("o1", "u", {"name": "Safe", "data_categories": ["FINANCIAL"], "region": "EU", "dpa_signed": True,
                                              "security_attestation": "ISO 27001 cert on file", "subprocessors_known": True, "exit_plan": True, "last_reviewed": "2026-09-01"})
        self.assertIn(weak["risk_tier"], ("HIGH", "CRITICAL")); self.assertEqual(strong["risk_tier"], "MEDIUM" if strong["risk_score"] >= 3 else "LOW")
        self.assertGreater(weak["risk_score"], strong["risk_score"]); self.assertTrue(weak["risk_reasons"])
        self.assertEqual([v["name"] for v in self.vendors.list("o1")], ["PayCo", "Safe"])      # riskiest first

    def test_review_dates(self):
        v = self.vendors.add("o1", "u", {"name": "A", "data_categories": ["NONE"], "last_reviewed": "2026-09-01", "dpa_signed": True, "security_attestation": "x", "region": "EU", "exit_plan": True, "subprocessors_known": True})
        self.assertFalse(v["review_overdue"]); self.assertEqual((v["risk_tier"], v["next_review_due"]), ("LOW", "2028-08-31"))     # 730 days (2028 is a leap year)
        self.clock.advance(days=800)
        self.assertTrue(self.vendors.list("o1")[0]["review_overdue"])
        never = self.vendors.add("o1", "u", {"name": "B", "data_categories": ["NONE"]})
        self.assertTrue(never["review_overdue"])                                              # never reviewed = overdue

    def test_vendor_validation_isolation_and_update(self):
        for bad in ({}, {"name": "x", "data_categories": ["SECRETS"]}, {"name": "x", "status": "GONE"}, {"name": "x", "last_reviewed": "yesterday"}):
            with self.assertRaises(ValidationError):
                self.vendors.add("o1", "u", bad)
        v = self.vendors.add("o1", "u", {"name": "A", "data_categories": ["PERSONAL"]})
        self.assertEqual(self.vendors.list("o2"), [])
        with self.assertRaises(NotFoundError):
            self.vendors.update("o2", v["id"], "u", {"dpa_signed": True})
        better = self.vendors.update("o1", v["id"], "u", {"dpa_signed": True})
        self.assertLess(better["risk_score"], v["risk_score"])

    def test_seed_does_not_assume_facts_and_is_idempotent(self):
        made = self.vendors.seed_platform_vendors("o1", "u")
        self.assertEqual({v["name"] for v in made}, {"Render", "Vercel", "GitHub"})
        self.assertTrue(all(v["review_overdue"] and not v["dpa_signed"] and not v["security_attestation"] for v in made))
        self.assertEqual(self.vendors.seed_platform_vendors("o1", "u"), [])

    def test_residency_report_flags_vendors_outside_policy(self):
        res = ResidencyService(self.settings, self.vendors)
        self.vendors.add("o1", "u", {"name": "USCloud", "data_categories": ["FINANCIAL"], "region": "US"})
        self.vendors.add("o1", "u", {"name": "Tooling", "data_categories": ["SOURCE_CODE"], "region": "US"})
        self.assertTrue(res.report("o1", "NG", "NG")["compliant"])                # unrestricted
        self.settings.update("o1", "u", allowed_regions=["NG"])
        r = res.report("o1", "NG", "US")
        self.assertFalse(r["compliant"]); self.assertEqual([x["vendor"] for x in r["vendors_outside_policy"]], ["USCloud"])
        self.assertFalse([l for l in r["locations"] if l["ok"] is False and "Evidence" in l["what"]])


# ------------------------------------------------------------------------------------------------- monitoring
class MonitoringTests(unittest.TestCase):
    def test_health_statuses(self):
        h = HealthChecker().add("db", lambda: "ok").add("optional", lambda: 1 / 0, critical=False)
        r = h.run(); self.assertEqual(r["status"], "DEGRADED"); self.assertFalse(r["checks"][1]["ok"])
        h.add("keys", lambda: (_ for _ in ()).throw(RuntimeError("no keys")))
        self.assertEqual(h.run()["status"], "DOWN")
        self.assertEqual(HealthChecker().add("a", lambda: "ok").run()["status"], "OK")

    def test_rate_limiter_window(self):
        t = [0.0]; rl = RateLimiter(3, 60, now=lambda: t[0])
        self.assertTrue(all(rl.allow("ip")[0] for _ in range(3)))
        ok, wait = rl.allow("ip"); self.assertFalse(ok); self.assertGreater(wait, 0)
        self.assertTrue(rl.allow("other")[0])
        t[0] = 61; self.assertTrue(rl.allow("ip")[0])

    def test_metrics(self):
        m = Metrics(); m.inc("a"); m.inc("a", 2); self.assertEqual(m.snapshot()["counters"]["a"], 3)


# ------------------------------------------------------------------------------------------------- OIDC
ISS, CID, REDIR = "https://idp.test", "client-1", "https://app.test/cb"


class FakeIdp:
    def __init__(self):
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.kid = "idp-key-1"
        self.claims_override = {}
        self.last_nonce = None
        self.token_calls = 0
        self.email = "dara@meridian.test"

    def jwk(self):
        j = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        j.update(kid=self.kid, use="sig", alg="RS256"); return j

    def get(self, url):
        if url.endswith("/.well-known/openid-configuration"):
            return {"issuer": ISS, "authorization_endpoint": ISS + "/auth", "token_endpoint": ISS + "/token", "jwks_uri": ISS + "/jwks"}
        if url == ISS + "/jwks":
            return {"keys": [self.jwk()]}
        raise RuntimeError("unexpected " + url)

    def token(self, key=None, alg="RS256", headers=None, **claims):
        now = int(time.time())
        c = {"iss": ISS, "aud": CID, "sub": "sub-123", "iat": now, "exp": now + 300, "nonce": self.last_nonce, "email": self.email, "email_verified": True, **claims, **self.claims_override}
        return jwt.encode(c, key or self.key, algorithm=alg, headers={"kid": self.kid, **(headers or {})})

    def post(self, url, form):
        self.token_calls += 1
        self.last_form = form
        return {"id_token": self.next_token(), "access_token": "x"}


class OidcTests(unittest.TestCase):
    def setUp(self):
        self.w = T.World(); self.idp = FakeIdp(); self.store = MemoryDocStore()
        self.idp.next_token = lambda: self.idp.token()
        self.svc = OidcService(OidcConfig(ISS, CID, "shh", REDIR), kr("k1"), self.store, self.w.identity.users, http_get=self.idp.get, http_post=self.idp.post)
        self.binding = "browser-binding-0123456789"

    def begin(self):
        u = self.svc.start(self.binding)["url"]
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(u).query))
        self.idp.last_nonce = q["nonce"]
        return q

    def test_start_url_has_pkce_state_nonce_and_exact_redirect(self):
        q = self.begin()
        self.assertEqual((q["response_type"], q["code_challenge_method"], q["client_id"], q["redirect_uri"]), ("code", "S256", CID, REDIR))
        self.assertTrue(q["state"] and q["nonce"] and q["code_challenge"])
        self.assertNotIn("code_verifier", q)

    def test_full_login_for_an_existing_user_and_pkce_verifier_is_sent(self):
        q = self.begin()
        r = self.svc.finish("auth-code", q["state"], self.binding)
        self.assertEqual(r["user"].id, self.w.owner.id)
        f = self.idp.last_form
        self.assertEqual(f["code"], "auth-code")
        self.assertEqual(base64_urlsafe_sha256(f["code_verifier"]), q["code_challenge"])           # the verifier really matches the challenge
        self.assertTrue(self.store.list("oidc_link"))                                              # (issuer, subject) is now linked

    def test_state_is_single_use(self):
        q = self.begin(); self.svc.finish("c", q["state"], self.binding)
        with self.assertRaises(OidcError):
            self.svc.finish("c", q["state"], self.binding)

    def test_state_tampering_binding_and_expiry(self):
        q = self.begin()
        with self.assertRaises(OidcError): self.svc.finish("c", q["state"][:-3] + "abc", self.binding)
        with self.assertRaises(OidcError): self.svc.finish("c", "garbage", self.binding)
        with self.assertRaises(OidcError): self.svc.finish("c", q["state"], "another-browser-binding-xyz")
        q = self.begin(); later = OidcService(self.svc.cfg, self.svc.keys, self.store, self.w.identity.users, now=lambda: time.time() + 700, http_get=self.idp.get, http_post=self.idp.post)
        with self.assertRaises(OidcError): later.finish("c", q["state"], self.binding)
        with self.assertRaises(OidcError): self.svc.start("short")

    def rejects(self, **kw):
        q = self.begin()
        for k, v in kw.items():
            if k == "override": self.idp.claims_override = v
        self.idp.next_token = kw.get("tokenfn", self.idp.next_token)
        with self.assertRaises(OidcError) as c:
            self.svc.finish("c", q["state"], self.binding)
        return str(c.exception)

    def test_bad_tokens_are_rejected(self):
        for override in ({"iss": "https://evil.test"}, {"aud": "someone-else"}, {"exp": int(time.time()) - 3600}, {"nonce": "wrong"}, {"email_verified": False}, {"email_verified": "true"}):
            self.setUp(); self.rejects(override=override)

    def test_signature_by_an_unknown_key_is_rejected(self):
        self.idp.next_token = lambda: self.idp.token(key=rsa.generate_private_key(public_exponent=65537, key_size=2048))
        q = self.begin()
        with self.assertRaises(OidcError): self.svc.finish("c", q["state"], self.binding)

    def test_alg_none_and_hs256_confusion_are_rejected(self):
        pub_pem = self.idp.key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        now = int(time.time())
        for tokenfn in (lambda: jwt.encode({"iss": ISS, "aud": CID, "sub": "s", "iat": now, "exp": now + 99, "nonce": self.idp.last_nonce, "email": "dara@meridian.test", "email_verified": True}, None, algorithm="none", headers={"kid": self.idp.kid}),
                        lambda: jwt.encode({"iss": ISS, "aud": CID, "sub": "s", "iat": now, "exp": now + 99, "nonce": self.idp.last_nonce, "email": "dara@meridian.test", "email_verified": True}, "k" * 40, algorithm="HS256", headers={"kid": self.idp.kid})):
            self.idp.next_token = tokenfn
            q = self.begin()
            with self.assertRaises(OidcError): self.svc.finish("c", q["state"], self.binding)

    def test_unknown_or_inactive_users_are_not_created_or_admitted(self):
        self.idp.email = "stranger@nowhere.test"
        q = self.begin()
        with self.assertRaises(OidcError) as c: self.svc.finish("c", q["state"], self.binding)
        self.assertIn("no active", str(c.exception))
        self.assertIsNone(self.w.identity.users.get_by_email("stranger@nowhere.test"))          # no automatic sign-up
        self.idp.email = "dara@meridian.test"
        self.w.identity.users.update(__import__("dataclasses").replace(self.w.owner, is_active=False))
        q = self.begin()
        with self.assertRaises(OidcError): self.svc.finish("c", q["state"], self.binding)

    def test_domain_allow_list(self):
        self.svc.cfg.allowed_domains = ["other.test"]
        q = self.begin()
        with self.assertRaises(OidcError) as c: self.svc.finish("c", q["state"], self.binding)
        self.assertIn("domain", str(c.exception))

    def test_provider_mfa_claim_is_reported(self):
        self.idp.claims_override = {"amr": ["pwd", "mfa"]}
        q = self.begin(); self.assertTrue(self.svc.finish("c", q["state"], self.binding)["mfa_by_provider"])
        self.idp.claims_override = {"amr": ["pwd"]}
        q = self.begin(); self.assertFalse(self.svc.finish("c", q["state"], self.binding)["mfa_by_provider"])

    def test_key_rotation_at_the_provider_is_followed(self):
        q = self.begin(); self.svc.finish("c", q["state"], self.binding)
        self.idp.key = rsa.generate_private_key(public_exponent=65537, key_size=2048); self.idp.kid = "idp-key-2"
        q = self.begin(); self.assertEqual(self.svc.finish("c", q["state"], self.binding)["user"].id, self.w.owner.id)

    def test_provider_problems_are_clear_errors(self):
        def down(url): raise OSError("net")
        s = OidcService(self.svc.cfg, self.svc.keys, self.store, self.w.identity.users, http_get=down, http_post=self.idp.post)
        with self.assertRaises(OidcError): s.start(self.binding)
        wrong = lambda url: {**self.idp.get(url), "issuer": "https://other"} if url.endswith("configuration") else self.idp.get(url)
        with self.assertRaises(OidcError): OidcService(self.svc.cfg, self.svc.keys, self.store, self.w.identity.users, http_get=wrong).start(self.binding)
        http = lambda url: {**self.idp.get(url), "token_endpoint": "http://idp.test/token"} if url.endswith("configuration") else self.idp.get(url)
        with self.assertRaises(OidcError): OidcService(self.svc.cfg, self.svc.keys, self.store, self.w.identity.users, http_get=http).start(self.binding)

    def test_config_from_env(self):
        self.assertIsNone(OidcConfig.from_env({}))
        with self.assertRaises(OidcError): OidcConfig.from_env({"ASAVEXA_OIDC_ISSUER": ISS})
        c = OidcConfig.from_env({"ASAVEXA_OIDC_ISSUER": ISS + "/", "ASAVEXA_OIDC_CLIENT_ID": "a", "ASAVEXA_OIDC_CLIENT_SECRET": "b", "ASAVEXA_OIDC_REDIRECT_URI": REDIR, "ASAVEXA_OIDC_ALLOWED_DOMAINS": "A.com, b.com"})
        self.assertEqual((c.issuer, c.allowed_domains), (ISS, ["a.com", "b.com"]))


def base64_urlsafe_sha256(v):
    import base64
    return base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).decode().rstrip("=")


if __name__ == "__main__":
    unittest.main()
