"""Assurance endpoints (Stage 12): the shared status vocabulary and a read-only summary across modules. Nothing here writes. Viewing needs audit:read."""
from fastapi import APIRouter, Depends

from ...assurance.service import AssuranceService
from ...assurance.vocabulary import vocabulary as _vocabulary
from ...identity.domain.permissions import AUDIT_READ
from ..deps import get_assurance, get_current_org, require_permission

router = APIRouter(prefix="/assurance", tags=["Assurance"], dependencies=[Depends(require_permission(AUDIT_READ))])


@router.get("/vocabulary")
def vocabulary():
    """The six kinds of assurance, the flags, and how each module's own status words map onto them."""
    return _vocabulary()


@router.get("/summary")
def summary(org: str = Depends(get_current_org), svc: AssuranceService = Depends(get_assurance)):
    """How many records of each kind carry each kind of assurance, for the current organisation only."""
    return svc.summary(org)
