"""Stage 7: agent registry and policy decisions."""
import unittest
from datetime import datetime, timedelta, timezone

from asavexa.agents import policy as P
from asavexa.agents.service import AgentError, AgentForbiddenError, AgentNotFoundError, AgentRegistry, AgentStateError
from asavexa.security.store import MemoryDocStore

ORG, OTHER = "org-1", "org-2"
A, B, C = "alice", "bob", "carol"
T0 = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self): self.t = T0
    def __call__(self): return self.t


def make():
    ck, ev = Clock(), []
    r = AgentRegistry(MemoryDocStore(), is_member=lambda org, u: u in (A, B, C), log=lambda *a, **k: ev.append(a), now=ck)
    return r, ck, ev


def agent(r, who=A, actions=("READ_LEDGER", "DRAFT_JOURNAL"), name="Reviewer"):
    return r.propose_agent(ORG, who, name, "Reads the ledger and drafts journals", C, list(actions))


def active(r, **kw):
    a = agent(r, **kw); return r.activate(ORG, a["id"], B)


class PolicyTests(unittest.TestCase):
    def test_actions_that_need_a_person_are_denied_for_every_agent(self):
        for a in ("POST_JOURNAL", "VERIFY_EVIDENCE", "APPROVE_ANYTHING", "CHANGE_PERMISSIONS", "CHANGE_STANDARDS", "CLOSE_PERIOD", "DELETE_RECORDS"):
            self.assertEqual(P.base_decision(a), P.DENY)

    def test_overrides_can_only_tighten(self):
        self.assertEqual(P.effective_decision("READ_LEDGER", {"READ_LEDGER": "REQUIRE_APPROVAL"}), "REQUIRE_APPROVAL")
        self.assertEqual(P.effective_decision("DRAFT_JOURNAL", {"DRAFT_JOURNAL": "ALLOW"}), "REQUIRE_APPROVAL")
        self.assertEqual(P.effective_decision("POST_JOURNAL", {"POST_JOURNAL": "ALLOW"}), "DENY")
        self.assertEqual(P.effective_decision("READ_LEDGER", {"READ_LEDGER": "bogus"}), "ALLOW")

    def test_only_rule_based_is_approved(self):
        self.assertEqual(P.ALLOWED_PROVIDERS, ("RULE_BASED",))


class RegistryTests(unittest.TestCase):
    def test_propose_activate_and_audit(self):
        r, _, ev = make()
        a = agent(r)
        self.assertEqual(a["status"], "PROPOSED")
        a = r.activate(ORG, a["id"], B, "ok")
        self.assertEqual((a["status"], a["activated_by"]), ("ACTIVE", B))
        self.assertEqual([e[0] for e in ev], ["AGENT_PROPOSED", "AGENT_ACTIVATED"])

    def test_proposer_cannot_activate(self):
        r, _, _ = make(); a = agent(r)
        with self.assertRaises(AgentForbiddenError): r.activate(ORG, a["id"], A)
        self.assertEqual(r.get_agent(ORG, a["id"])["status"], "PROPOSED")

    def test_cannot_register_forbidden_unknown_or_duplicate_actions_or_outside_models(self):
        r, _, _ = make()
        for bad in (["POST_JOURNAL"], ["NOPE"], [], ["READ_LEDGER", "READ_LEDGER"], "READ_LEDGER"):
            with self.assertRaises(AgentError, msg=str(bad)): r.propose_agent(ORG, A, "X", "p", C, bad)
        with self.assertRaises(AgentError): r.propose_agent(ORG, A, "X", "p", C, ["READ_LEDGER"], provider="OUTSIDE_LLM")
        with self.assertRaises(AgentError): r.propose_agent(ORG, A, "X", "p", "stranger", ["READ_LEDGER"])
        with self.assertRaises(AgentError): r.propose_agent(ORG, A, " ", "p", C, ["READ_LEDGER"])
        agent(r)
        with self.assertRaises(AgentStateError): agent(r)

    def test_allow_decision_needs_no_approval(self):
        r, _, _ = make(); a = active(r)
        d = r.request_decision(ORG, a["id"], "READ_LEDGER", A, "trial balance")
        self.assertEqual((d["decision"], d["state"]), ("ALLOW", "NOT_NEEDED"))
        self.assertTrue(r.confirm(ORG, d["id"], A)["permitted"])
        self.assertTrue(r.confirm(ORG, d["id"], A)["permitted"])

    def test_require_approval_flow_is_single_use_and_independent(self):
        r, _, ev = make(); a = active(r)
        d = r.request_decision(ORG, a["id"], "DRAFT_JOURNAL", A, "accrue rent")
        self.assertEqual((d["decision"], d["state"]), ("REQUIRE_APPROVAL", "PENDING"))
        with self.assertRaises(AgentForbiddenError): r.confirm(ORG, d["id"], A)            # not yet approved
        with self.assertRaises(AgentForbiddenError): r.resolve(ORG, d["id"], A, True)      # requester cannot approve
        d = r.resolve(ORG, d["id"], B, True, "looks right")
        self.assertEqual(d["state"], "APPROVED")
        self.assertTrue(r.confirm(ORG, d["id"], A)["once"])
        with self.assertRaises(AgentForbiddenError): r.confirm(ORG, d["id"], A)            # single use
        self.assertIn("AGENT_REQUEST_USED", [e[0] for e in ev])

    def test_rejection_needs_a_reason_and_blocks_use(self):
        r, _, _ = make(); a = active(r)
        d = r.request_decision(ORG, a["id"], "DRAFT_JOURNAL", A)
        with self.assertRaises(AgentError): r.resolve(ORG, d["id"], B, False, "")
        r.resolve(ORG, d["id"], B, False, "wrong account")
        with self.assertRaises(AgentForbiddenError): r.confirm(ORG, d["id"], A)
        with self.assertRaises(AgentStateError): r.resolve(ORG, d["id"], B, True)

    def test_approvals_expire(self):
        r, ck, _ = make(); a = active(r, actions=("EXPORT_DATA",))
        d = r.request_decision(ORG, a["id"], "EXPORT_DATA", A); r.resolve(ORG, d["id"], B, True)
        ck.t += timedelta(hours=25)
        with self.assertRaises(AgentForbiddenError): r.confirm(ORG, d["id"], A)
        self.assertEqual(r.list_decisions(ORG)[0]["state"], "EXPIRED")
        d2 = r.request_decision(ORG, a["id"], "EXPORT_DATA", A); ck.t += timedelta(hours=25)
        with self.assertRaises(AgentStateError): r.resolve(ORG, d2["id"], B, True)

    def test_refusals_are_recorded_not_raised(self):
        r, _, _ = make(); a = active(r)
        d = r.request_decision(ORG, a["id"], "SEND_EXTERNAL_MESSAGE", A)           # not on this agent's list
        self.assertEqual((d["decision"], d["state"]), ("DENY", "REFUSED"))
        with self.assertRaises(AgentForbiddenError): r.confirm(ORG, d["id"], A)
        p = agent(r, name="Other", actions=("READ_LEDGER",))              # a proposed agent is not active
        self.assertEqual(r.request_decision(ORG, p["id"], "READ_LEDGER", A)["decision"], "DENY")
        self.assertEqual(len(r.list_decisions(ORG)), 2)

    def test_suspending_stops_even_approved_requests(self):
        r, _, _ = make(); a = active(r)
        d = r.request_decision(ORG, a["id"], "DRAFT_JOURNAL", A); r.resolve(ORG, d["id"], B, True)
        r.suspend(ORG, a["id"], B, "investigating")
        with self.assertRaises(AgentForbiddenError): r.confirm(ORG, d["id"], A)
        self.assertEqual(r.request_decision(ORG, a["id"], "READ_LEDGER", A)["decision"], "DENY")
        with self.assertRaises(AgentStateError): r.suspend(ORG, a["id"], B, "again")
        self.assertEqual(r.activate(ORG, a["id"], B)["status"], "ACTIVE")
        r.retire(ORG, a["id"], B, "replaced")
        with self.assertRaises(AgentStateError): r.retire(ORG, a["id"], B, "again")
        with self.assertRaises(AgentError): r.suspend(ORG, a["id"], B, "")

    def test_tightening_policy_applies_and_loosening_is_refused(self):
        r, _, _ = make(); a = active(r)
        r.tighten_policy(ORG, B, "READ_LEDGER", "REQUIRE_APPROVAL")
        self.assertEqual(r.request_decision(ORG, a["id"], "READ_LEDGER", A)["decision"], "REQUIRE_APPROVAL")
        with self.assertRaises(AgentError): r.tighten_policy(ORG, B, "READ_LEDGER", "ALLOW")
        with self.assertRaises(AgentError): r.tighten_policy(ORG, B, "DRAFT_JOURNAL", "ALLOW")
        with self.assertRaises(AgentError): r.tighten_policy(ORG, B, "POST_JOURNAL", "DENY")   # already DENY
        with self.assertRaises(AgentError): r.tighten_policy(ORG, B, "NOPE", "DENY")
        row = next(x for x in r.policy_table(ORG) if x["action"] == "READ_LEDGER")
        self.assertEqual((row["builtin"], row["effective"]), ("ALLOW", "REQUIRE_APPROVAL"))
        self.assertEqual(next(x for x in r.policy_table(OTHER) if x["action"] == "READ_LEDGER")["effective"], "ALLOW")

    def test_other_organisation_sees_and_touches_nothing(self):
        r, _, _ = make(); a = active(r)
        d = r.request_decision(ORG, a["id"], "DRAFT_JOURNAL", A)
        self.assertEqual((r.list_agents(OTHER), r.list_decisions(OTHER)), ([], []))
        for call in (lambda: r.get_agent(OTHER, a["id"]), lambda: r.activate(OTHER, a["id"], B), lambda: r.request_decision(OTHER, a["id"], "READ_LEDGER", A),
                     lambda: r.resolve(OTHER, d["id"], B, True), lambda: r.confirm(OTHER, d["id"], A), lambda: r.suspend(OTHER, a["id"], B, "x"), lambda: r.retire(OTHER, a["id"], B, "x")):
            with self.assertRaises(AgentNotFoundError): call()

    def test_unknown_action_in_a_decision_is_an_error(self):
        r, _, _ = make(); a = active(r)
        with self.assertRaises(AgentError): r.request_decision(ORG, a["id"], "FLY", A)


class RouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib
        import harness_security_routers as H
        cls.H, cls.rt = H, importlib.import_module("asavexa.api.routers.agents")

    def test_end_to_end_through_the_router_functions(self):
        rt = self.rt; r, _, _ = make()
        a = rt.propose(rt.AgentBody(name="Rev", purpose="p", owner=C, actions=["DRAFT_JOURNAL"]), ORG, A, r)
        rt.activate(a["id"], rt.NoteBody(), ORG, B, r)
        d = rt.decide(rt.DecideBody(agent_id=a["id"], action="DRAFT_JOURNAL"), ORG, A, r)
        rt.resolve(d["id"], rt.ResolveBody(approve=True), ORG, B, r)
        self.assertTrue(rt.confirm(d["id"], ORG, A, r)["permitted"])
        self.assertEqual(len(rt.list_decisions(None, ORG, r)["decisions"]), 1)
        self.assertTrue(rt.catalog(ORG, r)["policy"])
        self.assertEqual(rt.get_agent(a["id"], ORG, r)["status"], "ACTIVE")

    def test_permissions_declared(self):
        import inspect
        s = inspect.getsource(self.rt)
        for n in ("AUDIT_READ", "GRC_PREPARE", "GRC_APPROVE"): self.assertIn(n, s)


if __name__ == "__main__":
    unittest.main()
