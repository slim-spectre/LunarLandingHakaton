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
