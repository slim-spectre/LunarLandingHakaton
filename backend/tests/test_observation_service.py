"""Deterministic unit tests for geometric observation service.

Tests ENU cardinal directions, unit vector invariants, visibility thresholds,
golden window evaluation, contract schema compliance, and input validation.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import httpx
import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker

from app.astronomy.horizons import EphemerisObservation, HorizonsProvider
from app.astronomy.observation import (
    calculate_direction_enu,
    calculate_geometric_observation,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = ROOT / "contracts" / "reference" / "horizons"
CONTRACT_PATH = ROOT / "contracts" / "openapi.v1.yaml"
OPENAPI_SPEC = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))


def load_fixture(filename: str) -> dict:
    fixture_path = FIXTURES_DIR / filename
    assert fixture_path.exists(), f"Fixture file not found: {fixture_path}"
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def point_validator() -> Draft202012Validator:
    schema = {
        "$ref": "#/components/schemas/Point",
        "components": OPENAPI_SPEC["components"],
    }
    return Draft202012Validator(schema, format_checker=FormatChecker())


# --- 1. ENU Cardinal Directions and Invariants ---


def test_enu_cardinal_directions():
    # North: azimuth 0 deg, elevation 0 deg
    north_vec = calculate_direction_enu(0.0, 0.0)
    assert north_vec.east == pytest.approx(0.0, abs=1e-6)
    assert north_vec.north == pytest.approx(1.0, abs=1e-6)
    assert north_vec.up == pytest.approx(0.0, abs=1e-6)

    # East: azimuth 90 deg, elevation 0 deg
    east_vec = calculate_direction_enu(90.0, 0.0)
    assert east_vec.east == pytest.approx(1.0, abs=1e-6)
    assert east_vec.north == pytest.approx(0.0, abs=1e-6)
    assert east_vec.up == pytest.approx(0.0, abs=1e-6)

    # South: azimuth 180 deg, elevation 0 deg
    south_vec = calculate_direction_enu(180.0, 0.0)
    assert south_vec.east == pytest.approx(0.0, abs=1e-6)
    assert south_vec.north == pytest.approx(-1.0, abs=1e-6)
    assert south_vec.up == pytest.approx(0.0, abs=1e-6)

    # West: azimuth 270 deg, elevation 0 deg
    west_vec = calculate_direction_enu(270.0, 0.0)
    assert west_vec.east == pytest.approx(-1.0, abs=1e-6)
    assert west_vec.north == pytest.approx(0.0, abs=1e-6)
    assert west_vec.up == pytest.approx(0.0, abs=1e-6)

    # Zenith: any azimuth, elevation +90 deg
    zenith_vec = calculate_direction_enu(45.0, 90.0)
    assert zenith_vec.east == pytest.approx(0.0, abs=1e-6)
    assert zenith_vec.north == pytest.approx(0.0, abs=1e-6)
    assert zenith_vec.up == pytest.approx(1.0, abs=1e-6)

    # Nadir: any azimuth, elevation -90 deg
    nadir_vec = calculate_direction_enu(45.0, -90.0)
    assert nadir_vec.east == pytest.approx(0.0, abs=1e-6)
    assert nadir_vec.north == pytest.approx(0.0, abs=1e-6)
    assert nadir_vec.up == pytest.approx(-1.0, abs=1e-6)


@pytest.mark.parametrize(
    ("azimuth", "elevation"),
    [
        (0.0, 0.0),
        (90.0, 0.0),
        (180.0, 0.0),
        (270.0, 0.0),
        (45.0, 45.0),
        (135.0, -30.0),
        (225.0, 60.0),
        (315.0, -60.0),
        (177.278712, -1.088272),
        (142.714718, -6.178829),
        (322.365998, 1.490814),
    ],
)
def test_enu_unit_vector_length(azimuth: float, elevation: float):
    vec = calculate_direction_enu(azimuth, elevation)
    norm_sq = vec.east**2 + vec.north**2 + vec.up**2
    assert norm_sq == pytest.approx(1.0, abs=1e-6)
    assert math.sqrt(norm_sq) == pytest.approx(1.0, abs=1e-6)


# --- 2. Visibility Threshold Testing ---


def test_visibility_threshold_strict_inequality_zero_margin():
    # Base threshold = horizon_elevation_deg(0.0) + margin(0.0) = 0.0
    # visible = elevation > threshold (strict inequality)

    class DummyProvider:
        def __init__(self, elevation: float):
            self.elevation = elevation

        def query_body(self, *, target, **kwargs):
            return EphemerisObservation(
                target=target,
                timestamp="2027-07-15T12:00:00Z",
                azimuth_deg=100.0,
                elevation_deg=self.elevation,
                solar_presence=None,
                interfering_marker=None,
                source_url="https://example.org",
                retrieval_time="2027-07-15T12:00:00Z",
                provider_name="TestProvider",
                ephemeris_source="DE441",
                request_params={},
            )

    # 1. Below threshold: elevation = -0.001 -> visible = False
    p_below = calculate_geometric_observation(
        latitude=-89.44,
        longitude=222.1,
        target_time="2027-07-15T12:00:00Z",
        visibility_margin_deg=0.0,
        provider=DummyProvider(-0.001),
    )
    assert not p_below.sun.visible
    assert not p_below.earth.visible
    assert not p_below.is_golden_window

    # 2. Exactly at threshold: elevation = 0.0 -> visible = False (strict inequality)
    p_at = calculate_geometric_observation(
        latitude=-89.44,
        longitude=222.1,
        target_time="2027-07-15T12:00:00Z",
        visibility_margin_deg=0.0,
        provider=DummyProvider(0.0),
    )
    assert not p_at.sun.visible
    assert not p_at.earth.visible
    assert not p_at.is_golden_window

    # 3. Above threshold: elevation = 0.001 -> visible = True
    p_above = calculate_geometric_observation(
        latitude=-89.44,
        longitude=222.1,
        target_time="2027-07-15T12:00:00Z",
        visibility_margin_deg=0.0,
        provider=DummyProvider(0.001),
    )
    assert p_above.sun.visible
    assert p_above.earth.visible
    assert p_above.is_golden_window


def test_visibility_threshold_with_nonzero_margin():
    # threshold = 0.0 + 2.0 = 2.0 degrees

    class ConfigurableProvider:
        def query_body(self, *, target, **kwargs):
            elev = 1.99 if target == "Sun" else 2.01
            return EphemerisObservation(
                target=target,
                timestamp="2027-07-15T12:00:00Z",
                azimuth_deg=100.0,
                elevation_deg=elev,
                solar_presence=None,
                interfering_marker=None,
                source_url="https://example.org",
                retrieval_time="2027-07-15T12:00:00Z",
                provider_name="TestProvider",
                ephemeris_source="DE441",
                request_params={},
            )

    point = calculate_geometric_observation(
        latitude=-89.44,
        longitude=222.1,
        target_time="2027-07-15T12:00:00Z",
        visibility_margin_deg=2.0,
        provider=ConfigurableProvider(),
    )

    # Sun is 1.99 <= 2.0 -> False
    assert not point.sun.visible
    # Earth is 2.01 > 2.0 -> True
    assert point.earth.visible
    # Not both visible -> is_golden_window = False
    assert not point.is_golden_window


# --- 3. Boolean Golden Window Conditions ---


@pytest.mark.parametrize(
    ("sun_elev", "earth_elev", "expected_golden"),
    [
        (5.0, 10.0, True),  # Both visible
        (5.0, -2.0, False),  # Sun visible, Earth invisible
        (-1.0, 10.0, False),  # Sun invisible, Earth visible
        (-1.0, -2.0, False),  # Both invisible
    ],
)
def test_golden_window_boolean_condition(sun_elev: float, earth_elev: float, expected_golden: bool):
    class SplitProvider:
        def query_body(self, *, target, **kwargs):
            elev = sun_elev if target == "Sun" else earth_elev
            return EphemerisObservation(
                target=target,
                timestamp="2027-07-15T12:00:00Z",
                azimuth_deg=90.0,
                elevation_deg=elev,
                solar_presence=None,
                interfering_marker=None,
                source_url="https://example.org",
                retrieval_time="2027-07-15T12:00:00Z",
                provider_name="TestProvider",
                ephemeris_source="DE441",
                request_params={},
            )

    point = calculate_geometric_observation(
        latitude=-89.44,
        longitude=222.1,
        target_time="2027-07-15T12:00:00Z",
        provider=SplitProvider(),
    )
    assert point.is_golden_window is expected_golden
    assert point.is_golden_window == (point.sun.visible and point.earth.visible)


# --- 4. End-to-End Execution with Stage 0 Reference Fixtures ---


def test_calculate_observation_shackleton_connecting_ridge():
    sun_fixture = load_fixture("shackleton-sun.json")
    earth_fixture = load_fixture("shackleton-earth.json")

    def mock_handler(request):
        url_str = str(request.url)
        if "%2710%27" in url_str or "COMMAND=%2710%27" in url_str:
            return httpx.Response(200, json=sun_fixture["raw_response"])
        elif "%27399%27" in url_str or "COMMAND=%27399%27" in url_str:
            return httpx.Response(200, json=earth_fixture["raw_response"])
        raise ValueError(f"Unexpected request URL: {url_str}")

    client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    provider = HorizonsProvider(client=client)

    point = calculate_geometric_observation(
        latitude=-89.44,
        longitude=222.1,
        target_time="2027-07-15T12:00:00Z",
        observer_height_m=2.0,
        visibility_margin_deg=0.0,
        provider=provider,
    )

    # Verify Sun observation
    assert point.sun.azimuth_deg == pytest.approx(177.278712, abs=1e-6)
    assert point.sun.elevation_deg == pytest.approx(-1.088272, abs=1e-6)
    assert point.sun.horizon_elevation_deg == 0.0
    assert not point.sun.visible  # -1.088272 <= 0.0

    # Verify Earth observation
    assert point.earth.azimuth_deg == pytest.approx(142.714718, abs=1e-6)
    assert point.earth.elevation_deg == pytest.approx(-6.178829, abs=1e-6)
    assert point.earth.horizon_elevation_deg == 0.0
    assert not point.earth.visible  # -6.178829 <= 0.0

    assert not point.is_golden_window

    # Validate output dictionary strictly adheres to OpenAPI Point schema
    point_dict = point.model_dump()
    point_validator().validate(point_dict)

    # Verify provenance metadata is preserved
    assert len(point.sources) == 2
    sun_source = next(s for s in point.sources if s.target == "Sun")
    earth_source = next(s for s in point.sources if s.target == "Earth")

    assert sun_source.name == "NASA/JPL Horizons API"
    assert sun_source.version == "DE441"
    assert "https://ssd.jpl.nasa.gov/api/horizons.api" in sun_source.url
    assert sun_source.settings["COMMAND"] == "'10'"
    assert sun_source.settings["CENTER"] == "'coord@301'"

    assert earth_source.name == "NASA/JPL Horizons API"
    assert earth_source.version == "DE441"
    assert earth_source.settings["COMMAND"] == "'399'"


def test_calculate_observation_faustini_rim_a():
    sun_fixture = load_fixture("faustini-sun.json")
    earth_fixture = load_fixture("faustini-earth.json")

    def mock_handler(request):
        url_str = str(request.url)
        if "%2710%27" in url_str or "COMMAND=%2710%27" in url_str:
            return httpx.Response(200, json=sun_fixture["raw_response"])
        elif "%27399%27" in url_str or "COMMAND=%27399%27" in url_str:
            return httpx.Response(200, json=earth_fixture["raw_response"])
        raise ValueError(f"Unexpected request URL: {url_str}")

    client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    provider = HorizonsProvider(client=client)

    point = calculate_geometric_observation(
        latitude=-87.45,
        longitude=77.0,
        target_time="2027-07-15T12:00:00Z",
        observer_height_m=2.0,
        visibility_margin_deg=0.0,
        provider=provider,
    )

    # At Faustini Rim A, Sun is above geometric horizon (+1.49 deg)
    assert point.sun.azimuth_deg == pytest.approx(322.365998, abs=1e-6)
    assert point.sun.elevation_deg == pytest.approx(1.490814, abs=1e-6)
    assert point.sun.visible

    # Earth is below geometric horizon (-4.95 deg)
    assert point.earth.azimuth_deg == pytest.approx(288.064862, abs=1e-6)
    assert point.earth.elevation_deg == pytest.approx(-4.947411, abs=1e-6)
    assert not point.earth.visible

    # Golden window is false because Earth is obscured
    assert not point.is_golden_window


# --- 5. Input Validation ---


@pytest.mark.parametrize("lat", [-90.1, 90.1, float("nan"), float("inf")])
def test_reject_invalid_latitude(lat):
    with pytest.raises(ValueError, match="Latitude"):
        calculate_geometric_observation(
            latitude=lat,
            longitude=0.0,
            target_time="2027-07-15T12:00:00Z",
        )


@pytest.mark.parametrize("lon", [-180.1, 360.0, float("nan"), float("inf")])
def test_reject_invalid_longitude(lon):
    with pytest.raises(ValueError, match="Longitude"):
        calculate_geometric_observation(
            latitude=0.0,
            longitude=lon,
            target_time="2027-07-15T12:00:00Z",
        )


def test_reject_naive_timestamp():
    with pytest.raises(ValueError, match="timezone"):
        calculate_geometric_observation(
            latitude=0.0,
            longitude=0.0,
            target_time="2027-07-15T12:00:00",  # No timezone
        )


@pytest.mark.parametrize(
    "out_of_bounds_time",
    [
        "1999-12-31T23:59:59Z",
        "2050-01-01T00:00:00Z",
        "2055-06-01T00:00:00Z",
    ],
)
def test_reject_time_outside_supported_epoch_range(out_of_bounds_time):
    with pytest.raises(ValueError, match="target_time must be within"):
        calculate_geometric_observation(
            latitude=0.0,
            longitude=0.0,
            target_time=out_of_bounds_time,
        )


@pytest.mark.parametrize("height", [-0.1, 20.1, float("nan")])
def test_reject_invalid_observer_height(height):
    with pytest.raises(ValueError, match="observer_height_m"):
        calculate_geometric_observation(
            latitude=0.0,
            longitude=0.0,
            target_time="2027-07-15T12:00:00Z",
            observer_height_m=height,
        )


@pytest.mark.parametrize("margin", [-0.1, 5.1, float("nan")])
def test_reject_invalid_visibility_margin(margin):
    with pytest.raises(ValueError, match="visibility_margin_deg"):
        calculate_geometric_observation(
            latitude=0.0,
            longitude=0.0,
            target_time="2027-07-15T12:00:00Z",
            visibility_margin_deg=margin,
        )
