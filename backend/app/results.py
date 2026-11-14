from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.astronomy import ObservationPoint


class ResolvedSite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    site_id: str | None
    name: str = Field(min_length=1)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, lt=180)
    surface_elevation_m: Literal[0.0]
    observer_height_m: float = Field(ge=0, le=20)


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    url: str = Field(min_length=1)
    version: str | None = Field(min_length=1)
    fetched_at: AwareDatetime


class Meta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_version: str = Field(min_length=1)
    generated_at: AwareDatetime
    data_status: Literal["fresh", "cached"]
    horizon_mode: Literal["geometric"]
    time_resolution_minutes: None
    terrain_dataset_id: None
    sources: list[Source] = Field(min_length=1)


class NowResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    site: ResolvedSite
    point: ObservationPoint
    meta: Meta
