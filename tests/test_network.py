"""The ASAVEXA Network: consent from both sides, the business decides, access is re-checked every time, everything is logged on both sides."""
import itertools
import unittest
from datetime import datetime, timedelta, timezone

from asavexa.network.errors import NetworkError, NetworkForbiddenError, NetworkNotFoundError, NetworkStateError
from asavexa.network.service import MAX_FAILED_CODES, TYPES, VIEWER_TYPES, NetworkService, clean_grant, default_grant, within
from asavexa.security.store import MemoryDocStore

BIZ, BIZ2, ACC, AUD, BANK, INV = "biz", "biz2", "acc", "aud", "bank", "inv"


class Clock:
    def __init__(self): self.t = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
    def __call__(self): return self.t
    def advance(self, **kw): self.t += timedelta(**kw)


class Base(unittest.TestCase):
    def setUp(self):
        self.clock = Clock(); self.logs = []
        self.s = NetworkService(MemoryDocStore(), log=lambda *a, **k: self.logs.append(a), now=self.clock)
        for org, typ, name in [(BIZ, "BUSINESS", "Adaeze Bakery"), (BIZ2, "BUSINESS", "Tailor Ltd"), (ACC, "ACCOUNTANT", "Obi & Co"), (AUD, "AUDITOR", "Audit LLP"), (BANK, "BANK", "First Bank"), (INV, "INVESTOR", "Seed Fund")]:
            self.s.set_profile(org, "u-" + org, typ, name)

    def offer(self, to="AUDITOR", **kw):
        return self.s.create_invite(BIZ, "u-biz", to, kw.pop("purpose", "Statutory audit 2026"), kw.pop("grant", None), **kw)

    def connect_offer(self, viewer=AUD, to="AUDITOR"):
        r = self.offer(to); return self.s.accept_invite(viewer, "u-" + viewer, r["code"])

    def request(self, who=BANK, typ="BANK", grant=None, **kw):
        return self.s.create_invite(who, "u-" + who, "BUSINESS", kw.pop("purpose", "Loan application"), grant, **kw)

    def by_action(self, a, org=None): return [x for x in self.logs if x[0] == a and (org is None or x[3] == org)]


class ProfileTests(Base):
    def test_validation(self):
        with self.assertRaises(NetworkError): self.s.set_profile("x", "u", "WIZARD", "Name")
        with self.assertRaises(NetworkError): self.s.set_profile("x", "u", "BANK", "a")
        with self.assertRaises(NetworkStateError): self.s.create_invite("noprofile", "u", "AUDITOR", "purpose here")

    def test_type_cannot_change_while_connected(self):
        self.connect_offer()
        with self.assertRaises(NetworkStateError): self.s.set_profile(AUD, "u", "REGULATOR", "Audit LLP")
        self.s.set_profile(AUD, "u", "AUDITOR", "Audit LLP renamed")          # a rename is fine


class DirectionTests(Base):
    def test_only_business_to_other_kinds_carries_data(self):
        for a, b in itertools.product(TYPES, TYPES):
            ok = (a == "BUSINESS") != (b == "BUSINESS")
            if ok: self.assertIn(NetworkService.kind_for(a, b), ("OFFER", "REQUEST"))
            else:
                with self.assertRaises(NetworkError, msg=(a, b)): NetworkService.kind_for(a, b)
        self.assertEqual(NetworkService.kind_for("BUSINESS", "BANK"), "OFFER"); self.assertEqual(NetworkService.kind_for("REGULATOR", "BUSINESS"), "REQUEST")

    def test_two_non_businesses_cannot_be_connected(self):
        with self.assertRaises(NetworkError): self.s.create_invite(ACC, "u", "AUDITOR", "Collaboration")
        with self.assertRaises(NetworkError): self.s.create_invite(BIZ, "u", "BUSINESS", "Peer share")


class GrantTests(unittest.TestCase):
    def test_defaults_are_the_safe_ones(self):
        g = clean_grant(None, datetime(2026, 10, 10).date())
        self.assertFalse(g["include_detail"]); self.assertTrue(g["closed_periods_only"]); self.assertEqual(g["date_to"], "2026-10-10"); self.assertEqual(g["date_from"], "2023-01-01")
        self.assertNotIn("GOVERNANCE", g["scopes"]); self.assertNotIn("AUDIT_TRAIL", g["scopes"])

    def test_validation_uses_the_sharing_rules(self):
        d = datetime(2026, 10, 10).date()
        for bad in ({"scopes": []}, {"scopes": ["SECRETS"]}, {"date_from": "2026-12-01", "date_to": "2026-01-01"}, {"date_from": "nonsense"}):
            with self.assertRaises(NetworkError, msg=bad): clean_grant(bad, d)

    def test_within(self):
        d = datetime(2026, 10, 10).date(); wide = clean_grant({"scopes": ["IDENTITY", "FINANCIAL_HISTORY"], "include_detail": False}, d)
        self.assertIsNone(within(clean_grant({"scopes": ["IDENTITY"]}, d), wide))
        self.assertIn("AUDIT_TRAIL", within(clean_grant({"scopes": ["IDENTITY", "AUDIT_TRAIL"]}, d), wide))
        self.assertIn("line-level", within(clean_grant({"scopes": ["IDENTITY"], "include_detail": True}, d), wide))
        self.assertIn("unfinished", within(clean_grant({"scopes": ["IDENTITY"], "closed_periods_only": False}, d), wide))
        self.assertIn("dates", within(clean_grant({"scopes": ["IDENTITY"], "date_from": "2020-01-01"}, d), wide))


class OfferTests(Base):
    def test_offer_accepted_by_the_right_kind_of_organisation(self):
        r = self.offer()
        self.assertTrue(r["code"].startswith("ASX-")); self.assertNotIn("code_hash", str(r["invite"]))
        pv = self.s.preview_invite(AUD, "u-aud", r["code"])
        self.assertEqual((pv["kind"], pv["from"]["name"], pv["you_decide"]), ("OFFER", "Adaeze Bakery", False))
        c = self.s.accept_invite(AUD, "u-aud", r["code"])
        self.assertEqual((c["role"], c["status"], c["counterparty"]["name"]), ("VIEWER", "ACTIVE", "Adaeze Bakery"))
        prov = self.s.list_connections(BIZ)[0]
        self.assertEqual((prov["role"], prov["counterparty"]), ("PROVIDER", {"name": "Audit LLP", "type": "AUDITOR"}))
        self.assertNotIn("views", c); self.assertEqual(prov["views"], 0)

    def test_code_is_forgiving_about_format_but_single_use(self):
        r = self.offer(); code = r["code"].lower().replace("-", " ")
        self.s.accept_invite(AUD, "u-aud", code)
        with self.assertRaises(NetworkError): self.s.accept_invite(AUD, "u-aud2", r["code"])             # used

    def test_wrong_kind_of_organisation_is_refused_and_the_invite_survives(self):
        r = self.offer("AUDITOR")
        with self.assertRaises(NetworkError): self.s.accept_invite(BANK, "u-bank", r["code"])
        with self.assertRaises(NetworkError): self.s.accept_invite(BIZ2, "u-biz2", r["code"])
        self.assertEqual(self.s.accept_invite(AUD, "u-aud", r["code"])["status"], "ACTIVE")

    def test_you_cannot_accept_your_own_invitation(self):
        r = self.offer()
        with self.assertRaises(NetworkError): self.s.accept_invite(BIZ, "u-biz", r["code"])

    def test_an_offer_cannot_be_edited_by_the_acceptor(self):
        r = self.offer()
        with self.assertRaises(NetworkError): self.s.accept_invite(AUD, "u-aud", r["code"], grant={"scopes": ["IDENTITY"]})

    def test_expired_and_cancelled_invitations(self):
        r = self.offer(invite_days=2); self.clock.advance(days=3)
        with self.assertRaises(NetworkError): self.s.accept_invite(AUD, "u-aud", r["code"])
        self.assertEqual(self.s.list_invites(BIZ)[0]["status"], "EXPIRED")
        r2 = self.offer(); inv = self.s.list_invites(BIZ)[0]
        self.s.cancel_invite(BIZ, "u-biz", inv["id"])
        with self.assertRaises(NetworkError): self.s.accept_invite(AUD, "u-aud", r2["code"])
        with self.assertRaises(NetworkStateError): self.s.cancel_invite(BIZ, "u-biz", inv["id"])
        with self.assertRaises(NetworkNotFoundError): self.s.cancel_invite(AUD, "u-aud", inv["id"])   # another organisation's invitation

    def test_validation_of_the_invitation(self):
        for kw in ({"purpose": " "}, {"invite_days": 0}, {"invite_days": 31}, {"connection_days": 400}, {"connection_days": True}):
            with self.assertRaises(NetworkError, msg=kw): self.offer(**kw)

    def test_only_one_active_connection_per_pair_and_pending_cap(self):
        self.connect_offer()
        with self.assertRaises(NetworkStateError): self.connect_offer()
        for _ in range(19): self.offer("BANK")      # one is already pending from the refused second connection
        with self.assertRaises(NetworkStateError): self.offer("BANK")


class RequestTests(Base):
    G = {"scopes": ["IDENTITY", "FINANCIAL_HISTORY", "EVIDENCE_QUALITY"]}

    def test_business_may_share_less_but_never_more(self):
        r = self.request(grant=self.G, connection_days=60)
        pv = self.s.preview_invite(BIZ, "u-biz", r["code"]); self.assertTrue(pv["you_decide"]); self.assertEqual(pv["from"]["type"], "BANK")
        with self.assertRaises(NetworkError): self.s.accept_invite(BIZ, "u-biz", r["code"], grant={"scopes": ["IDENTITY", "AUDIT_TRAIL"]})
        with self.assertRaises(NetworkError): self.s.accept_invite(BIZ, "u-biz", r["code"], grant={"scopes": ["IDENTITY"], "include_detail": True})
        with self.assertRaises(NetworkError): self.s.accept_invite(BIZ, "u-biz", r["code"], connection_days=90)
        c = self.s.accept_invite(BIZ, "u-biz", r["code"], grant={"scopes": ["IDENTITY"]}, connection_days=30)
        self.assertEqual((c["role"], c["grant"]["scopes"], c["counterparty"]["type"]), ("PROVIDER", ["IDENTITY"], "BANK"))
        self.assertEqual(self.s.list_connections(BANK)[0]["grant"]["scopes"], ["IDENTITY"])

    def test_default_is_exactly_what_was_asked(self):
        r = self.request(grant=self.G); c = self.s.accept_invite(BIZ, "u-biz", r["code"])
        self.assertEqual(c["grant"]["scopes"], self.G["scopes"])

    def test_only_a_business_can_answer_a_request(self):
        r = self.request()
        with self.assertRaises(NetworkError): self.s.accept_invite(AUD, "u-aud", r["code"])

    def test_every_non_business_kind_can_ask(self):
        for org in (ACC, AUD, BANK, INV):
            r = self.s.create_invite(org, "u-" + org, "BUSINESS", "Review request", self.G)
            self.s.accept_invite(BIZ if org != INV else BIZ2, "u-x", r["code"])
        self.assertEqual(len([c for c in self.s.list_connections(BIZ) if c["status"] == "ACTIVE"]), 3)


class CodeSecrecyTests(Base):
    def test_wrong_codes_give_one_generic_message_and_lock_out_a_guesser(self):
        r = self.offer(); msgs = set()
        for i in range(MAX_FAILED_CODES):
            try: self.s.preview_invite(AUD, "u-guess", f"ASX-AAAAA-0000{i}")
            except NetworkError as e: msgs.add(str(e))
        self.assertEqual(len(msgs), 1)
        with self.assertRaises(NetworkStateError): self.s.preview_invite(AUD, "u-guess", r["code"])        # even the right code is refused while locked
        self.clock.advance(minutes=16)
        self.assertEqual(self.s.preview_invite(AUD, "u-guess", r["code"])["kind"], "OFFER")
        self.assertEqual(self.s.accept_invite(AUD, "u-aud", r["code"])["status"], "ACTIVE")                  # someone else was never locked out

    def test_codes_are_not_stored_in_clear(self):
        r = self.offer(); blob = str(self.s.store._d)
        self.assertNotIn(r["code"], blob); self.assertNotIn(r["code"].replace("ASX-", "").replace("-", ""), blob)


class ViewAccessTests(Base):
    def setUp(self):
        super().setUp(); self.c = self.connect_offer(); self.cid = self.c["id"]

    def test_only_the_connected_viewer_may_open_it(self):
        conn, req = self.s.authorize_view(AUD, "u-aud", self.cid)
        self.assertEqual(conn["provider_org"], BIZ); self.assertEqual(req["scopes"], self.c["grant"]["scopes"]); self.assertFalse(req["include_detail"])
        for who in (BIZ, BANK, BIZ2, "stranger"):                                                           # the provider itself and everyone else
            with self.assertRaises(NetworkForbiddenError, msg=who): self.s.authorize_view(who, "u", self.cid)
        with self.assertRaises(NetworkForbiddenError): self.s.authorize_view(AUD, "u-aud", "no-such-id")

    def test_revoking_cuts_access_at_once_from_either_side(self):
        self.s.revoke(AUD, "u-aud", self.cid, "No longer engaged")
        with self.assertRaises(NetworkForbiddenError): self.s.authorize_view(AUD, "u-aud", self.cid)
        with self.assertRaises(NetworkStateError): self.s.revoke(BIZ, "u-biz", self.cid, "again")
        c2 = self.connect_offer()                                                                            # a fresh connection is possible after ending
        self.s.revoke(BIZ, "u-biz", c2["id"], "Contract ended")
        with self.assertRaises(NetworkForbiddenError): self.s.authorize_view(AUD, "u-aud", c2["id"])
        with self.assertRaises(NetworkNotFoundError): self.s.revoke(BANK, "u-bank", c2["id"], "not mine")
        with self.assertRaises(NetworkError): self.s.revoke(BIZ, "u", self.connect_offer()["id"], " ")

    def test_expiry_ends_access_by_itself(self):
        self.clock.advance(days=91)
        with self.assertRaises(NetworkForbiddenError): self.s.authorize_view(AUD, "u-aud", self.cid)
        self.assertEqual(self.s.list_connections(AUD)[0]["status"], "EXPIRED")
        with self.assertRaises(NetworkStateError): self.s.update_grant(BIZ, "u-biz", self.cid, extend_days=30)
        self.connect_offer()                                                                                  # an expired connection does not block a new one

    def test_only_the_business_changes_the_grant(self):
        with self.assertRaises(NetworkForbiddenError): self.s.update_grant(AUD, "u-aud", self.cid, {"scopes": ["GOVERNANCE", "AUDIT_TRAIL"]})
        c = self.s.update_grant(BIZ, "u-biz", self.cid, {"scopes": ["IDENTITY"]})
        self.assertEqual(c["grant"]["scopes"], ["IDENTITY"]); self.assertEqual(self.s.authorize_view(AUD, "u", self.cid)[1]["scopes"], ["IDENTITY"])
        self.clock.advance(days=80)
        c = self.s.update_grant(BIZ, "u-biz", self.cid, extend_days=30)
        self.clock.advance(days=20); self.s.authorize_view(AUD, "u", self.cid)                                # would have expired without the extension
        self.assertEqual({e["event"] for e in c["history"]}, {"CONNECTED", "CHANGED"})
        self.assertEqual(len(self.by_action("NETWORK_GRANT_CHANGED")), 4)                                      # two changes, each on both sides
        with self.assertRaises(NetworkError): self.s.update_grant(BIZ, "u-biz", self.cid, {"scopes": ["NONSENSE"]})

    def test_a_no_op_change_is_not_logged(self):
        self.s.update_grant(BIZ, "u-biz", self.cid, {"scopes": self.c["grant"]["scopes"]}); self.assertEqual(self.by_action("NETWORK_GRANT_CHANGED"), [])

    def test_views_are_counted_and_the_business_can_see_who_looked(self):
        conn, _ = self.s.authorize_view(AUD, "u-aud", self.cid)
        self.s.record_view(conn, "u-aud", "ab" * 32); self.clock.advance(minutes=5); self.s.record_view(conn, "u-aud2", "cd" * 32)
        p = self.s.list_connections(BIZ)[0]; self.assertEqual(p["views"], 2)
        log = self.s.access_log(BIZ, self.cid); self.assertEqual([r["user_id"] for r in log], ["u-aud2", "u-aud"]); self.assertEqual(log[0]["viewer_name"], "Audit LLP")
        self.assertEqual({x[3] for x in self.by_action("NETWORK_PASSPORT_VIEWED")}, {BIZ, AUD})
        with self.assertRaises(NetworkNotFoundError): self.s.access_log(AUD, self.cid)                         # the viewer cannot read the provider's access log


class LoggingAndOverviewTests(Base):
    def test_connection_and_disconnection_are_logged_on_both_sides(self):
        c = self.connect_offer(); self.s.revoke(BIZ, "u-biz", c["id"], "Done")
        for a in ("NETWORK_CONNECTED", "NETWORK_DISCONNECTED"): self.assertEqual({x[3] for x in self.by_action(a)}, {BIZ, AUD}, a)

    def test_overview(self):
        self.connect_offer(); r = self.request(BANK); self.s.accept_invite(BIZ, "u-biz", r["code"]); self.offer("INVESTOR")
        o = self.s.overview(BIZ)
        self.assertEqual((o["active"], o["by_type"], o["pending_invites"]), (2, {"AUDITOR": 1, "BANK": 1}, 1)); self.assertEqual(o["can_offer_to"], list(VIEWER_TYPES))
        self.assertEqual(self.s.overview(BANK)["can_offer_to"], ["BUSINESS"]); self.assertEqual(self.s.overview("nobody")["can_offer_to"], [])


if __name__ == "__main__":
    unittest.main()
