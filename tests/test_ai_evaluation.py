"""Stage 5: the evaluation harness, run on a labelled sample (labels written from how the sample books were built, not from the engine's output)."""
import unittest

from asavexa.ai import evaluation as E
from test_ai import engine, rich_world


def labels(w):
    L = []
    add = lambda rule, j, exp, why="": L.append({"rule": rule, "journal_id": j.id, "expected": exp, "why": why})
    r0, r1, r5 = w.routine[0], w.routine[1], w.routine[5]
    add("CONTRA_PAIRING", w.refund, True, "revenue debited"); add("CONTRA_PAIRING", r0, False); add("CONTRA_PAIRING", w.internet1, False)
    add("DUPLICATE_POSSIBLE", w.internet2, True, "same amount and description as the day before"); add("DUPLICATE_POSSIBLE", r0, False); add("DUPLICATE_POSSIBLE", w.equipment, False)
    add("AMOUNT_OUTLIER", w.equipment, True, "5.55m against ~13k routine"); add("AMOUNT_OUTLIER", r0, False); add("AMOUNT_OUTLIER", r5, False)
    add("DESCRIPTION_MISMATCH", w.mismatch, True, "rent described, equipment account used"); add("DESCRIPTION_MISMATCH", r0, False); add("DESCRIPTION_MISMATCH", w.refund, False)
    add("OWNER_MOVEMENT", w.dividend, True, "dividend"); add("OWNER_MOVEMENT", r1, False)
    add("SAME_PERSON_PREPARED_AND_POSTED", w.rent_journal, True, "owner drafted and posted"); add("SAME_PERSON_PREPARED_AND_POSTED", r0, False); add("SAME_PERSON_PREPARED_AND_POSTED", w.refund, False)
    add("EVIDENCE_GAP", w.rent_journal, True, "no evidence"); add("EVIDENCE_GAP", w.refund, True, "unverified"); add("EVIDENCE_GAP", w.dividend, True, "rejected"); add("EVIDENCE_GAP", w.equipment, False, "verified")
    add("ROUND_AMOUNT", w.equipment, True, "multiple of 10,000"); add("ROUND_AMOUNT", w.rent_journal, True, "200,000"); add("ROUND_AMOUNT", r0, False)
    return L


QUESTIONS = [
    {"question": "Find unusual transactions.", "expect": "answer"},
    {"question": "Why was JRN-000002 classified this way?", "expect": "answer"},
    {"question": "Show the evidence for JRN-000002.", "expect": "answer"},
    {"question": "Tell me a joke.", "expect": "refuse"},
    {"question": "Explain JRN-009999", "expect": "refuse"},
    {"question": "Is the owner stealing money?", "expect": "refuse"},
]


class EvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.w = rich_world(); cls.e = engine(cls.w)
        cls.result = E.run_evaluation(cls.e, labels(cls.w), QUESTIONS)

    def test_every_rule_meets_the_targets_on_the_labelled_sample(self):
        for code, r in self.result["detection"]["rules"].items():
            self.assertTrue(r["meets_criteria"], (code, r))
        self.assertEqual(self.result["detection"]["mistakes"], [])
        self.assertTrue(self.result["meets_criteria"])

    def test_questions_are_grounded_refused_and_stable(self):
        q = self.result["questions"]
        self.assertEqual((q["grounded_rate"], q["refused_correctly_rate"], q["stable_rate"]), (1.0, 1.0, 1.0))

    def test_unlabelled_rules_are_reported_not_hidden(self):
        self.assertIn("BANK_LINE_UNMATCHED", self.result["detection"]["unlabelled_rules"])

    def test_report_states_its_limits(self):
        text = E.format_report(self.result)
        self.assertIn("only the labelled cases", text)
        self.assertIn("No accuracy claim", self.result["claim_allowed"])

    def test_a_wrong_label_is_caught_as_a_mistake(self):
        bad = labels(self.w) + [{"rule": "OWNER_MOVEMENT", "journal_id": self.w.routine[2].id, "expected": True, "why": "deliberately wrong"}]
        r = E.evaluate_detection(self.e, bad)
        self.assertFalse(r["meets_criteria"])
        self.assertEqual([(m["rule"], m["outcome"]) for m in r["mistakes"]], [("OWNER_MOVEMENT", "fn")])
        self.assertLess(r["rules"]["OWNER_MOVEMENT"]["recall"], 1.0)

    def test_a_false_alarm_is_counted_against_precision(self):
        bad = [{"rule": "EVIDENCE_GAP", "journal_id": self.w.rent_journal.id, "expected": False, "why": "wrong on purpose"}] * 2
        r = E.evaluate_detection(self.e, bad)
        self.assertEqual(r["rules"]["EVIDENCE_GAP"]["fp"], 2)
        self.assertEqual(r["rules"]["EVIDENCE_GAP"]["precision"], 0.0)

    def test_too_few_labels_do_not_pass(self):
        one = [l for l in labels(self.w) if l["rule"] == "OWNER_MOVEMENT"][:1]
        r = E.evaluate_detection(self.e, one)
        self.assertFalse(r["rules"]["OWNER_MOVEMENT"]["meets_criteria"])
        self.assertIn("labelled case", r["rules"]["OWNER_MOVEMENT"]["problems"][0])

    def test_bad_input_is_refused(self):
        for bad in ([], [{"rule": "X"}], [{"rule": "OWNER_MOVEMENT", "journal_id": "j", "expected": "yes"}]):
            with self.assertRaises(ValueError):
                E.evaluate_detection(self.e, bad)
        with self.assertRaises(ValueError):
            E.evaluate_detection(self.e, [{"rule": "NO_SUCH_RULE", "journal_id": "j", "expected": True}])
        with self.assertRaises(ValueError):
            E.evaluate_questions(self.e, [{"question": "x", "expect": "maybe"}])

    def test_an_answer_expected_but_refused_fails(self):
        r = E.evaluate_questions(self.e, [{"question": "Tell me a joke.", "expect": "answer"}])
        self.assertFalse(r["meets_criteria"])
        self.assertEqual(r["grounded_rate"], 0.0)

    def test_a_refusal_expected_but_answered_fails(self):
        r = E.evaluate_questions(self.e, [{"question": "Find unusual transactions.", "expect": "refuse"}])
        self.assertFalse(r["meets_criteria"])


if __name__ == "__main__":
    unittest.main()
