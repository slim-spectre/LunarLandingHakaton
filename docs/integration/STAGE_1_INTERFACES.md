# Stage 1 Astronomy Integration: Observation Service & Horizons Provider

Handoff document for Stage 1 production astronomy service implementation.
Covers the JPL Horizons provider, single-time geometric observation service,
returned contract DTOs, and instructions for background job invocation.

## 1. Public Service Interface

The public entry point is `calculate_geometric_observation`, located in `app.astronomy`.

```python
from datetime import datetime
from app.astronomy import calculate_geometric_observation, ObservationPoint

point: ObservationPoint = calculate_geometric_observation(
    latitude=-89.44,
    longitude=222.1,
    target_time="2027-07-15T12:00:00Z",
    observer_height_m=2.0,            # optional, default 2.0 m (range: 0-20 m)
    visibility_margin_deg=0.0,        # optional, default 0.0 deg (range: 0-5 deg)
    provider=None,                     # optional, defaults to HorizonsProvider()
)
```

### Input Parameters & Validation Rules

- `latitude` (`float`): Lunar surface latitude in degrees $[-90, +90]$.
- `longitude` (`float`): Lunar surface longitude in degrees $[-180, 360)$ (positive East).
  Normalized automatically to $[-180, +180)$ per API v1 specification.
- `target_time` (`datetime | str`): Timezone-aware timestamp in ISO 8601 format.
  Must lie within the supported API epoch $[2000-01-01\text{T}00:00:00\text{Z}, 2050-01-01\text{T}00:00:00\text{Z})$.
  Timezone-naive dates are rejected with `ValueError`.
- `observer_height_m` (`float`): Observer height above base surface in metres $[0, 20]$.
  Converted to provider units (kilometres) at the provider boundary.
- `visibility_margin_deg` (`float`): Angle margin in degrees $[0, 5]$.
- `provider` (`HorizonsProvider | None`): Optional injected provider instance for testing.

## 2. Required Configuration

Settings are integrated into `app.core.config.Settings` and can be configured via environment variables or `.env`:

| Setting | Environment Variable | Default | Purpose |
|---|---|---|---|
| `horizons_api_url` | `HORIZONS_API_URL` | `https://ssd.jpl.nasa.gov/api/horizons.api` | JPL Horizons API endpoint |
| `horizons_timeout_seconds` | `HORIZONS_TIMEOUT_SECONDS` | `15.0` | Per-request network timeout (seconds) |

## 3. Returned Contract DTOs

The returned object is an instance of `ObservationPoint` (also aliased as `Point`), matching the canonical OpenAPI 3.1 schema `#/components/schemas/Point`.

```python
class DirectionENU(BaseModel):
    east: float   # [-1.0, 1.0]
    north: float  # [-1.0, 1.0]
    up: float     # [-1.0, 1.0]

class BodyObservation(BaseModel):
    azimuth_deg: float            # [0, 360), clockwise from North
    elevation_deg: float          # [-90, 90]
    horizon_elevation_deg: float  # 0.0 in Stage 1 geometric mode
    visible: bool                 # elevation_deg > horizon_elevation_deg + visibility_margin_deg
    direction_enu: DirectionENU   # Unit vector (norm == 1 within 1e-6)

class ObservationPoint(BaseModel):
    timestamp: str                # ISO 8601 UTC with 'Z' suffix
    sun: BodyObservation
    earth: BodyObservation
    is_golden_window: bool        # sun.visible AND earth.visible
    sources: list[SourceMetadata] # Excluded from JSON dump; available for job metadata
```

### Key Contract Conventions

1. **Body Centers**: Ephemeris queries request target centers (Sun Solar System Barycenter / center `COMMAND='10'` and Earth center `COMMAND='399'`).
2. **Airless Apparent Coordinates**: Refraction is omitted (`Atmos refraction: NO (AIRLESS)`).
3. **Local ENU Coordinates**:
   - $\text{east} = \cos(\text{elevation}) \cdot \sin(\text{azimuth})$
   - $\text{north} = \cos(\text{elevation}) \cdot \cos(\text{azimuth})$
   - $\text{up} = \sin(\text{elevation})$
   - Three.js mapping: `scene.x = east`, `scene.y = up`, `scene.z = -north`.
4. **Visibility Logic**:
   - Strict inequality: `visible = elevation_deg > horizon_elevation_deg + visibility_margin_deg`.
   - At threshold ($0.0^\circ$), `visible` evaluates to `False`.
   - `is_golden_window = sun.visible and earth.visible`.
5. **OpenAPI Serialization**:
   - Calling `point.model_dump()` returns only `timestamp`, `sun`, `earth`, and `is_golden_window`.
   - It directly validates against `#/components/schemas/Point` with `additionalProperties: false`.

## 4. Provider Error Hierarchy

All provider errors derive from `HorizonsError`:

```
HorizonsError (base)
 ├── HorizonsTransportError (network timeout, connection drop, DNS failure)
 ├── HorizonsHttpError (non-200 HTTP response status; carries .status_code)
 ├── HorizonsProviderError (error reported inside HTTP 200, e.g. unknown target, date constraint)
 └── HorizonsParseError (missing $$SOE/$$EOE delimiters, missing 'n.a.' values, malformed row)
```

In addition, parameter errors raise standard `ValueError` with descriptive explanations.

## 5. How Yaroslav Should Invoke from a Job

For `POST /ephemeris/now`, the asynchronous job worker should invoke `calculate_geometric_observation` and assemble the `NowResult` response:

```python
from datetime import UTC, datetime
from app.astronomy import (
    calculate_geometric_observation,
    HorizonsError,
)

def execute_now_calculation_job(
    job_id: str,
    resolved_site: dict,
    target_time: str,
    observer_height_m: float = 2.0,
    visibility_margin_deg: float = 0.0,
) -> dict:
    try:
        point = calculate_geometric_observation(
            latitude=resolved_site["latitude"],
            longitude=resolved_site["longitude"],
            target_time=target_time,
            observer_height_m=observer_height_m,
            visibility_margin_deg=visibility_margin_deg,
        )

        # Assemble contract-compliant metadata sources
        contract_sources = [source.to_contract_source() for source in point.sources]

        now_result = {
            "site": resolved_site,
            "point": point.model_dump(),
            "meta": {
                "model_version": "de441-v1",
                "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "data_status": "fresh",
                "horizon_mode": "geometric",
                "time_resolution_minutes": None,
                "terrain_dataset_id": None,
                "sources": contract_sources,
            },
        }
        return now_result

    except HorizonsError as exc:
        # Record structured job failure
        record_job_failure(
            job_id=job_id,
            error_code="PROVIDER_ERROR",
            error_message=f"Astronomy ephemeris retrieval failed: {exc}",
        )
    except ValueError as exc:
        record_job_failure(
            job_id=job_id,
            error_code="VALIDATION_ERROR",
            error_message=str(exc),
        )
```

## 6. Verification Status & Remaining Limitations

### Verification Status

- **Unit & Integration Suite**: 193 automated tests pass deterministically without network access.
- **Reference Fixture Agreement**: Parser and observation calculations match the Stage 0 reference fixtures (`shackleton-sun.json`, `shackleton-earth.json`, `faustini-sun.json`, `faustini-earth.json`, `farside-sun.json`, `farside-earth.json`) within $10^{-6}$ degrees.
- **Live Control Probe**: Ran explicit live network probe against `https://ssd.jpl.nasa.gov/api/horizons.api`; live values agree with Stage 0 fixtures down to 6 decimal places ($177.278712^\circ$ azimuth, $-1.088272^\circ$ elevation).
- **Code Quality**: Passes `ruff check` and `ruff format` across the backend.

### Remaining Limitations (Scope for Later Stages)

1. **Horizon Occlusion**: Stage 1 uses a geometric horizon threshold of $0.0^\circ$. Real terrain occlusion and DEM ray-tracing belong to Stage 2 (`horizon_mode="terrain"`).
2. **Timeline Generation**: Multi-step time series (`POST /ephemeris/timeline`) and comparison scoring (`POST /ephemeris/compare`) are scheduled in background job pipelines.
