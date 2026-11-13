# API v1: agreed human-readable specification

English translation of the API specification supplied by the project owner on
2026-11-13 (sections 5–12). This supersedes the earlier placeholder. Schema choices
and remaining ambiguities are recorded in CONTRACT_DECISIONS.md. OpenAPI is in
contracts/openapi.v1.yaml. All JSON examples in contracts/examples are synthetic
development/test fixtures; their numeric values are not measured NASA results.

## 5. General rules

Base path: `/api/v1`. Format: JSON, except map layer images.

Times use ISO 8601 with an explicit timezone. Reject timezone-free dates. Return
UTC with a `Z` suffix. Supported instants are in
`[2000-01-01T00:00:00Z, 2050-01-01T00:00:00Z)`. The entire calculated period must
fit inside this range, not only its start.

Coordinates: latitude is in [-90,90]. Input longitude is in [-180,360), positive
east. Normalize output longitude to [-180,180), using
`((longitude + 180) % 360) - 180`. Catalog and terrain must use the agreed lunar
coordinate system; do not assume an Earth CRS.

Units: angles in degrees, heights in metres, window duration in hours, time step
in minutes, percentages in [0,100], directions as unit vectors without a display
distance multiplier.

| Parameter | v1 limit |
| --- | --- |
| Timeline duration | 1–30 days |
| step_minutes | 15, 30, 60, 120, 180, 360 |
| Comparison scenarios | 2–6 |
| observer_height_m | 0–20, default 2 |
| visibility_margin_deg | 0–5, default 0 |

All routes reject unknown request fields. Do not use aliases `lat`, `lon` or
`step_hours`.

## 6. Site selection and horizon

Select by catalog with `{"site_id":"shackleton-connecting-ridge"}`, or by
coordinates with `{"name":"Custom site","latitude":-89.44,"longitude":222.1}`.
Name is optional for coordinate selection, as shown by the supplied timeline
request. Mixing site_id with custom coordinates is forbidden.

`horizon_mode` is required for calculations:

- `geometric`: local horizon plane, threshold 0 degrees, without terrain obstacles.
- `terrain`: horizon from prepared elevation data. If suitable coverage is absent,
  return TERRAIN_UNAVAILABLE. Never silently fall back to geometric mode.

observer_height_m is above the selected model surface. The backend determines the
base surface height and returns the actual height used.

Visibility uses strict inequalities:

```text
sun_visible = sun.elevation_deg > sun.horizon_elevation_deg + visibility_margin_deg
earth_visible = earth.elevation_deg > earth.horizon_elevation_deg + visibility_margin_deg
is_golden_window = sun_visible AND earth_visible
```

Use the center of the Sun's disk and the center of Earth. Do not apply atmospheric
refraction on the Moon. Earth visibility describes geometric direction only;
radio power, specific ground stations and bandwidth are outside v1. Sun visibility
means possible direct illumination; do not return watts without a panel model.

## 7. Catalog, maps, terrain and CSA

Paths below are relative to /api/v1. All listed successful GET responses are 200.

| Route | Parameters | Result |
| --- | --- | --- |
| GET /health | None | API and real database health |
| GET /sites | Optional category, limit=50, offset=0 | Paginated catalog |
| GET /sites/{site_id} | Site ID | One site |
| GET /map/layers | None | Available layers |
| GET /map/layers/{layer_id} | Layer ID | Metadata and access parameters |
| GET /map/layers/{layer_id}/tiles/{matrix}/{row}/{col} | WMTS indices | Image |
| GET /map/layers/{layer_id}/image | bbox, width, height | WMS image |
| GET /terrain/coverage | latitude, longitude | Terrain availability |
| GET /terrain/regions/{region_id}/heightmap | Region ID | Numeric local-scene grid |
| GET /resources/csa | limit=10, maximum 30 | Moon-related CSA materials |

WMS/WMTS routes accept only registered layer IDs. Arbitrary third-party URLs are
not accepted. Image CRS is defined by the registered layer. Maximum width and
height are 1024 each.

A site contains id, name, description (strings), category (artemis, apollo, clps,
international), numeric latitude and normalized longitude, source_url,
quickmap_url (string or null), terrain_region_id (string or null).
The catalog list is `{items: [], total: 27, limit: 50, offset: 0}`.

Layer metadata contains id, name, provider (moon_trek or lroc), service_type (wmts
or wms), actual lunar projection crs_id, coordinate_units (degrees or metres),
extent [min_x,min_y,max_x,max_y] in that projection, attribution, source_url,
tile_matrix_set (WMTS string or null for WMS), and our API access URL template.

Terrain coverage contains available, normalized latitude and longitude,
region_id, dataset_id, resolution_m, source_url (each value or null), and reason
(null, outside_coverage or no_data).

A terrain grid contains region_id, dataset_id, model_version, frame=`local_enu`,
geographic origin, east_min_m, north_min_m, spacing_m, width, height, elevation_m,
source_url and attribution. There are exactly width*height values. Index is
row*width+column; rows increase north and columns increase east. elevation_m is
the up component relative to the local scene origin. This is a display grid.
Physical horizons must use source elevation data, its coordinate system and
surface curvature.

Each CSA material contains id, title, summary, url, published_at and topics. The
response also includes fetched_at and data_status (fresh, cached or stale).
An inaccessible feed without a usable cache returns 503. An accessible feed
without matching materials returns an empty list.

## 8. Asynchronous calculation jobs

POST /ephemeris/now, POST /ephemeris/timeline and POST /ephemeris/compare all
return 202 Accepted. They do not wait for the Horizons calculation to finish.
The acceptance object contains job_id, kind, status=`queued`, status_url and
result_url. kind is now, timeline or comparison (the compare route uses comparison).
URLs point to /api/v1/jobs/{job_id} and /api/v1/jobs/{job_id}/result.

GET /jobs/{job_id} returns job_id, kind, status (queued, running, succeeded,
failed), created_at, started_at, finished_at, result_url and error (object or
null). Poll every two seconds and stop after succeeded or failed.

GET /jobs/{job_id}/result returns:

- 200: completed result, with shape determined by kind.
- 409 JOB_NOT_READY: queued or running.
- 409 JOB_FAILED: execution failed.
- 404 JOB_NOT_FOUND: unknown ID.
- 410 JOB_EXPIRED: result removed.

Keep completed results for at least seven days. Identical scenarios may use a
cache, but keys must include coordinates, time, parameters, model version and
terrain dataset. Errors after acceptance are stored as status=failed with the
same error object used by the common error envelope.

## 9. Single-instant calculation

POST /ephemeris/now requires site, target_time and horizon_mode. Optional
observer_height_m and visibility_margin_deg use the defaults above.

```json
{"site":{"site_id":"shackleton-connecting-ridge"},"target_time":"2027-07-15T12:00:00Z","horizon_mode":"geometric","observer_height_m":2,"visibility_margin_deg":0}
```

The job result contains normalized site and heights used, point and meta.
A point contains timestamp, sun, earth and is_golden_window. Each body has
azimuth_deg in [0,360), clockwise from north; elevation_deg in [-90,90];
horizon_elevation_deg in that direction; visible according to section 6; and
direction_enu={east,north,up}, a unit vector.

Three.js mapping: scene.x=east, scene.y=up, scene.z=-north. Frontend chooses scale
and marker distance; it preserves the backend direction.

## 10. Timeline, intervals and metrics

POST /ephemeris/timeline requires site, start_time, duration_days, step_minutes
and horizon_mode. observer_height_m and visibility_margin_deg are optional.

```json
{"site":{"latitude":-89.44,"longitude":222.1},"start_time":"2027-07-15T12:00:00Z","duration_days":14,"step_minutes":120,"horizon_mode":"terrain","observer_height_m":2,"visibility_margin_deg":0}
```

Result fields: site, start_time, end_time, step_minutes, total_samples, points,
sunlight_windows, earth_visibility_windows, golden_windows, summary and meta.
Each window has start_time, end_time and duration_hours.

The period is [start_time,end_time); do not add a point at end_time. Thirty days
at 60 minutes gives 720 points; fourteen days at 120 minutes gives 168. A favorable
point represents the interval until the next point or period end. Merge adjacent
favorable intervals; an unfavorable interval separates windows. Boundaries have
time-step accuracy, which the UI must display. Incomplete provider data fails the
job; never turn missing data into visibility.

Summary contains sunlit_hours, sunlit_pct, earth_visible_hours,
earth_visible_pct, golden_hours, golden_pct, longest_golden_window_hours,
average_sun_elevation_deg, next_sunset_at and next_earthset_at. The next events
are the earliest visible-to-invisible transitions in the calculated period.
They are null when no such event exists within that period; null does not mean
that the event never occurs. Percentages are based on interval duration; the
frontend must not recalculate them with another formula.

## 11. Comparison of sites and dates

POST /ephemeris/compare takes scenarios (2–6), shared duration_days, step_minutes,
horizon_mode and optional observer_height_m and visibility_margin_deg. Each
scenario requires a unique label, site and start_time. Sites and dates may vary.
See contracts/examples/comparison-request.json for a complete development fixture.

Result fields: ranking_version=`v1`, ranked_scenarios, recommended_label,
recommendation_reason and meta. Each ranked scenario has rank, label, site,
start_time, end_time, score and the same summary schema as timeline. Do not
include full point arrays. For details, request a timeline for that scenario.

```text
score = 0.40 * sunlit_pct + 0.30 * earth_visible_pct + 0.30 * golden_pct
```

This is a product comparison score, not an official NASA criterion. Sort by
higher unrounded score, then longer longest_golden_window_hours, then original
request order. Display component metrics alongside the score. Any formula change
requires a new ranking_version.

## 12. Result metadata and errors

Every calculation result has meta: model_version, generated_at,
data_status (fresh or cached), horizon_mode, time_resolution_minutes (timeline
step or null for now), terrain_dataset_id (string or null), and sources. Each
source has name, URL, version and retrieval time. List only actually used sources;
CSA is educational, Moon Trek provides map layers, and astronomy results cite
their actual data inputs rather than automatically listing all providers.

The common error shape is:

```json
{"error":{"code":"TERRAIN_UNAVAILABLE","message":"Terrain data is unavailable for the requested location.","details":[{"field":"site","reason":"outside_coverage"}],"request_id":"a706df04-b7c9-49c0-8eea-b53c71f86fe8"}}
```

| HTTP | Meaning |
| --- | --- |
| 400 | Invalid request structure |
| 404 | Unknown site, layer, region or job |
| 409 | Job not ready or job failed |
| 410 | Job result expired |
| 422 | Invalid values, dates, limits or requested terrain unavailable |
| 429 | Rate limit exceeded; include Retry-After |
| 502 | Invalid external provider response |
| 503 | Required service unavailable without a usable cache |

Never replace a failure with fabricated angles or windows. Failed jobs store the
same error object (code, message, details, request_id), without a second envelope.

## Stage 0 runtime boundary

Only GET /api/v1/health is implemented. Its success response is
`{status:"healthy",service:"lunar-navigator-api",timestamp:"<UTC timestamp ending in Z>",database:"ok"}`.
A real bounded SELECT 1 checks PostgreSQL. Database failure returns 503 with
DATABASE_UNAVAILABLE and the complete common error envelope. Planned operations
are documented in OpenAPI but remain absent from the running server.
