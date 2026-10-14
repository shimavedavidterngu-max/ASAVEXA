"""Risk indicators and resilience: indicators and readings, loss events, business processes, continuity tests, two-person rules, policy, isolation, audit, permissions."""
import ast
import os
import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace

from analysis_fixture import ORG, OTHER, World
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.permissions import AUDIT_READ, RESIL_APPROVE, RESIL_PREPARE, ROLE_PERMISSIONS
from asavexa.resilience.errors import ResilienceError, ResilienceForbiddenError, ResilienceNotFoundError, ResilienceStateError
from asavexa.resilience.service import ResilienceService, criticality, rate, refnum
from decimal import Decimal

U1, U2, U3 = "user-1", "user-2", "user-3"   # U1 prepares, U2 prepares too, U3 approves


class Clock:
    def __init__(self): self.d = date(2026, 2, 15)
    def __call__(self): return datetime(self.d.year, self.d.month, self.d.day, 9, tzinfo=timezone.utc)


class Vault:
    def get_evidence(self, org, i):
        if org == ORG and i in ("ev1", "ev2"): return SimpleNamespace(id=i, original_filename=f"{i}.pdf", file_hash="h" * 64)
        raise LookupError(i)


class Base(unittest.TestCase):
    def setUp(self):
        self.w = World(); self.clock = Clock(); self.events = []
        self.svc = ResilienceService(self.w.store, Vault(), log=lambda *a: self.events.append(a), now=self.clock)

    def kri(self, actor=U1, active=False, **kw):
        d = dict(name=f"Overdue invoices {len(self.events)}{kw.get('n', '')}", description="Share of invoices more than 30 days overdue", unit="%", direction="HIGHER_IS_WORSE", amber="10", red="20", owner_name="Ada Obi", review_days=30)
        d.update({k: v for k, v in kw.items() if k != "n"}); k = self.svc.rs_propose_kri(ORG, d, actor)
        return self.svc.rs_approve_kri(ORG, k["id"], U3) if active else k

    def reading(self, k, value="5", on="2026-02-10", actor=U1, confirm=False, **kw):
        d = dict(value=value, as_of=on); d.update(kw); k = self.svc.rs_record_reading(ORG, k["id"], d, actor)
        if confirm: k = self.svc.rs_confirm_reading(ORG, k["id"], next(r for r in k["readings"] if r["as_of"] == on)["id"], U3)
        return k

    def loss(self, actor=U1, **kw):
        d = dict(title="Payment sent to the wrong account", description="A payment was sent to a supplier with the same name", category="PROCESS", kind="LOSS", occurred_on="2026-02-01", discovered_on="2026-02-03", amount="1500.50", currency="ngn")
        d.update(kw); return self.svc.rs_record_loss(ORG, d, actor)

    def process(self, actor=U1, active=False, **kw):
        d = dict(name=f"Payroll processing {len(self.events)}{kw.get('n', '')}", description="Monthly payroll calculation and payment", owner_name="Ben Eze", rto_hours=24, rpo_hours=4,
                 impact_financial="HIGH", impact_legal="MEDIUM", impact_reputation="LOW"); d.update({k: v for k, v in kw.items() if k != "n"}); p = self.svc.rs_propose_process(ORG, d, actor)
        return self.svc.rs_approve_process(ORG, p["id"], U3) if active else p

    def drill(self, p, actor=U2, **kw):
        d = dict(process_id=p["id"], drill_type="FAILOVER", scenario="The payroll server is lost and the backup site takes over", performed_on="2026-02-10", achieved_recovery_hours=12,
                 achieved_data_loss_hours=2, outcome="The backup site took over and payroll ran on time"); d.update(kw); return self.svc.rs_record_drill(ORG, d, actor)


class Helpers(unittest.TestCase):
    def test_refnum(self): self.assertEqual(sorted([{"ref": "KR-010"}, {"ref": "KR-002"}], key=refnum)[0]["ref"], "KR-002"); self.assertEqual(refnum({"ref": "x"}), 0)

    def test_rating_both_directions_and_boundaries(self):
        D = Decimal
        for v, e in (("9.9999", "GREEN"), ("10", "AMBER"), ("19.9999", "AMBER"), ("20", "RED"), ("-5", "GREEN")): self.assertEqual(rate("HIGHER_IS_WORSE", D("10"), D("20"), D(v)), e, v)
        for v, e in (("101", "GREEN"), ("100", "AMBER"), ("51", "AMBER"), ("50", "RED"), ("0", "RED")): self.assertEqual(rate("LOWER_IS_WORSE", D("100"), D("50"), D(v)), e, v)

    def test_criticality(self):
        self.assertEqual(criticality({"a": "LOW", "b": "HIGH", "c": "LOW"}), "HIGH"); self.assertEqual(criticality({"a": "LOW", "b": "MEDIUM", "c": "LOW"}), "MEDIUM"); self.assertEqual(criticality({"a": "LOW"}), "LOW")


class Policy(Base):
    def test_defaults_set_and_validation(self):
        self.assertEqual(self.svc.rs_get_policy(ORG)["drill_days"], 365)
        self.assertEqual(self.svc.rs_set_policy(ORG, {"drill_days": 90, "loss_review_days": 7}, U3)["loss_review_days"], 7)
        for bad in ({"drill_days": 10}, {"drill_days": 1096}, {"loss_review_days": 0}, {"loss_review_days": "x"}, {"drill_days": True}, {"drill_days": "-5"}):
            with self.assertRaises(ResilienceError, msg=str(bad)): self.svc.rs_set_policy(ORG, bad, U3)


class Kris(Base):
    def test_propose_validates_and_numbers_last(self):
        bad = [dict(name="abc"), dict(description="short"), dict(unit=""), dict(direction="SIDEWAYS"), dict(amber="x"), dict(red="1.23456"), dict(amber="20", red="10"), dict(amber="10", red="10"),
               dict(direction="LOWER_IS_WORSE"), dict(owner_name="A"), dict(review_days=0), dict(review_days=366), dict(risk_id="nope")]
        for i, b in enumerate(bad):
            with self.assertRaises(ResilienceError, msg=str(b)): self.kri(n=f"v{i}", **b)
        self.assertEqual(self.svc.rs_overview(ORG)["counts"]["kris_active"], 0); self.assertEqual(self.kri(n="ok")["ref"], "KR-001")

    def test_lower_is_worse_thresholds(self):
        k = self.kri(direction="LOWER_IS_WORSE", amber="100", red="50", unit="days", n="l"); self.assertEqual((k["amber"], k["red"]), ("100", "50"))

    def test_duplicate_name_refused_until_retired_or_rejected(self):
        k = self.kri(name="Overdue invoices share")
        with self.assertRaises(ResilienceStateError): self.kri(name="overdue INVOICES share")
        self.svc.rs_reject_kri(ORG, k["id"], "Thresholds are not agreed yet", U3); self.assertEqual(self.kri(name="Overdue invoices share")["ref"], "KR-002")

    def test_approval_needs_a_different_person_and_reject_needs_a_reason(self):
        k = self.kri()
        with self.assertRaises(ResilienceForbiddenError): self.svc.rs_approve_kri(ORG, k["id"], U1)
        with self.assertRaises(ResilienceError): self.svc.rs_reject_kri(ORG, k["id"], "short", U3)
        with self.assertRaises(ResilienceError): self.svc.rs_approve_kri(ORG, k["id"], U3, "tiny")
        a = self.svc.rs_approve_kri(ORG, k["id"], U3); self.assertEqual((a["status"], a["decided_by"]), ("ACTIVE", U3))
        for f in (lambda: self.svc.rs_approve_kri(ORG, k["id"], U3), lambda: self.svc.rs_reject_kri(ORG, k["id"], "Not needed any longer", U3)):
            with self.assertRaises(ResilienceStateError): f()

    def test_readings_need_an_active_indicator(self):
        k = self.kri()
        with self.assertRaises(ResilienceStateError): self.reading(k)

    def test_reading_validation_and_note_rule(self):
        k = self.kri(active=True)
        for bad in (dict(value="x"), dict(value=""), dict(value="1.23456"), dict(on="2026-13-01"), dict(on="2026-03-30"), dict(note="tiny")):
            with self.assertRaises(ResilienceError, msg=str(bad)): self.reading(k, **{**{"value": "5"}, **{("as_of" if kk == "on" else kk): v for kk, v in bad.items()}} if False else {}) if False else self.svc.rs_record_reading(ORG, k["id"], {"value": bad.get("value", "5"), "as_of": bad.get("on", "2026-02-10"), **({"note": bad["note"]} if "note" in bad else {})}, U1)
        with self.assertRaises(ResilienceError): self.reading(k, value="12")                      # amber needs a note
        with self.assertRaises(ResilienceError): self.reading(k, value="25", note="short")
        self.assertEqual(self.reading(k, value="12", note="Two large customers paid late")["readings"][0]["rating"], "AMBER")
        self.assertEqual(self.reading(k, value="25", on="2026-02-11", note="Three large customers paid late")["readings"][1]["rating"], "RED")

    def test_one_reading_per_date_until_rejected(self):
        k = self.kri(active=True); k = self.reading(k)
        with self.assertRaises(ResilienceStateError): self.reading(k, value="6")
        self.svc.rs_reject_reading(ORG, k["id"], k["readings"][0]["id"], "Typed against the wrong day", U3); self.assertEqual(len(self.reading(k, value="6")["readings"]), 2)

    def test_confirmation_rules_and_latest_rating(self):
        k = self.kri(active=True); k = self.reading(k, value="5", on="2026-02-01")
        self.assertIsNone(k["rating"]); self.assertTrue(k["stale"]); self.assertEqual(k["pending_readings"], 1)
        with self.assertRaises(ResilienceForbiddenError): self.svc.rs_confirm_reading(ORG, k["id"], k["readings"][0]["id"], U1)
        with self.assertRaises(ResilienceNotFoundError): self.svc.rs_confirm_reading(ORG, k["id"], "nope", U3)
        k = self.svc.rs_confirm_reading(ORG, k["id"], k["readings"][0]["id"], U3); self.assertEqual((k["rating"], k["latest"]["value"]), ("GREEN", "5"))
        with self.assertRaises(ResilienceStateError): self.svc.rs_confirm_reading(ORG, k["id"], k["readings"][0]["id"], U3)
        k = self.reading(k, value="25", on="2026-02-12", note="Three large customers paid late")
        self.assertEqual(k["rating"], "GREEN")                                                       # an unconfirmed reading changes nothing
        k = self.svc.rs_confirm_reading(ORG, k["id"], k["readings"][-1]["id"], U3); self.assertEqual(k["rating"], "RED")
        k = self.reading(k, value="3", on="2026-02-05", confirm=True); self.assertEqual((k["rating"], k["latest"]["as_of"]), ("RED", "2026-02-12"))   # latest by date, not by entry order

    def test_stale_follows_the_indicator_interval(self):
        k = self.kri(active=True, review_days=10); k = self.reading(k, on="2026-02-10", confirm=True); self.assertFalse(k["stale"])
        self.clock.d = date(2026, 2, 21); self.assertTrue(self.svc.rs_get_kri(ORG, k["id"])["stale"])

    def test_reject_reading_needs_a_reason_and_a_different_person(self):
        k = self.reading(self.kri(active=True)); rid = k["readings"][0]["id"]
        with self.assertRaises(ResilienceForbiddenError): self.svc.rs_reject_reading(ORG, k["id"], rid, "Typed against the wrong day", U1)
        with self.assertRaises(ResilienceError): self.svc.rs_reject_reading(ORG, k["id"], rid, "short", U3)
        r = self.svc.rs_reject_reading(ORG, k["id"], rid, "Typed against the wrong day", U3); self.assertEqual(r["readings"][0]["status"], "REJECTED"); self.assertIsNone(r["rating"])

    def test_retire(self):
        k = self.reading(self.kri(active=True))
        with self.assertRaises(ResilienceStateError): self.svc.rs_retire_kri(ORG, k["id"], "No longer measured by us", U3)    # a reading is waiting
        k = self.svc.rs_confirm_reading(ORG, k["id"], k["readings"][0]["id"], U3)
        with self.assertRaises(ResilienceError): self.svc.rs_retire_kri(ORG, k["id"], "short", U3)
        self.assertEqual(self.svc.rs_retire_kri(ORG, k["id"], "No longer measured by us", U3)["status"], "RETIRED")
        with self.assertRaises(ResilienceStateError): self.reading(k, on="2026-02-12")
        with self.assertRaises(ResilienceStateError): self.svc.rs_retire_kri(ORG, k["id"], "No longer measured by us", U3)

    def test_risk_link_is_checked_per_company(self):
        self.w.store.put("grc_risk", f"{ORG}:r1", {"id": "r1", "org": ORG, "ref": "R-001", "status": "ASSESSED", "title": "Late payment"}, org_id=ORG)
        self.w.store.put("grc_risk", f"{OTHER}:r2", {"id": "r2", "org": OTHER, "ref": "R-001", "status": "ASSESSED"}, org_id=OTHER)
        self.assertEqual(self.kri(risk_id="r1", n="a")["risk_ref"], "R-001")
        with self.assertRaises(ResilienceError): self.kri(risk_id="r2", n="b")
        self.assertEqual([r["id"] for r in self.svc.rs_options(ORG)["risks"]], ["r1"])


class Losses(Base):
    def test_loss_recorded_with_exact_amount_and_currency(self):
        e = self.loss(); self.assertEqual((e["ref"], e["amount"], e["currency"], e["status"]), ("LE-001", "1500.50", "NGN", "RECORDED")); self.assertEqual(self.loss(amount="10")["amount"], "10.00")

    def test_validation(self):
        bad = [dict(title="abc"), dict(description="short"), dict(category="X"), dict(kind="X"), dict(occurred_on="2026-03-30"), dict(discovered_on="2026-03-30"), dict(occurred_on="2026-02-05", discovered_on="2026-02-03"),
               dict(amount="0"), dict(amount="-5"), dict(amount="1.234"), dict(amount=""), dict(currency="NG"), dict(currency="N1A"), dict(evidence_ids=["nope"]), dict(risk_id="nope")]
        for b in bad:
            with self.assertRaises(ResilienceError, msg=str(b)): self.loss(**b)
        self.assertEqual(self.loss()["ref"], "LE-001")

    def test_near_miss_has_no_amount(self):
        n = self.loss(kind="NEAR_MISS", amount=None, currency=None); self.assertEqual((n["kind"], n["amount"]), ("NEAR_MISS", None))
        with self.assertRaises(ResilienceError): self.loss(kind="NEAR_MISS", amount="5.00")
        with self.assertRaises(ResilienceError): self.loss(kind="NEAR_MISS", amount=None, currency="NGN")

    def test_review_needs_a_different_person_and_both_notes(self):
        e = self.loss(); d = dict(cause="The supplier name was almost identical", lesson="Payments now need the bank account checked by a second person")
        with self.assertRaises(ResilienceForbiddenError): self.svc.rs_review_loss(ORG, e["id"], d, U1)
        with self.assertRaises(ResilienceError): self.svc.rs_review_loss(ORG, e["id"], {**d, "cause": "short"}, U3)
        with self.assertRaises(ResilienceError): self.svc.rs_review_loss(ORG, e["id"], {**d, "lesson": "Too short a lesson"}, U3)
        r = self.svc.rs_review_loss(ORG, e["id"], d, U3); self.assertEqual((r["status"], r["reviewed_by"], r["reviewed_on"]), ("REVIEWED", U3, "2026-02-15"))
        for f in (lambda: self.svc.rs_review_loss(ORG, e["id"], d, U3), lambda: self.svc.rs_void_loss(ORG, e["id"], "Entered twice by mistake", U3)):
            with self.assertRaises(ResilienceStateError): f()

    def test_void(self):
        e = self.loss()
        with self.assertRaises(ResilienceForbiddenError): self.svc.rs_void_loss(ORG, e["id"], "Entered twice by mistake", U1)
        with self.assertRaises(ResilienceError): self.svc.rs_void_loss(ORG, e["id"], "short", U3)
        self.assertEqual(self.svc.rs_void_loss(ORG, e["id"], "Entered twice by mistake", U3)["status"], "VOIDED")
        with self.assertRaises(ResilienceStateError): self.svc.rs_void_loss(ORG, e["id"], "Entered twice by mistake", U3)

    def test_totals_per_currency_exclude_voided_and_near_misses(self):
        a = self.loss(amount="100.10", currency="NGN"); self.loss(amount="0.20", currency="NGN"); self.loss(amount="50.00", currency="USD"); self.loss(kind="NEAR_MISS", amount=None, currency=None)
        v = self.loss(amount="999.00", currency="NGN"); self.svc.rs_void_loss(ORG, v["id"], "Entered twice by mistake", U3)
        self.assertEqual(self.svc.rs_overview(ORG)["loss_totals"], [{"currency": "NGN", "total": "100.30"}, {"currency": "USD", "total": "50.00"}])
        c = self.svc.rs_overview(ORG)["counts"]; self.assertEqual((c["losses"], c["near_misses"]), (3, 1))
        self.assertEqual(len(self.svc.rs_list_losses(ORG, kind="NEAR_MISS")), 1); self.assertEqual(len(self.svc.rs_list_losses(ORG, status="VOIDED")), 1)

    def test_review_overdue_follows_the_window(self):
        e = self.loss(); self.assertFalse(self.svc.rs_get_loss(ORG, e["id"])["review_overdue"])
        self.clock.d = date(2026, 3, 5); self.assertTrue(self.svc.rs_get_loss(ORG, e["id"])["review_overdue"])
        self.svc.rs_set_policy(ORG, {"loss_review_days": 30}, U3); self.assertFalse(self.svc.rs_get_loss(ORG, e["id"])["review_overdue"])
        self.assertEqual(self.loss(evidence_ids=["ev1", "ev1"])["evidence"][0]["evidence_id"], "ev1")


class Processes(Base):
    def test_propose_validation_criticality_and_ref(self):
        p = self.process(); self.assertEqual((p["ref"], p["criticality"], p["status"], p["drill_due"]), ("BP-001", "HIGH", "PROPOSED", False))
        self.assertEqual(self.process(impact_financial="LOW", impact_legal="LOW", impact_reputation="MEDIUM", n="m")["criticality"], "MEDIUM")
        bad = [dict(name="abc"), dict(description="short"), dict(owner_name="A"), dict(rto_hours=0), dict(rto_hours=8761), dict(rto_hours="x"), dict(rpo_hours=-1), dict(impact_legal="X"), dict(impact_financial=None), dict(dependencies="abc")]
        for i, b in enumerate(bad):
            with self.assertRaises(ResilienceError, msg=str(b)): self.process(n=f"v{i}", **b)
        self.assertEqual(self.process(n="z", rpo_hours=0)["rpo_hours"], 0)

    def test_duplicate_and_approval(self):
        p = self.process(name="Payroll processing run")
        with self.assertRaises(ResilienceStateError): self.process(name="PAYROLL processing run")
        with self.assertRaises(ResilienceForbiddenError): self.svc.rs_approve_process(ORG, p["id"], U1)
        with self.assertRaises(ResilienceError): self.svc.rs_reject_process(ORG, p["id"], "short", U3)
        self.assertEqual(self.svc.rs_approve_process(ORG, p["id"], U3)["status"], "APPROVED")
        with self.assertRaises(ResilienceStateError): self.svc.rs_approve_process(ORG, p["id"], U3)

    def test_rejected_process_frees_the_name(self):
        p = self.process(name="Payroll processing run"); self.svc.rs_reject_process(ORG, p["id"], "The objectives are not agreed", U3)
        self.assertEqual(self.process(name="Payroll processing run")["ref"], "BP-002")

    def test_retire_blocked_while_a_test_waits(self):
        p = self.process(active=True); t = self.drill(p)
        with self.assertRaises(ResilienceStateError): self.svc.rs_retire_process(ORG, p["id"], "The process has been outsourced", U3)
        self.svc.rs_approve_drill(ORG, t["id"], U3)
        with self.assertRaises(ResilienceError): self.svc.rs_retire_process(ORG, p["id"], "short", U3)
        self.assertEqual(self.svc.rs_retire_process(ORG, p["id"], "The process has been outsourced", U3)["status"], "RETIRED")
        with self.assertRaises(ResilienceStateError): self.drill(p)

    def test_only_approved_process_can_be_tested(self):
        with self.assertRaises(ResilienceStateError): self.drill(self.process())


class Drills(Base):
    def test_met_when_within_both_objectives_and_snapshots_them(self):
        p = self.process(active=True); t = self.drill(p); self.assertEqual((t["ref"], t["result"], t["rto_met"], t["rpo_met"], t["rto_hours"], t["rpo_hours"]), ("DR-001", "MET", True, True, 24, 4))
        t = self.drill(p, achieved_recovery_hours=24, achieved_data_loss_hours=4, performed_on="2026-02-11"); self.assertEqual(t["result"], "MET")      # equal to the objective is met

    def test_not_met_needs_a_follow_up_and_either_objective_counts(self):
        p = self.process(active=True)
        for kw in (dict(achieved_recovery_hours=25), dict(achieved_data_loss_hours=5)):
            with self.assertRaises(ResilienceError): self.drill(p, **kw)
            t = self.drill(p, follow_up="Buy a second backup line and retest in March", **kw); self.assertEqual(t["result"], "NOT_MET")
        self.assertFalse(self.drill(p, follow_up="Buy a second backup line and retest", achieved_recovery_hours=25)["rto_met"])

    def test_validation(self):
        p = self.process(active=True)
        bad = [dict(drill_type="X"), dict(scenario="short"), dict(performed_on="2026-03-30"), dict(performed_on="x"), dict(achieved_recovery_hours=-1), dict(achieved_recovery_hours="x"), dict(achieved_data_loss_hours=9000),
               dict(outcome="short"), dict(evidence_ids=["nope"]), dict(process_id="nope")]
        for b in bad:
            with self.assertRaises((ResilienceError, ResilienceNotFoundError), msg=str(b)): self.drill(p, **b)
        self.assertEqual(self.svc.rs_overview(ORG)["counts"]["drills_approved"], 0); self.assertEqual(self.drill(p)["ref"], "DR-001")

    def test_objective_changes_do_not_rewrite_history(self):
        p = self.process(active=True); t = self.drill(p, achieved_recovery_hours=20)
        self.svc.rs_approve_drill(ORG, t["id"], U3); self.svc.rs_retire_process(ORG, p["id"], "Replaced with a faster target", U3)
        p2 = self.process(active=True, name="Payroll processing faster", rto_hours=8); self.assertEqual(self.svc.rs_get_drill(ORG, t["id"])["result"], "MET"); self.assertEqual(self.drill(p2, achieved_recovery_hours=20, follow_up="Move payroll to the second site")["result"], "NOT_MET")

    def test_approval_rules(self):
        p = self.process(active=True); t = self.drill(p, actor=U2)
        with self.assertRaises(ResilienceForbiddenError): self.svc.rs_approve_drill(ORG, t["id"], U2)
        with self.assertRaises(ResilienceError): self.svc.rs_reject_drill(ORG, t["id"], "short", U3)
        a = self.svc.rs_approve_drill(ORG, t["id"], U3); self.assertEqual((a["status"], a["decided_by"]), ("APPROVED", U3))
        with self.assertRaises(ResilienceStateError): self.svc.rs_approve_drill(ORG, t["id"], U3)
        t2 = self.drill(p, achieved_recovery_hours=30, follow_up="Buy a second backup line and retest", performed_on="2026-02-11")
        with self.assertRaises(ResilienceError): self.svc.rs_approve_drill(ORG, t2["id"], U3)                       # a miss needs an approval note
        self.assertEqual(self.svc.rs_approve_drill(ORG, t2["id"], U3, "Agreed follow-up; retest in March")["result"], "NOT_MET")
        t3 = self.drill(p, performed_on="2026-02-12"); r = self.svc.rs_reject_drill(ORG, t3["id"], "The outcome does not match the evidence", U3); self.assertEqual(r["status"], "REJECTED")

    def test_process_tested_state_and_due(self):
        p = self.process(active=True); self.assertTrue(self.svc.rs_get_process(ORG, p["id"])["drill_due"])
        t = self.drill(p); self.assertTrue(self.svc.rs_get_process(ORG, p["id"])["drill_due"])                       # not approved yet
        self.svc.rs_approve_drill(ORG, t["id"], U3); v = self.svc.rs_get_process(ORG, p["id"]); self.assertEqual((v["drill_due"], v["last_tested_on"], v["last_result"], v["drills"]), (False, "2026-02-10", "MET", 1))
        self.clock.d = date(2027, 3, 1); self.assertTrue(self.svc.rs_get_process(ORG, p["id"])["drill_due"])
        self.assertEqual(len(self.svc.rs_list_drills(ORG, process_id=p["id"])), 1); self.assertEqual(len(self.svc.rs_list_drills(ORG, status="RECORDED")), 0)


class Overview(Base):
    def test_attention(self):
        k = self.kri(active=True); self.reading(k, value="25", on="2026-02-12", note="Three large customers paid late", confirm=True)
        k2 = self.kri(active=True, n="b"); self.reading(k2, value="12", on="2026-02-12", note="Two large customers paid late", confirm=True)
        k3 = self.kri(active=True, n="c"); self.reading(k3, value="5", on="2026-02-12"); self.kri(n="d")
        self.loss(); self.process(); p = self.process(active=True, n="e"); t = self.drill(p, achieved_recovery_hours=30, follow_up="Buy a second backup line and retest"); self.svc.rs_approve_drill(ORG, t["id"], U3, "Agreed follow-up; retest in March")
        self.drill(self.process(active=True, n="f"))
        kinds = {a["kind"]: a["count"] for a in self.svc.rs_overview(ORG)["attention"]}
        self.assertEqual((kinds["KRIS_RED"], kinds["KRIS_AMBER"], kinds["KRIS_STALE"], kinds["READINGS_TO_CONFIRM"], kinds["PROPOSALS_TO_APPROVE"], kinds["TESTS_NOT_MET"], kinds["TESTS_TO_APPROVE"]), (1, 1, 1, 1, 2, 1, 1))
        self.assertEqual(kinds["PROCESSES_NEVER_TESTED"], 1); self.assertNotIn("LOSSES_REVIEW_OVERDUE", kinds)
        self.clock.d = date(2026, 3, 20); self.assertIn("LOSSES_REVIEW_OVERDUE", {a["kind"] for a in self.svc.rs_overview(ORG)["attention"]})
        c = self.svc.rs_overview(ORG)["counts"]; self.assertEqual((c["kris_active"], c["processes_approved"], c["processes_high"]), (3, 2, 2))

    def test_empty(self):
        o = self.svc.rs_overview(ORG); self.assertEqual((o["attention"], o["loss_totals"]), ([], [])); self.assertTrue(o["limitations"])


class Isolation(Base):
    def test_other_company_sees_nothing_and_cannot_touch(self):
        k = self.reading(self.kri(active=True)); e = self.loss(); p = self.process(active=True); t = self.drill(p)
        for lst in (self.svc.rs_list_kris, self.svc.rs_list_losses, self.svc.rs_list_processes, self.svc.rs_list_drills): self.assertEqual(lst(OTHER), [])
        for f in (lambda: self.svc.rs_get_kri(OTHER, k["id"]), lambda: self.svc.rs_get_loss(OTHER, e["id"]), lambda: self.svc.rs_get_process(OTHER, p["id"]), lambda: self.svc.rs_get_drill(OTHER, t["id"]),
                  lambda: self.svc.rs_confirm_reading(OTHER, k["id"], k["readings"][0]["id"], U3), lambda: self.svc.rs_approve_drill(OTHER, t["id"], U3),
                  lambda: self.svc.rs_record_drill(OTHER, {"process_id": p["id"]}, U2), lambda: self.svc.rs_void_loss(OTHER, e["id"], "Entered twice by mistake", U3)):
            with self.assertRaises(ResilienceNotFoundError): f()
        self.assertEqual(self.svc.rs_overview(OTHER)["loss_totals"], [])

    def test_same_names_allowed_in_each_company(self):
        self.kri(name="Overdue invoices share"); d = dict(name="Overdue invoices share", description="Share of invoices more than 30 days overdue", unit="%", direction="HIGHER_IS_WORSE", amber="10", red="20", owner_name="Ada", review_days=30)
        self.assertEqual(self.svc.rs_propose_kri(OTHER, d, U1)["ref"], "KR-001")


class Audit(Base):
    def test_every_write_logged_without_content(self):
        k = self.kri(active=True); k = self.reading(k, value="25", note="Three large customers paid late", confirm=True); e = self.loss(); self.svc.rs_review_loss(ORG, e["id"], dict(cause="The supplier name was almost identical", lesson="Payments now need the bank account checked by a second person"), U3)
        p = self.process(active=True); t = self.drill(p); self.svc.rs_approve_drill(ORG, t["id"], U3); self.svc.rs_set_policy(ORG, {"drill_days": 100}, U3); self.svc.rs_retire_kri(ORG, k["id"], "No longer measured by us", U3)
        l2 = self.loss(); self.svc.rs_void_loss(ORG, l2["id"], "Entered twice by mistake", U3)
        acts = [x[0] for x in self.events]
        for a in ("RESILIENCE_KRI_PROPOSED", "RESILIENCE_KRI_APPROVED", "RESILIENCE_READING_RECORDED", "RESILIENCE_READING_CONFIRMED", "RESILIENCE_KRI_RETIRED", "RESILIENCE_LOSS_RECORDED", "RESILIENCE_LOSS_REVIEWED",
                  "RESILIENCE_LOSS_VOIDED", "RESILIENCE_PROCESS_PROPOSED", "RESILIENCE_PROCESS_APPROVED", "RESILIENCE_DRILL_RECORDED", "RESILIENCE_DRILL_APPROVED", "RESILIENCE_POLICY_SET"): self.assertIn(a, acts)
        blob = " ".join(str(x) for x in self.events)
        for secret in ("wrong account", "almost identical", "large customers", "Entered twice", "backup site", "1500.50"): self.assertNotIn(secret, blob)

    def test_failed_actions_are_not_logged(self):
        with self.assertRaises(ResilienceError): self.loss(title="abc")
        with self.assertRaises(ResilienceError): self.kri(amber="30")
        self.assertEqual(self.events, [])


class Permissions(unittest.TestCase):
    def test_roles(self):
        has = lambda r, p: p in ROLE_PERMISSIONS[r]
        for r in (Role.OWNER, Role.ADMINISTRATOR, Role.MANAGER, Role.AUDITOR): self.assertTrue(has(r, RESIL_PREPARE), r)
        for r in (Role.OWNER, Role.APPROVER, Role.MANAGER): self.assertTrue(has(r, RESIL_APPROVE), r)
        for r in (Role.ACCOUNTANT, Role.REVIEWER, Role.EXTERNAL_AUDITOR, Role.READ_ONLY, Role.DONOR, Role.REGULATOR, Role.INVESTOR_REVIEWER): self.assertFalse(has(r, RESIL_PREPARE) or has(r, RESIL_APPROVE), r)

    def test_anyone_who_can_prepare_or_approve_can_view(self):
        for r, perms in ROLE_PERMISSIONS.items():
            if RESIL_PREPARE in perms or RESIL_APPROVE in perms: self.assertIn(AUDIT_READ, perms, r)


class RouterGuards(unittest.TestCase):
    SRC = os.path.join(os.path.dirname(__file__), "..", "src", "asavexa", "api", "routers", "resilience.py")

    def test_every_write_has_the_right_guard(self):
        tree = ast.parse(open(self.SRC).read()); named = {"_prepare": "RESIL_PREPARE", "_approve": "RESIL_APPROVE"}; g = {}
        for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.decorator_list]:
            verbs, guards = set(), set()
            for dec in fn.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute): verbs.add(dec.func.attr)
                for kw in getattr(dec, "keywords", []):
                    if kw.arg == "dependencies": guards |= {named[e.id] for e in kw.value.elts if isinstance(e, ast.Name) and e.id in named}
            g[fn.name] = (verbs, guards)
        approve = {"set_policy", "approve_kri", "reject_kri", "retire_kri", "confirm_reading", "reject_reading", "review_loss", "void_loss", "approve_process", "reject_process", "retire_process", "approve_drill", "reject_drill"}
        prepare = {"propose_kri", "record_reading", "record_loss", "propose_process", "record_drill"}
        for n in approve: self.assertEqual(g[n][1], {"RESIL_APPROVE"}, n)
        for n in prepare: self.assertEqual(g[n][1], {"RESIL_PREPARE"}, n)
        for n, (verbs, guards) in g.items():
            if verbs == {"get"}: self.assertEqual(guards, set(), n)
            else: self.assertIn(n, approve | prepare, f"{n} writes but has no resilience guard")
        src = open(self.SRC).read(); self.assertIn("dependencies=[Depends(require_permission(AUDIT_READ))]", src); self.assertNotIn("org_id", src)


if __name__ == "__main__":
    unittest.main()
