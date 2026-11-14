# Stage 0 implementation and verification

Verified on 2026-11-13. Repository root:
`C:\Users\Admin\NASAProject\LunarLandingHakaton\LunarLandingHakaton`.
Branch: `Yaroslav`. Initial worktree was clean. No AGENTS.md was found.
No frontend tracked files were changed. No commits, pushes, merges or deployment occurred.

## Files added

- `.gitignore`, `.env.example`, `.python-version`, `.nvmrc`, `compose.yaml`, `README.md`
- `.github/workflows/ci.yaml`
- `backend/pyproject.toml`, `backend/uv.lock`, `backend/alembic.ini`
- `backend/app/__init__.py`, `backend/app/main.py`
- `backend/app/core/__init__.py`, `backend/app/core/config.py`, `backend/app/core/database.py`
- `backend/migrations/env.py`, `backend/migrations/script.py.mako`, `backend/migrations/versions/.gitkeep`
- `backend/tests/test_health.py`, `backend/tests/test_integration.py`, `backend/tests/test_contract.py`
- `backend/tools/verify_csa.py`
- `contracts/openapi.v1.yaml`, `contracts/reference/README.md`
- `contracts/examples/README.md`, `contracts/examples/healthy.json`, `contracts/examples/database-unavailable.json`
- `docs/API_V1.md`, `docs/CONTRACT_DECISIONS.md`, `docs/STAGE0_VERIFICATION.md`, `docs/sources/csa.md`

## Implemented

Locked Python 3.12 backend; explicit CORS configuration; real PostgreSQL connectivity;
health only; agreed complete error envelope; empty Alembic foundation; Compose;
complete planned-route OpenAPI 3.1 contract and fixtures (updated after specification receipt); deterministic tests and opt-in database
integration test; bounded CI backend and existing frontend checks; separate CSA probe.
No domain tables, scientific calculations or planned product endpoints were created.

## Commands and observed results

Commands below use `uv` 0.9.9. In this session uv was installed into a temporary
directory and invoked by absolute path. Python 3.12.12 was downloaded by uv.
The existing host Node was 24.16.0 and npm 11.13.0; frontend CI is configured for 22.12.0.

| Command | Result |
| --- | --- |
| `git rev-parse --show-toplevel`, `git branch --show-current`, `git status --short` | Confirmed nested repository, branch Yaroslav and initially clean worktree. |
| `python -m pip install --target <temporary-directory> uv==0.9.9` | Restricted DNS failed initially; approved network retry installed uv. |
| `uv lock`, `uv sync --locked --python 3.12` in backend | Passed; real lock generated and dependencies installed into ignored backend/.venv. |
| `uv lock --check` | Passed; 60 packages resolved. |
| `uv pip check` | Passed; 59 installed packages compatible. |
| `ruff check . --fix`, `ruff format .` | Passed; two files formatted. |
| `ruff check .`, `ruff format --check .` | Passed; 10 Python files formatted. |
| `pytest -m "not integration"` | Restricted localhost sockets caused a bounded timeout initially. Approved rerun passed all 8 selected tests in 0.95 seconds. |
| Initial `pytest` | 8 passed, 1 skipped in 2.71 seconds. Integration was initially skipped because TEST_DATABASE_URL was unset and Docker could not start. The later real-database run below resolves this gap. |
| `alembic heads` | Passed with no revisions, as intended for Stage 0. |
| `docker compose config --quiet` with temporary placeholder environment variables | Passed. No .env file created. |
| `docker info --format '{{.ServerVersion}}'` | Failed: Docker Desktop Linux engine named pipe absent. |
| `docker desktop start --timeout 40` | Failed: Docker Desktop still starting; context deadline exceeded. A subsequent docker info still failed. |
| `python tools/verify_csa.py --output ../docs/sources/csa.md` | Exit 1. Restricted DNS failed initially; approved network retry received WinError 10054 connection reset. Report records incomplete verification. |
| `npm ci`, `npm run lint`, `npm run build` in existing frontend | All passed on host Node 24.16.0; npm reported zero vulnerabilities. Node 22.12 CI execution has not run locally. |
| `git diff --exit-code -- frontend` | Passed; no tracked frontend changes. |
| `git check-ignore` for .env, backend/.venv, caches, frontend/node_modules and frontend/dist | All checked paths correctly ignored. |
| `git diff --check` | Passed for tracked changes. New files remain untracked until a developer reviews and stages them. |

The selected runtime combination is FastAPI 0.121.3, Starlette 0.49.3 and
HTTPX 0.28.1. TestClient successfully completed real in-process HTTP requests.
There is one upstream deprecation warning about AnyIO's BlockingPortal alias;
it did not affect the test results. The tests have a 15-second timeout and CI
jobs have a 10-minute limit.

## Unresolved work and reproduction

1. The full product API specification has now been supplied and documented in
   English. All 15 paths and required fixture categories are represented. Remaining
   schema choices and the exact lunar frame/vertical datum require review in
   CONTRACT_DECISIONS.md before planned calculation endpoints are implemented.
2. Real PostgreSQL verification is now complete; see the follow-up below. Reproduce
   with README.md local setup steps 1РІР‚вЂњ5, then set TEST_DATABASE_URL and run
   `uv run --locked pytest -m integration`. CI provides a real PostgreSQL service.
3. CSA feed verification is now complete with explicit TLS 1.2 and Atom parsing;
   see the latest follow-up and docs/sources/csa.md. No matching articles were
   present among the five observed entries. No source results were fabricated.
4. Reproduce deterministic checks using the README's locked setup, then run
   `uv run --locked ruff check .`, `uv run --locked ruff format --check .` and
   `uv run --locked pytest -m "not integration"` from backend. Frontend checks
   use the existing package-lock.json and the README's frontend commands.

## Follow-up: real PostgreSQL verification completed

On 2026-11-13, after Docker was started by the developer, Docker Engine 29.9.3
was available. No containers were initially running and no root .env existed.
The previous Docker startup failures above are historical observations.

An isolated Compose project, `lunar-stage0-check-55c91308`, used the unchanged
root compose.yaml and PostgreSQL 16.6 Alpine. A free localhost port and random
temporary password were supplied through process environment variables. No
credentials or .env files were written to the repository.

Executed commands and results:

1. `docker compose -p lunar-stage0-check-55c91308 -f compose.yaml up -d --wait --wait-timeout 60 postgres`
   downloaded the configured image and started a healthy real PostgreSQL container.
2. From backend, `.venv/Scripts/python.exe -m alembic upgrade head` completed
   successfully against that database.
3. With DATABASE_URL and TEST_DATABASE_URL pointing to this container,
   `.venv/Scripts/python.exe -m pytest` completed: **9 passed, no skipped tests,
   one upstream deprecation warning, 1.11 seconds**.
4. `.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port <free-port> --no-access-log`
   started a real HTTP server. A GET to /api/v1/health returned HTTP 200 with
   status healthy, database ok and timestamp `2026-11-13T20:19:38.547414Z`.
   Request duration was 0.375 seconds.
5. `docker compose -p lunar-stage0-check-55c91308 -f compose.yaml stop -t 5 postgres`
   stopped the database. The same HTTP route returned HTTP 503 in 2.025 seconds:
   `{"error":{"code":"DATABASE_UNAVAILABLE","message":"Database is unavailable"}}`.
6. Repeating the Compose up command restored PostgreSQL. The same API process,
   without restart, returned HTTP 200 with database ok and timestamp
   `2026-11-13T20:19:45.185238Z` in 0.011 seconds.
7. The verification API process was terminated. `docker compose -p lunar-stage0-check-55c91308 -f compose.yaml down --volumes --timeout 5`
   successfully removed only the temporary test container, network and volume.

The orchestration bounded each subprocess and HTTP request. No backend code or
frontend files needed changes. This follow-up changes only this report. The
full API specification was still pending at the time of this earlier check. It has
since been supplied and incorporated as described below. CSA verification remains incomplete.


## Follow-up: supplied API v1 contract incorporated

On 2026-11-13 the owner supplied the actual API v1 sections 5вЂ“12. The earlier
specification gap is resolved. API_V1.md is now an English translation of those
rules. OpenAPI 3.1 documents all 15 paths, 34 schemas and 14 synthetic JSON fixtures.
Only health is registered in the Stage 0 app. Planned endpoints remain unimplemented.

Changed files in this follow-up:

- README.md; backend/app/main.py; backend/tests/test_health.py;
  backend/tests/test_contract.py.
- docs/API_V1.md; docs/CONTRACT_DECISIONS.md; docs/STAGE0_VERIFICATION.md.
- contracts/openapi.v1.yaml; contracts/reference/README.md;
  contracts/examples/README.md; contracts/examples/healthy.json;
  contracts/examples/database-unavailable.json.
- Added contracts/examples/comparison-request.json, comparison-result.json,
  job-accepted.json, job-accepted-now.json, job-accepted-comparison.json,
  job-queued.json, job-running.json, job-failed.json, observation-result.json,
  timeline-two-golden-windows.json, terrain-unavailable.json and
  terrain-unavailable-error.json.

The error envelope now includes details and server-created UUID request_id with
matching X-Request-ID. Structural errors use HTTP 400; invalid values use 422.
Health rejects unknown query parameters and unsupported request bodies. Internal
errors remain safe. Generated runtime health/error responses are validated against
the canonical contract in tests.

Tests now cover every referenced request/response fixture and internal reference,
route implementation markers, bounds, forbidden aliases/unknown fields, mutually
exclusive site forms, timezone presence, input longitude limits, unit vectors,
angle/visibility consistency, separate golden windows and merged intervals,
duration-based percentages, next transitions, longitude normalization, requested
periods and comparison scores/order. Cross-field rules are documented using
x-invariants; planned scientific validators are not presented as implemented APIs.

Commands and actual results for the final version:

| Command/check | Result |
| --- | --- |
| backend ruff check . --fix and ruff format . | Fixed import ordering and formatted three changed Python files. Final lint and format checks passed for all 10 Python files. |
| backend python -m pytest -m "not integration" (before final additions) | 41 passed, 1 deselected in 1.71 seconds. |
| docker compose -p lunar-contract-check-92eb91ec -f compose.yaml up -d --wait --wait-timeout 60 postgres | Healthy real PostgreSQL 16.6 Alpine, isolated volume/network and free localhost port. Random temporary credentials were held only in process environment. |
| backend python -m alembic upgrade head | Passed against the real database. |
| backend python -m pytest with DATABASE_URL and TEST_DATABASE_URL set | **43 passed, no skipped tests, one upstream AnyIO deprecation warning, 1.59 seconds.** |
| Running uvicorn; GET /api/v1/health | HTTP 200, database ok, 0.223 seconds; UTC timestamp 2026-11-13T20:35:48.168969Z. |
| docker compose stop -t 5 postgres; same live HTTP request | HTTP 503 in 2.051 seconds; DATABASE_UNAVAILABLE, details=[], UUID request_id and matching X-Request-ID verified. |
| docker compose up -d --wait --wait-timeout 60 postgres; same API process | HTTP 200, database ok, 0.046 seconds; UTC timestamp 2026-11-13T20:35:55.359733Z. |
| Stop test API; docker compose down --volumes --timeout 5 for the isolated project | Passed; removed only the verification container, network and volume. |
| ruff check backend; ruff format --check backend | Passed, 10 files formatted. |
| git diff --exit-code -- frontend; git diff --check | Passed. No tracked frontend changes. Work remains uncommitted. |

Reproduction uses the existing README setup: copy/edit the ignored root .env,
start PostgreSQL with docker compose up -d --wait postgres, enter backend and
run uv sync --locked --python 3.12. Set TEST_DATABASE_URL to the same database URL,
then run `uv run --locked pytest`, `uv run --locked ruff check .` and
`uv run --locked ruff format --check .`. For live HTTP verification start
uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8000 and request
/api/v1/health, stop PostgreSQL, request again, restore PostgreSQL and repeat.
The expected statuses are 200, 503, 200 without restarting the API.

No dependencies, frontend files or calculation endpoints changed. No provider
results were fabricated. CSA source verification was not rerun during this contract
update; its previous actual failure remains recorded in docs/sources/csa.md.


## Follow-up: CSA source verification completed

On 2026-11-13 the live CSA source check succeeded. No provider API route was added.

Changed files: backend/tools/verify_csa.py, the new deterministic test module
backend/tests/test_csa_verification.py, README.md, docs/sources/csa.md,
docs/CONTRACT_DECISIONS.md and this report.

Diagnostics and actual results:

- Bounded default Python HTTPX requests to the official portal and published feed
  were reset (WinError 10054). No proxy environment variables were configured.
- Windows curl with Schannel returned HTTP 200, text/xml, 5987 bytes for the feed.
- Python HTTPX with verified TLS 1.3-only was reset. Verified TLS 1.2-only returned
  HTTP 200, text/xml, 5987 bytes. No certificate checks were disabled. The exact
  server/network cause remains unknown; the portable explicit compatibility mode
  is verified on this machine.
- Inspecting XML revealed Atom 1.0, not RSS channel/item XML. The old RSS-only
  parser's zero-item intermediate observation was invalid and superseded. The
  probe now handles Atom namespaces and alternate-link href attributes plus RSS.
- `python tools/verify_csa.py --tls12 --output ../docs/sources/csa.md` completed
  with exit 0. At 2026-11-13T20:41:59.203568Z the portal returned HTTP 200 with
  text/html;charset=UTF-8; its discovered feed returned HTTP 200 with text/xml.
  XML was valid. Atom contained five entries and fields author,id,link,published,
  summary,title,updated. Zero entries matched moon/artemis/gateway/canadarm3.
- `python -m pytest -m "not integration"`: 48 passed, 1 integration test deselected,
  one upstream deprecation warning, 1.40 seconds. Six new deterministic tests
  cover the observed Atom format, RSS compatibility, TLS certificate policy,
  no matching entries, malformed XML, unsupported XML and forbidden DTDs.
  MockTransport is used; live provider calls remain outside tests.
- Final `ruff check .` and `ruff format --check .` passed for 11 Python files.

To reproduce, from backend run:

```sh
uv run --locked python tools/verify_csa.py --tls12 --output ../docs/sources/csa.md
uv run --locked pytest -m "not integration"
uv run --locked ruff check .
uv run --locked ruff format --check .
```

The generated source report intentionally reflects the latest feed state, which
can change. No production CSA/cache/job endpoint or frontend file was changed.
The source-verification gap is resolved; scientific coordinate-frame and schema
review decisions remain tracked in CONTRACT_DECISIONS.md.

## Follow-up: Windows Python environment repair

The developer's PowerShell reported that the interpreter referenced by backend/.venv
was missing at the uv-managed Python installation path. The agent process could
still start that interpreter, so the precise difference between shell environments
was not established. The managed interpreter was reinstalled and the environment
resynchronized without changing application code, dependencies or uv.lock.

Executed from backend:

- `python -m uv python install --reinstall 3.12`: downloaded and installed Python
  3.12.12 successfully.
- `python -m uv sync --locked --python 3.12`: passed; 60 packages resolved and
  59 installed packages audited.
- `python -m uv run --locked python --version`: returned Python 3.12.12.
- `python -m uv run --locked python tools/verify_csa.py --tls12`: exit 0;
  at 2026-11-13T20:52:15.116004Z both portal and feed returned HTTP 200, valid Atom
  XML contained five entries and no keyword matches. This diagnostic run printed
  its report without replacing docs/sources/csa.md.

README.md now documents installing uv, invoking it through `python -m uv` when
PATH does not contain its executable, and repairing a missing managed interpreter.
Only README.md and this report changed in the repository for this repair.


## Follow-up: merged team changes and repaired CI

On 2026-11-14, repository Yaroslav was clean at 22a3b0a. git fetch origin
confirmed exactly one missing commit across all fetched remote branches:
a2ec8ef from feature/slavik-map-3d. git merge --no-commit --no-ff integrated its
12 map/scene/coordinate files without conflicts. No commit or push was made;
the local merge remains pending until the developer commits the reviewed changes.

Changed areas:

- Added the colleague's docs/frontend-coordinate-conventions.md, frontend map and
  scene components/tests, and coordinate helper/tests from that missing commit.
- Repaired frontend/package-lock.json with Node 22.13.0/npm 10.9.2; the missing
  @emnapi/core and @emnapi/runtime beta entries now resolve in clean installations.
- Updated .nvmrc, README.md and frontend/README.md to Node 22.13.0, compatible
  with jsdom 29.1.1. Added CI frontend tests and generated API type verification.
- Added .gitattributes to force LF for frontend/src/api/generated/schema.ts.
  The generator checks bytes, so Windows CRLF caused a false stale-file failure;
  regeneration changed line endings only, not the API contract or generated types.
- Formatted backend/tools/probe_maps.py and backend/tests/probes/test_map_sources.py
  and corrected their import ordering for Ruff.
- Fixed backend/tools/probe_horizons.py to convert both request times to UTC,
  reject timezone-free input, reject nonfinite/out-of-range provider angles and
  keep rounded longitudes within [-180,180). Added regression tests in
  backend/tests/probes/test_probe_horizons.py. The same longitude boundary fix
  and regression test were applied to the merged frontend coordinate helper.
- Updated this verification report. No dependency ranges or product API rules
  were changed, and no production calculation endpoints were implemented.

Actual commands and results:

| Command | Result |
| --- | --- |
| git fetch origin; git merge --no-commit --no-ff origin/feature/slavik-map-3d | Latest remote refs fetched; missing commit integrated with no conflicts and no commit. |
| npm install --package-lock-only --ignore-scripts using Node 22.13.0/npm 10.9.2 | Lock repaired; no reported vulnerabilities. |
| npm ci using the same Node/npm versions on Windows | Passed. |
| npm run generate:api; npm run check:api | Passed; generated schema content matches the contract. LF enforced by Git attributes. |
| backend ruff check . --fix; ruff format . | Import issue fixed; four changed Python files formatted. |
| backend pytest -m "not integration" | 110 passed, 1 deselected; final Ruff lint/format checks passed for 16 Python files. |
| Isolated Compose PostgreSQL project lunar-ci-fix-53f91558; backend pytest with TEST_DATABASE_URL | 111 passed, no skipped tests, one upstream AnyIO deprecation warning, 2.36 seconds. |
| docker compose down --volumes for that isolated project | Temporary database container, network and volume removed successfully. |
| Windows frontend npm run lint; npm test -- --testTimeout=10000; npm run build | Passed; 50 tests and successful production build. |
| Linux node:22.13.0-bookworm-slim container, read-only source mounts copied into temporary container workspace | npm ci, npm run lint, npm run check:api, npm test -- --testTimeout=10000 and npm run build all passed. 50 tests passed in 1.74 seconds; lint reported zero warnings/errors. Container removed automatically. |
| git diff --check | Passed; no whitespace errors. |

Reproduce with Node from .nvmrc: enter frontend, run npm ci, npm run lint,
npm run check:api, npm test -- --testTimeout=10000 and npm run build. From backend
run the locked Ruff checks and pytest; set TEST_DATABASE_URL to a running local
PostgreSQL instance to include integration tests, following README.md.

GitHub Actions was not rerun or changed remotely. Live scientific provider probes
and interactive browser/WebGL rendering were not reverified during this CI repair.
The remaining upstream AnyIO and Three.js deprecation notices did not fail checks.
