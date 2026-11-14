from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.maps.catalog import Layer


class LayerList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[Layer]


class MapErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    reason: str = Field(min_length=1)


class MapAPIError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern="^[A-Z][A-Z0-9_]*$")
    message: str = Field(min_length=1)
    details: list[MapErrorDetail]
    request_id: UUID


class MapErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: MapAPIError
