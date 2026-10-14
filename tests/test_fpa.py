"""Planning and KPIs: KPI ownership and traceability, readings and review, target judgement, forecast stamping and accuracy, policy, isolation, audit."""
import ast
import os
import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from analysis_fixture import ORG, OTHER, World
from asavexa.fpa.errors import FpaError, FpaForbiddenError, FpaNotFoundError, FpaStateError
from asavexa.fpa.service import FpaService, add_months, judge, next_period_end, period_end_for
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.permissions import FPA_APPROVE, FPA_PREPARE, REPORTING_READ, ROLE_PERMISSIONS

U1, U2, U3, U4, U5 = "user-1", "user-2", "user-3", "user-4", "user-5"
MEMBERS = {U1, U2, U3, U4, U5}
RECORDERS = {U1, U3, U4, U5}                  # U2 is an approver only


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
        self.svc = FpaService(self.w.store, Vault(), is_member=lambda o, u: u in MEMBERS, can_record=lambda o, u: u in RECORDERS, log=lambda *a: self.events.append(a), now=self.clock)

    def kpi(self, name="Gross margin", approve=True, accept=True, **kw):
        d = dict(name=name, description="Share of revenue left after direct costs", unit="AMOUNT", currency="NGN", direction="HIGHER_BETTER", frequency="MONTHLY", owner=U3, data_source="Monthly management accounts, gross profit line",
                 method="Revenue less direct costs, from the posted ledger", target="1000.00", effective_from="2026-01-01"); d.update(kw)
        k = self.svc.define_kpi(ORG, d, U1)
        if approve: k = self.svc.approve_kpi(ORG, k["id"], U2)
        if accept and approve: k = self.svc.accept_kpi_ownership(ORG, k["id"], k["owner"])
        return k

    def read(self, k, value="1000.00", pe="2026-01-31", actor=U3, **kw):
        d = dict(period_end=pe, value=value, source_note="Taken from the January management accounts"); d.update(kw)
        return self.svc.record_kpi_reading(ORG, k["id"], d, actor)

    def fc(self, metric="Revenue", value="100.00", pe="2026-03-31", unit="AMOUNT", currency="NGN", actor=U1, **kw):
        d = dict(metric=metric, unit=unit, currency=currency, period_end=pe, value=value, basis="Run-rate of the last three months"); d.update(kw)
        if unit != "AMOUNT": d.pop("currency")
        return self.svc.register_forecast(ORG, d, actor)

    def confirmed(self, value, actual, metric="Revenue", pe="2026-03-31", currency="NGN", lead=20, forecaster=U1):
        keep = self.clock.d; pe_d = date.fromisoformat(pe)
        self.clock.d = pe_d - timedelta(days=lead); f = self.fc(metric, value, pe, currency=currency, actor=forecaster)
        self.clock.d = pe_d + timedelta(days=1)
        self.svc.record_forecast_actual(ORG, f["id"], dict(value=actual, source_note="Closed management accounts for the month"), U3)
        out = self.svc.confirm_forecast_actual(ORG, f["id"], U2); self.clock.d = keep; return out


class Helpers(unittest.TestCase):
    def test_references_sort_by_number_so_the_thousandth_comes_after_the_999th(self):
        from asavexa.fpa.service import refnum
        self.assertEqual(sorted([{"ref": "KP-1000"}, {"ref": "KP-999"}, {"ref": "KP-002"}], key=refnum), [{"ref": "KP-002"}, {"ref": "KP-999"}, {"ref": "KP-1000"}])
        self.assertEqual(refnum({}), 0)

    def test_periods(self):
        self.assertEqual(period_end_for(date(2026, 2, 3), "MONTHLY"), date(2026, 2, 28)); self.assertEqual(period_end_for(date(2024, 2, 3), "MONTHLY"), date(2024, 2, 29))
        self.assertEqual(period_end_for(date(2026, 2, 3), "QUARTERLY"), date(2026, 3, 31)); self.assertEqual(period_end_for(date(2026, 12, 31), "QUARTERLY"), date(2026, 12, 31))
        self.assertEqual(next_period_end(date(2026, 1, 31), "MONTHLY"), date(2026, 2, 28)); self.assertEqual(next_period_end(date(2026, 12, 31), "MONTHLY"), date(2027, 1, 31))
        self.assertEqual(next_period_end(date(2026, 12, 31), "QUARTERLY"), date(2027, 3, 31)); self.assertEqual(next_period_end(date(2026, 3, 31), "QUARTERLY"), date(2026, 6, 30))
        self.assertEqual(add_months(date(2024, 2, 29), 12), date(2025, 2, 28)); self.assertEqual(next_period_end(date(2025, 6, 30), "ANNUAL"), date(2026, 6, 30))

    def test_judgement_boundaries_are_exact(self):
        t = Decimal("1000")
        for v, d, want in (("1000", "HIGHER_BETTER", "ON_TARGET"), ("1100", "HIGHER_BETTER", "ON_TARGET"), ("900", "HIGHER_BETTER", "WATCH"), ("899.99", "HIGHER_BETTER", "OFF_TARGET"),
                           ("1000", "LOWER_BETTER", "ON_TARGET"), ("900", "LOWER_BETTER", "ON_TARGET"), ("1100", "LOWER_BETTER", "WATCH"), ("1100.01", "LOWER_BETTER", "OFF_TARGET")):
            self.assertEqual(judge(Decimal(v), t, d, 10)["status"], want, (v, d))
        self.assertEqual(judge(Decimal("900"), t, "HIGHER_BETTER", 10)["shortfall_pct"], "10.00")
        self.assertEqual(judge(Decimal("0"), Decimal("0"), "HIGHER_BETTER", 10)["status"], "ON_TARGET")
        self.assertEqual(judge(Decimal("-1"), Decimal("0"), "HIGHER_BETTER", 10), {"status": "OFF_TARGET", "shortfall_pct": None})
        self.assertEqual(judge(Decimal("-1000"), Decimal("-1000"), "LOWER_BETTER", 10)["status"], "ON_TARGET")
        self.assertEqual(judge(Decimal("-1100"), Decimal("-1000"), "HIGHER_BETTER", 10)["status"], "WATCH")           # shortfall is a share of the size of the target


class Policy(Base):
    def test_defaults_set_and_validation(self):
        p = self.svc.get_fpa_policy(ORG); self.assertEqual((p["watch_pct"], p["grace_days"], p["accuracy_pct"], p["min_items"]), (10, 15, 10, 3))
        p = self.svc.set_fpa_policy(ORG, dict(watch_pct=5, grace_days=0, accuracy_pct=100, min_items=1), U2); self.assertEqual((p["watch_pct"], p["grace_days"], p["accuracy_pct"], p["min_items"], p["updated_by"]), (5, 0, 100, 1, U2))
        for bad in (dict(watch_pct=51), dict(watch_pct=-1), dict(watch_pct="x"), dict(watch_pct=True), dict(grace_days=91), dict(accuracy_pct=101), dict(min_items=0), dict(min_items=51)):
            with self.assertRaises(FpaError, msg=bad): self.svc.set_fpa_policy(ORG, bad, U2)
        self.assertEqual(self.svc.get_fpa_policy(ORG)["watch_pct"], 5)

    def test_new_kpis_fix_the_margin_when_defined(self):
        self.svc.set_fpa_policy(ORG, dict(watch_pct=20), U2); k = self.kpi(); self.assertEqual(k["watch_pct"], 20)
        self.svc.set_fpa_policy(ORG, dict(watch_pct=1), U2); self.assertEqual(self.svc.get_kpi(ORG, k["id"])["watch_pct"], 20)
        self.assertEqual(self.kpi("Another", watch_pct=7)["watch_pct"], 7)


class KpiDefinition(Base):
    def test_define_approve_and_accept(self):
        k = self.kpi(approve=False); self.assertEqual((k["ref"], k["status"], k["owner"], k["owner_accepted"], k["target"]), ("KP-001", "DRAFT", U3, False, "1000.00"))
        for who, exc in ((U1, FpaForbiddenError), (U3, FpaForbiddenError)):
            with self.assertRaises(exc, msg=who): self.svc.approve_kpi(ORG, k["id"], who)
        k = self.svc.approve_kpi(ORG, k["id"], U2, "Target agreed with the board"); self.assertEqual((k["status"], k["approved_by"]), ("ACTIVE", U2))
        with self.assertRaises(FpaStateError): self.svc.approve_kpi(ORG, k["id"], U4)
        with self.assertRaises(FpaForbiddenError): self.svc.accept_kpi_ownership(ORG, k["id"], U1)
        k = self.svc.accept_kpi_ownership(ORG, k["id"], U3); self.assertTrue(k["owner_accepted"])
        with self.assertRaises(FpaStateError): self.svc.accept_kpi_ownership(ORG, k["id"], U3)

    def test_the_owner_cannot_approve_their_own_target(self):
        k = self.kpi(approve=False, owner=U3)
        with self.assertRaises(FpaForbiddenError) as e: self.svc.approve_kpi(ORG, k["id"], U3)
        self.assertIn("owner who is measured against", str(e.exception))

    def test_validation(self):
        base = dict(name="Cash days", description="Days of cash in hand", unit="DAYS", direction="LOWER_BETTER", frequency="QUARTERLY", owner=U3, data_source="Treasury balances report", method="Cash divided by daily spend",
                    target="30", effective_from="2026-01-01")
        for bad in (dict(name="ab"), dict(description="no"), dict(unit="NOPE"), dict(unit="AMOUNT"), dict(unit="AMOUNT", currency="N"), dict(currency="NGN"), dict(direction="SIDEWAYS"), dict(frequency="WEEKLY"),
                    dict(owner="stranger"), dict(owner=U2), dict(owner=None), dict(data_source="short"), dict(method="short"), dict(target="1.5"), dict(target="x"), dict(target="1e30"), dict(target=None),
                    dict(effective_from="soon"), dict(watch_pct=51), dict(watch_pct="x")):
            with self.assertRaises(FpaError, msg=bad): self.svc.define_kpi(ORG, {**base, **bad}, U1)
        self.assertEqual(self.svc.define_kpi(ORG, base, U1)["ref"], "KP-001")
        self.assertEqual(self.svc.define_kpi(ORG, {**base, "name": "Ratio one", "unit": "RATIO", "target": "1.2500"}, U1)["target"], "1.2500")
        with self.assertRaises(FpaError): self.svc.define_kpi(ORG, {**base, "name": "Ratio two", "unit": "RATIO", "target": "1.25001"}, U1)

    def test_an_owner_who_cannot_record_is_refused_with_the_reason(self):
        with self.assertRaises(FpaError) as e: self.kpi(approve=False, owner=U2)
        self.assertIn("can record KPI readings", str(e.exception))

    def test_duplicate_names_ignoring_capitals_unless_retired(self):
        k = self.kpi()
        with self.assertRaises(FpaStateError): self.kpi("gross MARGIN", approve=False)
        self.svc.retire_kpi(ORG, k["id"], "Replaced by a new definition", U2); self.assertEqual(self.kpi("Gross margin", approve=False)["ref"], "KP-002")

    def test_refused_requests_do_not_use_up_reference_numbers(self):
        with self.assertRaises(FpaError): self.kpi(approve=False, target="x")
        self.assertEqual(self.kpi("Good one", approve=False)["ref"], "KP-001")
        with self.assertRaises(FpaError): self.fc(value="x")
        self.assertEqual(self.fc()["ref"], "FC-001")

    def test_reassign_owner(self):
        k = self.kpi()
        with self.assertRaises(FpaStateError): self.svc.reassign_kpi_owner(ORG, k["id"], U3, "Same person again", U2)
        with self.assertRaises(FpaError): self.svc.reassign_kpi_owner(ORG, k["id"], U3 + "x", "Not a member", U2)
        with self.assertRaises(FpaError): self.svc.reassign_kpi_owner(ORG, k["id"], U2, "Approver cannot record", U1)
        with self.assertRaises(FpaError): self.svc.reassign_kpi_owner(ORG, k["id"], U4, "no", U2)
        k = self.svc.reassign_kpi_owner(ORG, k["id"], U4, "Moved to the budget team", U2); self.assertEqual((k["owner"], k["owner_accepted"], len(k["owner_history"])), (U4, False, 2))
        with self.assertRaises(FpaStateError): self.read(k, actor=U4)                  # must accept first
        with self.assertRaises(FpaForbiddenError): self.svc.accept_kpi_ownership(ORG, k["id"], U3)
        self.svc.accept_kpi_ownership(ORG, k["id"], U4); self.assertEqual(self.read(k, actor=U4)["status"], "RECORDED")

    def test_the_approver_of_a_target_cannot_become_its_owner(self):
        k = self.kpi(); S = FpaService(self.w.store, Vault(), is_member=lambda o, u: True, can_record=lambda o, u: True, now=self.clock)       # an approver who can also record
        with self.assertRaises(FpaForbiddenError): S.reassign_kpi_owner(ORG, k["id"], U2, "Taking this over myself", U1)

    def test_retire(self):
        k = self.kpi()
        with self.assertRaises(FpaError): self.svc.retire_kpi(ORG, k["id"], "", U2)
        self.assertEqual(self.svc.retire_kpi(ORG, k["id"], "No longer reported", U2)["status"], "RETIRED")
        for fn in (lambda: self.svc.retire_kpi(ORG, k["id"], "again again", U2), lambda: self.read(k), lambda: self.svc.accept_kpi_ownership(ORG, k["id"], U3), lambda: self.svc.reassign_kpi_owner(ORG, k["id"], U4, "Too late now", U2)):
            with self.assertRaises(FpaStateError): fn()
        self.assertEqual(self.svc.list_kpis(ORG, status="RETIRED")[0]["ref"], "KP-001")


class Readings(Base):
    def test_only_an_approved_accepted_kpi_and_only_its_owner(self):
        d = self.kpi(approve=False)
        with self.assertRaises(FpaStateError): self.read(d)
        a = self.svc.approve_kpi(ORG, d["id"], U2)
        with self.assertRaises(FpaStateError): self.read(a)                           # owner has not accepted
        self.svc.accept_kpi_ownership(ORG, a["id"], U3)
        with self.assertRaises(FpaForbiddenError): self.read(a, actor=U1)
        r = self.read(a); self.assertEqual((r["ref"], r["status"], r["value"], r["judgement"], r["traceable"]), ("KR-001", "RECORDED", "1000.00", "ON_TARGET", False))

    def test_period_rules(self):
        m = self.kpi(); q = self.kpi("Quarterly one", frequency="QUARTERLY"); a = self.kpi("Annual one", frequency="ANNUAL")
        self.assertEqual(self.read(m, pe="2026-01-31")["period_end"], "2026-01-31")
        for pe in ("2026-01-30", "2026-02-27", "nope", "2025-12-31", "2026-03-31"):          # not a month end / before the start / in the future
            with self.assertRaises(FpaError, msg=pe): self.read(m, pe=pe)
        with self.assertRaises(FpaError): self.read(q, pe="2026-01-31")
        self.clock.d = date(2026, 4, 2); self.assertEqual(self.read(q, pe="2026-03-31")["period_end"], "2026-03-31")
        self.assertEqual(self.read(a, pe="2026-02-14")["period_end"], "2026-02-14")           # an annual period may end on any date

    def test_value_and_source(self):
        k = self.kpi()
        for bad in (dict(value="x"), dict(value=None), dict(value="1.234"), dict(value="1e30"), dict(value=True), dict(source_note="short"), dict(source_note="")):
            with self.assertRaises(FpaError, msg=bad): self.read(k, **bad)
        c = self.kpi("Count one", unit="COUNT", currency=None, target="5")
        with self.assertRaises(FpaError): self.read(c, value="2.5")
        self.assertEqual(self.read(c, value="-3")["value"], "-3")

    def test_documents_must_exist_and_their_hashes_are_kept(self):
        k = self.kpi(); r = self.read(k, evidence_ids=["ev1", "ev1", "ev2"]); self.assertTrue(r["traceable"]); self.assertEqual([e["evidence_id"] for e in r["evidence"]], ["ev1", "ev2"]); self.assertEqual(r["evidence"][0]["file_hash"], "h" * 64)
        with self.assertRaises(FpaError): self.read(k, pe="2026-01-31", evidence_ids=["nope"], correction_note="Trying with a missing file")
        self.assertEqual(self.svc.get_kpi(ORG, k["id"])["untraceable"], 0)

    def test_a_correction_supersedes_and_keeps_the_old_reading(self):
        k = self.kpi(); a = self.read(k, value="900.00")
        with self.assertRaises(FpaError): self.read(k, value="950.00")                       # same period, no reason
        with self.assertRaises(FpaError): self.read(k, value="950.00", correction_note="short")
        b = self.read(k, value="950.00", correction_note="The first figure left out one invoice"); v = self.svc.get_kpi(ORG, k["id"])
        self.assertEqual([(r["ref"], r["status"]) for r in v["readings"]], [("KR-002", "RECORDED"), ("KR-001", "SUPERSEDED")]); self.assertEqual(v["readings"][1]["superseded_by"], b["id"])
        self.assertEqual((v["latest"]["value"], v["live_readings"]), ("950.00", 1))
        with self.assertRaises(FpaStateError): self.svc.review_kpi_reading(ORG, k["id"], a["id"], U2)                  # a superseded reading cannot be reviewed

    def test_review_by_someone_else_and_rejection(self):
        k = self.kpi(); r = self.read(k); self.assertTrue(self.svc.get_kpi(ORG, k["id"])["unreviewed"])
        with self.assertRaises(FpaForbiddenError): self.svc.review_kpi_reading(ORG, k["id"], r["id"], U3)
        with self.assertRaises(FpaForbiddenError): self.svc.reject_kpi_reading(ORG, k["id"], r["id"], "my own reading", U3)
        r = self.svc.review_kpi_reading(ORG, k["id"], r["id"], U2, "Agreed to the ledger"); self.assertEqual((r["status"], r["reviewed_by"]), ("REVIEWED", U2)); self.assertFalse(self.svc.get_kpi(ORG, k["id"])["unreviewed"])
        with self.assertRaises(FpaStateError): self.svc.review_kpi_reading(ORG, k["id"], r["id"], U4)
        self.clock.d = date(2026, 3, 1); w = self.read(k, pe="2026-02-28", value="800.00")
        with self.assertRaises(FpaError): self.svc.reject_kpi_reading(ORG, k["id"], w["id"], "", U2)
        self.assertEqual(self.svc.reject_kpi_reading(ORG, k["id"], w["id"], "Does not agree to the ledger", U2)["status"], "REJECTED")
        self.assertEqual(self.svc.get_kpi(ORG, k["id"])["latest"]["period_end"], "2026-01-31")                          # a rejected reading is not the latest
        self.assertEqual(self.read(k, pe="2026-02-28", value="990.00")["status"], "RECORDED")                           # the owner can record that period again without a correction reason

    def test_a_reading_belongs_to_its_kpi(self):
        k, j = self.kpi(), self.kpi("Other one"); r = self.read(k)
        with self.assertRaises(FpaNotFoundError): self.svc.review_kpi_reading(ORG, j["id"], r["id"], U2)

    def test_judgement_on_the_page_model(self):
        k = self.kpi(); self.read(k, value="900.00"); v = self.svc.get_kpi(ORG, k["id"])
        self.assertEqual((v["judgement"], v["latest"]["shortfall_pct"], v["latest"]["gap"]), ("WATCH", "10.00", "-100.00")); self.assertIn("On target when at or above 1000.00", v["meaning"])
        self.assertEqual(self.svc.get_kpi(ORG, self.kpi("Never read")["id"])["judgement"], "NOT_MEASURED")

    def test_due_dates_and_overdue(self):
        k = self.kpi(); v = self.svc.get_kpi(ORG, k["id"]); self.assertEqual((v["next_period_end"], v["due"], v["overdue"]), ("2026-01-31", "2026-02-15", False))
        self.clock.d = date(2026, 2, 16); self.assertTrue(self.svc.get_kpi(ORG, k["id"])["overdue"])
        self.read(k); v = self.svc.get_kpi(ORG, k["id"]); self.assertEqual((v["next_period_end"], v["due"], v["overdue"]), ("2026-02-28", "2026-03-15", False))
        q = self.kpi("Quarterly one", frequency="QUARTERLY"); self.assertEqual(self.svc.get_kpi(ORG, q["id"])["next_period_end"], "2026-03-31")
        a = self.kpi("Annual one", frequency="ANNUAL", effective_from="2025-01-01"); self.assertEqual(self.svc.get_kpi(ORG, a["id"])["next_period_end"], "2025-12-31")
        self.read(a, pe="2025-12-31"); self.assertEqual(self.svc.get_kpi(ORG, a["id"])["next_period_end"], "2026-12-31")
        self.assertFalse(self.svc.get_kpi(ORG, self.kpi("Draft one", approve=False)["id"])["can_record"])

    def test_list_filters(self):
        self.kpi(); self.kpi("Second", owner=U4, approve=False)
        self.assertEqual([k["ref"] for k in self.svc.list_kpis(ORG)], ["KP-001", "KP-002"]); self.assertEqual([k["ref"] for k in self.svc.list_kpis(ORG, status="DRAFT")], ["KP-002"]); self.assertEqual([k["ref"] for k in self.svc.list_kpis(ORG, owner=U4)], ["KP-002"])


class Forecasts(Base):
    def test_the_system_stamps_today_and_nobody_can_back_date(self):
        f = self.fc(made_on="2020-01-01"); self.assertEqual((f["ref"], f["made_on"], f["lead_days"], f["status"], f["forecaster"]), ("FC-001", "2026-02-15", 44, "OPEN", U1))
        self.clock.d = date(2026, 3, 1)
        with self.assertRaises(FpaError) as e: self.fc(pe="2026-02-28")
        self.assertIn("cannot be back-dated", str(e.exception)); self.assertEqual(self.fc(pe="2026-03-01")["lead_days"], 0)

    def test_validation_and_links(self):
        k = self.kpi()
        for bad in (dict(metric="ab"), dict(unit="NOPE"), dict(currency="N"), dict(period_end="soon"), dict(value="x"), dict(value="1.234"), dict(basis="short"), dict(kpi_id="missing")):
            with self.assertRaises((FpaError, FpaNotFoundError), msg=bad): self.fc(**bad)
        with self.assertRaises(FpaError): self.svc.register_forecast(ORG, dict(metric="Headcount", unit="COUNT", currency="NGN", period_end="2026-03-31", value="5", basis="Planned hiring"), U1)
        self.assertEqual(self.fc(kpi_id=k["id"])["kpi_ref"], "KP-001")
        with self.assertRaises(FpaError): self.fc(kpi_id=k["id"], currency="USD")                         # same unit and currency as the KPI
        with self.assertRaises(FpaError): self.fc(kpi_id=k["id"], unit="COUNT", value="5")
        other = self.kpi("In dollars", currency="USD")
        with self.assertRaises(FpaError): self.fc(kpi_id=other["id"])

    def test_withdraw(self):
        f = self.fc()
        with self.assertRaises(FpaForbiddenError): self.svc.withdraw_forecast(ORG, f["id"], "Not my forecast", U4)
        with self.assertRaises(FpaError): self.svc.withdraw_forecast(ORG, f["id"], "", U1)
        self.assertEqual(self.svc.withdraw_forecast(ORG, f["id"], "Replaced by a better one", U1)["status"], "WITHDRAWN")
        with self.assertRaises(FpaStateError): self.svc.withdraw_forecast(ORG, f["id"], "Again and again", U1)

    def test_actual_confirm_reject_flow(self):
        f = self.fc(pe="2026-02-28"); A = dict(value="90.00", source_note="Closed management accounts for February")
        with self.assertRaises(FpaStateError): self.svc.record_forecast_actual(ORG, f["id"], A, U3)                       # period not over
        self.clock.d = date(2026, 3, 1)
        with self.assertRaises(FpaForbiddenError): self.svc.record_forecast_actual(ORG, f["id"], A, U1)                  # not the forecaster
        for bad in (dict(value="x"), dict(source_note="short"), dict(evidence_ids=["nope"])):
            with self.assertRaises(FpaError, msg=bad): self.svc.record_forecast_actual(ORG, f["id"], {**A, **bad}, U3)
        f2 = self.svc.record_forecast_actual(ORG, f["id"], {**A, "evidence_ids": ["ev1"]}, U3); self.assertEqual((f2["status"], f2["error"]["direction"], f2["actual"]["evidence"][0]["file_hash"]), ("ACTUAL_RECORDED", "OVER", "h" * 64))
        for who in (U3, U1):
            with self.assertRaises(FpaForbiddenError, msg=who): self.svc.confirm_forecast_actual(ORG, f["id"], who)
        with self.assertRaises(FpaStateError): self.svc.record_forecast_actual(ORG, f["id"], A, U4)                      # already recorded
        r = self.svc.reject_forecast_actual(ORG, f["id"], "The figure is from the wrong month", U2); self.assertEqual((r["status"], r["actual"]), ("OPEN", None)); self.assertIn("ACTUAL_REJECTED", [h["event"] for h in r["history"]])
        self.svc.record_forecast_actual(ORG, f["id"], {**A, "value": "95.00"}, U4); c = self.svc.confirm_forecast_actual(ORG, f["id"], U2, "Agreed"); self.assertEqual((c["status"], c["actual"]["confirmed_by"]), ("CONFIRMED", U2))
        with self.assertRaises(FpaStateError): self.svc.confirm_forecast_actual(ORG, f["id"], U2)
        with self.assertRaises(FpaStateError): self.svc.withdraw_forecast(ORG, f["id"], "Too late for this", U1)

    def test_error_figures(self):
        f = self.confirmed("100.00", "80.00"); e = f["error"]; self.assertEqual((e["error"], e["abs_error"], e["pct_error"], e["direction"], e["within"]), ("20.00", "20.00", "25.00", "OVER", False))
        e = self.confirmed("90.00", "100.00", metric="Under")["error"]; self.assertEqual((e["error"], e["pct_error"], e["direction"], e["within"]), ("-10.00", "10.00", "UNDER", True))         # exactly at the band is within
        e = self.confirmed("100.00", "100.00", metric="Exact")["error"]; self.assertEqual((e["direction"], e["within"]), ("EXACT", True))
        e = self.confirmed("5.00", "0.00", metric="Zero")["error"]; self.assertEqual((e["pct_error"], e["within"]), (None, False))
        e = self.confirmed("0.00", "0.00", metric="Zeroes")["error"]; self.assertEqual((e["pct_error"], e["within"]), (None, True))

    def test_the_band_is_fixed_when_registered(self):
        self.svc.set_fpa_policy(ORG, dict(accuracy_pct=50), U2); f = self.confirmed("100.00", "80.00"); self.assertTrue(f["error"]["within"])
        self.svc.set_fpa_policy(ORG, dict(accuracy_pct=1), U2); self.assertTrue(self.svc.get_forecast(ORG, f["id"])["error"]["within"])

    def test_actual_due_flag(self):
        f = self.fc(pe="2026-02-28"); self.assertFalse(f["actual_due"]); self.clock.d = date(2026, 3, 1); self.assertTrue(self.svc.get_forecast(ORG, f["id"])["actual_due"])


class Accuracy(Base):
    def test_wape_bias_and_hit_rate_are_exact(self):
        self.confirmed("100.00", "90.00"); self.confirmed("200.00", "220.00"); self.confirmed("50.00", "50.00")
        g = self.svc.forecast_accuracy_report(ORG)["groups"][0]
        self.assertEqual((g["metric"], g["n"], g["wape"], g["bias"], g["over"], g["under"], g["exact"], g["within"], g["hit_rate"], g["mean_abs_error"], g["average_lead_days"], g["enough"]),
                         ("Revenue", 3, "8.33", "-2.78", 1, 1, 1, 2, "66.67", "10.00", "20.0", True))

    def test_few_items_are_not_called_meaningful(self):
        self.confirmed("100.00", "90.00"); self.assertFalse(self.svc.forecast_accuracy_report(ORG)["groups"][0]["enough"])
        self.svc.set_fpa_policy(ORG, dict(min_items=1), U2); self.assertTrue(self.svc.forecast_accuracy_report(ORG)["groups"][0]["enough"])

    def test_only_confirmed_actuals_count(self):
        self.confirmed("100.00", "90.00"); self.clock.d = date(2026, 1, 5); f = self.fc(pe="2026-01-31"); w = self.fc(pe="2026-01-31", metric="Gone"); self.svc.withdraw_forecast(ORG, w["id"], "Not needed any more", U1)
        self.clock.d = date(2026, 2, 1); self.svc.record_forecast_actual(ORG, f["id"], dict(value="1.00", source_note="Closed management accounts"), U3)
        r = self.svc.forecast_accuracy_report(ORG); self.assertEqual((r["counted"], r["awaiting_confirmation"], len(r["groups"])), (1, 1, 1))

    def test_units_and_currencies_are_never_mixed(self):
        self.confirmed("100.00", "100.00"); self.confirmed("100.00", "50.00", currency="USD"); self.confirmed("10.00", "10.00", metric="revenue")
        keys = [(g["metric"].lower(), g["currency"], g["n"]) for g in self.svc.forecast_accuracy_report(ORG)["groups"]]
        self.assertEqual(sorted(keys), [("revenue", "NGN", 2), ("revenue", "USD", 1)])                                      # capitals ignored, currencies kept apart

    def test_minimum_lead_time_filter(self):
        self.confirmed("100.00", "90.00", lead=20); self.confirmed("100.00", "90.00", pe="2026-04-30", lead=5)
        r = self.svc.forecast_accuracy_report(ORG, 10); self.assertEqual((r["counted"], r["excluded_short_lead"], r["groups"][0]["n"]), (1, 1, 1))
        self.assertEqual(self.svc.forecast_accuracy_report(ORG)["counted"], 2)
        with self.assertRaises(FpaError): self.svc.forecast_accuracy_report(ORG, -1)
        with self.assertRaises(FpaError): self.svc.forecast_accuracy_report(ORG, "x")

    def test_zero_actuals_give_no_percentage(self):
        self.confirmed("5.00", "0.00"); g = self.svc.forecast_accuracy_report(ORG)["groups"][0]; self.assertEqual((g["wape"], g["bias"]), (None, None))

    def test_by_forecaster(self):
        self.confirmed("100.00", "100.00", forecaster=U1); self.confirmed("100.00", "50.00", forecaster=U4, metric="Other")
        p = {x["forecaster"]: x for x in self.svc.forecast_accuracy_report(ORG)["forecasters"]}; self.assertEqual((p[U1]["hit_rate"], p[U4]["hit_rate"], p[U4]["over"]), ("100.00", "0.00", 1))


class Overview(Base):
    def test_empty_and_options(self):
        o = self.svc.fpa_overview(ORG); self.assertEqual((o["attention"], o["counts"]["kpis"]), ([], 0)); self.assertTrue(o["limitations"])
        k = self.kpi(); op = self.svc.fpa_options(ORG); self.assertEqual(op["kpis"][0]["id"], k["id"]); self.assertIn("AMOUNT", [u["id"] for u in op["units"]])

    def test_attention_list(self):
        self.kpi("Draft one", approve=False); self.kpi("Unaccepted", accept=False, owner=U4)
        a = self.kpi("Late one"); b = self.kpi("Off target"); self.read(b, value="500.00"); c = self.kpi("Close one"); self.read(c, value="950.00")
        self.clock.d = date(2026, 2, 16); self.read(a, pe="2026-01-31", evidence_ids=["ev1"])                               # a traced reading
        self.clock.d = date(2026, 4, 1); f = self.fc(pe="2026-04-30") ; self.clock.d = date(2026, 5, 2); g = self.fc(pe="2026-05-31"); self.clock.d = date(2026, 6, 1)
        self.svc.record_forecast_actual(ORG, g["id"], dict(value="1.00", source_note="Closed management accounts"), U3)
        kinds = {x["kind"] for x in self.svc.fpa_overview(ORG)["attention"]}
        self.assertEqual({"KPIS_PENDING", "OWNERSHIP_PENDING", "KPI_OVERDUE", "KPI_OFF_TARGET", "KPI_WATCH", "READINGS_TO_REVIEW", "READINGS_UNTRACED", "ACTUALS_DUE", "ACTUALS_TO_CONFIRM"} - kinds, set(), kinds)

    def test_bias_warning_needs_enough_items_and_a_big_bias(self):
        for v in ("200.00", "200.00", "200.00"): self.confirmed(v, "100.00")
        att = {x["kind"]: x for x in self.svc.fpa_overview(ORG)["attention"]}; self.assertIn("run high by 100.00%", att["FORECAST_BIAS"]["text"])
        self.svc.set_fpa_policy(ORG, dict(min_items=5), U2); self.assertNotIn("FORECAST_BIAS", {x["kind"] for x in self.svc.fpa_overview(ORG)["attention"]})

    def test_owner_workload(self):
        self.kpi(); self.kpi("Two", owner=U4, accept=False); o = {x["owner"]: x for x in self.svc.fpa_overview(ORG)["owners"]}
        self.assertEqual((o[U3]["kpis"], o[U3]["not_accepted"], o[U4]["not_accepted"]), (1, 0, 1))


class Isolation(Base):
    def test_other_organisation_sees_and_reaches_nothing(self):
        k = self.kpi(); r = self.read(k); f = self.fc()
        calls = [lambda: self.svc.get_kpi(OTHER, k["id"]), lambda: self.svc.approve_kpi(OTHER, k["id"], U2), lambda: self.svc.accept_kpi_ownership(OTHER, k["id"], U3), lambda: self.svc.retire_kpi(OTHER, k["id"], "not yours", U2),
                 lambda: self.svc.reassign_kpi_owner(OTHER, k["id"], U4, "not yours", U2), lambda: self.svc.record_kpi_reading(OTHER, k["id"], dict(period_end="2026-01-31", value="1", source_note="Not allowed here"), U3),
                 lambda: self.svc.review_kpi_reading(OTHER, k["id"], r["id"], U2), lambda: self.svc.get_forecast(OTHER, f["id"]), lambda: self.svc.withdraw_forecast(OTHER, f["id"], "not yours", U1),
                 lambda: self.svc.register_forecast(OTHER, dict(metric="Revenue", unit="AMOUNT", currency="NGN", period_end="2026-03-31", value="1", basis="Because I can", kpi_id=k["id"]), U1)]
        for fn in calls:
            with self.assertRaises(FpaNotFoundError): fn()
        self.assertEqual((self.svc.list_kpis(OTHER), self.svc.list_forecasts(OTHER)), ([], []))
        self.assertEqual(self.svc.fpa_overview(OTHER)["counts"]["kpis"], 0); self.assertEqual(self.svc.forecast_accuracy_report(OTHER)["counted"], 0)
        self.assertEqual(self.svc.define_kpi(OTHER, dict(name="Gross margin", description="Same name, own numbering", unit="PERCENT", direction="HIGHER_BETTER", frequency="MONTHLY", owner=U3, data_source="Another organisation's data",
                                                          method="Another organisation's method", target="40", effective_from="2026-01-01"), U1)["ref"], "KP-001")


class Audit(Base):
    def test_every_write_is_audited(self):
        k = self.kpi(); r = self.read(k); self.svc.review_kpi_reading(ORG, k["id"], r["id"], U2); w = self.read(k, pe="2026-01-31", value="1.00", correction_note="First figure was wrong")
        self.svc.reject_kpi_reading(ORG, k["id"], w["id"], "Does not agree to ledger", U2); self.svc.reassign_kpi_owner(ORG, k["id"], U4, "Moved to the budget team", U2); self.svc.retire_kpi(ORG, k["id"], "No longer reported", U2)
        f = self.fc(pe="2026-02-28"); g = self.fc(pe="2026-02-28", metric="Second"); self.svc.withdraw_forecast(ORG, g["id"], "Not needed any more", U1); self.clock.d = date(2026, 3, 1)
        self.svc.record_forecast_actual(ORG, f["id"], dict(value="1.00", source_note="Closed management accounts"), U3); self.svc.reject_forecast_actual(ORG, f["id"], "Wrong month used here", U2)
        self.svc.record_forecast_actual(ORG, f["id"], dict(value="1.00", source_note="Closed management accounts"), U3); self.svc.confirm_forecast_actual(ORG, f["id"], U2); self.svc.set_fpa_policy(ORG, dict(watch_pct=5), U2)
        got = {e[0] for e in self.events}
        want = {"FPA_KPI_DEFINED", "FPA_KPI_APPROVED", "FPA_KPI_OWNERSHIP_ACCEPTED", "FPA_KPI_OWNER_CHANGED", "FPA_KPI_RETIRED", "FPA_KPI_READING_RECORDED", "FPA_KPI_READING_REVIEWED", "FPA_KPI_READING_REJECTED",
                "FPA_FORECAST_REGISTERED", "FPA_FORECAST_WITHDRAWN", "FPA_ACTUAL_RECORDED", "FPA_ACTUAL_CONFIRMED", "FPA_ACTUAL_REJECTED", "FPA_POLICY_SET"}
        self.assertEqual(want - got, set())

    def test_a_refused_action_writes_nothing(self):
        k = self.kpi(approve=False); n = len(self.events)
        with self.assertRaises(FpaForbiddenError): self.svc.approve_kpi(ORG, k["id"], U1)
        self.assertEqual((len(self.events), self.svc.get_kpi(ORG, k["id"])["status"]), (n, "DRAFT"))


class Permissions(unittest.TestCase):
    def test_roles(self):
        has = lambda r, p: p in ROLE_PERMISSIONS[r]
        for r in (Role.OWNER, Role.MANAGER, Role.FINANCE_OFFICER): self.assertTrue(has(r, FPA_PREPARE) and has(r, FPA_APPROVE), r)
        self.assertTrue(has(Role.ACCOUNTANT, FPA_PREPARE) and not has(Role.ACCOUNTANT, FPA_APPROVE)); self.assertTrue(has(Role.APPROVER, FPA_APPROVE) and not has(Role.APPROVER, FPA_PREPARE))
        for r in (Role.ADMINISTRATOR, Role.REVIEWER, Role.AUDITOR, Role.EXTERNAL_AUDITOR, Role.READ_ONLY): self.assertFalse(has(r, FPA_PREPARE) or has(r, FPA_APPROVE), r)
        for r in Role:
            if has(r, FPA_PREPARE) or has(r, FPA_APPROVE): self.assertTrue(has(r, REPORTING_READ), r)


class RouterGuards(unittest.TestCase):
    SRC = os.path.join(os.path.dirname(__file__), "..", "src", "asavexa", "api", "routers", "fpa.py")

    def test_every_write_has_the_right_guard(self):
        tree = ast.parse(open(self.SRC).read()); named = {"_prepare": "FPA_PREPARE", "_approve": "FPA_APPROVE"}; g = {}
        for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.decorator_list]:
            verbs, guards = set(), set()
            for dec in fn.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute): verbs.add(dec.func.attr)
                for kw in getattr(dec, "keywords", []):
                    if kw.arg == "dependencies": guards |= {named[e.id] for e in kw.value.elts if isinstance(e, ast.Name) and e.id in named}
            g[fn.name] = (verbs, guards)
        approve = {"set_policy", "approve_kpi", "change_owner", "retire_kpi", "review_reading", "reject_reading", "confirm_actual", "reject_actual"}
        prepare = {"define_kpi", "accept_ownership", "add_reading", "register_forecast", "withdraw_forecast", "add_actual"}
        for n in approve: self.assertEqual(g[n][1], {"FPA_APPROVE"}, n)
        for n in prepare: self.assertEqual(g[n][1], {"FPA_PREPARE"}, n)
        for n, (verbs, guards) in g.items():
            if verbs == {"get"}: self.assertEqual(guards, set(), n)
            else: self.assertIn(n, approve | prepare, f"{n} writes but has no fpa guard")
        src = open(self.SRC).read(); self.assertIn("dependencies=[Depends(require_permission(REPORTING_READ))]", src); self.assertNotIn("org_id", src)


class Numbers(unittest.TestCase):
    def test_numbers(self):
        from asavexa.fpa.service import _num
        for bad in ("1e30", "abc", "", None, "1.005", float("nan"), True, "inf"):
            with self.assertRaises(FpaError, msg=bad): _num(bad, "x", 2)
        self.assertEqual(str(_num("-1,234.50", "x", 2)), "-1234.50"); self.assertEqual(str(_num("0", "x", 0)), "0")
        with self.assertRaises(FpaError): _num("1.5", "x", 0)


if __name__ == "__main__":
    unittest.main()
