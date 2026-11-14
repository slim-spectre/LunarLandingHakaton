"""Bounded, opt-in verification of official lunar map and terrain sources."""

import argparse
import json
from datetime import UTC, datetime
from math import isfinite
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from xml.etree import ElementTree

MAX_BYTES = 4 * 1024 * 1024
WMTS_SOURCES = {
    "global": (
        "https://trek.nasa.gov/tiles/Moon/EQ/LRO_WAC_Mosaic_Global_303ppd_v02/"
        "1.0.0/WMTSCapabilities.xml"
    ),
    "south_pole": (
        "https://trek.nasa.gov/tiles/Moon/SP/WAC_POLE_ILL_PCT_SOUTH_100M/"
        "1.0.0/WMTSCapabilities.xml"
    ),
}
WMS_SOURCE = "https://wms.im-ldi.com/?SERVICE=WMS&REQUEST=GetCapabilities&VERSION=1.1.1"
ALLOWED_HOSTS = {"trek.nasa.gov", "wms.im-ldi.com", "pgda.gsfc.nasa.gov"}
DEM_SOURCES = {
    "connecting_ridge_5m": (
        "https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/Site01/Site01_final_adj_5mpp_surf.tif",
        65536,
    ),
    "faustini_rim_a_5m": (
        "https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/LM7/LM7_final_adj_5mpp_surf.tif",
        65536,
    ),
    "peak_near_shackleton_5m": (
        "https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/Site07/Site07_final_adj_5mpp_surf.tif",
        65536,
    ),
    "south_pole_20m": (
        "https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LDEM_80S_20MPP_ADJ.TIF",
        8192,
    ),
}
WMTS = "{http://www.opengis.net/wmts/1.0}"
OWS = "{http://www.opengis.net/ows/1.1}"


def parse_wmts(document: bytes, expected_layer: str | None = None) -> dict:
    """Return actual WMTS metadata; reject incomplete or mismatched documents."""
    if b"<!DOCTYPE" in document.upper() or b"<!ENTITY" in document.upper():
        raise ValueError("WMTS capabilities must not contain a DTD or entity declaration")
    try:
        root = ElementTree.fromstring(document)
    except ElementTree.ParseError as exc:
        raise ValueError("Malformed WMTS capabilities XML") from exc
    if root.tag != WMTS + "Capabilities":
        raise ValueError("Document is not WMTS capabilities")
    contents = root.find(WMTS + "Contents")
    if contents is None:
        raise ValueError("WMTS capabilities has no Contents")
    layers = []
    for layer in contents.findall(WMTS + "Layer"):
        identifier = layer.findtext(OWS + "Identifier")
        link = layer.find(WMTS + "TileMatrixSetLink")
        matrix_link = link.findtext(WMTS + "TileMatrixSet") if link is not None else None
        resource = next(
            (
                item
                for item in layer.findall(WMTS + "ResourceURL")
                if item.get("resourceType") == "tile"
            ),
            None,
        )
        bbox = layer.find(OWS + "BoundingBox")
        lower = bbox.findtext(OWS + "LowerCorner") if bbox is not None else None
        upper = bbox.findtext(OWS + "UpperCorner") if bbox is not None else None
        if not identifier or not matrix_link or resource is None or not resource.get("template"):
            raise ValueError("WMTS layer is missing its identifier, matrix set, or tile resource")
        matrix_set = next(
            (item for item in contents.findall(WMTS + "TileMatrixSet")
             if item.findtext(OWS + "Identifier") == matrix_link),
            None,
        )
        crs = bbox.get("crs") if bbox is not None else None
        supported_crs = (
            matrix_set.findtext(OWS + "SupportedCRS") if matrix_set is not None else None
        )
        if not crs or not supported_crs or not lower or not upper:
            raise ValueError("WMTS layer is missing its CRS or geographic extent")
        formats = [item.text for item in layer.findall(WMTS + "Format") if item.text]
        if not formats or not matrix_set.findall(WMTS + "TileMatrix"):
            raise ValueError("WMTS layer is missing formats or tile matrices")
        extent = [float(value) for value in (lower + " " + upper).split()]
        if (
            len(extent) != 4
            or not all(isfinite(value) for value in extent)
            or not (extent[0] < extent[2] and extent[1] < extent[3])
        ):
            raise ValueError(f"WMTS layer has malformed extent: {identifier}")
        layers.append({
            "id": identifier,
            "title": layer.findtext(OWS + "Title"),
            "tile_matrix_set": matrix_link,
            "crs": crs,
            "supported_crs": supported_crs,
            "extent": extent,
            "coordinate_units": "degrees" if "104903" in crs else None,
            "formats": formats,
            "tile_template": resource.get("template"),
            "matrix_count": len(matrix_set.findall(WMTS + "TileMatrix")),
            "first_matrix": matrix_set.findtext(WMTS + "TileMatrix/" + OWS + "Identifier"),
            "style": layer.findtext(WMTS + "Style/" + OWS + "Identifier"),
        })
    if not layers:
        raise ValueError("WMTS capabilities advertises no layers")
    if expected_layer and not any(layer["id"] == expected_layer for layer in layers):
        raise ValueError(f"Expected WMTS layer ID is absent: {expected_layer}")
    return {"layers": layers}


def classify_product(format_name: str, values_are_elevation: bool) -> str:
    """Separate numerical terrain grids from rendered imagery and derivatives."""
    if values_are_elevation and format_name.lower() in {
        "geotiff",
        "tif",
        "tiff",
        "netcdf",
        "isis cube",
    }:
        return "numerical_terrain"
    return "imagery_or_derived_visualization"


def parse_wms(document: bytes) -> dict:
    if b"<!ENTITY" in document.upper():
        raise ValueError("WMS capabilities must not contain entity declarations")
    try:
        root = ElementTree.fromstring(document)
    except ElementTree.ParseError as exc:
        raise ValueError("Malformed WMS capabilities XML") from exc
    if root.tag.rsplit("}", 1)[-1] not in {"WMS_Capabilities", "WMT_MS_Capabilities"}:
        raise ValueError("Document is not WMS capabilities")
    capability = next((node for node in root if node.tag.rsplit("}", 1)[-1] == "Capability"), None)
    if capability is None:
        raise ValueError("WMS capabilities has no Capability section")
    request = next((node for node in capability if node.tag.rsplit("}", 1)[-1] == "Request"), None)
    get_map = next(
        (
            node
            for node in (request if request is not None else ())
            if node.tag.rsplit("}", 1)[-1] == "GetMap"
        ),
        None,
    )
    formats = [
        node.text
        for node in (get_map if get_map is not None else ())
        if node.tag.rsplit("}", 1)[-1] == "Format" and node.text
    ]
    root_layer = next((node for node in capability if node.tag.rsplit("}", 1)[-1] == "Layer"), None)
    if root_layer is None or not formats:
        raise ValueError("WMS capabilities is missing layers or GetMap formats")
    layers = []

    def visit(layer, inherited_crs=()):
        names = [
            child.text
            for child in layer
            if child.tag.rsplit("}", 1)[-1] in {"CRS", "SRS"} and child.text
        ]
        crs_values = tuple(dict.fromkeys((*inherited_crs, *names)))
        name = next(
            (
                child.text
                for child in layer
                if child.tag.rsplit("}", 1)[-1] == "Name" and child.text
            ),
            None,
        )
        title = next(
            (
                child.text
                for child in layer
                if child.tag.rsplit("}", 1)[-1] == "Title" and child.text
            ),
            None,
        )
        box = next(
            (child for child in layer if child.tag.rsplit("}", 1)[-1] == "BoundingBox"),
            None,
        )
        if name:
            if box is not None:
                crs = box.get("CRS") or box.get("SRS")
                extent = [float(box.get(key, "nan")) for key in ("minx", "miny", "maxx", "maxy")]
            else:
                box = next(
                    (
                        child
                        for child in layer
                        if child.tag.rsplit("}", 1)[-1] == "LatLonBoundingBox"
                    ),
                    None,
                )
                crs = next(
                    (value for value in crs_values if "104903" in value or "30100" in value),
                    None,
                )
                extent = (
                    [float(box.get(key, "nan")) for key in ("minx", "miny", "maxx", "maxy")]
                    if box is not None
                    else []
                )
            if box is not None and (not crs or crs not in crs_values):
                raise ValueError(f"WMS layer has invalid CRS metadata: {name}")
            if extent and (
                any(value != value for value in extent)
                or not (extent[0] < extent[2] and extent[1] < extent[3])
            ):
                raise ValueError(f"WMS layer has malformed extent: {name}")
            if crs and extent:
                layers.append({
                    "id": name,
                    "title": title,
                    "crs": crs,
                    "coordinate_units": "degrees" if "104903" in crs or "30100" in crs else None,
                    "extent": extent,
                })
        for child in layer:
            if child.tag.rsplit("}", 1)[-1] == "Layer":
                visit(child, crs_values)

    visit(root_layer)
    if not layers:
        raise ValueError("WMS capabilities advertises no named layers")
    return {"formats": formats, "layers": layers}


class SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        parsed = urlsplit(new_url)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
            raise ValueError("Provider redirected outside the HTTPS allowlist")
        return super().redirect_request(request, response, code, message, headers, new_url)


def fetch(opener, url: str, timeout: float) -> tuple[int, str | None, bytes]:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError("Probe URL is outside the HTTPS provider allowlist")
    request = Request(url, headers={"User-Agent": "LunarNavigator-Stage0-source-probe/1.0"})
    with opener.open(request, timeout=timeout) as response:
        body = bytearray()
        while chunk := response.read(min(65536, MAX_BYTES + 1 - len(body))):
            body.extend(chunk)
            if len(body) > MAX_BYTES:
                raise ValueError("Provider response exceeds the four MiB limit")
        return response.status, response.headers.get("content-type"), bytes(body)


def first_tile_url(layer: dict) -> str:
    template = layer["tile_template"]
    replacements = {
        "{Style}": layer["style"],
        "{TileMatrixSet}": layer["tile_matrix_set"],
        "{TileMatrix}": layer["first_matrix"],
        "{TileRow}": "0",
        "{TileCol}": "0",
    }
    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)
    return template


def head_and_range(opener, url: str, byte_count: int, timeout: float) -> dict:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError("Probe URL is outside the HTTPS provider allowlist")
    with opener.open(Request(url, method="HEAD"), timeout=timeout) as response:
        head_status = response.status
        content_length = response.headers.get("content-length")
    request = Request(url, headers={"Range": f"bytes=0-{byte_count - 1}"})
    with opener.open(request, timeout=timeout) as response:
        body = response.read(byte_count + 1)
        content_range = response.headers.get("content-range")
        if (
            response.status != 206
            or len(body) != byte_count
            or not content_range
            or not content_range.startswith(f"bytes 0-{byte_count - 1}/")
        ):
            raise ValueError("Provider did not honor the exact bounded byte-range request")
        return {
            "url": url,
            "head_status": head_status,
            "content_length_bytes": int(content_length) if content_length else None,
            "range_status": response.status,
            "content_range": content_range,
            "range_bytes_read": len(body),
        }


def verify(
    timeout: float,
    snapshot_dir: Path | None = None,
    terrain_metadata: bool = False,
) -> dict:
    report = {
        "verified_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "timeout_seconds": timeout,
        "verification": "incomplete",
        "wmts": {},
        "wms": {"url": WMS_SOURCE, "verification": "incomplete"},
        "failures": [],
    }
    opener = build_opener(ProxyHandler({}), SafeRedirectHandler())
    for name, url in WMTS_SOURCES.items():
        entry = {"capabilities_url": url, "verification": "incomplete"}
        report["wmts"][name] = entry
        try:
            status, content_type, body = fetch(opener, url, timeout)
            entry["http_status"] = status
            entry["content_type"] = content_type
            if status != 200:
                raise ValueError(f"GetCapabilities returned HTTP {status}")
            if snapshot_dir:
                snapshot_dir.mkdir(parents=True, exist_ok=True)
                (snapshot_dir / f"moon_trek_{name}_capabilities.xml").write_bytes(body)
            entry.update(parse_wmts(body))
            layer = entry["layers"][0]
            tile_url = first_tile_url(layer)
            tile_status, tile_type, tile_body = fetch(opener, tile_url, timeout)
            entry["tile_check"] = {
                "url": tile_url,
                "http_status": tile_status,
                "content_type": tile_type,
                "bytes": len(tile_body),
                "matrix": layer["first_matrix"],
                "row": 0,
                "col": 0,
            }
            if tile_status != 200 or not tile_type or not tile_type.startswith("image/"):
                raise ValueError("First advertised tile did not return an image")
            entry["verification"] = "complete"
        except (URLError, TimeoutError, ValueError) as exc:
            entry["failure"] = f"{type(exc).__name__}: {exc}"
            report["failures"].append(f"Moon Trek {name}: {entry['failure']}")
    try:
        status, content_type, body = fetch(opener, WMS_SOURCE, timeout)
        report["wms"].update(
            http_status=status,
            content_type=content_type,
        )
        if status != 200:
            raise ValueError(f"WMS GetCapabilities returned HTTP {status}")
        if snapshot_dir:
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            (snapshot_dir / "lroc_wms_capabilities.xml").write_bytes(body)
        parsed_wms = parse_wms(body)
        report["wms"].update(
            formats=parsed_wms["formats"],
            layers=[
                layer
                for layer in parsed_wms["layers"]
                if layer["id"] in {"luna_wac_roi_south_summer", "luna_wac_global"}
            ],
        )
        if not report["wms"]["layers"]:
            raise ValueError("WMS capabilities does not expose a supported LROC WAC layer")
        report["wms"]["verification"] = "complete"
    except (URLError, TimeoutError, ValueError) as exc:
        report["wms"]["failure"] = f"{type(exc).__name__}: {exc}"
        report["failures"].append(f"LROC WMS: {report['wms']['failure']}")
    if terrain_metadata:
        report["terrain_metadata"] = {}
        for name, (url, byte_count) in DEM_SOURCES.items():
            try:
                report["terrain_metadata"][name] = head_and_range(
                    opener, url, byte_count, timeout
                )
                metadata = report["terrain_metadata"][name]
                metadata["verification"] = (
                    "complete"
                    if metadata["head_status"] == 200
                    and metadata["range_status"] == 206
                    and metadata["range_bytes_read"] == byte_count
                    and metadata["content_range"].startswith(f"bytes 0-{byte_count - 1}/")
                    else "incomplete"
                )
                if metadata["verification"] != "complete":
                    raise ValueError("HEAD or bounded range response was not successful")
            except (URLError, TimeoutError, ValueError) as exc:
                report["terrain_metadata"][name] = {
                    "url": url,
                    "verification": "incomplete",
                    "failure": f"{type(exc).__name__}: {exc}",
                }
                report["failures"].append(
                    f"PGDA {name}: {report['terrain_metadata'][name]['failure']}"
                )
    wmts_complete = all(
        entry["verification"] == "complete" for entry in report["wmts"].values()
    )
    wms_complete = report["wms"]["verification"] == "complete"
    if wmts_complete and wms_complete:
        if not terrain_metadata or all(
            entry["verification"] == "complete" for entry in report["terrain_metadata"].values()
        ):
            report["verification"] = "complete"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=10, help="Per-request timeout in seconds")
    parser.add_argument("--output", type=Path, help="Write JSON report to this path")
    parser.add_argument("--snapshot-dir", type=Path, help="Save successful WMTS capabilities XML")
    parser.add_argument(
        "--terrain-metadata",
        action="store_true",
        help="Check PGDA DEM HEAD and small byte-range responses; never download a raster",
    )
    args = parser.parse_args()
    if not 0 < args.timeout <= 60:
        parser.error("--timeout must be greater than 0 and at most 60 seconds")
    report = verify(args.timeout, args.snapshot_dir, terrain_metadata=args.terrain_metadata)
    rendered = json.dumps(report, indent=2, ensure_ascii=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if report["verification"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
