"""Pilot service: consent, isolation between client organisations, honest survey privacy, and tamper-evident snapshots."""
import unittest
from datetime import datetime, timezone

from asavexa.pilot.errors import PilotError, PilotForbiddenError, PilotNotFoundError, PilotStateError
from asavexa.pilot.service import MAX_CLIENTS, PilotService
from asavexa.security.store import MemoryDocStore

FIRM, C1, C2, C3 = "firm", "sme1", "sme2", "sme3"
NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


class Base(unittest.TestCase):
    def setUp(self):
        self.logs = []
        self.s = PilotService(MemoryDocStore(), log=lambda *a, **k: self.logs.append(a), now=lambda: NOW)
        self.p = self.s.create_pilot(FIRM, "mgr", "Lagos pilot", "2026-10-01")
        self.pid = self.p["id"]

    def add(self, org=C1, label="Bakery", **kw):
        kw.setdefault("consent_reference", "Signed letter 2026-09-28")
        return self.s.add_client(FIRM, "mgr", self.pid, org, label, **kw)

    def start(self, *orgs):
        for o in orgs or (C1,):
            self.add(o, f"Client {o}")
        return self.s.set_status(FIRM, "mgr", self.pid, "ACTIVE")


class LifecycleTests(Base):
    def test_create_validates_dates_and_name(self):
        with self.assertRaises(PilotError): self.s.create_pilot(FIRM, "m", "x", "not a date")
        with self.assertRaises(PilotError): self.s.create_pilot(FIRM, "m", "x", "2026-10-02", "2026-10-01")
        with self.assertRaises(PilotError): self.s.create_pilot(FIRM, "m", "  ", "2026-10-01")
        with self.assertRaises(PilotError): self.s.create_pilot(FIRM, "m", "x", "2026-10-01", targets={"nonsense": 1})

    def test_status_flow_is_one_way_and_needs_a_client(self):
        with self.assertRaises(PilotStateError): self.s.set_status(FIRM, "m", self.pid, "ACTIVE")       # no clients
        with self.assertRaises(PilotStateError): self.s.set_status(FIRM, "m", self.pid, "COMPLETED")     # skipping
        with self.assertRaises(PilotError): self.s.set_status(FIRM, "m", self.pid, "PAUSED")
        self.assertEqual(self.start()["status"], "ACTIVE")
        self.assertEqual(self.s.set_status(FIRM, "m", self.pid, "COMPLETED")["status"], "COMPLETED")
        with self.assertRaises(PilotStateError): self.s.set_status(FIRM, "m", self.pid, "ACTIVE")
        with self.assertRaises(PilotStateError): self.add(C2)                                            # completed: no new clients

    def test_targets_update_merges_and_validates(self):
        t = self.s.update_targets(FIRM, "m", self.pid, {"onboarding_days": 7})["targets"]
        self.assertEqual(t["onboarding_days"], 7); self.assertEqual(t["evidence_verified_percent"], 90)
        with self.assertRaises(PilotError): self.s.update_targets(FIRM, "m", self.pid, {"onboarding_days": -3})

    def test_unknown_pilot(self):
        with self.assertRaises(PilotNotFoundError): self.s.view(FIRM, "nope")
        with self.assertRaises(PilotNotFoundError): self.s.view("other-firm", self.pid)                 # another firm cannot see it


class ClientTests(Base):
    def test_consent_reference_is_required(self):
        for bad in ("", "  ", "ok"):
            with self.assertRaises(PilotError): self.add(consent_reference=bad)

    def test_firm_cannot_be_its_own_client(self):
        with self.assertRaises(PilotError): self.add(FIRM)

    def test_one_active_pilot_per_client_organisation(self):
        self.add(C1)
        other = self.s.create_pilot("firm2", "m", "Other", "2026-10-01")
        with self.assertRaises(PilotStateError): self.s.add_client("firm2", "m", other["id"], C1, "Bakery", "letter 123")
        self.s.remove_client(FIRM, "m", self.pid, C1, "withdrew")
        self.assertEqual(len(self.s.add_client("firm2", "m", other["id"], C1, "Bakery", "letter 123")["clients"]), 1)

    def test_client_cap(self):
        for i in range(MAX_CLIENTS): self.add(f"c{i}", f"C{i}")
        with self.assertRaises(PilotStateError): self.add("one-too-many")

    def test_kickoff_in_future_rejected_and_default_is_now(self):
        with self.assertRaises(PilotError): self.add(kickoff="2027-01-01")
        self.assertTrue(self.add(kickoff=None)["clients"][0]["kickoff"].startswith("2026-10-20"))
        with self.assertRaises(PilotError): self.add(C2, kickoff="garbage")

    def test_baseline_validation(self):
        with self.assertRaises(PilotError): self.add(baseline={"audit_prep_minutes": 0})
        with self.assertRaises(PilotError): self.add(baseline={"report_minutes": "abc"})
        c = self.add(baseline={"audit_prep_minutes": "600"})["clients"][0]["baseline"]
        self.assertEqual(c, {"audit_prep_minutes": 600, "report_minutes": None})

    def test_update_client_changes_only_what_is_given(self):
        self.add(baseline={"audit_prep_minutes": 600})
        c = self.s.update_client(FIRM, "m", self.pid, C1, label="Bakery Ltd", baseline={"report_minutes": 90})["clients"][0]
        self.assertEqual((c["label"], c["baseline"]), ("Bakery Ltd", {"audit_prep_minutes": 600, "report_minutes": 90}))
        with self.assertRaises(PilotNotFoundError): self.s.update_client(FIRM, "m", self.pid, "ghost", label="x")

    def test_removal_is_logged_on_both_organisations_and_needs_a_reason(self):
        self.add()
        with self.assertRaises(PilotError): self.s.remove_client(FIRM, "m", self.pid, C1, " ")
        self.s.remove_client(FIRM, "m", self.pid, C1, "left the practice")
        orgs = [(a[0], a[3]) for a in self.logs if a[0] == "PILOT_CLIENT_REMOVED"]
        self.assertEqual({o for _, o in orgs}, {FIRM, C1})
        with self.assertRaises(PilotNotFoundError): self.s.remove_client(FIRM, "m", self.pid, C1, "again")
        self.assertIsNone(self.s.membership(C1))                                                          # no longer a participant

    def test_adding_is_logged_on_both_organisations(self):
        self.add()
        self.assertEqual({a[3] for a in self.logs if a[0] == "PILOT_CLIENT_ADDED"}, {FIRM, C1})


class MembershipTests(Base):
    def test_client_view_is_redacted(self):
        self.start(C1, C2)
        m = self.s.membership(C1)
        self.assertEqual(m["role"], "CLIENT"); self.assertEqual(m["client"]["label"], "Client sme1")
        self.assertNotIn("clients", m["pilot"]); self.assertNotIn("Client sme2", str(m))                  # no sight of other clients or targets
        self.assertNotIn("targets", m["pilot"])

    def test_firm_view_and_strangers(self):
        self.assertEqual(self.s.membership(FIRM)["role"], "FIRM")
        self.assertIsNone(self.s.membership("random-org"))


class LogTests(Base):
    def setUp(self):
        super().setUp(); self.start(C1, C2)

    def test_firm_can_log_for_any_active_client_client_only_for_itself(self):
        self.s.log_time(FIRM, "acc", FIRM, self.pid, C1, "AUDIT_PREP", 300, "2026-10-10")
        self.s.log_time(C1, "owner1", FIRM, self.pid, C1, "REPORT", 40, "2026-10-11")
        with self.assertRaises(PilotForbiddenError): self.s.log_time(C1, "owner1", FIRM, self.pid, C2, "REPORT", 40, "2026-10-11")
        with self.assertRaises(PilotForbiddenError): self.s.log_time("stranger", "x", FIRM, self.pid, C1, "REPORT", 40, "2026-10-11")
        with self.assertRaises(PilotNotFoundError): self.s.log_time(FIRM, "acc", FIRM, self.pid, "ghost", "REPORT", 40, "2026-10-11")

    def test_time_validation(self):
        bad = [("NAP", 5, "2026-10-10"), ("REPORT", 0, "2026-10-10"), ("REPORT", "x", "2026-10-10"), ("REPORT", True, "2026-10-10"), ("REPORT", 5, "2026-11-30"), ("REPORT", 5, "soon")]
        for k, m, d in bad:
            with self.assertRaises(PilotError, msg=(k, m, d)): self.s.log_time(FIRM, "a", FIRM, self.pid, C1, k, m, d)

    def test_saved_percent_uses_entry_baseline_then_client_baseline(self):
        self.s.update_client(FIRM, "m", self.pid, C1, baseline={"audit_prep_minutes": 1000})
        self.s.log_time(FIRM, "a", FIRM, self.pid, C1, "AUDIT_PREP", 600, "2026-10-10")                     # client baseline 1000
        self.s.log_time(FIRM, "a", FIRM, self.pid, C2, "AUDIT_PREP", 300, "2026-10-10", baseline_minutes=500)  # own baseline 500
        self.s.log_time(FIRM, "a", FIRM, self.pid, C2, "AUDIT_PREP", 999, "2026-10-10")                     # no baseline at all -> unpaired
        t = self.s.reported(self.s.view(FIRM, self.pid))["time"]["audit_prep"]
        self.assertEqual((t["entries"], t["paired_entries"], t["minutes"], t["baseline_minutes"], t["saved_percent"]), (3, 2, 1899, 1500, 40.0))

    def test_no_baseline_means_no_percentage_not_zero(self):
        self.s.log_time(FIRM, "a", FIRM, self.pid, C1, "REPORT", 30, "2026-10-10")
        self.assertIsNone(self.s.reported(self.s.view(FIRM, self.pid))["time"]["report"]["saved_percent"])

    def test_client_sees_only_its_own_entries_without_names_of_staff(self):
        self.s.log_issue(FIRM, "acc", FIRM, self.pid, C1, "USER_ERROR", "LOW", "Posted to the wrong account")
        self.s.log_issue(FIRM, "acc", FIRM, self.pid, C2, "BUG", "HIGH", "Report would not load")
        mine = self.s.logs(C1, FIRM, self.pid); allv = self.s.logs(FIRM, FIRM, self.pid)
        self.assertEqual(len(mine["issues"]), 1); self.assertEqual(len(allv["issues"]), 2)
        self.assertNotIn("reported_by", mine["issues"][0]); self.assertNotIn("acc", str(mine["issues"][0].get("reported_by", "")))
        with self.assertRaises(PilotForbiddenError): self.s.logs("stranger", FIRM, self.pid)
        self.assertEqual([c["org_id"] for c in allv["clients"]], [C1, C2]); self.assertEqual(mine["clients"], [{"org_id": C1, "label": "Client sme1"}])    # a client never learns who else is in the pilot
        self.assertEqual((allv["group"], mine["group"]), ("FIRM", "CLIENT"))

    def test_issue_resolution(self):
        i = self.s.log_issue(C1, "o", FIRM, self.pid, C1, "CONFUSION", "MEDIUM", "Could not find the evidence page")
        with self.assertRaises(PilotError): self.s.resolve_issue(FIRM, "m", self.pid, i["id"], "")
        r = self.s.resolve_issue(FIRM, "m", self.pid, i["id"], "Walked through it")
        self.assertEqual(r["status"], "RESOLVED")
        with self.assertRaises(PilotStateError): self.s.resolve_issue(FIRM, "m", self.pid, i["id"], "again")
        with self.assertRaises(PilotNotFoundError): self.s.resolve_issue(FIRM, "m", self.pid, "nope", "x y z")
        with self.assertRaises(PilotError): self.s.log_issue(FIRM, "a", FIRM, self.pid, C1, "BUG", "HIGH", "bad")   # too short to be useful

    def test_passport_use_summary(self):
        self.s.log_passport_use(FIRM, "a", FIRM, self.pid, C1, "LENDER", "HELPFUL", 120)
        self.s.log_passport_use(C2, "o", FIRM, self.pid, C2, "AUDITOR", "PARTLY")
        self.s.log_passport_use(C2, "o", FIRM, self.pid, C2, "AUDITOR", "NOT_HELPFUL", 0)
        u = self.s.reported(self.s.view(FIRM, self.pid))["passport_uses"]
        self.assertEqual((u["total"], u["helpful"], u["partly"], u["not_helpful"], u["minutes_saved"]), (3, 1, 1, 1, 120)); self.assertEqual(u["by_purpose"], {"LENDER": 1, "AUDITOR": 2})
        with self.assertRaises(PilotError): self.s.log_passport_use(FIRM, "a", FIRM, self.pid, C1, "FUN", "HELPFUL")

    def test_withdrawn_client_data_is_excluded_from_results(self):
        self.s.log_issue(FIRM, "a", FIRM, self.pid, C2, "USER_ERROR", "LOW", "Wrong period selected")
        self.s.log_time(FIRM, "a", FIRM, self.pid, C2, "REPORT", 10, "2026-10-10", baseline_minutes=20)
        self.s.log_passport_use(FIRM, "a", FIRM, self.pid, C2, "LENDER", "HELPFUL")
        self.s.remove_client(FIRM, "m", self.pid, C2, "withdrew consent")
        r = self.s.reported(self.s.view(FIRM, self.pid))
        self.assertEqual((r["issues"]["total"], r["time"]["report"]["entries"], r["passport_uses"]["total"]), (0, 0, 0))
        with self.assertRaises(PilotForbiddenError): self.s.log_time(C2, "o", FIRM, self.pid, C2, "REPORT", 5, "2026-10-10")   # and cannot keep logging


class SurveyTests(Base):
    S = {"overall": 4, "ease": 3, "trust": 5, "recommend": 9}

    def setUp(self):
        super().setUp(); self.start(C1, C2, C3)

    def test_validation(self):
        for bad in ({**S0, "overall": 6} for S0 in [self.S]):
            with self.assertRaises(PilotError): self.s.submit_survey(FIRM, "u", FIRM, self.pid, "WEEK 4", bad)
        with self.assertRaises(PilotError): self.s.submit_survey(FIRM, "u", FIRM, self.pid, "W", {"overall": 4})            # required answers missing
        with self.assertRaises(PilotError): self.s.submit_survey(FIRM, "u", FIRM, self.pid, "W", {**self.S, "recommend": 11})
        with self.assertRaises(PilotError): self.s.submit_survey(FIRM, "u", FIRM, self.pid, "W", {**self.S, "mood": 3})
        with self.assertRaises(PilotError): self.s.submit_survey(FIRM, "u", FIRM, self.pid, "bad!round", self.S)
        with self.assertRaises(PilotForbiddenError): self.s.submit_survey("stranger", "u", FIRM, self.pid, "W", self.S)

    def test_one_response_per_person_per_round_and_revision_counts(self):
        self.assertEqual(self.s.submit_survey(FIRM, "u1", FIRM, self.pid, "w4", self.S)["revision"], 1)
        self.assertEqual(self.s.submit_survey(FIRM, "u1", FIRM, self.pid, "W4", {**self.S, "overall": 2})["revision"], 2)
        sm = self.s.survey_summary(self.s.view(FIRM, self.pid))
        self.assertEqual(sm["respondents"], 1); self.assertEqual(sm["overall_mean"], 2.0)
        self.assertEqual(len(self.s.my_survey(FIRM, "u1", FIRM, self.pid)), 1); self.assertEqual(self.s.my_survey(FIRM, "u2", FIRM, self.pid), [])

    def test_group_average_hidden_below_three_people(self):
        self.s.submit_survey(C1, "o1", FIRM, self.pid, "W", {**self.S, "overall": 1}, "Too slow")
        self.s.submit_survey(C2, "o2", FIRM, self.pid, "W", self.S)
        g = self.s.survey_summary(self.s.view(FIRM, self.pid))["by_group"]["CLIENT"]
        self.assertEqual((g["n"], g["overall"], g["hidden"]), (2, None, True))
        self.s.submit_survey(C3, "o3", FIRM, self.pid, "W", self.S)
        g = self.s.survey_summary(self.s.view(FIRM, self.pid))["by_group"]["CLIENT"]
        self.assertEqual((g["n"], g["overall"], g["hidden"]), (3, 3.0, False))

    def test_nps_and_comments_gated(self):
        for i, rec in enumerate([10, 9, 7, 3]):
            self.s.submit_survey(FIRM, f"u{i}", FIRM, self.pid, "W", {**self.S, "recommend": rec}, f"c{i}")
        p = self.s.view(FIRM, self.pid)
        self.assertEqual(self.s.survey_summary(p)["nps"], 25)                    # (2 promoters - 1 detractor) / 4
        self.assertNotIn("comments", self.s.survey_summary(p)); self.assertEqual(len(self.s.survey_summary(p, True)["comments"]), 4)

    def test_withdrawn_client_answers_leave_the_summary(self):
        self.s.submit_survey(C1, "o1", FIRM, self.pid, "W", self.S)
        self.s.remove_client(FIRM, "m", self.pid, C1, "withdrew")
        self.assertEqual(self.s.survey_summary(self.s.view(FIRM, self.pid))["respondents"], 0)

    def test_optional_scores_summarised_only_when_given(self):
        self.s.submit_survey(FIRM, "u1", FIRM, self.pid, "W", {**self.S, "passport_useful": 4})
        self.s.submit_survey(FIRM, "u2", FIRM, self.pid, "W", self.S)
        sm = self.s.survey_summary(self.s.view(FIRM, self.pid))
        self.assertEqual(sm["passport_useful"], {"n": 1, "mean": 4.0}); self.assertEqual(sm["respondents"], 2)


class SnapshotTests(Base):
    EV = {"measures": [{"key": "k", "label": "L", "source": "MEASURED", "value": 1.0, "unit": "%", "target": 2, "direction": ">=", "n": 3, "status": "NOT_MET", "why": "secret", "detail": {"x": 1}}],
          "counts": {"clients": 1}, "headline": "0 of 1 met"}

    def test_not_before_start_and_stores_only_aggregates(self):
        with self.assertRaises(PilotStateError): self.s.take_snapshot(FIRM, "m", self.pid, self.EV, 1, 1)
        self.start()
        s = self.s.take_snapshot(FIRM, "m", self.pid, self.EV, 1, 1)
        self.assertNotIn("why", s["measures"][0]); self.assertNotIn("detail", s["measures"][0])
        self.assertEqual(len(self.s.snapshots(FIRM, self.pid)), 1)

    def test_hash_detects_tampering(self):
        from asavexa.pilot.service import sha
        self.start(); s = self.s.take_snapshot(FIRM, "m", self.pid, self.EV, 1, 1)
        self.assertEqual(s["hash"], sha({k: v for k, v in s.items() if k != "hash"}))
        s["measures"][0]["value"] = 99
        self.assertNotEqual(s["hash"], sha({k: v for k, v in s.items() if k != "hash"}))


if __name__ == "__main__":
    unittest.main()
