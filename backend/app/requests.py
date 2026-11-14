import re
from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.astronomy.observation import MAX_SUPPORTED_TIME, MIN_SUPPORTED_TIME

Category = Literal["artemis", "apollo", "clps", "international"]
Latitude = Annotated[float, Field(strict=True, ge=-90, le=90, allow_inf_nan=False)]
Longitude = Annotated[float, Field(strict=True, ge=-180, lt=360, allow_inf_nan=False)]


def canonical_time(value: str) -> str:
    instant = datetime.fromisoformat(value.upper())
    if instant.tzinfo is None:
        raise ValueError("Time must include a timezone")
    fraction = re.search(r"[.,](\d+)", value)
    digits = fraction.group(1).rstrip("0") if fraction else ""
    whole = instant.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")
    return whole + ("." + digits if digits else "") + "Z"


class CatalogSite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    site_id: str = Field(min_length=1)


class CustomSite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(default="Custom site", min_length=1)
    latitude: Latitude
    longitude: Longitude


class NowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    site: CatalogSite | CustomSite
    target_time: AwareDatetime
    horizon_mode: Literal["geometric", "terrain"]
    observer_height_m: Annotated[float, Field(strict=True, ge=0, le=20, allow_inf_nan=False)] = 2.0
    visibility_margin_deg: Annotated[float, Field(strict=True, ge=0, le=5, allow_inf_nan=False)] = (
        0.0
    )

    @field_validator("site", mode="before")
    @classmethod
    def select_site_form(cls, value):
        if isinstance(value, dict):
            model = CatalogSite if "site_id" in value else CustomSite
            return model.model_validate(value)
        return value

    @field_validator("target_time", mode="before")
    @classmethod
    def require_iso_string(cls, value):
        if not isinstance(value, str) or "T" not in value.upper():
            raise ValueError("target_time must be an ISO 8601 string with a timezone")
        return value

    @field_validator("target_time")
    @classmethod
    def supported_time(cls, value: datetime) -> datetime:
        value = value.astimezone(UTC)
        if not MIN_SUPPORTED_TIME <= value < MAX_SUPPORTED_TIME:
            raise ValueError("target_time must be within [2000-01-01, 2050-01-01) UTC")
        return value
