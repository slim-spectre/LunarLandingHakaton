# Map services integration handoff

The map router is exported from `app.maps` and is now registered by default in
`app.main.create_app`. It already owns the full `/api/v1/map/layers` prefix.
Custom applications can register it directly, without an additional prefix:

```python
from app.maps import router as map_router

app.include_router(map_router)
```

See [the final Stage 1 integration report](STAGE1_COMPLETION.md) for the shared
frontend/backend checks, browser observation and reproduction instructions.

The router serves these verified catalog IDs:

| Layer ID | Provider and operation | CRS and units | Attribution |
| --- | --- | --- | --- |
| `LRO_WAC_Mosaic_Global_303ppd_v02` | Moon Trek WMTS tiles | `urn:ogc:def:crs:EPSG::104903`, degrees | NASA/GSFC/ASU LROC Team; tiles served by NASA/JPL Moon Trek. |
| `luna_wac_roi_south_summer` | LROC WMS image | `IAU2000:30100`, degrees | NASA/GSFC/ASU LROC Team; cite Speyerer and Robinson (2013). |
| `luna_wac_global` | LROC WMS image | `IAU2000:30100`, degrees | NASA/GSFC/ASU LROC Team. |

QuickMap is an exploration/reference application. Programmatic rendered map
access is through the registered Moon Trek WMTS and LROC WMS adapters. Do not use
Earth `EPSG:4326` as a replacement for either lunar CRS. The Moon Trek service
advertises its CRS in an EPSG-shaped URN; preserve that literal identifier.

## Requests

All examples assume a locally running backend with this router registered.

```text
GET /api/v1/map/layers
GET /api/v1/map/layers/LRO_WAC_Mosaic_Global_303ppd_v02
GET /api/v1/map/layers/LRO_WAC_Mosaic_Global_303ppd_v02/tiles/0/0/0
GET /api/v1/map/layers/luna_wac_roi_south_summer/image?bbox=-2,-90,2,-88&width=512&height=512
```

The WMS BBOX order is `min_x,min_y,max_x,max_y` in the layer CRS. For the
registered WMS 1.1.1 layer this is longitude/latitude (x/y); the adapter sends
the advertised `SRS=IAU2000:30100` and does not swap axes. WMS dimensions must be
1 through 1024 pixels. WMTS matrix IDs and row/column bounds come from the saved
official Moon Trek GetCapabilities document.

A bounded live adapter smoke check returned matrix `0`, row `0`, column `0` from
Moon Trek as `image/jpeg` (49,475 bytes). The LROC WMS GetMap request for
`SRS=IAU2000:30100`, `BBOX=-2,-90,2,-88`, `WIDTH=64`, and `HEIGHT=64` returned
`image/png` (3,122 bytes). Providers can change; repeat these checks when
deploying or changing the saved capability snapshots.

Only registered layer IDs are accepted. Unknown IDs and absent source tiles
return the common error envelope with HTTP 404. Invalid operations, BBOX values,
dimensions, and tile indices return HTTP 422. Provider timeouts or network
failures return HTTP 503; malformed/non-image responses return HTTP 502. Failures
are never replaced with blank images. A bounded per-process cache retains up to
eight successful images for five minutes; it does not alter error responses.

Use the layer `attribution` field wherever an image is displayed. Keep the layer
name, CRS, units, and attribution visible or accessible in the map UI. The
metadata endpoint preserves the catalog attribution verbatim.

## Terrain status

The map service serves imagery only. PGDA numerical DEM products have been
identified for Shackleton Connecting Ridge, Faustini Rim A, and Peak near
Shackleton, but no data has been registered as terrain coverage and none is
processed into a validated physical horizon model. See
[`terrain-stage1-handoff.md`](../sources/terrain-stage1-handoff.md). Later terrain
work must resolve coordinate and vertical reference details, validate source
coverage and no-data behavior, and generate a tested horizon model before
observation calculations may claim terrain availability.
