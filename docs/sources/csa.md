# CSA source feed verification

Live observation, not a production integration or scientific result. The RSS URL is discovered from the official Moon Exploration portal. RSS and Atom are parsed with external entities and DTDs prohibited. Entries reflect the feed at verification time; relevance uses keyword matching. TLS mode is explicit and certificate verification remains enabled.

```json
{
  "verified_at": "2026-11-13T20:53:58.493885Z",
  "official_source_url": "https://www.asc-csa.gc.ca/eng/astronomy/moon-exploration/",
  "tls_mode": "TLS1.2_only",
  "certificate_verification": true,
  "verification": "complete",
  "xml_valid": true,
  "item_fields": [
    "author",
    "id",
    "link",
    "published",
    "summary",
    "title",
    "updated"
  ],
  "relevant_entries": [],
  "portal_http_status": 200,
  "portal_content_type": "text/html;charset=UTF-8",
  "feed_url": "https://www.asc-csa.gc.ca/rss/default_eng.xml",
  "feed_http_status": 200,
  "feed_content_type": "text/xml",
  "feed_format": "atom",
  "item_count": 5,
  "matching_item_count": 0
}
```


## Stage 1 resource-route verification (2026-11-14)

GET /api/v1/resources/csa now uses the same verified official feed with TLS 1.2,
certificate validation and safe Atom/RSS parsing. One initial live API attempt
returned 503 CSA_UNAVAILABLE with no cache; its exact underlying network failure
was not identified. A later fresh-database check returned HTTP 200, items=[],
data_status=fresh and fetched_at=2026-11-14T13:28:37.391057Z. Recreating the API app
returned data_status=cached with the same fetched_at from PostgreSQL. No matching
articles were fabricated. See ../integration/STAGE1_BACKEND.md for cache policies,
reproduction, test results and the separate production worker design.

## Concurrent initial refresh diagnosis and correction (2026-11-14)

A later direct API check returned HTTP 200, items=[] and data_status=cached, with
fetched_at=2026-11-14T15:07:17.796391Z. The verification script run at
2026-11-14T15:09:56.927825Z also returned HTTP 200 for both the official portal
and published feed, valid Atom XML, five entries and zero relevant matches.
No repository source report was overwritten by that probe.

A controlled reproduction found an independent local defect: with an empty
cache and an active refresh, a second request immediately returned CSA_UNAVAILABLE
although the first refresh succeeded. This can also be triggered by repeated
development mount requests. It does not prove that every earlier network failure
had the same cause; earlier ConnectError logs remain actual transport failures.

The corrected backend waits up to 15 seconds for another refresh to populate the
cache, polling every 100 ms after releasing the unsuccessful lock connection.
It does not issue another provider request. Fresh/cached/stale metadata, cache
retention, common errors and the valid empty-feed response remain unchanged.
A usable stale cache returns immediately; timeout without usable data remains
503. The official source can still fail independently of this concurrency fix.

Reproduce deterministic checks from backend/:

```powershell
python -m uv run --locked pytest tests/test_stage1_csa.py -q
python -m uv run --locked ruff check .
python -m uv run --locked ruff format --check .
```

The first new regression test failed against the original code with
CSA_UNAVAILABLE, and passed after the correction. The 14 CSA tests cover a shared
initial refresh, bounded waiting, rejection of expired cache, immediate stale
cache and actual source failure. A PostgreSQL integration regression in
tests/test_stage1_postgres.py coordinates two real database connections and checks
that both callers succeed with one controlled test-only feed fetch. Run it with
TEST_DATABASE_URL set to a dedicated test database, never the application database:

```powershell
python -m uv run --locked pytest tests/test_stage1_postgres.py -k parallel_csa -q
```

Final verification results:

- `pytest -m "not integration" -q`: 252 passed; one opt-in live Horizons probe skipped.
- `pytest tests/test_stage1_postgres.py -q`: all three tests passed in a newly
  created isolated PostgreSQL database, including the concurrent CSA regression.
- `pytest tests/test_integration.py -q`: the real PostgreSQL health check passed.
- Backend Ruff lint and formatting checks passed; `git diff --check` passed.
- An initial combined run hit an unbounded test connection timeout and was
  interrupted. The successful integration runs used 127.0.0.1 with
  connect_timeout=2; temporary test databases were removed. Application data was
  not cleared or populated with test fixtures.
- The API was restarted with the correction. A real GET /api/v1/resources/csa
  returned HTTP 200, items=[] and data_status=stale, retaining the actual
  fetched_at=2026-11-14T15:07:17.796391Z while the new source refresh failed.
  This is a valid retained empty-feed cache, not fabricated articles.

The frontend, worker and PostgreSQL remain running for local manual testing.
No commit, push, merge or deployment was performed. The existing Starlette/AnyIO
deprecation warning remains unrelated to the CSA correction.

Finally, Refresh resources was clicked in the existing browser without changing
the user's selected scenario. It displayed fresh, retrieved at
2026-11-14T15:24:36.022192Z, and "No matching articles in the available feed."
The previous CSA_UNAVAILABLE message disappeared. This confirms successful live
retrieval after the correction; it does not guarantee future provider availability.
