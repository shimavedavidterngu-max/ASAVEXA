"""The stored Proof-to-Action graph (Stage 13).

The Proof-to-Report graph is worked out on demand and stops at the report. This adds LINKS that people (or the platform, as a by-product of its own work)
RECORD between the records that matter once something goes wrong: evidence, controls, findings, remediations, cases, standards, risks, actions and
agent decisions. A link says what one record has to do with another ("this evidence supports that finding"), who said so, when, and why.

Honest by design:
  * A link is a claim somebody made, kept with its history. It is never deleted; it can be RETIRED (with a reason), DISPUTED, and REINSTATED.
  * A link starts as RECORDED (by a person) or SYSTEM (the platform created it while doing something else). A DIFFERENT person can CONFIRM it.
    Nobody can confirm their own link, and the person who disputed a link cannot be the one who reinstates it.
  * "An expected link is missing" can be written down too (a GAP), and "these two records conflict" is a relation (CONFLICTS_WITH).
  * Both ends must exist in the SAME organisation when the link is made. A link cannot cross organisations.
  * It records relationships. It does not change, approve, verify or delete either record, and a link existing does not make the claim true.
"""
from __future__ import annotations

import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Callable, Dict, List, NamedTuple, Optional, Tuple

from ..security.errors import SecurityError

LINK_KIND, GAP_KIND = "pa_link", "pa_gap"
LINK_STATUSES = ("ACTIVE", "DISPUTED", "RETIRED")
GAP_STATUSES = ("OPEN", "FILLED", "WAIVED")
BASIS = ("RECORDED", "SYSTEM")
MAX_TEXT = 2000
MAX_LINKS = 2000
MAX_NODES = 200
MAX_CHOICES = 100

NODE_TYPES = {
    "evidence": "Evidence", "control": "Control", "finding": "Finding", "remediation": "Remediation", "outcome": "Evidence Review case",
    "standard": "Standards source", "risk": "Risk", "action": "Risk action", "decision": "Agent decision",
}
ANY = frozenset(NODE_TYPES)
RELATIONS = {
    "EVIDENCES": {"label": "provides evidence for", "from": {"evidence"}, "to": {"finding", "remediation", "outcome", "risk", "action", "control", "decision"}},
    "RAISED_BY": {"label": "was raised by", "from": {"finding"}, "to": {"control"}},
    "ADDRESSES": {"label": "addresses", "from": {"remediation", "outcome"}, "to": {"finding"}},
    "ADDRESSES_RISK": {"label": "addresses the risk", "from": {"action"}, "to": {"risk"}},
    "MITIGATES": {"label": "mitigates", "from": {"control"}, "to": {"risk"}},
    "AUTHORISES": {"label": "authorises", "from": {"decision"}, "to": {"remediation", "action", "outcome"}},
    "GOVERNED_BY": {"label": "is governed by", "from": {"control", "risk", "finding"}, "to": {"standard"}},
    "CONFLICTS_WITH": {"label": "conflicts with", "from": ANY, "to": ANY},
}
SYMMETRIC = {"CONFLICTS_WITH"}


class GraphLinkError(SecurityError): status = 400
class GraphLinkNotFoundError(GraphLinkError): status = 404
class GraphLinkStateError(GraphLinkError): status = 409
class GraphLinkForbiddenError(GraphLinkError): status = 403


class NodeSource(NamedTuple):
    """How the graph reaches one kind of record. `label(org, id)` returns its name, or None when that record is not in this organisation.
    `choices(org)` lists records a person can pick from (may be empty for kinds that cannot be listed)."""
    label: Callable[[str, str], Optional[str]]
    choices: Callable[[str], List[Tuple[str, str]]]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _text(v, label, required=True) -> str:
    s = (v or "").strip() if isinstance(v, str) or v is None else str(v).strip()
    if required and not s:
        raise GraphLinkError(f"{label} is required.")
    if len(s) > MAX_TEXT:
        raise GraphLinkError(f"{label} must be at most {MAX_TEXT} characters.")
    return s


class ProofLinks:
    def __init__(self, store, sources: Dict[str, NodeSource], log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = _now):
        self.store, self.sources, self.log, self.now = store, dict(sources), log, now

    # ---------------------------------------------------------------- helpers
    def _all(self, kind, org) -> List[dict]:
        return [d for _, d in self.store.list(kind, org_id=org) if d.get("org") == org]

    def _put(self, kind, org, d): self.store.put(kind, f"{org}:{d['id']}", d, org_id=org)

    def _get(self, kind, org, did, label, for_update=False) -> dict:
        d = self.store.get(kind, f"{org}:{did}", for_update=for_update) if isinstance(did, str) and did else None
        if d is None or d.get("org") != org:
            raise GraphLinkNotFoundError(f"{label} not found.")
        return d

    def _stamp(self, d, actor, event, note=""):
        d["history"].append({"at": self.now().isoformat(), "by": actor, "event": event, "note": note})
        d["updated_at"] = self.now().isoformat()

    def _node(self, org, ref) -> dict:
        try:
            ntype, nid = ref
        except (TypeError, ValueError):
            raise GraphLinkError("A record must be given as a type and an id.")
        if ntype not in NODE_TYPES:
            raise GraphLinkError(f"Record type must be one of: {', '.join(NODE_TYPES)}.")
        nid = str(nid or "").strip()
        if not nid or len(nid) > 100:
            raise GraphLinkError("A record id is required.")
        src = self.sources.get(ntype)
        label = None
        if src is not None:
            try:
                label = src.label(org, nid)
            except Exception:
                label = None
        if not label:
            raise GraphLinkNotFoundError(f"{NODE_TYPES[ntype]} not found in this organisation.")
        return {"type": ntype, "id": nid, "label": str(label)[:200]}

    @staticmethod
    def _same(a, b) -> bool:
        return a["type"] == b["type"] and a["id"] == b["id"]

    def _existing(self, org, a, b, relation) -> Optional[dict]:
        for d in self._all(LINK_KIND, org):
            if d["status"] == "RETIRED" or d["relation"] != relation:
                continue
            if (self._same(d["from"], a) and self._same(d["to"], b)) or (relation in SYMMETRIC and self._same(d["from"], b) and self._same(d["to"], a)):
                return d
        return None

    # ---------------------------------------------------------------- links
    def link_records(self, org, from_ref, to_ref, relation, actor, note="", _basis="RECORDED", _idempotent=False) -> dict:
        rel = RELATIONS.get(relation)
        if rel is None:
            raise GraphLinkError(f"Relation must be one of: {', '.join(RELATIONS)}.")
        a, b = self._node(org, from_ref), self._node(org, to_ref)
        if a["type"] not in rel["from"] or b["type"] not in rel["to"]:
            raise GraphLinkError(f"A {NODE_TYPES[a['type']].lower()} cannot {rel['label']} a {NODE_TYPES[b['type']].lower()}.")
        if self._same(a, b):
            raise GraphLinkError("A record cannot be linked to itself.")
        note = _text(note, "Note", required=False)
        dup = self._existing(org, a, b, relation)
        if dup is not None:
            if _idempotent:
                return dup
            raise GraphLinkStateError("That link already exists.")
        if sum(1 for d in self._all(LINK_KIND, org) if d["status"] != "RETIRED") >= MAX_LINKS:
            raise GraphLinkStateError(f"This organisation already has {MAX_LINKS} live links. Retire some before adding more.")
        d = {"id": str(uuid.uuid4()), "org": org, "from": a, "to": b, "relation": relation, "status": "ACTIVE", "basis": _basis, "note": note,
             "created_by": actor, "created_at": self.now().isoformat(), "updated_at": self.now().isoformat(), "confirmed_by": None, "confirmed_at": None,
             "disputed_by": None, "history": []}
        self._stamp(d, actor, "CREATED", note)
        self._put(LINK_KIND, org, d)
        self.log("GRAPH_LINK_ADDED", actor, d["id"], org, f"{a['type']} {relation} {b['type']} ({_basis.lower()})")
        for g in self._all(GAP_KIND, org):                      # a link of the expected kind closes the gap it fills
            if g["status"] == "OPEN" and self._same(g["from"], a) and g["relation"] == relation and (not g["expected_type"] or g["expected_type"] == b["type"]):
                g.update(status="FILLED", filled_by_link=d["id"]); self._stamp(g, actor, "FILLED", f"Filled by link {d['id']}")
                self._put(GAP_KIND, org, g)
                self.log("GRAPH_GAP_FILLED", actor, g["id"], org, f"{a['type']} {relation}")
        return d

    def record_system_link(self, org, from_ref, to_ref, relation, actor, note="") -> dict:
        """A link the platform makes while doing its own work (for example, a case and the finding it addresses). It is marked SYSTEM and is idempotent."""
        return self.link_records(org, from_ref, to_ref, relation, actor, note, _basis="SYSTEM", _idempotent=True)

    def retire_link(self, org, link_id, actor, reason) -> dict:
        d = self._get(LINK_KIND, org, link_id, "Link", for_update=True)
        if d["status"] == "RETIRED":
            raise GraphLinkStateError("That link is already retired.")
        reason = _text(reason, "Reason")
        d["status"] = "RETIRED"; self._stamp(d, actor, "RETIRED", reason); self._put(LINK_KIND, org, d)
        self.log("GRAPH_LINK_RETIRED", actor, link_id, org, reason[:120])
        return d

    def dispute_link(self, org, link_id, actor, reason) -> dict:
        d = self._get(LINK_KIND, org, link_id, "Link", for_update=True)
        if d["status"] != "ACTIVE":
            raise GraphLinkStateError(f"Only an active link can be disputed (this one is {d['status'].lower()}).")
        reason = _text(reason, "Reason")
        d.update(status="DISPUTED", disputed_by=actor, confirmed_by=None, confirmed_at=None); self._stamp(d, actor, "DISPUTED", reason); self._put(LINK_KIND, org, d)
        self.log("GRAPH_LINK_DISPUTED", actor, link_id, org, reason[:120])
        return d

    def reinstate_link(self, org, link_id, actor, note) -> dict:
        d = self._get(LINK_KIND, org, link_id, "Link", for_update=True)
        if d["status"] != "DISPUTED":
            raise GraphLinkStateError(f"Only a disputed link can be reinstated (this one is {d['status'].lower()}).")
        if actor == d["disputed_by"]:
            raise GraphLinkForbiddenError("The person who disputed this link cannot reinstate it. Someone else must.")
        note = _text(note, "Note")
        d.update(status="ACTIVE", disputed_by=None); self._stamp(d, actor, "REINSTATED", note); self._put(LINK_KIND, org, d)
        self.log("GRAPH_LINK_REINSTATED", actor, link_id, org, note[:120])
        return d

    def confirm_link(self, org, link_id, actor, note="") -> dict:
        d = self._get(LINK_KIND, org, link_id, "Link", for_update=True)
        if d["status"] != "ACTIVE":
            raise GraphLinkStateError(f"Only an active link can be confirmed (this one is {d['status'].lower()}).")
        if d["confirmed_by"]:
            raise GraphLinkStateError("That link has already been confirmed.")
        if actor == d["created_by"]:
            raise GraphLinkForbiddenError("You made this link, so you cannot confirm it. A different person must.")
        d.update(confirmed_by=actor, confirmed_at=self.now().isoformat()); self._stamp(d, actor, "CONFIRMED", _text(note, "Note", required=False)); self._put(LINK_KIND, org, d)
        self.log("GRAPH_LINK_CONFIRMED", actor, link_id, org, f"{d['from']['type']} {d['relation']} {d['to']['type']}")
        return d

    # ---------------------------------------------------------------- gaps: "an expected link is missing"
    def expect_link(self, org, from_ref, relation, actor, note, expected_type: Optional[str] = None) -> dict:
        rel = RELATIONS.get(relation)
        if rel is None:
            raise GraphLinkError(f"Relation must be one of: {', '.join(RELATIONS)}.")
        a = self._node(org, from_ref)
        if a["type"] not in rel["from"]:
            raise GraphLinkError(f"A {NODE_TYPES[a['type']].lower()} cannot {rel['label']} anything.")
        if expected_type and expected_type not in rel["to"]:
            raise GraphLinkError(f"It cannot {rel['label']} a {NODE_TYPES.get(expected_type, expected_type)}.")
        note = _text(note, "What is missing and why it matters")
        for g in self._all(GAP_KIND, org):
            if g["status"] == "OPEN" and self._same(g["from"], a) and g["relation"] == relation and g["expected_type"] == (expected_type or None):
                raise GraphLinkStateError("That missing link is already recorded.")
        g = {"id": str(uuid.uuid4()), "org": org, "from": a, "relation": relation, "expected_type": expected_type or None, "status": "OPEN", "note": note,
             "created_by": actor, "created_at": self.now().isoformat(), "updated_at": self.now().isoformat(), "filled_by_link": None, "waived_by": None, "history": []}
        self._stamp(g, actor, "RECORDED", note)
        self._put(GAP_KIND, org, g)
        self.log("GRAPH_GAP_RECORDED", actor, g["id"], org, f"{a['type']} {relation}")
        return g

    def waive_gap(self, org, gap_id, actor, reason) -> dict:
        g = self._get(GAP_KIND, org, gap_id, "Missing link", for_update=True)
        if g["status"] != "OPEN":
            raise GraphLinkStateError(f"Only an open gap can be waived (this one is {g['status'].lower()}).")
        if actor == g["created_by"]:
            raise GraphLinkForbiddenError("You recorded this gap, so you cannot waive it. A different person must.")
        g.update(status="WAIVED", waived_by=actor); self._stamp(g, actor, "WAIVED", _text(reason, "Reason")); self._put(GAP_KIND, org, g)
        self.log("GRAPH_GAP_WAIVED", actor, gap_id, org, f"{g['from']['type']} {g['relation']}")
        return g

    # ---------------------------------------------------------------- read
    def get_link(self, org, link_id) -> dict:
        return self._get(LINK_KIND, org, link_id, "Link")

    def neighbourhood(self, org, ntype, nid, depth: int = 1, include_retired: bool = False) -> dict:
        focus = self._node(org, (ntype, nid))
        if not isinstance(depth, int) or isinstance(depth, bool) or not 1 <= depth <= 3:
            raise GraphLinkError("Depth must be 1, 2 or 3.")
        links = [d for d in self._all(LINK_KIND, org) if include_retired or d["status"] != "RETIRED"]
        by_node: Dict[Tuple[str, str], List[dict]] = {}
        for d in links:
            by_node.setdefault((d["from"]["type"], d["from"]["id"]), []).append(d); by_node.setdefault((d["to"]["type"], d["to"]["id"]), []).append(d)
        seen = {(focus["type"], focus["id"]): focus}; used: Dict[str, dict] = {}; truncated = False
        queue = deque([((focus["type"], focus["id"]), 0)])
        while queue:
            key, dist = queue.popleft()
            if dist >= depth:
                continue
            for d in sorted(by_node.get(key, []), key=lambda x: x["created_at"]):
                used[d["id"]] = d
                for end in (d["from"], d["to"]):
                    k = (end["type"], end["id"])
                    if k not in seen:
                        if len(seen) >= MAX_NODES:
                            truncated = True; continue
                        seen[k] = end; queue.append((k, dist + 1))
        gaps = [g for g in self._all(GAP_KIND, org) if (g["from"]["type"], g["from"]["id"]) in seen and g["status"] != "FILLED"]
        return {"focus": focus, "nodes": list(seen.values()), "links": sorted(used.values(), key=lambda x: x["created_at"]),
                "gaps": sorted(gaps, key=lambda x: x["created_at"]), "truncated": truncated, "depth": depth,
                "note": "A link is a claim somebody recorded. It does not make the claim true, and it does not change either record."}

    def list_links(self, org, status: Optional[str] = None) -> List[dict]:
        out = [d for d in self._all(LINK_KIND, org) if status is None or d["status"] == status]
        return sorted(out, key=lambda d: d["created_at"], reverse=True)

    def link_choices(self, org, ntype) -> List[dict]:
        if ntype not in NODE_TYPES:
            raise GraphLinkError(f"Record type must be one of: {', '.join(NODE_TYPES)}.")
        src = self.sources.get(ntype)
        if src is None:
            return []
        try:
            rows = list(src.choices(org))[:MAX_CHOICES]
        except Exception:
            rows = []
        return [{"id": str(i), "label": str(label)[:200]} for i, label in rows]

    @staticmethod
    def link_vocabulary() -> dict:
        return {"types": [{"code": c, "label": t} for c, t in NODE_TYPES.items()],
                "relations": [{"code": c, "label": r["label"], "from": sorted(r["from"]), "to": sorted(r["to"]), "symmetric": c in SYMMETRIC} for c, r in RELATIONS.items()],
                "note": "A link is a claim somebody recorded, kept with its history. A different person can confirm it. It does not make the claim true."}
