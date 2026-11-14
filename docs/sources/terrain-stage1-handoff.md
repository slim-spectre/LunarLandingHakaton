# Terrain dataset handoff for Stage 1

This manifest records numerical source candidates only. The map endpoints serve
rendered images; they do not expose DEM samples. Imagery availability does not
mean numerical terrain is available, and identified DEM files have not been
processed for physical calculations.

## Candidate datasets

| Area | Product and version | Footprint / resolution | Elevation reference and no-data | Download size | Expected processing | Official metadata and download |
| --- | --- | --- | --- | --- | --- | --- |
| Shackleton Connecting Ridge | PGDA Product 78, `Site01_final_adj_5mpp_surf.tif`; formal product version not stated | Site01 local raster, 3,200 × 3,200 at 5 m/pixel; header bounds X [-19000, -3000] m, Y [-20000, -4000] m | Float32 GeoTIFF; surface Z metres; no-data `nan`; PGDA documents south polar stereographic X/Y metres, MOON_ME / DE421; numeric CRS code, reference radius, and vertical datum not stated | 40,980,810 bytes (verified) | Resolve projection and vertical frame; verify ROI coverage/no-data; register source version; prepare a checked elevation window and validated horizon model. | [Product 78 metadata](https://pgda.gsfc.nasa.gov/products/78); [download](https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/Site01/Site01_final_adj_5mpp_surf.tif) |
| Faustini Rim A | PGDA Product 78, `LM7_final_adj_5mpp_surf.tif`; formal product version not stated | LM7 local raster, 4,000 × 4,000 at 5 m/pixel; header bounds X [54000, 74000] m, Y [-10000, 10000] m | Float32 GeoTIFF; surface Z metres; no-data `nan`; PGDA documents south polar stereographic X/Y metres, MOON_ME / DE421; numeric CRS code, reference radius, and vertical datum not stated | 64,033,675 bytes (verified) | Resolve projection and vertical frame; verify ROI coverage/no-data; register source version; prepare a checked elevation window and validated horizon model. | [Product 78 metadata](https://pgda.gsfc.nasa.gov/products/78); [download](https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/LM7/LM7_final_adj_5mpp_surf.tif) |
| Peak near Shackleton | PGDA Product 78, `Site07_final_adj_5mpp_surf.tif`; formal product version not stated | Site07 local raster, 3,200 × 3,200 at 5 m/pixel; header bounds X [22000, 38000] m, Y [-28000, -12000] m | Float32 GeoTIFF; surface Z metres; no-data `nan`; PGDA documents south polar stereographic X/Y metres, MOON_ME / DE421; numeric CRS code, reference radius, and vertical datum not stated | 40,980,808 bytes (verified) | Resolve projection and vertical frame; verify ROI coverage/no-data; register source version; prepare a checked elevation window and validated horizon model. | [Product 78 metadata](https://pgda.gsfc.nasa.gov/products/78); [download](https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/Site07/Site07_final_adj_5mpp_surf.tif) |

For continuous south-pole coverage, the regional candidate is PGDA Product 90,
`LDEM_80S_20MPP_ADJ.TIF` (formal version not stated): Float32 Cloud Optimized
GeoTIFF, 30,400 × 30,400, 20 m/pixel, documented from 80°S through the south
pole to 90°S. It uses south polar stereographic X/Y metres in MOON_ME / JPL DE421;
surface elevations are metres and the observed no-data tag is `nan`. The
reference radius and vertical datum are not stated. The file is 2,696,082,051
bytes; only its bounded header range was read, not the complete raster.
[Product 90 metadata](https://pgda.gsfc.nasa.gov/products/90) ·
[download](https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LDEM_80S_20MPP_ADJ.TIF)

The regional grid requires the same frame and no-data validation, plus COG-aware
window extraction for the areas of interest and validation that the requested
window includes sufficient surrounding terrain for a horizon model.

The local Product 78 rasters are high-resolution candidates around their named
sites; they do not replace the regional pole-covering product. The Product 90
footprint includes the pole and provides the regional coverage candidate for all
three areas. Header observations and exact byte sizes are recorded in
[`pgda_dem_header_observations.json`](../../contracts/reference/maps/pgda_dem_header_observations.json).

## Readiness and required processing

| Data type | Status | Meaning |
| --- | --- | --- |
| Rendered imagery | Available | Moon Trek global WAC tiles and LROC WMS mosaics are registered for map display. |
| Numerical terrain source | Identified | PGDA Product 78 local grids and Product 90 regional pole grid are documented; full files have not been staged. |
| Terrain processed for physical calculations | Not available | No validated, registered DEM/horizon model exists. Do not report terrain availability for observation calculations. |

Before a later terrain stage can produce physical horizons, it must establish the
numeric lunar CRS and transform for each raster, settle the vertical datum and
reference radius, confirm site coverage and no-data handling, register a
traceable dataset version, and validate the resulting horizon model against
source elevations. Do not synthesize height values from a basemap, hillshade, or
colorized image.
