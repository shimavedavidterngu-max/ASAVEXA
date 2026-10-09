"""
Permissioned sharing of the Financial Passport, exercised end to end over the
real Passport builder, real accounting/evidence/reconciliation services and the
real audit repository (SQLite). Only the share store is the in-memory reference.
"""
import json
import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest import mock

from asavexa.accounting.services.engine import LineInput
from asavexa.passport import sharing
from asavexa.passport.errors import (
    ShareAccessDeniedError, ShareNotFoundError, ShareStateError, ShareValidationError,
)
from asavexa.passport.sharing import InMemoryShareStore, ShareService
from test_passport import World

LONG = dict(date_from="2020-01-01", date_to="2039-12-31")


def now():
    return datetime.now(timezone.utc)


def req(**over):
    base = dict(recipient_name="First Bank Plc", recipient_type="BANK", recipient_email="loans@firstbank.test",
                purpose="Loan application", scopes=["FINANCIAL_HISTORY"], expires_in_days=30,
                include_detail=False, allow_download=False, closed_periods_only=False, **LONG)
    base.update(over)
    return base


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.w = World()

    def setUp(self):
        self.store = InMemoryShareStore()
        self.svc = ShareService(self.store, self.w.audit)
        self.t = now()

    def inputs(self):
        return self.w.inputs(profile={"legal_name": "Meridian Textiles Limited", "base_currency": "NGN"})

    def create(self, **over):
        return self.svc.create_share(self.inputs(), req(**over), actor=self.w.owner.id, now=self.t)

    def verify(self, c, code=None, email="loans@firstbank.test", at=None):
        return self.svc.verify(c["access_token"], code or c["access_code"], email, at or self.t)


class ValidationTests(Base):
    def bad(self, msg, **over):
        with self.assertRaises(ShareValidationError) as cm:
            self.create(**over)
        self.assertIn(msg, str(cm.exception))

    def test_rejections(self):
        self.bad("who you are sharing with", recipient_name="  ")
        self.bad("Recipient type", recipient_type="WIZARD")
        self.bad("valid email", recipient_email="not-an-email")
        self.bad("at least one section", scopes=[])
        self.bad("Unknown information section", scopes=["SECRETS"])
        self.bad("YYYY-MM-DD", date_from="yesterday")
        self.bad("must not be after", date_from="2030-01-01", date_to="2029-01-01")
        self.bad("too long", date_from="1990-01-01", date_to="2039-01-01")
        self.bad("between 1 and 365", expires_in_days=0)
        self.bad("between 1 and 365", expires_in_days=366)
        self.bad("between 1 and 365", expires_in_days=True)
        self.bad("too long", purpose="x" * 501)
        self.assertEqual(self.store.shares, {}, "nothing is stored when validation fails")

    def test_defaults_are_the_safe_ones(self):
        r = sharing.validate_request({"recipient_name": "X", "scopes": ["identity"], "date_from": "2026-01-01", "date_to": "2026-12-31"})
        self.assertEqual((r["include_detail"], r["allow_download"], r["closed_periods_only"], r["expires_in_days"]), (False, False, False, 30))
        self.assertEqual(r["scopes"], ["IDENTITY"])  # case-insensitive, de-duplicated


class ContentTests(Base):
    def test_only_chosen_sections_are_shared(self):
        c = self.create(scopes=["FINANCIAL_HISTORY", "REPORTING"])
        v = self.svc.view(self.verify(c)["session_token"], self.t)
        self.assertEqual(sorted(v["sections"]), ["financial_history", "reporting"])
        self.assertNotIn("audit_trail", v["sections"])

    def test_figures_are_the_organisations_real_figures(self):
        c = self.create()
        s = self.svc.view(self.verify(c)["session_token"], self.t)["sections"]["financial_history"]
        self.assertEqual(s["totals"]["revenue"], "1000000.00")
        self.assertEqual(s["totals"]["net_income"], "800000.00")
        self.assertEqual(s["currency"], "NGN")

    def test_summary_level_withholds_names_emails_and_line_items(self):
        c = self.create(scopes=list(sharing.SCOPES))
        text = json.dumps(self.svc.view(self.verify(c)["session_token"], self.t)["sections"])
        self.assertNotIn("@meridian.test", text, "no team email may leak at summary level")
        self.assertNotIn("January rent", text)
        self.assertNotIn("Unknown debit", text)
        sec = self.svc.view(self.verify(c)["session_token"], self.t)["sections"]
        self.assertTrue(sec["evidence_quality"]["detail_withheld"])
        self.assertEqual(sec["evidence_quality"]["transactions"]["missing_evidence"], 1, "counts remain")
        self.assertEqual(sec["evidence_quality"]["missing_evidence"]["count"], 1)
        self.assertEqual(sec["governance"]["segregation_of_duties"]["role_conflict_count"], 1)
        self.assertGreaterEqual(sec["audit_trail"]["people_count"], 3)

    def test_detail_included_when_chosen(self):
        c = self.create(scopes=list(sharing.SCOPES), include_detail=True)
        sec = self.svc.view(self.verify(c)["session_token"], self.t)["sections"]
        text = json.dumps(sec)
        self.assertIn("January rent", text)
        self.assertIn("kwame@meridian.test", text)
        self.assertNotIn("detail_withheld", text)
        self.assertTrue(any("Line-level detail" in w for w in c["warnings"]))

    def test_date_range_limits_periods_and_figures(self):
        c = self.create(date_from="2026-02-01", date_to="2026-02-28")   # only the empty February period
        fh = self.svc.view(self.verify(c)["session_token"], self.t)["sections"]["financial_history"]
        self.assertEqual(fh["totals"]["revenue"], "0.00")
        self.assertEqual([p["period_name"] for p in fh["periods"]], ["FY2026-M02"])
        self.assertEqual(c["share"]["periods_excluded"], 1)

    def test_range_with_no_complete_period_warns(self):
        c = self.create(date_from="2025-01-01", date_to="2025-12-31")
        self.assertTrue(any("No accounting period falls entirely" in w for w in c["warnings"]))

    def test_a_period_only_partly_inside_the_range_is_not_included(self):
        c = self.create(date_from="2026-01-10", date_to="2026-12-31")   # January starts on the 1st
        self.assertEqual([p["name"] for p in c["share"]["periods_included"]], ["FY2026-M02"])

    def test_closed_periods_only(self):
        c = self.create(closed_periods_only=True)
        self.assertEqual(c["share"]["periods_included"], [])
        self.assertTrue(any("(and is closed)" in w for w in c["warnings"]))
        self.assertEqual(self.svc.view(self.verify(c)["session_token"], self.t)["sections"]["financial_history"]["totals"]["revenue"], "0.00")

    def test_audit_events_outside_the_window_are_not_shared(self):
        c = self.create(scopes=["AUDIT_TRAIL"], include_detail=True, date_from="2020-01-01", date_to="2020-12-31")
        a = self.svc.view(self.verify(c)["session_token"], self.t)["sections"]["audit_trail"]
        self.assertEqual(a["total_events"], 0)
        self.assertEqual(a["recent_events"], [])

    def test_no_email_given_warns(self):
        c = self.create(recipient_email=None)
        self.assertTrue(any("No recipient email" in w for w in c["warnings"]))

    def test_snapshot_does_not_change_when_the_books_change(self):
        w = World()                       # its own books: this test posts a journal
        svc = ShareService(InMemoryShareStore(), w.audit)
        mk = lambda: svc.create_share(w.inputs(profile={"legal_name": "M"}), req(), actor=w.owner.id, now=self.t)
        rev = lambda c: svc.view(svc.verify(c["access_token"], c["access_code"], "loans@firstbank.test", self.t)["session_token"], self.t)["sections"]["financial_history"]["totals"]["revenue"]
        c = mk()
        self.assertEqual(rev(c), "1000000.00")
        d = w.accounting.create_draft_journal(w.org.id, date(2026, 1, 28), "Late sale", "NGN", [
            LineInput(w.cash.id, debit_amount=Decimal("500.00")), LineInput(w.rev.id, credit_amount=Decimal("500.00"))],
            created_by=w.accountant.id)
        w.accounting.post_journal(w.org.id, d.id, actor=w.approver.id)
        self.assertEqual(rev(c), "1000000.00", "an existing share keeps showing what was approved")
        self.assertEqual(rev(mk()), "1000500.00", "a new share reflects the new books")


class VerificationTests(Base):
    def test_full_happy_path_and_integrity(self):
        c = self.create()
        v = self.verify(c)
        self.assertEqual(v["share"]["recipient_name"], "First Bank Plc")
        view = self.svc.view(v["session_token"], self.t)
        self.assertTrue(view["integrity"]["verified"])
        self.assertEqual(view["share"]["organisation"], "Meridian Textiles Limited")
        json.dumps(view)

    def test_code_is_forgiving_about_case_and_spaces_not_about_value(self):
        c = self.create()
        messy = c["access_code"].lower().replace("-", " ")
        self.assertTrue(self.verify(c, code=messy)["session_token"])
        self.assertRegex(c["access_code"], r"^[A-HJ-NP-Z2-9]{5}-[A-HJ-NP-Z2-9]{5}$")

    def test_email_is_required_and_must_match_when_named(self):
        c = self.create()
        for bad in (None, "", "someone@else.test"):
            with self.assertRaises(ShareAccessDeniedError):
                self.verify(c, email=bad)
        self.assertTrue(self.verify(c, email="  LOANS@FirstBank.test ")["session_token"])

    def test_wrong_code_counts_down_then_locks_even_for_the_right_code(self):
        c = self.create()
        messages = []
        for _ in range(5):
            with self.assertRaises(ShareAccessDeniedError) as cm:
                self.verify(c, code="AAAAA-AAAAA")
            messages.append(str(cm.exception))
        self.assertIn("4 attempt(s) left", messages[0])
        self.assertIn("now locked", messages[-1])
        with self.assertRaises(ShareAccessDeniedError):
            self.verify(c)          # correct credentials, but locked
        self.assertEqual(self.svc.get_share(self.w.org.id, c["share"]["id"], self.t)["status"], "LOCKED")
        actions = [e["action"] for e in self.svc.access_log(self.w.org.id, c["share"]["id"])]
        self.assertIn("PASSPORT_SHARE_LOCKED", actions)
        self.assertEqual(actions.count("PASSPORT_SHARE_DENIED"), 6)

    def test_success_resets_the_failure_counter(self):
        c = self.create()
        for _ in range(4):
            with self.assertRaises(ShareAccessDeniedError):
                self.verify(c, code="AAAAA-AAAAA")
        self.verify(c)
        for _ in range(4):
            with self.assertRaises(ShareAccessDeniedError):
                self.verify(c, code="AAAAA-AAAAA")
        self.assertEqual(self.svc.get_share(self.w.org.id, c["share"]["id"], self.t)["status"], "ACTIVE")

    def test_a_stranger_without_the_link_cannot_lock_or_probe(self):
        c = self.create()
        sid = c["share"]["id"]
        for token in (f"{sid}.wrongsecret", "garbage", "", f"{sid}.", "not-a-uuid.secret", "." + "x" * 40):
            for _ in range(8):
                with self.assertRaises(ShareAccessDeniedError) as cm:
                    self.svc.verify(token, c["access_code"], "loans@firstbank.test", self.t)
                self.assertEqual(str(cm.exception), sharing.DENIED)
        share = self.svc.get_share(self.w.org.id, sid, self.t)
        self.assertEqual((share["status"], share["failed_attempts"]), ("ACTIVE", 0))
        self.assertTrue(self.verify(c)["session_token"])

    def test_unknown_and_invalid_session_tokens_are_refused(self):
        for tok in (None, "", "nope", "x" * 43):
            with self.assertRaises(ShareAccessDeniedError):
                self.svc.view(tok, self.t)

    def test_session_and_share_expiry(self):
        c = self.create(expires_in_days=1)
        v = self.verify(c)
        self.svc.view(v["session_token"], self.t + timedelta(minutes=59))
        with self.assertRaises(ShareAccessDeniedError) as cm:
            self.svc.view(v["session_token"], self.t + timedelta(minutes=61))
        self.assertIn("verify again", str(cm.exception))
        with self.assertRaises(ShareAccessDeniedError):
            self.verify(c, at=self.t + timedelta(days=1, minutes=1))
        self.assertEqual(self.svc.get_share(self.w.org.id, c["share"]["id"], self.t + timedelta(days=2))["status"], "EXPIRED")

    def test_session_never_outlives_the_share(self):
        c = self.create(expires_in_days=1)
        late = self.t + timedelta(hours=23, minutes=30)
        v = self.svc.verify(c["access_token"], c["access_code"], "loans@firstbank.test", late)
        with self.assertRaises(ShareAccessDeniedError):
            self.svc.view(v["session_token"], self.t + timedelta(days=1, minutes=1))

    def test_tampering_with_the_stored_snapshot_is_detected(self):
        c = self.create()
        sess = self.verify(c)["session_token"]
        stored = self.store.shares[c["share"]["id"]]
        stored.snapshot["sections"]["financial_history"]["totals"]["revenue"] = "999999999.00"
        self.assertFalse(self.svc.view(sess, self.t)["integrity"]["verified"])


class RevocationAndPermissionsTests(Base):
    def test_revoke_cuts_off_an_already_verified_recipient_immediately(self):
        c = self.create()
        sess = self.verify(c)["session_token"]
        self.svc.view(sess, self.t)
        r = self.svc.revoke_share(self.w.org.id, c["share"]["id"], self.w.owner.id, "Loan declined", self.t)
        self.assertEqual((r["status"], r["revoke_reason"]), ("REVOKED", "Loan declined"))
        with self.assertRaises(ShareAccessDeniedError):
            self.svc.view(sess, self.t)
        with self.assertRaises(ShareAccessDeniedError):
            self.verify(c)
        with self.assertRaises(ShareStateError):
            self.svc.revoke_share(self.w.org.id, c["share"]["id"], self.w.owner.id, None, self.t)

    def test_another_organisation_cannot_see_or_revoke_a_share(self):
        c = self.create()
        other = self.w.other_org.id
        self.assertEqual(self.svc.list_shares(other, self.t), [])
        for call in (lambda: self.svc.get_share(other, c["share"]["id"], self.t),
                     lambda: self.svc.revoke_share(other, c["share"]["id"], "x", None, self.t),
                     lambda: self.svc.access_log(other, c["share"]["id"]),
                     lambda: self.svc.get_share(other, "not-a-uuid", self.t)):
            with self.assertRaises(ShareNotFoundError):
                call()
        self.assertEqual(self.svc.get_share(self.w.org.id, c["share"]["id"], self.t)["status"], "ACTIVE")

    def test_download_only_when_permitted_and_it_is_logged(self):
        no = self.create(allow_download=False)
        with self.assertRaises(ShareAccessDeniedError) as cm:
            self.svc.download(self.verify(no)["session_token"], self.t)
        self.assertIn("did not allow", str(cm.exception))
        yes = self.create(allow_download=True)
        d = self.svc.download(self.verify(yes)["session_token"], self.t)
        self.assertEqual(d["kind"], sharing.KIND)
        self.assertTrue(d["integrity"]["verified"])
        json.dumps(d)
        self.assertIn("PASSPORT_SHARE_DOWNLOADED", [e["action"] for e in self.svc.access_log(self.w.org.id, yes["share"]["id"])])

    def test_secrets_never_appear_in_what_the_organisation_sees(self):
        c = self.create()
        self.verify(c)
        secret = c["access_token"].split(".", 1)[1]
        blob = json.dumps([self.svc.list_shares(self.w.org.id, self.t), self.svc.get_share(self.w.org.id, c["share"]["id"], self.t),
                           self.svc.access_log(self.w.org.id, c["share"]["id"]), c["share"]])
        for needle in (secret, c["access_code"], c["access_code"].replace("-", ""), "secret_hash", "code_hash", "code_salt", "snapshot"):
            self.assertNotIn(needle, blob)
        stored = self.store.shares[c["share"]["id"]]
        self.assertNotIn(secret, json.dumps(stored.snapshot))
        self.assertNotEqual(stored.secret_hash, secret)

    def test_recipient_view_has_no_organisation_internals(self):
        c = self.create()
        v = self.svc.view(self.verify(c)["session_token"], self.t)
        text = json.dumps(v)
        for forbidden in (self.w.org.id, self.w.owner.id, "secret_hash", "code_hash", "failed_attempts"):
            self.assertNotIn(forbidden, text)

    def test_access_log_tells_the_whole_story(self):
        c = self.create(allow_download=True)
        sid = c["share"]["id"]
        with self.assertRaises(ShareAccessDeniedError):
            self.verify(c, code="AAAAA-AAAAA")
        sess = self.verify(c)["session_token"]
        self.svc.view(sess, self.t)
        self.svc.download(sess, self.t)
        self.svc.revoke_share(self.w.org.id, sid, self.w.owner.id, "done", self.t)
        actions = [e["action"] for e in self.svc.access_log(self.w.org.id, sid, labels={self.w.owner.id: "dara@meridian.test"})]
        for a in ("PASSPORT_SHARE_CREATED", "PASSPORT_SHARE_DENIED", "PASSPORT_SHARE_VERIFIED", "PASSPORT_SHARE_VIEWED",
                  "PASSPORT_SHARE_DOWNLOADED", "PASSPORT_SHARE_REVOKED"):
            self.assertIn(a, actions)
        created = [e for e in self.svc.access_log(self.w.org.id, sid, labels={self.w.owner.id: "dara@meridian.test"}) if e["action"] == "PASSPORT_SHARE_CREATED"][0]
        self.assertEqual(created["who"], "dara@meridian.test")
        self.assertEqual(created["detail"]["recipient"], "First Bank Plc")

    def test_cap_on_active_shares(self):
        with mock.patch.object(sharing, "MAX_ACTIVE_SHARES", 2):
            self.create(); self.create()
            with self.assertRaises(ShareStateError):
                self.create()
            first = self.svc.list_shares(self.w.org.id, self.t)[0]
            self.svc.revoke_share(self.w.org.id, first["id"], self.w.owner.id, None, self.t)
            self.create()   # revoking frees a slot

    def test_sharing_events_do_not_change_the_live_passport_fingerprint(self):
        from asavexa.passport.builder import build_passport
        before = build_passport(self.inputs(), None, self.t)["fingerprint"]
        c = self.create()
        sess = self.verify(c)["session_token"]
        self.svc.view(sess, self.t)
        self.svc.revoke_share(self.w.org.id, c["share"]["id"], self.w.owner.id, None, self.t)
        self.assertEqual(build_passport(self.inputs(), None, self.t)["fingerprint"], before)


if __name__ == "__main__":
    unittest.main()
