from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import JSONResponse, Response

from app.maps.catalog import Layer, get_layer, get_layers, layer_payload
from app.maps.errors import MapServiceError, error_response
from app.maps.providers import build_wms_request, build_wmts_url, fetch_image
from app.maps.schemas import LayerList, MapErrorEnvelope
from app.routes import no_get_body

router = APIRouter(prefix="/api/v1/map/layers", tags=["map"], dependencies=[Depends(no_get_body)])
ERROR_RESPONSES = {
    status: {"model": MapErrorEnvelope} for status in (400, 404, 422, 429, 500, 502, 503)
}
ERROR_RESPONSES[429]["headers"] = {
    "Retry-After": {
        "description": "Seconds until retry (nonnegative integer)",
        "schema": {"type": "string", "pattern": "^[0-9]+$"},
    }
}


def _reject_unknown_query(request: Request, allowed: set[str]) -> JSONResponse | None:
    unknown = (set(request.query_params) - allowed) | {
        key for key in allowed if len(request.query_params.getlist(key)) > 1
    }
    if not unknown:
        return None
    return error_response(
        request,
        MapServiceError(
            400,
            "INVALID_REQUEST",
            "Unknown query parameter",
            [{"field": f"query.{name}", "reason": "extra_forbidden"} for name in sorted(unknown)],
        ),
    )


@router.get("", response_model=LayerList, responses=ERROR_RESPONSES)
def list_layers(request: Request):
    unknown = _reject_unknown_query(request, set())
    if unknown:
        return unknown
    return {"items": [layer_payload(layer) for layer in get_layers().values()]}


@router.get("/{layer_id}", response_model=Layer, responses=ERROR_RESPONSES)
def get_layer_metadata(request: Request, layer_id: str):
    unknown = _reject_unknown_query(request, set())
    if unknown:
        return unknown
    try:
        return layer_payload(get_layer(layer_id))
    except MapServiceError as exc:
        return error_response(request, exc)


@router.get(
    "/{layer_id}/tiles/{matrix}/{row}/{col}",
    response_class=Response,
    responses={
        **ERROR_RESPONSES,
        200: {
            "description": "Registered provider map image",
            "content": {
                media_type: {"schema": {"type": "string", "format": "binary"}}
                for media_type in ("image/png", "image/jpeg")
            },
        },
    },
)
async def get_map_tile(
    request: Request,
    layer_id: str,
    matrix: str,
    row: Annotated[int, Path(ge=0)],
    col: Annotated[int, Path(ge=0)],
):
    unknown = _reject_unknown_query(request, set())
    if unknown:
        return unknown
    try:
        layer = get_layer(layer_id)
        if layer.service_type != "wmts":
            raise MapServiceError(
                422,
                "VALIDATION_ERROR",
                "Tile requests are supported only for WMTS layers",
                [{"field": "layer_id", "reason": "unsupported_operation"}],
            )
        url = build_wmts_url(matrix, row, col)
        content, content_type = await fetch_image(layer.provider, url)
        return Response(
            content,
            media_type=content_type,
            headers={"Cache-Control": "public, max-age=300"},
        )
    except MapServiceError as exc:
        return error_response(request, exc)


@router.get(
    "/{layer_id}/image",
    response_class=Response,
    responses={
        **ERROR_RESPONSES,
        200: {
            "description": "Registered provider map image",
            "content": {
                media_type: {"schema": {"type": "string", "format": "binary"}}
                for media_type in ("image/png", "image/jpeg")
            },
        },
    },
)
async def get_map_image(
    request: Request,
    layer_id: str,
    bbox: Annotated[
        str,
        Query(
            pattern=r"^-?(?:\d+(?:\.\d+)?),-?(?:\d+(?:\.\d+)?),-?(?:\d+(?:\.\d+)?),-?(?:\d+(?:\.\d+)?)$"
        ),
    ],
    width: Annotated[int, Query(ge=1, le=1024)],
    height: Annotated[int, Query(ge=1, le=1024)],
):
    unknown = _reject_unknown_query(request, {"bbox", "width", "height"})
    if unknown:
        return unknown
    try:
        layer = get_layer(layer_id)
        url, params = build_wms_request(layer, bbox, width, height)
        content, content_type = await fetch_image(layer.provider, url, params)
        return Response(
            content,
            media_type=content_type,
            headers={"Cache-Control": "public, max-age=300"},
        )
    except MapServiceError as exc:
        return error_response(request, exc)
