"""Professional workspace selector: what exists, what does not, and the honest status of each."""
from fastapi import APIRouter, Depends

from ...workspaces import catalog
from ..deps import get_current_org

router = APIRouter(prefix="/workspaces", tags=["Professional Workspaces"])


@router.get("")
def list_workspaces(org_id: str = Depends(get_current_org)):
    return catalog()
