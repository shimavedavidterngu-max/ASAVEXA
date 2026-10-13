"""Stage 5: the evaluation harness, run on a labelled sample (labels written from how the sample books were built, not from the engine's output)."""
import unittest
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from asavexa.ai import evaluation as E
from asavexa.ai.engine import AiEngine
from asavexa.reconciliation.domain.models import BankTransactionInput
from test_ai import CHECK_NOW, UTC, engine, inputs, rich_world


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


def build_sample():
    """The Stage 14 labelled sample: the Stage 5 books PLUS planted cases for the nine rules that had no labels. Returns (world, engine, labels).
    Every planted case is built on purpose (a date moved, a posting delayed, a bank line left unmatched or rejected); the labels below say what each
    rule SHOULD do about it, written from how the case was built and not from what the engine printed."""
    w = rich_world(); a, o = w.accounting, w.org.id
    # --- weekend-dated unusual journals (a weekend date alone never flags a journal, so each also has a primary signal: revenue debited)
    w.wk_sat = w.post(date(2026, 1, 24), "Refund to customer", w.rev, w.cash, "7000")      # a Saturday
    w.wk_sun = w.post(date(2026, 1, 25), "Refund to customer", w.rev, w.cash, "6500")      # a Sunday
    # --- reversals (the originals were already unusual for other reasons, so the reversal note shows up beside them)
    a.reverse_journal(o, w.dividend.id, actor=w.owner.id, reason="entered in error", reversal_date=date(2026, 2, 4))
    a.reverse_journal(o, w.mismatch.id, actor=w.owner.id, reason="wrong account", reversal_date=date(2026, 1, 28))
    # --- a bank statement: normal lines of about 12 to 14 thousand, one huge one, some matched, one in need of review, two rejected
    rec = w.recon.create_reconciliation(o, w.cash.id, "February bank", date(2026, 2, 1), date(2026, 2, 28), actor=w.accountant.id)
    w.post(date(2026, 2, 17), "Courier", w.util, w.cash, "12400")
    w.post(date(2026, 2, 18), "Cleaning", w.util, w.cash, "13100.50")
    w.post(date(2026, 2, 19), "Printing", w.util, w.cash, "13450")
    w.post(date(2026, 2, 13), "Stationery", w.util, w.cash, "20000")
    w.post(date(2026, 2, 15), "Postage", w.inet, w.cash, "20000")                 # two entries fit the 20,000 bank line: a person must decide
    lines = [(17, "Courier", "12400"), (18, "Cleaning", "13100.50"), (19, "Printing", "13450"), (14, "Transfer", "20000")]      # (day of February, description, amount)
    lines += [(20 + i % 5, f"Bank fee {i}", amt) for i, amt in enumerate(("11450", "11650", "12050", "12150", "12450", "13050", "13350", "13850"))]
    lines += [(27, "Large unexplained transfer", "9000000")]
    w.recon.import_transactions(o, rec.id, [BankTransactionInput(date(2026, 2, day), d, credit_amount=Decimal(x), currency="NGN") for day, d, x in lines],
                                actor=w.accountant.id, import_source="bank_feed")
    w.bank = {t.description: t for t in w.recon.list_transactions(o, rec.id)}
    for d in ("Cleaning", "Printing"):
        w.recon.reject_match(o, w.bank[d].id, w.approver.id, "wrong entry")
    w.bank = {t.description: t for t in w.recon.list_transactions(o, rec.id)}
    # --- dates moved or postings delayed, on journals that were otherwise ordinary
    inp = inputs(w)
    by = {j.id: j for j in inp.journals}
    def at(j, days_after):
        j.posted_at = datetime.combine(j.date + timedelta(days=days_after), time(10, 0), tzinfo=UTC)
    at(by[w.routine[2].id], 60); at(by[w.routine[3].id], 50)                       # posted long after their dates
    at(by[w.routine[4].id], -10); at(by[w.routine[6].id], -5)                      # dated after they were posted
    by[w.routine[8].id].date = date(2026, 3, 16); at(by[w.routine[8].id], 1)       # outside the period (a Monday, so no weekend note)
    by[w.routine[9].id].date = date(2025, 12, 30); at(by[w.routine[9].id], 1)      # outside the period (a Tuesday)
    return w, AiEngine(inp, CHECK_NOW), labels(w) + new_labels(w)


def new_labels(w):
    L = []
    add = lambda rule, rid, exp, why="": L.append({"rule": rule, "journal_id": rid, "expected": exp, "why": why})
    r = w.routine
    j = lambda x: x.id
    b = lambda name: w.bank[name].id
    add("PERIOD_MISMATCH", j(r[8]), True, "dated 16 March, inside no period it belongs to"); add("PERIOD_MISMATCH", j(r[9]), True, "dated 30 December, before its period")
    add("PERIOD_MISMATCH", j(w.equipment), False); add("PERIOD_MISMATCH", j(w.internet2), False); add("PERIOD_MISMATCH", j(r[0]), False)
    add("BACKDATED_POSTING", j(r[2]), True, "posted 60 days after its date"); add("BACKDATED_POSTING", j(r[3]), True, "posted 50 days after its date")
    add("BACKDATED_POSTING", j(w.equipment), False); add("BACKDATED_POSTING", j(w.refund), False); add("BACKDATED_POSTING", j(r[0]), False)
    add("FUTURE_DATED", j(r[4]), True, "dated 10 days after it was posted"); add("FUTURE_DATED", j(r[6]), True, "dated 5 days after it was posted")
    add("FUTURE_DATED", j(w.equipment), False); add("FUTURE_DATED", j(w.refund), False); add("FUTURE_DATED", j(r[0]), False)
    add("WEEKEND_DATE", j(w.wk_sat), True, "a Saturday"); add("WEEKEND_DATE", j(w.wk_sun), True, "a Sunday")
    add("WEEKEND_DATE", j(w.equipment), False, "a Wednesday"); add("WEEKEND_DATE", j(w.refund), False, "a Monday"); add("WEEKEND_DATE", j(w.dividend), False, "a Tuesday")
    add("REVERSAL", j(w.dividend), True, "reversed on purpose"); add("REVERSAL", j(w.mismatch), True, "reversed on purpose")
    add("REVERSAL", j(w.equipment), False); add("REVERSAL", j(w.refund), False); add("REVERSAL", j(w.internet2), False)
    # bank lines are labelled by the bank line's own id
    add("BANK_LINE_UNMATCHED", b("Large unexplained transfer"), True, "no ledger entry for it"); add("BANK_LINE_UNMATCHED", b("Bank fee 0"), True, "no ledger entry for it")
    add("BANK_LINE_UNMATCHED", b("Bank fee 3"), True, "no ledger entry for it")
    add("BANK_LINE_UNMATCHED", b("Courier"), False, "matched to the courier journal"); add("BANK_LINE_UNMATCHED", b("Transfer"), False, "two entries fit, so it waits for a person")
    add("BANK_LINE_NEEDS_REVIEW", b("Transfer"), True, "two ledger entries of 20,000 fit")
    add("BANK_LINE_NEEDS_REVIEW", b("Courier"), False); add("BANK_LINE_NEEDS_REVIEW", b("Large unexplained transfer"), False); add("BANK_LINE_NEEDS_REVIEW", b("Bank fee 1"), False)
    add("BANK_LINE_REJECTED", b("Cleaning"), True, "a checker rejected the match"); add("BANK_LINE_REJECTED", b("Printing"), True, "a checker rejected the match")
    add("BANK_LINE_REJECTED", b("Courier"), False); add("BANK_LINE_REJECTED", b("Transfer"), False); add("BANK_LINE_REJECTED", b("Large unexplained transfer"), False)
    add("BANK_AMOUNT_OUTLIER", b("Large unexplained transfer"), True, "9,000,000 against lines of about 12,000")
    add("BANK_AMOUNT_OUTLIER", b("Courier"), False); add("BANK_AMOUNT_OUTLIER", b("Bank fee 2"), False); add("BANK_AMOUNT_OUTLIER", b("Bank fee 5"), False)
    add("BANK_AMOUNT_OUTLIER", b("Transfer"), False, "20,000 is large for this statement but not far above its usual lines")
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
        cls.w, cls.e, cls.labels = build_sample()
        cls.result = E.run_evaluation(cls.e, cls.labels, QUESTIONS)

    def test_every_rule_meets_the_targets_on_the_labelled_sample(self):
        for code, r in self.result["detection"]["rules"].items():
            self.assertTrue(r["meets_criteria"], (code, r))
        self.assertEqual(self.result["detection"]["mistakes"], [])
        self.assertTrue(self.result["meets_criteria"])

    def test_questions_are_grounded_refused_and_stable(self):
        q = self.result["questions"]
        self.assertEqual((q["grounded_rate"], q["refused_correctly_rate"], q["stable_rate"]), (1.0, 1.0, 1.0))

    def test_every_rule_the_assistant_has_is_now_measured(self):
        self.assertEqual(self.result["detection"]["unlabelled_rules"], [])
        self.assertEqual(len(self.result["detection"]["rules"]), len(self.e.DETECT_RULES))

    def test_every_rule_has_both_a_should_flag_and_a_should_not_flag_case_unless_it_cannot_have_one(self):
        both = {}
        for l in self.labels:
            both.setdefault(l["rule"], set()).add(l["expected"])
        for rule, kinds in both.items():
            self.assertIn(True, kinds, rule)
            self.assertIn(False, kinds, rule)

    def test_unlabelled_rules_are_still_reported_if_a_label_set_leaves_one_out(self):
        partial = [l for l in self.labels if l["rule"] != "BANK_LINE_UNMATCHED"]
        r = E.evaluate_detection(self.e, partial)
        self.assertEqual(r["unlabelled_rules"], ["BANK_LINE_UNMATCHED"])

    def test_a_matched_bank_line_does_not_pass_its_flags_to_its_journal(self):
        fired, _, _ = E.fired_rules(self.e)
        courier_journal = next(j for j in self.e.inp.journals if j.description == "Courier")
        self.assertEqual(fired.get(courier_journal.id, set()), set())
        self.assertIn("BANK_LINE_REJECTED", fired[self.w.bank["Cleaning"].id])

    def test_wrong_labels_on_the_new_rules_are_caught(self):
        for rule, rid, expected, outcome in (
                ("WEEKEND_DATE", self.w.equipment.id, True, "fn"), ("WEEKEND_DATE", self.w.wk_sat.id, False, "fp"),
                ("BANK_LINE_REJECTED", self.w.bank["Courier"].id, True, "fn"), ("BANK_AMOUNT_OUTLIER", self.w.bank["Bank fee 2"].id, True, "fn"),
                ("REVERSAL", self.w.equipment.id, True, "fn"), ("PERIOD_MISMATCH", self.w.routine[8].id, False, "fp")):
            r = E.evaluate_detection(self.e, self.labels + [{"rule": rule, "journal_id": rid, "expected": expected, "why": "wrong on purpose"}])
            self.assertIn((rule, outcome), [(m["rule"], m["outcome"]) for m in r["mistakes"]], (rule, rid))
            self.assertFalse(r["meets_criteria"])

    def test_report_states_its_limits(self):
        text = E.format_report(self.result)
        self.assertIn("only the labelled cases", text)
        self.assertIn("No accuracy claim", self.result["claim_allowed"])

    def test_a_wrong_label_is_caught_as_a_mistake(self):
        bad = self.labels + [{"rule": "OWNER_MOVEMENT", "journal_id": self.w.routine[2].id, "expected": True, "why": "deliberately wrong"}]
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
        one = [l for l in self.labels if l["rule"] == "OWNER_MOVEMENT"][:1]
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
