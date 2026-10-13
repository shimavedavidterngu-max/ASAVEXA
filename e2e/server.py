"""End-to-end test server. NOT the production server.

It runs the REAL router functions and REAL services (identity, accounting, evidence, reporting, compliance, Evidence Review, Standards Registry,
Agents, audit chain) behind a small HTTP front, with SQLite in memory and FastAPI stood in for (tests/harness_security_routers.py), so the browser
journeys can drive the real frontend without PostgreSQL. It proves the screens and the services work together. It does NOT prove FastAPI, SQLAlchemy,
PostgreSQL or deployment behaviour: tests/stack/ and CI cover those.

    PYTHONPATH=src:tests python3 e2e/server.py [port]      # default 8790
"""
import dataclasses
import importlib
import json
import os
import re
import sys
import types
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "src"), os.path.join(ROOT, "tests")]
import harness_security_routers as H0  # noqa: E402
from harness_security_routers import HTTPException, Request, auth  # noqa: E402
import test_passport as T  # noqa: E402

d = sys.modules["asavexa.api.deps"]
for n in ("get_reporting_service", "get_session", "get_security", "get_identity_service", "get_current_actor", "get_current_org"):
    setattr(d, n, lambda: None)
w = T.World()
w.compliance.evidence = w.vault          # api/deps.py does this in production

from asavexa.agents.service import AgentRegistry  # noqa: E402
from asavexa.evidence.domain.enums import EvidenceType  # noqa: E402
from asavexa.evidencereview.service import EvidenceReviewService  # noqa: E402
from asavexa.identity.domain.errors import AsavexaIdentityError, PermissionDeniedError  # noqa: E402
from asavexa.identity.domain.permissions import (AUDIT_READ, FINDING_MANAGE, FINDING_REMEDIATE, FINDING_VERIFY, GRC_APPROVE, GRC_PREPARE,  # noqa: E402
                                                 REPORTING_READ, ROLE_PERMISSIONS)
from asavexa.reporting.services.service import ReportingService  # noqa: E402
from asavexa.security import crypto  # noqa: E402
from asavexa.security.auditchain import ChainedAuditRepository  # noqa: E402
from asavexa.security.context import SecurityContext  # noqa: E402
from asavexa.security.errors import SecurityError  # noqa: E402
from asavexa.security.objectstore import MemoryObjectStore  # noqa: E402
from asavexa.security.sessions import SessionPolicy  # noqa: E402
from asavexa.security.store import SqliteDocStore  # noqa: E402
from asavexa.standards import catalog as CAT  # noqa: E402
from asavexa.standards.registry import StandardsRegistry  # noqa: E402
from asavexa.api import ratelimit  # noqa: E402

for name in ("get_evidence_review", "get_standards_registry", "get_agent_registry"):
    setattr(d, name, lambda: None)
er = importlib.import_module("asavexa.api.routers.evidence_review")
srt = importlib.import_module("asavexa.api.routers.standards_registry")
agr = importlib.import_module("asavexa.api.routers.agents")
asr = importlib.import_module("asavexa.api.routers.assurance")
plr = importlib.import_module("asavexa.api.routers.proof_links")
ratelimit.LOGIN.limit = ratelimit.MFA.limit = 10000

store = SqliteDocStore(w.conn)
keys = crypto.LocalKeyring({"k1": crypto.LocalKeyring.generate_key()}, "k1")
CH = ChainedAuditRepository(T.SqliteAuditRepository(w.conn), store, keys)
w.identity.audit = CH
ctx = SecurityContext(w.identity, CH, store, keys=keys, objects=MemoryObjectStore("NG"), now=lambda: datetime.now(timezone.utc), commit=w.conn.commit,
                      policy=SessionPolicy(idle_minutes=30, max_sessions=5), database_region="NG")


def log_for(kind):
    return lambda action, actor, eid, org, reason="": ctx.log(action, actor, eid, org_id=org, entity_type=kind, reason=reason)


is_member = lambda o, u: w.identity.memberships.get(o, u) is not None  # noqa: E731
rep = ReportingService(accounting=w.accounting, audit=w.audit, evidence=w.vault)
ers = EvidenceReviewService(store, rep, w.vault, w.compliance, is_member=is_member, log=log_for("EvidenceReview"))
srg = StandardsRegistry(store, log=log_for("StandardsRegistry"))
agrg = AgentRegistry(store, is_member=is_member, log=log_for("Agent"))
from asavexa.assurance.service import AssuranceService  # noqa: E402
asvc = AssuranceService({
    "evidence": lambda org: [(r.id, r.status.value, {"uploaded_by": r.uploaded_by, "verified_by": r.verified_by}) for r in w.vault.list_for_org(org)],
    "finding": lambda org: [(f.id, f.status.value, {}) for f in w.compliance.list_findings(org)],
    "evidence_review_case": lambda org: [(c["id"], c["status"], {}) for c in ers.list_cases(org)],
    "standards_source": lambda org: [(x["id"], x["status"], {}) for x in srg.list_sources(org)],
    "agent_decision": lambda org: [(d["id"], d["state"], {}) for d in agrg.list_decisions(org)],
})


from asavexa.proofgraph.links import ProofLinks  # noqa: E402
from asavexa.proofgraph.wiring import make_sources  # noqa: E402
pls = ProofLinks(store, make_sources(store, w.vault, w.compliance), log=log_for("ProofLink"))
ers.links = pls


def j(o):
    return json.dumps(o, default=lambda x: dataclasses.asdict(x) if dataclasses.is_dataclass(x) else (x.value if hasattr(x, "value") else (x.isoformat() if hasattr(x, "isoformat") else str(x))))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else j(body).encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

    def do_GET(self): self.go("GET")
    def do_POST(self): self.go("POST")

    def go(self, m):
        n = int(self.headers.get("content-length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}") if n else {}
        path, _, q = self.path.partition("?")
        qs = dict(x.split("=", 1) for x in q.split("&") if "=" in x)
        req = Request({"user-agent": self.headers.get("user-agent", ""), "x-forwarded-for": "7.7.7.7"})
        try:
            out = self.dispatch(m, path, qs, body, req)
            return self.send(*out) if isinstance(out, tuple) else self.send(200, out)
        except HTTPException as e: self.send(e.status_code, {"detail": e.detail})
        except SecurityError as e: self.send(e.status, {"error": type(e).__name__, "message": str(e)})
        except PermissionDeniedError as e: self.send(403, {"error": type(e).__name__, "message": str(e)})
        except AsavexaIdentityError as e: self.send(401, {"error": type(e).__name__, "message": str(e)})
        except Exception as e:
            import traceback; traceback.print_exc(); self.send(500, {"error": "InternalServerError", "message": str(e)})

    def dispatch(self, m, path, qs, b, req):
        if path == "/auth/login": return auth.login(req, auth.LoginRequest(**b), ctx).model_dump()
        tok = (self.headers.get("authorization") or "")[7:]
        s = w.identity.validate_session(tok); ctx.check_session(s)
        if path == "/organisations/mine":
            return [w.identity.organisations.get(x.org_id) for x in w.identity.memberships.list_for_user(s.user_id) if x.status.value == "ACTIVE"]
        if path == "/auth/select-organisation":
            s = w.identity.select_organisation(tok, b["org_id"]); return {"org_id": s.org_id, "role": w.identity.get_role(s.user_id, b["org_id"]).value}
        if path == "/auth/logout": w.identity.logout(tok); return (204, b"")
        org, a = s.org_id, s.user_id
        r = w.identity.get_role(a, org)

        def need(p):
            if r is None or p not in ROLE_PERMISSIONS[r]: raise PermissionDeniedError("You do not have " + p + ".")
        if path == "/periods": return w.accounting.periods.list_for_org(org)
        if path.startswith("/organisations/") and path.endswith("/members"): return w.identity.list_members(org)
        if path == "/standards/catalog": return {"frameworks": [{"code": k, **v} for k, v in CAT.FRAMEWORKS.items()], "jurisdictions": [{"code": k, "name": v} for k, v in CAT.JURISDICTIONS.items()]}
        # ---- test-only hooks the journeys use to play "the person who does the work in the Evidence Vault"
        if path == "/_fix":
            ev = w.vault.upload_evidence(org, EvidenceType.CONTRACT, b"lease-browser", "lease.pdf", "application/pdf", uploaded_by=w.accountant.id, linked_journal_id=w.rent_journal.id)
            w.vault.verify_evidence(org, ev.id, actor=w.approver.id); return {"ev": ev.id}
        if path == "/_audit":
            evs, _ = w.audit.list_recent_for_org(org, 1000); return {"actions": [e.action for e in evs]}
        if path.startswith("/evidence-review"):
            need(REPORTING_READ)
            if path == "/evidence-review/review": return er.review(qs["period_id"], qs.get("report", "income_statement"), qs.get("account_id"), org, a, ers)
            if path == "/evidence-review/rules" and m == "GET": return er.rules_overview(org, ers)
            if path == "/evidence-review/rules" and m == "POST": need(GRC_PREPARE); return (201, er.propose_rules(er.RulesBody(**b), org, a, ers))
            mm = re.match(r"/evidence-review/rules/(\d+)/(approve|reject)$", path)
            if mm:
                need(GRC_APPROVE)
                return er.approve_rules(int(mm.group(1)), er.DecisionBody(**b), org, a, ers) if mm.group(2) == "approve" else er.reject_rules(int(mm.group(1)), er.RejectBody(**b), org, a, ers)
            if path == "/evidence-review/cases" and m == "GET": return er.list_cases(None, org, ers)
            if path == "/evidence-review/cases" and m == "POST": need(FINDING_MANAGE); return (201, er.open_case(er.OpenBody(**b), org, a, ers))
            mm = re.match(r"/evidence-review/cases/([^/]+)(?:/(\w+))?$", path)
            if mm:
                cid, act = mm.groups()
                if act is None: return er.get_case(cid, org, ers)
                if act == "plan": need(FINDING_MANAGE); return er.plan(cid, er.PlanBody(**b), org, a, ers)
                if act == "complete": need(FINDING_REMEDIATE); return er.complete(cid, er.DoneBody(**b), org, a, ers)
                if act == "verify": need(FINDING_VERIFY); return er.verify(cid, er.VerifyBody(**b), org, a, ers)
                if act == "recheck": need(FINDING_VERIFY); return er.recheck(cid, org, a, ers)
        if path.startswith("/assurance"):
            need(AUDIT_READ)
            if path == "/assurance/vocabulary": return asr.vocabulary()
            if path == "/assurance/summary": return asr.summary(org, asvc)
        if path.startswith("/proof-links"):
            need(AUDIT_READ)
            if path == "/proof-links/vocabulary": return plr.vocabulary()
            if path == "/proof-links/choices": return plr.choices(qs["type"], org, pls)
            if path == "/proof-links/graph": return plr.graph(qs["type"], qs["id"], int(qs.get("depth", 1)), False, org, pls)
            if path == "/proof-links" and m == "GET": return plr.list_all(qs.get("status"), org, pls)
            if path == "/proof-links" and m == "POST": need(GRC_PREPARE); return (201, plr.add(plr.LinkBody(**b), org, a, pls))
            if path == "/proof-links/gaps" and m == "POST": need(GRC_PREPARE); return (201, plr.expect(plr.GapBody(**b), org, a, pls))
            mm = re.match(r"/proof-links/gaps/([^/]+)/waive$", path)
            if mm: need(GRC_APPROVE); return plr.waive(mm.group(1), plr.ReasonBody(**b), org, a, pls)
            mm = re.match(r"/proof-links/([^/]+)$", path)
            if mm and m == "GET": return plr.get_one(mm.group(1), org, pls)
            mm = re.match(r"/proof-links/([^/]+)/(retire|dispute|confirm|reinstate)$", path)
            if mm:
                lid, act = mm.groups()
                if act in ("retire", "dispute"): need(GRC_PREPARE)
                else: need(GRC_APPROVE)
                body = plr.NoteBody(**b) if act == "confirm" else plr.ReasonBody(**b)
                return getattr(plr, act)(lid, body, org, a, pls)
        if path.startswith("/standards-registry"):
            need(AUDIT_READ)
            if path == "/standards-registry/coverage": return srt.coverage(qs.get("jurisdiction"), org, srg)
            if path == "/standards-registry/sources" and m == "GET": return srt.list_sources(None, None, org, srg)
            if path == "/standards-registry/sources" and m == "POST": need(GRC_PREPARE); return (201, srt.add_source(srt.SourceBody(**b), org, a, srg))
            mm = re.match(r"/standards-registry/sources/([^/]+)/([\w-]+)$", path)
            if mm:
                sid, act = mm.groups()
                if act == "submit": need(GRC_PREPARE); return srt.submit(sid, org, a, srg)
                need(GRC_APPROVE)
                if act == "approve": return srt.approve(sid, srt.NoteBody(**b), org, a, srg)
                if act == "send-back": return srt.send_back(sid, srt.ReasonBody(**b), org, a, srg)
                if act == "withdraw": return srt.withdraw(sid, srt.ReasonBody(**b), org, a, srg)
        if path.startswith("/agents"):
            need(AUDIT_READ)
            if path == "/agents/catalog": return agr.catalog(org, agrg)
            if path == "/agents/decisions" and m == "GET": return agr.list_decisions(None, org, agrg)
            if path == "/agents/decisions" and m == "POST": need(GRC_PREPARE); return (201, agr.decide(agr.DecideBody(**b), org, a, agrg))
            if path == "/agents/policy": need(GRC_APPROVE); return agr.tighten(agr.PolicyBody(**b), org, a, agrg)
            if path == "/agents" and m == "GET": return agr.list_agents(org, agrg)
            if path == "/agents" and m == "POST": need(GRC_PREPARE); return (201, agr.propose(agr.AgentBody(**b), org, a, agrg))
            mm = re.match(r"/agents/decisions/([^/]+)/(resolve|confirm)$", path)
            if mm:
                did, act = mm.groups()
                if act == "resolve": need(GRC_APPROVE); return agr.resolve(did, agr.ResolveBody(**b), org, a, agrg)
                need(GRC_PREPARE); return agr.confirm(did, org, a, agrg)
            mm = re.match(r"/agents/([^/]+)/(activate|suspend|retire)$", path)
            if mm:
                aid, act = mm.groups(); need(GRC_APPROVE)
                if act == "activate": return agr.activate(aid, agr.NoteBody(**b), org, a, agrg)
                return getattr(agr, act)(aid, agr.ReasonBody(**b), org, a, agrg)
        return (404, {"detail": "no route " + path})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8790
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
