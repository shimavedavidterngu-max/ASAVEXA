import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from ...audit.models import AuditEvent
from ...identity.domain.permissions import ORG_MANAGE_SETTINGS
from ...standards import engine
from ...standards.errors import AsavexaStandardsError
from ..db.audit_sqlalchemy_repository import SqlAlchemyAuditRepository
from ..db.base import get_session
from ..db.profile_models import OrganisationProfileORM
from ..db.standards_models import OrganisationStandardsORM
from ..deps import get_current_actor, get_current_org, require_permission
from ..schemas.standards import ResolveRequest, StandardsConfigurationIn

router = APIRouter(prefix="/standards", tags=["Standards Configuration"])


@router.get("/catalog")
def get_catalog(org_id: str = Depends(get_current_org)):
    """Jurisdictions, entity types and frameworks the engine knows."""
    return engine.list_catalog()


@router.post("/resolve")
def resolve(body: ResolveRequest, org_id: str = Depends(get_current_org)):
    """Stateless preview: what would this choice resolve to? Nothing is saved."""
    return engine.resolve_configuration(
        body.jurisdiction, body.entity_type, body.framework, body.policy_overrides
    )


@router.get("/configuration")
def get_configuration(org_id: str = Depends(get_current_org), session=Depends(get_session)):
    """The organisation's saved configuration, fully resolved, or
    {"configured": false} if none has been saved yet."""
    row = session.get(OrganisationStandardsORM, org_id)
    if row is None:
        return {"configured": False}
    d = row.data
    try:
        resolved = engine.resolve_configuration(
            d["jurisdiction"], d["entity_type"], d.get("framework"), d.get("policy_overrides") or {}
        )
    except AsavexaStandardsError:
        # The catalog changed since this was saved and an old choice is no
        # longer valid: show the framework defaults and say so, never fail.
        resolved = engine.resolve_configuration(d["jurisdiction"], d["entity_type"], d.get("framework"), {})
        resolved["warnings"].insert(0, "A previously saved policy choice is no longer valid and was reset to the default. Review and save again.")
    resolved.update({"configured": True, "updated_at": row.updated_at, "updated_by": row.updated_by})
    return resolved


@router.put("/configuration", dependencies=[Depends(require_permission(ORG_MANAGE_SETTINGS))])
def save_configuration(
    body: StandardsConfigurationIn,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    session=Depends(get_session),
):
    """Validates (invalid choices are rejected with a 400 explaining why),
    saves, mirrors the framework onto the organisation profile, and
    audits the change."""
    resolved = engine.resolve_configuration(
        body.jurisdiction, body.entity_type, body.framework, body.policy_overrides
    )
    data = {
        "jurisdiction": body.jurisdiction, "entity_type": body.entity_type,
        "framework": resolved["framework"], "policy_overrides": body.policy_overrides,
    }
    now = datetime.now(timezone.utc)
    row = session.get(OrganisationStandardsORM, org_id)
    previous = dict(row.data) if row is not None else None
    if row is None:
        session.add(OrganisationStandardsORM(org_id=org_id, data=data, updated_at=now, updated_by=actor))
    else:
        row.data, row.updated_at, row.updated_by = data, now, actor

    # Keep the organisation profile's "reporting framework" in step.
    profile = session.get(OrganisationProfileORM, org_id)
    if profile is None:
        session.add(OrganisationProfileORM(
            org_id=org_id, data={"reporting_framework": resolved["framework"]}, updated_at=now, updated_by=actor,
        ))
    elif (profile.data or {}).get("reporting_framework") != resolved["framework"]:
        profile.data = {**(profile.data or {}), "reporting_framework": resolved["framework"]}
        profile.updated_at, profile.updated_by = now, actor

    SqlAlchemyAuditRepository(session).record(AuditEvent(
        id=str(uuid.uuid4()), org_id=org_id, entity_type="Organisation", entity_id=org_id,
        action="STANDARDS_CONFIGURATION_UPDATED", actor=actor, timestamp=now,
        previous_value=previous, new_value=data,
    ))
    resolved.update({"configured": True, "updated_at": now, "updated_by": actor})
    return resolved
