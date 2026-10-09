import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select

from ...audit.models import AuditEvent
from ...identity.domain.permissions import ORG_MANAGE_SETTINGS, PASSPORT_MANAGE
from ...passport.builder import PassportInputs, build_passport
from ...passport.sharing import ShareService
from ...standards import engine as standards_engine
from ...standards.errors import AsavexaStandardsError
from ..db.audit_sqlalchemy_repository import SqlAlchemyAuditRepository
from ..db.base import get_session
from ..db.compliance_sqlalchemy_repository import (
    SqlAlchemyControlDefinitionRepository,
    SqlAlchemyControlExecutionRepository,
    SqlAlchemyFindingRepository,
)
from ..db.evidence_sqlalchemy_repository import SqlAlchemyEvidenceRepository
from ..db.identity_sqlalchemy_repository import (
    SqlAlchemyMembershipRepository,
    SqlAlchemyOrganisationRepository,
)
from ..db.identity_models import UserORM
from ..db.passport_models import OrganisationStructureORM
from ..db.passport_share_store import SqlAlchemyShareStore
from ..db.period_close_sqlalchemy_repository import SqlAlchemyPeriodCloseRepository
from ..db.profile_models import OrganisationProfileORM
from ..db.reconciliation_sqlalchemy_repository import (
    SqlAlchemyBankTransactionRepository,
    SqlAlchemyReconciliationRepository,
)
from ..db.sqlalchemy_repository import (
    SqlAlchemyAccountRepository,
    SqlAlchemyJournalRepository,
    SqlAlchemyPeriodRepository,
)
from ..db.standards_models import OrganisationStandardsORM
from ..deps import get_current_actor, get_current_org, require_permission
from ..schemas.passport import ShareCreateIn, ShareRevokeIn, StructureIn, structure_to_data

router = APIRouter(prefix="/passport", tags=["VERA Financial Passport"])

AUDIT_WINDOW = 5000


def _resolved_standards(session, org_id: str) -> dict:
    row = session.get(OrganisationStandardsORM, org_id)
    if row is None:
        return {"configured": False}
    d = row.data or {}
    try:
        resolved = standards_engine.resolve_configuration(
            d["jurisdiction"], d["entity_type"], d.get("framework"), d.get("policy_overrides") or {}
        )
    except (AsavexaStandardsError, KeyError):
        try:
            resolved = standards_engine.resolve_configuration(d["jurisdiction"], d["entity_type"], d.get("framework"), {})
        except (AsavexaStandardsError, KeyError):
            return {"configured": False}
    resolved["configured"] = True
    return resolved


def user_labels(session, ids) -> dict:
    """{user id: email} for the ids that are real users. Only well-formed UUIDs go
    to the database: a stray non-UUID actor string would otherwise raise a
    DataError and poison the whole request."""
    valid = []
    for x in sorted(i for i in ids if i):
        try:
            valid.append(str(uuid.UUID(str(x))))
        except ValueError:
            continue
    out = {}
    if valid:
        for uid, email in session.execute(select(UserORM.id, UserORM.email).where(UserORM.id.in_(valid[:300]))):
            out[str(uid)] = email
    return out


def gather_inputs(session, org_id: str) -> PassportInputs:
    """Reads (never writes) everything the Passport needs for one organisation."""
    org = SqlAlchemyOrganisationRepository(session).get(org_id)
    profile_row = session.get(OrganisationProfileORM, org_id)
    structure_row = session.get(OrganisationStructureORM, org_id)
    structure = None
    if structure_row is not None:
        structure = {**(structure_row.data or {}), "updated_at": structure_row.updated_at,
                     "updated_by": structure_row.updated_by}

    recon_repo = SqlAlchemyReconciliationRepository(session)
    tx_repo = SqlAlchemyBankTransactionRepository(session)
    reconciliations = recon_repo.list_for_org(org_id)
    transactions = []
    for r in reconciliations:
        transactions.extend(tx_repo.list_for_reconciliation(org_id, r.id))

    periods = SqlAlchemyPeriodRepository(session).list_for_org(org_id)
    close_repo = SqlAlchemyPeriodCloseRepository(session)
    close_processes = []
    for p in periods:
        close_processes.extend(close_repo.list_for_period(org_id, p.id))

    audit_events, audit_total = SqlAlchemyAuditRepository(session).list_recent_for_org(
        org_id, AUDIT_WINDOW, exclude_action_prefix=("PASSPORT_", "AI_")
    )
    memberships = SqlAlchemyMembershipRepository(session).list_for_org(org_id)

    inp = PassportInputs(
        org_id=org_id, org_name=org.name if org else "",
        profile=dict(profile_row.data or {}) if profile_row is not None else {},
        structure=structure, standards=_resolved_standards(session, org_id),
        periods=periods,
        accounts=SqlAlchemyAccountRepository(session).list_for_org(org_id),
        journals=SqlAlchemyJournalRepository(session).list_for_org(org_id),
        evidence=SqlAlchemyEvidenceRepository(session).list_for_org(org_id),
        reconciliations=reconciliations, bank_transactions=transactions,
        controls=SqlAlchemyControlDefinitionRepository(session).list_for_org(org_id),
        executions=SqlAlchemyControlExecutionRepository(session).list_for_org(org_id),
        findings=SqlAlchemyFindingRepository(session).list_for_org(org_id),
        close_processes=close_processes, memberships=memberships,
        audit_events=audit_events, audit_total=audit_total,
    )

    # Readable names for the people who appear anywhere in the data.
    ids = set()
    for m in memberships:
        ids.add(m.user_id)
    for e in audit_events:
        ids.add(e.actor)
    for j in inp.journals:
        ids.update(x for x in (j.created_by, j.posted_by) if x)
    for p in periods:
        if p.locked_by:
            ids.add(p.locked_by)
    for e in inp.evidence:
        ids.update(x for x in (e.uploaded_by, e.verified_by) if x)
    for r in reconciliations:
        ids.update(x for x in (r.created_by, r.submitted_by, r.approved_by) if x)
    for c in close_processes:
        ids.update(x for x in (c.requested_by, c.approved_by) if x)
    for x in inp.executions:
        ids.update(y for y in (x.executed_by, x.reviewed_by) if y)
    if structure and structure.get("updated_by"):
        ids.add(structure["updated_by"])
    inp.user_labels.update(user_labels(session, ids))
    return inp


@router.get("", dependencies=[Depends(require_permission(PASSPORT_MANAGE))])
def get_passport(
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    session=Depends(get_session),
):
    """The VERA Financial Passport for the current organisation: identity,
    financial history, evidence quality, governance, reporting and audit
    trail, built fresh from the live records. Generating one is itself
    audited (PASSPORT_GENERATED, with the fingerprint)."""
    inp = gather_inputs(session, org_id)
    now = datetime.now(timezone.utc)
    passport = build_passport(inp, inp.user_labels.get(actor, actor), now)
    SqlAlchemyAuditRepository(session).record(AuditEvent(
        id=str(uuid.uuid4()), org_id=org_id, entity_type="Passport", entity_id=org_id,
        action="PASSPORT_GENERATED", actor=actor, timestamp=now,
        new_value={"fingerprint": passport["fingerprint"], "schema_version": passport["schema_version"]},
    ))
    return passport


@router.put("/structure", dependencies=[Depends(require_permission(ORG_MANAGE_SETTINGS))])
def save_structure(
    body: StructureIn,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    session=Depends(get_session),
):
    """Replaces the organisation's recorded owners and subsidiaries and
    audits the before/after."""
    data = structure_to_data(body)
    now = datetime.now(timezone.utc)
    row = session.get(OrganisationStructureORM, org_id)
    previous = dict(row.data or {}) if row is not None else None
    if row is None:
        session.add(OrganisationStructureORM(org_id=org_id, data=data, updated_at=now, updated_by=actor))
    else:
        row.data, row.updated_at, row.updated_by = data, now, actor
    SqlAlchemyAuditRepository(session).record(AuditEvent(
        id=str(uuid.uuid4()), org_id=org_id, entity_type="Organisation", entity_id=org_id,
        action="ORGANISATION_STRUCTURE_UPDATED", actor=actor, timestamp=now,
        previous_value=previous, new_value=data,
    ))
    return {**data, "updated_at": now, "updated_by": actor}


# ----------------------------------------------------------------------
# Permissioned sharing (organisation side). Recipients use the separate,
# unauthenticated /shared-passport router.
# ----------------------------------------------------------------------
def _share_service(session) -> ShareService:
    return ShareService(SqlAlchemyShareStore(session), SqlAlchemyAuditRepository(session))


def _share_labels(session, shares) -> dict:
    ids = set()
    for s in shares:
        ids.update(x for x in (s.get("created_by"), s.get("revoked_by")) if x)
    return user_labels(session, ids)


@router.post("/shares", status_code=201, dependencies=[Depends(require_permission(ORG_MANAGE_SETTINGS))])
def create_share(
    body: ShareCreateIn,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    session=Depends(get_session),
):
    """Freezes a snapshot of the chosen Passport sections for the chosen dates and
    returns the link and access code ONCE. Disclosing financial data outside the
    organisation needs org:manage_settings (owner or administrator)."""
    inp = gather_inputs(session, org_id)
    result = _share_service(session).create_share(inp, body.model_dump(), actor, datetime.now(timezone.utc))
    result["share"]["created_by"] = inp.user_labels.get(actor, actor)
    return result


@router.get("/shares", dependencies=[Depends(require_permission(PASSPORT_MANAGE))])
def list_shares(org_id: str = Depends(get_current_org), session=Depends(get_session)):
    svc = _share_service(session)
    shares = svc.list_shares(org_id, datetime.now(timezone.utc))
    labels = _share_labels(session, shares)
    for s in shares:
        s["created_by"] = labels.get(s["created_by"], s["created_by"])
        if s["revoked_by"]:
            s["revoked_by"] = labels.get(s["revoked_by"], s["revoked_by"])
    return shares


@router.get("/shares/{share_id}", dependencies=[Depends(require_permission(PASSPORT_MANAGE))])
def get_share(share_id: str, org_id: str = Depends(get_current_org), session=Depends(get_session)):
    s = _share_service(session).get_share(org_id, share_id, datetime.now(timezone.utc))
    labels = _share_labels(session, [s])
    s["created_by"] = labels.get(s["created_by"], s["created_by"])
    if s["revoked_by"]:
        s["revoked_by"] = labels.get(s["revoked_by"], s["revoked_by"])
    return s


@router.get("/shares/{share_id}/access-log", dependencies=[Depends(require_permission(PASSPORT_MANAGE))])
def share_access_log(share_id: str, org_id: str = Depends(get_current_org), session=Depends(get_session)):
    """Everything that happened to this share: created, every verification
    attempt, views, downloads, lock and revocation."""
    svc = _share_service(session)
    raw = svc.access_log(org_id, share_id)
    labels = user_labels(session, {e["who"] for e in raw})
    return [{**e, "who": labels.get(e["who"], e["who"])} for e in raw]


@router.post("/shares/{share_id}/revoke", dependencies=[Depends(require_permission(ORG_MANAGE_SETTINGS))])
def revoke_share(
    share_id: str, body: ShareRevokeIn,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    session=Depends(get_session),
):
    """Ends the share at once, including for a recipient who is already signed in."""
    s = _share_service(session).revoke_share(org_id, share_id, actor, body.reason, datetime.now(timezone.utc))
    labels = user_labels(session, [actor])
    s["revoked_by"] = labels.get(actor, actor)
    return s
