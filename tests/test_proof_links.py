"""Stage 13: the stored Proof-to-Action graph."""
import unittest
from datetime import datetime, timedelta, timezone

from test_passport import World
from asavexa.evidence.domain.enums import EvidenceType
from asavexa.proofgraph import links as L
from asavexa.proofgraph.links import (GraphLinkError, GraphLinkForbiddenError, GraphLinkNotFoundError, GraphLinkStateError, NodeSource, ProofLinks)
from asavexa.security.store import MemoryDocStore

ORG, OTHER = "org-1", "org-2"
RECORDS = {ORG: {"evidence": {"e1": "Invoice a.pdf", "e2": "Contract b.pdf"}, "finding": {"f1": "Finding one", "f2": "Finding two"}, "control": {"c1": "ACC-001 Control"},
                 "risk": {"r1": "R-001 Cash risk"}, "action": {"a1": "A-001 Fix cash"}, "standard": {"s1": "IFRS source"}, "remediation": {"m1": "Fix the lease"},
                 "outcome": {"o1": "EVR-001"}, "decision": {"d1": "Agent draft"}},
           OTHER: {"evidence": {"x1": "Other company evidence"}, "finding": {"fx": "Other finding"}}}


def sources():
    def src(t):
        return NodeSource(lambda org, i, t=t: RECORDS.get(org, {}).get(t, {}).get(i), lambda org, t=t: list(RECORDS.get(org, {}).get(t, {}).items()))
    return {t: src(t) for t in L.NODE_TYPES}


def make(events=None, clock=None):
    ev = events if events is not None else []
    return ProofLinks(MemoryDocStore(), sources(), log=lambda *a, **k: ev.append(a), now=clock or (lambda: datetime(2026, 10, 1, tzinfo=timezone.utc))), ev


class AddingLinks(unittest.TestCase):
    def setUp(self):
        self.g, self.ev = make()

    def add(self, a=("evidence", "e1"), b=("finding", "f1"), rel="EVIDENCES", actor="u1", note="why"):
        return self.g.link_records(ORG, a, b, rel, actor, note)

    def test_a_link_records_who_what_and_why(self):
        d = self.add()
        self.assertEqual((d["status"], d["basis"], d["created_by"], d["relation"], d["note"]), ("ACTIVE", "RECORDED", "u1", "EVIDENCES", "why"))
        self.assertEqual((d["from"]["label"], d["to"]["label"]), ("Invoice a.pdf", "Finding one"))
        self.assertEqual([h["event"] for h in d["history"]], ["CREATED"])
        self.assertEqual(self.ev[-1][0], "GRAPH_LINK_ADDED")

    def test_every_relation_only_joins_the_kinds_it_allows(self):
        with self.assertRaises(GraphLinkError):
            self.g.link_records(ORG, ("finding", "f1"), ("evidence", "e1"), "EVIDENCES", "u1")
        with self.assertRaises(GraphLinkError):
            self.g.link_records(ORG, ("risk", "r1"), ("finding", "f1"), "ADDRESSES", "u1")
        with self.assertRaises(GraphLinkError):
            self.g.link_records(ORG, ("evidence", "e1"), ("finding", "f1"), "NO_SUCH", "u1")
        self.assertEqual(self.g.list_links(ORG), [])

    def test_bad_references_are_refused(self):
        for a, b in ((("evidence",), ("finding", "f1")), (("nope", "e1"), ("finding", "f1")), (("evidence", ""), ("finding", "f1")), (None, ("finding", "f1")),
                     (("evidence", "e" * 200), ("finding", "f1"))):
            with self.assertRaises(GraphLinkError, msg=str((a, b))):
                self.g.link_records(ORG, a, b, "EVIDENCES", "u1")

    def test_both_ends_must_exist(self):
        with self.assertRaises(GraphLinkNotFoundError):
            self.add(a=("evidence", "missing"))
        with self.assertRaises(GraphLinkNotFoundError):
            self.add(b=("finding", "missing"))

    def test_nothing_can_cross_organisations(self):
        with self.assertRaises(GraphLinkNotFoundError):                       # our evidence, their finding
            self.g.link_records(ORG, ("evidence", "e1"), ("finding", "fx"), "EVIDENCES", "u1")
        with self.assertRaises(GraphLinkNotFoundError):                       # their evidence, asked for by us
            self.g.link_records(ORG, ("evidence", "x1"), ("finding", "f1"), "EVIDENCES", "u1")
        d = self.g.link_records(OTHER, ("evidence", "x1"), ("finding", "fx"), "EVIDENCES", "u9")
        self.assertEqual(self.g.list_links(ORG), [])
        with self.assertRaises(GraphLinkNotFoundError):
            self.g.get_link(ORG, d["id"])
        with self.assertRaises(GraphLinkNotFoundError):
            self.g.retire_link(ORG, d["id"], "u1", "x")

    def test_no_self_link_and_no_duplicate(self):
        with self.assertRaises(GraphLinkError):
            self.g.link_records(ORG, ("evidence", "e1"), ("evidence", "e1"), "CONFLICTS_WITH", "u1")
        self.add()
        with self.assertRaises(GraphLinkStateError):
            self.add()
        self.add(a=("evidence", "e2"))                                         # a different evidence is fine

    def test_conflicts_are_symmetric(self):
        self.g.link_records(ORG, ("evidence", "e1"), ("evidence", "e2"), "CONFLICTS_WITH", "u1", "Two amounts for one invoice")
        with self.assertRaises(GraphLinkStateError):
            self.g.link_records(ORG, ("evidence", "e2"), ("evidence", "e1"), "CONFLICTS_WITH", "u2")

    def test_a_note_is_bounded(self):
        with self.assertRaises(GraphLinkError):
            self.add(note="x" * 2001)

    def test_a_retired_link_can_be_made_again(self):
        d = self.add()
        self.g.retire_link(ORG, d["id"], "u2", "Wrong evidence")
        self.assertEqual(self.add()["status"], "ACTIVE")

    def test_the_organisation_has_a_ceiling(self):
        g, _ = make()
        old = L.MAX_LINKS
        try:
            L.MAX_LINKS = 2
            g.link_records(ORG, ("evidence", "e1"), ("finding", "f1"), "EVIDENCES", "u1")
            g.link_records(ORG, ("evidence", "e2"), ("finding", "f1"), "EVIDENCES", "u1")
            with self.assertRaises(GraphLinkStateError):
                g.link_records(ORG, ("evidence", "e1"), ("finding", "f2"), "EVIDENCES", "u1")
        finally:
            L.MAX_LINKS = old


class LinkLifecycle(unittest.TestCase):
    def setUp(self):
        self.g, self.ev = make()
        self.d = self.g.link_records(ORG, ("evidence", "e1"), ("finding", "f1"), "EVIDENCES", "u1", "supports")

    def test_confirmation_needs_a_different_person_and_happens_once(self):
        with self.assertRaises(GraphLinkForbiddenError):
            self.g.confirm_link(ORG, self.d["id"], "u1")
        c = self.g.confirm_link(ORG, self.d["id"], "u2", "Checked the invoice")
        self.assertEqual((c["confirmed_by"], c["status"]), ("u2", "ACTIVE"))
        with self.assertRaises(GraphLinkStateError):
            self.g.confirm_link(ORG, self.d["id"], "u3")

    def test_dispute_clears_confirmation_and_blocks_further_confirmation(self):
        self.g.confirm_link(ORG, self.d["id"], "u2")
        x = self.g.dispute_link(ORG, self.d["id"], "u3", "Wrong invoice number")
        self.assertEqual((x["status"], x["confirmed_by"], x["disputed_by"]), ("DISPUTED", None, "u3"))
        with self.assertRaises(GraphLinkStateError):
            self.g.confirm_link(ORG, self.d["id"], "u4")
        with self.assertRaises(GraphLinkStateError):
            self.g.dispute_link(ORG, self.d["id"], "u4", "again")

    def test_the_person_who_disputed_cannot_reinstate(self):
        self.g.dispute_link(ORG, self.d["id"], "u3", "Wrong invoice number")
        with self.assertRaises(GraphLinkForbiddenError):
            self.g.reinstate_link(ORG, self.d["id"], "u3", "I was wrong")
        r = self.g.reinstate_link(ORG, self.d["id"], "u4", "Checked: it is the right one")
        self.assertEqual((r["status"], r["disputed_by"]), ("ACTIVE", None))
        with self.assertRaises(GraphLinkStateError):
            self.g.reinstate_link(ORG, self.d["id"], "u4", "x")

    def test_reasons_are_required(self):
        for fn in (lambda: self.g.dispute_link(ORG, self.d["id"], "u3", " "), lambda: self.g.retire_link(ORG, self.d["id"], "u3", "")):
            with self.assertRaises(GraphLinkError):
                fn()
        self.g.dispute_link(ORG, self.d["id"], "u3", "r")
        with self.assertRaises(GraphLinkError):
            self.g.reinstate_link(ORG, self.d["id"], "u4", "")

    def test_retiring_keeps_the_record_and_its_history(self):
        r = self.g.retire_link(ORG, self.d["id"], "u2", "Linked by mistake")
        self.assertEqual(r["status"], "RETIRED")
        self.assertEqual([h["event"] for h in self.g.get_link(ORG, self.d["id"])["history"]], ["CREATED", "RETIRED"])
        for fn in (lambda: self.g.retire_link(ORG, self.d["id"], "u2", "again"), lambda: self.g.dispute_link(ORG, self.d["id"], "u2", "x"), lambda: self.g.confirm_link(ORG, self.d["id"], "u2")):
            with self.assertRaises(GraphLinkStateError):
                fn()

    def test_unknown_link_ids(self):
        for bad in ("nope", "", None, 5):
            with self.assertRaises(GraphLinkNotFoundError):
                self.g.confirm_link(ORG, bad, "u2")

    def test_every_step_is_audited(self):
        self.g.confirm_link(ORG, self.d["id"], "u2"); self.g.dispute_link(ORG, self.d["id"], "u3", "r"); self.g.reinstate_link(ORG, self.d["id"], "u4", "n"); self.g.retire_link(ORG, self.d["id"], "u4", "r")
        self.assertEqual([e[0] for e in self.ev], ["GRAPH_LINK_ADDED", "GRAPH_LINK_CONFIRMED", "GRAPH_LINK_DISPUTED", "GRAPH_LINK_REINSTATED", "GRAPH_LINK_RETIRED"])


class Superseding(unittest.TestCase):
    def setUp(self):
        self.g, self.ev = make()
        self.old = self.g.link_records(ORG, ("evidence", "e1"), ("finding", "f1"), "EVIDENCES", "u1", "first")
        self.new = self.g.link_records(ORG, ("evidence", "e1"), ("finding", "f2"), "EVIDENCES", "u1", "better")

    def test_supersede_keeps_both_and_hides_the_old_one(self):
        self.g.confirm_link(ORG, self.old["id"], "u2")
        r = self.g.supersede_link(ORG, self.old["id"], self.new["id"], "u3", "Pointed at the wrong finding")
        self.assertEqual((r["status"], r["superseded_by"], r["confirmed_by"]), ("SUPERSEDED", self.new["id"], None))
        self.assertEqual(self.g.get_link(ORG, self.new["id"])["supersedes"], [self.old["id"]])
        self.assertEqual([h["event"] for h in self.g.get_link(ORG, self.old["id"])["history"]], ["CREATED", "CONFIRMED", "SUPERSEDED"])
        self.assertEqual([h["event"] for h in self.g.get_link(ORG, self.new["id"])["history"]], ["CREATED", "SUPERSEDES"])
        ids = lambda inc: {d["id"] for d in self.g.neighbourhood(ORG, "evidence", "e1", 1, inc)["links"]}
        self.assertEqual(ids(False), {self.new["id"]}); self.assertEqual(ids(True), {self.old["id"], self.new["id"]})
        self.assertEqual(len(self.g.list_links(ORG, "SUPERSEDED")), 1)

    def test_a_disputed_link_can_be_superseded(self):
        self.g.dispute_link(ORG, self.old["id"], "u3", "Wrong invoice")
        self.assertEqual(self.g.supersede_link(ORG, self.old["id"], self.new["id"], "u3", "Replaced")["status"], "SUPERSEDED")

    def test_rules(self):
        for rep in (None, "", " ", 5, "nope"):
            with self.assertRaises(GraphLinkError): self.g.supersede_link(ORG, self.old["id"], rep, "u2", "reason")
        with self.assertRaises(GraphLinkError): self.g.supersede_link(ORG, self.old["id"], self.old["id"], "u2", "reason")
        with self.assertRaises(GraphLinkError): self.g.supersede_link(ORG, self.old["id"], self.new["id"], "u2", " ")
        other_from = self.g.link_records(ORG, ("evidence", "e2"), ("finding", "f1"), "EVIDENCES", "u1", "different record")
        with self.assertRaises(GraphLinkError): self.g.supersede_link(ORG, self.old["id"], other_from["id"], "u2", "reason")      # must start from the same record
        with self.assertRaises(GraphLinkNotFoundError): self.g.supersede_link(ORG, "nope", self.new["id"], "u2", "reason")
        with self.assertRaises(GraphLinkNotFoundError): self.g.supersede_link(OTHER, self.old["id"], self.new["id"], "u2", "reason")
        self.g.retire_link(ORG, self.new["id"], "u2", "gone")
        with self.assertRaises(GraphLinkStateError): self.g.supersede_link(ORG, self.old["id"], self.new["id"], "u2", "reason")      # replacement must be active
        self.assertEqual(self.g.get_link(ORG, self.old["id"])["status"], "ACTIVE")                                               # nothing changed on failure

    def test_a_superseded_link_is_final(self):
        self.g.supersede_link(ORG, self.old["id"], self.new["id"], "u2", "Replaced")
        for fn in (lambda: self.g.retire_link(ORG, self.old["id"], "u2", "x"), lambda: self.g.dispute_link(ORG, self.old["id"], "u2", "x"), lambda: self.g.confirm_link(ORG, self.old["id"], "u3"),
                   lambda: self.g.reinstate_link(ORG, self.old["id"], "u3", "x"), lambda: self.g.supersede_link(ORG, self.old["id"], self.new["id"], "u2", "again")):
            with self.assertRaises(GraphLinkStateError): fn()
        again = self.g.link_records(ORG, ("evidence", "e1"), ("finding", "f1"), "EVIDENCES", "u1", "same pair may be recorded afresh")
        self.assertEqual(again["status"], "ACTIVE")

    def test_audited_without_content(self):
        self.g.supersede_link(ORG, self.old["id"], self.new["id"], "u2", "Replaced")
        self.assertIn("GRAPH_LINK_SUPERSEDED", [e[0] for e in self.ev])


class SystemLinks(unittest.TestCase):
    def test_system_links_are_marked_and_idempotent(self):
        g, ev = make()
        a = g.record_system_link(ORG, ("outcome", "o1"), ("finding", "f1"), "ADDRESSES", "u1", "Case raised")
        b = g.record_system_link(ORG, ("outcome", "o1"), ("finding", "f1"), "ADDRESSES", "u1", "Case raised")
        self.assertEqual((a["basis"], a["id"] == b["id"], len(g.list_links(ORG)), len(ev)), ("SYSTEM", True, 1, 1))

    def test_a_system_link_still_needs_a_different_person_to_confirm(self):
        g, _ = make()
        a = g.record_system_link(ORG, ("outcome", "o1"), ("finding", "f1"), "ADDRESSES", "u1")
        with self.assertRaises(GraphLinkForbiddenError):
            g.confirm_link(ORG, a["id"], "u1")
        self.assertEqual(g.confirm_link(ORG, a["id"], "u2")["confirmed_by"], "u2")


class Gaps(unittest.TestCase):
    def setUp(self):
        self.g, self.ev = make()

    def test_an_expected_link_can_be_written_down_and_is_filled_by_a_matching_link(self):
        gap = self.g.expect_link(ORG, ("finding", "f1"), "RAISED_BY", "u1", "Every finding should name the control that raised it", "control")
        self.assertEqual(gap["status"], "OPEN")
        self.assertEqual([x["id"] for x in self.g.neighbourhood(ORG, "finding", "f1")["gaps"]], [gap["id"]])
        d = self.g.link_records(ORG, ("finding", "f1"), ("control", "c1"), "RAISED_BY", "u2")
        self.assertEqual(self.g.neighbourhood(ORG, "finding", "f1")["gaps"], [])
        self.assertEqual([e[0] for e in self.ev], ["GRAPH_GAP_RECORDED", "GRAPH_LINK_ADDED", "GRAPH_GAP_FILLED"])
        self.assertTrue(d["id"])

    def test_a_link_of_another_kind_does_not_fill_it(self):
        self.g.expect_link(ORG, ("finding", "f1"), "GOVERNED_BY", "u1", "needs a standard", "standard")
        self.g.link_records(ORG, ("finding", "f1"), ("control", "c1"), "RAISED_BY", "u2")
        self.assertEqual(len(self.g.neighbourhood(ORG, "finding", "f1")["gaps"]), 1)

    def test_validation(self):
        for args in ((("evidence", "e1"), "RAISED_BY", "u1", "x"), (("finding", "f1"), "NO", "u1", "x"), (("finding", "f1"), "RAISED_BY", "u1", " ")):
            with self.assertRaises(GraphLinkError):
                self.g.expect_link(ORG, *args)
        with self.assertRaises(GraphLinkError):
            self.g.expect_link(ORG, ("finding", "f1"), "RAISED_BY", "u1", "x", "evidence")
        with self.assertRaises(GraphLinkNotFoundError):
            self.g.expect_link(ORG, ("finding", "ghost"), "RAISED_BY", "u1", "x")

    def test_the_same_open_gap_is_not_recorded_twice(self):
        self.g.expect_link(ORG, ("finding", "f1"), "RAISED_BY", "u1", "x", "control")
        with self.assertRaises(GraphLinkStateError):
            self.g.expect_link(ORG, ("finding", "f1"), "RAISED_BY", "u2", "again", "control")

    def test_waiving_needs_a_different_person_and_a_reason(self):
        gap = self.g.expect_link(ORG, ("finding", "f1"), "RAISED_BY", "u1", "x")
        with self.assertRaises(GraphLinkForbiddenError):
            self.g.waive_gap(ORG, gap["id"], "u1", "not needed")
        with self.assertRaises(GraphLinkError):
            self.g.waive_gap(ORG, gap["id"], "u2", " ")
        w = self.g.waive_gap(ORG, gap["id"], "u2", "Manual finding, no control")
        self.assertEqual((w["status"], w["waived_by"]), ("WAIVED", "u2"))
        with self.assertRaises(GraphLinkStateError):
            self.g.waive_gap(ORG, gap["id"], "u3", "again")

    def test_gaps_belong_to_their_organisation(self):
        gap = self.g.expect_link(ORG, ("finding", "f1"), "RAISED_BY", "u1", "x")
        with self.assertRaises(GraphLinkNotFoundError):
            self.g.waive_gap(OTHER, gap["id"], "u2", "x")
        self.assertEqual(self.g.neighbourhood(OTHER, "finding", "fx")["gaps"], [])


class Reading(unittest.TestCase):
    def setUp(self):
        self.g, _ = make()
        a = self.g.link_records(ORG, ("evidence", "e1"), ("finding", "f1"), "EVIDENCES", "u1")
        self.g.link_records(ORG, ("finding", "f1"), ("control", "c1"), "RAISED_BY", "u1")
        self.g.link_records(ORG, ("control", "c1"), ("risk", "r1"), "MITIGATES", "u1")
        self.g.link_records(ORG, ("action", "a1"), ("risk", "r1"), "ADDRESSES_RISK", "u1")
        self.first = a

    def ids(self, v): return {(n["type"], n["id"]) for n in v["nodes"]}

    def test_depth_controls_how_far_it_reaches(self):
        one = self.g.neighbourhood(ORG, "finding", "f1", 1)
        self.assertEqual(self.ids(one), {("finding", "f1"), ("evidence", "e1"), ("control", "c1")})
        two = self.g.neighbourhood(ORG, "finding", "f1", 2)
        self.assertIn(("risk", "r1"), self.ids(two)); self.assertNotIn(("action", "a1"), self.ids(two))
        three = self.g.neighbourhood(ORG, "finding", "f1", 3)
        self.assertIn(("action", "a1"), self.ids(three)); self.assertEqual(len(three["links"]), 4)

    def test_depth_is_validated(self):
        for d in (0, 4, "2", True, None):
            with self.assertRaises(GraphLinkError):
                self.g.neighbourhood(ORG, "finding", "f1", d)

    def test_retired_links_are_hidden_unless_asked_for(self):
        self.g.retire_link(ORG, self.first["id"], "u2", "wrong")
        self.assertNotIn(("evidence", "e1"), self.ids(self.g.neighbourhood(ORG, "finding", "f1")))
        self.assertIn(("evidence", "e1"), self.ids(self.g.neighbourhood(ORG, "finding", "f1", include_retired=True)))

    def test_a_disputed_link_is_still_shown_with_its_state(self):
        self.g.dispute_link(ORG, self.first["id"], "u2", "wrong")
        v = self.g.neighbourhood(ORG, "finding", "f1")
        self.assertIn("DISPUTED", {x["status"] for x in v["links"]})

    def test_the_focus_must_exist_in_this_organisation(self):
        with self.assertRaises(GraphLinkNotFoundError):
            self.g.neighbourhood(ORG, "finding", "fx")
        with self.assertRaises(GraphLinkNotFoundError):
            self.g.neighbourhood(OTHER, "finding", "f1")

    def test_another_organisation_sees_nothing_of_ours(self):
        v = self.g.neighbourhood(OTHER, "finding", "fx")
        self.assertEqual((len(v["nodes"]), v["links"], v["gaps"]), (1, [], []))
        self.assertEqual(self.g.list_links(OTHER), [])

    def test_listing_and_choices(self):
        self.assertEqual(len(self.g.list_links(ORG)), 4)
        self.assertEqual(len(self.g.list_links(ORG, "RETIRED")), 0)
        self.assertEqual({c["id"] for c in self.g.link_choices(ORG, "evidence")}, {"e1", "e2"})
        self.assertEqual(self.g.link_choices(OTHER, "evidence")[0]["id"], "x1")
        with self.assertRaises(GraphLinkError):
            self.g.link_choices(ORG, "nope")

    def test_a_broken_source_gives_no_choices_and_refuses_links(self):
        def boom(*a): raise RuntimeError("db")
        g = ProofLinks(MemoryDocStore(), {"evidence": NodeSource(boom, boom), "finding": NodeSource(lambda o, i: "F", lambda o: [])})
        self.assertEqual(g.link_choices(ORG, "evidence"), [])
        with self.assertRaises(GraphLinkNotFoundError):
            g.link_records(ORG, ("evidence", "e1"), ("finding", "f1"), "EVIDENCES", "u1")
        self.assertEqual(g.link_choices(ORG, "control"), [])

    def test_the_node_ceiling_marks_the_view_truncated(self):
        old = L.MAX_NODES
        try:
            L.MAX_NODES = 2
            v = self.g.neighbourhood(ORG, "finding", "f1", 1)
            self.assertTrue(v["truncated"]); self.assertEqual(len(v["nodes"]), 2)
        finally:
            L.MAX_NODES = old

    def test_vocabulary_is_plain_data(self):
        import json
        v = ProofLinks.link_vocabulary(); json.dumps(v)
        self.assertEqual({r["code"] for r in v["relations"]}, set(L.RELATIONS))
        self.assertTrue(next(r for r in v["relations"] if r["code"] == "CONFLICTS_WITH")["symmetric"])


class RealCasesRecordTheirLinks(unittest.TestCase):
    """An Evidence Review case writes its own links into the graph, on the real services."""

    def setUp(self):
        from test_evidence_review import make as make_er
        self.w = World()
        self.er = make_er(self.w)
        w, store = self.w, self.er.store
        def lab(kind, f):
            return lambda org, i: (lambda d: f(d) if d and d.get("org") == org else None)(store.get(kind, f"{org}:{i}"))
        self.sources = {
            "outcome": NodeSource(lab("evr_case", lambda d: f"{d['ref']} {d['title']}"), lambda org: []),
            "finding": NodeSource(lambda org, i: (lambda f: f.description[:60])(w.compliance.get_finding(org, i)), lambda org: []),
            "control": NodeSource(lambda org, i: (lambda c: f"{c.code} {c.name}")(w.compliance.get_control(org, i)), lambda org: []),
            "remediation": NodeSource(lambda org, i: (lambda r: r.action[:60])(w.compliance.get_remediation(org, i)), lambda org: []),
        }
        self.events = []
        self.g = ProofLinks(store, self.sources, log=lambda *a, **k: self.events.append(a))
        self.er.links = self.g

    def test_opening_and_planning_a_case_links_it_to_its_finding_control_and_remediation(self):
        w, o = self.w, self.w.org.id
        c = self.er.open_case(o, w.period.id, "income_statement", w.accountant.id)
        self.er.plan_action(o, c["id"], "Attach the lease", w.accountant.id, w.owner.id)
        v = self.g.neighbourhood(o, "finding", c["finding_id"], 2)
        rels = sorted((x["from"]["type"], x["relation"], x["to"]["type"]) for x in v["links"])
        self.assertEqual(rels, [("finding", "RAISED_BY", "control"), ("outcome", "ADDRESSES", "finding"), ("remediation", "ADDRESSES", "finding")])
        self.assertTrue(all(x["basis"] == "SYSTEM" for x in v["links"]))
        self.assertTrue(any("EVR-" in n["label"] for n in v["nodes"]))

    def test_the_same_graph_is_not_duplicated_by_a_reopened_case_for_the_same_finding(self):
        w, o = self.w, self.w.org.id
        c = self.er.open_case(o, w.period.id, "income_statement", w.accountant.id)
        before = len(self.g.list_links(o))
        self.g.record_system_link(o, ("outcome", c["id"]), ("finding", c["finding_id"]), "ADDRESSES", w.accountant.id)
        self.assertEqual(len(self.g.list_links(o)), before)

    def test_a_graph_failure_never_blocks_the_case_but_is_audited(self):
        w, o = self.w, self.w.org.id
        class Broken:
            def record_system_link(self, *a, **k): raise RuntimeError("store down")
        self.er.links = Broken()
        c = self.er.open_case(o, w.period.id, "income_statement", w.accountant.id)
        self.assertEqual(c["status"], "OPEN")
        self.assertIn("GRAPH_LINK_SYNC_FAILED", [e[0] for e in self.w.events])

    def test_another_organisation_cannot_see_those_links(self):
        w, o = self.w, self.w.org.id
        c = self.er.open_case(o, w.period.id, "income_statement", w.accountant.id)
        self.assertEqual(self.g.list_links("someone-else"), [])
        with self.assertRaises(GraphLinkNotFoundError):
            self.g.neighbourhood("someone-else", "finding", c["finding_id"])

    def test_without_a_graph_cases_work_as_before(self):
        w, o = self.w, self.w.org.id
        self.er.links = None
        self.assertEqual(self.er.open_case(o, w.period.id, "income_statement", w.accountant.id)["status"], "OPEN")


if __name__ == "__main__":
    unittest.main()


class RealSourcesAndRouter(unittest.TestCase):
    """The production record sources (proofgraph.wiring) and the real router functions, on the real services."""

    @classmethod
    def setUpClass(cls):
        import harness_security_routers as H
        import importlib
        cls.H = H
        cls.pl = importlib.import_module("asavexa.api.routers.proof_links")

    def setUp(self):
        from test_evidence_review import make as make_er
        from asavexa.proofgraph.wiring import make_sources
        self.w = World(); w = self.w
        self.er = make_er(w)
        self.g = ProofLinks(self.er.store, make_sources(self.er.store, w.vault, w.compliance), log=lambda *a, **k: None)
        self.er.links = self.g
        self.o = w.org.id

    def test_every_kind_the_graph_offers_can_be_listed_without_error(self):
        for t in L.NODE_TYPES:
            rows = self.g.link_choices(self.o, t)
            self.assertIsInstance(rows, list, t)
        self.assertTrue(self.g.link_choices(self.o, "evidence"))
        self.assertTrue(self.g.link_choices(self.o, "finding"))

    def test_other_organisations_records_are_not_found(self):
        w = self.w
        ev = w.vault.list_for_org(self.o)[0]
        with self.assertRaises(GraphLinkNotFoundError):
            self.g.neighbourhood("another-org", "evidence", ev.id)

    def test_a_real_link_between_real_evidence_and_a_real_finding(self):
        w, o = self.w, self.o
        ev = w.vault.list_for_org(o)[0]
        f = w.compliance.list_findings(o)[0]
        d = self.g.link_records(o, ("evidence", ev.id), ("finding", f.id), "EVIDENCES", w.accountant.id, "supports")
        self.assertIn(ev.original_filename, d["from"]["label"])
        n = self.g.neighbourhood(o, "finding", f.id)
        self.assertEqual(len(n["links"]), 1)

    def test_router_round_trip_and_error_status(self):
        pl, w, o, g = self.pl, self.w, self.o, self.g
        ev = w.vault.list_for_org(o)[0]; f = w.compliance.list_findings(o)[0]
        d = pl.add(pl.LinkBody(from_ref=pl.Ref(type="evidence", id=ev.id), to_ref=pl.Ref(type="finding", id=f.id), relation="EVIDENCES"), o, w.accountant.id, g)
        self.assertEqual(d["status"], "ACTIVE")
        self.assertEqual(len(pl.graph("finding", f.id, 1, False, o, g)["links"]), 1)
        self.assertEqual(len(pl.list_all(None, o, g)["links"]), 1)
        self.assertTrue(pl.choices("evidence", o, g)["choices"])
        c = pl.confirm(d["id"], pl.NoteBody(note="seen"), o, w.approver.id, g)
        self.assertEqual(c["confirmed_by"], w.approver.id)
        with self.assertRaises(Exception) as cm:
            pl.confirm(d["id"], pl.NoteBody(), o, w.owner.id, g)
        self.assertEqual(getattr(cm.exception, "status_code", None), 409)
        with self.assertRaises(Exception) as cm:
            pl.get_one("nope", o, g)
        self.assertEqual(getattr(cm.exception, "status_code", None), 404)
        gap = pl.expect(pl.GapBody(from_ref=pl.Ref(type="finding", id=f.id), relation="RAISED_BY", note="no control recorded"), o, w.accountant.id, g)
        self.assertEqual(pl.waive(gap["id"], pl.ReasonBody(reason="not applicable"), o, w.approver.id, g)["status"], "WAIVED")

    def test_router_uses_the_right_permissions(self):
        import inspect
        src = inspect.getsource(self.pl)
        for name, perm in (("add", "GRC_PREPARE"), ("confirm", "GRC_APPROVE"), ("waive", "GRC_APPROVE"), ("graph", "AUDIT_READ")):
            seg = src[src.index(f"def {name}("):]; head = src[:src.index(f"def {name}(")].rsplit("@router", 1)[1]
            self.assertIn(perm, head, name)
