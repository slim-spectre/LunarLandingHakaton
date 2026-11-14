"""Geometric observation service for lunar surface sites.

Calculates topocentric apparent positions, local ENU direction vectors,
and visibility flags for the Sun and Earth at a single instant.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.astronomy.horizons import (
    HorizonsProvider,
    normalize_longitude,
)

MIN_SUPPORTED_TIME = datetime(2000, 1, 1, 0, 0, 0, tzinfo=UTC)
MAX_SUPPORTED_TIME = datetime(2050, 1, 1, 0, 0, 0, tzinfo=UTC)


class DirectionENU(BaseModel):
    """Local East-North-Up unit direction vector.

    Three.js mapping: scene.x = east, scene.y = up, scene.z = -north.
    Invariance: east**2 + north**2 + up**2 == 1 within 1e-6.
    """

    model_config = ConfigDict(extra="forbid")

    east: float = Field(ge=-1.0, le=1.0)
    north: float = Field(ge=-1.0, le=1.0)
    up: float = Field(ge=-1.0, le=1.0)


class BodyObservation(BaseModel):
    """Observation data for a single celestial body (Sun or Earth).

    Apparent topocentric coordinates refer to body centers without
    atmospheric refraction (airless lunar environment).
    """

    model_config = ConfigDict(extra="forbid")

    azimuth_deg: float = Field(ge=0.0, lt=360.0)
    elevation_deg: float = Field(ge=-90.0, le=90.0)
    horizon_elevation_deg: float = Field(ge=-90.0, le=90.0)
    visible: bool
    direction_enu: DirectionENU


class SourceMetadata(BaseModel):
    """Provenance metadata captured from the upstream ephemeris provider."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    url: str
    version: str | None = None
    fetched_at: str
    target: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)

    def to_contract_source(self) -> dict[str, Any]:
        """Convert to the canonical OpenAPI Source schema format."""
        return {
            "name": self.name,
            "url": self.url,
            "version": self.version,
            "fetched_at": self.fetched_at,
        }


class ObservationPoint(BaseModel):
    """Observation point at an instant containing Sun and Earth observations."""

    model_config = ConfigDict(extra="forbid")

    timestamp: str
    sun: BodyObservation
    earth: BodyObservation
    is_golden_window: bool
    sources: list[SourceMetadata] = Field(default_factory=list, exclude=True)


Point = ObservationPoint


def calculate_direction_enu(azimuth_deg: float, elevation_deg: float) -> DirectionENU:
    """Compute local East-North-Up unit vector from azimuth and elevation.

    Azimuth is measured clockwise from north:
      0 deg -> North, 90 deg -> East, 180 deg -> South, 270 deg -> West.
    Elevation is relative to local horizontal plane [-90, +90].

    Formulas:
      east  = cos(elevation) * sin(azimuth)
      north = cos(elevation) * cos(azimuth)
      up    = sin(elevation)
    """
    az_rad = math.radians(azimuth_deg)
    el_rad = math.radians(elevation_deg)
    cos_el = math.cos(el_rad)

    raw_east = cos_el * math.sin(az_rad)
    raw_north = cos_el * math.cos(az_rad)
    raw_up = math.sin(el_rad)

    # Clamp to [-1.0, 1.0] to guard against floating-point boundary imprecision
    east = max(-1.0, min(1.0, raw_east))
    north = max(-1.0, min(1.0, raw_north))
    up = max(-1.0, min(1.0, raw_up))

    return DirectionENU(east=east, north=north, up=up)


def calculate_geometric_observation(
    *,
    latitude: float,
    longitude: float,
    target_time: datetime | str,
    observer_height_m: float = 2.0,
    visibility_margin_deg: float = 0.0,
    provider: HorizonsProvider | None = None,
) -> ObservationPoint:
    """Calculate single-instant geometric observation for Sun and Earth.

    Stage 1 uses a geometric horizon threshold of 0.0 degrees without terrain occlusion.
    Body visibility follows strict inequality:
      visible = elevation_deg > horizon_elevation_deg + visibility_margin_deg
    is_golden_window is true only when both Sun and Earth are visible.
    """
    if not math.isfinite(latitude) or not -90.0 <= latitude <= 90.0:
        raise ValueError("Latitude must be a finite number between -90 and 90 degrees")

    if not math.isfinite(longitude) or not -180.0 <= longitude < 360.0:
        raise ValueError("Longitude must be a finite number in [-180, 360) degrees")

    norm_lon = normalize_longitude(longitude)

    if not math.isfinite(observer_height_m) or not 0.0 <= observer_height_m <= 20.0:
        raise ValueError("observer_height_m must be between 0 and 20 metres")

    if not math.isfinite(visibility_margin_deg) or not 0.0 <= visibility_margin_deg <= 5.0:
        raise ValueError("visibility_margin_deg must be between 0 and 5 degrees")

    if isinstance(target_time, str):
        dt = datetime.fromisoformat(target_time)
    else:
        dt = target_time

    if dt.tzinfo is None:
        raise ValueError("target_time must include an explicit timezone")

    dt_utc = dt.astimezone(UTC)
    if not (MIN_SUPPORTED_TIME <= dt_utc < MAX_SUPPORTED_TIME):
        min_iso = MIN_SUPPORTED_TIME.isoformat()
        max_iso = MAX_SUPPORTED_TIME.isoformat()
        raise ValueError(f"target_time must be within [{min_iso}, {max_iso})")

    active_provider = provider if provider is not None else HorizonsProvider()

    # Query ephemerides sequentially to avoid uncontrolled concurrent network load
    sun_ephem = active_provider.query_body(
        target="Sun",
        latitude=latitude,
        longitude=norm_lon,
        altitude_m=observer_height_m,
        target_time=dt_utc,
    )
    earth_ephem = active_provider.query_body(
        target="Earth",
        latitude=latitude,
        longitude=norm_lon,
        altitude_m=observer_height_m,
        target_time=dt_utc,
    )

    # Local ENU unit direction vectors
    sun_enu = calculate_direction_enu(sun_ephem.azimuth_deg, sun_ephem.elevation_deg)
    earth_enu = calculate_direction_enu(earth_ephem.azimuth_deg, earth_ephem.elevation_deg)

    # Stage 1 geometric horizon is 0.0 degrees
    horizon_elevation_deg = 0.0
    visibility_threshold = horizon_elevation_deg + visibility_margin_deg

    # Strict inequality per contract: elevation_deg > horizon_elevation_deg + visibility_margin_deg
    sun_visible = sun_ephem.elevation_deg > visibility_threshold
    earth_visible = earth_ephem.elevation_deg > visibility_threshold
    is_golden_window = sun_visible and earth_visible

    sun_observation = BodyObservation(
        azimuth_deg=sun_ephem.azimuth_deg,
        elevation_deg=sun_ephem.elevation_deg,
        horizon_elevation_deg=horizon_elevation_deg,
        visible=sun_visible,
        direction_enu=sun_enu,
    )

    earth_observation = BodyObservation(
        azimuth_deg=earth_ephem.azimuth_deg,
        elevation_deg=earth_ephem.elevation_deg,
        horizon_elevation_deg=horizon_elevation_deg,
        visible=earth_visible,
        direction_enu=earth_enu,
    )

    sources = [
        SourceMetadata(
            name=sun_ephem.provider_name,
            url=sun_ephem.source_url,
            version=sun_ephem.ephemeris_source,
            fetched_at=sun_ephem.retrieval_time,
            target="Sun",
            settings=sun_ephem.request_params,
        ),
        SourceMetadata(
            name=earth_ephem.provider_name,
            url=earth_ephem.source_url,
            version=earth_ephem.ephemeris_source,
            fetched_at=earth_ephem.retrieval_time,
            target="Earth",
            settings=earth_ephem.request_params,
        ),
    ]

    return ObservationPoint(
        timestamp=dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        sun=sun_observation,
        earth=earth_observation,
        is_golden_window=is_golden_window,
        sources=sources,
    )
