"""Tax Compliance: the registry, rule review (separation of duties), exact arithmetic, effective dating, the calendar and organisation isolation.
Every rate in these tests is an invented test value; ASAVEXA itself ships with no tax rates."""
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

from analysis_fixture import ORG, OTHER, PREP, PREP2, REVIEWER, World
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.permissions import ROLE_PERMISSIONS, TAX_APPROVE, TAX_PREPARE
from asavexa.tax import engine
from asavexa.tax.countries import BY_CODE, COUNTRIES
from asavexa.tax.errors import TaxError, TaxForbiddenError, TaxNotFoundError, TaxStateError
from asavexa.tax.service import TaxService

SRC = dict(authority="Test Revenue Authority", source_title="Test Act 2026, section 5", source_url="https://example.org/act/5")


def flat(country="NG", rate="7.5", frm="2026-01-01", to=None, name="Test VAT", **kw):
    b = dict(country=country, tax_type="VAT_GST", name=name, method="FLAT", rate=rate, effective_from=frm, effective_to=to, **SRC)
    b.update(kw); return b


BANDS = [{"from": "0", "up_to": "1000", "rate": "0"}, {"from": "1000", "up_to": "5000", "rate": "10"}, {"from": "5000", "up_to": None, "rate": "20"}]


class Base(unittest.TestCase):
    def setUp(self):
        self.w = World(); self.events = []
        self.now = datetime(2026, 3, 1, tzinfo=timezone.utc)
        self.s = TaxService(self.w.store, self.w.acc, log=lambda *a, **k: self.events.append(a), now=lambda: self.now)

    def live(self, body=None, org=ORG):
        r = self.s.create_rule(org, body or flat(), PREP); self.s.submit_rule(org, r["id"], PREP)
        return self.s.approve_rule(org, r["id"], REVIEWER, "checked against the source")


class Registry(Base):
    def test_every_country_once_with_currency(self):
        codes = [c[0] for c in COUNTRIES]
        self.assertGreaterEqual(len(codes), 190); self.assertEqual(len(codes), len(set(codes)))
        self.assertTrue(all(len(c[0]) == 2 and len(c[2]) == 3 for c in COUNTRIES))
        for code in ("NG", "GH", "KE", "ZA", "US", "GB", "IN", "BR", "JP", "FR", "AU", "AE", "CA", "MX"): self.assertIn(code, BY_CODE)

    def test_search_filter_and_no_rules_by_default(self):
        r = self.s.countries(ORG, q="nig")
        self.assertEqual({c["code"] for c in r["countries"]}, {"NG", "NE"})
        self.assertEqual(self.s.countries(ORG, q="NG")["countries"][0]["code"], "NG")
        self.assertTrue(all(c["region"] == "Africa" for c in self.s.countries(ORG, region="africa")["countries"]))
        self.assertEqual(self.s.countries(ORG)["with_rules"], 0)
        self.assertTrue(all(c["rules_in_force"] == 0 for c in self.s.countries(ORG)["countries"]))

    def test_select_and_remove_country_is_audited_and_isolated(self):
        self.s.set_jurisdiction(ORG, "ng", True, "TIN-123", PREP)
        c = [x for x in self.s.countries(ORG)["countries"] if x["code"] == "NG"][0]
        self.assertTrue(c["selected"]); self.assertEqual(c["registration"], "TIN-123")
        self.assertFalse([x for x in self.s.countries(OTHER)["countries"] if x["code"] == "NG"][0]["selected"])
        self.s.set_jurisdiction(ORG, "NG", False, "", PREP)
        self.assertFalse([x for x in self.s.countries(ORG)["countries"] if x["code"] == "NG"][0]["selected"])
        self.assertEqual([e[0] for e in self.events], ["TAX_COUNTRY_ADDED", "TAX_COUNTRY_REMOVED"])
        with self.assertRaises(TaxNotFoundError): self.s.set_jurisdiction(ORG, "ZZ", True, "", PREP)


class Engine(unittest.TestCase):
    def test_flat_exclusive_and_inclusive(self):
        e = engine.flat(Decimal("1000.00"), Decimal("7.5"), False, "HALF_UP")
        self.assertEqual((e["tax"], e["gross"]), (Decimal("75.00"), Decimal("1075.00")))
        i = engine.flat(Decimal("1075.00"), Decimal("7.5"), True, "HALF_UP")
        self.assertEqual((i["net"], i["tax"]), (Decimal("1000.00"), Decimal("75.00")))
        self.assertEqual(i["net"] + i["tax"], Decimal("1075.00"))

    def test_rounding_modes(self):
        a = engine.flat(Decimal("0.05"), Decimal("10"), False, "HALF_UP")["tax"]      # 0.005
        b = engine.flat(Decimal("0.05"), Decimal("10"), False, "DOWN")["tax"]
        c = engine.flat(Decimal("0.05"), Decimal("10"), False, "HALF_EVEN")["tax"]
        self.assertEqual((a, b, c), (Decimal("0.01"), Decimal("0.00"), Decimal("0.00")))

    def test_progressive_bands(self):
        b = engine.clean_brackets(BANDS)
        r = engine.progressive(Decimal("7000"), b, "HALF_UP")        # 0 + 4000*10% + 2000*20%
        self.assertEqual(r["tax"], Decimal("800.00")); self.assertEqual(r["effective_rate_pct"], "11.43")
        self.assertEqual(engine.progressive(Decimal("500"), b, "HALF_UP")["tax"], Decimal("0.00"))
        self.assertEqual(engine.progressive(Decimal("0"), b, "HALF_UP")["tax"], Decimal("0.00"))
        self.assertEqual(engine.progressive(Decimal("1000"), b, "HALF_UP")["tax"], Decimal("0.00"))
        self.assertEqual(engine.progressive(Decimal("5000"), b, "HALF_UP")["tax"], Decimal("400.00"))

    def test_bad_bands_refused(self):
        bad = [[], "x", [{"from": "5", "up_to": "10", "rate": "1"}], [{"from": "0", "up_to": "10", "rate": "1"}, {"from": "20", "up_to": None, "rate": "1"}],
               [{"from": "0", "up_to": None, "rate": "1"}, {"from": "10", "up_to": None, "rate": "1"}], [{"from": "0", "up_to": "0", "rate": "1"}], [{"from": "0", "up_to": None, "rate": "101"}],
               [{"from": "0", "up_to": None, "rate": "-1"}], [{"from": "0", "up_to": None, "rate": "abc"}]]
        for b in bad:
            with self.assertRaises(TaxError, msg=str(b)): engine.clean_brackets(b)

    def test_dec_rejects_junk(self):
        for v in (None, "", "abc", True, "NaN", "Infinity"):
            with self.assertRaises(TaxError): engine.dec(v)


class Rules(Base):
    def test_a_rule_cannot_be_used_until_a_second_person_approves(self):
        r = self.s.create_rule(ORG, flat(), PREP)
        self.assertEqual(r["status"], "DRAFT")
        with self.assertRaises(TaxStateError): self.s.calculate(ORG, r["id"], "100", "2026-02-01", False, PREP)
        self.s.submit_rule(ORG, r["id"], PREP)
        with self.assertRaises(TaxStateError): self.s.calculate(ORG, r["id"], "100", "2026-02-01", False, PREP)
        with self.assertRaises(TaxForbiddenError): self.s.approve_rule(ORG, r["id"], PREP, "me")
        with self.assertRaises(TaxForbiddenError): self.s.reject_rule(ORG, r["id"], PREP, "my own")
        a = self.s.approve_rule(ORG, r["id"], REVIEWER, "ok")
        self.assertEqual((a["status"], a["decided_by"]), ("APPROVED", REVIEWER)); self.assertEqual(len(a["fingerprint"]), 64)
        self.assertEqual(self.s.calculate(ORG, r["id"], "100", "2026-02-01", False, PREP)["tax"], "7.50")

    def test_the_author_cannot_approve_even_if_someone_else_submitted(self):
        r = self.s.create_rule(ORG, flat(), PREP); self.s.submit_rule(ORG, r["id"], PREP2)
        with self.assertRaises(TaxForbiddenError): self.s.approve_rule(ORG, r["id"], PREP, "")
        self.assertEqual(self.s.approve_rule(ORG, r["id"], REVIEWER, "")["status"], "APPROVED")

    def test_send_back_needs_a_reason_then_edit_and_resubmit(self):
        r = self.s.create_rule(ORG, flat(), PREP); self.s.submit_rule(ORG, r["id"], PREP)
        with self.assertRaises(TaxError): self.s.reject_rule(ORG, r["id"], REVIEWER, "no")
        self.assertEqual(self.s.reject_rule(ORG, r["id"], REVIEWER, "Rate differs from section 5")["status"], "REJECTED")
        e = self.s.update_rule(ORG, r["id"], flat(rate="7.0"), PREP)
        self.assertEqual((e["status"], e["version"], e["rate"]), ("DRAFT", 2, "7.0"))
        self.s.submit_rule(ORG, r["id"], PREP); self.assertEqual(self.s.approve_rule(ORG, r["id"], REVIEWER, "")["status"], "APPROVED")

    def test_approved_rule_cannot_be_edited_or_discarded(self):
        r = self.live()
        with self.assertRaises(TaxStateError): self.s.update_rule(ORG, r["id"], flat(rate="9"), PREP)
        with self.assertRaises(TaxStateError): self.s.delete_draft(ORG, r["id"], PREP)
        d = self.s.create_rule(ORG, flat(name="Other"), PREP); self.s.delete_draft(ORG, d["id"], PREP)
        self.assertNotIn(d["id"], [x["id"] for x in self.s.list_rules(ORG)])

    def test_validation(self):
        bad = [flat(country="ZZ"), flat(tax_type="MAGIC"), flat(name="ab"), flat(rate="101"), flat(rate="-1"), flat(rate="x"), dict(flat(), method="X"), flat(frm="not a date"),
               flat(frm="2026-02-01", to="2026-01-01"), flat(source_url="javascript:alert(1)"), flat(source_url="ftp://x.y/z"), flat(rounding="UP"), flat(authority=""), flat(source_title="x"),
               dict(flat(), method="BRACKETS", brackets=[])]
        for b in bad:
            with self.assertRaises(TaxError, msg=str(b)): self.s.create_rule(ORG, b, PREP)

    def test_overlap_blocked_but_replacement_supersedes(self):
        old = self.live(flat(rate="7.5", frm="2026-01-01"))
        dup = self.s.create_rule(ORG, flat(rate="8", frm="2026-06-01"), PREP); self.s.submit_rule(ORG, dup["id"], PREP)
        with self.assertRaises(TaxStateError): self.s.approve_rule(ORG, dup["id"], REVIEWER, "")
        new = self.s.create_rule(ORG, flat(rate="8", frm="2026-06-01"), PREP, replaces=old["id"]); self.s.submit_rule(ORG, new["id"], PREP)
        self.s.approve_rule(ORG, new["id"], REVIEWER, "")
        self.assertEqual(self.s.get_rule(ORG, old["id"])["status"], "SUPERSEDED")
        with self.assertRaises(TaxStateError): self.s.calculate(ORG, old["id"], "100", "2026-02-01", False, PREP)
        self.assertEqual(self.s.calculate(ORG, new["id"], "100", "2026-07-01", False, PREP)["tax"], "8.00")

    def test_other_names_or_countries_may_overlap(self):
        self.live(flat(name="VAT")); self.live(flat(name="Other tax")); self.live(flat(country="GH", name="VAT"))
        self.assertEqual(len(self.s.list_rules(ORG, status="APPROVED")), 3)

    def test_isolated_between_organisations(self):
        r = self.live()
        with self.assertRaises(TaxNotFoundError): self.s.get_rule(OTHER, r["id"])
        with self.assertRaises(TaxNotFoundError): self.s.calculate(OTHER, r["id"], "1", "2026-02-01", False, PREP)
        with self.assertRaises(TaxNotFoundError): self.s.submit_rule(OTHER, r["id"], PREP)
        self.assertEqual(self.s.list_rules(OTHER), [])

    def test_every_step_is_audited(self):
        r = self.live(); self.s.calculate(ORG, r["id"], "10", "2026-02-01", False, PREP)
        self.assertEqual([e[0] for e in self.events], ["TAX_RULE_CREATED", "TAX_RULE_SUBMITTED", "TAX_RULE_APPROVED", "TAX_CALCULATED"])


class Calculation(Base):
    def test_effective_dates_are_enforced(self):
        r = self.live(flat(frm="2026-02-01", to="2026-12-31"))
        for d in ("2026-01-31", "2027-01-01"):
            with self.assertRaises(TaxStateError, msg=d): self.s.calculate(ORG, r["id"], "100", d, False, PREP)
        for d in ("2026-02-01", "2026-12-31"): self.assertEqual(self.s.calculate(ORG, r["id"], "100", d, False, PREP)["tax"], "7.50")

    def test_result_carries_working_source_and_limits(self):
        r = self.live(); c = self.s.calculate(ORG, r["id"], "1075", "2026-02-01", True, PREP)
        self.assertEqual((c["net"], c["tax"], c["gross"]), ("1000.00", "75.00", "1075.00"))
        self.assertEqual(c["rule"]["source_url"], "https://example.org/act/5"); self.assertEqual(c["rule"]["fingerprint"], r["fingerprint"])
        self.assertEqual(c["currency"], "NGN"); self.assertTrue(c["steps"]); self.assertIn("ESTIMATE", c["kind"]); self.assertTrue(any("no tax rates" in l for l in c["limitations"]))
        self.assertEqual(self.s.calc_history(ORG)[0]["id"], c["id"])

    def test_brackets_through_the_service(self):
        r = self.live(dict(country="KE", tax_type="PERSONAL_INCOME", name="Income bands", method="BRACKETS", brackets=BANDS, effective_from="2026-01-01", **SRC))
        c = self.s.calculate(ORG, r["id"], "7000", "2026-05-01", False, PREP)
        self.assertEqual(c["tax"], "800.00"); self.assertEqual(len(c["bands"]), 3)
        with self.assertRaises(TaxError): self.s.calculate(ORG, r["id"], "7000", "2026-05-01", True, PREP)

    def test_bad_inputs(self):
        r = self.live()
        for a in ("-1", "abc", "", None, "NaN"):
            with self.assertRaises(TaxError, msg=str(a)): self.s.calculate(ORG, r["id"], a, "2026-02-01", False, PREP)
        with self.assertRaises(TaxError): self.s.calculate(ORG, r["id"], "1", "tomorrow", False, PREP)
        self.assertEqual(self.s.calculate(ORG, r["id"], "0", "2026-02-01", False, PREP)["tax"], "0.00")
        self.assertEqual(self.s.calculate(ORG, r["id"], "99999999999999.99", "2026-02-01", False, PREP)["tax"], "7500000000000.00")  # 7499999999999.99925 rounds half-up

    def test_ledger_base_is_read_only_and_labelled(self):
        w = self.w; w.classify()
        b = self.s.ledger_base(ORG, w.jan.id, "revenue")
        self.assertEqual(b["amount"], "15000.00"); self.assertIn("not taxable income", b["note"]); self.assertIsNone(b["warning"])
        self.assertEqual(self.s.ledger_base(ORG, w.jan.id, "net_income")["amount"], "6500.00")
        with self.assertRaises(TaxError): self.s.ledger_base(ORG, w.jan.id, "profit")


class Calendar(Base):
    def rule(self, **f):
        body = flat(filing=dict(frequency="QUARTERLY", due_days_after_period_end=30, form="Test return", period_anchor="2026-01-01", **f)); return self.live(body)

    def test_nothing_appears_without_a_selected_country_and_approved_rule(self):
        r = self.rule(); self.assertEqual(self.s.calendar(ORG, "2026-01-01", "2026-12-31")["items"], [])
        self.s.set_jurisdiction(ORG, "NG", True, "", PREP)
        items = self.s.calendar(ORG, "2026-01-01", "2026-12-31")["items"]
        self.assertEqual([(i["period_end"], i["due"]) for i in items], [("2026-03-31", "2026-04-30"), ("2026-06-30", "2026-07-30"), ("2026-09-30", "2026-10-30"), ("2026-12-31", "2027-01-30")][:3])
        self.assertEqual(self.s.calendar(OTHER, "2026-01-01", "2026-12-31")["items"], [])

    def test_states_overdue_due_soon_filed(self):
        r = self.rule(); self.s.set_jurisdiction(ORG, "NG", True, "", PREP)
        self.now = datetime(2026, 4, 25, tzinfo=timezone.utc)
        it = self.s.calendar(ORG, "2026-04-01", "2026-04-30")["items"][0]; self.assertEqual(it["state"], "DUE_SOON")
        self.now = datetime(2026, 5, 5, tzinfo=timezone.utc)
        it = self.s.calendar(ORG, "2026-04-01", "2026-04-30")["items"][0]; self.assertEqual(it["state"], "OVERDUE")
        self.s.mark_filed(ORG, r["id"], it["period_end"], "REF-77", PREP)
        it = self.s.calendar(ORG, "2026-04-01", "2026-04-30")["items"][0]; self.assertEqual((it["state"], it["filed"]["reference"]), ("FILED", "REF-77"))
        self.assertIn("did not submit", it["filed"]["note"])

    def test_rule_end_date_stops_the_calendar_and_month_end_dates_are_safe(self):
        self.live(flat(country="GH", to="2026-06-30", filing=dict(frequency="MONTHLY", due_days_after_period_end=15, period_anchor="2026-01-31")))
        self.s.set_jurisdiction(ORG, "GH", True, "", PREP)
        items = self.s.calendar(ORG, "2026-01-01", "2026-12-31")["items"]
        self.assertTrue(items); self.assertTrue(all(i["period_start"] <= "2026-06-30" for i in items))

    def test_range_checks_and_filed_needs_a_rule(self):
        with self.assertRaises(TaxError): self.s.calendar(ORG, "2026-02-01", "2026-01-01")
        with self.assertRaises(TaxError): self.s.calendar(ORG, "2020-01-01", "2026-01-01")
        d = self.s.create_rule(ORG, flat(), PREP)
        with self.assertRaises(TaxStateError): self.s.mark_filed(ORG, d["id"], "2026-03-31", "X1", PREP)
        with self.assertRaises(TaxError): self.s.mark_filed(ORG, self.live(flat(name="Z"))["id"], "2026-03-31", "", PREP)

    def test_overview_lists_selected_countries_with_no_rules(self):
        self.s.set_jurisdiction(ORG, "FR", True, "", PREP)
        o = self.s.overview(ORG); self.assertEqual(o["selected_without_rules"], [{"code": "FR", "name": "France"}])


class Permissions(unittest.TestCase):
    def test_roles(self):
        self.assertIn(TAX_PREPARE, ROLE_PERMISSIONS[Role.ACCOUNTANT]); self.assertNotIn(TAX_APPROVE, ROLE_PERMISSIONS[Role.ACCOUNTANT])
        self.assertIn(TAX_APPROVE, ROLE_PERMISSIONS[Role.APPROVER]); self.assertNotIn(TAX_PREPARE, ROLE_PERMISSIONS[Role.APPROVER])
        self.assertIn(TAX_PREPARE, ROLE_PERMISSIONS[Role.OWNER]); self.assertIn(TAX_APPROVE, ROLE_PERMISSIONS[Role.OWNER])
        for role in (Role.READ_ONLY,): self.assertNotIn(TAX_PREPARE, ROLE_PERMISSIONS[role]); self.assertNotIn(TAX_APPROVE, ROLE_PERMISSIONS[role])


if __name__ == "__main__":
    unittest.main()
