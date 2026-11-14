import asyncio
from importlib import import_module

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.database import check_database
from app.main import create_app
from app.maps.catalog import get_layer, get_layers
from app.maps.errors import MapServiceError
from app.maps.providers import (
    IMAGE_CACHE,
    WMS_ENDPOINT,
    WMS_FORMAT,
    WMS_VERSION,
    WMTS_MATRICES,
    build_wms_request,
    build_wmts_url,
    fetch_image,
)

map_routes = import_module("app.maps.router")
PNG = b"\x89PNG\r\n\x1a\nfixture"
JPEG = b"\xff\xd8\xfffixture"


@pytest.fixture
def client():
    app = create_app()
    app.dependency_overrides[check_database] = lambda: None
    with TestClient(app) as test_client:
        yield test_client


def clear_image_cache():
    IMAGE_CACHE._entries.clear()


def test_default_application_registers_real_map_routes_once(client):
    assert client.get("/api/v1/map/layers").status_code == 200
    assert len(client.get("/api/v1/map/layers").json()["items"]) == 3
    assert client.get("/api/v1/api/v1/map/layers").status_code == 404
    assert client.get("/api/v1/map/layers/luna_wac_global").status_code == 200


def test_map_routes_reject_get_bodies_and_duplicate_query_values(client):
    response = client.request("GET", "/api/v1/map/layers", json={"unexpected": True})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    response = client.get(
        "/api/v1/map/layers/luna_wac_global/image?bbox=-2,-90,2,-88&width=64&width=32&height=64"
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_registry_matches_contract_and_preserves_attribution():
    items = list(get_layers().values())
    assert len(items) == 3
    assert all(
        set(item.model_dump())
        == {
            "id",
            "name",
            "provider",
            "service_type",
            "crs_id",
            "coordinate_units",
            "extent",
            "attribution",
            "source_url",
            "tile_matrix_set",
            "access_url_template",
        }
        for item in items
    )
    assert get_layer("LRO_WAC_Mosaic_Global_303ppd_v02").attribution == (
        "NASA/GSFC/ASU LROC Team; tiles served by NASA/JPL Moon Trek."
    )
    assert get_layer("luna_wac_roi_south_summer").crs_id == "IAU2000:30100"


def test_wmts_url_comes_from_saved_verified_capabilities_and_validates_grid():
    assert WMTS_MATRICES["0"].width == 2
    assert WMTS_MATRICES["0"].height == 1
    assert build_wmts_url("0", 0, 0) == (
        "https://trek.nasa.gov/tiles/Moon/EQ/LRO_WAC_Mosaic_Global_303ppd_v02/"
        "1.0.0//default/default028mm/0/0/0.jpg"
    )
    for args in (("9", 0, 0), ("0", 1, 0), ("0", 0, 2)):
        with pytest.raises(MapServiceError) as error:
            build_wmts_url(*args)
        assert error.value.status_code == 422


def test_wms_request_preserves_contract_bbox_axis_order_and_lunar_crs():
    layer = get_layer("luna_wac_roi_south_summer")
    url, params = build_wms_request(layer, "-2,-90,2,-88", 512, 256)
    assert url == WMS_ENDPOINT == "https://wms.im-ldi.com/?"
    assert WMS_VERSION == "1.1.1"
    assert WMS_FORMAT == "image/png"
    assert params == {
        "SERVICE": "WMS",
        "VERSION": "1.1.1",
        "REQUEST": "GetMap",
        "LAYERS": "luna_wac_roi_south_summer",
        "STYLES": "",
        "SRS": "IAU2000:30100",
        "BBOX": "-2,-90,2,-88",
        "WIDTH": "512",
        "HEIGHT": "256",
        "FORMAT": "image/png",
    }
    assert "CRS" not in params


@pytest.mark.parametrize(
    "bbox,width,height,reason",
    [
        ("-2,-89,-2,-88", 10, 10, "invalid_bbox_extent"),
        ("-181,-89,-179,-88", 10, 10, "outside_layer_extent"),
        ("-2,-89,-1,-88", 1025, 10, "image_dimensions_out_of_range"),
        ("-2,-89,-1,-88", 10, 0, "image_dimensions_out_of_range"),
    ],
)
def test_wms_bbox_and_dimensions_are_validated(bbox, width, height, reason):
    with pytest.raises(MapServiceError) as error:
        build_wms_request(get_layer("luna_wac_global"), bbox, width, height)
    assert error.value.status_code == 422
    assert error.value.details[0]["reason"] == reason


def test_routes_list_and_return_registered_layer_metadata(client):
    listing = client.get("/api/v1/map/layers")
    detail = client.get("/api/v1/map/layers/luna_wac_roi_south_summer")
    assert listing.status_code == detail.status_code == 200
    assert len(listing.json()["items"]) == 3
    assert detail.json()["crs_id"] == "IAU2000:30100"
    assert detail.json()["attribution"] == get_layer("luna_wac_roi_south_summer").attribution


def test_router_openapi_matches_map_response_contract(client):
    document = client.get("/openapi.json").json()
    paths = document["paths"]
    assert set(paths) >= {
        "/api/v1/map/layers",
        "/api/v1/map/layers/{layer_id}",
        "/api/v1/map/layers/{layer_id}/tiles/{matrix}/{row}/{col}",
        "/api/v1/map/layers/{layer_id}/image",
    }
    layer_schema = document["components"]["schemas"]["Layer"]
    assert set(layer_schema["required"]) == {
        "id",
        "name",
        "provider",
        "service_type",
        "crs_id",
        "coordinate_units",
        "extent",
        "attribution",
        "source_url",
        "tile_matrix_set",
        "access_url_template",
    }
    assert layer_schema["properties"]["provider"]["enum"] == ["moon_trek", "lroc"]
    image_types = paths["/api/v1/map/layers/{layer_id}/image"]["get"]["responses"]["200"]["content"]
    assert set(image_types) == {"image/png", "image/jpeg"}


def test_unknown_layer_and_query_parameter_use_common_error_envelope(client):
    missing = client.get("/api/v1/map/layers/not-registered")
    unknown_query = client.get("/api/v1/map/layers?source_url=https://example.invalid")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "HTTP_404"
    assert unknown_query.status_code == 400
    assert unknown_query.json()["error"]["code"] == "INVALID_REQUEST"
    assert unknown_query.headers["X-Request-ID"] == unknown_query.json()["error"]["request_id"]


def test_unsupported_operation_and_invalid_bbox_return_validation_errors(client):
    unsupported = client.get(
        "/api/v1/map/layers/LRO_WAC_Mosaic_Global_303ppd_v02/image",
        params={"bbox": "-1,-1,1,1", "width": 32, "height": 32},
    )
    invalid = client.get(
        "/api/v1/map/layers/luna_wac_global/image",
        params={"bbox": "-2,-89,-2,-88", "width": 32, "height": 32},
    )
    assert unsupported.status_code == invalid.status_code == 422
    assert unsupported.json()["error"]["code"] == "VALIDATION_ERROR"
    assert invalid.json()["error"]["details"][0]["reason"] == "invalid_bbox_extent"


def test_wmts_route_returns_actual_image_content_type(client, monkeypatch):
    async def image(*args, **kwargs):
        return JPEG, "image/jpeg"

    monkeypatch.setattr(map_routes, "fetch_image", image)
    response = client.get("/api/v1/map/layers/LRO_WAC_Mosaic_Global_303ppd_v02/tiles/0/0/0")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "public, max-age=300"


def test_route_returns_envelope_when_provider_tile_is_missing(client, monkeypatch):
    async def missing(*args, **kwargs):
        raise MapServiceError(404, "HTTP_404", "Requested map image is not available")

    monkeypatch.setattr(map_routes, "fetch_image", missing)
    response = client.get("/api/v1/map/layers/LRO_WAC_Mosaic_Global_303ppd_v02/tiles/0/0/0")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HTTP_404"
    assert response.headers["X-Request-ID"] == response.json()["error"]["request_id"]


def test_wms_route_returns_image_and_rejects_unknown_query(client, monkeypatch):
    async def image(*args, **kwargs):
        return PNG, "image/png"

    monkeypatch.setattr(map_routes, "fetch_image", image)
    response = client.get(
        "/api/v1/map/layers/luna_wac_global/image",
        params={"bbox": "-2,-89,2,-88", "width": 32, "height": 32},
    )
    invalid = client.get(
        "/api/v1/map/layers/luna_wac_global/image",
        params={"bbox": "-2,-89,2,-88", "width": 32, "height": 32, "format": "png"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert invalid.status_code == 400


def run(coroutine):
    return asyncio.run(coroutine)


def test_provider_missing_tile_is_not_replaced_with_blank_image():
    clear_image_cache()

    async def check():
        async def missing(request):
            return httpx.Response(404, request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(missing)) as client:
            with pytest.raises(MapServiceError) as error:
                await fetch_image("moon_trek", build_wmts_url("0", 0, 0), client=client)
        assert error.value.status_code == 404

    run(check())


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, headers={"content-type": "text/html"}, content=b"provider failure"),
        httpx.Response(200, headers={"content-type": "image/png"}, content=b"not a png"),
    ],
)
def test_non_image_and_malformed_image_responses_are_rejected(response):
    clear_image_cache()

    async def check():
        async def malformed(request):
            return httpx.Response(
                response.status_code,
                headers=response.headers,
                content=response.content,
                request=request,
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(malformed)) as client:
            with pytest.raises(MapServiceError) as error:
                await fetch_image("lroc", "https://wms.im-ldi.com/?case=malformed", client=client)
        assert error.value.status_code == 502

    run(check())


def test_provider_timeout_is_reported_as_service_unavailable():
    clear_image_cache()

    async def check():
        async def timeout(request):
            raise httpx.ReadTimeout("timed out", request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as client:
            with pytest.raises(MapServiceError) as error:
                await fetch_image("lroc", "https://wms.im-ldi.com/?case=timeout", client=client)
        assert error.value.status_code == 503

    run(check())


def test_provider_cache_reuses_successful_images_for_identical_requests():
    clear_image_cache()

    async def check():
        requests = 0

        async def image(request):
            nonlocal requests
            requests += 1
            return httpx.Response(
                200,
                headers={"content-type": "image/jpeg"},
                content=JPEG,
                request=request,
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(image)) as client:
            first = await fetch_image(
                "moon_trek", "https://trek.nasa.gov/cache-test.jpg", client=client
            )
            second = await fetch_image(
                "moon_trek", "https://trek.nasa.gov/cache-test.jpg", client=client
            )
        assert first == second == (JPEG, "image/jpeg")
        assert requests == 1

    run(check())
