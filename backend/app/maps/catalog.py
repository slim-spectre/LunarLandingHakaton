import json
from functools import lru_cache
from math import isfinite
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.maps.errors import MapServiceError

ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "contracts" / "catalog" / "map_layers.json"
PROVIDER_HOSTS = {"moon_trek": "trek.nasa.gov", "lroc": "wms.im-ldi.com"}


class Layer(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    provider: Literal["moon_trek", "lroc"]
    service_type: Literal["wmts", "wms"]
    crs_id: str = Field(min_length=1)
    coordinate_units: Literal["degrees", "metres"]
    extent: list[float] = Field(min_length=4, max_length=4)
    attribution: str = Field(min_length=1)
    source_url: str = Field(min_length=1, json_schema_extra={"format": "uri"})
    tile_matrix_set: str | None
    access_url_template: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_metadata(self):
        if (self.service_type == "wmts") != bool(self.tile_matrix_set):
            raise ValueError("WMTS layers require a tile matrix set; WMS layers require null")
        if not all(isfinite(value) for value in self.extent):
            raise ValueError("Layer extent must contain finite coordinates")
        min_x, min_y, max_x, max_y = self.extent
        if min_x >= max_x or min_y >= max_y:
            raise ValueError("Layer extent must have positive width and height")
        parsed = urlsplit(self.source_url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != PROVIDER_HOSTS[self.provider]
            or parsed.username
            or parsed.password
        ):
            raise ValueError("Layer source URL is outside its verified HTTPS provider")
        return self


@lru_cache
def get_layers() -> dict[str, Layer]:
    document = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    if set(document) != {"items"}:
        raise ValueError("Map catalog must contain only the items field")
    items = [Layer.model_validate(item) for item in document["items"]]
    layers = {layer.id: layer for layer in items}
    if len(layers) != len(items):
        raise ValueError("Map catalog contains duplicate layer IDs")
    return layers


def get_layer(layer_id: str) -> Layer:
    layer = get_layers().get(layer_id)
    if layer is None:
        raise MapServiceError(404, "HTTP_404", "Map layer was not found")
    return layer


def layer_payload(layer: Layer) -> dict:
    return layer.model_dump(mode="json")
