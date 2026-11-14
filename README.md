# Lunar Landing Site Navigator вЂ” Stage 0

Repository root contains the existing `frontend/` and the new `backend/` side by
side. Run root commands from the directory containing this README, not its parent.
Frontend files and configuration belong to Sasha and Slavik and are preserved.

Python baseline is 3.12 (`.python-version` and backend metadata); Node baseline
is 22.13.0 (`.nvmrc`), with Node 22.13 or newer in the Node 22 series supported.
Install uv 0.9.9 and Docker with the Compose plugin. The backend lock is
`backend/uv.lock`; update dependencies deliberately with `uv lock` and review changes.

On Windows, install uv using an existing Python installation:

```powershell
python -m pip install --user uv==0.9.9
python -m uv python install 3.12
```

If `uv` is not on PATH, replace `uv` with `python -m uv` in the commands below.
The Python used to invoke uv can be a different version; uv selects Python 3.12
for the backend according to the project configuration.

If `.venv` reports `No Python at ...`, its base interpreter is missing or cannot
be accessed by that shell. From backend, repair it without changing the lockfile:

```powershell
python -m uv python install --reinstall 3.12
python -m uv sync --locked --python 3.12
python -m uv run --locked python --version
```

## Local setup

1. Copy `.env.example` to `.env` at repository root. Replace all `replace_me`
   values with local values. Set `DATABASE_URL` to match the PostgreSQL user,
   password, database and published port. Percent-encode special characters in
   URL credentials. Keep `.env` private; it is ignored by Git.
2. From repository root, start PostgreSQL:

   ```sh
   docker compose up -d --wait postgres
   ```

3. Install and run from `backend/` (uv downloads Python 3.12 if needed):

   ```sh
   cd backend
   uv sync --locked --python 3.12
   uv run --locked alembic upgrade head
   uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

   There are no domain migrations or domain tables in Stage 0. Alembic is ready
   for future reviewed migrations. Settings read the root `.env` independently
   of the current working directory.

4. In another terminal, request `http://localhost:8000/api/v1/health`:

   ```sh
   curl -i http://localhost:8000/api/v1/health
   ```

   Expect HTTP 200, `status: healthy`, `database: ok` and a UTC timestamp ending
   in `Z`. On Windows PowerShell use `curl.exe` to avoid older shell aliases.
5. From repository root run `docker compose stop postgres`, then repeat the
   request. Expect HTTP 503 and `error.code: DATABASE_UNAVAILABLE`. Restart with
   `docker compose up -d --wait postgres`. The check uses a fresh connection for
   every request, with two-second connection and statement timeouts.

## Checks

From `backend/`:

```sh
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pytest -m "not integration"
```

These include a minimal real TestClient request, health dependency tests, safe
error responses, CORS, OpenAPI 3.1 validation, reference resolution and fixture
schema validation. Each test has a 15-second timeout; CI jobs have 10-minute limits.

For the real PostgreSQL integration test, start PostgreSQL and set
`TEST_DATABASE_URL` to your local `DATABASE_URL` value, then run:

```sh
uv run --locked pytest -m integration
```

In PowerShell set `$env:TEST_DATABASE_URL = 'postgresql+psycopg://...'`; in POSIX
shells use `export TEST_DATABASE_URL='postgresql+psycopg://...'`.
Without this explicit variable the integration test is skipped. CI supplies it
and runs all tests against a PostgreSQL service.

## Frontend

Use Node 22.13.0 (for example `nvm use` from root when supported), then:

```sh
cd frontend
npm ci
npm run lint
npm run build
npm run dev
```

The existing scaffold already provides lint and build commands, so frontend CI
runs them now. No frontend package or configuration is created by this backend setup.

## Contract and source verification

Read `docs/API_V1.md`, `docs/CONTRACT_DECISIONS.md` and
`contracts/openapi.v1.yaml`. The supplied API v1 specification is now documented
in English with all 15 paths and synthetic fixtures. Only health is implemented;
planned routes are explicitly marked and return 404 in the Stage 0 server.
Errors use the agreed code, message, details and request_id fields. Remaining
lunar frame and schema review items are explicit in CONTRACT_DECISIONS.md.

The CSA probe is a separate, bounded live network operation, never part of tests.
From `backend/`, reproduce and replace its source observation report with:

```sh
uv run --locked python tools/verify_csa.py --tls12 --output ../docs/sources/csa.md
```

The tested CSA connection needs the explicit `--tls12` compatibility option in
this environment; default/TLS 1.3 connections were reset while TLS 1.2 succeeded.
Certificate and hostname verification stay enabled. The published RSS link
currently serves Atom XML, which the probe handles alongside RSS.

Exit 0 means feed verification completed (including zero relevant entries);
exit 1 means verification is incomplete and the report records the actual failure.
No provider endpoint runs inside the API. Never store downloaded datasets, secrets,
virtual environments, caches, frontend dependencies or build output in Git.
