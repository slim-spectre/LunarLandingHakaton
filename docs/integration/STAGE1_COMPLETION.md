# Stage 1 integration completion

Reviewed and integrated on 2026-11-14 in branch Yaroslav, starting from a clean
worktree at b01649c. This report supersedes historical map-registration and
schematic-only limitations in the earlier handoffs. No commits, push, merge or
deployment were performed. No dependencies, lockfiles or canonical API fields changed.

## Implemented scope

| Area | Stage 1 behavior |
| --- | --- |
| Astronomy | Denys's real single-time geometric Horizons service, source provenance and returned visibility flags |
| Catalog | PostgreSQL catalog, migrations, filtering/pagination, exclusive catalog/custom selection, verified source links |
| Jobs | Durable now jobs, separate bounded worker, recovery/fencing, structured failures, retention and scientific cache |
| CSA | Official verified feed, safe parsing, fresh/cached/stale/empty/error states and bounded cold-cache contention handling |
| Map services | Default API registers Bohdan's catalog, WMTS tile and WMS image proxy routes |
| Workspace | Explicit UTC selection, validation, HTTP 202, two-second nonoverlapping polling, cancellation and stale-response protection |
| Map UI | API layer metadata, layer selection, attribution/CRS, global Moon Trek mosaic, LROC WMS, selected marker and coordinate selection |
| Scene | Full observation point, resolved site, cache status and unchanged ENU vectors; scientific HUD values come only from the API |

Timeline generation, continuous golden-window intervals, ranking/comparison and
physical terrain occlusion remain deliberately unimplemented. Geometric mode is
explicit; terrain requests fail with TERRAIN_UNAVAILABLE. Whole-second input
matches the current astronomy service. No illumination/communication percentages
are invented for static sites. Verified QuickMap links remain optional/null.

## Integration corrections

The real map router already contains /api/v1/map/layers. It is now installed by
the default application without an additional /api/v1 prefix. Tests exercise
the same factory used by uvicorn, rather than manually registering the router.
Map GET routes reject bodies and duplicate query values consistently with the
common envelope. Timeline/comparison remain absent from the runtime API.

The workspace loads layers from GET /api/v1/map/layers. Failed metadata requests
show an error and retry; they do not silently use a static operational catalog.
The standalone map's verified defaults remain compatible with its existing public
interface; production passes the loaded catalog explicitly.

For the verified Moon Trek layer, matrix 0 has two columns and one row, tile size
256x256 and top-left longitude/latitude -180,90 in the saved official capabilities.
The UI renders both columns in one SVG geographic surface. WMS images occupy
their requested geographic extent in that same surface. The SVG, marker and click
handler share the same 2:1 global frame. Click conversion accounts for letterboxing
and rejects margin clicks. Provider image errors remove incomplete imagery and
show an explicitly schematic grid with a retry action; retry does not select a site.
This is a coarse registered imagery overview, not a physical terrain model.

The scene no longer derives scientific angles or visibility from vector-only
props. The application supplies observationPoint, site and dataStatus. Direct
vectors may still orient a schematic scene, but do not produce scientific HUD
values. A returned false flag above the horizon remains false when a visibility
margin applies. The display uses "Not visible" rather than claiming the body is
necessarily below the geometric horizon.

## Changed files

- backend/app/main.py: default real map registration and prefix correction.
- backend/app/maps/router.py: common GET body and duplicate-query validation.
- backend/tests/test_health.py: actual Stage 1 runtime route set.
- backend/tests/test_map_services.py: default application integration and malformed requests.
- backend/tests/test_stage1_jobs.py: custom router fixture uses its complete API prefix.
- frontend/src/api/client.ts and api/observation.test.ts: layer catalog transport,
  metadata validation and unsupported-CRS regression.
- frontend/src/features/observation/ObservationWorkspace.tsx and App.test.tsx:
  layer loading/retry, QuickMap forwarding and complete scene props.
- frontend/src/features/map/LunarMap.tsx and LunarMap.test.tsx: complete mosaic,
  shared image/marker/click frame, regional extent and retry regressions.
- frontend/src/features/scene/LunarScene.tsx and Scene.test.tsx: API-only HUD
  values, positive-margin visibility regression and no vector-derived defaults.
- README.md and integration handoffs: current registration, scope and reproduction.

## Checks and actual results

Use Python 3.12 with the committed backend/uv.lock, and Node 22.13.0/npm 10.9.2
with the existing frontend/package-lock.json.

| Command | Result |
| --- | --- |
| uv run --locked ruff check . | Passed |
| uv run --locked ruff format --check . | Passed after applying the formatter's adjustment |
| uv run --locked pytest -m "not integration" -q | 273 passed, one opt-in live Horizons test skipped |
| uv run --locked pytest -m integration -q | Four passed against an isolated temporary PostgreSQL database |
| npm run lint | Passed |
| npm run check:api | Passed, generated types match the canonical contract |
| npm run test -- --testTimeout=10000 | 122 passed |
| npm run build | Passed, including TypeScript checks |

The original route-set test failed when real map routes were first enabled; it
was updated to include the four implemented map paths, keeping Stage 2 exclusion
assertions. The initial Ruff format check requested one layout adjustment, which
was applied. Existing scientific expectations were not changed to make tests pass.
PostgreSQL tests used a fresh temporary database and bounded IPv4 connections;
the test database was removed and no application data was replaced with fixtures.

Live checks through the default API returned:

- GET /health: 200; GET /map/layers: 200 with the three registered layers.
- Moon Trek matrix 0, row 0, columns 0 and 1: 200 image/jpeg, respectively
  49,475 and 51,335 bytes.
- LROC luna_wac_global, bbox=-180,-90,180,90, 64x32 pixels: 200 image/png,
  5,046 bytes.
- The browser rendered the real global imagery, site catalog and scene. A real
  Faustini Rim A request for 2026-11-14T16:20:29Z with a 5-degree margin succeeded
  as job e856b7ab-238e-4067-9735-a7aa0c4dd3e9. The returned Sun elevation was
  3.47075 degrees with visible=false. Both the table and scene correctly showed
  not visible. These are observed provider-model outputs, not fixture benchmarks.
- Source retrieval timestamps were 2026-11-14T16:21:17Z, distinct from the
  requested instant. The scene showed the actual observation time.
- Repeating that exact scenario returned HTTP 202 again, succeeded and returned
  data_status=cached with the same observation instant and both source retrieval
  timestamps preserved. No new scientific values were substituted.
- CSA returned a correctly labelled retained stale empty feed while its live
  source refresh failed. No replacement articles were fabricated.

## Reproduction and team integration

1. Start Docker. Keep/configure the existing ignored root .env as described in
   the root README; do not overwrite another developer's local configuration.
2. From repository root: docker compose up -d --wait postgres.
3. In backend/: uv sync --locked --python 3.12, then uv run --locked alembic upgrade head.
4. In backend/: uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8000.
5. In another backend/ terminal: uv run --locked python -m app.worker.
6. In frontend/, with Node 22.13.0: npm ci, then npm run dev. Open http://localhost:5173.
7. Select a catalog site or custom coordinates, set UTC time and margin, submit,
   then inspect job states, numerical results, scene time/flags and source metadata.
   Repeat the same scenario to exercise cached results. Switch map layers and
   select coordinates inside the image; clicks in letterbox margins are ignored.
8. Run the checks above from their respective backend/ and frontend/ directories.
   For integration tests, explicitly set TEST_DATABASE_URL to a dedicated fresh
   test database. On Windows use python -m uv if uv is not on PATH; prefer
   127.0.0.1 and a connect_timeout=2 query option for the test connection.

All work is local. Teammates need these changes together with the already merged
astronomy, map services, scene, backend infrastructure and frontend workspace.
There is no additional migration, schema generation or dependency upgrade for
this completion patch. Stop API, worker and Vite with Ctrl+C and PostgreSQL with
docker compose stop postgres; retain its volume.

## Operational limitations

Live providers can become unavailable; proper error/stale states are still
required. No perpetual source availability or independent scientific certification
is claimed. GitHub CI for these uncommitted changes cannot run until the team pushes
them. A full mobile/browser matrix was not exercised. Production build warns about
the Three.js bundle size, and existing Three.js/Starlette dependency deprecations
remain non-blocking. Deployment and Stage 2 features were not performed.

Temporary API, worker, Vite and PostgreSQL processes were stopped after verification,
restoring the previous stopped state and retaining the application database volume.
