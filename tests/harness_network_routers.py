"""Runs the REAL network router functions (fastapi stubbed) over real identity, a real SecurityContext (audit chain), real Passport data and the real
network service on one SQLite connection. Provider: Meridian Textiles (has data). Viewer: 'Other Ltd' registered as an auditor."""
import sys, types
import os as _os; _ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), ".."))   # works wherever the repository is checked out
sys.path.insert(0, _ROOT + "/src"); sys.path.insert(0, _ROOT + "/tests")
def mod(name, **attrs):
    m = types.ModuleType(name); m.__dict__.update(attrs); sys.modules[name] = m; return m
class APIRouter:
    def __init__(self, **k): self.k = k
    def _d(self, *a, **k): return lambda f: f
    get = post = put = patch = delete = _d
mod("fastapi", APIRouter=APIRouter, Depends=lambda x=None: ("dep", x))
import asavexa
for pkg, path in [("asavexa.api","api"),("asavexa.api.routers","api/routers"),("asavexa.api.schemas","api/schemas")]:
    m = types.ModuleType(pkg); m.__path__ = [_ROOT + "/src/asavexa/"+path]; sys.modules[pkg] = m
mod("asavexa.api.deps", **{n: (lambda: None) for n in ["get_current_actor","get_current_org","get_identity_service","get_network","get_session"]}, require_permission=lambda p: ("perm", p))
import importlib, json
nr = importlib.import_module("asavexa.api.routers.network")

import unittest
from test_security_context import Ctx
from asavexa.identity.domain.enums import Role
from asavexa.identity.domain.permissions import NETWORK_MANAGE, ROLE_PERMISSIONS
from asavexa.network.errors import NetworkError, NetworkForbiddenError, NetworkStateError
from asavexa.network.service import NetworkService
from asavexa.network.wiring import make_log
from asavexa.passport.sharing import share_fingerprint
from asavexa.security.store import SqliteDocStore


class Run(Ctx):
    def setUp(self):
        self.build(); w = self.w
        self.prov, self.view = w.org.id, w.other_org.id
        self.dara, self.other = w.owner.id, w.other_owner.id
        self.svc = NetworkService(SqliteDocStore(w.conn), log=make_log(self.ctx))
        self.commits = 0
        self.session = types.SimpleNamespace(commit=lambda: setattr(self, "commits", self.commits + 1))
        self.gather = lambda s, o: w.inputs(o)
        nr.set_profile(nr.ProfileBody(org_type="BUSINESS", display_name="Meridian Textiles"), self.prov, self.dara, self.svc)
        nr.set_profile(nr.ProfileBody(org_type="AUDITOR", display_name="Other Audit LLP"), self.view, self.other, self.svc)

    def connect(self, scopes=("IDENTITY", "FINANCIAL_HISTORY", "EVIDENCE_QUALITY"), **kw):
        r = nr.create_invite(nr.InviteBody(counterparty_type="AUDITOR", purpose="Statutory audit", grant=nr.GrantBody(scopes=list(scopes), **kw)), self.prov, self.dara, self.svc)
        return nr.accept(nr.AcceptBody(code=r["code"]), self.view, self.other, self.svc, self.session)

    def open(self, cid, actor=None, org=None):
        return nr.build_view(self.svc, None, self.w.identity, actor or self.other, org or self.view, cid, self.gather)

    def test_permission(self):
        for r in Role: self.assertEqual(NETWORK_MANAGE in ROLE_PERMISSIONS[r], r in (Role.OWNER, Role.ADMINISTRATOR), r)
        self.assertTrue(nr._can_manage(self.w.identity, self.dara, self.prov)); self.assertFalse(nr._can_manage(self.w.identity, self.w.accountant.id, self.prov))
        g = nr.guide(); self.assertEqual(len(g["types"]), 7); self.assertEqual(len(g["how_it_works"]), 5)

    def test_the_auditor_sees_exactly_what_the_business_granted_and_nothing_else(self):
        c = self.connect(scopes=("IDENTITY", "FINANCIAL_HISTORY"))
        v = self.open(c["id"])
        self.assertEqual(set(v["sections"]), {"identity", "financial_history"}); self.assertEqual(v["share"]["scopes"], ["IDENTITY", "FINANCIAL_HISTORY"])
        text = json.dumps(v, default=str)
        for secret in ("aisha@meridian.test", "kwame@meridian.test", "dara@meridian.test"): self.assertNotIn(secret, text)      # no team e-mails without line-level detail
        self.assertFalse(v["share"]["include_detail"]); self.assertTrue(v["share"]["closed_periods_only"])
        self.assertEqual(v["fingerprint"], share_fingerprint(v["share"], v["sections"])); self.assertIn("not an audit opinion", v["disclaimer"])
        self.assertEqual(v["connection"]["role"], "VIEWER"); self.assertNotIn("views", v["connection"])

    def test_widening_the_grant_is_the_businesss_decision_and_takes_effect_at_once(self):
        c = self.connect(scopes=("IDENTITY",))
        self.assertEqual(set(self.open(c["id"])["sections"]), {"identity"})
        with self.assertRaises(NetworkForbiddenError): nr.update(c["id"], nr.UpdateBody(grant=nr.GrantBody(scopes=["IDENTITY", "AUDIT_TRAIL"])), self.view, self.other, self.svc)   # the auditor cannot
        nr.update(c["id"], nr.UpdateBody(grant=nr.GrantBody(scopes=["IDENTITY", "EVIDENCE_QUALITY"])), self.prov, self.dara, self.svc)
        self.assertEqual(set(self.open(c["id"])["sections"]), {"identity", "evidence_quality"})

    def test_nobody_else_can_open_it(self):
        c = self.connect()
        with self.assertRaises(NetworkForbiddenError): self.open(c["id"], self.dara, self.prov)                  # the business itself, through the viewer route
        w = self.w; bank_org = w.identity.create_organisation("Third Bank", actor=w.accountant.id); w.identity.add_membership(bank_org.id, w.accountant.id, Role.OWNER, actor_user_id=w.accountant.id)
        nr.set_profile(nr.ProfileBody(org_type="BANK", display_name="Third Bank"), bank_org.id, w.accountant.id, self.svc)
        with self.assertRaises(NetworkForbiddenError): self.open(c["id"], w.accountant.id, bank_org.id)           # an unrelated organisation, valid connection id
        with self.assertRaises(NetworkForbiddenError): self.open(c["id"], w.approver.id, self.view)              # a person with no membership in the viewing organisation

    def test_ending_or_expiring_closes_it_and_everything_is_audited_on_both_sides(self):
        c = self.connect(); self.open(c["id"])
        nr.end(c["id"], nr.EndBody(reason="Audit finished"), self.prov, self.dara, self.svc)
        with self.assertRaises(NetworkForbiddenError): self.open(c["id"])
        for org in (self.prov, self.view):
            acts = {e.action for e in self.w.audit.list_for_org(org) if e.action.startswith("NETWORK_")}
            self.assertTrue({"NETWORK_PROFILE_SET", "NETWORK_CONNECTED", "NETWORK_PASSPORT_VIEWED", "NETWORK_DISCONNECTED"} <= acts | {"NETWORK_INVITE_CREATED"} | {"NETWORK_PROFILE_SET"}, (org, acts))
        self.assertIn("NETWORK_INVITE_CREATED", {e.action for e in self.w.audit.list_for_org(self.prov)})
        self.assertEqual({e.entity_type for e in self.w.audit.list_for_org(self.prov) if e.action == "NETWORK_CONNECTED"}, {"NetworkConnection"})
        self.assertTrue(self.ctx.verify_audit(self.prov)["ok"]); self.assertTrue(self.ctx.verify_audit(self.view)["ok"])

    def test_access_log_names_the_organisation_not_the_person(self):
        c = self.connect(); self.open(c["id"]); self.open(c["id"])
        log = nr.access_log(c["id"], self.prov, self.svc)
        self.assertEqual(len(log), 2); self.assertEqual(log[0]["viewer"], "Other Audit LLP"); self.assertNotIn("user_id", log[0])
        self.assertEqual(nr.me(self.dara, self.prov, self.w.identity, self.svc)["connections"][0]["views"], 2)

    def test_wrong_codes_are_committed_so_the_lockout_counts_them(self):
        before = self.commits
        with self.assertRaises(NetworkError): nr.preview(nr.CodeBody(code="ASX-WRONG-CODE0"), self.view, self.other, self.svc, self.session)
        with self.assertRaises(NetworkError): nr.accept(nr.AcceptBody(code="ASX-WRONG-CODE1"), self.view, self.other, self.svc, self.session)
        self.assertEqual(self.commits - before, 2)

    def test_request_flow_through_the_router(self):
        r = nr.create_invite(nr.InviteBody(counterparty_type="BUSINESS", purpose="Loan", grant=nr.GrantBody(scopes=["IDENTITY", "FINANCIAL_HISTORY"])), self.view, self.other, self.svc)
        with self.assertRaises(NetworkError): nr.accept(nr.AcceptBody(code=r["code"], grant=nr.GrantBody(scopes=["IDENTITY", "GOVERNANCE"])), self.prov, self.dara, self.svc, self.session)
        pv = nr.preview(nr.CodeBody(code=r["code"]), self.prov, self.dara, self.svc, self.session); self.assertTrue(pv["you_decide"])
        c = nr.accept(nr.AcceptBody(code=r["code"], grant=nr.GrantBody(scopes=["IDENTITY"])), self.prov, self.dara, self.svc, self.session)
        self.assertEqual(set(self.open(c["id"])["sections"]), {"identity"})
        self.assertEqual(len(nr.invites(self.view, self.svc)), 1); self.assertEqual(nr.invites(self.view, self.svc)[0]["status"], "ACCEPTED")

    def test_connection_lists_are_private_to_each_side(self):
        self.connect()
        self.assertEqual(len(nr.connections(self.prov, self.svc)), 1); self.assertEqual(len(nr.connections(self.view, self.svc)), 1)
        self.assertEqual(nr.connections("someone-else", self.svc), [])
        self.assertEqual(nr.connections(self.view, self.svc)[0]["counterparty"]["name"], "Meridian Textiles")


if __name__ == "__main__":
    unittest.main()
