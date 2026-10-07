import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

# Deliberately framework-neutral: ASAVEXA must not assume one country's
# accounting standard. "OTHER" covers anything not listed.
REPORTING_FRAMEWORKS = (
    "IFRS", "IFRS_FOR_SMES", "US_GAAP", "IPSAS", "LOCAL_GAAP", "NONPROFIT", "CASH_BASIS", "OTHER",
)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class OrganisationProfileIn(BaseModel):
    legal_name: Optional[str] = Field(None, max_length=200)
    trading_name: Optional[str] = Field(None, max_length=200)
    registration_number: Optional[str] = Field(None, max_length=100)
    tax_id: Optional[str] = Field(None, max_length=100)
    industry: Optional[str] = Field(None, max_length=120)
    organisation_type: Optional[str] = Field(None, max_length=60)
    country: Optional[str] = Field(None, max_length=100)
    address: Optional[str] = Field(None, max_length=500)
    contact_email: Optional[str] = Field(None, max_length=200)
    contact_phone: Optional[str] = Field(None, max_length=60)
    website: Optional[str] = Field(None, max_length=200)
    base_currency: Optional[str] = Field(None, max_length=3)
    fiscal_year_start_month: Optional[int] = Field(None, ge=1, le=12)
    reporting_framework: Optional[str] = None

    @field_validator("*", mode="before")
    @classmethod
    def _blank_to_none(cls, v):
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v

    @field_validator("contact_email")
    @classmethod
    def _email(cls, v):
        if v is not None and not _EMAIL_RE.match(v):
            raise ValueError("contact_email must be a valid email address")
        return v

    @field_validator("base_currency")
    @classmethod
    def _currency(cls, v):
        if v is None:
            return v
        v = v.upper()
        if not re.fullmatch(r"[A-Z]{3}", v):
            raise ValueError("base_currency must be a 3-letter currency code such as USD, EUR, NGN")
        return v

    @field_validator("reporting_framework")
    @classmethod
    def _framework(cls, v):
        if v is not None and v not in REPORTING_FRAMEWORKS:
            raise ValueError(f"reporting_framework must be one of {', '.join(REPORTING_FRAMEWORKS)}")
        return v


class OrganisationProfileOut(OrganisationProfileIn):
    org_id: str
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None
