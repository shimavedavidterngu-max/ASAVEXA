"""Financial Analysis workspace: every figure checked against hand calculation (see analysis_fixture.py), plus the workflow and permission rules."""
import csv, io, json, unittest
from datetime import date
from decimal import Decimal

from analysis_fixture import ORG, OTHER, PREP, PREP2, REVIEWER, TAGS, World
from asavexa.analysis import forecast as fc
from asavexa.analysis.errors import AnalysisError, AnalysisForbiddenError, AnalysisNotFoundError, AnalysisStateError
from asavexa.analysis.ratios import compute_ratios
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.permissions import ANALYSIS_APPROVE, ANALYSIS_PREPARE, REPORTING_READ, ROLE_PERMISSIONS


class Base(unittest.TestCase):
    def setUp(self):
        self.w = World(); self.s = self.w.svc


class Figures(Base):
    def test_january_figures_match_the_ledger_by_hand(self):
        f = self.s.figures(ORG, self.w.jan.id)
        self.assertEqual((f["assets"], f["liabilities"], f["equity_recorded"], f["revenue"], f["expenses"], f["net_income"]),
                         (Decimal("84500.00"), Decimal("28000.00"), Decimal("50000.00"), Decimal("15000.00"), Decimal("8500.00"), Decimal("6500.00")))
        self.assertEqual(f["equity_total"], Decimal("56500.00")); self.assertEqual(f["equity_total"], f["equity_recorded"] + f["net_income"])
        self.assertEqual(f["period"]["days"], 31)

    def test_balance_sheet_is_as_at_period_end_and_income_is_inside_the_period(self):
        f = self.s.figures(ORG, self.w.feb.id); by = {r["code"]: r for r in f["accounts"]}
        self.assertEqual(by["1000"]["amount"], Decimal("68100.00"))      # 50,500 + 20,000 - 2,400
        self.assertEqual(by["4000"]["amount"], Decimal("20000.00"))      # February only
        self.assertEqual(by["1000"]["basis"], "AS_AT"); self.assertEqual(by["4000"]["basis"], "PERIOD")

    def test_drafts_never_count_and_nothing_is_written_to_the_ledger(self):
        before = (self.w.acc.get_trial_balance(ORG, self.w.jan.id), len(self.w.acc.journals.list_for_org(ORG)))
        self.w.acc.create_draft_journal(ORG, date(2026, 1, 28), "draft", "USD", [__import__("asavexa.accounting.services.engine", fromlist=["LineInput"]).LineInput(self.w.a["1000"].id, debit_amount=Decimal("999")),
                                                                                  __import__("asavexa.accounting.services.engine", fromlist=["LineInput"]).LineInput(self.w.a["4000"].id, credit_amount=Decimal("999"))], created_by=PREP)
        n = len(self.w.acc.journals.list_for_org(ORG))
        self.assertEqual(self.s.figures(ORG, self.w.jan.id)["revenue"], Decimal("15000.00"))
        self.w.classify(); self.s.ratios(ORG, self.w.jan.id); self.s.variance(ORG, self.w.feb.id)
        self.assertEqual(self.w.acc.get_trial_balance(ORG, self.w.jan.id), before[0]); self.assertEqual(len(self.w.acc.journals.list_for_org(ORG)), n)

    def test_unknown_period_and_other_organisation(self):
        with self.assertRaises(AnalysisNotFoundError): self.s.figures(ORG, "nope")
        with self.assertRaises(AnalysisNotFoundError): self.s.figures(OTHER, self.w.jan.id)


class Ratios(Base):
    EXPECTED = {"current_ratio": "8.06", "quick_ratio": "7.81", "cash_ratio": "6.31", "working_capital": "56500.00", "gross_margin": "60.00", "operating_margin": "46.67", "net_margin": "43.33",
                "return_on_assets": "7.69", "debt_ratio": "0.33", "debt_to_equity": "0.50", "equity_ratio": "0.67", "receivable_days": "24.8", "payable_days": "41.3", "inventory_days": "10.3"}

    def test_every_ratio_equals_the_hand_calculation(self):
        self.w.classify(); out = {r["id"]: r for r in self.s.ratios(ORG, self.w.jan.id)["ratios"]}
        self.assertEqual({k: v["value"] for k, v in out.items()}, self.EXPECTED)
        self.assertTrue(all(r["status"] == "CALCULATED" for r in out.values()))

    def test_each_ratio_shows_its_working(self):
        self.w.classify(); r = self.w.ratio(self.w.jan, "current_ratio")
        self.assertEqual((r["numerator"]["amount"], r["denominator"]["amount"]), ("64500.00", "8000.00")); self.assertIn("current assets / current liabilities", r["formula"])
        self.assertEqual({a["code"] for a in r["numerator"]["accounts"]}, {"1000", "1100", "1200"}); self.assertEqual([a["code"] for a in r["denominator"]["accounts"]], ["2000"]); self.assertTrue(r["reading"])

    def test_unclassified_accounts_make_a_ratio_incomplete_and_name_them_never_guessed(self):
        r = self.w.ratio(self.w.jan, "current_ratio")
        self.assertEqual(r["status"], "INCOMPLETE"); self.assertIsNone(r["value"]); self.assertIn("1000 Cash at bank", r["reason"])
        self.assertEqual(self.w.ratio(self.w.jan, "net_margin")["value"], "43.33")          # needs no classification
        self.assertEqual(self.w.ratio(self.w.jan, "gross_margin")["status"], "INCOMPLETE")

    def test_partly_classified_is_still_incomplete(self):
        self.s.set_config(ORG, {self.w.a["1000"].id: "CASH"}, None, PREP)
        r = self.w.ratio(self.w.jan, "current_ratio"); self.assertEqual(r["status"], "INCOMPLETE"); self.assertIn("1100", r["reason"])

    def test_zero_denominator_is_undefined_not_a_number(self):
        self.w.classify(); r = self.w.ratio(self.w.mar, "net_margin")        # no revenue in March
        self.assertEqual(r["status"], "UNDEFINED"); self.assertIsNone(r["value"]); self.assertIn("Revenue is zero", r["reason"])
        self.assertEqual(self.w.ratio(self.w.mar, "current_ratio")["status"], "CALCULATED")   # balances still carry forward

    def test_more_than_one_currency_blocks_ratios(self):
        fig = self.s.figures(ORG, self.w.jan.id); fig["currencies"] = ["EUR", "USD"]
        self.assertTrue(all(r["status"] == "INCOMPLETE" and "more than one currency" in r["reason"] for r in compute_ratios(fig)))

    def test_missing_tag_for_days_ratios(self):
        self.s.set_config(ORG, {a.id: None for a in self.w.a.values()}, None, PREP)
        tags = {c: t for c, t in TAGS.items() if t not in ("RECEIVABLE",)}; self.s.set_config(ORG, {self.w.a[c].id: t for c, t in tags.items()}, None, PREP)
        r = self.w.ratio(self.w.jan, "receivable_days"); self.assertEqual(r["status"], "INCOMPLETE"); self.assertIn("Trade receivables", r["reason"])

    def test_a_loss_gives_a_negative_margin(self):
        self.w.classify(); self.w.post(date(2026, 3, 5), "Big rent", [("5100", "4000", 0), ("1000", 0, "4000")]); self.w.post(date(2026, 3, 6), "Small sale", [("1000", "1000", 0), ("4000", 0, "1000")])
        self.assertEqual(self.w.ratio(self.w.mar, "net_margin")["value"], "-300.00")


class Config(Base):
    def test_classification_is_validated_versioned_and_audited(self):
        with self.assertRaises(AnalysisError): self.s.set_config(ORG, {self.w.a["1000"].id: "PAYABLE"}, None, PREP)      # a liability tag on an asset
        with self.assertRaises(AnalysisNotFoundError): self.s.set_config(ORG, {"nope": "CASH"}, None, PREP)
        with self.assertRaises(AnalysisError): self.s.set_config(ORG, None, {"percent": "abc"}, PREP)
        c = self.s.set_config(ORG, {self.w.a["1000"].id: "CASH"}, {"percent": "25"}, PREP); self.assertEqual(c["version"], 1); self.assertEqual(c["thresholds"]["percent"], "25")
        c = self.s.set_config(ORG, {self.w.a["1000"].id: None}, None, PREP2); self.assertEqual(c["version"], 2); self.assertIsNone(next(a for a in c["accounts"] if a["code"] == "1000")["tag"])
        self.assertEqual([e[0] for e in self.w.events], ["ANALYSIS_CONFIG_CHANGED"] * 2); self.assertEqual(self.w.events[1][1], PREP2)

    def test_settings_do_not_leak_between_organisations(self):
        self.s.set_config(ORG, {self.w.a["1000"].id: "CASH"}, {"percent": "25"}, PREP)
        self.assertEqual(self.s.get_config(OTHER)["version"], 0); self.assertEqual(self.s.get_config(OTHER)["accounts"], [])


class Variance(Base):
    def rows(self, **kw):
        v = self.s.variance(ORG, self.w.feb.id); return v, {r["code"]: r for r in v["rows"]}

    def test_february_against_january_by_hand(self):
        v, r = self.rows()
        self.assertEqual((r["4000"]["current"], r["4000"]["prior"], r["4000"]["change"], r["4000"]["change_pct"]), ("20000.00", "15000.00", "5000.00", "33.3"))
        self.assertEqual((r["5000"]["change"], r["5000"]["change_pct"]), ("3000.00", "50.0")); self.assertEqual((r["5100"]["change"], r["5100"]["change_pct"]), ("400.00", "20.0"))
        self.assertEqual((r["5200"]["change"], r["5200"]["change_pct"]), ("-500.00", "-100.0")); self.assertEqual((r["1000"]["change"], r["1000"]["change_pct"]), ("17600.00", "34.9"))
        self.assertEqual((r["3000"]["change"], r["3000"]["material"]), ("0.00", False))        # equity did not move: listed, but never flagged
        self.assertEqual((r["1200"]["current"], r["1200"]["change_pct"]), ("0.00", "-100.0"))   # stock fully used: 2,000 to 0

    def test_materiality_follows_the_thresholds(self):
        v, r = self.rows(); self.assertTrue(all(r[c]["material"] for c in ("4000", "5000", "5100", "5200", "1000")))
        self.s.set_config(ORG, None, {"percent": "25"}, PREP); v, r = self.rows(); self.assertFalse(r["5100"]["material"]); self.assertTrue(r["4000"]["material"])
        self.s.set_config(ORG, None, {"percent": "25", "amount": "4000"}, PREP); v, r = self.rows(); self.assertFalse(r["5000"]["material"]); self.assertTrue(r["4000"]["material"])

    def test_first_period_has_no_prior(self):
        self.assertEqual(self.s.variance(ORG, self.w.jan.id)["status"], "NO_PRIOR_PERIOD")

    def test_a_new_account_is_flagged_new_not_divided_by_zero(self):
        from asavexa.accounting.domain.enums import AccountType
        new = self.w.acc.create_account(ORG, "4100", "Consulting income", AccountType.REVENUE, actor=PREP); self.w.a["4100"] = new
        self.w.post(date(2026, 3, 4), "First consulting", [("1000", "700", 0), ("4100", 0, "700")])
        r = {x["code"]: x for x in self.s.variance(ORG, self.w.mar.id)["rows"]}
        self.assertEqual((r["4100"]["prior"], r["4100"]["change"], r["4100"]["change_pct"], r["4100"]["is_new"], r["4100"]["material"]), ("0.00", "700.00", None, True, True))

    def test_commentary_is_recorded_validated_and_attached(self):
        with self.assertRaises(AnalysisError): self.s.add_comment(ORG, self.w.feb.id, self.w.a["4000"].id, " ", PREP)
        with self.assertRaises(AnalysisNotFoundError): self.s.add_comment(ORG, self.w.feb.id, "nope", "why", PREP)
        with self.assertRaises(AnalysisNotFoundError): self.s.add_comment(ORG, "nope", self.w.a["4000"].id, "why", PREP)
        self.s.add_comment(ORG, self.w.feb.id, self.w.a["4000"].id, "New customer in February", PREP)
        v, r = self.rows(); self.assertEqual(r["4000"]["comments"][0]["text"], "New customer in February"); self.assertEqual(r["4000"]["comments"][0]["actor"], PREP); self.assertEqual(r["5000"]["comments"], [])
        self.assertIn("ANALYSIS_COMMENT_ADDED", [e[0] for e in self.w.events])


class Budget(Base):
    def lines(self): return {self.w.a["4000"].id: "18000", self.w.a["5000"].id: "8000", self.w.a["5100"].id: "2400"}

    def test_budget_against_actual_by_hand(self):
        self.assertEqual(self.s.budget_variance(ORG, self.w.feb.id)["status"], "NO_BUDGET")
        self.s.set_budget(ORG, self.w.feb.id, self.lines(), "Board-approved target", PREP); v = self.s.budget_variance(ORG, self.w.feb.id); r = {x["code"]: x for x in v["rows"]}
        self.assertEqual((r["4000"]["variance"], r["4000"]["variance_pct"], r["4000"]["favourable"]), ("2000.00", "11.1", True))       # more revenue than planned
        self.assertEqual((r["5000"]["variance"], r["5000"]["variance_pct"], r["5000"]["favourable"]), ("1000.00", "12.5", False))      # more cost than planned
        self.assertEqual((r["5100"]["variance"], r["5100"]["favourable"], r["5100"]["material"]), ("0.00", None, False))
        self.assertIn("not an approved budget", v["basis_note"])

    def test_budgets_are_versioned_and_only_for_revenue_and_expense(self):
        self.s.set_budget(ORG, self.w.feb.id, self.lines(), "v1", PREP); b = self.s.set_budget(ORG, self.w.feb.id, {self.w.a["4000"].id: "19000"}, "v2", PREP2)
        self.assertEqual(b["meta"]["version"], 2); self.assertEqual([h["version"] for h in b["history"]], [1, 2]); self.assertEqual(len(b["lines"]), 1)
        with self.assertRaises(AnalysisError): self.s.set_budget(ORG, self.w.feb.id, {self.w.a["1000"].id: "5"}, "", PREP)
        with self.assertRaises(AnalysisError): self.s.set_budget(ORG, self.w.feb.id, {self.w.a["4000"].id: "-5"}, "", PREP)
        with self.assertRaises(AnalysisError): self.s.set_budget(ORG, self.w.feb.id, {}, "", PREP)
        with self.assertRaises(AnalysisNotFoundError): self.s.set_budget(ORG, self.w.feb.id, {"nope": "5"}, "", PREP)
        with self.assertRaises(AnalysisNotFoundError): self.s.get_budget(OTHER, self.w.feb.id)       # another organisation cannot reach this period


class Forecast(Base):
    A = {"months": 3, "base_monthly_revenue": "10000", "base_monthly_expenses": "8000", "revenue_growth_pct": "10", "expense_growth_pct": "0", "opening_cash": "5000"}

    def test_projection_matches_hand_calculation(self):
        r = fc.run(fc.clean_assumptions(self.A)); rows = r["rows"]
        self.assertEqual([x["revenue"] for x in rows], ["11000.00", "12100.00", "13310.00"]); self.assertEqual([x["closing_cash"] for x in rows], ["8000.00", "12100.00", "17410.00"])
        self.assertEqual((r["closing_cash"], r["lowest_cash"], r["lowest_cash_month"], r["first_month_negative"]), ("17410.00", "8000.00", 1, None)); self.assertTrue(all(x["kind"] == "FORECAST" for x in rows))
        s = {x["change_points"]: x for x in r["sensitivity"]}
        self.assertEqual(s["-5"]["closing_cash"], "14101.25"); self.assertEqual(s["5"]["closing_cash"], "20933.75"); self.assertEqual(s["0"]["closing_cash"], "17410.00")

    def test_cash_running_out_is_found(self):
        r = fc.run(fc.clean_assumptions({**self.A, "base_monthly_revenue": "5000", "base_monthly_expenses": "10000", "revenue_growth_pct": "0", "opening_cash": "0"}))
        self.assertEqual(r["first_month_negative"], 1); self.assertEqual(r["closing_cash"], "-15000.00")

    def test_assumptions_are_validated(self):
        for bad in ({"months": 0}, {"months": 25}, {"months": "x"}, {"base_monthly_revenue": "-1"}, {"revenue_growth_pct": "abc"}, {"opening_cash": ""}, {"revenue_growth_pct": "-101"}):
            with self.assertRaises(AnalysisError, msg=str(bad)): fc.clean_assumptions({**self.A, **bad})

    def test_scenarios_are_saved_versioned_and_run_by_the_service(self):
        d = self.s.save_scenario(ORG, "Base case", self.w.feb.id, self.A, PREP); self.assertEqual((d["version"], d["kind"]), (1, "FORECAST"))
        d2 = self.s.save_scenario(ORG, "Base case v2", self.w.feb.id, {**self.A, "months": 6}, PREP2, scenario_id=d["id"]); self.assertEqual(d2["version"], 2); self.assertEqual(d2["created_by"], PREP)
        self.assertEqual(len(self.s.run_scenario(ORG, d["id"])["rows"]), 6); self.assertEqual(len(self.s.list_scenarios(ORG, self.w.feb.id)), 1); self.assertEqual(self.s.list_scenarios(ORG, self.w.jan.id), [])
        with self.assertRaises(AnalysisNotFoundError): self.s.run_scenario(OTHER, d["id"])
        with self.assertRaises(AnalysisNotFoundError): self.s.save_scenario(ORG, "x1", "nope", self.A, PREP)
        with self.assertRaises(AnalysisError): self.s.save_scenario(ORG, "", self.w.feb.id, self.A, PREP)

    def test_a_forecast_never_touches_the_ledger(self):
        n = len(self.w.acc.journals.list_for_org(ORG)); tb = self.w.acc.get_trial_balance(ORG, self.w.feb.id)
        d = self.s.save_scenario(ORG, "Base case", self.w.feb.id, self.A, PREP); self.s.run_scenario(ORG, d["id"]); self.s.breakeven("1000", "10", "4")
        self.assertEqual(len(self.w.acc.journals.list_for_org(ORG)), n); self.assertEqual(self.w.acc.get_trial_balance(ORG, self.w.feb.id), tb)

    def test_suggestions_come_from_actuals(self):
        self.w.classify(); g = self.s.suggest(ORG, self.w.jan.id)       # 15,000 x 30 / 31 and 8,500 x 30 / 31
        self.assertEqual((g["base_monthly_revenue"], g["base_monthly_expenses"], g["opening_cash"]), ("14516.13", "8225.81", "50500.00"))
        self.s.set_config(ORG, {self.w.a["1000"].id: None}, None, PREP); self.assertIsNone(self.s.suggest(ORG, self.w.jan.id)["opening_cash"])

    def test_break_even_by_hand(self):
        b = fc.breakeven("10000", "25", "15"); self.assertEqual((b["break_even_units"], b["break_even_revenue"], b["contribution_margin_pct"]), ("1000", "25000.00", "40.00"))
        self.assertEqual(fc.breakeven("10001", "25", "15")["break_even_units"], "1001")
        s = {x["price_change_pct"]: x["units"] for x in b["price_sensitivity"]}; self.assertEqual(s, {"-10": "1334", "0": "1000", "10": "800"})
        for bad in (("10", "5", "5"), ("10", "4", "5"), ("-1", "5", "1"), ("x", "5", "1")):
            with self.assertRaises(AnalysisError): fc.breakeven(*bad)


class Reports(Base):
    def setUp(self):
        super().setUp(); self.w.classify()
        self.sc = self.s.save_scenario(ORG, "Base case", self.w.feb.id, Forecast.A, PREP)
        self.r = self.s.create_report(ORG, self.w.feb.id, "February analysis", "For the board", [self.sc["id"]], [{"id": "e1", "filename": "bank.pdf", "type": "BANK_STATEMENT", "status": "VERIFIED", "file_hash": "ab" * 32}], PREP)

    def submit(self): return self.s.submit_report(ORG, self.r["id"], PREP)

    def test_submitting_freezes_a_snapshot_with_the_working(self):
        self.assertEqual((self.r["status"], self.r["version"], self.r["has_snapshot"]), ("DRAFT", 0, False))
        r = self.submit(); s = r["snapshot"]
        self.assertEqual((r["status"], r["version"]), ("SUBMITTED", 1)); self.assertEqual(len(r["fingerprint"]), 64)
        self.assertEqual(s["totals"]["net_income"], "8600.00"); self.assertEqual({x["id"]: x["value"] for x in s["ratios"]}["net_margin"], "43.00")
        self.assertEqual(s["scenarios"][0]["closing_cash"], "17410.00"); self.assertEqual(s["evidence"][0]["filename"], "bank.pdf"); self.assertEqual(s["variance"]["status"], "OK"); self.assertEqual(s["budget_variance"]["status"], "NO_BUDGET")
        self.assertTrue(s["limitations"]); self.assertEqual(s["config"]["version"], 1)

    def test_you_cannot_approve_or_reject_your_own_analysis_even_by_direct_call(self):
        self.submit()
        with self.assertRaises(AnalysisForbiddenError): self.s.approve_report(ORG, self.r["id"], PREP)
        with self.assertRaises(AnalysisForbiddenError): self.s.reject_report(ORG, self.r["id"], PREP, "no")
        self.assertEqual(self.s.get_report(ORG, self.r["id"])["status"], "SUBMITTED")

    def test_a_second_person_approves_and_it_becomes_final(self):
        self.submit(); a = self.s.approve_report(ORG, self.r["id"], REVIEWER, "Checked to the ledger")
        self.assertEqual((a["status"], a["decided_by"]), ("APPROVED", REVIEWER)); self.assertEqual([h["action"] for h in a["history"]], ["CREATED", "SUBMITTED", "APPROVED"])
        for fn in (lambda: self.s.update_report(ORG, self.r["id"], "x1x", None, None, None, PREP), lambda: self.s.submit_report(ORG, self.r["id"], PREP), lambda: self.s.approve_report(ORG, self.r["id"], REVIEWER), lambda: self.s.reject_report(ORG, self.r["id"], REVIEWER, "late")):
            with self.assertRaises(AnalysisStateError): fn()

    def test_nothing_skips_a_step(self):
        with self.assertRaises(AnalysisStateError): self.s.approve_report(ORG, self.r["id"], REVIEWER)          # still a draft
        with self.assertRaises(AnalysisStateError): self.s.export_csv(ORG, self.r["id"], PREP)
        self.submit()
        with self.assertRaises(AnalysisStateError): self.s.export_csv(ORG, self.r["id"], REVIEWER)                # submitted, not approved
        with self.assertRaises(AnalysisStateError): self.s.update_report(ORG, self.r["id"], "x1x", None, None, None, PREP)   # frozen while waiting

    def test_rejection_needs_a_reason_and_allows_a_new_version(self):
        self.submit()
        with self.assertRaises(AnalysisError): self.s.reject_report(ORG, self.r["id"], REVIEWER, "")
        j = self.s.reject_report(ORG, self.r["id"], REVIEWER, "Explain the rent increase"); self.assertEqual((j["status"], j["decision_note"]), ("REJECTED", "Explain the rent increase"))
        self.s.add_comment(ORG, self.w.feb.id, self.w.a["5100"].id, "Rent rose after the new lease", PREP)
        e = self.s.update_report(ORG, self.r["id"], "February analysis (revised)", None, None, None, PREP); self.assertEqual(e["title"], "February analysis (revised)")
        r2 = self.s.submit_report(ORG, self.r["id"], PREP2); self.assertEqual((r2["status"], r2["version"], r2["submitted_by"]), ("SUBMITTED", 2, PREP2))
        self.assertTrue(any(c["text"].startswith("Rent rose") for x in r2["snapshot"]["variance"]["rows"] for c in x["comments"]))
        with self.assertRaises(AnalysisForbiddenError): self.s.approve_report(ORG, self.r["id"], PREP2)
        self.assertEqual(self.s.approve_report(ORG, self.r["id"], PREP)["status"], "APPROVED")                    # PREP did not submit version 2

    def test_a_tampered_report_is_detected_and_cannot_be_approved(self):
        self.submit(); key = f"{ORG}:{self.r['id']}"; d = self.w.store.get("analysis_report", key); d["snapshot"]["totals"]["net_income"] = "99999.00"; self.w.store.put("analysis_report", key, d, org_id=ORG)
        v = self.s.verify_report(ORG, self.r["id"]); self.assertFalse(v["integrity_ok"]); self.assertIn("altered", v["meaning"])
        with self.assertRaises(AnalysisStateError): self.s.approve_report(ORG, self.r["id"], REVIEWER)

    def test_verification_detects_a_late_posting(self):
        self.submit(); self.s.approve_report(ORG, self.r["id"], REVIEWER)
        v = self.s.verify_report(ORG, self.r["id"]); self.assertTrue(v["integrity_ok"]); self.assertTrue(v["matches_ledger_now"]); self.assertEqual(v["account_differences"], [])
        self.w.post(date(2026, 2, 20), "Late sale", [("1000", "500", 0), ("4000", 0, "500")])
        v = self.s.verify_report(ORG, self.r["id"]); self.assertTrue(v["integrity_ok"]); self.assertFalse(v["matches_ledger_now"])
        self.assertIn("4000", [d["account"] for d in v["account_differences"]]); self.assertTrue(any(d["ratio"] == "net_margin" for d in v["ratio_differences"]))
        with self.assertRaises(AnalysisStateError): self.s.verify_report(ORG, self.s.create_report(ORG, self.w.feb.id, "Another", "", [], [], PREP)["id"])

    def test_export_is_csv_labelled_audited_and_only_when_approved(self):
        self.submit(); self.s.approve_report(ORG, self.r["id"], REVIEWER); out = self.s.export_csv(ORG, self.r["id"], REVIEWER)
        self.assertTrue(out["filename"].endswith("-v1.csv")); rows = list(csv.reader(io.StringIO(out["content"])))
        flat = [c for r in rows for c in r]; self.assertTrue(rows[0][0].startswith("CONFIDENTIAL")); self.assertIn(self.s.get_report(ORG, self.r["id"])["fingerprint"], flat)
        self.assertIn("FORECAST - Base case (not actual results)", flat); self.assertIn("LIMITATIONS", flat)
        ratio_row = next(r for r in rows if r and r[0] == "Net margin"); self.assertEqual(ratio_row[2], "43.00")
        self.assertEqual(self.w.events[-1][0], "ANALYSIS_REPORT_EXPORTED"); self.assertEqual(self.w.events[-1][1], REVIEWER)

    def test_every_step_is_in_the_audit_trail_with_the_right_person(self):
        self.submit(); self.s.approve_report(ORG, self.r["id"], REVIEWER)
        acts = [(e[0], e[1]) for e in self.w.events if e[0].startswith("ANALYSIS_REPORT")]
        self.assertEqual(acts, [("ANALYSIS_REPORT_CREATED", PREP), ("ANALYSIS_REPORT_SUBMITTED", PREP), ("ANALYSIS_REPORT_APPROVED", REVIEWER)])

    def test_reports_are_private_to_their_organisation(self):
        self.submit()
        for fn in (lambda: self.s.get_report(OTHER, self.r["id"]), lambda: self.s.submit_report(OTHER, self.r["id"], REVIEWER), lambda: self.s.approve_report(OTHER, self.r["id"], REVIEWER), lambda: self.s.verify_report(OTHER, self.r["id"])):
            with self.assertRaises(AnalysisNotFoundError): fn()
        self.assertEqual(self.s.list_reports(OTHER), []); self.assertEqual(len(self.s.list_reports(ORG)), 1); self.assertNotIn("snapshot", self.s.list_reports(ORG)[0])

    def test_unknown_scenario_or_period_is_refused(self):
        with self.assertRaises(AnalysisNotFoundError): self.s.create_report(ORG, self.w.feb.id, "Bad one", "", ["nope"], [], PREP)
        with self.assertRaises(AnalysisNotFoundError): self.s.create_report(ORG, "nope", "Bad one", "", [], [], PREP)
        with self.assertRaises(AnalysisError): self.s.create_report(ORG, self.w.feb.id, "x", "", [], [], PREP)

    def test_an_approved_snapshot_does_not_change_when_settings_change_later(self):
        self.submit(); self.s.approve_report(ORG, self.r["id"], REVIEWER); before = self.s.get_report(ORG, self.r["id"])["fingerprint"]
        self.s.set_config(ORG, {self.w.a["1000"].id: None}, {"percent": "50"}, PREP); self.s.add_comment(ORG, self.w.feb.id, self.w.a["4000"].id, "later note", PREP)
        r = self.s.get_report(ORG, self.r["id"]); self.assertEqual(r["fingerprint"], before); self.assertEqual(r["snapshot"]["config"]["thresholds"]["percent"], "10"); self.assertTrue(self.s.verify_report(ORG, self.r["id"])["integrity_ok"])


class Permissions(unittest.TestCase):
    def test_who_can_do_what(self):
        has = lambda r, p: p in ROLE_PERMISSIONS[r]
        self.assertTrue(all(has(Role.OWNER, p) for p in (ANALYSIS_PREPARE, ANALYSIS_APPROVE)))
        self.assertEqual({r for r in Role if has(r, ANALYSIS_PREPARE)}, {Role.OWNER, Role.ACCOUNTANT, Role.FINANCE_OFFICER})
        self.assertEqual({r for r in Role if has(r, ANALYSIS_APPROVE)}, {Role.OWNER, Role.FINANCE_OFFICER, Role.APPROVER})
        for r in (Role.READ_ONLY, Role.AUDITOR, Role.EXTERNAL_AUDITOR, Role.REVIEWER, Role.MANAGER): self.assertTrue(has(r, REPORTING_READ) and not has(r, ANALYSIS_PREPARE) and not has(r, ANALYSIS_APPROVE), r)
        for r in (Role.INVESTOR_REVIEWER, Role.DONOR, Role.REGULATOR): self.assertEqual(ROLE_PERMISSIONS[r], frozenset())
        self.assertFalse(has(Role.ADMINISTRATOR, ANALYSIS_PREPARE))


if __name__ == "__main__":
    unittest.main()
