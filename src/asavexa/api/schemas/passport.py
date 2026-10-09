from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from ...passport.builder import OWNER_KINDS, RELATIONSHIPS


def _strip_name(v):
    return v.strip() if isinstance(v, str) else v


def _clean(v):
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


class OwnerIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    kind: str = "INDIVIDUAL"
    ownership_percent: Optional[Decimal] = Field(None, ge=0, le=100)
    notes: Optional[str] = Field(None, max_length=500)

    @field_validator("name", mode="before")
    @classmethod
    def _strip_n(cls, v):
        return _strip_name(v)

    @field_validator("notes", mode="before")
    @classmethod
    def _strip(cls, v):
        return _clean(v)

    @field_validator("kind")
    @classmethod
    def _kind(cls, v):
        v = (v or "").upper()
        if v not in OWNER_KINDS:
            raise ValueError("kind must be one of " + ", ".join(OWNER_KINDS))
        return v


class SubsidiaryIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    relationship: str = "SUBSIDIARY"
    jurisdiction: Optional[str] = Field(None, max_length=100)
    registration_number: Optional[str] = Field(None, max_length=100)
    ownership_percent: Optional[Decimal] = Field(None, ge=0, le=100)

    @field_validator("name", mode="before")
    @classmethod
    def _strip_n(cls, v):
        return _strip_name(v)

    @field_validator("jurisdiction", "registration_number", mode="before")
    @classmethod
    def _strip(cls, v):
        return _clean(v)

    @field_validator("relationship")
    @classmethod
    def _rel(cls, v):
        v = (v or "").upper()
        if v not in RELATIONSHIPS:
            raise ValueError("relationship must be one of " + ", ".join(RELATIONSHIPS))
        return v


class StructureIn(BaseModel):
    owners: List[OwnerIn] = Field(default_factory=list, max_length=50)
    subsidiaries: List[SubsidiaryIn] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def _owners_total(self):
        total = sum((o.ownership_percent for o in self.owners if o.ownership_percent is not None), Decimal("0"))
        if total > 100:
            raise ValueError(f"Owners' percentages add up to {total}%, which is more than 100%.")
        return self


def structure_to_data(body: StructureIn) -> dict:
    """JSON-safe dict (Decimals as strings) for the JSONB column."""
    def conv(m):
        d = m.model_dump()
        if d.get("ownership_percent") is not None:
            d["ownership_percent"] = format(d["ownership_percent"].normalize(), "f")
        return {k: v for k, v in d.items() if v is not None}
    return {"owners": [conv(o) for o in body.owners], "subsidiaries": [conv(s) for s in body.subsidiaries]}
