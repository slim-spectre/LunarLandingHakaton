from collections import OrderedDict
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from time import monotonic
from urllib.parse import urlsplit
from xml.etree import ElementTree

import httpx

from app.maps.catalog import PROVIDER_HOSTS, Layer
from app.maps.errors import MapServiceError

ROOT = Path(__file__).resolve().parents[3]
WMTS_REFERENCE = ROOT / "contracts" / "reference" / "maps" / "moon_trek_global_capabilities.xml"
WMS_REFERENCE = ROOT / "contracts" / "reference" / "maps" / "lroc_wms_capabilities.xml"
MAX_IMAGE_BYTES = 4 * 1024 * 1024
UPSTREAM_TIMEOUT_SECONDS = 8.0
IMAGE_CACHE_TTL_SECONDS = 300.0
IMAGE_CACHE_ITEMS = 8
X_LINK = "{http://www.w3.org/1999/xlink}href"
WMTS_NS = "{http://www.opengis.net/wmts/1.0}"
OWS_NS = "{http://www.opengis.net/ows/1.1}"


@dataclass(frozen=True)
class TileMatrix:
    width: int
    height: int


def _positive_integer(text: str | None, label: str) -> int:
    if text is None:
        raise ValueError(f"WMTS capabilities is missing {label}")
    number = float(text)
    if not number.is_integer() or number <= 0:
        raise ValueError(f"WMTS capabilities has invalid {label}")
    return int(number)


def _read_wmts_configuration() -> tuple[str, str, dict[str, TileMatrix]]:
    root = ElementTree.parse(WMTS_REFERENCE).getroot()
    layers = root.find(WMTS_NS + "Contents")
    if layers is None:
        raise ValueError("Saved WMTS capabilities has no Contents")
    layer = next(
        (
            item
            for item in layers.findall(WMTS_NS + "Layer")
            if item.findtext(OWS_NS + "Identifier") == "LRO_WAC_Mosaic_Global_303ppd_v02"
        ),
        None,
    )
    if layer is None:
        raise ValueError("Saved WMTS capabilities is missing the registered global layer")
    link = layer.find(WMTS_NS + "TileMatrixSetLink")
    matrix_set = link.findtext(WMTS_NS + "TileMatrixSet") if link is not None else None
    resource = next(
        (
            item
            for item in layer.findall(WMTS_NS + "ResourceURL")
            if item.get("resourceType") == "tile"
        ),
        None,
    )
    if matrix_set != "default028mm" or resource is None:
        raise ValueError("Saved WMTS layer does not match the verified catalog")
    tile_template = resource.get("template")
    style = next(
        (
            item.findtext(OWS_NS + "Identifier")
            for item in layer.findall(WMTS_NS + "Style")
            if item.get("isDefault", "false").lower() == "true"
        ),
        None,
    )
    matrix_node = next(
        (
            item
            for item in layers.findall(WMTS_NS + "TileMatrixSet")
            if item.findtext(OWS_NS + "Identifier") == matrix_set
        ),
        None,
    )
    if not tile_template or not style or matrix_node is None:
        raise ValueError("Saved WMTS capabilities is missing tile configuration")
    matrices = {}
    for item in matrix_node.findall(WMTS_NS + "TileMatrix"):
        identifier = item.findtext(OWS_NS + "Identifier")
        if not identifier or identifier in matrices:
            raise ValueError("Saved WMTS capabilities has a missing or duplicate matrix ID")
        matrices[identifier] = TileMatrix(
            width=_positive_integer(item.findtext(WMTS_NS + "MatrixWidth"), "matrix width"),
            height=_positive_integer(item.findtext(WMTS_NS + "MatrixHeight"), "matrix height"),
        )
    if not matrices:
        raise ValueError("Saved WMTS capabilities has no tile matrices")
    return tile_template, style, matrices


WMTS_TEMPLATE, WMTS_STYLE, WMTS_MATRICES = _read_wmts_configuration()


def _read_wms_configuration() -> tuple[str, str, str]:
    root = ElementTree.parse(WMS_REFERENCE).getroot()
    version = root.get("version")
    get_map = next(
        (item for item in root.iter() if item.tag.rsplit("}", 1)[-1] == "GetMap"),
        None,
    )
    if get_map is None or not version:
        raise ValueError("Saved LROC WMS capabilities is incomplete")
    formats = {
        item.text
        for item in get_map.iter()
        if item.tag.rsplit("}", 1)[-1] == "Format" and item.text
    }
    get = next(
        (item for item in get_map.iter() if item.tag.rsplit("}", 1)[-1] == "Get"),
        None,
    )
    resource = next(
        (
            item
            for item in (get.iter() if get is not None else ())
            if item.tag.rsplit("}", 1)[-1] == "OnlineResource" and item.get(X_LINK)
        ),
        None,
    )
    endpoint = resource.get(X_LINK) if resource is not None else None
    if "image/png" not in formats or not endpoint:
        raise ValueError("Saved LROC WMS capabilities lacks PNG or a GetMap URL")
    return version, "image/png", endpoint


WMS_VERSION, WMS_FORMAT, WMS_ENDPOINT = _read_wms_configuration()


def build_wmts_url(matrix: str, row: int, col: int) -> str:
    definition = WMTS_MATRICES.get(matrix)
    if definition is None:
        raise MapServiceError(
            422,
            "VALIDATION_ERROR",
            "Tile matrix is not supported by this layer",
            [{"field": "matrix", "reason": "unsupported_matrix"}],
        )
    if row < 0 or row >= definition.height or col < 0 or col >= definition.width:
        raise MapServiceError(
            422,
            "VALIDATION_ERROR",
            "Tile row or column is outside the configured matrix",
            [{"field": "row,col", "reason": "tile_outside_matrix"}],
        )
    url = WMTS_TEMPLATE
    for placeholder, value in {
        "{Style}": WMTS_STYLE,
        "{TileMatrixSet}": "default028mm",
        "{TileMatrix}": matrix,
        "{TileRow}": str(row),
        "{TileCol}": str(col),
    }.items():
        url = url.replace(placeholder, value)
    _validate_upstream_url("moon_trek", url)
    return url


def build_wms_request(layer: Layer, bbox: str, width: int, height: int) -> tuple[str, dict]:
    if layer.service_type != "wms":
        raise MapServiceError(
            422,
            "VALIDATION_ERROR",
            "Image requests are supported only for WMS layers",
            [{"field": "layer_id", "reason": "unsupported_operation"}],
        )
    values = bbox.split(",")
    if len(values) != 4:
        raise MapServiceError(
            422,
            "VALIDATION_ERROR",
            "bbox must contain min_x,min_y,max_x,max_y",
            [{"field": "bbox", "reason": "invalid_bbox"}],
        )
    try:
        extent = [float(value) for value in values]
    except ValueError as exc:
        raise MapServiceError(
            422,
            "VALIDATION_ERROR",
            "bbox must contain four numeric coordinates",
            [{"field": "bbox", "reason": "invalid_bbox"}],
        ) from exc
    if not all(isfinite(value) for value in extent):
        raise MapServiceError(
            422,
            "VALIDATION_ERROR",
            "bbox coordinates must be finite",
            [{"field": "bbox", "reason": "invalid_bbox"}],
        )
    min_x, min_y, max_x, max_y = extent
    layer_min_x, layer_min_y, layer_max_x, layer_max_y = layer.extent
    if min_x >= max_x or min_y >= max_y:
        raise MapServiceError(
            422,
            "VALIDATION_ERROR",
            "bbox must have positive width and height",
            [{"field": "bbox", "reason": "invalid_bbox_extent"}],
        )
    if min_x < layer_min_x or min_y < layer_min_y or max_x > layer_max_x or max_y > layer_max_y:
        raise MapServiceError(
            422,
            "VALIDATION_ERROR",
            "bbox is outside the registered layer extent",
            [{"field": "bbox", "reason": "outside_layer_extent"}],
        )
    if not 1 <= width <= 1024 or not 1 <= height <= 1024:
        raise MapServiceError(
            422,
            "VALIDATION_ERROR",
            "Image dimensions must be between 1 and 1024 pixels",
            [{"field": "width,height", "reason": "image_dimensions_out_of_range"}],
        )
    # WMS 1.1.1 uses SRS and BBOX in x/y order; these layers advertise longitude/latitude.
    params = {
        "SERVICE": "WMS",
        "VERSION": WMS_VERSION,
        "REQUEST": "GetMap",
        "LAYERS": layer.id,
        "STYLES": "",
        "SRS": layer.crs_id,
        "BBOX": ",".join(values),
        "WIDTH": str(width),
        "HEIGHT": str(height),
        "FORMAT": WMS_FORMAT,
    }
    _validate_upstream_url(layer.provider, WMS_ENDPOINT)
    return WMS_ENDPOINT, params


def _validate_upstream_url(provider: str, url: str) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != PROVIDER_HOSTS.get(provider)
        or parsed.username
        or parsed.password
    ):
        raise MapServiceError(502, "HTTP_502", "Provider URL failed validation")


class ImageCache:
    def __init__(self):
        self._entries: OrderedDict[str, tuple[float, bytes, str]] = OrderedDict()

    def get(self, key: str) -> tuple[bytes, str] | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires, content, content_type = entry
        if expires <= monotonic():
            del self._entries[key]
            return None
        self._entries.move_to_end(key)
        return content, content_type

    def set(self, key: str, content: bytes, content_type: str) -> None:
        self._entries[key] = (monotonic() + IMAGE_CACHE_TTL_SECONDS, content, content_type)
        self._entries.move_to_end(key)
        while len(self._entries) > IMAGE_CACHE_ITEMS:
            self._entries.popitem(last=False)


IMAGE_CACHE = ImageCache()


async def fetch_image(
    provider: str,
    url: str,
    params: dict | None = None,
    *,
    client: httpx.AsyncClient | None = None,
) -> tuple[bytes, str]:
    _validate_upstream_url(provider, url)
    request_url = str(httpx.URL(url).copy_with(params=params))
    key = request_url
    cached = IMAGE_CACHE.get(key)
    if cached is not None:
        return cached
    owned_client = client is None
    client = client or httpx.AsyncClient(
        timeout=UPSTREAM_TIMEOUT_SECONDS,
        follow_redirects=False,
    )
    try:
        async with client.stream("GET", url, params=params) as response:
            if response.status_code == 404:
                raise MapServiceError(404, "HTTP_404", "Requested map image is not available")
            if response.status_code >= 500:
                raise MapServiceError(503, "HTTP_503", "Map provider is unavailable")
            if response.status_code != 200:
                raise MapServiceError(502, "HTTP_502", "Map provider returned an invalid response")
            content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if content_type not in {"image/png", "image/jpeg"}:
                raise MapServiceError(502, "HTTP_502", "Map provider returned a non-image response")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > MAX_IMAGE_BYTES:
                    raise MapServiceError(
                        502,
                        "HTTP_502",
                        "Map provider image exceeded the size limit",
                    )
            content = bytes(body)
            valid_signature = (
                content.startswith(b"\x89PNG\r\n\x1a\n")
                if content_type == "image/png"
                else content.startswith(b"\xff\xd8\xff")
            )
            if not content or not valid_signature:
                raise MapServiceError(502, "HTTP_502", "Map provider returned malformed image data")
            IMAGE_CACHE.set(key, content, content_type)
            return content, content_type
    except httpx.TimeoutException as exc:
        raise MapServiceError(503, "HTTP_503", "Map provider request timed out") from exc
    except httpx.RequestError as exc:
        raise MapServiceError(503, "HTTP_503", "Map provider request failed") from exc
    finally:
        if owned_client:
            await client.aclose()
