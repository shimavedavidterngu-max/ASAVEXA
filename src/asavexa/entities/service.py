"""Organisation type, subtype and enabled workspaces (Stage 15), kept per organisation in the shared document store.

What this decides and what it does not:
  * It decides which workspaces appear in the menu and which are suggested. It stores no permission and changes none: a person still needs the
    permission for every action, checked on the server. Hiding a workspace is a convenience, not a security control.
  * An organisation that has never been configured shows every workspace, exactly as before.
  * Every change is audited, keeps the old value in a history, and needs a reason once the organisation has been configured.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from ..security.errors import SecurityError
from . import catalog as C

KIND = "ent_config"
MAX_LANGUAGES = 5
_LANG = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$")
_TZ = re.compile(r"^[A-Za-z][A-Za-z_]*(/[A-Za-z0-9_+\-]+){0,2}$")


class EntityConfigError(SecurityError): status = 400
class EntityConfigConflictError(EntityConfigError): status = 409


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _text(v, label, limit, required=False) -> Optional[str]:
    s = "" if v is None else str(v)
    s = re.sub(r"[\x00-\x1f\x7f]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if required and not s:
        raise EntityConfigError(f"{label} is required.")
    if len(s) > limit:
        raise EntityConfigError(f"{label} must be at most {limit} characters.")
    return s or None


class EntityConfigService:
    def __init__(self, store, workspace_ids: Callable[[], List[str]], log: Callable[..., None] = lambda *a, **k: None, now: Callable[[], datetime] = _now):
        self.store, self.workspace_ids, self.log, self.now = store, workspace_ids, log, now

    # ------------------------------------------------------------------ read
    @staticmethod
    def entity_catalog() -> dict:
        return {"types": C.ENTITY_TYPES, "note": C.NOTE}

    def _doc(self, org, for_update=False) -> Optional[dict]:
        d = self.store.get(KIND, f"{org}:config", for_update=for_update)
        return d if d is not None and d.get("org") == org else None

    def _suggested(self, entity_type) -> List[str]:
        known = set(self.workspace_ids())
        t = C.BY_CODE.get(entity_type)
        ids = set(t["suggested_workspaces"] if t else C.CORE)
        return [w for w in self.workspace_ids() if w in ids and w in known]       # always in catalogue order

    def get_entity_config(self, org) -> dict:
        d = self._doc(org)
        known = list(self.workspace_ids())
        if d is None:
            return {"configured": False, "entity_type": None, "subtype": None, "custom_subtype": None, "languages": [], "timezone": None,
                    "enabled_workspaces": None, "shown_workspaces": known, "suggested_workspaces": [], "version": 0, "history": [], "updated_by": None, "updated_at": None,
                    "note": "This organisation has not described itself yet, so every workspace is shown."}
        enabled = [w for w in d["enabled_workspaces"] if w in known]      # a workspace removed from the product simply drops out
        return {"configured": True, "entity_type": d["entity_type"], "subtype": d["subtype"], "custom_subtype": d["custom_subtype"], "languages": d["languages"],
                "timezone": d["timezone"], "enabled_workspaces": enabled, "shown_workspaces": enabled, "suggested_workspaces": self._suggested(d["entity_type"]),
                "version": d["version"], "history": d["history"][-20:], "updated_by": d["updated_by"], "updated_at": d["updated_at"],
                "note": "Hiding a workspace only removes it from the menu. It does not remove anyone's access or any data."}

    def workspace_enabled(self, org, workspace_id) -> bool:
        return workspace_id in self.get_entity_config(org)["shown_workspaces"]

    # ------------------------------------------------------------------ change
    def save_entity_config(self, org, actor, entity_type, subtype=None, custom_subtype=None, enabled_workspaces=None, languages=None, timezone_name=None, note="") -> dict:
        t = C.BY_CODE.get(entity_type)
        if t is None:
            raise EntityConfigError("Choose the kind of organisation from the list.")
        subtype = (subtype or None)
        if subtype is not None and subtype not in {s["code"] for s in t["subtypes"]}:
            raise EntityConfigError("That subtype does not belong to the chosen kind of organisation.")
        custom = _text(custom_subtype, "Your own description", 80)
        known = self.workspace_ids()
        if enabled_workspaces is None:
            enabled = self._suggested(entity_type)
        else:
            if not isinstance(enabled_workspaces, list) or any(not isinstance(w, str) for w in enabled_workspaces):
                raise EntityConfigError("Workspaces must be a list of workspace ids.")
            bad = [w for w in enabled_workspaces if w not in known]
            if bad:
                raise EntityConfigError(f"Unknown workspace: {bad[0]}.")
            enabled = [w for w in known if w in set(enabled_workspaces)]        # catalogue order, no duplicates
        langs = []
        for x in (languages or []):
            if not isinstance(x, str) or not _LANG.match(x.strip()):
                raise EntityConfigError("A language must be a code such as en or fr-CA.")
            if x.strip() not in langs:
                langs.append(x.strip())
        if len(langs) > MAX_LANGUAGES:
            raise EntityConfigError(f"Choose at most {MAX_LANGUAGES} languages.")
        tz = _text(timezone_name, "Time zone", 60)
        if tz is not None and not _TZ.match(tz):
            raise EntityConfigError("A time zone looks like Africa/Lagos or Europe/London.")
        new = {"entity_type": entity_type, "subtype": subtype, "custom_subtype": custom, "enabled_workspaces": enabled, "languages": langs, "timezone": tz}
        d = self._doc(org, for_update=True)
        note = _text(note, "Reason", 500)
        if d is None:
            d = {"id": "config", "org": org, "version": 0, "history": [], **{k: None for k in new}}
            event, changes = "CONFIGURED", {}
        else:
            changes = {k: [d[k], v] for k, v in new.items() if d[k] != v}
            if not changes:
                raise EntityConfigConflictError("Nothing has changed.")
            if not note:
                raise EntityConfigError("Say why you are changing how this organisation is set up.")
            event = "CHANGED"
        d.update(new)
        d["version"] += 1
        d["updated_by"], d["updated_at"] = actor, self.now().isoformat()
        d["history"].append({"at": d["updated_at"], "by": actor, "event": event, "note": note or "", "version": d["version"], "changes": changes})
        self.store.put(KIND, f"{org}:config", d, org_id=org)
        self.log("ENTITY_CONFIG_SAVED", actor, f"{org}:config", org, f"{event} {entity_type}")
        return self.get_entity_config(org)
