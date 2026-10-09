from typing import Dict, Optional

from pydantic import BaseModel


class ResolveRequest(BaseModel):
    jurisdiction: str
    entity_type: str
    framework: Optional[str] = None
    policy_overrides: Dict[str, str] = {}


class StandardsConfigurationIn(ResolveRequest):
    pass
