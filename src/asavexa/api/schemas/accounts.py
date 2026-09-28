from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from ...accounting.domain.enums import AccountType


class AccountCreate(BaseModel):
    code: str = Field(..., examples=["1000"])
    name: str = Field(..., examples=["Cash"])
    type: AccountType
    currency: str = "USD"
    parent_id: Optional[str] = None


class AccountOut(BaseModel):
    id: str
    org_id: str
    code: str
    name: str
    type: AccountType
    currency: str
    parent_id: Optional[str]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
