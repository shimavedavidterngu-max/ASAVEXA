from typing import Literal, Optional

from pydantic import BaseModel, Field


class AiExplainIn(BaseModel):
    subject_type: Literal["journal", "bank_transaction"]
    subject_id: str = Field(..., min_length=1, max_length=100)


class AiDetectIn(BaseModel):
    period_id: Optional[str] = Field(None, max_length=100)
    limit: int = Field(20, ge=1, le=50)


class AiRecommendIn(BaseModel):
    scope: Literal["all", "reconciliation", "adjustment", "evidence"] = "all"
    period_id: Optional[str] = Field(None, max_length=100)
    limit: int = Field(15, ge=1, le=50)


class AiProveIn(BaseModel):
    subject_type: Literal["journal", "bank_transaction", "figure"]
    subject_id: Optional[str] = Field(None, max_length=100)
    metric: Optional[Literal["revenue", "expenses", "net_income", "assets", "liabilities"]] = None
    period_id: Optional[str] = Field(None, max_length=100)


class AiAskIn(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
