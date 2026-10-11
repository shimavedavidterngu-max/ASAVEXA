"""Business Development: accounts, pipeline stages, proposals and discount approval, win confirmation, targets and forecast, reports, isolation."""
import csv
import io
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

from analysis_fixture import ORG, OTHER, World
from asavexa.bizdev.errors import BizDevError, BizDevForbiddenError, BizDevNotFoundError, BizDevStateError
from asavexa.bizdev.service import BizDevService
from asavexa.evidence.domain.enums import EvidenceType
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.permissions import BD_APPROVE, BD_PREPARE, REPORTING_READ, ROLE_PERMISSIONS

U1, U2, U3 = "user-1", "user-2", "user-3"


class Clock:
    def __init__(self): self.d = date(2026, 2, 15)
    def __call__(self): return datetime(self.d.year, self.d.month, self.d.day, 9, tzinfo=timezone.utc)


class Base(unittest.TestCase):
    def setUp(self):
        self.w = World(); self.clock = Clock(); self.events = []
        self.svc = BizDevService(self.w.store, self.w.vault, log=lambda *a: self.events.append(a), now=self.clock)

    def acct(self, name="Meridian Textiles", **kw):
        return self.svc.create_account(ORG, dict(name=name, kind="PROSPECT", **kw), U1)

    def opp(self, value="100000", cur="NGN", close="2026-04-30", **kw):
        a = kw.pop("account", None) or self.acct(name=kw.pop("aname", "Meridian Textiles"))
        d = dict(account_id=a["id"], title="Audit retainer", currency=cur, value=value, expected_close=close); d.update(kw)
        return self.svc.create_opportunity(ORG, d, U1)

    def items(self, n=1, price="1000", qty="10"): return [{"description": f"Service {i}", "quantity": qty, "unit_price": price} for i in range(1, n + 1)]

    def prop(self, o, pct="0", price="1000", qty="10", valid="2026-03-31", **kw):
        d = dict(items=self.items(price=price, qty=qty), discount_pct=pct, valid_until=valid); d.update(kw)
        o = self.svc.create_proposal(ORG, o["id"], d, U1); return o, o["proposals"][-1]

    def sent(self, o, **kw):
        o, p = self.prop(o, **kw)
        self.svc.submit_proposal(ORG, o["id"], p["id"], U1)
        if self.svc.get_opportunity(ORG, o["id"])["proposals"][-1]["status"] == "PENDING_APPROVAL": self.svc.approve_proposal(ORG, o["id"], p["id"], U2)
        return self.svc.send_proposal(ORG, o["id"], p["id"], U1), p["id"]

    def won(self, o=None, value=None, **kw):
        o = o or self.opp(**kw)
        o, pid = self.sent(o); self.svc.accept_proposal(ORG, o["id"], pid, "Client signed", U1)
        self.svc.request_win(ORG, o["id"], "", U1); return self.svc.approve_win(ORG, o["id"], U2)


class Accounts(Base):
    def test_create_validate_duplicate_archive(self):
        a = self.acct(sector="Textiles", contacts=[{"name": "Ada N", "email": "ada@example.com"}])
        self.assertEqual((a["ref"], a["status"], a["kind"]), ("A-001", "ACTIVE", "PROSPECT"))
        for bad in (dict(name="x"), dict(name="Fine Co", kind="ENEMY"), dict(name="Fine Co", contacts=[{"name": "A"}]), dict(name="Fine Co", contacts=[{"name": "Bob B", "email": "bob example"}]),
                    dict(name="Fine Co", contacts="no")):
            with self.assertRaises(BizDevError): self.svc.create_account(ORG, bad, U1)
        with self.assertRaises(BizDevError): self.acct(name="  meridian TEXTILES ")
        o = self.opp(account=a)
        with self.assertRaises(BizDevStateError): self.svc.archive_account(ORG, a["id"], "no longer needed", U1)
        self.svc.mark_lost(ORG, o["id"], "Client chose another firm", U1)
        self.assertEqual(self.svc.archive_account(ORG, a["id"], "no longer needed", U1)["status"], "ARCHIVED")
        with self.assertRaises(BizDevStateError): self.svc.update_account(ORG, a["id"], {"notes": "x"}, U1)
        with self.assertRaises(BizDevStateError): self.opp(account=a)
        self.acct(name="Meridian Textiles")  # name free again after archive

    def test_update_keeps_other_fields(self):
        a = self.acct(sector="Retail"); b = self.svc.update_account(ORG, a["id"], {"notes": "Warm lead"}, U2)
        self.assertEqual((b["sector"], b["notes"], b["name"]), ("Retail", "Warm lead", "Meridian Textiles"))
        self.assertEqual(self.svc.list_accounts(ORG)[0]["open_opportunities"], 0)


class Opportunities(Base):
    def test_create_rules(self):
        a = self.acct()
        base = dict(account_id=a["id"], title="Deal one", currency="ngn", value="500.5", expected_close="2026-03-01")
        o = self.svc.create_opportunity(ORG, base, U1)
        self.assertEqual((o["ref"], o["stage"], o["currency"], o["value"], o["probability"], o["weighted"], o["account_name"]), ("O-001", "LEAD", "NGN", "500.50", 10, "50.05", "Meridian Textiles"))
        for k, v in (("title", "ab"), ("currency", "NG"), ("currency", "N1A"), ("value", "0"), ("value", "-5"), ("value", "abc"), ("value", "1,000"), ("expected_close", "2026-01-01"), ("expected_close", "2026-02-30"),
                     ("stage", "WON"), ("account_id", "nope")):
            with self.assertRaises(BizDevError, msg=f"{k}={v}"): self.svc.create_opportunity(ORG, {**base, k: v}, U1)

    def test_stage_moves_and_negotiation_needs_sent_proposal(self):
        o = self.opp()
        self.assertEqual(self.svc.move_stage(ORG, o["id"], "qualified", "", U1)["stage"], "QUALIFIED")
        with self.assertRaises(BizDevStateError): self.svc.move_stage(ORG, o["id"], "NEGOTIATION", "", U1)
        with self.assertRaises(BizDevError): self.svc.move_stage(ORG, o["id"], "WON", "", U1)
        with self.assertRaises(BizDevError): self.svc.move_stage(ORG, o["id"], "QUALIFIED", "", U1)
        with self.assertRaises(BizDevError): self.svc.move_stage(ORG, o["id"], "LEAD", "", U1)  # backwards needs a reason
        self.assertEqual(self.svc.move_stage(ORG, o["id"], "LEAD", "Contact went quiet", U1)["stage"], "LEAD")
        o, _ = self.sent(o)
        self.assertEqual(o["stage"], "PROPOSAL")  # sending moves a lead forward
        self.assertEqual(self.svc.move_stage(ORG, o["id"], "NEGOTIATION", "", U1)["stage"], "NEGOTIATION")
        hist = self.svc.get_opportunity(ORG, o["id"])["stage_history"]
        self.assertEqual([h["to"] for h in hist], ["LEAD", "QUALIFIED", "LEAD", "PROPOSAL", "NEGOTIATION"])

    def test_activity_rules(self):
        o = self.opp()
        r = self.svc.add_activity(ORG, o["id"], dict(type="call", date="2026-02-10", summary="Intro call"), U1)
        self.assertEqual(r["activities"][0]["type"], "CALL")
        for bad in (dict(type="TEXT", summary="hello there"), dict(type="CALL", summary="hi"), dict(type="CALL", date="2026-03-01", summary="future call")):
            with self.assertRaises(BizDevError): self.svc.add_activity(ORG, o["id"], bad, U1)

    def test_lost_needs_reason_and_freezes(self):
        o = self.opp(); o2, pid = self.sent(o)
        with self.assertRaises(BizDevError): self.svc.mark_lost(ORG, o["id"], "too short", U1)
        r = self.svc.mark_lost(ORG, o["id"], "Client went with a cheaper firm", U1)
        self.assertEqual((r["stage"], r["probability"], r["weighted"], r["proposals"][0]["status"]), ("LOST", 0, "0.00", "LAPSED"))
        for f in (lambda: self.svc.update_opportunity(ORG, o["id"], {"title": "New title"}, U1), lambda: self.svc.add_activity(ORG, o["id"], dict(type="NOTE", summary="late note"), U1),
                  lambda: self.svc.move_stage(ORG, o["id"], "LEAD", "reopen it", U1), lambda: self.svc.mark_lost(ORG, o["id"], "second time lost?", U1),
                  lambda: self.svc.create_proposal(ORG, o["id"], dict(items=self.items(), valid_until="2026-03-31"), U1)):
            with self.assertRaises(BizDevStateError): f()

    def test_update_fields(self):
        o = self.opp(); r = self.svc.update_opportunity(ORG, o["id"], {"value": "250", "expected_close": "2026-05-01", "title": "Renamed deal"}, U1)
        self.assertEqual((r["value"], r["expected_close"], r["title"], r["currency"]), ("250.00", "2026-05-01", "Renamed deal", "NGN"))
        with self.assertRaises(BizDevError): self.svc.update_opportunity(ORG, o["id"], {"expected_close": "2026-01-01"}, U1)

    def test_flags_overdue_and_stale(self):
        o = self.opp(close="2026-02-20")
        self.assertEqual(self.svc.get_opportunity(ORG, o["id"])["flags"], [])
        self.clock.d = date(2026, 2, 25)
        self.assertEqual(self.svc.get_opportunity(ORG, o["id"])["flags"], ["OVERDUE"])
        self.clock.d = date(2026, 3, 20)  # 33 days since creation on 2026-02-15
        self.assertEqual(sorted(self.svc.get_opportunity(ORG, o["id"])["flags"]), ["OVERDUE", "STALE"])
        self.svc.add_activity(ORG, o["id"], dict(type="CALL", date="2026-03-19", summary="Checked in"), U1)
        self.assertEqual(self.svc.get_opportunity(ORG, o["id"])["flags"], ["OVERDUE"])
        f = self.svc.overview(ORG)["currencies"][0]; self.assertEqual((f["stale"], f["overdue"]), (0, 1))


class Proposals(Base):
    def test_totals_and_validation(self):
        o = self.opp(); o, p = self.prop(o, pct="12.5", price="333.33", qty="3")
        self.assertEqual((p["subtotal"], p["discount_amount"], p["total"], p["version"], p["status"]), ("999.99", "125.00", "874.99", 1, "DRAFT"))
        ok = dict(items=self.items(), valid_until="2026-03-31")
        for bad in (dict(items=[]), dict(discount_pct="100"), dict(discount_pct="-1"), dict(discount_pct="abc"), dict(items=[{"description": "x", "quantity": "0", "unit_price": "5"}]),
                    dict(items=[{"description": "Thing", "quantity": "1", "unit_price": "-5"}]), dict(items=[{"description": "Thing", "quantity": "1", "unit_price": "1,000"}]),
                    dict(valid_until="2026-01-01"), dict(valid_until=""), dict(items=self.items(51))):
            with self.assertRaises(BizDevError, msg=str(bad)): self.svc.create_proposal(ORG, o["id"], {**ok, **bad}, U1)

    def test_discount_within_limit_goes_straight_to_approved(self):
        o = self.opp(); o, p = self.prop(o, pct="10")
        r = self.svc.submit_proposal(ORG, o["id"], p["id"], U1)["proposals"][0]
        self.assertEqual((r["status"], r["limit_at_submission"]), ("APPROVED", "10.00"))

    def test_large_discount_needs_second_person(self):
        o = self.opp(); o, p = self.prop(o, pct="10.01")
        r = self.svc.submit_proposal(ORG, o["id"], p["id"], U1)["proposals"][0]; self.assertEqual(r["status"], "PENDING_APPROVAL")
        with self.assertRaises(BizDevStateError): self.svc.send_proposal(ORG, o["id"], p["id"], U1)
        with self.assertRaises(BizDevForbiddenError): self.svc.approve_proposal(ORG, o["id"], p["id"], U1)
        with self.assertRaises(BizDevForbiddenError): self.svc.reject_proposal(ORG, o["id"], p["id"], U1, "not mine to send back")
        with self.assertRaises(BizDevError): self.svc.reject_proposal(ORG, o["id"], p["id"], U2, "")
        r = self.svc.reject_proposal(ORG, o["id"], p["id"], U2, "Discount too deep for this client")["proposals"][0]; self.assertEqual(r["status"], "REJECTED")
        with self.assertRaises(BizDevStateError): self.svc.send_proposal(ORG, o["id"], p["id"], U1)
        e = self.svc.update_proposal(ORG, o["id"], p["id"], dict(items=self.items(), discount_pct="5", valid_until="2026-03-31"), U1)["proposals"][0]
        self.assertEqual((e["status"], e["discount_pct"]), ("DRAFT", "5.00"))
        self.svc.submit_proposal(ORG, o["id"], p["id"], U1)
        self.assertEqual(self.svc.send_proposal(ORG, o["id"], p["id"], U1)["proposals"][0]["status"], "SENT")

    def test_policy_change_applies_at_submission(self):
        self.svc.set_policy(ORG, {"discount_limit_pct": "0"}, U2)
        o = self.opp(); o, p = self.prop(o, pct="0.01")
        self.assertEqual(self.svc.submit_proposal(ORG, o["id"], p["id"], U1)["proposals"][0]["status"], "PENDING_APPROVAL")

    def test_send_accept_decline_flow(self):
        o = self.opp(); o, p1 = self.sent(o)
        self.assertEqual(o["stage"], "PROPOSAL")
        o, p2 = self.prop(o, price="900"); self.svc.submit_proposal(ORG, o["id"], p2["id"], U1); o = self.svc.send_proposal(ORG, o["id"], p2["id"], U1)
        self.assertEqual([x["status"] for x in o["proposals"]], ["SUPERSEDED", "SENT"])
        with self.assertRaises(BizDevStateError): self.svc.accept_proposal(ORG, o["id"], p1, "this one was replaced", U1)
        with self.assertRaises(BizDevError): self.svc.accept_proposal(ORG, o["id"], p2["id"], "", U1)
        o = self.svc.accept_proposal(ORG, o["id"], p2["id"], "Signed by client", U1)
        self.assertEqual((o["proposals"][1]["status"], o["value"]), ("ACCEPTED", "9000.00"))
        with self.assertRaises(BizDevStateError): self.svc.decline_proposal(ORG, o["id"], p2["id"], "changed mind", U1)

    def test_expiry(self):
        o = self.opp(); o, p = self.prop(o, valid="2026-02-20"); self.svc.submit_proposal(ORG, o["id"], p["id"], U1)
        self.clock.d = date(2026, 2, 21)
        with self.assertRaises(BizDevStateError): self.svc.send_proposal(ORG, o["id"], p["id"], U1)

    def test_sent_proposal_cannot_be_edited(self):
        o = self.opp(); o, pid = self.sent(o)
        with self.assertRaises(BizDevStateError): self.svc.update_proposal(ORG, o["id"], pid, dict(items=self.items(), valid_until="2026-03-31"), U1)
        with self.assertRaises(BizDevStateError): self.svc.submit_proposal(ORG, o["id"], pid, U1)
        with self.assertRaises(BizDevNotFoundError): self.svc.send_proposal(ORG, o["id"], "nope", U1)

    def test_decline_then_new_version(self):
        o = self.opp(); o, pid = self.sent(o)
        with self.assertRaises(BizDevError): self.svc.decline_proposal(ORG, o["id"], pid, "", U1)
        o = self.svc.decline_proposal(ORG, o["id"], pid, "Price too high", U1)
        self.assertEqual(o["proposals"][0]["status"], "DECLINED")
        o, p2 = self.prop(o); self.assertEqual(p2["version"], 2)

    def test_evidence_linked_and_checked(self):
        e = self.w.vault.upload_evidence(ORG, list(EvidenceType)[0], b"signed order form" * 4, "order.pdf", "application/pdf", uploaded_by=U1)
        o = self.opp(); o, p = self.prop(o, evidence_ids=[e.id])
        self.assertEqual(p["evidence"][0]["filename"], "order.pdf")
        with self.assertRaises(BizDevError): self.prop(o, evidence_ids=["missing"])


class Wins(Base):
    def test_win_needs_accepted_proposal_and_second_person(self):
        o = self.opp(value="5")
        with self.assertRaises(BizDevStateError): self.svc.request_win(ORG, o["id"], "", U1)
        o, pid = self.sent(o)
        with self.assertRaises(BizDevStateError): self.svc.request_win(ORG, o["id"], "", U1)
        self.svc.accept_proposal(ORG, o["id"], pid, "Client signed", U1)
        r = self.svc.request_win(ORG, o["id"], "Please confirm", U1)
        self.assertEqual((r["stage"], r["probability"], r["weighted"]), ("WIN_PENDING", 90, "9000.00"))
        for f in (lambda: self.svc.update_opportunity(ORG, o["id"], {"title": "Changed title"}, U1), lambda: self.svc.move_stage(ORG, o["id"], "LEAD", "back please", U1), lambda: self.svc.create_proposal(ORG, o["id"], dict(items=self.items(), valid_until="2026-03-31"), U1)):
            with self.assertRaises(BizDevStateError): f()
        with self.assertRaises(BizDevForbiddenError): self.svc.approve_win(ORG, o["id"], U1)
        with self.assertRaises(BizDevForbiddenError): self.svc.reject_win(ORG, o["id"], U1, "sending myself back")
        r = self.svc.approve_win(ORG, o["id"], U2, "Looks right")
        self.assertEqual((r["stage"], r["value"], r["won_date"], r["probability"]), ("WON", "10000.00", "2026-02-15", 100))
        with self.assertRaises(BizDevStateError): self.svc.approve_win(ORG, o["id"], U3)
        with self.assertRaises(BizDevStateError): self.svc.mark_lost(ORG, o["id"], "can't lose a won deal", U1)

    def test_lost_from_win_pending_and_reject_returns_to_negotiation(self):
        o = self.opp(); o, pid = self.sent(o); self.svc.accept_proposal(ORG, o["id"], pid, "Client signed", U1); self.svc.request_win(ORG, o["id"], "", U1)
        with self.assertRaises(BizDevError): self.svc.reject_win(ORG, o["id"], U2, "")
        r = self.svc.reject_win(ORG, o["id"], U2, "Signature page missing")
        self.assertEqual((r["stage"], r["win_requested_by"]), ("NEGOTIATION", None))
        self.svc.request_win(ORG, o["id"], "", U1)
        self.assertEqual(self.svc.mark_lost(ORG, o["id"], "Client withdrew after signing review", U1)["stage"], "LOST")

    def test_value_taken_from_accepted_proposal(self):
        o = self.opp(value="1"); r = self.won(o=o)
        self.assertEqual(r["value"], "10000.00")


class Targets(Base):
    def test_attainment_and_forecast(self):
        t = self.svc.create_target(ORG, dict(name="Q1 2026 NGN", start="2026-01-01", end="2026-03-31", currency="ngn", amount="100000"), U2)
        self.assertEqual((t["ref"], t["currency"], t["won"], t["attainment_pct"], t["gap"], t["in_period"]), ("T-001", "NGN", "0.00", "0.00", "100000.00", True))
        self.won(account=self.acct(name="A One"))                                   # 10,000 won
        self.won(account=self.acct(name="A Two"), cur="USD")                        # other currency: not counted
        o = self.opp(account=self.acct(name="A Three"), value="40000", close="2026-03-15"); self.svc.move_stage(ORG, o["id"], "QUALIFIED", "", U1)  # 25%
        self.opp(account=self.acct(name="A Four"), value="40000", close="2026-09-01")   # outside the target period
        t = self.svc.list_targets(ORG)[0]
        self.assertEqual((t["won"], t["attainment_pct"], t["gap"], t["weighted_expected"], t["forecast"], t["forecast_pct"]), ("10000.00", "10.00", "90000.00", "10000.00", "20000.00", "20.00"))

    def test_target_validation_and_retire(self):
        base = dict(name="Year goal", start="2026-01-01", end="2026-12-31", currency="USD", amount="5000")
        for k, v in (("name", "ab"), ("amount", "0"), ("amount", "x"), ("end", "2025-12-31"), ("start", "bad"), ("currency", "USDX")):
            with self.assertRaises(BizDevError, msg=k): self.svc.create_target(ORG, {**base, k: v}, U2)
        t = self.svc.create_target(ORG, base, U2)
        with self.assertRaises(BizDevError): self.svc.retire_target(ORG, t["id"], "", U2)
        self.assertEqual(self.svc.retire_target(ORG, t["id"], "Replaced by new plan", U2)["status"], "RETIRED")
        with self.assertRaises(BizDevStateError): self.svc.retire_target(ORG, t["id"], "again please", U2)
        self.assertEqual(self.svc.overview(ORG)["targets"], [])


class Overview(Base):
    def test_figures_per_currency_never_mixed(self):
        a = self.acct()
        self.opp(account=a, value="1000"); o2 = self.opp(account=a, value="2000", title="Second deal"); self.svc.move_stage(ORG, o2["id"], "QUALIFIED", "", U1)
        self.opp(account=a, value="500", cur="USD", title="Dollar deal")
        lost = self.opp(account=a, value="700", title="Lost deal"); self.svc.mark_lost(ORG, lost["id"], "Client cancelled the project", U1)
        self.won(account=a, title="Big deal")
        ov = self.svc.overview(ORG); f = {c["currency"]: c for c in ov["currencies"]}
        self.assertEqual(sorted(f), ["NGN", "USD"])
        n = f["NGN"]; self.assertEqual((n["open_count"], n["open_value"], n["weighted"], n["won_count"], n["won_value"], n["lost_count"], n["lost_value"]), (2, "3000.00", "600.00", 1, "10000.00", 1, "700.00"))
        self.assertEqual((n["win_rate_pct"], n["win_rate_value_pct"]), ("50.00", "93.46"))
        self.assertEqual((f["USD"]["open_value"], f["USD"]["win_rate_pct"]), ("500.00", None))
        self.assertEqual(ov["counts"]["accounts"], 1); self.assertTrue(ov["limitations"])

    def test_empty(self):
        ov = self.svc.overview(ORG); self.assertEqual((ov["currencies"], ov["targets"], ov["counts"]["open"]), ([], [], 0))

    def test_list_filters(self):
        a, b = self.acct(), self.acct(name="Other Client Ltd"); self.opp(account=a); self.opp(account=b, title="Second one")
        self.assertEqual(len(self.svc.list_opportunities(ORG)), 2); self.assertEqual(len(self.svc.list_opportunities(ORG, account_id=b["id"])), 1)
        self.assertEqual(self.svc.list_opportunities(ORG, stage="won"), [])
        with self.assertRaises(BizDevError): self.svc.list_opportunities(ORG, stage="nope")
        self.assertEqual(self.svc.get_account(ORG, a["id"])["opportunities"][0]["ref"], "O-001")


class Policy(Base):
    def test_defaults_and_validation(self):
        p = self.svc.get_policy(ORG); self.assertEqual((p["discount_limit_pct"], p["stale_days"], p["probabilities"]["PROPOSAL"]), ("10.00", 30, 50))
        for bad in (dict(probabilities={"WON": 100}), dict(probabilities={"LEAD": 101}), dict(probabilities={"LEAD": -1}), dict(probabilities={"LEAD": "x"}), dict(probabilities={"LEAD": True}),
                    dict(probabilities={"LEAD": 60}), dict(probabilities=[1]), dict(discount_limit_pct="101"), dict(discount_limit_pct="-1"), dict(discount_limit_pct="abc"), dict(stale_days=0), dict(stale_days=366), dict(stale_days="x")):
            with self.assertRaises(BizDevError, msg=str(bad)): self.svc.set_policy(ORG, bad, U2)
        q = self.svc.set_policy(ORG, dict(probabilities={"LEAD": 5, "QUALIFIED": 20}, discount_limit_pct="15", stale_days=14), U2)
        self.assertEqual((q["probabilities"]["LEAD"], q["probabilities"]["QUALIFIED"], q["probabilities"]["NEGOTIATION"], q["discount_limit_pct"], q["stale_days"], q["updated_by"]), (5, 20, 75, "15.00", 14, U2))

    def test_probabilities_drive_forecast(self):
        self.svc.set_policy(ORG, dict(probabilities={"LEAD": 20}), U2); o = self.opp(value="1000")
        self.assertEqual(self.svc.get_opportunity(ORG, o["id"])["weighted"], "200.00")


class Reports(Base):
    def make(self, title="Q1 pipeline"):
        self.won(account=self.acct(name="Client A")); self.opp(account=self.acct(name="=Evil Co"), title="=HYPERLINK(1)", value="3000")
        return self.svc.create_report(ORG, "ngn", title, U1)

    def test_lifecycle_two_person_and_freeze(self):
        r = self.make(); self.assertEqual((r["ref"], r["status"], r["has_snapshot"]), ("R-001", "DRAFT", False))
        with self.assertRaises(BizDevStateError): self.svc.export_csv(ORG, r["id"], U1)
        r = self.svc.submit_report(ORG, r["id"], U1); fp = r["fingerprint"]; self.assertEqual((r["status"], r["version"]), ("SUBMITTED", 1))
        self.opp(account=self.acct(name="Late Client"), value="999999")  # changes after freezing must not appear
        self.assertEqual(self.svc.get_report(ORG, r["id"])["fingerprint"], fp); self.assertEqual(len(self.svc.get_report(ORG, r["id"])["snapshot"]["opportunities"]), 2)
        with self.assertRaises(BizDevForbiddenError): self.svc.approve_report(ORG, r["id"], U1)
        with self.assertRaises(BizDevError): self.svc.reject_report(ORG, r["id"], U2, "")
        self.assertEqual(self.svc.reject_report(ORG, r["id"], U2, "Add the dollar deals")["status"], "REJECTED")
        r = self.svc.submit_report(ORG, r["id"], U3); self.assertEqual((r["version"], len(r["snapshot"]["opportunities"])), (2, 3))
        self.assertEqual(self.svc.approve_report(ORG, r["id"], U2)["status"], "APPROVED")
        with self.assertRaises(BizDevStateError): self.svc.submit_report(ORG, r["id"], U1)

    def test_csv_export_confidential_and_neutralised(self):
        r = self.make(); self.svc.submit_report(ORG, r["id"], U1); self.svc.approve_report(ORG, r["id"], U2)
        out = self.svc.export_csv(ORG, r["id"], U3); self.assertEqual((out["filename"], out["content_type"]), ("R-001-pipeline-v1.csv", "text/csv; charset=utf-8"))
        rows = list(csv.reader(io.StringIO(out["content"]))); self.assertTrue(rows[0][0].startswith("CONFIDENTIAL"))
        text = out["content"]
        for h in ("PIPELINE BY STAGE", "OPPORTUNITIES", "TARGETS", "LIMITATIONS"): self.assertIn(h, text)
        self.assertIn("'=HYPERLINK(1)", text); self.assertIn("'=Evil Co", text)
        self.assertFalse(any(c.startswith("=") for row in rows for c in row))
        self.assertTrue(any(e[0] == "BD_REPORT_EXPORTED" for e in self.events))

    def test_tamper_blocks_export(self):
        r = self.make(); self.svc.submit_report(ORG, r["id"], U1); self.svc.approve_report(ORG, r["id"], U2)
        doc = self.w.store.get("bd_report", f"{ORG}:{r['id']}", for_update=True); doc["snapshot"]["figures"]["won_value"] = "999999.00"; self.w.store.put("bd_report", f"{ORG}:{r['id']}", doc, org_id=ORG)
        with self.assertRaises(BizDevStateError): self.svc.export_csv(ORG, r["id"], U3)

    def test_report_needs_opportunities_in_currency(self):
        with self.assertRaises(BizDevError): self.svc.create_report(ORG, "NGN", "Empty pipeline", U1)
        self.opp(); with_usd = self.svc.create_report(ORG, "NGN", "Has data", U1); self.assertEqual(with_usd["currency"], "NGN")
        with self.assertRaises(BizDevError): self.svc.create_report(ORG, "USD", "No dollars", U1)
        with self.assertRaises(BizDevError): self.svc.create_report(ORG, "NGN", "ab", U1)


class Isolation(Base):
    def test_other_org_sees_nothing_and_cannot_touch(self):
        a = self.acct(); o = self.opp(account=a); self.svc.create_target(ORG, dict(name="Goal one", start="2026-01-01", end="2026-12-31", currency="NGN", amount="1"), U2)
        r = self.svc.create_report(ORG, "NGN", "Our report", U1)
        self.assertEqual((self.svc.list_accounts(OTHER), self.svc.list_opportunities(OTHER), self.svc.list_targets(OTHER), self.svc.list_reports(OTHER)), ([], [], [], []))
        self.assertEqual(self.svc.overview(OTHER)["currencies"], [])
        for f in (lambda: self.svc.get_account(OTHER, a["id"]), lambda: self.svc.get_opportunity(OTHER, o["id"]), lambda: self.svc.get_report(OTHER, r["id"]), lambda: self.svc.mark_lost(OTHER, o["id"], "not your deal at all", U1),
                  lambda: self.svc.create_opportunity(OTHER, dict(account_id=a["id"], title="Cross org", currency="NGN", value="5", expected_close="2026-03-01"), U1)):
            with self.assertRaises(BizDevNotFoundError): f()
        self.assertEqual(self.svc.options(OTHER)["accounts"], [])


class Audit(Base):
    def test_every_write_is_logged(self):
        o = self.won(); acts = {e[0] for e in self.events}
        for a in ("BD_ACCOUNT_CREATED", "BD_OPPORTUNITY_CREATED", "BD_PROPOSAL_CREATED", "BD_PROPOSAL_SUBMITTED", "BD_PROPOSAL_SENT", "BD_PROPOSAL_ACCEPTED", "BD_WIN_REQUESTED", "BD_WIN_CONFIRMED"): self.assertIn(a, acts)
        self.svc.set_policy(ORG, {"stale_days": 20}, U2); self.assertIn("BD_POLICY_SET", {e[0] for e in self.events})


class Roles(unittest.TestCase):
    def test_role_matrix(self):
        has = lambda r, p: p in ROLE_PERMISSIONS[r]
        for r in (Role.OWNER, Role.FINANCE_OFFICER, Role.MANAGER): self.assertTrue(has(r, BD_PREPARE) and has(r, BD_APPROVE), r)
        self.assertTrue(has(Role.ACCOUNTANT, BD_PREPARE) and not has(Role.ACCOUNTANT, BD_APPROVE))
        self.assertTrue(has(Role.APPROVER, BD_APPROVE) and not has(Role.APPROVER, BD_PREPARE))
        for r in (Role.REVIEWER, Role.AUDITOR, Role.ADMINISTRATOR): self.assertFalse(has(r, BD_PREPARE) or has(r, BD_APPROVE), r)
        self.assertTrue(has(Role.REVIEWER, REPORTING_READ))


if __name__ == "__main__":
    unittest.main()
