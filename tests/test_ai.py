"""
ASAVEXA AI (Explain, Detect, Recommend, Prove), exercised over the real accounting, evidence,
reconciliation, reporting and audit services (SQLite) through the same PassportInputs the API uses.
"""
import json
import unittest
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from asavexa.accounting.domain.enums import AccountType
from asavexa.accounting.services.engine import LineInput
from asavexa.ai import grounding, knowledge
from asavexa.ai.engine import MODES, AiEngine
from asavexa.ai.errors import AiSubjectNotFoundError, AiValidationError
from asavexa.ai.grounding import CHAIN, UngroundedAnswerError, validate_item
from asavexa.evidence.domain.enums import EvidenceType
from asavexa.reconciliation.domain.models import BankTransactionInput
from asavexa.standards import engine as standards_engine
from test_passport import NOW, World

UTC = timezone.utc
CHECK_NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def std():
    s = standards_engine.resolve_configuration("NG", "PRIVATE_COMPANY")
    s["configured"] = True
    return s


def rich_world() -> World:
    w = World()
    a, o = w.accounting, w.org.id
    w.eq = a.create_account(o, "1500", "Office equipment", AccountType.ASSET, w.owner.id, currency="NGN")
    w.cap = a.create_account(o, "3000", "Owner capital", AccountType.EQUITY, w.owner.id, currency="NGN")
    w.util = a.create_account(o, "5200", "Electricity and utilities", AccountType.EXPENSE, w.owner.id, currency="NGN")
    w.inet = a.create_account(o, "5300", "Internet and telephone", AccountType.EXPENSE, w.owner.id, currency="NGN")
    w.chg = a.create_account(o, "5100", "Bank charges", AccountType.EXPENSE, w.owner.id, currency="NGN")

    def post(d, desc, dr, cr, amt, by=None, poster=None):
        j = a.create_draft_journal(o, d, desc, "NGN", [
            LineInput(dr.id, debit_amount=Decimal(str(amt))), LineInput(cr.id, credit_amount=Decimal(str(amt)))],
            created_by=(by or w.accountant).id)
        return a.post_journal(o, j.id, actor=(poster or w.approver).id)
    w.post = post
    days = [6, 7, 8, 9, 12, 13, 14, 15, 16, 19]
    amts = ["12500", "13200", "11800", "14100", "12900", "13700", "12300", "14500", "13100", "12700"]
    w.routine = [post(date(2026, 1, d), "Electricity bill", w.util, w.cash, amt) for d, amt in zip(days, amts)]
    w.equipment = post(date(2026, 1, 21), "Equipment purchase", w.eq, w.cash, "5550000")
    w.internet1 = post(date(2026, 1, 22), "Internet subscription", w.inet, w.cash, "12345")
    w.internet2 = post(date(2026, 1, 23), "Internet subscription", w.inet, w.cash, "12345")
    w.refund = post(date(2026, 1, 26), "Refund to customer", w.rev, w.cash, "31000")
    w.mismatch = post(date(2026, 1, 27), "Office rent for March", w.eq, w.cash, "150000")
    w.dividend = post(date(2026, 2, 3), "Dividend payment", w.cap, w.cash, "82500")
    up = lambda j, kind=EvidenceType.INVOICE, name=None: w.vault.upload_evidence(
        o, kind, (name or j.journal_number).encode(), f"{name or j.journal_number}.pdf", "application/pdf",
        uploaded_by=w.accountant.id, linked_journal_id=j.id)
    w.eq_ev = w.vault.verify_evidence(o, up(w.equipment).id, actor=w.approver.id)
    w.refund_ev = up(w.refund, name="credit-note")                      # uploaded, never verified
    bad = up(w.dividend, EvidenceType.APPROVAL_RECORD, name="minutes")
    w.div_ev = w.vault.reject_evidence(o, bad.id, actor=w.approver.id, reason="Unsigned")
    return w


def inputs(w, org_id=None, standards="cfg"):
    inp = w.inputs(org_id=org_id, profile={"legal_name": "Meridian Textiles Limited"},
                   standards=std() if standards == "cfg" else None)
    for j in inp.journals:      # a clean, plausible posting time: the day after the journal date
        if j.posted_at is not None:
            j.posted_at = datetime.combine(j.date + timedelta(days=1), time(10, 0), tzinfo=UTC)
    return inp


def engine(w, **kw):
    return AiEngine(inputs(w, **kw), CHECK_NOW)


class GroundingContractTests(unittest.TestCase):
    good = None

    @classmethod
    def setUpClass(cls):
        cls.w = rich_world()
        cls.e = engine(cls.w)

    def item(self):
        import copy
        return copy.deepcopy(self.e.explain("journal", self.w.equipment.id)["items"][0])

    def test_real_item_passes_and_has_every_link(self):
        it = self.item()
        validate_item(it)
        for k in CHAIN:
            self.assertIn(k, it)

    def test_each_missing_link_is_refused(self):
        for k in CHAIN:
            it = self.item()
            del it[k]
            with self.assertRaises(UngroundedAnswerError, msg=k):
                validate_item(it)

    def test_empty_conclusion_and_no_sources_are_refused(self):
        it = self.item(); it["conclusion"]["summary"] = "  "
        with self.assertRaises(UngroundedAnswerError):
            validate_item(it)
        it = self.item(); it["source_records"] = []
        with self.assertRaises(UngroundedAnswerError):
            validate_item(it)
        it = self.item(); it["source_records"][0]["id"] = ""
        with self.assertRaises(UngroundedAnswerError):
            validate_item(it)

    def test_unavailable_stage_must_say_why(self):
        it = self.item(); it["reporting_framework"] = {"available": False}
        with self.assertRaises(UngroundedAnswerError):
            validate_item(it)

    def test_non_high_confidence_cannot_claim_review_is_optional(self):
        it = self.item(); it["confidence"] = grounding.confidence([{"factor": "x", "effect": -60, "detail": ""}])
        it["human_review"] = grounding.human_review(False, [])
        with self.assertRaises(UngroundedAnswerError):
            validate_item(it)

    def test_confidence_arithmetic_and_bands(self):
        c = grounding.confidence([{"factor": "a", "effect": -15, "detail": ""}, {"factor": "b", "effect": -5, "detail": ""}])
        self.assertEqual((c["score"], c["level"]), (80, "HIGH"))
        self.assertEqual(grounding.confidence([{"factor": "a", "effect": -20, "detail": ""}])["level"], "HIGH")
        self.assertEqual(grounding.confidence([{"factor": "a", "effect": -21, "detail": ""}])["level"], "MEDIUM")
        self.assertEqual(grounding.confidence([{"factor": "a", "effect": -51, "detail": ""}])["level"], "LOW")
        self.assertEqual(grounding.confidence([{"factor": "a", "effect": -500, "detail": ""}])["score"], 0)

    def test_every_response_is_plain_json(self):
        # FastAPI must be able to serialise it with no help (dates, decimals and enums are already text)
        e = self.e
        resps = [e.detect(limit=50), e.recommend(limit=50), e.ask("hello"), e.prove("figure", metric="net_income", period_id=self.w.period.id)]
        resps += [e.explain("journal", j.id) for j in e.journals] + [e.prove("journal", j.id) for j in e.posted]
        for t in e.inp.bank_transactions:
            resps += [e.explain("bank_transaction", t.id), e.prove("bank_transaction", t.id)]
        for r in resps:
            self.assertEqual(json.loads(json.dumps(r)), r)

    def test_every_item_in_every_mode_is_grounded(self):
        e = self.e
        resps = [e.explain("journal", j.id) for j in e.posted] + [e.detect(limit=50), e.recommend(limit=50),
                 e.prove("figure", metric="revenue", period_id=self.w.period.id)] + [e.prove("journal", j.id) for j in e.posted]
        n = 0
        for r in resps:
            self.assertTrue(r["grounded"])
            for it in r["items"]:
                n += 1
                validate_item(it)
                self.assertIn(it["confidence"]["level"], ("HIGH", "MEDIUM", "LOW"))
                self.assertTrue(0 <= it["confidence"]["score"] <= 100)
                if it["confidence"]["level"] != "HIGH":
                    self.assertTrue(it["human_review"]["required"], it["title"])
        self.assertGreater(n, 40)


class KnowledgeTests(unittest.TestCase):
    def test_nature_rules(self):
        c = knowledge.classify_nature(["EXPENSE"], ["ASSET"])
        self.assertEqual((c["code"], c["usual"]), ("EXPENSE_PAID", True))
        self.assertEqual(knowledge.classify_nature(["REVENUE"], ["ASSET"])["usual"], False)
        self.assertEqual(knowledge.classify_nature(["ASSET"], ["REVENUE", "LIABILITY"])["code"], "REVENUE_WITH_LIABILITY")
        self.assertEqual(knowledge.classify_nature(["ASSET"], ["ASSET"], reversal=True)["code"], "REVERSAL")
        self.assertEqual(knowledge.classify_nature([], ["ASSET"])["code"], "UNCLASSIFIED")
        # every pair of the five account types has a defined meaning
        types = ["ASSET", "LIABILITY", "EQUITY", "REVENUE", "EXPENSE"]
        for d in types:
            for c_ in types:
                self.assertIn((d, c_), knowledge.NATURE_TABLE, (d, c_))

    def test_wording_hints(self):
        self.assertEqual(knowledge.implied_type("January rent")[0], "EXPENSE")
        self.assertEqual(knowledge.implied_type("Salaries for March")[0], "EXPENSE")
        self.assertEqual(knowledge.implied_type("Equipment purchase")[0], "ASSET")
        self.assertEqual(knowledge.implied_type("Invoice 001 to Kadena")[0], None)
        self.assertEqual(knowledge.implied_type("")[0], None)
        self.assertEqual(knowledge.implied_type(None)[0], None)
        # stems match the start of a word only
        self.assertEqual(knowledge.words_hit("The parent company", ("rent",)), [])
        self.assertEqual(knowledge.words_hit("Rent, January", ("rent",)), ["rent"])


class ExplainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.w = rich_world()
        cls.e = engine(cls.w)

    def text(self, r):
        return json.dumps(r["items"][0], default=str)

    def test_rent_journal_explained_from_its_lines(self):
        r = self.e.explain("journal", self.w.rent_journal.id)
        it = r["items"][0]
        self.assertIn("an expense paid out of an asset", r["summary"])
        self.assertEqual(it["accounting_treatment"]["classification"]["code"], "EXPENSE_PAID")
        pts = " ".join(it["conclusion"]["points"])
        self.assertIn("5000 Rent", pts)
        self.assertIn("1000 Cash at bank", pts)
        self.assertIn("dara@meridian.test", pts)
        self.assertEqual(it["journal"]["number"], self.w.rent_journal.journal_number)
        self.assertEqual(it["journal"]["period"]["name"], "FY2026-M01")
        self.assertEqual(r["interpreted_as"]["subject_label"], self.w.rent_journal.journal_number)

    def test_who_chose_the_accounts_is_stated_honestly(self):
        pts = " ".join(self.e.explain("journal", self.w.equipment.id)["items"][0]["conclusion"]["points"])
        self.assertIn("ASAVEXA explains it rather than deciding it", pts)

    def test_verified_evidence_and_policy_are_cited(self):
        it = self.e.explain("journal", self.w.equipment.id)["items"][0]
        self.assertEqual(it["evidence"]["state"], "VERIFIED")
        self.assertTrue(it["evidence"]["available"])
        rec = it["evidence"]["records"][0]
        self.assertEqual(rec["sha256"], self.w.eq_ev.file_hash)
        self.assertEqual(rec["verified_by"], "kwame@meridian.test")
        codes = {p["code"] for p in it["accounting_treatment"]["policies"]}
        self.assertTrue({"PPE_MEASUREMENT", "DEPRECIATION_METHOD"} <= codes, codes)
        ppe = next(p for p in it["accounting_treatment"]["policies"] if p["code"] == "PPE_MEASUREMENT")
        self.assertEqual(ppe["effective"], "COST_MODEL")
        self.assertIn("Balance sheet", " ".join(it["reporting_framework"]["statements_affected"]))
        self.assertEqual(it["reporting_framework"]["framework_code"], self.e.standards["framework"])

    def test_clean_journal_has_high_confidence_and_no_review(self):
        # prepared and posted by different people, verified evidence, wording gives no signal
        it = self.e.explain("journal", self.w.invoice.id)["items"][0]
        self.assertEqual(it["confidence"]["level"], "HIGH")
        self.assertFalse(it["human_review"]["required"])
        self.assertEqual(it["confidence"]["score"], 95)

    def test_missing_evidence_same_person_lowers_confidence_and_requires_review(self):
        it = self.e.explain("journal", self.w.rent_journal.id)["items"][0]
        self.assertFalse(it["evidence"]["available"])
        self.assertIn("MISSING EVIDENCE", it["evidence"]["note"])
        self.assertEqual((it["confidence"]["score"], it["confidence"]["level"]), (55, "MEDIUM"))
        self.assertTrue(it["human_review"]["required"])
        joined = " ".join(it["human_review"]["reasons"])
        self.assertIn("same person", joined)

    def test_mismatch_is_reported_and_costs_confidence(self):
        it = self.e.explain("journal", self.w.mismatch.id)["items"][0]
        self.assertEqual(it["accounting_treatment"]["description_check"]["status"], "MISMATCH")
        self.assertIn("rent", it["accounting_treatment"]["description_check"]["detail"])
        self.assertLess(it["confidence"]["score"], 60)
        self.assertTrue(it["human_review"]["required"])

    def test_contra_pattern_is_called_unusual(self):
        r = self.e.explain("journal", self.w.refund.id)
        self.assertIn("not the usual direction", " ".join(r["items"][0]["conclusion"]["points"]))
        self.assertIn("income reduced", r["summary"])

    def test_unverified_and_rejected_evidence_states(self):
        self.assertEqual(self.e.explain("journal", self.w.refund.id)["items"][0]["evidence"]["state"], "UNVERIFIED")
        d = self.e.explain("journal", self.w.dividend.id)["items"][0]
        self.assertEqual(d["evidence"]["state"], "DEFECTIVE")
        self.assertEqual(d["evidence"]["records"][0]["rejection_reason"], "Unsigned")

    def test_without_a_framework_none_is_invented(self):
        e = engine(self.w, standards=None)
        it = e.explain("journal", self.w.equipment.id)["items"][0]
        self.assertFalse(it["reporting_framework"]["available"])
        self.assertIn("No reporting framework", it["reporting_framework"]["note"])
        self.assertNotIn("IFRS", json.dumps(it["reporting_framework"]))
        self.assertEqual(it["accounting_treatment"]["policies"], [])
        self.assertIn("No framework is configured", it["accounting_treatment"]["note"])
        self.assertEqual(it["confidence"]["score"], self.e.explain("journal", self.w.equipment.id)["items"][0]["confidence"]["score"] - 10)

    def test_draft_journal_is_explained_but_flagged(self):
        draft = next(j for j in self.e.journals if j.description == "Draft only")
        it = self.e.explain("journal", draft.id)["items"][0]
        self.assertEqual(it["journal"]["status"], "DRAFT")
        self.assertTrue(it["human_review"]["required"])
        self.assertIn("draft", " ".join(it["human_review"]["reasons"]).lower())

    def test_journal_found_by_number_case_insensitively(self):
        self.assertEqual(self.e.explain("journal", self.w.rent_journal.journal_number.lower())["items"][0]["journal"]["id"], self.w.rent_journal.id)

    def test_bank_line_matched_to_a_journal_is_explained_with_its_rule(self):
        t = next(t for t in self.e.inp.bank_transactions if t.description == "Deposit Kadena")
        r = self.e.explain("bank_transaction", t.id)
        it = r["items"][0]
        self.assertEqual(it["journal"]["id"], self.w.invoice.id)
        self.assertIn("EXACT_AMOUNT_AND_DATE_WITHIN_TOLERANCE", " ".join(it["conclusion"]["points"]))
        self.assertEqual(r["interpreted_as"]["subject_type"], "bank_transaction")

    def test_unmatched_bank_line_has_no_journal_and_says_so(self):
        t = next(t for t in self.e.inp.bank_transactions if t.description == "Unknown debit")
        it = self.e.explain("bank_transaction", t.id)["items"][0]
        self.assertFalse(it["journal"]["available"])
        self.assertIn("not matched to a journal", it["journal"]["note"])
        self.assertFalse(it["accounting_treatment"]["available"])
        self.assertTrue(it["human_review"]["required"])
        self.assertIn("money out", " ".join(it["conclusion"]["points"]))

    def test_errors(self):
        with self.assertRaises(AiSubjectNotFoundError):
            self.e.explain("journal", "JRN-999999")
        with self.assertRaises(AiSubjectNotFoundError):
            self.e.explain("bank_transaction", "nope")
        with self.assertRaises(AiValidationError):
            self.e.explain("journal", "  ")
        with self.assertRaises(AiValidationError):
            self.e.explain("account", "x")


class DetectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.w = rich_world()
        cls.e = engine(cls.w)
        cls.d = cls.e.detect(limit=50)

    def flags(self, jid):
        for it in self.d["items"]:
            if it.get("kind") == "JOURNAL" and it["journal"]["id"] == jid:
                return {f["rule"] for f in it["flags"]}
        return set()

    def test_each_planted_anomaly_is_found_for_the_right_reason(self):
        self.assertIn("AMOUNT_OUTLIER", self.flags(self.w.equipment.id))
        self.assertIn("DUPLICATE_POSSIBLE", self.flags(self.w.internet2.id))
        self.assertIn("CONTRA_PAIRING", self.flags(self.w.refund.id))
        self.assertIn("DESCRIPTION_MISMATCH", self.flags(self.w.mismatch.id))
        self.assertIn("OWNER_MOVEMENT", self.flags(self.w.dividend.id))
        self.assertIn("SAME_PERSON_PREPARED_AND_POSTED", self.flags(self.w.rent_journal.id))

    def test_the_first_of_a_duplicate_pair_and_routine_journals_are_not_flagged(self):
        self.assertEqual(self.flags(self.w.internet1.id), set())
        for j in self.w.routine:
            self.assertEqual(self.flags(j.id), set(), j.journal_number)

    def test_duplicate_flag_names_the_other_journal(self):
        it = next(i for i in self.d["items"] if i.get("kind") == "JOURNAL" and i["journal"]["id"] == self.w.internet2.id)
        f = next(x for x in it["flags"] if x["rule"] == "DUPLICATE_POSSIBLE")
        self.assertIn(self.w.internet1.journal_number, f["detail"])

    def test_secondary_signals_alone_never_create_an_item(self):
        # weekend/round/evidence-gap/reversal are only aggravating
        for it in self.d["items"]:
            self.assertTrue(any(f["primary"] for f in it["flags"]), it["title"])

    def test_ordering_severity_and_summary(self):
        scores = [i["score"] for i in self.d["items"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        for i in self.d["items"]:
            self.assertEqual(i["severity"], "HIGH" if i["score"] >= 60 else "MEDIUM" if i["score"] >= 35 else "LOW")
        self.assertEqual(self.d["total_flagged"], len(self.d["items"]))
        self.assertIn("worth a look", self.d["summary"])
        self.assertEqual(sum(self.d["severity_counts"].values()), self.d["total_flagged"])

    def test_every_flag_requires_a_person_and_wording_is_not_an_accusation(self):
        for it in self.d["items"]:
            self.assertTrue(it["human_review"]["required"])
        text = json.dumps(self.d).lower()
        self.assertNotIn("fraud", text.replace("a finding of error or fraud", ""))
        self.assertIn("not 'wrong'", " ".join(self.d["limitations"]))

    def test_statistical_flags_cost_confidence(self):
        it = next(i for i in self.d["items"] if i.get("kind") == "JOURNAL" and i["journal"]["id"] == self.w.equipment.id)
        self.assertTrue(any(f["factor"] == "Statistical flag" for f in it["confidence"]["factors"]))

    def test_rules_are_published(self):
        codes = {r["code"] for r in self.d["rules"]}
        self.assertTrue({"AMOUNT_OUTLIER", "DUPLICATE_POSSIBLE", "CONTRA_PAIRING", "BANK_LINE_UNMATCHED"} <= codes)

    def test_unmatched_bank_line_is_flagged(self):
        b = [i for i in self.d["items"] if i.get("kind") == "BANK_TRANSACTION"]
        self.assertTrue(any("Unknown debit" in i["title"] and i["severity"] == "LOW" for i in b))

    def test_limit_and_period_filter(self):
        d3 = self.e.detect(limit=3)
        self.assertEqual(len(d3["items"]), 3)
        self.assertIn("Showing the top 3", d3["summary"])
        feb = self.e.detect(period_id=self.w.empty_period.id)
        ids = {i["journal"]["id"] for i in feb["items"] if i.get("kind") == "JOURNAL"}
        self.assertEqual(ids, {self.w.dividend.id} & ids)       # only February journals can appear
        self.assertNotIn(self.w.equipment.id, ids)
        with self.assertRaises(AiValidationError):
            self.e.detect(limit=0)
        with self.assertRaises(AiValidationError):
            self.e.detect(limit=51)
        with self.assertRaises(AiSubjectNotFoundError):
            self.e.detect(period_id="nope")

    def test_small_sample_disables_outlier_detection_and_says_so(self):
        w = World()
        e = engine(w)
        d = e.detect()
        self.assertTrue(any("Outlier detection needs" in x for x in d["limitations"]))
        for it in d["items"]:
            self.assertNotIn("AMOUNT_OUTLIER", {f["rule"] for f in it["flags"]})

    def test_clean_books_report_nothing_honestly(self):
        w = World()
        a, o = w.accounting, w.org.id
        j = a.create_draft_journal(o, date(2026, 1, 8), "Electricity bill", "NGN", [
            LineInput(w.rent.id, debit_amount=Decimal("5100.00")), LineInput(w.cash.id, credit_amount=Decimal("5100.00"))], created_by=w.accountant.id)
        a.post_journal(o, j.id, actor=w.approver.id)
        inp = inputs(w)
        # keep only the clean journal and no bank data
        inp.journals = [x for x in inp.journals if x.id == j.id]
        inp.bank_transactions, inp.reconciliations = [], []
        d = AiEngine(inp, CHECK_NOW).detect()
        self.assertEqual(d["items"], [])
        self.assertIn("not a guarantee", d["summary"])

    def test_backdated_and_future_dated_posting(self):
        inp = inputs(self.w)
        j = next(x for x in inp.journals if x.id == self.w.routine[0].id)
        j.posted_at = datetime.combine(j.date + timedelta(days=90), time(9), tzinfo=UTC)
        k = next(x for x in inp.journals if x.id == self.w.routine[1].id)
        k.posted_at = datetime.combine(k.date - timedelta(days=10), time(9), tzinfo=UTC)
        d = AiEngine(inp, CHECK_NOW).detect(limit=50)
        rules = {i["journal"]["id"]: {f["rule"] for f in i["flags"]} for i in d["items"] if i.get("kind") == "JOURNAL"}
        self.assertIn("BACKDATED_POSTING", rules[j.id])
        self.assertIn("FUTURE_DATED", rules[k.id])

    def test_a_journal_dated_outside_its_period_is_flagged(self):
        inp = inputs(self.w)
        j = next(x for x in inp.journals if x.id == self.w.routine[2].id)
        j.date = date(2026, 3, 15)
        d = AiEngine(inp, CHECK_NOW).detect(limit=50)
        it = next(i for i in d["items"] if i.get("kind") == "JOURNAL" and i["journal"]["id"] == j.id)
        self.assertIn("PERIOD_MISMATCH", {f["rule"] for f in it["flags"]})

    def test_reversals_do_not_trigger_duplicate_or_contra_flags(self):
        w = rich_world()
        w.accounting.reverse_journal(w.org.id, w.routine[0].id, actor=w.owner.id, reason="entered twice",
                                     reversal_date=date(2026, 1, 20))
        d = engine(w).detect(limit=50)
        for it in d["items"]:
            if it.get("kind") == "JOURNAL" and it["journal"]["reversal_of"]:
                self.assertNotIn("CONTRA_PAIRING", {f["rule"] for f in it["flags"]})
                self.assertNotIn("DUPLICATE_POSSIBLE", {f["rule"] for f in it["flags"]})


class RecommendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        w = cls.w = rich_world()
        a, o = w.accounting, w.org.id
        cls.rec = w.recon.create_reconciliation(o, w.cash.id, "February", date(2026, 2, 1), date(2026, 2, 28), actor=w.accountant.id)
        sales = w.post(date(2026, 2, 10), "Feb sales", w.cash, w.rev, "500000")
        fee = w.post(date(2026, 2, 20), "Card fees", w.chg, w.cash, "1130.00")
        c1 = w.post(date(2026, 2, 13), "Office cleaning", w.util, w.cash, "20000")
        c2 = w.post(date(2026, 2, 15), "Security services", w.util, w.cash, "20000")
        cls.fee = fee
        w.recon.import_transactions(o, cls.rec.id, [
            BankTransactionInput(date(2026, 2, 12), "Deposit", debit_amount=Decimal("500000.00"), currency="NGN"),
            BankTransactionInput(date(2026, 2, 20), "Card payment fee", credit_amount=Decimal("1150.00"), currency="NGN"),
            BankTransactionInput(date(2026, 2, 25), "Utilities payment", credit_amount=Decimal("9999.00"), currency="NGN"),
            BankTransactionInput(date(2026, 2, 14), "Transfer", credit_amount=Decimal("20000.00"), currency="NGN"),
        ], actor=w.accountant.id, import_source="bank_feed")
        cls.e = engine(w)
        cls.r = cls.e.recommend(limit=50)
        cls.tx = {t.description: t for t in cls.e.inp.bank_transactions}

    def by_kind(self, kind):
        return [i for i in self.r["items"] if i["proposal"]["kind"] == kind]

    def test_scenario_statuses_are_what_the_tests_assume(self):
        self.assertEqual(B(self.tx["Deposit"].status), "MATCHED")
        self.assertEqual(B(self.tx["Card payment fee"].status), "UNMATCHED")
        self.assertEqual(B(self.tx["Utilities payment"].status), "UNMATCHED")
        self.assertEqual(B(self.tx["Transfer"].status), "REVIEW_REQUIRED")

    def test_ambiguous_line_gets_a_choice_not_a_decision(self):
        it = next(i for i in self.by_kind("MATCH_BANK_TRANSACTION") if i["proposal"]["bank_transaction_id"] == self.tx["Transfer"].id)
        self.assertIn("More than one journal fits", {f["factor"] for f in it["confidence"]["factors"]})
        self.assertIn("a person must choose", " ".join(it["human_review"]["reasons"]))
        names = {r["label"] for r in it["source_records"] if r["kind"] == "JOURNAL"}
        self.assertEqual(len(names), 2)
        self.assertLess(it["priority"], 72)

    def test_difference_proposes_a_balanced_unposted_entry(self):
        it = next(i for i in self.by_kind("ADJUST_DIFFERENCE") if i["proposal"]["bank_transaction_id"] == self.tx["Card payment fee"].id)
        pe = it["proposal"]["proposed_entry"]
        self.assertEqual(it["proposal"]["journal_id"], self.fee.id)
        debit = sum(Decimal(l["amount"]) for l in pe["lines"] if l["side"] == "debit")
        credit = sum(Decimal(l["amount"]) for l in pe["lines"] if l["side"] == "credit")
        self.assertEqual((debit, credit), (Decimal("20.00"), Decimal("20.00")))
        self.assertFalse(pe["needs_account_choice"])
        self.assertIn("Bank charges", json.dumps(pe))
        self.assertIs(it["proposal"]["applied"], False)
        self.assertTrue(it["accounting_treatment"]["available"])
        self.assertTrue(it["accounting_treatment"]["proposed"])

    def test_unrecorded_bank_line_proposes_a_draft_with_a_hinted_account(self):
        it = next(i for i in self.by_kind("RECORD_BANK_LINE") if i["proposal"]["bank_transaction_id"] == self.tx["Utilities payment"].id)
        lines = it["proposal"]["proposed_entry"]["lines"]
        self.assertEqual({l["side"] for l in lines}, {"debit", "credit"})
        self.assertIn("Electricity and utilities", json.dumps(lines))
        credit_line = next(l for l in lines if l["side"] == "credit")
        self.assertIn("Cash at bank", credit_line["account"])           # money went out of the bank
        self.assertIn("hint, not a decision", " ".join(it["conclusion"]["points"]))
        self.assertFalse(it["journal"]["available"])
        self.assertEqual(it["confidence"]["level"] in ("LOW", "MEDIUM"), True)

    def test_unknown_counter_account_must_be_chosen_by_a_person(self):
        t = self.tx["Utilities payment"]
        inp = inputs(self.w)
        for tx in inp.bank_transactions:
            if tx.id == t.id:
                tx.description = "Payment 7781"
        r = AiEngine(inp, CHECK_NOW).recommend(scope="reconciliation", limit=50)
        it = next(i for i in r["items"] if i["proposal"]["kind"] == "RECORD_BANK_LINE" and i["proposal"]["bank_transaction_id"] == t.id)
        self.assertTrue(it["proposal"]["proposed_entry"]["needs_account_choice"])
        self.assertFalse(it["accounting_treatment"]["available"])

    def test_reconciliation_gap_is_explained_by_the_unmatched_items(self):
        it = self.by_kind("RECONCILE_DIFFERENCE")
        feb = next(i for i in it if "February" in i["title"])
        pts = " ".join(feb["conclusion"]["points"])
        self.assertIn("92481.00", pts)   # 9,981 from the two February differences + the 82,500 dividend paid from the same account
        self.assertIn("fully explain", pts)
        self.assertFalse(feb["journal"]["available"])
        self.assertEqual(feb["proposal"]["where"], f"/reconciliation/{self.rec.id}")

    def test_evidence_recommendations(self):
        kinds = {i["proposal"]["kind"] for i in self.r["items"]}
        self.assertTrue({"ATTACH_EVIDENCE", "VERIFY_EVIDENCE", "REPLACE_EVIDENCE"} <= kinds, kinds)
        v = next(i for i in self.by_kind("VERIFY_EVIDENCE") if i["proposal"]["journal_id"] == self.w.refund.id)
        self.assertIn("other than aisha@meridian.test", v["proposal"]["action"])
        a = next(i for i in self.by_kind("ATTACH_EVIDENCE") if i["proposal"]["journal_id"] == self.w.rent_journal.id)
        self.assertIn("invoice or receipt", a["proposal"]["action"])

    def test_reclassification_proposal_for_a_mismatch(self):
        it = next(i for i in self.by_kind("RECLASSIFY") if i["proposal"]["journal_id"] == self.w.mismatch.id)
        pe = it["proposal"]["proposed_entry"]
        self.assertIsNotNone(pe)
        by_side = {l["side"]: l for l in pe["lines"]}
        self.assertIn("5000 Rent", by_side["debit"]["account"])
        self.assertIn("1500 Office equipment", by_side["credit"]["account"])
        self.assertEqual(by_side["debit"]["amount"], "150000.00")

    def test_contra_pattern_asks_for_confirmation_only(self):
        it = next(i for i in self.by_kind("CONFIRM_DIRECTION") if i["proposal"]["journal_id"] == self.w.refund.id)
        self.assertIsNone(it["proposal"]["proposed_entry"])

    def test_every_recommendation_is_an_unapplied_proposal_needing_a_person(self):
        self.assertGreater(len(self.r["items"]), 8)
        for i in self.r["items"]:
            self.assertIs(i["proposal"]["applied"], False)
            self.assertTrue(i["human_review"]["required"])
            self.assertIn("never posts, matches or changes", i["human_review"]["reasons"][0])
            if i["proposal"]["proposed_entry"]:
                lines = i["proposal"]["proposed_entry"]["lines"]
                self.assertEqual(sum(Decimal(l["amount"]) for l in lines if l["side"] == "debit"),
                                 sum(Decimal(l["amount"]) for l in lines if l["side"] == "credit"))
        pr = [i["priority"] for i in self.r["items"]]
        self.assertEqual(pr, sorted(pr, reverse=True))

    def test_recommending_changes_nothing(self):
        def snapshot(w):
            c = w.conn
            return [c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("journals", "journal_lines", "evidence_records",
                    "bank_transactions", "reconciliations", "audit_events")]
        before = snapshot(self.w)
        e = engine(self.w)
        e.recommend(limit=50); e.detect(limit=50); e.explain("journal", self.w.equipment.id); e.prove("journal", self.w.equipment.id)
        e.ask("Suggest a reconciliation or adjustment.")
        self.assertEqual(snapshot(self.w), before)

    def test_scope_and_period_filters_and_validation(self):
        ev = self.e.recommend(scope="evidence", limit=50)
        self.assertTrue(ev["items"] and all(i["proposal"]["kind"].endswith("EVIDENCE") for i in ev["items"]))
        rc = self.e.recommend(scope="reconciliation", limit=50)
        self.assertTrue(all(i["proposal"]["kind"] in ("MATCH_BANK_TRANSACTION", "ADJUST_DIFFERENCE", "RECORD_BANK_LINE", "RECONCILE_DIFFERENCE") for i in rc["items"]))
        jan = self.e.recommend(scope="evidence", period_id=self.w.period.id, limit=50)
        feb = self.e.recommend(scope="evidence", period_id=self.w.empty_period.id, limit=50)
        self.assertTrue(set(i["journal"]["id"] for i in jan["items"]).isdisjoint(i["journal"]["id"] for i in feb["items"]))
        with self.assertRaises(AiValidationError):
            self.e.recommend(scope="everything")
        with self.assertRaises(AiSubjectNotFoundError):
            self.e.recommend(period_id="nope")

    def test_a_tidy_ledger_yields_no_recommendation(self):
        w = World()
        inp = inputs(w)
        inp.journals = [j for j in inp.journals if False]
        inp.bank_transactions, inp.reconciliations, inp.evidence = [], [], []
        r = AiEngine(inp, CHECK_NOW).recommend()
        self.assertEqual(r["items"], [])
        self.assertIn("No recommendation", r["summary"])


def B(x):
    return getattr(x, "value", x)


class ProveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.w = rich_world()
        cls.e = engine(cls.w)

    def test_verified_journal_is_proven(self):
        r = self.e.prove("journal", self.w.equipment.id)
        self.assertEqual(r["verdict"], "PROVEN")
        it = r["items"][0]
        crit = [c for c in it["checks"] if c["critical"]]
        self.assertTrue(crit and all(c["result"] == "PASS" for c in crit))
        by = {c["key"]: c for c in it["checks"]}
        self.assertEqual(by["EVIDENCE_HASH"]["detail"], self.w.eq_ev.file_hash)
        self.assertEqual(by["VERIFIER_INDEPENDENT"]["result"], "PASS")
        self.assertEqual(by["POSTER_INDEPENDENT"]["result"], "PASS")

    def test_unverified_evidence_is_partial_and_missing_or_rejected_is_not_proven(self):
        self.assertEqual(self.e.prove("journal", self.w.refund.id)["verdict"], "PARTIALLY_PROVEN")
        self.assertEqual(self.e.prove("journal", self.w.rent_journal.id)["verdict"], "NOT_PROVEN")
        self.assertEqual(self.e.prove("journal", self.w.dividend.id)["verdict"], "NOT_PROVEN")

    def test_a_proof_that_is_not_complete_requires_review_and_lists_what_failed(self):
        r = self.e.prove("journal", self.w.rent_journal.id)
        it = r["items"][0]
        self.assertTrue(it["human_review"]["required"])
        self.assertIn("MISSING EVIDENCE", [c for c in it["checks"] if c["key"] == "HAS_EVIDENCE"][0]["detail"])
        self.assertIn("Not passing", r["summary"])

    def test_a_proven_summary_admits_a_failing_non_critical_check(self):
        inp = inputs(self.w)
        j = next(x for x in inp.journals if x.id == self.w.equipment.id)
        j.posted_by = j.created_by                                    # break maker-checker only
        it = AiEngine(inp, CHECK_NOW).prove("journal", j.id)["items"][0]
        self.assertEqual(it["verdict"], "PROVEN")
        self.assertIn("but not", it["conclusion"]["summary"])
        self.assertTrue(it["human_review"]["required"])

    def test_unbalanced_data_cannot_be_proven(self):
        inp = inputs(self.w)
        j = next(x for x in inp.journals if x.id == self.w.equipment.id)
        j.lines[0].debit_amount = j.lines[0].debit_amount + Decimal("1.00")
        r = AiEngine(inp, CHECK_NOW).prove("journal", j.id)
        self.assertNotEqual(r["verdict"], "PROVEN")
        self.assertEqual({c["key"]: c for c in r["items"][0]["checks"]}["BALANCED"]["result"], "FAIL")

    def test_bank_line_proof(self):
        t = next(t for t in self.e.inp.bank_transactions if t.description == "Deposit Kadena")
        r = self.e.prove("bank_transaction", t.id)
        keys = {c["key"]: c["result"] for c in r["items"][0]["checks"]}
        self.assertEqual(keys["MATCHED"], "PASS")
        self.assertEqual(keys["AMOUNT_AGREES"], "PASS")
        self.assertEqual(keys["STATUS_FINAL"], "FAIL")          # matched but not yet approved
        self.assertNotEqual(r["verdict"], "PROVEN")
        u = next(t for t in self.e.inp.bank_transactions if t.description == "Unknown debit")
        ru = self.e.prove("bank_transaction", u.id)
        self.assertEqual(ru["verdict"], "NOT_PROVEN")
        self.assertFalse(ru["items"][0]["journal"]["available"])

    def test_figure_proof_matches_the_reporting_module(self):
        w = self.w
        for metric, rep in (("revenue", "total_revenue"), ("expenses", "total_expenses")):
            r = self.e.prove("figure", metric=metric, period_id=w.period.id)
            reported = getattr(w.reporting.get_income_statement(w.org.id, w.period.id, w.owner.id), rep)
            self.assertEqual(Decimal(r["items"][0]["figure"]["reported"]), Decimal(str(reported)), metric)
            sums = sum(Decimal(c["contribution"]) for c in r["items"][0]["contributions"])
            self.assertEqual(sums, Decimal(str(reported)))
            self.assertEqual({c["key"]: c["result"] for c in r["items"][0]["checks"]}["SUM_AGREES"], "PASS")

    def test_figure_coverage_by_evidence(self):
        r = self.e.prove("figure", metric="revenue", period_id=self.w.period.id)
        it = r["items"][0]
        # January revenue = invoice (verified) + the refund (negative, unverified)
        self.assertEqual(it["evidence"]["coverage"]["journals"], 2)
        self.assertEqual(it["verdict"], "PARTIALLY_PROVEN")
        self.assertLess(it["confidence"]["score"], 100)
        self.assertTrue(it["human_review"]["required"])

    def test_fully_verified_figure_is_proven_with_high_confidence(self):
        w = World()
        e = AiEngine(inputs(w), CHECK_NOW)
        r = e.prove("figure", metric="revenue", period_id=w.period.id)
        self.assertEqual(r["verdict"], "PROVEN")
        self.assertEqual(r["items"][0]["confidence"]["level"], "HIGH")
        self.assertFalse(r["items"][0]["human_review"]["required"])
        self.assertIn("100.0%", r["summary"])

    def test_empty_period_has_nothing_to_prove(self):
        r = self.e.prove("figure", metric="revenue", period_id=self.w.empty_period.id)
        self.assertEqual(r["verdict"], "NOT_PROVEN")
        self.assertIn("Nothing to prove", r["summary"])
        self.assertEqual(r["items"][0]["confidence"]["level"], "LOW")

    def test_proof_errors(self):
        with self.assertRaises(AiValidationError):
            self.e.prove("figure", metric="profit", period_id=self.w.period.id)
        with self.assertRaises(AiValidationError):
            self.e.prove("figure", metric="revenue")
        with self.assertRaises(AiSubjectNotFoundError):
            self.e.prove("figure", metric="revenue", period_id="nope")
        with self.assertRaises(AiValidationError):
            self.e.prove("widget", "x")
        with self.assertRaises(AiSubjectNotFoundError):
            self.e.prove("journal", "JRN-424242")


class AskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.w = rich_world()
        cls.e = engine(cls.w)

    def mode(self, q):
        r = self.e.ask(q)
        return r["interpreted_as"].get("mode"), r

    def test_the_four_blueprint_questions_route_correctly(self):
        n = self.w.rent_journal.journal_number
        self.assertEqual(self.mode(f"Why was {n} classified this way?")[0], "EXPLAIN")
        self.assertEqual(self.mode("Find unusual transactions.")[0], "DETECT")
        self.assertEqual(self.mode("Suggest a reconciliation or adjustment.")[0], "RECOMMEND")
        self.assertEqual(self.mode(f"Show the evidence supporting {n}")[0], "PROVE")

    def test_interpretation_is_shown_and_answer_is_grounded(self):
        m, r = self.mode(f"why was {self.w.equipment.journal_number.lower()} classified")
        self.assertEqual(r["interpreted_as"]["subject_id"], self.w.equipment.id)
        self.assertTrue(r["grounded"])
        self.assertEqual(r["question"], f"why was {self.w.equipment.journal_number.lower()} classified")

    def test_figure_questions(self):
        m, r = self.mode("Prove revenue for FY2026-M01")
        self.assertEqual((m, r["items"][0]["figure"]["metric"], r["interpreted_as"]["subject_id"]), ("PROVE", "revenue", self.w.period.id))
        m, r = self.mode("Show evidence for expenses")        # two active periods -> must ask which
        self.assertFalse(r["grounded"])
        self.assertIn("Which period", r["refusal"]["reason"])

    def test_id_references_work(self):
        t = next(t for t in self.e.inp.bank_transactions if t.description == "Unknown debit")
        m, r = self.mode(f"Why is {t.id} like this?")
        self.assertEqual((m, r["interpreted_as"]["subject_type"]), ("EXPLAIN", "bank_transaction"))
        m, r = self.mode(f"Explain {self.w.equipment.id}")
        self.assertEqual(r["interpreted_as"]["subject_type"], "journal")

    def test_period_and_scope_are_read_from_the_question(self):
        m, r = self.mode("Find unusual transactions in FY2026-M02")
        self.assertEqual(r["interpreted_as"]["subject_label"], "FY2026-M02")
        m, r = self.mode("Suggest evidence to attach")
        self.assertEqual(r["interpreted_as"]["scope"], "evidence")

    def test_what_it_cannot_do_it_refuses_instead_of_guessing(self):
        for q in ("hello there", "What will revenue be next year?"):
            r = self.e.ask(q)
            self.assertFalse(r["grounded"], q)
            self.assertEqual(r["items"], [])
            self.assertTrue(r["refusal"]["can_do"] or r["refusal"]["reason"])
        r = self.e.ask("Why was JRN-999999 classified this way?")
        self.assertFalse(r["grounded"])
        self.assertIn("JRN-999999", r["refusal"]["reason"])
        r = self.e.ask("Why was this classified this way?")
        self.assertFalse(r["grounded"])
        self.assertTrue(r["refusal"]["can_do"])         # suggests real journals to pick from

    def test_empty_or_oversized_questions_are_rejected(self):
        with self.assertRaises(AiValidationError):
            self.e.ask("   ")
        with self.assertRaises(AiValidationError):
            self.e.ask("x" * 501)


class DeterminismAndIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.w = rich_world()

    def test_same_records_same_answer(self):
        a = engine(self.w).detect(limit=50)
        b = engine(self.w).detect(limit=50)
        self.assertEqual(a["fingerprint"], b["fingerprint"])
        self.assertNotEqual(a["response_id"], b["response_id"])
        self.assertEqual(engine(self.w).explain("journal", self.w.equipment.id)["fingerprint"],
                         engine(self.w).explain("journal", self.w.equipment.id)["fingerprint"])

    def test_changed_records_change_the_fingerprint(self):
        before = engine(self.w).prove("figure", metric="revenue", period_id=self.w.period.id)["fingerprint"]
        inp = inputs(self.w)
        inp.evidence = [e for e in inp.evidence if e.linked_journal_id != self.w.invoice.id]
        after = AiEngine(inp, CHECK_NOW).prove("figure", metric="revenue", period_id=self.w.period.id)["fingerprint"]
        self.assertNotEqual(before, after)

    def test_another_organisation_sees_none_of_this_data(self):
        e = AiEngine(inputs(self.w, org_id=self.w.other_org.id), CHECK_NOW)
        d = e.detect(limit=50)
        self.assertEqual(d["items"], [])
        text = json.dumps([d, e.recommend(limit=50), e.ask("Find unusual transactions.")], default=str)
        for j in self.w.routine + [self.w.equipment, self.w.refund]:
            self.assertNotIn(j.id, text)
            self.assertNotIn(j.journal_number, text)
        with self.assertRaises(AiSubjectNotFoundError):
            e.explain("journal", self.w.equipment.id)
        with self.assertRaises(AiSubjectNotFoundError):
            e.prove("journal", self.w.equipment.id)

    def test_modes_are_the_four_in_the_blueprint(self):
        self.assertEqual(set(MODES), {"EXPLAIN", "DETECT", "RECOMMEND", "PROVE"})

    def test_ai_questions_are_kept_out_of_the_passport_audit_trail(self):
        w = self.w
        from asavexa.audit.models import AuditEvent
        for action in ("AI_EXPLAIN", "PASSPORT_GENERATED", "JOURNAL_POSTED"):
            w.audit.record(AuditEvent(id=f"00000000-0000-4000-8000-{abs(hash(action)) % 10**12:012d}", org_id=w.org.id, entity_type="X",
                                      entity_id="00000000-0000-4000-8000-000000000001", action=action, actor=w.owner.id, timestamp=NOW))
        events, _ = w.audit.list_recent_for_org(w.org.id, 5000, exclude_action_prefix=("PASSPORT_", "AI_"))
        acts = {e.action for e in events}
        self.assertIn("JOURNAL_POSTED", acts)
        self.assertNotIn("AI_EXPLAIN", acts)
        self.assertNotIn("PASSPORT_GENERATED", acts)
        events, _ = w.audit.list_recent_for_org(w.org.id, 5000, exclude_action_prefix="PASSPORT_")
        self.assertIn("AI_EXPLAIN", {e.action for e in events})


class RobustnessTests(unittest.TestCase):
    """Odd or incomplete data must produce an honest answer, never a crash."""

    @classmethod
    def setUpClass(cls):
        cls.w = rich_world()

    def run_everything(self, inp):
        e = AiEngine(inp, CHECK_NOW)
        out = [e.detect(limit=50), e.recommend(limit=50), e.ask("Find unusual transactions"), e.ask("Suggest a reconciliation or adjustment")]
        for j in e.journals[:12]:
            out += [e.explain("journal", j.id), e.prove("journal", j.id)]
        for t in e.inp.bank_transactions:
            out += [e.explain("bank_transaction", t.id), e.prove("bank_transaction", t.id)]
        for p in e.inp.periods:
            for m in ("revenue", "expenses", "net_income", "assets", "liabilities"):
                out.append(e.prove("figure", metric=m, period_id=p.id))
        for r in out:
            for it in r["items"]:
                validate_item(it)
        return out

    def test_accounts_missing_from_the_chart(self):
        inp = inputs(self.w)
        inp.accounts = inp.accounts[:2]                 # most journals now reference unknown accounts
        self.run_everything(inp)

    def test_no_periods_no_evidence_no_standards(self):
        inp = inputs(self.w, standards=None)
        inp.periods, inp.evidence = [], []
        self.run_everything(inp)

    def test_bank_lines_without_reconciliation_or_account(self):
        inp = inputs(self.w)
        inp.reconciliations = []
        for t in inp.bank_transactions:
            t.bank_account_id = "00000000-0000-4000-8000-00000000dead"
        self.run_everything(inp)

    def test_naive_timestamps_and_missing_users(self):
        inp = inputs(self.w)
        for j in inp.journals:
            if j.posted_at:
                j.posted_at = j.posted_at.replace(tzinfo=None)
            j.created_at = j.created_at.replace(tzinfo=None) if j.created_at else None
        inp.user_labels = {}
        self.run_everything(inp)

    def test_completely_empty_organisation(self):
        from asavexa.passport.builder import PassportInputs
        e = AiEngine(PassportInputs(org_id="o1"), CHECK_NOW)
        self.assertEqual(e.detect()["items"], [])
        self.assertEqual(e.recommend()["items"], [])
        self.assertFalse(e.ask("Why was JRN-000001 classified this way?")["grounded"])
        self.assertFalse(e.ask("Find unusual transactions")["items"])

    def test_large_ledger_is_answered_quickly(self):
        import time
        inp = inputs(self.w)
        base = list(inp.journals)
        import copy
        for k in range(150):
            for j in base[:12]:
                c = copy.copy(j)
                c.id = f"{k:04d}{j.id[4:]}"
                c.journal_number = f"JRN-9{k:03d}{j.journal_number[-2:]}"
                inp.journals.append(c)
        t = time.time()
        e = AiEngine(inp, CHECK_NOW)
        e.detect(limit=20); e.recommend(limit=15)
        self.assertLess(time.time() - t, 10)


if __name__ == "__main__":
    unittest.main()
