"""Pilot measures, checked against figures worked out by hand from tests/pilot_fixture.py."""
import unittest
from copy import deepcopy
from datetime import timedelta

import pilot_fixture as F
from asavexa.pilot import metrics as M
from asavexa.pilot.evaluate import DEFAULT_TARGETS, clean_targets, evaluate


def client(**over):
    return M.client_metrics(F.bakery_inputs(), F.bakery_events(), over.get("kickoff", F.KICKOFF), over.get("now", F.NOW), F.FIRM_USERS)


class ClientMetricTests(unittest.TestCase):
    def setUp(self):
        self.c = client()

    def test_onboarding(self):
        o = self.c["onboarding"]
        self.assertTrue(o["operational"]); self.assertEqual(o["days_to_operational"], 4.5)        # first journal posted 5 Oct 11:00 is the last of the four
        by = {m["key"]: m for m in o["milestones"]}
        self.assertEqual(by["ACCOUNTS"]["days"], 1.4); self.assertEqual(by["EVIDENCE"]["days"], 2.4); self.assertEqual(by["BANK_IMPORT"]["days"], 3.4)
        self.assertEqual(by["RECONCILIATION"]["days"], 11.4); self.assertEqual(o["reached"], 7); self.assertEqual(o["days_since_kickoff"], 30.5)

    def test_onboarding_not_complete_when_a_milestone_is_missing(self):
        inp = F.bakery_inputs(); inp.bank_transactions = []
        c = M.client_metrics(inp, F.bakery_events(), F.KICKOFF, F.NOW, F.FIRM_USERS)
        self.assertFalse(c["onboarding"]["operational"]); self.assertIsNone(c["onboarding"]["days_to_operational"])

    def test_milestone_before_kickoff_counts_zero_days_not_negative(self):
        c = client(kickoff=F.d(25))
        self.assertTrue(all(m["days"] is None or m["days"] >= 0 for m in c["onboarding"]["milestones"])); self.assertEqual(c["onboarding"]["days_to_operational"], 0.0)

    def test_events_after_now_are_ignored(self):
        c = client(now=F.d(10))
        self.assertEqual(c["errors"]["work_actions"], 0)                       # all work events are on/after 12 Oct

    def test_processing(self):
        p = self.c["processing"]
        self.assertEqual(p["journals_posted"], 11); self.assertEqual(p["median_hours_to_post"], 10.0)    # [1,2,4,6,8,10,12,24,48,72,100]
        self.assertEqual((p["drafts_open"], p["stale_drafts"]), (2, 1)); self.assertEqual(p["reversed"], 1); self.assertEqual(p["reversal_rate_percent"], 9.1)

    def test_evidence_matches_the_passport_definition(self):
        e = self.c["evidence"]
        self.assertEqual((e["posted"], e["verified"], e["unverified"], e["defective"], e["missing"]), (11, 6, 1, 1, 3))   # Passport counts reversed journals as posted
        self.assertEqual((e["verified_percent"], e["with_any_percent"]), (54.5, 72.7))

    def test_reconciliation(self):
        r = self.c["reconciliation"]
        self.assertEqual((r["bank_transactions"], r["reconciled"], r["unreconciled"]), (12, 9, 3)); self.assertEqual(r["rate_percent"], 75.0); self.assertEqual(r["reconciliations_approved"], 1)

    def test_exceptions(self):
        x = self.c["exceptions"]
        self.assertEqual(x["count"], 5); self.assertEqual(x["items_handled"], 23); self.assertEqual(x["per_100"], 21.7); self.assertEqual(x["open_findings"], 1)   # closed finding not counted

    def test_reports(self):
        r = self.c["reports"]
        self.assertEqual((r["generated"], r["failed"], r["success_percent"]), (3, 1, 75.0)); self.assertEqual(r["kinds"], ["INCOME_STATEMENT", "TRIAL_BALANCE"]); self.assertEqual(r["periods_closed"], 1)

    def test_corrections_exclude_logins_and_bookkeeping(self):
        e = self.c["errors"]
        self.assertEqual(e["corrections"], 3); self.assertEqual(e["work_actions"], 62); self.assertEqual(e["per_100_actions"], 4.8)
        self.assertEqual(e["breakdown"], {"JOURNAL_REVERSED": 1, "JOURNAL_DRAFT_DELETED": 1, "EVIDENCE_REJECTED": 1})

    def test_adoption_counts_only_firm_accountants_who_can_post_work(self):
        a = self.c["adoption"]
        self.assertEqual(a["accountants_assigned"], 2)                      # acc-1 and acc-2; the read-only reader and the (non-firm) owner do not count
        self.assertEqual(a["accountants_active"], 1); self.assertEqual(a["rate_percent"], 50.0)
        self.assertIn("journals", a["features_used"]); self.assertIn("evidence", a["features_used"]); self.assertIn("reports", a["features_used"])
        self.assertGreaterEqual(a["active_weeks"], 2); self.assertEqual(a["weeks_elapsed"], 5)

    def test_adoption_window(self):
        a = client(now=F.NOW + timedelta(days=60))["adoption"]
        self.assertEqual(a["accountants_active"], 0)                        # nothing in the last 30 days any more

    def test_passport_use(self):
        p = self.c["passport"]
        self.assertEqual((p["generated"], p["shares_created"], p["shares_viewed"], p["shares_downloaded"]), (2, 1, 2, 0)); self.assertEqual(p["sections_total"], 6)

    def test_public_strips_internals(self):
        pub = M.public(self.c)
        self.assertNotIn("_hours", pub["processing"]); self.assertNotIn("_assigned", pub["adoption"]); self.assertIn("_hours", self.c["processing"])   # original untouched

    def test_empty_organisation_gives_none_not_zero_or_crash(self):
        from asavexa.passport.builder import PassportInputs
        c = M.client_metrics(PassportInputs(org_id="empty"), [], F.KICKOFF, F.NOW, [])
        self.assertIsNone(c["evidence"]["verified_percent"]); self.assertIsNone(c["reconciliation"]["rate_percent"]); self.assertIsNone(c["exceptions"]["per_100"])
        self.assertIsNone(c["errors"]["per_100_actions"]); self.assertIsNone(c["processing"]["median_hours_to_post"]); self.assertFalse(c["onboarding"]["operational"])


class AggregateTests(unittest.TestCase):
    def test_ratios_come_from_summed_counts(self):
        a = client(); b = deepcopy(a)
        # second client: 89 posted all verified; ratio must be weighted, not the average of 60% and 100%
        b["evidence"].update(posted=89, verified=89, missing=0, unverified=0, defective=0)
        g = M.aggregate([a, b])
        self.assertEqual(g["evidence"]["posted"], 100); self.assertEqual(g["evidence"]["verified_percent"], 95.0)
        self.assertEqual(g["reconciliation"]["rate_percent"], 75.0); self.assertEqual(g["clients"], 2)

    def test_adoption_counts_each_accountant_once_across_clients(self):
        a = client(); g = M.aggregate([a, deepcopy(a)])
        self.assertEqual((g["adoption"]["accountants_assigned"], g["adoption"]["accountants_active"], g["adoption"]["rate_percent"]), (2, 1, 50.0))

    def test_processing_median_pools_raw_hours(self):
        a = client(); g = M.aggregate([a, deepcopy(a)])
        self.assertEqual(g["processing"]["median_hours_to_post"], 10.0); self.assertEqual(g["processing"]["journals_posted"], 22)

    def test_onboarding_median_ignores_unfinished_clients(self):
        a = client(); inp = F.bakery_inputs(); inp.bank_transactions = []
        b = M.client_metrics(inp, F.bakery_events(), F.KICKOFF, F.NOW, F.FIRM_USERS)
        g = M.aggregate([a, b])
        self.assertEqual((g["onboarding"]["completed"], g["onboarding"]["not_completed"], g["onboarding"]["median_days"]), (1, 1, 4.5))

    def test_no_clients(self):
        g = M.aggregate([])
        self.assertEqual(g["clients"], 0); self.assertIsNone(g["evidence"]["verified_percent"]); self.assertIsNone(g["adoption"]["rate_percent"])


REPORTED = lambda **o: {"time": {k: {"entries": 0, "minutes": 0, "paired_entries": 0, "baseline_minutes": 0, "saved_percent": None} for k in ("audit_prep", "report", "onboarding", "month_end", "reconciliation", "other")},
                        "issues": {"total": 0, "open": 0, "user_errors": 0, "by_kind": {}},
                        "survey": {"respondents": 0, "overall_mean": None, "ease_mean": None, "trust_mean": None, "nps": None, "by_group": {"FIRM": {"n": 0}, "CLIENT": {"n": 0}}, "passport_useful": {"n": 0, "mean": None}},
                        "passport_uses": {"total": 0, "helpful": 0, "partly": 0, "not_helpful": 0}, **o}


class EvaluateTests(unittest.TestCase):
    def ev(self, clients=None, reported=None, targets=None):
        clients = clients or [client()]
        return evaluate(M.aggregate(clients), reported or REPORTED(), clean_targets(targets), [M.public(c) for c in clients])

    def by(self, r): return {m["key"]: m for m in r["measures"]}

    def test_eleven_measures_in_the_requested_order(self):
        r = self.ev()
        self.assertEqual([m["key"] for m in r["measures"]], ["onboarding", "processing", "evidence", "reconciliation", "exceptions", "reports", "audit_prep", "errors", "satisfaction", "adoption", "passport"])

    def test_judged_against_targets(self):
        m = self.by(self.ev())
        self.assertEqual(m["onboarding"]["status"], "MET")                 # 4.5 <= 14
        self.assertEqual(m["processing"]["status"], "MET")                 # 10h <= 48
        self.assertEqual(m["evidence"]["status"], "NOT_MET")               # 60% < 90%
        self.assertEqual(m["reconciliation"]["status"], "NOT_MET")         # 75% < 95%
        self.assertEqual(m["exceptions"]["status"], "NOT_MET")             # 22.7 > 5
        self.assertEqual(m["reports"]["status"], "NOT_MET")                # 75% < 95%
        self.assertEqual(m["errors"]["status"], "MET")                     # 4.8 <= 5
        self.assertEqual(m["adoption"]["status"], "NOT_MET")               # 50% < 75%

    def test_a_sample_too_small_to_judge_shows_no_headline_figure(self):
        r = REPORTED(); r["survey"].update(respondents=1, overall_mean=5.0)
        m = self.by(self.ev(reported=r))["satisfaction"]
        self.assertEqual((m["status"], m["value"]), ("INSUFFICIENT_DATA", None)); self.assertIn("So far: 5", m["why"])
        e = self.by(self.ev(clients=[client()]))["exceptions"]                         # 23 items handled is more than the minimum of 20, so a figure is shown
        self.assertIsNotNone(e["value"])

    def test_reported_measures_without_data_are_insufficient_not_failed(self):
        m = self.by(self.ev())
        for k in ("audit_prep", "satisfaction", "passport"): self.assertEqual(m[k]["status"], "INSUFFICIENT_DATA", k)
        self.assertIn("Needs at least", m["satisfaction"]["why"]); self.assertEqual(m["satisfaction"]["source"], "REPORTED")

    def test_too_few_records_is_insufficient(self):
        inp = F.bakery_inputs(); inp.journals = inp.journals[:3]; inp.evidence = inp.evidence[:3]; inp.bank_transactions = inp.bank_transactions[:3]
        c = M.client_metrics(inp, F.bakery_events(), F.KICKOFF, F.NOW, F.FIRM_USERS)
        m = self.by(self.ev([c]))
        for k in ("processing", "evidence", "reconciliation", "exceptions"): self.assertEqual(m[k]["status"], "INSUFFICIENT_DATA", k)

    def test_reported_satisfaction_and_time_saved(self):
        rep = REPORTED(); rep["survey"].update(respondents=4, overall_mean=4.25, ease_mean=4.0, trust_mean=4.5, nps=50, by_group={"FIRM": {"n": 2}, "CLIENT": {"n": 2}}, passport_useful={"n": 3, "mean": 3.67})
        rep["time"]["audit_prep"].update(entries=3, minutes=300, paired_entries=3, baseline_minutes=600, saved_percent=50.0)
        m = self.by(self.ev(reported=rep))
        self.assertEqual(m["satisfaction"]["status"], "MET"); self.assertEqual(m["audit_prep"]["status"], "MET"); self.assertEqual(m["passport"]["status"], "NOT_MET")   # 3.67 < 4

    def test_onboarding_past_target_and_unfinished_is_not_met(self):
        inp = F.bakery_inputs(); inp.bank_transactions = []
        unfinished = M.client_metrics(inp, F.bakery_events(), F.KICKOFF, F.NOW, F.FIRM_USERS)      # 30 days, not operational
        m = self.by(self.ev([client(), unfinished]))
        self.assertEqual(m["onboarding"]["status"], "NOT_MET"); self.assertIn("still not operational", m["onboarding"]["why"])

    def test_report_measure_needs_every_client_to_have_a_report(self):
        inp = F.bakery_inputs()
        silent = M.client_metrics(inp, [e for e in F.bakery_events() if not e.action.startswith("REPORT_")], F.KICKOFF, F.NOW, F.FIRM_USERS)
        good = client(); good["reports"].update(generated=30, failed=0, success_percent=100.0)
        self.assertEqual(self.by(self.ev([good, silent]))["reports"]["status"], "NOT_MET")

    def test_headline_and_caution(self):
        r = self.ev()
        self.assertEqual(sum(r["counts"].values()), 11); self.assertIn("not statistically significant", r["caution"]); self.assertIn("met", r["headline"])

    def test_targets_are_validated(self):
        self.assertEqual(clean_targets(None), DEFAULT_TARGETS)
        for bad in ({"nope": 1}, {"satisfaction_score": 9}, {"onboarding_days": "x"}, {"exceptions_per_100": True}, {"evidence_verified_percent": 0}):
            with self.assertRaises(ValueError): clean_targets(bad)
        self.assertEqual(clean_targets({"onboarding_days": 7})["onboarding_days"], 7.0)

    def test_changed_target_changes_verdict(self):
        self.assertEqual(self.by(self.ev(targets={"evidence_verified_percent": 50}))["evidence"]["status"], "MET")


if __name__ == "__main__":
    unittest.main()
