"""The AI stays rule-based. The seam fixes the shape and the gate for any future provider; nothing outside is attached."""
import unittest
from datetime import datetime, timezone

from test_passport import World, NOW
from asavexa.ai import provider as P
from asavexa.ai.engine import AiEngine
from asavexa.ai.grounding import UngroundedAnswerError


class Seam(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.w = World()

    def engine(self):
        return AiEngine(self.w.inputs(), NOW)

    def test_rule_based_provider_gives_the_same_answer_as_the_engine(self):
        e = self.engine(); prov = P.select_provider("rule_based", e)
        self.assertIsInstance(prov, P.AnswerProvider)
        self.assertFalse(prov.uses_external_model)
        direct = e.detect(limit=5)
        via = prov.answer("detect", limit=5)
        self.assertEqual((via["fingerprint"], len(via["items"])), (direct["fingerprint"], len(direct["items"])))
        self.assertTrue(via["grounded"])

    def test_every_mode_goes_through_the_acceptance_check(self):
        e = self.engine(); prov = P.RuleBasedProvider(e)
        j = self.w.invoice
        for mode, params in (("explain", dict(subject_type="journal", subject_id=j.id)), ("detect", dict(limit=3)), ("recommend", dict(limit=3)),
                             ("prove", dict(subject_type="journal", subject_id=j.id)), ("ask", dict(question="Which journals have no evidence?"))):
            out = prov.answer(mode, **params)
            self.assertTrue(out["grounded"] or (out["items"] == [] and out["refusal"]), mode)       # a grounded answer, or an honest refusal that asserts nothing
        with self.assertRaises(ValueError):
            prov.answer("chat")

    def test_an_ungrounded_answer_is_refused(self):
        good = self.engine().detect(limit=3)
        for key in ("grounded", "fingerprint", "disclosure"):
            bad = dict(good); bad.pop(key)
            with self.assertRaises(UngroundedAnswerError):
                P.check_answer(bad)
        bad = dict(good, grounded=False)
        with self.assertRaises(UngroundedAnswerError):
            P.check_answer(bad)
        if good["items"]:
            broken = dict(good, items=[{k: v for k, v in good["items"][0].items() if k != "source_records"}])
            with self.assertRaises(UngroundedAnswerError):
                P.check_answer(broken)

    def test_no_outside_model_can_be_selected_and_the_gate_is_stated(self):
        for name in ("openai", "anthropic", "llm", "external", ""):
            with self.assertRaises(P.ProviderNotApprovedError) as ctx:
                P.select_provider(name, self.engine())
            self.assertIn("validated use case", str(ctx.exception))
            self.assertIn("acceptance criteria", str(ctx.exception))
        self.assertEqual(len(P.EXTERNAL_MODEL_GATE), 5)

    def test_a_refusal_is_allowed_but_only_if_it_asserts_nothing(self):
        refusal = self.engine().ask("Which journals have no evidence?")
        self.assertFalse(refusal["grounded"]); self.assertEqual(P.check_answer(refusal), refusal)
        with self.assertRaises(UngroundedAnswerError):
            P.check_answer(dict(refusal, items=[{"conclusion": {"summary": "invented"}}]))

    def test_the_engine_still_discloses_that_it_uses_no_outside_model(self):
        self.assertIn("no outside AI model", self.engine().detect(limit=1)["disclosure"])


if __name__ == "__main__":
    unittest.main()
