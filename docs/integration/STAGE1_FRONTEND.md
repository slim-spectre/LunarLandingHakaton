# Stage 1 frontend product and API integration

This document records the initial frontend handoff. For the completed integration
with the subsequently merged map/scene components, see [STAGE1_COMPLETION.md](STAGE1_COMPLETION.md).

## Scope and files

Implemented in the existing frontend on branch Yaroslav. The initial worktree was
clean. No dependencies, lockfiles, API schemas, backend files, map/scene internals
or coordinate utilities were changed. No commit, push, merge or deployment was made.

- `frontend/src/App.tsx`, `App.css`, `App.test.tsx`: Stage 1 shell, responsive
  workspace styling and application integration tests.
- `frontend/src/api/client.ts`, `errors.ts`, `types.ts`, `observation.test.ts`:
  generated contract type aliases, catalog/resources/observation transport,
  strict HTTP 202 acceptance, bounded requests, safe job URLs and transport tests.
- `frontend/src/features/observation/`: scenario validation, shared form state,
  polling lifecycle, numerical result/provenance display and deterministic tests.
- `frontend/src/features/resources/`: CSA loading, refresh, fresh/cached/stale,
  empty/error states and deterministic component tests.
- `frontend/src/components/SourceLink.tsx`, `RequestError.tsx`: HTTP(S)-only
  external links and common error display.
- `frontend/src/test/fixtures.ts`: test-only typed fixtures loading the committed
  contract examples. Synthetic catalog/news fixtures are explicitly labelled.
- `frontend/README.md`, this handoff: reproducible setup and integration details.

## Behavior

The catalog uses GET /api/v1/sites with category filtering and 50-item pages.
Selection retains the returned description and source/verified QuickMap links.
Custom inputs send coordinates and an optional name, without site_id. Latitude
is validated without clamping. Longitude input accepts [-180,360); normalization
belongs to the backend. The map receives only coordinates in its supported
normalized range; other custom longitudes get their marker after a result arrives.

The date/time control is explicitly UTC. Serialization appends Z to validated
calendar fields rather than interpreting them in the browser's local timezone.
The range is [2000-01-01T00:00:00Z,2050-01-01T00:00:00Z). Whole seconds match the
current astronomy integration; fractional seconds are rejected, never rounded.
Height is 0–20 metres and visibility margin 0–5 degrees. Only geometric mode is
offered. There are no frontend astronomical or visibility calculations.

POST /api/v1/ephemeris/now must return 202, including cache hits. Polling uses the
returned status URL every two seconds, with at most one poll in flight. Success
fetches the returned result URL once; failure or transport error stops polling.
Queued/running/failed, terrain unavailable, result not ready, unknown/expired jobs,
network failures and bounded timeouts have explicit display states.

New submission, any scenario edit, Stop waiting and unmount abort pending client
requests and clear timers. A sequence token also rejects stale responses when a
transport fails to honor abort. Stop waiting does not cancel a durable server job.
Old results are cleared on scenario changes/submission so they cannot describe the
new selection. Before success all visibility/availability values remain unknown.

Results display the returned normalized site, observation instant, Sun/Earth
angles and flags, simultaneous availability, horizon mode, model, cache state,
surface/observer heights, generation time and source versions/retrieval times.
An instant does not establish a continuous golden window or a link budget.

CSA is always loaded through the backend. The UI displays short provider text
as React text, never HTML. Empty feeds are valid; source errors produce no fabricated
articles. Stale cache is explicitly labelled. Unsafe provider links are text only.
The existing explicit development demo switch affects health alone; observation
and resource routes never use operational fixtures. Production disables that switch.

## Integration with Slavik

The workspace mounts the existing exports from features/map and features/scene:

- LunarMap: selectedCoordinate, selectedSiteId and onSelectCoordinate. A map click
  switches the shared form to custom mode using the callback values unchanged.
- LunarScene: Sun/Earth direction_enu passed unchanged from the result,
  observerHeightM from the resolved site, null vectors before success, isLoading
  during requests. Its existing WebGL error boundary remains in place.
- Both height:100% components have explicit 340px wrapper heights in App.css.

These are the existing schematic coordinate grid and local ENU scene. Provider
imagery, physical terrain and map adapters are not implemented by this work.
Slavik can extend those components behind the same props. Backend integration
requires the existing Stage 1 migrations, API and separate worker; no schema
regeneration is needed for this frontend change.

## Reproduction

Run commands from the nested repository containing backend/, frontend/ and
compose.yaml. Follow the root README to install uv and configure the ignored
root .env; do not overwrite an existing .env.

1. Start Docker, then from repository root: `docker compose up -d --wait postgres`.
2. In backend/: `python -m uv sync --locked --python 3.12`, then
   `python -m uv run --locked alembic upgrade head`.
3. In backend/: `python -m uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8000`.
4. In another terminal in backend/: `python -m uv run --locked python -m app.worker`.
5. With Node 22.13.0/npm 10, in frontend/: `npm ci`, then `npm run dev`.
   Open http://localhost:5173 (the example CORS allowlist includes that origin).
6. Select a catalog site, choose an explicit UTC time, submit, and observe queued/
   running/result states. Repeat the exact scenario to exercise the server cache.
   Switch to custom coordinates to check latitude validation and normalized output.
7. From frontend/: `npm run lint`, `npm run typecheck`, `npm run check:api`,
   `npm run test -- --testTimeout=10000`, `npm run build`.

For another API address, create an ignored frontend/.env.local with VITE_API_URL
and restart Vite. The root backend .env is not automatically read by Vite. Include
the actual frontend origin in the backend CORS allowlist. Do not enable demo mode
for operational verification. Stop API, worker and Vite with Ctrl+C; stop the local
database with `docker compose stop postgres` when finished.

## Verification and limitations

Verification on 2026-11-14 used pinned Node 22.13.0/npm 10.9.2 via npm exec. The
first non-escalated npm invocation could not resolve registry.npmjs.org; the
approved invocation succeeded. An initial fixture-loading failure was corrected
by reading contract JSON with Node filesystem paths instead of Vite asset URLs.

Final command results (all exit 0):

| Command | Result |
| --- | --- |
| npm run lint | Passed, no warnings |
| npm run typecheck | Passed; build also reran TypeScript after the final edits |
| npm run check:api | Passed, no contract/type drift |
| npm run test -- --testTimeout=10000 | 103 tests passed in 10 files |
| npm run build | Passed; dist is ignored and not committed |
| docker compose up -d --wait postgres | PostgreSQL healthy |
| python -m uv run --locked alembic upgrade head | Existing migrations applied successfully |
| git diff --check | Passed |

For pinned tools on the verification host, npm commands were invoked as
`npm exec --yes --package=node@22.13.0 --package=npm@10.9.2 -- npm ...`.
Formatting used pinned prettier 3.6.2 through npm exec, without changing project
dependencies or package-lock.json. API, worker and Vite were run temporarily for
the browser check and stopped afterward; PostgreSQL was also stopped, retaining
its local data volume.

The real browser smoke check loaded eight PostgreSQL sites, submitted a Faustini
Rim A job, polled it, and displayed a fresh Horizons result for
2026-11-14T14:53:28Z (job 8d20abcc-cea0-4547-9364-16550dfd345e). Sun visibility
was Yes, Earth visibility No, simultaneous availability No, as returned by the
server. Source URLs, fetched_at and geometric-now-v1 were displayed. These values
are a smoke observation, not benchmark assertions or frontend fixtures.

The live CSA request returned CSA_UNAVAILABLE with no usable cache; the UI showed
that failure. Fresh/cached/stale/empty resource states are covered deterministically.
Live provider availability is not guaranteed. No new backend test run was needed
because backend code was unchanged. GitHub CI was not run remotely; no push occurred.

Subsequent CSA diagnosis identified and corrected a backend cold-cache concurrency
defect; see ../sources/csa.md. A second request now waits for the active refresh
instead of immediately reporting unavailable. The original frontend verification
and its recorded failure above remain historical observations. The fix and its
backend regression tests are separate from the original frontend-only file scope.

Production build reports a >500kB JavaScript chunk from the mounted Three.js scene;
it completes successfully. The existing scene test emits a Three.js CommonJS
deprecation warning, and the real scene emits a Three.Clock deprecation warning.
The corrected map wrapper height was rechecked visually in the real browser.
The initial workspace had no provider imagery; the final integration now displays
registered Moon Trek and LROC imagery. Physical terrain, timeline and comparison/ranking
remain outside Stage 1. Mobile layout is responsive CSS; a full mobile device matrix
has not been exercised.
