# Development/test fixtures

All JSON files are synthetic illustrations, not measured NASA results or outputs
of a running calculation service. Sources under example.org deliberately identify
fixture provenance. Only health exists in the Stage 0 server.

OpenAPI references and tests validate every fixture, including healthy/unavailable
database, accepted/queued/running/failed jobs, one observation, a one-day timeline
with two separate six-hour golden windows, comparison request/result, unavailable
terrain coverage and the TERRAIN_UNAVAILABLE error. Semantic tests check unit
vectors, strict visibility, sample/window consistency and v1 scores.
