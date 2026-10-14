"""Organisation type, subtype and enabled workspaces (Stage 15). Any member can read; changing needs org:manage_settings.
The organisation always comes from the signed-in session. Nothing here grants or removes a permission."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...entities.service import EntityConfigError, EntityConfigService
from ...identity.domain.permissions import ORG_MANAGE_SETTINGS
from ..deps import get_current_actor, get_current_org, get_entity_config, require_permission

router = APIRouter(prefix="/entity-config", tags=["Organisation type and workspaces"])


class EntityConfigBody(BaseModel):
    entity_type: str
    subtype: Optional[str] = None
    custom_subtype: Optional[str] = None
    enabled_workspaces: Optional[List[str]] = None
    languages: Optional[List[str]] = None
    timezone: Optional[str] = None
    note: str = ""


def _run(fn):
    try:
        return fn()
    except EntityConfigError as exc:
        raise HTTPException(status_code=getattr(exc, "status", 400), detail=str(exc))


@router.get("/catalog")
def catalog(org: str = Depends(get_current_org)):
    return EntityConfigService.entity_catalog()


@router.get("")
def read(org: str = Depends(get_current_org), svc: EntityConfigService = Depends(get_entity_config)):
    return svc.get_entity_config(org)


@router.put("", dependencies=[Depends(require_permission(ORG_MANAGE_SETTINGS))])
def save(body: EntityConfigBody, org: str = Depends(get_current_org), actor: str = Depends(get_current_actor), svc: EntityConfigService = Depends(get_entity_config)):
    return _run(lambda: svc.save_entity_config(org, actor, body.entity_type, body.subtype, body.custom_subtype, body.enabled_workspaces, body.languages, body.timezone, body.note))
