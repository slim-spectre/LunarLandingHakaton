# Map and terrain source verification

Stage 0 source inspection; this does not implement map proxying, terrain
processing, horizon masks, or illumination calculations. The API contract remains
the source of truth for catalog fields, degree/metre units, longitude
normalization, and the local ENU heightmap response.

Live service checks were run with `python backend/tools/probe_maps.py --timeout
12 --snapshot-dir contracts/reference/maps --terrain-metadata`. The latest
successful report was recorded at `2026-11-13T22:23:33Z`: both Moon Trek
GetCapabilities documents and actual tiles, LROC WMS GetCapabilities, and
bounded HEAD/range checks for all four PGDA rasters succeeded. The raw
capability XML and captured report are saved under `contracts/reference/maps/`.
An earlier run in the restricted shell failed with Windows `WinError 10013`
before connecting; the authorized network run succeeded, so this was a local
socket permission failure rather than a provider failure. Source state can
change; rerun before implementation or deployment.

## Moon Trek WMTS

Moon Trek documents its map layers as OGC RESTful WMTS and instructs clients to
take the layer, matrix set, matrix IDs, and image extension from GetCapabilities
and `ResourceURL`, rather than constructing them from a guessed naming rule.
The [official WMTS guide](https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=moon)
and [Moon Trek application](https://trek.nasa.gov/moon/) are the provider references.

| Result | Basemap: global LRO WAC | South-pole illumination layer |
| --- | --- | --- |
| Capabilities URL/status | [GetCapabilities](https://trek.nasa.gov/tiles/Moon/EQ/LRO_WAC_Mosaic_Global_303ppd_v02/1.0.0/WMTSCapabilities.xml), HTTP 200, `application/xml` | [GetCapabilities](https://trek.nasa.gov/tiles/Moon/SP/WAC_POLE_ILL_PCT_SOUTH_100M/1.0.0/WMTSCapabilities.xml), HTTP 200, `application/xml` |
| Layer identifier | `LRO_WAC_Mosaic_Global_303ppd_v02` | `WAC_POLE_ILL_PCT_SOUTH_100M` |
| Tile matrix set | `default028mm` | `default028mm` |
| Service CRS as advertised | `urn:ogc:def:crs:EPSG::104903` | `urn:ogc:def:crs:EPSG::0` |
| Units and extent | Degrees; `[-180, -90, 180, 90]` | CRS and units unresolved; advertised projected bounding box `[-60884.204, -61186.798, 61115.796, 61213.202]` |
| Image format | `image/jpeg` | `image/png` |
| Actual tile check | Matrix `0`, row `0`, col `0`: HTTP 200, `image/jpeg`, 49,475 bytes | Matrix `0`, row `0`, col `0`: HTTP 200, `image/png`, 804 bytes |
| Attribution | NASA/GSFC/ASU LROC team; tiles served by NASA/JPL Moon Trek | NASA/GSFC/ASU LROC team; tiles served by NASA/JPL Moon Trek |

The global layer is usable as a lunar basemap. The advertised identifier
`104903` resolves in the ESRI registry to the lunar geographic CRS Moon 2000,
whose angular units are degrees ([ESRI:104903 reference](https://epsg.io/104903)).
The WMTS document itself places the number in an `EPSG` URN; preserve that raw
service value, and resolve the authority discrepancy before treating it as the
project's canonical CRS identifier.

The polar layer is a percentage-based WAC illumination image, not terrain. Its
GetCapabilities response labels its CRS `EPSG::0`; the layer's projected bbox
values and PNG tile response do not establish a valid CRS identifier or its
coordinate units. The LROC product description independently describes the
illumination product as a 100 m/pixel polar-stereographic map covering 88°S to
90°S ([official product metadata](https://data.lroc.im-ldi.com/lroc/view_rdr/WAC_POLE_ILL_PCT_SOUTH)).
That documentation confirms its south-pole relevance, but does not repair the
WMTS CRS metadata. The layer is therefore documented here and excluded from
`map_layers.json` until the service CRS and units are resolved.

Both successful tile URLs were expanded from the saved capabilities document's
advertised `ResourceURL`, style, matrix set, and first matrix; the row and column
were `0` and `0`. The original tile template contains a double slash before the
style segment. Keep the captured URL behavior until the provider confirms a
canonical form.

## LROC WMS and QuickMap

QuickMap is an interactive LROC web application. It is not the map-data service.
NASA identifies [QuickMap](https://quickmap.lroc.asu.edu/) as the web viewer
([NASA QuickMap description](https://science.nasa.gov/wp-content/uploads/2024/04/citizen-science-lpsc2024.pdf)).
The LROC team's separate [Lunaserv WMS](https://wms.im-ldi.com/lunaserv.html)
serves supported data layers. LROC describes that WMS and GetCapabilities
workflow on its [official Lunaserv page](https://lroc.im-ldi.com/news/531).

The verified service endpoint is `https://wms.im-ldi.com/`; its returned
capabilities document is WMS 1.1.1, HTTP 200, content type
`application/vnd.ogc.wms_xml`. The verified [capabilities request](https://wms.im-ldi.com/?SERVICE=WMS&REQUEST=GetCapabilities&VERSION=1.1.1)
advertises `image/png`, `image/jpeg`, `image/tiff`, `image/gif`, `image/pnm`,
`image/vicar`, `application/x-cesium-terrain`, and `image/tiff; mode=32bit` for
GetMap. Use `image/png` for the contracted map-image response.

| Verified WMS layer | Identifier | CRS | Units / advertised extent | Coverage note |
| --- | --- | --- | --- | --- |
| LROC WAC South Pole Summer Mosaic | `luna_wac_roi_south_summer` | `IAU2000:30100` | Degrees; capabilities LatLonBoundingBox `[-180, -90, 180, 90]` | Layer abstract says polar-stereographic source mosaic spans 45° from the south pole. The published geographic bbox is broad and not a tight footprint. |
| LROC WAC Global 100m/px | `luna_wac_global` | `IAU2000:30100` | Degrees; `[-180, -90, 180, 90]` | Global image layer. |

Both identifiers, CRS values, extents, and formats come from the saved live WMS
capabilities document. The South Pole Summer Mosaic's abstract says it was made
from LROC WAC images selected for low southern solar elevation and projected
using GLD100/LOLA near-pole data; it is a rendered mosaic, not a numeric DEM.
See the [official LROC mosaic description](https://data.lroc.im-ldi.com/lroc/view_rdr/WAC_ROI_SOUTH_SUMMER).
LROC's page cites Speyerer and Robinson (2013) for the associated polar
illumination product; the WMS layer's own abstract is the source for the mosaic
description.

### QuickMap area links

The verified QuickMap entry point redirects from NASA's
`https://quickmap.lroc.asu.edu/` to the current official application at
`https://quickmap.lroc.im-ldi.com/`. Open the application and use its place/feature
search for each named area:

- [Shackleton Connecting Ridge](https://quickmap.lroc.im-ldi.com/) — search `Connecting Ridge`.
- [Faustini Rim A](https://quickmap.lroc.im-ldi.com/) — search `Faustini` or `Faustini Rim A`.
- [Peak near Shackleton](https://quickmap.lroc.im-ldi.com/) — search `Peak near Shackleton` or `Shackleton`.

QuickMap's official material documents a UI-generated permalink/share feature,
but does not specify stable center-coordinate URL parameters. The computer-use
browser inventory returned no browser, so no map-state permalink could be
generated or verified. These are verified application links with search
instructions, not claimed deep links to a pre-centered view. Do not add guessed
URL parameters.

## Terrain candidates and coverage

The selected additional site for comparison is Peak near Shackleton (PGDA
Site07). NASA's [Product 78 metadata](https://pgda.gsfc.nasa.gov/products/78)
lists local numerical LDEMs for Site01 (Connecting Ridge), Site07 (Peak near
Shackleton), and LM7 (Faustini Rim A), as well as ROI shapefiles. Those local
files are useful high-resolution candidates but are not the proof of pole-wide
coverage. The regional [Product 90 metadata](https://pgda.gsfc.nasa.gov/products/90)
explicitly states that `LDEM_80S_20MPP_ADJ.TIF` covers 80°S–90°S, so its named
coverage includes the south pole and all three candidate latitudes. Its header
was checked with an 8 KiB byte-range request only; no multi-gigabyte raster was
downloaded.

| Dataset / use | Numerical format, version | Footprint and horizontal resolution | Vertical units / reference | CRS and no-data | Download size | Official metadata / download |
| --- | --- | --- | --- | --- | --- | --- |
| `Site01_final_adj_5mpp_surf.tif` — Connecting Ridge high-detail candidate | Float32 GeoTIFF DEM; product filename says adjusted surface; no formal version stated | Site01 local raster, 3,200 × 3,200 at 5 m/pixel; projected bounds from GeoTIFF tags: X `[-19000, -3000]` m, Y `[-20000, -4000]` m | Surface Z in metres; reference radius/vertical datum not stated | Product metadata: south polar stereographic X/Y metres, MOON_ME / DE421. GeoTIFF CRS keys are user-defined/unnamed. NoData tag: `nan`. | 40,980,810 bytes (HEAD and 8 KiB range verified) | [Product 78](https://pgda.gsfc.nasa.gov/products/78); [GeoTIFF](https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/Site01/Site01_final_adj_5mpp_surf.tif) |
| `LM7_final_adj_5mpp_surf.tif` — Faustini Rim A high-detail candidate | Float32 GeoTIFF DEM; adjusted surface; no formal version stated | LM7 local raster, 4,000 × 4,000 at 5 m/pixel; X `[54000, 74000]` m, Y `[-10000, 10000]` m from GeoTIFF tags | Surface Z in metres; reference radius/vertical datum not stated | Product metadata: south polar stereographic X/Y metres, MOON_ME / DE421. GeoTIFF CRS keys are user-defined/unnamed. NoData tag: `nan`. | 64,033,675 bytes (HEAD and 8 KiB range verified) | [Product 78](https://pgda.gsfc.nasa.gov/products/78); [GeoTIFF](https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/LM7/LM7_final_adj_5mpp_surf.tif) |
| `Site07_final_adj_5mpp_surf.tif` — Peak near Shackleton high-detail candidate | Float32 GeoTIFF DEM; adjusted surface; no formal version stated | Site07 local raster, 3,200 × 3,200 at 5 m/pixel; X `[22000, 38000]` m, Y `[-28000, -12000]` m from GeoTIFF tags | Surface Z in metres; reference radius/vertical datum not stated | Product metadata: south polar stereographic X/Y metres, MOON_ME / DE421. GeoTIFF CRS keys are user-defined/unnamed. NoData tag: `nan`. | 40,980,808 bytes (HEAD and 8 KiB range verified) | [Product 78](https://pgda.gsfc.nasa.gov/products/78); [GeoTIFF](https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/Site07/Site07_final_adj_5mpp_surf.tif) |
| `LDEM_80S_20MPP_ADJ.TIF` — regional coverage for all three candidates and the pole | Float32 Cloud Optimized GeoTIFF DEM; `ADJ` is the filename processing stem, no semantic version stated | 80°S–90°S cap, explicitly including the pole; 20 m/pixel; 30,400 × 30,400 header dimensions | Surface Z in metres; reference radius/vertical datum not stated | South polar stereographic X/Y metres, MOON_ME / JPL DE421 per Product 90. GeoTIFF NoData tag: `nan`. | 2,696,082,051 bytes (about 2.51 GiB; listed as 2.6G by PGDA) | [Product 90](https://pgda.gsfc.nasa.gov/products/90); [GeoTIFF](https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LDEM_80S_20MPP_ADJ.TIF) |

The Product 78 site rasters are local RoIs and should not stand in for a
pole-spanning coverage product. The Product 90 regional LDEM is the coverage
candidate for `Shackleton Connecting Ridge`, `Faustini Rim A`, and `Peak near
Shackleton`; the three 5 m files are optional local detail after registration
and vertical-reference decisions. Product 78's GeoTIFF tags do not encode a
usable named CRS (their citation strings say `unknown`/`unnamed`); the bounded
observations are saved in
[`pgda_dem_header_observations.json`](../../contracts/reference/maps/pgda_dem_header_observations.json).
The PGDA page
documents their intended south-polar stereographic, MOON_ME/DE421 coordinates.
Use the documented CRS family and frame as provenance, but do not infer a
numeric CRS code, reference radius, or vertical datum from the files.

## Proposed source assignment and coordinate handling

- **Rendered global lunar basemap:** Moon Trek `LRO_WAC_Mosaic_Global_303ppd_v02` (JPEG WMTS).
- **Rendered south-pole context:** LROC `luna_wac_roi_south_summer` (WMS, request PNG). The Moon Trek south-pole illumination image can be an optional overlay only after its CRS/units are resolved.
- **Numerical elevation / terrain coverage:** PGDA Product 90 adjusted 20 m/pixel LDEM for continuous coverage through the pole. Product 78 Site01, LM7, and Site07 5 m LDEMs are higher-resolution local candidates, but not a substitute for a pole-covering dataset.
- **Attribution:** retain NASA/GSFC/ASU LROC / LOLA product attribution and cited source links in map/terrain metadata. Imagery, illumination overlays, hillshades, and colorized images are never elevation grids.

API v1 accepts latitude in degrees and positive-east longitude in `[-180, 360)`;
its output longitude is normalized to `[-180, 180)` by
`((longitude + 180) % 360) - 180`. Retain the advertised lunar CRS IDs (`104903`
and `IAU2000:30100`), not Earth `EPSG:4326`. WMTS global-map coordinates are
angular degrees; LROC WMS geographic extents are also in degrees. WMS 1.1.1 BBOX
values must follow the registered layer CRS. The provider GeoTIFFs use projected
metre coordinates in a lunar frame. Do not convert site latitude/longitude to
polar X/Y or convert model Z to the API's `elevation_m` until the project agrees
the lunar body-fixed frame, radius, longitude origin/pole convention, and
vertical reference. Product 78's generic unknown CRS tags are not a coordinate
transformation.

## Unresolved results and access limitations

1. Moon Trek's south-pole WMTS endpoint and PNG tile are live and usable as an
   image, but its declared CRS `EPSG::0` and coordinate units are unresolved.
   It is intentionally absent from the API catalog.
2. LROC's WMS capabilities advertise `[-180, -90, 180, 90]` for the polar WAC
   layer, which is not a tight footprint. Its layer abstract provides the
   approximate 45°-from-pole context; obtain a precise footprint from provider
   metadata before coverage decisions at a site boundary.
3. The exact vertical datum/reference radius for the PGDA elevations was not
   stated in the metadata inspected. Float32 values are metres and NoData is
   `nan`, but a numeric lunar shape/radius is still required to relate those
   heights to the API surface elevation and physical horizon model.
4. Product 78 datasets are site-specific, and their undefined GeoTIFF CRS
   citations prevent canonical coordinate transformation despite the PGDA
   product page's south-polar stereographic / MOON_ME DE421 description.
5. QuickMap deep links to the candidate views remain unavailable because the
   official link format is created by the application and the browser bridge
   could not be used. The verified app URL and UI search names are provided above.
6. No terrain file was downloaded in full. Site raster HEAD requests, 8 KiB
   metadata ranges, and the Product 90 8 KiB range returned HTTP 200/206 and
   exposed file size and TIFF metadata. No provider failures were hidden; all
   successful and incomplete items are listed above.

## Reproduction

From repository root with Python 3 and network access to the official providers:

```powershell
python backend/tools/probe_maps.py --timeout 12 --snapshot-dir contracts/reference/maps --terrain-metadata --output contracts/reference/maps/live_probe_report.json
Push-Location backend
python -m unittest discover -s tests/probes -v
Pop-Location
```

The live probe disables ambient proxy settings, restricts HTTPS hosts, verifies
TLS normally, caps each response at 4 MiB, and accepts a configurable timeout from
0 (exclusive) to 60 seconds. It fetches only capabilities XML and one tile per
WMTS source. Terrain checks issue HEAD plus exact byte-range requests: 64 KiB for
each local site raster and 8 KiB for the regional product. The response must be
HTTP 206 with a matching `Content-Range`; no raster is downloaded in full.
