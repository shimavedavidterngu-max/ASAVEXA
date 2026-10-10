"""The ASAVEXA Network: organisations of different kinds connected by explicit, scoped, revocable consent.

        Businesses  <->  Accountants / Auditors / Banks / Investors / Donors / Regulators

Rules this module enforces (and tests prove):
- The business (data owner) always decides what a connection may see. A counterparty can ask for a lot; the business can narrow it. Nobody can widen it
  for themselves. What is shareable is exactly the existing Financial Passport sections, so the network cannot expose anything sharing could not.
- A connection exists only after BOTH sides agreed: one side issues a one-time invitation code, the other side's administrator enters it.
- Access is checked on every view: the connection must be active, unexpired, and the viewer must be the organisation it was made with.
  Either side can end it at any time and the viewer loses access immediately. Expired connections stop working by themselves.
- Everything is written to the audit trail of BOTH organisations.
- Data flows from a business to the other six kinds. Connections between two non-business organisations carry no data and are not offered.
Storage is injected (a DocStore), so the same code runs over SQLite in tests and PostgreSQL in production."""
from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional

from ..passport.errors import ShareValidationError
from ..passport.sharing import SCOPES, validate_request
from .errors import NetworkError, NetworkForbiddenError, NetworkNotFoundError, NetworkStateError

TYPES = ("BUSINESS", "ACCOUNTANT", "AUDITOR", "BANK", "INVESTOR", "DONOR", "REGULATOR")
TYPE_TEXT = {"BUSINESS": "Business or NGO", "ACCOUNTANT": "Accountant / accounting firm", "AUDITOR": "Auditor", "BANK": "Bank or lender", "INVESTOR": "Investor",
             "DONOR": "Donor or funder", "REGULATOR": "Regulator"}
VIEWER_TYPES = tuple(t for t in TYPES if t != "BUSINESS")
MAX_ACTIVE_CONNECTIONS = 50
MAX_PENDING_INVITES = 20
MAX_FAILED_CODES = 8
FAIL_WINDOW = timedelta(minutes=15)
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _utc(): return datetime.now(timezone.utc)
def _aware(s): d = datetime.fromisoformat(s) if isinstance(s, str) else s; return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
def _norm(code: str) -> str: return re.sub(r"[\s\-]", "", (code or "")).upper().removeprefix("ASX")
def _h(code: str) -> str: return hashlib.sha256(("asavexa-network:" + _norm(code)).encode()).hexdigest()
def new_code() -> str:
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(10))
    return f"ASX-{raw[:5]}-{raw[5:]}"


def _txt(v, name, lo=1, hi=300, required=True) -> str:
    v = (v if isinstance(v, str) else ("" if v is None else str(v))).strip()
    if required and len(v) < lo:
        raise NetworkError(f"{name} is required.")
    if len(v) > hi:
        raise NetworkError(f"{name} is too long (limit {hi} characters).")
    return v


def _days(v, name, lo, hi) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
        raise NetworkError(f"{name} must be a whole number of days from {lo} to {hi}.")
    return v


def default_grant(today: date) -> dict:
    return {"scopes": ["IDENTITY", "FINANCIAL_HISTORY", "EVIDENCE_QUALITY"], "include_detail": False, "closed_periods_only": True,
            "date_from": date(today.year - 3, 1, 1).isoformat(), "date_to": today.isoformat()}


def clean_grant(g: Optional[dict], today: date) -> dict:
    """Validates a grant with the SAME rules as Passport sharing. Safe defaults: summary only, finished periods only."""
    g = {**default_grant(today), **{k: v for k, v in (g or {}).items() if v is not None}}
    try:
        r = validate_request({"recipient_name": "network", "scopes": g["scopes"], "date_from": g["date_from"], "date_to": g["date_to"], "expires_in_days": 30,
                              "include_detail": g["include_detail"], "closed_periods_only": g["closed_periods_only"]})
    except ShareValidationError as e:
        raise NetworkError(str(e))
    return {"scopes": r["scopes"], "include_detail": r["include_detail"], "closed_periods_only": r["closed_periods_only"],
            "date_from": r["date_from"].isoformat(), "date_to": r["date_to"].isoformat()}


def within(narrow: dict, wide: dict) -> Optional[str]:
    """None if `narrow` asks for nothing beyond `wide`; otherwise a sentence saying what goes beyond."""
    extra = [s for s in narrow["scopes"] if s not in wide["scopes"]]
    if extra: return "It includes sections that were not requested: " + ", ".join(extra) + "."
    if narrow["include_detail"] and not wide["include_detail"]: return "It includes line-level detail that was not requested."
    if not narrow["closed_periods_only"] and wide["closed_periods_only"]: return "It includes unfinished periods that were not requested."
    if narrow["date_from"] < wide["date_from"] or narrow["date_to"] > wide["date_to"]: return "Its dates go beyond the requested dates."
    return None


def grant_to_request(grant: dict) -> dict:
    """The shape the Passport builder expects (dates as dates)."""
    return {"scopes": list(grant["scopes"]), "include_detail": grant["include_detail"], "closed_periods_only": grant["closed_periods_only"],
            "date_from": date.fromisoformat(grant["date_from"]), "date_to": date.fromisoformat(grant["date_to"])}


class NetworkService:
    def __init__(self, store, log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = _utc):
        self.store, self.log, self.now = store, log, now

    # ------------------------------------------------------------------ profile
    def set_profile(self, org: str, actor: str, org_type: str, display_name: str, description: str = "") -> dict:
        org_type = (org_type or "").upper()
        if org_type not in TYPES:
            raise NetworkError("Type must be one of: " + ", ".join(TYPES) + ".")
        prev = self.store.get("net_profile", org, for_update=True)
        if prev and prev["org_type"] != org_type and any(c["status"] == "ACTIVE" for c in self.list_connections(org)):
            raise NetworkStateError("This organisation has active connections, so its type cannot change. End them first.")
        p = {"org_id": org, "org_type": org_type, "display_name": _txt(display_name, "Display name", 2, 120), "description": _txt(description, "Description", hi=500, required=False),
             "updated_by": actor, "updated_at": self.now().isoformat()}
        self.store.put("net_profile", org, p, org_id=org)
        self.log("NETWORK_PROFILE_SET", actor, org, org, f"{org_type}: {p['display_name']}")
        return p

    def profile(self, org: str) -> Optional[dict]:
        return self.store.get("net_profile", org)

    def _need_profile(self, org: str) -> dict:
        p = self.profile(org)
        if p is None:
            raise NetworkStateError("Set your organisation's network profile (what kind of organisation you are) first.")
        return p

    # ------------------------------------------------------------------ invitations
    @staticmethod
    def kind_for(my_type: str, counterparty_type: str) -> str:
        """OFFER: a business offers its data. REQUEST: a counterparty asks a business for data. Anything else carries no data and is refused."""
        if my_type == "BUSINESS" and counterparty_type in VIEWER_TYPES: return "OFFER"
        if my_type in VIEWER_TYPES and counterparty_type == "BUSINESS": return "REQUEST"
        raise NetworkError("Connections carry a business's information to an accountant, auditor, bank, investor, donor or regulator. "
                           "A business connects to one of those, and one of those connects to a business.")

    def create_invite(self, org: str, actor: str, counterparty_type: str, purpose: str, grant: Optional[dict] = None, invite_days: int = 14, connection_days: int = 90, note: str = "") -> dict:
        me = self._need_profile(org)
        counterparty_type = (counterparty_type or "").upper()
        if counterparty_type not in TYPES:
            raise NetworkError("Counterparty type must be one of: " + ", ".join(TYPES) + ".")
        kind = self.kind_for(me["org_type"], counterparty_type)
        if sum(1 for i in self.list_invites(org) if i["status"] == "PENDING") >= MAX_PENDING_INVITES:
            raise NetworkStateError(f"There are already {MAX_PENDING_INVITES} pending invitations. Cancel some first.")
        now = self.now()
        code = new_code()
        inv = {"id": str(uuid.uuid4()), "org_id": org, "initiator_name": me["display_name"], "initiator_type": me["org_type"], "kind": kind, "counterparty_type": counterparty_type,
               "purpose": _txt(purpose, "Purpose", 3, 300), "note": _txt(note, "Note", hi=500, required=False), "grant": clean_grant(grant, now.date()),
               "invite_days": _days(invite_days, "Invitation validity", 1, 30), "connection_days": _days(connection_days, "Connection length", 1, 365),
               "status": "PENDING", "created_by": actor, "created_at": now.isoformat(), "expires_at": (now + timedelta(days=invite_days)).isoformat(), "code_hash": _h(code)}
        self.store.put("net_invite", inv["id"], inv, org_id=org)
        self.store.put("net_code", inv["code_hash"], {"invite_id": inv["id"], "org_id": org}, org_id=org)
        self.log("NETWORK_INVITE_CREATED", actor, inv["id"], org, f"{kind} to a {TYPE_TEXT[counterparty_type]}: {inv['purpose']}")
        return {"invite": self._pub_invite(inv), "code": code, "note": "This code is shown once and cannot be recovered. Send it to the other organisation by a separate route (a call, not the same email as other details)."}

    @staticmethod
    def _eff_invite(inv: dict, now: datetime) -> str:
        return "EXPIRED" if inv["status"] == "PENDING" and now >= _aware(inv["expires_at"]) else inv["status"]

    def _pub_invite(self, inv: dict) -> dict:
        return {k: inv[k] for k in ("id", "kind", "counterparty_type", "purpose", "note", "grant", "invite_days", "connection_days", "created_at", "expires_at")} | {"status": self._eff_invite(inv, self.now())}

    def list_invites(self, org: str) -> List[dict]:
        return sorted((self._pub_invite(i) for _, i in self.store.list("net_invite", org_id=org)), key=lambda i: i["created_at"], reverse=True)

    def cancel_invite(self, org: str, actor: str, invite_id: str) -> dict:
        inv = self.store.get("net_invite", invite_id, for_update=True)
        if inv is None or inv["org_id"] != org:
            raise NetworkNotFoundError("Invitation not found.")
        if inv["status"] != "PENDING":
            raise NetworkStateError("Only a pending invitation can be cancelled.")
        inv["status"] = "CANCELLED"
        self.store.put("net_invite", inv["id"], inv, org_id=org)
        self.log("NETWORK_INVITE_CANCELLED", actor, inv["id"], org, inv["purpose"])
        return self._pub_invite(inv)

    # ---- looking a code up is throttled per person, because a code is a secret that opens a connection
    def _check_throttle(self, actor: str) -> None:
        a = self.store.get("net_attempts", actor) or {"fails": []}
        recent = [f for f in a["fails"] if self.now() - _aware(f) < FAIL_WINDOW]
        if len(recent) >= MAX_FAILED_CODES:
            raise NetworkStateError("Too many wrong codes. Wait 15 minutes and check the code with the sender.")

    def _fail(self, actor: str) -> None:
        a = self.store.get("net_attempts", actor, for_update=True) or {"fails": []}
        a["fails"] = [f for f in a["fails"] if self.now() - _aware(f) < FAIL_WINDOW] + [self.now().isoformat()]
        self.store.put("net_attempts", actor, a, org_id=None)

    def _lookup(self, org: str, actor: str, code: str) -> dict:
        self._check_throttle(actor)
        idx = self.store.get("net_code", _h(code))
        inv = self.store.get("net_invite", idx["invite_id"], for_update=True) if idx else None
        generic = "That invitation code is not valid. It may be mistyped, expired, cancelled or already used."
        if inv is None or inv["org_id"] == org or self._eff_invite(inv, self.now()) != "PENDING":
            self._fail(actor)
            raise NetworkError(generic)
        return inv

    def preview_invite(self, org: str, actor: str, code: str) -> dict:
        """What the receiving organisation is being asked to agree to, before it agrees."""
        inv = self._lookup(org, actor, code)
        me = self._need_profile(org)
        self._compatible(inv, me)
        return {"kind": inv["kind"], "from": {"name": inv["initiator_name"], "type": inv["initiator_type"]}, "purpose": inv["purpose"], "note": inv["note"], "grant": inv["grant"],
                "connection_days": inv["connection_days"], "expires_at": inv["expires_at"],
                "you_decide": inv["kind"] == "REQUEST", "explain": ("This organisation asks to see the information below. You can share less, never more." if inv["kind"] == "REQUEST"
                                                                   else "This business offers you the information below.")}

    @staticmethod
    def _compatible(inv: dict, me: dict) -> None:
        if inv["kind"] == "OFFER" and me["org_type"] != inv["counterparty_type"]:
            raise NetworkError(f"This invitation was made to a {TYPE_TEXT[inv['counterparty_type']].lower()}, but your organisation is registered as a {TYPE_TEXT[me['org_type']].lower()}.")
        if inv["kind"] == "REQUEST" and me["org_type"] != "BUSINESS":
            raise NetworkError("This is a request for a business's information, so only a business can answer it.")

    def accept_invite(self, org: str, actor: str, code: str, grant: Optional[dict] = None, connection_days: Optional[int] = None) -> dict:
        inv = self._lookup(org, actor, code)
        me = self._need_profile(org)
        self._compatible(inv, me)
        now = self.now()
        if inv["kind"] == "OFFER":
            provider, viewer, g, days = inv["org_id"], org, inv["grant"], inv["connection_days"]
            viewer_prof, provider_prof = me, self.profile(inv["org_id"])
            if grant is not None:
                raise NetworkError("An offer is accepted as it is. Ask the business for a different offer instead.")
        else:
            provider, viewer = org, inv["org_id"]
            g = clean_grant(grant, now.date()) if grant is not None else inv["grant"]
            over = within(g, inv["grant"])
            if over: raise NetworkError("You can share less than was requested, never more. " + over)
            days = inv["connection_days"] if connection_days is None else _days(connection_days, "Connection length", 1, inv["connection_days"])
            viewer_prof, provider_prof = self.profile(inv["org_id"]), me
        if provider_prof is None or viewer_prof is None:
            raise NetworkStateError("The other organisation has no network profile any more.")
        if any(c["viewer_org"] == viewer and self._eff(c) == "ACTIVE" for c in self._conns_of(provider)):
            raise NetworkStateError("These two organisations are already connected. End the existing connection first if you want to replace it.")
        for o in (provider, viewer):
            if sum(1 for c in self.list_connections(o) if c["status"] == "ACTIVE") >= MAX_ACTIVE_CONNECTIONS:
                raise NetworkStateError(f"An organisation can have at most {MAX_ACTIVE_CONNECTIONS} active connections.")
        conn = {"id": str(uuid.uuid4()), "provider_org": provider, "viewer_org": viewer, "provider_name": provider_prof["display_name"], "viewer_name": viewer_prof["display_name"],
                "viewer_type": viewer_prof["org_type"], "purpose": inv["purpose"], "grant": g, "status": "ACTIVE", "created_at": now.isoformat(), "expires_at": (now + timedelta(days=days)).isoformat(),
                "initiated_by_org": inv["org_id"], "accepted_by": actor, "invite_id": inv["id"], "history": [{"at": now.isoformat(), "by": actor, "org": org, "event": "CONNECTED"}],
                "views": 0, "last_viewed_at": None}
        self.store.put("net_conn", f"{provider}:{conn['id']}", conn, org_id=provider)
        self.store.put("net_link", f"{viewer}:{conn['id']}", {"provider_org": provider, "id": conn["id"]}, org_id=viewer)
        inv["status"] = "ACCEPTED"; inv["connection_id"] = conn["id"]; inv["accepted_by"] = actor
        self.store.put("net_invite", inv["id"], inv, org_id=inv["org_id"])
        self.store.put("net_attempts", actor, {"fails": []}, org_id=None)
        scopes = ", ".join(g["scopes"])
        self.log("NETWORK_CONNECTED", actor, conn["id"], provider, f"{viewer_prof['display_name']} ({viewer_prof['org_type']}) may see: {scopes}")
        self.log("NETWORK_CONNECTED", actor, conn["id"], viewer, f"Connected to {provider_prof['display_name']}; may see: {scopes}")
        return self.public(conn, org)

    # ------------------------------------------------------------------ connections
    def _conns_of(self, provider_org: str) -> List[dict]:
        return [c for _, c in self.store.list("net_conn", org_id=provider_org)]

    def _eff(self, c: dict) -> str:
        return "EXPIRED" if c["status"] == "ACTIVE" and self.now() >= _aware(c["expires_at"]) else c["status"]

    def public(self, c: dict, org: str) -> dict:
        """A connection as one of its two sides sees it. The provider sees who may view; the viewer sees whose information it is and exactly what it was given."""
        mine = "PROVIDER" if c["provider_org"] == org else "VIEWER"
        out = {"id": c["id"], "role": mine, "status": self._eff(c), "purpose": c["purpose"], "grant": c["grant"], "created_at": c["created_at"], "expires_at": c["expires_at"],
               "counterparty": {"name": c["viewer_name"] if mine == "PROVIDER" else c["provider_name"], "type": c["viewer_type"] if mine == "PROVIDER" else "BUSINESS"},
               "history": c["history"]}
        if mine == "PROVIDER":
            out.update(views=c["views"], last_viewed_at=c["last_viewed_at"])
        return out

    def list_connections(self, org: str) -> List[dict]:
        rows = [self.public(c, org) for c in self._conns_of(org)]
        for _, link in self.store.list("net_link", org_id=org):
            c = self.store.get("net_conn", f"{link['provider_org']}:{link['id']}")
            if c: rows.append(self.public(c, org))
        return sorted(rows, key=lambda r: r["created_at"], reverse=True)

    def _conn_for(self, org: str, conn_id: str, for_update=False) -> dict:
        c = self.store.get("net_conn", f"{org}:{conn_id}", for_update=for_update)
        if c is None:
            link = self.store.get("net_link", f"{org}:{conn_id}")
            c = self.store.get("net_conn", f"{link['provider_org']}:{link['id']}", for_update=for_update) if link else None
        if c is None:
            raise NetworkNotFoundError("Connection not found.")
        return c

    def _save(self, c: dict): self.store.put("net_conn", f"{c['provider_org']}:{c['id']}", c, org_id=c["provider_org"])

    def update_grant(self, org: str, actor: str, conn_id: str, grant: Optional[dict] = None, extend_days: Optional[int] = None) -> dict:
        """Only the business (provider) can change what a connection may see or how long it lasts. Every change is recorded on both sides."""
        c = self._conn_for(org, conn_id, True)
        if c["provider_org"] != org:
            raise NetworkForbiddenError("Only the business whose information it is can change what this connection may see.")
        if self._eff(c) != "ACTIVE":
            raise NetworkStateError("This connection is no longer active.")
        now = self.now(); changed = []
        if grant is not None:
            g = clean_grant({**c["grant"], **grant}, now.date())
            if g != c["grant"]:
                changed.append("what it may see"); c["grant"] = g
        if extend_days is not None:
            c["expires_at"] = (now + timedelta(days=_days(extend_days, "Connection length", 1, 365))).isoformat(); changed.append("how long it lasts")
        if not changed:
            return self.public(c, org)
        c["history"].append({"at": now.isoformat(), "by": actor, "org": org, "event": "CHANGED", "what": ", ".join(changed)})
        self._save(c)
        for o in (c["provider_org"], c["viewer_org"]):
            self.log("NETWORK_GRANT_CHANGED", actor, c["id"], o, f"Changed {', '.join(changed)}: " + ", ".join(c["grant"]["scopes"]))
        return self.public(c, org)

    def revoke(self, org: str, actor: str, conn_id: str, reason: str) -> dict:
        c = self._conn_for(org, conn_id, True)
        if org not in (c["provider_org"], c["viewer_org"]):
            raise NetworkNotFoundError("Connection not found.")
        if c["status"] != "ACTIVE":
            raise NetworkStateError("This connection has already ended.")
        now = self.now(); why = _txt(reason, "Reason", 3, 300)
        c["status"] = "REVOKED"; c["history"].append({"at": now.isoformat(), "by": actor, "org": org, "event": "ENDED", "reason": why})
        self._save(c)
        who = "the business" if org == c["provider_org"] else "the other organisation"
        for o in (c["provider_org"], c["viewer_org"]):
            self.log("NETWORK_DISCONNECTED", actor, c["id"], o, f"Ended by {who}: {why}")
        return self.public(c, org)

    # ------------------------------------------------------------------ viewing
    def authorize_view(self, viewer_org: str, actor: str, conn_id: str) -> tuple:
        """Returns (connection, passport-builder request). Refuses with one generic message, whatever the reason."""
        deny = NetworkForbiddenError("This connection is not active, so its information cannot be opened.")
        link = self.store.get("net_link", f"{viewer_org}:{conn_id}")
        c = self.store.get("net_conn", f"{link['provider_org']}:{link['id']}") if link else None
        if c is None or c["viewer_org"] != viewer_org or self._eff(c) != "ACTIVE":
            raise deny
        return c, grant_to_request(c["grant"])

    def record_view(self, c: dict, actor: str, fingerprint: str) -> None:
        cur = self._conn_for(c["provider_org"], c["id"], True)
        now = self.now()
        cur["views"] += 1; cur["last_viewed_at"] = now.isoformat(); self._save(cur)
        self.store.put("net_access", f"{cur['provider_org']}:{cur['id']}:{uuid.uuid4()}", {"conn_id": cur["id"], "at": now.isoformat(), "viewer_org": cur["viewer_org"], "viewer_name": cur["viewer_name"],
                                                                                           "user_id": actor, "fingerprint": fingerprint}, org_id=cur["provider_org"])
        for o in (cur["provider_org"], cur["viewer_org"]):
            self.log("NETWORK_PASSPORT_VIEWED", actor, cur["id"], o, f"{cur['viewer_name']} viewed {cur['provider_name']}'s Passport ({fingerprint[:12]})")

    def access_log(self, provider_org: str, conn_id: str) -> List[dict]:
        c = self.store.get("net_conn", f"{provider_org}:{conn_id}")
        if c is None:
            raise NetworkNotFoundError("Connection not found.")
        rows = [d for _, d in self.store.list("net_access", org_id=provider_org, prefix=f"{provider_org}:{conn_id}:")]
        return sorted(rows, key=lambda r: r["at"], reverse=True)

    # ------------------------------------------------------------------ overview
    def overview(self, org: str) -> dict:
        prof = self.profile(org); conns = self.list_connections(org)
        active = [c for c in conns if c["status"] == "ACTIVE"]
        by: Dict[str, int] = {}
        for c in active: by[c["counterparty"]["type"]] = by.get(c["counterparty"]["type"], 0) + 1
        return {"profile": prof, "active": len(active), "by_type": by, "pending_invites": sum(1 for i in self.list_invites(org) if i["status"] == "PENDING"),
                "can_offer_to": list(VIEWER_TYPES) if prof and prof["org_type"] == "BUSINESS" else (["BUSINESS"] if prof else []),
                "connections": conns, "types": {t: TYPE_TEXT[t] for t in TYPES}, "scopes": list(SCOPES)}
