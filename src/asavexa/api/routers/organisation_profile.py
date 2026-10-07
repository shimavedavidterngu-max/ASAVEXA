import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from ...audit.models import AuditEvent
from ...identity.domain.permissions import ORG_MANAGE_SETTINGS
from ..db.audit_sqlalchemy_repository import SqlAlchemyAuditRepository
from ..db.base import get_session
from ..db.profile_models import OrganisationProfileORM
from ..deps import get_current_actor, get_current_org, require_permission
from ..schemas.organisation_profile import OrganisationProfileIn, OrganisationProfileOut

router = APIRouter(prefix="/organisation-profile", tags=["Organisation Profile"])


def _to_out(org_id: str, row) -> OrganisationProfileOut:
    if row is None:
        return OrganisationProfileOut(org_id=org_id)
    return OrganisationProfileOut(
        org_id=org_id, updated_at=row.updated_at, updated_by=row.updated_by, **(row.data or {})
    )


@router.get("", response_model=OrganisationProfileOut)
def get_profile(org_id: str = Depends(get_current_org), session=Depends(get_session)):
    """The current organisation's profile (empty fields until saved).
    Any member of the organisation may read it."""
    return _to_out(org_id, session.get(OrganisationProfileORM, org_id))


@router.put(
    "", response_model=OrganisationProfileOut,
    dependencies=[Depends(require_permission(ORG_MANAGE_SETTINGS))],
)
def update_profile(
    body: OrganisationProfileIn,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    session=Depends(get_session),
):
    """Replaces the organisation's profile with the submitted fields and
    records the before/after in the shared audit trail."""
    new_data = body.model_dump(exclude_none=True)
    now = datetime.now(timezone.utc)
    row = session.get(OrganisationProfileORM, org_id)
    previous = dict(row.data or {}) if row is not None else None
    if row is None:
        row = OrganisationProfileORM(org_id=org_id, data=new_data, updated_at=now, updated_by=actor)
        session.add(row)
    else:
        row.data = new_data
        row.updated_at = now
        row.updated_by = actor
    SqlAlchemyAuditRepository(session).record(
        AuditEvent(
            id=str(uuid.uuid4()), org_id=org_id, entity_type="Organisation", entity_id=org_id,
            action="ORGANISATION_PROFILE_UPDATED", actor=actor, timestamp=now,
            previous_value=previous, new_value=new_data,
        )
    )
    return _to_out(org_id, row)
