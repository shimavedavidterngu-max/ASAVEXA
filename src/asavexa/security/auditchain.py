"""Tamper-evident audit log.

Every audit event is also linked into a per-organisation hash chain: link N holds sha256(link N-1's hash + the event's
digest), plus a MAC made with a platform key. Changing, deleting or re-ordering an event, or cutting links off the end,
makes verification fail; because of the MAC, someone with only database access cannot quietly rebuild the chain."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from ..audit.entity_ids import db_entity_id
from .store import DocStore

GENESIS = "0" * 64
GLOBAL = "GLOBAL"
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _norm(v):
    return json.loads(json.dumps(v, default=str, sort_keys=True)) if v is not None else None


def event_digest(e) -> str:
    ts = e.timestamp if e.timestamp.tzinfo else e.timestamp.replace(tzinfo=timezone.utc)
    body = {"id": e.id, "org": e.org_id, "et": e.entity_type, "eid": db_entity_id(e.entity_id), "a": e.action, "who": e.actor,
            "us": (ts - _EPOCH) // timedelta(microseconds=1),
            "prev": _norm(e.previous_value), "new": _norm(e.new_value), "why": e.reason, "rel": e.related_record_id}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _link_hash(prev: str, digest: str, seq: int) -> str:
    return hashlib.sha256(f"{prev}|{seq}|{digest}".encode()).hexdigest()


def _mac_data(scope, seq, h, prev):
    return f"{scope}|{seq}|{h}|{prev}".encode()


def append_link(store: DocStore, keys, event) -> None:
    """Adds one event to its organisation's chain. Call it right after the event is stored, inside the same transaction."""
    scope = event.org_id or GLOBAL
    head = store.get("audit_head", scope, for_update=True) or {"seq": 0, "hash": GENESIS}
    seq, prev = head["seq"] + 1, head["hash"]
    digest = event_digest(event)
    h = _link_hash(prev, digest, seq)
    kid, tag = keys.mac("audit-chain", _mac_data(scope, seq, h, prev))
    store.put("audit_link", f"{scope}:{seq:012d}", {"seq": seq, "event_id": event.id, "digest": digest, "prev": prev, "hash": h, "kid": kid, "mac": tag}, org_id=scope)
    kid2, tag2 = keys.mac("audit-head", _mac_data(scope, seq, h, ""))
    store.put("audit_head", scope, {"seq": seq, "hash": h, "kid": kid2, "mac": tag2}, org_id=scope)


class ChainedAuditRepository:
    """Wraps any audit repository. Same interface; every record() also extends the chain."""
    def __init__(self, inner, store: DocStore, keys):
        self._inner, self._store, self._keys = inner, store, keys

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def record(self, event):
        saved = self._inner.record(event)
        append_link(self._store, self._keys, event)
        return saved


def verify_chain(inner_audit, store: DocStore, keys, scope: str) -> dict:
    """Checks one organisation's chain against the stored audit events. Returns a plain report (never raises)."""
    problems: List[dict] = []
    links = [d for _, d in store.list("audit_link", prefix=scope + ":")]
    links.sort(key=lambda d: d["seq"])
    head = store.get("audit_head", scope)
    events = {}
    if scope != GLOBAL:
        events = {e.id: e for e in inner_audit.list_for_org(scope)}
    prev = GENESIS
    seen = set()
    for i, l in enumerate(links, start=1):
        if l["seq"] != i:
            problems.append({"seq": l["seq"], "problem": "A link is missing or out of order.", "kind": "SEQUENCE"}); prev = l["hash"]; continue
        if l["prev"] != prev:
            problems.append({"seq": i, "problem": "The link does not follow the one before it.", "kind": "BROKEN_LINK"})
        if _link_hash(l["prev"], l["digest"], i) != l["hash"]:
            problems.append({"seq": i, "problem": "The stored hash does not match its contents.", "kind": "BAD_HASH"})
        if not keys.verify_mac("audit-chain", _mac_data(scope, i, l["hash"], l["prev"]), l["kid"], l["mac"]):
            problems.append({"seq": i, "problem": "The link's signature is not valid (it was not written by this platform).", "kind": "BAD_SIGNATURE"})
        if scope != GLOBAL:
            ev = events.get(l["event_id"])
            if ev is None:
                problems.append({"seq": i, "event_id": l["event_id"], "problem": "An audit event that was recorded has been deleted.", "kind": "EVENT_DELETED"})
            elif event_digest(ev) != l["digest"]:
                problems.append({"seq": i, "event_id": l["event_id"], "problem": "An audit event was changed after it was recorded.", "kind": "EVENT_CHANGED"})
            seen.add(l["event_id"])
        prev = l["hash"]
    if head is None and links:
        problems.append({"problem": "The chain's head record is missing.", "kind": "HEAD_MISSING"})
    elif head is not None:
        last = links[-1] if links else None
        if (last["seq"] if last else 0) != head["seq"] or (last["hash"] if last else GENESIS) != head["hash"]:
            problems.append({"problem": "Links were removed from the end of the chain.", "kind": "TRUNCATED"})
        if not keys.verify_mac("audit-head", _mac_data(scope, head["seq"], head["hash"], ""), head["kid"], head["mac"]):
            problems.append({"problem": "The chain's head signature is not valid.", "kind": "BAD_HEAD_SIGNATURE"})
    unchained = [e for eid, e in events.items() if eid not in seen]
    return {"scope": scope, "ok": not problems, "links": len(links), "events": len(events) if scope != GLOBAL else None,
            "unchained_events": len(unchained), "problems": problems[:50], "problem_count": len(problems),
            "note": ("Events recorded before the chain was switched on are not covered." if unchained else None)}
