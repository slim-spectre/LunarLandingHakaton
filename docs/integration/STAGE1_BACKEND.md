# Stage 1 backend API and infrastructure handoff

Implemented and verified on 2026-11-14 in the nested repository
C:/Users/Admin/NASAProject/LunarLandingHakaton/LunarLandingHakaton, branch Yaroslav.
Initial worktree was clean. No commits, push, merge or deployment were performed.

## Implemented behavior

The default API registers these product routes under /api/v1:

| Route | Behavior |
| --- | --- |
| GET /health | Existing real PostgreSQL health check |
| GET /sites | PostgreSQL catalog, category filter, positive limit, nonnegative offset |
| GET /sites/{site_id} | One catalog record or SITE_NOT_FOUND |
| GET /resources/csa | Real official feed, persistent fresh/cached/stale cache |
| POST /ephemeris/now | Validate and resolve input, persist a queued job, always 202 on acceptance |
| GET /jobs/{job_id} | Persisted now job state, timestamps and structured error |
| GET /jobs/{job_id}/result | Result, JOB_NOT_READY, JOB_FAILED, JOB_NOT_FOUND or JOB_EXPIRED |

Timeline, comparison and physical terrain occlusion are not implemented. A terrain
observation request returns 422 TERRAIN_UNAVAILABLE without changing its mode.
Unknown fields and mixed site selection forms are rejected. Requests use the agreed
common error envelope and server-generated request IDs. CORS permits configured
origins and GET/POST, disables credentials, and exposes X-Request-ID.

Raw submitted JSON is stored separately from normalized/resolved inputs. UTC
normalization preserves the exact fractional timestamp in the scientific cache key.
The current astronomy service supports whole-second observations; a changed instant
is an explicit failed job, never a silently rounded successful result.

## Catalog provenance and geometric reference

Migration 0001_stage1 creates and seeds sites plus the observation_jobs,
observation_cache and resource_cache tables. It adds queue/lease/expiry indexes
and database constraints. It does not rewrite existing application tables.

The six Apollo lunar-module coordinates come from the official
[NASA landing-site table](https://nssdc.gsfc.nasa.gov/planetary/lunar/lunar_sites.html),
which identifies DE421 Mean Earth/Polar Axis coordinates. Stable IDs are apollo-11,
apollo-12, apollo-14, apollo-15, apollo-16 and apollo-17.

The other two IDs are shackleton-connecting-ridge and faustini-rim-a. Their points
are explicitly supplied project reference coordinates from API v1 examples, not
new NASA measurements or officially selected landing positions. The official
[PGDA study-region source](https://pgda.gsfc.nasa.gov/products/78) documents the
named regions. Their API descriptions make that distinction. All site-specific
QuickMap URLs and physical terrain-region references remain null until verified.
No static illumination/communication percentages are attached to catalog entries.

Geometric surface_elevation_m=0 is the origin of the Horizons reference surface,
not a DEM measurement. observer_height_m is passed unchanged to Denys's agreed
service, which performs the provider unit conversion. No lunar radius, physical
terrain height, angle, ENU vector or visibility flag is independently calculated
by this infrastructure layer. The exact terrain frame/datum remains a joint
astronomy/terrain decision for later integration.

## Worker, durability and recovery

Start the API and worker as separate processes against the same DATABASE_URL.
The API only persists submissions; it never schedules an untracked HTTP background
task. Restarting the API does not erase queued or running jobs.

The worker claims queued jobs using SELECT FOR UPDATE SKIP LOCKED, records a new
lease token and running state, commits, then executes outside the transaction.
A PostgreSQL advisory slot serializes provider work across cooperating workers.
Run one worker process per database; extra instances must use the same slot.
The astronomy service queries Sun and Earth sequentially. The adapter configures
at most one provider retry per body; the queue does not add another retry layer.

The production executor runs in a supervised child process with a hard 120-second
wall-clock limit by default. The lease is the configured limit plus 30 seconds.
The child is terminated and joined on timeout. An expired running lease is requeued
on the next poll. Completion requires the current running state, matching lease
token and unexpired lease, preventing a stale executor from overwriting a recovered
attempt. Provider calls can repeat after a crash: execution is at least once, while
result publication is fenced. This is not a claim of exactly-once network calls.

Deploy the worker under a supervisor that terminates the complete process group
on an abrupt failure. Allow at least 150 seconds for graceful shutdown with the
default execution limit. No deployment configuration was supplied or deployed.
SIGINT/SIGTERM stops further claims after the active attempt finishes. Idle polling
is once per second. Database failures leave jobs durable for a subsequent poll.

Successful results are available for at least seven days after completion; the
configuration cannot lower that retention. Expired result reads return 410 even
before maintenance clears the payload. At most 100 expired payloads and 100 expired
observation cache rows are cleared per poll. Job metadata remains available.
Failed jobs preserve their structured error and return 409 JOB_FAILED on result reads.

## Cache and source semantics

Observation cache keys include normalized latitude/longitude, exact UTC target time,
observer height, visibility margin, horizon mode, model version and reference surface
height. The default TTL is 3600 seconds. Names/catalog labels are rebound to each
job's resolved site instead of leaking a previous scenario name from cached output.
Cache hits still create a queued job and return 202. The worker marks the result
cached without changing scientific source retrieval or original generation times.
Cache hits do not extend the scientific cache TTL.

MODEL_VERSION=geometric-now-v1 identifies this calculation pipeline. It is not an
invented provider ephemeris version. Source versions are returned by Denys's service;
the approved one-line provenance fix preserves null when a version is unreported.
Bump MODEL_VERSION when calculation/reference settings change.

CSA uses https://www.asc-csa.gc.ca/rss/default_eng.xml, previously discovered from
the official Moon Exploration portal. It supports Atom and RSS, uses verified
TLS 1.2, does not follow redirects, limits the response to 2 MiB and uses finite
network and read budgets. Only title, link, summary/description, publication time,
ID and topic matches are retained. Full article content is not fetched or republished.

Default CSA fresh-cache TTL is 300 seconds and maximum usable stale age is 86400
seconds. A successful refresh returns fresh; a TTL hit returns cached; a refresh
failure with a usable older cache returns stale. Failure without a usable cache
returns 503 CSA_UNAVAILABLE. An accessible feed with no Moon-related entries is a
valid empty response. No development feed or observation fixture is enabled by a
production flag. Controlled executors/fetchers exist only as injected test dependencies.

Concurrent cold-cache requests share the existing PostgreSQL provider lock. A
request that finds a refresh in progress and has no usable cache releases its
database connection, then polls the cache every 100 ms for at most 15 seconds.
It returns cached once the first request publishes the data, without starting a
duplicate upstream fetch. Usable stale data is returned immediately. If no usable
cache appears before the deadline, the common 503 CSA_UNAVAILABLE error remains.

Optional environment settings: OBSERVATION_TIMEOUT_SECONDS (1..300, default 120),
OBSERVATION_CACHE_SECONDS (default 3600), RESULT_RETENTION_DAYS (minimum/default 7),
CSA_CACHE_SECONDS (default 300), CSA_STALE_SECONDS (default 86400), and the existing
HORIZONS_TIMEOUT_SECONDS (positive, at most 30, default 15). Stale retention must
not be shorter than the CSA cache TTL. Existing DATABASE_URL/CORS_ORIGINS apply.

## Local reproduction

Keep the existing local .env, or copy .env.example and replace its placeholders.
The database credentials/port in DATABASE_URL must match POSTGRES_* values.
From repository root:

```powershell
docker compose up -d --wait postgres
cd backend
python -m uv sync --locked --python 3.12
python -m uv run --locked alembic upgrade head
python -m uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a separate terminal, from backend:

```powershell
python -m uv run --locked python -m app.worker
```

Without that worker, accepted jobs correctly remain queued. Use --once to process
at most one queued job and exit. Observe its actual success/failure through the job
API; process completion alone does not mean a calculation succeeded.

In another PowerShell terminal:

```powershell
Invoke-RestMethod 'http://localhost:8000/api/v1/sites?category=artemis&limit=10'
Invoke-RestMethod 'http://localhost:8000/api/v1/resources/csa?limit=10'
$payload = '{"site":{"site_id":"faustini-rim-a"},"target_time":"2027-07-15T12:00:00Z","horizon_mode":"geometric"}'
$job = Invoke-RestMethod -Method Post -Uri 'http://localhost:8000/api/v1/ephemeris/now' -ContentType 'application/json' -Body $payload
Invoke-RestMethod ('http://localhost:8000' + $job.status_url)
Invoke-RestMethod ('http://localhost:8000' + $job.result_url)
```

Poll status every two seconds and stop on succeeded/failed. A result read before
completion returns 409 JOB_NOT_READY. Repeat the same submission to observe another
202 and a cached result after the worker processes it.

From backend, deterministic tests are `python -m uv run --locked pytest -m "not integration"`.
For all database tests, set TEST_DATABASE_URL to a dedicated test PostgreSQL database
and run `python -m uv run --locked pytest`. These tests run versioned migrations.
Do not point that variable at a production database. The opt-in provider test remains
separate; the live smoke below was run explicitly outside the deterministic suite.

## Map and frontend integration

Bohdan's Stage 1 router/handoff was absent both locally and in the inspected Bogdan
branch (22a3b0a). No map adapter was copied or rewritten. Supply the exported
APIRouter to create_app(map_router=exported_router). It should have its own /map
or /terrain prefix, without /api/v1; the application adds /api/v1 once. Register
that actual export in the default app construction when the handoff is available.
Tests prove that the registration mechanism mounts an injected router correctly;
that test router is not a production map implementation.

Sasha/Slavik can use the six new operations in the canonical OpenAPI contract and
regenerated schema.ts. Build a catalog selector or custom coordinates, submit a
geometric now job, poll every two seconds and then fetch its result. Treat resource
503 errors by their code; they are not always database failures. Physical terrain,
timelines and comparison controls should remain disabled. The current frontend
shell was not modified by this backend task.

## Files changed

New files:

- backend/app/core/problems.py (shared errors moved here plus APIProblem).
- backend/app/requests.py, results.py, routes.py, storage.py, resources.py, worker.py.
- backend/migrations/versions/0001_stage1.py.
- backend/tests/conftest.py, test_stage1_jobs.py, test_stage1_csa.py, test_stage1_postgres.py.
- docs/integration/STAGE1_BACKEND.md (this document).

Updated files:

- backend/app/main.py, backend/app/core/config.py, backend/migrations/env.py,
  backend/alembic.ini.
- backend/app/astronomy/horizons.py and backend/tests/test_horizons_provider.py:
  only the owner-approved provenance fallback removal and its regression test.
- backend/tests/test_health.py and test_contract.py: Stage 1 route-boundary assertions.
- contracts/openapi.v1.yaml, docs/API_V1.md, docs/CONTRACT_DECISIONS.md,
  docs/sources/csa.md and README.md.
- frontend/src/api/generated/schema.ts: generated synchronization explicitly approved
  by the owner; no frontend logic changed.
- .github/workflows/ci.yaml: renamed the workflow to Project checks; existing checks
  already discover the new tests and provide PostgreSQL.

No new dependency or lockfile change was needed. The existing .env was not edited.

## Actual checks and live observations

| Check | Actual outcome |
| --- | --- |
| Full pytest on isolated PostgreSQL, final version | 252 passed, 1 intentionally skipped live-provider test, one upstream AnyIO deprecation warning; 6.65 seconds. All three database integration tests ran. |
| Ruff check and format | Passed for 33 Python files. |
| compileall backend/app | Passed. |
| alembic upgrade head --sql | Offline migration SQL generated successfully. |
| Fresh database alembic upgrade head and alembic check | Passed; no new upgrade operations detected. |
| npm run generate:api; npm run check:api | Passed on Node 22.13.0/npm 10.9.2. |
| Frontend lint, tests, build | Passed; 50 tests, successful production build. Upstream Three.js deprecation and bundler timing notices did not fail checks. |
| Live now submission using catalog faustini-rim-a | HTTP 202, queued; initial result read was 409; separate real worker completed succeeded; result read was 200. |
| Repeat live submission | HTTP 202 again; worker returned cached with identical scientific source retrieval times. |
| First live CSA route check | HTTP 503 CSA_UNAVAILABLE without cache. No response was fabricated; the original underlying transport error was not retained by that first attempt. |
| Subsequent direct CSA adapter check | Successful verified fetch with zero matching entries. |
| Live CSA route on a fresh isolated database | HTTP 200, items=[], fresh, fetched_at=2026-11-14T13:28:37.391057Z. A new API app instance read the persisted cache and returned cached with the same fetched_at. |

The live ephemeris request referred to 2027-07-15T12:00:00Z. Its two source retrieval
times were 2026-11-14T13:24:17Z and 2026-11-14T13:24:18Z, demonstrating that observation
time and scientific retrieval time are distinct. Horizons reported DE441. The
provider-derived model output, not measured lunar conditions, was:

- Sun: azimuth 322.365998 degrees, elevation 1.490814 degrees, visible=true.
- Earth: azimuth 288.064862 degrees, elevation -4.947411 degrees, visible=false.
- is_golden_window=false, supplied by Denys's service, without an interval claim.

Controlled tests and the live smoke used separate temporary databases to prevent
fixture cache contamination. Temporary verification containers/networks/volumes
were removed. No persistent API/worker server or production job was started.
Initial test failures involving union error classification and the raw-submission
test setup were corrected; existing expected scientific fixture values were not
changed to make tests pass.

## Open integration items

1. Closed by final Stage 1 integration: Bohdan's real map router is registered by
   default without duplicating its API prefix. See STAGE1_COMPLETION.md.
2. Denys's service currently emits whole-second observations. Subsecond requests are
   preserved and fail explicitly on time mismatch. Supporting them requires an
   astronomy-service change; the infrastructure does not round them into fake success.
3. Exact lunar terrain frame/datum and verified site-specific QuickMap links remain
   unresolved; no physical terrain data or unknown links have been invented.
4. GitHub Actions itself was not rerun and no deployment was performed. Browser UI
   integration was subsequently verified; see STAGE1_COMPLETION.md for current results.
