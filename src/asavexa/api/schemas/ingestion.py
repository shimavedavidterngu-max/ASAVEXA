import json
from typing import Dict, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator

from ...ingestion.errors import IngestionError


class IngestOptions(BaseModel):
    """Everything a person may adjust after a preview. Unknown keys are refused rather than ignored."""
    model_config = {"extra": "forbid"}

    header_row: Optional[int] = Field(None, ge=0, le=100)
    mapping: Optional[Dict[str, Union[str, int, None]]] = None
    date_format: Optional[str] = Field(None, max_length=20)
    flip: bool = False
    sheet: Optional[str] = Field(None, max_length=100)
    delimiter: Optional[Literal[",", ";", "\t", "|"]] = None
    doc_type: Optional[Literal["INVOICE", "RECEIPT"]] = None
    provider: Optional[Literal["PAYSTACK", "FLUTTERWAVE", "STRIPE", "PLAID", "OPEN_BANKING_UK"]] = None
    currency: Optional[str] = Field(None, min_length=3, max_length=3)

    @field_validator("currency")
    @classmethod
    def _upper(cls, v):
        return v.upper() if v else v


def parse_options(raw: Optional[str]) -> IngestOptions:
    """The options arrive as a JSON string inside a multipart form; a bad one is a clear 400, not a crash."""
    if raw is None or not raw.strip():
        return IngestOptions()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise IngestionError("The options are not valid JSON.")
    if not isinstance(data, dict):
        raise IngestionError("The options must be a JSON object.")
    try:
        return IngestOptions(**data)
    except Exception as e:  # pydantic.ValidationError -> plain message
        msgs = getattr(e, "errors", lambda: [])()
        raise IngestionError("Invalid options: " + "; ".join(f"{'.'.join(str(x) for x in m['loc'])}: {m['msg']}" for m in msgs) if msgs else "Invalid options.")
