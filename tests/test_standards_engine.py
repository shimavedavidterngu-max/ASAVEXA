import itertools
import unittest

from asavexa.standards import catalog as C
from asavexa.standards import engine
from asavexa.standards.errors import (
    AsavexaStandardsError, InvalidPolicyChoiceError, UnknownEntityTypeError,
    UnknownFrameworkError, UnknownJurisdictionError, UnknownPolicyError,
)


class RecommendationTestCase(unittest.TestCase):
    def test_the_examples_from_the_brief(self):
        self.assertEqual(engine.recommend("NG", "PRIVATE_COMPANY")["framework"], "IFRS")
        self.assertEqual(engine.recommend("NG", "SME")["framework"], "IFRS_FOR_SMES")
        self.assertEqual(engine.recommend("US", "PRIVATE_COMPANY")["framework"], "US_GAAP")
        self.assertEqual(engine.recommend("US", "PUBLIC_INTEREST")["framework"], "US_GAAP")
        self.assertEqual(engine.recommend("NG", "PUBLIC_SECTOR")["framework"], "IPSAS")
        self.assertEqual(engine.recommend("OTHER", "PUBLIC_SECTOR")["framework"], "IPSAS")

    def test_every_jurisdiction_and_entity_type_resolves_to_a_valid_framework(self):
        for j, e in itertools.product(C.JURISDICTIONS, C.ENTITY_TYPES):
            rec = engine.recommend(j, e)
            self.assertIn(rec["framework"], C.FRAMEWORKS, (j, e))
            for alt in rec["alternatives"]:
                self.assertIn(alt, C.FRAMEWORKS, (j, e))
            self.assertNotIn(rec["framework"], rec["alternatives"])
            self.assertIn(rec["confidence"], ("established", "confirm"))
            self.assertEqual(len(rec["chain"]), 3)

    def test_a_jurisdiction_without_a_specific_rule_falls_back_and_says_so(self):
        rec = engine.recommend("GH", "NONPROFIT")
        self.assertFalse(rec["specific_rule"])
        self.assertEqual(rec["confidence"], "confirm")
        self.assertIn("No specific rule", rec["note"])
        self.assertTrue(engine.recommend("NG", "SME")["specific_rule"])

    def test_every_rule_key_uses_known_codes(self):
        for (j, e), (default, alts, why, conf) in C.RULES.items():
            self.assertTrue(j == "*" or j in C.JURISDICTIONS, j)
            self.assertIn(e, C.ENTITY_TYPES)
            self.assertIn(default, C.FRAMEWORKS)
            self.assertTrue(why)

    def test_unknown_inputs_are_rejected(self):
        with self.assertRaises(UnknownJurisdictionError):
            engine.recommend("ZZ", "SME")
        with self.assertRaises(UnknownEntityTypeError):
            engine.recommend("NG", "WIZARD")


class PolicyTestCase(unittest.TestCase):
    def test_every_framework_has_policies_with_valid_defaults(self):
        for fw in C.FRAMEWORKS:
            if fw == "CASH_BASIS":
                continue
            policies = engine.policies_for(fw)
            self.assertTrue(policies, fw)
            for p in policies:
                codes = [o["code"] for o in p["options"]]
                self.assertIn(p["default"], codes, (fw, p["code"]))
                self.assertEqual(p["effective"], p["default"])
                if p["locked"]:
                    self.assertEqual(len(codes), 1, (fw, p["code"]))
                for o in p["options"]:
                    self.assertIn(o["code"], C.OPTION_LABELS)

    def test_lifo_is_allowed_only_where_the_framework_permits_it(self):
        engine.policies_for("US_GAAP", {"INVENTORY_COSTING": "LIFO"})
        for fw in ("IFRS", "IFRS_FOR_SMES", "IPSAS"):
            with self.assertRaises(InvalidPolicyChoiceError):
                engine.policies_for(fw, {"INVENTORY_COSTING": "LIFO"})

    def test_revaluation_is_blocked_under_us_gaap_and_allowed_under_ifrs(self):
        engine.policies_for("IFRS", {"PPE_MEASUREMENT": "REVALUATION_MODEL"})
        with self.assertRaises(InvalidPolicyChoiceError):
            engine.policies_for("US_GAAP", {"PPE_MEASUREMENT": "REVALUATION_MODEL"})

    def test_locked_policy_cannot_be_changed_but_restating_it_is_fine(self):
        engine.policies_for("IFRS", {"LEASES": "RIGHT_OF_USE"})
        with self.assertRaises(InvalidPolicyChoiceError):
            engine.policies_for("IFRS", {"LEASES": "OPERATING_FINANCE_SPLIT"})

    def test_ifrs_for_smes_expenses_borrowing_costs_while_ifrs_capitalises(self):
        eff = lambda fw: {p["code"]: p["effective"] for p in engine.policies_for(fw)}
        self.assertEqual(eff("IFRS")["BORROWING_COSTS"], "CAPITALISE_QUALIFYING")
        self.assertEqual(eff("IFRS_FOR_SMES")["BORROWING_COSTS"], "EXPENSE")

    def test_override_is_flagged_only_when_it_differs_from_the_default(self):
        p = {x["code"]: x for x in engine.policies_for("IFRS", {"INVENTORY_COSTING": "FIFO", "DEPRECIATION_METHOD": "STRAIGHT_LINE"})}
        self.assertTrue(p["INVENTORY_COSTING"]["overridden"])
        self.assertFalse(p["DEPRECIATION_METHOD"]["overridden"])

    def test_fund_accounting_applies_only_to_nonprofits(self):
        self.assertIn("FUND_ACCOUNTING", [p["code"] for p in engine.policies_for("NONPROFIT")])
        self.assertNotIn("FUND_ACCOUNTING", [p["code"] for p in engine.policies_for("IFRS")])
        with self.assertRaises(InvalidPolicyChoiceError):
            engine.policies_for("IFRS", {"FUND_ACCOUNTING": "TRACK_FUNDS"})

    def test_unknown_policy_and_framework(self):
        with self.assertRaises(UnknownPolicyError):
            engine.policies_for("IFRS", {"NOPE": "X"})
        with self.assertRaises(UnknownFrameworkError):
            engine.policies_for("MADE_UP")

    def test_cash_basis_has_no_accrual_policies(self):
        self.assertEqual(engine.policies_for("CASH_BASIS"), [])


class RequirementsTestCase(unittest.TestCase):
    def test_every_framework_has_requirements_and_report_keys_are_real_reports(self):
        valid = {None, "trial-balance", "income-statement", "balance-sheet", "general-ledger"}
        for fw in C.FRAMEWORKS:
            reqs = engine.requirements_for(fw, "PRIVATE_COMPANY")
            self.assertTrue(reqs, fw)
            self.assertTrue(any(r["mandatory"] for r in reqs), fw)
            for r in reqs:
                self.assertIn(r["report_key"], valid)

    def test_entity_specific_requirements_are_filtered(self):
        listed = {r["code"] for r in engine.requirements_for("IFRS", "PUBLIC_INTEREST")}
        private = {r["code"] for r in engine.requirements_for("IFRS", "PRIVATE_COMPANY")}
        self.assertIn("EPS", listed)
        self.assertNotIn("EPS", private)

    def test_readiness_is_honest_about_what_asavexa_cannot_produce_yet(self):
        r = engine.readiness(engine.requirements_for("IFRS", "PRIVATE_COMPANY"))
        self.assertEqual(r["mandatory_available"], 2)  # balance sheet + income statement
        self.assertIn("Statement of cash flows", r["missing"])


class ResolveTestCase(unittest.TestCase):
    def test_default_resolution_follows_the_whole_chain(self):
        r = engine.resolve_configuration("NG", "SME")
        self.assertEqual(r["framework"], "IFRS_FOR_SMES")
        self.assertEqual([c["step"] for c in r["chain"]],
                         ["Jurisdiction", "Entity type", "Reporting framework", "Accounting policies", "Reporting requirements"])
        self.assertTrue(r["policies"] and r["requirements"])
        self.assertTrue(r["disclaimer"])

    def test_choosing_a_recognised_alternative_warns_softly(self):
        r = engine.resolve_configuration("NG", "SME", "IFRS")
        self.assertEqual(r["framework"], "IFRS")
        self.assertTrue(any("recognised alternative" in w for w in r["warnings"]))

    def test_choosing_an_unusual_framework_warns_strongly_but_is_allowed(self):
        r = engine.resolve_configuration("NG", "SME", "US_GAAP")
        self.assertTrue(any("not a usual choice" in w for w in r["warnings"]))

    def test_invalid_policy_override_fails_the_whole_resolution(self):
        with self.assertRaises(InvalidPolicyChoiceError):
            engine.resolve_configuration("NG", "SME", None, {"INVENTORY_COSTING": "LIFO"})

    def test_switching_framework_drops_policies_that_no_longer_apply(self):
        with self.assertRaises(InvalidPolicyChoiceError):
            engine.resolve_configuration("NG", "NONPROFIT", "IFRS", {"FUND_ACCOUNTING": "TRACK_FUNDS"})

    def test_all_errors_share_one_base_class_for_http_mapping(self):
        for exc in (UnknownJurisdictionError, UnknownEntityTypeError, UnknownFrameworkError, UnknownPolicyError, InvalidPolicyChoiceError):
            self.assertTrue(issubclass(exc, AsavexaStandardsError))

    def test_every_combination_resolves_without_error(self):
        n = 0
        for j, e in itertools.product(C.JURISDICTIONS, C.ENTITY_TYPES):
            for fw in C.FRAMEWORKS:
                engine.resolve_configuration(j, e, fw)
                n += 1
        self.assertEqual(n, len(C.JURISDICTIONS) * len(C.ENTITY_TYPES) * len(C.FRAMEWORKS))

    def test_profile_framework_codes_match_the_engine_frameworks(self):
        import re
        src = open("src/asavexa/api/schemas/organisation_profile.py").read()
        profile = set(re.findall(r'"([A-Z_]+)"', src.split("REPORTING_FRAMEWORKS = (")[1].split(")")[0]))
        self.assertEqual(profile, set(C.FRAMEWORKS))


if __name__ == "__main__":
    unittest.main()
