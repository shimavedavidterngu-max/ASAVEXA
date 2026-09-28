from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel

from ...accounting.domain.enums import PeriodStatus


class PeriodCreate(BaseModel):
    name: str
    start_date: date
    end_date: date


class PeriodLockRequest(BaseModel):
    reason: str


class PeriodOut(BaseModel):
    id: str
    org_id: str
    name: str
    start_date: date
    end_date: date
    status: PeriodStatus
    locked_at: Optional[datetime]
    locked_by: Optional[str]

    model_config = {"from_attributes": True}
