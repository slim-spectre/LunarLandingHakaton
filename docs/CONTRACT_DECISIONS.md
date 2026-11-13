# API v1 schema decisions and remaining review items

The full owner-supplied specification received on 2026-11-13 supersedes the initial
placeholder. Product rules are preserved in API_V1.md and OpenAPI. Only health is
implemented at Stage 0. The choices below make otherwise unspecified wire details
explicit; scientific details marked pending require owner agreement before their
future implementation.

## Explicit schema choices

1. Coordinate site name is optional because the supplied timeline example omits
   it. site_id and coordinates are mutually exclusive; unknown fields are rejected.
   Resolved site uses site_id (null for custom sites), name, latitude, longitude,
   surface_elevation_m and observer_height_m. Surface height is the model's base
   elevation, not observer elevation. Default naming of unnamed custom sites is
   pending; fixture names do not define a production naming rule.
2. Treat duration_days as an integer in [1,30]. The source gives a range but does
   not explicitly discuss fractional days; this interpretation requires review.
   limit is a positive integer; offset is a nonnegative integer. No catalog limit
   maximum is invented. CSA limit has its specified maximum 30.
3. Layer list is {items:[Layer]}; CSA list is {items:[CSAItem],fetched_at,data_status}.
   The layer URL template field is access_url_template. WMS bbox is a comma-separated
   min_x,min_y,max_x,max_y string in layer coordinates, with positive extent.
   WMTS matrix is a nonempty identifier; row and col are nonnegative integers.
   Image formats are provider-dependent; OpenAPI advertises PNG and JPEG.
   Confirm other formats before registering providers.
4. Heightmap origin is {latitude,longitude,elevation_m}. Origin elevation is in
   the source model's vertical reference. Spacing is positive and dimensions are
   positive integers. elevation_m array length must equal width*height. The exact
   lunar body-fixed frame, reference shape/radius, vertical datum, pole convention
   and geographic origin-to-ENU conversion remain pending joint astronomy/terrain
   agreement. No Earth EPSG code or lunar radius is assumed.
5. Source fields are name,url,version,fetched_at. version is null when a source
   offers no version; fetched_at is UTC. Calculation sources are nonempty and list
   actual inputs. Horizon elevation is bounded to physically meaningful [-90,90].
   Direction vectors use squared-norm tolerance 1e-6 for fixture validation; this
   tolerance is numerical, not a scientific accuracy claim.
6. Queued jobs have null started_at/finished_at/error. Running jobs have started_at
   and null finished_at/error. Succeeded jobs have both timestamps and null error.
   Failed jobs have finished_at and an Error object; started_at can be null for a
   failure before execution. result_url remains present at every state; fetching
   it is governed by the specified HTTP statuses. Acceptance is always queued,
   including a result that may subsequently be resolved from cache.
7. Error details is always an array (possibly empty); request_id is a server-created
   UUID. Every failed response carries matching X-Request-ID for diagnostics.
   Do not trust caller-provided IDs as server identifiers. Missing fields, unknown
   fields, malformed JSON, wrong container shape and unsupported health request
   bodies are structural 400 INVALID_REQUEST errors; invalid field values are
   422 VALIDATION_ERROR. details.field is a dotted location such as body.count or
   query.lat; details.reason is a stable validation category, never raw input.
   Other HTTP errors preserve status and use HTTP_<status> unless a product code
   is specified. Unexpected server errors use 500 INTERNAL_ERROR with no internals.
   Retry-After is nonnegative delta-seconds. These unspecified code/details/header
   conventions are explicit choices, not changes to agreed product error codes.
8. The next sunset/earthset is the first sampled visible-to-invisible transition
   strictly inside the period. Do not infer a transition at the excluded end from
   a missing sample. Average solar elevation is duration-weighted; uniform v1
   sampling over integer days makes this equal to the arithmetic mean. These
   boundary/averaging details should be reviewed before calculation implementation.
9. start/target instants must be inside the supported half-open range. end_time
   can equal 2050-01-01T00:00:00Z because the final instant is excluded. Input
   timezone offsets are accepted and normalized to UTC. JSON Schema validates
   timezone syntax; semantic date bounds, interval consistency, unique labels,
   vector norms, grid size, visibility and ranking require application validation.
   OpenAPI x-invariants and descriptions record those rules; fixture tests check
   applicable invariants. They are not implemented calculation endpoints.
10. Geometric meta uses terrain_dataset_id=null; terrain meta requires the actual
    dataset ID. time_resolution_minutes is null only for now, otherwise the
    requested shared step. No automatic horizon fallback is permitted.
11. CORS remains an explicit JSON origin allowlist with credentials disabled.
    Database health uses a fresh connection with two-second connection and query
    timeouts. No domain tables or job infrastructure are implemented in Stage 0.

## Still pending

Agree the exact lunar horizontal and vertical frames with Denys and Bohdan, and
review the wire details above before implementing planned endpoints. A terrain
comparison may span several datasets while meta.terrain_dataset_id is singular;
agree its representation before implementation rather than inventing a combined ID. Live CSA
verification is now complete using the explicit TLS 1.2 option; actual Atom feed
observations are documented in sources/csa.md. The observed five entries had no
matching Moon keywords; no production CSA endpoint has been implemented.
